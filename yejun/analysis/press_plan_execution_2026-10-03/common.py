"""Shared exact-input, metric and operational contracts for the October 3 plan."""
from __future__ import annotations

import os
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import hashlib
import importlib.util
import json
import platform
from datetime import datetime, timezone
from dataclasses import replace

import numpy as np
import pandas as pd
import scipy
from sklearn.metrics import average_precision_score, roc_auc_score

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
ROOT = YEJUN.parent
MASTER = YEJUN / "plans/press_master_2026-10-03"
LEGACY = HERE.parent / "press_master_validation_2026-10-03"
sys.path.append(str(LEGACY))
import core

CONTRACT = json.loads((MASTER / "execution_contracts.json").read_text(encoding="utf-8"))
PROTOCOL = core.PROTOCOL


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


legacy_run = import_file("registered_development", LEGACY / "run.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    return value


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    frame.to_csv(path, index=False)


def now():
    return datetime.now(timezone.utc).isoformat()


def environment():
    import sklearn
    return dict(python=platform.python_version(), platform=platform.platform(),
                numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                sklearn=sklearn.__version__, threads=1)


def load_press(kind="normal"):
    name = "press_data_normal.csv" if kind == "normal" else "outlier_data.csv"
    path = HERE / "data/press" / name
    if sha(path) != PROTOCOL["input"][kind + "_sha256"]:
        raise ValueError("Press input hash mismatch")
    records, audit = core.records_from_frame(pd.read_csv(path))
    return [replace(r, source_namespace=kind) for r in records], audit


def ratio(a, b):
    return float(a / b) if b else None


def metrics(y, pred, score=None):
    y, pred = np.asarray(y, dtype=int), np.asarray(pred, dtype=bool)
    tp, fp = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum())
    fn, tn = int((~pred & (y == 1)).sum()), int((~pred & (y == 0)).sum())
    result = dict(n=len(y), positive=int(y.sum()), negative=int((y == 0).sum()),
                  tp=tp, fp=fp, fn=fn, tn=tn, f1=ratio(2*tp, 2*tp+fp+fn),
                  precision=ratio(tp, tp+fp), recall=ratio(tp, tp+fn),
                  accuracy=ratio(tp+tn, len(y)), specificity=ratio(tn, tn+fp),
                  false_positive_rate=ratio(fp, tn+fp))
    result["balanced_accuracy"] = ((result["recall"] + result["specificity"])/2
                                    if result["recall"] is not None and result["specificity"] is not None else None)
    if score is not None:
        score = np.asarray(score, float)
        valid = np.isfinite(score)
        result["scored_n"] = int(valid.sum())
        result["score_coverage"] = ratio(valid.sum(), len(y))
        if len(np.unique(y[valid])) == 2:
            result["auroc_scored"] = float(roc_auc_score(y[valid], score[valid]))
            result["average_precision_scored"] = float(average_precision_score(y[valid], score[valid]))
        else:
            result["auroc_scored"] = result["average_precision_scored"] = None
    return result


def interval_metrics(lower, upper, pred):
    l, u, b = np.asarray(lower), np.asarray(upper), np.asarray(pred, int)
    tl, th = int((b*l).sum()), int((b*u).sum())
    fl, fh = int((b*(1-u)).sum()), int((b*(1-l)).sum())
    nl, nh = int(((1-b)*l).sum()), int(((1-b)*u).sum())
    return dict(n=len(b), ambiguous=int((l != u).sum()), tp_low=tl, tp_high=th,
                fp_low=fl, fp_high=fh, fn_low=nl, fn_high=nh,
                f1_low=ratio(2*tl, 2*tl+fh+nh), f1_high=ratio(2*th, 2*th+fl+nl),
                precision_low=ratio(tl, b.sum()), precision_high=ratio(th, b.sum()),
                recall_low=ratio(tl, tl+nh), recall_high=ratio(th, th+nl),
                possible_zero_f1_denominator=bool(tl+fl+nl == 0),
                possible_zero_recall_denominator=bool(l.sum() == 0))


def rank(scores, reference, alpha=.05):
    s, ref = np.asarray(scores), np.asarray(reference)
    ref = np.sort(ref[np.isfinite(ref)])
    supported = np.isfinite(s) & (len(ref) >= int(np.ceil(1/alpha))-1)
    p = np.where(supported, (1+len(ref)-np.searchsorted(ref, s, side="left"))/(1+len(ref)), np.nan)
    return p, supported


def rng_for(key):
    encoded = json.dumps(key, ensure_ascii=True, separators=(",", ":")).encode()
    seed = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "little")
    return np.random.Generator(np.random.PCG64(seed))


def policy(times, bits, supported=None, quality=None, name="I0"):
    """Decisions must belong to one ordered capture. Quality tickets are instantaneous."""
    t, b = np.asarray(times, float), np.asarray(bits, bool)
    valid = np.ones(len(t), bool) if supported is None else np.asarray(supported, bool)
    q = np.zeros(len(t), bool) if quality is None else np.asarray(quality, bool)
    if len(t) and (not np.isfinite(t).all() or np.any(np.diff(t) <= 0)):
        raise ValueError("Policy requires strictly increasing finite decision times")
    active, history, negatives, opened = False, [], 0, None
    starts, intervals, trace = [], [], []
    for i, ti in enumerate(t):
        reset = i > 0 and ti-t[i-1] > 30
        if reset:
            if active:
                intervals.append((opened, t[i-1]+30, "gap_unknown"))
            active, history, negatives, opened = False, [], 0, None
        mechanical_start = repeated = False
        quality_ticket = bool(q[i] or not valid[i])
        if not valid[i]:
            if active:
                intervals.append((opened, ti, "closed_unknown"))
            active, history, negatives, opened = False, [], 0, None
        else:
            history = (history + [bool(b[i])])[-3:]
            negatives = 0 if b[i] else negatives+1
            if active and negatives >= 2:
                intervals.append((opened, ti, "resolved"))
                active, history, opened = False, [], None
            if not active and b[i] and (name == "I0" or sum(history) >= 2):
                active, mechanical_start, opened = True, True, ti
                starts.append(i)
            elif active and b[i]:
                repeated = True
        trace.append(dict(index=i, time=ti, bit=bool(b[i]), supported=bool(valid[i]),
                          quality_ticket=quality_ticket, mechanical_start=mechanical_start,
                          ticket_start=bool(mechanical_start or quality_ticket), active=active,
                          repeated_suppressed=repeated, reset_gap=reset))
    if active:
        intervals.append((opened, t[-1], "right_censored"))
    return dict(starts=np.asarray(starts, int), intervals=intervals, trace=trace,
                mechanical_starts=len(starts), quality_tickets=sum(r["quality_ticket"] for r in trace),
                total_tickets=sum(r["ticket_start"] for r in trace),
                threshold_positive=int((b & valid).sum()),
                suppressed=sum(r["repeated_suppressed"] for r in trace),
                occupancy_s=sum(end-start for start, end, _ in intervals))


def event_response(result, times, start, deadline, late_deadline=None):
    times = np.asarray(times)
    indices = result["starts"]
    inside = indices[(times[indices] >= start) & (times[indices] <= deadline)]
    late = indices[(times[indices] > deadline) & (times[indices] <= late_deadline)] if late_deadline is not None else []
    first = int(inside[0]) if len(inside) else None
    return dict(detected=bool(len(inside)), detection_index=first,
                valid_decision_ordinal=sum(r["supported"] for r in result["trace"][:first+1]) if first is not None else None,
                detection_time=float(times[first]) if first is not None else None,
                delay_s=float(times[first]-start) if first is not None else None,
                preexisting_request=any(a < start < z for a, z, _ in result["intervals"]),
                late_detection=bool(len(late)),
                not_detected_by_observation_end=not bool(len(inside)))
