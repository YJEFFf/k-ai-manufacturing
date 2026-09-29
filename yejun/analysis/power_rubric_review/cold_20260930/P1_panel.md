# P1 위원 서면평가 — 과제 ⑤ 전력사용량 예측·최대피크 위험조건 (백지 채점)

- 평가일: 2026-09-30. 관점: 시계열·확률 예측 방법론(누설·시험 노출·사후 선택·검증 설계·보정) + 공장 에너지 관리 실무.
- 기준 커밋: `d5a3446f65a190ed71c867a712283aa5d00dffa2` (시작 시 HEAD 확인). 끝날 때 HEAD: 같음(`d5a3446f…`, 검수 중 변경 없음).
- 대상: `yejun/power_submission/`의 README.md, powerguard/, run_all.py, verify.py, make_submission.py, tests/, requirements.txt, environment.yml, outputs/, expected/, artifacts/(Git 제외, 작업 사본에서 복사), data/okm_augumented_2021.csv. 외부 KAMP ZIP 3종(`데이터셋/`). 공식 기준은 `official_task_extract.txt`.
- 참고로 본 자료: 대회 가이드북(`데이터셋/Guidebook_자원 최적화 AI 데이터셋.pdf`)의 변수 정의. 생산량은 "해당 시점에 생산해야할 생산량"(ERP 입력)으로 정의돼 있다.

**눈가림 준수**

- 열지 않음: `power_submission/PLAN.md`, `power_submission/reviews/`, `yejun/analysis/`(예외 2곳 제외), `yejun/` 바로 아래 메모 문서, `press_guard/`, `press_submission/`, `claude/`, git 로그·커밋 메시지.
- 사본은 `git archive d5a3446 -- yejun/power_submission ':(exclude)…/PLAN.md' ':(exclude)…/reviews'`로 만들어 두 경로가 사본에도 없었다. 제출 폴더 grep은 `--exclude=PLAN.md --exclude-dir=reviews`로 했다.
- git은 `log -1 --format=%H`(해시 확인)와 `archive`/`ls-tree`(해당 커밋의 파일 추출·목록)만 썼다. 쓰기 명령은 쓰지 않았다.
- 자동 노출 공개: 세션 시작 때 하네스가 `yejun/AGENTS.md`(CLAUDE.md 경유), 메모리 색인 요약, 최근 커밋 제목 5개를 컨텍스트에 넣었다. ⑤ 점수는 없었다(검수 횟수·버전 언급만). 다른 과제(③) 수치 한 줄이 있었으나 이 채점과 무관하다. 어느 것도 채점에 쓰지 않았다.
- 코드 주석의 내부 검수 표기("3차 검수" 등)는 제출물의 흔적으로만 판단했고, 가리키는 기록은 찾지 않았다.

---

## ① 총점과 항목별 점수

| 문항 | 배점 | 점수 | 한 줄 판정 |
|---|---:|---:|---|
| 1. 데이터 이해 및 진단 | 15 | **14.0** | 1~4월 전력이 5·6월 패턴의 복제임을 밝혀낸 진단이 탁월하다. 검증 설계가 시험의 새 체제를 담지 못한 한계만 남는다. |
| 2. AI 예측모델 개발 | 40 | **33.2** | 비교·사전 선택 규칙·확률 평가는 엄밀하다. 다만 익일 최종모델이 시험 RMSE에서 단순 프로파일에 지고, 헤드라인이 시험 뒤 추가한 게이트에 기댄다. |
| 3. 영향요인 및 오류분석 | 15 | **13.3** | FN/FP 집중 조건·오즈비·운영 창 분석이 구체적이다. SHAP 상호작용의 해석력과 오차 규칙의 시험 재현성이 약하다. |
| 4. 현장 활용방안 | 10 | **7.8** | 래칫(요금적용전력) 사다리·경보 등급·운영 절차가 실무적이다. 그러나 시험에서 AI 예측이 규칙 대비 추가 절감을 보이지 못했다. |
| 5. 창의성·차별성 | 10 | **9.0** | 복제 포렌식, 유사일+잔차 하이브리드, 지평 결합 잔차 표집 확률, 적응형 구간 등 차별점이 많다. 측정된 이득이 작은 기법도 섞여 있다. |
| 6. 코드 및 재현성 | 10 | **9.4** | 학습부터 다시 돌려도 동결값 98/98·시험 예측 SHA·모델 파일 목록까지 일치했다. 전체 실행이 길고 제출 밖 문서를 참조한다. |
| **합계** | **100** | **86.7** | |

---

## ② 항목별 감점 내역

감점 합 = 배점 − 점수. "구분"은 지금 자료로 고칠 수 있는지다.

### 1. 데이터 이해 및 진단 (15 − 14.0 = 1.0)

| 사유 | 감점 | 근거 | 구분 |
|---|---:|---|---|
| 검증 설계가 시험의 핵심 체제를 담지 못함. 교차검증은 6·7월 2폴드(학습 1~2개월)이고 평일 정지·공휴일 가동이 없다. 팀은 차이를 진단했지만 층화 점검 같은 장치는 없다. 결과적으로 교차검증 순위가 시험에서 두 과제 모두 뒤집혔다 | 0.5 | `outputs/diagnostics/split_composition.csv:2-4`, `input_support_test_days.csv:3-7,17`, `outputs/cv/selection_summary.csv:5,22` | 대부분 자료 한계(체제별 성적 보고는 고칠 수 있음) |
| 설비·제품 단위 관계는 분석하지 못함(자료에 구분 없음). 외부 #46으로 동시 기동 기전만 보였다 | 0.3 | `outputs/external/external_summary.json`(kamp46_mechanism) | 자료 한계 |
| 원본 판정 근거(규칙·문턱 6종·972조합·검정 4종)의 분량이 커서 핵심 메시지가 묻힐 위험 | 0.2 | `outputs/diagnostics/copy_direction_checks.csv:2-10`, `copy_origin_sensitivity.csv`(85 KB) | 고칠 수 있음 |

### 2. AI 예측모델 개발 (40 − 33.2 = 6.8)

| 사유 | 감점 | 근거 | 구분 |
|---|---:|---|---|
| (a) 익일(B) 최종모델 M8 혼합이 시험 RMSE에서 기준모델 BL3(체제×요일유형4×슬롯 평균)에 유의하게 진다(M8−BL3 +1.68 [0.30, 3.04]). 내가 따로 짠 같은 구조의 프로파일도 12.30이었다. 일 최대 오차는 M8이 낫다(M8−BL3 −2.15 [−3.66, −0.63]). 그런데 헤드라인 "최선 기준 대비 7.9%"는 교차검증 기준 BL5와의 비교다 | 2.0 | `outputs/analysis/test_bootstrap.csv:20,24`, `test_skill.csv:3,13`, `powerguard/stage_analysis.py:699`, 재계산 `p1_independent_check.json` | 성능은 자료 한계, 표기는 고칠 수 있음 |
| (b) 계획 정지 게이트를 시험을 본 뒤 추가했다. 게이트 없이는 B 20.94(M8)·32.22(M1)로, 모든 구조 기준(BL5 15.18, BL3 12.29)보다 나쁘다. 공개는 충실하지만 B 헤드라인 13.98은 사후 수치다 | 2.0 | `README.md:57-60,67`, `outputs/analysis/ablations.csv:21-25`, `powerguard/models.py:455-460` | 되돌릴 수 없음(병기는 가능) |
| (c) 실시간(A) 선택 M7c가 시험에서 M1 LightGBM보다 유의하게 나쁘다(M7c−M1 +0.42 [0.03, 0.84]). 미선택 M8보다도 나쁘다(M8−M7c −0.51 [−0.78, −0.29]). 교차검증 날짜 부트스트랩 구간이 월 사이 변화를 담지 못한다 | 0.6 | `outputs/cv/selection_summary.csv:2,5`, `selection.json`(A trail) | 자료 한계 |
| (d) 다음 1시간 피크 경보의 F1 이점이 시험에서 사라진다. F1 0.694는 기후값(체제×슬롯 빈도) 0.695와 같다(차이 −0.001 [−0.048, 0.047]). 시각 규칙보다 +0.03 [−0.02, 0.08]로 유의하지 않다. 우위는 확률 품질(BSS 0.19 [0.08, 0.29], PR-AUC +0.19)에 있다. 일 단위 초과(일 최대 ≥ T)도 전면 가동일 규칙과 F1이 같다(0.981) | 0.7 | `outputs/peak/next_hour_f1_bootstrap.csv:4-9`, `next_hour_prob_quality_bootstrap.csv:14,16` | 성능은 자료 한계, 헤드라인 표기는 고칠 수 있음 |
| (e) 계획(가동 체제) 입력에 크게 의존한다. 체제 오류 5%면 B 시험 RMSE가 13.7에서 평균 32.1로 오른다(M1). 달력만 쓰면 41.6이다. 가이드 정의와는 맞는 가정이지만 운영 입력 품질 위험이 크다 | 0.5 | `outputs/analysis/plan_regime_error_summary.csv:5`, `plan_information_value.csv:2-3` | 자료 한계 |
| (f) 80% 예측구간이 피크에서 덜 덮는다(B Mondrian 0.69, A4 0.73) | 0.3 | `outputs/peak/interval_coverage.csv:17` | 일부 고칠 수 있음 |
| (g) 후보 12개×과제 5개, 게이트·혼합·하이브리드, 규칙 v1/v1.1이 얽혀 있다. 최종모델과 근거를 한눈에 보기 어렵다 | 0.4 | `outputs/cv/selection_summary.csv`(33열), `selection.json` | 고칠 수 있음 |
| (h) B 선택의 근거가 얇다. 혼합 구성원을 같은 OOF 순위로 고른 뒤 같은 OOF로 평가한다(중첩 없음). B 선택은 이 비교(M8−M1 −0.23, 상한 −0.03)에 겨우 걸렸고, 시험에서는 +0.24 [−0.32, 0.74]다. 구조 기준(BL5)의 k를 현재 폴드로 맞추면(k=4) 같은 규칙이 B에서 BL5를 고른다(팀 사후 민감도, 공개) | 0.3 | `powerguard/stage_models.py:82-108`, `outputs/cv/selection.json`(B trail), `outputs/analysis/test_bootstrap.csv:14`, `structural_retuned_selection.json`(B.rule_choice_with_retuned_baseline) | 고칠 수 있음(폴드 교차 구성원 선택·기준 초모수 동등 조정 보고) |

### 3. 영향요인 및 오류분석 (15 − 13.3 = 1.7)

| 사유 | 감점 | 근거 | 구분 |
|---|---:|---|---|
| SHAP 상호작용 상위가 지연값·유사일 쌍이라(lag_d2×analog_regime 9.06 등) 공정조건으로 읽기 어렵다. 시각×기온은 별도 구조 모델로 우회했다 | 0.6 | `outputs/analysis/shap_interactions.csv:2-4`, `powerguard/stage_analysis.py:475-505` | 고칠 수 있음 |
| 교차검증에서 찾은 오차 규칙의 시험 재현이 5/14다. 오차 크기 규칙은 0/6이다 | 0.5 | `outputs/analysis/error_rules.csv`(reproduced 열) | 자료 한계(시험 45일) |
| 큰 오차가 소수 날짜로 설명된다. 8/16(대체공휴일 가동)이 M8−BL3 SSE 차이의 50%다. 생산량 수준과의 연결은 상관 ≈0에서 멈춘다 | 0.3 | `outputs/analysis/test_inversion_days.csv:2-5`, `outputs/diagnostics/production_power_relation.csv:2-4` | 자료 한계 |
| 분석 산출물 30개 파일에 FN/FP 결론이 흩어져 있다 | 0.3 | `outputs/analysis/` | 고칠 수 있음 |

### 4. 현장 활용방안 (10 − 7.8 = 2.2)

| 사유 | 감점 | 근거 | 구분 |
|---|---:|---|---|
| 시험에서 AI 예측의 추가 기여가 확인되지 않는다. 같은 개입 수준에서 모델 확률 차단과 반응형 규칙이 모두 8월 최대 215다. 기본 설정에서는 개입이 약 3배인 반응형 규칙이 207.1로 더 낮춘다. 래칫 위험일 규칙은 시험에서 표시 0건, 재현율 0이다. 통합 시나리오의 절감(222→214)은 인터록·순차 기동에서 나오고, ④ 수요제어의 추가 효과는 0이다 | 1.2 | `outputs/field/demand_controller.csv:12-13`, `demand_controller_pareto.csv`(test, 204.2), `ratchet_risk_days_summary.json:31,36`, `integrated_scenario.csv:2-6` | 성능은 자료 한계, 결론 표기는 고칠 수 있음 |
| 절감 효과가 가정에 기댄다(스파이크 상한 인터록, 기동 과도분 50% 분산, 사전 냉방 c=0.3). 전력 단위가 없어 원화 환산이 없다 | 0.4 | `outputs/field/integrated_scenario.csv:3-5`, `powerguard/stage_field.py:578` | 자료 한계 |
| 운영 기준(T=182) 경보 부담이 크다(시험 "주의 이상" 9.1시간/가동일). 요금 목표(T=210.9) 등급은 시험에서 경계·심각 7행 중 초과 0이고, 초과 9행 중 6행이 "정상"이었다 | 0.4 | `outputs/field/alarm_burden.csv:5-7`, `alarm_grades_billing_target.csv:6-9` | 일부 고칠 수 있음 |
| 도입 요건(수요제어기·인터록 구현, 계획 입력 절차, 교육)이 구체적이지 않다 | 0.2 | `outputs/field/operating_procedure.csv:2-6` | 고칠 수 있음 |

### 5. 창의성·차별성 (10 − 9.0 = 1.0)

| 사유 | 감점 | 근거 | 구분 |
|---|---:|---|---|
| 일부 차별 기법의 측정 이득이 작거나 없다. 냉방 단조 제약은 M7 대비 차이 ≤0.03이다. 기상 특징을 빼도 B +0.005다. A 혼합은 선택되지 않았다 | 0.5 | `outputs/test/test_metrics.csv`(M7·M7c 행), `outputs/analysis/ablations.csv:2-5` | 자료 한계 |
| 불균형 학습 기법은 명시적으로 쓰지 않았다(문턱·기후값 비교로 대응) | 0.2 | `powerguard/stage_peak.py:396-404` | 고칠 수 있음(선택) |
| 부가 분석(외부 자료 3종, 냉방, 야간 이동 등)이 많아 차별점의 초점이 흩어진다 | 0.3 | `outputs/field/`, `outputs/external/` | 고칠 수 있음 |

### 6. 코드 및 재현성 (10 − 9.4 = 0.6)

| 사유 | 감점 | 근거 | 구분 |
|---|---:|---|---|
| 전체 실행이 길다(README 5,088초, 내 실행 4,167초). 심사 환경의 재현 부담이 크다. ablation을 빼면 약 12분이라는 안내는 맞았다(751초) | 0.3 | `README.md:47-49`, 실행 기록 | 일부 고칠 수 있음 |
| 제출 ZIP에서 빠지는 PLAN.md와 내부 검수 차수를 코드·README가 참조한다 | 0.2 | `powerguard/config.py:1`, `powerguard/stage_models.py:113`, `tests/test_data.py:1`, `README.md:61,71,74`, `powerguard/stage_field.py:814` | 고칠 수 있음 |
| verify는 그림을 이름으로만 확인한다. 일부 단계만 다시 돌리면 이전 산출물도 "일치"로 센다(신선도는 경고만) | 0.1 | `verify.py:146-178` | 고칠 수 있음 |

---

## ③ 강점 (직접 확인한 것만)

### 1. 데이터 이해 및 진단

- 257일 중 115일이 다른 날과 96값이 같은 복제이고, 고유 패턴은 142개다. 1~4월은 5·6월 패턴의 역채움이다. 내 독립 재계산도 같다(257/142/115, 다중 복제군 45개, 월별 복제 공유일 1월 27·2월 28·3월 28·4월 30·5월 17·6월 28·7월 2·8~9월 0). `powerguard/data.py:225-272`, `outputs/figures/01_copy_forensics_heatmap.png`.
- 복제 방향을 검정으로 뒷받침했다. 자정 연속성 1~4월 88/119 vs 5~9월 131/133(p=1.6e-9), 휴무 다음 평일 야간조 전력 15/17 vs 1/22(p=8.0e-8). `outputs/diagnostics/copy_direction_checks.csv:2-10`.
- 누설 열을 식별했다. 평균 = 네 값 평균의 반올림, 공장인원 = 생산량 ÷ 전력 합. `outputs/diagnostics/variable_dictionary.csv:8,18`, `powerguard/data.py:198-206`.
- 시간 열 손상일 7/13·7/15, 시험의 0 전력 74구간을 찾았다(독립 재계산 일치). 처리 폭포와 분할 구성을 표로 냈다. `outputs/diagnostics/preprocessing_waterfall.csv:2-10`, `split_composition.csv:2-4`.
- 가동일 안에서 생산량과 전력의 상관이 ≈0(0.04 [−0.03, 0.11])임을 보였다. 전력은 생산량이 아니라 가동 체제·시각이 정한다는 해석이다. `outputs/diagnostics/production_power_relation.csv:2-4`, `operating_states.csv`.
- 요일유형4(휴무 다음 평일 분리)는 야간조 이월이 없는 월요일을 잡는다. 내 프로파일로 확인하니 요일유형3이면 시험 RMSE 17.5, 요일유형4면 12.3이다.
- 발행 시각 기준 누설 방지를 코드와 테스트로 보장했다. 과제 A는 60분, B는 7시간 간격을 두고, 발행 뒤 전력을 교란해도 특징이 같은지 확인한다. `powerguard/cv.py:12-24`, `tests/test_leakage.py:30-89`.

### 2. AI 예측모델 개발

- 익일 96구간(B)과 15~60분 앞(A1~A4) 두 예측을 모두 다뤘다. 후보는 기준모델 4~6개와 ML·구조·하이브리드·혼합이다(과제당 12개). `powerguard/registry.py:28-50`.
- 선택 규칙을 미리 고정했다. 교차검증 RMSE 최소 모델을 더 단순한 모델과 날짜 부트스트랩(90%)으로 비교한다. 내 독립 부트스트랩도 같은 결론이다: B M8−M1 −0.232 [−0.456, −0.028], A M8−M7c −0.072 [−0.144, 0.005], A M7c−M1 −0.351 [−0.525, −0.189]. `powerguard/stage_models.py:111-174`.
- 부트스트랩 난수·반복 수를 바꿔도 선택이 거의 같았다(A는 난수 20개 중 19개와 20,000회에서 M7c, B는 20/20). `outputs/cv/selection_robustness.csv`.
- 시험 성능을 내 정답 마스크로 다시 계산해 모든 모델·과제에서 소수 넷째 자리까지 일치했다. A의 선택모델은 지속성 대비 46~61%, 릿지 대비 4.6~4.8% 낮다(차이의 90% 구간이 모두 0보다 작음). `outputs/analysis/test_bootstrap.csv`.
- 확률 모델을 따로 세웠다. 다음 1시간 최대 초과확률을 지평 결합 잔차 표집으로 만들고, 교차검증 Brier로 방법을, 교차검증 ECE로 보정 여부를, 교차검증 F1로 문턱을 골랐다. `powerguard/peak.py:105-137`, `powerguard/stage_peak.py:371-404`.
- 시험 확률 품질이 기준보다 낫다. BSS 0.19 [0.08, 0.29], PR-AUC 0.757 vs 0.572, ECE 0.013(재계산 일치). 가동 창(전면 가동일 8~16시) 안에서만 봐도 PR-AUC 0.81 vs 기후값 0.58이다(내 추가 계산). `outputs/peak/next_hour_classification.csv`, `outputs/figures/13_reliability_next_hour.png`.
- 사후 변경을 방향표로 공개했다. 시험에 유리한데도 교차검증을 악화시킨 변경은 기각했다(전날 체제 키, LightGBM 격자 최선, 시험 최선 모델 교체). `README.md:63-74`, `outputs/analysis/ablations.csv:26`.

### 3. 영향요인 및 오류분석

- 피크 조건을 오즈비로 정량화했다. 기동 8시대 2.77 [1.95, 4.07], 냉방도 1도당 1.38 [1.23, 1.56], 기동×냉방도 상호작용 1.27 [1.08, 1.52]. `outputs/analysis/peak_logit_odds.csv:2-8`.
- FN/FP 집중 조건을 운영 창별 미탐률·오경보율·점유·lift로 냈다. 시험에서 주간조 종료 17시 미탐률 0.91, 16~19시 미탐률 0.74(FN의 18%), 13~15시가 FP의 41%다. 내 재계산으로 시각대별 FN/FP 수가 모두 같았다. `outputs/analysis/peak_alarm_error_conditions.csv`.
- 시험 역전을 날짜로 분해했다. 8/16이 M8−BL3 SSE 차이의 50.3%이고(재계산 0.5026), 상위 4일을 빼면 두 모델이 10.91 vs 10.83으로 같다. `outputs/analysis/test_inversion_days.csv:2-5`.
- 계획 정보가치 사다리(L0~L3)로 입력별 기여를 분리했다. 달력만 41.6 → 일 체제 13.7 → 시간별 생산량 11.9(B, M1). `outputs/analysis/plan_information_value.csv:2-9`.

### 4. 현장 활용방안

- 요금적용전력 규칙(12·1·2·7·8·9월 최대)을 반영해 "15분 몇 개가 1년 기본요금을 정한다"를 사다리로 보였다(상위 1건 차단 −1.8%, 6건 −4.5%). 월 최대 199/222/222/218/204는 원본으로 재계산해 일치했다. `outputs/field/ratchet_ladder.csv`, `billing_ratchet.json`, `outputs/figures/15_integrated_ratchet.png`.
- 경보 등급이 관측 초과율과 잘 맞는다(시험 정상 1.1%, 주의 32%, 경계 59%, 심각 89%). 등급마다 조치·담당·점검 항목이 있다. `outputs/field/alarm_grades.csv:6-9`.
- 운영 절차가 시점·입력·판단 규칙·조치·담당·KPI로 짜여 있다(D-1 17시, 07~09시, 매 15분, 15분 창, 월중). `outputs/field/operating_procedure.csv:2-6`.
- 모델 기반 조치와 규칙 기반 조치를 같은 표에서 비교하고, 모델이 못 이긴 결과도 그대로 냈다. `outputs/field/demand_controller.csv`, `integrated_scenario.csv:7-10`.

### 5. 창의성·차별성

- 데이터 복제 포렌식과 원본 판정(정합성·자정 연속성·McNemar)이 독창적이다. `powerguard/data.py:96-163`.
- 유사일 기준 + LightGBM 잔차 보정 하이브리드, 냉방 특징 단조 제약, 계획 정지 게이트로 제조 지식을 모델 구조에 넣었다. `powerguard/models.py:282-321,455-497`.
- 예측구간을 시간 국소 split conformal·Mondrian(가동 주간/그 외)·ACI로 만들었다. 가동 주간 포괄률이 전역 0.61에서 Mondrian 0.80으로 오른다. `powerguard/peak.py:31-80`, `outputs/peak/interval_coverage.csv:7,15`.
- 외부 KAMP #41이 본 자료(#27)의 파생임을 행 대응으로 밝혀 외부 검증에서 뺐다(R² 0.965, 생산 상관 0.99998). `outputs/external/external_summary.json`.
- 복제를 모르는 "흔한 절차"의 반사실 결과를 같이 냈다. `outputs/analysis/naive_protocol.csv`.

### 6. 코드 및 재현성

- `run_all.py` 한 명령으로 진단→학습→추론→분석→현장→그림→핵심 수치를 만든다. 단계 선택과 실행 기록(코드 지문 포함)이 있다. `run_all.py:61-174`.
- 추론 전용 단계가 모델 파일 SHA-256을 확인하고 학습 때 예측과 비교한다. `powerguard/stage_predict.py:43-62`.
- 처음부터 다시 학습해도 동결값 98/98, 시험 예측 SHA-256, 저장 모델 목록(파일별 SHA 포함)이 바이트 단위로 같았다. README의 전체 명령(`run_all.py` → `verify.py --require-fresh`)도 그대로 통과했다(⑥ 7·9번).
- 제출 ZIP 생성기가 파일별 SHA-256 목록을 넣고 작업 기록을 뺀다. 풀어서 추론·검증이 됐다. `make_submission.py:25-30,51-56`.
- 식별 정보(소속·이름·경로)가 제출 파일에 없었다(grep 확인).

---

## ④ 지금 자료로 고칠 수 있는 결함

P0(결론을 뒤집는 사실 오류·핵심 재현 실패): **없음.** 헤드라인 수치는 모두 원본과 제출 예측으로 다시 계산해 일치했고, 학습부터 재현도 됐다.

### P1 — 해석에 실질적 영향

| # | 위치 | 문제 | 할 일 |
|---|---|---|---|
| P1-1 | `outputs/key_numbers.json`(test_skill_chosen, test_regression), `powerguard/stage_analysis.py:699`, `powerguard/stage_digest.py:70-83` | B 헤드라인 "최선 기준 대비 7.9%"는 교차검증 기준 BL5 대비다. 시험에서는 BL3 프로파일이 RMSE로 유의하게 낫다(M8−BL3 +1.68 [0.30, 3.04]) | 헤드라인에 "시험 최선 기준(BL3)보다 RMSE 13.7% 나쁨, 일 최대 오차는 2.15 [0.63, 3.66] 좋음"을 함께 적는다. B의 가치를 RMSE가 아니라 일 최대·피크 지표로 주장한다. 구조 기준을 같은 폴드로 맞추면 규칙이 BL5를 고른다는 점(README 방향표에만 있음)도 선정근거 옆에 적는다 |
| P1-2 | `outputs/key_numbers.json`(test_regression), `README.md:57-60` | 사후 게이트 전 수치(B 20.94, M1 32.22, A4 M1 14.30)가 별도 블록에만 있다 | 헤드라인 표의 같은 줄에 "사전 규칙(게이트 없음)" 열을 두고, 게이트가 바꾼 날짜(평일 정지 5일)의 기여를 따로 적는다 |
| P1-3 | `outputs/field/operating_procedure.csv:2,4`, `integrated_scenario.csv` | 절차 5단계 중 두 단계(D-1 위험일 표시, 매 15분 차단)가 모델 확률을 쓴다. 시험에서는 모델 기반 차단이 같은 개입 수준의 반응형 규칙과 같고(8월 215), 래칫 위험일 재현율이 0이다. 통합 절감은 규칙 조치에서 나온다 | "규칙만(인터록+순차 기동)" 행을 기준으로 AI의 추가 기여를 따로 표기한다. 모델 기반 단계는 채택 조건을 달거나 보조 정보로 낮춘다 |
| P1-4 | `outputs/key_numbers.json`(peak.test_classification) | 확률 경보 헤드라인 F1 0.694는 기후값 F1 0.695와 같다 | 주 지표를 BSS·PR-AUC·신뢰도로 바꾸고, F1은 기후값 동률임을 함께 적는다 |

### P2 — 국소 결함

| # | 위치 | 할 일 |
|---|---|---|
| P2-1 | `powerguard/config.py:1`, `stage_models.py:113`, `tests/test_data.py:1`, `README.md:61,71,74`, `stage_field.py:814` | 제출에서 빠지는 PLAN.md와 검수 차수 참조를 지우거나 README 안의 설명으로 바꾼다 |
| P2-2 | `outputs/key_numbers.json`(196 KB) | "핵심 수치" 파일이 너무 크다. 헤드라인 10~15줄 요약을 따로 둔다 |
| P2-3 | `README.md:63-74` 방향표 | A 선택 역전(시험에서 M1이 M7c보다 0.42 [0.03, 0.84] 낮음)을 표에 넣는다 |
| P2-4 | `outputs/analysis/test_skill.csv`(skill_vs_naive) | 비교 기준 BL2는 체제를 무시해 휴가 주간에 크게 틀린다. 체제 인지 기준 대비를 주 비교로 쓴다 |
| P2-5 | `outputs/peak/interval_coverage.csv:17` | 피크 구간 과소 포괄(0.69/0.80)을 헤드라인에 적고, 피크 층 보정 여부를 검토한다 |
| P2-6 | `outputs/field/alarm_burden*.csv` | 운영 문턱을 T=182와 T=210.9 중 하나로 정해 절차에 쓰고, 선택한 문턱의 시험 판별력 한계를 적는다 |
| P2-7 | `powerguard/stage_figures.py` | 한글 굵은 글꼴 경고(AppleGothic bold 없음)가 난다. 글꼴 폴백을 정한다 |
| P2-8 | `verify.py:146-185` | 비교 파일 중 이번 실행에서 다시 만들지 않은 파일 수를 기본 모드에서도 표시한다. 그림은 해시로 확인한다 |

---

## ⑤ 고칠 수 없는 자료 한계

- 실측은 약 4.5개월(5/1~9/14)뿐이다. 1~4월은 복제라 계절 변화와 동계 래칫 월(12~2월)을 관측할 수 없다.
- 시험에 학습에 없던 체제가 있다. 평일 휴가 정지 5일(8/2~8/6), 대체공휴일 가동(8/16), 휴가 뒤 월요일. 교차검증으로 대표할 수 없다.
- 설비·제품 단위 부하, 전력 단위, 계획과 실적의 구분이 없다. 절감량의 원화 환산과 인터록·순차 기동·사전 냉방 효과를 검증할 수 없다.
- 시험 45일, 요금 목표 초과 구간 9개로 표본이 작다. 경보·래칫 평가의 구간이 넓다.
- 기상은 실측값이다. 예보오차는 모의로만 볼 수 있다.
- 가동 체제가 전날 확정된다는 가정은 자료로 검증할 수 없다(가이드 정의와는 맞는다).

---

## ⑥ 직접 수행한 검증

작업 사본: `/private/tmp/p1_power_OwPnAJ`(끝나고 삭제 완료). 가상환경: Python 3.12.2 + requirements.txt 고정 버전(numpy 2.5.3, pandas 3.0.6, scikit-learn 1.9.1, lightgbm 4.7.0, shap 0.52.0, scipy 1.18.1, matplotlib 3.11.2). 모든 실행에 `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1`. 저장소 안에서는 아무것도 실행하지 않았다.

| # | 명령·스크립트 | 결과 | 시간 |
|---|---|---|---|
| 1 | `git -C <repo> log -1 --format=%H` | 시작·끝 모두 `d5a3446f…`(변경 없음) | — |
| 2 | 사본 만들기(`git archive … ':(exclude)PLAN.md' ':(exclude)reviews'`), CSV·artifacts 복사 | CSV SHA-256 `8f7af2e4…` = 공식 ZIP 내용 = config 값 | 수 초 |
| 3 | `pip install -r requirements.txt` (새 venv) | 설치 성공(libomp는 이미 있음) | 약 2분 |
| 4 | `run_all.py --stages predict` | 48개 모델 SHA 확인, 모든 과제 최대 차이 ≤5e-5 통과(A4 반올림 경계 296행은 README 설명대로) | 28.8초(첫 실행), ZIP 사본 2.9초 |
| 5 | `python -m pytest -q tests` | 70 passed | 11초 |
| 6 | `run_all.py --stages predict,peak` → `verify.py` | 시험 예측 SHA `d8e791d1…` 일치, 98/98, `--require-fresh`는 설계대로 실패 | 54초 |
| 7 | `run_all.py --stages diagnostics,models,predict,peak,analysis,field,external,figures,digest --kamp-dir <데이터셋>` → `verify.py` | 처음부터 재학습. 98/98, 시험 예측 SHA 일치, 모델 목록 `manifest.json` SHA `efa3d8d3…`가 제출본과 같음(모델 파일 바이트 일치) | 751초(models 510초) |
| 8 | `make_submission.py --with-external` → 풀기 → `SHA256SUMS` 확인 → `--stages predict` → `verify.py` | 320개 파일 21.4 MB, PLAN·reviews 없음, SHA 전부 OK, 추론 통과, 98/98, `--require-fresh` 설계대로 실패 | 1분 이내 |
| 9 | 전체 `run_all.py --kamp-dir <데이터셋>`(ablation 포함) → `verify.py --require-fresh` | 종료 코드 0. `verify.py --require-fresh` 통과: 98/98, 시험 예측 SHA 일치, 신선도 확인 통과. ablation 산출물(게이트 전후 B 20.94→13.98, 체제 오류, 반사실 절차, 학습 창 등)도 동결값과 같음. 모델 목록 SHA 다시 일치 | 4,167초(ablation 3,368초, models 550초) |
| 10 | `p1_independent_check.py`(팀 코드 import 없음) → `p1_independent_check.json` | 아래 표 | 8초 |

**독립 재계산 결과(10번)**

| 항목 | 팀 값 | 내 값 | 판정 |
|---|---|---|---|
| 날짜·고유 패턴·복제일 | 257 / 142 / 115 | 257 / 142 / 115 | 일치 |
| 손상일 | 7/13, 7/15 | 7/13, 7/15 | 일치 |
| 시험 평가 구간(0 전력 제외) | 4,246 | 4,246(0 전력 74) | 일치 |
| 피크 기준 T(5~7월 q95) | 182 | 182(7/9 포함·제외, 복제 제거 전후 모두) | 일치 |
| 시험 RMSE, 전 모델·5과제 | test_metrics.csv | 소수 넷째 자리까지 같음(예: B M8 13.9759, BL3 12.2948, A1 M7c 6.9816) | 일치 |
| 교차검증 pooled RMSE | B M8 9.9353, A1 M7c 6.8907 | 같음(7/30 제외 58일) | 일치 |
| 선택 단계 부트스트랩 | selection.json | 같은 부호·유의성(②-(c), ③-2 참고) | 일치 |
| 독립 기준모델(B, 시험) | — | 7일 전 같은 슬롯 59.7, 요일유형3 프로파일 42.9, 체제×요일유형3 17.5, 체제×요일유형4(주간 재학습) 12.30 | BL3 12.29를 독립 구현으로 재현 |
| M8−BL3(B, 시험) | +1.68 [0.30, 3.04] | +1.68 [0.32, 3.04] | 일치 |
| 일 최대 MAE(B, 시험) | M8 7.79, BL3 9.94 | 7.80 / 9.94 | 일치 |
| 8/16의 SSE 차이 점유 | 0.5026 | 0.5026 | 일치 |
| 다음 1시간 경보(시험, τ=0.5) | F1 0.694, Brier 0.0504, PR-AUC 0.757, ECE 0.0129, BSS 0.188 | 0.694 / 0.0504 / 0.757 / 0.0129 / 0.1885, 라벨 불일치 0/4,236 | 일치 |
| 기후값·분류기·시각 규칙 F1(시험) | 0.695 / 0.681 / 0.663 | 0.695 / 0.681 / 0.663 | 일치 |
| 시각대별 FN/FP(시험) | peak_alarm_error_conditions.csv | 8개 시각대 모두 같음 | 일치 |
| 월 최대(5~9월) | 199/222/222/218/204 | 199/222/222/218/204 | 일치 |
| 래칫 사다리 상위 날짜(7~9월) | 7/19 222, 8/11 218, 7/26 217, 8/9 215, 7/21 214, 7/22 213 | 같음 | 일치 |
| 경보 등급 관측 초과율(시험) | 정상 1.1%·주의 32%·경계 59%·심각 89% (n 3335/354/386/161) | 같음(38/115/229/143건) | 일치 |

산출 파일: `p1_independent_check.py`, `p1_independent_check.json`, `p1_logs.txt`(실행 로그 발췌). 재실행: `python p1_independent_check.py "<데이터셋>/Dataset_자원 최적화 AI 데이터셋.zip" <power_submission/artifacts> <출력.json>`.

총 작업 시간: 약 1시간 30분(00:34~02:04). 무거운 실행은 한 번에 하나만 돌렸다. 작업 사본·가상환경(733 MB)은 끝나고 삭제했다. 제출 폴더에는 시작 뒤 바뀐 파일이 없다(find로 확인).
