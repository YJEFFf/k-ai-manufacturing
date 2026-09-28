"""review4: 순수 0.6 Hz 사인(무작위 위상)을 N행(0.1초 간격) 뽑을 때 |평균| > SD(ddof=1)가 될 확률. 정상 파일의 길이 분포와 함께 본다."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); import review4_indep as I
ph = np.linspace(0, 2 * np.pi, 3600, endpoint=False)
for f in (0.6, 0.22):
    out = {}
    for N in (10, 12, 15, 17, 20, 25, 30, 50):
        t = np.arange(N) * 0.1
        x = np.sin(2 * np.pi * f * t[None, :] + ph[:, None])
        out[N] = round(float((np.abs(x.mean(1)) > x.std(1, ddof=1)).mean()), 3)
    print(f"f={f} Hz  P(|평균|>SD) by N:", out)
n, a = I.load_raw()
for k, fr in (("normal", n), ("abnormal", a)):
    L = pd.Series(I.records(fr.TimeStamp)).value_counts()
    print(k, "길이 10~16 기록", int(((L >= 10) & (L < 17)).sum()), "· 길이≥17", int((L >= 17).sum()), "· 길이 분포", L.describe()[["min", "50%", "max"]].to_dict())
