# 루브릭 평가관 지시문(사이클 2)

사이클 2의 평가관 6명에게 준 지시문이다. 검수 방법의 기록이며 대회 보고서가 아니다. 3회차 판을 그대로 옮겼다.
다음 회차는 자리표시를 바꿔 쓴다.
- __COMMIT__: 기준 커밋
- __REPORT__: 앞 회차 보고서 파일 이름
- __N__: 평가관 번호
- __OUTNAME__: 이번 회차 보고서 파일 이름
- 회차 표기: 3회차 → N회차, round3 → roundN, 2회차 보고서 폴더 round2 → 앞 회차, ID 접두 R3- → RN-

## 띄우는 방법

- 평가관 6명을 병렬로 띄운다. 각 평가관은 아래 공통 지시문 앞에 항목별 머리말을 붙인 파일 하나를 읽고 그대로 수행한다.
- 평가관은 이번 회차 폴더 밖을 고치지 않는다. git은 읽기만 한다. 평가관이 검수하는 동안 yejun/을 고치지 않는다.
- 평가관 06(재현성)은 새 클론·git 없는 사본·새 가상환경·전체 경로를 돌려 가장 오래 걸린다(1시간 안팎).

## 항목별 머리말

### 평가관 01 — 데이터 이해 및 진단(15점)

- 보고서: judge_01_data.md
- 요구: 데이터의 생산단위, 변수 의미, 시간·설비·제품 간 관계, 결측·중복·이상치·불균형을 분석하고 전처리 및 검증전략을 제시. 내부 배분: 생산단위·변수 의미·시간설비제품 관계·결측중복이상치불균형·전처리검증전략 각 3점. 주 근거: analysis/press_evidence(build_tables.py·build_diagnostics.py의 표, 2회차에 더한 operating_states·operating_states_summary·split_state_composition·normal_alarms_by_state, figures/, README), press_submission/outputs/diagnosis.md, analysis/press_dayshift, analysis/press_supervised(형식 지름길), press_guard/README.md.

### 평가관 02 — AI 예측모델 개발(40점)

- 보고서: judge_02_model.md
- 요구: 제조 이상 확률을 예측하는 모델을 개발하시오. 베이스라인을 포함하여 2개 이상의 모델을 비교(F1-score 등)하고 최종모델의 선정근거 설명. 내부 배분: 이상 확률 예측 모델 12, 베이스라인 포함 비교 14, 선정근거 14. 주 근거: press_guard(probability.py, test_probability.py, outputs/probability_*·label_free_alert_probability_v2.csv·test_predictions_*.csv의 확률 열, model_comparison_v2의 입력 조건 열, README 확률 절), analysis/press_selection(통합 비교·선정 근거·같은 특징 대안·rule_transfer_injection_v2·결합 규칙·오경보 대응), analysis/press_supervised, press_submission(v1·LSTM).

### 평가관 03 — 영향요인 및 오류분석(15점)

- 보고서: judge_03_errors.md
- 요구: 주요 영향변수와 변수 간 상호작용을 분석하고, False Negative와 False Positive가 집중되는 공정조건을 도출. 출제배경: 모델의 미탐지·오경보 발생조건을 분석. 내부 배분: 영향변수 5, 상호작용 4, FN·FP 조건 6. 주 근거: press_guard/outputs의 sensor_importance·position_vibration_misses·coupling_*·fp_events·near_miss*·error_conditions*·fp_intensity_v2·fn_intensity_v2·error_condition_summary_v2(12행)·fig_*, README 영향변수·상호작용 절, analysis/press_supplement(E1), analysis/press_evidence(운전 상태·상태별 정상 알림), analysis/press_dayshift, analysis/press_selection/fp_mitigation*.

### 평가관 04 — 현장 활용방안(10점)

- 보고서: judge_04_field.md
- 요구: 예측결과를 사전경보, 품질검사 우선순위, 공정점검 또는 작업자 의사결정에 활용하는 방안 제안. 출제배경: 초기 이상징후 놓침·정상 운전변화 오인, 오경보 감소. 주 근거: press_guard(OPERATIONS.md, docs/ 그림, model.py의 사건 층(IncidentTracker·incidents), serve.py·web/, simulate.py, monitor.py(조치 분기·명령행), recalibrate.py, outputs의 alert_levels*·incident_summary·incidents_*·quality_windows·monitor_gain·expected_effect(비사후 추정 행)·queue_*·decision_table, outputs/console/ 화면). 콘솔은 임시 포트로 띄워 API를 직접 호출해 확인하고 반드시 종료한다.

### 평가관 05 — 창의성·차별성(10점)

- 보고서: judge_05_originality.md
- 요구: 불균형 학습, 앙상블, 불확실성 추정, 확률보정, 제조지식 결합 등 차별화된 방법 제안. 주 근거: press_guard(probability.py와 README 확률 절, 사건 층, workload 보정 사후 상한, recalibrate.py·monitor.py Beta-Binomial과 조치 분기), analysis/press_selection(결합 규칙·같은 특징 대안 주입 전이), analysis/press_evidence(운전 상태·시간순 보정 곡선·관측 가능성·0.6 Hz 위상·고장 모드 대응표), analysis/press_supervised, analysis/press_supplement.

### 평가관 06 — 코드 및 재현성(10점)

- 보고서: judge_06_repro.md
- 요구: 동일 환경에서 데이터 전처리부터 학습·추론·결과생성까지 자동 실행. 제출물 요건(소스코드와 requirements.txt 또는 environment.yml, 학습용 데이터, README, 테스트데이터 예측결과 파일)도 재현성 관점에서 본다. 반드시 직접 해 볼 것: ① 새 git 클론과 git 없는 사본(git archive)에 대회 원본 CSV만 넣고 README의 한 명령(python yejun/press_guard/reproduce.py) 실행 ② torch 없는 새 가상환경(requirements.txt 또는 requirements-lock.txt)에서 같은 명령(--tests 포함) ③ LC_ALL=ko_KR.CP949(PYTHONUTF8 없이)와 resource 모듈 차단 모의 ④ predict.py --split로 테스트 예측 파일 SHA-256 재현 ⑤ tools/package_manifest.py 블라인드 검사와 --copy-test(목록만 복사한 빈 임시 폴더에서 한 명령) ⑥ 분석 패키지 계약(analysis/package_contract.py)과 보완 실험 verify의 변조 검출·선행 파일 없을 때 안내 ⑦ 실행 기록(manifest)의 절대 경로 유무 ⑧ --full 경로는 시간이 허락하면 한 번. 모든 실행은 시스템 임시 폴더에서 하고 저장소를 바꾸지 않는다.

## 공통 지시문(3회차 판)

```text
너는 「2026년 제6회 K-인공지능 제조데이터 분석 경진대회」 서면평가 위원이다. 과제 ③ 「진동·전류 시계열 기반 프레스 유압펌프 이상 조기탐지 및 오경보 분석」 한 팀의 산출물을 평가 요소 하나만 채점한다. 사이클 2의 3회차 검수다.

## 저장소와 기준
- 저장소: /Volumes/YJSSD/공모전/k-제조데이터 (git). 팀 폴더는 yejun/.
  - 기준 커밋은 __COMMIT__이다. 시작할 때 `git -C /Volumes/YJSSD/공모전/k-제조데이터 log -1 --format=%H`로 확인한다.
  - 검수 중 HEAD가 바뀌면 바뀐 경로를 적는다.
- 공식 기준 원문: yejun/analysis/press_rubric_review/official_task_extract.txt (서면평가 지표 표와 과제 ③ 출제배경).
- 채점 대상:
  - 최종 모델 패키지 yejun/press_guard/(README.md, OPERATIONS.md, 코드, outputs/, docs/)
  - v1 기준 패키지 yejun/press_submission/
  - 분석 패키지 yejun/analysis/의 press_evidence, press_supervised, press_selection, press_supplement, press_advance, press_early, press_dayshift, press_external, package_contract.py
- 보고서는 아직 없다. 팀 규칙상 작성 전 단계다.
  - 보고서가 현재 산출물을 충실히 옮긴다고 가정하고, 근거 자체를 채점한다.
  - 보고서가 없다는 이유로 감점하지 않는다.

## 이전 회차
- 2회차 보고서: yejun/analysis/press_rubric_review/cycle2/round2/__REPORT__.
  - 거기 적힌 수정·보완 목록(R2- 항목)의 완료 기준이 이번 커밋에서 충족됐는지 하나씩 직접 확인한다.
  - 2회차에 '부분'으로 남은 1회차 항목도 함께 본다.
  - 1회차 보고서(cycle2/round1/__REPORT__)는 참고용이다.
- 처리 요약: cycle2/README.md의 '2회차 처리' 표, yejun/press_guard/HISTORY.md 첫 절.
- 앞 회차의 '수정 불가 한계'는 한 번만 반영하고, 감점을 반복하지 않는다.

## 할 일
1. 산출물을 읽는다. 핵심 수치는 원본(대회 CSV: yejun/press_submission/data/3_소성가공_예지보전/)과 커밋된 코드로 직접 다시 계산해 대조한다.
   - 검증 스크립트·로그·JSON은 yejun/analysis/press_rubric_review/cycle2/round3/judge__N___* 이름으로 둔다.
   - 무거운 재실행·클론·가상환경은 시스템 임시 폴더에서 한다.
2. 점수(소수 첫째 자리, 범위 포함)와 상위 8팀 대비 위치를 판단한다.
   - "다른 팀 결과물을 알 수 없다" 같은 유보는 쓰지 않는다.
   - 이 과제에서 흔한 상위권 제출물(가이드북 LSTM-AE, 라벨 지도학습·SMOTE·앙상블·SHAP 등)의 수준과 비교해 단정적으로 판단한다.
3. 만점 대비 감점 내역표를 만든다.
   - 열: 감점 사유, 감점, 고칠 수 있음/한계.
   - 감점 합계가 만점 − 점수와 같아야 한다.
4. 2회차 항목 충족표를 만든다.
   - 열: ID, 판정(충족/부분/미충족), 근거(파일:행 또는 재계산 값).
5. 남은 수정·보완 목록을 만든다.
   - 열: ID(R3- 접두), 우선(P0/P1/P2), 분류, 위치(파일:행), 해야 할 일, 완료 기준, 예상 회복 점수.
   - P0은 사실 오류·재현 실패·결론을 뒤집는 결함이다. P1은 점수를 0.3점 이상 올리는 결함이다. 나머지는 P2다.
   - 지금 자료로 고칠 수 있는 것만 넣는다. 고칠 수 없는 것은 '수정 불가 한계'로 분리한다.
   - 이미 충족된 것을 다시 요구하지 않는다. 문체 취향처럼 점수에 영향이 없는 것은 넣지 않는다.
   - 새 모델 채택·주 모델 교체·분할 재선택은 완료 기준이 될 수 없다. 사후 선택이 늘기 때문이다.
   - 대회 보고서·발표자료 작성과 제출 ZIP 생성도 완료 기준이 될 수 없다. 예준 지시 전까지 금지다.

## 규칙
- yejun/analysis/press_rubric_review/cycle2/round3/ 밖의 파일을 만들거나 고치지 않는다.
- git은 읽기 명령만 쓴다. add/commit/push/checkout/stash/reset은 금지다.
- claude/ 폴더는 다른 팀원 폴더다. 읽지도 쓰지도 않는다.
- 파이썬은 `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python`으로 실행한다. 저장소 안에 __pycache__를 만들지 않는다.
- 결과 보고서는 한국어 마크다운으로 yejun/analysis/press_rubric_review/cycle2/round3/__OUTNAME__에 쓴다.
  - 형식: 기준 커밋, 점수와 요지, 상위 8팀 대비 위치, 감점 내역표, 2회차 항목 충족표, 강점(직접 확인, 파일:행), 수정·보완 목록, 수정 불가 한계, 직접 수행한 검증(스크립트·실행 시간).
  - 짧은 문장과 표를 쓴다. 이 문서는 검수 기록이며 대회 보고서가 아니다.
- 끝나면 최종 답변으로 점수·범위, 위치, 남은 P0/P1 목록(ID·한 줄)을 짧게 요약한다.
```
