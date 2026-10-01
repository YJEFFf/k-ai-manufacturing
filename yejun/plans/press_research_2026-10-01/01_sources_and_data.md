# 프레스 과제 출처 검증과 데이터·문헌 조사

확인일: 2026-10-01. [전체 계획](README.md) · [접근법 비교](02_research_options.md) · [검증 계획](03_validation_and_execution_plan.md) · [증강 문헌·계획](04_augmentation_plan.md)

## 1. 자료를 채택하는 기준

사용자 요청에 따라 **데이터 도입과 보고서 근거에는 원출처가 명확하고 신뢰할 수 있는 자료만 사용한다.** 폭넓게 찾는 것과 모든 자료를 근거로 채택하는 것은 구분한다.

### 출처와 확인 수준을 별도로 기록한다

| 항목 | 판단 기준 |
|---|---|
| 제공 주체 | 주최 기관, 대학·연구기관, 학회, 원저자, 제조사 등 실제 생산·발표 주체가 확인되는가? |
| 연결 관계 | 기관 페이지 → 논문/데이터 DOI → 배포본이 연결되는가? 이름만 비슷한 재배포본은 아닌가? |
| 확인 범위 | 원문 관련 절, 데이터 설명서, 공식 모델 카드, 초록·서지만 확인한 경우를 구분했는가? |
| 내용 신뢰 | 센서·라벨·수집 과정·실험 단위·제한사항을 설명하는가? 문서 내부의 모순은 없는가? |
| 사용 범위 | 재분석·변형·배포·그림 재사용에 관한 배포 조건을 확인했는가? |
| 현재 상태 | 철회·정정·버전 변경, 접근 불가, 향후 공개 예정 상태를 확인했는가? |

아래의 **“설명 확인”은 원시 파일 검수나 성능 재현 완료를 뜻하지 않는다.** 이번 작업에서는 논문·설명서·배포 메타데이터를 조사했으며 새 외부 데이터 전체 다운로드나 실험은 하지 않았다. 작은 설명 PDF는 내용 확인을 위해 열람했다.

### 향후 인용·도입 시 필요한 기록

데이터마다 제목, 저자/제공기관, 원본 URL, DOI 또는 버전·커밋, 공개일, 확인일, 배포 조건, 파일명·크기·해시, 센서 단위, 원 샘플링과 저장 주기, 개체·회차·상태 라벨을 남긴다. 실제 사용 시에는 사용한 파일·열·조건·제외 이유와 전처리도 연결한다.

논문·표·그림마다 **어느 주장에 쓰는지**, 실제 확인한 페이지/절/표 번호, 연구 대상, 저자의 실험인지 재인용인지, 우리 데이터에 적용할 때의 차이를 남긴다. 수치가 필요한 경우 초록만으로 결론내리지 않고 분할·지표·분모까지 본다. DOI가 있는 것과 동료심사를 거친 것은 같지 않으며, arXiv는 출판 상태를 별도로 표시한다.

제조사 문서는 제품 기능·계측 항목·유지보수 절차의 1차 자료로 쓴다. 제조사의 절감률이나 홍보 문구는 우리 모델의 효과로 옮기지 않는다. 표준 소개 페이지를 읽은 것만으로 표준 원문 전체를 검토했거나 준수했다고 하지 않는다.

## 2. 조사 경로와 범위

- 로컬: 주최 측 HWPX, 원본 가이드북 PDF, 데이터 보유 목록, 기존 진단·비교·외부 실험·검수 기록.
- 데이터: UCI, PHM Society, Zenodo의 원저자 배포, 대학 공식 데이터센터, Mendeley Data와 연결 논문.
- 논문: 학회·학술지 원문, 저자 arXiv, 공식 연구실 저장소. 출판사 접근 실패 시 공개 학술 아카이브에서 동일 DOI를 대조했다.
- 기술: NIST 통계 문서, NI 계측 문서, IBM·Auton Lab 모델 카드, 알고리즘 원저자 저장소.
- 현장: Bosch Rexroth, HYDAC, ISA의 공식 문서.
- 한국어·영어 검색과 인용 연결을 함께 사용했다. 프레스·유압펌프뿐 아니라 정상 운전 전환, 다중 운전 모드, 계측 오류, 표본화, 순차 경보, 전이, 확률보정까지 범위를 넓혔다.

검색 결과 요약은 발견 경로로만 쓴다. 아래에 직접 확인 범위를 표시하지 않은 새로운 성능 주장은 채택하지 않는다. 같은 데이터의 UCI·Zenodo 사본, 같은 논문의 arXiv·학회판은 독립 증거 수로 중복 계산하지 않는다.

## 3. 데이터 후보 지도

| 자료 | 원출처 상태 | 우리 과제에서의 역할 | 도입 우선순위 |
|---|---|---|---|
| 대회 프레스 원본 | 주최 배포본·가이드북 로컬 확인 | 주 과제, 기존 결과와 비교 | 필수 |
| UCI/ZeMA hydraulic systems | 공식 배포·설명 확인, 기존 로컬 실험 있음 | 운전 조건 이동, 느린 고장 관련 특징 | 우선, 기존 자료임을 명시 |
| SKAB | 원저자 배포·저자 논문 연결 확인 | 사건 시작 후 지연·여러 실험 회차 | 우선 후보, 라이선스 대조 필요 |
| AI4EU robotic pump | 기관 페이지·DOI·설명서·메타데이터 확인 | 운전 단계 전환·날짜 변화 | 우선 후보, 정상 판정 근거 확인 필요 |
| PHM 2022 rock drill | 학회 공식 과제·설명서 확인 | 개체 이동·정상 참조를 이용한 적응 | 적응 방향 선택 시 우선 |
| Beihang aviation piston pump | 논문 원문·데이터 DOI 연결 확인 | 속도·유량 조건과 주입 고장 | 조건부 우선, 비동기·메타데이터 검수 필요 |
| Paderborn bearing | 대학 공식 배포·원 논문 확인 | 전류·진동 표현과 조건 이동 보조 검증 | 보조 |
| MIMII DUE | Hitachi 원저자 배포·DCASE 연결 확인 | 정상 조건 변화, 목표 도메인 적응 설계 | 보조, 음향 자료 |
| ESPset | 저자 데이터 DOI·연구실 코드·서지 연결 | 개체별 분할·스펙트럼 표현 | 보조, 원시 시계열 아님 |
| FZU_HGPFD | 저장소 설명만 확인, 기관 교차 연결 미완료 | 속도·압력·복합 고장 아이디어 | 도입 대기 |
| 2026 centrifugal pump long-tail 자료 | 배포 메타데이터만 확인 | 불균형·복합 고장 탐색 단서 | 도입 대기 |
| 로컬 KAMP 46/59 등 | 보유 목록·관련 설명 검토 | 프레스 운영 맥락·수집 항목 참고 | 보조, 원본 프레스와 합치지 않음 |

### D1. 대회 프레스 원본

- **원출처:** 주최 측 공용 원본 `데이터셋/프레스_유압펌프_예지보전/`와 해당 가이드북. 과제 원문은 [로컬 추출본](../../analysis/press_rubric_review/official_task_extract.txt)으로 추적 가능하다.
- **확인:** 파인블랭킹 프레스의 유압펌프 상·하부 진동과 전류, 정상/이상 파일 구성. 가이드북이 설명하는 LSTM-AE는 교육용 접근이며 과제에서 강제하는 모델이 아니다.
- **핵심 제한:** 단위·정확한 펌프 모델·실제 운전 조건·고장 시작 시각을 확인하지 못했다. 가이드북의 기어펌프 도식만으로 대상 펌프의 정확한 기종을 확정하지 않는다.
- **사용:** 과제의 주 데이터. 시간·파일·표현 교락을 명시하고 기존 동결 결과와 비교한다.
- **금지:** 별도 폴더의 `미사용_KAMP07_다른프레스데이터셋/`을 같은 대회 원본으로 취급하지 않는다. 제공 조건을 넘어 원본을 임의 공개하지 않는다.

### D2. UCI / ZeMA — Condition Monitoring of Hydraulic Systems

- **원출처:** [UCI 공식 배포](https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems), DOI `10.24432/C5CW21`. [ZeMA의 Zenodo 배포](https://zenodo.org/records/1323611)는 같은 데이터 계열이다.
- **확인:** 2,205개의 60초 주기와 냉각기·밸브·펌프 누설·축압기 조건. 센서별 취득 속도가 다르며 압력·전력 100 Hz, 유량 10 Hz, 진동 등 일부는 1 Hz다. UCI의 CC BY 4.0 표기를 확인했다.
- **쓸 질문:** 조건별 정상화, 주기 내 단계별 평균/잔차, 조건 밖 성능, 빠른 파형과 느린 수준 변화의 차이.
- **제한:** 모든 센서를 10 Hz로 맞췄다고 같은 정보량이 되지 않는다. 냉각기 상태는 문서상 부품 상태이며 무조건 무해한 운전부하로 이름을 바꾸지 않는다. 목표가 펌프 누설이면 다른 부품 상태를 별도 요인으로 관리한다.
- **현재 상태:** 팀이 이미 사용했다. 기존 [실험 결과](../../analysis/press_external/README.md)를 실패조건 분석에 활용하되 새 미열람 검증셋이라고 하지 않는다.

### D3. SKAB — Skoltech Anomaly Benchmark

- **원출처:** Katser·Kozitsin의 [공식 저장소](https://github.com/waico/SKAB), [원저자 데이터 DOI](https://doi.org/10.34740/KAGGLE/DSV/1693952). 동일 저자·Skoltech 소속과 데이터 설명은 [저자 논문 원문](https://mdpi-res.com/d_attachment/applsci/applsci-11-04280/article_deploy/applsci-11-04280-v2.pdf), DOI `10.3390/app11094280`으로 교차 확인했다.
- **확인:** 물 순환 시험장치, 진동 RMS 2개·전류·압력·온도·전압·유량과 anomaly/changepoint 라벨. v0.9 설명에 34개 이상 실험과 35개 파일 표기가 함께 있어 정상 전용 파일을 포함한 정확한 구성은 실제 도입 시 고정한다. 향후 300개 이상 공개 예정 문구는 현재 자료량에 포함하지 않는다.
- **쓸 질문:** 시작 시각이 표시된 여러 실험에서 탐지 지연·정상 복귀·운전 전환을 평가한다. 진동 RMS+전류 조건과 전체 센서 조건을 나누면 추가 센서의 가치도 볼 수 있다.
- **제한:** RMS와 프레스 원시 관측값은 다른 표현이다. 유압유 프레스 실증으로 표현하지 않는다. 기존 리더보드와 새로운 평가 방식이 달라 저자 점수를 그대로 비교하지 않는다.
- **이용 조건:** [GitHub 라이선스 원문](https://github.com/waico/SKAB/blob/master/LICENSE)의 GPL-3.0과 [Kaggle 공식 메타데이터](https://www.kaggle.com/api/v1/datasets/view/yuriykatser/skoltech-anomaly-benchmark-skab)의 AGPL-3.0 표기가 다르다. 양쪽을 직접 확인했다. 실제 사용할 버전·파일의 적용 조건을 정리하기 전 원본 재배포 계획을 확정하지 않는다.

### D4. AI4EU Robotics Pilot — Robotic Pump

- **원출처:** Mossige(ABB Robotics), Ramachandran(Fraunhofer IPA), Spieker(Simula)의 [Zenodo 배포](https://zenodo.org/records/5729187), DOI `10.5281/zenodo.5729187`. [Simula 공식 연구 목록](https://www.simula.no/research/ai4eu-robotics-pilot-vibration-sensor-measurements-robotic-pump)에서 동일 DOI를 확인했다.
- **확인:** 2020년 두 달 범위, 날짜별 33개 파일, 전체 약 18.9 GB. [설명 PDF](https://zenodo.org/records/5729187/files/Pump%20Dataset%20Documentation.pdf?download=1)를 읽어 1초 단위 기록 내부의 진동이 **6.14 kHz**임을 확인했다. 개요의 “1-second intervals”를 원시 진동 1 Hz로 해석하면 안 된다. [공식 메타데이터](https://zenodo.org/api/records/5729187)는 CC BY 4.0이다.
- **쓸 질문:** 단계·회전수·설정값이 바뀔 때의 경보 민감도, 날짜 이동, 상태별 참조 기준. 속도가 낮은 다른 센서는 보간된 값이 포함된다.
- **제한:** 확인한 문서에는 검증 가능한 고장 라벨이 없다. 전체를 건강한 정상으로 단정하기보다 “고장 라벨 없는 운전 자료”로 시작한다. 물리 고장 재현율·고장 시작 지연을 계산하지 않는다.
- **도입 범위 제안:** 처음부터 18.9 GB 전체를 받지 않고 설명서의 단계 정의와 필요한 날짜·조건을 정한 뒤 일부를 선택한다. 정상 이력의 신뢰 근거를 확보하지 못하면 경보를 FP라고 단정하지 않고 조건별 경보 민감도로 보고한다.

### D5. PHM Society 2022 — Hydraulic Rock Drill Challenge

- **원출처:** [학회 공식 과제](https://data.phmsociety.org/2022-phm-conference-data-challenge/), [공식 데이터 설명 PDF](https://data.phmsociety.org/wp-content/uploads/sites/9/2022/06/PHM2022_Data_Challenge_Description.pdf).
- **확인:** 여러 개체/구성의 유압 착암기, 정상 포함 11개 상태, 압력 3채널 50 kHz. 학습·검증·최종 평가의 개체 구분과 목표 개체 정상 참조 자료가 있다.
- **쓸 질문:** 새 개체의 건강한 참조 자료를 이용한 특징 정렬·거리 기반 진단. 시간창을 섞는 평가보다 leave-one-unit-out 설계의 참고 가치가 크다.
- **직접 연결 문헌:** Oh 등, [A Hybrid Approach of Data-Driven and Signal Processing-Based Methods for Fault Diagnosis of Hydraulic Rock Drill](https://www.papers.phmsociety.org/index.php/phmconf/article/view/3408), PHM 2022. 학회 원문 페이지에서 정상 참조와 신호처리·학습 결합 접근을 확인했다.
- **제한/도입 조건:** 착암기 압력과 프레스 진동·전류는 다르다. 배포 파일의 이용·재배포 조건을 실제 도입 시 확인한다. 과거 대회 우승 점수를 우리 과제의 기대 성능으로 옮기지 않는다.

### D6. Beihang — Aviation Piston Pump

- **원출처:** [Mendeley Data v1](https://data.mendeley.com/datasets/xw8gjjk9km/1), DOI `10.17632/xw8gjjk9km.1`, 2025-10-11. Wang·Ma·Fu, Beihang University의 **Multi-mode fault dataset for aviation piston pump based on standard test procedure**, Data in Brief 64, 112336, DOI `10.1016/j.dib.2025.112336`와 연결된다.
- **원문 확인 경로:** 출판사 직접 열람이 막혀 [PMC 문헌](https://pmc.ncbi.nlm.nih.gov/articles/PMC12769818/)의 [Europe PMC 공개 전문 XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12769818/fullTextXML)로 저자·DOI·본문·표를 확인했다. 학술 아카이브의 수록을 그 기관의 연구 승인으로 해석하지 않는다.
- **확인:** 실제 시험대의 인위적 마모 고장과 속도·유량 스캔. 압력 100/1,000/2,000 Hz, 진동 1,000 Hz, 속도·토크 10 Hz의 비동기 자료다. 데이터 CC BY 4.0과 논문 CC BY-NC는 적용 대상이 다르다.
- **쓸 질문:** 제어된 조건 전환과 고장 반응의 분리, 추가 압력·유량 센서의 가치.
- **검수 보류점:** 본문에 서술된 온도와 실제 열 설명, 조건/단계 수의 대응, 압력 센서 표의 범위와 정격 압력의 관계를 원시 설명과 대조해야 한다. 저자도 표본화에 따른 왜곡을 제한사항으로 적었다. 보간으로 잃은 고주파 정보가 복원된다고 가정하지 않는다.

### D7. Paderborn University Bearing Data Center

- **원출처:** [대학 공식 배포](https://mb.uni-paderborn.de/en/kat/research/bearing-datacenter/data-sets-and-download), [시험장치 설명](https://mb.uni-paderborn.de/kat/forschung/bearing-datacenter/test-rig-and-measurement-equipment), [2016 원 논문 PDF](https://mb.uni-paderborn.de/fileadmin-mb/kat/PDF/Veroeffentlichungen/20160703_PHME16_CM_bearing.pdf).
- **확인:** 정상·손상 베어링, 여러 운전 조건, 동시 취득한 전류와 진동. 정상 6개·손상 26개 베어링 및 조건별 반복 기록 구조가 설명된다.
- **쓸 질문:** 채널 조합·정상 조건 이동·베어링 개체별 분할. 고주파 센서로 가능한 진단이 프레스의 저속 저장 신호와 어떻게 다른지 비교한다.
- **제한/도입 조건:** 베어링 데이터가 펌프 고장 데이터로 바뀌지는 않는다. 원 신호에서 잘린 창을 서로 다른 개체처럼 분할하지 않는다. 실제 파일의 라이선스·인용 안내를 확보한 뒤 도입한다.

### D8. Hitachi — MIMII DUE

- **원출처:** Tanabe 등 Hitachi 연구진의 [Zenodo v1.01](https://zenodo.org/records/4740355), DOI `10.5281/zenodo.4740355`, [연결 논문](https://arxiv.org/abs/2105.02702). 배포 페이지가 DCASE 2021 Task 2와 직접 연결된다.
- **확인:** 펌프 등 5종 기계의 정상/이상 음향, 기종별 여러 section, 속도·환경소음 등의 source/target 차이. CC BY-NC-SA 4.0.
- **쓸 질문:** 목표 환경의 소량 정상 자료, 조건 변화에 대한 강건성, 알려지지 않은 이상을 평가하는 설계.
- **제한:** 음향 데이터를 진동/전류와 직접 합치지 않는다. DCASE 배포본과 같은 부분을 독립 데이터셋으로 두 번 세지 않는다. “제조 분야라서 전이 가능”이라는 주장의 근거로 삼지 않는다.

### D9. ESPset — Electrical Submersible Pumps

- **원출처:** [저자 Mendeley 배포](https://data.mendeley.com/datasets/m268jsw339/1), DOI `10.17632/m268jsw339.1`; [NINFA-UFES 연구실 코드](https://github.com/NINFA-UFES/ESPset)와 [서지 파일](https://raw.githubusercontent.com/NINFA-UFES/ESPset/master/CITATION.bib).
- **연결 논문:** Varejão 등, **An open source experimental framework and public dataset for vibration-based fault diagnosis of electrical submersible pumps used on offshore oil exploration**, Knowledge-Based Systems 288, 111452 (2024), DOI `10.1016/j.knosys.2024.111452`. 이번에는 논문 서지·배포 설명을 확인했으며 출판사 전문은 열람하지 못했다.
- **확인:** 6,032개 스펙트럼, 회전수에 맞춘 주파수 정규화, 개체 식별자. 데이터 배포 CC BY 4.0과 코드 MIT를 구분한다.
- **쓸 질문:** 개체 단위 분할과 속도 정규화 아이디어.
- **제한:** 시간 순서가 보존된 원시 신호가 아니므로 고장 시작 후 탐지 지연에 쓰지 않는다. 상세 성능 주장이나 고장 유형별 인용은 원 논문 확인 이후로 보류한다.

### D10. FZU_HGPFD — 도입 대기

[배포 저장소](https://github.com/HuiHuang2025/FZU_HGPFD)는 Fuzhou University 연구실·기관 이메일을 표기하고, 6개 건강 상태·28개 속도/압력 조건·48 kHz·3분 기록을 설명한다. 하지만 이번 조사에서는 **기관 공식 페이지/연결 논문과의 교차 확인 및 명확한 라이선스 확인을 완료하지 못했다.**

따라서 이 정보는 후보 발견 기록이다. 데이터를 가져오거나 검증된 연구 데이터로 인용하지 않는다. 기관·저자 연결, 배포 버전, 이용 조건, 개체·회차 구조가 확인되면 조건 변화 검증 후보로 승격할 수 있다. Baidu 링크가 있다는 것 자체를 신뢰 근거로 삼지 않는다.

### D11. 신규 원심펌프 long-tail 데이터 — 도입 대기

[Mendeley 배포 기록](https://data.mendeley.com/datasets/63gjxpn7s6/1), DOI `10.17632/63gjxpn7s6.1`, 2026-06-01 공개 표기는 확인했다. 2 kHz와 정상·단일·복합 고장이라는 소개가 있으나 이번 조사에서 원저자 기관·수집 논문·독립 회차를 충분히 확인하지 못했다. 플랫폼 이름과 CC BY 표기만으로 채택하지 않는다. 불균형·복합 고장 자료의 검색 단서로만 유지한다.

### D12. 국내·로컬 보조 자료

기존 보유 목록에는 KAMP 46 소성가공 자원최적화, KAMP 59 냉간단조 등의 전류·전력·운전 이력이 있다. 이들은 **원본 프레스 펌프와 같은 설비·날짜·고장 라벨로 연결되는 자료가 아니다.** 운영 상태·사이클·추가 수집 항목을 생각하는 참고 자료로 사용한다. 도입 전 해당 원 가이드북과 배포 안내를 다시 연결한다.

국내 검색에서 발견한 프레스 운전·생산 이력 카탈로그는 원문 페이지가 404여서 채택하지 않았다. 같은 대회 펌프의 독립 날짜·고장 이력을 확실하게 제공하는 추가 공개 데이터는 이번 조사 범위에서 확인하지 못했다. 이는 그런 자료가 어디에도 없다는 뜻은 아니다.

## 4. 논문과 방법: 무엇을 배울 것인가

아래는 결과 점수를 복사하기 위한 목록이 아니다. **문제 정의와 실험 설계를 바꾸는 데 필요한 자료**를 중심으로 정리했다. `초록/서지` 표기는 상세 재현성 검토를 끝냈다는 뜻이 아니다. 우리 과제의 채택 판단은 계획상 제안이다.

### 4.1 평가의 함정과 비교 기준

| 자료·1차 링크 | 확인 범위 | 계획에 반영할 점 |
|---|---|---|
| Wu·Keogh, [Current Time Series Anomaly Detection Benchmarks are Flawed…](https://arxiv.org/abs/2009.13807), [저자 공개 요약 원문](https://wu.renjie.im/research/anomaly-benchmarks-are-flawed/ICDE2022_TSAD.pdf) | 초록·저자 원문 | 쉬운 이상, 라벨·밀도·배치 편향을 진단한다. 유명 벤치마크의 높은 점수만으로 실용성을 판단하지 않는다. |
| Kim 등, [Towards a Rigorous Evaluation of Time-series Anomaly Detection](https://arxiv.org/abs/2109.05257), [AAAI 2022 원문](https://cdn.aaai.org/ojs/20680/20680-13-24693-1-2-20220628.pdf) | 초록·학회 원문 | point adjustment와 단순 기준선 부재를 경계한다. |
| [TSB-AD](https://github.com/thedatumorg/TSB-AD), [NeurIPS 2024 원문](https://proceedings.neurips.cc/paper_files/paper/2024/file/c3f3c690b7a99fba16d0efd35cb83b2c-Paper-Datasets_and_Benchmarks_Track.pdf) | 공식 저장소·논문 개요 | 여러 탐지 계열·평가 도구를 찾는 출발점. 통합 리더보드를 우리 데이터의 모델 순위로 쓰지 않는다. |
| [TimeEval / VLDB 2022](https://timeeval.github.io/evaluation-paper/) | 저자 평가 페이지 | 모델 실행 조건·평가 절차를 표준화하는 참고. 모든 알고리즘 실행은 목표가 아니다. |
| Huet 등, [Local Evaluation of Time Series Anomaly Detection Algorithms / affiliation metrics](https://github.com/ahstat/affiliation-metrics-py) | 저자 저장소·설명 | 사건 근처의 탐지를 보는 보조 지표. 독립 고장 부족을 해결하지 않는다. |
| [Position: Quo Vadis, Unsupervised Time Series Anomaly Detection?](https://arxiv.org/abs/2405.02678), ICML 2024 | 초록·서지 | 평가·모델 복잡도에 대한 비판을 검토한다. 이를 “딥러닝은 항상 불필요”로 일반화하지 않는다. |

### 4.2 운전 조건, 정상 기준과 신호 관계

| 자료·1차 링크 | 확인 범위 | 계획에 반영할 점 |
|---|---|---|
| Yu·Qin, [Multimode Process Monitoring with Bayesian Inference-Based Finite Gaussian Mixture Models](https://aiche.onlinelibrary.wiley.com/doi/10.1002/aic.11515), AIChE Journal 2008 | 출판사 페이지·초록 | 여러 정상 모드를 하나의 분포로 묶는 문제. 조건별/혼합 정상 모델의 근거이며 프레스 검증 결과는 아니다. |
| Oh 등, [Hydraulic Rock Drill Hybrid Approach](https://www.papers.phmsociety.org/index.php/phmconf/article/view/3408), PHM 2022 | 학회 원문 페이지 | 목표 개체 정상 참조와 신호처리·학습 결합을 비교 대상으로 삼는다. |
| Katser 등, [Unsupervised Offline Changepoint Detection Ensembles](https://mdpi-res.com/d_attachment/applsci/applsci-11-04280/article_deploy/applsci-11-04280-v2.pdf), 2021 | 출판사 PDF 관련 절 | 여러 통계 변화의 결합 및 SKAB 원출처 연결. **오프라인** 분할 방법을 실시간 지연 성능으로 옮기지 않는다. |
| [ECOD: Unsupervised Outlier Detection Using Empirical Cumulative Distribution Functions](https://arxiv.org/abs/2201.00382), 2022 | 초록·서지 | 가벼운 경험분포 기준선. 점수를 확률로 부르지 않고 평가 배치로 기준이 바뀌는지 점검한다. |
| Adams·MacKay, [Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742), 2007 preprint | 초록·서지 | 지속 변화와 변화 시점의 별도 모델링. 변화점이 곧 고장이라는 가정은 하지 않는다. |
| NIST, [CUSUM](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm), [EWMA](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc324.htm) | 공식 기술 문서 | 작은 지속 변화를 다룰 간단한 기준선. 독립·정상 분포 가정을 시계열에 자동 적용하지 않는다. |

### 4.3 표현학습과 최근 모델

| 자료·1차 링크 | 확인 범위 | 채택 판단에 필요한 점 |
|---|---|---|
| [catch22](https://github.com/DynamicsAndNeuralSystems/catch22), [논문](https://arxiv.org/abs/1901.10200) | 저자 문서·초록 | 기본 특징은 내부 정규화를 사용한다. 평균·분산 이상을 놓치지 않도록 원 크기 특징/catch24를 별도 비교한다. 짧거나 상수인 창의 NaN 처리 필요. |
| [ROCKET](https://arxiv.org/abs/1910.13051), [저자 코드](https://github.com/angus924/rocket) | 초록·저자 문서 | 간단한 통계와 큰 신경망 사이의 표현 후보. 이를 정상 거리 모델에 붙이는 것은 우리 실험 제안이다. |
| [TS2Vec](https://arxiv.org/abs/2106.10466), [저자 코드](https://github.com/zhihanyue/ts2vec), AAAI 2022 | 초록·공식 사용법 | causal 설정을 포함한 표현학습 후보. 진폭 증강이 실제 고장 정보를 지우지 않는지 확인한다. |
| [Anomaly Transformer](https://arxiv.org/abs/2110.02642), [저자 코드](https://github.com/thuml/Anomaly-Transformer), ICLR 2022 | 초록·평가 안내 | 공식 평가의 point adjustment와 미래 문맥 사용을 확인한 뒤 공통 프로토콜로 비교한다. 발표 점수를 그대로 가져오지 않는다. |
| [TranAD](https://arxiv.org/abs/2201.07284), 2022 | 초록·서지 | 시계열 재구성 계열의 도전자 후보. 우리 짧은 기록에서 성능이 좋다는 근거는 아직 없다. |
| [MOMENT](https://arxiv.org/abs/2402.03885), [Auton Lab 모델 카드](https://huggingface.co/AutonLab/MOMENT-1-large), ICML 2024 | 초록·공식 모델 카드·config | MIT. 확인한 large config의 길이는 512다. 최대 50행인 프레스 기록에서 패딩·정규화·추론 시점을 따로 검증해야 한다. |
| [TSPulse](https://arxiv.org/abs/2505.13033), [IBM 공식 모델 카드](https://huggingface.co/ibm-granite/granite-timeseries-tspulse-r1) | 공식 모델 카드·평가 안내 | Apache-2.0, 약 1M 규모. AD 사용 안내가 약 1,536~2,048점 이상을 요구한다. 현재 프레스 짧은 묶음에 즉시 적용할 주력안으로 두지 않는다. 긴 외부 자료에서의 보조 비교 후보다. |

MOMENT/TSPulse의 입력 길이 문제는 **공식 설정과 안내에 근거한 적합성 판단**이다. 짧은 신호를 보간해 길게 만드는 것이 관측 정보를 추가하지는 않는다. 단, 이것만으로 모든 짧은 입력 응용이 불가능하다고 결론내리지는 않으며 별도 적합성 검증을 선행한다.

### 4.4 확률, 조건별 보정과 순차 판단

| 자료·1차 링크 | 확인 범위 | 사용할 때의 경계 |
|---|---|---|
| Bates 등, [Testing for Outliers with Conformal p-values](https://arxiv.org/html/2104.08279), Annals of Statistics 2023, DOI `10.1214/22-AOS2244` | 저자 공개 전문의 분할·조건부 보정 관련 절 | 주변 보장과 특정 보정셋 조건부 보장은 다르다. 더 강한 결과에는 추가 조건이 있다. p값은 현장 고장 확률이 아니다. |
| Barber 등, [Conformal prediction beyond exchangeability](https://arxiv.org/abs/2202.13415), DOI `10.1214/23-AOS2276` | 초록·서지 | 분포 변화에 따른 보장 손실을 다룬다. 임의 드리프트에 대한 무조건 보장으로 인용하지 않는다. |
| Gibbs·Candès, [Adaptive Conformal Inference Under Distribution Shift](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html), NeurIPS 2021 | 학회 초록·저자 개요 | 온라인 피드백과 장기 오차율 적응의 연구. 실제 정상 여부를 모르는 고장 탐지에 그대로 이식하지 않는다. |
| Gibbs·Cherian·Candès, [Conformal Prediction with Conditional Guarantees](https://arxiv.org/abs/2305.12616) | 초록·서지 | 집단별 보정과 표본량의 문제를 검토할 추가 문헌. 현재 적은 보정 자료를 잘게 나눠도 문제가 사라지지 않는다. |
| Howard 등, [Time-uniform, nonparametric, nonasymptotic confidence sequences](https://arxiv.org/abs/1810.08240), Annals of Statistics 2021 | 초록·서지 | 반복 관찰을 고려하는 통계 방향. 유효한 귀무 모형 없이 점수를 누적해 동일 보장을 주장하지 않는다. |
| Guo 등, [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html), ICML 2017 | 학회 원문 페이지·초록 | 확률보정의 기준 문헌. 독립 고장 사건과 실제 유병률이 없는 문제를 보정 함수 하나가 해결하지 않는다. |

### 4.5 계측·물리·현장 경보

| 자료·1차 링크 | 확인 범위 | 계획에 반영할 점 |
|---|---|---|
| NI, [Acquiring an Analog Signal: Bandwidth and Nyquist](https://www.ni.com/en/shop/data-acquisition/measurement-fundamentals/analog-fundamentals/acquiring-an-analog-signal--bandwidth--nyquist-sampling-theorem-.html) | 제조사 계측 기술 문서 | 원 취득·필터·저장 주기를 구분한다. 10 Hz 저장 자료로 미확인 고주파 고장을 진단했다고 하지 않는다. |
| NI, [Dynamic Signal Acquisition Fundamentals](https://www.ni.com/en/shop/data-acquisition-and-control/sound-and-vibration/dynamic-signal-acquisition-fundamentals.html) | 공식 문서 | 향후 고주파·동기 계측 설계의 출발점. |
| Bosch Rexroth, [CytroConnect Solutions](https://www.boschrexroth.com/en/in/connected-hydraulics/products/cytroconnect-solutions/) | 제조사 공식 제품·운영 설명 | 운전 상태와 압력·온도·유량·오일 상태를 포함하는 현장 관측의 참고. 홍보 절감률은 인용하지 않는다. |
| Bosch Rexroth, [Failures—causes and advices](https://www.boschrexroth.com/en/pl/service-and-support/service/repairs/failures-causes-and-advices/) | 공식 유지보수 설명 | 흡입 조건·유체 점도·내부 누설 등 여러 원인 가능성. 진동 증가만으로 원인을 확정하지 않는다. |
| HYDAC, [Test benches and test systems](https://www.hydac.com/download/components-systems-and-service-for-test-benches-and-test-systems-1000451395-en.pdf) | 제조사 문서 | 압력·유량·온도·오일 상태와 장치 운전 맥락을 수집 후보에 포함한다. |
| ISA, [ISA-18 Series](https://www.isa.org/standards-and-publications/isa-standards/isa-18-series-of-standards), [Alarm management life cycle](https://www.isa.org/intech-home/2018/march-april/features/alarm-management-life-cycle) | 공식 소개·기술 해설 | 알림의 목적·우선순위·작업자 조치를 정의한다. 표준 전체 검토·인증·특정 허용 경보율을 확인한 것은 아니다. |
| [OpenHydraulics](https://github.com/modelica-3rdparty/OpenHydraulics), [OpenModelica 문서](https://build.openmodelica.org/Documentation/OpenHydraulics.html) | 배포·기술 문서 | 유압 회로 모델을 통한 가설 검토 후보. 진동 고장 신호를 자동으로 만들어주는 검증된 생성기로 취급하지 않는다. |
| Kauffmann 등, [Explainable AI reveals Clever Hans effects…](https://www.nature.com/articles/s42256-025-01000-2), Nature Machine Intelligence 2025 | 출판사 설명·초록 | 비지도 학습도 편법 특징에 반응할 수 있다는 경고. 논문의 이미지 실험을 프레스의 인과 증거로 옮기지 않는다. |

### 4.6 데이터 증강·합성

데이터 증강 관련 추가 조사 7편과 확인 범위는 [증강 계획의 1차 문헌 목록](04_augmentation_plan.md)에 별도로 정리했다. TimeGAN·T-SMOTE·Diffusion-TS는 원문 관련 절까지 확인했고, TimeVAE·CSDI·2026년 합성 비율 연구는 초록/서지 또는 공식 사용 설명 범위로 구분했다.

## 5. 발견했지만 근거 채택을 보류·제외한 자료

| 자료 | 확인된 상태 | 처리 |
|---|---|---|
| [Multi-Condition Digital Twin Calibration for Axial Piston Pumps](https://arxiv.org/abs/2603.00199) | arXiv에서 철회 상태 확인 | 기술·성능 근거에서 제외. 검색 결과에 남아 있어도 인용하지 않는다. |
| [Digital Twin Calibration of Axial Piston Pumps…](https://arxiv.org/abs/2512.19280) | 저자 preprint 초록 확인 | 압력 기반 디지털 트윈의 아이디어 참고. 동료심사 확인·방법 검수 전 핵심 근거로 쓰지 않는다. |
| [Hydraulic pump fault diagnosis with corrupted flow signals](https://www.sciencedirect.com/science/article/pii/S0951832024006112), DOI `10.1016/j.ress.2024.110539` | 출판사 검색 초록/미리보기, 직접 본문 접근 실패 | 센서 오류 분리 연구의 발견 기록. 상세 방법·성능 인용은 보류. |
| [Robust Fault Diagnosis of Hydraulic Pumps Under Variable Load](https://www.mdpi.com/2076-3417/16/12/6051) | 출판사 검색에 노출되나 본문 접근 제한 | 조건 변화 신호처리의 추가 후보. 검색 요약의 개선 수치를 채택하지 않는다. |
| [Action States for Excavators](https://www.mdpi.com/2076-3417/16/5/2414), DOI `10.3390/app16052414` | 출판사 검색 설명·서지 확인, 직접 본문 미확보 | 실제 제어 입력으로 상태를 나누는 아이디어 후보. 프레스 전류 대용 상태와 같다고 하지 않는다. |
| [프레스 다중 센서 연구, DBpia](https://www.dbpia.co.kr/journal/articleDetail?nodeId=NODE12859580) | 제목·서지 단서, 본문 미확인 | 국내 선행 연구 추가 확인 목록. 방법이나 결과 인용 금지. |
| 프레스 운전·생산 이력 UMAI 카탈로그 | 발견된 원문 주소 404 | 다운로드·데이터량·품질 주장 제외. |
| KAMP 최신 공지·외부 데이터 개정 안내 | 온라인 직접 확인 실패 | 로컬 공식 과제 문서와 구분. 허용 범위를 임의 확정하지 않는다. |
| 블로그, Reddit, 데이터 모음집, 임의 미러 | 원출처를 대신하지 못함 | 검색 단서·브레인스토밍 외 보고서 근거로 사용하지 않는다. |

## 6. 조사에서 도출한 우선 판단

**문헌과 데이터가 함께 뒷받침하는 방향:** 여러 정상 조건을 구분하고, 평가 단위를 지키고, 목표 환경의 정상 기준을 명시하는 설계. 새로운 아키텍처 한 개를 선정하는 것보다 먼저 해결할 사항이다.

**문헌상 가능하지만 현재 데이터가 부족한 방향:** 물리 효율·누설량 추정, 자연 열화 예측, 고장 원인 확정, 실제 시간당 오경보율의 안정적 보장. 자료가 추가되기 전에는 실증 주장으로 발전시키지 않는다.

**최근 모델에 관한 구체적 결론:** 최신이라는 이유로 제외하지도 채택하지도 않는다. 공식 모델 카드에서 입력 길이·정규화·권장 조건을 확인했을 때, 특히 TSPulse AD의 길이 조건은 현재 짧은 프레스 기록과 맞지 않는다. 기존 데이터를 공백 없이 이어붙이는 우회는 허용하지 않는다.

**데이터 선택 제안:** 첫 외부 검증은 연구 질문 하나에 맞춰 고른다. 시작 시점 검증이면 SKAB의 이용 조건을 먼저 정리하고, 조건 이동이면 기존 UCI 또는 PHM을 검토한다. 운전 맥락 조사에는 AI4EU를 쓰되 건강 라벨이 없는 자료에서 FP를 단정하지 않는다. 신규 고장 조건은 Beihang 자료의 검수 항목을 통과했을 때 추가한다.

이 목록은 전 세계 자료를 완전하게 망라했다는 뜻이 아니다. 여러 독립된 조사 경로로 후보를 넓히고, 출처와 과제 적합성으로 좁힌 **이번 계획의 검증 가능한 조사 범위**다.
