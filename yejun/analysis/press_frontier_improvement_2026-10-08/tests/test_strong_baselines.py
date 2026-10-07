"""Check historical model identity, causal boundaries and paired block inference."""
import ast
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import Ridge
from sklearn.neighbors import NearestNeighbors

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_strong_baselines as A


def records(seed=202, count=16):
    rng = np.random.default_rng(seed)
    result = []
    for length in rng.integers(16, 28, count):
        values = rng.normal(size=(length, 3)) * [.002, .003, 8.]
        values[:, 2] += 40 * np.sin(np.arange(length)*.39+rng.uniform(-1, 1))
        step = np.array([1e-4, 1e-4, 1.1920929])
        result.append(np.round(values/step)*step)
    return result


@pytest.fixture(scope="module")
def models():
    train = records()
    frame, _ = A.as_frame(train)
    guard = A.guard.GuardModel.fit(frame, frame)
    return train, guard, A.FeatureMatchedKNN(guard).fit(train), A.HistoricalRidge(guard.mean, guard.scale).fit(train)


def historical_class(filename, classname):
    candidates = [A.ROOT / "claude/code/press/tvt" / filename, A.ROOT / "code/press/tvt" / filename]
    path = next((path for path in candidates if path.is_file()), None)
    assert path is not None, f"Historical definition missing: {filename}"
    parsed = ast.parse(path.read_text(encoding="utf-8-sig"))
    declaration = next(node for node in parsed.body if isinstance(node, ast.ClassDef) and node.name == classname)
    # Load the original class definition only; no old script side effects,
    # automatic output writes or import-time experiments are executed.
    namespace = dict(np=np, pd=pd, Ridge=Ridge, NearestNeighbors=NearestNeighbors,
                     IsolationForest=IsolationForest, RIDGE_ALPHAS=A.RIDGE_ALPHAS, LAGS=5)
    exec(compile(ast.Module(body=[declaration], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[classname]


def test_knn_preserves_original_five_feature_baseline(models):
    train, model, knn, _ = models
    frame, segment = A.as_frame(train)
    reference = historical_class("15_record_auroc_featbase.py", "FeatBase")({"D": A.D, "guard": A.guard}, model, frame, segment)
    unseen = records(203, 5) + [np.array([[.001, -.003, 5.]])]
    test, seg = A.as_frame(unseen)
    expected = reference.scores(test, seg)["knn5_feat"]
    np.testing.assert_allclose(np.concatenate(knn.score(unseen)), expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(knn.median_, reference.med)
    np.testing.assert_array_equal(knn.mean_, reference.mu)
    np.testing.assert_array_equal(knn.scale_, reference.sd)
    assert knn.neighbors_.n_features_in_ == 5


def test_ridge_preserves_original_internal_tuning_and_three_output_score(models):
    train, model, _, ridge = models
    frame, segment = A.as_frame(train)
    reference = historical_class("14_baseline_injection_ridge.py", "RidgeForecast")(model.mean, model.scale).fit(frame, segment, A.D)
    unseen = records(203, 5) + [np.array([[.001, -.003, 5.]])]
    test, seg = A.as_frame(unseen)
    np.testing.assert_allclose(np.concatenate(ridge.score(unseen)), reference.score(test, seg, A.D),
                               rtol=1e-12, atol=1e-12, equal_nan=True)
    assert ridge.alpha_ == reference.alpha
    np.testing.assert_allclose(list(ridge.validation_mse_.values()), list(reference.val_mse.values()), rtol=1e-12, atol=1e-12)
    assert ridge.models_[5].coef_.shape == (3, 15)


@pytest.mark.parametrize("model_index", [2, 3])
def test_comparator_scores_are_causal_and_do_not_cross_records(models, model_index):
    model = models[model_index]
    original = records(204, 3)
    changed = [r.copy() for r in original]
    cut = 9
    changed[0][cut:] += [100, -200, 5000]
    before, after = model.score(original), model.score(changed)
    np.testing.assert_allclose(before[0][:cut], after[0][:cut], rtol=1e-12, atol=1e-12, equal_nan=True)
    for index in (1, 2):
        np.testing.assert_array_equal(before[index], after[index])
    separate = model.score([original[1]])[0]
    np.testing.assert_allclose(separate, before[1], rtol=1e-12, atol=1e-12, equal_nan=True)


def test_early_rows_and_short_records_stay_in_denominators(models):
    _, _, knn, ridge = models
    short = [np.array([[0., 0., 20.]])]
    assert np.isfinite(knn.score(short)[0][0])
    assert np.isnan(ridge.score(short)[0][0])
    output = A.metrics([np.array([False])], [np.array([False])], ridge.score(short), ridge.score(short))
    assert output["normal_rows"] == output["abnormal_rows"] == 1
    assert output["fn"] == output["missed_records"] == output["abnormal_unscored_rows"] == 1
    assert output["row_f1"] == 0


def test_bootstrap_pairs_models_and_retains_variable_record_lengths():
    normals = [np.array([False]*length) for length in [1, 10, 4, 6]]
    abnormal = [np.array([True]*length) for length in [1, 2, 12]]
    settings = dict(seed=18, repetitions=400, normal_block_records=3, abnormal_block_records=2,
                    pairs=[["first", "same"], ["first", "miss"]])
    outputs = A.paired_bootstrap({"first": normals, "same": normals, "miss": normals},
                                {"first": abnormal, "same": abnormal,
                                 "miss": [np.zeros(len(x), bool) for x in abnormal]}, settings)
    identical, different = outputs
    assert identical["f1_difference"] == identical["ci95_low"] == identical["ci95_high"] == 0
    assert identical["includes_zero"] is True
    assert different["f1_difference"] == different["ci95_low"] == different["ci95_high"] == 1
    assert all(row["changed_selection"] is False for row in outputs)


def test_block_indices_preserve_within_block_order():
    sampled = A.circular_blocks(np.random.default_rng(17), count=11, length=3, repetitions=20)
    assert sampled.shape == (20, 11)
    assert ((sampled >= 0) & (sampled < 11)).all()
    for start in (0, 3, 6):
        np.testing.assert_array_equal((sampled[:, start+1] - sampled[:, start]) % 11, np.ones(20))
        np.testing.assert_array_equal((sampled[:, start+2] - sampled[:, start+1]) % 11, np.ones(20))


def test_fit_only_feature_statistics_do_not_change_on_new_inputs(models):
    _, _, knn, ridge = models
    before = A.canonical_hash(dict(knn=knn.metadata(), ridge=ridge.metadata()))
    extreme = [r+np.array([10., -20., 10000.]) for r in records(205, 2)]
    knn.score(extreme)
    ridge.score(extreme)
    after = A.canonical_hash(dict(knn=knn.metadata(), ridge=ridge.metadata()))
    assert before == after


def test_protocol_disallows_selection_changes_and_requires_source_identity(tmp_path, monkeypatch):
    parent = {"selected": A.SELECTED, "lock_sha256": "test-parent"}
    monkeypatch.setattr(A, "verify_lock", lambda _: parent)
    monkeypatch.setattr(A, "locked_sources", lambda: {"test/source.py": "fixed"})
    destination = tmp_path / "committed"
    protocol = A.prepare(destination, tmp_path)
    assert protocol["model_or_rule_selection_allowed"] is False
    assert protocol["selectable_new_models"] == []
    assert A.verify_protocol(destination, tmp_path)["protocol_sha256"] == protocol["protocol_sha256"]
    monkeypatch.setattr(A, "locked_sources", lambda: {"test/source.py": "changed"})
    with pytest.raises(ValueError, match="implementation changed"):
        A.verify_protocol(destination, tmp_path)
