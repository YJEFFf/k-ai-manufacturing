"""Holdout data boundaries and no-refit inference, not synthetic performance claims."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_holdout as H
from frontier_model import FrontierSuite


def frame(seed=61, rows=24):
    rng = np.random.default_rng(seed)
    values = rng.normal(size=(rows, 3)) * [.002, .003, 20.]
    values[:, 2] += 70 * np.sin(np.arange(rows) * .4)
    result = pd.DataFrame(values, columns=H.D.SENSORS)
    result[H.D.TIME] = pd.date_range("2030-01-01", periods=rows, freq="100ms")
    return result


def write_csv(tmp_path, data, name="input.csv"):
    path = tmp_path / name
    data.to_csv(path, index=False)
    return path


def provenance():
    return dict(process=H.PROCESS, source_uri="synthetic-contract-test-only", equipment_id="test",
                acquisition_id="test", schema_matches_source=True, sampling_seconds=.1,
                prior_model_development_exposure="previously_seen",
                relationship_to_original_failure="Synthetic software test; no physical failure event")


@pytest.mark.parametrize("change", ["missing_sensor", "nonfinite", "backward", "duplicate_time", "too_long", "bad_label"])
def test_malformed_input_is_rejected_without_dropping_rows(tmp_path, change):
    data = frame(rows=51 if change == "too_long" else 24)
    data["label"] = 0
    if change == "missing_sensor":
        data = data.drop(columns=H.D.SENSORS[0])
    elif change == "nonfinite":
        data.loc[3, H.D.SENSORS[1]] = np.inf
    elif change == "backward":
        data = data.iloc[::-1]
    elif change == "duplicate_time":
        data.loc[3, H.D.TIME] = data.loc[2, H.D.TIME]
    elif change == "bad_label":
        data.loc[3, "label"] = 2
    with pytest.raises(ValueError):
        H.read_input(write_csv(tmp_path, data), label_column="label")


def test_explicit_record_cannot_cross_gap_or_reappear(tmp_path):
    data = frame()
    data["record_id"] = ["A"] * 8 + ["B"] * 8 + ["A"] * 8
    with pytest.raises(ValueError, match="contiguous run"):
        H.read_input(write_csv(tmp_path, data), record_column="record_id")
    data["record_id"] = "A"
    data.loc[12:, H.D.TIME] += pd.Timedelta(seconds=2)
    with pytest.raises(ValueError, match="contiguous 10 Hz"):
        H.read_input(write_csv(tmp_path, data), record_column="record_id")


@pytest.mark.parametrize("variant", ["same", "renamed", "time_shifted", "partial_eight_rows"])
def test_reused_data_cannot_become_holdout_by_renaming_or_time_shift(tmp_path, variant):
    original = frame()
    path = write_csv(tmp_path, original, "known.csv")
    source = H.read_input(path)
    catalog = H.catalog_for_inputs([source], [H.file_hash(path)])
    changed = original.copy()
    if variant in ("time_shifted", "partial_eight_rows"):
        changed[H.D.TIME] += pd.Timedelta(days=20)
    if variant == "partial_eight_rows":
        changed = changed.iloc[5:13]
    other = write_csv(tmp_path, changed, "new.csv")
    outcome = H.duplicate_audit(H.read_input(other), H.file_hash(other), catalog)
    assert not outcome["passed"]
    if variant == "partial_eight_rows":
        assert outcome["overlapping_eight_row_sensor_windows"] == 1


def test_shuffled_rows_do_not_pass_as_new_independent_data(tmp_path):
    data = frame().sample(frac=1, random_state=99)
    with pytest.raises(ValueError, match="strictly increasing"):
        H.read_input(write_csv(tmp_path, data))


def test_conformal_exact_ties_are_not_alarm_but_next_float_is():
    calibration = [2.] * 120
    scores = [2., np.nextafter(2., np.inf), np.nan, -np.inf, np.inf]
    np.testing.assert_array_equal(H.direct_pvalues(scores, calibration) <= .01,
                                  [False, True, False, False, False])


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    directory = tmp_path_factory.mktemp("frozen_holdout_contract")
    training = [H.quantized(frame(seed)[H.D.SENSORS].to_numpy()) for seed in range(100, 111)]
    calibration = [H.quantized(frame(seed)[H.D.SENSORS].to_numpy()) for seed in range(200, 320)]
    suite = FrontierSuite().fit(training).calibrate(calibration)
    for split in ("A", "B"):
        state = dict(schema=H.SCHEMA, split=split, selected=H.SELECTED, alpha=H.ALPHA,
                     guard_state=suite.guard_.state, vd3=H.branch_state(suite.vibration_["VD3"]),
                     fusion_tails={name: suite.fusion_tails_[name].state() for name in ("V2", "VD3")},
                     calibration={name: suite.cal_[name] for name in ("V2", H.SELECTED)})
        H.write_json(directory / f"{split}_state.json", state)
    H.write_json(directory / "exposure_catalog.json", H.catalog_for_inputs([], []))
    manifest = dict(schema=H.SCHEMA, selected=H.SELECTED, alpha=H.ALPHA,
                    files={name: H.file_hash(directory / name) for name in
                           ("A_state.json", "B_state.json", "exposure_catalog.json")})
    manifest["commitment_sha256"] = H.canonical_hash(manifest)
    H.write_json(directory / "manifest.json", manifest)
    return directory


def test_evaluation_never_refits_and_labels_never_change_scores(artifact, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Holdout evaluation attempted to fit or calibrate")
    monkeypatch.setattr(FrontierSuite, "fit", forbidden)
    monkeypatch.setattr(FrontierSuite, "calibrate", forbidden)
    monkeypatch.setattr(H.guard.GuardModel, "fit", forbidden)
    monkeypatch.setattr(H, "independent_vd3_fit", forbidden)
    declaration = tmp_path / "provenance.json"
    H.write_json(declaration, provenance())
    data = frame(789)
    data["label"] = [0] * 12 + [1] * 12
    first_csv = write_csv(tmp_path, data, "first.csv")
    first = H.evaluate(artifact, "A", first_csv, declaration, tmp_path / "first", label_column="label")
    data["label"] = 1 - data.label
    second_csv = write_csv(tmp_path, data, "second.csv")
    second = H.evaluate(artifact, "A", second_csv, declaration, tmp_path / "second", label_column="label")
    a, b = [pd.read_csv(tmp_path / name / "row_predictions.csv") for name in ("first", "second")]
    for name in ("V2", H.SELECTED):
        for field in ("score", "pvalue", "alarm"):
            np.testing.assert_array_equal(a[f"{name}|{field}"], b[f"{name}|{field}"])
    assert first["fit_calls"] == second["calibration_calls"] == 0
    assert first["independent_failure_validation_established"] is False
    assert first["provenance"]["prior_model_development_exposure"] == "previously_seen"
    assert json.loads((tmp_path / "first/evaluation_precommit.json").read_text())["csv_opened"] is False
    with pytest.raises(FileExistsError):
        H.evaluate(artifact, "A", first_csv, declaration, tmp_path / "first")


def test_missing_label_column_produces_no_accuracy_claim(artifact, tmp_path):
    declaration = tmp_path / "provenance.json"
    H.write_json(declaration, provenance())
    data = frame(791)
    data["Equipment_state"] = 1  # Ignored unless explicitly declared a binary label column.
    result = H.evaluate(artifact, "B", write_csv(tmp_path, data), declaration, tmp_path / "unlabeled")
    assert all("row_f1" not in metric and "tp" not in metric for metric in result["metrics"])


def test_wrong_process_is_rejected_before_csv_open(artifact, tmp_path):
    declaration = tmp_path / "provenance.json"
    details = provenance()
    details["process"] = "different_manufacturing_process"
    H.write_json(declaration, details)
    with pytest.raises(ValueError, match="original press process"):
        H.evaluate(artifact, "A", tmp_path / "nonexistent.csv", declaration, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_artifact_mutation_is_rejected(artifact, tmp_path):
    import shutil
    clone = tmp_path / "clone"
    shutil.copytree(artifact, clone)
    state = clone / "A_state.json"
    state.write_bytes(state.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file changed"):
        H.load_artifact(clone)
