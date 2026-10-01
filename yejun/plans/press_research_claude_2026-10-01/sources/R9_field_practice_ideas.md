# R9 — 산업 현장의 오경보 저감 관행, 타 분야 교훈, 아이디어 목록

- 작성: R9 리서치 에이전트, 2026-10-01
- 대상 과제: ③ 진동·전류 시계열 기반 프레스 유압펌프 이상 조기탐지 및 오경보 분석 (KAMP 소성가공 예지보전 데이터)
- 독립성: `yejun/` 폴더와 저장소 git 기록은 열지 않았다. 데이터 파일도 열지 않았다. 데이터 관련 수치는 호출자가 준 요약(정상 20,000행·약 599 burst·00:00–01:17 약 77분, 이상 600행·21 burst, 10 Hz, burst당 최대 50샘플)만 썼다.
- 검증 표기
  - **[열람-전문]**: 원문 PDF·웹 본문(또는 표준의 공식 미리보기)을 직접 읽음 = "opened"
  - **[열람-초록]**: 공식 초록·서지 페이지(Europe PMC/PubMed, Crossref, OpenAlex, 출판사·기관 페이지)를 직접 확인 = "opened(abstract)"
  - **[검색만]**: 서지사항만 확인(Crossref 등)했거나 검색 결과 요약으로만 확인 = "search-only". 내용 주장은 약하게만 쓴다.
  - **[미검증]**: 접근 실패 = "unverified"
- 등급: A = 동료심사 학술지·주요 학회·국제/국가 표준·정부/공공기관, B = 평판 있는 프리프린트·기술보고서·학위논문·제조사 기술문서·업계 협회 지침, C = 블로그·포럼·벤더 마케팅(가리키기만 하고 근거로 쓰지 않음)
- 방법 메모: 세션의 WebSearch 할당량(200회)이 중간에 바닥나서, 그 뒤로는 Crossref·Europe PMC·OpenAlex API와 직접 URL 접근으로 서지·초록을 확인했다. 받은 원문은 `scratchpad/research/r9src/`에 텍스트로 남겼다(작업용).
- 호출자 전제 정정
  1. Saxena et al.(2008, 2010)의 예지 성능 지표 논문은 NIST가 아니라 **NASA Ames**(Prognostics Center of Excellence) 저자다. NIST 쪽 PHM 문헌은 Vogl·Weiss·Helu(2019), Thomas·Weiss(2020, 2021)다.
  2. Vogl, Weiss & Helu는 2016년 온라인 공개, J Intell Manuf 30(1):79–95(2019) 수록이다.

---

## 1. 핵심 요약

1. **현장 표준은 오경보를 과제 정의와 같은 말로 정의한다.** ISO 17359:2018 §8.4는 "파라미터 변화가 고장 때문인지, duty·운전조건 변화 때문인지 판단하는 것이 중요하다"고 쓴다. 과제의 오경보("정상 운전 변화를 이상으로 판단") 바로 그것이다. 공통 해법은 **운전조건 조건부 기준선(regime-aware / normal behaviour model)**과 **동적 임계값**이다. 발전소 급수펌프 유량 경보를 펌프 전류에 비례하는 동적 trip point로 바꿔 오경보를 없앤 사례(Wang et al. 2016, IEEE T-ASE)와, 교량 고유진동수를 온도 조건부로 모델링해 "정상 변화는 경보를 울리면 안 된다"고 한 Z24 사례(Peeters & De Roeck 2001)가 직접적인 선례다. 우리 데이터에서는 **전류를 부하 대리변수로 삼아 진동 기준선을 조건화**하는 것이 가장 근거가 탄탄한 오경보 저감책이다.
2. **오경보의 상당수는 기계가 아니라 계측 문제다.** 임상 감시장치 경보 255만 건 중 31%(791,632건)가 기술 경보였고(Drew 2014), Joint Commission은 전극 건조·센서 위치 오류를 비조치 경보의 원인으로 꼽았다(SEA #50, 2013). 유압 상태감시에서도 오프셋·드리프트·노이즈·스파이크 센서 결함이 분류를 망가뜨린다(Helwig 2015; Adams 2025). 그래서 **센서 검증(signal-quality) 층을 기계 이상 판정 앞에 두고, "계측 의심"을 별도 범주로** 보고하는 것을 제안한다. 이 범주를 조용히 묻어 두면 안 되고, 우선순위가 낮은 정비 요청으로 남겨야 한다.
3. **지속성·지연·히스테리시스는 가장 값싼 오경보 저감책이지만 대가가 있다.** ICU에서 19초 지연을 두면 무시·무효 경보의 67%가 사라진다고 추정됐고(Görges 2009), 소아 병동은 지연·임계값 맞춤·전극 교체로 환자·일당 경보를 180건에서 40건으로 줄였다(Dandoy 2014). 대가는 탐지 지연이다. FAR(오경보율)–MAR(놓친 경보율)–AAD(평균 경보 지연) 세 지표의 트레이드오프로 설계해야 한다(Xu 2012). 반대로 Western Electric식 run rule을 덧붙이면 오경보가 늘어난다. 정상 상태 평균 런 길이(ARL₀)가 370에서 166으로 떨어진다(Champ & Woodall 1987, CRAN `spc` 재현값).
4. **경보 피로의 정량 근거는 강하지만 일방적이지는 않다.** 임상 경보의 72–99%가 거짓이거나 비조치이고(Sendelbach & Funk 2013), 비조치 경보에 많이 노출될수록 반응이 느려졌다(Bonafide 2015). 실험에서도 오경보형 자동화는 놓침형보다 전체 성과를 더 해쳤다(Dixon 2007). 사람은 경보 신뢰도에 맞춰 반응률을 맞추는 "확률 매칭"을 보인다(Bliss 1995). **반론**도 있다. 항공관제 충돌경보는 45%가 오경보였지만 cry-wolf 행동이 없었고(Wickens 2009), 대중 토네이도 경보의 근거도 엇갈린다(Lim 2019). 운영자가 경보의 맥락을 이해할 때는 피로가 줄어든다.
5. **운영자 표시의 근거.** 이진 경보보다 **가능도 경보(likelihood alarm)에 원자료 교차확인을 붙인 쪽**이 신뢰·준수·성과 모두에서 좋았다(Wiczorek & Manzey 2014). **권고와 불확실성을 함께 주는 것**이 최선이었고, 범주형 권고만으로는 결정이 나아지지 않았다(Joslyn & LeClerc 2012). AI 설명만 덧붙이면 정답 여부와 관계없이 수용률만 올라갔다(Bansal 2021). 그러니 확신도, 근거 원자료, 대응 체크리스트를 중심으로 설계한다.
6. **우리 데이터로 환산한 "경보 예산".** burst는 분당 약 7.8개(599/77)다. 8시간 교대 한 번이면 약 3,734 burst다. 교대당 오경보 1회 이하를 원하면 burst당 FPR이 약 0.027% 이하여야 한다(독립 가정). 정상 599 burst에서 FP가 0건이어도 95% 상한 FPR은 약 0.50%다(rule of three). 그러면 교대당 오경보가 최대 약 19회까지 가능하다. 20% 홀드아웃(약 120 burst)만으로 FP 0을 보였다면 상한은 교대당 약 92회다. **"테스트 FP 0건"은 현장 허용성을 증명하지 못한다.** 이것을 보고서에 정직하게 쓰는 것 자체가 차별점이 된다.
7. **"이상 확률"은 기저율에 묶여 있다.** 학습 데이터의 이상 비율은 burst 기준 3.4%(21/620)다. 현장 기저율이 10⁻⁴라면 모델의 0.9는 약 0.025, 0.99는 약 0.22로 바뀐다(Saerens 2002, Elkan 2001의 사전확률 보정). 확률은 기저율 시나리오별로 제시하고, 조치 임계값은 비용비로 정한다: **p* = C_I / (C_U − C_P)** (점검비용 ÷ 조기발견으로 피하는 손실). 기상 예보의 cost-loss 모형(Murphy 1977; Richardson 2000)과 임상의 decision curve(Vickers & Elkin 2006)가 같은 틀이다.
8. **평가의 함정.** point-adjust 평가는 무작위 점수도 SOTA로 만든다(Kim 2022, AAAI). 이상 사건이 하나뿐이면 사건 단위 recall은 통계적으로 식별되지 않는다(1/1의 95% CI 하한 2.5%). 가이드북 정확도 97.51%는, 같은 비율로 평가했다면 "전부 정상" 기준선 97.09%보다 0.42%p 높을 뿐이다(가이드북의 분할 방식은 미확인). 보완책은 **합성 결함 주입(dose–response)**, 사건·시간 기반 지표, **음성 대조(negative control)·Clever-Hans 점검**이다.
9. **배포 교훈.** 임상 AI의 silent trial(예측을 숨긴 그림자 운영)에서 개발 AUC 0.90이 분포 이동 때문에 0.50으로 떨어졌다(Kwong 2022). 널리 쓰인 Epic Sepsis Model은 외부 검증에서 입원의 18%에 경보를 내면서 패혈증의 67%를 놓쳤다(Wong 2021). 정비에서는 조치하면 예측이 맞았는지 검증할 수 없다("paradox of prognostics", Saxena 2010). **그림자 운영 → 경보 예산 충족 확인 → 단계적 가동**, 그리고 조치 전 상태를 남기는 **as-found 기록**이 필요하다.
10. **경제성 숫자는 고르게 써야 한다.** NIST 설문(Thomas & Weiss 2021, n=71)에서 반응정비 의존도가 낮은 절반은 계획외 정지가 52.7%, 결함이 78.5% 적었다. 다만 저자 스스로 "일화적 증거(anecdotal)"라고 했다. DOE FEMP 가이드의 "ROI 10배, 정지 35–45% 감소"는 출처가 불명확한 "independent surveys"에 기댄다. 벤더 다운타임 통계는 C등급이라 근거로 쓰면 안 된다. 우리 프레스 라인의 기대값 모형은 **비용 변수를 두고 민감도 분석**으로 제시하는 것이 정직하다.

---

## 2. 출처 표

열 설명: 검증(위 표기), 등급(A/B/C), 사용 위험 = 공개 경진대회 보고서에 근거로 쓸 때의 위험(낮음/중간/높음).

### 2.1 PdM 관행·표준·상태감시

| ID | 출처 (전체 인용) | 유형·등급 | 검증 | 이 보고서에서 쓰는 핵심 | 적신호·라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S01 | Vogl, G.W., Weiss, B.A., Helu, M. (2019). A review of diagnostic and prognostic capabilities and best practices for manufacturing. *J. Intelligent Manufacturing* 30(1):79–95. doi:10.1007/s10845-016-1228-8 | 리뷰 논문, A (NIST) | 열람-초록 (NIST 페이지) | PHM에는 개방형 아키텍처, 비용편익 분석, 방법 V&V, 표준이 유익하다 | 2016 온라인; Springer 저작권 | 낮음 |
| S02 | Thomas, D.S., Weiss, B.A. (2021). Maintenance Costs and Advanced Maintenance Techniques in Manufacturing Machinery: Survey and Analysis. *Int. J. Prognostics and Health Management* 12(1). doi:10.36001/ijphm.2021.v12i1.2883 | 학술지·설문, A | 열람-전문 (p.1–10) | 총 비용·손실 평균 $222.0B(2016), 계획외 정지 손실 $18.1B(90% CI 10.4–27.8); 반응정비 의존 하위 50%는 계획외 정지 52.7%↓·결함 78.5%↓; 예측 > 예방: 정지 18.5%↓·결함 87.3%↓ | n=71, 저자가 "anecdotal evidence"로 명시; CC BY 3.0 US | 낮음(단서 병기 필수) |
| S03 | Thomas, D.S., Weiss, B.A. (2020). Economics of Manufacturing Machinery Maintenance: A Survey and Analysis of U.S. Costs and Benefits. NIST AMS 100-34. doi:10.6028/NIST.AMS.100-34 | 정부 보고서, A | 열람-초록 | 2016년 미국 이산제조 정비비+예방가능 손실 $193.6B | 미국 정부 저작물 | 낮음 |
| S04 | U.S. DOE FEMP (2010). *Operations & Maintenance Best Practices Guide, Release 3.0*, Ch.5 Types of Maintenance Programs (PNNL 작성). https://www1.eere.energy.gov/femp/pdfs/om_5.pdf | 정부 가이드, A(문서)/수치는 B–C | 열람-전문 (5장) | 예방 vs 반응 12–18% 절감, 예측 vs 예방 8–12%; "independent surveys": ROI 10배, 정비비 25–30%↓, 고장 70–75% 제거, 정지 35–45%↓, 생산 20–25%↑ | **수치 출처 불명** ("independent surveys indicate"); 공공영역 | 중간–높음(정의 인용만) |
| S05 | ISO 13374-1:2003. Condition monitoring and diagnostics of machines — Data processing, communication and presentation — Part 1: General guidelines | 국제표준, A | 열람-전문 (iTeh 공식 미리보기 §2) | 6블록(DA, DM, SD, HA, PA, AG). DA는 "data quality" 포함, SD는 정상 기준 "profiles"와 "alert/alarm" 이상구역, 표시에는 고장유형·심각도·전망·권고조치(+비용·위험), 과거 평가 감사 | 유료·저작권, 미리보기 범위만 | 낮음 |
| S06 | ISO 17359:2018. Condition monitoring and diagnostics of machines — General guidelines | 국제표준, A | 열람-전문 (미리보기 §8.4–8.8) | §8.4 같은 운전조건에서 기준선 비교, 고장과 운전조건 변화 구별; §8.5 LTTF(lead time to failure); §8.6 수집률; §8.7 운전조건·단위 기록 | 유료 | 낮음 |
| S07 | ISO/FDIS 13379-1:2025 (2판; ISO 13379-1:2012 대체). Condition monitoring and diagnostics of machine systems — Data interpretation and diagnostics techniques — Part 1 | 국제표준 초안, A | 열람-전문 (미리보기: 서문·목차) | 이상 = "기준값 또는 예상 운전조건으로부터의 편차", 기준과 비교해 경보; FMSA와 MPN(5.3.4), 진단 confidence(7.5, Annex H), 데이터 기반 방법(Annex E) | FDIS(최종안). MPN 산식 세부는 [검색만] | 낮음–중간 |
| S08 | Saxena, A., Celaya, J., Saha, B., Saha, S., Goebel, K. (2010). Metrics for Offline Evaluation of Prognostic Performance. *IJPHM* 1(1). doi:10.36001/ijphm.2010.v1i1.1336 | 학술지, A (NASA Ames) | 열람-전문 | "paradox of prognostics": 예측대로 조치하면 예측이 맞았는지 검증할 기회가 사라진다; 진단 지표(FP/FN, ROC)와 비용편익 지표 | IJPHM 오픈액세스 | 낮음 |
| S09 | Saxena, A. et al. (2008). Metrics for evaluating performance of prognostic techniques. *IEEE PHM 2008*, Denver | 학회, A | 검색만 | 예지 지표 체계(원전) | — | 낮음 |
| S10 | Saxena, A., Goebel, K., Simon, D., Eklund, N. (2008). Damage propagation modeling for aircraft engine run-to-failure simulation. *IEEE PHM 2008*. doi:10.1109/PHM.2008.4711414 | 학회, A | 열람-초록 | C-MAPSS: health index = 여러 운전 여유의 최솟값 | — | 낮음 |
| S11 | Lei, Y. et al. (2018). Machinery health prognostics: A systematic review from data acquisition to RUL prediction. *MSSP* 104:799–834. doi:10.1016/j.ymssp.2017.11.016 | 리뷰, A | 검색만 | HI 구성·평가 리뷰(참고) | — | 낮음 |
| S12 | Tautz-Weinert, J., Watson, S.J. (2017). Using SCADA data for wind turbine condition monitoring – a review. *IET Renewable Power Generation* 11(4):382–394. doi:10.1049/iet-rpg.2016.0248 | 리뷰, A | 열람-초록 | 접근법 분류: trending, clustering, **normal behaviour modelling**, damage modelling, 경보·전문가시스템 평가 | — | 낮음 |
| S13 | Schlechtingen, M., Santos, I.F. (2011). Comparative analysis of neural network and regression based condition monitoring approaches for wind turbine fault detection. *MSSP* 25(5):1849–1875. doi:10.1016/j.ymssp.2010.12.007 | 학술지, A | 검색만 | NBM 비교(참고) | — | 낮음 |
| S14 | Bangalore, P., Tjernberg, L.B. (2015). An artificial neural network approach for early fault detection of gearbox bearings. *IEEE Trans. Smart Grid* 6(2):980–987. doi:10.1109/TSG.2014.2386305 | 학술지, A | 열람-초록 | SCADA 기반 ANN 정상모델로 기어박스 베어링 손상 조기 표시 | 경보 지속성 규칙 세부는 미확인 | 낮음 |
| S15 | Bartelmus, W., Zimroz, R. (2009). A new feature for monitoring the condition of gearboxes in non-stationary operating conditions. *MSSP* 23(5):1528–1534. doi:10.1016/j.ymssp.2009.01.014 | 학술지, A | 검색만 | 비정상 운전조건(부하 변동)용 특징(제목 수준) | 내용 미확인 | 중간 |
| S16 | Peeters, B., De Roeck, G. (2001). One-year monitoring of the Z24-Bridge: environmental effects versus damage events. *Earthquake Eng. Struct. Dyn.* 30(2):149–171 | 학술지, A | 열람-초록 | 정상 변화(온도)는 경보를 울리면 안 됨(=FP); 고유진동수를 온도 함수로 모델링, 신뢰구간 밖이면 다른 원인(손상) | 타 분야(구조) | 낮음–중간 |
| S17 | Sohn, H. (2007). Effects of environmental and operational variability on structural health monitoring. *Phil. Trans. R. Soc. A* 365(1851):539–560. doi:10.1098/rsta.2006.1935 | 리뷰, A | 열람-초록 | 환경·운전 변동이 손상 신호를 가림 → data normalization으로 분리 | 타 분야 | 낮음–중간 |
| S18 | Cross, E.J., Worden, K., Chen, Q. (2011). Cointegration: a novel approach for the removal of environmental trends in SHM data. *Proc. R. Soc. A* 467:2712–2732 | 학술지, A | 검색만 | 환경 추세 제거(대안 기법) | — | 중간 |
| S19 | Helwig, N., Pignanelli, E., Schütze, A. (2015). Condition monitoring of a complex hydraulic system using multivariate statistics. *IEEE I2MTC 2015*, 210–215. doi:10.1109/I2MTC.2015.7151267 | 학회, A | 열람-초록 | 유압 시험대 결함 분류(특징 상관+LDA), 무작위 부하 사이클에는 특징 추세 분포 분석으로 개선 | — | 낮음 |
| S20 | Helwig, N., Pignanelli, E., Schütze, A. (2015). D8.1 Detecting and Compensating Sensor Faults in a Hydraulic Condition Monitoring System. *SENSOR 2015*, 641–646. doi:10.5162/sensor2015/D8.1 | 학회 논문집, B | 열람-초록 (AMA 페이지) | 센서 결함(constant offset, drift, noise, signal peaks)을 탐지·보상; 센서 간 상관으로 최대 5개 센서 고장까지 보상 | 세부 수치 미확인 | 낮음–중간 |
| S21 | Helwig, N., Pignanelli, E., Schütze, A. (2015). Condition Monitoring of Hydraulic Systems [Dataset]. UCI ML Repository. doi:10.24432/C5CW21 | 공개 데이터, B | 열람-전문 (UCI 페이지) | 2,205 사이클×60 s; 압력·모터전력 100 Hz, 진동 1 Hz; 내부 펌프 누설 등 4개 부품 상태 | **CC BY 4.0**; 외부 데이터 사용 시 사유·방법·출처 명시 | 중간 |
| S22 | Adams, S. et al. (2025). The Impact of Sensor Faults on Condition Monitoring of a Hydraulic Actuator. *Annual Conf. PHM Society* 17(1). doi:10.36001/phmconf.2025.v17i1.4415 | 학회, A/B | 열람-초록 | 결함 센서 데이터가 모델 성능을 떨어뜨림; 일부 특징은 특정 결함에 강건, 앙상블이 더 강건; **결함 주입 오픈소스 패키지** 공개 | CC BY 3.0 | 낮음 |
| S23 | Di Maio, F., Baraldi, P., Zio, E., Seraoui, R. (2013). Fault detection in nuclear power plants components by a combination of statistical methods. *IEEE Trans. Reliability* 62(4):833–845. doi:10.1109/TR.2013.2285033 | 학술지, A | 열람-초록 | 원자로냉각재**펌프** 46개 신호, AAKR 재구성 + **SPRT**로 경보 수준 설정, 오경보·놓침 균형, SPRT 파라미터 지침 | — | 낮음 |
| S24 | Coble, J.B. et al. (2012). A Review of Sensor Calibration Monitoring for Calibration Interval Extension in Nuclear Power Plants. PNNL (OSTI). doi:10.2172/1061413 | 정부 연구소 보고서, A/B | 열람-초록 | 온라인 감시로 교정이 필요한 센서만 식별; NRC가 2000년 개념 승인; Sizewell B 센서는 8년 이상 교정 허용치 유지 | 공공영역 | 낮음 |
| S25 | Khan, S., Phillips, P., Jennions, I., Hockley, C. (2014). No Fault Found events in maintenance engineering Part 1. *Reliability Eng. & System Safety* 123:183–195. doi:10.1016/j.ress.2013.11.003 | 리뷰, A | 열람-초록 | NFF(정상 부품 탈거, 원인 미확인)의 조직·인적요인, 비용·안전 영향 | — | 낮음 |
| S26 | Steenwinckel, B. et al. (2021). FLAGS: adaptive anomaly detection and root cause analysis on sensor data streams by fusing expert knowledge with ML. *Future Generation Computer Systems* 116:30–48. doi:10.1016/j.future.2020.10.015 | 학술지, A | 열람-초록 | 전문가 지식과 ML 융합, 제한된 사용자 피드백으로 적응; 열차 PdM 사례에서 정지시간 감소 | CC BY | 낮음 |
| S27 | Holtz, D. et al. (2025). A data-efficient active learning architecture for anomaly detection in industrial time series data. *Flexible Services and Manufacturing J.* 38(2):618–649. doi:10.1007/s10696-024-09588-0 | 학술지, A | 열람-초록 | 예산 제한 전문가 피드백(능동학습)으로 비지도 대비 **F1 59% 향상**; 에너지(전류계) 데이터만으로 기계 공정 데이터와 동등 | CC BY; 나사 체결 로봇 사례(타 설비) | 낮음–중간 |
| S28 | Das, S., Wong, W.-K., Dietterich, T., Fern, A., Emmott, A. (2016). Incorporating Expert Feedback into Active Anomaly Discovery. *IEEE ICDM*, 853–858 | 학회, A | 열람-초록 | "모든 이상치가 이상은 아니고, 모든 이상이 이상치도 아니다"; 전문가 라벨로 검출기 조정 | — | 낮음 |
| S29 | Siddiqui, M.A. et al. (2018). Feedback-Guided Anomaly Discovery via Online Optimization. *KDD*, 2200–2209 | 학회, A | 검색만 | 피드백 기반 이상 탐지(참고) | — | 낮음 |
| S30 | Isermann, R. (2005). Model-based fault-detection and diagnosis – status and applications. *Annual Reviews in Control* 29(1):71–85 | 리뷰, A | 검색만 | 모델 기반 FDI 개관(참고) | — | 낮음 |
| S31 | Frank, P.M., Ding, X. (1997). Survey of robust residual generation and evaluation methods in observer-based fault detection systems. *J. Process Control* 7(6):403–424 | 리뷰, A | 검색만 | 잔차 평가·적응 임계값(참고) | 내용 미확인 | 중간 |
| S32 | Chow, E.Y., Willsky, A.S. (1984). Analytical redundancy and the design of robust failure detection systems. *IEEE TAC* 29(7):603–614 | 학술지, A | 검색만 | 해석적 중복성(센서 간 관계로 고장 검출) 개념 원전 | — | 낮음 |
| S33 | Malhotra, P. et al. (2016). LSTM-based Encoder-Decoder for Multi-sensor Anomaly Detection. arXiv:1607.00148 (ICML 2016 Anomaly Detection Workshop) | 프리프린트, B | 열람-초록 | 정상만으로 재구성 학습, 재구성 오차로 이상 탐지; 길이 30짜리 짧은 시계열에도 적용 | 가이드북 LSTM-AE 계열의 원형 | 낮음 |
| S34 | Liu, F.T., Ting, K.M., Zhou, Z.-H. (2008). Isolation Forest. *IEEE ICDM*, 413–422 | 학회, A | 검색만 | 기준선 후보 | — | 낮음 |

### 2.2 경보 관리(공정·항공·원자력)

| ID | 출처 | 유형·등급 | 검증 | 핵심 | 적신호·라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S35 | UK HSE (2000-03). *Better alarm handling*. HSE Information Sheet, Chemicals Sheet No 6 (CHIS6) | 규제기관 지침, A | 열람-전문 (humanfactors101.com 사본) | Milford Haven(1994): 폭발 전 마지막 11분간 운전원 2명이 **275개 경보** 처리; 경보 과다·우선순위 불량. EEMUA 목표: 정상운전 평균 10분당 1건 이하, 대형 이상 후 첫 10분 10건 이하; 우선순위 약 3단계(5/15/80%); 모든 경보에 정의된 대응; 즉효책: 대응 없는 경보 제거, nuisance 경보 설정 조정, **deadband 조정**, 정지 설비 경보 억제 | 사본 사이트; "상업 목적 외 자유 복제, 출처 HSE 표기" | 낮음 |
| S36 | Stauffer, T., Sands, N.P., Dunn, D.G. (2010). Alarm Management and ISA-18 – A Journey, Not a Destination. Texas A&M Instrumentation Symposium (exida) | 업계 학회 논문, B (벤더 소속 저자) | 열람-전문 | **ISA-18.2-2009 성과지표 표 인용**: 운전위치당 하루 약 150건 "매우 수용 가능", 약 300건 "최대 관리 가능"; 시간당 약 6/12건; 10분당 약 1/2건; 10건 초과 10분 구간 1% 미만; chattering 0건; 우선순위 80/15/5%. Rationalization 단계는 결과, 대응시간, 운전원 조치 문서화 | 초록의 "$20B 생산손실"은 벤더형 수치(C) | 낮음(표 수치) / 높음($ 수치) |
| S37 | ISA. ANSI/ISA-18.2-2016 *Management of Alarm Systems for the Process Industries* 및 TR18.2.1–.8 (ISA 웹 페이지) | 표준, A | 열람-초록 (ISA 페이지만, 본문 미열람) | 수명주기(식별–rationalization–구현–유지–변경관리); TR18.2.6 *Batch and Discrete Processes*, TR18.2.8 *Non-Alarm Notifications* 존재 | 유료 | 낮음 |
| S38 | IEC 62682 Management of alarm systems for the process industries | 국제표준, A | 미검증 | ISA-18.2의 국제판으로 알려짐(Wang 2016이 IEC 경보관리 표준으로 언급) | 판·연도 미확인 | 중간 |
| S39 | EEMUA Publication 191, *Alarm systems: a guide to design, management and procurement* (HSE 시트는 1999년판 인용) | 업계 지침, B | 간접 확인 (S35, S40 인용) | 경보율 기준, 하루 144건 이하(Wang 2016 인용) | 유료, 최신판 미확인 | 낮음–중간 |
| S40 | Wang, J., Yang, F., Chen, T., Shah, S.L. (2016). An overview of industrial alarm systems: main causes for alarm overloading, research status, and open problems. *IEEE T-ASE* 13(2):1045–1061. doi:10.1109/TASE.2015.2464234 | 리뷰, A | 열람-전문 (저자 사본) | 경보 과부하 4대 원인: 노이즈·외란에 의한 chattering, 경보 변수 설정 오류, **관련 변수와 고립된 경보 설계**, 이상 전파. **예 4**: 급수펌프 유량 고경보는 운전원 수요 때문 → 펌프 전류에 비례하는 **동적 trip point**와 상태 기반 경보로 제거. 15개 플랜트 정상 10분당 2–33건, 이상 시 최고 72–625건 | 저자 사본; IEEE 저작권 | 낮음 |
| S41 | Xu, J., Wang, J., Izadi, I., Chen, T. (2012). Performance assessment and design for univariate alarm systems based on FAR, MAR, and AAD. *IEEE T-ASE* 9(2):296–307. doi:10.1109/TASE.2011.2176490 | 학술지, A | 열람-초록 | FAR, MAR, AAD 세 지표로 trip point·on/off 지연 경보를 평가·설계, 트레이드오프 | — | 낮음 |
| S42 | Adnan, N.A., Izadi, I., Chen, T. (2011). On expected detection delays for alarm systems with deadbands and delay-timers. *J. Process Control* 21(9):1318–1331. doi:10.1016/j.jprocont.2011.06.019 | 학술지, A | 검색만 | deadband·delay-timer의 탐지 지연 계산(참고) | — | 낮음 |
| S43 | Kondaveeti, S.R. et al. (2013). Quantification of alarm chatter based on run length distributions. *Chem. Eng. Res. Des.* 91(12):2550–2558 | 학술지, A | 검색만 | chattering 지수(참고) | — | 낮음 |
| S44 | 14 CFR §25.1322 Flightcrew alerting (Amdt. 25-131, 75 FR 67209, 2010-11-02), eCFR | 미국 연방규정, A | 열람-전문 | 경보는 비정상 식별과 **적절한 조치 결정**에 필요한 정보 제공; 조건 해소 시 제거; 위계: **Warning**(즉시 인지·즉시 대응) / **Caution**(즉시 인지·후속 대응) / **Advisory**(인지·후속 대응 가능); (d) **오경보·nuisance 경보의 영향을 최소화**하도록 설계, 억제 시 억제 사실을 분명히 표시 | 공공영역 | 낮음 |
| S45 | FAA AC 25.1322-1 Flightcrew Alerting (2010) | 정부 지침, A | 미검증 (403) | 세부 해설 | — | — |
| S46 | Brown, W.S., O'Hara, J.M., Higgins, J.C. (2000). *Advanced Alarm Systems: Revision of Guidance and Its Technical Basis*. NUREG/CR-6684, U.S. NRC (BNL) | 정부 보고서, A | 열람-초록 (NRC 페이지) | 원전 경보 HFE 검토 지침 개정 근거, NUREG-0700 Rev.2에 반영 | 세부 경보처리 기법은 미열람 | 낮음 |
| S47 | Wickens, C.D. et al. (2009). False alerts in air traffic control conflict alerting system: is there a "cry wolf" effect? *Human Factors* 51(4):446–462 | 학술지, A | 열람-초록 | 충돌경보 495건 중 **45% 오경보**(센터별 0.28–0.58)였지만 cry-wolf 증거 없음; 관제사가 경보 전에 선제 조치 | **반례** | 낮음 |
| S48 | Degani, A., Wiener, E.L. (1993). Cockpit checklists: concepts, design, and use. *Human Factors* 35(2):345–359 | 학술지, A | 검색만 | 체크리스트 설계 원칙(참고) | — | 낮음 |

### 2.3 타 분야 경보 피로(임상·기상·보안)·배포 교훈

| ID | 출처 | 유형·등급 | 검증 | 핵심 | 적신호·라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S49 | The Joint Commission (2013-04-08). Sentinel Event Alert, Issue 50: Medical device alarm safety in hospitals | 인증기관 경보, A | 열람-전문 | 2009.1–2012.6 경보 관련 98건 중 **사망 80**, 영구 기능상실 13; 경보 신호의 85–99%가 임상 개입 불필요(설정 과민, 기본값 미조정, **ECG 전극 건조, 센서 위치 오류**); 권고: 설정 지침, 맞춤 한계, 일회용 센서 교체 | 자발 보고(역학 자료 아님); "**전체로만 복제 가능**" → 짧은 인용·요약만 | 낮음–중간(타 분야) |
| S50 | Sendelbach, S., Funk, M. (2013). Alarm fatigue: a patient safety concern. *AACN Adv. Crit. Care* 24(4):378–386 | 리뷰, A | 열람-초록 | 연구들에서 임상 경보의 **72–99%가 거짓**; 전극 매일 교체, 피부 준비, 교육, 설정 맞춤으로 감소 | 문헌 범위값 | 중간 |
| S51 | Drew, B.J. et al. (2014). Insights into the problem of alarm fatigue with physiologic monitor devices. *PLOS ONE* 9(10):e110274 | 관찰연구, A | 열람-초록 | 461명, 31일, 경보 **2,558,760건**(부정맥 1,154,201, 파라미터 612,927, **기술 791,632**); 주석 부정맥 경보 12,671건 중 **88.8% 위양성**; 진짜 VT 경보 168건 중 93%는 치료할 만큼 지속되지 않음; 권고: 모든 유도 활용, 맞춤 설정, AF는 시작·종료만 경보, 지연 설정 | **CC BY 4.0** | 중간 |
| S52 | Bonafide, C.P. et al. (2015). Association between exposure to nonactionable physiologic monitor alarms and response time in a children's hospital. *J. Hosp. Med.* 10(6):345–351 | 관찰(비디오), A | 열람-초록 | 간호사 36명, 210시간, 경보 5,070건; 비조치 PICU 87.1%·병동 99.0%; 직전 120분 비조치 경보 노출이 많을수록 반응시간 증가(p<0.001, p=0.009) | 소아 1개 병원 | 중간 |
| S53 | Paine, C.W. et al. (2016). Systematic review of physiologic monitor alarm characteristics and pragmatic interventions to reduce alarm frequency. *J. Hosp. Med.* 11(2):136–144 | 체계적 문헌고찰, A | 열람-초록 | 관찰연구 24편 + 중재연구 8편; 조치 가능 비율 1% 미만–36%; 유망하지만 미입증인 중재: 경보 범위 확대, **지연 도입**, 일회용 리드·잦은 전극 교체; 비뚤림 위험 큼 | — | 중간 |
| S54 | Görges, M., Markewitz, B.A., Westenskow, D.R. (2009). Improving alarm performance in the medical ICU using delays and clinical context. *Anesth. Analg.* 108(5):1546–1552 | 관찰, A | 열람-초록 | 200시간, 경보 1,214건(시간당 6.07); 유효 23%, 무효 36%, 무시 41%; 지속 중앙값 17 s; **14 s 지연이면 무시·무효 경보 50%, 19 s 지연이면 67% 제거**; 처치 활동 맥락 감지 결합 시 934→274 | 단일 기관 | 중간 |
| S55 | Graham, K.C., Cvach, M. (2010). Monitor alarm fatigue: standardizing use of physiological monitors and decreasing nuisance alarms. *Am. J. Crit. Care* 19(1):28–34 | QI 보고, A | 열람-초록 | 기본값 조정과 맞춤 한계로 위험 경보 **43% 감소** | 전후 비교 | 중간 |
| S56 | Dandoy, C.E. et al. (2014). A team-based approach to reducing cardiac monitor alarms. *Pediatrics* 134(6):e1686–e1694 | QI 보고, A | 열람-초록 | 표준 공정(연령별 기본값, 매일 전극 교체, 매일 개별 평가, 적절한 중단, **맞춤 지연·임계값**)으로 환자·일당 경보 중앙값 **180→40** | 전후 비교 | 중간 |
| S57 | Clifford, G.D. et al. (2016). False alarm reduction in critical care. *Physiol. Meas.* 37(8):E5–E23 (+ PhysioNet/CinC Challenge 2015 페이지) | 대회 편집논문, A | 열람-초록 (+ 대회 페이지 열람) | 1,250 구간(학습 750/시험 500); **참 경보 억제에 오경보 수용의 5배 벌점**; 38팀 215건 | 데이터 ODC-By 1.0 | 낮음–중간 |
| S58 | Plesinger, F. et al. (2016). Taming of the monitors: reducing false alarms in ICUs. *Physiol. Meas.* 37(8):1313–1325 | 학술지, A | 열람-초록 | 다중 신호(ECG+ABP/PPG) 기반, 실시간 민감도 93%·특이도 87% (후향 95%/88%) | — | 중간 |
| S59 | Wong, A. et al. (2021). External validation of a widely implemented proprietary sepsis prediction model in hospitalized patients. *JAMA Intern. Med.* 181(8):1065–1070 | 코호트, A | 열람-초록 | 38,455 입원, AUC 0.63; 입원의 18%(6,971)에 경보, 패혈증 67% 놓침 → **경보 피로 부담** | — | 중간 |
| S60 | Kwong, J.C.C. et al. (2022). The silent trial – the bridge between bench-to-bedside clinical AI applications. *Front. Digit. Health* 4:929508 | 사례·관점, A | 열람-초록 | 사용자에게 예측을 숨긴 전향 평가에서 **AUC 0.90→0.50**(연령·좌우·영상형식 분포 이동), 수정 후 0.85–0.91 | **CC BY** | 낮음 |
| S61 | Simmons, K.M., Sutter, D. (2009). False alarms, tornado warnings, and tornado casualties. *Weather, Climate, and Society* 1(1):38–53. doi:10.1175/2009WCAS1005.1 | 학술지, A | 검색만 (정성 결론은 S64 본문에서 확인) | 오경보율이 높은 지역의 토네이도가 사망·부상을 더 냄; 검색 요약에 따르면 오경보율 1 SD 증가 → 사망 12–29% 증가 | 수치는 스니펫 수준 | 중간 |
| S62 | LeClerc, J., Joslyn, S. (2015). The cry wolf effect and weather-related decision making. *Risk Analysis* 35(3):385–395 | 실험, A | 열람-전문 | 아주 높거나 아주 낮은 오경보율은 결정을 나쁘게 함; 오경보율을 조금 낮추는 것은 유의하지 않음; **확률적 불확실성 추정을 더하자 준수와 결정 품질이 모두 향상** | 강의용 사본(저작권 Wiley) | 낮음 |
| S63 | Joslyn, S., LeClerc, J. (2012). Uncertainty forecasts improve weather-related decisions and attenuate the effects of forecast error. *J. Exp. Psychol.: Applied* 18(1):126–140 | 실험, A | 열람-초록 | 불확실성 정보가 결정 품질·신뢰를 높임; **범주형 권고만으로는 개선 없음, 권고+불확실성 조합이 최선** | — | 낮음 |
| S64 | Lim, J.R., Liu, B.F., Egnoto, M. (2019). Cry Wolf Effect? Evaluating the Impact of False Alarms on Public Responses to Tornado Alerts in the Southeastern United States. *Weather, Climate, and Society* 11(3):549–563 | 설문, A | 열람-전문 (NOAA 저장소) | 미국 토네이도 경보의 평균 75%가 오경보; 4개 설문 N=4,162; 인지 오경보율과 실제 오경보율 무관, 실제 오경보율이 보호행동을 예측하지 못함 → 대중에서는 **cry-wolf 우려가 과장되었을 수 있음** | **반례** | 낮음 |
| S65 | Axelsson, S. (2000). The base-rate fallacy and the difficulty of intrusion detection. *ACM TISSEC* 3(3):186–205 | 학술지, A | 열람-전문 | 기저율이 낮으면 탐지율이 1.0이어도 **오경보율 약 1×10⁻⁵**이 되어야 경보의 66%가 진짜; 탐지율 0.7이면 약 58% | ACM 저작권 | 낮음 |
| S66 | Alahmadi, B.A., Axon, L., Martinovic, I. (2022). 99% False Positives: A Qualitative Study of SOC Analysts' Perspectives on Security Alarms. *USENIX Security*, 2783–2800 | 정성 연구, A | 열람-전문 | 설문 n=20, 인터뷰 n=21; FP 대부분은 **"benign trigger"**(정당한 활동이 설명하는 참 경보); 좋은 경보의 5속성: Reliable, Explainable, Analytical, Contextual, Transferable | 오픈액세스 | 낮음–중간 |

### 2.4 인간요인·HCI(확률·불확실성 표현, 설명, 체크리스트)

| ID | 출처 | 유형·등급 | 검증 | 핵심 | 적신호·라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S67 | Bliss, J.P., Gilson, R.D., Deaton, J.E. (1995). Human probability matching behaviour in response to alarms of varying reliability. *Ergonomics* 38(11):2300–2312 | 실험, A | 열람-초록 | n=138, 경보 신뢰도 25/50/75%; 약 90%가 신뢰도에 맞춰 반응(확률 매칭), 약 10%는 전부/전무 | 학생 표본 | 중간 |
| S68 | Dixon, S.R., Wickens, C.D., McCarley, J.S. (2007). On the independence of compliance and reliance: are automation false alarms worse than misses? *Human Factors* 49(4):564–572 | 실험, A | 열람-초록 | **오경보형 자동화가 놓침형보다 전체 성과를 더 해침**; 오경보는 compliance와 reliance 모두에 영향 | n=32 학생 | 중간 |
| S69 | Wickens, C.D., Dixon, S.R. (2007). The benefits of imperfect diagnostic automation: a synthesis of the literature. *Theor. Issues Ergon. Sci.* 8(3):201–212 | 메타종합, A | 검색만 | 검색 요약상 신뢰도 약 0.70 아래면 자동화가 없는 것보다 나쁨 | 0.70 수치 미확인 | 중간 |
| S70 | Sorkin, R.D., Kantowitz, B.H., Kantowitz, S.C. (1988). Likelihood alarm displays. *Human Factors* 30(4):445–459 | 실험, A | 열람-초록 | 가능도 정보를 경보 신호에 담으면 주의 배분이 나아지고 부하가 반드시 늘지는 않음 | — | 낮음 |
| S71 | Wiczorek, R., Manzey, D. (2014). Supporting attention allocation in multitask environments: effects of likelihood alarm systems on trust, behavior, and performance. *Human Factors* 56(7):1209–1221 | 실험, A | 열람-초록 | LAS가 이진 경보보다 신뢰·준수·성과 모두 높음; **원자료 교차확인 옵션과 결합할 때 최고** | — | 낮음 |
| S72 | Lee, J.D., See, K.A. (2004). Trust in automation: designing for appropriate reliance. *Human Factors* 46(1):50–80 | 리뷰, A | 열람-초록 | 적절한 의존을 위한 신뢰 보정(calibration) 개념 모형, 표시 특성의 역할 | — | 낮음 |
| S73 | Parasuraman, R., Riley, V. (1997). Humans and automation: use, misuse, disuse, abuse. *Human Factors* 39(2):230–253 | 리뷰, A | 검색만 (+ Lee 2008 회고 초록) | 과의존·과소의존 개념 | — | 낮음 |
| S74 | Gigerenzer, G., Hoffrage, U. (1995). How to improve Bayesian reasoning without instruction: frequency formats. *Psychol. Rev.* 102(4):684–704 | 실험·이론, A | 열람-초록 | 빈도 형식으로 제시하면 비전문가도 추론의 최대 50%를 베이즈식으로 함 | — | 낮음 |
| S75 | Galesic, M., Garcia-Retamero, R., Gigerenzer, G. (2009). Using icon arrays to communicate medical risks: overcoming low numeracy. *Health Psychol.* 28(2):210–216 | 실험, A | 열람-초록 | icon array가 수리력 낮은/높은 사람 모두의 이해 정확도를 높임 | — | 낮음 |
| S76 | Kay, M., Kola, T., Hullman, J., Munson, S. (2016). When (ish) is my bus? *CHI*, 5092–5103 | 실험, A | 열람-초록 | quantile dotplot 제안, 밀도 그림 대비 확률 추정 분산 약 1.15배 감소 | — | 낮음 |
| S77 | Fernandes, M. et al. (2018). Uncertainty displays using quantile dotplots or CDFs improve transit decision-making. *CHI* | 실험, A | 열람-초록 | 50점 quantile dotplot은 최적 보상의 97%, 대조군보다 5%p 높음; 텍스트 불확실성보다 우수 | — | 낮음 |
| S78 | Spiegelhalter, D., Pearson, M., Short, I. (2011). Visualizing uncertainty about the future. *Science* 333(6048):1393–1400 | 리뷰, A | 열람-초록 | 불확실성 시각화 관행 개관, 실험 근거는 제한적이라고 경고 | — | 낮음 |
| S79 | Zhang, Y., Liao, Q.V., Bellamy, R.K.E. (2020). Effect of confidence and explanation on accuracy and trust calibration in AI-assisted decision making. *FAT\**, 295–305 | 실험, A | 열람-초록 | **confidence score는 신뢰 보정에 도움**, 지역 설명(local explanation)은 문제가 있음 | — | 낮음 |
| S80 | Bansal, G. et al. (2021). Does the whole exceed its parts? The effect of AI explanations on complementary team performance. *CHI* | 실험, A | 열람-초록 | 설명이 팀 성과를 높이지 못했고, **정답 여부와 무관하게 AI 권고 수용만 늘림** | — | 낮음 |
| S81 | Buçinca, Z., Malaya, M.B., Gajos, K.Z. (2021). To trust or to think. *Proc. ACM HCI* 5(CSCW1) | 실험, A | 열람-초록 | N=199; cognitive forcing이 과의존을 유의하게 줄였지만 사용자 선호는 가장 낮음 | — | 낮음 |
| S82 | Haynes, A.B. et al. (2009). A surgical safety checklist to reduce morbidity and mortality in a global population. *NEJM* 360(5):491–499 | 전후 비교, A | 열람-초록 | 19항목 체크리스트 도입 후 사망 1.5%→0.8%, 합병증 11.0%→7.0% | 인과 해석 주의 | 중간(타 분야) |

### 2.5 평가·통계·ML 방법

| ID | 출처 | 유형·등급 | 검증 | 핵심 | 적신호·라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S83 | Kim, S., Choi, K., Choi, H.-S., Lee, B., Yoon, S. (2022). Towards a Rigorous Evaluation of Time-Series Anomaly Detection. *AAAI* 36(7):7194–7201 | 학회, A | 열람-초록 | **point adjustment(PA)는 성능을 과대평가**하며, 무작위 점수도 SOTA처럼 보이게 만듦; PA 없이도 학습 안 한 모델이 기존 방법과 비슷 | — | 낮음 |
| S84 | Wu, R., Keogh, E.J. (2021/2023). Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress. *IEEE TKDE*. doi:10.1109/TKDE.2021.3112126 | 학술지, A | 열람-초록 (arXiv) | 벤치마크의 4대 결함: 사소함(triviality), 비현실적 이상 밀도, 잘못된 라벨, **run-to-failure 편향** | — | 낮음 |
| S85 | Tatbul, N., Lee, T.J., Zdonik, S., Alam, M., Gottschlich, J. (2018). Precision and Recall for Time Series. *NeurIPS* (arXiv:1803.03639) | 학회, A | 열람-초록 | 구간 기반 precision/recall, 존재 보상, **앞쪽 가중(front-end bias)** | — | 낮음 |
| S86 | Lavin, A., Ahmad, S. (2015). Evaluating Real-Time Anomaly Detection Algorithms — the Numenta Anomaly Benchmark. *IEEE ICMLA*, 38–44 | 학회, A/B | 열람-초록 | 조기 탐지 보상과 오경보 벌점을 결합한 점수 | 점수 설계에 대한 비판 문헌 있음 | 중간 |
| S87 | Goswami, M., Challu, C., Callot, L., Minorics, L., Kan, A. (2023). Unsupervised Model Selection for Time-series Anomaly Detection. *ICLR* (arXiv:2210.01078) | 학회, A | 열람-초록 | 대리 지표: 예측오차, 모델 중심성, **합성 이상 주입 성능**; 라벨 없이도 일부 라벨로 고르는 것만큼 효과적 | — | 낮음 |
| S88 | Saito, T., Rehmsmeier, M. (2015). The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets. *PLOS ONE* 10(3):e0118432 | 학술지, A | 열람-초록 | 불균형 데이터에서는 ROC가 오해를 부를 수 있어 PR 곡선이 유리 | CC BY | 낮음 |
| S89 | Kapoor, S., Narayanan, A. (2023). Leakage and the reproducibility crisis in machine-learning-based science. *Patterns* 4(9):100804 | 학술지, A | 검색만 | 누수(leakage) 유형학(참고) | — | 낮음 |
| S90 | Geirhos, R. et al. (2020). Shortcut learning in deep neural networks. *Nature Machine Intelligence* 2(11):665–673 | 관점·리뷰, A | 검색만 | 지름길 학습(참고) | — | 낮음 |
| S91 | Lapuschkin, S. et al. (2019). Unmasking Clever Hans predictors and assessing what machines really learn. *Nature Communications* 10 | 학술지, A | 검색만 | Clever-Hans 예측기 점검(참고) | — | 낮음 |
| S92 | Lipsitch, M., Tchetgen Tchetgen, E., Cohen, T. (2010). Negative controls: a tool for detecting confounding and bias in observational studies. *Epidemiology* 21(3):383–388 | 방법론, A | 검색만 | 음성 대조로 교란 탐지(참고) | — | 낮음 |
| S93 | Bates, S., Candès, E., Lei, L., Romano, Y., Sesia, M. (2023). Testing for outliers with conformal p-values. *Annals of Statistics* 51(1). doi:10.1214/22-AOS2244 | 학술지, A | 열람-초록 (arXiv) | 정상 참조 데이터로 conformal p-value를 만들면 **정확한 FDR 통제**가 가능(약한 marginal 의미) | 교환가능성 가정 | 낮음 |
| S94 | Laxhammar, R., Falkman, G. (2015). Inductive conformal anomaly detection for sequential detection of anomalous sub-trajectories. *Ann. Math. Artif. Intell.* 74(1–2):67–94 | 학술지, A | 검색만 | conformal anomaly detection(참고) | — | 낮음 |
| S95 | Siffer, A., Fouque, P.-A., Termier, A., Largouët, C. (2017). Anomaly Detection in Streams with Extreme Value Theory. *KDD*, 1067–1075 | 학회, A | 열람-전문 (1쪽) | 분포 가정 없이 위험 q만으로 임계값 z_q 설정(P(X>z_q)<q) | **iid 가정** | 낮음–중간 |
| S96 | Champ, C.W., Woodall, W.H. (1987). Exact results for Shewhart control charts with supplementary runs rules. *Technometrics* 29(4):393–399 + CRAN `spc` 문서(xshewhartrunsrules.arl) | 학술지, A | 검색만 + 문서 열람 | ARL₀: Shewhart 370.40, +2-of-3 225.44, +4-of-5 166.05, +8연속 152.73 → **규칙을 더할수록 오경보 증가** | 전체 규칙 ARL은 미확인 | 낮음 |
| S97 | Nelson, L.S. (1984). The Shewhart control chart—tests for special causes. *J. Quality Technology* 16(4):237–239 | 학술지, A | 검색만 | Nelson 규칙(참고) | — | 낮음 |
| S98 | Lucas, J.M., Saccucci, M.S. (1990). Exponentially weighted moving average control schemes: properties and enhancements. *Technometrics* 32(1):1–12 | 학술지, A | 검색만 | EWMA 설계와 ARL(참고) | — | 낮음 |
| S99 | Page, E.S. (1954). Continuous inspection schemes. *Biometrika* 41(1–2):100–115 | 학술지, A | 검색만 | CUSUM 원전 | — | 낮음 |
| S100 | Westerhuis, J.A., Gurden, S.P., Smilde, A.K. (2000). Generalized contribution plots in multivariate statistical process monitoring. *Chemometr. Intell. Lab. Syst.* 51(1):95–114 | 학술지, A | 검색만 | MSPC 기여도 그림(참고) | — | 낮음 |
| S101 | Chow, C.K. (1970). On optimum recognition error and reject tradeoff. *IEEE Trans. Inf. Theory* 16(1):41–46 | 학술지, A | 검색만 | 판정 보류(reject option) 원전 | — | 낮음 |
| S102 | Lakshminarayanan, B., Pritzel, A., Blundell, C. (2017). Simple and scalable predictive uncertainty estimation using deep ensembles. *NeurIPS* (arXiv:1612.01474) | 학회, A | 열람-초록 | 앙상블 불확실성 | — | 낮음 |
| S103 | Niculescu-Mizil, A., Caruana, R. (2005). Predicting good probabilities with supervised learning. *ICML*, 625–632 | 학회, A | 열람-초록 | Platt vs isotonic 보정, 보정에 필요한 데이터 양 | — | 낮음 |
| S104 | Saerens, M., Latinne, P., Decaestecker, C. (2002). Adjusting the outputs of a classifier to new a priori probabilities: a simple procedure. *Neural Computation* 14(1):21–41 | 학술지, A | 열람-초록 | 학습과 현장의 사전확률이 다르면 사후확률을 보정해야 함 | — | 낮음 |
| S105 | Hanley, J.A., Lippman-Hand, A. (1983). If nothing goes wrong, is everything all right? Interpreting zero numerators. *JAMA* 249(13):1743–1745 | 학술지, A | 검색만 | rule of three(0/n이면 95% 상한 약 3/n) | — | 낮음 |
| S106 | Brier, G.W. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review* 78(1):1–3 | 학술지, A | 검색만 | Brier score 원전 | — | 낮음 |

### 2.6 의사결정·경제성

| ID | 출처 | 유형·등급 | 검증 | 핵심 | 적신호·라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S107 | Elkan, C. (2001). The Foundations of Cost-Sensitive Learning. *IJCAI-01*, 973–978 | 학회, A | 열람-전문 (저자 사본) | 비용행렬로 최적 결정 임계값 결정; §3 "새 기저율에서의 새 확률" | — | 낮음 |
| S108 | Vickers, A.J., Elkin, E.B. (2006). Decision curve analysis: a novel method for evaluating prediction models. *Med. Decis. Making* 26(6):565–574 | 방법론, A | 열람-초록 | 임계 확률은 FP와 FN 해악의 상대적 무게를 뜻함 → net benefit 곡선 | — | 낮음 |
| S109 | Richardson, D.S. (2000). Skill and relative economic value of the ECMWF ensemble prediction system. *QJRMS* 126(563):649–667 | 학술지, A | 열람-초록 | cost-loss 모형의 **상대적 경제가치**를 C/L 함수로; 확률 예보가 결정론 예보보다 가치 큼 | Wiley | 낮음 |
| S110 | Murphy, A.H. (1977). The value of climatological, categorical and probabilistic forecasts in the cost-loss ratio situation. *Monthly Weather Review* 105(7):803–816 | 학술지, A | 검색만 | cost-loss 원전 | — | 낮음 |

### 2.7 가리키기만 하는 출처(근거 사용 금지 또는 미검증)

| ID | 출처 | 등급 | 검증 | 메모 |
|---|---|---|---|---|
| S111 | NAMUR NE 43 "Standardization of the Signal Level for the Failure Information of Digital Transmitters" (2021-07-26판) | B (업계 협회 권고) | 열람 (NAMUR 목록, 제목·판만) | 회원 전용·유료. 4–20 mA 신호의 고장 신호대역 개념 |
| S112 | Wikipedia, "Current loop" | C | 열람 | "3.8 mA 미만이나 20.5 mA 초과는 고장으로 간주". 개념 안내용, 근거 금지 |
| S113 | 벤더 다운타임 통계(예: exida 논문 초록의 "연 $20B 생산손실"; Siemens/Senseye "True Cost of Downtime" 류) | C | exida 열람 / Siemens 미검증 | 근거로 쓰지 말 것 |
| S114 | ISO 14224:2016 (신뢰성·정비 데이터 수집 분류체계) | A | 미검증 (403) | 정비 피드백 라벨 체계로 유용할 수 있음. 확인 후 사용 |
| S115 | ISO 20816-1 / ISO 10816 계열의 alert/alarm 설정 관행 | A | 미검증 | 기준선 대비 상대 경보 설정 관행. 확인 못 함 |

---

## 3. 세부 내용과 우리 계획에 쓰는 법

### 3.1 산업 PdM에서 오경보를 줄이는 관행

#### 3.1.1 운전조건 조건부 기준선(regime-aware baseline, normal behaviour model)

- **표준의 요구.** ISO 17359:2018 §8.4는 이렇게 쓴다(S06, 열람). "Subsequent measurements are compared to the baseline values to detect changes … It is also important to be able to determine if a change in one or more parameters is due to the occurrence of a fault or is due to a change in duty or operating conditions." ISO/FDIS 13379-1:2025 서문은 이상(anomaly)을 "deviations from baseline values or expected operating conditions"로 정의한다(S07). ISO 13374-1의 State Detection 블록은 정상 기준 "profiles"를 만들어 유지하고, 데이터가 어느 이상구역("alert"/"alarm")에 드는지 판정한다(S05).
- **산업 선례(펌프).** Wang et al.(2016)의 예 4(S40, 열람-전문)가 있다. 발전소 급수펌프 유량이 고경보 trip point(560)를 넘었지만, 실제로는 운전원 수요가 늘었을 뿐 펌프는 정상이었다. 유량과 펌프 전류의 비례관계는 그대로였다. 처방은 "펌프 전류에 비례하는 동적 trip point로 정상 운전대역을 만들고", 펌프 on/off 같은 관련 변수 상태를 경보 설계에 넣는 것(ISA-18.2의 state-based alarming)이었다. 이 논문은 경보 과부하의 4대 원인 중 하나로 "alarm design isolated from related variables"를 꼽는다.
- **타 분야 선례.** Z24 교량(S16)은 고유진동수가 온도에 따라 정상적으로 변한다. 그래서 "normal changes should not raise an alarm (i.e. a false positive)"라며 온도 함수 모델의 신뢰구간 밖일 때만 이상으로 본다. SHM 분야는 이것을 data normalization이라 부른다(S17). 풍력 SCADA에서는 normal behaviour modelling이 독립된 주류 범주다(S12).
- **우리 계획에 쓰는 법**
  1. 전류(AI2)를 부하 대리변수로 삼아 진동 특징(burst RMS, 피크, 분산 등)의 **조건부 기대값과 조건부 분산**을 정상 데이터로 학습한다. 분위수 회귀나 전류 구간(bin)별 분위수를 쓴다. 잔차와 표준화 잔차를 health index로 쓴다.
  2. 이상 burst를 **전류가 비슷한 정상 burst와만 비교**하는 "regime-matched" 분석을 넣는다. 이상 burst의 전류가 정상 범위 밖이면 그 사실 자체를 보고해야 한다. 이때 "부하가 다른 날의 데이터"라는 교란을 분리할 수 없기 때문이다.
  3. 채점 (3)항(FN·FP가 몰리는 공정조건)은 **전류 구간별 FP/FN 분포**로 답한다.
  4. 주의할 점은 과정규화다. 고장 자체가 전류를 바꾸는 경우(예: 내부 누설로 같은 출력에 전류 증가)에는 전류로 정규화하면 신호가 지워질 수 있다. 그래서 정규화 모델과 비정규화 모델을 둘 다 보고, 전류–진동 관계 자체의 변화(결합 계수 이동)도 특징으로 둔다(추론, speculative).

#### 3.1.2 Health index와 이상구역

- ISO 13374-1의 정상 profile과 alert/alarm 구역(S05), C-MAPSS의 "health index = 여러 운전 여유의 최솟값"(S10)이 업계와 연구의 표준 언어다. ISO 13374-1은 정보 제시에 "failure type or fault, an estimate of the severity, a projection of condition and, finally, recommended action. Cost and risk factors may also be displayed."를 담으라고 한다.
- **쓰는 법.** 모델 점수를 그대로 내보내지 말고 하나의 HI(0–1 또는 정상 대비 백분위)로 통합한다. ISO 13374식 구역(관찰/점검/정지 검토)과 연결하고, 각 구역에 고장 추정, 심각도, 권고조치를 붙인다.

#### 3.1.3 센서 검증 층: 계측 결함과 기계 결함을 분리한다

- **근거**
  - ISO 13374-1의 Data Acquisition 블록에는 "data quality" 정보가 포함된다(S05).
  - 임상 감시경보 중 기술 경보가 31%였다(S51). Joint Commission은 전극 건조·센서 위치 오류를 비조치 경보의 원인으로 꼽았고, 단일 사용 센서 교체를 nuisance 경보 저감책으로 권고했다(S49).
  - Drew et al.은 "모든 유도(lead)를 써서 non-artifact 유도를 고르라"고 권고했다(S51). PhysioNet 2015 우승팀은 ECG에 ABP/PPG를 더한 다중 신호로 특이도 87%를 얻으면서 민감도 93%를 유지했다(S58).
  - 유압 시스템에서는 오프셋, 드리프트, 노이즈, 스파이크 결함을 센서 간 상관으로 탐지·보상해 최대 5개 센서 고장까지 견뎠다(S20). 결함 센서 데이터로 학습하면 모델이 망가진다. 다만 특징·모델을 고르면 강건성이 달라진다(S22).
  - 원자력에서는 온라인 감시로 교정이 필요한 센서만 골라낸다(S24). 펌프 46개 신호를 AAKR로 재구성하고 SPRT로 경보 수준을 정했다(S23).
  - HSE는 nuisance를 일으키는 디지털 경보 센서를 아날로그로 바꾸라고 했다(S35). 4–20 mA 계장에는 고장 신호대역 규약(NAMUR NE 43; 세부 미검증)이 있다(S111).
- **쓰는 법(규칙 목록, burst 단위)**
  - 타임스탬프: 단조성, 중복, burst 내 간격 0.1 s 일관성, burst 길이(50 미만이면 불완전 표시)를 확인한다.
  - 값: flat-line(burst 내 분산 0 또는 양자화 1단계 이하), 포화·클리핑(최대·최솟값 반복), 물리적으로 불가능한 값, 결측을 확인한다.
  - 채널 간 정합성: 상·하부 진동 중 **한 채널만 급변**하고 다른 진동과 전류가 그대로면 "계측·체결 의심"으로 본다. **세 채널이 일관되게 바뀌면** 기계 이상 가능성이 높다. 이것이 해석적 중복성(S32)의 응용이다.
  - 출력: "기계 이상 확률"과 별도로 "계측 신뢰도(SQI)"를 낸다. SQI가 낮을 때 기계 이상 경보를 **조용히 억제하면 안 된다.** 14 CFR 25.1322(d)(2)는 경보를 억제할 때 억제 사실을 분명히 표시하라고 하고(S44), ISA-18.2 지표는 승인 안 된 억제를 0건으로 둔다(S36). 그러니 "계측 점검" 등급의 별도 알림으로 바꿔 내보낸다.
  - 검증: 정상 burst에 합성 센서 결함을 주입해 "계측 의심"으로 잡히는지, 기계 이상 경보로 새는지 혼동행렬로 보인다(아이디어 I-04).

#### 3.1.4 지속성·지연·히스테리시스(persistence logic)

- **근거**
  - ICU 경보 지속시간 중앙값은 17 s였다. 14 s 지연이면 무시·무효 경보의 50%, 19 s면 67%가 제거된다(S54).
  - 체계적 문헌고찰은 지연을 "유망하지만 미입증"으로 분류했다. 지연에 따른 탐지 지체라는 이론적 해악도 언급했다(S53).
  - 맞춤 지연, 맞춤 임계값, 전극 교체를 묶어 환자·일당 경보가 180건에서 40건으로 줄었다(S56).
  - 공정산업에서는 on/off delay와 deadband를 FAR–MAR–AAD로 설계한다(S41, S42). HSE의 즉효책에도 deadband 조정이 있다(S35).
  - Drew et al.은 지속되는 심방세동 경보를 "시작과 종료에만" 울리라고 권고했다(S51). 진행 중인 이상 상태를 burst마다 반복해 울리지 말라는 뜻이다.
  - 반대 방향의 근거도 있다. SPC run rule을 더하면 정상 상태 ARL이 370에서 166으로 줄어 **오경보가 늘어난다**(S96).
- **우리 데이터로 해 본 산술(독립 가정, 실제 효과는 정상 타임라인에서 실측해야 함)**

| burst당 FPR p | 단일 burst 경보: 교대당 오경보 | 2-of-3 연속 burst 규칙: 창 오경보확률 | 교대당 오경보 |
|---|---|---|---|
| 2% | 약 75 | 1.18×10⁻³ | 약 4.4 |
| 1% | 약 37 | 2.98×10⁻⁴ | 약 1.1 |
| 0.5% | 약 19 | 7.5×10⁻⁵ | 약 0.28 |

  - 교대당 burst 수는 약 3,734개(7.78 burst/분 × 480분)로 계산했다. burst 사이 자기상관이 있으면 감소폭은 표보다 작다. 반드시 **정상 77분 타임라인에서 경보 발생 횟수를 직접 세어** 보고한다.
  - 대가는 지연이다. 2-of-3 규칙의 최소 지연은 2 burst(평균 주기 약 7.7 s이므로 약 15 s)다. 이상 사건 전체가 21 burst(약 3분)였으니 이 지연을 함께 보고한다.
- **쓰는 법**
  - "시작 시 경보 → 악화 시 상향 → 해소 시 해제 알림(off-delay)"의 상태기계로 설계한다.
  - 지속성 파라미터(k, n, off-delay)는 정상 데이터의 오경보 횟수와 합성 주입 이상의 지연으로 함께 고른다.
  - run rule은 쓰지 않거나 ARL을 다시 계산해서만 쓴다.

#### 3.1.5 경보 rationalization과 우선순위

- **근거**
  - ISA-18.2의 rationalization은 경보 후보마다 결과(consequence), 대응시간, 운전원 조치를 문서화한다. 우선순위는 결과의 심각도와 대응 가능 시간으로 정하고, 고우선 경보는 5% 이하로 둔다(S36). 결과는 Master Alarm Database에 기록한다.
  - ISA TR18.2.6은 **배치·이산공정**(프레스 같은 이산 제조)용, TR18.2.8은 **경보가 아닌 알림(non-alarm notifications)** 지침이다(S37).
  - HSE는 약 3단계 우선순위를 쓰고, 모든 경보에 정의된 대응을 두라고 한다(S35).
  - 항공 규정의 Warning/Caution/Advisory 위계(S44)도 같은 구조다.
  - ISO 13379-1은 FMSA와 Monitoring Priority Number를 제시한다(S07, 목차 수준).
- **쓰는 법.** 3단계 체계를 쓴다.

| 등급 | 성격 | 대응 |
|---|---|---|
| 관찰(Advisory) | ISA 의미의 "알림"에 해당 | 교대 보고서에만 기록 |
| 점검 권고(Caution) | 정비 요청 | 해당 교대 안에 지정 항목 점검 |
| 정지 검토(Warning) | 즉시 판단 | 운전원과 반장이 즉시 판단 |

  - 각 등급에 결과, 대응시간, 조치, 근거 원자료를 적은 "경보 정의표"를 보고서 부록으로 둔다.
  - 우선순위 비율(예: 고우선 5% 이하)을 운영 목표로 제시한다.

#### 3.1.6 Human-in-the-loop 피드백

- **근거**
  - ISO 13374-1: "Previous health assessments should be audited for accuracy, and root cause information added upon its discovery."(S05)
  - ISA-18.2는 감시·평가와 변경관리 단계를 둔다(S37).
  - 능동학습: "not all outliers are anomalies and not all anomalies are outliers"(S28). 예산 제한 전문가 라벨로 F1이 59% 올랐고, 전류(에너지) 데이터만으로 충분했다(S27). 전문가 규칙과 ML을 피드백으로 갱신한 FLAGS는 열차 PdM에 적용됐다(S26).
  - 보안관제(SOC)에서는 FP 대부분이 "benign trigger", 즉 정당한 활동이 설명하는 참 경보였다(S66). 이것은 과제가 말하는 "정상 운전 변화"와 같은 범주다.
- **쓰는 법.** 경보마다 처리 코드를 받는다.
  - (a) 실제 기계 이상
  - (b) 정상 운전 변화(benign trigger: 금형 교체, 부하 변화, 가동 개시 등)
  - (c) 계측 문제
  - (d) 진짜지만 조치 불필요(일시적)
  - (e) 미확인
  - (b)가 쌓이면 regime 정의에 새 상태를 더하거나 state-based 억제를 한다. (c)는 센서 정비로 보낸다. (a)는 라벨로 써서 재학습한다.
  - 보고서에는 이 순환을 "운영 6개월 계획"으로 그린다. 처리 코드 (d)는 Drew 2014의 "진짜 VT 경보의 93%가 치료할 만큼 지속되지 않음"(S51)에서 착안했다.

#### 3.1.7 단계적 도입(shadow mode, silent trial)

- **근거**
  - 임상 silent trial에서 AUC 0.90이 0.50으로 떨어졌다. 원인은 연령, 신장 좌우, 영상 형식 분포의 이동이었고, 고친 뒤 0.85–0.91이 됐다(S60).
  - 상용 패혈증 모델은 외부 검증에서 입원의 18%에 경보를 내면서 67%를 놓쳤다(S59).
  - 정비에서는 조치하면 반사실(counterfactual)이 사라진다("paradox of prognostics", S08).
- **쓰는 법.** 3단계 도입안을 쓴다.
  1. 2–4주 그림자 운영: 경보는 기록만 하고, 정비일지와 대조한다.
  2. 경보 예산(예: 교대당 1회 이하)을 충족하는지 확인한 뒤 점검 권고 등급만 가동한다.
  3. 처리 코드 데이터가 쌓이면 정지 검토 등급을 가동한다.
  - 조치할 때는 분해·점검 전 상태를 기록하는 **as-found 기록**(사진, 측정값, 이상 소견)을 의무로 해서 경보 라벨을 사후에 만들 수 있게 한다.
  - 우리 데이터의 핵심 위험은 "정상(화요일 새벽)과 이상(일요일 오전)의 날짜·시간 차이"다. silent trial 사례의 분포 이동 교훈이 그대로 적용된다.

### 3.2 타 분야 경보 피로: 정량 근거와 설계 패턴

| 분야 | 정량 근거 | 설계 패턴 | 우리 적용 |
|---|---|---|---|
| 임상 감시 | 거짓 경보 72–99%(S50); 31일 255만 건, 위양성 88.8%, 기술 경보 31%(S51); 비조치 경보 노출에 따라 반응 지연(S52); 98건 사건 중 80명 사망(S49) | 설정 맞춤, 지연, 전극·센서 관리, 다중 유도·다중 신호 확인, 지속 상태는 시작·종료만 경보 | regime 맞춤 임계값, 지속성 규칙, 센서 검증 층, 채널 교차확인, 상태기계 |
| 임상 경보 저감 성과 | 19 s 지연으로 67% 감소 추정(S54); 위험 경보 43% 감소(S55); 환자·일당 180→40(S56); 다중 신호로 특이도 87%·민감도 93%(S58) | 여러 중재를 묶어서 시행, 안전성(놓침) 측정을 함께 | "오경보 감소율"과 "놓침·지연 증가"를 반드시 같이 보고 |
| 공정산업 | Milford Haven 마지막 11분 275개 경보(S35); 15개 플랜트 정상 10분당 2–33건, 이상 시 72–625건(S40); ISA 목표 10분당 약 1건(S36) | rationalization, 우선순위 80/15/5, chattering 0, deadband·지연, state-based 경보 | 경보 정의표, 우선순위 분포 목표, 경보 예산 KPI |
| 항공 | 연방규정이 오경보·nuisance 경보 영향 최소화를 요구(S44); ATC 45% 오경보에도 cry-wolf 없음(S47) | Warning/Caution/Advisory 위계, 조건 해소 시 제거, 억제 사실 표시 | 3단계 위계, 해제 알림, "계측 의심"을 숨기지 않기 |
| 원자력 | 경보 HFE 검토 지침(S46); 펌프 AAKR+SPRT로 오경보·놓침 균형(S23); 온라인 센서 교정 감시(S24) | 신호 재구성 잔차와 순차검정, 센서 상태 감시 | 정상모델 잔차 + 순차검정(SPRT/CUSUM) |
| 기상 | 높거나 낮은 극단적 오경보율은 결정을 나쁘게 함, 확률 정보를 더하면 개선(S62); 권고+불확실성이 최선(S63); 대중 대상 근거는 혼재(S64); 오경보율과 사상자 연관(S61) | 확률 예보, cost-loss 결정 | 확률 + 권고 + 원자료 |
| 보안관제 | 기저율이 낮으면 오경보율 약 10⁻⁵ 수준이 필요(S65); FP 대부분이 benign trigger(S66) | 맥락(Contextual)과 설명(Explainable) 있는 경보 | burst당 FPR 목표를 기저율로 역산, FP 유형 분류 |
| 실험 인간요인 | 확률 매칭(S67); 오경보형 자동화가 더 해로움(S68); 신뢰도 약 0.7 미만이면 역효과(S69, 미확인) | 가능도 경보(S70, S71), 신뢰 보정(S72) | 확률 등급 경보 + 교차확인 패널 |

**종합.** 경보 피로가 실제로 생기는 조건은 세 가지다. ① 운영자가 경보를 자주 보고, ② 경보의 근거와 맥락을 모르고, ③ 대응 비용이 클 때다. ATC(S47)와 대중 기상 경보(S64)의 반례는 ②가 충족되거나 ①이 약한 경우다. 그래서 우리 설계의 우선순위는 이렇다. **경보 횟수를 예산 안으로 줄이고, 경보마다 근거(부하 조건, 어느 채널, 정상 대비 얼마나), 확신도, 대응 체크리스트를 붙인다.**

### 3.3 운영자 의사결정 지원의 인간요인

- **확률 표현.**
  - 빈도 형식("이 등급 경보 100건 중 약 N건이 실제 이상")이 베이즈 추론을 쉽게 한다(S74). icon array는 수리력과 무관하게 이해를 높인다(S75).
  - 연속 예측의 불확실성은 quantile dotplot이 결정 품질을 높였다(S76, S77).
  - 실무 결론: 현장 화면에는 숫자 확률 하나보다 **등급 + 자연빈도 문장 + (필요 시) 작은 icon array**가 낫다. N은 현장 기저율 가정에 따라 달라지므로, 보고서에는 시나리오 표로 둔다.
- **가능도 경보 + 교차확인.**
  - LAS가 이진 경보보다 신뢰·준수·성과 모두 우수했고, 원자료 교차확인 옵션과 결합할 때 최고였다(S71). 가능도 정보는 부하를 반드시 늘리지 않는다(S70).
  - 쓰는 법: 경보 카드에 "해당 burst의 세 채널 파형 + 같은 전류대 정상 envelope(5–95% 분위수 띠)"를 붙인다.
- **설명의 함정.**
  - 설명은 정답 여부와 무관하게 수용만 늘렸다(S80). 지역 설명은 신뢰 보정에 문제가 있었고, confidence score가 더 나았다(S79). cognitive forcing은 과의존을 줄였지만 사용자는 싫어했다(S81).
  - 쓰는 법: SHAP류 설명보다 **"어느 채널이, 같은 부하의 정상 대비 몇 배인가"라는 물리적 비교**와 확신도를 우선한다. 정지 검토 등급에만 "운전원이 먼저 원자료를 보고 판단을 입력한 뒤 모델 판단을 보는" 가벼운 forcing을 둔다(선택).
- **체크리스트.**
  - 19항목 수술 체크리스트 도입 후 사망과 합병증이 줄었다(S82). 항공 체크리스트 설계 원칙(S48)이 있다. 연방 항공규정은 경보가 "적절한 조치를 결정하는 데 필요한 정보"를 주라고 한다(S44). HSE는 모든 경보에 정의된 대응을 두라고 한다(S35).
  - 쓰는 법: 등급별 대응 카드를 만든다. 순서는 ① 계측 확인(센서 체결, 케이블, SQI) → ② 공정 확인(작동유 온도·레벨, 흡입 필터, 압력계, 이음) → ③ 판단(지속 운전, 감속, 정지)이다. 센서를 먼저 확인하는 순서가 오경보 비용을 낮춘다.
- **신뢰 보정.**
  - 적절한 의존은 시스템 능력에 맞춘 신뢰 보정의 문제다(S72). 과의존과 과소의존 둘 다 실패다(S73).
  - 쓰는 법: 운영 화면에 "최근 30일 경보 중 확인된 이상 비율(처리 코드 기반)"을 보여 주어 운영자의 신뢰가 실제 정밀도를 따라가게 한다.

### 3.4 경제성과 정직한 기대값 모형

#### 3.4.1 믿을 만한 숫자와 조심할 숫자

- **쓸 수 있다(단서와 함께).**
  - NIST 설문(S02, S03): 2016년 미국 이산제조 정비비와 예방 가능한 손실은 $193.6B(S03)다. Monte Carlo 평균은 $222.0B, 계획외 정지 손실은 $18.1B(90% CI 10.4–27.8B)다.
  - 반응정비 의존 상위 50%와 하위 50%를 비교하면, 하위 50%는 계획외 정지 52.7%, 결함 78.5%가 적다. 계획 생산시간 중 정지 비율 평균은 10.38% 대 4.91%다.
  - 예측 대 예방 비교에서는 정지 18.5%, 결함 87.3%가 적다.
  - **단서:** 응답 71개, 저자가 "should be treated as anecdotal evidence"라고 명시했다. 예측정비 상위 그룹은 직접 정비비가 출하액 대비 212.3% 높았다. 고장 관련 추가비용이 오히려 조금 높게 나온 점에 대해 저자는 "고장 정의 임계값 차이" 가능성을 들었다.
- **정의 인용만 한다.** DOE FEMP 가이드(S04)의 예방 12–18%, 예측 8–12% 절감과 "independent surveys"의 ROI 10배, 정지 35–45% 감소는 원출처가 없다.
- **쓰지 않는다.** 벤더의 "시간당 $X", "연 $1조" 류 통계(S113).

#### 3.4.2 프레스 라인용 단순 기대값 모형(파라미터형)

변수(교대 단위). 플랜트 담당자에게 값을 받거나 범위로 둔다.
- N_b: 교대당 burst 수 ≈ 3,734 (데이터 주기에서 계산)
- F: 교대당 오경보 수 = 정상 타임라인에서 실측한 경보 발생률 × 교대 길이
- λ: 교대당 고장 발생 기대 횟수(현장 기저율; 미지, 시나리오)
- d: 고장을 **유효 리드타임 안에서** 잡을 확률(합성 주입 실험과 이상 사건 분석으로 범위 추정)
- C_I: 경보 1건 점검비용(점검 인건비, 단기 정지, 생산 손실)
- C_U: 놓친 고장의 비용(계획외 정지 시간 × 시간당 손실 + 수리 + 불량·스크랩 + 금형 손상)
- C_P: 조기 발견 시 계획 수리비용

**기대 절감(반응정비 대비, 교대당) = λ·d·(C_U − C_P) − (F + λ·d)·C_I − (시스템 운영비)**

- **손익분기 정밀도.** 경보 1건이 실제일 확률(PPV)이 **C_I / (C_U − C_P)**보다 커야 이익이다.
- **확률 임계값(cost-loss 규칙).** 점검하면 기대비용이 C_I + p·C_P, 안 하면 p·C_U다. 그래서 **p > p* = C_I / (C_U − C_P)**일 때 점검한다. 이것이 Elkan(S107)의 비용 기반 임계값이자 기상의 cost-loss 비율 C/L(S109, S110)이다. 예: C_U − C_P가 C_I의 50배면 p*는 약 0.02다.
- **기저율 보정이 필수다.** 모델의 학습 비율(burst 기준 3.4%)과 현장 기저율이 다르다(S104; S107 §3).

| 모델 확률 | 현장 기저율 10⁻³ | 현장 기저율 10⁻⁴ |
|---|---|---|
| 0.5 | 0.028 | 0.0028 |
| 0.9 | 0.20 | 0.025 |
| 0.99 | 0.74 | 0.22 |

  - 사전 odds 비율로 보정한 값이다(계산은 R9). 즉 **같은 모델이라도 현장 기저율 가정에 따라 경보 등급이 바뀐다.** 보고서에서는 "확률"이 아니라 "기저율 가정별 확률"로 쓴다.
- **비용을 모를 때의 대안(Neyman–Pearson식).** 운영자가 감당할 경보 예산 B(예: 교대당 1회)를 먼저 정하고, 그 예산에서의 탐지율과 지연을 보고한다. ISA·EEMUA의 10분당 1건(S35, S36)은 공정 제어실 전체 경보에 대한 목표다. 기계 한 대의 PdM 알림 예산은 그보다 훨씬 작아야 한다는 정도로만 인용한다(유추).
- **시각화.**
  - decision curve: 임계 확률별 net benefit = TP/N − FP/N × p_t/(1−p_t) (S108)
  - relative economic value: C/L 비율별로 "항상 점검"이나 "점검 안 함" 대비 이익 (S109)
  - 둘 다 "어떤 비용 구조에서 우리 시스템이 의미가 있는가"를 한 장에 보여 준다.

### 3.5 평가 방법론의 함정(채점 (2)·(6)과 직결)

- **정확도 역설.** 행 기준 "전부 정상"의 정확도는 20,000/20,600 = 97.09%다. 가이드북 정확도 97.51%는, 같은 비율로 평가했다면 기준선보다 0.42%p 높을 뿐이다. 가이드북 수치는 호출자 제공이고 분할 방식은 미확인이다. 불균형에서는 PR 곡선이 ROC보다 정보가 많다(S88).
- **point adjustment 금지.** PA는 무작위 점수도 SOTA로 만들 수 있다(S83). 사건(burst 묶음) 단위 지표, 구간 기반 PR(S85, 앞쪽 가중), 탐지 지연을 쓴다.
- **n=1 사건.** 이상은 사건 하나다. burst 21개는 독립 표본이 아니다. 사건 단위 recall은 1/1이고 95% CI는 [0.025, 1]이다. 따라서 "조기탐지 성능"은 실제 데이터만으로 입증할 수 없다. 이를 **합성 열화 주입(dose–response)**으로 보완하고 민감도 분석으로 명시한다(S87; S84의 run-to-failure 편향 경고).
- **rule of three.** 정상 599 burst에서 FP 0건이어도 burst당 FPR의 95% 상한은 0.50%(교대당 약 19회)다. 20% 홀드아웃(약 120 burst)이면 2.47%(교대당 약 92회)다(S105의 원리; 계산은 R9). 따라서 FPR은 **정상 데이터 전체를 시간 블록 교차검증으로 돌려** 추정하고 상한을 함께 보고한다.
- **누수와 지름길.** 정상과 이상이 다른 날·다른 시간대라서, 모델이 "고장"이 아니라 "일요일 오전" 같은 조건을 배울 수 있다(S89–S91). 음성 대조(S92)로 점검한다.
  - 예: 정상 데이터의 앞 절반과 뒤 절반을 가르는 분류기의 AUC로 시간 드리프트의 크기를 재고, 이상 탐지 점수의 크기와 비교한다.
  - 예: 전류가 비슷한 정상 burst와만 비교한다.
- **확률 보정의 한계.** isotonic 같은 보정은 데이터가 많아야 한다(S103). 이상이 사건 하나뿐이면 신뢰도 곡선의 이상 쪽은 추정할 수 없다. 정상 쪽은 conformal p-value로 보정을 보장하고(S93; 교환가능성 가정), 이상 확률은 기저율 시나리오로 제시한다.

---

## 4. 위험·한계·반론

1. **타 분야 전이의 한계.** 임상·항공·기상·보안의 근거는 운영자, 경보 빈도, 대응비용이 다른 환경에서 나왔다. 실험 연구는 학생 표본이 많다(S67, S68). 대중 기상 경보에서는 cry-wolf가 약하거나 없었고(S64), ATC도 그랬다(S47). 보고서에는 "직접 증거"가 아니라 "설계 원칙의 근거"로 쓰고, 반례를 함께 적어야 신뢰를 얻는다.
2. **공정산업 경보 KPI는 제어실 기준이다.** ISA-18.2와 EEMUA의 10분당 1건(S35, S36)은 DCS 운전원 1인이 받는 모든 경보에 대한 목표다. 기계 한 대의 PdM 경보에 그대로 적용하면 안 된다. 유추로만 인용한다.
3. **경제성 수치의 품질.** NIST 설문은 n=71이고 저자가 일화적이라고 했다. FEMP 수치는 출처 불명이다. 벤더 통계는 쓰면 안 된다. 우리 라인의 비용은 모르므로 **파라미터 모형과 민감도**로만 제시한다. 근거 없는 "연간 X억 절감" 같은 문장은 감점 위험이 크다.
4. **센서 검증 층의 이중 위험.** 진짜 고장의 초기 증상이 한 채널에만 나타나면 "계측 의심"으로 잘못 분류될 수 있다(위험한 FN). 그래서 계측 의심도 반드시 알림으로 나가야 하고, 억제는 금지다(S44의 원칙). 규칙의 임계값은 정상 데이터 분위수로 정하고, 합성 주입으로 오분류율을 보고한다.
5. **과정규화.** 전류 조건부 정규화는 부하 변화로 인한 오경보를 줄인다. 하지만 고장이 전류–진동 관계를 바꾸는 방식으로 나타나면 신호를 지울 수 있다. 정규화 모델과 비정규화 모델을 비교하고, 관계 자체의 변화를 특징으로 둔다.
6. **지속성 규칙의 대가.** 오경보를 줄이는 만큼 탐지가 늦어진다. 이상 사건이 21 burst뿐이라 지연 추정이 불확실하다. 갑작스러운 고장(급성)에서는 지연이 치명적일 수 있다. 그래서 최상위 등급은 "단일 burst라도 극단값이면 즉시"라는 우회 경로를 둔다(설계 제안, speculative).
7. **통계적 보장의 가정.** conformal(S93)과 EVT(S95)의 보장은 교환가능성이나 iid 가정에 기댄다. burst는 자기상관이 있고 시간 드리프트가 있을 수 있다. 시간 블록 단위 보정, 최근 기간 가중, 보장 문구의 완화("근사적으로")가 필요하다.
8. **합성 주입의 타당성.** 합성 열화는 실제 고장 물리를 대신하지 못한다. 결과는 "탐지 가능 최소 효과 크기"라는 **민감도 분석**으로만 제시하고, 실제 고장 성능이라고 주장하면 안 된다(S84의 경고와 같은 맥락).
9. **아이디어 과잉.** 아래 아이디어는 40개다. 다 하면 일관성이 깨진다. 최소 핵심 세트(6장 끝)에 집중하고, 나머지는 "향후 운영 계획"으로 돌리는 것이 채점상 유리할 가능성이 크다(판단).
10. **저작권.** ISO, IEC, ISA, EEMUA 문서는 유료·저작권물이다. 표나 문장을 길게 옮기지 말고 수치와 개념을 출처와 함께 요약한다. Joint Commission 경보문은 "전체로만 복제 가능"하다. 짧은 사실 인용만 한다. 그림 재사용은 CC BY 출처(S21, S51, S60, S88 등)만 출처 표기와 함께 한다.

## 5. 아직 확인 못 한 것

- **센서 신호의 성격:** AI0·AI1이 RMS형 진동 트랜스미터 출력(4–20 mA 등)인지 원파형 샘플인지, 단위는 무엇인지. 특징 설계와 "10 Hz로 진동 진단은 부족" 논점의 강도가 이것에 따라 달라진다. 데이터 제공처나 가이드북 확인이 필요하다. 데이터에서 볼 수 있는 단서는 값의 부호, 평균 0 여부, 부드러움, 양자화 단계다.
- **현장 비용 값:** 프레스 라인의 시간당 정지 손실, 점검 1회 비용, 금형 손상 비용.
- **표준 원문:** ISO 14224(접근 403), IEC 62682의 판, ISO 20816/10816의 alert 설정 관행, FAA AC 25.1322-1(403), EEMUA 191 원문, ISA-18.2-2016 본문. ISA 표는 2009년판을 exida 논문 인용으로만 확인했다.
- **검색만 한 수치:** Simmons & Sutter의 "오경보율 1 SD당 사망 12–29%"(S61), Wickens & Dixon의 신뢰도 0.70 교차점(S69), Champ & Woodall의 전체 run rule 적용 ARL 약 92(미확인; 개별 규칙 값만 확인).
- **내용 미확인 논문:** Bangalore & Tjernberg의 경보 지속성 세부, Bartelmus & Zimroz의 부하 의존 특징 세부, Wang et al.(2008, PHM)의 운전 regime 정규화 세부(이번 보고서에서는 쓰지 않음).
- **제조 PdM 사례:** 지속성 규칙이나 regime 조건화로 오경보를 몇 % 줄였는지를 정량 보고한 동료심사 사례(검색 할당량 소진으로 추가 탐색 불가).
- **도메인 근거:** 작동유 온도·점도가 펌프 진동과 전류에 미치는 영향, 그리고 그것이 "다른 날·다른 시간" 교란의 한 경로인지에 대한 유압 전문 문헌.
- **가이드북 수치(97.51%, F1 0.7476)의 평가 단위와 분할 방식:** 호출자 제공, 미확인.

---

## 6. 아이디어 목록

표기: **[SC]** = 전문가 심사위원에게 "놀랍지만 신뢰할 만하다"로 보일 가능성이 높은 아이디어. 노력 S/M/L. 배점 항목: (1) 데이터 이해 15, (2) 모델 40, (3) 영향요인·오류분석 15, (4) 현장 적용 10, (5) 창의성 10, (6) 재현성 10. 패러다임 태그: [데이터공학] [물리] [통계] [ML] [딥러닝] [의사결정] [HITL] [평가] [시각화].

### A. 데이터공학·센서 검증

**I-01. burst 단위 데이터 모델** [데이터공학]
- 무엇: 간격(gap)으로 burst를 나누고 burst ID를 부여한다. 창(window)은 절대 gap을 넘지 않는다. burst당 표본 수, 간격 일관성, 중복 행을 검사한다. 특징, 라벨, 평가 단위를 burst로 통일한다.
- 왜: 데이터가 최대 5초 burst와 1.5–17초 간격으로 되어 있어서, 연속 시계열 가정(LSTM 창 등)은 gap을 넘는 가짜 패턴을 만든다.
- 근거: ISO 13374-1 DA·DM 블록(S05), ISO 17359 §8.7 기록 요건(S06), 데이터 구조.
- 노력 S · 위험 낮음 · 배점 (1)(6).

**I-02. 센서 검증(SQI) 관문과 "계측 의심" 범주** [데이터공학][물리] [SC]
- 무엇: 3.1.3의 규칙(타임스탬프, flat-line, 포화, 단일 채널 급변, 채널 간 정합성)으로 burst마다 SQI를 낸다. 기계 이상 확률과 별개로 "계측 점검" 알림을 낸다. 억제는 하지 않는다.
- 왜: 타 분야에서 비조치 경보의 큰 몫이 계측 문제였다. 과제가 요구하는 오경보 조건 분석에 "계측성 FP"라는 범주를 추가할 수 있다.
- 근거: S49, S51, S20, S22, S58, S05, S44.
- 노력 S–M · 위험: 진짜 고장의 초기 단일 채널 증상을 계측 문제로 오분류할 수 있음 → 알림 유지로 완화 · 배점 (1)(3)(4)(5).

**I-03. 신호 성격 감식** [물리][데이터공학]
- 무엇: AI0·AI1·AI2가 RMS형 출력인지 원파형인지 판별한다. 부호 변화, 평균 0 여부, 자기상관, 양자화 단계, 상하한 포화를 본다. 결과에 따라 특징군을 정한다. RMS형이면 추세·분산·결합 특징, 원파형이면 앨리어싱 경고와 저주파 통계를 쓴다.
- 왜: 10 Hz 진동의 의미가 이것으로 정해진다. 심사위원이 반드시 물을 질문이다.
- 근거: speculative (+ S06 §8.6 "수집률은 조건이 바뀌기 전에 전체 데이터를 잡을 만큼 빨라야").
- 노력 S · 위험 낮음 · 배점 (1).

**I-04. 센서 결함 주입 시험대** [평가] [SC]
- 무엇: 정상 burst에 오프셋, 드리프트, 잡음 증가, 스파이크, flat-line, 결측, 타임스탬프 지터를 주입한다. "계측 의심 vs 기계 이상 vs 정상"의 혼동행렬과 기계 경보로 새는 비율을 보고한다.
- 왜: 센서 검증 층의 성능을 숫자로 보여 주는 유일한 방법이다. 오경보 분석의 깊이를 보여 준다.
- 근거: S20(결함 유형), S22(오픈소스 결함 주입 패키지).
- 노력 M · 위험: 주입 크기 설정이 자의적이라는 비판 → 정상 분포 분위수로 크기를 정함 · 배점 (3)(5)(6).

### B. 통계·물리 기반

**I-05. 전류 조건부 정상모델과 동적 임계값** [물리][통계] [SC]
- 무엇: 진동 특징의 조건부 분위수(전류 구간별 또는 분위수 회귀)를 정상 데이터로 학습한다. 잔차 HI와 전류 의존 임계 띠를 만든다.
- 왜: 과제의 오경보 정의("정상 운전 변화")에 정면으로 대응한다. 산업 선례가 있다.
- 근거: S40 예 4(펌프 전류 비례 동적 trip point), S06 §8.4, S16, S17, S12.
- 노력 M · 위험: 과정규화(4장 5항) · 배점 (2)(3)(5).

**I-06. 상·하부 진동 결합과 전류–진동 결합 특징** [물리][통계]
- 무엇: 상/하 RMS 비, burst 내 상관, 한 채널로 다른 채널을 예측한 잔차, 전류 대비 진동 기울기를 특징으로 둔다. 결합이 깨지는 것을 이상 신호로 본다.
- 왜: 기계 고장은 결합 구조를 바꾸고, 계측 문제는 한 채널만 바꾸는 경향이 있다(가설). 해석적 중복성으로 FP의 원인을 구분할 수 있다.
- 근거: S32, S20(센서 간 상관 이용), speculative.
- 노력 S–M · 위험: 채널이 진짜 중복 측정이 아니어서 관계가 약할 수 있음 · 배점 (3)(5).

**I-07. MSPC 기준선(PCA T²/SPE와 기여도 그림)** [통계]
- 무엇: burst 특징에 PCA를 적합하고 Hotelling T²와 SPE 관리한계를 둔다. 경보 시 변수 기여도를 제시한다.
- 왜: 가볍고 해석 가능한 "기준선 모델"이며, 기여도가 영향요인 분석으로 이어진다.
- 근거: S100.
- 노력 S · 위험 낮음 · 배점 (2)(3).

**I-08. AAKR/정상모델 + SPRT 경보 논리(원자력 펌프 관행 차용)** [통계] [SC]
- 무엇: 정상 burst 메모리에서 커널 가중으로 현재 burst를 재구성(AAKR)한다. 잔차에 순차확률비검정(SPRT)을 걸어 오경보율과 놓침률 목표로 경보를 낸다.
- 왜: 원자력 펌프 감시라는 고신뢰 분야의 검증된 조합이다. 오경보와 놓침의 균형을 명시적 파라미터로 다룬다.
- 근거: S23, S24.
- 노력 M · 위험: SPRT의 분포 가정 · 배점 (2)(5).

**I-09. HI에 EWMA/CUSUM — ARL₀를 경보 예산으로 설계** [통계] [SC]
- 무엇: burst HI에 EWMA나 CUSUM을 걸고, 정상 상태 ARL₀를 "교대당 1회 이하"(ARL₀ ≈ 3,700 burst)로 맞춘다.
- 왜: SPC의 ARL₀는 곧 "평균 오경보 간격"이다. 현장 언어(교대당 오경보)와 통계 설계가 한 줄로 이어진다.
- 근거: S98, S99, S96(run rule은 ARL을 줄인다는 경고).
- 노력 S · 위험: 자기상관으로 ARL이 틀어짐 → 정상 타임라인 시뮬레이션으로 실측 · 배점 (2)(4)(5).

**I-10. EVT 꼬리 임계값(SPOT/POT)** [통계]
- 무엇: 정상 점수 꼬리에 일반화 파레토를 적합하고, 위험 q(경보 예산에서 역산)에 해당하는 임계값을 쓴다.
- 왜: "임계값을 손으로 정했다"는 비판을 피한다.
- 근거: S95.
- 노력 S–M · 위험: iid 가정, 꼬리 표본 부족(599 burst) · 배점 (2)(5).

**I-11. conformal p-value + BH로 오경보를 FDR로 통제** [통계] [SC]
- 무엇: 정상 보정 집합으로 burst별 conformal p-value를 만들고, 시간 창 단위로 Benjamini–Hochberg를 적용한다. "경보 중 거짓의 비율"을 명목 수준으로 통제한다.
- 왜: 과제의 "오경보 감소"를 통계적 보장(FDR)으로 번역한다. 확률형 출력(채점 (2))과 불확실성(채점 (5))을 동시에 충족한다.
- 근거: S93, S94.
- 노력 M · 위험: 교환가능성 위반 → 블록 보정, "근사적" 표현 · 배점 (2)(5).

### C. ML·딥러닝

**I-12. 가이드북 LSTM-AE 재현과 정직한 재평가** [딥러닝]
- 무엇: EncDec-AD 계열을 재현해 기준선 1로 둔다. burst 단위로 입력하고, PA 없는 사건·시간 지표로 다시 평가한다.
- 왜: "베이스라인 포함 2개 이상 비교" 요건을 충족하고, 가이드북 대비 평가 차이를 투명하게 보인다.
- 근거: S33, S83.
- 노력 M · 위험: 가이드북 설정을 몰라 재현이 불완전할 수 있음 → 차이를 명시 · 배점 (2).

**I-13. Isolation Forest와 robust covariance 기준선** [ML]
- 무엇: burst 특징 위의 비지도 기준선 2개.
- 왜: 빠르고 견고하다. 딥러닝 대비 "간단한 모델로 충분한가"를 보여 준다.
- 근거: S34.
- 노력 S · 위험 낮음 · 배점 (2).

**I-14. 정상 전용 학습 프로토콜과 시간 블록 교차검증** [평가][ML]
- 무엇: 이상 데이터는 학습에 쓰지 않고 평가에만 쓴다. 정상은 시간 블록 K-fold로 돌려 정상 전체에서 FPR을 추정한다.
- 왜: 이상 사건 하나에 과적합하는 것과, 이상 burst가 학습·평가에 섞여 생기는 누수를 막는다. rule-of-three 상한을 줄인다.
- 근거: S89, S84, S105.
- 노력 S · 위험 낮음 · 배점 (1)(2).

**I-15. 이질 앙상블과 불일치 시 "검토" 등급(reject option)** [ML][의사결정]
- 무엇: 통계·IF·AE 점수를 순위 평균한다. 모델끼리 크게 엇갈리면 "판정 보류 → 사람 확인"으로 보낸다.
- 왜: 불확실성 추정과 오경보 저감을 동시에 한다. 보류 비율도 지표로 보고한다.
- 근거: S101, S102.
- 노력 M · 위험: 복잡도 증가 · 배점 (2)(5).

**I-16. 지도 판별기는 보조, 상한 참고용으로만** [ML]
- 무엇: 정상 대 이상 분류기(클래스 가중, 사건 그룹 CV)를 만들되 "분포가 같다면의 상한"으로만 제시한다.
- 왜: 지도 모델은 날짜·시간 교란을 배우기 쉽다. 비교용으로만 가치가 있다.
- 근거: S88, S89, S90.
- 노력 M · 위험: 심사위원이 높은 F1을 그대로 믿을 위험 → 경고 문구 · 배점 (2).

### D. 평가·타당성

**I-17. 사건·시간 기반 지표 세트** [평가]
- 무엇: 사건 탐지 여부, 사건 시작부터 첫 경보까지의 burst 수(지연), 구간 기반 PR(앞쪽 가중), burst 단위 PR-AUC. PA는 쓰지 않는다.
- 왜: 조기탐지 과제의 본질에 맞고, 평가 함정을 피한다.
- 근거: S85, S83, S86, S88.
- 노력 S–M · 위험 낮음 · 배점 (2)(3).

**I-18. 경보 예산 보고(교대당 오경보, MTBFA, rule-of-three 상한)** [평가][의사결정] [SC]
- 무엇: 모든 모델의 오경보를 "교대당 횟수와 평균 무오경보 시간"으로 환산하고 95% 상한을 함께 낸다.
- 왜: 현장 언어로 오경보를 말한다. "FP 0" 주장의 한계를 스스로 밝히는 정직성이 돋보인다.
- 근거: S105, S36, S35, 3.5절 계산.
- 노력 S · 위험 낮음 · 배점 (2)(4).

**I-19. 음성 대조와 Clever-Hans 감사** [평가] [SC]
- 무엇: ① 정상 앞/뒤 절반 판별 AUC로 시간 드리프트의 크기를 잰다. ② 이상 점수와 전류 수준의 관계를 본다. ③ 전류가 비슷한 정상과만 비교한다. ④ 절대 수준 특징을 빼는 ablation을 한다. "다른 날"이라는 교란이 탐지 성능을 얼마나 설명하는지 정량화한다.
- 왜: 데이터의 가장 큰 약점(정상과 이상의 일시 차이)을 정면으로 다룬다.
- 근거: S92, S90, S91, S60(silent trial의 분포 이동).
- 노력 M · 위험: 결과가 불리하게 나올 수 있음 → 그래도 보고하는 편이 신뢰를 얻음 · 배점 (1)(3).

**I-20. 합성 열화 dose–response 곡선** [평가] [SC]
- 무엇: 홀드아웃 정상 burst에 단계적 열화를 주입한다. 진동 분산 x% 증가, 간헐 스파이크 빈도, 느린 드리프트, 채널 결합 붕괴, 전류–진동 기울기 변화 같은 것이다. 효과 크기별 탐지율과 지연 곡선을 그리고 최소 탐지 효과를 보고한다.
- 왜: 이상 사건 하나로는 "조기" 탐지를 평가할 수 없다. 모델 비교의 공정한 공통 척도가 된다.
- 근거: S87(합성 이상 주입은 검증된 대리 지표), S22.
- 노력 M · 위험: 합성은 실제 고장이 아님 → 민감도 분석으로만 표현 · 배점 (2)(3)(5).

**I-21. 이상 사건 내부의 시작 구간 분석** [평가]
- 무엇: 21 burst 중 앞쪽 k개만 보고 탐지 여부를 보는 prefix 분석과, 사건 시작 대비 경보 시점.
- 왜: 실제 데이터로 할 수 있는 유일한 조기성 근거다.
- 근거: speculative.
- 노력 S · 위험: 사건의 실제 시작 시각을 모름(기록 시작 = 사건 시작이 아닐 수 있음) · 배점 (3)(4).

**I-22. 보정 진단의 정직한 버전** [통계][의사결정] [SC]
- 무엇: 정상 쪽은 conformal p-value의 균등성 검사와 신뢰도 그림으로 보인다. 이상 확률은 Brier와 신뢰도 곡선(표본 한계를 명시)으로 보이고, 기저율 시나리오별 확률표(3.4.2)를 둔다.
- 왜: "확률을 예측하라"는 요구에 수학적으로 정직하게 답한다.
- 근거: S103, S104, S107, S106.
- 노력 M · 위험 낮음 · 배점 (2)(5).

**I-23. 블록 부트스트랩 신뢰구간과 임계값 불확실성 띠** [평가]
- 무엇: 모든 지표와 임계값에 시간 블록 부트스트랩 CI를 붙인다.
- 왜: 표본이 작으니 불확실성을 보여 주는 것이 곧 재현성이다.
- 근거: 표준 통계(별도 출처 없음).
- 노력 S · 위험 낮음 · 배점 (2)(6).

### E. 의사결정·현장 적용

**I-24. 3단계 경보 위계와 경보 정의표** [의사결정][HITL]
- 무엇: 관찰(알림), 점검 권고, 정지 검토 3단계. 각 등급의 결과, 대응시간, 조치, 근거 데이터를 표로 정의한다. 우선순위 분포 목표를 둔다.
- 왜: 산업·항공의 검증된 구조이며, 현장 적용 점수에 직접 기여한다.
- 근거: S44, S36, S35, S37.
- 노력 S · 위험 낮음 · 배점 (4).

**I-25. 지속성·히스테리시스 상태기계** [의사결정]
- 무엇: k-of-n on-delay, off-delay, "시작 시 1회 경보 → 악화 시 상향 → 해소 알림", 극단값 즉시 경로. FAR–MAR–AAD 표로 파라미터를 고른다.
- 왜: 가장 값싸고 효과가 큰 오경보 저감책이다.
- 근거: S54, S56, S41, S42, S51.
- 노력 S · 위험: 지연 증가 · 배점 (4)(5).

**I-26. 비용 기반 임계값과 decision curve·REV 그림** [의사결정] [SC]
- 무엇: p* = C_I/(C_U − C_P). 비용비 범위에서 net benefit과 상대 경제가치 곡선을 그린다.
- 왜: "왜 이 임계값인가"에 대한 가장 강한 답이다. 의료·기상의 검증된 틀을 제조에 옮긴다.
- 근거: S107, S108, S109, S110.
- 노력 S–M · 위험: 비용을 모름 → 범위와 민감도 · 배점 (4)(5).

**I-27. 교대 단위 기대값 계산기와 손익분기 정밀도** [의사결정]
- 무엇: 3.4.2 식을 노트북이나 슬라이드의 슬라이더로 만든다.
- 왜: 운영자·관리자 의사결정과 바로 연결된다.
- 근거: S107, S02(맥락).
- 노력 S · 위험: 숫자를 사실로 오인할 수 있음 → "가정값" 표기 · 배점 (4).

**I-28. 점검 우선순위 목록(위험 = 확률 × 결과)** [의사결정]
- 무엇: 교대마다 상위 k개 이상 구간을 확률 × 결과 × SQI로 순위화한다. FMSA의 MPN과 비슷한 우선순위 수를 쓴다.
- 왜: 과제 문구 "점검 우선순위"에 직접 답한다.
- 근거: S07, S36.
- 노력 S · 위험 낮음 · 배점 (4).

**I-29. 처리 코드 피드백 순환과 능동학습 대기열** [HITL] [SC]
- 무엇: 경보마다 (a) 실제 이상, (b) 정상 운전 변화, (c) 계측, (d) 진짜지만 조치 불필요, (e) 미확인 코드를 받는다. (b)는 regime을 갱신하고, (a)는 재학습 라벨이 되며, 불확실 burst는 전문가 확인 대기열로 간다.
- 왜: 오경보를 줄이는 운영 기제를 제시하고, 과제의 FP 조건 분석을 운영으로 확장한다.
- 근거: S66, S28, S27, S26, S05.
- 노력 M(설계만 하면 S) · 위험: 라벨 부담 → 예산 제한 · 배점 (3)(4)(5).

**I-30. as-found 기록 규약** [HITL] [SC]
- 무엇: 경보로 점검할 때 분해·수리 전 상태(측정값, 사진, 소견)를 기록하는 양식.
- 왜: 조치하면 예측의 진위를 알 수 없게 되는 "paradox of prognostics"를 우회해 라벨을 만든다.
- 근거: S08.
- 노력 S · 위험 낮음 · 배점 (4).

**I-31. 그림자 운영(silent trial) 도입 계획** [HITL][의사결정]
- 무엇: 2–4주 기록만 하는 운영, 경보 예산 충족을 가동 기준으로, 등급별 단계 가동. 분포 이동 감시 지표(전류 분포, 정상 점수 분포)를 함께 둔다.
- 왜: 다른 날·시간 데이터로 학습한 모델의 위험을 운영으로 관리한다.
- 근거: S60, S59, S37.
- 노력 S · 위험 낮음 · 배점 (4).

**I-32. 경보 연동 대응 카드(체크리스트)** [HITL]
- 무엇: 등급별 1쪽 카드. 순서는 ① 계측(체결, 케이블, SQI) → ② 공정(작동유 온도·레벨, 흡입 필터, 압력계, 소음) → ③ 판단 기준이다.
- 왜: 오경보 비용을 낮추고(센서 먼저), 경보를 행동으로 연결한다.
- 근거: S82, S48, S35, S44.
- 노력 S · 위험: 유압 점검 항목은 현장 검토가 필요 · 배점 (4).

### F. 시각화·전달

**I-33. 가능도 경보 표시와 교차확인 패널** [시각화] [SC]
- 무엇: 등급 색과 확률 등급에 더해, 해당 burst의 세 채널 파형을 같은 전류대 정상 envelope(5–95% 띠) 위에 겹친 패널.
- 왜: LAS와 교차확인 조합이 실험에서 최선이었고, 운영자가 경보의 맥락을 즉시 이해한다.
- 근거: S71, S70, S05(이상구역 표시).
- 노력 S–M · 위험 낮음 · 배점 (4)(5).

**I-34. 자연빈도 문장과 icon array** [시각화]
- 무엇: "이 등급 경보 100건 중 약 N건이 실제 이상(기저율 가정 X)". 10×10 아이콘.
- 왜: 비전문가에게 확률을 전달하는 근거 있는 형식이다.
- 근거: S74, S75.
- 노력 S · 위험: N이 가정에 민감 → 시나리오 병기 · 배점 (4).

**I-35. 경보 홍수 재현 타임라인** [시각화]
- 무엇: 정상 77분 타임라인에서 "단순 임계값 vs 최종 정책"의 경보를 막대로 보이고, 교대 단위로 외삽해 CI와 함께 보인다.
- 왜: 오경보 저감 효과를 한 장으로 전달한다.
- 근거: S35, S36(경보율 지표 관행).
- 노력 S · 위험: 77분에서의 외삽 → CI와 단서 · 배점 (4).

**I-36. 부하–진동 사분면 FP/FN 지도** [시각화][물리]
- 무엇: x축 전류 z, y축 진동 잔차 z인 평면에 정상·이상·FP·FN을 찍어 FP/FN이 몰리는 운전조건을 보인다.
- 왜: 채점 (3)항 "FN·FP가 집중되는 공정조건"에 시각적으로 직접 답한다.
- 근거: S40(관련 변수와의 관계), speculative.
- 노력 S · 위험 낮음 · 배점 (3).

**I-37. ISO식 이상구역 HI 띠 그래프와 불확실성 띠** [시각화]
- 무엇: 시간축 HI에 관찰/점검/정지 구역 색띠, 부트스트랩 불확실성 띠, 전류 regime 띠를 겹친다.
- 왜: 표준(ISO 13374 "trends as well as associated abnormality zones")에 맞는 표시다.
- 근거: S05, S76, S77.
- 노력 S · 위험 낮음 · 배점 (4).

### G. 외부 데이터·교차분야 개념

**I-38. UCI 유압 데이터로 외부 검증** [ML][평가]
- 무엇: CC BY 4.0인 UCI Condition Monitoring of Hydraulic Systems 데이터에서 센서 검증 층과 특징 파이프라인의 일반화를 점검한다. 예를 들어 펌프 내부 누설 등급을 전력·진동 저속 신호로 탐지하는지 본다. 사유, 방법, 출처를 보고서에 명시한다.
- 왜: 이상 사건이 하나뿐인 약점을 외부 공개 데이터로 일부 보완한다.
- 근거: S21, S19.
- 노력 L · 위험: 센서 구성과 수집률이 달라 직접 비교가 어려움, 시간 소모, 규정상 명시 필요 · 배점 (5)(2).

**I-39. FP 유형학(보안·임상 차용)** [평가][HITL] [SC]
- 무엇: FP를 (1) 검출기 오류, (2) benign trigger(실제 편차지만 정당한 원인, 예: 부하 변화), (3) 계측, (4) 진짜지만 조치 불필요(일시적)로 나눈다. 우리 실험의 FP를 이 틀로 분류해 보고한다.
- 왜: "오경보 조건 분석"의 구조를 주며, 채점 (3)항의 분석 깊이를 높인다.
- 근거: S66, S51.
- 노력 S · 위험 낮음 · 배점 (3).

**I-40. 채널 투표 규칙(다중 신호 확인)** [의사결정]
- 무엇: 채널별 이상 플래그(상부 진동, 하부 진동, 전류 잔차) 중 2개 이상일 때만 "기계 이상" 등급으로 올린다. 1개뿐이면 "계측 의심/관찰"로 둔다.
- 왜: 다중 신호 확인이 임상 오경보 저감의 핵심이었다.
- 근거: S58, S51. 안전계장의 MooN 투표와의 유비는 [미검증].
- 노력 S · 위험: 세 채널이 같은 양의 중복 측정이 아니라서 고장이 한 채널에만 보일 수 있음 → I-02와 함께 쓰고 알림은 유지 · 배점 (4)(5).

### 최소 핵심 세트 제안(R9 판단)

- **반드시:** I-01, I-02, I-05, I-14, I-17, I-18, I-20, I-24, I-25, I-26
  - 이 10개가 "데이터 진단 → 오경보 저감 모델 → 정직한 평가 → 현장 의사결정"을 한 줄로 잇는다.
- **기준선 비교:** I-12, I-13 (+ I-07)
- **가산점 후보([SC] 중 저비용):** I-09, I-11, I-19, I-30, I-33, I-39
- **후순위·향후 계획:** I-08, I-15, I-16, I-29의 구현, I-38
