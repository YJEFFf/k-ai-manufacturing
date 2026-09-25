# Press Guard v2 — 구현·실험 상태

정상 전류를 직전 두 관측으로 예측하는 AR(2) 잔차를 기존 크기·파형 점수에 결합한다. 첫 6관측부터 짧은 파형 창, 8관측부터 기존 창을 적용한다. 각 성분은 정상 학습 분포로 변환하고, 정상 보정 **기록구간 최대 점수**로 전체 결합 점수를 보정한다. 라벨·절대 날짜·파일명은 모델 입력이 아니다.

**모델·CSV 순차 추론 구현과 테스트 완료. 웹 시연은 미완성이다.** `serve.py`와 `web/index.html`·`style.css`는 초안이며 API·브라우저 동작 검수를 하지 않았다. `web/app.js`는 준비 중 표시만 한다. 현재 웹 화면을 완성된 기능으로 소개하지 않는다.

기존 `../press_submission/` v1 코드·산출물·동결 기대값은 바꾸지 않았다. 이 폴더는 별도 버전의 후보 구현이다. 대회 보고서 작업은 시작하지 않았다.

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

## 검수 범위

2026-09-25 새 테스트 **13개 통과**. 저장·복원 동일, artifact 변조 차단, 미래 관측 불변, 라벨/날짜 변경 불변, 독립 순위 p값 계산 대조, 빈 입력·필수 열·α 오류, 구간당 첫 알림만 발행, 결측·중복·역순·혼합 시각 형식 경계, 1행/불규칙/128행/전체 청크 동일성을 확인했다. 실제 모델 출력은 선행 탐색 실험의 TP/FP/FN/F1과 일치한다. 실행 코드·산출물·학습 상태 해시도 대조했다.

순차 추론 검수 중 BLAS의 배치 크기에 따른 미세한 사인 잔차 차이가 ECDF 순위를 바꾸는 문제를 발견했다. v2에서는 행별 합산 순서를 고정했고, 시각은 각 행에 동일한 파싱 규칙을 적용했다. 최종 수치는 유지됐다. 원본 센서 이력은 직전 7행만 유지하며 이상 구간 내 반복 경보는 점검 건 하나로 묶는다.

아직 실행하지 않은 검수: 깨끗한 클론에서 v2 전체 재현, CLI 통합 검수, API·웹 화면 연결 및 브라우저 검수, 처리시간 벤치마크, 독립적인 후속 코드 리뷰. 수집 오류는 판정 보류이며 고장 확률·원인·잔여수명·자동 정지를 구현한 것이 아니다.
