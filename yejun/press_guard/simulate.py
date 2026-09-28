"""모의 운용: CSV를 시간 순서대로 StreamDetector에 흘려 넣고, 알림(1단계 주의·2단계 점검 요청)을 나는 즉시 출력·기록한다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/simulate.py \
        --csv 기록.csv --split B [--alpha 0.01] [--prior 0.01] [--speed 10] [--chunk 1] [--log alerts.csv]

- --speed 1은 수집 속도(0.1초에 1행), 10은 10배속, 0은 기다리지 않고 처리한다. 행이 들어온 뒤 알림을 내기까지의 계산 시간도 기록한다.
- 설비 제어 명령을 보내지 않는다. 알림 전달(화면·경광등·메신저·CMMS 작업 요청)은 run(on_alert=...) 콜백으로 붙인다.
  구성은 docs/fig_architecture.png, 운영 절차는 OPERATIONS.md에 있다.
- 알림은 사건 단위다: 경보가 이어진 알림 단위(공백 60초 이하)가 한 사건이고, 사건마다 1단계(사건 시작)와 2단계(격상)를 한 번씩 알린다.
- 알림 행·단계는 같은 CSV를 한 번에 분석(GuardModel.predict)한 결과와 같다(test_simulate.py). 수집 오류 행은 "수집 상태 확인"으로
  기록하고 판정하지 않는다. 평균 기록 길이가 8행(8행 파형 창)보다 짧으면 수집 시각 간격 경고를 낸다.
"""
from pathlib import Path
import argparse
import sys
import time

import pandas as pd

from model import StreamDetector, LEVEL_NAMES, D, HERE, ALPHAS, load_bundle, timing_warning
import runtime


def run(frame, model, alpha=.01, prior=None, chunk=1, speed=0.0, on_alert=None, clock=time.perf_counter, sleep=time.sleep):
    """frame을 chunk행씩 흘려 넣는다. 사건 단위 알림(사건 시작 = 1단계, 격상 = 2단계)과 근거 추가(갱신, 알림 아님),
    수집 오류 시작을 사건 표로 돌려준다. notify=1인 행이 실제로 사람에게 보내는 알림이다."""
    stream = StreamDetector(model, alpha, prior)
    events, start, invalid_open = [], clock(), False
    for i in range(0, len(frame), chunk):
        part = frame.iloc[i:i + chunk]
        t_in = clock()
        res = stream.push(part)
        compute_ms = (clock() - t_in) * 1000
        for r in res.itertuples():
            if r.status != "ok":
                kind, notify = (None, 0) if invalid_open else ("수집 오류", 1)
                invalid_open = True
            else:
                invalid_open = False
                kind, notify = (("사건 시작", 1) if r.incident_notification else ("격상", 1) if r.incident_escalation else
                                ("근거 추가", 0) if r.incident_update else (None, 0))
            if kind is None:
                continue
            level = 2 if kind == "격상" else (1 if kind == "사건 시작" else int(r.alert_level))
            ev = dict(row_id=int(r.row_id), timestamp=r.timestamp, incident_id=int(r.incident_id), record_id=int(r.record_id), position=int(r.position),
                      kind=kind, notify=notify, level=level, level_name=LEVEL_NAMES.get(level, "수집 상태 확인"), evidence=r.reason, action=r.action,
                      anomaly_probability=float(r.anomaly_probability), compute_ms=compute_ms)
            events.append(ev)
            if on_alert and notify:
                on_alert(ev)
        if speed > 0:
            wait = start + (i + len(part)) * D.DT / speed - clock()
            if wait > 0:
                sleep(wait)
    return pd.DataFrame(events, columns=["row_id", "timestamp", "incident_id", "record_id", "position", "kind", "notify", "level", "level_name",
                                         "evidence", "action", "anomaly_probability", "compute_ms"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--split", choices=tuple(D.SPLITS), default="A")
    ap.add_argument("--model", type=Path, help="모델 JSON(기본: artifacts/guard_<split>.json, 재보정 모델도 가능)")
    ap.add_argument("--alpha", type=float, choices=ALPHAS, default=.01)
    ap.add_argument("--prior", type=float, default=None, help="이상 행 비율 π 가정(기본 1%%). 기록 확률은 같은 π를 쓰는 근사")
    ap.add_argument("--speed", type=float, default=0.0, help="1=수집 속도, 10=10배속, 0=대기 없음")
    ap.add_argument("--chunk", type=int, default=1)
    ap.add_argument("--log", type=Path, help="알림 기록 CSV")
    args = ap.parse_args(argv)
    runtime.setup()
    model = load_bundle(args.model or HERE / "artifacts" / f"guard_{args.split}.json")
    if model.probability is None:
        print("안내: 라벨 확률 보정기가 없어 확률·우도비 열 4개는 비어 있고 --prior(π)는 쓰이지 않습니다.", file=sys.stderr)
    frame = pd.read_csv(args.csv)

    def show(ev):
        prob = "" if pd.isna(ev["anomaly_probability"]) else f" · 이상 확률 {ev['anomaly_probability']:.1%}"
        print(f"[{ev['timestamp']}] {ev['kind']} · {ev['level_name']} · 구간 {ev['record_id']} · {ev['evidence'] or '-'} · {ev['action']}{prob}", flush=True)

    t = time.perf_counter()
    log = run(frame, model, args.alpha, args.prior, args.chunk, args.speed, on_alert=show)
    if args.log:
        log.to_csv(args.log, index=False)
    kinds = log.kind.value_counts().to_dict() if len(log) else {}
    warn = timing_warning(model.predict(frame, args.alpha))
    if warn:
        print(warn, file=sys.stderr)
    print(f"{len(frame):,}행 · 사건 {kinds.get('사건 시작', 0)} · 격상 {kinds.get('격상', 0)} · 근거 추가 {kinds.get('근거 추가', 0)} · 수집 오류 {kinds.get('수집 오류', 0)} · "
          f"계산 p95 {log.compute_ms.quantile(.95) if len(log) else float('nan'):.1f} ms · 경과 {time.perf_counter() - t:.1f}초", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
