# R3 — 이상탐지 방법과 평가 방법론 조사

대상 데이터: 프레스 유압펌프. 3채널(AI0 상부 진동, AI1 하부 진동, AI2 전류), 10 Hz, 최대 50샘플(≤5 s) 버스트, 정상은 하룻밤 77분(약 2만 행), 이상은 에피소드 하나(600행, 166 s).

- 작성일: 2026-10-01 · 작성: R3 조사 에이전트
- 독립성: `yejun/` 아래 파일과 저장소 git 이력은 열지 않았습니다. 원천 CSV(`데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전/`)는 읽기만 했습니다.
- 확인 상태 표기
  - **opened-전문**: 본문 PDF, 웹 페이지, 소스코드 또는 LICENSE 파일을 직접 받아서 읽음.
  - **opened-메타**: DOI(Crossref), Semantic Scholar, PMLR, arXiv API로 서지 정보만 확인. 본문 내용 주장은 검증하지 않았습니다.
  - **search-only**: 검색 결과 요약으로만 봄.
  - **unverified**: 확인하지 못함.
- 신뢰 등급: A는 동료심사 저널, 주요 학회, 표준, 공공기관입니다. B는 프리프린트, 워크숍, 기술문서, 소프트웨어 논문입니다. C는 블로그나 홍보 자료로, 근거로 쓰지 않습니다.
- **[R3 점검]**: 이번 조사 중 원천 CSV로 직접 계산한 빠른 점검입니다. 튜닝하지 않았고 일부 선택(최소 버스트 길이 10, 특징 구성 등)은 임의이므로 **계획 수립용이며 최종 결과로 인용하면 안 됩니다.** 스크립트 경로: `scratchpad/r3_work/`(`r3_quick*.py`, `r3_demo.py`, `r3_sens.py`, `r3_nbm*.py`, `r3_blockperm.py`).
- 수치 정의
  - FA = 오경보(false alarm).
  - FA/h = 정상 데이터의 벽시계 1시간당 오경보 수(정상 구간 1.282 h 기준).
  - "버스트" = 0.15 s 넘는 시간 간격으로 나눈 연속 샘플 묶음.

---

## 1. 핵심 요약

1. **이상 에피소드는 '한 줄짜리(one-liner)'로도 잡힙니다. 그래서 탐지 성공 자체는 근거가 약하고, 승부는 정상 쪽 오경보와 불확실성의 정직한 보고에서 납니다.**
   - [R3 점검] `|AI0| > 정상 최대값(0.352)` 규칙은 이상 에피소드의 둘째 샘플, 즉 첫 이상 샘플 후 **0.1 s**에 경보를 냅니다.
   - 버스트 단위 `max|AI0| > 학습 폴드 최대` 규칙은 연속 블록 5겹 검증에서 정상 FA가 **599개 중 1개**이고, 이상 버스트는 **21개 중 18개**를 잡습니다.
   - Wu & Keogh(TKDE)는 이 상황을 "triviality"라고 부릅니다. 그들의 brute-force 실험에서 Yahoo 시계열 **316/367(86.1%)**이 한 줄 규칙으로 풀렸습니다.
   - 따라서 one-liner, 상수 예측, 무작위 점수 같은 **사소한 기준선(trivial baseline)을 반드시 보고**해야 합니다(§3.3).
2. **교란(confound)과 지름길(shortcut)은 가설이 아니라 데이터에서 측정되는 문제입니다.**
   - [R3 점검] 전류의 버스트 내 lag-1 자기상관(정상 중앙값 0.928, 이상 0.382)과 우세 에일리어싱 주파수(정상 약 0.6 Hz, 이상 약 0.2–0.28 Hz)는 버스트 단위 **AUC 1.000**으로 두 파일을 완벽히 가릅니다. 이 한 특징만으로 MCD/kNN 탐지기를 만들면 이상 버스트 16/17을 잡고 FA는 약 3.1/h입니다.
   - 이것이 고장 신호인지(압력 불안정 → 전류 요동), 측정이나 운전 조건 차이인지(샘플링 클록, 구동 주파수, 날짜와 운전 상태) 데이터만으로는 구분할 수 없습니다.
   - `TimeStamp`(날짜·시각)와 `Unnamed: 0`(행 번호; 이상 파일은 0–599)도 누설 경로입니다.
   - 따라서 **지름길 탐침(probe), 특징군 절제(ablation), 음성 대조(negative control)가 필수**입니다. Geirhos 2020, DeGrave 2021, Lapuschkin 2019가 근거입니다.
3. **금지하거나 보조로만 쓸 지표와 관행**
   - **Point-adjust(PA) F1** — Kim et al.(AAAI 2022)에서 무작위 점수의 F1PA가 SWaT 0.969, WADI 0.965, SMAP 0.961로 기존 방법보다 높았습니다.
   - **테스트 데이터로 임계값을 정하는 관행** — Anomaly Transformer, Time-Series-Library(TimesNet 등), DCdetector의 공식 코드는 모두 `train+test` 점수를 합친 분위수로 임계값을 정하고 PA를 적용합니다. 코드에서 확인했습니다.
   - **정확도(accuracy)** — 모두 정상으로 찍는 상수 예측이 97.087%입니다.
   - **주 지표로 권장하는 것**
     - 보류한 정상 블록의 FA/h(Poisson 정확 CI 포함)
     - 에피소드 탐지 여부와 첫 이상 샘플부터 첫 경보까지 시간
     - 버스트 단위 재현율과 FN 목록
   - **보조 지표**: 임계값과 무관한 AUC-PR과 VUS-PR(TSB-AD 권장), 그리고 FA/h–지연 곡선(AMOC 유형).
4. **불확실성의 하한이 매우 넓습니다. 이를 숨기지 말아야 합니다.**
   - 정상 1.282 h에서 FA가 0건이어도 95% 단측 상한은 **2.34 FA/h**(양측 2.88/h)입니다.
   - 에피소드 재현율 1/1의 Clopper–Pearson 95% CI는 **[0.025, 1]**입니다.
   - 같은 길이(166 s)의 정상 블록 28개를 비교하는 블록 순위 검정의 최소 p는 1/29 = **0.034**입니다. 진동 진폭 통계와 지름길 통계(전류 자기상관)가 **둘 다 이 최소 p에 도달**합니다. 즉 "유의함"으로는 고장과 세션 차이를 가를 수 없습니다.
   - 운영 목표 "8시간 교대당 FA 1회"는 버스트당 α ≈ 2.7×10⁻⁴를 뜻합니다. 정상 버스트 530–599개로는 이 수준을 경험적으로 보정할 수 없습니다. 지속성 규칙이나 EVT 같은 외삽이 필요합니다.
5. **방법 근거는 일관되게 "단순한 방법이 경쟁력 있다"입니다.**
   - Schmidl et al.(PVLDB 2022): "no clear winner".
   - TSB-AD(NeurIPS 2024): "simpler architectures and statistical methods often yield better performance".
   - Sarfraz et al.(ICML 2024): PCA 재구성오차 기준선이 SWaT·SMD에서 Anomaly Transformer보다 F1과 F1T가 높았습니다.
   - Audibert et al.(Pattern Recognition 2022): "no family of methods outperforms the others".
   - ADBench: "none of the benchmarked unsupervised algorithms is statistically better".
   - Goldstein & Uchida: 전역 이상에는 k-NN을 권장합니다.
   - 우리 규모(학습 가능한 버스트 약 530–599개)에 맞는 권장 구성
     - **버스트 단위 위상불변 특징**(RMS/표준편차, 최대 절대값 등)과 SPC/통계(T²/SPE, Mahalanobis), kNN의 조합입니다.
     - 가이드북 LSTM-AE는 **공식 기준선**으로 두고, 같은 구조의 **무작위 가중치(미학습) 버전**도 함께 보고합니다(Kim et al.의 Case 3).
     - 트랜스포머 계열과 파운데이션 모델은 주 모델로 권장하지 않습니다.
6. **오경보를 줄이는 가장 유력한 수단은 '부하 조건부 정상거동 모델(normal behaviour model)'입니다.** 과제 문구의 "정상 운전 변화 오인"과 정확히 맞닿습니다.
   - [R3 점검] 정상 버스트에서 corr(log std AI1, log std 전류) = **0.94**입니다.
   - 전류 표준편차로 조건화하면 AI1 잔차 SD가 0.59에서 **0.20**으로 줄었습니다.
   - 같은 명목 FA에서 합성 ×2 진폭 증가의 검출률은 고정 임계값 42%에서 조건부 잔차 **70%**로 올랐습니다.
   - 단, 공변량으로 `max|I|`를 넣으면(이상 파일 전류의 DC 오프셋과 파형 차이에 민감) 이상 검출이 **5/17**로 떨어졌습니다. 공변량 선택과 외삽 점검이 핵심입니다.
7. **"조기" 탐지는 예지(lead time)로 측정할 수 없습니다.** 고장 전 데이터가 없고, 이상은 5일 뒤 다른 파일입니다. 측정할 수 있는 것은 세 가지입니다.
   - 에피소드 안에서 첫 경보까지의 지연. 설계에 따라 다릅니다: 행 단위 0.1 s, 10샘플 미만 버스트를 건너뛰면 13.7 s.
   - 지속성 규칙(k-of-n)에 따른 FA–지연 절충. [R3 점검] 2-of-3 규칙에서 단일 버스트 경보 6건이 경보 개시 1건으로 줄었습니다.
   - 합성 심각도 스윕(고정 FA에서 최소 검출 가능 변화, ARL1 유사).
   - [R3 점검] 6특징 MCD는 두 진동 채널이 ×2 커져도 사실상 못 잡습니다(1%). 다변량 omnibus 거리가 한 방향 변화를 희석합니다.
8. **라벨 단위 문제가 있습니다.**
   - [R3 점검] 이상 파일 버스트 3개(#3, #19, #20)의 AI0 표준편차가 0.022–0.029로 정상 중앙값(0.070)보다 **작습니다**. 진폭 기반 one-liner의 FN이 정확히 여기에 몰립니다.
   - 파일 전체가 1로 라벨된 "파일 단위 라벨"이라 생기는 일입니다. Wu & Keogh와 TSB-AD가 지적한 "mislabeling" 유형입니다.
   - FN 분석에서 이 버스트들의 라벨 의미(고장 중 저부하 상태인지, 비고장 구간인지)를 분리해서 서술해야 합니다.
9. **'확률' 출력은 정직하게 정의해야 합니다.**
   - 이상 에피소드가 하나뿐이므로 Platt이나 isotonic 같은 지도 보정은 불가능합니다.
   - 대안은 정상 보정 집합으로 만든 **conformal p-value**(Bates et al., Ann. Stat. 2023)입니다. P(점수 ≥ s | 정상)를 교환가능성 가정 아래 보장하고, 임계값에 따른 FPR의 균일 신뢰구간도 제공합니다. 이를 1 − p 형태의 "이상 정도 확률"로 제시하되 **P(고장 | x)가 아님을 명시**해야 합니다.
   - PyOD `predict_proba(method='unify')`(Kriegel 2011)는 점수를 변환할 뿐 보정된 확률이 아닙니다.
10. **라이선스**
    - 핵심 스택은 모두 관대한 라이선스입니다.

      | 라이브러리 | 라이선스 |
      |---|---|
      | scikit-learn | BSD-3-Clause |
      | PyOD | BSD-2-Clause |
      | STUMPY | BSD-3-Clause |
      | ruptures | BSD-2-Clause |
      | statsmodels | BSD-3-Clause |
      | PyTorch | BSD 계열 |
      | TensorFlow | Apache-2.0 |
      | tsfresh | MIT |
      | sktime | BSD-3-Clause |
      | Darts | Apache-2.0 |
      | TSB-AD | Apache-2.0 |
      | MOMENT 코드·가중치 | MIT |
      | Chronos 코드·가중치 | Apache-2.0 |

    - **위험 요소**
      - **Moirai 가중치 CC-BY-NC-4.0**(1.0/1.1/2.0/MoE 모두)
      - **TimesFM 3.0 가중치 비상업 전용**(2.5 이하는 Apache-2.0)
      - **alibi-detect: Business Source License 1.1**(오픈소스 아님)
      - **catch22/pycatch22: GPL-3.0**
      - **hctsa: CC BY-NC-SA 4.0 + GPL-3.0**
      - **saxpy: GPL-2.0**
      - **twitter/AnomalyDetection: GPL-3.0**
      - **NAB**: 2015-08-10부터 2024-12-03까지 **AGPL-3.0**, 이후 MIT. 옛 복사본은 AGPL입니다.
      - **VUS 저장소: LICENSE 파일 없음**(PyPI `vus`는 Apache-2.0 표기)
      - **DCdetector 저장소: 라이선스 없음**
      - PyPI `prts`: 라이선스 불명확

---

## 2. 출처 표

### 2.1 평가 비판·지표·벤치마크

| ID | 인용(저자, 제목, 게재처, 연도, DOI/URL) | 유형·등급 | 확인 | 적신호·이해관계 | 라이선스/저작권 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| E1 | Wu, R., Keogh, E. J. "Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress." *IEEE TKDE* 35, 2421–2429 (2023; early access 2021). DOI 10.1109/TKDE.2021.3112126. 확장초록: *ICDE 2022* pp. 1479–1480, DOI 10.1109/ICDE53745.2022.00116. arXiv 2009.13807v5 | 저널 A | opened-전문(arXiv v5). 서지는 Crossref, 권·쪽은 Semantic Scholar. 호(issue)는 미확인 | 저자가 대안 아카이브(UCR Anomaly Archive)를 만들었으므로 경미한 이해관계. 일부 판정은 시각적 | IEEE 저작권. arXiv 판은 재사용 라이선스 없음 | 요지와 짧은 인용은 가능. 그림 재사용 금지 |
| E2 | Kim, S., Choi, K., Choi, H.-S., Lee, B., Yoon, S. "Towards a Rigorous Evaluation of Time-Series Anomaly Detection." *AAAI* 36(7):7194–7201 (2022). DOI 10.1609/aaai.v36i7.20680. arXiv 2109.05257 | 학회 A | opened-전문(AAAI 페이지, arXiv PDF Table 2) | 없음 | AAAI 저작권 | 수치 인용 가능 |
| E3 | Paparrizos, J., Boniol, P., Palpanas, T., Tsay, R. S., Elmore, A., Franklin, M. J. "Volume Under the Surface: A New Accuracy Evaluation Measure for Time-Series Anomaly Detection." *PVLDB* 15(11):2774–2787 (2022). DOI 10.14778/3551793.3551830 | 학회지 A | opened-전문(PVLDB PDF) | 제안자 그룹이 이후 TSB-AD에서 VUS-PR을 권장하므로 자기 지표를 권장하는 구조 | 논문 **CC BY-NC-ND 4.0**(PDF 표기 확인) | 그림 변형 불가(ND). 인용과 재서술만 |
| E4 | Paparrizos, J., Kang, Y., Boniol, P., Tsay, R. S., Palpanas, T., Franklin, M. J. "TSB-UAD: An End-to-End Benchmark Suite for Univariate Time-Series Anomaly Detection." *PVLDB* 15(8):1697–1711 (2022). DOI 10.14778/3529337.3529354 | 학회지 A | opened-전문(초록, 13,766 시계열) | 같은 그룹 | 논문 CC BY-NC-ND 4.0. 코드 Apache-2.0(GitHub API) | 데이터셋별 원 라이선스가 다르므로 zip에 넣지 않음 |
| E5 | Schmidl, S., Wenig, P., Papenbrock, T. "Anomaly Detection in Time Series: A Comprehensive Evaluation." *PVLDB* 15(9):1779–1797 (2022). DOI 10.14778/3538598.3538602 | 학회지 A | opened-전문(RI 1–14) | Rolls-Royce 연구비 사사 | 논문 CC BY-NC-ND 4.0 | 인용 가능 |
| E6 | Liu, Q., Paparrizos, J. "The Elephant in the Room: Towards A Reliable Time-Series Anomaly Detection Benchmark." *NeurIPS 2024 Datasets & Benchmarks Track*. https://proceedings.neurips.cc/paper_files/paper/2024/hash/c3f3c690b7a99fba16d0efd35cb83b2c-Abstract-Datasets_and_Benchmarks_Track.html | 학회 A | opened-전문(proceedings PDF와 NeurIPS 발표 슬라이드) | VUS 제안 그룹. 파운데이션 모델은 사전학습 데이터 오염 위험을 저자들도 언급 | 코드 Apache-2.0. 데이터는 원 출처 라이선스를 따름 | 데이터 재배포 금지. 결론 인용은 가능 |
| E7 | Sarfraz, M. S., Chen, M.-Y., Layer, L., Peng, K., Koulakis, M. "Position: Quo Vadis, Unsupervised Time Series Anomaly Detection?" *ICML 2024*, PMLR 235:43461–43476. arXiv 2405.02678 | 학회 A(position paper) | opened-전문(PMLR 페이지, arXiv PDF Table 2) | Mercedes-Benz Tech Innovation 소속. 입장 논문 | "Copyright 2024 by the author(s)" | 수치 인용 가능 |
| E8 | Tatbul, N., Lee, T. J., Zdonik, S., Alam, M., Gottschlich, J. "Precision and Recall for Time Series." *NeurIPS 2018*. arXiv 1803.03639 | 학회 A | opened-전문(NeurIPS 페이지 제목, arXiv PDF) | 원 구현 저장소(IntelLabs/TSAD-Evaluator) **404** | — | 구현은 수식 보고 재작성 권장(PyPI `prts` 라이선스 불명) |
| E9 | Lavin, A., Ahmad, S. "Evaluating Real-Time Anomaly Detection Algorithms — the Numenta Anomaly Benchmark." *IEEE ICMLA 2015*, pp. 38–44. DOI 10.1109/ICMLA.2015.141. arXiv 1510.03336 | 학회 A−(중견 학회) | opened-전문 | Numenta(자사 HTM 알고리즘)의 이해관계. 점수 해석이 어렵다는 비판(E1, E8) | NAB 저장소 MIT(2024-12-03부터). **2015-08-10~2024-12-03은 AGPL-3.0**(GitHub 커밋 이력 확인) | 옛 NAB 코드 복사본은 AGPL |
| E10 | Hwang, W.-S., Yun, J.-H., Kim, J., Kim, H. C. "Time-Series Aware Precision and Recall for Anomaly Detection." *CIKM 2019*, pp. 2241–2244. DOI 10.1145/3357384.3358118 | 학회 A | opened-메타(본문 미열람) | — | 코드 wshw4ng/TaPR MIT | 내용 인용 전 본문 확인 필요 |
| E11 | Garg, A., Zhang, W., Samaran, J., Savitha, R., Foo, C.-S. "An Evaluation of Anomaly Detection and Diagnosis in Multivariate Time Series." *IEEE TNNLS* 33(6):2508–2517 (2022). DOI 10.1109/TNNLS.2021.3105827 | 저널 A | opened-전문(arXiv 2109.11428) | — | IEEE 저작권. 코드 mvts-ano-eval MIT | 인용 가능 |
| E12 | Huet, A., Navarro, J. M., Rossi, D. "Local Evaluation of Time Series Anomaly Detection Algorithms." *KDD 2022*, pp. 635–645. DOI 10.1145/3534678.3539339 | 학회 A | opened-전문(초록) | Huawei. E6 슬라이드 표에서 무작위 점수의 Affiliation-F가 0.70으로 관대함 | 코드 MIT | 보조 지표로만 |
| E13 | Sørbø, S., Ruocco, M. "Navigating the metric maze: a taxonomy of evaluation metrics for anomaly detection in time series." *Data Min. Knowl. Disc.* 38(3):1027–1068 (2024). DOI 10.1007/s10618-023-00988-8 | 저널 A | opened-메타 | — | 미확인 | 지표 분류의 포인터로만 |
| E14 | Ren, H. et al. "Time-Series Anomaly Detection Service at Microsoft." *KDD 2019*, pp. 3009–3017. DOI 10.1145/3292500.3330680 | 학회 A(산업) | opened-전문(arXiv 1906.03821, 지연 k 규정) | Microsoft | — | 지연 제약 평가의 선례로 인용 |
| E15 | Xu, H. et al. "Unsupervised Anomaly Detection via Variational Auto-Encoder for Seasonal KPIs in Web Applications" (Donut). *WWW 2018*, pp. 187–196. DOI 10.1145/3178876.3185996 | 학회 A | opened-메타. "PA의 기원"은 E7과 M21의 서술로 간접 확인 | — | — | 기원 언급만 |
| E16 | Hundman, K. et al. "Detecting Spacecraft Anomalies Using LSTMs and Nonparametric Dynamic Thresholding." *KDD 2018*, pp. 387–395. DOI 10.1145/3219819.3219845 | 학회 A | opened-전문(일부) | NASA JPL | telemanom: Caltech BSD 유사 | 동적 임계값과 가지치기 아이디어 |
| E17 | Fawcett, T., Provost, F. "Activity monitoring: noticing interesting changes in behavior." *KDD 1999*, pp. 53–62. DOI 10.1145/312129.312195 | 학회 A | opened-메타. **본문 403. AMOC 정의는 기억에 의존하므로 unverified** | — | 유료 | AMOC 용어를 쓸 때 "Fawcett & Provost가 제안한 timeliness–FA 곡선" 정도로만 서술 |
| E18 | van den Burg, G. J. J., Williams, C. K. I. "An Evaluation of Change Point Detection Algorithms." arXiv 2003.06222v3 (2020–) | 프리프린트 B | opened-전문 | — | 코드 TCPDBench MIT | "zero(무변화) 기준선" 근거 |
| E19 | Sehili, M. E. A., Zhang, Z. "Multivariate Time Series Anomaly Detection: Fancy Algorithms and Flawed Evaluation Methodology." arXiv 2308.13068v2 (TPCTC 2023 게재 표기) | 워크숍 B | opened-전문(초록). 게재본 서지 미확인 | — | — | 보조 근거 |
| E20 | Audibert, J., Michiardi, P., Guyard, F., Marti, S., Zuluaga, M. A. "Do deep neural networks contribute to multivariate time series anomaly detection?" *Pattern Recognition* 132:108945 (2022). DOI 10.1016/j.patcog.2022.108945 | 저널 A | opened-전문(초록, Semantic Scholar) | USAD 저자들의 자기 검토 | Elsevier | 인용 가능 |
| E21 | Rewicki, F., Denzler, J., Niebling, J. "Is It Worth It? Comparing Six Deep and Classical Methods for Unsupervised Anomaly Detection in Time Series." *Applied Sciences* 13(3):1778 (2023). DOI 10.3390/app13031778 | 저널(MDPI) A−/주의 | opened-메타(본문 미열람) | MDPI는 심사 품질 편차가 있음 | MDPI는 통상 CC BY(미확인) | 포인터로만 |
| E22 | Saito, T., Rehmsmeier, M. "The Precision-Recall Plot Is More Informative than the ROC Plot When Evaluating Binary Classifiers on Imbalanced Datasets." *PLOS ONE* 10(3):e0118432 (2015). DOI 10.1371/journal.pone.0118432 | 저널 A | opened-메타 | — | PLOS는 통상 CC BY(미확인) | PR 기준선이 유병률이라는 근거 |

### 2.2 방법

| ID | 인용 | 유형·등급 | 확인 | 적신호 | 라이선스/코드 | 사용 위험 |
|---|---|---|---|---|---|---|
| M1 | Jackson, J. E., Mudholkar, G. S. "Control Procedures for Residuals Associated With Principal Component Analysis." *Technometrics* 21(3):341–349 (1979). DOI 10.1080/00401706.1979.10489779 | 저널 A | opened-메타 | — | 유료 | Q(SPE) 한계식은 수식만 인용 |
| M2 | MacGregor, J. F., Kourti, T. "Statistical process control of multivariate processes." *Control Eng. Practice* 3(3):403–414 (1995). DOI 10.1016/0967-0661(95)00014-L | 저널 A | opened-메타 | — | 유료 | 개념 인용 |
| M3 | Qin, S. J. "Statistical process monitoring: basics and beyond." *J. Chemometrics* 17(8–9):480–502 (2003). DOI 10.1002/cem.800 | 저널 A | opened-메타 | — | 유료 | T²/SPE 개관 |
| M4 | Rousseeuw, P. J., Van Driessen, K. "A Fast Algorithm for the Minimum Covariance Determinant Estimator." *Technometrics* 41(3):212–223 (1999). DOI 10.1080/00401706.1999.10485670 | 저널 A | opened-메타 | — | sklearn `MinCovDet` | — |
| M5 | Lowry, C. A., Woodall, W. H., Champ, C. W., Rigdon, S. E. "A Multivariate Exponentially Weighted Moving Average Control Chart." *Technometrics* 34(1):46–53 (1992). DOI 10.1080/00401706.1992.10485232 | 저널 A | opened-메타 | — | — | MEWMA 근거 |
| M6 | Page, E. S. "Continuous Inspection Schemes." *Biometrika* 41(1–2):100–115 (1954). DOI 10.1093/biomet/41.1-2.100 | 저널 A | opened-메타 | — | — | CUSUM 원전 |
| M7 | Lorden, G. "Procedures for Reacting to a Change in Distribution." *Ann. Math. Statist.* 42(6):1897–1908 (1971). DOI 10.1214/aoms/1177693055 | 저널 A | opened-메타 | — | — | 탐지지연 최적성 이론 |
| M8 | Breunig, M. M., Kriegel, H.-P., Ng, R. T., Sander, J. "LOF: Identifying Density-Based Local Outliers." *SIGMOD 2000*, pp. 93–104. DOI 10.1145/342009.335388 | 학회 A | opened-메타 | — | sklearn/PyOD | — |
| M9 | Liu, F. T., Ting, K. M., Zhou, Z.-H. "Isolation Forest." *ICDM 2008*, pp. 413–422. DOI 10.1109/ICDM.2008.17 | 학회 A | opened-메타 | — | sklearn | — |
| M10 | Schölkopf, B., Platt, J. C., Shawe-Taylor, J., Smola, A. J., Williamson, R. C. "Estimating the Support of a High-Dimensional Distribution." *Neural Computation* 13(7):1443–1471 (2001). DOI 10.1162/089976601750264965 | 저널 A | opened-메타 | — | sklearn | — |
| M11 | Goldstein, M., Uchida, S. "A Comparative Evaluation of Unsupervised Anomaly Detection Algorithms for Multivariate Data." *PLOS ONE* 11(4):e0152173 (2016). DOI 10.1371/journal.pone.0152173 | 저널 A | opened-전문 | 표 형식 데이터 기준이며 시계열은 아님 | **CC BY**(PDF 표기 확인) | 그림 재사용도 출처 표기 시 가능 |
| M12 | Han, S., Hu, X., Huang, H., Jiang, M., Zhao, Y. "ADBench: Anomaly Detection Benchmark." *NeurIPS 2022 Datasets & Benchmarks*. arXiv 2206.09426 | 학회 A | opened-전문 | 표 형식 데이터 기준 | 코드 BSD-2-Clause | 인용 가능 |
| M13 | Yeh, C.-C. M. et al. "Matrix Profile I: All Pairs Similarity Joins for Time Series." *ICDM 2016*, pp. 1317–1322. DOI 10.1109/ICDM.2016.0179 | 학회 A | opened-메타 | Keogh 그룹 | — | — |
| M14 | Law, S. M. "STUMPY: A Powerful and Scalable Python Library for Time Series Data Mining." *JOSS* 4(39):1504 (2019). DOI 10.21105/joss.01504 | 소프트웨어 논문 B+ | opened-메타, 코드(`stump.py` docstring) opened | "STUMPY는 TD Ameritrade 상표" 문구 | **BSD-3-Clause**(LICENSE 원문 확인) | — |
| M15 | Truong, C., Oudre, L., Vayatis, N. "Selective review of offline change point detection methods." *Signal Processing* 167:107299 (2020). DOI 10.1016/j.sigpro.2019.107299 | 저널 A | opened-메타 | — | ruptures **BSD-2-Clause** | — |
| M16 | Aminikhanghahi, S., Cook, D. J. "A survey of methods for time series change point detection." *Knowl. Inf. Syst.* 51(2):339–367 (2017). DOI 10.1007/s10115-016-0987-z | 저널 A | opened-메타 | — | — | 포인터 |
| M17 | Malhotra, P. et al. "LSTM-based Encoder-Decoder for Multi-sensor Anomaly Detection." ICML 2016 Anomaly Detection Workshop. arXiv 1607.00148 | 워크숍 B | opened-전문(헤더) | — | — | 가이드북 LSTM-AE의 계보 |
| M18 | Audibert, J. et al. "USAD: UnSupervised Anomaly Detection on Multivariate Time Series." *KDD 2020*, pp. 3395–3404. DOI 10.1145/3394486.3403392 | 학회 A | opened-메타. 코드 LICENSE opened | — | 코드 BSD(EURECOM) | — |
| M19 | Tuli, S., Casale, G., Jennings, N. R. "TranAD: Deep Transformer Networks for Anomaly Detection in Multivariate Time Series Data." *PVLDB* 15(6):1201–1214 (2022). DOI 10.14778/3514061.3514067 | 학회지 A | opened-메타. **코드 opened**(`src/pot.py`의 `pot_eval`이 `adjust_predicts`, 즉 PA 호출) | 평가에 PA 사용 | 코드 BSD-3-Clause | 공식 숫자를 그대로 비교하면 안 됨 |
| M20 | Xu, J., Wu, H., Wang, J., Long, M. "Anomaly Transformer: Time Series Anomaly Detection with Association Discrepancy." *ICLR 2022*(Spotlight). arXiv 2110.02642 | 학회 A | opened-전문 + **코드 opened**(`solver.py`, `data_loader.py`, issue #14) | test 기반 임계값, PA, 일부 로더의 val=test | 코드 MIT | §3.5 참조 |
| M21 | Wu, H. et al. "TimesNet: Temporal 2D-Variation Modeling for General Time Series Analysis." *ICLR 2023*. arXiv 2210.02186 | 학회 A | opened-전문(헤더). TSLib `exp_anomaly_detection.py` opened | TSLib도 같은 임계값·PA 관행 | TSLib MIT | 동일 |
| M22 | Yang, Y., Zhang, C., Zhou, T., Wen, Q., Sun, L. "DCdetector: Dual Attention Contrastive Representation Learning for Time Series Anomaly Detection." *KDD 2023*, pp. 3033–3045. DOI 10.1145/3580305.3599295 | 학회 A | opened-메타. 코드(`solver.py`) opened | 같은 관행 | **저장소에 라이선스 없음** | 코드 복사 금지(기본 저작권) |
| M23 | Goswami, M. et al. "MOMENT: A Family of Open Time-series Foundation Models." *ICML 2024*, PMLR 235:16115–16152. arXiv 2402.03885 | 학회 A | opened-전문 | 사전학습에 이상탐지 데이터 포함 → 오염 위험(E6) | 코드 MIT, HF 가중치 MIT | 입력 길이 512 고정(짧으면 0 패딩) |
| M24 | Ansari, A. F. et al. "Chronos: Learning the Language of Time Series." arXiv 2403.07815v3. README bib상 *TMLR* | 저널 A/B | opened-전문(arXiv). TMLR 게재는 README로만 확인 | — | 코드·가중치 Apache-2.0(chronos-2 포함, HF API) | 학습 문맥 길이 512 |
| M25 | Das, A., Kong, W., Sen, R., Zhou, Y. "A decoder-only foundation model for time-series forecasting" (TimesFM). *ICML 2024*, PMLR 235:10148–10167 | 학회 A | opened-메타(PMLR). README opened | **3.0 가중치 비상업** | 코드 Apache-2.0. 가중치 ≤2.5 Apache-2.0, 3.0 `timesfm-non-commercial-license-v1.0` | 3.0은 사용·동봉 금지 권장 |
| M26 | Woo, G. et al. "Unified Training of Universal Time Series Forecasting Transformers" (Moirai). *ICML 2024*, PMLR 235:53140–53164 | 학회 A | opened-메타(PMLR). HF API | **가중치 CC-BY-NC-4.0** | 코드 uni2ts Apache-2.0 | 상금이 걸린 대회에서 NC 해석이 모호하므로 회피 권장 |
| M27 | Rasul, K. et al. "Lag-Llama: Towards Foundation Models for Probabilistic Time Series Forecasting." arXiv 2310.08278v3 | 프리프린트 B | opened-메타. README opened(학습 문맥 32) | 동료심사 여부 미확인 | 코드·가중치 Apache-2.0 | — |
| M28 | Tautz-Weinert, J., Watson, S. J. "Using SCADA data for wind turbine condition monitoring – a review." *IET Renew. Power Gener.* 11(4):382–394 (2017). DOI 10.1049/iet-rpg.2016.0248 | 저널 A | opened-전문(초록, normal behaviour modelling 범주) | 풍력 분야이므로 유추 적용 | 유료 | 정상거동 모델 근거 |
| M29 | Helwig, N., Pignanelli, E., Schütze, A. "Condition monitoring of a complex hydraulic system using multivariate statistics." *I2MTC 2015*, pp. 210–215. DOI 10.1109/I2MTC.2015.7151267 | 학회 A− | opened-메타 | 시험대(rig) 데이터 | 유료 | 유압 분야에서 단순 통계가 유효하다는 포인터 |
| M30 | Ruff, L. et al. "A Unifying Review of Deep and Shallow Anomaly Detection." *Proc. IEEE* 109(5):756–795 (2021). DOI 10.1109/JPROC.2021.3052449 | 저널 A | opened-메타 | — | — | 포인터 |
| M31 | Blázquez-García, A., Conde, A., Mori, U., Lozano, J. A. "A Review on Outlier/Anomaly Detection in Time Series Data." *ACM CSUR* 54(3):1–33 (2021/2022). DOI 10.1145/3444690 | 저널 A | opened-메타 | — | — | 포인터 |
| M32 | Zamanzadeh Darban, Z., Webb, G. I., Pan, S., Aggarwal, C., Salehi, M. "Deep Learning for Time Series Anomaly Detection: A Survey." *ACM CSUR* 57(1):1–42 (2025). DOI 10.1145/3691338 | 저널 A | opened-메타 | — | — | 포인터 |
| M33 | Christ, M., Braun, N., Neuffer, J., Kempa-Liehr, A. W. "Time Series FeatuRe Extraction on basis of Scalable Hypothesis tests (tsfresh)." *Neurocomputing* 307:72–77 (2018). DOI 10.1016/j.neucom.2018.03.067 | 저널 A | opened-메타 | 특징 폭발로 지름길 특징이 섞일 위험 | **MIT** | — |
| M34 | Lubba, C. H. et al. "catch22: CAnonical Time-series CHaracteristics." *DMKD* 33(6):1821–1852 (2019). DOI 10.1007/s10618-019-00647-x | 저널 A | opened-메타 | — | **GPL-3.0**(catch22, pycatch22) | zip 동봉 시 GPL 의무 |
| M35 | Siffer, A., Fouque, P.-A., Termier, A., Largouet, C. "Anomaly Detection in Streams with Extreme Value Theory" (SPOT). *KDD 2017*, pp. 1067–1075. DOI 10.1145/3097983.3098144 | 학회 A | opened-메타. POT 임계값이 TranAD 코드에 쓰인 것은 확인 | — | — | 극단값 외삽의 근거 |

### 2.3 검증·불확실성·확률화·지름길

| ID | 인용 | 유형·등급 | 확인 | 비고 |
|---|---|---|---|---|
| V1 | Bergmeir, C., Benítez, J. M. "On the use of cross-validation for time series predictor evaluation." *Information Sciences* 191:192–213 (2012). DOI 10.1016/j.ins.2011.12.028 | 저널 A | opened-메타 | 블록 교차검증 |
| V2 | Bergmeir, C., Hyndman, R. J., Koo, B. "A note on the validity of cross-validation for evaluating autoregressive time series prediction." *CSDA* 120:70–83 (2018). DOI 10.1016/j.csda.2017.11.003 | 저널 A | opened-메타 | — |
| V3 | Roberts, D. R. et al. "Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure." *Ecography* 40(8):913–929 (2017). DOI 10.1111/ecog.02881 | 저널 A | opened-메타 | 구조적 블록 CV |
| V4 | Varma, S., Simon, R. "Bias in error estimation when using cross-validation for model selection." *BMC Bioinformatics* 7:91 (2006). DOI 10.1186/1471-2105-7-91 | 저널 A | opened-전문(초록) | 중첩(nested) CV. 오픈액세스 |
| V5 | Cawley, G. C., Talbot, N. L. C. "On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation." *JMLR* 11:2079–2107 (2010) | 저널 A | opened-전문(PDF 헤더, 초록) | — |
| V6 | Kaufman, S., Rosset, S., Perlich, C., Stitelman, O. "Leakage in data mining: Formulation, detection, and avoidance." *ACM TKDD* 6(4):1–21 (2012). DOI 10.1145/2382577.2382579 | 저널 A | opened-메타 | — |
| V7 | Kapoor, S., Narayanan, A. "Leakage and the reproducibility crisis in machine-learning-based science." *Patterns* 4(9):100804 (2023). DOI 10.1016/j.patter.2023.100804 | 저널 A | opened-전문(초록: 누설 8유형 분류, model info sheet) | 8유형의 세부 명칭은 미열람 |
| V8 | Ojala, M., Garriga, G. C. "Permutation Tests for Studying Classifier Performance." *JMLR* 11:1833–1863 (2010) | 저널 A | opened-전문 | sklearn `permutation_test_score` docstring이 이 논문을 인용(코드 확인) |
| V9 | Hurlbert, S. H. "Pseudoreplication and the Design of Ecological Field Experiments." *Ecol. Monogr.* 54(2):187–211 (1984). DOI 10.2307/1942661 | 저널 A | opened-메타 | 가짜 반복 |
| V10 | Field, C. A., Welsh, A. H. "Bootstrapping Clustered Data." *JRSS-B* 69(3):369–390 (2007). DOI 10.1111/j.1467-9868.2007.00593.x | 저널 A | opened-메타 | 군집 부트스트랩 |
| V11 | Künsch, H. R. "The Jackknife and the Bootstrap for General Stationary Observations." *Ann. Statist.* 17(3):1217–1241 (1989). DOI 10.1214/aos/1176347265 | 저널 A | opened-메타(쪽수는 Semantic Scholar) | 블록 부트스트랩 |
| V12 | Politis, D. N., Romano, J. P. "The Stationary Bootstrap." *JASA* 89(428):1303–1313 (1994). DOI 10.1080/01621459.1994.10476870 | 저널 A | opened-메타 | — |
| V13 | Hanley, J. A., Lippman-Hand, A. "If nothing goes wrong, is everything all right? Interpreting zero numerators." *JAMA* 249(13):1743–1745 (1983). DOI 10.1001/jama.1983.03330370053031 | 저널 A | opened-메타(Crossref는 1저자만, Semantic Scholar는 2저자와 1743–5) | "rule of three" |
| V14 | Bates, S., Candès, E., Lei, L., Romano, Y., Sesia, M. "Testing for outliers with conformal p-values." *Ann. Statist.* 51(1):149–178 (2023). DOI 10.1214/22-AOS2244. arXiv 2104.08279 | 저널 A | opened-전문(초록) | 주변 타당 p값, FDR, FPR 균일 신뢰한계 |
| V15 | Laxhammar, R., Falkman, G. "Inductive conformal anomaly detection for sequential detection of anomalous sub-trajectories." *Ann. Math. Artif. Intell.* 74(1–2):67–94 (2015). DOI 10.1007/s10472-013-9381-7 | 저널 A | opened-메타 | 순차 conformal |
| V16 | Kriegel, H.-P., Kröger, P., Schubert, E., Zimek, A. "Interpreting and Unifying Outlier Scores." *SDM 2011*, pp. 13–24. DOI 10.1137/1.9781611972818.2 | 학회 A | opened-메타. PyOD `predict_proba(method='unify')`가 이 논문을 인용하는 것을 코드에서 확인 | 점수 변환 |
| V17 | Perini, L., Vercruyssen, V., Davis, J. "Quantifying the Confidence of Anomaly Detectors in Their Example-Wise Predictions." *ECML PKDD 2020*, LNCS, pp. 227–243 (2021). DOI 10.1007/978-3-030-67664-3_14 | 학회 A | opened-메타. PyOD `predict_confidence`가 인용(코드 확인) | ExCeeD |
| V18 | Niculescu-Mizil, A., Caruana, R. "Predicting good probabilities with supervised learning." *ICML 2005*, pp. 625–632. DOI 10.1145/1102351.1102430 | 학회 A | opened-메타 | 지도 보정 |
| V19 | Zadrozny, B., Elkan, C. "Transforming classifier scores into accurate multiclass probability estimates." *KDD 2002*, pp. 694–699. DOI 10.1145/775047.775151 | 학회 A | opened-메타 | isotonic |
| V20 | Geirhos, R. et al. "Shortcut learning in deep neural networks." *Nat. Mach. Intell.* 2(11):665–673 (2020). DOI 10.1038/s42256-020-00257-z | 저널 A | opened-메타 | 지름길 학습 |
| V21 | DeGrave, A. J., Janizek, J. D., Lee, S.-I. "AI for radiographic COVID-19 detection selects shortcuts over signal." *Nat. Mach. Intell.* 3(7):610–619 (2021). DOI 10.1038/s42256-021-00338-7 | 저널 A | opened-메타 | 출처 교란의 실사례 |
| V22 | Lapuschkin, S. et al. "Unmasking Clever Hans predictors and assessing what machines really learn." *Nat. Commun.* 10 (2019). DOI 10.1038/s41467-019-08987-4 | 저널 A | opened-메타(article 번호 미확인) | — |
| V23 | Lipsitch, M., Tchetgen Tchetgen, E., Cohen, T. "Negative Controls: A Tool for Detecting Confounding and Bias in Observational Studies." *Epidemiology* 21(3):383–388 (2010). DOI 10.1097/EDE.0b013e3181d61eeb | 저널 A | opened-메타(Crossref 제목 "Negative Controls") | 음성 대조 |

V1–V23 모두 라이선스는 해당 없음(인용만)이며, 그림은 재사용하지 않습니다.

### 2.4 소프트웨어와 모델 가중치 라이선스

확인 경로는 GitHub REST API(`gh api repos/...`)의 `license.spdx_id`, 표준이 아닌 경우 LICENSE 원문, PyPI JSON, Hugging Face `api/models`입니다. 모두 2026-10-01에 확인했고 상태는 모두 opened입니다.

| ID | 패키지/저장소 | 정확한 라이선스 | 비고·위험 |
|---|---|---|---|
| L1 | scikit-learn | BSD-3-Clause | `permutation_test_score`(Ojala & Garriga 인용), `TimeSeriesSplit(gap=…)`, `GroupKFold`, `LeaveOneGroupOut`, `MinCovDet` 존재를 코드에서 확인 |
| L2 | PyOD | BSD-2-Clause | `predict_proba(method='linear'/'unify')`, `predict_confidence`(ExCeeD) |
| L3 | STUMPY | BSD-3-Clause(원문: "Copyright 2019 TD Ameritrade … 3-Clause BSD") | 기본 `normalize=True`(z-정규화). `normalize=False`이면 `aamp`(비정규화). `stump.py` docstring과 주석상 NaN/inf를 포함한 부분열은 별도로 처리됨(거리 계산 생략으로 이해. 실제 동작은 사용 전 소규모 시험으로 확인할 것) |
| L4 | ruptures | BSD-2-Clause | — |
| L5 | tsfresh | MIT | — |
| L6 | sktime | BSD-3-Clause | — |
| L7 | Merlion(salesforce) | BSD-3-Clause | **저장소 archived**(유지보수 중단 위험) |
| L8 | Darts | Apache-2.0 | — |
| L9 | TSB-AD / TSB-UAD | Apache-2.0 / Apache-2.0 | PyPI `TSB-AD` 1.5도 Apache-2.0. 동봉 데이터는 원 라이선스를 따름 |
| L10 | VUS(TheDatumOrg/VUS) | **GitHub 저장소: LICENSE 없음**. PyPI `vus` 0.0.6: Apache-2.0 표기 | 불일치. PyPI 설치본만 쓰거나 TSB-AD의 구현을 쓰는 편이 안전 |
| L11 | statsmodels | BSD-3-Clause | — |
| L12 | PyTorch | BSD 계열(저장소 LICENSE "From PyTorch: Copyright (c) 2016- Facebook…") | PyPI `torch` 2.14.1의 license_expression은 번들 구성요소 때문에 Apache-2.0, BSD, MIT, BSL-1.0 등이 섞여 있음 |
| L13 | TensorFlow | Apache-2.0 | — |
| L14 | NAB | MIT(2024-12-03부터). **AGPL-3.0(2015-08-10~2024-12-03)** | 옛 포크나 복사본 주의 |
| L15 | TimeEval / GutenTAG | MIT / MIT | TimeEval-algorithms 저장소는 최상위 LICENSE 없음(알고리즘별 상이) |
| L16 | Anomaly-Transformer / Time-Series-Library | MIT / MIT | — |
| L17 | TranAD / USAD / DCdetector | BSD-3-Clause / BSD(EURECOM) / **라이선스 없음** | DCdetector 코드 복사 금지 |
| L18 | MOMENT(코드·HF 가중치 MOMENT-1-small/large) | MIT / MIT | — |
| L19 | Chronos(코드, chronos-t5-small, chronos-bolt-small, chronos-2) | Apache-2.0(모두) | — |
| L20 | TimesFM | 코드 Apache-2.0. 가중치 1.0-200m, 2.0-500m, 2.5-200m은 Apache-2.0. **3.0: timesfm-non-commercial-license-v1.0** | 3.0 사용 금지 권장 |
| L21 | Moirai(uni2ts) | 코드 Apache-2.0. **가중치 1.0-R, 1.1-R, 2.0-R, MoE 모두 CC-BY-NC-4.0** | 회피 |
| L22 | Lag-Llama / Granite TTM-r2 / Timer-base-84m / Toto-Open-Base-1.0 / TimeMoE-50M | 모두 Apache-2.0(HF) | Timer 코드 저장소는 MIT |
| L23 | alibi-detect | **Business Source License 1.1**(PyPI 0.13.0 동일) | 오픈소스 아님. "non-production use" 조건. 회피 |
| L24 | ADTK | MPL-2.0 | 파일 단위 약한 copyleft. 수정 시 해당 파일 공개 의무 |
| L25 | catch22 / pycatch22 | GPL-3.0 | zip 동봉이나 결합 배포 시 GPL 의무 |
| L26 | hctsa | CC BY-NC-SA 4.0 + 개별 특징 GPL-3.0 | 회피(MATLAB) |
| L27 | saxpy / twitter AnomalyDetection | GPL-2.0 / GPL-3.0(archived) | 회피 |
| L28 | River, tslearn, pyts, MAPIE, hmmlearn, DeepOD | BSD-3 / BSD-2 / BSD-3 / BSD-3 / BSD-3 / BSD-2 | — |
| L29 | Kats, Orion, OmniAnomaly, DeepADoTS, TaPR, affiliation-metrics-py, TCPDBench, mvts-ano-eval | MIT(모두) | — |
| L30 | GluonTS, NeuralForecast, TODS, luminaire, luminol, granite-tsfm, Toto | Apache-2.0(모두) | — |
| L31 | telemanom | BSD-3 유사(Caltech 저작권 고지) | — |
| L32 | PyPI `prts`(range-based P/R 구현) | "Other/Proprietary License"(PyPI 분류). 원문 미확인 | 사용하려면 원문 확인. 아니면 직접 구현 |
| L33 | rkillick/changepoint(R) | GitHub API로는 라이선스 감지 안 됨(CRAN 표기 미확인) | 쓸 일이 없으면 무시 |
| L34 | numpy / scipy / pandas / matplotlib / LightGBM / XGBoost / SHAP / Lightning / transformers | BSD-3(+번들) / BSD-3 / BSD-3 / matplotlib License(PSF 기반) / MIT / Apache-2.0 / MIT / Apache-2.0 / Apache-2.0 | — |

---

## 3. 세부 내용과 계획 활용

### 3.1 [R3 점검] 평가와 관련해 데이터에서 바로 확인한 사실

| 항목 | 값 | 함의 |
|---|---|---|
| 정상 파일 | 20,000행, 버스트 599개(10샘플 이상 530개). 벽시계 1:16:55.8(1.282 h), 실제 샘플 시간 33.3분. 버스트 길이 중앙값 37(50샘플 202개). 간격 1.54–16.64 s(중앙값 4.22) | FA율은 **벽시계 시간당**과 **100버스트당**을 함께 보고(가동률 약 43%) |
| 이상 파일 | 600행, 버스트 21개(10샘플 이상 17개), 165.6 s. 간격 1.78–8.57 s(중앙값 5.35) | 이상 쪽 실효 표본은 에피소드 1개 |
| 상수 "모두 정상" 정확도 | 20000/20600 = **97.087%** | 가이드북 정확도(97.51%)와 비교할 때 기준이 되는 값. 단, 가이드북의 시험 분할 비율은 모름 |
| 행 단위 one-liner `|AI0|>0.352` | 이상 행의 27% 표시. 첫 경보는 **두 번째 행(0.1 s)** | "조기" 경쟁은 무의미할 정도로 쉬움 |
| 버스트 one-liner `max|AI0| > 학습 폴드 최대` | 연속 블록 5겹에서 정상 FA **1/599**. 이상 **18/21**. 첫 경보는 버스트 #0(4샘플, 0.3 s) | Wu & Keogh식 triviality |
| 버스트 AUC(10샘플 이상) | AI0 std 0.825, AI1 std 0.839, max|AI0| 0.844, AI1 우세주파수 0.990, **전류 lag-1 AC 1.000, 전류 우세주파수 1.000** | 진폭보다 "동역학" 특징이 더 잘 가름 → 지름길 의심 |
| 전류 동역학 | 정상: 우세 0.596 Hz(중앙값), AC1 0.928 ≈ cos(2π·0.6·0.1) = 0.930(깨끗한 에일리어싱 정현파와 일치). 이상: 우세 ≈0.2 Hz, AC1 0.38. 0.2 Hz 단일 정현파라면 AC1은 0.992여야 하므로 **광대역이나 불규칙 성분이 섞임**. 이상 파일 전류 평균은 57.3(정상 1.4) | 고장(압력 불안정 → 부하 요동)인지 측정·운전 차이인지 판정 불가. 50샘플 버스트의 주파수 분해능은 0.2 Hz이므로 "0.2 Hz"는 분해능 바닥 |
| 진동 우세주파수(정상) | AI0 ≈ 3.57 Hz ≈ 6×전류 에일리어스, AI1 ≈ 1.80 Hz ≈ 3×. 이상 파일에서는 이 관계가 깨짐(AI0 0.54 Hz, AI1 0.29 Hz) | 진동의 에일리어싱 선도 날짜나 조건에 묶여 있을 수 있음. 물리 해석은 R1/R2에 넘김 |
| 음성 대조 | 정상 전반부 대 후반부 AUC 0.50–0.61 | 야간 내 표류는 작음. 단 **다른 날의 정상**은 관측 불가 |
| "조용한" 이상 버스트 | #3(n=31, AI0 std 0.029), #19(n=10, 0.028), #20(n=15, 0.022). 정상 중앙값은 0.070 | 진폭 기반 FN이 집중됨. 라벨 의미 점검 필요 |
| 간이 탐지기 비교(연속 5겹, 임계값 = 내부 보정 블록 점수의 99.5% 분위) | MCD-Mahalanobis: FA 6/530(4.7/h), 이상 17/17. kNN(k=5): 7/530(5.5/h), 17/17. iForest: 23/530(17.9/h), 16/17. max|AI0|: 4/530(3.1/h), 14/17 | 단순 방법 사이에도 FA율 차이가 큼 → **FA가 승부처** |
| 지름길 특징 하나(전류 AC1)만으로 | MCD, kNN 모두 FA 4/530(3.1/h), 이상 16/17. iForest는 0/17(훈련 범위 밖에서 점수가 포화된다고 추정. 문헌으로 확인하지 않음) | "성능 좋음"이 고장 신호라는 증거가 되지 못함 |
| 지속성 규칙 | MCD 단일 버스트 경보 6건 → 2-of-3 규칙 적용 시 경보 개시 1건 | FA–지연 절충 곡선을 보고 |
| 부하 결합 | corr(log s1, log sc) = **0.94**. corr(log s0, log s1) = 0.77. corr(log s0, log sc) = 0.69 | 정상 변동의 상당 부분이 부하(전류)로 설명됨 |
| 정상거동 잔차(공변량 log 전류 std) | AI1 잔차 SD 0.590 → 0.197. 합성 ×1.5/×2/×3 검출률: 잔차 16%/70%/99%, 고정 임계 29%/42%/54%. 이상 버스트 17/17(AI1), 14/17(AI0) | 오경보를 줄이고 민감도를 높이는 핵심 수단 |
| 공변량에 max|I| 추가 | AI1 잔차 SD 0.167로 더 작지만 이상 검출은 **5/17** | 이상 파일의 전류 파형 차이(DC 오프셋)를 끌어들이는 공변량은 위험 |
| 다변량 omnibus 둔감성(6특징 MCD) | 두 진동 채널 동시 ×2 → 1%, ×3 → 28%, ×5 → 99%. AI0만 ×3 → 2% | 방향성(단측) 물리 통계를 따로 감시해야 함 |
| 블록 순위 검정 | 166 s 정상 블록 K=28. 이상의 AI0 std 중앙값 0.395, 정상 블록 최대 0.085 → p = 1/29 = 0.034(최소값). 전류 AC1도 p = 0.034 | 유의성으로는 고장과 세션을 구분하지 못함 |
| 버스트 간 자기상관 | log AI0 std의 lag 1/2/5/10 = 0.33/0.36/0.41/0.35 | i.i.d. 부트스트랩은 과신. 블록(약 10버스트 이상) 단위로 |
| 짧은 버스트(<10샘플) | 정상 69/599, 이상 4/21 | 최소 길이 규칙이 지연에 영향(0.3 s → 13.7 s) |
| 운영 FA 목표 환산 | 7.79 버스트/분이므로 "1 FA/교대(8 h)"는 버스트당 α ≈ 2.7×10⁻⁴, "1 FA/h"는 2.1×10⁻³ | 정상 버스트 530–599개로는 α < 10⁻³을 경험적으로 보정할 수 없음 |

### 3.2 이상 에피소드가 하나일 때 평가가 말할 수 있는 것: 원칙

- **P1. 주장의 범위를 미리 정합니다.**
  - 말할 수 있는 것: "이 에피소드는 같은 길이의 모든 정상 블록보다 극단적이다", "정상 야간 데이터에서 FA율은 x/h(CI …)이다", "이 에피소드를 첫 이상 샘플 후 t초에 잡았다".
  - 말할 수 없는 것: "다른 고장을 잡는다", "고장 전에 미리 경보한다", "통계적으로 유의하게 고장을 판별한다".
  - 근거: E1의 run-to-failure와 mislabel 논의, E6의 single-anomaly bias, V9 가짜 반복, [R3 점검] 블록 순위 검정.
- **P2. 이상 데이터는 한 번만 봅니다(최종 시험).**
  - 하이퍼파라미터, 특징, 임계값은 정상 데이터의 내부 분할로만 정합니다(V4, V5 중첩 검증).
  - 이상을 보고 고른 설정은 "oracle/사후" 행으로 따로 표기합니다. E2가 지적한 "best-F1 임계값" 관행을 피하기 위함입니다.
- **P3. 정상 쪽이 주 증거입니다.** 연속 블록 교차검증(V1, V3)으로 FA율을 추정하고 Poisson 정확 CI와 rule of three(V13)를 붙입니다.
- **P4. 사소한 기준선과 지름길 탐침을 같은 표에 둡니다**(§3.3). 근거는 E1, E2, E7, V20–V22입니다.
- **P5. 지표는 사용 맥락(조기경보·오경보)에 맞춥니다.** 사건 지연, 시간당 FA, 지속성 규칙을 씁니다. PA-F1과 정확도는 금지합니다.
- **P6. 불확실성은 단위별로 보고합니다.** 행이 아니라 버스트, 블록, 에피소드 단위입니다. 이상 쪽 CI는 "에피소드 내부 변동만 반영"한다고 명시합니다.

### 3.3 반드시 보고할 사소한 기준선(trivial baselines)과 탐침

| 코드 | 기준선 | 근거 | 우리 데이터에서 기대되는 결과·용도 |
|---|---|---|---|
| B0 | 상수 "모두 정상" | 상식. E1 | 정확도 97.087%, F1 0. 정확도를 쓰면 안 되는 이유를 보여줌 |
| B1 | 무작위 점수(균등분포). PA를 적용한 경우와 안 한 경우 | E2(Case 1), E7("Random") | PA를 쓰면 높게 나오는 것을 보여줘 PA 금지의 근거로 삼음. 표에는 PA 없는 값만 |
| B2 | 센서 범위 이탈: 정상 학습 min/max 밖이면 1 | E7 "Sensor range deviation" | "최소한 넘어야 할 기준" |
| B3 | 입력 크기 자체를 점수로: 행 L2-norm 또는 버스트 RMS | E2 Case 2("input itself"), E7 "L2-norm" | 진폭 이상이므로 강할 것 |
| B4 | One-liner: `max|AI0|` 또는 `std(AI0)` 임계값 | E1 정의 1 | §3.1 결과. 탐지는 거의 완벽 |
| B5 | 1-NN 거리(정상 학습 대비) | E7, M11, M23(UCR에서 kNN이 VUS-ROC로 근소 우위) | 강력한 비모수 기준선 |
| B6 | PCA 재구성오차 = SPE/Q 통계 | E7, E19, M1 | E7에서 PCA Error가 Anomaly Transformer보다 F1과 F1T가 높았음 |
| B7 | Shewhart / 3σ, 버스트 RMS 관리도(단측) | M2, M3, M6 | 현장 해석이 가장 쉬움 |
| B8 | 가이드북 LSTM-AE(공식 기준선)와 **같은 구조의 미학습(무작위 가중치) LSTM-AE** | E2 Case 3(단층 LSTM 오토인코더 미학습) | 학습 효과를 분리. 미학습 모델도 상당한 점수를 낼 수 있음 |
| P1 | 누설 탐침: `TimeStamp`(날짜·시각)만, `Unnamed: 0`(행 번호)만 쓰는 분류기 | V6, V7 | 날짜는 AUC 1.0. 입력에서 반드시 제외했음을 증명하는 용도 |
| P2 | 지름길 탐침: 전류 버스트 내 AC1이나 우세주파수만 쓰는 탐지기 | V20–V22, [R3 점검] | AUC 1.000. "이만큼은 고장 신호가 아닐 수도 있다"는 상한선 |
| P3 | 음성 대조: 정상 전반부 대 후반부 판별 | V23 | AUC 0.5–0.6이면 야간 표류가 작음을 보임 |
| P4 | 시간 순서 파괴 대조: 버스트 내 샘플 순서를 섞은 입력으로 시계열 모델(LSTM-AE 등) 재평가 | V8 Test 2의 발상을 시간축에 응용(우리 제안, 문헌 직접 근거 없음) | 성능이 유지되면 진폭 의존, 무너지면 동역학(지름길 후보) 의존 |

### 3.4 지표 설계(권장, 보조, 금지)

**주 지표(표 첫 열에 둠)**

1. **정상 보류 FA**
   - 연속 블록 교차검증(예: 5겹, 또는 166 s 블록 28개로 leave-one-block-out). 블록 경계에 1버스트 이상 퍼지(gap)를 둡니다(sklearn `TimeSeriesSplit(gap=…)`나 그룹 분할).
   - 보고: 경보 **개시** 수, FA/h(벽시계), FA/100버스트, Poisson 정확 95% CI.
   - [R3 점검] 0건 → 단측 상한 2.34/h, 4건 → 3.12/h [0.85, 7.99], 6건 → 4.68/h [1.72, 10.19].
2. **에피소드 탐지와 첫 경보 시간**
   - t₀ = 첫 이상 샘플(2022-07-17 10:51:07.943). 지연은 판정에 필요한 마지막 샘플 시각에서 t₀를 뺀 값입니다. 버스트 특징이면 버스트 끝 시각입니다.
   - 초와 버스트 수로 함께 보고합니다. 버스트 사이 공백 때문에 지연이 계단 형태가 되므로 이를 명시합니다.
   - E14(SR-CNN)의 "시작 후 k점 이내 탐지만 인정" 규칙을 참고해 허용 지연 k(예: 2버스트)를 사전에 정해 두는 것도 좋습니다.
3. **버스트 단위 재현율과 FN 목록**
   - 21개 또는 17개 중 몇 개인지와 CP 구간을 보고하되, 군집이 하나라는 단서를 붙입니다.
   - FN 버스트의 특성(진폭·전류 수준)을 표로 정리합니다. 이것이 FN 조건 분석의 핵심입니다.

**보조 지표**

- 임계값과 무관한 **버스트 단위 AUC-PR**. 무작위 기준선은 유병률(버스트 21/620 = 3.4%, 행 600/20,600 = 2.9%)입니다(E22). AUC-ROC도 함께 둡니다.
- **VUS-PR**: 문헌 비교용. E6이 "the most reliable"로 권장합니다. TSB-AD 패키지(Apache-2.0)로 계산할 수 있습니다. 다만 이상이 별도 파일이라 "정상 보류 블록 + 이상 에피소드"를 이어 붙인 인공 타임라인에서 계산하며, 그 사실을 명시합니다.
- **FA/h 대 지연 곡선**(임계값 × 지속성 규칙 격자): AMOC의 발상(E17, 내용 미검증)이며 SPC의 ARL0/ARL1 대응(M6, M7)입니다. 현장 판단에 가장 직접적인 그림입니다.
- **민감도(심각도) 스윕**: 보류 정상 버스트의 진동 진폭을 s배(1.2–5)로 합성 증폭하고, 고정 FA 임계에서 검출률을 봅니다. "최소 검출 가능 변화"를 제시하는 용도이며, "조기" 탐지 역량의 대리 지표입니다. 실제 고장이 아님을 명시합니다.

**금지하거나 주석을 붙여야 하는 것**

- PA-F1(E2, E7, E19). 쓰더라도 PA%K 곡선 아래 면적(E2)과 PA 없는 F1을 병기해야 합니다. 하지만 우리 경우 굳이 쓸 이유가 없습니다.
- 시험 데이터 기반 임계값(best-F1, test 분위수).
- 정확도.
- 무작위 행 분할이나 겹치는 창 분할(누설).
- **사건 단위 지표(event-wise F1, composite F1(E11), range-based P/R(E8), NAB(E9))는 사건이 하나라 재현율이 0 또는 1로 퇴화합니다.** 정의만 소개하고 수치는 위의 주 지표로 대신합니다.
- Affiliation-F(E12)는 E6 슬라이드에서 무작위 점수에 0.70을 줄 만큼 관대하므로 쓰지 않습니다.

**보고표 템플릿(제안)**

| 모델 | 특징군 | FA/h [95% CI] | FA/100버스트 | 에피소드 탐지 | 첫 경보(s, 버스트) | 이상 버스트 재현 x/21 | AUC-PR(버스트) | 지름길 절제 후 변화 | 비고(임계값 결정 데이터) |
|---|---|---|---|---|---|---|---|---|---|

### 3.5 Anomaly Transformer류 평가의 알려진 실패 양상(코드로 확인)

1. **시험 점수로 임계값 결정**: `thuml/Anomaly-Transformer/solver.py` 286–288행입니다.
   ```
   test_energy = np.array(attens_energy)
   combined_energy = np.concatenate([train_energy, test_energy], axis=0)
   thresh = np.percentile(combined_energy, 100 - self.anormly_ratio)
   ```
   - 여기서 `thre_loader`는 test 창을 순회합니다(`data_loader.py`의 else 분기).
   - 논문 본문은 "validation dataset"의 비율 r(SWaT 0.1%, SMD 0.5%, 그 외 1%)로 정한다고 쓰지만, 코드의 실제 동작은 train과 test를 합친 분위수입니다.
2. **검증 = 시험**: `data_loader.py`의 PSM, MSL, SMAP 로더에서 `self.val = self.test`입니다. SMD만 train의 마지막 20%를 씁니다.
3. **Point adjustment**: `solver.py` 338행 이후 "detection adjustment"가 있습니다. 저자들은 issue #14에서 "abnormal event detection" 프로토콜이라고 해명했습니다. 이 프로토콜에서는 무작위 점수도 높은 점수를 받습니다(E2, E7).
4. **같은 관행의 전파**
   - Time-Series-Library `exp/exp_anomaly_detection.py` 171–186행(combined_energy 분위수 + `adjustment`). TimesNet 등 TSLib의 모든 이상탐지 결과가 해당됩니다.
   - DCdetector `solver.py` 260–262행 + 309행 이후.
   - TranAD `pot_eval`은 `adjust_predicts`(PA)를 씁니다.
5. **벤치마크 자체의 결함**: SMD, MSL, SMAP 등은 E1이 "abandon"을 권고한 데이터 계열입니다.
6. **단순 기준선에 패배**: E7 Table 2에서 Random의 F1PA(SWaT)는 0.963으로 Anomaly Transformer(0.941)보다 높습니다. PA 없는 F1에서는 PCA Error 0.833이 AT 0.765보다 높고, F1T는 0.574 대 0.331입니다. SMD의 F1도 0.572 대 0.426입니다.

**우리 계획에 주는 함의**

- 이 계열 모델을 쓴다면 공식 평가 코드를 쓰지 말고 §3.4 프로토콜로 다시 평가해야 합니다.
- 버스트 ≤50샘플, 학습 시퀀스 약 600개라는 규모에서는 주 모델로 권장하지 않습니다.
- "최신 모델을 써 봤으나 정직한 프로토콜에서는 단순 모델보다 낫지 않았다"는 비교 서술은 오히려 평가 항목(모델 비교·정당화)에 유리할 수 있습니다.

### 3.6 방법 계열 평가: 증거와 우리 데이터 적합성

| 계열 | 증거 요약 | 우리 데이터 적합성 | 권장 역할 | 주의점 |
|---|---|---|---|---|
| **SPC/통계**: T²(Mahalanobis), SPE/Q(PCA), MCD, MEWMA, CUSUM | 오래 검증된 공정감시 방법(M1–M7). E6에서 Sub-PCA가 TSB-AD-U 1위, PCA가 TSB-AD-M 3위. E7에서 PCA Error가 최상위권 | 버스트 특징 약 6–12개, 표본 530–599 → 공분산 추정 가능. 관리한계와 ARL 개념이 현장에 친숙 | **주력 후보.** 특히 부하 조건부 잔차의 단측 관리도(CUSUM/EWMA) | MCD는 정상이 다봉(부하 상태)일 때 소수 상태를 이상으로 취급. [R3 점검]에서 omnibus 거리는 단일 방향 변화에 둔감 |
| **거리/밀도**: kNN, LOF | M11: 전역 이상에는 k-NN, 지역 이상에는 LOF. E5: KNN이 "robust and effective". M23: UCR에서 kNN이 VUS-ROC 근소 우위 | 특징 표준화만 하면 됨 | **주력 비교 모델**(1-NN과 k-NN) | LOF는 전역 이상에서 FP가 많을 수 있음(M11) |
| **Isolation Forest** | 범용 기준선(M9). ADBench에서 다른 비지도 방법과 통계적 차이 없음(M12) | 가능 | 비교용 | [R3 점검] FA가 가장 많음(17.9/h). 1차원 범위 밖 값의 점수 포화가 의심됨(가설) |
| **OCSVM** | M10. E6 TSB-AD-M 10위 | 이상 없이 ν와 γ를 정해야 함 | 선택 | 하이퍼파라미터를 고를 신호가 없음 |
| **행렬 프로필**(STUMPY) | M13. E1은 discord가 deep 모델과 대등한 사례를 제시 | 부분열 길이 m < 50, 버스트 사이 NaN 구분자 필요. **기본 z-정규화는 진폭 변화를 지움** → `normalize=False` | 보조(형태 이상 탐색) | 이상 파일을 정상에 AB-join하는 것은 결국 부분열 1-NN 거리와 같음 |
| **변화점**(ruptures, CUSUM) | M15, M16. E18: "zero"(무변화) 기준선을 어떤 방법도 유의하게 이기지 못함(Default 실험) | 정상과 이상이 별도 파일이므로 둘 사이 변화점은 사소함 | **정상 야간 안의 운전 상태 전환 찾기**(FP 조건 분석용). 온라인 CUSUM은 경보 로직에 사용 | 기본 설정에서 FP가 많음(E18) |
| **예측 잔차**(AR/ARIMA/상태공간) | E5: 예측 계열이 패턴·주파수 이상에 강함 | 버스트 내 ≤49 문맥, 공백 때문에 버스트를 넘는 문맥 없음 | 신중히 | **버스트 내 AR 구조가 곧 지름길 특징(전류 AC1, 에일리어싱 주파수)**이라 예측 잔차가 날짜 차이를 잡을 위험 |
| **딥러닝**: LSTM-AE, USAD, TranAD, Anomaly Transformer, TimesNet, DCdetector | E6 "simpler architectures… often yield better performance". E7 "SOTA deep models effectively learn linear mappings". E20 "no family outperforms". E5 RI11: 재구성 계열 다수가 AUC-ROC 약 0.5 | 학습 시퀀스 약 600, 창 ≤50 | **LSTM-AE만** 가이드북 기준선 + 미학습판(B8) | 공식 평가 코드의 PA와 test 임계값(§3.5). 시간 순서 의존 → P4 탐침 필수 |
| **파운데이션 모델**: MOMENT, Chronos, TimesFM, Moirai, Lag-Llama | E6: FM이 점 이상에 강하고 연속(sequence) 이상에 약함. 오염 위험. M23: MOMENT 입력 512 고정(짧으면 0 패딩) | 버스트 ≤50 → 입력의 약 90%가 패딩. Chronos 학습 문맥 512, Lag-Llama 학습 문맥 32(README) | 창의성 항목용 **부록 실험**까지만 | 라이선스(Moirai NC, TimesFM 3.0 NC). 가중치 크기(zip 용량). 오프라인 재현성 |
| **지도/준지도**(GBM 등) | M12: 1% 라벨만으로도 준지도가 최고 비지도를 이김(표 형식 데이터 기준) | 이상 라벨은 에피소드 1개뿐 → 일반화 검증 불가 | "확률 모델" 비교용. 반드시 낙관적 상한으로 표기 | 버스트 단위 LOO는 가짜 반복(V9). 에피소드 안에서 앞쪽으로 학습하고 뒤쪽으로 시험하는 전진 분할만 허용 |

**~20k 행에서 현실적인 것**

- 학습 단위는 행이 아니라 **버스트(약 530–599)**입니다. 모델 자유도는 이보다 훨씬 작아야 합니다.
- 버스트 특징(채널별 RMS/표준편차, 최대 절대값, 파고율, 채널 간 비율과 상관, 전류 RMS 조건부 잔차) 위에 저자유도 탐지기를 두는 구성이 증거와 데이터 양에 모두 맞습니다.
- 위상이나 에일리어싱에 의존하는 특징(우세주파수, AC1)은 "지름길 후보군"으로 분리해 절제 실험에만 씁니다.

### 3.7 단일 에피소드용 검증 설계(구체안)

1. **분할**
   - 정상은 시간 순서대로 연속 블록 K개로 나눕니다(예: 5겹, 또는 이상 길이와 같은 166 s 블록 28개). 블록 사이에 1버스트 이상 퍼지를 둡니다.
   - 블록 내부 자기상관(버스트 간 lag-10까지 약 0.35)을 고려하면 무작위 버스트 분할은 금지입니다(V1–V3).
2. **중첩 선택**: 바깥 루프의 시험 블록을 뺀 학습 블록 안에서 다시 "적합 블록과 보정 블록"으로 나눠 하이퍼파라미터와 임계값을 정합니다(V4, V5). 이상 파일은 바깥 루프가 끝난 뒤 최종 모델에 한 번만 적용합니다.
3. **지도 모델(선택)**
   - 이상 21버스트를 시간 순서대로 앞 k개는 학습, 뒤는 시험으로 씁니다(전진 분할).
   - 버스트 단위 leave-one-out은 가짜 반복이라 금지합니다(V9).
   - 결과는 "같은 에피소드 내부 외삽"의 낙관적 상한임을 명시합니다.
4. **순열 검정과 블록 순위 검정**
   - 행이나 버스트 단위 라벨 순열(V8 Test 1)은 의존성과 교란 때문에 무효입니다. p가 거의 0으로 나와 오해를 부릅니다.
   - 대안은 **블록 순위 검정**입니다. 이상 에피소드의 통계(점수 중앙값 등)가 같은 길이 정상 블록 K개 중 몇 위인지 보고, p = (1 + #{정상 ≥ 이상})/(K+1)로 계산합니다(최소 1/(K+1)).
   - 같은 검정을 지름길 통계에도 적용해, 둘 다 최소 p라면 "고장 대 세션"을 가를 수 없다고 명시합니다([R3 점검] 둘 다 0.034).
   - 세션 단위로 보면 정상 세션 1개 대 이상 세션 1개이므로 정확 순열 p의 하한은 1/2입니다. 판별의 통계적 유의성은 원리적으로 주장할 수 없습니다.
5. **신뢰구간**
   - FA: Poisson 정확 구간(경보 개시 단위). 0건이면 rule of three(V13).
   - 버스트 재현율: CP 구간에 "군집 1개" 주석. 예: 21/21 → [0.839, 1], 18/21 → [0.637, 0.970]. 이 구간은 에피소드 사이 변동을 반영하지 못합니다.
   - 정상 쪽 지표의 변동: 이동 블록이나 정상 부트스트랩(V11, V12), 블록 길이 ≥10버스트.
   - 군집 부트스트랩(V10)은 이상 쪽 군집이 1개라 의미가 없습니다.
6. **음성 대조와 지름길 절제**: §3.3의 P1–P4를 실행합니다. 주 모델은 **진폭·부하 조건부 특징만**으로 성능을 보고하고, 동역학 특징을 더했을 때의 증분은 따로 보고합니다.
7. **조기성**: 첫 경보 시간, FA/h–지연 곡선(지속성 규칙 1-of-1, 2-of-3, 3-of-5 등), 합성 심각도 스윕을 보고합니다. 예지 리드타임 주장은 금지합니다.
8. **운영 FA 목표와 임계값**
   - 버스트당 α ≈ 10⁻³ 아래는 정상 표본 수 때문에 경험적 분위수로 보정할 수 없습니다. conformal p의 최소값은 1/(n_cal+1)입니다.
   - 대안
     - 지속성 규칙
     - EVT/POT 꼬리 외삽(M35. TranAD 코드에서 POT 사용을 확인)
     - 목표 FA를 현실적으로 정의하고 "이 데이터로 입증 가능한 FA 하한은 약 2–3/h"라고 명시
9. **확률 출력**
   - 정상 보정 블록으로 conformal p-value를 만들고 "이상 정도 = 1 − p"로 제시합니다(V14). 주변 타당성 P(p ≤ α) ≤ α는 교환가능성 가정 아래에서만 성립하며, 시계열이라 근사입니다. V14의 FPR 균일 신뢰한계는 임계값별 FA 불확실성을 보고하는 데 쓸 수 있습니다.
   - PyOD `predict_proba(method='unify')`(V16)는 보조로 쓸 수 있고, "보정 확률 아님"을 명시합니다.
   - Platt이나 isotonic(V18, V19)은 다수의 라벨된 이상이 있어야 하므로 불가능합니다.
   - ExCeeD(V17, PyOD `predict_confidence`)는 "학습 집합 섭동에 대한 예측 안정성"으로 불확실성 시각화에 쓸 수 있습니다.

### 3.8 라이브러리 선택 가이드

- **안전한 기본 스택**: numpy, scipy, pandas, scikit-learn, statsmodels, PyOD, ruptures, STUMPY, matplotlib, 그리고 필요하면 PyTorch(LSTM-AE). 모두 BSD, MIT, Apache 계열이거나 matplotlib License입니다.
- **zip 동봉 원칙**
  - 라이브러리는 `requirements.txt`로만 명시하고 소스를 동봉하지 않습니다.
  - 남의 코드를 일부 복사하면 원 라이선스 고지를 포함합니다.
  - 라이선스가 없는 저장소(DCdetector, VUS GitHub)의 코드는 복사하지 않습니다.
- **피할 것**
  - Moirai 가중치(NC)
  - TimesFM 3.0 가중치(NC)
  - alibi-detect(BSL)
  - catch22, pycatch22, hctsa, saxpy, twitter AnomalyDetection(GPL/NC-SA)
  - 2024-12-03 이전 NAB 코드 복사본(AGPL)
- **파운데이션 모델 가중치**: 수백 MB에서 GB 단위라 zip에 넣기보다 런타임 다운로드가 현실적입니다. 다만 "원클릭 재현성"과 충돌하므로 부록 실험으로 분리하고 고정 버전과 해시를 기록합니다.

### 3.9 계획 반영 체크리스트(요약)

1. 입력에서 `TimeStamp`와 `Unnamed: 0`을 제외하고, 누설 탐침 결과를 표에 남깁니다.
2. 버스트 분할 규칙(0.15 s), 최소 버스트 길이 규칙, 지연에 미치는 영향을 문서화합니다.
3. 주 특징은 위상불변 진폭 특징과 전류 RMS 조건부 진동 잔차입니다. 동역학 특징은 절제 실험용입니다.
4. 기준선 B0–B8과 탐침 P1–P4를 실행합니다.
5. 연속 블록 교차검증, 중첩 임계값 보정, 이상 1회 적용 순서를 지킵니다.
6. 주 지표 3종, 보조 지표, CI, 블록 순위 검정, FA/h–지연 곡선, 심각도 스윕을 보고합니다.
7. FN 분석에서는 조용한 이상 버스트 3개의 라벨 의미를 분리해 서술합니다. FP 분석은 정상 야간의 부하 상태 전환(변화점)과 관련지어 합니다.
8. 확률은 conformal p 기반으로 정의하고, 해석상 한계를 문장으로 명시합니다.
9. 라이선스 표를 README에 넣습니다(사용 패키지와 정확한 라이선스명).

---

## 4. 위험·한계·반론

- **"이상은 하나가 이상적"이라는 주장과 그 반론**
  - E1은 "the ideal number of anomalies in a single testing time series is exactly one"이라고 보며, 위치 하나를 맞히는 이진 평가를 제안합니다.
  - E6은 "Single Anomaly Bias"를 데이터셋 결함으로 분류합니다.
  - 우리 상황은 시험 시계열 하나에 이상이 하나인 경우입니다. E1식 평가(가장 이상한 위치가 에피소드 안에 있는가)는 가능하지만, 일반화와 FA율 추정에는 E6의 비판이 그대로 적용됩니다. 두 관점을 함께 서술해야 합니다.
- **VUS-PR 권장의 이해관계**: VUS를 제안한 그룹이 TSB-AD에서 VUS-PR을 "most reliable"로 결론냈습니다. E5는 "가장 적절한 지표는 사용 사례에 따라 다르다"(RI 4)고 봅니다. 우리 경우 사건이 하나라 VUS 계열도 사실상 버스트 AUC-PR 수준의 정보만 줍니다.
- **PA 옹호론**: Anomaly Transformer 저자들은 PA가 "abnormal event detection"이라는 현장 의미를 가진다고 해명했습니다(issue #14). 현장에서 사건 단위 탐지가 중요하다는 점은 타당합니다. 다만 PA가 FA 비용을 반영하지 못하고 무작위 점수를 보상한다는 점(E2)이 결정적 반론입니다. 우리는 PA 대신 "사건 지연 + 시간당 FA"로 같은 현장 의미를 직접 측정합니다.
- **단순 방법 우위의 일반화 한계**: E5, E6, E7의 근거는 공개 벤치마크(결함 포함)에 기반합니다. 미세한 초기 고장에서는 딥 모델이 유리할 가능성을 배제할 수 없습니다. 다만 우리 데이터에는 미세 고장 사례가 없으므로 이를 검증할 수도 없습니다.
- **[R3 점검]의 한계**
  - 튜닝하지 않았습니다. 최소 버스트 길이 10, 99.5% 분위, 특징 선택은 임의입니다.
  - 정상거동 모델의 공변량 선택(std만 사용)은 이상 파일 결과를 본 뒤 비교한 것이므로 **사후 선택(oracle)**에 해당합니다. 실제 계획에서는 정상 데이터와 물리적 근거로 사전에 정해야 합니다.
  - 합성 진폭 스윕은 실제 고장 형태가 아닙니다. 고장이 진폭을 키운다는 가정을 깔고 있습니다.
- **정상거동 모델의 외삽 위험**: 이상 파일의 전류 std 범위(log 3.58–4.90)는 정상 범위(4.09–5.31)보다 아래로 넓습니다. 정상 범위를 벗어난 공변량에서 잔차를 해석하면 외삽입니다.
- **전류 동역학 특징의 해석 미정**: 지름길로 단정할 수 없습니다. 과제 설명대로 펌프 이상이 압력 불안정을 만든다면 모터 토크가 요동하고 전류가 불규칙해지는 것이 진짜 고장 신호일 수 있습니다. 확인하려면 측정 메타데이터(DAQ 설정, 인버터 여부)나 다른 날의 정상 데이터가 필요합니다.
- **conformal 보장의 가정**: 교환가능성이 시계열 자기상관 때문에 깨집니다. 블록 단위 보정이나 보수적 해석이 필요합니다.
- **라이선스 해석**
  - 법률 자문이 아닙니다.
  - "NC"가 상금이 있는 대회 제출에 해당하는지는 모호하므로 회피를 권장합니다.
  - GPL 패키지를 import만 하는 경우(동봉 안 함)의 의무 범위는 해석이 갈립니다. 동봉하지 않고 대체 가능한 패키지를 쓰는 편이 안전합니다.
  - 논문 그림은 CC BY(PLOS ONE 등)가 아니면 재사용하지 말고, 우리 데이터로 다시 그립니다. PVLDB 논문은 CC BY-NC-ND라 변형이 금지됩니다.
- **가이드북 수치 비교**: 가이드북의 시험 분할과 평가 단위를 모르므로, 97.087%(상수 기준) 비교는 "같은 클래스 비율이라면"이라는 조건부 서술로만 써야 합니다.

## 5. 아직 확인하지 못한 것

1. Fawcett & Provost(1999) AMOC 본문: 접근이 막혀(403) 정의와 그림 세부는 미검증입니다.
2. TaPR(E10), Sørbø & Ruocco(E13), Rewicki(E21) 본문: 메타데이터만 확인했습니다.
3. Chronos의 TMLR 게재: README의 bib로만 확인했습니다. Lag-Llama의 동료심사 게재 여부도 미확인입니다.
4. Wu & Keogh TKDE의 호(issue) 번호(권 35, 쪽 2421–2429만 확인).
5. PyPI `prts`의 실제 라이선스 원문, R `changepoint`의 CRAN 라이선스.
6. Kapoor & Narayanan의 누설 8유형 세부 명칭(초록만 열람).
7. TimeSeAD(Wagner et al., TMLR 2023), Lai et al.(TODS, NeurIPS 2021 D&B): 이번 조사에서 서지 확인을 못 해 표에서 제외했습니다.
8. 전류와 진동의 에일리어싱 오프셋 차이(정상 0.6 Hz, 이상 ≤0.3 Hz)의 물리적 원인(DAQ 클록, 인버터 주파수, 고장): R1/R2의 신호 분석이나 데이터 제공처 확인이 필요합니다.
9. KAMP 대회 규정이 사전학습 가중치나 외부 모델 사용을 어떻게 다루는지: 외부 "데이터" 규정만 공유받았으므로 다른 조사 주제로 넘깁니다.
10. 웹 검색 할당량(세션 200회)이 조사 도중 소진됐습니다. 이후는 WebFetch, Crossref·Semantic Scholar·arXiv·PMLR API, GitHub·PyPI·HF API로 확인했습니다. 그 결과 일부 최신 후속 연구(2025–2026)는 충분히 검색하지 못했을 수 있습니다.
