"""샘플링 주기 가설 점검: S10(가이드북대로 0.1 s 간격, 클럭 1 % 오차로 60 Hz가 0.6 Hz로 앨리어싱) vs S1k(실제 약 1 ms 간격, 버스트 = 약 50 ms 스냅샷).

1) 정상 긴 버스트에서 전류 주파수 fc와 하부진동 톤 f1을 '주기/샘플' 단위로 정밀 적합하고, 비 r = f1/fc의 부하 의존성을 본다.
   S1k라면 r = 3(1 − s), s = 유도전동기 슬립 → s = 1 − r/3.  S10(실제 fs ≈ 9.9 Hz)이라면 s ≈ (3 − r)/300.
2) 버스트 시작 시각(실시각)으로 부하 계열의 주기를 찾는다(Lomb–Scargle 1–30 s). 버스트 간격이 불규칙해 짧은 주기도 구분된다.
실행: python pilot_sampling_hypothesis.py --root <데이터셋/프레스_유압펌프_예지보전>
"""
import argparse, os, sys
import numpy as np, pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import spearmanr
from scipy.signal import lombscargle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)

def sse(f, v):
    k = np.arange(len(v))
    X = np.column_stack([np.ones(len(v)), np.cos(2 * np.pi * f * k), np.sin(2 * np.pi * f * k)])
    b = np.linalg.lstsq(X, v, rcond=None)[0]; r = v - X @ b
    return (r ** 2).sum(), np.hypot(b[1], b[2])

def refine(v, f0, w):
    res = minimize_scalar(lambda f: sse(f, v)[0], bounds=(f0 - w, f0 + w), method='bounded', options={'xatol': 1e-6})
    s, amp = sse(res.x, v)
    return res.x, amp, 1 - s / ((v - v.mean()) ** 2).sum()

rows = []
for b, d in N.groupby('burst'):
    if len(d) < 45: continue
    fc, ac, rc = refine(d.AI2_Current.values, 0.060, 0.005)      # 주기/샘플
    f1, a1, r1 = refine(d.AI1_Vibration.values, 0.179, 0.008)
    rows.append(dict(ts=d.ts.iloc[0], fc=fc, ac=ac, rc=rc, f1=f1, a1=a1, r1=r1))
R = pd.DataFrame(rows)
print('long bursts (>=45 rows):', len(R))
print('current frequency [cycles/sample]: median %.6f (IQR %.6f-%.6f)' % (R.fc.median(), R.fc.quantile(.25), R.fc.quantile(.75)))
G = R[R.r1 > 0.8].copy(); G['ratio'] = G.f1 / G.fc
print('AI1 tone well-fitted (R2>0.8): n=%d, ratio median %.4f' % (len(G), G.ratio.median()))
print('Spearman(load amplitude, ratio): rho=%.3f p=%.2e' % spearmanr(G.ac, G.ratio))
for lo, hi in [(100, 160), (160, 220), (220, 300)]:
    g = G[(G.ac >= lo) & (G.ac < hi)]
    if len(g):
        r = g.ratio.median()
        print(f'  load amp {lo}-{hi}: n={len(g):3d} ratio {r:.4f} -> slip if S1k {100*(1-r/3):.2f} % | if S10 (fs~9.9 Hz) {100*(3-r)/300:.4f} %')
# 2) 부하 계열의 실시각 주기
Nb = N.groupby('burst').agg(t0=('ts', 'first'), n=('idx', 'size'))
amp = []
for b, d in N.groupby('burst'):
    x = d.AI2_Current.values
    amp.append(np.sqrt(2) * x.std() if len(x) >= 10 else np.nan)
Nb['amp'] = amp
S = Nb[(Nb.t0 < 3600) & Nb.amp.notna()]
y = S.amp.values - S.amp.mean(); t = S.t0.values
per = np.linspace(1.0, 30, 60000); pw = lombscargle(t, y, 2 * np.pi / per, normalize=True)
order = np.argsort(pw)[::-1]; top = []
for i in order:
    if all(abs(per[i] - per[j]) > 0.15 for j in top): top.append(i)
    if len(top) == 6: break
print('load periodogram (burst start times, 1-30 s) top periods:', [(round(per[i], 3), round(pw[i], 3)) for i in top])
rng = np.random.default_rng(0)
null = [lombscargle(t, rng.permutation(y), 2 * np.pi / per, normalize=True).max() for _ in range(100)]
print('permutation null max power p95: %.3f' % np.percentile(null, 95))
# 3) 어떤 피크가 표본 시각 패턴이 만든 앨리어스인지: 실제 버스트 시각에서 순수 주기 신호를 표본화해 본다
def top_peaks(y, k=5):
    p = lombscargle(t, y - y.mean(), 2 * np.pi / per, normalize=True); o = np.argsort(p)[::-1]; out = []
    for i in o:
        if all(abs(per[i] - per[j]) > 0.15 for j in out): out.append(i)
        if len(out) == k: break
    return [(round(per[i], 2), round(p[i], 3)) for i in out]
for P in (2.90, 19.6):
    print(f'spectral window check: pure square wave with period {P} s sampled at the real burst times ->', top_peaks(np.sign(np.sin(2 * np.pi * t / P + 0.3))))
# 4) 버스트 안 부하 안정성(S10이면 2.9 s 부하 주기가 5 s 버스트 안에서 진폭 변화로 보여야 한다)
print('within-burst current sine-fit R2 (>=45 rows): min %.4f' % R.rc.min())
