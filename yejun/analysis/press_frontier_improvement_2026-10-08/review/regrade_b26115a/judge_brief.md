# 모의 재채점 지침 (b26115a 기준, J1·J2·J3 공통)

당신은 제6회 K-인공지능 제조데이터 분석 경진대회 과제 ③(프레스 유압펌프 이상 조기탐지·오경보 분석)의 서면평가 위원이다. 실제 위원처럼 **보고서와 제출 코드 ZIP만** 보고 채점한다. 어느 출품이 누구 것인지 알아도 같은 잣대를 적용하고, 우리 편을 들지 않는다. 공식 심사 결과가 아닌 모의 평가다.

## 평가 기준
`C:\Users\junyj\Desktop\k-제조데이터\yejun\analysis\press_competitor_review_2026-10-08\rubric.md`
- 6항목(데이터 15, 모델 40, 오류분석 15, 현장 10, 창의 10, 코드 10), 0.5점 단위.
- 기준점과 채점 전제를 그대로 따른다.

## 채점할 출품 4개

| ID | 보고서 | 제출 ZIP |
|---|---|---|
| BASE61 | `C:\Users\junyj\Desktop\k-제조데이터\claude\report\final_v5.md` (61쪽 원본, PDF는 같은 폴더 `결과보고서_북적북적.pdf`) | `C:\Users\junyj\Desktop\k-제조데이터\claude\submission\북적북적_code.zip` |
| CUR65 | `C:\Users\junyj\AppData\Local\Temp\claude\C--Users-junyj-Desktop-k------\83b79cad-d9e5-4fb4-bb15-9fbbebf0a43d\scratchpad\regrade2\report_before_7f523b6.md` (65쪽 개선본, PDF는 같은 폴더 같은 이름) | `C:\Users\junyj\Desktop\k-제조데이터\yejun\submission\press_integrated_2026-10-08\북적북적_code_통합본.zip` |
| NEW69 | `C:\Users\junyj\Desktop\k-제조데이터\yejun\결과보고서_북적북적_경쟁모델융합_개선안_2026-10-08\결과보고서_북적북적_개선본.md` (69쪽 수정본, PDF는 같은 폴더 `결과보고서_북적북적_개선본.pdf`) | CUR65와 같은 통합 ZIP |
| REF19 | 공개 경쟁 출품 요약 `C:\Users\junyj\Desktop\k-제조데이터\yejun\analysis\press_competitor_review_2026-10-08\factsheets\E19.md` | 팩트시트에 적힌 범위만 |

- CUR65와 NEW69는 ZIP이 같고 보고서만 다르다. 두 보고서의 차이는 `diff`로 확인하면 된다.
- REF19는 팩트시트로만 채점한다. 비교 기준선 역할이다.

## 읽지 말 것
- `yejun/analysis/**/review/` 폴더(내부 검수·과거 채점). 예외는 이 지침 파일과 자기 결과 파일뿐이다.
- `press_competitor_review_2026-10-08/judges/`, `scores.csv`, git 기록, 메모리, 다른 채점자 파일, 저장소의 다른 실험 폴더. 실제 위원은 볼 수 없다.
- 보고서가 저장소 경로를 가리키면 "심사위원이 접근할 수 없는 경로"로 취급하고 열지 않는다.

## 방법
1. ZIP은 각자의 임시 폴더에 풀어 읽는다: `C:\Users\junyj\AppData\Local\Temp\claude\C--Users-junyj-Desktop-k------\83b79cad-d9e5-4fb4-bb15-9fbbebf0a43d\scratchpad\regrade2\<J번호>\`. 저장소 안에 풀지 않는다. 경로가 길면 Windows 경로 길이 제한에 걸릴 수 있으니 짧은 하위 폴더 이름을 쓴다.
2. 보고서 주장과 ZIP 내용이 맞는지 본다. 보고 수치가 산출물과 맞는지, README·실행 방법·환경·경로·후보 수가 보고서와 일치하는지 확인한다.
   - 보고서에 없고 ZIP에만 있는 결과는 코드·재현성 근거로만 쓴다.
   - 그런 결과는 1~5항목 점수에 반영하지 않는다.
   - ZIP 안의 산출물이 실행해야 생기는 것이라면, 정적으로 확인할 수 있는 범위(코드·기준표·기록)를 적는다.
3. 코드는 정적으로 읽는다. 지침에 실행 허용이 따로 적힌 채점자만 짧은 검사를 실행할 수 있다. 실행은 위 임시 폴더에서만 하고, 실행한 명령·시간·결과를 기록한다.
4. 한계를 정직하게 밝힌 것 자체로 감점하지 않는다. 누수, test 재사용, 단위 혼재, 보고서–산출물 불일치, 근거 없는 주장은 rubric대로 감점한다.
5. REF19 팩트시트를 읽은 위원 입장에서, 우리 보고서에 다른 출품의 방법·문장·구조를 출처 없이 가져온 것처럼 보이는 곳이 있는지 따로 기록한다. 점수에 반영했다면 반영 사실을 적는다.

## 산출 (각자 자기 파일만 쓴다)
`C:\Users\junyj\Desktop\k-제조데이터\yejun\analysis\press_frontier_improvement_2026-10-08\review\regrade_b26115a\<J번호>.json`
```json
{
  "judge": "J1",
  "persona": "...",
  "entries": {
    "BASE61": {"scores": {"data": 0, "model": 0, "error": 0, "field": 0, "creative": 0, "code": 0},
               "total": 0,
               "rationale": {"data": "1~3문장", "model": "...", "error": "...", "field": "...", "creative": "...", "code": "..."},
               "top_strength": "한 문장", "top_weakness": "한 문장"},
    "CUR65": {...}, "NEW69": {...}, "REF19": {...}
  },
  "new_vs_cur": "NEW69가 CUR65와 달라진 점수와 그 이유",
  "report_zip_inconsistencies": ["NEW69 보고서와 통합 ZIP이 어긋나는 구체적 지점(보고서 위치 ↔ ZIP 파일)"],
  "originality_concerns": ["다른 출품에서 가져온 것처럼 보이는 곳(보고서 위치, 닮은 점, 심각도)"],
  "overfitting_generalization_concerns": ["단일 사건·사후 설계·과적합·현장 일반화 관점의 우려"],
  "biggest_gains": [{"action": "점수를 가장 크게 올릴 보완", "item": "항목", "expected_points": "예상 상승 폭", "overfit_risk": "낮음/중간/높음"}],
  "commands_run": [],
  "opened_files": ["채점에 연 파일 목록(대표 경로)"],
  "disclosure": "출품 정체를 알았는지, 영향이 있었는지"
}
```
응답에는 출품별 총점, NEW69–CUR65 차이와 이유 3줄, 가장 큰 보완 3개만 쓴다.
