"""검토(방법론) 지적 재계산: ① 마지막 행 시각 기준 스트로크 주기, ② 부하 보정 진동의 시간 드리프트, ③ 단측 대 양측 판정의 장시간 대기 오경보(같은 보정 방식).

실행: python pilot_drift_anchor.py --root <데이터셋/프레스_유압펌프_예지보전>
"""
import argparse, os, sys
import numpy as np, pandas as pd
from scipy.signal import lombscargle
from scipy.stats import kendalltau, theilslopes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)

def a60(x):
    k = np.arange(len(x)); X = np.column_stack([np.ones(len(x)), np.cos(2*np.pi*0.06*k), np.sin(2*np.pi*0.06*k)])
    b = np.linalg.lstsq(X, x, rcond=None)[0]; return np.hypot(b[1], b[2])
rows = []
for b, d in N.groupby('burst'):
    if len(d) < 10: continue
    rows.append(dict(t0=d.ts.iloc[0], tend=d.ts.iloc[-1], n=len(d), amp=a60(d.AI2_Current.values),
                     v0=np.sqrt(np.mean(d.AI0_Vibration**2)), v1=np.sqrt(np.mean(d.AI1_Vibration**2))))
B = pd.DataFrame(rows)

# ① 스트로크 주기: 시작 시각 vs 마지막 행 시각, 0–60분
S = B[B.t0 < 3600]; y = S.amp.values - S.amp.mean()
per = np.linspace(1.0, 30, 60000)
for nm, t in [('start time', S.t0.values), ('last-row time', S.tend.values)]:
    p = lombscargle(t, y, 2*np.pi/per, normalize=True); i = np.argmax(p)
    print(f'① {nm:13s}: top period {per[i]:.4f} s power {p[i]:.3f}')
fine = np.linspace(2.88, 2.92, 4001); pf = lombscargle(S.tend.values, y, 2*np.pi/fine, normalize=True)
T = fine[np.argmax(pf)]; print(f'   refined last-row period {T:.4f} s (power {pf.max():.3f})')
for lo, hi in [(0, 1200), (1200, 2400), (2400, 3600)]:
    s = S[(S.t0 >= lo) & (S.t0 < hi)]; yy = s.amp.values - s.amp.mean()
    print(f'   segment {lo//60:2d}-{hi//60:2d} min: power at {T:.4f} s = {lombscargle(s.tend.values, yy, [2*np.pi/T], normalize=True)[0]:.3f}')

# ② 드리프트: 가압(A60>180) 하부진동 log RMS를 log 부하 3차로 보정한 잔차의 시간 추세 (0–60분)
L = B[(B.t0 < 3600) & (B.amp > 180)].copy()
X = np.column_stack([np.ones(len(L))] + [np.log(L.amp.values) ** k for k in (1, 2, 3)])
for ch in ('v1', 'v0'):
    yv = np.log(L[ch].values); coef = np.linalg.lstsq(X, yv, rcond=None)[0]; r = yv - X @ coef
    sl = theilslopes(r, L.t0.values / 600.0); tau = kendalltau(L.t0.values, r)
    print(f'② loaded {ch}: Theil-Sen slope {sl[0]:+.4f} log/10min (95% CI {sl[2]:+.4f}..{sl[3]:+.4f}), Kendall tau {tau.correlation:.3f} p {tau.pvalue:.1e}, n={len(L)}')

# ③ 같은 보정(보정 구간 99 % 분위) 아래 단측 vs 양측: 학습 0–40분, 보정 40–60분, 시험 장시간 대기 60–72분
def fit_law(d, ch):
    X = np.column_stack([np.ones(len(d)), np.log(d.amp), np.log(d.amp) ** 2])
    return np.linalg.lstsq(X, np.log(d[ch].values), rcond=None)[0]
def resid(d, ch, c):
    X = np.column_stack([np.ones(len(d)), np.log(d.amp), np.log(d.amp) ** 2]); return np.log(d[ch].values) - X @ c
tr, ca, te = B[B.t0 < 2400], B[(B.t0 >= 2400) & (B.t0 < 3600)], B[(B.t0 >= 3600) & (B.t0 < 4320)]
c1, c0 = fit_law(tr, 'v1'), fit_law(tr, 'v0'); s1, s0 = resid(tr, 'v1', c1).std(), resid(tr, 'v0', c0).std()
def scores(d):
    z1, z0 = resid(d, 'v1', c1) / s1, resid(d, 'v0', c0) / s0
    return np.maximum(np.maximum(z1, z0), 0), np.maximum(np.abs(z1), np.abs(z0))
one_c, two_c = scores(ca); one_t, two_t = scores(te)
thr1, thr2 = np.quantile(one_c, 0.99), np.quantile(two_c, 0.99)
print(f'③ standby 60-72 min FPR (threshold = 99% of 40-60 min calibration): one-sided {np.mean(one_t > thr1):.3f}, two-sided {np.mean(two_t > thr2):.3f} (n={len(te)})')
one_a, _ = scores(B[(B.t0 >= 4320)]); print(f'   resume 72-77 min FPR one-sided {np.mean(one_a > thr1):.3f}')
