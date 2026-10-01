# R8 — 영향 요인·상호작용·오류 분석·교란(confound) 문제 조사 보고서

작성일: 2026-10-01 · 대상: 과제 ③ 프레스 유압펌프 이상 조기탐지·오경보 분석
범위: (1) 이상탐지기와 시계열 특징의 설명가능성, (2) 오류 분석·슬라이스 탐색과 "공정 조건" 정의, (3) 지름길 학습(shortcut)·교란과 그 검정 도구, (4) "이상 에피소드 1건, 다른 날 기록"을 정직하고 설득력 있게 보고하는 법.

검증 표기
- **opened-전문**: 원문 PDF나 HTML을 직접 받아서 해당 부분을 읽음
- **opened-초록**: 출판사 페이지나 API(Crossref, OpenAlex, Semantic Scholar, EuropePMC, arXiv)에서 초록과 서지를 받아 읽음
- **메타만**: Crossref에서 서지(저자, 제목, 권호, DOI)만 확인했고 내용은 보지 못함
- **search-only**: 검색 결과 요약으로만 봄
- **unverified**: 확인하지 못함

모든 DOI는 Crossref API로 실제 존재와 서지를 대조했다(예외는 표에 따로 적음). 이 보고서의 3.1절 숫자는 원시 데이터로 내가 직접 돌린 빠른 탐색 결과다. 재현 스크립트는 `scratchpad/research/r8eda/eda1.py`~`eda6.py`, 출력은 같은 폴더의 `*_out.txt`에 있다. 원시 데이터는 읽기만 했다.

---

## 1. 핵심 요약

1. **설계가 완전히 교란되어 있다.** 라벨, 파일, 날짜·시간대가 하나로 묶여 있다. 정상은 7/12(화) 00:00–01:17, 이상은 7/17(일) 10:51–10:54다. 인과추론 용어로는 positivity(overlap) 위반이다(Petersen et al. 2012). 그래서 데이터만으로 "고장 효과"와 "그날 조건 효과"를 통계적으로 분리할 방법이 **없다**.
   - 심사위원에게 설득력 있는 길은 세 가지다. ① 이 사실을 먼저 밝힌다. ② 반증 시험(음성 대조, 부하 매칭 비교, 특징군 제거, 정상 구간끼리 분리 가능성)을 묶어서 보인다. ③ 주장 범위를 "이 에피소드 대 이 정상 구간"으로 좁힌다.
   - 근거 문헌: DeGrave et al. 2021, Zech et al. 2018, Lipsitch et al. 2010, REFORMS.
2. **분리가 잘 된다는 것만으로는 고장 탐지의 증거가 되지 않는다(직접 확인).** 버스트 단위 분류기로 classifier two-sample test(C2ST)를 했다.
   - 정상 파일 안의 "조용한 구간"(약 01:00–01:12)과 다른 정상 구간: AUC 0.98–0.99
   - 정상 대 이상: AUC 0.995–1.0
   - 같은 날 정상끼리도 운전 상태가 바뀌면 거의 완벽하게 갈린다. 즉 높은 F1이나 AUC 자체를 "고장을 잡았다"는 증거로 내세우면 안 된다.
3. **이 데이터는 Wu & Keogh(2021)의 정의로 "trivial"하다(직접 확인).** "상부 진동 버스트 표준편차 > 학습용 정상 구간의 최댓값"이라는 한 줄 규칙만으로 다음 결과가 나온다.
   - 시간순 앞 60% 정상으로 임계값 설정
   - 뒤 40% 정상(조용한 구간 포함): 오경보 0/212 버스트
   - 이상 긴 버스트: 14/17 탐지
   - 따라서 모델의 가치는 F1이 아니라 다음에서 입증해야 한다: 정상 운전 변화와 수집 조건 변화에 대한 오경보 강건성, 조기성(첫 경보까지 시간), 확률 출력의 의미, 정직한 오류·교란 분석. 한 줄 규칙은 "기준선(baseline)" 비교군으로 반드시 넣는다.
4. **고장 쪽을 가장 강하게 지지하는 증거(직접 확인).**
   - 전류 진폭(부하의 대리변수)을 ±15%로 맞춘 정상 버스트와 비교했다. 긴 이상 버스트 17개 중 13개의 상부 진동 표준편차가 같은 부하 정상 버스트의 최댓값보다 컸다. 그 최댓값의 1.5–20배이고, 13개의 중앙값은 약 3.8배다.
   - 진동의 시간 구조도 바뀌었다. 상부 lag-1 자기상관 중앙값이 −0.04에서 0.69로, 1 Hz 미만(앨리어싱 영역) 전력 비중이 약 3%에서 약 48%로 늘었다.
   - 이 방향은 수집 타이밍 지터가 만드는 효과(신호가 백색화되는 쪽)와 **반대**다. 그래서 "수집 장비 문제"만으로는 설명하기 어렵다.
5. **가장 큰 지름길 위험은 전류의 시간 구조다(직접 확인, 가설 포함).**
   - 정상 전류는 77분 내내 0.600 Hz 단일 사인파였다. 긴 버스트 표본 69개 모두 R² ≥ 0.994였다(60 Hz 근처 교류를 10 Hz로 샘플링한 앨리어스로 보임).
   - 이상 파일의 전류는 그렇지 않다(R² 0.31–0.77). 전류 lag-1 자기상관 하나만으로 두 파일이 AUC 0.9997로 갈린다.
   - 그런데 시뮬레이션을 해 보니 **샘플링 시각 지터 2–3 ms(표준편차)**만으로 같은 패턴이 재현되고 진폭은 그대로였다.
   - 결론: 전류의 동역학 특징(lag-1 자기상관, 스펙트럼 모양, 원시 전류 시퀀스를 복원하는 LSTM-AE)은 "수집 계측(instrumentation) 의심 특징"으로 따로 다룬다. 전류 **진폭**만 운전 상태 변수로 쓴다.
6. **FN과 FP가 몰릴 것으로 예상되는 조건(직접 확인).**
   - FN: 이상 라벨인데 조용한 버스트 3/21개(#4, #20, #21). 비율 14%, Wilson 95% CI 5–35%. 이 가운데 #21은 전류 진폭(표준편차 35.8)이 정상 긴 버스트 최솟값(60.0)보다 낮아 정상 데이터가 덮지 못하는 영역에 있다.
   - FP 위험: 정상의 조용한 구간과 그 전환 시점, 짧은 버스트, 버스트 경계를 넘는 창(window).
   - 표는 행(row)이 아니라 **버스트 단위 건수/분모와 Wilson 구간**으로 낸다(Brown et al. 2001, Hurlbert 1984).
7. **설명 도구 구성.**
   - TreeSHAP: sklearn IsolationForest를 공식 지원한다(소스 확인, MIT).
   - DIFFI(MIT)
   - PCA/AE: 채널별 기여도와 reconstruction-based contribution. 다만 smearing에 주의한다.
   - 주효과는 PDP 대신 ALE, 상호작용은 H-statistic을 귀무분포와 함께 본다.
   - 중요도는 주변 순열 중요도 대신 **특징군 제거 후 재학습**으로 구한다(Hooker et al. 2021).
   - 전류×진동 상호작용이 정말 필요한지는 Ojala & Garriga의 Test 2(클래스 안에서 특징 순열)로 검정한다.
   - 설명의 1차 용도는 "모델이 옳은 이유로 맞히는지" 감사(Clever Hans audit)다(Lapuschkin 2019, Ruff 2021, Kauffmann 2025).
8. **평가와 보고.**
   - 임계값은 정상 데이터만으로 정한다.
   - 이상 에피소드는 최종 평가에 한 번만 쓴다.
   - 오경보는 시간당 건수로 보고한다. 정상 1.28시간에서 오경보 0건이어도 95% 상한은 약 2.3건/시간이다. 이 데이터로는 "시간당 1건 이하"를 증명할 수 없다. 이 한계 자체를 k-of-n 지속 조건 같은 경보 로직의 근거로 쓴다.
   - KAMP 가이드북 절차의 문제: 같은 이상 에피소드의 앞 300개 창으로 PR 곡선 교차점에서 임계값을 정하고 나머지 창으로 평가한다. 이 방식은 낙관적이라고 명시해야 한다(Kapoor & Narayanan의 L3.2 비독립 유형, 경계 창 겹침은 L1.4와 유사).
   - 보고 틀: REFORMS(8개 모듈 32문항), Kapoor & Narayanan의 누수 8유형, TRIPOD+AI 해당 항목, Model Card의 Factors(부하, 운전 구간, 계측), Datasheet를 한 장짜리 체크리스트로 부록에 넣는다.
9. **요청서 서지 정정.**
   - Li et al. 설명가능 이상탐지 서베이: ACM Computing Surveys가 아니라 **ACM TKDD 18(1), 2024**(DOI 10.1145/3609333)
   - 이상 설명 리뷰의 세 번째 저자: Pinel이 아니라 **Pivert**(Yepmo, Smits & Pivert, DKE 137, 2022)
10. **라이선스.**
    - **Alibi Explain**은 2024년부터 Business Source License(BSL)이므로 쓰지 않는다.
    - 사용 가능: shap(MIT), DIFFI(MIT), PyALE(MIT), Microsoft RAI Toolbox(MIT), pysubgroup(Apache-2.0), Domino(Apache-2.0).

---

## 2. 출처 표

등급
- **A**: 동료심사 저널, 주요 학회, 표준, 공공기관
- **B**: 신뢰할 만한 프리프린트, 기술보고서, 학위논문, 제조사 기술문서
- **C**: 블로그, 홍보물(근거로는 쓰지 않음)

"보고서 사용 위험"은 대회 보고서에 인용했을 때의 위험이다.

### A. 설명가능성 (특징 기여, 상호작용, 이상탐지 설명)

| # | 출처 | 유형·등급 | 검증 | 경고 | 라이선스 | 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| A1 | Lundberg, S.M., Lee, S.-I. "A Unified Approach to Interpreting Model Predictions." NeurIPS 30 (2017). https://proceedings.neurips.cc/paper/2017/hash/8a20a8621978632d76c43dfd28b67767-Abstract.html | 학회·A | opened-초록 (NeurIPS 페이지) | 없음. KernelSHAP은 특징 독립 가정(주변 분포 대체) 때문에 상관 특징이 있으면 외삽한다(A15, A16 참조) | 논문 저작권 저자/NeurIPS. 코드 shap은 MIT(LICENSE 확인) | 낮음 |
| A2 | Lundberg, S.M., Erion, G., Chen, H., DeGrave, A., Prutkin, J.M., Nair, B., Katz, R., Himmelfarb, J., Bansal, N., Lee, S.-I. "From local explanations to global understanding with explainable AI for trees." *Nature Machine Intelligence* 2, 56–67 (2020). DOI 10.1038/s42256-019-0138-9 | 저널·A | opened-초록 (Nature 페이지, arXiv 1905.04610) | 비OA(구독). arXiv 판 있음 | 구독 | 낮음 |
| A3 | Carletti, M., Terzi, M., Susto, G.A. "Interpretable Anomaly Detection with DIFFI: Depth-based feature importance of Isolation Forest." *Engineering Applications of AI* 119, 105730 (2023). DOI 10.1016/j.engappai.2022.105730. 코드 https://github.com/mattiacarletti/DIFFI | 저널·A | 메타 + opened-초록(arXiv 2007.11117) + GitHub 확인 | 저장소가 sklearn 내부 함수를 수정한 파일(`sklearn_mod_functions.py`)을 쓴다. 최신 sklearn(1.8)에서 동작하는지 **미검증** | 코드 MIT(LICENSE.md 확인) | 중간(버전 고정 필요) |
| A4 | Miller, P., Swanson, R.E., Heckler, C.E. "Contribution plots: a missing link in multivariate quality control." *Applied Mathematics and Computer Science* 8, 775–792 (1998) | 저널·A(지역 저널) | **원문 미열람**. Westerhuis et al. 2000 참고문헌 [3]에서 서지 확인(opened) | 호(issue) 미확인 | — | 낮음(고전적 출처로만) |
| A5 | Westerhuis, J.A., Gurden, S.P., Smilde, A.K. "Generalized contribution plots in multivariate statistical process monitoring." *Chemometrics and Intelligent Laboratory Systems* 51(1), 95–114 (2000). DOI 10.1016/S0169-7439(00)00062-9 | 저널·A | opened-전문 (PDF) | 기여도 관리한계를 제안했다. Q 기여도가 시간과 변수로 퍼지는 smearing을 지적했고, "변수 방향 smearing은 해결 불가"라고 명시 | 비OA | 낮음 |
| A6 | Alcala, C.F., Qin, S.J. "Reconstruction-based contribution for process monitoring." *Automatica* 45(7), 1593–1600 (2009). DOI 10.1016/j.automatica.2009.02.027 | 저널·A | opened-초록 (CityU 페이지) + 메타 | 단일 센서 고장이 크면 전통적 기여도는 진단에 실패하고 RBC는 올바른 진단을 보장한다는 결과(초록) | 비OA | 낮음 |
| A7 | Apley, D.W., Zhu, J. "Visualizing the Effects of Predictor Variables in Black Box Supervised Learning Models." *JRSS-B* 82(4), 1059–1086 (2020). DOI 10.1111/rssb.12377 | 저널·A | opened-초록 (OUP) | PDP는 상관 예측변수에서 외삽하고 ALE는 조건부 분포로 이를 피한다 | 비OA | 낮음 |
| A8 | Friedman, J.H., Popescu, B.E. "Predictive learning via rule ensembles." *Annals of Applied Statistics* 2(3), 916–954 (2008). DOI 10.1214/07-AOAS148 | 저널·A | opened-전문 (arXiv 0811.1679 §8) | H²_jk의 정의(식 44)와 parametric bootstrap 귀무분포(§8.3)를 확인. 예측변수 사이 연관만으로도 가짜 상호작용이 생길 수 있다고 저자들이 명시 | — | 낮음 |
| A9 | Strobl, C., Boulesteix, A.-L., Zeileis, A., Hothorn, T. "Bias in random forest variable importance measures: Illustrations, sources and a solution." *BMC Bioinformatics* 8, 25 (2007). DOI 10.1186/1471-2105-8-25 | 저널·A | opened-초록 (EuropePMC) | 척도나 범주 수가 다른 변수에서 RF 중요도가 편향된다 | CC BY 2.0 | 낮음 |
| A10 | Strobl, C., Boulesteix, A.-L., Kneib, T., Augustin, T., Zeileis, A. "Conditional variable importance for random forests." *BMC Bioinformatics* 9, 307 (2008). DOI 10.1186/1471-2105-9-307 | 저널·A | opened-초록 | 상관 변수에 유리한 편향이 있고, 조건부 순열로 이를 해결한다 | CC BY 2.0 | 낮음 |
| A11 | Hooker, G., Mentch, L., Zhou, S. "Unrestricted permutation forces extrapolation: variable importance requires at least one more model, or there is no free variable importance." *Statistics and Computing* 31, 82 (2021). DOI 10.1007/s11222-021-10057-z | 저널·A | opened-초록 (arXiv 1905.03151) + 메타 | permute-and-predict는 희소 영역에 과도한 비중을 준다. 효과를 제거한 뒤 성능 변화를 보는 재학습 방식을 권고 | CC BY 4.0 | 낮음 |
| A12 | Li, Z., Zhu, Y., van Leeuwen, M. "A Survey on Explainable Anomaly Detection." *ACM Transactions on Knowledge Discovery from Data* 18(1), Art. 23, 1–54 (2024; 온라인 2023). DOI 10.1145/3609333 | 저널·A(서베이) | 메타(Crossref) + search-only(내용) | **요청서의 "ACM Computing Surveys"는 틀림. TKDD가 맞음** | CC BY-SA 4.0(Crossref) | 낮음 |
| A13 | Yepmo, V., Smits, G., **Pivert, O.** "Anomaly explanation: A review." *Data & Knowledge Engineering* 137, 101946 (2022). DOI 10.1016/j.datak.2021.101946 | 저널·A(리뷰) | 메타 + search-only | **요청서의 "Pinel"은 틀림. Pivert가 맞음** | 비OA | 낮음 |
| A14 | Antwarg, L., Miller, R.M., Shapira, B., Rokach, L. "Explaining anomalies detected by autoencoders using Shapley Additive Explanations." *Expert Systems with Applications* 186, 115736 (2021). DOI 10.1016/j.eswa.2021.115736 | 저널·A | opened-초록 (arXiv 1903.02407) + 메타 | 기여 특징과 상쇄 특징을 함께 보여 준다. 사용자 연구 여부는 초록에서 확인 못 함 | 비OA | 낮음 |
| A15 | Takeishi, N. "Shapley Values of Reconstruction Errors of PCA for Explaining Anomaly Detection." 2019 ICDM Workshops, 793–798. DOI 10.1109/ICDMW.2019.00117 | 워크숍·A−/B | opened-초록 (arXiv 1909.03495) + 메타 | 상관된 특징에서는 확률적 PCA의 조건부 분포로 가치함수를 계산해야 한다 | IEEE | 낮음 |
| A16 | Molnar, C. et al. "General Pitfalls of Model-Agnostic Interpretation Methods for Machine Learning Models." In *xxAI – Beyond Explainable AI*, LNCS 13200, 39–68 (2022). DOI 10.1007/978-3-031-04083-2_4 | 단행본 장·A | opened-초록 (OpenAlex) | 함정 목록: 일반화 안 된 모델 해석, 특징 의존성, 상호작용, 불확실성, 인과 해석 | OA(hybrid) | 낮음 |
| A17 | Ruff, L., Kauffmann, J.R., Vandermeulen, R.A., Montavon, G., Samek, W., Kloft, M., Dietterich, T.G., Müller, K.-R. "A Unifying Review of Deep and Shallow Anomaly Detection." *Proceedings of the IEEE* 109(5), 756–795 (2021). DOI 10.1109/JPROC.2021.3052449 | 저널·A | opened-전문 (arXiv 2009.11732, Clever Hans 절) | MVTec 'wood'에서 KDE가 얼룩 대신 나뭇결에 반응하는 Clever Hans 사례. 높은 AUC가 가짜 상관에서 나옴 | CC BY 4.0 | 낮음 |
| A18 | Kauffmann, J., Dippel, J., Ruff, L., Samek, W., Müller, K.-R., Montavon, G. "Explainable AI reveals Clever Hans effects in unsupervised learning models." *Nature Machine Intelligence* 7(3), 412–422 (2025). DOI 10.1038/s42256-025-01000-2 | 저널·A | opened-초록 (OpenAlex) + 메타 | 비지도 이상탐지에서도 CH 효과가 흔하고, 데이터 이동에서 성능이 떨어진다(의료·산업 검사) | CC BY 4.0 | 낮음 |

### B. 오류 분석과 슬라이스 탐색

| # | 출처 | 유형·등급 | 검증 | 경고 | 라이선스 | 위험 |
|---|---|---|---|---|---|---|
| B1 | Chung, Y., Kraska, T., Polyzotis, N., Tae, K.H., Whang, S.E. "Slice Finder: Automated Data Slicing for Model Validation." ICDE 2019, 1550–1553. DOI 10.1109/ICDE.2019.00139; 확장판 "Automated Data Slicing for Model Validation: A Big Data – AI Integration Approach." *IEEE TKDE* 32(12), 2284–2296 (2020). DOI 10.1109/TKDE.2019.2916074 | 학회·저널·A | opened-전문 (arXiv 1807.06068) + 메타 | 문제 슬라이스 정의: Welch t-검정 + 효과크기 φ. 다중비교는 α-investing(mFDR)으로 통제. 큰 표본을 가정하므로 우리 21개 버스트에는 검정력이 거의 없음 | IEEE | 낮음 |
| B2 | Eyuboglu, S. et al. "Domino: Discovering Systematic Errors with Cross-Modal Embeddings." ICLR 2022 (Oral). arXiv 2203.14960 | 학회·A | opened-초록 | 이미지, 의료영상, 시계열(EEG)용 교차모달 임베딩이 필요하다. 우리 3채널 버스트 특징에는 과하다 | 코드 Apache-2.0(LICENSE 확인) | 중간(적용 부적합) |
| B3 | Microsoft Responsible AI Toolbox – Error Analysis. https://github.com/microsoft/responsible-ai-toolbox (docs/erroranalysis-dashboard-README.md) | 소프트웨어·B | opened (문서) + LICENSE 확인 | 오류 트리(error rate와 error coverage), 1–2차원 히트맵. 표본이 작으면 트리가 우연에 과적합함 | MIT | 낮음 |
| B4 | Herrera, F., Carmona, C.J., González, P., del Jesus, M.J. "An overview on subgroup discovery: foundations and applications." *Knowledge and Information Systems* 29(3), 495–525 (2011). DOI 10.1007/s10115-010-0356-2 | 저널·A | 메타 | — | 비OA | 낮음 |
| B5 | Atzmueller, M. "Subgroup discovery." *WIREs Data Mining and Knowledge Discovery* 5(1), 35–49 (2015). DOI 10.1002/widm.1144 | 저널·A(리뷰) | 메타 | — | 비OA | 낮음 |
| B6 | Lemmerich, F., Becker, M. "pysubgroup: Easy-to-Use Subgroup Discovery in Python." ECML PKDD 2018 Demo, LNCS, 658–662 (2019). DOI 10.1007/978-3-030-10997-4_46 | 데모·A−/B | 메타 + LICENSE 확인 | — | Apache-2.0 | 낮음 |

### C. 지름길 학습, 교란, 검정 도구

| # | 출처 | 유형·등급 | 검증 | 경고 | 라이선스 | 위험 |
|---|---|---|---|---|---|---|
| C1 | Geirhos, R. et al. "Shortcut learning in deep neural networks." *Nature Machine Intelligence* 2(11), 665–673 (2020). DOI 10.1038/s42256-020-00257-z | 저널·A(관점 논문) | opened-초록 (arXiv 2004.07780) + 메타 | 정의: "decision rules that perform well on standard benchmarks but fail to transfer to more challenging testing conditions". o.o.d. 검증을 권고 | 구독(arXiv 판 있음) | 낮음 |
| C2 | Lapuschkin, S. et al. "Unmasking Clever Hans predictors and assessing what machines really learn." *Nature Communications* 10, 1096 (2019). DOI 10.1038/s41467-019-08987-4 | 저널·A | opened-초록 (EuropePMC) | 표준 성능지표로는 문제 해결 전략의 차이를 구별하지 못한다. SpRAy 제안 | CC BY 4.0 | 낮음 |
| C3 | DeGrave, A.J., Janizek, J.D., Lee, S.-I. "AI for radiographic COVID-19 detection selects shortcuts over signal." *Nature Machine Intelligence* 3(7), 610–619 (2021). DOI 10.1038/s42256-021-00338-7 | 저널·A | opened-초록 (Semantic Scholar) + 메타 | 양성과 음성을 다른 출처에서 모으는 방식이 "nearly ideal scenario" for shortcut이다. 외부 검증만으로는 불충분하다. **우리 상황(정상과 이상이 다른 파일과 날짜)과 구조가 같음** | Nature(PMC 판 있음) | 낮음 |
| C4 | Zech, J.R. et al. "Variable generalization performance of a deep learning model to detect pneumonia in chest radiographs: A cross-sectional study." *PLOS Medicine* 15(11), e1002683 (2018). DOI 10.1371/journal.pmed.1002683 | 저널·A | opened-초록 (EuropePMC) | 병원만으로 정렬해도 AUC 0.861. CNN이 병원과 부서를 "robustly identified"함. 사이트가 교란변수로 작용한 사례 | CC BY 4.0 | 낮음 |
| C5 | Lipsitch, M., Tchetgen Tchetgen, E., Cohen, T. "Negative controls: a tool for detecting confounding and bias in observational studies." *Epidemiology* 21(3), 383–388 (2010). DOI 10.1097/EDE.0b013e3181d61eeb | 저널·A | opened-초록 (EuropePMC) | 노출 음성대조와 결과 음성대조를 구분. 음성대조가 민감한 탐지기가 되려면 조건이 필요하다(저자가 한계를 명시) | 비OA(PMC 판 있음) | 낮음 |
| C6 | Ojala, M., Garriga, G.C. "Permutation Tests for Studying Classifier Performance." *JMLR* 11, 1833–1863 (2010). https://www.jmlr.org/papers/v11/ojala10a.html | 저널·A | opened-초록 (JMLR 페이지) | Test 1은 라벨 순열(클래스 구조 존재), Test 2는 클래스 안에서 특징 순열(특징 의존성 활용 여부) | JMLR(OA) | 낮음 |
| C7 | Lopez-Paz, D., Oquab, M. "Revisiting Classifier Two-Sample Tests." ICLR 2017. arXiv 1610.06545 | 학회·A | opened-초록 (Semantic Scholar) | 두 표본이 같은 분포면 분류 정확도는 우연 수준이다(C2ST) | — | 낮음 |
| C8 | Rabanser, S., Günnemann, S., Lipton, Z.C. "Failing Loudly: An Empirical Study of Methods for Detecting Dataset Shift." NeurIPS 2019. arXiv 1810.11953 | 학회·A | opened-초록 (arXiv) | 도메인 분류기는 이동의 정성적 특성 파악에 유용하다 | — | 낮음 |
| C9 | Moreno-Torres, J.G., Raeder, T., Alaiz-Rodríguez, R., Chawla, N.V., Herrera, F. "A unifying view on dataset shift in classification." *Pattern Recognition* 45(1), 521–530 (2012). DOI 10.1016/j.patcog.2011.06.019 | 저널·A | 메타 | 용어 정리용 | 비OA | 낮음 |
| C10 | Peters, J., Bühlmann, P., Meinshausen, N. "Causal inference by using invariant prediction: identification and confidence intervals." *JRSS-B* 78(5), 947–1012 (2016). DOI 10.1111/rssb.12167 | 저널·A | opened-초록 (OpenAlex) | 여러 환경이 필요하다. 우리는 라벨당 환경이 1개뿐이라 **정상 운전 구간 사이의 불변성 점검**에만 쓸 수 있음 | 비OA | 중간(적용 범위 주의) |
| C11 | Stuart, E.A. "Matching Methods for Causal Inference: A Review and a Look Forward." *Statistical Science* 25(1), 1–21 (2010). DOI 10.1214/09-STS313 | 저널·A | opened-초록 | — | (green OA) | 낮음 |
| C12 | Petersen, M.L., Porter, K.E., Gruber, S., Wang, Y., van der Laan, M.J. "Diagnosing and responding to violations in the positivity assumption." *Statistical Methods in Medical Research* 21(1), 31–54 (2012). DOI 10.1177/0962280210386207 | 저널·A | opened-초록 | positivity 위반은 식별 가능성을 위협한다. 대응: 표본 제한, 목표 모수 수정 | (green OA) | 낮음 |
| C13 | Cinelli, C., Forney, A., Pearl, J. "A Crash Course in Good and Bad Controls." *Sociological Methods & Research* 53(3), 1071–1104 (2024; 온라인 2022). DOI 10.1177/00491241221099552 | 저널·A | opened-초록 | 매개변수를 통제하면 편향이 생긴다. **전류가 고장의 결과(매개변수)일 수 있으므로** 부하 매칭 해석 시 주의 | 비OA | 낮음 |

### D. 운전조건 정규화, PHM 벤치마크의 함정

| # | 출처 | 유형·등급 | 검증 | 경고 | 라이선스 | 위험 |
|---|---|---|---|---|---|---|
| D1 | Sohn, H. "Effects of environmental and operational variability on structural health monitoring." *Phil. Trans. R. Soc. A* 365(1851), 539–560 (2007). DOI 10.1098/rsta.2006.1935 | 저널·A(리뷰) | opened-초록 (OpenAlex) | 운전·환경 변동이 손상 신호를 가리므로 "data normalization"이 필요하다 | 비OA | 낮음 |
| D2 | Worden, K., Sohn, H., Farrar, C.R. "Novelty detection in a changing environment: regression and interpolation approaches." *Journal of Sound and Vibration* 258(4), 741–761 (2002). DOI 10.1006/jsvi.2002.5148 | 저널·A | 메타만 | 내용은 제목 수준으로만 인용 | 비OA | 낮음 |
| D3 | Cross, E.J., Worden, K., Chen, Q. "Cointegration: a novel approach for the removal of environmental trends in structural health monitoring data." *Proc. R. Soc. A* 467(2133), 2712–2732 (2011). DOI 10.1098/rspa.2011.0023 | 저널·A | opened-초록 | 공적분 잔차를 운전·환경 조건과 독립적인 손상 민감 특징으로 쓴다 | 비OA | 낮음 |
| D4 | Kullaa, J. "Distinguishing between sensor fault, structural damage, and environmental or operational effects in structural health monitoring." *MSSP* 25(8), 2976–2989 (2011). DOI 10.1016/j.ymssp.2011.05.017 | 저널·A | 메타만 | 센서 고장, 실제 손상, 운전 효과를 구분하는 문제의식(제목 수준). 내용 미열람 | 비OA | 낮음 |
| D5 | Bartelmus, W., Zimroz, R. "A new feature for monitoring the condition of gearboxes in non-stationary operating conditions." *MSSP* 23(5), 1528–1534 (2009). DOI 10.1016/j.ymssp.2009.01.014 | 저널·A | 메타만(내용 search-only) | 부하 의존성을 특징으로 쓰는 접근으로 알려져 있으나 **내용 미검증** | 비OA | 중간(내용 인용 금지, 존재만) |
| D6 | Zimroz, R., Bartelmus, W., Barszcz, T., Urbanek, J. "Diagnostics of bearings in presence of strong operating conditions non-stationarity — A procedure of load-dependent features processing with application to wind turbine bearings." *MSSP* 46(1), 16–27 (2014). DOI 10.1016/j.ymssp.2013.09.010 | 저널·A | 메타만(내용 search-only) | 같음 | 비OA | 중간 |
| D7 | Tautz-Weinert, J., Watson, S.J. "Using SCADA data for wind turbine condition monitoring – a review." *IET Renewable Power Generation* 11(4), 382–394 (2017). DOI 10.1049/iet-rpg.2016.0248 | 저널·A(리뷰) | opened-초록 | 접근 분류: trending, clustering, **normal behaviour modelling**, damage modelling, 경보 평가 | green OA | 낮음 |
| D8 | Schlechtingen, M., Santos, I.F., Achiche, S. "Wind turbine condition monitoring based on SCADA data using normal behavior models. Part 1: System description." *Applied Soft Computing* 13(1), 259–270 (2013). DOI 10.1016/j.asoc.2012.08.033 | 저널·A | 메타만 | — | 비OA | 낮음 |
| D9 | Michau, G., Fink, O. "Unsupervised transfer learning for anomaly detection: Application to complementary operating condition transfer." *Knowledge-Based Systems* 216, 106816 (2021). DOI 10.1016/j.knosys.2021.106816 | 저널·A | opened-초록 | 건강 데이터가 운전조건을 충분히 대표해야 한다. 그렇지 않으면 미경험 조건이 이상으로 오인된다 | CC BY-NC-ND 4.0(Crossref) | 낮음 |
| D10 | Fink, O., Wang, Q., Svensén, M., Dersin, P., Lee, W.-J., Ducoffe, M. "Potential, challenges and future directions for deep learning in prognostics and health management applications." *EAAI* 92, 103678 (2020). DOI 10.1016/j.engappai.2020.103678 | 저널·A(리뷰) | opened-초록 | — | OA(hybrid) | 낮음 |
| D11 | Hendriks, J., Dumond, P., Knox, D.A. "Towards better benchmarking using the CWRU bearing fault dataset." *MSSP* 169, 108732 (2022). DOI 10.1016/j.ymssp.2021.108732 | 저널·A | 메타 + search-only(내용) | 운전조건을 바꿔 학습/시험을 나눠도 **같은 물리적 베어링**이 양쪽에 있으면 진짜 domain shift 시험이 아니다. 독립 베어링 단위로 나눠야 한다(검색 요약 기준) | 비OA | 중간(내용은 search-only로 표기) |
| D12 | Rauber, T.W., da Silva Loca, A.L., Boldt, F.d.A., Rodrigues, A.L., Varejão, F.M. "An experimental methodology to evaluate machine learning methods for fault diagnosis based on vibration signals." *Expert Systems with Applications* 167, 114022 (2021). DOI 10.1016/j.eswa.2020.114022 | 저널·A | opened-초록 (Semantic Scholar) | "recycling identical patterns in test data sets"로 인한 낙관 편향, 하이퍼파라미터 과적합 | 비OA | 낮음 |
| D13 | Smith, W.A., Randall, R.B. "Rolling element bearing diagnostics using the Case Western Reserve University data: A benchmark study." *MSSP* 64–65, 100–131 (2015). DOI 10.1016/j.ymssp.2015.04.021 | 저널·A | opened-초록 | 기록마다 진단 가능성을 분류해 정직하게 보고한 사례. 라벨 타당성 점검의 본보기 | green OA | 낮음 |
| D14 | Zhao, Z. et al. "Deep learning algorithms for rotating machinery intelligent diagnosis: An open source benchmark study." *ISA Transactions* 107, 224–255 (2020). DOI 10.1016/j.isatra.2020.08.010 | 저널·A | opened-초록 (arXiv 2003.03315) | "unfair comparisons"를 지적. 분할 방식의 영향을 다룸(세부는 본문 미열람) | green OA | 낮음 |
| D15 | Lessmeier, C., Kimotho, J.K., Zimmer, D., Sextro, W. "Condition Monitoring of Bearing Damage in Electromechanical Drive Systems by Using Motor Current Signals of Electric Motors: A Benchmark Data Set for Data-Driven Classification." PHM Society European Conference 2016. https://papers.phmsociety.org/index.php/phme/article/view/1577 | 학회·A−/B | opened-초록 | 인공 손상과 실제 손상으로 학습했을 때 정확도가 다르다. 전류 기반 진단 | CC BY 3.0 | 낮음 |
| D16 | Gück, C., Roelofs, C.M.A., Faulstich, S. "CARE to Compare: A Real-World Benchmark Dataset for Early Fault Detection in Wind Turbine Data." *Data* 9(12), 138 (2024). DOI 10.3390/data9120138 | 저널(MDPI)·B+ | opened-초록 (OpenAlex) | 지적: "many publications highlight a couple of case studies where fault detection was successful". CARE 점수 = Coverage, Accuracy, Reliability, Earliness. **공식 세부는 미열람**(MDPI 403). MDPI라서 품질 편차 있음 | CC BY 4.0 | 중간(개념만 인용) |

### E. 평가 설계와 소표본 통계

| # | 출처 | 유형·등급 | 검증 | 경고 | 라이선스 | 위험 |
|---|---|---|---|---|---|---|
| E1 | Wu, R., Keogh, E. "Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress." *IEEE TKDE* (early access 2021). DOI 10.1109/TKDE.2021.3112126 | 저널·A | opened-전문 (arXiv 2009.13807) + 메타 | 네 가지 결함: triviality(한 줄 MATLAB으로 풀림), unrealistic anomaly density, mislabeled ground truth, run-to-failure bias. **최종 권·쪽 미확인** | arXiv | 낮음 |
| E2 | Kim, S., Choi, K., Choi, H.-S., Lee, B., Yoon, S. "Towards a Rigorous Evaluation of Time-Series Anomaly Detection." AAAI 36(7), 7194–7201 (2022). DOI 10.1609/aaai.v36i7.20680 | 학회·A | opened-초록 | point-adjust는 성능을 과대평가한다. 무작위 점수도 SOTA처럼 보일 수 있다 | AAAI(OA) | 낮음 |
| E3 | Roberts, D.R. et al. "Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure." *Ecography* 40(8), 913–929 (2017). DOI 10.1111/ecog.02881 | 저널·A | opened-초록 | 의존 구조가 있으면 block CV를 쓴다. 다만 블록화가 외삽을 유발할 수도 있음 | 비OA | 낮음 |
| E4 | Saeb, S., Lonini, L., Jayaraman, A., Mohr, D.C., Kording, K.P. "The need to approximate the use-case in clinical machine learning." *GigaScience* 6(5), gix019 (2017). DOI 10.1093/gigascience/gix019 | 저널·A | opened-초록 | record-wise CV는 "massively overestimates" 한다. subject-wise로 해야 한다 | OA(gold) | 낮음 |
| E5 | Varoquaux, G. "Cross-validation failure: Small sample sizes lead to large error bars." *NeuroImage* 180, 68–77 (2018). DOI 10.1016/j.neuroimage.2017.06.061 | 저널·A | opened-초록 (arXiv 1706.07581) | 표본 100개에서 ±10% 오차막대 | green OA | 낮음 |
| E6 | Hurlbert, S.H. "Pseudoreplication and the Design of Ecological Field Experiments." *Ecological Monographs* 54(2), 187–211 (1984). DOI 10.2307/1942661 | 저널·A | opened-초록 | 처리가 반복되지 않았는데 표본 반복을 독립 반복처럼 검정하는 오류 | 비OA | 낮음 |
| E7 | Brown, L.D., Cai, T.T., DasGupta, A. "Interval Estimation for a Binomial Proportion." *Statistical Science* 16(2) (2001). DOI 10.1214/ss/1009213286 | 저널·A | opened-초록 | Wald 구간은 신뢰할 수 없다. 작은 n에서는 Wilson이나 Jeffreys를 권고 | — | 낮음 |
| E8 | Hanley, J.A., Lippman-Hand, A. "If nothing goes wrong, is everything all right? Interpreting zero numerators." *JAMA* 249(13), 1743–1745 (1983). DOI 10.1001/jama.1983.03330370053031 | 저널·A | 메타(EuropePMC 저자 확인) | "rule of three"(0/n이면 95% 상한은 약 3/n) | 비OA | 낮음 |
| E9 | Künsch, H.R. "The Jackknife and the Bootstrap for General Stationary Observations." *Annals of Statistics* 17(3) (1989). DOI 10.1214/aos/1176347265 | 저널·A | opened-초록 | moving block bootstrap | (bronze OA) | 낮음 |
| E10 | Gelman, A., Loken, E. "The Statistical Crisis in Science." *American Scientist* 102(6), 460 (2014). DOI 10.1511/2014.111.460 | 잡지 기사·B | 메타만 | forking paths 개념 설명용 | — | 낮음 |
| E11 | Bates, S., Candès, E., Lei, L., Romano, Y., Sesia, M. "Testing for outliers with conformal p-values." *Annals of Statistics* 51(1) (2023). DOI 10.1214/22-AOS2244 | 저널·A | opened-초록 | conformal p-value로 오탐률과 FDR을 통제한다. **교환가능성(i.i.d.)을 가정**하므로 시계열에서는 블록 단위로 써야 함 | green OA | 중간(가정 위반 명시 필요) |
| E12 | Laxhammar, R., Falkman, G. "Inductive conformal anomaly detection for sequential detection of anomalous sub-trajectories." *Annals of Mathematics and AI* 74(1–2), 67–94 (2015). DOI 10.1007/s10472-013-9381-7 | 저널·A | 메타만 | — | 비OA | 낮음 |
| E13 | Gregorutti, B., Michel, B., Saint-Pierre, P. "Grouped variable importance with random forests and application to multiple functional data analysis." *Computational Statistics & Data Analysis* 90, 15–35 (2015). DOI 10.1016/j.csda.2015.04.002 | 저널·A | opened-초록 (Semantic Scholar) | 특징군 단위 중요도 | green OA(arXiv 1411.4170) | 낮음 |
| E14 | Lei, J., G'Sell, M., Rinaldo, A., Tibshirani, R.J., Wasserman, L. "Distribution-Free Predictive Inference for Regression." *JASA* 113(523), 1094–1111 (2018). DOI 10.1080/01621459.2017.1307116 | 저널·A | 메타만 | LOCO 중요도의 출처로 흔히 인용된다(내용 미열람) | 비OA | 낮음 |
| E15 | Dietterich, T.G., Lathrop, R.H., Lozano-Pérez, T. "Solving the multiple instance problem with axis-parallel rectangles." *Artificial Intelligence* 89(1–2), 31–71 (1997). DOI 10.1016/S0004-3702(96)00034-3 | 저널·A | 메타만 | MIL의 원전 | 비OA | 낮음 |
| E16 | Zhou, Z.-H. "A brief introduction to weakly supervised learning." *National Science Review* 5(1), 44–53 (2018). DOI 10.1093/nsr/nwx106 | 저널·A | opened-초록 | inexact supervision = 거친(coarse-grained) 라벨 | OA(hybrid) | 낮음 |

### F. 보고 지침

| # | 출처 | 유형·등급 | 검증 | 경고 | 라이선스 | 위험 |
|---|---|---|---|---|---|---|
| F1 | Kapoor, S. et al. "REFORMS: Consensus-based Recommendations for Machine-learning-based Science." *Science Advances* 10(18), eadk3452 (2024). DOI 10.1126/sciadv.adk3452 | 저널·A(합의 지침) | opened-전문 (EuropePMC, 표 1의 32문항 전부 확인) | — | Science Advances(OA) | 낮음 |
| F2 | Kapoor, S., Narayanan, A. "Leakage and the reproducibility crisis in machine-learning-based science." *Patterns* 4(9), 100804 (2023). DOI 10.1016/j.patter.2023.100804 | 저널·A | opened-전문 (누수 8유형 L1.1–L3.3 확인) | — | CC BY 4.0 | 낮음 |
| F3 | Collins, G.S. et al. "TRIPOD+AI statement: updated guidance for reporting clinical prediction models that use regression or machine learning methods." *BMJ* 385, e078378 (2024). DOI 10.1136/bmj-2023-078378 | 저널·A(지침) | opened-전문 (항목 10, 12d, 12e, 13, 26, 27a 확인) | 임상용이라 일부 항목은 해당 없음 | CC BY 4.0 | 낮음 |
| F4 | Mitchell, M. et al. "Model Cards for Model Reporting." FAT* 2019, 220–229. DOI 10.1145/3287560.3287596 | 학회·A | opened-전문 (arXiv 1810.03993) | Factors = groups, **instrumentation**, environment | ACM | 낮음 |
| F5 | Gebru, T. et al. "Datasheets for Datasets." *Communications of the ACM* 64(12), 86–92 (2021). DOI 10.1145/3458723 | 저널·A | opened-전문 (arXiv 1803.09010 v8) | 7개 절(Motivation … Maintenance) | ACM | 낮음 |

### G. 도구, 라이선스, 대회 자료

| # | 출처 | 유형 | 검증 | 경고 | 라이선스 | 위험 |
|---|---|---|---|---|---|---|
| G1 | shap (https://github.com/shap/shap) `shap/explainers/_tree.py` | 소프트웨어·B | opened(소스) | TreeExplainer가 `sklearn.ensemble.IsolationForest`를 명시적으로 지원함(소스 확인) | MIT | 낮음 |
| G2 | Alibi Explain (SeldonIO/alibi) LICENSE | 소프트웨어 | opened(LICENSE) | **Business Source License**(2024년 1월부터). 비영리 교육기관의 생산 사용 등 조건부 허용 | BSL 1.1 | **높음 → 쓰지 말 것** |
| G3 | PyALE (DanaJomar/PyALE) LICENSE | 소프트웨어·C/B | opened(LICENSE) | 저작자 표기 자리가 "[year] [fullname]" 그대로 남은 MIT | MIT | 낮음(직접 구현도 쉬움) |
| G4 | KAMP 「소성가공 예지보전 AI 데이터셋」 분석실습 가이드북(로컬 PDF) | 공공기관 자료·A/B | opened-전문(로컬) | 3.1절의 G 항목 참조(같은 에피소드로 임계값 설정, 창이 버스트 공백을 넘음) | KAMP 이용조건 | — |

---

## 3. 세부 내용과 우리 계획에의 적용

### 3.1 원시 데이터에서 직접 확인한 사실 (교란 판단의 출발점)

> 모두 내가 직접 계산했다. 스크립트: `scratchpad/research/r8eda/`. 버스트 = 0.5초를 넘는 시간 공백으로 자른 연속 구간. "긴 버스트" = 10행 이상.

**(a) 분석 단위의 위계.** 유사반복(pseudoreplication) 문제다(E6, E4).

| 단위 | 정상 | 이상 |
|---|---|---|
| 행 | 20,000 | 600 |
| 버스트 | 599 (긴 버스트 530) | 21 (긴 버스트 17) |
| 운전 구간(눈으로 구분) | 최소 2개: 바쁜 구간, 조용한 구간 01:00–01:12 | 1개 에피소드 안에 조용한 버스트 섞임 |
| 독립 에피소드 / 날 | 1 / 1 | **1 / 1** |

- 결론: 이상 쪽의 유효 표본 수는 사실상 **1(에피소드)**이다. 행 600개나 창 수백 개를 독립 표본처럼 다루어 F1·정확도에 신뢰구간을 붙이면 Hurlbert가 말한 pseudoreplication이 된다.

**(b) 음성대조 성격의 수집 특징은 거의 분리하지 못한다.** 버스트 길이(n) AUC 0.44, 앞 공백 길이 0.62, 시작 시각 ms 위상 0.49. 이는 좋은 신호다. 수집 "패턴"만으로 두 파일이 구별되지는 않는다.

**(c) 단일 특징 분리력(긴 버스트, AUC).**

| 특징 | AUC |
|---|---|
| 상부 진동 표준편차 | 0.825 |
| 하부 진동 표준편차 | 0.839 |
| 하부 첨도 | 0.869 |
| 상부/하부 비 | 0.859 |
| 진동/전류 비 | 0.906 |
| 상부 진동 lag-1 자기상관 | 0.962 |
| **전류 lag-1 자기상관** | **0.0003, 즉 반대 방향으로 0.9997** |
| 전류 표준편차(부하) | 0.315 (이상 쪽이 약간 낮음) |

- 정상 전류 lag-1 최솟값은 0.757, 이상 최댓값은 0.822다. 이상 최댓값보다 낮은 정상 버스트는 530개 중 2개뿐이다.

**(d) 부하를 맞춘 비교(matched comparison, C11).** 각 이상 버스트마다 전류 표준편차가 ±15% 안인 정상 버스트를 모아 상부 진동 표준편차를 비교했다.
- 긴 이상 버스트 17개 중 **13개가 같은 부하 정상 버스트의 최댓값보다 컸다.** 예: #2는 0.395 대 정상 최댓값 0.116, #5는 0.708 대 0.106.
- 2개(#4, #20)는 정상보다 조용했다.
- 2개(#15, #21)는 짝지을 정상 버스트가 없었다. 부하가 정상 범위 밖이라 positivity가 위반된다(C12).

**(e) 전류 앨리어스 구조.**
- 정상 전류: 긴 버스트마다 단일 사인파를 맞추면 주파수 0.595–0.605 Hz, R² 0.994–1.000이다(표본 69개, 77분 내내 변동 없음). FFT 피크도 276개 긴 버스트 모두 0.61 Hz이고 1 Hz 미만 전력이 99.6%다.
- 이상 전류: 최적 주파수 0.01–0.23 Hz, R² 0.31–0.77로 단일 사인파가 아니다.
- **지터 시뮬레이션**(`eda6.py`): 60.6 Hz 사인파를 10 Hz로 샘플링하면서 샘플 시각에 가우스 지터를 넣었다.
  - 지터 표준편차 2 ms: lag-1 0.51, R² 0.62
  - 지터 표준편차 3 ms: lag-1 0.25, R² 0.30
  - 진폭은 변하지 않았다.
  - 이상 파일 값과 겹친다: lag-1 중앙값은 21버스트 전체 0.385, 긴 버스트 17개 0.44이고 R²는 0.31–0.77이다.
- 해석: 몇 ms 수준의 수집 타이밍 차이만으로도 전류의 "모양"이 바뀐 것처럼 보일 수 있다. 실제 토크 맥동(고장)일 수도 있다. **데이터로 둘을 구별할 수 없다.**

**(f) 진동 구조는 지터로 설명되지 않는다.**
- 정상 진동: 앨리어스 피크 1.78–3.6 Hz, 1 Hz 미만 전력 비중 중앙값 3.4%(상부), 1.5%(하부), lag-1 약 −0.04
- 이상 진동: 1 Hz 미만 비중 47.8%(상부), 59.4%(하부), lag-1 0.69
- 지터는 신호를 백색화하는 쪽으로 작용하므로 관측된 변화(저주파 집중, 자기상관 증가)와 방향이 반대다. 진동 변화는 실제 저주파 진동(예: 압력 맥동이나 기계적 요동)일 가능성이 상대적으로 높다. 다만 물리적 해석은 다른 조사 주제와 대조가 필요하다.

**(g) 정상 안의 운전 변화(자연 실험).**
- 약 01:00–01:12에 조용한 구간이 있다(상부 진동 표준편차 약 0.04, 전류 표준편차 약 86).
- 조용한 버스트(상부 < 0.05, 하부 < 0.07)는 모두 138개이고 시각 중앙값은 01:01이다.
- C2ST(RF, 5겹, 버스트 단위, 전체 특징) AUC:

| 비교 | AUC |
|---|---|
| 조용한 구간 대 다른 정상 블록 | 0.984–0.993 |
| 다른 정상 블록끼리 | 0.49–0.72 |
| 정상 전체 대 이상 | 1.0 |
| 정상 대 이상(진동만) | 0.995 |

- 주의: 블록 안에서 무작위 5겹으로 나눴으므로 인접 버스트의 자기상관 때문에 AUC가 약간 부풀었을 수 있다. 하지만 모든 비교에 같은 조건이다.

**(h) 정직한 한 줄 기준선.**
- 앞 60% 정상의 상부 진동 표준편차 최댓값 0.149를 임계값으로 썼다.
- 결과: 뒤 40% 정상(0.52시간, 212버스트, 조용한 구간 포함)에서 오경보 0건, 긴 이상 버스트 탐지 14/17(Wilson 95% CI 59–94%).
- 하부 진동으로 하면 오경보 3/212, 탐지 9/17이다.

**(i) 오경보율 상한(E8).**
- 정상 전체 1.28시간(버스트 599개, 시간당 약 468개)에서 오경보 0건이면, 포아송 95% 상한은 3.0/1.28 ≈ **2.3건/시간**이다.
- 뒤 40%만 쓰면 3.0/0.52 ≈ **5.8건/시간**이다.
- 버스트당 오경보율 0.5%면 시간당 2.3건이다. 운영상 감당하기 어렵다.

**(j) 이상 라벨 안의 조용한 버스트.**
- #4(10:51:31, 31행, 상부 0.029), #20(10:53:42, 10행, 0.028), #21(10:53:52, 15행, 0.022)
- #21은 전류 표준편차 35.8로 정상 긴 버스트 최솟값 60.0보다 낮다. 에피소드 끝에서 부하가 내려가는 모습(정지나 무부하로 보이나 확인 불가)이다.
- 가이드북에서 Equipment_state의 정의는 "장비 고장 여부"다(로컬 PDF). 즉 **파일 단위 라벨**이다. 행이나 버스트 단위의 실제 상태는 모른다. 약지도(weak supervision) 중 inexact supervision(E16)이나 MIL(E15)의 "가방(bag)" 구조로 보는 것이 맞다.

**(k) 가이드북 절차의 사실관계(G4, 로컬 PDF 확인).**
- 정상: 0–14,999행(00:00–00:57)으로 학습, 15,000–19,999행(00:57–01:17)으로 시험. 시험 구간에 조용한 구간 01:00–01:12가 통째로 들어간다.
- MinMaxScaler는 학습 데이터에만 fit한다. 이 부분은 올바르다.
- 창: 20행, stride 1. 행 번호로 연속하게 만들므로 버스트 공백을 넘는 창이 많다.
- 임계값: 이상 파일의 앞 300개 창과 정상 880개 창으로 만든 검증셋에서 **정밀도·재현율 곡선 교차점**으로 정한다. 같은 에피소드의 나머지 창으로 평가한다.
- 이것은 Kapoor & Narayanan 분류로 낙관 편향이다. 같은 에피소드에서 검증과 시험을 뽑으므로 L3.2(비독립)에 해당하고, stride 1 창이라 검증·시험 경계에서 창이 행을 공유하므로 L1.4(중복)와도 비슷하다. 우리 보고서에서 "가이드북 수치와 직접 비교할 때의 주의"로 명시한다.

### 3.2 설명가능성: 무엇을, 어떻게, 왜

**원칙.** 우리 상황에서 설명의 1차 목적은 "모델이 무엇을 보고 이상이라고 하는가" 감사다(C2, A17, A18, C3). 설명이 진동 진폭이나 부하 대비 진동 같은 물리적으로 그럴듯한 특징을 가리키면 지지 근거가 된다. 전류 앨리어스 구조나 수집 특징을 가리키면 Clever Hans 경고다.

1. **TreeSHAP(A1, A2, G1).**
   - 버스트 특징 위의 IsolationForest, GBM, RF에 쓴다. shap TreeExplainer는 sklearn IsolationForest를 공식 지원한다(소스 확인).
   - 산출물 ① 이상 버스트별 waterfall: 상위 3개 특징. 상쇄 특징도 함께 보인다(A14의 아이디어).
   - 산출물 ② 전체 beeswarm.
   - 산출물 ③ **SHAP interaction values**: 전류 진폭 × 상부 진동, 상부 × 하부.
   - 주의 ①: TreeSHAP도 `feature_perturbation` 설정(interventional+배경데이터 대 tree_path_dependent)에 따라 상관 특징 사이의 기여 배분이 달라진다. interventional 방식은 존재하지 않는 조합으로 외삽할 수 있다(A16). 설정을 명시하고 두 설정의 순위가 같은지 확인한다.
   - 주의 ②: 비지도 점수(IF path length)의 SHAP은 "고장 원인"이 아니라 "점수 원인"을 설명한다.
2. **DIFFI(A3).**
   - IF 전용 전역·국소 중요도. TreeSHAP 결과와 순위가 일치하는지 교차 확인용으로 쓴다(방법 간 합의 = 강건성 근거).
   - 코드가 sklearn 내부를 수정하므로 requirements에 sklearn 버전을 고정하거나 핵심 로직을 따로 구현해야 한다. **동작 미검증.**
3. **재구성 기반 모델(PCA, AE, LSTM-AE)의 기여도(A5, A6, A15).**
   - 채널별 SPE(Q) 기여 = 채널별 재구성 오차 제곱. Westerhuis식으로 정상 데이터 기준 **기여도 관리한계**(예: 정상 기여의 99% 분위)를 함께 그린다.
   - smearing에 주의한다. 상부와 하부 진동이 상관되어 있으면 한 채널의 이상이 다른 채널 기여로 번진다. 이를 줄이려면 RBC(Alcala & Qin)나 확률적 PCA 조건부 Shapley(Takeishi)를 쓴다.
   - "어느 센서가 이상을 주도했나"(상부 대 하부)를 보고할 때는 RBC를 1순위로 하고, 단순 기여도를 보조로 둔다.
4. **ALE(A7). PDP는 쓰지 않는다.**
   - 전류 진폭과 진동이 운전 구간에 따라 함께 움직이므로(조용한 구간은 둘 다 낮음) PDP는 존재하지 않는 조합(조용한 전류 + 바쁜 진동)에서 외삽한다.
   - 2차원 ALE(전류 진폭 × 상부 진동 표준편차)로 "같은 부하에서 진동이 높으면 점수가 오르는가"를 그린다.
   - 라이브러리: PyALE(MIT) 또는 직접 구현(약 40줄). Alibi는 BSL이므로 배제한다(G2).
5. **상호작용 강도(A8, C6).**
   - H²_jk = 2변수 부분의존이 주효과 합으로 설명되지 않는 분산 비율(식 44).
   - 귀무분포는 Friedman–Popescu의 parametric bootstrap(상호작용 없는 가법 모델로 만든 인공 데이터에서 같은 절차를 반복)으로 얻는다. 귀무분포 없이 H 값만 보고하지 않는다(저자들이 표본 변동과 예측변수 연관이 가짜 상호작용을 만든다고 명시).
   - 보완 검정은 **Ojala–Garriga Test 2**다. 이상과 정상 각각 안에서 특징 열을 독립적으로 섞어 특징 간 의존을 깬다. 그래도 성능이 그대로면 "상호작용이나 결합 정보는 필요 없고 주변 분포만으로 충분하다"는 결론이 된다. 성능이 떨어지면 결합 정보가 쓰이고 있다는 뜻이다.
   - 이 결과를 "주요 변수와 상호작용" 채점 항목(배점 15)의 근거로 쓴다.
6. **변수 중요도: 주변 순열 대신 특징군 제거 후 재학습(A9–A11, E13, E14).**
   - 특징군 정의: {진동 진폭}, {진동 동역학(lag-1, 저주파 비중, 첨도)}, {전류 진폭}, **{전류 동역학(lag-1, 앨리어스 R²)}**, {결합(상부/하부 비, 진동/전류 비, 전류–진동 상관)}.
   - 각 군을 빼고 재학습해 탐지율과 오경보율의 변화를 표로 낸다. 군 단위로 하면 상관 특징끼리 공을 나누는 문제가 줄어든다(Gregorutti, Hooker 권고).
   - **판정 규칙**: {전류 동역학}만으로 탐지가 유지되거나, 그 군을 뺐을 때 성능이 크게 떨어지면 → "계측 의존(Clever Hans 의심)" 경고를 달고, 최종 모델에서 빼거나 따로 보고한다.

### 3.3 오류 분석: "공정 조건"을 세 개 신호와 시간에서 만들기

**정의할 운전 상태 변수(사전 등록 슬라이스).** 오류를 보기 *전에* 정해 두고, 보고서에 "사전 정의"라고 명시한다(E10의 forking paths 방지).

| 변수 | 정의(버스트 단위) | 근거·용도 |
|---|---|---|
| 부하 수준 | 전류 진폭(표준편차 또는 √2·RMS; 앨리어스 단일 사인파면 진폭 추정이 안정적)을 정상 3분위로 나눔 | 펌프 구동 토크의 대리변수(도메인 지식, 문헌 미검증). 매개변수일 수 있어 주의(C13) |
| 운전 구간 | 바쁜 구간 대 조용한 구간(정상 기준 진동·전류 군집 또는 01:00–01:12 같은 시간 블록) | 정상 운전 변화 → FP 슬라이스 |
| 구간 전환 근접 | 운전 구간이 바뀐 시점 ±2분 | 변화점에서 생기는 FP |
| 버스트 길이 | 1–9 / 10–49 / 50행 | 짧은 버스트는 창 특징이 불안정 → FP·FN 모두 |
| 버스트 내 위치 | 첫 k 샘플 대 이후 | 창 워밍업과 버스트 경계 효과 |
| 전류 앨리어스 상태 | 단일 사인파 R² ≥ 0.95(정상형) 대 미만(교란형) | 계측 의심 슬라이스 |
| 상부/하부 비 | 정상 분위 기준 3구간 | 고장 위치 단서(상부 우세) |
| 진동–전류 결합 | 버스트 안에서 전류 절댓값과 진동 절댓값의 상관 | 상호작용 슬라이스 |
| 시간 | 정상: 10분 블록. 이상: 에피소드 경과 시간(초) | 조기성, 표류 |

**표 서식(작은 수 정직하게).** 행 비율은 쓰지 않는다. 버스트 단위로 쓴다.

| 슬라이스 | 이상 버스트 n | FN | FN 비율(Wilson 95% CI) | 정상 버스트 n | FP | FP/시간(포아송 95% 상한) | 비고 |
|---|---|---|---|---|---|---|---|
| (예) 조용한 이상 버스트 | 3 | 3 | — | — | — | — | #4, #20, #21. 라벨 해상도 문제 |
| (예) 정상 조용한 구간 | — | — | — | 83(긴 버스트) | ? | ? | 모델별로 채움 |

- 분모가 10 미만인 칸은 비율 대신 "k/n"만 적고 "탐색적"이라고 표시한다.
- CI는 Wilson(E7)으로 낸다. 0건이면 rule of three(E8)를 쓴다.
- 행 단위 지표는 가이드북과 비교할 때만 부록에 넣고 "유사반복(독립 아님)"이라고 각주를 단다.
- 에피소드 안의 불확실성은 버스트 단위 block bootstrap(E9)으로 보인다. 예: 탐지율의 버스트 재표집 구간.

**자동 슬라이스 탐색 도구의 쓰임새.** 21개 이상 버스트로는 통계적 검정력이 없다. 그래서 확인용이 아니라 "가설 생성용"으로 쓴다.
- Slice Finder(B1): 효과크기 φ와 Welch t-검정, α-investing. 정상 쪽 FP 분석(530버스트)에는 조금 쓸 만하다.
- RAI Error Analysis(B3): 오류 트리와 히트맵. 시각화에 좋다.
- pysubgroup(B6).
- 발견한 슬라이스는 "사전 정의 슬라이스와 일치하는가"로만 보고한다.
- Domino(B2)는 교차모달 임베딩용이라 쓰지 않는다.

**예상 결과(3.1 기반, 가설).**
- FN: 조용한 이상 버스트(#4, #20, #21)에 몰린다. 진폭 기반 모델은 이를 놓친다. 전류 동역학을 쓰는 모델은 잡지만, 그 이유는 계측 의심 특징이다.
- FP: 형태와 동역학에 민감한 모델(LSTM-AE, 다특징 IF)이 정상의 조용한 구간과 그 전환 시점, 짧은 버스트, 버스트 공백을 넘는 창에서 오경보를 낼 가능성이 있다. 진폭 단측 규칙은 조용한 구간에서 오경보를 내지 않는다(3.1(h)).

### 3.4 교란·지름길 검정 모음 (반증 시험)

"교란이 없음"은 증명할 수 없다(C5의 조건 논의). 대신 **교란이 있었다면 실패했을 시험**을 여러 개 통과했다고 보인다. 실행 순서대로 정리했다.

| ID | 시험 | 방법 | 통과 기준(예) | 근거 |
|---|---|---|---|---|
| T1 | 분석 단위 공개 | 행, 버스트, 운전 구간, 에피소드, 날의 위계 표 | 표 제시 | E4, E6 |
| T2 | **정상 대 정상 C2ST**(음성대조 라벨) | 정상 시간 블록끼리, 특히 조용한 구간을 같은 분류기로 분리 | 결과 해석: "분리 가능성 ≠ 고장 탐지"를 수치로 보임(3.1(g): 0.98–0.99) | C7, C8, C4 |
| T3 | 음성대조 특징 | 버스트 길이, 공백, ms 위상만으로 파일 분리 | AUC 0.5 근처(현재 0.44–0.62) | C5 |
| T4 | 부하 매칭 비교 | 전류 진폭 ±15% 또는 k-NN 매칭으로 진동의 조건부 분위 산출 | 이상 버스트 대부분이 정상 조건부 최댓값보다 큼(현재 13/17) | C11 |
| T5 | positivity 점검 | 정상 지지 범위(전류 진폭, 운전 구간) 밖의 이상 버스트 목록 | 해당 버스트(#15, #21)는 "판정 보류"로 따로 보고 | C12 |
| T6 | 특징군 제거·재학습 | 3.2-6의 다섯 군 | 진동 군만으로도 성능 유지. 전류 동역학 의존은 경고 | A11, E13 |
| T7 | **계측 스트레스 시험** | 정상 시험 구간에 샘플 시각 지터(0–5 ms) 주입(전류는 60 Hz 근처 사인파 모형으로 재샘플, 또는 앨리어스 위상 교란), 센서 이득 ±10–20%, 전류 진폭 ±20% 변환 → 오경보율 곡선 | 현실적 범위의 변환(지터 1–2 ms, 이득 ±10%)에서 오경보가 늘지 않음 | C1(o.o.d. 검증), A18 |
| T8 | 정상 운전 변화 시험 | 바쁜 구간으로만 학습하고 조용한 구간으로 시험(leave-regime-out) | 조용한 구간 오경보 0 또는 시간당 상한 보고 | D9, E3 |
| T9 | 정상 행동 모델 불변성 | 진동 ~ f(전류 진폭)을 정상 바쁜 구간과 조용한 구간에 각각 적합. 잔차 분포가 같은지 확인 | 두 구간 잔차 분포 차이가 작음 → 잔차 점수를 신뢰 | C10, D1–D3, D7 |
| T10 | 순열 검정 | (i) 버스트 블록 순열로 만든 라벨 순열 귀무분포(Test 1). (ii) Test 2 | Test 1은 "파일 구별"만 보증함을 명시. Test 2는 상호작용 판단에 씀 | C6 |
| T11 | 설명 감사 | 이상 버스트 SHAP 상위 특징이 계측 의심 군인지 확인 | 상위 특징이 진동 진폭이나 부하 대비 진동 | C2, A17, A18 |

- T7은 이 과제의 핵심 문구("정상적인 운전 변화를 이상으로 판단하는 오경보")에 직접 답하는 실험이다. 창의성 항목(도메인 지식, 불확실성)에서도 차별점이 된다.
- 단, 변환 범위는 근거가 약한 가정이므로 "민감도 분석"으로 표현한다.
- **매개변수 함정(C13).** 고장이 내부 누설을 늘려 같은 압력에서 전류(토크)를 바꾼다면, 전류는 고장의 결과(매개변수)다. 전류로 매칭하면 고장 효과의 일부를 지우게 된다. 이번 데이터에서는 이상 쪽 전류 진폭이 정상과 비슷하거나 약간 낮다(AUC 0.315). 그래서 매칭이 과보정했을 위험은 작아 보인다. 이 점을 보고서에 한 줄로 밝힌다.

### 3.5 "에피소드 1개, 다른 날" — 정직한 보고 체크리스트

REFORMS(F1)의 8개 모듈, 누수 8유형(F2), TRIPOD+AI(F3), Model Card(F4), Datasheet(F5)를 우리 과제에 맞게 압축했다. 보고서 부록에 표로 넣고 각 항목에 해당 절과 쪽수를 적는다. REFORMS도 "보고 위치 기재"를 권고한다.

| # | 항목 | 우리의 구체 조치 | 출처 |
|---|---|---|---|
| 1 | 주장 대상 분포 명시 | "이 프레스, 이 펌프의 7/12 야간 정상 운전 대 7/17 이상 에피소드"로 한정. 다른 고장 유형, 설비, 계절은 범위 밖 | REFORMS 1a, 8b |
| 2 | 데이터 출처·시점·라벨 과정 | 수집일, PLC/센서 수집, 10 Hz 버스트, 단위 미상, 라벨 = 파일 단위 "장비 고장 여부" | REFORMS 3a, Datasheet(Collection, Labeling) |
| 3 | 표본 크기와 결과 빈도 | 행, 버스트, 에피소드 수를 모두 적고 이상 유효 n = 1 에피소드라고 명시 | REFORMS 3e, TRIPOD+AI 10 |
| 4 | 결측, 중복, 이상치 | 중복 타임스탬프 1건, 버스트 공백 분포, 짧은 버스트 처리 규칙 | REFORMS 3f, 4a–4b |
| 5 | 전처리 흐름도 | 버스트 분할 → 버스트 안 창 → 특징 → 스케일러(학습 정상만 fit) | REFORMS 4c |
| 6 | 분할과 독립성 | 정상은 시간 블록 분할. 창은 버스트를 넘지 않음. 분할 경계에서 창 겹침 금지. 이상 에피소드는 최종 평가 1회 | REFORMS 5c, 6b, F2 L1.4/L3.2, E3, E4 |
| 7 | 시험 정보 누수 금지 | 임계값, 하이퍼파라미터, 특징 선택에 이상 데이터를 쓰지 않음(쓰면 명시하고 별도 표기). 가이드북 방식과 차이 설명 | REFORMS 6a, F2 L1.1–L1.3 |
| 8 | 특징의 정당성 | 날짜, 시각, 수집 패턴, 전류 동역학의 정당성 논의. 계측 의심 특징 분리 | REFORMS 6c, F2 L2 |
| 9 | 기준선 비교 | 한 줄 진폭 규칙, 가이드북 LSTM-AE 재현, 우리 모델 | REFORMS 5f, E1(triviality) |
| 10 | 지표 선택 근거 | 이벤트 단위 탐지, 첫 경보까지 시간, 오경보/시간을 주 지표로. 행 F1은 부록. point-adjust 미사용 | REFORMS 7a, E2 |
| 11 | 불확실성 | Wilson CI, 포아송 상한, 버스트 block bootstrap. "1 에피소드라 일반화 오차는 추정 불가" 명시 | REFORMS 7b, E5, E7–E9 |
| 12 | 군집 간 이질성 | 운전 구간별 성능(바쁜/조용한), 부하 3분위별 | TRIPOD+AI 12d, Model Card Factors |
| 13 | 불균형 처리와 재보정 | 과표집 등을 쓰면 이유와 방법을 적고, 확률 재보정 여부를 명시 | TRIPOD+AI 13 |
| 14 | 확률 출력의 의미 | "P(고장)"은 이상 사례 1건으로 보정할 수 없음. 정상 기준 초과확률(conformal p-value, 블록 단위)이나 정상 분위로 정의하고 그 한계를 명시 | E11, TRIPOD+AI 15 |
| 15 | 설명과 인과 해석 구분 | "모델 점수에 기여"라고만 쓰고 "고장 원인" 단정 금지. 상관 특징 주의 | A16 |
| 16 | 교란 시험 결과 | 3.4의 T1–T11 결과표 | C3–C5 |
| 17 | 외적 타당도와 한계 | 다른 날 정상 데이터 없음, 다른 고장 없음, 단위·수집 장비 미상, 시각 지터 가능성 | REFORMS 8a–8b, TRIPOD+AI 26 |
| 18 | 현장 사용 시 입력 품질 | 짧은 버스트, 지원 범위 밖 부하, 앨리어스 교란이면 "판정 보류, 점검" 상태로 | TRIPOD+AI 27a |
| 19 | 모델 카드 | 의도된 사용(조기경보 보조), 범위 밖 사용, Factors(부하, 운전 구간, 계측), 지표, 결정 임계값, 주의사항 | F4 |
| 20 | 재현 | 한 번에 실행하는 스크립트, README, 버전 고정(shap, sklearn, DIFFI) | REFORMS 2a–2e |

**"주장 장부(claims ledger)" 한 장.** 슬라이드 1장 또는 보고서 박스로 만든다.
- 주장한다: "이 에피소드는 같은 부하의 정상 운전 대비 상부 진동이 크고 저주파 성분이 많다. 우리 모델은 정상 운전 변화(조용한 구간)와 현실적인 계측 변동에서 오경보를 내지 않으면서 이를 X초 안에 경보한다."
- 주장하지 않는다: 다른 날이나 다른 고장으로의 일반화, P(고장)의 보정, 고장 원인 부위 확정.
- 근거와 한계는 T 시험 번호로 연결한다.
- 우리 상황과 같은 구조에서 실패한 사례(C3, C4)와 벤치마크 비판(E1, D11–D13, D16)을 근거로 붙이면 "몰라서 놓친 것"이 아니라 "알고 통제한 것"으로 읽힌다.

### 3.6 현장 활용으로 이어지는 형태 (오류 분석의 출구)

- **3-상태 출력**: 정상 / 이상 경보 / **판정 보류(미지 운전 상태)**.
  - 판정 보류 조건: 전류 진폭이 정상 지지 범위 밖(#21 같은 경우), 앨리어스 교란(계측 의심), 짧은 버스트.
  - 이는 T5와 T7의 결과를 운영 규칙으로 바꾼 것이다. 오경보를 줄이면서 놓침을 숨기지 않는다.
- **경보 지속 조건(k-of-n 버스트).** 3.1(i)에 따르면 버스트당 오경보율이 조금만 있어도 시간당 경보가 많아진다. k-of-n으로 시간당 오경보를 낮추고, 그 대가인 첫 경보 지연(이상 에피소드 기준 초 단위)을 표로 보인다.
- **점검 우선순위.** 경보 시 RBC나 SHAP 기여에서 "상부 우세 / 하부 우세 / 전류 결합"을 함께 보여 준다. 예: 상부 우세면 펌프 상부(구동 측) 체결과 소음 점검을 먼저. 실제 정비 매핑은 도메인 조사 결과와 맞춰야 한다.

---

## 4. 위험·한계·반론

1. **반증 시험은 교란의 부재를 증명하지 못한다.** 음성대조는 특정 편향 경로에만 민감하다(C5). T2–T11을 모두 통과해도 그날의 제품, 금형, 유온, 센서 재장착 같은 관측되지 않은 요인이 남는다. 보고서에서 "통과"를 "확증"으로 쓰면 오히려 감점 요인이다.
2. **외부 검증만으로는 부족하고 설명도 불안정하다.** DeGrave(C3)는 외부 검증이 지름길을 잡지 못할 수 있다고 했다. 그런데 설명 기법 자체도 상관 특징, 외삽, 작은 표본에서 흔들린다(A11, A16). 그래서 단일 설명을 근거로 쓰지 말고 TreeSHAP, DIFFI, 특징군 재학습 세 방법이 합의하는지로 판단한다.
3. **지터 가설은 검증되지 않았다.** 수집 장비, 샘플링 방식, 타임스탬프가 명목값인지 실측값인지를 모른다. 이상 시 실제 토크 맥동이나 전원 주파수 변화로도 같은 현상이 날 수 있다. "전류 동역학 = 계측 문제"라고 단정하지 말고 "계측에 민감해서 근거로 쓰기에 취약한 특징"으로 표현한다.
4. **전류를 부하로 보는 가정.** 역률, 전압 변동, 인버터 구동 여부에 따라 전류 진폭이 부하를 제대로 대리하지 못할 수 있다. 또 매개변수(bad control) 문제가 있다(C13). 펌프 형식(기어 펌프 추정)과 모터 구동 방식은 미확인이다.
5. **정상 안의 "조용한 구간"의 정체.** 정상 운전 변화(무부하, 다른 제품, 대기)일 수도 있고 다른 무엇일 수도 있다. 정상 라벨이 붙어 있으니 정상으로 간주하는 것이 원칙이다. 다만 "정상 운전 변화의 대표"로 일반화하는 것도 1건의 사례다.
6. **너무 많은 유보는 역효과를 낼 수 있다.** 심사위원은 모델 성능과 현장성도 본다. 유보는 주장 장부 한 장과 부록 체크리스트에 모으고, 본문은 실험 결과 중심으로 쓴다.
7. **채점 항목과의 긴장.** 채점 기준이 "F1 등"을 요구하므로 행 F1을 빼면 회피처럼 보일 수 있다. 그래서 행 F1도 보고하되(가이드북과 같은 조건 재현 포함), 단위 위계와 유사반복 주석을 단다.
8. **슬라이스 탐색의 다중비교와 과적합.** 21개 이상 버스트에서 나온 "FN 집중 조건"은 우연일 수 있다. 사전 정의 슬라이스만 본문에 쓰고, 자동 탐색 결과는 부록에 둔다.
9. **C2ST 수치의 낙관성.** 3.1(g)는 블록 안에서 무작위로 겹을 나눴으므로 인접 버스트 상관 때문에 AUC가 부풀었을 수 있다. 결론("정상끼리도 거의 완벽하게 분리됨")의 방향은 유지될 가능성이 크지만, 보고서 수치는 블록 CV로 다시 계산해야 한다.
10. **라이선스와 재현성.** DIFFI의 sklearn 수정 코드와 RAI Toolbox의 무거운 의존성은 원클릭 재현 점수를 떨어뜨릴 수 있다. 핵심 지표는 가벼운 의존성(shap, sklearn, numpy)으로 내고, 대시보드는 선택 사항으로 둔다.

---

## 5. 아직 확인 못 한 것

1. **수집 시스템 정보**: 샘플링 장비, 타임스탬프가 실측인지 명목인지, 지터 크기, 전원 주파수, 모터 구동 방식(직입 또는 인버터), 센서 종류와 단위. 이 정보 없이는 3.1(e)의 지터 가설을 확인할 수 없다.
2. **7/17(일) 10:51 에피소드의 실제 상황**: 고장 직전인지, 고장 중인지, 시운전인지, 정비 후인지. 에피소드 끝의 조용한 버스트(#20, #21)가 정지 과정인지. KAMP나 제공사 문의 필요.
3. **다른 날의 정상 데이터나 추가 이상 데이터** 존재 여부(KAMP 다른 버전).
4. 결론에 영향을 주는 미검증 문헌 내용: Bartelmus & Zimroz(D5), Zimroz et al.(D6), Worden et al.(D2), Kullaa(D4), Schlechtingen et al.(D8)의 본문(초록이 API로 제공되지 않음), Hendriks et al.(D11) 본문, CARE 점수(D16)의 정확한 공식, Miller et al. 1998(A4) 원문과 호수, Wu & Keogh(E1)의 최종 권·쪽, Lei et al.(E14)의 LOCO 세부.
5. 도구 동작: DIFFI 코드가 sklearn 1.8과 호환되는지, PyALE 최신 버전의 동작, RAI Toolbox 설치 크기와 Python 버전 호환성. 하나도 실행해 보지 않았다.
6. 가이드북 LSTM-AE 수치(정확도 97.51%, F1 0.7476)를 그대로 재현하면 FN과 FP가 어디에 몰리는지(정상 시험 구간에 조용한 구간이 들어가는 영향). 재현 실험으로 확인해야 한다.
7. 3.1(g) C2ST를 블록 CV와 시간 간격(gap)을 둔 분할로 다시 계산하는 것, T7 계측 스트레스 시험의 현실적 범위(이득 변화, 지터)를 정할 근거(센서와 DAQ 사양).
8. 전류 진폭과 펌프 토크·압력의 정량 관계(펌프 배제량, 모터 사양)는 도메인 문헌 확인이 필요하다(이 보고서에서는 검증하지 않음).
