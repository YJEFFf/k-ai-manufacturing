# 04. 출처 통합 — 두 계획의 출처표를 하나로 (2026-10-02)

- 기본 목록은 Claude v2의 `02_research_sources.md`(핵심 출처 130여 개, ID 체계 KM-·DP-·AD-·ST-·DS-·SW- 등)다. 이 문서는 그 목록을 다시 적지 않는다.
- 이 문서가 다루는 것은 아래와 같다.
  1. 통합안이 직접 기대는 출처
  2. 코덱스에만 있던 출처(CX-)
  3. 두 계획의 출처 판단이 충돌한 곳과 결론
  4. 데이터셋 통합 표
  5. 제외·보류 통합 목록
  6. 아직 확인하지 못한 것
  7. 인용 주의(블라인드 심사 지적)
  8. 코드 의존성 라이선스(계약 테스트 T8의 근거)
- 오늘(2026-10-02) 직접 확인한 것은 확인 열에 "(통합 확인)"으로 적었다.
- `[J1]`·`[J2]`는 블라인드 심사자 1·2가 확인하거나 지적한 것이다(`judges/`).

## 0. 사용 원칙 (두 계획 공통)

1. 원출처가 불분명한 자료는 데이터로도, 근거로도 쓰지 않는다. 검색 결과·블로그·재배포본은 원출처를 찾는 단서로만 쓴다 [X01 §1], [C02 §0].
2. DOI가 있다고 동료심사를 거친 것은 아니다. arXiv는 출판 상태를 따로 적는다 [X01 §1].
3. "설명 확인"은 원시 파일 검수나 성능 재현이 아니다. 확인 범위(초록·전문·공식 문서)를 표시한다 [X01 §1], [C02 확인 열].
4. 제조사 문서는 제품 기능·계측 항목·절차의 1차 자료로만 쓴다. 홍보 절감률은 옮기지 않는다 [X01 §1].
5. 표준 소개 페이지를 읽은 것만으로 표준 원문을 검토했다거나 준수했다고 쓰지 않는다 [X01 §1], [C02 §4 서지 정정].
6. 그림은 재사용 라이선스가 확인된 것만 출처를 밝혀 쓴다. 나머지는 자체 그림으로 그린다 [C02], [X04 §7].
7. 같은 데이터의 다른 배포본(UCI·Zenodo 등)과 같은 논문의 다른 판(arXiv·학회판)은 독립 증거로 두 번 세지 않는다 [X01 §2].
8. 가이드북(KM-02)을 인용할 때는 인쇄 쪽 번호를 쓰고 PDF 쪽을 병기한다. 인쇄 쪽과 PDF 쪽은 1쪽 차이 난다(인쇄 40쪽 = PDF 41쪽, 7·10쪽도 같음) [X README §4.1, J2].
9. 저장소 안의 분석 결과(이전 패키지 수치, 이번 `eda/` 재계산)는 문헌이 아니라 내부 근거다. 경로와 스크립트를 함께 적는다.

## 1. 통합안이 직접 기대는 출처

| 쓰는 곳(02 문서) | 출처 ID(Claude 02 목록 또는 아래 CX) | 비고 |
|---|---|---|
| 데이터·이용 조건 | KM-02(가이드북), KAMP 데이터셋 페이지, 출처 표기 양식 [C01 §1] | 가이드북 PDF는 재배포 금지. 수치 인용만 |
| 외부 데이터 규정 | 9/22 수정 공고 보관본 `yejun/analysis/reselection/official_sources/notice28.txt` | (통합 확인) "(추가) 외부데이터 활용 관련" 절 |
| conformal·보정 | ST-01 Bates 2023, ST-02 Vovk cross-conformal, ST-03 Barber 2021 jackknife+, ST-04a Vovk·Gammerman·Shafer 2005, ST-05 Angelopoulos·Bates, ST-06 Gibbs·Candès 2021 | 두 계획 공통(Bates·Gibbs) |
| 순차 판정·경보 | ST-04b Shiryaev 1963, NIST CUSUM·EWMA, ISA-18.2, CX-12 Howard 2021 | Howard는 "반복 관찰 보장"의 한계 근거로만 |
| 평가 함정 | AD-01 Wu·Keogh, AD-02 Kim 2022(point-adjust), AD-05 Sarfraz 2024, TSB-AD, CX-02 affiliation | |
| 다중 모드 정상 | CX-03 Yu·Qin 2008 | 조건별 정상 모델의 선행 근거(프레스 검증 아님) |
| 표현 도전자 | CX-08a MiniRocket(Dempster 2021), sktime(BSD-3) | (통합 확인) |
| 증강 설계 | CX-18 Iwana·Uchida 2021, Claude R5 계열(주입·MAPOD) | |
| 지름길 점검 | Kauffmann 2025(Clever Hans) | 두 계획 공통 |
| 사전학습 제외 근거 | SW-10 MOMENT(MIT, 문맥 512), CX-11 TSPulse(Apache-2.0, AD 입력 1,536–2,048) | 두 계획 공통 결론 |
| 현장·경보 | ISA-18.2, R9 계열 [C02], CX-15 Bosch Rexroth, CX-16 HYDAC | 제조사 문서는 점검 항목 근거로만 |
| 외부 R4(선택) | DS-01 UCI/ZeMA(CC BY 4.0), CX-D2 Beihang | |
| 블록 단위 추론(제약 n·k의 OC, 드리프트) | CX-25 Künsch 1989(블록 부트스트랩). 단조 순서의 정확 순열 p(1/n!)는 계산으로 충분 | 03 원칙 7, 02 §5.3 [J1] |
| 0건일 때 상한 | ST-12 Clopper–Pearson 1934, ST-14 Garwood 1936 | 버스트 FPR·FA/h 상한 |
| 검출한계 a50·POD | SY-01 MIL-HDBK-1823A | 계열 평균 POD 금지의 근거도 같음 |
| 상호작용 분석(02 §5.5) | XE-04 Friedman·Popescu 2008(H 통계량), XE-03 Apley·Zhu 2020(ALE). 부분의존은 scikit-learn(SW-01) | [J2] |
| `p_anomaly` 붕괴 점검·구간(Tier 2) | ST-09 Vovk·Petej 2014(Venn–Abers), 구현 후보 SW-09 | [J1] |
| 공식 개발환경 | 9/22 공고 보관본(`notice28.txt`) "개발환경: 자체 개발환경(Python, Anaconda-Jupyter Notebook), KAMP-NOTE, KAMP AI-PaaS 중 선택" | 03 R3 Jupyter 확인 [J2] |
| B0 기준선 수치 | KM-02 인쇄 40쪽(F1 0.7476, 정확도 97.51 %), 저장소 기존 재현 0.614(`yejun/analysis/press_selection/unified_comparison.md`), 60에폭 파일럿 0.646 [C01 §7] | 03 R2 B0 3시드 [J2] |
| 정정된 데이터 사실(진동 내보내기 경로, 공식 분할 두 단위 F1, 모두-정상 95.69 %, 블록 단위 드리프트) | 내부 근거: `eda/check_judge_findings.py`와 출력, `judges/JUDGE1_REPORT.md`·`JUDGE2_REPORT.md` | 02 §2 [J1, J2] |

## 2. 코덱스에만 있던 출처 (CX-)

확인 범위는 코덱스 문서의 기록이고, 오늘 다시 확인한 항목만 따로 표시했다. "쓰는 곳"이 "—"이면 통합안에서 쓰지 않고 발견 기록으로만 둔다.

| ID | 서지 | 확인 범위 | 이용·위험 | 쓰는 곳 |
|---|---|---|---|---|
| CX-02 | Huet 등, "Local Evaluation of Time Series Anomaly Detection Algorithms"(affiliation metrics), 저자 저장소 `ahstat/affiliation-metrics-py` | 저자 저장소·설명 [X01 §4.1] | 보조 사건 지표. 독립 고장 부족을 해결하지 않음 | 평가 함정(보조) |
| CX-03 | Yu·Qin, "Multimode process monitoring with Bayesian inference-based finite Gaussian mixture models" AIChE J 54(7):1811–1829 (2008), DOI 10.1002/aic.11515 | 출판사 초록 [X01 §4.2]. **(통합 확인) Crossref 서지 일치** | 유료. 개념 인용만 | 3절 근거 |
| CX-04 | Katser 등, "Unsupervised Offline Changepoint Detection Ensembles", Applied Sciences 11(9):4280 (2021), DOI 10.3390/app11094280 | 출판사 PDF 관련 절 [X01 §4.2]. 권·호는 심사자 2가 Crossref로 확인 | 오프라인 방법. 실시간 지연으로 옮기지 않음. SKAB 원출처 연결 | — |
| CX-05 | "ECOD: Unsupervised Outlier Detection Using Empirical Cumulative Distribution Functions", arXiv 2201.00382 (2022) | 초록·서지 [X01 §4.2] | 가벼운 경험분포 기준선 후보 | — |
| CX-06 | Adams·MacKay, "Bayesian Online Changepoint Detection" arXiv 0710.3742 (2007) | 초록·서지 [X01 §4.2] | 변화점 ≠ 고장 | — |
| CX-08 | ROCKET, arXiv 1910.13051, 저자 코드 `angus924/rocket` | 초록·저자 문서 [X01 §4.3] | 원저자 코드 라이선스는 아래 충돌 1 참고 | — |
| CX-08a | Dempster·Schmidt·Webb, "MiniRocket: A Very Fast (Almost) Deterministic Transform for Time Series Classification" KDD 2021, pp. 248–257, DOI 10.1145/3447548.3467231 | **(통합 확인) Crossref 서지** | 구현은 sktime(BSD-3-Clause, (통합 확인) 저장소 LICENSE). 원저자 저장소는 GPL-3.0 | 5.4 C-REP |
| CX-09 | TS2Vec, AAAI 2022, arXiv 2106.10466, 저자 코드 `zhihanyue/ts2vec` | 초록·공식 사용법 [X01 §4.3] | 증강이 고장 정보를 지울 위험 | — |
| CX-10 | TranAD, arXiv 2201.07284 (2022) | 초록·서지 [X01 §4.3] | 짧은 기록에서의 근거 없음 | — |
| CX-11 | TSPulse, arXiv 2505.13033, IBM 공식 모델 카드 `ibm-granite/granite-timeseries-tspulse-r1` | 공식 모델 카드 [X01 §4.3] | Apache-2.0. AD 입력 1,536–2,048 이상 | 5.4 제외 근거 |
| CX-12 | Howard 등, "Time-uniform, nonparametric, nonasymptotic confidence sequences", Annals of Statistics (2021), arXiv 1810.08240 | 초록·서지 [X01 §4.4] | 유효한 귀무 모형 없이 점수를 누적해 같은 보장을 주장하지 않는다는 경계로만 | 4절 |
| CX-13 | Gibbs·Cherian·Candès, "Conformal Prediction with Conditional Guarantees", arXiv 2305.12616 | 초록·서지 [X01 §4.4] | 집단별 보정과 표본량 | 3.4절 배경 |
| CX-14 | NI "Acquiring an Analog Signal: Bandwidth and Nyquist", "Dynamic Signal Acquisition Fundamentals" | 제조사 기술 문서 [X01 §4.5] | 원 취득·필터·저장 주기 구분 | 2절 3행 배경 |
| CX-15 | Bosch Rexroth "CytroConnect Solutions", "Failures — causes and advices" | 제조사 공식 문서 [X01 §4.5] | 절감률 인용 금지 | 9절 점검 항목 |
| CX-16 | HYDAC "Components, systems and service for test benches and test systems" | 제조사 문서 [X01 §4.5] | 수집 항목 후보 | 9절 로드맵 |
| CX-17 | ISA "Alarm management life cycle", InTech 2018 | 기술 해설 [X01 §4.5] | 표준 원문 아님 | 9절(ISA-18.2 보조) |
| CX-18 | Iwana·Uchida, "An empirical survey of data augmentation for time series classification with neural networks" PLOS ONE 16(7):e0254841 (2021), DOI 10.1371/journal.pone.0254841 | 방법·결과 절 [X04 §2]. **(통합 확인) Crossref, CC BY 4.0** | 그림 재사용 가능(출처 표기) | 6.2절 |
| CX-19 | Zhao 등, T-SMOTE, IJCAI 2022, pp. 2406–2412, DOI 10.24963/ijcai.2022/334 | IJCAI 공식 페이지·방법 절 [X04 §2]. 서지·쪽수는 심사자 2가 Crossref로 확인 | 고장 전 연속 이력이 없어 원 논리를 그대로 못 씀 | — |
| CX-20 | Desai 등, TimeVAE, arXiv 2111.08095 (2021) | 초록·서지, 프리프린트 [X04 §2] | U5 후보 | Tier 2 조건부 |
| CX-21 | Yuan·Qiao, "Diffusion-TS: Interpretable Diffusion for General Time Series Generation", ICLR 2024, arXiv 2403.01742 | 저자 전문·방법 개요 [X04 §2] | U5 후보 | Tier 2 조건부 |
| CX-22 | Tashiro 등, CSDI, NeurIPS 2021 | 초록·코드 설명 [X04 §2] | 결측 복원용. 고장 생성 근거 아님 | — |
| CX-23 | Shidani 등, "Beyond Real Data: Synthetic Data through the Lens of Regularization", AISTATS 2026, PMLR v300 | 초록·서지 [X04 §2]. 통합 확인 못 함 | 이미지 등의 결과를 프레스 비율로 옮기지 않음 | 6.2 배경(선택) |
| CX-24 | Oh 등, "A Hybrid Approach of Data-Driven and Signal Processing-Based Methods for Fault Diagnosis of Hydraulic Rock Drill", PHM Society Conference 2022 | 학회 원문 페이지 [X01 D5] | 논문만. 데이터는 라이선스 표기 없음 | — |
| CX-25 | Künsch, "The Jackknife and the Bootstrap for General Stationary Observations", The Annals of Statistics 17(3) (1989), DOI 10.1214/aos/1176347265 | **(통합 확인) Crossref 서지**. 쪽수는 Crossref에 없어 미확인. Claude v2 목록에는 미확인 항목으로만 있었다 [C02 §5-18] | 인용만 | 03 원칙 7, 02 §5.3(블록 부트스트랩 OC) |

- 코덱스의 TimeEval(Schmidl 등, VLDB 2022), NIST CUSUM·EWMA, Kauffmann 2025, Bates·Barber·Gibbs·Guo, catch22, MOMENT, Anomaly Transformer, TimeGAN은 Claude 목록에도 있다.
- 두 목록의 서지는 서로 맞는다. Wu·Keogh는 Claude 쪽(IEEE TKDE 35, 2023, ICDE 2022 확장초록)을 기본으로 쓴다.

## 3. 두 계획의 판단이 충돌한 곳과 결론

| # | 대상 | 코덱스 | Claude v2 | 결론 |
|---|---|---|---|---|
| 1 | catch22 / ROCKET 계열 라이선스 | catch22/24를 가벼운 특징 후보로 제안. 라이선스 언급 없음 | catch22는 GPL-3.0이라 위험 목록 | **(통합 확인)** catch22 저장소 GPL-3.0, MiniRocket 원저자 저장소 GPL-3.0, sktime BSD-3-Clause → 표현 도전자는 sktime 구현만 쓴다 |
| 2 | 외부 데이터 규정 | 공지 원문 미확인이라 확정 규정으로 인용 안 함 | "신고 부담 없이" Tier 1에서 미사용 | **(통합 확인)** 9/22 수정 공고 보관본: 활용 가능, 사유·방법·출처 명시, 공개에 문제없는 데이터만 |
| 3 | Paderborn | 실제 라이선스 확인 후 도입 | CC BY-NC 4.0(KAt 페이지 열람) | Claude 기록 채택 → 데이터로 쓰지 않음. 논문 인용만 |
| 4 | PHM 2022 착암기 | 도입 시 이용 조건 확인 | 데이터 라이선스 표기 없음 | 데이터로 쓰지 않음. 논문(CX-24)은 인용 가능 |
| 5 | SKAB | 우선 후보, 라이선스 대조 필요(GPL-3.0 대 AGPL-3.0 불일치 확인) | 같은 불일치 → 쓰지 않음 | 쓰지 않음. GitHub의 GPL-3.0은 심사자 2가 API로 다시 확인했다. Kaggle의 AGPL-3.0 표기는 인증이 필요해 재확인하지 못했다. 어느 쪽이든 카피레프트라 데이터 재배포 조건이 걸린다 [J2] |
| 6 | 생성 모델(TimeGAN 등) | U5 조건부 후보 | 고르지 않음(이상 1건 복제 위험) | 기본 제외, U2·U3 이익 시에만 Tier 2 검토 |
| 7 | 사전학습 기초모델 | 입력 길이 부적합, 조건부 도전자 | Tier 3(라이선스 확인분만) | 제외(근거: 두 계획 공통의 입력 길이) |
| 8 | 가이드북 쪽 번호 | 인쇄 쪽과 PDF 쪽이 1쪽 차이 | 쪽 표기 기준을 밝히지 않음 | 인쇄 쪽 기준 + PDF 쪽 병기(0절 8항). 심사자 2가 인쇄 40쪽 = PDF 41쪽을 확인 [J2] |

## 4. 데이터셋 통합 표

| 자료 | 이용 조건 | 통합안에서의 지위 | 근거 |
|---|---|---|---|
| 대회 프레스 원본(KAMP 소성가공 예지보전) | 콘텐츠 변경허용, 출처 표기, 재배포 조항 없음 | 주 데이터 | [C01 §1] |
| UCI/ZeMA 유압 | CC BY 4.0 | 선택 R4(권장). 크기 앵커 | [C02 DS-01], [X01 D2] |
| Beihang 항공 피스톤펌프 | 데이터 CC BY 4.0(논문 CC BY-NC) | 선택 R4 대안. 메타데이터 검수 선행. 논문 서지(Data in Brief 64:112336, Wang·Ma·Fu)는 심사자 2가 Crossref로 확인 | [X01 D6], [J2] |
| NLN-EMP | CC0 | 스냅샷 수집 흉내 참고(Tier 2) | [C02] |
| KAMP 소성가공 자원최적화 | KAMP 조건 | 정상 변동 폭 참고(Tier 3) | [C02] |
| AI4EU 로봇 펌프 | CC BY 4.0 | 쓰지 않음(고장 레이블 없음). 파일 34개(설명 PDF 포함)·18.93 GB·저자 3인은 심사자 2가 Zenodo·DataCite로 확인 | [X01 D4], [J2] |
| ESPset | 데이터 CC BY 4.0, 코드 MIT | 쓰지 않음(스펙트럼만, 시간 순서 없음) | [X01 D9] |
| Paderborn KAt | CC BY-NC 4.0 | 쓰지 않음 | [C02 DS-08] |
| MIMII DUE | CC BY-NC-SA 4.0 | 쓰지 않음(비영리, 음향) | [X01 D8] |
| SKAB | GPL-3.0 / AGPL-3.0 불일치 | 쓰지 않음 | [X01 D3], [C02] |
| PHM 2022 착암기 | 표기 없음 | 쓰지 않음 | [C02], [X01 D5] |
| CWRU, MAFAULDA, Kaggle pump, Hercik 공개분 | 표기 없음 등 | 쓰지 않음 | [C02] |
| FZU_HGPFD, 원심펌프 long-tail(2026) | 기관·조건 미확인 | 도입 대기(발견 기록) | [X01 D10·D11] |
| 같은 수행기관의 다른 KAMP 데이터(용접 등) | — | 내부 참고만. 제공 기관 비판으로 읽힐 수 있어 결과물에 쓰지 않음 | [C01 §2-1] |

## 5. 제외·보류 통합 목록

- Claude v2의 사용 금지 33개 [C02 §3]와 서지 정정 [C02 §4]는 그대로 유지한다.
- 코덱스의 보류·제외 [X01 §5]를 더한다.

| 자료 | 상태 | 처리 |
|---|---|---|
| arXiv 2603.00199 축방향 피스톤펌프 디지털 트윈 다조건 보정 | 철회 | 인용 금지 |
| arXiv 2512.19280 축방향 피스톤펌프 디지털 트윈 보정 | 프리프린트 | 아이디어 참고만 |
| RESS 2024, DOI 10.1016/j.ress.2024.110539(손상된 유량 신호) | 본문 미확보 | 방법·수치 인용 보류 |
| Applied Sciences 16(12):6051(가변 부하 펌프 진단) | 본문 접근 제한 | 검색 요약 수치 채택 금지 |
| Soh 등, Applied Sciences 16(5):2414, DOI 10.3390/app16052414(굴착기 동작 상태) | 서지만(심사자 2 Crossref 확인) | 아이디어 후보 |
| DBpia NODE12859580(국내 프레스 다중 센서) | 서지 단서 | 방법·결과 인용 금지 |
| 프레스 운전·생산 이력 UMAI 카탈로그 | 원문 404 | 제외 |
| 블로그·Reddit·데이터 모음집·임의 미러 | 원출처 아님 | 검색 단서로만 |

## 6. 아직 확인하지 못한 것

- [C02 §5]의 미확인 20개를 그대로 이어받는다. 단 9번의 PyYAML 라이선스는 해소됐다(MIT, 8절). 여기에 아래를 더한다.
  - CX-23 Shidani 2026의 PMLR 쪽수(통합 확인 시 Crossref 요청 제한)
  - CX-25 Künsch 1989의 쪽수(Crossref 메타데이터에 없음)
  - SKAB의 Kaggle 라이선스 표기(인증 필요)
  - Beihang 데이터의 열 설명과 본문 불일치 여부 [X01 D6]
  - UCI 압력 센서 범위와 정격 압력의 관계(R4를 할 때)
- 코덱스가 원문을 열지 못한 KAMP 최신 공지는 저장소 보관본(9/22)으로 대신한다. 그 뒤 추가 개정이 있었는지는 확인하지 못했다.

## 7. 인용 주의 (블라인드 심사 지적)

- [C02 §1] 리서치 요약에는 v2에서 철회한 v1 주장이 남아 있다. 이 요약 문장들은 인용하지 않는다 [J1].
  - 슬립 정량 "0.12 → 0.63 %"
  - "이상 전류 99.67 %"
  - "블록 28개 p 0.034"(정정값은 27개·0.036)
  - "양측 19.8 % 대 단측 0.8 %"
  - "부하 매칭 상부진동 = 고장 쪽 가장 강한 증거"
  - "전류 동역학은 지터 2–3 ms로 재현"
- [C02]의 "쓰는 곳" 열은 v1 절 번호다.
- 서지 표본 점검: 심사자 2가 Crossref·DataCite로 두 계획의 DOI 26건을 조회했고 모두 맞았다(`judges/JUDGE2_REPORT.md` 4.3절).

## 8. 코드 의존성 라이선스 — 계약 테스트 T8의 허용 목록 근거

`licenses_allowed.yaml`과 계약 테스트 T8(03 §4)이 이 표를 근거로 한다. 오늘 원문으로 확인한 것은 "(통합 확인)"이다.

| 패키지 | 쓰임 | 라이선스 | 확인 |
|---|---|---|---|
| numpy, scipy, pandas, statsmodels | 핵심 | BSD-3-Clause | [C02 SW-03] |
| matplotlib | 핵심(그림) | Matplotlib License(PSF 기반) | [C02 SW-03] |
| scikit-learn | 핵심(IF, GBM, 부분의존) | BSD-3-Clause | [C02 SW-01] |
| PyYAML | 핵심(`protocol.yaml`) | MIT | (통합 확인) GitHub `yaml/pyyaml` LICENSE. [C02 §5-9] 미확인 해소 |
| TensorFlow | 선택(B0 재현, C-DL) | Apache-2.0 | [C02 SW-05] |
| sktime | 선택(C-REP MiniRocket) | BSD-3-Clause | (통합 확인) GitHub `sktime/sktime` LICENSE |
| numba | 선택(sktime MiniRocket 의존) | BSD-2-Clause | (통합 확인) GitHub `numba/numba` LICENSE |

**쓰지 않는 것**

| 대상 | 라이선스 | 근거 |
|---|---|---|
| catch22 | GPL-3.0 | (통합 확인) [C02 §3] |
| MiniRocket·ROCKET 원저자 구현 | GPL-3.0 | (통합 확인) |
| alibi-detect, Alibi Explain | BSL 1.1(오픈소스 아님) | [C02 §3] |
| Moirai·TimesFM 3.0 가중치 | 비상업 조건 | [C02 §3] |
| OpenModelica | AGPL v3 또는 OSMC-PL | [C02 §3] |

**허용 목록 초안**
- MIT, BSD-2-Clause, BSD-3-Clause, Apache-2.0, ISC, PSF 계열(Matplotlib License 포함)
- GPL·AGPL·LGPL·비상업(NC)·BSL은 실패로 처리한다. LGPL은 검토 뒤 예외로 둘 수 있다.
- 라이선스를 판별하지 못한 패키지도 "검토 필요"로 실패시킨다.

**구현 메모**
- 설치된 배포판의 라이선스는 표준 라이브러리 `importlib.metadata`로 읽는다. 별도 도구(pip-licenses 등)를 의존성에 더하지 않는다.
- 간접 의존성까지 고정 파일(requirements lock) 기준으로 검사한다.
