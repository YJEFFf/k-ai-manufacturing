import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

NEEDS_DATA = {"test_data.py", "test_leakage.py", "test_models.py"}


def _data_available() -> bool:
    from powerguard import data as D
    try:
        D.resolve_source()
        return True
    except FileNotFoundError:
        return False


def pytest_collection_modifyitems(config, items):
    """원본 데이터가 없으면 데이터가 필요한 테스트는 오류 대신 건너뛴다(README의 데이터 배치 안내 참고)."""
    if _data_available():
        return
    skip = pytest.mark.skip(reason="원본 없음: run_all.py --data로 한 번 실행하거나 POWERGUARD_DATA를 지정한다")
    for item in items:
        if Path(str(item.fspath)).name in NEEDS_DATA:
            item.add_marker(skip)
