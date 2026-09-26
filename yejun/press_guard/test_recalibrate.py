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
    report = json.loads((tmp_path / "site_report.json").read_text())
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
    report = json.loads((tmp_path / "z_report.json").read_text())
    assert not report["passed"] and not report["model_saved"] and not out.exists()
