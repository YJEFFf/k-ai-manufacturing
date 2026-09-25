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
    assert s["partial_copy_days"] == ["2021-01-02", "2021-01-09", "2021-01-10", "2021-01-16", "2021-02-09",
                                      "2021-02-10", "2021-02-16", "2021-03-07", "2021-03-21", "2021-03-28"]
    assert set(pd.to_datetime(d.contradictions["date"]).dt.strftime("%Y-%m-%d")) == {
        "2021-02-11", "2021-03-01", "2021-03-14", "2021-05-09"}


def test_corruption_outage_mismatch(dg):
    df, _, d = dg
    s = d.summary
    assert s["corrupt_hour_dates"] == ["2021-07-13", "2021-07-15"]
    assert s["regime_mismatch_days"] == ["2021-01-17", "2021-01-24", "2021-02-19", "2021-02-26"]
    iv = D.build_intervals(df, d)
    out = iv.index[iv["outage"]]
    assert len(out) == 74
    assert out.min() == pd.Timestamp("2021-08-28 17:30") and out.max() == pd.Timestamp("2021-09-08 12:15")
    # 손상일 전력·생산은 결측
    bad = iv.loc["2021-07-13"]
    assert bad["y_raw"].isna().all() and bad["prod"].isna().all()
    # 평가 가능 ⊇ 학습 가능
    assert (iv["trainable"] <= iv["usable"]).all()


def test_test_period_is_clean(dg):
    df, _, d = dg
    iv = D.build_intervals(df, d)
    te = iv.loc["2021-08-01":"2021-09-14"]
    assert not te["copied"].any() and not te["partial_copy"].any() and not te["hour_copy"].any()
    assert int(te["usable"].sum()) == 4320 - 74
