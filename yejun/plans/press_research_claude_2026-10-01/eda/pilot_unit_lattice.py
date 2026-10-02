"""단위·격자 지문 점검: 두 파일의 전류·진동이 어떤 ADC 계수 격자에 올라 있는가, 회전 톤은 이상 파일에도 있는가.

LSB = 10 V / 2^23 = 1.1920929e-6 V (±10 V 24비트 입력 가정). 후보 격자:
  정상 전류 LSB×100 = 1.1920929e-4, 이상 전류 LSB×1e6 = 1.1920929, 이상 진동 LSB/0.1080, LSB/0.1030 (감도 mV/g 가정).
실행: python pilot_unit_lattice.py --root <데이터셋/프레스_유압펌프_예지보전>
"""
import argparse, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)
LSB = 10.0 / 2 ** 23

def lattice_share(x, step, tol=0.05, corr=1.0):
    k = x / (step * corr)
    return float(np.mean(np.abs(k - np.round(k)) < tol)), int(np.round(k).min()), int(np.round(k).max())

rng = np.random.default_rng(0)
for nm, df in [('normal', N), ('abnormal', A)]:
    for col, steps in [('AI2_Current', {'LSB*1e2': LSB * 1e2, 'LSB*1e6': LSB * 1e6}),
                       ('AI0_Vibration', {'LSB/0.1080': LSB / 0.1080, 'LSB/0.1030': LSB / 0.1030}),
                       ('AI1_Vibration', {'LSB/0.1080': LSB / 0.1080, 'LSB/0.1030': LSB / 0.1030})]:
        x = df[col].values
        for sn, st in steps.items():
            sh, kmin, kmax = lattice_share(x, st)
            sh32, _, _ = lattice_share(x, st, corr=1 + 2 ** -23)      # float32 반올림 보정 시험
            ctrl, _, _ = lattice_share(x + rng.uniform(-st / 2, st / 2, len(x)), st)  # 무작위 대조
            print(f'{nm:8s} {col:13s} step {sn:10s}: share |k-round(k)|<0.05 = {sh:.3f} (float32-corr {sh32:.3f}; random ctrl {ctrl:.3f}); counts {kmin}..{kmax}')

# 회전 톤: 상부 약 0.355–0.365, 하부 약 0.175–0.185 주기/샘플 대역 최대 진폭(최소제곱)
def tone_amp(x, lo, hi):
    k = np.arange(len(x)); best = 0.0
    for f in np.linspace(lo, hi, 201):
        X = np.column_stack([np.ones(len(x)), np.cos(2*np.pi*f*k), np.sin(2*np.pi*f*k)])
        b = np.linalg.lstsq(X, x, rcond=None)[0]; best = max(best, np.hypot(b[1], b[2]))
    return best
rows = []
for nm, df in [('normal', N), ('abnormal', A)]:
    for b, d in df.groupby('burst'):
        if len(d) < 10: continue
        rows.append(dict(file=nm, t=d.TimeStamp.iloc[0][11:19], up=tone_amp(d.AI0_Vibration.values, 0.350, 0.370),
                         lo=tone_amp(d.AI1_Vibration.values, 0.175, 0.185), rms0=np.sqrt(np.mean(d.AI0_Vibration**2))))
T = pd.DataFrame(rows)
n = T[T.file == 'normal']
print('normal upper-tone amp min %.4f p1 %.4f median %.4f | lower-tone amp p1 %.4f median %.4f'
      % (n.up.min(), n.up.quantile(.01), n.up.median(), n.lo.quantile(.01), n.lo.median()))
q = T[(T.file == 'abnormal') & (T.t.isin(['10:51:31', '10:53:42', '10:53:52']))]
print('quiet abnormal bursts:'); print(q.round(4).to_string(index=False))
