"""2단계: 상수 격자(81점) × α(1·3·5%) × 분할 A·B에서 1단계(v2+R1)·2단계(v2+R1+R2)를 공식 평가 함수로 채점한다.

재학습 없음: 점수는 공식 실행 사본의 cache/rows_{A,B}.pkl. 학습 정상 전류는 r2_ref 재계산용으로만 원본 CSV에서 다시 읽는다.
먼저 공식 상수 재현·prefix/r2_ref 재현·패치 가시성을 확인하고, 하나라도 실패하면 멈춘다.
출력: outputs/grid_metrics.csv(긴 표), grid_alpha01_wide.csv, grid_reference_v2.csv, r2_ref_grid.csv,
      grid_distribution.csv, grid_main_effects.csv, grid_oat.csv, grid_summary.json, checks_grid.json
실행: PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python run_grid.py
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

import sens_common as C

OUT = C.OUT


def run_checks(tables, meta, cands, S07, train_pr2):
    checks = dict(
        cache=C.cache_hash_check(),
        official_reproduction=C.official_reproduction(tables, meta, cands, S07,
                                                      {"copy": C.TVT / "outputs", "claude_repo": C.CLAUDE_TVT / "outputs"}),
        prefix_and_r2_ref=C.prefix_and_ref_checks(tables, meta, {s: train_pr2[s][8] for s in C.SPLITS}),
        patch_visibility=C.patch_visibility_checks(tables, meta, cands, S07),
    )
    ok = (all(v["ok"] for v in checks["cache"].values()) and checks["official_reproduction"]["ok"]
          and all(v for k, v in checks["prefix_and_r2_ref"].items() if "==" in k)
          and all(checks["patch_visibility"].values()))
    checks["all_ok"] = bool(ok)
    C.dump(checks, OUT / "checks_grid.json")
    if not ok:
        raise SystemExit("사전 확인 실패: outputs/checks_grid.json")
    return checks


def compute_grid(tables, cands, S07, refs):
    """격자점마다 공식 함수로 지표를 낸다."""
    tm = {(s, m): t.assign(prefix_r2=C.table_prefix(t, m)) for s, t in tables.items() for m in C.GRID["R2_MIN_LEN"]}
    rows = []
    for p in C.grid_points():
        with C.lib_constants(gap=p["GAP_S"], confirm=p["CONFIRM_ROWS"]):
            assert C.lib.GAP_S == p["GAP_S"] and C.lib.CONFIRM_ROWS == p["CONFIRM_ROWS"]
            for s in C.SPLITS:
                r2ref = refs[s][(p["R2_Q"], p["R2_MIN_LEN"])]
                t = tm[(s, p["R2_MIN_LEN"])]
                for a in C.ALPHAS:
                    for variant, name in C.VARIANTS.items():
                        m = C.evaluate_point(t, cands[name], a, r2ref, S07)
                        rows.append(dict(split=s, alpha=a, **p, official=C.is_official(p), variant=variant, model=name, r2_ref=r2ref, **m))
    assert (C.lib.GAP_S, C.lib.CONFIRM_ROWS, C.lib.R2_MIN_LEN) == (60.0, 2, 8)
    return pd.DataFrame(rows)


def reference_v2(tables, meta, cands, S07):
    """규칙 없는 v2(네 상수와 무관) — 분할·α마다 한 번."""
    rows = []
    for s, t in tables.items():
        for a in C.ALPHAS:
            m = C.evaluate_point(t, cands["v2"], a, meta[s]["r2_ref"], S07)
            rows.append(dict(split=s, alpha=a, variant="reference", model="v2", **m))
    return pd.DataFrame(rows)


def wide(g: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """α 하나에서 격자점마다 한 줄: 단계·분할별 핵심 지표."""
    sub = g[np.isclose(g.alpha, alpha)]
    keys = list(C.KEYS)
    out = sub[sub.split == "A"][keys + ["official"]].drop_duplicates().reset_index(drop=True)
    for s in C.SPLITS:
        r = sub[sub.split == s].drop_duplicates(keys)[keys + ["r2_ref"]].rename(columns={"r2_ref": f"r2_ref_{s}"})
        out = out.merge(r, on=keys)
    for variant, short in (("stage1", "s1"), ("stage2", "s2")):
        for s in C.SPLITS:
            r = sub[(sub.split == s) & (sub.variant == variant)][keys + ["test_f1", "test_fn_rows", "test_fp_rows", "test_fp_records",
                                                                          "test_abn_records_detected", "valid_f1", "test_only_f1", "test_only_fn_rows"]]
            r = r.rename(columns={c: f"{short}_{c}_{s}" for c in r.columns if c not in keys})
            out = out.merge(r, on=keys)
        out[f"{short}_test_f1_mean"] = (out[f"{short}_test_f1_A"] + out[f"{short}_test_f1_B"]) / 2
        out[f"{short}_valid_f1_mean"] = (out[f"{short}_valid_f1_A"] + out[f"{short}_valid_f1_B"]) / 2
        out[f"{short}_test_only_f1_mean"] = (out[f"{short}_test_only_f1_A"] + out[f"{short}_test_only_f1_B"]) / 2
        out[f"{short}_fp_records_total"] = out[f"{short}_test_fp_records_A"] + out[f"{short}_test_fp_records_B"]
        out[f"{short}_fp_rows_total"] = out[f"{short}_test_fp_rows_A"] + out[f"{short}_test_fp_rows_B"]
        out[f"{short}_fn_rows_total"] = out[f"{short}_test_fn_rows_A"] + out[f"{short}_test_fn_rows_B"]
    return out


METRICS_DIST = ["test_f1", "test_fn_rows", "test_fp_rows", "test_fp_records", "test_abn_records_detected", "valid_f1",
                "test_only_f1", "test_only_fn_rows", "test_record_f1"]


def distribution(g: pd.DataFrame) -> pd.DataFrame:
    """변형·α·분할·지표마다 81점의 최솟값·중앙값·최댓값, F1 ≥ 0.99 비율, 공식 격자점 값, 공식과 다른 격자점 수."""
    rows = []
    for (a, variant, s), sub in g.groupby(["alpha", "variant", "split"]):
        off = sub[sub.official].iloc[0]
        for m in METRICS_DIST:
            x = sub[m].to_numpy(float)
            rows.append(dict(alpha=a, variant=variant, split=s, metric=m, n=len(x), min=x.min(), median=float(np.median(x)), max=x.max(),
                             official=float(off[m]), n_differs_from_official=int((~np.isclose(x, float(off[m]), rtol=0, atol=1e-12)).sum()),
                             share_ge_0_99=float((x >= 0.99).mean()) if "f1" in m else np.nan))
    return pd.DataFrame(rows)


ME_METRICS = ["test_f1_mean", "fp_records_total", "fp_rows_total", "fn_rows_total", "valid_f1_mean", "test_only_f1_mean"]


def main_effects(w: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """상수의 각 값에서 나머지 27점 평균, 주효과 = 최대 − 최소. 그 상수의 모든 값에서 다른 상수 조합마다 지표가 같은지(invariant)도 낸다."""
    rows = []
    for short in ("s1", "s2"):
        for met in ME_METRICS:
            col = f"{short}_{met}"
            for k in C.KEYS:
                means = w.groupby(k)[col].mean()
                others = [o for o in C.KEYS if o != k]
                invariant = bool((w.groupby(others)[col].nunique() == 1).all())
                rows.append(dict(alpha=alpha, stage=short, metric=met, constant=k,
                                 **{f"mean_at_{lv}": float(v) for lv, v in means.items()},
                                 level_means=";".join(f"{lv}:{v:.6g}" for lv, v in means.items()),
                                 main_effect=float(means.max() - means.min()), invariant_across_levels=invariant))
    me = pd.DataFrame(rows)
    me["rank"] = me.groupby(["stage", "metric"])["main_effect"].rank(ascending=False, method="min").astype(int)
    return me


def oat(w: pd.DataFrame, alpha: float) -> pd.DataFrame:
    """공식 격자점에서 상수 하나만 바꾼 8점(+공식점)."""
    out = []
    for _, r in w.iterrows():
        diff = [k for k in C.KEYS if r[k] != C.OFFICIAL[k]]
        if len(diff) <= 1:
            out.append(dict(alpha=alpha, changed=diff[0] if diff else "(공식)", value=r[diff[0]] if diff else None,
                            **{c: r[c] for c in w.columns if c.startswith(("s1_", "s2_", "r2_ref"))}))
    return pd.DataFrame(out)


def key_numbers(g, me, ref):
    """보고서용 핵심 수치(α 1% 중심, α 3·5%는 보조). me = 모든 α의 주효과 표."""
    out = {}
    for a in C.ALPHAS:
        w = wide(g, a)
        d = {}
        for short, variant in (("s1", "stage1"), ("s2", "stage2")):
            off = w[w.official].iloc[0]
            both = (w[f"{short}_test_f1_A"] >= 0.99) & (w[f"{short}_test_f1_B"] >= 0.99)
            low = w[~both][list(C.KEYS) + [f"{short}_test_f1_A", f"{short}_test_f1_B"]]
            d[variant] = dict(
                test_f1={s: dict(min=float(w[f"{short}_test_f1_{s}"].min()), median=float(w[f"{short}_test_f1_{s}"].median()),
                                 max=float(w[f"{short}_test_f1_{s}"].max()), official=float(off[f"{short}_test_f1_{s}"]),
                                 share_ge_0_99=float((w[f"{short}_test_f1_{s}"] >= 0.99).mean())) for s in C.SPLITS},
                share_both_ge_0_99=float(both.mean()),
                points_below_0_99=low.to_dict("records"),
                test_fn_rows={s: [int(w[f"{short}_test_fn_rows_{s}"].min()), int(w[f"{short}_test_fn_rows_{s}"].max())] for s in C.SPLITS},
                test_fp_rows={s: [int(w[f"{short}_test_fp_rows_{s}"].min()), int(w[f"{short}_test_fp_rows_{s}"].max()),
                                  int(off[f"{short}_test_fp_rows_{s}"])] for s in C.SPLITS},
                test_fp_records={s: dict(min=int(w[f"{short}_test_fp_records_{s}"].min()), max=int(w[f"{short}_test_fp_records_{s}"].max()),
                                         official=int(off[f"{short}_test_fp_records_{s}"]),
                                         n_points_differ=int((w[f"{short}_test_fp_records_{s}"] != off[f"{short}_test_fp_records_{s}"]).sum()),
                                         n_records=int(g[(g.split == s)].test_normal_records.iloc[0])) for s in C.SPLITS},
                n_points_fp_records_differ_any_split=int(((w[f"{short}_test_fp_records_A"] != off[f"{short}_test_fp_records_A"]) |
                                                           (w[f"{short}_test_fp_records_B"] != off[f"{short}_test_fp_records_B"])).sum()),
                abn_records_detected={s: [int(w[f"{short}_test_abn_records_detected_{s}"].min()), int(w[f"{short}_test_abn_records_detected_{s}"].max())] for s in C.SPLITS},
                valid_f1_mean=dict(min=float(w[f"{short}_valid_f1_mean"].min()), median=float(w[f"{short}_valid_f1_mean"].median()),
                                   max=float(w[f"{short}_valid_f1_mean"].max()), official=float(off[f"{short}_valid_f1_mean"])),
                test_only_f1={s: dict(min=float(w[f"{short}_test_only_f1_{s}"].min()), median=float(w[f"{short}_test_only_f1_{s}"].median()),
                                      max=float(w[f"{short}_test_only_f1_{s}"].max()), official=float(off[f"{short}_test_only_f1_{s}"]),
                                      share_ge_0_99=float((w[f"{short}_test_only_f1_{s}"] >= 0.99).mean())) for s in C.SPLITS},
            )
            mes = me[(me.stage == short) & np.isclose(me.alpha, a)]
            d[variant]["main_effects"] = {met: mes[mes.metric == met].sort_values("main_effect", ascending=False)[
                ["constant", "main_effect", "invariant_across_levels", "level_means"]].to_dict("records") for met in ME_METRICS}
        d["reference_v2"] = {s: dict(test_f1=float(ref[(ref.split == s) & np.isclose(ref.alpha, a)].test_f1.iloc[0]),
                                     test_fp_records=int(ref[(ref.split == s) & np.isclose(ref.alpha, a)].test_fp_records.iloc[0]),
                                     test_only_f1=float(ref[(ref.split == s) & np.isclose(ref.alpha, a)].test_only_f1.iloc[0]))
                             for s in C.SPLITS}
        out[str(a)] = d
    return out


def main():
    t0 = time.time()
    tables, meta = C.load_tables(), C.load_meta()
    cands = C.candidates_by_name(meta)
    S07 = C.load_module("tvt_s07_sens", "07_r1_on_baselines.py")
    M = C.setup_official()
    trains = C.train_currents(M)
    train_pr2 = {s: {m: C.prefix_r2_with(m, cur, seg) for m in C.GRID["R2_MIN_LEN"]} for s, (cur, seg) in trains.items()}
    refs = {s: C.r2_refs(train_pr2[s]) for s in C.SPLITS}
    pd.DataFrame([dict(split=s, R2_Q=q, R2_MIN_LEN=m, r2_ref=v, official=(q, m) == (0.005, 8)) for s in C.SPLITS for (q, m), v in refs[s].items()]
                 ).to_csv(OUT / "r2_ref_grid.csv", index=False)
    checks = run_checks(tables, meta, cands, S07, train_pr2)
    print("사전 확인 통과:", checks["all_ok"], "| 공식 재현 비교", checks["official_reproduction"]["checked"], "건", f"({time.time() - t0:.0f}초)")

    g = compute_grid(tables, cands, S07, refs)
    g.to_csv(OUT / "grid_metrics.csv", index=False)
    ref = reference_v2(tables, meta, cands, S07)
    ref.to_csv(OUT / "grid_reference_v2.csv", index=False)
    # 격자 안 공식점이 공식 출력과 같아야 한다(공식 재현과 같은 값)
    off = g[g.official & np.isclose(g.alpha, 0.01)].set_index(["split", "variant"])
    assert off.loc[("A", "stage1"), "test_f1"] == 1.0 and abs(off.loc[("B", "stage1"), "test_f1"] - 0.9953917050691244) < 1e-12
    assert off.loc[("A", "stage2"), "test_f1"] == 1.0 and off.loc[("B", "stage2"), "test_f1"] == 1.0

    w1 = wide(g, C.PRIMARY_ALPHA)
    w1.to_csv(OUT / "grid_alpha01_wide.csv", index=False)
    for a in C.ALPHAS:
        if a != C.PRIMARY_ALPHA:
            wide(g, a).to_csv(OUT / f"grid_alpha{int(round(a * 100)):02d}_wide.csv", index=False)
    dist = distribution(g)
    dist.to_csv(OUT / "grid_distribution.csv", index=False)
    me = pd.concat([main_effects(wide(g, a), a) for a in C.ALPHAS], ignore_index=True)
    me.to_csv(OUT / "grid_main_effects.csv", index=False)
    pd.concat([oat(wide(g, a), a) for a in C.ALPHAS], ignore_index=True).to_csv(OUT / "grid_oat.csv", index=False)
    summary = dict(n_grid_points=int(len(w1)), alphas=list(C.ALPHAS), primary_alpha=C.PRIMARY_ALPHA,
                   r2_ref={s: {f"{q}|{m}": v for (q, m), v in refs[s].items()} for s in C.SPLITS},
                   key_numbers=key_numbers(g, me, ref),
                   seconds=round(time.time() - t0, 1))
    C.dump(summary, OUT / "grid_summary.json")
    kn = summary["key_numbers"]["0.01"]
    for v in ("stage1", "stage2"):
        print(v, {s: kn[v]["test_f1"][s] for s in C.SPLITS}, "both>=0.99:", kn[v]["share_both_ge_0_99"],
              "FP rec:", kn[v]["test_fp_records"], "valid:", kn[v]["valid_f1_mean"])
    print(f"완료 {time.time() - t0:.0f}초")


if __name__ == "__main__":
    main()
