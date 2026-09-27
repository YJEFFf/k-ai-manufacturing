# 평가관 06 — 코드 및 재현성(10점) 검수 · cycle2 round1

2026-09-27. **기준 커밋 `dcd300a`**(`dcd300aa88288508d0794ce89a9aebcfd53bc3b4`). 검수를 시작할 때 HEAD는 `f6ec6b8`이었다. 첫 실행 직전에 `dcd300a`(`press_supervised` 추가)가 커밋되어 모든 클론·실행은 `dcd300a`에서 했다. 실행 도중 올라온 `3ad2452`는 `analysis/press_supervised/`만 바꿨다(press_guard·press_submission·보완·진단 코드는 `dcd300a`와 같다). 이 커밋은 재실행 결정성만 따로 확인했다(Phase H, 바이트 동일). Phase T·H·I의 클론은 `3ad2452`다. 작업 트리의 미커밋 변경(`press_guard/`에 `probability.py`·`monitor.py`·`simulate.py` 등 추가, `train.py`·`verify.py`·`analyze.py` 등 수정 진행 중)은 채점하지 않았다.

공식 기준은 `official_task_extract.txt:88-89`의 「동일 환경에서 데이터 전처리부터 학습·추론·결과생성까지 자동 실행」(10점)이다. 제출물 요건(`:53-57`: 소스코드와 requirements.txt 또는 environment.yml, 학습용 데이터, README, 테스트데이터 예측결과 파일)도 재현성 관점에서 함께 봤다. 제출 ZIP이 없는 것은 감점하지 않았다. 대신 최종 묶음을 한 번에 만들 준비가 됐는지를 채점했다. 이 문서는 검수 기록이며 대회 보고서가 아니다. 이 폴더의 `judge06_*`와 이 문서 말고는 아무 파일도 바꾸지 않았다. 클론·가상환경·실행 산출물은 시스템 임시 폴더에 두었다.

## 점수: 7.5/10 (범위 7.0~8.0)

- **강점.** 같은 환경에서는 공식 문구를 넘는 수준으로 충족한다.
  - 원본 CSV 2개만 남기고 커밋된 중간 산출물·LSTM 캐시·학습 상태를 지운 새 클론에서 전체를 다시 만들었다. v1 1~5단계, 후보 비교, v2 학습·분석·audit·verify, 진단 표, 보완 실험 E1~E3, 테스트 118개가 모두 통과했다.
  - 저장 모델과 테스트 예측 파일 4개가 동결 해시와 **비트 단위로 같았다**. 새 가상환경(다른 파이썬 빌드)과 8스레드 BLAS에서도 같았다.
- **감점 요인(−2.5).**
  1. **한국어 Windows에서 최종 모델 경로가 멈춘다(R1, −1.0).** Unix 전용 표준 모듈 `resource`와 인코딩을 지정하지 않은 JSON 읽기 때문이다.
  2. **최종 모델에 한 명령 진입점이 없다(R2, −0.5).** README대로 새 클론에서 실행하면 analyze에서 멈춘다.
  3. **제출 묶음 조립기가 v1만 담는다(R3, −0.5).** 테스트 예측 파일도 지정돼 있지 않다.
  4. **의존성 명세가 약하다(R4, −0.5).** 파이썬 버전을 고정하지 않았고 3.13 이상에서는 설치가 안 된다. 최종 모델은 쓰지 않는 torch가 선행 단계에서 필수다.
- **범위.** 하한 7.0은 평가위원이 한국어 Windows에서 실행해 R1을 만나는 경우다. 상한 8.0은 macOS·Linux에서 코드와 README만 읽는 경우다.
- **직전 8.5 대비 −1.0.** 후퇴가 아니다. 이번 과제가 요구한 '묶음 준비 상태'를 채점에 넣었다. 이전 평가관이 하지 않은 README 문자 그대로 실행, Windows 조건 모의, 다른 파이썬 버전 해석을 직접 해서 새 결함이 드러났다. 직전 R9·R23은 해결을 확인했다(보완 verify·재실행 통과, 캐시 키). R24는 보완 실험·진단 표 manifest에만 반영됐다.
- **전망.** R1~R4를 마치면 9.5 안팎이다. R5~R11까지 마치면 다른 OS 실측 한계만 남는다.

## 상위 8팀 대비 위치

**이 항목에서 상위 8팀 중 4위권이다.**

- **앞선 점.** 원본부터 전체를 다시 만들어 저장 모델·테스트 예측 파일까지 비트 단위로 같음을 보였다. 동결 기대값·해시 계약·변조 검출 테스트도 갖췄다. 이만큼 증명하는 팀은 8팀 중 없다.
- **뒤진 점.** 평가위원이 이 항목에서 실제로 하는 일은 "README대로 설치 → 한 명령 → 예측 파일 확인"이다. 여기서는 environment.yml과 `python main.py` 하나로 끝나는 팀보다 불리하다. 평가위원 PC가 한국어 Windows이면 최종 모델 학습 스크립트가 실행 기록을 쓰기 직전에 멈춘다.
- **1위 조건.** R1~R4를 고치면 이 항목 1위다. 같은 저장소의 ⑤ 전력 패키지(`power_submission/`)는 한 명령 `run_all.py`, `environment.yml`, `make_submission.py`, 추론 전용 단계를 이미 갖췄다. 프레스에도 같은 틀을 적용하면 된다.

## 1. 강점 — 직접 실행 결과

기기: Apple M2 8코어, macOS 26.3.1. 기본은 anaconda Python 3.12.2다. 여러 평가관 작업이 동시에 돌아 시간은 부하 상태 값이다. 부하가 적을 때 잰 값은 T행에 따로 적었다.

| 검증(조건) | 결과 | 기록 |
|---|---|---|
| **원본만으로 전체 재생성**(새 클론. 커밋 산출물·기대값·LSTM 캐시·학습 상태를 지우고 시작) | v1 `run_all.py` 1~5단계 1,957초. LSTM 3종을 처음부터 학습했다(749·197·101 에폭). v1 verify 39/39, LSTM 표를 포함해 최대 차이 0. 이어서 press_advance 7초, v2 train 22초, analyze 14초, audit 16/16, verify 20/20. 진단 표 17개를 만든 뒤 보완 verify가 통과했다(재학습 모델 해시가 E1~E3 manifest와 같음). E1·E2·E3는 새 임시 폴더에서 UCI 10 Hz 변환부터 재실행해 622초에 통과했다. 테스트는 pytest v2 54·v1 49·보완 11, JS 4로 모두 통과. 총 47분 | `judge06_phaseC_full_raw.log` |
| **비트 단위 재현**(README 경로·전체 재생성·새 venv·BLAS 8스레드, 4개 실행) | 네 실행 모두 `guard_A/B.json`과 테스트 예측 4개 파일의 SHA-256이 동결 manifest와 같다. 예측 파일은 정상 평가 4,090·6,097행, 이상 600·600행이다. v1 비교표 5개, press_advance `metrics/primary.csv`, 진단 표 17개, 지도학습 기준선 3표(`dcd300a`·`3ad2452` 두 판)도 커밋본과 바이트가 같다 | `judge06_results.json` |
| **새 가상환경**(다른 파이썬 빌드 python.org 3.12.8, `requirements.txt`만 설치) | 설치 26초(pip 캐시 사용). v1 2단계를 거쳐 v2 학습·분석·audit 16/16·verify 20/20. pytest v2 54·v1 49 통과 | `judge06_phaseD_venv.log`, `judge06_venv312_pip_freeze.txt` |
| 저장소의 새 클론 재현 스크립트 | v2 `clean_repro.sh`는 verify 20/20(239초). v1 `clean_repro.sh --with-lstm`은 39/39(56초) | `judge06_phaseA_clean_repro.log` |
| 추론 전용 | `predict.py`로 저장 모델만 써서 이상 CSV 600행을 128행 묶음으로 추론했다. 학습 실행의 예측과 26개 열이 모두 같고, 점검 대기는 21구간이다(B·C 두 클론) | `judge06_results.json`(`predict_cli_vs_train`) |
| 스레드 수 | `OMP_NUM_THREADS`를 빼고 OpenBLAS 8스레드로 돌려도 verify 20/20이고 예측 파일이 비트 단위로 같다 | `judge06_phaseE_portability.log`(Ec) |
| 검증기 정직성 | 선행 산출물이 없으면 audit 15/16, verify 18/20으로 실패를 보고한다. 통과로 속이지 않는다 | `judge06_phaseB_readme_path.log` |
| T. 부하가 적을 때 시간(부하 평균 약 4) | v1 2단계 8초, train 26초, analyze 17초, audit 172초, verify 1초. 합계 약 3.7분 | `judge06_phaseT_timing.log` |
| v1 인코딩 처리 | v1 `run_all.py`는 CP949 기본 인코딩 모의에서도 통과한다(`encoding="utf-8"` 지정). v2가 따라야 할 모범이다 | Phase E(Ea07) |

## 2. 수정·보완 목록

경로는 `yejun/` 기준이고 행 번호는 `dcd300a` 기준이다. 모델·문턱·분할·동결 수치를 바꾸는 일은 어느 항목의 완료 기준도 아니다. ZIP 생성 자체는 예준 지시 전까지 보류한다. 조립기는 목록 계산(`--dry-run`)까지만 만든다.

| ID | 우선 | 분류 | 위치 | 해야 할 일 | 완료 기준 |
|---|---|---|---|---|---|
| **R1** | **P0** | 이식성(Windows) | ① `press_guard/train.py:99-100`(`import resource`, Unix 전용) ② 인코딩을 지정하지 않은 텍스트 입출력 20곳: `press_guard/contracts.py:30`, `analyze.py:40-41·68-69·74·419`, `audit.py:32`, `model.py:223·227`, `serve.py:93·107`, `recalibrate.py:140`, `analysis/press_supplement/common.py:18`·`verify.py:50·66`·`contract.py:93`, `analysis/press_advance/run_experiment.py:48`, `analysis/press_supervised/run.py:27`(3ad2452에서는 `:28`), `press_submission/vendor/press_policy_audit.py:187` | **확인한 증상.** `resource` 차단 모의(Windows 조건)에서 `train.py`는 학습과 예측·모델 파일 저장까지 마친 뒤 99행에서 죽는다. manifest를 쓰지 못해 뒤 단계가 모두 막힌다. CP949 기본 인코딩 모의(한국어 Windows 조건)에서는 v2 verify가 18/20으로 실패한다. analyze, 보완 verify, 웹 콘솔 `/api/overview`(`Console().overview()`)는 `UnicodeDecodeError`로 죽는다. `PYTHONUTF8=1`을 주면 verify 20/20이고 콘솔도 뜬다. Linux(KAMP-NOTE 포함)는 `resource`가 있고 기본 인코딩이 UTF-8이라 해당하지 않는다. **할 일.** ① `resource`를 `try/except ImportError`로 감싼다(Windows에서는 None을 기록하거나 psutil 사용). ② 모든 텍스트 입출력에 `encoding="utf-8"`을 넣는다. ③ 한글 표준출력은 `sys.stdout.reconfigure(encoding="utf-8")`로 처리하거나 README에 안내한다. ④ 인코딩 없는 `read_text/write_text/open`과 `import resource` 직접 사용을 막는 정적 검사 테스트를 추가한다 | `LC_ALL=ko_KR.CP949`(PYTHONUTF8 없이)와 `resource` 차단을 함께 건 새 클론에서 다음이 모두 통과한다: v1 2단계, train, analyze, audit 16/16, verify 20/20, 보완 verify, press_supervised. 정적 검사 0건. 가능하면 실제 Windows나 KAMP-NOTE에서 한 번 실행한 기록을 남긴다 |
| **R2** | P1 | 실행 진입점·README 순서 | `press_guard/README.md:46-52`; `press_guard/analyze.py:66-77`(오류 메시지); `press_guard/tools/clean_repro.sh:10·20` | **확인한 증상.** README 블록 그대로 새 클론에서 실행하면 analyze가 `분석 원본 무결성 오류: predictions_A.csv: 없음`으로 멈춘다. audit는 15/16, verify는 18/20이다. 선행 단계(v1 `run_all.py --steps 2`)는 `clean_repro.sh:20`에만 있다. `clean_repro.sh`는 git 클론을 전제로 해, git이 없는 사본(ZIP을 푼 상태)에서는 종료 코드 128로 즉시 실패한다. 전체 결과를 다시 만들려면 7개 폴더의 명령 10여 개를 암묵적 순서로 돌려야 한다: v1, press_advance, v2 4단계, 진단 표, 외부 자료, E1~E3, 그림, 지도학습 비교. **할 일.** ① 최종 패키지 루트에 파이썬 진입점 하나(예: `reproduce.py`)를 둔다. 순서는 입력 확인 → v1 선행 → (선택) 후보 비교 → v2 학습·분석·audit → (선택) 진단 표·보완 실험·지도학습 비교 → 모든 verify 요약이다. ② `--quick`(LSTM 캐시 사용, E1 생략)과 `--full` 두 모드를 둔다. ③ analyze 오류 메시지에 해결 명령을 적는다. ④ README 첫 화면에 설치 → 한 명령 → 결과 위치 → 검증을 4줄로 쓴다 | `git archive`로 만든 git 없는 사본에서 README의 한 명령만으로 다음이 모두 통과한다: v1 39/39, v2 20/20, 보완 E1~E3, 진단 표, 지도학습 기준선. 단계별 시간이 README 표기와 맞는다 |
| **R3** | P1 | 제출 묶음·테스트 예측 파일 | `press_submission/tools/make_submission_zip.py:13-15`; `press_guard/train.py:82`(`analysis/press_advance/primary.csv` 대조); `press_guard/README.md`(제출 예측 파일 지정 없음) | **확인한 증상.** 조립기 목록을 계산해 보니 `press_submission/`만 담는다(70개 파일, 8.1 MB). 최종 모델 코드·저장 모델·v2 테스트 예측이 없다. `train.py`가 읽는 press_advance, 보완·진단·외부·지도학습 패키지도 빠진다. `train.py`가 쓰는 `predictions_{normal,abnormal}_{A,B}.csv`를 제출용 테스트 예측 파일로 지정하거나 열을 설명한 문서가 없다. **할 일.** ① 최종 패키지용 조립기를 만든다(`--dry-run` 목록, SHA-256, 블라인드 검사). 넣을 것은 코드, 의존성 파일, 학습용 CSV 2개, 저장 모델, 테스트 예측 파일, expected, README이고 작업 기록은 뺀다. ② 테스트 예측 파일은 분할별 1개로 합치고 정답 구분 열(정상 평가/이상)을 넣어 파일만으로 F1을 다시 계산할 수 있게 한다. ③ README에 열 사전과 이상 600행 재사용 사실을 적는다. ④ 풀린 사본에서 저장 모델로 같은 파일을 다시 만드는 추론 전용 명령을 둔다(예: `predict.py --split A`) | dry-run 목록대로 복사한 임시 사본에서 R2 한 명령과 추론 전용 명령이 통과한다. 다시 만든 테스트 예측 파일의 SHA-256이 동봉본과 같다 |
| **R4** | P1 | 의존성 명세 | `press_submission/requirements.txt:1-8`; `press_submission/run_all.py:27`(→ `press/lstm_ae.py:19`); `press_guard/`(의존성 파일 없음) | **확인한 증상.** 파이썬 버전은 주석뿐이다. 고정한 numpy 1.26.4는 3.13 이상용 휠이 없어 3.13(uv 해석)과 3.14(pip)에서 설치가 실패한다. 3.11·3.12와 Windows·Linux 3.12는 해석된다. torch를 뺀 venv에서는 `run_all.py`가 최상단에서 torch를 import해 v1 2단계부터 실패하고, v2 분석까지 막힌다. Linux x86_64에서는 torch 2.5.1이 nvidia·triton 13개 패키지(수 GB)를 끌어온다. 전이 의존성도 고정하지 않았다. **할 일.** ① `environment.yml`을 둔다(`python=3.12`, `pip -r requirements.txt`). ② 최종 모델용 requirements(torch 제외)와 LSTM 비교용 `requirements-lstm.txt`(CPU 휠 인덱스 안내)를 나눈다. ③ lstm_ae import를 4단계 안으로 옮긴다. ④ `pip freeze` 잠금 파일을 둔다. ⑤ 진입점에서 파이썬 버전을 확인한다 | `conda env create -f environment.yml`로 만든 빈 환경에서 R2 한 명령이 통과한다. torch 없는 환경에서 최종 모델 경로(verify 20/20)가 통과한다. 3.13 이상에서는 안내를 내고 멈춘다 |
| R5 | P2 | verify 범위 | `press_guard/verify.py:22-24` | expected manifest에 테스트 예측 4개 파일의 해시가 있지만 verify는 집계 표만 비교한다. 이번 네 실행에서는 모두 비트 단위로 같았다(평가관 계산). 같은 환경이면 해시 일치를, 다른 환경이면 행·열 허용오차(경보 열은 정확 일치)를 verify 항목에 넣는다 | 예측 파일 한 행을 바꾸면 verify가 실패하는 테스트가 있다 |
| R6 | P2 | 외부 자료 없는 환경 | `analysis/press_supplement/contract.py:31·63`, `test_contract.py` | Git에서 뺀 UCI ZIP(73 MB)이 없으면 보완 계약 테스트 11개 중 5개가 `FileNotFoundError`로 **실패**한다(새 venv 클론에서 재현). 없을 때는 E2 검사를 이유와 함께 건너뛰고, `press_external/acquire.py` 명령과 SHA-256을 README에 둔다 | ZIP 없는 새 클론에서 실패 0(건너뜀 표시), ZIP을 넣으면 11/11 |
| R7 | P2 | 보완 verify 거짓 실패 | `analysis/press_supplement/uci_v2.py:251`, `verify.py:66` | README가 안내하는 E2 `--no-cache` 실행은 결과 CSV 4개가 동결값과 바이트까지 같다. 그런데도 manifest config의 `cache_used`(False 대 True)가 달라 verify가 "실행 설정이 동결 실행과 다름"으로 실패한다. 결과에 영향이 없는 실행 옵션은 비교할 config에서 빼고 따로 기록한다 | `--no-cache` 실행이 verify를 통과하고, `CACHE_VERSION`을 바꾸면 여전히 실패한다 |
| R8 | P2 | 분석 패키지 검증 계약 | `analysis/press_evidence/`, `analysis/press_supervised/`, `analysis/press_advance/`(README 없음) | 루브릭 근거 표 17개, 지도학습 기준선, 후보 비교는 manifest만 있고 동결 기대값과 verify가 없다. 이번 재실행은 커밋본과 바이트가 같았지만 팀 검증기로는 확인할 수 없다. 보완 실험의 `contract.py/verify.py`를 공용으로 만들어 세 패키지에 적용하고, R2 진입점의 verify 요약에 넣는다. press_advance에 실행법 README를 둔다 | 세 패키지 모두 산출물을 변조하거나 지우면 verify가 실패하고, 재실행 결과는 통과한다 |
| R9 | P2 | 교차 기기 취약점 | `press_guard/analyze.py:71`(v1 `model_comparison_all.csv`를 v1 expected manifest 해시와 **바이트 일치**로 대조) | 이 기기에서는 LSTM을 처음부터 다시 학습해도 바이트가 같아 통과했다. 그러나 LSTM 행 F1 값 하나의 마지막 자리(차이 약 1e-17)만 바꿔도 analyze가 `model_comparison_all.csv: 실행 후 변경`으로 거부했다(Phase I). 다른 기기에서는 v1 verify가 허용오차 1e-3 안에서 통과해도 여기서 막히므로, 원본부터 전체를 다시 만드는 경로가 다른 기기에서 끊긴다. 해시 대신 v1 verify의 허용오차 비교 결과를 받도록 바꾼다 | v1 비교표의 LSTM 열을 1e-6 바꾼 사본으로 analyze가 통과하고, 1e-2 바꾸면 실패한다 |
| R10 | P2 | 문서 정정 | `press_guard/README.md:32·35·46-52·70`, `press_guard/tools/clean_repro.sh:4`, `analysis/press_supplement/README.md` 등 | ① `/opt/anaconda3/bin/python` 절대 경로 25곳(press_guard README 14, 보완 README 7 등)과 POSIX 전용 환경변수 문법을 `python`으로 바꾸고 PowerShell 병기. ② "결과 CSV 10개"는 실제 15개. ③ 시간 정정: analyze "약 5초"는 실측 17초, clean_repro "약 1분"은 실측 약 4분이고 audit가 172초를 차지한다. press_supervised "약 15분"은 실측 2.3분이다. ④ 제출용 README를 작업 기록(검수 이력·도구 이름)과 분리한다 | README 명령을 새 Windows·macOS 셸에 그대로 붙여 넣어 실행되고, 적힌 개수·시간이 실측과 맞는다 |
| R11 | P2 | 실행 환경 처리 | `press_submission/press/data.py:155-164`; `press_guard/analyze.py:358`; `press_submission/press/data.py:21`(`DATA_SUBDIR`) | ① 스레드 수를 코드에서 고정한다(threadpoolctl). 미설정 때 결과는 같지만 train 99초·analyze 93초로 4~5배 느렸다(동시 부하 상태). ② v2 manifest의 `environment.blas`가 null이다. R24는 보완 실험·진단 표에만 반영됐으니 공용 `environment()`를 고친다. ③ v2 그림 글꼴 목록에 Windows용 `Malgun Gothic`과 Linux 나눔 글꼴 이름 `NanumGothic`이 없다(macOS 이름 `Nanum Gothic`만 있음). v1 `diagnosis.py:22`에는 둘 다 있다. ④ 주최 측 데이터 ZIP은 `data/*.csv` 구조인데 코드는 `data/3_소성가공_예지보전/`를 요구해 `--root`로 줄 수 없다. ZIP이나 폴더를 직접 받는 옵션을 둔다 | 스레드 변수 없이 부하 없는 기기에서 train이 30초 안쪽이다. manifest에 BLAS 이름·버전·스레드가 남는다. Windows 글꼴로 한글이 깨지지 않는다. 주최 측 ZIP 경로 하나로 실행된다 |

## 3. 수정 불가 한계

| 한계 | 내용 |
|---|---|
| 다른 OS·CPU 실측 | 이 기기는 macOS arm64 한 대다. Windows·Linux는 원인 조건만 모의했다(CP949 기본 인코딩, `resource` 부재, 스레드 수, 휠 해석). 다른 CPU·BLAS에서는 부동소수 차이가 순위 p값을 바꿀 수 있어 비트 동일은 보장되지 않는다. 허용오차와 경보 일치로만 보장할 수 있다. 팀이 Windows PC나 KAMP-NOTE에서 한 번 실행하면 범위를 좁힐 수 있다(R1 완료 기준) |
| LSTM 재학습 | PyTorch 결과는 기기·빌드에 따라 달라질 수 있다(v1 README가 이미 적었다). 비교용 기준모델이라 최종 모델 수치에는 영향이 없다 |
| 외부 자료 | UCI 유압 자료(73 MB)는 제3자 배포물이다. 가용성과 재배포 조건을 팀이 통제할 수 없어 획득 스크립트와 해시로 대신한다 |
| 테스트셋 정의 | 공식 별도 테스트셋이 없다. 테스트데이터 예측결과는 팀이 정한 분할 A/B의 평가 구간 예측이고, 이상 600행은 두 분할에 같다. 정의의 문제라 코드로 없앨 수 없다. README에 역할을 적는 데까지만 가능하다 |

## 4. 직접 수행한 검증과 명령

모든 스크립트는 이 폴더에 있다. 저장소 HEAD를 새로 클론하고 대회 원본 CSV 2개만 복사한 뒤 실행했다. 임시 폴더는 환경변수 `J06_BASE`로 바꿀 수 있다(기본은 이 세션의 임시 폴더). 파이썬은 `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python`이다(Ec·D 제외).

```bash
cd yejun/analysis/press_rubric_review/cycle2/round1
bash judge06_phaseA_clean_repro.sh      # 저장소 재현 스크립트 그대로: v2 clean_repro.sh, v1 clean_repro.sh --with-lstm
bash judge06_phaseB_readme_path.sh      # press_guard/README.md 문자 그대로(train→analyze 실패) → v1 --steps 2 보충 → 20/20 → predict.py
bash judge06_phaseC_full_raw.sh         # 원본만: v1 run_all 1~5(LSTM 처음부터)→v1 verify→press_advance→v2 4단계→진단 표→보완 verify·--rerun E1,E2,E3(새 TMPDIR)→테스트→추론 전용
bash judge06_phaseD_venv.sh             # python.org 3.12.8 venv + requirements.txt → v2 전체·테스트; torch 없는 venv; py3.14 pip dry-run; uv 해석(3.11~3.13, Windows·Linux 3.12)
bash judge06_phaseE_portability.sh      # LC_ALL=ko_KR.CP949 모의, resource 차단 모의(sitecustomize), OMP 미설정, 주최 측 ZIP 구조, press_supervised 재실행
bash judge06_phaseF_e2_nocache.sh       # E2 --no-cache 결과는 바이트 동일, verify는 config 불일치로 실패
bash judge06_phaseG_archive_clean_repro.sh # git archive로 만든 git 없는 사본에서 clean_repro.sh(종료 코드 128)
bash judge06_phaseT_timing.sh           # 부하 낮을 때 단계별 시간
bash judge06_phaseH_supervised_v2.sh    # 3ad2452 press_supervised 재실행 결정성
bash judge06_phaseI_v1table_tolerance.sh # v1 비교표 한 값의 마지막 자리 변경 → v2 analyze 거부 여부
python judge06_check.py                 # 비트 동일성·추론 전용·재생성 표 대조·조립기 목록(ZIP 미생성)·정적 이식성 → judge06_results.json
```

- Phase E의 Ea08·Ea09(웹 콘솔 처리 함수 직접 호출)는 첫 실행 뒤 추가해 같은 클론에서 따로 돌렸고, 결과를 같은 로그 끝에 붙였다.
- 실행 기록: `judge06_phase{A,B,C,D,E,F,G,H,I,T}_*.log`, 대조 결과는 `judge06_results.json`·`judge06_check.log`에 있다. Phase E 로그 가운데 CP949 모의 실행의 출력은 `[cp949 출력]` 표시를 붙여 UTF-8로 풀어 적었다.
- 정리: 저장소 재현 스크립트가 `/var/folders/.../T/`에 남긴 임시 클론은 확인 후 지웠다(macOS `mktemp -d`는 TMPDIR을 따르지 않는다). 가상환경 3개(1.3 GB)도 확인 후 지웠고, 설치 목록은 `judge06_venv312_pip_freeze.txt`에 남겼다. 나머지 클론은 세션 임시 폴더에 있다.
