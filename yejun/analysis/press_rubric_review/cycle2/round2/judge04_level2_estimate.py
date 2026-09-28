"""평가관 04 cycle2 round2: 2단계(점검 요청) 교대 알림 수의 근거가 얼마나 되는지 센다(R2-02 근거).

입력은 커밋된 alert_levels_v2.csv다. 이 표는 judge04_r2_check.py가 원본 재학습 모델로 42행을 독립 계산해 모두 일치를 확인했다.
  1) 0건 관측의 단측 95% 상한을 교대 8시간으로 환산: 표본 수만으로 정해지는 값
  2) 독립 폴드(동결 A·B와 보정값이 다른 300~359·360~419·540~599)의 1단계 → 2단계 정상 알림과 그 비
  3) [평가관 가정] 비가 α와 무관하다고 두고 B α1% 1단계 명목(교대 29.6건)에 곱한 2단계 추정 예시. 사후 규칙 선택과 무관한 자료만 쓴다
실행(yejun/에서): OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python analysis/press_rubric_review/cycle2/round2/judge04_level2_estimate.py
쓰는 파일: 이 폴더의 judge04_level2_estimate.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
lv = pd.read_csv(YEJUN / "press_guard" / "outputs" / "alert_levels_v2.csv")
b1 = lv[(lv.model == "frozen_B") & np.isclose(lv.alpha, .01)].set_index("level")
nominal_l1 = float(b1.loc[1, "nominal_alerts_per_8h_elapsed"])
units_per_8h = nominal_l1 / (np.floor(.01 * 121 + 1e-9) / 121)     # 명목 = (⌊α·121⌋/121) × 교대당 알림 단위 수
out = dict(source="press_guard/outputs/alert_levels_v2.csv", nominal_level1_per_8h_B_a1=nominal_l1, units_per_8h_B=units_per_8h)
out["zero_count_upper95_per_8h"] = {str(n): float((1 - .05 ** (1 / n)) * units_per_8h) for n in (60, 120, 180, 300, 600)}
indep = ["rolling_test_300_359", "rolling_test_360_419", "rolling_test_540_599"]
folds = {}
for a in (.01, .03, .05):
    g = lv[lv.model.isin(indep) & np.isclose(lv.alpha, a)]
    k1 = int(g[g.level == 1].normal_alerted_segments.sum())
    k2 = int(g[g.level == 2].normal_alerted_segments.sum())
    row = dict(level1=k1, level2=k2, units=int(g[g.level == 1].normal_segments.sum()),
               per_fold={m: (int(g[(g.model == m) & (g.level == 1)].normal_alerted_segments.iloc[0]),
                             int(g[(g.model == m) & (g.level == 2)].normal_alerted_segments.iloc[0])) for m in indep})
    if k1:
        ratio, up = k2 / k1, float(stats.beta.ppf(.95, k2 + 1, k1 - k2)) if k2 < k1 else 1.0
        row.update(ratio_l2_over_l1=ratio, ratio_upper95=up,
                   example_level2_per_8h_B_a1=nominal_l1 * ratio, example_level2_upper95_per_8h_B_a1=nominal_l1 * up)
    folds[f"alpha_{a}"] = row
out["independent_folds"] = folds
out["note"] = ("예시 추정은 '2단계/1단계 비가 α에 무관'이라는 평가관 가정에 기댄다. α 1%의 독립 폴드는 1단계 알림이 0건이라 비를 줄 수 없다. "
               "사후 규칙 선택(평가관 04 1회차 관찰)과 무관한 자료는 독립 폴드 180단위뿐이다")
(HERE / "judge04_level2_estimate.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
