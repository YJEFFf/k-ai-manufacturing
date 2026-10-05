---
title: 3회차 수정 진행표 (고칠 수 있는 감점 전부)
created: 2026-10-05
updated: 2026-10-05
tags: [contest/k-ai-manufacturing]
source: 중립 판정(84점) 뒤 사용자 요청 "고칠 수 있는 감점 다 고쳐, 문서+개발" — 토큰 한도 뒤 이어서 하기 위한 표
status: growing
---

# 3회차 진행표

> **이어서 할 때 먼저 읽을 것.** 체크 안 된 항목부터 위에서 아래로 한다. 각 항목 끝에 바뀐 파일을 적는다.
> - 볼트 스크립트는 `C:/Temp/bj_v3/venv/Scripts/python.exe`(pandas 3.0.5)로 돌린다. 전역 파이썬은 pandas 2.3.3이라 캐시 pkl을 못 읽는다(10/5 13:41 pykrx 설치)
> - 한글 조립(build_hwpx.py)과 PDF 검사(pymupdf)는 전역 `python`으로
> - 원고 수정은 (old, new, 횟수) 검사 뒤 바이트로 쓴다(`write_text`는 이 PC에서 CRLF로 바꾼다). Bash heredoc은 백슬래시를 먹으니 백슬래시가 든 글은 Write 도구로 스크립트를 만들어 돌린다
> - 레이아웃 검사: `python scratchpad/refs/layout_check.py <hwpx> <pdf>` (스크래치는 세션마다 지워질 수 있음 → 같은 검사를 다시 짜도 됨: 장 맨 위, 표 끊김, 홀로 남은 제목)
> - 공개 문장 P1~P5 각 1회 원문 그대로, 금지 문구("사전 등록","독립 검증","보지 않고","처음 보는 시험") 0, `check_facts.py final_v5.md` 근거 없는 숫자 0

## 지금 상태 (10/5 21시 무렵)
- 원고 final_v5.md: 1회차(검수·질문 반영)·2회차(77건 병합) 반영, 조립 40쪽(작업본 `결과보고서_북적북적_작업.hwpx/pdf`). 원래 이름 파일은 아직 1회차 전 판
- 제출 zip: 06·07 사후 스크립트, 예측 파일, 대조 24개(quick 18). README에 자리표시자 {CHECKS_QUICK}·{CHECKS_FULL}·{FULL_TIME}·{VERIFIED} 남음(전체 실행 뒤 채움)
- 새 venv 전체 실행: `C:/Temp/bj_v3/full_run.log` (round 3 코드 변경 전 zip 기준). round 3에서 코드가 바뀌면 마지막에 다시 돌린다
- 토론 판정 84점, 고칠 목록은 아래

## 할 일 (판정자 합의 목록 기준)
### 개발
- [x] D1 (10/5 완료: code/press/tvt/08_probability.py, run_all 2단계 추가, make_package Brier 대조, 원고 2.5·5·6장, README, facts_build) 이상 확률을 run_all에서 다시 만들기: 05_test_predictions.py가 v2 확률 층(yejun press_guard/probability.py)을 **valid만으로** 맞춰 test 예측 파일에 확률 열을 넣는다. Brier(파일 사전·현장 1%)를 outputs에 저장 → 원고 2.5절 확률 문단을 이 값으로 바꾸고 6장·README의 "다시 만들지 않는 수치"에서 이상 확률·Brier를 뺀다. make_package 기대값에 Brier 1개 추가
- [~] D2 (그림 완료: report/figures/fig12_alarm_card.png, make_figures.fig_alarm_card — 분할 B 이상 기록 11과 정상 기록 423. 남은 것: 원고 4.2에 [그림 13: …]과 설명 1줄) 최종 모델 경보 카드 예시 그림(콘솔이 v2 기준이라는 감점 보완): test 예측 파일로 최종 모델 사건 하나의 경보 근거·R1 유지·R2 보류를 한 장에 → 4.2절
### 문서
- [ ] T1 요약 성능 사슬 첫 고리(LSTM 0.289) 교체 → 베이스라인 최고값 기준으로
- [ ] T2 2.4 주 비교표에 test 실시간 미탐·오경보 행 열 추가(tvt_test.csv의 fn·fp, PCA·CUSUM·EWMA는 산출물에 있으면 넣고 없으면 —)
- [~] T3 (그림 완료: report/figures/fig11_model_structure.png, make_figures.fig_model_structure. 남은 것: 원고 2.3에 [그림 8: …] 넣고 뒤 그림 번호 +1, build_hwpx FIGS 고침) 2.3 모델 구조도(그림) 추가 → 뒤 그림 번호와 본문 "그림 n" 참조를 다시 매김
- [ ] T4 3.2절 9/53→1/53, 14.0% 대 3.8%에 Clopper–Pearson 구간
- [ ] T5 5장 대조표에 모델·규칙 행, 한계 항목(표본 간격 역산·세션 교락)을 기여로 다시 쓰거나 다른 장으로
- [ ] T6 1장 결함표 이상치 칸에 2.2절 꼬리 점검 연결, 남은 필터 단서 반복 정리
- [ ] T7 "팀 분석 자료"(3.1) 출처 명시, R² "중앙 0.095"(3.x) 조건 명시
- [x] T9 (10/5 완료: code/press/domain/07_anomaly_patterns.py, 원고 4.2절 표·6장 단계 표, run_all 4단계, make_package 대조 1개, README, facts_build) (예준 제안 10/5 21시) 이상 기록 21개의 양상 유형화 → '먼저 점검할 곳' 표: 기록마다 상부·하부 진동 크기, 전류 파형(사인 R²), 전류 치우침, 상·하부 상관이 정상 범위 밖인지 표시 → 양상별 묶음 → 2.1 진단 매트릭스·4.2 점검표에 연결. 단서: 21기록은 한 사건의 연속 구간이라 '고장 유형'이 아니라 '사건 안 시기별 양상'. 새 사후 스크립트 code/press/domain/07_anomaly_patterns.py(run_all 4단계), 원고 3장 또는 4.2절
- [x] T8 (10/5 완료: code/press/cases/README.md 실행 절을 zip 기준으로) zip 안 code/press/cases/README.md의 없는 경로(claude/…, /tmp/v2_out) 고침
### 마무리
- [ ] F1 make_package → 새 venv 전체 실행 → README 자리표시자·6장 대조 수·시간 채움 → README만 바뀐 zip 재빌드
- [ ] F2 build_hwpx(원래 이름 결과보고서_북적북적.hwpx/pdf) → 레이아웃 검사 → 바뀐 쪽 눈으로 확인
- [ ] F3 3회차 검증(critic 1명, 사실·일관성)
- [ ] F4 판단 기록·MOC·회신 문서 갱신 → sync_repo + 보고서·zip 강제 추가 → 커밋·push → PR #3 댓글
- [ ] F5 예준 톡 초안 + 확인 질문 파일(report/logs/검토요청_예준.md, 쪽 번호 채우기)
- [ ] F6 임시 venv(C:/Temp/bj_v3) 삭제
### 사용자 몫
- 만족도 조사 캡처를 실제 완료 화면으로(파일 주면 넣고 다시 조립)

- W4(문서 T1·T2·T4~T7) 수정안: 스크래치 round3/W4_edits.json — 도착하면 report/_archive 백업 뒤 적용(겹치면 건너뛰는 적용 스크립트), 그다음 그림 번호 다시 매김(T3·D2)

## 10/5 밤 중단 시점 상태 (사용 한도) — 여기서부터 이어서
- 완료: D1(확률, tvt/08) · D2(경보 카드 그림 13, 4.2절) · T1 · T2 · T3(구조도 그림 8, 2.3절, 뒤 그림 번호 +1, build_hwpx FIGS 갱신) · T4 · T5 · T6 · T7(W4 21건 적용) · T8 · T9(domain/07, 4.2절 양상 표)
- 검사 상태: check_facts 근거 없는 숫자 0, P1~P5 각 1회, 금지 문구 0, 레이아웃 문제 0(장 맨 위·표 끊김 없음). 작업본 결과보고서_북적북적_작업.pdf 44쪽, 그림 13장
- 백업: report/_archive/final_v5_before_round3_W4.md, final_v5_before_fig_renumber.md
- facts_build.py에 확률·양상·3.2 CP 구간·PCA/CUSUM 미탐 블록 추가(전역 파이썬 말고 C:/Temp/bj_v3 venv로 돌릴 것)
- 다음 할 일(순서대로)
  1. 쪽 줄이기(선택): 39쪽은 5장 마지막 2줄만 넘어가 87% 빔 → 5장에서 2~3줄 줄이면 1쪽 감소. 25쪽(2장 끝 7줄), 23쪽(2.6 표가 통째로 넘어가 79% 빔), 31쪽(3장 끝 10줄)도 같은 방식으로 1~2줄씩 줄이면 쪽이 준다
  2. F1: `python submission/make_package.py --repo <scratchpad/repo>`(bj_v3 python) → zip을 C:/Temp/bj_v3에 풀어 새 venv(또는 bj_v3)로 `run_all.py` 전체 → 대조 수(예상 전체 26·quick 19)·시간으로 README 자리표시자 {CHECKS_QUICK}·{CHECKS_FULL}·{FULL_TIME}·{VERIFIED}와 원고 6장 "대조 21개"·"약 80분"을 채움(facts_build EXT run.full_min·run.checks도) → README만 바뀐 zip 재빌드
     - 주의: 지금 C:/Temp/bj_v3/full_run.log는 3회차 코드 변경 전 zip으로 돈 것(참고용)
  3. F2: build_hwpx를 원래 이름(결과보고서_북적북적.hwpx/pdf)으로 → 레이아웃 검사 → 바뀐 쪽 눈으로
  4. F3 3회차 검증 1명(사실·일관성) → F4 기록·업로드·PR 댓글 → F5 예준 톡(예준이 이상 양상 유형화 의견을 냈고 4.2절에 반영함 — 톡에 인정 한 줄) + report/logs/검토요청_예준.md 쪽 번호 → F6 C:/Temp/bj_v3 삭제
- 참고: 3회차 수정 전 zip의 전체 실행 결과 = 대조 24/24 일치, 전체 129.5분. 예측 파일: predictions/test_predictions_A.csv, _B.csv / exit=0 (C:/Temp/bj_v3/full_run.log). 3회차 코드(08·domain/07)가 들어간 zip으로 다시 돌려야 최종 수치
- 10/6 이어서: 쪽 줄이기 완료(2.6 끝 문단·5장 끝 항목 축약, build_hwpx가 장 제목 앞 빈 문단을 지우게 고침 → 빈 쪽 없음) 작업본 42쪽. 다음 F1부터
- 10/6: F3 3회차 검증 완료(수정 11건 적용, 그림 8 화살표·가운데 상자, 그림 13(a) 제목 고침). 남은 C1 = 6장·README 재현 수치(F1 실행 결과로)
- F1 완료(10/6): 원고 재현 수치 26개·약 56분, README 자리표시 채움, facts EXT 갱신, check_facts 0개, 패키지 재생성(tested3.zip 대비 README만 다름)
- F2 완료(10/6): 원래 이름으로 hwpx/pdf 재생성 42쪽, layout_check 문제 0건, 바뀐 쪽(2·36·38) 눈으로 확인
