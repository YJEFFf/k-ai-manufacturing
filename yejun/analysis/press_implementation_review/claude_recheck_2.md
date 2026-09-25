# Codex 재검수(bf246a9)에 대한 재검수 — 2026-09-25 (Claude Code)

대상: [codex_recheck.md](codex_recheck.md)와 커밋 `bf246a9`의 코드(`press/validation.py`, `verify.py`, `run_all.py`, `tools/clean_repro.sh`, 회귀 테스트). 주장을 그대로 믿지 않고 테스트·verify·반례 스크립트·1단계 재실행을 직접 돌렸고, 코드는 줄 단위로 읽었다. 보고서·장별 근거·발표자료·ZIP 작업은 하지 않았다.

**판정: 코덱스의 여섯 가지 수정(필수 검사 계약, 불완전 동결 거부, 예측 파일 무결성, 재현 스크립트 실패 전파, JSON 허용오차, 실행 식별자)은 전부 사실이고 유효하다. 다만 같은 부류의 빈틈이 넷 더 남아 있어 이번에 고쳤다.** 미해결 구현 오류는 이번 확인 범위에서 찾지 못했다. 이 판정은 보고서 착수 허가가 아니다.

## 1. 코덱스 주장의 재현

| 코덱스 주장 | 직접 확인 |
|---|---|
| 테스트 46개 통과 | **재현.** `pytest -q tests` 46 passed (9.0초) |
| 캐시 사용 1~5단계 기대값 비교 38/38, CSV 차이 0 | **재현.** `verify.py --out outputs` 38/38, 모든 CSV max\|Δ\|=0 |
| 원래 반례 `issue_reproduced` 전부 false | **재현.** `review_checks.py` 11개 항목 전부 false |
| 주 모델 독립 집계 A 21/21·0/120·F1 0.91008, B 21/21·3/180·0.92032 | **재현.** 독립 집계·CLI 예측 경로·잘못된 입력 검사 모두 일치 |
| P1 필수 검사 누락: 키 삭제·`{"steps_run":5}`로도 통과했음 | **사실.** `check_required`가 단계별 필수 항목과 분할 A/B 개별 검사를 요구하도록 바뀐 것을 코드와 회귀 테스트로 확인 |
| P1 불완전 동결: 결과 파일을 지워도 `--freeze` 성공 | **사실.** 필수 집계 32개를 계약으로 정의하고 누락 시 동결 거부·기존 기대값 보존을 확인 |
| P2 집계 밖 산출물 변조: 예측 파일을 한 행으로 바꿔도 통과 | **사실.** manifest 해시 대조로 예측·numbers·checks·그림까지 검출 |
| P2 재현 스크립트가 실행 실패를 숨김 | **사실.** 종료 코드 즉시 전파·`verify --steps N` 명시 확인 |

코덱스가 `outputs/`를 갱신하면서 남긴 흔적 하나는 짚어 둔다. 코덱스 실행의 그림 5개와 `diagnosis.json`(센서 표준편차, 최대 약 4×10⁻¹³)은 직전 Claude 실행(`e43d96b`)과 바이트가 달랐다. 내가 같은 기기의 표준 환경에서 1단계와 전체를 다시 돌리면 `e43d96b`와 **바이트 단위로 같다**(그림 5개·diagnosis.json 해시 일치). 즉 코덱스는 manifest의 환경 항목(Python·numpy·pandas·sklearn·matplotlib 버전, OMP 스레드)으로는 구분되지 않는 다른 실행 환경(글꼴 캐시·CPU 기능 분기 등으로 추정)에서 돌렸다. 수치는 허용오차 안이라 결과에 영향은 없지만, 동결·제출용 `outputs/`는 한 환경에서 만든 것을 쓰는 편이 안전하므로 이번 커밋의 `outputs/`는 내 재실행 결과로 갱신했다(CSV 차이 0, 그림·diagnosis는 `e43d96b`와 동일).

## 2. 남아 있던 빈틈과 이번 수정

| 항목 | 반례·영향 | 수정 |
|---|---|---|
| 실행 후 코드 변경 미검출 (P2) | `press/scores.py` 끝에 한 줄을 추가한 뒤 `verify.py`가 38/38 통과했다. manifest의 `code_sha256`은 기록만 되고 현재 코드와 대조하지 않았다. "이 산출물은 이 코드의 결과"라는 제출 주장을 verify가 보증하지 못함 | `code_sha256()`을 `press/validation.py`로 옮겨 run_all·verify가 공유. verify는 현재 패키지 코드 해시와 manifest를 대조하는 `code.matches_manifest`를 추가하고, 불일치 시 실패·동결 거부 |
| artifact 무결성 미검사 (P3) | `predict.py`가 읽는 `artifacts/main_A.json`·`main_B.json`은 실행 산출물이지만 manifest에 해시가 없고 verify가 보지 않았다. 변조·삭제해도 통과 | run_all이 `manifest.artifacts`에 해시를 기록하고 누락 시 필수 검사 실패. verify는 `--artifacts`(기본 `<out>/../artifacts`)에서 대조 |
| 갓 클론한 저장소에서 verify 실패 안내 부재 (P3) | 행별 예측·기록 파일은 Git 제외라 새 클론에서 `verify.py --out outputs`가 37/38로 실패하는데, README는 독립 명령처럼 안내했고 실패 메시지도 원인을 말하지 않았다 | 누락 파일이 Git 제외 대상이면 "run_all.py를 먼저 실행" 안내를 출력. README·docstring에 명시 |
| `clean_repro.sh`가 작업 트리의 `expected/`를 사용 | 클론 대신 작업 트리의 `outputs/expected`를 복사해 미커밋 기대값이 "깨끗한 클론" 비교에 섞일 수 있었다 | 클론에 커밋된 `expected/`만 사용(없으면 종료 2). 회귀 테스트로 고정 |
| 기록 | `verify.py`의 `REQUIRED_CHECKS` 상수가 더 이상 쓰이지 않는데 docstring이 참조 | 삭제, docstring 정정 |
| 기록 | `review_checks.py`의 verify 반례가 artifact 검사 추가로 실패하게 됨 | `--artifacts`로 원본 artifacts를 넘겨 반례 의미 유지 |

manifest 자체를 함께 고치는 변조는 verify가 잡을 수 없다(서명 없는 자기 참조). 이는 커밋된 manifest와 Git 이력이 기준이 되며, 코덱스 판정과 같은 한계로 남긴다. LSTM 캐시 파일 내용도 키만 검사하고 내용 해시는 없다. 캐시 없는 재학습(`--retrain-lstm`, `e43d96b` 34/34 기록)이 그 보완이다.

## 3. 수정 후 검증

| 검사 | 결과 |
|---|---|
| 전체 테스트 | **49개 통과** (코덱스 46개 + 코드 변경 검출 1, artifact 변조·삭제 2) |
| 1~5단계 재실행(LSTM 캐시)·기대값 비교 | **39/39 통과** (38 + `code.matches_manifest`), CSV max\|Δ\|=0, 총 45.8초 |
| 코드 변경 반례 | 재실행 전 옛 manifest에 대해 `code.matches_manifest`·artifact 해시 누락으로 37/39 실패 확인 |
| 코덱스 반례 재실행 | 11개 항목 `issue_reproduced` 전부 false. 독립 집계 A 21/21·0/120·F1 0.9100817, B 21/21·3/180·0.9203223 |
| `clean_repro.sh` 기본(1~3단계) | 커밋 `b7391c9` 클론에서 **27/27 통과** (1~3단계 부분 비교, 필수 집계 20개) |
| `clean_repro.sh --with-lstm`(1~5단계, 캐시) | 같은 클론에서 **39/39 통과** (1~5단계 전체 비교, 필수 집계 32개) |
| 결과 유지 | `outputs/expected/`는 재동결하지 않았다. 코드 해시는 `362db343a42f…`(코덱스 `2006b7b9ebe8…`, 동결 `3b66c92eba46…`) |

세부 관측값: [claude_recheck_2_results.json](claude_recheck_2_results.json). 환경: Python 3.12.2, numpy 1.26.4, pandas 2.3.3, scikit-learn 1.8.0, torch 2.5.1, macOS arm64.

## 4. 현재 상태

이번 확인 범위에서 미해결 구현 오류는 없다. 데이터·방법론의 알려진 한계(정상 하루·이상 하루 교락, 이미 본 자료에 대한 탐색적 평가, 창 길이 탐색 이력, 다른 OS 미검증, 21/21의 의미)는 코덱스 판정과 같이 유지한다. 보고서·장별 근거·발표자료·최종 ZIP은 예준의 명시적인 시작 지시 전까지 보류한다.
