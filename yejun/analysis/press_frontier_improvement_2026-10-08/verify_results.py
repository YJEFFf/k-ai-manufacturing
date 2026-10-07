"""Recompute published retrospective metrics from local saved predictions.

Does not fit or select models. Reads source data neither directly nor indirectly.
The row-level files stay local; this audit's compact JSON may be versioned.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from run_experiment import verify_lock, write_json
from build_hwpx_copy import verify_protected_sources

HERE = Path(__file__).resolve().parent


def close(actual, expected, label):
    if pd.isna(actual) and pd.isna(expected):
        return
    if not np.isclose(float(actual), float(expected), atol=1e-12, rtol=1e-10):
        raise AssertionError(f"{label}: {actual!r} != {expected!r}")


def verify_actual(output):
    table = pd.read_csv(output / "actual_metrics.csv")
    checked = 0
    for split, expected_n in (("A", 4090), ("B", 6097)):
        pred = pd.read_csv(output / "local" / f"{split}_row_predictions.csv.gz", float_precision="round_trip")
        normal = pred.source.eq("normal")
        abnormal = pred.source.eq("abnormal")
        assert normal.sum() == expected_n and abnormal.sum() == 600
        assert not pred.duplicated(["source", "record", "position"]).any()
        metadata = json.loads((output / f"{split}_fitted_metadata.json").read_text(encoding="utf-8"))
        for row in table[table.split.eq(split)].itertuples(index=False):
            name, alpha = row.model, row.alpha
            key = f"{name}|alarm@{alpha:g}"
            alert = pred[key].to_numpy(bool)
            if name.startswith("OR_"):
                other = name.removeprefix("OR_V2_")
                expected = pred[f"V2|alarm@{alpha:g}"].to_numpy(bool) | pred[f"{other}|alarm@{alpha:g}"].to_numpy(bool)
                assert not row.equal_single_budget
            else:
                scores = pred[f"{name}|score"].to_numpy(float)
                cal = np.array([-np.inf if x is None else x for x in metadata["calibration_maxima"][name]])
                assert len(cal) == 120
                # Direct rank count, independent of the scoring implementation.
                p = (1 + (cal[:, None] >= scores[None, :]).sum(axis=0)) / 121
                expected = np.isfinite(scores) & (p <= alpha)
                assert row.equal_single_budget
            np.testing.assert_array_equal(alert, expected, err_msg=f"{split}/{name}/{alpha}")
            subset = abnormal.copy()
            if row.abnormal_subset == "front10":
                subset &= pred.record.lt(10)
            elif row.abnormal_subset == "back11":
                subset &= pred.record.ge(10)
            a = pred.loc[subset, ["record", "position"]].assign(alert=alert[subset])
            n = pred.loc[normal, ["record", "position"]].assign(alert=alert[normal])
            tp, fp, fn = int(a.alert.sum()), int(n.alert.sum()), int((~a.alert).sum())
            record_hit = a.groupby("record").alert.any()
            fp_rec = int(n.groupby("record").alert.any().sum())
            delays = a[a.alert].groupby("record").position.min() * .1
            expected_fields = dict(tp=tp, fn=fn, normal_fp_rows=fp,
                normal_rows=len(n), abnormal_rows=len(a),
                normal_records=n.record.nunique(), normal_fp_records=fp_rec,
                normal_record_fpr=fp_rec / n.record.nunique(),
                abnormal_records=len(record_hit), detected_records=record_hit.sum(),
                missed_records=(~record_hit).sum(),
                row_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
                row_precision=tp/(tp+fp) if tp+fp else 0,
                row_recall=tp/len(a), hit_only_median_delay_s=delays.median(),
                hit_only_max_delay_s=delays.max())
            for field, expected in expected_fields.items():
                close(getattr(row, field), expected, f"{split}/{name}/{alpha}/{row.abnormal_subset}/{field}")
            checked += 1
        base = table[(table.split == split) & (table.model == "V2") &
                     (table.alpha == .01) & (table.abnormal_subset == "all21")].iloc[0]
        historical = dict(A=(556, 0, 44), B=(569, 3, 31))[split]
        assert (base.tp, base.normal_fp_rows, base.fn) == historical, "Historical V2 reproduction changed"
    return dict(metric_rows=checked, calibration_alarm_equality=True,
                all_rows_and_records_retained=True, historical_v2_counts_reproduced=True)


def verify_injection(output, models):
    result = {}
    keys = ["model", "family", "target", "strength", "onset_fraction", "seed", "alpha"]
    for phase in ("development", "A", "B"):
        parts = []
        for chunk in pd.read_csv(output / "local" / f"{phase}_injection_records.csv.gz", chunksize=100000):
            parts.append(chunk[chunk.model.isin(models)])
        rows = pd.concat(parts, ignore_index=True)
        assert not rows.duplicated(keys + ["record"]).any()
        assert ((rows.onset >= 0) & (rows.onset < rows.rows)).all()
        assert rows.loc[~rows.detected, "delay_s"].isna().all()
        grouped = rows.groupby(keys, dropna=False)
        summary = pd.read_csv(output / f"{phase}_injection.csv")
        count = 0
        for row in summary[summary.model.isin(models)].itertuples(index=False):
            group = grouped.get_group(tuple(getattr(row, key) for key in keys))
            expected = dict(records=len(group), detected=group.detected.sum(),
                missed=(~group.detected).sum(), detection_rate=group.detected.mean(),
                control_rate=group.control_detected.mean(),
                paired_increase=group.detected.mean()-group.control_detected.mean(),
                pre_onset_alarm_rate=group.pre_onset_alarm.mean(),
                hit_only_median_delay_s=group.delay_s.median())
            for key, value in expected.items():
                close(getattr(row, key), value, f"{phase}/{row.model}/{key}")
            count += 1
        result[phase] = dict(detail_rows=len(rows), aggregate_rows=count)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "outputs")
    args = parser.parse_args()
    output = args.output.resolve()
    lock = verify_lock(output / "selection_lock.json")
    selection = json.loads((output / "selection.json").read_text(encoding="utf-8"))
    ranking = pd.read_csv(output / "development_candidates.csv")
    eligible = ranking[ranking.selectable & ranking.gate_pass]
    expected = None if eligible.empty else eligible.iloc[0].model
    assert expected == selection["selected"] == lock["selected"]
    models = ["V2"] + ([expected] if expected and expected != "V2" else [])
    result = dict(passed=True, lock_sha256=lock["lock_sha256"], selected=expected,
                  protected_sources=verify_protected_sources(),
                  actual=verify_actual(output), injection=verify_injection(output, models),
                  injection_audit_models=models,
                  limitations="Saved prediction arithmetic and source integrity; not independent failure validation")
    write_json(output / "verification.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
