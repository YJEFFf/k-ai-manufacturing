"""데이터 로드·경로·예준 vendor 헬퍼.

경로는 --root 하나에서 계산한다. 기본 root = 이 파일의 parents[2]
(볼트: 제조데이터_경진대회/, 레포: claude/) — 둘 다 그 아래 data/3_소성가공_예지보전/ 가 있다.
"""
import hashlib
import importlib.util
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[2]
VENDOR = HERE / "vendor" / "press_policy_audit.py"
# 팀 레포 main의 codex/analysis/press_welding_review/press_policy_audit.py (마지막 변경 83a2273)
VENDOR_SHA256 = "4887e4c52bcb9022324225a113d1ca4e54b37a395a0707cd222a72683b4312a0"
SENSORS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
CRLF, LF = bytes([13, 10]), bytes([10])


def load_vendor():
    """예준 헬퍼를 import. 파일이 바뀌면 수치가 조용히 바뀌므로 해시·상수를 확인한다."""
    # 줄바꿈을 LF로 정규화해 해시한다 (Windows git autocrlf 체크아웃에서도 같은 값)
    digest = hashlib.sha256(VENDOR.read_bytes().replace(CRLF, LF)).hexdigest()
    assert digest == VENDOR_SHA256, f"vendor 파일이 바뀜: {digest}"
    spec = importlib.util.spec_from_file_location("yj_vendor", VENDOR)
    yj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yj)
    assert yj.SPLITS == [("normal_60_20_20", 360, 480), ("normal_50_20_30", 300, 420)]
    assert yj.BUDGETS == [0.01, 0.03, 0.05]
    assert yj.COLS == SENSORS
    return yj


def data_dir(root):
    return Path(root) / "data" / "3_소성가공_예지보전"


def load(root=DEFAULT_ROOT):
    d = data_dir(root)
    normal = pd.read_csv(d / "press_data_normal.csv")
    abnormal = pd.read_csv(d / "outlier_data.csv")
    assert len(normal) == 20000 and len(abnormal) == 600
    return normal, abnormal


def inputs_only(frame):
    """추론 입력: 센서 3열 + TimeStamp. 라벨·인덱스 열은 버린다."""
    return frame[["TimeStamp"] + SENSORS].reset_index(drop=True)


def split_sets(normal, yj, train_end, cal_end):
    nb = yj.blocks(normal)
    assert len(set(nb)) == 600
    train = normal[nb < train_end].reset_index(drop=True)
    cal = normal[(nb >= train_end) & (nb < cal_end)].reset_index(drop=True)
    test = normal[nb >= cal_end].reset_index(drop=True)
    return train, cal, test
