# 프레스 유압펌프 이상 경보 — 실행 코드 (팀 북적북적)

제6회 K-인공지능 제조데이터 분석 경진대회 과제 ③ 결과보고서의 수치를 이 폴더에서 처음부터 다시 만든다. 명령 하나로 전처리 → 학습 → 추론 → 결과 생성 → 보고서 수치 대조까지 돈다.

## 1. 환경

- 파이썬 **3.13** (Windows 11, CPU에서 실행·검증). GPU는 필요 없고, 패키지 설치 뒤에는 인터넷도 필요 없다
- 설치(둘 중 하나)
  - `python -m venv venv` → `venv\Scripts\activate`(macOS·Linux는 `source venv/bin/activate`) → `pip install -r requirements.txt`
  - `conda env create -f environment.yml` → `conda activate bukjeok-press`
- 판은 결과를 만든 환경 그대로 고정했다(requirements.txt). 판이 다르면 `run_all.py`가 시작할 때 알려 준다

## 2. 실행

```
python run_all.py            # 전체 (새 환경 기준 약 56~80분, PC 부하에 따라 다름)
python run_all.py --quick    # 핵심만: 진단·모델·test 예측·대조 (약 13분)
```

- 끝나면 화면에 결과 대조표가 나온다. 모두 "일치"면 보고서 수치가 그대로 재현된 것이다
- 종료 코드: 0 = 성공, 1 = 어떤 단계가 실패(화면에 로그 위치가 나온다), 2 = 실행은 끝났지만 대조 불일치
- 새 가상환경에 설치한 뒤 위 명령을 그대로 실행해 대조 21개 모두 일치를 확인했다

## 3. 결과물

| 위치 | 내용 |
|---|---|
| `predictions/test_predictions_A.csv`, `_B.csv` | **test 예측 결과(제출물).** 분할 A·B의 test 구간 모든 행. zip에 이미 들어 있고, 실행하면 같은 파일을 다시 만든다(바이트 단위로 같아야 한다) |
| `logs/` | 단계별 로그, `run_summary.json`(단계별 시간·대조 결과) |
| `code/press/*/outputs/` | 단계별 산출물(보고서 표·그림의 원자료) |

예측 파일의 열

| 열 | 뜻 |
|---|---|
| `subset`, `label` | normal(정상, 0) / abnormal(이상, 1). label은 채점용이며 모델 입력에는 쓰지 않았다 |
| `rec`, `pos`, `ts` | 기록 번호, 기록 안 위치(0 = 첫 행), 수집 시각 |
| `final_v2_R1_R2_realtime` | **최종 모델** 실시간 경보(행이 들어오는 순간 판정, True/False) |
| `final_v2_R1_R2_record` | 최종 모델 기록 단위 판정(기록이 끝난 뒤, 0/1) |
| `locked_v2_R1_*` | valid에서 잠근 선택 모델(v2+R1) |
| `v2_*` | 기반 모델 v2 |

- `code/press/cases/v2_predictions/`에도 같은 이름의 파일이 있지만, v2 원래 평가를 재현하는 용도라 제출물이 아니다

## 4. 단계와 보고서 대응

| 단계 | 스크립트 | 하는 일 | 보고서 |
|---|---|---|---|
| 1 진단 | `code/press/cases/01_case_features.py`, `03_facts_extra.py`, `code/press/06_alias_frequency_audit.py` | 기록 구조, 형식 누수, 전류 겉보기 주파수 | 1장 |
| 2 모델 | `code/press/tvt/01_scores.py` → `02_select_on_valid.py` → `03_score_test.py` → `05_test_predictions.py` | 정상 학습 → valid 보정·선택·해시 잠금 → 잠금 확인 후 test 채점 → 예측 파일 | 2.3~2.5절 |
| 3 검증 | `code/press/tvt/04_validation.py` | 인공 고장 주입, 분할 변경, 수집 조건 흔들림 | 2.6절 |
| 4 사후 분석 | `code/press/domain/01~06_*.py`, `code/press/tvt/06_record_count.py` | 신호 물리, 사건 안 추세, PCA 관리도, CUSUM·EWMA·불확실성, 지도학습 대조, 운전 상태별 오경보, 기록 하나를 1개로 센 F1 | 1.4~1.6, 2.2, 2.4(† 열), 2.5, 3.1, 3.2절 |

- 4단계는 test 채점 이후에 덧붙인 분석이다. 모델 선택(2단계의 해시 잠금)에는 쓰지 않았다
- 보고서의 R1(사건 지속)·R2(교차 확인)는 코드에서 H1·H2로 부른다

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
```

## 6. 재현성 메모

- 원본 CSV 2개는 시작할 때 SHA-256으로 확인한다. 파일이 바뀌면 멈춘다
- 무작위가 들어가는 곳은 seed를 고정했다
- 가이드북 방식 LSTM 오토인코더(비교용 기준선)는 학습 난수 때문에 값이 조금 달라질 수 있어 대조 허용 오차를 0.05로 두었다. 최종 모델 점수와 예측 파일은 바이트 단위로 같아야 한다
- 사건 안 추세 분석(4단계)의 결과 파일에는 실행 날짜가 들어간다. 이 필드만 날짜에 따라 달라진다

## 7. 데이터 출처

중소벤처기업부, Korea AI Manufacturing Platform(KAMP), 소성가공 예지보전 AI 데이터셋, 스마트제조혁신추진단(㈜인터엑스), 2022.12.23, https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48
