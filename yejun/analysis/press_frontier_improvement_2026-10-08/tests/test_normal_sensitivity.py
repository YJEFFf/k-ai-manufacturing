"""Contracts for new normal-only sensitivity scenarios, not model performance."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_normal_sensitivity import (CURRENT_STEP, NEW_FAMILIES, MODELS,
    new_injection, paired_summary, shift_frequency, fit_sine, leave_one_family_out,
    install_normal_only_guard)
from verify_normal_sensitivity import verify_scenarios


@pytest.fixture
def aggregation_example():
    scenario = dict(split="A", family="example", target=0, strength=1., sign=1,
                    seed=0, onset_fraction=.25, model="V2")
    detail = pd.DataFrame([dict(**scenario, record=480+i, onset=2, rows=10,
        detected=i != 1, control_detected=i == 0, pre_onset_alarm=False,
        delay_s=[.2, np.nan, .4][i]) for i in range(3)])
    summary = pd.DataFrame([dict(**scenario, records=3, detected=2, missed=1,
        control_detected=1, detection_rate=2/3, control_rate=1/3, paired_increase=1/3,
        pre_onset_alarm_records=0, hit_only_median_delay_s=.3)])
    return detail, summary


def test_record_aggregation_keeps_misses_and_hit_only_delay(aggregation_example):
    detail, summary = aggregation_example
    macro = verify_scenarios(detail, summary, 480, 483)
    assert macro.iloc[0].mean_detection_rate == 2/3


@pytest.mark.parametrize("corruption", ["missing_record", "false_hit_count", "delay_for_miss"])
def test_record_aggregation_rejects_corrupted_results(aggregation_example, corruption):
    detail, summary = aggregation_example
    if corruption == "missing_record":
        detail = detail.iloc[:-1]
    elif corruption == "false_hit_count":
        summary.loc[0, "detected"] = 3
    else:
        detail.loc[1, "delay_s"] = 0.
    with pytest.raises(ValueError):
        verify_scenarios(detail, summary, 480, 483)


@pytest.fixture
def example():
    rng = np.random.default_rng(51)
    x = rng.normal(size=(45, 3))
    gen = SimpleNamespace(ac_scale_=np.array([.1, .2, 100.]), mean_=np.array([.01, -.02, 1.]))
    return x, gen


@pytest.mark.parametrize("family", list(NEW_FAMILIES))
def test_injection_prefix_other_channels_and_zero(example, family):
    x, gen = example
    spec = NEW_FAMILIES[family]
    for target in spec["targets"]:
        out = new_injection(x, gen, family, target, spec["strengths"][0], 12, 811)
        assert out[:12].tobytes() == x[:12].tobytes()
        remaining = [i for i in range(3) if i != target]
        assert out[:, remaining].tobytes() == x[:, remaining].tobytes()
        assert new_injection(x, gen, family, target, 0, 12, 811).tobytes() == x.tobytes()
        assert np.array_equal(out, new_injection(x, gen, family, target, spec["strengths"][0], 12, 811))
        assert not np.array_equal(out[:, target], x[:, target])


@pytest.mark.parametrize("family", list(NEW_FAMILIES))
def test_injection_uses_fixed_ramp_and_no_future_record_center(example, family):
    x, gen = example
    spec = NEW_FAMILIES[family]
    target, strength = spec["targets"][0], spec["strengths"][0]
    original = new_injection(x, gen, family, target, strength, 5, 811)
    changed = x.copy(); changed[25:] *= 999
    changed_result = new_injection(changed, gen, family, target, strength, 5, 811)
    assert original[:25].tobytes() == changed_result[:25].tobytes()
    assert original[:25].tobytes() == new_injection(x[:25], gen, family, target, strength, 5, 811).tobytes()


def test_ramp_reaches_frozen_scale_without_overshoot(example):
    x, gen = example
    out = new_injection(x, gen, "slow_vibration_level_ramp", 1, .5, 5, sign=-1)
    delta = out[:, 1] - x[:, 1]
    np.testing.assert_allclose(delta[24:], -.5 * gen.ac_scale_[1], rtol=0, atol=1e-15)


def test_frequency_zero_matches_original_matched_grid_and_preserves_vibration():
    t = np.arange(40)*.1
    x = np.column_stack([np.sin(t), np.cos(t), np.round(100*np.sin(2*np.pi*.606*t)/CURRENT_STEP)*CURRENT_STEP])
    out = shift_frequency(x, 0., fit_sine(x[:, 2]))
    np.testing.assert_array_equal(out, x)
    moved = shift_frequency(x, -.1, fit_sine(x[:, 2]))
    np.testing.assert_array_equal(moved[:, :2], x[:, :2])
    np.testing.assert_array_equal(shift_frequency(x[:7], .1), x[:7])


def test_paired_detection_excludes_pre_onset_alarms_but_retains_misses():
    result, _ = paired_summary([np.array([1, 0, 0, 0], bool), np.array([0, 0, 0, 1], bool)],
                              [np.array([1, 0, 0, 0], bool), np.array([0, 0, 0, 0], bool)], [2, 2])
    assert result["records"] == 2 and result["detected"] == 1 and result["missed"] == 1
    assert result["control_detected"] == 0 and result["pre_onset_alarm_records"] == 1
    assert result["hit_only_median_delay_s"] == .1


def test_family_exclusion_retains_original_eligibility_and_can_change_choice():
    rows = []
    for name, values, selectable, eligible in [(MODELS[1], [.5]*4, True, True),
          ("alternative", [.1,.8,.8,.8], True, True), ("excluded", [1.]*4, False, True),
          ("fails_gate", [1.]*4, True, False)]:
        rows.append(dict(model=name,selectable=selectable,gate_pass=eligible,maximum_stress_fpr=.1,complexity=3,
                         **{f"detection_{i}":v for i,v in enumerate(values)}))
    source = pd.DataFrame(rows); original = source.copy(deep=True)
    out = leave_one_family_out(source)
    assert out.iloc[0].audit_choice == MODELS[1]
    assert out[out.excluded_family.eq("0")].iloc[0].audit_choice == "alternative"
    assert set(out.eligible_candidates) == {2}
    assert not out.selection_applied.any()
    pd.testing.assert_frame_equal(source, original)


def test_invalid_zeroing_duration_rejected(example):
    x, gen = example
    with pytest.raises(ValueError):
        new_injection(x, gen, "intermittent_zeroing", 0, 1.5, 5)


def test_raw_input_guard_blocks_abnormal_before_open(tmp_path, monkeypatch):
    from frontier_model import D
    hooks = []
    monkeypatch.setattr(sys, "addaudithook", hooks.append)
    allowed = install_normal_only_guard(tmp_path)
    hooks[0]("open", (str(allowed), "r", 0))
    with pytest.raises(PermissionError):
        hooks[0]("open", (str(tmp_path / D.FILES["abnormal"]), "r", 0))
    with pytest.raises(PermissionError):
        hooks[0]("open", (str(tmp_path / "renamed.csv"), "r", 0))
