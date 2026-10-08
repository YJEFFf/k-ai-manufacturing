"""격자·교차·E3 결과와 확인 기록을 모아 outputs/summary.json(핵심 수치)과 outputs/environment.json(판·소스 해시)을 쓴다.

실행 순서: run_grid.py → run_swap.py → run_e3.py(선택) → make_summary.py → verify.py
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

import sens_common as C

OUT = C.OUT


def load(name):
    p = OUT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def top(me_list):
    """주효과가 가장 큰 상수(동률이면 모두). 모두 0이면 빈 목록."""
    mx = max(r["main_effect"] for r in me_list)
    return [] if mx <= 0 else [r["constant"] for r in me_list if abs(r["main_effect"] - mx) <= 1e-12]


def stage_block(kn):
    out = dict(test_f1=kn["test_f1"], share_both_ge_0_99=kn["share_both_ge_0_99"], n_points_below_0_99=len(kn["points_below_0_99"]),
               points_below_0_99=kn["points_below_0_99"], test_fn_rows_range=kn["test_fn_rows"],
               test_fp_rows_min_max_official=kn["test_fp_rows"], test_fp_records=kn["test_fp_records"],
               n_points_fp_records_differ_any_split=kn["n_points_fp_records_differ_any_split"],
               abn_records_detected_range=kn["abn_records_detected"], valid_f1_mean=kn["valid_f1_mean"], test_only_f1=kn["test_only_f1"])
    out["most_influential"] = {m: dict(top=top(v), main_effects={r["constant"]: round(r["main_effect"], 6) for r in v},
                                       invariant={r["constant"]: r["invariant_across_levels"] for r in v})
                               for m, v in kn["main_effects"].items()}
    return out


def main():
    lock = json.loads((C.HERE / "protocol_lock.json").read_text(encoding="utf-8"))
    cg, gs, sw, e3, ce = load("checks_grid.json"), load("grid_summary.json"), load("swap_summary.json"), load("e3_summary.json"), load("checks_e3.json")
    env = C.environment_record()
    C.dump(env, OUT / "environment.json")
    kn = gs["key_numbers"]
    summ = dict(
        protocol_lock=lock,
        nature="민감도 감사. 공식 모델(1단계 v2+R1, 2단계 v2+R1+R2)·상수(60초·2행·0.5% 분위·8행)·α 1%는 바꾸지 않는다. 같은 단일 사건, 상수는 자료를 본 뒤 정함.",
        official_reproduction=dict(ok=cg["official_reproduction"]["ok"], checked=cg["official_reproduction"]["checked"],
                                   compared_against=["사본 code/press/tvt/outputs", "claude/code/press/tvt/outputs"],
                                   official_point_alpha01={v: kn["0.01"][v]["test_f1"] for v in ("stage1", "stage2")},
                                   valid_f1_mean_official={v: kn["0.01"][v]["valid_f1_mean"]["official"] for v in ("stage1", "stage2")},
                                   prefix_r2_and_r2_ref=cg["prefix_and_r2_ref"], patch_visibility_all_ok=all(cg["patch_visibility"].values()),
                                   cache=cg["cache"]),
        grid_points=gs["n_grid_points"],
        r2_ref_range={s: [min(gs["r2_ref"][s].values()), max(gs["r2_ref"][s].values())] for s in C.SPLITS},
        grid_alpha01={v: stage_block(kn["0.01"][v]) for v in ("stage1", "stage2")},
        grid_secondary_alphas={a: {v: dict(test_f1=kn[a][v]["test_f1"], share_both_ge_0_99=kn[a][v]["share_both_ge_0_99"],
                                           test_fp_records=kn[a][v]["test_fp_records"], valid_f1_mean=kn[a][v]["valid_f1_mean"],
                                           test_only_f1=kn[a][v]["test_only_f1"],
                                           most_influential={m: top(x) for m, x in kn[a][v]["main_effects"].items()})
                                   for v in ("stage1", "stage2")} for a in ("0.03", "0.05")},
        reference_v2={a: kn[a]["reference_v2"] for a in kn},
        swap=dict(selected_realtime=sw["swapped_selection"]["selected_realtime"]["model"],
                  selected_realtime_detail=sw["swapped_selection"]["selected_realtime"],
                  selected_record=sw["swapped_selection"]["selected_record"]["model"],
                  front10_test_alpha01={m: {s: v[s]["f1"] for s in C.SPLITS} for m, v in sw["swapped_test_front10_alpha01"].items()},
                  front10_test_alpha01_counts=sw["swapped_test_front10_alpha01"],
                  back11_valid_alpha01={m: {s: v[s]["f1"] for s in C.SPLITS} for m, v in sw["swapped_valid_back11_alpha01"].items()},
                  record_track_front10=sw["swapped_test_front10_record_selected"],
                  control_reproduced_official=sw["control_unswapped"]["valid_csv_identical_lf"] and sw["control_unswapped"]["same_selection_as_official"],
                  caveat=sw["caveat"]),
        e3=None if e3 is None else dict(ok=ce["all_ok"], seconds=e3["seconds"], within_time_budget=e3["within_time_budget"],
                                        n_records=300, alpha={a: {v: {k: e3["summary"][a][f"all|{v}"][k] for k in
                                                                       ("min", "median", "max", "official", "rate_min", "rate_max", "rate_official",
                                                                        "n_points_differ", "largest_main_effect", "main_effect_range")}
                                                                  for v in ("v2", "v2+R2", "v2+R1", "v2+R1+R2")} for a in e3["summary"]},
                                        keep288={a: {v: {k: e3["summary"][a][f"keep|{v}"][k] for k in ("min", "max", "official")}
                                                     for v in ("v2+R1", "v2+R1+R2")} for a in e3["summary"]}),
        deviations=[],
        issues=["verify.py 첫 실행에서 r2_ref_grid.csv 비교가 실패했다. pandas 기본 CSV 실수 파서가 마지막 자리(1 ULP)를 잃은 탓이며 "
                "float_precision='round_trip'으로 읽게 고친 뒤 18개 값이 모두 비트 단위로 일치했다. 결과 값은 바뀌지 않았다.",
                "swap_selection.json은 공식 02 코드를 고치지 않고 돌린 출력이라 protocol.splits.abnormal 문구('앞 10기록 검증, 뒤 11기록 시험')가 "
                "그대로 남아 있다. 실제 역할은 뒤 11기록 valid·앞 10기록 test이며 swap_summary.json에 적었다."],
        extras_beyond_protocol=["주효과·불변 판정을 FP 행·미탐 행·test부터 따로 F1에도 계산", "α 3·5%의 주효과", "규칙 없는 v2 참고값",
                                "앞뒤 바꾸기의 α 3·5% F1", "E3 창별 표와 v2·v2+R2 수"],
    )
    # 한 번에 하나만 바꾼 8점(α 1%), 상수별 불변 판정, 탐지 쪽 범위
    o = pd.read_csv(OUT / "grid_oat.csv", float_precision="round_trip")
    o = o[np.isclose(o.alpha, C.PRIMARY_ALPHA)].copy()
    o["value"] = o["value"].astype(object).where(o["value"].notna(), None)   # 공식점은 바꾼 값이 없다(JSON null)
    summ["oat_alpha01"] = o[["changed", "value", "s1_test_f1_A", "s1_test_f1_B", "s1_test_fp_records_B", "s1_test_fp_rows_B", "s1_valid_f1_mean",
                             "s2_test_f1_A", "s2_test_f1_B", "s2_test_fp_records_B", "s2_valid_f1_mean"]].to_dict("records")
    me = pd.read_csv(OUT / "grid_main_effects.csv")
    summ["invariant_metric_count"] = {f"{a}": {k: f"{int(g.invariant_across_levels.sum())}/{len(g)}" for k, g in me[np.isclose(me.alpha, a)].groupby("constant")}
                                      for a in C.ALPHAS}
    gm = pd.read_csv(OUT / "grid_metrics.csv", float_precision="round_trip")
    summ["detection_all_points"] = dict(max_test_missed_rows=int(gm.test_fn_rows.max()), max_test_only_missed_rows=int(gm.test_only_fn_rows.max()),
                                        min_abnormal_test_records_detected=int(gm.test_abn_records_detected.min()), of=11,
                                        scope="81점 × α 1·3·5% × A·B × 1·2단계")
    C.dump(summ, OUT / "summary.json")
    print(json.dumps(dict(official=summ["official_reproduction"]["official_point_alpha01"], swap=summ["swap"]["selected_realtime"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
