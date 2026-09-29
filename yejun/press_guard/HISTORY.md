# Press Guard 작업 기록

구현·검수 이력이다. 실행 설명은 [README.md](README.md), 운영 절차는 [OPERATIONS.md](OPERATIONS.md)에 있다. 아래 옛 기록의 명령·경로·수치는 당시 기준이다. 현재 값은 README와 outputs/를 따른다. 제출 묶음에는 넣지 않는다(tools/package_manifest.py).

## 2026-09-29 적대적 검수와 보완(1~7차)

앞선 채점을 모르는 적대적 검수(백지 채점 75.5·74.5, 중대 지적 8건)와 코덱스 재검수의 보완 순서를 따랐다. 근거와 처리표는 [적대적 검수](../analysis/press_rubric_review/cycle2/adversarial/README.md), [독립 검토](../analysis/press_rubric_review/cycle2/fix_review/), [처리 기록](../analysis/press_rubric_review/cycle2/README.md)에 있다.

- 1차(110afa2): 수집 시각 순서를 상태 기계로 바꿨다(TimeOrder: 튄 미래 행 건너뛰기, 이른 시각 보류 뒤 정상 간격 3행이면 새 기준). 오류 행과 8행 미만 무경보 조각은 사건을 닫지 않는다. 5.0 Hz 사인 기저를 계수 2로 계산한다. 다른 기기의 동결 비교를 판정 열 정확·실수 행별 상대 1e-6(순위 구간 1e-3)·모델 원소 대조로 바꿨다. 단위별 결과·확률 기준선 표를 더했다. 리눅스 arm64·x86-64(에뮬레이션)에서 21/21단계가 통과했다.
- 2차: 사건 추적의 되돌리기가 이미 나간 격상을 되돌리지 않게 하고, 되돌릴 대상을 튄 행으로 정했다. 튐 예외를 다음 표본(또는 60초 넘는 튐 뒤의 새 기록)으로 한정했다. 튄 행은 품질 시간창의 경계가 되지 않는다. 사인 투영 캐시를 고쳤다(1행 지연 p50 73.7 → 14.5 ms). 판단표는 계측(부착·영점·접지·수집 설정)을 먼저 보고 FM6을 후보에 넣는다. 대기열은 포화된 이상 확률 대신 권장 확인을 보인다. 재보정 도구에 운전 범위 점검 경고를 넣었다. 짧은 기록 경고 기준을 8행으로 올렸다. 전류 수준 치우침·수준 이동·표본화 흔들림 근거 표를 press_evidence에 더했다.
- 3차: 검토 5·6이 찾은 회귀를 고쳤다. 튐 예외를 튀기 전 기준에서 표본 1~3칸 뒤(끼어듦·대체)로 넓히고, '60초 넘는 튐' 조건 대신 기록 끝의 튐을 새 기준 채택 때 확인한다(부호 4). 같은 보정 규칙의 단일 성분 기준선을 선정 근거에 더했고, 문서 수치 13곳과 지도학습 README의 옛 값을 고쳤다.
- 4~6차(8b65130·873e4e1·a489001): 검토 7의 R7-01(오류 한 행이 기록을 잘라 사건을 나누거나 합침)을 고치려고 사건 단위를 기록과 따로 정했다(수집 공백 0.5초 → 도착 행 수로 설명되는 간격). 매번 새 검토자(검토 8·9·10)가 c7d8bba보다 나빠진 경우를 찾았다(옮겨진 행 묶음·짧은 공백 연속 운전, 공백에 낀 빈 시각·재전송 행, 순서 뒤바뀜·튐 + 흔들림, 건 대기열과 사건 경계의 불일치). 같은 기간에 2단계 교대 추정의 분할 민감도(8.4~9.1건), 시각 규칙 문서·경고 정정(보류 행 수·부호 4), 튐 모의 도구(tools/spike_scan.py)를 더했다.
- 7차: 사건 단위를 c7d8bba처럼 건 대기열과 같은 (기록구간, 50행 블록)으로 되돌리고 R7-01을 실측 빈도와 함께 알려진 한계로 적었다. 대기열과 행별 사건 열이 긴 연속 기록에서도 맞는지 보는 시험을 더했다.
- 주 지표(A F1 0.961938·B 0.970990, 정상 0/120·3/180, 이상 21/21)와 경보 규칙·문턱·분할은 그대로다.

## 2026-09-28 루브릭 사이클2 4회차 구현·독립 검수

3회차의 실제 결함과 누락을 보완했다. [처리 기록](../analysis/press_rubric_review/cycle2/README.md)과 [검수 원칙](../analysis/press_rubric_review/cycle2/round4/review_protocol.md)에 근거를 남긴다. 이전 평가의 경쟁팀 순위 단정은 후속 채점에서 사용하지 않는다.

- 원 전류의 누적 RMS·운전 상태를 일괄/스트림 예측, 건/사건, 콘솔에 연결했다. 경보 1행인 건 둘도 같은 사건이면 누적 2행째에 격상하고 `escalation_row`를 저장한다.
- 감시는 변경 기록·전류 수준 이동에 따라 네 갈래로 권고한다. 점검 요청 창은 결과가 정상 확인일 때만 재보정에 들어간다.
- 모의 화면의 미래 건·집계·근거·품질 조치 노출을 막고 매 재생 시점의 실제 순차 추론 결과와 대조했다. 역순 시각은 최대 수신 시각에 복귀할 때까지 판정을 보류하며 사건 연결과 품질 시간창에 음수 간격을 허용하지 않는다.
- 상태·시간 블록별 오경보, 50시드 미탐 주입, 다중 비교 보정, 같은 단위 상관차 부트스트랩을 추가했다. 2단계 주추정은 비중첩 폴드 1/7로 교대 4.2건(상한 15.4건)이며 사후 규칙·같은 날 추정이라는 조건을 유지한다.
- 확률의 행 비율과 알림 단위 비율, 표시 상한과 명목 FAR 시나리오를 구분했다. 등방 회귀의 0→양수 보간에서 LR 단조성이 깨지던 경계 결함을 수정했다.
- 예측 동결 요약은 모든 비실수 열, NaN/±inf 종류·위치를 보호하고 기대 요약 자체의 해시도 확인한다. 문서 링크 검사와 입력 전 분석 시험의 건너뜀 안내를 추가했다.
- A/B 저장 모델·확률 보정기 SHA-256 및 주 지표(F1 0.961938·0.970990, 정상 0/120·3/180, 이상 21/21)는 유지됐다.
- 최종 내부 검수는 96.4/100(15·38·14.5·9.5·9.4·10)이며 각 검수 범위의 잔여 P0·P1·P2는 없다. 자료 한계는 그대로 남긴다.
- 결과 동결 후 두 무결성 시험 2/2, 잠금 새 환경 재현 24/24, 목록 사본 재현 15/15를 통과했다. Python 시험은 중복 없이 224개 범위(v2 132·v1 49·분석 43)를 확인했다. 새 환경의 선택 의존성 skip은 Torch·UCI가 있는 호스트 시험으로 보완했다.
- 사용자의 후속 지시에 따라 전체 검증을 마친 상태를 Claude에 인계한다. 최종 수치·로그·파일 해시와 자료 한계는 위 처리 기록, 인계 요점은 이 변경의 커밋 본문에 남긴다.

## 2026-09-28 루브릭 사이클2 2회차 반영

2회차 점수는 합계 89.4/100이다(1회차 77.5). 처리 목록은 [cycle2/README.md](../analysis/press_rubric_review/cycle2/README.md)에 있다. press_guard 쪽 변경은 다음과 같다.
- 사건(incident) 층: 경보 단위가 이어지고 공백이 60초 이하면 한 사건이고, 사건마다 1·2단계 알림을 한 번씩 낸다(model.IncidentTracker, 일괄 = 스트림). 콘솔 대기열·결과 기록·simulate가 사건 단위다. 건은 case_uid(첫 경보 행)로 구분한다.
- 기록 경계 허용 오차: 0.1초 ± 20 ms(TIME_TOL_S). 수집 시각이 ±1·2 ms 흔들려도 결과가 같다. 평균 기록 길이 5행 미만이면 경고한다.
- 감시 조치 분기와 명령행(monitor.py), 비사후 2단계 업무량 추정, 운전 강도별 오류 표, 12행 오류 요약, 확률 설명 정정, 재현 목록 도구 개편.
- 주 지표·경보 규칙·분할은 그대로다.

## 2026-09-27 루브릭 사이클2 1회차 반영

평가관 6명(데이터·모델·오류·현장·창의성·재현성)의 1회차 보완 목록을 반영했다. 원문은 [analysis/press_rubric_review/cycle2/round1/](../analysis/press_rubric_review/cycle2/round1/)에 있다. 주 지표(A F1 0.961938·B 0.970990, 정상 0/120·3/180, 이상 21/21)와 경보 규칙은 바꾸지 않았다.

| 평가관 항목 | 반영 |
|---|---|
| 02 M1, 05 O2 이상 확률 | `probability.py`(등방 회귀 LR, 사전 비율, LR 상한 121), 예측 열 `likelihood_ratio`·`anomaly_probability`·`record_probability`, 21겹 교차 평가, 문턱 확률 불안정 공개, 라벨 없는 환산표 |
| 02 M2, 05 O5·O6 지도학습 비교 | `analysis/press_supervised` v2(같은 특징·conformal 문턱·21겹·가중 변형·주입 5회), 결론을 전이·라벨 불필요·재보정으로 정정 |
| 02 M3~M5, 05 O3, 03 E7 선정 근거 | `analysis/press_selection`(같은 특징 대안, 결합 규칙, 선정 근거표, 통합 비교표, v2 오경보 대응 시험과 그 주입 비용) |
| 03 E1~E5, E8 영향요인·오류 | 센서 중요도, 위치×진동 미탐(단측·양측 Fisher), 진동–전류 결합, 오경보 사건 모음, 근접 오경보, 조건표 CI·lift·Fisher와 위치 2 이상 층, FN·FP 집중 조건 요약(`error_condition_summary_v2.csv`, 파일:행), 그림 3장, 미탐 사례 제목에 진동 수준 |
| 03 E6 | 420~479·480~539 폴드는 B·A와 같은 모델이라 오경보 근거를 합산하지 않는다고 README에 적었다 |
| 04 U1 | 2단계 알림(건 안 경보 2행, 사후 결정 공개), 단계별 업무량·지연(대회·시간순 5창·주입), 알림 예산 역산, 콘솔 설명에 관측값·상한 |
| 04 U2 | 의심 생산 시간창(`suspect_*`, 먼 공백은 열림), 단계별 품질 조치, SPM 가정 환산 |
| 04 U3, U7 | OPERATIONS.md, 흐름도·구성도, 콘솔 재캡처, `simulate.py`(일괄 분석과 같은 알림) |
| 04 U4 | `expected_effect_v2.csv`(가정·출처 분리, 손익분기 배수, 두 운영 방식) |
| 04 U5 | 혼합 대기열 한 순위, 정렬 키 후보 4개 비교(주입 대 오경보), 계단형 고장 한계 |
| 04 U6, 05 O7 | `monitor.py`(Beta-Binomial 한도, 전류 수준 이동, 재보정 검토, 결과 기록 규칙), 수락 한도 Beta-Binomial, 검정력, 알림 예산, `--outcomes` |
| 04 U8 | 판단표 점검 항목·고장 모드 후보·가이드북 쪽수 |
| 05 O1 | 보정 조건부 사후 95% 업무량(A 44·B 92건/교대), 시간순 보정 곡선은 analysis/press_evidence |
| 01 D1~D7, 05 O4 | analysis/press_evidence 진단 보강(센서 관계, 진단 그림, 결정표, 생산단위 근거, 라벨 일관성, 관행 기준, 관측 가능성, 0.6 Hz 위상 시험, 고장 모드 대응표) |
| 06 R1 | 모든 텍스트 입출력 UTF-8, `resource` 조건부, CP949 콘솔 대응, 정적 검사 시험 |
| 06 R2 | `reproduce.py` 한 명령(빠른·전체), `clean_repro.sh`가 git 없는 사본에서도 동작, analyze 오류 메시지에 해결 명령 |
| 06 R3 | 테스트 예측 파일(분할별 1개, 정답 구분 열), `predict.py --split`(학습 없이 같은 SHA-256), 패키지 목록 도구(ZIP 보류) |
| 06 R4 | requirements(torch 제외)·requirements-lstm·requirements-lock·environment.yml, v1 `run_all.py`의 torch 지연 import(v1 재동결 39/39, 결과 동일), 파이썬 판 확인 |
| 06 R5, R9 | verify가 행 단위 예측 요약을 비교, v1 비교표는 v1 verify 허용오차로 대조 |
| 06 R11 | 스레드 고정(threadpoolctl), manifest에 BLAS 기록, 그림 글꼴(Windows·Linux), 주최 측 ZIP 입력 |

## 2026-09-25~26 기록(당시 README 원문)

정상 전류를 직전 두 관측으로 예측하는 AR(2) 잔차를 기존 크기·파형 점수에 결합한다. 첫 6관측부터 짧은 파형 창, 8관측부터 기존 창을 적용한다. 각 성분은 정상 학습 분포로 변환하고, 정상 보정 **기록구간 최대 점수**로 전체 결합 점수를 보정한다. 라벨·절대 날짜·파일명은 모델 입력이 아니다.

**모델·CSV 순차 추론·로컬 웹 콘솔 구현과 테스트 완료(2026-09-25 Claude).** `serve.py`의 `/api/overview`·`/api/analyze`에 `web/app.js`를 연결했다. 점검 대기열(근거 필터·CSV 내보내기), 선택 구간의 전류·성분 점수 그래프(호버 툴팁·문턱선·재생), 성능 검증·외부 검증 탭이 동작한다. API 계약 테스트 10개와 헤드리스 Chrome 렌더링(DOM 값·스크린샷)으로 확인했다. 사람이 브라우저에서 클릭·업로드·재생을 직접 확인한 기록은 아직 없다. 로컬 기록 재생용이며 설비 제어를 하지 않는다.

기존 `../press_submission/` v1 코드·산출물·동결 기대값은 바꾸지 않았다. 예준의 위임을 기록한 `21c6cab`에 따라 v2를 최종 모델로 디벨롭한다. 대회 보고서 작업은 시작하지 않았다.

## 확인한 수치

동일 데이터, 정상 학습/보정 분할, matched 전처리, conformal α=1%.

| 분할 | 모델 | F1 | 미탐 행/600 | 정상 알림 구간 | 이상 알림 구간 | 최대 첫 경보 지연 |
|---|---|---:|---:|---:|---:|---:|
| A | v1 | 0.910082 | 99 | 0/120 | 21/21 | 0.7초 |
| A | v2 | **0.961938** | **44** | 0/120 | 21/21 | **0.5초** |
| B | v1 | 0.920322 | 86 | 3/180 | 21/21 | 0.7초 |
| B | v2 | **0.970990** | **31** | 3/180 | 21/21 | **0.5초** |

미탐 감소율 A 55.6%, B 64.0%. 첫 경보 지연은 **기록 시작 기준**이며 실제 고장 발생 시각은 없다.

**A의 정상 알림 0/120은 유리한 조건에서 잰 값이다.** A의 정상 평가 구간(480~599구간, 01:00~01:17)은 정상 77분 중 가장 조용한 시간대다. v2 A 평가 구간 중 최대 점수가 보정 구간 중앙값을 넘는 것은 12/120이다(보정과 평가가 교환가능하면 약 60개, Mann–Whitney p=2.9e-11). B 평가 구간도 50/180으로 보정보다 조용하다. 오경보는 B의 3/180과 아래 시간순 비교의 420~479구간 2/60을 함께 본다. 분할은 바꾸지 않았다([루브릭 검수 R1](../analysis/press_rubric_review/README.md)). A/B는 같은 이상 21구간을 재사용하므로 독립 검증 두 건이 아니다. 이미 본 이상 자료를 사용한 탐색 결과이며 수상·현장 성능 보장의 근거가 아니다.

- 정상 평가 구간을 300~359, 360~419, 420~479, 480~539, 540~599로 나눈 시간순 5회 비교에서도 F1 0.961938~0.971819. 정상 알림은 각 0·0·2·0·0/60으로 v1과 동일. 이상 자료는 다시 같은 21구간이다.
- raw 정밀도 입력에서는 개선 유지. coarse B에서는 v2 정상 알림 **5/180**, v1 **4/180**으로 증가했다. 모든 입력 정밀도에서 오경보가 같다고 주장하면 안 된다.
- 단일 AR(2) 점수의 F1은 A 0.831548/B 0.839768. 다른 성분과의 결합 효과이며 단순히 새 모델 이름만 바꾼 결과가 아니다.

집계: [metrics.csv](outputs/metrics.csv), [rolling.csv](outputs/rolling.csv). 후보 전체 비교: [탐색 프로토콜](../analysis/press_advance/protocol.json), [전체 결과](../analysis/press_advance/metrics.csv). 추가 외부 자료: [UCI 검증](../analysis/press_external/README.md).

## 실행

저장소 루트에서 기존 `press_submission`의 고정 의존성이 설치된 Python을 사용한다. 현재 환경은 `/opt/anaconda3/bin/python`이다. 학습 상태·원본·행별 예측은 Git에 넣지 않는다.

```bash
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/train.py --rolling
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python -m pytest -q yejun/press_guard/test_guard.py
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/predict.py --model yejun/press_guard/artifacts/guard_A.json --input new.csv --out /tmp/press_predictions.csv --cases /tmp/press_cases.csv --chunk 128
```

CSV 필수 열: `TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current`. 기본 원본 위치는 v1 패키지와 같으며 `train.py --root`로 바꿀 수 있다. `predict.py`는 학습하지 않는다. 신규 설비의 정상 기준을 무검증으로 기존 모델에 적용하지 않는다.

## 최종 모델 패키지로서의 산출물 (2026-09-25 Claude)

예준 위임에 따라 v2를 최종 모델로 디벨롭한다. v1 패키지(`../press_submission/`)는 기준선·기준모델·LSTM 비교의 출처로 그대로 두고, 이 폴더에 분석·재현 도구를 갖춘다.

```bash
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
/opt/anaconda3/bin/python yejun/press_guard/train.py --rolling    # 학습·보정·저장·평가 (약 20초)
/opt/anaconda3/bin/python yejun/press_guard/analyze.py            # 통합 비교·오류 조건·불확실성·업무량·그림 (약 5초)
/opt/anaconda3/bin/python yejun/press_guard/audit.py              # 실행 검증 16개
/opt/anaconda3/bin/python yejun/press_guard/verify.py             # 동결 기대값 비교 (--freeze 로 동결)
PYTHON=/opt/anaconda3/bin/python bash yejun/press_guard/tools/clean_repro.sh # 커밋된 코드·기대값으로 새 클론 재현
```

| 산출물 | 내용 |
|---|---|
| `outputs/model_comparison_v2.csv` (+`.md`) | v1 패키지의 기준모델·결합·LSTM 결과와 v2 후보 고정 비교를 같은 입력(해시 확인)·분할·보정 구간에서 합친 표. `is_final_model`=early6_ar2 |
| `outputs/robustness_v2.csv` | matched로 적합·보정한 상태를 고정하고 평가 입력만 raw/coarse로 바꾼 v1·v2 결과(press_advance에서 추출). 웹 콘솔 성능 검증 탭에 조건표와 함께 표시 |
| `outputs/sensitivity_v2.csv` | 전처리(raw/matched/coarse)별로 **학습·보정·평가를 다시 실행**한 v1·v2 결과(PLAN §5.2 ①). matched 재적합 v2는 저장 모델 지표와 같음을 실행 중 확인 |
| `outputs/ablation_v2.csv` | matched 재적합에서 v2 성분 절제: 센서 크기·파형·예측 오차·초반 창 전환을 각각 제거한 결과 |
| `outputs/error_conditions_segments_v2.csv` | 구간 단위 조건표(길이·진동 산포·진폭·진동 수준·파형): 이상은 미탐 구간, 정상은 알림 구간. 진폭 조건에 신뢰 제한(길이<17) 구간 수 |
| `outputs/interaction_2x2_v2.csv` | 진동 수준(진동 두 센서 max\|z\| > 정상 학습 q95) × 전류 파형(사인 R² < 정상 학습 q05) 교차표, v1·v2 경보 각각 |
| `outputs/error_conditions_v2.csv` | v1·v2의 미탐(이상)·오경보(정상) 조건: 구간 내 위치, 구간 길이, 진동 산포·전류 진폭 4분위, 가장 강한 성분. 분모 포함 |
| `outputs/records_first_alarm_v2.csv` | 이상 21구간별 v1·v2 첫 경보 위치·미탐 행·첫 경보 근거 |
| `outputs/uncertainty_v2.csv` | 이동 블록 부트스트랩: 정상 알림 구간 수(블록 5·10·20), 이상 미탐 행·탐지 구간(블록 3·5). 관측값이 주 결과 |
| `outputs/workload_v2.csv` | α별 정상 첫 알림 수와 기록시간·경과시간 기준 알림률, 가동시간 시나리오 |
| `outputs/fig_recall_by_position_v2.png` | 위치별 이상 행 재현율 v1 vs v2 |
| `outputs/fig_first_alarm_v2.png` | 이상 21구간의 첫 경보 시점 v1 vs v2 |
| `outputs/fig_missed_example_v2.png` | v2 미탐이 가장 많은 구간의 전류·성분 점수 |
| `outputs/expected/` | `verify.py --freeze`로 동결한 결과 CSV 10개 + manifest/audit/summary |

행 단위 조건표의 사분위 경계는 정상 학습 구간 기준으로 하나만 쓰고(열 `q25·q50·q75·boundary_source`), 정상·이상 평가에 같은 경계를 적용한다. 진폭 조건에는 길이 17 미만 행 수(`unreliable_amp_rows`)를 함께 적는다. `amp_reliable`과 `unreliable_amp_*`는 **길이 ≥17 여부만** 뜻한다. 사인이 아닌 구간(파형 broken)의 `amp_proxy`는 √2×평균 제거 RMS일 뿐 사인 진폭이 아니다. 예를 들어 A 정상 평가의 broken 23구간 중 18구간이 길이 ≥17이고, 파형을 판정할 수 있는 이상 17구간은 모두 broken이다. 파형 조건별 구간 수는 [press_evidence/amplitude_reliability.csv](../analysis/press_evidence/amplitude_reliability.csv)에 따로 둔다. 조건표의 분모는 바꾸지 않았다.

재적합 민감도(α=1%): v2는 raw 재적합 A 미탐 43, coarse 재적합 B 정상 알림 4/180·미탐 34로 matched(3/180·31)보다 나쁘다. 정밀도가 거친 입력으로 학습·보정하면 B의 정상 알림이 한 구간 늘어난다. 절제(matched): 예측 오차 성분 제거 시 미탐 44→86·31→71, 파형 제거 시 133·112, 센서 크기 제거 시 이상 탐지 20/21, 초반 창 전환 제거 시 46·33. 각 성분이 결과를 바꾼다.

v2 예측 CSV에는 v1 계약(PLAN §7)과 대응하는 `model_id`(early6_ar2_A/B)·`protocol_version`·`criterion`·`is_scored`·`anomaly_score`(1−p) 열이 있다. v1의 `position_in_record`는 v2의 `position`, `alarm_reason`은 `reason`, `combined_score`는 `score`에 해당한다.

v2의 미탐 감소 55행 중 위치 2~6에서 A 49행·B 51행, 위치 10 이후에서 A 6행·B 4행이 개선됐다. 위치 0·1은 A 각각 13행(합계 26), B 각각 10행(합계 20) 미탐으로 v1·v2가 같다. 그 위치에는 센서 크기 성분만 있다. 개선이 위치 2~6에만 국한된다는 이전 서술과 A 23·23/B 20·20 표기는 오류였다.

주 비교 기준은 α=1%다. B에서 α를 3%로 높이면 v2 정상 알림은 3→5구간(경보 행 3→7), 미탐은 31행으로 같고 F1은 0.970990→0.967687로 낮아진다. α=3%에서의 모델 간 비교도 v1 4/180 대 v2 5/180으로 표기한다. α=5%는 v1 6/180 대 v2 7/180이다.

`contracts.py`는 학습·분석·검수·웹 코드, 필수 예측/집계/그림, 원본 비교표, 개별 검사 16개를 확인한다. 분석은 학습 실행에, audit는 코드·모델·분석 결과에 연결된다. 파일 변경·검사 누락·오래된 audit는 동결 근거로 사용할 수 없다. 기대값도 자체 해시와 검사 계약을 검증한다. 새 클론은 v1 주 모델 예측을 재생성하고, 기존 기준모델·LSTM 비교표는 커밋된 표의 해시를 확인해 재사용한다. LSTM 전체 재학습은 포함하지 않는다.

## 웹 콘솔·검증 도구

```bash
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/serve.py --port 8765   # http://127.0.0.1:8765
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/audit.py       # outputs/audit.json (실행 검증 16개)
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/benchmark.py   # outputs/benchmark.json (처리시간)
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python -m pytest -q yejun/press_guard/test_guard.py yejun/press_guard/test_serve.py yejun/press_guard/test_analyze.py yejun/press_guard/test_review_regressions.py yejun/press_guard/test_recalibrate.py
```

- `audit.py`: 실행 코드·저장 모델·v1 의존 코드·입력 해시가 manifest와 같은지, 입력 묶음 1·7·128행 순차 추론이 전체 추론과 같은지, 독립 집계·p값 순위 규칙·날짜 이동/라벨 불변을 실제 자료로 확인한다(16개). 구간당 알림이 경보 유무와 일치하는 정확성 검사와 이상 21구간 탐지 성능 회귀 검사는 이름을 나눠 판정한다. 웹 콘솔 '실행 검증' 목록이 이 파일을 읽는다.
- `benchmark.py`: 분할 A 평가 스트림 4,690행, CPU 한 스레드. 2026-09-26 재측정에서 1행 묶음 호출당 약 11 ms(p95 11.7 ms)로 수집 주기 0.1초보다 짧다. 128행 묶음 약 6,800행/초, 전체 일괄 0.28초. 기기 참고치다(평가관 04의 측정은 p95 19.9 ms).
- 웹 화면의 경보 문턱선은 `p ≤ α`와 동치인 점수(정상 보정 구간 최대 점수 순위)를 표시한다. 그래프 색은 계열 3개를 색각 이상 분리·대비 검사(dataviz 검증기)로 확인해 정했다.

## 현장 운영 규칙 (2026-09-26, 루브릭 검수 3단계)

[루브릭 검수](../analysis/press_rubric_review/README.md)의 R6·R7·R8·R15·R16·R17을 반영했다. 대회 자료의 지표·예측·오류 조건표·불확실성은 이전과 같다(저장 모델 바이트 동일, 기존 열 값 동일). 동결 기대값에서 바뀐 것은 `cases_*.csv`(열 5개 추가), `workload_v2.csv`(열 7개 추가), 새 `decision_table_v2.csv`다. pytest 54개(재보정 4개 포함), JS 4, audit 16/16, verify 20/20을 통과했다.

**알림·보정 단위(R7).** 대회 자료는 최대 50행(5초)의 수집 묶음(기록구간)이 1.5~16.6초 간격으로 들어온다. 보정·알림 단위를 "기록구간 안의 50행 블록"으로 정했다(`ALERT_UNIT_ROWS`, `alert_units`). 대회 자료에서는 블록이 곧 기록구간이다.
- 끊김 없는 연속 입력은 50행마다 새 블록이 되고, 블록의 첫 경보에 알린다.
- 바로 앞 블록도 경보였으면 이어지는 이상으로 보고 같은 건으로 묶는다.
- 이전에는 연속 입력 전체가 한 기록구간이 되어, 앞쪽 오경보 뒤의 이상이 새 알림 없이 묻혔다.
- 예측 CSV의 `alert_unit`은 블록 번호, `beyond_calibration_length`는 대회 보정 단위보다 긴 연속 입력인지를 보인다.
- 연속 입력의 블록은 초반 창이 비지 않아(기록 시작이 없음), 대회 보정값의 α는 근사다. 연속 수집 설비에서는 같은 방식의 정상 연속 자료로 재보정한다(R16).

**α의 뜻과 업무량(R8).** α는 시간 비율이 아니라 **보정·알림 단위(기록구간)당** 비율이다. 대회 정상 자료의 밀도는 경과 1시간에 약 447구간이다. [workload_v2.csv](outputs/workload_v2.csv)의 새 열로 교대 8시간(경과시간) 환산을 둔다.

| 분할 | α | 명목(보정 격자 ⌊α·121⌋/121) | 관측 | 관측 비율의 이항 95% 상한 |
|---|---:|---:|---:|---:|
| A | 1% | 약 30건 | 0건(0/120) | 약 88건 |
| B | 1% | 약 30건 | 약 60건(3/180) | 약 152건 |
| B | 3% | 약 89건 | 약 99건(5/180) | 약 206건 |
| B | 5% | 약 178건 | 약 139건(7/180) | 약 257건 |

A 평가 구간은 보정보다 조용한 시간대라 관측 0건은 유리한 조건의 값이다. 같은 날 간헐 수집 밀도를 가정한 환산이다. 연속 수집이면 블록 수(시간당 720개)로 다시 계산해야 한다. 웹 콘솔의 α 선택지에 "구간당"을 붙이고, 성능 탭에 업무량 표를 넣었다.

**조치 문구와 판단표(R6).** 크기 성분은 세 센서 중 최대 편차 센서를 따른다. 이전 규칙은 이를 보지 않아 전류만 튀어도 "진동·부하 확인"을 권했다.
- 전류 크기만 발화: "전류 크기·부하·계측 확인"
- 전류 크기와 파형·예측 오차가 함께 발화: "전류 크기·파형·계측 확인"
- 관측 자료의 크기 발화는 모두 진동 센서라 기존 결과는 같다.
- 판단표는 조치 규칙과 같은 원천(`model.DECISION_TABLE`)에서 [decision_table_v2.csv](outputs/decision_table_v2.csv)로 나온다. 대기열·CSV에는 `magnitude_sensors` 열이 붙는다.
- 확인 대상은 가설이며 정비 결과로 검증하지 않았다.

**대기열 우선순위(R15).** `priority_rank`는 이상 라벨 없이 정한 정렬 키다(근거 성분 수 → 경보 행 비율 → 최대 점수). 웹 대기열은 기본으로 이 순서를 쓰고, 시간순으로 바꿀 수 있다.
- α=1%에서는 보정 120구간으로 낼 수 있는 최소 p값(1/121)이 모든 경보에 같다. 그래서 상세 화면은 p값 대신 "문턱 대비 최대 점수"를 먼저 보인다.
- 사후 관찰(이상 라벨 사용, 성능 근거 아님): 정상+이상 혼합 자료에서 정상 오경보는 모든 분할·α에서 이상 21건보다 아래 순위였다(B α=1%에서 22~24위).
- 품질검사 우선순위와의 연결은 가공품·로트 자료가 없어 제안 수준이다.

**재보정 절차(R16).** [recalibrate.py](recalibrate.py)는 새 날짜·설비의 정상 CSV 하나로 학습·보정·수락 검사를 한다.

```bash
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/recalibrate.py --normal new_normal.csv --out site_model.json
```

1. 시간순으로 학습 / 보정(기본 120단위) / 수락 검사(기본 60단위)로 나눈다. α=1%에서 보정 단위가 99개 미만이면 중단한다.
2. 수락 검사 (a): 수락 구간의 알림 단위 수가 이항 95백분위 이하인가.
3. 수락 검사 (b): 30행 이상 단위에 전류 잡음 0.2σ·전류 오프셋 0.4×진폭·진동 잡음 4σ를 넣었을 때 2초 안 탐지율이 각각 90% 이상인가. 주입 세기는 보완 실험 E1의 결과를 보고 정한 운영 기준이다.
4. 통과할 때만 모델을 저장하고 보고서 JSON을 남긴다.

대회 정상 0~479구간을 새 자료로 가정하면 학습 300·보정 120·수락 60단위(정상 약 26.5분, 경과 약 61분)에서 알림 2/60(한도 2), 주입 3종 모두 36단위 100%로 통과했다. 같은 날 자료라 새 날짜의 성능을 보장하지 않는다.

**콘솔 문구(R17).** 성능 탭의 "v2의 향상은 위치 2~6에서 나온다"를 README의 정정(위치 2~6에서 A 49행·B 51행, 위치 10 이후 A 6행·B 4행)과 맞췄다.

## 검수 범위

2026-09-25 새 테스트 **13개 통과**. 저장·복원 동일, artifact 변조 차단, 미래 관측 불변, 라벨/날짜 변경 불변, 독립 순위 p값 계산 대조, 빈 입력·필수 열·α 오류, 구간당 첫 알림만 발행, 결측·중복·역순·혼합 시각 형식 경계, 1행/불규칙/128행/전체 청크 동일성을 확인했다. 실제 모델 출력은 선행 탐색 실험의 TP/FP/FN/F1과 일치한다. 실행 코드·산출물·학습 상태 해시도 대조했다.

순차 추론 검수 중 BLAS의 배치 크기에 따른 미세한 사인 잔차 차이가 ECDF 순위를 바꾸는 문제를 발견했다. v2에서는 행별 합산 순서를 고정했고, 시각은 각 행에 동일한 파싱 규칙을 적용했다. 최종 수치는 유지됐다. 원본 센서 이력은 직전 7행만 유지하며 이상 구간 내 반복 경보는 점검 건 하나로 묶는다.

2026-09-25 Claude 후속 검수([기록](../analysis/press_guard_review/README.md))와 Codex 재검수는 [재검수 기록](../analysis/press_guard_review/codex_recheck.md)을 참고한다. Chrome 자동 조작으로 탭·선택·재생·CSV 업로드/내보내기까지 확인했다. 계산 불가 점수를 0으로 그리던 문제와 빈 재생 위치의 호버 오류를 수정했다. 사람이 직접 조작한 확인·다른 OS·다른 날짜/설비 검증은 별개다. 수집 오류는 판정 보류이며 고장 확률·원인·잔여수명·자동 정지를 구현한 것이 아니다.
