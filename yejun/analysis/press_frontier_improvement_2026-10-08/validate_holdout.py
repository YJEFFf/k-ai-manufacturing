"""Freeze the selected system, audit its new branch, or score a separate CSV.

``audit`` is an independent numerical implementation check on already observed
data. It is NOT independent failure validation. ``evaluate`` never fits, selects
or calibrates. A provenance declaration and duplicate screening cannot establish
that a failure event is independent; the output states this explicitly.

Artifacts are JSON (no pickle or executable deserialization). Input records must
use the original process, sensor units, 10 Hz sampling and at most 50 rows.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from frontier_model import D, FrontierSuite, as_frame, guard
from run_experiment import (HERE, canonical_hash, clean_json, experiment_config,
                            file_hash, load_records, verify_lock, write_json)

SELECTED = "V2+VD3@1"
SCHEMA = "press-frontier-frozen-holdout-v1"
PROCESS = "plastic_forming_press_hydraulic_pump"
ALPHA = .01
WINDOW = 8


def now():
    return datetime.now(timezone.utc).isoformat()


def quantized(values):
    steps = np.array([1e-4, 1e-4, 1.1920929])
    return np.round(np.asarray(values, float) / steps) * steps


def digest_values(values):
    values = np.asarray(values, dtype="<f8").copy()
    values[values == 0] = 0.  # Canonicalize signed zero.
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def observation_hash(timestamp_ns, values):
    return hashlib.sha256(np.asarray([timestamp_ns], dtype="<i8").tobytes()
                          + bytes.fromhex(digest_values(values))).hexdigest()


def read_input(path, record_column=None, label_column=None, *, allow_source_clock_reset=False):
    """Reject malformed rows instead of silently dropping or repairing them."""
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream), [])
    if len(header) != len(set(header)):
        raise ValueError("CSV has duplicate column names")
    frame = pd.read_csv(path)
    required = [D.TIME, *D.SENSORS]
    if record_column:
        required.append(record_column)
    if label_column:
        required.append(label_column)
    if not len(frame) or set(required) - set(frame):
        raise ValueError("Empty CSV or missing timestamp/sensor/declared metadata column")
    times = pd.to_datetime(frame[D.TIME], errors="coerce", format="mixed", utc=True)
    values = frame[D.SENSORS].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    if times.isna().any() or not np.isfinite(values).all():
        raise ValueError("Invalid timestamp, missing sensor, or nonfinite sensor value")
    nanoseconds = times.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    gaps = np.diff(nanoseconds) / 1e9
    if np.any(gaps <= 0) and not allow_source_clock_reset:
        raise ValueError("Timestamps must be strictly increasing; reordered/duplicate rows are not accepted")
    if record_column:
        if frame[record_column].isna().any():
            raise ValueError("Missing explicit record ID")
        ids = frame[record_column].astype(str).to_numpy()
        boundary = np.r_[True, ids[1:] != ids[:-1]]
        runs = ids[boundary]
        if len(runs) != len(set(runs)):
            raise ValueError("An explicit record ID appears in more than one contiguous run")
        if np.any((np.abs(gaps - .1) > 1e-6) & ~boundary[1:]):
            raise ValueError("Explicit records must contain contiguous 10 Hz observations")
    else:
        boundary = np.r_[True, np.abs(gaps - .1) > 1e-6]
    groups = np.cumsum(boundary) - 1
    indices = [np.flatnonzero(groups == i) for i in range(int(groups[-1]) + 1)]
    if max(map(len, indices)) > 50:
        raise ValueError("A record exceeds the calibrated 50-row maximum; do not silently rechunk it")
    labels = None
    if label_column:
        numeric = pd.to_numeric(frame[label_column], errors="coerce")
        if numeric.isna().any() or not numeric.isin([0, 1]).all():
            raise ValueError("Declared labels must be complete binary values: normal=0, abnormal=1")
        labels = numeric.to_numpy(int)
    return dict(frame=frame, values=values, quantized=quantized(values),
                times_ns=nanoseconds, indices=indices, labels=labels,
                record_rule=(f"explicit:{record_column}" if record_column else "timestamp_gap_0.1s_tolerance_1e-6s"))


def catalog_for_inputs(inputs, hashes):
    observations, full_records, sensor_windows = set(), set(), set()
    for source in inputs:
        observations.update(observation_hash(t, x) for t, x in zip(source["times_ns"], source["quantized"]))
        for indices in source["indices"]:
            record = source["quantized"][indices]
            full_records.add(digest_values(record))
            for i in range(max(0, len(record) - WINDOW + 1)):
                sensor_windows.add(digest_values(record[i:i + WINDOW]))
    return dict(source_file_sha256=hashes, observation_sha256=sorted(observations),
                full_record_sensor_sha256=sorted(full_records),
                sensor_window_rows=WINDOW, sensor_window_sha256=sorted(sensor_windows))


def duplicate_audit(source, source_hash, catalog):
    known_observations = set(catalog["observation_sha256"])
    known_records = set(catalog["full_record_sensor_sha256"])
    known_windows = set(catalog["sensor_window_sha256"])
    observations = sum(observation_hash(t, x) in known_observations
                       for t, x in zip(source["times_ns"], source["quantized"]))
    records, windows = 0, 0
    for indices in source["indices"]:
        record = source["quantized"][indices]
        records += digest_values(record) in known_records
        windows += sum(digest_values(record[i:i + WINDOW]) in known_windows
                       for i in range(max(0, len(record) - WINDOW + 1)))
    result = dict(exact_source_file=source_hash in catalog["source_file_sha256"],
                  overlapping_timestamp_sensor_rows=int(observations),
                  overlapping_complete_sensor_records=int(records),
                  overlapping_eight_row_sensor_windows=int(windows),
                  screening="Exact quantized observations, full sensor records and sliding eight-row sensor windows; no label or filename dependence",
                  limitation="Cannot detect all transformed copies, short time-shifted excerpts, or the same physical event measured differently")
    result["passed"] = not any([result["exact_source_file"], observations, records, windows])
    return result


def branch_state(branch):
    return dict(kind=branch.kind, smooth=branch.smooth, mean=branch.mean_, scale=branch.scale_,
                models={str(lag): dict(coef=model.coef_, intercept=model.intercept_,
                                      residual_center=branch.residual_centers_[lag],
                                      covariance=branch.covariances_[lag],
                                      training_examples=branch.training_examples_[lag],
                                      shrinkage=branch.shrinkage_[lag])
                        for lag, model in branch.models_.items()})


def independent_branch_scores(records, state):
    """Scalar time-step calculation, with covariance solve rather than precision einsum."""
    outputs = []
    mean, scale = np.asarray(state["mean"]), np.asarray(state["scale"])
    for record in records:
        difference = (np.diff(record, axis=0) - mean) / scale
        raw = np.full(len(record), np.nan)
        for position in range(2, len(record)):
            target = position - 1
            lag = min(5, target)
            model = state["models"].get(str(lag))
            if model is None:
                continue
            predictors = np.concatenate([difference[target - k] for k in range(1, lag + 1)])
            predicted = np.asarray(model["coef"]) @ predictors + model["intercept"]
            residual = difference[target, :2] - predicted - model["residual_center"]
            raw[position] = max(0., float(residual @ np.linalg.solve(model["covariance"], residual)))
        scores = np.full(len(record), np.nan)
        for position in range(4, len(record)):
            recent = raw[position - 2:position + 1]
            if np.isfinite(recent).all():
                scores[position] = sum(map(float, recent)) / 3.
        outputs.append(scores)
    return outputs


def independent_tail(scores, state):
    """Direct empirical count and exponential extension, not ExpTail.__call__."""
    values = np.asarray(scores, float)
    output = np.full(values.shape, np.nan)
    if not state["ok"]:
        return output
    ref = np.asarray(state["ref_sorted"], float)
    u, beta = float(state["u"]), float(state["beta"])
    g_u = -np.log10((np.count_nonzero(ref >= u) + 1) / (len(ref) + 1))
    for position in np.flatnonzero(np.isfinite(values)):
        value = values[position]
        output[position] = (-np.log10((np.count_nonzero(ref >= value) + 1) / (len(ref) + 1))
                            if value <= u else g_u + (value - u) / (beta * np.log(10.)))
    return output


def direct_pvalues(scores, calibration):
    calibration = np.array([-np.inf if value is None else value for value in calibration], float)
    values = np.asarray(scores, float)
    result = np.full(len(values), np.nan)
    for i in np.flatnonzero(np.isfinite(values)):
        result[i] = (1 + np.count_nonzero(calibration >= values[i])) / (len(calibration) + 1)
    return result


def frozen_scores(records, state):
    """Only deserialize parameters; never call a fit/calibrate/select method."""
    model = guard.GuardModel(state["guard_state"])
    frame, seg = as_frame(records)
    baseline = model.components(frame, seg)["score"]
    baseline = np.split(baseline, np.cumsum([len(record) for record in records])[:-1])
    branch = independent_branch_scores(records, state["vd3"])
    selected = [np.fmax(independent_tail(v2, state["fusion_tails"]["V2"]),
                        independent_tail(vd3, state["fusion_tails"]["VD3"]))
                for v2, vd3 in zip(baseline, branch)]
    return {"V2": baseline, SELECTED: selected, "VD3": branch}


def independent_vd3_fit(records):
    """Centered normal equations and direct outer-product Ledoit-Wolf formula.

    No sklearn Ridge/LedoitWolf fitting or production feature-design functions.
    A separate covariance solve is also used for downstream Mahalanobis scores.
    """
    differences = [np.diff(record, axis=0) for record in records]
    joined = np.concatenate([record for record in differences if len(record)])
    mean, scale = joined.mean(0), joined.std(0)
    scale = np.where(scale > 1e-12, scale, 1.)
    standardized = [(record - mean) / scale for record in differences]
    models = {}
    for lag in range(1, 6):
        features, targets = [], []
        for record in standardized:
            for t in range(lag, len(record)):
                features.append(np.concatenate([record[t - k] for k in range(1, lag + 1)]))
                targets.append(record[t, :2])
        X, y = np.asarray(features), np.asarray(targets)
        if len(X) < 3:
            continue
        xm, ym = X.mean(0), y.mean(0)
        centered_x, centered_y = X - xm, y - ym
        coef = np.linalg.solve(centered_x.T @ centered_x + np.eye(X.shape[1]),
                               centered_x.T @ centered_y).T
        intercept = ym - coef @ xm
        residual = y - (X @ coef.T + intercept)
        center = residual.mean(0)
        errors = residual - center
        outer = errors[:, :, None] * errors[:, None, :]
        empirical = outer.mean(0)
        target = np.eye(2) * np.trace(empirical) / 2.
        numerator = np.sum((outer - empirical) ** 2) / (len(errors) ** 2)
        denominator = np.sum((empirical - target) ** 2)
        shrinkage = min(1., numerator / denominator) if denominator > 0 else 0.
        covariance = (1. - shrinkage) * empirical + shrinkage * target
        eigenvalues, vectors = np.linalg.eigh(covariance)
        covariance = (vectors * np.maximum(eigenvalues, 1e-8)) @ vectors.T
        models[str(lag)] = dict(coef=coef, intercept=intercept, residual_center=center,
                                covariance=covariance, training_examples=len(X), shrinkage=shrinkage)
    return dict(kind="difference_ridge", smooth=3, mean=mean, scale=scale, models=models)


def compare_arrays(left, right, label, atol=1e-10, rtol=1e-8):
    left, right = np.asarray(left, float), np.asarray(right, float)
    np.testing.assert_allclose(left, right, atol=atol, rtol=rtol, equal_nan=True, err_msg=label)
    finite = np.isfinite(left) & np.isfinite(right)
    return float(np.max(np.abs(left[finite] - right[finite]), initial=0.))


def audit(data_dir, output):
    lock = verify_lock(output / "selection_lock.json")
    if lock["selected"] != SELECTED:
        raise ValueError("This independent audit is scoped to the locked V2+VD3@1 selection")
    normal, _ = load_records(data_dir, "normal")
    abnormal, _ = load_records(data_dir, "abnormal", output / "selection_lock.json")
    splits = []
    for split, (train_end, cal_end, _) in experiment_config()["evaluation_splits"].items():
        suite = FrontierSuite().fit(normal[:train_end]).calibrate(normal[train_end:cal_end])
        production = branch_state(suite.vibration_["VD3"])
        independent = independent_vd3_fit(normal[:train_end])
        parameter_differences = {}
        for key in ("mean", "scale"):
            parameter_differences[key] = compare_arrays(independent[key], production[key], f"{split}/{key}")
        for lag in range(1, 6):
            p, q = production["models"][str(lag)], independent["models"][str(lag)]
            if p["training_examples"] != q["training_examples"]:
                raise AssertionError("Independent lag feature counts differ")
            for key in ("coef", "intercept", "residual_center", "covariance", "shrinkage"):
                parameter_differences[f"lag{lag}/{key}"] = compare_arrays(q[key], p[key], f"{split}/{lag}/{key}")
        records = normal[train_end:] + abnormal
        reference = suite.vibration_["VD3"].score(records)
        separate = independent_branch_scores(records, independent)
        difference = compare_arrays(np.concatenate(separate), np.concatenate(reference), f"{split}/all VD3 scores")
        # A second, independently accumulated score can differ by a few ulps at
        # exact empirical-tail ties. Audit all p-values/alarms, not just closeness.
        cal_independent = [float(np.nanmax(r)) if np.isfinite(r).any() else None for r in separate[:120]]
        stored = json.loads((output / f"{split}_fitted_metadata.json").read_text(encoding="utf-8"))
        compare_arrays(np.array([-np.inf if x is None else x for x in cal_independent]),
                       np.array([-np.inf if x is None else x for x in stored["calibration_maxima"]["VD3"]]),
                       f"{split}/calibration maxima")
        saved = pd.read_csv(output / "local" / f"{split}_row_predictions.csv.gz", float_precision="round_trip")
        expected = np.concatenate(separate[120:])
        saved_difference = compare_arrays(expected, saved["VD3|score"], f"{split}/saved VD3 predictions")
        changed_alarms = {}
        for alpha in (.01, .03, .05):
            independent_alarm = direct_pvalues(expected, cal_independent) <= alpha
            expected_alarm = saved[f"VD3|alarm@{alpha:g}"].to_numpy(bool)
            mismatches = int(np.count_nonzero(independent_alarm != expected_alarm))
            changed_alarms[str(alpha)] = mismatches
            if mismatches:
                raise AssertionError(f"{split}: independently fitted VD3 alters {mismatches} alarms at {alpha}")
        splits.append(dict(split=split, training_records=train_end,
                           independent_ridge_examples={lag: m["training_examples"] for lag, m in independent["models"].items()},
                           audited_calibration_records=120, audited_normal_test_records=600-cal_end,
                           audited_abnormal_records=21, audited_score_rows=sum(map(len, records)),
                           parameter_max_absolute_differences=parameter_differences,
                           maximum_absolute_score_difference=difference,
                           maximum_absolute_saved_prediction_difference=saved_difference,
                           changed_alarms_by_alpha=changed_alarms,
                           saved_predictions_sha256=file_hash(output / "local" / f"{split}_row_predictions.csv.gz")))
        print(f"{split}: independent normal-equation / covariance / row-score audit passed", flush=True)
    verify_lock(output / "selection_lock.json")
    result = dict(passed=True, created_utc=now(), selection_lock_sha256=lock["lock_sha256"],
                  script_sha256_lf=file_hash(Path(__file__), True), splits=splits,
                  arithmetic="Separate lag construction, centered Ridge normal equations, direct outer-product Ledoit-Wolf shrinkage, covariance solve, causal three-score mean",
                  independence_scope="Implementation arithmetic for the new VD3 branch; production V2 and empirical-tail training are not independently reimplemented",
                  data_scope="Previously observed source normal and abnormal data; NOT independent failure validation",
                  model_or_threshold_selection_changed=False)
    write_json(output / "independent_implementation_verification.json", result)
    return result


def freeze(data_dir, output, artifact):
    lock = verify_lock(output / "selection_lock.json")
    if lock["selected"] != SELECTED:
        raise ValueError("Frozen evaluator supports the unchanged V2+VD3@1 selection only")
    if artifact.exists():
        raise FileExistsError("Artifact already exists; use a new directory without overwriting the commitment")
    normal, normal_source = load_records(data_dir, "normal")
    abnormal, abnormal_source = load_records(data_dir, "abnormal", output / "selection_lock.json")
    # Hash-verified historical CSVs contain acquisition clock resets. Catalog
    # their original order and boundaries; new-input evaluation remains strict.
    inputs = [read_input(Path(data_dir) / D.FILES[kind], allow_source_clock_reset=True)
              for kind in ("normal", "abnormal")]
    catalog = catalog_for_inputs(inputs, [normal_source["sha256"], abnormal_source["sha256"]])
    artifact.mkdir(parents=True)
    write_json(artifact / "exposure_catalog.json", catalog)
    equality = []
    for split, (train_end, cal_end, _) in experiment_config()["evaluation_splits"].items():
        suite = FrontierSuite().fit(normal[:train_end]).calibrate(normal[train_end:cal_end])
        state = clean_json(dict(schema=SCHEMA, split=split, selected=SELECTED, alpha=ALPHA,
                     guard_state=suite.guard_.state, vd3=branch_state(suite.vibration_["VD3"]),
                     fusion_tails={name: suite.fusion_tails_[name].state() for name in ("V2", "VD3")},
                     calibration={name: suite.cal_[name] for name in ("V2", SELECTED)},
                     training_records=train_end, calibration_records=cal_end-train_end))
        records = normal[cal_end:] + abnormal
        independent = frozen_scores(records, state)
        production = suite.score(records)
        alarm_equality, deltas = {}, {}
        for name in ("V2", SELECTED):
            actual, expected = np.concatenate(independent[name]), np.concatenate(production[name])
            deltas[name] = compare_arrays(actual, expected, f"{split}/frozen/{name}", atol=1e-8, rtol=1e-8)
            alert = direct_pvalues(actual, state["calibration"][name]) <= ALPHA
            expected_alert = np.concatenate(suite.alarms(production, ALPHA)[name])
            np.testing.assert_array_equal(alert, expected_alert)
            alarm_equality[name] = True
        equality.append(dict(split=split, rows=sum(map(len, records)), alarms_equal=alarm_equality,
                             maximum_absolute_score_differences=deltas))
        write_json(artifact / f"{split}_state.json", state)
        print(f"{split}: froze unchanged parameters and verified all retrospective test alarms", flush=True)
    manifest = dict(schema=SCHEMA, created_utc=now(), selected=SELECTED, alpha=ALPHA,
                    selection_lock_sha256=lock["lock_sha256"], process=PROCESS,
                    retrospective_export_equivalence=equality,
                    known_data_previously_exposed=True,
                    validation_scope="Frozen inference only; independent event status requires external provenance verification",
                    files={name: file_hash(artifact / name) for name in ("A_state.json", "B_state.json", "exposure_catalog.json")})
    manifest["commitment_sha256"] = canonical_hash(manifest)
    write_json(artifact / "manifest.json", manifest)
    write_json(artifact / "provenance.example.json", dict(
        process=PROCESS, source_uri="REPLACE_WITH_SOURCE_OR_COLLECTION_ID",
        equipment_id="REPLACE", acquisition_id="REPLACE", schema_matches_source=True,
        sampling_seconds=.1, prior_model_development_exposure="unseen",
        relationship_to_original_failure="REPLACE_WITH_DOCUMENTED_RELATIONSHIP",
        independent_event_ids=["REPLACE_IF_DOCUMENTED"], label_definition="normal=0; abnormal=1, based on maintenance evidence"))
    verify_lock(output / "selection_lock.json")
    return manifest


def load_artifact(artifact):
    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest.pop("commitment_sha256")
    if canonical_hash(manifest) != expected or manifest.get("schema") != SCHEMA:
        raise ValueError("Frozen artifact commitment/schema mismatch")
    for name in ("A_state.json", "B_state.json", "exposure_catalog.json"):
        if file_hash(artifact / name) != manifest["files"][name]:
            raise ValueError(f"Frozen artifact file changed: {name}")
    manifest["commitment_sha256"] = expected
    return manifest


def validate_provenance(provenance):
    required = ("source_uri", "equipment_id", "acquisition_id", "relationship_to_original_failure")
    if any(not isinstance(provenance.get(key), str) or not provenance[key].strip()
           or "REPLACE" in provenance[key] for key in required):
        raise ValueError("Complete source/equipment/acquisition/failure-relationship provenance before evaluation")
    if (provenance.get("process") != PROCESS or provenance.get("schema_matches_source") is not True
            or provenance.get("sampling_seconds") != .1):
        raise ValueError("The frozen model requires the original press process, units/schema, and 10 Hz sampling")
    if provenance.get("prior_model_development_exposure") not in ("unseen", "previously_seen", "unknown"):
        raise ValueError("Declare prior exposure as unseen, previously_seen, or unknown")


def evaluate(artifact, split, csv_path, provenance_path, output, record_column=None, label_column=None):
    manifest = load_artifact(artifact)
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    validate_provenance(provenance)
    if output.exists():
        raise FileExistsError("Use a new evaluation output directory; results are not silently overwritten")
    output.mkdir(parents=True)
    # Commit the chosen split/alpha/artifact and provenance before opening CSV.
    precommit = dict(created_utc=now(), artifact_commitment_sha256=manifest["commitment_sha256"],
                     split=split, selected=SELECTED, alpha=ALPHA,
                     provenance=provenance, provenance_sha256=file_hash(provenance_path),
                     evaluator_sha256_lf=file_hash(Path(__file__), True), csv_opened=False)
    write_json(output / "evaluation_precommit.json", precommit)
    try:
        source = read_input(csv_path, record_column=record_column, label_column=label_column)
        source_hash = file_hash(csv_path)
        catalog = json.loads((artifact / "exposure_catalog.json").read_text(encoding="utf-8"))
        duplicate = duplicate_audit(source, source_hash, catalog)
        write_json(output / "duplicate_audit.json", duplicate)
        if not duplicate["passed"]:
            raise ValueError("Known source data overlap detected; this input cannot be used as a new holdout")
        state = json.loads((artifact / f"{split}_state.json").read_text(encoding="utf-8"))
        if state.get("selected") != SELECTED or state.get("alpha") != ALPHA or state.get("split") != split:
            raise ValueError("Frozen model identity mismatch")
        records = [source["quantized"][indices] for indices in source["indices"]]
        scores = frozen_scores(records, state)
        predictions = pd.DataFrame(dict(row=np.arange(len(source["frame"])),
                       timestamp=source["frame"][D.TIME],
                       record=np.concatenate([np.full(len(r), i) for i, r in enumerate(records)]),
                       position=np.concatenate([np.arange(len(r)) for r in records])))
        metrics = []
        for name in ("V2", SELECTED):
            values = np.concatenate(scores[name])
            pvalues = direct_pvalues(values, state["calibration"][name])
            alarms = np.isfinite(pvalues) & (pvalues <= ALPHA)
            predictions[f"{name}|score"] = values
            predictions[f"{name}|pvalue"] = pvalues
            predictions[f"{name}|alarm"] = alarms
            row = dict(model=name, rows=len(values), records=len(records),
                       unavailable_rows=int((~np.isfinite(values)).sum()), alarm_rows=int(alarms.sum()),
                       alarm_records=sum(bool(np.any(alarms[indices])) for indices in source["indices"]))
            labels = source["labels"]
            if labels is not None:
                tp, fp, fn, tn = (int(np.sum(mask)) for mask in
                                  (alarms & (labels == 1), alarms & (labels == 0),
                                   ~alarms & (labels == 1), ~alarms & (labels == 0)))
                abnormal_records = [indices for indices in source["indices"] if np.any(labels[indices] == 1)]
                normal_records = [indices for indices in source["indices"] if np.all(labels[indices] == 0)]
                row.update(tp=tp, fp=fp, fn=fn, tn=tn, row_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                           row_recall=tp/(tp+fn) if tp+fn else None,
                           row_precision=tp/(tp+fp) if tp+fp else None,
                           abnormal_records=len(abnormal_records), normal_records=len(normal_records),
                           detected_abnormal_records=sum(bool(np.any(alarms[i] & (labels[i] == 1))) for i in abnormal_records),
                           normal_fp_records=sum(bool(np.any(alarms[i])) for i in normal_records))
            metrics.append(row)
        if source["labels"] is not None:
            predictions["label"] = source["labels"]
        predictions.to_csv(output / "row_predictions.csv", index=False)
        result = dict(passed=True, completed_utc=now(), split=split, alpha=ALPHA,
                      artifact_commitment_sha256=manifest["commitment_sha256"], source_csv_sha256=source_hash,
                      provenance=provenance, record_boundary_rule=source["record_rule"],
                      label_column=label_column, duplicate_audit=duplicate, metrics=metrics,
                      fit_calls=0, calibration_calls=0, candidate_selection_calls=0,
                      independent_failure_validation_established=False,
                      interpretation="Separate input evaluated with frozen parameters; provenance assertions are not independently authenticated and recording fragments are not independent failure events",
                      no_labels_note="Without an explicitly declared binary label column, alert counts are not false-positive rates or sensitivity")
        write_json(output / "result.json", result)
        load_artifact(artifact)  # Verify no artifact mutation during inference.
        return result
    except Exception as exc:
        write_json(output / "rejected.json", dict(passed=False, reason=str(exc), completed_utc=now(),
                    artifact_commitment_sha256=manifest["commitment_sha256"], no_model_update=True))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "freeze"):
        command = commands.add_parser(name)
        command.add_argument("--data-dir", type=Path, required=True)
        command.add_argument("--experiment-output", type=Path, default=HERE / "outputs")
        if name == "freeze":
            command.add_argument("--artifact", type=Path, required=True)
    command = commands.add_parser("evaluate")
    command.add_argument("--artifact", type=Path, required=True)
    command.add_argument("--split", choices=("A", "B"), required=True)
    command.add_argument("--csv", type=Path, required=True)
    command.add_argument("--provenance", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--record-column")
    command.add_argument("--label-column", help="Explicit binary column: normal=0, abnormal=1; omitted means unlabeled")
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        if args.command == "audit":
            result = audit(args.data_dir.resolve(), args.experiment_output.resolve())
        elif args.command == "freeze":
            result = freeze(args.data_dir.resolve(), args.experiment_output.resolve(), args.artifact.resolve())
        else:
            result = evaluate(args.artifact.resolve(), args.split, args.csv.resolve(),
                              args.provenance.resolve(), args.output.resolve(),
                              args.record_column, args.label_column)
    print(json.dumps(clean_json(result), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
