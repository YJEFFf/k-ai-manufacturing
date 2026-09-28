"""검토 1: TimeOrder 권고안(예외 한 번, 원래 시간축을 이을 때만) 모의. 저장소 코드는 바꾸지 않고 하위 클래스로 비교한다.

    REVIEW_ENV=<사본의 yejun 폴더> PYTHONDONTWRITEBYTECODE=1 python review1_timeorder_proposed.py
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["REVIEW_ENV"]) / "press_guard"))
import numpy as np, pandas as pd
import model as M
from model import TimeOrder, D


class Proposed(TimeOrder):
    def step(self, t):
        if t is None or pd.isna(t):
            return False
        if self.ref is None or t >= self.ref:
            self.prev_ref, self.ref, self.run, self.run_last = self.ref, t, 0, None
            return False
        if self.prev_ref is not None and t >= self.prev_ref and abs((t - self.prev_ref).total_seconds() - D.DT) <= M.TIME_TOL_S:
            self.ref, self.prev_ref, self.run, self.run_last = t, None, 0, None      # 한 번만, 원래 시간축을 이을 때만
            return False
        steady = self.run_last is not None and abs((t - self.run_last).total_seconds() - D.DT) <= M.TIME_TOL_S
        previous = self.run_last
        self.run, self.run_last = (self.run + 1 if steady else 1), t
        if self.run >= M.REANCHOR_ROWS:
            self.prev_ref, self.ref, self.run, self.run_last = previous, t, 0, None
            return False
        return True


T0 = pd.Timestamp("2022-07-14", tz="UTC"); k = lambda i: T0 + pd.Timedelta(seconds=.1 * i); H = pd.Timedelta(hours=1)
cases = {
    "S2 중간 한 행 미래 튐": [k(i) for i in range(5)] + [T0 + H] + [k(i) for i in range(5, 15)],
    "S4 과거 한 행": [k(i) for i in range(5)] + [T0 - H] + [k(i) for i in range(5, 15)],
    "S5 시계 영구 후퇴": [k(i) for i in range(10)] + [T0 - H + pd.Timedelta(seconds=.1 * j) for j in range(10)],
    "S9 한 기록 역순(14→5)": [k(i) for i in range(5)] + [k(i) for i in range(14, 4, -1)] + [k(i) for i in range(15, 20)],
    "S10 튐 뒤 감소 시각": [k(i) for i in range(5)] + [T0 + H, T0 + pd.Timedelta(minutes=30), T0 + pd.Timedelta(minutes=20), T0 + pd.Timedelta(minutes=10)] + [k(i) for i in range(5, 10)],
    "S11 이웃 행 맞바뀜": [k(0), k(1), k(3), k(2), k(4), k(5)],
}
for name, times in cases.items():
    cur, new = TimeOrder(), Proposed()
    a = [i for i, t in enumerate(times) if cur.step(t)]
    b = [i for i, t in enumerate(times) if new.step(t)]
    print(f"{name:22s} 현재 보류 {a} | 권고안 보류 {b}")
