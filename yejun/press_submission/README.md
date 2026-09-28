# ③ 프레스 유압펌프 이상 탐지 — 기준 모델 패키지

정상 자료 기반 기준 모델(combined_w8), LSTM 비교와 진단·검증 코드를 제공한다. 최종 모델의 전체 실행은 [Press Guard v2](../press_guard/README.md)를 따른다.

## 실행

```bash
cd yejun/press_submission
python -m pip install -r requirements.txt
# 데이터 배치: data/3_소성가공_예지보전/press_data_normal.csv, outlier_data.csv (Git 제외)
#   로컬 원본: ../../데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전/ 에서 복사하거나 --root로 그 폴더를 지정
python run_all.py --root . --out outputs            # 스레드는 코드가 1개로 고정. LSTM 캐시가 있으면 약 1분, 없으면 첫 실행 30~40분(CPU 학습); --steps 3 이면 40초
python -m pytest -q tests                                              # 정확성 검사
python verify.py --out outputs                                         # run_all 실행 뒤 outputs/expected 대비 허용오차 검사 (--freeze 로 동결)
python predict.py --model artifacts/main_A.json --input <입력.csv> --out predictions.csv   # 저장 상태만으로 추론
```

`--root`는 `data/3_소성가공_예지보전/`을 포함하는 폴더다. 기본은 이 패키지 폴더. `--no-verify`를 주면 해시·행 수 검증을 건너뛰고 다른 자료로도 실행한다(그때 기록구간 수 검사는 생략된다). 이 미검증 실행은 `verify.py`의 정식 비교·기대값 동결 대상에서 제외한다.

`verify.py`는 단계별 필수 파일·검사 항목, 예측 파일과 `artifacts/main_A·B.json`을 포함한 실행 산출물 해시, 현재 패키지 코드 해시와 manifest의 일치(실행 후 코드 변경 검출), 실행 범위·설정을 확인한다. 행별 예측·기록 파일은 Git에 없으므로 갓 클론한 저장소에서는 `run_all.py`를 먼저 실행해야 통과한다. 부분 실행은 `python verify.py --out outputs --steps 3`처럼 비교 범위를 지정한다. 기본 전체 비교는 동결 기대값과 실행 단계가 같아야 한다. `--freeze`는 필수 검사·파일·코드 검증이 끝난 실행만 저장한다.

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
| `sensitivity.csv`, `sensitivity_params.csv` | 전처리 raw/matched/coarse × 분할 × 창 {5,6,8,10,12,15,20} 전 절차 재실행(구간 단위 conformal·cutoff), 성분별 꼬리 파라미터·g(1) |
| `quantization_frozen.csv` | matched로 적합·보정한 주 모델을 동결하고 평가 입력만 raw/coarse로 바꾼 진단(재적합 효과와 입력 효과 분리) |
| `ablation.csv` | matched·w=8 절제: 사인 제거, 크기 제거, 초기 max-z 보완 제거, capped 꼬리(기존 ECDF) |
| `label_bypass.csv` | 날짜 이동·불필요한 열·6자리 재직렬화(스트레스)·미래 행 추가에 대한 추론 불변 |
| `segment_features.csv`, `error_conditions_fn.csv`, `error_conditions_fp.csv`, `alarm_components.csv`, `influence.csv`, `interaction_2x2.csv` | 기록구간 특징, 분모 포함 FN(행)/FP(구간) 조건표(위치·길이·진폭 대리 지표·진동 사분위), 발화 성분, 단변량 AUROC(방향 표기), 진동 수준×파형 2×2 |
| `fig_vibration_vs_waveform.png`, `fig_recall_by_position.png`, `fig_error_examples.png` | 진동×구간 R²(사후), 위치별 이상 행 경보율, 사례(파형만 경보·FP·늦은 경보) |
| `lstm_guidebook_reproduction.json`, `lstm_guidebook_history.csv` | 가이드북 LSTM-AE 프로토콜 재구현(PyTorch): 검증 P=R 문턱, 4,000 정상·180 이상 창 혼동행렬, 가이드 보고값 병기. 주 비교표와 다른 프로토콜 |
| `model_comparison_lstm.csv`, `lstm_common_meta.csv`, `lstm_common_history_*.csv`, `model_comparison_all.csv/.md` | 공통 프로토콜 LSTM20 단독·LSTM20+max-z 결합(정상 학습 내부 조기 종료, 구간 내부 창, 정상 보정만)과 전체 모델 병합표 |
| `uncertainty.csv` | 정상 평가 구간 알림 수의 moving-block bootstrap(블록 5·10·20) 민감도. 관측 카운트가 주 결과이며 0건은 퇴화로 표시 |
| `workload.csv`, `persistence.csv`, `load_normalization.csv`, `load_normalization_meta.csv`, `field_decision_table.md` | 업무량(기록시간·경과시간 기준, 가동시간 시나리오), 지속성 (k,n) 규칙(재보정), 진폭 정규화 후보(온라인 trailing-17 특징), 작업자 판단표 |
| `numbers.json` | 검수용 수치 집계(모델·분할·기준·α·분모·run_id 연결). 보고서 서술·장별 초안 생성 없음 |
| `predictions_A.csv`, `predictions_B.csv`, `records_main_*.csv` | 행별 예측(평가 스트림)·구간별 알림 기록 — Git 제외 |
| `checks.json`, `manifest.json` | 정확성 검사 결과, 환경·입력 해시·산출물 해시·실행 시간 |
| `../artifacts/main_A.json`, `main_B.json` | 주 모델 학습·보정 상태(스케일러, 참조 점수, 꼬리 변환, 보정 구간 최댓값, 문턱). `predict.py`가 이 파일만으로 추론한다 — Git 제외 |
| `../artifacts/lstm_cache/*.npz` | LSTM 학습 결과 캐시(설정 해시 키: 프로토콜·에폭·patience·시드·torch 버전·입력 해시). `--retrain-lstm`으로 무시 — Git 제외, 제출 ZIP 포함 |

산출 CSV에는 센서 원값 열이 없다(`checks.json.outputs_free_of_raw_sensor_columns`). 원본 CSV·행별 예측·artifacts는 Git 제외이며 제출 ZIP에만 포함한다.

진단 참조(2026-09-27, v1 산출물은 동결 그대로 둔다):
- `diagnosis.md`의 `current_on_grid_strict`(허용 1e-6) 행(이상 0.077, AUROC 0.538)은 격자 상수의 유효숫자 한계에서 생긴 값이라 판별 의미가 없다. 격자 판정은 허용 1e-3 기준을 쓴다 → [analysis/press_evidence/current_grid.csv](../analysis/press_evidence/current_grid.csv).
- 숨은 시험 자료를 가정하지 않고 공개된 정상·이상 기록으로 탐색 평가한다. 날짜·시간대의 교락을 해소할 현장 자료는 없다.

## 주 모델과 경보 기준 (PLAN §3·§4)
- 성분: 3센서 max-abs-z, 전류 trailing-8 사인 적합 1−R². 각 성분을 정상 학습 참조의 q95 초과분 지수 꼬리로 변환해 fmax로 결합. 사인이 없는 행(구간 첫 7행·SST=0)은 max-z만.
- 주 기준: 정상 보정 기록구간 최댓값의 conformal p ≤ α (α=1%, 3%·5% 병기). 참고 기준: 기존 cutoff. 두 기준은 `criterion` 열로 구분한다.
- 결과 해석: 정상·이상이 각각 하루라 이미 본 자료에 대한 탐색적 평가다. 1%는 고정 비교 기준이지 현장 최적 운영점이 아니다.

## LSTM 학습 설정
- 가이드북 재구현: `--lstm-guide-epochs 800 --lstm-guide-patience 120`(원값). 공통 프로토콜: `--lstm-epochs`·`--lstm-patience`(기본 축약값, `outputs/lstm_common_meta.csv`에 실제 에폭 기록). CPU 단일 스레드·고정 시드. 원 Keras와 초기화·최적화 세부가 달라 가이드 수치의 정확한 재현을 보장하지 않는다.

## 구현 단계 (PLAN §8)
| 단계 | 상태 |
|---|---|
| 1 데이터·구간·분할·진단·뼈대 | 완료 |
| 2 w=8 고정, q95 지수 꼬리, conformal 보정, 추론·집계 | 완료 |
| 3 전처리·창 민감도, 절제, 오류 조건 | 구현·기본 결과 재현. R4(α별 최초 경보 위치) 수정 완료 |
| 4 기준모델·LSTM 3프로토콜, coverage·불확실성 | R2(캐시 키에 코드·전처리·스케일러·자료 해시) 수정 완료, 새 키로 재학습. R6 캐시 없는 재현은 아래 재현 확인 범위 참조 |
| 5 업무량·지속성·진폭 후보·수치 집계 | R3(지속성 결측 처리) 수정 완료. 보고서 생성 기능 삭제 |
| 6 환경 고정·깨끗한 재현·구현 재검수 | Claude 2차 보완과 Codex 재검수 후 테스트 49개·전체 집계 비교 39/39 통과. 상세 범위는 최신 재검수 기록 참조 |
| 보고서·발표자료·최종 제출물 조립 | 보류. 예준의 명시적인 보고서 작성 시작 지시 필요 |

## 재현 확인 범위 (6단계)
- `outputs/expected/`는 검증된 실행(이 저장소의 커밋 시점, macOS arm64·Python 3.12.2)에서 `verify.py --freeze`로 동결한 집계값이다.
- `bash tools/clean_repro.sh --with-lstm`: 저장소를 임시 폴더에 클론하고 산출물을 지운 뒤 데이터·LSTM 캐시를 복사해 `run_all.py`를 처음부터 실행하고 `verify.py`로 비교한다. `--retrain-lstm`은 캐시 없이 LSTM을 처음부터 학습한다(약 30분). 허용오차는 행의 모델별로 적용한다(LSTM 계열 1e-3, IF/MLP-AE 1e-6, 나머지 1e-8). 결과 기록은 재검수 문서에 있다.
- 최신 Codex 재검수에서 기본 명령의 1~3단계는 27/27, `--with-lstm`의 1~5단계는 39/39 통과했다. 전체 LSTM의 캐시 없는 재학습은 Claude의 `294b0f6` 실행 기록을 참조하며 이번 Codex 작업에서 반복하지 않았다.
- 다른 기기·OS에서는 LSTM 오차가 허용오차를 넘을 수 있다. 그 경우 경보 판정(`alarm*` 열)의 차이 수를 verify가 따로 보고한다. 다른 OS 검증은 수행하지 못했다. `verify.py`는 기대 파일 누락·진단 수치 변조·필수 검사 실패를 모두 실패로 처리하며, 실행 메타데이터(cached·train_seconds 등)는 비교하지 않는다.
- 초안을 포함했던 기존 `yejun/submission_press.zip`은 삭제했다. 최종 ZIP 조립과 보고서·발표자료 대조는 예준의 명시적인 보고서 착수 지시 이후로 보류한다. `tools/make_submission_zip.py`는 `evidence/`를 수집하지 않는다.
