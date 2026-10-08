"""11단계(사후, test 채점 이후): 보고서에 쓴 사후 수치 몇 개를 다시 만든다(선택·잠금·최종 선정에 쓰지 않음).

- max|z|+R1+R2(2.7절 R1 표, 사후): max|z|는 크기 성분뿐이라 R2는 '전류 파형(기록 첫 행부터의 사인 적합 R²)이 정상이면 보류'가 된다.
  evalcore의 채점을 그대로 쓰고 자기 경보만 이 규칙으로 바꾼다. α 1·5%의 valid·test 실시간 F1·오경보·미탐 행
- 이상 확률(2.5절): 제출 예측 파일의 두 확률 열로 test 행 AUROC·PR-AUC와 구간(0·0.01·0.1·0.5·0.9·1)별 ECE
- 수집 공백(4.3절): 정상 파일에서 이웃 행 간격이 0.15초를 넘는 곳의 길이 중앙값·90% 분위
출력: outputs/posthoc_numbers.json
실행(제출본 루트에서): python code/press/tvt/11_posthoc_numbers.py --repo .
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

import evalcore
from lib import CACHE, OUT, SPLITS, repo_arg, setup

_orig = evalcore.own_alarm


def _own_maxz_r2(table, mask, base, alpha, regime, h2, r2_ref):
    """max|z|에 R2를 붙일 때: 크기 성분뿐이므로 전류 파형이 정상인 경보를 모두 보류한다."""
    if base == "maxz3" and h2:
        a = _orig(table, mask, base, alpha, regime, False, r2_ref)
        return a & ~(table.loc[mask, "prefix_r2"].to_numpy() >= r2_ref)
    return _orig(table, mask, base, alpha, regime, h2, r2_ref)


def maxz_rules():
    evalcore.own_alarm = _own_maxz_r2
    meta = json.loads((OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    out = {}
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl")
        r2, cx = meta[s]["r2_ref"], meta[s]["complexity"]
        for name, h1, h2 in (("maxz3+H1+H2", True, True), ("v2+H1+H2", True, True)):
            base = name.split("+")[0]
            cand = (name, base, h1, h2, False, cx[base] + h1 + h2)
            for alpha in (0.01, 0.05):
                te = evalcore.evaluate(t, cand, alpha, "test", r2)["realtime"]
                va = evalcore.evaluate(t, cand, alpha, "valid", r2)["realtime"]
                out[f"{s}|{name}|{alpha}"] = dict(test_f1=float(te["f1"]), test_fp=int(te["fp"]), test_fn=int(te["fn"]),
                                                  valid_f1=float(va["f1"]), valid_fp=int(va["fp"]), valid_fn=int(va["fn"]))
    evalcore.own_alarm = _orig
    return out


def probability():
    out = {}
    bins = [0, 0.01, 0.1, 0.5, 0.9, 1.0000001]
    for s in SPLITS:
        d = pd.read_csv(OUT / f"test_predictions_{s}.csv")
        y = (d["label"] == 1).to_numpy()
        for col in ("v2_prob_fileprior", "v2_prob_site1pct"):
            p = d[col].to_numpy(float)
            idx = np.digitize(p, bins) - 1
            ece = sum(abs(p[idx == k].mean() - y[idx == k].mean()) * (idx == k).mean() for k in range(5) if (idx == k).any())
            out[f"{s}|{col}"] = dict(auroc=float(roc_auc_score(y, p)), prauc=float(average_precision_score(y, p)), ece=float(ece))
    return out


def gaps(repo):
    M = setup(repo)
    normal, _, _ = M["D"].load(repo / "yejun/press_submission")
    ts = pd.to_datetime(normal["TimeStamp"]).sort_values().to_numpy()
    dt = np.diff(ts).astype("timedelta64[ms]").astype(float) / 1000
    g = dt[dt > 0.15]
    return dict(n=int(len(g)), median_s=float(np.median(g)), p90_s=float(np.quantile(g, 0.9)), max_s=float(g.max()))


def main():
    repo = repo_arg()
    res = dict(maxz_rules=maxz_rules(), probability=probability(), gaps=gaps(repo))
    (OUT / "posthoc_numbers.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
