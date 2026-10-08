"""검증: 공식 상수 행을 공식 코드로 다시 계산해 공식 출력과 같은지, 저장한 격자·교차·E3 결과가 다시 계산과 같은지 확인한다.

확인 항목
1. 프로토콜 잠금 해시(PROTOCOL.md·protocol.json)가 protocol_lock.json과 같다.
2. 공식 상수 재현: v2·v2+H1·v2+H1+H2, α 1·3·5%, A·B, test/valid 실시간·기록 판정이 tvt_test.csv·tvt_valid.csv(사본·claude/ 판)와 같고,
   test부터 따로 F1이 tvt_r1_baselines.csv와 같다. prefix_r2·r2_ref 재현, 패치 가시성, 점수 캐시 해시.
3. grid_metrics.csv의 공식점(α 1·3·5%)과 OAT 8점(α 1%)을 다시 계산해 저장값과 같다.
4. 앞뒤 바꾸기: 대조 실행이 공식 선택을 재현했고, 앞 10기록 F1을 다시 계산하면 swap_summary.json과 같다.
5. E3: checks_e3.json 통과, 공식점 300기록 합계가 13의 v3_rolling_pooled와 같다.
6. summary.json의 핵심 수치가 원 산출물과 같다. claude/ 아래에 변경·새 파일이 없다. 원래 clean-run 폴더의 공식 소스·캐시가 사본과 같다.
출력: outputs/verify_report.json. 하나라도 실패하면 종료 코드 1.
실행: PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 python verify.py
"""
from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pandas as pd

import sens_common as C

OUT = C.OUT


def main():
    rep = {}
    # 1. 프로토콜 잠금
    lock = json.loads((C.HERE / "protocol_lock.json").read_text(encoding="utf-8"))
    rep["protocol_lock"] = {f: C.sha256_file(C.HERE / f) == h for f, h in lock["files"].items()}
    rep["protocol_lock"]["locked_at_utc"] = lock["locked_at_utc"]

    # 2. 공식 상수 재현
    tables, meta = C.load_tables(), C.load_meta()
    cands = C.candidates_by_name(meta)
    S07 = C.load_module("tvt_s07_verify", "07_r1_on_baselines.py")
    rep["official_reproduction"] = C.official_reproduction(tables, meta, cands, S07,
                                                           {"copy": C.TVT / "outputs", "claude_repo": C.CLAUDE_TVT / "outputs"})
    M = C.setup_official()
    trains = C.train_currents(M)
    train_pr2 = {s: {m: C.prefix_r2_with(m, cur, seg) for m in C.GRID["R2_MIN_LEN"]} for s, (cur, seg) in trains.items()}
    refs = {s: C.r2_refs(train_pr2[s]) for s in C.SPLITS}
    rep["prefix_and_r2_ref"] = C.prefix_and_ref_checks(tables, meta, {s: train_pr2[s][8] for s in C.SPLITS})
    rep["patch_visibility"] = C.patch_visibility_checks(tables, meta, cands, S07)
    rep["cache"] = C.cache_hash_check()
    # 기록한 r2_ref 표와 같은지(기본 CSV 파서는 마지막 자리를 잃을 수 있어 round_trip으로 읽는다)
    rg = pd.read_csv(OUT / "r2_ref_grid.csv", float_precision="round_trip")
    rep["r2_ref_grid_matches"] = bool(all(rg[(rg.split == s) & np.isclose(rg.R2_Q, q) & (rg.R2_MIN_LEN == m)].r2_ref.iloc[0] == v
                                          for s in C.SPLITS for (q, m), v in refs[s].items()))

    # 3. 격자 저장값 재계산(공식점 α 1·3·5%, OAT 8점 α 1%)
    g = pd.read_csv(OUT / "grid_metrics.csv", float_precision="round_trip")
    metric_cols = [c for c in g.columns if c.startswith(("test_", "valid_"))]
    pts = [p for p in C.grid_points() if sum(p[k] != C.OFFICIAL[k] for k in C.KEYS) <= 1]
    assert len(pts) == 9
    mism, checked = [], 0
    for p in pts:
        alphas = C.ALPHAS if C.is_official(p) else (C.PRIMARY_ALPHA,)
        with C.lib_constants(gap=p["GAP_S"], confirm=p["CONFIRM_ROWS"]):
            for s, t in tables.items():
                tm = t.assign(prefix_r2=C.table_prefix(t, p["R2_MIN_LEN"]))
                r2ref = refs[s][(p["R2_Q"], p["R2_MIN_LEN"])]
                for a in alphas:
                    for variant, name in C.VARIANTS.items():
                        got = C.evaluate_point(tm, cands[name], a, r2ref, S07)
                        row = g[(g.split == s) & np.isclose(g.alpha, a) & (g.variant == variant) &
                                np.isclose(g.GAP_S, p["GAP_S"]) & (g.CONFIRM_ROWS == p["CONFIRM_ROWS"]) &
                                np.isclose(g.R2_Q, p["R2_Q"]) & (g.R2_MIN_LEN == p["R2_MIN_LEN"])]
                        assert len(row) == 1
                        row = row.iloc[0]
                        for c in metric_cols:
                            checked += 1
                            if abs(float(row[c]) - float(got[c])) > 1e-12:
                                mism.append(dict(point=p, split=s, alpha=a, variant=variant, metric=c, stored=float(row[c]), got=float(got[c])))
    rep["grid_recompute"] = dict(points=len(pts), checked=checked, mismatches=mism, ok=not mism)
    off = g[g.official & np.isclose(g.alpha, 0.01)].set_index(["split", "variant"]).test_f1
    rep["grid_official_point_values"] = {f"{s}|{v}": float(off.loc[(s, v)]) for s in C.SPLITS for v in C.VARIANTS}
    rep["grid_official_point_ok"] = bool(off.loc[("A", "stage1")] == 1.0 and abs(off.loc[("B", "stage1")] - 0.9953917050691244) <= 1e-12
                                         and off.loc[("A", "stage2")] == 1.0 and off.loc[("B", "stage2")] == 1.0)

    # 4. 앞뒤 바꾸기
    import run_swap
    sw = json.loads((OUT / "swap_summary.json").read_text(encoding="utf-8"))
    ctrl = sw["control_unswapped"]
    swt = {s: run_swap.swap_roles(t) for s, t in tables.items()}
    swap_ok = ctrl["valid_csv_identical_lf"] and ctrl["same_selection_as_official"]
    swap_checks = {}
    for m, per in sw["swapped_test_front10_alpha01"].items():
        for s in C.SPLITS:
            got = C.evalcore.evaluate(swt[s], cands[m], C.PRIMARY_ALPHA, "test", meta[s]["r2_ref"])["realtime"]
            same = all(got[k] == per[s][k] for k in ("tp", "fp", "fn")) and abs(got["f1"] - per[s]["f1"]) <= 1e-12
            swap_checks[f"{s}|{m}"] = dict(f1=got["f1"], same_as_summary=same)
            swap_ok &= same
    sel = json.loads((OUT / "swap_selection.json").read_text(encoding="utf-8"))
    swap_ok &= sel["selected_realtime"] == sw["swapped_selection"]["selected_realtime"]
    rep["swap"] = dict(control=ctrl, recomputed_front10=swap_checks, ok=bool(swap_ok))

    # 5. E3
    e3 = {}
    if (OUT / "checks_e3.json").exists():
        ce = json.loads((OUT / "checks_e3.json").read_text(encoding="utf-8"))
        pooled = pd.read_csv(OUT / "e3_grid_pooled.csv")
        offi = json.loads((C.TVT / "outputs" / "r2_oos_alpha.json").read_text(encoding="utf-8"))["B_alpha_nominal_vs_actual"]["v3_rolling_pooled"]
        ok = ce["all_ok"]
        for a in C.ALPHAS:
            r = pooled[pooled.official & np.isclose(pooled.alpha, a)].iloc[0]
            for v in ("v2", "v2+R1", "v2+R1+R2"):
                same = int(r[f"all|{v}"]) == int(offi[str(a)][v]["k"])
                e3[f"{a}|{v}"] = dict(got=int(r[f"all|{v}"]), official_13=int(offi[str(a)][v]["k"]), same=same)
                ok &= same
        e3["ok"] = bool(ok)
    else:
        e3["ok"] = None
        e3["note"] = "E3 미실행"
    rep["e3"] = e3

    # 6. summary.json 수치 대조, claude/ 무변경, 원래 clean-run 폴더와 사본 대조
    summ = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    gs = json.loads((OUT / "grid_summary.json").read_text(encoding="utf-8"))["key_numbers"]["0.01"]
    rep["summary_consistent"] = bool(
        summ["grid_alpha01"]["stage1"]["test_f1"] == gs["stage1"]["test_f1"]
        and summ["grid_alpha01"]["stage2"]["test_f1"] == gs["stage2"]["test_f1"]
        and summ["swap"]["selected_realtime"] == sw["swapped_selection"]["selected_realtime"]["model"]
        and summ["official_reproduction"]["ok"] is True)
    st = subprocess.run(["git", "-C", str(C.REPO), "status", "--porcelain", "--untracked-files=all", "--", "claude"],
                        capture_output=True, text=True, encoding="utf-8")
    rep["claude_untouched"] = dict(git_status=st.stdout.strip(), ok=st.returncode == 0 and st.stdout.strip() == "")
    orig = {}
    for f in C.SOURCE_FILES["tvt"]:
        orig[f] = C.sha256_file(C.CLEAN_ORIGINAL / "code/press/tvt" / f) == C.sha256_file(C.TVT / f)
    for s in C.SPLITS:
        orig[f"cache/rows_{s}.pkl"] = C.sha256_file(C.CLEAN_ORIGINAL / f"code/press/tvt/cache/rows_{s}.pkl") == C.sha256_file(C.TVT / "cache" / f"rows_{s}.pkl")
    rep["clean_run_original_equals_copy"] = orig

    ok = (all(v for k, v in rep["protocol_lock"].items() if k != "locked_at_utc")
          and rep["official_reproduction"]["ok"]
          and all(v for k, v in rep["prefix_and_r2_ref"].items() if "==" in k)
          and all(rep["patch_visibility"].values())
          and all(v["ok"] for v in rep["cache"].values())
          and rep["r2_ref_grid_matches"] and rep["grid_recompute"]["ok"] and rep["grid_official_point_ok"]
          and rep["swap"]["ok"] and rep["e3"]["ok"] is not False and rep["summary_consistent"]
          and rep["claude_untouched"]["ok"] and all(orig.values()))
    rep["all_ok"] = bool(ok)
    C.dump(rep, OUT / "verify_report.json")
    print(json.dumps({k: (v if isinstance(v, bool) else v.get("ok", "-") if isinstance(v, dict) else "-") for k, v in rep.items()}, ensure_ascii=False))
    print("검증", "통과" if ok else "실패")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
