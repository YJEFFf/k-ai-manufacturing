"""Independently implemented comparator motivated by public CARE-Press methods.

Method provenance, inspected 2026-10-08:
https://github.com/chlanstjr0301/workspace---claude/tree/
518f9ada91fa8adb858ef59ed7c523eaf6e77b02
Specifically src/features.py, src/models.py and run_all.py. No license file was
found in the inspected snapshot; source files have not been copied here.

This is a controlled method comparator, NOT a reproduction of their evaluation:
the caller supplies already segmented/quantized records, fits normal training
records only, and calibrates normal record maxima externally. This module has
no labels, threshold selection, alarm persistence, or cross-record state.

``score_parts`` exposes two raw statistics plus a train-scaled AND statistic.
The latter is min(s1/q95_train(s1), s2/q95_train(s2)); calibrating this statistic
is different from AND-ing two separately calibrated conformal p-values.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


SOURCE_COMMIT = "518f9ada91fa8adb858ef59ed7c523eaf6e77b02"
SOURCE_URL = f"https://github.com/chlanstjr0301/workspace---claude/tree/{SOURCE_COMMIT}"
WINDOW = 10
_EPS = 1e-12
_CHANNELS = ("vibration_upper", "vibration_lower", "current")
FEATURE_SCHEMA = tuple(
    f"{stat}_{channel}"
    for stat in ("std", "peak_to_peak", "rms", "centered_ac1", "centered_ac2", "centered_zcr")
    for channel in _CHANNELS
) + ("vibration_correlation", "absolute_vibration_correlation",
     "vibration_std_ratio", "current_mean", "current_abs_mean")
VIBRATION_COLUMNS = np.asarray(
    [i for i, name in enumerate(FEATURE_SCHEMA) if "current" not in name], dtype=int
)


def _records(records: Iterable[np.ndarray]) -> list[np.ndarray]:
    validated = []
    for record in records:
        array = np.asarray(record, dtype=np.float64)
        if array.ndim != 2 or array.shape[1] != 3:
            raise ValueError("Each record must have shape (samples, 3).")
        if not np.isfinite(array).all():
            raise ValueError("Records must contain finite values only.")
        validated.append(array)
    return validated


def _correlation(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    left = left - left.mean(axis=1, keepdims=True)
    right = right - right.mean(axis=1, keepdims=True)
    scale = np.sqrt(np.mean(left * left, axis=1) * np.mean(right * right, axis=1))
    return np.mean(left * right, axis=1) / (scale + _EPS)


def record_features(record: np.ndarray) -> np.ndarray:
    """Return (max(n-9, 0), 23) causal, stride-one window features.

    Autocorrelation uses mean(z[t] z[t-k]) / mean(z**2), with the
    lag-product mean taken over 10-k terms. It is not np.corrcoef(lagged).
    ZCR treats exactly zero centered values as nonnegative.
    """
    record = _records([record])[0]
    if len(record) < WINDOW:
        return np.empty((0, len(FEATURE_SCHEMA)), dtype=float)
    windows = np.lib.stride_tricks.sliding_window_view(record, WINDOW, axis=0)
    windows = windows.transpose(0, 2, 1)  # samples, time, channels
    centered = windows - windows.mean(axis=1, keepdims=True)
    variance = np.mean(centered * centered, axis=1)
    blocks = [np.sqrt(variance), np.ptp(windows, axis=1),
              np.sqrt(np.mean(windows * windows, axis=1))]
    for lag in (1, 2):
        blocks.append(np.mean(centered[:, lag:] * centered[:, :-lag], axis=1)
                      / (variance + _EPS))
    positive = centered >= 0
    blocks.append(np.mean(positive[:, 1:] != positive[:, :-1], axis=1))
    upper, lower = windows[:, :, 0], windows[:, :, 1]
    current = windows[:, :, 2]
    extras = np.column_stack([
        _correlation(upper, lower),
        _correlation(np.abs(upper), np.abs(lower)),
        np.std(upper, axis=1) / (np.std(lower, axis=1) + _EPS),
        current.mean(axis=1), np.abs(current).mean(axis=1),
    ])
    return np.concatenate([*blocks, extras], axis=1)


class CompetitorReference:
    """PCA-MSPC on 23 features; shrinkage Mahalanobis on 15 vibration features.

    Fit accepts only normal training records by contract. Scores align with the
    original row count; rows 0..8 of every record are unavailable (NaN).
    Caller owns segmentation, normal-only calibration, and metrics.
    """

    feature_schema = FEATURE_SCHEMA
    vibration_feature_schema = tuple(FEATURE_SCHEMA[i] for i in VIBRATION_COLUMNS)

    def __init__(self) -> None:
        self.fitted_ = False

    def fit(self, normal_records: Iterable[np.ndarray]) -> "CompetitorReference":
        records = _records(normal_records)
        usable = [record_features(record) for record in records if len(record) >= WINDOW]
        if not usable or sum(map(len, usable)) < 2:
            raise ValueError("At least two normal training windows are required.")
        features = np.vstack(usable)
        self.stage1_scaler_ = StandardScaler().fit(features)
        standardized = self.stage1_scaler_.transform(features)
        if not np.any(np.var(standardized, axis=0) > 0):
            raise ValueError("PCA requires variation in normal training windows.")
        self.pca_ = PCA(n_components=0.95, svd_solver="full").fit(standardized)
        projected = self.pca_.transform(standardized)
        self.pc_variance_ = np.var(projected, axis=0) + _EPS
        t2, spe = self._pca_parts(standardized)
        self.t2_scale_ = float(np.quantile(t2, 0.95) + _EPS)
        self.spe_scale_ = float(np.quantile(spe, 0.95) + _EPS)
        vibration = features[:, VIBRATION_COLUMNS]
        self.stage2_scaler_ = StandardScaler().fit(vibration)
        self.covariance_ = LedoitWolf().fit(self.stage2_scaler_.transform(vibration))
        stage1 = np.maximum(t2 / self.t2_scale_, spe / self.spe_scale_)
        stage2 = self.covariance_.mahalanobis(self.stage2_scaler_.transform(vibration))
        self.and_scale_ = np.quantile(np.column_stack([stage1, stage2]), 0.95, axis=0) + _EPS
        self.training_records_ = len(records)
        self.training_windows_ = len(features)
        self.fitted_ = True
        return self

    def _pca_parts(self, standardized: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        projected = self.pca_.transform(standardized)
        residual = standardized - self.pca_.inverse_transform(projected)
        return (np.sum(projected * projected / self.pc_variance_, axis=1),
                np.sum(residual * residual, axis=1))

    def score_parts(self, records: Iterable[np.ndarray]) -> dict[str, list[np.ndarray]]:
        if not self.fitted_:
            raise RuntimeError("Call fit(normal_records) before scoring.")
        result = {"stage1": [], "stage2": [], "and": []}
        for record in _records(records):
            aligned = {name: np.full(len(record), np.nan) for name in result}
            if len(record) >= WINDOW:
                features = record_features(record)
                t2, spe = self._pca_parts(self.stage1_scaler_.transform(features))
                stage1 = np.maximum(t2 / self.t2_scale_, spe / self.spe_scale_)
                stage2 = self.covariance_.mahalanobis(
                    self.stage2_scaler_.transform(features[:, VIBRATION_COLUMNS]))
                aligned["stage1"][WINDOW - 1:] = stage1
                aligned["stage2"][WINDOW - 1:] = stage2
                aligned["and"][WINDOW - 1:] = np.minimum(
                    stage1 / self.and_scale_[0], stage2 / self.and_scale_[1])
            for name in result:
                result[name].append(aligned[name])
        return result

    def score(self, records: Iterable[np.ndarray], component: str = "stage1") -> list[np.ndarray]:
        if component not in {"stage1", "stage2", "and"}:
            raise ValueError("component must be 'stage1', 'stage2', or 'and'.")
        return self.score_parts(records)[component]
