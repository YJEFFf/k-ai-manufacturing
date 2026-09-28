# 평가관 05 — 창의성·차별성 10점 · cycle2 round4

2026-09-28. 구현·실험 검수 기록이다. 대회 보고서가 아니다. 경로는 `yejun/` 기준이다.

## 평가 대상과 점수

**9.4/10, 판단 범위 9.2~9.6.** 범위는 심사 판단의 여지를 나타내며 통계적 신뢰구간이 아니다. 공식 심사 결과나 경쟁팀 순위가 아니다.

공식 기준은 `analysis/press_rubric_review/official_task_extract.txt:85`의 불균형 학습·앙상블·불확실성 추정·확률보정·제조지식 결합 등 차별화된 방법 제안이다. 이전 점수와 회복 전망을 채점 기준으로 쓰지 않았다. 보고서가 없다는 이유로 감점하지 않았다.

차별성의 근거는 정상 자료로 적합하는 크기·파형·동역학 성분, 기록 최대값 보정, 별도 확률 층, 감시·수락 검사, 제조 점검 분기를 연결하고 그 비용까지 측정한 구현이다. 같은 특징 대안의 우수한 결과와 외부 적용 실패를 공개해 선택 근거의 범위도 확인할 수 있다. 현재 확인한 고칠 수 있는 P0·P1·P2 결함은 없다. 실제 고장·새 날짜와 제조 물리에 대한 검증 범위가 만점 판단을 제한한다.

검수 시작·종료 HEAD는 `6c61a88d8de437182a2cdd25f640af556a23036a`로 같다. **그 커밋 위의 승인된 미커밋 최종 작업사본**을 평가했다. 해당 커밋만으로 이번 판을 식별할 수 없으므로 마지막 절과 [judge05_verify.json](judge05_verify.json)의 `hashes_end`를 함께 사용한다. 검수 중 추적한 37개 파일의 해시 변경은 0개다.

**최종 재검수 완료:** 현장04 후속 수정이 동결된 뒤 C0~C7, 두 폴드 재적합·단위 검사, 관련 pytest 5개를 다시 실행해 모두 통과했다. 이전 검수와 비교해 `model.py`, `README.md`, `OPERATIONS.md`, `web/app.js`, `outputs/manifest.json`의 해시가 바뀌었고 저장 모델 4개·검증 수치는 같다([변경 기록](judge05_final_delta.json)). `model.py`의 역순 시각 보류·음수 간격 차단, `serve.py`의 조치 사전 전달, `app.js`의 관측 접두부 집계를 코드로 확인했다. 이 보고서의 수치 검증 범위는 정상 시각의 대회 원본과 R3-O1~O3 및 확률·비교 실험이다. 모의 화면·역순 입력의 상세 현장 동작은 평가관04의 [접두부 재검수](judge04_prefix_regression.json)·[역순 시각 재검수](judge04_time_reversal.json)를 참조한다. 최종 파일 재확인과 이 보고서의 해시는 [judge05_final_snapshot.json](judge05_final_snapshot.json)에 남겼다.

## 만점 대비 감점

| 감점 사유 | 감점 | 고칠 수 있음/한계 |
|---|---:|---|
| 방법의 유효성·확률·업무량을 실제 고장 및 독립 날짜에서 검증하지 못했다. 이상은 한 날 3분이며 날짜 교락과 사후 설계가 남는다. 현장 기저율·탐지율도 없어 확률 절대값은 가정에 조건부다. 이 증거 범위의 한계를 한 번으로 묶어 반영한다 | 0.4 | 현재 자료의 한계 |
| 제조지식 결합은 신호 관측과 일반 공학 가설까지다. 10 Hz 순시값, 부하·회전수·압력·정비 이력 부재로 주파수 원천과 FM1~FM6를 물리적으로 식별하지 못한다 | 0.2 | 현재 자료의 한계 |
| **합계** | **0.6** | **10 − 9.4 = 0.6** |

## 3회차 항목 충족

| ID | 판정 | 근거 |
|---|---|---|
| R3-O1 — 변경 기록 없는 전류 상승의 선점검 | 충족 | `press_guard/monitor.py:120`의 네 조치 분기를 실제 B 예측으로 실행했다. ×1.5 창 0은 전류 비 1.318876 > 기준 상한 1.265921, 알림 12/60으로 FM4·FM5 점검을 권한다. 같은 창에 변경 기록을 주면 재보정 검토다. ×1.3과 진동 잡음 2σ는 열화 점검이다. `monitor.py:163`의 4조치 × 결과 5경우를 실행해 두 점검 분기만 정상 확인 후 자료에 남는 것을 확인했다(C1). `recalibrate.py:157`의 실제 CLI 필터도 시험 통과. `OPERATIONS.md:22`, `README.md:174`, `web/index.html:23`, `web/app.js:649` 및 `outputs/monitor_gain_v2.csv`가 창별 조치를 표시한다 |
| R3-O2 — FM3 좁은 대역 접힘의 해석 | 충족 | `analysis/press_evidence/failure_mode_map.csv:4`, `build_diagnostics.py:606`. 저주파만으로 좁은 대역 회전 성분의 접힘을 배제하지 않는다. 이상 50행 5기록의 주기도표 최대값 AI0 1.18·0.72·0.30·0.36·0.02 Hz, AI1 0.70·0.28·0.18·1.10·0.18 Hz를 원본에서 재계산했고 문구와 모두 일치한다(C5). 0.4 Hz 미만의 짧은 기록 해석 한계도 있다 |
| R3-O3 — 정상 진동의 좁은 대역 구조 | 충족 | `analysis/press_evidence/observability.csv:2`, `vibration_tones.csv`, `README.md:238`, `build_diagnostics.py:501`. 정상 202기록 × 센서 2개와 이상 5기록 × 센서 2개의 총 414행을 독립 계산했다. 주파수 최대 오차 1.775×10⁻⁶ Hz. AI1 1.792568 Hz·조화 R² 0.912509·전류 진폭 상관 0.890535·위상 R 0.030764, AI0 3.593997 Hz·조화 R² 0.652077·위상 R 0.095454다(C5). 정상·이상 진동과 E1 흰 잡음 대리의 차이도 설명한다 |

3회차에서 부분으로 남은 더 이전 항목은 없다. 기존 확률·업무량 보완은 이번 C2·C4·C6에서도 현재 수치와 해석을 확인했다.

## 확인한 강점과 적용 범위

| 항목 | 이번 확인 결과 | 근거 |
|---|---|---|
| 불균형 대응 | 경보 모델은 정상만으로 적합·재보정한다. 별도의 라벨 확률 층과 구별된다. 클래스 가중 지도학습, 저장 형식만 쓴 기준선, 동일 특징 지도학습 비교가 공개돼 있다. 가중치나 높은 대회 F1만으로 우위를 주장하지 않는다 | `press_guard/README.md:27`, `analysis/press_supervised/README.md:24`·`:64`. 코드·표 검토. 지도학습 전체 재학습은 이번에 반복하지 않음 |
| 앙상블의 이득과 비용 | fmax·Fisher·Stouffer·합·평균·5NN, α 1·3·5%, A/B의 36조건을 재계산했다. α1% Fisher는 A 미탐 44→32, B 정상 알림 3→1이며 5NN은 미탐 44→36·31→29다. fmax의 유지 근거는 기존 선택 유지와 경보별 단독 근거 성분이다. Fisher의 단독 근거 없는 이상 경보 12·1행, 5NN 8·2행도 일치한다 | C3, `analysis/press_selection/README.md:8`·`:32`·`:48`, `combination_rules.csv`, `same_feature_alternatives.csv` |
| 대안의 전이 비교 | 주입 없음·전류 잡음 0.1σ·오프셋 0.2×·진동 잡음 2σ·충격 4σ의 두 분할·세 α·다섯 규칙 총 150값을 별도 순위 p·결합·주입 코드로 계산해 전부 일치했다. A α1%에서 대안들이 앞서는 결과, B 4σ 충격에서 fmax가 앞서는 결과, α별 무주입 기준선이 함께 공개돼 있다 | C3, `analysis/press_selection/README.md:53`, `rule_transfer_injection_v2.csv` |
| 불확실성과 공유 문턱 | 베타 이항 질량을 감마·베타 함수로 따로 계산했다. 60단위 수락 한도 2·4·7, 정상 거부확률 3.580%·4.205%·2.949%가 일치한다. B 부하 3/51의 공유 문턱 참고 p=0.09136978이고 고정위험 이항 p=0.04929468과 구별한다 | C2, `monitor.py:39`, `recalibrate.py:101`, `analysis/press_evidence/README.md:321` |
| 확률보정의 단위와 한계 | 21겹을 별도 등방 회귀로 적합했다. Brier A 0.00722780·B 0.00559398, ECE 0.00749499·0.00660095가 일치한다. 점수 격자 20,013·20,015개에서 LR 감소 0건. 라벨 없는 환산 216행도 산식과 일치한다. 행 π와 알림 단위 π를 구별하며 기록 확률은 같은 행 π를 쓰는 근사로 표시한다 | C4, `probability.py:8`·`:74`·`:127`, `press_guard/README.md:90` |
| 상한 주장의 정정 | LR 121은 표시 정책이며 이론상 상한·실제 확률의 하한 보장이 아니다. 명목 FAR 참고 LR도 보편적 상한으로 사용하지 않는다. 예를 들어 실제 FAR 0.001·TPR 0.955이면 알림 LR=955로, 최소 순위 명목 FAR에 고정한 115.555보다 크다. 현재 설명은 이 반례와 일치한다. SBB도 정확한 연속 p값의 참고값으로 제한한다 | C4, `probability.py:11`·`:127`·`:136`, `press_guard/README.md:119` |
| 제조 가설과 재보정 연결 | FM4·FM5 대리와 같은 전류 배율 상승을 변경 기록 없이 정상으로 흡수하지 않도록 점검·확인·자료 필터가 연결된다. 정상 진동 성분과 실제 관측 범위를 적고, 4성분 BIC 및 합성 상태 전환과 같은 상태 대조도 공개한다. 합성 잇기·이득 경사 수치를 실제 정상 전환율로 채택하지 않는다 | C1·C5, `analysis/press_evidence/README.md:281`·`:330`, `failure_mode_map.csv`. 상태 전환 전 표의 재생성은 평가관01 범위이며 이번에는 코드·표·설명 검토 |
| 2단계 추정과 사건 단위 | 비중첩 두 폴드의 모델을 원본에서 다시 적합했다. α5%에서 300~359는 1단계 5·2단계 1, 360~419는 2·0이고, 현재 표본에서는 건·사건 집계가 같다. 그 비 1/7을 B α1% 명목 29.58499건에 적용하면 4.22643건, 비의 단측 이항 95% 상한을 적용하면 15.40499건이다. 사후 규칙·같은 날·α 전환 가정 및 1/9·2/5·3/7 민감도가 공개돼 있다 | C6, [judge05_units_probe.json](judge05_units_probe.json), `insights.py:714`, `OPERATIONS.md:40` |

주 모델 직접 재계산은 A TP/FP/FN 556/0/44, F1 0.9619377163; B 569/3/31, F1 0.9709897611이다. 저장 모델·확률 보정기 4개는 manifest의 해시와 일치한다. 차별성 판단은 실제 구현한 비교 조건 안에서만 한다.

## 남은 수정·보완 목록

| ID | 우선 | 분류 | 위치 | 해야 할 일 | 완료 기준 |
|---|---|---|---|---|---|
| 없음 | — | — | 이번 검수 범위 | 고칠 수 있는 실제 P0·P1·P2를 발견하지 못함 | — |

새 모델 채택, 주 모델 교체, 분할 재선택, 대회 보고서 작성은 요구하지 않는다.

## 현재 자료로 해소할 수 없는 한계

아래는 위 감점 두 항목의 범위를 설명한다. 추가 감점하지 않는다.

- 21개 이상 기록은 같은 날의 3분이고 실제 고장 시작 시각·정비 원인·독립 고장 사례가 없다. 교차 적합·중첩 선택·합성 주입은 이 자료의 독립성을 새로 만들지 않는다. 정상 기반 전이의 근거도 평가한 인공 신호에 한정된다.
- 2단계 4.2건·상한 15.4건은 α5%의 조건부 비를 α1% 명목 업무량에 적용한 시나리오다. 비의 상한은 시간 의존성이나 현장 FAR의 불확실성을 함께 보장하지 않는다. 현재 두 폴드에서 건·사건 수가 같은 것도 다른 연속 입력의 보장이 아니다.
- 기저율과 실제 고장 탐지율이 없으므로 행·기록·알림 확률을 현장 절대값으로 검증하지 못한다. LR 표시 상한도 이 정보 부족을 해결하는 통계적 보장이 아니다.
- 0.6·1.8·3.6 Hz의 원천과 부하 상태의 물리적 의미는 가설이다. 진동 성분 관측과 전류 진폭 상관은 제조 원인 식별이 아니다. 10 Hz 순시값은 고주파 고장 모드를 구분할 수 없다.

## 직접 수행한 검증

공통 환경: `OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python`. 팀 코드·산출물·원본은 수정하지 않았고 Git은 읽기만 했다.

| 실행 | 결과·시간 | 기록 |
|---|---|---|
| `analysis/press_rubric_review/cycle2/round4/judge05_verify.py` | 최종 동결본 C0~C7 전부 통과, **15.316초**. 원본 해시, 실제 감시 분기, 자료 필터, 베타 이항, 결합·전이, 21겹 확률, 414행 진동, 업무량을 확인 | [스크립트](judge05_verify.py), [로그](judge05_verify.log), [JSON](judge05_verify.json) |
| `analysis/press_rubric_review/cycle2/round4/judge05_units_probe.py` | 최종 동결본 두 시간순 폴드 재적합·건/사건 집계 일치, **2.643초**. B 정상 6,097행의 누적 RMS를 매 행까지의 원 전류 표준편차로 다시 계산한 최대 오차 8.53×10⁻¹⁴ | [스크립트](judge05_units_probe.py), [로그](judge05_units_probe.log), [JSON](judge05_units_probe.json) |
| `python -m pytest -q -p no:cacheprovider press_guard/test_recalibrate.py::test_windows_option_filters_before_fitting press_guard/test_state_incidents.py press_guard/test_probability.py::test_zero_isotonic_endpoint_remains_monotone_under_interpolation` | 최종 동결본 **5 passed, 5.60초**. 실제 `--windows` CLI, 두 단발 경보 건의 사건 격상, 인과 상태, 0→양수 LR 보간. 임시 산출물은 pytest의 시스템 임시 폴더 | [로그](judge05_pytest.log) |

검수 스크립트의 준비 실행에서 CSV의 후보명·교차 적합 방식 이름을 맞추고 정상 겹 LR 집계를 구현의 중앙값으로 수정했다. 팀 산출물 오류가 아니며 최종 전체 실행은 모두 통과했다. 무거운 지도학습/E1~E3 전체 재학습, 서버 API·전체 패키지 재현은 이번 평가관 범위에서 반복하지 않았다.

## 최종 파일 해시

아래는 핵심 판정 파일의 SHA-256이다. 예측 파일, 문서·웹·나머지 표를 포함한 **37개 전체 해시**는 [judge05_verify.json](judge05_verify.json)의 `hashes_end`에 있다. 원본 두 CSV의 해시는 같은 파일의 `checks.C0_provenance.input_sha256`에 있다.

| 파일 | SHA-256 |
|---|---|
| `press_guard/model.py` | `8b9493a248609180f139aa777ed0b1cbf29d3bfca5e5b98f2e588cbeb0cb3f6f` |
| `press_guard/probability.py` | `67007ee9c8a9a12c48707e77230907dac2c155a519edfe7868863065aa4f34dd` |
| `press_guard/monitor.py` | `43b9be9c35df9ab01fb139b821c05f2d7aaaa6f414b4da7983839bdfc8694912` |
| `press_guard/recalibrate.py` | `448883f5c1d65e5b14877d838abcbd338df9970941683a425c0266e54b05042b` |
| `press_guard/insights.py` | `6eeb75f0daf73322d0e9a0877cdfb34e076a930bba798a9a9c691f1bbd1b9ddf` |
| `analysis/press_evidence/build_diagnostics.py` | `1541ad6409c256694d12691f8abccf72ee6f29954708c719b222748784a8de11` |
| `analysis/press_evidence/diagnostic_probes.py` | `620f1e2c1dde23cc4ce5d03a7ccf30c4033b2af52d48039c597b32152a39fcf6` |
| `analysis/press_evidence/vibration_tones.csv` | `de16d47406726addb7441c2e94758c4e959bd9d04f95b1a3aca43aa340846351` |
| `analysis/press_evidence/failure_mode_map.csv` | `be367c8be6aef2a6d4c9407db431d7c70bef6de699bb9f177e3eb1e6a844c0c7` |
| `analysis/press_selection/rule_transfer_injection_v2.csv` | `f9cd350b775bbf5ca1293a8f5d8e9d937f8a62fbee809f9d61e341d1e6072d63` |
| `press_guard/outputs/expected_effect_v2.csv` | `94b696d2dde0848987b55ea1558ca61fa91e90f1f6a60fd996be80fe3fcc7ec0` |
| `press_guard/artifacts/guard_A.json` | `c938707f1dd16e7c239b8053e7f032d8fac828d6c753de2b898ba9130a594f10` |
| `press_guard/artifacts/guard_B.json` | `b64ac3b30bc697034104287964f3154e88c8a50749ccdec04f6d4f8744fd6969` |
| `press_guard/artifacts/probability_A.json` | `1a8100e78046393d9292fc7c305b5ec57b46c4e2c73b03abeb596052a8705f8a` |
| `press_guard/artifacts/probability_B.json` | `7fde4cd1bdfa74e78e2d3f07c5dbd9c27619e19b2e94ceb8fab786c27abcaae8` |
