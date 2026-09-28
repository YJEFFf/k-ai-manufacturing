"""검증 계약(루브릭 사이클2 평가관 06 R8): 커밋된 실행은 통과하고, 결과 변조·삭제, 실행 기록의 해시 변경(실행 뒤 코드·입력 변경),
실행 기록 삭제, 동결값 변조는 실패한다. 공용 규칙은 analysis/package_contract.py에 있다.

    python -m pytest -q analysis/<패키지>/test_contract.py
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import package_contract as pc  # noqa: E402


@pytest.fixture(autouse=True)
def require_generated_inputs():
    lacking = pc.missing_prerequisites()
    if lacking:
        pytest.skip(pc.FIRST_RUN_HINT + ": " + ", ".join(lacking))


def test_committed_run_passes():
    assert pc.verify(HERE) == []


@pytest.mark.parametrize("scenario", pc.SCENARIOS)
def test_tampering_is_detected(scenario, tmp_path):
    assert pc.mutate_and_verify(HERE, scenario, tmp_path), scenario


def test_csv_tolerance_and_images(tmp_path):
    """수치 열은 허용오차(1e-9) 안이면 같고 넘으면 다르다. 문자 열은 정확 비교."""
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    a.write_text("x,y\n1.0,s\n", encoding="utf-8")
    b.write_text("x,y\n1.0000000001,s\n", encoding="utf-8")
    assert pc.compare_csv(a, b, 1e-9) is None
    b.write_text("x,y\n1.001,s\n", encoding="utf-8")
    assert pc.compare_csv(a, b, 1e-9)
    b.write_text("x,y\n1.0,t\n", encoding="utf-8")
    assert pc.compare_csv(a, b, 1e-9)


def test_missing_git_excluded_output_is_not_a_failure(tmp_path):
    """Git에서 뺀 결과(segment_metrics.csv)가 없는 갓 받은 사본은 실패가 아니라 참고로 알린다."""
    c = pc.load_contract(HERE)
    out = tmp_path / "out"
    out.mkdir()
    for rel in list(c["outputs"]) + list(c["manifests"]):
        (out / rel).write_bytes((HERE / rel).read_bytes())
    assert c["local_outputs"] and not any((out / r).exists() for r in c["local_outputs"])
    bad, notes = pc.compare_expected(HERE, out)
    assert pc.integrity(HERE, out) == [] and bad == [] and any("Git 제외" in n for n in notes)
