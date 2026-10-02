# 통합 계획의 출처와 확인 범위

확인 기준일 2026-10-02 · [통합 계획](README.md)

핵심 판단은 원출처와 해당 내용을 실제로 확인한 범위를 함께 기록한다. 기존 두 계획의 참고문헌 전체를 이번에 재열람했다고 하지 않는다. 접근 실패, 서지만 확인, 기존 조사에서 승계한 근거는 각각 표시한다. 출처의 기관 등급만으로 모든 문장을 승인하지 않는다.

## 1 이번에 직접 확인한 공식 자료

| 자료 | 확인 방법과 범위 | 계획에 미치는 영향 |
|---|---|---|
| [KAMP 공지 86](https://www.kamp-ai.kr/noticeDetail?NOTICE_SEQ=86) | 2026-10-02 공식 HTML 직접 수신, 과제 ③·외부 데이터 추가 조항·제출물·일정 | 외부 데이터 사용 가능 조건 확인. Codex 이전 계획의 규정 미확인 상태 해소 |
| [대회 상세 페이지](https://www.kamp-ai.kr/contestDetail?CPT_SEQ=38) | 공식 HTML 안내 | 전체 행사 일정과 과제 제출 마감을 구분 |
| [KAMP 데이터 설명](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48) | 공식 HTML의 변수·수집 설명·자료량·이용 표기 | 세 센서·정상/이상 행 수 확인. ADC 사양·A/g 단위는 미확인 유지 |

브라우징 도구의 직접 열기는 실패했으나 같은 공식 URL을 Python 표준 HTTPS 요청으로 열어 HTTP 200을 확인했다. HTML 크기·SHA-256·확인 범위를 [확인 기록](evidence/official_source_checks.json)에 남겼다. 동적 페이지 전체 해시는 후속 수신 시 달라질 수 있다. 원 HTML은 조사용 임시 저장만 했고 공용 데이터나 워터마크가 있는 가이드북 사본을 저장소에 올리지 않았다.

공지의 외부 데이터 추가 조항은 2026-09-22 수정분이다. 사용 이유·방법·출처와 공개 가능한 이용 조건을 충족해야 한다. 제출 마감은 2026-10-08 23:59 KST다. 이 사실은 외부 자료를 제출물에 아무 조건 없이 재배포할 권한을 뜻하지 않는다.

과제의 확률 출력·모델 비교 요구는 계획에 반영한다. 가이드북의 예제 분할은 주최 측이 모든 참가자에게 지정한 공통 시험셋으로 확인되지 않았다. 파일 수 20,600 전체의 예측을 만드는 것은 추적성을 위한 우리 설계이지 공지에서 지정한 정확한 행 수 요구가 아니다.

## 2 SKAB 버전과 파일 분할

| 항목 | 확인 내용 |
|---|---|
| 원저자 배포 | [waico/SKAB](https://github.com/waico/SKAB), README가 저자 데이터 DOI와 연결 |
| 이번 고정 버전 | [커밋 b2c0d46](https://github.com/waico/SKAB/tree/b2c0d46c2971dcbfe71e26087b6d231998bb91c2), 커밋 시각 2024-08-11 UTC |
| 설명 확인 | [고정 README](https://github.com/waico/SKAB/blob/b2c0d46c2971dcbfe71e26087b6d231998bb91c2/README.md), [자료 설명](https://github.com/waico/SKAB/blob/b2c0d46c2971dcbfe71e26087b6d231998bb91c2/data/README.md) |
| 라이선스 표시 | [고정 LICENSE](https://github.com/waico/SKAB/blob/b2c0d46c2971dcbfe71e26087b6d231998bb91c2/LICENSE)의 GPL-3.0, 같은 README 표기 |
| 트리 확인 | GitHub 공식 API의 해당 커밋 recursive tree. CSV 35개, 센서 내용은 미열람 |
| 분할 예약 | fit 17, dev 7, cal 5, test 6 파일. fit에 anomaly-free 1개 포함 |
| 센서 | 진동 가속도 RMS 두 채널과 전류 등. 프레스의 원시 관측값과 표현 차이 |
| 라벨 | anomaly와 changepoint 열 설명. 실제 라벨 일관성은 도입 시 검사 |
| 남은 주의 | data README의 valve 파일 번호가 실제 트리와 다름. 파일별 물리 원인 자동 대응 금지 |

[예약 JSON](evidence/skab_split_reservation.json)은 고정 파일명만으로 SHA-256 순서를 정해 작성했다. 난수 실험이나 센서 데이터 분석 결과가 아니다. test 파일은 valve1의 3·10·11, valve2의 2, other의 9·10이다. 다른 부모 파일의 창이 양쪽에 들어가는지 이후 원자료 감사가 필요하다. 파일 분할은 새 설비 일반화를 증명하지 않는다.

이전 Codex 조사에서는 Kaggle 공식 메타데이터가 AGPL-3.0으로 확인됐다. 두 배포판의 표기를 하나로 합치지 않는다. 이번 계획은 GitHub 고정판을 대상으로 삼고, 실제 도입 시 원본·라이선스·수정 범위·배포 형태를 연결한다. 적용 범위가 명확하지 않으면 재배포하지 않고 그 이유와 연구 범위를 기록한다.

SKAB에 대한 저자·기관·논문 연결은 [이전 원출처 조사](../press_research_2026-10-01/01_sources_and_data.md)의 D3를 승계한다. 이번에는 저장소와 메타데이터를 재확인했으며 센서 CSV를 다운로드하거나 논문 결과를 재현하지 않았다.

## 3 판단을 바꾼 방법론 원출처

| 자료 | 이번 확인 범위 | 사용할 주장과 경계 |
|---|---|---|
| Vovk, [Cross conformal predictors](https://arxiv.org/html/1208.0806), arXiv v1 | 원문 §1·§2·§4 | 초기 방법의 경험적 타당성 연구. 임의 OOF 보정에 유한표본 보장을 부여하지 않음. 이후 모든 이론 부재를 주장하지 않음 |
| Barber 등, [Conformal Prediction Beyond Exchangeability](https://arxiv.org/html/2202.13415) | 원문 §1·보장 손실·가중치 조건 관련 절 | 드리프트·상관에서 기존 보장이 달라짐. 단순 갱신이 임의 변화에서 유효성을 회복한다는 근거가 아님 |
| Bates 등, [Testing for Outliers with Conformal p values](https://arxiv.org/html/2104.08279) | 원문 페이지·기존 조사 연결, 이상 검정의 p값 정의 | 정상 꼬리 순위와 현장 고장 확률 구분. 우리 특정 우도비 상한을 증명하지 않음 |
| Kim 등, [Towards a Rigorous Evaluation of Time series Anomaly Detection](https://arxiv.org/abs/2109.05257), AAAI 2022 | 이번에는 저자 초록·서지 재확인. 기존 두 조사에서 학회 원문 열람 | 평가 관행·point adjustment 비판의 근거. 이번 코드의 미래 정보 판단은 로컬 코드 검토에서 도출 |
| NI, [Bandwidth Nyquist Sampling Theorem and Aliasing](https://www.ni.com/en/shop/data-acquisition/measurement-fundamentals/analog-fundamentals/acquiring-an-analog-signal--bandwidth--nyquist-sampling-theorem-.html) | 공식 본문, aliasing 설명 | 표본 주파수·실제 주파수·필터의 구분. 프레스 센서 설정의 원증거가 아님 |
| scikit-learn, [HistGradientBoostingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html) | 공식 API 파라미터 설명 | 작은 GBM 후보 설정의 구현 가능성. 프레스에서의 성능 근거가 아님 |

문헌의 논리와 우리 판단을 구분한다. 예를 들어 “격자만으로 센서 단위를 식별할 수 없다”, “전체 기록 최댓값의 앞선 행 소급은 인과적 예측이 아니다”, “p값 해상도로 일반적 우도비 상한을 정할 수 없다”는 해당 코드·수학적 정의를 검토한 통합 작성자의 판단이다.

## 4 기존 조사에서 승계한 연구와 후속 후보

| 주제 | 승계하는 근거 위치 | 통합안의 사용 범위 |
|---|---|---|
| 조건별 정상 기준 | [Codex 출처 4.2](../press_research_2026-10-01/01_sources_and_data.md), [Claude 출처](../press_research_claude_2026-10-01/02_research_sources.md) | 다중 조건·센서 관계 모델의 설계 동기. 현재 전류 대리값의 타당성을 대신하지 않음 |
| 증강 | [Codex 증강 문헌](../press_research_2026-10-01/04_augmentation_plan.md), [Claude R5](../press_research_claude_2026-10-01/sources/R5_synthetic_faults_augmentation.md) | 제한 변형·잔차·합성 노출의 후보와 한계. 프레스 최적 변환·비율·고장 물리라고 단정하지 않음 |
| 시간 감시 | [NIST EWMA](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm), [CUSUM](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm), 기존 Codex 열람 | 느린 변화 후보. 현재 연속 감시 시간·오경보 예산의 실증은 아님 |
| 경보와 운영 | Claude R4·R9, Codex의 ISA 공식 소개 기록 | 요청·이유·처리 결과를 연결하는 설계. 표준 전문 준수·80/15/5 분포·현장 정지 기준을 주장하지 않음 |
| UCI/ZeMA | 양쪽 출처 및 [기존 보완 실험](../../analysis/press_supplement/README.md) | 이미 본 자료의 방법 실패/성공 사례. 새로운 최종 시험셋 아님 |
| PHM 2022 | [공식 과제](https://data.phmsociety.org/2022-phm-conference-data-challenge/), 기존 두 조사 | 새 개체 정상 참조를 주 질문으로 바꿀 때의 후보 |
| Beihang aviation pump | Codex D6의 논문·데이터 DOI 연결 | 조건·고장 변화 확장. 비동기·메타데이터 검수 후 도입 |
| AI4EU robotic pump | Codex D4의 기관·DOI·설명서 연결 | 운전 패턴·날짜 분석. 건강 라벨 없이 FP·고장 재현율 계산 금지 |
| NLN-EMP | Claude DS-04, [4TU 데이터 DOI](https://doi.org/10.4121/2b61183e-c14f-4131-829b-cc4822c369d0.v4) | 전류·진동 원자료와 여러 고장의 후속 후보. 이번 DOI 열기는 실패하여 Claude의 기존 확인을 승계한 상태로 표시 |

TimeGAN·Diffusion-TS의 사용 가능성을 조사한 사실과 이 데이터에 적합하다는 결론은 다르다. 증강 기법을 사용하는 경우 원저자 코드·버전·학습 데이터·라이선스를 다시 고정한다. 생성기를 쓰지 않아도 이 계획은 완결된다.

## 5 로컬 수치의 근거 수준

| 수치 또는 판단 | 직접 연결 | 이번 처리 |
|---|---|---|
| 동결 v2 성능 | [선정 기록](../../analysis/press_selection/README.md), [Press Guard](../../press_guard/README.md) | 새 계산 없이 기존 기준으로 보존 |
| 599 대 600 기록 | [기존 분할 코드](../../press_submission/press/data.py), [Claude 로더](../press_research_claude_2026-10-01/eda/eda_facts.py) | 경계 정의 차이 확인. 새 공통 결과는 미계산 |
| F1 1.000 | [코드](../press_research_claude_2026-10-01/eda/pilot_review_checks.py), [출력](../press_research_claude_2026-10-01/eda/pilot_review_checks_output.txt) | 기록 전체 판정의 행 소급이라는 평가 범위로 제한 |
| 0.0275 log/10분, 2.9006초, 단측 대 양측 | [코드](../press_research_claude_2026-10-01/eda/pilot_drift_anchor.py), [출력](../press_research_claude_2026-10-01/eda/pilot_drift_anchor_output.txt) | 특정 적합·구간의 파일럿. 열 원인·실제 스트로크·일반 보장으로 확대하지 않음 |
| 전류 격자 | [코드](../press_research_claude_2026-10-01/eda/pilot_unit_lattice.py), [출력](../press_research_claude_2026-10-01/eda/pilot_unit_lattice_output.txt) | 격자 적합 관측과 장비 가정을 분리 |
| 차분 격자·20행 창 F1 0.820·평균 제거·6블록 추세 | `2cc5400`의 [보완 코드](../press_plan_merged_2026-10-02/eda/check_judge_findings.py), [저장 출력](../press_plan_merged_2026-10-02/eda/check_judge_findings_output.txt) | 원안의 추적성 공백과 평가 단위 교정 반영. 가정한 ADC, 클래스별 감도 환산, 순열 교환가능성은 별도 검토 |
| 이상 14/17, 정상 0/251 | Claude review_checks 코드·출력 | 전체 21기록 중 짧은 4개를 뺀 특정 규칙의 값. 통합 모델 성능으로 사용하지 않음 |

이 표의 저장 수치는 재현 실행을 하지 않았다. 코드가 직접 계산하지 않는 리뷰 임시 분석 수치는 계획의 동기로만 남기고 확정 수치로 재인용하지 않는다. 데이터 출처의 신뢰성과 분석의 타당성은 별개로 확인한다.

## 6 보류 사항의 처리 규칙

| 미확인점 | 계획의 기본 경로 | 이후 확인되면 바꿀 수 있는 것 |
|---|---|---|
| ADC 취득 속도·시각 생성 | 주기/표본, 기록 대표 시각, 가상 로거 규약 | 물리 Hz·실제 처리 지연 |
| 센서 단위·감도·DAQ | raw 수치와 상대 정상 기준 | 실제 단위, 알려진 단위 변환 |
| 생산·정지·정비 기록 | 관측 조건·원인 미확정 | 실제 운전 상태별 진단 |
| 독립 고장 사건 | 내부 탐색 및 외부 실험 회차 | 실제 고장 일반화·선행시간 |
| 실제 점검 비용·손실 | 변수를 둔 비용 비교 | 실용 문턱과 점검 우선순위 |
| 외부 파일의 배포 조건 | 고정판의 조건·원본과 연결, 해결 전 제출 포함 보류 | 제출용 데이터/코드 배포 방식 |

이 항목은 현재 계획을 작성하지 못하는 이유가 아니다. 확인되지 않을 때의 경로와 주장 범위를 정했으므로 계획은 그 조건 아래 완료될 수 있다. 이번에 제공기관·연구자·팀원에게 연락하거나 메시지를 보내지 않았다.
