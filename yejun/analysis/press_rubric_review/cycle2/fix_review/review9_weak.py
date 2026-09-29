"""검토 9: 경보가 드문 약한 이상(검토 7·8과 같은 주입: 정상 평가 B 기록 20~49에 전류 잡음 Lσ, 시드 고정)에서
(1) 모든 기록 경계(29곳)에 '도착한 행 수'를 부풀리는 행(시각 빈 행 k개, 앞 기록 행 k개 역순 재전송)을 넣었을 때,
(2) 모든 행의 수집 시각에 독립 흔들림 U(−s, +s)를 넣었을 때 사건 수·시작·격상 알림이 오류 없는 입력과 얼마나 달라지는가. 판마다 같은 입력.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review9_weak.py [--level 0.1]
"""
import argparse
import math

import numpy as np
import pandas as pd

import review7_weak as W
import review9_lib as L

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


def tally(kind, frames):
    more = less = same_ = 0
    detail = []
    for s, f in frames:
        r = L.summ(M.predict(f))
        if r[0] > bs[0]:
            more += 1; detail.append((int(s), "+", r))
        elif r[0] < bs[0]:
            less += 1; detail.append((int(s), "−", r))
        else:
            same_ += 1
    print(f"  {kind:28s}: 사건 늘어남 {more} · 줄어듦 {less} · 같음 {same_} · 달라진 경계(행, 방향, (사건, 시작, 격상)) {detail}", flush=True)


print("## (1) 경계마다 도착 행 수를 부풀리는 행")
for k in (5, 15, 30):
    tally(f"빈 시각 {k}행", [(s, L.insert(F, s, L.blank_rows(F, k, s))) for s in starts[1:]])
tally("빈 시각 round(공백/0.1초)행", [(s, L.insert(F, s, L.blank_rows(F, int(round(g / 0.1)), s)))
                                     for s, g in zip(starts[1:], gaps)])
for k in (5, 15, 30):
    frames = []
    for s in starts[1:]:
        prev = int(starts[starts < s][-1])
        late = F.iloc[max(prev, s - k):s].iloc[::-1].reset_index(drop=True)
        frames.append((s, L.insert(F, s, late)))
    tally(f"앞 기록 끝 {k}행 역순 재전송", frames)

print("## (2) 모든 행 수집 시각 독립 흔들림 U(−s, +s)")
for s in (0.01, 0.02, 0.03, 0.04, 0.049):
    rows = []
    for seed in range(5):
        e = np.random.default_rng(1000 + seed).uniform(-s, s, len(F))
        f = F.copy()
        f[L.D.TIME] = (T + pd.to_timedelta(np.round(e * 1e6), unit="us")).dt.strftime(L.FMT)
        p = M.predict(f)
        r = L.summ(p)
        # 사건 추적 단위 수(5차: CollectionUnits 연속 수집 수, 앞 판: 기록구간 수)
        if hasattr(L.M, "CollectionUnits"):
            u = L.M.CollectionUnits()
            tt = pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce")
            runs = len({u.step(t, not pd.isna(t) and ev != L.M.ORDER_HELD)[0] for t, ev in zip(tt, p.time_order_event)})
        else:
            runs = int(p.record_id.nunique())
        rows.append((r, runs, int(p.alarm.sum()), int(p.record_id.nunique())))
    print(f"  s = {s * 1000:.0f} ms: (사건, 시작, 격상)·사건 단위 연속 수 · 경보 행 · 기록구간 수 = {rows}", flush=True)
