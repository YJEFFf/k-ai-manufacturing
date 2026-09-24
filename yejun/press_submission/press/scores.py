"""행 단위 이상 점수 — PLAN.md §3·§4.1. 모든 모델은 정상 학습 자료(주 전처리 적용 후)로만 적합한다.

성분: max-abs-z(3센서 / 진동 2센서), 전류 trailing-w 사인 적합 1−R², 5NN 거리, RMS5, IsolationForest, MLP-AE(w=5).
주 결합: S = fmax(g_z(maxz3), g_s(sine_w)). g는 정상 학습 참조 점수의 q95 초과분 지수 꼬리 변환(ExpTail).
사인 점수가 없는 행(구간 첫 w−1행, SST=0 창)은 NaN이며 결합은 그 행에서 max-z만 쓴다.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .data import DT, SENSORS

FREQS = np.arange(0.0, 5.0001, 0.005)
AE_WIN = 5
MAIN_W = 8
LN10 = np.log(10.0)


@lru_cache(maxsize=None)
def _hats(win: int) -> np.ndarray:
    t = np.arange(win) * DT
    hats = []
    for f in FREQS:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
        hats.append(A @ np.linalg.pinv(A))
    return np.stack(hats)


def window_index(seg: np.ndarray, win: int) -> np.ndarray:
    """같은 기록구간 안에서 최근 win관측이 모두 있는 행 번호."""
    idx = np.arange(win - 1, len(seg))
    return idx[seg[idx] == seg[idx - win + 1]]


def sine_score(current: np.ndarray, seg: np.ndarray, win: int) -> np.ndarray:
    """행별 1−R²: 최근 win관측 전류에 단일 사인+상수(0~5Hz 격자) 최소제곱. 창이 안 차거나 SST=0이면 NaN."""
    x = np.asarray(current, float)
    score = np.full(len(x), np.nan)
    idx = window_index(seg, win)
    if len(idx) == 0:
        return score
    W = np.stack([x[i - win + 1:i + 1] for i in idx])
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in _hats(win):
        r = W - W @ H.T
        np.minimum(best, (r * r).sum(1), out=best)
    with np.errstate(divide="ignore", invalid="ignore"):
        val = np.where(sst > 0, best / sst, np.nan)
    score[idx] = np.clip(val, 0.0, None)
    return score


class ExpTail:
    """정상 학습 참조 점수 R의 q95 초과분 지수 꼬리 변환 g(s) (PLAN §4.1). 확률 추정치가 아니라 척도 변환이다."""

    def __init__(self, ref: np.ndarray, q: float = 0.95):
        r = np.asarray(ref, float)
        r = np.sort(r[np.isfinite(r)])
        self.n = int(len(r))
        self.ref = r
        self.q = q
        self.ok = self.n > 0
        self.u = float(np.quantile(r, q, method="linear")) if self.ok else np.nan
        exc = r[r > self.u] - self.u if self.ok else np.array([])
        self.n_exceed = int(len(exc))
        self.beta = float(exc.mean()) if len(exc) else np.nan
        self.ok = bool(self.ok and len(exc) > 0 and np.isfinite(self.beta) and self.beta > 0)
        self.g_u = self._g_emp(np.array([self.u]))[0] if self.ok else np.nan

    def _g_emp(self, s: np.ndarray) -> np.ndarray:
        ge = self.n - np.searchsorted(self.ref, s, side="left")   # #{R >= s}
        return -np.log10((ge + 1) / (self.n + 1))

    def __call__(self, s) -> np.ndarray:
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        if not self.ok:
            return out
        ok = np.isfinite(s)
        v = s[ok]
        low = v <= self.u
        res = np.empty_like(v)
        res[low] = self._g_emp(v[low])
        res[~low] = self.g_u + (v[~low] - self.u) / (self.beta * LN10)
        out[ok] = res
        return out

    def state(self) -> dict:
        return {"q": self.q, "n": self.n, "u": self.u, "beta": self.beta, "n_exceed": self.n_exceed, "ok": self.ok,
                "ref_sorted": self.ref}

    @classmethod
    def from_state(cls, st: dict) -> "ExpTail":
        obj = cls.__new__(cls)
        obj.q, obj.n, obj.u, obj.beta, obj.n_exceed, obj.ok = st["q"], int(st["n"]), float(st["u"]), float(st["beta"]), int(st["n_exceed"]), bool(st["ok"])
        obj.ref = np.asarray(st["ref_sorted"], float)
        obj.g_u = obj._g_emp(np.array([obj.u]))[0] if obj.ok else np.nan
        return obj


def capped_logp(ref: np.ndarray, values: np.ndarray) -> np.ndarray:
    """절제·이전 결과 대조용: 기존 파이프라인의 상한 있는 ECDF 변환 −log10((#ref≥v+1)/(n+1))."""
    r = np.sort(np.asarray(ref, float)[np.isfinite(ref)])
    out = np.full(len(values), np.nan)
    ok = np.isfinite(values)
    ge = len(r) - np.searchsorted(r, values[ok], side="left")
    out[ok] = -np.log10((ge + 1) / (len(r) + 1))
    return out


def _ae_windows(z: np.ndarray, seg: np.ndarray):
    idx = window_index(seg, AE_WIN)
    X = np.stack([z[i - AE_WIN + 1:i + 1].ravel() for i in idx]) if len(idx) else np.empty((0, 3 * AE_WIN))
    return idx, X


class Scorer:
    """정상 학습 구간(전처리 후)에서 적합하고 임의 프레임에 행 점수를 매긴다."""

    def __init__(self, train, seg_train, vendor, wins=(MAIN_W,), baselines: bool = True, tail: str = "exp"):
        self.wins, self.baselines, self.tail, self.vendor = tuple(wins), baselines, tail, vendor
        self.scaler = StandardScaler().fit(train[SENSORS])
        ztr = self.scaler.transform(train[SENSORS])
        self.ref_z3 = np.abs(ztr).max(1)
        self.ref_z2 = np.abs(ztr[:, :2]).max(1)
        cur = train[SENSORS[2]].to_numpy(float)
        self.ref_sine = {w: sine_score(cur, seg_train, w) for w in self.wins}
        self.tail_z3 = ExpTail(self.ref_z3)
        self.tail_sine = {w: ExpTail(self.ref_sine[w]) for w in self.wins}
        if baselines:
            self.nn = NearestNeighbors(n_neighbors=5).fit(ztr)
            self.iforest = IsolationForest(random_state=0).fit(ztr)
            _, Xw = _ae_windows(ztr, seg_train)
            self.ae = MLPRegressor(hidden_layer_sizes=(8, 3, 8), random_state=0, max_iter=300).fit(Xw, Xw)

    # --- 성분 ---
    def components(self, frame, seg):
        z = self.scaler.transform(frame[SENSORS])
        maxz3, maxz2 = np.abs(z).max(1), np.abs(z[:, :2]).max(1)
        comp = {"maxz3": maxz3, "maxz2": maxz2, "maxz_sensor": np.array(SENSORS)[np.abs(z).argmax(1)],
                "g_maxz3": self._transform(self.tail_z3, self.ref_z3, maxz3)}
        cur = frame[SENSORS[2]].to_numpy(float)
        for w in self.wins:
            s = sine_score(cur, seg, w)
            comp[f"sine_{w}"] = s
            comp[f"g_sine_{w}"] = self._transform(self.tail_sine[w], self.ref_sine[w], s)
        return comp, z

    def _transform(self, tail: ExpTail, ref, values):
        if self.tail == "capped":
            return capped_logp(ref, np.asarray(values, float))
        return tail(values)

    def score(self, frame, seg) -> tuple[dict, dict]:
        """모델명 → 행 점수. 결합은 fmax(g_maxz3, g_sine_w); 사인 NaN 행은 max-z만."""
        comp, z = self.components(frame, seg)
        out = {"maxz_vib2": comp["maxz2"], "maxz_3": comp["maxz3"]}
        if self.baselines:
            out["5nn_distance"] = self.nn.kneighbors(z)[0].mean(1)
            out["trailing_rms5"] = self.vendor.rms5(frame, self.scaler)
            out["isolation_forest"] = -self.iforest.score_samples(z)
            ae = np.full(len(frame), np.nan)
            idx, Xw = _ae_windows(z, seg)
            if len(idx):
                ae[idx] = ((self.ae.predict(Xw) - Xw) ** 2).mean(1)
            out["mlp_ae_w5"] = ae
        for w in self.wins:
            out[f"sine_w{w}"] = comp[f"sine_{w}"]
            out[f"combined_w{w}"] = np.fmax(comp["g_maxz3"], comp[f"g_sine_{w}"])
        return out, comp

    # --- 주 모델 저장/복원 (max-z + sine + 꼬리) ---
    def main_state(self, w: int) -> dict:
        return {"scaler_mean": self.scaler.mean_, "scaler_scale": self.scaler.scale_, "w": int(w), "tail": self.tail,
                "tail_z3": self.tail_z3.state(), "tail_sine": self.tail_sine[w].state(),
                "ref_z3_sorted": np.sort(self.ref_z3), "ref_sine_sorted": np.sort(self.ref_sine[w][np.isfinite(self.ref_sine[w])])}


class MainModel:
    """artifact 상태만으로 주 결합 점수를 계산한다(재학습 없음). predict.py가 사용한다."""

    def __init__(self, st: dict):
        self.mean, self.scale = np.asarray(st["scaler_mean"], float), np.asarray(st["scaler_scale"], float)
        self.w, self.tail = int(st["w"]), st.get("tail", "exp")
        self.tail_z3, self.tail_sine = ExpTail.from_state(st["tail_z3"]), ExpTail.from_state(st["tail_sine"])
        self.ref_z3, self.ref_sine = np.asarray(st["ref_z3_sorted"], float), np.asarray(st["ref_sine_sorted"], float)

    def _g(self, tail, ref, v):
        return capped_logp(ref, v) if self.tail == "capped" else tail(v)

    def score(self, frame, seg) -> dict:
        z = (frame[SENSORS].to_numpy(float) - self.mean) / self.scale
        maxz3 = np.abs(z).max(1)
        s = sine_score(frame[SENSORS[2]].to_numpy(float), seg, self.w)
        gz, gs = self._g(self.tail_z3, self.ref_z3, maxz3), self._g(self.tail_sine, self.ref_sine, s)
        return {"maxz3": maxz3, "maxz_sensor": np.array(SENSORS)[np.abs(z).argmax(1)], "sine": s, "g_maxz3": gz,
                "g_sine": gs, "combined": np.fmax(gz, gs)}
