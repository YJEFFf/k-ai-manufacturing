"""검토(전략) 지적의 핵심 수치 재계산: 공식(가이드북) 분할에서 한 줄 규칙 F1, 부하 미상 대체 규칙, 이상 버스트 A60.

실행: python pilot_review_checks.py --root <데이터셋/프레스_유압펌프_예지보전>
"""
import argparse, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)

def a60(x):
    k = np.arange(len(x)); X = np.column_stack([np.ones(len(x)), np.cos(2*np.pi*0.06*k), np.sin(2*np.pi*0.06*k)])
    b = np.linalg.lstsq(X, x, rcond=None)[0]; return np.hypot(b[1], b[2])

# 1) 이상 버스트 A60 vs 정상 A60 분포 (10행 이상)
na = np.array([a60(d.AI2_Current.values) for _, d in N[N.ts < 3600].groupby('burst') if len(d) >= 10])
aa = np.array([a60(d.AI2_Current.values) for _, d in A.groupby('burst') if len(d) >= 10])
lo, hi = np.percentile(na, [0.5, 99.5])
print('normal 0-60 min A60 p0.5 %.1f p99.5 %.1f | abnormal A60 median %.1f, below p0.5: %d/%d' % (lo, hi, np.median(aa), (aa < lo).sum(), len(aa)))

# 2) 공식 분할에서 한 줄 규칙: 버스트 max|AI0| > 정상 0-40분 최댓값, 버스트 판정을 행에 펼침
thr = N[N.ts < 2400].AI0_Vibration.abs().max()
def burst_flag(df):
    m = df.groupby('burst').AI0_Vibration.transform(lambda s: s.abs().max())
    return (m > thr).astype(int).values
fN = burst_flag(N); fA = burst_flag(A)
tn_rows = np.arange(15880, 19899); ta_rows = np.arange(300, 499)   # 가이드북 시험 창이 덮는 행 범위
pred = np.r_[fN[tn_rows], fA[ta_rows]]; y = np.r_[np.zeros(len(tn_rows)), np.ones(len(ta_rows))]
tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
f1 = 2 * tp / (2 * tp + fp + fn)
print('one-liner on guidebook split (row-level approx): thr %.4f TP %d FP %d FN %d TN %d F1 %.3f' % (thr, tp, fp, fn, tn, f1))

# 3) 부하 미상 대체 규칙: 상부진동 RMS > 정상 0-40분 최댓값(10행 이상 버스트)
rms = lambda d: np.sqrt(np.mean(d.AI0_Vibration ** 2))
nb = [(d.ts.iloc[0], rms(d)) for _, d in N.groupby('burst') if len(d) >= 10]
env = max(r for t, r in nb if t < 2400)
test = [r for t, r in nb if t >= 2400]
ab = [rms(d) for _, d in A.groupby('burst') if len(d) >= 10]
print('load-unknown rule: env(0-40 min max upper RMS) %.3f | abnormal %d/%d (x1.5: %d) | normal 40-77 min FA %d/%d'
      % (env, sum(r > env for r in ab), len(ab), sum(r > 1.5 * env for r in ab), sum(r > env for r in test), len(test)))
mx = N.AI0_Vibration.abs().max()
print('extreme fast path max|AI0| > 3 x normal max (%.3f): abnormal bursts %d/21'
      % (3 * mx, sum(d.AI0_Vibration.abs().max() > 3 * mx for _, d in A.groupby('burst'))))
