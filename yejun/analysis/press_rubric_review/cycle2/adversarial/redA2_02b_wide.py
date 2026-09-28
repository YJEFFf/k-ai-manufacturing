"""redA2_02_hyper_grid.csv(α=1%)를 설정당 한 행(A·B 열)으로 펴고, 팀 선택 규칙 아래 v2의 순위를 센다.
redA2_03_nested_hyper.py의 입력(redA2_02_hyper_grid_wide.csv)을 만든다. 출력: redA2_02b_wide.json"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
g = pd.read_csv(H / "redA2_02_hyper_grid.csv")
g1 = g[np.isclose(g.alpha, .01)]
w = g1.pivot_table(index=["config", "w_late", "w_early", "ar_order", "q", "rule"], columns="split",
                   values=["fn", "normal_alerted", "abnormal_detected", "delay_max_s", "fp", "tails_ok"]).reset_index()
w.columns = ["_".join([str(x) for x in c if x != ""]) for c in w.columns]
w["fn_sum"] = w.fn_A + w.fn_B
w["eligible"] = (w.normal_alerted_A <= 0) & (w.normal_alerted_B <= 3) & (w.abnormal_detected_A == 21) & (w.abnormal_detected_B == 21)
target = H / "redA2_02_hyper_grid_wide.csv"
if "--check" in sys.argv and target.is_file():
    tmp = H / "redA2_02b_wide_check.tmp.csv"
    w.to_csv(tmp, index=False)
    same = hashlib.sha256(tmp.read_bytes()).hexdigest() == hashlib.sha256(target.read_bytes()).hexdigest()
    tmp.unlink()
    print("기존 wide 표와 바이트 일치:", same)
else:
    w.to_csv(target, index=False)
v2 = w.config.eq("wl8_we6_sw7_ar2_q0.95_fmax_u50")
e = w[w.eligible]
ef = e[e.rule.eq("fmax")]
dom = w[(w.fn_A <= 44) & (w.fn_B <= 31) & (w.normal_alerted_A <= 0) & (w.normal_alerted_B <= 3) & ((w.fn_A < 44) | (w.fn_B < 31) | (w.normal_alerted_B < 3))]
out = dict(configs=len(w), eligible=int(len(e)), v2_fn_sum=int(w[v2].fn_sum.iloc[0]),
           v2_rank_eligible=int((e.fn_sum < 75).sum()) + 1, ties_at_75=int((e.fn_sum == 75).sum()), best_eligible_fn_sum=int(e.fn_sum.min()),
           v2_rank_fmax_eligible=int((ef.fn_sum < 75).sum()) + 1, fmax_eligible=int(len(ef)), best_fmax_fn_sum=int(ef.fn_sum.min()),
           configs_dominating_v2=int(len(dom)), dominating_by_rule=dom.rule.value_counts().to_dict(),
           eligible_fn_sum_quantiles={str(q): float(e.fn_sum.quantile(q)) for q in (0, .1, .25, .5, .75, 1)})
(H / "redA2_02b_wide.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False))
