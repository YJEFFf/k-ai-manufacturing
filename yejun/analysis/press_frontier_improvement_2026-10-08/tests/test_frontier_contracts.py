"""Tests of the consequential selection, scoring, and calibration boundaries."""
from pathlib import Path
import sys

import joblib
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frontier_model import (FrontierSuite, PrefixReplay, as_frame, candidate_grid,
                            record_maxima)


def records(seed=81, count=10):
    rng = np.random.default_rng(seed)
    result = []
    for n in rng.integers(18, 29, size=count):
        x = rng.normal(size=(n, 3)) * [0.001, 0.002, 8.]
        x[:, 2] += 70 * np.sin(np.arange(n) * .4 + rng.uniform(0, 6))
        step = np.array([1e-4, 1e-4, 1.1920929])
        result.append(np.round(x / step) * step)
    return result


@pytest.fixture(scope="module")
def suite():
    return FrontierSuite().fit(records()).calibrate(records(82, 120))


def assert_same_scores(actual, expected, **tolerance):
    assert actual.keys() == expected.keys()
    for model in expected:
        assert len(actual[model]) == len(expected[model])
        for a, e in zip(actual[model], expected[model]):
            np.testing.assert_allclose(a, e, err_msg=model, **tolerance)


def test_declared_grid_has_48_fusions_and_11_references():
    grid = candidate_grid()
    assert len(grid) == len({s["name"] for s in grid}) == 59
    names = {s["name"] for s in grid}
    assert {"V2", "C", "W", "CD", "VR1", "VR3", "VD1", "VD3",
            "REF_PCA", "REF_VIB", "REF_AND"} <= names
    expected = {f"{c}+{v}@{w:g}" for c in ("V2", "C", "W", "CD")
                for v in ("VR1", "VR3", "VD1", "VD3") for w in (.5, 1., 2.)}
    assert {s["name"] for s in grid if s["kind"] == "fusion"} == expected
    assert all(not s["selectable"] for s in grid if s["kind"] == "reference")


def test_current_baselines_reproduce_original_guard_components(suite):
    xs = records(83, 3)
    frame, seg = as_frame(xs)
    legacy = suite.guard_.components(frame, seg)
    actual = suite.score(xs)
    np.testing.assert_allclose(np.concatenate(actual["V2"]), legacy["score"])
    np.testing.assert_allclose(np.concatenate(actual["C"]),
                               np.fmax(legacy["g_waveform"], legacy["g_dynamics"]))
    np.testing.assert_allclose(np.concatenate(actual["W"]), legacy["g_waveform"])


def test_every_candidate_is_prefix_causal_and_resets_at_record_boundaries(suite):
    xs = records(84, 2)
    before = [x.copy() for x in xs]
    expected = suite.score(xs)
    for index, x in enumerate(xs):
        single = suite.score([x])
        assert_same_scores(single, {name: [value[index]] for name, value in expected.items()})
        for cut in (1, 3, 6, 8, 10, 16):
            prefix = suite.score([x[:cut]])
            assert_same_scores(prefix, {name: [value[index][:cut]] for name, value in expected.items()},
                               atol=1e-9, rtol=1e-9)
        changed = x.copy()
        changed[12:] += [30, -50, 1e4]
        actual = suite.score([changed])
        assert_same_scores({name: [value[0][:12]] for name, value in actual.items()},
                           {name: [value[index][:12]] for name, value in expected.items()})
    for x, original in zip(xs, before):
        np.testing.assert_array_equal(x, original)


def test_dc_invariant_paths_ignore_per_record_sensor_offsets(suite):
    xs = records(85, 3)
    shifted = [x + [3 + i, -5 - i, 1000 + 100 * i] for i, x in enumerate(xs)]
    expected, actual = suite.score(xs), suite.score(shifted)
    for model in ("W", "CD", "VD1", "VD3", "CD+VD3@1", "W+VD1@0.5"):
        for a, e in zip(actual[model], expected[model]):
            np.testing.assert_allclose(a, e, rtol=1e-7, atol=1e-7, err_msg=model)


def test_unavailable_early_rows_keep_alignment_and_never_alarm(suite):
    xs = [records(86, 1)[0]]
    scores = suite.score(xs)
    alarm = suite.alarms(scores)
    starts = {"V2": 0, "C": 2, "W": 5, "CD": 3,
              "VR1": 1, "VR3": 3, "VD1": 2, "VD3": 4,
              "REF_PCA": 9, "REF_VIB": 9, "REF_AND": 9}
    for model, first in starts.items():
        assert len(scores[model][0]) == len(xs[0])
        assert np.isnan(scores[model][0][:first]).all(), model
        assert np.isfinite(scores[model][0][first:]).all(), model
        assert not alarm[model][0][:first].any(), model


@pytest.mark.parametrize("model", ["V2", "CD+VD3@1", "REF_AND"])
def test_sample_and_chunk_replay_equal_batch_and_reset(suite, model):
    xs = records(87, 2)
    batch = suite.score(xs)
    expected_alarm = suite.alarms(batch)[model]
    for chunks in ((1,), (3, 1, 7, 2), (100,)):
        replay = PrefixReplay(suite, model)
        for rec_id, (x, expected, alarm) in enumerate(zip(xs, batch[model], expected_alarm)):
            actual_scores, actual_alarms = [], []
            offset, chunk_index = 0, 0
            while offset < len(x):
                size = chunks[chunk_index % len(chunks)]
                sc, al = replay.push(x[offset:offset + size], record_id=rec_id)
                actual_scores.extend(sc)
                actual_alarms.extend(al)
                offset += size
                chunk_index += 1
            np.testing.assert_allclose(actual_scores, expected, rtol=1e-9, atol=1e-9)
            np.testing.assert_array_equal(actual_alarms, alarm)


def test_calibration_uses_record_maxima_and_cannot_refit_scores(suite):
    fresh = FrontierSuite().fit(records(88))
    evaluate = records(89, 2)
    expected = fresh.score(evaluate)
    # Exclude the memoization dictionary when comparing immutable fit state.
    fitted_objects = [fresh.guard_, fresh.vibration_, fresh.reference_,
                      fresh.diff_coef_, fresh.diff_tail_, fresh.fusion_tails_]
    frozen_hash = joblib.hash(fitted_objects)
    calibration = [evaluate[0][:1], *records(90, 4)]
    raw = fresh.score(calibration)
    fresh.calibrate(calibration)
    assert joblib.hash(fitted_objects) == frozen_hash
    assert_same_scores(fresh.score(evaluate), expected)
    for name, values in raw.items():
        np.testing.assert_array_equal(fresh.cal_[name], record_maxima(values))
        assert len(fresh.cal_[name]) == 5
    assert np.isneginf(fresh.cal_["W"][0])


def test_joint_fusion_calibration_differs_from_separate_or_budget(suite):
    xs = records(91, 2)
    scores = suite.score(xs)
    for alpha in (.005, .01, .03, .05):
        alarms = suite.alarms(scores, alpha)
        for name, values in scores.items():
            for rows, alert in zip(values, alarms[name]):
                expected = np.array([
                    np.isfinite(row) and (1 + np.count_nonzero(suite.cal_[name] >= row)) / 121 <= alpha
                    for row in rows
                ])
                np.testing.assert_array_equal(alert, expected, err_msg=name)
        for vib in ("VR1", "VR3", "VD1", "VD3"):
            for a, b, union in zip(alarms["V2"], alarms[vib], alarms[f"OR_V2_{vib}"]):
                np.testing.assert_array_equal(union, a | b)


def test_saved_suite_preserves_scores_and_calibrated_alerts(suite, tmp_path):
    artifact = tmp_path / "frontier.joblib"
    joblib.dump(suite, artifact)
    restored = joblib.load(artifact)
    xs = records(92, 2)
    expected, actual = suite.score(xs), restored.score(xs)
    assert_same_scores(actual, expected)
    expected_alarm, actual_alarm = suite.alarms(expected), restored.alarms(actual)
    for name in expected_alarm:
        for a, e in zip(actual_alarm[name], expected_alarm[name]):
            np.testing.assert_array_equal(a, e)
