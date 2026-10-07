"""Reaggregate normal-sensitivity outcomes without reading any raw dataset.

Run after audit_normal_sensitivity.py. The reviewed frequency table is optional;
the standalone submission requires only files created by its own audit run.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

import numpy as np
import pandas as pd

from run_experiment import canonical_hash, file_hash, utc_now, verify_lock, write_json

HERE = Path(__file__).resolve().parent
KEYS = ["split", "family", "target", "strength", "sign", "seed", "onset_fraction", "model"]
DERIVED_FILES = {"aggregation_verification.json", "derived_family_macro.csv", "derived_calibration_deltas.csv"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_number(actual, expected, message):
    require((pd.isna(actual) and pd.isna(expected)) or abs(actual - expected) < 1e-14, message)


def verify_scenarios(detail, aggregate, first_record, end_record):
    """Check counts, denominators and hit-only delay using recorded outcomes."""
    groups = detail.groupby(KEYS, dropna=False)
    require(len(groups) == len(aggregate), "Scenario count differs between detail and summary")
    require(not aggregate.duplicated(KEYS).any(), "Duplicate scenario summary")
    for row in aggregate.to_dict(orient="records"):
        block = groups.get_group(tuple(row[k] for k in KEYS))
        count = end_record - first_record
        require(len(block) == count and set(block.record) == set(range(first_record, end_record)),
                "Missing or duplicate normal recording in scenario")
        hit, control = int(block.detected.sum()), int(block.control_detected.sum())
        expected = dict(records=count, detected=hit, missed=count-hit, control_detected=control,
                        pre_onset_alarm_records=int(block.pre_onset_alarm.sum()))
        for name, value in expected.items():
            require(row[name] == value, f"Recorded outcome aggregation mismatch: {name}")
        for name, value in dict(detection_rate=hit/count, control_rate=control/count,
                                paired_increase=(hit-control)/count).items():
            same_number(row[name], value, f"Recorded rate aggregation mismatch: {name}")
        delays = block.loc[block.detected, "delay_s"]
        require(delays.notna().all() and (delays >= 0).all(), "Detected recording has invalid delay")
        same_number(row["hit_only_median_delay_s"], delays.median(), "Hit-only median delay mismatch")
        require(block.loc[~block.detected, "delay_s"].isna().all(), "Missed recording has a delay")
        require(((block.onset >= 0) & (block.onset < block.rows)).all(), "Onset is outside recording")
        require(np.allclose((block.delay_s.dropna() / .1).round(), block.delay_s.dropna() / .1, rtol=0, atol=1e-12),
                "Delay is outside the 0.1-second observation grid")
    return aggregate.groupby(["split", "family", "model"], as_index=False).agg(
        scenarios=("detection_rate", "size"), mean_detection_rate=("detection_rate", "mean"),
        mean_control_rate=("control_rate", "mean"), mean_paired_increase=("paired_increase", "mean"))


def verify_run(output, experiment_output=None, reference_frequency_csv=None):
    output = Path(output).resolve()
    experiment_output = Path(experiment_output).resolve() if experiment_output else output.parent
    summary_path = output / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    require(summary["passed"] is True and summary["abnormal_file_read"] is False,
            "Source audit did not complete as normal-only")
    checked = 0
    for name, digest in summary["output_sha256"].items():
        # These are post-run products and may refer to a previous run's summary.
        if name in DERIVED_FILES:
            continue
        require(Path(name).name == name, "Output inventory contains a non-local path")
        require(file_hash(output / name) == digest, f"Source output digest mismatch: {name}")
        checked += 1
    locked = json.loads((output / "protocol_lock.json").read_text(encoding="utf-8"))
    digest = locked.pop("protocol_lock_sha256")
    require(canonical_hash(locked) == digest == summary["protocol_lock_sha256"], "Protocol digest mismatch")
    require(file_hash(HERE / "audit_normal_sensitivity.py", True) == locked["source_sha256_lf"],
            "Audit source differs from locked protocol")
    selection = verify_lock(experiment_output / "selection_lock.json")
    require(selection["lock_sha256"] == summary["original_selection_lock_sha256"] == locked["original_selection_lock_sha256"],
            "Original model selection digest mismatch")

    frequency_matches = None
    if reference_frequency_csv is not None:
        reference = pd.read_csv(reference_frequency_csv)
        current = pd.read_csv(output / "B_frequency.csv")
        for row in current.itertuples():
            match = reference[reference.model.eq(row.model)]
            match = (match[match.delta_hz.eq("original")] if row.scenario == "original" else
                     match[pd.to_numeric(match.delta_hz, errors="coerce").eq(row.delta_hz)])
            require(len(match) == 1, "Missing or duplicate reviewed frequency scenario")
            old = match.iloc[0]
            require(row.alarm_records == old.fp_records and row.records == old.records,
                    "Reviewed frequency count mismatch")
            same_number(row.normal_record_fpr, old.fp_rate, "Reviewed frequency rate mismatch")
        frequency_matches = len(current)

    protocol = locked["protocol"]
    expected_scenarios = len(protocol["models"]) * len(protocol["onset_fractions"]) * sum(
        np.prod([len(spec[key]) for key in ["targets", "strengths", "signs", "seeds"]])
        for spec in protocol["new_families"].values())
    checks, family_tables, contamination_tables = [], [], []
    for split, (_, start, stop) in protocol["splits"].items():
        detail_path = output / "local" / f"{split}_new_family_records.csv.gz"
        detail = pd.read_csv(detail_path)
        aggregate = pd.read_csv(output / f"{split}_new_families.csv")
        require(len(aggregate) == expected_scenarios, "Missing locked scenario")
        macro = verify_scenarios(detail, aggregate, start, stop)
        family_tables.append(macro)
        contamination = pd.read_csv(output / f"{split}_calibration_contamination.csv")
        for row in contamination[contamination.contaminated_records.eq(0)].itertuples():
            match = macro[macro.family.eq(row.evaluation_family) & macro.model.eq(row.model)]
            require(len(match) == 1, "Unknown contamination evaluation family")
            for column in ["mean_detection_rate", "mean_control_rate", "mean_paired_increase"]:
                same_number(getattr(row, column), match.iloc[0][column], "Zero-contamination control mismatch")
        for _, group in contamination.groupby(["model", "contamination_family", "evaluation_family"]):
            group = group.sort_values("contaminated_records")
            require(list(group.contaminated_records) == [0, *protocol["calibration_contamination"]["counts"]],
                    "Missing or duplicate contamination count")
            require(np.all(np.diff(group.contaminated_maximum) >= -1e-14), "Calibration maximum decreased")
            require(np.all(np.diff(group.mean_detection_rate) <= 1e-14), "Detection increased with raised threshold")
            first = group.iloc[0]
            contamination_tables.append(group.assign(
                detection_change=group.mean_detection_rate-first.mean_detection_rate,
                maximum_ratio=group.contaminated_maximum/group.baseline_maximum))
        checks.append(dict(split=split, record_scenario_rows=len(detail), scenario_model_rows=len(aggregate),
                           aggregation_exact=True, calibration_zero_control_identical=True,
                           detail_sha256=file_hash(detail_path)))
    pd.concat(family_tables).to_csv(output / "derived_family_macro.csv", index=False)
    pd.concat(contamination_tables).to_csv(output / "derived_calibration_deltas.csv", index=False)
    result = dict(passed=True, verified_utc=utc_now(),
        method="Independent CSV aggregation from record outcomes; no model refit or raw dataset access",
        verifier_source_sha256_lf=file_hash(Path(__file__), True), source_summary_sha256=file_hash(summary_path),
        protocol_lock_sha256=digest, original_selection_lock_sha256=selection["lock_sha256"],
        summary_output_hashes_checked=checked, reviewed_B_frequency_rows_matched=frequency_matches,
        record_aggregation_checks=checks, calibration_contamination_monotone_for_locked_scenarios=True,
        independent_failure_validation=False,
        derived_output_sha256={name:file_hash(output/name) for name in sorted(DERIVED_FILES) if name.endswith(".csv")})
    write_json(output / "aggregation_verification.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-output", type=Path)
    parser.add_argument("--reference-frequency-csv", type=Path)
    args = parser.parse_args()
    result = verify_run(args.output, args.experiment_output, args.reference_frequency_csv)
    rows = sum(check["record_scenario_rows"] for check in result["record_aggregation_checks"])
    print(f"Normal-sensitivity aggregation verified: {rows} recording/scenario outcomes")


if __name__ == "__main__":
    main()
