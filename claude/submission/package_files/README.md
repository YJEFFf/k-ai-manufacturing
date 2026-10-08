# 프레스 유압펌프 이상 경보: 실행 코드 (팀 북적북적)

제6회 K-인공지능 제조데이터 분석 경진대회 과제 ③ 결과보고서의 수치를 이 폴더에서 처음부터 다시 만든다. 명령 하나로 전처리 → 학습 → 추론 → 결과 생성 → 보고서 수치 대조까지 돈다.

## 0. 먼저 5분 확인(설치 없이)

- zip에 든 `predictions/test_predictions_A.csv`·`_B.csv`에서 `label`과 `locked_v2_R1_realtime`(True/False)으로 행 F1을 계산하면 보고서의 공식 성능인 잠금 모델(1단계 "주의") 1.000·0.995가 나온다. `final_v2_R1_R2_realtime`(2단계 "점검 요청", test 확인 뒤 더한 R2 규칙)은 1.000·1.000, `v2_realtime`은 0.965·0.970이다
- 그다음 `--quick`(약 13분, 대조 28개)으로 전처리 → 학습 → 추론 → 예측 파일 생성을 확인하고, 시간이 되면 전체(대조 43개)를 돌린다

## 1. 환경

- 파이썬 **3.13**이 필요하다. GPU는 쓰지 않는다(LSTM도 CPU에서 학습). 패키지 설치 뒤에는 인터넷이 필요 없다
- 설치(둘 중 하나)
  - venv: Windows `py -3.13 -m venv venv` → `venv\Scripts\python -m pip install -r requirements.txt` / macOS·Linux `python3.13 -m venv venv` → `venv/bin/python -m pip install -r requirements.txt`
  - conda: `conda env create -f environment.yml` → `conda activate bukjeok-press`
  - 파이썬 3.13이 없는 PC(구형 Anaconda, KAMP-NOTE 등)에서는 conda 방법을 쓴다. `environment.yml`이 파이썬 3.13을 함께 설치한다
- 가상환경을 켜지 않고 `venv\Scripts\python run_all.py`(macOS·Linux는 `venv/bin/python run_all.py`)로 바로 실행해도 된다. PowerShell에서 `activate`가 실행 정책에 막힐 때 이 방법을 쓴다
- Linux에서 `pip install torch`는 CUDA 라이브러리까지 받는다. 먼저 `pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu`로 CPU 판을 받은 뒤 requirements를 설치하면 빠르다
- 판은 결과를 만든 환경 그대로 고정했다(requirements.txt). 판이 다르면 `run_all.py`가 시작할 때 알려 준다
- 검증 환경: Windows 11, Intel Core Ultra 7 155H(16코어), RAM 32GB. macOS·Linux에서는 실행해 보지 않았다

## 2. 실행

```
python run_all.py            # 전체 (새 환경 기준 약 55분, 다른 작업이 같이 돌면 더 걸림)
python run_all.py --quick    # 핵심만: 진단·모델·test 예측·2.4·2.7·4.3절 사후 계산·대조 (약 13분)
```

- 끝나면 화면에 결과 대조표가 나온다. 모두 "일치"면 보고서 수치가 그대로 재현된 것이다
- 종료 코드: 0 = 성공, 1 = 어떤 단계가 실패(화면에 로그 위치가 나온다), 2 = 실행은 끝났지만 대조 불일치
- 새 가상환경에 설치한 뒤 위 명령을 그대로 실행해 대조 43개 모두 일치를 확인했다(Windows 11, Core Ultra 7 155H, 전체 54.8분·quick 단계 합 13.0분, 2026-10-08)
- 대조 항목은 결론을 좌우하는 대표 수치다. 나머지 표 값은 산출물에서 그대로 읽는다: 2.4절 표 → `code/press/tvt/outputs/tvt_test.csv`, 열 → `tvt_record_count.csv`·`tvt_r1_baselines.csv`, 2.5절 이상 확률 → `tvt_probability.json`, 2.6절 → `validation_summary.json`, 3.2절 표 → `code/press/domain/outputs/06_operating_regime.csv`, 1.6절 → `code/press/cases/outputs/facts_extra.json`
- 잠금 규칙이 고른 모델은 `code/press/tvt/outputs/tvt_selection.json`의 `selected_realtime`(v2+H1 = 보고서 v2+R1)에서 확인한다

## 3. 결과물

| 위치 | 내용 |
|---|---|
| `predictions/test_predictions_A.csv`, `_B.csv` | **test 예측 결과(제출물).** 분할 A·B의 test 구간 모든 행. zip에 이미 들어 있고, 실행하면 같은 파일을 다시 만든다(줄바꿈을 맞추면 바이트 단위로 같다) |
| `logs/` | 단계별 로그, `run_summary.json`(단계별 시간·대조 결과) |
| `code/press/*/outputs/` | 단계별 산출물(보고서 표·그림의 원자료) |

- 주최 측이 테스트 파일을 따로 주지 않아, 보고서 1.7절 시간순 분할의 test 구간(정상 A 기록 480~599·B 420~599, 이상 21기록 중 뒤 11기록)을 테스트데이터로 썼다. 행 수는 A 4,414(정상 4,090·이상 324), B 6,421(정상 6,097·이상 324)이다
- 예측 파일은 경보 판정(True/False, 0/1)과 v2 이상 확률 두 열을 담는다. 확률은 `code/press/tvt/08_probability.py`가 valid 자료로만 보정해 붙인다

예측 파일의 열

| 열 | 뜻 |
|---|---|
| `subset`, `label` | normal(정상, 0) / abnormal(이상, 1). label은 채점용이며 모델 입력에는 쓰지 않았다 |
| `rec` | `test:normal:k`는 test 정상 구간 안 순번(보고서 기록 번호 = A는 k+480, B는 k+420), `test:abnormal:k`는 이상 기록 번호 k(10~20) |
| `pos`, `ts` | 기록 안 위치(0 = 첫 행), 수집 시각 |
| `final_v2_R1_R2_realtime` | 2단계 모델(v2+R1+R2, "점검 요청") 실시간 경보(행이 들어오는 순간 판정, True/False). R2는 경보를 빼기만 하므로 늘 `locked_v2_R1_realtime`의 부분집합이다 |
| `final_v2_R1_R2_record` | 2단계 모델 기록 단위 판정(기록이 끝난 뒤, 0/1) |
| `locked_v2_R1_*` | **공식 성능**: valid에서 골라 잠근 모델(v2+R1, 1단계 "주의") |
| `v2_realtime`, `v2_record` | 기반 모델 v2 |
| `v2_prob_site1pct`, `v2_prob_fileprior` | v2 이상 확률(0~1). valid 자료로만 보정했고, 사전 비율은 각각 현장 가정 1%와 test 파일의 이상 행 비율. 경보 판정과는 무관(보고서 2.5절) |

- `code/press/cases/v2_predictions/`에도 같은 이름의 파일이 있지만, v2 원래 평가를 재현하는 용도라 제출물이 아니다

## 4. 단계와 보고서 대응

| 단계 | 스크립트 | 하는 일 | 보고서 |
|---|---|---|---|
| 1 진단 | `code/press/cases/01_case_features.py`, `03_facts_extra.py`, `code/press/06_alias_frequency_audit.py` | 기록 구조, 형식 누수, 전류 겉보기 주파수 | 1장 |
| 2 모델 | `code/press/tvt/01_scores.py` → `02_select_on_valid.py` → `03_score_test.py` → `05_test_predictions.py` → `08_probability.py` | 정상 학습 → valid 보정·선택·해시 잠금 → 잠금 확인 후 test 채점 → 예측 파일 → 이상 확률(valid로만 보정) | 2.3~2.5절 |
| 3 검증 | `code/press/tvt/04_validation.py` | 인공 고장 주입, 분할 변경, 수집 조건 흔들림 | 2.6절 |
| 4 사후 분석 | `code/press/domain/01~07_*.py`, `code/press/tvt/06_record_count.py`, `07_r1_on_baselines.py`, `09_component_ablation.py`, `10_threshold_free.py`, `11_posthoc_numbers.py`, `12_ramp_warning.py`, `13_r2_oos_alpha.py`, `14_baseline_injection_ridge.py`, `15_record_auroc_featbase.py`, `16_jitter_ridge_combo.py` | 신호 물리, 사건 안 추세, PCA 관리도, CUSUM·EWMA·불확실성, 지도학습 대조, 운전 상태별 오경보, 이상 양상별 먼저 볼 곳, 기록 하나를 1개로 센 F1, R1을 베이스라인에 붙인 비교, v2 성분 절제(인공 주입), 문턱과 무관한 AUROC·부트스트랩 구간, 사후 보조 수치(max|z|+R1+R2, 확률 AUROC·ECE, 수집 공백), 합성 열화 조기경보, R2 준-표본 밖·α 실측·블록 부트스트랩, 베이스라인 인공 주입·Ridge 예측 오차, 기록 단위 AUROC·특징 맞춤 베이스라인, 표본 시각 흔들림 반증·Ridge 병행 | 1.4~1.6, 2.2, 2.4·2.7(사후), 2.5, 3.1, 3.2, 3.6, 4.2, 4.3절 |

- 4단계는 test 채점 이후에 덧붙인 분석이다. 모델 선택(2단계의 해시 잠금)에는 쓰지 않았다. tvt/06·07·10~12는 `--quick`에서도 돌고, 09(성분 절제)·13(R2 준-표본 밖)·14(베이스라인 주입·Ridge, 약 23분)·15(특징 맞춤)·16(흔들림·병행)은 전체 실행에서만 돈다
- 보고서의 R1(사건 지속)·R2(교차 확인)는 코드에서 H1·H2로 부른다
- `run_all.py`가 다시 만들지 않는 수치: 2.6절 UCI 외부 실험, 2.4절 팀 문서의 단순 규칙 F1, 4.2절 콘솔 화면은 v1·v2·v3 모듈을 만들 때의 결과를 인용했다
- 2.7절 보완 LSTM 비교(사후)는 `yejun/analysis/press_lstm_improvement/`의 별도 실험이다. 결과 표는 그 폴더 `outputs/`에, 실험 설계(결과를 열기 전에 고정)는 `PROTOCOL.md`에, 결과 정리는 `README.md`에 있다. 다시 돌리려면 먼저 루트의 `run_all.py` 전체를 실행해 `code/press` 산출물을 만든 뒤, 그 폴더에서 README의 "다시 실행" 순서대로 실행한다(학습 162회, Apple M2 8코어에서 약 8시간). LSTM 학습은 PC마다 조금 달라 `run_all.py` 대조에는 넣지 않았다

## 5. 폴더 구조

```
run_all.py               한 번에 실행
requirements.txt         패키지 판(파이썬 3.13)
environment.yml          conda용
expected_results.json    보고서 작성 때의 결과(대조 기준)
data/                    주최 측 원본 CSV 2개
predictions/             test 예측 결과(제출물)
code/press/              우리 코드(cases 진단, tvt 모델, domain 사후 분석)
yejun/                   v1·v2·v3 모듈. 우리 코드가 그대로 불러 쓴다
yejun/analysis/press_lstm_improvement/   보완 LSTM 실험(2.7절 사후, run_all.py 밖, 결과 표 포함)
```

- `yejun/` 아래의 README·PLAN·HISTORY와 `yejun/press_submission/run_all.py`는 모듈을 만들 때의 기록이다. 그 안의 실행 방법(파이썬 3.12, 이 zip에 없는 requirements 파일 등)은 쓰지 않는다. 실행은 루트의 `run_all.py` 하나로 한다

## 6. 재현성 메모

- 원본 CSV 2개는 시작할 때 SHA-256으로 확인한다. 파일이 바뀌면 멈춘다. `press_data_normal.csv` 20,000행, `outlier_data.csv` 600행
- 무작위가 들어가는 곳은 seed를 고정했다. 가이드북 방식 LSTM 오토인코더(비교용 기준선)는 seed 0·스레드 1로 고정했지만 CPU나 torch 빌드가 다르면 부동소수 연산 순서가 바뀌어 값이 조금 달라질 수 있어, 대조 허용 오차를 0.05로 두었다. 잠금·2단계 모델 F1은 소수 9자리까지 같아야 한다
- 예측 파일 대조는 줄바꿈(Windows CRLF, macOS·Linux LF)을 맞춘 뒤 해시를 비교한다. 내용이 같으면 OS와 관계없이 일치로 나온다
- 사건 안 추세 분석(4단계)의 결과 파일에는 실행 날짜가 들어간다. 이 필드만 날짜에 따라 달라진다

## 7. 데이터 출처

중소벤처기업부, Korea AI Manufacturing Platform(KAMP), 소성가공 예지보전 AI 데이터셋, 스마트제조혁신추진단(㈜인터엑스), 2022.12.23, https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48
