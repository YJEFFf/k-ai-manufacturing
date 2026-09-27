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


def test_committed_run_passes():
    assert pc.verify(HERE) == []


@pytest.mark.parametrize("scenario", pc.SCENARIOS)
def test_tampering_is_detected(scenario, tmp_path):
    assert pc.mutate_and_verify(HERE, scenario, tmp_path), scenario
