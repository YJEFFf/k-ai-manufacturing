# Claude 2차 수정에 대한 Codex 재검수 — 2026-09-25

대상: `9ecbdcb7bf52e66ddbdd652a02ccb919a1bb394f`와 [Claude 재검수 2차](claude_recheck_2.md). 실제 수정 코드, 기존 테스트, 임시 클론의 전체 실행, 원본 자료의 독립 재집계, 실제 파일 변경·삭제 반례를 확인했다.

**판정: Claude가 추가한 네 가지 보완은 유효하며, 이번 확인 범위에서 추가 구현 결함은 발견하지 못했다.** 기존 테스트 49개, 깨끗한 클론의 1~3단계 27/27 및 1~5단계 39/39, 기존 반례 11개, 추가 확인 12개가 기대한 대로 동작했다. 전체 실행은 LSTM 캐시를 사용했다.

## 1. 네 가지 수정의 직접 확인

| 수정 | 재검수 방법과 결과 |
|---|---|
| 실행 후 코드 변경 검출 | 임시 클론의 `press/scores.py`, `predict.py`, `vendor/press_policy_audit.py`에 각각 주석을 추가했다. manifest는 고치지 않았다. 세 경우 모두 `code.matches_manifest` 실패·비교 종료 1·동결 종료 2이며 기존 기대값은 보존됐다. |
| 주 모델 artifact 무결성 | 실제 `main_A.json`·`main_B.json`의 스케일러 평균을 변경하거나 파일을 삭제했다. 네 경우 모두 해당 파일의 무결성 검사 실패·비교 종료 1·동결 종료 2이며 기존 기대값은 보존됐다. 별도 폴더로 옮긴 정상 artifact는 `--artifacts` 지정 시 통과하고, 지정하지 않으면 실패했다. |
| 새 클론의 실행 안내 | Git에서 방금 클론한 상태에서 verify를 실행했다. Git 제외 예측·기록·모델 파일의 누락으로 종료 1이며 `run_all.py` 선행 안내를 출력했다. 파일을 갖춘 동일 클론은 39/39로 통과했다. |
| clean_repro의 기대값 출처 | 임시 원본 클론의 작업 트리에서 `outputs/expected/model_comparison.csv`를 잘못된 내용으로 바꾼 후 실제 `clean_repro.sh`를 실행했다. 내부 클론은 27/27로 통과했고, 사용한 기대값 전체의 파일별 해시는 커밋된 기대값과 일치했다. |

별도 검사 코드: [recheck_claude_2.py](recheck_claude_2.py). 결과: [codex_recheck_2_results.json](codex_recheck_2_results.json). 네 보완에 대한 경로별 검사와 원본 보존 확인을 합쳐 12개 항목이다. 실패가 필요한 반례에서는 비교·동결이 실패해야 검수 항목이 통과한다.

## 2. 실행 결과 재현

| 검사 | 결과 |
|---|---|
| 기존 전체 테스트 | **49 passed**, 6.49초 |
| 기존 작업 공간의 verify | **39/39**, 모든 비교 CSV의 최대 수치 차이 0 |
| 실제 `clean_repro.sh` | 커밋 `9ecbdcb` 클론, **27/27**, 1~3단계·필수 집계 20개, 실행 38.83초 |
| 실제 `clean_repro.sh --with-lstm` | 같은 커밋의 별도 클론, **39/39**, 1~5단계·필수 집계 32개, 실행 43.18초. 가이드북·공통 A/B 모두 캐시 사용 |
| 새 실행의 모델·분석 산출물 | CSV 수치 차이 0. 그림 5개와 `diagnosis.json`은 기존 Claude 산출물과 바이트 단위로 동일. 모델 A/B는 생성 시각을 제외한 모든 내용이 동일 |
| 기존 `review_checks.py` | `issue_reproduced`가 있는 11개 항목 모두 false. 필수 검사 실패 종료, 캐시 코드 변경 시 재학습, 결측 뒤 지속성 창 초기화, α별 최초 경보 위치도 일치 |

실행 환경은 `/opt/anaconda3/bin/python`, Python 3.12.2, numpy 1.26.4, pandas 2.3.3, scikit-learn 1.8.0, scipy 1.13.1, matplotlib 3.9.2, torch 2.5.1, macOS arm64, `OMP_NUM_THREADS=1`이다. 패키지 실행 코드 해시는 `362db343a42f5224e977bc81f43a7bbd5549b3d1a2d1e720b633b729404f58d7`이다.

실행 요약·파일별 비교: [codex_recheck_2_execution.json](codex_recheck_2_execution.json). 기존 반례·독립 재집계: [codex_recheck_2_legacy_results.json](codex_recheck_2_legacy_results.json).

## 3. 주 모델 독립 재집계

패키지의 평가 집계 함수와 별도로 원본 시각에서 평가 구간을 구성하고 저장 모델의 추론 결과를 직접 집계했다. 기존 예측 파일·운영점 표와 모두 일치했다.

| 분할 | 이상 탐지 구간 | 정상 알림 구간 | FP 행 | FN 행 | 전체 행 F1 |
|---|---:|---:|---:|---:|---:|
| A | 21/21 | 0/120 | 0 | 99/600 | 0.9100817439 |
| B | 21/21 | 3/180 | 3 | 86/600 | 0.9203222919 |

정상 보정 구간을 사용한 conformal α=1% 기준이다. α=1/3/5%의 최초 경보 이전 이상 관측 수는 A 64/55/55, B 55/55/55로 일치했다. 미래 행 추가 시 기존 점수의 불변성과 잘못된 입력 행의 상태 표시도 통과했다.

## 4. 변경·확인 범위

이번 작업은 검수 스크립트·관측 결과·검수 기록을 추가하고 README의 최신 기록 연결 및 남아 있던 46개·38/38 표기를 갱신했다. 구현 코드·원래 `outputs/`·동결 기대값·원래 artifacts는 변경하지 않았다. 원래 산출물과 artifacts의 파일별 해시 보존을 추가 스크립트에서 확인했다. 기존 미커밋 `yejun/analysis/press_merge_review/`도 수정·스테이징하지 않았다.

전체 LSTM의 캐시 없는 재학습을 이번에 반복하지 않았다. 그 확인은 [Claude의 이전 재학습 기록](claude_response.md)에 남아 있으며, 이번 결과를 캐시 없는 전체 재학습의 증거로 사용하지 않는다. 다른 기기·OS도 검사하지 않았다. manifest와 파일을 함께 고치는 변조, LSTM 캐시 내용 해시 미검사 등 이미 명시한 한계도 그대로다.

이 검수는 구현·재현 경로의 확인이다. 정상 하루·이상 하루의 교락, 이미 본 자료에 대한 탐색적 평가, 창 길이 탐색 이력은 해소하지 않는다. 21/21은 각 이상 기록구간에서 적어도 한 번 경보했다는 뜻이다.

대회 보고서·장별 근거·발표자료·최종 ZIP 작업은 예준의 명시적인 시작 지시 전까지 계속 보류한다.

재실행 예시(저장소 루트, `requirements.txt` 환경):

```bash
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/analysis/press_implementation_review/recheck_claude_2.py \
  --package yejun/press_submission --out /tmp/claude_recheck_2.json
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/analysis/press_implementation_review/review_checks.py \
  --package yejun/press_submission --outputs yejun/press_submission/outputs --out /tmp/legacy_recheck_2.json
```

두 스크립트는 정상 실행을 마친 로컬 패키지의 Git 제외 데이터·예측·모델 파일을 필요로 한다. `clean_repro.sh`는 PATH의 `python3`를 사용하므로 실행 전에 같은 환경을 활성화한다.
