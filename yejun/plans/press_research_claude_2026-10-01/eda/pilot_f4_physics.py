"""파일럿: F4(토크 맥동 → 전류 변조)를 연속시간에서 만들고 같은 샘플링으로 다시 찍는 방식의 타당성 점검.

정상 버스트마다 0.600 Hz 사인을 적합해 진폭 A·위상을 얻고, 60 Hz 반송파를 변조지수 m으로 진폭변조한 뒤
표본 주기 Ts(101.01 ms 또는 99.01 ms; 둘 다 0.600 Hz 앨리어스를 만든다)로 다시 표본화한다. 원래 잔차는 그대로 더한다.
"""
import argparse, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eda_facts import load
from fastsine import sinefit
ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)
rng = np.random.default_rng(1)
FE = 60.0
rows = []
bursts = [d for _, d in N.groupby('burst') if len(d) >= 30]
for Ts in (6 / 59.4, 6 / 60.6):           # 0.10101 s, 0.09901 s
    for m in (0.0, 0.02, 0.05, 0.1, 0.2):
        for fp_band in ('pump_mesh_265_415Hz', 'slow_0.5_5Hz'):
            res = []
            for d in bursts[:200]:
                x = d.AI2_Current.values; n = len(x); k = np.arange(n)
                s = sinefit(None, x)
                # 원래 표본의 0.600 Hz 성분 → 연속시간 60 Hz 반송파 위상으로 환산 (표본 k에서 같은 값이 나오도록)
                t = k * Ts
                # 겉보기 위상: phi_app(k) = 2π f_app (0.1 k) + φ0 ; 실제 위상 2π FE t + ψ 가 표본점에서 같은 값(2π 모듈로)이 되도록 ψ 선택
                f_app = s['f']
                M = np.column_stack([np.sin(2*np.pi*f_app*0.1*k), np.cos(2*np.pi*f_app*0.1*k), np.ones(n)])
                c, *_ = np.linalg.lstsq(M, x, rcond=None)
                base = M @ c; resid = x - base
                amp = np.hypot(c[0], c[1]); phi0 = np.arctan2(c[1], c[0])
                carrier_phase = 2*np.pi*f_app*0.1*k + phi0   # 표본점에서의 반송파 위상(앨리어스와 동일)
                fp = rng.uniform(265, 415) if fp_band.startswith('pump') else rng.uniform(0.5, 5)
                th = rng.uniform(0, 2*np.pi)
                env = 1 + m*np.sin(2*np.pi*fp*t + th)          # 연속시간 변조를 실제 표본 시각 t에서 평가
                x2 = amp*env*np.sin(carrier_phase) + c[2] + resid
                s2 = sinefit(None, x2)
                res.append((s['rres'], s2['rres'], s2['r2'], amp))
            r = np.array(res)
            rows.append(dict(Ts_ms=round(Ts*1000, 2), m=m, band=fp_band, rres_before=np.median(r[:, 0]).round(2),
                             rres_after_med=np.median(r[:, 1]).round(2), rres_after_p10=np.percentile(r[:, 1], 10).round(2),
                             r2_after_med=np.median(r[:, 2]).round(4), share_above_normal_max=(r[:, 1] > 8.29).mean().round(2)))
print(pd.DataFrame(rows).to_string(index=False))
