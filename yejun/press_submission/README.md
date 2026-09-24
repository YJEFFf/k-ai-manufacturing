# ③ 프레스 유압펌프 이상 탐지 — 제출 패키지

실행 기준은 [PLAN.md](PLAN.md)다. 현재 상태: **1단계(데이터·구간·분할·진단·뼈대) 구현.** 2~6단계는 `outputs/checks.json`의 `pending_steps`에 표시된다.

## 실행

```bash
cd yejun/press_submission
python -m pip install -r requirements.txt
# 데이터 배치: data/3_소성가공_예지보전/press_data_normal.csv, outlier_data.csv (Git 제외)
#   로컬 원본: ../../데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전/ 에서 복사하거나 --root로 그 폴더를 지정
OMP_NUM_THREADS=1 python run_all.py --root . --out outputs            # 약 10초
python -m pytest -q tests                                              # 정확성 검사
python predict.py --model artifacts/skeleton.json --input <입력.csv> --out predictions.csv
```

`--root`는 `data/3_소성가공_예지보전/`을 포함하는 폴더다. 기본은 이 패키지 폴더. `--no-verify`를 주면 해시·행 수 검증을 건너뛰고 다른 자료로도 실행한다(그때 기록구간 수 검사는 생략된다).

## 입력 검증
- SHA-256: 정상 `f2d61cb3…b0a7`, 이상 `9fad8c23…ed2e`. 행 수 20,000 / 600.
- 필수 열: `TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current`. 라벨·파일명·행 번호는 모델 입력이 아니다.
- 잘못된 행(시각 파싱 불가, 비유한 센서값)은 삭제하지 않고 `status`로 표시하며 앞뒤로 기록구간 경계가 된다.

## 산출물 (`outputs/`)
| 파일 | 내용 |
|---|---|
| `diagnosis.md`, `diagnosis.json`, `waveform_segments.csv` | 데이터 진단(구조·Δt·저장 형식 규칙·센서 통계·전류 파형·lag-1 자기상관) |
| `fig_current_waveform.png`, `fig_segment_length.png` | 파형 예시, 구간 길이 분포 |
| `splits.csv` | 분할 A/B의 학습·보정·평가 행/구간 수 |
| `preprocess_effect.csv` | raw/matched/coarse 전처리가 값에 준 변화 |
| `checks.json`, `manifest.json` | 정확성 검사 결과, 환경·입력 해시·산출물 해시·실행 시간 |
| `../artifacts/skeleton.json` | 산출물 계약 뼈대(학습 상태 없음). 2단계에서 학습 상태를 채운 artifact가 추가된다 |

산출 CSV에는 센서 원값 열이 없다(`checks.json.outputs_free_of_raw_sensor_columns`). 원본 CSV·행별 예측·artifacts는 Git 제외이며 제출 ZIP에만 포함한다.

## 구현 단계 (PLAN §8)
| 단계 | 상태 |
|---|---|
| 1 데이터·구간·분할·진단·뼈대 | 완료 |
| 2 w=8 고정, q95 지수 꼬리, conformal 보정, 추론·집계 | 예정 |
| 3 전처리·창 민감도, 절제, 오류 조건 | 예정 |
| 4 기준모델·LSTM 3프로토콜, coverage·불확실성 | 예정 |
| 5 업무량·지속성·진폭 후보·장별 근거 | 예정 |
| 6 환경 고정·깨끗한 재현·ZIP 조립 | 예정 |
