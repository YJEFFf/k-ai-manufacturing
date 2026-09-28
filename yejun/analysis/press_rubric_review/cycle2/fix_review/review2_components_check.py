#!/usr/bin/env python
"""review2 — 위치별 성분 유무(결과 파일 열만 사용, 팀 모듈 import 없음)."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
R = Path(sys.argv[1])
for s in "AB":
    v2 = pd.read_csv(R / f"yejun/press_guard/outputs/test_predictions_{s}.csv")
    v1 = pd.read_csv(R / f"yejun/press_submission/outputs/predictions_{s}.csv")
    for lo, hi in [(0, 1), (2, 4), (5, 6), (7, 999)]:
        m2 = v2.position.between(lo, hi); m1 = v1.position_in_record.between(lo, hi)
        print(f"{s} 위치 {lo}~{hi if hi<999 else '끝'}: v2 g_waveform 있음 {int(v2.loc[m2,'g_waveform'].notna().sum())}/{int(m2.sum())}, "
              f"g_dynamics 있음 {int(v2.loc[m2,'g_dynamics'].notna().sum())}/{int(m2.sum())}, 창 {sorted(v2.loc[m2,'waveform_window'].dropna().unique().tolist())} | "
              f"v1 g_sine 있음 {int(v1.loc[m1,'g_sine'].notna().sum())}/{int(m1.sum())}")
    # v2 개선 행(α 1%)이 어느 성분에서 문턱을 넘었는지
    fixed = (v2.label == 1) & (v2.alarm == 1) & (v1.alarm == 0)
    print(f"{s} v1 미탐→v2 탐지 {int(fixed.sum())}행의 reason 분포:", v2.loc[fixed, 'reason'].value_counts().to_dict())
    # 단순 비교: v1 점수와 v2 크기 성분
    d = (v2.g_magnitude - v1.g_maxz3).abs().max()
    print(f"{s} v2 g_magnitude vs v1 g_maxz3 최대 |차| {d:.2e}")
