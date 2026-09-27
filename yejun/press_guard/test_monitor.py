"""monitor.py 계약: 알림 수 한계, 재보정 검토 규칙, 정상 운전변화(전류 배율) 모의에서의 발동."""
import numpy as np
import pandas as pd
import pytest

from model import D, HERE, load_bundle
from monitor import Reference, alert_limit, gain_scenarios, monitor_windows


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
    """analysis/press_dayshift와 같은 전류 배율: 1.0~1.2는 발동하지 않고 1.3·1.5는 재보정 검토로 넘어간다(B, α=1%)."""
    model, sp, ref = split_b
    g = gain_scenarios(model, ref, sp["test"], .01, gains=(1.0, 1.05, 1.2, 1.3, 1.5)).set_index("gain")
    assert not g.loc[[1.0, 1.05, 1.2], "recalibration_review"].any()
    assert g.loc[[1.3, 1.5], "recalibration_review"].all()
    assert g.loc[1.5, "alerted_units"] == 17 and g.loc[1.5, "windows_drift_up"] >= 1
