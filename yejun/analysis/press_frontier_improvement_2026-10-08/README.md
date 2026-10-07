# 정상 전용 진동 보완 실험 — Windows 실행 결과

`b62f0ee` 인계 이후 고정된 PROTOCOL의 후보를 실행했다. 정상 개발로 **V2+VD3@1**을 선택하고 잠근 다음 기존 이상 파일을 읽었다. 이 연구는 이미 알려진 같은 자료의 **사후 재평가**다. 기존 공식 모델 교체나 실제 대회 순위 상승을 주장하지 않는다.

| R1 없는 전체 이상 21기록 평가 | 기존 v2 A / B | 선택 후보 A / B |
|---|---:|---:|
| 행 F1 | 0.961938 / 0.970990 | 0.968186 / 0.974490 |
| 정상 오경보 기록 | 0/120 / 3/180 | 0/120 / 3/180 |
| 이상 탐지 기록 | 21/21 / 21/21 | 21/21 / 21/21 |

진동 잡음·충격 주입 탐지는 늘었지만 B 전류 왜곡은 43.84→41.48%, 지속 진동 증폭은 17.85→17.50%로 낮아졌다. 0.5ms 시각 흔들림의 정상 경보율은 A 95.0%, B 97.2%로 그대로 높다. 강도·채널·시작 위치·seed별 결과와 무주입 대조를 함께 읽는다. A/B는 중복 자료이며 이상 21기록은 한 사건이다.

## 실행 환경

Windows 11, Python 3.14.7에서 `requirements-windows-lock.txt`의 모든 패키지를 설치했고 `pip check`가 통과했다. 이번 PC 실행 환경은 `%TEMP%\k-manufacturing-frontier-py314`다. 다른 PC에서는 아래처럼 별도 가상환경을 생성한다. HWPX/PDF 조립은 설치된 한컴오피스가 필요하며 이번에는 한글 2020으로 확인했다.

저장소 루트의 PowerShell에서:

```powershell
py -3.14 -m venv "$env:LOCALAPPDATA\k-manufacturing\frontier-py314"
$frontierPython = "$env:LOCALAPPDATA\k-manufacturing\frontier-py314\Scripts\python.exe"
& $frontierPython -m pip install -r yejun/analysis/press_frontier_improvement_2026-10-08/requirements-windows-lock.txt
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
```

원본 CSV는 이 PC의 `데이터셋/3. 소성가공 예지보전 AI 데이터셋/`에 있다. 이 폴더에 `press_data_normal.csv`와 `outlier_data.csv`가 있으며, 실행기가 원본 해시·행 수·기록 경계를 검사한다. Mac 인계 문서의 이전 절대경로를 만들거나 원본을 이동할 필요는 없다.

```powershell
# 새 정상 전용 선택 + 잠금 + 사후 평가. 새 결과 폴더를 지정한다.
& $frontierPython yejun/analysis/press_frontier_improvement_2026-10-08/run_experiment.py --data-dir '데이터셋/3. 소성가공 예지보전 AI 데이터셋' --output yejun/analysis/press_frontier_improvement_2026-10-08/outputs_reproduction --phase all

# 기존 잠금 후보의 평가만 재현한다. 저장된 평가 CSV를 다시 쓰므로 필요하면 먼저 보존한다.
& $frontierPython yejun/analysis/press_frontier_improvement_2026-10-08/run_experiment.py --data-dir '데이터셋/3. 소성가공 예지보전 AI 데이터셋' --phase evaluate

# 계약 검사, 저장 예측 재계산, 실제 자료 참조 재생
& $frontierPython -m pytest -q -p no:cacheprovider yejun/analysis/press_frontier_improvement_2026-10-08/tests
& $frontierPython yejun/analysis/press_frontier_improvement_2026-10-08/verify_results.py
& $frontierPython yejun/analysis/press_frontier_improvement_2026-10-08/verify_replay.py --data-dir '데이터셋/3. 소성가공 예지보전 AI 데이터셋'
```

초기 실행은 정상 개발 약 30초, A/B 평가 약 343초였다. 참조 재생 검수는 약 125초이며, 배포 추론 지연 측정값이 아니다. 실제 실행시간은 PC와 동시 작업에 따라 달라진다.

## 산출물과 검증 범위

| 파일 | 의미 |
|---|---|
| `outputs/config.json` | 후보 59개·별도 OR 4개·분할·주입·섭동·선택 기준 |
| `outputs/development_candidates.csv` | 선택 가능 56개 중 31개 관문 통과, 탈락 포함 모든 후보 |
| `outputs/selection.json`, `selection_lock.json` | 정상 전용 선정, 설정·코드·선정표 해시 |
| `outputs/actual_metrics.csv` | 모든 후보·3개 α·이상 앞10/뒤11/전체21, R1 없음 |
| `outputs/A_injection.csv`, `B_injection.csv` | 인과적 주입의 가족×채널×강도×onset×seed별 탐지·대조·지연 |
| `outputs/A_stress.csv`, `B_stress.csv` | 계측·부하 대리변형 및 센서 고정 반응 |
| `outputs/local/` | 행 예측 및 짝지은 주입 상세 기록. Git 제외, 실행 시 재생성 |
| `outputs/verification.json` | 실제 지표 1,134행 재계산, 모든 후보 conformal/OR 경보 확인, 기존 v2 재현, 선정 모델·v2의 주입 상세 집계 확인 |
| `outputs/replay_verification.json` | A 28기록·844행, B 29기록·824행의 sample/chunk/batch 경보 일치, 점수 최대 차이 약 1.42e-14 |
| `outputs/report_facts.json` | 보고서에 사용한 수치와 원자료 대응 |
| `outputs/report_layout_audit.json` | 한컴 결과물 원고 포함 여부·PDF 레이아웃 검사 |

잠금 SHA-256: `20c992cd930c02c59f3ef4d3b7cccc1b15e2f3eda1fd78065fd06452a3c1ce2b`.
선택 이후 잠긴 실험 코드나 설정을 바꾸지 않았다. Git에서 JSON/CSV의 자동 줄바꿈 변환을 끄는 `.gitattributes`를 두어 잠금 파일의 바이트를 보존한다.

계약 검사 75개가 통과했다. 미래 suffix 불변·기록 간 분리·정상 학습/보정 분리·직렬화·주입 전 불변·잠금 변조와 잠금 전 이상 접근 차단을 포함한다. 실제 자료 참조 재생은 모든 이상 기록과 길이/위치로 고른 정상 대표 기록에 한정하며 전체 정상 test 스트림의 배포 검증이 아니다. 원본 보고서·PDF·HWPX·제출 ZIP 해시는 유지했다(Markdown은 Git CRLF를 LF로 정규화하여 대조).

최초 후보 격자에는 기존 특징 맞춤 5NN과 3채널 RidgeForecast를 넣지 않았다. 아래 검수 보완에서 두 기준선을 같은 조건으로 추가 대조했으며 원래 선택을 바꾸지 않았다. 새 VR/VD 2채널 잔차 경로의 OR를 기존 Ridge 병행 실험의 재현이라고 해석하면 안 된다. 최소점수 참고 비교기는 독립 α 경보의 AND와 다르다. 센서 고정은 고장 반응으로, 일반 nuisance 오경보와 구분한다.

## 보고서 조립

**현재 보류:** 아래는 이전 커밋에서 수행한 보고서 작업 기록이다. 사용자 지시에 따라 이번 ZIP 통합·검수 보완 결과는 보고서 원고·HWPX·PDF와 생성기에 반영하지 않았다.

보고서 복사본의 2.8절·요약·적용 조건·5장 그림15·6장 재현 설명에 결과를 반영했다. 기존 43개 대조 통과 이력은 원본의 실행 기록으로 남겼으며 이번 신규 실험의 테스트 75개와 구분한다. 첫 페이지 요약을 줄이고 그림 설명이 그림과 함께 놓이도록 한컴 문단 설정을 조정했다.

```powershell
& $frontierPython yejun/analysis/press_frontier_improvement_2026-10-08/update_report.py
& $frontierPython yejun/analysis/press_frontier_improvement_2026-10-08/build_hwpx_copy.py --figure-map yejun/analysis/press_frontier_improvement_2026-10-08/figure_map.json
& $frontierPython yejun/analysis/press_frontier_improvement_2026-10-08/audit_hwpx_pdf.py --hwpx 'yejun/결과보고서_북적북적_경쟁모델융합_개선안_2026-10-08/결과보고서_북적북적_개선본.hwpx' --output yejun/analysis/press_frontier_improvement_2026-10-08/outputs/report_layout_audit.json
```

`update_report.py`는 현재 복사 원고에 신규 실험 부분을 반영한다. 초기 원고나 원본을 덮어쓰지 않는다. HWPX/PDF는 `yejun/결과보고서_북적북적_경쟁모델융합_개선안_2026-10-08/`에 별도로 저장하며 Git에는 기존 제외 규칙에 따라 올리지 않는다. 표지 서명 및 만족도 조사 캡처는 실제 제출자가 마무리할 양식 항목이다.

## 모의 재채점과 인용 정정

서로 분리된 AI 평가 3개에서 기존 61쪽은 평균 85.0점, c7947f7 개선본 65쪽은 88.5·88.5·86.0점으로 평균 87.7점이었다. 공식 심사 결과나 실제 순위가 아니다. 항목별 근거와 평균은 [재채점 결과](review/regrade_c7947f7/summary.json), 수정 전후와 남은 한계는 [보완 내역](review/regrade_c7947f7/changes.json)에 있다. 과거 56쪽 평가 점수와 평가자·대상이 달라 직접 연결하지 않는다.

이후 사용자 지적에 따라 제출 원고의 참고문헌 29번을 실제 사용한 Ledoit–Wolf 수축 공분산 원논문으로 정정하고 관련 본문 인용과 파일명을 고쳤다. 재생성 코드와 내용 검사에도 반영했다. 이 문구 정정으로 위 고정 평가 점수를 바꾸지 않았으며 실험 수치·모델 선택·원본 자료는 유지했다.

## 제출 ZIP 통합과 독립 검증 범위

기존 제출 파이프라인과 이번 실험을 [통합 패키지](../../submission/press_integrated_2026-10-08/README.md)로 묶었다. ZIP 안의 `python run_all.py --extra-audits`는 기존 26단계, 신규 실험 전체, 수치·재생·별도 수식 검산, 고정 상태 생성, 강한 기준선·정상 조건 민감도 감사와 108개 계약 검사를 연결한다. 배포본에서는 선택 대상이 아니었던 비교기 3개를 제외해 선택 가능 56개와 별도 OR 4개를 유지했다. 원래 실험 기록과 잠금은 보존했다. 기존 공식 경보와 신규 후보의 출력은 구분하며 기존 모델을 교체하지 않는다. 검증 실행과 최종 ZIP의 관계는 통합 폴더 `verification/`에 보존한다.

추가 데이터가 없다는 사용자 확인과 [로컬 자료 감사](outputs/independent_data_audit.json)에 따라 새 날짜·고장 사건에 대한 독립 성능 검증은 수행하지 않았다. 원자료 사본과 라벨 없는 캐시도 기존 파일과 동일하다. A/B 재분할이나 합성 주입을 새 독립 사건으로 세지 않는다.

대신 VD3의 지연 입력, Ridge 정규방정식, 수축 공분산, 거리와 이동평균을 별도로 구현해 [19,104행 계산 검산](outputs/independent_implementation_verification.json)을 수행했다. A/B 보정·시험 구간과 알려진 이상을 포함하며 구간 간 자료가 겹친다. 최대 점수 차이는 약 3.41e-12이고 세 α의 경보 불일치는 0이다. V2 전체를 새로 구현한 검산은 아니다.

`validate_holdout.py freeze`는 기존 정상 자료의 고정 학습·보정 구간으로 상태를 만들어 JSON으로 저장한다. 새 CSV의 `evaluate`는 이 상태만 사용해 재학습·재보정·재선택 없이 평가한다. 동결 상태의 기존 시험 11,387행에서 두 모델의 경보가 모두 일치했다([상태 생성 검증](outputs/frozen_holdout_manifest.json)). 새 입력의 중복·시간 이동·부분 복사·스키마·기록 경계와 상태 변조를 검사하는 계약 17개를 추가했다. 입력 출처 선언과 중복 검사만으로 실제 고장 사건의 독립성이 입증되지는 않는다. 사용법과 출처 양식은 통합 ZIP의 README에 있다.

## Claude 검수와 겹침을 대조한 보완

[검수 대응 기록](review/claude_review_resolution_2026-10-08.json)에 이미 해결한 항목, 추가로 수용한 점, 채택하지 않은 제안과 보고서 반영 보류를 구분했다. 패키지·공통 환경·고정 상태 준비를 중복 수행하지 않았고, 실제 결과를 보고 새 문턱이나 경보 억제 규칙을 추가하지 않았다.

[강한 기준선 대조](outputs/strong_baselines/summary.json)에서 전체 21기록·α 1% 행 F1은 통합 후보 A 0.968186/B 0.974490, 특징 맞춤 5NN A 0.969072/B 0.971771이었다. 두 방법 차이의 쌍 기록블록 부트스트랩 구간은 A/B 모두 0을 포함한다. 우월성이나 동등성 입증으로 해석하지 않는다. 기존 3채널 Ridge는 실제 이상에서 낮았지만 진동 잡음 주입 탐지율은 A/B 모두 통합 후보보다 높았다. 모든 비교는 이미 관측한 한 사건과 기존 정상 자료에 대한 사후 대조다.

[정상 조건 민감도](outputs/normal_sensitivity/summary.json)는 이상 파일을 읽지 않았다. 겉보기 주파수 −0.1 Hz 이동에서 선택 후보는 정상 A 18/120, B 53/180기록에 경보를 냈다. 선택 시 사용한 네 주입 가족 중 하나씩 빼면 4회 중 2회 다른 후보가 1위가 됐다. 새 세 주입 가족 전반에서 우월성은 없었으며 보정 기록 1개에 진동 충격이 섞여도 탐지 민감도가 낮아졌다. 원래 선택과 보정·경보 규칙은 유지했다. 별도 검산기가 33,600개 기록·시나리오 결과를 224개 집계와 대조했다.

추가 고장 자료가 없는 상태에서 확률 층을 다시 맞추거나, 새 60초 승격 규칙 또는 주파수 기반 경보 억제를 붙이는 제안은 채택하지 않았다. 수축 공분산의 이유를 각 기록 초반의 표본 부족으로 설명하는 예시도 실제 전체 정상 학습 방식과 맞지 않아 제외했다. 문장·기여도·인용 설명에 관한 타당한 지적은 보고서 작업 재개 때 반영할 항목으로 남겼다.
