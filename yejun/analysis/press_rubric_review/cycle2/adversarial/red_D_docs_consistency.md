# 적대적 검수 D — 문서·수치 정합과 과장

- 기준 커밋: `cc1aac2`. 대상 문서의 작업 사본은 모두 이 커밋과 같다(`redD_extract_claims.log`).
- 방법: 문서와 커밋된 산출물(CSV·JSON·저장 모델 JSON)만 읽어 대조했다. 팀의 생성 스크립트는 실행하지 않았다.
- 이 문서는 검수 기록이며 대회 보고서가 아니다.
- 경로는 `yejun/` 기준이다. `round4/`는 `analysis/press_rubric_review/cycle2/round4/`이다.

## ① 결론 요약(심각한 것부터)

1. **D-01 중대 — 주 지표 선언과 헤드라인이 어긋난다.**
   - 문서는 "구간 단위가 주 지표"라고 쓴다.
   - 그러나 v2의 개선은 행 단위에서만 나타난다. 행 단위 미탐 합은 v2 선정의 목적함수이기도 하다.
   - 구간 단위(21/21, 0/120, 3/180)에서는 v1과 v2가 같다.
   - 미탐 감소의 약 90%는 기록 시작 0.2~0.6초(위치 2~6)에서 나온다.
2. **D-03 보통 — A 문턱 설명이 틀렸다. A·B 결과가 같은 기록에 의존한다.**
   - A의 α1% 문턱 4.418과 2위 4.049는 보정 구간의 기록 461·423에서 나왔다. 이 둘은 B 오경보 3건 중 2건과 같은 기록이다.
   - 오류 조건표는 A 문턱이 높은 이유를 "A 평가 구간이 조용해서"라고 적는다.
3. **D-02 보통 — 「조기」와 지연 수치에 기준이 빠졌다.**
   - README 결과(최대 첫 경보 0.5초, 2단계 0.2·0.6초)는 기록 시작 기준이다. 고장 발생 기준이 아니다.
   - README에는 이 기준이 적혀 있지 않다. 대회 자료에는 고장 시작 시각이 없다.
4. **D-05 보통 — E2 외부 자료 실패가 축소됐다.**
   - 최종 README는 E2(AUROC 0.43~0.55)를 "느린 누설에는 약하다"로 줄여 쓴다.
   - 콘솔의 「외부 데이터 검증」 탭은 다른 모델(공분산 모델)의 결과만 보인다.
5. **D-06·D-07 보통 — 재현성 문구가 근거보다 세거나 낡았다.**
   - README는 Windows 실행을 단정하지만 실측은 macOS arm64뿐이다.
   - README의 재현 시간(9.5분·572초·651초)은 이전 구현 값이다. 최종 실측은 803.6초(15단계)·893.4초(24단계)다.
   - 현재 구현 시간을 적었다는 `reproduce_summary.json`은 커밋·제출 목록에서 빠진다.
6. **D-04 보통 — 2회차 설계 변경(기록 경계 ±20 ms)이 결정표에 반영되지 않았다.**
   - 결정표에는 아직 "1e-6 현행 유지"가 적혀 있다.

수치 자체는 대체로 정확하다. 정보가 있는 수치 토큰 933개 중 929개가 커밋 산출물 값과 맞았다. 핵심 수치의 손 대조와 파일:행 인용 대조에서도 어긋남은 D-13의 인용 1건뿐이다. 문제는 값이 아니라 해석·범위·기준·낡은 문장이다.

## ② 지적 표

| ID | 심각도 | 종류 | 내용 | 증거 | 팀 공개 여부 | 주장·점수에 미치는 영향 | 권고 조치 |
|---|---|---|---|---|---|---|---|
| D-01 | 중대 | 모순·점수 부풀림 | ① 문서마다 주 지표를 다르게 선언한다: v1 README와 진단 README는 "구간 단위", 결정표는 "행 F1과 구간 단위를 함께", 최종 README는 행 F1을 굵게 헤드라인으로 둔다. ② v2의 개선은 행 단위(미탐 행·행 F1)에서만 나타난다. 선정 목적함수가 곧 이 값이다: "두 분할 미탐 합 최소". ③ 구간 단위에서는 v1과 v2가 같다: 이상 21/21, 정상 알림 0/120·3/180, 기록구간 AUROC 1.0(포화), 기록구간 F1 A 1.000·B 0.933. ④ 미탐 감소 55행 중 A 49행·B 51행(약 89·93%)이 위치 2~6이다. 위치 2~6은 5초 간헐 수집에서 기록이 다시 시작된 직후 0.2~0.6초다 | `press_submission/README.md:34`, `analysis/press_evidence/README.md:47`, `analysis/press_evidence/decision_table_diagnosis_v2.csv:2`(decision 열), `press_guard/README.md:47-52`, `press_guard/outputs/metrics.csv:2-3,8-9`, `analysis/press_selection/README.md:179-184`, `analysis/press_selection/selection_evidence.csv:8`, `press_guard/web/index.html:17` | 공개됐지만 멀리 떨어짐: 포화는 press_selection에, 이득 위치는 웹 잔글씨에만 있다. 최종 README 결과 절에는 없다 | "v2가 v1보다 낫다"를 "기록 시작 직후 0.2~0.6초의 이상 행을 더 잡는다"로 좁혀야 한다. 연속 스트림에서는 기록 재시작이 드물다. 따라서 이 이득의 현장 크기는 산출물로 확인되지 않는다(추론). 모델 개발(40점)의 핵심 주장이다 | 주 지표 문장을 하나로 통일한다. README 결과 표 옆에 "구간 단위 동일, 이득은 위치 2~6"을 적는다 |
| D-02 | 보통 | 과장·누락 | ① README 제목·첫 문장은 "조기 경보"다. ② 결과 표 "최대 첫 경보 지연 0.5초"와 2단계 "지연 중앙 0.2초, 최대 0.6초"는 기록 시작 기준이다. ③ 21구간은 이미 진행 중인 3분 한 에피소드의 5초 조각이라 고장 대비 선행시간은 잴 수 없다. ④ README에는 이 기준이 없다. ⑤ 발생 시각을 아는 E1 지연(하한 조건 0.6·0.4초)도 README 결과에 없다 | `press_guard/README.md:1,3,49-52,60`, `press_guard/web/index.html:17,19`(기준은 잔글씨에만), `analysis/press_evidence/guidebook_protocol_vs_records.csv:5`("선행시간을 주장하지 않는다"), `analysis/press_supplement/README.md:17-20` | 공개됐지만 멀리 떨어짐(웹·결정표). 최종 README에는 없음 | "조기탐지" 과제명에 대한 답이 대회 자료만으로는 입증되지 않는다. 심사위원은 0.5초를 선행시간으로 읽을 수 있다 | 표 아래에 "지연은 기록 시작 기준, 고장 발생 시각 없음, 발생 시각을 아는 지연은 E1 주입"이라고 한 줄 적는다 |
| D-03 | 보통 | 모순(잘못된 설명)·의존 | ① 오류 조건표의 limitation은 "A 평가 구간은 조용한 시간대라 문턱(max\|z\| 4.49)이 B(3.77)보다 높다"라고 적는다. ② 그러나 문턱은 보정 구간의 최대 점수로만 정해진다. ③ 저장 모델 `guard_A.json`의 `state.calibration` 상위 2개(4.418, 4.049)는 보정 위치 101·63, 즉 기록 461·423이다(A 보정 = 360~479). ④ 이 둘은 B α1% 오경보 423·461과 같은 기록이다. B 보정 상위 2개는 기록 303·301이다(3.52, 3.51). ⑤ 결론: A는 그날 가장 튀는 부하 기록 2개로 문턱을 올렸고, B는 같은 기록을 평가에서 오경보로 셌다 | `press_guard/outputs/error_condition_summary_v2.csv:8`(limitation), `press_guard/insights.py:1179`, `press_guard/README.md:35,54`, `press_guard/artifacts/guard_A.json`·`guard_B.json`(`state.calibration`, `redD_targeted_checks.log` 3절), `press_guard/outputs/incidents_B.csv:2-4`, `analysis/press_selection/README.md:105` | 부분 공개: press_selection:105는 문턱이 "단발 크기 급등"에서 나왔다고만 쓴다. 기록 번호와 B 오경보와의 동일성은 공개 안 됨. README:54는 A 0/120의 유리함을 평가 구간이 조용하다는 이유로만 설명한다 | A 0/120은 두 가지 유리한 조건이 겹친 값이다: 조용한 평가 구간, 그리고 가장 시끄러운 두 기록을 포함한 보정 구간. A·B 결과는 서로 독립이 아니다 | limitation 문장을 고친다. README:54에 "A 문턱은 보정 구간의 기록 461·423(B 오경보와 같은 기록)이 정했다"를 더한다 |
| D-04 | 보통 | 모순·낡은 문장 | 결정표 "기록구간 규칙"은 "\|Δt−0.1초\|>1e-6이면 새 구간 … 현행 규칙 유지"라고 적는다. 그러나 v2 코드는 `TIME_TOL_S = 0.02`이고 README도 ±20 ms라고 적는다(2회차 변경). 결과(600/21구간)는 두 규칙에서 같다 | `analysis/press_evidence/decision_table_diagnosis_v2.csv:4`, `press_guard/model.py:42-43`, `press_guard/README.md:32`, `analysis/press_evidence/segment_rule_tolerance.csv:2-7` | 공개 안 됨(불일치 자체) | 진단→전처리 결정표(데이터 진단 15점의 핵심 근거)가 최종 모델과 다른 규칙을 적는다 | 결정표 문구를 ±20 ms로 고치고 1e-6은 v1 규칙으로 표시한다 |
| D-05 | 보통 | 과장(축소)·누락 | ① E2에서 v2 구조는 UCI 펌프 누설에 AUROC 0.43~0.55(무작위 수준)로 실패했다. ② 최종 README는 이를 "느린 누설에는 약하다(E1·E2)"로 줄여 쓴다. ③ 콘솔 「외부 데이터 검증」 탭은 다른 모델(press_external 공분산 모델, 현지 기준 F1 최대 1.0)의 결과를 "다른 환경에서 확인한 성능과 실패 조건"으로 보인다. ④ 최종 모델 구조의 실패는 탭에 없다 | `press_guard/README.md:219`, `analysis/press_supplement/README.md:8,44-57`, `press_guard/web/index.html:8,27`, `press_guard/web/app.js:687-695` | 공개됐지만 축소됨. 전체 실패는 press_supplement와 결정표에 공개됐다 | 콘솔만 본 사람은 외부 검증이 성공했다고 오해할 수 있다 | 탭 제목을 "외부 자료: 다른 모델 참고·v2 구조 실패"로 바꾸고 E2 표를 함께 보인다. README 한계에 "E2 실패(AUROC 0.43~0.55)"를 명시한다 |
| D-06 | 보통 | 과장 | README는 Windows 실행을 사실로 적는다: "PowerShell에서도 같은 명령이다… CP949 콘솔에서도 멈추지 않는다". 실측은 macOS arm64뿐이다. CP949는 macOS 위 모의 시험이다 | `press_guard/README.md:24`, `round4/judge_06_repro.md:122`, `press_guard/outputs/manifest.json`(platform macOS), `press_guard/requirements-lock.txt:1` | 최종 README에서는 공개 안 됨. v1 README:82에는 "다른 OS 검증은 수행하지 못했다"가 있다 | 재현성(10점)에서 심사 환경이 Windows면 문구와 실제가 다를 위험이 있다 | "Windows 미실측(인코딩 모의 시험만)"을 같은 줄에 적는다 |
| D-07 | 보통 | 낡은 문장 | ① README의 재현 시간은 이전 구현 값이다: "15단계 약 9.5분(572초)", "--tests 651초(기존 구현 실측)". ② 같은 커밋의 최종 실측은 15/15단계 803.6초, 24/24단계 893.4초다(동시 부하 있음). ③ README는 현재 시간을 `reproduce_summary.json`에서 보라고 하지만, 이 파일은 커밋되지 않고 제출 목록에서도 빠진다. ④ `reproduce.py` 머리말에는 "약 10분"이 남아 있다 | `press_guard/README.md:21`, `round4/package_copy_final.log:32`, `round4/judge06_final_repro.log:52`, `press_guard/tools/package_manifest.py:56`(EXCLUDE), `press_guard/reproduce.py:3` | 공개 안 됨 | 제출 문서만으로는 현재 구현의 실측 시간을 알 수 없다 | 최종 실측(약 13~15분, 부하 조건 포함)을 README에 적는다 |
| D-08 | 보통 | 과장 | ① OPERATIONS 0단계는 "α=1%면 최소 174단위(학습 15·보정 99·수락 60)"를 운영 요구로 쓴다. ② 99는 산식 하한이다. 그러나 학습 15는 E3의 사후 탐색값이다. ③ E3의 사전 안정 규칙을 만족한 설정은 36개 중 0개였다. 15+99에서는 문턱이 3.1~5.2로 흔들렸다. ④ press_supplement는 이 값을 "검증된 최소 수집량으로 쓰지 않는다"고 적는다 | `press_guard/OPERATIONS.md:14`, `analysis/press_supplement/README.md:9,72,74-75`, `analysis/press_supplement/e3_stability.csv:2` | OPERATIONS 해당 줄에서는 공개 안 됨. press_supplement에는 공개됐다 | 현장 절차가 사후 탐색값을 최소 요구처럼 제시한다 | "학습 15는 같은 날 사후 탐색값, [가정]"을 붙인다 |
| D-09 | 보통 | 점수 부풀림·결함 | ① 부모 집계(평가관·루브릭·사이클2) 밖에도 내부 표기가 제출 문서에 남아 있다. ② press_submission README: R2·R3·R4·R6, "Claude 2차 보완과 Codex 재검수", "최신 Codex 재검수", "예준의 명시적인 보고서 작성 시작 지시". ③ press_evidence README: 절 제목 R1~R22·D1~D6·O1(a)·O4·R2-D1~R2-O11, 본문 "2회차". ④ press_selection README: 절 제목 M3·O3·E7·M4·M5. ⑤ `selection_evidence.csv`는 제출 목록에서 빠지는 `judge_02_model.md`를 출처로 인용한다(끊긴 인용). ⑥ 평가관 06의 "문서·lock 내부 검수 표기 0"은 정규식과 대상이 좁아서 나온 값이다: 정규식은 루브릭\|사이클2\|평가관\|press_rubric_review\|press_implementation_review, 대상은 .md와 lock뿐 | `press_submission/README.md:72-76,81,83`, `analysis/press_evidence/README.md:20-98,132,179,243,279-324`, `analysis/press_selection/README.md:16,36,86,154,170`, `analysis/press_selection/selection_evidence.csv:3,44,45`, `analysis/press_supplement/README.md:125`, `round4/judge_06_repro.md:28`, `round4/judge06_final_checks.py:99-103` | 공개 안 됨 | 블라인드 위반은 아니다(성명은 허용). 그러나 심사위원에게 내부 검수 흔적과 끊긴 출처로 보인다. 평가관 06의 해당 판정은 과대평가다 | 제출용 문서에서 내부 ID·도구명·작업 지시를 걷어낸다. 표의 출처를 제출 파일로 바꾼다 |
| D-10 | 경미 | 낡은 문장 | 같은 절 안에서 보강 표 개수가 셋으로 다르다: "표 16개(보강 2의 표 4개는 별도)" = 20, "표 22개·그림 5장", "산출물 25개(표 20·그림 5)". 실제 산출물은 표 22·그림 5 = 27개다 | `analysis/press_evidence/README.md:106,110,114`, `analysis/press_evidence/diagnostics_manifest.json`(outputs 27) | 공개 안 됨 | 문서 신뢰 저하 | 22·27로 통일한다 |
| D-11 | 경미 | 낡은 문장 | press_selection은 2단계를 "건 안의 경보 행 2개 이상이면 점검 요청"으로 적는다. 현재 규칙은 사건 안 누적 경보 2행이다 | `analysis/press_selection/README.md:151`, `press_guard/README.md:37`, `press_guard/OPERATIONS.md:17` | 공개 안 됨 | 사건 단위 변경의 미반영 | 문구를 고친다 |
| D-12 | 경미 | 결함(근거 없는 수치) | ① press_supervised README의 수치 가운데 커밋 산출물에 없는 값이 있다(grep 0건): 21겹 문턱 0.248~0.997, 기록 2를 뺀 겹의 문턱 0.990·미탐 47행, 다른 특징 구성 0.9601·0.9574·0.9709·0.9673. ② `grouped_records.csv`의 `threshold_value`는 21겹 행에도 값 하나만 적는다(A 창+v2 부스팅 0.640870, 3겹과 같은 값). 실제 겹별 문턱이 아니다 | `analysis/press_supervised/README.md:37-38`, `analysis/press_supervised/grouped_records.csv:33,36` | 공개 안 됨 | 재현·대조 불가 수치 | 겹별 문턱을 표로 남기거나 문장을 뺀다 |
| D-13 | 경미 | 단위·인용 | ① 오류 조건표 9·10행의 `errors_A`·`errors_B`는 분할 값이 아니다. 9행은 α 1%·5%, 10행은 서로 다른 구성비(AI0 단독 15/17, 경보 1행 13/17)를 담는다. limitation에는 공개됐다. ② 결정표는 시간 적용률 43.3%·36.2%의 출처로 `gaps.csv:3`을 가리키지만 그 행에는 적용률 열이 없다. 값은 `diagnosis.md:11`에서 유도된다 | `press_guard/outputs/error_condition_summary_v2.csv:9-10`, `analysis/press_evidence/decision_table_diagnosis_v2.csv:7`, `analysis/press_evidence/gaps.csv:3`, `press_submission/outputs/diagnosis.md:11` | ①은 공개됨(limitation), ②는 공개 안 됨 | 기계 판독 오독, 인용 불일치 | 열을 분리하고 인용을 고친다 |
| D-14 | 경미 | 표기 | ① README:180은 "9개 조건"이라고 쓰지만 본문은 7개만 열거한다. B α3% 전류 잡음 0.1σ 1건·오프셋 0.4 1건이 빠졌다(인용 행에는 있다). ② OPERATIONS는 "12.7건"을 서로 다른 두 양에 쓴다: 1/9 상한 12.696, α5% 3/7 점추정 12.679 | `press_guard/README.md:180`, `press_guard/outputs/queue_injection_ranks_v2.csv:83,91`, `press_guard/OPERATIONS.md:40` | — | 읽는 사람 혼동 | 열거를 보충한다. 소수 둘째 자리나 이름을 붙인다 |

### ②-1 공식 요구와의 대응

| 평가 항목(배점) | 요구 핵심 낱말 | 답하는 위치 | 판정 |
|---|---|---|---|
| 1 데이터 이해·진단(15) | 생산단위, 변수 의미, 시간·설비·제품 관계, 결측·중복·이상치·불균형, 전처리·검증전략 | `analysis/press_evidence/README.md` R2(변수 사전)·D4(생산단위)·R3(불균형·이상치)·R20(중복)·D3 결정표, v1 `diagnosis.md` | 내용은 직접 답한다. 「제품」은 식별 열이 없다고 답한다(`press_evidence/README.md:42`). 약점: 최종 README에서 이 문서로 가는 링크가 없다(`press_guard/README.md`에 `press_evidence/README.md` 링크 0개). 절 제목이 내부 ID다. D-04 결정표 불일치도 있다 |
| 2 AI 예측모델(40) | 제조 이상 확률 예측, 베이스라인 포함 2개 이상 비교(F1), 선정 근거 | README 결과 표, `outputs/model_comparison_v2.md`(14모델), `press_selection/README.md`, README 이상 확률 절 | 비교와 선정 근거는 답한다. 약점 ①: README 결과 표는 팀의 v1·v2만 보인다. 가이드북 LSTM·IF 등 기준선은 산출물 목록에서 이름으로만 가리킨다(`README.md:187`). 약점 ②: 「이상 확률」의 답이 약하다. π 1%에서 이상 행 A 555/600·B 568/600과 B 오경보 3/3이 모두 상한 0.55다(재계산 일치). 그래서 경보 사이의 확률 순위는 거의 없다. README가 이를 정직하게 공개한다(`README.md:106-113`). 약점 ③: D-01 |
| 3 영향요인·오류분석(15) | 주요 영향변수, 변수 간 상호작용, FN·FP 집중 공정조건 | README 「영향변수와 상호작용」, 12행 오류 조건표 | 영향변수는 재적합 절제·채널 교체로 직접 답한다. 상호작용은 에둘러 답한다: 모델 안 곱 항이 없어 오류 쪽 사후 층화로 보이고, A 진동 효과는 Bonferroni에서 비유의다(`README.md:138-142`). 공정조건은 자료에 없어 신호 대리변수로 답한다(공개됨) |
| 4 현장 활용(10) | 사전경보, 품질검사 우선순위, 공정점검, 작업자 의사결정 | `OPERATIONS.md` 1~9단계, 대기열, 판단표, 품질 조치 | 사전경보·점검·의사결정은 직접 답한다. 「품질검사 우선순위」는 에둘러 답한다: 설비 점검 대기열 순위와 품질 조치 가설(의심 시간창 보류, 샘플 앞당김)이다. 가공품·로트·검사 자료가 없어 검증하지 못했다(`index.html:21`) |
| 5 창의성·차별성(10) | 불균형 학습, 앙상블, 불확실성 추정, 확률보정, 제조지식 결합 | 정상만 학습, conformal·블록 부트스트랩, 등방 보정·LR 표시 상한, FM 대응표·0.6 Hz AR(2) 진동자 | 답한다. 앙상블은 없다(세 성분 fmax). 제조지식은 가설로 표시했다 |
| 6 코드·재현성(10) | 동일 환경에서 전처리→학습→추론→결과 자동 실행 | `reproduce.py` 한 명령, `verify.py` | 직접 답한다. 약점: D-06(Windows 단정), D-07(현재 구현 시간 없음) |

### ②-2 읽기 부담

- **분량**
  - 대상 문서 11개는 2,017행이다.
  - Markdown 문서 8개는 약 148 KB다. 그중 `press_guard/README.md` 31.7 KB, `press_evidence/README.md` 42.5 KB다.
  - 수치가 든 문장은 1,361개, 수치 토큰은 3,842개다.
- **표**
  - 문서 안 Markdown 표는 45개다(README 8개에 41개, `diagnosis.md`에 4개).
  - 커밋된 CSV 표는 137개다(press_guard 42, evidence 39, v1 30, selection 11, supplement 10, supervised 3, advance 2). 동결 사본은 따로 있다.
  - 표 설명 열의 칸은 455개다(`redD_table_notes.csv`).
- **셈 단위 용어**
  - 알림을 세는 단위가 8개다: 행, 기록구간(구간), 알림 단위, 50행 블록, 건, 사건, 창, 폴드.
  - 같은 화면 안에서도 섞인다. 예: `index.html:19` "표는 건 단위, 운영 알림은 사건 단위".
- **심사위원의 경로**
  - 최종 성능은 README 45~63행에서 바로 찾는다. 유리 조건과 표본 내 경고가 표 바로 아래에 있다(좋음).
  - 데이터 진단(15점)은 최종 README에서 링크가 없다. 심사위원이 357행짜리 `analysis/press_evidence/README.md`를 스스로 찾아야 하고, 절 제목은 R1·D1·O4·R2-D1 같은 내부 ID다.
  - 선정 근거는 README 43행에서 한 번 링크된다.
- **내부 표기**
  - 부모 집계: 제출 목록 479개 파일 중 30개에 「평가관」 83번, 「루브릭」 29번, 「사이클2」 21번. `press_submission/evidence/요청사항_준용.md`와 `PROVENANCE.md`에 팀원 이름·도구명.
  - 본 검수의 추가분은 D-09에 적었다. 대상 README에서 내부 ID·도구명·회차 표기가 든 행: press_submission 7, press_evidence 24, press_selection 5, supervised 1, supplement 1.

## ③ 확인했지만 문제없음

| 확인 | 방법 | 결과 |
|---|---|---|
| 문서 수치 토큰 전수 선별 | 문서 10개의 수치 토큰을 커밋 CSV 156개·JSON 34개의 값 176,845개와 반올림 허용으로 대조. 분수는 분자·분모가 같은 표 행에 있는지 대조 | 정보 있는 토큰 933개 중 929개 일치, 분수 196개 중 187개 일치. 나머지 13개는 유도값이나 구간 표기였고(600/20,600, 21/621, 555/600 등) 손 계산으로 맞았다(`redD_pool_screen.log`, `redD_pool_unmatched.csv`) |
| 결과·업무량·2단계 수치의 문서 간 일치 | 손 대조: README·OPERATIONS·`index.html`·`app.js`·`test_web.cjs` | F1 0.961938·0.970990, 미탐 44·31, 0/120·3/180. 명목 30, 관측 60, 상한 152, 사후 44·92건. 2단계 4.2(상한 15.4)·3.3(12.7)·11.8·12.7건, 정상 평가 상한 88·59건. 시간순 5창 F1 0.961938~0.971819, 알림 0·0·2·0·0/60. 모두 산출물과 같다 |
| 사건 단위 | `incident_summary_v2.csv`, `incidents_{A,B}.csv` | 이상 21구간은 사건 1개·알림 2건이다. B α1·3·5%는 사건 3·5·7개, 알림 3·7·10건으로 문서와 같다 |
| 확률 수치 | `probability_eval/conversion/label_free_*` | Brier·ECE 표, 문턱 확률 0.30·0.007, 최소 LR 108.9·2.42, 계단 [2.896, 3.561)·9행 대 1행, 라벨 없는 환산 10.4·53.8·3.7·28.1%, SBB 9.3·8.6%가 일치한다. 상한 행 수 A 555/600·B 568/600, B 오경보 3/3도 재계산이 일치한다 |
| 영향변수·절제·오류 조건표 12행 | `sensor_importance`, `ablation`, `fn/fp_intensity`, `near_miss_corr`, `position_vibration_misses` | 모든 값이 일치한다(BH·Bonferroni·MH OR·CMH·순열 p 포함) |
| 크기 성분 문턱 \|z\| A 4.49·B 3.77 | 행 단위 예측에서 발화 경계 재계산 | A: 비발화 최대 4.444 < 4.49 < 발화 최소 4.677. B: 3.755 < 3.77 < 3.776. 문서가 맞다 |
| 파일:행 인용 | 오류 조건표 13행의 source, 결정표 인용 약 25곳, 고장 모드표의 `e1_summary` 인용 22곳, README:180 인용 9행 | 인용한 행이 주장 값을 담는다. 예외는 D-13의 1건이다 |
| 진단 수치 | `press_evidence` 표 30여 개(블록·상태·전이·전환 스트레스·위상·보정 곡선·품질 지수) | 모두 일치한다. 원본에서 다시 계산한 값도 같다: 정상 600구간, 길이 20 이상 쌍 355개(1.553~8.432초, 중앙 3.046초), 시간 적용률 43.3%, 이상 구간 순서 Spearman 0.011(p=0.97) |
| 수락 검사와 E3의 모순 여부 | `recalibrate.py:16,45` | 수락 검사의 주입 3종은 전류 잡음 0.2σ·오프셋 0.4×·진동 4σ다. 동결 모델도 E1에서 100%라 통과한다. E3 사전 규칙(진동 2σ) 미충족과 모순되지 않는다 |
| 앞 회차 설계 변경의 반영 | README·OPERATIONS·웹 문구·`docs` 그림 2장·콘솔 캡처 5조각 판독 | 사건 단위, 감시 4갈래, 운전 상태(부하·저수준·판정 대기, 91.9), 확률 조건부성이 반영됐다. 예외는 D-04·D-11이다. 콘솔 캡처의 코드 해시가 현재 `web/`·`serve.py`와 같다(`capture.json`) |
| 개수 | `reproduce.py`의 `steps()` 재계산, `audit.json`, `expected/` | 15단계, 23·24단계, 실행 검증 16개, 기대값 CSV 42개, 14모델, press_evidence 결과 44개(표 39·그림 5)가 일치한다 |
| README 한계 절이 알려진 한계를 담는가 | 지시문 목록과 대조 | 날짜 교락(215), 한 에피소드(215), 설계 사후성(43·217), A 조용한 구간(54), 전환 미관측(41), 확률 조건부성(109~113·216)은 주장 옆이나 한계 절에 있다. 빠지거나 축소된 것은 E2 실패(D-05), 다른 OS 미실측(D-06), 지연 기준(D-02)이다 |
| 파이썬 판 | README·requirements·environment.yml·lock | 3.11~3.12(권장 3.12), 확인 3.12.2·3.12.8. 모순 없다 |

## ④ 미확인 의심

- **v1 테스트 수:** `press_submission/README.md:75`는 "테스트 49개"라고 쓴다. 현재 `tests/`의 test 함수는 44개다(grep). 매개변수화로 49개가 될 수 있어 판정하지 않았다.
- **2단계 비의 단위:** 주추정 1/7은 건(구간) 단위 비다. 두 폴드의 α5% 값에서 나왔다: 1단계 5+2건, 2단계 1+0건(`alert_levels_v2.csv`). 운영 알림은 사건 단위다. 동결 B에서는 건 수와 사건 수가 같았다. 그러나 두 폴드의 사건 단위 비는 산출물에 없다.
- **D-01의 현장 크기:** 연속 스트림에서 v2의 위치 2~6 이득이 얼마나 남는지는 산출물이 없어 추론으로만 적었다.

## ⑤ 직접 수행한 검증

| 산출 | 내용 |
|---|---|
| `redD_extract_claims.py` → `redD_claims_raw.csv`, `redD_table_notes.csv`, `redD_extract_claims.log` | 기준 커밋의 문서 11개에서 수치 문장 1,361개·토큰 3,842개를 추출했다. 표 설명 열 455칸도 추출했다 |
| `redD_pool_screen.py` → `redD_pool_screen.csv`, `redD_pool_unmatched.csv`, `redD_pool_screen.log` | 수치 토큰과 분수를 커밋 산출물 값 풀과 대조했다(약 5초) |
| `redD_targeted_checks.py`(+`redD_lib.py`) → `redD_targeted_checks.log` | 남은 인용 행 대조, 크기 성분 \|z\| 경계, 저장 모델의 보정 최대 점수 위치(D-03), 확률 상한 행 수를 확인했다 |
| 손 대조 | pandas로 표를 출력해 문서 문장과 대조했다. 원본 CSV에서 공백·적용률·Spearman을 다시 계산했다. 콘솔 캡처 5조각과 `docs` 그림 2장을 판독했다. `round4` 기록(시간·평가관 06 정규식)을 대조했다 |

- 저장소의 생성 스크립트는 실행하지 않았다.
- 쓰기는 `adversarial/redD_*`와 이 보고서뿐이다. `claude/`는 읽지 않았다.
- 스크립트 실행 시간 합계는 1분 미만이다. 검수는 중단 포함 약 1시간 걸렸다.
