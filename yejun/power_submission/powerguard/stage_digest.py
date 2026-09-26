"""핵심 수치 모음(outputs/key_numbers.json). 각 값에 출처 파일을 붙인다. 서술·결론은 쓰지 않는다."""
from __future__ import annotations

import json

import pandas as pd

from . import config as C
from . import io


def _read_json(rel):
    p = C.OUTPUT_DIR / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _read_csv(rel):
    p = C.OUTPUT_DIR / rel
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def run() -> dict:
    out = {}
    diag = _read_json("diagnostics/summary.json")
    if diag:
        d = diag["diagnosis"]
        out["data"] = {"source": "diagnostics/summary.json", "days": d["n_days"], "unique_day_patterns": d["unique_daily_power_patterns"],
                       "copied_days": d["copied_power_days"], "copy_origin_rule": d.get("copy_origin_rule"),
                       "copy_groups_multi": d.get("copy_groups_multi"),
                       "copy_groups_earliest_member_consistent": d.get("copy_groups_earliest_member_consistent"),
                       "copy_groups_latest_member_consistent": d.get("copy_groups_latest_member_consistent"),
                       "singleton_days_consistent": d.get("singleton_days_consistent"),
                       "earliest_is_origin_binom_p": d.get("earliest_is_origin_binom_p"),
                       "copied_by_src_month": d.get("copied_by_src_month"), "genuine_days_by_month": d.get("genuine_days_by_month"),
                       "partial_copy_days": d["partial_copy_days"],
                       "hour_copy_placebo": d["hour_copy_placebo_matches"], "corrupt_dates": d["corrupt_hour_dates"],
                       "regime_mismatch_days": d["regime_mismatch_days"], "usable": diag["usable"], "peak": diag["peak"],
                       "test_composition": diag["test_composition"]}
    for rel, key in (("diagnostics/preprocessing_waterfall.csv", "preprocessing_waterfall"),
                     ("diagnostics/split_composition.csv", "split_composition"),
                     ("diagnostics/production_power_relation.csv", "production_power_relation")):
        t0 = _read_csv(rel)
        if not t0.empty:
            out[key] = {"source": rel, "rows": t0.round(4).to_dict("records")}
    sel = _read_json("cv/selection.json")
    out["selection"] = {"source": "cv/selection.json", **{k: {"chosen": v["chosen"], "v1_rule_choice": v.get("v1_rule_choice"),
                                                              "blend_members": v.get("blend_members"), "trail": v["trail"]}
                                                          for k, v in sel.items()}}
    rob = _read_csv("cv/selection_robustness.csv")
    if not rob.empty:
        out["selection_robustness"] = {"source": "cv/selection_robustness.csv", **{
            f: g["chosen"].value_counts().to_dict() for f, g in rob.groupby("family")}}
    tm = _read_csv("test/test_metrics.csv")
    if not tm.empty and sel:
        rows = {}
        for task in ["B", "A1", "A2", "A3", "A4"]:
            fam = "A" if task.startswith("A") else "B"
            t = tm[tm.task == task].set_index("model")
            ch = sel[fam]["chosen"]
            ref = "BL1_persistence" if fam == "A" else "BL2_same_daytype"
            rows[task] = {"chosen": ch, "MAE": t.at[ch, "MAE"], "RMSE": t.at[ch, "RMSE"], "nMAE": t.at[ch, "nMAE"],
                          "R2": t.at[ch, "R2"], "RMSE_work_dayshift": t.at[ch, "RMSE_work"] if "RMSE_work" in t else None,
                          "naive": ref, "naive_RMSE": t.at[ref, "RMSE"],
                          "rmse_reduction_vs_naive": 1 - t.at[ch, "RMSE"] / t.at[ref, "RMSE"],
                          "best_test_model": t["RMSE"].idxmin(), "best_test_RMSE": t["RMSE"].min(),
                          "best_test_baseline": t[t.index.str.startswith("BL")]["RMSE"].idxmin(),
                          "best_test_baseline_RMSE": t[t.index.str.startswith("BL")]["RMSE"].min()}
        out["test_regression"] = {"source": "test/test_metrics.csv", **rows}
    for rel, key, filt in (("analysis/test_skill.csv", "test_skill_chosen", None),
                           ("cv/selection_summary.csv", "selection_summary", None),
                           ("peak/day_level_metrics.csv", "day_level_metrics_test", ("period", "test")),
                           ("peak/month_max_prediction.csv", "month_max_prediction", None),
                           ("analysis/test_bootstrap.csv", "test_bootstrap", None)):
        t0 = _read_csv(rel)
        if t0.empty:
            continue
        if filt:
            t0 = t0[t0[filt[0]] == filt[1]]
        if key == "test_skill_chosen" and sel:
            t0 = t0[[m == sel["A" if tk.startswith("A") else "B"]["chosen"] for tk, m in zip(t0.task, t0.model)]]
        out[key] = {"source": rel, "rows": t0.round(4).to_dict("records")}
    j = _read_json("field/ratchet_risk_days_summary.json")
    if j:
        out["ratchet_risk_days"] = {"source": "field/ratchet_risk_days_summary.json", **j}
    cvm = _read_csv("cv/cv_metrics.csv")
    if not cvm.empty and sel:
        out["cv_pooled_RMSE_chosen"] = {"source": "cv/cv_metrics.csv", **{
            t: float(cvm[(cvm.task == t) & (cvm.split == "pooled") & (cvm.model == sel["A" if t.startswith("A") else "B"]["chosen"])]["RMSE"].iloc[0])
            for t in ["B", "A1", "A2", "A3", "A4"]}}
    pk = _read_json("peak/peak_summary.json")
    nh = _read_csv("peak/next_hour_classification.csv")
    sens = _read_csv("peak/next_hour_threshold_sensitivity.csv")
    al = _read_csv("peak/next_hour_alarms.csv")
    if pk:
        m = pk["prob_method"]["chosen"]
        o = {"source": "peak/*", "T_test": pk["T_test"], "prob_method": m, "tau": pk["tau"][m],
             "calibration": pk["prob_method"].get("calibration")}
        if not nh.empty:
            o["test_classification"] = nh[(nh.method == m) & (nh.period == "test")].iloc[0][
                ["F1", "precision", "recall", "PR_AUC", "Brier", "ECE", "base_rate", "BSS_vs_climatology"]].to_dict()
            o["test_rules_F1"] = nh[(nh.method.str.startswith("R_")) & (nh.period == "test")].set_index("method")["F1"].to_dict()
            o["test_climatology"] = nh[(nh.method == "P_climatology") & (nh.period == "test")].iloc[0][
                ["F1", "PR_AUC", "Brier", "ECE"]].to_dict()
        fb = _read_csv("peak/next_hour_f1_bootstrap.csv")
        if not fb.empty:
            o["F1_diff_bootstrap"] = fb.to_dict("records")
        if not sens.empty:
            s = sens[sens.period == "test"]
            o["threshold_sensitivity_test"] = {str(q): s[s.peak_q == q].set_index("method")[["F1", "PR_AUC"]].round(4).to_dict("index")
                                               for q in sorted(s.peak_q.unique())}
        if not al.empty:
            cols = ["tau", "precision", "recall", "F1", "event_recall", "event_recall_scheduled",
                    "event_recall_unscheduled", "events", "alarm_on_hours_per_day", "episodes_per_day",
                    "false_episodes_per_day", "lead_median_min"]
            for rule in ("f1", "match_clock_hours"):
                a = al[(al.method == m) & (al.period == "test") & (al.tau_rule == rule)]
                if len(a):
                    o[f"test_alarm_{rule}"] = a.iloc[0][cols].to_dict()
            c = al[(al.method == "R_clock") & (al.period == "test") & (al.tau_rule == "rule")]
            if len(c):
                o["test_alarm_clock_rule"] = c.iloc[0][cols].to_dict()
        out["peak"] = o
    cov = _read_csv("peak/interval_coverage.csv")
    if not cov.empty:
        c = cov[(cov.alpha == 0.2) & (cov.period == "test")]
        out["intervals_80_test"] = {"source": "peak/interval_coverage.csv", **{
            f"{t}|{mth}": c[(c.task == t) & (c.method == mth)].set_index("cond")[["coverage", "width"]].round(4).to_dict("index")
            for t in c.task.unique() for mth in c.method.unique()}}
    for rel, key in (("analysis/peak_conditions.json", "peak_conditions"), ("external/external_summary.json", "external")):
        j = _read_json(rel)
        if j:
            out[key] = {"source": rel, **j}
    dc = _read_csv("field/demand_controller.csv")
    if not dc.empty:
        t = dc[(dc.period == "test") & (dc.shed == 0.10) & (dc.tau_selection != "candidate")]
        out["demand_controller_test_shed10"] = {"source": "field/demand_controller.csv", **{
            f"T{int(r.target)}|{r.payback}|{r.policy}": {"over_reduction_share": r.over_reduction_share,
                                                         "max_month_max_change": r.max_month_max_change,
                                                         "episodes_per_workday": r.episodes_per_workday,
                                                         "shed_hours_per_workday": r.shed_hours_per_workday, "tau": r.tau}
            for r in t.itertuples()}}
    st = _read_csv("field/startup_staggering_monthly.csv")
    if not st.empty:
        st = st[(st["hold"] == 0)]
        out["startup_staggering"] = {"source": "field/startup_staggering_monthly.csv(유지 부하 0)",
                                     "rows": st.round(3).to_dict("records")}
    for rel in ("field/billing_ratchet.json",):
        j = _read_json(rel)
        if j:
            out["billing_ratchet"] = {"source": rel, **j}
    for rel, key in (("field/integrated_scenario.csv", "integrated_scenario"), ("field/alarm_burden.csv", "alarm_burden"),
                     ("field/ratchet_events.csv", "ratchet_events"), ("analysis/naive_protocol.csv", "naive_protocol"),
                     ("analysis/shap_grouped.csv", "shap_grouped"), ("analysis/error_rule_stability.csv", "error_rule_stability"),
                     ("cv/ml_sweep.csv", "ml_sweep")):
        t0 = _read_csv(rel)
        if not t0.empty:
            out[key] = {"source": rel, "rows": t0.round(4).to_dict("records")}
    for rel, key in (("analysis/plan_information_value.csv", "plan_information_value"),
                     ("analysis/ablations.csv", "ablations"), ("analysis/learning_curve.csv", "learning_curve")):
        t = _read_csv(rel)
        if not t.empty:
            out[key] = {"source": rel, "rows": t.round(4).to_dict("records")}
    io.write_json(out, C.OUTPUT_DIR / "key_numbers.json")
    return out
