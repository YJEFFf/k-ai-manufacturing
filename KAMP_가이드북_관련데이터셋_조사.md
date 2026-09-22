# KAMP 가이드북과 과제 관련 무료 제조AI 데이터셋

확인일: 2026-09-22. [KAMP 무료 제조AI데이터셋](https://www.kamp-ai.kr/aidataList)의 6개 목록 페이지와 **50개 상세 페이지 전체**를 직접 확인했다. 아래 내용은 공식 상세 설명·분석 요약·데이터 미리보기 기준이다.

**50개 모두 가이드북 메뉴가 있고, 비로그인 상태에서는 로그인을 요구한다.** 웹 조사에서는 가이드북 PDF나 원본 데이터 파일을 다운로드하지 않았다. 이후 로컬 폴더에서 ‘로봇용접 예지보전’ 가이드북 PDF 1종이 확인되었다. 파일 확보·본문 검토 상태는 [과제재선정_자료확보목록.md](과제재선정_자료확보목록.md)에서 별도로 관리한다. 가이드북 메뉴 확인과 PDF 본문 검토를 구분한다. 표의 링크는 로그인 후 가이드북을 받을 수 있는 공식 상세 페이지다. 연도는 등록연도이며 실제 센서 수집연도를 뜻하지 않는다.

**현재 방침: 다섯 과제의 추가 자료를 확보한 뒤 수상 가능성만 기준으로 과제를 다시 선정한다.** 기존의 용접 선택은 재검토 대상이며, 아래 자료 열람 우선순위는 과제의 수상 순위가 아니다.

## 1. 이번 다섯 과제에 대응하는 가이드북

| 대회 과제 | 공식 상세·가이드북 진입 | 등록연도 | 공식 상세 설명에서 확인한 분석 방식 |
|---|---|---:|---|
| ① 사출성형 불량예측 | [사출성형기 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=4) | 2020 | 시간·압력·온도·속도 등 공정값, 라벨/무라벨 데이터 활용, Autoencoder·SVM·DNN 비교 |
| ② 로봇용접 불량예측 | [용접기 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=5) | 2020 | SPOT 용접의 가압력·전류·전압·통전시간, 비지도 Autoencoder, 일별 불량 개수 비교 |
| ③ 프레스 유압펌프 예지보전 | [소성가공 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48) | 2022 | 파인블랭킹 프레스의 상·하부 진동·전류, 정상 데이터로 학습한 LSTM-Autoencoder |
| ④ 식품 X-ray 이물검출 | [X-ray 검사장비 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=12) | 2020 | 완제품 X-ray 영상, YOLOv3 객체탐지, 미검·과검 문제 |
| ⑤ 전력·최대피크 예측 | [자원 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=27) | 2021 | 변압기 센서의 15분 측정, 생산·기상·전력 변수, Random Forest·DNN 회귀 |

### 대회 자료와의 대응 수준

- **③은 대응 근거가 강하다.** 공식 설명에 `press_data_normal.csv`, `outlier_data.csv`가 명시되어 있고 정상 20,000행·이상 600행으로 대회 자료와 일치한다. [공식 상세](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48)
- **⑤는 18개 변수 구성이 같다.** 공식 표기의 데이터 개수 111,024는 대회 CSV의 6,168행×18열과 같다. 공식 ‘개수’를 무조건 행 수로 해석하지 않는다. [공식 상세](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=27)
- **①·④는 대응하는 명칭·분석 대상의 가이드이지만 동일 배포본인지는 미확인이다.** 웹페이지가 설명하는 규모와 대회 파일 구성이 같다고 가정하지 않는다. 다운로드 후 파일 목록·해시·행 수로 비교해야 한다.
- 일부 페이지의 최종 수정일이 2025년이라고 해서 데이터 파일이 그때 수정됐다는 뜻은 아니다. 페이지 수정과 파일 버전은 구분한다.

## 2. 현재 용접 과제에 특히 중요한 새 공식 근거

[2020 용접기 상세 페이지](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=5)는 수집을 생산 Lot 단위 불량 이력으로 설명하고, 비지도 오토인코더 사용을 명시한다. 분석결과 설명도 개별 불량품의 정량 평가가 어렵고 일별 개수 예측을 비교했다는 취지다.

이는 앞선 감사에서 확인한 **개별 품질 정답 연결의 한계와 집계 결과 구조**에 부합한다. 현재 대회의 F1·FN/FP 요구를 어떤 방법으로 충족해야 하는지는 여전히 주최 측 답변이 필요하다. 과거 자료의 분석방법이 이번 대회의 평가방법을 자동으로 결정하지는 않는다.

또한 이번 대회 ②에 대응하는 원 자료는 **‘용접기 AI 데이터셋’(2020)**이다. 아래 **‘로봇용접 예지보전’(2022)**은 다른 데이터다.

## 3. 추가로 찾은 용접 관련 무료 데이터 4종

우선순위는 현재 과제인 용접 품질예측·공정조건 분석과의 관련성을 기준으로 정했다. 실제 데이터 품질이나 수상 성능을 비교한 순위는 아니다. 네 항목 모두 2022-12-23 등록이며 가이드북 메뉴가 있다.

| 우선순위 | 공식 상세·가이드북 진입 | 공개 페이지에서 확인한 내용 | 활용과 한계 |
|---:|---|---|---|
| 1 | [용접 공정최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=52) | 강철판→파이프 용접 품질분류와 변수 통제범위. 의사결정나무·XGBoost·LightGBM. 739,888행×7열 | **제품번호 `PIPE_NO`와 결과 열 후보 `FIN_JGMT`를 미리보기에서 확인.** 품질분류·조건범위 연구의 가장 직접적인 참고 후보 |
| 2 | [용접 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=51) | 용접기 노즐 이상, 전류·전압·속도, LSTM-Autoencoder. 정상 81,775행·이상 18,225행, 8열 | 정상학습 이상탐지와 임계값·평가 설계 참고. 설비 이상과 제품 불량을 같은 정답으로 취급하지 않음 |
| 3 | [로봇용접 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=45) | 로봇 용접기의 진동·전류, Convolutional Autoencoder, 팁·기어·벨트 등의 이상 배경 | 로봇 거동·설비 상태 감시 참고. 현재 대회 데이터에는 진동 신호가 없어 동일 입력 모델로 옮길 수 없음 |
| 4 | [전자부품(배터리팩) 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=57) | 배터리모듈 **레이저 용접** 설비의 출력·속도·설정·시간, N-HiTS 예측과 Z-score 이상판정 | 공정 시계열 예측·경보 구조 참고. 점용접과 공정이 다르며 공개 미리보기에는 명시적 제품 양불량 열이 없음 |

### 먼저 읽을 추가 가이드북은 ‘용접 공정최적화’

공개 미리보기의 열은 `PIPE_NO`, `DV_R`, `DA_R`, `AV_R`, `AA_R`, `PM_R`, `FIN_JGMT`다. 센서로 품질을 예측하고 주요 변수의 통제범위를 제안한다는 점이 이번 과제와 가깝다. 다만 공식 설명은 파이프 제작의 아크 용접 공정으로, 대회 점용접과 동일한 공정은 아니다. [공식 상세](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=52)

`FIN_JGMT`의 0/1 의미, 실제 검사 방법, 제품별/시점별 정답 부여 방식은 PDF와 원본을 확인해야 한다. 같은 파이프에서 반복되는 행도 미리보기에 있어 739,888행을 독립 제품 739,888개로 셀 수 없다.

51번과 52번 자료는 제공·수행기관, 파이프 식별자, 다섯 센서의 구조가 같다. 두 자료를 독립 학습셋·검증셋으로 쓰기 전에는 제품번호·시점·센서 중복을 확인해야 한다. 같은 원천의 자료인지 현재 공개 설명만으로 확정하지는 않는다.

## 4. 다른 네 과제에 관련된 추가 무료 데이터

기존 표는 주요 후보를 선별한 목록이었다. 무료 50종을 다시 대조해 인접 공정·센서·분석방법 관련 후보도 보완했다. 아래 관련성은 공식 설명을 토대로 한 판단이며, 대회 원본과 결합 가능하거나 독립 검증용으로 적합하다고 확인한 것은 아니다.

| 관련 과제 | 공식 상세·가이드북 진입 | 어떤 자료인가 | 참고할 범위 |
|---|---|---|---|
| ① 사출 | [사출성형 예지보전](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=56) | Shot 단위 온도·압력·시간·속도·위치, 26열. Lot별 경향을 보고 정상/비정상 상태 라벨링, Autoencoder | 센서 구성이 가까운 추가 후보. 제품 검사 정답과 설비 상태 라벨은 구분 |
| ① 사출 | [머신비전](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=6) | 사출품 320×256 열화상 온도, 수기 두께 기록, SVM 품질판정 | 사출 품질 현상과 다른 검사 방식 이해. 대회 공정 기록과 제품별로 연결된다는 근거는 없음 |
| ① 사출 | [생산공정 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=28) | 콘택트렌즈의 금형조합·곡률·도수, 연관규칙·XGBoost | 목표 품질에 맞는 공정조건 추천의 방법론 |
| ① 사출 | [소성가공 품질보증](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=49) | **압출성형**의 수지 온도·압력·모터속도와 불량예측 | 수지 공정변수와 품질 관계 참고. 사출과 압출의 생산 방식은 다름 |
| ① 사출 | [주조 품질보증](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=55) | 다이캐스팅 Shot별 공정·센서값과 양품/불량유형 이력, XGBoost | 제품 단위 품질분류 설계 참고. 금속 주조와 사출은 재료·공정조건이 다름 |
| ① 사출 | [주조 공정최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=53) | 금형온도·주입압력 등으로 불량 분류와 변수 통제범위 제시 | 품질예측을 공정조건 관리로 연결하는 방법 참고 |
| ① 사출 | [주조 설비 예지보전](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=54) | 다이캐스팅의 예열 중 가생산과 정상 상태 구분 | 예열 구간을 별도로 다루는 분석 참고. 이 상태 라벨을 미래 고장 정답으로 해석하지 않음 |
| ① 사출 | [사출성형 공급망 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=40) | 수주량·생산계획·온습도 시계열 | 같은 업종의 운영 자료이며 제품 불량의 직접 보충 자료는 아님 |
| ③ 예지보전 | [회전기계 고장유형](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=18) | Rotor testbed의 4개 진동센서와 고장유형, DNN·CNN·RNN | 모터 진동의 고장분류·신호처리. 시험장치와 실제 프레스 펌프의 차이 고려 |
| ③ 예지보전 | [교반구동장치](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=9) | 식품 용해탱크 구동부 진동, 정상·결함 데이터, K-NN | 다른 모터 설비의 진동 감시·기준 설정 사례 |
| ③ 예지보전 | [건조구동장치](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=11) | 식품 건조 구동부의 Z축 진동, PCA | 정상 진동 분포로부터의 이탈 분석 |
| ③ 예지보전 | [Ford 엔진 진동](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=2) | FordA 시계열 정상/비정상 분류, CNN·RNN 등 | 시계열 분류 비교 참고. 유압펌프와 다른 설비이며 500개 열을 500개 물리 센서로 단정하지 않음 |
| ③ 예지보전 | [로봇용접 예지보전](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=45) | 로봇 설비의 진동·전류와 Convolutional Autoencoder | 용접 자료이지만 ③의 센서·설비 이상탐지에도 관련. 설비와 고장 원인은 다름 |
| ③ 예지보전 | [장비이상 조기탐지](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=23) | 열풍건조 PLC 수치 데이터와 팬 소리 WAV, LSTM·Decision Tree | 다른 센서를 이용한 설비 이상탐지 참고. 소리와 진동 측정값은 구분 |
| ③ 예지보전 | [열처리 예지보전](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=43) | 열처리로 각 구역의 온도·운전 변수와 Autoencoder | 다변량 설비 상태 감시 방법 참고. 펌프 진동의 직접 보충 자료는 아님 |
| ③ 예지보전 | [프레스기](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=7) | 가압시간·압력과 생산 Lot 불량 이력, Gaussian Mixture Model | 같은 프레스 공정의 품질 이해. 유압펌프 고장 정답과 구분 |
| ③ 예지보전 | [기계부품 품질보증](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=59) | 냉간단조 운전 기록, 모터 전류·주파수 등과 정상/불량 분류 | 인접 성형설비의 상태·제품 품질 관계 참고. 정확한 라벨 정의는 원본 확인 필요 |
| ④ X-ray | [품질 이상탐지,진단(크로메이트)](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=25) | 표면처리 공정 pH·온도·전압·시간과 제품 영상, Decision Tree·CNN | 영상 품질검사 사례. **X-ray 또는 식품 이물 위치 정답을 보충하는 자료는 아님** |
| ④ X-ray | [머신비전](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=6) | 사출품 열화상 품질검사 | 다른 영상검사의 설계 참고. X-ray와 영상 형성 원리가 다름 |
| ④ X-ray | [제조현장 안전관리](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=29) | 작업자 영상, 위치박스 라벨, YOLO | 객체검출·위치 정답 형식 참고. 식품·X-ray·이물 데이터는 아님 |
| ⑤ 전력 | [소성가공 자원최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=46) | 로봇 2대·프레스 4대의 설비 ID·측정시각·전류·공정정보, 전력 사용량 예측 | **가장 직접적인 추가 전력 자료.** 설비별 부하·공정조건과 에너지의 관계 참고 |
| ⑤ 전력 | [표면처리 자원 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=41) | 가이드 목표는 인원예측이나, 미리보기에 `Power_Usage`·`Power_Cost`·생산량·온습도·시각 존재 | **전력사용량 후보열이 있어 확보 후 검토 필요.** 단위·실측/파생 여부·원 자료 27번과의 중복은 미확인 |
| ⑤ 전력 | [생산계획 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=30) | 설비·처리시간·용량·수량·납기 관련 생산계획, 유전알고리즘 | 생산 스케줄 제약을 모델링하는 방법론. 전력 측정 데이터는 아님 |
| ⑤ 전력 | [공급망 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=26) | 발주·계획발주 시계열과 LSTM 미래 발주수량 예측 | 생산량·수요 예측의 보조 사례. 동일 공장 전력자료로 합칠 수 없음 |
| ⑤ 전력 | [표면처리 공급망 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=36) | 생산 시작·종료·수량과 출고 일정, 유전알고리즘 | 생산계획 제약 참고. 전력 측정 자료는 아님 |
| ⑤ 전력 | [열처리 공급망 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=37) | 생산·재고·수주와 미래 출고량 예측, 베이지안 신경망 | 수요 예측과 불확실성 분석 참고. 전력 측정 자료는 아님 |
| ⑤ 전력 | [사출성형 공급망 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=40) | 수주량·생산계획과 1D CNN | 생산 수요 예측 방법 참고. ①과 중복 후보이므로 파일은 한 번만 확보 |

현재 확인한 무료 50종 중 **식품 X-ray 이물검출이라는 같은 문제의 추가 데이터셋은 찾지 못했다.** 위 영상 자료는 다른 문제의 참고 사례다. 원 X-ray 상세 설명은 검출 결과가 표시된 이미지를 사용한다고 명시해, 기존 감사에서 발견한 영상 내 표식과 부합한다. [X-ray 공식 상세](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=12)

## 5. 이름 때문에 혼동하기 쉬운 자료

- [표면처리 자원 최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=41)의 가이드 목표는 **투입 인원 예측**이지만, 미리보기에 `Power_Usage`가 있다. 기존 설명에서 인원 목표만 보고 전력 후보에서 제외한 해석은 좁았다. 전력 관련 추가 검토 대상으로 포함하되, 실제 활용 가능성은 원본과 PDF를 확인한다.
- [정밀가공 자원최적화](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=44)는 레이저 반사광으로 **미세 홀의 품질**을 구별한다.
- [전자부품(배터리팩) 품질보증](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=58)은 배터리셀의 **충방전 시험** 전압·온도 자료다. 용접 자료는 57번 예지보전 항목이다.
- [프레스기](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=7)는 프레스 성형 조건과 품질·공정 최적화 자료다. 이번 ③의 유압펌프 진동·전류 자료는 48번이다.
- [소성가공 품질보증](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=49)은 수지 온도·압력·모터속도를 사용한 압출 품질 문제로 설명된다. 이번 프레스 펌프 예지보전과 다르다.

## 6. 가이드북을 받는 경로

1. KAMP에 로그인한다.
2. 위 표의 공식 상세 링크를 연다.
3. ‘가이드북’ 버튼을 누른다.
4. 사이트에서 요구하는 활용목적을 선택하고 안내·동의 내용을 확인해 다운로드한다.

용접 자료 내부의 열람 순서는 **2020 용접기 → 2022 용접 공정최적화 → 2022 용접 예지보전**이 유용하다. 다섯 과제 재선정을 위해서는 각 과제의 원 가이드북과 추가 후보를 함께 확보·검토한다.

가이드북과 관련 데이터가 무료로 제공된다는 사실은 이번 대회에서 추가 데이터를 학습·검증에 사용해도 된다는 승인과 별개다. 외부 데이터 허용 여부는 문의 답변에 따라 정하고, 다른 공정에서의 성능을 제공된 점용접 자료의 성능으로 표현하지 않는다.

## 7. 조사 범위와 확인 자료

- KAMP 무료 목록 6개 페이지, 상세 50개 페이지를 모두 공개 GET 요청으로 읽었다. 상세 설명·모델·미리보기·가이드북 메뉴·로그인 안내를 확인했다.
- 웹 조사만으로 PDF 본문, 원본 데이터의 전체 라벨·중복·분할 가능성, 대회 배포본과의 바이트 단위 동일성을 확인한 것은 아니다. 이후 로컬에 확보된 파일의 검토 결과는 별도 확보목록에 기록한다.
- [공공데이터포털의 공식 50종 목록](https://www.data.go.kr/data/15089213/fileData.do)도 대조했다. 그 CSV의 연번과 KAMP 상세 주소의 `DATASET_SEQ`는 일부 다르므로 링크는 실제 목록에서 추출했다.
- 공개 페이지 수집 결과는 `/tmp/kamp_free_catalog.json`, 재현 스크립트는 `/tmp/kamp_free_catalog.py`에 있다. 로그인 우회나 외부 연락, GitHub 업로드는 수행하지 않았다.

## 부록: 확인한 무료 50종 전체 목록

아래 각 상세 페이지에 가이드북 메뉴가 있다. 이 번호는 순위가 아니라 KAMP `DATASET_SEQ` 식별자다.

| 식별자 | 공식 데이터셋명·상세/가이드북 진입 |
|---:|---|
| 1 | [제조 현장용 OCR학습 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=1) |
| 2 | [Ford 엔진 진동 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=2) |
| 3 | [CNC 머신 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=3) |
| 4 | [사출성형기 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=4) |
| 5 | [용접기 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=5) |
| 6 | [머신비전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=6) |
| 7 | [프레스기 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=7) |
| 8 | [용해탱크 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=8) |
| 9 | [교반구동장치 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=9) |
| 10 | [살균기 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=10) |
| 11 | [건조구동장치 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=11) |
| 12 | [X-ray 검사장비 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=12) |
| 16 | [제조현장용 Scene-Text Recognition 학습 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=16) |
| 18 | [회전기계 고장유형 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=18) |
| 19 | [공정운영 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=19) |
| 20 | [품질 이상탐지,진단(전해탈지) AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=20) |
| 21 | [품질 이상탐지,진단(도금욕) AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=21) |
| 23 | [장비이상 조기탐지 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=23) |
| 25 | [품질 이상탐지,진단(크로메이트) AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=25) |
| 26 | [공급망 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=26) |
| 27 | [자원 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=27) |
| 28 | [생산공정 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=28) |
| 29 | [제조현장 안전관리 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=29) |
| 30 | [생산계획 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=30) |
| 36 | [표면처리 공급망 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=36) |
| 37 | [열처리 공급망 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=37) |
| 40 | [사출성형 공급망 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=40) |
| 41 | [표면처리 자원 최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=41) |
| 42 | [화장품 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=42) |
| 43 | [열처리 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=43) |
| 44 | [정밀가공 자원최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=44) |
| 45 | [로봇용접 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=45) |
| 46 | [소성가공 자원최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=46) |
| 47 | [전자부품(음향기기) 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=47) |
| 48 | [소성가공 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48) |
| 49 | [소성가공 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=49) |
| 50 | [정밀가공 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=50) |
| 51 | [용접 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=51) |
| 52 | [용접 공정최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=52) |
| 53 | [주조 공정최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=53) |
| 54 | [주조 설비 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=54) |
| 55 | [주조 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=55) |
| 56 | [사출성형 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=56) |
| 57 | [전자부품(배터리팩) 예지보전 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=57) |
| 58 | [전자부품(배터리팩) 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=58) |
| 59 | [기계부품 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=59) |
| 60 | [열처리 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=60) |
| 61 | [열처리 공정최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=61) |
| 62 | [의류 품질보증 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=62) |
| 90 | [의류 공정최적화 AI 데이터셋](https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=90) |
