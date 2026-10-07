"""Synthetic onset is an input contract, independently of model causality."""
from pathlib import Path
import sys

import joblib
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenarios import CausalGenerator, DEVELOPMENT_SEEDS, EVALUATION_SEEDS, FAMILIES


@pytest.fixture(scope="module")
def generator():
    rng = np.random.default_rng(122)
    return CausalGenerator().fit([rng.normal(size=(n, 3)) for n in (18, 21, 28, 29)])


CASES = [(family, target) for family, spec in FAMILIES.items() for target in spec["targets"]]


@pytest.mark.parametrize("family,target", CASES)
@pytest.mark.parametrize("onset", [0, 11, 24])
def test_injections_preserve_prefix_and_other_channels(generator, family, target, onset):
    x = np.random.default_rng(123).normal(size=(25, 3))
    before = x.copy()
    altered = generator.inject(x, family, target, 1., seed=101, onset=onset)
    assert altered[:onset].tobytes() == x[:onset].tobytes()
    np.testing.assert_array_equal(altered[:, [c for c in range(3) if c != target]],
                                  x[:, [c for c in range(3) if c != target]])
    np.testing.assert_array_equal(x, before)
    assert np.any(altered[onset:, target] != x[onset:, target])
    np.testing.assert_array_equal(
        altered, generator.inject(x, family, target, 1., seed=101, onset=onset))


@pytest.mark.parametrize("family,target", CASES)
def test_zero_strength_and_future_suffix_cannot_change_injected_prefix(generator, family, target):
    x = np.random.default_rng(124).normal(size=(25, 3))
    altered = generator.inject(x, family, target, 1., seed=811, onset=7)
    zero = generator.inject(x, family, target, 0., seed=811, onset=7)
    assert zero.tobytes() == x.tobytes()
    suffix = x.copy()
    suffix[15:] += 900
    future = generator.inject(suffix, family, target, 1., seed=811, onset=7)
    np.testing.assert_array_equal(future[:15], altered[:15])
    prefix = generator.inject(x[:15], family, target, 1., seed=811, onset=7)
    np.testing.assert_array_equal(prefix, altered[:15])


def test_fitted_injection_scales_never_update_during_evaluation(generator):
    before = joblib.hash(generator)
    x = np.random.default_rng(125).normal(size=(25, 3))
    for family, target in CASES:
        generator.inject(x * 1e6, family, target, 1., seed=811, onset=10)
    for spec in generator.stress_specs():
        generator.perturb([x], **spec)
    assert joblib.hash(generator) == before
    assert set(DEVELOPMENT_SEEDS).isdisjoint(EVALUATION_SEEDS)


def test_stuck_stress_preserves_samples_before_declared_failure(generator):
    x = np.random.default_rng(126).normal(size=(25, 3))
    before = x.copy()
    for target in range(3):
        result = generator.perturb([x], "stuck", target, .5)[0]
        np.testing.assert_array_equal(result[:12], x[:12])
        np.testing.assert_array_equal(result[12:, target], np.full(13, x[11, target]))
    np.testing.assert_array_equal(x, before)
