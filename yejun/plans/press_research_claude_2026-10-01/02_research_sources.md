# 02. 리서치 출처 — 신뢰도·확인 방식·라이선스·사용 위험

- 작성: 2026-10-02, Claude Code. 근거는 `sources/R1–R9`(2026-10-01 리서치 원보고서)와 계획 문서 01·03·04·05뿐이다. 이 문서를 쓰면서 웹 검색은 하지 않았다.
- 원보고서에 없는 서지·DOI·쪽수는 넣지 않았다. 예외는 총괄 계획자가 Crossref 메타데이터나 공식 문서로 직접 확인한 6건이다(2026-10-01 4건, 10-02 2건; 확인 열에 "(Claude)").
- **[v2 주의]** "계획에서 쓰는 곳" 열은 이 문서를 쓸 때의 계획 v1 절 번호 기준이다. v2(2026-10-02)에서 03·04·05의 절 구성이 바뀌었으므로 위치는 `06_review_response.md`와 각 문서의 현재 절 제목으로 확인한다. 쓰지 않게 된 출처(예: Cauchy 결합)는 행에 [v2] 표시를 했다.
- 표기: `R4-S13` = R4 보고서 출처표의 S13. 이 문서의 행 번호(KM-01 등)는 다른 계획 문서에서 가리킬 때 쓴다.

## 0. 사용 원칙

### 0.1 등급

| 등급 | 뜻 | 쓰는 법 |
|---|---|---|
| A | 동료심사 학술지·주요 학회, 국제·국가 표준, 정부·공공기관(법령 포함) | 근거로 인용 |
| B | 프리프린트, 기술보고서·학위논문, 제조사 기술문서, 업계 단체 지침, 데이터 저장소 기록 | 근거로 쓰되 성격을 밝힘("프리프린트", "제조사 주장", "2차 재현") |
| C | 블로그·포럼·개인 저장소·홍보물·벤더 마케팅 | 근거로 쓰지 않음. 길잡이로만 |

- 등급은 원보고서 표기를 그대로 옮겼다. 보고서마다 경계가 조금 다르다(R2는 GitHub 개인 저장소를 C로, R7은 KCI 등재지를 A로 둔다). 보고서끼리 등급이 다르면 둘 다 적었다.
- 소프트웨어 행(2.12)은 근거 등급 대신 라이선스 확인 여부만 본다(R4는 코드를 근거 C로 분류했다).

### 0.2 확인 방식

| 수준 | 원보고서 표기 | 뜻 |
|---|---|---|
| 본문 | opened(R1·R2·R6·R7), opened-전문(R3·R8), opened(본문)(R4), [열람](R5), 열람-전문(R9) | 원문이나 공식 미리보기를 직접 읽음. 단 R6의 opened는 "원 페이지·메타데이터·초록·공개 미리보기"를 모두 포함하고, R5의 [열람]에는 초록만 본 경우가 섞여 있다. 괄호 설명을 함께 본다 |
| 초록·목차 | opened-초록(R8), opened(초록)·opened(목차)(R4), 열람-초록(R9), meta(초록 …)(R1) | 내용 주장은 초록·목차 범위까지만 |
| 메타 | meta(R1), opened-메타(R3), opened(메타)(R4), 메타·메타만(R8), Crossref 메타데이터만(R2) | 서지만 확인. 내용을 인용하기 전에 원문을 연다 |
| search-only | search-only, [검색만](R5), 검색만(R9) | 검색 요약만 봄. R5·R9의 [검색만]에는 Crossref 서지만 본 경우도 들어 있다 |
| 미확인 | unverified, [미검증](R5), 미검증(R9) | 근거로 쓰지 않음 |
| 총괄 계획자 확인 | Crossref 메타 확인(Claude), 공식 문서 열람(Claude) | 2026-10-01 직접 확인 |

- 확인 열은 원보고서 문구를 그대로 옮겼다. 긴 괄호 설명만 "…"로 줄였다. 확인 수준을 올려 적은 행은 없다.
- 여러 보고서가 같은 출처를 다르게 적었으면 "열었다"고 명시한 보고서의 더 강한 표기를 앞에 두고 〔R#〕로 밝혔다. 원보고서 ID 열에는 모든 ID를 적었다.

### 0.3 인용 규칙

1. **유료 표준**(ISO·IEC·ISA·EEMUA·NAMUR·KS): 번호·제목·조항 번호와, 미리보기로 확인한 짧은 문구만 인용한다. 표·그림·zone 경계값·본문 문장은 옮기지 않는다. 미리보기 범위 밖 조항은 번호만 쓰고 내용을 서술하지 않는다. "표준을 준수했다"고 쓰지 않는다(R7).
2. **그림**: CC BY(또는 CC0·공공영역)일 때만, 출처를 밝히고 우리가 다시 그려서 쓴다. CC BY-NC·NC-ND(PVLDB 논문 등), 출판사 저작권 그림, 가이드북 그림은 재사용하지 않는다.
3. **데이터**: 제출 zip에 넣을 수 있는 외부 데이터는 CC BY·CC0뿐이다(05 §4). NC(Paderborn KAt), 라이선스 표기 없음(CWRU·MAFAULDA·PHM 2022 rock drill 데이터·Hercik 공개분·Kaggle pump), AI 허브 데이터는 넣지 않는다. KAMP 원자료는 대회 요구로만 넣고 공개 저장소에 올리지 않는다(R2·R7). 다른 KAMP 데이터는 외부 데이터로 신고한다.
4. **경쟁팀 공개 저장소**: 열람·인용·복사하지 않는다. 이 문서에도 저장소 이름과 URL을 옮기지 않는다(원보고서 R2 2절·R7 2-G에만 있다). 우리 수치는 우리 코드로 다시 계산한다.
5. **벤더 통계**(C등급: 다운타임 비용, 절감률 등)는 근거로 쓰지 않는다. 비용은 파라미터와 민감도로만 낸다(R9).
6. **KAMP 인용 형식**(가이드북 1쪽·KAMP 페이지, R2·R7):
   - 국문: 중소벤처기업부, Korea AI Manufacturing Platform(KAMP), 소성가공 예지보전 AI 데이터셋, 스마트제조혁신추진단(㈜인터엑스), 2022.12.23., www.kamp-ai.kr
   - 영문: Ministry of SMEs and Startups., and KAIST(Korea Advanced Institute of Science and Technology). (2022, December 23). Plastic forming predictive maintenance AI dataset. Korea AI Manufacturing Platform(KAMP). https://www.kamp-ai.kr/
   - 연구·공식 사용 시 활용 내용을 kamp@kaist.ac.kr로 보내 달라는 **요청**이 있다. 의무 조항은 아니고, 이 주소가 지금도 운영되는지는 확인하지 못했다(R2·R7).
7. **수치 재확인**: 이 표의 수치·문구는 원보고서가 전한 값이다. 앞으로 보고서에 옮길 모든 수치는 원문으로 다시 확인한다. 확인 열이 메타·초록·search-only인 출처는 원문을 열기 전에는 내용(수치·문장)을 인용하지 않는다.
8. **검색 한도**: 조사 도중 세션 웹 검색 한도(200회)가 소진되었다. 그 뒤로는 Crossref·OpenAlex·Europe PMC·DataCite API와 알려진 URL을 직접 열어 확인했다. 그래서 일부 출처는 메타 수준에 머문다(R1–R9 공통). 남은 확인 항목은 5절에 모았다.

## 1. 주제별 핵심 결과 요약

### R1 — 도메인 물리(파인블랭킹 프레스·유압펌프·전동기)
- 버스트는 약 8초마다 찍은 약 50 ms 고속 스냅샷(약 1 kHz)일 가능성이 크다. 근거는 세 가지다.
  - 전류가 0.0600 주기/샘플 = 정확히 60.0 Hz
  - 진동 톤 ÷ 전류 주파수 비가 부하에 따라 줄어듦(유도전동기 슬립 0.12 → 0.63 %)
  - 1000 t 파인블랭킹 사이클 2.9–3.2 s(DP-01)
  - 계획은 이것을 가설(S1k)로 두고 모든 정의를 샘플 단위로 한다(01 §2-2).
- 스냅샷별 60 Hz 진폭은 펌프 부하 지표다(무부하 자화전류 첨두 약 121). I_T = √(A60² − I₀²)와 슬립 ŝ는 서로 독립인 부하 추정이다. 둘의 일관성 잔차가 "정상 운전 변화"와 "전기·계측 이상"을 가른다(03 §2.1, E2).
- 이상 파일 전류는 60 Hz 성분이 사라지고 직류 오프셋·계단이 있어 계측·수집 이상일 수 있다. 진동은 상·하부 역위상 약 100–110 Hz 링잉(흔들림 모드)으로 실제 기계 현상으로 보인다(01 §3–4, M5).
- 고장 모드 → 신호 표가 지표와 주입 계열의 바탕이다(03 §2.2–2.4, 04 §3.1 F1–F9).
  - 마모 → 체적효율 저하(부하 체류 약 +16 %)·압력맥동 증가
  - 흡입·공동현상 → 광대역 / 베어링 → 첨도 / 릴리프 밸브 채터 → 협대역 톤 / 헐거움 → 링잉
- 정상 변화의 크기(부하 전환 시 전류 약 2배·하부 진동 약 3배, 유온·전압 영향)와 정비 맥락(정지 최대 2–3일, FM 5-499 고장탐구표 → 점검 카드, 센서 추가 권고)을 준다(04 §3.2, 05 §5).

### R2 — 공개 데이터셋과 라이선스
- KAMP 사용조건은 "콘텐츠 변경허용" 하나뿐이고 약관에 재배포 조항이 없다. 그래서 대회 제출물 포함은 주최 요구로 보고, 공개 저장소 게시는 피한다. 출처 표기 양식도 확정했다(01 §1, 0.3절).
- 가이드북 PDF는 표지에 회원 ID·워터마크가 있고 그림 8장이 제3자 그림이다. 수치만 인용한다.
- 두 파일의 숫자 형식이 다르다(이상 전류 99.67 %가 1.19209 격자 위). 같은 수행기관의 「용접 예지보전」도 같은 normal/outlier 파일 체계다(01 §2-1, 04 N8·제약 2).
- 가이드북 LSTM-AE 수치는 같은 이상 사건의 앞부분으로 임계값을 정한 겹침 창 점수다. 사건 단위 성능이 아니다(01 §7).
- 외부 데이터는 ZeMA(CC BY 4.0, 크기 앵커), NLN-EMP(CC0, 스냅샷 수집 흉내), KAMP 「소성가공 자원최적화」(정상 변동 폭)로 좁힌다. AI 허브·Paderborn(NC)·라이선스 없는 데이터는 뺀다(03 §3.3 I).
- 경쟁팀 저장소가 형식 누수·0.6 Hz 앨리어싱·합성 주입을 이미 공개했다. 이것들은 우리 차별점이 아니다. 저장소는 라이선스가 없어 인용·복사하지 않는다(03 §0·§7).

### R3 — 이상탐지 방법과 평가 비판
- 한 줄 규칙(max|AI0| > 정상 최대)이 이상 21버스트 중 18개를 잡는다. Wu & Keogh가 말한 triviality다. 그래서 상수·무작위·한 줄 규칙·무작위 가중치 LSTM-AE 같은 사소한 기준선을 반드시 보고한다(03 §3.1).
- 금지: point-adjust F1, 시험 점수로 정한 임계값(Anomaly Transformer·TSLib·DCdetector 공식 코드에서 확인), 정확도 헤드라인(04 §4.3, 03 §6).
- 주 지표는 보류 정상의 FA/h(Poisson 정확 구간), 에피소드 탐지·첫 경보까지 시간, 버스트 재현율·FN 목록이다. 불확실성 하한도 숨기지 않는다(04 §4.1, §6.1, C12).
  - 에피소드 1/1의 CI [0.025, 1]
  - 정상 1.28 h에서 0건이어도 상한 2.34/h
  - 같은 길이 정상 블록 28개 대비 순위 검정의 최소 p = 0.034. 진동 통계와 지름길 통계가 둘 다 도달한다.
- 벤치마크 근거는 "단순 방법이 경쟁력 있다"이다(Schmidl, TSB-AD, Sarfraz, Goldstein & Uchida). 그래서 버스트 특징 + SPC·kNN을 중심에 두고, 트랜스포머·기초모델은 부록으로 둔다(03 §3.2–3.3).
- 부하 조건부 정상거동 모델이 가장 유력한 오경보 저감책이다(하부진동 잔차 SD 0.59 → 0.20). 단 공변량은 미리 정하고 외삽을 점검한다(03 §2.2 M1, §2.1 지지 범위).
- 확률은 정상 보정 conformal p로 정의하고 P(고장｜x)가 아님을 밝힌다. 라이선스 위험 목록(Moirai·TimesFM 3.0 가중치, alibi-detect, catch22, 옛 NAB 등)을 준다(03 §3.3 E, 05 §1).

### R4 — 경보관리·확률 보정·소표본 불확실성
- 주의 단계는 응답 의무가 없는 비가청 alert(정비 일일 보고)로 두고, 경고·위험만 경보로 둔다. 근거는 ISA-18.2·IEC 62682의 경보 정의, EEMUA 191 4판의 alert, Brazier 2025다(05 §5).
- 버스트 단위로 바꾸면 숫자가 냉혹하다. 교대당 오경보 1건이면 버스트당 α ≈ 2.7×10⁻⁴이고, conformal 보정 표본이 3,703개 이상 필요하다. 단일 버스트 판정으로는 교대 예산을 보장할 수 없다. 그래서 지속성·CUSUM·상태 기반 억제가 필수다(03 §4, 04 §6.1).
- 단측 CUSUM(k=0.5)을 교대 예산(ARL₀ ≈ 3,737 버스트)에 맞추면 h ≈ 6.37이고 1σ 이동 지연은 약 13버스트다(03 §3.2 B, 05 T2-1).
  - AR(1) ρ = 0.2만 있어도 ARL₀가 1/5이 된다. 그래서 정상 블록 부트스트랩으로 다시 맞춘다.
  - Western Electric 4규칙을 모두 켜면 ARL₀가 약 92로 줄어든다(자체 재현).
- 양측 점수는 저부하 구간에서 명목 5 % 대비 19.8 %의 오경보를 냈고, 단측은 0.8 %였다. 그래서 악화 방향 단측으로 판정한다(03 §2.5).
- conformal 보장은 버스트 단위·교환가능성·주변 보장이다(04 §4.1, §4.3, §6).
  - 고정 보정집합의 실제 FAR은 Beta(l, n+1−l)를 따른다(n = 236, α = 0.01이면 95 % 상한 약 2 %).
  - ACI는 고장 중에 임계를 올려 경보를 지울 수 있다.
- 확률은 (a) 정상 꼬리 p와 (b) 명시한 π의 사후확률로 나눈다(Platt 완전분리 문제, Venn–Abers 구간). 진술 단위표와 그림자 운전 필요 시간(교대 예산 ≥ 24 h, 주 예산 ≥ 503 h)을 준다(03 §4, 04 §6.2, 05 §5).

### R5 — 합성 고장 주입·증강·검출한계(POD)
- 실제 이상 1건은 쉬운 사례라 조기탐지의 증거가 되지 못한다. 증거는 정상 데이터에 물리 기반 고장을 크기별로 주입한 POD 곡선과 검출지연으로 만든다. 실제 이상은 마지막 1회 현실 시험으로 남긴다(04 §1 증거 위계).
- 순환성: 주입 결과는 설계한 계열에만 유효하다(Goswami, Yoo, NCAD, Lessmeier). 대응은 계열별 보고, leave-one-family-out, 격자 사전등록, 학습용·평가용 주입 분리다(04 §3, 03 §3.2 D).
- 증강은 물리적으로 중립인 것만 쓴다: 위상 무작위화, 버스트 블록 부트스트랩, 잘라내기(04 §2.3, 03 §6).
  - 진동 스케일링은 그 자체가 고장 주입이다.
  - 앨리어싱된 신호에 건 시간왜곡은 어떤 실제 속도 변화와도 대응하지 않는다.
  - 생성모델은 이상 1건을 복제하는 누설 경로라 쓰지 않는다.
- ZeMA로 계산한 앵커: 내부누설 약/심 → 모터전력 +0.45/+1.05 %, 냉각기 열화(오일 +8–21 °C) → 전력 −3 ~ −6 %, 진동 +9 ~ +28 %. 누설형은 전류·진동만으로 잡기 어렵고 온도는 강한 오경보 원인이다(04 §3.1 앵커, N4).
- MIL-HDBK-1823A 틀을 빌린다. hit/miss 회귀의 a50/a90(/95), "반복 검사로 POD 표본이 늘지 않는다", "이질 데이터를 평균한 POD는 어느 것도 대표하지 않는다"(04 §4.2–4.3).
- 센서 구성상 구별할 수 없는 쌍을 미리 선언한다: 마찰 토크 ↔ 부하·전원전압, 소폭 진동 증가 ↔ 유온(04 §3.4). 사전등록 주입 프로토콜 R5-INJ v1이 04 §3의 바탕이다.

### R6 — 신호처리와 진동·상태감시 표준
- 전류는 교류 순시값을 찍은 값이다. 단일 사인 R² ≥ 0.994이고 3·5·7차 고조파(4.5·2.2·1.8 %)가 남아 있다. 앤티앨리어싱 필터·블록평균·RMS 변환은 없었다(01 §2-2, §3).
- 진동 크기는 부하에 강하게 묶여 있다. 전류 진폭으로 설명되는 R²가 AI1 0.94, AI0 0.39다. 전류 진폭으로 조건화한 잔차가 가장 직접적인 오경보 저감 장치다(03 §2.2).
- 이상 파일은 격자·소수 자릿수·겉보기 주파수가 다르다. 스펙트럼·순서·양자화에 민감한 특징은 고장이 아니라 "수집 맥락"을 배울 위험이 크다(01 §2-1, 03 §2.5).
- 표준으로는 진동 등급(zone) 판정을 할 수 없다(03 §6, 05 §5).
  - ISO 20816 계열은 broad-band 속도 RMS·단위·정상 상태를 전제한다. 10816-7은 rotodynamic 펌프 전용이다.
  - 쓸 수 있는 것은 기준선 대비 변화(20816-1 Criterion II)와 ISO 17359 §8.4(고장 대 운전조건 변화)·§8.7(운전조건·단위 기록)이다.
- MCSA는 kHz 연속 기록이 필요해 이 데이터로 불가하다(잔차 바닥 약 −41 dB). R6은 10 Hz를 전제해 진동 접힌 선(1.8/3.6 Hz)의 원인을 미해결로 남겼다. 01 §2-2는 R1의 S1k 가설로 이 선을 회전 차수 톤으로 다시 읽는다(4.2절 1번).

### R7 — 한국·대회 특화 자료
- KAMP 메타데이터로 확정되는 사실: 파인블랭킹 프레스 공정, PLC·센서 실시간 수집, 정상 20,000행·이상 600행, 수행기관 ㈜인터엑스. 단위·펌프 형식·센서 사양은 어디에도 없다(01 §1).
- 2026 규정(03 §5, 04 §8, 05 §4):
  - 서면 지표 15/40/15/10/10/10
  - 제출물에 "테스트데이터 예측결과 파일". ③에는 공식 시험 분할이 없어 분할 정의를 문서화한다.
  - 외부데이터 조항은 9-22 수정분이라 웹 본문에만 있다.
- 이 데이터셋은 이번에 처음 출제되었다. 이 데이터를 쓴 KCI 논문은 찾지 못했다(검색이 불완전). "국내 최초" 같은 주장은 하지 않는다.
- KS 현황: KS B ISO 17359·13379-1/-2·13381-1·13374-1·20816-1·20816-3(2026-07-28 제정)이 있다. 10816-7은 회전동역학 펌프용이고, KS B ISO 10816-1은 폐지되었다. 경보관리(IEC 62682)의 KS 부합판은 찾지 못했다.
- 안전보건규칙 제35조·별표 3의 프레스 작업시작 전 점검에는 유압펌프 상태 항목이 없다. 그래서 AI 경보는 법정 점검·방호장치를 대체하지 않는 정비 의사결정 보조로 둔다(05 §5).
- 국내 현장 자료(05 §5, 03 §6):
  - KAMP 우수사례: 전류로 정지 구간을 가려 정상 운전 구간을 나눈 뒤 판정
  - INTERX 유압식프레스 표준 가이드: AAS 속성명 → 센서 로드맵·출력 필드
  - SMOTE류 과표집의 반례 맥락(김지연 외 2024)

### R8 — 설명가능성·오류 분석·교란
- 라벨·파일·날짜·시간대가 하나로 묶인 완전 교란이다(positivity 위반). 고장 효과와 그날 조건 효과를 통계로 가를 수 없다. 그래서 이 사실을 먼저 밝히고, 반증 시험을 묶어 보이고, 주장 범위를 좁힌다(01 §6, 04 §7).
- 분리가 된다는 것 자체는 증거가 아니다. 같은 날 정상끼리도 운전 상태가 바뀌면 분류기 AUC가 0.98–0.99다(01 §6, 04 C2).
- 고장 쪽의 가장 강한 증거(01 §4–4-1):
  - 부하 매칭 상부진동: 전류 ±15 % 매칭에서 17개 중 13개가 정상 최댓값 초과, 중앙 약 3.8배
  - 진동 시간 구조 변화: 샘플 시각 지터가 만드는 방향(백색화)과 반대
- 전류 동역학 특징(lag-1, 스펙트럼 모양, 원시 전류를 복원하는 LSTM-AE)은 샘플 시각 지터 2–3 ms로 재현된다. 그래서 "계측 민감" 군으로 따로 두고 전류 진폭만 상태 변수로 쓴다(01 §3, 03 §2.3, 04 C8).
- 설명 도구는 TreeSHAP·RBC·ALE·귀무분포를 붙인 H·특징군 재학습·Ojala–Garriga Test 2다. 1차 용도는 Clever Hans 감사다(03 §3.4, 04 C14).
- 보고 틀은 REFORMS·누수 8유형·주장 장부다. 가이드북 절차는 L3.2(비독립)에 해당하고 경계 창 겹침은 L1.4와 비슷하다(01 §7, 04 §7).

### R9 — 현장 관행·타 분야 교훈·아이디어
- ISO 17359 §8.4는 과제의 오경보 정의와 같은 말을 한다("고장인가, duty·운전조건 변화인가"). 해법은 운전조건 조건부 기준선이다. 직접 선례는 급수펌프 경보를 펌프 전류에 비례하는 동적 trip point로 바꾼 사례(Wang 2016)다(03 §1–2, §3.2 A).
- 오경보 상당수는 계측 문제다(임상 기술 경보 31 %). 그래서 센서 검증(SQI) 층을 앞에 두고, "계측 점검"을 억제하지 않고 별도로 알린다(03 §1 L0, 04 F8).
- 지속성·지연은 값싼 저감책이지만 지연 비용이 있다(ICU에서 19 s 지연으로 무시·무효 경보 67 % 감소 추정). run rule은 오경보를 늘린다(03 §3.2 B, §4).
- 표시 원칙(05 §5, 03 §3.4):
  - 가능도 경보 + 원자료 교차확인
  - 설명보다 확신도 우선(설명만 붙이면 정답 여부와 관계없이 수용만 늘었다)
  - 자연빈도 문장
- 경보 예산과 확률 산술(03 §4, 05 §5):
  - 교대당 약 3,734버스트. 정상 599버스트에서 FP 0건이어도 교대당 최대 약 19회가 가능하다.
  - 기저율 10⁻⁴이면 모델 확률 0.99가 약 0.22가 된다 → 기저율 시나리오 확률, p* = C_I/(C_U − C_P).
- 도입과 경제성(05 §5, 03 §3.3 J):
  - 그림자 운영 → 예산 확인 → 단계적 가동, 처리 코드 (a)–(e), as-found 기록
  - 경제성 수치는 단서와 함께 쓴다(NIST 설문 n=71, 저자가 "anecdotal"이라 명시). 벤더 통계는 쓰지 않는다.
  - 아이디어 40개 중 I-02·I-05·I-09·I-18·I-24–I-26·I-29–I-31·I-33·I-34 계열이 계획에 들어갔다(대응은 이 문서의 판단).

## 2. 핵심 출처표

- 행 130개(총괄 계획자 확인 4건 포함). 계획 문서가 기대는 출처와 심사위원이 기대할 출처만 골랐다. 나머지는 원보고서 출처표를 본다.
- 열: 번호 | 출처(저자, 제목, 매체, 연도, DOI·URL) | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID.
- "※정정 4.1-n"은 원보고서가 서지를 바로잡은 항목이다(4절).

### 2.1 대회·KAMP·데이터 이용조건

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| KM-01 | 중소벤처기업부·KAMP, 「소성가공 예지보전 AI 데이터셋」 상세 페이지(DATASET_SEQ=48). 제공 스마트제조혁신추진단(수행 ㈜인터엑스), 등록 2022-12-23, 최종 수정 2025-04-02. https://www.kamp-ai.kr/aidataDetail?DATASET_SEQ=48 | A | opened (2026-10-01 HTML 직접 수신)〔R7〕 / opened (2026-10-01)〔R2〕 | 사용조건 "콘텐츠 변경허용"(정의 문서 없음). 출처 표기와 kamp@kaist.ac.kr 송부 **요청**. 재배포·상업 조항 없음. 센서 표기 "모터의 상하부 진동"이 가이드북("유압펌프 상/하단")과 다름. 위험 낮음(출처 표기 필수) | 01 §1, 04 §8(`DATA_SOURCES.md`), 05 §1 | R2-S01, R7-S1 |
| KM-02 | 스마트제조혁신추진단·㈜인터엑스/KAMP, 「소성가공 예지보전 AI 데이터셋 분석실습 가이드북」(65쪽, 문서번호 워터마크, 로컬 PDF) | A(R1: 데이터 출처 1차 문서) / A/B(R8) / B(R2·R5) | opened-전문(로컬)〔R8〕 / opened(로컬 PDF, 5–9쪽·42쪽)〔R1〕 / opened〔R2〕 / [열람] 로컬 텍스트〔R5〕. 7쪽 정지 문구는 원문 확인(Claude, 2026-10-01) | 표지에 다운로더 KAMP 회원 ID·다운로드 일시·문서 고유번호 → PDF·표지 캡처를 어디에도 넣지 않음. 그림 1·2·5·6·7·8·9·11은 제3자 그림(재사용 금지). 그림 3 센서 사진은 출처 표기·최소 사용. 수치·문구 인용만. 위험 높음(PDF·그림 재사용 시) | 01 §1·§7, 03 §3.1 B0, 05 §5(C_U 정성 근거) | R1-S1, R2-S02, R5-S32, R8-G4 |
| KM-03 | KAMP 이용약관. https://www.kamp-ai.kr/agreement | A | opened〔R2·R7〕 | 데이터 저작권·재배포·2차 저작물 조항 없음(제3조 개별 서비스 별도 약관, 제10조 면책). 운영 주체 표기("한국과학기술원")가 현재 하단 운영기관(TIPA·NHN·이노비즈)과 달라 해석이 불확실 | 01 §1 | R2-S03, R7-S2 |
| KM-04 | 중소기업기술정보진흥원, 「제조AI 데이터셋 50종_20241231」 목록 CSV(공공데이터포털). https://www.data.go.kr/data/15089213/fileData.do | A | opened, CSV 내려받음〔R2〕 / opened (CSV 내려받아 확인)〔R7〕 | 50종 모두 "콘텐츠 변경허용". "이용허락범위 제한 없음"은 **목록 파일**의 조건 → 데이터 본체 라이선스 근거로 쓰면 과장 | 01 §1(보조) | R2-S05, R7-S3 |
| KM-05 | (사)중소기업기술혁신협회(이노비즈협회), 「2026년 제6회 K-인공지능(AI) 제조데이터 분석 경진대회」 공고 — KAMP 공지 85(2026-08-18)·공고문 hwp. 대회 페이지 https://www.kamp-ai.kr/contestDetail?CPT_SEQ=38 | A | opened〔R7〕 / opened (페이지). HWP·과제안내 미열람〔R2〕 | "KAMP 내 등재된 제조AI데이터셋(총 50종) 중 1종 또는 여러 종 활용하여 문제 출제 예정"은 출제 범위이지 참가자의 다른 KAMP 데이터 사용 허가가 아님(R2). 위험 낮음 | 03 §3.3 I(다른 KAMP 데이터 = 외부 데이터), 05 §4 | R7-S5, R2-S04 |
| KM-06 | 같은 협회, 「2026년 제6회 … 과제공개(일반국민/대학(원)생)」 KAMP 공지 86(2026-09-21, 9-22 수정)과 첨부 hwpx. https://www.kamp-ai.kr/noticeDetail?NOTICE_SEQ=86 | A | opened (웹 본문과 로컬 hwpx 모두)〔R7〕 | 서면 지표 15/40/15/10/10/10, 제출 구성(소스·requirements·학습 데이터·README·테스트데이터 예측결과 파일), 블라인드. 외부데이터 조항(사유·방법·출처 명시, 공개에 문제없는 데이터만)은 9-22 수정분이라 **웹 본문에만** 있음 | 03 §5, 04 §8, 05 §4 | R7-S4 |

### 2.2 도메인 물리(파인블랭킹·유압펌프·전동기)

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| DP-01 | Hua L., Xu Z., Liu Y., Zhao X. (2021) "Research On Energy Saving and Performance Enhancement of High-End Hydraulic Press With Controllable Accumulator", Research Square preprint, DOI 10.21203/rs.3.rs-155423/v1 | B | opened(PDF 본문, Table 1)〔R1〕 | CC BY 4.0(Europe PMC·Crossref 표기). 심사 전 판본이고 어큐뮬레이터를 개조한 **다른 연구용 프레스**다 → [v2] 이 설비의 사이클 근거로 쓰지 않고 공정 맥락으로만 인용 | 01 §2-2(맥락), 03 §2.1(언로딩·어큐뮬레이터) | R1-S5 |
| DP-02 | Xu Z., Hua L., Liu Y. (2024) "Energy saving and performance enhancement of hydraulic fineblanking press assisted with controllable hydraulic accumulator for sustainability", Int J Adv Manuf Technol 131:1119–1136, DOI 10.1007/s00170-024-13082-0 | A | meta(Crossref 초록 요약: 1000 t 검증, 효율 +20.35 %, 169.4 kJ 절감)〔R1〕 | 유료. 그림 재사용 불가 | 01 §2-2(DP-01의 심사본) | R1-S6 |
| DP-03 | Xu Z., Liu Y., Hua L., Zhao X., Guo W. (2019) "Energy analysis and optimization of main hydraulic system in 10,000 kN fine blanking press with simulation and experimental methods", Energy Conversion and Management 181:143–158, DOI 10.1016/j.enconman.2018.12.012 | A | meta(Semantic Scholar 초록 전문, Crossref 서지)〔R1〕 | 유료(Elsevier). 본문 수치 미확인 → 초록 범위만 | 03 §2.1(펌프 전류는 제품 하중보다 공급압·언로딩 상태를 반영) | R1-S7 |
| DP-04 | Guo R., Li Y., Shi Y., Li H., Zhao J., Gao D. (2020) "Research on Identification Method of Wear Degradation of External Gear Pump Based on Flow Field Analysis", Sensors 20(14):4058, DOI 10.3390/s20144058 | A | opened(PMC)〔R1〕 | CC BY 4.0. MDPI(품질 편차 논쟁), 소형 펌프(4 mL/r) | 03 §2.2 M6·§2.4 S1, 04 §3.1 F4·F7 | R1-S12 |
| DP-05 | Liao J., Zheng J., Chen Z. (2022) "Research on the Fault Diagnosis Method of an Internal Gear Pump Based on a Convolutional Auto-Encoder and PSO-LSSVM", Sensors 22(24):9841, DOI 10.3390/s22249841 | A | opened(PMC)〔R1〕 | CC BY 4.0. 20 mL/r 소형 | 03 §2.4 S1(고장 기준 η_v < 82.5 %), 04 §3.1 F7 | R1-S13 |
| DP-06 | Edge K.A. (1999) "Designing quieter hydraulic systems — some recent developments and contributions", Proc. 4th JFPS Int. Symp. on Fluid Power, DOI 10.5739/isfp.1999.3 | A | opened(J-STAGE PDF)〔R1〕 | 본문 인용 가능. 그림 재사용은 허락 필요 | 03 §2.2 M3·M6(펌핑 주파수 고조파, 공동현상 광대역), 04 §3.1 F1·F4 | R1-S16 |
| DP-07 | U.S. Army (1997, Change 1 2001) FM 5-499 Hydraulics | A(기초 지침) | opened(globalsecurity PDF)〔R1〕 | 미국 정부 교범(배포 제한 표기는 확인 필요). 오래됐지만 원리 수준은 유효 | 05 §5 점검 카드(Table 6-1 고장탐구표), 04 §3.1 F3(릴리프 밸브 채터) | R1-S30 |
| DP-08 | U.S. DOE Motor Challenge, "Determining Electric Motor Load and Efficiency", Fact sheet DOE/GO-10097-517 (c. 1997). https://www.energy.gov/sites/prod/files/2014/04/f15/10097517.pdf | A | opened〔R1〕 / [열람] PDF 본문〔R5〕 | 미국 정부 저작물(공공영역 추정 — R1, 공공 이용 가능·미확정 — R5) | 03 §2.1 I_T·ŝ·§2.3 E2(전류는 저부하에서 비선형, 슬립은 부하 비례), 01 §2-2 | R1-S28, R5-S49 |
| DP-09 | McCoy G.A., Douglass J.G. (2014) Premium Efficiency Motor Selection and Application Guide, U.S. DOE AMO (OSTI 1220835) | A | opened〔R1〕 | 미국 정부 저작물 | 03 §2.4 S2(전압 → 자화전류), 04 §3.2 N3, 05 §5(3상 측정) | R1-S29 |
| DP-10 | Thomson W.T., Fenger M. (2001) "Current signature analysis to detect induction motor faults", IEEE Industry Applications Magazine 7(4):26–34, DOI 10.1109/2943.930988 | A | Crossref + 초록 opened, 본문 미열람〔R6〕 / [열람] 초록〔R5〕 / meta(초록)〔R1〕 | IEEE 유료. 측대역 dB 판정표 등 본문 수치는 인용 금지(R6) | 01 §2-2(이 수집 방식으로는 MCSA 불가), 03 §2.3 | R6-P2, R1-S18, R5-S48 |
| DP-11 | Blödt M., Granjon P., Raison B., Rostaing G. (2008) "Models for bearing damage detection in induction motors using stator current monitoring", IEEE TIE 55(4):1813–1822, DOI 10.1109/TIE.2008.917108 | A | [열람] 초록(OpenAlex). HAL 전문은 봇 차단〔R5〕 / meta(초록 전문)〔R1〕 / Crossref + 초록〔R6〕 | IEEE(그린 OA hal-00270747) | 04 §3.1 F5(부하토크 변동 → 고정자 전류 변조) | R5-S46, R1-S21, R6-P5 |

### 2.3 공개 데이터셋(쓸 것 / 앵커로만 / 쓰지 않을 것)

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| DS-01 | **[앵커로만(Tier 2), 일반화 시연은 Tier 3]** Helwig N., Pignanelli E., Schütze A., Condition monitoring of hydraulic systems [Dataset], UCI ML Repository, DOI 10.24432/C5CW21. Zenodo판 Schneider T., Klein S., Bastuck M. (2018) Condition monitoring of hydraulic systems Data Set at ZeMA, DOI 10.5281/zenodo.1323611 | B(R2·R9) / A(R5) | [열람] UCI·Zenodo 페이지·documentation.txt. 데이터를 내려받아 우리 계산〔R5〕 / 열람-전문 (UCI 페이지)〔R9〕 / opened (UCI 페이지, DataCite)〔R2〕 | CC BY 4.0 — 저작자 표시·변경사항(다운샘플·부분집합) 명시 시 재배포 가능, 외부 데이터 고지 필요. 실험실 리그, EPS1은 전류가 아니라 전력(100 Hz), VS1은 1 Hz 속도값, 고장은 오리피스 모사 → 비율만 차용. UCI판과 Zenodo판 파일 대조는 안 함(R2) | 03 §3.3 I, 04 §1(L3)·§3.1(크기 앵커)·§3.2 N4, 05 T2-7 | R5-S45, R2-S14, R2-S17, R9-S21, R1-S27, R6-P26 |
| DS-02 | Helwig N., Pignanelli E., Schütze A. (2015) "Condition monitoring of a complex hydraulic system using multivariate statistics", IEEE I2MTC 2015 Proc., pp. 210–215, DOI 10.1109/I2MTC.2015.7151267 | A / A−(R3) | 열람-초록〔R9〕 / Crossref 메타데이터만 opened. 본문 미열람〔R2〕 / opened-메타〔R3〕 / [검색만]〔R5〕 | IEEE. 그림 재사용은 허가 필요 | DS-01의 원 논문(데이터 인용 시 병기) | R9-S19, R2-S15, R3-M29, R5-S42, R6-P26, R1-S27 |
| DS-03 | Helwig N., Pignanelli E., Schütze A. (2015) "D8.1 Detecting and compensating sensor faults in a hydraulic condition monitoring system", Proc. SENSOR 2015, pp. 641–646, DOI 10.5162/sensor2015/D8.1 | A(R2) / A-(R5) / B(R9) | [열람] AMA PDF(폰트 인코딩을 복원해 판독)〔R5〕 / 열람-초록 (AMA 페이지)〔R9〕 / Crossref 메타데이터만〔R2〕 | AMA 공개(R5). 세부 수치는 R9 미확인 | 04 §3.1(누설 = 오리피스, 정격유량 3.3·4.6 % 앵커)·F8·§3.3, 03 §1 L0 | R5-S43, R9-S20, R2-S16 |
| DS-04 | **[쓸 것, Tier 3]** Bruinsma S., Geertsma R., Loendersloot R., Tinga T. (2024) "Motor current and vibration monitoring dataset for various faults in an E-motor-driven centrifugal pump", Data in Brief 52:109987, DOI 10.1016/j.dib.2023.109987. 데이터 NLN-EMP: 4TU.ResearchData DOI 10.4121/2b61183e-c14f-4131-829b-cc4822c369d0.v4 | A | opened (4TU, DataCite, Europe PMC 본문)〔R2〕 | 데이터 CC0 1.0, 논문 CC BY. 원심펌프·인버터 구동(도메인 차이), 7z 약 20.8 GB → 부분집합만 | 03 §3.3 I, 05 §4 | R2-S30 |
| DS-05 | **[쓸 것, Tier 3]** KAMP 「소성가공 자원최적화 AI 데이터셋」(KAIST, 수행 UNIST/㈜리쉐니에, 2022-12-23) 가이드북(로컬 PDF) | B | opened (표지·데이터 쪽)〔R2〕 | KAMP "콘텐츠 변경허용". 과제 지정 데이터가 아니므로 외부 데이터로 신고. 전류 RMS 저속(간격 약 1분 추정, 미확인), 진동·고장 라벨 없음 | 03 §3.3 I, 05 §4 | R2-S07(D13) |
| DS-06 | **[비교만]** KAMP 「용접 예지보전 AI 데이터셋」(스마트제조혁신추진단, 수행 ㈜인터엑스, 2022-12-23) 가이드북·압축 목록 | B | opened (표지·데이터 쪽)〔R2〕 | KAMP 조건, 외부 데이터 — 형식 비교 참고용. R2는 압축을 풀지 않았고, 파일 형식은 01 §2-1에서 총괄 계획자가 `pilot_weld_format.py`로 직접 확인 | 01 §2-1, 03 §7-8 | R2-S07(D15) |
| DS-07 | **[쓰지 않음]** 한국지능정보사회진흥원 AI 허브 「데이터 이용정책」(https://aihub.or.kr/intrcn/guid/usagepolicy.do), 「기계시설물 고장 예지 센서」(dataSetSn=238)·239·71802 | A | opened〔R2〕 | 학습용 한정, 승인 없는 제3자 열람·제공 금지, 국외 반출 별도 합의, "내국인만 데이터 신청" → 제출물 포함·재현 요건과 충돌 | 03 §3.3 I | R2-S39, R2-S40, R2-S41 |
| DS-08 | **[쓰지 않음]** Paderborn Univ. KAt-DataCenter 베어링 데이터(모터 전류·진동 64 kHz) | A(논문)·데이터 | opened (KAt 페이지, 논문 PDF)〔R2〕 | 데이터 CC BY-NC 4.0("Commercial use requires contacting the authors") → 상금 있는 대회의 NC 해석 위험. 넣지 않음. 논문 인용은 SY-06 | 03 §3.3 I | R2-S32 |

### 2.4 이상탐지 방법·평가 비판·기준선

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| AD-01 | Wu R., Keogh E.J. "Current Time Series Anomaly Detection Benchmarks are Flawed and are Creating the Illusion of Progress." IEEE TKDE 35, 2421–2429 (2023; early access 2021). DOI 10.1109/TKDE.2021.3112126. 확장초록 ICDE 2022 pp. 1479–1480, arXiv 2009.13807(서지 차이는 4.2-12) | A | opened-전문(arXiv v5). 서지는 Crossref, 권·쪽은 Semantic Scholar. 호(issue)는 미확인〔R3〕 | IEEE 저작권, arXiv판에 재사용 라이선스 없음 → 요지·짧은 인용, 그림 금지. 저자가 대안 아카이브를 만든 경미한 이해관계 | 01 §0-9·§6, 03 §3.1 B-one, 04 §4.2(대회 지표 머리 주석) | R3-E1, R4-S98, R5-S12, R8-E1, R9-S84 |
| AD-02 | Kim S., Choi K., Choi H.-S., Lee B., Yoon S. "Towards a Rigorous Evaluation of Time-Series Anomaly Detection." AAAI 36(7):7194–7201 (2022). DOI 10.1609/aaai.v36i7.20680. arXiv 2109.05257 | A | opened-전문(AAAI 페이지, arXiv PDF Table 2)〔R3〕 | AAAI 저작권. 수치 인용 가능 | 03 §3.1 B-rand·B0-rnd, 04 §4.3(point-adjust 금지) | R3-E2, R4-S96, R5-S13, R8-E2, R9-S83 |
| AD-03 | Schmidl S., Wenig P., Papenbrock T. "Anomaly Detection in Time Series: A Comprehensive Evaluation." PVLDB 15(9):1779–1797 (2022). DOI 10.14778/3538598.3538602 | A | opened-전문(RI 1–14)〔R3〕 / [열람] PDF〔R5〕 | 논문 CC BY-NC-ND 4.0 → 그림 변형·상업 이용 불가. 인용·재서술만 | 03 §3.3 E("단순 방법이 자주 이긴다") | R3-E5, R5-S2 |
| AD-04 | Liu Q., Paparrizos J. "The Elephant in the Room: Towards A Reliable Time-Series Anomaly Detection Benchmark." NeurIPS 2024 Datasets & Benchmarks Track. https://proceedings.neurips.cc/paper_files/paper/2024/hash/c3f3c690b7a99fba16d0efd35cb83b2c-Abstract-Datasets_and_Benchmarks_Track.html | A | opened-전문(proceedings PDF와 NeurIPS 발표 슬라이드)〔R3〕 | 코드 Apache-2.0. 데이터는 원 출처 라이선스(재배포 금지). VUS 제안 그룹이라 자기 지표를 권장하는 구조 | 03 §3.3 E | R3-E6 |
| AD-05 | Sarfraz M.S., Chen M.-Y., Layer L., Peng K., Koulakis M. "Position: Quo Vadis, Unsupervised Time Series Anomaly Detection?" ICML 2024, PMLR 235:43461–43476. arXiv 2405.02678 | A(position paper) | opened-전문(PMLR 페이지, arXiv PDF Table 2)〔R3〕 | "Copyright 2024 by the author(s)". 수치 인용 가능. 기업 소속 입장 논문 | 03 §3.1 B-pca | R3-E7 |
| AD-06 | Goldstein M., Uchida S. "A Comparative Evaluation of Unsupervised Anomaly Detection Algorithms for Multivariate Data." PLOS ONE 11(4):e0152173 (2016). DOI 10.1371/journal.pone.0152173 | A | opened-전문〔R3〕 | CC BY(PDF 표기 확인) → 그림도 출처 표기 시 재사용 가능. 표 형식 데이터 기준 | 03 §3.1 B-1nn, §3.2 C(kNN) | R3-M11 |
| AD-07 | Snyder D.E., Echauz J., Grimes D.B., Litt B. (2008) "The statistics of a practical seizure warning system", J. Neural Eng. 5(4):392–401 (PMC2888045) | A | opened(초록): 우연 예측기 대비, 경보 시간 비율 제약 하의 민감도 차 지표 확인〔R4〕 | ⓒIOP(PMC 공개본). 개념만 차용. 저자 소속 기업(이해상충 가능) | 04 §4.1(우연 예측기 대비) | R4-S100 |
| AD-08 | Jackson J.E., Mudholkar G.S. "Control Procedures for Residuals Associated With Principal Component Analysis." Technometrics 21(3):341–349 (1979). DOI 10.1080/00401706.1979.10489779 | A | opened-메타〔R3〕 | 유료. Q(SPE) 한계식은 수식만 인용 | 03 §3.1 B-pca, §3.2 B(SPE) | R3-M1 |
| AD-09 | Rousseeuw P.J., Van Driessen K. "A Fast Algorithm for the Minimum Covariance Determinant Estimator." Technometrics 41(3):212–223 (1999). DOI 10.1080/00401706.1999.10485670 | A | opened-메타〔R3〕 | sklearn `MinCovDet` | 01 §8(파일럿 MCD), 03 §3.2 B 약점 | R3-M4 |
| AD-10 | Liu F.T., Ting K.M., Zhou Z.-H. "Isolation Forest." ICDM 2008, pp. 413–422. DOI 10.1109/ICDM.2008.17 | A | opened-메타〔R3〕 / 검색만〔R9〕 | sklearn | 01 §8, 03 §3.2 C | R3-M9, R9-S34 |
| AD-11 | Xu J., Wu H., Wang J., Long M. "Anomaly Transformer: Time Series Anomaly Detection with Association Discrepancy." ICLR 2022. arXiv 2110.02642 | A | opened-전문 + 코드 opened(solver.py, data_loader.py, issue #14)〔R3〕 | 코드 MIT. 공식 코드가 train+test 점수 분위수로 임계값을 정하고 PA를 적용, 일부 로더는 val = test → 공식 수치를 그대로 비교하면 안 됨. TimesNet/TSLib(R3-M21)·DCdetector(R3-M22) 코드도 같은 관행 | 03 §6 | R3-M20 |
| AD-12 | Bergmeir C., Benítez J.M. "On the use of cross-validation for time series predictor evaluation." Information Sciences 191:192–213 (2012). DOI 10.1016/j.ins.2011.12.028 | A | opened-메타〔R3〕 | 인용만 | 04 §2.1 B(블록 교차검증) | R3-V1 |

### 2.5 경보관리·SPC·순차검정

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| AL-01 | ANSI/ISA-18.2-2016, Management of Alarm Systems for the Process Industries. ISA, 승인 2016-03-17, ISBN 978-1-941546-86-4(목차 발췌는 위원 개인 사이트 사본) ※정정 4.1-11 | A | opened(목차): §9.5, §10.5, §11.7–11.9, §12.4–12.5, §16.4, §16.8, 표5–7 확인〔R4〕 / 열람-초록 (ISA 페이지만, 본문 미열람)〔R9〕 | ⓒISA 유료, 전재 금지 → 조항·표 번호와 개별 수치만. 목차 발췌본은 제3자 호스팅이라 원 출처로 인용 | 03 §4(ISA-18.2식 경보 정의표), 05 §5(rationalization 형식, §11.9 설계 억제 범주) | R4-S01, R9-S37 |
| AL-02 | IEC 62682:2022 Ed.2.0 (2022-12), Management of alarm systems for the process industries(VDE 미리보기) ※정정 4.1-10 | A | opened(목차): §16.3.3–16.3.10, 표5–7, 3.1.4 adaptive alarm, 1판(2014) 대체 확인〔R4〕 / 미검증〔R9〕 | ⓒIEC 유료 → 조항 번호만. KS 부합판은 e-나라표준인증 검색 0건(R4-S15, 2026-10-01) | 03 §4·05 §5(경보 체계; 상태 의존 임계의 공식 용어 후보 "3.1.4 adaptive alarm") | R4-S02, R4-S15, R9-S38 |
| AL-03 | EEMUA Publication 191 Ed.4, Alarm systems – a guide to design, management and procurement, 2024-11, ISBN 978 0 85931 243 1(EEMUA 공식 목차 PDF) | B | opened(목차): §2.3.1 Alerts, §2.6, §6.4.5 Deadband, §7.4.4–7.4.8, 표9–11·15–19·27, 부록3 확인〔R4〕 / 간접 확인 (S35, S40 인용)〔R9〕 | ⓒEEMUA 유료. 표 값 미확인(3판과 다를 수 있음) → 표 번호만 | 05 §5(주의 = 비가청 alert) | R4-S05, R9-S39 |
| AL-04 | Brazier A. (2025) "Alarm management – update to EEMUA 191", IChemE Symposium Series No.172 (Hazards 35) | B | opened(본문): alert·prompt 구분, "정비팀 일일 보고용 alert", 우선순위가 낮아도 무시하면 안 된다는 원칙 확인〔R4〕 | ⓒIChemE, 그림 ⓒEEMUA → 문장 인용만. EEMUA를 대표한 저자(이해관계) | 05 §5(주의 단계 = 정비 일일 보고) | R4-S06 |
| AL-05 | IChemE Safety Centre (2021-11) Lead Process Safety Metrics – Alarm Rationalisation (guidance) | B | opened(본문): IEC/ISA/EEMUA 지표 표(… 3단계 약 80/15/5) 확인〔R4〕 | ⓒIChemE. 표준 수치의 2차 재현 → "2차 출처" 명시 | 05 §5(우선순위 분포 약 80/15/5), 04 §4.2(chattering·fleeting KPI) | R4-S08 |
| AL-06 | NAMUR NE 107, Self-monitoring and diagnosis of field devices (2006, 개정 2017-04-10, 개정 2025-07-15)(namur.net 공지) | B | opened(공지): 상태신호 F·C·S·M과 2017·2025 개정 확인〔R4〕 | ⓒNAMUR 유료. 본문 미확인 → 상태신호 이름만 | 05 §5(F/C/S/M 대응) | R4-S11 |
| AL-07 | 14 CFR §25.1322 Flightcrew alerting (Amdt. 25-131, 75 FR 67209, 2010-11-02), eCFR | A | 열람-전문〔R9〕 | 공공영역 | 03 §1 L0(억제할 때는 억제 사실을 표시 → 계측 점검을 숨기지 않음), 03 §4(Warning/Caution/Advisory 위계) | R9-S44 |
| AL-08 | Wang J., Yang F., Chen T., Shah S.L. (2016) "An overview of industrial alarm systems: main causes for alarm overloading, research status, and open problems", IEEE T-ASE 13(2):1045–1061, doi:10.1109/TASE.2015.2464234 | A | opened(본문, 저자 사본)〔R4〕 / 열람-전문 (저자 사본)〔R9〕 | ⓒIEEE. 그림 재사용은 허가 필요 | 03 §1–2(급수펌프 전류 비례 동적 trip point = 운전 상태 조건부 기준선의 선례), 04 §4.2(chattering) | R4-S16, R9-S40 |
| AL-09 | Xu J., Wang J., Izadi I., Chen T. (2012) "Performance assessment and design for univariate alarm systems based on FAR, MAR, and AAD", IEEE T-ASE 9(2):296–307, doi:10.1109/TASE.2011.2176490 | A | 열람-초록〔R9〕 / opened(메타)〔R4〕 | ⓒIEEE. 정확한 수식은 원문 확인 후 사용 | 03 §4(지속성), §7-6(FAR–MAR–AAD 교환) | R9-S41, R4-S18 |
| AL-10 | Page E.S. "Continuous Inspection Schemes." Biometrika 41(1–2):100–115 (1954). DOI 10.1093/biomet/41.1-2.100 | A | opened(메타)〔R4〕 / opened-메타〔R3〕 / [검색만] Crossref〔R5〕 / 검색만〔R9〕 | ⓒOUP. 인용만 | 03 §1 L5·§3.2 B(CUSUM), 05 T2-1 | R4-S27, R3-M6, R5-S56, R9-S99 |
| AL-11 | NIST/SEMATECH e-Handbook of Statistical Methods §6.3.2.3 CUSUM(ARL 표), §6.3.2.4 EWMA ※정정 4.1-13 | A | opened(본문): 단측 CUSUM k=0.5에서 h=4 ARL0 336, h=5 ARL0 930, 1σ에서 8.38·10.4, Shewhart 371, EWMA λ 0.2–0.3 확인〔R4〕 | 미국 정부 저작물(공개). 인용·재사용 위험 낮음 | 03 §3.2 B(ARL₀ = 경보 예산 설계), 03 §2.4 S3(EWMA), 05 T2-1 | R4-S26 |
| AL-12 | Champ C.W., Woodall W.H. (1987) "Exact results for Shewhart control charts with supplementary runs rules", Technometrics 29(4):393–399, doi:10.1080/00401706.1987.10488266(+ CRAN `spc` 문서 xshewhartrunsrules.arl) | A | opened(메타). ARL0 약 92는 자체 몬테카를로로 재현(92.3±0.3)〔R4〕 / 검색만 + 문서 열람〔R9〕 | ⓒASA/T&F. 정확값 91.75는 원문 미확인. 03 §3.2 B의 "370 → 166"은 4-of-5 규칙 하나만 더한 값(4.2-2) | 03 §3.2 B(run rule을 쓰지 않는 근거) | R4-S30, R9-S96 |
| AL-13 | Montgomery D.C., Mastrangelo C.M. (1991) "Some statistical process control methods for autocorrelated data", J. Quality Technology 23(3):179–193, doi:10.1080/00224065.1991.11979321 | A | opened(메타)〔R4〕 | ⓒASQ/T&F. 인용만. 같은 취지로 Alwan & Roberts 1988(R4-S31, opened(메타)) | 05 T2-1(자기상관에서 이론 ARL이 무너짐 → 블록 부트스트랩으로 재보정) | R4-S32 |

### 2.6 conformal·확률 보정·소표본 통계·의사결정

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| ST-01 | Bates S., Candès E., Lei L., Romano Y., Sesia M. (2023) "Testing for outliers with conformal p-values", Ann. Stat. 51(1):149–178, DOI 10.1214/22-AOS2244(arXiv 2104.08279) | A | opened(초록): 주변 유효성, 시험점 간 의존, 보정조건부 유효 p값, PRDS와 BH FDR 확인〔R4〕 / opened-전문(초록)〔R3〕 / opened-초록〔R8〕 / [열람] 초록〔R5〕 / 열람-초록 (arXiv)〔R9〕 | arXiv판 CC BY 4.0(R4) → arXiv판 그림은 출처 표기 후 재사용 가능. 교환가능성 가정 → 시계열에서는 블록 단위로 해석(R8) | 03 §1 L4·§3.2 A·§4, 04 §4.2(p값 타당성)·§6.2 | R4-S38, R3-V14, R5-S58, R8-E11, R9-S93 |
| ST-02 | Vovk V. "Cross-conformal predictors." Annals of Mathematics and Artificial Intelligence 74(1–2), 9–28 (online 2013). DOI 10.1007/s10472-013-9368-4 | A | Crossref 메타 확인(Claude) | 라이선스 미확인 → 수식·결과 인용만. 03 §4의 "Vovk 2015"는 권호 연도 표기로 보임(같은 권 논문 R4-S43이 "2015, 온라인 2013"으로 표기) | 03 §4(교차 conformal), 04 §6.1 | —(총괄 계획자 확인 2026-10-01) |
| ST-03 | Barber R.F., Candès E.J., Ramdas A., Tibshirani R.J. "Predictive inference with the jackknife+." The Annals of Statistics 49(1) (2021). DOI 10.1214/20-AOS1965 | A | Crossref 메타 확인(Claude) | 라이선스 미확인 → 수식·결과 인용만. R4-S39(Barber et al. 2023, "Conformal prediction beyond exchangeability")와 다른 논문 | 03 §4(CV+/jackknife+ 보장 1−2α → 실제 FAR 병기) | —(총괄 계획자 확인 2026-10-01) |
| ST-04 | Liu Y., Xie J. "Cauchy Combination Test: A Powerful Test With Analytic p-Value Calculation Under Arbitrary Dependency Structures." Journal of the American Statistical Association 115(529), 393–402 (online 2019, issue 2020). DOI 10.1080/01621459.2018.1554485 | A | Crossref 메타 확인(Claude) | 라이선스 미확인 → 수식·결과 인용만. 보장은 통계량이 쌍마다 이변량 정규(가우스 코퓰라)이고 α → 0일 때의 근사다 → **[v2] 계획에서 쓰지 않음**(conformal p값은 이산·동일 보정집합이라 조건 밖, 해상도 바닥·상쇄 문제. 검토 R-M P1-3) | 03 §3·§8(쓰지 않는 이유) | —(총괄 계획자 확인 2026-10-01) |
| ST-04a | Vovk V., Gammerman A., Shafer G. (2005) *Algorithmic Learning in a Random World*, Springer, DOI 10.1007/b106715 (Mondrian conformal 예측기의 원전) | A(학술서) | Crossref 메타 확인(Claude, 2026-10-02; 레코드에 저자 미기재 → 저자는 일반 서지 기준) | 인용만 | 03 §3(상태별 conformal 보정) | —(총괄 계획자 확인) |
| ST-04b | Shiryaev A.N. (1963) "On Optimum Methods in Quickest Detection Problems", Theory of Probability & Its Applications 8(1):22–46, DOI 10.1137/1108002 | A | Crossref 메타 확인(Claude, 2026-10-02) | 인용만 | 03 §5.2·05 §3(베이즈 누적, Tier 2) | —(총괄 계획자 확인) |
| ST-05 | Angelopoulos A.N., Bates S. (2023) "Conformal prediction: a gentle introduction", Found. Trends ML 16(4):494–591, doi:10.1561/2200000101(arXiv:2107.07511v6) | A | opened(본문): 보정조건부 커버리지가 Beta(n+1−l, l), l=⌊(n+1)α⌋(Vovk)이고 보정점 약 1000개 권장 확인〔R4〕 | arXiv 비독점 → 수식 인용 가능 | 04 §4.1(고정 보정집합의 실제 FAR Beta), §6.1 | R4-S46 |
| ST-06 | Gibbs I., Candès E. (2021) "Adaptive conformal inference under distribution shift", NeurIPS 34 | A | opened(본문): 식(2) α_{t+1}=α_t+γ(α−err_t), Prop. 4.1 … 확인〔R4〕 | arXiv 비독점 → 수식 인용 가능. "고장을 지운다"는 Prop. 4.1에서 나온 R4의 해석 | 04 §4.3(고장 중 갱신하는 적응형 conformal 금지), 05 §5(갱신은 확인된 정상 구간만) | R4-S40 |
| ST-07 | Benjamini Y., Hochberg Y. (1995) "Controlling the false discovery rate", JRSS-B 57(1):289–300, doi:10.1111/j.2517-6161.1995.tb02031.x | A | opened(메타)〔R4〕 | 인용만 | 04 §4.3(긴 창의 BH-FDR 금지 — 보정 표본 부족) | R4-S47 |
| ST-08 | Platt J.C. (1999) "Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods", in Advances in Large Margin Classifiers, MIT Press(저자 사본 1999-03-26) | A | opened(본문): 완전분리 시 기울기 발산, 목표값 식(13)(14) 확인〔R4〕 | ⓒMIT Press. 식 인용 가능 | 03 §3.2 D(확률 보정 — 실제 이상 1건으로는 지도 보정 불가), 04 §4.2(확률 품질) | R4-S58 |
| ST-09 | Vovk V., Petej I. (2014) "Venn-Abers predictors", UAI 2014(arXiv:1211.0025) | A | opened(본문): 출력 (p₀,p₁), 구간 폭이 과적합 정도를 알려줌, 로그손실 최소최대 병합 … 확인〔R4〕 | arXiv. 수식 인용 가능 | 04 §8(`va_low`/`va_high`), 05 T2-4 | R4-S63 |
| ST-10 | Saerens M., Latinne P., Decaestecker C. (2002) "Adjusting the outputs of a classifier to new a priori probabilities: a simple procedure", Neural Computation 14(1):21–41, doi:10.1162/089976602753284446 | A | 열람-초록〔R9〕 / opened(메타)〔R4〕 | ⓒMIT Press. 인용만 | 03 §4(기저율 시나리오 사후확률), 04 §8, 05 §5(확률 표시) | R9-S104, R4-S72 |
| ST-11 | Elkan C. (2001) "The foundations of cost-sensitive learning", IJCAI-01, 973–978(저자 사본) | A | opened(본문): §1.3 최적 결정 임계, … §3 기저율 변경 정리 확인〔R4〕 / 열람-전문 (저자 사본)〔R9〕 | ⓒIJCAI. PDF 글리프가 깨져 식은 재서술해 인용(R4) | 03 §4(p* = C_I/(C_U − C_P)), 05 §5(비용 기반 임계) | R4-S73, R9-S107 |
| ST-12 | Clopper C.J., Pearson E.S. (1934) "The use of confidence or fiducial limits illustrated in the case of the binomial", Biometrika 26(4):404–413, doi:10.1093/biomet/26.4.404 | A | opened(메타). 값은 statsmodels로 계산〔R4〕 | 인용만 | 04 §4.1(에피소드 1/1의 CI [0.025, 1], CP 구간), §6.1 | R4-S81 |
| ST-13 | Brown L.D., Cai T.T., DasGupta A. (2001) "Interval Estimation for a Binomial Proportion", Statistical Science 16(2), DOI 10.1214/ss/1009213286 | A | opened-초록〔R8〕 / opened(메타). 쪽수 미확인〔R4〕 | 인용만 | 04 §4.1(Wilson 구간), 05 WP9 | R8-E7, R4-S83 |
| ST-14 | Garwood F. (1936) "Fiducial limits for the Poisson distribution", Biometrika 28(3-4):437–442 | A | opened(메타). 값은 χ² 공식으로 계산〔R4〕 | 인용만 | 04 §4.1(FA/h Poisson 정확 구간) | R4-S87 |
| ST-15 | Hanley J.A., Lippman-Hand A. (1983) "If nothing goes wrong, is everything all right? Interpreting zero numerators", JAMA 249(13):1743–1745, DOI 10.1001/jama.1983.03330370053031(PMID 6827763) ※정정 4.1-14 | A | opened(메타, PubMed). 3/n 규칙은 수치로 확인(−ln 0.05=2.996)〔R4〕 / opened-메타(Crossref는 1저자만, Semantic Scholar는 2저자와 1743–5)〔R3〕 / 메타(EuropePMC 저자 확인)〔R8〕 / [검색만] Crossref〔R5〕 / 검색만〔R9〕 | 인용만 | 04 §4.1(0건이면 3/T), §6.1 | R4-S85, R3-V13, R5-S59, R8-E8, R9-S105 |
| ST-16 | Field C.A., Welsh A.H. (2007) "Bootstrapping clustered data", JRSS-B 69(3):369–390, DOI 10.1111/j.1467-9868.2007.00593.x | A | opened(메타)〔R4〕 / opened-메타〔R3〕 | 인용만 | 04 §6.3(10분 블록 군집 부트스트랩) | R4-S92, R3-V10 |
| ST-17 | Politis D.N., Romano J.P. (1994) "The Stationary Bootstrap", JASA 89(428):1303–1313, DOI 10.1080/01621459.1994.10476870 | A | opened(메타)〔R4〕 / opened-메타〔R3〕 / [검색만] Crossref〔R5〕 | 인용만 | 04 §2.3(긴 스트림 = 정상 블록 부트스트랩), §6.3 | R4-S90, R3-V12, R5-S31 |

### 2.7 합성 주입·증강·POD

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| SY-01 | U.S. DoD. MIL-HDBK-1823A, "Nondestructive Evaluation System Reliability Assessment," 7 April 2009 | A | [열람] PDF(배포문 A, 6.3·6.4절, 부록 G·H 목차와 본문)〔R5〕 | Distribution Statement A(공개, 무제한) → 인용·도식 차용 가능. NDE 균열 검출용이라 유추 적용임을 명시 | 03 §7-5(MAPOD형 검출한계), 04 §4.2(a50/a90 hit/miss GLM)·§4.3(계열 평균 POD 금지) | R5-S53 |
| SY-02 | Goswami M., Challu C., Callot L., Minorics L., Kan A. "Unsupervised Model Selection for Time-series Anomaly Detection." ICLR 2023. arXiv:2210.01078 | A | [열람] arXiv PDF(부록 A.5 주입 정의 포함)〔R5〕 / 열람-초록〔R9〕 | 코드 Apache-2.0. 의사라벨 평가에 adjusted F1(point-adjust 계열)을 씀 → 결론만 인용 | 04 §3(개발·보류 계열, 계열 맞바꾼 판), 03 §3.2 D | R5-S4, R9-S87 |
| SY-03 | Um, Pfister, Pichler, Endo, Lang, Hirche, Fietzek, Kulić. "Data Augmentation of Wearable Sensor Data for Parkinson's Disease Monitoring using Convolutional Neural Networks." ICMI 2017. doi:10.1145/3136755.3136817 | A | [열람] arXiv 본문〔R5〕 | 웨어러블 영역(유추 적용) | 04 §2.3(진동 스케일링은 라벨을 바꿀 수 있음 → 물리적으로 중립인 증강만) | R5-S21 |
| SY-04 | Schreiber, Schmitz. "Improved Surrogate Data for Nonlinearity Tests"(IAAFT). Phys. Rev. Lett. 77:635–638, 1996. doi:10.1103/PhysRevLett.77.635 | A | [검색만] Crossref. IAAFT 성질은 [S18]에서 [열람]〔R5〕 | 인용만. 본문 확인 전에는 방법 이름과 서지만 | 04 §3.1 F1(위상 무작위 IAAFT 대리잡음) | R5-S30 |
| SY-05 | Somepalli, Singla, Goldblum, Geiping, Goldstein. "Diffusion Art or Digital Forgery? Investigating Data Replication in Diffusion Models." CVPR 2023, pp. 6048–6058. doi:10.1109/CVPR52729.2023.00586 | A | [열람] arXiv 본문〔R5〕 | 이미지 영역(유추 적용임을 명시) | 03 §6(GAN·확산 합성 배제 — 이상 1건 복제 = 누설 경로) | R5-S28 |
| SY-06 | Lessmeier C., Kimotho J.K., Zimmer D., Sextro W. (2016) "Condition Monitoring of Bearing Damage in Electromechanical Drive Systems by Using Motor Current Signals of Electric Motors: A Benchmark Data Set for Data-Driven Classification." PHM Society European Conf. 3(1). DOI 10.36001/phme.2016.v3i1.1577 | A-(R5) / A(R2) / A−/B(R8) | [열람] PDF 본문(7.2절·결론)〔R5〕 / opened (KAt 페이지, 논문 PDF)〔R2〕 / opened-초록〔R8〕 | 논문 CC BY 3.0 US(R5; R2·R8은 CC BY 3.0). 데이터는 CC BY-NC 4.0(DS-08) | 03 §3.2 D 약점(인공 손상 학습 → 실제 손상에서 "quite low") | R5-S50, R2-S32, R8-D15 |
| SY-07 | Nosek, Ebersole, DeHaven, Mellor. "The preregistration revolution." PNAS 115:2600–2606, 2018. doi:10.1073/pnas.1708274114 | A | [검색만] Crossref〔R5〕 | 인용만(본문 미확인) | 04 머리말·§5(사전 등록), 05 §0-2 | R5-S62 |
| SY-08 | Chen, Kuo, Liu, Poon, Towey, Tse, Zhou. "Metamorphic Testing: A Review of Challenges and Opportunities." ACM Computing Surveys 51:1–27, 2018. doi:10.1145/3143561 | A | [열람] 초록〔R5〕 | ACM. SW 테스트 분야(개념 차용) | 04 §3.2(정상 변화 계열 N = 불변성 시험) | R5-S66 |
| SY-09 | Adams S. et al. (2025) "The Impact of Sensor Faults on Condition Monitoring of a Hydraulic Actuator." Annual Conf. PHM Society 17(1). doi:10.36001/phmconf.2025.v17i1.4415 | A/B | 열람-초록〔R9〕 | CC BY 3.0. 결함 주입 오픈소스 패키지 공개(코드 라이선스는 미확인) | 03 §1 L0, 04 §3.1 F8·§3.3 | R9-S22 |

### 2.8 신호처리·상태감시 표준(ISO/KS)

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| SG-01 | ISO 20816-1:2016, Mechanical vibration — Measurement and evaluation of machine vibration — Part 1: General guidelines. ISO/TC 108/SC 2, ed.1. https://www.iso.org/standard/63180.html. KS B ISO 20816-1(2023-12-29 개정, ISO 20816-1:2016 IDT) ※정정 4.1-7 | A | opened (iso.org 보관본 2026-02-26: 초록·상태·이력). 미리보기(목차, 4.1.3, 4.2, 4.3.2)는 … iTeh 공개 미리보기 사본을 직접 읽음〔R6〕 / opened(목차·범위): §6.3.2–6.3.3, §6.4.2 Setting of ALARMS, §6.4.3 Setting of TRIPS 확인〔R4〕 / [열람] ISO 카탈로그 초록〔R5〕 / KS opened〔R7〕 / unverified〔R1〕 | ISO 유료 → 초록 요지와 조항 번호만. 표·그림·zone 경계값 전재 금지. 단계 90.92 "to be revised". §6.3.3·§6.4.2·§6.4.3은 목차로만 확인. "기준선 + B영역 상한 25 %" 규칙은 미확인(3절) | 01 §2-2(진동 평가 구간 미적용), 03 §6, 05 §5(ALARM/TRIP 대응) | R6-S1, R4-S14, R5-S60, R7-S27, R6-S11, R1-S42 |
| SG-02 | ISO 20816-3:2022, … Part 3: Industrial machinery with a power rating above 15 kW and operating speeds between 120 r/min and 30 000 r/min. ed.1. https://www.iso.org/standard/78311.html. KS B ISO 20816-3(2026-07-28 제정, IDT) ※정정 4.1-8 | A | opened (보관본 2025-11-27: 적용·제외 목록 전문)〔R6〕 / KS opened〔R7〕 | 유료. zone 경계 수치 전재 금지. rotodynamic pump는 제외(→ ISO 10816-7). broad-band·steady-state 전제 → 우리 데이터는 세 조건 모두 벗어남 | 01 §2-2, 03 §6 | R6-S2, R7-S28 |
| SG-03 | ISO 10816-7:2009, Mechanical vibration — Evaluation of machine vibration by measurements on non-rotating parts — Part 7: Rotodynamic pumps for industrial applications, including measurements on rotating shafts. https://www.iso.org/standard/41726.html. KS B ISO 10816-7(제정 2017-02-17, 최종확인 2022-12-29, IDT) ※정정 4.1-9 | A | opened (보관본 2024-05-10)〔R6〕 / KS opened〔R7〕 / unverified〔R1〕 | 유료. **rotodynamic 펌프 전용** → 용적식 유압펌프에 등급 기준을 빌려 쓰지 않음 | 03 §6(ISO 진동 등급 직접 적용 배제) | R6-S3, R7-S30, R1-S42 |
| SG-04 | ISO 17359:2018, Condition monitoring and diagnostics of machines — General guidelines. ed.3, 2018-01. https://www.iso.org/standard/71194.html. KS B ISO 17359(2019-12-19 개정, 2024-12-20 확인, IDT) | A | opened (iso.org 보관본 2026-02-22, 초록·상태). 미리보기(목차와 §8.1–8.8 본문)는 … iTeh 사본을 직접 읽음. §8.9 alert/alarm, §8.10 baseline, §9.3 본문은 미리보기 범위 밖〔R6〕 / 열람-전문 (미리보기 §8.4–8.8)〔R9〕 / opened(본문 일부, iTeh 샘플)〔R4〕 / [열람] 카탈로그 초록〔R5〕 / KS opened〔R7〕 / unverified〔R1〕 | 유료 → 조항 번호와 미리보기로 확인한 짧은 인용만. §8.9 내용은 미확인(R4는 search-only) | 03 §3.2 A(§8.4 고장 대 운전조건 변화), 05 §5(기준선 대비 변화, §8.7 운전조건·단위 기록) | R6-S7, R9-S06, R4-S13, R5-S61, R7-S21, R1-S42 |
| SG-05 | ISO 13373-1:2002, Condition monitoring and diagnostics of machines — Vibration condition monitoring — Part 1: General procedures. https://www.iso.org/standard/21831.html. KS B ISO 13373-1(2026-07-16 개정) | A | opened (보관본 2024-05-10, 초록)〔R6〕 / KS opened〔R7〕 | 유료. 본문 미열람 → 센서 선택·신호조건화의 근거로만. 앤티앨리어싱 조항 번호 미확인 | 05 §5(센서·수집 로드맵) | R6-S4, R7-S26 |
| SG-06 | ISO 13374-1:2003, Condition monitoring and diagnostics of machines — Data processing, communication and presentation — Part 1: General guidelines. KS B ISO 13374-1(2026-07-16 개정) | A | 열람-전문 (iTeh 공식 미리보기 §2)〔R9〕 / KS opened〔R7〕 | 유료, 미리보기 범위만. 처리 블록 명칭은 KS 본문 미열람(R7) | 03 §1 L0(Data Acquisition 블록의 data quality), L6(고장 유형·심각도·권고 조치 표시) | R9-S05, R7-S25 |
| SG-07 | IEEE Standard for Digitizing Waveform Recorders(IEEE Std 1057). DOI 10.1109/IEEESTD.2018.8291741 | A | Crossref 메타데이터 opened(번호·연도는 메타데이터에 없음, DOI는 2018 등록)〔R6〕 | IEEE 유료. 판 연도 "1057-2017"은 추정 → 확인 필요 | 03 §2.1 A60(사인 적합), 05 WP2 | R6-S13 |
| SG-08 | Vaughan R.G., Scott N.L., White D.R. "The theory of bandpass sampling," IEEE Trans. Signal Process. 39(9):1973–1984, 1991. DOI 10.1109/78.134430 | A | Crossref + 초록(OpenAlex) opened〔R6〕 | IEEE. 인용·의역만 | 01 §2-2(언더샘플링·접힘 해석) | R6-P1 |
| SG-09 | VanderPlas J.T. "Understanding the Lomb–Scargle periodogram," ApJS 236(1):16, 2018. DOI 10.3847/1538-4365/aab766 | A | Crossref + 초록〔R6〕 | AAS/IOP. R6 분석은 Zechmeister & Kürster 2009의 floating-mean GLS를 씀(R6-P19, Crossref 메타) | 01 §2-2(불규칙 버스트 시각에서 부하 주기 2.9 s) | R6-P18 |

### 2.9 설명가능성·오류분석·교란·보고 지침

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| XE-01 | Lundberg S.M., Erion G., Chen H., DeGrave A., Prutkin J.M., Nair B., Katz R., Himmelfarb J., Bansal N., Lee S.-I. "From local explanations to global understanding with explainable AI for trees." Nature Machine Intelligence 2, 56–67 (2020). DOI 10.1038/s42256-019-0138-9 | A | opened-초록 (Nature 페이지, arXiv 1905.04610)〔R8〕 | 구독(arXiv판 있음). 코드 shap은 MIT(SW-06) | 03 §3.4(TreeSHAP) | R8-A2 |
| XE-02 | Alcala C.F., Qin S.J. "Reconstruction-based contribution for process monitoring." Automatica 45(7), 1593–1600 (2009). DOI 10.1016/j.automatica.2009.02.027 | A | opened-초록 (CityU 페이지) + 메타〔R8〕 | 비OA. smearing 근거는 Westerhuis et al. 2000(R8-A5, opened-전문 (PDF)) | 03 §3.2 B·§3.4(RBC, 채널 간 번짐 주의) | R8-A6 |
| XE-03 | Apley D.W., Zhu J. "Visualizing the Effects of Predictor Variables in Black Box Supervised Learning Models." JRSS-B 82(4), 1059–1086 (2020). DOI 10.1111/rssb.12377 | A | opened-초록 (OUP)〔R8〕 | 비OA | 03 §3.4(ALE — PDP는 상관 특징에서 외삽) | R8-A7 |
| XE-04 | Friedman J.H., Popescu B.E. "Predictive learning via rule ensembles." Annals of Applied Statistics 2(3), 916–954 (2008). DOI 10.1214/07-AOAS148 | A | opened-전문 (arXiv 0811.1679 §8)〔R8〕 | 인용만 | 03 §3.4(H 통계량에 parametric bootstrap 귀무분포) | R8-A8 |
| XE-05 | Hooker G., Mentch L., Zhou S. "Unrestricted permutation forces extrapolation: variable importance requires at least one more model, or there is no free variable importance." Statistics and Computing 31, 82 (2021). DOI 10.1007/s11222-021-10057-z | A | opened-초록 (arXiv 1905.03151) + 메타〔R8〕 | CC BY 4.0 | 03 §3.4(특징군 제거 후 재학습), 04 §7 C8 | R8-A11 |
| XE-06 | Ojala M., Garriga G.C. "Permutation Tests for Studying Classifier Performance." JMLR 11:1833–1863 (2010). https://www.jmlr.org/papers/v11/ojala10a.html | A | opened-전문〔R3〕 / opened-초록 (JMLR 페이지)〔R8〕 | JMLR(OA). sklearn `permutation_test_score`가 이 논문을 인용(R3, 코드 확인) | 03 §3.4(Test 2 — 결합 정보 필요성) | R3-V8, R8-C6 |
| XE-07 | Lapuschkin S. et al. "Unmasking Clever Hans predictors and assessing what machines really learn." Nature Communications 10, 1096 (2019). DOI 10.1038/s41467-019-08987-4(article 번호는 4.2-14) | A | opened-초록 (EuropePMC)〔R8〕 / opened-메타(article 번호 미확인)〔R3〕 / 검색만〔R9〕 | CC BY 4.0 | 03 §3.4(설명의 1차 용도 = Clever Hans 감사), 04 §7 C14 | R8-C2, R3-V22, R9-S91 |
| XE-08 | DeGrave A.J., Janizek J.D., Lee S.-I. "AI for radiographic COVID-19 detection selects shortcuts over signal." Nature Machine Intelligence 3(7), 610–619 (2021). DOI 10.1038/s42256-021-00338-7 | A | opened-초록 (Semantic Scholar) + 메타〔R8〕 / opened-메타〔R3〕 | Nature(PMC판 있음) | 01 §6, 03 §6(실제 레이블 학습 배제), 04 §7(양성·음성이 다른 출처 = 지름길에 이상적인 상황) | R8-C3, R3-V21 |
| XE-09 | Lipsitch M., Tchetgen Tchetgen E., Cohen T. "Negative controls: a tool for detecting confounding and bias in observational studies." Epidemiology 21(3), 383–388 (2010). DOI 10.1097/EDE.0b013e3181d61eeb | A | opened-초록 (EuropePMC)〔R8〕 / opened-메타(Crossref 제목 "Negative Controls")〔R3〕 / 검색만〔R9〕 | 비OA(PMC판 있음). 음성 대조가 민감하려면 조건이 필요하다고 저자가 한계를 명시 | 01 §6, 04 §7 C2·C3 | R8-C5, R3-V23, R9-S92 |
| XE-10 | Petersen M.L., Porter K.E., Gruber S., Wang Y., van der Laan M.J. "Diagnosing and responding to violations in the positivity assumption." Statistical Methods in Medical Research 21(1), 31–54 (2012). DOI 10.1177/0962280210386207 | A | opened-초록〔R8〕 | green OA | 01 §6(positivity 위반), 03 §2.1(지지 범위 플래그 → 판정 보류) | R8-C12 |
| XE-11 | Tautz-Weinert J., Watson S.J. "Using SCADA data for wind turbine condition monitoring – a review." IET Renewable Power Generation 11(4):382–394 (2017). DOI 10.1049/iet-rpg.2016.0248 | A | opened-전문(초록, normal behaviour modelling 범주)〔R3〕 / opened-초록〔R8〕 / 열람-초록〔R9〕 | 유료(R3), green OA 사본(R8). 풍력 분야라 유추 적용 | 03 §1 L1–L2·§2(정상 거동 모델 = 부하 조건부 기준선) | R3-M28, R8-D7, R9-S12 |
| XE-12 | Michau G., Fink O. "Unsupervised transfer learning for anomaly detection: Application to complementary operating condition transfer." Knowledge-Based Systems 216, 106816 (2021). DOI 10.1016/j.knosys.2021.106816 | A | opened-초록〔R8〕 | CC BY-NC-ND 4.0(Crossref) → 그림 변형·상업 이용 불가, 문장 인용만 | 04 §2.1 분할 C(학습에 없던 정상 운전 상태의 오경보), 03 §2.1 지지 범위 | R8-D9 |
| XE-13 | Kapoor S., Narayanan A. "Leakage and the reproducibility crisis in machine-learning-based science." Patterns 4(9), 100804 (2023). DOI 10.1016/j.patter.2023.100804 | A | opened-전문 (누수 8유형 L1.1–L3.3 확인)〔R8〕 / opened-전문(초록: 누설 8유형 분류, model info sheet)〔R3〕 / [열람] 초록〔R5〕 / 검색만〔R9〕 | CC BY 4.0 | 01 §7(L3.2·L1.4), 03 §3.1 P-leak, 04 §7 C5 | R8-F2, R3-V7, R5-S63, R9-S89 |
| XE-14 | Kapoor S. et al. "REFORMS: Consensus-based Recommendations for Machine-learning-based Science." Science Advances 10(18), eadk3452 (2024). DOI 10.1126/sciadv.adk3452 | A | opened-전문 (EuropePMC, 표 1의 32문항 전부 확인)〔R8〕 / [열람] 초록〔R5〕 | 라이선스 표기가 엇갈림(R8 "Science Advances(OA)", R5 "CC BY-NC") → 그림 재사용 전 확인, 문장 인용 권장 | 04 §7(주장 장부), 05 WP9(`claims_ledger.md`) | R8-F1, R5-S64 |

### 2.10 현장 관행·인간요인·경제성

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| FP-01 | Wiczorek R., Manzey D. (2014) "Supporting attention allocation in multitask environments: effects of likelihood alarm systems on trust, behavior, and performance." Human Factors 56(7):1209–1221 | A | 열람-초록〔R9〕 | 실험 연구(현장 전이는 유추) | 05 §5(물리 비교 표시 = 가능도 경보 + 원자료 교차확인) | R9-S71 |
| FP-02 | Bansal G. et al. (2021) "Does the whole exceed its parts? The effect of AI explanations on complementary team performance." CHI | A | 열람-초록〔R9〕 | 실험 연구 | 03 §3.4(설명만 붙이면 정답 여부와 무관하게 수용만 증가) | R9-S80 |
| FP-03 | Gigerenzer G., Hoffrage U. (1995) "How to improve Bayesian reasoning without instruction: frequency formats." Psychol. Rev. 102(4):684–704 | A | 열람-초록〔R9〕 | 인용만 | 03 §7-7, 05 §5(자연빈도 표기) | R9-S74 |
| FP-04 | Görges M., Markewitz B.A., Westenskow D.R. (2009) "Improving alarm performance in the medical ICU using delays and clinical context." Anesth. Analg. 108(5):1546–1552 | A | 열람-초록〔R9〕 | 단일 기관 관찰연구. 타 분야 → 설계 원칙의 근거로만 | 03 §4(지속성 — 지연이 무의미 경보를 줄이지만 지연 비용) | R9-S54 |
| FP-05 | Drew B.J. et al. (2014) "Insights into the problem of alarm fatigue with physiologic monitor devices." PLOS ONE 9(10):e110274 | A | 열람-초록〔R9〕 | CC BY 4.0(그림도 출처 표기 시 재사용 가능). 타 분야 | 03 §1 L0(기술 경보 31 % → 계측 층 분리) | R9-S51 |
| FP-06 | The Joint Commission (2013-04-08). Sentinel Event Alert, Issue 50: Medical device alarm safety in hospitals | A | 열람-전문〔R9〕 / unverified(403)〔R4〕 | "전체로만 복제 가능" → 짧은 사실 인용·요약만. 자발 보고(역학 자료 아님) | 03 §1 L0(센서 원인의 비조치 경보) | R9-S49, R4-S114 |
| FP-07 | Wickens C.D. et al. (2009) "False alerts in air traffic control conflict alerting system: is there a 'cry wolf' effect?" Human Factors 51(4):446–462 | A | opened(초록): 경보 495건 중 45%가 오경보였지만 cry-wolf 행동은 보이지 않음(반례) 확인〔R4〕 / 열람-초록〔R9〕 | ⓒHFES/SAGE. **반례**로 병기 | (보강 후보) 03 §4·05 §5 — 경보 예산 논리의 반례로 병기 | R4-S95, R9-S47 |
| FP-08 | Kwong J.C.C. et al. (2022) "The silent trial – the bridge between bench-to-bedside clinical AI applications." Front. Digit. Health 4:929508 | A | 열람-초록〔R9〕 | CC BY | 05 §5(도입 절차 ① 그림자 운전) | R9-S60 |
| FP-09 | Saxena A., Celaya J., Saha B., Saha S., Goebel K. (2010) "Metrics for Offline Evaluation of Prognostic Performance." IJPHM 1(1). doi:10.36001/ijphm.2010.v1i1.1336 ※정정 4.1-3 | A(NASA Ames) | 열람-전문〔R9〕 | IJPHM 오픈액세스 | 05 §5(as-found 기록 — "paradox of prognostics") | R9-S08 |
| FP-10 | Alahmadi B.A., Axon L., Martinovic I. (2022) "99% False Positives: A Qualitative Study of SOC Analysts' Perspectives on Security Alarms." USENIX Security, 2783–2800 | A | 열람-전문〔R9〕 | 오픈액세스. 정성 연구(n=20·21) | 03 §3.3 J·05 §5(처리 코드 (b) 정상 운전 변화 = benign trigger) | R9-S66 |
| FP-11 | Thomas D.S., Weiss B.A. (2021) "Maintenance Costs and Advanced Maintenance Techniques in Manufacturing Machinery: Survey and Analysis." IJPHM 12(1). doi:10.36001/ijphm.2021.v12i1.2883 | A | 열람-전문 (p.1–10)〔R9〕 | CC BY 3.0 US. n=71, 저자가 "anecdotal evidence"로 명시 → 단서 병기 필수 | (보강 후보) 05 §5 비용 기반 임계 — 외부 경제 수치는 단서와 함께만 | R9-S02 |

### 2.11 국내 문헌·법규·현장 자료

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| KR-01 | 「산업안전보건기준에 관한 규칙」[고용노동부령 제450호, 2025-09-01 일부개정, 시행 2026-03-02] 제35조, 제103조, 제104조. 국가법령정보센터 lsiSeq=273603 | A | opened〔R7〕 | 위험 낮음 | 05 §5(위치 정의 — 법정 점검·방호장치를 대체하지 않음) | R7-S33 |
| KR-02 | 같은 규칙 [별표 3] 작업시작 전 점검사항(법령정보센터 첨부 PDF, flSeq=40366527) | A | opened (내용). 첨부의 개정 시점은 미확인〔R7〕 | 위험 낮음(최신 별표로 재확인 권장). 프레스 항목에 유압펌프 상태 항목 없음 | 05 §5 | R7-S34 |
| KR-03 | ㈜인터엑스(INTERX), 「제조데이터 표준 활용 가이드(유압식프레스) — AAS표준(IEC 63278-1:2023)을 중심으로」(2026.2). KAMP 「제조데이터 참조모델」에서 연결된 GitHub `kosmo-AAS/kasmo-AAS_Pubilc` 저장소 `2025_KPC_Public/INTERX/07. 유압식 프레스/` | B | opened (docx 전문 텍스트 추출)〔R7〕 | 저장소 라이선스 미지정(`license: null`) → 저작권 유보로 보고 짧은 인용·출처 표기만. 근거 없는 수치(3절) 인용 금지. 데이터셋 수행기관과 같은 업체. 위험 중간(벤더 수치 인용 시) | 05 §5(센서·수집 로드맵, AAS 속성명 출력 필드) | R7-S37 |
| KR-04 | KAMP 「제조데이터 참조모델」 목록. https://www.kamp-ai.kr/dataReferenceList | A(목록)·B(내용) | opened〔R7〕 | 각 저장소 조건을 따름 | 05 §5(유압식 프레스·용적형 펌프 AAS 서브모델) | R7-S38 |
| KR-05 | KAMP 우수사례 「냉간단조설비 센서데이터 AI적용을 통한 예지보전 향상」(정원금속㈜ × ㈜디엠테크컨설팅, 2023-06-13), USECASE_SEQ=200 | B | opened〔R7〕 | 성능 수치 없음 | (보강 후보) 03 §1 L1(전류로 정지 구간을 가려 정상 운전 구간을 나누는 국내 선례), 03 §4(여러 묶음 누적 검정) | R7-S40 |
| KR-06 | 이정형 (2021). 시계열 특징을 갖는 선박용 공기 압축기 전류 데이터의 이상 탐지 알고리즘 적용 실험. 해양환경안전학회지 27(1):127–134. doi:10.7837/kosomes.2021.27.1.127 | A(KCI 등재) | opened〔R7〕(R7 2-F 공통: 초록·서지 열람, 본문 PDF 미열람) | 데이터·과제가 달라 수치 비교 불가 | (보강 후보) 04 §3.4 — 미세 부하 변동형 이상의 FN 위험 가설 | R7-S44 |
| KR-07 | 김기동·김영일 (2021). MCSA를 활용한 3상 유도전동기의 고장진단과 예지보전. 설비공학논문집 33(12):656–669. doi:10.6110/KJACR.2021.33.12.656 | A(KCI 우수등재) | opened〔R7〕(초록·서지) | 같음 | (보강 후보) 03 §2.1(전류 = 부하 대리변수), 05 §5(조치 후 점수 복귀 확인) | R7-S45 |
| KR-08 | 김지연·김기환·하상현·강영진·정석찬 (2024). 진공 패드 압력 이상 탐지를 위한 데이터 불균형 처리 기법 적용 및 그 효과 분석. 한국정보통신학회논문지 28(12):1450–1458. doi:10.6109/jkiice.2024.28.12.1450 | A(KCI 등재) | opened〔R7〕(초록·서지) | 반례 맥락으로만 인용 | 03 §6(SMOTE류 과표집 배제) | R7-S55 |
| KR-09 | 최승준·김종근·이수윤·정동헌 (2024). 트랙터 유압기어펌프 내구시험 설계. 대한기계학회논문집 A 48(4):279–284. doi:10.3795/KSME-A.2024.48.4.279 | A(KCI 등재) | opened〔R7〕(초록·서지) | 펌프 형식 미확정 → 형식별 주 고장 기전의 예시로만 | (보강 후보) 05 §5 점검 카드 | R7-S49 |
| KR-10 | 김경수·이지환·강명철·유범상 (2018). 유압 피스톤 펌프의 수명 예측 연구. 한국군사과학기술학회지 21(5):607–613. doi:10.9766/kimst.2018.21.5.607 | KCI 미확인(ScienceON) | opened〔R7〕(초록·서지) | 같음 | (보강 후보) 05 §5 점검 카드 | R7-S50 |

### 2.12 소프트웨어 라이선스

R3의 소프트웨어 확인은 GitHub REST API `license.spdx_id`, LICENSE 원문, PyPI JSON, Hugging Face API로 2026-10-01에 했고 상태는 모두 opened다(R3 2.4).

| 번호 | 출처 | 등급 | 확인 | 라이선스·사용 위험 | 계획에서 쓰는 곳 | 원보고서 ID |
|---|---|---|---|---|---|---|
| SW-01 | scikit-learn | — | opened〔R3〕 | BSD-3-Clause. `permutation_test_score`, `TimeSeriesSplit(gap=…)`, `GroupKFold`, `LeaveOneGroupOut`, `MinCovDet` 존재를 코드에서 확인 | 05 §1(Tier 1) | R3-L1 |
| SW-02 | scikit-learn 공식 사용자 가이드 — `HistGradientBoostingClassifier`의 `monotonic_cst`(열람 버전 1.9.1) | — | 공식 문서 열람(Claude) | 단조 제약은 이진 분류에서 지원, 다중 클래스·범주형 특징에는 미지원 | 03 §3.2 D | —(총괄 계획자 확인 2026-10-01) |
| SW-03 | numpy / scipy / pandas / matplotlib / statsmodels | — | opened〔R3〕 / opened(LICENSE)〔R4〕 | BSD-3(+번들) / BSD-3 / BSD-3 / matplotlib License(PSF 기반) / BSD-3-Clause | 05 §1(Tier 1) | R3-L34, R3-L11, R4-S108 |
| SW-04 | PyTorch | — | opened〔R3〕 | 저장소 LICENSE는 BSD 계열. PyPI `torch` 2.14.1의 license_expression에는 번들 구성요소 때문에 여러 라이선스가 섞여 있음 | 05 §1(B0′, E) | R3-L12 |
| SW-05 | TensorFlow | — | opened〔R3〕 | Apache-2.0 | 05 §1(B0 가이드북 원본 재현, 별도 requirements) | R3-L13 |
| SW-06 | shap(github.com/shap/shap) `shap/explainers/_tree.py` | — | opened(소스)〔R8〕 / opened〔R3〕 | MIT. TreeExplainer가 `sklearn.ensemble.IsolationForest`를 명시적으로 지원 | 03 §3.4, 05 §1(Tier 2 설명) | R8-G1, R3-L34 |
| SW-07 | PyALE(DanaJomar/PyALE) | — | opened(LICENSE)〔R8〕 | MIT(저작자 표기 자리가 "[year] [fullname]" 그대로 남음). 직접 구현도 쉬움 | 03 §3.4 | R8-G3 |
| SW-08 | DIFFI(github.com/mattiacarletti/DIFFI) — Carletti M., Terzi M., Susto G.A. "Interpretable Anomaly Detection with DIFFI: Depth-based feature importance of Isolation Forest." Engineering Applications of AI 119, 105730 (2023). DOI 10.1016/j.engappai.2022.105730 | A(논문) | 메타 + opened-초록(arXiv 2007.11117) + GitHub 확인〔R8〕 | 코드 MIT(LICENSE.md 확인). sklearn 내부 함수를 고친 파일을 씀 → 최신 sklearn 동작 미검증, 버전 고정 필요 → 선택 | 03 §3.4 | R8-A3 |
| SW-09 | MAPIE / crepes / venn-abers 1.5.4 | — | opened(PyPI 메타·LICENSE) / opened(PyPI 분류자·LICENSE 첫 줄) / opened(PyPI)〔R4〕 | BSD-3-Clause / BSD / MIT | 05 §1 `calibrate.py`(선택. 직접 구현 가능) | R4-S102, R4-S103, R4-S104, R3-L28 |
| SW-10 | MOMENT(Goswami M. et al., ICML 2024, PMLR 235:16115–16152, arXiv 2402.03885) / Chronos(Ansari A.F. et al., arXiv 2403.07815v3, README bib상 TMLR) | A / A/B | opened-전문 + 라이선스 opened〔R3〕 / opened-전문(arXiv). TMLR 게재는 README로만 확인〔R3〕 | 코드·HF 가중치 MIT / 코드·가중치 Apache-2.0. MOMENT는 사전학습 데이터 오염 위험, 둘 다 학습 문맥 512(짧은 버스트는 패딩) | 03 §3.3 E, 05 §4(Tier 3) | R3-M23, R3-L18, R3-M24, R3-L19 |

## 3. 주의·사용 금지 출처

| 출처 | 이유 | 대신 쓸 것 |
|---|---|---|
| 경쟁팀 공개 저장소(R2-S09–S12), 대회 기간 공개 저장소 목록(R7-S61), 개인·수업 저장소(R2-S08, S13) | 라이선스 없음(모든 권리 유보), 검토되지 않은 주장, 독창성 관리. 한 곳은 KAMP 원자료를 공개 커밋 | 우리 EDA·코드로 다시 계산한 수치(01 문서), 가이드북 원문(KM-02) |
| 가이드북 PDF 자체·표지·그림 1·2·5·6·7·8·9·11(KM-02) | 다운로더 회원 ID·워터마크, 제3자 그림 | 수치·문구만 쪽 표시와 함께 인용. 그림은 우리 데이터로 새로 그림 |
| AI 허브 데이터(R2-S39–S41) | 내국인·학습용 한정, 제3자 제공 금지, 국외 반출 별도 합의 | NLN-EMP(DS-04), ZeMA(DS-01) |
| Paderborn KAt 데이터(R2-S32) | CC BY-NC 4.0(상금 있는 대회의 NC 해석 위험) | 논문만 인용(SY-06). 전류 데이터가 필요하면 NLN-EMP |
| CWRU(R2-S34), MAFAULDA(R2-S35), PHM 2022 rock drill 데이터(R2-S21), Hercik & Svoboda 2023 공개분(R2-S23) | 라이선스 표기 없음("without restrictions"는 라이선스가 아님), 나머지 NDA | 논문 개념만 인용(rock drill 논문 CC BY 3.0 US, Hercik 논문 CC BY 4.0) |
| Kaggle pump_sensor_data(R2-S26), Sánchez et al. 2026 arXiv:2601.11163(R2-S27) | 라이선스 "Unknown", 출처가 일화적인 물 펌프. arXiv 논문이 이를 "hydraulic pump"로 잘못 기술 | ZeMA(DS-01), Helwig 논문(DS-02·03) |
| Crompton Greeves Three Phase Pump 데이터(R2-S28) | 합성 데이터, 구독 필요 | 쓰지 않음 |
| KAMP 실증·지역 데이터셋(R2-S06) | 로그인 필요, 사용조건 미표기, 50종 밖 | 주최 측 확인 전에는 쓰지 않음 |
| SKAB(R2-S36) | GitHub GPL-3.0과 Kaggle AGPL-3.0이 불일치, 데이터에 카피레프트 | 쓰지 않음. "F1이 비슷해도 FAR이 높을 수 있다"(LSTM-AE FAR 29.96 %)는 다른 데이터임을 밝힌 단서로만 |
| 공공데이터포털 목록의 "이용허락범위 제한 없음"(KM-04) | 목록 파일에 대한 표기 | 데이터 본체 조건은 KAMP 페이지·약관(KM-01·03) |
| goodstream 블로그(R2-S50) | "원본 재판매 제한" 주장의 근거가 없음(C) | KAMP 페이지·약관 원문 |
| Moirai 가중치(R3-M26·L21), TimesFM 3.0 가중치(R3-M25·L20) | CC-BY-NC-4.0 / timesfm-non-commercial-license-v1.0 | MOMENT(MIT)·Chronos(Apache-2.0)(SW-10), TimesFM ≤ 2.5 가중치(Apache-2.0) |
| alibi-detect(R3-L23), Alibi Explain(R8-G2) | Business Source License 1.1(오픈소스 아님) | shap(SW-06)·PyALE(SW-07), 직접 구현 |
| catch22/pycatch22, hctsa, saxpy, twitter AnomalyDetection, 옛 NAB 복사본(R3-L14, L25–L27) | GPL-3.0 / CC BY-NC-SA 4.0 + GPL-3.0 / GPL-2.0 / GPL-3.0 / AGPL-3.0(2015-08-10 ~ 2024-12-03) | tsfresh(MIT)·자체 특징. NAB는 2024-12-03 이후 MIT판만 |
| DCdetector 저장소(R3-M22·L17), VUS GitHub 저장소(R3-L10), PyPI `prts`(R3-L32) | 라이선스 없음 / LICENSE 없음(PyPI `vus`는 Apache-2.0 표기) / "Other/Proprietary" 표기, 원문 미확인 | 수식을 보고 직접 구현. VUS는 TSB-AD 구현 |
| OpenModelica(R5-S36), MATLAB/Simscape 예제(R5-S33·S34) | AGPL v3 또는 OSMC-PL 택일 / 상용, 모델 재배포 불가 → 한 명령 재현 불가 | 식(모델 형태)만 인용, numpy로 직접 구현(R5 권고) |
| Gu & Shi 2019, Mathematical Problems in Engineering(R1-S26) | Hindawi MPE의 2022–23 대량 철회 이력, 이 논문의 철회 여부 미확인 | DOE 자료(DP-08·09), Thomson & Fenger(DP-10). 길잡이로만 |
| Kumar, Sathujoda, Ranjan 2021, Vibroengineering PROCEDIA(R1-S38) | 출판사(JVE/Extrica) 품질 편차 | 정렬불량 1×·2× 징후는 일반 서술로 |
| MDPI 계열 논문(R1-S12·S13·S15·S34, R3-E21, R5-S39–S41, R8-D16) | 논문별 심사 품질 편차(금지는 아님) | 개별 품질을 확인하고 가능하면 다른 출처와 병기 |
| "ISO 10816/20816 경보 = 기준선 + B영역 상한의 25 %" 규칙(R4-S14 search-only, R5 4절, R6 5절, R7 3.5, R9-S115) | 벤더 사이트에서만 확인, 원문 미확인 | 쓰지 않음. ISO 20816-1 §6.3.3·§6.4.2는 조항 번호만 쓰고, 임계는 우리 정상 데이터와 경보 예산으로 정함 |
| 벤더 다운타임 통계(R9-S113: exida 초록의 "연 $20B" 등, Siemens/Senseye "True Cost of Downtime" 류) | C등급, 판매 이해관계 | Thomas & Weiss 2021(FP-11, 단서 병기), 파라미터 비용 모형 |
| DOE FEMP O&M Best Practices Guide의 수치(R9-S04) | "independent surveys" 원출처 불명 | 정의 인용만 |
| INTERX 가이드의 근거 없는 수치("유압 시스템 고장의 70~80%는 유압유 오염", 서보유압 30~50 % 절감)(R7-S37), KAMP 우수사례 기대효과(R7-S39) | 벤더 서술, 예상치 | 속성명·구조만 인용(KR-03) |
| 국내 통계(산업연구원 2020 스마트공장 도입성과, 대한상의 2024 AI 활용률 재인용; R7-S42·S43) | 자기보고·선택편향, 재인용, 예지보전 특정 아님 | 쓰지 않음(쓰면 1–2개만, 출처·한계 병기) |
| 철회·대체된 표준판: ISO 13379-1:2012, ISO 13381-1:2015, ISO 10816-3:2009, KS B ISO 10816-1(폐지) | 대체·철회(4.1-5–4.1-8) | ISO 13379-1:2025, ISO 13381-1:2025, ISO 20816-3:2022, KS B ISO 20816-1(KS 부합판 연도 병기) |
| ISO 10816-7:2009 / KS B ISO 10816-7(SG-03) | 회전동역학 펌프 전용 | 등급 적용 금지. "기준선 대비 변화" 개념만(SG-01 Criterion II, SG-04) |
| 확인 못 한 출처: ISO 20958:2013(R6-S12), 전기사업법 시행규칙 주파수 허용오차(R6-L1), NI-DAQmx 채널 문서(R6-V2), Analog Devices MT-002(R6-V3), ISO 14224(R9-S114), FAA AC 25.1322-1(R9-S45), Moubray RCM(R1-S37·R4-S109), Nowlan & Heap(R4-S110), SAE JA1011/1012(R4-S111), ISO 3448·ISO 4406·ASTM D341(R1-S42·S43) | unverified·미검증 | 확인 전에는 인용 보류(5절) |
| Wikipedia "Current loop"(R9-S112), NAMUR NE 43(R9-S111, 제목·판만 확인) | C / 회원 전용·본문 미확인 | 근거로 쓰지 않음 |
| ANDRITZ 보도자료(R1-S4), Feintool 브로슈어(R1-S2·S3) | 홍보성 C / 제조사 주장 B | 사실관계 보조로만, "제조사 주장"으로 표기 |
| Tong, Feng, Li 2018 Science Advances(R4-S79)의 그림, REFORMS(XE-14) 그림 | CC BY-NC(그림 재사용 시 비상업 조건) / 라이선스 표기 엇갈림 | 문장 인용만 |
| PVLDB 논문(AD-03, R3-E3·E4)과 Michau & Fink(XE-12)의 그림 | CC BY-NC-ND → 변형·상업 이용 불가 | 인용·재서술, 그림은 우리 데이터로 |
| Joint Commission SEA #50(FP-06) | "전체로만 복제 가능" | 짧은 사실 인용·요약만 |
| HSE CRR 166 사본(R4-S07)·ISA-18.2 목차 발췌본(R4-S01) | 제3자 호스팅 사본, Crown copyright·ISA 저작권 | 원 출처로 인용하고 요지만 |

## 4. 서지 정정 목록

### 4.1 원보고서가 바로잡은 서지

| # | 정정 내용 | 보고서 |
|---|---|---|
| 1 | Li, Z., Zhu, Y., van Leeuwen, M. "A Survey on Explainable Anomaly Detection." — ACM Computing Surveys가 아니라 **ACM TKDD 18(1), Art. 23, 1–54 (2024; 온라인 2023)**, DOI 10.1145/3609333. 확인: 메타(Crossref) + search-only(내용) | R8-A12 |
| 2 | "Anomaly explanation: A review"의 세 번째 저자는 Pinel이 아니라 **Pivert**: Yepmo, V., Smits, G., Pivert, O., Data & Knowledge Engineering 137, 101946 (2022), DOI 10.1016/j.datak.2021.101946. 확인: 메타 + search-only | R8-A13 |
| 3 | Saxena et al.(2008, 2010)의 예지 성능 지표 논문은 NIST가 아니라 **NASA Ames**(Prognostics Center of Excellence) 저자다. NIST 쪽 PHM 문헌은 Vogl·Weiss·Helu(2019), Thomas·Weiss(2020, 2021) | R9 머리말, R9-S08 |
| 4 | Vogl, G.W., Weiss, B.A., Helu, M. "A review of diagnostic and prognostic capabilities and best practices for manufacturing." — **2016년 온라인 공개, J Intell Manuf 30(1):79–95(2019) 수록**, doi:10.1007/s10845-016-1228-8 | R9 머리말, R9-S01 |
| 5 | ISO 13379-1:2012는 **ISO 13379-1:2025(2판, 제목 "…of machine systems…")로 대체되어 철회(95.99)**. KS B ISO 13379-1은 아직 2012판 부합(2024-12-20 확인) → "ISO 13379-1:2025(KS B ISO 13379-1은 2012판 부합)"로 인용. 2025판 정식 발행일은 미확인 | R6-S8, R9-S07, R7-S22 |
| 6 | ISO 13381-1:2015는 2025-09에 **ISO 13381-1:2025(ed.3)**로 대체. KS B ISO 13381-1은 2015판 IDT | R6-S9 |
| 7 | **KS B ISO 10816-1은 2018-03-22 폐지**(KS B ISO 20816-1로 대체) → 인용하지 않음. ISO 20816-1:2016은 ISO 10816-1:1995·ISO 7919-1:1996을 대체 | R7-S29, R6-S1 |
| 8 | ISO 20816-3:2022는 ISO 10816-3:2009·ISO 7919-3:2009를 대체하고 rotodynamic pump를 적용 범위에서 뺀다(→ ISO 10816-7). KS B ISO 20816-3은 2026-07-28 제정 | R6-S2, R7-S28 |
| 9 | ISO 10816-7:2009(KS B ISO 10816-7)는 "rotodynamic pumps for industrial applications"(회전동역학·원심 등) **전용** → 용적식 유압펌프의 등급 기준으로 빌리면 오류 | R6-S3, R7-S30 |
| 10 | IEC 62682:2022(Ed.2.0)는 2014년 1판을 대체한 기술 개정판이다(packaged systems 포함, 정의 갱신) | R4-S02 |
| 11 | ISA-18.2의 데드밴드·지연 출발값(유량 5 %/15 s 등)은 **2009판 그림**에서 왔고 지금은 ISA-TR18.2.3에 있다. 2016판 본문 그림은 1–5뿐. 2차 매체 수치는 "2009판, 2차 인용"으로 표기 | R4-S01·S03·S10, R4 3.1(4) |
| 12 | HSE CRR 166/1998 — PDF에는 "First published 1997"로 되어 있다 | R4-S07 |
| 13 | 단측 CUSUM(k = 0.5)의 ARL₀는 h = 4에서 336, h = 5에서 930(NIST)이다. 교재에 흔히 실린다는 168·465는 양측 값으로 단측의 약 절반(교재 원문은 미확인) | R4 3.2, R4-S26 |
| 14 | Hanley & Lippman-Hand 1983 — Crossref에는 1저자만 등록되어 있다. Semantic Scholar·PubMed는 2저자, 1743–1745 | R3-V13, R4-S85 |
| 15 | Ma, Zhao, Zhang, Akoglu(2023) SIGKDD Explorations 25(1)은 arXiv:2104.01422와 제목이 다르다 | R5-S15 |
| 16 | Kaggle pump_sensor_data는 물(수원) 펌프 데이터인데 Sánchez et al. 2026(arXiv:2601.11163)이 "hydraulic pump"로 잘못 기술했다 | R2-S26·S27 |
| 17 | Kim Seo-yeon 외(2021, 대한산업공학회 추계학술대회, DBpia NODE10671952)는 2023년 대회 대상작(XAER)과 **무관**하다(검색 요약이 잘못 연결) | R7-S60, R7 3.4 |
| 18 | e-나라표준인증의 KS B ISO 20816-1 "대응 국제표준" 칸이 'ISO/NP 20816-1'로, KS B ISO 13373-3이 'ISO/PRF 13373-3'으로 표기되어 있다. DB 표기 오류로 추정(20816-1은 2016판으로 판단) | R6-S11, R6 3.4 |

### 4.2 보고서끼리 엇갈린 표기(정정이 아니라 확인이 필요한 것)

| # | 내용 | 계획 처리 |
|---|---|---|
| 1 | **샘플링 해석.** R2·R5·R6·R7은 10 Hz를 전제로 전류를 "0.6 Hz 앨리어스"로 읽었다. R6은 진동 1.8/3.6 Hz 선이 유도전동기 회전 차수와 맞지 않는다며 원인을 미해결로 남겼고, 실제 전기 주파수는 정할 수 없다고 했다. R1은 버스트 = 약 1 kHz 스냅샷(S1k)이라는 가설로 전류 = 정확히 60.0 Hz, 톤/전류 비 = 슬립과 정량 일치라고 봤다 | 01 §2-2는 R1을 가설로 채택하고 모든 정의를 샘플 단위로 둔다. 확정은 수집 사양 확인 뒤(5절 1번) |
| 2 | **Run rule ARL₀.** R9-S96(CRAN `spc`)의 370.40 / 225.44 / 166.05 / 152.73은 규칙을 하나씩 더한 값이다(R9 5절: 전체 규칙 ARL 미확인). Western Electric 4규칙 전부는 R4 몬테카를로 재현으로 약 92(정확값 91.75는 원문 미확인) | 03 §3.2 B의 "370 → 166"은 4-of-5 규칙 하나만 더한 기준이다. "4규칙 전부면 약 92"를 병기하는 것이 정확 |
| 3 | **조용한 이상 버스트 번호.** R3·R6은 #3·#19·#20, R8은 #4·#20·#21이다. 번호가 1씩 어긋난다(0부터 셈과 1부터 셈의 차이로 보임) | 01 §4는 시각(10:51:31, 10:53:42, 10:53:52)으로 표기. 인용 전 시각으로 대조 |
| 4 | **가이드북 등급.** R1 A(데이터 출처 1차 문서), R8 A/B, R2·R5 B | KM-02에 모두 표기 |
| 5 | **Joint Commission SEA #50.** R4는 unverified(403), R9는 열람-전문 | FP-06은 R9 표기를 따름 |
| 6 | **IEC 62682.** R4는 opened(목차), R9는 미검증. R7은 KS 부합판을 unverified로, R4-S15는 KS 검색 0건으로 적음 | AL-02는 R4 표기를 따름 |
| 7 | **KS B ISO 13381-1 확인일.** R4·R6은 2026-08-28, R7은 2021-08-31 | 인용 전 e-나라표준인증에서 재확인 |
| 8 | **KS B ISO 10816-3.** R6은 "조회 결과 없음", R7은 K001010133641(2021 확인) | 계획은 20816-3을 쓰므로 영향 없음. 인용할 일이 생기면 재확인 |
| 9 | **REFORMS 라이선스.** R5는 CC BY-NC, R8은 "Science Advances(OA)" | XE-14: 그림 재사용 전 확인, 문장 인용 권장 |
| 10 | **Lai et al., NeurIPS 2021 D&B("Revisiting Time Series Outlier Detection").** R3는 서지 확인을 못 해 표에서 뺐고, R5-S1은 PDF 본문을 [열람] | 계획은 직접 인용하지 않음. 인용하려면 R5 판본 기준 |
| 11 | **Schneider, Helwig, Schütze 2018, Meas. Sci. Technol.** R2는 "논문번호 미확인", R6-P27은 29(9):094002 | 인용하려면 R6 서지 기준으로 재확인 |
| 12 | **Wu & Keogh 서지.** R3는 IEEE TKDE 35, 2421–2429(2023; early access 2021)까지 확인(호는 미확인). R8은 "최종 권·쪽 미확인", R4·R5는 2021(early access)로만, R9는 2021/2023으로 표기 | AD-01은 R3 서지를 따름 |
| 13 | **"펌프 고장 시 최대 2–3일 정지".** R4는 "원문 미확인"으로 남겼다. R1은 가이드북을 열어 같은 문구를 적었다 | 총괄 계획자가 가이드북 7쪽 원문을 확인함(5절 5번) |
| 14 | **Lapuschkin et al. 2019 article 번호.** R8은 Nature Communications 10, 1096으로 적었고, R3는 article 번호를 확인하지 못했다고 적음 | XE-07은 R8 서지를 따름 |

## 5. 아직 확인 못 한 핵심 항목

계획이 기대는 정도가 큰 순서다. 1–4번은 주로 데이터 제공처(KAMP·스마트제조혁신추진단·㈜인터엑스)에 문의해야 풀린다(R6·R8).

| # | 항목 | 계획에서 기대는 곳 | 보고서 |
|---|---|---|---|
| 1 | 실제 샘플링 사양과 DAQ(1 kHz 여부, 앤티앨리어싱·PLC 평균 처리, 클럭), TimeStamp 생성 방식(명목값인지 실측인지), 정상·이상 파일이 같은 수집·내보내기 체계로 기록되었는지 | 01 §2-1·§2-2(S1k 가설, H3), 04 C4·C15·I1 | R1·R2·R5·R6·R8 |
| 2 | 펌프 형식(기어·내접기어·베인·피스톤)과 펌핑 요소 수, 전동기 극수·정격(kW·A), 직입·인버터 여부와 설정 주파수 | 01 §2-2(톤 차수 해석), 03 §2.2 M6, 04 F4·N5 | R1·R5·R6·R7·R8 |
| 3 | 센서 사양: 진동 센서 종류·측정량·단위·대역·부착 부위(모터 프레임인지 펌프인지 — KAMP 페이지와 가이드북 표기가 다름), 전류 센서 종류(CT·Hall)·측정 상·배율 | 01 §1, 03 §2, 04 I2 | R1·R2·R6·R7·R8·R9 |
| 4 | 07-17(일) 10:51 에피소드의 실제 상황(고장 단계, 시운전·정비 후 여부, 정비 기록)과 두 날의 운전 조건(제품·설정압·유온). 다른 날 정상 데이터·추가 이상 데이터가 있는지 | 01 §6(H1–H3), 04 §7 | R1·R8 |
| 5 | 가이드북: "2–3일 정지" 문구는 **확인 완료**(7쪽: "펌프 고장시 수리비용 및 수리 부품의 수급 문제로 최대 2~3일 가량 가동이 중단", 총괄 계획자 2026-10-01). 남은 것은 정확도 97.51 %·F1 0.7476의 평가 단위와 분할(분모) | 01 §7, 05 §5 | R4·R8·R9 |
| 6 | 경보관리 표준 수치: ISA-18.2-2016 표 5–7 원문, IEC 62682:2022 표 5–7 값과 2014판 대비 변화, EEMUA 191 4판 표 9–11·15–19, ISA-TR18.2.8 발간 여부, chattering 경험칙 출처, NAMUR NE 107 2025 개정과 F/C/S/M 정의 문구 | 03 §4, 05 §5(80/15/5는 지금 IChemE 2차 재현) | R4·R9 |
| 7 | ISO 본문: ISO 17359 §8.9(다단계 alert/alarm — search-only)·§8.10·§9.3, ISO 20816-1 §6.3.3 Criterion II 수치·§6.4.2 ALARM 설정 규칙("25 %" 포함), ISO 20816-3 측정 대역, ISO 13373-1/-2의 앤티앨리어싱·샘플링 조항, ISO 13379-1:2025 정식 발행일 | 05 §5, 03 §6 | R4·R5·R6·R7·R9 |
| 8 | KAMP "콘텐츠 변경허용"의 공식 정의와 공개 재배포 범위, kamp@kaist.ac.kr 운영 여부. 대회 규정 해석: 외부 데이터를 크기 앵커로만 쓸 때의 고지·동봉 의무, 사전학습 가중치·외부 모델 사용 규정, 심사 시 재실행 환경 | 01 §1, 03 §3.3 I, 05 §4 | R2·R3·R5·R7 |
| 9 | 원보고서 출처표에 원전이 없던 계획 개념: Mondrian conformal → ST-04a, Shiryaev → ST-04b로 [v2] 보완(Crossref 메타). **PyYAML 라이선스(MIT로 알려짐)는 아직 미확인** | 03 §3, 05 §1 | —(v2에서 일부 해결) |
| 10 | 비용 값: 프레스 라인 시간당 정지 손실, 점검 1회 비용, 금형 손상 비용(지금은 가정) | 03 §4, 05 §5 | R7·R9 |
| 11 | 대형 프레스 유압펌프의 P–F 구간·고장률. RCM의 P–F 정의(Moubray·Nowlan & Heap·SAE JA1012) | 04 F10 램프, 05 T2-2 | R1·R4 |
| 12 | 공기 혼입·공동현상·유온(점도)이 진동·전류에 주는 정량 효과(동료심사 근거), ISO VG 점도–온도 값 | 04 §3.1 F1, §3.2 N4(지금은 ZeMA 앵커로 대체) | R1·R5·R9 |
| 13 | 이상일 전류 변화가 수집 지터인지 실제 토크 맥동인지(고샘플링 재측정 필요), 10 Hz 해석의 1.8/3.6 Hz 접힌 선의 물리 원인 | 01 §3, 03 §2.3(이중 해석) | R6·R8 |
| 14 | 「소성가공 자원최적화」 전류 RMS의 실제 샘플링 간격(약 1분 추정) | 03 §3.3 I, 05 §4 | R2 |
| 15 | 한국 계통 주파수의 법정 허용범위 원문(전기사업법 시행규칙, ±0.2 Hz로 알려짐) | 01 §2-2(60.0 Hz 해석 보조) | R6 |
| 16 | IEC 62682가 KS에 다른 번호로 부합화됐는지, KOSHA 지침(P-116-2012 경보시스템 관리, M-110, M-121, M-131 등) 본문과 개정 여부, 안전보건규칙 별표 3 현행판 원문 | 05 §5 | R4·R7 |
| 17 | 본문을 못 본 문헌(내용 인용 전 원문 확인): Xu 2019(DP-03)·Aravind·Schuler·Randall & Antoni·MCSA 리뷰(R1), Helwig I2MTC(DS-02)·Vacca & Guidetti·Frith & Scott·Sobie·MathWorks 수치(R5), TaPR·Sørbø & Ruocco·Rewicki·Fawcett & Provost AMOC(R3), Bartelmus & Zimroz·Zimroz·Worden·Kullaa·Schlechtingen·Hendriks·CARE 공식·Miller 1998·Lei 2018(R8), Xu 2012·Adnan의 FAR·MAR·AAD 정확식·Collins 2016 권고 문구(R4), Champ & Woodall 91.75(R4·R9), Simmons & Sutter·Wickens & Dixon 0.70(R9) | 각 인용 위치 | R1·R3·R4·R5·R8·R9 |
| 18 | 서지 세부: 쪽수(Barber 2023, Brown 2001, Künsch 1989, Moustakides 1986, DeGroot 1983), Nixon 2019·e-detector의 게재처, Wu & Keogh의 호, Chronos TMLR 게재·Lag-Llama 심사 여부, IEEE Std 1057 판 연도, Miller 1998 호 | — | R3·R4·R6·R8 |
| 19 | 라이선스·도구: PyPI `prts` 원문, R `changepoint` CRAN, TimeGAN 정식 표기, Iglesias 출판본, DIFFI의 최신 sklearn 호환, Paderborn Zenodo 미러, MetroPT-3 샘플링, Hercik `README_DATA.md`, rock drill 데이터 조건 | 05 §1 | R2·R3·R5·R8 |
| 20 | 이 데이터셋을 쓴 KCI·학위논문이 있는지(검색 한도로 전수 검색을 못 함) → 확인 전에는 "국내 최초" 주장 금지 | — | R2·R7 |
