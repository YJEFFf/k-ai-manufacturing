"""2단계 정확성 검사: 꼬리 변환·conformal·cutoff·사인 점수·artifact 추론 일치·순서 불변."""
import numpy as np
import pandas as pd
import pytest

from press import data as D
from press.artifact import Artifact
from press.calibrate import ALPHAS, alpha_grid, conformal_p, conformal_threshold, cutoff_threshold, mc_check_conformal, segment_max
from press.scores import ExpTail, MainModel, Scorer, capped_logp, sine_score, window_index


def test_exp_tail_monotone_and_strict_above_u():
    rng = np.random.default_rng(1)
    ref = rng.gamma(2.0, 1.0, 5000)
    g = ExpTail(ref)
    assert g.ok and g.n == 5000 and g.beta > 0
    s = np.sort(rng.uniform(0, ref.max() * 3, 2000))
    v = g(s)
    assert np.all(np.diff(v) >= -1e-12)                     # 단조
    above = s > g.u
    assert np.all(np.diff(v[above]) > 0)                     # u 위에서는 서로 다른 점수에 강증가
    assert np.isfinite(g(np.array([1e9]))[0]) and np.isnan(g(np.array([np.nan]))[0])
    assert v[above][0] >= g.g_u - 1e-12                      # 접합점: g(u+) = g_emp(u)


def test_exp_tail_degenerate():
    g = ExpTail(np.ones(100))          # 초과분 없음 → 적합 불가
    assert not g.ok and np.isnan(g(np.array([2.0]))[0])
    assert not ExpTail(np.array([])).ok


def test_exp_tail_state_roundtrip():
    ref = np.random.default_rng(2).standard_normal(500)
    g = ExpTail(ref)
    h = ExpTail.from_state(g.state())
    s = np.linspace(-3, 6, 50)
    assert np.allclose(g(s), h(s))


def test_conformal_threshold_equals_p_rule():
    rng = np.random.default_rng(3)
    cal = np.round(rng.standard_normal(120), 1)               # 동점 포함
    s = np.round(rng.standard_normal(5000) * 1.5, 1)
    p = conformal_p(cal, s)
    for a in ALPHAS:
        thr, k = conformal_threshold(cal, a)
        assert np.array_equal(p <= a, s > thr)
        assert alpha_grid(a, 120) == np.floor(a * 121) / 121
    thr, k = conformal_threshold(cal, 0.005)
    assert k < 0 and thr == np.inf                            # n=120에서 0.5%는 경보 불가


def test_cutoff_matches_vendor():
    vendor = D.load_vendor()
    cal = np.random.default_rng(4).standard_normal(120)
    for b in ALPHAS:
        assert cutoff_threshold(cal, b)[0] == vendor.cutoff_at_budget(cal, b)


def test_mc_conformal():
    for m in mc_check_conformal(reps=5000, seed=5):
        assert abs(m["realized"] - m["alpha_grid"]) <= 4 * m["mc_se"]


def test_sine_score_window_rules():
    seg = np.r_[np.zeros(10, int), np.ones(6, int)]
    t = np.arange(16) * D.DT
    x = np.sin(2 * np.pi * 0.6 * t)
    x[10:] = 3.0                                             # 두 번째 구간은 상수 → SST=0
    s = sine_score(x, seg, 8)
    assert np.isnan(s[:7]).all() and np.isfinite(s[7:10]).all() and s[7:10].max() < 1e-9
    assert np.isnan(s[10:]).all()                            # 창이 안 찬 행 + 상수 창
    assert list(window_index(seg, 8)) == [7, 8, 9]
    assert np.allclose(capped_logp(np.arange(9.0), np.array([9.5, -1.0])), [1.0, -np.log10(1.0)])


@pytest.fixture(scope="module")
def fitted():
    normal, abnormal, report = D.load(D.PACKAGE_DIR, verify=True)
    seg_n = D.segments(normal)
    sp = D.split_normal(normal, seg_n, "A")
    vendor = D.load_vendor()
    train = D.quantize(sp["train"], "matched")
    scorer = Scorer(train, D.segments(train), vendor, wins=(8,), baselines=False)
    return scorer, D.quantize(sp["cal"], "matched"), D.quantize(sp["test"], "matched"), D.quantize(abnormal, "matched"), report


def test_main_model_matches_scorer_and_is_order_invariant(fitted, tmp_path):
    scorer, cal, test, abn, report = fitted
    st = scorer.main_state(8)
    cal_seg = segment_max(scorer.score(cal, D.segments(cal))[0]["combined_w8"], D.segments(cal))
    st["calibration"] = {"unit": "recording_segments", "segment_max": cal_seg, "n": len(cal_seg), "thresholds": []}
    st["preprocess_spec"] = D.QUANTIZATION["matched"]
    art = Artifact(model_id="t", split="A", preprocess="matched", w=8, input_sha256={}, state=st)
    mm = MainModel(Artifact.load(art.save(tmp_path / "m.json")).state)
    stream = pd.concat([D.inputs_only(test), D.inputs_only(abn)], ignore_index=True)
    seg = D.segments(stream)
    ref = np.r_[scorer.score(test, D.segments(test))[0]["combined_w8"], scorer.score(abn, D.segments(abn))[0]["combined_w8"]]
    got = mm.score(stream, seg)["combined"]
    assert np.allclose(got, ref, equal_nan=True)
    rng = np.random.default_rng(0)
    order = rng.permutation(np.unique(seg))
    perm = np.concatenate([np.flatnonzero(seg == u) for u in order])
    shuf = stream.iloc[perm].reset_index(drop=True)
    back = np.empty_like(perm); back[perm] = np.arange(len(perm))
    assert np.allclose(mm.score(shuf, D.segments(shuf))["combined"][back], got, equal_nan=True)
    # 미래값 불변: 뒤에 행을 덧붙여도 앞 예측은 같다
    longer = pd.concat([stream, stream.tail(30)], ignore_index=True)
    assert np.allclose(mm.score(longer, D.segments(longer))["combined"][:len(stream)], got, equal_nan=True)
