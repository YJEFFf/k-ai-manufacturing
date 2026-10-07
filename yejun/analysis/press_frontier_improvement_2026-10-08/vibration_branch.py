"""Causal vibration innovation branch for the separate frontier experiment.

This module does not read files or set alert thresholds. Fit normal records only;
calibrate the *joint* system score on separate normal recording maxima afterwards.
Ridge alpha is fixed at 1.0. Every lag model has its own training residual
Ledoit--Wolf covariance, because the first few observations have less context.
"""
from __future__ import annotations

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.linear_model import Ridge


class VibrationBranch:
    """Predict two vibration channels from up to five prior three-channel rows.

    ``difference_ridge`` operates entirely on within-record first differences.
    Its first possible score is position 2 (zero based); ``ridge`` starts at 1.
    Scores are nonnegative squared residual Mahalanobis distances. ``smooth=3``
    averages the last three available consecutive scores and waits for all three.
    Neither prediction nor smoothing ever crosses a record boundary.
    """

    MAX_LAG = 5
    RIDGE_ALPHA = 1.0
    COVARIANCE_FLOOR = 1e-8  # Standardized target units; numerical stability only.

    def __init__(self, kind="ridge", smooth=1):
        if kind not in ("ridge", "difference_ridge"):
            raise ValueError("kind must be 'ridge' or 'difference_ridge'")
        if smooth not in (1, 3):
            raise ValueError("smooth must be 1 or 3")
        self.kind = kind
        self.smooth = smooth

    @staticmethod
    def _records(records):
        result = []
        for record in records:
            x = np.asarray(record, dtype=float)
            if x.ndim != 2 or x.shape[1] != 3:
                raise ValueError("Each record must have shape (n, 3)")
            if not np.isfinite(x).all():
                raise ValueError("Records must contain finite sensor values")
            result.append(x)
        return result

    def _transform(self, record):
        return np.diff(record, axis=0) if self.kind == "difference_ridge" else record

    @staticmethod
    def _design(z, lag):
        if len(z) <= lag:
            return np.empty((0, 3 * lag)), np.empty((0, 2))
        indices = np.arange(lag, len(z))
        X = np.hstack([z[indices - k] for k in range(1, lag + 1)])
        return X, z[indices, :2]

    def fit(self, records):
        """Fit using normal training records; return self for chaining.

        Constant training channels use scale 1.0. Lag lengths with fewer than
        three training examples remain unavailable instead of borrowing records.
        """
        records = self._records(records)
        transformed = [self._transform(x) for x in records]
        nonempty = [x for x in transformed if len(x)]
        if not nonempty:
            raise ValueError("No eligible training observations")
        all_x = np.vstack(nonempty)
        self.mean_ = all_x.mean(axis=0)
        scale = all_x.std(axis=0)
        self.scale_ = np.where(scale > 1e-12, scale, 1.0)
        standardized = [(x - self.mean_) / self.scale_ for x in transformed]
        self.models_ = {}
        self.residual_centers_ = {}
        self.precisions_ = {}
        self.covariances_ = {}
        self.training_examples_ = {}
        self.shrinkage_ = {}
        for lag in range(1, self.MAX_LAG + 1):
            pairs = [self._design(x, lag) for x in standardized if len(x) > lag]
            if not pairs:
                continue
            X = np.vstack([p[0] for p in pairs])
            y = np.vstack([p[1] for p in pairs])
            if len(X) < 3:
                continue
            model = Ridge(alpha=self.RIDGE_ALPHA).fit(X, y)
            residuals = y - model.predict(X)
            covariance = LedoitWolf().fit(residuals)
            eigenvalues, eigenvectors = np.linalg.eigh(covariance.covariance_)
            eigenvalues = np.maximum(eigenvalues, self.COVARIANCE_FLOOR)
            self.models_[lag] = model
            self.residual_centers_[lag] = covariance.location_.copy()
            self.covariances_[lag] = (eigenvectors * eigenvalues) @ eigenvectors.T
            self.precisions_[lag] = (eigenvectors / eigenvalues) @ eigenvectors.T
            self.training_examples_[lag] = len(X)
            self.shrinkage_[lag] = float(covariance.shrinkage_)
        if not self.models_:
            raise ValueError("Need at least three eligible within-record lag examples")
        self.training_records_ = len(records)
        self.training_rows_ = sum(len(x) for x in records)
        return self

    def score(self, records):
        """Return one causal score array per record; unavailable rows are NaN."""
        if not getattr(self, "models_", None):
            raise ValueError("Fit the branch before scoring")
        outputs = []
        offset = int(self.kind == "difference_ridge")
        for record in self._records(records):
            z = (self._transform(record) - self.mean_) / self.scale_
            out = np.full(len(record), np.nan)
            for lag, model in self.models_.items():
                X, y = self._design(z, lag)
                if not len(X):
                    continue
                if lag < self.MAX_LAG:
                    X, y = X[:1], y[:1]
                residual = y - model.predict(X) - self.residual_centers_[lag]
                values = np.einsum("ij,jk,ik->i", residual, self.precisions_[lag], residual)
                start = lag + offset
                out[start:start + len(values)] = np.maximum(values, 0.0)
            if self.smooth == 3:
                smoothed = np.full(len(out), np.nan)
                for i in range(2, len(out)):
                    if np.isfinite(out[i - 2:i + 1]).all():
                        smoothed[i] = out[i - 2:i + 1].mean()
                out = smoothed
            outputs.append(out)
        return outputs

    def metadata(self):
        """Small JSON-compatible fit summary; model itself supports joblib."""
        if not getattr(self, "models_", None):
            raise ValueError("Fit the branch before requesting metadata")
        return dict(kind=self.kind, smooth=self.smooth, max_lag=self.MAX_LAG,
                    ridge_alpha=self.RIDGE_ALPHA, covariance_floor=self.COVARIANCE_FLOOR,
                    training_records=self.training_records_, training_rows=self.training_rows_,
                    training_examples=self.training_examples_, shrinkage=self.shrinkage_,
                    mean=self.mean_.tolist(), scale=self.scale_.tolist())
