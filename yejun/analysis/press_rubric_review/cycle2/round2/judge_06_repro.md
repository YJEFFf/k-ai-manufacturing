# 평가관 06 — 코드 및 재현성(10점) 검수 · cycle2 round2

2026-09-27~28. **기준 커밋 `f5679ca`**(`f5679ca5cf03426555edfad7ec7417f45d216f9a`). 검수 내내 HEAD는 바뀌지 않았다. 검수 중 작업 트리에 미커밋 변경(press_evidence·press_guard 등 71개 파일)이 생겼지만 채점하지 않았다. 모든 실행은 기준 커밋의 새 클론이나 `git archive` 사본에서 했다. 행 번호도 기준 커밋(`git show f5679ca:…`) 기준이다.

- **중단과 재실행.** 2026-09-28 14:10쯤 기기가 재부팅됐다. 임시 폴더와 진행 중이던 실행이 모두 사라졌다. 저장소 안의 이 폴더 기록만 남았다. 그래서 모든 실행을 같은 커밋에서 처음부터 다시 했다. 아래 수치는 모두 재실행 값이다.
- **기준.** 공식 기준은 `official_task_extract.txt:88-89`의 「동일 환경에서 데이터 전처리부터 학습·추론·결과생성까지 자동 실행」(10점)이다. 제출물 요건(`:53-57`)도 재현성 관점에서 봤다. 요건은 소스코드와 requirements.txt 또는 environment.yml, 학습용 데이터, README, 테스트데이터 예측결과 파일이다.
- **범위.** 보고서가 없는 것은 감점하지 않았다. 제출 ZIP도 만들지 않았다. 묶음 목록 도구(`package_manifest.py`)의 목록만 계산해 그 목록대로 복사한 사본을 시험했다.
- **기록.** 이 문서는 검수 기록이며 대회 보고서가 아니다. 이 폴더의 `judge06_*`와 이 문서 말고는 아무것도 쓰지 않았다.

## 점수: 9.0/10 (범위 8.0~9.5)

- **1회차 P0·P1(R1~R4)의 핵심은 풀렸다(R1·R2 충족, R3·R4 부분).**
  - 이제 한 명령(`reproduce.py`)이 원본 ZIP 하나로 전처리·학습·추론·테스트 예측·분석·동결값 비교까지 돈다. 다음 조건에서 모두 통과했다.
    - git 없는 사본 + environment.yml로 만든 빈 conda 환경: 15/15
    - 새 클론 + torch 없는 새 가상환경 + `--tests`: 23/23
    - 파이썬 3.11 새 환경: 15/15
    - 새 클론 `--full`(LSTM 캐시 없이 처음부터, E1~E3 재실행): 16/16, v1 39/39
    - 한국어 Windows 조건 모의(CP949 + `resource` 차단): 본 경로 15/15(`--tests`는 R2-02)
  - 저장 모델 4개와 행 단위 예측 6개 파일은 모든 실행에서 커밋된 동결 해시와 **비트 단위로 같았다**. 파이썬 빌드 4종(3.11.15, 3.12.2, 3.12.8, 3.12.14)과 스레드 1·8개에서 같다.
- **감점(−1.0).**
  1. **묶음 목록대로 만든 사본에서 한 명령이 8/15에서 멈춘다(R2-01, −0.5).** 커밋된 의존 파일 17개가 목록에 없다. 행 단위 예측 동결 요약(`expected/predictions_digest.json`)은 제외 정규식에 걸려 빠진다. README 명령은 `yejun/` 접두인데 목록은 yejun 기준 경로다. 1회차 R3의 완료 기준(목록 사본에서 한 명령 통과)을 못 채웠다.
  2. **CP949 조건에서 `--tests`가 17단계 v1 시험 2개에서 멈춘다(R2-02, −0.2).** 본 경로는 통과하지만 README가 권하는 `--tests`는 종료 코드 1이다.
  3. **파이썬 3.10 지원 주장이 틀렸다(R2-03, −0.2).** 3.10에서는 requirements.txt와 lock이 모두 설치되지 않는다. 그런데 판 확인은 3.10을 통과시킨다.
  4. **문서 잔여(R2-04~R2-08, −0.1).** 단계 로그 한글 깨짐, verify 요약 설명 불일치, 갓 받은 사본의 단독 검사 안내 부족, Windows Git 줄바꿈, PowerShell 5.1의 `&&` 등이다.
- **범위.**
  - 하한 8.0: R2-01을 고치지 않은 목록으로 ZIP을 만들고, 평가위원이 그 ZIP에서 한 명령을 돌리는 경우다. 학습·테스트 예측(1~3단계)은 되지만 분석·검증 7단계가 실패로 찍힌다.
  - 상한 9.5: 목록을 고친 뒤 평가위원이 README대로 돌리는 경우다.
- **1회차 7.5 대비 +1.5.**
  - 1회차 감점 R1(−1.0)·R2(−0.5)는 풀렸다. R4(−0.5)도 3.10 문구만 남기고 풀렸다.
  - R3(−0.5)은 추론 전용·테스트 예측 파일은 풀렸고, 묶음 목록이 새 결함으로 남았다.
  - '다른 OS 실측 없음'은 1회차에서 한 번 반영했으므로 다시 감점하지 않았다.

## 상위 8팀 대비 위치

**이 항목에서 상위 8팀 중 1위다.**

- **앞선 점.** 이 과제의 흔한 상위권 제출물은 가이드북 LSTM-AE, 라벨 지도학습(SMOTE·앙상블·SHAP) 노트북과 requirements.txt다. 이런 제출물은 셀을 순서대로 눌러야 하고, 난수·GPU 때문에 같은 숫자가 다시 나오는지 보장하지 않는다. 이 팀은 다음을 직접 증명한다.
  - 원본 ZIP 한 개로 한 명령 재현
  - 빌드가 다른 파이썬 4종에서 모델·예측 파일 비트 동일
  - 동결 기대값과 변조 검출(평가관이 따로 만든 58개 시나리오가 모두 설계대로 판정)
  - torch 없는 경로, CP949·`resource` 없는 환경
  - 파일만으로 F1 재계산이 되는 테스트 예측 파일
- **남은 위험.** R2-01을 고치지 않은 목록으로 ZIP을 만들면 평가위원 화면에 "8/15 단계 통과"가 찍힌다. 그때는 environment.yml과 `python main.py` 하나로 끝나는 팀보다 불리해져 4~5위권으로 내려간다. 고치는 데 드는 일은 목록 보완과 사본 시험 한 번이다.

## 1. 1회차 항목 충족표

행 번호는 기준 커밋 기준이다. 실행 기록은 이 폴더의 `judge06_P*.log`에 있다.

| ID | 판정 | 근거 |
|---|---|---|
| R1 Windows(`resource`·인코딩) | **충족** | 1회차 완료 기준을 CP949 + `resource` 차단 새 클론에서 모두 통과했다: v1 2단계, train, analyze, audit 16/16, verify 48/48(1회차 20항목에서 늘어남), 보완 verify, press_supervised(P3). 이어서 다음도 통과했다: 웹 콘솔 HTTP(`/api/overview` audit 16/16, `/api/analyze` 혼합·업로드), predict·simulate·recalibrate·package_manifest, v1 1~5단계 39/39(LSTM 캐시), E1~E3 재실행. `runtime.py:45-52`가 `resource`를 선택으로 쓴다. 팀 정적 시험(`test_portability.py:44-60`)은 범위 안 0건이다. 새 결함: `--tests` 17단계 실패는 R2-02, 로그 한글 깨짐은 R2-04 |
| R2 한 명령 진입점 | **충족** | git 없는 사본 + README 빠른 시작 두 줄: 15/15, 867.8초(P1). 새 클론 `--tests`: 23/23, 968.7초(P2). 둘 다 v1 16/16, v2 48/48, 계약 4개, E1·E3 비교를 통과했다(E2는 UCI ZIP이 없어 이유를 적고 건너뜀). `--full`도 새 클론에서 16/16이다(P4, 3,798.7초). LSTM을 캐시 없이 처음부터 학습해 v1 39/39, E1~E3 재실행까지 통과했다. analyze 오류 메시지의 해결 명령(`analyze.py:90`)을 그대로 따르면 풀린다(P6 A3~A5). 시간: 부하 평균 6~11에서는 팀 실측(572초)의 1.4~1.6배였다. 부하가 2.6~6으로 낮을 때 다시 잰 P11은 646초였다. 단계별로 train 25.2초·analyze 101.1초·audit 186.1초로 팀 기록(25.1·99.8·180.4초)과 거의 같다. 차이는 부하가 다시 오른 뒤의 지도학습 단계(201.6초 대 148.9초)에서 났다 |
| R3 제출 묶음·테스트 예측 | **부분** | 됨: 테스트 예측 파일 정의와 열 사전(README:59-72), 파일만으로 F1 재계산(A 0.961938 = TP 556·FP 0·FN 44, B 0.970990 = 569·3·31), 두 파일의 이상 600행 식별자 같음, `predict.py --split`이 학습 없이 같은 SHA-256을 만듦(클론·목록 사본 모두, P5). 안 됨: 목록 사본에서 한 명령이 8/15(R2-01) |
| R4 의존성 명세 | **부분** | 됨: `environment.yml`로 만든 빈 conda 환경(90초)에서 한 명령 통과(P1). torch 없는 환경에서 전체 통과(P2). v1 `run_all.py`의 torch 지연 import. 3.13·3.14는 안내를 내고 종료 코드 1로 멈춤(P7a). 안 됨: 3.10 주장(R2-03). lock에 cloudpickle(joblib 의존)·Windows colorama가 빠짐(R2-08) |
| R5 verify 행 단위 | **충족** | 예측 파일 한 행 경보 0→1 변경과 파일 삭제를 CLI verify가 잡는다(P6 V1·V2). 저장 모델 계수 +1e-12도 잡는다(V6). 시험은 `test_analyze.py:93-116`에 있다. 다른 기기용 요약 경로의 설명 불일치는 R2-05 |
| R6 외부 자료 없는 환경 | **충족** | UCI ZIP이 없으면 보완 시험 10 통과·3 건너뜀, 넣으면 13 통과(P6 S0a·S0b). verify는 E2를 이유·획득 명령과 함께 건너뛴다(`press_supplement/verify.py:34-36·131-132`) |
| R7 보완 verify 거짓 실패 | **충족** | 실제 E2 `--no-cache` 실행 결과가 verify(E2)를 통과했다(126초, P6 S6). `cache_used` 반전은 참고로만 표시하고 `cache_version` 변경은 실패한다(S4·S5) |
| R8 분석 패키지 계약 | **충족** | 공용 계약 `analysis/package_contract.py`를 4개 패키지에 적용했다. 평가관이 따로 만든 변조를 모두 잡았다: 결과 한 칸 +1e-6, 결과와 실행 기록을 함께 위조, 삭제, 코드 한 줄, 동결값 +1e-3, 의존 파일 한 줄(P6 C1~C7, 의존 파일은 의존 묶음이 있는 3개 패키지). 1e-12 변경은 설계대로 통과했다(C3). `--rerun`도 통과했다(C10). 기대와 다른 1건(press_evidence C3)은 평가관 위조가 `cited` 묶음을 빠뜨린 탓이다. 검출이 더 엄격했다는 뜻이다 |
| R9 v1 비교표 허용오차 | **충족** | LSTM F1 +1e-6이면 analyze 원본 검사를 통과하고, +1e-2이면 실패한다(P6 A1·A2, `analyze.py:73-83`) |
| R10 문서 정정 | **부분** | 됨: press_guard README는 `python …`만 쓰고 PowerShell을 안내한다. 결과 CSV 37개와 단계 수 15·23이 실제와 같다. 절대 경로는 제출 목록 문서에 없다(블라인드 검사 통과). 안 됨: README:14의 `&&`(PowerShell 5.1), README:9의 HISTORY 링크(목록 제외), 제출 문서의 내부 검수 표기, v1·선정 README의 POSIX 전용 문법(R2-08). README:159 설명 불일치(R2-05) |
| R11 실행 환경 처리 | **충족** | 스레드 변수 없이 train 23초(부하 7~8)였고, manifest에 BLAS 3종이 스레드 1로 남았다(P10). `PRESS_THREADS=8`에서도 비트 동일했다. 그림 글꼴 목록에 Malgun Gothic·NanumGothic이 있다(`runtime.py:68-73`). 주최 측 ZIP을 `--data`로 바로 받는다(P1~P3, `runtime.py:76-103`) |

## 2. 강점 — 직접 확인

| 강점 | 파일:행 | 직접 확인 |
|---|---|---|
| 한 명령 재현 | `press_guard/reproduce.py:30-61`(단계), `:71-80`(판·입력 확인, ZIP 배치), `:95-110`(단계 로그·요약·종료 코드) | 원본 ZIP만 준 사본에서 15/15·23/23·16/16(`--full`). 실패하면 그 단계에서 멈추고 종료 코드 1이다(P3). `--keep-going`이면 끝까지 돌고 실패 단계를 요약한다(P5) |
| 환경 간 비트 동일 | `runtime.py:21-35`(스레드 고정), `:55-65`(BLAS 기록) | 모델 4개와 예측 6개가 모든 실행(P1~P4·P7·P10·P11)에서 동결 해시와 같다. 조건은 conda-forge 3.12.14, python.org 3.12.8, anaconda 3.12.2(CP949·`--full`), uv 3.11.15, 8스레드다. press_guard 결과 38개도 모두 바이트가 같다. press_evidence 표 4개만 1e-16~7e-15 차이였고 계약 허용오차(1e-9)가 흡수했다(P1·P2) |
| 테스트 예측 파일 | README:59-79, `train.py`의 `test_prediction_file`, `predict.py:26-35·55-64` | 파일만으로 F1 재계산, 학습 없이 같은 SHA-256 재생성(클론·목록 사본) |
| 한국어 Windows 조건 | `runtime.py:21-28·45-52`, `test_portability.py:44-96` | CP949 + `resource` 차단에서 본 경로 전체, v1 1~5단계 39/39, E1~E3 재실행, 웹 콘솔 HTTP, 운영 도구가 통과했다(P3·P3c) |
| 변조 검출 | `verify.py:37-73·99-117`, `analysis/package_contract.py:102-149·178-240`, `press_supplement/verify.py:31-45` | 58개 시나리오가 전부 설계대로 판정됐다(P6) |
| 의존성 | `environment.yml`, `requirements.txt`(torch 없음), `requirements-lstm.txt`, `runtime.py:38-42` | 빈 conda 환경 90초, pip 설치 13초, 3.13·3.14 안내 후 정지 |
| 전체 모드 | `reproduce.py:35-38·52-53` | 새 클론 `--full` 16/16(P4). LSTM 3종을 처음부터 학습했다(2,461초, 에폭 749·197·101로 커밋 기록과 같음). v1 결과 30개 중 29개가 바이트까지 같았다. 나머지 `lstm_common_meta.csv`는 `cached`·`train_seconds` 실행 메타 열만 달랐다. E2는 새 TMPDIR에서 UCI 10 Hz 변환부터 다시 해 통과했다 |

## 3. 수정·보완 목록

경로는 `yejun/` 기준이다. 모델·문턱·분할·동결 수치를 바꾸는 일은 완료 기준이 아니다. ZIP 생성과 보고서 작성도 완료 기준이 아니다.

| ID | 우선 | 분류 | 위치(파일:행) | 해야 할 일 | 완료 기준 |
|---|---|---|---|---|---|
| **R2-01** | **P0** | 제출 묶음 목록 | `press_guard/tools/package_manifest.py:22-36`(GROUPS), `:37`(EXCLUDE의 `/predictions_`), `:38-41`(REQUIRED 11개뿐), `:55`(yejun 기준 경로); `press_guard/README.md:14-15·24`(`yejun/` 접두 명령) | **확인한 증상.** 목록 379개(12.8 MB)만 새 폴더에 복사해 한 명령을 돌리면 8/15다(P5). 실패한 단계는 다음과 같다: analyze(`press_submission/outputs/model_comparison_all.csv` 없음), audit 15/16, verify 40/43(`expected/predictions_digest.json` 없음), 진단 보강(`load_normalization_meta.csv` 없음), press_selection(`load_normalization.csv` 없음), 계약 2개. 실행 기록이 적은 커밋된 의존 파일 17개가 목록에 없다(`judge06_P5b_missing.json`): `press_submission/outputs`의 3~5단계 결과 10개(model_comparison_all·sensitivity·ablation·persistence·load_normalization·load_normalization_meta·lstm_guidebook_reproduction·diagnosis.md·label_bypass·splits), `analysis/press_dayshift/v2_current_scale.csv`(analyze.py:27), `press_improvement` 2개, `press_early` 2개, `press_external` 2개(E2용). README 명령을 문자 그대로 치면 파일이 없다고 나온다. 블라인드 검사는 필수 파일 11개만 봐서 "통과"라고 한다. 절대 경로 검사도 JSON을 보지 않아, 목록에 든 실행 기록 3개(`analysis/press_advance/manifest.json`·`expected/manifest.json`, `press_submission/outputs/expected/manifest.json`)에 개발 기기 경로(`/Volumes/…`)가 남는다. **할 일.** ① 목록을 실행 기록(manifest의 sources·cited·dependencies·external_inputs)에서 모으거나 누락분을 넣는다. ② 제외 규칙을 `outputs/predictions_`로 좁힌다. ③ 묶음 최상위를 `yejun/`으로 두거나 README 명령을 묶음 구조에 맞춘다. ④ 블라인드 검사에 "목록 사본에서 한 명령 실행"이나 의존 파일 존재 검사를 넣는다 | 목록만 복사한 새 폴더에서 README 빠른 시작 명령을 문자 그대로 실행해 15/15(`--tests` 23/23)가 나온다. verify의 행 단위 예측 요약이 통과한다. `predict.py --split` SHA-256이 동봉본과 같다 |
| **R2-02** | **P1** | 한국어 Windows 시험 | `press_submission/tests/test_review_regressions.py:223`(`subprocess.run(…, text=True)` 인코딩 없음); `press_guard/test_portability.py:15-20`(정적 검사 범위에 press_submission 없음) | **확인한 증상.** CP949 + `resource` 차단 새 클론에서 `reproduce.py --tests`가 17단계(v1 시험)에서 2개 실패하고 16/23으로 멈춘다(P3). 원인은 `UnicodeDecodeError`다: `clean_repro.sh` 출력의 `→`와 한글을 cp949로 읽었다. 1~16단계는 통과했고, 따로 돌린 18~23단계 시험과 나머지 v1 시험 47개도 통과했다(P3c). **할 일.** `encoding="utf-8"`을 지정한다. bash가 없는 Windows에서는 건너뛴다. 정적 검사 범위에 `press_submission`(시험 포함)을 넣는다 | 같은 조건의 새 클론에서 `reproduce.py --tests`가 23/23이다. 정적 검사가 press_submission까지 0건이다 |
| **R2-03** | **P1** | 파이썬 판 주장 | `press_guard/runtime.py:6·17·41`, `requirements.txt:1`, `README.md:14`, `test_portability.py:77` | **확인한 증상.** 3.10 새 환경에서 requirements.txt와 lock이 모두 설치되지 않는다. scikit-learn 1.8.0과 contourpy 1.3.3이 3.11 이상을 요구한다(P7b). 그런데 판 확인은 3.10을 통과시키고, 문구는 "3.10~3.12에서 실행·검증했다"이다. Ubuntu 22.04 기본 파이썬이 3.10이다. 3.11.15는 lock 설치, 15/15, 비트 동일을 확인했다(P7c). **할 일.** 지원 범위를 3.11~3.12로 고치고 판 확인·문구·시험을 맞춘다 | 3.10에서 `reproduce.py`가 설치 안내를 내고 멈춘다. 문서의 판 범위가 실제 실행 기록과 같다 |
| R2-04 | P2 | 로그 인코딩 | `press_guard/reproduce.py:86-87`(자식 환경에 `PYTHONIOENCODING` 없음), `:95` | CP949 조건에서 단계 로그(`outputs/reproduce_logs/*.log`)와 요약 `last_line`의 한글이 U+FFFD로 깨진다. 실행은 통과한다. `package_contract.py:283`과 `press_supplement/verify.py:100`은 이미 `PYTHONIOENCODING=utf-8`을 준다. 자식 환경에 같은 값을 준다 | CP949 조건 실행의 단계 로그에 한글이 그대로 남는다 |
| R2-05 | P2 | verify 설명·검출 단위 | `press_guard/README.md:159`("실수 열이 소수 6자리까지"), `verify.py:8-9·37-73` | 구현은 열 합·제곱합·최솟값·최댓값을 상대 1e-7로 비교한다. 실행 기록을 함께 다시 만든 경로(다른 기기)에서는 다음 변경이 통과한다: 점수 한 행 +1e-4, 우도비 한 행 ×1.001, 두 행 점수 맞바꿈(P6 V7). 경보·알림·단계 열은 정확 비교라 판정 결과에는 영향이 없다. 같은 기기에서는 manifest 해시가 잡는다. README 문구를 구현에 맞추거나 열별 반올림 해시를 추가한다 | 문서 설명과 동작이 같다. 설명한 단위의 변경이 설명대로 판정된다 |
| R2-06 | P2 | 갓 받은 사본의 단독 검사 | `analysis/package_contract.py:123-124`, `analysis/press_supplement/contract.py:61-64` | 학습 전 새 클론에서 `package_contract.py`를 단독으로 부르면 4개 패키지가 모두 "파일 없음"으로 실패한다. Git 제외 원본 CSV와 `press_guard/artifacts`가 없어서다. 보완 verify는 추적 출력을 내며 죽는다(P9). **P8의 press_selection 실패 원인이 이것이다.** 줄바꿈 변환 없는 클론에서도 커밋 결과가 아니라 실행 전 의존 파일 부재로 실패했다. 한 명령 재현 뒤에는 4개 모두 통과한다. 없을 때 "먼저 `python press_guard/reproduce.py`" 안내로 멈추게 한다 | 새 클론에서 단독 실행하면 안내 한 줄과 종료 코드 2가 나오고 추적 출력이 없다 |
| R2-07 | P2 | Windows Git 줄바꿈 | 저장소에 `.gitattributes` 없음; `analysis/package_contract.py:55-60`, `press_guard/verify.py:107-117`(바이트 해시) | `core.autocrlf=true` 클론(Git for Windows 기본값)에서 커밋된 동결값 해시가 모두 어긋난다. 4개 패키지 lock이 불일치하고 v2 기대값 39건이 "실행 후 변경"으로 나온다(P8). ZIP 배포에는 해당하지 않는다. `yejun/.gitattributes`로 변환을 끄거나 해시 전에 CRLF를 정규화한다(v1 `code_sha256`처럼) | autocrlf=true 클론에서 커밋 상태 계약 검사와 한 명령 재현이 통과한다 |
| R2-08 | P2 | 제출 문서 잔여(R10) | `press_guard/README.md:14`(`&&`), `:9`(HISTORY 링크), `OPERATIONS.md:37`·분석 README의 "평가관 04·06 R8" 표기, `press_submission/README.md:18`·`analysis/press_selection/README.md:163-164`(POSIX 환경변수 접두), `requirements-lock.txt`(cloudpickle·colorama 누락), `reproduce.py:4`(--full 시간) | `&&`는 Windows PowerShell 5.1에서 구문 오류다(이 기기에 PowerShell이 없어 정적 확인). HISTORY.md는 목록에서 빠져 링크가 죽는다. 내부 검수 표기는 평가위원이 읽을 문서에 남아 있다. lock은 "전이 의존성 고정"이라 적었지만 joblib이 쓰는 cloudpickle이 없다. `reproduce.py:4`의 "--full 약 25분"은 LSTM 캐시가 있을 때 값이다. 새 사본에서는 63분이 걸렸다(P4, LSTM만 41분). 두 줄로 나누고, 링크와 표기를 정리하고, PowerShell을 병기하고, lock을 보완한다 | 목록 사본의 문서 명령이 PowerShell 5.1과 zsh에 그대로 붙어 실행된다. 죽은 링크·내부 표기가 없다. `pip install --no-deps -r requirements-lock.txt` 환경에서 시험이 통과한다 |

## 4. 수정 불가 한계

1회차 한계는 그대로다. 감점을 다시 하지 않았다.

| 한계 | 내용 |
|---|---|
| 다른 OS·CPU 실측 | 이 기기는 macOS arm64 한 대다. Windows 조건(CP949·`resource` 부재·스레드 수·휠 해석)은 모의만 했다. 비트 동일은 이 기기의 파이썬 빌드 4종에서 확인했다. 다른 CPU·BLAS에서는 부동소수 차이가 순위 p값을 바꿀 수 있다. 그래서 허용오차와 경보 정확 비교로만 보장한다 |
| LSTM 재학습 | PyTorch 결과는 기기·빌드마다 다를 수 있다. 비교용 기준모델이라 최종 모델 수치에는 영향이 없다 |
| 외부 자료 | UCI 유압 자료(73 MB)는 제3자 배포물이라 획득 스크립트와 해시로 대신한다. 없으면 E2를 건너뛴다 |
| 테스트셋 정의 | 공식 별도 테스트셋이 없다. 테스트 예측 파일은 팀이 정한 분할 A/B의 평가 구간이고, 이상 600행은 두 파일에 같다. README:61이 이를 적었다 |
| 부하 없는 시간 | 다른 평가관 실행이 겹쳐 부하 없는 조건을 만들 수 없었다. 가장 낮은 부하(2.6~6)에서 646초(README 572초의 1.13배)였다 |

## 5. 직접 수행한 검증

스크립트와 로그는 모두 이 폴더에 있다. 임시 폴더는 `J06_BASE`(기본: 이 세션의 scratchpad/judge06r2)다. 파이썬은 `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python`을 기본으로 썼다. P1·P2·P7은 새 환경의 파이썬을 썼고, P10은 스레드 변수를 일부러 뺐다. 새 사본 실행(P1~P4·P7·P11)은 원본을 주최 측 ZIP(`--data`) 하나로만 줬다. P5 목록 사본은 목록에 든 학습용 CSV를 썼다.

| 단계 | 스크립트 | 조건 | 결과 | 시간(부하) |
|---|---|---|---|---|
| P1 | `judge06_P1_archive_conda.sh` | git archive 사본(.git 없음), `conda env create -f environment.yml`(conda-forge 3.12.14, 캐시 새로), README 두 줄 | 환경 90초, 15/15, 비트 동일 | 867.8초(6~11) |
| P2 | `judge06_P2_venv_notorch.sh` | 새 클론, python.org 3.12.8 venv에 requirements.txt만(torch 없음), `--tests` | 23/23: v2 시험 77·1 건너뜀, v1 44·2 건너뜀, 분석 8·6·6·6·10(+3 건너뜀), 웹 9 | 968.7초(6~9) |
| P3 | `judge06_P3_cp949_nores.sh` | 새 클론, `LC_ALL=ko_KR.CP949`(PYTHONUTF8 없음) + `resource` 차단, `--tests`, 운영 도구, v1 1~5단계(LSTM 캐시), E1~E3 재실행(UCI ZIP) | 16/23(17단계 v1 시험 2개 실패, R2-02). 1~16단계 통과. 운영 도구·웹 콘솔 HTTP 통과. E1~E3 재실행 통과(949초) | 999.3초 |
| P3c | `judge06_P3c_cp949_rest.sh` | P3와 같은 조건: 18~23단계 시험, v1 나머지 시험, v1 전체 verify | 분석 시험 8·6·6·6·13, 웹 9, v1 47(2개 제외), v1 39/39 | 약 30초 |
| P4 | `judge06_P4_full.sh` | 새 클론, `--full`(v1 LSTM 캐시 없이 처음부터, 후보 비교, E1~E3 재실행, UCI ZIP, 새 TMPDIR) | 16/16: v1 1~5단계 2,461초, v1 39/39, 후보 비교 7.6초, E1~E3 재실행 695초. 모델·예측 비트 동일, v2 결과 38개·분석 패키지 결과 바이트 동일, v1 결과 29/30 바이트 동일(나머지 1개는 메타 열) | 3,798.7초(4~15) |
| P5 | `judge06_P5_predict_package.sh`, `judge06_P5b_missing.py` | P2 사본에서 `predict.py --split`, `package_manifest.py` 목록 → 목록만 복사한 사본에서 README 명령, 추론 전용, 한 명령(`--keep-going`) | 추론 전용 SHA-256 A `d01201af…`·B `e042763e…`가 학습 실행·커밋 요약·커밋 manifest와 같음. 목록 379개, 블라인드 검사 "통과". README 문자 그대로는 파일 없음. 한 명령 8/15. 누락 의존 17개와 제외된 동결 요약 1개 | 648.8초 |
| P6 | `judge06_P6_tamper.py` | P2 사본의 복사본: verify 변조 7종과 요약 검출 단위, 계약 4패키지 × 8종, 그림, `--rerun`, 보완 시험(ZIP 유무), 실행 옵션, E2 `--no-cache` 실제 실행, R9 허용오차, 해결 명령 | 58개 중 57개 기대대로. 나머지 1개는 평가관 위조 누락이라 검출이 더 엄격했다 | 333초 |
| P7 | `judge06_P7_python_versions.sh` | 3.13.13·3.14.6에서 한 명령, 3.10.20 설치, 3.11.15(lock) git 없는 사본 한 명령 | 3.13·3.14는 안내 후 종료 1. 3.10은 설치 불가. 3.11은 15/15, 비트 동일 | 889.3초 |
| P8 | `judge06_P8_crlf.sh` | `core.autocrlf=true` 클론과 변환 없는 클론의 커밋 상태 계약 검사 | CRLF: 4패키지 lock 불일치, v2 기대값 39건(R2-07). LF: press_selection "파일 없음". 원인은 학습 전이라 Git 제외 원본 CSV 2개와 `press_guard/artifacts/guard_A·B.json`이 없어서다(P9, R2-06). 커밋 결과의 결함이 아니다 | 20초 |
| P9 | `judge06_P9_fresh_contract.sh` | 학습 전 새 클론에서 계약 검사 단독 실행 | 4패키지 모두 Git 제외 원본·모델 "파일 없음", 보완 verify 추적 출력 | 5초 |
| P10 | `judge06_P10_threads.sh` | 스레드 변수 없이 train, `PRESS_THREADS=8` train | 23초·BLAS 스레드 1 기록·비트 동일. 8스레드는 182초(과다 구독)·비트 동일 | 205초 |
| P11 | `judge06_P11_timing.sh` | 부하가 낮아진 뒤 git 없는 사본 + anaconda 3.12.2로 README 시간 재측정 | 15/15, 비트 동일 | 646.3초(2.6~6) |
| 정적 | `judge06_static.py` | 기준 커밋 파이썬 79개 ast 검사(인코딩·Unix 전용·절대 경로·POSIX 문법) | 제출 목록의 실행 코드는 인코딩 누락 0건이다. 예외 셋: v1 시험(ASCII JSON이라 무해, `:223`만 R2-02), vendor CLI `:187`(파이프라인에서 실행 안 됨), git·chrome 호출의 `text=True`(ASCII 출력) | 수 초 |
| 대조 | `judge06_check.py` | P1~P4 사본의 모델·예측 SHA-256, 결과 표, 분석 패키지 결과, v1 결과를 커밋본과 대조 | `judge06_results.json` | 수 초 |

- 기기: Apple M2 8코어, macOS 26.3.1. 재부팅 뒤 다른 평가관 실행과 겹쳐 부하 평균이 4~28 사이였다. 각 단계의 부하는 로그의 `load_start/load_end`에 있다.
- 결과 파일: `judge06_P*.log`, `judge06_P6_tamper.json`, `judge06_P5b_missing.json`, `judge06_static.json`, `judge06_results.json`, `judge06_check.log`.
- 정리: 클론과 실행 결과는 세션 임시 폴더(`judge06r2/`)에 남겼다. conda 환경·가상환경·내려받기 캐시(약 2 GB)는 확인 뒤 지웠다. 설치 목록은 P1·P2·P7 로그에 있다. 재부팅으로 1차 실행분은 사라졌다.
