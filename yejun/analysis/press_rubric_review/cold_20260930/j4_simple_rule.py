"""J4 위원 독립 점검 4: README의 '거의 학습하지 않는 단순 규칙'(행 F1 0.890·0.900, 이상 21/21, 정상 알림 A 0/120·B 2/180)을
팀 코드 없이 문장 정의대로 다시 만든다.

정의(README 결과 절): 전류의 고정 0.6 Hz 공진 잔차 |x_t - 2cos(2π·0.06)·x_{t-1} + x_{t-2}|(기록 안, 위치 2부터)와
두 진동의 절댓값을 각각 정상 학습 구간 최댓값으로 나눈 값의 최댓값. 보정은 v2와 같은 기록 최대 점수 conformal(α=1%).
결과: j4_simple_rule.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(sys.argv[1])
S = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
nrm = pd.read_csv(root / "press_data_normal.csv")
ab = pd.read_csv(root / "outlier_data.csv")


def records(df):
    t = pd.to_datetime(df.TimeStamp).astype("int64").to_numpy()
    return np.cumsum(np.r_[False, np.abs(np.diff(t) - 100_000_000) > 20_000_000])


def matched(df, on):
    out = df[S].astype(float).copy()
    if on:
        for c in S[:2]:
            out[c] = np.round(out[c] / 1e-4) * 1e-4
        out[S[2]] = np.round(out[S[2]] / 1.1920929) * 1.1920929
    return out


phi1 = 2 * np.cos(2 * np.pi * 0.6 * 0.1)


def parts(df, seg, on):
    X = matched(df, on)
    x = X[S[2]].to_numpy()
    r = np.full(len(x), np.nan)
    i = np.arange(2, len(x))
    i = i[seg[i] == seg[i - 2]]
    r[i] = np.abs(x[i] - phi1 * x[i - 1] + x[i - 2])
    return np.column_stack([np.abs(X[S[0]].to_numpy()), np.abs(X[S[1]].to_numpy()), r])


sn, sa = records(nrm), records(ab)
res = {}
for on in (True, False):
    key = "matched" if on else "raw"
    res[key] = {}
    for split, (tr_end, cal_end) in {"A": (360, 480), "B": (300, 420)}.items():
        Pn, Pa = parts(nrm, sn, on), parts(ab, sa, on)
        scale = np.nanmax(Pn[sn < tr_end], axis=0)
        score_n = np.nanmax(Pn / scale, axis=1)
        score_a = np.nanmax(Pa / scale, axis=1)
        cal = (sn >= tr_end) & (sn < cal_end)
        ref = np.sort(pd.Series(score_n[cal]).groupby(sn[cal]).max().to_numpy())
        p = lambda s: (len(ref) - np.searchsorted(ref, s, side="left") + 1) / (len(ref) + 1)
        te = sn >= cal_end
        an, aa = p(score_n[te]) <= 0.01, p(score_a) <= 0.01
        tp, fn, fp = int(aa.sum()), int((~aa).sum()), int(an.sum())
        res[key][split] = dict(tp=tp, fn=fn, fp=fp, f1=round(2 * tp / (2 * tp + fn + fp), 4),
                               normal_records_alerted=f"{int(pd.Series(an).groupby(sn[te]).any().sum())}/{len(np.unique(sn[te]))}",
                               abnormal_records_detected=f"{int(pd.Series(aa).groupby(sa).any().sum())}/21",
                               learned_scales=[round(float(v), 4) for v in scale])
Path(__file__).with_name("j4_simple_rule.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
