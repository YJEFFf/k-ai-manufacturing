"""검수 R1~R4·R6의 반례를 회귀 검사로 옮긴 것 (yejun/analysis/press_implementation_review/review_checks.py 기준)."""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import verify
from press.field import persistence_score
from press.lstm_ae import config_key


def _mini_outputs(tmp_path: Path) -> Path:
    out = tmp_path / "outputs"
    exp = out / "expected"
    exp.mkdir(parents=True)
    a = pd.DataFrame({"model": ["combined_w8", "lstm20"], "threshold": [1.5, np.inf], "f1_all_rows": [0.9, 0.3], "alarm": [1, 0]})
    a.to_csv(out / "t.csv", index=False); a.to_csv(exp / "t.csv", index=False)
    d = {"structure": {"normal": {"rows": 20000}}, "path": "/x"}
    (out / "diagnosis.json").write_text(json.dumps(d)); (exp / "diagnosis.json").write_text(json.dumps(dict(d, path="/y")))
    man = {"inputs": {"files": {"normal": {"sha256": "h"}}}, "environment": {"platform": "p"}, "code_sha256": "c" * 64}
    (out / "manifest.json").write_text(json.dumps(man)); (exp / "manifest.json").write_text(json.dumps(man))
    checks = {k: True for k in verify.REQUIRED_CHECKS}
    (out / "checks.json").write_text(json.dumps(checks)); (exp / "checks.json").write_text(json.dumps(checks))
    return out


def test_verify_passes_on_identical(tmp_path):
    out = _mini_outputs(tmp_path)
    assert verify.main(["--out", str(out)]) == 0


def test_verify_fails_on_missing_result(tmp_path):            # R1: 결과 파일 누락
    out = _mini_outputs(tmp_path)
    (out / "t.csv").unlink()
    assert verify.main(["--out", str(out)]) == 1


def test_verify_fails_on_corrupted_diagnosis(tmp_path):       # R1: 진단 수치 변조
    out = _mini_outputs(tmp_path)
    d = json.loads((out / "diagnosis.json").read_text()); d["structure"]["normal"]["rows"] = -123
    (out / "diagnosis.json").write_text(json.dumps(d))
    assert verify.main(["--out", str(out)]) == 1


def test_verify_inf_vs_nan_differs(tmp_path):                 # R1: ±inf와 NaN 구분
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    pd.DataFrame({"threshold": [np.inf]}).to_csv(a, index=False)
    pd.DataFrame({"threshold": [np.nan]}).to_csv(b, index=False)
    assert not verify.compare_csv(a, b)["ok"]
    pd.DataFrame({"threshold": [np.inf]}).to_csv(b, index=False)
    assert verify.compare_csv(a, b)["ok"]


def test_verify_fails_on_required_check(tmp_path):            # R1: 필수 검사 false
    out = _mini_outputs(tmp_path)
    c = json.loads((out / "checks.json").read_text()); c["conformal_mc_within_4se"] = False
    (out / "checks.json").write_text(json.dumps(c))
    assert verify.main(["--out", str(out)]) == 1
    assert verify.main(["--out", str(out), "--freeze"]) == 2   # 동결도 거부


def test_verify_tolerance_per_row(tmp_path):                  # 파일 단위가 아니라 행(model)별 허용오차
    out = _mini_outputs(tmp_path)
    a = pd.read_csv(out / "t.csv"); a.loc[a.model == "combined_w8", "f1_all_rows"] += 1e-5
    a.to_csv(out / "t.csv", index=False)
    assert verify.main(["--out", str(out)]) == 1
    a = pd.read_csv(out / "expected" / "t.csv"); a.loc[a.model == "lstm20", "f1_all_rows"] += 1e-5
    a.to_csv(out / "t.csv", index=False)
    assert verify.main(["--out", str(out)]) == 0


def test_verify_ignores_runtime_metadata(tmp_path):           # R6: 실행 메타데이터는 비교하지 않음
    out = _mini_outputs(tmp_path)
    g = {"f1": 0.61, "tn": 10, "cached": False, "train_seconds": 1.0}
    (out / "expected" / "g.json").write_text(json.dumps(dict(g, cached=True, train_seconds=99.0)))
    (out / "g.json").write_text(json.dumps(g))
    assert verify.main(["--out", str(out)]) == 0
    (out / "g.json").write_text(json.dumps(dict(g, f1=0.62)))
    assert verify.main(["--out", str(out)]) == 1


def test_persistence_missing_resets_window():                  # R3
    score = np.array([10.0, 10.0, 10.0, np.nan, 0.0, 0.0, 0.0])
    got = persistence_score(score, np.zeros(7, int), 2, 3)
    want = np.array([np.nan, np.nan, 10.0, np.nan, np.nan, np.nan, 0.0])
    assert np.allclose(got, want, equal_nan=True)


def test_lstm_cache_key_depends_on_code_and_config():          # R2
    cfg = {"protocol": "common_lstm20", "epochs": 1}
    assert config_key(cfg, code="aaaa") != config_key(cfg, code="bbbb")
    assert config_key(cfg, code="aaaa") == config_key(dict(cfg), code="aaaa")
    assert config_key(dict(cfg, scaler_mean=[0.1]), code="aaaa") != config_key(dict(cfg, scaler_mean=[0.2]), code="aaaa")
