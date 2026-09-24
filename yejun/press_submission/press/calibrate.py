"""보정과 경보 기준 — PLAN.md §4.2.

- 주 기준 conformal: 정상 보정 구간 최댓값 M_j로 p(s) = (1 + #{M_j ≥ s})/(n+1). p ≤ α이면 경보.
  alpha_grid = floor(α(n+1))/(n+1). 경보 ⇔ s > (a+1)번째 큰 보정값, a = floor(α(n+1)) − 1. a<0이면 경보 불가.
- 참고 기준 cutoff: vendor cutoff_at_budget(허용 초과 floor(budget·n), 문턱 = 정렬값[n−allowed−1], 경보 ⇔ s > 문턱).
- 행 단위 cutoff는 과거 비교용.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist

ALPHAS = (0.01, 0.03, 0.05)


def segment_max(scores: np.ndarray, seg: np.ndarray) -> np.ndarray:
    safe = np.where(np.isfinite(scores), scores, -np.inf)
    return pd.Series(safe).groupby(seg).max().to_numpy()


def conformal_p(cal_values: np.ndarray, scores: np.ndarray) -> np.ndarray:
    ref = np.sort(np.where(np.isfinite(cal_values), cal_values, -np.inf))
    out = np.full(len(scores), np.nan)
    ok = np.isfinite(scores)
    ge = len(ref) - np.searchsorted(ref, scores[ok], side="left")   # #{cal >= s}
    out[ok] = (ge + 1) / (len(ref) + 1)
    return out


def alpha_grid(alpha: float, n: int) -> float:
    return math.floor(alpha * (n + 1)) / (n + 1)


def conformal_threshold(cal_values: np.ndarray, alpha: float) -> tuple[float, int]:
    """경보 ⇔ score > threshold 가 p ≤ α와 같아지는 문턱. 반환 (threshold, 허용 초과 수 a). a<0이면 +inf(경보 불가)."""
    ref = np.sort(np.where(np.isfinite(cal_values), cal_values, -np.inf))[::-1]   # 내림차순
    n = len(ref)
    a = math.floor(alpha * (n + 1)) - 1
    if a < 0:
        return float("inf"), a
    thr = float(ref[a]) if a < n else float("-inf")   # (a+1)번째 큰 값
    return thr, a


def cutoff_threshold(cal_values: np.ndarray, budget: float) -> tuple[float, int]:
    values = np.sort(np.where(np.isfinite(cal_values), cal_values, -np.inf))
    allowed = math.floor(budget * len(values))
    thr = float(values[max(0, len(values) - allowed - 1)])
    assert (values > thr).sum() <= allowed
    return thr, allowed


def binomial_upper95(k: int, n: int) -> float:
    """정상 평가 구간 알림 k/n의 독립 가정 단측 95% 상한(Clopper–Pearson). 참고치이며 시간 의존성은 반영하지 않는다."""
    if n <= 0:
        return float("nan")
    if k >= n:
        return 1.0
    return float(beta_dist.ppf(0.95, k + 1, n - k))


def thresholds_for(cal_values: np.ndarray, unit: str) -> list[dict]:
    """(unit, criterion, alpha) 조합별 문턱. 구간 단위: conformal + cutoff. 행 단위: cutoff만."""
    rows = []
    n = len(cal_values)
    for alpha in ALPHAS:
        if unit == "recording_segments":
            thr, a = conformal_threshold(cal_values, alpha)
            rows.append(dict(calibration_unit=unit, criterion="conformal", alpha=alpha, alpha_grid=alpha_grid(alpha, n),
                             allowed_exceedances=a, n_calibration=n, threshold=thr, alarm_possible=np.isfinite(thr)))
        thr, allowed = cutoff_threshold(cal_values, alpha)
        rows.append(dict(calibration_unit=unit, criterion="cutoff", alpha=alpha, alpha_grid=(allowed + 1) / (n + 1),
                         allowed_exceedances=allowed, n_calibration=n, threshold=thr, alarm_possible=True))
    return rows


def mc_check_conformal(n_cal: int = 120, alphas=ALPHAS, reps: int = 20000, seed: int = 0) -> list[dict]:
    """연속 iid 합성 점수로 순위 p값 구현을 확인한다: 새 보정셋·새 평가점을 반복해 P(p ≤ α) ≈ alpha_grid."""
    rng = np.random.default_rng(seed)
    cal = rng.standard_normal((reps, n_cal))
    new = rng.standard_normal(reps)
    ge = (cal >= new[:, None]).sum(1)
    p = (ge + 1) / (n_cal + 1)
    out = []
    for a in alphas:
        out.append(dict(n_cal=n_cal, alpha=a, alpha_grid=alpha_grid(a, n_cal), realized=float((p <= a).mean()),
                        mc_se=float(np.sqrt(alpha_grid(a, n_cal) * (1 - alpha_grid(a, n_cal)) / reps)), reps=reps))
    return out
