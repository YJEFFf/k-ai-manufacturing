"""01 문서 4–7절 수치 재현: 상태별 진동표, 버스트 안 부하 안정성, 음성 대조, 가이드북 분할 매핑, 이상 버스트표.

실행: python pilot_probes.py --root <데이터셋/프레스_유압펌프_예지보전>  (eda_facts.py 먼저 실행해 burst_features.csv 생성)
"""
import argparse, sys, os
import numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load
from fastsine import sinefit
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)
F = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'burst_features.csv'))
Nf = F[F.file == 0].copy()
Nf['state'] = np.where(Nf.ts >= 3600, np.where(Nf.ts < 4320, 'standby_60_72', 'resume_72_77'),
                       np.where(Nf.i_amp > 180, 'loaded', np.where(Nf.i_amp < 130, 'idle', 'mid')))
print('## 상태별 진동표 (정상, 10행 이상 버스트)')
g = Nf.groupby('state')
print(pd.DataFrame({'n': g.size(), 'v0_rms_med': g.v0_rms.median(), 'v1_rms_med': g.v1_rms.median(),
                    'v1_f_med': g.v1_f.median(), 'v1_r2_med': g.v1_r2.median(), 'c01_med': g.c01.median()}).round(3).to_string())
print('\n## 버스트 안 부하 안정성 (40행 이상, 앞/뒤 절반 사인 진폭 차)')
rows = []
for b, d in N.groupby('burst'):
    if len(d) < 40: continue
    x = d.AI2_Current.values; h = len(x) // 2
    rows.append(dict(a=sinefit(None, x)['amp'], d=sinefit(None, x[h:])['amp'] - sinefit(None, x[:h])['amp']))
R = pd.DataFrame(rows)
print('bursts', len(R), '|d| p50/p95/max', np.percentile(R.d.abs(), [50, 95, 100]).round(1))
s = Nf[Nf.ts < 3600].sort_values('ts').i_amp.values; s = (s - s.mean()) / s.std()
print('burst amplitude ACF lag1 (0-60 min):', round(np.corrcoef(s[:-1], s[1:])[0, 1], 3))
print('\n## 음성 대조 (GradientBoosting, GroupKFold 5, 5분 블록)')
feat = [c for c in F.columns if (c.split('_')[0] in ('v0', 'v1', 'i') or c == 'c01') and c != 'i_off']
def auc(lbl, grp, X):
    p = cross_val_predict(GradientBoostingClassifier(random_state=0), X, lbl, cv=GroupKFold(5), groups=grp, method='predict_proba')[:, 1]
    return roc_auc_score(lbl, p)
print('NC1 normal first half vs second half: %.3f' % auc((Nf.ts >= Nf.ts.median()).astype(int).values, (Nf.ts // 300).astype(int).values, Nf[feat].values))
sub = Nf[Nf.ts < 4320]
print('NC2 normal 0-60 vs standby 60-72: %.3f' % auc((sub.ts >= 3600).astype(int).values, (sub.ts // 300).astype(int).values, sub[feat].values))
print('normal vs abnormal: %.3f' % auc(F.file.values, np.where(F.file == 0, (F.ts // 300).astype(int), 100 + (F.burst % 5)), F[feat].values))
print('\n## 가이드북 분할 매핑')
def cross(df, seq=20, ahead=100):
    b = df.burst.values; n = len(df) - seq - ahead
    return sum(b[i] != b[i + seq - 1] for i in range(n)), n
print('train windows crossing gaps', cross(N.iloc[:15000]), '| test-normal', cross(N.iloc[15000:]), '| abnormal', cross(A))
print('valid normal', N.TimeStamp[15000], '..', N.TimeStamp[15899], '| test normal', N.TimeStamp[15880], '..', N.TimeStamp[19898])
print('valid abnormal', A.TimeStamp[0], '..', A.TimeStamp[319], '| test abnormal', A.TimeStamp[300], '..', A.TimeStamp[498])
print('\n## 이상 버스트표')
rows = []
for b, d in A.groupby('burst'):
    rows.append(dict(burst=b, t=d.TimeStamp.iloc[0][11:19], n=len(d), v0_max=d.AI0_Vibration.abs().max(), v1_max=d.AI1_Vibration.abs().max(),
                     v0_mean=d.AI0_Vibration.mean(), i_min=d.AI2_Current.min(), i_max=d.AI2_Current.max()))
print(pd.DataFrame(rows).round(2).to_string(index=False))

print('\n## 대기 구간 오경보 원인 (0–50분 학습 MCD, 99 % 임계값)')
from sklearn.covariance import MinCovDet
featm = ['i_amp', 'i_rres', 'v0_rms', 'v1_rms', 'v0_ac1', 'v1_ac1', 'c01', 'v0_kurt', 'v1_kurt', 'v0_maxabs', 'v1_maxabs']
tr = Nf[Nf.ts < 3000]; sb = Nf[(Nf.ts >= 3600) & (Nf.ts < 4320)]
mu, sd = tr[featm].mean(), tr[featm].std(); Zf = lambda d: (d[featm] - mu) / sd
mcd = MinCovDet(random_state=0).fit(Zf(tr)); thr = np.quantile(mcd.mahalanobis(Zf(tr)), 0.99)
flag = sb[mcd.mahalanobis(Zf(sb)) > thr]
zz = (Zf(flag).values - mcd.location_) / np.sqrt(np.diag(mcd.covariance_))
print('flagged', len(flag), 'of', len(sb)); print(pd.Series(np.median(zz, axis=0), index=featm).round(2).sort_values().to_string())

print('\n## 파일별 숫자 형식·양자화 (원본 문자열 기준)')
import csv, collections
sub = os.path.join(a.root, 'data', '3_소성가공_예지보전')
for fn in ['press_data_normal.csv', 'outlier_data.csv']:
    rows = list(csv.reader(open(os.path.join(sub, fn))))[1:]
    def ndec(s):
        return -1 if 'e' in s.lower() else (len(s.split('.')[1]) if '.' in s else 0)
    for k, nm in [(2, 'AI0'), (3, 'AI1')]:
        print(fn, nm, 'decimals', dict(sorted(collections.Counter(ndec(r[k]) for r in rows).items())))
    I = np.array([float(r[4]) for r in rows]); qs = 1e7 / 2 ** 23
    print(fn, 'AI2 on 1e7/2^23 lattice share %.3f, unique %d/%d' % (np.mean(np.abs(I / qs - np.round(I / qs)) < 1e-3), len(set(I)), len(I)))

print('\n## 부하 교대 주기 (0–60분 버스트 진폭, Lomb–Scargle, 6–200초)')
from scipy.signal import lombscargle
Ns = Nf[Nf.ts < 3600].sort_values('ts')
tt = Ns.ts.values + Ns.n.values * 0.05; yy = Ns.i_amp.values - Ns.i_amp.mean()
per = np.linspace(6, 200, 20000); ww = 2 * np.pi / per
pw = lombscargle(tt, yy, ww, normalize=True)
order = np.argsort(pw)[::-1]; top = []
for i in order:
    if all(abs(per[i] - per[j]) > 0.5 for j in top): top.append(i)
    if len(top) == 4: break
print('top periods (s, power):', [(round(per[i], 2), round(pw[i], 3)) for i in top])
rng = np.random.default_rng(0)
print('permutation null max power p95: %.3f' % np.percentile([lombscargle(tt, rng.permutation(yy), ww, normalize=True).max() for _ in range(200)], 95))

print('\n## 부하 매칭 비교 (10행 이상 이상 버스트 vs 전류 표준편차 ±15 % 정상 버스트의 상부진동 표준편차 최댓값)')
def bstd(df):
    g = df.groupby('burst')
    return pd.DataFrame({'n': g.size(), 't': g.TimeStamp.first(), 'v0s': g.AI0_Vibration.std(ddof=0), 'is': g.AI2_Current.std(ddof=0)})
Nb = bstd(N); Ab = bstd(A); Nl = Nb[Nb.n >= 10]; Al = Ab[Ab.n >= 10]
mrows = []
for b, r in Al.iterrows():
    m = Nl[(Nl['is'] >= 0.85 * r['is']) & (Nl['is'] <= 1.15 * r['is'])]
    mrows.append(dict(burst_1based=b + 1, t=r.t[11:19], n=int(r.n), i_std=round(r['is'], 1), v0s=round(r.v0s, 3), n_match=len(m),
                      ratio=round(r.v0s / m.v0s.max(), 2) if len(m) else np.nan))
M = pd.DataFrame(mrows); print(M.to_string(index=False))
ok = M.dropna()
print('exceed matched max: %d/%d matchable (%d long); median ratio among exceeders %.2f; normal long-burst current std min %.1f'
      % ((ok.ratio > 1).sum(), len(ok), len(M), ok[ok.ratio > 1].ratio.median(), Nl['is'].min()))

print('\n## 부하 대리변수 점검: 이상 버스트의 max|I|(진폭 하한)로 정상 선형 법칙을 외삽했을 때의 진동 배율')
rows = []
for b, d in N.groupby('burst'):
    if len(d) < 10: continue
    x = d.AI2_Current.values
    rows.append(dict(amp=sinefit(None, x)['amp'], v0=np.sqrt(np.mean(d.AI0_Vibration ** 2)), v1=np.sqrt(np.mean(d.AI1_Vibration ** 2)), istd=x.std()))
Rn = pd.DataFrame(rows); c0 = np.polyfit(Rn.amp, Rn.v0, 1); c1 = np.polyfit(Rn.amp, Rn.v1, 1)
print('normal std/amp median %.3f; amp range %.0f-%.0f' % ((Rn.istd / Rn.amp).median(), Rn.amp.min(), Rn.amp.max()))
rows = []
for b, d in A.groupby('burst'):
    x = d.AI2_Current.values; lb = np.abs(x).max()
    v0 = np.sqrt(np.mean(d.AI0_Vibration ** 2)); v1 = np.sqrt(np.mean(d.AI1_Vibration ** 2))
    rows.append(dict(burst_1based=b + 1, n=len(d), imax=round(lb), v0_ratio=round(v0 / np.polyval(c0, lb), 2), v1_ratio=round(v1 / np.polyval(c1, lb), 2)))
Ea = pd.DataFrame(rows); print(Ea.to_string(index=False))
L = Ea[Ea.n >= 10]
print('bursts with max|I| > normal max amp: %d/21 | long bursts v0_ratio>1.5: %d/%d (median %.2f) | v1_ratio>1.5: %d/%d (median %.2f)'
      % ((Ea.imax > Rn.amp.max()).sum(), (L.v0_ratio > 1.5).sum(), len(L), L.v0_ratio.median(), (L.v1_ratio > 1.5).sum(), len(L), L.v1_ratio.median()))
