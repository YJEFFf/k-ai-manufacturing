"""Finite-sample alert-budget contracts of the reused conformal calibration."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "press_submission"))
from press.calibrate import conformal_p, conformal_threshold, segment_max


@pytest.mark.parametrize("alpha", [0.005, 0.01, 0.03, 0.05])
def test_record_budget_uses_exact_conformal_rank_and_conservative_ties(alpha):
    maxima = np.repeat(np.arange(40, dtype=float), 3)
    values = np.array([-1., 0., 1., 36., 37., 38., 39., 40., np.nan])
    expected = np.array([
        (1 + np.count_nonzero(maxima >= score)) / 121
        if np.isfinite(score) else np.nan for score in values
    ])
    actual = conformal_p(maxima, values)
    np.testing.assert_array_equal(actual, expected)
    threshold, _ = conformal_threshold(maxima, alpha)
    np.testing.assert_array_equal(actual <= alpha, values > threshold)
    if alpha == 0.005:
        assert np.isposinf(threshold)
        assert not (actual <= alpha).any()
    if alpha == 0.01:
        assert threshold == 39
        assert actual[-2] == 1 / 121
        assert actual[-3] > alpha  # A score tied with the largest calibration record.


def test_long_records_cannot_receive_extra_calibration_weight():
    scores = np.array([2., np.nan, 1., 4., np.nan, np.nan])
    segments = np.array([0, 0, 0, 1, 2, 2])
    expected = np.array([2., 4., -np.inf])
    np.testing.assert_array_equal(segment_max(scores, segments), expected)
    repeated = segment_max(np.repeat(scores, 8), np.repeat(segments, 8))
    np.testing.assert_array_equal(repeated, expected)
    # The record without a score remains one calibration unit, and a row
    # without a score cannot produce an alarm at any declared operating point.
    p = conformal_p(repeated, np.array([5., np.nan]))
    assert p[0] == 1 / 4
    assert np.isnan(p[1])
