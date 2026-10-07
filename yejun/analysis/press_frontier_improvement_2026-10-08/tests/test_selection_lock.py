"""Development isolation and lock enforcement before any abnormal file access."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_experiment as runner


@pytest.fixture
def locked_output(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "locked_sources", lambda: {"model.py": "original"})
    selection = {"selected": "CD+VD1@1"}
    runner.write_json(tmp_path / "config.json", {"development": [0, 300]})
    runner.write_json(tmp_path / "selection.json", selection)
    (tmp_path / "development_candidates.csv").write_text("model,gate_pass\nCD+VD1@1,True\n", encoding="utf-8")
    runner.write_lock(tmp_path, selection)
    return tmp_path


def test_valid_lock_verifies_and_payload_tampering_fails(locked_output):
    path = locked_output / "selection_lock.json"
    original = runner.verify_lock(path)
    assert original["selected"] == "CD+VD1@1"
    original["selected"] = "V2"
    runner.write_json(path, original)
    with pytest.raises(ValueError, match="payload hash"):
        runner.verify_lock(path)


@pytest.mark.parametrize("filename", ["config.json", "selection.json", "development_candidates.csv"])
def test_modifying_any_selection_input_invalidates_lock(locked_output, filename):
    path = locked_output / filename
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        runner.verify_lock(locked_output / "selection_lock.json")


def test_modifying_fitted_or_evaluation_source_invalidates_lock(locked_output, monkeypatch):
    monkeypatch.setattr(runner, "locked_sources", lambda: {"model.py": "changed"})
    with pytest.raises(ValueError, match="source changed"):
        runner.verify_lock(locked_output / "selection_lock.json")


def test_abnormal_bytes_and_csv_are_unreadable_without_lock(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Abnormal bytes or CSV were read before lock verification")

    monkeypatch.setattr(runner, "file_hash", forbidden)
    monkeypatch.setattr(runner.pd, "read_csv", forbidden)
    with pytest.raises(ValueError, match="verified selection lock"):
        runner.load_records(tmp_path, "abnormal")
    with pytest.raises(FileNotFoundError):
        runner.load_records(tmp_path, "abnormal", tmp_path / "nonexistent_lock.json")


def test_rejected_lock_prevents_even_abnormal_hashing(locked_output, monkeypatch):
    original_hash = runner.file_hash
    calls = []

    def guarded_hash(path, *args, **kwargs):
        calls.append(Path(path).name)
        assert Path(path).name != runner.D.FILES["abnormal"]
        return original_hash(path, *args, **kwargs)

    monkeypatch.setattr(runner, "file_hash", guarded_hash)
    (locked_output / "selection.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="selection.json changed"):
        runner.load_records(locked_output, "abnormal", locked_output / "selection_lock.json")
    assert runner.D.FILES["abnormal"] not in calls


@pytest.mark.parametrize("all_fail", [False, True])
def test_development_uses_only_fixed_normal_ranges_and_respects_gates(tmp_path, monkeypatch, all_fail):
    normal = [np.full((1, 3), index, dtype=float) for index in range(600)]
    calls = []

    def identifiers(records):
        return [int(record[0, 0]) for record in records]

    class FakeSuite:
        def fit(self, records):
            calls.append(("fit", identifiers(records)))
            return self

        def calibrate(self, records):
            calls.append(("cal", identifiers(records)))
            return self

        def score(self, records):
            calls.append(("dev", identifiers(records)))
            return records

        def alarms(self, records, alpha):
            assert alpha == .01
            return {name: [np.array([False]) for _ in records] for name in ("V2", "CD")}

    class FakeGenerator:
        mean_ = std_ = ac_scale_ = np.ones(3)
        current_residual_scale_ = 1.

        def fit(self, records):
            calls.append(("generator_fit", identifiers(records)))
            return self

    def fake_stress(suite, generator, records, phase, output, alphas):
        calls.append(("stress", identifiers(records)))
        return pd.DataFrame([
            dict(model="V2", kind="offset", normal_record_fpr=.5),
            dict(model="CD", kind="offset", normal_record_fpr=.5 if all_fail else .01),
        ])

    def fake_injections(suite, generator, records, seeds, phase, output, offset):
        calls.append(("injection", identifiers(records)))
        assert offset == 240
        assert tuple(seeds) == (101,)
        return pd.DataFrame([dict(model=model, family=family, detection_rate=rate)
                             for model, rate in (("V2", .99), ("CD", .4))
                             for family in runner.FAMILIES])

    monkeypatch.setattr(runner, "FrontierSuite", FakeSuite)
    monkeypatch.setattr(runner, "CausalGenerator", FakeGenerator)
    monkeypatch.setattr(runner, "stress_experiment", fake_stress)
    monkeypatch.setattr(runner, "injection_experiment", fake_injections)
    monkeypatch.setattr(runner, "locked_sources", lambda: {"model.py": "original"})
    lock = runner.develop(normal, {"kind": "normal"}, tmp_path)
    assert lock["selected"] == (None if all_fail else "CD")
    assert lock["normal_only_selection"] and not lock["abnormal_file_read"]
    for operation, observed in calls:
        expected = range(0, 120) if operation in ("fit", "generator_fit") else (
            range(120, 240) if operation == "cal" else range(240, 300))
        assert observed == list(expected), operation
    runner.verify_lock(tmp_path / "selection_lock.json")
