"""Normal-only, record-causal frontier scores and joint record calibration.

Inputs are explicit records in sensor order upper vibration, lower vibration,
current, already transformed by the same matched quantizer for both classes.
No labels, filenames, absolute times or cross-record state enter any score.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "yejun/press_submission"))
from press import data as D
from press.calibrate import conformal_p
from press.scores import ExpTail
from vibration_branch import VibrationBranch
from competitor_reference import CompetitorReference

_spec = importlib.util.spec_from_file_location("frontier_guard_reference", ROOT / "yejun/press_guard/model.py")
guard = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = guard
_spec.loader.exec_module(guard)

CURRENT = ("V2", "C", "W", "CD")
VIBRATION = ("VR1", "VR3", "VD1", "VD3")


def candidate_grid():
    candidates = [dict(name=x, kind="single", components=[x], weight=1.0,
                       complexity=1, selectable=True) for x in CURRENT + VIBRATION]
    for current in CURRENT:
        for vibration in VIBRATION:
            for weight in (0.5, 1.0, 2.0):
                candidates.append(dict(name=f"{current}+{vibration}@{weight:g}", kind="fusion",
                                       components=[current, vibration], weight=weight,
                                       complexity=2 + int(vibration.endswith("3")), selectable=True))
    candidates += [dict(name=x, kind="reference", components=[x], weight=1.0,
                        complexity=3, selectable=False)
                   for x in ("REF_PCA", "REF_VIB", "REF_AND")]
    assert len(candidates) == 59
    return candidates


def as_frame(records):
    """Synthetic within-record timestamps only adapt the existing scorer API."""
    x = np.vstack(records)
    seg = np.concatenate([np.full(len(r), i, dtype=int) for i, r in enumerate(records)])
    seconds = np.concatenate([i * 1000.0 + np.arange(len(r)) * .1 for i, r in enumerate(records)])
    frame = pd.DataFrame(x, columns=D.SENSORS)
    frame[D.TIME] = pd.Timestamp("2020-01-01") + pd.to_timedelta(seconds, unit="s")
    return frame, seg


def split_values(values, records):
    return list(np.split(values, np.cumsum([len(r) for r in records])[:-1]))


def record_maxima(records):
    return np.array([np.max(np.where(np.isfinite(x), x, -np.inf), initial=-np.inf) for x in records])


class FrontierSuite:
    """All frozen candidates share fitted components; fit and cal are separate."""

    def fit(self, records):
        records = VibrationBranch._records(records)
        frame, seg = as_frame(records)
        # This same training frame is supplied as a throwaway adapter calibration;
        # its maxima are never used. All experiment thresholds use calibrate().
        self.guard_ = guard.GuardModel.fit(frame, frame)
        self.vibration_ = {
            name: VibrationBranch("difference_ridge" if name[1] == "D" else "ridge",
                                  int(name[-1])).fit(records) for name in VIBRATION}
        self.reference_ = CompetitorReference().fit(records)
        pairs = []
        for r in records:
            dx = np.diff(r[:, 2])
            if len(dx) >= 3:
                pairs.append((np.column_stack([np.ones(len(dx) - 2), dx[1:-1], dx[:-2]]), dx[2:]))
        self.diff_coef_ = np.linalg.lstsq(np.vstack([x for x, _ in pairs]),
                                         np.concatenate([y for _, y in pairs]), rcond=None)[0]
        self.diff_tail_ = ExpTail(np.concatenate(self._diff_residual(records)))
        self._current_cache = {}
        train = self.raw_parts(records)
        # Single components retain their original score scale. Fusion maps BOTH
        # branch scores to training tails before taking a weighted max.
        self.fusion_tails_ = {name: ExpTail(np.concatenate(train[name])) for name in CURRENT + VIBRATION}
        self.training_records_ = len(records)
        self.training_rows_ = sum(map(len, records))
        return self

    def _diff_residual(self, records):
        result = []
        for r in records:
            out = np.full(len(r), np.nan)
            dx = np.diff(r[:, 2])
            if len(dx) >= 3:
                out[3:] = np.abs(dx[2:] - self.diff_coef_[0]
                                 - self.diff_coef_[1] * dx[1:-1] - self.diff_coef_[2] * dx[:-2])
            result.append(out)
        return result

    def current_parts(self, records):
        fingerprint = hashlib.sha256()
        for r in records:
            fingerprint.update(np.asarray([len(r)], np.int64).tobytes())
            fingerprint.update(np.ascontiguousarray(r[:, 2]).tobytes())
        key = fingerprint.hexdigest()
        if key not in self._current_cache:
            frame, seg = as_frame(records)
            comp = self.guard_.components(frame, seg)
            waveform = split_values(comp["g_waveform"], records)
            dynamics = split_values(comp["g_dynamics"], records)
            diff = [self.diff_tail_(s) for s in self._diff_residual(records)]
            self._current_cache[key] = {
                "W": waveform,
                "C": [np.fmax(w, d) for w, d in zip(waveform, dynamics)],
                "CD": [np.fmax(w, d) for w, d in zip(waveform, diff)]}
            # The cache is an optimization, never training or temporal state.
            if len(self._current_cache) > 8:
                self._current_cache.pop(next(iter(self._current_cache)))
        out = dict(self._current_cache[key])
        magnitude = [self.guard_.tails["magnitude"](np.max(np.abs((r - self.guard_.mean) / self.guard_.scale), axis=1)) for r in records]
        out["V2"] = [np.fmax(c, m) for c, m in zip(out["C"], magnitude)]
        return out

    def raw_parts(self, records):
        records = VibrationBranch._records(records)
        out = self.current_parts(records)
        out.update({name: model.score(records) for name, model in self.vibration_.items()})
        ref = self.reference_.score_parts(records)
        out.update({"REF_PCA": ref["stage1"], "REF_VIB": ref["stage2"], "REF_AND": ref["and"]})
        return out

    def score(self, records, parts=None):
        parts = self.raw_parts(records) if parts is None else parts
        out = dict(parts)
        transformed = {name: [self.fusion_tails_[name](s) for s in parts[name]] for name in CURRENT + VIBRATION}
        for spec in candidate_grid():
            if spec["kind"] == "fusion":
                a, b = spec["components"]
                out[spec["name"]] = [np.fmax(x, spec["weight"] * y)
                                      for x, y in zip(transformed[a], transformed[b])]
        return out

    def calibrate(self, records):
        self.cal_ = {name: record_maxima(scores) for name, scores in self.score(records).items()}
        self.calibration_records_ = len(records)
        return self

    def alarms(self, scores, alpha=.01):
        out = {name: [np.nan_to_num(conformal_p(self.cal_[name], s), nan=1.0) <= alpha for s in values]
               for name, values in scores.items()}
        for vib in VIBRATION:
            out[f"OR_V2_{vib}"] = [x | y for x, y in zip(out["V2"], out[vib])]
        return out


class PrefixReplay:
    """Reference causal replay with explicit upstream record IDs.

    Stores the current record only (at most 50 rows in the source dataset).
    This is equivalence evidence, not a low-latency deployment implementation.
    """
    def __init__(self, suite, model, alpha=.01):
        self.suite, self.model, self.alpha = suite, model, alpha
        self.record_id, self.buffer = None, []

    def push(self, rows, record_id):
        if record_id != self.record_id:
            self.record_id, self.buffer = record_id, []
        if len(rows) == 0:
            return np.array([], dtype=float), np.array([], dtype=bool)
        start = len(self.buffer)
        self.buffer.extend(np.asarray(rows, float).tolist())
        scores = self.suite.score([np.asarray(self.buffer, float)])
        alarms = self.suite.alarms(scores, self.alpha)
        return scores[self.model][0][start:], alarms[self.model][0][start:]
