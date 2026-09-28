"""관측 범위 점검용 사후 진단. 저장 모델·분할·문턱을 변경하지 않는다.

정상 전환의 속도와 물리 원인은 자료에서 관측되지 않았다. 합성 기록의
경보율과 좁은 대역 적합은 가정별 민감도이며 현장 성능 추정치가 아니다.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import optimize, stats

TRANSITION_SEED = 20260928
POWER_SEED = 0
JITTER_SEED = 20260929
JITTER_REPEATS = 5
# (원 주파수 가설 Hz, 표본화 시각 흔들림 RMS ms). 10 Hz 표본에서 0.6 Hz로 보이려면 원 신호가 k·10 ± 0.6 Hz다. 60.6 Hz는 상용 전원 대역
# (60 Hz 직입이면 실제 표본화 주기가 명목과 약 1% 다른 경우와 같은 접힘), 50.6 Hz는 인버터 운전의 예, 0.6 Hz는 앨리어싱이 아닌 물리 주기 대조다.
# 위상 오차는 2π·(원 주파수)·δt라 60·60.6 Hz의 차이(1%)는 결과에 거의 영향이 없다. 2.4 ms는 이상 파일의 전류 사인 R² 중앙값 0.451과 같은 크기(class_differences.csv)
JITTER_CONDITIONS = ((None, 0.0), (60.6, .05), (60.6, .1), (60.6, .2), (60.6, .5), (60.6, 2.4), (50.6, .1), (50.6, .2), (0.6, 2.4))
SPLICE_ROW = 25
PAIR_COUNT = 200
LOW, LOADED = "저수준", "부하"
SENSORS = ("AI0_Vibration", "AI1_Vibration", "AI2_Current")


def tone_design(n, frequency, dt=.1):
    phase = 2 * np.pi * frequency * np.arange(n) * dt
    return np.column_stack((np.cos(phase), np.sin(phase), np.ones(n)))


def tone_coefficients(values, frequency, dt=.1):
    return np.linalg.lstsq(tone_design(len(values), frequency, dt), values, rcond=None)[0]


def phase_aligned_splice(first, second, at=SPLICE_ROW, dt=.1):
    """50행 두 기록을 전류 0.6 Hz 위상·평균에 맞춰 잇는다.

    센서 순서는 AI0·AI1·AI2. 두 번째 기록의 시작 오프셋은 0~16이다.
    전류 위상만 맞추므로 진동 위상 불연속은 같은 상태 대조에도 남는다.
    """
    if first.shape != (50, 3) or second.shape != (50, 3):
        raise ValueError("잇기 입력은 센서 3열의 50행 기록이어야 한다")
    ca, cb = (tone_coefficients(x[:, 2], .6, dt) for x in (first, second))
    # cos 계수 a, sin 계수 b일 때 시간 위상은 atan2(-b, a).
    target = np.arctan2(-ca[1], ca[0]) + 2 * np.pi * .6 * at * dt
    candidates = np.arange(17)
    incoming = np.arctan2(-cb[1], cb[0]) + 2 * np.pi * .6 * candidates * dt
    errors = np.abs(np.angle(np.exp(1j * (incoming - target))))
    offset = int(np.argmin(errors))
    result = np.concatenate((first[:at], second[offset:offset + 50 - at])).copy()
    result[at:, 2] += ca[2] - cb[2]
    return result, offset, float(np.degrees(errors[offset]))


def gain_transition(values, gains, ramp_rows, at=SPLICE_ROW):
    """기록 평균을 기준으로 시간별 편차 이득을 적용한다. ramp_rows=1은 계단이다."""
    if ramp_rows < 1:
        raise ValueError("경사 길이는 양수여야 한다")
    weight = np.clip((np.arange(len(values)) - at + 1) / ramp_rows, 0, 1)
    centre = values.mean(axis=0)
    return centre + (values - centre) * (1 + weight[:, None] * (np.asarray(gains) - 1))


def _synthetic_frame(records, dt=.1):
    data = np.concatenate(records)
    # 50행당 4.9초 기록 뒤 5초 공백. 모델 경계가 합성 기록과 일치한다.
    ticks = (np.repeat(np.arange(len(records)) * 9900, 50) +
             np.tile(np.arange(50) * round(dt * 1000), len(records)))
    frame = pd.DataFrame(data, columns=SENSORS)
    frame.insert(0, "TimeStamp", (pd.Timestamp("2030-01-01") + pd.to_timedelta(ticks, unit="ms")).strftime("%Y-%m-%d %H:%M:%S.%f"))
    return frame


def transition_stress(normal, segments, states, models, test_starts, alphas=(.01, .03, .05)):
    """분할별 200쌍 잇기·같은 상태 대조와 모든 원기록의 계단/경사 이득.

    같은 원기록이 여러 쌍에 쓰이므로 쌍을 독립 표본으로 간주한 CI를 만들지
    않는다. 대조는 진폭비 max(a/b,b/a)로 층화하고 모든 분모를 보존한다.
    """
    rng = np.random.default_rng(TRANSITION_SEED)
    indexed = states.set_index("record")
    rows_of = {int(s): np.flatnonzero(segments == s) for s in np.unique(segments)}
    raw = normal[list(SENSORS)].to_numpy(float)
    med = indexed.groupby("state")[["AI0_sd", "AI1_sd", "amp06"]].median()
    gain_up = (med.loc[LOADED] / med.loc[LOW]).to_numpy()
    output = []
    for sid, model in models.items():
        pools = {state: indexed.index[(indexed.index >= test_starts[sid]) & indexed.length.eq(50) & indexed.state.eq(state)].to_numpy()
                 for state in (LOW, LOADED)}
        records, metadata = [], []
        for source, target in ((LOW, LOADED), (LOADED, LOW), (LOW, LOW), (LOADED, LOADED)):
            for _ in range(PAIR_COUNT):
                left = int(rng.choice(pools[source]))
                right = int(rng.choice(pools[target][pools[target] != left]))
                values, offset, mismatch = phase_aligned_splice(raw[rows_of[left]], raw[rows_of[right]])
                records.append(values)
                metadata.append(dict(method="splice", direction=f"{source}→{target}", source_state=source,
                                     control=source == target, ramp_rows=0, source_record=left, target_record=right,
                                     offset=offset, phase_mismatch_deg=mismatch,
                                     amp_ratio=float(indexed.loc[right, "amp06"] / indexed.loc[left, "amp06"])))
        for source, target in ((LOW, LOADED), (LOADED, LOW)):
            gains = gain_up if source == LOW else 1 / gain_up
            for ramp_rows in (1, 10, 20):
                for record in pools[source]:
                    records.append(gain_transition(raw[rows_of[record]], gains, ramp_rows))
                    metadata.append(dict(method="gain", direction=f"{source}→{target}", source_state=source,
                                         control=False, ramp_rows=ramp_rows, source_record=int(record), target_record=int(record),
                                         offset=0, phase_mismatch_deg=0.0, amp_ratio=float(gains[2])))
        meta = pd.DataFrame(metadata)
        frame = _synthetic_frame(records)
        for alpha in alphas:
            prediction = model.predict(frame, alpha)
            if prediction.record_id.nunique() != len(meta):
                raise AssertionError("합성 기록과 추론 기록의 경계 불일치")
            alarm = prediction.alarm.to_numpy(bool).reshape(-1, 50)
            reason = prediction.reason.to_numpy().reshape(-1, 50)
            evaluated = meta.assign(pre=alarm[:, :SPLICE_ROW].any(axis=1), post=alarm[:, SPLICE_ROW:].any(axis=1),
                                    post2s=alarm[:, SPLICE_ROW:SPLICE_ROW + 20].any(axis=1))
            evaluated["first_reason"] = [str(reason[i, SPLICE_ROW + np.flatnonzero(a[SPLICE_ROW:])[0]]) if a[SPLICE_ROW:].any() else ""
                                         for i, a in enumerate(alarm)]

            def summarize(group, method, direction, ramp_rows, stratum):
                n = len(group)
                counts = group.loc[group.post, "first_reason"].value_counts().sort_index().to_dict()
                output.append(dict(split=sid, alpha=alpha, method=method, direction=direction, ramp_rows=ramp_rows,
                                   stratum=stratum, records=n, source_records=int(group.source_record.nunique()),
                                   target_records=int(group.target_record.nunique()), pre_alerted=int(group.pre.sum()),
                                   post_alerted=int(group.post.sum()), post2s_alerted=int(group.post2s.sum()),
                                   post_rate=float(group.post.mean()) if n else np.nan,
                                   post2s_rate=float(group.post2s.mean()) if n else np.nan,
                                   phase_mismatch_median_deg=float(group.phase_mismatch_deg.median()) if n else np.nan,
                                   first_post_reasons=json.dumps(counts, ensure_ascii=False, sort_keys=True),
                                   gain_AI0=float(gain_up[0]), gain_AI1=float(gain_up[1]), gain_current=float(gain_up[2]),
                                   seed=TRANSITION_SEED,
                                   note="사후 스트레스·가설. 동일 원기록 반복 사용, 실제 전환 속도 미관측. 이득 열은 저수준→부하 비(역방향은 역수)"))

            for (method, direction, ramp_rows), group in evaluated.groupby(["method", "direction", "ramp_rows"], sort=False):
                summarize(group, method, direction, int(ramp_rows), "all")
            controls = evaluated[evaluated.control].copy()
            symmetric_ratio = np.exp(np.abs(np.log(controls.amp_ratio)))
            labels = ("<1.1", "1.1~1.3", "1.3~1.6", "≥1.6")
            controls["ratio_bin"] = pd.cut(symmetric_ratio, [1, 1.1, 1.3, 1.6, np.inf], right=False, labels=labels)
            for label in labels:
                summarize(controls[controls.ratio_bin == label], "splice_control", "같은 상태", 0, label)
    table = pd.DataFrame(output)
    table.attrs["note"] = ("사후 스트레스 시험(현장 정상 전환 경보율 아님). 같은 평가 구간 50행 기록을 25행에서 전류 0.6 Hz 위상과 평균에 맞춰 잇기 "
                           "200쌍/조건, 전류 위상 오프셋 0~16. 같은 상태 대조에는 진동 위상 이음매도 남는다. 이득은 전체 정상의 상태별 중앙값 비로 "
                           "계단·10행·20행 경사를 적용하며 각 평가 원기록을 한 번씩 쓴다. 평가 데이터와 반복 원기록을 공유한다. 모델·문턱 불변")
    return table


def jitter_stress(normal, segments, models, test_starts, sine_fit, min_len=17, alpha=.01):
    """표본화 시각 흔들림(지터) 민감도. 정상 평가 기록(길이 ≥ min_len)마다 전류 사인(최적 격자 주파수)과 상수를 적합하고
    잔차는 그대로 둔 채, 사인 위상에 2π·(원 주파수)·δt(δt ~ N(0, σ), 표본마다 독립)를 더한다. 진동은 그대로다.

    원 주파수·흔들림 모양은 가정이다(시각 열은 명목값이라 실제 흔들림을 잴 수 없다). 경보율은 가정별 민감도이며 현장 오경보율이 아니다.
    """
    current = SENSORS[2]
    output = []
    for sid, model in models.items():
        test = normal[segments >= test_starts[sid]].reset_index(drop=True)
        seg = segments[segments >= test_starts[sid]]
        x0 = test[current].to_numpy(float)
        lengths = pd.Series(seg).value_counts()
        fits = {}
        for s in sorted(lengths[lengths >= min_len].index):
            idx = np.flatnonzero(seg == s)
            frequency = sine_fit(x0[idx])[0]
            coef = tone_coefficients(x0[idx], frequency)
            fits[s] = (idx, frequency, coef, x0[idx] - tone_design(len(idx), frequency) @ coef)
        keep = np.isin(seg, list(fits))
        for frequency_hz, sigma_ms in JITTER_CONDITIONS:
            rng = np.random.default_rng(JITTER_SEED)
            repeats = JITTER_REPEATS if sigma_ms > 0 else 1
            level1 = level2 = total = 0
            first = {"magnitude": 0, "waveform": 0, "dynamics": 0}
            r2, fitted_frequency = [], []
            for _ in range(repeats):
                x = x0.copy()
                for s, (idx, f, coef, residual) in fits.items():
                    phase = 2 * np.pi * f * np.arange(len(idx)) * .1
                    if sigma_ms > 0:
                        phase = phase + 2 * np.pi * frequency_hz * rng.normal(0, sigma_ms / 1e3, len(idx))
                    x[idx] = coef[0] * np.cos(phase) + coef[1] * np.sin(phase) + coef[2] + residual
                    frequency_fit, r2_fit = sine_fit(x[idx])[:2]
                    r2.append(r2_fit); fitted_frequency.append(frequency_fit)
                frame = test.copy()
                frame[current] = x
                prediction = model.predict(frame, alpha)
                prediction = prediction[keep].assign(record=seg[keep])
                alarms = prediction.groupby("record").alarm.sum()
                level1 += int((alarms >= 1).sum()); level2 += int((alarms >= 2).sum()); total += len(alarms)
                for _, rows in prediction[prediction.alarm.eq(1)].groupby("record"):
                    row = rows.iloc[0]
                    first[max(row.reason.split("+"), key=lambda c: row[f"g_{c}"])] += 1
            output.append(dict(split=sid, alpha=alpha, source_frequency_hz=frequency_hz if frequency_hz else np.nan, jitter_rms_ms=sigma_ms,
                               repeats=repeats, records=len(fits), record_trials=total, level1_alerted=level1, level2_alerted=level2,
                               level1_rate=level1 / total, level2_rate=level2 / total, sine_r2_median=float(np.median(r2)),
                               fit_frequency_median=float(np.median(fitted_frequency)),
                               fit_frequency_near_06_share=float(np.mean(np.abs(np.asarray(fitted_frequency) - .6) <= .05)),
                               first_magnitude=first["magnitude"], first_waveform=first["waveform"], first_dynamics=first["dynamics"],
                               seed=JITTER_SEED))
    table = pd.DataFrame(output)
    table.attrs["note"] = ("사후 스트레스·가설. 앨리어싱 가설 아래 표본화 시각 흔들림이 동결 v2 정상 경보에 주는 영향. 원 주파수·흔들림 모양(표본마다 독립 가우스)은 "
                           "가정이고 시각 열은 명목값이라 실제 흔들림을 잴 수 없다. 전류 사인 위상만 바꾸고 잔차·진동은 그대로 둔다. 모델·문턱 불변. "
                           "level*_rate는 기록 단위 경보 비율이다(사건 단위 알림 수가 아니다). fit_frequency_*는 흔들린 기록의 최적 사인 주파수로, "
                           "이상 파일(class_differences.csv의 적합 주파수 행)과 비교한다")
    return table


def transition_observation_power(normal, segments, states, repeats=4):
    """17행 창 진폭비 >1.3의 계단 전환 검정력. 난수 0, 기록마다 4위치.

    무작위 시각/20.5초당 두 전환은 가정이다. 전체 평균 검정력 곱의 근사와
    기록 길이별 가로지름 확률을 곱한 기대 탐지를 함께 반환한다.
    """
    rng = np.random.default_rng(POWER_SEED)
    med = states.groupby("state").amp06.median()
    values = normal.AI2_Current.to_numpy(float)
    design_inverse = np.linalg.pinv(tone_design(17, .6))
    per_record = []
    for row in states.itertuples():
        x = values[segments == row.record]
        gain = float(med[LOADED] / med[LOW]) if row.state == LOW else float(med[LOW] / med[LOADED])
        detected = 0
        for _ in range(repeats):
            at = int(rng.integers(1, len(x)))
            y = x.copy()
            y[at:] = x.mean() + gain * (x[at:] - x.mean())
            windows = np.lib.stride_tricks.sliding_window_view(y, 17)
            coef = windows @ design_inverse.T
            amplitudes = np.hypot(coef[:, 0], coef[:, 1])
            detected += amplitudes.max() / amplitudes.min() > 1.3
        crossing = min(1.0, 2 * (len(x) - 1) * .1 / 20.5)
        per_record.append(dict(record=row.record, length=len(x), power=detected / repeats, crossing=crossing))
    sample = pd.DataFrame(per_record)
    return dict(records=len(sample), repeats=repeats, power=float(sample.power.mean()),
                long_record_power=float(sample.loc[sample.length >= 40, "power"].mean()),
                expected_crossing=float(sample.crossing.sum()), crossing_mean=float(sample.crossing.mean()),
                expected_detected_approx=float(sample.crossing.sum() * sample.power.mean()),
                expected_detected_length_weighted=float((sample.crossing * sample.power).sum()))


def vibration_tones(raw, segments):
    """50행 기록별 좁은 대역·조화 적합과 Hann 주기도표(0.02 Hz 격자).

    주파수 격자 보간은 실제 분해능(약 0.2 Hz)을 높이지 않는다. 이상 5기록의
    0.4 Hz 아래 성분은 2주기 미만이므로 주기 판정 대신 느린 흐름으로 읽는다.
    """
    n, dt = 50, .1
    grid_cache = {}
    for f0, span in ((.6, .1), (1.8, .15), (3.6, .15)):
        grid = np.linspace(f0 - span, f0 + span, 301)
        design = np.array([tone_design(n, f, dt) for f in grid])
        grid_cache[f0] = (grid, design, np.linalg.pinv(design))

    def best_frequency(x, f0):
        grid, design, inverse = grid_cache[f0]
        coef = np.einsum("fij,j->fi", inverse, x)
        fitted = np.einsum("fij,fj->fi", design, coef)
        index = int(np.argmin(((x - fitted) ** 2).sum(axis=1)))

        def residual(frequency):
            mat = tone_design(n, frequency, dt)
            return float(np.square(x - mat @ np.linalg.lstsq(mat, x, rcond=None)[0]).sum())

        fit = optimize.minimize_scalar(residual, bounds=(grid[max(0, index - 1)], grid[min(len(grid) - 1, index + 1)]), method="bounded")
        return float(fit.x)

    harmonic = np.column_stack([np.ones(n)] + [tone_design(n, .6 * h, dt)[:, c] for h in range(1, 9) for c in (0, 1)])
    projection = harmonic @ np.linalg.pinv(harmonic)
    frequencies = np.fft.rfftfreq(500, dt)
    rows = []
    for name, frame in raw.items():
        values = frame[list(SENSORS)].to_numpy(float)
        for record in np.unique(segments[name]):
            idx = np.flatnonzero(segments[name] == record)
            if len(idx) < n:
                continue
            x = values[idx[:n]]
            current = tone_coefficients(x[:, 2], .6)
            current_phase = np.arctan2(-current[1], current[0])
            current_frequency = best_frequency(x[:, 2], .6)
            for channel, center, multiple in ((0, 3.6, 6), (1, 1.8, 3)):
                vibration = x[:, channel]
                fitted_tone = tone_coefficients(vibration, center)
                amplitude = float(np.hypot(*fitted_tone[:2]))
                power = np.abs(np.fft.rfft((vibration - vibration.mean()) * np.hanning(n), n=500)) ** 2
                harmonic_r2 = 1 - np.square(vibration - projection @ vibration).sum() / np.square(vibration - vibration.mean()).sum()
                rows.append(dict(file=name, record=int(record), sensor=SENSORS[channel], length=n,
                                 current_frequency_hz=current_frequency, current_amplitude=float(np.hypot(*current[:2])),
                                 tone_frequency_hz=best_frequency(vibration - vibration.mean(), center), fitted_tone_hz=center,
                                 tone_amplitude=amplitude, harmonic_r2=float(harmonic_r2),
                                 tone_rms_over_sd=float(amplitude / np.sqrt(2) / vibration.std()),
                                 phase_difference=float((np.arctan2(-fitted_tone[1], fitted_tone[0]) - multiple * current_phase) % (2 * np.pi)),
                                 spectral_peak_hz=float(frequencies[1:][np.argmax(power[1:])]),
                                 note="사후 진단·가설. 5초 기록의 주파수 격자 0.02 Hz는 분해능 향상이 아니다. 0.4 Hz 미만은 느린 흐름"))
    table = pd.DataFrame(rows)
    table.attrs["note"] = "50행 정상 202·이상 5기록의 센서별 진단. 고정 1.8/3.6 Hz 성분, 0.6 Hz 1~8배 조화, Hann 주기도표. 위상차는 전류의 3/6배에 대한 값. 인과·물리 원천을 확정하지 않는다"
    return table


def tone_summary(records):
    return dict(records_50rows=len(records), tone_frequency_hz_median=float(records.tone_frequency_hz.median()),
                harmonic_r2_median=float(records.harmonic_r2.median()), tone_rms_over_sd_median=float(records.tone_rms_over_sd.median()),
                tone_amp_current_spearman=float(stats.spearmanr(records.tone_amplitude, records.current_amplitude).statistic),
                phase_lock_R=float(np.abs(np.exp(1j * records.phase_difference).mean())),
                random_phase_R_scale=float(1 / np.sqrt(len(records))),
                spectral_peak_hz_q25=float(records.spectral_peak_hz.quantile(.25)),
                spectral_peak_hz_median=float(records.spectral_peak_hz.median()),
                spectral_peak_hz_q75=float(records.spectral_peak_hz.quantile(.75)),
                spectral_peaks_hz=";".join(f"{r.record}:{r.spectral_peak_hz:.2f}" for r in records.itertuples()) if records.file.iloc[0] == "abnormal" else "")
