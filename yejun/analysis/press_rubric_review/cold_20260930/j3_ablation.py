"""J3: 성분·센서 절제 독립 재계산(팀 코드 import 없음). README '성분 절제'·'재적합 절제' 수치 대조.
각 변형은 정상 학습으로 다시 적합하고 정상 보정 기록 최대로 다시 보정한다(α 1%).
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python j3_ablation.py <데이터 폴더> <출력 JSON>"""
import json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
T0 = time.time()
DATA, OUT = Path(sys.argv[1]), Path(sys.argv[2])
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




class V2X:
    """sensors: 크기 성분에 쓰는 센서 번호, comps: 쓰는 성분"""
    def __init__(self, tr, sensors=(0, 1, 2), comps=("mag", "wave", "dyn")):
        self.sensors, self.comps = list(sensors), comps
        q = quantize(tr); seg = segments(q.TimeStamp); X = q[SENS].to_numpy(float)
        self.mu, self.sd = X.mean(0), X.std(0)
        self.t_mag = Tail(np.abs(((X - self.mu) / self.sd)[:, self.sensors]).max(1))
        cur = X[:, 2]
        self.t6, self.t8 = Tail(sine(cur, seg, 6)), Tail(sine(cur, seg, 8))
        idx = win_idx(seg, 3)
        self.c = np.linalg.lstsq(np.column_stack([np.ones(len(idx)), cur[idx - 1], cur[idx - 2]]), cur[idx], rcond=None)[0]
        self.t_dyn = Tail(ar_res(cur, seg, self.c))

    def score(self, df):
        q = quantize(df); seg = segments(q.TimeStamp); pos = positions(seg); X = q[SENS].to_numpy(float); cur = X[:, 2]
        parts = []
        if "mag" in self.comps:
            parts.append(self.t_mag(np.abs(((X - self.mu) / self.sd)[:, self.sensors]).max(1)))
        if "wave" in self.comps:
            parts.append(np.where(pos < 7, self.t6(sine(cur, seg, 6)), self.t8(sine(cur, seg, 8))))
        if "dyn" in self.comps:
            parts.append(self.t_dyn(ar_res(cur, seg, self.c)))
        s = parts[0]
        for p in parts[1:]:
            s = np.fmax(s, p)
        return s, seg


N = pd.read_csv(DATA / "press_data_normal.csv"); A = pd.read_csv(DATA / "outlier_data.csv"); segN = segments(N.TimeStamp)
variants = {"full": dict(), "no_waveform": dict(comps=("mag", "dyn")), "no_dynamics": dict(comps=("mag", "wave")), "no_magnitude": dict(comps=("wave", "dyn")),
            "no_AI0": dict(sensors=(1, 2)), "no_AI1": dict(sensors=(0, 2)), "current_only": dict(sensors=(2,)),
            "vibration_only": dict(sensors=(0, 1), comps=("mag",))}
res = {}
for sid, (te, ce) in {"A": (360, 480), "B": (300, 420)}.items():
    tr, ca, ts = (N[m].reset_index(drop=True) for m in (segN < te, (segN >= te) & (segN < ce), segN >= ce))
    for name, kw in variants.items():
        m = V2X(tr, **kw)
        sc, gc = m.score(ca); st, gt = m.score(ts); sa, ga = m.score(A)
        thr = seg_max(sc, gc).max()
        an, aa = np.isfinite(st) & (st > thr), np.isfinite(sa) & (sa > thr)
        tp, fp = int(aa.sum()), int(an.sum())
        res.setdefault(name, {})[sid] = dict(fn=600 - tp, fp=fp, f1=round(2 * tp / (2 * tp + fp + 600 - tp), 4),
                                             normal_rec=int(pd.Series(an).groupby(gt).max().sum()), abn_rec=int(pd.Series(aa).groupby(ga).max().sum()))
    print(sid, {k: v[sid] for k, v in res.items()}, flush=True)
res["seconds"] = round(time.time() - T0, 1)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
