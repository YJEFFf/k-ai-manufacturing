"""미래 교란 불변 테스트: 발행 시점 이후의 전력을 바꿔도 그 발행의 특징이 변하지 않아야 한다."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from powerguard import cv as CV
from powerguard import data as D
from powerguard import features as F


@pytest.fixture(scope="module")
def base():
    df, _ = D.load_raw()
    dg = D.diagnose(df)
    iv = D.build_intervals(df, dg)
    return iv


def _perturb_after(iv: pd.DataFrame, t0: pd.Timestamp, seed: int = 0) -> pd.DataFrame:
    """t0 이후 시작하는 구간의 전력(y_raw·y·y_train)을 무작위 값으로 바꾼다."""
    rng = np.random.default_rng(seed)
    iv2 = iv.copy()
    m = iv2.index >= t0
    noise = rng.uniform(20, 220, m.sum())
    for c in ("y_raw", "y", "y_train"):
        iv2.loc[m, c] = np.where(iv2.loc[m, c].notna(), noise, np.nan)
    return iv2


@pytest.mark.parametrize("day", ["2021-07-21", "2021-08-18", "2021-09-07"])
def test_dayahead_features_ignore_power_after_issue(base, day):
    d = pd.Timestamp(day)
    issue = d - pd.Timedelta(days=1) + pd.Timedelta(hours=17)  # D-1 17:00
    st = F.schedule_table(base)
    a = F.dayahead_features(base, st, issue_hour=17)
    b = F.dayahead_features(_perturb_after(base, issue), st, issue_hour=17)
    rows = (a.index >= d) & (a.index < d + pd.Timedelta(days=1))
    cols = F.feature_list("B")
    pd.testing.assert_frame_equal(a.loc[rows, cols], b.loc[rows, cols])


@pytest.mark.parametrize("h", [1, 4])
@pytest.mark.parametrize("ts", ["2021-07-21 08:00", "2021-08-18 13:15", "2021-09-07 07:45"])
def test_intraday_features_ignore_power_after_issue(base, h, ts):
    issue_end = pd.Timestamp(ts)  # 발행 = 이 시각(= 구간 i의 종료)
    target = issue_end + pd.Timedelta(minutes=15 * (h - 1))
    st = F.schedule_table(base)
    xa = F.intraday_features(base, h, F.dayahead_features(base, st, issue_hour=24))
    pb = _perturb_after(base, issue_end)
    xb = F.intraday_features(pb, h, F.dayahead_features(pb, st, issue_hour=24))
    cols = F.feature_list("A")
    pd.testing.assert_series_equal(xa.loc[target, cols], xb.loc[target, cols], check_names=False)


def test_cv_train_mask_respects_gap(base):
    idx = base.index
    tr = base["trainable"].to_numpy()
    for _, s, _ in CV.cv_blocks():
        mA = CV.train_mask(idx, tr, s, "A")
        mB = CV.train_mask(idx, tr, s, "B")
        assert idx[mA].max() + pd.Timedelta(minutes=15) <= s - CV.GAP
        assert idx[mB].max() + pd.Timedelta(minutes=15) <= s - pd.Timedelta(hours=7)


def test_weekly_blocks_cover_period_without_overlap():
    blocks = CV.weekly_blocks(pd.Timestamp("2021-08-01"), pd.Timestamp("2021-09-15"))
    assert blocks[0][0] == pd.Timestamp("2021-08-01") and blocks[-1][1] == pd.Timestamp("2021-09-15")
    for (s1, e1), (s2, e2) in zip(blocks, blocks[1:]):
        assert e1 == s2 and s2.dayofweek == 0


@pytest.mark.parametrize("h", [2, 3, 4])
@pytest.mark.parametrize("target", ["2021-08-18 00:00", "2021-08-18 00:15", "2021-09-07 00:30", "2021-07-22 00:00"])
@pytest.mark.parametrize("mode", ["extreme", "nan"])
def test_intraday_midnight_targets_with_extreme_perturbation(base, h, target, mode):
    """자정 직후 목표(발행이 전날 23시대)와 극단값·결측 교란: 전날 요약이 발행 뒤 값을 쓰면 실패한다."""
    t = pd.Timestamp(target)
    issue_end = t - pd.Timedelta(minutes=15 * (h - 1))
    pb = base.copy()
    m = pb.index >= issue_end
    for c in ("y_raw", "y", "y_train"):
        pb.loc[m, c] = (pb.loc[m, c] + 1000.0) if mode == "extreme" else np.nan
    st = F.schedule_table(base)
    xa = F.intraday_features(base, h, F.dayahead_features(base, st, issue_hour=24))
    xb = F.intraday_features(pb, h, F.dayahead_features(pb, st, issue_hour=24))
    cols = F.feature_list("A")
    pd.testing.assert_series_equal(xa.loc[t, cols], xb.loc[t, cols], check_names=False)
