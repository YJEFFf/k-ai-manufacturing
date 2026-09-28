"""review4: 60.6 Hz·2.4 ms로 흔든 정상 기록이 이상 기록의 다른 파형 지표도 닮는지(주장 3·4의 '설명될 수 있다' 점검).

R²만 맞추도록 고른 흔들림(2.4 ms)이 적합 주파수·기록 안 lag-1·잔차 lag-1·|평균|/SD도 재현하는지 본다. 팀 함수 미사용.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import review4_indep as I  # noqa: E402

pd.set_option("display.width", 220)
rng = np.random.default_rng(7)
n, a = I.load_raw()
rn, ra = I.records(n.TimeStamp), I.records(a.TimeStamp)


def feats(x):
    x = np.asarray(x, float)
    f, r2, fitted = I.best_sine(x)
    d = x - x.mean()
    lag = float(np.corrcoef(d[:-1], d[1:])[0, 1])
    res = x - fitted
    rl = float(np.corrcoef(res[:-1], res[1:])[0, 1])
    return dict(n=len(x), f=f, r2=r2, lag1=lag, res_lag1=rl, near06=abs(f - 0.6) <= 0.05, off=abs(x.mean()) > x.std(ddof=1))


def table(recs):
    t = pd.DataFrame([feats(x) for x in recs])
    return dict(records=len(t), r2_med=round(t.r2.median(), 3), f_med=round(t.f.median(), 3), f_near06=f"{t.near06.mean():.0%}",
                lag1_med=round(t.lag1.median(), 3), res_lag1_med=round(t.res_lag1.median(), 3), mean_gt_sd=f"{t.off.mean():.0%}")


def split_records(frame, rec, min_len, first=None):
    x = frame.AI2_Current.to_numpy(float)
    out = []
    for s in np.unique(rec):
        if first is not None and s < first:
            continue
        idx = np.flatnonzero(rec == s)
        if len(idx) >= min_len:
            out.append(x[idx])
    return out


def jitter(recs, fhz, sigma, reps=5):
    out = []
    for _ in range(reps):
        for x in recs:
            f = I.best_sine(x)[0]
            coef, resid = I.ls_tone(x, f)
            ph = 2 * np.pi * f * np.arange(len(x)) * .1 + 2 * np.pi * fhz * rng.normal(0, sigma / 1e3, len(x))
            out.append(coef[0] * np.cos(ph) + coef[1] * np.sin(ph) + coef[2] + resid)
    return out


rows = {}
for ml in (10, 17):
    rows[f"이상(길이≥{ml})"] = table(split_records(a, ra, ml))
normA = split_records(n, rn, 17, first=480)
rows["정상 A 평가(길이≥17)"] = table(normA)
for sig in (1.0, 2.4, 3.5):
    rows[f"정상 A 평가 + 60.6 Hz {sig} ms"] = table(jitter(normA, 60.6, sig))
# 대안: 표본화 주기 편차(느린 위상 표류) — 이상 기록의 낮은 적합 주파수·기록 사이 수준 연속성과 비교용
print(pd.DataFrame(rows).T.to_string())
