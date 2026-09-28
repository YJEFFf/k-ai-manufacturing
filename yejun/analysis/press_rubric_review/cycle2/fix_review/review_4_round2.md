# 검수 4 · 2라운드 — 적대적 검수 J2 보완 작업본(110afa2 대비) 독립 검토

- 작성: 2026-09-29, 처음 보는 독립 검토자
- 대상: `r4snap/yejun`(작업본 사본)과 `CHANGES_vs_110afa2.diff`. 원 저장소는 읽기만 했다. 사본에 없는 파일 두 개(`analysis/press_guard_review/README.md`, `analysis/press_external/metrics.csv`)는 원 저장소에서 내 작업 폴더로 복사해 점검했다.
- 방법
  - 팀 코드를 import하지 않는 독립 구현(`review4_indep.py`)을 만들었다. 원본 CSV와 동결 `guard_{A,B}.json`만 읽고 기록 경계, matched 양자화, 세 성분, ExpTail 변환, conformal p를 다시 계산한다.
  - 이 구현은 동결 예측(`outputs/predictions_abnormal_*.csv`·`predictions_normal_*.csv`)과 경보·근거·크기 센서가 완전히 같다. g 점수 최대 차이는 7e-14다.
  - 팀 스크립트는 사본을 한 번 더 복사한 `review4_work/`에서만 돌렸다.
  - 비교 기준선 `review4_base/`는 diff를 거꾸로 적용해 110afa2 상태로 되돌린 트리다.

## 1. 결론

- **수치 주장(1·2·3)은 모두 재현된다.**
  - 독립 구현으로 다시 만든 `current_offset.csv` 6행과 `sampling_jitter_stress.csv` 18행이 팀 CSV와 한 칸도 다르지 않다.
  - 흔들림 0 조건의 재구성 오차는 최대 9e-13이고, 양자화 뒤 달라진 값은 0행이다.
- **새 구현(jitter_stress·current_offset)에서는 결함을 찾지 못했다.** 기록 경계·마스크 정렬, 첫 경보 성분, 난수 재현, 평가 구간 선택을 모두 확인했다.
- **문제는 해석과 마무리에 있다.**
  1. **흔들림 설명은 과장이다(R4-03).** 「이상 파일의 파형 흐트러짐도 수집 시각 변화로 설명될 수 있다」는 R² 하나를 맞추도록 고른 2.4 ms에 기댄다(순환 논리).
     - 같은 흔들림을 준 정상 기록은 82~84%가 0.6 Hz 적합을 유지한다. 이상 기록은 0/17이다(중앙 0.22 Hz).
     - 표본마다 독립인 흔들림으로는 이상 파형이 재현되지 않는다.
  2. **v2는 수준 치우침에 둔감하지 않다(R4-04).** 예측 오차(AR(2)) 성분이 기록 수준 이동에 강하게 반응한다.
     - 정상 평가 기록 전류에 +230을 더하면 A 67/120, B 174/180 기록이 경보한다.
     - 경보는 거의 모두 「전류 파형·계측 확인」 행으로 간다. 그런데 이 행의 점검 항목에는 「영점」이 없다.
     - 「v2 경보는 이 치우침에 기대지 않는다」는 이 이상 파일에 한해서만 맞다.
  3. **분석 실행 뒤 model.py를 고쳤다(R4-01·R4-02).**
     - press_evidence 계약 검사가 7건 실패한다. 110afa2 재구성 트리는 44/44 통과한다.
     - `decision_table_diagnosis_v2.csv`의 model.py 행 인용 3곳이 지금은 엉뚱한 줄을 가리킨다.
     - press_guard verify도 58/59다. 실패 범위가 「알려진 1건」보다 넓다.
- 웹과 verify 변경은 의도대로 동작한다. 빈 조치 처리·약한 시험·옛 화면 캡처는 경미하다.
- 중대 결함은 없다. 보통 4건, 경미 8건이다.

## 2. 주장별 판정

| # | 판정 | 근거·재계산 값 |
|---|---|---|
| 1 전류 수준 치우침 | 확인 | 독립 재계산(matched, 길이≥10, ddof=1) 결과는 다음과 같다. \|평균\|>SD는 정상 0/530·이상 9/17이다. 모든 값이 양수인 기록은 0/530·5/17이다. \|평균\| 최대는 62.747(→62.7)·272.43이고, 시간순 이웃 평균 상관은 −0.0025·0.8131이다. raw 값이나 ddof=0으로 바꿔도 같다. 길이≥17로 좁혀도 0/469 대 7/14, 양수 0/469 대 3/14, 상관 −0.020·0.810으로 결론이 같다. 이상 16쌍 상관의 피셔 95% 구간은 0.53~0.93이다. `class_differences.csv:11`의 인용도 맞다. 해석 조건 하나는 R4-12에 적었다. |
| 2 v2가 치우침에 기대지 않음 | 부분(수치 확인, 해석 불완전) | 독립 v2 구현으로 모든 수치를 재현했다. 원자료 A 556·B 569행이 전류 평균 제거 뒤 555·567행이 되고 21/21구간은 그대로다. 전류가 최댓값인 크기 경보는 0행이다. waveform은 472·481로 변하지 않고, dynamics는 408→411·426→427이다. 정상 평가 B는 3→4다. 행 단위로 보면 A에서 경보 3행이 꺼지고 2행이 켜졌다. dynamics 성분은 16행 꺼지고 19행 켜졌다(B 21·22). 이 파일에서의 결론은 맞다. 다만 예측 오차 성분 자체는 수준 이동에 강하게 반응한다(R4-04). |
| 3 흔들림 스트레스 | 확인(구현·수치) | 같은 시드와 추출 순서로 독립 재구현하니 18/18행이 모두 같았다(경보 기록 수, 2단계, R² 중앙, 첫 경보 성분). 다른 시드 1~5로 돌린 범위는 다음과 같다. 0.1 ms에서 A 7.3~9.0%·B 27.9~31.2%, 0.2 ms에서 A 68.5~72.3%·B 88.1~89.9%다. 60.0 Hz로 바꿔도 A 7.8%·B 29.4%(평균)로 같다. 2.4 ms의 R² 0.480·0.472가 0.451과 비슷한 것은 2.4 ms를 R²에서 역산했기 때문이다(구성상 당연). 0.6 Hz 대조의 위상 잡음은 2π·0.6·2.4 ms=0.009 rad에 불과해 결과(B 17/725, 기준 15/725)가 자명하다. |
| 4 문서 해석 | 부분 | 문서의 수치는 CSV와 모두 일치한다. 변경된 표에서 깨진 칸은 0개다. 앨리어싱 산수도 맞다: 60.6×3=181.8→1.8 Hz, ×6=363.6→3.6 Hz이고 59.4 Hz로도 같다. 문제는 네 가지다: 「설명될 수 있다」의 과장(R4-03), 0단계 수치의 단위·조건 누락(R4-05), 출처 링크 오류(R4-06), 근거 없는 「설비 정지 없이」(R4-07). 치우침 지표의 해석 조건도 빠졌다(R4-12). |
| 5 판단표 | 부분 | action_for의 5개 분기와 수집 오류가 6행과 1:1로 대응한다. `test_decision_table_is_the_action_rule` 실패는 알려진 상태다. `test_serve`는 외부 metrics.csv를 넣으면 14/14 통과하고, 판단표 6행·키 검사도 여기에 포함된다. 남은 문제는 세 가지다: 영점 이동이 실제로 도착하는 파형·예측 오차 행에 영점이 없다(R4-04). FM6 대응표가 갱신되지 않았다(R4-10). model.py 행 인용이 어긋났다(R4-01). |
| 6 웹 콘솔 | 부분 | `node test_web.cjs`가 통과한다. 실제 서버 사건(A 1·B 4)에는 모두 action이 있다. 대기열에는 조치가 보이고 확률은 빠졌으며, 상세 패널 라벨은 「이상 확률(참고)」이다. 다만 빈 조치일 때 문구가 끝에서 끊기고, 새 시험은 조치 값을 확인하지 않는다(R4-08). 커밋된 콘솔 캡처는 옛 화면이다(R4-09). |
| 7 verify.py 정리 | 확인 | `ARTIFACTS`·`_close`를 참조하는 곳은 사본 전체에 없다. 제거 뒤 digest·regression 시험을 포함해 pytest 139개가 통과한다. README 설명도 코드와 맞다: 결과 CSV 1e-9+1e-7, 행별 float32 1e-9+1e-6, 열 요약은 개수 정확·상대 1e-6, ECDF 열(score·g_*)은 g≤1.35에서 절대 1e-3·요약 1e-4다. `--freeze`는 audit 통과를 요구한다. 모델 동등성의 허용오차 표기만 다르다(R4-11). verify 자체는 산출물 미재생성 때문에 지금 58/59다(R4-02). |

## 3. 결함

| ID | 심각도 | 위치(파일:행) | 내용 | 재현 | 권고 |
|---|---|---|---|---|---|
| R4-01 | 보통 | `analysis/press_evidence/manifest.json:13`, `diagnostics_manifest.json:16,65`, `decision_table_diagnosis_v2.csv:2,10,11`(`expected/` 사본도 같음), `expected/`(신규 2표 없음). 원인은 `press_guard/model.py:64-85` | 두 실행 기록의 model.py 해시는 수정 전 값 `89d6ce4a…`인데 현재 파일은 `0d1f39ff…`다. 계약 검사 FAIL 7건: 코드 해시 2, cited 1, class_differences 모양, 동결 없는 신규 2표, failure_mode_map 문자열. 110afa2로 되돌린 트리는 「통과(결과 44개)」다. 사본에서 build_diagnostics를 다시 돌리면 인용이 model.py:95→101, 377→383, 412→418로 바뀐다. 현재 파일의 95·377·412행은 action_for의 return 문·빈 줄·`mag=` 계산이다. 원래 가리키던 곳은 alert_units·fit·초반 6→8 전환이다 | `python analysis/package_contract.py --package analysis/press_evidence`(`review4_contract_check.log`, 기준선 `review4_contract_base.log`). build_diagnostics 재실행(`review4_build_diagnostics.log`) 뒤에도 동결값 비교 5건이 실패한다(`review4_contract_after_rerun.log`) | model.py를 확정한 뒤 build_tables→build_diagnostics를 다시 실행한다. 무결성 통과를 확인한 다음 `--freeze`로 동결값을 갱신한다 |
| R4-02 | 보통 | `press_guard/outputs/manifest.json`(코드 해시), `verify.py:184`, `test_analyze.py:84,176` | model.py·verify.py·web/app.js를 실행 기록 뒤에 고쳐 verify가 58/59(outputs.integrity FAIL)다. 110afa2 트리는 59/59다. 알려진 `test_decision_table_is_the_action_rule` 외에 `test_verify_detects_tampering`도 실패한다. 사본 전체 pytest는 3 실패·139 통과·1 건너뜀이다. 세 번째 실패(`test_serve` external 18행)는 사본에 `analysis/press_external/metrics.csv`가 없어서 생긴 것으로, 파일을 넣으면 14/14 통과한다 | `review4_verify_current.log`, `review4_verify_base.log`, `review4_pytest_press_guard_full.log`, `review4_pytest_serve.log` | train/analyze→audit→`verify --freeze`를 다시 실행한다. 인계 문구의 「알려진 실패」를 verify 무결성과 tampering 시험까지 넓혀 적는다 |
| R4-03 | 보통 | `analysis/press_evidence/README.md:377`, `press_guard/README.md:229` | 2.4 ms는 R² 0.451에서 역산한 값이라, 흔들린 정상 기록의 R² 0.48·0.47이 비슷한 것은 독립 증거가 아니다. 같은 조건에서 다른 지표는 이상 기록과 맞지 않는다. 적합 주파수는 흔들린 정상 기록이 중앙 0.6 Hz, 0.6±0.05 Hz 안 82%(A)·84%(B)이고 이상은 중앙 0.22 Hz, 0/17이다. \|평균\|>SD는 0% 대 53%, 적합 잔차 lag-1은 −0.10 대 +0.09다. 3.5 ms로 키워도 0.6 Hz가 42% 남는다(R² 0.27). 기록 안 lag-1(0.39 대 0.44)만 비슷하다. 표본마다 독립인 흔들림으로는 이상 파형을 설명하지 못한다. 팀 CSV(`class_differences.csv:13`, 0.6 대 0.22 Hz)에 이미 있는 반대 증거를 이 문장이 다루지 않는다 | `review4_jitter_features.py`·`review4_jitter_features_B.py`(.log) | 「R² 크기만 같다. 적합 주파수는 독립 흔들림으로 재현되지 않아 이 스트레스로는 이상 파형을 설명하지 못한다. 표본화 주기 편차 같은 다른 수집 가설과 실제 설비 변화는 시험하지 않았다」로 고친다 |
| R4-04 | 보통 | `analysis/press_evidence/README.md:70-71`, `build_tables.py:230,232`(`class_differences.csv:10` 「예측 오차(상수항, 약함)」), `press_guard/model.py:74-76`, `OPERATIONS.md:18` | AR(2) 잔차는 상수 이동 δ에 0.142·δ(=1−φ1−φ2)만큼 움직이고, dynamics 꼬리 u는 22.0이다. 정상 평가 기록 전류에 δ를 더하면 +100에서 A 0/120·B 17/180(기준 0·3), +150에서 6/120·53/180, +230에서 67/120·174/180, +272에서 115/120·178/180 기록이 경보한다. 조치는 거의 모두 「전류 파형·계측 확인」이다(B +230에서 1056/1094행). 이상 파일 기록 15~20의 평균은 155~272다. 그러니 평균 제거 뒤 경보가 같은 것은 둔감해서가 아니다. 그 기록들이 이미 파형 흐트러짐으로 경보하기 때문이다(치우친 기록의 AR 잔차 중앙은 제거 뒤 86→94). 영점 이동이 도착하는 판단표 행의 점검 항목은 「전류 센서 접지·수집 장비 표본화 시각(먼저)…」이라 영점이 없다. OPERATIONS 4단계의 「계측(…영점…)부터」와도 어긋난다 | `review4_offset_sensitivity.py`, `review4_offset_actions.py`(.log), 행 단위 뒤집힘은 `review4_claims12.log` | README R4에 「예측 오차 성분은 AR 상수항 때문에 기록 수준 이동에 반응한다」와 위 수치를 적는다. 「약함」은 「중앙값 22.9 수준에서는 약함」처럼 조건을 붙인다. 판단표 파형·예측 오차 행의 점검 항목 맨 앞에 「전류 센서 영점」을 넣는다(모델 불변) |
| R4-05 | 경미 | `press_guard/OPERATIONS.md:14`(0단계) | 「대회 정상 기록의 1단계 알림 A 8%·B 31%」는 평가 구간 길이≥17 기록(A 96·B 145) 가운데 경보 행이 있는 기록의 비율이다. 운영의 1단계 알림은 사건 단위다. 같은 시드 1회로 보면 B 0.1 ms에서 경보 기록 44/145, 사건 1단계 알림 31건, 2단계 격상 17건이다(경과 24.1분, 기준 3건·0건). 또 이 값은 흔들림 없이 보정한 동결 모델에 흔들림을 더한 결과다. 현장 자료로 재보정하면(1단계) 일정한 흔들림은 문턱에 흡수된다. 실제 요건은 「보정 뒤 흔들림이 늘지 않을 것」이다 | `review4_jitter_incidents.py`(.log) | 「경보 기록 비율」로 고친다. 사건 단위 수치나 「보정 자료보다 흔들림이 늘면」이라는 조건을 붙인다 |
| R4-06 | 경미 | `press_guard/OPERATIONS.md:18`, `press_guard/model.py:64-66` | 「\|평균\| > SD 9/17구간, 정상 0/530」의 출처로 current_offset.csv를 링크했다. 이 수치는 `class_differences.csv:11`에 있고, current_offset.csv에는 경보 수만 있다. model.py 주석도 치우침 관찰의 출처를 current_offset.csv로 적었다 | current_offset.csv에서 「9/17」「0/530」 각각 grep 0건 | class_differences.csv를 함께 링크한다 |
| R4-07 | 경미 | `press_guard/OPERATIONS.md:18`(「설비를 멈추지 않고 짧게 끝나며」), `press_guard/model.py:66` | 근거 파일이 없는 단정이고, 같은 표의 다른 가정과 달리 [가정] 표시도 없다. 점검 항목에 넣은 전류 센서 영점 확인은 보통 무전류 상태(설비 정지나 센서 분리)가 필요하다. 접지 점검에도 안전 절차가 따른다 | 문서 문구 확인(자료 근거 없음) | [가정]을 표시하거나 「부착·케이블 육안 확인은 운전 중, 영점은 정지 시」로 나눈다 |
| R4-08 | 경미 | `press_guard/web/app.js:295`, `test_web.cjs:48` | 대기열은 `권장 확인: ${esc(c.action)}`라서 조치가 없거나 빈 값이면 「권장 확인: 」으로 끝난다. 상세 패널(app.js:364)은 이때 「—」를 보인다. 새 시험의 사건 고정자료에는 action이 없어 `/권장 확인: /`가 조치가 빠진 상태에서도 통과한다. 실제 서버 사건은 모두 action이 있어 현재 화면 오류는 없다 | `node review4_web_queue.cjs review4_work/yejun/press_guard` → 사건 1~3이 「권장 확인: 」로 끝남(`review4_web_queue.log`) | `esc(c.action \|\| '—')`로 고친다. 시험 고정자료에 action을 넣고 값까지 확인한다 |
| R4-09 | 경미 | `press_guard/outputs/console/console_workspace_v2.png`, `capture.json`, `OPERATIONS.md:53` | 작업 화면 캡처가 옛 app.js(`73ba4539…`)로 찍혀, 대기열에 「이상 확률 55.0%(모형 상한)」이 보인다(`review4_console_crop.png`). 현재 app.js는 `ebeee818…`다 | 해시 비교, 이미지 확인 | `tools/capture_console.py`로 다시 찍는다 |
| R4-10 | 경미 | `analysis/press_evidence/failure_mode_map.csv:7`(FM6), `build_diagnostics.py:660-671`, `README.md:282` | FM6의 반응 성분은 「입력 검증, 크기(스파이크)」, 대리 주입은 「없음(직접 주입하지 않음)」 그대로다. 이번 흔들림 스트레스는 수집 이상(FM6)의 대리 주입이고, 반응 성분은 파형·예측 오차다. 판단표도 FM6를 파형·예측 오차 행의 후보로 둔다 | CSV·README 대조 | FM6 행에 흔들림 스트레스와 파형·예측 오차 반응을 적는다 |
| R4-11 | 경미 | `press_guard/README.md:218` | 「저장 모델·확률 보정기는 동결 사본과 SHA-256이 같거나 원소 단위로 같아야 한다」고 적었다. 그러나 `equivalence.py`는 \|차이\| ≤ 1e-10 + 1e-8·\|값\|을 허용한다. 나머지 허용오차 설명은 코드와 맞다 | `equivalence.py:17,55-58` | 허용오차를 적는다 |
| R4-12 | 경미 | `analysis/press_evidence/README.md:66`, `build_tables.py:173,236` | 「교류 순시값이면 구간 평균은 0 근처여야 한다」는 기록이 교류 한 주기 이상일 때만 맞다. 순수 0.6 Hz 사인도 10행이면 21%가 \|평균\|>SD다(12행 이상이면 0%). 이상 기록의 적합 주파수 중앙인 0.22 Hz 사인은 17행에서 57%, 25행에서 34%가 \|평균\|>SD다. 이 지표는 직류 치우침과, 기록보다 주기가 긴 느린 변동을 가르지 못한다. 결론(원인 미상)과 정상·이상 대비(길이≥17: 0/469 대 7/14)는 그대로다 | `review4_short_sine.py`(.log) | 해석 조건을 한 줄 붙인다. `OFFSET_MIN_LEN` 주석의 근거를 12행 이상으로 고치거나 길이≥17 결과를 함께 적는다 |

## 4. 문제없던 것

- **jitter_stress 구현**
  - 흔들림 0에서 원 신호가 복원된다(최대 8.95e-13, 양자화 뒤 차이 0행). 흔들림 없음 행(A 0/96, B 3/145)이 원 예측과 같다.
  - 기록 경계와 `keep` 마스크가 위치로 정렬된다(`reset_index` 뒤 같은 불리언 마스크).
  - 첫 경보 성분 규칙(활성 성분 가운데 g 최대)은 결과에 거의 영향이 없다. 성분이 둘 이상인 첫 경보 행은 0~4.5%다.
  - 조건마다 같은 시드로 난수를 다시 만든다(공통 난수). 평가 구간은 A 480·B 420 이후로 다른 표와 같다.
- **current_offset 구현**
  - `D.segments`가 numpy 배열을 돌려주므로 인덱스가 0부터가 아닌 평가 조각에서도 groupby가 위치 기준으로 맞게 동작한다.
  - 「원자료」 행과 변환 행이 같은 전처리 경로(predict 안의 matched 양자화)를 쓴다.
- **문서 수치와 CSV 대조**
  - README 흔들림 표 8행, R4 불릿, FM6 행, OPERATIONS 0·4단계, press_guard README 한계의 수치가 CSV와 모두 맞는다(반올림 포함).
  - 인용 `class_differences.csv:11`, `current_offset.csv:2-7`도 맞다.
- **마크다운 표**
  - 변경된 md 4개와 press_guard_review/README.md에서 칸 수 불일치가 0행이다.
  - 110afa2에서 깨져 있던 `HISTORY.md:116`, `press_guard/README.md:218` 두 곳이 이번에 고쳐졌다.
- **개수·재실행**
  - contract 46개(표 41·그림 5), build_tables 18표, build_diagnostics 23표가 실제와 같다.
  - build_tables를 다시 돌리면 18표가 바이트까지 같다.
  - build_diagnostics를 다시 돌리면 인용 행이 바뀐 decision_table_diagnosis_v2.csv 하나만 다르다(R4-01).
- **verify.py·시험**
  - verify.py 정리가 다른 모듈을 깨지 않는다.
  - press_evidence `test_diagnostics.py` 4개와 `test_web.cjs`가 통과한다.
- **현재 데이터에서 웹 조치 표시**
  - 사건 대기열의 조치(최우선 건)와 상세 기본 건(시간순 첫 건)의 조치가 모든 사건에서 같다.

## 5. 판단 불가

- 0.6 Hz가 앨리어싱인지, 원 주파수가 무엇인지, 실제 수집 흔들림이 얼마인지는 이 자료로 알 수 없다(시각 열이 명목값이다). 흔들림 스트레스는 가정별 민감도로만 읽어야 한다.
- 현장 센서 종류와 영점 점검 절차를 모른다. R4-07이 실제로 얼마나 걸릴지는 알 수 없다.
- 리눅스 x86-64 실측값(2.3e-4 등)은 다른 기기가 없어 확인하지 못했다.
- 사건 대기열 조치(최우선 건)와 상세 기본 건(시간순 첫 건)의 조치가 다른 사건은 현재 자료에 없어 표시 불일치 여부를 확인하지 못했다.
- 사본에는 원 저장소의 일부 폴더(press_external 등)가 없다. `test_serve` 1건 실패는 이 때문으로 보고, 파일을 복사해 통과를 확인했다.

## 6. 재현 파일(이 폴더)

- **독립 구현:** `review4_indep.py`
- **주장 1·2:** `review4_claims12.py`
- **주장 3**
  - 같은 시드 재현과 다른 시드: `review4_jitter.py` → `review4_jitter_same_seed.csv`·`review4_jitter_other_seeds.csv`
  - 파형 지표 비교: `review4_jitter_features.py`·`review4_jitter_features_B.py`
  - 사건 단위 비교: `review4_jitter_incidents.py`
- **수준 이동 민감도:** `review4_offset_sensitivity.py`, `review4_offset_actions.py`
- **짧은 기록 사인:** `review4_short_sine.py`
- **표 칸 점검:** `review4_mdtables.py`
- **웹 대기열:** `review4_web_queue.cjs`
- **로그:** 각 `.log`, `review4_pytest_*.log`, `review4_verify_{base,current}.log`, `review4_contract_{check,base,after_rerun}.log`, `review4_build_{tables,diagnostics}.log`
- **트리:** `review4_base/`(110afa2 재구성), `review4_work/`(실행용 사본), `review4_repo_copy/`(원 저장소 파일 사본)
- **실행 방법:** `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python review4_<이름>.py`. `review4_jitter.py`는 약 2분 걸린다.
