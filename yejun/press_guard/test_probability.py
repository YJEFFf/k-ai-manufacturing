"""이상 확률 층 계약: 경보와 분리, 단조성, 사전 비율 변환, 표시 범위, 교차 적합 누설 차단, 저장·복원."""
import json

import numpy as np
import pandas as pd
import pytest

from model import D, HERE, StreamDetector, load_bundle
from probability import ProbabilityCalibrator, min_rank_nominal_likelihood_ratio, posterior, sellke_bayes_factor
from train import oof_likelihood_ratio


@pytest.fixture(scope="module")
def data():
    return D.load()[:2]


@pytest.fixture(scope="module")
def bundle():
    return load_bundle(HERE / "artifacts" / "guard_B.json")


def test_probability_does_not_change_alarms(bundle, data):
    """확률 보정기를 붙여도 경보·알림·단계는 같다(경보는 conformal p값만으로 정한다)."""
    _, abnormal = data
    with_prob = bundle.predict(abnormal, .01)
    calibrator, bundle.probability = bundle.probability, None
    try:
        without = bundle.predict(abnormal, .01)
    finally:
        bundle.probability = calibrator
    for col in ("score", "p_value", "alarm", "notification", "alert_level", "escalation", "reason", "action"):
        pd.testing.assert_series_equal(with_prob[col], without[col])
    assert without.anomaly_probability.isna().all() and with_prob.anomaly_probability.notna().all()


def test_monotone_in_score_and_prior(bundle):
    cal = bundle.probability
    s = np.linspace(-2, 40, 400)
    lr = cal.likelihood_ratio(s)
    assert np.all(np.diff(lr) >= -1e-12)
    assert lr.max() <= len(bundle.cal) + 1 and lr.min() > 0      # 운영 표시 정책: 보정 단위 수 + 1에서 자른다.
    p_lo, p_hi = cal.probability(s, prior=.001), cal.probability(s, prior=.1)
    assert np.all(p_hi >= p_lo) and np.all((0 < p_lo) & (p_hi < 1))


def test_prior_conversion_formula():
    lr = np.array([.5, 1.0, 9.28, 121.0])
    for pi in (.001, .01, .1):
        p = posterior(lr, pi)
        assert np.allclose(p / (1 - p), lr * pi / (1 - pi))          # 사후 오즈 = LR × 사전 오즈
        assert np.isclose(posterior(1.0, pi), pi)
    assert np.isclose(min_rank_nominal_likelihood_ratio(120), 121)
    assert np.isclose(1 / sellke_bayes_factor(1 / 121), 9.28, atol=.01)


def test_zero_isotonic_endpoint_remains_monotone_under_interpolation():
    """P̂=0만 floor로 올리면 첫 양수로의 보간 구간에서 LR이 오히려 급락한다."""
    cal = ProbabilityCalibrator.fit([0, 1, 2, 3], [2, 3, 4], calibration_units=120)
    scores = np.linspace(0, 4, 401)
    assert np.any(cal.y == 0) and np.any(cal.y == 1)
    lr = cal.likelihood_ratio(scores)
    assert np.all(np.diff(lr) >= -1e-12)
    assert np.all((lr >= cal.lr_floor) & (lr <= cal.lr_cap))
    assert cal.probability([1.1])[0] >= cal.probability([1.0])[0]
    assert np.isnan(cal.likelihood_ratio([np.nan, np.inf, -np.inf])).all()


def test_nominal_lr_reference_is_not_a_universal_upper_bound():
    """FAR의 상한은 LR의 상한을 뜻하지 않는다. 이 수치는 관측치가 아닌 산술 반례다."""
    tpr = .955
    nominal = min_rank_nominal_likelihood_ratio(120, tpr)
    assert nominal == pytest.approx(tpr / (1 / 121))
    assert tpr / (1 / 242) > nominal


def test_out_of_fold_has_no_leakage(bundle, data):
    """평가용 이상 행 우도비는 그 기록을 뺀 보정기로만 계산한다. 대상 기록의 신호를 바꿔도 그 기록에 쓰는 보정기는 그대로이고,
    대상 기록의 값은 자기 점수가 바뀐 만큼만 바뀐다(자기 라벨·점수가 적합에 들어가지 않는다)."""
    normal, abnormal = data
    sp = D.split_normal(normal, D.segments(normal), "B")
    cal_scores = bundle.predict(sp["cal"]).score.to_numpy()
    seg = D.segments(abnormal)
    target = 11
    inside = seg == target
    pa = bundle.predict(abnormal)
    base = oof_likelihood_ratio(bundle, sp["cal"], abnormal)
    fold = ProbabilityCalibrator.fit(cal_scores, pa.score.to_numpy()[~inside], calibration_units=len(bundle.cal))
    assert np.allclose(base[inside], fold.likelihood_ratio(pa.score.to_numpy()[inside]))
    moved = abnormal.copy()
    moved.loc[np.flatnonzero(inside), D.SENSORS[0]] *= 3.0            # 대상 기록의 진동만 바꾼다
    pm = bundle.predict(moved)
    assert np.allclose(pm.score.to_numpy()[~inside], pa.score.to_numpy()[~inside], equal_nan=True)   # 다른 기록 점수는 그대로
    changed = oof_likelihood_ratio(bundle, sp["cal"], moved)
    assert np.allclose(changed[inside], fold.likelihood_ratio(pm.score.to_numpy()[inside]))          # 같은 보정기, 새 점수
    deploy = bundle.probability.likelihood_ratio(pa.score.to_numpy())
    assert np.isfinite(base).all() and not np.allclose(base, deploy)   # 평가용 값은 배포용(전체 적합)과 다르다


def test_stream_record_probability_equals_batch(bundle, data):
    normal, abnormal = data
    frame = pd.concat([normal.iloc[:120], abnormal.iloc[:180]], ignore_index=True)
    batch = bundle.predict(frame, .01)
    for chunks in ((1,), (7, 50, 3), (128,)):
        stream = StreamDetector(bundle); parts = []; i = 0; c = 0
        while i < len(frame):
            size = chunks[c % len(chunks)]; parts.append(stream.push(frame.iloc[i:i + size])); i += size; c += 1
        got = pd.concat(parts, ignore_index=True)
        for col in ("likelihood_ratio", "anomaly_probability", "record_likelihood_ratio", "record_probability", "alert_level", "escalation"):
            assert np.allclose(got[col].to_numpy(float), batch[col].to_numpy(float), equal_nan=True, rtol=1e-11, atol=1e-11), (chunks, col)
    rec = batch.groupby("record_id").record_likelihood_ratio.last()
    assert np.allclose(rec, batch.groupby("record_id").likelihood_ratio.max())   # 기록 확률 = 기록 안 최대 우도비의 확률


def test_calibrator_roundtrip_and_tamper(bundle, tmp_path):
    path = tmp_path / "p.json"
    bundle.probability.save(path)
    again = ProbabilityCalibrator.load(path)
    s = np.linspace(0, 30, 50)
    assert np.array_equal(again.likelihood_ratio(s), bundle.probability.likelihood_ratio(s))
    env = json.loads(path.read_text(encoding="utf-8")); env["state"]["lr_cap"] = 1e6
    path.write_text(json.dumps(env), encoding="utf-8")
    with pytest.raises(ValueError, match="해시"):
        ProbabilityCalibrator.load(path)
