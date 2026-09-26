"""총괄(root) 재확인: 2차 평가관 01의 새 지적(D2·D3·D4·D5)을 원본·동결 모델로 독립 계산한다. 읽기 전용."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
from scipy import stats

YEJUN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import GuardModel, D, BASE, layout  # noqa: E402
from press.calibrate import segment_max  # noqa: E402

normal, abnormal, _ = D.load(BASE)
seg_all = D.segments(normal)
out = {}

# D3: 정상 평가 구간의 최대 점수가 보정 중앙값을 넘는 비율(교환가능하면 약 50%)과 시간대
for sid in D.SPLITS:
    m = GuardModel.load(YEJUN / "press_guard" / "artifacts" / f"guard_{sid}.json")
    _, train_end, cal_end = D.SPLITS[sid]
    test = D.quantize(D.inputs_only(normal[seg_all >= cal_end]), "matched")
    sg = layout(test)[1]
    test_max = segment_max(m.components(test, sg)["score"], sg)
    med = float(np.median(m.cal))
    above = int((test_max > med).sum())
    t = pd.to_datetime(normal.TimeStamp)
    out[f"D3_{sid}"] = dict(cal_segments=len(m.cal), test_segments=len(test_max), cal_median=med,
                            test_above_cal_median=above, share=above / len(test_max),
                            binom_two_sided_p=float(stats.binomtest(above, len(test_max), .5).pvalue),
                            mannwhitney_p=float(stats.mannwhitneyu(test_max, m.cal).pvalue),
                            test_window=f"{t[seg_all >= cal_end].iloc[0]:%H:%M}~{t[seg_all >= cal_end].iloc[-1]:%H:%M}",
                            cal_window=f"{t[(seg_all >= train_end) & (seg_all < cal_end)].iloc[0]:%H:%M}~{t[(seg_all >= train_end) & (seg_all < cal_end)].iloc[-1]:%H:%M}")

# 60구간 블록별 진동 수준(정상): 시간대에 따른 '조용함' 확인
blk = pd.DataFrame(dict(block=seg_all // 60, v0=normal.AI0_Vibration.abs(), v1=normal.AI1_Vibration.abs()))
out["D3_block_vibration_abs_mean"] = blk.groupby("block")[["v0", "v1"]].mean().round(4).to_dict(orient="index")

# D4: 진동 lag-1 자기상관(구간 안), 상·하부 진동 상관
def lag1(frame):
    seg = D.segments(frame)
    rows = {}
    for c in D.SENSORS[:2]:
        x = frame[c].to_numpy(float)
        same = seg[1:] == seg[:-1]
        rows[c] = float(np.corrcoef(x[1:][same], x[:-1][same])[0, 1])
    return rows

for name, f in (("normal", normal), ("abnormal", abnormal)):
    q = D.quantize(D.inputs_only(f), "matched")
    out[f"D4_{name}"] = dict(lag1=lag1(q), corr_v0_v1=float(np.corrcoef(q.AI0_Vibration, q.AI1_Vibration)[0, 1]))

# D2: 행 기준 이상 비율, 평가셋 이상 비율, 전부 양성 F1
out["D2_row_share_abnormal"] = len(abnormal) / (len(normal) + len(abnormal))
for sid in D.SPLITS:
    n_test = int((seg_all >= D.SPLITS[sid][2]).sum())
    prev = len(abnormal) / (n_test + len(abnormal))
    out[f"D2_{sid}"] = dict(test_normal_rows=n_test, prevalence=prev, all_positive_f1=2 * prev / (1 + prev))

# D5: 중복 시각
dup = normal[normal.duplicated("TimeStamp", keep=False)]
out["D5_duplicate_timestamps"] = dict(rows=len(dup), full_row_duplicates=int(normal.drop(columns=normal.columns[0]).duplicated(keep=False).sum()),
                                      timestamps=dup.TimeStamp.unique().tolist())

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
Path(__file__).with_suffix(".json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
