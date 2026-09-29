"""4차 자체 점검: 시각이 틀려 기록 사이 공백으로 옮겨진 한 행이 이웃 정상 기록에 붙을 때 두 이상이 합쳐지는가.
[이상 기록 11, 정상 m행, (b에서는 1행으로도 경보가 나는 행 +) 이상 기록 12]를 3초 공백으로 잇고,
(a) 이상 11 끝 행을 +d초 늦게, (b) 둘째 이상 첫 행을 −d초 이르게 찍는다. 칸의 세 숫자는 (사건 수, 시작 알림, 격상 알림)이고 원자료는 222다.
d = 2.88·2.9초는 붙은 간격이 정상 간격(0.1초 ± 20 ms)이라 어느 판도 구분하지 못한다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python selfcheck4_displaced.py <사본의 yejun/press_guard>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PG = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(PG))
from model import D, StreamDetector, load_bundle  # noqa: E402

model = load_bundle(PG / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
seg = D.segments(abnormal)
test = D.inputs_only(D.split_normal(normal, D.segments(normal), "B")["test"]).reset_index(drop=True)
pred = model.predict(test)
rec = pred.record_id.to_numpy()
quiet = [r for r in np.unique(rec) if pred.alarm[rec == r].sum() == 0 and (rec == r).sum() >= 30]
q = test[rec == quiet[0]].reset_index(drop=True)
ab = D.inputs_only(abnormal).reset_index(drop=True)
probe = ab.copy()
probe[D.TIME] = [(pd.Timestamp("2022-07-17 10:00:00") + pd.Timedelta(seconds=10 * i)).strftime("%Y-%m-%d %H:%M:%S.%f") for i in range(len(ab))]
mag = ab.iloc[np.flatnonzero(model.predict(probe).alarm.eq(1).to_numpy())[:1]]
r11, r12 = (D.inputs_only(abnormal[seg == k]).reset_index(drop=True) for k in (11, 12))
FMT = "%Y-%m-%d %H:%M:%S.%f"


def chain(parts, gap=3.0):
    frames, times, t = [], [], pd.Timestamp("2022-07-22")
    for part in parts:
        times += list(t + pd.to_timedelta(np.arange(len(part)) * .1, unit="s"))
        t = times[-1] + pd.Timedelta(seconds=gap)
        frames.append(D.inputs_only(part))
    f = pd.concat(frames, ignore_index=True)
    f[D.TIME] = pd.Series(times).dt.strftime(FMT)
    return f


def summ(p):
    return f"{int(p.incident_id.max())}{int(p.incident_notification.sum())}{int(p.incident_escalation.sum())}"


def stream_same(f, p, n):
    det = StreamDetector(model)
    s = pd.concat([det.push(f.iloc[i:i + n]) for i in range(0, len(f), n)], ignore_index=True)
    cols = ["incident_id", "incident_notification", "incident_escalation", "incident_update", "alarm"]
    return bool((s[cols].to_numpy() == p[cols].to_numpy()).all())


bad = 0
for side in ("a", "b"):
    for m in (10, 14, 20, 40):
        second = r12 if side == "a" else pd.concat([D.inputs_only(mag), r12], ignore_index=True)
        frame = chain([r11, q.iloc[:m], second])
        t = pd.to_datetime(frame[D.TIME])
        row, sign = (len(r11) - 1, 1) if side == "a" else (len(r11) + m, -1)
        cells = [f"({side}) m={m:2d} 원자료 {summ(model.predict(frame))} |"]
        for d in (2.5, 2.55, 2.6, 2.7, 2.8, 2.85, 2.88, 2.9, 2.95):
            f = frame.copy()
            f.loc[row, D.TIME] = (t[row] + pd.Timedelta(seconds=sign * d)).strftime(FMT)
            p = model.predict(f)
            cells.append(f"{d}:{summ(p)}{'' if int(p.alarm[row]) else '(무경보)'}")
            bad += sum(not stream_same(f, p, n) for n in (1, 7, 64))
        print(" ".join(cells))
print("일괄≠스트림(청크 1·7·64):", bad)
