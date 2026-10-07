# Windows 인수인계 — 경쟁 1위 모델 아이디어 융합 (2026-10-08 중간 저장)

## 현재 상태

사용자 요청으로 Mac에서 작업을 이 지점에서 중단했다. **모델 후보를 실제 대회 자료로 채점하거나 선택하지 않았고, 복사한 보고서 본문도 아직 고치지 않았다.** 성능 개선이나 1위 역전을 달성했다는 주장을 하지 않는다. 현재 제출본은 준용의 c898be2(보고서 61쪽, 43항목 대조)이며 원본은 `claude/report/`와 `claude/submission/`에 그대로 있다.

PPT 생성 중인 `yejun/presentation/`은 한 파일도 이번 커밋에 넣지 않았다. 작업 중이던 로컬 `main`에는 이미 과거 발표자료 초안 커밋 f2b274e가 있어, 그 계보를 push하면 PPT도 GitHub로 올라간다. 그래서 **PPT 이력이 없는** `codex/press-frontier-handoff-20261008` 브랜치에 이 인수인계만 올린다. Windows에서는 이 브랜치로 이어간다.

## 받은 근거와 완료물

- 사용자 경쟁팀 검토 원본: `yejun/analysis/press_competitor_review_2026-10-08/`(함께 인계). 당시의 우리 평가 E05는 56쪽 b05570e 기준이므로 현 61쪽에 그대로 적용하지 않는다.
- `review/current_report_audit.md`: 현재 보고서의 주장/반례/필요 수정 및 우선순위. 특히 진동 탐지, 통합 오경보 예산, 스트림 동등성, 합성 주입 onset 문제를 확인했다.
- `review/competitor_ideas.md`: 1위 chlanstjr0301/workspace---claude 커밋 518f9ada91fa8adb858ef59ed7c523eaf6e77b02의 공개 코드/평가 분석. 선택·평가 자료 재사용 및 과민한 계측 섭동 문제도 기록했다. 경쟁 모델 코드는 복사하지 않았다.
- `PROTOCOL.md`: 신규 이상 파일을 보기 전에 정한 후보, 정상 개발 구간, 단일 기록 단위 경보 예산, 합성 주입·탈락 규칙. 이미 원래 데이터의 test를 팀이 봤으므로 이 실험은 **사후 재평가**이지 독립 외부 검증이 아니다.
- `vibration_branch.py`: 과거 최대 5행에서 진동 잔차를 예측해 Ledoit-Wolf 거리로 채점하는, 인과적 진동 보완 경로. 원신호 Ridge/차분 Ridge, 즉시/3행 평균 옵션. current를 과거 입력에도 사용하므로 엄밀한 전류 독립 경로는 아니다.
- `competitor_reference.py`: 정상 기록에서 10행 23특징 PCA-MSPC 및 15진동특징 Mahalanobis를 학습하는 독립 구현 대조기. 원 경쟁팀의 창 단위 경보/수치 자체를 복제한다고 주장하지 않는다.
- `tests/test_vibration_branch.py`: 미래 suffix 불변, 기록 간 분리, 차분 경로 상수 이동 불변 등 12개 계약 검사. Mac의 `/opt/anaconda3/bin/python -m pytest -q yejun/analysis/press_frontier_improvement_2026-10-08/tests/test_vibration_branch.py`로 12개 통과. 경쟁 대조기는 인공 자료에서 23/15특징, 인과성, 단독/묶음 일치 확인. 실제 이상 채점은 하지 않았다.
- `source_manifest.json`: 손대면 안 되는 원본 보고서 Markdown/PDF/HWPX/제출 ZIP의 SHA-256.
- `build_report.py`: 복사 Markdown을 HTML과 검토용 PDF로 렌더하는 보조 스크립트. Windows Chrome 경로 또는 `--chrome` 지정 지원, Python 패키지 markdown/beautifulsoup4/PyMuPDF/Pillow 필요. `yejun/presentation/`을 참조하지 않고 선택적으로 `복사보고서/assets/`의 글꼴을 사용하며, 없으면 시스템 한글 글꼴로 폴백한다. 기존 Mac PDF는 40쪽의 **별도 검토 레이아웃**이고 원래 한컴 양식 61쪽과 다른 것임을 명시한다.

보고서 작업 복사본: `yejun/결과보고서_북적북적_경쟁모델융합_개선안_2026-10-08/결과보고서_북적북적_경쟁모델융합_개선안.md`. **현재는 원본 원고와 동일한 출발점**이다. `figures/`에는 원본 보고서의 그림 14개를 복사해 두었다. `원본보관/final_v5.md`는 시작점 백업이다. `.pdf`와 `.hwpx`는 `yejun/.gitignore`가 제외하므로 이 브랜치에는 없다. Mac의 생성 HTML/미리보기 이미지도 업로드하지 않는다.

## Windows에서 바로 할 일

1. 브랜치 `codex/press-frontier-handoff-20261008`을 체크아웃하고, `source_manifest.json`의 SHA-256로 원본 확인. Python 3.12+ 및 numpy/pandas/scipy/scikit-learn/pytest가 있는 환경 사용. 데이터 CSV 두 개의 위치와 SHA-256는 `yejun/press_submission/press/data.py`를 따른다.
2. `PROTOCOL.md`대로 **정상 개발 기록만**으로 후보 결합·보정 실험 스크립트를 새 분석 폴더에 만든다. 각 경로를 개별 α=1%로 보정해서 OR하지 말고, 결합 점수의 정상 calibration **기록 최대값**을 하나의 α=1%로 보정한다. 정상 기록 120개에서 α=0.5%씩 쪼개면 최소 conformal p=1/121라 어느 경로도 켜지지 않는다.
3. 후보 고정·해시 기록 뒤 A/B 기존 test, 실제 이상 사건, 진동/전류 합성 주입, 부하/센서 오프셋/시각 흔들림을 각각 평가한다. 기존 주입기 `core.Generator.inject`의 감쇠 충격은 전체 기록 평균을 빼서 **선언된 onset 이전 표본도 바뀐다**. 새 첫 경보 지연 시험은 주입 전 표본이 원래와 동일한 인과적 주입기를 쓴다.
4. 값이 좋아진 후보만 복사 보고서에 조건과 한계를 함께 기록한다. 악화되면 악화 수치와 채택 거부를 기록한다. 공식 잠금 모델을 사후에 다시 고른 것처럼 쓰거나, 합성 실험을 실제 고장 전 선행 시간으로 쓰지 않는다. `review/current_report_audit.md`의 절별 수정 위치를 따른다.
5. 새 그림/절 수정 뒤 `build_report.py`로 검토 PDF를 만들 수 있다. 한컴 양식 HWPX는 Windows에서 `claude/report/build_hwpx.py`를 **읽기만 하면서**, 입력/출력 절대경로를 복사 보고서 쪽으로 주어 별도 조립한다. 새 그림을 추가하면 builder의 FIGS 대응을 새 작업용 복사본에서 갱신하고 원본 builder는 수정하지 않는다. 수치 대조·레이아웃·원본 해시를 다시 확인한다.

## 보류와 기존 작업 보호

- 실험 실행기·선택 기록·평가 결과·최종 보고서 수정은 아직 없음. 이것들이 다음 단계의 핵심이다.
- 원본 `claude/`는 직접 수정하지 않는다. 프레젠테이션 관련 파일과 폰트는 이번 원격 브랜치에 포함하지 않는다.
- Mac의 로컬 `main`에는 이 작업 전부터 다른 미커밋 변경/삭제가 많다. GitHub 인계 브랜치와 혼동하여 그 상태 전체를 `git add -A`로 올리지 않는다.
