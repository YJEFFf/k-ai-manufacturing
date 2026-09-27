"""보완 실험 재현 계약(R9)과 E2 캐시 키(R23)의 변조 검출. 실제 파일 대신 임시 복사본과 기록 해시를 바꾼다.

E2는 Git에서 뺀 UCI 원본(analysis/press_external/data/hydraulic.zip)이 있어야 검사할 수 있다. 없으면 E2 검사는 이유와 함께
건너뛴다(평가관 06 R6). 획득: python analysis/press_external/acquire.py"""
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

import contract
import uci_v2
from contract import EXPERIMENTS, HERE, manifest_name

# common.py가 press_guard를 import 경로 맨 앞에 넣으므로, 같은 이름의 press_guard/verify.py가 아니라 이 폴더의 verify.py를 파일 경로로 불러온다.
_spec = importlib.util.spec_from_file_location("supplement_verify", Path(__file__).with_name("verify.py"))
verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify)

UCI = EXPERIMENTS["E2"]["extra_inputs"]["uci_hydraulic_zip"]
HAS_UCI = UCI.is_file()
needs_uci = pytest.mark.skipif(not HAS_UCI, reason="UCI 원본 ZIP 없음(Git 제외 73 MB). python analysis/press_external/acquire.py로 받으면 검사한다")
AVAILABLE = [e for e in EXPERIMENTS if e != "E2" or HAS_UCI]


@pytest.fixture
def run_copy(tmp_path):
    for exp, spec in EXPERIMENTS.items():
        for name in spec["outputs"] + (manifest_name(exp),):
            shutil.copy2(HERE / name, tmp_path / name)
    return tmp_path


def edit_manifest(path, exp, update):
    m = json.loads((path / manifest_name(exp)).read_text(encoding="utf-8")); update(m)
    (path / manifest_name(exp)).write_text(json.dumps(m), encoding="utf-8")


def test_committed_run_is_consistent():
    for exp in AVAILABLE:
        assert contract.errors(exp, HERE) == [], exp
    assert verify.main(["--experiments", ",".join(AVAILABLE)]) == 0
    assert verify.main([]) == 0            # UCI ZIP이 없으면 E2는 건너뛰고 실패로 세지 않는다


@pytest.mark.parametrize("exp,kind", [("E1", "output_changed"), pytest.param("E2", "output_missing", marks=needs_uci), ("E3", "shared_code"),
                                      ("E3", "artifact"), pytest.param("E2", "external_table", marks=needs_uci), ("E1", "input"),
                                      pytest.param("E2", "protocol", marks=needs_uci)])
def test_mutations_are_detected(run_copy, exp, kind):
    first = EXPERIMENTS[exp]["outputs"][0]
    if kind == "output_changed":
        (run_copy / first).write_text((run_copy / first).read_text(encoding="utf-8").replace("0.", "1.", 1), encoding="utf-8")
    elif kind == "output_missing":
        (run_copy / first).unlink()
    else:
        group, key = {"shared_code": ("code", "press_guard/model.py"), "artifact": ("artifacts", "guard_A.json"),
                      "external_table": ("sources", "analysis/press_external/metrics.csv"), "input": ("inputs", "normal"),
                      "protocol": (None, None)}[kind]
        def update(m):
            if group is None: m["protocol"] = "other"
            else: m[group][key] = "0" * 64      # 실행 당시와 다른 파일을 쓴 것과 같다
        edit_manifest(run_copy, exp, update)
    assert contract.errors(exp, run_copy)
    assert verify.main(["--out", str(run_copy), "--experiments", exp]) == 1
    assert verify.main(["--out", str(run_copy), "--experiments", exp, "--freeze"]) == 2


def test_expected_tampering_is_detected(run_copy, monkeypatch, tmp_path_factory):
    expected = tmp_path_factory.mktemp("expected")
    for exp, spec in EXPERIMENTS.items():
        for name in spec["outputs"] + (manifest_name(exp),):
            shutil.copy2(verify.EXPECTED / name, expected / name)
    monkeypatch.setattr(verify, "EXPECTED", expected)
    assert verify.main(["--out", str(run_copy), "--experiments", ",".join(AVAILABLE)]) == 0
    name = EXPERIMENTS["E3"]["outputs"][0]
    (expected / name).write_text((expected / name).read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert verify.main(["--out", str(run_copy), "--experiments", "E3"]) == 1


def test_compare_csv_tolerance(tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("x,y\n1.0,s\n", encoding="utf-8"); b.write_text("x,y\n1.0000000001,s\n", encoding="utf-8")
    assert verify.compare_csv(a, b) is None
    b.write_text("x,y\n1.001,s\n", encoding="utf-8")
    assert verify.compare_csv(a, b)


def test_cache_key_tracks_conversion(tmp_path):
    path, key = uci_v2.cache_path("abc")
    other, other_key = uci_v2.cache_path("abc", version="uci10hz-v2")
    assert key != other_key and path != other
    arrays = {s: np.zeros((2205, 600)) for s in uci_v2.UCI_SENSORS}
    good = tmp_path / "good.npz"; np.savez(good, key=key, **arrays)
    assert uci_v2.read_cache(good, key) is not None and uci_v2.read_cache(good, other_key) is None
    arrays["VS1"][0, 0] = np.nan
    bad = tmp_path / "bad.npz"; np.savez(bad, key=key, **arrays)
    assert uci_v2.read_cache(bad, key) is None                      # 손상 캐시는 쓰지 않는다
    (tmp_path / "broken.npz").write_bytes(b"not a zip")
    assert uci_v2.read_cache(tmp_path / "broken.npz", key) is None


def test_run_options_are_recorded_not_compared(run_copy):
    """평가관 06 R7: E2 --no-cache 실행(cache_used=False)은 결과가 같으므로 통과, 캐시 형식(cache_version)이 다르면 실패."""
    assert verify.compare_to_expected(run_copy, ["E2"]) == []
    edit_manifest(run_copy, "E2", lambda m: m["config"].update(cache_used=not m["config"]["cache_used"]))
    assert verify.compare_to_expected(run_copy, ["E2"]) == []
    edit_manifest(run_copy, "E2", lambda m: m["config"].update(cache_version="uci10hz-v2"))
    assert verify.compare_to_expected(run_copy, ["E2"])


def test_missing_external_input_is_skipped_not_failed(monkeypatch, tmp_path):
    """평가관 06 R6: UCI ZIP이 없으면 E2를 이유와 함께 건너뛴다(기본 통과, --strict면 실패, 동결은 거부)."""
    monkeypatch.setitem(EXPERIMENTS["E2"], "extra_inputs", {"uci_hydraulic_zip": tmp_path / "없음.zip"})
    assert verify.unavailable("E2") and verify.main(["--experiments", "E2"]) == 0
    assert verify.main(["--experiments", "E2", "--strict"]) == 1
    assert verify.main(["--experiments", "E2", "--freeze"]) == 2
