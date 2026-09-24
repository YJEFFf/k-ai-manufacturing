"""outputs/를 동결된 기대값(outputs/expected/)과 비교한다 — PLAN.md §7·§9. 검수 R1·R6 반영.

    python verify.py --out outputs            # 비교 (실패 시 종료 코드 1)
    python verify.py --out outputs --freeze   # 현재 outputs를 기대값으로 동결 (필수 검사가 통과한 실행에서만)

규칙
- 기대값에 있는 파일이 outputs에 없으면 실패한다(부분 실행을 완료로 오인하지 않는다). 검사한 파일 수와 기대 파일 수를 함께 출력한다.
- 수치 열은 행의 `model` 값으로 허용오차를 고른다: 기본 1e-8, isolation_forest·mlp_ae_w5 1e-6, lstm 계열 1e-3. NaN·±inf는 패턴이 정확히 같아야 한다.
- 실행 메타데이터(cached·train_seconds·cache_key·epochs_run·경로)는 결과 수치와 분리해 비교하지 않는다.
- checks.json의 필수 검사(REQUIRED_CHECKS)가 true가 아니면 실패한다.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOL_DEFAULT, TOL_BY_MODEL = 1e-8, {"isolation_forest": 1e-6, "mlp_ae_w5": 1e-6}
TOL_LSTM = 1e-3
SKIP_FILES = {"manifest.json", "checks.json", "numbers.json"}
ROW_LEVEL_PREFIX = ("predictions", "records_main")
META_COLUMNS = {"train_seconds", "cached", "cache_key", "epochs_run", "max_epochs", "patience"}
META_KEYS = {"cached", "train_seconds", "cache_key", "epochs_run", "max_epochs", "patience", "path", "data_dir", "notes"}
REQUIRED_CHECKS = ["input_hash_ok", "input_rows_ok", "segments_equal_vendor_blocks", "conformal_mc_within_4se",
                   "step2_all_ok", "step3_label_bypass_ok", "outputs_free_of_raw_sensor_columns", "required_checks_ok"]


def tol_for(model, fname: str) -> float:
    if "lstm" in fname or (isinstance(model, str) and "lstm" in model):
        return TOL_LSTM
    return TOL_BY_MODEL.get(model, TOL_DEFAULT)


def _strip_meta(obj):
    if isinstance(obj, dict):
        return {k: _strip_meta(v) for k, v in obj.items() if k not in META_KEYS}
    if isinstance(obj, list):
        return [_strip_meta(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 10)
    return obj


def compare_csv(a: Path, b: Path) -> dict:
    x, y = pd.read_csv(a), pd.read_csv(b)
    cols = [c for c in y.columns if c not in META_COLUMNS]
    if x.shape[0] != y.shape[0] or any(c not in x.columns for c in cols):
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
                alarm_diff += int((xv != yv).sum())
        elif not x[c].astype(str).equals(y[c].astype(str)):
            return dict(file=a.name, ok=False, reason=f"text column {c} differs")
    return dict(file=a.name, ok=True, max_abs_diff=worst, alarm_cells_diff=alarm_diff)


def compare_json(a: Path, b: Path) -> dict:
    x, y = _strip_meta(json.loads(a.read_text(encoding="utf-8"))), _strip_meta(json.loads(b.read_text(encoding="utf-8")))
    return dict(file=a.name, ok=x == y, reason=None if x == y else "결과 수치가 다름(메타데이터 제외 비교)")


def check_required(checks: dict) -> list[str]:
    """필수 검사 중 true가 아닌 항목 목록."""
    return [k for k in REQUIRED_CHECKS if k in checks and checks[k] is not True]


def result_files(out: Path) -> list[Path]:
    return sorted(p for p in out.iterdir() if p.is_file() and p.suffix in (".csv", ".json") and p.name not in SKIP_FILES and not p.name.startswith(ROW_LEVEL_PREFIX))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "outputs")
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args(argv)
    exp = args.out / "expected"
    checks = json.loads((args.out / "checks.json").read_text(encoding="utf-8")) if (args.out / "checks.json").exists() else {}
    bad_required = check_required(checks) or (["checks.json 없음"] if not checks else [])
    if args.freeze:
        if bad_required:
            print(f"동결 거부: 필수 검사 미통과 {bad_required}", file=sys.stderr)
            return 2
        exp.mkdir(exist_ok=True)
        for p in exp.glob("*"):
            p.unlink()
        for p in result_files(args.out) + [args.out / "manifest.json", args.out / "checks.json"]:
            shutil.copy2(p, exp / p.name)
        print(f"동결: {len(result_files(args.out))}개 결과 파일 + manifest/checks → {exp}")
        return 0
    if not exp.exists():
        print("outputs/expected 가 없다. 필수 검사가 통과한 실행에서 --freeze 로 먼저 동결한다.", file=sys.stderr)
        return 2
    man_now = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    man_exp = json.loads((exp / "manifest.json").read_text(encoding="utf-8"))
    res = [dict(file="inputs.sha256", ok=all(man_now["inputs"]["files"][k]["sha256"] == v["sha256"] for k, v in man_exp["inputs"]["files"].items()))]
    res.append(dict(file="checks.required", ok=not bad_required, reason=f"미통과 {bad_required}" if bad_required else None))
    expected_files = sorted(p for p in exp.iterdir() if p.is_file() and p.name not in ("manifest.json", "checks.json"))
    for q in expected_files:
        p = args.out / q.name
        if not p.exists():
            res.append(dict(file=q.name, ok=False, reason="outputs에 없음(단계 누락?)"))
        elif p.suffix == ".csv":
            res.append(compare_csv(p, q))
        else:
            res.append(compare_json(p, q))
    bad = [r for r in res if not r["ok"]]
    for r in res:
        tail = f"  ({r.get('reason')})" if not r["ok"] else (f"  max|Δ|={r['max_abs_diff']:.2g}" + (f" 경보 셀 차이 {r['alarm_cells_diff']}" if r.get("alarm_cells_diff") else "") if "max_abs_diff" in r else "")
        print(("OK  " if r["ok"] else "FAIL") + f" {r['file']}{tail}")
    print(f"\n{len(res) - len(bad)}/{len(res)} 통과 (기대 파일 {len(expected_files)}개 전부 검사). 환경: {man_now['environment'].get('platform')} vs 동결 {man_exp['environment'].get('platform')}; "
          f"코드 {man_now.get('code_sha256', '?')[:12]} vs 동결 {man_exp.get('code_sha256', '?')[:12]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
