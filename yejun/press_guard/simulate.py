"""모의 운용: CSV를 시간 순서대로 StreamDetector에 흘려 넣고, 알림(1단계 주의·2단계 점검 요청)을 나는 즉시 출력·기록한다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/simulate.py \
        --csv 기록.csv --split B [--alpha 0.01] [--prior 0.01] [--speed 10] [--chunk 1] [--log alerts.csv]

- --speed 1은 수집 속도(0.1초에 1행), 10은 10배속, 0은 기다리지 않고 처리한다. 행이 들어온 뒤 알림을 내기까지의 계산 시간도 기록한다.
- 설비 제어 명령을 보내지 않는다. 알림 전달(화면·경광등·메신저·CMMS 작업 요청)은 run(on_alert=...) 콜백으로 붙인다.
  구성은 outputs/fig_architecture_v2.png, 운영 절차는 OPERATIONS.md에 있다.
- 알림 행·단계는 같은 CSV를 한 번에 분석(GuardModel.predict)한 결과와 같다(test_simulate.py). 수집 오류 행은 "수집 상태 확인"으로
  기록하고 판정하지 않는다.
"""
from pathlib import Path
import argparse
import sys
import time

import pandas as pd

from model import StreamDetector, LEVEL_NAMES, D, HERE, ALPHAS, load_bundle
import runtime


def run(frame, model, alpha=.01, prior=None, chunk=1, speed=0.0, on_alert=None, clock=time.perf_counter, sleep=time.sleep):
    """frame을 chunk행씩 흘려 넣는다. 알림(첫 알림·격상)과 수집 오류 시작을 사건 표로 돌려준다."""
    stream = StreamDetector(model, alpha, prior)
    events, start, invalid_open = [], clock(), False
    for i in range(0, len(frame), chunk):
        part = frame.iloc[i:i + chunk]
        t_in = clock()
        res = stream.push(part)
        compute_ms = (clock() - t_in) * 1000
        for r in res.itertuples():
            kind = None
            if r.status != "ok":
                kind = None if invalid_open else "수집 오류"
                invalid_open = True
            else:
                invalid_open = False
                kind = "첫 알림" if r.notification else ("격상" if r.escalation else None)
            if kind is None:
                continue
            ev = dict(row_id=int(r.row_id), timestamp=r.timestamp, record_id=int(r.record_id), position=int(r.position), kind=kind,
                      level=int(r.alert_level), level_name=LEVEL_NAMES.get(int(r.alert_level), "수집 상태 확인"),
                      evidence=r.reason, action=r.action, anomaly_probability=float(r.anomaly_probability), compute_ms=compute_ms)
            events.append(ev)
            if on_alert:
                on_alert(ev)
        if speed > 0:
            wait = start + (i + len(part)) * D.DT / speed - clock()
            if wait > 0:
                sleep(wait)
    return pd.DataFrame(events, columns=["row_id", "timestamp", "record_id", "position", "kind", "level", "level_name", "evidence",
                                         "action", "anomaly_probability", "compute_ms"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--split", choices=tuple(D.SPLITS), default="A")
    ap.add_argument("--model", type=Path, help="모델 JSON(기본: artifacts/guard_<split>.json, 재보정 모델도 가능)")
    ap.add_argument("--alpha", type=float, choices=ALPHAS, default=.01)
    ap.add_argument("--prior", type=float, default=None, help="이상 확률의 사전 비율(기본 1%)")
    ap.add_argument("--speed", type=float, default=0.0, help="1=수집 속도, 10=10배속, 0=대기 없음")
    ap.add_argument("--chunk", type=int, default=1)
    ap.add_argument("--log", type=Path, help="알림 기록 CSV")
    args = ap.parse_args(argv)
    runtime.setup()
    model = load_bundle(args.model or HERE / "artifacts" / f"guard_{args.split}.json")
    frame = pd.read_csv(args.csv)

    def show(ev):
        prob = "" if pd.isna(ev["anomaly_probability"]) else f" · 이상 확률 {ev['anomaly_probability']:.1%}"
        print(f"[{ev['timestamp']}] {ev['kind']} · {ev['level_name']} · 구간 {ev['record_id']} · {ev['evidence'] or '-'} · {ev['action']}{prob}", flush=True)

    t = time.perf_counter()
    log = run(frame, model, args.alpha, args.prior, args.chunk, args.speed, on_alert=show)
    if args.log:
        log.to_csv(args.log, index=False)
    kinds = log.kind.value_counts().to_dict() if len(log) else {}
    print(f"{len(frame):,}행 · 첫 알림 {kinds.get('첫 알림', 0)} · 격상 {kinds.get('격상', 0)} · 수집 오류 {kinds.get('수집 오류', 0)} · "
          f"계산 p95 {log.compute_ms.quantile(.95) if len(log) else float('nan'):.1f} ms · 경과 {time.perf_counter() - t:.1f}초", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
