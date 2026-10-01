"""파일럿: 합성 고장 주입으로 탐지기 간 차이가 드러나는지 확인 (계획 근거용, 최종 실험 아님)."""
import sys, numpy as np, pandas as pd, warnings
warnings.filterwarnings('ignore')
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load, COLS
from fastsine import sinefit
from sklearn.covariance import MinCovDet
from sklearn.ensemble import IsolationForest
from scipy import stats
import argparse
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); ROOT = ap.parse_args().root
rng = np.random.default_rng(0)
N, A = load(ROOT)
full = N.groupby('burst').filter(lambda d: len(d) >= 30)
tr_b = full[full.ts < 3000].burst.unique(); te_b = full[full.ts >= 3000].burst.unique()

def feats_of(d):
    t = np.arange(len(d)) * 0.1; r = {}
    for c, k in zip(COLS, ['v0', 'v1', 'i']):
        x = d[c].values; s = sinefit(t, x)
        r[f'{k}_amp'] = s['amp']; r[f'{k}_rres'] = s['rres']
        r[f'{k}_rms'] = np.sqrt(np.mean(x ** 2)); r[f'{k}_maxabs'] = np.abs(x).max()
        r[f'{k}_kurt'] = stats.kurtosis(x); r[f'{k}_ac1'] = np.corrcoef(x[:-1], x[1:])[0, 1]
    r['c01'] = np.corrcoef(d.AI0_Vibration, d.AI1_Vibration)[0, 1]
    return r

def inject(d, fam, sev):
    d = d.copy(); n = len(d); t = np.arange(n) * 0.1
    if fam == 'vib_gain':          # 부하와 무관한 진동 증가 (마모·헐거움 가정)
        d[COLS[0]] *= (1 + sev); d[COLS[1]] *= (1 + sev)
    elif fam == 'lowfreq_osc':     # 저주파 흔들림 (실제 이상 구간 형태와 비슷한 계열)
        f = rng.uniform(0.7, 1.3); ph = rng.uniform(0, 2 * np.pi)
        d[COLS[0]] += sev * np.sin(2 * np.pi * f * t + ph); d[COLS[1]] += 0.5 * sev * np.sin(2 * np.pi * f * t + ph + 0.5)
    elif fam == 'current_ripple':  # 토크 맥동 → 전류 파형 왜곡 (진폭 비례 잡음)
        amp = np.abs(d[COLS[2]]).max()
        d[COLS[2]] += sev * amp * rng.standard_normal(n)
    elif fam == 'normal_load_up':  # 정상 운전 변화: 부하 증가와 그에 맞는 하부진동 증가 (경보가 나면 오경보)
        d[COLS[2]] *= (1 + sev); d[COLS[1]] *= (1 + 1.5 * sev)
    return d

tr = pd.DataFrame([feats_of(full[full.burst == b]) for b in tr_b])
te = pd.DataFrame([feats_of(full[full.burst == b]) for b in te_b])
feat = list(tr.columns)
mu, sd = tr.mean(), tr.std(); Z = lambda X: (X[feat] - mu) / sd
mcd = MinCovDet(random_state=0).fit(Z(tr)); t_m = np.quantile(mcd.mahalanobis(Z(tr)), 0.99)
iso = IsolationForest(n_estimators=300, random_state=0).fit(Z(tr)); t_i = np.quantile(-iso.score_samples(Z(tr)), 0.99)
cf = np.polyfit(tr.i_amp, tr.v1_rms, 2); rs = np.std(tr.v1_rms - np.polyval(cf, tr.i_amp))
cf0 = np.polyfit(tr.i_amp, tr.v0_rms, 2); rs0 = np.std(tr.v0_rms - np.polyval(cf0, tr.i_amp))
h_rres = np.quantile(tr.i_rres, 0.995)
t_max0 = np.quantile(tr.v0_maxabs, 0.99)
def detectors(X):
    phys = (((X.v1_rms - np.polyval(cf, X.i_amp.clip(upper=280))) / rs > 4) |
            ((X.v0_rms - np.polyval(cf0, X.i_amp.clip(upper=280))) / rs0 > 4) | (X.i_rres > h_rres))
    return dict(MCD=(mcd.mahalanobis(Z(X)) > t_m), IForest=(-iso.score_samples(Z(X)) > t_i),
                physics=phys.values, maxAI0=(X.v0_maxabs > t_max0).values)
base = detectors(te)
print('held-out normal (50-77 min) alarm rate:', {k: round(float(np.mean(v)), 3) for k, v in base.items()}, 'n=', len(te))
rows = []
for fam, sevs in [('vib_gain', [0.25, 0.5, 1.0, 2.0]), ('lowfreq_osc', [0.05, 0.1, 0.2, 0.4]),
                  ('current_ripple', [0.02, 0.05, 0.1, 0.2]), ('normal_load_up', [0.1, 0.2])]:
    for sev in sevs:
        X = pd.DataFrame([feats_of(inject(full[full.burst == b], fam, sev)) for b in te_b])
        det = detectors(X)
        rows.append(dict(family=fam, severity=sev, **{k: round(float(np.mean(v)), 2) for k, v in det.items()}))
print(pd.DataFrame(rows).to_string(index=False))
