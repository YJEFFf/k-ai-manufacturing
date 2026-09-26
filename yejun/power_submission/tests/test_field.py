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


def test_measured_payback_uses_pre_shed_demand_forecast_and_no_dump():
    """측정 기반 회복(v2.3): 차단으로 낮아진 직전 값이 아니라 차단 전 수요와 익일 예측으로 판정하고, 창 안에 못 푼 잔여는
    한 구간에 몰지 않고 같은 날 20~23시에 나눈다. 에너지는 보존된다."""
    n = 96
    room = np.full(n, 205.9)
    # (1) 고원 200에서 차단: 낮아진 값(180)으로 보면 바로 풀지만, 차단 전 수요(200) + 회복분 > 205.9라 풀지 않는다
    y = np.full(n, 200.0)
    y[60:] = 150.0
    al = np.zeros(n, bool)
    al[40] = True
    y2, _ = SF.simulate(y.copy(), al, 0.10, room=room, search=16, unlock_after_shed=True)
    assert np.isclose(y2.sum(), y.sum()) and y2[43:58].max() <= 200.0
    # (2) 7/19 모양: 차단 직후 급변 구간(43)은 직전 수요가 낮아도(182) 익일 예측(205)에 여유가 없어 회복분을 얹지 않는다
    y = np.full(n, 150.0)
    y[40:48] = [209, 203, 182, 222, 207, 186, 205, 204]
    fc = np.full(n, 150.0)
    fc[36:52] = 205.0
    y2, _ = SF.simulate(y.copy(), al, 0.10, room=room, search=16, unlock_after_shed=True, forecast=fc)
    assert np.isclose(y2.sum(), y.sum()) and y2[43] == 222.0  # v2.2: 231.6
    # (3) 고원(208)이 이어져 창 안에 못 풀면 잔여는 20~23시에 고르게(몰아넣기 없음)
    z = np.full(n, 208.0)
    z2, _ = SF.simulate(z.copy(), al, 0.10, room=room, search=16, unlock_after_shed=True)
    assert np.isclose(z2.sum(), z.sum())
    assert z2.max() <= 208.0 + 41.6 / 16 + 1e-9
    assert np.allclose(z2[80:96], z2[80])


def test_interlock_caps_single_interval_spikes_only():
    y = np.array([180.0, 182.0, 222.0, 207.0, 206.0, 214.0, 190.0])
    y2, n = SF.apply_interlock(y, 15.0)
    assert n == 1 and y2[2] == 207.0 and y2[5] == 214.0  # 214는 앞뒤보다 +8·+24 → 한쪽만 높아 스파이크 아님
    assert SF.event_type(15.0, 45, 15.0) == "spike" and SF.event_type(15.0, 45, 20.0) == "plateau"


def test_measured_payback_does_not_stack_beyond_room():
    """연속 차단 사건들의 회복분이 한 구간에 겹쳐도, 이미 푼 양을 포함해 (목표 − 여유)를 넘기지 않는다(직전 수요 기준)."""
    n = 96
    y = np.full(n, 150.0)
    y[36:44] = 204.0
    al = np.zeros(n, bool)
    al[35] = al[37] = al[39] = True  # 차단 직후 재경보(측정 기반 회복)
    room = np.full(n, 205.9)
    y2, info = SF.simulate(y.copy(), al, 0.10, room=room, search=16, unlock_after_shed=True)
    assert info["episodes"] == 3 and np.isclose(y2.sum(), y.sum())
    head = np.r_[np.nan, y[:-1]]  # 이 예에서는 차단 전 수요 = 원래 값
    extra = y2 - y
    ok = (extra <= 1e-9) | (head + extra <= 205.9 + 1e-9) | (np.arange(n) >= 80)
    assert ok.all()
