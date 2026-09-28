"""v2 outputs/를 동결 기대값(outputs/expected/)과 비교한다. v1 verify와 같은 원칙: 누락·변조·검사 실패는 모두 실패.

    python verify.py --out outputs            # 비교 (실패 시 종료 1)
    python verify.py --out outputs --freeze   # audit 통과·코드/모델 해시 일치 실행만 동결

대상: train.py(metrics·rolling·cases) + analyze.py(통합 비교·오류 조건·첫 경보·불확실성·업무량·보강 표) 결과 CSV와 manifest·audit,
그리고 행 단위 예측 파일(predictions_*·test_predictions_*). 행 단위 파일은 커밋하지 않으므로 동결 때 요약(predictions_digest.json)을 남긴다:
SHA-256이 같으면 통과한다. 다르면(다른 기기) 경보·알림·단계·사건·근거·조치·상태 등 실수가 아닌 모든 열이 정확히 같고,
NaN·±inf 위치가 같고, 실수 열은 행마다(동결 때 float32로 저장한 값과) |차이| ≤ 1e-9 + 1e-6·|값|이고 열 요약(합·제곱합·최솟값·최댓값)도
상대 1e-6 안이어야 통과한다. 경보가 한 행이라도 바뀌거나, 행 사이 값을 맞바꾸거나, 작은 값 열을 몇 배로 바꾸면 실패한다.
예외는 정상 기준 분포의 순위(ECDF)로 바꾼 점수 열(score·g_*)의 ECDF 구간(g ≤ 1.35, 꼬리 확률 약 5% 이상)이다. 상수만 다른 창처럼
수학적으로 같은 점수들의 순위가 기기마다 한 칸씩 뒤바뀌므로(리눅스 x86-64 실측 최대 2.3e-4, 경보 불변) 행마다 1e-3, 열 요약은 상대 1e-4까지
허용한다. 꼬리 구간은 연속식이라 순위가 흔들리지 않으므로 엄격 비교를 그대로 쓴다.
결과 CSV는 |차이| ≤ 1e-9 + 1e-7·|값|(기기 간 실측 최대 상대 2.5e-9의 약 40배), 정수·문자 열은 정확 비교. 순위 통계 열만 COLUMN_TOLERANCE에 이유와 함께 따로 둔다.
모델 파일은 동결 사본(expected/guard_*.json·probability_*.json)과 SHA-256이 같거나, 다른 기기면 모든 원소가 수치로 같아야 한다(equivalence.py).
실행 메타데이터(elapsed_s·환경)는 비교하지 않는다.
"""
import base64
import hashlib
import zlib
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
from contracts import ARTIFACTS as FROZEN_ARTIFACTS   # 모델 2개 + 확률 보정기 2개(동결 사본·동등성 대상)
from equivalence import artifact_equivalent

RESULTS = ["metrics.csv", "rolling.csv", "cases_A.csv", "cases_B.csv", "incidents_A.csv", "incidents_B.csv", "model_comparison_v2.csv", "robustness_v2.csv", "sensitivity_v2.csv", "ablation_v2.csv",
           "error_conditions_v2.csv", "error_conditions_segments_v2.csv", "interaction_2x2_v2.csv", "records_first_alarm_v2.csv", "uncertainty_v2.csv", "workload_v2.csv",
           "decision_table_v2.csv"] + list(INSIGHT_TABLES)
META = ["manifest.json", "audit.json", "analysis_summary.json"]
ARTIFACTS = ["guard_A.json", "guard_B.json"]
TOL = 1e-9
RTOL = 1e-7
# 순위 통계 열: 기록 최대 점수 가운데 수학적으로 같은 값의 순위가 기기마다 뒤바뀌면 스피어만 상관이 조금 달라진다(리눅스 x86-64 실측 3e-4).
COLUMN_TOLERANCE = {("near_miss_corr_v2.csv", "spearman"): 1e-3}
ROW_RTOL, ROW_ATOL = 1e-6, 1e-9                    # 행별·열 요약 비교(다른 기기)
ECDF_COLUMNS = ("score", "g_magnitude", "g_waveform", "g_dynamics")   # 정상 기준 분포 순위로 바꾼 점수
ECDF_G_MAX, ECDF_ROW_ATOL, ECDF_SUMMARY_RTOL = 1.35, 1e-3, 1e-4       # ECDF 구간(꼬리 확률 약 5% 이상)의 순위 한 칸 허용
EXACT_COLUMNS = ("subset", "label", "row_id", "record_id", "position", "timestamp", "status", "alarm", "notification", "alert_level", "escalation", "reason", "action", "alert_unit",
                 "incident_id", "incident_notification", "incident_escalation", "incident_update", "magnitude_sensor", "operating_state")
DIGEST = "predictions_digest.json"


def _pack(v):
    """실수 열의 행별 값(float32, NaN·±inf 그대로)을 압축해 문자열로 저장한다."""
    return base64.b64encode(zlib.compress(np.asarray(v, dtype="<f4").tobytes(), 9)).decode("ascii")


def _unpack(text):
    return np.frombuffer(zlib.decompress(base64.b64decode(text)), dtype="<f4").astype(float)


def _row_bound(column, frozen):
    bound = ROW_ATOL + ROW_RTOL * np.abs(frozen)
    if column in ECDF_COLUMNS:
        bound = np.where(frozen <= ECDF_G_MAX, np.maximum(bound, ECDF_ROW_ATOL), bound)
    return bound


def prediction_digest(path: Path) -> dict:
    """전체·정확 비교 열·NaN/±inf 위치 해시, 실수 열별 [유한 개수, 합, 제곱합, 최솟값, 최댓값]과 행별 지문(0.001 격자)."""
    x = pd.read_csv(path)
    exact = [c for c in x.columns if c in EXACT_COLUMNS or not pd.api.types.is_float_dtype(x[c])]
    numeric = [c for c in x.columns if c not in exact]
    summary, nonfinite, rows = {}, {}, {}
    for c in numeric:
        v = x[c].to_numpy(float); f = np.isfinite(v)
        kinds = np.zeros(len(v), dtype=np.uint8)
        kinds[np.isnan(v)], kinds[np.isposinf(v)], kinds[np.isneginf(v)] = 1, 2, 3
        nonfinite[c] = hashlib.sha256(kinds.tobytes()).hexdigest()
        summary[c] = [int(f.sum()), float(v[f].sum()), float((v[f] ** 2).sum()), float(v[f].min()) if f.any() else None, float(v[f].max()) if f.any() else None]
        rows[c] = _pack(v)
    return dict(sha256=D.sha256_file(path), rows=int(len(x)), columns=list(x.columns), exact_columns=exact,
                exact_sha256=hashlib.sha256(x[exact].astype(str).to_csv(index=False).encode()).hexdigest(),
                nonfinite_sha256=nonfinite, numeric_summary=summary, row_values=rows, alarm_rows=int(x.alarm.sum()) if "alarm" in x else None)


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
        reason = ""
        if not (now["columns"] == e["columns"] and now["rows"] == e["rows"] and now["exact_columns"] == e.get("exact_columns")):
            reason = "열·행 구성이 동결 실행과 다름"
        elif now["exact_sha256"] != e["exact_sha256"]:
            reason = "경보·알림·단계·사건·상태 등 정확 비교 열이 동결 실행과 다름"
        elif now["nonfinite_sha256"] != e.get("nonfinite_sha256"):
            reason = "실수 열의 NaN·±inf 위치가 동결 실행과 다름"
        elif "row_values" not in e:
            reason = "동결 요약에 행별 값이 없다(이전 형식). 동결 기기에서 다시 동결한다"
        else:
            x = pd.read_csv(p)
            for c, text in e["row_values"].items():
                frozen, cur = _unpack(text), x[c].to_numpy(float)
                ok = np.isfinite(frozen) & np.isfinite(cur)
                d, bound = np.abs(cur[ok] - frozen[ok]), _row_bound(c, frozen[ok])
                if len(d) and (d > bound).any():
                    i = int(np.flatnonzero(ok)[np.argmax(d - bound)])
                    reason = f"{c} {i}행이 동결 실행과 {abs(cur[i] - frozen[i]):.3g} 다름(허용 {_row_bound(c, np.array([frozen[i]]))[0]:.3g})"
                    break
                rtol = ECDF_SUMMARY_RTOL if c in ECDF_COLUMNS else ROW_RTOL
                a, b = now["numeric_summary"][c], e["numeric_summary"][c]
                if a[0] != b[0] or not all((u is None and w is None) or (u is not None and w is not None and abs(u - w) <= ROW_ATOL + rtol * max(abs(u), abs(w)))
                                           for u, w in zip(a[1:], b[1:])):
                    reason = f"{c} 열 요약(개수·합·제곱합·최솟값·최댓값)이 동결 실행과 다름(상대 {rtol:g})"
                    break
        res.append(dict(file=name, ok=not reason, reason=reason, note="" if reason else "기기 간 부동소수 차이만 있음(행별·열 요약 허용오차 안)"))
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
            bound = np.full(len(xv), COLUMN_TOLERANCE.get((a.name, c), TOL)); bound[~yn] += RTOL * np.abs(yv[~yn])
            if any(pd.api.types.is_integer_dtype(s) or pd.api.types.is_bool_dtype(s) for s in (x[c],y[c])):
                if (d > 0).any():
                    return dict(file=a.name, ok=False, reason=f"{c}: 정수/불리언 열 불일치 {int((d > 0).sum())}셀")
            elif (d > bound).any():
                i = int(np.argmax(d - bound)); return dict(file=a.name, ok=False, reason=f"{c} row {i}: |Δ|={d[i]:.3g} > {bound[i]:.3g}")
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
        bad+=check_files(exp,{DIGEST:manifest.get("prediction_digest_sha256")},(DIGEST,))
        bad+=check_files(exp,manifest.get("frozen_artifacts"),FROZEN_ARTIFACTS)
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
            for name in FROZEN_ARTIFACTS:               # 다른 기기에서 다시 학습한 모델을 원소 단위로 대조할 동결 사본
                shutil.copy2(args.artifacts / name, staged / name)
            (staged / DIGEST).write_text(json.dumps({n: prediction_digest(args.out / n) for n in PREDICTIONS}, ensure_ascii=False, indent=2), encoding="utf-8")
            frozen_manifest = read_json(staged / "manifest.json")
            frozen_manifest["prediction_digest_sha256"] = D.sha256_file(staged / DIGEST)
            frozen_manifest["frozen_artifacts"] = {name: D.sha256_file(staged / name) for name in FROZEN_ARTIFACTS}
            (staged / "manifest.json").write_text(json.dumps(frozen_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
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
    for name in FROZEN_ARTIFACTS:
        ok, why = artifact_equivalent(args.artifacts / name, exp)
        res.append(dict(file=f"artifacts/{name}", ok=ok, reason=why, note="" if why == "SHA-256 같음" else why))
    res.extend(compare_predictions(args.out, exp))
    failed = [r for r in res if not r["ok"]]
    for r in res:
        print(("OK  " if r["ok"] else "FAIL") + f" {r['file']}" + (f"  ({r['reason']})" if not r["ok"] else (f"  max|Δ|={r['max_abs_diff']:.2g}" if "max_abs_diff" in r else "")
                                                                   + (f"  [{r['note']}]" if r.get("note") else "")))
    print(f"\n{len(res) - len(failed)}/{len(res)} 통과. 코드 {now_manifest.get('code_hashes', {}).get('model.py', '?')[:12]} vs 동결 {exp_manifest.get('code_hashes', {}).get('model.py', '?')[:12]}; "
          f"환경 {now_manifest.get('environment', {}).get('platform')} vs 동결 {exp_manifest.get('environment', {}).get('platform')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
