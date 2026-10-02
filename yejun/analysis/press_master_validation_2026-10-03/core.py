"""Completed-record reference implementation of press master v1.

This is an experiment, not a row-causal predictor or field fault-probability model.
Fit objects never receive calibration/evaluation records during fitting.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MASTER = ROOT / "yejun/plans/press_master_2026-10-03"
PROTOCOL = json.loads((MASTER / "protocol.json").read_text())
DESIGN = json.loads((HERE / "design_v1.json").read_text())
COLS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
AXES = ["v0_rms", "v1_rms", "v0_peak", "v1_peak", "i_raw", "i_ac", "i_residual"]
BINS = [(1, 9), (10, 19), (20, 39), (40, 50)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, obj):
    def default(x):
        if isinstance(x, np.ndarray):
            return x.tolist()
        if isinstance(x, np.generic):
            return x.item()
        if isinstance(x, Path):
            return str(x)
        raise TypeError(type(x).__name__)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                     default=default, allow_nan=False) + "\n")


@dataclass
class Record:
    parent: int
    x: np.ndarray
    start_m: float
    end_m: float
    decision_m: float
    source_rows: tuple[int, ...]
    source_namespace: str = "normal"


def records_from_frame(raw):
    raw = raw.copy()
    raw["source_row"] = np.arange(len(raw))
    raw["time"] = pd.to_datetime(raw.TimeStamp, errors="raise")
    if raw.time.isna().any() or not np.isfinite(raw[COLS].to_numpy()).all():
        raise ValueError("Invalid timestamp or nonfinite sensor; quality contract violation")
    duplicate = raw.duplicated(["TimeStamp"] + COLS)
    retained = raw.loc[~duplicate].copy()
    ns = retained.time.astype("int64").to_numpy()
    if np.any(np.diff(ns) <= 0):
        raise ValueError("Backward or conflicting same-time observation; do not sort")
    boundary = np.r_[True, (np.diff(ns) < 80_000_000) | (np.diff(ns) > 120_000_000)]
    retained["parent"] = boundary.cumsum() - 1
    mapping = raw.merge(retained[["TimeStamp"] + COLS + ["parent"]],
                        on=["TimeStamp"] + COLS, how="left", validate="many_to_one")
    if mapping.parent.isna().any():
        raise AssertionError("Lost source-row mapping")
    out = []
    for parent, g in retained.groupby("parent", sort=False):
        first = (g.time.iloc[0].value - ns[0]) / 60e9
        last = (g.time.iloc[-1].value - ns[0]) / 60e9
        # Search retained rows, not original offsets, after duplicate removal.
        end_position = int(np.searchsorted(ns, g.time.iloc[-1].value))
        next_time = ((ns[end_position+1] - ns[0]) / 60e9
                     if end_position+1 < len(ns) else np.inf)
        out.append(Record(int(parent), g[COLS].to_numpy(dtype=float), first, last,
                          min(last + 0.5/60, next_time),
                          tuple(mapping.loc[mapping.parent.eq(parent), "source_row"].astype(int))))
    return out, {"original_rows": len(raw), "retained_rows": len(retained),
                 "duplicate_rows": raw.loc[duplicate, "source_row"].astype(int).tolist(),
                 "records": len(out), "source_mapping_rows": sum(len(r.source_rows) for r in out)}


def load_records(kind="normal"):
    filename = "press_data_normal.csv" if kind == "normal" else "outlier_data.csv"
    path = ROOT / "데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전" / filename
    if sha(path) != PROTOCOL["input"][kind + "_sha256"]:
        raise ValueError("Source hash mismatch")
    records, contract = records_from_frame(pd.read_csv(path))
    return [replace(r, source_namespace=kind) for r in records], contract


def split_records(records, fold):
    roles = {}
    for role in ["fit", "cal", "evaluation"]:
        lo, hi = PROTOCOL["folds_minutes"][fold][role]
        hi = np.inf if hi is None else hi
        roles[role] = [r for r in records if r.start_m >= lo and r.end_m < hi]
    ids = [set(r.parent for r in roles[k]) for k in roles]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])
    return roles


def sine_basis(n):
    angle = 2*np.pi*0.06*np.arange(n)
    return np.column_stack([np.ones(n), np.cos(angle), np.sin(angle)])


def features(records):
    rows = []
    for r in records:
        x = r.x
        n = len(x)
        if n == 0 or x.shape[1] != 3 or not np.isfinite(x).all():
            raise ValueError("Unsupported quality input")
        ac = x - x.mean(axis=0)
        row = dict(parent=r.parent, parent_key=f"{r.source_namespace}:{r.parent}",
                   n=n, start_m=r.start_m, end_m=r.end_m,
                   decision_m=r.decision_m, quality=bool(n >= 2 and np.any(np.ptp(x, axis=0) == 0)),
                   amplitude=np.nan, r2=np.nan, i_residual=np.nan)
        for j in range(2):
            row[f"v{j}_rms"] = np.sqrt(np.mean(ac[:, j]**2)) if n >= 2 else np.nan
            row[f"v{j}_peak"] = np.max(np.abs(ac[:, j])) if n >= 2 else np.nan
        row["i_raw"] = np.sqrt(np.mean(x[:, 2]**2))
        row["i_ac"] = np.sqrt(np.mean(ac[:, 2]**2)) if n >= 2 else np.nan
        if n >= 20 and np.sum(ac[:, 2]**2) > 0:
            basis = sine_basis(n)
            beta, _, rank, _ = np.linalg.lstsq(basis, x[:, 2], rcond=None)
            if rank == 3:
                residual = x[:, 2] - basis @ beta
                row["amplitude"] = np.hypot(beta[1], beta[2])
                row["i_residual"] = np.sqrt(np.mean(residual**2))
                row["r2"] = 1-np.sum(residual**2)/np.sum(ac[:, 2]**2)
        rows.append(row)
    return pd.DataFrame(rows)


def robust(x):
    x = np.asarray(x)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return np.nan, np.nan
    center = float(np.median(x))
    scale = float(1.4826*np.median(np.abs(x-center)))
    if scale == 0:
        scale = float(np.subtract(*np.quantile(x, [0.75, 0.25]))/1.349)
    return center, scale if scale > 0 else np.nan


class RobustLength:
    def fit(self, x, n):
        x, n = np.asarray(x), np.asarray(n)
        self.global_stats = robust(x)
        self.by_length = {}
        for lo, hi in BINS:
            mask = (n >= lo) & (n <= hi) & np.isfinite(x)
            if mask.sum() >= 30:
                self.by_length[(lo, hi)] = robust(x[mask])
        return self

    def parameters(self, n):
        n = np.asarray(n)
        center = np.full(len(n), self.global_stats[0])
        scale = np.full(len(n), self.global_stats[1])
        for (lo, hi), (c, s) in self.by_length.items():
            m = (n >= lo) & (n <= hi)
            center[m], scale[m] = c, s
        return center, scale

    def transform(self, x, n):
        c, s = self.parameters(n)
        return (np.asarray(x)-c)/s


class Preprocessing:
    def fit(self, f):
        self.floors, self.scalers, self.medians = {}, {}, {}
        for axis in AXES:
            positives = f.loc[f[axis].gt(0), axis].to_numpy()
            floor = 1e-6*np.median(positives) if len(positives) else np.nan
            self.floors[axis] = floor
            x = np.log(np.maximum(f[axis].to_numpy(), floor))
            self.scalers[axis] = RobustLength().fit(x, f.n)
            self.medians[axis] = float(np.nanmedian(x)) if np.isfinite(x).any() else np.nan
        return self

    def logs(self, f, axis):
        return np.log(np.maximum(f[axis].to_numpy(), self.floors[axis]))

    def z(self, f, axis):
        return self.scalers[axis].transform(self.logs(f, axis), f.n)

    def vector(self, f):
        z = []
        for axis in AXES:
            if not np.isfinite(self.scalers[axis].global_stats[1]):
                continue
            raw = self.logs(f, axis)
            raw = np.where(np.isfinite(raw), raw, self.medians[axis])
            column = self.scalers[axis].transform(raw, f.n)
            z.append(np.nan_to_num(column, nan=0.0))
        return np.column_stack(z) if z else np.zeros((len(f), 0))


def finite_max(a):
    a = np.asarray(a)
    available = np.isfinite(a).any(axis=1)
    result = np.max(np.where(np.isfinite(a), a, -np.inf), axis=1)
    return np.where(available, result, np.nan)


class Detector:
    def __init__(self, name):
        self.name = name
        self.degree = int(name[-1]) if name.startswith(("C1", "C2")) else 1
        self.one_sided = name.startswith("C2")

    def fit(self, f):
        self.pre = Preprocessing().fit(f)
        self.fit_ids = f.parent_key.to_numpy().copy()
        self.reference = self.pre.vector(f)
        self.min_n = 20
        eligible = (f.n.ge(self.min_n) & f.r2.ge(.95) & f.amplitude.gt(0)).to_numpy()
        self.support = (np.quantile(f.loc[eligible, "amplitude"], [.01, .99])
                        if eligible.sum() >= 30 else np.array([np.inf, -np.inf]))
        mask = eligible & f.amplitude.between(*self.support).to_numpy()
        self.conditional_n = int(mask.sum())
        self.available = self.conditional_n >= 30
        self.beta, self.residual_scalers = {}, {}
        if self.available:
            x = self.polynomial(f.loc[mask, "amplitude"].to_numpy())
            self.xmean, self.xstd = x.mean(axis=0), x.std(axis=0)
            self.xstd = np.where(self.xstd > 0, self.xstd, 1)
            x = np.column_stack([np.ones(len(x)), (x-self.xmean)/self.xstd])
            penalty = np.diag([0] + [len(x)*.001]*self.degree)
            for j in range(2):
                y = self.pre.logs(f.loc[mask], f"v{j}_rms")
                beta = np.linalg.solve(x.T @ x + penalty, x.T @ y)
                self.beta[j] = beta
                self.residual_scalers[j] = RobustLength().fit(y-x@beta, f.loc[mask, "n"])
        return self

    def polynomial(self, amplitude):
        x = np.log(np.maximum(amplitude, np.finfo(float).tiny))
        return np.column_stack([x**power for power in range(1, self.degree+1)])

    def condition(self, f):
        return ((f.n.ge(self.min_n) & f.r2.ge(.95) & f.amplitude.between(*self.support)).to_numpy()
                & self.available)

    def expected_log_rms(self, f, j):
        if not self.available:
            return np.full(len(f), np.nan)
        x = (self.polynomial(f.amplitude.to_numpy())-self.xmean)/self.xstd
        return np.column_stack([np.ones(len(f)), x]) @ self.beta[j]

    def conditional_z(self, f, j):
        residual = self.pre.logs(f, f"v{j}_rms")-self.expected_log_rms(f, j)
        if not self.available:
            return np.full(len(f), np.nan)
        return self.residual_scalers[j].transform(residual, f.n)

    def score(self, f, diagnostic=False):
        gate = self.condition(f)
        global_z = np.column_stack([self.pre.z(f, f"v{j}_rms") for j in range(2)])
        conditional_z = np.column_stack([self.conditional_z(f, j) for j in range(2)])
        vib = np.abs(global_z)
        if self.name.startswith(("C1", "C2")):
            active = np.maximum(conditional_z, 0) if self.one_sided else np.abs(conditional_z)
            vib = np.where(gate[:, None], active, vib)
        current_raw = np.abs(self.pre.z(f, "i_raw"))
        current_resid = np.maximum(self.pre.z(f, "i_residual"), 0)
        components = np.column_stack([vib, current_raw, current_resid])
        score = finite_max(components)
        if self.name.startswith("B3"):
            k = int(self.name[3:])
            d = cdist(self.pre.vector(f), self.reference)
            d[f.parent_key.to_numpy()[:, None] == self.fit_ids[None, :]] = np.inf
            # No augmentation here: exactly one reference per real fit parent.
            score = np.mean(np.partition(d, k-1, axis=1)[:, :k], axis=1)
            score[~np.isfinite(score)] = np.nan
        if not diagnostic:
            return score
        return dict(score=score, gate=gate, global_z=global_z,
                    conditional_z=conditional_z, components=components)

    def parameters(self):
        def scalar(x):
            return float(x) if np.isfinite(x) else None
        return dict(name=self.name, conditional_fit_parents=self.conditional_n,
                    support=[scalar(x) for x in self.support], conditional_available=self.available,
                    beta={str(j): b.tolist() for j, b in self.beta.items()},
                    global_center_scale={k: [scalar(x) for x in v.global_stats]
                                         for k, v in self.pre.scalers.items()},
                    conditional_center_scale={str(j): [scalar(x) for x in s.global_stats]
                                              for j, s in self.residual_scalers.items()},
                    length_specific_axes={k: [list(b) for b in s.by_length]
                                          for k, s in self.pre.scalers.items()})


class RankCalibration:
    def fit(self, scores):
        scores = np.asarray(scores)
        self.scores = np.sort(scores[np.isfinite(scores)])
        self.excluded = int((~np.isfinite(scores)).sum())
        if len(self.scores) == 0:
            raise ValueError("No calibration scores")
        return self

    def p(self, scores):
        scores = np.asarray(scores)
        rank = (1+len(self.scores)-np.searchsorted(self.scores, scores, side="left"))/(len(self.scores)+1)
        return np.where(np.isfinite(scores), rank, np.nan)

    def threshold(self, alpha):
        k = int(np.floor(alpha*(len(self.scores)+1)))
        return float(self.scores[-k]) if k >= 1 else None


class Generator:
    """One fixed fit-only generator shared by every scoring candidate."""
    def __init__(self, fit_features, fold):
        self.fold = fold
        self.model = Detector("C1d1").fit(fit_features)
        self.tau = float(np.clip(np.median(fit_features.n)/10, 1, 5))
        self.reference = {}
        for axis in ["v0_rms", "v1_rms", "i_residual"]:
            values = fit_features[axis].to_numpy()
            valid = np.isfinite(values) & (values > 0)
            self.reference[axis] = {"global": float(np.median(values[valid])), "bins": {}}
            for lo, hi in BINS:
                mask = valid & fit_features.n.between(lo, hi).to_numpy()
                if mask.sum() >= 30:
                    self.reference[axis]["bins"][(lo, hi)] = float(np.median(values[mask]))

    def scales(self, f, axis):
        result = np.full(len(f), self.reference[axis]["global"])
        for (lo, hi), value in self.reference[axis]["bins"].items():
            result[f.n.between(lo, hi)] = value
        if axis.startswith("v"):
            j = int(axis[1])
            mask = self.model.condition(f)
            if self.model.available:
                center, _ = self.model.residual_scalers[j].parameters(f.n)
                prediction = np.exp(self.model.expected_log_rms(f, j)+center)
                result[mask] = prediction[mask]
        return result

    def inject(self, record, family, target, strength, seed, scale, mode=""):
        n = len(record.x)
        x = record.x.copy()
        key = ["development", self.fold, record.parent, family, int(target), mode, int(seed)]
        rng_seed = int.from_bytes(hashlib.sha256(json.dumps(key).encode()).digest()[:8], "little")
        rng = np.random.default_rng(rng_seed)
        onset = -1
        if family == "amplitude_decrease":
            if target < 2:
                center = x[:, target].mean()
                x[:, target] = center + strength*(x[:, target]-center)
            else:
                x[:, target] *= strength
        elif strength == 0:
            return replace(record, x=x), dict(valid=True, delta_rms=0.0, onset=onset)
        else:
            if family in ["band_noise", "compound_unavailable"]:
                frequency = np.fft.rfftfreq(n)
                band = (frequency >= .15) & (frequency <= .45)
                wave = np.fft.irfft(np.fft.rfft(rng.normal(size=n))*band, n=n)
                wave -= wave.mean()
                norm = np.sqrt(np.mean(wave**2))
            elif family == "damped_impulse":
                onset = int(rng.integers(n))
                t = np.arange(n)-onset
                wave = np.exp(-np.maximum(t, 0)/self.tau)*(t >= 0)
                wave -= wave.mean()
                norm = np.max(np.abs(wave))
            elif family == "current_residual":
                if n < 4:
                    return replace(record, x=x), dict(valid=False, delta_rms=0.0, onset=onset)
                basis = sine_basis(n)
                wave = rng.normal(size=n)
                wave -= basis @ np.linalg.lstsq(basis, wave, rcond=None)[0]
                norm = np.sqrt(np.mean(wave**2))
            else:
                raise ValueError(family)
            if not np.isfinite(norm) or norm < 1e-12:
                return replace(record, x=x), dict(valid=False, delta_rms=0.0, onset=onset)
            x[:, target] += strength*scale*wave/norm
            if family == "compound_unavailable":
                if mode == "flat":
                    x[:, 2] = x[:, 2].mean()
                elif mode == "distorted":
                    x[:, 2] = np.sqrt(np.mean(x[:, 2]**2)) * (-1.)**np.arange(n)
                else:
                    raise ValueError(mode)
        difference = x[:, target]-record.x[:, target]
        if target < 2:
            difference -= difference.mean()
        delta = float(np.sqrt(np.mean(difference**2)))
        return replace(record, x=x), dict(valid=delta > 0, delta_rms=delta, onset=onset)


def fit_suite(fit, cal, names=None):
    models, calibrations = {}, {}
    for name in names or DESIGN["models"]:
        models[name] = Detector(name).fit(fit)
        calibrations[name] = RankCalibration().fit(models[name].score(cal))
    return models, calibrations
