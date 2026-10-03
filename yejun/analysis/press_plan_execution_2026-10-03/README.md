# 10월 3일 플랜 실행·준용 작업 비교

실행: 2026-10-03~04 KST. 기준 커밋 `d48e8af`, [최종 실행 계약](../../plans/press_master_2026-10-03/08_execution_contracts.md)의 E1~E6을 구현하고 계산했다. 대회 제출 보고서가 아닌 코드·실험·검수 기록이다.

**같은 P2 분할·보정·기록 단위로 맞춘 비교에서는 준용의 고정 w=8 결합 모델이 F1 0.9333으로 더 좋았다. 새 플랜의 K1과 두 증강 비율은 모두 사전 채택 기준을 통과하지 못했다. `selected_candidate=null`이며 B1은 비교 기준으로만 유지한다.**

## F1부터 보는 동일 조건 비교

정상 0~40분 fit / 40~60분 cal / 60분 이후 평가, 완전 중복 제거와 경계 purge를 공통 적용했다. 평가 단위는 정상 **126기록 + 제공 이상 21기록**, 판정 시점은 기록 종료 후, 문턱은 실제 정상 cal 156기록의 동점 포함 순위 p≤0.05다. 날짜·파일명·정답은 모델 특징이 아니다. 이상 21기록은 **이미 살펴본 하나의 수집 에피소드**다.

| 모델 | F1 | 정밀도 | 재현율 | 정확도 | AUROC | AP | 정상 FP | 이상 FN |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 준용 고정 w=8 결합 | **0.933333** | 0.875000 | 1.000000 | 0.979592 | 1.000000 | 1.000000 | 3/126 | 0/21 |
| 플랜 전역 기준 B1 | 0.500000 | 0.352941 | 0.857143 | 0.755102 | 0.921391 | 0.803881 | 33/126 | 3/21 |
| 플랜 조건부 참조 C1d1 | 0.571429 | 0.428571 | 0.857143 | 0.816327 | 0.947090 | 0.841929 | 24/126 | 3/21 |

[전체 수치·confusion matrix](evidence/press_common_metrics.csv). AP는 average precision이며, AUROC와 AP는 원점수의 순위 성능이다. 준용 구조는 원래의 인과적 행 점수를 기록 안에서 최대로 집계한 뒤 같은 정상 순위 보정을 적용했다. w=8은 과거 탐색에서 사용한 고정 비교 기준이고 새 평가에서 고른 값이 아니다. 이 표는 **모델 구조를 같은 조건에 놓은 비교**이며 준용의 원래 행 예측 성능과 구분한다. C1과 K1·증강의 채택 실패를 이 표의 순위로 취소하지 않는다. 탈락한 K1·증강 후보는 플랜대로 보류 시험 목록에 다시 넣지 않았다.

## 준용 파이프라인 자체도 재실행했다

원래 두 분할 × 행/구간 보정 × 예산 1·3·5%의 **108셀**에서 TP/FP/FN/TN과 알림 기록 수가 저장값과 같았다. F1 최대 차이는 1.11e-16이다. 준용 폴더를 수정하지 않았으며 import의 bytecode 생성도 차단했다.

아래는 원래 **구간 보정 1% 예산, 전체 행 F1**이다. 정상으로 창 길이를 선택하는 실제 파이프라인 결과와 탐색용 w=8을 따로 남겼다.

| 분할 | 창 선택 | F1 | 정밀도 | 재현율 | 정확도 |
|---|---|---:|---:|---:|---:|
| 60/20/20 | 정상 선택 w=5 | 0.759049 | 1.000000 | 0.611667 | 0.950320 |
| 50/20/30 | 정상 선택 w=10 | 0.894204 | 0.997947 | 0.810000 | 0.982828 |
| 60/20/20 | 탐색 고정 w=8 | 0.915009 | 1.000000 | 0.843333 | 0.979957 |
| 50/20/30 | 탐색 고정 w=8 | 0.918149 | 0.984733 | 0.860000 | 0.986263 |

[재현 영수증](evidence/junyong_reproduction.json), [행 지표](evidence/junyong_historical_headline.csv), [108셀 전체](evidence/junyong_historical_metrics.csv). 위 행 F1과 첫 표의 기록 F1은 분모와 판정 시점이 달라 직접 빼서 향상률로 제시할 수 없다.

## 작업과 플랜의 차이

| 항목 | 준용 최신 작업 | 마지막 플랜 및 이번 실행 |
|---|---|---|
| 핵심 점수 | 표준화 센서 max-z + 전류 사인 적합 붕괴 | 기록별 AC 진동·전류 점수, 조건부 잔차, K1 경로별 정상 보정 |
| 입력 단위 | 행별 최근 관측 창, 원래 정상 600구간 | 중복 한 행 제거 후 정상 599기록; 짧은 기록도 유지 |
| 선택 근거 | 정상 창 선택과 기존 이상일 탐색 | P0/P1 정상 부담 + 개발 변화 + 감소·전류 무효 손실 |
| 증강 | 해당 파이프라인에 없음 | 실제 fit A0 / 반복 A1 / 동기 crop A2, 부모당 이웃 1개 |
| 외부 검증 | 해당 파이프라인에 없음 | SKAB 30수집 그룹, 237주석 충돌 통제, dev 후 동결 test |
| 확률 | 정상 꼬리 p값 | 별도 q 가중 라벨 확률 헤드와 상수 확률 대조 |
| 운영 정책 | 기록 알림 집계 | 동일 해제 규칙의 I0/P23, 단발·지속 변화 미탐 및 지연 검사 |

## 단계별 실행 결과

**E1 — SKAB 개발.** 고정판을 기존 해시와 대조해 다시 취득했다. fit 14·dev 5·cal 5그룹만 모델 개발에 열었고 test 6그룹은 동결 뒤 별도 명령에서 열었다. fit 정상 완성 블록 456개, cal 정상 완성 블록 105개, 추정 간격 1초다. 양쪽 라벨 충돌 237개를 재확인했다. 제공된 진동 RMS를 원시 AC 파형으로 다시 해석하지 않았다. [입력 집계](evidence/skab_development_input.csv), [접근 기록](evidence/skab_development_access.json), [cal 그룹별 기여](evidence/skab_cal_contributions.csv)

**E2 — K1.** 조건부 cal은 P0 49개·P1 106개로 주 α의 최소 39개를 충족했다. 조건 불가 시 B1의 점수·p·최종 판정 동등성은 정상과 모든 개발 주입에서 검사했다. 기존 감소·전류 무효 손실은 없어졌지만 정상 요청과 시간대별 증가가 채택 한도를 넘었다.

| 모델 | 개발 정상 요청/313 | D1 대표 POD | D2 대표 POD | D3 대표 POD | B1 대비 최악 손실 | 10분 구간 최대 추가 요청 |
|---|---:|---:|---:|---:|---:|---:|
| B1 | 14 | 1.9702% | 5.3781% | 13.2588% | 기준 | 0 |
| C1d1 | 13 | 8.7061% | 12.3269% | 11.2354% | −15.3846%p | +1 |
| K1 | 27 | 19.5953% | 25.3727% | 23.5889% | 0%p | **+7** |

K1의 작은 변화 민감도 향상은 확인했지만, 이를 전체 성공이라고 표시하지 않았다. 정상 요청 3건 감소 또는 두 계열 +10%p와 함께 **어느 10분 구간도 +1건 초과 금지** 등 모든 조건을 적용했다. [채택 판정](evidence/selection.json), [계열별 POD](evidence/press_family_pod.csv), [손실 셀](evidence/press_loss_cells.csv), [길이×게이트×경로별 cal 기여·판정 차이](evidence/K1_route_by_length_gate.csv)

**E3 — 증강.** 두 비율 0.5·1.0 × 학습 seed 11·29·47을 모두 계산했고, 각 학습판에 평가 주입 seed 11·29·47을 모두 교차했다. A1은 A0와 점수·p·판정이 같았으며 276,066개의 합성 질의에서 이 동등성을 확인했다. A2 생성 실패는 0개이고 각 부모의 작은 비율 자식은 큰 비율 자식 목록의 접두 부분이다. 실제 fit만 전처리를 적합하고 실제 cal만 문턱을 정했다.

A0의 정상 요청은 14건, A2는 여섯 설정 모두 15건이었다. B1 대비 최악 손실은 A0 −22.6415%p, A2 약 −22.64~−27.43%p였다. A0 대비 대조와 B1 대비 대조를 함께 적용해 **A2 두 비율 모두 탈락**했다. seed 평균으로 실패를 숨기거나 최상 seed를 선정하지 않았다. [생성 집계](evidence/augmentation_generation.csv), [A0 대비 민감도](evidence/augmentation_family_gain.csv), [A0 대비 손실](evidence/augmentation_loss_cells.csv)

**E4 — 확률·운영.** 후보 선정 뒤 B1·C1d1의 별도 라벨 확률을 적합했다. 정상 0~40분 점수 적합, 40~50분 헤드, 50~60분 문턱, 60분 이후 평가를 분리했고 이상 기록 0~13/14~20을 헤드/평가로 나눴다. 평가 133기록은 모두 지원됐다. q=0.1 가중 결과는 다음과 같다.

| 확률 헤드 | Brier ↓ | Log loss ↓ |
|---|---:|---:|
| 상수 q=0.1 | 0.090000 | 0.325083 |
| B1 | 0.078323 | 0.278357 |
| C1d1 | 0.078134 | 0.277352 |

모든 q=0.01·0.05·0.1·0.2에서 상수보다 두 손실이 낮았다. 이것은 **같은 이상 수집 에피소드 내부의 제공 라벨 구분 진단**이며 현장 고장 확률 검증이 아니다. [전체 확률 지표·분포](evidence/probability_metrics.csv), [최적화 상태](evidence/probability_heads.json)

P23은 정상 티켓을 14→0건으로 줄였지만, I0가 탐지한 단발 주입 재생 7,509건과 비영점 T1 재생 47건을 놓쳤다. 이 수는 중복 부모·시드·강도를 포함하는 **합성 시나리오 수**다. 개별 부모를 바꾼 전체 스트림을 각각 재생했고 서로 다른 주입을 하나의 스트림에 이어 붙이지 않았다. 추가 판정 지연 조건도 T1에서 실패해 **I0 유지**다. [정책 판정](evidence/press_policy_selection.json), [정상 부담](evidence/press_policy_normal.csv), [단발 집계](evidence/press_policy_single_summary.csv), [T1](evidence/press_policy_ramps.csv)

**E5 — 동결 후 평가.** [동결 파일](evidence/freeze.json)에 입력·코드·환경·명세·학습 상태·cal 배열·후보 null·정책·보류 생성기를 기록했다. H1/H2에는 B1과 C1d1만 넣었고 사용자 요청의 준용 구조 비교는 별도 P2 감사로 남겼다. H2에서 RMS 모델의 새 탐지는 0개였고 최대 점수 차이는 약 3.6e-15로, 예정된 위상 불변성 음성 대조와 일치했다. H1은 fit의 톤을 피한 모든 등록 주파수·강도·seed를 남겼다. [보류 곡선](evidence/heldout_curves.csv)

SKAB test에서는 아래 결과를 얻었다. 미완성 블록은 정상으로 삭제하지 않고 **기계 판정 유보(이진 집계에서는 0)·품질 요청**으로 모두 남겼다.

| 구조 | 전체 블록 F1 | 정밀도 | 재현율 | 기계 FP | 기계 FN | 점수 지원 | 확정 발생 사건 내 신규 탐지 |
|---|---:|---:|---:|---:|---:|---:|---:|
| G 전역 | 0.018605 | 0.666667 | 0.009434 | 1 | 210 | 189/584 | 0/7 |
| C 조건부 | 0.103448 | 0.600000 | 0.056604 | 8 | 200 | 189/584 | 0/7 |

395/584블록이 미완성이고 지원률은 32.3630%다. 품질 요청까지 합친 확정 정상 티켓은 G 245/372, C 252/372였다. 블록 F1 증가는 있지만 정상 부담 비증가 조건을 통과하지 못했고, 모든 그룹에서의 일관된 외부 개선은 미확인이다. 발생이 불명확한 구간, 관측 종료까지 미탐인 우측 검열 사건, 블록이 닫힌 뒤의 늦은 탐지는 별도 표로 남겼다. [합산 점수](evidence/skab_test_pooled.csv), [그룹별 점수](evidence/skab_test_groups.csv), [그룹 동일 비중 평균](evidence/skab_test_macro.csv), [라벨 범위](evidence/skab_test_bounds.csv), [사건 표](evidence/skab_test_events.csv), [외부 판정](evidence/skab_external_claim.json)

**E6 — 재현·검수.** 21개 신규 실행 테스트(그 안에서 기존 핵심 계약 18개 재실행), 독립 재집계·원행 보존·미지 CSV 추론·재적합/체크포인트 재로딩 검사 74/74가 통과했다. 별도 가상환경에서도 전체 E1~E6과 같은 검사가 통과했고, 집계·선택·압축 해제한 예측 파일 **54/54개가 정확히 일치**했다. [새 환경 대조 영수증](evidence/cold_reproduction.json). 측정 시간은 결정적 값 비교에서 제외한다. [검수](evidence/verification.json), [특징 계산을 포함한 추론 비용](evidence/inference_cost.csv)

첫 전체 실행은 동일 이름의 구버전 검수 모듈을 import하는 경로 충돌로 E6 직전에 멈췄다. 모델·선택 알고리즘을 바꾸지 않고 import 우선순위를 수정한 뒤 모든 비교를 재실행했다. 수정 전 동결과 집계는 `evidence/history/before_import_fix/`에 보존했고 수치 불변을 대조했다. [수정 기록](evidence/implementation_corrections.json)

## 실행과 파일

Python 3.14.7 / Windows에서 계산했다. 과거 Python 3.12 환경과의 차이는 기존 B1·C1 개발 집계 재현 및 준용 108셀 재현으로 검사했고, 현재 패키지는 아래의 새 환경에서 다시 실행했다. 원자료·환경·모델 상태·행별 예측은 Git에서 제외하며 집계만 버전 관리한다.

저장소의 `yejun/`에서 실행한다. POSIX에서는 가상환경 실행 파일 경로를 `bin/python`으로 바꾼다.

```powershell
python -m venv analysis/press_plan_execution_2026-10-03/.venv
analysis/press_plan_execution_2026-10-03/.venv/Scripts/python.exe -m pip install -r analysis/press_plan_execution_2026-10-03/requirements-runtime-lock.txt
python -X utf8 analysis/press_plan_execution_2026-10-03/prepare_data.py
analysis/press_plan_execution_2026-10-03/.venv/Scripts/python.exe -X utf8 -u analysis/press_plan_execution_2026-10-03/run_all.py all
analysis/press_plan_execution_2026-10-03/.venv/Scripts/python.exe -X utf8 analysis/press_plan_execution_2026-10-03/tools/summarize_contract_details.py
```

개발·동결·시험을 나누려면 `all` 대신 `development`, `freeze`, `test`, `verify`를 순서대로 쓴다. `test`는 동결된 코드·환경·입력·학습 상태가 바뀌면 중단한다. 새 출력 경로는 `--output <경로>/evidence`로 지정한다. 원자료 복구는 기존 공식 배포 파일의 해시를 검증하며 과거 취득 영수증을 덮어쓰지 않는다.

```powershell
analysis/press_plan_execution_2026-10-03/.venv/Scripts/python.exe -X utf8 analysis/press_plan_execution_2026-10-03/predict.py --input <센서CSV> --artifact analysis/press_plan_execution_2026-10-03/artifacts/press_frozen.pkl --output analysis/press_plan_execution_2026-10-03/cache/new_predictions.csv
```

추론 입력은 `TimeStamp`, `AI0_Vibration`, `AI1_Vibration`, `AI2_Current`다. 출력은 원행 대응과 **판정 가능 시각**을 함께 갖는다. 기록 결과를 앞 행에도 연결한 값은 사후 대응이며 조기 행 예측이 아니다. 순위 p값은 고장 확률이 아니다.

최종 상태는 [completion.json](evidence/completion.json)에 분리했다. 구현·외부 계산 완료와 후보 채택·현장 검증은 별개다. 선택 사항인 Beihang 보조 모델은 실행하지 않았으며, UCI·ESPset·추가 신경망·A3/O1·보고서·발표자료는 이번 실행 범위 밖이다. 새로운 최종 모델 채택은 없고 과거 v2로 복귀하지 않았다.
