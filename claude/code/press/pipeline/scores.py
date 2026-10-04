"""행 단위 이상 점수. 모든 모델은 정상 학습 구간으로만 적합한다.

성분 점수(component)는 융합 모델(fusion.py)의 입력이고, 단일 모델 점수(model)는 비교표용이다.
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
COMPONENTS = ("maxz", "knn5", "ae5", "sine")  # 융합 성분 (사전 고정, 균등 가중)


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


def sine_misfit(W):
    """창 행렬 W (n, win)마다 1 - R²: 단일 사인파(0~5Hz 격자) + 상수 최소제곱."""
    win = W.shape[1]
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(W), np.inf)
    for H in _hats(win):
        r = W - W @ H.T
        np.minimum(best, (r * r).sum(1), out=best)
    return np.where(sst > 0, best / np.where(sst > 0, sst, 1), 0.0)


def sine_score(frame, groups, win):
    """행별 1 - R²: 같은 기록구간 안 최근 win관측 전류."""
    x = frame["AI2_Current"].to_numpy(float)
    score = np.full(len(x), np.nan)
    idx = _window_index(groups, win)
    if len(idx):
        score[idx] = sine_misfit(np.stack([x[i - win + 1:i + 1] for i in idx]))
    return score


def tail_logp(ref, values):
    """[07 재현 검사 전용] 학습 ECDF 꼬리확률 -log10((#ref>=v+1)/(n+1)). 최댓값 log10(n+1)에서 포화하므로
    융합에는 쓰지 않는다 (2026-09-24 검증에서 발견한 결함)."""
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
    """정상 학습 구간에서 적합하고, 임의의 프레임에 성분·모델 점수를 매긴다.

    blocks: 예준 blocks() — 0.1초가 아닌 시각 차이에서 기록구간을 끊는다.
    wins: 사인 창 길이들. 첫 번째가 융합 모델의 창(규칙으로 선택한 값)이다.
    """

    def __init__(self, train, blocks, wins=(8,), baselines=True):
        self.blocks, self.wins, self.baselines = blocks, tuple(wins), baselines
        self.scaler = StandardScaler().fit(train[SENSORS])
        ztr = self.scaler.transform(train[SENSORS])
        gtr = blocks(train)
        self.nn = NearestNeighbors(n_neighbors=5).fit(ztr)
        _, Xw = _ae_windows(ztr, gtr)
        self.ae = MLPRegressor(hidden_layer_sizes=(8, 3, 8), random_state=0, max_iter=300).fit(Xw, Xw)
        if baselines:
            self.iforest = IsolationForest(random_state=0).fit(ztr)
        # 학습 구간 성분 점수 = 꼬리 모델(fusion.TailModel)의 기준 분포
        nn6 = NearestNeighbors(n_neighbors=6).fit(ztr).kneighbors(ztr)[0][:, 1:].mean(1)  # 자기 자신 제외
        self.train_components = {"maxz": np.abs(ztr).max(1), "knn5": nn6, "ae5": self._ae(ztr, gtr)}
        for w in self.wins:
            self.train_components[f"sine_{w}"] = sine_score(train, gtr, w)

    def _ae(self, z, groups):
        out = np.full(len(z), np.nan)
        idx, Xw = _ae_windows(z, groups)
        if len(idx):
            out[idx] = ((self.ae.predict(Xw) - Xw) ** 2).mean(1)
        return out

    def components(self, frame):
        """성분 점수 dict (+ max-z를 만든 센서). 키: maxz, knn5, ae5, sine_{w}."""
        groups = self.blocks(frame)
        z = self.scaler.transform(frame[SENSORS])
        comp = {"maxz": np.abs(z).max(1), "knn5": self.nn.kneighbors(z)[0].mean(1), "ae5": self._ae(z, groups)}
        for w in self.wins:
            comp[f"sine_{w}"] = sine_score(frame, groups, w)
        return comp, np.array(SENSORS)[np.abs(z).argmax(1)], z

    def models(self, frame, yj, comp=None, z=None):
        """단일 모델 점수 dict (비교표용)."""
        if comp is None:
            comp, _, z = self.components(frame)
        out = {"max_abs_z": comp["maxz"], "5nn_distance": comp["knn5"],
               "trailing_rms5": yj.rms5(frame, self.scaler), "autoencoder_w5": comp["ae5"]}
        if self.baselines:
            out["isolation_forest"] = -self.iforest.score_samples(z)
        for w in self.wins:
            out[f"sine_r2_{w}"] = comp[f"sine_{w}"]
        # [07 재현 검사 전용] 포화하는 옛 결합
        if 8 in self.wins:
            out["legacy_maxz_plus_sine_8"] = np.fmax(tail_logp(self.train_components["maxz"], comp["maxz"]),
                                                     tail_logp(self.train_components["sine_8"], comp["sine_8"]))
        return out
