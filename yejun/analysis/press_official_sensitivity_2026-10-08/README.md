# 공식 모델 상수 민감도·선택 규칙 교차 확인 (2026-10-08)

심사 지적(설계 누출: R1·R2 상수를 전체 자료를 본 뒤 정했다)에 대한 **민감도 감사**다. 새 검증이 아니며 공식 모델·상수·α는 바꾸지 않았다.

- 공식 모델: 1단계 '주의' = v2+R1(잠금 모델, 코드 `v2+H1`), 2단계 '점검 요청' = v2+R1+R2(`v2+H1+H2`). 상수 GAP_S 60초 · CONFIRM_ROWS 2행 · R2_Q 0.5% 분위 · R2_MIN_LEN 8행, α 1%.
- 계약 `PROTOCOL.md`·`protocol.json`은 평가 코드를 돌리기 전에 썼고, SHA-256과 시각(2026-10-07T21:47:35Z UTC)을 `protocol_lock.json`에 남겼다. 이후 고치지 않았다.

## 한 일

- 입력: 새로 돌린 공식 실행 결과 폴더(`%TEMP%\k-manufacturing-official-clean-20261008\unpacked\북적북적_code_통합본`)를 `%TEMP%\press_official_sensitivity_work\`에 통째로 복사한 사본. 점수 캐시 `code/press/tvt/cache/rows_{A,B}.pkl`을 그대로 쓰고 재학습하지 않았다. R2_Q·R2_MIN_LEN에 따라 바뀌는 r2_ref(학습 정상 prefix R² 분위)만 원본 CSV를 공식 함수(`01_scores.frame_rows`)로 다시 읽어 계산했다.
- 공식 코드(사본)를 import해 그대로 썼다: `lib.stream_rules`(R1)·`lib.prefix_r2`, `evalcore.evaluate`·`predict_rows`·`candidates`, `07_r1_on_baselines.test_only`(이상 흐름을 test부터 따로), `02_select_on_valid.main`(잠금 선택 규칙), `04.fit_split`·`13.rows_multi`·`record_alerts`(E3).
- 상수 바꾸기: GAP_S·CONFIRM_ROWS·R2_MIN_LEN은 `lib` 모듈 전역을 바꾸고, R2_Q는 다시 계산한 r2_ref를 인자로 넘겼다. R2_Q의 r2_ref는 공식 코드와 같이 R1 해제(파형 정상 행)와 R2 보류에 함께 쓰인다(`evalcore._streams`·`own_alarm` 확인). R2_MIN_LEN은 행 표의 `prefix_r2` 열을 저장된 전류로 다시 계산했다.
- 격자: GAP_S {30, 60, 120} × CONFIRM_ROWS {1, 2, 3} × R2_Q {0.001, 0.005, 0.01} × R2_MIN_LEN {6, 8, 10} = 81점, α 1%(주)·3·5%(보조), 분할 A·B.

## 공식 재현 확인 (모두 통과, `outputs/verify_report.json`)

- 공식 상수에서 v2·v2+R1·v2+R1+R2의 test/valid(α 1·3·5%, A·B, 실시간·기록 판정) 156건이 공식 `tvt_test.csv`·`tvt_valid.csv`(사본, `claude/code/press/tvt/outputs/` 판 모두)와 정수 일치, F1 차 ≤ 1e-12. test 실시간 행 F1은 v2+R1 A 1.000 · B 0.995391705, v2+R1+R2 A·B 1.000, valid 평균 0.9973·0.9982. test부터 따로 F1도 `tvt_r1_baselines.csv`와 같다.
- 8행으로 다시 계산한 prefix R²가 캐시 열과 비트 단위(NaN 위치 포함)로 같고, r2_ref(0.5%, 8행)가 메타 값과 같다(A 0.98432, B 0.98440).
- 패치 가시성: evalcore·07·04가 쓰는 `stream_rules`가 `lib.stream_rules`와 같은 객체이고 전역이 `lib`다. GAP_S = −1 또는 CONFIRM_ROWS = 10⁹이면 1단계가 v2와 같아지고, R2_MIN_LEN = m이면 기록 앞 m−1행만 NaN이다. α를 바꾼 `07.test_only`의 정상 오경보 행이 `evaluate`와 같다.
- 바꾸지 않은 표로 공식 02를 돌린 대조 실행은 `tvt_valid.csv`·`tvt_selection.json`을 공식 파일과 바이트 단위로 같게 냈다. E3 공식 상수는 13의 rolling 5창 수와 같다(150건 비교).
- 점수 캐시 해시가 사본 `tvt_selection.json`의 잠금 해시와 같다. import한 공식 소스는 `claude/code/press/tvt/`와 줄바꿈만 다르고(LF 맞춤 해시 같음) 원래 clean-run 폴더와 바이트 단위로 같다(`outputs/environment.json`). `claude/`에는 아무 파일도 생기지 않았다.

## 격자 결과 (α 1%, 81점)

| 지표 | 1단계 v2+R1 | 2단계 v2+R1+R2 |
|---|---|---|
| test 실시간 행 F1 A | 1.000 (81/81점) | 1.000 (81/81점) |
| test 실시간 행 F1 B | 0.956~0.995 (중앙값·공식 0.995, ≥ 0.99는 54/81점) | 1.000 (81/81점) |
| test 미탐 행 A·B | 0 (모든 점) | 0 (모든 점) |
| test 정상 오경보 기록 A / B | 0 / 3~6 (공식 0/3, 27점에서 다름) | 0 / 0 (모든 점) |
| test 정상 오경보 행 B | 3~30 (공식 3) | 0 |
| valid 실시간 F1(A·B 평균) | 0.981~0.997 (공식 0.997) | 0.990~0.998 (공식 0.998) |
| 이상 흐름을 test부터 따로 F1 A / B | 1.000 / 0.956~0.995 | 1.000 / 1.000 |

- 0.99 아래 27점은 모두 CONFIRM_ROWS = 1이다(B F1 0.973·0.964·0.956, R2_MIN_LEN 6·8·10). 1행이면 정상 기록의 자기 경보 1행도 '확인된 이상'이 되어 다음 기록으로 이어지고, B 정상 오경보가 3기록·3행에서 6기록·18~30행으로 는다.
- 한 번에 하나만 바꾼 8점: CONFIRM_ROWS 1(1단계 B 0.964)만 공식값과 다르고 나머지 7점은 1·2단계의 모든 지표가 공식값과 같다(`outputs/grid_oat.csv`).
- 영향이 큰 상수: CONFIRM_ROWS(1단계 test F1 평균 주효과 0.016, 정상 오경보 기록 +3, valid 0.012) > R2_MIN_LEN(0.003, CONFIRM_ROWS 1일 때만) > GAP_S·R2_Q(α 1%에서 모든 지표가 다른 상수 조합마다 수준과 무관). GAP_S는 α 3·5%에서도 무관했고 R2_Q는 α 3·5%에서 test F1 주효과 0.0003 이하, valid F1 주효과 0.0004 이하다.
- 탐지 쪽: 81점 × α 1·3·5% × A·B × 1·2단계 모든 경우 test 미탐 행 0, test 이상 11기록 모두 탐지, test부터 따로 돌려도 미탐 0. 상수가 움직인 것은 정상 오경보뿐이다.
- 2단계가 81점 모두 1.000인 이유: v2의 B test 오경보 3행(기록 안 위치 0부터 41·40·11, prefix R² 0.995~0.998)은 R² 계산이 시작되는 행(R2_MIN_LEN 10이면 위치 9)보다 뒤이고 격자의 모든 r2_ref(0.955~0.989)보다 높아 늘 보류된다. 이 3행은 R2 착안 때 본 기록(423·461·570)이다.
- 보조 α(변화는 모두 정상 오경보): α 3%에서 1단계 A 0.985~0.998·B 0.924~0.989, 2단계 A 1.000·B 0.983~0.998(공식 0.998). α 5%에서 1단계 A 0.985~0.998·B 0.896~0.976, 2단계 A 1.000·B 0.982~0.997(공식 0.986).

## 선택 규칙 교차 확인 (이상 기록 앞뒤 바꾸기)

- 뒤 11기록을 valid, 앞 10기록을 test로 바꿔 공식 02를 그대로 돌리면 잠금 규칙은 다시 v2+R1을 고른다(valid 평균 0.9985, 0.002 안 동률 6개 중 가장 단순. 동률 묶음은 공식과 같다). 기록 단위 트랙은 v3_B3k5(공식 v3_B3k10).
- 앞 10기록 test 실시간 행 F1 A / B (α 1%): v2+R1 0.998 / 0.995, v2+R1+R2 0.998 / 1.000, R1 없는 v2 0.958 / 0.967. A의 미탐 1행은 이상 파일 첫 기록의 첫 행(이전 기록이 없어 R1이 도울 수 없음), B의 오경보 3행은 공식 test와 같은 정상 기록이다. 공식(뒤 11기록 test)은 v2+R1 1.000 / 0.995, v2+R1+R2 1.000 / 1.000, v2 0.965 / 0.970.
- 같은 단일 사건의 앞뒤를 바꾼 것이라 독립 반복이 아니다. 선택 결과가 어느 절반을 valid로 쓰느냐에 따라 바뀌지 않았다는 것만 보인다.

## E3 시간순 5창 정상 300기록 (정상 전용)

| α | 1단계 v2+R1 경보 기록 수 (공식) | 2단계 v2+R1+R2 (공식) | v2 단독 |
|---|---|---|---|
| 1% | 2~4 (2) | 0 (81점 모두) | 2 |
| 3% | 8~16 (11) | 2~6 (2) | 8 |
| 5% | 15~28 (18) | 3~10 (4) | 14 |

- 가장 큰 상수는 CONFIRM_ROWS다. 1단계에서 1이면 늘고(α 1% 2→4, 3% 11→16, 5% 18→28) 3이면 α 3·5%에서만 준다(11→8, 18→15). 2단계는 α 3·5%에서 R2_MIN_LEN 10이 늘린다. GAP_S·R2_Q는 영향이 없다. 평가 300기록은 분할 B valid+test와 같은 기록이고 창마다 v2를 다시 적합했다(독립 자료 아님). 실행 42초로 20분 안이었다.

## 한계

- 이상 데이터는 약 3분짜리 단일 고장 사건(21기록)이다. 격자·앞뒤 바꾸기·E3 모두 같은 사건과 같은 정상 자료를 다시 쓴 것이라 새 검증이나 일반화 근거가 아니다.
- 상수는 전체 자료를 본 뒤 정했고 격자는 그 값을 가운데 둔 이웃 값이다. 국소 민감도이며 격자 밖 값은 보지 않았다. B 오경보 3행과 A valid 오경보(기록 461)는 R2 착안 때 본 기록이다.
- 결과를 근거로 공식 모델·상수·α를 바꾸거나 '최적 상수'를 제안하지 않는다. 공식값과 같거나 더 좋아 보이는 격자점이 있어도 채택하지 않았다.

## 프로토콜 이탈·검수 기록

- 프로토콜 이탈 없음.
- `verify.py` 첫 실행이 `r2_ref_grid.csv` 비교에서 실패했다. pandas 기본 CSV 실수 파서가 마지막 자리(1 ULP)를 잃은 탓이라 `float_precision="round_trip"`으로 읽게 고쳤고 18개 값이 모두 비트 단위로 일치했다. 결과 값은 바뀌지 않았다.
- `outputs/swap_selection.json`은 공식 02를 고치지 않고 돌린 출력이라 `protocol.splits.abnormal` 문구('앞 10기록 검증, 뒤 11기록 시험')가 그대로 남아 있다. 실제 역할은 `swap_summary.json`에 적었다.
- 계약 외 추가 산출: FP 행·미탐 행·test부터 따로 F1의 주효과, α 3·5% 주효과, 규칙 없는 v2 참고값, 앞뒤 바꾸기의 α 3·5% F1, E3 창별 표와 v2·v2+R2 수.
- 결정성: 전체 파이프라인(아래 '실행')을 두 번 돌렸다. CSV 15개는 바이트 단위로 같고, JSON 9개는 실행 시간(`seconds`) 필드만 달랐다. 두 번째 실행의 `verify.py`도 통과했다.

## 파일

| 파일 | 내용 |
|---|---|
| `PROTOCOL.md`, `protocol.json`, `protocol_lock.json` | 실행 전 계약과 SHA-256·UTC 잠금 |
| `sens_common.py` | 공식 코드 사본 import, 상수 패치, 공통 지표·재현·가시성 확인 |
| `run_grid.py` | 격자 81점 × α × A·B (약 3분) |
| `run_swap.py` | 앞뒤 바꾸기 선택·채점 (약 15초) |
| `run_e3.py` | E3 정상 5창 격자 (약 45초) |
| `make_summary.py`, `verify.py` | `summary.json`·`environment.json` 작성, 재현·재계산 확인 |
| `outputs/summary.json` | 핵심 수치 모음 |
| `outputs/grid_metrics.csv` | 격자 긴 표(분할·α·상수·단계별 지표 972줄) |
| `outputs/grid_alpha0{1,3,5}_wide.csv` | α별 격자점 한 줄 요약 |
| `outputs/grid_distribution.csv`, `grid_main_effects.csv`, `grid_oat.csv`, `grid_summary.json` | 분포·주효과·한 번에 하나 바꾸기 |
| `outputs/grid_reference_v2.csv`, `r2_ref_grid.csv` | 규칙 없는 v2 참고값, (R2_Q, R2_MIN_LEN)별 r2_ref |
| `outputs/swap_*.csv/json` | 앞뒤 바꾸기 valid 표·선택·test 표·요약 |
| `outputs/e3_*.csv/json` | E3 창별·합계 표, r2_ref, 요약 |
| `outputs/checks_grid.json`, `checks_e3.json`, `verify_report.json`, `environment.json` | 확인 기록, 판·소스·캐시 해시 |

## 실행

사용한 파이썬은 `%TEMP%\k-manufacturing-integrated-clean-py314\Scripts\python.exe`(공식 clean-run과 같은 환경)다.

```console
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
rem 공식 사본 위치가 다르면 PRESS_OFFICIAL_COPY, 임시 폴더는 PRESS_SENS_WORK로 지정
python run_grid.py && python run_swap.py && python run_e3.py && python make_summary.py && python verify.py
```

환경: CPython 3.14.7, numpy 2.5.3, pandas 3.0.6, scipy 1.18.1, scikit-learn 1.9.1, statsmodels 0.15.0, torch 2.14.0(CPU), Windows 10.
