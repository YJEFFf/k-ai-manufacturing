# R5 — 실제 이상이 1건뿐일 때 "방어 가능한 추가 증거" 만들기
### 합성 고장 주입 · 증강 · 물리 시뮬레이션 · 검출한계(POD) 설계

- 작성: R5 리서치 에이전트, 2026-10-01
- 독립성·범위: `yejun/` 하위와 해당 저장소의 git 기록은 열지 않았다. 저장소 파일은 하나도 수정하지 않았다. 원시 CSV 2개는 읽기 전용으로 열었다. 정상 파일은 분석했고, 이상 파일은 요약 통계만 계산했다. 이상 파일에서 본 내용은 **부록 S(봉인)**에 따로 모았다. 블라인드를 유지해야 하면 부록 S는 읽지 말 것.
- 검증 표기: **[열람]** = 원문(PDF·웹페이지·저장소 파일·데이터)을 직접 받아 내용을 확인함. **[검색만]** = 검색 결과나 Crossref/OpenAlex 메타데이터로 서지 정보만 확인하고 본문은 못 봄. **[미검증]** = 확인 못 함. 등급 A/B/C는 요청서의 정의를 따른다.
- "우리 계산" = 이번에 R5가 스크래치패드에서 직접 돌린 계산이다(스크립트는 부록 R). 설계용 파일럿이지 최종 결과가 아니다.
- 참고: 이번 세션 중간에 WebSearch 한도(200회)가 소진되었다. 그 뒤의 검증은 WebFetch, curl(arXiv·Crossref·OpenAlex·Europe PMC·GitHub raw), 원문 PDF 직접 열람으로 했다.

---

## 1. 핵심 요약

1. **실제 이상 1건은 '쉬운 사례'일 가능성이 크므로, 조기탐지 능력의 증거는 정상 데이터에 고장을 주입해 따로 만들어야 한다.** 이상 파일의 상부 진동 표준편차는 정상의 약 6배다(0.45 대 0.07, 공유 맥락의 통계). 이런 사례는 "한 줄짜리 규칙(one-liner)"으로도 잡힌다(Wu & Keogh [S12]). 그래서 실제 사례에서 성공해도 '조기' 탐지 능력은 보여주지 못한다. 조기탐지는 정상 데이터에 물리 기반 고장을 크기별로 주입해 얻는 **검출확률 곡선(POD vs 크기)**과 **검출지연 vs 성장속도**로 보여야 한다. 실제 이상 1건은 마지막에 한 번만 쓰는 '현실 시험'으로 남긴다.
2. **주입 결과는 '설계한 고장 종류에 대해서만' 유효하다(순환성).** 근거는 다섯 가지다. 주입 기반 모델선택은 유용하지만 실제 이상과 종류가 다를 수 있다(Goswami [S4]). 증강과 실제 이상 메커니즘이 어긋나면 자기지도 학습이 오히려 성능을 깎는다(Yoo [S10]). 불일치 주입은 해가 될 수 있다(NCAD [S5]). 인공 손상으로 학습하고 실제 손상으로 시험하면 정확도가 "quite low"였다(Lessmeier [S50]). 라벨 없는 내부 지표로 모델을 고르는 방법은 실무적으로 쓸모가 없었다(Ma [S15]). 대응책은 고장 '가족'별로 따로 보고하기, leave-one-family-out, 주입 격자의 사전등록, 학습용 주입과 평가용 주입의 분리다.
3. **우리 정상 데이터의 물리 구조가 주입 설계를 정한다(우리 계산).**
   - 전류: 각 버스트가 **0.600 Hz(0.594–0.607)의 거의 순수한 정현파**다(정현 적합 R² ≥ 0.994). 60 Hz 전류가 10 Hz 근처 표본화로 에일리어싱된 것으로 보인다.
   - 전류 진폭: 공회전 약 121과 부하 약 233, 두 상태로 나뉜다.
   - 진동 RMS는 전류 진폭에 강하게 묶여 있다. 하부 진동은 로그-로그 기울기 약 1.8, r = 0.96이다.
   - 결론: **부하조건부(전류 진폭 대비) 특징**이 정상 운전변화로 생기는 오경보를 막는 핵심이다. 파일럿에서 부하를 +20~+30% 올리면 비조건부 탐지기의 오경보율은 13–16%로 올랐고, 조건부 탐지기는 0–1%를 유지했다(부하 ±30%, 5-fold 기준 약 1%).
4. **증강은 정상 데이터에 '물리적으로 중립'인 것만 쓴다.**
   - 안전: 버스트 위상 무작위화, 버스트 단위 블록 부트스트랩, 버스트 내 잘라내기.
   - 위험: 시간왜곡, 순열, 믹스업, 진동만 따로 스케일링, 지터.
   - 진동 스케일링은 그 자체가 고장 주입이다. "scaling ... may change their labels"(Um [S21]).
   - 에일리어싱된 신호에 시간왜곡을 걸면 어떤 실제 속도 변화와도 대응하지 않는다. 실제 주파수가 Δf 바뀌면 에일리어스는 비례 이동이 아니라 ±Δf만큼 움직인다.
5. **생성모델(TimeGAN·Diffusion-TS·CSDI)로 고장 데이터를 만드는 것은 권하지 않는다.**
   - 이상 데이터가 600행 1건뿐이라 생성모델은 사실상 복제하게 된다. 작은 데이터에서 복제가 잦다(Somepalli [S28]). 작은 데이터에서는 수렴과 신뢰성도 문제다(TSGBench [S26]).
   - 생성 품질지표(discriminative score, predictive score/TSTR)는 이상탐지에 쓸모 있는지는 평가하지 않는다([S26]).
   - 정상 데이터 보강이 필요하면 **화이트박스 파라메트릭 생성기**(정현파, 상태 전이, 잡음)를 쓴다.
6. **외부 공개 리그 데이터는 "누설형 고장은 전류·진동에 거의 안 보이고, 오일 온도 같은 운전조건 변화는 크게 보인다"는 근거가 된다.** 데이터는 ZeMA 유압 리그다(CC BY 4.0 [S45]). 내부 펌프 누설은 펌프 고압·저압 포트를 잇는 오리피스로 모사했고, 크기는 정격유량의 3.3%와 4.6%다([S43]). 우리 계산 결과는 다음과 같다.

   | 비교 | 모터전력 변화 | 진동 변화 | 유량 변화 |
   |---|---|---|---|
   | 누설 '약' vs 없음 | +0.45% | 일관성 없음 | −3.1% |
   | 누설 '심' vs 없음 | +1.05% | 일관성 없음 | −4.5% |
   | 냉각기 열화(오일 +8~21 °C) vs 정상 | −3~−6% | +9~+28% | — |

   유량 변화는 문헌의 누설 크기와 맞는다. 결론: **누설형 고장은 전류·진동만으로 조기탐지하기 사실상 어렵다. 온도류 변화는 강력한 오경보 원인이다.** 단, 이 리그는 펌프·센서·샘플링이 우리와 다르다.
7. **검출한계 추정(우리 계산, 정규 근사).** 하부 진동의 부하조건부 RMS로 POD 90%를 얻는 데 필요한 크기는 다음과 같다.

   | 버스트당 오경보율 | 단일 버스트 | 10버스트 평균 |
   |---|---|---|
   | 1% | ×1.9 | ×1.3 |
   | 1e-5 (≈ 주 1회) | ×2.6 | ×1.5 |

   blocked 5-fold 주입 파일럿에서 진동 에너지 +20/+50/+100%의 POD는 0.17/0.67/0.95였다. 그래서 주입 격자는 **×1.1–×3** 구간에 촘촘히 둔다.
8. **오경보율 검증 능력에는 근본 한계가 있다.** 정상 데이터는 77분, 599개 버스트다. 경보가 한 번도 안 나와도 95% 상한은 버스트당 0.5%, 즉 시간당 약 2.3회다(rule of three [S59]). "주 1회 이하" 같은 현장 오경보율은 이 데이터로 검증할 수 없다. 꼬리분포 가정으로 외삽했다고 명시해야 한다.
9. **보고서 신뢰성은 NDE·과학 재현성 분야의 틀을 빌려 세운다.**
   - MIL-HDBK-1823A [S53]의 POD/MAPOD 틀: â vs a 회귀와 a90/95.
   - 같은 핸드북의 경고 두 가지: "반복 검사로 POD 표본이 늘지 않는다", "이질 데이터를 평균한 POD는 어느 것도 대표하지 않는다".
   - 사전등록(Nosek [S62]), 누설(leakage) 점검(Kapoor [S63][S64]), 모델 운용한계 명시(NASA-STD-7009B [S65]).
   - 정상 운전변화 강건성은 **불변성(metamorphic) 시험**으로 보인다(Chen [S66], Wu & Keogh [S12]).
10. **센서 구성상 구별할 수 없는 쌍을 명시하면 과제의 'FN/FP 조건 분석'에 바로 답이 된다.** 예: 마찰형 토크 증가와 부하·전원전압 변화, 소폭 진동 증가와 오일온도 변화. 압력·온도·생산 로그가 없으면 원리적으로 구분할 수 없는 구간이다. 그 구간에서 FP/FN이 몰린다고 정직하게 제시하는 편이 낫다.

---

## 2. 출처 표

등급: A 동료심사 학술지·주요 학회·국제/국가 표준·정부기관, B 프리프린트·기술보고서·제조사 기술문서·학위논문, C 블로그·포럼·마케팅(근거로 쓰지 않음).

### 2-A. 시계열 이상탐지(TSAD)의 합성 이상 주입·택소노미·평가

| # | 인용 | 유형·등급 | 검증 | 위험 신호 | 라이선스·저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S1 | Lai, Zha, Xu, Zhao, Wang, Hu. "Revisiting Time Series Outlier Detection: Definitions and Benchmarks." NeurIPS 2021 Datasets & Benchmarks Track. https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/file/ec5decca5ed3d6b8079e2e7e7bacc9f2-Paper-round1.pdf | 학회 논문, A | [열람] PDF 본문(택소노미·합성 공식·결과) | 실데이터 결과가 오염비율 6개 중 최고값 보고(낙관적) | 코드 TODS(Apache-2.0, GitHub API 확인) | 낮음. 그림 재사용은 저작권 확인 필요 |
| S2 | Schmidl, Wenig, Papenbrock. "Anomaly Detection in Time Series: A Comprehensive Evaluation." PVLDB 15(9):1779–1797, 2022. doi:10.14778/3538598.3538602 | 학술지(PVLDB), A | [열람] PDF | 하이퍼파라미터를 GutenTAG 합성 데이터로 튜닝한 뒤 전체 평가에 사용(합성→실데이터 전이 가정) | CC BY-NC-ND 4.0(본문 표기) | 그림 변형·상업 이용 불가. 인용만 |
| S3 | Wenig, Schmidl, Papenbrock. "TimeEval: A Benchmarking Toolkit for Time Series Anomaly Detection Algorithms." PVLDB 15(12):3678–3681, 2022. doi:10.14778/3554821.3554873. GutenTAG: https://github.com/TimeEval/GutenTAG | 데모 논문 A + 오픈소스 B | [검색만] 논문(Crossref). [열람] GutenTAG README·LICENSE·문서(anomaly-types.md, base-oscillations.md) | 합성 기본진동(sine 등) 중심이라 실제 신호와 다름 | GutenTAG MIT, TimeEval MIT | 낮음. 코드 포함 시 MIT 고지 |
| S4 | Goswami, Challu, Callot, Minorics, Kan. "Unsupervised Model Selection for Time-series Anomaly Detection." ICLR 2023 (notable top-25%). arXiv:2210.01078 | 학회, A | [열람] arXiv PDF(부록 A.5 주입 정의 포함) | 의사라벨 평가에 adjusted F1(point-adjust 계열) 사용 | 코드 Apache-2.0(GitHub API) | 낮음 |
| S5 | Carmona, Aubet, Flunkert, Gasthaus. "Neural Contextual Anomaly Detection for Time Series." IJCAI 2022, pp. 2843–2851. doi:10.24963/ijcai.2022/394 | 학회, A | [열람] arXiv 본문 + IJCAI 페이지 | F1을 "best threshold on the test set"으로 계산(낙관적) | — | 낮음 |
| S6 | Ren, Xu, Wang, et al. "Time-Series Anomaly Detection Service at Microsoft." KDD 2019. doi:10.1145/3292500.3330680 | 학회(산업), A | [열람] arXiv 본문(주입 공식 식 10) | 산업 KPI 데이터. 주입 6,500만 점 학습 | — | 낮음 |
| S7 | Jeong, Yang, Ryu, Park, Kang. "AnomalyBERT: Self-Supervised Transformer for Time Series Anomaly Detection using Data Degradation Scheme." ICLR 2023 Workshop (ML for IoT). arXiv:2305.04468 | 워크숍, B | [열람] arXiv | point-adjust F1도 함께 보고 | — | 중간(워크숍 등급) |
| S8 | Xu, Wang, Jian, Liao, Wang, Pang. "Calibrated One-Class Classification for Unsupervised Time Series Anomaly Detection" (COUTA). IEEE TKDE 36:5723–5736, 2024. doi:10.1109/TKDE.2024.3393996 | 학술지, A | [열람] arXiv 본문. [검색만] 출판 서지(Crossref) | "simulated anomalies와 실제 유형이 겹치지 않아도 도움"이라는 주장. Yoo [S10]와 상충 | IEEE 저작권 | 낮음 |
| S9 | Darban, Webb, Pan, Aggarwal, Salehi. "CARLA: Self-supervised contrastive representation learning for time series anomaly detection." Pattern Recognition 157:110874, 2025. doi:10.1016/j.patcog.2024.110874 | 학술지, A | [열람] arXiv 본문(Algorithm 1) | 주입 크기 3–5σ로 큼. 조기·미세 고장과 거리 있음 | Crossref상 CC BY 4.0 | 낮음 |
| S10 | Yoo, Zhao, Akoglu. "Data Augmentation is a Hyperparameter: Cherry-picked Self-Supervision for Unsupervised Anomaly Detection is Creating the Illusion of Success." TMLR 2023. arXiv:2208.07734 | 학술지(TMLR), A | [열람] arXiv 초록·서론 | **이미지** AD 대상(시계열에는 유추 적용) | — | 낮음. 영역 차이 명시 필요 |
| S11 | Deforce, Lee, Baesens, Serral Asensio, Yoo, Akoglu. "End-To-End Self-Tuning Self-Supervised Time Series Anomaly Detection" (TSAP). SDM 2025. doi:10.1137/1.9781611978520.61 | 학회, A | [열람] arXiv | 라벨 없는 **시험 데이터**로 증강을 튜닝(전이적). 우리 경우 실제 이상 1건을 엿보는 셈 | 코드 MIT(GitHub API) | 중간: 실제 이상에 쓰면 누설 |
| S12 | Wu, Keogh. "Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress." IEEE TKDE (early access 2021). doi:10.1109/TKDE.2021.3112126 (확장초록 ICDE 2022 pp.1479–1480) | 학술지, A | [열람] arXiv 본문(4대 결함, one-liner, "Synthetic, but Highly Plausible Anomalies", 불변성 논의) | 비판 논문. 저자가 대안 아카이브(UCR) 제안자 | — | 낮음 |
| S13 | Kim, Choi, Choi, Lee, Yoon. "Towards a Rigorous Evaluation of Time-Series Anomaly Detection." AAAI 2022, 36(7):7194–7201. doi:10.1609/aaai.v36i7.20680 | 학회, A | [열람] arXiv 초록·본문 | — | — | 낮음 |
| S14 | Paparrizos, Kang, Boniol, Tsay, Palpanas, Franklin. "TSB-UAD: An End-to-End Benchmark Suite for Univariate Time-Series Anomaly Detection." PVLDB 15:1697–1711, 2022. doi:10.14778/3529337.3529354 | 학술지, A | [열람] PDF(전역·국소 변환 목록) | 변환형 인공 이상 | 코드 Apache-2.0. 논문 CC BY-NC-ND 4.0 | 낮음 |
| S15 | Ma, Zhao, Zhang, Akoglu. "The Need for Unsupervised Outlier Model Selection: A Review and Evaluation of Internal Evaluation Strategies." ACM SIGKDD Explorations 25(1), 2023. doi:10.1145/3606274.3606277 (arXiv:2104.01422, 제목 상이) | 학술지, A | [열람] arXiv 초록. [검색만] 출판본 | **표 형식** 이상탐지 대상 | — | 낮음 |
| S16 | Smolyakov, Sviridenko, Ishimtsev, Burikov, Burnaev. "Learning Ensembles of Anomaly Detectors on Synthetic Data." ISNN 2019. arXiv:1905.07892 | 학회(LNCS), B | [열람] arXiv 초록 | 기상 도로정보 응용 한정 | — | 중간 |
| S17 | Lavin, Ahmad. "Evaluating Real-Time Anomaly Detection Algorithms – the Numenta Anomaly Benchmark." IEEE ICMLA 2015, pp. 38–44. doi:10.1109/ICMLA.2015.141 | 학회, A(이해상충 주의) | [열람] 초록(OpenAlex) | 저자가 Numenta 소속(벤치마크 제작사). NAB 데이터는 [S12]가 비판 | — | 중간: '조기 탐지 보상' 개념만 인용 |

### 2-B. 증강·생성모델·대리(surrogate) 데이터

| # | 인용 | 유형·등급 | 검증 | 위험 신호 | 라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S18 | Wen, Sun, Yang, Song, Gao, Wang, Xu. "Time Series Data Augmentation for Deep Learning: A Survey." IJCAI 2021, pp. 4653–4660. doi:10.24963/ijcai.2021/631 | 서베이, A | [열람] arXiv 본문 + IJCAI 페이지 | — | — | 낮음 |
| S19 | Iwana, Uchida. "An empirical survey of data augmentation for time series classification with neural networks." PLOS ONE 16:e0254841, 2021. doi:10.1371/journal.pone.0254841 | 학술지, A | [열람] PLOS 페이지 + arXiv 본문 | **분류** 과제 대상 | CC BY 4.0. 코드 Apache-2.0 | 낮음. 그림도 출처 표기 시 재사용 가능 |
| S20 | Iglesias, Talavera, González-Prieto, Mozo, Gómez-Canaval. "Data Augmentation techniques in time series domain: a survey and taxonomy." Neural Computing and Applications 35:10123–10145, 2023. doi:10.1007/s00521-023-08459-3 | 서베이, A | [열람] arXiv 본문. [미검증] 출판사 라이선스(Springer 페이지 접근 실패) | — | 미확인 | 인용만 |
| S21 | Um, Pfister, Pichler, Endo, Lang, Hirche, Fietzek, Kulić. "Data Augmentation of Wearable Sensor Data for Parkinson's Disease Monitoring using Convolutional Neural Networks." ICMI 2017. doi:10.1145/3136755.3136817 | 학회, A | [열람] arXiv 본문 | 웨어러블 영역 | — | 낮음 |
| S22 | Yoon, Jarrett, van der Schaar. "Time-series Generative Adversarial Networks." NeurIPS 2019. https://papers.nips.cc/paper/2019/hash/c9efe5f26cd17ba6216bbe2a7d26d490-Abstract.html | 학회, A | [열람] 초록 페이지. 코드 저장소 README·license 파일 | 코드 license 파일은 Apache-2.0 헤더 형태라 GitHub이 "NOASSERTION"으로 표시 | Apache-2.0(비표준 표기) | 코드 동봉 시 라이선스 문구 확인 |
| S23 | Yuan, Qiao. "Diffusion-TS: Interpretable Diffusion for General Time Series Generation." ICLR 2024. arXiv:2403.01742 | 학회, A | [열람] arXiv 본문(지표·한계) | 추론 비용 큼(저자 명시) | 코드 MIT | 낮음 |
| S24 | Tashiro, Song, Song, Ermon. "CSDI: Conditional Score-based Diffusion Models for Probabilistic Time Series Imputation." NeurIPS 2021. arXiv:2107.03502 | 학회, A | [검색만] 본문 세부 미확인(arXiv 메타데이터) | — | 코드 MIT | 인용만 |
| S25 | Esteban, Hyland, Rätsch. "Real-valued (Medical) Time Series Generation with Recurrent Conditional GANs." arXiv:1706.02633, 2017 | 프리프린트, B | [검색만] + arXiv 표지 | TSTR/TRTS 개념의 출처 | — | 낮음 |
| S26 | Ang, Huang, Bao, Tung, Huang. "TSGBench: Time Series Generation Benchmark." PVLDB 17:305–318, 2023. doi:10.14778/3632093.3632097 | 학술지, A | [열람] arXiv 본문 | — | — | 낮음 |
| S27 | Stenger, Leppich, Foster, Kounev, Bauer. "Evaluation is key: a survey on evaluation measures for synthetic time series." Journal of Big Data 11:66, 2024. doi:10.1186/s40537-024-00924-7 | 서베이, A | [열람] 초록(OpenAlex) | — | CC BY | 낮음 |
| S28 | Somepalli, Singla, Goldblum, Geiping, Goldstein. "Diffusion Art or Digital Forgery? Investigating Data Replication in Diffusion Models." CVPR 2023, pp. 6048–6058. doi:10.1109/CVPR52729.2023.00586 | 학회, A | [열람] arXiv 본문 | **이미지** 영역(유추 적용) | — | 영역 차이 명시 |
| S29 | Theiler, Eubank, Longtin, Galdrikian, Farmer. "Testing for nonlinearity in time series: the method of surrogate data." Physica D 58:77–94, 1992. doi:10.1016/0167-2789(92)90102-S | 학술지, A | [검색만] Crossref | — | — | 낮음 |
| S30 | Schreiber, Schmitz. "Improved Surrogate Data for Nonlinearity Tests" (IAAFT). Phys. Rev. Lett. 77:635–638, 1996. doi:10.1103/PhysRevLett.77.635 | 학술지, A | [검색만] Crossref. IAAFT 성질은 [S18]에서 [열람] | — | — | 낮음 |
| S31 | Politis, Romano. "The Stationary Bootstrap." JASA 89:1303–1313, 1994. doi:10.1080/01621459.1994.10476870 | 학술지, A | [검색만] Crossref | — | — | 낮음 |

### 2-C. 물리 기반 시뮬레이션·유압펌프/전동기 지식·공개 고장 데이터·sim-to-real

| # | 인용 | 유형·등급 | 검증 | 위험 신호 | 라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S32 | KAMP/스마트제조혁신추진단·InterX, 「소성가공 예지보전 AI 데이터셋」 분석실습 가이드북(2022) | 데이터 공식 문서, B | [열람] 로컬 텍스트(scratchpad/task/guidebook.txt) | 펌프 형식은 "기어형 예시"일 뿐 확정 아님. 그림은 네이버 출처(제3자) | KAMP 이용조건 | 그림 재사용 금지, 문장 인용은 출처 표기 |
| S33 | MathWorks. "Multi-Class Fault Detection Using Simulated Data" (Predictive Maintenance Toolbox 예제, 삼중 펌프). https://www.mathworks.com/help/predmaint/ug/multi-class-fault-detection-using-simulated-data.html | 제조사 기술문서, B | [열람] WebFetch 요약으로 확인 | 상용 툴 필요. 우리 펌프와 모델이 다름 | MathWorks 라이선스(모델 재배포 불가) | 높음: zip 재현성 불가. 개념만 인용 |
| S34 | MathWorks. "Fixed-Displacement Pump (IL)" Simscape Fluids 블록 문서. https://www.mathworks.com/help/hydro/ref/fixeddisplacementpumpil.html | 제조사 기술문서, B | [열람] WebFetch(누설·마찰 식, faults 항목) | 상용 | 위와 같음 | 식(모델 형태)만 인용 |
| S35 | Paredis et al. OpenHydraulics Modelica library v2.0.0 (2022-10-14). https://github.com/modelica-3rdparty/OpenHydraulics | 오픈소스 모델, B | [열람] LICENSE, ConstantDisplacementPump.mo 원문 | 검증 수준 미상(학술 라이브러리) | BSD-3-Clause | 낮음. 식을 Python으로 옮기면 됨 |
| S36 | Modelica Standard Library LICENSE(BSD-3-Clause), OpenModelica OSMC-License(AGPL v3 또는 OSMC-PL 1.8 택일) | 라이선스 문서 | [열람] raw LICENSE 파일 | OpenModelica는 AGPL 선택지 | MSL BSD-3. OM AGPL/OSMC-PL | OM 바이너리는 zip에 넣지 말 것 |
| S37 | Vacca, Guidetti. "Modelling and experimental validation of external spur gear machines for fluid power applications." Simulation Modelling Practice and Theory 19:2007–2031, 2011. doi:10.1016/j.simpat.2011.05.009 | 학술지, A | [검색만] Crossref(본문 미열람) | — | Elsevier | 인용만 |
| S38 | Frith, Scott. "Wear in external gear pumps: a simplified model." Wear 172:121–126, 1994. doi:10.1016/0043-1648(94)90279-8. 및 "Comparison of an external gear pump wear model with test data." Wear 196:64–71, 1996. doi:10.1016/0043-1648(95)06845-7 | 학술지, A | [검색만] Crossref | — | Elsevier | 인용만 |
| S39 | Szwemin, Fiebig. "The Influence of Radial and Axial Gaps on Volumetric Efficiency of External Gear Pumps." Energies 14:4468, 2021. doi:10.3390/en14154468 | 학술지(MDPI), A | [열람] 초록(OpenAlex) | MDPI는 논문별 품질 편차 큼 | CC BY 4.0 | 낮음 |
| S40 | Yang, Jang, Ji. "Volumetric Efficiency Prediction of External Gear Pumps Using a Leakage Model Based on Dynamic Clearances." Actuators 15(1):56, 2026. doi:10.3390/act15010056 | 학술지(MDPI), A | [열람] 초록(OpenAlex) | 위와 같음 | CC BY 4.0 | 낮음 |
| S41 | Yang, Ding, Xiao, Fang, Li. "Current Status and Applications for Hydraulic Pump Fault Diagnosis: A Review." Sensors 22:9714, 2022. doi:10.3390/s22249714 | 리뷰(MDPI), A | [열람] 전문(Europe PMC PMC9788536) | 전류 기반 진단은 거의 다루지 않음(본문에 'motor current' 0회) | CC BY 4.0 | 낮음 |
| S42 | Helwig, Pignanelli, Schütze. "Condition Monitoring of a Complex Hydraulic System Using Multivariate Statistics." IEEE I2MTC 2015. doi:10.1109/I2MTC.2015.7151267 | 학회, A | [검색만] (Zenodo/UCI 설명에 인용됨) | 유료 | IEEE | 인용만 |
| S43 | Helwig, Pignanelli, Schütze. "Detecting and Compensating Sensor Faults in a Hydraulic Condition Monitoring System." SENSOR 2015, D8.1. doi:10.5162/sensor2015/D8.1 | 학회, A- | [열람] AMA PDF(폰트 인코딩을 복원해 판독) | 2단 편집이라 문장 재구성 필요 | AMA 공개 | 낮음 |
| S44 | Helwig, Klein, Schütze. "Identification and Quantification of Hydraulic System Faults Based on Multivariate Statistics Using Spectral Vibration Features." Procedia Engineering 120:1225–1228, 2015. doi:10.1016/j.proeng.2015.08.835 | 학회 논문집, A | [검색만] Crossref(본문은 403) | — | CC BY-NC-ND 4.0 | 인용만 |
| S45 | ZeMA "Condition monitoring of hydraulic systems" 데이터셋: UCI doi:10.24432/C5CW21, Zenodo doi:10.5281/zenodo.1323611 (Helwig, Pignanelli, Schütze; Schneider, Klein, Bastuck) | 공개 연구 데이터, A | [열람] UCI·Zenodo 페이지·documentation.txt. 데이터를 내려받아 **우리 계산** | 고장은 오리피스 모사(seeded). 진동은 1 Hz 속도값. 우리 설비와 다름 | **CC BY 4.0**(재배포 가능, 저작자 표시) | 외부데이터 사용 고지 필요(이유·방법·출처) |
| S46 | Blödt, Granjon, Raison, Rostaing. "Models for Bearing Damage Detection in Induction Motors Using Stator Current Monitoring." IEEE TIE 55:1813–1822, 2008. doi:10.1109/TIE.2008.917108 | 학술지, A | [열람] 초록(OpenAlex). HAL 전문은 봇 차단 | — | IEEE | 인용만 |
| S47 | Kia, Henao, Capolino. "Gear Tooth Surface Damage Fault Detection Using Induction Machine Stator Current Space Vector Analysis." IEEE TIE 62:1866–1878, 2015. doi:10.1109/TIE.2014.2360068 | 학술지, A | [열람] 초록 | 250 W 소형 실험 | IEEE | 인용만 |
| S48 | Thomson, Fenger. "Current Signature Analysis to Detect Induction Motor Faults." IEEE Industry Applications Magazine 7:26–34, 2001. doi:10.1109/2943.930988 | 학술지(실무), A | [열람] 초록 | — | IEEE | 인용만 |
| S49 | U.S. DOE Motor Challenge. "Determining Electric Motor Load and Efficiency." Fact sheet DOE/GO-10097-517 (c. 1997). https://www.energy.gov/sites/prod/files/2014/04/f15/10097517.pdf | 정부 기술자료, A | [열람] PDF 본문 | 오래된 자료(원리는 유효) | 미국 정부 저작물(공공 이용 가능, 미확정) | 낮음 |
| S50 | Lessmeier, Kimotho, Zimmer, Sextro. "Condition Monitoring of Bearing Damage in Electromechanical Drive Systems by Using Motor Current Signals of Electric Motors: A Benchmark Data Set for Data-Driven Classification." PHM Society European Conference 3(1), 2016. doi:10.36001/phme.2016.v3i1.1577 | 학회, A- | [열람] PDF 본문(7.2절·결론) | 베어링·전류 영역 | CC BY 3.0 US | 낮음 |
| S51 | Sobie, Freitas, Nicolai. "Simulation-driven machine learning: Bearing fault classification." MSSP 99:403–419, 2018. doi:10.1016/j.ymssp.2017.06.025 | 학술지, A | [검색만] Crossref(초록은 출판사 비공개) | 저자 소속 Siemens(시뮬레이션 SW 업체), 이해상충 가능 | Elsevier | 인용만 |
| S52 | Sobie, Freitas. "Bearing Race Faults Classification using Simulation-generated Training Data and Feature Free Methods." PHM Society Asia-Pacific 2017. doi:10.36001/phmap.2017.v1i1.1778 | 학회, B | [열람] 학회 페이지(요약) | 위와 같은 이해상충 | PHM Society | 낮음 |

### 2-D. POD(검출확률)·검출지연·임계값·신뢰성 있는 보고

| # | 인용 | 유형·등급 | 검증 | 위험 신호 | 라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| S53 | U.S. DoD. MIL-HDBK-1823A, "Nondestructive Evaluation System Reliability Assessment," 7 April 2009 | 정부 핸드북, A | [열람] PDF(배포문 A, 6.3·6.4절, 부록 G·H 목차와 본문) | NDE 균열 검출용(유추 적용) | Distribution Statement A(공개, 무제한) | 낮음. 인용·도식 차용 가능 |
| S54 | Forsyth. "Structural health monitoring and probability of detection estimation." AIP Conf. Proc. 1706:200004, 2016. doi:10.1063/1.4940648 | 학회, A- | [열람] 초록 | — | AIP | 인용만 |
| S55 | Rébillat, Hmad, Kadri, Mechbal. "Peaks Over Threshold–based detector design for structural health monitoring: Application to aerospace structures." Structural Health Monitoring 17:91–107, 2017. doi:10.1177/1475921716685039 | 학술지, A | [열람] 초록 | — | SAGE | 인용만 |
| S56 | Page. "Continuous Inspection Schemes." Biometrika 41(1–2):100–115, 1954. doi:10.1093/biomet/41.1-2.100 | 학술지, A | [검색만] Crossref | — | — | 낮음 |
| S57 | Basseville, Nikiforov. *Detection of Abrupt Changes: Theory and Application.* Prentice-Hall, 1993(저자 사이트 무료 PDF) https://people.irisa.fr/Michele.Basseville/kniga/ | 학술서, A | [열람] 저자 페이지 | — | 저자 공개(개인 이용) | 낮음 |
| S58 | Bates, Candès, Lei, Romano, Sesia. "Testing for outliers with conformal p-values." Annals of Statistics 51, 2023. doi:10.1214/22-AOS2244 | 학술지, A | [열람] 초록 | i.i.d./교환가능성 가정. 시계열 의존성과 충돌 | — | 낮음 |
| S59 | Hanley, Lippman-Hand. "If Nothing Goes Wrong, Is Everything All Right?" JAMA 249:1743, 1983. doi:10.1001/jama.1983.03330370053031 | 학술지, A | [검색만] Crossref | — | — | 낮음 |
| S60 | ISO 20816-1:2016, *Mechanical vibration — Measurement and evaluation of machine vibration — Part 1: General guidelines* | 국제표준, A | [열람] ISO 카탈로그 초록 | 유료. 개정판(ISO/FDIS 20816-1) 예정 | 유료 저작물 | 조항 번호만 인용. 표·수치 전재 금지 |
| S61 | ISO 17359:2018, *Condition monitoring and diagnostics of machines — General guidelines* | 국제표준, A | [열람] 카탈로그 초록 | 유료 | 유료 | 위와 같음 |
| S62 | Nosek, Ebersole, DeHaven, Mellor. "The preregistration revolution." PNAS 115:2600–2606, 2018. doi:10.1073/pnas.1708274114 | 학술지, A | [검색만] Crossref | — | — | 낮음 |
| S63 | Kapoor, Narayanan. "Leakage and the reproducibility crisis in machine-learning-based science." Patterns 4:100804, 2023. doi:10.1016/j.patter.2023.100804 | 학술지, A | [열람] 초록 | — | CC BY 4.0 | 낮음 |
| S64 | Kapoor et al. "REFORMS: Consensus-based Recommendations for Machine-learning-based Science." Science Advances 10, 2024. doi:10.1126/sciadv.adk3452 | 학술지, A | [열람] 초록 | — | CC BY-NC | 낮음 |
| S65 | NASA. NASA-STD-7009B, *Standard for Models and Simulations*, 2024-03-05. https://standards.nasa.gov/standard/NASA/NASA-STD-7009 | 정부 표준, A | [열람] PDF | 우주 분야용(개념 차용) | 공개 | 낮음 |
| S66 | Chen, Kuo, Liu, Poon, Towey, Tse, Zhou. "Metamorphic Testing: A Review of Challenges and Opportunities." ACM Computing Surveys 51:1–27, 2018. doi:10.1145/3143561 | 서베이, A | [열람] 초록 | SW 테스트 분야(개념 차용) | ACM | 낮음 |
| S67 | Shannon. "Communication in the Presence of Noise." Proceedings of the IRE 37:10–21, 1949. doi:10.1109/JRPROC.1949.232969 | 학술지, A | [검색만] Crossref | — | IEEE | 낮음(표본화·에일리어싱 원리의 고전 출처) |

### 2-E. 코드·도구 라이선스 요약(제출 zip 관점)

| 도구 | 라이선스 | 확인 방법 | zip 동봉 |
|---|---|---|---|
| TODS(Lai 벤치마크 코드) | Apache-2.0 | GitHub API | 가능(고지) |
| tsad-model-selection(Goswami) | Apache-2.0 | GitHub API | 가능 |
| GutenTAG / TimeEval | MIT / MIT | GitHub API + LICENSE | 가능 |
| TSB-UAD | Apache-2.0 | GitHub API | 가능 |
| tsaug | Apache-2.0 | GitHub API | 가능 |
| uchidalab/time_series_augmentation(Iwana) | Apache-2.0 | GitHub API | 가능 |
| TSA-on-autoPilot(TSAP) | MIT | GitHub API | 가능 |
| Diffusion-TS / CSDI | MIT / MIT | GitHub API | 가능 |
| TimeGAN | license 파일에 Apache-2.0 헤더(GitHub 판정 NOASSERTION) | raw 파일 열람 | 주의 |
| OpenHydraulics / Modelica Standard Library | BSD-3 / BSD-3 | raw LICENSE | 가능 |
| OpenModelica | AGPL v3 또는 OSMC-PL 1.8 | raw 라이선스 | 동봉 비권장 |
| MATLAB/Simscape 예제 | MathWorks 상용 | 문서 | 불가 |

---

## 3. 세부 내용과 우리 계획에 쓰는 법

### 3.0 주입 설계의 출발점: 정상 데이터에서 확인한 물리 구조(우리 계산, 정상 파일만)

스크립트: `r5_work/eda_r5.py`, `eda_r5b.py`. 수치는 길이 30 이상인 버스트(599개 중 360개) 기준이다.

- **수집 구조**: 76.9분에 버스트 599개(시간당 약 467개)다. 버스트 내부 간격은 0.1 s다. 버스트 사이 간격은 1.5–16.6 s이고 중앙값은 4.2 s다.
- **전류(AI2)**
  - 버스트마다 **단일 정현파**다. 적합 주파수는 0.594–0.607 Hz(중앙값 0.600)이고 R²는 0.9943–0.9994다. 버스트 내 lag-1 자기상관은 0.93이다.
  - 60 Hz 전류의 에일리어스로 보이며, 에일리어스 주파수는 77분 내내 거의 고정이다.
  - 진폭(√2·표준편차)은 **공회전 중앙값 121.4, 부하 중앙값 233.4**의 두 덩어리다. 부하 버스트 비율은 약 35%이고, 상태는 1–5개 버스트마다 바뀐다(프레스 행정 주기로 추정).
  - **10분 창별 부하 버스트 비율**: 0.43, 0.35, 0.45, 0.40, 0.48, 0.40, **0.00**, 0.24. 60–70분 구간은 부하가 전혀 없는 공회전 구간이다. 정상 파일 안에 이미 '정상 운전변화'의 자연 실험이 들어 있다.
  - 첫 25% 대비 마지막 25% 구간의 진폭 중앙값은 159 → 121로, 운전 혼합이 표류한다.
- **진동(AI0 상부, AI1 하부)**
  - 버스트 RMS 중앙값은 0.069(상부)와 0.089(하부)다.
  - 버스트 내 lag-1 자기상관은 상부 −0.03, 하부 0.26으로 백색잡음에 가깝다.
  - 그래도 에일리어스 협대역 선이 있다. 주성분은 상부 1.4–3.6 Hz, 하부 1.8/3.6 Hz다.
- **부하–진동 결합**
  - log RMS(진동)을 log 진폭(전류)에 회귀하면 하부는 기울기 1.73–1.85, r = 0.96이고 상부는 0.60–0.83, r = 0.71이다.
  - 부하조건부 잔차의 표준편차는 하부 0.15–0.17, 상부 0.21–0.25다(로그 단위).
  - 잔차는 거의 정규분포다(Shapiro p 0.25–0.36). 버스트 간 lag-1 자기상관은 0.25–0.28인데 lag-5는 0.33–0.42로 오히려 크다. 느린 표류가 있다는 뜻이다.
- **의미**:
  1. 진동 '절대 크기'로 이상을 판단하면 부하 변화가 곧 오경보가 된다. 부하조건부 잔차가 기본 특징이어야 한다.
  2. 전류의 정보는 대부분 **진폭(부하 상태)**에 있다. 파형 위상과 에일리어스 주파수는 수집 시계·전원에 좌우되는 교란일 가능성이 크다(3.2·3.6의 N5).
  3. 버스트 간 의존성이 있어서 창 평균의 이득이 독립 가정보다 작다.

### 3.1 TSAD의 합성 이상 주입: 택소노미·쓰임새·함정

**택소노미(무엇을 주입하나)**
- Lai et al. [S1]: 기존의 점/맥락/집합 분류가 모호하다고 보고 **행동 기반 택소노미**를 제안했다. 점(point) 이상은 global과 contextual, 패턴(pattern) 이상은 shapelet, seasonal, trend로 나눈다. 합성 기준도 식으로 줬다. global은 x_t = µ(X) ± λσ(X)이고, contextual은 국소창의 µ, σ를 쓴다. 패턴 이상은 구조식 X = ρ(2πωT) + τ(T)의 한 성분을 바꿔 만든다. 이 기준으로 35개 합성 데이터셋을 만들었고, "classical algorithms could outperform many recent deep learning approaches"라는 결과를 얻었다. **주의**: 실데이터 표는 오염비율 6개 중 최고 결과를 보고했다.
- GutenTAG [S3]
  - 이상 종류: amplitude, extremum, frequency, mean, pattern, pattern-shift, platform, trend, variance, mode-correlation.
  - amplitude·mean·variance는 **creeping**(선형으로 서서히 진입)을 지원한다. 조기탐지용 램프 주입과 같은 개념이다.
  - **custom-input**(CSV를 기본신호로 사용)도 지원한다.
  - Schmidl et al. [S2]은 하이퍼파라미터를 GutenTAG 합성 데이터의 평균 AUC-ROC로 튜닝한 뒤 976개 데이터셋 평가 전체에 썼다. "합성으로 고르고 실데이터로 평가"한 대규모 선례다.
- TSB-UAD [S14]: 정상 시계열에 변환을 걸어 이상을 만든다.
  - 전역 변환: random-walk 배경, 점 이상치, 평활, 백색잡음.
  - 국소 변환: 평탄구간 삽입, 한 주기 재스케일, 한 주기 잡음, 한 주기 뒤집기, tanh 정규화, 과표집.
- Goswami et al. [S4]의 9종: spikes, contextual, flip, speedup(주파수 ×½ 또는 ×2), noise, cutoff, average(이동평균), scale, wander(선형 기준선 이동). 자기상관으로 주기를 추정해 주기 시작점에 주입한다.
- CARLA [S9]: Global, Contextual(3–5σ), Seasonal(주파수계수 {1/3, 1/2, 2, 3}), Trend(+3–5σ), Shapelet(상수).
- AnomalyBERT [S7]: soft replacement, uniform replacement, length adjustment, peak noise.
- COUTA [S8]: 점·맥락·집합 정의에 맞춘 6개 교란 연산으로 "native anomaly"를 만든다.
- NCAD [S5]: Contextual Outlier Exposure(창 일부를 다른 시계열로 교체), IQR 비례 점 스파이크, window mixup.
- SR-CNN [S6]: x = (x̄ + mean)(1 + var)·r + x (r ~ N(0,1)) 형태의 점 주입으로 6,500만 점을 만들어 CNN을 학습했다.

**쓰임새 1: 학습(자기지도·outlier exposure)** — [S5][S6][S7][S8][S9]. 대부분 크기가 크고(3–5σ 수준) 일반적인 이상이다. NCAD는 SMAP의 완만한 기울기 이상에는 일반 주입이 약했고, 기울기 주입을 따로 설계하자 크게 좋아졌다고 보고했다. 즉 **도메인 맞춤 주입**이 효과적이다. 다만 사전지식이 필요하다는 점을 저자들도 한계로 적었다.

**쓰임새 2: 모델·임계값 선택(라벨 없이)**
- Goswami [S4]: 대리지표는 예측오차, 중심성, 주입 이상 성능 세 계열이다. "We found synthetic anomaly injection to perform better than prediction error and centrality metrics". 예비 평가에서 scale, noise, cutoff, contextual, speedup 주입 지표가 대체로 우수했다. 여러 지표를 robust rank aggregation(robust Borda, MIM)으로 합치면 부분 라벨 선택과 비슷한 성능을 냈다.
- Goswami의 자체 경고: "Model selection based on anomaly injection might not be perfect because (i) real anomalies might be of a different type compared to injected ones, and (ii) there may already be anomalies for which our pseudo-labels will be negative." 또 "Prior knowledge of anomalies might help identify good anomaly injection metrics."라고 적었다.
- Smolyakov et al. [S16]: 인공 이상으로 앙상블 임계값을 적응적으로 골랐다.

**함정과 반론**
- **순환성·정렬 문제**
  - Yoo et al. [S10]: 3개 탐지기, 420개 과제(이미지)에서 "the alignment between data augmentation and anomaly-generating mechanism is the key ... and in the lack thereof, SSL may even impair accuracy".
  - TSAP [S11]: 시계열에서 이 정렬을 자동화하려고 라벨 없는 **시험 데이터**를 쓴다. 우리 경우 그 시험 데이터가 실제 이상 1건이므로, 쓰면 곧 누설이다.
  - COUTA [S8]는 반대로 겹치지 않아도 도움이 된다고 주장한다. 증거는 엇갈린다.
- **비현실성·쉬움**
  - Wu & Keogh [S12]: 기존 벤치마크의 4대 결함은 triviality(one-liner로 풀림), unrealistic anomaly density, mislabeled ground truth, run-to-failure bias다.
  - 같은 논문은 "Synthetic, but Highly Plausible Anomalies" 절에서, 현실적으로 그럴듯하게 만든 단일 주입은 쓸 만하다고 본다.
  - 또 알고리즘을 **불변성(invariances: amplitude scaling, offset, noise, warping…)**으로 설명하라고 권한다. 우리 '정상 운전변화 시험'의 이론적 뿌리다.
- **과대평가**
  - Point adjustment(PA)는 성능을 크게 부풀린다. "even a random anomaly score can easily turn into a state-of-the-art TAD method"(Kim [S13]). CARLA [S9]는 PA를 쓰지 않았다.
  - NCAD는 시험셋 최적 임계값으로 F1을 계산했고, Lai의 실데이터 결과도 최고값 보고라 낙관적이다.
- **라벨 없는 선택의 한계**: Ma et al. [S15](표 형식 데이터): 7개 내부 전략, 39개 과제, 297개 모델에서 "none would be practically useful". 주입 기반 선택만 믿어서는 안 되고, 가족별 결과의 안정성을 직접 보여야 한다.

**우리 계획에 쓰는 법**
- 주입 '가족'은 TSAD 택소노미를 그대로 쓰지 말고 **펌프·전동기 메커니즘에 맞춰 정의**한다(3.6). TSAD 용어(variance, amplitude, frequency, trend, extremum, mode-correlation)는 보고서에서 대응표로만 쓴다. 예: 우리 F1 = GutenTAG variance/amplitude, F2 = extremum, F3 = frequency/pattern, F8 = creeping.
- 크기는 TSAD 관행(3–5σ)보다 **훨씬 작은 구간(×1.1–×3)**에 촘촘히 둔다. 조기탐지가 목적이기 때문이다.
- PA 금지. 시험셋에서 임계값을 고르는 것도 금지다.
- 모델선택에 Goswami식 순위 결합을 쓰되 **leave-one-family-out 안정성**을 함께 보고한다.
- 자기지도 주입으로 학습하는 모델(예: NCAD식)은 **학습에 쓴 가족과 평가 가족을 분리**한다. 학습에 F1·F2를 썼다면 평가는 F3·F5·F8로 한다.

### 3.2 물리 기반 고장 시뮬레이션: 유압펌프·기어·유도전동기

**(a) 집중정수(lumped-parameter) 손실 모델 — 모델 형태는 공개 문서로 확인**
- OpenHydraulics(BSD-3) `ConstantDisplacementPump`: 누설 q_leak = C_s·Δp·D/μ + (압축성 항), 기계손실은 점성항력 계수 C_v와 쿨롱마찰 계수 C_f(정격 토크 대비 비율)다 [S35]. Wilson형 손실 모델이다.
- Simscape Fluids Fixed-Displacement Pump(IL) [S34]
  - 누설: ṁ_leak = K·ρ·Δp. K는 명목 체적효율 η_v,nom에서 K = D·ω_nom·(1−η_v,nom)/Δp_nom으로 정한다(Hagen–Poiseuille).
  - 마찰토크: τ_fr = (τ_0 + k|Δp|)·tanh(...).
  - 고장 인터페이스: displacement fault, leakage fault(누설을 "faulted leakage factor"만큼 키움, 기본값 2.0으로 요약됨), shaft friction torque fault.
- 기어펌프 상세 모델과 마모
  - 외접기어 기계의 집중정수 모델과 실험 검증(Vacca & Guidetti [S37]).
  - 마모 모델(Frith & Scott [S38]).
  - 축·반경 틈새가 체적효율에 미치는 CFD·실험(Szwemin & Fiebig [S39]).
  - 압력에 따른 동적 틈새와 마모를 넣은 체적효율 예측(Yang, Jang, Ji [S40]): 명목 정적 틈새 모델 오차 9.43% → 동적 틈새 모델 1.98%.
- 이 식들이 말하는 것:
  1. **마모로 틈새 h가 커지면 누설은 h³에 비례해 늘지만(층류 틈새류), 축토크는 직접 거의 변하지 않는다.** 토크는 D·Δp + 마찰이다. 같은 압력을 유지하면 전류가 거의 안 변한다.
  2. **마찰 증가(베어링·치면 손상, 오염)는 토크를 늘리고**, 부하 상태 전류를 키운다.
  3. **오일 온도가 오르면 μ가 떨어진다.** 누설은 늘고 점성 토크는 준다. 마모와 같은 방향의 누설 증가와 반대 방향의 전류 변화가 섞인다.
- 가이드북 [S32]: "펌프 내부의 기어 마모 → 진동과 소음이 심해지며 출력 유압이 약해져"
- 펌프 리뷰 [S41]: "when the hydraulic pump is gradually worn and damaged ... increased noise, increased vibration, and decreased flow"
- 두 문서 모두 **진동 증가 + 유량·압력 저하**를 주 증상으로 든다. 전류는 언급이 거의 없다(리뷰 본문 'motor current' 0회).

**(b) 전류로 가는 사상(induction motor)**
- DOE [S49]: "The amperage draw of a motor varies approximately linearly with respect to load, down to about 50% of full load. ... Below the 50% load point, due to reactive magnetizing current requirements ... the amperage curve becomes increasingly non-linear. In the low load region, current measurements are not a useful indicator of load." 또 "RMS current measurements should always be corrected for voltage"라고 했다.
  - 우리 데이터의 공회전 진폭(약 121)은 부하 진폭(약 233)의 약 52%로, 자화전류가 지배하는 영역으로 보인다.
  - 따라서 마찰형 고장 주입은 **부하 버스트 전류에는 비례로, 공회전 버스트에는 미미하게** 넣어야 물리적으로 맞다.
  - 전원전압 변화는 전류를 바꾸는 교란(nuisance)이다.
- MCSA
  - 베어링 결함은 **부하토크 변동**을 일으켜 고정자 전류 주파수 성분을 만든다(Blödt [S46]).
  - 치면 손상은 충격과 감쇠 진동 형태의 토크 진동을 만들고, 이것이 전류의 고장 관련 주파수로 나타난다(Kia [S47]).
  - 우리 10 Hz 에일리어스 영역에서는 이런 토크 변동이 **전류 포락선(진폭)의 변조**나 버스트 간 진폭 요동으로 보일 것으로 추정된다. 이것은 추정이고 검증되지 않았다.

**(c) 진동(10 Hz 표본)으로 가는 사상**
- 진동 표본이 순간값이고 안티앨리어싱 필터가 없다면, kHz 대역의 기어·베어링 에너지는 0–5 Hz에 접혀 들어와 **분산·첨도·협대역 선**으로 나타난다(표본화 정리 [S67]).
- DAQ가 필터링을 했는지는 알 수 없으므로 **진동 주입은 물리 시뮬레이션 대신 통계 가족(에너지·충격성·톤·결합)으로** 정의하는 것이 정직하다.

**(d) 외부 근거: ZeMA 유압 리그(CC BY 4.0) — 우리 계산**
스크립트 `r5_work/zema_effects.py`. 안정 사이클 1,449개를 쓰고, 냉각기×밸브×축압기 층(stratum) 48개 안에서 누설 수준을 비교했다.

| 비교 | 모터전력 EPS1 평균 | 진동 VS1 평균(1 Hz, mm/s) | 유량 FS1 | 효율 SE |
|---|---|---|---|---|
| 누설 약(정격유량의 3.3%) vs 없음 | **+0.45%** (IQR 0.32–1.93) | +0.95% (IQR −0.47–2.67, 불일치) | −3.1% | −3.6% |
| 누설 심(4.6%) vs 없음 | **+1.05%** (IQR 0.71–4.14) | +1.21% (IQR −0.35–2.93, 불일치) | −4.5% | −5.9% |
| 냉각기 20% vs 100%(오일 +8~9 °C, 누설 0, 밸브 100) | **−2.9 ~ −3.3%** | **+9 ~ +14%** | — | — |
| 냉각기 3% vs 100%(오일 +19~21 °C) | **−3.6 ~ −6.4%** | **+13 ~ +28%** | — | — |

- 유량 감소(−3.1%, −4.5%)는 논문의 누설 크기(정격유량 3.3%, 4.6% [S43])와 거의 같다. 라벨 해석과 계산이 맞다는 교차 확인이다.
- 해석: 층 안의 사이클 간 변동이 매우 작아서 전력 변화의 표준화 효과크기(d ≈ 5–13)는 크다. 그러나 **절대 변화는 1% 안팎**이다. 부하 진폭이 2배 넘게 오가는 우리 데이터에서는 압력 기준 신호 없이는 잡히지 않는다.
- 반면 운전조건(오일 온도) 변화는 전력과 진동을 수 %에서 수십 % 바꾼다.
- 데이터셋 문서도 "Pump and especially Accumulator states are more complex targets"라고 적었다(ZeMA documentation.txt).
- 한계: 냉각기 조건별 셀은 사이클 10–19개로 작다. 진동은 1 Hz 속도값이고, 펌프·모터·센서가 우리와 다르다. 냉각기 조건에는 온도 말고 다른 차이도 섞여 있을 수 있다.

**(e) 도구 선택과 라이선스**
- 상용(MathWorks 삼중 펌프 예제 [S33])
  - 누설 면적 0–0.036(최대 체크밸브 면적 대비), 흡입 막힘 계수 0.8–0.53, 베어링 마찰 0–6×10⁻⁴를 각 10단계로 두고 1,000회 시뮬레이션했다(요약으로 확인).
  - 압력·유량·속도·전류를 기록했고, SVM 정확도 90%, 고장 존재 판별 100%를 보고했다.
  - "**심각도 격자 × 반복 시드**"로 시뮬레이션 앙상블을 만드는 설계는 참고할 만하다. 하지만 MATLAB 라이선스가 필요하고 모델 파일을 재배포할 수 없어 zip 재현성에 맞지 않는다.
- 오픈(OpenHydraulics BSD-3 + MSL BSD-3, OpenModelica AGPL/OSMC-PL [S35][S36])
  - 쓸 수는 있다. 하지만 10 Hz 에일리어싱 진동은 만들 수 없고, 우리 설비 파라미터도 모른다.
  - **권고**: 전체 회로 시뮬레이션은 하지 않는다. 위 손실 모델을 **Python 30줄 정도의 "전류 진폭 사상 함수"**로 옮긴다. 파라미터는 우리 데이터의 공회전·부하 진폭에 맞춘 **상대값**으로 둔다.
  - 보고서에는 모델 형태의 출처로 [S34][S35]를 적고, 운용한계(limits of operation, [S65])를 명시한다.

### 3.3 시계열 증강: 정상 데이터에 안전한 변환 vs 물리를 깨는 변환

**문헌**
- Wen et al. [S18]
  - "the data augmentation methods applicable for time series classification may not be valid for time series anomaly detection"
  - AAFT/IAAFT 대리 데이터는 "can approximately preserve the temporal correlation, power spectra, and the amplitude distribution"
- Iwana & Uchida [S19](128개 데이터셋, 분류)
  - Window Warping이 "the most recommended algorithm"이었다.
  - Rotation·Permutation은 정확도를 떨어뜨렸다.
  - Time warping은 과변형으로 부진했다.
  - "not every transformation is applicable to every dataset". 분산이 작은 데이터셋은 변환에 교란되기 쉽다.
- Um et al. [S21]: "scaling of the acceleration data may change their labels because some labels are differentiated by the intensity of motion"
- Iglesias et al. [S20]: 전통 기법, VAE, GAN을 정리한 택소노미다. TSTR(predictive score)을 "one of the most effective and used evaluation metrics"로 소개한다.

**우리 데이터 전용 판정표**

| 변환 | 판정 | 이유(우리 데이터 근거) |
|---|---|---|
| 버스트 시작 위상 무작위화(전류를 A·sin(2πf t+φ)+잔차로 재합성, φ 무작위) | **안전** | 버스트 시작 시점은 AC 위상과 무관하다. 진폭·주파수가 그대로라 물리가 보존된다 |
| 버스트 단위 (정상) 블록 부트스트랩 [S31] | **안전**(정상 증강·긴 시험 스트림 생성용) | 버스트 내부 구조를 보존한다. 단 원천이 77분이라는 점은 그대로(MIL-HDBK 6.4 경고) |
| 버스트 내 잘라내기(window slicing) | **안전**(특징이 길이에 강건할 때) | 실제로도 길이 4–50인 버스트가 섞여 있다. 길이 강건성 시험(N6)에도 쓴다 |
| 진동 IAAFT 대리 [S29][S30] | **조건부** | 스펙트럼과 진폭분포를 보존한다. 하지만 50표본으로는 제약이 약하고 비선형 구조(충격성)를 지워 FPR을 과소추정할 수 있다. 판별점수(C2ST)로 현실성을 확인한 뒤에만 쓴다 |
| 전류·진동의 공동 스케일(부하 법칙 b 유지, 정상 범위 안) | **조건부 → 교란 시험용**(N2) | 실제 부하 변화의 모사다. 정상 라벨이 유지된다 |
| 진동만 스케일 / 지터(잡음 추가) | **위험 = 고장 주입** | 진동 에너지 증가는 우리의 주 고장 신호다(Um의 경고). 지터는 백색에 가까운 진동에서 곧 분산 증가다 |
| 시간왜곡·창 왜곡(time/window warping) | **위험** | 에일리어스 영역에서 비물리적이다. 실제 축속도가 1% 바뀌면(예: 29.5 → 29.8 Hz) 에일리어스는 0.5 → 0.2 Hz로 −60% 움직인다. 시간왜곡 1%는 0.5 → 0.505 Hz일 뿐이다 |
| 순열(permutation)·버스트 내 셔플 | **위험** | 0.600 Hz 정현파(R² 0.99+)와 진동 에일리어스 선을 파괴한다. [S19]에서도 해로웠다 |
| 믹스업(서로 다른 버스트 볼록결합) | **위험** | 위상이 다른 두 정현파를 섞으면 진폭이 줄어 '가짜 저부하' 상태가 생긴다. 부하 상태를 섞으면 비물리 상태가 된다. NCAD의 window mixup은 다른 데이터에서의 결과다 |
| 주파수영역 위상 교란(APP 등) | **위험** | 전류의 코히어런트 위상을 깬다 |
| 부호 반전(rotation/flip) | 무해하지만 무의미 | 정현파에서는 위상 π 이동과 같다. 진동 분포는 대칭이다 |

**우리 계획에 쓰는 법**: 정상 증강은 꼭 필요할 때만 '안전'과 '조건부(검증 후)' 행만 쓴다. 증강의 주된 목적은 **임계값 보정용 정상 표본 확대**가 아니라 **교란(nuisance) 시험**이어야 한다. 정상 표본을 인위로 늘려도 77분이라는 정보량은 늘지 않기 때문이다.

### 3.4 생성모델(TimeGAN·Diffusion-TS·CSDI)

**문헌**
- 생성 품질 평가지표(TimeGAN [S22], Diffusion-TS [S23])
  - discriminative score: 사후 RNN이 실제와 합성을 구별하는지.
  - predictive score: train-synthesis-test-real(TSTR), 개념은 [S25]에서 왔다.
  - Context-FID, correlational score.
  - Diffusion-TS는 discriminative score를 평균 50% 개선했다고 보고했다. 추론 비용이 높다는 한계도 저자가 적었다.
- TSGBench [S26]
  - 기존 TSG 방법은 "sensitive to dataset sizes. With smaller datasets, they may not converge effectively due to insufficient training data, compromising their reliability"
  - "some tasks, like anomaly detection, require extra data and ground truth, which would complicate the evaluation and surpass the designated scope". 즉 **생성 품질 지표는 이상탐지 유용성을 재지 않는다.**
- Stenger et al. [S27]: 합성 시계열 품질을 어떻게 재야 하는지 합의가 없다.
- Somepalli et al. [S28](이미지): "for small and medium dataset sizes, replication happens frequently"

**판단**
- **이상 600행 1건으로 고장 데이터를 생성하는 것은 사실상 복제다.** 실제 이상을 학습·평가 양쪽에 새는 누설 경로가 되므로 금지한다.
- 정상 데이터용 생성모델도 이점이 불확실하다. 정상 360–599개 버스트의 구조가 이미 단순하다(정현파 전류 + 상태 전이 + 백색에 가까운 진동 + 소수 선스펙트럼). 그래서 **화이트박스 생성기**가 더 투명하고 감사하기 쉽다. 생성기는 버스트별로 다음을 뽑는다.
  1. 상태(공회전/부하; 마르코프 전이는 정상 데이터에서 추정)
  2. 진폭(상태별 분포)
  3. 에일리어스 주파수와 위상
  4. 진동(조건부 RMS 법칙 + 정상 잔차 부트스트랩)
- 그래도 생성모델을 비교군으로 넣고 싶다면, 정상 데이터에만 학습한다. 판별점수(분류기 AUC ≈ 0.5 근처인지)와 TSTR로 현실성을 보고하고, 이상탐지 결과에 쓴다면 "합성 정상으로 늘린 경우와 아닌 경우"를 함께 보고한다.

### 3.5 PHM의 고장 주입·sim-to-real 검증, POD(용량–반응), 검출지연

**sim-to-real 근거와 반론**
- Sobie & Freitas [S52](Sobie et al. [S51]의 학회판): 시뮬레이션 베어링 진동으로 학습한 분류기가 "other machines" 데이터로 학습한 것보다 정확했다. 풍력 터빈 고장을 한 달 넘게 미리 예측했다고도 보고했다. 저자는 시뮬레이션 SW 업체 소속이라 이해상충 가능성이 있다.
- Lessmeier et al. [S50]: 인공 손상(EDM·드릴·전기 조각기)과 가속수명시험의 실제 손상을 비교했다.
  - "Training with data from bearings with artificially induced damages (7.2) and testing with real damages achieve quite low accuracies"
  - "**For a realistic application of classification methods in CM systems the use of training data with artificial damages is apparently not sufficient.**"
  - 물리적으로 만든 인공 고장조차 실제 고장을 대표하지 못한다는 강한 반론이다.
- MathWorks 삼중 펌프 [S33]: 시뮬레이션 앙상블과 심각도 격자의 전형적 예다. 실기 검증은 없다.

**NDE의 POD/MAPOD 틀 (MIL-HDBK-1823A [S53], 배포문 A)**
- 결함 크기 a에 대한 응답 â를 회귀한다(â vs a). 이진 데이터면 hit/miss GLM을 쓴다. 여기서 POD(a)와 신뢰한계를 구하고 **a90/95**를 보고한다. 핸드북은 이를 "a de facto design criterion"이라 부른다.
- 잡음(noise) 분석으로 오경보(false call, PFP)를 함께 다룬다.
- **6.3 Model-Assisted POD**: 실험 비용이 클 때 수학·물리 모델로 POD를 보조한다. 부록 H에 MAPOD 절차가 있다. 용도 정의 → POD 지배 인자 식별 → 일부는 실험으로, 일부는 모델로 평가 → â vs a 모델 구축 순이다.
- **6.4 "Repeated inspections improve POD"는 오해**다. 같은 표본을 여러 번 보면 표본 수가 늘어난 게 아니다. 우리 경우 같은 77분 정상 데이터에 주입을 수천 번 해도 '다른 날·다른 조건'에 대한 불확실성은 줄지 않는다.
- 그림 G-47/48: **서로 다른 데이터를 묶어 만든 '평균' POD 곡선은 어느 것도 대표하지 않는다.** 고장 가족을 섞은 평균 POD를 보고하면 안 된다.
- SHM 쪽 확장
  - 반복 측정에서 유효 POD를 추정하는 이론과 데이터(Forsyth [S54]).
  - 건전 데이터의 꼬리를 EVT/POT로 모델링해 목표 PFA(10⁻⁴–10⁻⁹)에 맞는 임계값을 설계(Rébillat [S55]). Parzen 방식보다 실제 PFA가 목표에 가까웠다.

**검출지연과 성장속도**
- CUSUM(Page [S56])과 변화검출 이론(Basseville & Nikiforov [S57])은 ARL₀(오경보 간 평균 길이)와 지연(ARL₁) 사이의 교환관계를 다룬다.
- 조기탐지는 "**램프 주입의 성장속도 s별 검출지연 분포**"와 "**경보 시점의 고장 크기**"로 보고하는 것이 표준적이다. GutenTAG creeping [S3]이 같은 개념이다.
- NAB [S17]는 이른 탐지를 보상하는 점수를 썼다. 개념만 빌리고 점수 체계는 쓰지 않는다([S12]의 비판 때문).

**우리 정상 데이터의 검출한계(우리 계산, `r5_work/pilot_pod.py`, `pilot_pod_cv.py`)**

① 정규 근사 계산. 부하조건부 log-RMS 잔차를 쓰고, POD 90%에 필요한 RMS 배율을 구했다. 유효 표본은 AR(1) 근사로 보정했다.

| 채널(잔차 σ) | 버스트당 FPR | 단일 버스트 | 5버스트 평균 | 10버스트 평균 |
|---|---|---|---|---|
| 하부 AI1 (0.171) | 1% | ×1.86 | ×1.45 | ×1.30 |
| 하부 AI1 | 1e-5(≈ 주 1회 경보) | ×2.59 | ×1.76 | ×1.49 |
| 상부 AI0 (0.246) | 1% | ×2.43 | ×1.67 | ×1.44 |
| 상부 AI0 | 1e-5 | ×3.91 | ×2.19 | ×1.74 |

lag-5 자기상관이 lag-1보다 커서(느린 표류) AR(1) 보정도 낙관적이다.

② 주입 파일럿. 정상 데이터만 썼고, 시간 순 연속 5-fold다. 임계값은 보정 블록의 99분위수로, 버스트당 1% FPR이다.

| 주입 | 크기 | 조건부 RMS | 첨도 | max(RMS, 첨도), 단일 임계값 |
|---|---|---|---|---|
| 없음(정상) | — | 0.01 (fold 0.00–0.03) | 0.00 | 0.01 |
| 진동 에너지 ×(1+δ), 양 채널 | +20% | 0.17 (0.07–0.28) | 0.01 | 0.01 |
|  | +50% | 0.67 (0.26–0.88) | 0.01 | 0.11 |
|  | +100% | 0.95 (0.75–1.00) | 0.01 | 0.67 |
| 부하 변화(진동은 정상 법칙대로 함께 변함) | ±30% | **0.01**(오경보 증가 없음) | 0.01 | 0.01 |
| 하부 진동에 협대역 톤 추가(진폭비 ρ) | 0.25 / 0.5 / 1.0 | 0.01 / 0.05 / 0.44 | ~0 | 0.01 / 0.01 / 0.05 |
| 충격성 스파이크(표본당 확률 p, 5σ) | 2% / 5% / 10% | 0.26 / 0.60 / 0.87 | **0.75 / 0.95 / 0.96** | 0.75 / 0.95 / 0.98 |

단일 분할 파일럿의 추가 결과는 두 가지다.
- 비조건부 진동 RMS 탐지기는 부하 +20%/+30% 변화에 **오경보율 13%/16%**를 냈다. 조건부 탐지기는 0%였다.
- 진동은 그대로 두고 전류만 +5–30% 바꾼 '마찰형' 주입은 단측 진동잔차 탐지기에 **POD 0**이었다. 사각지대다.

**해석과 계획 반영**
1. 진동 에너지 고장의 현실적 검출한계는 대략 ×1.3–×2.6이다(창 길이·FPR 목표에 따라). 격자를 이 구간에 촘촘히 둔다.
2. **가족마다 맞는 특징이 다르다.** 에너지 증가에는 조건부 RMS, 충격성에는 첨도, 톤에는 스펙트럼/자기상관 특징이 필요하다. 여러 점수를 단일 임계값으로 합치면 각 가족의 민감도가 떨어진다(다중검정 비용: +100% 에너지 POD 0.95 → 0.67). **가족별 POD를 보고**하고, 결합 탐지기는 결합 후 다시 보정해야 한다.
3. 전류만 변하는 고장은 부하 기준 신호(압력·행정)가 없어서 원리적으로 식별하기 어렵다. FN 분석의 핵심 메시지다.
4. fold 간 POD 범위가 넓다(+50%에서 0.26–0.88). 반드시 구간으로 보고한다.
5. **현장 오경보율 문제**: 버스트당 1%는 시간당 약 4.7회 경보다. 현장 목표(예: 주 1회 ≈ 버스트당 1.3×10⁻⁵)는 77분 데이터로 검증할 수 없다. 경보가 0건이어도 95% 상한은 3/599 ≈ 0.5%다 [S59]. EVT 외삽 [S55]이나 conformal 한계 [S58]를 쓰되 가정(정상성·독립성)을 명시한다.

### 3.6 권고안: 사전등록 주입 프로토콜 "R5-INJ v1"

**원칙**
- P1. **증거 위계를 분리한다.**
  - L1: 실제 이상 1건. 최종 1회 시험이며 어떤 선택·임계값에도 쓰지 않는다.
  - L2: 실제 정상 데이터 + 물리 동기 주입(MAPOD형).
  - L3: 외부 공개 리그(ZeMA)의 효과크기. 파라미터 앵커로만 쓴다.
  - L4: 문헌.
- P2. **임계값은 정상 데이터만으로** 목표 FPR에 맞춘다. 주입은 **POD(검출한계), 모델·특징 선택, 교란 강건성**에만 쓴다.
- P3. **격자를 동결**한다. 가족×크기×채널×상태×위치×시드를 YAML로 커밋하고 해시를 남긴 뒤 실행한다. 모든 셀을 보고한다(실패 셀 포함). 사전등록 개념은 [S62]를 따른다.
- P4. **순환성 차단**
  - 자기지도 주입 학습에 쓴 가족은 평가에서 제외한다(leave-one-family-out).
  - 실제 이상 파일은 TSAP식 튜닝에도 쓰지 않는다.
  - 팀이 이미 실제 이상의 요약통계를 보았다는 사실은 보고서에 공개한다.
  - "실제 이상과 가장 닮은 가족"을 빼도 결론이 같은지 민감도 분석을 한다.
- P5. **가족별로 보고하고 평균 POD는 금지**한다([S53] G-47/48).

**데이터 분할**
- 정상 버스트를 시간 순 5개 연속 블록으로 나눈다(blocked CV). 블록 경계에는 5버스트 버퍼를 둔다.
- 각 fold는 fit 50%, cal(임계값) 20%, test 30%로 쓴다. 주입은 test에만 한다.
- 긴 스트림(램프용 4–8시간)은 test 블록 버스트의 stationary bootstrap으로 만든다. 77분 원천을 재사용한다는 사실은 명시한다.

**고장 가족(F) — 메커니즘 → 신호 → 크기**

| 가족 | 메커니즘(출처) | 주입 구현 | 크기 격자(사전등록 제안) |
|---|---|---|---|
| F1 진동 광대역 에너지 증가 | 마모·헐거움·캐비테이션의 고주파 에너지가 에일리어싱됨 [S32][S41]. "change of vibration"도 평가기준 [S60] | (a) 곱셈 이득 ×g, (b) 가산: 같은 버스트의 IAAFT 대리잡음을 더해 RMS 비 g. 채널: 상·하·둘 다. 상태: 전체/부하만 | g ∈ {1.1, 1.2, 1.3, 1.5, 1.75, 2, 2.5, 3, 4, 6} |
| F2 충격성 | 치면 손상의 충격 + 감쇠 토크진동 [S47]. 점 이상 관행 [S5][S9] | 표본당 확률 p의 스파이크, 진폭 a·σ_burst, 부호 무작위, 채널 부분집합 | p ∈ {0.5, 1, 2, 5, 10}%, a ∈ {3, 5, 8} |
| F3 협대역 톤 출현 | 기어 맞물림·축 고조파가 미지 주파수로 에일리어싱됨 | 진폭비 ρ의 정현, f ~ U(0.2, 4.8) Hz(정상 선 1.8/3.6 Hz ±0.1은 별도 셀) | ρ ∈ {0.25, 0.5, 1, 2} |
| F4 토크(마찰) 증가 → 전류 | 마찰토크 모델 [S34][S35], 전류–부하 관계 [S49] | 부하 버스트 진폭 ×(1+ε), 공회전은 ×(1+ε/4) | ε ∈ {2, 5, 10, 20}% |
| F5 토크 맥동 → 전류 진폭변조 | 부하토크 변동 → 고정자 전류 [S46][S47][S48] | 버스트 진폭에 AM: 1 + m·sin(2πf_m t), f_m ~ U(0.05, 2) Hz, 또는 버스트 간 진폭 요동 증가 | m ∈ {2, 5, 10, 20}% |
| F6 결합 이탈 / 센서 이상 | 부하와 무관한 진동 변화. 센서 탈착·이득 저하 | 진동 ×{0.5, 0.7}(전류 그대로). flat-line, 오프셋 +3σ, 채널 결측 | — (센서 이상은 '데이터 품질 경보'로 따로 라벨) |
| F7 듀티사이클 변화 | 내부누설 → 부하구간 연장 가설. 누설의 토크 영향은 미미 [S45] | 10분 창 부하 버스트 비율을 블록 재표본으로 올림 | +10, +20, +30 %p |
| F8 램프(점진 성장) | 조기탐지의 본질. creeping [S3] | F1/F2/F4/F5를 0에서 목표까지 선형 증가 | 목표: F1 g=3, F2 p=5%, F4 ε=20%, F5 m=20%. 기간 T ∈ {10, 30, 60, 120} 분 |

**교란 가족(N) — "알람이 울리면 안 되는 정상 운전변화" = 불변성(metamorphic) 시험 [S12][S66]**

| 가족 | 실제 원인 | 구현 | 크기 |
|---|---|---|---|
| N1 부하 혼합 변화 | 생산 속도·정지·대기 | 10분 창 부하 비율을 블록 재표본으로 조절. **정상 파일 60–70분 공회전 구간은 실데이터 자연 실험으로 따로 보고** | 0–50%(정상 관측 0.00–0.48) |
| N2 부하 수준 변화 | 다이·제품 변경 | 전류 ×(1+γ), 진동 ×(1+γ)^b(하부 b ≈ 1.7–1.9, 상부 b ≈ 0.6–0.8) | γ ∈ {±10, ±20, ±30}% |
| N3 전원전압·전류센서 이득 | 계통전압 변동 [S49] | 전류만 ×(1±r) | r ∈ {2, 5}% (F4와 겹침, 3.6 끝의 식별불가 쌍 참조) |
| N4 오일 온도(점도) | 계절·시간대·냉각 | 부하 전류 −c, 진동 RMS ×v 동시 적용(ZeMA 앵커) | c ∈ {2, 4, 6}%, v ∈ {1.1, 1.2, 1.3} |
| N5 전류 에일리어스 주파수 이동 | 수집 시계·공급주파수. 직입(DOL) 유도전동기라면 전류 기본주파수 = 공급주파수라 펌프 상태와 무관(가정) | 전류를 A·sin(2πf′t+φ)+잔차로 재합성 | f′ ∈ {0.2, 0.4, 0.8, 1.0} Hz (정상 0.594–0.607) |
| N6 수집 패턴 | PLC 로깅 불규칙 | 버스트 길이 절단, 간격 분포 변경 | 길이 {10, 20, 30} |
| N7 위상 | 수집 시작 시점 | 버스트 위상 무작위화 | — |
| N8 요일·시간대 | 실제 이상은 일요일 10:51, 정상은 화요일 00:00–01:17 | **시뮬레이션 불가 → 한계로 명시** | — |

**지표와 보고**
- 가족×크기별 POD@고정FPR(버스트·창 단위). fold·시드 부트스트랩 구간을 붙인다.
- hit/miss GLM(로그 크기)으로 **a50, a90, 가능하면 a90/95**를 구한다. MIL-HDBK 방식이되 "MAPOD형 보조 증거"로 표기한다.
- 램프: 검출지연(중앙값·IQR) vs 성장속도, 경보 시점 크기, 경보 전 오경보 수.
- 교란 가족별 FPR과 **시간당 경보 수**.
- 식별불가 쌍 ROC: 같은 크기 축에서 F4 vs N3, F1(소) vs N4, F7 vs N1.
- 기준선을 반드시 둔다: one-liner(버스트 RMS 임계)와 부하조건부 RMS [S12]. 그다음 ML 모델(LSTM-AE 등)을 같은 하네스에 넣는다.
- PA 금지 [S13]. 실제 이상 1건에서는 "탐지 여부, 첫 경보까지 시간·버스트 수, 점수 여유도, **â 역산 위치**(예: '진동 에너지 기준선 대비 ×k에 해당')"만 보고한다. 600행 위의 F1은 독립 표본 추정치가 아니므로 주지표로 쓰지 않는다.

**보고서·발표에서 신뢰를 얻는 장치**
1. 증거 위계 그림(L1–L4). "실제 이상 성공 = 쉬운 사례 확인", "조기탐지 능력 = L2의 POD·지연 곡선"을 명시한다.
2. **주입 카드**: 가족마다 메커니즘, 신호 효과, 크기 범위, 출처, 운용한계([S65]의 limits of operation)를 1장으로 정리한다.
3. **누설 점검표**([S63][S64] 차용): 실제 이상 미사용, 학습·평가 가족 분리, 시간 블록 분할, 임계값 정상만, 격자 사전등록 해시.
4. **부정적 결과를 전면에 둔다.** 전류만 변하는 고장의 사각지대, 소폭 진동 증가와 온도 교란의 혼동, 오경보율 검증 불가. 과대주장보다 신뢰를 얻는다.
5. 현장 적용(과제 4번 항목)
   - 2단 경보: '관찰'은 창 평균 기반 낮은 임계, '점검'은 높은 임계 + k-of-n 지속성.
   - 경보에 **가족 서명**을 붙여 점검 우선순위를 준다. 충격성↑ → 기어·베어링·오일 분석 우선. 진동 에너지↑(부하 대비) → 펌프 체결·정렬·흡입 확인. 전류만↑ → 전원·생산 변경 기록부터 확인.
   - â 역산으로 "심각도 환산값"을 표시한다.
   - 다이 교체, 정지, 오일 온도를 기록하는 운전변경 로그를 권고한다(N1–N4 오경보 억제).
6. 확률 출력과의 연결(타 주제와 접점): POD(크기별 P(경보|고장))와 PFA(P(경보|정상))를 주면 사전확률을 명시한 베이즈 사후확률로 이상 확률을 설명할 수 있다.

**식별불가 쌍 — FP/FN이 몰리는 조건을 미리 말하는 법**
- F4(ε ≤ 5%) ≈ N3(전압·이득 ±5%) ≈ N2 일부. 압력·전압 기준이 없으면 구별할 수 없다.
- F1(g ≤ 1.3) ≈ N4(진동 ×1.1–1.3, 온도). 오일 온도 신호가 없으면 구별할 수 없다.
- F7 ≈ N1(생산 혼합 변화). 생산 로그가 없으면 구별할 수 없다.
- 이 셋을 "센서 구성상 구조적 FN/FP 영역"으로 제시하면, 과제의 '오경보·미탐 조건 분석'에 대해 데이터만으로 나올 수 있는 가장 정직한 답이 된다.

---

## 4. 위험·한계·반론

1. **순환성.** 주입 가족이 곧 '고장'의 정의다. 결과는 "이 가족들에 대해" 조건부다(Goswami [S4] 경고 (i)). 팀이 실제 이상의 요약통계를 이미 봤으므로 가족 설계가 그쪽으로 기울 위험이 있다. 공개, 민감도 분석, leave-one-family-out으로 완화하지만 없앨 수는 없다.
2. **현실성.** 실제 고장은 운전변화와 함께 오고, 비선형으로 자라며, 여러 증상이 섞인다. 깨끗한 단일 주입은 낙관적이다. 인공 손상조차 실제를 대표하지 못한 사례가 있다(Lessmeier [S50]). 에일리어싱과 DAQ 필터링을 모르므로 "kHz 고장 에너지 → 10 Hz 분산 증가" 사상 자체가 가정이다.
3. **통계적 과대평가.**
   - 원천 정상은 77분 한 세션이다. 주입을 아무리 반복해도 날짜·조건 다양성은 늘지 않는다(MIL-HDBK 6.4).
   - 버스트 간 의존과 느린 표류 때문에 창 평균 이득이 과장될 수 있다.
   - fold 간 POD 범위가 넓다.
   - 오경보율 상한 검증 능력에 한계가 있다(rule of three).
4. **반론과 증거 충돌.**
   - COUTA [S8]는 겹치지 않는 주입도 도움이 된다고 하고, Yoo [S10]·NCAD [S5]는 해칠 수 있다고 한다.
   - 주입 기반 선택이 낫다는 Goswami [S4]와, 내부 지표 선택은 쓸모없다는 Ma [S15](다른 영역)가 공존한다.
   - 따라서 "주입으로 고른 모델이 최고"라고 주장하지 말고 **"가족별로 이런 검출한계를 보였다"**고만 말한다.
5. **외부 데이터(ZeMA) 사용 위험.**
   - 다른 리그다. 진동은 1 Hz 속도값이고 고장은 오리피스로 모사했다.
   - 대회 규정상 외부데이터 고지(이유·방법·출처)가 필요하다.
   - CC BY 4.0이라 파생 표를 동봉할 수 있다(저작자 표시와 변경 사실 명시). 다만 "학습데이터를 zip에 포함"하라는 규정이 파라미터 앵커에도 적용되는지는 불명확하다(5장).
6. **생성모델 유혹.** 그럴듯한 그림을 주지만 이상 1건을 복제하는 누설 경로다. 심사자에게 "직접 만든 시험지"로 보일 위험이 가장 크다.
7. **상용 시뮬레이터 의존.** Simscape·MATLAB 모델은 zip 원샷 재현과 재배포 요건에 맞지 않는다.
8. **표준 인용 위험.** ISO 본문은 유료라 조항 번호만 인용한다. 흔히 회자되는 'ISO 10816 경보 = 기준선 + 구역 B 상한의 25%' 규칙은 확인하지 못했으므로 쓰지 않는다.
9. **영역 차이.** Yoo [S10], Somepalli [S28]는 이미지, Ma [S15]는 표 형식, MIL-HDBK·SHM은 구조 NDE 분야다. 모두 유추 적용임을 명시한다.

---

## 5. 아직 확인 못 한 것

- 설비 사실관계: 펌프 형식(가이드북은 기어형을 '예시'로 설명할 뿐), 모터 구동 방식(DOL인지 인버터인지; N5의 전제), DAQ 안티앨리어싱 필터 유무, 실제 표본화 주기(0.600 Hz 에일리어스의 기원은 R1 주제와 겹침).
- ISO 10816/20816의 경보 설정 관행(25% 규칙)과 구역 경계 수치: [미검증], 유료 본문 미열람.
- 오일 점도–온도 관계의 정량값(ISO VG별 수치): 미확보. ZeMA 실측 대비로 대체했다.
- Sobie et al. 2018 [S51] 본문·초록(출판사 비공개), Helwig I2MTC 2015 [S42] 본문(유료), Vacca & Guidetti [S37]·Frith & Scott [S38] 본문: [검색만].
- MathWorks 예제 [S33]·Simscape 블록 [S34]의 수치(누설 계수 기본값 2.0 등): WebFetch 요약에 의존했으므로 인용 전 원문 대조가 필요하다.
- Iglesias et al. [S20] 출판본 라이선스(Springer 접근 실패), TimeGAN 코드 라이선스의 정식 표기.
- 대회 규정 해석: 외부데이터를 "학습"이 아니라 "주입 크기 앵커"로만 쓸 때도 zip 동봉과 고지 의무가 같은지.
- 캐비테이션의 기어펌프 진동·전류 서명: 리뷰 [S41]의 참고문헌 목록(예: 저주파 에너지 기반 플런저 펌프 캐비테이션 인식, 2021)에서만 봤다. [미검증]
- GutenTAG custom-input으로 다채널·버스트 구조 데이터에 직접 주입할 수 있는지(실험하지 않음). 우리 구현은 numpy 자작을 권한다.
- 파일럿 수치는 단순 특징(RMS·첨도) 기준이다. LSTM-AE 등 실제 후보 모델의 POD는 아직 없다.

---

## 부록 R. 재현용 스크립트(스크래치패드, 저장소 밖)

경로 접두어: `/private/tmp/claude-501/-Volumes-YJSSD-----k------/24589ffb-d6d3-4fe1-b00c-1f2f84f3d931/scratchpad/r5_work/`

- `eda_r5.py`: 버스트 분할, 채널 통계, 버스트 내 자기상관, 주파수 피크.
- `eda_r5b.py`: 버스트별 전류 정현 적합(주파수·진폭·R²), 부하조건부 진동 잔차, 진폭 분포.
- `pilot_pod.py`: 정상 데이터만 쓴 주입 POD 파일럿(단일 시간 분할, 조건부/비조건부 비교, 부하 교란, 전류만 변하는 고장).
- `pilot_pod_cv.py`: blocked 5-fold 파일럿(에너지·부하·톤·충격 가족; RMS·첨도·결합 점수).
- `zema_effects.py`: ZeMA(CC BY 4.0) 누설·냉각기 효과크기. 원자료는 `r5_work/zema/`(Zenodo 10.5281/zenodo.1323611에서 내려받음).
- 원문 PDF·텍스트: `r5_work/pdf/`(Lai, Goswami, NCAD, SR-CNN, AnomalyBERT, COUTA, CARLA, Yoo, Wu-Keogh, TSAP, Kim, Wen, Iwana, Um, Iglesias, TSGBench, Diffusion-TS, CSDI, Esteban, Somepalli, Schmidl, TSB-UAD, Lessmeier, MIL-HDBK-1823A, NASA-STD-7009B, DOE fact sheet, Helwig SENSOR 2015).

---

## 부록 S (봉인) — 이상 파일에서 본 것

> **블라인드를 유지해야 하는 계획자는 이 부록을 읽지 말 것.** 주입 가족을 설계할 때 이 내용을 쓰면 순환성이 커진다. 공개 목적으로만 기록한다.

R5는 `outlier_data.csv`(600행, 21버스트)의 요약 통계를 계산했다(`eda_r5.py`, `eda_r5b.py`). 그 결과:

- 진동 버스트 내 lag-1 자기상관이 상부 0.69, 하부 0.67이다(정상 −0.03, 0.26). 주성분은 상부 약 1.1 Hz이고, 저주파 성분이 강하게 나타났다.
- 상·하부 진동의 상관은 −0.38로, 정상(+0.37)과 부호가 반대다.
- 버스트 RMS 기준으로 진동과 전류의 결합이 사라졌다(r ≈ −0.13; 정상 +0.64, +0.90).
- 전류가 더 이상 깨끗한 정현파가 아니다(30표본 이상 버스트의 적합 R² 0.29–0.78; 정상 ≥ 0.994). 평균 오프셋이 57로 커졌고, 우세 주파수는 약 0.1–0.2 Hz다.
- 시사점: 실제 이상은 F1(큰 배율)·F3·F6과 전류 파형 변화가 겹친 모습이다. 이 중 전류 파형·에일리어스 변화는 펌프 고장이 아닌 수집·전원 조건 차이(N5, N8)일 가능성을 배제할 수 없다. 실제 이상에서의 성공이 '고장 탐지'의 증거인지 '조건 차이 탐지'의 증거인지는 이 데이터만으로 판정할 수 없다.
