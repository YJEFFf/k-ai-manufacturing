"""monitor.py 계약: 알림 수 한계, 재보정 검토 규칙, 정상 운전변화(전류 배율) 모의에서의 발동."""
import numpy as np
import pandas as pd
import pytest

from model import D, HERE, load_bundle
from monitor import (Reference, alert_limit, gain_scenarios, monitor_windows,
                     ACTION_OBSERVE, ACTION_RECALIBRATE, ACTION_INSPECT_SHIFT, ACTION_INSPECT)


@pytest.fixture(scope="module")
def split_b():
    normal, _, _ = D.load()
    sp = D.split_normal(normal, D.segments(normal), "B")
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    return model, sp, Reference.from_frame(pd.concat([sp["train"], sp["cal"]], ignore_index=True))


def test_limits_grow_with_units_and_alpha():
    assert alert_limit(.01, 120, 0) == 0
    assert alert_limit(.01, 120, 60) <= alert_limit(.01, 120, 600) and alert_limit(.01, 120, 60) <= alert_limit(.05, 120, 60)
    assert alert_limit(.01, 120, 60, .99) >= alert_limit(.01, 120, 60)


def test_unshifted_normal_does_not_trigger(split_b):
    model, sp, ref = split_b
    win = monitor_windows(model.predict(sp["test"], .01), sp["test"], .01, len(model.cal), ref)
    assert win.units.sum() == 180 and win.alerted_units.sum() == 3 and not win.recalibration_review.any()


def test_current_gain_triggers_review(split_b):
    """전류 배율 1.0~1.2는 관측 지속이고 1.3·1.5는 조치 대상이다. 무기록 상승을 재보정으로 흡수하지 않는다."""
    model, sp, ref = split_b
    g = gain_scenarios(model, ref, sp["test"], .01, gains=(1.0, 1.05, 1.2, 1.3, 1.5)).set_index("gain")
    assert not g.loc[[1.0, 1.05, 1.2], "recalibration_review"].any()
    assert g.loc[[1.3, 1.5], "recalibration_review"].all()
    assert g.loc[1.5, "alerted_units"] == 17 and g.loc[1.5, "windows_drift_up"] >= 1
    assert f"0:{ACTION_INSPECT_SHIFT}" in g.loc[1.5, "recommended_actions_no_change"]
    assert f"0:{ACTION_RECALIBRATE}" in g.loc[1.5, "recommended_actions_with_change"]
    assert f"0:{ACTION_INSPECT}" in g.loc[1.3, "recommended_actions_no_change"]
    assert ACTION_INSPECT not in g.loc[1.0, "recommended_actions_no_change"]
    assert g.incident_notifications.eq(g.incident_level1_notifications + g.incident_level2_escalations).all()


def test_operating_change_and_degradation_get_different_actions(split_b):
    """평가관 04 2회차 R2-01: 전류 ×1.3(운전 조건 변경 기록 있음)은 재보정 검토, 마지막 창의 진동 1σ(기록 없음)는 설비 점검 요청."""
    from monitor import ACTION_RECALIBRATE, ACTION_INSPECT
    from recalibrate import inject
    model, sp, ref = split_b
    test = D.inputs_only(sp["test"])
    g = test.copy(); g["AI2_Current"] = pd.to_numeric(g.AI2_Current) * 1.3
    w1 = monitor_windows(model.predict(g, .01), g, .01, len(model.cal), ref, 60, [g.TimeStamp.iloc[5]])
    assert w1.recommended_action.iloc[0] == ACTION_RECALIBRATE and w1.operating_change.iloc[0]
    f = inject(test, model, "vib_noise", 1.0, D.segments(test) >= 120, np.random.default_rng(0))
    w2 = monitor_windows(model.predict(f, .01), f, .01, len(model.cal), ref, 60)
    assert w2.recommended_action.iloc[-1] == ACTION_INSPECT and "정상 확인" in w2.recalibration_data.iloc[-1]
    assert set(w2.recommended_action.iloc[:-1]) == {"관측 지속"}


def test_four_actions_and_normal_confirmation_requirement(split_b):
    """무기록 ×1.5는 FM4·FM5 점검, 변경 기록이 있으면 재보정 검토. 무기록 ×1.3·진동2σ는 열화 점검이다."""
    from recalibrate import inject
    model, sp, ref = split_b
    raw = D.inputs_only(sp["test"])
    shifted = raw.copy()
    shifted[D.SENSORS[2]] = pd.to_numeric(shifted[D.SENSORS[2]]) * 1.5
    pred = model.predict(shifted, .01)
    no_change = monitor_windows(pred, shifted, .01, len(model.cal), ref)
    with_change = monitor_windows(pred, shifted, .01, len(model.cal), ref, operating_changes=[shifted[D.TIME].iloc[0]])
    assert no_change.iloc[0].drift_up and no_change.iloc[0].recommended_action == ACTION_INSPECT_SHIFT
    assert "정상 확인" in no_change.iloc[0].recalibration_data
    assert with_change.iloc[0].recommended_action == ACTION_RECALIBRATE
    vib = inject(raw, model, "vib_noise", 2.0, np.ones(len(raw), bool), np.random.default_rng(0))
    windows = monitor_windows(model.predict(vib, .01), vib, .01, len(model.cal), ref)
    assert set(windows.recommended_action) <= {ACTION_OBSERVE, ACTION_INSPECT}
    assert ACTION_INSPECT in set(windows.recommended_action)


def test_monitor_counts_incident_notifications_across_windows(split_b):
    """이상 21기록은 창 경계를 지나도 사건 시작·격상 각 1회다. 감시표 합계가 simulate 알림과 같다."""
    import simulate
    model, _, ref = split_b
    _, abnormal, _ = D.load()
    pred = model.predict(abnormal, .01)
    win = monitor_windows(pred, abnormal, .01, len(model.cal), ref, window_units=5)
    log = simulate.run(abnormal, model, .01, chunk=128)
    assert win.level1_notifications.sum() == 1 and win.level2_escalations.sum() == 1
    assert win.incident_notifications.sum() == log.notify.sum() == 2


def test_monitor_command_matches_gain_table(split_b, tmp_path, capsys):
    """평가관 04 2회차 R2-07: 교대 감시 명령. 대회 B 평가 자료의 창별 알림 단위가 monitor_gain_v2 ×1.0 행(2/0/1)과 같다."""
    import monitor
    _, sp, _ = split_b
    csv = tmp_path / "shift.csv"; D.inputs_only(sp["test"]).to_csv(csv, index=False)
    out = tmp_path / "windows.csv"
    assert monitor.main(["--csv", str(csv), "--split", "B", "--out", str(out)]) == 0
    w = pd.read_csv(out)
    assert "/".join(map(str, w.alerted_units)) == "2/0/1"
    gain = pd.read_csv(HERE / "outputs" / "monitor_gain_v2.csv")
    assert gain[gain.split.eq("B") & gain.alpha.eq(.01) & gain.gain.eq(1.0)].alerted_by_window.iloc[0] == "2/0/1"
