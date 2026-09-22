# 베이스라인 이상탐지 · 검증 틀

> `code/03_baselines.py` 자동 생성. 점수는 모두 out-of-fold(원본 구간 5겹 분할)이다.

## 1. 왜 원본 구간 단위로 나눠야 하나 (누수 점검)

| 분할 방식 | 평가 행 중 '같은 원본'이 학습에도 있는 비율 |
|---|---|
| 무작위 행 분할(80/20) | **96.7%** |
| 원본 구간 5겹 분할(우리 방식) | 0.0% |

→ 무작위로 나누면 평가 데이터 대부분이 학습 데이터와 똑같은 행이다. 이렇게 나온 성능은 의미가 없다.

## 2. 모델

| 모델 | 방식 |
|---|---|
| SPC | 변수별 로버스트 z의 최대 절댓값 — 현장 관리한계 규칙 |
| IsolationForest | 트리 분할로 쉽게 고립되는 점을 이상으로 봄 |
| AutoEncoder | 병목층 신경망의 복원 오차 — 원 가이드북 방식 재현 |
| RobustMahalanobis | 로버스트 공분산 기준 통계적 거리 |

특징: raw = 가압력·전류·전압·통전시간 / phys = 입열량·동저항·가압력·전류·통전시간. 학습: dedup = 학습 구간의 원본 행만 / all = 복제 행 포함.

## 3. 일별 불량 수 LODO (실제 라벨, 8일)

다른 7일의 불량률로 임계값을 정하고 남긴 날의 경보 수를 불량 수로 본다. 실제 총 불량 39건.

| model | MAE_model | MAE_naive | spearman_pred_actual | pred_total |
|---|---|---|---|---|
| IsolationForest|raw|dedup | 4.75 | 2.19 | 0.48 | 33.0 |
| IsolationForest|raw|all | 5.125 | 2.19 | 0.48 | 36.0 |
| SPC|raw|all | 6.375 | 2.19 | 0.373 | 46.0 |
| SPC|raw|dedup | 6.375 | 2.19 | 0.373 | 46.0 |
| SPC|phys|all | 6.375 | 2.19 | 0.373 | 46.0 |
| SPC|phys|dedup | 6.375 | 2.19 | 0.373 | 46.0 |
| IsolationForest|phys|all | 6.5 | 2.19 | 0.373 | 47.0 |
| AutoEncoder|phys|all | 6.75 | 2.19 | 0.373 | 49.0 |
| IsolationForest|phys|dedup | 6.75 | 2.19 | 0.373 | 49.0 |
| AutoEncoder|phys|dedup | 6.75 | 2.19 | 0.373 | 49.0 |
| AutoEncoder|raw|all | 6.75 | 2.19 | 0.373 | 49.0 |
| AutoEncoder|raw|dedup | 6.75 | 2.19 | 0.373 | 49.0 |
| RobustMahalanobis|raw|dedup | 6.75 | 2.19 | 0.373 | 49.0 |
| RobustMahalanobis|raw|all | 6.75 | 2.19 | 0.373 | 49.0 |
| RobustMahalanobis|phys|dedup | 6.75 | 2.19 | 0.373 | 49.0 |
| RobustMahalanobis|phys|all | 6.75 | 2.19 | 0.373 | 49.0 |

- MAE_naive = '다른 날 평균 불량률 × 그날 용접 수'. 모델이 이를 못 이기면 센서 이상점수가 일별 불량 수를 설명하지 못한다는 뜻이다.
- 날짜 간 센서 구간이 복제돼 있어(진단 D1) 이 점검의 검정력은 매우 낮다. 건별 성능은 04 주입 벤치마크로 본다.

## 4. 모델 간 일치도 (상위 1% 경보 Jaccard)

| 쌍 | Jaccard |
|---|---|
| SPC vs IsolationForest (raw) | 0.017 |
| SPC vs AutoEncoder (raw) | 1.0 |
| SPC vs RobustMahalanobis (raw) | 1.0 |
| IsolationForest vs AutoEncoder (raw) | 0.017 |
| IsolationForest vs RobustMahalanobis (raw) | 0.017 |
| AutoEncoder vs RobustMahalanobis (raw) | 1.0 |
| SPC vs IsolationForest (phys) | 0.072 |
| SPC vs AutoEncoder (phys) | 1.0 |
| SPC vs RobustMahalanobis (phys) | 1.0 |
| IsolationForest vs AutoEncoder (phys) | 0.072 |
| IsolationForest vs RobustMahalanobis (phys) | 0.072 |
| AutoEncoder vs RobustMahalanobis (phys) | 1.0 |

## 5. 상위 1% 경보가 몰리는 곳 (오경보 후보)

| model | high_force_block | copy_boundary | high_current_stepper_zone |
|---|---|---|---|
| SPC|raw|dedup | 1.0 | 0.0 | 0.133 |
| IsolationForest|raw|dedup | 0.839 | 0.0 | 0.935 |
| AutoEncoder|raw|dedup | 1.0 | 0.0 | 0.133 |
| RobustMahalanobis|raw|dedup | 1.0 | 0.0 | 0.133 |
| SPC|phys|dedup | 1.0 | 0.0 | 0.133 |
| IsolationForest|phys|dedup | 0.667 | 0.0 | 0.933 |
| AutoEncoder|phys|dedup | 1.0 | 0.0 | 0.133 |
| RobustMahalanobis|phys|dedup | 1.0 | 0.0 | 0.133 |

기준 비율: {'high_force_block': 0.081, 'copy_boundary': 0.001, 'high_current_stepper_zone': 0.079}

- 고가압력 블록이 전체의 8%인데 경보의 대부분을 차지한다면, 베이스라인은 '평소와 다른 운전 조건'을 이상으로 잡고 있는 것이다. 이것이 불량인지는 라벨로 확인할 수 없다(해당 날짜 불량 4~8건으로 평범 — 진단 D2).
