"""검수 R1~R4·R6의 반례를 회귀 검사로 옮긴 것 (yejun/analysis/press_implementation_review/review_checks.py 기준)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import verify
from press.field import persistence_score
from press.validation import (SPLIT_CHECKS, artifact_names, check_required, code_sha256, file_hash, output_names,
                              required_check_names, result_names, run_fingerprint)


def _stamp(out: Path):
    p = out / "manifest.json"
    man = json.loads(p.read_text(encoding="utf-8"))
    steps = int(man["args"]["steps"])
    art = out.parent / "artifacts"
    man["outputs"] = {n: file_hash(out / n) for n in output_names(steps) | {"checks.json"} if (out / n).is_file()}
    man["artifacts"] = {n: file_hash(art / n) for n in artifact_names(steps) if (art / n).is_file()}
    p.write_text(json.dumps(man), encoding="utf-8")


def _mini_outputs(tmp_path: Path, steps=1) -> Path:
    out = tmp_path / "outputs"
    exp = out / "expected"
    exp.mkdir(parents=True)
    a = pd.DataFrame({"model": ["combined_w8", "lstm20"], "threshold": [1.5, np.inf], "f1_all_rows": [0.9, 0.3], "alarm": [1, 0]})
    for name in output_names(steps):
        if name.endswith(".csv"):
            a.to_csv(out / name, index=False)
        elif name.endswith(".json"):
            (out / name).write_text(json.dumps({"structure": {"normal": {"rows": 20000}}, "path": "/x"}), encoding="utf-8")
        else:
            (out / name).write_text("test artifact", encoding="utf-8")
    art = out.parent / "artifacts"; art.mkdir()
    for name in artifact_names(steps):
        (art / name).write_text(json.dumps({"model_id": name, "state": {"u": 1.0}}), encoding="utf-8")
    man = {"inputs": {"verified": True, "files": {"normal": {"sha256": "h"}}},
           "environment": {"platform": "p"}, "code_sha256": code_sha256(), "args": {"steps": str(steps)}}
    (out / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    checks = {k: True for k in required_check_names(steps)}
    checks.update(steps_run=steps, required_checks_ok=True, required_checks_failed=[])
    if steps >= 2:
        checks["step2"] = {s: {k: True for k in SPLIT_CHECKS} for s in ("A", "B")}
    (out / "checks.json").write_text(json.dumps(checks), encoding="utf-8")
    _stamp(out)
    for name in result_names(steps) | {"checks.json", "manifest.json"}:
        shutil.copy2(out / name, exp / name)
    return out


def test_verify_passes_on_identical(tmp_path):
    out = _mini_outputs(tmp_path)
    assert verify.main(["--out", str(out)]) == 0


def test_verify_fails_on_missing_result(tmp_path):            # R1: 결과 파일 누락
    out = _mini_outputs(tmp_path)
    (out / "waveform_segments.csv").unlink()
    assert verify.main(["--out", str(out)]) == 1


def test_verify_fails_on_corrupted_diagnosis(tmp_path):       # R1: 진단 수치 변조
    out = _mini_outputs(tmp_path)
    d = json.loads((out / "diagnosis.json").read_text(encoding="utf-8")); d["structure"]["normal"]["rows"] = -123
    (out / "diagnosis.json").write_text(json.dumps(d), encoding="utf-8")
    assert verify.main(["--out", str(out)]) == 1


def test_verify_inf_vs_nan_differs(tmp_path):                 # R1: ±inf와 NaN 구분
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    pd.DataFrame({"threshold": [np.inf]}).to_csv(a, index=False)
    pd.DataFrame({"threshold": [np.nan]}).to_csv(b, index=False)
    assert not verify.compare_csv(a, b)["ok"]
    pd.DataFrame({"threshold": [np.inf]}).to_csv(b, index=False)
    assert verify.compare_csv(a, b)["ok"]


def test_verify_fails_on_required_check(tmp_path):            # R1: 필수 검사 false
    out = _mini_outputs(tmp_path, steps=5)
    c = json.loads((out / "checks.json").read_text(encoding="utf-8")); c["conformal_mc_within_4se"] = False
    (out / "checks.json").write_text(json.dumps(c), encoding="utf-8")
    _stamp(out)
    assert verify.main(["--out", str(out)]) == 1
    assert verify.main(["--out", str(out), "--freeze"]) == 2   # 동결도 거부


def test_verify_tolerance_per_row(tmp_path):                  # 파일 단위가 아니라 행(model)별 허용오차
    out = _mini_outputs(tmp_path)
    path = out / "waveform_segments.csv"; expected = out / "expected" / path.name
    a = pd.read_csv(path); a.loc[a.model == "combined_w8", "f1_all_rows"] += 1e-5
    a.to_csv(path, index=False)
    assert not verify.compare_csv(path, expected)["ok"]
    a = pd.read_csv(expected); a.loc[a.model == "lstm20", "f1_all_rows"] += 1e-5
    a.to_csv(path, index=False)
    assert verify.compare_csv(path, expected)["ok"]


def test_verify_ignores_runtime_metadata(tmp_path):           # R6: 실행 메타데이터는 비교하지 않음
    out = _mini_outputs(tmp_path)
    g = {"f1": 0.61, "tn": 10, "cached": False, "train_seconds": 1.0}
    (out / "expected" / "g.json").write_text(json.dumps(dict(g, cached=True, train_seconds=99.0)), encoding="utf-8")
    (out / "g.json").write_text(json.dumps(g), encoding="utf-8")
    assert verify.compare_json(out / "g.json", out / "expected" / "g.json")["ok"]
    (out / "g.json").write_text(json.dumps(dict(g, f1=0.62)), encoding="utf-8")
    assert not verify.compare_json(out / "g.json", out / "expected" / "g.json")["ok"]


@pytest.mark.parametrize("missing", ["conformal_mc_within_4se", "required_checks_ok", "all"])
def test_missing_checks_cannot_pass_or_freeze(tmp_path, missing):
    out = _mini_outputs(tmp_path, steps=5)
    checks = json.loads((out / "checks.json").read_text(encoding="utf-8"))
    if missing == "all":
        checks = {"steps_run": 5}
    else:
        checks.pop(missing)
    (out / "checks.json").write_text(json.dumps(checks), encoding="utf-8")
    _stamp(out)  # 새 실행이 불완전한 검사를 기록한 경우도 거부해야 한다.
    assert verify.main(["--out", str(out)]) == 1
    assert verify.main(["--out", str(out), "--freeze"]) == 2


def test_freeze_requires_complete_outputs_and_preserves_old_snapshot(tmp_path):
    out = _mini_outputs(tmp_path, steps=5)
    before = {p.name: p.read_bytes() for p in (out / "expected").iterdir()}
    (out / "model_comparison_all.csv").unlink()
    _stamp(out)  # 불완전한 목록만 담은 manifest도 완료 근거가 아니다.
    assert verify.main(["--out", str(out), "--freeze"]) == 2
    assert before == {p.name: p.read_bytes() for p in (out / "expected").iterdir()}
    (out / "expected" / "model_comparison_all.csv").unlink()
    assert verify.main(["--out", str(out)]) == 1


@pytest.mark.parametrize("name", ["predictions_A.csv", "numbers.json"])
def test_changed_unfrozen_outputs_fail_integrity(tmp_path, name):
    out = _mini_outputs(tmp_path, steps=5)
    (out / name).write_text("tampered", encoding="utf-8")
    assert verify.main(["--out", str(out)]) == 1


def test_code_changed_after_run_fails_verify_and_freeze(tmp_path):   # 실행 후 코드 변경 → 산출물은 이 코드의 결과가 아니다
    out = _mini_outputs(tmp_path, steps=5)
    assert verify.main(["--out", str(out)]) == 0
    p = out / "manifest.json"; man = json.loads(p.read_text(encoding="utf-8")); man["code_sha256"] = "c" * 64
    p.write_text(json.dumps(man), encoding="utf-8")
    assert verify.main(["--out", str(out)]) == 1
    assert verify.main(["--out", str(out), "--freeze"]) == 2


@pytest.mark.parametrize("how", ["tamper", "delete"])
def test_changed_artifact_fails_integrity(tmp_path, how):        # predict.py가 읽는 artifact도 실행 시 해시와 대조
    out = _mini_outputs(tmp_path, steps=2)
    assert verify.main(["--out", str(out)]) == 0
    art = tmp_path / "artifacts" / "main_A.json"
    art.write_text("tampered", encoding="utf-8") if how == "tamper" else art.unlink()
    assert verify.main(["--out", str(out)]) == 1
    assert verify.main(["--out", str(out), "--freeze"]) == 2


def test_partial_run_needs_explicit_comparison_scope(tmp_path):
    full = _mini_outputs(tmp_path / "full", steps=5)
    partial = _mini_outputs(tmp_path / "partial", steps=1)
    shutil.rmtree(partial / "expected")
    shutil.copytree(full / "expected", partial / "expected")
    assert verify.main(["--out", str(partial)]) == 1
    assert verify.main(["--out", str(partial), "--steps", "1"]) == 0


def test_lstm_json_tolerance_and_exact_counts(tmp_path):
    a, b = tmp_path / "lstm_guidebook_reproduction.json", tmp_path / "expected.json"
    b.write_text(json.dumps({"f1": 0.61, "tp": 10}), encoding="utf-8")
    a.write_text(json.dumps({"f1": 0.6101, "tp": 10}), encoding="utf-8")
    assert verify.compare_json(a, b)["ok"]
    a.write_text(json.dumps({"f1": 0.6101, "tp": 11}), encoding="utf-8")
    assert not verify.compare_json(a, b)["ok"]
    a.write_text(json.dumps({"f1": 0.6101, "tp": 10.0001}), encoding="utf-8")
    assert not verify.compare_json(a, b)["ok"]


def test_run_identity_distinguishes_configuration_inputs_and_environment():
    args, inputs, env = {"seed": 0, "preprocess": "matched", "out": "a"}, {"files": {"normal": {"sha256": "h"}}}, {"torch": "t"}
    key = run_fingerprint("code", args, inputs, env)
    assert run_fingerprint("code", dict(args, seed=1), inputs, env) != key
    assert run_fingerprint("code", args, {"files": {"normal": {"sha256": "changed"}}}, env) != key
    assert run_fingerprint("code", args, inputs, {"torch": "changed"}) != key
    assert run_fingerprint("code", dict(args, out="b"), inputs, env) == key


def test_runner_gate_requires_individual_checks():
    checks = {k: True for k in required_check_names(2)}
    checks["step2"] = {s: {k: True for k in SPLIT_CHECKS} for s in ("A", "B")}
    checks["step2"]["B"].pop("prediction_alarm_counts_equal_table")
    assert "step2.B.prediction_alarm_counts_equal_table" in check_required(checks, 2, summary=False)
    checks["input_hash_ok"] = False
    assert "input_hash_ok" not in check_required(checks, 2, verify_inputs=False, summary=False)


@pytest.mark.parametrize("run_status", [0, 7])
def test_clean_repro_propagates_failure_and_declares_scope(tmp_path, run_status):
    pkg = tmp_path / "repo" / "yejun" / "press_submission"
    (pkg / "tools").mkdir(parents=True)
    (pkg / "data").mkdir()
    (pkg / "outputs" / "expected").mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "tools" / "clean_repro.sh"
    script = pkg / "tools" / source.name
    shutil.copy2(source, script)
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    fake_git = bin_dir / "git"
    fake_git.write_text('#!/bin/bash\nif [[ "$1" == clone ]]; then mkdir -p "$4/yejun/press_submission/outputs/expected"; '
                        'echo committed > "$4/yejun/press_submission/outputs/expected/marker"; else echo test-head; fi\n', encoding="utf-8")
    fake_python = bin_dir / "python3"
    fake_python.write_text('#!/bin/bash\nif [[ "$1" == run_all.py ]]; then exit ' + str(run_status) + '; fi\n'
                           'printf "%s\\n" "$@" > "$VERIFY_CALL"; cat outputs/expected/marker >> "$VERIFY_CALL"\n', encoding="utf-8")
    fake_git.chmod(0o755); fake_python.chmod(0o755)
    scratch = tmp_path / "scratch"; scratch.mkdir()
    calls = tmp_path / "verify_call"
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"], TMPDIR=str(scratch), VERIFY_CALL=str(calls))
    if shutil.which("bash") is None:
        pytest.skip("bash가 없는 환경(Windows)에서는 clean_repro.sh를 시험하지 않는다")
    result = subprocess.run(["bash", str(script)], env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
    assert result.returncode == run_status, result.stdout + result.stderr
    if run_status:
        assert not calls.exists()
    else:
        assert calls.read_text(encoding="utf-8").splitlines()[-3:] == ["--steps", "3", "committed"]   # 클론에 커밋된 기대값을 쓴다


def test_persistence_missing_resets_window():                  # R3
    score = np.array([10.0, 10.0, 10.0, np.nan, 0.0, 0.0, 0.0])
    got = persistence_score(score, np.zeros(7, int), 2, 3)
    want = np.array([np.nan, np.nan, 10.0, np.nan, np.nan, np.nan, 0.0])
    assert np.allclose(got, want, equal_nan=True)


def test_lstm_cache_key_depends_on_code_and_config():          # R2
    pytest.importorskip("torch", reason="LSTM 캐시 키 검사는 torch가 있을 때만")
    from press.lstm_ae import config_key
    cfg = {"protocol": "common_lstm20", "epochs": 1}
    assert config_key(cfg, code="aaaa") != config_key(cfg, code="bbbb")
    assert config_key(cfg, code="aaaa") == config_key(dict(cfg), code="aaaa")
    assert config_key(dict(cfg, scaler_mean=[0.1]), code="aaaa") != config_key(dict(cfg, scaler_mean=[0.2]), code="aaaa")
