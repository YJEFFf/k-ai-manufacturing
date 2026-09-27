"""v2 실행 검증 기록(outputs/audit.json). 저장 모델·코드 해시, 청크 불변, 독립 집계, 알림 계약을 실제 자료로 확인한다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/audit.py

train.py 실행 뒤에 돌린다. 결과는 웹 콘솔의 '실행 검증' 목록과 검수 기록에 쓴다. 성능 주장이 아니라 실행 경로의 확인이다.
"""
from pathlib import Path
import argparse
import json
import time

import numpy as np
import pandas as pd

from model import GuardModel, StreamDetector, cases, D, HERE, ALPHAS
import runtime
from press.validation import code_sha256
from contracts import CODE_FILES, execution_errors, run_fingerprint


def check(name, ok, detail):
    print(f"{'OK ' if ok else 'FAIL'} {name}: {detail}", flush=True)
    return dict(name=name, ok=bool(ok), detail=str(detail))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=HERE / "outputs")
    ap.add_argument("--artifacts", type=Path, default=HERE / "artifacts")
    args = ap.parse_args()
    runtime.setup()
    start = time.monotonic()
    manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
    checks = []
    now = {name: D.sha256_file(HERE / name) for name in CODE_FILES}
    errors=execution_errors(manifest,args.out,args.artifacts,require_audit=False)
    checks.append(check("실행 코드·선행 산출물이 manifest와 같음", now == manifest.get("code_hashes") and not errors,
                        "필수 코드·학습·분석·원본 해시 일치" if not errors else str(errors)))
    art = {p.name: D.sha256_file(p) for p in sorted(args.artifacts.glob("*.json")) if p.name.startswith(("guard_", "probability_"))}
    checks.append(check("저장 모델이 manifest와 같음", art == manifest["artifacts"], f"{sorted(art)} 해시 일치" if art == manifest["artifacts"] else "해시 불일치"))
    models = {sid: GuardModel.load(args.artifacts / f"guard_{sid}.json") for sid in D.SPLITS}
    base_ok = all(m.state["base_code_sha256"] == code_sha256() for m in models.values())
    checks.append(check("v1 의존 코드가 학습 당시와 같음", base_ok, code_sha256()[:12]))
    normal, abnormal, inputs = D.load(args.root) if args.root else D.load()
    hashes = {k: v["sha256"] for k, v in inputs["files"].items()}
    checks.append(check("입력 자료 해시가 학습 당시와 같음", all(m.state["input_hashes"] == hashes for m in models.values()), "정상·이상 CSV SHA-256 일치"))
    metrics = pd.read_csv(args.out / "metrics.csv")
    for sid, model in models.items():
        split = D.split_normal(normal, D.segments(normal), sid)
        stream_frame = pd.concat([split["test"], abnormal], ignore_index=True)
        whole = model.predict(stream_frame)
        worst = 0.0
        for chunk in (1, 7, 128):
            det = StreamDetector(model)
            parts = pd.concat([det.push(stream_frame.iloc[i:i + chunk]) for i in range(0, len(stream_frame), chunk)], ignore_index=True)
            same_alarm = np.array_equal(parts.alarm.to_numpy(), whole.alarm.to_numpy()) and np.array_equal(parts.notification.to_numpy(), whole.notification.to_numpy())
            diff = float(np.nanmax(np.abs(parts.score.to_numpy() - whole.score.to_numpy())))
            worst = max(worst, diff)
            if not same_alarm:
                worst = np.inf
        checks.append(check(f"{sid} 입력 묶음 1·7·128행과 전체 추론 동일", np.isfinite(worst) and worst <= 1e-11, f"{len(stream_frame)}행 · 점수 최대 차이 {worst:.1e} · 경보·알림 동일"))
        pn, pa = model.predict(split["test"]), model.predict(abnormal)
        tp, fp = int(pa.alarm.sum()), int(pn.alarm.sum()); fn = len(pa) - tp
        row = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(.01)].iloc[0]
        agg_ok = (tp, fp, fn) == (int(row.tp), int(row.fp), int(row.fn)) and abs(2 * tp / (2 * tp + fp + fn) - row.f1) < 1e-12
        checks.append(check(f"{sid} 독립 집계가 metrics.csv와 같음", agg_ok, f"이상 경보 {tp}/600 · 정상 경보 {fp}/{len(pn)} · F1 {2 * tp / (2 * tp + fp + fn):.6f}"))
        direct = np.array([(1 + np.sum(model.cal >= s)) / (len(model.cal) + 1) if np.isfinite(s) else np.nan for s in pa.score])
        p_ok = np.allclose(np.nan_to_num(direct, nan=-1), np.nan_to_num(pa.p_value.to_numpy(), nan=-1))
        checks.append(check(f"{sid} p값이 보정 순위 규칙과 같음", p_ok, f"보정 구간 {len(model.cal)}개 · α {ALPHAS}"))
        # 정확성: 구간당 알림 수 = 그 구간에 경보가 있으면 1, 없으면 0 (정상·이상 모두). 점검 건 수 = 경보가 있는 구간 수
        per = pd.concat([pn.assign(record_id=pn.record_id + 10**6), pa]).groupby("record_id").agg(n=("notification", "sum"), any=("alarm", "max"))
        notif_ok = per.n.eq(per["any"]).all() and len(cases(pa)) == int(pa.groupby("record_id").alarm.max().sum())
        checks.append(check(f"{sid} 구간당 알림은 경보 유무와 일치(정확성)", notif_ok, f"정상 {pn.record_id.nunique()}·이상 {pa.record_id.nunique()}구간 · 알림 {int(pn.notification.sum())}+{int(pa.notification.sum())}회"))
        # 성능 회귀: 이상 21구간 모두 탐지. 정확성 검사와 분리해 이름 붙인다(PLAN §2 R8)
        detected = int(pa.groupby("record_id").alarm.max().sum())
        checks.append(check(f"{sid} 이상 21구간 모두 탐지(성능 회귀)", detected == pa.record_id.nunique() == 21, f"{detected}/{pa.record_id.nunique()}구간"))
        shifted = D.inputs_only(abnormal)
        shifted[D.TIME] = (pd.to_datetime(shifted[D.TIME]) + pd.Timedelta(days=400)).astype(str)
        shifted["Equipment_state"] = 0
        inv = model.predict(shifted)
        checks.append(check(f"{sid} 날짜 이동·라벨 변경에 불변", np.array_equal(inv.alarm.to_numpy(), pa.alarm.to_numpy()) and np.allclose(inv.score.to_numpy(), pa.score.to_numpy(), equal_nan=True), "경보·점수 동일"))
    result = dict(version=manifest["version"], generated_from_manifest=manifest.get("input_hashes"), environment=runtime.environment(D.environment()),
                  run_fingerprint=run_fingerprint(manifest), checks=checks, all_ok=all(c["ok"] for c in checks), elapsed_s=round(time.monotonic() - start, 1))
    D.dump_json(result, args.out / "audit.json")
    manifest["audit_sha256"]=D.sha256_file(args.out/"audit.json")
    D.dump_json(manifest,args.out/"manifest.json")
    print(f"{sum(c['ok'] for c in checks)}/{len(checks)} 통과 → {args.out / 'audit.json'}")
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
