"""Regression and counterexample tests for newly implemented contracts."""
import copy
import itertools
import pickle
from dataclasses import replace

import pytest
from common import (core, np, pd, load_press, policy, rank, interval_metrics, metrics,
                    event_response, HERE, MASTER, canonical_sha, import_file)
from press import ParentKNN, fit_candidates, crop_children
from diagnostics import logistic_head
from heldout import phase_change, off_tone
import skab


@pytest.fixture(scope="module")
def setup():
    normal, _ = load_press()
    roles = core.split_records(normal, "P0")
    f, cal, ev = [core.features(roles[r]) for r in ["fit", "cal", "evaluation"]]
    models, _, _ = fit_candidates(roles["fit"], cal, "P0", augment=False)
    return roles, f, cal, ev, models


def test_existing_18_core_contracts_with_only_data_path_adapter():
    module = import_file("original_contract_tests", HERE.parent / "press_master_validation_2026-10-03/test_contracts.py")
    module.load_records = load_press
    import unittest
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.Contracts)
    result = unittest.TestResult()
    suite.run(result)
    assert result.wasSuccessful(), result.errors + result.failures
    assert result.testsRun == 18


def test_rank_ties_and_insufficient_reference():
    p, valid = rank([3., 4., np.nan], [1., 2., 3.], .25)
    np.testing.assert_array_equal(p[:2], [.5, .25])
    assert valid.tolist() == [True, True, False]
    assert not rank([100], [1, 2, 3], .05)[1][0]


def test_f1_label_bounds_by_exhaustive_assignments():
    for prediction in itertools.product([0, 1], repeat=4):
        lower, upper = np.array([0, 1, 0, 0]), np.array([0, 1, 1, 1])
        values = [metrics([0, 1, a, b], prediction)["f1"] for a, b in itertools.product([0, 1], repeat=2)]
        bounds = interval_metrics(lower, upper, prediction)
        assert bounds["f1_low"] == min(values)
        assert bounds["f1_high"] == max(values)


@pytest.mark.parametrize("name,expected", [("I0", [0, 5]), ("P23", [1, 6])])
def test_policy_state_sequence(name, expected):
    p = policy(np.arange(8)*5., [1, 1, 0, 0, 0, 1, 1, 0], name=name)
    assert p["starts"].tolist() == expected
    assert p["intervals"][-1][1] == 35


def test_policy_gap_boundary_quality_and_ticket_union():
    assert policy([0, 30], [1, 1], name="P23")["starts"].tolist() == [1]
    assert policy([0, 30.01], [1, 1], name="P23")["starts"].tolist() == []
    p = policy([0, 10, 15], [1, 0, 1], [1, 0, 1], [1, 0, 0])
    assert p["total_tickets"] == 3
    assert p["quality_tickets"] == 2
    assert p["intervals"][0] == (0., 10., "closed_unknown")
    assert policy([0, 50], [1, 0])["occupancy_s"] == 30


def test_delayed_completed_block_is_not_in_event_hit():
    p = policy([19, 39], [0, 1])
    r = event_response(p, [19, 39], 20, 25, 39)
    assert not r["detected"] and r["late_detection"]


def test_k1_exact_fallback_after_current_is_invalidated(setup):
    roles, _, _, _, models = setup
    changed = [replace(r, x=np.column_stack([r.x[:, :2], np.repeat(r.x[:, 2].mean(), len(r.x))])) for r in roles["evaluation"]]
    f = core.features(changed)
    a, b = models["B1"].predict(f), models["K1"].predict(f)
    assert not b["gate"].any()
    for key in ["score", "p", "bit"]:
        np.testing.assert_array_equal(a[key], b[key])


def test_k1_small_conditional_cal_uses_baseline(setup):
    _, _, _, ev, models = setup
    model = copy.deepcopy(models["K1"])
    model.conditional_reference = model.conditional_reference[:38]
    np.testing.assert_array_equal(model.predict(ev)["p"], models["B1"].predict(ev)["p"])


def test_parent_knn_copies_and_self_children_do_not_change_score(setup):
    _, f, _, ev, _ = setup
    model = ParentKNN(f)
    repeated = ParentKNN(f, pd.concat([f]*3, ignore_index=True))
    np.testing.assert_array_equal(model.score(ev), repeated.score(ev))
    target = f.iloc[[0]]
    children = f.iloc[[0]].copy()
    children.loc[:, "v0_rms"] = children.v0_rms*20
    with_child = ParentKNN(f, children)
    np.testing.assert_array_equal(model.score(target), with_child.score(target))


def test_crop_nested_allocations_and_synchronous_samples(setup):
    roles, _, _, _, _ = setup
    for seed in [11, 29, 47]:
        small, sl, sa = crop_children(roles["fit"], "P0", .5, seed)
        large, ll, la = crop_children(roles["fit"], "P0", 1., seed)
        operations = lambda links:{(l["parent_key"], l["length"], l["start"]) for l in links}
        assert operations(sl) <= operations(ll)
        assert len(operations(ll)) == len(ll)
        assert sa["generated"] + sa["failed"] == sa["target"]
        parents = {f"normal:{r.parent}":r for r in roles["fit"]}
        for child, link in zip(large, ll):
            parent = parents[link["parent_key"]]
            assert len(child.x) < len(parent.x)
            np.testing.assert_array_equal(child.x, parent.x[link["start"]:link["start"]+link["length"]])


@pytest.mark.parametrize("n", [21, 30, 41, 50])
def test_phase_rotation_odd_even_rms_and_last_bin(n):
    rng = np.random.default_rng(11)
    r = core.Record(1, rng.normal(size=(n, 3))+2, 0, 1, 2, (), "test")
    changed, audit = phase_change(r, 0, np.pi/3, 1e-6)
    assert audit["valid"] and audit["invariant"]
    np.testing.assert_array_equal(changed.x[:, 1:], r.x[:, 1:])
    ft = np.fft.rfft(r.x[:, 0]-r.x[:, 0].mean())
    new = np.fft.rfft(changed.x[:, 0]-changed.x[:, 0].mean())
    np.testing.assert_allclose(new[-1], ft[-1] if n % 2 == 0 else ft[-1]*np.exp(1j*np.pi/3), atol=1e-10)


def test_zero_injection_exact_and_seed_paired_amplitude(setup):
    r = setup[0]["evaluation"][10]
    zero, _ = off_tone(r, 0, .25, 0., 101, .1)
    np.testing.assert_array_equal(zero.x, r.x)
    one, a = off_tone(r, 0, .25, .25, 101, .1)
    two, b = off_tone(r, 0, .25, .5, 101, .1)
    assert a["phase"] == b["phase"]
    np.testing.assert_allclose(two.x-r.x, 2*(one.x-r.x), atol=1e-15)


def test_probability_constant_and_wrong_direction():
    y = np.r_[np.zeros(80), np.ones(20)]
    constant = logistic_head(np.ones(100), y, .1)
    assert constant["status"] == "uninformative"
    bad_direction = logistic_head(-y, y, .1)
    assert bad_direction["status"] == "fitted"
    assert bad_direction["a"] == 0
    assert abs(bad_direction["b"]-np.log(.1/.9)) < 1e-7


def test_skab_development_access_never_opens_test():
    access = []
    groups = skab.finalize_labels(skab.load_groups({"fit", "dev", "cal"}, access))
    assert {g["role"] for g in groups.values()} == {"fit", "dev", "cal"}
    assert all(r["role"] != "test" for r in access)
    assert sum(r["conflict"] for g in groups.values() for r in g["rows"]) == 237


def test_skab_constant_current_not_a_waveform_error():
    f = pd.DataFrame(dict(f0=np.linspace(1, 2, 40), f1=np.linspace(2, 3, 40),
                          f2=np.ones(40), f3=np.zeros(40), n=np.repeat(20, 40)))
    m = skab.Detector().fit(f)
    assert np.isfinite(m.scores(f)["G"]).all()


def test_model_reload_equal(setup):
    _, _, _, ev, models = setup
    loaded = pickle.loads(pickle.dumps(models))
    for name in models:
        for key, array in models[name].predict(ev).items():
            np.testing.assert_array_equal(array, loaded[name].predict(ev)[key])


def test_entrypoint_uses_current_verifier_not_legacy_namesake():
    module = import_file("execution_entrypoint", HERE / "run_all.py")
    assert module.verify_results.__file__ == str(HERE / "verify_results.py")
    assert callable(module.verify_results.verify)
