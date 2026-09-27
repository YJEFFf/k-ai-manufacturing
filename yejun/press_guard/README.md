# Press Guard v2 — 프레스 유압펌프 이상 조기 경보(최종 모델)

정상 운전 자료만으로 학습·보정하는 이상 조기 경보 모델이다. 0.1초 관측마다 다음을 낸다.

- 경보와 경보 단계(1단계 주의·2단계 점검 요청)
- 근거 성분과 권장 확인
- 이상 확률(사전 비율 가정에 조건부)

경보는 점검 대기열로 모인다. 이 문서는 코드·실행 설명서이며 대회 보고서가 아니다. 구현·검수 이력은 [HISTORY.md](HISTORY.md), 현장 운영 절차는 [OPERATIONS.md](OPERATIONS.md)에 있다.

## 빠른 시작

```bash
conda env create -f yejun/press_guard/environment.yml && conda activate press-guard   # 또는: pip install -r yejun/press_guard/requirements.txt (파이썬 3.10~3.12)
python yejun/press_guard/reproduce.py --data "Dataset_소성가공 예지보전 AI 데이터셋.zip"      # 주최 측 ZIP 배치 + 한 명령 재현
```

- **결과 위치:** `yejun/press_guard/outputs/`에 테스트 예측(`test_predictions_A.csv`·`test_predictions_B.csv`), 지표(`metrics.csv`), 단계별 요약(`reproduce_summary.json`)이 생긴다.
- **검증:** 한 명령이 v1 선행 결과, v2 동결값 비교(verify), 분석 패키지 동결값 비교까지 실행한다. 한 단계라도 실패하면 종료 코드 1이다.
- **전체 모드:** `--full`은 v1 LSTM 비교(torch 필요, `requirements-lstm.txt`), 후보 비교, 보완 실험 E1~E3 재실행까지 한다.
- **시험:** `--tests`는 끝에 pytest와 웹 회귀 시험을 돌린다.
- **Windows:** PowerShell에서도 같은 명령이다. 모든 파일 입출력은 UTF-8이고 CP949 콘솔에서도 멈추지 않는다. 한글이 깨져 보이면 `chcp 65001`을 쓴다.
- **데이터 배치:** 원본 두 CSV가 이미 `yejun/press_submission/data/3_소성가공_예지보전/`에 있으면 `--data`는 필요 없다. SHA-256이 대회 원본과 다르면 멈춘다.

## 모델

| 부분 | 내용 |
|---|---|
| 입력 | `TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current`. 라벨·날짜·파일명은 입력이 아니다(날짜 이동·라벨 변경에 결과 불변, audit) |
| 전처리 | 저장 형식 정밀도 맞춤(matched: 진동 1e-4, 전류 1.1920929 격자), 정상 학습 구간으로 표준화. 0.1초 간격이 끊기면 새 기록구간이고, 창은 기록구간 안에서만 쓴다 |
| 성분 | ① 크기: 세 센서 max\|z\|(위치 0부터) ② 파형: 전류 사인 적합 1−R²(위치 5부터 6행 창, 7부터 8행 창) ③ 동역학: AR(2) 전류 예측 오차(위치 2부터) |
| 결합 | 성분마다 정상 학습 꼬리로 g=−log10(꼬리 확률)을 만들고 최댓값(fmax = 정상 꼬리 확률의 Tippett 최소 p 결합)을 쓴다. 경보마다 문턱을 넘은 성분이 있어 근거 → 조치로 이어진다 |
| 보정·경보 | 정상 보정 기록구간의 최대 점수로 conformal p값. α ∈ {1, 3, 5}%는 **알림 단위(기록구간, 연속 입력은 50행 블록)당** 비율이다 |
| 2단계 알림 | 첫 경보는 1단계 "주의"다. 같은 건(경보가 이어진 블록 묶음) 안의 경보가 2행에 이르면 2단계 "점검 요청"으로 격상하고 다시 알린다 |
| 이상 확률 | 경보와 분리된 층([probability.py](probability.py)). 정상 보정 행과 이상 행에 맞춘 등방 회귀로 우도비(LR)를 구하고, 사전 비율 π로 확률을 낸다. LR 상한은 보정 단위 수+1(=121)이다 |
| 조치 | 근거 → 확인 대상 → 권장 확인 → 점검 항목 → 고장 모드 후보(FM1~FM6)를 한 원천(`model.DECISION_TABLE`)에 둔다. 품질 조치는 단계별로 다르다 |

설계(초반 창·AR(2))는 이미 본 이상 자료에서 v1의 미탐을 본 뒤 정했다. 선정 근거(탐색 장부 65항목, 중첩 선택 21/21, v1 대비 짝 비교)는 [press_selection](../analysis/press_selection/README.md)에 있다.

## 결과(α=1%, matched)

| 분할 | 모델 | 행 F1 | 미탐 행/600 | 정상 알림 구간 | 이상 탐지 구간 | 최대 첫 경보 지연 |
|---|---|---:|---:|---:|---:|---:|
| A | v1 | 0.910082 | 99 | 0/120 | 21/21 | 0.7초 |
| A | v2 | **0.961938** | **44** | 0/120 | 21/21 | **0.5초** |
| B | v1 | 0.920322 | 86 | 3/180 | 21/21 | 0.7초 |
| B | v2 | **0.970990** | **31** | 3/180 | 21/21 | **0.5초** |

- **A의 정상 0/120은 유리한 조건의 값이다.** A 평가 구간(480~599, 01:00~01:17)은 정상 77분 중 가장 조용한 시간대다. 최대 점수가 보정 중앙값을 넘는 구간이 12/120이다(교환가능하면 약 60, Mann–Whitney p=2.9e-11).
- **시간순 5창 비교(300~359 … 540~599):** F1 0.961938~0.971819, 정상 알림 0·0·2·0·0/60.
  - 420~479 폴드는 B와, 480~539 폴드는 A와 학습·보정이 같아 보정값이 비트 단위로 같다.
  - 420~479의 2/60은 B 오경보 3건 중 2건(구간 423·461)이다. 오경보 근거로 합산하지 않는다.
  - 동결 모델과 독립인 폴드는 300~359·360~419·540~599 3개이고 모두 0/60이다.
- **2단계:** 정상 평가(A·B, 시간순 5창)에서 모두 0건이다. 이상 21구간은 모두 격상했다(지연 중앙 0.2초, 최대 0.6초).
- **알림률:** α 3%에서 B 정상 알림은 5/180, 5%에서 7/180이다(v1 4·6). coarse 입력 B는 5/180(v1 4)이다. 모든 조건에서 오경보가 같다고 말하지 않는다.
- **이상 자료:** A/B는 같은 이상 21구간(07-17 일요일 3분)을 쓰고, 정상과 이상은 다른 날이다. 이미 본 자료의 탐색 평가이며 새 날짜·설비 성능의 근거가 아니다.

## 테스트 예측 파일

`outputs/test_predictions_A.csv`(4,690행)와 `_B.csv`(6,697행)는 정상 평가 기록과 이상 600행을 α=1%로 순차 추론한 결과다. 이상 600행은 두 파일이 같다. 파일만으로 F1을 다시 계산할 수 있다(`label`과 `alarm`: A 0.961938, B 0.970990).

| 열 | 뜻 |
|---|---|
| `subset`, `label` | 정상 평가(`normal_test`, 0) / 이상(`abnormal`, 1). 평가용이며 모델 입력이 아니다 |
| `row_id`, `record_id`, `position`, `timestamp`, `status` | 행 번호, 기록구간 번호, 기록구간 안 위치(0.1초 단위), 원래 시각, 수집 상태(`ok`·`bad_value`·`bad_timestamp`) |
| `score`, `p_value`, `alarm` | 결합 점수, conformal p값, 경보(p≤α) |
| `notification`, `alert_level`, `escalation` | 건의 첫 알림, 단계(0·1 주의·2 점검 요청), 2단계 격상 행 |
| `reason`, `action` | 문턱을 넘은 성분(magnitude·waveform·dynamics), 권장 확인 |
| `magnitude`, `current_residual`, `g_magnitude`, `g_waveform`, `g_dynamics`, `magnitude_sensor`, `waveform_window` | 성분 원값·꼬리 점수·크기 최대 센서·파형 창 |
| `likelihood_ratio`, `anomaly_probability`, `record_likelihood_ratio`, `record_probability`, `probability_prior`, `probability_source` | 행·기록구간(지금까지 최대) 우도비와 이상 확률(π=1%). 이상 행은 그 기록을 뺀 교차 적합 값(`leave_one_record_out`) |
| `anomaly_score`, `criterion`, `model_id`, `protocol_version`, `alert_unit`, `beyond_calibration_length`, `is_scored` | 1−p(정렬용, 확률 아님), 규칙, 모델 이름, 판, 알림 단위, 보정 길이 초과 여부, 점수 계산 여부 |

학습 없이 저장 모델로 같은 파일을 다시 만들 수 있다. SHA-256을 학습 실행 기록과 대조한다.

```bash
python yejun/press_guard/predict.py --split A --out test_predictions_A.csv
python yejun/press_guard/predict.py --input 새기록.csv --out 예측.csv --cases 대기열.csv --model yejun/press_guard/artifacts/guard_B.json
```

## 이상 확률

- **교차 평가(21겹, 이상 기록 1개씩 떼어 냄, 행 단위):**

  | 분할 | 방법 | Brier | log-loss | ECE |
  |---|---|---:|---:|---:|
  | A | 라벨 보정 확률 | 0.0072 | 0.046 | 0.0075 |
  | A | 유병률만 | 0.112 | 0.382 | — |
  | A | 1−p(확률 아님) | 0.012 | 0.110 | 0.036 |
  | B | 라벨 보정 확률 | 0.0056 | 0.037 | 0.0066 |
  | B | 유병률만 | 0.082 | 0.302 | — |
  | B | 1−p(확률 아님) | 0.023 | 0.120 | 0.078 |

  - 비교용 두 방법(배포하지 않음)도 같은 교차 평가로 쟀다: 상한 없는 등방 회귀는 ECE A 0.0012·B 0.0009(Brier 0.0069·0.0052), Platt은 0.0036·0.0022(0.0074·0.0055).
  - 배포 확률의 ECE가 더 큰 것은 LR 상한(121) 때문이다. 알림 한 건이 conformal 순위로 줄 수 있는 증거보다 크게 말하지 않도록 최상위 구간의 확률을 낮춘 결과이며, 보수적인 쪽으로의 어긋남이다.
  - 신뢰도 곡선은 [fig_probability_reliability_v2.png](outputs/fig_probability_reliability_v2.png)에 있다.
- **확률의 조건.** 이 확률은 대회 이상 모양(한 날 3분)과 날짜 교락이 만든 분리를 담는다.
  - 경보 문턱 점수에서의 확률은 분할마다 크게 다르다(π 1%에서 A 0.30, B 0.007).
  - 확률을 경보 기준으로 쓰지 않는다. 경보는 conformal p값으로만 정한다.
- **라벨 없는 환산**([label_free_alert_probability_v2.csv](outputs/label_free_alert_probability_v2.csv)):

  P(이상|알림) = π·TPR / (π·TPR + (1−π)·FAR)

  - 명목 FAR 1/121과 E1 전류 잡음 0.1σ 탐지율 95.5%를 쓰면 π 0.1%에서 10.4%, π 1%에서 53.8%다.
  - 보정 조건부 95% FAR를 쓰면 3.7%, 28.1%다.
  - p값 하나의 보수적 상한(Sellke–Bayarri–Berger, 우도비 ≤ 9.3)을 쓰면 π 1%에서 8.6% 이하다.

## 미탐·오경보가 몰리는 조건(요약)

[error_condition_summary_v2.csv](outputs/error_condition_summary_v2.csv)는 FN·FP가 몰리는 조건을 공정조건 대리변수로 옮긴 표다. 공정 상태 변수(부하·금형·스트로크)는 자료에 없어 신호로 대신한다. 모든 행은 원 산출물의 파일:행을 가리킨다. α=1%, A·B 순이다.

| 구분 | 조건(대리변수) | 오류/분모 | 비교·근거 |
|---|---|---|---|
| 미탐 | 기록 시작 0.2초 안 × 진동이 동반되지 않은 이상(수집 재개 직후) | 6/6 · 6/6 | 진동 높은 구간 20/36·14/36, 단측 Fisher p 0.044·0.0074(관측) |
| 미탐 | 기록 시작 0.2초 안 전체 | 26/42 · 20/42 | 위치 2 이상 18/558·11/558(관측) |
| 미탐 | 기록 시작부터 있는 전류 오프셋 0.8×진폭(고장 모양) | 탐지 3.3% · 28.8% | 10행째에 넣으면 100%(E1 주입) |
| 미탐 | 전류 진폭만 ×1.15(전류 수준 이동) | 탐지 0% · 6.3% | 정상 운전도 0.85~1.29배 오르내린다(E1 주입) |
| 미탐 | 4σ 미만 진동 이상 2σ · 약한 전류 오프셋 0.2× | 탐지 74%·94% · 40%·52% | 4σ·0.4×는 100%(E1 주입) |
| 오경보 | 상부 진동(AI0) 단발 충격(운전 강도) | α 5% 사건 17건 중 15건 | 경보 1행 13건, 가장 조용한 480~539 블록 0건(관측) |
| 오경보 | 문턱 근처 정상 구간(운전 강도·시간대) | B 7/180이 문턱의 0.9배 이상 | Spearman 진동 max\|z\| 0.61·전류 진폭 0.50·시간 −0.31(관측) |
| 오경보 | 전류 수준 상승(전류 배율) | B ×1.05 4/180, ×1.5 17/180 | 감시 규칙이 ×1.3부터 재보정 검토(스트레스) |
| 오경보 | 거친 계측 정밀도 | B 5/180(matched 3) | 재보정 대상(스트레스) |

## 현장 운영 기능

| 기능 | 파일 | 내용 |
|---|---|---|
| 점검 콘솔 | `serve.py`, `web/` | 사전 비율 선택, 1·2단계 건수, 대기열(단계 → 근거 수 → 경보 비율 → 최대 점수, 이상 라벨 없이 정함), 의심 생산 시간창·품질 조치·점검 항목, 점검 결과 기록과 CSV 내보내기, 10배속 모의 운용. `python yejun/press_guard/serve.py --port 8765` |
| 모의 운용 | `simulate.py` | CSV를 10 Hz(`--speed 1`) 또는 배속으로 흘려 알림을 즉시 출력·기록한다. 알림 행이 일괄 분석과 같다 |
| 운영 감시 | `monitor.py` | 창별 알림 단위 수를 보정 조건부 Beta-Binomial 95·99% 한도와 비교하고 전류 수준 이동을 본다. 재보정 검토 규칙과 "정상 확인 구간만 재보정" 규칙을 둔다 |
| 재보정 | `recalibrate.py` | 새 정상 CSV로 학습·보정·수락 검사를 한다. 정상 알림은 Beta-Binomial 95백분위(α 5%에서 6→7, 정상 거부 5% 이하), 주입 3종은 2초 탐지 90%. 검정력·알림 예산 환산·결과 기록으로 자료를 거르는 `--outcomes`를 둔다 |
| 운영 절차 | [OPERATIONS.md](OPERATIONS.md) | 정상 수집 → 재보정 → 1·2단계 → 판단표 → 품질 → 기록 → 복귀 확인 → 교대 감시 → 재보정, 흐름도·구성도 |

대기열 한계가 있다. 변화 순간에만 경보가 나는 계단형 전류 변화(주입 오프셋)는 경보 행 비율이 낮아 오경보보다 뒤로 밀릴 수 있다(B α 3·5%, [queue_injection_ranks_v2.csv](outputs/queue_injection_ranks_v2.csv)). 정렬 키 후보 4개의 비교는 [queue_key_selection_v2.csv](outputs/queue_key_selection_v2.csv)에 있다.

## 산출물

| 파일(outputs/) | 내용 |
|---|---|
| `metrics.csv`, `rolling.csv`, `cases_{A,B}.csv` | α별 행 지표·구간 알림, 시간순 5창, 혼합 대기열(정상+이상, 한 순위) |
| `model_comparison_v2.csv`·`.md`, `robustness_v2.csv`, `sensitivity_v2.csv`, `ablation_v2.csv` | 14개 모델 비교, 입력 정밀도 강건성, 전처리 재적합, 성분 절제 |
| `error_condition_summary_v2.csv` | FN·FP가 몰리는 조건 11행 요약: 공정조건 대리변수(수집 재개 직후·운전 강도·시간대·전류 수준·계측 정밀도·고장 모양), 오류/분모, 근거 종류(관측·주입·스트레스), 파일:행 |
| `error_conditions_v2.csv`, `error_conditions_segments_v2.csv`, `error_conditions_stats_v2.csv`, `interaction_2x2_v2.csv`, `records_first_alarm_v2.csv` | 미탐·오경보 조건(행·구간, 위치 2 이상 층 `*_pos_ge2` 포함), 신뢰구간·lift·Fisher, 구간 특징 분리표, 구간별 첫 경보 |
| `sensor_importance_v2.csv`, `position_vibration_misses_v2.csv`, `coupling_fit_v2.csv`, `coupling_records_v2.csv`, `fp_events_v2.csv`, `near_miss_v2.csv`, `near_miss_corr_v2.csv` | 센서 중요도(재적합 절제·채널 교체), 위치×진동 미탐, 진동–전류 결합, 오경보 사건 모음, 근접 오경보 |
| `uncertainty_v2.csv`, `workload_v2.csv`, `alert_levels_v2.csv`, `alert_levels_injection_v2.csv`, `alert_budget_design_v2.csv` | 블록 부트스트랩, 업무량(명목·관측·이항·보정 사후 95%), 단계별 업무량·지연(대회·시간순·주입), 알림 예산 역산 |
| `probability_eval_v2.csv`, `probability_reliability_v2.csv`, `probability_conversion_v2.csv`, `label_free_alert_probability_v2.csv` | 확률 교차 평가·신뢰도·문턱 확률·라벨 없는 환산 |
| `queue_mixed_ranks_v2.csv`, `queue_injection_ranks_v2.csv`, `queue_key_selection_v2.csv`, `quality_windows_v2.csv`, `monitor_gain_v2.csv`, `expected_effect_v2.csv`, `decision_table_v2.csv` | 대기열 순위, 품질 의심 시간창, 감시 규칙 모의, 기대효과·손익분기(가정), 판단표 |
| `fig_*_v2.png` | 위치별 재현율, 첫 경보, 미탐 사례, 센서 중요도, 결합, 오경보 사례, 확률 신뢰도 |
| `expected/` | 동결 기대값: 결과 CSV 37개, manifest·audit·요약, 행 단위 예측 요약(`predictions_digest.json`) |
| `console/` | 콘솔 화면 캡처와 해시(`tools/capture_console.py`) |

행 단위 예측(`predictions_*`, `test_predictions_*`)과 저장 모델(`artifacts/`)은 Git에 넣지 않는다. 실행하면 생기고, 해시는 manifest와 `expected/predictions_digest.json`으로 대조한다.

## 검증

| 명령 | 확인하는 것 |
|---|---|
| `python yejun/press_guard/audit.py` | 실행 검증 16개. 코드·모델·입력 해시, 입력 묶음 1·7·128행과 전체 추론 동일, 독립 집계, p값 순위 규칙, 알림 정확성, 이상 21구간 탐지, 날짜 이동·라벨 변경 불변 |
| `python yejun/press_guard/verify.py` | 동결 기대값과 비교한다. 결과 CSV(수치 1e-9), 실행 기록, 행 단위 예측 요약을 본다. 요약은 SHA-256이 같거나, 경보·알림 열이 정확히 같고 실수 열이 소수 6자리까지 같아야 한다. `--freeze`는 audit를 통과한 실행만 동결한다 |
| `python -m pytest -q yejun/press_guard` | 모델·스트림·서버·분석·재보정·감시·모의 운용·이식성(인코딩·resource·CP949) 시험 |
| `node yejun/press_guard/test_web.cjs` | 콘솔 그래프·단계 표시·모의 운용·결과 양식 회귀 |
| `bash yejun/press_guard/tools/clean_repro.sh` | git 클론(또는 git 없는 사본)에 원본만 복사해 `reproduce.py`를 실행한다 |
| `python yejun/press_guard/tools/package_manifest.py` | 최종 패키지 파일 목록·SHA-256·블라인드 검사(절대 경로·필수 파일). ZIP은 만들지 않는다 |

실행 환경은 [requirements.txt](requirements.txt)(torch 없음), [requirements-lock.txt](requirements-lock.txt)(전이 의존성 고정, 파이썬 3.12.8 새 가상환경에서 확인), [environment.yml](environment.yml)이다. BLAS·OpenMP 스레드는 코드에서 1개로 고정한다(`PRESS_THREADS`로 변경). 결과는 스레드 수와 무관하다(8스레드에서도 예측 파일이 비트 단위로 같았다). manifest에 BLAS 이름·판·스레드 수를 남긴다.

## 한계

- **독립 검증이 없다.** 이상 21구간은 한 날 3분의 연속 기록이고, 모델 설계에 이미 본 자료다. 정상(화요일 심야)과 이상(일요일 오전)은 날짜·시간대·저장 형식이 겹친다. 형식은 제거했지만 신호 차이가 고장 때문인지 운전 조건 때문인지는 분리할 수 없다.
- **현장 값을 모른다.** 이상 확률·알림 예산·기대효과는 사전 비율, 현장 알림률, 비용 가정에 조건부다.
- **2단계 규칙은 사후에 정했다.** 대회 오경보가 모두 경보 1행이라는 관찰을 본 뒤 정했다. 약한 진동형 고장은 2단계로 늦게 가거나 1단계에만 남는다(E1식 진동 잡음 2σ, 2초 안 2단계 38~79%).
- **10 Hz 순시값이다.** 베어링·캐비테이션처럼 수십 Hz 이상인 특징은 식별하지 못한다. 고장 모드는 후보 목록이다.
- **약한 조건이 있다.** 기록 시작부터 있는 전류 오프셋, 전류 배율 변화, 느린 누설에는 약하다(보완 실험 E1·E2).
