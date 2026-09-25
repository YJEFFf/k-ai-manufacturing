# ⑤ 전력 과제 패키지 (`power_submission`)

제조 생산데이터 기반 15분 전력 예측과 최대피크 위험 분석을 한 번에 재현하는 코드다. 실행계획과 판단 기록은 [PLAN.md](PLAN.md)에 있다. 이 폴더는 보고서가 아니라 코드·실험 결과·분석용 표와 그림을 담는다.

## 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_all.py                      # 원본 자동 탐색: data/okm_augumented_2021.csv → 저장소 데이터셋 ZIP
python run_all.py --data "/경로/Dataset_자원 최적화 AI 데이터셋.zip" --kamp-dir "/경로/데이터셋"
python -m pytest -q tests              # 데이터 진단·누설(미래 교란 불변)·분할 경계 테스트
python verify.py                       # outputs/ 를 expected/ 동결값과 비교
```

단계만 골라 실행할 수 있다: `--stages diagnostics,models,peak,analysis,ablation,field,external,figures,digest`. `peak`부터는 `models` 결과(`artifacts/`)가 필요하다. 전체 실행은 Apple M 계열 8코어에서 약 31분(모델 비교 7.5분, 절제 21분)이다.

원본 CSV의 SHA-256(`8f7af2e4…4830`)을 적재 시 확인한다. 외부 KAMP 자료(#41·#46·#30) ZIP은 `--kamp-dir` 폴더(기본: 저장소 `데이터셋/`)에서 찾으며, 없으면 `external` 단계는 해당 항목을 건너뛴다.

## 구성

| 경로 | 내용 |
|---|---|
| `powerguard/data.py` | 원본 적재, 복제(일·시간·부분)·손상·정전·체제 불일치 진단, 15분 구간 표 |
| `powerguard/features.py` | 발행 시점 기준 특징: 운영일정·요일유형4·기상·지연값·체제별 유사일·실시간 수준 보정 |
| `powerguard/models.py`, `registry.py` | 기준모델·유사일·LightGBM·MLP·하이브리드·선형 보정 유사일, 비교 후보 목록 |
| `powerguard/cv.py` | 4·5·7월 워크포워드(폴드 안 주간 재학습), 시험 8/1~9/14 주간 재학습 |
| `powerguard/stage_models.py` | 교차검증 비교, 사전 규칙(부트스트랩)에 따른 선택, 시험 예측 |
| `powerguard/peak.py`, `stage_peak.py` | 잔차 기반 예측분포, 다음 1시간 초과확률, 예측구간, 경보·사건, 익일·월 누적 최대 |
| `powerguard/stage_analysis.py` | 조건별 성능, 부트스트랩, 오차 조건 규칙, SHAP, 피크 조건, 계획 정보가치, 절제 |
| `powerguard/stage_field.py` | 수요제어·순차 기동·냉방·경보 등급 시뮬레이션(가정 기반) |
| `powerguard/stage_external.py` | KAMP #41 파생 판정, #46 동시 기동, #30 일정 제약 |
| `powerguard/stage_figures.py` | 분석용 그림 |
| `outputs/` | 집계 결과 CSV/JSON과 그림(Git 포함). `outputs/test/predictions_test.csv`는 시험 구간 예측 파일(Git 제외) |
| `artifacts/`, `data/` | 행 단위 예측·원본 사본(Git 제외) |
| `expected/` | `verify.py`용 동결 기대값 |
| `reviews/` | 구현 검수 지적·처리 기록과 변경 전 핵심 수치 |

## 결과 파일 안내

- `outputs/diagnostics/summary.json`: 데이터 진단 수치(복제·손상·정전·사용 가능 구간·시험 구성)
- `outputs/cv/cv_metrics.csv`, `outputs/cv/selection.json`: 교차검증 성능과 선택 근거(부트스트랩 경로)
- `outputs/test/test_metrics.csv`: 시험 구간 모든 모델 성능, `test_metrics_static_refit.csv`: 정적 학습 민감도
- `outputs/peak/`: 예측구간 포괄률, 다음 1시간 피크 분류·경보, 익일·월 누적 최대
- `outputs/analysis/`: 조건별 성능·기술점수·부트스트랩·오차 규칙·SHAP·피크 조건·계획 정보가치·절제
- `outputs/field/`: 수요제어·순차 기동·냉방·경보 등급
- `outputs/external/`: 외부 KAMP 자료 판정·메커니즘
- `outputs/figures/`: 분석용 그림
- `outputs/key_numbers.json`: 위 결과의 핵심 수치 모음(각 값의 출처 파일 표기)
