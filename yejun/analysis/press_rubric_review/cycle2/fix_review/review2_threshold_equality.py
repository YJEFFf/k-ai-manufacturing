#!/usr/bin/env python
"""review2 — v1 α 1% 문턱(v1 예측 파일 threshold 열)과 v2 저장 모델 보정 최대값 비교. JSON은 자료로만 읽는다(팀 모듈 import 없음).
실행: python review2_threshold_equality.py <루트(예측 CSV)> <guard_*.json 폴더>"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
R, M = Path(sys.argv[1]), Path(sys.argv[2])
for s in "AB":
    v1 = pd.read_csv(R / f"yejun/press_submission/outputs/predictions_{s}.csv", usecols=["threshold"])
    t1 = float(v1.threshold.unique()[0])
    cal = np.asarray(json.loads((M / f"guard_{s}.json").read_text(encoding="utf-8"))["state"]["calibration"], float)
    print(f"{s}: v1 α1% 문턱 {t1!r} | v2 보정 최대 {cal.max()!r} | 차 {cal.max()-t1:.3e}")
