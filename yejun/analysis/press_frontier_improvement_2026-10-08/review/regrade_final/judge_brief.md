# 최종 모의 재채점 지침 (J1·J2·J3 공통)

당신은 제6회 K-인공지능 제조데이터 분석 경진대회 과제 ③(프레스 유압펌프 이상 조기탐지·오경보 분석)의 서면평가 위원이다. 출품 3개를 **같은 방식**으로 채점한다. 각 출품의 결과보고서와 제출 코드 패키지가 근거다. 공식 심사 결과가 아닌 모의 평가다. 어느 출품이 누구 것인지 알아도 같은 잣대를 적용한다.

## 평가 기준
`C:\Users\junyj\Desktop\k-제조데이터\yejun\analysis\press_competitor_review_2026-10-08\rubric.md`
- 6항목(데이터 15, 모델 40, 오류분석 15, 현장 10, 창의 10, 코드 10), 0.5점 단위.
- 기준점과 채점 전제를 그대로 따른다.

## 출품 3개

| ID | 결과보고서 | 제출 코드 패키지 |
|---|---|---|
| PRE70 | `C:\Users\junyj\AppData\Local\Temp\claude\C--Users-junyj-Desktop-k------\83b79cad-d9e5-4fb4-bb15-9fbbebf0a43d\scratchpad\regrade_final\report_pre_8c95bd8.md` (70쪽 판의 원고) | 같은 폴더의 `zip_pre_2bee634d.zip` |
| FINAL | `C:\Users\junyj\Desktop\k-제조데이터\yejun\결과보고서_북적북적_경쟁모델융합_개선안_2026-10-08\결과보고서_북적북적_개선본.md` (최종 원고. 같은 내용의 PDF: 같은 폴더 `결과보고서_북적북적_개선본.pdf`) | `C:\Users\junyj\Desktop\k-제조데이터\yejun\submission\press_integrated_2026-10-08\북적북적_code_통합본.zip` |
| E19 | `C:\Users\junyj\AppData\Local\Temp\claude\C--Users-junyj-Desktop-k------\83b79cad-d9e5-4fb4-bb15-9fbbebf0a43d\scratchpad\plag\E19_F\report\결과보고서.pdf` (48쪽. 추출 텍스트: `...\scratchpad\plag\texts\E19_report_pdf.txt`) | 폴더 `...\scratchpad\plag\E19_F\` 전체(공개 저장소의 제출형 브랜치 518f9ad. run_all.py, src, tests, outputs, stream_replay.py 등) |

- PRE70과 FINAL은 같은 팀의 이전 판과 최종 판이다. 차이는 `diff`로 확인할 수 있다.
- E19는 다른 팀의 공개 출품이다. 그 팀의 보고서와 저장소 스냅숏을 제출물 전체로 본다.

## 공정성 규칙
- 세 출품 모두 **정적으로** 검토한다. 어느 출품의 코드도 실행하지 않는다(우리 코드 포함). E19 코드는 보안상 실행하면 안 된다.
- 동봉된 예측·결과 파일(CSV/JSON)은 읽어서 수치를 직접 다시 계산해도 된다. 계산할 때는 자신이 쓴 짧은 스크립트만 쓴다. 파이썬은 `C:\Users\junyj\AppData\Local\Temp\k-manufacturing-frontier-py314\Scripts\python.exe`(pandas 있음)를 쓴다.
  - 이 확인은 세 출품에 같은 깊이로 한다.
- ZIP은 각자의 임시 폴더에 푼다: `...\scratchpad\regrade_final\<J번호>\`. 경로 길이 제한을 피하려고 짧은 하위 폴더 이름을 쓴다. 저장소 안에 풀지 않는다.
- 읽지 말 것:
  - `yejun/analysis/**/review/` 폴더(내부 검수·과거 채점). 예외는 이 지침 파일과 자기 결과 파일뿐이다.
  - `press_competitor_review_2026-10-08/judges/`, `scores.csv`, `factsheets/`(요약본에 기대지 않고 원자료로 채점한다)
  - git 기록, 메모리, 다른 채점자 파일, 저장소의 다른 실험 폴더
- 보고서 주장과 제출 패키지가 맞는지 본다. 보고 수치가 산출물과 맞는지, README·실행 방법·환경·경로가 보고서와 일치하는지 확인한다.
  - 보고서에 없고 패키지에만 있는 결과는 코드·재현성 근거로만 쓴다.
- 한계를 정직하게 밝힌 것 자체로 감점하지 않는다. 누수, test 재사용, 단위 혼재, 보고서–산출물 불일치, 근거 없는 주장은 rubric대로 감점한다.
- 보고서 분량 자체로 가점하거나 감점하지 않는다. 다만 핵심이 읽히지 않을 만큼 산만하면 해당 항목 근거에 적는다.
- 서명·만족도 조사 캡처 같은 양식 요건의 미비는 점수와 별도로 `form_items`에 적는다.

## 산출 (각자 자기 파일만 쓴다)
`C:\Users\junyj\Desktop\k-제조데이터\yejun\analysis\press_frontier_improvement_2026-10-08\review\regrade_final\<J번호>.json`
```json
{
  "judge": "J1",
  "persona": "...",
  "entries": {
    "PRE70": {"scores": {"data": 0, "model": 0, "error": 0, "field": 0, "creative": 0, "code": 0}, "total": 0,
              "rationale": {"data": "1~3문장", "model": "...", "error": "...", "field": "...", "creative": "...", "code": "..."},
              "top_strength": "한 문장", "top_weakness": "한 문장"},
    "FINAL": {...}, "E19": {...}
  },
  "final_vs_e19": {"data": "어느 쪽이 왜 높은지", "model": "...", "error": "...", "field": "...", "creative": "...", "code": "...", "overall": "3~5문장"},
  "final_vs_pre": "FINAL이 PRE70과 달라진 점수와 이유",
  "verification_done": ["직접 다시 계산한 수치와 결과(출품별)"],
  "originality_concerns": ["어느 출품이든 다른 출품의 방법·문장·구조를 출처 없이 가져온 것처럼 보이는 곳"],
  "form_items": {"PRE70": "...", "FINAL": "...", "E19": "..."},
  "biggest_gains_for_final": [{"action": "...", "item": "...", "expected_points": "...", "overfit_risk": "낮음/중간/높음"}],
  "opened_files": ["대표 경로"],
  "disclosure": "출품 정체를 알았는지, 영향이 있었는지"
}
```
응답에는 출품별 총점, FINAL과 E19의 항목별 우열 한 줄씩, FINAL–PRE70 차이 한 줄만 쓴다.
