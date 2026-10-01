# R6 — 10 Hz 진동·전류에서 무엇을 뽑을 수 있나, 그리고 어떤 표준이 도메인 근거가 되나

- 작성일: 2026-10-01
- 범위: aliasing/undersampling, 저샘플링 특징량의 물리적 의미, 진동·상태감시 표준(ISO/KS), MCSA, 센서 측면 해석. 원자료 직접 분석 포함(읽기 전용).
- 산출물(모두 scratchpad/research/ 아래)
  - 보고서: `R6_signal_processing_standards.md` (이 파일)
  - 분석 스크립트: `R6_signal_analysis.py` — 실행 `/opt/anaconda3/bin/python3 R6_signal_analysis.py > R6_signal_analysis_output.txt` (약 30초)
  - 출력: `R6_signal_analysis_output.txt` — 본문에 나오는 모든 데이터 수치의 출처. 절 A–I로 나뉘며 본문에 [A], [B] …로 표시했다.
  - 중간 탐색 스크립트: `r6_work/explore*.py`, `r6_work/*.csv` (참고용. 최종 수치는 위 스크립트 기준)
- **검증 방법 메모**: 이 세션은 WebSearch 예산(세션 공유 200회)이 이미 소진된 상태였다. 그래서 검색엔진 대신 다음처럼 1차 출처를 직접 조회했다.
  - iso.org가 자동 접근을 403으로 막아, Internet Archive에 보관된 iso.org 원 페이지를 열었다(스냅샷 날짜는 표에 적음).
  - 논문은 Crossref DOI 레지스트리와 OpenAlex에서 서지, 초록, 철회 여부를 직접 조회했다.
  - KS 부합 여부는 e-나라표준인증(standard.go.kr) 상세 페이지를 열어 확인했다.
  - ISO 17359:2018, ISO 20816-1:2016, ISO/FDIS 13379-1:2025는 같은 세션의 병렬 조사 에이전트가 내려받은 iTeh 공개 미리보기 사본(scratchpad 안 텍스트 파일)을 내가 직접 읽어 목차와 앞부분 조항을 확인했다. 해당 행에 출처 경로를 적었다.
  - 표의 "opened"는 이렇게 원 페이지, 메타데이터, 초록, 공개 미리보기를 직접 확인했다는 뜻이다. **유료 표준의 미리보기 범위 밖 본문은 열람하지 못했다.** 검색 기반 발견이 막혀 있었으므로 관련 문헌이 빠졌을 수 있다(§5).

---

## 1. 핵심 요약

1. **전류(AI2)는 교류 전류의 순시값을 10 Hz로 찍은 "스트로보스코프(등가시간) 복제"다.**
   - 정상 버스트(30행 이상) 360개 모두 단일 사인 적합 R² ≥ 0.994이고, 1–8차 고조파를 넣으면 중앙값 R² 0.99992다.
   - 겉보기(접힌) 주파수는 0.6000 Hz(5–95 % 0.5972–0.6025, sd 0.0017 Hz)로 77분 내내 거의 고정이며 부하와 무관하다(corr −0.04) [B].
   - 3·5·7차 고조파가 4.5 %·2.2 %·1.8 %로 보인다 [C]. 따라서 anti-aliasing 필터, 100 ms 블록평균, RMS 변환은 없었다. 100 ms 블록평균이었다면 60.6 Hz 성분의 진폭은 약 1 %로 줄었어야 한다.
2. **전류에서 물리적으로 확실한 것은 진폭, 즉 부하다.**
   - 사인 적합 진폭 A_c는 q05 114.7, 최대 261.3이다(단위 미상, √2×RMS).
   - 분포는 두 덩어리다: 저부하 100–130 구간 162/360개, 고부하 230–280 구간 71/360개 [B].
   - 실제 전기 주파수는 정할 수 없다. 59.4/60.6 Hz(샘플링이 정확히 10 Hz일 때)일 수도, 60 Hz에 실제 샘플 주기 99/101 ms일 수도, 10k±0.6 Hz의 다른 값일 수도 있다. 정확한 타임스탬프로 버스트 간 위상을 추적해도 풀리지 않았다(최대 R 0.23, 다중검정 null ≈ 0.17) [E].
3. **진동(AI0/AI1)은 평균 0이고 대칭이다.** 4–20 mA RMS 송신기 출력이 아니라 AC 결합 원파형을 언더샘플링한 값이다.
   - 정상 구간의 주성분은 접힌 선 1.79–1.80 Hz와 3.58–3.61 Hz다. 전류 겉보기 주파수의 약 3배·6배(비 2.985)다.
   - 이 선은 전류와 위상 고정이 아니며(R 0.08), 부하가 클수록 0.002 → 0.011 Hz 낮아진다 [D, I]. 물리 원인은 미해결이다.
   - 유도전동기 회전 차수라면 슬립 1 %당 0.3 Hz 이상 움직여야 하므로 그 해석은 맞지 않는다.
   - **결론: 0–5 Hz의 "주파수"는 물리 주파수가 아니라 접힘 지문(alias fingerprint)일 뿐이다.**
4. **진동 크기는 부하에 강하게 묶여 있다.**
   - 버스트 RMS 중 전류 진폭으로 설명되는 비율(R²)은 AI1 0.94, AI0 0.39다.
   - 저부하 기준선의 99 % 임계를 그대로 쓰면, 시간상 뒤쪽 절반의 정상 고부하 버스트 100 %(AI1), 49 %(AI0)가 경보가 된다.
   - 전류 진폭으로 조건화한 잔차 임계를 쓰면 같은 정상 버스트의 2.2 %만 걸린다. 이상 버스트(30행 이상)는 AI1에서 10/10, AI0에서 9/10이 걸린다 [H].
   - 과제가 말하는 "정상 운전 변화를 이상으로 오판"을 줄이는 가장 직접적이고 물리적으로 정당한 장치다.
5. **이상 파일은 고장 외에도 전기·수집 맥락이 다르다.**
   - 전류가 깨끗한 사인이 아니다: R² 중앙값 0.53, 거칠기(roughness) 0.90(정상 0.38).
   - 겉보기 주파수가 다르다: 0.10–0.22 Hz(IQR).
   - 전류 값의 100 %가 1.1920929(= 10⁷/2²³) 간격 격자 위에 있다(정상 0.2 %). 진동 소수 자릿수도 8자리 대 6자리로 다르다 [A].
   - 따라서 스펙트럼·순서 기반 특징과 양자화 민감 특징은 "고장"이 아니라 "수집 체계·구동 주파수 차이"를 학습할 위험이 크다.
6. **반대로 샘플 분산(RMS)은 정상(stationary) 신호라면 언더샘플링·타이밍 지터와 무관하게 불편(unbiased) 추정이다.**
   - 이상 구간 AI0 RMS 중앙값은 0.349다. 정상 최대는 0.147이며, 이상 버스트 17개 중 14개가 이를 넘는다. 첨도도 +1.56(정상 −0.51)이다 [B, F].
   - 이 변화는 지터나 접힘으로는 설명되지 않는다. 다만 운전 조건(속도·부하) 차이로 생겼을 가능성은 남는다.
   - 이상 버스트 3·19·20(31·10·15행)은 진동이 정상 95 % 범위 안에 있다. 에피소드 단위 라벨이 버스트 단위로는 섞여 있다는 뜻이다(FN 분석 대상).
7. **표준: 우리 데이터로는 어떤 진동 등급(zone) 판정도 불가하다고 명시해야 한다.**
   - ISO 20816 계열은 broad-band 측정을 요구한다. ISO 20816-1 §4.1.3: "The measurement of vibration shall be broad band". NOTE 1: "In the past, broad-band measurements in the range 10 Hz to 1 000 Hz were the intended metric…". 비회전부의 권장량은 r.m.s. velocity다(§4.2).
   - 20816-3:2022은 정상 상태 운전도 전제로 한다(초록에 명시). zone 경계값 본문은 미열람이다.
   - 20816-3은 rotodynamic pump를 제외하고 ISO 10816-7:2009(rotodynamic 전용)로 넘긴다. 프레스 유압펌프는 용적식일 가능성이 높아 10816-7도 그대로는 맞지 않는다.
   - 10 Hz 샘플에 단위 미상인 이 데이터로는 판정할 수 없다.
   - 쓸 수 있는 것은 기준선 대비 "변화" 개념(ISO 20816-1 §6.3.3 "Criterion II: Change in vibration magnitude", 목차로 확인)과 ISO 17359:2018이다.
   - ISO 17359:2018 §8.4는 과제의 오경보 정의와 같은 말을 한다: "It is also important to be able to determine if a change in one or more parameters is due to the occurrence of a fault or is due to a change in duty or operating conditions."
   - ISO 13379-1:2012는 2025년 2판(ISO 13379-1:2025)으로 대체되어 **철회(95.99)**되었다. ISO 13381-1:2015는 2025-09에 **ISO 13381-1:2025**로 대체되었다.
   - KS: KS B ISO 17359, 20816-1, 20816-3(2026-07-28 제정), 10816-7, 13373-1/-2/-3, 13379-1, 13381-1, 18436-2, 13372가 있음을 확인했다.
8. **MCSA는 이 데이터로 불가하다.** MCSA(Thomson & Fenger 2001; Benbouzid 2000)는 stator current 스펙트럼의 측대역을 kHz 샘플과 장시간 연속 기록으로 분해하는 기법이다.
   - 10 Hz로 가능한 것은 네 가지다: (a) 부하(진폭) 추세, (b) 스트로보스코프 효과를 이용한 저차 고조파 비, (c) 버스트 안의 느린 진폭 변조, (d) 파형 적합 잔차(전기·수집 품질 지표).
   - 잔차 바닥이 약 −41 dB라 약한 측대역은 원리적으로 검출할 수 없다.
9. **계획에 바로 넣을 것**
   - (i) 버스트 또는 고정 길이 창 단위의 "물리 특징 세트": A_c, 진동 RMS·강건 분위수·첨도, 부하 조건화 잔차, AI0/AI1 비.
   - (ii) "맥락 게이트": 전류 겉보기 주파수와 적합 R²로 수집·구동 맥락 변화를 감지해 고장과 구분한다.
   - (iii) confound 실험: 맥락 특징만으로 정상과 이상이 완벽히 갈린다는 것을 보여주고, 그 특징을 주 모델에서 뺀다.
   - (iv) 경보: 부하 조건화 잔차와 지속성 규칙(k-of-n)을 쓰고, 오경보를 "시간당 건수"로 보고한다(정상 데이터 기준 467 버스트/시간).

---

## 2. 출처 표

등급: A = 동료심사 학술지/주요 학회/국제·국가표준/공공기관, B = 기술보고서·전문서·제조사 기술문서, C = 블로그·포럼·마케팅(포인터 전용).
검증: opened = 원 페이지·메타데이터·초록·공개 미리보기를 직접 열어 확인, search-only = 검색 스니펫만, unverified = 확인 못 함.

### 2.1 표준·법령

| ID | 인용 | 유형·등급 | 검증 | 레드 플래그 | 라이선스·저작권 | 공개 보고서 사용 위험 |
|---|---|---|---|---|---|---|
| S1 | ISO 20816-1:2016, *Mechanical vibration — Measurement and evaluation of machine vibration — Part 1: General guidelines*. ISO/TC 108/SC 2, 2016-11, ed.1, 34 pp. https://www.iso.org/standard/63180.html. 공개 미리보기: https://standards.iteh.ai/catalog/standards/sist/e1185587-ea9f-44a4-81d5-adab1b23b7de/iso-20816-1-2016 | 국제표준, A | opened (iso.org 보관본 2026-02-26: 초록·상태·이력). 미리보기(목차, 4.1.3, 4.2, 4.3.2)는 이 세션의 병렬 조사 에이전트가 받은 iTeh 공개 미리보기 사본(`research/iso20816_1_sample.txt`)을 직접 읽음 | 단계 90.92 "to be revised"(개정 진행 중). ISO 10816-1:1995, ISO 7919-1:1996 대체 | ISO 저작권·유료 | 초록 요지와 조항 번호만 인용. 표·그림·zone 경계값 전재 금지 |
| S2 | ISO 20816-3:2022, *… Part 3: Industrial machinery with a power rating above 15 kW and operating speeds between 120 r/min and 30 000 r/min*. ed.1, 24 pp. https://www.iso.org/standard/78311.html | A | opened (보관본 2025-11-27: 적용·제외 목록 전문) | 90.92 "to be revised". ISO 10816-3:2009, ISO 7919-3:2009 대체 | 유료 | 같음. zone 경계 수치 전재 금지 |
| S3 | ISO 10816-7:2009, *Mechanical vibration — Evaluation of machine vibration by measurements on non-rotating parts — Part 7: Rotodynamic pumps for industrial applications, including measurements on rotating shafts*. 2009-02, 17 pp. https://www.iso.org/standard/41726.html | A | opened (보관본 2024-05-10) | 90.93 confirmed. **rotodynamic 펌프 전용** | 유료 | 용적식 펌프에 쓰지 말 것 |
| S4 | ISO 13373-1:2002, *Condition monitoring and diagnostics of machines — Vibration condition monitoring — Part 1: General procedures*. https://www.iso.org/standard/21831.html | A | opened (보관본 2024-05-10, 초록) | 90.60 under review | 유료 | 센서 선택·신호조건화 근거로만(본문 미열람) |
| S5 | ISO 13373-2:2016, *… Part 2: Processing, analysis and presentation of vibration data*. https://www.iso.org/standard/68128.html | A | opened (보관본 2024-07-10, 초록) | 90.93 | 유료 | 같음 |
| S6 | ISO 13373-3:2015, *… Part 3: Guidelines for vibration diagnosis* | A | 간접 확인: KS B ISO 13373-3 페이지(대응 표준 'ISO/PRF 13373-3'로 표기). ISO 페이지는 미열람 | 발행 연도는 ISO 페이지로 확인 못 함 | 유료 | 제목만 인용 |
| S7 | ISO 17359:2018, *Condition monitoring and diagnostics of machines — General guidelines*. ed.3, 2018-01, 29 pp., ISO/TC 108/SC 5. https://www.iso.org/standard/71194.html. 공개 미리보기: https://standards.iteh.ai/catalog/standards/sist/c664dc56-e63a-41c3-a056-f39595d15752/iso-17359-2018 | A | opened (iso.org 보관본 2026-02-22, 초록·상태). 미리보기(목차와 §8.1–8.8 본문)는 병렬 조사 에이전트가 받은 iTeh 사본(`research/r9src/iso17359_sample.txt`)을 직접 읽음. §8.9 alert/alarm, §8.10 baseline, §9.3 본문은 미리보기 범위 밖 | 90.93 confirmed | 유료 | 조항 번호와 짧은 인용은 가능. §8.9 내용은 미확인 |
| S8 | ISO 13379-1:2012, *… Data interpretation and diagnostics techniques — Part 1: General guidelines*. https://www.iso.org/standard/39836.html. 후속판 ISO 13379-1:2025(2판), 미리보기: https://standards.iteh.ai/catalog/standards/iso/d9c086bc-af50-41d5-98d1-76d0c775e2f2/iso-fdis-13379-1 | A | opened (2012판 iso.org 보관본 2025-11-01). 후속판은 병렬 에이전트가 받은 ISO/FDIS 13379-1:2025 미리보기(투표 2025-07-07~09-01, "This second edition … cancels … ISO 13379-1:2012")를 읽음. 정식 발행일은 미확인 | **2012판 철회(95.99)** | 유료 | 2025판으로 인용. KS B ISO 13379-1은 아직 2012판 부합. FMSA 등 본문은 미열람 |
| S9 | ISO 13381-1:2025, *Condition monitoring and diagnostics of machine systems — Prognostics — Part 1: General guidelines and requirements*. 2025-09, ed.3, 23 pp. https://www.iso.org/standard/88029.html (구판 ISO 13381-1:2015: /51436) | A | opened (2025판 보관본 2025-12-02, 2015판 보관본 2024-03-30) | 2015판은 철회·대체됨 | 유료 | 최신판 번호로 인용 |
| S10 | ISO 18436-2:2014, *… Requirements for qualification and assessment of personnel — Part 2: Vibration condition monitoring and diagnostics*. https://www.iso.org/standard/50447.html | A | opened (보관본 2025-10-07) | 90.92 | 유료 | 현장 적용(해석 인력 자격) 언급용 |
| S11 | KS B ISO 17359 / 20816-1 / 20816-3 / 20816-2 / 10816-7 / 13373-1 / 13373-2 / 13373-3 / 13379-1 / 13381-1 / 18436-2 / 13372 / 2954, KS C IEC 60034-14 — e-나라표준인증 상세 페이지(예: https://www.standard.go.kr/KSCI/standardIntro/getStandardSearchView.do?menuId=919&topMenuId=502&upperMenuId=503&ksNo=KSBISO17359&tmprKsNo=KSBISO17359) | 국가표준(KS), A | opened (2026-10-01 조회, 상세는 §3.4 표) | 일부 페이지의 "대응 국제표준" 칸이 구판 또는 'ISO/NP 20816-1', 'ISO/PRF 13373-3'처럼 표기됨(DB 표기 오류 추정) | KS 원문은 약관 동의·유료 | KS 번호·제정일·적용범위 요지 인용 가능 |
| S12 | ISO 20958:2013, *Electrical signature analysis of three-phase induction motors*(제목은 기억에 의존) | A | **unverified** (ISO·KS 페이지 확인 실패. KS B ISO 20958은 검색 결과 없음) | – | 유료 | 확인 전 인용 보류 |
| S13 | *IEEE Standard for Digitizing Waveform Recorders* (IEEE Std 1057). DOI 10.1109/IEEESTD.2018.8291741 | 표준, A | Crossref 메타데이터 opened(번호·연도는 메타데이터에 없음, DOI는 2018 등록) | – | IEEE 유료 | 3/4-parameter sine fit의 근거. 판 연도는 "1057-2017"로 추정, 확인 필요 |
| L1 | 전기사업법 시행규칙 — 전기의 품질기준(표준주파수 60 Hz, 허용오차 ±0.2 Hz로 알려짐). https://www.law.go.kr/법령/전기사업법시행규칙 | 법령, A | **unverified** (조문이 동적 로딩이라 본문 미확인) | – | 공공 | 확인 후 인용 |

### 2.2 논문·서적

| ID | 인용 | 유형·등급 | 검증 | 레드 플래그 | 라이선스·저작권 | 사용 위험 |
|---|---|---|---|---|---|---|
| P1 | R. G. Vaughan, N. L. Scott, D. R. White, "The theory of bandpass sampling," *IEEE Trans. Signal Process.* 39(9):1973–1984, 1991. DOI 10.1109/78.134430 | 학술지 A | Crossref + 초록(OpenAlex) opened | 없음(철회 아님) | IEEE 저작권 | 인용·의역만 |
| P2 | W. T. Thomson, M. Fenger, "Current signature analysis to detect induction motor faults," *IEEE Ind. Appl. Mag.* 7(4):26–34, 2001. DOI 10.1109/2943.930988 | IEEE 매거진 A(튜토리얼 성격) | Crossref + 초록 opened, 본문 미열람 | 매거진 기사(연구논문 아님) | IEEE | 본문의 측대역 dB 판정표 등 수치는 미확인이므로 인용 금지 |
| P3 | M. E. H. Benbouzid, "A review of induction motors signature analysis as a medium for faults detection," *IEEE Trans. Ind. Electron.* 47(5):984–993, 2000. DOI 10.1109/41.873206 | A | Crossref + 초록 | – | IEEE | 고장 주파수 식은 본문 확인 후 인용 |
| P4 | S. Nandi, H. A. Toliyat, X. Li, "Condition monitoring and fault diagnosis of electrical motors—A review," *IEEE Trans. Energy Convers.* 20(4):719–729, 2005. DOI 10.1109/TEC.2005.847955 | A | Crossref + 초록 | – | IEEE | – |
| P5 | M. Blödt, P. Granjon, B. Raison, G. Rostaing, "Models for bearing damage detection in induction motors using stator current monitoring," *IEEE Trans. Ind. Electron.* 55(4):1813–1822, 2008. DOI 10.1109/TIE.2008.917108 (그린 OA: hal-00270747) | A | Crossref + 초록 | – | IEEE(저자 사본) | "부하 토크 변동 → 전류 변조" 근거 |
| P6 | W. T. Thomson, M. Fenger, "Case histories of current signature analysis to detect faults in induction motor drives," IEMDC'03, vol.3, pp.1459–1465, 2003. DOI 10.1109/IEMDC.2003.1210644 | 학회 A | Crossref + 초록 | – | IEEE | 기계 구동계 성분과 결함 성분을 분리해야 한다는 근거 |
| P7 | W. T. Thomson, I. Culbert, *Current Signature Analysis for Condition Monitoring of Cage Induction Motors*, Wiley(Crossref issued 2016-12-17). DOI 10.1002/9781119175476 | 전문서 B | Crossref 메타만 | – | 저작권 | 배경 참고 |
| P8 | B. Hjorth, "EEG analysis based on time domain properties," *Electroencephalogr. Clin. Neurophysiol.* 29(3):306–310, 1970. DOI 10.1016/0013-4694(70)90143-4 | A | Crossref 메타(초록 없음) | – | Elsevier | 정의 인용 |
| P9 | C. Bandt, B. Pompe, "Permutation entropy: A natural complexity measure for time series," *Phys. Rev. Lett.* 88(17):174102, 2002. DOI 10.1103/PhysRevLett.88.174102 | A | Crossref + 초록 | – | APS | – |
| P10 | L. Zunino, F. Olivares, F. Scholkmann, O. A. Rosso, "Permutation entropy based time series analysis: Equalities in the input signal can lead to false conclusions," *Phys. Lett. A* 381(22):1883–1892, 2017. DOI 10.1016/j.physleta.2017.03.052 | A | Crossref + 저장소(SEDICI) 초록 opened | – | Elsevier(그린 OA) | 양자화 tie 경고의 근거 |
| P11 | M. Riedl, A. Müller, N. Wessel, "Practical considerations of permutation entropy," *Eur. Phys. J. Spec. Top.* 222(2):249–262, 2013. DOI 10.1140/epjst/e2013-01862-7 | A | Crossref 메타 | – | Springer | – |
| P12 | J. S. Richman, J. R. Moorman, "Physiological time-series analysis using approximate entropy and sample entropy," *Am. J. Physiol. Heart Circ. Physiol.* 278(6):H2039–H2049, 2000. DOI 10.1152/ajpheart.2000.278.6.H2039 | A | Crossref + 초록 | – | APS(Physiol.) | – |
| P13 | J. M. Yentes et al., "The appropriate use of approximate entropy and sample entropy with short data sets," *Ann. Biomed. Eng.* 41(2):349–365, 2013. DOI 10.1007/s10439-012-0668-3 | A | PMC 원문 페이지 opened | – | Springer(PMC 사본) | "N≤200에서 매우 민감" 인용 가능 |
| P14 | T. Inouye et al., "Quantification of EEG irregularity by use of the entropy of the power spectrum," *Electroencephalogr. Clin. Neurophysiol.* 79(3):204–210, 1991. DOI 10.1016/0013-4694(91)90138-T | A | Crossref 메타 | – | Elsevier | – |
| P15 | D. Dyer, R. M. Stewart, "Detection of rolling element bearing damage by statistical vibration analysis," *J. Mech. Des.* 100(2):229–235, 1978. DOI 10.1115/1.3453905 | A | Crossref + 초록 | – | ASME | 첨도 근거(고샘플링 전제) |
| P16 | D. Rife, R. Boorstyn, "Single tone parameter estimation from discrete-time observations," *IEEE Trans. Inf. Theory* 20(5):591–598, 1974. DOI 10.1109/TIT.1974.1055282 | A | Crossref + 초록 | – | IEEE | 주파수 추정 하한(CRLB) 근거 |
| P17 | P. Händel, "Properties of the IEEE-STD-1057 four-parameter sine wave fit algorithm," *IEEE Trans. Instrum. Meas.* 49(6):1189–1193, 2000. DOI 10.1109/19.893254 | A | Crossref + 초록 | – | IEEE | 주기 일부만 덮는 잡음 자료에서는 1차원 탐색이 우월하다는 근거 |
| P18 | J. T. VanderPlas, "Understanding the Lomb–Scargle periodogram," *ApJS* 236(1):16, 2018. DOI 10.3847/1538-4365/aab766 | A | Crossref + 초록 | – | AAS/IOP | 불균등 샘플 주기 분석 |
| P19 | M. Zechmeister, M. Kürster, "The generalised Lomb-Scargle periodogram," *A&A* 496(2):577–584, 2009. DOI 10.1051/0004-6361:200811296 | A | Crossref 메타 | – | EDP | 본 분석에서 쓴 floating-mean GLS |
| P20 | F. J. J. Clarke, J. R. Stockton, "Principles and theory of wattmeters operating on the basis of regularly spaced sample pairs," *J. Phys. E: Sci. Instrum.* 15(6):645–652, 1982. DOI 10.1088/0022-3735/15/6/011 | A | Crossref + 초록(OpenAlex) | – | IOP | "등간격 순시 표본으로 사인파의 RMS·전력을 올바르게 계산" 근거 |
| P21 | R. Garg, A. L. Varna, A. Hajj-Ahmad, M. Wu, "'Seeing' ENF: Power-signature-based timestamp for digital multimedia via optical sensing and signal processing," *IEEE Trans. Inf. Forensics Secur.* 8(9):1417–1432, 2013. DOI 10.1109/TIFS.2013.2272217 | A | Crossref + 초록 | – | IEEE | 유추(analogy)로만 인용 |
| P22 | X.-G. Xia, "On estimation of multiple frequencies in undersampled complex valued waveforms," *IEEE Trans. Signal Process.* 47(12):3417–3419, 1999. DOI 10.1109/78.806088 | A | Crossref + 초록 | – | IEEE | – |
| P23 | P. P. Vaidyanathan, P. Pal, "Sparse sensing with co-prime samplers and arrays," *IEEE Trans. Signal Process.* 59(2):573–586, 2011. DOI 10.1109/TSP.2010.2089682 | A | Crossref 메타 | – | IEEE | – |
| P24 | K. Worden, H. Sohn, C. R. Farrar, "Novelty detection in a changing environment: regression and interpolation approaches," *J. Sound Vib.* 258(4):741–761, 2002. DOI 10.1006/jsvi.2002.5148 | A | Crossref 메타 | – | Elsevier | 운전 조건 회귀 정규화의 근거 |
| P25 | H. Sohn, "Effects of environmental and operational variability on structural health monitoring," *Phil. Trans. R. Soc. A* 365(1851):539–560, 2007(온라인 2006-12-13). DOI 10.1098/rsta.2006.1935 | A | Crossref + 초록 | – | Royal Society | 데이터 정규화 개념 |
| P26 | N. Helwig, E. Pignanelli, A. Schütze, "Condition monitoring of a complex hydraulic system using multivariate statistics," I2MTC 2015, pp.210–215. DOI 10.1109/I2MTC.2015.7151267. 데이터: UCI "Condition monitoring of hydraulic systems", DOI 10.24432/C5CW21 | 학회 A / 공개 데이터 | Crossref + 초록, UCI 페이지 opened | 시험대(test rig) 데이터라 프레스와 다른 시스템 | **데이터는 CC BY 4.0**(UCI 표기) | 출처 표시하면 재배포 가능. 다만 도메인 불일치 |
| P27 | T. Schneider, N. Helwig, A. Schütze, "Industrial condition monitoring with smart sensors using automated feature extraction and selection," *Meas. Sci. Technol.* 29(9):094002, 2018. DOI 10.1088/1361-6501/aad1d4 | A | Crossref + 초록 | – | IOP(bronze OA) | – |

### 2.3 제조사·기타

| ID | 인용 | 유형·등급 | 검증 | 레드 플래그 | 라이선스 | 사용 위험 |
|---|---|---|---|---|---|---|
| V1 | PCB Piezotronics, "Introduction to Accelerometers"(technical information). https://www.pcb.com/resources/technical-information/introduction-to-accelerometers | 제조사 기술문서 B | opened. "ICP® accelerometers are AC coupled devices and will not measure or respond to uniform acceleration", DC bias +8~+12 V | 상업적 이해관계 | 저작권 | 일반 사실 인용만 |
| V2 | NI-DAQmx 물리 채널 명명("Dev1/ai0") 문서(ni.com docs) | 제조사 문서 B | **unverified** (JS 렌더링이라 내용 미확인) | – | – | 근거로 쓰지 말 것 |
| V3 | Analog Devices MT-002 "What the Nyquist Criterion Means…" | 제조사 튜토리얼 B | **unverified** (접속 실패) | – | – | 인용 보류 |
| D1 | 본 분석: `R6_signal_analysis.py`(KAMP 원자료 읽기 전용) | 자체 분석 | 재현 가능 | §4 한계 참조 | – | – |

---

## 3. 세부 내용과 계획 활용

### 3.1 원자료 직접 분석 (R6_signal_analysis.py)

**(a) 시간 구조와 타임스탬프** [A]

- 정상 파일: 20,000행, 버스트 599개, 50행을 다 채운 버스트 202개, 버스트 길이 중앙값 37.
- 이상 파일: 600행, 버스트 21개, 50행 버스트 5개, 길이 중앙값 28. **버스트 길이 분포가 두 파일에서 다르다.** 따라서 N(표본 수)에 의존하는 특징(max, p2p, crest, entropy)은 길이 자체가 confound가 될 수 있다.
- 버스트 안 간격은 모두 정확히 100 ms다(정상 파일의 0 ms 1건은 중복 행 1개). 모든 버스트에서 ms 자리 오프셋(mod 100)이 일정하다.
  - 즉 타임스탬프는 "시작 시각 + n×100 ms"로 계산된 값이거나, 하드웨어 클럭 시각이다. 실제 샘플링 지터에 대한 정보는 담고 있지 않다.
  - 실제 샘플링이 규칙적이었는지는 아래 (b)처럼 사인 적합으로 간접 확인했다.
- 버스트 사이 간격: 정상 1.55–16.6 s(중앙 4.2 s), 이상 1.78–8.57 s. 간격이 0.1 s의 배수가 아니다(5 ms 이내 비율 0.10, 무작위 수준).
  - 따라서 버스트를 이어 붙인 연속 10 Hz 시계열로 볼 근거가 없다. 버스트 경계를 넘는 창(window)은 인공 불연속을 만든다.
  - 가이드북처럼 행 단위 슬라이딩 창으로 LSTM-AE를 학습한다면 이 점을 반드시 처리해야 한다(가이드북 본문은 확인하지 않았음).

**(b) 전류 = 스트로보스코프 복제** [B, C]

- 정상 버스트 360개(30행 이상)의 단일 사인 적합 결과: 겉보기 주파수 중앙 0.6000 Hz(q05–q95 0.5972–0.6025, sd 0.0017), R² 중앙 0.996(최소 0.994), 초과 첨도 −1.46(순수 사인은 −1.5).
- 1–8차 고조파 모형의 R² 중앙값은 0.99992다.
  - 고조파비 h₂–h₈ = 0.0021, **0.0452**, 0.0008, **0.0215**, 0.0007, **0.0183**, 0.0004. 홀수 차수가 우세하며 대칭 파형에서 예상되는 결과다.
  - 실제 전류 파형을 시간축으로 약 100배 늘린 복제가 그대로 보이는 셈이다.
- 이 잔차가 모두 타이밍 지터에서 왔다고 가정해도, 60 Hz라면 RMS 지터는 중앙 23 µs(최대 116 µs) 이하다. 버스트 안 샘플링은 하드웨어 타이밍 수준으로 규칙적이다.
- 진폭 A_c: q05 114.7, 중앙 141.6, q95 250.9, 최대 261.3. 구간별 개수(100/130/160/200/230/280 경계)는 162/48/38/41/71로 두 운전 상태가 뚜렷하다.
- 겉보기 주파수와 A_c의 상관은 −0.042로, 부하가 변해도 전기 주파수는 변하지 않는다.
- 후보 전기 주파수: 10k ± 0.6 Hz = 39.4/40.6/49.4/50.6/**59.4/60.6**/69.4/70.6 Hz. 또는 f_e = 60.000 Hz이고 실제 샘플 주기가 99.00 ms나 101.00 ms인 경우와 수학적으로 같다 [E].
- 버스트 간 위상 일관성 검사: 연속 버스트 451쌍의 위상 차를 30–70 Hz 범위에서 0.0002 Hz 간격으로 스캔했다.
  - 최대 R은 0.227(60.669 Hz)이고, 스캔 전체의 최대값 null은 약 0.165다. 약간 높지만 결정적이지 않다.
  - 결론: **ms 타임스탬프와 주파수 표류 때문에 진짜 f_e는 식별되지 않는다.**

**(c) 진동의 접힌 선** [B, D, I]

- 평균 스펙트럼(버스트 평균, Hann 창)
  - AI1 고부하: 1.78 Hz 피크가 전력의 59 %.
  - AI1 저부하: 3.60 Hz 26 %, 1.80 Hz 13 %.
  - AI0 고부하: 1.80 Hz 26 %, 3.58 Hz 11 %.
- 3배·6배 고정 주파수 모형은 단일 자유 사인보다 설명력이 높다: AI1 R² 0.866 대 0.771, AI0 0.579 대 0.474.
- 1.8 Hz 선의 진폭은 A_c와 강하게 상관된다(AI1 0.975, AI0 0.907).
- 그러나 전류 위상에 고정되어 있지 않다(phase-locking R: AI1 0.076, AI0 0.047, null ≈ 0.06).
- 주파수 비 f_v/f_c는 중앙 2.985로 정확히 3이 아니다. δ = f_v − 3f_c의 평균은 −0.0078 Hz(SE 0.0007)이고, 부하 구간별로 −0.0028 / −0.0078 / −0.0110 Hz다. f₁과 2f₁을 함께 적합해도 결과가 같다(−0.0080 Hz, SE 0.0007).
- 해석
  - 측정된 전류 위상에 고정된 전기적 혼입(EMI) 가능성은 낮다. 그렇다면 R ≈ 1이고 기본파(0.6 Hz) 혼입이 가장 커야 하는데, 기본파 진폭은 0.003으로 거의 없다.
  - 유도전동기 회전 차수(m·f_sync·(1−s))라면 슬립 1 %당 m·f_sync·0.01 ≥ 0.3 Hz씩 움직여야 한다. 관측된 0.01 Hz 변화와 맞지 않는다.
  - 동기기의 기계 차수라면 정확히 고정되어야 한다(δ = 0). 이것도 맞지 않는다.
  - **원인 미해결.** 물리 주파수 대신 "운전 지문"으로만 써야 한다.
- AI0와 AI1의 상대위상은 매우 안정적이다: 1.8 Hz 선 −64.7°(R 0.865), 3.6 Hz 선 +55.7°(R 0.868). 동시 샘플링이라면 접힘을 거쳐도 채널 간 상대위상은 보존된다. 상·하부 사이 전달경로나 모드 형상의 지표가 될 수 있다.

**(d) 이상 파일의 맥락 차이** [A, B, D, F]

- 전류: 단일 사인 R² 중앙 0.527(최소 0.291), roughness 0.900(정상 0.381, 0.6 Hz 순수 사인은 0.375, 백색잡음은 1.414). 겉보기 주파수는 IQR 0.098–0.216 Hz다.
- 전류 값 600개 모두가 1.1920929 격자 위에 있다(정상 0.2 % = 우연 수준). 고유값도 340/600뿐이다(정상 19,934/20,000).
- 진동 소수 자릿수는 이상 8자리, 정상 6자리다.
- 진동 RMS
  - AI0: 정상 중앙 0.069, 최대 0.147 / 이상 중앙 0.349, 17개 중 14개가 정상 최대 초과.
  - AI1: 정상 최대 0.221 / 이상 중앙 0.227, 9/17 초과.
  - 초과 첨도: AI0 +1.56, AI1 +1.01(정상 −0.51, −0.94).
  - 버스트 3·19·20은 두 채널 모두 정상 95 % 안에 있다.
- 버스트 내 AI0–AI1 상관: 정상 +0.281, 이상 −0.314로 부호가 반전되었다.
- 이상 전류의 "잡음"에 대한 두 가설(지금 데이터로는 구분 불가)
  - (H1) 수집 방식 차이로 ms급 타이밍 지터가 생겼다. 60 Hz에서 진폭 약 300이면 σ ≈ 1 ms 정도로 이 잡음이 설명된다.
  - (H2) 실제 부하 토크 맥동이 전류를 위상변조했다(Blödt 2008의 토크 변동 → 전류 변조 기전).
  - 타이밍 지터와 위상변조는 수학적으로 같은 형태라 전류만으로는 가를 수 없다.
  - 반면 진동 RMS 증가는 지터로 생기지 않으므로 실제 물리 변화가 있었다는 쪽에 무게를 싣는다. 다만 운전 조건이 달라서일 수도 있다.

**(e) 부하가 오경보의 주원인임을 보이는 실험** [H]

- 정상 버스트를 시간순으로 반으로 나눴다(앞쪽 = 기준, 뒤쪽 = 평가).
- 순진한 기준선: 저부하 버스트 RMS의 99 % 분위를 임계로 쓰면, 평가 구간 고부하 정상 버스트가 AI1 100 %, AI0 49 % 경보된다.
- 부하 조건화 기준선: RMS ~ a + b·A_c 선형회귀(R² AI1 0.940, AI0 0.391) 잔차의 99 % 분위를 쓰면, 평가 구간 정상 버스트 2.2 %만 경보된다.
- 같은 조건에서 이상 버스트(30행 이상)는 AI1 10/10, AI0 9/10이 경보된다.
- 이상 파일의 A_c 대용치(√2·std)는 잡음 때문에 부풀어 있다. 그래서 예측 RMS가 커지고 잔차는 작아지므로, 이 결과는 보수적이다.

### 3.2 aliasing·언더샘플링 이론과 물리적 해석

- **접힘 공식**: 주파수 f인 성분을 fs로 균일 샘플링하면 겉보기 주파수는 f_a = |f − k·fs|(가장 가까운 정수 k)로 [0, fs/2]에 접힌다.
  - fs = 10 Hz에서 10 Hz의 배수(60, 120, 180, 360 Hz …)는 모두 DC로 접힌다.
  - 정확한 10 Hz 샘플링과 60 Hz 계통이라면 선(line) 동기 성분은 전부 0 Hz에 모인다 [G].
  - 2·4·6극 유도전동기의 1× 회전 주파수는 동기속도(60/30/20 Hz)가 10의 배수이므로 "기계적 슬립 속도" s·f_sync로 접힌다(예: 4극, s = 1.5 % → 0.45 Hz).
  - **우리 데이터에서는 전류가 0 Hz가 아니라 0.600 Hz에 있으므로 이 단순한 그림이 성립하지 않는다.**
- **bandpass sampling**(Vaughan et al. 1991, P1): 초록에 따르면 "the signal-to-noise ratio is not preserved owing to the out-of-band noise being aliased".
  - 10 Hz 샘플에는 아날로그 대역 전체의 광대역 잡음이 0–5 Hz로 접혀 들어온다. 선 검출 SNR은 떨어진다.
  - 반대로 표본 분산은 전체 대역의 분산을 그대로 담는다.
- **분산 불변성**(유도): 넓은 의미의 정상(WSS) 과정 x(t)에 대해 E[x(t_n)²] = R_x(0)이고, 이는 샘플 시각과 무관하다.
  - 따라서 언더샘플링이든 지터든 표본 RMS는 아날로그 대역 전체 RMS의 불편 추정량이다. 상관만 추정 분산에 영향을 준다.
  - 결정적 주기 신호라면 창 안에서 위상이 고르게 덮일 때만 성립한다. 접힌 주파수 × 버스트 길이 ≳ 1이어야 한다. 정상 전류는 0.6 Hz × 4.9 s = 2.9주기로 충분하고, 이상 전류(약 0.1–0.2 Hz)는 1주기 이하로 부족하다.
  - Clarke & Stockton(1982, P20)의 초록: 등간격 순시 표본 기반 전력계에서 "Sinusoidal waveforms are handled correctly, and the errors with near-sinusoidal waveforms are generally negligible". 언더샘플링한 순시값으로 전류 진폭·RMS를 계산하는 것이 계측학적으로 정당하다는 근거다.
- **샘플-앤-홀드·평균·RMS 출력이었다면 어떻게 보였을까**
  - 블록평균(길이 T): 성분 f를 |sinc(fT)|만큼 감쇠시킨다. T = 100 ms이면 60 Hz는 정확히 0, 59.4/60.6 Hz는 약 1 %만 남는다.
  - 60 Hz 적분형 ADC(50/60 Hz 잡음 제거형): 비슷하게 소거된다.
  - RMS/4–20 mA 송신기: 음수가 없는 느린 레벨이 나오고 영점 교차가 없다.
  - 피크홀드: 계단 모양의 양수 값이 나온다.
  - 실제 데이터는 ±270의 깨끗한 사인과 7차 고조파까지 보이므로, **순시 점표본에 anti-alias 필터가 없는 경우**로 판단한다. 진동도 접힌 고차 선이 보이므로 같은 판단이 유력하다(증명은 아님).
- **전기 주파수 추정법과 한계**
  - 버스트 안에서 4-parameter sine fit을 한다(IEEE 1057, S13. Händel 2000, P17은 "noisy data covering only a fraction of a period"에서는 1차원 탐색이 더 낫다고 보고). 또는 floating-mean GLS 주기도 다음 NLS를 쓴다(P18, P19). 본 스크립트가 쓴 방법이다.
  - 정밀도는 CRLB(Rife & Boorstyn 1974, P16)를 따른다. 정상 전류처럼 SNR이 높으면 버스트당 약 10⁻³ Hz 수준이다.
  - k와 부호의 모호성은 단일 샘플률로는 풀 수 없다. 서로 다른 샘플률(Xia 1999, P22; co-prime sampling, P23)이나 sub-ms 정확도의 연속 타임스탬프가 필요하다. 본 데이터에서는 실패했다 [E].
  - 유사 사례: ENF(계통 주파수) 포렌식(P21)은 조명 깜빡임을 영상(저프레임)으로 기록해 계통 주파수 변동을 복원한다. "저율 샘플로 주파수 *변동*을 추적"하는 것은 학계에서 확립된 접근이다. 단, 영상 프레임 기반이라 aliasing을 거친다는 것은 우리의 해석이며 초록에 명시된 내용은 아니다.
- **겉보기 주파수 변화의 물리적 의미** — 어느 채널이 변하는지가 단서다.

| 원인 | 전류 겉보기 주파수 | 회전 관련 진동선 | 비고 |
|---|---|---|---|
| 계통 주파수 표류(직입 전동기) | 변함(Δf 그대로) | 변함(같은 비율) | 계통은 법정 허용범위 ±0.2 Hz로 알려짐(L1, 미확인). 0.6 Hz 상시 편차는 계통으로 설명 불가 |
| VFD 설정 주파수 변경 | 변함 | 변함 | 서보펌프라면 운전 중 계속 변함 → 본 정상 데이터는 77분간 ±0.002 Hz로 고정 |
| 부하 증가 → 슬립 증가(유도기) | **안 변함**(고정자 주파수 = 공급 주파수) | 변함(1 %당 ≥ 0.3 Hz) | 본 데이터의 진동선 변화는 약 0.01 Hz라 해당 없음 |
| DAQ 샘플 클럭 변화 | 변함(f·ε) | 변함(f·ε) | 정상일 → 이상일 사이에 0.6 → 약 0.1–0.2 Hz로 변함. 구동 주파수나 수집 클럭 중 하나가 달라졌다는 뜻 |

**계획 활용**

1. **맥락 게이트(context gate)**: 버스트마다 전류 겉보기 주파수 f_c와 적합 R²_c를 계산한다. 이 설비 정상 범위(f_c 0.597–0.603 Hz, R²_c ≥ 0.99) 밖이면 "구동·수집 맥락 변화"로 표시하고, 스펙트럼 계열 특징을 신뢰하지 않는다. 고장 경보와 분리해 운전자에게 "데이터·설비 상태 확인"으로 안내하면 오경보가 줄어든다.
2. **부하 변수 A_c**: 이상 점수를 조건화하는 공변량으로 쓴다(§3.1e).
3. **고조파비(h₃/h₁, h₅/h₁, h₇/h₁)**: 정상 내 추세 감시용(전원·구동 품질)으로만 쓴다. f_c가 다른 이상 파일에는 직접 비교할 수 없다.

### 3.3 저샘플링 특징량: 물리적 의미 대 접힘 인공물

| 특징 | 10 Hz에서의 의미 | 접힘·수집 민감도 | 권고 |
|---|---|---|---|
| 진동 RMS/std | 아날로그 대역 전체 broadband 크기(단위 미상)의 불편 추정 | 낮음(분산 불변). 단 N = 50에서 상대 SE 약 10 %(가우스, 1/√(2(N−1))) | **핵심.** 부하 조건화 잔차로 |
| 강건 분위수(MAD, q95−q05) | 크기, 꼬리 | 낮음. 극단 분위는 N 의존 | 고정 길이 창(예: 20행) 또는 N 보정 |
| p2p, max, crest factor | 충격성 | 극값이라 N 의존이 크다. ms급 충격은 100 ms 간격 점표본에 거의 안 잡힘 | 단독 사용 지양, 길이 보정 필수 |
| kurtosis, skewness | 분포 모양(충격·비선형) | 주변분포는 보존되지만 N ≤ 50이면 추정 분산이 크다. 선이 우세하면 음수(사인 −1.5) | 보조. 이상 +1.0–1.6 대 정상 −0.5–−0.9. Dyer & Stewart(P15)의 "kurtosis… remains constant for an undamaged bearing irrespective of load and speed"는 고샘플링 전제라는 점을 밝힐 것 |
| 전류 사인 진폭 A_c | 부하 | 버스트가 접힌 주기를 1회 이상 덮어야 신뢰 가능 | 핵심 공변량 |
| 전류 f_c, R²_c, 적합 잔차 | 구동·수집 맥락, 파형 청결도 | **매우 높음**(그 자체가 접힘 지표) | 게이트·품질 지표로만. 분류 입력에서는 제외 |
| dominant f, spectral centroid/entropy(P14) | 접힌 스펙트럼의 모양 | **매우 높음** | confound 실험 전용 |
| ZCR, Hjorth mobility/complexity(P8) | 접힌 평균 주파수·대역폭(mobility = √(var(Δx)/var(x)), 본 roughness와 같은 계열) | 높음: roughness 정상 1.21–1.41 대 이상 0.77–0.80, 전류 0.38 대 0.90 | 같음 |
| permutation entropy(P9, P11) | 연속 표본의 순서 패턴. 단조 변환에 불변(초록) | 높음. 양자화 tie가 "false conclusions"를 낳을 수 있음(P10). 이상 파일 전류가 1.19 격자 | 같음 |
| sample/approximate entropy(P12) | 규칙성 | 높음. "extremely sensitive to parameter choices, especially for very short data sets, N≤200"(P13) | 버스트 단위로는 비권장 |
| AI0–AI1 상관, 고정선 상대위상 | 상·하부 전달경로·모드 | 동시 샘플링이면 상대위상은 보존되지만, 접힌 선이 같은 조건에서만 비교 가능 | 정상 내 변화 감시(R 0.87로 안정). 파일 간 비교 금지 |
| RMS_AI1/RMS_AI0 비 | 상·하 진동 분배 | 낮음 | 보조 |
| 부하 조건화 잔차 r = RMS − f(A_c) | 운전 변화를 뺀 이상 | 낮음 | **주 이상 점수 후보**(P24, P25의 운전 조건 정규화와 같은 발상) |

### 3.4 진동·상태감시 표준: 무엇이 적용되고 무엇이 안 되나

**ISO 20816-1:2016 (S1)** — 초록과 공개 미리보기 기준 내용

- §4.1.3 Frequency range: "The measurement of vibration shall be broad band, so that the frequency spectrum of the machine is adequately covered."
  - NOTE 1: "In the past, broad-band measurements in the range 10 Hz to 1 000 Hz were the intended metric for full-load acceptance testing. This might not meet the requirements of a condition monitoring scheme…"
  - 즉 10–1000 Hz는 과거 인수시험의 관례 대역이다. 상태감시에서는 더 넓을 수 있다. 어느 경우든 10 Hz 샘플(나이퀴스트 5 Hz)로는 불가능하다.
- §4.2: "it is important at all times to identify clearly the measurement quantity and its unit". 비회전부에 권장되는 측정량은 "r.m.s. velocity"다. 우리 데이터는 단위와 측정량(가속도/속도)이 모두 미상이라 이 요건부터 충족하지 못한다.
- 목차에서 확인한 조항(본문 미열람): §6.3.3 "Criterion II: Change in vibration magnitude", §6.4.2 "Setting of ALARMS", §6.4.3 "Setting of TRIPS", Annex D "Vector analysis of change in vibration". 변화량 기준의 구체 수치(예: 25 %)는 미확인이다.
- 평가 기준은 "in terms of both vibration magnitude and change of vibration"이며 "Guidelines are also presented for setting operational limits"라고 되어 있다.
- 또 "The ISO 20816 series permits the use of different measurement quantities and methods, provided that they are well-defined and their limitations are set out"라고 한다. 그래서 우리의 "10 Hz 언더샘플링 RMS(단위 미상)"를 **표준 측정량이 아니지만 정의와 한계를 명시한 양**으로 소개하고, 절대 zone 대신 *변화*로 평가하는 것이 표준의 정신과 맞는다.
- 다만 "The evaluation criteria relate only to the vibration produced by the machine itself and not the vibration transmitted to it from outside"라고 되어 있다. 프레스 타발 충격이 펌프 센서로 전달되는 성분은 기준 밖이며, 우리 데이터로는 이를 분리할 수 없다(§4).

**ISO 20816-3:2022 (S2)**

- 15 kW 초과, 120–30,000 r/min 산업기계에 적용된다. 유연 커플링 전동기는 포함된다.
- 명시적으로 제외되는 것: rotodynamic pumps(→ ISO 10816-7), 왕복동 기계(→ ISO 10816-6), rotary positive displacement compressors 등.
- 요건 문장: "apply to in-situ **broad-band** vibration measurements … under **steady-state operating conditions** within their nominal operating speed range."
- 프레스 유압펌프는 ① 용적식일 가능성이 높고, ② 프레스 사이클 때문에 부하가 주기적으로 바뀌어 정상 상태가 아니며, ③ 10 Hz로는 broadband 속도 RMS를 계산할 수 없다. **세 가지 모두 적용 조건을 벗어난다.**
- 20816-3 본문의 대역 규정(예: "10 Hz–1 kHz, 저속기는 2 Hz–1 kHz")은 기억에 의존한 것이며 미확인이다. 확인된 것은 20816-1 §4.1.3 NOTE 1의 "과거 인수시험 관례 10–1000 Hz"까지다.
- 대역 상한이 1 kHz라면 최소 2 kHz, 관례상 2.56 kHz 이상의 샘플링과 anti-alias 필터가 필요하다. **10 Hz와는 2–3 자릿수 차이**다.

**ISO 10816-7:2009 (S3)** — 적용 대상은 "rotodynamic pumps for industrial applications with nominal power above 1 kW"뿐이다. 기어·베인·피스톤 등 용적식 유압펌프에는 해당하지 않는다. 용적식 유압펌프를 직접 다루는 ISO 진동 심각도 표준은 이번 조사에서 찾지 못했다. 검색 제약 때문에 "없다"고 단정할 수는 없다.

**ISO 13373-1/-2/-3 (S4–S6)** — 측정 방법, 센서 선택·부착, 신호조건화, 시간·주파수 영역 분석, 진단 절차를 다룬다(초록 기준). 우리 보고서에서는 "현 수집 체계(10 Hz 점표본, AA 필터 없음)가 13373 계열이 상정하는 진동 상태감시 측정 체계에 못 미친다"는 개선 권고의 근거로 쓴다. anti-aliasing 관련 구체 조항 번호는 미확인이다.

**ISO 17359:2018 (S7)** — 초록: "general procedures … when setting up a condition monitoring programme for machines", "applicable to all machines". 미리보기에서 읽은 조항 중 우리에게 직접 쓰이는 것은 다음과 같다.

- §8.1: "For certain parameters, such as current, voltage, and vibration, simple measurements of overall values might not be sufficient to show the occurrence of a fault. Techniques such as time, spectral and phase measurement can be required…"
  - **반론 근거다.** 우리 데이터는 사실상 overall 값만 믿을 수 있다(§3.3). 그러므로 "검출 가능한 고장 유형이 제한된다"고 명시해야 한다.
- §8.2: "Methods using trending of values can be effective where repeatability of measurement is more important than absolute accuracy of measurement."
  - 단위 미상 데이터로 **추세·기준선 대비 감시**를 하는 정당화 근거다.
- §8.4 Operating conditions during monitoring
  - "Subsequent measurements are compared to the baseline values to detect changes."
  - "Measurements of different parameters should be taken wherever possible at the same time or under the same operating conditions."
  - "…determine if a change … is due to the occurrence of a fault or is due to a change in duty or operating conditions."
  - **부하 조건화 기준선(§3.1e)과 맥락 게이트(§3.2)의 직접 근거다.**
- §8.6 Data acquisition rate: "fast enough to capture a complete set of data before conditions change". 버스트(4.9 s) 안에서는 부하가 거의 일정하다는 가정을 점검할 필요가 있다는 근거다.
- §8.7: 기록에는 "essential data describing operating conditions", "the measured quantity units and processing", "date and time information"이 포함되어야 한다. **현 데이터셋은 단위와 처리 정보가 없어 이 요건을 못 채운다.** 현장 적용 권고에 넣을 것.
- §8.9 "Initial alert/alarm criteria", §8.10 "Baseline data", §9.3 "Measurement comparison to alert/alarm criteria", §9.4 "Diagnosis and prognosis": 목차로만 확인했고 본문은 미리보기 범위 밖이다. 조항 번호로만 인용할 것.

**ISO 13379-1 (S8)** — 2012판은 진단 기법 지침이며, FMSA(Failure Mode Symptoms Analysis) 개념으로 알려져 있다(기억, 본문 미열람). **2012판은 ISO 13379-1:2025(2판, 제목 "…of machine systems…")로 대체되어 철회되었다.** KS B ISO 13379-1은 2024-12-20 확인 기준으로 아직 2012판 부합이다. 인용한다면 "ISO 13379-1:2025(KS B ISO 13379-1은 2012판 부합)"로 쓸 것.

**ISO 13381-1:2025 (S9)** — 예지 지침이다. 고장까지의 추세(run-to-failure)가 없고 이상 에피소드가 하나뿐이므로, 우리는 "예지(ETTF/RUL)"가 아니라 "탐지·경보"까지만 주장해야 한다.

**ISO 18436-2:2014 (S10)** — 진동 분석 인력 자격(4개 등급)이다. 현장 적용 절에서 "경보 해석과 점검 우선순위는 자격 있는 인력이 최종 판단"이라는 운영 원칙의 근거로 쓴다.

**KS 부합 현황(2026-10-01, e-나라표준인증)**

| KS | 한글명(요지) | 제정 / 최종 개정·확인 | 대응 국제표준(페이지 표기) |
|---|---|---|---|
| KS B ISO 17359 | 기계의 상태 감시 및 진단 ― 일반 지침 | 2004-12-30 / 2024-12-20(2019-12-19 개정으로 2018판 부합) | ISO 17359:2018 IDT |
| KS B ISO 20816-1 | 기계적 진동 ― 기계 진동의 측정과 평가 ― 제1부: 일반 지침 | 2018-03-22 / 2023-12-29 | 'ISO/NP 20816-1' IDT로 표기(DB 표기 오류 추정, 2016판으로 판단) |
| KS B ISO 20816-3 | … 제3부: 15 kW 초과, 120–30 000 r/min 산업용 기계류 | **2026-07-28 제정** | ISO 20816-3:2022 IDT |
| KS B ISO 10816-7 | … 제7부: 산업용 회전동역학 펌프 | 2017-02-17 / 2022-12-29 | ISO 10816-7:2009 IDT |
| KS B ISO 13373-1 / -2 / -3 | 진동 상태 감시 제1부 일반 지침 / 제2부 데이터 처리·분석·표현 / 제3부 진동 진단 지침 | 2004-12-30 / 2026-07-16 · 2007-09-05 / 2022-12-29 · 2018-03-22 / 2023-12-29 | ISO 13373-1:2002 · (2005판 표기, 2017·2022 개정) · 'ISO/PRF 13373-3' |
| KS B ISO 13379-1 | 데이터 해석 및 진단 기술 제1부 | 2004 제정 → 2014-12-29 개정(13379:2003 → 13379-1:2012) / 2024-12-20 | 2012판 부합(ISO는 2025판으로 대체) |
| KS B ISO 13381-1 | 예측진단 제1부 일반 지침 | 2007-06-29 / 2026-08-28 | ISO 13381-1:2015 IDT(ISO는 2025판 발행) |
| KS B ISO 18436-2 | 요원 자격 — 진동 | 2004-12-30 / 2026-08-28 | ISO 18436-2:2014 IDT |
| KS B ISO 13372 | 상태 감시 및 진단 — 용어 | 2005-10-18 / 2025-09-05 | ISO 13372:2012 IDT |
| KS B ISO 2954 | 진동 심각도 측정기 요구사항 | – / 2026-07-16 | 'ISO 2954:1975' 표기 |
| KS C IEC 60034-14 | 회전기기 기계적 진동(축 높이 56 mm 이상) | 2002-06-29 / 2025-04-03 | IEC 60034-14 Ed.4.0. **무부하·비연결 시험 조건**이라 현장 감시에는 부적합 |
| KS B ISO 20958, KS B ISO 10816-3 | – | 조회 결과 없음 | – |

**전문가가 받아들일 주장의 경계**

- 받아들일 만한 주장
  - "10 Hz 순시 표본의 버스트 RMS는 센서·DAQ 아날로그 대역 전체 진동 크기의 (단위 미상) 추정치다. 정상 기준선 대비 *변화*를 감시하는 데 쓴다."
  - "전류 진폭은 부하 지표이며, 진동 크기의 부하 의존성을 보정하는 데 쓴다."
  - "0–5 Hz 스펙트럼 선은 접힘 지문이고 물리 주파수가 아니다. 그 안정성만 감시한다."
  - "모델 출력은 같은 설비·같은 수집 조건의 정상 기준선 대비 이상 확률(점수)이다. 이상 사례가 1건이라 일반화 성능은 입증되지 않았다."
- 받아들이기 어려운 주장
  - ISO zone(A/B/C/D)이나 mm/s 경계값을 이 값에 적용하는 것.
  - "베어링·기어 결함 주파수 검출", "MCSA로 회전자 결함 판별".
  - "1.8 Hz 진동"을 물리 주파수로 해석하는 것.
  - 10 Hz 데이터로 펌프 진동 스펙트럼을 "포착"했다는 표현.
  - 예지(RUL/ETTF)를 주장하는 것.

### 3.5 MCSA: kHz가 필요한 것과 10 Hz로 가능한 것

- MCSA는 "spectral analysis of the stator current"(P3 초록)로 결함 관련 고조파·측대역을 찾는다(P2, P4).
  - 회전자 바, 편심, 베어링, 부하 토크 진동(P5: 베어링 결함 → "load torque variations" → 전류 주파수 성분)이 대상이다.
  - 측대역은 공급 주파수 주변 수 Hz(회전자 바, 슬립 의존)부터 수백 Hz–kHz(슬롯 고조파, 베어링)까지 퍼져 있다.
  - 따라서 kHz 샘플링, 수십 초 이상 연속 기록(0.01–0.1 Hz 분해능), 높은 동적 범위가 필요하다(일반 원리. 구체 수치 기준은 P2·P7 본문 미확인).
  - 실무 사례(P6)는 기어박스 동역학 같은 기계 구동계 성분과 결함 성분을 분리해야 한다고 강조한다(초록). 펌프 맥동이 있는 우리 시스템도 마찬가지다.
- 10 Hz·4.9 s 버스트의 한계
  - 분해능이 약 0.2 Hz다.
  - 모든 성분이 0–5 Hz에 겹쳐 접힌다.
  - 고조파 모형의 잔차 바닥은 약 −41 dB다(R² 0.99992 → 잔차 전력 8×10⁻⁵).
  - 결론: 일반적으로 약한(수십 dB 아래) 측대역은 원리적으로 볼 수 없다.
- 10 Hz로 가능한 것
  1. 진폭(부하)과 그 버스트 간 추세. 부하 상태(저/고) 분류도 여기에 포함된다.
  2. 버스트 내 진폭 변화(앞/뒤 반 진폭비): 0.3 Hz보다 느린 부하 변동.
  3. 스트로보스코프로 얻는 저차 고조파비(f_c가 안정적일 때만).
  4. 적합 잔차·roughness: 전기·수집 품질 지표. 정상 0.38 대 이상 0.90이지만 confound 위험이 크다.
  5. 진동과 전류의 결합 관계(기울기 b, 잔차).

### 3.6 센서 측면 해석

- **"AI0/AI1/AI2"**: DAQ·PLC 아날로그 입력 채널 번호(analog input 0/1/2)라는 관례적 표기다. 예: NI-DAQmx의 "Dev1/ai0"(V2). 문서로는 확인하지 못했다.
- **진동 채널**
  - 평균 약 0(−0.0001), 대칭이고 접힌 고차 선을 포함한다.
  - IEPE/ICP 가속도계처럼 AC 결합 동적 신호를 그대로 샘플링한 형태와 맞는다. V1: "ICP® accelerometers are AC coupled devices…".
  - 4–20 mA 진동 송신기는 보통 overall RMS(속도 또는 가속도)를 직류 전류로 낸다. 그렇다면 값이 음수가 없는 느린 레벨이어야 한다. 이 일반론은 제조사 데이터시트로는 확인하지 못했다.
  - 대조 사례: 공개 유압 시험대 데이터(P26, UCI)는 VS1 진동을 **mm/s 단위·1 Hz**로 기록한다. RMS형 공정값 채널의 전형이다.
  - 우리 AI0/AI1은 그런 RMS 채널이 아니다. 단위는 g, mm/s, V 중 무엇인지 알 수 없다.
- **전류 채널**
  - 0을 중심으로 대칭인 순간 교류 파형이다. CT(교류 전용) 또는 Hall 센서의 순시 출력으로 보인다. RMS 변환형 전류 트랜스듀서라면 양수 레벨이어야 한다.
  - 진폭 114–261을 첨두 A로 보면 RMS 80–185 A다. 380–440 V급에서 수십–100 kW대 전동기라는 가설과 그럴듯하게 맞지만, **단위와 채널 배율이 미상이므로 가설로만** 쓸 것.
  - 이상 파일 전류의 1.1920929 격자(10⁷/2²³, 24-bit 코드 간격과 같은 꼴)는 다른 변환·배율 경로를 시사한다. 이상 파일의 전류 배율이 정상과 같다는 보장도 없다.

### 3.7 계획에 넣을 구체 항목

**특징(버스트 단위 또는 고정 20행 창)**

- 핵심: A_c(사인 적합), RMS_AI0, RMS_AI1, MAD·(q95−q05), kurtosis, RMS_AI1/RMS_AI0, 부하 조건화 잔차 r_AI0·r_AI1.
  - 잔차 모형은 선형 → 분위회귀나 GAM으로 확장할 수 있다. 부하 상태별 기준선도 가능하다.
- 정상 내 감시 전용: 고조파비, AI0–AI1 상대위상(고정선), 고정선 진폭(3f_c, 6f_c).
- 게이트·품질: f_c, R²_c, roughness, 표본 수 N.

**실험**

- **E1 confound 실증**: 맥락 특징(f_c, R²_c, roughness, 양자화 격자 적중률, 소수 자릿수)만으로 정상/이상 분류를 한다. AUC ≈ 1이 나오면 "자명한 분리"를 보고하고 주 모델에서 뺀다.
- **E2 접힘 불변 ablation**: 진폭 특징만 쓴 모델과 스펙트럼·순서 특징을 더한 모델을 비교한다. 성능 향상이 E1의 맥락 차이로 설명되는지 확인한다.
- **E3 길이 통제**: 고정 길이 창으로 다시 평가하고, 특징과 N의 상관을 확인한다(정상 중앙 37 대 이상 28).
- **E4 부하 조건화 ablation**: §3.1e처럼 시간 블록 분할로 순진한 임계와 조건화 임계를 비교해 정상 FP율을 보고한다.
- **E5 지터 민감도 시뮬레이션**: 정상 전류의 고조파 모형에 0–2 ms 지터를 넣어 R²·roughness 변화를 측정한다. 이상 파일 수준(roughness 0.9)을 재현하는 지터 크기를 제시한다. 진동 RMS는 불변임을 함께 보인다.
- **E6 라벨 입도**: 이상 버스트별 점수를 보고, 정상처럼 보이는 3·19·20의 사유를 FN 분석에 넣는다.

**경보·임계**

- alert: 정상 보류(hold-out) 데이터 잔차의 99 % 분위.
- alarm: 최근 n개 버스트 중 k개 이상 초과(예: 3-of-5). 지속성 규칙으로 단발 오경보를 억제한다.
- 맥락 게이트가 켜지면 "고장 경보"가 아니라 "구동·수집 상태 확인"으로 낸다.

**평가 지표**

- 정상 데이터에서 버스트당 FP율을 **시간당 오경보 건수**로 바꿔 보고한다. 정상은 599 버스트/77분 ≈ 467 버스트/시간이므로 버스트당 1 %면 시간당 약 4.7건이라 현장에서 쓸 수 없다.
- k-of-n의 이론값은 독립 가정에서 매우 작지만, 부하 상태가 지속되므로 독립이 아니다. 반드시 실측으로 보고할 것.

**현장 적용**

- 점검 우선순위
  - 조건화 진동 잔차↑ + 전류 정상 → 기계·유압(펌프·커플링·마운트) 점검.
  - 전류 파형 이상(R²_c↓, f_c 변화) → 구동·전원·DAQ 점검.
  - 둘 다 → 긴급.
- 운전자 화면: "부하 보정 진동 지수 + 맥락 상태"를 보여준다.
- 설비 개선 권고
  - 진동: anti-alias 필터와 kHz 샘플링(예: IEPE + 24-bit DAQ). 또는 10–1000 Hz 속도 RMS 송신기를 추가해 ISO 20816 평가를 가능하게 한다.
  - 전류: kHz 연속 기록(MCSA용).
  - 압력·스트로크 신호 추가. 이 권고는 ISO 13373-1, ISO 17359을 근거로 든다.
  - ISO 17359 §8.7에 따라 측정량·단위·처리(필터, 샘플링, 타임스탬프 생성 방식)와 운전조건(제품·금형·설정 압력·구동 주파수)을 데이터와 함께 기록한다. 이번 데이터셋에서 가장 크게 빠진 부분이다.

---

## 4. 위험·한계·반론

1. **단일 이상 에피소드 + 다른 날·시각 + 다른 수집·내보내기 경로**(전류 접힌 주파수, 양자화 격자, 소수 자릿수가 모두 다름). 어떤 분리 성능도 "이 에피소드와 이 정상 밤의 분리"일 뿐이다. 모델이 고장이 아니라 수집·구동 맥락을 배웠을 가능성을 배제하려면 E1·E2가 필수다.
2. **반론 — 진폭 증거도 완전히 깨끗하지 않다.** 진동 RMS 증가(3–5배)는 지터나 접힘으로는 안 생긴다. 하지만 이상일에 전기 주파수(= 펌프 속도) 자체가 달랐다면 속도·운전 조건 차이만으로 진동이 커질 수 있다. 일요일 오전이라는 운전 맥락도 다르다. "고장 때문"이라고 단정하지 말고 "정상 기준선 대비 이례적"이라고 표현할 것.
3. **프레스 충격의 전달 진동.** 펌프 센서에는 프레스 타발 충격이 구조를 통해 전달된 성분이 섞일 수 있다(ISO 20816-1도 외부 전달 진동은 평가 대상에서 제외). 10 Hz 점표본과 스트로크 신호 부재 때문에 분리할 수 없다.
4. **1.8/3.6 Hz 선의 원인 미해결.** 전기적 혼입도, 유도기 회전 차수도, 동기기 차수도 관측과 맞지 않는다. 우연의 일치(약 3배)일 수도 있다. 해석에 쓰지 말 것.
5. **AA 필터 부재 판단은 추론이다.** 전류는 확실하다(7차까지 원래 크기의 고조파). 진동은 정황 증거(접힌 선)만 있다.
6. **부하 조건화 모형은 하룻밤(77분) 데이터로 적합했다.** 제품·금형·유온·계절이 바뀌면 기준선이 이동할 수 있다. 이상 파일의 A_c 대용치도 잡음으로 부풀어 있다.
7. **버스트당 표본이 적다(≤ 50).** RMS 상대 SE가 약 10 %이고 첨도·엔트로피는 더 불안정하다. 버스트 단위 결정은 잡음이 크므로 집계와 지속성 규칙이 필요하다.
8. **단위 미상.** 어떤 표준 수치와도 비교할 수 없다.
9. **위상 일관성 분석(E절)은 결론 없음.** 타임스탬프의 실제 정밀도는 모른다.
10. **문헌 측 한계.** WebSearch를 쓸 수 없어 문헌 발견이 제한적이었다. 특히 "저샘플링·aliasing 기반 상태감시"를 직접 다룬 최신 논문, 용적식 유압펌프 진동 기준, 프레스 유압 시스템 사례가 빠졌을 수 있다. MCSA 판정 수치(측대역 dB 기준표 등)는 본문을 열지 못해 쓰지 않았다.

## 5. 아직 확인 못 한 것

- 유료 본문이라 미열람인 조항: ISO 17359:2018 §8.9(initial alert/alarm criteria)·§8.10·§9.3의 본문(목차로 번호만 확인), ISO 20816-1 §6.3.3 Criterion II의 구체 수치(예: 25 %, 기억)와 §6.4.2 ALARM 설정 규칙, ISO 20816-3의 측정 대역 규정, ISO 13373-1/-2의 anti-aliasing·샘플링 조항.
- ISO 13379-1:2025의 정식 발행일(ISO 페이지 id 88027 추정, 보관본 없음).
- ISO 20958:2013(전기 신호 분석)의 존재·범위 확인. KS 부합본은 조회되지 않았다.
- IEEE Std 1057의 판 연도(메타데이터에 번호·연도 없음).
- 한국 계통 주파수 법정 허용범위(전기사업법 시행규칙 별표, ±0.2 Hz로 알려짐) 원문.
- NI 등 DAQ 채널 명명 규칙 문서, 4–20 mA 진동 송신기 출력 정의(제조사 데이터시트).
- 설비 사실관계 — 데이터 제공처(KAMP/스마트제조혁신추진단·InterX)에 문의할 가치가 있다
  - 센서와 DAQ 모델, 단위·배율, 아날로그 대역·필터
  - 타임스탬프 생성 방식
  - 구동 방식(직입/VFD/서보)과 설정 주파수, 전동기 극수, 펌프 형식(기어/베인/피스톤)
  - **이상 파일을 같은 수집 체계로 기록·내보냈는지**
- 이상일 전류 "잡음"이 수집 지터(H1)인지 실제 토크 맥동(H2)인지. 전류만으로는 원리적으로 구분 불가하고 고샘플링 재측정이 필요하다.
- 1.8/3.6 Hz 접힌 진동선의 물리적 원인.
