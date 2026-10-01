"""이상 파일 구조 점검(샘플 단위): 고정 0.0600 주기/샘플 사인의 설명력, 진동의 우세 주파수와 상·하부 위상 관계.

실행: python pilot_abnormal_structure.py --root <데이터셋/프레스_유압펌프_예지보전>
"""
import argparse, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)

def fixed_fit(x, f=0.0600):
    k = np.arange(len(x)); X = np.column_stack([np.ones(len(x)), np.cos(2 * np.pi * f * k), np.sin(2 * np.pi * f * k)])
    b = np.linalg.lstsq(X, x, rcond=None)[0]; r = x - X @ b
    return np.hypot(b[1], b[2]), 1 - (r ** 2).sum() / ((x - x.mean()) ** 2).sum(), b[0]

def dom_freq(x):
    x = x - x.mean(); n = 512; F = np.abs(np.fft.rfft(x * np.hanning(len(x)), n)); fr = np.fft.rfftfreq(n, 1.0)
    F[0] = 0; return fr[np.argmax(F)]

for nm, df in [('normal', N), ('abnormal', A)]:
    rows = []
    for b, d in df.groupby('burst'):
        if len(d) < 10: continue
        amp, r2, off = fixed_fit(d.AI2_Current.values)
        v0, v1 = d.AI0_Vibration.values, d.AI1_Vibration.values
        rows.append(dict(amp=amp, r2=r2, off=off, f0=dom_freq(v0), f1=dom_freq(v1), c01=np.corrcoef(v0, v1)[0, 1]))
    R = pd.DataFrame(rows)
    print(f'== {nm}: bursts(>=10 rows)={len(R)}')
    print('  current fixed 0.0600 cyc/sample fit: amplitude median %.1f, R2 median %.3f (min %.3f, max %.3f), |offset| median %.1f'
          % (R.amp.median(), R.r2.median(), R.r2.min(), R.r2.max(), R.off.abs().median()))
    print('  dominant vib freq [cyc/sample] AI0 median %.3f, AI1 median %.3f; corr(AI0,AI1) median %.2f, share negative %.2f'
          % (R.f0.median(), R.f1.median(), R.c01.median(), (R.c01 < 0).mean()))
