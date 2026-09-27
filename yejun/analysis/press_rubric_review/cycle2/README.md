# 루브릭 검수 사이클 2 — 평가관 6명 반복 검수

예준 지시(2026-09-27): 평가 요소마다 평가관 에이전트가 점수를 매기고, 부족한 부분을 고친 뒤 다음 검수에서 고칠 수 있는 부족분이 나오지 않을 때까지 반복한다. 검수 기록이며 대회 보고서가 아니다. 공식 기준은 [official_task_extract.txt](../official_task_extract.txt)다.

## 1회차(round1, 기준 커밋 dcd300a)

| 평가관 | 항목(배점) | 점수 | 보고서 |
|---|---|---:|---|
| 01 | 데이터 이해 및 진단(15) | 12.5 | [judge_01_data.md](round1/judge_01_data.md) |
| 02 | AI 예측모델 개발(40) | 31 | [judge_02_model.md](round1/judge_02_model.md) |
| 03 | 영향요인 및 오류분석(15) | 11.5 | [judge_03_errors.md](round1/judge_03_errors.md) |
| 04 | 현장 활용방안(10) | 7.0 | [judge_04_field.md](round1/judge_04_field.md) |
| 05 | 창의성·차별성(10) | 8.0 | [judge_05_originality.md](round1/judge_05_originality.md) |
| 06 | 코드 및 재현성(10) | 7.5 | [judge_06_repro.md](round1/judge_06_repro.md) |
| | 합계(100) | **77.5** | |

평가관의 검증 스크립트·로그·JSON은 같은 폴더에 있다. 평가관은 이 폴더 밖을 고치지 않았다.

## 1회차 처리

| 평가관 항목 | 처리 위치 |
|---|---|
| 01 D1~D7, 05 O1(a)·O4 | `analysis/press_evidence/`(build_diagnostics.py, figures.py, 새 표 16개·그림 5장), `press_submission/README.md` 참조 두 줄 |
| 02 M1, 05 O2 | `press_guard/probability.py`, 예측 열, `outputs/probability_*`, `label_free_alert_probability_v2.csv` |
| 02 M2, 05 O5·O6 | `analysis/press_supervised/` v2(3ad2452) |
| 02 M3~M5, 05 O3, 03 E7 | `analysis/press_selection/` |
| 03 E1~E6·E8 | `press_guard/insights.py`와 보강 표·그림, README E6 문장 |
| 04 U1~U8, 05 O1(b)·O7 | `press_guard/`(2단계 알림, 품질 시간창, monitor.py, simulate.py, recalibrate.py, 콘솔, OPERATIONS.md, docs/ 그림, expected_effect_v2.csv) |
| 06 R1~R5·R9·R11 | `press_guard/`(runtime.py, reproduce.py, requirements·environment.yml, test_predictions, predict.py --split, verify 예측 요약, 이식성 시험), `press_submission/run_all.py` torch 지연 import와 v1 재동결 |
| 06 R6~R8·R10 | `analysis/package_contract.py`와 각 패키지 contract.json·expected·test_contract.py, 보완 실험 계약 수정, README 경로 정리 |

주 지표(A F1 0.961938·B 0.970990, 정상 0/120·3/180, 이상 21/21)와 경보 규칙은 바꾸지 않았다. 사후에 정한 것(2단계 규칙, 대기열 정렬 키, 확률 층)은 각 문서에 그 사실을 적었다.
