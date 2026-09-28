"""검토 5: IncidentTracker 단독 무작위 시험(모델 없이). 되돌리기(undo)를 아무 유효 행 뒤에나 넣어도(튄 행 되돌리기의 상위 집합)
_prune 때문에 KeyError가 나거나, 한 사건에 시작·격상 알림이 두 번 나가거나, 발급 번호가 겹치는지 본다.

    REVIEW_ENV=<사본의 yejun 폴더> PYTHONDONTWRITEBYTECODE=1 python review5_tracker_fuzz.py
"""
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import IncidentTracker

rng = np.random.default_rng(11)
errors, dup_start, dup_esc, undo_calls, max_kept = 0, 0, 0, 0, 0
T0 = pd.Timestamp("2022-07-14", tz="UTC")
for seq in range(3000):
    tr = IncidentTracker()
    t, rec, blk = 0.0, 0, 0
    starts, escs = Counter(), Counter()
    for step in range(int(rng.integers(20, 120))):
        r = rng.random()
        if r < .25:
            rec += 1; blk = 0; t += float(rng.choice([0.2, 2.0, 30.0, 59.0, 61.0, 300.0, -3.0, -100.0]))
        elif r < .30:
            blk += 1
        t += .1
        valid = rng.random() > .1
        alarm = rng.random() < .45
        reason = rng.choice(["magnitude", "waveform", "dynamics", "magnitude+dynamics", "waveform+dynamics"])
        time = None if rng.random() < .05 else T0 + pd.Timedelta(seconds=t)
        try:
            k, n, e, u = tr.update(rec, blk, alarm, reason, time, valid)
        except Exception as exc:
            errors += 1; print("예외", seq, step, repr(exc)); break
        starts[k] += n; escs[k] += e
        max_kept = max(max_kept, len(getattr(tr, "alarms", {})))
        if valid and rng.random() < .15:        # 방금 넣은 유효 행을 되돌린다(튄 행 되돌리기)
            tr.undo(); undo_calls += 1
    dup_start += sum(1 for k, v in starts.items() if k and v > 1)
    dup_esc += sum(1 for k, v in escs.items() if k and v > 1)
print(f"수열 3000개, 되돌리기 {undo_calls}회, 예외 {errors}, 시작 두 번 이상인 사건 {dup_start}, 격상 두 번 이상인 사건 {dup_esc}, 보관한 사건 상태 최대 {max_kept}개")
