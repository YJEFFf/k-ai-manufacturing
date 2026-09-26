"""v2.0 회귀 테스트: 계획 정지 게이트, 지연값 출처(학습 제외일도 관측값은 실시간 입력)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from powerguard import cv as CV
from powerguard import data as D
from powerguard import features as F
from powerguard import models as M


@pytest.fixture(scope="module")
def base():
    df, _ = D.load_raw()
    dg = D.diagnose(df)
    iv = D.build_intervals(df, dg)
    return iv, CV.build_frames(iv, tasks=("B", "A4"))


class _Const:
    features = ["slot"]

    def fit(self, X, y):
        return self

    def predict(self, X):
        return np.full(len(X), 999.0)


@pytest.mark.parametrize("task", ["B", "A4"])
def test_plan_stop_gate_uses_structural_base_on_stop_days(base, task):
    iv, fr = base
    X = fr[task].loc["2021-08-01":"2021-08-10"]
    g = M.PlanStopGate(_Const(), "A" if task.startswith("A") else "B").fit(X, np.zeros(len(X)))
    p = g.predict(X)
    stop = X["regime"].to_numpy() == 0
    assert stop.any() and (~stop).any()
    assert np.all(p[~stop] == 999.0)
    assert np.nanmax(p[stop]) < 60  # 휴가 주간(평일 정지)에는 대기 수준(≈21~28)
    assert np.isfinite(p).all()


def test_lags_use_observed_values_on_train_excluded_day(base):
    """7/09는 학습·유사일에서만 빠진다(전력–생산 불일치). 그날의 관측은 다음 구간의 지연값으로 쓰여야 한다."""
    iv, fr = base
    assert not iv.loc["2021-07-09", "trainable"].any() and iv.loc["2021-07-09", "usable"].all()
    X = F.intraday_features(iv, 1, F.dayahead_features(iv, F.schedule_table(iv), issue_hour=24))
    t = pd.Timestamp("2021-07-09 10:00")
    assert X.at[t, "lag_0"] == iv.at[t - pd.Timedelta(minutes=15), "y"]
    assert np.isfinite(X.loc["2021-07-09", "lag_0"].iloc[1:]).all()
