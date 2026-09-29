"""J3 추가 점검(팀 코드 import 없음): ① 기록 길이별 conformal 오경보율(교환가능성) ② 이상 확률 층 독립 재적합(21겹 LORO)
③ 이상 기록별 경보 행 수(2단계 격상) ④ 팀 테스트 예측 파일의 F1·Brier·ECE 재계산(파일이 주어질 때).

실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python j3_checks2.py <데이터 폴더> <출력 JSON> [팀 outputs 폴더]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

T0 = time.time()
DATA, OUT = Path(sys.argv[1]), Path(sys.argv[2])
TEAM_OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else None
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
FREQS = np.arange(0.0, 5.0001, 0.005)
LN10 = np.log(10.0)


def segments(ts):
    t = pd.to_datetime(ts).astype("int64").to_numpy()
    return np.cumsum(np.r_[False, np.abs(np.diff(t) - 100_000_000) > 20_000_000])


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


def sine(x, seg, w):
    if w not in _H:
        t = np.arange(w) * 0.1
        _H[w] = np.stack([(lambda A: A @ np.linalg.pinv(A, rcond=1e-10))(np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(w)])) for f in FREQS])
    out = np.full(len(x), np.nan)
    idx = win_idx(seg, w)
    if not len(idx):
        return out
    W = np.stack([x[i - w + 1:i + 1] for i in idx])
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in _H[w]:
        r = W - W @ H.T
        np.minimum(best, (r * r).sum(1), out=best)
    out[idx] = np.clip(np.where(sst > 0, best / np.where(sst > 0, sst, 1), np.nan), 0, None)
    return out


class Tail:
    def __init__(self, ref, q=0.95):
        r = np.sort(np.asarray(ref, float)[np.isfinite(ref)])
        self.r, self.n = r, len(r)
        self.u = float(np.quantile(r, q))
        self.beta = float((r[r > self.u] - self.u).mean())
        self.gu = self.emp(np.array([self.u]))[0]

    def emp(self, s):
        return -np.log10((self.n - np.searchsorted(self.r, s, side="left") + 1) / (self.n + 1))

    def __call__(self, s):
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        v = s[ok]
        out[ok] = np.where(v <= self.u, self.emp(v), self.gu + (v - self.u) / (self.beta * LN10))
        return out


def ar_res(x, seg, c):
    out = np.full(len(x), np.nan)
    idx = win_idx(seg, 3)
    out[idx] = np.abs(x[idx] - c[0] - c[1] * x[idx - 1] - c[2] * x[idx - 2])
    return out


class V2:
    def __init__(self, tr):
        q = quantize(tr); seg = segments(q.TimeStamp); X = q[SENS].to_numpy(float)
        self.mu, self.sd = X.mean(0), X.std(0)
        self.t_mag = Tail(np.abs((X - self.mu) / self.sd).max(1))
        cur = X[:, 2]
        self.t6, self.t8 = Tail(sine(cur, seg, 6)), Tail(sine(cur, seg, 8))
        idx = win_idx(seg, 3)
        self.c = np.linalg.lstsq(np.column_stack([np.ones(len(idx)), cur[idx - 1], cur[idx - 2]]), cur[idx], rcond=None)[0]
        self.t_dyn = Tail(ar_res(cur, seg, self.c))

    def score(self, df):
        q = quantize(df); seg = segments(q.TimeStamp); pos = positions(seg); X = q[SENS].to_numpy(float); cur = X[:, 2]
        gz = self.t_mag(np.abs((X - self.mu) / self.sd).max(1))
        gs = np.where(pos < 7, self.t6(sine(cur, seg, 6)), self.t8(sine(cur, seg, 8)))
        ga = self.t_dyn(ar_res(cur, seg, self.c))
        return np.fmax(np.fmax(gz, gs), ga), seg, pos


def seg_max(s, seg):
    return pd.Series(np.where(np.isfinite(s), s, -np.inf)).groupby(seg).max().to_numpy()


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1); tot = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & ((p < hi) | (hi == 1))
        if k.any():
            tot += k.mean() * abs(p[k].mean() - y[k].mean())
    return float(tot)


def brier(y, p):
    return float(np.mean((p - y) ** 2))


N = pd.read_csv(DATA / "press_data_normal.csv"); A = pd.read_csv(DATA / "outlier_data.csv")
segN = segments(N.TimeStamp)
res = {}

# ---------- ① 기록 길이별 오경보: 동결 A·B + 시간순 5겹(학습 [0,e), 보정 [e,e+120), 평가 [e+120,e+180)) ----------
fits = [("A", 360, 480, 600), ("B", 300, 420, 600)] + [(f"roll{e}", e, e + 120, e + 180) for e in (180, 240, 300, 360, 420)]
rows = []
models = {}
for name, te, ce, ee in fits:
    tr = N[segN < te].reset_index(drop=True); ca = N[(segN >= te) & (segN < ce)].reset_index(drop=True)
    ts = N[(segN >= ce) & (segN < ee)].reset_index(drop=True)
    m = V2(tr)
    sc, sgc, _ = m.score(ca); st, sgt, _ = m.score(ts)
    cal = np.sort(seg_max(sc, sgc)); n = len(cal)
    tmax = seg_max(st, sgt); tlen = pd.Series(sgt).value_counts().sort_index().to_numpy()
    clen = pd.Series(sgc).value_counts().sort_index().to_numpy()
    # 기록 최소 p = (1 + #{cal >= max})/(n+1)
    pmin = (n - np.searchsorted(cal, tmax, side="left") + 1) / (n + 1)
    for k in (1, 3, 6, 12):
        for grp, mask in (("len50", tlen == 50), ("len17_49", (tlen >= 17) & (tlen < 50)), ("len_lt17", tlen < 17)):
            rows.append(dict(fit=name, k=k, nominal=k / (n + 1), group=grp, n=int(mask.sum()), alerts=int((pmin[mask] <= k / (n + 1)).sum())))
    models[name] = (m, ca, ts, sc, sgc, st, sgt, cal)
    # 보정 기록의 길이와 최대 점수의 순위상관
    from scipy.stats import spearmanr
    rows.append(dict(fit=name, k=-1, group="spearman_len_vs_calmax", n=int(n), alerts=float(spearmanr(clen, seg_max(sc, sgc)).correlation)))
df = pd.DataFrame(rows)
res["length_conditional_far"] = df.to_dict(orient="records")
pooled = df[df.k > 0].groupby(["k", "group"])[["n", "alerts"]].sum().reset_index()
pooled["rate"] = pooled.alerts / pooled.n
pooled["nominal"] = pooled.k / 121
res["length_conditional_far_pooled_all7fits"] = pooled.round(4).to_dict(orient="records")
print(pooled.to_string(index=False), flush=True)

# ---------- ② 이상 확률 층 독립 재적합(행, 21겹 LORO, LR 상한 121) ----------
prob = {}
for sid in ("A", "B"):
    m, ca, ts, sc, sgc, st, sgt, cal = models[sid]
    sa, sga, pa_pos = m.score(A)
    s0 = sc[np.isfinite(sc)]
    lr_ab = np.full(len(sa), np.nan)

    def fit_lr(s0, s1):
        x = np.r_[s0, s1]; y = np.r_[np.zeros(len(s0)), np.ones(len(s1))]
        iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip").fit(x, y)
        odds = y.mean() / (1 - y.mean())
        inner = iso.y_thresholds_[(iso.y_thresholds_ > 0) & (iso.y_thresholds_ < 1)]
        floor = min((inner / (1 - inner) / odds).min() if len(inner) else 1.0, 121.0)
        def f(s):
            p = np.interp(s, iso.X_thresholds_, iso.y_thresholds_)
            p = np.clip(p, 1e-9, 1 - 1e-9)
            return np.clip(p / (1 - p) / odds, floor, 121.0)
        return f
    for r in np.unique(sga):
        keep = sga != r
        f = fit_lr(s0, sa[keep & np.isfinite(sa)])
        lr_ab[~keep] = f(sa[~keep])
    f_all = fit_lr(s0, sa[np.isfinite(sa)])
    lr_n = f_all(st)
    y = np.r_[np.zeros(len(st)), np.ones(len(sa))]
    lr = np.r_[lr_n, lr_ab]
    pi_eval = y.mean()
    out = {}
    for label, pi in (("pi_1pct", 0.01), ("pi_file", pi_eval)):
        p = pi * lr / (pi * lr + 1 - pi)
        out[label] = dict(brier=round(brier(y, p), 5), ece=round(ece(y, p), 5), max_p=round(float(p.max()), 4),
                          n_at_cap=int((lr >= 121 - 1e-9).sum()), n_abn_at_cap=int((lr_ab >= 121 - 1e-9).sum()), n_normal_at_cap=int((lr_n >= 121 - 1e-9).sum()))
    # 문턱 점수에서의 확률(π 1%)
    thr = float(cal[-1])
    out["p_at_threshold_pi1"] = round(float(0.01 * f_all(np.array([thr]))[0] / (0.01 * f_all(np.array([thr]))[0] + 0.99)), 4)
    out["pi_eval"] = round(float(pi_eval), 4)
    # 유병률만 쓰는 기준선
    out["prevalence_only_brier"] = round(brier(y, np.full(len(y), pi_eval)), 5)
    prob[sid] = out
    # ③ 이상 기록별 경보 행 수(α 1%)
    thr_alarm = cal[-1]
    alarm = np.isfinite(sa) & (sa > thr_alarm)
    per = pd.Series(alarm).groupby(sga).sum()
    res.setdefault("abnormal_alarm_rows_per_record", {})[sid] = dict(min=int(per.min()), records_ge2=int((per >= 2).sum()), records=int(len(per)),
                                                                     first_alarm_pos=pd.Series(np.where(alarm, pa_pos, 999)).groupby(sga).min().tolist())
    nal = np.isfinite(st) & (st > thr_alarm)
    res.setdefault("normal_alarm_rows_per_alerted_record", {})[sid] = pd.Series(nal).groupby(sgt).sum().loc[lambda s: s > 0].tolist()
res["probability_independent"] = prob
print(json.dumps(prob, ensure_ascii=False), flush=True)

# ---------- ④ 팀 테스트 예측 파일 재채점 ----------
if TEAM_OUT is not None:
    tp_ = {}
    for sid in ("A", "B"):
        f = TEAM_OUT / f"test_predictions_{sid}.csv"
        if not f.exists():
            continue
        d = pd.read_csv(f)
        y = d.label.to_numpy(float); a = d.alarm.to_numpy(float)
        tpv, fpv = int(((a == 1) & (y == 1)).sum()), int(((a == 1) & (y == 0)).sum()); fnv = int(((a == 0) & (y == 1)).sum())
        p1, pf = d.anomaly_probability.to_numpy(float), d.anomaly_probability_file_prior.to_numpy(float)
        ok = np.isfinite(p1) & np.isfinite(pf)
        tp_[sid] = dict(rows=len(d), tp=tpv, fp=fpv, fn=fnv, f1=round(2 * tpv / (2 * tpv + fpv + fnv), 6),
                        brier_pi1=round(brier(y[ok], p1[ok]), 5), ece_pi1=round(ece(y[ok], p1[ok]), 5),
                        brier_file=round(brier(y[ok], pf[ok]), 5), ece_file=round(ece(y[ok], pf[ok]), 5), n_prob_nan=int((~ok).sum()),
                        abn_at_cap=int(((d.likelihood_ratio >= 120.999) & (y == 1)).sum()), normal_alarm_at_cap=int(((d.likelihood_ratio >= 120.999) & (y == 0) & (a == 1)).sum()),
                        incident_notifications_normal=int(d.loc[d.label == 0, "incident_notification"].sum()), incident_escalations_normal=int(d.loc[d.label == 0, "incident_escalation"].sum()),
                        incident_notifications_abn=int(d.loc[d.label == 1, "incident_notification"].sum()), incident_escalations_abn=int(d.loc[d.label == 1, "incident_escalation"].sum()))
    res["team_test_prediction_rescore"] = tp_
    print(json.dumps(tp_, ensure_ascii=False), flush=True)
res["seconds"] = round(time.time() - T0, 1)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
print("done", res["seconds"])
