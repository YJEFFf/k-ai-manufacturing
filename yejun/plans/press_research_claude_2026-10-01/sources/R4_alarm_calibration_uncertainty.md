# R4 — 오경보 통제·경보관리·확률 보정·소표본 불확실성 조사 보고서

- 작성일: 2026-10-01 · 작성: 리서치 에이전트 R4
- 대상 과제: ③ 진동·전류 시계열 기반 프레스 유압펌프 이상 조기탐지 및 오경보 분석
- 독립성: `yejun/` 폴더와 저장소 git 이력은 열지 않았다. 원시 데이터(`데이터셋/프레스_유압펌프_예지보전/data/`)만 읽기 전용으로 사용했다.
- 웹 검증: WebSearch 예산이 조사 중간에 소진되어(세션 공유 한도 200회), 이후는 WebFetch와 공개 API(Crossref, PubMed E-utilities, arXiv API, Europe PMC, e-나라표준인증 검색, PyPI)로 1차 출처를 직접 확인했다.

## 0. 표기 규칙

- **검증 상태**
  - `opened(본문)`: 원문 페이지·PDF를 직접 열어 해당 서술을 확인함.
  - `opened(초록)`: 초록·요약 페이지만 확인함.
  - `opened(목차)`: 공식 미리보기·목차·서문만 확인함(본문 표 값은 미확인).
  - `opened(메타)`: Crossref/PubMed/arXiv API로 저자·제목·권호·DOI만 확인함. 내용 서술은 일반 지식에 의존하므로 보고서 인용 전에 원문을 다시 확인해야 함.
  - `search-only`: 검색 스니펫으로만 확인함.
  - `unverified`: 확인하지 못함.
- **등급**: A = 동료심사 저널·주요 학회·국제/국가 표준·정부/공공기관, B = 평판 있는 프리프린트·기술보고서·학위논문·제조사 기술문서·업계 단체 지침, C = 블로그·포럼·벤더 홍보(근거가 아니라 단서로만 사용).
- **[계산]**: 이 조사에서 원시 CSV로 직접 계산한 값이다. 스크립트는 `scratchpad/research/` 아래 `burst_stats.py`, `neff2.py`, `drift.py`, `persist.py`, `ci.py`, `regime.py`, `cusum.py`, `we_arl2.py`에 있다. 팀 저장소의 산출물이 아니므로 다시 실행해 검증해야 한다. 분위수 임계는 대부분 표본 안에서 정했기 때문에 **낙관적으로 나온 값**이다.

---

## 1. 핵심 요약

1. **이 펌프 알림은 "경보(alarm)"인가 "알림(alert)"인가부터 정해야 한다.** ISA-18.2-2016과 IEC 62682:2022는 경보를 "운전원에게 적시 대응이 필요한 설비 고장·공정 이탈·비정상 상태를 알리는 가청/가시 수단"으로 정의한다 [S01, S02, S04]. EEMUA 191 4판(2024)은 응답 의무가 없는 설비상태 정보를 alert로 분리하고, 정비팀 일일 보고로 돌릴 수 있다고 정리했다 [S05, S06]. 따라서 3단계(주의/경고/위험) 가운데 **주의는 비가청 alert(정비 보고)**, **경고·위험만 경보**로 설계하자. 그러면 운전원 콘솔당 평균 약 1건/10분, 10분 최대 10건 이하, 플러드 시간 1% 미만 같은 ISA/IEC 성능지표를 펌프 하나가 잠식하지 않는다는 논리가 선다 [S08].
2. **버스트 단위로 바꿔 보면 숫자가 냉혹하다 [계산].** 정상 1.28시간에 버스트 599개(약 467개/시간)가 있다.
   - 버스트당 오경보 확률 α=0.01이면 시간당 4.7건, 교대(8시간)당 37건이다.
   - 교대당 1건이 목표라면 α≈2.7×10⁻⁴가 필요하다. 콘포멀 p값은 1/(n+1) 단위로만 움직이므로 보정용 정상 버스트가 3,703개 이상 있어야 한다.
   - Neyman–Pearson 우산 알고리즘으로 α=0.001을 δ=0.05로 보장하려 해도 n≥2,995가 필요하다 [S79].
   - **결론: 버스트 하나로 판정하는 방식으로는 교대 단위 예산을 보장할 수 없다.** 지속성 규칙, CUSUM 같은 누적 통계, 상태 기반 억제가 필수다.
3. **지속성 규칙은 효과가 크지만 함정이 있다 [계산].**
   - 상단 진동 RMS의 95분위 임계를 버스트 하나에 적용하면 정상 구간에 경보 25회(19.5회/시간)가 난다. 3연속(3-of-3) 규칙이면 0회이고, 이상 에피소드는 3번째 버스트(약 15–20초)에서 잡힌다.
   - 2연속 규칙은 i.i.d. 이론값(1.1회/시간)의 3.5배인 3.9회/시간이 나왔다. 00:40–01:00 구간의 느린 드리프트 때문이다.
   - 단측 CUSUM(k=0.5)을 교대당 1건(ARL0≈3,737 버스트)에 맞추면 h≈6.37이고, 1σ 이동의 탐지 지연은 약 13 버스트(약 1.7분)다.
   - 그러나 AR(1) 상관 ρ=0.2만 있어도 ARL0가 3,767에서 760으로 1/5이 된다(몬테카를로) [S26, S31, S32].
   - Western Electric 보조 규칙 4개를 모두 켜면 ARL0가 370에서 약 92로 줄어든다 [S30, 재현].
4. **정상 데이터 안에 이미 "정상 운전 변화"가 들어 있다 [계산].**
   - 01:00–01:10에 진동·전류 RMS가 평소의 약 절반으로 떨어지는 저부하 구간이 있다.
   - 0–30분 데이터로 학습하고 30–60분으로 보정한 **양측** 점수(Mahalanobis)는 이 구간에서 명목 α=0.05 대비 오경보율이 **19.8%**(약 4배)였다.
   - "증가만 보는" **단측** 점수는 0.8%였다.
   - 과제가 요구하는 "정상 운전 변화가 FP로 오판되는 조건" 분석의 실제 사례로 바로 쓸 수 있다. 상태 기반 억제와 단측 점수 설계의 근거도 된다 [S01 §11.9·§12.4, S02 3.1.4 adaptive alarm, S13 §8.4].
5. **콘포멀 보장은 버스트 단위·교환가능성 가정·주변(marginal) 보장이다** [S38, S46].
   - 보정집합을 고정하면 실제 오경보율은 Beta(l, n+1−l)를 따른다. n=236, α=0.01이면 평균 0.84%, 95% 상한 2.0%다 [계산].
   - 시계열 의존이 있으면: β-mixing 같은 조건에서 작은 커버리지 손실만 보면 유효하고 [S42], 가중 콘포멀은 총변동 거리만큼 손실이 생기며 [S39], 블록 순열로 근사 유효하다 [S41].
   - **ACI는 장기 오경보 비율을 α로 수렴시키도록 "강제"한다.** 그래서 고장이 계속되는 동안 임계를 올려 경보를 지워버릴 수 있다(Prop. 4.1에서 나오는 우리 해석) [S40]. 갱신은 확인된 정상 구간에서만 해야 한다.
6. **확률 보정은 이상 에피소드가 1개(21 버스트)뿐이라는 점이 핵심 제약이다.**
   - 이상과 정상이 완전히 분리되면 Platt 로지스틱 보정의 기울기가 무한대로 발산한다. Platt 본인이 목표값 평활 t₊=(N₊+1)/(N₊+2), t₋=1/(N₋+2)로 이 문제를 다뤘다 [S58].
   - 방어 가능한 보고 방식은 두 값을 분리하는 것이다.
     - (a) 정상 대비 꼬리확률(콘포멀 p값)
     - (b) 명시한 사전확률 π를 둔 P(이상|x, π) [S72, S73]
   - 예: 학습셋 유병률(3.4%) 기준으로 0.99로 보정된 값은 π=10⁻⁴이면 0.22가 된다 [계산].
   - Venn–Abers의 (p₀, p₁) 구간 폭은 소표본 불확실성을 그대로 보여준다 [S63].
7. **소표본 결과는 정직하게 보고해야 한다 [계산].**
   - 에피소드 1개 중 1개 탐지의 Clopper–Pearson 95% CI는 [0.025, 1]이다 [S81].
   - "21/21 버스트 탐지, CI [0.839, 1]"이라고 쓰면 버스트 간 의존을 무시한 과신이다.
   - 정상 1.28시간 동안 오경보 0건이면 시간당 95% 상한은 2.34건이다(3/T 규칙) [S85, S87].
   - 교대당 1건 이하를 95%로 보이려면 오경보 0건인 정상 운전이 24시간 이상, 주당 1건 이하는 503시간 이상 필요하다. 이를 **섀도 운전 검증 계획**으로 제시할 수 있다.
8. **의사결정 규칙은 "비용 최소화 + 경보 예산 제약"을 섞는 것을 권장한다.**
   - 비용비 c_FN/c_FP=100이면 사후확률 임계는 p*≈0.0099다 [S73]. π=10⁻⁴이면 우도비 100 이상이 필요하다 [계산].
   - 비용만으로는 경보 피로를 담지 못한다. 근거:
     - 응답률이 경보 신뢰도에 맞춰진다(probability matching) [S93].
     - 오경보가 잦은 자동화가 놓침이 잦은 자동화보다 성과를 더 해친다 [S94].
     - 단, 항공교통관제 현장에서는 반례가 있다 [S95].
   - 그래서 예산 제약(NP)과 비용 최소화를 함께 쓴다 [S79, S80].
9. **평가 단위를 이벤트로 바꿔야 한다.**
   - point-adjust F1은 무작위 점수도 최신 기법처럼 보이게 만든다 [S96].
   - 주 지표 후보:
     - 이벤트 단위 탐지 지연과 FA/시간
     - 같은 경보 시간 비율을 쓰는 우연 예측기와의 비교 [S100]
     - 발작예측특성(민감도 대 시간당 오예측률) 형식의 곡선 [S99]
10. **표준은 인용 방식에 주의해야 한다.**
    - ISA/IEC/EEMUA/ISO는 유료다. 조항 번호와 개별 수치만 인용하고 표 전체를 옮기지 않는다.
    - IEC 62682는 e-나라표준인증 검색(2026-10-01)에서 KS 부합화 0건이었다.
    - 상태감시 계열(KS B ISO 17359, 13379-1/-2, 13381-1, 20816-1, 10816-7 등)은 KS로 존재한다 [S15].

---

## 2. 출처 표

열 구성: 인용 · 유형/등급 · 검증 · 위험신호 · 라이선스/저작권 · 공모전 보고서 사용 위험

### 2.1 표준·지침·업계 문서

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S01 | ANSI/ISA-18.2-2016, *Management of Alarm Systems for the Process Industries*. ISA, 승인 2016-03-17, ISBN 978-1-941546-86-4 (목차 발췌: grahamnasby.com/files_publications/ANSI-ISA-18.02-2016_TOC-excerpt.pdf) | 국가표준 / A | opened(목차): §9.5, §10.5, §11.7–11.9, §12.4–12.5, §16.4, §16.8, 표5–7 확인 | 목차는 위원 개인 사이트에 올라온 발췌본 | ⓒISA 유료, 전재 금지 | 조항·표 번호와 수치만 인용, 표 전재 금지 |
| S02 | IEC 62682:2022 Ed.2.0 (2022-12), *Management of alarm systems for the process industries* (VDE 미리보기 CMV) | 국제표준 / A | opened(목차): §16.3.3–16.3.10, 표5–7, 3.1.4 adaptive alarm, 1판(2014) 대체 확인 | 없음 | ⓒIEC 유료 | 조항 번호만 인용 |
| S03 | ISA-TR18.2.3-2015, *Basic Alarm Design* (승인 2015-06-12)와 ISA-TR18.2.3-2024 미리보기 서문 | 기술보고서 / B | opened(목차): §8.2 deadband, §8.3 on/off-delay, §8.4 filtering, §7.13·§7.15, 그림 9·13·14 확인. 2024 서문에서 TR18.2.8 *Guidelines for Non-alarm Notifications* 언급 확인 | 수치는 그림(이미지)이라 미확인 | ⓒISA 유료 | 그림 재사용 금지 |
| S04 | ISA-TR18.2.5-2022, *Alarm System Monitoring, Assessment, and Auditing* (ISA 미리보기) | 기술보고서 / B | opened(목차): 서문, 3.1.2 active(주석: deadband·delay가 활성 상태를 바꿈), 3.1.3 alarm 정의 확인 | 없음 | ⓒISA | 정의 문장은 짧게 인용 |
| S05 | EEMUA Publication 191 Ed.4, *Alarm systems – a guide to design, management and procurement*, 2024-11, ISBN 978 0 85931 243 1 (EEMUA 공식 목차 PDF) | 업계 지침 / B | opened(목차): §2.3.1 Alerts, §2.6, §6.4.5 Deadband, §7.4.4–7.4.8, 표9–11·15–19·27, 부록3 확인 | 표 값 미확인. 3판(2013)과 수치가 다를 수 있음 | ⓒEEMUA 유료 | 표 번호만 인용 |
| S06 | Brazier A. (2025) "Alarm management – update to EEMUA 191", *IChemE Symposium Series* No.172 (Hazards 35) | 학회 논문(업계) / B | opened(본문): alert·prompt 구분, "정비팀 일일 보고용 alert", 우선순위가 낮아도 무시하면 안 된다는 원칙 확인 | EEMUA를 대표해 작성(이해관계) | ⓒIChemE, 그림 ⓒEEMUA | 문장 인용만, 그림 금지 |
| S07 | Bransby M.L. & Jenkinson J., *The management of alarm systems*, HSE Contract Research Report CRR 166/1998, ISBN 0 7176 1515 4 (ISBN은 검색 스니펫으로만 확인; humanfactors101.com 사본) | 정부 위탁 연구보고서 / A | opened(본문): §4.4 평균 경보율(10분당 1건), §4.6, §4.7, §4.10(우선순위 3단계, 최고 우선순위는 허위 가능성 0) 확인 | 제3자 호스팅 사본. PDF에는 "First published 1997"이라 1998 표기와 다름 | Crown copyright, 무단 복제 금지 | 요지 인용만 |
| S08 | IChemE Safety Centre (2021-11) *Lead Process Safety Metrics – Alarm Rationalisation* (guidance) | 전문단체 지침 / B | opened(본문): IEC/ISA/EEMUA 지표 표(10분당 약 1건 목표·약 2건 차선, 10분 최대 ≤10, 플러드 시간 <1%, 상위10 기여, chattering·fleeting, stale <5, 3단계 약 80/15/5) 확인 | 표준 수치의 2차 재현 | ⓒIChemE | ISA 원문 대신 2차 출처임을 명시 |
| S09 | Dubois L. (M.A.C. Solutions/ProcessVue), "The sense and nonsense of Alarm system performance KPIs" (연도 미상) | 벤더 백서 / C | opened(본문): EEMUA 3판 p.96–97 수치 재인용, ISA 2016판에서 KPI 4개가 빠진 경위 확인 | 벤더(분석 도구 판매). 저자는 ISA18 투표위원(S01 명단에서 확인) | ⓒ벤더 | 근거가 아니라 단서로만 사용 |
| S10 | processonline.com.au, "Improving alarm management with ISA-18.2: Part 1" | 업계 매체 / C | opened(본문): 데드밴드·지연 표(유량 5%/15초, 레벨 5%/60초, 압력 2%/15초, 온도 1%/60초)를 ISA-18.2-2009 출처로 제시 | 2차 인용. 2016판 본문에는 해당 그림 없음 | ⓒ매체 | 수치는 "2009판, 2차 인용"으로 표기 |
| S11 | NAMUR NE 107, *Self-monitoring and diagnosis of field devices* (2006, 개정 2017-04-10, 개정 2025-07-15) (namur.net 공지) | 사용자협회 권고 / B | opened(공지): 상태신호 F·C·S·M과 2017·2025 개정 확인 | 본문 미확인 | ⓒNAMUR 유료 | 상태신호 이름만 인용 |
| S12 | Wolff O. (2014) "What does the Process Automation understand under Diagnosis?", ODVA Industry Conference | 업계 학회 / B–C | opened(본문): FCSM 매핑, 사용자가 범주·우선순위를 설정할 수 있음 확인 | 제조사 소속 저자 | ⓒODVA | 단서로만 사용 |
| S13 | ISO 17359:2018 (3판), *Condition monitoring and diagnostics of machines — General guidelines*; KS B ISO 17359 (개정/확인 2024-12-20) | 국제/국가표준 / A | opened(본문 일부, iTeh 샘플): §8.4 운전조건(고장과 운전조건 변화 구분), §8.5 LTTF, §8.9·§8.10·§9.3 목차 확인. §8.9 본문은 search-only | 없음 | ⓒISO/KS 유료 | 조항 번호만 인용 |
| S14 | ISO 20816-1:2016 (1판, 2016-11-15), *Mechanical vibration — Part 1: General guidelines*; KS B ISO 20816-1 (2023-12-29) | 국제/국가표준 / A | opened(목차·범위): §6.3.2–6.3.3, §6.4.2 Setting of ALARMS, §6.4.3 Setting of TRIPS 확인. "기준선 + B영역 상한의 25%" 규칙은 search-only(벤더 사이트) | 25% 규칙 원문 미확인 | ⓒISO | 25% 수치 사용 시 "미확인" 표기 |
| S15 | e-나라표준인증 KS 검색 결과 (2026-10-01 조회): 번호 "62682" 0건, 표준명 "경보 관리" 0건. KS B ISO 17359, 13379-1/-2, 13381-1, 13373-1/2/3, 13374-1, 20816-1, 10816-7 존재 | 정부 DB / A | opened(검색 결과) | 다른 번호로 부합화됐다면 놓칠 수 있음 | 공공 | 사실 서술 가능 |

### 2.2 경보 설계 연구

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S16 | Wang J., Yang F., Chen T., Shah S.L. (2016) "An overview of industrial alarm systems: main causes for alarm overloading, research status, and open problems", *IEEE T-ASE* 13(2):1045–1061, doi:10.1109/TASE.2015.2464234 | 저널 / A | opened(본문, 저자 사본): chattering 정의(ISA 인용), FAR·MAR 상충, i.i.d. 밖에서는 이론 관계가 어렵다는 점, cry-wolf, 짧은 지속(<20초)·stale(>24시간) 확인 | 없음 | ⓒIEEE | 그림 재사용은 허가 필요 |
| S17 | Adnan N.A., Izadi I., Chen T. (2011) "On expected detection delays for alarm systems with deadbands and delay-timers", *J. Process Control* 21(9):1318–1331, doi:10.1016/j.jprocont.2011.06.019 | 저널 / A | opened(메타)와 초록 스니펫(마르코프 과정으로 지연 계산) | 없음 | ⓒElsevier | 수식은 원문 확인 후 사용 |
| S18 | Xu J., Wang J., Izadi I., Chen T. (2012) "Performance assessment and design for univariate alarm systems based on FAR, MAR, and AAD", *IEEE T-ASE* 9(2):296–307, doi:10.1109/TASE.2011.2176490 | 저널 / A | opened(메타) | 없음 | ⓒIEEE | 동일 |
| S19 | Adnan N.A., Cheng Y., Izadi I., Chen T. (2013) "Study of generalized delay-timers in alarm configuration", *J. Process Control* 23(3):382–395, doi:10.1016/j.jprocont.2012.12.013 | 저널 / A | opened(메타)와 스니펫 | 없음 | ⓒElsevier | 동일 |
| S20 | Kondaveeti S.R. et al. (2013) "Quantification of alarm chatter based on run length distributions", *Chem. Eng. Res. Des.* 91(12):2550–2558, doi:10.1016/j.cherd.2013.02.028 | 저널 / A | opened(메타) | 없음 | ⓒElsevier | 동일 |
| S21 | Naghoosi E., Izadi I., Chen T. (2011) "Estimation of alarm chattering", *J. Process Control* 21(9):1243–1249, doi:10.1016/j.jprocont.2011.07.015 | 저널 / A | opened(메타) | 없음 | ⓒElsevier | 동일 |
| S22 | Cheng Y., Izadi I., Chen T. (2013) "Optimal alarm signal processing: filter design and performance analysis", *IEEE T-ASE* 10(2):446–451, doi:10.1109/TASE.2012.2233472 | 저널 / A | opened(메타) | 없음 | ⓒIEEE | 동일 |
| S23 | Izadi I., Shah S.L., Shook D.S., Kondaveeti S.R., Chen T. (2009) "A framework for optimal design of alarm systems", *IFAC Proc. Vol.* 42:651–656, doi:10.3182/20090630-4-ES-2003.00108 | 학회 / A | opened(메타) | 없음 | ⓒIFAC/Elsevier | 동일 |
| S24 | Wang J., Hu W., Chen T. (2024) *Intelligent Industrial Alarm Systems*, Springer (1장 doi:10.1007/978-981-97-6516-4_1, 2장 _2) | 학술서 / A | opened(메타) | 없음 | ⓒSpringer | 동일 |

### 2.3 SPC·순차검정·온라인 모니터링

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S25 | Montgomery D.C. (2019) *Introduction to Statistical Quality Control*, 8th ed., Wiley, ISBN 978-1-119-39930-8 | 교재 / A | opened(메타, Wiley 페이지) | 없음 | ⓒWiley | 표 전재 금지 |
| S26 | NIST/SEMATECH *e-Handbook of Statistical Methods* §6.3.2.3 CUSUM, ARL 표(pmc3231), §6.3.2.4 EWMA | 정부기관 / A | opened(본문): 단측 CUSUM k=0.5에서 h=4 ARL0 336, h=5 ARL0 930, 1σ에서 8.38·10.4, Shewhart 371, EWMA λ 0.2–0.3 확인 | 없음 | 미국 정부 저작물(공개) | 인용·재사용 위험 낮음 |
| S27 | Page E.S. (1954) "Continuous inspection schemes", *Biometrika* 41(1-2):100–115, doi:10.1093/biomet/41.1-2.100 | 저널 / A | opened(메타) | 없음 | ⓒOUP | 인용만 |
| S28 | Roberts S.W. (1959) "Control chart tests based on geometric moving averages", *Technometrics* 1(3):239–250, doi:10.1080/00401706.1959.10489860 | 저널 / A | opened(메타) | 없음 | ⓒASA/T&F | 인용만 |
| S29 | Lucas J.M., Saccucci M.S. (1990) "Exponentially weighted moving average control schemes: properties and enhancements", *Technometrics* 32(1):1–12, doi:10.1080/00401706.1990.10484583 | 저널 / A | opened(메타) | 없음 | ⓒASA/T&F | 인용만 |
| S30 | Champ C.W., Woodall W.H. (1987) "Exact results for Shewhart control charts with supplementary runs rules", *Technometrics* 29(4):393–399, doi:10.1080/00401706.1987.10488266 | 저널 / A | opened(메타). ARL0 약 92는 자체 몬테카를로로 재현(92.3±0.3) | 정확값 91.75는 원문 미확인 | ⓒASA/T&F | 재현값으로 서술 |
| S31 | Alwan L.C., Roberts H.V. (1988) "Time-series modeling for statistical process control", *J. Bus. Econ. Stat.* 6(1):87–95, doi:10.1080/07350015.1988.10509640 | 저널 / A | opened(메타) | 없음 | ⓒASA | 인용만 |
| S32 | Montgomery D.C., Mastrangelo C.M. (1991) "Some statistical process control methods for autocorrelated data", *J. Quality Technology* 23(3):179–193, doi:10.1080/00224065.1991.11979321 | 저널 / A | opened(메타) | 없음 | ⓒASQ/T&F | 인용만 |
| S33 | Wald A. (1945) "Sequential tests of statistical hypotheses", *Ann. Math. Stat.* 16(2):117–186, doi:10.1214/aoms/1177731118 | 저널 / A | opened(메타) | 없음 | ⓒIMS | 인용만 |
| S34 | Lorden G. (1971) "Procedures for reacting to a change in distribution", *Ann. Math. Stat.* 42(6):1897–1908, doi:10.1214/aoms/1177693055 | 저널 / A | opened(메타) | 없음 | ⓒIMS | 인용만 |
| S35 | Moustakides G.V. (1986) "Optimal stopping times for detecting changes in distributions", *Ann. Stat.* 14(4), doi:10.1214/aos/1176350164 | 저널 / A | opened(메타). 쪽수 미확인 | 없음 | ⓒIMS | 인용만 |
| S36 | Basseville M., Nikiforov I.V. (1993) *Detection of Abrupt Changes: Theory and Application*, Prentice-Hall (저자 공개 PDF: people.irisa.fr/Michele.Basseville/kniga/) | 학술서 / A | opened(배포 페이지) | 없음 | 원 출판사 저작권, 저자 무료 배포 | 그림 재사용 금지 |
| S37 | Coble J.B. et al. (2012) *A Review of Sensor Calibration Monitoring for Calibration Interval Extension in Nuclear Power Plants*, PNNL-21687, doi:10.2172/1061413 | 미 에너지부 연구소 보고서 / A–B | opened(본문): 잔차 기반 thresholding·EULM·SPRT(Wald 1945)의 실무 사용 확인 | 없음 | 미국 정부 후원(대체로 공개) | 인용 가능 |

### 2.4 콘포멀·FDR·변화탐지

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S38 | Bates S., Candès E., Lei L., Romano Y., Sesia M. (2023) "Testing for outliers with conformal p-values", *Ann. Stat.* 51(1):149–178, doi:10.1214/22-AOS2244 | 저널 / A | opened(초록): 주변 유효성, 시험점 간 의존, 보정조건부 유효 p값, PRDS와 BH FDR 확인 | 없음 | arXiv판 CC BY 4.0 | arXiv판 그림은 출처 표기 후 재사용 가능 |
| S39 | Barber R.F., Candès E.J., Ramdas A., Tibshirani R.J. (2023) "Conformal prediction beyond exchangeability", *Ann. Stat.* 51(2), doi:10.1214/23-AOS2276 | 저널 / A | opened(초록): 가중 분위수, 총변동 거리로 표현한 손실 확인. 쪽수 미확인 | 없음 | arXiv 비독점 라이선스 | 그림 재사용은 허가 필요 |
| S40 | Gibbs I., Candès E. (2021) "Adaptive conformal inference under distribution shift", *NeurIPS* 34 | 학회 / A | opened(본문): 식(2) α_{t+1}=α_t+γ(α−err_t), Prop. 4.1 abs(평균 err − α) ≤ (max{α₁,1−α₁}+γ)/(Tγ) 확인 | 없음 | arXiv 비독점 | 수식 인용 가능 |
| S41 | Chernozhukov V., Wüthrich K., Zhu Y. (2018) "Exact and robust conformal inference methods for predictive machine learning with dependent data", *COLT*, PMLR 75:732–749 | 학회 / A | opened(초록): 교환가능하면 정확, 약한 의존에서 근사 유효, 블록 순열 확인 | 없음 | PMLR | 인용만 |
| S42 | Oliveira R.I., Orenstein P., Ramos T., Romano J.V. (2024) "Split conformal prediction and non-exchangeable data", *JMLR* 25(225) (arXiv:2203.15885) | 저널 / A | opened(초록): 많은 비교환 과정에서 작은 커버리지 페널티로 유효 확인 | 없음 | JMLR 오픈 액세스(CC BY 4.0로 알려짐, 미확인) | 인용 가능 |
| S43 | Laxhammar R., Falkman G. (2015, 온라인 2013) "Inductive conformal anomaly detection for sequential detection of anomalous sub-trajectories", *Ann. Math. Artif. Intell.* 74(1-2):67–94, doi:10.1007/s10472-013-9381-7 | 저널 / A | opened(메타) | 없음 | ⓒSpringer | 인용만 |
| S44 | Laxhammar R., Falkman G. (2014) "Online learning and sequential anomaly detection in trajectories", *IEEE TPAMI* 36(6):1158–1173, doi:10.1109/TPAMI.2013.172 | 저널 / A | opened(초록, PubMed): 즉흥적 임계는 경보율 보정이 나쁘고, 콘포멀은 임계 보정에 근거를 준다는 점 확인 | 없음 | ⓒIEEE | 인용만 |
| S45 | Vovk V. (2013) "Conditional validity of inductive conformal predictors", *Machine Learning* 92(2-3):349–376, doi:10.1007/s10994-013-5355-6 | 저널 / A | opened(메타) | 없음 | ⓒSpringer | 인용만 |
| S46 | Angelopoulos A.N., Bates S. (2023) "Conformal prediction: a gentle introduction", *Found. Trends ML* 16(4):494–591, doi:10.1561/2200000101 (arXiv:2107.07511v6) | 저널 튜토리얼 / A | opened(본문): 보정조건부 커버리지가 Beta(n+1−l, l), l=⌊(n+1)α⌋(Vovk)이고 보정점 약 1000개 권장 확인 | 없음 | arXiv 비독점 | 수식 인용 가능 |
| S47 | Benjamini Y., Hochberg Y. (1995) "Controlling the false discovery rate", *JRSS-B* 57(1):289–300, doi:10.1111/j.2517-6161.1995.tb02031.x | 저널 / A | opened(메타) | 없음 | ⓒRSS/OUP | 인용만 |
| S48 | Liang Z., Sesia M., Sun W. (2024) "Integrative conformal p-values for out-of-distribution testing with labelled outliers", *JRSS-B* 86(3):671–693, doi:10.1093/jrsssb/qkad138 (arXiv:2208.11111) | 저널 / A | opened(초록): 라벨된 이상을 쓰면서도 유효성을 유지하고 FDR도 다룸 확인 | 없음 | ⓒRSS/OUP | 인용만 |
| S49 | Volkhonskiy D., Burnaev E., Nouretdinov I., Gammerman A., Vovk V. (2017) "Inductive conformal martingales for change-point detection", PMLR 60:132–153 | 학회 / A | opened(초록): i.i.d.만 가정하고 CUSUM·SR와 비교 확인 | 없음 | PMLR | 인용만 |
| S50 | Vovk V. (2021) "Testing randomness online", *Statistical Science* 36(4), doi:10.1214/20-STS817 | 저널 / A | opened(메타) | 없음 | ⓒIMS | 인용만 |
| S51 | Shin J., Ramdas A., Rinaldo A. "E-detectors: a nonparametric framework for sequential change detection", arXiv:2203.03532 (v4) | 프리프린트(게재처 미확인) / B | opened(초록): 비점근 ARL 한계 확인 | 게재 여부 미확인 | arXiv | "프리프린트" 표기 |
| S52 | Ramdas A. (2026) "Universality of e-detectors for ARL control", arXiv:2608.12660 | 프리프린트 / B | opened(초록): 임계 b에서 ARL ≥ b, P(T≤t) ≤ t/b 확인 | 심사 전 최신 프리프린트 | arXiv | 보조 근거로만 사용 |
| S53 | Javanmard A., Montanari A. (2018) "Online rules for control of false discovery rate and false discovery exceedance", *Ann. Stat.* 46(2), doi:10.1214/17-AOS1559 | 저널 / A | opened(메타) | 없음 | ⓒIMS | 인용만 |
| S54 | Siffer A., Fouque P.-A., Termier A., Largouet C. (2017) "Anomaly detection in streams with extreme value theory", *KDD*, pp.1067–1075, doi:10.1145/3097983.3098144 | 학회 / A | opened(메타) | 없음 | ⓒACM | 인용만 |
| S55 | Vignotto E., Engelke S. (2020) "Extreme value theory for anomaly detection – the GPD classifier", *Extremes* 23(4):501–520, doi:10.1007/s10687-020-00393-0 | 저널 / A | opened(메타) | 없음 | CC BY 4.0 | 재사용 가능(출처 표기) |

### 2.5 점수→확률 보정·평가지표·비용 결정

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S56 | Kriegel H.-P., Kröger P., Schubert E., Zimek A. (2011) "Interpreting and unifying outlier scores", *SDM*, pp.13–24, doi:10.1137/1.9781611972818.2 | 학회 / A | opened(메타). 방법은 PyOD 구현 코드(S101)로 간접 확인(erf 기반 Gaussian scaling) | 원문 미열람 | ⓒSIAM | 인용만 |
| S57 | Gao J., Tan P.-N. (2006) "Converting output scores from outlier detection algorithms into probability estimates", *ICDM*, pp.212–221, doi:10.1109/ICDM.2006.43 | 학회 / A | opened(메타) | 없음 | ⓒIEEE | 인용만 |
| S58 | Platt J.C. (1999) "Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods", in *Advances in Large Margin Classifiers*, MIT Press (저자 사본 1999-03-26) | 책 장 / A | opened(본문): 완전분리 시 기울기 발산, 목표값 식(13)(14) 확인 | 없음 | ⓒMIT Press | 식 인용 가능 |
| S59 | Zadrozny B., Elkan C. (2002) "Transforming classifier scores into accurate multiclass probability estimates", *KDD*, pp.694–699, doi:10.1145/775047.775151 | 학회 / A | opened(메타) | 없음 | ⓒACM | 인용만 |
| S60 | Niculescu-Mizil A., Caruana R. (2005) "Predicting good probabilities with supervised learning", *ICML*, pp.625–632, doi:10.1145/1102351.1102430 | 학회 / A | opened(메타) | 없음 | ⓒACM | 인용만 |
| S61 | Kull M., Silva Filho T., Flach P. (2017) "Beta calibration: a well-founded and easily implemented improvement on logistic calibration for binary classifiers", *AISTATS*, PMLR 54:623–631 | 학회 / A | opened(초록): 로지스틱 보정은 치우친 점수에서 나빠지고 항등함수를 포함하지 못함 확인 | 없음 | PMLR | 인용만 |
| S62 | Kull M., Silva Filho T.M., Flach P. (2017) "Beyond sigmoids…", *Electron. J. Stat.* 11(2), doi:10.1214/17-EJS1338SI | 저널 / A | opened(메타) | 없음 | EJS 오픈 액세스 | 인용 가능 |
| S63 | Vovk V., Petej I. (2014) "Venn-Abers predictors", *UAI 2014* (arXiv:1211.0025) | 학회 / A | opened(본문): 출력 (p₀,p₁), 구간 폭이 과적합 정도를 알려줌, 로그손실 최소최대 병합 p=p₁/(1−p₀+p₁) 확인 | 없음 | arXiv | 수식 인용 가능 |
| S64 | Guo C., Pleiss G., Sun Y., Weinberger K.Q. (2017) "On calibration of modern neural networks", *ICML*, PMLR 70:1321–1330 | 학회 / A | opened(초록): temperature scaling 확인 | 없음 | PMLR | 인용만 |
| S65 | Nixon J. et al. (2019) "Measuring calibration in deep learning", arXiv:1904.01685 | 프리프린트(CVPR Workshops 게재로 알려짐, 미확인) / B | opened(초록): ECE의 여러 결함 확인 | 게재처 미확인 | arXiv | 인용만 |
| S66 | Kumar A., Liang P., Ma T. (2019) "Verified uncertainty calibration", *NeurIPS* (arXiv:1909.10155) | 학회 / A | opened(초록): Platt·temperature 보정이 보고보다 덜 보정되고 오차 추정이 어렵다는 점 확인 | 없음 | arXiv | 인용만 |
| S67 | Roelofs R., Cain N., Shlens J., Mozer M.C. (2022) "Mitigating bias in calibration error estimation", *AISTATS* (arXiv:2012.08668) | 학회 / A | opened(초록): ECE_bin 추정 편향, 동일질량 bin 권장 확인 | 없음 | arXiv | 인용만 |
| S68 | Gneiting T., Raftery A.E. (2007) "Strictly proper scoring rules, prediction, and estimation", *JASA* 102(477):359–378, doi:10.1198/016214506000001437 | 저널 / A | opened(메타) | 없음 | ⓒASA | 인용만 |
| S69 | Brier G.W. (1950) "Verification of forecasts expressed in terms of probability", *Mon. Weather Rev.* 78(1):1–3 | 저널 / A | opened(메타) | 없음 | ⓒAMS | 인용만 |
| S70 | Murphy A.H. (1973) "A new vector partition of the probability score", *J. Appl. Meteorol.* 12(4):595–600 | 저널 / A | opened(메타) | 없음 | ⓒAMS | 인용만 |
| S71 | DeGroot M.H., Fienberg S.E. (1983) "The comparison and evaluation of forecasters", *The Statistician* 32(1/2):12– , doi:10.2307/2987588 | 저널 / A | opened(메타) | 끝 쪽 미확인 | ⓒRSS | 인용만 |
| S72 | Saerens M., Latinne P., Decaestecker C. (2002) "Adjusting the outputs of a classifier to new a priori probabilities: a simple procedure", *Neural Computation* 14(1):21–41, doi:10.1162/089976602753284446 | 저널 / A | opened(메타) | 없음 | ⓒMIT Press | 인용만 |
| S73 | Elkan C. (2001) "The foundations of cost-sensitive learning", *IJCAI-01* (저자 사본) | 학회 / A | opened(본문): §1.3 최적 결정 임계, 2×2 비용행렬의 자유도가 1이라는 점, §3 기저율 변경 정리 확인(PDF 글리프 깨짐으로 식 모양은 일반형으로 재서술) | 없음 | ⓒIJCAI | 식은 재서술해 인용 |
| S74 | Firth D. (1993) "Bias reduction of maximum likelihood estimates", *Biometrika* 80(1):27–38, doi:10.1093/biomet/80.1.27 | 저널 / A | opened(메타) | 없음 | ⓒOUP | 인용만 |
| S75 | Van Calster B. et al. (2016) "A calibration hierarchy for risk models was defined: from utopia to empirical data", *J. Clin. Epidemiol.* 74:167–176, doi:10.1016/j.jclinepi.2015.12.005 | 저널 / A | opened(메타) | 의료 분야(전이 시 주의) | ⓒElsevier | 인용만 |
| S76 | Van Calster B., McLernon D.J., van Smeden M., Wynants L., Steyerberg E.W. (2019) "Calibration: the Achilles heel of predictive analytics", *BMC Medicine* 17, doi:10.1186/s12916-019-1466-7 | 저널 / A | opened(메타) | 의료 분야 | CC BY 4.0 | 그림 재사용 가능(출처 표기) |
| S77 | Collins G.S., Ogundimu E.O., Altman D.G. (2016) "Sample size considerations for the external validation of a multivariable prognostic model: a resampling study", *Stat. Med.* 35(2):214–226, doi:10.1002/sim.6787 | 저널 / A | opened(메타). "사건 100개 이상, 가능하면 200개" 권고는 일반 지식(원문 재확인 필요) | 의료 분야 | CC BY 4.0 | 인용 전 원문 재확인 |
| S78 | Perini L., Vercruyssen V., Davis J. (2021, ECML PKDD 2020) "Quantifying the confidence of anomaly detectors in their example-wise predictions", LNCS pp.227–243, doi:10.1007/978-3-030-67664-3_14 | 학회 / A | opened(메타)와 PyOD 구현 코드(S101) | 없음 | ⓒSpringer | 인용만 |
| S79 | Tong X., Feng Y., Li J.J. (2018) "Neyman-Pearson classification algorithms and NP receiver operating characteristics", *Science Advances* 4(2):eaao1659, doi:10.1126/sciadv.aao1659 | 저널 / A | opened(본문, Europe PMC): 우산 알고리즘, 최소 표본 n ≥ log δ / log(1−α) 확인 | 없음 | CC BY-NC | 그림 재사용 시 비상업 조건 검토 필요(상금 있는 대회). 문장 인용 권장 |
| S80 | Scott C., Nowak R. (2005) "A Neyman–Pearson approach to statistical learning", *IEEE TIT* 51(11):3806–3819, doi:10.1109/TIT.2005.856955 | 저널 / A | opened(메타) | 없음 | ⓒIEEE | 인용만 |

### 2.6 소표본 구간·의존 표본

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S81 | Clopper C.J., Pearson E.S. (1934) "The use of confidence or fiducial limits illustrated in the case of the binomial", *Biometrika* 26(4):404–413, doi:10.1093/biomet/26.4.404 | 저널 / A | opened(메타). 값은 statsmodels로 계산 | 없음 | ⓒOUP | 인용만 |
| S82 | Wilson E.B. (1927) "Probable inference, the law of succession, and statistical inference", *JASA* 22(158):209–212, doi:10.1080/01621459.1927.10502953 | 저널 / A | opened(메타) | 없음 | ⓒASA | 인용만 |
| S83 | Brown L.D., Cai T.T., DasGupta A. (2001) "Interval estimation for a binomial proportion", *Statistical Science* 16(2), doi:10.1214/ss/1009213286 | 저널 / A | opened(메타). 쪽수 미확인 | 없음 | ⓒIMS | 인용만 |
| S84 | Agresti A., Coull B.A. (1998) "Approximate is better than 'exact' for interval estimation of binomial proportions", *Am. Stat.* 52(2):119–126 | 저널 / A | opened(메타) | 없음 | ⓒASA | 인용만 |
| S85 | Hanley J.A., Lippman-Hand A. (1983) "If nothing goes wrong, is everything all right? Interpreting zero numerators", *JAMA* 249(13):1743–1745, PMID 6827763 | 저널 / A | opened(메타, PubMed). 3/n 규칙은 수치로 확인(−ln 0.05=2.996) | 없음 | ⓒAMA | 인용만 |
| S86 | Jovanovic B.D., Levy P.S. (1997) "A look at the rule of three", *Am. Stat.* 51(2):137–139 | 저널 / A | opened(메타) | 없음 | ⓒASA | 인용만 |
| S87 | Garwood F. (1936) "Fiducial limits for the Poisson distribution", *Biometrika* 28(3-4):437–442 | 저널 / A | opened(메타). 값은 χ² 공식으로 계산 | 없음 | ⓒOUP | 인용만 |
| S88 | Zwiers F.W., von Storch H. (1995) "Taking serial correlation into account in tests of the mean", *J. Climate* 8(2):336–351 | 저널 / A | opened(메타) | 없음 | ⓒAMS | 인용만 |
| S89 | Künsch H.R. (1989) "The jackknife and the bootstrap for general stationary observations", *Ann. Stat.* 17(3), doi:10.1214/aos/1176347265 | 저널 / A | opened(메타). 쪽수 미확인 | 없음 | ⓒIMS | 인용만 |
| S90 | Politis D.N., Romano J.P. (1994) "The stationary bootstrap", *JASA* 89(428):1303–1313 | 저널 / A | opened(메타) | 없음 | ⓒASA | 인용만 |
| S91 | Politis D.N., White H. (2004) "Automatic block-length selection for the dependent bootstrap", *Econometric Rev.* 23(1):53–70 | 저널 / A | opened(메타) | 정오표(2009)가 있다고 알려짐, 미확인 | ⓒT&F | 인용만 |
| S92 | Field C.A., Welsh A.H. (2007) "Bootstrapping clustered data", *JRSS-B* 69(3):369–390 | 저널 / A | opened(메타) | 없음 | ⓒRSS | 인용만 |

### 2.7 인간요인·평가 방법

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S93 | Bliss J.P., Gilson R.D., Deaton J.E. (1995) "Human probability matching behaviour in response to alarms of varying reliability", *Ergonomics* 38(11):2300–2312 | 저널 / A | opened(초록, PubMed): 대학생 138명, 약 90%가 응답률을 경보 신뢰도에 맞춤 확인 | 실험실·학생 표본 | ⓒT&F | 인용만 |
| S94 | Dixon S.R., Wickens C.D., McCarley J.S. (2007) "On the independence of compliance and reliance: are automation false alarms worse than misses?", *Human Factors* 49(4):564–572 | 저널 / A | opened(초록): 32명, 오경보 경향 자동화가 놓침 경향보다 성과를 더 해침 확인 | 소표본 실험실 | ⓒHFES/SAGE | 인용만 |
| S95 | Wickens C.D. et al. (2009) "False alerts in air traffic control conflict alerting system: is there a 'cry wolf' effect?", *Human Factors* 51(4):446–462 | 저널 / A | opened(초록): 경보 495건 중 45%가 오경보였지만 cry-wolf 행동은 보이지 않음(반례) 확인 | 영역 차이 | ⓒHFES/SAGE | 반론으로 인용 |
| S96 | Kim S., Choi K., Choi H.-S., Lee B., Yoon S. (2022) "Towards a rigorous evaluation of time-series anomaly detection", *AAAI* 36(7):7194–7201, doi:10.1609/aaai.v36i7.20680 | 학회 / A | opened(초록): PA 프로토콜에서는 무작위 점수도 최신 기법처럼 보임 확인 | 없음 | ⓒAAAI | 인용만 |
| S97 | Lavin A., Ahmad S. (2015) "Evaluating real-time anomaly detection algorithms – the Numenta Anomaly Benchmark", *ICMLA*, pp.38–44, doi:10.1109/ICMLA.2015.141 | 학회 / A | opened(메타) | NAB 점수법 비판이 있다고 알려짐(미확인) | ⓒIEEE | 인용만 |
| S98 | Wu R., Keogh E.J. (2021) "Current time series anomaly detection benchmarks are flawed and are creating the illusion of progress", *IEEE TKDE*, doi:10.1109/TKDE.2021.3112126 | 저널 / A | opened(메타) | 없음 | ⓒIEEE | 인용만 |
| S99 | Winterhalder M. et al. (2003) "The seizure prediction characteristic: a general framework to assess and compare seizure prediction methods", *Epilepsy & Behavior* 4(3):318–325 | 저널 / A | opened(초록): 582시간·발작 88회로 평가 틀 제안 확인. SOP/SPH 세부는 미확인 | 의료 영역 | ⓒElsevier | 개념만 차용 |
| S100 | Snyder D.E., Echauz J., Grimes D.B., Litt B. (2008) "The statistics of a practical seizure warning system", *J. Neural Eng.* 5(4):392–401 (PMC2888045) | 저널 / A | opened(초록): 우연 예측기 대비, 경보 시간 비율 제약 하의 민감도 차 지표 확인 | 저자 소속 기업(이해상충 가능) | ⓒIOP(PMC 공개본) | 개념만 차용 |

### 2.8 소프트웨어(재현성·라이선스)

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S101 | PyOD (github.com/yzhao062/pyod) `BaseDetector.predict_proba(method='unify')`, `predict_confidence` | 코드 / C(근거), 라이선스는 1차 | opened(코드): erf((s−μ)/(σ√2))를 [0,1]로 자름, Perini식 (1+k)/(2+n)과 이항 cdf 확인 | 기본 'linear'는 min-max라 확률 아님 | BSD-2-Clause | requirements 포함 가능 |
| S102 | MAPIE (scikit-learn-contrib) | 코드 / C | opened(PyPI 메타·LICENSE) | 없음 | BSD-3-Clause | 포함 가능 |
| S103 | crepes (Boström) | 코드 / C | opened(PyPI 분류자·LICENSE 첫 줄) | 없음 | BSD | 포함 가능 |
| S104 | venn-abers (ip200) 1.5.4 | 코드 / C | opened(PyPI) | 없음 | MIT | 포함 가능 |
| S105 | betacal 1.1.0 | 코드 / C | opened(PyPI) | 없음 | MIT | 포함 가능 |
| S106 | netcal (EFS calibration-framework) 1.4.0 | 코드 / C | opened(PyPI, LICENSE) | 없음 | Apache-2.0 | 포함 가능(NOTICE 유지) |
| S107 | scikit-learn 문서 "Tuning the decision threshold" (`TunedThresholdClassifierCV`, `FixedThresholdClassifier`) | 공식 문서 / B | opened(본문): 학습 데이터로 임계를 튜닝하지 말라는 경고 확인. 도입 버전은 미확인 | 없음 | BSD-3 | 포함 가능 |
| S108 | statsmodels `proportion_confint` / SciPy | 코드 / C | opened(LICENSE) | 없음 | BSD-3 | 포함 가능 |

### 2.9 확인하지 못한 단서

| ID | 인용 | 유형/등급 | 검증 | 위험신호 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S109 | Moubray J. (1997) *Reliability-Centred Maintenance*, 2nd ed. (P–F interval 개념) | 실무서 / B | unverified | 미확인 | ⓒ | 확인 전 인용 금지 |
| S110 | Nowlan F.S., Heap H.F. (1978) *Reliability-Centered Maintenance*, DTIC AD-A066579 | 정부 보고서 / A | unverified(DTIC 접근 차단) | 미확인 | 공개로 알려짐 | 확인 후 인용 |
| S111 | SAE JA1011/JA1012 (RCM 기준·지침) | 표준 / A | unverified | 미확인 | ⓒSAE | 확인 후 인용 |
| S112 | ISO 13381-1:2015 Prognostics — General guidelines (KS B ISO 13381-1, 2026-08-28) | 표준 / A | KS 등재만 확인, 본문 unverified | 미확인 | ⓒISO | 번호만 인용 |
| S113 | ISO 13379-2:2015 Data-driven applications (KS B ISO 13379-2, 2023-12-29) | 표준 / A | KS 등재만 확인, 본문 unverified | 미확인 | ⓒISO | 번호만 인용 |
| S114 | The Joint Commission, Sentinel Event Alert #50 (의료기기 경보 피로) | 인증기관 / A | unverified(403) | 미확인 | ⓒTJC | 사용 보류 |

---

## 3. 세부 내용과 우리 계획에의 적용

### 3.0 [계산] 원시 데이터로 본 기준선 수치

#### 기본 구조 (버스트는 0.5초 넘는 간격으로 분리)

| 항목 | 정상(press_data_normal) | 이상(outlier_data) |
|---|---|---|
| 행 수 | 20,000 | 600 |
| 버스트 수 | 599 | 21 |
| 관측 시간 | 4,615.8초(1.282시간) | 165.6초 |
| 버스트/시간 | 467.2 (평균 약 7.7초마다 1개) | 456.5 |
| 버스트 크기 | 1–50행(중앙값 37, 50행짜리 202개) | 3–50행(중앙값 28) |
| 버스트 간 공백 | 1.55–16.64초(중앙값 4.22초) | 1.78–8.57초 |
| 중복 타임스탬프 | 1 (dt=0) | 0 |

#### 상태 변화

5분 단위 평균에서 **01:00–01:10에 저부하 구간**이 보인다.

| 지표 | 평소 | 01:00–01:10 |
|---|---|---|
| 상단 진동 RMS | 0.067–0.078 | 0.035–0.040 |
| 하단 진동 RMS | 0.10–0.13 | 0.044–0.045 |
| 전류 RMS | 109–133 | 84–86 |

또 00:40–01:00에는 상단 진동 RMS가 약간 높아지는 느린 드리프트가 있다(95분위 초과 30회 중 17회가 이 20분에 몰림).

#### 유효 표본 (배치평균 τ, n_eff=n/τ)

| 범위 | 지표 | τ | n_eff |
|---|---|---|---|
| 파일 전체 | 상단 진동 RMS | b=5에서 2.2 → b=60에서 15.8 (계속 증가) | 약 38–277 |
| 첫 60분(정상 상태) | 상단 진동 RMS | 0.9–1.5 | 약 310–520 / 473 |
| 첫 60분(정상 상태) | 하단 진동·전류 RMS | 0.5–1.2 | — |

**해석: 같은 운전 상태 안에서는 버스트가 거의 독립이다. "의존성"의 주원인은 운전 상태 변화(비정상성)다.** 따라서 오경보 불확실성의 실질적 단위는 "독립 운전 구간의 수"이고, 이 파일에서는 그 수가 극히 적다.

#### 행(row) 단위

- 행 기준 시간당 약 15,600행이므로, 행당 1% 임계면 시간당 약 156건의 초과가 생긴다.
- 버스트 내 lag-1 자기상관은 상단 진동 0.03, 하단 진동 0.32, **전류 0.93**이다.
- 1% 행 임계에서 초과가 1개라도 있는 버스트 비율은 9.7–19.7%다(행이 독립이라면 27.5%). 초과가 버스트 안에 몰린다.
- ⇒ 행 단위 오경보율은 의사결정 단위로도, 독립 표본으로도 의미가 없다.

#### 단순 기준선

전부 정상으로 예측하면 행 정확도가 97.09%(20,000/20,600)다. 공유된 가이드북 정확도 97.51%와 0.42%p 차이에 불과하다. 정확도는 이 과제의 지표로 부적절하다는 근거가 된다(가이드북 시험 분할 구성은 미확인).

#### 지속성 규칙 (표본 내 95분위 임계라 낙관적)

| 특징(임계) | 규칙 | 정상 경보 개시 수(1.28시간) | 시간당 | i.i.d. 예측(시간당) | 이상 에피소드 첫 탐지 버스트 |
|---|---|---|---|---|---|
| 상단 진동 RMS(0.1037) | 1-of-1 | 25 | 19.5 | 22.2 | 0번째 |
|  | 2-of-2 | 5 | 3.9 | 1.1 | 1번째 |
|  | 3-of-3 | 0 | 0 | 0.06 | 2번째 |
|  | 3-of-5 | 1 | 0.8 | – | 2번째 |
| 하단 진동 RMS(0.2011) | 2-of-2 | 1 | 0.8 | 1.1 | 1번째 |
|  | 3-of-5 | 2 | 1.6 | – | 2번째 |
| 전류 RMS(179.7) | 1-of-1 | 30 | 23.4 | 22.2 | 10번째(약함) |

i.i.d.에서 n-of-n 규칙의 경보 **개시율**은 버스트당 약 (1−p)·pⁿ이다. 지연 타이머의 FAR·MAR·AAD는 마르코프 연쇄로 분석된다 [S17–S19]. 상단 진동의 2-of-2가 이론보다 3.5배 많은 것은 위의 드리프트 때문이다.

#### 상태 변화 실험

| 점수 | α | 01:00–01:17 정상(126 버스트) 오경보율 | 보정집합 자체 FAR | 이상 버스트 탐지율 |
|---|---|---|---|---|
| Mahalanobis(양측, log RMS 3채널) | 0.05 | **19.8%** | 4.2% | 95% |
|  | 0.01 | 0.8% | 0.4% | 62% |
| 채널별 최대 z(단측, 증가만) | 0.05 | 0.8% | 4.2% | 90% |
|  | 0.01 | 0.0% | 0.4% | 86% |

- 조건: 0–30분 학습, 30–60분 보정(n=236)이며 분할은 시간순이다.
- 저부하처럼 "덜 진동하는" 정상 변화가 양측 검출기에서 FP를 만든다는 직접 증거다.

#### CUSUM (단측, k=0.5, Siegmund 근사, NIST 표로 검증: h=4에서 338 대 336, h=5에서 938 대 930)

| 예산 | 목표 ARL0(버스트) | h | 1σ 탐지 지연 | 2σ | 3σ |
|---|---|---|---|---|---|
| 1건/시간 | 467 | 4.31 | 9.0 버스트(약 69초) | 3.4 | 2.1 |
| 1건/교대(8시간) | 3,737 | 6.37 | 13.1(약 1.7분) | 4.8 | 2.9 |
| 1건/일 | 11,212 | 7.47 | 15.3 | 5.5 | 3.4 |
| 1건/주 | 78,486 | 9.41 | 19.2(약 2.5분) | 6.8 | 4.2 |

- 몬테카를로로 h=6.37일 때 ARL0 3,767±59를 확인했다.
- 같은 h에서 AR(1) ρ=0.2이면 ARL0 760, ρ=0.3이면 421이다. i.i.d.를 가정해 설계한 CUSUM은 상관이 조금만 있어도 오경보가 5–9배로 늘어난다.

#### Shewhart 3σ와 Western Electric 4규칙

ARL0가 370.5에서 92.3으로 줄어든다(몬테카를로 10만 회). "규칙을 더 붙일수록 오경보가 늘어난다."

#### 소표본 구간

| 항목 | 값 |
|---|---|
| 에피소드 탐지 1/1, CP 95% | [0.025, 1.000] |
| Wilson 95% | [0.207, 1.000] |
| 21/21 버스트(의존 무시, 사용 금지 예시) | CP [0.839, 1.000] |
| 0/599 버스트 오경보 | CP 상한 0.0061, 3/n 규칙 0.0050 |
| 정상 1.282시간 오경보 0건 | 단측 95% 상한 2.34건/시간, 양측 97.5% 상한 2.88건/시간 |
| 정상 1.282시간 오경보 5건 | 1.27–9.10건/시간 |
| 교대당 ≤1 입증 | 오경보 0건 정상 운전 24.0시간 필요 |
| 일당 ≤1 입증 | 71.9시간 필요 |
| 주당 ≤1 입증 | 503시간 필요 |
| 사건 단위 민감도 하한 0.8 입증 (모두 탐지 가정) | 독립 고장 사건 14개(단측) / 17개(양측 CP) |
| 사건 단위 민감도 하한 0.9 입증 | 29개 / 36개 |

#### 정밀도(PPV) 감각

- π_burst≈6.2×10⁻⁵로 가정한다(한 달에 3분짜리 에피소드 1회 ≈ 21/336k 버스트).
- 버스트 민감도 0.9, 버스트 FAR 0.001이면 **PPV≈5.3%**다.
- 즉 경보 100개 중 95개가 허위다. 버스트 FAR 0.001도 운영상 너무 높다.

### 3.1 경보관리 표준과 적용

**(1) 정의와 범위**

- ISA-18.2-2016의 경보 정의(3.1.3)는 "적시 대응 요구"가 핵심이다 [S04]. ISA TR5의 정의 주석(3.1.2 active)은 "deadband, on/off delay, latching 때문에 경보 조건이 거짓인데도 활성일 수 있고 그 반대일 수도 있다"고 명시한다. 즉 **데드밴드·지연은 경보 정의의 일부로 문서화해야 하는 속성**이다.
- IEC 62682:2022는 2014판을 대체한 기술 개정판이다. packaged systems가 범위에 들어갔고 정의가 갱신됐다 [S02]. 3.1.4 *adaptive alarm*은 "설정점이 알고리즘으로 바뀌는 경보(예: 생산율에 따라 계산된 설정점)"로 정의된다. 우리가 제안할 상태 의존 임계의 공식 용어로 쓸 수 있다.
- EEMUA 191 4판(2024-11)은 alarm·alert·prompt·event를 구분한다(§2.3.1, §2.6, 그림 7·9) [S05]. Brazier(2025)의 요약에 따르면 alert는 "운전원이 응답할 필요가 없는" 상황인식용 정보다. 설비 상태 정보는 "정비팀 일일 보고에 나타나는 alert"로 처리할 수 있고, alert에는 보통 가청 신호를 쓰지 않는다 [S06].
- ISA는 비경보 통지 지침 TR18.2.8 *Guidelines for Non-alarm Notifications*를 따로 두고 있다(TR18.2.3-2024 서문에서 확인, 발간 상태 미확인) [S03].
- **적용**: 보고서의 "현장 적용" 장에서 3단계 신호를 다음처럼 분류한다.
  - 주의 = alert(정비 대시보드·일일 보고, 비가청)
  - 경고 = 저·중 우선순위 경보(정비 책임자와 운전원)
  - 위험 = 최고 우선순위 경보(운전원, 즉시 대응)

  이렇게 하면 ISA/IEC 성능지표가 정의하는 "운전원 부하"에 들어가는 것은 경고·위험뿐이다.

**(2) 성능지표(KPI)와 펌프 경보 "예산"**

조항 위치는 ISA-18.2-2016 §16.4·§16.8, 표 5 "Average alarm rates", 표 6 "Example annunciated alarm priority distribution", 표 7 "Recommended alarm performance metrics summary"다 [S01]. IEC 62682:2022에서는 §16.3.3–16.3.10과 표 5–7이다 [S02].

수치(IChemE 2021이 IEC/ISA/EEMUA를 재정리한 것) [S08]:

| 지표 | 값 |
|---|---|
| 운전원 콘솔당 경보 | 10분당 약 1건 "목표", 약 2건 "차선", 2건 초과 "불량" |
| 10분 최대 경보 | 목표 ≤10(IEC/ISA), 차선 ≤20(EEMUA 근거) |
| 플러드 상태 시간 비율 | <1% |
| 플러드 정의 | 10분에 10건 초과, 10분에 5건 미만으로 떨어지면 해제 |
| 상위 10개 경보의 부하 기여 | <1%(목표)–≤5% |
| chattering·fleeting | 사실상 0 |
| stale | <5(IEC/ISA), <10(EEMUA) |
| 우선순위 분포(3단계) | 약 80% 낮음 / 15% 중간 / 5% 높음 |

- ISA 표 5의 "시간당 약 6건(매우 수용 가능)/약 12건(최대 관리 가능)"은 검색 스니펫과 IChemE 표의 10분 기준이 일치하는 수준으로만 확인했다.
- 기원: HSE CRR 166 §4.4가 "평균 10분당 1건이면 대부분의 경보를 초기 조사할 시간이 있다"고 했다. 일주일 평균 경보율, 운전 모드별 구분, 10분 피크율도 측정하라고 권했다 [S07].
- EEMUA 3판 p.96–97은 정상 상태에서 10분당 1건 미만 "매우 수용 가능", 5분당 1건 "관리 가능", 2분당 1건 "과부하 가능성", 분당 1건 초과 "수용 불가"로 등급화했다(벤더 문서 S09의 2차 인용).
- **반론(같은 S09)**: 10분당 1건을 시간당 6건·하루 144건으로 단순 환산하는 것은 무의미하다. ISA 2016판은 일별 KPI와 "시간당 30건 초과 시간 비율" 등 4개 지표를 삭제했다. 사이트 철학에 맞는 값을 정하라는 취지다.
- **적용**:
  - 펌프 1대의 예측정비 신호가 운전원 부하의 작은 부분만 쓰도록 예산을 정한다. 예: 경고 ≤1회/주, 위험은 사실상 0, 주의 ≤1회/일. 이는 제안값이며 표준에서 온 값이 아니다.
  - 이 예산에서 임계를 역산한다(§3.2의 CUSUM 표).
  - 평가는 "F1 최대화"가 아니라 "예산을 지킬 때의 탐지 지연"으로 보고한다.

**(3) chattering·fleeting·stale**

- ISA-18.2는 chattering을 "짧은 시간에 경보 상태와 정상 상태를 반복 전이하는 경보"로 정의한다 [S16이 ISA 인용]. IChemE는 fleeting을 "반복 없이 짧게 활성/비활성을 오가는 경보", stale을 "장시간(예: 24시간) 계속 표시되는 경보"로 설명한다 [S08].
- Wang & Chen의 규칙은 지속시간이 매우 짧은 경우(예: 20초 미만)를 chattering으로 본다 [S16].
- Kondaveeti 등은 run-length 분포 기반 chatter index를 제안했다 [S20]. Naghoosi 등은 chattering 추정과 데드밴드·한계 최적화를 다뤘다 [S21].
- **적용**: 우리 검출기 출력(경보 개시/해제 시계열)에 대해 정상 데이터에서 다음을 보고한다. 우리 경보는 버스트 간격(약 7.7초)으로만 바뀔 수 있으므로 "1분 안에 개시와 해제" 패턴이 곧 chattering이다.
  - 경보 지속시간 분포
  - 1분 내 재개시 횟수
  - chatter index

**(4) 데드밴드·지연(on/off-delay)**

- ISA-18.2-2016 본문의 그림은 1–5뿐이다(목차 확인). TR18.2.3-2015는 "Recommended starting point deadband based on signal type (ISA-18.2, Figure 9)"(그림 9)와 "Recommended delay times based on signal type (ISA-18.2, Figure 10)"(그림 14)을 싣고 있다. 따라서 이 출발값은 **2009판 그림 9·10에서 왔고 지금은 TR18.2.3에 있다** [S01, S03].
- 수치(2차 인용, 2009판 기준): 유량 5%/15초, 레벨 5%/60초, 압력 2%/15초, 온도 1%/60초 [S10]. 이는 공정변수용이며 **진동·전류에 대한 표준 출발값은 찾지 못했다**. EEMUA 4판에는 표 9 "filter time constants", 표 10 "default deadband settings", 표 11 "default de-bounce timer parameters"가 있다(값은 미확인) [S05].
- **적용(유비)**:
  - **on-delay = n 버스트**: 3 버스트면 약 23초로, ISA 압력·유량 출발값 15초와 같은 규모다.
  - **off-delay = m 버스트**
  - **데드밴드 = 점수 히스테리시스**: 예를 들어 p ≤ 0.005에서 켜고 p > 0.05에서 끈다. 또는 CUSUM 재설정 규칙.

  보고서에는 "공정변수용 출발값을 버스트 단위로 옮긴 유비이며 표준값이 아님"이라고 쓴다.

**(5) 우선순위·다단계 경보와 상태 신호**

- HSE CRR 166 §4.10은 "3개 우선순위(예: urgent, warning, caution)가 수용된 모범 관행", "최고 우선순위는 소수이고 즉각적이며 잘 정의된 조치와 연결"이라고 쓴다. 각주 14는 "최고 우선순위 경보가 허위로 여겨질 가능성은 없어야 한다"이다 [S07].
- 3단계 분포는 약 80/15/5다 [S08]. EEMUA 4판은 우선순위 행렬(부록 3, 표 27 Time to Consequence 구간)과 "단일 경보면 우선순위와 무관하게 즉시 대응" 원칙을 둔다 [S05, S06].
- NAMUR NE 107은 기기 자기진단을 4개 상태신호 F(Failure), C(Function check), S(Out of specification), M(Maintenance required/request)로 압축한다. 사용자가 진단을 범주와 우선순위에 할당할 수 있게 한다 [S11, S12]. 신호별 정확한 정의 문구는 원문 미확인이다.
- 진동 표준:
  - ISO 20816-1:2016 §6.4는 운영 한계를 ALARM(§6.4.2)과 TRIP(§6.4.3) 두 단계로 둔다. 평가 기준은 크기(Criterion I, §6.3.2)와 **변화량**(Criterion II, §6.3.3) 두 가지다 [S14].
  - ISO 17359:2018 §8.9는 초기 alert/alarm 기준이 고장의 가장 이른 징후를 주도록 설정하라고 하며, 다단계와 증가·감소 양방향을 허용한다(search-only). §8.10은 기준선 데이터를 다룬다 [S13].
- **적용(제안 설계, 수치는 실험으로 확정)**:

| 단계 | 분류 | NE 107 유비 | 근거 | 규칙 예(가설) | 수신·전달 | 기대 대응 | 예산(제안) |
|---|---|---|---|---|---|---|---|
| 주의 | alert(비가청) | M | ISO 17359 §8.9–8.10(자기 기준선) | 버스트 콘포멀 p≤0.01이 5개 중 3개 이상, 또는 CUSUM h₁(1건/일) 초과 | 정비 대시보드·일일 보고 | 다음 계획 정비에서 확인 | ≤1회/일 |
| 경고 | 경보(낮음·중간) | S | ISO 20816-1 §6.4.2(기준선 대비 증가), Criterion II | 두 진동 채널 모두 증가 + CUSUM h₂(1건/주) 초과 + 10분 이상 지속 | 정비 책임자 + 운전원 | 교대 내 현장 점검(소음·유온·누유·토출압 맥동 확인), 정비 계획 | ≤1회/주 |
| 위험 | 경보(최고) | F | ISO 20816-1 §6.4.3 TRIP 성격, HSE 각주 14 | 모든 보정 버스트 초과(p=1/(n+1))이면서 크기 기준(기록된 이상 에피소드 수준)과 2채널·2버스트 일치 | 운전원(가청) | 정지 검토와 정비 호출 | 사실상 0(허위가 한 번도 없어야 함) |
| 점검중 | 설계 억제/보류 | C | ISA §11.7–11.9, §12.4 | 금형교체·시운전·정비·저부하 상태 감지 | 이력 기록만 | – | 억제 이력 감사 |

- 위험 단계에는 지속성 규칙을 두지 않는 "빠른 경로"를 남긴다. Shewhart가 큰 이동에서 CUSUM보다 빠르다는 점과 같은 이유다 [S26].
- 상태 기반 억제는 ISA §11.9(Alarms suppressed by design)와 §12.4(Logic-based alarming), TR18.2.4(state-based alarming) 범주에 해당한다 [S01, S03]. 운전 상태 자체는 전류 RMS로 추정할 수 있다(01:00–01:10 저부하 구간은 전류 RMS 약 85).
- ISO 17359 §8.4도 "변화가 고장 때문인지 운전 조건 변화 때문인지 판단할 수 있어야 한다"고 명시한다 [S13].

**(6) 생애주기 운영**

- ISA 생애주기에는 rationalization(§9), 보류 shelving(§11.7, §14.3), 무단 억제 감시(§16.5), 변경관리(§17)가 있다 [S01].
- **적용**: 각 단계마다 "경보 대응 카드"를 둔다. 카드에는 원인 후보, 결과, 대응 조치, 대응 가능 시간, 확인 방법을 적는다.
- 운전원·정비원의 판정(실제 이상/허위)을 기록해 다음 보정의 라벨로 쓰는 피드백 루프를 현장 적용안에 넣는다. 단, 갱신은 확인된 정상 구간으로만 한다(§3.3의 ACI 위험 참조).

### 3.2 통계적 경보 설계: SPC·SPRT·지연 타이머

- **Shewhart·CUSUM·EWMA** [S25–S29]
  - 3σ Shewhart의 ARL0는 약 370이다.
  - 단측 CUSUM(k=0.5)의 ARL0는 h=4에서 336, h=5에서 930이다(NIST 표, 단측) [S26]. 교재에 흔히 실린다고 알려진 168·465는 양측 값으로 단측의 약 절반이다. 다만 이 두 값은 교재 원문으로 확인하지 못했다.
  - EWMA는 λ 0.2–0.3이 통상값이며 Lucas & Saccucci 표로 선택한다 [S26, S29].
  - CUSUM은 Page가 제안했고 [S27], Lorden 기준으로 최적성이 증명됐다 [S34, S35].
  - **적용**: §3.0 표처럼 경보 예산(ARL0)에서 h를 역산하고 이동 크기별 탐지 지연을 함께 보고한다. 교대 예산에서도 1σ 이동이 1.7분 안에 잡히므로, 마모성 고장이라면 지속성·누적 비용은 P–F 구간(시간–일 단위로 추정되나 미확인)에 비해 무시할 만하다.
- **자기상관 경고** [S31, S32]
  - 시계열 상관이 있으면 관리도의 오경보가 늘어난다. 잔차 관리도(ARIMA 잔차에 관리도 적용)가 표준 대처다.
  - 우리 몬테카를로에서 ρ=0.2이면 ARL0가 1/5이 됐다.
  - **적용**: h는 이론식으로 정하지 말고 정상 데이터의 블록 부트스트랩이나 시간순 보정으로 다시 맞춘다. 또는 콘포멀 p값의 −log p에 CUSUM을 적용하는 비모수 대안을 쓴다 [S49].
- **보조 규칙의 함정**: Western Electric 4규칙은 ARL0를 약 92로 낮춘다 [S30, 재현]. 여러 규칙을 OR로 묶을수록 오경보 예산이 빨리 소진된다. 규칙마다 기여 오경보를 분리해 보고해야 한다.
- **SPRT** [S33, S37]
  - Wald 근사 경계는 A≈(1−β)/α, B≈β/(1−α)다.
  - 원전 온라인 모니터링(OLM)에서는 잔차의 평균 이동이나 분산 변화를 SPRT로 판정하는 것이 실무 표준 도구 중 하나다 [S37].
  - CUSUM은 "재시작하는 SPRT"로 볼 수 있다.
  - **적용**: 정상과 이상(예: 분산 k배) 두 가설로 버스트 RMS 잔차에 SPRT를 적용한다. 설정한 α(오경보)·β(놓침)가 해석 가능한 파라미터가 되므로, 경보 철학 문서에 "왜 이 임계인가"를 설명하기 좋다.
- **지연 타이머와 k-of-n** [S17–S19, S22]
  - FAR(오경보율)·MAR(놓침율)·AAD(평균 경보 지연)를 함께 보는 설계가 이 분야 표준 틀이다.
  - 일반화 지연 타이머(m-of-n)는 n-of-n보다 지연을 줄이면서 오경보를 억제한다.
  - Wang 등은 이런 관계가 **i.i.d. 밖에서는 확립하기 어렵다**고 명시한다 [S16].
  - **적용**: §3.0 표처럼 이론값과 경험값을 나란히 보고하고, 차이(드리프트 구간 군집)를 FP 조건 분석의 한 항목으로 쓴다.

### 3.3 콘포멀 이상탐지와 FDR: 남는 보장과 정직한 진술

- **기본** [S38, S43–S46]
  - 정상 보정 점수 n개에 대해 콘포멀 p값은 p(x)=(1+#{보정점수 ≥ s(x)})/(n+1)이다.
  - 새 정상 표본이 보정 표본과 교환가능하면 P(p ≤ α) ≤ α(주변 보장)다. 이상탐지에서는 이것이 "경보율 보정"의 근거다 [S44].
  - 보정집합을 고정하면 실제 오경보율은 Beta(l, n+1−l), l=⌊(n+1)α⌋을 따른다 [S46]. 이 변동을 줄이려면 보정점이 약 1,000개 필요하다는 것이 저자 권고다.
  - 우리 정상 데이터는 599 버스트이고, 학습과 보정으로 나누면 보정은 약 240–300개다. 그러면 α=0.01에서 실제 FAR 95% 상한이 약 2%다 [계산].
  - Bates 등은 보정조건부(학습 데이터 조건부) 유효 p값을 만드는 보정법을 제시한다 [S38, S45].
- **다중 버스트와 FDR** [S38, S47]
  - 콘포멀 p값은 PRDS이므로 BH가 FDR을 통제한다.
  - 하지만 고장이 없는 시간대(전역 귀무)에서는 FDR이 "하나라도 경보가 날 확률"과 같아진다. 또 BH가 무엇이든 기각하려면 최소 p값 1/(n+1) ≤ q/m이어야 한다. 그러려면 보정 표본이 다음만큼 필요하다 [계산]:

| BH 창(검정 버스트 수) | q | 필요 보정 표본 |
|---|---|---|
| 10 | 0.1 | ≥99 |
| 60 | 0.1 | ≥599 |
| 467 (1시간) | 0.1 | ≥4,669 |
| 3,737 (1교대) | 0.1 | ≥37,369 |

  ⇒ **긴 창의 BH는 이 데이터로는 검정력이 0**이다. 짧은 창(약 10 버스트)에서 창 단위 통제로만 실용적이다.
- **라벨된 이상 21 버스트의 올바른 용도**
  - Integrative conformal p-values는 라벨된 이상을 써서 검정력을 높이면서도 유효성을 유지한다 [S48].
  - **권장**: 이상 버스트는 **검정력(탐지율)과 크기 기준 설정에만** 쓰고, **오경보 보정에는 절대 쓰지 않는다**. 보고서에서 이 원칙을 명시하면 누설 의혹을 피할 수 있다.
- **시간 의존성 하에서 남는 것**
  - 분할 콘포멀은 많은 비교환 과정(β-mixing 등)에서 "작은 커버리지 페널티"를 더하면 유효하다 [S42].
  - 블록 순열 콘포멀은 약한 의존에서 근사 유효하다 [S41].
  - 가중 콘포멀(최근 표본 가중)의 손실은 가중 총변동 거리로 한정된다 [S39].
  - 그러나 **운전 상태가 바뀌는 비정상성**(우리 데이터의 01:00–01:10)은 "약한 의존"이 아니다. 보정 기간에 그 상태가 없으면 보장이 성립하지 않는다(§3.0 실험: 양측 점수 FAR 19.8%).
- **ACI의 함정** [S40]
  - ACI는 α_{t+1}=α_t+γ(α−err_t)로 갱신하고, 어떤 데이터 과정에서도 장기 평균 err이 α에 수렴함을 보장한다(Prop. 4.1).
  - 이상탐지에 적용하면 고장이 지속될 때 경보(err=1)가 이어져 α_t가 내려가고 임계가 올라간다. 즉 **고장을 "적응"해 지워버린다**(우리 해석).
  - ⇒ 온라인 갱신은 운전원이 정상으로 확인한 구간에서만 하고, 경고 이상이 발생하면 갱신을 동결한다.
- **언제나 유효한(anytime-valid) 대안** [S49–S52]
  - 콘포멀 마팅게일(i.i.d. 가정만 필요)로 변화점을 탐지할 수 있다 [S49, S50].
  - e-detector를 임계 b로 끊으면 ARL ≥ b이고, 임의 감시 기간 t에 대해 P(t 이전 오경보) ≤ t/b다(프리프린트) [S51, S52].
  - 예: 교대당 오경보 확률 ≤5%를 원하면 b = 3,737/0.05 ≈ 74,700이다.
  - 사전 변화 분포의 i.i.d./교환가능 가정이 깨지면(상태 변화) 보장도 깨진다.
- **1/n 아래로 외삽**
  - 정상 점수 꼬리에 GPD(peaks-over-threshold)를 맞춰 1/n보다 작은 α의 임계를 외삽할 수 있다(SPOT 등) [S54, S55].
  - 모형 위험이 크므로 **민감도 분석으로만** 제시하고 "보장"이라는 말은 쓰지 않는다.
- **정직한 보장 진술 단위표(권장)**

| 단위 | 보장·추정할 수 있는 것 | 필요한 가정 | 이 데이터의 한계 | 권장 표현 |
|---|---|---|---|---|
| 행 | 사실상 없음 | 행 독립(불성립: 전류 lag-1 0.93) | 의사결정 단위 아님 | 본문에서 보고하지 않음(진단 부록만) |
| 버스트 | P(경보∣정상 버스트) ≤ α(보정집합에 대한 평균). 고정 보정 시 Beta 분포 | 보정 버스트와 운영 버스트의 교환가능성 | α ≥ 1/(n+1). 같은 날·같은 조건 | "07-12 00:00–01:00 조건에서 보정, 명목 α=0.01, 고정 보정집합 기준 실제 FAR 95% 상한 약 2%" |
| 경보 사건(지속성 규칙 적용 후) | 관측 개시 건수/노출 시간, Poisson 정확 CI | 사건 간 근사 독립 | 0건이면 상한 3/T. 독립 운전 구간 수가 적음 | "정상 1.28시간 0건 → 95% 상한 2.3건/시간(동일 조건 한정)" |
| 시간·교대 | 기대 오경보 수/시간, P(교대 중 ≥1건) | 정상성, 독립, 상태 분포 동일 | 다른 요일·부하 미관측 | "교대당 ≤1건은 i.i.d. 가정 설계값이며 실증 아님. 실증에는 ≥24시간 섀도 운전 필요" |
| anytime(e-detector·콘포멀 마팅게일) | P(t 이전 오경보) ≤ t/b | 사전 변화 i.i.d./교환가능 | 상태 변화 시 깨짐 | 이론 보장과 실증값을 병기 |

### 3.4 점수→확률 보정(양성이 1개 에피소드뿐일 때)

- **비지도 변환**
  - Kriegel 등의 통합 방식은 정상 점수 분포의 평균·표준편차만으로 erf((s−μ)/(σ√2))를 [0,1]로 잘라 "이상 확률"을 만든다. PyOD `predict_proba(method='unify')`가 이 방식을 구현한다 [S56, S101].
  - Gao & Tan은 시그모이드·혼합모형 변환을 제안했다 [S57].
  - 이 값은 **고장 확률이 아니라** "정상 점수가 가우시안이라면 이만큼 이례적"이라는 척도다. 보고서에서 이 이름을 혼동하지 말아야 한다.
- **지도 보정(라벨 필요)**
  - **Platt** [S58]: 검증 데이터가 완전 분리되면 MLE 기울기가 −∞로 발산한다. 그래서 목표값을 t₊=(N₊+1)/(N₊+2), t₋=1/(N₋+2)로 둔다(균등 사전의 MAP).
    - 버스트 기준(N₊=21, N₋=599)이면 t₊=0.957, t₋=0.0017이다.
    - **에피소드 기준(N₊=1)이면 t₊=0.667**이다. 보정 확률 상단이 0.67로 묶여야 정직하다는 해석도 가능하다.
    - Firth 벌점 로지스틱도 분리 문제의 표준 처방이다 [S74].
  - **Isotonic** [S59, S60]: 단조 비모수라 소표본에서 계단·과적합이 심하다.
  - **Beta 보정** [S61, S62]: 치우친 점수에서 로지스틱 보정의 결함(항등함수 미포함)을 고친다. 파라미터가 3개뿐이다.
  - **Temperature scaling** [S64]: 다중분류 신경망용이며 여기서는 Platt와 비슷하다.
  - **Venn–Abers** [S63]: (p₀, p₁)을 출력하며 i.i.d. 하에서 보정 보장이 있다. 폭 |p₁−p₀|이 과적합·소표본 정도를 알려준다. 단일 값이 필요하면 p=p₁/(1−p₀+p₁)을 쓴다. **운전원 화면에 "P(이상) 0.6–0.9"처럼 구간으로 보여주는 아이디어**에 좋다.
- **사전확률(기저율) 교정** [S72, S73]
  - 학습셋 유병률(버스트 3.4%, 행 2.9%)은 실제 고장 빈도가 아니다.
  - 사후 오즈 = 우도비 × 사전 오즈이므로, 학습 유병률 π_tr로 보정된 p를 실제 π로 옮긴다:

    p′ = (π/π_tr)·p / [(π/π_tr)·p + ((1−π)/(1−π_tr))·(1−p)]

  - [계산] 학습 p와 사전 π에 따른 p′:

| 학습 p | π=10⁻² | π=10⁻³ | π=10⁻⁴ |
|---|---|---|---|
| 0.9 | 0.72 | 0.20 | 0.025 |
| 0.99 | 0.97 | 0.74 | 0.22 |
| 0.999 | 0.997 | 0.97 | 0.74 |

  - **권장 산출 스키마**:
    - ① `p_normal_tail`: 콘포멀 p값
    - ② `score_unified`: Kriegel 방식, 참고용
    - ③ `P_fault_given_prior(π)`: π∈{10⁻³, 10⁻⁴}처럼 명시한 시나리오별 값
    - ④ `VA_interval`: [p₀, p₁]

    "제조 이상 확률을 예측하라"는 채점 항목에는 ③을 주 확률로 내되, ①과 ④로 불확실성을 함께 보여준다.
- **평가 지표**
  - Brier와 로그손실은 엄격 적정 점수규칙이다 [S68–S70]. Murphy 분해로 신뢰도·해상도를 볼 수 있다.
  - 신뢰도 도표는 DeGroot & Fienberg를 참조한다 [S71].
  - **ECE는 bin 선택에 민감하고 편향된다** [S65–S67]. 양성 21개(사실상 1개 사건)에서는 상단 bin이 비어 의미가 없다.
  - 의료 예측모형 문헌의 보정 위계(평균 보정 → 약한 보정 → 중간 보정)와, 외부 검증에 사건 약 100개 이상이 필요하다는 권고 [S75–S77, 원문 재확인 필요]를 인용하면 "이 데이터로는 보정 자체를 검증할 수 없다"는 진술을 뒷받침할 수 있다.
  - **적용**:
    - (a) 정상 데이터에서 calibration-in-the-large(평균 예측 대 0)를 본다.
    - (b) 합성 심각도 스케일링 데이터(§3.7 E10)에서 Brier와 로그손실을 블록 부트스트랩 CI와 함께 보고한다.
    - (c) 신뢰도 도표는 "예시"로만 싣는다.
- **이상탐지 신뢰도**: ExCeeD는 학습셋이 조금 바뀌어도 같은 예측을 할지에 대한 확신도를 준다(PyOD `predict_confidence`) [S78, S101]. 오염률 가정에 의존한다는 점을 함께 명시한다.

### 3.5 소표본 비율의 불확실성

- **구간 선택** [S81–S84]
  - Clopper–Pearson은 보수적인 정확 구간이다.
  - Wilson과 Agresti–Coull은 소표본 커버리지가 좋은 근사 구간이다.
  - Brown–Cai–DasGupta는 Wald 구간을 쓰지 말라고 권한다.
  - 0건일 때는 3/n 규칙을 쓴다 [S85, S86]. Poisson(시간당 사건)에는 Garwood 정확 구간을 쓴다 [S87].
  - 구현은 `statsmodels.stats.proportion.proportion_confint(method='beta'·'wilson')`와 SciPy χ²로 한다 [S108].
- **의존과 유효 표본** [S88–S92]
  - 계열상관이 있으면 유효 표본이 줄어든다 [S88].
  - 블록·정상 부트스트랩을 쓴다 [S89, S90]. 블록 길이는 자동 선택할 수 있다 [S91].
  - 군집(에피소드·운전 구간) 단위로 다시 뽑는 부트스트랩도 있다 [S92].
  - **적용**:
    - 오경보 CI는 5–10분 블록 단위(정상 파일 기준 블록 약 8–15개) 부트스트랩으로 낸다. CI가 넓게 나오는 것이 정직한 결과다.
    - 탐지 성능은 에피소드 단위 1/1(CI 0.025–1)로 보고한다.
    - 버스트 단위 21/21은 "같은 에피소드 안의 반복 측정"이라고 명시한다.
    - 같은 운전 상태 안에서는 버스트가 거의 독립(τ≈1)이고, 상태 변화가 주된 의존원이라는 §3.0 결과를 함께 적는다.

### 3.6 의사결정 이론과 현장 적용

- **비용 민감 임계** [S73]
  - 최적 결정은 E[비용∣경보] ≤ E[비용∣무경보]이다. 맞는 판정의 비용을 0으로 두면 p* = c_FP/(c_FP + c_FN)이다.
  - Elkan은 2×2 비용행렬의 결정상 자유도가 하나뿐이고, 기저율이 바뀌면 확률을 다시 계산해야 한다고 보였다.
  - 가이드북이 말하는 "고장 시 최대 2–3일 라인 정지"(공유 컨텍스트, 원문 미확인)를 쓰면 c_FN/c_FP가 수십–수백이다.
  - [계산] 비용비 100이면 p*≈0.0099다. π=10⁻⁴이면 우도비가 100 이상이어야 경보를 낸다.
  - **비용 숫자는 가정**이므로 비용비 10/50/100/300 × π 10⁻³/10⁻⁴ 격자 표로 결정이 얼마나 민감한지 보인다.
- **예산 제약(Neyman–Pearson)** [S79, S80]
  - 오경보 예산을 제약으로 두고 탐지를 최대화한다.
  - 우산 알고리즘은 정상 표본의 순서통계량으로 임계를 정한다. P(실제 오경보율 > α) ≤ δ를 보장하려면 n ≥ log δ / log(1−α)여야 한다. α=0.01·δ=0.05이면 299, α=0.005이면 598(정상 버스트 전체 599개와 거의 같음), α=0.001이면 2,995다 [계산].
  - **권장 결합 규칙**: "예산을 지키는 임계 중 기대 비용이 최소인 것". 경보 피로처럼 비용행렬에 담기지 않는 비용을 예산으로 반영할 수 있다.
  - 근거: 응답률이 경보 신뢰도에 맞춰지고 [S93], 오경보가 놓침보다 해롭다 [S94]. 반례도 있다 [S95].
- **점검 우선순위**: 펌프가 1대이므로 "어느 경보부터 볼 것인가"는 경보 사건들의 증거 강도 순위다. 증거 강도는 p값, e-값, CUSUM 초과량으로 잴 수 있다. 정비 대시보드는 상위 k개 주의(alert)만 보여주고 나머지는 이력으로 둔다.
- **P–F 구간과 경보 단계**
  - ISO 17359 §8.5는 고장 탐지부터 실제 고장까지의 경과 시간을 **LTTF(lead time to failure)**로 정의하고, 이것이 감시 간격과 감시 체계 유형을 좌우한다고 쓴다 [S13]. RCM의 P–F 구간과 같은 개념이다(Moubray·Nowlan & Heap 원문은 미확인 [S109, S110]).
  - **매핑**: P(검출 가능 시점) → [주의] → [경고] → [위험] → F(기능 고장).
    - 주의는 P 가까이에서 낸다. 리드타임이 길고 특이도가 낮다.
    - 경고는 열화가 확인된 상태로, F 전에 정비를 계획하게 한다.
    - 위험은 F가 임박했거나 진행 중인 상태다.
  - 감시 간격(버스트 약 7.7초)은 마모성 고장의 P–F에 비해 매우 짧다. 그래서 몇 분짜리 누적·지속성이 리드타임을 거의 깎지 않는다. **오경보가 진짜 제약**이다.
  - 갑작스러운 고장(짧은 P–F)에는 위험 단계의 빠른 경로만 의미가 있다.
  - 공유된 이상 에피소드는 진동 표준편차가 약 6배(0.07→0.45)인 **말기(F 근처) 상태일 가능성**이 있다. "조기" 탐지 주장은 합성 초기 고장 실험(E10)으로만 뒷받침할 수 있다.
- **평가 곡선** [S96–S100]
  - point-adjust F1을 쓰지 않는다 [S96].
  - 가로축을 FA/시간(또는 경보 시간 비율), 세로축을 이벤트 탐지 여부와 지연으로 하는 곡선을 그린다. 발작예측특성과 같은 방식이다 [S99].
  - 같은 경보 시간 비율을 쓰는 우연 예측기와 비교한다 [S100]. 예: 경보 시간 비율 5%인 무작위 경보도 3분짜리 에피소드를 우연히 맞힐 확률이 약 5% 이상이다. "탐지했다"는 주장은 낮은 경보 시간 비율에서만 의미가 있다.

### 3.7 계획에 넣을 실험 목록(제안)

- **E1 평가 단위 고정**
  - 버스트를 판정 단위로 하고, 경보 개시를 사건 단위로 한다.
  - 노출 시간을 기준으로 FA/시간과 Poisson CI를 낸다.
  - 이벤트 탐지 지연(초·버스트)을 측정하고 우연 예측기를 기준선으로 둔다.
  - 가이드북식 행 지표(정확도·F1)는 비교용으로만 병기한다.
- **E2 시간순 보정**
  - 0–30분 학습, 30–60분 보정, 60–77분 시험으로 나눈다.
  - 역순 분할과 5–10분 블록 leave-one-block-out도 한다.
  - 01:00–01:10 저부하 구간은 별도로 보고한다(FP 조건 분석의 핵심 사례).
- **E3 단측 대 양측 점수**: §3.0 실험을 실제 모델 점수로 반복한다. 상태 기반 억제(전류 RMS 기반 상태 분류) 전후의 FA를 비교한다.
- **E4 지속성·누적 격자**
  - n-of-n, k-of-n, CUSUM h(예산에서 역산), EWMA λ를 격자로 돌린다.
  - FA/시간 대 탐지 지연 곡선을 그린다.
  - i.i.d. 이론값과 경험값의 비율(상관 팽창 계수)을 보고한다.
- **E5 콘포멀 변형**
  - 분할, CV+/jackknife+(MAPIE·crepes)를 비교한다.
  - 보정조건부 보정과 Beta 분포로 실제 FAR 상한을 표기한다.
  - 채널 결합은 Bonferroni나 Simes로 한다.
- **E6 라벨된 이상의 사용 경계**: integrative conformal로 검정력만 개선하는지 확인한다. 오경보 보정에서 이상을 배제했는지 감사 로그로 남긴다.
- **E7 꼬리 외삽**: GPD/SPOT로 α<1/n 임계를 외삽하는 민감도 분석을 하고 경험 분위수와 비교한다. "보장" 표현은 금지한다.
- **E8 확률 보정 비교**
  - Kriegel unify, Platt(평활), Firth, beta, isotonic, Venn–Abers를 비교한다.
  - 지표는 Brier·로그손실(블록 부트스트랩 CI)이다.
  - π 민감도 표를 붙인다.
- **E9 비용·예산 결정표**: 비용비 {10, 50, 100, 300} × π {10⁻³, 10⁻⁴} × 예산 {1/일, 1/주}로 결정이 어떻게 바뀌는지 보인다.
- **E10 합성 초기 고장 주입**
  - 정상 버스트의 진동 RMS를 δσ만큼(δ=0.5–3) 늘리거나, 이상 버스트 특징을 10–50% 섞는다.
  - 이동 크기별 탐지율(ARL1)을 그린다.
  - "조기탐지" 주장의 유일한 근거이므로 시뮬레이션임을 명시한다.
- **E11 경보 품질 KPI**: 정상 데이터에서 chattering(1분 내 개시·해제), fleeting, 경보 지속시간 분포, 10분당 경보 수를 보고한다.
- **E12 현장 검증 계획(제안서용)**
  - 섀도 운전 기간: 교대 예산 입증에 ≥24시간, 일 예산에 ≥72시간, 주 예산에 ≥3주.
  - 운전원 판정 로그를 남긴다.
  - 임계 변경은 변경관리(MoC)로 기록한다(ISA §17).

### 3.8 보고서 문구 예시(정직한 진술)

- "오경보율은 버스트 단위로 보정했다. 보정에는 2022-07-12(화) 00:30–01:00의 정상 운전만 사용했다. 명목 α=0.01이며, 보정집합이 고정된 상태의 실제 오경보율은 95% 확률로 약 2% 이하다(Beta 분포). 이 보장은 보정 기간과 같은 운전 조건에서만 성립한다."
- "지속성 규칙을 적용한 경보 사건 기준으로, 시험 구간(01:00–01:17)에서 오경보는 x건이었다(노출 0.28시간, Poisson 95% CI …). 0건이어도 95% 상한은 10시간당 수 건 수준이다. 교대당 1건 이하를 입증하려면 오경보 0건인 정상 운전 24시간 이상이 필요하다."
- "이상 확률 P는 연간 고장 빈도 가정(π)에 따라 달라진다. 표 X에 π=10⁻³과 10⁻⁴의 결과를 함께 제시했다. 학습셋의 이상 비율 3.4%는 실제 빈도가 아니므로 그대로 쓰지 않았다."
- "이상 에피소드가 1개뿐이므로 사건 단위 재현율은 1/1(95% CI 2.5–100%)이며 추정할 수 없다. 버스트 단위 탐지율은 같은 에피소드 안의 반복 측정이므로 일반화 성능으로 해석하지 않는다."

---

## 4. 위험·한계·반론

1. **표준 적용 범위의 차이**
   - ISA/IEC/EEMUA의 KPI는 연속 공정 산업의 운전원 콘솔이 받는 "모든 경보"에 대한 값이다. 프레스 공장의 예측정비 신호 하나에 그대로 적용하는 것은 유비에 불과하다.
   - 데드밴드·지연 출발값도 공정변수(유량·레벨·압력·온도)용이다 [S10].
   - 벤더 저자는 평균 환산 자체가 "무의미"하다고 반박한다 [S09].
2. **인간요인 근거의 한계**
   - 실험 근거가 대학생 대상의 실험실 연구다(n=138 [S93], n=32 [S94]).
   - 현장 연구인 항공교통관제에서는 오경보 45%에도 cry-wolf가 관찰되지 않았다 [S95].
   - 오경보 비용은 맥락에 따라 다르므로 "오경보가 항상 놓침보다 나쁘다"고 일반화하면 안 된다.
3. **교환가능성과 요일·시간 교란**
   - 보정은 화요일 심야 77분이고, 이상은 일요일 오전이다. 일요일 정상 운전의 오경보는 전혀 평가할 수 없다.
   - 콘포멀·NP 보장은 보정 조건 밖으로 이전되지 않는다.
4. **분포 가정**
   - CUSUM ARL 공식(Siegmund·NIST)은 i.i.d. 정규를 전제한다.
   - 버스트 RMS는 양수이고 치우쳐 있으므로 로그 변환이나 비모수(콘포멀) CUSUM이 필요하다.
   - §3.0의 상관 몬테카를로는 AR(1) 가정이다.
5. **이 보고서의 계산은 낙관적**
   - 분위수 임계를 대부분 표본 안에서 정했다.
   - 특징은 RMS 3개뿐이다.
   - 실제 모델로 E2–E4를 다시 해야 한다.
6. **확률 보정은 검증할 수 없다**
   - 독립 양성 사건이 1개뿐이므로 어떤 보정 확률이든 가정 기반이다.
   - 외부 검증 권고치(사건 100개 이상)는 의료 문헌에서 온 것이고 원문도 재확인해야 한다 [S77].
   - ECE와 신뢰도 도표는 21개 양성으로 의미가 없다.
7. **비용·사전확률 값이 없다**
   - "2–3일 정지"는 가이드북 기술을 공유 컨텍스트로 전달받은 것이며 원문 미확인이다.
   - 오경보 비용에는 신뢰 저하(장기 비용)가 빠져 있다.
8. **P–F 구간을 모른다**
   - 이상 에피소드가 말기 상태일 수 있다.
   - "조기" 주장은 합성 실험에만 기대고, 합성 방식 자체가 결과를 좌우한다.
9. **온라인 적응의 위험**
   - ACI나 재보정은 고장을 정상으로 흡수할 수 있다.
   - 운전원 판정 라벨은 편향(확인 편향, 바쁜 교대에서의 일괄 처리)을 가질 수 있다.
10. **외삽 모형 위험**: EVT/GPD 꼬리 외삽은 임계 선택과 모형에 민감하다. "보장"으로 표현하면 과장이다.
11. **프리프린트 근거**: e-detector 계열(특히 2026-08 프리프린트 S52)은 심사 전이다.
12. **저작권·라이선스**
    - 표준 원문은 유료이고 HSE는 Crown copyright다. 표를 전재하면 안 된다.
    - Tong 등 [S79]은 CC BY-NC라 그림 재사용 시 상금이 있는 공모전이 "비상업"인지 판단이 필요하다. 문장 인용을 권장한다.
    - 목차 발췌본과 HSE 사본은 제3자 호스팅이므로 원 출처로 인용한다.
13. **벤더 문서의 편향**: S09, S10, S12는 판매 이해가 있을 수 있다. 수치는 1차 표준 조항 번호와 함께 쓴다.
14. **반론(오경보 억제 과잉)**
    - 지속성·누적은 지연을 늘린다.
    - Shewhart는 큰 이동에서 CUSUM보다 빠르다 [S26].
    - 갑작스러운 고장에 대비해 위험 단계는 지속성 없는 빠른 경로를 유지해야 한다.
15. **지표 비교성**: 가이드북은 행 기준 정확도 97.51%·F1 0.7476을 보고했다. 우리 버스트·사건 지표와 직접 비교할 수 없으므로 두 단위를 병기하고 차이를 설명해야 한다.

## 5. 아직 확인 못 한 것

- ISA-18.2-2016 표 5·6·7의 원문 문구와 전체 값. 특히 4단계 우선순위 분포 예시와 "시간당 약 6/12건"은 스니펫과 IChemE 재인용으로만 확인했다.
- IEC 62682:2022 표 5–7 값과 2014판 대비 수치 변화.
- EEMUA 191 4판 표 9–11(필터·데드밴드·디바운스 기본값)과 표 15–19의 수치(목차만 확인).
- ISA-TR18.2.3의 데드밴드·지연 그림 수치를 TR 원문으로 확인하는 것. 지금은 2차 매체 [S10]로만 확인했다.
- ISA-TR18.2.8 *Guidelines for Non-alarm Notifications*의 발간 여부와 내용.
- chattering 경험칙(예: "1분에 3회 이상")의 출처(ISA TR5 등).
- ISO 17359 §8.9 본문(다단계 alert/alarm 문장은 search-only), ISO 20816-1 §6.4.2의 "기준선 + B영역 상한 25%" 규칙(벤더 사이트만 확인).
- ISO 13381-1·13379-2 본문(KS 등재만 확인). KOSHA 가이드 등 국내 경보관리 지침(검색 예산 소진으로 미조사).
- NAMUR NE 107 2025 개정 내용과 F/C/S/M 공식 정의 문구.
- IEC 62682가 KS에 다른 번호·명칭으로 부합화됐는지 여부(번호·명칭 검색은 0건).
- Xu 2012·Adnan 2011/2013의 FAR·MAR·AAD 정확 수식. 본 보고서의 개시율 근사 (1−p)pⁿ는 자체 유도다.
- Champ & Woodall의 정확값 91.75(자체 재현 92.3).
- Moubray, Nowlan & Heap, SAE JA1012의 P–F 정의와 "점검 주기 = P–F/2" 같은 규칙.
- 쪽수 미확인: Barber 2023, Brown 2001, Künsch 1989, Moustakides 1986, DeGroot 1983. Nixon 2019의 게재처. e-detector(S51)의 최종 게재처.
- Collins 2016의 "사건 100/200개" 권고 원문 문구.
- Venn–Abers·beta 보정·integrative conformal을 우리 데이터에 실제로 적용했을 때의 거동(미실험).
- 가이드북의 "2–3일 정지" 원문, 시험 분할 구성(정확도 97.51%의 분모).
- Joint Commission 경보 피로 통계(403으로 미확인).
