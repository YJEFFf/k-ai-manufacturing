---
title: 보고서 v5 진행 상황 (이어하기용)
created: 2026-10-04
updated: 2026-10-04
tags: [contest/k-ai-manufacturing]
source: 작업 세션 자체 기록
status: growing
---

# v5 진행 상황 — 중단되면 여기서 이어 간다

> 계획: `report/plans/plan_report_v5.md` · 판단 기록: `report/logs/decision_log_v5.md` · 조사: `report/research/*.md` · 분석 결과: `code/press/domain/outputs/*_summary.md`

## 체크리스트
- [x] 조사 R1 도메인 근거 → research/domain_sources.md
- [x] 조사 R2 출제 의도 → research/organizer_intent.md
- [x] 조사 R3 경쟁팀·논문 기법 → research/peer_and_methods.md
- [x] 분석 D1 신호 물리 → 01_signal_physics
- [x] 분석 D2 사건 안 추세 → 02_event_trend
- [x] 분석 D3 MSPC → 03_mspc
- [x] 분석 D4 순차 검출·불확실성·경보 KPI → 04_sequential_uncertainty
- [x] 분석 D5 지도학습 교락 → 05_supervised_confound (draft_v5 2.4절 반영)
- [x] 분석 D6 운전 상태별 오경보 → 06_operating_regime
- [x] 그림 추가(완료, build_hwpx FIGS 매핑 v5로 변경): fig1 계통도 갱신, fig8 관측 가능성 주파수 축, fig9 정상 77분 운전 상태 타임라인(정숙 구간·분할 경계·오경보), fig10 부하-진동 관계(정상 vs 이상)
- [x] report/drafts/draft_v5.md 작성 (D5 지도학습 대조 문단만 '[D5 결과 반영 예정]' 자리로 남음)
- [x] facts_build.py 도메인·외부 수치 등록, check_facts 0 (D5 반영 후 재실행)
- [x] critic 1회차 REVISE → 46곳 수정·참고문헌 재번호(report/drafts/draft_v5_r0.md 백업)
- [x] critic 2회차 조건부 PASS → N1·N2·MINOR 반영(report/drafts/draft_v5_r1.md 백업). 재검토 불요
- [x] humanize 6조각(005~010) → final_v5.md 병합. 숫자 동일·인용 순서 동일·P1~P5·금지어 0·표시 개수 동일 확인
- [x] build_hwpx.py final_v5.md → 31쪽. 전 쪽 화면 점검, hwpx 본문 숫자 대조(원고 숫자 누락 0), 메타데이터 jacob 0, 만족도 조사 쪽 새 쪽 시작
- [x] MOC 갱신, decision_log 마감, 사용자 보고

## 중단 시 메모
- D1·D5가 끝나지 않은 채 중단됐으면 outputs/01_*, 05_* 존재 여부를 보고, 없거나 요약 md가 없으면 해당 스크립트를 다시 실행하거나 같은 지시로 에이전트를 다시 띄운다
