"""4단계(선택): E3 시간순 5창의 정상 평가 기록(300기록)에서 상수 격자별 정상 오경보 기록 수(정상 전용).

13_r2_oos_alpha.py와 같은 창·같은 계산: 창마다 공식 04.fit_split으로 v2를 다시 적합(결정적)하고, 13.rows_multi·record_alerts로
v2·v2+R2·v2+R1·v2+R1+R2의 정상 경보 기록을 센다. 상수는 lib 전역(GAP_S·CONFIRM_ROWS·R2_MIN_LEN)과 fin.r2_ref(R2_Q·R2_MIN_LEN으로 다시 계산)로 바꾼다.
공식 상수에서는 13의 A_per_fold(rolling 5창 all|·keep|)와 같아야 한다. 탐지는 보지 않는다.
출력: outputs/e3_grid_per_window.csv, e3_grid_pooled.csv, e3_summary.json, checks_e3.json
실행: PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python run_e3.py
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

import sens_common as C

OUT = C.OUT
TIME_BUDGET_S = 20 * 60


def main():
    t0 = time.time()
    S13 = C.load_module("tvt_s13_sens", "13_r2_oos_alpha.py")   # 13이 04(tvt_v04)·10을 함께 불러온다
    V04 = S13.V04
    vis = {"13.prefix_r2 is lib.prefix_r2": S13.prefix_r2 is C.lib.prefix_r2,
           "04.stream_rules is lib.stream_rules": V04.stream_rules is C.lib.stream_rules,
           "04.prefix_r2 is lib.prefix_r2": V04.prefix_r2 is C.lib.prefix_r2}
    M = C.setup_official()
    D = M["D"]
    normal, _, _ = D.load(C.COPY / "yejun" / "press_submission")
    seg_all, fold_masks = S13.folds(normal, D)
    official = json.loads((C.TVT / "outputs" / "r2_oos_alpha.json").read_text(encoding="utf-8"))
    off_fold = pd.DataFrame(official["A_per_fold"])
    rows, ref_rows = [], []
    for name, (tr, ca, te) in fold_masks.items():
        if not name.startswith("rolling"):
            continue
        train = normal[tr].reset_index(drop=True)
        fin = V04.fit_split(M, train, normal[ca].reset_index(drop=True))
        r2_official = fin.r2_ref
        q = D.quantize(D.inputs_only(train), "matched")
        _, seg = M["guard"].layout(train)
        cur = q[D.SENSORS[2]].to_numpy(float)
        refs = C.r2_refs({m: C.prefix_r2_with(m, cur, seg) for m in C.GRID["R2_MIN_LEN"]})
        vis[f"{name}: r2_ref(0.005, 8) == 04.fit_split"] = refs[(0.005, 8)] == r2_official
        ev = normal[te].reset_index(drop=True)
        rec_ids = list(pd.unique(seg_all[te]))
        keep = [k for k in rec_ids if k not in S13.EXCLUDE]
        for (qv, m), r2ref in refs.items():
            ref_rows.append(dict(fold=name, R2_Q=qv, R2_MIN_LEN=m, r2_ref=r2ref))
            fin.r2_ref = r2ref
            with C.lib_constants(min_len=m):
                rm = S13.rows_multi(fin, ev, C.ALPHAS)
            for g in C.GRID["GAP_S"]:
                for c in C.GRID["CONFIRM_ROWS"]:
                    with C.lib_constants(gap=g, confirm=c):
                        for a, r in rm.items():
                            al = S13.record_alerts(r, rec_ids)
                            rows.append(dict(fold=name, GAP_S=float(g), CONFIRM_ROWS=int(c), R2_Q=float(qv), R2_MIN_LEN=int(m), alpha=a,
                                             r2_ref=r2ref, n_all=len(rec_ids), n_keep=len(keep),
                                             **{f"all|{v}": int(sum(al[v][k] for k in rec_ids)) for v in S13.VARIANTS},
                                             **{f"keep|{v}": int(sum(al[v][k] for k in keep)) for v in S13.VARIANTS}))
        fin.r2_ref = r2_official
        print(name, f"{time.time() - t0:.0f}초", flush=True)
    per = pd.DataFrame(rows)
    per["official"] = [all(r[k] == C.OFFICIAL[k] for k in C.KEYS) for _, r in per.iterrows()]
    per.to_csv(OUT / "e3_grid_per_window.csv", index=False)
    pd.DataFrame(ref_rows).to_csv(OUT / "e3_r2_ref.csv", index=False)

    # ---- 공식 상수 재현: 13 A_per_fold
    mism, checked = [], 0
    cols = [f"{p}|{v}" for p in ("all", "keep") for v in S13.VARIANTS] + ["n_all", "n_keep"]
    for _, r in per[per.official].iterrows():
        o = off_fold[(off_fold.fold == r.fold) & np.isclose(off_fold.alpha, r.alpha)]
        assert len(o) == 1
        for col in cols:
            checked += 1
            if int(o.iloc[0][col]) != int(r[col]):
                mism.append(dict(fold=r.fold, alpha=r.alpha, column=col, official=int(o.iloc[0][col]), got=int(r[col])))
    checks = dict(patch_visibility=vis, official_13_reproduction=dict(checked=checked, mismatches=mism, ok=not mism))
    checks["all_ok"] = bool(all(vis.values()) and not mism)
    C.dump(checks, OUT / "checks_e3.json")
    if not checks["all_ok"]:
        raise SystemExit("E3 공식 재현 실패: outputs/checks_e3.json")

    keys = list(C.KEYS)
    pooled = per.groupby(keys + ["alpha"], as_index=False)[[c for c in per.columns if "|" in c] + ["n_all", "n_keep"]].sum()
    pooled["official"] = [all(r[k] == C.OFFICIAL[k] for k in C.KEYS) for _, r in pooled.iterrows()]
    assert (pooled.n_all == 300).all() and (pooled.n_keep == 288).all()
    pooled.to_csv(OUT / "e3_grid_pooled.csv", index=False)

    summ = {}
    for a in C.ALPHAS:
        sub = pooled[np.isclose(pooled.alpha, a)]
        off = sub[sub.official].iloc[0]
        d = {}
        for v in S13.VARIANTS:
            for p, n in (("all", 300), ("keep", 288)):
                x = sub[f"{p}|{v}"]
                d[f"{p}|{v}"] = dict(n_records=n, min=int(x.min()), median=float(x.median()), max=int(x.max()), official=int(off[f"{p}|{v}"]),
                                     rate_min=round(x.min() / n, 4), rate_max=round(x.max() / n, 4), rate_official=round(off[f"{p}|{v}"] / n, 4),
                                     n_points_differ=int((x != off[f"{p}|{v}"]).sum()),
                                     main_effects={k: {str(lv): float(val) for lv, val in sub.groupby(k)[f"{p}|{v}"].mean().items()} for k in keys})
                me = {k: max(d[f"{p}|{v}"]["main_effects"][k].values()) - min(d[f"{p}|{v}"]["main_effects"][k].values()) for k in keys}
                d[f"{p}|{v}"]["main_effect_range"] = me
                d[f"{p}|{v}"]["largest_main_effect"] = max(me, key=me.get) if max(me.values()) > 0 else None
        summ[str(a)] = d
    elapsed = time.time() - t0
    out = dict(windows=[n for n in fold_masks if n.startswith("rolling")], n_records_all=300, n_records_keep=288,
               excluded_records=sorted(S13.EXCLUDE), note="정상 전용. 평가 300기록은 분할 B valid+test와 같은 기록이며 창마다 v2를 다시 적합했다.",
               variants=dict(zip(S13.VARIANTS, ("v2", "v2+R2", "v2+R1 (1단계)", "v2+R1+R2 (2단계)"))),
               summary=summ, seconds=round(elapsed, 1), within_time_budget=elapsed <= TIME_BUDGET_S)
    C.dump(out, OUT / "e3_summary.json")
    for a in C.ALPHAS:
        print(a, {k: (summ[str(a)][f"all|{k}"]["min"], summ[str(a)][f"all|{k}"]["official"], summ[str(a)][f"all|{k}"]["max"]) for k in S13.VARIANTS})
    print(f"완료 {elapsed:.0f}초")


if __name__ == "__main__":
    main()
