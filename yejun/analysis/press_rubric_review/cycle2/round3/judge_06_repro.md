# 평가관 06 — 코드 및 재현성(10점) 검수 · cycle2 round3

2026-09-28. **기준 커밋 `061fac8`**(`061fac8ae9a8373265434a5586cde956982db934`). 검수 시작과 끝에 HEAD를 확인했고 바뀌지 않았다. 모든 실행은 기준 커밋의 새 클론, `git archive` 사본, 제출 목록 사본에서 했다. 행 번호는 기준 커밋 기준이다.

- **기준.** `official_task_extract.txt:88-89`의 「동일 환경에서 데이터 전처리부터 학습·추론·결과생성까지 자동 실행」(10점)이다. 제출물 요건(`:53-57`: 소스코드와 requirements.txt 또는 environment.yml, 학습용 데이터, README, 테스트데이터 예측결과 파일)과 블라인드 규칙(`:50`)도 재현성 관점에서 봤다.
- **범위.** 보고서가 없는 것은 감점하지 않았다. 제출 ZIP은 만들지 않았다. 목록 도구의 `--copy-test`와, 평가관이 목록대로 따로 복사한 사본으로 대신했다.
- **기록.** 이 문서는 검수 기록이며 대회 보고서가 아니다. 이 폴더의 `judge06_*`와 이 문서 말고는 아무것도 쓰지 않았다. 클론·가상환경·실행 산출물은 시스템 임시 폴더에 두었다.

## 점수: 9.7/10 (범위 9.5~9.8)

- **2회차 P0·P1(R2-01~R2-03)은 모두 풀렸다.** 2회차 항목 8개 중 7개가 충족, 1개(R2-08 문서)가 부분이다.
  - 제출 목록만 복사한 빈 폴더에서 한 명령이 15/15로 돈다(팀 도구 `--copy-test`). 평가관이 따로 복사한 목록 사본에서 README 빠른 시작 3행을 문자 그대로 붙여 `--tests`까지 23/23이다. 2회차에는 8/15에서 멈췄다.
  - 한국어 Windows 모의(CP949 + `resource` 차단)에서 `--tests`가 23/23이다. 단계 로그의 깨진 글자(U+FFFD)는 0개다.
  - 파이썬 3.10·3.13·3.14는 설치 안내 한 줄을 내고 멈춘다(추적 출력 0). 3.11.15와 3.12(3개 빌드)에서 통과한다.
- **11개 실행 조건에서 모두 통과하고 결과가 비트 단위로 같다.** 조건: git 없는 사본+빈 conda 환경, 새 클론+lock `--no-deps` 가상환경, CP949, 목록 사본 2종, 공백·한글 경로+다른 시간대, autocrlf 클론, clean_repro.sh, 파이썬 3.11, 부하 측정 사본, `--full`. 저장 모델·보정기 4개와 행 단위 예측 6개가 모든 실행에서 커밋된 동결 해시와 같다. 파일만으로 다시 계산한 F1도 A 0.961938(556/0/44)·B 0.970990(569/3/31)로 같다.
- **감점(−0.3).** 모두 P2다.
  1. 제출 목록 문서에 죽은 링크 10개와 내부 검수 표기 4행이 남았다(R3-01, −0.1).
  2. 행 단위 예측 동결 요약(`expected/predictions_digest.json`)만 동결값 무결성 검사 밖이다. 요약의 해시 필드 하나를 0으로 바꿔도 verify가 통과한다. 다른 기기 경로에서는 사건 알림 열과 문자 열을 비교하지 않는다(R3-02, −0.1).
  3. 배치 결과의 사건 표에서 2단계 사건의 `escalation_row`가 비어 있다. 분석 패키지 시험은 선행 파일이 없으면 추적 출력을 내며 실패한다(R3-03·R3-04, −0.1).
- **범위.**
  - 하한 9.5: 평가위원이 v1 README 첫 줄의 죽은 링크(PLAN.md·내부 검수 문서)를 따라가거나, 한 명령 전에 분석 README의 pytest 명령을 먼저 치는 경우다.
  - 상한 9.8: 평가위원이 press_guard README만 따르는 경우다. 그러면 모든 단계가 통과한다.
- **2회차 9.0 대비 +0.7.** R2-01(−0.5)·R2-02(−0.2)·R2-03(−0.2)이 풀려 +0.9다. 문서 잔여(−0.1)는 R3-01로 남았다. 새로 찾은 P2(R3-02~R3-04)가 −0.2다.
- '다른 OS·CPU 실측 없음'은 1회차에서 한 번 반영했으므로 다시 감점하지 않았다.

## 상위 8팀 대비 위치

**이 항목에서 상위 8팀 중 1위다.** 2회차의 남은 위험(목록 사본 8/15)이 사라졌다.

- 이 과제의 흔한 상위권 제출물은 가이드북 LSTM-AE 또는 라벨 지도학습(SMOTE·앙상블·SHAP) 노트북과 requirements.txt다. 셀을 순서대로 눌러야 하고, 난수·GPU 때문에 같은 숫자가 다시 나온다는 보장이 없다. 테스트 예측 파일을 파일만으로 재채점할 수 있게 만든 팀도 드물다.
- 이 팀은 다음을 직접 증명한다. 경쟁 팀이 따라오기 어려운 수준이다.
  - 원본 ZIP 한 개와 한 명령으로 전처리·학습·추론·테스트 예측·분석·동결값 비교까지
  - 파이썬 빌드 4종, CP949, autocrlf, 공백·한글 경로에서 모델·예측 비트 동일
  - 제출 목록만으로 재현, 목록 누락·절대 경로를 잡는 블라인드 검사
  - 평가관이 따로 만든 변조 54개 중 53개가 설계대로 판정(나머지 1개는 R3-02)
- 남은 결함은 문서 링크와 검증 세부다. 평가위원이 README 한 명령을 실행하는 흐름에는 영향이 없다.

## 감점 내역표

| 감점 사유 | 감점 | 고칠 수 있음/한계 |
|---|---:|---|
| 제출 목록 문서의 죽은 링크 10개, 내부 검수 표기 4행(2회차 R2-08·1회차 R10 잔여) | −0.1 | 고칠 수 있음(R3-01) |
| 행 단위 예측 동결 요약: 요약 파일 자체의 무결성 검사 없음(요약 손상 3종 통과: `alarm_rows`+1, `sha256`만 0, `exact_sha256`만 0), 다른 기기 경로에서 사건 알림 열(`incident_*`)·문자 열 미비교 | −0.1 | 고칠 수 있음(R3-02) |
| 배치 결과 `incidents_{A,B}.csv`에서 2단계 사건의 `escalation_row`가 빔(콘솔 경로는 채움), 분석 패키지 시험이 선행 파일 없을 때 안내 없이 실패 | −0.1 | 고칠 수 있음(R3-03·R3-04) |
| **합계** | **−0.3** | 10 − 9.7 = 0.3 |

## 2회차 항목 충족표

행 번호는 기준 커밋 기준이다. 실행 기록은 이 폴더의 `judge06_Q*.log`에 있다.

| ID | 판정 | 근거(파일:행 또는 재계산 값) |
|---|---|---|
| R2-01 제출 목록 | **충족** | 목록 464개·16.9 MB, 블라인드 검사 통과(Q5a). 최상위가 `yejun/`이다(`package_manifest.py:90·94`). 동결 요약은 필수 파일이다(`:58-60`). 제외 규칙은 `^press_guard/outputs/predictions_`로 좁혔다(`:55-57`). ① 팀 도구 `--copy-test`: 빈 임시 폴더에서 15/15, 1,343.1초(Q5b). ② 평가관 목록 사본: README 16행을 README에서 읽어 zsh로 그대로 실행하고 `--tests`를 붙여 23/23, 1,044.5초(Q5c). ③ 두 사본 모두 verify 53/53(행 단위 예측 요약 포함). ④ 목록 사본의 `predict.py --split` SHA-256이 동봉본과 같다(A `b87f1e20…`, B `8ad05ed2…`). ⑤ 블라인드 검사가 실제로 잡는다: 의존 묶음 한 줄 삭제, 동결 요약 제외, 실행 기록 JSON의 절대 경로(Q6c M1~M3) |
| R2-02 CP949 `--tests` | **충족** | 새 클론 + `LC_ALL=ko_KR.CP949`(utf8_mode 0, stdout cp949) + `resource` 차단에서 23/23, 2,266.0초. v1 시험 49개 통과(Q3). `test_review_regressions.py:223-225`에 bash 확인과 `encoding="utf-8"`이 있다. 정적 검사 범위가 press_submission까지 넓어졌다(`test_portability.py:17-18`). 평가관 AST 검사로도 팀 범위 74개 파일에 인코딩 누락은 git 호출 2건(ASCII 출력)뿐이다 |
| R2-03 파이썬 판 | **충족** | 패키지 없는 3.10.20·3.13.13·3.14.6에서 `reproduce.py`가 종료 코드 1과 안내 한 줄을 낸다. 추적 출력은 0이다(Q9a). 3.10 가상환경에서 uv 해석은 불가다: requirements.txt는 scikit-learn 1.8.0, lock은 contourpy 1.3.3이 Python≥3.11을 요구한다. 문구(`README.md:14`, `runtime.py:6·17·41-42`, `requirements.txt:1`)와 시험(`test_portability.py:79-87`)이 3.11~3.12로 맞는다. 3.11.15 + lock `--no-deps`에서 23/23, 비트 동일(Q9c) |
| R2-04 로그 인코딩 | **충족** | 자식 환경에 `PYTHONIOENCODING=utf-8`이 있다(`reproduce.py:87-88`). CP949 실행의 단계 로그 23개와 요약 `last_line`에 U+FFFD가 0개다. 요약에 한글이 그대로 남는다(Q3) |
| R2-05 verify 설명 | **충족** | README:192와 `verify.py:8-9`가 구현(`:37-73`)과 같다. 다른 기기 경로(동결 요약만 대조)에서 설명대로 판정한다: 경보 0→1, 근거·단계 변경, p값 +1e-4는 잡고, 점수 +1e-4·우도비 ×1.001·점수 두 행 맞바꿈은 통과한다(합·제곱합 상대 1e-7 안). 같은 기기에서는 실행 기록 해시가 모든 바이트 변경을 잡는다(V1·V1b). 새 사건 열의 검출 범위는 R3-02로 따로 둔다 |
| R2-06 선행 파일 안내 | **충족** | 학습 전 새 클론에서 12가지 호출이 모두 종료 코드 2, stderr 한 줄, 추적 출력 0이다(Q6b). 호출: 4개 패키지 계약, `--rerun`, `--freeze`(동결 파일 변경 0), 보완 verify 기본·`--strict`·`--rerun`, 저장소 루트에서 부르기, 원본만 있고 저장 모델이 없는 부분 상태 2개. 구현은 `package_contract.py:338-344·364-367`, `press_supplement/verify.py:129-134`다. 팀 시험 파일은 R3-04 |
| R2-07 Windows 줄바꿈 | **충족** | `yejun/.gitattributes:2`(`* text=auto eol=lf`). `core.autocrlf=true` 클론에서 CRLF 파일 0/1,182, git status 변경 0이다(Q10). 커밋 상태에서 v2 기대값 무결성 0건, 4개 패키지 계약·보완 verify가 통과한다. 원본은 주최 측 ZIP에서, 저장 모델은 커밋 manifest 해시와 같은 사본을 넣었다. 같은 클론의 한 명령 재현은 15/15, 비트 동일이다 |
| R2-08 문서 잔여 | **부분** | 됨: README 빠른 시작에 `&&`와 HISTORY 링크가 없다(`README.md:9·14-16`). v1·선정 README의 POSIX 환경변수 접두가 사라졌다. 분석 README의 `export` 줄에는 PowerShell 대안이 병기됐다. lock에 cloudpickle·colorama가 들어갔다(`requirements-lock.txt:3-4`). `pip install --no-deps -r requirements-lock.txt` 뒤 `pip check` 통과, 시험 23/23(3.12.8·3.11.15)이다. `--full` 시간 문구도 고쳤다(`reproduce.py:4-5`). 안 됨: 목록 문서에 죽은 링크 10개, 내부 표기 4행(R3-01) |
| (1회차 R3) 제출 묶음 | **충족** | R2-01로 해결됐다 |
| (1회차 R4) 의존성 | **충족** | R2-03과 lock 보완으로 해결됐다. environment.yml로 만든 빈 conda 환경(98초, conda-forge 3.12.14)에서 15/15다(Q1) |
| (1회차 R10) 문서 정정 | **부분** | R2-08과 같다 |

## 강점 — 직접 확인

| 강점 | 파일:행 | 직접 확인 |
|---|---|---|
| 한 명령 재현 | `press_guard/reproduce.py:31-62`(단계), `:72-81`(판 확인·ZIP 배치·입력 오류 안내), `:87-111`(자식 환경·단계 로그·요약·종료 코드) | 11개 실행 모두 통과: 15/15 6회, 23/23 4회, `--full` 1회(아래 검증표). 모든 단계 로그가 `yejun` 기준 상대 경로다 |
| 제출 목록 도구 | `press_guard/tools/package_manifest.py:33-60`(묶음·제외·필수), `:98-117`(실행 기록 인용 수집), `:120-132`(블라인드 검사), `:135-146`(복사 시험), `:155-157`(ZIP 보류) | 목록 464개로 두 사본 모두 재현했다. 누락 의존·필수 파일 제외·JSON 절대 경로를 잡는다. 비어 있지 않은 폴더로는 복사 시험을 거부한다(Q6c). git 없는 사본에서 계산한 목록(466개)도 블라인드 검사를 통과한다. 차이는 v1 저장 모델 2개가 더 들어간 것뿐이다 |
| 환경 간 비트 동일 | `runtime.py:21-35`(스레드 고정), `:55-65`(BLAS 기록), `.gitattributes:2` | 파이썬 3.11.15·3.12.2·3.12.8·3.12.14, CP949, autocrlf, 공백·한글 경로 + `TZ=America/Los_Angeles`에서 저장 모델 4개·예측 6개가 커밋 해시와 같다. 빠른 경로 실행에서는 press_guard 결과 43개와 v1 결과 30개도 바이트가 같다. press_evidence 표 4개만 1e-16~7e-15 차이였고 계약 허용오차(1e-9) 안이다 |
| 테스트 예측 파일 | `README.md:61-83`, `train.py:72`, `predict.py:52-62` | 파일만으로 F1 재계산(A 0.961938, B 0.970990). 이상 600행 식별자가 두 파일에 같다. `predict.py --split`이 학습 없이 같은 SHA-256을 만든다(클론·목록 사본·CP949) |
| 변조 검출 | `press_guard/verify.py:57-73·99-117`, `analysis/package_contract.py:102-149·178-240`, `press_supplement/verify.py:32-46` | 평가관 변조 54개 중 53개가 설계대로 판정됐다(Q6). 결과 CSV와 행 단위 예측을 결과·실행 기록·동결값까지 함께 위조해도 audit·analysis 연결 검사가 잡는다(Q6d V8a·V8b) |
| 실행 기록의 상대 경로 | `press_submission/run_all.py:40-51·344-345`, `analysis/press_advance/run_experiment.py:46-53·95` | 목록 안 실행 기록에 절대 경로가 0개다. 커밋 상태와 임시 폴더 실행 뒤(Q1·Q2·Q5c)에 모두 확인했다. 절대 경로가 남는 `reproduce_summary.json`은 목록에서 빠진다 |
| 운영 도구의 이식성 | `predict.py:38-74`, `simulate.py:59`, `monitor.py:181-221`, `recalibrate.py:129`, `serve.py` | CP949 + `resource` 차단에서 모두 통과했다: 한글 파일 이름 입력(monitor), 웹 콘솔 HTTP 200 세 번(overview audit 16/16, 혼합 B 6,697행, 업로드 600행·사건 1) |
| 블라인드 규칙 | 목록 464개 | 한 명령 재현 뒤 목록 사본의 텍스트 440개에 사용자명·이메일·디스크 이름이 0개다. 개발 기기 경로 패턴(`/Users/`·`/Volumes/`)은 검사 도구 자신의 정규식 정의(`package_manifest.py:14·61`)에만 있다(`judge06_Q5_blind_identity.log`) |

## 수정·보완 목록

경로는 `yejun/` 기준이다. 모델·문턱·분할·주 지표를 바꾸는 일은 완료 기준이 아니다. ZIP 생성과 보고서 작성도 완료 기준이 아니다. **P0·P1은 없다.**

| ID | 우선 | 분류 | 위치(파일:행) | 해야 할 일 | 완료 기준 | 예상 회복 |
|---|---|---|---|---|---|---:|
| R3-01 | P2 | 제출 문서 | `press_submission/README.md:3`(PLAN.md, 목록 제외), `:5·7·9`(press_implementation_review), `:63`(press_dayshift README); `analysis/press_evidence/README.md:42`, `analysis/press_selection/README.md:158`, `analysis/press_supplement/README.md:3·36·111`; 내부 표기 `press_evidence/README.md:10·328`("사이클2"), `press_supplement/README.md:36`(press_rubric_review 링크), `press_guard/requirements-lock.txt:2`("루브릭 사이클2 평가관 06 Phase D") | 목록 문서의 링크 대상을 목록에 넣거나(press_dayshift·press_early README, press_external/acquisition.json) 링크를 풀어 쓴다. 검수 기록 링크와 내부 표기는 지운다. 블라인드 검사(`package_manifest.py:120-132`)에 목록 문서의 상대 링크 대상 존재 검사를 넣는다. README:196에 `--copy-test`와 실행 기록 인용 검사를 적고, README:21의 23단계는 node가 있을 때라고 적는다(없으면 22단계) | 목록 문서 18개의 상대 링크 159개 중 죽은 링크 0개(`judge06_Q5_docs.py`), 내부 표기 0행. 블라인드 검사가 링크 하나를 일부러 깨면 실패한다 | 0.1 |
| R3-02 | P2 | 검증 세부 | `press_guard/verify.py:33`(EXACT_COLUMNS), `:37-48`(prediction_digest), `:107-117`(expected_integrity가 동결 요약을 보지 않음); `README.md:71·192` | ① 동결 요약(`expected/predictions_digest.json`)의 해시를 동결 manifest나 별도 lock에 넣고 verify가 대조한다. 동결 결과 CSV는 이미 이렇게 보호된다(V4·V8a). 지금은 요약의 `sha256`이나 `exact_sha256` 하나만 0으로 바꾸거나 `alarm_rows`를 +1 해도 통과한다(V6b·V6c·V6d). ② 정확 비교 열을 '실수가 아닌 모든 열'로 넓힌다. 적어도 사람에게 가는 알림인 `incident_notification`·`incident_escalation`·`incident_id`와 `magnitude_sensor`·`timestamp`는 넣는다. 지금은 다른 기기 경로에서 사건 알림 행 이동, 사건 번호 맞바꿈, 크기 최대 센서·시각·확률 출처 변경이 모두 통과한다(V7) | 평가관 탐침 V6b~V6d와 V7의 사건·문자 열 6종이 모두 실패로 판정된다. 기존 통과 탐침(점수 +1e-4 등)은 README:192의 설명대로 판정된다 | 0.1 |
| R3-03 | P2 | 결과 생성 | `press_guard/train.py:117`(`incidents(queue)`에 예측을 넘기지 않음), `model.py:517-523`, 비교 `serve.py:65` | 배치 결과의 사건 표에 예측(정상 평가 뒤 이상을 이은 같은 행 번호)을 넘겨 `escalation_row`를 채운다. 지금 `incidents_A.csv`·`incidents_B.csv`에서 2단계(점검 요청) 사건 A 1건·B 1건의 `escalation_row`가 비어 있다. 1단계 사건은 격상이 없어 빈 값이 맞다. 같은 사건의 테스트 예측 파일에는 격상 행이 있다(A 행 4092, B 행 6098). 콘솔은 값을 채운다. 고친 뒤 audit를 통과한 실행으로 다시 동결한다 | 두 사건 표에서 2단계 사건의 `escalation_row`가 테스트 예측 파일의 `incident_escalation=1` 행 번호와 같다. verify 통과 | 0.05 |
| R3-04 | P2 | 단독 시험 | `analysis/press_{evidence,supervised,selection}/test_contract.py:16`, `analysis/press_supplement/test_contract.py:70·113` | 원본·저장 모델이 없으면 `package_contract.missing_prerequisites()`로 확인해 `pytest.skip(FIRST_RUN_HINT)`로 건너뛴다. 지금은 원본만 있는 상태에서 5개 시험 파일 중 4개가 FileNotFoundError·assert 추적 출력으로 실패한다(Q6b). 분석 README가 이 pytest 명령을 안내한다(예: `press_evidence/README.md:12`) | 학습 전 새 클론에서 5개 시험 파일이 실패 없이 '건너뜀 + 안내'로 끝난다. 한 명령 재현 뒤에는 지금처럼 모두 통과한다 | 0.05 |

## 수정 불가 한계

1·2회차 한계는 그대로다. 감점을 다시 하지 않았다.

| 한계 | 내용 |
|---|---|
| 다른 OS·CPU 실측 | 이 기기는 macOS arm64 한 대다. Windows 조건(CP949·`resource` 부재·줄바꿈·공백 경로)은 모의만 했다. 비트 동일은 이 기기의 파이썬 빌드 4종에서 확인했다. 다른 CPU·BLAS에서는 부동소수 차이가 순위 p값을 바꿀 수 있다. 그래서 허용오차와 경보 정확 비교로만 보장한다 |
| LSTM 재학습 | PyTorch 결과는 기기·빌드마다 다를 수 있다. 비교용 기준모델이라 최종 모델 수치에는 영향이 없다 |
| 외부 자료 | UCI 유압 자료(73 MB)는 제3자 배포물이라 획득 스크립트와 해시(e2_manifest의 입력 해시)로 대신한다. 없으면 E2를 건너뛴다 |
| 테스트셋 정의 | 공식 별도 테스트셋이 없다. 테스트 예측 파일은 팀이 정한 분할 A/B의 평가 구간이다(README:61-63) |
| 부하 없는 시간 | 다른 평가관 실행이 겹쳐 부하 없는 조건을 만들 수 없었다. 부하 평균 5.0(최대 7.3)에서 856.8초였다(README:21의 572초의 1.5배). 1회차부터 같은 한계다 |

## 직접 수행한 검증

스크립트와 로그는 모두 이 폴더에 있다. 임시 폴더는 `J06_BASE`(이 세션의 scratchpad/judge06r3)다. 파이썬은 기본으로 `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python`(3.12.2)을 썼다. Q1·Q2·Q5·Q9·Q12는 새 환경의 파이썬을 썼다. 새 사본은 원본을 주최 측 ZIP(`--data`) 하나나 원본 CSV 두 개로만 받았다. 기기는 Apple M2 8코어, macOS 26.3.1이다. 다른 평가관 실행과 겹쳐 1분 부하 평균이 2~42 사이였다. 각 단계의 부하는 로그의 `load_start/load_end`에 있다.

| 단계 | 스크립트 | 조건 | 결과 | 시간 |
|---|---|---|---|---|
| Q1 | `judge06_Q1_archive_conda.sh` | git archive 사본(.git 없음) + `conda env create -f environment.yml`(conda-forge 3.12.14, 캐시 새로) + 원본 CSV 2개만 넣고 `python yejun/press_guard/reproduce.py` | 환경 98초. 15/15, 비트 동일. git 없는 사본의 목록 466개, 블라인드 통과 | 1,979.4초 |
| Q2 | `judge06_Q2_clone_lock_tests.sh` | 새 클론 + python.org 3.12.8 venv에 `pip install --no-deps -r requirements-lock.txt`(torch 없음, `pip check` 통과) + ZIP을 현재 폴더에 두고 README 16행 그대로 + `--tests` | 23/23: v2 83·1 건너뜀, v1 44·2 건너뜀, 분석 8·6·6·6·10(+3 건너뜀), 웹 11 | 2,234.0초 |
| Q3 | `judge06_Q3_cp949_nores.sh` | 새 클론 + `LC_ALL=ko_KR.CP949`(PYTHONUTF8 없음) + `resource` 차단 + `--data` ZIP + `--tests`, 운영 도구 7종 | 23/23(v1 시험 49), 단계 로그 U+FFFD 0. predict·simulate·monitor(한글 파일 이름)·recalibrate·목록 도구·웹 콘솔 HTTP 모두 통과 | 2,266.0초 |
| Q4 | `judge06_Q5_package.sh` 앞부분 | Q2 사본에서 `predict.py --split A/B` | SHA-256이 학습 실행·커밋 동결 요약·커밋 manifest와 모두 같다 | 12초 |
| Q5 | `judge06_Q5_package.sh`, `judge06_Q5_docs.py`, `judge06_Q7_abs_paths.py` | 목록·블라인드 검사, `--copy-test`(빈 임시 폴더), 평가관 목록 사본에서 README 16행 그대로 + `--tests`, 문서 링크 검사 | 목록 464개. 복사 시험 15/15. 목록 사본 23/23, 추론 전용 SHA-256 동봉본과 같음. 죽은 링크 10개, 내부 표기 3행(md) | 1,348초 + 1,046초 |
| Q6 | `judge06_Q6_tamper.py` | Q2 사본의 복사본: verify 변조 9종 + 검출 단위 탐침 15종(V7), 계약 4패키지 × 7~8종 + 그림·`--rerun`, 보완 verify 8종, v1 비교표 허용오차 3종 | 54개 중 53개가 설계대로. 예외 V6b(동결 요약 `alarm_rows`+1 통과, R3-02). V7 사건·문자 열 6종 미검출(R3-02) | 220초 |
| Q6d | `judge06_Q6d_digest_probes.py` | Q6 작업 사본에서 동결 요약 필드 손상(V6c~V6e), 결과 CSV·행 단위 예측 3중 위조(V8a·V8b: 결과 + 실행 기록 해시 + 동결값) | V6c(`sha256`만 0)·V6d(`exact_sha256`만 0) 통과, V6e(둘 다 0) 검출. V8a는 동결 CSV 무결성과 audit 연결이, V8b는 analysis·audit 연결이 잡음 | 약 30초 |
| Q6b | `judge06_Q6b_prereq.sh` | 학습 전 새 클론에서 계약·보완 verify 단독 호출 12가지, 팀 시험 5개 | 12가지 모두 종료 코드 2·한 줄·추적 0. 팀 시험은 원본만 있으면 4개 실패(R3-04) | 약 80초 |
| Q6c | `judge06_Q6c_manifest_tool.sh` | 목록 도구 민감도: 의존 묶음 삭제, 동결 요약 제외, JSON·CSV 절대 경로, 비어 있지 않은 폴더 | M1~M3 검출, M4는 설계 범위 밖(CSV는 검사 안 함), M5 거부. 되돌림 확인 | 30초 |
| Q7 | `judge06_Q7_abs_paths.py` | 커밋 상태 새 클론, Q1·Q2 실행 뒤, 목록 사본 실행 전후 | 목록 경로의 실행 기록에 절대 경로 0개. 목록 밖(press_early·press_improvement manifest, HISTORY.md 등)에만 남음 | 수 초 |
| Q8 | `judge06_Q8_full.sh` | 새 클론 + `--full`(v1 1~5단계 LSTM 캐시 없이 처음부터, 후보 비교, E1~E3 재실행, UCI ZIP, 새 TMPDIR), anaconda 3.12.2(torch 2.5.1) | 16/16. v1 1~5단계 4,466초(LSTM 3종 처음부터, 에폭 749·197·101로 커밋 기록과 같음), v1 39/39, 후보 비교 14.7초, E1~E3 재실행 622.9초(E2 포함). 모델·예측 비트 동일. v2 결과 43개·분석 패키지 결과 64개 바이트 동일. v1 결과 29/30 바이트 동일(나머지 `lstm_common_meta.csv`는 `cached`·`train_seconds` 실행 메타 열만 다름) | 5,780.5초 |
| Q9 | `judge06_Q9_python_versions.sh`, `judge06_Q9_python_versions_b310.log` | 3.10.20·3.13.13·3.14.6 게이트, 3.10 venv에 uv 해석(`--dry-run`), 3.11.15 venv + lock `--no-deps` + git 없는 사본 + `--tests` | 게이트 3종 종료 코드 1·한 줄·추적 0. 3.10 설치 불가(scikit-learn 1.8.0·contourpy 1.3.3). 3.11은 23/23, 비트 동일 | 1,885.0초 |
| Q10 | `judge06_Q10_crlf.sh` | `core.autocrlf=true` 클론: 줄바꿈, 커밋 상태 계약·보완 verify·기대값 무결성, 한 명령 재현 | CRLF 0/1,182. 커밋 상태 검사 모두 통과. 15/15, 비트 동일. 재현 뒤 바뀐 추적 파일은 실행 기록 9개뿐 | 1,972.1초 |
| Q11 | `judge06_Q11_clean_repro.sh` | README:195의 `bash yejun/press_guard/tools/clean_repro.sh`를 git 없는 사본(원본 CSV만)에서 그대로 | 15/15, 비트 동일. 스크립트의 `mktemp -d`는 TMPDIR 대신 사용자 임시 폴더(/var/folders)를 썼고, 확인 뒤 지웠다 | 1,247.4초 |
| Q12 | `judge06_Q12_space_path_tz.sh` | 목록 사본을 `평가 위원 폴더/제출 사본 (압축 해제)`에 두고 `TZ=America/Los_Angeles` | 15/15, 비트 동일 | 1,331.1초 |
| Q13 | `judge06_Q13_timing.sh` | 부하가 내려간 뒤 git 없는 사본 + ZIP + README 16행(anaconda 3.12.2) | 15/15, 비트 동일. 부하 평균 5.0(최대 7.3). 단계: 분석 230.5초, audit 244.0초, 지도학습 154.6초 | 856.8초 |
| Q14 | `judge06_Q14_nodata.sh` | git 없는 사본에서 원본 없이 README 한 명령, 없는 `--data` 경로 | 둘 다 종료 코드 1, 안내 한 줄, 추적 출력 0, 단계 실행 0 | 수 초 |
| 정적 | `judge06_static.py` | 기준 커밋 파이썬 78개(팀 시험 범위 74개) AST 검사, 문서 코드 블록의 POSIX 문법·절대 경로·내부 표기 | 팀 범위: git 호출 `text=True` 2건(ASCII 출력), 조건부 `resource` 1건. 범위 밖: `press_early/run_experiment.py:65` `read_text()` 인코딩 없음(목록에 들지만 실행 경로 밖), vendor CLI `:187`. 문서: 분석 README 4곳의 `export`는 PowerShell 대안을 병기했다 | 수 초 |
| 대조 | `judge06_check.py` | Q1~Q13 사본의 모델·예측 SHA-256, 결과 표, 분석 패키지 결과, v1 결과를 커밋본과 대조, 파일만으로 F1 | `judge06_results.json` | 수 초 |

- 결과 파일: `judge06_Q*.log`, `judge06_Q6_tamper.json`, `judge06_Q6d_digest_probes.log`, `judge06_Q5_docs.json`, `judge06_Q5_list_compare.log`, `judge06_Q5_internal_markers.log`, `judge06_Q5_blind_identity.log`, `judge06_Q7_abs_paths_*.json`, `judge06_static.json`, `judge06_results.json`, `judge06_check.log`.
- 정리: conda 환경·가상환경·내려받기 캐시는 확인 뒤 지웠다. 설치 목록은 Q1·Q2·Q9 로그에 있다. clean_repro.sh가 /var/folders에 만든 사본도 지웠다.
