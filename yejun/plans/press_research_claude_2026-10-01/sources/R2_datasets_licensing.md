# R2 — 이 과제를 도울 공개 데이터셋과 라이선스 조사

- 작성일: 2026-10-01 (KST)
- 대상 과제: ③ 진동·전류 시계열 기반 프레스 유압펌프 이상 조기탐지 및 오경보 분석 (KAMP 「소성가공 예지보전 AI 데이터셋」)
- 확인 표기: **opened** = 내가 페이지·PDF·API 응답을 직접 열어 내용을 봄 / **search-only** = 검색 결과 요약으로만 봄 / **unverified** = 확인 못 함
- 등급: **A** = 동료심사 학술지·주요 학회·정부·공공기관 / **B** = 프리프린트·기술보고서·학위논문·데이터 저장소 기록·제조사 문서 / **C** = 블로그·포럼·GitHub 개인 저장소·홍보물(근거가 아니라 단서로만 씀)

---

## 0. 조사 방법과 범위(짧게)

- 웹 검색(WebSearch)·페이지 열람(WebFetch), DOI 메타데이터 API(Crossref, DataCite), Zenodo·Kaggle·GitHub API, Europe PMC 본문 API, KAMP 포털(curl로 공개 페이지 열람)을 썼다.
- 로컬에서는 대회 원자료(`데이터셋/프레스_유압펌프_예지보전/data/…`)와 KAMP 가이드북 PDF(읽기 전용), 그리고 다른 KAMP 데이터셋 압축 파일 **목록**과 가이드북 표지·데이터 설명 쪽만 봤다. 다른 데이터셋 압축은 풀지 않았다. `yejun/` 폴더와 저장소 git 기록은 열지 않았다.
- 이 세션의 WebSearch 한도(200회)가 조사 막바지에 소진됐다. 그 뒤로는 Zenodo·DataCite·Crossref API와 직접 URL 열람으로만 확인했다. 그래서 KCI·DBpia·RISS 전수 검색과 "stamping/servo press 데이터셋" 추가 검색은 끝내지 못했다(5절).
- 작업 메모: Crossref API를 1회 호출할 때 사용자 이메일을 User-Agent(mailto)에 넣었다. 지침 위반이며, 다른 서비스에는 보내지 않았다.

---

## 1. 핵심 요약

1. **대회 데이터의 공식 이용조건은 "사용조건: 콘텐츠 변경허용" 하나다.** KAMP 상세 페이지(DATASET_SEQ=48)와 가이드북 표지에 출처 표기 양식이 있고, "연구/공식적으로 사용할 때는 KAMP 출처를 남기고, 인용 시 활용한 내용과 문서를 kamp@kaist.ac.kr로 보내 달라"고 **요청**한다. KAMP 이용약관에는 데이터 저작권·재배포 조항이 없다(opened).
   - 대회가 학습 데이터를 zip에 넣으라고 요구하므로, 제출 zip에 넣는 것은 주최 측이 허용한 배포로 보는 것이 합리적이다.
   - 공개 GitHub 같은 일반 공개 재배포는 근거 조항이 없으니 피하는 것이 안전하다. 실제로 경쟁팀 중 한 곳은 원본 CSV를 공개 저장소에 올렸고, 다른 팀은 "재배포하지 않는다"며 뺐다.
2. **가이드북 PDF는 zip·보고서에 넣지 말 것.** 표지에 다운로드한 사람의 KAMP 회원 ID·다운로드 일시·활용목적과 문서 고유번호 워터마크가 찍혀 있다. 블라인드 평가와 개인정보 측면에서 위험하다. 또 그림 1·2·5·6·7·8·9·11이 네이버 블로그, 네이버 지식백과, tistory, f-secure 블로그, ResearchGate, 타 논문에서 가져온 제3자 그림이라 재사용하면 안 된다.
3. **정상·이상 두 파일의 숫자 형식이 다르다(직접 확인).** 이상 파일의 전류값 99.67%가 **1.19209 간격 격자** 위에 있고(고유값 340개), 정상 파일은 0.18%뿐이다(고유값 19,934개). 진동 소수 자릿수도 정상은 대부분 6자리, 이상은 8~9자리다. 공개 경쟁팀 저장소가 먼저 보고한 "형식 누수"를 원자료로 재확인한 것이다. 형식을 통일하지 않으면 어떤 모델이든 "파일"을 구분하게 된다.
4. **이 데이터를 쓴 동료심사 논문은 찾지 못했다**(KCI·DBpia·ScienceON 검색 범위 안에서). 비교점은 세 가지다.
   - 가이드북의 LSTM-AE: Accuracy 97.51%, F1 0.7476. 단, 20행 겹침 윈도우 단위로 계산했고, 임곗값을 **같은 단일 이상 사건의 앞부분 300윈도우**로 정했다.
   - 이를 재현한 2023년 수업 저장소.
   - 2026년 대회 경쟁팀 공개 저장소 4곳 이상. 형식 누수 단일특징 AUC 0.94~1.000, 정상 전류 0.6 Hz 에일리어싱, 라벨 노이즈 의심, 고부하 구간 FP 집중, 합성 이상 주입 같은 결과가 이미 공개돼 있다. 이 저장소들은 라이선스가 없으므로 코드·문장을 가져오면 안 된다.
5. **유압 쪽에서 가장 쓸모 있는 공개 데이터는 UCI/ZeMA "Condition monitoring of hydraulic systems"(CC BY 4.0)다.**
   - 내부 펌프 누설 0/1/2 단계 라벨이 있고, 모터 전력 EPS1은 100 Hz, 진동 VS1은 1 Hz다. 2,205사이클.
   - 쓸 곳: 합성 고장 크기 보정, "전류 이상 ≠ 펌프 고장"(밸브·어큐뮬레이터·냉각기 변화도 모터 전력을 바꾼다) 정량화, 파이프라인 일반화 시연. zip에 넣을 수 있다(출처·변경사항 표기 조건).
6. **모터 전류+진동 펌프 데이터로는 NLN-EMP(CC0)가 가장 낫다.**
   - 인버터(VFD) 구동 원심펌프 2대, 11개 고장 유형(캐비테이션, 임펠러 손상 등)과 심각도, 전류·전압·진동 20 kHz.
   - 수집도 우리처럼 **버스트 방식**이다(전류 15초씩 2분마다, 진동 60초씩 5분마다).
   - 10 Hz로 그대로 솎아 에일리어싱과 운전속도(50/75/100%) 변화에 따른 오경보를 재현하는 데 쓸 수 있다. 다만 원심펌프라 기어펌프와 도메인 차이가 크고, 압축 20.8 GB라 일부만 써야 한다.
7. **사건 단위 지표와 오경보 분석을 설계·검증할 다중 에피소드 저속 벤치마크**는 둘이다. 둘 다 학습용이 아니라 지표·지속성 규칙·확률 보정을 검증하는 용도다.
   - SKAB: 물 순환 펌프 리그, 진동 RMS 2채널과 모터 전류, 1초 해상도, 이상 실험 34개(밸브, 캐비테이션, 5가지 개시 형태의 불평형). 라이선스가 GitHub은 GPL-3.0, Kaggle은 AGPL-3.0으로 서로 다르다.
   - MetroPT-3: 지하철 공기압축기, 모터 전류 포함, 정비기록으로 문서화된 실제 공기누설 고장 4건. CC BY 4.0.
8. **운전조건 변화에 따른 오경보 스트레스 테스트용**으로는 KAIST Jung et al. 2023(CC BY 4.0; 부하 0/2/4 Nm, 속도 680~2460 rpm 가변, 3상 전류 25.6/100 kHz)과 Chen et al. 2026(CC BY 4.0; 가변 속도·부하와 과도 구간, 3상 전류+3축 진동 12.8 kHz)이 깨끗하다.
9. **KAMP 안의 다른 데이터셋도 "외부 데이터"로 취급해야 한다.** 2026 공고 문구는 "KAMP 내 제조AI데이터셋(총 50종) 중 1종 또는 여러 종 활용하여 **문제 출제 예정**"이다. 출제 범위를 말한 것이지 참가자가 다른 KAMP 데이터를 써도 된다는 허가는 아니다. 그래도 같은 이용조건(콘텐츠 변경허용)이고 로컬에 이미 있어 위험이 낮다. 특히 둘이 쓸모 있다.
   - **「소성가공 자원최적화 AI 데이터셋」**: 프레스 4대의 **유압펌프 모터 전류 RMS** 1.5개월치와 생산기록. 정상 운전변화(품목, 주·야간, 비가동)의 폭을 보여 주는 오경보 근거로 쓸 수 있다.
   - **「용접 예지보전 AI 데이터셋」**: 같은 수행기관 ㈜인터엑스, 같은 normal/outlier 파일 체계, 같은 LSTM-AE. 형식 누수가 수행기관 처리 과정의 공통 산물인지 확인하는 데 쓸 수 있다.
10. **훈련·zip에 쓰지 말아야 할 것**
    - AI Hub: 내국인만 신청, 학습용 한정, 승인 없는 제3자 열람·제공 금지, 국외 반출은 별도 합의.
    - Paderborn KAt: CC BY-NC 4.0.
    - CWRU, MAFAULDA, PHM 2022 rock drill: 데이터 라이선스 표기 없음.
    - Kaggle pump_sensor_data: 라이선스 "Unknown", 수원(水源) 펌프 데이터인데 2026 arXiv 한 편이 "hydraulic pump"라고 잘못 기술함.
    - Crompton Greeves: 합성 데이터에 구독 필요.
    - KAMP 실증 데이터셋: 로그인 필요, 사용조건 표기 없음.
    - Hercik & Svoboda 2023의 실제 유압프레스 데이터(축방향 피스톤펌프 132/75 kW, 펌프 플랜지 진동과 펌프모터 전류 포함)는 가장 현장에 가까운 사례다. 하지만 명시 라이선스가 없고 영업비밀에서 나온 데이터라 서술용 근거로만 쓴다.

---

## 2. 출처 표

| ID | 출처(저자·제목·매체·연도·DOI/URL) | 유형·등급 | 확인 | 라이선스·이용조건 | 레드플래그 | 공개 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S01 | 중소벤처기업부·KAMP, 「소성가공 예지보전 AI 데이터셋」 상세 페이지. 제공 스마트제조혁신추진단(수행 ㈜인터엑스), 등록 2022-12-23 13:13:36, 최종수정 2025-04-02. https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48 | 정부 플랫폼 데이터 페이지, A | opened (2026-10-01) | "사용조건: 콘텐츠 변경허용". 출처표기 양식과 kamp@kaist.ac.kr 송부 요청 | 재배포·상업 조항 없음. 센서 표기 "모터의 상하부 진동"이 가이드북의 "유압펌프 상/하단"과 다름 | 낮음. 출처 표기 필수 |
| S02 | ㈜인터엑스/KAMP, 「소성가공 예지보전 AI 데이터셋」 분석실습 가이드북(65쪽, 문서번호 워터마크, 다운로드 2026-09-22). 로컬 PDF | 공공 플랫폼 기술문서, B | opened | 표지에 국·영문 출처표기 양식. 사용조건 콘텐츠 변경허용 | 표지에 다운로더 회원 ID. 그림 다수가 제3자 출처 | 높음(가이드북 PDF·그림 재사용 시). 수치 인용은 가능 |
| S03 | KAMP 이용약관. https://www.kamp-ai.kr/agreement | 정부 플랫폼 약관, A | opened | 데이터 저작권·재배포 조항 없음. 개별 서비스 별도 약관 적용(제3조) | 약관은 "한국과학기술원 운영"이라 쓰는데 하단 운영기관은 TIPA·NHN·이노비즈 | 해석상 불확실성 |
| S04 | 이노비즈협회, 「2026년 제6회 K-인공지능(AI) 제조데이터 분석 경진대회」 공고. https://www.kamp-ai.kr/contestDetail?CPT_SEQ=38 (공지 CPT_NOTICE_SEQ=27, 첨부 HWP) | 공공 위탁기관 공고, A | opened (페이지). HWP·과제안내 미열람 | "KAMP 내 등재된 제조AI데이터셋(총 50종) 중 1종 또는 여러 종 활용하여 문제 출제 예정". 공개 페이지에 외부데이터 조항 없음 | 외부데이터 규정은 팀이 가진 과제문 기준 | 낮음 |
| S05 | 중소기업기술정보진흥원, 「제조AI 데이터셋 50종_20241231」 목록. 공공데이터포털 https://www.data.go.kr/data/15089213/fileData.do | 공공데이터, A | opened, CSV 내려받음 | 목록 파일은 "이용허락범위 제한 없음". 50종 전부 사용조건 "콘텐츠 변경허용" | 목록의 라이선스이지 데이터셋 자체의 것이 아님 | 낮음 |
| S06 | KAMP 실증 제조AI데이터셋: 프레스성형기(SEQ 89), 진공펌프(HD) 가동(108), 진동 결함 시뮬레이터(45, 56). KAMP 지역 데이터셋(146, 147) | 플랫폼 데이터 페이지, A(플랫폼) | opened | 다운로드에 로그인 필요. 사용조건 미표기 | 50종 밖이라 외부데이터. 조건 불명 | 중간 |
| S07 | KAMP 50종 가운데 관련 데이터셋 가이드북: 회전기계 고장유형(KAIST 이필승, 2021-12-27), 용접 예지보전(인터엑스, 2022-12-23), 소성가공 자원최적화(KAIST/UNIST/리쉐니에, 2022-12-23), 기계부품 품질보증(임픽스), 프레스기(UNIST/EPM, 2020-12-14). 로컬 PDF | 공공 플랫폼 기술문서, B | opened (표지·데이터 쪽) | 모두 "콘텐츠 변경허용" | 과제 지정 데이터가 아님(외부데이터 취급) | 낮음 |
| S08 | yskim9574, `DFclass-2023/LSTM_pressformingmachine_anomaly` (GitHub, 2023-09-13 생성) | 개인 저장소, C | opened | 라이선스 없음 | 가이드북 코드 재현 | 인용 불필요 |
| S09 | ChoeHyeongSoo, `KAMP-Manufacturing-AI` README와 PR #1, #7, #11, #14, #20 (2026-09-26~) | 경쟁팀 저장소, C | opened (gh API) | 라이선스 없음(모든 권리 유보) | 진행 중이고 검토되지 않은 주장 | 높음. 보고서에 인용하지 말고 우리 검증만 쓸 것 |
| S10 | kimjaehyeonC, `Kamp_AI` (2026-09-22~) | 경쟁팀 저장소, C | opened | 라이선스 없음. 데이터 미커밋 | 위와 같음 | 높음 |
| S11 | ekhwn0430, `KAMP` (2026-09-15~) | 경쟁팀 저장소, C | opened | 라이선스 없음. **원본 CSV 2개를 공개 커밋** | KAMP 데이터 공개 재배포 사례 | 높음 |
| S12 | seokchu, `2026_-` (2026-09-26~) | 경쟁팀 저장소, C | opened | 라이선스 없음. "대회 제공 데이터는 재배포하지 않으므로" 데이터 제외 | — | 높음 |
| S13 | 7SH7, `multi_agent` (2025) — 이 데이터의 임계값을 챗봇 지식베이스로 사용 | 개인 저장소, C | search-only (코드 검색 결과)와 저장소 메타데이터 | 라이선스 없음 | 분석 연구가 아님 | — |
| S14 | Helwig N., Pignanelli E., Schütze A., *Condition monitoring of hydraulic systems* [Dataset], UCI ML Repository, DOI 10.24432/C5CW21 | 데이터 저장소, B (관련 논문은 A) | opened (UCI 페이지, DataCite) | **CC BY 4.0** ("sharing and adaptation … for any purpose, provided that the appropriate credit is given") | 없음 | 낮음. 출처 표기 |
| S15 | Helwig N., Pignanelli E., Schütze A. (2015). Condition monitoring of a complex hydraulic system using multivariate statistics. *IEEE I2MTC 2015 Proc.*, pp. 210–215. DOI 10.1109/I2MTC.2015.7151267 | 학회논문, A | Crossref 메타데이터만 opened. 본문 미열람 | IEEE 저작권 | — | 그림 재사용에는 허가 필요 |
| S16 | Helwig N., Pignanelli E., Schütze A. (2015). D8.1 Detecting and compensating sensor faults in a hydraulic condition monitoring system. *Proc. SENSOR 2015*, pp. 641–646. DOI 10.5162/sensor2015/D8.1 | 학회논문, A | Crossref 메타데이터만 | 미확인 | — | 그림 재사용 주의 |
| S17 | Schneider T., Klein S., Bastuck M. (2018). *Condition monitoring of hydraulic systems Data Set at ZeMA*. Zenodo. DOI 10.5281/zenodo.1323611 | 데이터 저장소, B | opened (DataCite) | **CC BY 4.0** | 설명으로 보아 UCI 판과 같은 데이터(파일 대조는 안 함) | 낮음 |
| S18 | Schneider T., Helwig N., Schütze A. (2018). Industrial condition monitoring with smart sensors using automated feature extraction and selection. *Meas. Sci. Technol.* 29. DOI 10.1088/1361-6501/aad1d4 | 학술지, A | Crossref 메타데이터만 | IOP 표준 저작권 | 논문번호 미확인 | 그림 재사용에는 허가 필요 |
| S19 | Wang T., Ma J., Fu Y. Multi-mode fault dataset for aviation piston pump based on standard test procedure. *Data in Brief* 64, 112336 (Crossref 발행 2026-02; 온라인 2025). DOI 10.1016/j.dib.2025.112336. 데이터: Mendeley 10.17632/xw8gjjk9km.1 | 데이터 논문, A | opened (PMC, Mendeley, DataCite) | **데이터 CC BY 4.0**(Mendeley·DataCite), **논문 CC BY-NC 4.0** | 논문과 데이터 라이선스가 다름. 고장은 사포(P400)로 만든 마모(시뮬레이션 시험) | 데이터는 낮음. 논문 그림은 NC |
| S20 | Bosch Research, `Hydraulic-EoL-Testing` (GitHub) + Gaugel S., Reichert M. (2023). PrecTime … *Eng. Appl. Artif. Intell.* DOI 10.1016/j.engappai.2023.106078 | 기업연구 저장소 B / 학술지 A | opened (README), Crossref | README: 데이터 **CC BY 4.0**(LICENSE 파일은 없음) | 센서 익명화·정규화, 라벨 의미 비공개 | 낮음 |
| S21 | Jakobsson E., Frisk E., Krysander M., Pettersson R. (2022). A Dataset for Fault Classification in Rock Drills, a Fast Oscillating Hydraulic System. *Annual Conf. PHM Society* 14. DOI 10.36001/phmconf.2022.v14i1.3144. 데이터 https://data.phmsociety.org/2022-phm-conference-data-challenge/ | 학회논문 A, 챌린지 데이터 | opened (논문 PDF, 데이터 페이지) | 논문 CC BY 3.0 US. **데이터 라이선스 명시 없음** | 압력만 50 kHz, 정규화됨 | 재배포 불가로 간주 |
| S22 | Barczewski R., Szewczyk S., Staszewski W., Dao P. (2026). *Vibration dataset of a rotor-shaft test rig (misalignment under load variations)* v2. Mendeley. DOI 10.17632/cbpr9fvvwb.2 | 데이터 저장소, B | opened (Mendeley, DataCite) | **CC BY 4.0** | 진동만 있음(전류 없음) | 낮음 |
| S23 | Hercik R., Svoboda R. (2023). Collecting and Pre-Processing Data for Industry 4.0 Implementation Using Hydraulic Press. *Data* 8(4):72. DOI 10.3390/data8040072. 공개분: Google Drive 폴더(논문에 URL) | 학술지(MDPI), A | opened (PDF, 폴더 목록). README_DATA 미열람 | 논문 CC BY 4.0. 데이터는 "publicly available without restrictions for other researchers"라고만 함. **명시 라이선스 없음**, 나머지는 NDA | 영업비밀 출처. 무작위 80/20 분할 | 데이터 재배포 금지로 간주. 논문은 인용 가능 |
| S24 | Jancarczyk D., Wróbel I., Danielczyk P., Sidzina M. (2024). Enhancing Vibration Analysis in Hydraulic Presses: A Case Study Evaluation. *Applied Sciences* 14(7):3097. DOI 10.3390/app14073097 | 학술지(MDPI), A | opened (PDF) | 논문 CC BY 4.0. 데이터는 "available … on request" | 프레스 구조물 진동이지 펌프 진동이 아님 | 낮음 |
| S25 | Maschler B., Knodel T., Weyrich M. (2021). Towards Deep Industrial Transfer Learning for Anomaly Detection on Time Series Data. IEEE ETFA 2021, arXiv:2106.04920 | 학회/프리프린트, A/B | opened (arXiv PDF) | 데이터 비공개 | 8개 펌프가 붙은 유압프레스 데이터지만 비공개 | — |
| S26 | nphantawee, *pump_sensor_data*, Kaggle | 커뮤니티 데이터, C | opened (Kaggle API) | **"Unknown"** | 출처가 "친구의 소도시 물 펌프"로 일화적. 센서 익명 | 사용 금지 권장 |
| S27 | Sánchez P., Reyes K., Radu B., Fernández E. (2026). LSTM vs. Feed-Forward Autoencoders for Unsupervised Fault Detection in Hydraulic Pumps. arXiv:2601.11163 | 프리프린트, B | opened (PDF) | — | **S26(물 펌프, 센서 익명)을 "hydraulic pump"로 기술하고 센서 범주를 단정함** | 근거로 쓰지 말 것 |
| S28 | Rajesh T., Pillai A.S. (2025). *Crompton Greeves Three Phase Pump-Predictive Maintenance Dataset*. IEEE DataPort. DOI 10.21227/1bzr-hq65 | 데이터 저장소, C | opened (페이지, DataCite) | DataCite는 CC BY 4.0이라 하지만 **구독 필요** | **합성(synthetic) 데이터** | 사용 금지 권장 |
| S29 | ESPset (Pellegrini et al., Mendeley 10.17632/m268jsw339.1); Centrifugal Pump Multi-Fault Vibration Dataset under Long-Tailed Distributions (jiang, Mendeley 10.17632/63gjxpn7s6.1) | 데이터 저장소, B | DataCite 메타데이터만 opened | 둘 다 CC BY 4.0 | 진동만, 원심/잠수펌프 | 낮음 |
| S30 | Bruinsma S., Geertsma R., Loendersloot R., Tinga T. (2024). Motor current and vibration monitoring dataset for various faults in an E-motor-driven centrifugal pump. *Data in Brief* 52:109987. DOI 10.1016/j.dib.2023.109987. 데이터 NLN-EMP: 4TU.ResearchData DOI 10.4121/2b61183e-c14f-4131-829b-cc4822c369d0.v4 | 데이터 논문, A | opened (4TU, DataCite, Europe PMC 본문) | **데이터 CC0 1.0**, 논문 CC BY | 원심펌프, 해군 시험장 | 낮음 |
| S31 | Jung W., Kim S.-H., Yun S.-H., Bae J., Park Y.-H. (2023). Vibration, acoustic, temperature, and motor current dataset of rotating machine under varying operating conditions for fault diagnosis. *Data in Brief* 48:109049. DOI 10.1016/j.dib.2023.109049. 데이터 Mendeley 10.17632/ztmf3m7h5x.6, vxkj334rzv.7, x3vhp8t6hg.7, j8d8pfkvj2.7 | 데이터 논문, A | opened (Europe PMC 본문, DataCite) | 데이터·논문 모두 **CC BY 4.0** | 회전기계 리그(펌프 아님) | 낮음 |
| S32 | Lessmeier C., Kimotho J.K., Zimmer D., Sextro W. (2016). Condition Monitoring of Bearing Damage in Electromechanical Drive Systems by Using Motor Current Signals of Electric Motors: A Benchmark Data Set for Data-Driven Classification. *PHM Society European Conf.* 3. DOI 10.36001/phme.2016.v3i1.1577. 데이터: KAt-DataCenter, Paderborn Univ. | 학회논문 A, 데이터 | opened (KAt 페이지, 논문 PDF) | **데이터 CC BY-NC 4.0** ("Commercial use requires contacting the authors"). 논문 CC BY 3.0 | NC 조건 | 상금이 걸린 대회라 NC 해석 위험. zip에 넣지 않음 |
| S33 | Chen S., Liu Z., Li C., Zou D., He X., Zhou D. (2026). Multi-mode Fault Diagnosis Datasets of Three-phase Asynchronous Motor Under Variable Working Conditions. arXiv:2601.02278. 데이터 Mendeley 10.17632/6s3dggj9mw.1 | 프리프린트 B, 데이터 | opened (PDF, DataCite) | 데이터 **CC BY 4.0** | 프리프린트(심사 전) | 낮음 |
| S34 | Case Western Reserve University Bearing Data Center. https://engineering.case.edu/bearingdatacenter/welcome | 대학 데이터 페이지, B | opened | **이용조건·라이선스 표기 없음** | 진동만. 문헌상 문제점이 많이 지적된 데이터 | 재배포 금지로 간주 |
| S35 | Ribeiro F.M.L., *MAFAULDA – Machinery Fault Database*, UFRJ. https://www02.smt.ufrj.br/~offshore/mfs/page_01.html | 대학 데이터 페이지, B | opened | **라이선스 표기 없음** | 전류 없음(가속도, 마이크, 타코) | 재배포 금지로 간주 |
| S36 | Katser I.D., Kozitsin V.O. (2020). *SKAB – Skoltech Anomaly Benchmark*. Kaggle DOI 10.34740/KAGGLE/DSV/1693952. GitHub waico/SKAB | 데이터/벤치마크, B | opened (GitHub README, Kaggle API, DataCite) | GitHub **GPL-3.0**, Kaggle **AGPL-3.0** | 라이선스 표기 불일치. 데이터에 카피레프트 적용 | 포함 시 라이선스 전문 동봉. 코드 재사용 금지 |
| S37 | Davari N., Veloso B., Ribeiro R.P., Gama J., *MetroPT-3 Dataset*, UCI. DOI 10.24432/C5VW3R + Davari et al. (2021) IEEE DSAA. DOI 10.1109/DSAA53316.2021.9564181 | 데이터 B, 학회 A | opened (UCI, DataCite, Crossref) | **CC BY 4.0** | 샘플링 표기(1 Hz와 0.1 Hz)가 혼재 | 낮음 |
| S38 | Veloso B., Gama J., Ribeiro R., Pereira P. (2022). *MetroPT2: A Benchmark dataset for predictive maintenance*. Zenodo. DOI 10.5281/zenodo.7766691 | 데이터 저장소, B | opened (Zenodo API) | **CC BY 4.0** | 고장 건수 미확인 | 낮음 |
| S39 | 한국지능정보사회진흥원, AI 허브 「데이터 이용정책」. https://aihub.or.kr/intrcn/guid/usagepolicy.do | 공공기관 정책, A | opened | "학습용으로만". 승인 없이 제3자에게 "열람하게 하거나 제공, 양도, 대여, 판매" 금지. 국외 소재 이용과 국외 반출은 별도 합의. 출처 표시 의무 | — | zip 포함 불가 |
| S40 | AI 허브 「기계시설물 고장 예지 센서」 (dataSetSn=238) | 공공데이터, A | opened | **"내국인만 데이터 신청이 가능"**. S39 정책 적용 | 일부 설비는 정상·고장 수집일이 분리돼 있다는 보고(S42) | 사용 금지 권장 |
| S41 | AI 허브 「전력 설비 에너지 패턴 및 고장 분석 센서」 (239), 「제조현장 이송장치의 열화 예지보전 멀티모달 데이터」 (71802) | 공공데이터, A | opened | 내국인만. S39 정책 적용 | — | 사용 금지 권장 |
| S42 | MinSeok-Good, `motor-current-fault-detection` (GitHub) — AI 허브 238 전류 2 kHz·1초 파일, 정상/고장 날짜 교란 보고 | 개인 저장소, C | opened (README) | 라이선스 미확인 | — | 단서로만 |
| S43 | 뉴스핌(2026-03-25), 「기계연, 기계 연구데이터 외부 공개… 데이터 플랫폼 가동」 | 언론, C | opened | 이용조건 미기재 | 유압·펌프 데이터는 언급 없음 | 단서로만 |
| S44 | NASA PCoE Data Set Repository. https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/ | 정부기관, A | opened | "Users employ the data at their own risk…". 기증자 사의 표시 요청 | **유압펌프·프레스·모터전류 데이터 없음** | — |
| S45 | PHM Society Data Repository 목록(2019~2026 챌린지). https://data.phmsociety.org/ | 학회 저장소, B | opened (목록, 2025·2026 페이지) | 개별 조건. 다수가 미표기 | 유압 관련은 2022 rock drill뿐 | — |
| S46 | Niemietz P. (2024). *Fine-blanking Punch Force Measurements processing case hardening steel 16MnCr5*. Harvard Dataverse. DOI 10.7910/DVN/VV55IT | 데이터 저장소(RWTH MTI), B | DataCite 메타데이터 opened | **CC0 1.0** | 공정력 데이터이지 펌프 데이터가 아님 | 낮음 |
| S47 | Niemietz P. (2022). *Series of Time Series representing Fine-blanking Punch Force Strokes with Wear assessment*. Harvard Dataverse. DOI 10.7910/DVN/OYNDZO | 데이터 저장소(RWTH WZL), B | DataCite opened | **CC0 1.0** | 익명화 | 낮음 |
| S48 | Ortjohann L., Becker M. (2024). *Fine Blanking Force Measurements and Barkhausen Noise from Parts Processed with Different Leveller Settings*. Harvard Dataverse. DOI 10.7910/DVN/CEDFTR | 데이터 저장소, B | DataCite opened | **CC0 1.0** | — | 낮음 |
| S49 | Moon J., Niemietz P. (2024), RWTH Publications DOI 10.18154/RWTH-2024-06676; Moon J., Unterberg M.C. (2026), DOI 10.18154/RWTH-2025-05719 | 데이터 저장소, B | DataCite opened | **메타데이터에 라이선스 없음** | — | 인용만 |
| S50 | goodstream 블로그 「인공지능 제조 플랫폼 KAMP 데이터셋 활용」(2025-10-20) | 블로그, C | opened | "원본 데이터셋 재판매 제한"이라 주장하지만 근거 출처 없음 | 근거 불명 | 근거로 쓰지 말 것 |

---

## 3. 세부 내용과 활용 방안

### 3.1 대회 데이터(KAMP 소성가공 예지보전) — 이용조건, 인용, 출처 관리

**공식 메타데이터** (S01 opened, S02 opened)

- 업종 뿌리(소성가공) / 목적 예지보전 / 유형 csv / 알고리즘 LSTM-Autoencoder.
- 사용조건 "콘텐츠 변경허용", 제공기관 스마트제조혁신추진단(수행기관 ㈜인터엑스).
- 등록 2022-12-23 13:13:36, 최종 수정 2025-04-02 15:26:46. 조회수 4,895(2026-10-01).
- 수집방법: "PLC 및 센서를 통해 실시간 데이터를 수신하여 수집된 시간을 기준으로 CSV 파일 형태로 저장". AI0/AI1/AI2라는 이름이 PLC 아날로그 입력 채널명이라는 해석과 맞는다.
- 수집기간(가이드북 10쪽): 정상 2022-07-12, 이상 2022-07-17, 초당 10회.

**센서 위치 표기가 문서마다 다르다** (둘 다 opened)

- KAMP 상세 페이지: "소성가공 설비의 유압펌프에 센서를 부착하여 **모터의 상하부 진동**, 전류와 같은 데이터를 수집".
- 가이드북 7쪽: "프레스 설비 **유압펌프 상/하단에 진동센서**를 설치하고 유압펌프 전력선에 전류 센서를 설치".
- 따라서 보고서에는 "부착 부위(모터 몸체인지 펌프 몸체인지)는 공식 자료 사이에서 일치하지 않음"이라고 쓰고, 해석을 가정별로 나누는 것이 안전하다.

**인용 양식** (S01·S02에서 확인, 문구 그대로)

- 국문: 중소벤처기업부, Korea AI Manufacturing Platform(KAMP), 소성가공 예지보전 AI 데이터셋, 스마트제조혁신추진단(㈜인터엑스), 2022.12.23., www.kamp-ai.kr
- 영문: Ministry of SMEs and Startups., and KAIST(Korea Advanced Institute of Science and Technology). (2022, December 23). Plastic forming predictive maintenance AI dataset. Korea AI Manufacturing Platform(KAMP). https://www.kamp-ai.kr/
- 상세 페이지의 일반 양식: "중소벤처기업부, Korea AI Manufacturing Platform(KAMP), 제조AI데이터셋 제목, 제공기관(수행기관), 데이터셋등록일, KAMP URL".
- 요청 문구: "연구/공식적으로 사용하실 때에는 꼭 아래와 같이 'KAMP 출처(reference)'를 남겨 주시고, 인용시 활용한 내용과 문서 등은 아래 이메일로 보내주시기 바랍니다. (E-mail : kamp@kaist.ac.kr)".
- "바랍니다"는 의무 조항이라기보다 요청이다. 다만 현재 포털 하단 운영기관 연락처가 TIPA·NHN·이노비즈로 바뀌어 있어, KAIST 주소가 실제로 운영되는지는 확인하지 못했다.

**재배포·zip 포함**

- 이용약관(S03)에는 데이터 조항이 없고 "개별서비스에 대한 별도 약관"만 언급한다. 데이터 페이지(S01)의 조건은 "콘텐츠 변경허용"과 출처 표기뿐이다.
- 제출 zip: 대회가 학습 데이터 포함을 요구하므로 주최 측이 허용한 배포로 본다.
- 공개 저장소 게시: 허용한다는 명시 근거가 없다. 저장소를 비공개로 두거나, 데이터는 `.gitignore`로 빼고 내려받기 안내만 두는 것을 권한다. 경쟁팀 S11은 원본을 공개 커밋했고 S12는 "재배포하지 않으므로" 뺐다. 블로그 S50의 "재판매 제한" 주장은 근거가 확인되지 않는다.
- 출처 관리: KAMP zip 안의 파일과 로컬 추출본이 일치한다(직접 확인, MD5).
  - `press_data_normal.csv` = `90bddc57753a51958ae4b985c51a14c9` (1,211,960 B)
  - `outlier_data.csv` = `d1b9c76943fdd48a72dea2698374fb9d` (38,823 B)
  - 압축 안 파일 날짜는 2022-10-14다. README에 이 해시를 적어 두면 재현성 점수에 도움이 된다.

**가이드북 사용 주의** (S02 opened)

- 표지에 "이용자 정보"(회원 ID, 다운로드일, 활용목적)와 "문서 고유 번호와 워터마크"가 있다. zip이나 슬라이드에 PDF나 표지 캡처를 넣지 말 것.
- 그림 출처를 쓰지 말 것.
  - [그림 1]: 네이버 블로그
  - [그림 2]: 네이버 지식백과
  - [그림 5·6]: tistory
  - [그림 7·8]: 타 논문(김현재 외 2021, 이종현 외 2021)
  - [그림 9]: ResearchGate
  - [그림 11]: f-secure 블로그
- [그림 3] 센서 설치 사진은 제공기관 자료로 보이지만, 저작권자가 따로 표시돼 있지 않다. 쓴다면 KAMP 출처를 표기하고 최소한으로만 쓴다.

**두 파일의 형식 차이** (원자료로 직접 확인, 읽기 전용)

| 항목 | 정상 파일 | 이상 파일 |
|---|---|---|
| AI2_Current 값 중 1.19209 정수배 비율(허용오차 1e-3) | 0.18% | **99.67%** |
| AI2_Current 고유값 수 | 19,934 / 20,000 | **340** / 600 (최소 간격 1.19209) |
| 진동 소수 자릿수 | 대부분 6자리 (AI0 17,958/20,000행) | 대부분 8~9자리, 전류에는 14~15자리 부동소수 흔적 60행 |
| 버스트 안 표본 간격 중앙값 | 0.1000 s | 0.1000 s |
| 전류 50샘플 버스트의 주파수 피크 중앙값 | **0.596 Hz** (IQR 0.596–0.605; 40샘플 이상 버스트 276개) | 0.200 Hz (8개 버스트) |

- 해석: 두 파일이 서로 다른 내보내기·처리 경로를 거쳤을 가능성이 크다.
  - 1.19209 = 10/2²³ × 10⁶이므로, 24비트 ADC LSB를 배율한 값이라는 경쟁팀 가설(S09 PR #7)과 수치는 맞는다. 하지만 가설일 뿐이다.
  - 정상 전류가 깨끗한 0.6 Hz 사인파라는 점은 60 Hz 계열 교류를 10 Hz로 그대로 샘플링해 생긴 에일리어싱과 맞는다.
  - 계산상 정확히 60 Hz를 10.000 Hz로 샘플링하면 별칭 주파수는 0 Hz다. 0.6 Hz가 나오려면 구동 주파수가 약 59.4/60.6 Hz(인버터 구동)이거나, 실제 샘플 클럭이 타임스탬프 클럭과 약 1% 다르거나 둘 중 하나여야 한다. 둘 다 미확인 가설이다.
- 활용: 3.5절 E1(형식 통일과 형식 탐침 분류기). 1절 요약 3번과 연결된다.

### 3.2 같은 데이터를 쓴 공개 작업물 — 비교점

**(a) 가이드북 기준선** (S02 opened, 코드에서 직접 확인)

- 전처리: 모든 채널에 `abs()`를 적용하고 MinMaxScaler를 쓴다.
- 분할: 정상 앞 15,000행이 학습, 나머지 5,000행이 평가다.
- 윈도우: 20행, stride 1. **버스트 사이 공백을 가로지르는 윈도우도 그대로 만든다.** 라벨은 index+120 위치 값이다.
- 임곗값: 정상 880윈도우와 **이상 윈도우 앞쪽 300개**(단일 사건)로 precision=recall 지점을 고른다.
- 평가: 정상 4,000윈도우 + 이상 180윈도우(같은 사건의 뒷부분). 양성 비율 4.3%.
- 모델: LSTM 64-32-32-64, epochs 800, batch 128, EarlyStopping patience 120.
- 결과: "정확도 97.51%, F1-Score 74.76%".
- 해석: 겹침 윈도우 단위 점수이고, 같은 사건 안에서 임곗값을 정했다. 따라서 **사건 단위 탐지력이나 다른 날짜로 일반화되는 성능을 뜻하지 않는다.** 우리 보고서에서 "기준선 재현 → 같은 지표의 한계 → 사건 단위·누수 차단 지표"로 이어지는 비교에 쓰기 좋다.
- S08(2023 수업 저장소)은 이 코드를 그대로 재현했다(파일명 `press_data_outlier.csv`만 다름).

**(b) 2026 경쟁팀 공개 저장소** (S09~S12, opened. 공개 PR에 적힌 주장이며 대부분 미검증)

- S09 PR #1 (2026-09-26)
  - 정상 버스트 599개, 이상 버스트 21개.
  - 정상 전류가 영교차·FFT 기준 0.6 Hz이므로 "60 Hz→10 Hz 에일리어싱"이라고 판단.
  - 이상 파일 전류의 99.67%가 1.19209 배수(우리 확인과 같음). DC 단독 AUC 0.9443.
  - 이상 세그먼트 3·19·20을 라벨 노이즈로 의심.
  - 정상 운전상태를 K-means 2개(고부하 43.18%, 저부하 56.82%)로 나눔.
- S09 PR #7: 형식 피처 AUC가 전처리 전 1.000에서 후 0.566~0.637로 떨어짐. 진폭 피처 AUC는 0.92~0.997.
- S09 PR #11
  - 모델 9종을 사전 비교했더니 실제 이상에서 상위 6종이 AUC 1.000.
  - 오경보는 고부하에 집중(CNN 고부하 0.044 vs 저부하 0.003).
  - 합성 이상 주입(스파이크·진폭·상하부 반대 흔들림·전류 불규칙, 강도 4단계)에서 탐지율은 0.10~0.30.
- S09 PR #20: "진동센서가 모터 몸체에만 있다"는 단정을 철회하고 "부착 부위 미확정"으로 고침. 우리가 3.1에서 본 불일치와 같은 결론이다.
- S12: `01_press_acquisition_grid_leak.csv` 파일명으로 보아 같은 격자 누수를 파악한 것으로 보인다(내용 미열람).
- 시사점
  - 형식 누수, 0.6 Hz 에일리어싱, 실제 이상이 쉽게 갈린다는 점(AUC≈1), 합성 이상 주입은 **이미 여러 팀이 공유하는 출발점**이다. 우리 차별점은 다른 곳에서 나와야 한다. 예를 들어 사건 단위 지표, 외부 공개 데이터로 효과크기를 보정한 합성 주입(E3), 운전조건 FP 스트레스 테스트(E4), 형식 불변성 증명(E1), 확률 보정.
  - 이 저장소들은 라이선스가 없다(모든 권리 유보). 코드·문장을 가져오지 말고, 보고서에 인용하지도 말 것. 우리 수치는 우리 코드로 재계산한다.

**(c) 학술 문헌**

- KCI·DBpia·ScienceON 검색 결과에서 이 데이터셋을 쓴 논문은 나오지 않았다(search-only).
- 창원대 두 편(DBpia NODE11039181, NODE10754725)은 데이터셋 이름이 명시되지 않았다. 한 편은 데이터 등록일(2022-12)보다 먼저 나왔다(2021).
- RISS·Google Scholar 전수 확인은 못 했다(5절).

### 3.3 데이터셋 카드

각 카드 항목: 소유·URL/DOI · 규모 · 센서·샘플링 · 고장·라벨 · 독립 단위/에피소드 · 라이선스 · zip 포함 · 출처표시 · 상업/NC · 활용 제안 · 부적합 이유.

#### D0. 대회 데이터 — KAMP 「소성가공 예지보전 AI 데이터셋」 (S01, S02)

- **소유·URL**: 중소벤처기업부·KAMP. 제공 스마트제조혁신추진단(수행 ㈜인터엑스). https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48
- **규모**: 정상 20,000행(1,211,960 B), 이상 600행(38,823 B). MD5는 3.1절.
- **센서·샘플링**: AI0_Vibration(상부), AI1_Vibration(하부), AI2_Current. 10 Hz. 최대 50샘플 버스트. PLC로 수집.
- **고장·라벨**: Equipment_state 0/1. 고장 유형 라벨은 없다(가이드북은 기어 마모를 일반론으로만 언급).
- **독립 단위/에피소드**: 설비 1대. 정상 1세션(2022-07-12 00:00–01:17), 이상 1회(2022-07-17, 버스트 21개).
- **라이선스**: KAMP 사용조건 "콘텐츠 변경허용"(CC 계열 아님). 연구·공식 사용 시 출처 표기, 활용 문서를 kamp@kaist.ac.kr로 보내 달라는 요청.
- **zip**: 대회 요구에 따라 포함. 공개 저장소 게시는 피한다.
- **상업/NC**: 명시 없음.
- **활용**: 학습·평가 본체. 형식 통일(E1)이 먼저다.
- **부적합 이유(한계)**: 단일 사건, 날짜·시간 교란, 파일 형식 차이, 센서 위치 표기 불일치.

#### D1. UCI/ZeMA Hydraulic test rig (S14, S17; 논문 S15, S16, S18)

- **소유·DOI**: ZeMA gGmbH(독일 자르브뤼켄) / Helwig·Pignanelli·Schütze. UCI id 447, DOI 10.24432/C5CW21. Zenodo 미러 10.5281/zenodo.1323611.
- **규모**: 2,205사이클 × 60초, 17센서, 압축 73.1 MB, 결측 없음(UCI 표기).
- **센서·샘플링**
  - PS1–6 압력 100 Hz
  - **EPS1 모터 전력 100 Hz**
  - FS1–2 유량 10 Hz
  - TS1–4 온도 1 Hz
  - **VS1 진동(mm/s) 1 Hz**
  - CE·CP·SE 1 Hz
  - 인스턴스당 속성 수는 8×60 + 2×600 + 7×6000 = 43,680으로 UCI 센서 표와 맞는다.
- **고장·라벨**
  - 냉각기 3/20/100%
  - 밸브 100/90/80/73%
  - **내부 펌프 누설 0/1/2**
  - 어큐뮬레이터 130/115/100/90 bar
  - stable flag
- **독립 단위**: 시험 리그 1대. 4개 부품 상태를 정량적으로 조합해 바꿨다(opened).
- **라이선스**: CC BY 4.0. https://creativecommons.org/licenses/by/4.0/
- **zip**: 가능. 출처 표기와 변경사항(예: 10 Hz 다운샘플, 부분집합) 명시 조건.
- **NC**: 없음.
- **활용**: E3(누설 단계별 EPS1·VS1 효과크기로 합성 고장 크기 보정), E4(밸브·냉각기·어큐뮬레이터 변화도 전력을 바꾸는지로 "전류 이상의 비펌프 원인" 정량화), E7(일반화 시연).
- **부적합 이유**: 실험실 리그이고 60초 고정 부하 사이클이다. VS1이 1 Hz 속도값이라 우리 10 Hz 원파형 진동과 다르다. 펌프 형식이 우리와 같은지 확인하지 못했다. 전류가 아니라 **전력**이다.

#### D2. NLN-EMP 원심펌프 모터전류·진동 (S30)

- **소유·DOI**: Univ. of Twente / Royal Netherlands Navy(Fieldlab Techport). 4TU DOI 10.4121/2b61183e-c14f-4131-829b-cc4822c369d0.v4. 논문 Data in Brief 52:109987.
- **규모**: 7z 약 20.8 GB, CSV.
- **설비**: 모터 2대(11 kW@1470 rpm 4극, 22 kW@2950 rpm 2극), 인버터 구동 원심펌프 2대. Motor 2는 정격 50/75/100% 속도, Motor 4는 70% 속도.
- **센서·샘플링**
  - 진동(가속도) 20 kHz: **5분마다 60초**
  - 3상 전류·전압 20 kHz: **2분마다 15초**
  - 2차 Butterworth 대역통과 1 Hz–10 kHz(본문상 NI USB-4432 진동 측정 설정으로 읽힘)
- **고장**: 베어링, loose foot, 임펠러 손상, 고정자 권선 단락, 회전자 바 파손, soft foot, 정렬불량, 불평형, 커플링 열화, **캐비테이션**, 휜 축. 대부분 여러 심각도.
- **독립 단위**: 설비 2세트, 여러 속도.
- **라이선스**: 데이터 **CC0 1.0** (4TU, DataCite opened). 논문 CC BY.
- **zip**: 가능(부분집합 권장). **출처표시**: 법적 의무는 없지만 권장.
- **NC**: 없음.
- **활용**
  - E2: 앤티에일리어싱 없이 10 Hz로 솎아 50샘플 버스트로 만든 뒤, 별칭 주파수·RMS·DC가 속도와 고장에 어떻게 반응하는지 본다.
  - E4: 50/75/100% 속도 변화로 정상 FP를 시험한다.
  - 현장 적용: 버스트 수집 주기 설계 근거로 쓴다.
- **부적합 이유**: 원심펌프라 기어펌프 맥동과 다르다. 우리 DAQ의 앤티에일리어싱 필터와 PLC 평균 처리 여부를 모르니 솎기 재현이 정확하지 않을 수 있다. 용량이 크다.

#### D3. KAIST 회전기계 진동·음향·온도·모터전류 (S31)

- **소유·DOI**: KAIST(KAIST 연구정보 시스템 pure.kaist.ac.kr에 등재). Mendeley 4개 DOI(10.17632/ztmf3m7h5x.6 외 3). 논문 Data in Brief 48:109049.
- **규모·센서**
  - (i) 부하 가변: 가속도 4(PCB352C34), 마이크 1(51.2 kHz), 열전대 2, CT 3. 진동·온도·전류 **25.6 kHz**. 정상 120초, 고장 60초. 부하 0/2/4 Nm.
  - (ii) 속도 가변: Siemens 3 HP 4극 유도전동기(380 V, 60 Hz, 1770 rpm). 진동 25.6 kHz, **전류 100 kHz**. 정속 600초, **가변속 680–2460 rpm 2,100초**. 모두 Europe PMC 본문에서 opened.
- **고장**: 내륜·외륜, 축 정렬불량, 로터 불평형(심각도별).
- **독립 단위**: 리그 2종.
- **라이선스**: 데이터·논문 모두 **CC BY 4.0**.
- **zip**: 가능(출처·변경 표기). **NC**: 없음.
- **활용**: E4(부하·속도 변화에 따른 정상 FP와 "고장 대 운전변화" 민감도 비율), E2(60 Hz 직입 전류를 10 Hz로 샘플링하면 별칭이 DC 쪽으로 간다는 것을 재현해 우리 0.6 Hz와 대비).
- **부적합 이유**: 펌프가 아니다. 실험실 리그다.

#### D4. Chen et al. 2026 3상 유도전동기 가변조건 (S33)

- **소유·DOI**: Chen·Liu·Li·Zou·He·Zhou(저자 소속은 확인 못 함). Mendeley 10.17632/6s3dggj9mw.1. 논문은 arXiv:2601.02278(프리프린트).
- **센서·샘플링**: 8채널 동기 12.8 kHz(key-phase, 3축 진동, 3상 전류, 토크). 정상상태와 **과도상태**.
- **고장**: 불평형, 고정자 단락, 베어링, 기계-전기 복합고장(심각도별).
- **라이선스**: **CC BY 4.0**. **zip**: 가능. **NC**: 없음.
- **활용**: E4. 과도 구간이 정상 운전변화로 오경보를 부르는 양상을 정량화한다.
- **부적합 이유**: 심사 전 프리프린트다. 펌프가 아니다.

#### D5. Paderborn KAt 베어링(모터 전류) (S32)

- **소유**: Paderborn Univ. KAt.
- **규모**: 베어링 상태 32종(건전 6, 인공 손상 12, 가속수명 실손상 14). 운전조건 4종. 설정당 4초 측정 20회.
- **센서**: 모터 상전류와 진동 **64 kHz**(논문 PDF opened). 속도·토크·반경력·온도는 더 낮은 샘플링.
- **라이선스**: **CC BY-NC 4.0**. 인용: "Christian Lessmeier et al., KAt-DataCenter" + 기관·링크. 상업 이용은 저자 문의.
- **zip**: **넣지 않음** 권장(NC). 내부 방법 검증용으로만, 그것도 불필요하면 생략한다.
- **활용**: 전류 기반 진단 문헌 근거로 인용하는 정도. 논문 요지(opened): 모터전류로 베어링 손상을 식별할 수 있지만 분류 정확도는 진동보다 낮다.
- **부적합 이유**: NC 조건, 베어링 중심, 64 kHz.

#### D6. SKAB (S36)

- **소유**: Skoltech(Katser, Kozitsin). GitHub waico/SKAB. Kaggle DOI 10.34740/KAGGLE/DSV/1693952.
- **규모**: CSV 35개(이상 실험 34 + anomaly-free 1). 약 5.3 MB(Kaggle API).
- **센서**: Accelerometer1RMS, Accelerometer2RMS(g), Current(A), Pressure, Temperature, Thermocouple, Voltage, RateRMS. 타임스탬프 1초 해상도.
- **이상**: 밸브1·밸브2 폐쇄, 누수·유체 추가, **로터 불평형의 5가지 개시 형태(급변·선형·계단·디랙·지수)**, 물 배출에 따른 캐비테이션, 2상 유입 캐비테이션, 고온수.
- **라벨**: anomaly, changepoint.
- **라이선스**: GitHub **GPL-3.0**, Kaggle **AGPL-3.0**(불일치).
- **zip**: 가능은 하지만 라이선스 전문을 동봉하고 원형을 유지해야 하며, 코드를 섞으면 안 된다. 다운로드 스크립트로 대체하는 것을 권장.
- **NC**: 없음(카피레프트).
- **활용**: E5(사건 단위 지표, 지속성 규칙 k-of-n, 개시 형태별 탐지지연), E8(사건별 교차 확률보정).
  - 참고: README 리더보드에서 LSTM-AE는 F1 0.74인데 **FAR 29.96%**, MAR 25.92%다(opened). F1이 비슷해도 오경보율은 높을 수 있다는 근거다.
- **부적합 이유**: 물 순환 펌프 리그다. 1 Hz RMS라 원파형이 없다. 라이선스 해석이 복잡하다.

#### D7. MetroPT-3 / MetroPT2 (S37, S38)

- **소유**: 포르투갈 Porto 도시철도 운영사와의 XPM(설명가능 예지보전) 프로젝트(저자 Davari·Veloso·Ribeiro·Gama 등. 소속기관은 확인 못 함).
- **MetroPT-3**
  - UCI DOI 10.24432/C5VW3R.
  - 1,516,948행. 아날로그 7개(TP2, TP3, H1, DV_pressure, Reservoirs, **Motor_current**, Oil_temperature), 디지털 8개.
  - **정비기록으로 문서화된 공기누설 고장 4건**(2020).
- **MetroPT2**: Zenodo, 2022-04-28~07-28, 7,116,940행, 16신호 + GPS, 약 2.8 GB.
- **라이선스**: 둘 다 **CC BY 4.0**. **zip**: 가능(용량상 일부만). **NC**: 없음.
- **활용**: E5(실제 고장 여러 건에서 경보 선행시간과 시간당 오경보의 교환관계, 압축기 듀티 사이클이라는 정상 운전변화). 현장 적용 시나리오(정비기록과 경보의 대응)의 예로 쓴다.
- **부적합 이유**: 공기압축기다. 샘플링 표기가 혼재한다(UCI 페이지에 1 Hz와 0.1 Hz가 모두 보임, 확인 필요).

#### D8. 항공 피스톤펌프 다중모드 고장 (S19)

- **소유**: Wang·Ma·Fu(저자 소속은 확인 못 함). Mendeley 10.17632/xw8gjjk9km.1.
- **설비**: 9피스톤 사판식 정압 가변용량 항공연료 피스톤펌프. 시험 조건 22개(속도 50–100%, 압력·유량 스캔).
- **센서**: 압력 100–2000 Hz, 유량 100 Hz, **진동 3축 1 kHz**, 토크·속도 10 Hz, 온도.
- **고장**: 서보피스톤 마모, 조절밸브 마모, 사판 베어링부시 마모. 사포 P400으로 균일 마모 흔적을 만들었다.
- **규모**: 시계열 11개 × 22열.
- **라이선스**: **데이터 CC BY 4.0**, 논문 CC BY-NC 4.0.
- **zip**: 데이터는 가능. 논문 그림은 NC.
- **활용**: 용적형 펌프에서 "운전조건 스캔(압력·유량) 대 마모" 효과크기의 참고값. 토크 10 Hz 채널은 우리 10 Hz 부하 지표의 참고가 된다.
- **부적합 이유**: 항공 연료펌프이고 시뮬레이션 마모다. 전류가 없다.

#### D9. 기어펌프를 부하로 쓴 로터-축 리그 (S22)

- **소유**: Poznań Univ. of Technology. Mendeley 10.17632/cbpr9fvvwb.2 (v2, 2026-09-01).
- **센서**: 가속도 3, 24비트, **11 kHz**, 대역 7 Hz–4 kHz.
- **조건**: 정렬불량 0–1.0 mm 5단계. **유압 기어펌프 스로틀로 부하 0–4.0 MPa**.
- **라이선스**: **CC BY 4.0**. **zip**: 가능.
- **활용**: 기어펌프 토출압(부하)이 바뀌면 진동이 얼마나 변하는지로 정상 운전변화의 폭을 정량화한다(E4 보조).
- **부적합 이유**: 고장 대상이 축 정렬이지 펌프가 아니다. 전류가 없다.

#### D10. Bosch Hydraulic EoL Testing (S20)

- 유압펌프 출하시험 사이클. 9센서(z-정규화·익명), **100 Hz**. 상태 라벨은 정수이고 의미 비공개. 세대 2, 제어방식 3. 저장소 약 900 MB.
- **라이선스**: README상 **CC BY 4.0**.
- **활용**: 다단계 시험 사이클을 분할하는 방법(운전 단계 인식) 참고.
- **부적합 이유**: 고장 라벨이 없고 단위도 없다.

#### D11. PHM 2022 hydraulic rock drill (S21)

- Epiroc 유압 착암기. 3곳 압력 50 kHz(정규화). 11클래스(정상 1 + 고장 10).
- 학습은 5개 configuration("individual")에서, 시험과 검증은 다른 individual에서 한다. individual마다 정상 기준 사이클이 함께 제공된다.
- **데이터 라이선스**: 명시 없음. 논문은 CC BY 3.0 US.
- **활용**: 데이터는 쓰지 않고 **논문의 개념만 인용**한다. "개체 차이가 고장 차이를 가릴 수 있어 같은 개체의 정상 기준이 보정에 필요할 수 있다"(opened 원문 취지). 우리 정상(화요일 00시)과 이상(일요일 10시) 세션 차이 문제의 근거가 된다(E6).
- **부적합 이유**: 라이선스 불명. 압력만 있다.

#### D12. 실제 유압프레스 Hercik & Svoboda 2023 (S23)

- **설비**: Brose CZ 차체 판재 프레스(높이 7.5 m 이상). 비동기 모터 132 kW·75 kW와 축방향 피스톤펌프(Rexroth, Bucher). 실린더 2개.
- **수집**: PLC 5–10 ms 주기(실측 약 12±2 ms) → 125 Hz로 재표본화. 레코드당 51값, 하루 평균 655만 행.
- **센서 군**: 가압력, 기울기, 절단 완충, 램 이동, **펌프 베어링(펌프 플랜지 가속도)**, 냉각, 제어유, **에너지(메인펌프 1–3 전압·전류)**.
- **공개분**: 하루치(raw 1.47 GB, resampled 1.98 GB, 이상 타임스탬프, 운전상태)와 학습·시험 CSV.
- **라이선스**: "without restrictions for other researchers"라고만 했고 명시 라이선스는 없다. 나머지는 NDA.
- **zip**: **넣지 않음.**
- **활용**: 정상 프레스 사이클에서 펌프 모터 전류와 펌프 진동이 얼마나 변동하는지에 대한 서술 근거(FP 원인 설명). 연구 설계상 반례로도 쓸 수 있다: 10초 윈도우 2,255개(이상 386)를 **무작위 80/20**으로 나눴으므로 인접 윈도우 누수 가능성이 있다.
- **부적합 이유**: 라이선스 불명, 영업비밀 출처, 용량.

#### D13. KAMP 「소성가공 자원최적화 AI 데이터셋」 (S07, 로컬 가이드북 opened)

- **소유**: KAIST(수행 UNIST/㈜리쉐니에). 등록 2022-12-23. 사용조건 "콘텐츠 변경 허용".
- **내용**: 자동차 차체 단조·연속 프레스 라인의 **프레스 1–4호 유압펌프 모터 전류 RMS**와 로봇 2대 전류.
  - 기간 2022-07-17~08-31(1.5개월). 프레스별 59,032~65,068행. 행 수로 보면 약 1분 간격으로 추정되지만 미확인.
  - 공정 데이터: 품목번호, 주·야, 생산수량 등 55,007행.
  - 무선 전류센서, 엣지, OPC-UA. 총 8.15 MB.
- **zip**: 가능. 같은 KAMP 조건이고 외부데이터로 명시한다.
- **활용**: E9. 프레스 유압펌프 모터 전류가 품목·주야·비가동에 따라 바뀌는 폭(정상 운전변화의 분포)을 보여 주는 국내 현장 근거로, 상태조건부 임계값과 FP 분석의 서술 근거가 된다.
- **부적합 이유**: RMS 저속 데이터이고 파인블랭킹이 아니다. 진동이 없고 고장 라벨도 없다.

#### D14. KAMP 「회전기계 고장유형 AI 데이터셋」 (S07)

- **소유**: KAIST 이필승 교수. 2021-12-27.
- **설비**: rotor testbed(약 1,500 rpm), Signallink 스마트 진동센서 4개(주파수 범위 672 Hz).
- **수집**: 약 140초. 센서 1 기준 190,218행이므로 약 1.36 kHz로 추산. 센서별 샘플링이 달라 선형보간본을 함께 제공한다.
- **고장**: 정상, 질량 불균형, 지지 불량, 복합.
- **라이선스**: 콘텐츠 변경허용.
- **활용**: 10 Hz로 솎았을 때 불균형·지지불량이 RMS 수준으로 남는지 보여 주는 "10 Hz 한계" 시연(외부데이터로 명시).
- **부적합 이유**: 소형 리그이고 펌프가 아니다.

#### D15. KAMP 「용접 예지보전 AI 데이터셋」 (S07)

- **소유**: 스마트제조혁신추진단(수행 **㈜인터엑스**). 2022-12-23. LSTM-AE.
- **파일**: `normal_data.csv`, `outlier_data.csv`(압축 목록 opened).
- **변수**: DV_R·DA_R·AV_R·AA_R(직류·교류 전압·전류), PM_R(용접속도). 파이프당 5분 주기. 2022-01-17~04-01.
- **활용**: E1 보조. 같은 수행기관의 normal/outlier 파일에서도 소수 자릿수·격자 차이가 보이면, 형식 누수가 "제공 과정의 산물"이라는 우리 주장이 강해진다. 압축을 풀지 않아 아직 확인하지 않았다.
- **부적합 이유**: 다른 설비다. 비교만 한다.

#### D16. KAMP 실증 데이터셋 (S06)

- 진공펌프(HD) 가동(SEQ 108): 반도체 진공펌프 수리·출하 시험. DP_CUR·BP_CUR(펌프 전류), 배기압·온도, BP_SPEED·BP_POWER, 3축 진동. 1초. 289,521,000개, 1.9 GB.
- 프레스성형기(SEQ 89): 150톤 기계식 프레스. 로드셀·각도·메인모터 속도 등 26변수. 1초. 39 MB. 양불 예측용.
- 진동 결함 시뮬레이터(SEQ 45·56): AST 시뮬레이터 1,500 rpm. 정상 + 16종 이상. 샘플 간격으로 보면 약 488 Hz(ICP)와 800 Hz(MEMS).
- **이용조건**: 상세 페이지에 사용조건이 없다. 로그인 후 다운로드. 50종 밖이다.
- **판단**: 쓰려면 주최 측 확인이 먼저다. 우선순위는 낮다.

#### D17. AI 허브 (S39–S41)

- **238 「기계시설물 고장 예지 센서」**
  - 대전광역시 주관, 대전교통공사·한국기계연구원 등. 2020년 구축, 2021-06 갱신.
  - 전동기 2.2–55 kW 12종 용량 범위, 233.3만 개(정상 109.8만 / 고장 123.5만).
  - 진동·전류. 고장 4종(베어링 불량, 회전체 불평형, 축정렬 불량, 벨트 느슨함).
  - 전류 2 kHz·1초 파일(S42, C등급 근거).
- **239**: 펌프·압축기·모터 등 10종 전력품질(전류평균, 역률, 고조파). 원천 7.08억 건.
- **71802**: OHT·AGV 전류 CT1–4, 온도, 미세먼지, 열화상, 4단계 열화 라벨. 2024년.
- **이용조건**(S39 opened)
  - "본 AI데이터는 인공지능 학습모델의 학습용으로만 사용할 수 있습니다."
  - "…승인을 받지 않은 다른 법인, 단체 또는 개인에게 열람하게 하거나 제공, 양도, 대여, 판매하여서는 안됩니다."
  - "국외에 소재하는 법인, 단체 또는 개인이 AI데이터 등을 이용하기 위해서는 … 별도로 합의가 필요합니다."
  - 국외 반출도 같은 조건이다.
  - 출처 표시: "…한국지능정보사회진흥원의 사업결과임을 밝혀야 하며 … 2차적 저작물에도 동일하게".
  - 데이터셋 페이지: "내국인만 데이터 신청이 가능합니다".
- **판단**: 심사위원에게 데이터를 제공하는 zip에 넣을 수 없다. 학습에 쓰면 재현 요건과 충돌한다. **사용하지 않음.**

#### D18. 기타 제외·참고

- **CWRU**(S34): 이용조건 표기가 없다. 진동만 있고 샘플링은 12/48 kHz로 알려져 있다(search-only).
- **MAFAULDA**(S35): 표기 없음. 1,951시퀀스, 50 kHz × 5초. 전류 없음.
- **Kaggle pump_sensor_data**(S26): "Unknown". 52센서 익명, 분 단위. 2018년 고장 7건. 물 펌프.
- **Crompton Greeves**(S28): 합성, 구독.
- **ESPset·원심펌프 장꼬리 데이터**(S29): CC BY 4.0이지만 진동만 있다.
- **NASA PCoE**(S44): 해당 데이터 없음.
- **Maschler 2021**(S25): 비공개.
- **KIMM 기계데이터 플랫폼**(S43): 2026-03 개시, 베어링 열화 데이터 등. 이용조건 미확인.

#### D19. 파인블랭킹 공정 데이터(RWTH Aachen) (S46–S49)

- 펀치력 시계열(공구 내 압전센서).
- S46: 16MnCr5 4 mm, 33,960 stroke, **분당 120 stroke**, 1.45 GB, CC0.
- S47: 4개 시리즈 2,058–3,339 stroke, 마모 평가, 익명화, CC0.
- S48: Feintool XFT 2500 speed와 롤러 레벨러 9개 설정, 설정당 100개 이상 부품, Barkhausen noise, CC0.
- S49: 판두께 대 공정력, 펀치 마모와 전단면 조도. 라이선스는 메타데이터에 없음.
- **활용**: 파인블랭킹이 stroke 단위의 주기 공정이며 stroke 속도·재료·레벨러 설정 같은 **정상 공정 변화**가 공정력을 바꾼다는 도메인 근거(E9). 펌프 신호가 아니므로 학습에는 쓰지 않는다.
- **주의**: 우리 1000톤 설비의 stroke 속도는 모른다. 120 spm은 다른 설비의 한 실험값일 뿐이다.

### 3.4 우선순위와 용도

| 우선 | 데이터 | 주 용도 | zip | 근거 |
|---|---|---|---|---|
| 필수 | KAMP 소성가공 예지보전(D0) | 학습·평가 | 넣음(대회 요구) | S01, S04 |
| 1 | UCI/ZeMA 유압(D1) | 합성 고장 크기 보정, 비펌프 원인 정량화, 일반화 | 넣을 수 있음(부분집합·출처 표기) | CC BY 4.0 |
| 1 | NLN-EMP(D2) | 10 Hz 에일리어싱 재현, 속도변화 FP | 일부만 | CC0 |
| 1 | KAMP 소성가공 자원최적화(D13) | 프레스 유압펌프 전류의 정상 변동 분포 | 넣을 수 있음 | KAMP 조건 |
| 2 | KAIST Jung(D3), Chen(D4) | 부하·속도 변화 FP 스트레스 | 선택 | CC BY 4.0 |
| 2 | SKAB(D6), MetroPT-3(D7) | 사건 단위 지표·지속성 규칙·확률보정 시연 | 스크립트 권장 | GPL/AGPL, CC BY |
| 2 | KAMP 용접 예지보전(D15), 회전기계(D14) | 형식 누수 원인 교차확인, 10 Hz 한계 시연 | 선택 | KAMP 조건 |
| 3(인용만) | Hercik(D12), Jancarczyk(S24), rock drill(D11), RWTH(D19), 항공펌프(D8), 기어펌프 리그(D9) | 도메인 서술·반례 | 넣지 않음 | 각 항목 |
| 제외 | AI 허브, Paderborn, CWRU, MAFAULDA, Kaggle pump, Crompton, KAMP 실증 | — | 넣지 않음 | 라이선스·출처 문제 |

### 3.5 구체 실험 제안

**E1. 형식 불변성 증명** (필수, 루브릭 1·6. 데이터: 대회 데이터 + D15 선택)

- 전처리
  - 모든 채널을 같은 정밀도로 반올림한다(예: 진동 1e-6, 전류는 공통 격자).
  - 정상 전류를 1.19209 격자로 양자화하거나, 두 파일 모두에 ±LSB/2 균일 디더를 넣는다.
- 형식 탐침 분류기
  - 피처: 소수 자릿수, 격자 잔차, 고유값 비율, 버스트 길이.
  - 전처리 전후 AUC를 보고하고, 목표는 약 0.5다. 이 탐침 AUC를 "누수 차단 지표"로 보고서에 넣는다.
- 주 모델의 성능도 전처리 전후로 함께 보고한다.
- D15 압축 안의 두 파일에서 같은 차이가 보이면 "수행기관 처리 과정의 공통 산물"이라는 근거로 쓴다.

**E2. 10 Hz 에일리어싱 재현** (루브릭 1·5. 데이터: D2 일부, D3)

- 절차: 원 전류(20/100 kHz)를 앤티에일리어싱 없이 10 Hz로 솎고, 50샘플(5초) 버스트로 자른다.
- 볼 것
  - 별칭 주파수 = |f − 10·round(f/10)|. 60 Hz 직입이면 0 Hz 근처, 인버터 59.4/60.6 Hz면 0.6 Hz.
  - 버스트 RMS, 최대-최소, DC, 별칭 주파수 안정성이 속도·부하·고장에 어떻게 반응하는지.
- 산출물: 우리 정상 전류 0.596 Hz가 "운전상태(구동 주파수)"를 나타낼 가능성이 있다는 설명, 그리고 별칭 주파수 이탈 피처를 쓸지 말지에 대한 근거.
- 한계: 우리 DAQ 필터를 모른다.

**E3. 합성 고장 크기의 외부 보정** (루브릭 2·5. 데이터: D1, 보조 D2·D8)

- 절차
  - D1에서 다른 부품 상태를 고정하고 내부 누설 0→1→2에 따른 효과크기를 계산한다. 대상은 EPS1(10 Hz로 솎음)의 사이클 평균·표준편차·버스트 RMS와 VS1이고, Cohen's d와 변화율로 낸다.
  - 이 크기의 0.5×, 1×, 2×를 우리 정상 버스트에 주입한다.
- 산출물: 탐지확률 대 주입크기 곡선, 그리고 "최소 검출 변화" 문장.
- 현장 적용: 이 변화량 이상이면 X 버스트 안에 경보를 낸다.

**E4. 정상 운전변화 FP 스트레스 테스트** (루브릭 3. 데이터: D1, D2, D3, D4, D9, 우리 데이터 내부 상태)

- 절차
  - "건전 조건 A"로 학습하고 "건전 조건 B"(속도·부하·밸브 등)에서 FP율을 잰다.
  - 피처마다 (고장 효과크기) ÷ (운전변화 효과크기) 비율, 즉 "특이도 지수"를 계산한다.
- 산출물: 우리 피처 중 운전변화에 민감한 것의 목록, 그리고 상태조건부 임계값의 근거.
- 현장 적용
  - 오경보가 운전 전이·고부하에 집중된다는 설명.
  - D1 근거로 "전류 이상의 대안 원인(밸브·어큐뮬레이터·냉각)" 점검 목록.

**E5. 사건 단위 지표·지속성 규칙 설계** (루브릭 2·4. 데이터: D6, D7)

- 지표: 사건 재현율, 첫 경보 지연, 정상 운전 시간당 오경보(FA/h), NAB식 점수.
- 규칙: k-of-n 버스트 지속성 규칙에 따라 지연과 FA가 어떻게 바뀌는지 본다. D6의 5가지 개시 형태별로도 본다.
- 같은 지표 정의를 우리 단일 사건(21 버스트)에 적용해, 가이드북식 겹침 윈도우 F1과 대비한다.
- 현장 적용
  - 버스트 간격이 1.5–17초라 n=3이면 대략 수십 초 지연이 생긴다. 교대당 허용 오경보 예산과 묶어 경보 정책을 정한다.

**E6. 세션 차이 내성** (루브릭 3·5. 근거 D11 논문)

- 이상 파일에는 같은 날 정상 기준이 없다. 그래서 정상 데이터에 이득·오프셋·정밀도 변화를 모의해 넣고 FP가 유지되는지 시험한다.
- 버스트 내 z-정규화 형상 피처의 견고성도 시험한다.
- 보고서에는 "세션·날짜 교란은 원리상 분리할 수 없음"을 한계로 명시한다.

**E7. 파이프라인 일반화 시연** (루브릭 5. 데이터: D1 또는 D6 중 하나)

- 같은 코드로 버스트화 → 피처 → 모델 → 보정 → 사건 지표를 돌린다.
- 계산량과 zip 용량을 줄이기 위해 하나만 고른다. 라이선스로 보면 D1이 간단하다.

**E8. 확률 해석의 정직성** (루브릭 2·5)

- 우리 데이터: 정상 보류 버스트로 경험적 p값(conformal)을 계산해 "정상 대비 이례성 확률"로 보고한다. 이상 사건이 1개뿐이어서 진짜 사후확률 보정은 할 수 없다.
- D6: 사건별 교차(leave-one-experiment-out) Platt/isotonic 보정을 시연한다.

**E9. 도메인 근거 수집** (루브릭 1·4. 데이터: D13, D19, S23, S24)

- D13: 품목·주야·비가동별 펌프모터 전류 RMS 분포로 정상 변동 폭을 보인다.
- S24 인용: 프레스 진동 스펙트럼이 비생산·무부품·정상생산·가압상승 상태에서 뚜렷이 다르다. 저주파(약 10 Hz 이하) 대역에도 특징 대역이 있다.
- S23 인용: 실제 프레스 HPU가 펌프 플랜지 진동과 펌프 전류를 함께 감시한다.
- 위 근거로 "운전상태 피처 + 상태조건부 경보"를 정당화한다.

### 3.6 zip과 보고서에 넣을 때의 라이선스 체크리스트

1. `DATA_SOURCES.md` 또는 README 절에 데이터셋마다 다음을 적는다: 제목, 저작자, 출처 URL/DOI, 라이선스 이름과 링크, 받은 날짜, **변경사항**(예: "EPS1을 10 Hz로 다운샘플, cycle 0–499만 포함"), 파일 해시.
2. CC BY: 위 1번이 표기 요건을 충족한다. 변경 표시가 필수다.
3. CC0: 표기는 선택이지만 권장한다.
4. GPL/AGPL(SKAB): 넣으려면 라이선스 전문을 동봉하고 데이터를 원형으로 둔다. 우리 코드와 섞지 말고 별도 폴더에 둔다. 가능하면 다운로드 스크립트와 해시만 넣는다.
5. KAMP: 국·영문 인용을 README와 보고서 참고문헌에 넣는다. 가이드북 PDF·표지·제3자 그림은 넣지 않는다. 공개 저장소에는 원본을 올리지 않는다.
6. NC(Paderborn), 라이선스 불명(CWRU, MAFAULDA, rock drill, Hercik, Kaggle pump), AI 허브는 **zip에 넣지 않는다.**
7. 대회 과제문의 외부데이터 요건에 맞춰 보고서에 "사용 이유·방법·출처"를 표로 넣는다. 학습에 쓰지 않고 검증·보정에만 썼다는 점도 명시한다.
8. 애매하면 문의처(이노비즈 sjkim@innobiz.or.kr, yjkim@innobiz.or.kr)에 "공개 CC BY/CC0 데이터를 검증용으로 zip에 포함해도 되는지"를 묻는다. 공고상 문의처다.

---

## 4. 위험·한계·반론

- **도메인 차이**
  - 공개 데이터 대부분이 원심펌프·전동기 리그·실험실이다. 우리는 1000톤 파인블랭킹 프레스의 유압펌프(가이드북은 기어 마모를 말하지만 형식은 미확정)이고 현장 데이터다.
  - 효과크기를 그대로 옮기면 오해를 부른다. "크기의 범위 설정"용으로만 쓰고 결론을 이것에 기대지 않는다.
- **샘플링 재현의 불확실성**
  - 우리 DAQ의 앤티에일리어싱, PLC 평균, 클럭을 모른다. 정상과 이상 파일의 처리 경로도 다르다. 솎기 재현(E2)은 가설 검증 도구일 뿐이다.
- **심사 관점의 반론**
  - 외부 데이터가 많으면 "주어진 데이터 이해"보다 산만해 보일 수 있다. 1~2개(D1과 D2 또는 D13)로 좁히고 각각 질문 하나에 답하게 하는 편이 낫다.
  - zip 용량 상한은 확인하지 못했다.
- **라이선스 해석 위험**
  - NC: 상금이 걸린 대회가 "비상업"인지 불명확하다.
  - SKAB: 데이터에 GPL/AGPL을 적용한 범위가 모호하다.
  - KAMP: 공개 재배포 조항이 없다.
  - Hercik: "without restrictions"는 라이선스가 아니다.
- **경쟁팀 공개 결과와의 유사성**
  - 형식 누수, 0.6 Hz, 합성 이상 주입은 이미 공개돼 있다. 우리 보고서가 비슷해 보일 수 있으니 독립 검증 수치와 우리만의 축(E3·E4·E5)으로 차별화한다.
  - 경쟁팀 코드는 라이선스가 없으므로 보지 않고 다시 구현한다. 참고하더라도 인용하지 않는다.
- **반례 근거**: SKAB 리더보드에서 LSTM-AE(F1 0.74)의 FAR은 약 30%다. "F1이 높으면 오경보도 적다"는 가정은 성립하지 않는다. 이것은 우리 주장을 뒷받침하지만 다른 데이터라는 점도 함께 밝힌다.
- **센서 위치·펌프 형식 불확실성**: 공식 자료끼리 표기가 다르다(모터 대 펌프 상·하단). 외부 데이터의 고장 메커니즘(예: 기어 맞물림, 캐비테이션)을 우리 신호에 바로 대응시키지 않는다.
- **AI 허브 유혹**: 국내 전동기 진동·전류 대용량 데이터지만 이용정책상 심사위원 제공·재현과 충돌한다. 쓰지 않는다.

---

## 5. 아직 확인 못 한 것

1. KAMP가 제출 zip 외 공개 재배포를 허용하는지. 이용약관과 데이터 페이지에 조항이 없다. kamp@kaist.ac.kr이 현재 운영되는지도 모른다.
2. 대회 과제안내(로그인 필요)와 첨부 HWP의 외부데이터·zip 용량·코드 공개 관련 세부 문구.
3. 진동센서 부착 부위(모터 몸체인지 펌프 몸체인지)와 펌프 형식, 그리고 0.6 Hz 별칭의 원인(인버터 구동 주파수인지 클럭 차이인지).
4. KAMP 「용접 예지보전」 normal/outlier 파일에도 같은 형식 차이가 있는지. 압축을 풀지 않아 미확인이다(E1에서 확인 가능).
5. 「소성가공 자원최적화」 전류 RMS의 정확한 샘플링 간격(행 수로 1분 정도로 추정).
6. AI 허브 238 진동의 샘플링(전류 2 kHz는 C등급 근거). 다만 사용하지 않으므로 우선순위가 낮다.
7. Hercik 공개분의 `README_DATA.md` 내용과 실제 이용조건.
8. PHM 2022 rock drill 데이터 자체의 라이선스(챌린지 페이지에 없음).
9. MetroPT-3의 실제 샘플링 주기(UCI 표기 혼재).
10. Paderborn 데이터의 Zenodo 미러 존재 여부(search-only 언급만 있음).
11. KCI·DBpia·RISS·Google Scholar 전수 검색(WebSearch 한도 소진). 「소성가공 예지보전」을 쓴 학위논문·학술대회 발표가 있을 수 있다.
12. 공개 "stamping/servo/hydraulic press" 진동·전류 데이터 추가 탐색. Zenodo와 DataCite 키워드 검색에서는 RWTH 파인블랭킹(공정력)만 나왔다.
13. S18 논문번호(Crossref에 article number 없음)와 S15·S16 본문 내용(메타데이터만 확인).

---

## 부록 — 직접 계산한 수치의 재현 방법(요약)

- 형식 차이: 두 CSV를 읽어 `abs(v/1.19209 - round(v/1.19209)) < 1e-3`인 비율을 채널별로 계산하고, 원문 문자열의 소수점 이하 자릿수 분포를 센다.
- 버스트 분리: 연속 타임스탬프 간격이 0.15초를 넘으면 새 버스트로 본다. 정상 599개, 이상 21개.
- 전류 주파수: 길이 40 이상인 버스트에서 평균을 빼고 Hann 창을 씌운 뒤 1024점 rFFT(Δt = 0.1 s)를 하고, DC를 뺀 최대 피크를 고른다.
- 해시: macOS `md5`. KAMP 압축 안 파일과 추출본을 비교했다.
