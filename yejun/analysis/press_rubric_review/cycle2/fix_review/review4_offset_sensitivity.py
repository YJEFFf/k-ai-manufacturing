"""review4: 순수한 전류 수준 이동(기록 전체 +δ)에 동결 v2가 반응하는가. 정상 평가 기록에 δ를 더한다(팀 함수 미사용).

주장 2('v2 경보는 이 치우침에 기대지 않는다')와 class_differences.csv의 '예측 오차(상수항, 약함)' 표기를 점검한다.
AR(2) 잔차는 x_t − c0 − c1·x_{t−1} − c2·x_{t−2}라 상수 이동 δ에 (1 − c1 − c2)·δ만큼 움직인다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import review4_indep as I  # noqa: E402

pd.set_option("display.width", 220)
n, a = I.load_raw()
rn = I.records(n.TimeStamp)
SPL = {"A": 480, "B": 420}
rows = []
for sid in ("A", "B"):
    m = I.Model(sid)
    k = 1 - m.ar[1] - m.ar[2]
    mask = rn >= SPL[sid]
    t = n[mask].reset_index(drop=True)
    v0 = t[I.SENS].to_numpy(float)
    rec = I.records(t.TimeStamp)
    for d in (0, 25, 50, 100, 150, 230, 272):
        v = v0.copy(); v[:, 2] += d
        p = m.predict(v, t.TimeStamp)
        al = p.groupby("record").alarm.max()
        comp = p[p.alarm.eq(1)].reason.str.split("+").explode().value_counts().to_dict()
        rows.append(dict(split=sid, delta=d, residual_shift=round(k * d, 1), dyn_tail_u=round(m.tails["dynamics"].u, 1),
                         records_alarmed=f"{int(al.sum())}/{len(al)}", alarm_rows=int(p.alarm.sum()), rows=len(p),
                         components=comp))
print(pd.DataFrame(rows).to_string(index=False))
