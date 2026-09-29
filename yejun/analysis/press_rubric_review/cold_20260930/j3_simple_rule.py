"""J3: README의 '거의 학습하지 않는 단순 규칙'을 문서 설명(고정 0.6 Hz 공진 잔차 |x_t − 2cos(2π·0.6·0.1)x_{t−1} + x_{t−2}|, 두 진동 절댓값,
각각 정상 학습 최댓값으로 나눈 값의 최댓값, 보정 기록 최대 conformal)대로 독립 구현해 A·B α1% 결과를 잰다(팀 코드 import 없음)."""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
D = Path(sys.argv[1]); S = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
def seg(ts):
    t = pd.to_datetime(ts).astype("int64").to_numpy(); return np.cumsum(np.r_[False, np.abs(np.diff(t) - 100_000_000) > 20_000_000])
def q(df):
    o = df.copy()
    for c in S[:2]: o[c] = np.round(o[c] / 1e-4) * 1e-4
    o[S[2]] = np.round(o[S[2]] / 1.1920929) * 1.1920929
    return o
C = 2 * np.cos(2 * np.pi * .6 * .1)
def feats(df):
    x = q(df); sg = seg(x.TimeStamp); X = x[S].to_numpy(float); cur = X[:, 2]
    r = np.full(len(cur), np.nan); idx = np.arange(2, len(cur)); idx = idx[sg[idx] == sg[idx - 2]]
    r[idx] = np.abs(cur[idx] - C * cur[idx - 1] + cur[idx - 2])
    return np.column_stack([np.abs(X[:, 0]), np.abs(X[:, 1]), r]), sg
N = pd.read_csv(D / "press_data_normal.csv"); A = pd.read_csv(D / "outlier_data.csv"); sN = seg(N.TimeStamp)
out = {}
for sid, (te, ce) in {"A": (360, 480), "B": (300, 420)}.items():
    tr, ca, ts = (N[m].reset_index(drop=True) for m in (sN < te, (sN >= te) & (sN < ce), sN >= ce))
    Ft, _ = feats(tr); mx = np.nanmax(Ft, axis=0)
    def score(df):
        F, sg = feats(df); return np.nanmax(F / mx, axis=1), sg
    sc, gc = score(ca); st, gt = score(ts); sa, ga = score(A)
    thr = pd.Series(sc).groupby(gc).max().max()      # α1%, n=120: 경보 ⇔ 점수 > 보정 기록 최대의 최댓값
    an, aa = st > thr, sa > thr
    tp, fp = int(aa.sum()), int(an.sum()); fn = 600 - tp
    out[sid] = dict(threshold=round(float(thr), 4), tp=tp, fp=fp, fn=fn, f1=round(2 * tp / (2 * tp + fp + fn), 4),
                    normal_records_alerted=int(pd.Series(an).groupby(gt).max().sum()), abnormal_records_detected=int(pd.Series(aa).groupby(ga).max().sum()))
print(json.dumps(out, ensure_ascii=False)); Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
