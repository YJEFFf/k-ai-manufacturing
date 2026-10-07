"""Audit locked selected/V2 replay against batch on actual recording fragments.

The selected candidate is never changed. The normal sample rule uses record
length/order only: first three, last three, shortest and longest test records.
Every one of the 21 abnormal fragments is replayed. This is a causal reference
implementation audit, not a device or deployment latency benchmark.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

import numpy as np
from threadpoolctl import threadpool_limits

from frontier_model import FrontierSuite, PrefixReplay
from run_experiment import (HERE, experiment_config, file_hash, load_records,
                            utc_now, verify_lock, write_json)


def normal_indices(records):
    lengths = [len(record) for record in records]
    return sorted(set([*range(min(3, len(records))),
                       *range(max(0, len(records) - 3), len(records)),
                       int(np.argmin(lengths)), int(np.argmax(lengths))]))


def replay_mode(suite, models, records, record_ids, expected, expected_alarms, chunks):
    audit = []
    for model in models:
        stream = PrefixReplay(suite, model, alpha=.01)
        max_absolute = 0.
        max_relative = 0.
        peak_buffer = 0
        for index, (record, record_id) in enumerate(zip(records, record_ids)):
            scores, alarms = [], []
            offset, iteration = 0, 0
            empty_score, empty_alarm = stream.push(np.empty((0, 3)), record_id=record_id)
            assert not len(empty_score) and not len(empty_alarm)
            while offset < len(record):
                count = chunks[iteration % len(chunks)]
                score, alert = stream.push(record[offset:offset + count], record_id=record_id)
                scores.extend(score)
                alarms.extend(alert)
                peak_buffer = max(peak_buffer, len(stream.buffer))
                offset += count
                iteration += 1
            actual = np.asarray(scores)
            reference = expected[model][index]
            np.testing.assert_allclose(actual, reference, rtol=1e-9, atol=1e-9,
                                       err_msg=f"{model} {record_id}")
            np.testing.assert_array_equal(alarms, expected_alarms[model][index])
            finite = np.isfinite(reference)
            if finite.any():
                difference = np.abs(actual[finite] - reference[finite])
                max_absolute = max(max_absolute, float(np.max(difference)))
                max_relative = max(max_relative, float(np.max(difference / np.maximum(1., np.abs(reference[finite])))))
        audit.append(dict(model=model, chunks=list(chunks), records=len(records),
                          rows=sum(map(len, records)), alarms_equal=True, scores_allclose=True,
                          score_rtol=1e-9, score_atol=1e-9,
                          maximum_absolute_score_difference=max_absolute,
                          maximum_relative_score_difference=max_relative,
                          maximum_buffer_rows=peak_buffer, empty_chunks_checked=True,
                          record_boundaries_reset=True))
    return audit


def run(data_dir, output):
    start = time.perf_counter()
    lock_path = output / "selection_lock.json"
    lock = verify_lock(lock_path)
    normal, normal_manifest = load_records(data_dir, "normal")
    abnormal, abnormal_manifest = load_records(data_dir, "abnormal", lock_path)
    models = list(dict.fromkeys(["V2", lock["selected"]]))
    models = [model for model in models if model is not None]
    audit = []
    for split, (train_end, cal_end, _) in experiment_config()["evaluation_splits"].items():
        suite = FrontierSuite().fit(normal[:train_end]).calibrate(normal[train_end:cal_end])
        test = normal[cal_end:]
        indices = normal_indices(test)
        records = [test[index] for index in indices] + abnormal
        ids = [("normal", index + cal_end) for index in indices] + [("abnormal", index) for index in range(len(abnormal))]
        expected = suite.score(records)
        expected_alarms = suite.alarms(expected, .01)
        replay = []
        for mode, chunks in (("sample", (1,)), ("irregular_chunks", (3, 1, 8, 2, 5)), ("whole_record", (100,))):
            started = time.perf_counter()
            result = replay_mode(suite, models, records, ids, expected, expected_alarms, chunks)
            replay.extend([dict(mode=mode, **row) for row in result])
            print(f"{split}: {mode} matched for {len(records)} records / {sum(map(len, records))} rows in {time.perf_counter()-started:.1f}s", flush=True)
        # This check is independent of chunk partitioning: future sensor values
        # are replaced while the complete prefix scores/alarms must be preserved.
        cutoffs = [max(1, len(record) // 2) for record in records]
        changed = [record.copy() for record in records]
        for record, cutoff in zip(changed, cutoffs):
            record[cutoff:] += [10., -20., 3000.]
        altered = suite.score(changed)
        altered_alarm = suite.alarms(altered, .01)
        for model in models:
            for index, cutoff in enumerate(cutoffs):
                np.testing.assert_allclose(altered[model][index][:cutoff], expected[model][index][:cutoff], rtol=1e-9, atol=1e-9)
                np.testing.assert_array_equal(altered_alarm[model][index][:cutoff], expected_alarms[model][index][:cutoff])
        audit.append(dict(split=split, normal_record_ids=[index + cal_end for index in indices],
                          abnormal_record_ids=list(range(len(abnormal))), replay=replay,
                          future_suffix_score_and_alarm_invariance=True,
                          reference_uses_explicit_record_boundaries=True))
    verify_lock(lock_path)
    payload = dict(passed=True, completed_utc=utc_now(), selected=lock["selected"],
                   selection_lock_sha256=lock["lock_sha256"],
                   verification_script_sha256_lf=file_hash(Path(__file__), normalized=True),
                   normal=normal_manifest, abnormal=abnormal_manifest,
                   normal_sampling_rule="first three, last three, shortest and longest test records; duplicates removed; no score-based sampling",
                   abnormal_sampling_rule="all 21 recording fragments in both overlapping splits",
                   source_limit="records up to 50 rows; replay stores current complete record and uses upstream record IDs",
                   interpretation="Numerical score/alert equivalence of reference replay; not sensor delivery latency or independent failure validation",
                   elapsed_seconds=time.perf_counter() - start, splits=audit)
    write_json(output / "replay_verification.json", payload)
    print(f"Replay verification passed in {payload['elapsed_seconds']:.1f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "outputs")
    args = parser.parse_args()
    with threadpool_limits(limits=1):
        run(args.data_dir, args.output)


if __name__ == "__main__":
    main()
