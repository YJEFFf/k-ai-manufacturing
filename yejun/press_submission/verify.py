"""outputs/를 동결된 기대값(outputs/expected/)과 비교한다 — PLAN.md §7·§9. 검수 R1·R6 반영.

    python verify.py --out outputs            # 비교 (실패 시 종료 코드 1)
    python verify.py --out outputs --freeze   # 현재 outputs를 기대값으로 동결 (필수 검사가 통과한 실행에서만)

규칙
- 단계별 필수 파일·검사 항목과 실행 시 파일 해시를 확인한 뒤 비교·동결한다.
- 기본은 동결된 실행과 같은 단계까지 검사한다. --steps N은 명시적인 부분 검사이며 실행 범위 안에서만 허용한다.
- 수치 열은 행의 `model` 값으로 허용오차를 고른다: 기본 1e-8, isolation_forest·mlp_ae_w5 1e-6, lstm 계열 1e-3. NaN·±inf는 패턴이 정확히 같아야 한다.
- 실행 메타데이터(cached·train_seconds·cache_key·epochs_run·경로)는 결과 수치와 분리해 비교하지 않는다.
- checks.json의 단계별 필수 검사(press/validation.py)가 true가 아니면 실패한다.
- 현재 패키지 코드 해시가 manifest의 code_sha256과 다르면(실행 후 코드 변경) 실패하고 동결도 거부한다.
- 주 모델 artifact(artifacts/main_A.json·main_B.json)도 실행 시 해시와 대조한다. 행별 예측·기록 파일은 Git에 없으므로
  갓 클론한 저장소에서는 run_all.py를 먼저 실행해야 통과한다.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from press.validation import (artifact_names, check_files, check_required, code_sha256, declared_steps,
                              output_names, result_names)

TOL_DEFAULT, TOL_BY_MODEL = 1e-8, {"isolation_forest": 1e-6, "mlp_ae_w5": 1e-6}
TOL_LSTM = 1e-3
META_COLUMNS = {"train_seconds", "cached", "cache_key", "epochs_run", "max_epochs", "patience"}
META_KEYS = {"cached", "train_seconds", "cache_key", "epochs_run", "max_epochs", "patience", "path", "data_dir", "notes"}
GIT_EXCLUDED = ("predictions_", "records_")   # yejun/.gitignore: 행별 파일은 실행해야 생긴다


def tol_for(model, fname: str) -> float:
    if "lstm" in fname or (isinstance(model, str) and "lstm" in model):
        return TOL_LSTM
    return TOL_BY_MODEL.get(model, TOL_DEFAULT)


def _strip_meta(obj):
    if isinstance(obj, dict):
        return {k: _strip_meta(v) for k, v in obj.items() if k not in META_KEYS}
    if isinstance(obj, list):
        return [_strip_meta(v) for v in obj]
    return obj


def compare_csv(a: Path, b: Path) -> dict:
    x, y = pd.read_csv(a), pd.read_csv(b)
    cols = [c for c in y.columns if c not in META_COLUMNS]
    if x.shape[0] != y.shape[0] or [c for c in x.columns if c not in META_COLUMNS] != cols:
        return dict(file=a.name, ok=False, reason=f"shape/columns {x.shape} vs {y.shape}")
    models = x["model"].astype(str).tolist() if "model" in x.columns else [None] * len(x)
    tols = np.array([tol_for(m, a.name) for m in models])
    worst, alarm_diff = 0.0, 0
    for c in cols:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float)
            xn, yn = ~np.isfinite(xv), ~np.isfinite(yv)
            if (xn != yn).any() or not np.array_equal(xv[xn], yv[yn], equal_nan=True):
                return dict(file=a.name, ok=False, reason=f"NaN/inf pattern differs in {c}")
            with np.errstate(invalid="ignore"):
                d = np.abs(xv - yv)
            d[xn] = 0.0
            over = d > tols
            if over.any():
                i = int(np.argmax(d - tols))
                return dict(file=a.name, ok=False, reason=f"{c} row {i} ({models[i]}): |Δ|={d[i]:.3g} > tol {tols[i]:g}")
            worst = max(worst, float(d.max()) if len(d) else 0.0)
            if c.startswith("alarm"):
                alarm_diff += int(((xv != yv) & ~xn).sum())
        elif not x[c].astype(str).equals(y[c].astype(str)):
            return dict(file=a.name, ok=False, reason=f"text column {c} differs")
    return dict(file=a.name, ok=alarm_diff == 0, max_abs_diff=worst, alarm_cells_diff=alarm_diff,
                reason="경보 판정이 다름" if alarm_diff else None)


def compare_json(a: Path, b: Path) -> dict:
    x, y = _strip_meta(json.loads(a.read_text(encoding="utf-8"))), _strip_meta(json.loads(b.read_text(encoding="utf-8")))
    tol = tol_for(None, a.name)

    def equal(left, right):
        if isinstance(left, dict) and isinstance(right, dict):
            return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
        if isinstance(left, list) and isinstance(right, list):
            return len(left) == len(right) and all(equal(u, v) for u, v in zip(left, right))
        if type(left) is bool or type(right) is bool:
            return type(left) is type(right) and left == right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if isinstance(left, int) or isinstance(right, int):
                return left == right
            if not math.isfinite(left) or not math.isfinite(right):
                return (math.isnan(left) and math.isnan(right)) or left == right
            return abs(left - right) <= tol
        return type(left) is type(right) and left == right

    ok = equal(x, y)
    return dict(file=a.name, ok=ok, reason=None if ok else f"결과 값이 다름(정수·범주는 정확 비교, 실수 허용오차 {tol:g})")


def result_files(out: Path, steps: int) -> list[Path]:
    return [out / name for name in sorted(result_names(steps))]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "outputs")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--steps", type=int, choices=range(1, 6), help="명시적인 부분 비교 범위. 동결은 실행한 모든 단계를 대상으로 한다")
    ap.add_argument("--artifacts", type=Path, default=None, help="주 모델 artifact 폴더. 기본: <out>/../artifacts (run_all과 같음)")
    args = ap.parse_args(argv)
    try:
        return verify_outputs(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"검증 실패: {exc}", file=sys.stderr)
        return 2


def verify_outputs(args):
    exp = args.out / "expected"
    checks = json.loads((args.out / "checks.json").read_text(encoding="utf-8"))
    man_now = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    steps = declared_steps(man_now, checks)
    bad_required = check_required(checks, steps)
    if man_now.get("inputs", {}).get("verified") is not True:
        bad_required.append("inputs.verified (--no-verify 실행은 비교·동결 불가)")
    bad_files = check_files(args.out, man_now, output_names(steps) | {"checks.json"})
    art_dir = args.artifacts or args.out.parent / "artifacts"
    bad_files += check_files(art_dir, man_now, artifact_names(steps), key="artifacts", label="artifacts/")
    if any(b.endswith("없음") and b.startswith(GIT_EXCLUDED) for b in bad_files):
        print("행별 예측·기록 파일이 없다. 이 파일은 Git에 없으므로 run_all.py를 먼저 실행한 뒤 verify한다.", file=sys.stderr)
    code_now = code_sha256()
    bad_code = [] if code_now == man_now.get("code_sha256") else [f"현재 코드 {code_now[:12]} ≠ 실행 코드 {str(man_now.get('code_sha256'))[:12]} (실행 후 코드 변경)"]
    if args.freeze:
        if args.steps is not None:
            raise ValueError("--freeze와 --steps는 함께 사용할 수 없다")
        if bad_required or bad_files or bad_code:
            print(f"동결 거부: 필수 검사 {bad_required}; 산출물 {bad_files}; 코드 {bad_code}", file=sys.stderr)
            return 2
        # 먼저 복사를 완료한다. 검사 실패나 복사 실패로 기존 기대값을 지우지 않는다.
        with tempfile.TemporaryDirectory(prefix=".freeze-", dir=args.out) as scratch:
            staged = Path(scratch) / "expected"
            staged.mkdir()
            for p in result_files(args.out, steps) + [args.out / "manifest.json", args.out / "checks.json"]:
                shutil.copy2(p, staged / p.name)
            if exp.exists():
                shutil.rmtree(exp)
            staged.rename(exp)
        print(f"동결: 1~{steps}단계 {len(result_names(steps))}개 결과 파일 + manifest/checks → {exp}")
        return 0
    if not exp.exists():
        print("outputs/expected 가 없다. 필수 검사가 통과한 실행에서 --freeze 로 먼저 동결한다.", file=sys.stderr)
        return 2
    man_exp = json.loads((exp / "manifest.json").read_text(encoding="utf-8"))
    checks_exp = json.loads((exp / "checks.json").read_text(encoding="utf-8"))
    exp_steps = declared_steps(man_exp, checks_exp)
    scope = args.steps if args.steps is not None else exp_steps
    scope_ok = scope <= min(steps, exp_steps) and (args.steps is not None or steps == exp_steps)
    exp_bad = check_files(exp, man_exp, result_names(exp_steps) | {"checks.json"})
    exp_bad += check_required(checks_exp, exp_steps)
    hashes = lambda m: {k: v["sha256"] for k, v in m["inputs"]["files"].items()}
    res = [dict(file="inputs.sha256", ok=hashes(man_now) == hashes(man_exp))]
    res.append(dict(file="checks.required", ok=not bad_required, reason=f"미통과 {bad_required}" if bad_required else None))
    res.append(dict(file="outputs.integrity", ok=not bad_files, reason=str(bad_files)))
    res.append(dict(file="code.matches_manifest", ok=not bad_code, reason=str(bad_code)))
    res.append(dict(file="expected.integrity", ok=not exp_bad, reason=str(exp_bad)))
    res.append(dict(file="execution.scope", ok=scope_ok, reason=f"실행 {steps}, 기대값 {exp_steps}, 요청 {scope}"))
    config_keys = {"preprocess"} | ({"no_baselines"} if scope >= 2 else set())
    if scope >= 4:
        config_keys |= {"seed", "lstm_epochs", "lstm_patience", "lstm_guide_epochs", "lstm_guide_patience"}
    config_diff = [k for k in sorted(config_keys) if str(man_now["args"].get(k)) != str(man_exp["args"].get(k))]
    res.append(dict(file="configuration", ok=not config_diff, reason=f"설정 불일치 {config_diff}"))
    expected_files = result_files(exp, scope)
    for q in expected_files:
        p = args.out / q.name
        if not p.is_file() or not q.is_file():
            res.append(dict(file=q.name, ok=False, reason="필수 결과 파일 없음(실행 또는 기대값)"))
        elif p.suffix == ".csv":
            res.append(compare_csv(p, q))
        else:
            res.append(compare_json(p, q))
    bad = [r for r in res if not r["ok"]]
    for r in res:
        tail = f"  ({r.get('reason')})" if not r["ok"] else (f"  max|Δ|={r['max_abs_diff']:.2g}" + (f" 경보 셀 차이 {r['alarm_cells_diff']}" if r.get("alarm_cells_diff") else "") if "max_abs_diff" in r else "")
        print(("OK  " if r["ok"] else "FAIL") + f" {r['file']}{tail}")
    print(f"\n{len(res) - len(bad)}/{len(res)} 통과 (1~{scope}단계 {'전체 비교' if scope == steps == exp_steps else '부분 비교'}, 필수 집계 {len(expected_files)}개). 환경: {man_now['environment'].get('platform')} vs 동결 {man_exp['environment'].get('platform')}; "
          f"코드 {man_now.get('code_sha256', '?')[:12]} vs 동결 {man_exp.get('code_sha256', '?')[:12]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
