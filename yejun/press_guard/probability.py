"""이상 확률 층 — v2 점수를 라벨로 보정한 단조 함수와 사전 비율 보정.

경보·알림은 이 층과 무관하다(정상 자료만으로 정한 conformal 규칙). 이 층은 공식 과제의 "이상 확률" 출력을 위한 것이다.

    LR(s) = [P̂(이상 | s) / (1 − P̂(이상 | s))] / [π_fit / (1 − π_fit)]
    P(이상 | s; π) = π·LR(s) / (π·LR(s) + 1 − π)

- P̂: 정상 보정 구간 행(0)과 이상 기록 행(1)에 맞춘 등방(isotonic) 회귀. π_fit은 그 적합 자료의 이상 비율이다.
- LR(우도비)은 사전 비율과 무관하다. π는 현장의 이상 비율에 대한 가정이다(기본 1%).
- 증거력 상한: 알림은 보정 단위 n개의 conformal 순위로 정한다. 정상에서 한 알림 단위가 최상위가 될 확률은
  1/(n+1)이므로, 한 알림이 줄 수 있는 우도비는 (n+1)×탐지율을 넘지 못한다. 행 확률도 그 행이 속한 알림 단위가
  낼 수 있는 증거보다 크게 말하지 않도록 LR을 (n+1)에서 자른다(보정 120단위면 121). 행 사이 자기상관 때문에
  행 수를 표본 수로 쓰면 증거를 과대평가한다.
- 낮은 점수 쪽: 이상 행이 하나도 없는 구간(P̂=0)은 등방 회귀의 가장 작은 유한 LR로 둔다(0으로 확신하지 않음).
- 이상 자료는 한 날 3분의 연속 기록이라 LR은 그 이상 모양에서 나온 점수 분포에 맞춰져 있다.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

VERSION = "press-guard-probability-v1"
DEFAULT_PRIOR = .01
EPS = 1e-9


def posterior(lr, prior):
    """우도비와 사전 비율로 사후확률."""
    lr = np.asarray(lr, float)
    return prior * lr / (prior * lr + 1 - prior)


class ProbabilityCalibrator:
    def __init__(self, state):
        if state.get("version") != VERSION:
            raise ValueError("지원하지 않는 확률 보정 형식")
        self.state = state
        self.x = np.asarray(state["thresholds_x"], float)
        self.y = np.asarray(state["thresholds_y"], float)
        self.pi_fit = float(state["pi_fit"])
        self.lr_cap, self.lr_floor = float(state["lr_cap"]), float(state["lr_floor"])
        if (len(self.x) < 2 or len(self.x) != len(self.y) or np.any(np.diff(self.x) < 0) or np.any(np.diff(self.y) < 0)
                or not 0 < self.pi_fit < 1 or not 0 < self.lr_floor <= self.lr_cap):
            raise ValueError("확률 보정 계수 오류")

    @classmethod
    def fit(cls, normal_scores, abnormal_scores, *, calibration_units, split="custom", source=None):
        """calibration_units: 이 모델의 conformal 보정 단위 수(증거력 상한 n+1)."""
        s0 = np.asarray(normal_scores, float); s1 = np.asarray(abnormal_scores, float)
        s0, s1 = s0[np.isfinite(s0)], s1[np.isfinite(s1)]
        x = np.r_[s0, s1]; y = np.r_[np.zeros(len(s0)), np.ones(len(s1))]
        iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip").fit(x, y)
        odds_fit = y.mean() / (1 - y.mean())
        inner = iso.y_thresholds_[(iso.y_thresholds_ > 0) & (iso.y_thresholds_ < 1)]
        finite = inner / (1 - inner) / odds_fit if len(inner) else np.array([1.0])
        cap = float(calibration_units + 1) if calibration_units is not None else float("inf")   # None은 평가 비교용(상한 없음, 저장 불가)
        return cls(dict(version=VERSION, split=split, thresholds_x=iso.X_thresholds_.tolist(), thresholds_y=iso.y_thresholds_.tolist(),
                        pi_fit=float(y.mean()), n_normal=int(len(s0)), n_abnormal=int(len(s1)), calibration_units=None if calibration_units is None else int(calibration_units),
                        lr_cap=cap, lr_floor=float(min(finite.min(), cap)), default_prior=DEFAULT_PRIOR, source=source or {},
                        note="정상 보정 구간 행과 이상 기록 행으로 맞춘 등방 회귀. LR 상한 = 보정 단위 수 + 1. 경보 규칙과 무관"))

    def fitted(self, scores):
        s = np.asarray(scores, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        out[ok] = np.interp(s[ok], self.x, self.y)      # 등방 회귀 예측(sklearn predict와 같은 선형 보간)
        return out

    def likelihood_ratio(self, scores):
        p = self.fitted(scores)
        inner = np.clip(p, EPS, 1 - EPS)
        lr = inner / (1 - inner) / (self.pi_fit / (1 - self.pi_fit))
        lr = np.where(p <= 0, self.lr_floor, np.minimum(lr, self.lr_cap))   # 증거력 상한은 conformal 순위 한계
        return np.where(np.isfinite(p), lr, np.nan)

    def probability(self, scores, prior=DEFAULT_PRIOR):
        if not 0 < prior < 1:
            raise ValueError("사전 비율은 0과 1 사이여야 한다")
        return posterior(self.likelihood_ratio(scores), prior)

    def save(self, path):
        canonical = json.dumps(self.state, ensure_ascii=False, sort_keys=True, allow_nan=False)
        envelope = dict(sha256=hashlib.sha256(canonical.encode()).hexdigest(), state=self.state)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(envelope, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    @classmethod
    def load(cls, path):
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
        canonical = json.dumps(envelope["state"], ensure_ascii=False, sort_keys=True, allow_nan=False)
        if hashlib.sha256(canonical.encode()).hexdigest() != envelope["sha256"]:
            raise ValueError("확률 보정 상태 해시 불일치")
        return cls(envelope["state"])


def grouped_evaluation(normal_fit_scores, normal_eval_scores, abnormal_scores, abnormal_records, folds, calibration_units):
    """이상 기록을 겹으로 떼어 낸 교차 보정. 떼어 둔 이상 행과 정상 평가 행의 확률을 평가 자료의 이상 비율에 맞춰 돌려준다.

    정상 평가 행은 어느 보정기의 적합에도 쓰지 않는다. 겹마다의 정상 평가 확률은 평균한다."""
    abnormal_scores = np.asarray(abnormal_scores, float); abnormal_records = np.asarray(abnormal_records)
    pa = np.full(len(abnormal_scores), np.nan); pn = []
    pi_eval = len(abnormal_scores) / (len(abnormal_scores) + len(normal_eval_scores))
    for hold in folds:
        keep = ~np.isin(abnormal_records, hold)
        cal = ProbabilityCalibrator.fit(normal_fit_scores, abnormal_scores[keep], calibration_units=calibration_units)
        pa[~keep] = cal.probability(abnormal_scores[~keep], prior=pi_eval)
        pn.append(cal.probability(normal_eval_scores, prior=pi_eval))
    return np.mean(pn, axis=0), pa, pi_eval


def expected_calibration_error(y, p, bins=10):
    y, p = np.asarray(y, float), np.asarray(p, float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & ((p < hi) | (hi == 1))
        if k.any():
            total += k.mean() * abs(p[k].mean() - y[k].mean())
    return float(total)


def alert_evidence_bound(calibration_units, detection_rate=1.0):
    """라벨 적합 없이 쓰는 알림 한 건의 우도비 상한: 정상에서 알림 확률 = 1/(n+1)(conformal), 이상에서 ≤ 탐지율."""
    return (calibration_units + 1) * detection_rate


def sellke_bayes_factor(p):
    """Sellke–Bayarri–Berger 최소 베이즈 인수 −e·p·ln p(p < 1/e). 참고값이다.

    연속 p값을 정확히 관측하고, 대립에서 p가 Beta(ξ,1) 족을 따를 때의 회의적 환산이다. conformal 알림은 "p ≤ 1/(n+1)"이라는
    사건이라 이 값이 알림 한 건의 우도비 상한이 아니다. 알림의 상한은 alert_evidence_bound((n+1)×탐지율)다."""
    p = float(p)
    return -math.e * p * math.log(p) if 0 < p < 1 / math.e else 1.0
