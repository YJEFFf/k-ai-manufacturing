# 루브릭 검수 사이클 2 — 평가관 6명 반복 검수

예준 지시(2026-09-27): 평가 요소마다 평가관 에이전트가 점수를 매기고, 부족한 부분을 고친 뒤 다음 검수에서 고칠 수 있는 부족분이 나오지 않을 때까지 반복한다. 검수 기록이며 대회 보고서가 아니다. 공식 기준은 [official_task_extract.txt](../official_task_extract.txt)다.

## 1회차(round1, 기준 커밋 dcd300a)

| 평가관 | 항목(배점) | 점수 | 보고서 |
|---|---|---:|---|
| 01 | 데이터 이해 및 진단(15) | 12.5 | [judge_01_data.md](round1/judge_01_data.md) |
| 02 | AI 예측모델 개발(40) | 31 | [judge_02_model.md](round1/judge_02_model.md) |
| 03 | 영향요인 및 오류분석(15) | 11.5 | [judge_03_errors.md](round1/judge_03_errors.md) |
| 04 | 현장 활용방안(10) | 7.0 | [judge_04_field.md](round1/judge_04_field.md) |
| 05 | 창의성·차별성(10) | 8.0 | [judge_05_originality.md](round1/judge_05_originality.md) |
| 06 | 코드 및 재현성(10) | 7.5 | [judge_06_repro.md](round1/judge_06_repro.md) |
| | 합계(100) | **77.5** | |

평가관의 검증 스크립트·로그·JSON은 같은 폴더에 있다. 평가관은 이 폴더 밖을 고치지 않았다.

## 1회차 처리

| 평가관 항목 | 처리 위치 |
|---|---|
| 01 D1~D7, 05 O1(a)·O4 | `analysis/press_evidence/`(build_diagnostics.py, figures.py, 새 표 16개·그림 5장), `press_submission/README.md` 참조 두 줄 |
| 02 M1, 05 O2 | `press_guard/probability.py`, 예측 열, `outputs/probability_*`, `label_free_alert_probability_v2.csv` |
| 02 M2, 05 O5·O6 | `analysis/press_supervised/` v2(3ad2452) |
| 02 M3~M5, 05 O3, 03 E7 | `analysis/press_selection/` |
| 03 E1~E6·E8 | `press_guard/insights.py`와 보강 표·그림, README E6 문장 |
| 04 U1~U8, 05 O1(b)·O7 | `press_guard/`(2단계 알림, 품질 시간창, monitor.py, simulate.py, recalibrate.py, 콘솔, OPERATIONS.md, docs/ 그림, expected_effect_v2.csv) |
| 06 R1~R5·R9·R11 | `press_guard/`(runtime.py, reproduce.py, requirements·environment.yml, test_predictions, predict.py --split, verify 예측 요약, 이식성 시험), `press_submission/run_all.py` torch 지연 import와 v1 재동결 |
| 06 R6~R8·R10 | `analysis/package_contract.py`와 각 패키지 contract.json·expected·test_contract.py, 보완 실험 계약 수정, README 경로 정리 |

주 지표(A F1 0.961938·B 0.970990, 정상 0/120·3/180, 이상 21/21)와 경보 규칙은 바꾸지 않았다. 사후에 정한 것(2단계 규칙, 대기열 정렬 키, 확률 층)은 각 문서에 그 사실을 적었다.

## 2회차(round2, 기준 커밋 e9ed90f·f5679ca)

| 평가관 | 항목(배점) | 1회차 | 2회차 | 보고서 |
|---|---|---:|---:|---|
| 01 | 데이터 이해 및 진단(15) | 12.5 | 13.6 | [judge_01_data.md](round2/judge_01_data.md) |
| 02 | AI 예측모델 개발(40) | 31 | 36.5 | [judge_02_model.md](round2/judge_02_model.md) |
| 03 | 영향요인 및 오류분석(15) | 11.5 | 13.0 | [judge_03_errors.md](round2/judge_03_errors.md) |
| 04 | 현장 활용방안(10) | 7.0 | 8.5 | [judge_04_field.md](round2/judge_04_field.md) |
| 05 | 창의성·차별성(10) | 8.0 | 8.8 | [judge_05_originality.md](round2/judge_05_originality.md) |
| 06 | 코드 및 재현성(10) | 7.5 | 9.0 | [judge_06_repro.md](round2/judge_06_repro.md) |
| | 합계(100) | 77.5 | **89.4** | |

1회차 항목은 거의 모두 충족으로 판정됐다(부분: 01 D4, 02 M2·M3, 03 E1·E3·E8, 05 O1(b)). 2회차에 새로 나온 P0는 두 건이다. 01 R2-D1(정상 운전 2수준 상태와 약 20초 주기를 진단하지 않아 문서 결론 두 개가 자료와 어긋남)과 06 R2-01(제출 목록만 복사한 사본에서 한 명령이 8/15에서 멈춤)이다.

## 2회차 처리

| 평가관 항목 | 처리 |
|---|---|
| 01 R2-D1~D3, 05 R2-O10·O11 | press_evidence: 운전 상태 표 4개(2수준·20초 주기·기록-상태 동기화·분할별 상태 구성·상태별 정상 알림), 결론 세 곳 정정, 그림 3장, 결정표 인용, 관측 이상 진동의 저주파 성격을 FM 대응표에 연결, 앨리어싱 일반형 |
| 02 R2-M1·M4 | press_selection: 같은 특징 대안의 주입 전이표(rule_transfer_injection_v2), fmax 유지 근거를 사전 선택 유지·경보별 단독 근거로 한정. press_supervised README에 값 차이 이유·부스팅 문턱 흔들림·가중 부스팅 범위 |
| 02 R2-M2·M3·M5, 05 R2-O8·O12 | 예측 파일에 파일 비율 사전확률 열, 확률 상한·채점 환산 설명, B 문턱 확률의 등방 계단 설명과 경보 행 최소 우도비, SBB 값을 참고값으로 정정, 확률 층이 오경보를 거르지 못함을 명시, 비교표 입력 조건 열 |
| 03 R2-01~06 | 운전 강도별 조건부 오경보율(fp_intensity_v2), 고장 모양 × 운전 강도 미탐(fn_intensity_v2), 영향변수·상호작용 절, 위치×진동 그림과 오경보 사례 성분·문턱, 12행 요약의 전 행 인용·CI·lift, 절대 구간 번호 |
| 04 R2-01~09 | 감시 조치 분기(재보정 검토 / 설비 점검 요청)와 명령행, 비사후 2단계 업무량 추정(교대 3.3건, 상한 12.7건), 사건 묶음(이상 21기록 → 사건 1개·알림 2건, 일괄 = 스트림), 콘솔 사건 대기열·건 번호·사건 단위 결과 기록, 기록 경계 0.1초 ± 20 ms와 수집 시각 경고, 확률 상한 표시, 대기열 한계 9조건 |
| 05 R2-O9 | 업무량 사후 95%(A 44·B 92건)를 운영 절차·콘솔 표에 표시 |
| 06 R2-01~08 | 제출 목록을 실행 기록 인용에서 검사하고 목록 사본 한 명령 시험(--copy-test), 실행 기록의 절대 경로 제거(v1·press_advance 상대 경로), v1 시험 인코딩과 정적 검사 확대, 파이썬 3.11~3.12, 자식 로그 UTF-8, verify 설명 정정, 선행 파일 없을 때 안내, yejun/.gitattributes(LF 고정), README 명령 정리·내부 표기 제거·lock 보완 |
