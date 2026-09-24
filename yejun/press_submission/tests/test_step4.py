"""4단계 검사: LSTM-AE 형태·축약 학습·마지막 시점 오차·캐시 키·블록 부트스트랩."""
import numpy as np
import torch

from press.lstm_ae import LSTMAE, config_key, last_step_error, train_ae
from press.uncertainty import moving_block_bootstrap


def test_lstm_shapes_and_training_runs():
    torch.manual_seed(0)
    X = np.random.default_rng(0).standard_normal((64, 20, 3)).astype(np.float32)
    m = LSTMAE()
    assert tuple(m(torch.tensor(X[:5])).shape) == (5, 20, 3)
    model, hist = train_ae(X, X[:16], epochs=3, patience=2, seed=0)
    assert len(hist) == 3 and hist.val_loss.notna().all()
    e = last_step_error(model, X)
    assert e.shape == (64,) and np.isfinite(e).all() and (e >= 0).all()
    assert len(last_step_error(model, np.empty((0, 20, 3)))) == 0


def test_training_is_deterministic():
    X = np.random.default_rng(1).standard_normal((48, 20, 3)).astype(np.float32)
    a, _ = train_ae(X, X[:8], epochs=2, patience=5, seed=3)
    b, _ = train_ae(X, X[:8], epochs=2, patience=5, seed=3)
    assert np.allclose(last_step_error(a, X), last_step_error(b, X))


def test_config_key_stable():
    assert config_key({"a": 1, "b": [1, 2]}) == config_key({"b": [1, 2], "a": 1})
    assert config_key({"a": 1}) != config_key({"a": 2})


def test_moving_block_bootstrap():
    x = np.zeros(120, int)
    c = moving_block_bootstrap(x, 10, reps=200, seed=0)
    assert len(c) == 200 and (c == 0).all()
    x[:60] = 1
    c = moving_block_bootstrap(x, 10, reps=2000, seed=0)
    assert abs(c.mean() - 60) < 5 and c.min() >= 0 and c.max() <= 120
    assert len(moving_block_bootstrap(np.array([]), 5)) == 0
