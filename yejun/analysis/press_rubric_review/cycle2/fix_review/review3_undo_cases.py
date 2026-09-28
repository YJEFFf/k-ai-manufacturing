"""검토 3: 수정 커밋(110afa2)의 TimeOrder 튐 예외(jumped·ORDER_SPIKE_SKIPPED)와 IncidentTracker.undo 반례.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_undo_cases.py
사본만 읽는다. 모델은 사본의 artifacts/guard_B.json(+probability_B.json)이다.

U0  대회 원자료(정상·이상)에서 시각 순서 사건이 0인지(보통 자료에서 튐 예외가 잘못 발동하지 않는지)
U1  진행 중 사건에서 앞으로 튄 한 행(이웃 두 행 맞바뀜, +5초 튐)이 격상을 낸 뒤 되돌려지면 같은 사건에 격상이 두 번 나가는가
U2  튄 행과 원래 시간축 사이에 수집 오류 행(시각 결측·보류 행)이 끼면 되돌리기가 빠져 사건이 쪼개지는가(R1-04 재발)
U3  기록 첫 행 바로 뒤의 과거 한 행(기록 사이 공백 안의 시각)이 보류되지 않고 '미래 튐'으로 처리되는가
각 사례는 일괄 predict와 StreamDetector(청크 1·7·128)가 같은지도 본다.
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))

import numpy as np
import pandas as pd

from model import D, layout, load_bundle, StreamDetector, cases, incidents, timing_warning, time_order_events
import simulate

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
REC = layout(TEST)[1]
CLEAN = TEST[REC == 0].reset_index(drop=True)          # 경보 없는 정상 기록(50행)
T0 = pd.Timestamp("2022-07-17 10:00:00")
COLS = ["time_order_event", "status", "record_id", "alarm", "reason", "incident_id", "incident_notification", "incident_escalation", "incident_update"]


def fmt(t):
    return pd.Timestamp(t).strftime("%Y-%m-%d %H:%M:%S.%f")


def stamp(frame, times):
    out = frame.copy().reset_index(drop=True)
    out[D.TIME] = [fmt(t) if t is not None else "" for t in times]
    return out


def stream_same(frame, pred):
    res = []
    for chunk in (1, 7, 128):
        det = StreamDetector(MODEL)
        parts = [det.push(frame.iloc[i:i + chunk]) for i in range(0, len(frame), chunk)]
        try:
            pd.testing.assert_frame_equal(pd.concat(parts, ignore_index=True), pred, rtol=1e-11, atol=1e-11)
            res.append(True)
        except AssertionError:
            res.append(False)
    return res


def per_incident(pred):
    g = pred[pred.incident_id.gt(0)].groupby("incident_id")
    return pd.DataFrame(dict(rows=g.size(), notifications=g.incident_notification.sum(), escalations=g.incident_escalation.sum(),
                             first_row=g.apply(lambda x: int(x.index.min()), include_groups=False)))


def show(title, frame, pred, rows=None):
    inc = per_incident(pred)
    print(f"\n### {title}")
    print(f"  시각 순서 사건(보류·새 기준·튐) {time_order_events(pred)} | 사건 {len(inc)}개 | 사건 시작 알림 {int(pred.incident_notification.sum())} "
          f"| 격상 {int(pred.incident_escalation.sum())} | 사건별(행·시작·격상): {inc[['rows', 'notifications', 'escalations']].to_dict('index')}")
    dup = inc[(inc.notifications > 1) | (inc.escalations > 1)]
    print(f"  한 사건에 시작·격상 알림이 두 번 이상인 사건: {dup.index.tolist()}")
    if rows is not None:
        view = pred.loc[rows, COLS].copy(); view.insert(0, "timestamp", frame[D.TIME].iloc[rows].str[11:].to_numpy())
        print(view.to_string())
    print("  경고:", timing_warning(pred)[:160] or "(없음)")
    print("  일괄=스트림(청크 1·7·128):", stream_same(frame, pred))
    return inc


def magnitude_rows(k):
    """1행 기록(크기 성분만)으로도 α 1%에서 경보가 나는 이상 행 k개."""
    probe = MODEL.predict(stamp(ABN, [T0 + pd.Timedelta(seconds=10 * i) for i in range(len(ABN))]))   # 모든 행을 1행 기록으로
    idx = np.flatnonzero(probe.alarm.eq(1).to_numpy())
    return ABN.iloc[idx[:k]].reset_index(drop=True)


def u0():
    print("## U0 대회 원자료의 시각 순서 사건")
    for name, frame in (("정상 전체", D.inputs_only(normal)), ("이상 전체", ABN)):
        p = MODEL.predict(frame)
        print(f"  {name}: 행 {len(p)}, time_order_event 분포 {p.time_order_event.value_counts().to_dict()}, 보류 {int(p.status.eq('bad_time_order').sum())}")


def u1():
    print("\n## U1 진행 중 사건의 앞으로 튄 한 행 → 되돌린 뒤 같은 사건에 격상 두 번")
    mag = magnitude_rows(4)
    base_times = [T0 + pd.Timedelta(seconds=.1 * i) for i in range(len(CLEAN))]
    s = T0 + pd.Timedelta(seconds=7.0)
    # (a) 이웃 두 행 맞바뀜: 7.0(첫 경보) → 7.2(먼저 도착) → 7.1 → 7.3
    frame = pd.concat([stamp(CLEAN, base_times),
                       stamp(mag, [s, s + pd.Timedelta(seconds=.2), s + pd.Timedelta(seconds=.1), s + pd.Timedelta(seconds=.3)])], ignore_index=True)
    pred = MODEL.predict(frame)
    show("U1a 이웃 두 행 맞바뀜(7.2가 7.1보다 먼저 도착)", frame, pred, rows=list(range(len(CLEAN), len(frame))))
    ordered = pd.concat([stamp(CLEAN, base_times), stamp(mag, [s + pd.Timedelta(seconds=.1 * i) for i in range(4)])], ignore_index=True)
    show("U1a 대조: 같은 네 행을 제 순서로", ordered, MODEL.predict(ordered))
    q = incidents(cases(pred), pred)
    print("  사건 대기열(incidents):", q[["incident_id", "cases", "level", "escalation_row"]].to_dict("records"),
          "| 격상 행(예측):", pred.index[pred.incident_escalation.eq(1)].tolist())
    log = simulate.run(frame, MODEL, chunk=1)
    print("  모의 운용(simulate.run, 청크 1)의 사람에게 가는 알림:", log[log.notify.eq(1)][["row_id", "incident_id", "kind"]].to_dict("records"))
    # (b) +5초 튐 한 행
    frame = pd.concat([stamp(CLEAN, base_times),
                       stamp(mag, [s, s + pd.Timedelta(seconds=5), s + pd.Timedelta(seconds=.1), s + pd.Timedelta(seconds=.2)])], ignore_index=True)
    show("U1b 첫 경보 다음 행이 +5초로 튐(원래 시간축은 7.1·7.2로 이어짐)", frame, MODEL.predict(frame), rows=list(range(len(CLEAN), len(frame))))
    # (c) 수집 시각 흔들림: 7.1초 표본의 시각이 150 ms 늦게 찍힘(7.25), 도착 순서는 그대로
    frame = pd.concat([stamp(CLEAN, base_times),
                       stamp(mag, [s, s + pd.Timedelta(seconds=.25), s + pd.Timedelta(seconds=.2), s + pd.Timedelta(seconds=.3)])], ignore_index=True)
    show("U1c 둘째 표본의 시각만 150 ms 늦음(7.0 → 7.25 → 7.2 → 7.3)", frame, MODEL.predict(frame), rows=list(range(len(CLEAN), len(frame))))


def spike_frame(extra):
    """test_alarmed_spike_row_does_not_split_incident와 같은 +1시간 경보 튐 행(이상 자료 행 300 앞). extra는 튄 행 바로 뒤에 끼울 행."""
    base = MODEL.predict(ABN)
    src = int(base.index[base.alarm.eq(1) & base.reason.str.contains("magnitude")][0])
    glitch = ABN.iloc[[src]].copy()
    glitch[D.TIME] = (pd.to_datetime(glitch[D.TIME]) + pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    where = 300
    parts = [ABN.iloc[:where], glitch] + ([extra] if extra is not None else []) + [ABN.iloc[where:]]
    return pd.concat(parts, ignore_index=True), where


def u2():
    print("\n## U2 튄 행과 원래 시간축 사이의 수집 오류 행")
    frame, where = spike_frame(None)
    show("U2 대조: 경보 난 +1시간 튄 행만(저장소 시험과 같은 입력)", frame, MODEL.predict(frame), rows=list(range(where - 1, where + 3)))
    nat = ABN.iloc[[where]].copy(); nat[D.TIME] = ""
    frame, where = spike_frame(nat)
    show("U2a 튄 행 바로 뒤에 시각 결측 한 행", frame, MODEL.predict(frame), rows=list(range(where - 1, where + 4)))
    held = ABN.iloc[[where]].copy(); held[D.TIME] = (pd.to_datetime(held[D.TIME]) - pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    frame, where = spike_frame(held)
    show("U2b 튄 행 바로 뒤에 과거(−1시간) 한 행", frame, MODEL.predict(frame), rows=list(range(where - 1, where + 4)))


def u3():
    print("\n## U3 기록 첫 행 바로 뒤의 과거 한 행(기록 사이 공백 안의 시각)")
    mag = magnitude_rows(6)
    base_times = [T0 + pd.Timedelta(seconds=.1 * i) for i in range(len(CLEAN))]       # 정상 기록 0.0~4.9초
    s = T0 + pd.Timedelta(seconds=7.0)                                                    # 다음 기록 7.0초부터(공백 2.1초)
    glitch = CLEAN.iloc[[10]]
    good = pd.concat([stamp(CLEAN, base_times), stamp(mag, [s + pd.Timedelta(seconds=.1 * i) for i in range(len(mag))])], ignore_index=True)
    show("U3 대조: 과거 행 없음", good, MODEL.predict(good))
    frame = pd.concat([stamp(CLEAN, base_times), stamp(mag.iloc[:1], [s]), stamp(glitch, [T0 + pd.Timedelta(seconds=6.0)]),
                       stamp(mag.iloc[1:], [s + pd.Timedelta(seconds=.1 * i) for i in range(1, len(mag))])], ignore_index=True)
    show("U3a 7.0초 행 뒤에 6.0초 행 한 개(1초 과거)", frame, MODEL.predict(frame), rows=list(range(len(CLEAN) - 1, len(CLEAN) + 4)))
    far = pd.concat([stamp(CLEAN, base_times), stamp(mag.iloc[:1], [s]), stamp(glitch, [T0 + pd.Timedelta(seconds=3.0)]),
                     stamp(mag.iloc[1:], [s + pd.Timedelta(seconds=.1 * i) for i in range(1, len(mag))])], ignore_index=True)
    show("U3b 대조: 과거 행 시각이 앞 기록 끝보다 이른 경우(3.0초)", far, MODEL.predict(far), rows=list(range(len(CLEAN) - 1, len(CLEAN) + 4)))
    resend = pd.concat([stamp(CLEAN, base_times), stamp(mag.iloc[:1], [s]), stamp(CLEAN.iloc[[-1]], [base_times[-1]]),
                        stamp(mag.iloc[1:], [s + pd.Timedelta(seconds=.1 * i) for i in range(1, len(mag))])], ignore_index=True)
    show("U3c 앞 기록의 마지막 행(3.7초)이 다음 기록 첫 행 뒤에 다시 도착(재전송)", resend, MODEL.predict(resend),
         rows=list(range(len(CLEAN) - 1, len(CLEAN) + 4)))


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    u0()
    u1()
    u2()
    u3()
