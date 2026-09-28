"""오류 분석의 층화·짝지은 재표집과 운영 추정의 선택 자료 중첩 회귀 검사."""
import numpy as np
import pandas as pd
import pytest

from insights import _bh_adjust, _block_amplitude_stats, _cmh_statistics, _paired_spearman_bootstrap, expected_effect


def test_cmh_continuity_correction_matches_reference():
    """각 층 주변 합으로 직접 구할 수 있는 표. statsmodels와 독립 대조한 참조값."""
    tables = [np.array([[4, 6], [2, 8]]), np.array([[2, 8], [1, 9]])]
    odds, statistic, pvalue = _cmh_statistics(tables)
    assert odds == pytest.approx(2.5)
    assert statistic == pytest.approx(0.5629629629629629)
    assert pvalue == pytest.approx(0.4530688771897964)


def test_block_permutation_does_not_turn_time_confounding_into_effect():
    """노출이 블록과 완전히 겹치면 모든 경보가 노출군이어도 블록 안에서는 효과를 식별할 수 없다."""
    frame = pd.DataFrame({"absolute_record": [0, 1, 2, 3, 60, 61, 62, 63],
                          "false_alarm": [1, 1, 0, 0, 0, 0, 0, 0]})
    result = _block_amplitude_stats(frame, [True] * 4 + [False] * 4, permutations=1000)
    assert result["permutation_p_greater"] == 1
    assert result["cmh_informative_blocks"] == 0
    assert np.isnan(result["cmh_p"])


def test_bh_counts_only_finite_tests_and_preserves_input_order():
    p = [.01, .04, .03, .002, np.nan]
    np.testing.assert_allclose(_bh_adjust(p), [.02, .04, .04, .008, np.nan], equal_nan=True)


def test_interaction_bootstrap_resamples_the_same_units_for_both_outcomes():
    """두 족 탐지가 같으면 동일 단위 재표집의 상관 차이는 모든 추출에서 0이어야 한다."""
    amp = np.arange(12, dtype=float)
    detection = np.array([0, .2, .2, .6, 1, .4, 1, 0, .2, 1, 1, .4])
    result = _paired_spearman_bootstrap(amp, detection, detection, repeats=200)
    assert result["interaction_bootstrap_valid"] == 200
    assert result["interaction_rho_difference"] == 0
    assert result["interaction_ci_low"] == result["interaction_ci_high"] == 0


def test_primary_workload_estimate_excludes_seen_evaluation_windows():
    """같은 보정값 제거만으로 독립 검증이라 부르지 않는다. 기록 570이 든 폴드는 민감도에만 든다."""
    rows = []
    settings = [("frozen_B", "420~599", .01, 3, 0),
                ("frozen_B", "420~599", .03, 5, 2),
                ("frozen_B", "420~599", .05, 7, 3),
                ("rolling_test_300_359", "300~359", .05, 5, 1),
                ("rolling_test_360_419", "360~419", .05, 2, 0),
                ("rolling_test_540_599", "540~599", .05, 2, 0)]
    for model, window, alpha, first, second in settings:
        for level, count in ((1, first), (2, second)):
            rows.append(dict(model=model, normal_window=window, independent=True, alpha=alpha, level=level,
                             normal_alerted_segments=count, nominal_alerts_per_8h_elapsed=30,
                             alerts_per_8h_elapsed=count, upper95_alerts_per_8h_elapsed=10, delay_median_s=.2))
    injection = pd.DataFrame([dict(split="B", alpha=.01, family="vib_noise", level2_detect_2s=.5)])
    result = expected_effect(pd.DataFrame(rows), injection)
    primary = result[result.estimate_role.eq("primary")]
    assert set(primary.ratio_numerator) == {1}
    assert set(primary.ratio_denominator) == {7}
    assert not primary.evaluation_overlaps_rule_selection.any()
    assert primary.rule_selected_post_hoc.all()
    sensitivity = result[result.alert_scenario.eq("민감도(겹치는 폴드 포함)")]
    assert set(sensitivity.ratio_denominator) == {9}
    assert sensitivity.evaluation_overlaps_rule_selection.all()
    assert sensitivity.level2_basis.str.contains("570").all()
    frozen = result[result.alert_scenario.isin(["민감도(동결 B α3%)", "민감도(동결 B α5%)"])]
    assert set(zip(frozen.ratio_numerator, frozen.ratio_denominator)) == {(2, 5), (3, 7)}
