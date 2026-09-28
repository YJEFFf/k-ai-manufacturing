"""검토 5: 대회 이상 파일 600행(원자료는 사건 1개·시작 1·격상 1)에 시각 오류 한 곳을 넣었을 때 사건이 쪼개지는 비율.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_split.py
같은 스크립트를 3c6fbf3·110afa2 사본에 돌려 비교한다. 위치는 1~598행 가운데 무작위 80곳(시드 고정)이다.
  replace  행 i의 시각만 +Δ(표본 자리를 차지한 튐, 다음 행은 튀기 전 기준의 0.2초 뒤)
  insert   행 i 앞에 행 i를 +Δ 시각으로 끼움(다음 행은 튀기 전 기준의 0.1초 뒤)
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, load_bundle, time_order_events

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
_, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
T = pd.to_datetime(ABN[D.TIME])
rng = np.random.default_rng(5)
POS = np.sort(rng.choice(np.arange(1, 599), 80, replace=False))


def fmt(s):
    return s.dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def frame_for(kind, i, delta):
    if kind == "replace":
        t = T.copy(); t.iloc[i] += pd.Timedelta(seconds=delta)
        f = ABN.copy(); f[D.TIME] = fmt(t); return f
    ins = ABN.iloc[[i]].copy(); ins[D.TIME] = fmt(pd.Series([T.iloc[i - 1] + pd.Timedelta(seconds=delta)])).to_numpy()
    return pd.concat([ABN.iloc[:i], ins, ABN.iloc[i:]], ignore_index=True)


print(f"위치 {len(POS)}곳. 원자료: 사건 1·시작 1·격상 1·경보 569행")
for kind in ("replace", "insert"):
    for delta in (1.0, 5.0, 30.0, 59.9, 3600.0):
        split = starts = esc = held = alarms_lost = spike_alarm = 0
        for i in POS:
            p = MODEL.predict(frame_for(kind, int(i), delta))
            k = int(p.incident_id.max())
            split += k > 1
            starts += int(p.incident_notification.sum()) > 1
            esc += int(p.incident_escalation.sum()) > 1
            held += time_order_events(p)[0]
            alarms_lost += 569 + (1 if kind == "insert" else 0) - int(p.alarm.sum())
        print(f"  {kind:7s} Δ={delta:>6g}초: 사건 2개 이상 {split}/{len(POS)} · 시작 알림 2건 이상 {starts} · 격상 2건 이상 {esc} "
              f"· 보류 행 합 {held} · 줄어든 경보 행 합 {alarms_lost}")
