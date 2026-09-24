"""행 단위 이상 점수. 모든 모델은 정상 학습 구간으로만 적합한다 (07_policy_with_sine.py에서 이식).

점수가 없는 행(창이 덜 찬 구간 초반)은 NaN → 경보 없음, 분모에는 남는다 (예준 RMS 규칙과 같음).
"""
from functools import lru_cache

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from data import SENSORS

FREQS = np.arange(0.0, 5.0001, 0.005)
AE_WIN = 5


@lru_cache(maxsize=None)
def _hats(win):
    """주파수별 사인+상수 모델의 hat 행렬 (F, win, win)."""
    t = np.arange(win) * 0.1
    hats = []
    for f in FREQS:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
        hats.append(A @ np.linalg.pinv(A))
    return np.stack(hats)


def _window_index(groups, win):
    """같은 기록구간 안에서 최근 win관측이 모두 있는 행 번호."""
    n = len(groups)
    idx = np.arange(win - 1, n)
    return idx[groups[idx] == groups[idx - win + 1]]


def sine_score(frame, groups, win):
    """행별 1 - R²: 최근 win관측 전류에 단일 사인파(0~5Hz 격자) 최소제곱 피팅."""
    x = frame["AI2_Current"].to_numpy(float)
    score = np.full(len(x), np.nan)
    idx = _window_index(groups, win)
    if len(idx) == 0:
        return score
    W = np.stack([x[i - win + 1:i + 1] for i in idx])
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in _hats(win):
        r = W - W @ H.T
        np.minimum(best, (r * r).sum(1), out=best)
    score[idx] = np.where(sst > 0, best / sst, 0.0)
    return score


def tail_logp(ref, values):
    """정상 학습 점수 ref 대비 꼬리확률 -log10((#ref >= v + 1)/(n+1)). 점수 정규화용이지 p값 주장이 아니다."""
    ref = np.sort(ref[np.isfinite(ref)])
    out = np.full(len(values), np.nan)
    ok = np.isfinite(values)
    ge = len(ref) - np.searchsorted(ref, values[ok], side="left")
    out[ok] = -np.log10((ge + 1) / (len(ref) + 1))
    return out


def _ae_windows(z, groups):
    idx = _window_index(groups, AE_WIN)
    X = np.stack([z[i - AE_WIN + 1:i + 1].ravel() for i in idx]) if len(idx) else np.empty((0, 3 * AE_WIN))
    return idx, X


class Scorer:
    """정상 학습 구간에서 적합하고, 임의의 프레임에 행 점수를 매긴다.

    blocks: 예준 blocks() — 0.1초가 아닌 시각 차이에서 기록구간을 끊는다.
    """

    def __init__(self, train, blocks, wins=(8,), baselines=True):
        self.blocks, self.wins, self.baselines = blocks, tuple(wins), baselines
        self.scaler = StandardScaler().fit(train[SENSORS])
        ztr = self.scaler.transform(train[SENSORS])
        gtr = blocks(train)
        self.ref_z = np.abs(ztr).max(1)
        self.ref_s = {w: sine_score(train, gtr, w) for w in self.wins}
        self.nn = NearestNeighbors(n_neighbors=5).fit(ztr)
        if baselines:
            self.iforest = IsolationForest(random_state=0).fit(ztr)
            _, Xw = _ae_windows(ztr, gtr)
            self.ae = MLPRegressor(hidden_layer_sizes=(8, 3, 8), random_state=0, max_iter=300).fit(Xw, Xw)

    def components(self, frame):
        """결합 모델의 성분 (경보 사유 계산용): max-z 정규화 점수, 창별 사인 정규화 점수, max-z 센서."""
        groups = self.blocks(frame)
        z = self.scaler.transform(frame[SENSORS])
        maxz = np.abs(z).max(1)
        comp = {"maxz": maxz, "maxz_logp": tail_logp(self.ref_z, maxz),
                "maxz_sensor": np.array(SENSORS)[np.abs(z).argmax(1)]}
        for w in self.wins:
            s = sine_score(frame, groups, w)
            comp[f"sine_{w}"] = s
            comp[f"sine_{w}_logp"] = tail_logp(self.ref_s[w], s)
        return comp, z, groups

    def score(self, frame, yj):
        """모델명 -> 행 점수 배열."""
        comp, z, groups = self.components(frame)
        out = {"max_abs_z": comp["maxz"],
               "5nn_distance": self.nn.kneighbors(z)[0].mean(1),
               "trailing_rms5": yj.rms5(frame, self.scaler)}
        if self.baselines:
            out["isolation_forest"] = -self.iforest.score_samples(z)
            ae = np.full(len(frame), np.nan)
            idx, Xw = _ae_windows(z, groups)
            if len(idx):
                ae[idx] = ((self.ae.predict(Xw) - Xw) ** 2).mean(1)
            out["autoencoder_w5"] = ae
        for w in self.wins:
            out[f"sine_r2_{w}"] = comp[f"sine_{w}"]
            # fmax: 사인 점수가 없는(구간 초반) 쪽은 max-z만 사용
            out[f"maxz_plus_sine_{w}"] = np.fmax(comp["maxz_logp"], comp[f"sine_{w}_logp"])
        return out, comp
