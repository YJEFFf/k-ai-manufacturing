"""10단계(사후, test 채점 이후): 문턱과 무관한 비교와 기록 단위 부트스트랩 구간(보고서 2.4절, 사후). 선택·잠금·최종 선정에는 쓰지 않는다.

- 행 AUROC·PR-AUC: test 정상·이상 행의 R1 없는 점수(01이 만든 행 표의 '|score'). 창이 차지 않아 점수가 없는 행은 가장 정상으로 둔다
- 부트스트랩: test 기록을 정상·이상 묶음 안에서 복원 추출(2,000회, seed 0)해 R1 없는 실시간 행 F1(α 1%)과 AUROC의
  v2 − 비교 모델 차이의 95% 구간을 낸다. 이상 기록은 한 사건의 11기록이라 사건 단위 표본은 1이다(구간은 이 사건 안의 흔들림)
- 확인: 부트스트랩 전 F1은 03의 tvt_test.csv(실시간, α 1%)와 같아야 한다
출력: outputs/threshold_free.csv, outputs/threshold_free_boot.csv
실행: python code/press/tvt/10_threshold_free.py
"""
import math

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from lib import CACHE, OUT, PRIMARY_ALPHA, SPLITS

MODELS = ["maxz3", "iforest", "knn5", "mlp_ae5", "lstm20", "v1", "v2"]
N_BOOT = 2000


def f1(y, a):
    tp = int((y & a).sum()); fp = int((~y & a).sum()); fn = int((y & ~a).sum())
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def main():
    ref = pd.read_csv(OUT / "tvt_test.csv").query("mode == 'realtime' and alpha == @PRIMARY_ALPHA")
    rows, boot_rows = [], []
    rng = np.random.default_rng(0)
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl").query("part == 'test'").reset_index(drop=True)
        y = (t.label == 1).to_numpy()
        score = {m: np.nan_to_num(t[f"{m}|score"].to_numpy(float), nan=-np.inf, neginf=-np.inf) for m in MODELS}
        alarm = {m: np.isfinite(t[f"{m}|p_full"].to_numpy(float)) & (t[f"{m}|p_full"].to_numpy(float) <= PRIMARY_ALPHA) for m in MODELS}
        for m in MODELS:
            sc = np.where(np.isfinite(score[m]), score[m], np.nanmin(score[m][np.isfinite(score[m])]) - 1)
            r = dict(split=s, model=m, auroc=roc_auc_score(y, sc), prauc=average_precision_score(y, sc), f1=f1(y, alarm[m]))
            chk = ref.query("split == @s and model == @m").f1
            if len(chk) != 1 or not math.isclose(r["f1"], float(chk.iloc[0]), abs_tol=1e-9):
                raise SystemExit(f"F1이 tvt_test.csv와 다름: {s} {m}")
            rows.append(r)
        # 기록 단위 부트스트랩(정상·이상 묶음 안에서 복원 추출)
        key = t.subset + ":" + t.rec.astype(str)
        groups = {g: np.flatnonzero(key.to_numpy() == g) for g in pd.unique(key)}
        norm = [g for g in groups if g.startswith("normal")]
        abn = [g for g in groups if g.startswith("abnormal")]
        sc_fix = {m: np.where(np.isfinite(score[m]), score[m], np.nanmin(score[m][np.isfinite(score[m])]) - 1) for m in MODELS}
        for b in range(N_BOOT):
            pick = np.concatenate([groups[g] for g in rng.choice(norm, len(norm))] + [groups[g] for g in rng.choice(abn, len(abn))])
            yb = y[pick]
            res = {m: (f1(yb, alarm[m][pick]), roc_auc_score(yb, sc_fix[m][pick])) for m in MODELS}
            for m in MODELS:
                if m == "v2":
                    continue
                boot_rows.append(dict(split=s, other=m, b=b, d_f1=res["v2"][0] - res[m][0], d_auroc=res["v2"][1] - res[m][1]))
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "threshold_free.csv", index=False)
    bt = pd.DataFrame(boot_rows)
    ci = bt.groupby(["split", "other"]).agg(d_f1_lo=("d_f1", lambda v: v.quantile(.025)), d_f1_hi=("d_f1", lambda v: v.quantile(.975)),
                                            d_auroc_lo=("d_auroc", lambda v: v.quantile(.025)), d_auroc_hi=("d_auroc", lambda v: v.quantile(.975))).reset_index()
    ci.to_csv(OUT / "threshold_free_boot.csv", index=False)
    pd.set_option("display.width", 200)
    print(out.round(4).to_string(index=False))
    print(ci.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
