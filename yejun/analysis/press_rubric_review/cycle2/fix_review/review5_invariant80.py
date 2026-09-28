"""검토 5: 3c6fbf3 test_random_time_faults_keep_one_start_and_escalation_per_incident의 입력 80회를 그대로 만들어
두 판(3c6fbf3·110afa2)에서 사건 불변식(사건마다 시작·격상 ≤ 1) 위반 시행 수와 사건 수(한 이상 에피소드가 몇 사건이 되는가)를 센다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_invariant80.py
"""
import os
import sys
from collections import Counter
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, load_bundle

model = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
_, abnormal, _ = D.load()
rng = np.random.default_rng(20260929)
base = D.inputs_only(abnormal).reset_index(drop=True)
times = pd.to_datetime(base[D.TIME])
viol, incidents, starts = 0, Counter(), Counter()
for trial in range(80):
    t = times.copy()
    for _ in range(6):
        i = int(rng.integers(1, len(base) - 2))
        kind = rng.choice(["swap", "jump", "spike", "back", "swap"])
        if kind == "swap":
            t.iloc[[i, i + 1]] = t.iloc[[i + 1, i]].to_numpy()
        elif kind == "jump":
            t.iloc[i] += pd.Timedelta(seconds=float(rng.choice([.2, .3, 2, 5, 30])))
        elif kind == "spike":
            t.iloc[i] += pd.Timedelta(hours=1)
        else:
            t.iloc[i] -= pd.Timedelta(hours=1)
    stamps = t.dt.strftime("%Y-%m-%d %H:%M:%S.%f").tolist()
    for i in rng.choice(len(base), 3, replace=False):
        if rng.random() < .5:
            stamps[i] = ""
    frame = base.copy(); frame[D.TIME] = stamps
    pred = model.predict(frame)
    c = pred[pred.incident_id.gt(0)].groupby("incident_id")[["incident_notification", "incident_escalation"]].sum()
    viol += int((c > 1).any(axis=None))
    incidents[int(pred.incident_id.max())] += 1
    starts[int(pred.incident_notification.sum())] += 1
print(f"불변식 위반 시행 {viol}/80 | 사건 수 분포 {dict(sorted(incidents.items()))} | 시작 알림 수 분포 {dict(sorted(starts.items()))}")
