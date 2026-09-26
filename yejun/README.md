# K-AI 제조데이터 분석 경진대회

이 폴더는 예준의 작업 공간이다. Codex와 Claude Code를 번갈아 쓰며, 두 도구가 함께 따르는 작업 규칙은 [`AGENTS.md`](AGENTS.md)에 있다. 과제 재선정, 데이터 품질 감사, 기준모델 실험과 후속 검증을 보관한다.

현재 선택은 **③ 프레스 유압펌프 이상 탐지·오경보 분석**이다. 사용자 결정으로 ① 사출·④ X-ray·⑤ 전력은 후보에서 제외했다. ② 용접과의 추가 검증 및 최종 판단은 [프레스·용접 비교 보고서](analysis/press_welding_review/README.md)를 우선 참고한다. 아래 기존 문서는 당시 후보 범위와 판단을 보존한 기록이다.

**현재 단계: 구현·실험·디버깅·검수.** 2026-09-25 예준 지시로 대회 보고서 초안과 자동 생성 코드를 삭제했다. 예준이 결과에 만족하고 **보고서 작성 시작을 명시적으로 지시하기 전까지 보고서 작업을 진행하지 않는다.** Codex와 Claude Code 공통 지침은 [AGENTS.md](AGENTS.md)를 따른다.

## 먼저 볼 문서

- [프레스 루브릭 6항목 검수](analysis/press_rubric_review/README.md): 2026-09-26 Codex(1차)·Claude Code(2차·총괄). 현재 근거 충족도 78/100(공식 점수 아님), P0 없음, 수정 24건(R1~R24)과 수정 순서
- [프레스 진단·근거 보강 표](analysis/press_evidence/README.md): 2026-09-26 검수 R1~R4·R10·R14·R18~R22. A 평가 구간이 가장 조용한 시간대(0/120은 유리한 조건), 변수 사전·불균형·이상치·가이드북 품질 지수, 상·하부 진동 상관 부호 반전, AR(2)=0.6064 Hz 진동자
- [프레스 보완 실험 E1~E3](analysis/press_supplement/README.md): 2026-09-26 고장 주입(전류 불규칙 σ×0.1부터 탐지), UCI에 v2 구조 적용 실패, 재보정 곡선(사전 안정 규칙 0/36 충족, 사후 탐색값 약 6분)
- ⑤ 전력 병행 패키지 [power_submission](power_submission/README.md)과 [프레스와의 비교](analysis/power_press_comparison/README.md): 과제 최종 선택은 예준 결정 대기
- [날짜·시간대 교락 참고 분석](analysis/press_dayshift/README.md): 2026-09-26 자원최적화 자료는 다른 현장·다른 센서라 교락 해소 근거가 못 됨. 대회 정상은 07-12(화) 00:00~01:17, 이상은 07-17(일) 10:51~10:54. v2 이상 탐지는 전류 수준에 의존하지 않고, 분할 B는 전류 +5%부터 정상 알림 증가. 주최 측이 데이터 문의에 답하지 않아 확인 사항 4개를 팀 결정 규칙으로 바꿈(§6)
- [Codex 전체 워크플로우 검수 F1~F5 반영](analysis/press_guard_review/README.md): 2026-09-26 재적합 민감도·절제·구간 조건표·2×2·예측 CSV 계약·audit 분리. v2 테스트 46개·audit 16/16·verify 19/19·새 클론 19/19
- [위치 0·1 미탐 후보 실험](analysis/press_early/README.md): 2026-09-25 공동 정상 분포·1차 예측 오차 후보를 사전 고정해 시험, 둘 다 채택 기준 불충족(정상 알림 증가 또는 개선 없음). v2 유지
- [Claude 후속 구현 Codex 재검수](analysis/press_guard_review/codex_recheck.md): 검증·동결 누락 경로와 웹 차트/재생 결함 수정, 미탐 해석 교정, 토의 항목 3개 판단
- [코덱스 인수인계 검수·웹 콘솔 구현](analysis/press_guard_review/README.md): Claude의 v2·후보 탐색·UCI 재현, 웹 연결·검수·벤치마크 및 사용자 위임에 따른 v2 채택·디벨롭 이력
- [Press Guard v2 구현·실험](press_guard/README.md): 2026-09-25 정상 전류 AR(2) 잔차 결합으로 F1 A 0.961938/B 0.970990, 미탐 44/31, 정상 알림 0/120·3/180 유지(A 평가 구간은 보정보다 조용한 시간대라 0/120은 유리한 조건의 값). 테스트 42개·JS 회귀 4개 통과. 로컬 웹 콘솔 동작
- [외부 유압 데이터 확보·검증](analysis/press_external/README.md): UCI 2,205사이클 다운로드·CRC 확인 및 18개 고정 비교 완료. 다른 운전 환경으로의 무보정 전이 실패도 보존
- [프레스 성능 개선 후보 실험](analysis/press_improvement/README.md): 2026-09-25 초반 6→8관측 창 후보가 정상 알림·21/21 탐지를 유지하며 F1 A 0.910→0.923, B 0.920→0.935. 탐색 결과이며 기본 모델은 유지
- [Claude 2차 수정에 대한 Codex 재검수](analysis/press_implementation_review/codex_recheck_2.md): 2026-09-25 테스트 49개·깨끗한 클론 27/27 및 39/39·독립 재집계 통과. 실제 코드·모델 파일 변경과 기준값 출처도 확인. 보고서 작성은 보류
- [Claude 구현 재검수 2차](analysis/press_implementation_review/claude_recheck_2.md): 코드 변경 검출·artifact 무결성·새 클론 안내·기준값 출처 보완 이력
- [프레스 구현 재검수·수정 (Codex)](analysis/press_implementation_review/codex_recheck.md): 2026-09-25 Claude 수정 재검증·남은 완료 판정 오류 수정
- [최초 구현 검수 이력](analysis/press_implementation_review/README.md): R1~R6 반례·Claude 재검수·후속 검증 연결
- [프레스 제출 패키지 실행계획 — 확정 v1](press_submission/PLAN.md): 확정 연구설계·실행 프로토콜·단계별 완료 조건
- [클로드 후속 계획 적대적 검토](analysis/press_plan_review/README.md): 2026-09-24 계획 실행 전 수정할 R1~R8, 실제 계산 결과, 검토 당시 계획 원문
- `analysis/press_welding_review/README.md`: 2026-09-23 프레스·용접 추가 검증과 현재 선택
- `과제재선정_정밀검토.md`: 이전 후보 범위에서의 과제 추천과 핵심 근거
- `과제재선정_후속검증.md`: 추가 자료 및 실험을 반영한 상세 검토
- `평가기준_3_4_5_중심_전략재검토.md`: 영향요인·현장 활용·차별성 중심 전략
- `전력과제_제출까지의_검증계획.md`: 전력 과제를 선택했을 때의 개발·판정 일정
- `analysis/energy_followup/README.md`: 전력 후속 실험의 정의, 결과와 재현 방법

## 디렉터리

- `press_guard/`: 별도 v2 후보의 학습·저장·CSV/순차 추론·집계·테스트·실행 검증·벤치마크. 로컬 웹 콘솔(`serve.py` + `web/`) 동작
- `analysis/press_advance/`: 정상 전류 AR(2) 결합의 후보 고정·절제·입력 정밀도 실험
- `analysis/press_external/`: UCI 유압 자료 확보·특징 추출·환경 이동 검증
- `press_submission/`: 실행계획, 모델 코드·실험 결과·검수용 수치 집계 (보고서 작성 보류)
- `analysis/press_implementation_review/`: 1~6단계 구현의 실행 재현·독립 재집계·결함 재현·검수 판정
- `analysis/press_improvement/`: 기존 구현을 유지한 채 수행하는 성능 개선 후보·입력 정밀도 민감도 실험
- `analysis/press_plan_review/`: 클로드 후속 계획 검토와 검토 당시 원문
- `analysis/press_welding_review/`: 두 후보의 집계 정답·경보 정책·센서 관계 추가 검증
- `analysis/reselection/`: 다섯 과제와 KAMP 추가 자료의 감사 코드·결과·판정
- `analysis/energy_followup/`: 전력 예측, 고부하 경보, 오류 조건 분석
- `analysis/followup_materials/`: 추가 가이드와 사출·설비·용접 후속 검토
- `analysis/xray_followup/`: X-ray 표식 처리와 날짜 분리 검출 감사
- `analysis/welding/`: 로봇용접 데이터 품질 및 반복 구간 분석

## 데이터 정책

대회 원본 데이터, 관련 자료, 복원 CSV, 이미지·라벨 묶음과 행 단위 예측값은 저장소에 포함하지 않는다. 코드 실행 시 원본 경로를 별도로 지정해야 한다. 커밋된 CSV·JSON은 데이터셋 원행이 아닌 집계 성능표와 감사 요약이다.

이 브랜치의 결과는 과제 선정 과정에서 이미 살펴본 기간을 포함한다. 최종 미사용 시험이나 실제 현장 실증으로 해석하지 않으며, 각 보고서에 검증 범위와 한계를 기록했다.

## 폴더 이동 후 실행

이 폴더는 2026-09-24에 `codex/`에서 `yejun/`으로 이름을 바꿨다. 과거 기록에 남은 `codex/` 경로는 지금의 `yejun/`이다. 기존 문서의 `analysis/...` 명령은 `yejun/` 안에서 실행한다. 원본 `데이터셋/`과 `관련 자료/`는 저장소 루트에 있는 로컬 자료를 사용하며 Git에 포함하지 않는다. 과거 보고서의 절대 경로·`/tmp` 경로는 당시 실행 기록으로 보존했다. 해당 자료가 없는 환경에서는 스크립트의 입력 경로 옵션을 지정해야 한다.

```bash
cd yejun
python analysis/press_welding_review/press_policy_audit.py
python analysis/press_welding_review/welding_validation_audit.py --claude-code ../claude/code
```
