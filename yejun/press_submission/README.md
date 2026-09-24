# ③ 프레스 유압펌프 이상 탐지 — 제출 패키지

실행 기준은 [PLAN.md](PLAN.md)다. 현재 상태: **1단계(데이터·진단·뼈대)와 2단계(w=8 고정·q95 지수 꼬리·conformal 보정·추론) 구현.** 3~6단계는 `outputs/checks.json`의 `pending_steps`에 표시된다.

## 실행

```bash
cd yejun/press_submission
python -m pip install -r requirements.txt
# 데이터 배치: data/3_소성가공_예지보전/press_data_normal.csv, outlier_data.csv (Git 제외)
#   로컬 원본: ../../데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전/ 에서 복사하거나 --root로 그 폴더를 지정
OMP_NUM_THREADS=1 python run_all.py --root . --out outputs            # 약 10초 (2단계 포함)
python -m pytest -q tests                                              # 정확성 검사
python predict.py --model artifacts/main_A.json --input <입력.csv> --out predictions.csv   # 저장 상태만으로 추론
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
| `model_comparison.csv` / `.md` / `_cutoff.md` | 모델 × 분할 × 보정 단위 × 기준(conformal/cutoff) × α 집계. 주 지표: 이상 탐지 구간, 정상 알림 구간, 판정 가능 비율, 첫 경보 지연; F1·coverage 병기 |
| `operating_points.csv`, `thresholds_main.csv` | 주 모델(combined_w8)의 운영점: 명목 α, alpha_grid, 문턱, 정상 알림 k/n, 독립 가정 이항 95% 상한, 지연 |
| `tail_params.csv`, `conformal_mc.csv` | 성분별 q95·beta·적합 여부·g(1); 순위 p값 MC 검사 |
| `predictions_A.csv`, `predictions_B.csv`, `records_main_*.csv` | 행별 예측(평가 스트림)·구간별 알림 기록 — Git 제외 |
| `checks.json`, `manifest.json` | 정확성 검사 결과, 환경·입력 해시·산출물 해시·실행 시간 |
| `../artifacts/main_A.json`, `main_B.json` | 주 모델 학습·보정 상태(스케일러, 참조 점수, 꼬리 변환, 보정 구간 최댓값, 문턱). `predict.py`가 이 파일만으로 추론한다 — Git 제외 |

산출 CSV에는 센서 원값 열이 없다(`checks.json.outputs_free_of_raw_sensor_columns`). 원본 CSV·행별 예측·artifacts는 Git 제외이며 제출 ZIP에만 포함한다.

## 주 모델과 경보 기준 (PLAN §3·§4)
- 성분: 3센서 max-abs-z, 전류 trailing-8 사인 적합 1−R². 각 성분을 정상 학습 참조의 q95 초과분 지수 꼬리로 변환해 fmax로 결합. 사인이 없는 행(구간 첫 7행·SST=0)은 max-z만.
- 주 기준: 정상 보정 기록구간 최댓값의 conformal p ≤ α (α=1%, 3%·5% 병기). 참고 기준: 기존 cutoff. 두 기준은 `criterion` 열로 구분한다.
- 결과 해석: 정상·이상이 각각 하루라 이미 본 자료에 대한 탐색적 평가다. 1%는 고정 비교 기준이지 현장 최적 운영점이 아니다.

## 구현 단계 (PLAN §8)
| 단계 | 상태 |
|---|---|
| 1 데이터·구간·분할·진단·뼈대 | 완료 |
| 2 w=8 고정, q95 지수 꼬리, conformal 보정, 추론·집계 | 완료 |
| 3 전처리·창 민감도, 절제, 오류 조건 | 예정 |
| 4 기준모델·LSTM 3프로토콜, coverage·불확실성 | 예정 |
| 5 업무량·지속성·진폭 후보·장별 근거 | 예정 |
| 6 환경 고정·깨끗한 재현·ZIP 조립 | 예정 |
