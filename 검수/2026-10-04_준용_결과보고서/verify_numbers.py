"""Independent numerical audit; this does not retrain the report's models.

Usage: python verify_numbers.py --repo REPO --source EXTRACTED_GIT_SNAPSHOT --out RESULT.json
"""
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def audit_data(path):
    rows = read_csv(path)
    times = [datetime.fromisoformat(r["TimeStamp"]) for r in rows]
    groups = [[]]
    for i, row in enumerate(rows):
        if i and abs((times[i] - times[i - 1]).total_seconds() - .1) > 1e-6:
            groups.append([])
        groups[-1].append(i)
    identity = [tuple((k, v) for k, v in r.items() if k) for r in rows]
    duration = (times[-1] - times[0]).total_seconds()
    return {
        "path": str(path), "sha256": sha(path), "rows": len(rows),
        "records": len(groups), "record_length_counts": dict(sorted(Counter(map(len, groups)).items())),
        "duplicate_timestamp_sensor_label_rows": len(identity) - len(set(identity)),
        "empty_cells_excluding_csv_index": sum(v == "" for r in rows for k, v in r.items() if k),
        "first_timestamp": times[0].isoformat(), "last_timestamp": times[-1].isoformat(),
        "elapsed_seconds": duration,
        "nominal_observed_seconds": len(rows) * .1,
        "nominal_observed_fraction": len(rows) * .1 / duration,
        "first_10_record_rows": sum(len(g) for g in groups[:10]),
        "after_first_10_record_rows": sum(len(g) for g in groups[10:]),
        "splits": {s: {"train_records": a, "valid_records": b-a, "test_records": len(groups)-b,
                        "test_rows": sum(len(g) for g in groups[b:]),
                        "test_elapsed_seconds": (times[-1] - times[groups[b][0]]).total_seconds()}
                   for s, (a, b) in {"A": (360, 480), "B": (300, 420)}.items() if len(groups) > b},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    data_dir = next(p.parent for p in args.repo.glob("*/*/press_data_normal.csv"))
    result = {"scope": "Raw-data counts, supplied-output arithmetic and mathematical counterexamples; no model retraining.",
              "raw": {name: audit_data(data_dir / name) for name in ["press_data_normal.csv", "outlier_data.csv"]}}
    tvt = args.source / "claude/code/press/tvt"
    tests = read_csv(tvt / "outputs/tvt_test.csv")
    errors = []
    for row in tests:
        tp, fp, fn = (int(row[k]) for k in ("tp", "fp", "fn"))
        actual = 2 * tp / (2 * tp + fp + fn) if tp else 0.
        if abs(actual - float(row["f1"])) > 1e-12:
            errors.append(row)
    result["provided_test_csv_arithmetic"] = {"rows_checked": len(tests), "inconsistent_rows": errors}
    result["primary_alpha_rows"] = [r for r in tests if float(r["alpha"]) == .01 and r["model"] in ("v2", "v2+H1", "v2+H1+H2")]
    operating = read_csv(args.source / "claude/code/press/domain/outputs/06_operating_regime_records.csv")
    fps = [r for r in operating if r["part_B"] == "test" and float(r["fa1_B_v2"] or 0) > 0]
    v2_b = next(r for r in tests if r["split"] == "B" and r["model"] == "v2" and r["mode"] == "record" and float(r["alpha"]) == .01)
    result["record_metric_check"] = {
        "normal_false_positive_records_from_provided_operating_csv": [{"record": r["rec"], "length": int(r["n"])} for r in fps],
        "false_positive_row_weight_sum": sum(int(r["n"]) for r in fps),
        "abnormal_test_records": result["raw"]["outlier_data.csv"]["records"] - 10,
        "reported_v2_B_record_F1": float(v2_b["f1"]),
        "equal_record_weight_F1_given_all_11_detected": 22 / (22 + len(fps)),
        "explanation": "record_flags broadcasts a group decision to rows; evaluate passes row labels to f1_counts. The CSV's record mode is length-weighted.",
    }
    selection = tvt / "outputs/tvt_selection.json"
    expected = (tvt / "outputs/tvt_selection.sha256").read_text().strip()
    result["selection_hash"] = {"expected": expected, "actual": sha(selection), "matches": sha(selection) == expected,
                                "limitation": "File integrity only; this cannot establish a historically unexposed holdout."}
    result["confidence_arithmetic"] = {
        "binomial_one_sided_95_upper_0_of_120": 1 - .05 ** (1 / 120),
        "binomial_one_sided_95_upper_0_of_180": 1 - .05 ** (1 / 180),
        "binomial_one_sided_95_lower_11_of_11": .05 ** (1 / 11),
        "limitation": "These bounds require a valid sampling model; adjacent records from one event are not 11 independent fault events.",
    }
    result["aliasing_counterexamples"] = {
        "max_difference_0p6Hz_and_60p6Hz_at_10Hz": max(abs(math.sin(2*math.pi*.6*n/10)-math.sin(2*math.pi*60.6*n/10)) for n in range(50)),
        "sample_sd_20Hz_unit_sine_at_10Hz_50_samples": statistics.pstdev(math.sin(2*math.pi*20*n/10) for n in range(50)),
        "continuous_rms_20Hz_unit_sine": math.sqrt(.5),
        "limitation": "Counterexamples to universal identifiability/RMS claims, not a claim that this dataset actually contains 20 Hz vibration.",
    }
    claimed = ["claude/code/press/cases/03_facts_extra.py", "claude/code/press/tvt/04_validation.py", "claude/code/press/tvt/05_test_predictions.py", "claude/code/press/tvt/outputs/test_predictions_A.csv", "claude/code/press/tvt/outputs/test_predictions_B.csv"]
    result["claimed_artifacts_in_reviewed_commit"] = {name: (args.source / name).is_file() for name in claimed}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("raw", "primary_alpha_rows")}, ensure_ascii=False, indent=2))
    print(json.dumps(result["raw"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
