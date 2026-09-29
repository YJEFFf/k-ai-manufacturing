"""검토 8: 경보가 드문 약한 이상(검토 7과 같은 주입: 정상 평가 B 기록 20~49에 전류 잡음 Lσ, 시드 고정)의 모든 기록 경계(29곳)에
'공백으로 옮겨져 이웃 기록에 붙는' 시각 오류를 넣고, 사건 수·시작·격상 알림이 오류 없는 입력과 달라지는 경계 수를 센다. 두 판에서 같은 입력.

오류(경계 하나에 하나씩):
  late1/late2: 앞 기록 끝 1·2행을 +(공백 − 0.3초) → 다음 기록 첫 행 0.3초 앞에 붙음
  early1/early2: 뒤 기록 첫 1·2행을 −(공백 − 0.3초) → 앞 기록 끝 0.3초 뒤에 붙음
  clock: 뒤 기록부터 끝까지 −(공백 − 0.3초) → 기록 사이 공백이 0.3초가 됨(시계 한 번 뒤로)

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_boundary.py [--level 0.1]
"""
import argparse

import numpy as np
import pandas as pd

import review7_weak as W
import review8_lib as L

ap = argparse.ArgumentParser()
ap.add_argument("--level", type=float, default=0.1)
a = ap.parse_args()
_, M, F, T = W.setup(a.level)
base = M.predict(F)
rec = L.D.segments(F)
starts = np.flatnonzero(np.r_[True, rec[1:] != rec[:-1]])
gaps = [(T[s] - T[s - 1]).total_seconds() for s in starts[1:]]
bs = L.summ(base)
print(f"# 판 {L.VERSION} · 세기 {a.level}σ · {len(F)}행 · 경계 {len(starts) - 1}곳(공백 {min(gaps):.2f}~{max(gaps):.2f}초) · 원자료 (사건, 시작, 격상) {bs}")
FMT = L.FMT
for kind in ("late1", "late2", "early1", "early2", "clock"):
    more = less = same_ = 0
    detail = []
    for s, g in zip(starts[1:], gaps):
        d = g - 0.3
        f = F.copy()
        if kind.startswith("late"):
            for j in range(int(kind[-1])):
                f.loc[s - 1 - j, L.D.TIME] = (T[s - 1 - j] + pd.Timedelta(seconds=d)).strftime(FMT)
        elif kind.startswith("early"):
            for j in range(int(kind[-1])):
                f.loc[s + j, L.D.TIME] = (T[s + j] - pd.Timedelta(seconds=d)).strftime(FMT)
        else:
            f.loc[s:, L.D.TIME] = (T[s:] - pd.Timedelta(seconds=d)).dt.strftime(FMT)
        p = M.predict(f)
        r = L.summ(p)
        if r[0] > bs[0]:
            more += 1; detail.append((int(s), "+", r))
        elif r[0] < bs[0]:
            less += 1; detail.append((int(s), "−", r))
        else:
            same_ += 1
    print(f"  {kind:6s}: 사건 늘어남 {more} · 줄어듦 {less} · 같음 {same_} · 달라진 경계(행, 방향, (사건, 시작, 격상)) {detail}")
