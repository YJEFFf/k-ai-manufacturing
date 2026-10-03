# 데이터 확보와 출처 검증

데이터가 공개돼 있다는 사실, 파일을 받았다는 사실, 우리 질문에 타당하게 쓸 수 있다는 판단은 별개다. 아래에서 취득·해시·구조 검수·모델 평가를 구분했다. 외부 모델 평가는 아직 수행하지 않았다. 출처의 존재만으로 문헌의 모든 수치나 프레스 적용성을 승인하지 않는다. 현재 실행할 SKAB·Beihang의 점수·집계·사건·미지원 처리는 [08 명세](08_execution_contracts.md)로 완성했다. ESPset과 UCI의 아래 사용 설계는 현재 필수 실행 목록 밖이다.

## 실제 확보 내역

경로는 저장소 루트 기준이다. 아래 파일은 로컬에 존재하며 Git에는 원자료를 넣지 않는다. 전체 취득 명령은 `python3 yejun/plans/press_master_2026-10-03/scripts/acquire_data.py --dataset core`다. 기존 파일이 있으면 해시·크기를 검증한다. 공식 배포 버전이 바뀌면 조용히 최신판으로 바꾸지 않고 중단한다.

| 자료 | 원출처와 고정판 | 로컬 위치 | 확인 |
|---|---|---|---|
| UCI Hydraulic | [UCI 447](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems), DOI 10.24432/C5CW21 | `yejun/analysis/press_external/data/hydraulic.zip` | 76,601,704 B, 기존 SHA-256 일치, ZIP 20파일 CRC 통과 |
| SKAB | [고정 GitHub판](https://github.com/waico/SKAB/tree/b2c0d46c2971dcbfe71e26087b6d231998bb91c2) | `yejun/plans/press_master_2026-10-03/data/skab/` | 35 CSV 합계 4,392,581 B, 각 파일 해시, 원 README·LICENSE 보관 |
| Beihang | [Mendeley v1](https://data.mendeley.com/datasets/xw8gjjk9km/1), DOI 10.17632/xw8gjjk9km.1 | `yejun/plans/press_master_2026-10-03/data/beihang/` | 196,394,316 B, 게시 SHA-256 일치, 11 CSV CRC 통과 |
| ESPset | [Mendeley v3](https://data.mendeley.com/datasets/m268jsw339/3), DOI 10.17632/m268jsw339.3 | `yejun/plans/press_master_2026-10-03/data/espset/` | 특징·스펙트럼 2 ZIP, 합계 115,324,308 B, 게시 SHA-256 일치·CRC 통과 |

네 자료의 위 원파일 합계는 **392,712,909 B**다. UCI는 기존 취득본을 재검사했고 나머지 세 자료를 새로 취득했다. byte 수는 압축 또는 배포 CSV 크기이며 독립 표본 수가 아니다. 기록은 [UCI](evidence/uci_acquisition.json), [SKAB](evidence/skab_acquisition.json), [Beihang](evidence/beihang_acquisition.json), [ESPset](evidence/espset_acquisition.json)에 남겼다.

NLN-EMP는 [4TU v4](https://data.4tu.nl/datasets/2b61183e-c14f-4131-829b-cc4822c369d0/4)의 CC0 표기·DOI·기관 연결을 확인했다. 20,803,099,256 B의 외부 7z 안에 약 20.8 GB의 `Dataset.7z`가 다시 들어 있다. HTTP Range로 압축 디렉터리, README, 측정 개요 XLSX만 확보했다. README는 센서 데이터 해제에 약 90 GB 공간이 필요하다고 설명한다. **센서 원자료는 미취득**이다. 전체 다운로드를 일부 진행한 뒤 중첩 구조 확인에 필요한 메타데이터 취득으로 범위를 바꾸었고 미완료 파일은 삭제했다. [목록](evidence/nln_archive_inventory.json), [취득 기록](evidence/nln_metadata_acquisition.json)

NLN 재취득은 `scripts/acquire_nln_metadata.py`로 재현한다(`py7zr==1.1.3`). README의 저장 진동 샘플 길이는 12초다. 과거 리서치의 60초 수집 설명과 파일 분할 관계는 센서 원자료 검수 전에 확정하지 않는다. 다른 장치의 전류·진동을 프레스 채널처럼 동기화해 붙이는 용도로 쓰지 않는다.

## SKAB에서 발견한 누수와 라벨 충돌

공식 설명은 진동 RMS 2개, 전류, 압력, 온도, 유량 등의 실험 자료와 anomaly/changepoint 표기를 제공한다. 프레스의 원시 파형과 같은 입력은 아니다. 실제 도입판은 GitHub 고정판이며 Kaggle판 라이선스와 섞지 않는다. [원저자 설명](https://github.com/waico/SKAB/blob/b2c0d46c2971dcbfe71e26087b6d231998bb91c2/README.md)

| 같은 시각과 모든 센서값이 겹친 파일 | 공유 행 수 | 기존 역할 |
|---|---:|---|
| anomaly-free와 other/5 | 572 | fit / dev |
| other/10과 other/11 | 21 | test / fit |
| other/12와 other/13 | 349 | fit / fit |
| other/2와 other/3 | 120 | cal / dev |
| other/3와 other/4 | 228 | dev / fit |

시간 범위 겹침도 같은 5쌍이다. 연결 성분을 수집 그룹으로 묶어 총 30그룹을 얻었다. 동일 시각·센서값의 주석도 대조했으며 **237개 고유 관측에서 anomaly 또는 changepoint가 충돌하고, 그중 235개는 anomaly 라벨이 다르다.** 파일별 실험 문맥에서 주석했을 가능성이 있으므로 제공자 오류로 단정하지 않는다. 확인된 정상이라고 사용하는 데는 충돌이 된다. [그룹 검사](scripts/reserve_skab_groups.py), [주석 충돌](evidence/skab_label_consistency.json)

새 분할은 다음과 같다. 기존 test가 속한 그룹은 모두 test, anomaly-free 연결 그룹은 fit, 나머지 연결 그룹은 cal > dev > fit 우선으로 배정했다. 성능을 보고 이동한 파일은 없다.

| 역할 | 파일 수 | 수집 그룹 수 |
|---|---:|---:|
| fit | 16 | 14 |
| dev | 5 | 5 |
| cal | 7 | 5 |
| test | 7 | 6 |

기준은 [새 예약 JSON](evidence/skab_group_reservation.json)이다. 이전 17/7/5/6 파일 예약을 사용하면 안 된다. 시험 파일도 기계적인 시각·동일값·주석 일치 검사에는 접근했다. 다른 파일이 test로 승격되기 전 수행한 구조·라벨 개수 감사도 존재한다. **완전 미열람 원자료라고 주장하지 않으며 모델 성능과 시험 분포를 이용한 선택은 하지 않았다는 범위로 제한한다.**

사용 계약은 다음과 같다.

- 같은 그룹의 같은 관측은 센서·시각 기준 한 번만 점수화한다. 겹친 파일을 이어 길이를 두 배로 만들지 않는다. 원 파일 ID와 모든 주석은 대응표에 보존한다.
- 주석 충돌 관측과 이를 포함하는 입력창은 fit/cal의 확인된 정상에서 제외한다. 평가에서는 `ambiguous_annotation`으로 남기고 커버리지·보수/낙관 경계 지표를 함께 낸다. 모델에 유리한 쪽의 라벨을 택하지 않는다.
- 각 수집 그룹을 시간순으로 한 번 재생해 **비중첩 20표본 블록**에서 1회 판정한다. 블록 시작은 그룹 첫 관측이며 라벨을 보고 맞추지 않는다. 공백은 fit의 중앙 시각 간격 1.5배 초과에서 끊고, 역행·동일 시각 상충값은 품질 오류다. 마지막의 20표본 미만 블록도 상태·커버리지·유보 부담에 남긴다. fit/cal에서는 모든 관측이 정상이고 충돌 없는 완성 블록만 쓴다. dev/test의 블록 생성과 점수화에는 정상 라벨을 요구하지 않는다.
- 주 평가는 같은 20표본 단위다. 점수 한 개를 실제 정상 cal 블록 점수로 순위 보정하며 프레스 기록이나 1초 행의 α와 보장 단위를 섞지 않는다. 주석 충돌이 있는 블록은 먼저 모호로 표시한다. 나머지 블록의 anomaly 정답은 구성 관측 중 하나라도 1이면 1, 모두 확정 0이면 0이다. changepoint는 별도 사건 주석이다. 지연은 원 0→1 시각부터 블록 종료 판정까지 계산하므로 묶어서 기다린 시간도 포함된다. 그룹 상관을 무시한 보장은 하지 않는다.
- 현재 첫 비교는 전역 G와 1차 양측 조건부 C 두 구조다. 프레스 K1이 개발 기준을 통과한 경우에만 같은 보정 규칙의 K1을 세 번째로 추가한다. kNN·증강 변형은 현재 SKAB 목록에서 제외한다. 특징은 두 진동 RMS 중앙값과 전류 크기 중앙값·MAD의 로그다. 조건은 양수 `abs(median(Current))`의 fit 1~99백분위다. 이미 RMS인 진동을 AC 원시 파형으로 처리하거나 프레스의 0.06 사인 게이트를 복사하지 않는다.
- 주 질문은 동일 절차를 외부 정상에 재적합했을 때 수집 그룹별 요청과 변화 이후 지연이 어떻게 달라지는가다. anomaly 0→1 사건, changepoint 진단, 검열과 모호 라벨의 처리는 08에서 사전 고정했다. dev에서 주석 구조를 확인하되 더 좋은 점수를 주는 사건 정의로 바꾸지 않는다. 변화 전에 켜진 요청은 신규 탐지로 세지 않는다.
- 최종 시험 전에 특징·창·점수·정책·라벨 충돌 규칙의 해시를 고정한다. test 결과를 보고 더 잘 나오는 모델로 바꾸지 않는다. 추가 중복·유사 복제가 발견되면 구조 감사 이력을 남기고 주장 범위를 조정한다.

충돌 마스크의 행별 해시는 Git 제외 `cache/skab_label_conflicts.json`에 두고 검사 스크립트로 재생성한다. Git에는 집계와 마스크 SHA-256만 보존한다. 모호한 평가 블록은 어느 라벨에서 오류가 될지에 대한 두 경계를 제시하며 단일 정답을 확정하지 않는다. 선별된 확정 블록의 성능만으로 전체 파일 성능을 대신하지 않는다.

## Beihang의 조건부 사용

정상 CSV 2개, 압력 조절 밸브·서보 피스톤·사판 베어링 부시 마모 각 3개가 있다. 이것은 서로 다른 프레스 11대나 독립 자연 고장 9건이 아니다. 정상 1번의 시각 구조를 읽었고 나머지는 헤더·압축 CRC만 검사했다. 실제 시험대에서 인위적으로 손상을 준 자료라는 의미이며, 수치 시뮬레이터가 생성한 프레스 고장이라고 쓰지 않는다. [데이터](https://data.mendeley.com/datasets/xw8gjjk9km/1), [저자 논문 전문 XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12769818/fullTextXML)

정상 1번은 811,530행·22열이지만 이것이 811,530개의 동기 센서 관측은 아니다. 진동 3축은 각각 270,509유효쌍·약 1 kHz, 속도·토크는 2,704유효쌍·약 10 Hz다. 출력 압력의 시각 간격은 약 3 kHz, 제어 포트 압력은 약 2 kHz다. 시간·신호 쌍별 빈 칸은 서로 다른 길이 때문에 생긴다. 전 행 `dropna()`는 가장 긴 채널의 대부분을 버리는 잘못된 전처리다. [직접 감사](evidence/external_audit.json)

일차 연구 입력은 진동 3축과 속도다. 각 채널 시간축을 파싱하고 같은 **1초 비중첩 구간**의 AC RMS·산포 및 속도 중앙값을 계산한다. 시각이 리셋되거나 불연속인 구간을 이어붙이지 않는다. 모든 모델은 완성 1초 구간이 닫힌 후 판정한다. 온도는 설명에 있지만 CSV 11신호에는 없으므로 만들지 않는다. 압력 취득률·유량 단위·단계 매핑이 해소되기 전 압력·유량 특징을 주 모델에 넣지 않는다.

Beihang의 두 구조 G/C와 하이퍼파라미터는 08에 고정하며 프레스 결과로 유리한 구조를 고르지 않는다. 정상 1번의 공통 시간 범위 앞 60%로 적합, 중간 20%는 구조 확인 전용, 뒤 20%로 정상 보정한다. 경계 창 제외는 08 규칙을 쓴다. 정상 2번과 마모 9파일은 보류 평가다. 보정 표본이 α 해상도를 못 채우면 해당 α는 미지원으로 남긴다. 정상 1회 안의 적합/보정은 독립 회차가 아니며 정상 파일 2개로 폭넓은 일반화를 주장하지 않는다. 역할을 뒤집는 대칭 실험은 현재 실행하지 않는다.

이 자료에는 우리의 기준으로 확정된 고장 시작 시각이 없다. 상태 분류·조건별 정상 요청을 검사하며 자연 고장 선행시간은 계산하지 않는다. 제공 문헌의 속도/유량 절차와 파일 시간은 실험 실행 전에 정상 개발 파일에서 대조한다. 대응이 모호하면 절차 번호를 생성하지 않고 관측 속도 구간으로 층화한다.

## ESPset의 개체 검증

공식 v3 배포의 특징·스펙트럼을 모두 확보했다. 6,032관측·11개 `esp_id`, 라벨은 Normal 4,801, Unbalance 576, Faulty sensor 295, Rubbing 290, Misalignment 70이다. 각 펌프 ID에는 복수 라벨이 있다. 이 수치 확인은 ID·라벨 메타데이터 감사이며 특징 분포나 모델 성능은 계산하지 않았다. [배포](https://data.mendeley.com/datasets/m268jsw339/3), [감사](evidence/espset_audit.json)

`esp_id`와 `id`는 특징에서 제거하고, 해시로 ID를 정렬한 [예약](evidence/espset_group_reservation.json)을 사용한다. fit 5대, dev 2대, cal 2대, test 2대다. 같은 펌프의 관측을 역할 사이에 나누지 않는다. CSV 구분자는 세미콜론이며 [재생성 코드](scripts/audit_espset.py)가 구조·예약을 확인한다. 제공된 회전수 정규화 특징을 사용한 전역 거리·조건 없는 기준 비교가 기본이다. 스케일·정상 모델은 fit ID의 Normal에만 적합하고 정상 순위 보정은 cal ID의 Normal에만 수행한다. dev는 고정된 후보의 선택과 오류 분석, test는 마지막 평가다. 2개 cal 개체에서 얻은 수많은 행이 독립 개체 수를 늘리지는 않는다. 전류 조건부 모델을 검증했다는 주장이나 원시 파형 전이 주장은 하지 않는다.

기계 이상 탐지와 Faulty sensor 요청을 따로 평가한다. 대표 이진 결과는 Normal 대 모든 비정상, 별도 결과는 기계 3라벨 대 Normal이며 센서 라벨은 별도 집계한다. 이렇게 정의한 후 결과에 맞춰 목표 라벨을 바꾸지 않는다. 최종 펌프 2대는 여전히 작은 표본이다. 시간 순서가 없어 지연·경보/시간은 산출하지 않는다. 실제 현장 기원의 자료라도 프레스 설비의 현장 실증으로 부르지 않는다.

## UCI와 나머지 후보의 역할

UCI는 이미 탐색한 자료다. 2,205개 60초 사이클과 네 부품 상태·안정성 라벨이 있고 전류가 아니라 전력 EPS1, 진동은 VS1 1 Hz다. 냉각기 상태는 고장 요인이므로 정상 부하라고 이름을 바꾸지 않는다. 펌프 누설을 목표로 할 때 다른 부품 상태별 층화와 이미 남긴 [분할](../../analysis/press_external/partitions.csv)을 우선 유지한다. 이전 적용 실패를 재현하고 조건부 기준이 어느 조건에서 이를 바꾸는지 조사하는 회귀 실험이다. 같은 UCI를 새 외부 시험으로 다시 세지 않는다. [UCI 설명](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems)

| 후보 | 이번 재확인 범위 | 처리 |
|---|---|---|
| AI4EU | 이번 Zenodo API 403. 이전 기관·CC BY·18.9 GB·라벨 부재 조사 승계 | 고장 라벨 없는 조건 변화 참고. FP·고장 recall 입증용에서 제외 |
| MIMII DUE | 이번 Zenodo API 403. 이전 Hitachi 배포·CC BY-NC-SA 기록 승계 | 음향 도메인·이용 조건 차이로 이번 입력에서 제외 |
| PHM 2022 | 공식 페이지 재수신 | 개체 이동 설계 참고. 명확한 재사용 조건 검토 없이 원자료 편입하지 않음 |
| Paderborn | 공식 페이지 수신. 이번에 세부 조건 확정은 하지 않음 | 이전 NC 조건 조사 유지, 이번 필수 자료 아님 |
| FZU_HGPFD | 저자 저장소 README 재수신, 기어펌프·조건 구성 확인 | 기관 교차 연결·명시적 배포 조건·독립 회차 검수가 남음 |
| 2026 long-tail pump | Mendeley 공식 메타데이터·CC BY 확인 | 기관·연결 논문·수집 단위가 남아 데이터 사용 보류 |
| KAMP의 다른 프레스/용접 | 원 과제와 다른 자료 | 같은 설비 자료로 합치지 않음 |

불필요한 용량 확보를 연구의 깊이로 대신하지 않는다. 현재 핵심 질문에 필요한 외부 역할은 확보한 네 자료로 구성했고, 후보별 미해결점은 발견 기록으로 남겼다.

## 이용 조건과 출처 표기

KAMP 공식 공지 86을 2026년 10월 3일 다시 수신해 외부 데이터 활용 사유·방법·출처와 공개 가능 조건을 확인했다. 제출물은 보고서 PDF, 코드·학습 데이터·실행 환경·README·시험 예측을 포함한 ZIP, 발표 PDF/PPT, 설문 증빙이며 식별 정보 제한도 있다. 현재는 이 제출물을 작성하지 않고 요구사항만 추적한다. [공식 공지](https://www.kamp-ai.kr/noticeDetail?NOTICE_SEQ=86)

| 자료 | 관찰한 표시 | 배포 설계 |
|---|---|---|
| UCI·Beihang·ESPset | CC BY 4.0 | 저자·제목·고정 DOI·라이선스 링크·부분 선택/전처리 변경을 기록 |
| NLN-EMP | CC0 1.0 | 법적 최소와 별개로 학술 출처·버전·변경을 보존 |
| SKAB GitHub 고정판 | GPL-3.0 | 원 라이선스·고지·파일 버전 보존. 제출 패키지와 파생 자료의 조건을 별도 검토 |
| KAMP 원본·가이드북 | KAMP 표시·대회 제공 조건 | 공용 원본 읽기 전용, 원본 공개 Git 재배포 금지 유지 |

실제 사용한 자료의 저자 표기는 UCI: N. Helwig, E. Pignanelli, A. Schuetze; SKAB: Iurii D. Katser, Vyacheslav O. Kozitsin; Beihang: Jiming Ma; ESPset: Marcos Pellegrini, Flavio Varejao, Alexandre Rodrigues, Lucas Henrique Sousa Mello, Luciano Silva다. 제목·고정 DOI는 위 취득 표와 각 manifest에 연결했다. 원 ZIP·CSV는 변경하지 않았고 이번 파생물은 구조 통계·중복/주석 검사·분할 예약이다. 이후 학습용 전처리가 추가되면 그 변경도 기록한다. 원저자의 보증이나 본 연구 승인을 뜻하지 않는다.

GPL이 상업 사용이나 대회 참가를 일괄 금지한다는 결론은 내리지 않는다. 코드 의존성과 데이터 라이선스는 별개다. SKAB 재배포 형식이 해결되지 않으면 필수 학습 데이터로 묶지 않고 외부 참고 검증으로 범위를 줄이며, 이를 완료된 제출 요건 충족이라고 표현하지 않는다. 데이터 권한 확인과 대회 규정 충족은 각각 점검한다. [고정 LICENSE](https://github.com/waico/SKAB/blob/b2c0d46c2971dcbfe71e26087b6d231998bb91c2/LICENSE), [CC BY 설명](https://creativecommons.org/licenses/by/4.0/)

파일별 취득 manifest에는 URL·고정판·크기·SHA-256·게시 해시 검증 여부가 있다. 연구 데이터 사용표는 각 파일을 어느 질문·채널·분할·전처리에 썼는지 추가해야 한다. 다운로드 스크립트만으로 학습 데이터 제출 요구를 충족했다고 하지 않는다.

## 방법론 출처의 확인 수준

이번 스크립트는 주요 원출처 URL 29개에 접근해 26개를 수신했고 3개는 접근 실패했다. HTTP 성공은 내용 검토와 같지 않다. 원문 사본은 Git 제외 cache에, 수신 시각·해시는 [출처 기록](evidence/source_receipts.json)에 보관한다. 기존 약 130개 문헌을 모두 새로 전문 검토했다고 주장하지 않는다.

| 근거 | 이번 사용 범위 |
|---|---|
| [Cross-conformal predictors](https://arxiv.org/html/1208.0806) | 초기 방법 정의와 경험 검증. 모든 후속 이론의 부재라고 일반화하지 않음 |
| [Conformal Prediction Beyond Exchangeability](https://arxiv.org/html/2202.13415) | 가정·방법에 따라 보장이 달라진다는 근거. 임의 OOF 점수 보정에 보장 이식 금지 |
| [Testing for Outliers with Conformal p-values](https://arxiv.org/abs/2104.08279) | 저자 초록·서지 확인. 정상 꼬리 p값과 현장 사후확률 구분 |
| [Rigorous Evaluation of TSAD](https://arxiv.org/abs/2109.05257) | 저자 초록·서지와 기존 학회 원문 조사 연결. point adjustment 비판 |
| [Iwana와 Uchida의 증강 조사](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0254841) | 방법·결과·제약. 프레스에서 특정 변환이 정상이라는 증거는 아님 |
| [Künsch 1989](https://doi.org/10.1214/aos/1176347265) | 이번에는 Crossref 서지 확인만. 블록 부트스트랩이 모든 비정상 시계열을 해결한다는 근거 없음 |
| [NIST EWMA](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm) | 작은 지속 변화 감시의 설계 배경. 우리 경보 정책의 검증 결과 아님 |
| [NIST의 일정 고장률 모형](https://www.itl.nist.gov/div898/handbook/apr/section4/apr451.htm) | 무사건 노출시간에 대한 조건부 표본량 계산. 현재 자료의 실증 보장 아님 |

구체적인 crop 길이, 주입 강도, 3건·10%p·5%p 선택 기준, 모델 목록은 이 계획의 설계 선택이다. 문헌이 입증한 최적 설정으로 인용하지 않는다. 철회된 `arXiv:2603.00199`, 본문 미확보 연구의 성능 수치, 표준 소개만 읽고 표준 전체 준수라고 한 주장은 사용하지 않는다.
