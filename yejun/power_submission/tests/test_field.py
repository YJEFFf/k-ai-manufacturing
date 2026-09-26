"""현장 시뮬레이션 도우미: 요금적용전력(래칫), 경보 등급 히스테리시스, 기동 분산 에너지 보존."""
from __future__ import annotations

import numpy as np
import pandas as pd

from powerguard import stage_field as SF


def test_billing_demand_ratchet():
    mm = {5: 200.0, 6: 222.0, 7: 210.0, 8: 205.0, 9: 190.0}
    b = SF.billing_demand(mm)
    # 6월은 래칫 대상 월이 아니므로 7월 이후 요금적용전력에 들어가지 않는다
    assert b[6] == 222.0 and b[7] == 210.0 and b[8] == 210.0 and b[9] == 210.0
    assert SF.ratchet_max(mm) == 210.0


def test_grade_sequence_hysteresis():
    p = np.array([0.1, 0.9, 0.1, 0.1, 0.1, 0.6, 0.3, 0.6])
    g = SF.grade_sequence(p, hold=2)
    # 심각(3) 뒤 한 구간만 내려가면 유지, 두 구간 연속이면 내려간다
    assert list(g[:5]) == [0, 3, 3, 0, 0]
    assert g[5] == 2 and g[6] == 2 and g[7] == 2


def test_staggering_conserves_energy():
    idx = pd.date_range("2021-06-01", periods=96, freq="15min")
    y = np.full(96, 150.0)
    y[32:36] = [190, 185, 175, 160]
    iv = pd.DataFrame({"y": y, "prod": 1000.0, "hour": idx.hour, "usable": True, "trainable": True,
                       "y_train": y, "temp": 25.0, "holiday": False}, index=idx)
    iv["date"] = idx.normalize()
    y2 = SF.apply_staggering(y.copy(), iv, m_fixed=20.0, s=0.5, hold=0.0)
    assert np.isclose(np.nansum(y2), np.nansum(y))
    assert np.nanmax(y2) < np.nanmax(y)
