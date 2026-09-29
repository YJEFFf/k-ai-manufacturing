"""J4 위원 독립 점검 2: 팀 코드를 import하지 않고 README·코드 설명대로 v2 점수를 새로 구현해 주 지표를 다시 계산한다.

구현(README '모델' 표와 press/scores.py·press_guard/model.py의 정의를 읽고 새로 작성):
- 기록구간: 이웃 행 간격이 0.1초 ± 20 ms 밖이면 새 구간. 분할 A 학습 0~359/보정 360~479/평가 480~599, B 0~299/300~419/420~599.
- matched: 진동 1e-4 반올림, 전류 1.1920929 격자 반올림. 표준화는 정상 학습 행 평균·SD(ddof=0).
- 성분: 크기 max|z|, 전류 사인 1-R^2(0~5 Hz 0.005 격자, 사인·코사인·상수, 위치 5~6은 6행 창, 7부터 8행 창), AR(2) 절편 포함 절대 잔차(위치 2부터).
- 꼬리 변환 g: 학습 참조의 q95 이하에서는 -log10((#ref>=s + 1)/(n+1)), 초과분은 지수 꼬리(평균 초과량 beta)로 선형 연장.
- 결합 fmax, 보정 기록구간 최대 점수로 conformal p=(1+#cal>=s)/(n+1), 경보 p<=alpha.
결과: j4_independent_v2.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(sys.argv[1])
S = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
FREQS = np.arange(0.0, 5.0001, 0.005)
DT = 0.1
normal = pd.read_csv(root / "press_data_normal.csv")
abnormal = pd.read_csv(root / "outlier_data.csv")


def records(df):
    t = pd.to_datetime(df.TimeStamp).astype("int64").to_numpy()
    gap = np.diff(t)
    new = np.r_[False, np.abs(gap - 100_000_000) > 20_000_000]
    return np.cumsum(new)


def positions(seg):
    return pd.Series(seg).groupby(seg).cumcount().to_numpy()


def matched(df):
    out = df[S].astype(float).copy()
    for c in S[:2]:
        out[c] = np.round(out[c] / 1e-4) * 1e-4
    out[S[2]] = np.round(out[S[2]] / 1.1920929) * 1.1920929
    return out


HATS = {}


def hats(win):
    if win not in HATS:
        t = np.arange(win) * DT
        H = []
        for f in FREQS:
            A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
            H.append(A @ np.linalg.pinv(A, rcond=1e-10))
        HATS[win] = np.stack(H)
    return HATS[win]


def sine_1mr2(x, seg, win):
    out = np.full(len(x), np.nan)
    idx = np.arange(win - 1, len(x))
    idx = idx[seg[idx] == seg[idx - win + 1]]
    if not len(idx):
        return out
    W = np.stack([x[i - win + 1:i + 1] for i in idx])
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in hats(win):
        r = W - W @ H.T
        best = np.minimum(best, (r * r).sum(1))
    val = np.where(sst > 0, best / np.where(sst > 0, sst, 1), np.nan)
    out[idx] = np.clip(val, 0, None)
    return out


class Tail:
    def __init__(self, ref, q=0.95):
        r = np.sort(np.asarray(ref, float)[np.isfinite(ref)])
        self.r, self.n = r, len(r)
        self.u = float(np.quantile(r, q))
        exc = r[r > self.u] - self.u
        self.beta = float(exc.mean())
        self.gu = self.emp(np.array([self.u]))[0]

    def emp(self, s):
        ge = self.n - np.searchsorted(self.r, s, side="left")
        return -np.log10((ge + 1) / (self.n + 1))

    def __call__(self, s):
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        v = s[ok]
        res = np.where(v <= self.u, self.emp(v), self.gu + (v - self.u) / (self.beta * np.log(10)))
        out[ok] = res
        return out


def ar_idx(seg):
    idx = np.arange(2, len(seg))
    return idx[seg[idx] == seg[idx - 2]]


class J4Guard:
    def __init__(self, train, seg):
        X = matched(train)
        self.mu, self.sd = X.mean().to_numpy(), X.std(ddof=0).to_numpy()
        z = np.abs((X.to_numpy() - self.mu) / self.sd).max(1)
        x = X[S[2]].to_numpy()
        i = ar_idx(seg)
        D = np.column_stack([np.ones(len(i)), x[i - 1], x[i - 2]])
        self.coef = np.linalg.lstsq(D, x[i], rcond=None)[0]
        self.t_mag = Tail(z)
        self.t_s6 = Tail(sine_1mr2(x, seg, 6))
        self.t_s8 = Tail(sine_1mr2(x, seg, 8))
        self.t_dyn = Tail(self.residual(x, seg))

    def residual(self, x, seg):
        out = np.full(len(x), np.nan)
        i = ar_idx(seg)
        out[i] = np.abs(x[i] - self.coef[0] - self.coef[1] * x[i - 1] - self.coef[2] * x[i - 2])
        return out

    def score(self, df, seg):
        X = matched(df)
        z = np.abs((X.to_numpy() - self.mu) / self.sd).max(1)
        x = X[S[2]].to_numpy()
        pos = positions(seg)
        gz = self.t_mag(z)
        gs = np.where(pos < 7, self.t_s6(sine_1mr2(x, seg, 6)), self.t_s8(sine_1mr2(x, seg, 8)))
        ga = self.t_dyn(self.residual(x, seg))
        return np.fmax(np.fmax(gz, gs), ga)


seg_n, seg_a = records(normal), records(abnormal)
pos_a = positions(seg_a)
res = dict(normal_records=int(seg_n.max() + 1), abnormal_records=int(seg_a.max() + 1))
for split, (tr_end, cal_end) in {"A": (360, 480), "B": (300, 420)}.items():
    tr = seg_n < tr_end
    cal = (seg_n >= tr_end) & (seg_n < cal_end)
    te = seg_n >= cal_end
    g = J4Guard(normal[tr].reset_index(drop=True), seg_n[tr] - 0)
    s_cal = g.score(normal[cal].reset_index(drop=True), seg_n[cal])
    cal_max = pd.Series(np.where(np.isfinite(s_cal), s_cal, -np.inf)).groupby(seg_n[cal]).max().to_numpy()
    ref = np.sort(cal_max)

    def pval(s):
        out = np.full(len(s), np.nan)
        ok = np.isfinite(s)
        out[ok] = (len(ref) - np.searchsorted(ref, s[ok], side="left") + 1) / (len(ref) + 1)
        return out

    s_te = g.score(normal[te].reset_index(drop=True), seg_n[te])
    s_ab = g.score(abnormal, seg_a)
    out = {}
    for alpha in (0.01, 0.03, 0.05):
        a_te = pval(s_te) <= alpha
        a_ab = pval(s_ab) <= alpha
        tp, fn, fp = int(a_ab.sum()), int((~a_ab).sum()), int(a_te.sum())
        first = pd.DataFrame(dict(seg=seg_a, pos=pos_a, a=a_ab)).query("a").groupby("seg").pos.min()
        out[str(alpha)] = dict(tp=tp, fn=fn, fp=fp, f1=round(2 * tp / (2 * tp + fp + fn), 6),
                               normal_records_alerted=f"{int(pd.Series(a_te).groupby(seg_n[te]).any().sum())}/{len(np.unique(seg_n[te]))}",
                               abnormal_records_detected=f"{int(len(first))}/{int(seg_a.max() + 1)}",
                               first_alarm_delay_max_s=round(float(first.max()) * DT, 1),
                               missed_rows_pos01=int(((~a_ab) & (pos_a < 2)).sum()))
    out["threshold_cal_max"] = round(float(ref[-1]), 4)
    out["ar2"] = [round(float(c), 4) for c in g.coef]
    res[split] = out
Path(__file__).with_name("j4_independent_v2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
