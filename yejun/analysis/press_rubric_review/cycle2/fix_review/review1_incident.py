"""검토 1: 사건 묶음(IncidentTracker) 반례 — 미래 시각 한 행, 8행 규칙(짧은 기록), 긴 오류 구간.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_incident.py
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))

import numpy as np
import pandas as pd

import model as M
from model import D, layout, load_bundle, StreamDetector, cases, incidents, timing_warning

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)


def summary(pred, label):
    inc_n = int(pred.incident_notification.sum()); inc_e = int(pred.incident_escalation.sum())
    print(f"  {label}: alarms {int(pred.alarm.sum())} | incidents {int(pred.incident_id.max())} | 사건 시작 알림 {inc_n} | 격상 알림 {inc_e} "
          f"| 사람에게 가는 알림 {inc_n + inc_e} | records {pred.record_id.nunique()}")
    return inc_n, inc_e


def stream_equal(frame, pred, chunk):
    det = StreamDetector(MODEL)
    parts = [det.push(frame.iloc[i:i + chunk]) for i in range(0, len(frame), chunk)]
    try:
        pd.testing.assert_frame_equal(pd.concat(parts, ignore_index=True), pred, rtol=1e-11, atol=1e-11)
        return True
    except AssertionError:
        return False


def spike_cases():
    print("\n## I1 미래 시각(+1h) 한 행을 이상 자료 중간에 끼운다(원래 행은 그대로 둔다)")
    base = MODEL.predict(ABN)
    summary(base, "원본(끼움 없음)")
    seg = D.segments(abnormal)
    for where in (100, 125, 350):
        glitch = ABN.iloc[[where]].copy()
        glitch[D.TIME] = (pd.to_datetime(glitch[D.TIME]) + pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        frame = pd.concat([ABN.iloc[:where], glitch, ABN.iloc[where:]], ignore_index=True)
        pred = MODEL.predict(frame)
        body = pred.drop(index=where).reset_index(drop=True)
        lost = int(base.alarm.sum() - body.alarm.sum())
        rec_of_spike = seg[where]
        in_rec = np.flatnonzero(seg == rec_of_spike)
        print(f"  spike before original row {where}(기록 {rec_of_spike}, 기록 안 위치 {where - in_rec[0]}): "
              f"bad_time_order {int(pred.status.eq('bad_time_order').sum())} | 튄 행 status {pred.status.iloc[where]} alarm {int(pred.alarm.iloc[where])} "
              f"| 원래 행의 경보 감소 {lost}행 | 기록 수 {base.record_id.nunique()}→{body.record_id.nunique()}")
        summary(pred, "  끼운 뒤")
        print("   사건 시작 알림 행:", pred.index[pred.incident_notification.eq(1)].tolist(), "| stream chunk1/7 동일:",
              stream_equal(frame, pred, 1), stream_equal(frame, pred, 7))


def quiet_records():
    """B 평가 구간에서 경보가 없는 정상 기록들(기록 경계를 그대로 둔다)."""
    p = MODEL.predict(TEST)
    alarmed = set(p.record_id[p.alarm.eq(1)])
    rec = layout(TEST)[1]
    return [TEST[rec == r].reset_index(drop=True) for r in np.unique(rec) if r not in alarmed]


QUIET = None


def normal_stretch(start, minutes, every=None, extra=.03, record_gap=2.0, nan_every=None):
    """정상 기록을 원래 경계 그대로 이어 붙인다(기록 사이 record_gap초). every를 주면 기록 안에서 every행마다 간격에 extra초를 더해
    기록을 every행 조각으로 쪼갠다(수집 시각 흔들림). nan_every를 주면 기록 안 nan_every행마다 진동 값을 NaN으로 둔다(센서 오류)."""
    global QUIET
    QUIET = QUIET or quiet_records()
    parts, t, total, i = [], pd.Timestamp(start), 0, 0
    while total < minutes * 600:
        r = QUIET[i % len(QUIET)].copy(); i += 1
        steps = np.full(len(r), .1); steps[0] = 0
        if every:
            steps[(np.arange(len(r)) % every == 0) & (np.arange(len(r)) > 0)] += extra
        times = t + pd.to_timedelta(np.cumsum(steps), unit="s")
        r[D.TIME] = times.strftime("%Y-%m-%d %H:%M:%S.%f")
        if nan_every:
            r.loc[r.index % nan_every == nan_every - 1, D.SENSORS[0]] = np.nan
        parts.append(r); total += len(r)
        t = times[-1] + pd.Timedelta(seconds=record_gap)
    return pd.concat(parts, ignore_index=True), t


def stamped(frame, start):
    out = frame.copy().reset_index(drop=True)
    out[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(out)) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
    return out, pd.Timestamp(start) + pd.Timedelta(seconds=len(out) * .1 + 2.0)


def two_anomalies(minutes, **kw):
    rec0 = ABN.iloc[np.flatnonzero(D.segments(abnormal) == 0)]
    rec9 = ABN.iloc[np.flatnonzero(D.segments(abnormal) == 9)]
    first, t = stamped(rec0, "2022-07-17 10:00:00")
    mid, t = normal_stretch(t, minutes, **kw)
    second, _ = stamped(rec9, t)
    return pd.concat([first, mid, second], ignore_index=True), len(first), len(mid)


def short_record_cases():
    print("\n## I2 8행 규칙: 두 이상 기록 사이 정상 구간의 기록이 짧게 쪼개지면(수집 시각 흔들림) 사건이 닫히지 않는다")
    for every in (7, 8, None):
        frame, n1, nm = two_anomalies(20, every=every)
        pred = MODEL.predict(frame)
        mid = pred.iloc[n1:n1 + nm]
        print(f"  정상 20분(기록 {every or '원래'}행 조각): 정상 구간 경보 {int(mid.alarm.sum())}행, 정상 구간 평균 기록 길이 {len(mid) / mid.record_id.nunique():.1f}행, "
              f"경고='{timing_warning(pred)[:50]}'")
        summary(pred, "  두 이상 기록(20분 간격)")
        second = pred.iloc[n1 + nm:]
        print(f"    둘째 이상 기록: 경보 {int(second.alarm.sum())}행, 사건 시작 알림 {int(second.incident_notification.sum())}, "
              f"격상 {int(second.incident_escalation.sum())}, 사건 번호 {sorted(set(second.incident_id) - {0})}")
        q = incidents(cases(pred), pred)
        print(f"    사건 대기열: {len(q)}사건, 단계 {q.level.tolist()}, 사건별 건 수 {q.cases.tolist()}")
        print("    stream chunk 7 동일:", stream_equal(frame, pred, 7))
    old = M.INCIDENT_MIN_CLEAR_ROWS
    M.INCIDENT_MIN_CLEAR_ROWS = 1
    try:
        frame, n1, nm = two_anomalies(20, every=7)
        summary(MODEL.predict(frame), "  (대조) 같은 입력에서 INCIDENT_MIN_CLEAR_ROWS=1(이전 규칙)")
    finally:
        M.INCIDENT_MIN_CLEAR_ROWS = old


def invalid_rows_cases():
    print("\n## I3 정상 기록 안에 센서 오류 행이 6행마다 끼면(진동 NaN) 유효 조각이 5행이라 사건이 닫히지 않는다")
    frame, n1, nm = two_anomalies(20, nan_every=6)
    pred = MODEL.predict(frame)
    mid = pred.iloc[n1:n1 + nm]
    print(f"  정상 20분: 오류 행 {int(mid.status.eq('bad_value').sum())}/{len(mid)}, 정상 구간 경보 {int(mid.alarm.sum())}, 경고='{timing_warning(pred)[:50]}'")
    summary(pred, "  두 이상 기록(20분 간격)")
    second = pred.iloc[n1 + nm:]
    print(f"    둘째 이상 기록: 사건 시작 알림 {int(second.incident_notification.sum())}, 격상 {int(second.incident_escalation.sum())}")
    print("\n## I4 긴 오류 구간(모든 센서 NaN, 시각은 0.1초 간격으로 연속) 사이의 두 이상 기록: 공백으로 판정")
    rec0 = ABN.iloc[np.flatnonzero(D.segments(abnormal) == 0)]
    rec9 = ABN.iloc[np.flatnonzero(D.segments(abnormal) == 9)]
    for seconds in (600, 40):
        mid = pd.concat([TEST] * 3, ignore_index=True).iloc[:int(seconds * 10)].copy(); mid[D.SENSORS] = np.nan
        frame, _ = stamped(pd.concat([rec0, mid, rec9], ignore_index=True), "2022-07-17 10:00:00")
        summary(MODEL.predict(frame), f"  오류 {seconds}초 사이")


if __name__ == "__main__":
    spike_cases()
    short_record_cases()
    invalid_rows_cases()
