"""Common vibration representation and target-only evaluation for transfer tests."""
from __future__ import annotations

import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
import sys
sys.dont_write_bytecode = True
import hashlib
import importlib.util
import json
from pathlib import Path
from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from sklearn.metrics import average_precision_score, roc_auc_score

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
ROOT = YEJUN.parent
MASTER = YEJUN / "plans/press_master_2026-10-03"
CFG = json.loads((HERE / "protocol.json").read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


core = module("external_training_press_core", YEJUN / "analysis/press_master_validation_2026-10-03/core.py")
guard = module("external_training_guard", YEJUN / "press_guard/model.py")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def array_sha(a):
    a = np.ascontiguousarray(a)
    return hashlib.sha256(str(a.shape).encode() + a.dtype.str.encode() + a.tobytes()).hexdigest()


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (tuple, list, np.ndarray)):
        return [clean(v) for v in x]
    if isinstance(x, (np.bool_, np.integer)):
        return x.item()
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, Path):
        return str(x)
    return x


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def bands(amplitude):
    """Magnitude bins include DC; integrate positive-frequency energy mass."""
    amp = np.asarray(amplitude, dtype=float)
    if amp.ndim != 1 or len(amp) < 3 or not np.isfinite(amp).all() or (amp < 0).any():
        raise ValueError("Invalid magnitude spectrum")
    power = amp[1:] ** 2
    total = power.sum()
    if total == 0:
        return np.zeros(16)
    # Centers of positive frequencies are (1..m)/m. Cell boundaries span 0..1.
    m = len(power)
    edges = np.r_[0., (np.arange(1, m) + .5) / m, 1.]
    cumulative = np.r_[0., np.cumsum(power) / total]
    mass = np.diff(np.interp(np.linspace(0, 1, 17), edges, cumulative))
    return np.sqrt(np.maximum(mass, 0.))


def waveform(x):
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or len(x) < 4 or not np.isfinite(x).all():
        raise ValueError("Unsupported waveform")
    return bands(np.abs(np.fft.rfft(x - x.mean())))


def load_target():
    result, audit = {}, {}
    for kind in ("normal", "abnormal"):
        recs, audit[kind] = core.load_records(kind)
        rounded = []
        for r in recs:
            frame = pd.DataFrame(r.x, columns=core.COLS)
            x = guard.D.quantize(frame, "matched")[core.COLS].to_numpy()
            rounded.append(replace(r, x=x))
        result[kind] = rounded
    return result, audit


def target_vectors(records):
    vectors, indices, ids = [], [], []
    for i, r in enumerate(records):
        if len(r.x) < CFG["shared_representation"]["minimum_target_samples"]:
            continue
        for channel in (0, 1):
            vectors.append(waveform(r.x[:, channel]))
            indices.append(i)
            ids.append(f"press:{r.source_namespace}:{r.parent}:{channel}")
    return np.asarray(vectors), np.asarray(indices, dtype=int), np.asarray(ids)


def frame(records):
    frames = []
    for r in records:
        f = pd.DataFrame(r.x, columns=core.COLS)
        start_ns = int(round(r.start_m * 60e9))
        f["TimeStamp"] = pd.to_datetime(start_ns + np.arange(len(f)) * 100_000_000)
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def base_fit(roles):
    model = guard.GuardModel.fit(frame(roles["fit"]), frame(roles["cal"]), split="external_training_control")
    result = {}
    for role, records in roles.items():
        f = frame(records)
        seg = np.repeat(np.arange(len(records)), [len(r.x) for r in records])
        raw = model.components(f, seg)["score"]
        result[role] = np.maximum.reduceat(raw, np.r_[0, np.cumsum([len(r.x) for r in records])[:-1]])
        if not np.isfinite(result[role]).all():
            raise ValueError("Fixed target detector failed")
    return result, model


def record_max(channel_scores, mapping, n):
    out = np.full(n, np.nan)
    for i in np.unique(mapping):
        out[i] = np.max(channel_scores[mapping == i])
    return out


def rank_p(reference, query):
    r = np.sort(np.asarray(reference, float))
    if not len(r) or not np.isfinite(r).all():
        raise ValueError("Finite target calibration required")
    q = np.asarray(query, float)
    return (1 + len(r) - np.searchsorted(r, q, side="left")) / (len(r) + 1)


def metric(y, pred, scores):
    y, pred = np.asarray(y, int), np.asarray(pred, bool)
    tp, fp = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum())
    fn, tn = int((~pred & (y == 1)).sum()), int((~pred & (y == 0)).sum())
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, f1=2*tp/(2*tp+fp+fn),
                precision=tp/(tp+fp) if tp+fp else 0., recall=tp/(tp+fn),
                auroc=roc_auc_score(y, scores), ap=average_precision_score(y, scores))


def select_pool(pool, count, seed, normal_only):
    mask = pool["normal"].astype(bool) if normal_only else np.ones(len(pool["x"]), bool)
    candidates = np.flatnonzero(mask)
    groups = pool["groups"][candidates]
    rng = np.random.default_rng(seed)
    queues = [rng.permutation(candidates[groups == g]).tolist() for g in sorted(set(groups))]
    order = rng.permutation(len(queues))
    chosen = []
    while len(chosen) < count:
        progressed = False
        for g in order:
            if queues[g]:
                chosen.append(queues[g].pop())
                progressed = True
                if len(chosen) >= count:
                    break
        if not progressed:
            break
    return np.asarray(chosen, dtype=int)


class Neighbors:
    def __init__(self, x, ids):
        _, unique = np.unique(ids, return_index=True)
        unique = np.sort(unique)
        self.x, self.ids = np.asarray(x)[unique], np.asarray(ids)[unique]

    def score(self, x, exclude_parents=None):
        d = cdist(x, self.x)
        if exclude_parents is not None:
            for i, parent in enumerate(exclude_parents):
                d[i, np.char.startswith(self.ids, parent + ":")] = np.inf
        k = CFG["methods"]["pooled_knn"]["k"]
        result = np.partition(d, k-1, axis=1)[:, :k].mean(axis=1)
        if not np.isfinite(result).all():
            raise ValueError("Not enough independent reference examples")
        return result
