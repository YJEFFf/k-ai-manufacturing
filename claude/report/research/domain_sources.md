---
title: 도메인 근거 조사 — 파인블랭킹 프레스 유압펌프 예지보전(현직자 수준 근거)
created: 2026-10-04
updated: 2026-10-04
tags: [contest/k-ai-manufacturing]
source: 제조사 카탈로그·기술자료(Feintool, ANDRITZ Schuler, Bosch Rexroth, Casappa, Parker, Shell, SKF), ISO 표준 미리보기(iTeh 샘플), 법령(국가법령정보센터), 전력거래소 규칙, 학술논문(MDPI·IEEE·Elsevier 서지 및 OpenAlex 초록), 업계지(The Fabricator, Machinery Lubrication), 웹 검색 — 2026-10-04 열람
status: seed
---

# 도메인 근거 조사 — 파인블랭킹 프레스 유압펌프

관련 노트: [[제조데이터 경진대회 MOC]] · [[peer_and_methods]] · [[organizer_intent]] · 보고서 원고 `report/final_v5.md`

## 표기 규칙

- **1차**: 원문(제조사 PDF, 표준 본문 미리보기, 법령 PDF, 논문 본문 또는 출판사·OpenAlex 초록)을 직접 열어 해당 문장을 확인함
- **2차**: 다른 문서가 옮겨 적은 내용(예: 표준 표를 재인용한 컨설팅사 백서), 검색 결과 요약, 교육용 슬라이드를 거쳐 확인함. 원문 확인 전에는 숫자를 단정하지 않는다
- **추정**: 위 사실들을 바탕으로 한 이 문서 작성자의 계산이나 해석. 보고서에 넣을 때는 "추정" 또는 "가설"이라고 적는다
- **확인 못 함**: 찾지 못했거나 출처끼리 수치가 달라 결론을 내지 않은 항목
- 숫자는 출처에 적힌 그대로 옮겼다(단위 포함). 출처가 영어면 뜻만 한국어로 옮겼다

## 0. 핵심 발견 요약 (보고서 작성자용)

1. 파인블랭킹 프레스는 V링력·역압(카운터력)·블랭킹력을 각각 유압 실린더로 따로 거는 3중 동작 유압 프레스다. 슬라이드는 아래에서 위로 움직이고, 1행정은 고속 접근 → 감속·감지 → 저속 블랭킹 → 고속 복귀로 나뉜다(1차: Kaya & Altan 2007, Shu et al. 2023).
2. 압력원은 모터-펌프가 어큐뮬레이터를 계속 채우다가 설정압에 도달하면 비례밸브로 탱크에 언로딩하는 구조다(1차: Shu et al. 2023). 따라서 펌프 모터 부하는 행정과 충전·언로딩 주기에 따라 수 초 단위로 오르내린다고 추정된다. 10Hz 데이터에서 0.5~2Hz 성분이 공정 주기일 수 있다.
3. 외접 기어펌프의 기어는 보통 9~12개, Rexroth AZPF는 12개다(1차). 마모는 주로 기어 끝면과 측판(플로팅 부싱)에서 생기고 끝면 누설은 틈새의 세제곱에 비례한다(1차: Guo et al. 2020). 그 결과 토출 유량이 줄고 체적효율이 떨어진다.
4. 기어 맞물림 주파수(잇수×회전수)는 수백 Hz다(예: 12잇수×24.5Hz=294Hz, 1차). 10Hz 샘플링으로는 원천적으로 볼 수 없다. 캐비테이션의 kHz 광대역 성분도 마찬가지다. 10Hz 데이터로는 "진폭(에너지)·저주파 변동·채널 간 관계"만 볼 수 있다는 점을 보고서에 한계로 적어야 한다.
5. 냉간 기동: ISO VG 46 광유(Shell Tellus S2 M 46)는 0°C에서 580cSt, 40°C에서 46cSt다(1차). 외삽하면 20°C 약 135cSt, 25°C 약 100cSt다(추정). 한여름(7월) 기동이라면 점도는 Rexroth 권장 상한(100mm²/s) 근처일 뿐 냉간 기동 한계(2000mm²/s)에는 한참 못 미친다. "고점도 흡입 캐비테이션"으로 설명하는 근거는 약하다(추정). 기동 직후의 과도 상태(공기 혼입, 어큐뮬레이터 빈 상태에서 충전)는 다른 설명이 될 수 있다.
6. 진동 위상: 기계가 기초 위에서 흔들리면(rocking) 발·베이스·기초 사이에 180° 위상차가 나타난다. 연성 기초, 체결 풀림, 소프트풋의 전형 서명이다(1차: SKF CM5003, IIT 진동 차트). 다만 이 기준은 1X 성분의 위상(±30° 정확도)이다. 10Hz 원시 샘플의 상관계수 −0.36을 곧바로 rocking의 증거로 쓰면 안 되고 "일치하는 정황"으로만 써야 한다.
7. ISO 20816-1은 진동 값을 비교할 때 "측정량과 단위를 항상 명확히" 하라고 요구한다(1차). 이 데이터처럼 단위를 모르면 ISO 구역(A/B/C/D) 판정은 할 수 없고 기준선 대비 상대 판정만 가능하다.
8. 한국 전력계통 표준주파수는 60Hz, 허용오차는 ±0.2Hz다(1차: 전기사업법 시행규칙 별표3, 2013년판과 2025년판 동일). 샘플링이 정확히 10.000Hz이면 60±0.2Hz 전류의 겉보기 주파수는 0.2Hz를 넘을 수 없다. 관측된 0.60Hz를 앨리어싱으로 설명하려면 실제 샘플 간격이 약 0.0990초 또는 0.1010초여야 한다(약 1% 어긋남, 추정 계산). 이를 검증하지 않으면 0.60Hz가 공정 주기(예: 36spm)일 가능성을 배제할 수 없다.
9. 경보 부담 기준: 운전원 1인당 평균 10분에 1건(시간당 약 6건, 하루 약 150건)이면 "수용 가능성이 매우 높음", 10분에 2건(시간당 약 12건, 하루 약 300건)이면 "최대 관리 가능"이다(2차: ISA-18.2 표를 exida가 재수록. EEMUA 191도 같은 계열). 오경보율은 "시간당 건수"로 환산해 이 기준과 비교하면 설득력이 있다.

---

## 1. 파인블랭킹 프레스 구조·행정·유압 부하

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| 파인블랭킹에서는 V링력(F_R), 역압(counterforce, F_G), 블랭킹력(F_S) 세 힘이 블랭크에 작용한다. F_R과 F_G는 유압 실린더가 건다. 펀치·가이드판·다이 동작을 따로 제어하는 3중 동작(triple-action) 유압 프레스에서 수행한다. 이 힘들은 부품 품질에 큰 영향을 준다 | Kaya, S. & Altan, T. "Blanking developments – Part I", The Fabricator, 2007-07-10. https://www.thefabricator.com/thefabricator/article/bending/blanking-developments---part-i | 1차 | 설비 설명 첫 문단. "유압이 약해지면 클램핑·역압이 부족해져 절단면 품질이 나빠진다"는 가이드북 논리의 공학적 근거 |
| 공정 시작 시 F_R과 F_G를 먼저 걸어 소재를 단단히 클램핑하고, F_S가 블랭킹을 완료한다. 사이클: (A) 공구 열림·소재 이송 → (B) 주 피스톤 작동 → (C) 절단 시작 → (D) 절단 종료 후 유압 해제 → (E) 공구 열림 → (F~H) 스트립 전진·부품/스크랩 배출 | 같은 글(Part I) | 1차 | 1행정 단계 그림의 근거 |
| "파인블랭킹 프레스에서 슬라이드는 항상 아래에서 위로 움직인다. 슬라이드 행정은 고속 닫힘, 접촉, 블랭킹, 고속 복귀로 나뉜다" (글의 참고문헌: F. Birzer, Forming and Blanking 2판, Feintool 1999 / Schuler Metal Forming Handbook) | 같은 글(Part I) | 1차(업계지), 원전(Schuler·Birzer)은 2차 | 단계별 부하 설명 |
| 램 사이클: 하사점(BDC, 공구 완전 열림)에서 설정 공구 간격까지 고속 상승 → b점에서 감속해 감지 동작 → 저속 블랭킹 → 상사점(TDC)에서 블랭킹 완료 후 BDC로 고속 복귀. 블랭킹 속도는 소재에 따라 5~50mm/s | Kaya & Altan, "Blanking developments – Part II", The Fabricator, 2007-08-08. https://www.thefabricator.com/thefabricator/article/bending/blanking-developments---part-ii | 1차 | 블랭킹 구간만 저속·고압이라는 점을 강조 |
| 12,000kN 유압 파인블랭킹 프레스의 압력원 서브시스템은 모터, 펌프(P3, P4), 스위치 카트리지 밸브, 어큐뮬레이터, 압력 형성 카트리지 밸브(비례밸브 제어)로 구성된다. 모터-펌프가 어큐뮬레이터를 계속 채우고, 설정압에 도달하면 비례밸브가 압력 형성 카트리지 밸브를 열어 기름을 탱크로 돌려보낸다(언로딩). 외부로 유량이 필요하면 모터-펌프와 어큐뮬레이터가 함께 고압유를 공급한다 | Shu, Y., Liu, Y., Xu, Z., Zhao, X., Chen, M. "Optimization of Hydraulic Fine Blanking Press Control System Based on System Identification", Processes 11(1):59, 2023. https://doi.org/10.3390/pr11010059 (공개본: https://psecommunity.org/wp-content/plugins/wpor/includes/file/2302/LAPSE-2023.0093-1v1.pdf) | 1차 | "모터→펌프→압력제어/비례밸브→어큐뮬레이터·실린더" 계통도의 직접 근거 |
| 같은 프레스의 서브시스템: 고속(fast) 서브시스템(모터, 펌프 P1, 서보밸브, 전자 방향전환밸브, 고속 실린더), 주 블랭킹 서브시스템(압력보상밸브+서보밸브로 된 속도조절 모듈, 충전밸브, 주 실린더, 언로딩 카트리지 밸브), 역압 펀치 서브시스템, 블랭크 홀더 서브시스템 등 | 같은 논문 2.1.1절 | 1차 | 계통도 보강 |
| 행정 단계: FA(고속 접근) → DT(감지: 감속해 다이 면의 스크랩 유무 확인, 있으면 BDC로 복귀·정지) → BL(블랭킹: 고속 실린더에서 고압·대유량의 주 블랭킹 실린더로 전환, 저속) → FR(고속 복귀). "슬라이드 행정이 증가할수록 전체 파인블랭킹 힘이 증가한다" | 같은 논문 1장·2.1.4절 | 1차 | 단계별 유압 부하 변화: FA·FR은 저압·대유량, BL은 고압·저속, 힘은 BL 구간에서 행정에 따라 증가 |
| 기존 대형 유압 프레스는 고정 고압원으로 부하를 구동해 출력과 부하가 맞지 않아 효율이 낮다. 5단 압력원(어큐뮬레이터 예압 35, 65, 95, 125, 155bar)으로 바꾸자 1사이클당 고압회로 에너지 손실이 34.86% 줄었다. 고속회로는 서보모터로 정용량 펌프를 구동해 중압회로 손실을 50.32% 줄였다 | 같은 논문 1장·2.1.1절 | 1차 | 일반 설비는 "고정압 펌프가 계속 돌며 어큐뮬레이터 충전·언로딩을 반복"한다는 배경 설명 |
| 펌프 모터 부하는 행정 단계(FA/DT/BL/FR)와 어큐뮬레이터 충전·언로딩에 따라 주기적으로 오르내린다 | 위 두 행의 조합 | 추정 | 정상 데이터의 저주파 변동(0.5~2Hz)과 반복 패턴을 "공정 주기" 가설로 제시할 때 사용. 대회 설비의 실제 회로(어큐뮬레이터 유무)는 확인 못 함 |
| Feintool FB one: 최대 100 strokes/min. 직동 유압(FEINdrive)으로 에너지 최대 30% 절감, 작동유량 약 50% 감소("Oxy-Stop"으로 기름 속 공기 비율도 낮춤), 급격한 충격(sudden impact)을 유압 역압으로 감쇠. FEINmonitoring으로 상태감시(condition monitoring) 기반 보전 시점을 예측 | Feintool, "Fineblanking reinvented – Hydraulic fineblanking presses at the highest level – the FB one", 브로슈어(문서코드 FIH D 150 092018, 2023-07 게시). https://www.feintool.com/wp-content/uploads/2023/07/Broschuere_FB_one_A4_EN_WEB.pdf | 1차 | 행정 속도 범위, 제조사도 상태감시를 제품 기능으로 넣는다는 근거, "기름 속 공기"가 관리 대상이라는 근거 |
| Feintool은 파인블랭킹이 최대 200 strokes/min에 이른다고 소개 | Feintool, Fineblanking 기술 페이지. https://www.feintool.com/technologies/fineblanking/ | 1차 | 상한값(고속 서보 기종). 1000톤급 유압기의 일반값으로 쓰면 안 됨 |
| ANDRITZ Schuler HFA plus+ 유압 파인블랭킹 프레스: 3,200~15,500kN, 최대 85 strokes/min. 신형은 서보 제어 펌프 구동을 채택. 전 세계 유압 파인블랭킹 설비 800대 이상 제작 | ANDRITZ 보도자료, 2026-01-22. https://www.andritz.com/newsroom-en/metals/2026-01-22-hfa-fineblanking-group | 1차 | 약 1000톤(≈9,800kN) 설비가 이 등급에 속함. 행정 속도는 "수십 spm, 최대 85~100spm" 범위로 기술. 대회 설비의 실제 spm은 확인 못 함 |
| 60~100spm이면 행정 주기는 0.6~1.0초(1.0~1.7Hz)이고, 10Hz 샘플링에서 1행정당 6~10샘플이다. 36spm이면 0.60Hz다 | 위 행정 속도로 계산 | 추정 | 10Hz 데이터의 나이퀴스트(5Hz) 안에 공정 주기가 들어온다는 점 → 저주파 성분 해석 시 공정 주기 가설을 반드시 검토 |
| Schuler 편 『Metal Forming Handbook』(Springer, 1998)에 파인블랭킹 절이 있다 | https://link.springer.com/book/10.1007/978-3-642-58857-0 | 2차(서지만 확인, 본문 미열람) | 일반 참고문헌으로만 인용 |
| V링력·역압이 블랭킹력의 몇 %인지는 출처마다 다르다(검색 결과에 30~70%, 20%, "V링 최대 50%·카운터홀더 최대 25%" 등이 섞여 있음) | 검색 결과(원문 미확인) | 확인 못 함 | 보고서에 비율 수치를 쓰지 않는다 |
| 1000톤급 10,000kN 유압 파인블랭킹 프레스의 주 유압계통 에너지 분석 논문이 있다 | Xu, Z., Liu, Y., Hua, L., Zhao, X., Guo, W. Energy Conversion and Management 181:143–158, 2019(온라인 2018). https://doi.org/10.1016/j.enconman.2018.12.012 | 2차(서지만 확인) | 동급 설비 연구가 있다는 정도로만 인용 |

## 2. 기어펌프 고장 모드·원인·서명

### 2-1. 사실 표

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| 외접 기어펌프는 베어링 부싱에 지지된 기어 한 쌍, 하우징, 앞·뒤 커버로 구성되고 미끄럼 베어링이 베어링 하중을 받는다. "기어 잇수는 12개이며, 이로써 유량 맥동과 소음 방출을 최소로 한다." 작동압을 부싱 바깥 압력장으로 보내 부싱을 기어 쪽으로 눌러 축방향 틈새를 밀봉하고, 반경방향은 압력에 따라 정해지는 최소 틈새로 밀봉한다 | Bosch Rexroth, "External gear pump High Performance AZPF", 데이터시트 RE 10089/2021-11-24(러시아 대리점 미러). https://boschrexroth-russia.ru/image/catalog/docs/re10089_2021-11-24_AZPF.pdf | 1차 | 펌프 구조 설명. 마모 부위(부싱·측판)와 연결 |
| "고성능·고압용 직선치 기어펌프는 보통 잇수가 9~12개" | US10024317B2(Danfoss Power Solutions, 발명자 M. A. Morselli, 우선일 2012-12-18, 공개 2018-07-17). https://patents.google.com/patent/US10024317B2/en | 1차(특허 본문) | 잇수 범위 근거. 대회 펌프의 실제 잇수는 확인 못 함 |
| 마모 부위: ① 기어 끝면과 플로팅 측판, ② 이끝과 케이싱 내면, ③ 치면. 끝면 누설량은 끝면 틈새 s의 세제곱에 비례. 고압에서 플로팅 부싱이 기울어 유막이 깨지면 끝면 마모가 빨라지고, 오염 입자도 끝면 마모를 가속한다. "토출 유량 감소가 끝면 누설의 가장 직접적인 결과" | Guo, R., Li, Y., Shi, Y. 외 "Research on Identification Method of Wear Degradation of External Gear Pump Based on Flow Field Analysis", Sensors 20(14):4058, 2020. https://doi.org/10.3390/s20144058 | 1차 | 가이드북의 "기어 마모 → 출력 유압 약화"를 측판·끝면 누설 → 체적효율 저하로 구체화 |
| 같은 연구 수치: 배제량 4mL/r, 1470rpm, 잇수 12, 회전주파수 24.5Hz, 맞물림 주파수 294Hz. 초기 틈새 반경 20μm·끝면 50μm. 가속수명시험에서 체적효율 70% 시점의 마모 틈새는 반경 98.5μm·끝면 368.0μm, 도달 시간 960.3~981.8h(펌프 4대). 오염도 NAS 6 이하, 유온 약 50°C. 마모가 커질수록 압력 맥동 진폭이 커지고 스펙트럼 성분이 늘어남. 논문이 인용한 업계 표준 JB/T 7014.2-2018은 정격 조건 체적효율 82% 미만을 고장으로 본다 | 같은 논문 3·4장, 표 2·3 | 1차 | 마모 진행이 수백 시간 단위로 서서히 일어난다는 점 → 2분 46초짜리 급변 구간은 "마모 진행 자체"보다 "마모된 펌프가 특정 운전 조건에서 드러낸 증상"일 가능성(추정) |
| 기어 맞물림 주파수(GMF) = 피니언 잇수 × 피니언 축 회전주파수. 측대역은 GMF 성분의 진폭변조(AM)와 주파수·위상변조(FM)로 생기며, 결함 기어의 회전주파수 간격으로 대칭으로 생긴다. 전면적 마모는 GMF 고조파 크기를 키우고, 국부 결함(피팅 등)은 낮고 고른 측대역을 많이 만든다(Randall 2021 인용) | Lupea, I., Lupea, M., Coroian, A. "Helical Gearbox Defect Detection with Machine Learning Using Regular Mesh Components and Sidebands", Sensors 24(11):3337, 2024. https://doi.org/10.3390/s24113337 | 1차(논문 본문), 개념 원전(Randall)은 2차 | GMF·측대역 정의. 10Hz로는 관측 불가함을 함께 적는다 |
| 기어펌프 유량 맥동(유압 맥동)의 기본 주파수는 잇수 × 회전수(예: 12잇수·1800rpm → 360Hz) | 미국 특허 US10954935(능동 맥동 상쇄) 검색 요약 및 위 Guo 2020의 294Hz 계산 | 2차(특허 원문 미열람) / Guo 계산은 1차 | 출력 압력 서명 설명 |
| 저점도(고온): 모든 밀봉 틈새의 누설 증가 → 체적효율 저하·발열 → 윤활 상실·금속 접촉 마모(기어, 스러스트 판, 베어링). 고점도(저온): 밀봉·윤활 틈새가 채워지지 않음, 충전 손실이 캐비테이션 손상을 일으킴. 최적 운전 점도 약 100SUS(20cSt), 기동 최대 약 7500SUS(1600cSt). 흡입구 진공 5in.Hg(13cm) 이하, 흡입관 유속 8fps(2.5m/s) 이하 권장. 기동 시 서서히 예열하고 기름이 충분히 묽어질 때까지 최대 압력으로 운전하지 말 것 | Parker Hannifin Gear Pump Division, "Hydraulic Oil Recommendation"(GPD Oil Specifications, 발행일 미기재, 대리점 게시본). https://irp.cdn-website.com/8e9b3e0f/files/uploaded/GPD%20Oil%20Specifications.pdf | 1차 | 온도·점도와 누설·캐비테이션의 양방향 관계 |
| 캐비테이션: 펌프가 공급하려는 만큼 기름을 받지 못할 때 생긴다. 작동유에는 약 9%의 용존 공기가 있고, 기포가 고압부에서 붕괴하며 꾸준한 고음 휘이잉(whine) 소리와 내부 손상을 낸다. 원인: 막힌 흡입 스트레이너, 막힌 브리더, 저온 고점도, 고온, 과속, 높은 흡입 낙차. "대부분의 유압계통은 유온이 40°F보다 낮을 때 기동하지 말고, 최소 70°F가 되기 전에는 부하를 걸지 말 것". 에어레이션: 흡입관 공기 누입(흡입관은 대기압보다 낮아 기름 대신 공기가 샘), 저유면, 마모된 축 씰. 캐비테이션보다 불규칙한 소리, 구슬·자갈 구르는 소리, 탱크 거품 | Noria Corp., "Cavitation or Aeration? How to Tell the Difference", Machinery Lubrication, 2017-03-09. https://www.machinerylubrication.com/Read/30768/cavitation-or-aeration | 1차(업계지) | 캐비테이션과 에어레이션 구분, 기동 온도 경험칙(40°F≈4°C, 70°F≈21°C) |
| 펌프가 마모되면 토출량이 줄고 작동이 느려진다. "펌프가 심하게 마모돼 바이패스되는지 판단하려면 먼저 전동기 전류를 확인하라. 가능하면 새 펌프일 때 기준값을 잡아 두라." 전동기 마력은 계통이 요구하는 유압 마력(유량×압력)에 비례하므로 전류가 크게 낮으면 펌프 내부 바이패스 가능성이 크다. 펌프 하우징·흡입관 온도가 크게 오르면 심한 마모 신호 | "Troubleshooting Hydraulic Pumps", Machinery Lubrication, 2018-01-25. https://www.machinerylubrication.com/Read/31064/troubleshooting-hydraulic-pumps | 1차(업계지) | 현장 정비에서 "전류 기준선 대비 변화"를 마모 지표로 쓴다는 근거. 전류 채널의 존재 이유 |
| 기어펌프 캐비테이션 실험: 흡입측에 오리피스를 달아 강제 캐비테이션, 흡입구 근처 비접촉형 가속도계로 감지. FFT로 캐비테이션 기본 주파수를 찾고 시간영역 기법으로 온라인 감지 | Siano, D., Panza, M. A. "Diagnostic method by using vibration analysis for pump fault detection", Energy Procedia 148:10–17, 2018. https://doi.org/10.1016/j.egypro.2018.08.013 | 1차(초록) | 캐비테이션의 진동 감지 가능성. 원심펌프 문헌들은 캐비테이션을 1~20kHz 광대역으로 보고(2차, 검색 요약) → 10Hz로는 직접 관측 불가 |
| 트랙터 조향용 외접 기어펌프: 정상, 저널베어링 내면 마모, 치면 마모, 복합 마모를 1000·1500·2000rpm에서 비교. 모든 조건에서 PSD 최댓값이 70~120Hz에 있었고, PSD 면적(에너지)이 고장 구분에 효과적 | Mollazade, K., Ahmadi, H., Omid, M., Alimardani, R. "Vibration-Based Fault Diagnosis of Hydraulic Pump of Tractor Steering System by Using Energy Technique", Modern Applied Science 3(6):59, 2009. https://doi.org/10.5539/mas.v3n6p59 | 1차 | 기어펌프 마모를 진동 "에너지"로 구분한 사례 → 10Hz 데이터에서 쓸 수 있는 것은 에너지(분산) 계열 특징이라는 논리 |
| 전동기 전류 신호 분석(MCSA)은 고정자 전류 스펙트럼으로 전동기와 부하의 전기·기계 이상을 찾는 기법이다 | Benbouzid, M. E. H. "A review of induction motors signature analysis as a medium for faults detection", IEEE Trans. Industrial Electronics 47(5):984–993, 2000. https://doi.org/10.1109/41.873206 | 1차(초록) | MCSA 정의 인용 |
| 부하 토크 진동은 고정자 전류를 위상변조(PM)하고 회전자 편심은 진폭변조(AM)한다. 일반 전류 스펙트럼에서는 두 고장의 주파수 서명이 같아 시간-주파수 분석(Wigner 분포)으로 구분한다 | Blodt, M., Regnier, J., Faucher, J. "Distinguishing Load Torque Oscillations and Eccentricity Faults in Induction Motors Using Stator Current Wigner Distributions", IEEE Trans. Industry Applications 45(6):1991–2000, 2009. https://doi.org/10.1109/TIA.2009.2031888 | 1차(초록) | "이상 구간 전류가 사인에서 크게 벗어남"을 "부하 토크 변동이 전류의 진폭·위상을 흔든 결과"로 해석할 때의 근거(해석 자체는 추정) |
| 펌프 진단에 전동기 전기 신호를 쓰는 문헌 정리: Casada(ORNL)는 전동기 전류·전력 분석으로 흡입 스트레이너 막힘, 정렬 불량을 감지했고, 비교 연구에서 전동기 측 변수가 비정상 공정 조건 감지에 진동 센서보다 민감했다고 보고 | Harihara, P. P., Parlos, A. G. "Fault Diagnosis of Centrifugal Pumps Using Motor Electrical Signals", in Centrifugal Pumps(InTech), 2012. https://cdn.intechopen.com/pdfs/29650/InTech-Fault_diagnosis_of_centrifugal_pumps_using_motor_electrical_signals.pdf | 1차(장 본문), Casada 원전은 2차 | 전류 채널이 흡입측 문제(캐비테이션 원인)에도 반응할 수 있다는 근거 |
| 정렬 불량: 1X·2X 우세. 각도 정렬 불량은 커플링 양쪽 축방향 위상 180°, 평행 정렬 불량은 반경방향 위상 180°. 심하면 3X~10X 고조파. 풀림(looseness)은 수직 ≥ 수평. 전기적 원인 진동은 선 주파수의 정확히 2배(100 또는 120Hz)에 나타나고, 전원을 끄면 즉시 사라진다. 위상값은 ±30° 정확도 | SKF Condition Monitoring, "Vibration Diagnostic Guide" CM5003(Revised 9-00), 2000(포럼 게시본). https://forums.ni.com/attachments/ni/170/107329/1/CM5003%20Vibration%20Guide1.pdf | 1차 | 커플링 정렬 불량, 체결 풀림, 전기적 원인 진동의 서명 |
| 기계적 풀림 A형: 기계 발·베이스판·기초의 구조적 풀림·약화, 그라우팅 열화, 기초 볼트 풀림, 프레임 비틀림(소프트풋). 발·베이스판·기초 수직 측정 사이에 약 180° 위상차. B형: 필로블록 볼트 풀림, 프레임·베어링 받침 균열. C형: 부품 간 끼워맞춤 불량, 고조파가 많고 위상이 불안정하며 1/2·1/3X 분수 고조파(0.5X, 1.5X…)가 나타남. 풀림은 방향성이 강함 | IIT Kharagpur Virtual Labs, "Mechanical Looseness" 진단 차트(Technical Associates of Charlotte 차트 계열). http://vlabs.iitkgp.ac.in/rmfs/exp5/pdf/Mechanical_Looseness.pdf | 1차(교육자료) | 체결 풀림 가설의 서명 |

### 2-2. 고장 모드-증상 매트릭스(ISO 13379-1 FMSA 형식으로 정리)

아래 표는 2-1의 사실을 ISO 13379-1의 "고장 모드 → 증상 → 감시 기법" 틀에 맞춰 정리한 것이다. 마지막 열은 이 대회 데이터(10Hz, 진동 2 + 전류 1, 단위 미상)에서 볼 수 있는지에 대한 작성자의 판단이다(**추정**).

| 고장 모드 | 주요 원인 | 진동 서명(문헌) | 모터 전류 서명(문헌) | 출력 압력·유량(문헌) | 10Hz 데이터에서 관측 가능성(추정) |
|---|---|---|---|---|---|
| 측판·부싱·끝면 마모(내부 누설) | 장기 운전, 고압에서 부싱 기울어짐, 오염 입자(Guo 2020) | GMF 고조파 증가, 성분 증가(Guo 2020, Lupea 2024) | 유압 일(유량×압력) 감소로 전류 감소(ML 2018) | 토출 유량·체적효율 저하, 압력 맥동 증가(Guo 2020) | GMF는 불가(수백 Hz). 전류 레벨 기준선 하락, 진동 에너지 변화로만 간접 관측 |
| 치면 마모·피팅 | 마모 누적, 윤활 불량 | GMF와 1X 간격 측대역(Lupea 2024) | 부하 토크 변동 → 전류 위상·진폭 변조(Blodt 2009) | 맥동 증가 | 측대역 불가. 전류 파형 일그러짐(변조)으로 간접 관측 가능성 |
| 캐비테이션 | 흡입 막힘, 저유면, 고점도(저온), 과속(ML 2017, Parker) | kHz 광대역 증가(2차), 고음 소음(ML 2017) | 흡입 스트레이너 막힘을 전류·전력으로 감지한 사례(Casada, 2차) | 토출 유량 감소, 불안정 | 광대역 성분 직접 관측 불가. 센서가 RMS를 낸다면 에너지 증가로 보일 수 있음(센서 사양 확인 못 함) |
| 에어레이션 | 흡입관 공기 누입, 축 씰 마모, 저유면(ML 2017) | 불규칙 소음·진동(ML 2017) | 불규칙 부하 변동(추정) | 응답 둔화, 거품(ML 2017) | 불규칙한 저주파 변동으로 보일 수 있음(추정) |
| 커플링 정렬 불량 | 설치·열변형 | 1X·2X, 커플링 양쪽 180°(SKF) | 1X 관련 변조(추정) | 영향 작음 | 1X(약 29~30Hz)는 10Hz에서 앨리어싱됨 → 직접 판별 불가 |
| 기초·체결 풀림, 소프트풋, rocking | 볼트 풀림, 그라우트 열화, 기초 강성 저하(IIT, SKF) | 발·베이스·기초 간 180° 위상(SKF, IIT), 분수 고조파(C형) | 영향 작음(추정) | 영향 작음 | 상·하부 진동의 역상관이 "일치하는 정황"은 될 수 있으나 1X 위상 측정이 아님 |

## 3. 냉간 기동: 온도·점도·예열

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| Shell Tellus S2 M 46(ISO VG 46, HM, DIN 51524-2 HLP): 동점도 0°C 580cSt, 40°C 46cSt, 100°C 6.7cSt(ASTM D445), 점도지수 98, 유동점 −30°C | Shell, Technical Data Sheet "Shell Tellus S2 M 46", v3.5, 2017-03-21. https://www.shell-livedocs.com/data/published/en-AE/8476bad7-8701-441b-8a5a-7f113ad6e0ad.pdf | 1차 | VG 46의 대표 점도-온도 값. 대회 설비의 실제 유종은 확인 못 함 |
| 40°C·100°C 값으로 ASTM D341(Walther)식을 맞춰 외삽하면 0°C ≈ 597cSt(실측 580과 비슷), 10°C ≈ 268, 15°C ≈ 188, 20°C ≈ 135, 25°C ≈ 100, 30°C ≈ 76, 50°C ≈ 30cSt | 위 데이터로 작성자 계산 | 추정 | 기동 시 유온별 점도 표. 수치는 "약"으로 표기 |
| Rexroth AZPF 점도 범위: 연속 운전 허용 12~800mm²/s, 연속 운전 권장 20~100mm²/s, 냉간 기동 허용 최대 2000mm²/s. NBR 씰 −30~+80°C. 선정 선도에 "warm-up phase(예열 구간)" 표시 | Bosch Rexroth RE 10089/2021-11-24(위와 같음) | 1차 | 펌프 제조사 한계와 위 점도를 비교 |
| Casappa 기어펌프 카탈로그: 권장 점도 12~100mm²/s, 허용 750mm²/s. 냉간 기동(짧은 시간·저속 공회전 의미) 한계: 최소 흡입압 0.5bar abs, 토출압 ≤50bar, 회전수 ≤1500min⁻¹, 최저 −40°C, 최대 점도 2000mm²/s. 주위 온도가 −20°C 아래면 유온이 −20°C를 넘을 때까지 속도·압력 제한. "펌프·모터 온도와 유체 온도 차이가 10°C를 넘으면 계통을 빠르게 켰다 껐다 하며 서서히 데우고, 이후 압력과 회전수를 단계적으로 올릴 것" | Casappa, "Hydraulic gear pumps and motors"(Polaris 시리즈, 성능곡선 04/01.2019). https://www.casappa.com/c/downloads/download/9/ | 1차 | 예열 권고의 제조사 근거. "온도차 10°C" 기준은 열충격(틈새 변화) 관점 |
| Parker: 기동 최대 약 1600cSt, 서서히 예열, 충분히 묽어지기 전에는 최대 압력 금지. 최적 운전 유온 120~140°F(50~60°C), 일반 권장 최고 180°F(82°C) | Parker GPD Oil Specifications(위와 같음) | 1차 | 같은 용도 |
| 경험칙: 유온 40°F(약 4°C) 미만 기동 금지, 70°F(약 21°C) 전 부하 금지 | Machinery Lubrication 2017(위와 같음) | 1차(업계지) | 같은 용도 |
| 감시는 가능하면 정해진 운전 조건(예: 정상 운전 온도)에 도달한 뒤 하고, 변화가 고장 때문인지 운전 조건 변화 때문인지 가려야 한다. 과도 상태는 정해진 시작·종료 조건과 운전 프로파일로 감시 | ISO 17359:2018, 8.4절(아래 5장) | 1차 | "기동 직후 구간은 기준선과 따로 다룬다"는 설계의 표준 근거 |
| 7월 일요일 오전 재기동처럼 유온이 20~25°C라면 점도는 약 100~135cSt로 Rexroth 권장 상한(100) 근처이고 냉간 기동 한계(2000)의 1/15 수준이다. 따라서 "고점도 때문에 흡입 캐비테이션이 났다"는 설명은 근거가 약하다. 다만 주말 정지 뒤 기동 과도(배관 내 공기 고임에 따른 에어레이션, 빈 어큐뮬레이터 충전에 따른 고부하 지속, 펌프-유체 온도차)는 남는 가설이다 | 위 사실들의 조합 | 추정 | 이상 구간을 "냉간 기동"으로 단정하지 말고 "기동 과도 가설"로 쓰며, 유온 센서가 없어 검증할 수 없다고 적는다. 실제 유온·실내 온도는 확인 못 함 |

## 4. 진동 위상·저주파 진동 해석

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| 구조(structural) 문제: 기초가 열화돼 강성을 잃으면 기계가 흔들리며(rock), 그때 기계 발·베이스판·기초 사이에 180° 위상 변화가 생긴다. 소프트풋은 발 볼트를 조일 때 위상이 바뀐다 | SKF CM5003(위와 같음) | 1차 | rocking·소프트풋 정의 |
| A형 풀림은 발·베이스판·기초 수직 측정 사이에 약 180° 위상차를 보일 수 있다 | IIT Kharagpur 차트(위와 같음) | 1차(교육자료) | 같은 용도 |
| 진동은 벡터량이므로 두 값을 비교할 때 위상각을 고려해야 할 수 있다 | ISO 20816-1:2016, 4.3절 NOTE(아래 5장) | 1차 | 두 채널의 관계(상관·위상)를 특징으로 쓰는 이유 |
| 고전적 위상 분석은 회전 기준(타코미터)에 대한 1X 성분의 위상이고 정확도는 ±30°다(SKF). 대회 데이터의 상·하부 상관 +0.28 → −0.36은 10Hz 원시 샘플 간 상관이라 1X 위상과 같은 개념이 아니다. 1X(4극 60Hz 전동기면 약 29~30Hz)는 10Hz 샘플링에서 앨리어싱된다. 또 PLC가 두 채널을 순차 변환하면 채널 간 시간 어긋남이 고주파 성분의 겉보기 위상을 바꿀 수 있다 | SKF + 앨리어싱 원리(7장) | 추정 | "역위상 = rocking 확정"이 아니라 "rocking·기초 풀림과 일치하는 정황, 확인에는 동기 샘플링·1X 위상 측정이 필요"라고 쓴다 |
| 펌프-모터 유닛에 상부·하부 센서가 붙어 있을 때, 두 지점이 반대로 움직이면 두 센서 사이 어딘가를 축으로 한 흔들림(rocking/pitching) 모드와 맞는다 | SKF·IIT 정의를 센서 배치에 적용 | 추정 | 해석 문장의 근거. 실제 센서 위치·방향(수직·수평)은 가이드북 기준으로 다시 확인할 것 |
| 저주파(<5Hz) 성분의 일반적 원인 ① 공정·부하 주기: 프레스 행정(60~100spm = 1.0~1.7Hz)과 어큐뮬레이터 충전·언로딩 주기 | 1장 행정 속도·압력원 구조 | 추정(1장 1차 사실 기반) | 정상 구간의 저주파·주기 성분부터 공정 주기로 설명되는지 확인 |
| ② 맥놀이(beating): 주파수가 매우 가까운 두 성분이 더해지면 진폭이 두 주파수 차이의 속도로 오르내린다(예: 29.5Hz와 30.5Hz → 1.0Hz). 진폭변조와는 다른 선형 합 현상 | Erbessd Instruments "Vibration Beating", Power-MI "Beating" 등(검색 요약) https://www.erbessd-instruments.com/en/articles/vibration-beating/ | 2차 | 두 회전체(예: 전동기와 다른 설비)의 근접 주파수가 저주파 진폭 변동을 만들 수 있다는 대안 |
| ③ 오일 휠(oil whirl): 미끄럼 베어링에서 회전속도의 약 40~49%(0.4~0.48X)로 나타나는 아동기 진동 | 검색 요약(Vibromera, Turbomachinery Magazine 등) | 2차 | 기어펌프는 미끄럼 베어링을 쓰지만(Rexroth) 0.42×30Hz ≈ 12.6Hz라 <5Hz 설명으로는 맞지 않음(추정) |
| ④ 앨리어싱: 나이퀴스트(샘플링의 절반)보다 높은 성분은 낮은 주파수로 접혀 들어오고, 나이퀴스트의 배수마다 접힘이 반복된다. 이를 막는 유일한 방법은 아날로그 안티앨리어싱 필터다 | Data Physics, "Dynamic Signal Analysis Review – Part 3: Aliasing". https://dataphysics.com/blog/dynamic-signal-analysis/dynamic-signal-analysis-review-part-3-aliasing/ | 2차(계측기 업체 해설) | 10Hz 데이터의 "저주파 증가"(자기상관 −0.03 → 0.69)가 실제 저주파일 수도, 고주파가 접힌 것일 수도 있다는 한계 |
| ⑤ C형 풀림의 분수 고조파(0.5X 등) | IIT 차트 | 1차(교육자료) | 0.5X도 약 15Hz라 <5Hz 설명으로는 부족(추정) |

## 5. 상태감시 표준

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| **ISO 17359:2018**(3판, 2018-01, 2011판 대체): 기계 상태감시 프로그램을 세울 때의 일반 절차 지침, 모든 기계에 적용. 감시 활동을 근본 원인 고장 모드의 증상 탐지로 향하게 하고, 경보 기준 설정·진단·예지·신뢰도 향상의 일반 접근을 기술. 부속서 A(기계 유형별 감시 변수 예), B(고장-측정 변수 대응표, 표 B.2~B.11) | ISO 17359:2018 미리보기(iTeh). https://cdn.standards.iteh.ai/samples/71194/c551f4c170654bb19be2ee017d144969/ISO-17359-2018.pdf / https://www.iso.org/standard/71194.html | 1차(미리보기) | 보고서 방법론의 상위 틀: 고장 모드 → 증상 → 측정 변수 → 경보 기준 |
| ISO 17359 8.4: 정해진 운전 조건(예: 정상 운전 온도)에서 감시하고, 변화가 고장인지 운전 조건 변화인지 가릴 것. 8.5: 감시 간격은 고장 진행 속도와 고장까지의 선행 시간(LTTF)에 따라 정함. 8.6: 정상 상태에서는 조건이 바뀌기 전에 데이터 한 세트를 다 얻을 만큼 빨리, 과도 상태에서는 고속 획득이 필요할 수 있음 | 같은 문서 8.4~8.6절 | 1차 | 운전 상태 분리, 10Hz 샘플링의 적정성 논의 |
| **ISO 13374-1:2003**: 상태감시 정보 흐름을 6개 처리 블록으로 정의. DA(데이터 획득: 변환기 출력 → 디지털 물리량 + 시간·교정·데이터 품질·센서 구성 정보), DM(데이터 처리: 신호 분석, 서술자·가상 센서 계산), SD(상태 감지: 정상 기준선 프로파일 생성·유지, 새 데이터의 이상 여부와 "alert/alarm" 구역 판정), HA(건강 평가: 고장 진단, 현재 건강 등급), PA(예지: 미래 건강 상태·고장 모드, 잔여 수명), AG(조언 생성: 보전·운전 변경 권고). 앞 3개는 기술별, 뒤 3개는 여러 기술을 결합 | ISO 13374-1:2003 미리보기(iTeh). https://cdn.standards.iteh.ai/samples/21832/4f282cf6f5594b73be0bbca7590719f1/ISO-13374-1-2003.pdf | 1차(미리보기). 현행 여부는 확인 못 함 | 파이프라인 그림을 DA→DM→SD→HA→PA→AG로 매핑. 이 대회 범위는 DA~SD(+HA 일부)라고 명시 |
| **ISO 13379-1:2012**: 데이터 해석·진단 일반 지침. 고장 모드 증상 분석(FMSA): 구성품 → 고장 모드 → 영향 → 원인 → 증상 → 최적 감시 기법 → 감시 빈도를 나열하고 탐지성(DET), 심각도(SEV), 진단 신뢰도(DGN), 예지 신뢰도(PGN)를 1~5로 매겨 감시 우선순위 수(MPN)를 산출. 진단 요구사항 보고서에 "다루는 고장과 다루지 않는 고장"을 명시하라고 강하게 권고 | ISO 13379-1:2012 미리보기(iTeh). https://cdn.standards.iteh.ai/samples/39836/30bb973655944d23881a0f819e01416e/ISO-13379-1-2012.pdf | 1차(미리보기) | 2-2절 매트릭스의 틀. "이 데이터로 진단 불가한 고장 모드" 목록을 보고서에 넣는 근거 |
| ISO 13379-1:2012는 철회됐고 ISO 13379-1:2025(2판, 2025-10, 39쪽, 제목이 "machine systems"로 바뀜)로 대체됨 | ISO 웹페이지(검색 결과). https://www.iso.org/standard/88027.html | 2차(검색 요약) | 인용 시 "2012판(2025판으로 개정)"이라고 적는다 |
| **ISO 20816-1:2016**(ISO 7919-1:1996, ISO 10816-1:1995 및 Amd 1:2009 통합·대체): "혼동을 피하고 올바른 해석을 위해 측정량과 단위를 항상 명확히 밝혀야 한다(예: 변위 p-p μm, 속도 r.m.s. mm/s)". 비회전부에는 r.m.s. 속도가 선호 측정량. 진동 심각도 = 합의된 지지·운전 조건에서 측정한 광대역 크기의 최댓값. 과거 인수시험은 10Hz~1,000Hz 광대역이었으나 상태감시에는 맞지 않을 수 있음 | ISO 20816-1:2016 미리보기(iTeh). https://cdn.standards.iteh.ai/samples/63180/ace1232a76714dc48087a6cfe49c2bda/ISO-20816-1-2016.pdf | 1차(미리보기) | "센서 단위·측정량이 공개되지 않아 ISO 심각도 구역 판정은 불가, 기준선 대비 상대 지표만 사용"의 근거 |
| ISO 20816 평가 구역: A(신규 설치 수준), B(장기 무제한 운전 허용), C(장기 연속 운전 부적합), D(손상 가능). ISO 20816-3:2022(15kW 초과 산업기계, 120~30,000r/min) 경계값: 그룹 1 강성 지지 2.3/4.5/7.1mm/s, 그룹 2 강성 지지 1.4/2.8/4.5mm/s, 유연 지지는 그룹 1 3.5/7.1/11.0, 그룹 2 2.3/4.5/7.1mm/s(r.m.s.) | 검색 요약(Vibromera 등), 표준 원문 미열람. https://vibromera.eu/glossary/iso-20816-3/ | 2차 | 숫자는 "참고" 수준으로만. 정변위 기어펌프에 그대로 적용되는지는 확인 못 함 |
| **ISO 13381-1:2015**: 예지(prognosis) 프로세스 개발·적용 지침. 잔여 유효 수명(RUL) = 시스템 건강이 정해진 고장 임계 아래로 떨어지기 전까지 남은 시간. 예지는 고장 진행 과정에 대한 지식에 기반하며, ISO 17359의 일반 개념이 그 전제 | ISO 13381-1:2015 미리보기(iTeh). https://cdn.standards.iteh.ai/samples/51436/8246d96c8ff54347ae65f3aba73f2e88/ISO-13381-1-2015.pdf | 1차(미리보기) | "이상 1구간·이상 1건으로는 RUL 예측(PA 블록)을 할 수 없다"는 범위 한정 근거 |

## 6. 경보 관리

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| ISA-18.2 경보 성능 지표(운전 위치당): 하루 약 150건 / 시간당 약 6건(평균) / 10분당 약 1건(평균) = "수용 가능성 매우 높음", 하루 약 300건 / 시간당 약 12건 / 10분당 약 2건 = "최대 관리 가능". 30건 넘는 시간 비율 약 <1%, 10건 넘는 10분 구간 비율 약 <1%, 10분 최대 경보 ≤10, 경보 홍수 시간 비율 약 <1%, 상위 10개 경보의 부하 기여 약 <1%~최대 5%, 채터링·순간 경보 0, 장기 잔류(stale) 경보 하루 5건 미만, 우선순위 분포 약 80%(낮음)/15%(중간)/5%(높음) | exida, "Alarm Management and ISA-18 – A Journey, Not a Destination"(© 2018–2020, ISA-18.2-2009 표 재수록). https://www.exida.com/articles/ALARM-MANAGEMENT-AND-ISA-18-A-JOURNEY-NOT-A-DESTINATION.pdf | 2차(표준 표의 재수록) | 오경보율 목표를 "운전원 1인 시간당 6건 이하" 같은 산업 기준과 비교 |
| EEMUA 191(3판 p.96~97): 정상 운전 중 평균 10분에 1건 미만은 수용 가능성 매우 높음, 5분에 1건은 관리 가능, 2분에 1건은 과부하 가능성, 1분에 1건 초과는 수용 불가 가능성 매우 높음. 큰 이상 직후 첫 10분: 10건 미만 관리 가능, 20~100건 대응 어려움, 100건 초과 과다. 이 기준의 기원은 영국 HSE 연구보고서 CRR 166/1998(Bransby & Jenkinson) | Dubois, L.(M.A.C. Solutions/ProcessVue), "The Sense and Nonsense of Alarm System Performance KPIs", V1.0. https://www.processvue.com/downloads/Alarm_system_performance_KPIs_V1_0.pdf | 2차(EEMUA 원문 재인용) | 같은 용도. EEMUA 원문은 확인 못 함 |
| ISA 18.2-2016은 "하루 약 150건" 지표 등 4개 항목(30건 넘는 시간 비율, 하루 경보 수, 무단 억제, 무단 속성 변경)을 표에서 뺐다. IEC 62682는 하루 약 144건을 목표로 제시(글은 2014년 기술, 참고문헌은 IEC 62682-2015) | 같은 문서 | 2차 | 하루 단위 환산은 판본에 따라 다르다는 단서. 10분·1시간 단위 지표를 우선 사용 |
| ISA-18.2 경보 속성: ON-delay(조건이 얼마나 오래 참이어야 경보가 울리는지), OFF-delay(조건이 얼마나 오래 거짓이어야 정상 복귀하는지, 반복 경보 방지), deadband(아날로그 경보의 히스테리시스, 예: 0~10m 신호의 8m 고경보에 1% 데드밴드 → 8m 초과 시 ON, 7.9m 미만 시 OFF). 경보 상태도에 래치 상태(Latch Unack, Latch Ack)가 있고, 공정이 정상으로 돌아와도 운전원이 리셋해야 해제 | Nasby, G. "Introduction to the ISA 18.2 Alarm Management Standard"(York Region 교육 슬라이드), 2013. https://www.grahamnasby.com/files_publications/NasbyG_2013_IntroToAlarmMgmt_YorkRegion_oct2013_slides.pdf | 2차(표준 해설 교육자료) | 경보 후처리 설계(k-of-n, 지연, 래치)를 표준 용어로 설명 |
| 래치 경보(latching alarm) 정의: 공정 조건이 정상으로 돌아온 뒤에도 경보 상태를 유지하며, 운전원이 리셋해야 정상으로 돌아가는 경보. 리셋 = 래치 경보를 해제하는 운전원 조작 | ISA-18.2 정의를 인용한 검색 결과 | 2차 | 같은 용도 |
| 신호 종류별 데드밴드·지연 시작값(유량 5%·15초, 레벨 5%·60초, 압력 2%·15초, 온도 1%·60초) | 검색 요약(ISA-18.2 표로 소개됨), 원문 표 미확인 | 2차(원문 미확인) | 쓰려면 "ISA-18.2 해설 자료에 소개된 시작값"이라고 출처 수준을 낮춰 적는다 |
| 10분당 1건 = 시간당 6건 = 하루 144건(24시간 연속 운전 가정) | 산술 | 추정(계산) | 오경보율을 운전시간 기준으로 환산할 때 사용 |

## 7. 전력 주파수·샘플링

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| 표준주파수 60헤르츠, 허용오차 "60헤르츠 상하로 0.2헤르츠 이내"(전기사업법 시행규칙 제18조 관련 별표 3). 2013-03-23 개정판과 2025-06-13 개정판 모두 같음(2025년 개정은 220V 허용오차를 ±13V → ±22V로 바꾼 것) | 국가법령정보센터 별표 PDF. 2013판 https://law.go.kr/flDownload.do?gubun=&flSeq=115149499 / 2025판 https://www.law.go.kr/LSW/flDownload.do?gubun=&flSeq=152902497&bylClsCd=110201 | 1차 | 데이터 수집 시점(2022년)의 법정 주파수 범위. 검색 요약 중 "2025년에 ±0.3%로 바뀌었다"는 내용은 원문과 달라 틀린 정보임 |
| 전력거래소는 육지 60±0.1Hz, 60±0.2Hz, 제주 60±0.1Hz 주파수 유지율(실적·목표)을 월별로 공개(HWP) | 공공데이터포털 "한국전력거래소_주파수 유지율". https://www.data.go.kr/data/15051430/fileData.do | 2차(메타데이터만 확인, 2022년 7월 값 미확인) | 실제 계통 주파수가 대부분 ±0.1Hz 안에 있었음을 보이려면 이 파일을 내려받아 확인 |
| 전력시장운영규칙 별표 3(전력계통 운영 기준): 주파수제어예비력(평상시 계통주파수 안정 유지, AGC), 1차예비력(주파수 변동 10초 이내 응동), 2차예비력(과도 안정 주파수를 목표주파수 60Hz로 회복) 등 | 전력거래소 전력시장운영규칙 별표 3. https://marketrule.kpx.or.kr/lmxdata/attach/2025/5/upload_5127126665285383397_p8.pdf | 1차 | 계통 주파수가 상시 제어된다는 배경 |
| 겉보기(앨리어스) 주파수 = abs(f_grid − k·f_s), k는 결과를 0~f_s/2로 만드는 정수. f_s = 10.000Hz이면 k = 6이고, f_grid가 59.8~60.2Hz일 때 앨리어스는 0~0.2Hz다. 관측된 0.60Hz를 만들려면 f_s ≈ 9.90Hz(샘플 간격 ≈ 0.1010초) 또는 f_s ≈ 10.10Hz(≈ 0.0990초)여야 한다(샘플당 약 1ms, 약 1% 어긋남) | 앨리어싱 원리(Data Physics) + 법정 주파수 범위 | 추정(계산) | 보고서의 "0.60Hz 앨리어싱" 설명에 반드시 덧붙일 조건. 타임스탬프 간격 분포를 확인해 0.099/0.101초 경향이 있는지 검증 권장 |
| 대안 가설: 0.60Hz가 실제 공정 주기(36spm 행정, 어큐뮬레이터 충전 주기)일 수 있다. 구분법: (a) 순시 교류 앨리어스면 값이 0을 기준으로 양·음 대칭으로 흔들리고, RMS·포락선이면 양수 쪽에서만 오르내린다. (b) 앨리어스 주파수는 계통 주파수 변동만큼(1:1) 흔들리지만 공정 주기는 PLC 설정에 묶인다 | 1장 행정 속도 + 위 계산 | 추정 | 전류 채널 해석의 강건성 점검 항목 |
| 진폭·위상 변조는 앨리어싱 뒤에도 보존된다: 60Hz 반송파 전류 A(t)·cos(2π·60·t + φ(t))를 10Hz로 찍으면 A(t)·cos(2π·0.6·t + φ(t)) 꼴이 되므로, 부하 토크 변동에 따른 진폭·위상 변조(Blodt 2009)가 겉보기 사인의 일그러짐으로 나타난다(변조 대역이 수 Hz 이내일 때) | 샘플링 이론 + Blodt 2009 | 추정 | "이상 구간 전류가 사인에서 크게 벗어남"을 부하 토크 변동의 간접 증거로 해석하는 논리 |
| PLC의 주기 스캔(OB1 등)은 프로그램 실행·통신 부하에 따라 스캔마다 길이가 달라진다. 고정 간격 실행이 필요하면 주기 인터럽트(예: Siemens OB35, 기본 100ms, 1~60000ms 설정)를 쓴다 | Siemens S7-1200 System Manual "Monitoring and configuring the cycle time"(manualslib), industrialmonitordirect 해설(검색 요약) | 2차(원문 미열람) | 0.1초 간격이 정확히 지켜졌다고 가정하면 안 되는 이유. 대회 설비의 PLC 기종·로깅 방식은 확인 못 함 |
| 저속 상태감시 데이터에서 진동 채널은 RMS 같은 집계값으로 기록되는 경우가 있다: UCI 유압 데이터의 진동 VS1은 1Hz, 단위 mm/s | UCI Machine Learning Repository(8장) | 1차 | 대회 진동 채널이 순시값인지 RMS인지에 따라 해석이 달라진다는 점을 적는다(대회 센서 사양은 확인 못 함) |

## 8. 유압 프레스·펌프 상태감시 사례 논문

| 사실 | 출처(URL) | 신뢰도 | 보고서에 쓰는 법 |
|---|---|---|---|
| Helwig, Pignanelli, Schütze(2015): 부품 상태를 가역적으로 열화시킬 수 있는 유압 시험대로 여러 고장 시나리오를 만들고, 원시 센서 데이터에서 뽑은 특징과 고장 특성의 상관으로 핵심 특징을 고른 뒤 LDA 판별 공간에서 고장 상태와 심각도를 분류. 고정 작업 사이클에서 구현·시험했고, 무작위 부하 사이클에서는 특징 추세 분포 분석으로 분류율을 높임 | Helwig, N., Pignanelli, E., Schütze, A. "Condition monitoring of a complex hydraulic system using multivariate statistics", Proc. IEEE I2MTC 2015, pp. 210–215. https://doi.org/10.1109/I2MTC.2015.7151267 | 1차(OpenAlex 초록) | "부하 사이클이 바뀌면 분류가 어려워지고, 운전 조건 처리로 보완"한 선례 → 운전 상태 분리의 필요성 |
| 위 연구 데이터(UCI, 2018-04-25 기증): 2,205 사이클, 사이클당 60초. 압력 PS1~6 100Hz(bar), 모터 전력 EPS1 100Hz(W), 유량 FS1~2 10Hz(l/min), 온도 TS1~4 1Hz(°C), 진동 VS1 1Hz(mm/s), 냉각 효율 CE·냉각 동력 CP·효율 SE 1Hz. 고장: 냉각기 효율 3~100%, 밸브 거동 73~100%, 펌프 내부 누설 0~2(없음·약함·심함), 어큐뮬레이터 압력 90~130bar. 1차 작동회로와 2차 냉각·여과 회로가 탱크로 연결 | UCI ML Repository "Condition Monitoring of Hydraulic Systems"(DOI 10.24432/C5CW21). https://archive.ics.uci.edu/dataset/447/condition+monitoring+of+hydraulic+systems / Zenodo https://zenodo.org/records/1323611 | 1차 | 샘플링 1/10/100Hz 사실 확인 완료. "1~10Hz 저속 센서로도 펌프 내부 누설을 다룬 공개 선례"로 인용. 단, 이 데이터에는 압력·유량·전력이 있고 대회 데이터에는 없다는 차이를 함께 적는다 |
| Mohanty, Pradhan, Mahalik, Dastidar(2012): 진동 분석과 MCSA가 기계 고장 탐지에 가장 적합한 기법이라 보고, 원심펌프의 정상·결함 임펠러를 MCSA의 시간·주파수 영역 분석으로 구분(유의한 차이 확인, 고장 예측 전략 제시) | International Journal of Automation and Control 6(3/4):261–276, 2012. https://doi.org/10.1504/IJAAC.2012.051884 | 1차(초록) | 진동+전류 결합의 선례 |
| Guo et al.(2020): 외접 기어펌프 가속수명시험(4대)으로 마모 열화 상태 식별(2-1절 수치) | Sensors 20(14):4058. https://doi.org/10.3390/s20144058 | 1차 | 기어펌프 마모의 시간 척도(수백 시간) |
| Mollazade et al.(2009): 외접 기어펌프 마모 고장을 진동 PSD 에너지로 구분(2-1절) | Modern Applied Science 3(6):59. https://doi.org/10.5539/mas.v3n6p59 | 1차 | 진동 에너지 특징의 근거 |
| Gu & Shi(2019): 압력·유량·진동 신호는 비정상적이고 외란에 민감하므로, 인버터 구동 유압계통을 전동기 고정자 측 전압·전류의 진폭과 위상으로 그린 "동적 전력 원 그래프"로 감시. 여러 주파수·부하 실험에서 온라인 감시 가능 확인 | Gu, L., Shi, Y. "Online Monitoring Technique of Power Condition for Inverter-Fed Motor Driven Hydraulic System", Mathematical Problems in Engineering 2019:4908942. https://doi.org/10.1155/2019/4908942 | 1차(초록) | 유압계통을 전동기 전기 신호만으로 감시한 선례 → 전류 채널의 가치 |
| Bernini, Waltz, Albertelli, Monno: 공작기계 유압 유닛(펌프·센서·밸브)에 디지털 트윈으로 정상·고장 데이터를 만들어 진단·예지. 펌프 진단 성능은 우수, 가장 어려운 작업 사이클에서 센서 79.75%, 밸브 74.93%. 정상·비정상(가변) 운전 조건 모두 다룸 | Proc. IMechE Part B: J. Engineering Manufacture 236(9):1199–1215, 2022(온라인 2021). https://doi.org/10.1177/09544054211064682 | 1차(OpenAlex 초록) | 고장 데이터 부족을 시뮬레이션으로 메운 선례(향후 과제) |
| Unterberg et al.(2021): 파인블랭킹 공정의 공구 마모를 음향방출(AE) 특징으로 감시 | Procedia CIRP 104:164–169, 2021. https://doi.org/10.1016/j.procir.2021.11.028 | 1차(초록) | 파인블랭킹 상태감시 문헌은 주로 공구 쪽이라는 관찰 → 펌프 쪽 저속 데이터 분석은 상대적으로 드묾(추정, 체계적 문헌조사는 하지 않음) |

---

## 확인 못 한 항목(보고서에 단정하지 말 것)

- 대회 설비의 실제 제원: 펌프 형식·잇수·전동기 극수와 회전수, 프레스 spm, 어큐뮬레이터 유무, 작동유 종류, 유온
- 진동 센서가 순시 가속도(또는 속도)를 내는지 RMS를 내는지, 단위, 장착 방향(수직·수평), PLC 기종과 채널 변환 순서·간격
- V링력·역압의 블랭킹력 대비 비율(출처마다 다름)
- ISO 20816 구역 정의·경계값 원문, ISA-18.2(2016) 원문 표, EEMUA 191 원문, ISA-18.2 데드밴드·지연 시작값 원문 표
- 2022년 7월 실제 계통 주파수 유지율(전력거래소 HWP 파일 미열람)
- ISO 13374-1:2003의 현행 여부

## 보고서용 인용 목록

표준·법령
1. ISO. ISO 17359:2018, Condition monitoring and diagnostics of machines — General guidelines (3rd ed.). ISO, 2018. https://www.iso.org/standard/71194.html
2. ISO. ISO 13374-1:2003, Condition monitoring and diagnostics of machines — Data processing, communication and presentation — Part 1: General guidelines. ISO, 2003. https://cdn.standards.iteh.ai/samples/21832/4f282cf6f5594b73be0bbca7590719f1/ISO-13374-1-2003.pdf
3. ISO. ISO 13379-1:2012, Condition monitoring and diagnostics of machines — Data interpretation and diagnostics techniques — Part 1: General guidelines. ISO, 2012(ISO 13379-1:2025로 개정). https://www.iso.org/standard/88027.html
4. ISO. ISO 20816-1:2016, Mechanical vibration — Measurement and evaluation of machine vibration — Part 1: General guidelines. ISO, 2016. https://cdn.standards.iteh.ai/samples/63180/ace1232a76714dc48087a6cfe49c2bda/ISO-20816-1-2016.pdf
5. ISO. ISO 13381-1:2015, Condition monitoring and diagnostics of machines — Prognostics — Part 1: General guidelines. ISO, 2015. https://www.iso.org/standard/51436.html
6. ANSI/ISA-18.2, Management of Alarm Systems for the Process Industries(2009, 2016). ISA. (표 수치는 exida 재수록본으로 확인: https://www.exida.com/articles/ALARM-MANAGEMENT-AND-ISA-18-A-JOURNEY-NOT-A-DESTINATION.pdf)
7. EEMUA Publication 191, Alarm Systems — A Guide to Design, Management and Procurement(3rd ed.). EEMUA. (수치는 Dubois, ProcessVue 백서로 확인: https://www.processvue.com/downloads/Alarm_system_performance_KPIs_V1_0.pdf)
8. 산업통상자원부. 「전기사업법 시행규칙」 별표 3 표준전압·표준주파수 및 허용오차(제18조 관련), 개정 2013.3.23 / 2025.6.13. 국가법령정보센터. https://www.law.go.kr/LSW/flDownload.do?gubun=&flSeq=152902497&bylClsCd=110201
9. 한국전력거래소. 전력시장운영규칙 별표 3 전력계통 운영 기준. https://marketrule.kpx.or.kr/lmxdata/attach/2025/5/upload_5127126665285383397_p8.pdf

학술 논문·도서
10. Shu, Y., Liu, Y., Xu, Z., Zhao, X., Chen, M. Optimization of Hydraulic Fine Blanking Press Control System Based on System Identification. Processes, 11(1), 59. MDPI, 2023. https://doi.org/10.3390/pr11010059
11. Xu, Z., Liu, Y., Hua, L., Zhao, X., Guo, W. Energy analysis and optimization of main hydraulic system in 10,000 kN fine blanking press with simulation and experimental methods. Energy Conversion and Management, 181, 143–158. Elsevier, 2019. https://doi.org/10.1016/j.enconman.2018.12.012
12. Schuler GmbH (ed.). Metal Forming Handbook. Springer, 1998. https://doi.org/10.1007/978-3-642-58857-0
13. Guo, R., Li, Y., Shi, Y. et al. Research on Identification Method of Wear Degradation of External Gear Pump Based on Flow Field Analysis. Sensors, 20(14), 4058. MDPI, 2020. https://doi.org/10.3390/s20144058
14. Mollazade, K., Ahmadi, H., Omid, M., Alimardani, R. Vibration-Based Fault Diagnosis of Hydraulic Pump of Tractor Steering System by Using Energy Technique. Modern Applied Science, 3(6), 59. CCSE, 2009. https://doi.org/10.5539/mas.v3n6p59
15. Siano, D., Panza, M. A. Diagnostic method by using vibration analysis for pump fault detection. Energy Procedia, 148, 10–17. Elsevier, 2018. https://doi.org/10.1016/j.egypro.2018.08.013
16. Lupea, I., Lupea, M., Coroian, A. Helical Gearbox Defect Detection with Machine Learning Using Regular Mesh Components and Sidebands. Sensors, 24(11), 3337. MDPI, 2024. https://doi.org/10.3390/s24113337
17. Benbouzid, M. E. H. A review of induction motors signature analysis as a medium for faults detection. IEEE Transactions on Industrial Electronics, 47(5), 984–993. IEEE, 2000. https://doi.org/10.1109/41.873206
18. Blodt, M., Regnier, J., Faucher, J. Distinguishing Load Torque Oscillations and Eccentricity Faults in Induction Motors Using Stator Current Wigner Distributions. IEEE Transactions on Industry Applications, 45(6), 1991–2000. IEEE, 2009. https://doi.org/10.1109/TIA.2009.2031888
19. Harihara, P. P., Parlos, A. G. Fault Diagnosis of Centrifugal Pumps Using Motor Electrical Signals. In: Centrifugal Pumps. InTech, 2012. https://cdn.intechopen.com/pdfs/29650/InTech-Fault_diagnosis_of_centrifugal_pumps_using_motor_electrical_signals.pdf
20. Helwig, N., Pignanelli, E., Schütze, A. Condition monitoring of a complex hydraulic system using multivariate statistics. Proc. 2015 IEEE I2MTC, 210–215. IEEE, 2015. https://doi.org/10.1109/I2MTC.2015.7151267
21. Helwig, N., Pignanelli, E., Schütze, A. Condition Monitoring of Hydraulic Systems [Dataset]. UCI Machine Learning Repository, 2018. https://doi.org/10.24432/C5CW21
22. Mohanty, A. R., Pradhan, P. K., Mahalik, N. P., Dastidar, S. G. Fault detection in a centrifugal pump using vibration and motor current signature analysis. International Journal of Automation and Control, 6(3/4), 261–276. Inderscience, 2012. https://doi.org/10.1504/IJAAC.2012.051884
23. Gu, L., Shi, Y. Online Monitoring Technique of Power Condition for Inverter-Fed Motor Driven Hydraulic System. Mathematical Problems in Engineering, 2019, 4908942. Hindawi, 2019. https://doi.org/10.1155/2019/4908942
24. Bernini, L., Waltz, D., Albertelli, P., Monno, M. A novel prognostics solution for machine tool sub-units: The hydraulic case. Proc. IMechE Part B: Journal of Engineering Manufacture, 236(9), 1199–1215. SAGE, 2022(온라인 2021). https://doi.org/10.1177/09544054211064682
25. Unterberg, M., Voigts, H., Weiser, I. F., Feuerhack, A., Trauth, D., Bergs, T. Wear monitoring in fine blanking processes using feature based analysis of acoustic emission signals. Procedia CIRP, 104, 164–169. Elsevier, 2021. https://doi.org/10.1016/j.procir.2021.11.028

제조사·업계 자료
26. Kaya, S., Altan, T. Blanking developments – Part I: Fineblanking process and tool design. The Fabricator, 2007-07-10. https://www.thefabricator.com/thefabricator/article/bending/blanking-developments---part-i
27. Kaya, S., Altan, T. Blanking developments – Part II: Fineblanking part, process design. The Fabricator, 2007-08-08. https://www.thefabricator.com/thefabricator/article/bending/blanking-developments---part-ii
28. Feintool Technologie AG. Fineblanking reinvented — Hydraulic fineblanking presses at the highest level – the FB one(브로슈어, FIH D 150 092018). https://www.feintool.com/wp-content/uploads/2023/07/Broschuere_FB_one_A4_EN_WEB.pdf
29. ANDRITZ. More energy efficiency and output: ANDRITZ Schuler further develops HFA fineblanking presses together with Feintool(보도자료), 2026-01-22. https://www.andritz.com/newsroom-en/metals/2026-01-22-hfa-fineblanking-group
30. Bosch Rexroth AG. External gear pump High Performance AZPF, RE 10089/2021-11-24. https://boschrexroth-russia.ru/image/catalog/docs/re10089_2021-11-24_AZPF.pdf
31. Casappa S.p.A. Hydraulic gear pumps and motors(Polaris), 2019. https://www.casappa.com/c/downloads/download/9/
32. Parker Hannifin Gear Pump Division. Hydraulic Oil Recommendation(GPD Oil Specifications). https://irp.cdn-website.com/8e9b3e0f/files/uploaded/GPD%20Oil%20Specifications.pdf
33. Shell. Technical Data Sheet — Shell Tellus S2 M 46, v3.5, 2017-03-21. https://www.shell-livedocs.com/data/published/en-AE/8476bad7-8701-441b-8a5a-7f113ad6e0ad.pdf
34. Morselli, M. A.(Danfoss Power Solutions). US 10,024,317 B2, Geared hydraulic machine and relative gear wheel, 2018. https://patents.google.com/patent/US10024317B2/en
35. SKF Condition Monitoring. Vibration Diagnostic Guide, CM5003(Revised 9-00), 2000. https://forums.ni.com/attachments/ni/170/107329/1/CM5003%20Vibration%20Guide1.pdf
36. IIT Kharagpur Virtual Labs. Mechanical Looseness(진단 차트). http://vlabs.iitkgp.ac.in/rmfs/exp5/pdf/Mechanical_Looseness.pdf
37. Noria Corporation. Cavitation or Aeration? How to Tell the Difference. Machinery Lubrication, 2017. https://www.machinerylubrication.com/Read/30768/cavitation-or-aeration
38. Noria Corporation. Troubleshooting Hydraulic Pumps. Machinery Lubrication, 2018. https://www.machinerylubrication.com/Read/31064/troubleshooting-hydraulic-pumps
39. Data Physics. Dynamic Signal Analysis Review – Part 3: Aliasing. https://dataphysics.com/blog/dynamic-signal-analysis/dynamic-signal-analysis-review-part-3-aliasing/
40. Nasby, G. Introduction to the ISA 18.2 Alarm Management Standard(교육 슬라이드), 2013. https://www.grahamnasby.com/files_publications/NasbyG_2013_IntroToAlarmMgmt_YorkRegion_oct2013_slides.pdf
