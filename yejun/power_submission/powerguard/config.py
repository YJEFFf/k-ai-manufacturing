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
DATA_PATH = None  # run_all.py --data로 준 원본 경로(외부 자료 판정도 같은 원본을 쓴다)
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
    # (이름, 검증 시작, 검증 끝(미포함)) — 학습은 검증 시작 이전의 원본일 전부.
    # v2.0: 실측 전력은 5월부터다(1~4월은 5·6월 패턴의 역방향 채움). 5월은 첫 학습 창, 6·7월을 검증한다.
    ("V1_Jun", pd.Timestamp("2021-06-01"), pd.Timestamp("2021-07-01")),
    ("V2_Jul", pd.Timestamp("2021-07-01"), pd.Timestamp("2021-08-01")),
]
MEASURED_START = pd.Timestamp("2021-05-01")  # 진단으로 확인한 실측 시작(1~4월 원본일 0일)

# 복제군 원본 판정(v2.0). 같은 96값을 가진 날짜 묶음(복제군)에서 전력 패턴이 그 날짜의 달력·생산 기록과
# 정합하는 구성원 중 가장 늦은 날짜를 원본으로 본다. v1.x는 가장 이른 날짜를 원본으로 봤다(비교용 "earliest").
COPY_ORIGIN = "latest_consistent"
# 정합성 판정: 야간조 이월(01~05시 전력 ↔ 00~06시 생산)과 주간 가동(09~16시 전력 ↔ 08~19시 생산)이 서로 맞는가.
# 대기 전력 ≈22, 야간조 ≈100, 주간 가동 ≈150~180 사이의 중간값으로 정했다(민감도는 진단 산출물에 기록).
NIGHT_POWER_ON = 60
NIGHT_PROD_ON = 100
DAY_POWER_ON = 100
DAY_PROD_ON = 1000

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


# 기동 과도분(모든 단계 공통 정의): 08:00~08:59 최대 − 09:00~09:59 평균(10:00 휴식 저부하 제외)
STARTUP_SLOTS = slice(32, 36)
PLATEAU_SLOTS = slice(36, 40)


def startup_excess(v) -> float:
    import numpy as _np
    return float(_np.nanmax(v[STARTUP_SLOTS]) - _np.nanmean(v[PLATEAU_SLOTS]))


TRANSITION_WINDOWS = {
    "startup_0730_0845": (slot_of(7, 30), slot_of(8, 45)),
    "lunch_1145_1315": (slot_of(11, 45), slot_of(13, 15)),
    "break_1645_1745": (slot_of(16, 45), slot_of(17, 45)),
    "shift_end_1945_2030": (slot_of(19, 45), slot_of(20, 30)),
}
