"""Tests of consequential transfer and leakage boundaries, using synthetic fixtures."""
import numpy as np
import pytest

from basis import bands, waveform, rank_p, Neighbors, select_pool, record_max


def test_same_spectrum_path_has_same_features():
    x = np.sin(np.arange(32)*.39) + .2*np.cos(np.arange(32)*1.1)
    np.testing.assert_array_equal(waveform(x), bands(np.abs(np.fft.rfft(x-x.mean()))))


def test_amplitude_and_offset_do_not_encode_dataset_units():
    x = np.random.default_rng(4).normal(size=31)
    np.testing.assert_allclose(waveform(x), waveform(5*x+100), atol=1e-13)
    assert abs(np.square(waveform(x)).sum()-1) < 1e-12


def test_flat_and_short_signals_are_explicit():
    np.testing.assert_array_equal(waveform(np.ones(10)), np.zeros(16))
    with pytest.raises(ValueError):
        waveform(np.arange(3.))
    with pytest.raises(ValueError):
        waveform(np.array([1., 2., np.nan, 4.]))


def test_spectral_mass_never_becomes_negative():
    for n in (4, 5, 8, 16, 31, 32, 50, 1000):
        v = waveform(np.sin(np.arange(n)*.5))
        assert v.shape == (16,) and np.all(v >= 0) and np.isfinite(v).all()
        assert abs(np.square(v).sum()-1) < 1e-12


def test_calibration_ties_and_finite_resolution():
    p = rank_p(np.array([1., 2., 2.]), np.array([2., 3.]))
    np.testing.assert_array_equal(p, [.75, .25])
    with pytest.raises(ValueError):
        rank_p([1., np.nan], [2.])


def test_neighbor_repeat_control_really_deduplicates():
    x = np.arange(12.).reshape(-1, 1)
    ids = np.array([f"normal:{i}:0" for i in range(len(x))])
    a = Neighbors(x, ids)
    b = Neighbors(np.tile(x, (5, 1)), np.tile(ids, 5))
    np.testing.assert_array_equal(a.score([[3.5]]), b.score([[3.5]]))
    assert len(b.x) == 12


def test_fit_scores_exclude_both_channels_of_same_record():
    x = np.arange(12.).reshape(-1, 1)
    ids = np.array([f"press:normal:{i//2}:{i%2}" for i in range(len(x))])
    detector = Neighbors(x, ids)
    # Query 0: exclude reference 0 and 1, so nearest five are 2,3,4,5,6.
    np.testing.assert_array_equal(detector.score([[0.]], ["press:normal:0"]), [4.])


def test_source_sampling_uses_normal_labels_only_when_requested():
    pool = dict(x=np.arange(20).reshape(10, 2), normal=np.array([True]*4+[False]*6),
                groups=np.array(["a"]*2+["b"]*2+["c"]*6))
    normal = select_pool(pool, 20, 11, True)
    all_rows = select_pool(pool, 20, 11, False)
    assert set(normal) == set(range(4)) and set(all_rows) == set(range(10))
    assert len(set(all_rows)) == len(all_rows)


def test_group_sampling_balances_before_reusing_large_capture():
    pool = dict(x=np.zeros((12, 16)), normal=np.ones(12, bool), groups=np.array(["a"]*10+["b", "c"]))
    ix = select_pool(pool, 3, 47, True)
    assert set(pool["groups"][ix]) == {"a", "b", "c"}


def test_unsupported_target_record_stays_in_result():
    result = record_max(np.array([1., 3., 2., 4.]), np.array([0, 0, 2, 2]), 3)
    assert result[0] == 3 and np.isnan(result[1]) and result[2] == 4
