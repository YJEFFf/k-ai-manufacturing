"""검토 5: recalibrate.py 운전 범위 점검(outside_pmf·outside_limit·coverage)의 정확 분포·한도·경계·계산 시간, 대회 정상 자료에서의 경고.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_coverage.py
1) 작은 n·m에서 모든 배열을 세어 outside_pmf와 대조, 2) 연속 i.i.d. 모의(20만 회)와 대조, 3) 경계(n=2, m=1, n<2, m=0, 동률),
4) 큰 n·m 계산 시간, 5) 대회 정상 기록 600개를 480기록씩 밀어 가며(학습 300·보정 120·수락 60) 경고가 나는지.
"""
import itertools
import math
import os
import sys
import time
from fractions import Fraction
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
import recalibrate as R
from model import D


def brute(n, m):
    counts = [0] * (m + 1)
    for pos in itertools.combinations(range(n + m), n):          # 보정 단위가 놓인 순위
        lo, hi = pos[0], pos[-1]
        counts[lo + (n + m - 1 - hi)] += 1
    total = math.comb(n + m, n)
    return [Fraction(c, total) for c in counts]


print("## 1) 모든 배열을 센 분포와 outside_pmf")
bad = [(n, m) for n in range(2, 9) for m in range(0, 7) if brute(n, m) != R.outside_pmf(n, m)]
print(f"  n=2..8, m=0..6 (49쌍) 불일치: {bad}")

print("## 2) 연속 i.i.d. 모의와 한도(q = 1 − 0.05/3)")
rng = np.random.default_rng(7)
for n, m in ((97, 48), (120, 60), (20, 200), (5, 40)):
    reps = 200000
    lim = R.outside_limit(n, m, 1 - .05 / 3)
    x = rng.random((reps, n)); y = rng.random((reps, m))
    lo, hi = x.min(1, keepdims=True), x.max(1, keepdims=True)
    T = ((y < lo) | (y > hi)).sum(1)
    pmf = R.outside_pmf(n, m)
    exceed = float(sum(pmf[lim + 1:]))
    print(f"  n={n}, m={m}: 한도 {lim}, 정확 P(T>한도)={exceed:.5f}, 모의 {np.mean(T > lim):.5f}, 평균 정확 {2 * m / (n + 1):.3f} 모의 {T.mean():.3f}")

print("## 3) 경계")
print("  n=2,m=1:", R.outside_pmf(2, 1), "한도(0.95):", R.outside_limit(2, 1, .95))
print("  n=2,m=5:", [str(p) for p in R.outside_pmf(2, 5)], "한도(0.9833):", R.outside_limit(2, 5, 1 - .05 / 3))
print("  m=0:", R.outside_pmf(10, 0), R.outside_limit(10, 0, .98))
try:
    print("  n=1,m=3:", R.outside_pmf(1, 3))
except Exception as exc:
    print("  n=1,m=3: 예외", repr(exc))
cal = pd.DataFrame({"TimeStamp": pd.date_range("2022-07-14", periods=17, freq="100ms").strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "AI0_Vibration": np.r_[np.zeros(16), 1.0], "AI1_Vibration": 0.0, "AI2_Current": np.sin(np.arange(17))})
print("  보정 17행 단위 1개(n=1):", {k: v for k, v in R.coverage(cal, cal).items() if k in ("cal_units", "holdout_units", "note", "flagged")})

print("## 4) 큰 n·m 계산 시간(outside_limit)")
for n, m in ((5000, 5000), (20, 20000), (2, 100000), (100000, 100000), (50000, 20)):
    t0 = time.perf_counter(); lim = R.outside_limit(n, m, 1 - .05 / 3); dt = time.perf_counter() - t0
    print(f"  n={n}, m={m}: 한도 {lim} ({dt:.2f}초)")
t0 = time.perf_counter(); R.outside_pmf(3000, 3000); print(f"  outside_pmf(3000,3000) {time.perf_counter() - t0:.2f}초(시험에서만 씀)")

print("## 5) 대회 정상 자료(600기록)를 480기록씩 밀며 학습 300·보정 120·수락 60")
normal, _, _ = D.load()
seg = D.segments(normal)
rows = []
for s in range(0, 121, 10):
    frame = D.inputs_only(normal[(seg >= s) & (seg < s + 480)]).reset_index(drop=True)
    parts, total, n_train = R.split_units(frame, 120, 60)
    cov = R.coverage(parts["cal"], parts["holdout"])
    f = cov["features"]
    rows.append(dict(start=s, cal_units=cov["cal_units"], holdout_units=cov["holdout_units"], limit=f["current_rms"]["limit"],
                     **{k: f[k]["holdout_below"] + f[k]["holdout_above"] for k in f}, flagged="+".join(cov["flagged"])))
    for k in cov["flagged"]:
        print(f"  창 {s}: {k} 보정 범위 {f[k]['cal_min']:.4f}~{f[k]['cal_max']:.4f}, 수락 단위 아래 {f[k]['holdout_below']}·위 {f[k]['holdout_above']} (보정 기록 {s + 300}~{s + 419}, 수락 기록 {s + 420}~{s + 479})")
print(pd.DataFrame(rows).to_string(index=False))
