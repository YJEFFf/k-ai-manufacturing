"""Evaluation-only strong comparators under the frozen frontier protocol.

Reproduces the earlier report's five-feature 5NN and three-output Ridge models.
This adds no selectable candidate and changes no alarm/persistence rule. All
abnormal data belong to the already observed source event; neither the audit nor
its recording-block bootstrap establishes independent-failure generalization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.neighbors import NearestNeighbors
from threadpoolctl import threadpool_limits

from frontier_model import FrontierSuite, D, ROOT, HERE, as_frame, guard, record_maxima, split_values
from press.calibrate import conformal_p
from run_experiment import (canonical_hash, clean_json, file_hash, load_records,
                            locked_sources, utc_now, verify_lock, write_json)
from scenarios import CausalGenerator, FAMILIES, ONSETS, DEVELOPMENT_SEEDS, EVALUATION_SEEDS

KNN = "5NN_feature_matched"
RIDGE = "RidgeForecast_3channel"
SELECTED = "V2+VD3@1"
MODELS = ("V2", SELECTED, KNN, RIDGE)
ALPHAS = (.01, .03, .05)
RIDGE_ALPHAS = (.01, .1, 1., 10., 100.)
SPLITS = {"development": (120, 240, 300), "A": (360, 480, 600), "B": (300, 420, 600)}


class FeatureMatchedKNN:
    """Historical 5NN: three z-scored sensors plus waveform/AR2 raw features.

    Definition follows the report's tvt/15_record_auroc_featbase.py::FeatBase.
    This is different from a 5NN over the three already transformed V2 scores.
    Missing early waveform/AR2 features use NORMAL TRAINING medians only.
    """
    def __init__(self, guard_model):
        self.guard = guard_model

    def raw_features(self, records):
        frame, segment = as_frame(records)
        values = frame[D.SENSORS].to_numpy(float)
        z = (values - self.guard.mean) / self.guard.scale
        position = D.segment_positions(segment)[0]
        current = values[:, 2]
        wave = np.where(position < 7, guard.sine_score(current, segment, 6),
                        guard.sine_score(current, segment, 8))
        dynamics = guard.ar_residual(frame, segment, self.guard.coef)
        return z, np.column_stack([wave, dynamics])

    def fit(self, records):
        z, raw = self.raw_features(records)
        self.median_ = np.nanmedian(raw, axis=0)
        raw = np.where(np.isnan(raw), self.median_, raw)
        self.mean_, self.scale_ = raw.mean(0), raw.std(0)
        if not np.isfinite(self.median_).all() or np.any(self.scale_ <= 0):
            raise ValueError("Historical feature-matched 5NN requires nonconstant finite training features")
        features = np.hstack([z, (raw - self.mean_) / self.scale_])
        self.neighbors_ = NearestNeighbors(n_neighbors=5).fit(features)
        self.training_rows_ = len(features)
        return self

    def score(self, records):
        z, raw = self.raw_features(records)
        raw = np.where(np.isnan(raw), self.median_, raw)
        features = np.hstack([z, (raw - self.mean_) / self.scale_])
        scores = self.neighbors_.kneighbors(features)[0].mean(1)
        return split_values(scores, records)

    def metadata(self):
        return dict(n_neighbors=5, dimensions=5, missing_feature_training_median=self.median_,
                    raw_feature_training_mean=self.mean_, raw_feature_training_sd=self.scale_,
                    stored_training_rows=self.training_rows_, first_row_scored=True)


class HistoricalRidge:
    """Historical tvt/14 RidgeForecast, preserving its training-only alpha rule."""
    def __init__(self, mean, scale):
        self.mean, self.scale = np.asarray(mean, float), np.asarray(scale, float)

    def design(self, records, lag):
        predictors, targets = [], []
        for record in records:
            z = (np.asarray(record, float) - self.mean) / self.scale
            indices = np.arange(lag, len(z))
            if len(indices):
                predictors.append(np.hstack([z[indices-k] for k in range(1, lag+1)]))
                targets.append(z[indices])
        if not predictors:
            return np.empty((0, 3*lag)), np.empty((0, 3))
        return np.vstack(predictors), np.vstack(targets)

    def fit(self, records):
        cut = int(len(records) * .8)
        early_x, early_y = self.design(records[:cut], 5)
        late_x, late_y = self.design(records[cut:], 5)
        if not len(early_x) or not len(late_x):
            raise ValueError("Historical Ridge alpha tuning needs eligible training records in both 80/20 portions")
        self.validation_mse_ = {}
        for alpha in RIDGE_ALPHAS:
            error = Ridge(alpha=alpha).fit(early_x, early_y).predict(late_x) - late_y
            self.validation_mse_[alpha] = float(np.mean(error ** 2))
        self.alpha_ = min(self.validation_mse_, key=self.validation_mse_.get)
        self.models_, self.residual_sd_, self.training_examples_ = {}, {}, {}
        for lag in range(1, 6):
            x, y = self.design(records, lag)
            model = Ridge(alpha=self.alpha_).fit(x, y)
            residual_sd = (model.predict(x) - y).std(0)
            if np.any(residual_sd <= 0) or not np.isfinite(residual_sd).all():
                raise ValueError("Historical Ridge requires positive finite residual training SD")
            self.models_[lag], self.residual_sd_[lag] = model, residual_sd
            self.training_examples_[lag] = len(x)
        self.training_tuning_cut_ = cut
        return self

    def score(self, records):
        result = []
        for record in records:
            z = (np.asarray(record, float) - self.mean) / self.scale
            score = np.full(len(record), np.nan)
            for lag in range(1, 6):
                indices = np.arange(lag, len(z)) if lag == 5 else np.array([lag]) if len(z) > lag else np.array([], int)
                if len(indices):
                    x = np.hstack([z[indices-k] for k in range(1, lag+1)])
                    residual = np.abs(self.models_[lag].predict(x) - z[indices]) / self.residual_sd_[lag]
                    score[indices] = residual.max(1)
            result.append(score)
        return result

    def metadata(self):
        return dict(outputs=3, maximum_lag=5, alpha=self.alpha_, alpha_grid=RIDGE_ALPHAS,
                    training_validation_mse=self.validation_mse_, training_tuning_cut=self.training_tuning_cut_,
                    training_examples=self.training_examples_, residual_sd=self.residual_sd_,
                    first_row_scored=False, first_row_kept_in_all_denominators=True)


class ComparisonSuite:
    def fit(self, train, calibration):
        self.frontier = FrontierSuite().fit(train).calibrate(calibration)
        self.knn = FeatureMatchedKNN(self.frontier.guard_).fit(train)
        self.ridge = HistoricalRidge(self.frontier.guard_.mean, self.frontier.guard_.scale).fit(train)
        self.calibration = {name: self.frontier.cal_[name] for name in ("V2", SELECTED)}
        self.calibration[KNN] = record_maxima(self.knn.score(calibration))
        self.calibration[RIDGE] = record_maxima(self.ridge.score(calibration))
        if any(len(values) != 120 for values in self.calibration.values()):
            raise ValueError("All models must use the same 120 calibration records")
        return self

    def score(self, records):
        original = self.frontier.score(records)
        return {"V2": original["V2"], SELECTED: original[SELECTED],
                KNN: self.knn.score(records), RIDGE: self.ridge.score(records)}

    def alarms(self, scores, alpha):
        return {name: [np.isfinite(values) & (conformal_p(self.calibration[name], values) <= alpha)
                       for values in records] for name, records in scores.items()}


def protocol_config(parent):
    return dict(schema=1, created_utc=utc_now(), parent_selection_lock_sha256=parent["lock_sha256"],
                existing_selected_model=parent["selected"], models=MODELS,
                selectable_new_models=[], model_or_rule_selection_allowed=False,
                study="Retrospective same previously observed source failure event; evaluation-only comparison",
                splits=SPLITS, preprocessing="Original matched quantization, before continuous causal injection; no re-quantization after injection",
                calibration="Each model has one score, calibrated on the same 120 NORMAL record maxima, p=(1+count(cal>=score))/121",
                alphas=ALPHAS, injection_alpha=.01, actual_subsets=["all21", "front10", "back11"],
                source_exposure="Historical failure data and historical comparator results were known before this audit; this is not a blinded preregistration",
                abnormal_input_opened_during_this_audit=False,
                knn=dict(features=["upper sensor z", "lower sensor z", "current sensor z", "v2 raw waveform", "v2 raw AR2 absolute error"],
                         imputation="normal fit median", additional_feature_scaling="normal fit mean and population SD", k=5,
                         source_definition="original report tvt/15_record_auroc_featbase.py FeatBase"),
                ridge=dict(input="up to five prior rows of all three standardized sensors", output="current three standardized sensors",
                           score="maximum absolute residual / respective training residual SD", first_row="unavailable; retained",
                           alpha_grid=RIDGE_ALPHAS, alpha_choice="minimum lag-5 MSE on normal FIT last20%, trained on FIT first80%; grid order breaks ties",
                           source_definition="original report tvt/14_baseline_injection_ridge.py RidgeForecast"),
                injections=dict(families=FAMILIES, onsets=ONSETS, development_seeds=DEVELOPMENT_SEEDS,
                                evaluation_seeds=EVALUATION_SEEDS, denominator="every normal test record; only onset-and-later rows count as hits/control hits"),
                bootstrap=dict(repetitions=4000, seed=20261008, normal_block_records=10, abnormal_block_records=3,
                               method="Stratified circular moving recording-block bootstrap; same sampled record IDs across models",
                               interval="two-sided percentile 95%, no retuning or recalibration in resamples",
                               pairs=[[SELECTED, "V2"], [SELECTED, KNN], [SELECTED, RIDGE], ["V2", KNN], ["V2", RIDGE]],
                               interpretation="Within-event conditional variability only; overlapping A/B are not replications; no independent failure generalization",
                               zero_included="No superiority or equivalence conclusion; retain existing selection",
                               excludes_zero="Describe directional difference only within this observed event; retain existing selection"),
                operational_properties_frozen_before_run={
                    "V2": "causal, deterministic, first-row availability, component-level explanation",
                    SELECTED: "causal, deterministic, first-row availability through V2, separate vibration residual indication",
                    KNN: "causal, deterministic, first-row availability with fit-median fill, retained training reference rows",
                    RIDGE: "causal, deterministic, first row unavailable, three-channel prediction residuals"},
                rules="No R1/R2/persistence or new operational rule; no candidate reselection",
                source_sha256_lf={**locked_sources(), str(Path(__file__).relative_to(ROOT)).replace("\\", "/"): file_hash(Path(__file__), True)})


def prepare(output, parent_output):
    parent = verify_lock(parent_output / "selection_lock.json")
    if parent["selected"] != SELECTED:
        raise ValueError("This comparison is fixed to the existing V2+VD3@1 selection")
    if output.exists():
        raise FileExistsError("Use a new output directory; do not overwrite a precommitted comparison")
    output.mkdir(parents=True)
    protocol = protocol_config(parent)
    protocol["protocol_sha256"] = canonical_hash(protocol)
    write_json(output / "protocol.json", protocol)
    return protocol


def verify_protocol(output, parent_output):
    parent = verify_lock(parent_output / "selection_lock.json")
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    expected = protocol.pop("protocol_sha256")
    if canonical_hash(protocol) != expected or parent["lock_sha256"] != protocol["parent_selection_lock_sha256"]:
        raise ValueError("Strong-comparator protocol or parent selection commitment changed")
    current = protocol_config(parent)
    if current["source_sha256_lf"] != protocol["source_sha256_lf"]:
        raise ValueError("Comparison implementation changed after protocol commitment")
    protocol["protocol_sha256"] = expected
    return protocol


def normal_summary(alarms):
    return dict(normal_rows=sum(map(len, alarms)), normal_fp_rows=int(sum(np.sum(x) for x in alarms)),
                normal_records=len(alarms), normal_fp_records=int(sum(np.any(x) for x in alarms)),
                normal_record_fpr=float(np.mean([np.any(x) for x in alarms])))


def metrics(normal_alarms, abnormal_alarms, normal_scores, abnormal_scores):
    result = normal_summary(normal_alarms)
    tp, total = int(sum(np.sum(x) for x in abnormal_alarms)), sum(map(len, abnormal_alarms))
    fp, fn = result["normal_fp_rows"], total-tp
    delays = [np.flatnonzero(x)[0]*.1 for x in abnormal_alarms if np.any(x)]
    result.update(tp=tp, fn=fn, abnormal_rows=total, abnormal_records=len(abnormal_alarms),
                  detected_records=int(sum(np.any(x) for x in abnormal_alarms)),
                  missed_records=int(sum(not np.any(x) for x in abnormal_alarms)),
                  row_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.,
                  row_precision=tp/(tp+fp) if tp+fp else 0., row_recall=tp/total if total else 0.,
                  hit_only_median_delay_s=float(np.median(delays)) if delays else None,
                  normal_unscored_rows=int(sum(np.sum(~np.isfinite(x)) for x in normal_scores)),
                  abnormal_unscored_rows=int(sum(np.sum(~np.isfinite(x)) for x in abnormal_scores)))
    return result


def circular_blocks(rng, count, length, repetitions):
    starts = rng.integers(0, count, size=(repetitions, int(np.ceil(count/length))))
    return ((starts[:, :, None] + np.arange(length)[None, None, :]) % count).reshape(repetitions, -1)[:, :count]


def paired_bootstrap(normal_alarms, abnormal_alarms, settings):
    """Preserve record lengths and pair resampled records across every model."""
    first = next(iter(normal_alarms))
    rng = np.random.default_rng(settings["seed"])
    n_indices = circular_blocks(rng, len(normal_alarms[first]), settings["normal_block_records"], settings["repetitions"])
    a_indices = circular_blocks(rng, len(abnormal_alarms[first]), settings["abnormal_block_records"], settings["repetitions"])
    f1, point = {}, {}
    lengths = np.array([len(x) for x in abnormal_alarms[first]])
    positives = lengths[a_indices].sum(1)
    for model in normal_alarms:
        normal_counts = np.array([np.sum(x) for x in normal_alarms[model]])
        abnormal_counts = np.array([np.sum(x) for x in abnormal_alarms[model]])
        tp, fp = abnormal_counts[a_indices].sum(1), normal_counts[n_indices].sum(1)
        f1[model] = 2*tp/(tp+fp+positives)
        point[model] = 2*abnormal_counts.sum()/(abnormal_counts.sum()+normal_counts.sum()+lengths.sum())
    rows = []
    for first_model, second_model in settings["pairs"]:
        low, high = np.quantile(f1[first_model]-f1[second_model], [.025, .975], method="linear")
        includes_zero = bool(low <= 0 <= high)
        rows.append(dict(first_model=first_model, second_model=second_model,
                         f1_difference=point[first_model]-point[second_model], ci95_low=low, ci95_high=high,
                         includes_zero=includes_zero, first_model_bootstrap_win_fraction=float(np.mean(f1[first_model] > f1[second_model])),
                         interpretation=("No directional separation within this resampling; not an equivalence test" if includes_zero else
                                         "Directional difference within this single observed event only"),
                         changed_selection=False))
    return rows


def injection_audit(suite, generator, records, phase, offset, settings, output):
    controls = suite.alarms(suite.score(records), .01)
    seeds = settings["development_seeds"] if phase == "development" else settings["evaluation_seeds"]
    summary, detail = [], []
    for family, family_spec in settings["families"].items():
        for target in family_spec["targets"]:
            for strength in family_spec["strengths"]:
                for fraction in settings["onsets"]:
                    onsets = [min(len(r)-1, max(1, int(len(r)*fraction))) for r in records]
                    for seed in seeds:
                        injected = [generator.inject(r, family, target, strength, seed+1009*(i+offset), onset)
                                    for i, (r, onset) in enumerate(zip(records, onsets))]
                        for original, changed, onset in zip(records, injected, onsets):
                            if original[:onset].tobytes() != changed[:onset].tobytes():
                                raise AssertionError("Injection changed observations before onset")
                        alarms = suite.alarms(suite.score(injected), .01)
                        for model in MODELS:
                            rows = []
                            for i, (alert, control, onset) in enumerate(zip(alarms[model], controls[model], onsets)):
                                hit = np.flatnonzero(alert[onset:])
                                rows.append(dict(phase=phase, model=model, family=family, target=target, strength=strength,
                                            onset_fraction=fraction, seed=seed, record=i+offset, rows=len(alert), onset=onset,
                                            detected=bool(len(hit)), control_detected=bool(np.any(control[onset:])),
                                            pre_onset_alarm=bool(np.any(alert[:onset])),
                                            delay_s=float(hit[0]*.1) if len(hit) else None))
                            detail.extend(rows)
                            hit_rate, control_rate = np.mean([x["detected"] for x in rows]), np.mean([x["control_detected"] for x in rows])
                            delays = [x["delay_s"] for x in rows if x["delay_s"] is not None]
                            summary.append(dict(phase=phase, model=model, family=family, target=target, strength=strength,
                                            onset_fraction=fraction, seed=seed, alpha=.01, records=len(rows),
                                            detection_rate=hit_rate, control_rate=control_rate, paired_increase=hit_rate-control_rate,
                                            detected=sum(x["detected"] for x in rows), missed=sum(not x["detected"] for x in rows),
                                            pre_onset_alarm_rate=np.mean([x["pre_onset_alarm"] for x in rows]),
                                            hit_only_median_delay_s=float(np.median(delays)) if delays else None))
        print(f"{phase}: same-condition strong-comparator injection {family} complete", flush=True)
    pd.DataFrame(detail).to_csv(output / "local" / f"{phase}_injection_records.csv.gz", index=False, compression="gzip")
    return summary


def prediction_table(scores, alarms, records, source, offset):
    result = pd.DataFrame(dict(source=source,
                    record=np.concatenate([np.full(len(record), offset+i) for i, record in enumerate(records)]),
                    position=np.concatenate([np.arange(len(record)) for record in records])))
    for model in MODELS:
        result[f"{model}|score"] = np.concatenate(scores[model])
        for alpha in ALPHAS:
            result[f"{model}|alarm@{alpha:g}"] = np.concatenate(alarms[alpha][model])
    return result


def verify_existing_reference(rows, parent_output):
    original = pd.read_csv(parent_output / "actual_metrics.csv")
    checked = 0
    for row in rows:
        if row["model"] not in ("V2", SELECTED):
            continue
        match = original[(original.split == row["split"]) & (original.model == row["model"]) &
                         (original.alpha == row["alpha"]) & (original.abnormal_subset == row["abnormal_subset"])]
        if len(match) != 1:
            raise AssertionError("Missing original locked reference comparison")
        for field in ("tp", "fn", "normal_fp_rows", "normal_fp_records", "row_f1", "detected_records"):
            if not np.isclose(row[field], match.iloc[0][field], rtol=1e-12, atol=1e-12):
                raise AssertionError(f"Locked reference changed: {row['split']}/{row['model']}/{field}")
        checked += 1
    return checked


def verify_existing_injections(table, parent_output):
    checked = 0
    keys = ["model", "family", "target", "strength", "onset_fraction", "seed", "alpha"]
    for phase in SPLITS:
        existing = pd.read_csv(parent_output / f"{phase}_injection.csv").set_index(keys)
        subset = table[(table.phase == phase) & table.model.isin(["V2", SELECTED])]
        for row in subset.to_dict("records"):
            reference = existing.loc[tuple(row[key] for key in keys)]
            for field in ("records", "detected", "missed", "detection_rate", "control_rate", "paired_increase", "pre_onset_alarm_rate"):
                if not np.isclose(row[field], reference[field], rtol=1e-10, atol=1e-12):
                    raise AssertionError(f"Locked injection reference changed: {phase}/{row['model']}/{field}")
            checked += 1
    return checked


def run(data_dir, output, parent_output):
    protocol = verify_protocol(output, parent_output)
    if (output / "summary.json").exists():
        raise FileExistsError("Completed comparison exists; use a new output directory")
    (output / "local").mkdir(exist_ok=True)
    start = time.perf_counter()
    normal, normal_source = load_records(data_dir, "normal")
    write_json(output / "started.json", dict(started_utc=utc_now(), protocol_sha256=protocol["protocol_sha256"],
                                            normal_source=normal_source, abnormal_opened=False))
    all_metrics, all_bootstrap, all_injections, normal_development, fitted = [], [], [], [], {}
    # Development is completed with normal data before opening the abnormal file.
    abnormal = None
    for phase, (train_end, cal_end, test_end) in SPLITS.items():
        print(f"{phase}: fitting original-model comparators on normal {train_end} / calibration 120", flush=True)
        train, calibration, test = normal[:train_end], normal[train_end:cal_end], normal[cal_end:test_end]
        suite = ComparisonSuite().fit(train, calibration)
        generator = CausalGenerator().fit(train)
        fitted[phase] = dict(normal_training_records=train_end, calibration_records=120,
                             normal_test_records=len(test), calibration_maxima=suite.calibration,
                             knn=suite.knn.metadata(), ridge=suite.ridge.metadata())
        n_scores = suite.score(test)
        n_alarms = {alpha: suite.alarms(n_scores, alpha) for alpha in ALPHAS}
        if phase == "development":
            for alpha in ALPHAS:
                for model in MODELS:
                    normal_development.append(dict(phase=phase, model=model, alpha=alpha, **normal_summary(n_alarms[alpha][model])))
        else:
            if abnormal is None:
                verify_protocol(output, parent_output)
                abnormal, abnormal_source = load_records(data_dir, "abnormal", parent_output / "selection_lock.json")
                write_json(output / "abnormal_access.json", dict(opened_utc=utc_now(), source=abnormal_source,
                           protocol_sha256=protocol["protocol_sha256"], normal_development_completed=True,
                           source_previously_observed=True, no_selection_or_rules_changed=True))
            a_scores = suite.score(abnormal)
            a_alarms = {alpha: suite.alarms(a_scores, alpha) for alpha in ALPHAS}
            for alpha in ALPHAS:
                for model in MODELS:
                    for subset, sl in (("all21", slice(None)), ("front10", slice(0, 10)), ("back11", slice(10, None))):
                        all_metrics.append(dict(split=phase, model=model, alpha=alpha, abnormal_subset=subset,
                                **metrics(n_alarms[alpha][model], a_alarms[alpha][model][sl], n_scores[model], a_scores[model][sl])))
                all_bootstrap.extend([dict(split=phase, alpha=alpha, abnormal_subset="all21", **row)
                                      for row in paired_bootstrap(n_alarms[alpha], a_alarms[alpha], protocol["bootstrap"])])
            predictions = pd.concat([prediction_table(n_scores, n_alarms, test, "normal", cal_end),
                                     prediction_table(a_scores, a_alarms, abnormal, "abnormal", 0)], ignore_index=True)
            predictions.to_csv(output / "local" / f"{phase}_row_predictions.csv.gz", index=False, compression="gzip")
        all_injections.extend(injection_audit(suite, generator, test, phase, cal_end, protocol["injections"], output))
        write_json(output / "fitted_metadata.json", fitted)
    checked_actual = verify_existing_reference(all_metrics, parent_output)
    actual, injection, bootstrap = pd.DataFrame(all_metrics), pd.DataFrame(all_injections), pd.DataFrame(all_bootstrap)
    checked_injection = verify_existing_injections(injection, parent_output)
    actual.to_csv(output / "actual_metrics.csv", index=False)
    injection.to_csv(output / "injection_metrics.csv", index=False)
    bootstrap.to_csv(output / "paired_block_bootstrap.csv", index=False)
    pd.DataFrame(normal_development).to_csv(output / "normal_development.csv", index=False)
    family = injection.groupby(["phase", "model", "family"], as_index=False)[["detection_rate", "control_rate", "paired_increase"]].mean()
    family.to_csv(output / "injection_family_summary.csv", index=False)
    primary = actual[actual.alpha.eq(.01) & actual.abnormal_subset.eq("all21")]
    primary_bootstrap = bootstrap[bootstrap.alpha.eq(.01)]
    verify_protocol(output, parent_output)
    summary = dict(passed=True, completed_utc=utc_now(), protocol_sha256=protocol["protocol_sha256"],
                   parent_selection_lock_sha256=protocol["parent_selection_lock_sha256"],
                   model_selection_unchanged=SELECTED, new_operational_rules=False,
                   compared_models=MODELS, normal_development_records=60,
                   actual_metric_rows=len(actual), injection_condition_model_rows=len(injection),
                   unchanged_original_actual_metric_rows=checked_actual,
                   unchanged_original_injection_condition_model_rows=checked_injection,
                   primary_all21_alpha01=primary.to_dict("records"), primary_paired_bootstrap=primary_bootstrap.to_dict("records"),
                   same_condition_injection_family_summary=family.to_dict("records"),
                   comparison_scope="Feature-matched five-dimensional 5NN and historical three-channel Ridge, with identical fit/calibration/test records, preprocessing, injections and joint per-model record-max budget",
                   limitations=["All actual abnormal recording fragments arise from the same previously observed event",
                                "A/B normal test sets overlap; they are not independent replications",
                                "Bootstrap conditions on fitted models and calibration; blocks are recording fragments, not independent failures",
                                "A CI containing zero is not evidence of equivalence; no superiority claim in that case",
                                "The source event and comparator results had been viewed historically before this audit",
                                "No detector, threshold, R1/R2 rule or selected candidate was changed based on results"],
                   elapsed_seconds=time.perf_counter()-start)
    write_json(output / "summary.json", summary)
    print(f"Strong-comparator audit completed in {summary['elapsed_seconds']:.1f}s", flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--parent-output", type=Path, default=HERE / "outputs")
    parser.add_argument("--output", type=Path, default=HERE / "outputs/strong_baselines")
    parser.add_argument("--phase", choices=("all", "prepare", "evaluate"), default="all")
    args = parser.parse_args()
    output, parent = args.output.resolve(), args.parent_output.resolve()
    if args.phase in ("prepare", "all"):
        result = prepare(output, parent)
        print(f"Comparison protocol committed before data access: {result['protocol_sha256']}", flush=True)
    if args.phase in ("evaluate", "all"):
        with threadpool_limits(limits=1):
            run(args.data_dir.resolve(), output, parent)


if __name__ == "__main__":
    main()
