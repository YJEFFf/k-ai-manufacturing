"""검토 5: 3c6fbf3의 튐 예외(다음 표본·60초 넘는 튐 뒤 60초 안)가 잘못 발동하거나 빠지는 입력.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_time_rules.py
같은 스크립트를 110afa2 사본(REVIEW_ENV=<110afa2 사본>)에도 돌려 두 판을 비교한다. 모델은 사본의 artifacts/guard_B.json이다.

A  한 표본의 시각만 +Δ 틀림(표본 자리를 차지한 튐, 다음 행은 튀기 전 기준의 0.2초 뒤). 대회 이상 파일(한 에피소드) 가운데.
B  대조: 같은 행을 +Δ 시각으로 끼움(끼운 튐, 다음 행은 튀기 전 기준의 0.1초 뒤).
C  60초 넘는 수집 중단 뒤 새 기록 첫 행 다음에 공백 안의 과거 행 한 개(R3-03의 60초 초과 판).
D  튄 행이 두 번 도착(동률 재전송) 뒤 원래 시간축.
E  60초 경계에 걸친 역순 기록.
F  60초 넘는 중단 뒤 시계가 뒤로 재설정.
각 사례는 일괄 predict와 StreamDetector(청크 1·7·128)가 같은지도 본다.
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, layout, load_bundle, StreamDetector, time_order_events, cases, timing_warning

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
CLEAN = TEST[layout(TEST)[1] == 0].reset_index(drop=True)          # 경보 없는 정상 기록 50행
T0 = pd.Timestamp("2022-07-17 10:00:00")
ABN_T = pd.to_datetime(ABN[D.TIME])


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
    return "".join("=" if r else "X" for r in res)


def summary(pred):
    g = pred[pred.incident_id.gt(0)].groupby("incident_id")
    dup = int(((g.incident_notification.sum() > 1) | (g.incident_escalation.sum() > 1)).sum())
    held, re, sk = time_order_events(pred)
    return (f"보류 {held}·새기준 {re}·튐건너뜀 {sk} | 경보 {int(pred.alarm.sum())} | 사건 {g.ngroups} "
            f"| 시작 {int(pred.incident_notification.sum())} | 격상 {int(pred.incident_escalation.sum())} | 중복사건 {dup}")


def run(title, frame, show=None, stream=True):
    pred = MODEL.predict(frame)
    line = f"  {title}: {summary(pred)}"
    if stream:
        line += f" | 일괄=스트림(1·7·128) {stream_same(frame, pred)}"
    print(line)
    if show is not None:
        v = pred.loc[show, ["time_order_event", "status", "record_id", "alarm", "incident_id", "incident_notification", "incident_escalation"]].copy()
        v.insert(0, "t", frame[D.TIME].iloc[show].str[11:].to_numpy())
        print("    " + v.to_string().replace("\n", "\n    "))
        print("    경고:", timing_warning(pred) or "(없음)")
    return pred


def a_b():
    print("## A 표본 자리를 차지한 튐(행 i의 시각만 +Δ) / B 끼운 튐(행 i 앞에 +Δ 행을 더함), 대회 이상 파일 600행")
    run("대조(원자료)", ABN, stream=False)
    for i in (70, 8):                                    # 70: 1행 기록으로도 크기 경보, 8: 1행 기록이면 경보 없음
        for delta in (0.3, 1.0, 5.0, 30.0, 59.9, 60.5, 3600.0):
            t = ABN_T.copy(); t.iloc[i] += pd.Timedelta(seconds=delta)
            frame = stamp(ABN, t)
            run(f"A 행 {i} +{delta:g}초", frame, show=list(range(i - 1, i + 4)) if (i == 70 and delta == 5.0) else None,
                stream=(delta in (5.0, 3600.0)))
        for delta in (5.0,):
            ins = ABN.iloc[[i]].copy(); ins[D.TIME] = fmt(ABN_T.iloc[i - 1] + pd.Timedelta(seconds=delta))
            frame = pd.concat([ABN.iloc[:i], ins, ABN.iloc[i:]], ignore_index=True)
            run(f"B 행 {i} 앞에 +{delta:g}초 행 끼움", frame)


def mag_rows(k):
    iso = stamp(ABN, [T0 + pd.Timedelta(seconds=10 * i) for i in range(len(ABN))])
    idx = np.flatnonzero(MODEL.predict(iso).alarm.eq(1).to_numpy())
    return ABN.iloc[idx[:k]].reset_index(drop=True)


def c():
    print("\n## C 수집 중단 G초 뒤 새 기록(1행으로도 경보) 첫 행 다음에 공백 안의 과거 행(앞 기록 끝 + min(G/2, 30)초)")
    mag = mag_rows(6)
    base = [T0 + pd.Timedelta(seconds=.1 * i) for i in range(len(CLEAN))]
    end = base[-1]
    for gap in (10.0, 59.0, 61.0, 120.0, 600.0):
        s = end + pd.Timedelta(seconds=gap)
        good = pd.concat([stamp(CLEAN, base), stamp(mag, [s + pd.Timedelta(seconds=.1 * i) for i in range(len(mag))])], ignore_index=True)
        past = end + pd.Timedelta(seconds=min(gap / 2, 30.0))
        bad = pd.concat([stamp(CLEAN, base), stamp(mag.iloc[:1], [s]), stamp(CLEAN.iloc[[10]], [past]),
                         stamp(mag.iloc[1:], [s + pd.Timedelta(seconds=.1 * i) for i in range(1, len(mag))])], ignore_index=True)
        run(f"G={gap:g}초 대조(과거 행 없음)", good, stream=False)
        run(f"G={gap:g}초 과거 행 {min(gap / 2, 30.0):g}초", bad, show=list(range(len(CLEAN) - 1, len(CLEAN) + 3)) if gap == 120.0 else None)


def d():
    print("\n## D 튄 행이 두 번 도착(동률) 뒤 원래 시간축(끼운 +5초·+3600초 튐, 행 70)")
    i = 70
    for delta in (5.0, 3600.0):
        ins = ABN.iloc[[i]].copy(); ins[D.TIME] = fmt(ABN_T.iloc[i - 1] + pd.Timedelta(seconds=delta))
        one = pd.concat([ABN.iloc[:i], ins, ABN.iloc[i:]], ignore_index=True)
        two = pd.concat([ABN.iloc[:i], ins, ins, ABN.iloc[i:]], ignore_index=True)
        run(f"+{delta:g}초 한 번", one, stream=False)
        run(f"+{delta:g}초 두 번(재전송)", two, show=list(range(i - 1, i + 5)) if delta == 3600.0 else None)


def e():
    print("\n## E 60초 경계에 걸친 역순 기록: 앞 기록 끝 E, 다음 기록 E+58.0~E+62.9(50행)가 역순으로 도착")
    base = [T0 + pd.Timedelta(seconds=.1 * i) for i in range(len(CLEAN))]
    end = base[-1]
    for start in (40.0, 58.0, 70.0):
        rev = [end + pd.Timedelta(seconds=start + .1 * k) for k in range(50)][::-1]
        frame = pd.concat([stamp(CLEAN, base), stamp(ABN.iloc[100:150], rev)], ignore_index=True)
        pred = run(f"다음 기록 E+{start:g}~E+{start + 4.9:g}초 역순", frame)
        sk = np.flatnonzero(pred.time_order_event.eq(2).to_numpy())
        if len(sk):
            print(f"    튐 건너뜀 행: {sk.tolist()} 시각 {frame[D.TIME].iloc[sk].str[11:].tolist()}")


def f():
    print("\n## F 수집 중단 뒤 새 기록 첫 행 다음에 시계가 뒤로 재설정(새 시간축이 앞 기록 끝 + 40초에서 이어짐)")
    mag = mag_rows(6)
    base = [T0 + pd.Timedelta(seconds=.1 * i) for i in range(len(CLEAN))]
    end = base[-1]
    for gap in (50.0, 300.0):
        s = end + pd.Timedelta(seconds=gap)
        reset = end + pd.Timedelta(seconds=40.0)
        frame = pd.concat([stamp(CLEAN, base), stamp(mag.iloc[:1], [s]),
                           stamp(mag.iloc[1:], [reset + pd.Timedelta(seconds=.1 * i) for i in range(len(mag) - 1)])], ignore_index=True)
        run(f"G={gap:g}초, 둘째 행부터 E+40초", frame, show=list(range(len(CLEAN) - 1, len(CLEAN) + 4)))


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    a_b()
    c()
    d()
    e()
    f()
