"""고정 설정: 경로, 달력, 분할, 피크 기준. 실험 중 바꾸면 PLAN.md 변경 기록에 남긴다."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PKG_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PKG_ROOT.parents[1]
DATA_DIR = PKG_ROOT / "data"
ARTIFACT_DIR = PKG_ROOT / "artifacts"
OUTPUT_DIR = PKG_ROOT / "outputs"
EXPECTED_DIR = PKG_ROOT / "expected"

CSV_NAME = "okm_augumented_2021.csv"
ZIP_MEMBER = "data/okm_augumented_2021.csv"
DEFAULT_ZIP = REPO_ROOT / "데이터셋" / "Dataset_자원 최적화 AI 데이터셋.zip"
KAMP_DIR = REPO_ROOT / "데이터셋"  # 외부 KAMP 자료 ZIP 폴더(run_all.py --kamp-dir로 바꿀 수 있다)
CSV_SHA256 = "8f7af2e49366c93e1d6f5fdef4b5e350066c1792ac463c2c2886e370f4674830"

POWER_COLS = ["15분", "30분", "45분", "60분"]
SEED = 20260925

# 2021 대한민국 공휴일(관공서의 공휴일에 관한 규정). 데이터 기간(1/1~9/14) 안의 날짜만.
HOLIDAYS = pd.to_datetime([
    "2021-01-01",
    "2021-02-11", "2021-02-12", "2021-02-13",  # 설날 연휴
    "2021-03-01",  # 삼일절
    "2021-05-05",  # 어린이날
    "2021-05-19",  # 부처님오신날
    "2021-06-06",  # 현충일(일)
    "2021-08-15",  # 광복절(일)
    "2021-08-16",  # 대체공휴일
])

# 시간순 분할
TEST_START = pd.Timestamp("2021-08-01")
TEST_END = pd.Timestamp("2021-09-15")  # 미포함
CV_FOLDS = [
    # (이름, 검증 시작, 검증 끝(미포함)) — 학습은 검증 시작 이전의 원본일 전부
    ("V1_Apr", pd.Timestamp("2021-04-01"), pd.Timestamp("2021-05-01")),
    ("V2_May", pd.Timestamp("2021-05-01"), pd.Timestamp("2021-06-01")),
    ("V3_Jul", pd.Timestamp("2021-07-01"), pd.Timestamp("2021-08-01")),
]

# 부분 복제 판정: 앞선 다른 패턴 날짜와 연속 동일 구간 수가 이 값 이상
PARTIAL_COPY_RUN = 16
PARTIAL_COPY_HOURS = 3      # 복제된 가동 시간이 이 수 이상이면 그날 전체를 부분 복제로 본다
RUNNING_HOUR_MEAN = 40      # 가동 시간 판정(네 값 평균 초과)

# 피크 기준: 학습 구간 원본일 15분 전력의 분위수
PEAK_Q = 0.95
PEAK_Q_SENS = (0.90, 0.975)

# 교대·휴식 전환 슬롯(구간 시작 시각 기준, 15분 슬롯 번호 = 시*4 + 분/15)
def slot_of(hh: int, mm: int) -> int:
    return hh * 4 + mm // 15


TRANSITION_WINDOWS = {
    "startup_0730_0845": (slot_of(7, 30), slot_of(8, 45)),
    "lunch_1145_1315": (slot_of(11, 45), slot_of(13, 15)),
    "break_1645_1745": (slot_of(16, 45), slot_of(17, 45)),
    "shift_end_1945_2030": (slot_of(19, 45), slot_of(20, 30)),
}
