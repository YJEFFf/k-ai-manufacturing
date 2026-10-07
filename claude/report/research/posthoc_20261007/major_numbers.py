"""MAJOR 반영에 쓸 수치 계산(사후, 선택에 쓰지 않음).
1) max|z|+R1+R2 (max|z|는 크기 성분뿐이라 R2 = 전류 파형 정상이면 보류)
2) 이상 확률(파일 비율) AUROC·PR-AUC·ECE
3) 정상 파일 수집 공백 중앙값·90% 분위
4) valid 오경보 기록 수(LOO 보정 구조)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\jacob\Documents\Obsidian Vault\대회\제조데이터_경진대회")
TVT = ROOT / "code/press/tvt"
sys.path.insert(0, str(TVT))
import evalcore  # noqa: E402
from lib import PRIMARY_ALPHA  # noqa: E402

out = {}
orig = evalcore.own_alarm


def own2(table, mask, base, alpha, regime, h2, r2_ref):
    if base == "maxz3" and h2:
        a = orig(table, mask, base, alpha, regime, False, r2_ref)
        return a & ~(table.loc[mask, "prefix_r2"].to_numpy() >= r2_ref)
    return orig(table, mask, base, alpha, regime, h2, r2_ref)


evalcore.own_alarm = own2
meta = json.loads((TVT / "outputs/tvt_scores_meta.json").read_text(encoding="utf-8"))
for s in ("A", "B"):
    t = pd.read_pickle(TVT / f"cache/rows_{s}.pkl")
    r2 = meta[s]["r2_ref"]
    cx = meta[s]["complexity"]
    for name, h1, h2 in (("maxz3", False, False), ("maxz3+H2", False, True), ("maxz3+H1", True, False), ("maxz3+H1+H2", True, True), ("v2+H1+H2", True, True)):
        base = name.split("+")[0]
        cand = (name, base, h1, h2, False, cx[base] + h1 + h2)
        for alpha in (0.01, 0.05):
            te = evalcore.evaluate(t, cand, alpha, "test", r2)["realtime"]
            va = evalcore.evaluate(t, cand, alpha, "valid", r2)["realtime"]
            out[f"{s}|{name}|{alpha}"] = dict(test_f1=round(te["f1"], 4), test_fp=int(te["fp"]), test_fn=int(te["fn"]),
                                               valid_f1=round(va["f1"], 4), valid_fp=int(va["fp"]), valid_fn=int(va["fn"]))

# 2) 확률
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
for s in ("A", "B"):
    d = pd.read_csv(TVT / f"outputs/test_predictions_{s}.csv")
    y = (d["label"] == 1).to_numpy()
    for col in ("v2_prob_fileprior", "v2_prob_site1pct"):
        p = d[col].to_numpy()
        bins = [0, 0.01, 0.1, 0.5, 0.9, 1.0000001]
        idx = np.digitize(p, bins) - 1
        ece = sum(abs(p[idx == k].mean() - y[idx == k].mean()) * (idx == k).mean() for k in range(5) if (idx == k).any())
        out[f"prob|{s}|{col}"] = dict(auroc=round(roc_auc_score(y, p), 4), prauc=round(average_precision_score(y, p), 4), ece=round(float(ece), 4),
                                      n=len(p), max=round(float(p.max()), 4))

# 3) 수집 공백
n = pd.read_csv(ROOT / "data/3_소성가공_예지보전/press_data_normal.csv")
ts = pd.to_datetime(n["TimeStamp"]).sort_values().to_numpy()
dt = np.diff(ts).astype("timedelta64[ms]").astype(float) / 1000
gaps = dt[dt > 0.15]
out["gap"] = dict(n=int(len(gaps)), median=round(float(np.median(gaps)), 2), p90=round(float(np.quantile(gaps, 0.9)), 2),
                  max=round(float(gaps.max()), 2))

# 4) valid 오경보 기록 수
rc = pd.read_csv(TVT / "outputs/tvt_record_count.csv")
out["valid_rec_fp"] = rc.query("part == 'valid'")[[c for c in rc.columns if c in ("split", "model", "alpha", "rec_fp")]].to_dict("records") if "part" in rc.columns else rc.columns.tolist()
json.dump(out, open(Path(__file__).with_suffix(".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "valid_rec_fp"}, ensure_ascii=False, indent=1))
print(str(out["valid_rec_fp"])[:1500])
