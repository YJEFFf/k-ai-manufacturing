"""v2 outputs/를 동결 기대값(outputs/expected/)과 비교한다. v1 verify와 같은 원칙: 누락·변조·검사 실패는 모두 실패.

    python verify.py --out outputs            # 비교 (실패 시 종료 1)
    python verify.py --out outputs --freeze   # audit 통과·코드/모델 해시 일치 실행만 동결

대상: train.py(metrics·rolling·cases) + analyze.py(통합 비교·오류 조건·첫 경보·불확실성·업무량·보강 표) 결과 CSV와 manifest·audit,
그리고 행 단위 예측 파일(predictions_*·test_predictions_*). 행 단위 파일은 커밋하지 않으므로 동결 때 요약(predictions_digest.json)을 남긴다:
SHA-256이 같으면 통과, 다르면 경보·알림·단계·근거·조치 등 정확 비교 열의 해시가 같고, 실수 열마다 개수·합·제곱합·최솟값·최댓값이
상대 1e-7 안에서 같을 때만 통과한다(다른 기기의 부동소수 차이는 허용, 경보가 한 행이라도 바뀌면 실패).
수치 열 허용오차 1e-9, 정수·문자 열은 정확 비교. 실행 메타데이터(elapsed_s·환경)는 비교하지 않는다.
"""
import hashlib
from pathlib import Path
import argparse
import json
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

from model import D, HERE
import runtime
from contracts import (TRAIN_TABLES, ANALYSIS_TABLES, INSIGHT_TABLES, PREDICTIONS, execution_errors, read_json, check_files, audit_errors)

RESULTS = ["metrics.csv", "rolling.csv", "cases_A.csv", "cases_B.csv", "incidents_A.csv", "incidents_B.csv", "model_comparison_v2.csv", "robustness_v2.csv", "sensitivity_v2.csv", "ablation_v2.csv",
           "error_conditions_v2.csv", "error_conditions_segments_v2.csv", "interaction_2x2_v2.csv", "records_first_alarm_v2.csv", "uncertainty_v2.csv", "workload_v2.csv",
           "decision_table_v2.csv"] + list(INSIGHT_TABLES)
META = ["manifest.json", "audit.json", "analysis_summary.json"]
ARTIFACTS = ["guard_A.json", "guard_B.json"]
TOL = 1e-9
EXACT_COLUMNS = ("subset", "label", "row_id", "record_id", "position", "status", "alarm", "notification", "alert_level", "escalation", "reason", "action", "alert_unit")
DIGEST = "predictions_digest.json"


def prediction_digest(path: Path) -> dict:
    """행 단위 예측 파일 요약: 전체 SHA-256, 정확 비교 열의 해시, 실수 열마다 [유한 개수, 합, 제곱합, 최솟값, 최댓값]."""
    x = pd.read_csv(path)
    exact = [c for c in EXACT_COLUMNS if c in x.columns]
    numeric = [c for c in x.columns if c not in exact and pd.api.types.is_numeric_dtype(x[c])]
    summary = {}
    for c in numeric:
        v = x[c].to_numpy(float); f = np.isfinite(v)
        summary[c] = [int(f.sum()), float(v[f].sum()), float((v[f] ** 2).sum()), float(v[f].min()) if f.any() else None, float(v[f].max()) if f.any() else None]
    return dict(sha256=D.sha256_file(path), rows=int(len(x)), columns=list(x.columns),
                exact_sha256=hashlib.sha256(x[exact].astype(str).to_csv(index=False).encode()).hexdigest(),
                numeric_summary=summary, alarm_rows=int(x.alarm.sum()) if "alarm" in x else None)


def _close(a, b):
    if a[0] != b[0]:
        return False
    return all((u is None and w is None) or (u is not None and w is not None and np.isclose(u, w, rtol=1e-7, atol=1e-9)) for u, w in zip(a[1:], b[1:]))


def compare_predictions(out: Path, exp: Path) -> list[dict]:
    try:
        expected = read_json(exp / DIGEST)
    except (OSError, ValueError) as exc:
        return [dict(file=DIGEST, ok=False, reason=f"동결 요약 없음: {exc}")]
    res = []
    for name in PREDICTIONS:
        p, e = out / name, expected.get(name)
        if e is None or not p.is_file():
            res.append(dict(file=name, ok=False, reason="예측 파일 또는 동결 요약 없음")); continue
        now = prediction_digest(p)
        if now["sha256"] == e["sha256"]:
            res.append(dict(file=name, ok=True)); continue
        same = (now["columns"] == e["columns"] and now["rows"] == e["rows"] and now["exact_sha256"] == e["exact_sha256"]
                and all(_close(now["numeric_summary"][c], e["numeric_summary"][c]) for c in e["numeric_summary"]))
        res.append(dict(file=name, ok=same, reason="경보·알림 열 또는 실수 열 요약(상대 1e-7)이 동결 실행과 다름", note="부동소수 차이만 있음" if same else ""))
    return res


def compare_csv(a: Path, b: Path) -> dict:
    x, y = pd.read_csv(a), pd.read_csv(b)
    if x.shape != y.shape or list(x.columns) != list(y.columns):
        return dict(file=a.name, ok=False, reason=f"shape/columns {x.shape} vs {y.shape}")
    worst = 0.0
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float)
            xn, yn = ~np.isfinite(xv), ~np.isfinite(yv)
            if any(not np.array_equal(f(xv),f(yv)) for f in (np.isnan,np.isposinf,np.isneginf)):
                return dict(file=a.name, ok=False, reason=f"NaN/inf pattern differs in {c}")
            d = np.zeros(len(xv)); d[~xn] = np.abs(xv[~xn] - yv[~xn])
            if any(pd.api.types.is_integer_dtype(s) or pd.api.types.is_bool_dtype(s) for s in (x[c],y[c])):
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
    try:
        return execution_errors(read_json(out/"manifest.json"),out,art_dir)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        return [f"실행 기록 오류: {exc}"]


def expected_integrity(exp):
    """커밋된 기대값 자체의 파일 해시와 개별 검사 계약도 확인한다."""
    try:
        manifest=read_json(exp/"manifest.json")
        bad=check_files(exp,manifest.get("outputs"),TRAIN_TABLES)
        bad+=check_files(exp,manifest.get("analysis",{}).get("outputs"),ANALYSIS_TABLES+INSIGHT_TABLES+("analysis_summary.json",))
        bad+=check_files(exp,{"audit.json":manifest.get("audit_sha256")},("audit.json",))
        bad+=audit_errors(read_json(exp/"audit.json"),manifest)
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
        return [f"기대값 기록 오류: {exc}"]
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "outputs")
    ap.add_argument("--artifacts", type=Path, default=HERE / "artifacts")
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args(argv)
    runtime.setup()
    exp = args.out / "expected"
    bad = integrity(args.out, args.artifacts)
    if args.freeze:
        if bad:
            print(f"동결 거부: {bad}", file=sys.stderr); return 2
        with tempfile.TemporaryDirectory(prefix=".freeze-", dir=args.out) as scratch:
            staged = Path(scratch) / "expected"; staged.mkdir()
            for name in RESULTS + META:
                shutil.copy2(args.out / name, staged / name)
            (staged / DIGEST).write_text(json.dumps({n: prediction_digest(args.out / n) for n in PREDICTIONS}, ensure_ascii=False, indent=2), encoding="utf-8")
            if exp.exists():
                shutil.rmtree(exp)
            staged.rename(exp)
        print(f"동결: 결과 {len(RESULTS)}개 + 행 단위 예측 요약 {len(PREDICTIONS)}개 + manifest/audit/summary → {exp}"); return 0
    if not exp.exists():
        print("outputs/expected 가 없다. audit 통과 실행에서 --freeze 로 먼저 동결한다.", file=sys.stderr); return 2
    res = [dict(file="outputs.integrity", ok=not bad, reason=str(bad))]
    try:
        exp_manifest = read_json(exp/"manifest.json")
        now_manifest = read_json(args.out/"manifest.json")
    except (OSError,ValueError) as exc:
        print(f"FAIL 실행/기대값 기록: {exc}"); return 1
    res.append(dict(file="inputs.sha256", ok=now_manifest.get("input_hashes") == exp_manifest.get("input_hashes"), reason="입력 자료 해시가 동결 실행과 다름"))
    exp_bad = expected_integrity(exp)
    res.append(dict(file="expected.integrity", ok=not exp_bad, reason=str(exp_bad)))
    same_config=(now_manifest.get("config")==exp_manifest.get("config") and
                 now_manifest.get("analysis",{}).get("config")==exp_manifest.get("analysis",{}).get("config"))
    res.append(dict(file="configuration",ok=same_config,reason="학습·분석 실행 설정 불일치"))
    try:
        summaries=[read_json(p/"analysis_summary.json") for p in (args.out,exp)]
        for s in summaries: s.pop("elapsed_s",None)
        res.append(dict(file="analysis_summary.json",ok=summaries[0]==summaries[1],reason="분석 요약 불일치"))
    except (OSError,ValueError) as exc:
        res.append(dict(file="analysis_summary.json",ok=False,reason=str(exc)))
    for name in RESULTS:
        p, q = args.out / name, exp / name
        res.append(compare_csv(p, q) if p.is_file() and q.is_file() else dict(file=name, ok=False, reason="결과 파일 없음(실행 또는 기대값)"))
    res.extend(compare_predictions(args.out, exp))
    failed = [r for r in res if not r["ok"]]
    for r in res:
        print(("OK  " if r["ok"] else "FAIL") + f" {r['file']}" + (f"  ({r['reason']})" if not r["ok"] else (f"  max|Δ|={r['max_abs_diff']:.2g}" if "max_abs_diff" in r else "")))
    print(f"\n{len(res) - len(failed)}/{len(res)} 통과. 코드 {now_manifest.get('code_hashes', {}).get('model.py', '?')[:12]} vs 동결 {exp_manifest.get('code_hashes', {}).get('model.py', '?')[:12]}; "
          f"환경 {now_manifest.get('environment', {}).get('platform')} vs 동결 {exp_manifest.get('environment', {}).get('platform')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
