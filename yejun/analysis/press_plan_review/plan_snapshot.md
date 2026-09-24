# ③ 프레스 유압펌프 이상 탐지 — 수상 수준 완성도 계획

## Context

과제는 ③ "진동·전류 시계열 기반 프레스 유압펌프 이상 조기탐지 및 오경보 분석"으로 확정됐다. 이 계획은 **일정을 고려하지 않고, 심사위원이 수상작으로 인정할 완성도**에 도달하기 위해 무엇을 어떤 순서로 만들지 정한다.

### 결정 사항 (예준 확인, 2026-09-24)
- 최종 제출 코드 패키지는 **`yejun/press_submission/`에 우리가 구축**한다. 준용이 코드는 읽기 전용으로 가져다 쓴다(사본 + 출처·커밋·sha256 기록).
- **보고서(hwpx 6장)·발표자료는 준용이가 작성**한다. 우리는 장별 근거 자료(표·그림·수치·문장 초안)를 만들어 커밋으로 넘긴다.
- `claude/`는 절대 수정하지 않는다. 준용이 문서·코드의 수정 필요 사항은 요청 목록으로 전달한다.
- Codex↔Claude Code 인수인계는 커밋 메시지(`한 일/결과/다음/도구`)로 한다. 아래 작업 항목 하나 = 커밋 하나.

### 준용이가 9/23에 한 일 (claude/, 그 뒤 변경 없음)
- `05_requantize_audit.py` 형식 누수 감사(진동 소수 6 vs 8자리, 전류 1.1920929 격자 → 형식만으로 F1 0.972/1.000; 양자화를 맞추면 붕괴, 크기 모델은 불변), `06_alias_frequency_audit.py` 전류 단일 사인 적합(정상 530구간 R² 0.993~1.000, 이상 17구간 0.291~0.783), `07_policy_with_sine.py` 예준 평가 틀에 사인 점수·결합 모델 추가.
- `pipeline/run_all.py` 한 명령 파이프라인(약 40초): max-z·5NN·RMS5·IF·MLP-AE·사인·결합 7모델 × 2분할 × 행/구간 보정 × 1·3·5% 비교표, 라벨 없는 창 선택 규칙, 구간 단위 conformal p값, 예측 파일, 영향요인·FN/FP 조건, 진단 문서, 그림 4장, 자동 검사.
- 헤드라인: 결합 모델(max-z + 전류 사인 1−R²) 기록구간 1% 예산에서 **21/21 탐지, 정상 알림 0/120·1/180**(규칙 w=5/10, F1 0.759/0.894; 탐색값 w=8은 F1 0.915). max-z 단독 18/21(진동이 정상 수준인 이상 구간 3·19·20은 전류 파형으로만 잡힘).
- 노트: `프레스_결과요약_보고서용.md`(장별 수치), `프레스_실행계획_2026-09-23.md`, `프레스_분석방향_아이디어.md`(수상작·문헌 조사, 경쟁 팀은 LSTM-AE/IF + 점 F1≈1.0 예상).

### 심사 구조 (공식 문서 확인)
서면평가 6항목: 진단 15 · 모델 40 · 영향요인/오류 15 · 현장활용 10 · 창의성 10 · 재현성 10. 심사위원 5인, 최고·최저 제외 평균, 동점은 정성 합계 → 정량. 상위 8팀 → 발표평가(기준 미공개, 팀원 전원 참석) → 4팀만 수상. 부문 강조점 "창의성, 분석 성능, 데이터 활용도". 제출물: 보고서 PDF(양식 6장 = 배점 항목, 분량 제한 없음), 소스코드 zip(코드·requirements·**학습용 데이터**·README·**테스트 예측 파일**), 발표자료 PPT+PDF, 설문 캡처. 블라인드(소속·로고 금지). 외부 데이터는 출처 명시 시 허용. **공식 테스트셋 없음** → 예측 파일 형식 자체 정의(문의 초안 `claude/notes/문의메일_초안.md` 미발송).

### 우리 검토가 찾은 문제 (`yejun/analysis/press_merge_review/`, 재현은 1e-9 오차로 성공)
- **문제 1 창 선택·점수 상한**: `tail_logp`가 학습 최댓값 이상을 전부 `log10(n+1)`로 묶어 문턱이 상한에 걸리면 사인 성분이 영원히 경보를 못 낸다("죽은 성분"). 양자화를 맞춘 데이터에서 창 재선택 시 18/21·F1 0.44로 붕괴. w=8 고정이면 모든 변환에서 21/21·F1 0.915~0.921 → 특징은 건강, 결합·선택 절차가 문제. 창 선택은 동률(5·6·8 모두 0경보)을 "작은 값"으로 끊고, 후보 집합 {5..12}는 라벨 실험(15·20 실패)을 본 뒤 정해짐.
- **문제 2 경보 기준 혼동**: 순서통계 문턱(cutoff, 보정 초과 1개 허용 → 초과확률 2/121)과 conformal p≤α는 다른 기준. n_cal=120이면 최소 p=1/121. w=8에서 두 기준이 337행 불일치(21/21 vs 18/21).
- **문제 3 보정셋 재사용**: `select_w`가 최종 보정셋으로 후보별 문턱을 만들고 그 w를 같은 보정셋으로 다시 보정 → split conformal 전제 위반.
- **문제 4 경로·캐시**: 05 캐시가 입력 해시 확인 없이 재사용, `--root` 미전달, 사용자 지정 `--out`에서 진단 문단 누락.
- **표현·정리**: "기동 직후 1초"(기록구간 첫 w−1 관측이 정확), 앨리어싱 60Hz는 가설(60/10은 0Hz로 접혀야 하고 0.6Hz는 실간격 0.101s 필요), `predictions_test.csv`에 센서 원값 3열(Git에 원본 유출), 그림 y축(롤링 5점 R²)과 본문(구간 R²) 불일치, "0.600±0.002Hz" 재현 불가(530구간 중 411이 정확히 0.600, 범위 0.365~0.630), N3(AI0 자기상관) 코드 없음, 구간 정의 3종(599/600), 05 감사가 결합 모델 미포함, 현장활용 장에 정량표 없음, `current_amp`에 DC 오프셋(이상 전류 평균 57.3)이 섞임.
- **날짜 교락**: 정상 07-12 하루, 이상 07-17 하루. 소수 자릿수·전류 격자·타임스탬프 지터(SD 0.7ms vs 0)·DC 오프셋까지 다르므로 **두 파일은 수집·저장 경로가 달랐다**. 사인 붕괴가 펌프 고장인지 수집 조건인지 이 데이터로는 완전히 분리할 수 없다 → 진단 장에서 정면으로 다룬다.

### 한 문장 스토리와 2단 방어
"저장 형식·수집 조건 차이라는 지름길을 먼저 찾아 제거하고, 정상 데이터만으로 설계·보정한 **진동 크기 + 전류 파형(물리 특징)** 결합 경보가 오경보 예산(실효 α 명시) 안에서 이상 21구간을 관측 시작 1초 안에 잡으며, 놓치는 조건·헛울리는 조건·점검 업무량을 숫자로 공개한다."
2단 방어: 사인 신호가 수집 설정 차이라 해도 진동만으로 18/21·F1 0.46은 남는다. 사인은 "+3구간·F1 0.92"의 보조 신호라고 명시한다.

---

## 산출물 구조 (`yejun/press_submission/`)

```
yejun/press_submission/
  README.md                 # 실행법·환경·데이터 배치·기대 실행시간·출력 목록·예측 파일 규격 (= 제출 zip README)
  PROVENANCE.md             # 가져온 파일(원본 경로·커밋 cee2267·sha256)과 변경점
  requirements.txt          # == 고정: numpy 1.26.4, pandas 2.3.3, scikit-learn 1.8.0, scipy 1.13.1, matplotlib 3.9.2, torch 2.5.1 (+ environment.yml, Python 3.12)
  run_all.py                # 한 명령: 전처리→학습→추론→표·그림·예측 파일→검사→manifest
  predict.py                # TimeStamp + 센서 3열 CSV만 받아 점수·p값·경보 출력 (심사위원용 추론 진입점)
  verify.py                 # outputs/expected/ 대비 허용오차 비교 (주 모델 1e-8, IF/AE 1e-6, LSTM 별도)
  press/
    data.py                 # 로드·sha256 검증·기록구간(단일 정의)·시간순 분할·matched 양자화·current_amp(평균 제거)
    scores.py               # max-z, 5NN, RMS5, IF, MLP-AE, sine(w), 결합(상한 없는 연속 꼬리 확장)
    lstm_ae.py              # 가이드북 LSTM-AE 재구현 (PyTorch), 2 프로토콜, 점수 캐시 + 해시
    select_w.py             # 물리 규칙(정상 학습 앨리어스 반주기) + 학습 내부 A/B/C 안정성, 보정셋 접근 금지 assert
    calibrate.py            # cutoff(순서통계)·conformal(n+1 보정, α_eff) 두 기준을 명시적 열로
    evaluate.py             # 2분할 × 행/구간 × 1·3·5% × 기준 2종, 정상 구간 부트스트랩 CI, 혼동행렬·P/R/F1 병기
    analysis.py             # 영향요인·FN/FP 조건(분모 포함)·2×2 상호작용·그림
    field.py                # 운영점·부담표, k-of-n 지속성, 부하 정규화 점수 후보, 판단표
    diagnosis.py            # 수집 경로 차이 감사(N3 포함)·구간 구조·파형·검증전략 그림·diagnosis.md
    robustness.py           # raw/matched/coarse 전 절차 재실행, 죽은 성분 검사, 라벨 우회 검사 4종
    numbers.py              # 헤드라인 수치 전부를 numbers.json으로 (정렬 검사 입력)
  vendor/press_policy_audit.py   # 예준 평가 헬퍼 (yejun/analysis/press_welding_review/ 사본, sha256 assert)
  tests/                    # segments 600/21, conformal MC, 죽은 성분, 셔플 불변
  outputs/                  # run_all 산출 (원값 없는 CSV/MD/PNG만 커밋), outputs/expected/manifest.json
  evidence/보고서_근거_장별.md    # 준용이 보고서용: 장별 표·그림·수치·문장 초안 + 출처 파일
  evidence/요청사항_준용.md       # 준용이 노트·코드 수정 요청 목록
  tools/check_alignment.py  # 보고서(hwpx→txt)·슬라이드(pptx→txt)·README의 수치가 numbers.json과 일치하는지
  data/                     # (git 제외) data/3_소성가공_예지보전/{press_data_normal,outlier_data}.csv
```

**재사용할 기존 코드** (읽기 전용 → 사본):
- 예준 `yejun/analysis/press_welding_review/press_policy_audit.py`: `blocks, rms5, cutoff_at_budget, segment_max, summarize_records, SPLITS, BUDGETS` 그대로.
- 준용 `claude/code/press/pipeline/scores.py`: `sine_score, _hats, _window_index, _ae_windows, Scorer` (tail_logp만 교체). `evaluate.py`: `conformal_p, evaluate` 루프(criterion 열 추가). `analysis.py`: `segment_features, run`. `diagnosis.py`: `_decimals, _sine_fit`. `data.py`: `load, inputs_only, split_sets`.
- 준용 `05_requantize_audit.py`의 `quantize()`, `06_alias_frequency_audit.py`의 구간별 사인 적합·`early_check`.
- 우리 `yejun/analysis/press_merge_review/review_checks.py`: `compare_csvs`, 포화 탐침, 경로 검사 → `robustness.py`·`verify.py`의 출발점.

---

## P0. 신뢰성 수정 (결과 확정 전 필수)

| # | 문제 | 수정 설계 | 수용 기준 |
|---|---|---|---|
| P0-1 | 점수 상한 → 죽은 성분 | `tail_logp`를 학습 최댓값 너머로 **연속 단조 확장**: `v ≤ max`면 ECDF 꼬리 −log10p, `v > max`면 `log10(n+1) + log10(1 + (v − max)/σ_tail)`, `σ_tail = max − q99`(정상 학습). 대안 POT-GPD 꼬리. 결합은 `fmax` 유지, "고정 점수 함수이며 확률 아님" 유지. 보정 단계에 **가동 검사**(각 성분이 문턱을 넘길 수 있는지)를 `checks.json`에 기록 | 모든 (변환 3 × 분할 2 × w 5..12)에서 "성분 상한 ≤ 문턱" 0건. w 고정 시 6개 (변환×분할) 셀 모두 21/21, 정상 알림 raw 대비 ±1, F1 변화 ≤0.02 — 아니면 표로 그대로 보고 |
| P0-2 | 경보 기준 혼동 | 모든 표·예측 파일에 `criterion ∈ {cutoff, conformal}` 열. conformal: `p = (1+#{cal ≥ s})/(n+1)`, 허용 초과 `a = ⌊α(n+1)⌋ − 1`, **α_eff = (a+1)/(n+1) 병기** (n=120: α 1/3/5% → conformal 0.83/2.48/4.96%, cutoff 1.65/3.31/5.79%). α=1%는 "보정 최댓값 120개 전부 초과" 규칙임을 명시. 헤드라인은 conformal + α_eff, cutoff는 같은 표에 | `tests/`: 연속 점수 MC 10,000회에서 초과율 = α_eff ± MC 오차; `conformal_unit_test.csv`에 모델별 두 기준 차이 행·구간 수. "cutoff F1"과 "conformal 보장"을 한 문장에 쓰지 않음 |
| P0-3 | w 선택이 라벨·보정셋 오염 | **주 규칙 = 물리 규칙**: 정상 *학습* 구간(길이≥10)의 사인 적합 주파수 중앙값 f̂로 `w = round(0.5 / (f̂·Δt))` (반 주기 = 진폭·위상·주파수 3모수 적합의 최소 창; f̂=0.600Hz → 8.33 → **8**). 부록: 학습 내부 시간순 A/B/C 3중 분할(A 적합, B 문턱, C 경보율·문턱 여유)로 후보 5..12 안정성 + 민감도표. 보정 120구간은 `calibrate()`에서만 접근(assert). "w=8은 탐색에서 먼저 봤고 이후 라벨 없는 규칙이 같은 값을 냄"을 보고서에 명시 | `w_selection.csv`에 f̂·후보별 C-경보율·margin·최종 w·근거. 두 분할에서 같은 w → 분할 간 직접 비교. 민감도 5~10 전부 21/21, ≥12 하락 원인(구간 길이) 문장 유지 |
| P0-4 | 형식 지름길 | **기본 전처리 = matched 양자화**(진동 1e-4, 전류 1.1920929 격자로 두 파일 모두) → 형식 정보 제거 상태에서 모든 모델 학습·보정·평가. raw·coarse는 강건성 표 | 형식 규칙 F1 0.972/1.000 → 정규화 후 ≤0.1. 최종 절차(선택 포함) 탐지 구간 수가 3변환에서 동일(다르면 그대로 보고) |
| P0-5 | 경로·캐시·원값 | `--root`, `--out` 하나로 전 단계. 캐시 키 = 입력 sha256 + 변환 설정. `predictions_test.csv`에 센서 원값 제외(zip 동봉본은 학습용 데이터를 포함하므로 원값 허용) | 임의 `--out`에서 전 산출 생성. Git 추적 파일에 원값 열 없음 |
| P0-6 | 구간 정의·부하 지표 | 기록구간 = `|Δt−0.1|>1e-6` 분할(600/21) 하나만(`data.segments()`), 중복 타임스탬프 1건 처리 명시. `current_amp` = 평균 제거 RMS 또는 사인 진폭 | 진단 문서 구간 수 = 평가표 구간 수; 06 `early_check` 경계 오차 해소 |

---

## P1. 배점별 보강 (근거 파일 = 준용이 보고서 재료)

### 1장 진단 15 — `outputs/diagnosis.md`, `acquisition_audit.csv`, 그림 3장
- **수집 경로 차이 감사표**(정상/이상): 저장 자릿수 6 vs 8, 전류 격자 0.2% vs 100%, Δt 지터 SD 0.7ms vs 0, 전류 평균 1.45 vs 57.3(DC 오프셋), 앨리어스 주파수(중앙값·IQR·0.600 정확 일치 411/530), AI0 lag-1 자기상관(N3 코드 신규), 중복 타임스탬프.
- **"라벨이 실제로 부호화하는 것"** 절: `Equipment_state` = 파일 = 날짜 = 수집 경로. 분리 불가 명시 + 반증 조건("정상일 자료를 이상일과 같은 경로로 한 번 더 수집하면 판별 가능").
- 생산단위 설명: 기록구간 = 기록 청크(프레스 스트로크·기동 아님), 77분 중 33분만 기록, 구간 길이 분포, 이상 21구간 ≠ 고장 21회. 전류가 60Hz 순시값(RMS 아님)이라 사인 적합이 되는 이유; 60Hz 앨리어싱은 "가설", 0.6Hz는 정상 학습 추정값.
- 형식 규칙 F1 → 정규화 후 붕괴 (지름길 제거의 증거) + 결정: matched 양자화를 모든 모델의 전처리로 채택.
- 검증 전략 그림: 정상만 학습(A/B/C) → 보정 120구간 → 평가; 이상 600행은 평가 전용·두 분할 공유.

### 2장 모델 40 — `model_comparison.csv/.md`, `bootstrap_ci.csv`, `ablation.csv`, `fig_reliability.png`
- 베이스라인: **가이드북 LSTM-AE 충실 재현**(abs+MinMax, seq 20, LSTM 64-32-32-64, Adam 1e-3) **2 프로토콜** — (가) 가이드 그대로(공백 가로지르는 창, 이상 포함 검증셋 P=R 문턱 → F1 0.748 재현 시도), (나) 우리 프로토콜(구간 내 창, 정상 보정만). 점수 CSV 캐시 + 해시, `--retrain-lstm` 옵션. 그 외 max-z·5NN·RMS5·IF·MLP-AE·사인 단독·**결합(최종)** × 2분할 × 행/구간 × 1·3·5% × 기준 2종. 혼동행렬·P/R/F1도 같은 표에 병기.
- 정상 평가 구간(120/180) 블록 부트스트랩 95% CI: 정상 알림 수·비율. 이상은 21구간 **카운트로만**(하루치라 비율 일반화 금지).
- **p값 신뢰도 곡선**: 명목 α 0.5~10% vs 정상 평가 구간 실현 오경보율.
- 최종 선정 근거: 정상 데이터만으로 결정된 w·점수 함수, 상한 없음, 3변환 강건, 두 분할 최악 경우 기준.
- "이상 확률" 요구 대응: 출력 = **정상 이탈 p값(오경보 확률)**, `anomaly_score = 1−p`. 사후확률은 유병률·이상 표본 없이 추정 불가함을 설명(Platt 금지).

### 3장 영향요인·오류 15 — `influence.csv`, `error_conditions.csv`, 그림 2장
- 단변량 AUROC + 성분 기여(경보 사유 max-z/사인/둘 다), 센서별 발화 비율.
- **분모 포함 조건표**: 구간 내 위치(첫 w−1행 / 이후), 구간 길이 구간(≤4, 5–9, 10–29, ≥30), 부하 수준(정상 학습 전류 진폭 4분위), 진동 수준. "10번째 관측부터 재현율 100%"류 문장은 통제 후 성립 확인.
- **진동 수준 × 파형 R² 2×2 표**(이상 21구간·정상 평가 구간 배치): "진동 정상·파형 붕괴" 칸의 3구간이 사인 전용 탐지.
- FP는 1·3·5% 예산까지: 고부하(진폭 211~250) 집중 여부·max-z 발화 비율, 같은 부하 수준 비알림 구간과 대조(단일 구간 근거임을 명시).
- 그림을 **구간 단위 R²** 기준으로 다시 그려 본문 수치와 일치. "잘 작동하는 조건/실패 조건" 문단을 표에서 직접 도출.

### 4장 현장활용 10 — `workload.csv`, `persistence.csv`, `load_norm.csv`, 판단표
- **부담표**: 예산 × 기준별 정상 알림 구간 수 → 기록 시간당·가동 시간당 알림 수(가정 명시), 탐지 구간, 첫 경보 지연 중앙값/p90(미탐 제외 표기), 알림당 점검 항목.
- **k-of-n 지속성 규칙**(k=1,2,3)을 *보정 단계부터* 적용: 탐지/오경보/지연 트레이드오프(길이 3~4 구간 손실 포함).
- **부하 정규화 점수** 후보(정상 학습에서 진동 std ~ 전류 진폭 회귀 잔차) = 평가된 개선 후보. 개선 없으면 부정 결과로 보고. 층별 문턱은 n≈40이라 α_eff ≥ 2.4%로 불가함을 명시.
- 작업자 판단표: 관측(사유·p값·부하·지속) → 판단 → 확인 대상(상부 진동 → 펌프 상부·커플링, 파형 → 모터·전원; 가설 표기) → 대응 시간·확인 업무량.

### 5장 창의성 10 — `ablation.csv`
- 요소별 "빼면 무엇이 바뀌나" 한 줄: 사인 제거 → 18/21·F1 0.46; max-z 제거 → 사인 단독 18/21(다른 구간 미탐); 연속 꼬리 확장 제거 → 재양자화 시 18/21; 구간 보정 제거 → 같은 명목 1%에서 정상 알림 4~5/120; 형식 정규화 → 규칙 F1 1.0→0, 모델 불변; 가이드 창 방식 → LSTM-AE 수치. 각 행을 2·3장 표 번호로 연결.

### 6장 재현성 10
- `requirements.txt(==)` + `environment.yml`, Python 버전, `OMP_NUM_THREADS=1`·torch 시드, 입력·출력 sha256 `manifest.json`, `verify.py`, `predict.py`(TimeStamp+센서 3열만), 예측 파일 규격, 기대 실행시간·메모리(CPU만), 깨끗한 클론 재현 절차(다른 OS 1대 포함, autocrlf 재발 확인).

---

## 작업 배분과 순서 (항목 = 커밋 = 인수인계 단위)

A = 우리(yejun/), B = 준용 요청, C = 팀 결정.

| ID | 작업 | 담당 | 산출 | 의존 |
|---|---|---|---|---|
| W0 | 미커밋 `press_merge_review/` 커밋(경로 이미 yejun/으로 수정됨) + 요청 노트 초안 | A | `evidence/요청사항_준용.md` | — |
| W1 | 패키지 뼈대: 로드·해시·`segments()` 통일·분할·matched 양자화·`current_amp` 수정·vendor 사본·PROVENANCE·requirements 고정·`data/` gitignore·tests | A | `press/data.py`, `vendor/`, `tests/test_segments.py` | — |
| W2 | P0-1 연속 꼬리 확장 + 가동 검사 | A | `press/scores.py` | W1 |
| W3 | P0-2 cutoff·conformal(n+1, α_eff) 분리, MC 단위테스트, 예측 파일 규격(원값 없음) | A | `press/calibrate.py`, `evaluate.py`, `predictions_test.csv` | W2 |
| W4 | P0-3 물리 w 규칙 + A/B/C 안정성 + 민감도, 보정셋 접근 assert | A | `press/select_w.py`, `w_selection.csv` | W2 |
| W5 | 강건성: raw/matched/coarse 전 절차, 죽은 성분 검사, 라벨 우회 검사 4종 | A | `press/robustness.py`, `robustness.csv` | W3, W4 |
| W6 | 1장 진단: 수집 경로 차이 감사(N3 포함), 앨리어싱 통계 재현, diagnosis.md 자동 생성 | A | `press/diagnosis.py`, `acquisition_audit.csv` | W1 |
| W7 | LSTM-AE 가이드북 베이스라인 2 프로토콜 + 캐시 | A | `press/lstm_ae.py`, `lstm_ae_scores.csv.gz` | W1 |
| W8 | 절제표·부트스트랩·p값 신뢰도 곡선·혼동행렬 병기 | A | `ablation.csv`, `bootstrap_ci.csv`, `fig_reliability.png` | W5, W7 |
| W9 | 3장: 분모 포함 FN/FP 조건표, 2×2 상호작용, 그림 수정 | A | `error_conditions.csv`, `fig_*` | W5 |
| W10 | 4장: 부담표, k-of-n, 부하 정규화 후보, 판단표 | A | `workload.csv`, `persistence.csv`, `load_norm.csv` | W5 |
| W11 | 6장: `run_all.py` 통합, `predict.py`, `verify.py`, manifest, `numbers.json`, README, 깨끗한 클론 재현 | A | 패키지 완성 | W6–W10 |
| W12 | 근거 문서 작성 → 준용이에게 커밋으로 전달 | A | `evidence/보고서_근거_장별.md` | W11 |
| W13 | 문의 메일(프레스용 재작성: 테스트셋 부재 시 예측 파일 형식·자체 평가셋 허용 여부) 발송 여부 결정 | C(예준) | 발송 기록 | — |
| W14 | 보고서·발표자료 작성 (근거 문서 기반, 수치 출처 = `yejun/press_submission/outputs/`) | B | claude/ | W12 |
| W15 | 최종 조립: zip(학습용 데이터 포함), `check_alignment.py`, 블라인드 스크럽, 최종 재현 | A+C | 제출물 | W14 |

**준용이 요청 노트 골자**(W0, 이후 갱신): ① 보고서 수치 출처를 `yejun/press_submission/outputs/`와 `evidence/보고서_근거_장별.md`로 통일(C); ② `프레스_결과요약_보고서용.md` :41 "같은 구간을 고른다"(w=8 불성립), :58 "기동 직후 1초", :64 "오경보 상한", :65 "5~10 전부 21/21" 수정; ③ 앨리어싱 가설 표기, "0.600±0.002" 폐기, N3 코드 없는 주장 삭제, 그림 y축 정의; ④ `predictions_test.csv` 원값 6,697행 Git 추적 해제 + .gitignore; ⑤ `05`/`07` 기본 경로 `yejun/`; ⑥ `run_all.py:149–151` 캐시·`--root`, `diagnosis.py:77` (준용 파이프라인을 계속 참조할 경우만). 함수 단위 사양으로 적어 담당 교체 가능하게 둔다.

---

## 최종 산출물 조립

- **보고서 장 ↔ 근거 파일**: 1장 `acquisition_audit.csv`·`diagnosis.md`·`shortcut_rules.csv`·파형/길이/검증전략 그림 / 2장 `model_comparison`(criterion·α_eff 열)·`lstm_ae_*`·`ablation.csv`·`bootstrap_ci.csv`·`fig_reliability.png` / 3장 `error_conditions.csv`·2×2 표·위치별 재현율 그림 / 4장 `workload.csv`·`persistence.csv`·`load_norm.csv`·판단표 / 5장 절제표 재인용 / 6장 명령·환경·manifest·verify 결과 + 설문 캡처. 표지는 프로젝트명·팀명·요약만.
- **슬라이드 개요(14장)**: 문제·데이터 구조 → "한 줄로 F1 1.0"(누수) → 정규화 후 남는 것 → 전류 파형 물리 → 프로토콜(분할·예산·구간 단위) → 모델 비교 → 헤드라인 + 절제 → p값과 α_eff → 오류 조건 → 현장 운영표 → 한계와 반증 조건 → 재현 → 요약.
- **코드 zip**: README, requirements(==)·environment.yml, run_all.py, predict.py, verify.py, press/, vendor/(출처 표기), data/(학습용 CSV 2개 + sha256), outputs/expected/manifest.json, predictions/(분할별 예측 파일 + 규격), LSTM 캐시.
- **정렬 검사**: `numbers.json`(21/21, 0/120, 1/180, F1, α_eff, 18/21, LSTM F1, R² 범위, 알림/시간 등) → `tools/check_alignment.py`가 보고서·슬라이드·README에서 각 수치 존재·일치 검사; 예측 파일에서 다시 센 알림 구간 수 = 비교표.

## 검증 게이트
1. **G1 재현**: 새 클론 + `data/` 배치 + `pip install -r requirements.txt` + `python run_all.py --root . --out outputs` → `checks.json`·`manifest.json` 기대값 일치, `verify.py` 통과(다른 OS 1대 포함).
2. **G2 강건성**: raw/matched/coarse × 2분할, 선택 규칙 포함 재실행 → P0-1·P0-4 수용 기준.
3. **G3 라벨 우회 4종**: 구간 순서 셔플, 이상 파일 타임스탬프를 정상 날짜로 이동, 6자리 재직렬화, index 열 제거 → 주 모델 경보 동일. 추론 입력은 TimeStamp+센서 3열뿐.
4. **G4 conformal**: MC 단위테스트(α_eff 재현) + "α=1% = 보정 최댓값 전부 초과" assert. 죽은 성분 0건.
5. **G5 원값·블라인드**: Git 추적 파일에 센서 원값 없음; 보고서·슬라이드·README·코드 주석·경로 문자열에서 소속·이메일·GitHub 조직명·`/Users/<이름>` 0건; PDF/PPTX 작성자 메타데이터 스크럽.
6. **G6 정렬**: `check_alignment.py` 통과.
7. **G7 실행 기록**: 실행 시간·메모리(LSTM 포함, CPU만) README에 기재.

## 하지 말 것 / 위험
- RUL·"고장 전 N초" 주장(지연 = 관측 시작 후). "블라인드 테스트"·독립 검증·현장 실증·절감액 표현.
- 이상 라벨을 보고 w·문턱·후보 집합 고르기. 가장 좋은 분할·예산만 헤드라인으로.
- "conformal 1% 보장" 대신 α_eff. cutoff F1과 conformal 보장을 한 운영점으로 묶기 금지. 0/120을 "오경보율 0%"로 표현 금지.
- 60Hz 앨리어싱을 확인된 사실로, 21구간을 독립 고장 21회로 쓰기 금지. 재양자화 불변은 "형식 독립"이지 "진짜 고장 탐지" 증명이 아님. 가이드 F1 0.748과 비교 시 프로토콜 차이 병기.
- Git에 원본 데이터·원값 예측 파일 올리기 금지. `claude/` 수정 금지. 준용이 결과와 우리 결과 혼용 표기 금지(출처 파일 항상 명시). Platt 사후확률·경쟁 레포 언급 금지.

**회의적 심사위원 5문과 답**: ① "날짜를 배운 것 아닌가" → 수집 경로 차이표를 우리가 먼저 제시, 형식 정규화 후에도 결과 유지, 분리 불가 인정 + 반증 조건, 진동만으로도 18/21. ② "w=8은 라벨로 골랐나" → 물리 규칙(정상 학습 앨리어스 반주기)·민감도 5~12·탐색 이력 공개. ③ "1% 보장의 실체는" → α_eff 표(0.83% vs 1.65%), 두 기준 성능 병기, 실현 오경보율 옆에. ④ "딥러닝은 왜 안 썼나" → 가이드 LSTM-AE를 두 프로토콜로 같은 표에, 40초 재현·해석 가능성. ⑤ "현장에서 하루 몇 번 울리고 뭘 하나" → 부담표·판단표·k-of-n 트레이드오프.
