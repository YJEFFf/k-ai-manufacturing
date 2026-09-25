# Press Guard v2 — 구현·실험 상태

정상 전류를 직전 두 관측으로 예측하는 AR(2) 잔차를 기존 크기·파형 점수에 결합한다. 첫 6관측부터 짧은 파형 창, 8관측부터 기존 창을 적용한다. 각 성분은 정상 학습 분포로 변환하고, 정상 보정 **기록구간 최대 점수**로 전체 결합 점수를 보정한다. 라벨·절대 날짜·파일명은 모델 입력이 아니다.

**모델·CSV 순차 추론·로컬 웹 콘솔 구현과 테스트 완료(2026-09-25 Claude).** `serve.py`의 `/api/overview`·`/api/analyze`에 `web/app.js`를 연결했다. 점검 대기열(근거 필터·CSV 내보내기), 선택 구간의 전류·성분 점수 그래프(호버 툴팁·문턱선·재생), 성능 검증·외부 검증 탭이 동작한다. API 계약 테스트 10개와 헤드리스 Chrome 렌더링(DOM 값·스크린샷)으로 확인했다. 사람이 브라우저에서 클릭·업로드·재생을 직접 확인한 기록은 아직 없다. 로컬 기록 재생용이며 설비 제어를 하지 않는다.

기존 `../press_submission/` v1 코드·산출물·동결 기대값은 바꾸지 않았다. 예준의 위임을 기록한 `21c6cab`에 따라 v2를 최종 모델로 디벨롭한다. 대회 보고서 작업은 시작하지 않았다.

## 확인한 수치

동일 데이터, 정상 학습/보정 분할, matched 전처리, conformal α=1%.

| 분할 | 모델 | F1 | 미탐 행/600 | 정상 알림 구간 | 이상 알림 구간 | 최대 첫 경보 지연 |
|---|---|---:|---:|---:|---:|---:|
| A | v1 | 0.910082 | 99 | 0/120 | 21/21 | 0.7초 |
| A | v2 | **0.961938** | **44** | 0/120 | 21/21 | **0.5초** |
| B | v1 | 0.920322 | 86 | 3/180 | 21/21 | 0.7초 |
| B | v2 | **0.970990** | **31** | 3/180 | 21/21 | **0.5초** |

미탐 감소율 A 55.6%, B 64.0%. 첫 경보 지연은 **기록 시작 기준**이며 실제 고장 발생 시각은 없다. A/B는 같은 이상 21구간을 재사용하므로 독립 검증 두 건이 아니다. 이미 본 이상 자료를 사용한 탐색 결과이며 수상·현장 성능 보장의 근거가 아니다.

- 정상 평가 구간을 300~359, 360~419, 420~479, 480~539, 540~599로 나눈 시간순 5회 비교에서도 F1 0.961938~0.971819. 정상 알림은 각 0·0·2·0·0/60으로 v1과 동일. 이상 자료는 다시 같은 21구간이다.
- raw 정밀도 입력에서는 개선 유지. coarse B에서는 v2 정상 알림 **5/180**, v1 **4/180**으로 증가했다. 모든 입력 정밀도에서 오경보가 같다고 주장하면 안 된다.
- 단일 AR(2) 점수의 F1은 A 0.831548/B 0.839768. 다른 성분과의 결합 효과이며 단순히 새 모델 이름만 바꾼 결과가 아니다.

집계: [metrics.csv](outputs/metrics.csv), [rolling.csv](outputs/rolling.csv). 후보 전체 비교: [탐색 프로토콜](../analysis/press_advance/protocol.json), [전체 결과](../analysis/press_advance/metrics.csv). 추가 외부 자료: [UCI 검증](../analysis/press_external/README.md).

## 실행

저장소 루트에서 기존 `press_submission`의 고정 의존성이 설치된 Python을 사용한다. 현재 환경은 `/opt/anaconda3/bin/python`이다. 학습 상태·원본·행별 예측은 Git에 넣지 않는다.

```bash
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/train.py --rolling
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python -m pytest -q yejun/press_guard/test_guard.py
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/predict.py --model yejun/press_guard/artifacts/guard_A.json --input new.csv --out /tmp/press_predictions.csv --cases /tmp/press_cases.csv --chunk 128
```

CSV 필수 열: `TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current`. 기본 원본 위치는 v1 패키지와 같으며 `train.py --root`로 바꿀 수 있다. `predict.py`는 학습하지 않는다. 신규 설비의 정상 기준을 무검증으로 기존 모델에 적용하지 않는다.

## 최종 모델 패키지로서의 산출물 (2026-09-25 Claude)

예준 위임에 따라 v2를 최종 모델로 디벨롭한다. v1 패키지(`../press_submission/`)는 기준선·기준모델·LSTM 비교의 출처로 그대로 두고, 이 폴더에 분석·재현 도구를 갖춘다.

```bash
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
/opt/anaconda3/bin/python yejun/press_guard/train.py --rolling    # 학습·보정·저장·평가 (약 20초)
/opt/anaconda3/bin/python yejun/press_guard/analyze.py            # 통합 비교·오류 조건·불확실성·업무량·그림 (약 5초)
/opt/anaconda3/bin/python yejun/press_guard/audit.py              # 실행 검증 14개
/opt/anaconda3/bin/python yejun/press_guard/verify.py             # 동결 기대값 비교 (--freeze 로 동결)
PYTHON=/opt/anaconda3/bin/python bash yejun/press_guard/tools/clean_repro.sh # 커밋된 코드·기대값으로 새 클론 재현
```

| 산출물 | 내용 |
|---|---|
| `outputs/model_comparison_v2.csv` (+`.md`) | v1 패키지의 기준모델·결합·LSTM 결과와 v2 후보 고정 비교를 같은 입력(해시 확인)·분할·보정 구간에서 합친 표. `is_final_model`=early6_ar2 |
| `outputs/robustness_v2.csv` | matched로 적합·보정한 상태를 고정하고 평가 입력만 raw/coarse로 바꾼 v1·v2 결과(press_advance에서 추출). 웹 콘솔 성능 검증 탭에 조건표와 함께 표시 |
| `outputs/error_conditions_v2.csv` | v1·v2의 미탐(이상)·오경보(정상) 조건: 구간 내 위치, 구간 길이, 진동 산포·전류 진폭 4분위, 가장 강한 성분. 분모 포함 |
| `outputs/records_first_alarm_v2.csv` | 이상 21구간별 v1·v2 첫 경보 위치·미탐 행·첫 경보 근거 |
| `outputs/uncertainty_v2.csv` | 이동 블록 부트스트랩: 정상 알림 구간 수(블록 5·10·20), 이상 미탐 행·탐지 구간(블록 3·5). 관측값이 주 결과 |
| `outputs/workload_v2.csv` | α별 정상 첫 알림 수와 기록시간·경과시간 기준 알림률, 가동시간 시나리오 |
| `outputs/fig_recall_by_position_v2.png` | 위치별 이상 행 재현율 v1 vs v2 |
| `outputs/fig_first_alarm_v2.png` | 이상 21구간의 첫 경보 시점 v1 vs v2 |
| `outputs/fig_missed_example_v2.png` | v2 미탐이 가장 많은 구간의 전류·성분 점수 |
| `outputs/expected/` | `verify.py --freeze`로 동결한 결과 CSV 10개 + manifest/audit/summary |

v2의 미탐 감소 55행 중 위치 2~6에서 A 49행·B 51행, 위치 10 이후에서 A 6행·B 4행이 개선됐다. 위치 0·1은 A 각각 13행(합계 26), B 각각 10행(합계 20) 미탐으로 v1·v2가 같다. 그 위치에는 센서 크기 성분만 있다. 개선이 위치 2~6에만 국한된다는 이전 서술과 A 23·23/B 20·20 표기는 오류였다.

주 비교 기준은 α=1%다. B에서 α를 3%로 높이면 v2 정상 알림은 3→5구간(경보 행 3→7), 미탐은 31행으로 같고 F1은 0.970990→0.967687로 낮아진다. α=3%에서의 모델 간 비교도 v1 4/180 대 v2 5/180으로 표기한다. α=5%는 v1 6/180 대 v2 7/180이다.

`contracts.py`는 학습·분석·검수·웹 코드, 필수 예측/집계/그림, 원본 비교표, 개별 검사 14개를 확인한다. 분석은 학습 실행에, audit는 코드·모델·분석 결과에 연결된다. 파일 변경·검사 누락·오래된 audit는 동결 근거로 사용할 수 없다. 기대값도 자체 해시와 검사 계약을 검증한다. 새 클론은 v1 주 모델 예측을 재생성하고, 기존 기준모델·LSTM 비교표는 커밋된 표의 해시를 확인해 재사용한다. LSTM 전체 재학습은 포함하지 않는다.

## 웹 콘솔·검증 도구

```bash
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/serve.py --port 8765   # http://127.0.0.1:8765
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/audit.py       # outputs/audit.json (실행 검증 14개)
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/press_guard/benchmark.py   # outputs/benchmark.json (처리시간)
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python -m pytest -q yejun/press_guard/test_guard.py yejun/press_guard/test_serve.py
```

- `audit.py`: 실행 코드·저장 모델·v1 의존 코드·입력 해시가 manifest와 같은지, 입력 묶음 1·7·128행 순차 추론이 전체 추론과 같은지, 독립 집계·p값 순위 규칙·구간당 알림 한 번·날짜 이동/라벨 불변을 실제 자료로 확인한다. 웹 콘솔 '실행 검증' 목록이 이 파일을 읽는다.
- `benchmark.py`: 분할 A 평가 스트림 4,690행, CPU 한 스레드. 1행 묶음 호출당 약 10 ms(p95 10.5 ms)로 수집 주기 0.1초보다 짧다. 128행 묶음 약 7,300행/초, 전체 일괄 0.27초. 기기 참고치다.
- 웹 화면의 경보 문턱선은 `p ≤ α`와 동치인 점수(정상 보정 구간 최대 점수 순위)를 표시한다. 그래프 색은 계열 3개를 색각 이상 분리·대비 검사(dataviz 검증기)로 확인해 정했다.

## 검수 범위

2026-09-25 새 테스트 **13개 통과**. 저장·복원 동일, artifact 변조 차단, 미래 관측 불변, 라벨/날짜 변경 불변, 독립 순위 p값 계산 대조, 빈 입력·필수 열·α 오류, 구간당 첫 알림만 발행, 결측·중복·역순·혼합 시각 형식 경계, 1행/불규칙/128행/전체 청크 동일성을 확인했다. 실제 모델 출력은 선행 탐색 실험의 TP/FP/FN/F1과 일치한다. 실행 코드·산출물·학습 상태 해시도 대조했다.

순차 추론 검수 중 BLAS의 배치 크기에 따른 미세한 사인 잔차 차이가 ECDF 순위를 바꾸는 문제를 발견했다. v2에서는 행별 합산 순서를 고정했고, 시각은 각 행에 동일한 파싱 규칙을 적용했다. 최종 수치는 유지됐다. 원본 센서 이력은 직전 7행만 유지하며 이상 구간 내 반복 경보는 점검 건 하나로 묶는다.

2026-09-25 Claude 후속 검수([기록](../analysis/press_guard_review/README.md))와 Codex 재검수는 [재검수 기록](../analysis/press_guard_review/codex_recheck.md)을 참고한다. Chrome 자동 조작으로 탭·선택·재생·CSV 업로드/내보내기까지 확인했다. 계산 불가 점수를 0으로 그리던 문제와 빈 재생 위치의 호버 오류를 수정했다. 사람이 직접 조작한 확인·다른 OS·다른 날짜/설비 검증은 별개다. 수집 오류는 판정 보류이며 고장 확률·원인·잔여수명·자동 정지를 구현한 것이 아니다.
