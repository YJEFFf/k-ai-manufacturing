"""사건의 기록 경계 격상과 진단 상태의 인과성·청크 불변 회귀시험."""
import numpy as np
import pandas as pd
import pytest

from model import D, HERE, GuardModel, StreamDetector, current_states, cases, incidents, layout


@pytest.fixture(scope="module")
def sample():
    normal, _ = D.load()[:2]
    split = D.split_normal(normal, D.segments(normal), "B")
    return GuardModel.load(HERE / "artifacts" / "guard_B.json"), split["test"]


def test_running_state_uses_only_observed_raw_current():
    current = 1000 + 160 * np.sin(2 * np.pi * .6 * np.arange(55) * .1)
    rec = np.r_[np.zeros(50, int), np.ones(5, int)]
    rms, states = current_states(current, rec)
    for i in range(len(current)):
        segment = current[:i + 1][rec[:i + 1] == rec[i]]
        assert rms[i] == pytest.approx(np.std(segment), abs=1e-10)
    assert set(states[:16]) == {"short"}
    assert states[49] == "load" and set(states[50:]) == {"short"}
    prefix = current_states(current[:22], rec[:22])
    np.testing.assert_array_equal(prefix[0], rms[:22])


def test_b_false_alarms_are_in_load_state(sample):
    model, normal = sample
    pred = model.predict(normal)
    queue = cases(pred)
    assert queue.record_id.tolist() == [3, 41, 150]
    assert queue.operating_state.tolist() == ["load"] * 3
    records = layout(normal)[1]
    for r in queue.itertuples():
        x = normal.loc[records == r.record_id, D.SENSORS[2]].to_numpy(float)
        assert r.record_current_rms == pytest.approx(np.std(x), abs=1e-10)


def test_two_single_row_cases_escalate_one_incident(sample):
    model, normal = sample
    records = layout(normal)[1]
    parts = [D.inputs_only(normal.loc[records == k]).reset_index(drop=True) for k in (3, 41)]
    start = pd.Timestamp("2022-07-12 00:00:00")
    for part in parts:
        part[D.TIME] = (start + pd.to_timedelta(np.arange(len(part)) * .1, unit="s")).astype(str)
        start += pd.Timedelta(seconds=(len(part) - 1) * .1 + 2)
    frame = pd.concat(parts, ignore_index=True)
    pred = model.predict(frame)
    queue = cases(pred)
    assert queue.alarm_rows.tolist() == [1, 1]
    assert pred.incident_notification.sum() == pred.incident_escalation.sum() == 1
    expected_row = int(pred.loc[pred.incident_escalation.eq(1), "row_id"].iloc[0])
    for with_predictions in (False, True):
        inc = incidents(queue, pred if with_predictions else None)
        assert len(inc) == 1 and inc.level.iloc[0] == 2
        assert inc.escalation_row.iloc[0] == expected_row
    for size in (1, 7, 31):
        stream = StreamDetector(model)
        actual = pd.concat([stream.push(frame.iloc[i:i + size]) for i in range(0, len(frame), size)], ignore_index=True)
        pd.testing.assert_frame_equal(actual, pred, rtol=1e-11, atol=1e-11)
