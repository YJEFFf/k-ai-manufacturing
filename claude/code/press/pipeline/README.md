# ③ 프레스 제출 파이프라인

```bash
pip install -r code/press/pipeline/requirements.txt
# data/3_소성가공_예지보전/ 에 press_data_normal.csv, outlier_data.csv 를 둔다 (SHA-256은 data/README.md)
python code/press/pipeline/run_all.py        # 약 40초. 산출: code/press/outputs/pipeline/
```

확인 환경: Python 3.13.15, numpy 2.5.2, pandas 3.0.5, scikit-learn 1.9.1, matplotlib 3.11.1. `OMP_NUM_THREADS=1`을 스크립트가 고정한다.

## 흐름

| 단계 | 파일 | 하는 일 |
|---|---|---|
| 데이터 | `data.py` | 로드, 경로(`--root`), 예준 평가 헬퍼 vendor 사본 import (sha256·SPLITS·BUDGETS assert) |
| 창 길이 | `select_w.py` | 정상 데이터만으로 사인 창 길이 선택 (학습-A로 ECDF, 보정 구간으로 문턱, 학습-B에서 알림 비율 최소) |
| 점수 | `scores.py` | max-z, 5NN, RMS5, Isolation Forest, AE(5관측 창 MLP), 사인 1−R², **결합(max-z + 사인)**. 전부 정상 학습 구간으로만 적합 |
| 평가 | `evaluate.py` | 예준 평가 루프 복제(2분할 × 행/구간 보정 × 1·3·5% 예산) + 구간 단위 conformal p값 |
| 예측 | `run_all.py` | `predictions_test.csv` (라벨 없는 입력 스트림으로 추론), 수용 검사 |
| 오류 | `analysis.py` | 영향요인(경보 사유·센서·단변량 AUROC), FN·FP 조건, 그림 2장 |
| 진단 | `diagnosis.py` | 구조·형식 누수·전류 파형 진단 문서, 그림 2장 (형식 누수 감사는 `../05_requantize_audit.py`를 vendor 사본으로 실행) |

## 산출물 (`code/press/outputs/pipeline/`)

| 파일 | 내용 |
|---|---|
| `model_comparison.csv/.md` | 모델 × 분할 × 보정단위 × 예산 전 지표 |
| `predictions_test.csv` | 평가 행별 점수·p값·경보·경보 사유 (아래 참고) |
| `w_selection.csv` | 창 길이 규칙 후보별 결과 |
| `influence.csv`, `error_conditions.csv`, `segment_features.csv` | 영향요인·FN/FP 조건 |
| `diagnosis.md` | 데이터 진단 |
| `checks.json`, `conformal_unit_test.csv` | 수용 검사 결과 |
| `fig_*.png` | 그림 4장 |

## 예측 파일에 대해

- **공식 테스트셋이 없어 자체 평가셋이다.** 분할마다 정상 평가 구간 + 이상 600행 전체. 이상 600행은 두 분할이 공유하고, 결합 구조(max-z + 사인)를 떠올릴 때 이미 본 데이터다
- `p_value`는 **정상 이탈 p값**(정상 보정 구간 최댓값 분포 기준 conformal)이다. `anomaly_score = 1 − p_value`는 이상일 사후확률이 아니다. 오경보 상한은 기록구간 단위에서만 주장한다
- `alarm`은 예준 문턱(`cutoff_at_budget`, 1% 구간 예산), `conformal_alarm`은 `p ≤ 0.01`. 결합 모델에서는 두 열이 같은 구간을 고른다. 표본이 작을 때 conformal 쪽이 더 보수적이다(`conformal_unit_test.csv`)
- `source`는 출력용 메타데이터다. 추론 입력은 TimeStamp + 센서 3열뿐이며, 기록구간 순서를 섞어도 결과가 같음을 검사한다
