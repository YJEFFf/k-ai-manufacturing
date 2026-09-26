# ⑤ 전력 과제 패키지 (`power_submission`)

제조 생산데이터 기반 15분 전력 예측과 최대피크 위험 분석을 한 번에 재현하는 코드다. 원본 데이터 적재부터 진단·전처리·학습·추론·
분석·현장 시뮬레이션·그림·핵심 수치까지 `run_all.py` 한 번으로 만들고, `verify.py`가 동결 기대값과 비교한다.

## 환경

- Python 3.12 이상(고정한 numpy 2.5.3 휠은 3.12+용, conda는 `environment.yml`). 메모리 약 1.1GB. 실행 시간은 아래 '실행 기록' 참고.
- macOS: LightGBM이 OpenMP를 쓰므로 필요하면 `brew install libomp`. Windows: 가상환경 활성화는 `.venv\Scripts\activate`,
  그림 한글은 맑은 고딕을 쓴다(한글 글꼴이 없으면 `figures` 단계가 경고를 낸다. 수치 산출물에는 영향 없음).
- LightGBM 스레드(4)·결정적 모드와 난수 시드를 고정해 결과가 코어 수·BLAS·파이썬 빌드와 무관하게 같다
  (다른 파이썬 빌드·OpenBLAS에서 비트 단위 일치를 확인했다).

## 실행

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_all.py --stages predict     # 추론만: 저장된 선택 모델로 시험 예측 재생성(학습 없음, 수 초)
python run_all.py --data "/경로/Dataset_자원 최적화 AI 데이터셋.zip"   # 전체(전처리·학습·추론·분석). 원본 사본을 data/에 저장
python -m pytest -q tests              # 데이터 진단·누설(미래 교란 불변)·분할 경계·게이트·요금 규칙·검증 도구 테스트
python verify.py --require-fresh       # outputs/ 를 expected/ 동결값과 비교 + 마지막 전체 실행에서 만든 산출물인지 확인
```

- **추론만**(`--stages predict`): `models` 단계가 저장한 선택 모델(시험 구간 주간 재학습 모델, `artifacts/models/`, 파일별 SHA-256)을
  불러 시험 예측을 다시 만들고(`outputs/test/predictions_from_saved_models.csv`), 학습 때 예측과의 최대 절대 차이를
  `outputs/test/inference_check.json`에 남긴다. 학습 때 예측은 소수 넷째 자리로 저장되므로 차이 ≤ 5e-5는 저장 반올림이다
  (2026-09-26 실행: 모델 48개 12MB, 0.6초, 모든 과제 최대 차이 < 5e-5).
- `--require-fresh`는 모든 단계를 한 번에 실행한 기록을 요구한다. 일부 단계만 다시 돌리면 그 단계의 산출물이 전체 실행 기록 밖에서
  쓰였으므로 실패한다(기본 `verify.py`는 비교는 하고 신선도는 경고만 한다). 실행 도중 코드가 바뀌면 run_all.py가 오류로 끝나고,
  전체 실행 뒤 코드가 바뀌어도 신선도 확인이 실패한다(코드 지문).
- 원본 경로는 `--data` 인자 → 환경변수 `POWERGUARD_DATA` → `data/okm_augumented_2021.csv` → 상위 `데이터셋/` ZIP 순서로 찾는다.
  원본이 없으면 데이터가 필요한 테스트는 건너뛴다.
- 외부 KAMP 자료(#41·#46·#30) ZIP은 `--kamp-dir` 폴더(기본: `data/external/`, 없으면 상위 `데이터셋/`)에서 찾으며, 없으면
  `external` 단계는 해당 항목을 건너뛰고 `verify.py`는 `external/*`를 비교하지 않는다.
- 단계만 골라 실행할 수 있다: `--stages diagnostics,models,predict,peak,analysis,ablation,field,external,figures,digest`.
  `predict`·`peak`부터는 `models` 결과(`artifacts/`)가 필요하다. `outputs/run_manifest.json`에 단계별 실행 시각, 마지막 호출,
  마지막 전체 실행(시작·끝·단계별 시간·인자·커밋·CPU 수·코드 지문)이 남는다.

## 실행 기록

- 2026-09-26 v2.2 전체 실행(Apple M 계열 8코어, 다른 전체 실행과 동시에 돌아 부하 상태): 4,182초 — models 625초(선택 모델 저장 포함),
  predict 0.6초, peak 33초, analysis 97초, ablation 3,367초(정보가치·절제·반사실 절차·기상 예보오차·학습 창·LightGBM 격자), 나머지 약 1분.
  `ablation`을 빼면 약 15분이다.
- 결과 동일성: 코드만 복사한 사본의 전체 재실행이 `verify.py --require-fresh`로 동결값·시험 예측 SHA-256·그림 목록과 모두 일치했다.

## 제출 패키지 체크리스트(재현용)

1. `python make_submission.py`가 코드·테스트·기대값·산출물(시험 예측 파일 포함)·원본 CSV·저장된 선택 모델과 파일별 SHA-256 목록을
   ZIP 하나로 만든다. 묶음 안의 실행 기록에서는 전체 실행 기록을 빼므로, 풀기만 한 사본은 `--require-fresh`에서 실패하고
   `run_all.py`를 돌린 뒤 통과한다. 외부 ZIP은 `--with-external`로 `data/external/`에 넣는다. 작업 기록 문서는 넣지 않는다.
2. 원본은 `data/okm_augumented_2021.csv`에 두거나(SHA-256 확인) `--data`로 KAMP ZIP 경로를 준다.
3. 외부 KAMP 자료 ZIP이 없으면 `external` 단계는 해당 항목을 건너뛰고, `verify.py`는 `external/*`를 비교하지 않는다(메시지로 알린다).
4. 시험 구간 예측 파일은 `outputs/test/predictions_test.csv`(점예측·예측구간·다음 1시간 피크 확률·경보)이며, 열 뜻은
   `outputs/test/test_prediction_columns.csv`에 있다.
5. `python -m pytest -q tests` → `python verify.py --require-fresh`로 확인한다.

## 구성

| 경로 | 내용 |
|---|---|
| `powerguard/data.py` | 원본 적재, 복제군 원본 판정(달력·생산 정합)·부분/시간 복제·손상·정전·전력–생산 불일치 진단, 15분 구간 표 |
| `powerguard/features.py` | 발행 시점 기준 특징: 가동 체제·요일유형4·기상·지연값·체제별 유사일·실시간 수준 보정, 특징 사전(FEATURE_GLOSSARY) |
| `powerguard/models.py`, `registry.py` | 기준모델·유사일·LightGBM·MLP·하이브리드·선형 보정 유사일·계획 정지 게이트, 비교 후보 목록 |
| `powerguard/cv.py` | 6·7월 워크포워드(5월 = 첫 학습 창, 폴드 안 주간 재학습), 시험 8/1~9/14 주간 재학습 |
| `powerguard/stage_models.py` | 교차검증 비교, 사전 규칙(부트스트랩)에 따른 선택과 난수 민감도, 한 장 선택표, LightGBM 소형 격자, 선택 모델 저장 |
| `powerguard/stage_predict.py` | 추론 전용 단계: 저장된 선택 모델로 시험 예측 재생성·학습 때 예측과 비교 |
| `powerguard/peak.py`, `stage_peak.py` | 잔차 기반 예측분포, 다음 1시간 초과확률(기후값 기준·F1 차이 구간·보정 비교), 예측구간, 경보·사건, 익일·월 누적 최대 |
| `powerguard/stage_analysis.py` | 조건×모델 기술점수, 오차 규칙(교차검증에서 찾고 시험에서 재현 확인), SHAP(묶음·의존도), 피크 조건, FN/FP 집중, 계획 정보가치, 절제·반사실 절차 |
| `powerguard/stage_field.py` | 요금적용전력(래칫), 래칫 위험일 선별, 수요제어(개입 예산)·순차 기동·냉방·야간 이동·경보 등급·통합 운영 절차(가정 기반) |
| `powerguard/stage_external.py` | KAMP #41 파생 판정, #46 동시 기동, #30 일정 제약 |
| `powerguard/stage_figures.py` | 분석용 그림 |
| `outputs/` | 집계 결과 CSV/JSON과 그림. `outputs/test/predictions_test.csv`는 시험 구간 예측 파일 |
| `artifacts/` | 행 단위 예측(OOF·시험)·저장된 선택 모델(`models/`) |
| `data/` | 원본 사본(`--data` 첫 실행 때 저장), 외부 KAMP ZIP(`external/`, 선택) |
| `expected/` | `verify.py`용 동결 기대값(시험 예측 SHA-256·그림 목록 포함) |

## 결과 파일 안내

- `outputs/diagnostics/`: `summary.json`(진단 수치·원본 판정 근거), `variable_dictionary.csv`(18열 사전), `missing_outlier_treatment.csv`,
  `preprocessing_waterfall.csv`, `split_composition.csv`, `imbalance.csv`, `copy_groups.csv`·`copy_origin_sensitivity.csv`·
  `copy_direction_checks.csv`(복제 방향), `production_power_relation.csv`·`operating_states.csv`(생산–전력 관계·운영 상태),
  `input_support_test_days.csv`(시험 날짜의 운영 조합이 학습에 있었는가)
- `outputs/cv/`: `cv_metrics.csv`, `selection.json`(선택 경로), `selection_summary.csv`(과제별 한 장 선택표), `selection_robustness.csv`, `ml_sweep.csv`
- `outputs/test/`: `test_metrics.csv`(시험 구간 모든 모델 성능), `test_metrics_static_refit.csv`(정적 학습 민감도), `inference_check.json`
- `outputs/peak/`: 예측구간 포괄률·보정 이득 구간, 다음 1시간 피크 분류(기후값 기준·F1 차이·보정 비교·신뢰도)·경보, 익일·월 누적 최대
- `outputs/analysis/`: 조건×모델 기술점수, 오차 규칙·안정성, 시험 역전 날짜 분해, SHAP(특징·묶음·상호작용·기상 의존도), 피크 조건·조건부 비율,
  FN/FP 집중 조건, 계획 정보가치, 절제(계획 정지 게이트 제외 포함)·반사실 절차(`naive_protocol.csv`), 기상 예보오차, 학습 창 곡선
- `outputs/field/`: 요금적용전력(`billing_ratchet.json`)·래칫 사건·사다리·완전 제어 상한·래칫 위험일, 수요제어(설정·파레토·민감도),
  순차 기동, 냉방, 야간 이동, 경보 등급·부담(운전 상태·요금 목표), 통합 시나리오·운영 절차
- `outputs/external/`: 외부 KAMP 자료 판정·메커니즘
- `outputs/figures/`: 분석용 그림
- `outputs/key_numbers.json`: 위 결과의 핵심 수치 모음(각 값의 출처 파일 표기)
