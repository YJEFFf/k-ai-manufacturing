# 평가관 06 — 코드·재현성(10점) · cycle2 round4 최종 검수

2026-09-28. **점수 10.0/10, 감점 합계 0.0. 확인된 잔여 P0·P1·P2 없음.** 공식 문항 6의 「동일 환경에서 데이터 전처리부터 학습·추론·결과생성까지 자동 실행」을 기준으로 판단했다. 3회차 점수와 전체 목표 점수는 채점 기준으로 쓰지 않았다. 대회 보고서가 없는 것은 감점하지 않았다. 이 문서는 구현 검수 기록이다.

검수 대상은 **HEAD `6c61a88d8de437182a2cdd25f640af556a23036a` 위의 최종 미커밋 작업 사본**이다. 해당 커밋 자체의 구현을 검수한 것으로 해석하지 않는다. 복사한 416개 파일의 SHA-256은 [사본 기록](judge06_final_setup.json)에 있고, 검수 종료 때 원 작업 폴더와 다시 대조해 변경 0개를 확인했다. 최종 `model.py` 실행·동결 코드 해시는 `8b9493a24860…`이다. 평가관은 제품 코드·산출물을 수정하지 않았으며 임시 사본과 `judge06_*` 검수 기록만 썼다.

## 최종 판단과 감점

새 Python 잠금 환경에서 원본 ZIP만 입력으로 받아 **24/24단계가 종료 코드 0**으로 완료됐다. **v2 132개 시험 전부 통과**, 전체 Python 시험은 **216개 통과·선택 의존성 관련 5건 건너뜀**, 웹 회귀시험도 통과했다. 재학습한 모델·확률 보정기 4개와 예측 파일 6개는 최종 작업 사본과 바이트가 같다. 모델 4개는 3회차 기준 커밋 `061fac8`의 해시와도 같다.

| 항목 | 최종 판정 | 감점 |
|---|---|---:|
| R3-01 문서 링크·내부 검수 표기 | 해결 | 0.0 |
| R3-02 동결 요약 보호·사건/문자 열 정확 비교 | 해결 | 0.0 |
| R3-03 배치 사건의 격상 행 누락 | 해결 | 0.0 |
| R3-04 선행 파일 없는 단독 시험 | 해결 | 0.0 |
| R4-R1 비유한 값의 종류·위치 비교 누락 | 이번 검수에서 발견 후 해결·재검증 | 0.0 |
| **합계** | **10.0 − 0.0 = 10.0/10** | **0.0** |

고칠 수 있는 미해결 결함은 확인되지 않았다. 다른 OS·CPU 실측 등의 기존 검증 한계는 아래에 남기며 중복 감점하지 않았다. 점수와 기계 판독용 결과는 [judge06_result.json](judge06_result.json)에 있다.

## 3회차 항목 충족표

아래 `verify.py`·`train.py`·`tools/package_manifest.py`는 `yejun/press_guard/` 기준이며 행 번호는 이번 최종 작업 사본 기준이다.

| ID | 판정 | 독립 확인과 근거 |
|---|---|---|
| R3-01 | 충족 | 최종 재현 사본의 문서를 CommonMark 파서로 따로 읽었다. 상대 링크 **161개 중 누락 0**, 문서·lock의 내부 검수 표기 0, 팀 블라인드 검사 0건이다. 초기 `vibration_tones.csv` 링크 누락은 산출물 생성 후 해결됐다. 없는 링크를 임시 README에 넣으면 팀 검사도 실패한다. `tools/package_manifest.py:133·137`, [최종 대조](judge06_final_checks.json), [선행 탐침](judge06_preflight.json). |
| R3-02 | 충족 | 실제 동결 요약의 `alarm_rows`·`sha256`·`exact_sha256`를 각각 바꾸면 전체 verify가 **종료 1**이며 `expected.integrity`에서 해당 요약 변경을 잡는다. 사건 번호·시작 알림·격상 알림·최대 센서·시각·확률 출처·운전 상태 **7개 열의 행 맞바꿈도 모두 검출**한다. 명시되지 않은 새 문자열 열도 선행 탐침에서 검출했다. `verify.py:38·75·120·145`, [최종 대조](judge06_final_checks.json), `judge06_final_digest_*.log`. |
| R3-03 | 충족 | `train.py:114·117`에서 건 대기열과 같은 흐름의 예측을 사건 집계에 넘긴다. A·B 사건 표의 2단계 `escalation_row`가 각각 **4092·6098**이고, 테스트 예측 파일의 `incident_escalation=1`인 **0기반 전체 행 위치**와 일치한다. B의 1단계 사건 3개에는 격상 행이 비어 있어 맞다. [독립 재계산](judge06_final_checks.json). |
| R3-04 | 충족 | Git 없는 최종 소스 사본에서 ① 원본·모델 모두 없음, ② 원본만 있고 모델 없음의 두 조건을 직접 시험했다. `press_evidence/advance/supervised/selection/supplement` 계약 시험은 조건마다 **39건(6·8·6·6·13) 건너뜀, 5개 호출 모두 종료 0**이며 `reproduce.py` 안내를 낸다. 추적 출력 0이다. 최종 재현 뒤에는 계약 시험들이 통과하며 UCI 관련 3건만 명시적으로 건너뛴다. [최종 소스 선행 파일 검사](judge06_final_prerequisites.json), `judge06_final_prereq_{no_inputs,raw_data_only}_*.log`, 최종 단계 18~23 로그. |

## 이번 회차에서 찾고 해결한 결함

**R4-R1, P2, 수정 가능한 검증 결함.** 다른 기기용 허용오차 비교는 실수 열의 유한 값 개수·합·제곱합·범위만 보았으므로 `NaN`과 무한대의 종류·위치를 놓쳤다. 실제 B 예측 파일의 `current_residual`·`g_waveform`·`g_dynamics` 각각에서 `NaN→+inf`, `NaN→−inf`, `NaN 위치 맞바꿈`을 만들었고 초기 **9/9가 잘못 통과**했다. 같은 기기에서 실행 기록 해시는 변조를 잡으므로 P0·P1로 분류하지 않았다.

수정 후에는 각 실수 열의 유한 값/NaN/+inf/−inf 종류 배열을 정확 해시한다(`verify.py:43~52·75`). **최종 사본의 실제 동결 요약을 기준으로 9/9를 모두 검출**했다. 실수 허용오차 탐침인 점수 한 셀 `+1e-4`, 우도비 한 셀 `×1.001`은 기존 문서에 적힌 요약 허용오차 범위에서 통과한다. 경보·사건·문자 열의 정확 비교와 비유한 값 보호는 유지된다.

- 반례·재검수 스크립트: [judge06_nonfinite_probe.py](judge06_nonfinite_probe.py)
- 수정 전: [judge06_nonfinite_pre.json](judge06_nonfinite_pre.json)
- 최종 동결값 검수: [judge06_nonfinite_final.json](judge06_nonfinite_final.json), [로그](judge06_nonfinite_final.log)

## 새 환경에서 수행한 24단계

macOS 26.3.1 arm64, Python **3.12.8 새 venv**, `requirements-lock.txt`를 `pip install --no-deps`로 설치했다. `pip check`가 통과했고 torch·사용자 site·별도 PYTHONPATH가 없는 환경이다. Node는 22.14.0이다. BLAS/OpenMP와 `PRESS_THREADS`는 1로 고정했다.

사본에 `.git`, 원본 CSV, 저장 모델이 없었고 현재 v2 계산 결과도 제거했다. 동결 기대값·기준모델 비교 결과·문서용 콘솔 화면은 남겼다. 주최 ZIP의 SHA-256은 `0bf0e7a2de0c7622cffdab426fd42deab20078b6f4c724815a87b802f7b8f5fa`이며 `--data`로 원본을 배치했다. 동일 ZIP을 입력 배치 시험이 찾는 사본 내 경로에도 두어 해당 시험까지 실행했다.

실행 명령은 다음과 같다. Python은 위 새 venv의 실행 파일이다.

```bash
python yejun/press_guard/reproduce.py --data "Dataset_소성가공 예지보전 AI 데이터셋.zip" --tests
```

단계 합계 **893.4초**, 최초 라이브러리 로드를 포함한 명령 실측 **941.77초**였다. 동시에 다른 사본 재현이 실행됐으므로 독점 부하의 속도 측정은 아니다. 단계별 명령·시간·종료 코드는 [전체 결과](judge06_final_repro.json), [실행 로그](judge06_final_repro.log), `judge06_final_step_01.log`~`24.log`에 있다.

| 단계 | 확인 | 결과 |
|---:|---|---|
| 1 | v1 주 모델·기준모델 재학습, 행별 예측 | 통과 |
| 2 | v1 빠른 경로 동결 비교 | 16/16, 1~2단계 부분 비교 |
| 3 | v2 학습·시간순 5회 | 통과 |
| 4 | v2 분석 | 통과 |
| 5 | 실행 audit | 16/16 |
| 6 | v2 동결값 비교 | 53/53 |
| 7 | 진단 표 재생성 | 통과 |
| 8 | 보강 진단 표·그림 | 표 22개·그림 5장, 통과 |
| 9 | 지도학습 기준선 재생성 | 통과 |
| 10 | 모델 선정 근거 재생성 | 통과 |
| 11 | press_evidence 계약 | 결과 44개, 통과 |
| 12 | press_supervised 계약 | 결과 3개, 통과 |
| 13 | press_advance 계약 | 결과 2개, 통과 |
| 14 | press_selection 계약 | 결과 12개, 통과 |
| 15 | 보완 실험 동결 비교 | E1·E3 통과, E2는 외부 ZIP 없음 안내와 함께 건너뜀 |
| 16 | v2 전체 pytest | **132 passed, 0 skipped**, 94.81초 |
| 17 | v1 pytest | 44 passed, 2 skipped |
| 18 | press_advance 계약 시험 | 8 passed |
| 19 | press_evidence 계약 시험 | 6 passed |
| 20 | press_evidence 진단 시험 | 4 passed |
| 21 | press_selection 계약 시험 | 6 passed |
| 22 | press_supervised 계약 시험 | 6 passed |
| 23 | press_supplement 계약 시험 | 10 passed, 3 skipped |
| 24 | 웹 콘솔 회귀시험 | 통과 |

최신 `test_simulation_view.py`는 실제 `test_web_prefix.cjs`를 실행해 관측 접두부의 화면 집계를 대조했고, `test_time_order.py`의 역순 시각 판정보류·회복·사건 분리 시험도 v2 132개에 포함된다.

앞서 실패했던 `test_analyze.py::test_verify_detects_tampering`와 `test_review_regressions.py::test_v1_rerun_does_not_break_v2_verify`는 재생성 진행 중 실패로 기록됐었다. 최종 동결 후 팀의 [두 시험 재확인](field_final_two_tests.json)은 **2 passed(3.31초)**이며, 이번 별도 사본에서도 두 시험을 포함한 **132개 전체가 통과**했다. 이번 실행은 재생성과 시험을 순차 수행했다.

## 건너뜀과 보완 시험

새 환경의 Python 합계는 **216 passed, 5 skipped**다. 웹 시험은 별도이며 Python 합계에 넣지 않는다.

| 건너뜀 | 이유 | 선택 의존성을 갖춘 호스트의 보완 결과 |
|---|---|---|
| v1 2건 | 잠금 환경에 torch가 없다. LSTM 시험 모듈 단위 1건과 캐시 서명 시험 1건이며, 모듈 안 개별 시험까지 합하면 미실행 범위는 5개다 | v1 전체 **49 passed**, 9.33초 |
| 보완 실험 3건 | 기본 데이터만 넣은 사본에는 UCI 유압 ZIP이 없어 E2 변조 사례 3개를 건너뛴다 | 보완 계약 전체 **13 passed**, 2.82초 |

호스트 보완 시험은 주 담당자가 실행했고 평가관은 [host_final_optional_tests.json](host_final_optional_tests.json)과 로그를 확인했다. 중복 범위를 빼면 최종 Python 시험 범위는 **224개**다(v2 132 + v1 49 + 분석 43). 새 환경의 216개와 호스트의 49·13개를 단순 합산하지 않았다. `Matplotlib/pyparsing`의 기존 폐기 예정 API 경고 14건은 v1 단계에 있었으며 실패는 없었다.

## 파일·지표·문서 독립 대조

| 대상 | 결과 |
|---|---|
| 재학습 모델·보정기 4개 | 최종 작업 사본 및 3회차 `061fac8`의 SHA-256과 모두 동일 |
| 예측 파일 6개 | 최종 작업 사본과 모두 바이트 동일 |
| 코드·문서·동결 기대값 268개 | 재현·시험 전후 변경 0 |
| A 평가 파일 | 4,690행, TP 556·FP 0·FN 44, **F1 0.9619377162629758**, 정상 알림 0/120 |
| B 평가 파일 | 6,697행, TP 569·FP 3·FN 31, **F1 0.9709897610921502**, 정상 알림 3/180 |
| `predict.py --split A/B --chunk 7` | 두 파일 모두 학습 실행의 테스트 예측 SHA-256과 동일 |
| 동결 요약 필드 변조 | 3/3 검출, 전체 verify 종료 1 |
| 사건·문자·상태 열 변조 | 7/7 검출 |
| NaN·무한대 종류/위치 변조 | 9/9 검출 |
| 실행 후 Git 없는 사본의 문서 | 상대 링크 161개, 죽은 링크 0, 내부 검수 표기 0, 블라인드 실패 0 |

근거: [judge06_final_checks.json](judge06_final_checks.json), [대조 로그](judge06_final_checks.log), [A 추론](judge06_final_inference_A.log), [B 추론](judge06_final_inference_B.log). A·B 테스트 파일의 SHA-256은 각각 `2941bf9dde2c9b66308eb6e26d19e4a41f93de1441833c8b476e0534e47e98c8`, `9bd02a7cf086ad9ff81542166c2af768aefee944d4385e343a2d771d8a2f5524`다.

제출 목록 전체의 복사 시험은 주 담당자가 다른 임시 폴더에서 수행했다. [package_copy_final.json](package_copy_final.json): **479개·18.1 MB, 블라인드 통과, 15/15단계, 종료 0, 실측 806.69초**. 이 평가관은 저장 모델·현재 결과가 없는 소스 사본과 새 잠금 환경을 검수했다. 실행 후 Git 없는 탐색 목록은 480개이며, 실제 제출 목록과 수를 혼동하지 않는다.

## 검증 범위와 현재 자료의 한계

| 구분 | 범위 | 감점 처리 |
|---|---|---|
| 다른 OS·CPU | 직접 실측은 macOS arm64다. CP949 등 이식성 시험은 포함되지만 다른 OS·CPU의 실제 실행을 이번 결과로 주장하지 않는다 | 기존 한계, 중복 감점 없음 |
| 비교용 LSTM 전체 재학습 | 이번 독립 실행은 최종 모델 빠른 경로와 전체 시험이다. `--full`의 LSTM 전체 재학습 시간·새 기기 결과를 이번 회차에서 다시 측정하지 않았다. torch 시험은 호스트에서 모두 통과했다 | 검수 범위 명시, 추가 감점 없음 |
| 외부 UCI 자료 | 기본 사본에서 E2의 명시적 건너뜀을 확인했다. UCI 원본이 있는 호스트의 E2 계약 시험·엄격 검증은 별도 기록이다 | 같은 자료 결핍을 중복 감점하지 않음 |
| 독립 현장 테스트셋 | 제공된 A/B 평가 구간은 팀이 정의한 분할이며 별도 현장 시험셋은 없다 | 데이터·모델 평가에서 다루는 기존 한계, 재현성 중복 감점 없음 |

검수 재실행에 사용한 코드는 [환경 준비](judge06_environment.py), [새 사본 전체 재현](judge06_final_repro.py), [파일·지표 대조](judge06_final_checks.py), [최종 선행 파일 검사](judge06_final_prerequisites.py), [비유한 값 반례](judge06_nonfinite_probe.py)에 보존했다. 환경·사본 경로와 명령은 해당 JSON·로그에 있다. ZIP 제출물과 대회 보고서는 생성하지 않았다.
