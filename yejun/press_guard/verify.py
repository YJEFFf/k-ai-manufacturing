"""v2 outputs/를 동결 기대값(outputs/expected/)과 비교한다. v1 verify와 같은 원칙: 누락·변조·검사 실패는 모두 실패.

    python verify.py --out outputs            # 비교 (실패 시 종료 1)
    python verify.py --out outputs --freeze   # audit 통과·코드/모델 해시 일치 실행만 동결

대상: train.py(metrics·rolling·cases) + analyze.py(통합 비교·오류 조건·첫 경보·불확실성·업무량) 결과 CSV와 manifest·audit.
수치 열 허용오차 1e-9, 정수·문자 열은 정확 비교. 실행 메타데이터(elapsed_s·환경)는 비교하지 않는다.
"""
from pathlib import Path
import argparse
import json
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

from model import D, HERE, BASE
from press.validation import code_sha256

RESULTS = ["metrics.csv", "rolling.csv", "cases_A.csv", "cases_B.csv", "model_comparison_v2.csv", "robustness_v2.csv", "error_conditions_v2.csv",
           "records_first_alarm_v2.csv", "uncertainty_v2.csv", "workload_v2.csv"]
META = ["manifest.json", "audit.json", "analysis_summary.json"]
ARTIFACTS = ["guard_A.json", "guard_B.json"]
TOL = 1e-9


def compare_csv(a: Path, b: Path) -> dict:
    x, y = pd.read_csv(a), pd.read_csv(b)
    if x.shape != y.shape or list(x.columns) != list(y.columns):
        return dict(file=a.name, ok=False, reason=f"shape/columns {x.shape} vs {y.shape}")
    worst = 0.0
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float)
            xn, yn = ~np.isfinite(xv), ~np.isfinite(yv)
            if (xn != yn).any():
                return dict(file=a.name, ok=False, reason=f"NaN/inf pattern differs in {c}")
            d = np.abs(xv - yv); d[xn] = 0
            if pd.api.types.is_integer_dtype(x[c]) or pd.api.types.is_bool_dtype(x[c]):
                if (d > 0).any():
                    return dict(file=a.name, ok=False, reason=f"{c}: 정수/불리언 열 불일치 {int((d > 0).sum())}셀")
            elif (d > TOL).any():
                i = int(np.argmax(d)); return dict(file=a.name, ok=False, reason=f"{c} row {i}: |Δ|={d[i]:.3g} > {TOL:g}")
            worst = max(worst, float(d.max()) if len(d) else 0.0)
        elif not x[c].astype(str).equals(y[c].astype(str)):
            return dict(file=a.name, ok=False, reason=f"text column {c} differs")
    return dict(file=a.name, ok=True, max_abs_diff=worst)


def integrity(out: Path, art_dir: Path) -> list[str]:
    """manifest·audit 대비 현재 코드·모델·산출물 상태. 실패 사유 목록을 돌려준다."""
    bad = []
    try:
        manifest = json.loads((out / "manifest.json").read_text())
    except OSError as exc:
        return [f"manifest.json: {exc}"]
    for name, h in manifest["code_hashes"].items():
        if not (HERE / name).is_file() or D.sha256_file(HERE / name) != h:
            bad.append(f"코드 변경: {name}")
    for name in ARTIFACTS:
        p = art_dir / name
        if not p.is_file():
            bad.append(f"artifacts/{name}: 없음")
        elif manifest["artifacts"].get(name) != D.sha256_file(p):
            bad.append(f"artifacts/{name}: 실행 후 내용 변경")
    for name in ("metrics.csv", "rolling.csv", "cases_A.csv", "cases_B.csv"):
        p = out / name
        if not p.is_file():
            bad.append(f"{name}: 없음")
        elif manifest["outputs"].get(name) != D.sha256_file(p):
            bad.append(f"{name}: 실행 후 내용 변경")
    for name in RESULTS + ["audit.json", "analysis_summary.json"]:
        if not (out / name).is_file():
            bad.append(f"{name}: 없음 (train.py → analyze.py → audit.py 순서로 실행)")
    audit_path = out / "audit.json"
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text())
        if audit.get("all_ok") is not True:
            bad.append("audit.json: all_ok가 아님")
        if audit.get("generated_from_manifest") != manifest.get("input_hashes"):
            bad.append("audit.json: 다른 입력 해시의 실행에서 생성됨")
    summary_path = out / "analysis_summary.json"
    if summary_path.is_file() and json.loads(summary_path.read_text()).get("input_hashes") != manifest.get("input_hashes"):
        bad.append("analysis_summary.json: 다른 입력 해시의 실행에서 생성됨")
    v1_code = code_sha256()
    if manifest.get("code_hashes") and (art_dir / "guard_A.json").is_file():
        state = json.loads((art_dir / "guard_A.json").read_text())["state"]
        if state.get("base_code_sha256") != v1_code:
            bad.append(f"v1 의존 코드가 학습 당시와 다름 ({v1_code[:12]})")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "outputs")
    ap.add_argument("--artifacts", type=Path, default=HERE / "artifacts")
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args(argv)
    exp = args.out / "expected"
    bad = integrity(args.out, args.artifacts)
    if args.freeze:
        if bad:
            print(f"동결 거부: {bad}", file=sys.stderr); return 2
        with tempfile.TemporaryDirectory(prefix=".freeze-", dir=args.out) as scratch:
            staged = Path(scratch) / "expected"; staged.mkdir()
            for name in RESULTS + META:
                shutil.copy2(args.out / name, staged / name)
            if exp.exists():
                shutil.rmtree(exp)
            staged.rename(exp)
        print(f"동결: 결과 {len(RESULTS)}개 + manifest/audit/summary → {exp}"); return 0
    if not exp.exists():
        print("outputs/expected 가 없다. audit 통과 실행에서 --freeze 로 먼저 동결한다.", file=sys.stderr); return 2
    res = [dict(file="outputs.integrity", ok=not bad, reason=str(bad))]
    exp_manifest = json.loads((exp / "manifest.json").read_text())
    now_manifest = json.loads((args.out / "manifest.json").read_text()) if (args.out / "manifest.json").is_file() else {}
    res.append(dict(file="inputs.sha256", ok=now_manifest.get("input_hashes") == exp_manifest.get("input_hashes"), reason="입력 자료 해시가 동결 실행과 다름"))
    exp_bad = [n for n in RESULTS + META if not (exp / n).is_file()]
    res.append(dict(file="expected.integrity", ok=not exp_bad, reason=f"동결 파일 누락 {exp_bad}"))
    for name in RESULTS:
        p, q = args.out / name, exp / name
        res.append(compare_csv(p, q) if p.is_file() and q.is_file() else dict(file=name, ok=False, reason="결과 파일 없음(실행 또는 기대값)"))
    failed = [r for r in res if not r["ok"]]
    for r in res:
        print(("OK  " if r["ok"] else "FAIL") + f" {r['file']}" + (f"  ({r['reason']})" if not r["ok"] else (f"  max|Δ|={r['max_abs_diff']:.2g}" if "max_abs_diff" in r else "")))
    print(f"\n{len(res) - len(failed)}/{len(res)} 통과. 코드 {now_manifest.get('code_hashes', {}).get('model.py', '?')[:12]} vs 동결 {exp_manifest.get('code_hashes', {}).get('model.py', '?')[:12]}; "
          f"환경 {now_manifest.get('environment', {}).get('platform')} vs 동결 {exp_manifest.get('environment', {}).get('platform')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
