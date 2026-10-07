"""Behavioral contracts of the causal standalone vibration branch."""
from pathlib import Path
import sys

import joblib
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vibration_branch import VibrationBranch


def records(seed=11, count=10):
    rng = np.random.default_rng(seed)
    output = []
    for n in rng.integers(9, 31, count):
        x = rng.normal(size=(n, 3))
        for t in range(1, n):
            x[t] += 0.6 * x[t - 1]
        output.append(x)
    return output


@pytest.mark.parametrize("kind", ["ridge", "difference_ridge"])
@pytest.mark.parametrize("smooth", [1, 3])
def test_prefix_and_future_suffix_invariance(kind, smooth):
    model = VibrationBranch(kind, smooth).fit(records())
    x = records(19, 1)[0]
    expected = model.score([x])[0]
    for n in range(1, len(x) + 1):
        prefix = model.score([x[:n]])[0]
        np.testing.assert_allclose(prefix, expected[:n], rtol=1e-10, atol=1e-10)
    changed = x.copy()
    changed[8:] += np.array([500.0, -250.0, 1000.0])
    np.testing.assert_allclose(model.score([changed])[0][:8], expected[:8])


@pytest.mark.parametrize("smooth", [1, 3])
def test_difference_branch_record_offset_invariance(smooth):
    train, evaluate = records(), records(23)
    offsets = [np.array([30.0 + i, -22.0 - i, 1000.0 * i]) for i in range(len(train))]
    model = VibrationBranch("difference_ridge", smooth).fit(train)
    shifted_model = VibrationBranch("difference_ridge", smooth).fit(
        [x + shift for x, shift in zip(train, offsets)])
    expected = model.score(evaluate)
    shifted = [x + shift for x, shift in zip(evaluate, offsets)]
    for a, b, c in zip(expected, model.score(shifted), shifted_model.score(shifted)):
        np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-9)
        np.testing.assert_allclose(a, c, rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize("kind", ["ridge", "difference_ridge"])
@pytest.mark.parametrize("smooth", [1, 3])
def test_records_independent_unavailable_rows_and_no_input_mutation(kind, smooth):
    train, evaluate = records(), records(31)
    train_before = [x.copy() for x in train]
    evaluate_before = [x.copy() for x in evaluate]
    model = VibrationBranch(kind, smooth).fit(train)
    batch = model.score(evaluate)
    first_available = 1 + int(kind == "difference_ridge") + smooth - 1
    for x, score in zip(evaluate, batch):
        np.testing.assert_allclose(score, model.score([x])[0])
        assert np.isnan(score[:first_available]).all()
        assert np.isfinite(score[first_available:]).all()
        assert (score[first_available:] >= 0).all()
    for a, b in zip(train + evaluate, train_before + evaluate_before):
        np.testing.assert_array_equal(a, b)
    short = model.score([np.empty((0, 3)), evaluate[0][:1]])
    assert short[0].shape == (0,)
    assert np.isnan(short[1]).all()


def test_serialization_preserves_predictions_and_constant_channels(tmp_path):
    train = records()
    for x in train:
        x[:, 2] = 17.0
    model = VibrationBranch("difference_ridge", 3).fit(train)
    path = tmp_path / "vibration.joblib"
    joblib.dump(model, path)
    restored = joblib.load(path)
    evaluate = records(53)
    for a, b in zip(model.score(evaluate), restored.score(evaluate)):
        np.testing.assert_array_equal(a, b)
    assert restored.metadata() == model.metadata()


def test_rejects_unsupported_or_nonfinite_inputs():
    with pytest.raises(ValueError):
        VibrationBranch("unknown")
    with pytest.raises(ValueError):
        VibrationBranch(smooth=2)
    with pytest.raises(ValueError):
        VibrationBranch().score(records())
    with pytest.raises(ValueError):
        VibrationBranch().fit([np.empty((0, 3))])
    with pytest.raises(ValueError):
        VibrationBranch().fit([np.zeros((10, 2))])
    with pytest.raises(ValueError):
        VibrationBranch().fit([np.full((10, 3), np.nan)])
