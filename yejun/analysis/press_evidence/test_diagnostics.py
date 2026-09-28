"""합성 진단이 의도하지 않은 직류 단차·미래값 변경을 만들지 않는지 확인."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostic_probes as probes


def test_splice_matches_current_phase_and_removes_dc_step():
    t = np.arange(50) * .1
    phase = .6 * 2 * np.pi * t
    first = np.column_stack((np.sin(phase), np.cos(phase), 30 + 100 * np.cos(phase + .3)))
    second = np.column_stack((np.cos(phase), np.sin(phase), -70 + 175 * np.cos(phase + 1.1)))
    result, offset, mismatch = probes.phase_aligned_splice(first, second)
    np.testing.assert_array_equal(result[:25], first[:25])
    np.testing.assert_array_equal(result[25:, :2], second[offset:offset + 25, :2])
    np.testing.assert_allclose(result[25:, 2], 30 + 175 * np.cos(phase[offset:offset + 25] + 1.1), atol=1e-12)
    assert 0 <= offset <= 16 and mismatch <= 10.81


def test_ramp_keeps_prefix_and_reaches_requested_gain_at_endpoint():
    values = np.arange(150, dtype=float).reshape(50, 3)
    gains = np.array([1.76, 3.0, 1.75])
    centre = values.mean(axis=0)
    ramp = probes.gain_transition(values, gains, 10)
    np.testing.assert_array_equal(ramp[:25], values[:25])
    np.testing.assert_allclose(ramp[25], centre + (values[25] - centre) * (1 + .1 * (gains - 1)))
    np.testing.assert_allclose(ramp[34:], centre + (values[34:] - centre) * gains)
    step = probes.gain_transition(values, gains, 1)
    np.testing.assert_allclose(step[25:], centre + (values[25:] - centre) * gains)


def test_narrowband_probe_recovers_known_harmonics_and_phase_lock():
    frames = []
    t = np.arange(50) * .1
    for amplitude, phase in ((1.0, .1), (2.0, .8), (3.0, 1.6), (4.0, 2.4)):
        frames.append(pd.DataFrame({"AI0_Vibration": amplitude * np.cos(2 * np.pi * 3.6 * t + 6 * phase),
                                    "AI1_Vibration": amplitude * np.cos(2 * np.pi * 1.8 * t + 3 * phase),
                                    "AI2_Current": 10 + amplitude * np.cos(2 * np.pi * .6 * t + phase)}))
    frame = pd.concat(frames, ignore_index=True)
    table = probes.vibration_tones({"normal": frame}, {"normal": np.repeat(np.arange(4), 50)})
    for sensor, expected in (("AI0_Vibration", 3.6), ("AI1_Vibration", 1.8)):
        group = table[table.sensor.eq(sensor)]
        summary = probes.tone_summary(group)
        assert abs(summary["tone_frequency_hz_median"] - expected) < 1e-5
        assert summary["harmonic_r2_median"] > .999999
        assert summary["phase_lock_R"] > .999999
        assert summary["tone_amp_current_spearman"] > .999999


def test_observation_power_accounts_for_short_record_blindness():
    frames, state_rows, segments = [], [], []
    for record, (length, state, amplitude) in enumerate(((17, probes.LOW, 100), (17, probes.LOADED, 175),
                                                        (50, probes.LOW, 100), (50, probes.LOADED, 175))):
        frames.extend(amplitude * np.cos(2 * np.pi * .6 * np.arange(length) * .1 + .3))
        segments.extend([record] * length)
        state_rows.append(dict(record=record, state=state, amp06=amplitude))
    power = probes.transition_observation_power(pd.DataFrame({"AI2_Current": frames}), np.array(segments), pd.DataFrame(state_rows), repeats=100)
    assert 0 < power["power"] < .5  # 17행은 창 하나뿐이므로 전환을 검출할 수 없다.
    assert power["long_record_power"] > power["power"]
    assert power["expected_detected_length_weighted"] > power["expected_detected_approx"]
