#!/usr/bin/env python
"""review2 — A 문턱 항목 전용. 팀 모듈 사용은 이 스크립트 하나로 한정한다(지시로 허용된 유일한 항목).

저장소가 아니라 rsync 사본(<copy>/press_guard, <copy>/press_submission)에서 실행한다.
출력: 보정·평가 구간을 저장 모델로 predict한 기록별 최대 점수 CSV(분할별)와 대조 로그.
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review2_threshold_model.py --copy <사본 폴더> --out <출력 폴더>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--copy", required=True)
ap.add_argument("--out", required=True)
args = ap.parse_args()
C = Path(args.copy); O = Path(args.out)
sys.path.insert(0, str(C / "press_guard"))
from model import load_bundle  # noqa: E402  (허용된 유일한 팀 모듈 사용)

raw_path = C / "press_submission/data/3_소성가공_예지보전/press_data_normal.csv"
print("원본 SHA-256:", hashlib.sha256(raw_path.read_bytes()).hexdigest())
nor = pd.read_csv(raw_path)
t = pd.to_datetime(nor.TimeStamp)
new = t.diff().dt.total_seconds().sub(0.1).abs().gt(1e-6).fillna(False).to_numpy()
nrec = np.cumsum(new)
COLS = ["TimeStamp", "AI0_Vibration", "AI1_Vibration", "AI2_Current"]
SPLITS = {"A": (360, 480), "B": (300, 420)}

for s, (tr, ca) in SPLITS.items():
    mpath = C / f"press_guard/artifacts/guard_{s}.json"
    print(f"\n[{s}] 모델 {mpath.name} SHA-256 {hashlib.sha256(mpath.read_bytes()).hexdigest()}")
    model = load_bundle(mpath)
    saved_cal = np.sort(np.asarray(json.loads(mpath.read_text(encoding='utf-8'))["state"]["calibration"], float))
    for part, (r0, r1) in {"cal": (tr, ca), "test": (ca, 600)}.items():
        m = (nrec >= r0) & (nrec < r1)
        frame = nor.loc[m, COLS].reset_index(drop=True)
        pred = model.predict(frame, alpha=0.01)
        absrec = nrec[m]
        assert (pred.record_id.to_numpy() + r0 == absrec).all(), "기록 번호 대응 실패"
        rm = pd.DataFrame({"abs_record": absrec, "score": pred.score.to_numpy()}).groupby("abs_record").score.max()
        rm.rename("record_max").to_csv(O / f"review2_{part}_record_max_{s}.csv")
        if part == "cal":
            same = np.allclose(np.sort(rm.to_numpy()), saved_cal, rtol=0, atol=1e-12)
            print(f"  보정 {r0}~{r1-1}: 기록 {len(rm)}개, 저장 모델 calibration 배열과 정렬 후 일치(atol 1e-12): {same}; "
                  f"최대 |차| {np.abs(np.sort(rm.to_numpy()) - saved_cal).max():.2e}")
            top = rm.sort_values(ascending=False).head(5)
            print("  보정 기록 최대 점수 상위 5:", "; ".join(f"기록 {int(k)}={v:.6f}" for k, v in top.items()))
        else:
            ref = pd.read_csv(C / f"press_guard/outputs/test_predictions_{s}.csv")
            ref = ref[ref.subset == "normal_test"]
            d = np.abs(ref.score.to_numpy() - pred.score.to_numpy())
            print(f"  평가 {r0}~{r1-1}: 사본 test_predictions_{s}.csv 정상 행 점수와 최대 |차| {d.max():.2e}, "
                  f"경보 일치 {bool((ref.alarm.to_numpy() == pred.alarm.to_numpy()).all())}")
