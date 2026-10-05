---
title: 공개 분석·관련 기법 조사 — 프레스 유압펌프(KAMP 소성가공 예지보전)
created: 2026-10-04
updated: 2026-10-04
tags: [contest/k-ai-manufacturing]
source: GitHub 공개 레포 README·docs·PR 본문(gh api 읽기 전용, 2026-10-04 열람), Crossref·arXiv·출판사 서지 레코드, 웹 검색
status: seed
---

# 공개 분석·관련 기법 조사

관련 노트: [[제조데이터 경진대회 MOC]] · [[프레스_분석방향_아이디어]] · 보고서 원고 `report/final_v5.md`

표기 규칙
- **[1차]** 원문을 직접 읽음(레포 파일·PR 본문·Crossref/arXiv 레코드·PDF 본문)
- **[2차]** 검색 결과 요약이나 2차 자료로만 확인
- **[추정]** 내 해석. 확인된 사실이 아님
- 레포 내용은 2026-10-04 시점 기준이다. 대회 마감(10-08) 전이라 바뀔 수 있다.

---

## 0. 한눈에 (결론 먼저)

1. 같은 과제 ③을 공개 레포로 진행하는 팀이 적어도 9곳 있다. 가장 깊은 곳은 **ChoeHyeongSoo/KAMP-Manufacturing-AI**(3인, PR 27개)다. 이 팀은 **형식 누수(소수 자릿수·1.19209 격자)**, 앨리어싱, 버스트(최대 50행) 구조, 날짜 교락, 단일 사건, 고부하 오경보 집중, 조용한 이상 기록 3·19·20, 탐지 지연의 구조적 하한(버스트 간격 약 8초)을 **우리보다 먼저, 비슷하거나 더 많은 수치로** 정리했다. [1차]
2. 그래서 "형식 누수 발견", "기록 단위 구조", "사인 파형 적합", "지속성 규칙"은 우리만의 발견이라고 쓰면 안 된다. 사인 적합 잔차는 kimjaehyeonC/Kamp_AI도 핵심 피처로 쓴다(정상 중심 고정 NRMSE, AUC 1.000). [1차]
3. 우리가 앞서는 지점은 **평가의 정직성과 적용 조건 명세**다.
   - valid 선택을 해시로 잠갔고, 최종 모델이 잠금 선택에서 벗어난 경위를 공개했다. 다른 팀은 CV 반복이나 단일 시간 분할을 썼고, test를 잠근 곳은 없다.
   - 수집 조건 흔들림(시각 흔들림·이동량) 시험으로 무너지는 조건을 밝혔다. 다른 팀은 인공 고장 주입까지만 했다.
   - conformal 문턱으로 α를 명시했다. 다른 팀은 q99·q0.9999·"val 오경보 1%" 같은 경험 분위수를 썼다.
4. 보완할 점도 있다. 경쟁팀은 **사건 단위 탐지·탐지 지연·시간당 오경보**를 보고하는데, 우리 헤드라인은 행 F1 1.000이다. 행 F1 옆에 사건 1/1, 정상 오경보 0/N과 **Clopper-Pearson 95% 구간**, 사건 시작 기준 지연(버스트 간격 하한 포함)을 함께 적어야 한다.
5. 도메인 차별 포인트가 하나 있다. 정확히 10 Hz로 찍은 60 Hz 상용 전류는 0 Hz 근처로 접혀야 한다. 겉보기 0.60 Hz가 나오려면 전류 기본파가 59.4/60.6 Hz(인버터 구동 등)이거나 실제 표본 간격이 명목값과 약 1% 달라야 한다. 이상 구간의 0.22 Hz도 같은 이유로 **계측(클럭) 차이 가설**과 맞물린다. CHS 팀은 "60 Hz가 0.600 Hz로 접힘"이라고만 썼다. kimjaehyeonC는 "클럭 미세 편차" 가능성을 언급했다. [1차 + 추정]
6. 문헌상 근거도 있다. 우리처럼 단순하고 해석 가능한 모델이 딥모델과 비슷하거나 낫다는 연구가 있다(Audibert 2022, Sarfraz 2024). 벤치마크의 "자명성(triviality)" 결함을 짚은 연구도 있어(Wu & Keogh 2023) 형식 누수 1줄 규칙을 설명하기 좋다. PCA T²/SPE, CUSUM, SPOT, 사건 단위 지표, 이항 신뢰구간은 보고서에 바로 넣을 수 있다.

---

## A. 같은 데이터를 다룬 공개 분석

### A.1 조사 대상

| # | 레포/글 | 만든 날 → 마지막 push | 성격 | 이 데이터? |
|---|---|---|---|---|
| 1 | [ChoeHyeongSoo/KAMP-Manufacturing-AI](https://github.com/ChoeHyeongSoo/KAMP-Manufacturing-AI) | 09-26 → 10-02 | 3인 팀, 노트북 12·리포트 10·PR 27 | 예(과제 ③) |
| 2 | [kimjaehyeonC/Kamp_AI](https://github.com/kimjaehyeonC/Kamp_AI) | 09-22 → 10-03 | EDA·피처·규칙 기준선, 모델 미완 | 예 |
| 3 | [MinSeok-Good/press-equipment-anomaly-detection](https://github.com/MinSeok-Good/press-equipment-anomaly-detection) | 10-01 | 지도학습(CatBoost) 포트폴리오형 | 예 |
| 4 | [yerinnn24/kamp](https://github.com/yerinnn24/kamp) | 10-02 | PatchTST 마스킹 재구성 | 예 |
| 5 | [sunwoocodes/KAMPact](https://github.com/sunwoocodes/KAMPact) (추가 발견) | 09-26 → 10-03 | 다중 스케일 마할라노비스 + 스트리밍 | 예 |
| 6 | [Hankookiniayo/kamp2026](https://github.com/Hankookiniayo/kamp2026) (추가) | 09-22 | 비지도+지도 하이브리드 | 예 |
| 7 | [ekhwn0430/KAMP](https://github.com/ekhwn0430/KAMP) (추가) | → 10-03 | EDA 위주, 물리 기반 지표, 지도 모델 | 예 (README 없음) |
| 8 | [goddesse12-coder/pump-ai-team](https://github.com/goddesse12-coder/pump-ai-team) (추가) | 10-01 | 협업 골격·분할 도구만, 성능 수치 없음 | 예 |
| 9 | [yoni0345678910/kamp-press-anomaly-detection](https://github.com/yoni0345678910/kamp-press-anomaly-detection) (추가) | 09-24 → 10-02 | RF + 대시보드 앱, README 없음 | 예 |
| 10 | [yskim9574/DFclass-2023](https://github.com/yskim9574/DFclass-2023) `LSTM_pressformingmachine_anomaly` (추가) | 2023-09 | 강의용 가이드북식 LSTM-AE | 예(대회 무관) |
| — | [jhy5317/pre-kamp](https://github.com/jhy5317/pre-kamp) | 09-10 | **배터리팩 레이저 용접** 데이터 연습 | **아님**(범위 밖) |
| — | [goodstream 블로그 2025-10-20](https://goodstream.co.kr/docs/blog/posts/2025-10-20-using-kamp/) | — | KAMP 플랫폼 소개글 | **아님**(이 데이터 분석·코드·수치 없음) |

- 검색 경로: GitHub 코드 검색 `press_data_normal`, 저장소 검색(`KAMP press`, `kamp hydraulic pump`, `fine blanking`, `K-인공지능 제조데이터`), 웹 검색. 다른 블로그·논문에서 이 데이터를 분석한 공개 글은 찾지 못했다. [1차]
- 공식 가이드북 모델은 LSTM-Autoencoder 정상 학습 + 재구성 오차 문턱이다(볼트 `가이드북_소성가공_원문확인.md` p14~18). #10이 같은 틀을 그대로 쓴다.

### A.2 진단 항목 비교 (○ 찾음 / △ 부분 / × 언급 없음 / — 문서가 없어 미확인)

| 항목 | 우리 | #1 CHS | #2 kimjh | #3 MinSeok | #4 yerin | #5 KAMPact | #6 Hankook | #7 ekhwn |
|---|---|---|---|---|---|---|---|---|
| 형식 누수(소수 자릿수) | ○ 행 F1 0.992 1줄 규칙 | ○ AUC 1.000 → 0.566 | × | × | × | × | × | × |
| 전류 1.192 격자 | ○ | ○ 0.19% vs 99.67% | × | × | × | × | × | × |
| 전류 DC(평균) 치우침 | ○ \|평균\|>표준편차 9/17 | ○ \|DC\| AUC 0.94 → **평균 제거** | △ 정상 중심 고정 | × (평균을 피처로 씀) | △ RevIN | × (평균을 피처로 씀) | ○ 날짜 오프셋 의심 → 제외 | × (평균 피처) |
| 앨리어싱(0.60 Hz) | ○ 원인 가설로 둠 | ○ "60→0.6 Hz" | ○ 클럭 편차 가능성 | × | △ 교류만 | × | △ | △ |
| 버스트(≤50행)·약 8초 주기 | ○ | ○ 7.958 s, duty 42% | ○ 7.96/8.13 s | ○ | ○ | ○ | ○ | ○ |
| 날짜·세션 교락 | ○ | ○ | ○ 5일 9시간 34분 | ○ | ○ | × | ○ | — |
| 단일 사건(21조각 = 1건) | ○ | ○ | ○ | △ "usable 17" | × | × **21 event로 셈** | ○ | — |
| 운전 상태(고·저부하/유휴) | ○ 고부하 오경보 | ○ 2상태, 실루엣 0.599 | ○ V자 딥 | × | ○ 저진폭 구간 | ○ Idle 라벨 | ○ | ○ |
| 조용한 이상 3·19·20 | ○ | ○ | ○ | △ 20만 | × | △ | △ | ○ |
| 탐지 지연 구조적 하한 | △ 0.0초(R1 승계) | ○ 7.96 s + 첫 창 0.9 s | ○ "조기 = 사이클 단위" | × | × | ○ 사건 지연 | △ | × |

### A.3 레포별 메모

#### #1 ChoeHyeongSoo/KAMP-Manufacturing-AI — 가장 강한 경쟁 사례 [1차]
- **진단**
  - 정상 599·이상 21 세그먼트로 셌다(우리는 600·21. 동일 시각 중복 1행 처리 차이로 보임 [추정]).
  - **형식 누수**: \|DC\| 단독 AUC 0.9443(AI0)/0.9198/0.8911. 전류 1.19209 배수 비율이 정상 0.19%, 이상 99.67%다. 진동 소수 자릿수 최빈값은 정상 6자리(약 90%), 이상 8자리(AI0 44.0%·AI1 65.7%)다. 1.19209 ≈ 10 V/2²³×10⁶이라는 24-bit ADC 최소 단위(LSB) 가설도 냈다(PR #1, #7).
  - **차단 검증**: 진동 6자리 반올림, 전류 격자 양자화, 세그먼트 평균 제거를 적용했다. 그러자 형식 피처 AUC가 1.000에서 진동 0.566·전류 0.597로 내려갔다(PR #6·#7).
  - **앨리어싱**: 정상 전류 사인 적합 f 0.6001 Hz(IQR 0.5987~0.6011), R² 0.9965. 이상은 R² 0.46이다. 결함 주파수 분석은 불가로 결론 냈다.
  - **운전 상태**: k-means 2개(고부하 43.18%/저부하 56.82%). 오경보는 27개 모델 중 19개에서 고부하에 집중됐다.
  - 정상 의심 세그먼트는 26개(4.3%)다. 마지막 시간 블록은 저부하 85.71%로 분포가 이동한다.
  - 이상 AC 추이에 유의한 경향이 없어 "점진적 열화" 서술을 **철회**했다(PR #18).
  - 19·20의 "전류 확실 이상"은 DC 기준이다. 평균을 빼면 AC RMS 59.6/35.2로 정상 중앙값 100.5보다 오히려 조용하다(PR #13·#14).
- **전처리**: 형식 통일 + 세그먼트 평균 제거 + 세그먼트 경계 안 1·2·3초 창(0.5초 이동). 피처는 33열(진폭 18·형상 9·사인 잔차 3·관계 3)이다. 사인·관계 피처는 세그먼트 단위로 한 번 계산해 창마다 그대로 붙였고, 날짜 교락 후보로 분리 보고한다.
- **모델**
  - 규칙 6종: 크기 rule1 AUC 0.786, 크기×방향 rule3 0.870.
  - 9종: CNN(DeepAnT)·LSTM-AD·MTAD-GAT·GDN·DeepSVDD·MCD·OCSVM·HBOS·COPOD.
  - CNN+LSTM AE와 PCA 선형 AE.
  - 2단계 경보 설계(주의 = OR, 경보 = CNN AND MCD).
- **분할·검증**: 세그먼트 GroupKFold 5겹 + 정상 시간 블록 전진 4겹, 문턱은 train 정상 q99. 세그먼트 단위 부트스트랩 1,000회로 AUC CI와 쌍 차이 CI를 냈다(rule3−rule1 +0.0896 [0.042, 0.143]).
- **점수**
  - 주력 모델 AUC 0.995~1.000, fpr_segment 2.6~7.7%다.
  - PCA AE fpr_segment는 0.041로 CNN-LSTM AE(0.077)보다 낮다. 그래서 "복원 계열은 선형으로 충분하다"고 결론 냈다(PR #25).
  - 합성 이상 4종 × 강도 4단계를 FPR 1%에서 넣었을 때 탐지율은 0.23~0.31이다.
  - AND 결합은 오경보 0.0%/0.1%로 실제 이상을 100% 잡았지만, 합성 이상 탐지는 0.334에서 0.027로 줄었다(PR #22).
- **지연**: 첫 1초 창이 완성되는 0.9초가 곧 지연의 최솟값이다. 사건 시작 기준 체감 지연은 9.68초(1건 관측값)이고, 구조적 하한은 버스트 간격 중앙값 7.96초다. 세그먼트 오경보 7.67%를 시간당 약 35건으로 환산했다(PR #8).
- **도메인**: 가이드북 7·8·9·10·11쪽으로 센서 위치를 바로잡았다. 근거 없이 단정했던 "센서가 모터 몸체에만 있다"를 철회했고(PR #20), 탐지 대상은 "모터-펌프 구동부 이상"으로 표현한다. 근거 수준 표기 [데이터]/[추정]/[가정]도 쓴다.
- **한계 인식**: 이상 1건, 날짜 교락, 브로드캐스트 피처의 교락 위험, error_cases와 metrics 시드 불일치 6건까지 스스로 공개했다.
- **평가**: 진단·통계 엄밀성은 우리와 동급 이상이다. 다만 ① 세그먼트 평균 제거로 전류 오프셋(16~20 기록의 가장 큰 차이)을 아예 버렸고, ② test를 잠그지 않았으며 CV만 썼고, ③ 수집 조건 흔들림 시험이 없다. [추정]

#### #2 kimjaehyeonC/Kamp_AI [1차, docs 기준]
- **진단**
  - 세그먼트 길이 상한 50, 주기 정상 7.96초/이상 8.13초, 수집 가동률 43%/36%.
  - "현재 조각 길이 ↔ 다음 공백" 상관이 −0.72~−0.98이다. 그래서 공백은 결측이 아니라 수집 듀티라고 봤다. 버퍼·트리거 가설은 반증 기록으로 남겼다.
  - 두 파일은 5일 9시간 34분 떨어져 있어 날짜와 완전히 교락된다.
  - AI0 lag-1 자기상관이 −0.03에서 0.69로 바뀐다.
  - 전류 ac1 AUC 1.000은 "클럭 편차로 날짜가 바뀌면 달라질 수 있다"는 **경고 신호**로 해석했다.
  - **형식 누수 언급 없음**.
- **피처**
  - 정상 공통 주기 0.6000 Hz(5~95% 0.5973~0.6028)로 고정한 **정상 중심 고정 사인 잔차(NRMSE)** 가 n≥10에서 AUC 1.000이다. 3·19·20을 정상 최대의 14·19·50배로 잡는다. n<10인 4개는 미해결이다.
  - 그 밖에 band_purity 0.995, env_cv 0.978, ai1_peak_hz 0.952.
  - 전류로 예측한 AI1 rms의 잔차(cur_vib_resid)가 "조용한" 유형 16~20을 잡는다.
- **교훈 기록**: AUC 순위와 운영점(오경보 0) 순위가 다르다(ai0_ac1은 AUC 0.962인데 FP=0에서 8/17). 길이 10~19 구간에서 rms AUC가 0.52로 무너진다.
- **분할**: 정상 시간순 70/30에서 내부 오경보 0~0.6%. 모델 단계 계획은 60/20/20, N중 M 지속성 규칙, CUSUM·EWMA 검토다.
- **도메인**: "조기"를 "주기점검 대신 발생 즉시(사이클 ≈8초) 자동 인지"로 정의하고, 전조 탐지는 이 데이터로 증명 불가라고 명시했다.
- **평가**: 우리 3성분 중 사인 파형 적합과 거의 같은 아이디어다. 형식 누수를 다루지 않았으므로 정밀도 차이에 대한 민감도는 확인되지 않았다. [추정]

#### #3 MinSeok-Good [1차]
- 지도학습이다. 1초 창(겹침 없음), 센서별 mean·std·RMS·min·max 15피처로 LR·RF·CatBoost를 돌렸다.
- **원시 평균(전류 DC 포함)을 그대로 피처로 쓴다.** 형식 통일은 없다.
- StratifiedGroupKFold(세그먼트)를 10시드 × 5겹으로 돌렸다. CatBoost 튜닝 창 F1은 0.944±0.008, PR-AUC는 0.979다. 세그먼트 평균 확률 F1 0.997은 "참고"로만 둔다.
- 오류 사례
  - 세그먼트 16: 창별 확률이 0.014 → 0.999로 오른다. 기록 안에서 상태가 바뀐다.
  - 세그먼트 20: SHAP을 보면 전류 평균 +, 저진동 −로 기여가 맞서 미탐이 났다.
- 한계(세션 교락, 개발 CV라 독립 test 아님)를 명시했다. 현장 활용으로 점검 템플릿·CMMS 연계 워크플로와 국내외 사례 50개 조사를 제시했다.

#### #4 yerinnn24/kamp [1차]
- PatchTST 마스킹 재구성(RevIN, 패치 40% 마스킹, 추론 마스크 8개 평균)이다. 정상만 학습하고 정상은 시간순 80/20, 경계는 세그먼트 시작점에 맞췄다.
- 행 단위 F1: 기준 0.909 → 패딩 인식 0.919 → 후처리(갭 가중 + 연속 2회) **0.936**. FPR 1.00% → 0.38%, 최악 모드 FPR 1.24%다.
- 운전 조건별 문턱(저진폭/정상진폭)은 오히려 나빴다(stage6).
- 오류 분해가 쓸 만하다. 기록 시작 0~4번째 행의 FP는 3.95%로, 5번째 이후(0.50%)보다 훨씬 높다.
- 형식 누수 언급은 없다. 날짜 차이는 RevIN 창 정규화로 대응했다고 서술한다.

#### #5 sunwoocodes/KAMPact [1차]
- 정상 안 Idle 구간(00:59:53.992~01:11:32.588)에 수동으로 라벨을 붙였다. Idle은 학습·보정에서 빼고 오경보만 따로 잰다.
- 피처는 1.0초·0.5초 창 + 행 단위로 16개(mean·std·RMS·ptp·slope × 3 + 상하 상관). **평균을 그대로 쓴다.**
- signed-log 변환 + Ledoit-Wolf 마할라노비스 검출기 3개를 OR로 묶고 연속 2회(P2)로 확정한다. 문턱 q = 0.9999.
- 그룹 5겹 × 5반복에 실제 대시보드 검출기를 행 단위로 돌리는 스트리밍 CV를 했다. 사건 탐지 94.29±2.13%, 지연 0.524초, F1 0.852, 정상 오경보 사이클 0.90%. 분위수 민감도 표도 있다.
- **21개 세그먼트를 21개 고장 사건으로 셌다.** 실제로는 1건이다. 한계에서 "독립 holdout 없음, ±는 반복 표준편차이지 CI가 아님"을 밝혔다.

#### #6 Hankookiniayo/kamp2026 [1차]
- 비지도(IF·OCSVM·LOF·LSTM-AE)와 지도(LR·RF·LightGBM·XGBoost·CatBoost)를 비교하고, 최종은 IF 점수 + 부스팅 확률의 하이브리드다.
- 분할은 구간 단위·시간순(정상 6:2:2, 이상 5:2:3)이다. 문턱은 val 정상 창 오경보율 1%로 잡았다. 경보는 3단계(주의/경고 2-of-3/점검)다.
- **전류 평균을 날짜 오프셋 누수 후보로 보고 기본 피처에서 뺐다.** 포함·제외 ablation도 했다. 전류 평균은 이상 사건 초반과 후반에 부호가 뒤집힌다(train AUC 0.54 → test 0.02).
- 피처셋별 IF test PR-AUC: 진동만 0.78 → +부하 0.91 → +전류 파형 0.97.
- 부하 전환 구간 창 오경보율은 2.4%로, 전환 없는 구간(0.8%)의 약 3배다. 부스팅 3종은 val PR-AUC가 모두 1.000이고 차이는 test FPR(0.9~3.7%)에서만 났다.

#### #7 ekhwn0430/KAMP [1차, `코드결과.md` 기준]
- 창 크기별 기준선이 있다. 1초 창은 이상 17/21 세그먼트가 판정 가능하고, 정상 행 오경보는 0.50%다.
- **H1**: 전류로 진동을 회귀한 잔차(AI1 R² 0.884)다. 가설을 쌓아 가는 누적 설명표(RMS 235행 → +H1 380행 → … 428행, 정상 오경보 0.6% → 6.3%)가 있다.
- 지도 모델 test F1은 최대 1.000이다(RF, +전류 크기). 전류 평균을 쓴다.
- `05_Physics_Informed`에 PORD·CNVG·OCVT 등 물리 기반 지표 폴더가 있다. 이름만 확인했고 내용은 미열람이다.

#### #8 goddesse12-coder/pump-ai-team [1차]
- 아직 성능 수치는 없다. 원칙은 정상·이상 각각 시간순 70/15/15, 파일 해시로 팀 간 비교, "조각은 수집 단위이며 독립 고장 사건이 아니다"이다.
- 계획은 LR/LightGBM → 부하로 예상한 진동의 잔차 → 지속 경보 → 센서 불일치 → PCA/IF/AE 순이다.

#### #9 yoni0345678910 [1차, 코드만]
- RF 지도 모델에 18피처(전류 평균 포함), 정상 중앙값·IQR 기반 건강 지수, 앱 코드가 있다. README·수치는 없다.

#### #10 yskim9574/DFclass-2023 (2023 강의) [1차]
- 가이드북식 LSTM-AE다. 절댓값 변환, MinMax, 정상 앞 15,000행 학습을 쓴다.
- **공백을 무시하고 20행 창을 만들었다.** 문턱은 **이상을 섞은 검증셋**에서 precision = recall이 되는 지점이다(라벨로 문턱 결정).
- "가이드북 기본 틀이 버스트 공백·라벨 사용 문제를 안고 있다"는 대조 사례로 쓸 만하다.

### A.4 경쟁팀이 이미 찾은 것 — 우리 '독자 발견'으로 쓰면 안 되는 것

| 항목 | 먼저·함께 찾은 곳 | 보고서 서술 방식 제안 |
|---|---|---|
| 소수 자릿수·1.192 격자 형식 누수 | #1(AUC 정량, 차단 검증까지) | "우리 진단에서도 확인"으로 쓴다. 우리 고유 기여는 아래 A.5-1 |
| 최대 50행 기록, 약 8초 주기 | #1·#2·#4·#5·#6·#7·#8 거의 전부 | 공통 사실로 짧게 쓴다 |
| 날짜·세션 교락, 단일 사건 | #1·#2·#3·#6 | 공통 사실 |
| 0.6 Hz 앨리어싱 | #1·#2 | A.5-5의 "왜 0.6인가" 해석으로 차별 |
| 사인 파형 적합 잔차 | #1(사인 잔차 AUC 0.991), #2(정상 중심 고정 NRMSE AUC 1.000) | 3성분 중 하나로 담담히. 차별은 3성분 결합 + conformal |
| 지속성·N중 M 규칙 | #2(계획), #4(run≥2), #5(P2), #6(2-of-3) | R1은 "기록 간 래치(공백 60초 승계)"라는 점이 다르다 |
| 크기 경보를 파형으로 확인(교차 확인) | #1 JIW 2단계(AND), #6 하이브리드 | R2의 트레이드오프(진동형 고장 −23.7%p)는 #1의 AND 결과(합성 탐지 0.334 → 0.027)와 같은 방향이다 |
| 고부하 오경보 집중 | #1, #6(부하 전환 3배) | 공통 |
| 인공 이상 주입 | #1(4유형 × 4강도) | 우리는 "분할 변경 + 수집 조건 흔들림"까지 넓힌 점을 강조 |
| PCA T²/SPE | #1(조용한 이상도 q99의 3.1~4.3배) | 우리 베이스라인에 없으면 추가 검토(B.1) |

### A.5 우리 보고서가 차별화할 점

1. **누수 설명을 "1줄 규칙"과 "같은 분포 증명"으로 끝까지 닫은 것**
   - 학습 없는 "자릿수 > 6" 규칙만으로 행 F1 0.992가 나온다. 정밀도를 맞추면 자릿수 분포가 같아진다(4자리 89.5% 대 90.2%).
   - Wu & Keogh(2023)의 "자명성(triviality)" 결함, Kaufman et al.(2012)의 누수, Geirhos et al.(2020)의 지름길 학습 개념으로 이름을 붙이면 학술적 무게가 생긴다.
   - #1은 AUC로 보였다. 우리는 운영 지표(F1)와 분포 동치로 보인다.
2. **전류 오프셋을 버리지 않고 검증한 것**
   - #1은 세그먼트 평균을 빼서 지웠고 #6은 피처에서 뺐다. #3·#5·#7·#9는 아무 처리 없이 썼다.
   - 우리는 정밀도만 맞추고 치우침을 지표(\|평균\|>표준편차)로 쓴다. 이동량 시험(V5)으로 "오프셋을 이상으로 잡는 것인지"를 직접 시험했다.
   - 보고서에 이 선택의 근거와 위험(FM6 계측 이상과 구분 불가)을 한 문단으로 명시할 것.
3. **시간순 train/valid/test + 해시 잠금 + 이탈 공개**
   - 다른 팀은 CV(#1·#3·#5)나 단일 시간 분할(#2·#4·#6·#8)을 썼다. test를 잠근 곳은 없다.
   - #3·#5는 "개발 CV라 독립 검증 아님"을 인정만 했다. 우리는 코드로 강제했고 이탈 경위(B 0.995 → 최종 1.000)까지 냈다.
   - 이것은 심사 6번(재현성)과 5번(창의성) 양쪽에 걸리는 강점이다.
4. **"무너지는 조건"을 실험으로 밝힌 적용 조건표**
   - 수집 조건 흔들림(시각 흔들림 0.1 ms에서 정상 경보율 B 35.2%), 진동 단독 고장, 진폭 감소를 실험했다.
   - #1의 합성 주입은 탐지율만 보고 수집 조건을 흔들지 않았다. 운영 범위(operating envelope)를 표로 준 팀은 없다.
5. **앨리어싱의 물리적 해석**
   - 10 Hz로 정확히 표본화하면 60 Hz는 0 Hz로 접힌다. 겉보기 0.60 Hz는 기본파가 10의 배수 ± 0.6 Hz(예: 59.4/60.6 Hz, 인버터 구동)이거나 실제 표본 간격이 명목값보다 약 1% 다를 때 나온다.
   - 유도전동기 상용 구동이라면 부하가 바뀌어도 고정자 전류 기본파는 바뀌지 않는다. 그렇다면 이상 구간의 0.22 Hz는 **고장보다 수집 클럭·구동 조건 차이**로 설명하는 편이 쉽다. [추정]
   - #1은 실효 fs 10.0000 Hz(타임스탬프 기준)를 보고했다. 이 둘을 합쳐 "타임스탬프가 실제 표본 시각인지"를 주최 측 확인 질문으로 올리면, 도메인 이해와 교락 분석이 함께 강해진다.
6. **소표본 정직성 수치화(아무도 안 함)**
   - 사건 1/1의 Clopper-Pearson 95% 구간은 [0.025, 1.000]이고, 이상 기록 21/21은 [0.839, 1.000]이다.
   - 정상 오경보 0/N의 상한은 1−0.025^(1/N)이다(N = 120이면 3.0%, 200이면 1.8%).
   - "1.000이 무엇을 증명하지 못하는가"를 숫자로 보여 준다(B.8).
7. **단순 모델 정당화를 문헌으로**
   - 경쟁팀은 PatchTST·MTAD-GAT·CNN-LSTM AE 같은 복잡한 모델을 늘어놓는다. 우리는 3성분 + 규칙 2개다.
   - Audibert et al.(2022)과 Sarfraz et al.(2024)이 "단순 기준선이 딥모델과 대등하거나 낫다, 딥모델은 사실상 선형 사상을 배운다"를 보였다. #1도 내부적으로 "선형으로 충분"을 얻었다.

### A.6 채택할 만한 기법 (출처 표기 전제)

블라인드 평가라 경쟁 레포를 본문에 인용하는 것은 부적절할 수 있다. 채택하면 기법 자체는 B장의 문헌으로 인용하고, 착안 출처는 내부 기록(이 노트)에 남긴다.

| 기법 | 착안 출처 | 우리 보고서 적용 |
|---|---|---|
| 탐지 지연을 "기록 안 지연"과 "사건 시작 기준 지연"으로 나누고 구조적 하한(버스트 간격 중앙값 약 8초)을 함께 적기 | #1 PR #8, 02 리포트 §8 | 현재 "첫 행 0.0초"는 R1 승계 효과다. 사건 첫 기록 기준 지연과 하한을 별도 행으로 |
| 기록 오경보율 → 시간당 오경보 건수 환산(시간당 버스트 약 452회) | #1 PR #8 | 정상 오경보 0/N을 "시간당 상한 x건"으로 바꿔 현장 언어로 |
| 운전 상태별 오경보율 + Fisher/BH 검정 | #1 31 리포트 | R2 효과를 고부하/저부하로 쪼개 보고 |
| 기록 내 위치(공백 후 0~4행 vs 5행 이후)별 오류 분해 | #4 stage3 | 우리 valid 오경보 "위치 4" 사례와 직접 연결 |
| 기록 길이 구간별 성능 분해(n<10, 10~19, ≥20) | #2 docs | 짧은 기록 한계를 표로 |
| "AUC 순위 ≠ 운영점 순위" — 고정 FPR에서의 탐지율 보고 | #2 docs | 베이스라인 비교표에 α 1%에서의 탐지율 열 |
| 최악 모드 FPR(max over 운전 모드) | #4 팀 지표 | 운영 안정성 지표로 한 줄 |
| 운영 검출기를 행 단위로 그대로 돌리는 스트리밍 검증 + 분위수 민감도 표 | #5 §15 | 우리 α 민감도(1·3·5%)를 같은 형식 표로 |
| 누수 후보 피처 포함/제외 ablation | #6 3-4 | 정밀도 맞춤 전/후, 오프셋 지표 포함/제외 두 축 ablation |
| 부하 전환 구간 오경보 분리 | #6 3-2 | R2가 전환 직후에도 버티는지 |
| 기록 내 확률 궤적(정상형 → 이상형 전이) 그림 | #3 세그먼트 16 | 사건 첫 기록에서 점수가 오르는 모습 |
| 근거 수준 표기 [데이터]/[추정]/[가정] | #1 | 보고서 1·3장 문장에 일관 적용 |
| 세그먼트 부트스트랩 **쌍 차이** CI로 모델 비교 | #1 PR #17 | 베이스라인 대비 차이를 CI로(개별 CI 겹침 판정 금지) |

---

## B. 관련 논문 기법

각 항목은 **핵심 아이디어(2줄) → 이 데이터 적용(2줄) → 대표 서지(확인 상태)** 순서다.

### B.1 다변량 통계적 공정 관리: PCA 기반 Hotelling T²·SPE(Q)
- **아이디어**
  - 정상 데이터로 PCA를 적합한다. 모델 부분공간 안의 이탈은 T²(F 분포 기반 한계)로, 부분공간 밖 잔차는 SPE/Q(Jackson-Mudholkar 근사 한계)로 감시한다.
  - 기여도 그림으로 "어느 변수가 한계를 깼는지" 진단한다. 배치 공정은 배치 × 시간 × 변수를 펼친 multiway PCA로 다룬다.
- **적용**
  - 기록 단위 특징(3성분 점수, 상·하부 표준편차 비, 상하 상관, 전류 오프셋 등)에 PCA를 train 정상으로 적합하고 T²·SPE를 낸다. 이론 한계와 valid 정상 conformal 한계를 나란히 보고한다.
  - 베이스라인 6번째로 넣어 "선형 다변량으로 어디까지 되는가"를 보인다. 기여도로 R2(크기 vs 파형)의 판단 근거를 시각화한다. 기록 길이가 들쭉날쭉하니 multiway 버전은 첫 k행 정렬이 필요하다.
- **서지**
  - MacGregor, J.F., Kourti, T. (1995). Statistical process control of multivariate processes. *Control Engineering Practice* 3(3):403–414. doi:10.1016/0967-0661(95)00014-L **[1차 Crossref]**
  - Jackson, J.E., Mudholkar, G.S. (1979). Control procedures for residuals associated with principal component analysis. *Technometrics* 21(3):341–349. doi:10.1080/00401706.1979.10489779 **[1차 Crossref]**
  - Qin, S.J. (2003). Statistical process monitoring: basics and beyond. *Journal of Chemometrics* 17(8–9):480–502. doi:10.1002/cem.800 **[1차 Crossref]**
  - Nomikos, P., MacGregor, J.F. (1995). Multivariate SPC charts for monitoring batch processes. *Technometrics* 37(1):41–59. doi:10.1080/00401706.1995.10485888 **[1차 Crossref]**

### B.2 순차 검출: CUSUM·EWMA·변화점 검출
- **아이디어**
  - CUSUM은 기준값 k를 넘는 편차(또는 로그우도비)를 누적해 h를 넘으면 경보를 낸다. 작은 지속 변화에 강하고, 평균 무경보 길이(ARL₀)와 탐지 지연(ARL₁)을 맞바꾼다.
  - EWMA는 λ로 지수가중한 평균을 관리 한계와 비교한다. 변화점 검출은 오프라인(PELT 등)·온라인(베이지안)으로 분포가 바뀐 시점을 찾는다.
- **적용**
  - R1 사건 지속(래치)을 "기록 단위 conformal p값의 −log를 누적하는 CUSUM + 60초 이상 공백이면 초기화"로 재정식화하면 임의 상수를 ARL₀(예: 한 근무조당 오경보 1회 이하)로 정할 수 있다. R1의 이론적 근거로 쓴다.
  - EWMA는 정상 하루 안의 느린 드리프트(#1이 본 마지막 블록 분포 이동)를 감시하는 보조 지표로 쓴다. PELT로 정상 77분을 운전 구간으로 나누면 운전 상태 정의를 데이터로 정당화할 수 있다.
- **서지**
  - Page, E.S. (1954). Continuous inspection schemes. *Biometrika* 41(1–2):100–115. doi:10.1093/biomet/41.1-2.100 **[1차 Crossref]**
  - Roberts, S.W. (1959). Control chart tests based on geometric moving averages. *Technometrics* 1(3):239–250. doi:10.1080/00401706.1959.10489860 **[1차 Crossref]**
  - Basseville, M., Nikiforov, I.V. (1993). *Detection of Abrupt Changes: Theory and Application*. Prentice-Hall. ISBN 0131267809 **[2차: ACM DL·Google Books 서지]**
  - Killick, R., Fearnhead, P., Eckley, I.A. (2012). Optimal detection of changepoints with a linear computational cost. *JASA* 107(500):1590–1598. doi:10.1080/01621459.2012.737745 **[2차: 검색 결과·arXiv 1101.1438. Crossref 조회는 429로 실패]**
  - Truong, C., Oudre, L., Vayatis, N. (2020). Selective review of offline change point detection methods. *Signal Processing* 167:107299. doi:10.1016/j.sigpro.2019.107299 **[1차 Crossref]**

### B.3 극값 이론 문턱: SPOT/DSPOT
- **아이디어**
  - 높은 초기 문턱 t를 넘은 초과분에 일반화 파레토 분포(GPD)를 맞추는 POT 방식이다. 분포를 가정하지 않고 매우 작은 위험 q(예: 10⁻⁴)에 해당하는 문턱을 외삽한다.
  - 스트림에서 점진적으로 갱신하며(SPOT), 국소 이동평균을 빼서 드리프트에 대응한다(DSPOT).
- **적용**
  - valid 정상 기록이 N개면 conformal 문턱의 최소 α는 1/(N+1)이다. 그래서 α 0.1%나 "근무조당 1회" 같은 낮은 오경보율은 경험 분위수로 정할 수 없다. 기록별 최대 점수에 POT를 적용해 외삽하고 conformal 문턱과 비교한다.
  - 기록 안 행들은 서로 의존하므로 기록 최댓값(묶음 처리)을 쓴다. 초과분이 적으면 GPD 적합이 불안정하니 부트스트랩 구간을 함께 보고한다.
- **서지**: Siffer, A., Fouque, P.-A., Termier, A., Largouët, C. (2017). Anomaly detection in streams with extreme value theory. *Proc. 23rd ACM SIGKDD (KDD '17)*, pp. 1067–1075. doi:10.1145/3097983.3098144 **[1차 Crossref]**

### B.4 시계열 이상탐지 평가: point-adjust 비판, 구간 기반 P/R, eTaPR, 탐지 지연

#### B.4a point-adjust 비판 (Kim et al. AAAI 2022)
- **아이디어**: 구간 안에서 한 점만 맞혀도 구간 전체를 맞힌 것으로 치는 point-adjust(PA)는 성능을 크게 부풀린다. 무작위 점수도 최신 기법처럼 보일 수 있다. PA를 금지해도 학습하지 않은 모델이 기존 기법과 비슷하다. 대안으로 새 기준선과 평가 프로토콜(PA%K)을 냈다.
- **적용**: 우리 행 F1은 PA 없이 점 단위로 쟀다고 명시해 신뢰를 얻는다. R1 승계는 사실상 "앞 기록 판정을 뒤로 퍼뜨리는" 장치라 PA와 비슷해 보일 수 있다. 그러니 R1 없이 잰 점 단위 F1과 R1 포함 F1을 나란히 둔다.
- **서지**: Kim, S., Choi, K., Choi, H.-S., Lee, B., Yoon, S. (2022). Towards a rigorous evaluation of time-series anomaly detection. *Proc. AAAI* 36(7):7194–7201. doi:10.1609/aaai.v36i7.20680 **[1차 Crossref + arXiv 2109.05257 초록]**

#### B.4b 구간 기반 precision/recall (Tatbul et al. NeurIPS 2018)
- **아이디어**: 이상을 점이 아니라 구간으로 본다. 존재 보상(구간을 조금이라도 잡았나), 겹침 비율, 위치 편향(앞부분을 잡으면 가산), 조각 수 패널티를 조합해 재현율과 정밀도를 정의한다.
- **적용**: 이상 사건 1건(21기록)을 하나의 구간으로 보고 "앞 편향" 재현율로 조기 탐지를 보상한다. 존재(1/1)·겹침 비율·앞 편향 점수를 행 F1 옆에 둔다.
- **서지**: Tatbul, N., Lee, T.J., Zdonik, S., Alam, M., Gottschlich, J. (2018). Precision and recall for time series. *NeurIPS 2018*. arXiv:1803.03639 **[1차 arXiv]**

#### B.4c TaPR/eTaPR (Hwang et al.)
- **아이디어**: 구간 탐지 여부(detection)와 겹침 정도(portion)를 나눠 점수화한다. 이상 직후에 경보가 늦게 나와도 인정하는 "모호 구간"을 둔다. 2022년판 eTaPR은 이상과 무관한 넓은 구간을 찍는 부정확한 예측을 기존 지표가 과대평가한다고 지적했다.
- **적용**: 모호 구간을 버스트 공백 1회(약 8초)로 잡고 TaPR을 계산하면 기록 구조와 맞는다. 공개 구현(github.com/wshw4ng/eTaPR)을 쓸 수 있다.
- **서지**
  - Hwang, W.-S., Yun, J.-H., Kim, J., Kim, H.C. (2019). Time-series aware precision and recall for anomaly detection. *Proc. CIKM '19*, pp. 2241–2244. doi:10.1145/3357384.3358118 **[1차 Crossref]**
  - Hwang, W.-S., Yun, J.-H., Kim, J., Min, B.G. (2022). "Do you know existing accuracy metrics overrate time-series anomaly detections?" *Proc. ACM SAC '22*. doi:10.1145/3477314.3507024 **[2차: 검색 요약. Crossref 429. 요청서의 "CIKM 2022"는 SAC 2022로 정정]**

#### B.4d 탐지 지연·실시간 평가
- **아이디어**: NAB는 이상 구간 앞쪽에서 일찍 탐지할수록 높은 점수를 주고 오경보에 벌점을 준다. 순차 검출 이론은 ARL₀(오경보 간 평균 길이)와 평균 탐지 지연을 짝으로 보고한다.
- **적용**: "사건 시작 기준 첫 경보 지연(초) + 구조적 하한(버스트 간격)"과 "정상 시간당 오경보(상한)"를 한 쌍으로 보고한다. α별로 이 쌍을 그린 곡선(지연-오경보 트레이드오프)이 현장 활용 장의 핵심 그림이 된다.
- **서지**
  - Lavin, A., Ahmad, S. (2015). Evaluating real-time anomaly detection algorithms — the Numenta Anomaly Benchmark. *IEEE ICMLA 2015*. doi:10.1109/ICMLA.2015.141 · arXiv:1510.03336 **[2차: 검색 결과]**
  - 벤치마크 결함 4종(자명성·비현실적 이상 밀도·오라벨·run-to-failure 편향): Wu, R., Keogh, E.J. (2023). Current time series anomaly detection benchmarks are flawed and are creating the illusion of progress. *IEEE TKDE* 35(3):2421–2429. doi:10.1109/TKDE.2021.3112126 **[2차: 검색 결과]** → 형식 누수 1줄 규칙을 "자명성" 결함의 실례로 인용

### B.5 conformal 이상탐지
- **아이디어**
  - 정상 보정 집합의 비적합 점수 순위로 p값을 만든다. 정상 데이터가 교환 가능하면 오경보율이 유한 표본에서 α 이하로 보장된다(Laxhammar & Falkman의 ICAD는 이를 궤적의 순차 탐지에 적용).
  - Bates et al.은 conformal p값이 주변적으로만 유효하고 서로 의존한다는 점을 짚었다. 그래서 훈련 데이터에 조건부로 유효하고 서로 독립인 p값(calibration-conditional)을 제안했고, 여러 시점을 한꺼번에 검정할 때 FDR 제어와도 연결했다.
- **적용**
  - 우리 문턱은 valid 정상 기록의 최대 점수 순위다. 시간순 분할과 드리프트 때문에 교환 가능성이 깨질 수 있다는 가정 위반을 명시한다. 실제 test 오경보율을 Clopper-Pearson 구간과 함께 보여 "보장 vs 실측"을 대비한다(보고서가 이미 "α로 보장하지 않음"을 인정하므로 수치로 보강).
  - valid N이 작으니 Bates식 calibration-conditional 보정 문턱을 민감도 행으로 추가한다. 운전 상태별(Mondrian식) 보정을 하면 B.6과 이어진다.
- **서지**
  - Laxhammar, R., Falkman, G. (2015). Inductive conformal anomaly detection for sequential detection of anomalous sub-trajectories. *Annals of Mathematics and Artificial Intelligence* 74(1–2):67–94 (온라인 2013). doi:10.1007/s10472-013-9381-7 **[1차 Crossref]**
  - Bates, S., Candès, E., Lei, L., Romano, Y., Sesia, M. (2023). Testing for outliers with conformal p-values. *Annals of Statistics* 51(1):149–178. doi:10.1214/22-AOS2244 **[1차 Crossref(권·호) + 2차(쪽수: Project Euclid 검색)]**, arXiv:2104.08279 초록 **[1차]**
  - Mondrian(조건부) conformal의 원전(Vovk, Gammerman, Shafer, *Algorithmic Learning in a Random World*, Springer 2005)은 **서지 미확인**이다.

### B.6 운전 조건(부하) 정규화·조건부 기준선
- **아이디어**
  - 고장 신호는 운전 조건 변화에 가려진다. 그래서 운전 영역(regime)을 먼저 군집으로 나누고 영역별로 표준화하거나 조건부 기준선을 만든 뒤 잔차를 본다(C-MAPSS 다중 조건 연구의 표준 처리).
  - 정상 운전 조건이 일부만 관측된 경우에는 조건 간 전이학습으로 기준선을 넓힌다.
- **적용**
  - 부하 대리 변수로 전류 AC 진폭(#1의 2상태 경계)을 쓴다. 진동 기대값을 전류 진폭으로 회귀한 잔차, 또는 상태별 conformal 문턱을 R2의 원리적 대안으로 시험한다. R2는 "크기만 크고 파형이 정상이면 보류"하는 휴리스틱 조건부 판단이다.
  - 단, #4는 조건별 문턱이 오히려 나빴다(stage6). 그러니 단일 문턱 대 조건부 문턱을 고부하 오경보와 진동형 주입 탐지율로 같이 비교하고, 나쁘면 나쁘다고 적는다.
- **서지**
  - Ramasso, E., Saxena, A. (2014). Performance benchmarking and analysis of prognostic methods for CMAPSS datasets. *International Journal of Prognostics and Health Management* (ISSN 2153-2648) 2014-014. https://papers.phmsociety.org/index.php/ijphm/article/view/2236 **[1차 PDF 1~3쪽: "effects of faults are masked due to operational conditions"]**
  - Wang, T., Yu, J., Siegel, D., Lee, J. (2008). A similarity-based prognostics approach for remaining useful life estimation of engineered systems. *2008 Int. Conf. on Prognostics and Health Management*, pp. 1–6. doi:10.1109/PHM.2008.4711421 **[1차 Crossref]**. 운전 조건별 표준화를 했다는 내용은 **[2차: 검색 요약]**
  - Michau, G., Fink, O. (2021). Unsupervised transfer learning for anomaly detection: Application to complementary operating condition transfer. *Knowledge-Based Systems* 216:106816. doi:10.1016/j.knosys.2021.106816 · arXiv:2008.07815 **[2차: 검색 결과]**

### B.7 MCSA(모터 전류 신호 분석)로 펌프·기어 이상 탐지
- **아이디어**
  - 고정자 전류에는 전동기 결함뿐 아니라 구동되는 부하 쪽 결함(기어 맞물림, 펌프 캐비테이션 등)도 전원 주파수 주변 측파대 변조로 남는다. 그래서 비침습 진단이 된다.
  - 기어 진동을 전류로 감시하거나, 원심 펌프 결함을 진동과 MCSA를 함께 써서 진단한 연구가 있다.
- **적용**
  - 이 데이터는 10 Hz 표본이라 60 Hz 주변 측파대(회전·맞물림 주파수만큼 떨어진 수십~수천 Hz 성분)가 모두 접혀 사라진다. 그래서 MCSA의 주파수 진단은 **불가능**하다. 남는 것은 파형 일관성(사인 적합 잔차)·진폭(부하)·오프셋뿐이다. 보고서에 "MCSA의 원리(부하 측 결함이 전류를 변조한다)를 근거로 전류 파형 이탈을 쓰되, 결함 종류 판별은 불가"라고 명시한다.
  - 현장 활용 제안은 "전류 표본화를 kHz 대역으로 올리면 기어 맞물림 측파대로 결함 종류 진단이 가능하다"로 연결한다(필요 표본률 수치는 설비 사양 확인 후 제시. 구체 수치는 [추정]이라 보고서에는 쓰지 않음).
- **서지**
  - Thomson, W.T., Fenger, M. (2001). Current signature analysis to detect induction motor faults. *IEEE Industry Applications Magazine* 7(4):26–34. doi:10.1109/2943.930988 **[1차 Crossref]**
  - Benbouzid, M.E.H. (2000). A review of induction motors signature analysis as a medium for faults detection. *IEEE Trans. Industrial Electronics* 47(5):984–993. doi:10.1109/41.873206 **[1차 Crossref]**
  - Kar, C., Mohanty, A.R. (2006). Monitoring gear vibrations through motor current signature analysis and wavelet transform. *Mechanical Systems and Signal Processing* 20(1):158–187. doi:10.1016/j.ymssp.2004.07.006 **[1차 Crossref]**
  - Mohanty, A.R., Pradhan, P.K., Mahalik, N.P., Dastidar, S.G. (2012). Fault detection in a centrifugal pump using vibration and motor current signature analysis. *Int. J. Automation and Control* 6(3/4):261–276. doi:10.1504/IJAAC.2012.051884 **[2차: Inderscience 검색 결과]**

### B.8 이진 비율 신뢰구간과 소표본 성능 보고
- **아이디어**
  - Clopper-Pearson은 이항분포를 뒤집은 정확(보수적) 구간이다. 0/n이나 n/n 같은 극단값에서도 유효하다. 소표본에서는 Wald 구간의 포함확률이 불안정하므로 Wilson·Jeffreys 구간이 권장된다.
  - 0/n이면 단측 95% 상한은 약 3/n이다("3의 규칙").
- **적용**
  - 사건 탐지 1/1의 95% CP 구간은 **[0.025, 1.000]**, 이상 기록 21/21은 **[0.839, 1.000]**, test 이상 11/11은 [0.715, 1.000]이다. 정상 test 오경보 0/N의 95% 상한은 1−0.025^(1/N)이다(N = 100 → 3.6%, 120 → 3.0%, 200 → 1.8%, 300 → 1.2%). 계산은 scipy `beta.ppf`로 검산했다.
  - 기록·행은 서로 독립이 아니다(같은 사건, 인접 기록). 그러니 "행 수가 아니라 기록 수, 사건 수"를 n으로 써야 하고, 이렇게 구해도 구간은 낙관적일 수 있다고 적는다.
- **서지**
  - Clopper, C.J., Pearson, E.S. (1934). The use of confidence or fiducial limits illustrated in the case of the binomial. *Biometrika* 26(4):404–413. doi:10.1093/biomet/26.4.404 **[1차 Crossref]**
  - Brown, L.D., Cai, T.T., DasGupta, A. (2001). Interval estimation for a binomial proportion. *Statistical Science* 16(2):101–133. doi:10.1214/ss/1009213286 **[2차: Project Euclid 검색 결과]**
  - Hanley, J.A., Lippman-Hand, A. (1983). If nothing goes wrong, is everything all right? Interpreting zero numerators. *JAMA* 249(13):1743–1745 **[2차: 검색 결과. DOI 미확인]**

### B.9 단순 베이스라인이 딥모델과 비슷하거나 낫다는 근거
- **아이디어**
  - 다변량 시계열 이상탐지에서 전통·기계학습·딥러닝 세 계열을 5개 데이터셋으로 비교했더니, 어느 계열도 유의하게 앞서지 않았다(Audibert et al.). 전통 기법을 벤치마크에 반드시 넣으라고 권고한다.
  - 평가 지표와 벤치마크 관행이 잘못돼 진전이 과장됐다. 최신 딥 이상탐지 모델은 사실상 선형 사상을 배운다. 그러니 단순 기준선 대비 엄밀 평가가 우선이다(Sarfraz et al.).
- **적용**
  - 우리 3성분 모델(크기·사인 파형·AR(2))과 conformal 문턱의 "단순함"을 약점이 아니라 설계 원칙으로 서술하는 근거다. 베이스라인 5종에 PCA T²/SPE(B.1)를 넣고, "1줄 규칙 기준선"(정밀도 맞춤 후 상부 진동 표준편차 단일 문턱 등)을 추가해 자명성 수준을 보이면 좋다.
  - 딥모델을 하나 더 넣기보다 "가이드북 LSTM-AE를 버스트 공백·정밀도 맞춤 조건에서 재현한 결과"를 비교 열로 두면, 가이드북 대비 개선이 분명해진다.
- **서지**
  - Audibert, J., Michiardi, P., Guyard, F., Marti, S., Zuluaga, M.A. (2022). Do deep neural networks contribute to multivariate time series anomaly detection? *Pattern Recognition* 132:108945. doi:10.1016/j.patcog.2022.108945 **[1차 Crossref + 2차 초록 요약]**
  - Sarfraz, M.S., Chen, M.-Y., Layer, L., Peng, K., Koulakis, M. (2024). Position: Quo vadis, unsupervised time series anomaly detection? *Proc. 41st ICML*, PMLR 235:43461–43476. https://proceedings.mlr.press/v235/sarfraz24a.html · arXiv:2405.02678 **[1차 arXiv 초록 + 2차(PMLR 쪽수: 검색 결과)]**

### B.10 (보너스) 누수·지름길 학습 개념
- **아이디어**: 누수는 예측 시점에 쓸 수 없는 정보나 목표와 우연히 얽힌 정보가 학습에 들어가 성능을 부풀리는 현상이다. 지름길 학습은 모델이 의도한 특징 대신 쉬운 상관(형식·배경)을 배우는 현상이다.
- **적용**: 소수 자릿수·1.192 격자는 "수집 파이프라인이 라벨과 얽힌 지름길"이다. 이 두 개념으로 1.4절 결함표의 이름을 붙이면 심사위원이 바로 이해한다.
- **서지**
  - Kaufman, S., Rosset, S., Perlich, C., Stitelman, O. (2012). Leakage in data mining: Formulation, detection, and avoidance. *ACM TKDD* 6(4), Article 15:1–21. doi:10.1145/2382577.2382579 **[2차: ACM DL 검색 결과]**
  - Geirhos, R. et al. (2020). Shortcut learning in deep neural networks. *Nature Machine Intelligence* 2(11):665–673. doi:10.1038/s42256-020-00257-z **[1차 Crossref]**

---

## C. 보고서 반영 우선순위 (제안)

1. **헤드라인 지표 보강**: 행 F1 1.000 옆에 사건 1/1 [0.025, 1], 이상 기록 21/21 [0.839, 1], 정상 오경보 0/N 상한(CP), 사건 시작 기준 지연 + 버스트 간격 하한, 시간당 오경보 상한을 한 줄 표로 넣는다(B.4d, B.8).
2. **누수 서술 이름 붙이기**: "자명성 결함(Wu & Keogh) + 지름길 학습(Geirhos)" 한 문장을 쓰고, 오프셋을 지우지 않은 이유와 V5 결과를 연결한다(A.5-1·2).
3. **앨리어싱 물리 해석 한 문단**: 60 Hz는 10 Hz에서 0 Hz로 접혀야 한다. 0.60/0.22 Hz → 클럭·구동 조건 가설 → FM6 교락 근거 → 주최 측 확인 질문으로 잇는다(A.5-5, B.7).
4. **R1·R2의 이론적 자리 매김**: R1은 CUSUM·ARL₀ 관점(B.2), R2는 운전 조건부 기준선(B.6)의 휴리스틱판이다. PA 오해를 막으려고 R1 없는 점 단위 F1을 병기한다(B.4a).
5. **베이스라인 1~2개 추가 검토**: PCA T²/SPE(B.1), 가이드북 LSTM-AE 재현. 시간이 없으면 "검토했으나 미적용"으로 적용 조건표에만 둔다.

## 부록: 확인 실패·주의
- Crossref가 429(요청 과다)로 막혀 Killick 2012, eTaPR 2022, Brown 2001, Kaufman 2012, Wu & Keogh 2023, Lavin & Ahmad 2015, Michau & Fink 2021은 검색 결과로만 확인했다(2차).
- 요청서의 "eTaPR (Hwang et al. CIKM 2019/2022)" 중 2022년판은 **ACM SAC '22**다. 저자도 Kim, H.C.가 아니라 Min, B.G.다(검색 결과 기준).
- 경쟁 레포는 마감 전이라 계속 바뀐다. 특히 #1 PR #27은 아직 열려 있다. 보고서 제출 직전에 #1·#2·#5를 한 번 더 확인할 것.
