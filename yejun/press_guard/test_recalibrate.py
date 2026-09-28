"""recalibrate.py 계약: 단위 분할, α별 최소 보정 단위, 수락 검사 기록, 실패 시 저장 안 함."""
import json

import numpy as np
import pandas as pd
import pytest

import recalibrate
from model import GuardModel, D


@pytest.fixture(scope="module")
def normal_csv(tmp_path_factory):
    n, _ = D.load()[:2]
    path = tmp_path_factory.mktemp("recal") / "normal.csv"
    D.inputs_only(n[D.segments(n) < 480]).to_csv(path, index=False)
    return path


def test_recalibration_passes_and_saves(normal_csv, tmp_path):
    out = tmp_path / "site.json"
    assert recalibrate.main(["--normal", str(normal_csv), "--out", str(out)]) == 0
    report = json.loads((tmp_path / "site_report.json").read_text(encoding="utf-8"))
    assert report["passed"] and report["model_saved"] and report["units"] == dict(total=480, train=300, cal=120, holdout=60, min_cal_for_alpha=99)
    assert {c["name"].split(" ")[0] for c in report["checks"]} >= {"정상", "고장"} and len(report["checks"]) == 4
    model = GuardModel.load(out)
    assert len(model.cal) == 120 and model.state["split"] == "recalibrated"


def test_alpha_needs_enough_calibration_units(normal_csv, tmp_path):
    assert recalibrate.min_cal_units(.01) == 99 and recalibrate.min_cal_units(.05) == 19
    assert recalibrate.main(["--normal", str(normal_csv), "--out", str(tmp_path / "x.json"), "--cal-units", "50"]) == 2
    assert not (tmp_path / "x.json").exists()


def test_too_little_normal_data_is_refused(tmp_path):
    n, _ = D.load()[:2]
    path = tmp_path / "short.csv"
    D.inputs_only(n[D.segments(n) < 150]).to_csv(path, index=False)
    assert recalibrate.main(["--normal", str(path), "--out", str(tmp_path / "y.json")]) == 2


def test_failed_acceptance_does_not_save(normal_csv, tmp_path, monkeypatch):
    monkeypatch.setattr(recalibrate, "DETECT_RATE", 1.01)   # 통과할 수 없는 수락 기준
    out = tmp_path / "z.json"
    assert recalibrate.main(["--normal", str(normal_csv), "--out", str(out)]) == 1
    report = json.loads((tmp_path / "z_report.json").read_text(encoding="utf-8"))
    assert not report["passed"] and not report["model_saved"] and not out.exists()


def test_acceptance_limit_is_calibration_conditional():
    """수락 한도는 보정 조건부 Beta-Binomial 95백분위다(평가관 05 O7). α=5%·보정 120·수락 60에서 6→7, 1·3%는 2·4 그대로."""
    from scipy import stats
    from monitor import alert_limit, beta_params
    assert [alert_limit(a, 120, 60) for a in (.01, .03, .05)] == [2, 4, 7]
    for a in (.01, .03, .05):
        assert stats.betabinom.sf(alert_limit(a, 120, 60), 60, *beta_params(a, 120)) <= .05
    # 옛 이항 한도(6)는 α=5%에서 정상 보정을 5%보다 자주 거부했다
    assert stats.betabinom.sf(6, 60, *beta_params(.05, 120)) > .05


def test_report_records_power_and_budget(normal_csv, tmp_path):
    out = tmp_path / "b.json"
    assert recalibrate.main(["--normal", str(normal_csv), "--out", str(out), "--target-alerts-per-8h", "3"]) == 0
    report = json.loads((tmp_path / "b_report.json").read_text(encoding="utf-8"))
    a = report["checks"][0]
    assert a["limit"] == 2 and 0 < a["power_if_rate_multiplied"]["2x"] < a["power_if_rate_multiplied"]["3x"] < 1
    b = report["budget"]
    assert b["target_alerts_per_8h"] == 3 and not b["within_budget"] and b["calibration_units_required"] > 1000
    assert abs(b["nominal_alerts_per_8h"] - b["nominal_rate"] * b["units_per_elapsed_hour"] * 8) < 1e-9


def test_unconfirmed_cases_are_excluded_from_recalibration(normal_csv, tmp_path):
    """확인된 정상 구간만 재보정 자료로 쓴다: 정상 확인으로 닫히지 않은 건의 의심 시간창은 빠진다."""
    from monitor import exclude_unconfirmed
    frame = pd.read_csv(normal_csv)
    t = frame[D.TIME]
    outcomes = pd.DataFrame(dict(first_timestamp=[t.iloc[100], t.iloc[2000]], suspect_from=[t.iloc[90], t.iloc[1990]],
                                 suspect_to=[t.iloc[140], t.iloc[2040]], outcome=["정상 확인", ""]))
    kept, info = exclude_unconfirmed(frame, outcomes)
    assert info == dict(cases=2, unconfirmed_cases=1, rows_removed=51, rows_kept=len(frame) - 51)
    assert t.iloc[2000] not in set(kept[D.TIME]) and t.iloc[100] in set(kept[D.TIME])


def test_monitor_windows_require_normal_confirmation(normal_csv):
    """전류 이동·열화 점검 창은 결과가 비면 빠지고 정상 확인 뒤 남는다. 관측/변경 기록 창은 그대로 남는다."""
    from monitor import (exclude_unconfirmed_windows, ACTION_INSPECT_SHIFT, ACTION_INSPECT,
                         ACTION_RECALIBRATE, ACTION_OBSERVE)
    frame = pd.read_csv(normal_csv)
    starts, ends = [100, 200, 300, 400], [149, 249, 349, 449]
    windows = pd.DataFrame(dict(start=frame[D.TIME].iloc[starts].to_numpy(), end=frame[D.TIME].iloc[ends].to_numpy(),
                                recommended_action=[ACTION_INSPECT_SHIFT, ACTION_INSPECT, ACTION_RECALIBRATE, ACTION_OBSERVE]))
    kept, info = exclude_unconfirmed_windows(frame, windows)
    assert info["unconfirmed_windows"] == 2 and info["rows_removed"] == 100
    assert frame[D.TIME].iloc[100] not in set(kept[D.TIME]) and frame[D.TIME].iloc[300] in set(kept[D.TIME])
    windows["outcome"] = ["정상 확인", "보류", "", ""]
    kept, info = exclude_unconfirmed_windows(frame, windows)
    assert info["unconfirmed_windows"] == 1 and info["rows_removed"] == 50
    assert frame[D.TIME].iloc[100] in set(kept[D.TIME]) and frame[D.TIME].iloc[200] not in set(kept[D.TIME])
    windows["outcome"] = "정상 확인"
    kept, info = exclude_unconfirmed_windows(frame, windows)
    pd.testing.assert_frame_equal(kept, frame)
    assert info["rows_removed"] == 0
    windows.loc[0, "outcome"] = ""
    windows.loc[0, "start"] = "bad-time"
    with pytest.raises(ValueError, match="start/end"):
        exclude_unconfirmed_windows(frame, windows)


def test_windows_option_filters_before_fitting(normal_csv, tmp_path):
    """실제 CLI가 미확인 점검 창을 빼고 보고서에 제외 수를 남긴다."""
    from monitor import ACTION_INSPECT_SHIFT
    frame = pd.read_csv(normal_csv)
    seg = D.segments(frame)
    drop = frame[seg < 60]
    windows = tmp_path / "windows.csv"
    pd.DataFrame([dict(start=drop[D.TIME].iloc[0], end=drop[D.TIME].iloc[-1],
                       recommended_action=ACTION_INSPECT_SHIFT, outcome="")]).to_csv(windows, index=False)
    out = tmp_path / "filtered.json"
    assert recalibrate.main(["--normal", str(normal_csv), "--windows", str(windows), "--out", str(out)]) in (0, 1)
    report = json.loads((tmp_path / "filtered_report.json").read_text(encoding="utf-8"))
    assert report["units"]["total"] == 420
    assert report["excluded_by_windows"]["rows_removed"] == len(drop)
