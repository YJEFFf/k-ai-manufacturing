# 루브릭 검수 사이클 2 — 평가관 6명 반복 검수

예준 지시(2026-09-27): 평가 요소마다 평가관 에이전트가 점수를 매기고, 부족한 부분을 고친 뒤 다음 검수에서 고칠 수 있는 부족분이 나오지 않을 때까지 반복한다. 검수 기록이며 대회 보고서가 아니다. 공식 기준은 [official_task_extract.txt](../official_task_extract.txt)다.

## 1회차(round1, 기준 커밋 dcd300a)

| 평가관 | 항목(배점) | 점수 | 보고서 |
|---|---|---:|---|
| 01 | 데이터 이해 및 진단(15) | 12.5 | [judge_01_data.md](round1/judge_01_data.md) |
| 02 | AI 예측모델 개발(40) | 31 | [judge_02_model.md](round1/judge_02_model.md) |
| 03 | 영향요인 및 오류분석(15) | 11.5 | [judge_03_errors.md](round1/judge_03_errors.md) |
| 04 | 현장 활용방안(10) | 7.0 | [judge_04_field.md](round1/judge_04_field.md) |
| 05 | 창의성·차별성(10) | 8.0 | [judge_05_originality.md](round1/judge_05_originality.md) |
| 06 | 코드 및 재현성(10) | 7.5 | [judge_06_repro.md](round1/judge_06_repro.md) |
| | 합계(100) | **77.5** | |

평가관의 검증 스크립트·로그·JSON은 같은 폴더에 있다. 평가관은 이 폴더 밖을 고치지 않았다.

## 1회차 처리

| 평가관 항목 | 처리 위치 |
|---|---|
| 01 D1~D7, 05 O1(a)·O4 | `analysis/press_evidence/`(build_diagnostics.py, figures.py, 새 표 16개·그림 5장), `press_submission/README.md` 참조 두 줄 |
| 02 M1, 05 O2 | `press_guard/probability.py`, 예측 열, `outputs/probability_*`, `label_free_alert_probability_v2.csv` |
| 02 M2, 05 O5·O6 | `analysis/press_supervised/` v2(3ad2452) |
| 02 M3~M5, 05 O3, 03 E7 | `analysis/press_selection/` |
| 03 E1~E6·E8 | `press_guard/insights.py`와 보강 표·그림, README E6 문장 |
| 04 U1~U8, 05 O1(b)·O7 | `press_guard/`(2단계 알림, 품질 시간창, monitor.py, simulate.py, recalibrate.py, 콘솔, OPERATIONS.md, docs/ 그림, expected_effect_v2.csv) |
| 06 R1~R5·R9·R11 | `press_guard/`(runtime.py, reproduce.py, requirements·environment.yml, test_predictions, predict.py --split, verify 예측 요약, 이식성 시험), `press_submission/run_all.py` torch 지연 import와 v1 재동결 |
| 06 R6~R8·R10 | `analysis/package_contract.py`와 각 패키지 contract.json·expected·test_contract.py, 보완 실험 계약 수정, README 경로 정리 |

주 지표(A F1 0.961938·B 0.970990, 정상 0/120·3/180, 이상 21/21)와 경보 규칙은 바꾸지 않았다. 사후에 정한 것(2단계 규칙, 대기열 정렬 키, 확률 층)은 각 문서에 그 사실을 적었다.

## 2회차(round2, 기준 커밋 e9ed90f·f5679ca)

| 평가관 | 항목(배점) | 1회차 | 2회차 | 보고서 |
|---|---|---:|---:|---|
| 01 | 데이터 이해 및 진단(15) | 12.5 | 13.6 | [judge_01_data.md](round2/judge_01_data.md) |
| 02 | AI 예측모델 개발(40) | 31 | 36.5 | [judge_02_model.md](round2/judge_02_model.md) |
| 03 | 영향요인 및 오류분석(15) | 11.5 | 13.0 | [judge_03_errors.md](round2/judge_03_errors.md) |
| 04 | 현장 활용방안(10) | 7.0 | 8.5 | [judge_04_field.md](round2/judge_04_field.md) |
| 05 | 창의성·차별성(10) | 8.0 | 8.8 | [judge_05_originality.md](round2/judge_05_originality.md) |
| 06 | 코드 및 재현성(10) | 7.5 | 9.0 | [judge_06_repro.md](round2/judge_06_repro.md) |
| | 합계(100) | 77.5 | **89.4** | |

1회차 항목은 거의 모두 충족으로 판정됐다(부분: 01 D4, 02 M2·M3, 03 E1·E3·E8, 05 O1(b)). 2회차에 새로 나온 P0는 두 건이다. 01 R2-D1(정상 운전 2수준 상태와 약 20초 주기를 진단하지 않아 문서 결론 두 개가 자료와 어긋남)과 06 R2-01(제출 목록만 복사한 사본에서 한 명령이 8/15에서 멈춤)이다.

## 2회차 처리

| 평가관 항목 | 처리 |
|---|---|
| 01 R2-D1~D3, 05 R2-O10·O11 | press_evidence: 운전 상태 표 4개(2수준·20초 주기·기록-상태 동기화·분할별 상태 구성·상태별 정상 알림), 결론 세 곳 정정, 그림 3장, 결정표 인용, 관측 이상 진동의 저주파 성격을 FM 대응표에 연결, 앨리어싱 일반형 |
| 02 R2-M1·M4 | press_selection: 같은 특징 대안의 주입 전이표(rule_transfer_injection_v2), fmax 유지 근거를 사전 선택 유지·경보별 단독 근거로 한정. press_supervised README에 값 차이 이유·부스팅 문턱 흔들림·가중 부스팅 범위 |
| 02 R2-M2·M3·M5, 05 R2-O8·O12 | 예측 파일에 파일 비율 사전확률 열, 확률 상한·채점 환산 설명, B 문턱 확률의 등방 계단 설명과 경보 행 최소 우도비, SBB 값을 참고값으로 정정, 확률 층이 오경보를 거르지 못함을 명시, 비교표 입력 조건 열 |
| 03 R2-01~06 | 운전 강도별 조건부 오경보율(fp_intensity_v2), 고장 모양 × 운전 강도 미탐(fn_intensity_v2), 영향변수·상호작용 절, 위치×진동 그림과 오경보 사례 성분·문턱, 12행 요약의 전 행 인용·CI·lift, 절대 구간 번호 |
| 04 R2-01~09 | 감시 조치 분기(재보정 검토 / 설비 점검 요청)와 명령행, 비사후 2단계 업무량 추정(교대 3.3건, 상한 12.7건), 사건 묶음(이상 21기록 → 사건 1개·알림 2건, 일괄 = 스트림), 콘솔 사건 대기열·건 번호·사건 단위 결과 기록, 기록 경계 0.1초 ± 20 ms와 수집 시각 경고, 확률 상한 표시, 대기열 한계 9조건 |
| 05 R2-O9 | 업무량 사후 95%(A 44·B 92건)를 운영 절차·콘솔 표에 표시 |
| 06 R2-01~08 | 제출 목록을 실행 기록 인용에서 검사하고 목록 사본 한 명령 시험(--copy-test), 실행 기록의 절대 경로 제거(v1·press_advance 상대 경로), v1 시험 인코딩과 정적 검사 확대, 파이썬 3.11~3.12, 자식 로그 UTF-8, verify 설명 정정, 선행 파일 없을 때 안내, yejun/.gitattributes(LF 고정), README 명령 정리·내부 표기 제거·lock 보완 |

## 3회차(round3, 기준 커밋 061fac8)

| 평가관 | 항목(배점) | 1회차 | 2회차 | 3회차 | 보고서 |
|---|---|---:|---:|---:|---|
| 01 | 데이터 이해 및 진단(15) | 12.5 | 13.6 | 14.4 | [judge_01_data.md](round3/judge_01_data.md) |
| 02 | AI 예측모델 개발(40) | 31 | 36.5 | 38.1 | [judge_02_model.md](round3/judge_02_model.md) |
| 03 | 영향요인 및 오류분석(15) | 11.5 | 13.0 | 14.1 | [judge_03_errors.md](round3/judge_03_errors.md) |
| 04 | 현장 활용방안(10) | 7.0 | 8.5 | 9.1 | [judge_04_field.md](round3/judge_04_field.md) |
| 05 | 창의성·차별성(10) | 8.0 | 8.8 | 9.2 | [judge_05_originality.md](round3/judge_05_originality.md) |
| 06 | 코드 및 재현성(10) | 7.5 | 9.0 | 9.7 | [judge_06_repro.md](round3/judge_06_repro.md) |
| | 합계(100) | 77.5 | 89.4 | **94.6** | |

- 2회차 항목은 거의 모두 충족으로 판정됐다. 부분은 02 R2-M5(md 표 표시)와 04 R2-01(콘솔 감시 표·재보정 도구 잔여), 06 R2-08(제출 문서 잔여)다.
- P0는 없다. P1은 01 R3-D1(정상 운전 상태 전환이 학습·보정·평가에 한 번도 없다는 검증 한계와 전환 모의)이다. 나머지는 P2다.
- 여섯 평가관 모두 항목 1위로 판정했다. 남은 감점은 고칠 수 있는 것 약 2.35점과 수정 불가 한계(독립 검증 없음, 날짜 교락, 이상 한 에피소드, 현장 자료 없음) 약 3.05점이다. 고칠 수 있는 것을 모두 마치면 평가관 예상 합계는 약 97점이다(01 15.0, 02 38.5, 03 14.5, 04 9.5, 05 9.4, 06 10.0).

## 3회차 남은 항목과 처리 방향(처리 전)

예준 지시(2026-09-28)로 3회차 검수까지 Claude Code가 하고, 아래 처리부터 Codex가 이어간다. 아래 표는 평가관 보고서의 수정·보완 목록을 파일별로 모으고, 겹치는 요구를 합쳐 처리 방향을 정한 것이다. 항목별 완료 기준과 기대값은 각 보고서의 수정·보완 목록에 있다. 평가관 스크립트(round3/judge*.py)는 대조용이고, 코드는 팀 코드로 따로 구현한다.

공통 조건은 다음과 같다.
- 주 지표(A F1 0.961938·B 0.970990, 정상 0/120·3/180, 이상 21/21), 경보 규칙, 분할, 저장 모델(guard_A/B.json)은 바꾸지 않는다.
- 새 분석과 문구는 사후 분석·가설로 표시한다.
- 대회 보고서·발표자료·제출 ZIP은 만들지 않는다.

### press_guard

| 순서 | 항목 | 처리 방향 |
|---:|---|---|
| 1 | 04 R3-02 사건 단계 | `model.incidents()`의 단계를 사건의 누적 경보 행으로 정한다. 합이 `ESCALATION_ALARM_ROWS` 이상이면 2다(`IncidentTracker`의 격상과 같은 규칙). `escalation_row`는 predictions 없이도 건 순서로 계산한다. 누적 1행 뒤 다음 건이 오면 그 건의 `first_row`다. `train.py:117`도 predictions를 넘긴다. 시험: B 평가 상대 기록 3·41(경보 1행)을 2초 간격으로 이은 CSV에서 simulate 격상 1건 = `incidents()` 단계 2 = 콘솔 `level_counts` 점검 요청 1 |
| 2 | 운전 상태(01 R3-D5, 03 R3-01, 04 R3-04) | ① `model.py`에 `LOAD_STATE_RMS = 91.9`와 `STATE_MIN_ROWS = 17`을 둔다. 근거는 press_evidence 2성분 경계 91.886이다. 정상 469기록의 저수준 최대가 91.457, 부하 최소가 91.997이라 분류가 같다. 전류 RMS는 원 전류의 기록 평균 제거 RMS(ddof 0)다(`build_diagnostics.py`의 `segment_stats`).<br>② `predict()`에 `record_current_rms`(기록 안 누적)와 `operating_state` 열을 더한다. `StreamDetector`는 기록별 누적합을 이어받는다(일괄 = 스트림 시험). 예측 열이 늘어 test_predictions와 digest를 재동결한다.<br>③ `cases()`·`incidents()`에 상태 열을 둔다. 콘솔 상세와 판단표 첫 확인에 상태와 그 조건의 대회 정상 알림률을 참고로 보인다(B α1% 부하 3/51·저수준 0/94).<br>④ `fp_intensity`에 상태 행을 더한다. 5적합 합침 α5%는 부하 17/154 대 나머지 0/326이다. 60구간 블록 층화 CMH(statsmodels `StratifiedTable`, 연속성 보정)와 블록 안 순열 20,000회, 부하 상태 안 진폭 효과(중앙 203.6, Fisher·Spearman)도 더한다. 기대값은 03 R3-01 완료 기준에 있다.<br>⑤ 오류 요약의 FP 행에 상태 수치 한 줄을 넣는다(12행 유지). README ④·:51과 OPERATIONS 3·4단계에도 넣는다.<br>⑥ 시험: B α1% 오경보 3건이 모두 부하다 |
| 3 | 감시 분기(05 R3-O1, 04 R3-01) | ① 창별 조치는 네 갈래다.<br>- 한도 안: 「관측 지속」<br>- 변경 기록 있음: 「재보정 검토(운전 조건 변경)」<br>- 기록 없음 + 전류 상승 이동: 「설비 점검 요청(전류 수준 이동: FM4·FM5 점검, 정상 확인이면 재보정)」<br>- 기록 없음·이동 없음: 「설비 점검 요청(열화 의심)」<br>② 점검 요청 두 갈래의 창은 결과가 「정상 확인」일 때만 재보정 자료로 쓴다. `recalibrate.py --windows <monitor.py 창별 CSV, outcome 열>`로 이 규칙을 적용한다.<br>③ `monitor_gain_v2`에 창별 조치 열(변경 기록 없음·있음)을 둔다. 콘솔 감시 표·설명, OPERATIONS 8·9단계, README:163, docstring을 같은 규칙으로 고친다.<br>④ test_monitor 기대:<br>- ×1.5·기록 없음 → 전류 수준 이동 점검<br>- ×1.5·기록 있음 → 재보정 검토<br>- ×1.3·진동 2σ → 열화 의심<br>- --windows는 결과 없는 점검 창을 빼고 정상 확인 창을 남긴다 |
| 4 | 04 R3-03 비사후 2단계 추정 | ① 주 추정을 겹치지 않는 폴드(300~359·360~419)의 α5% 2단계/1단계 1/7로 바꾼다. 교대 4.2건, 상한 15.4건이다.<br>② 기존 1/9는 민감도 행으로 둔다. 540~599가 B 평가와 겹치고, 그 폴드의 기록 570은 대회 오경보다. 동결 B α3% 2/5 → 11.8건과 α5% 3/7 → 12.7건도 민감도 행이다.<br>③ 「사후 선택과 무관」 문구를 사실대로 고친다. README:56, OPERATIONS:32, 콘솔 강조를 맞춘다 |
| 5 | 04 R3-05 문구·집계 단위 | ① 콘솔 설명(`index.html:15`)에 비사후 추정과 사건 단위 알림을 넣는다.<br>② 단계 패널(`:19`)에 「표는 건 단위, 운영 알림은 사건 단위」를 적는다.<br>③ 감시 표의 알림 수는 사건 알림(사건 시작 + 격상)으로 센다.<br>④ README:167 대기열 한계에 사건 단위 결과(2조건 2건)를 `queue_injection_ranks`의 사건 단위 열로 더한다 |
| 6 | 02 R3-M1·M2 확률 표기 | ① π의 정의를 하나로 맞춘다. 행 확률의 π는 행 비율이다. 기록 확률은 같은 π를 쓰는 근사다. 알림 단위 비율은 라벨 없는 환산에만 쓴다. 고칠 곳: README:74, `probability.py:9`, `predict.py:47`, `index.html:10·22`, OPERATIONS:16.<br>② 콘솔 확률 설명에 「B 0.007은 등방 계단 경계, 경보 행 최소 LR 2.42」 한 줄을 넣는다.<br>③ 재보정 모델은 라벨 보정기가 없어 확률 열 4개가 비고 π가 쓰이지 않는다. README 확률 절과 OPERATIONS 2단계를 두 경우로 나눈다. predict·simulate·monitor는 보정기가 없을 때 한 줄 안내를 낸다 |
| 7 | 02 R3-M3 md 표 | `analyze.py`가 `model_comparison_v2.md`를 쓸 때만 입력 조건 값의 `\|` 앞에 역슬래시를 붙인다(CSV는 그대로). round3/judge02_md_table.py로 28/28행이 11칸인지 본다 |
| 8 | 03 R3-02·03·04 오류 분석 | ① `fn_intensity`에 `p_amp`의 BH q 열과 검정 수를 둔다.<br>② 진동 잡음 2σ 행에 ρ 차이(− 오프셋 0.2×)의 단위 재표집 붓스트랩 4,000회 95% 구간을 둔다.<br>③ 잡음 족 반복을 50회(난수 0~49)로 늘린다. E1 기록별 결과(`predictions_e1_records.csv`)는 Git 제외라 빠른 경로에서 쓸 수 없다.<br>④ CSV note와 README 148에 E1 값(74.4%·93.9%)과의 관계를 적는다. README 175의 「11행」을 「12행」으로 고친다.<br>⑤ 영향변수 절에 성분 절제 한 줄을 넣는다(`ablation_v2.csv` 인용) |
| 9 | 01 R3-D1의 press_guard 몫 | README:35(연속 입력 α 문장)에 한 줄을 잇고 press_evidence `state_transition_stress.csv`를 인용한다: 「연속 수집 현장은 전환이 든 정상 연속 자료로 재보정·재검증하기 전에는 대회 오경보 수치를 옮기지 않는다」 |
| 10 | 06 R3-01 제출 문서 링크 | ① 목록 문서의 죽은 상대 링크 10개와 내부 표기 4행을 정리한다. 링크 대상을 목록에 넣거나(press_dayshift·press_early README, press_external/acquisition.json) 링크를 풀어 쓴다. 검수 기록 링크와 「사이클2」·「평가관」 표기는 지운다(`press_submission/README.md:3·5·7·9·63`, `analysis/press_evidence/README.md:10·42·328`, `analysis/press_selection/README.md:158`, `analysis/press_supplement/README.md:3·36·111`, `press_guard/requirements-lock.txt:2`).<br>② `package_manifest.py`의 블라인드 검사에 목록 문서의 상대 링크 대상 존재 검사를 넣는다.<br>③ README:196에 `--copy-test`와 실행 기록 인용 검사를 적는다. README:21의 23단계는 node가 있을 때이고, 없으면 22단계라고 적는다.<br>④ round3/judge06_Q5_docs.py로 죽은 링크가 0인지 본다. press_submission README를 고치면 v1 verify도 다시 돌린다 |
| 11 | 06 R3-02 동결 요약 무결성 | ① `expected/predictions_digest.json`의 해시를 동결 manifest(또는 lock)에 넣고 verify가 대조한다.<br>② 정확 비교 열을 실수가 아닌 모든 열로 넓힌다. 최소한 `incident_id`·`incident_notification`·`incident_escalation`·`magnitude_sensor`·`timestamp`는 넣는다.<br>③ 평가관 탐침 V6b~V6d·V7이 실패로 판정되는지 본다 |
| 12 | 06 R3-04 분석 시험의 선행 파일 | analysis 패키지의 `test_contract.py` 5개가 `package_contract.missing_prerequisites()`로 선행 파일을 확인한다. 없으면 `pytest.skip(FIRST_RUN_HINT)`로 건너뛴다. 학습 전 새 클론에서는 「건너뜀 + 안내」로 끝나야 한다 |
| (1) | 06 R3-03 | 1번(`train.py:117`) 수정으로 함께 풀린다. `incidents_A/B.csv`의 2단계 사건 `escalation_row`가 테스트 예측 파일의 `incident_escalation=1` 행(A 4092, B 6098)과 같아야 한다 |

### analysis/press_evidence

| 항목 | 처리 방향 |
|---|---|
| 01 R3-D1 전환 모의(P1) | ① `state_transition_stress.csv`를 새로 만든다. 시드를 고정하고 동결 A·B를 읽기 전용으로 쓴다. 참고 구현은 round3/judge01_transition_stress.py다.<br>- 잇기: 같은 평가 구간의 50행 기록 두 개를 25행에서 잇는다. 0.6 Hz 위상을 맞추는 오프셋 0~16과 전류 평균 맞춤을 쓴다. 저수준→부하, 부하→저수준, 같은 상태 대조를 조건마다 200쌍 만든다.<br>- 이득: 한 기록 안 25행째부터 계단·10행·20행 경사로 상태 중앙값 비(전류 진폭 1.75, AI0 SD 1.76, AI1 SD 3.0배)와 그 역수를 준다.<br>- α 1·3·5%별로 이음매 뒤 경보 비율과 첫 근거를 세고, 대조는 진폭 비로 층화한다. 평가관 값은 B α1% 74%·43%, 대조 3.5%, 계단 97%·53%, 경사 0~8%다.<br>② README 한계 절과 결정표 두 행(7·14의 한계 칸)에 결측 기제(공백이 전환 순간을 가림)와 해석(가설)을 넣는다.<br>③ contract.json에 넣는다 |
| 01 R3-D2 성분 수 | BIC를 1~6성분으로 넓힌다. 문구를 「저수준 대 부하 범위(하위 2~3수준)」로 바꾼다. 4성분 중앙·가중치·인접 전이, 정상 알림 기록의 하위 수준, 골 분포 문구, 검정력 반영 기대 탐지(95 대 0)를 넣는다 |
| 01 R3-D3 | README:41과 `variable_dictionary` AI2 행(`build_tables.py`)을 주기 진단과 잇는다 |
| 01 R3-D4 | `fig_d2a` 확대 패널을 상태 색으로 칠하고 전류 RMS를 적는다(`figures.py:115-125`) |
| 01 R3-D5 결정표 | conformal 행 한계 칸에 적는다: 보정 구간 상태 혼합에 대한 주변 보장이다. 부하만 보면 B α1% 3/51로 1/62를 넘는다(p 0.049) |
| 05 R3-O2 | FM3 행 문구를 좁은 대역 접힘 전제에 맞춘다. 근거는 이상 기록 주기도표의 최대 주파수가 흩어진다는 것이다 |
| 05 R3-O3 | observability 정상 진동 행과 README O4(a)에 좁은 대역 구조를 넣는다.<br>- AI1 1.79 Hz, AI0 3.59 Hz<br>- 조화 설명 분산 0.91·0.65<br>- AI1 진폭과 전류 진폭 ρ 0.89<br>- 위상 고정 없음<br>D1 결합 해석과 E1 흰 잡음 주입의 한계에 잇는다 |

### analysis/press_selection·press_supervised

| 항목 | 처리 방향 |
|---|---|
| 02 R3-M4 | ① `press_supervised/README.md:64`의 「(0.96~0.97)」을 표 값으로 바꾼다. A 0.915~0.973, B 0.972~0.974이고 가중을 넣으면 0.830~0.974다.<br>② 「A는 대안이 모든 족에서 같거나 높다」에 α 1%를 붙인다. α 3·5% 단발 충격 4σ는 fmax가 두 분할 모두 앞선다는 한 줄을 넣는다.<br>③ remark 열(`run.py:296-298, 308-309`)에도 α 기준을 적는다. Fisher remark의 B 목록에는 전류 잡음 0.1σ와 충격 6σ를 더한다 |

### 재실행·동결 순서

v1(press_submission)과 press_advance는 바꾸지 않으면 건너뛴다. 명령은 `yejun/`에서 `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`로 돌린다.
1. `press_guard/train.py --rolling`
2. `analysis/press_supplement/`의 `fault_injection.py`, `uci_v2.py`, `recalibration.py`, `figures.py`, `verify.py --freeze`, `verify.py --strict`. press_guard 코드 해시가 실행 기록에 들어가므로 다시 돈다.
3. `press_guard/`의 `analyze.py`, `audit.py`, `verify.py --freeze`, `verify.py`
4. 패키지 재실행과 동결. 각 패키지는 재실행 뒤 `analysis/package_contract.py --package analysis/<패키지> --freeze`로 동결한다.
   - `analysis/press_supervised/run.py`
   - `analysis/press_selection/run.py`
   - `analysis/press_evidence/build_tables.py`, `build_diagnostics.py`
5. 네 패키지 계약을 비교하고 `press_submission/verify.py --out press_submission/outputs`를 돌린다.
6. 시험을 돌린다.
   - press_guard pytest
   - analysis 패키지의 `test_*.py`를 파일마다 따로(같은 파일 이름이 겹친다)
   - press_submission tests
   - `node press_guard/test_web.cjs`
7. `press_guard/tools/package_manifest.py --copy-test <빈 임시 폴더>`로 목록 사본의 한 명령 재현을 확인한다.
8. 커밋·푸시한 뒤 4회차 평가관을 띄운다. 지시문은 [judge_prompts.md](judge_prompts.md)이고, 기록은 round4/에 둔다. ID 접두는 R4-다.
