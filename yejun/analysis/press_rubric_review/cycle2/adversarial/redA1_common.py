"""적대적 검수자 A1 — 독립 재구현 공용 함수.

팀 모듈(press_guard, press_submission/press)을 import하지 않는다. numpy·pandas만 쓴다.
알고리즘은 팀 코드(model.py, press/scores.py, press/calibrate.py, press/data.py)를 읽고 글로 옮긴 명세를 다시 구현했다.
수치 경로는 일부러 다르게 했다(사인 적합은 hat 행렬 대신 QR 직교 기저, 표준화는 직접 계산).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path("/Volumes/YJSSD/공모전/k-제조데이터")
DATA = REPO / "yejun/press_submission/data/3_소성가공_예지보전"
OUT = REPO / "yejun/analysis/press_rubric_review/cycle2/adversarial"
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
TIME = "TimeStamp"
DT = 0.1
VIB_STEP, CUR_STEP = 1e-4, 1.1920929
SPLITS = {"A": (360, 480), "B": (300, 420)}   # 학습 끝(미포함), 보정 끝(미포함)
FREQS = np.arange(0.0, 5.0001, 0.005)
ALPHAS = (0.01, 0.03, 0.05)


def load_raw():
    normal = pd.read_csv(DATA / "press_data_normal.csv")
    abnormal = pd.read_csv(DATA / "outlier_data.csv")
    return normal, abnormal


def seconds(ts) -> np.ndarray:
    """시각을 초(실수)로. 첫 행 기준."""
    t = pd.to_datetime(pd.Series(ts).astype(str), format="mixed")
    ns = t.to_numpy().astype("datetime64[ns]").astype("int64")
    return (ns - ns[0]) / 1e9


def segment_ids(ts, tol=0.02) -> np.ndarray:
    """이웃 행 간격이 0.1초에서 tol 넘게 벗어나면 새 기록."""
    s = seconds(ts)
    new = np.abs(np.diff(s) - DT) > tol
    return np.concatenate([[0], np.cumsum(new)]).astype(int)


def positions(seg) -> np.ndarray:
    seg = np.asarray(seg)
    start = np.concatenate([[True], seg[1:] != seg[:-1]])
    first = np.maximum.accumulate(np.where(start, np.arange(len(seg)), 0))
    return np.arange(len(seg)) - first


def quantize(values: np.ndarray) -> np.ndarray:
    """matched: 진동 1e-4, 전류 1.1920929 격자로 반올림. values는 (n,3)."""
    out = np.array(values, float)
    out[:, 0] = np.round(out[:, 0] / VIB_STEP) * VIB_STEP
    out[:, 1] = np.round(out[:, 1] / VIB_STEP) * VIB_STEP
    out[:, 2] = np.round(out[:, 2] / CUR_STEP) * CUR_STEP
    return out


def windows_index(seg, win):
    """같은 기록 안에서 최근 win행이 모두 있는 행 번호."""
    seg = np.asarray(seg)
    idx = np.arange(win - 1, len(seg))
    return idx[seg[idx] == seg[idx - win + 1]]


_BASIS = {}


def _bases(win):
    """주파수마다 [sin, cos, 1]의 열공간 직교 기저(SVD, 계수 부족은 버림)."""
    if win not in _BASIS:
        t = np.arange(win) * DT
        out = []
        for f in FREQS:
            A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
            u, s, _ = np.linalg.svd(A, full_matrices=False)
            out.append(u[:, s > 1e-10 * s.max()])
        _BASIS[win] = out
    return _BASIS[win]


def sine_1mr2(current, seg, win, return_freq=False):
    """행별 1−R²: 최근 win행 전류에 (단일 사인 + 상수) 최소제곱, 0~5 Hz 0.005 간격 격자에서 잔차 최소."""
    x = np.asarray(current, float)
    out = np.full(len(x), np.nan)
    fbest = np.full(len(x), np.nan)
    idx = windows_index(seg, win)
    if not len(idx):
        return (out, fbest) if return_freq else out
    W = np.stack([x[i - win + 1:i + 1] for i in idx])
    sst = ((W - W.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)
    best = np.full(len(idx), np.inf)
    arg = np.zeros(len(idx), int)
    for k, Q in enumerate(_bases(win)):
        r = W - (W @ Q) @ Q.T
        sse = (r * r).sum(axis=1)
        better = sse < best
        best[better] = sse[better]
        arg[better] = k
    val = np.full(len(idx), np.nan)
    ok = sst > 0
    val[ok] = np.clip(best[ok] / sst[ok], 0, None)
    out[idx] = val
    fbest[idx] = FREQS[arg]
    return (out, fbest) if return_freq else out


class Tail:
    """정상 학습 참조 점수의 q95 초과분 지수 꼬리 변환 g = −log10(꼬리 확률)."""

    def __init__(self, ref, q=0.95):
        r = np.asarray(ref, float)
        self.ref = np.sort(r[np.isfinite(r)])
        self.n = len(self.ref)
        self.u = float(np.quantile(self.ref, q))
        exc = self.ref[self.ref > self.u] - self.u
        self.beta = float(exc.mean())
        self.gu = self._emp(np.array([self.u]))[0]

    def _emp(self, s):
        ge = self.n - np.searchsorted(self.ref, s, side="left")
        return -np.log10((ge + 1) / (self.n + 1))

    def __call__(self, s):
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        v = s[ok]
        res = np.where(v <= self.u, self._emp(v), self.gu + (v - self.u) / (self.beta * np.log(10)))
        out[ok] = res
        return out


def record_max(score, seg):
    s = np.where(np.isfinite(score), score, -np.inf)
    return pd.Series(s).groupby(np.asarray(seg)).max().to_numpy()


def conformal_p(cal, score):
    ref = np.sort(np.asarray(cal, float))
    out = np.full(len(score), np.nan)
    ok = np.isfinite(score)
    ge = len(ref) - np.searchsorted(ref, np.asarray(score)[ok], side="left")
    out[ok] = (ge + 1) / (len(ref) + 1)
    return out


class Detector:
    """v2 검출기 독립 재구현. fit(train 값, 기록 번호) → calibrate → score."""

    def __init__(self, use=("magnitude", "waveform", "dynamics"), early=True):
        self.use, self.early = tuple(use), early

    def fit(self, X, seg):
        """X: matched 양자화된 (n,3) 정상 학습 값."""
        self.mean = X.mean(axis=0)
        self.scale = X.std(axis=0)   # ddof=0
        z = np.abs((X - self.mean) / self.scale).max(axis=1)
        cur = X[:, 2]
        i = windows_index(seg, 3)
        D = np.column_stack([np.ones(len(i)), cur[i - 1], cur[i - 2]])
        self.ar = np.linalg.lstsq(D, cur[i], rcond=None)[0]
        self.t_mag = Tail(z)
        self.t_s6 = Tail(sine_1mr2(cur, seg, 6))
        self.t_s8 = Tail(sine_1mr2(cur, seg, 8))
        self.t_dyn = Tail(self.residual(cur, seg))
        return self

    def residual(self, cur, seg):
        out = np.full(len(cur), np.nan)
        i = windows_index(seg, 3)
        out[i] = np.abs(cur[i] - self.ar[0] - self.ar[1] * cur[i - 1] - self.ar[2] * cur[i - 2])
        return out

    def components(self, X, seg):
        pos = positions(seg)
        mag = np.abs((X - self.mean) / self.scale).max(axis=1)
        cur = X[:, 2]
        s6, s8 = sine_1mr2(cur, seg, 6), sine_1mr2(cur, seg, 8)
        res = self.residual(cur, seg)
        gz = self.t_mag(mag)
        if self.early:
            gs = np.where(pos < 7, self.t_s6(s6), self.t_s8(s8))
        else:
            gs = self.t_s8(s8)
        ga = self.t_dyn(res)
        nan = np.full(len(X), np.nan)
        parts = dict(magnitude=gz if "magnitude" in self.use else nan,
                     waveform=gs if "waveform" in self.use else nan,
                     dynamics=ga if "dynamics" in self.use else nan)
        with np.errstate(all="ignore"):
            score = np.fmax(np.fmax(parts["magnitude"], parts["waveform"]), parts["dynamics"])
        return dict(pos=pos, mag=mag, s6=s6, s8=s8, res=res, gz=gz, gs=gs, ga=ga, score=score)

    def calibrate(self, X, seg):
        self.cal = record_max(self.components(X, seg)["score"], seg)
        return self

    def predict(self, X, seg, alpha=0.01):
        c = self.components(X, seg)
        p = conformal_p(self.cal, c["score"])
        c["p"] = p
        c["alarm"] = np.isfinite(p) & (p <= alpha)
        return c


def split_frames(normal, seg, sid):
    a, b = SPLITS[sid]
    return dict(train=seg < a, cal=(seg >= a) & (seg < b), test=seg >= b)


def f1_rows(alarm_normal, alarm_abnormal):
    tp, fp = int(np.sum(alarm_abnormal)), int(np.sum(alarm_normal))
    fn = len(alarm_abnormal) - tp
    return dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0)


def auroc(neg, pos):
    """Mann–Whitney AUROC(양성 점수가 클수록 1). 동점은 0.5."""
    from scipy.stats import rankdata
    neg, pos = np.asarray(neg, float), np.asarray(pos, float)
    neg, pos = neg[np.isfinite(neg)], pos[np.isfinite(pos)]
    r = rankdata(np.concatenate([neg, pos]))
    u = r[len(neg):].sum() - len(pos) * (len(pos) + 1) / 2
    return float(u / (len(pos) * len(neg)))
