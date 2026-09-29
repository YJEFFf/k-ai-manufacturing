"""J3 독립 재구현: 팀 코드를 import하지 않고 원본 CSV에서 v2(early6_ar2) 핵심 수치를 다시 계산한다.

재현 대상(README 결과 표): A 행 F1 0.961938(미탐 44, 오경보 0), B 0.970990(미탐 31, 오경보 3), 정상 알림 0/120·3/180, 이상 21/21.
추가 점검: 기록 구조·저장 형식 차이·시간 교락, 보정 문턱, A 평가 구간의 조용함, 기록 단위 군집 부트스트랩, 단순 규칙 기준선.

실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python j3_independent.py <데이터 폴더> <출력 JSON>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

T0 = time.time()
DATA = Path(sys.argv[1])
OUT = Path(sys.argv[2])
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
DT_NS = 100_000_000
TOL_NS = 20_000_000
FREQS = np.arange(0.0, 5.0001, 0.005)
LN10 = np.log(10.0)


def load(name):
    raw = pd.read_csv(DATA / name, dtype=str)
    df = pd.read_csv(DATA / name)
    return raw, df


def segments(ts):
    t = pd.to_datetime(ts).astype("int64").to_numpy()
    d = np.diff(t)
    new = np.r_[False, np.abs(d - DT_NS) > TOL_NS]
    return np.cumsum(new)


def positions(seg):
    return pd.Series(seg).groupby(seg).cumcount().to_numpy()


def quantize(df):
    out = df.copy()
    for c in SENS[:2]:
        out[c] = np.round(out[c] / 1e-4) * 1e-4
    out[SENS[2]] = np.round(out[SENS[2]] / 1.1920929) * 1.1920929
    return out


def win_idx(seg, w):
    idx = np.arange(w - 1, len(seg))
    return idx[seg[idx] == seg[idx - w + 1]]


_H = {}


def hats(w, rcond):
    key = (w, rcond)
    if key not in _H:
        t = np.arange(w) * 0.1
        hs = []
        for f in FREQS:
            A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(w)])
            hs.append(A @ np.linalg.pinv(A, rcond=rcond))
        _H[key] = np.stack(hs)
    return _H[key]


def sine(x, seg, w, rcond=1e-10):
    out = np.full(len(x), np.nan)
    idx = win_idx(seg, w)
    if not len(idx):
        return out
    W = np.stack([x[i - w + 1:i + 1] for i in idx])
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in hats(w, rcond):
        r = W - W @ H.T
        np.minimum(best, (r * r).sum(1), out=best)
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
        res = np.where(v <= self.u, self.emp(v), self.gu + (v - self.u) / (self.beta * LN10))
        out[ok] = res
        return out


def ar_res(x, seg, c):
    out = np.full(len(x), np.nan)
    idx = win_idx(seg, 3)
    out[idx] = np.abs(x[idx] - c[0] - c[1] * x[idx - 1] - c[2] * x[idx - 2])
    return out


class V2:
    def __init__(self, tr):
        q = quantize(tr)
        seg = segments(q.TimeStamp)
        X = q[SENS].to_numpy(float)
        self.mu, self.sd = X.mean(0), X.std(0)
        z = (X - self.mu) / self.sd
        self.t_mag = Tail(np.abs(z).max(1))
        cur = X[:, 2]
        self.t6 = Tail(sine(cur, seg, 6))
        self.t8 = Tail(sine(cur, seg, 8))
        self.t8_v1 = Tail(sine(cur, seg, 8, rcond=1e-15))
        idx = win_idx(seg, 3)
        D = np.column_stack([np.ones(len(idx)), cur[idx - 1], cur[idx - 2]])
        self.c = np.linalg.lstsq(D, cur[idx], rcond=None)[0]
        self.t_dyn = Tail(ar_res(cur, seg, self.c))

    def comp(self, df):
        q = quantize(df)
        seg = segments(q.TimeStamp)
        pos = positions(seg)
        X = q[SENS].to_numpy(float)
        z = (X - self.mu) / self.sd
        cur = X[:, 2]
        gz = self.t_mag(np.abs(z).max(1))
        gs = np.where(pos < 7, self.t6(sine(cur, seg, 6)), self.t8(sine(cur, seg, 8)))
        ga = self.t_dyn(ar_res(cur, seg, self.c))
        v2 = np.fmax(np.fmax(gz, gs), ga)
        # v1 기준(크기 + 8행 파형, 원래 pinv)
        v1 = np.fmax(gz, self.t8(sine(cur, seg, 8, rcond=1e-15)))
        return dict(seg=seg, pos=pos, gz=gz, gs=gs, ga=ga, v2=v2, v1=v1, absz=np.abs(z))


def seg_max(s, seg):
    return pd.Series(np.where(np.isfinite(s), s, -np.inf)).groupby(seg).max().to_numpy()


def pval(cal, s):
    ref = np.sort(cal)
    out = np.full(len(s), np.nan)
    ok = np.isfinite(s)
    ge = len(ref) - np.searchsorted(ref, s[ok], side="left")
    out[ok] = (ge + 1) / (len(ref) + 1)
    return out


def f1(tp, fp, fn):
    return 2 * tp / (2 * tp + fp + fn)


res = {}
rawN, N = load("press_data_normal.csv")
rawA, A = load("outlier_data.csv")

# ---------- 1. 자료 구조 ----------
segN, segA = segments(N.TimeStamp), segments(A.TimeStamp)
tN, tA = pd.to_datetime(N.TimeStamp), pd.to_datetime(A.TimeStamp)
lenN, lenA = pd.Series(segN).value_counts().sort_index(), pd.Series(segA).value_counts().sort_index()
gapN = np.diff(tN.astype("int64").to_numpy()) / 1e9
gapA = np.diff(tA.astype("int64").to_numpy()) / 1e9


def decimals(col):
    s = col.astype(str)
    frac = s.str.split(".").str[1].fillna("")
    return frac.str.len()


res["data"] = dict(
    rows=dict(normal=len(N), abnormal=len(A)),
    labels=dict(normal=N.Equipment_state.value_counts().to_dict(), abnormal=A.Equipment_state.value_counts().to_dict()),
    missing=dict(normal=int(N.isna().sum().sum()), abnormal=int(A.isna().sum().sum())),
    dup_timestamps=dict(normal=int(N.TimeStamp.duplicated().sum()), abnormal=int(A.TimeStamp.duplicated().sum())),
    dup_rows_sensors=dict(normal=int(N[SENS].duplicated().sum()), abnormal=int(A[SENS].duplicated().sum())),
    time_range=dict(normal=[str(tN.min()), str(tN.max()), tN.min().day_name()], abnormal=[str(tA.min()), str(tA.max()), tA.min().day_name()]),
    records=dict(normal=int(segN.max() + 1), abnormal=int(segA.max() + 1)),
    record_len=dict(normal=dict(min=int(lenN.min()), median=float(lenN.median()), max=int(lenN.max()), n_len_lt8=int((lenN < 8).sum()), n_len50=int((lenN == 50).sum())),
                    abnormal=dict(min=int(lenA.min()), median=float(lenA.median()), max=int(lenA.max()), lens=lenA.tolist())),
    between_record_gap_s=dict(normal=[float(gapN[gapN > 0.12].min()), float(np.median(gapN[gapN > 0.12])), float(gapN[gapN > 0.12].max())],
                              abnormal=[float(gapA[gapA > 0.12].min()), float(np.median(gapA[gapA > 0.12])), float(gapA[gapA > 0.12].max())]),
    within_gap_ms_range=dict(normal=[float(gapN[gapN <= 0.12].min() * 1e3), float(gapN[gapN <= 0.12].max() * 1e3)],
                             abnormal=[float(gapA[gapA <= 0.12].min() * 1e3), float(gapA[gapA <= 0.12].max() * 1e3)]),
    same_as_1us_rule=dict(normal=bool((np.cumsum(np.r_[False, np.abs(gapN - 0.1) > 1e-6]) == segN).all()),
                          abnormal=bool((np.cumsum(np.r_[False, np.abs(gapA - 0.1) > 1e-6]) == segA).all())),
    decimals=dict(normal={c: decimals(rawN[c]).value_counts().head(4).to_dict() for c in SENS},
                  abnormal={c: decimals(rawA[c]).value_counts().head(4).to_dict() for c in SENS}),
    sensor_stats=dict(normal=N[SENS].describe().loc[["mean", "std", "min", "max"]].round(4).to_dict(),
                      abnormal=A[SENS].describe().loc[["mean", "std", "min", "max"]].round(4).to_dict()),
)
# 저장 형식 누설: 전류 소수 자릿수만으로 분류
dN, dA = decimals(rawN[SENS[2]]), decimals(rawA[SENS[2]])
thr_best = None
for k in range(1, 12):
    pred_n, pred_a = (dN >= k), (dA >= k)
    tp, fp = int(pred_a.sum()), int(pred_n.sum())
    fn = len(dA) - tp
    val = f1(tp, fp, fn) if tp else 0
    if thr_best is None or val > thr_best[1]:
        thr_best = (k, val, tp, fp, fn)
res["format_leak_current_decimals_ge_k"] = dict(k=thr_best[0], f1=thr_best[1], tp=thr_best[2], fp=thr_best[3], fn=thr_best[4])

# ---------- 2. v2 재현 ----------
SPL = {"A": (360, 480), "B": (300, 420)}
res["splits"] = {}
cache = {}
for sid, (te, ce) in SPL.items():
    tr = N[segN < te].reset_index(drop=True)
    ca = N[(segN >= te) & (segN < ce)].reset_index(drop=True)
    ts = N[segN >= ce].reset_index(drop=True)
    m = V2(tr)
    cc, ct, cab = m.comp(ca), m.comp(ts), m.comp(A)
    out = dict(train_records=int(te), cal_records=int(ce - te), test_records=int(600 - ce), test_rows=len(ts),
               ar2=[float(v) for v in m.c], scaler_mean=m.mu.round(5).tolist(), scaler_sd=m.sd.round(5).tolist())
    for name in ("v2", "v1"):
        cal = seg_max(cc[name], cc["seg"])
        cal_sorted = np.sort(cal)[::-1]
        for alpha in (0.01, 0.03, 0.05):
            pn, pa = pval(cal, ct[name]), pval(cal, cab[name])
            an = np.isfinite(pn) & (pn <= alpha)
            aa = np.isfinite(pa) & (pa <= alpha)
            tp, fp = int(aa.sum()), int(an.sum())
            fn, tn = 600 - tp, len(ts) - fp
            rec_n = pd.Series(an).groupby(ct["seg"]).max()
            rec_a = pd.Series(aa).groupby(cab["seg"]).max()
            key = f"{name}_a{int(alpha*100)}"
            out[key] = dict(tp=tp, fp=fp, fn=fn, tn=tn, f1=round(f1(tp, fp, fn), 6), precision=round(tp / (tp + fp), 6),
                            recall=round(tp / 600, 6),
                            normal_records_alerted=int(rec_n.sum()), normal_records=int(len(rec_n)),
                            normal_alerted_ids=[int(i + ce) for i in np.where(rec_n.to_numpy())[0]],
                            abnormal_records_detected=int(rec_a.sum()),
                            miss_by_pos=pd.Series(~aa).groupby(np.minimum(cab["pos"], 7)).sum().astype(int).to_dict())
            if name == "v2" and alpha == 0.01:
                cache[sid] = dict(cc=cc, ct=ct, cab=cab, cal=cal, an=an, aa=aa, ce=ce, te=te)
        out[f"{name}_cal_top3"] = [round(float(v), 4) for v in cal_sorted[:3]]
        out[f"{name}_cal_top3_record"] = [int(np.argsort(cal)[::-1][k] + te) for k in range(3)]
        tmax = seg_max(ct[name], ct["seg"])
        amax = seg_max(cab[name], cab["seg"])
        out[f"{name}_record_max"] = dict(normal_test_max=round(float(tmax.max()), 3), abnormal_min=round(float(amax.min()), 3),
                                         record_auroc=float((amax[:, None] > tmax[None, :]).mean() + 0.5 * (amax[:, None] == tmax[None, :]).mean()))
        # 평가 구간의 조용함: 평가 기록 최대 점수가 보정 중앙값을 넘는 비율
        if name == "v2":
            med = np.median(cal)
            out["v2_test_above_cal_median"] = int((tmax > med).sum())
            from scipy.stats import mannwhitneyu
            out["v2_mw_test_vs_cal_p"] = float(mannwhitneyu(tmax, cal, alternative="two-sided").pvalue)
    res["splits"][sid] = out
    print(sid, out["v2_a1"]["f1"], out["v2_a1"]["fn"], out["v2_a1"]["fp"], out["v1_a1"]["f1"], round(time.time() - T0, 1), flush=True)

# ---------- 3. 군집(기록) 부트스트랩: 행 F1의 불확실성 ----------
rng = np.random.default_rng(20260930)
boot = {}
for sid, c in cache.items():
    an, aa = c["an"], c["aa"]
    segn, sega = c["ct"]["seg"], c["cab"]["seg"]
    n_fp = pd.Series(an).groupby(segn).sum().to_numpy(); n_rows_n = pd.Series(an).groupby(segn).size().to_numpy()
    a_tp = pd.Series(aa).groupby(sega).sum().to_numpy(); a_rows = pd.Series(aa).groupby(sega).size().to_numpy()
    vals, recs = [], []
    for _ in range(4000):
        i = rng.integers(0, len(n_fp), len(n_fp)); j = rng.integers(0, len(a_tp), len(a_tp))
        tp = a_tp[j].sum(); fn = a_rows[j].sum() - tp; fp = n_fp[i].sum()
        vals.append(f1(tp, fp, fn))
    boot[sid] = dict(f1_point=round(f1(aa.sum(), an.sum(), 600 - aa.sum()), 6), f1_ci95=[round(float(np.quantile(vals, .025)), 4), round(float(np.quantile(vals, .975)), 4)],
                     note="정상 평가 기록과 이상 21기록을 따로 복원 추출(4000회). 이상 21기록은 한 에피소드라 이 구간도 낙관적이다")
res["cluster_bootstrap_f1"] = boot

# ---------- 4. 정상 알림률의 교환가능성 점검 ----------
from scipy.stats import binom, beta as B
ex = {}
for sid, c in cache.items():
    n_cal = len(c["cal"]); n_test = res["splits"][sid]["v2_a1"]["normal_records"]; k = res["splits"][sid]["v2_a1"]["normal_records_alerted"]
    p0 = 1 / (n_cal + 1)
    ex[sid] = dict(nominal=round(p0, 5), k=k, n=n_test, expected=round(n_test * p0, 2), p_ge_k_binom=round(float(binom.sf(k - 1, n_test, p0)), 4) if k else 1.0,
                   cp_upper95=round(float(B.ppf(0.95, k + 1, n_test - k)), 4))
res["conformal_far_check"] = ex

# ---------- 5. 단순 규칙 기준선(README 설명대로 독립 구현): 0.6 Hz 고정 사인 잔차 + |진동| / 정상 학습 최댓값 ----------
def simple_rule(train, frames, w=8):
    q = quantize(train); seg = segments(q.TimeStamp)
    def feats(df):
        qq = quantize(df); sg = segments(qq.TimeStamp); X = qq[SENS].to_numpy(float)
        cur = X[:, 2]; out = np.full(len(cur), np.nan); idx = win_idx(sg, w)
        t = np.arange(w) * 0.1
        Am = np.column_stack([np.sin(2 * np.pi * 0.6 * t), np.cos(2 * np.pi * 0.6 * t), np.ones(w)])
        H = Am @ np.linalg.pinv(Am)
        if len(idx):
            Wd = np.stack([cur[i - w + 1:i + 1] for i in idx]); r = Wd - Wd @ H.T
            out[idx] = np.sqrt((r * r).mean(1))
        return np.column_stack([np.abs(X[:, 0]), np.abs(X[:, 1]), out]), sg
    Ftr, _ = feats(train)
    mx = np.nanmax(Ftr, axis=0)
    res_ = []
    for df in frames:
        F, sg = feats(df)
        res_.append((np.nanmax(F / mx, axis=1), sg))
    return res_

sr = {}
for sid, (te, ce) in SPL.items():
    tr = N[segN < te].reset_index(drop=True); ca = N[(segN >= te) & (segN < ce)].reset_index(drop=True); ts = N[segN >= ce].reset_index(drop=True)
    (sc, sgc), (st, sgt), (sa, sga) = simple_rule(tr, [ca, ts, A])
    cal = seg_max(sc, sgc)
    pn, pa = pval(cal, st), pval(cal, sa)
    an, aa = pn <= 0.01, pa <= 0.01
    tp, fp = int(aa.sum()), int(an.sum())
    sr[sid] = dict(f1=round(f1(tp, fp, 600 - tp), 4), tp=tp, fp=fp, normal_rec=int(pd.Series(an).groupby(sgt).max().sum()),
                   abn_rec=int(pd.Series(aa).groupby(sga).max().sum()))
res["simple_rule_approx"] = sr
res["seconds"] = round(time.time() - T0, 1)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
print(json.dumps(res["splits"]["A"]["v2_a1"], ensure_ascii=False))
print(json.dumps(res["splits"]["B"]["v2_a1"], ensure_ascii=False))
print("done", res["seconds"])
