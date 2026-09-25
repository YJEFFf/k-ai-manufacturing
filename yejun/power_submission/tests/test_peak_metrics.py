"""피크·경보·지표 함수의 합성 자료 검사."""
from __future__ import annotations

import numpy as np
import pandas as pd

from powerguard import metrics as MT
from powerguard import peak as PK
from powerguard import stage_field as SF


def _series(values, start="2021-08-02"):
    idx = pd.date_range(start, periods=len(values), freq="15min")
    return pd.Series(np.asarray(values, float), index=idx)


def test_events_merge_gap_and_usable_break():
    y = _series([100, 190, 100, 190, 190, 100, 100, 190])
    usable = np.ones(len(y), bool)
    ev = PK.events(y, usable, 180, merge_gap=1)
    assert list(zip(ev["start"], ev["end"])) == [(1, 4), (7, 7)]
    usable[2] = False  # 사용 불가 구간은 병합하지 않는다
    ev2 = PK.events(y, usable, 180, merge_gap=1)
    assert list(zip(ev2["start"], ev2["end"])) == [(1, 1), (3, 4), (7, 7)]


def test_next_hour_labels_require_all_four_future_intervals():
    y = _series([10, 20, 30, 40, 50, 60])
    usable = np.array([True, True, True, False, True, True])
    lab = PK.next_hour_labels(y, usable)
    assert not lab["valid"].iloc[0]          # 미래 네 구간 중 하나(3번)가 사용 불가
    assert not lab["valid"].iloc[2]          # 끝부분은 네 구간이 없다
    assert lab["valid"].sum() == 0


def test_evaluate_alarms_event_detection_and_lead():
    y = _series([100] * 10 + [190, 190] + [100] * 10)
    usable = np.ones(len(y), bool)
    labels = PK.next_hour_labels(y, usable)
    prob = pd.Series(0.0, index=y.index)
    prob.iloc[7] = 0.9   # 사건 시작 구간 10의 3구간 전 발행 → 선행 30분
    r = PK.evaluate_alarms(prob, labels, y, usable, 180, 0.5, np.ones(len(y), bool))
    assert r["events"] == 1 and r["events_detected"] == 1 and r["lead_median_min"] == 30
    assert r["alarm_episodes"] == 1 and r["false_episodes"] == 0


def test_classification_and_best_threshold():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.4, 0.6, 0.9])
    c = MT.classification(y, p, 0.5)
    assert c["TP"] == 2 and c["FP"] == 0 and c["F1"] == 1.0
    t, f = MT.best_f1_threshold(y, p)
    assert f == 1.0 and 0.4 < t <= 0.6  # 동률이면 높은 문턱(경보가 적은 쪽)


def test_paired_bootstrap_sign():
    idx = pd.date_range("2021-08-01", periods=96 * 10, freq="15min")
    rng = np.random.default_rng(0)
    y = pd.Series(rng.normal(100, 10, len(idx)), index=idx)
    good = y + rng.normal(0, 1, len(idx))
    bad = y + rng.normal(0, 5, len(idx))
    r = MT.paired_day_bootstrap(y, good, bad, np.ones(len(idx), bool), n_boot=300)
    assert r["diff"] < 0 and r["ci90"][1] < 0


def test_demand_controller_simulation_conserves_energy():
    y = np.array([100, 100, 200, 200, 100, 100, 100, 100, 100.0])
    alarm = np.array([False, True, True, True, False, False, False, False, False])
    y2, info = SF.simulate(y, alarm, 0.1)
    # 첫 경보만 차단(2구간), 이후 4구간 회복 동안 추가 경보 무시
    assert info["episodes"] == 1 and info["shed_intervals"] == 2
    assert np.isclose(y2.sum(), y.sum())
    assert y2[2] == 180 and y2[3] == 180 and np.allclose(y2[4:8], 110)
    valley = np.array([False] * 6 + [True, True, True])
    y3, info3 = SF.simulate(y, alarm, 0.1, valley)  # 저부하 구간(6~8)으로 회복
    assert np.isclose(y3.sum(), y.sum()) and np.allclose(y3[6:9], 100 + 40 / 3) and info3["payback_to_valley_share"] == 1


def test_rolling_intervals_use_only_past_days():
    idx = pd.date_range("2021-08-01", periods=96 * 30, freq="15min")
    rng = np.random.default_rng(1)
    y = pd.Series(rng.normal(0, 1, len(idx)), index=idx)
    pred = pd.Series(0.0, index=idx)
    kb = pd.Timedelta(hours=7)
    base = PK.rolling_intervals(y, pred, np.zeros(len(idx), int), 0.2, known_before=kb)
    y2 = y.copy()
    y2.loc["2021-08-20 17:00":] = 1000.0  # D-1 17:00 이후 값을 바꿔도 D(8/21) 이전 날의 구간은 그대로여야 한다
    alt = PK.rolling_intervals(y2, pred, np.zeros(len(idx), int), 0.2, known_before=kb)
    m = idx < pd.Timestamp("2021-08-21")
    pd.testing.assert_frame_equal(base[m], alt[m])
    # 8/21 구간은 8/20 17:00 전에 끝난 잔차만 쓰므로 역시 그대로
    m2 = (idx >= pd.Timestamp("2021-08-21")) & (idx < pd.Timestamp("2021-08-22"))
    pd.testing.assert_frame_equal(base[m2], alt[m2])


def test_next_hour_prob_uses_only_completed_residual_vectors():
    idx = pd.date_range("2021-08-01", periods=96 * 25, freq="15min")
    rng = np.random.default_rng(2)
    y = pd.Series(rng.normal(150, 10, len(idx)), index=idx)
    preds = {h: pd.Series(150.0, index=idx) for h in range(1, 5)}
    g = np.zeros(len(idx), int)
    p1 = PK.next_hour_prob(idx, preds, y, 170, g)
    y2 = y.copy()
    y2.loc["2021-08-20 00:15":] = 5000.0  # 8/20 첫 발행(00:15) 이후 목표를 바꿔도 8/20 확률은 그대로
    p2 = PK.next_hour_prob(idx, preds, y2, 170, g)
    m = idx < pd.Timestamp("2021-08-21")
    pd.testing.assert_series_equal(p1[m], p2[m])


def test_persistence_fallback_never_nan():
    from powerguard import models as M
    X = pd.DataFrame({f"lag_{k}": [np.nan, 5.0] for k in range(8)})
    X["lag_3"] = [7.0, 5.0]
    X["same_dt_last"] = [9.0, 9.0]
    p = M.Persistence().fit(X, np.array([1.0, 2.0])).predict(X)
    assert p[0] == 7.0 and p[1] == 5.0
