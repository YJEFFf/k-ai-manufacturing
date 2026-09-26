"""데이터 진단 사실(PLAN §2)이 코드 결과와 일치하는지 확인."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from powerguard import config as C
from powerguard import data as D


@pytest.fixture(scope="module")
def dg():
    df, meta = D.load_raw()
    return df, meta, D.diagnose(df)


def test_hash_and_shape(dg):
    df, meta, _ = dg
    assert meta["sha256"] == C.CSV_SHA256
    assert df.shape[0] == 6168


def test_leaky_columns(dg):
    _, _, d = dg
    s = d.summary
    assert s["평균_equals_round_half_up_mean"] == 6168
    assert s["공장인원_equals_prod_div_power_sum"] == s["공장인원_nonnull"] == 6151


def test_copies(dg):
    _, _, d = dg
    s = d.summary
    assert s["unique_daily_power_patterns"] == 142
    assert s["copied_power_days"] == 115
    assert s["hour_copy_placebo_matches"] == "0/3885"
    assert s["partial_copy_days"] == ["2021-01-01", "2021-01-09", "2021-01-10", "2021-01-16",
                                      "2021-03-07", "2021-03-21", "2021-03-28"]
    con = set(pd.to_datetime(d.contradictions["date"]).dt.strftime("%Y-%m-%d"))
    # 설·삼일절·일요일인데 평일 가동 전력(v1에서 찾은 모순)은 모두 복제일 쪽에 있다
    assert {"2021-02-11", "2021-03-01", "2021-03-14", "2021-05-09"} <= con
    assert all(pd.Timestamp(x) < C.TEST_START for x in con)  # 모순은 모두 시험 전 채움 날짜(1~5월과 7/30)
    assert "2021-07-30" in con and "2021-07-28" not in con  # v2.1: 저녁 정합으로 7/28이 원본


def test_copy_origin_is_latest_consistent_member(dg):
    """복제군의 가장 늦은 구성원은 45군 중 44군이 달력·생산과 정합하고(예외 7/28·7/30군), 가장 이른 구성원은 절반만 정합한다."""
    _, _, d = dg
    s = d.summary
    assert s["copy_groups_multi"] == 45
    assert s["copy_groups_chosen_origin_consistent"] == "45/45"
    assert s["copy_groups_latest_member_consistent"] == "44/45"  # 예외 1군: 7/28·7/30(원본 7/28)
    assert s["copy_groups_earliest_member_consistent"] == "21/45"
    assert s["singleton_days_consistent_measured_period"] == "87/88"
    assert s["earliest_is_origin_binom_p"] < 1e-10
    assert s["earliest_is_origin_binom_p_measured_baseline"] < 1e-30  # 실측 기간 단독 날짜(87/88) 기준
    assert s["copied_src_later_share"] > 0.99  # 예외 1일: 7/30 ← 7/28(같은 달, 저녁 정합으로 판정)
    g = d.copy_groups
    assert (g[g["is_origin"]]["consistent"] == 1).all()
    # 1~4월은 원본일이 없다: 실측은 5월부터
    assert s["genuine_days_by_month"] == {5: 30, 6: 30, 7: 27, 8: 31, 9: 14}


def test_previous_rule_reproducible(dg):
    """비교용 v1.x 규칙(가장 이른 날짜 = 원본)은 예전 부분 복제 목록을 그대로 재현한다."""
    df, _, _ = dg
    old = C.COPY_ORIGIN
    try:
        C.COPY_ORIGIN = "earliest"
        s = D.diagnose(df).summary
    finally:
        C.COPY_ORIGIN = old
    assert s["partial_copy_days"] == ["2021-01-02", "2021-01-09", "2021-01-10", "2021-01-16", "2021-02-09",
                                      "2021-02-10", "2021-02-16", "2021-03-07", "2021-03-21", "2021-03-28"]
    assert s["copy_groups_earliest_member_consistent"] == "21/45"


def test_corruption_outage_mismatch(dg):
    df, _, d = dg
    s = d.summary
    assert s["corrupt_hour_dates"] == ["2021-07-13", "2021-07-15"]
    assert s["regime_mismatch_days"] == ["2021-07-09"]
    iv = D.build_intervals(df, d)
    out = iv.index[iv["outage"]]
    assert len(out) == 74
    assert out.min() == pd.Timestamp("2021-08-28 17:30") and out.max() == pd.Timestamp("2021-09-08 12:15")
    # 손상일 전력·생산은 결측
    bad = iv.loc["2021-07-13"]
    assert bad["y_raw"].isna().all() and bad["prod"].isna().all()
    # 평가 가능 ⊇ 학습 가능, 5월 이전 평가 가능 구간 없음
    assert (iv["trainable"] <= iv["usable"]).all()
    assert not iv.loc[iv.index < C.MEASURED_START, "usable"].any()


def test_test_period_is_clean(dg):
    df, _, d = dg
    iv = D.build_intervals(df, d)
    te = iv.loc["2021-08-01":"2021-09-14"]
    assert not te["copied"].any() and not te["partial_copy"].any() and not te["hour_copy"].any()
    assert int(te["usable"].sum()) == 4320 - 74


def test_waterfall_adds_up(dg):
    from powerguard import stage_diagnostics as SD
    df, _, d = dg
    iv = D.build_intervals(df, d)
    w = SD.preprocessing_waterfall(iv)
    assert int(w.iloc[0]["remaining"]) == 24672
    steps = w.iloc[1:6]
    assert int(w.iloc[0]["remaining"] - steps["removed"].sum()) == int(iv["usable"].sum()) == 12694


def test_consistency_rule_is_robust_to_thresholds(dg):
    """정합 판정 문턱 6개의 전 조합(972)에서 '가장 늦은 구성원 정합 ≫ 가장 이른 구성원 정합'이 유지되고, 원본이 바뀌는 군은
    많아야 3개다. 저녁 생산 문턱을 50 이상으로 올리면 6/17군의 원본이 채움 날짜(3/17)로 바뀐다(공개된 민감도)."""
    from powerguard import stage_diagnostics as SD
    df, _, d = dg
    t, summ = SD.origin_sensitivity(df, d)
    assert len(t) == 972 and int(t["is_headline"].sum()) == 1
    h = t[t["is_headline"]].iloc[0]
    assert (h["latest_consistent"], h["earliest_consistent"], h["origin_changed_groups"]) == (44, 21, 0)
    assert h["singleton_measured_consistent"] == "87/88"
    assert (t["latest_consistent"] >= 40).all()
    assert (t["earliest_consistent"] <= 25).all()
    assert (t["latest_consistent"] - t["earliest_consistent"]).min() >= 18
    assert summ["max_origin_changed_groups"] <= 3
    assert summ["one_way_from_headline"]["evening_prod_on"]["50"]["origin_changes"] == "2021-06-17→2021-03-17"
    assert summ["one_way_from_headline"]["evening_power_on"]["40"]["origin_changes"] == "-"


def test_power_only_direction_checks(dg):
    """생산 기록을 쓰지 않는 증거: 자정 연속성과 휴무 다음 날 야간 전력이 5~9월에만 실측답다."""
    from powerguard import stage_diagnostics as SD
    df, _, d = dg
    t, _ = SD.direction_checks(df, d)
    r = t.set_index(["check", "subset"])["rate"]
    assert r[("자정 연속성(전날 21~23시 ↔ 당일 01~05시)", "5~9월")] > 0.95
    assert r[("자정 연속성(전날 21~23시 ↔ 당일 01~05시)", "1~4월")] < 0.8
    assert r[("휴무 다음 평일의 01~05시 야간조 전력", "5~9월")] < 0.1
    pv = t.set_index(["check", "subset"])["p_value"]
    assert pv[("자정 연속성(전날 21~23시 ↔ 당일 01~05시)", "5~9월")] < 1e-6
    assert pv[("복제군 구성원의 앞뒤 자정 연속성", "불일치 쌍 중 가장 늦은 쪽만 연속")] < 1e-3
    ex = t.set_index(["check", "subset"])["exceptions"]
    assert ex[("휴무 다음 평일의 01~05시 야간조 전력", "5~9월")] == "8/17"


def test_naive_intervals_include_copies(dg):
    df, _, d = dg
    iv = D.build_intervals(df, d, naive=True)
    assert iv.loc["2021-02-01":"2021-02-28", "usable"].sum() > 0
    assert not iv["outage"][iv["usable"]].any()
    assert np.array_equal(iv["usable"].to_numpy(), iv["trainable"].to_numpy())
