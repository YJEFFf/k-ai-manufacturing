"""Causality and sensor-scope contracts for the independently built comparator."""
from pathlib import Path
import sys

import joblib
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from competitor_reference import CompetitorReference, record_features


def records(seed=14, count=12):
    rng = np.random.default_rng(seed)
    return [rng.normal(size=(int(n), 3))
            for n in rng.integers(15, 32, size=count)]


@pytest.fixture(scope="module")
def fitted():
    return CompetitorReference().fit(records())


def test_feature_semantics_on_known_window():
    # Three equal ramps have variance 8.25, centered lag products 77/12
    # and 17/4, and one crossing over nine consecutive pairs.
    ramp = np.arange(10, dtype=float)
    x = np.column_stack([ramp, ramp, ramp])
    f = record_features(x)[0]
    np.testing.assert_allclose(f[:3], np.sqrt(8.25))
    np.testing.assert_array_equal(f[3:6], [9., 9., 9.])
    np.testing.assert_allclose(f[6:9], np.sqrt(28.5))
    np.testing.assert_allclose(f[9:12], (77 / 12) / 8.25)
    np.testing.assert_allclose(f[12:15], (17 / 4) / 8.25)
    np.testing.assert_allclose(f[15:18], 1 / 9)
    np.testing.assert_allclose(f[18:], [1, 1, 1, 4.5, 4.5])


@pytest.mark.parametrize("component", ["stage1", "stage2", "and"])
def test_all_prefixes_and_future_changes_preserve_scores(fitted, component):
    x = records(18, 1)[0]
    expected = fitted.score([x], component)[0]
    for size in range(len(x) + 1):
        actual = fitted.score([x[:size]], component)[0]
        np.testing.assert_allclose(actual, expected[:size], rtol=1e-10, atol=1e-10)
    changed = x.copy()
    changed[15:] = 1000
    np.testing.assert_allclose(fitted.score([changed], component)[0][:15], expected[:15])


def test_record_boundaries_and_unscored_rows_are_preserved(fitted):
    xs = [np.empty((0, 3)), *[np.ones((n, 3)) for n in (1, 9)], *records(25)]
    before = [x.copy() for x in xs]
    batches = fitted.score_parts(xs)
    for component, batch in batches.items():
        assert len(batch) == len(xs)
        for x, result in zip(xs, batch):
            assert result.shape == (len(x),)
            assert np.isnan(result[:9]).all()
            assert np.isfinite(result[9:]).all()
            np.testing.assert_allclose(result, fitted.score([x], component)[0])
    for x, original in zip(xs, before):
        np.testing.assert_array_equal(x, original)


def test_vibration_comparator_ignores_current_in_fit_and_score():
    train, evaluate = records(), records(26)
    altered_train = [x.copy() for x in train]
    altered_evaluate = [x.copy() for x in evaluate]
    rng = np.random.default_rng(78)
    for x in altered_train + altered_evaluate:
        x[:, 2] = rng.normal(2000, 150, size=len(x))
    baseline = CompetitorReference().fit(train)
    altered = CompetitorReference().fit(altered_train)
    expected = baseline.score(evaluate, "stage2")
    for original, scored, retrained in zip(
        expected, baseline.score(altered_evaluate, "stage2"),
        altered.score(altered_evaluate, "stage2"),
    ):
        np.testing.assert_allclose(original, scored, rtol=1e-10, atol=1e-10)
        np.testing.assert_allclose(original, retrained, rtol=1e-10, atol=1e-10)


def test_evaluation_never_updates_fitted_statistics(fitted):
    before = joblib.hash(fitted)
    fitted.score_parts([x * 1e5 + 1e6 for x in records(31)])
    assert joblib.hash(fitted) == before


def test_feature_and_training_domains_reject_unusable_data():
    model = CompetitorReference()
    assert len(model.feature_schema) == 23
    assert len(model.vibration_feature_schema) == 15
    assert all("current" not in name for name in model.vibration_feature_schema)
    with pytest.raises(ValueError):
        model.fit([np.zeros((9, 3))])
    with pytest.raises(ValueError):
        model.fit([np.ones((30, 3))])
    with pytest.raises(ValueError):
        record_features(np.full((10, 3), np.nan))
