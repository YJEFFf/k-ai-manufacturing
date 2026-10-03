"""보고서 수치 근거표(facts.csv)를 원본 산출물에서 다시 읽어 만든다.

각 행: id, value(원값), shown(본문 표시형), source(파일), locator(키·행열)
check_facts.py가 본문 숫자를 이 표의 shown 값과 대조한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "code/press/cases/outputs"
TVT = ROOT / "code/press/tvt/outputs"
ALIAS = ROOT / "code/press/outputs/alias/segment_sine_fit.csv"
rows = []


def add(fid, value, shown, source, locator):
    rows.append(dict(id=fid, value=value, shown=str(shown), source=str(Path(source).relative_to(ROOT)) if Path(source).is_absolute() else source,
                     locator=locator))


def fmt(x, d):
    return f"{x:.{d}f}"


# ---- 1장: 데이터 ----
fx = json.loads((CASES / "facts_extra.json").read_text(encoding="utf-8"))
for side in ("normal", "abnormal"):
    f = fx[side]
    src = CASES / "facts_extra.json"
    add(f"{side}.rows", f["rows"], f"{f['rows']:,}", src, f"{side}.rows")
    add(f"{side}.records", f["records"], f["records"], src, f"{side}.records")
    add(f"{side}.measured_pct", f["measured_share"], fmt(f["measured_share"] * 100, 1), src, f"{side}.measured_share")
    add(f"{side}.measured_pct0", f["measured_share"], fmt(f["measured_share"] * 100, 0), src, f"{side}.measured_share")
    add(f"{side}.vib_upper_sd", f["vib_upper_sd"], fmt(f["vib_upper_sd"], 3), src, f"{side}.vib_upper_sd")
    add(f"{side}.vib_lower_sd", f["vib_lower_sd"], fmt(f["vib_lower_sd"], 3), src, f"{side}.vib_lower_sd")
    add(f"{side}.current_mean", f["current_mean"], fmt(f["current_mean"], 1), src, f"{side}.current_mean")
    add(f"{side}.corr_median", f["upper_lower_corr_median"], fmt(f["upper_lower_corr_median"], 2), src, f"{side}.upper_lower_corr_median")
    add(f"{side}.ratio_median", f["upper_over_lower_sd_median"], fmt(f["upper_over_lower_sd_median"], 2), src, f"{side}.upper_over_lower_sd_median")
    add(f"{side}.rec_mean_min", f["record_current_mean_min"], fmt(f["record_current_mean_min"], 1), src, f"{side}.record_current_mean_min")
    add(f"{side}.rec_mean_max", f["record_current_mean_max"], fmt(f["record_current_mean_max"], 1), src, f"{side}.record_current_mean_max")
    add(f"{side}.ge10", f["records_ge10"], f["records_ge10"], src, f"{side}.records_ge10")
    add(f"{side}.ge10_offset", f["records_ge10_abs_mean_gt_sd"], f["records_ge10_abs_mean_gt_sd"], src, f"{side}.records_ge10_abs_mean_gt_sd")
add("normal.exactly50", fx["normal"]["records_exactly_50"], fx["normal"]["records_exactly_50"], CASES / "facts_extra.json", "normal.records_exactly_50")
add("normal.over50", fx["normal"]["records_over_50"], fx["normal"]["records_over_50"], CASES / "facts_extra.json", "normal.records_over_50")
add("normal.negative_pct", fx["normal"]["current_negative_share"], fmt(fx["normal"]["current_negative_share"] * 100, 1), CASES / "facts_extra.json", "normal.current_negative_share")
add("abnormal.corr_negative_pct", fx["abnormal"]["upper_lower_corr_negative_share"], fmt(fx["abnormal"]["upper_lower_corr_negative_share"] * 100, 0), CASES / "facts_extra.json", "abnormal.upper_lower_corr_negative_share")
add("normal.duplicate", fx["normal"]["duplicate_rows"], fx["normal"]["duplicate_rows"], CASES / "facts_extra.json", "normal.duplicate_rows")
add("normal.span_min", fx["normal"]["span_s"] / 60, fmt(fx["normal"]["span_s"] / 60, 0), CASES / "facts_extra.json", "normal.span_s/60")
add("normal.measured_min", fx["normal"]["measured_s"] / 60, fmt(fx["normal"]["measured_s"] / 60, 0), CASES / "facts_extra.json", "normal.measured_s/60")
add("ratio.upper_sd", fx["abnormal"]["vib_upper_sd"] / fx["normal"]["vib_upper_sd"], fmt(fx["abnormal"]["vib_upper_sd"] / fx["normal"]["vib_upper_sd"], 1), CASES / "facts_extra.json", "abnormal/normal vib_upper_sd")
fl = fx["format_leak"]
add("leak.raw_f1", fl["raw"]["f1"], fmt(fl["raw"]["f1"], 3), CASES / "facts_extra.json", "format_leak.raw.f1")
add("leak.matched_f1", fl["matched"]["f1"], fmt(fl["matched"]["f1"], 3), CASES / "facts_extra.json", "format_leak.matched.f1")
for side, key in (("normal", "normal_digits_share"), ("abnormal", "abnormal_digits_share")):
    for tag in ("raw", "matched"):
        for dg, v in fl[tag][key].items():
            add(f"leak.{tag}.{side}.digits{dg}", v, fmt(v * 100, 1), CASES / "facts_extra.json", f"format_leak.{tag}.{key}.{dg}")
add("abnormal.abs_mean_median", fx["abnormal"]["record_abs_mean_median"], fmt(fx["abnormal"]["record_abs_mean_median"], 1), CASES / "facts_extra.json", "abnormal.record_abs_mean_median")
REQ = ROOT / "code/press/outputs/requantize"
pm = pd.read_csv(REQ / "policy_metrics_by_variant.csv")
pm = pm[(pm.budget == 0.01) & (pm.calibration_unit == "rows")]
for r in pm.itertuples():
    add(f"requant.{r.variant}.{r.split}.{r.model}.f1", r.f1_all_rows, fmt(r.f1_all_rows, 3), REQ / "policy_metrics_by_variant.csv", f"{r.variant}/{r.split}/{r.model}/α0.01 rows")
sr = pd.read_csv(REQ / "shortcut_rules.csv")
for r in sr.itertuples():
    add(f"shortcut.{r.variant}.{r.rule}.f1", r.f1, fmt(r.f1, 3), REQ / "shortcut_rules.csv", f"{r.variant}/{r.rule}")
leak = json.loads((CASES / "leak_demo.json").read_text(encoding="utf-8"))
add("leak.f1_all", leak["f1"], fmt(leak["f1"], 3), CASES / "leak_demo.json", "f1")
alias = pd.read_csv(ALIAS)
add("alias.normal", alias[alias.set == "normal"].f_alias.median(), fmt(alias[alias.set == "normal"].f_alias.median(), 2), ALIAS, "set=normal f_alias median")
add("alias.abnormal", alias[alias.set != "normal"].f_alias.median(), fmt(alias[alias.set != "normal"].f_alias.median(), 2), ALIAS, "set!=normal f_alias median")

# ---- 2장: 케이스 특징 ----
sep = pd.read_csv(CASES / "feature_separation.csv").set_index("feature")
for feat in sep.index:
    add(f"auroc.{feat}", sep.loc[feat, "auroc"], fmt(sep.loc[feat, "auroc"], 3), CASES / "feature_separation.csv", f"{feat}.auroc")
    add(f"outside.{feat}", sep.loc[feat, "abnormal_outside_normal"], int(sep.loc[feat, "abnormal_outside_normal"]), CASES / "feature_separation.csv", f"{feat}.abnormal_outside_normal")
add("r2.normal_median", sep.loc["cur_sine_r2", "normal_median"], fmt(sep.loc["cur_sine_r2", "normal_median"], 3), CASES / "feature_separation.csv", "cur_sine_r2.normal_median")
add("r2.abnormal_median", sep.loc["cur_sine_r2", "abnormal_median"], fmt(sep.loc["cur_sine_r2", "abnormal_median"], 3), CASES / "feature_separation.csv", "cur_sine_r2.abnormal_median")
add("r2.abnormal_max", sep.loc["cur_sine_r2", "abnormal_max"], fmt(sep.loc["cur_sine_r2", "abnormal_max"], 3), CASES / "feature_separation.csv", "cur_sine_r2.abnormal_max")
add("lag1.normal_median", sep.loc["vib_upper_lag1", "normal_median"], fmt(sep.loc["vib_upper_lag1", "normal_median"], 3), CASES / "feature_separation.csv", "vib_upper_lag1.normal_median")
add("lag1.abnormal_median", sep.loc["vib_upper_lag1", "abnormal_median"], fmt(sep.loc["vib_upper_lag1", "abnormal_median"], 3), CASES / "feature_separation.csv", "vib_upper_lag1.abnormal_median")
pre = pd.read_csv(CASES / "precursor_scan.csv")
add("precursor.count", len(pre), len(pre), CASES / "precursor_scan.csv", "rows")
add("precursor.r2_min", pre.cur_sine_r2.min(), fmt(pre.cur_sine_r2.min(), 3), CASES / "precursor_scan.csv", "cur_sine_r2 min")
add("precursor.r2_max", pre.cur_sine_r2.max(), fmt(pre.cur_sine_r2.max(), 3), CASES / "precursor_scan.csv", "cur_sine_r2 max")

# ---- 2·3장: 모델 비교 ----
test = pd.read_csv(TVT / "tvt_test.csv")
valid = pd.read_csv(TVT / "tvt_valid.csv")
for mode in ("realtime", "record"):
    for (model, split, alpha), r in test[test["mode"] == mode].groupby(["model", "split", "alpha"]):
        r = r.iloc[0]
        for k in ("f1",):
            add(f"test.{mode}.{model}.{split}.{alpha}.f1", r.f1, fmt(r.f1, 3), TVT / "tvt_test.csv", f"{mode}/{model}/{split}/{alpha}")
            add(f"test.{mode}.{model}.{split}.{alpha}.f1_4", r.f1, fmt(r.f1, 4), TVT / "tvt_test.csv", f"{mode}/{model}/{split}/{alpha}")
        for k in ("tp", "fp", "fn"):
            add(f"test.{mode}.{model}.{split}.{alpha}.{k}", r[k], int(r[k]), TVT / "tvt_test.csv", f"{mode}/{model}/{split}/{alpha}/{k}")
for mode in ("realtime", "record"):
    vm = valid[(valid.alpha == 0.01) & (valid["mode"] == mode)].groupby("model").f1.mean()
    for model, v in vm.items():
        add(f"valid.{mode}.{model}.mean", v, fmt(v, 3), TVT / "tvt_valid.csv", f"{mode}/{model}/α0.01 mean")
        add(f"valid.{mode}.{model}.mean4", v, fmt(v, 4), TVT / "tvt_valid.csv", f"{mode}/{model}/α0.01 mean")
meta = json.loads((TVT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
for s in ("A", "B"):
    add(f"repro.v2.{s}", meta[s]["v2_original_protocol"]["f1"], fmt(meta[s]["v2_original_protocol"]["f1"], 6), TVT / "tvt_scores_meta.json", f"{s}.v2_original_protocol.f1")
hyp = json.loads((TVT / "tvt_hypotheses.json").read_text(encoding="utf-8"))
add("leak.f1_test", hyp["hypotheses"]["H4"]["test"]["A"]["f1"], fmt(hyp["hypotheses"]["H4"]["test"]["A"]["f1"], 3), TVT / "tvt_hypotheses.json", "H4.test.A.f1")
for s in ("A", "B"):
    e = hyp["v2_test_errors"][s]
    add(f"v2err.{s}.missed", e["missed_rows"], e["missed_rows"], TVT / "tvt_hypotheses.json", f"v2_test_errors.{s}.missed_rows")
    add(f"v2err.{s}.pos01", e["missed_by_position"].get("0", 0) + e["missed_by_position"].get("1", 0),
        e["missed_by_position"].get("0", 0) + e["missed_by_position"].get("1", 0), TVT / "tvt_hypotheses.json", f"v2_test_errors.{s}.pos0+1")
    for fa in e["false_alarms"]:
        add(f"v2err.{s}.fa_pos.{fa['position']}", fa["position"], fa["position"], TVT / "tvt_hypotheses.json", f"v2_test_errors.{s}.false_alarms")
        add(f"v2err.{s}.fa_r2.{fa['position']}", fa["prefix_r2"], fmt(fa["prefix_r2"], 3), TVT / "tvt_hypotheses.json", f"v2_test_errors.{s}.false_alarms")
fa = json.loads((TVT / "test_first_alarm.json").read_text(encoding="utf-8"))
add("first_alarm.max", fa["A"]["first_alarm_s_max"], fmt(fa["A"]["first_alarm_s_max"], 1), TVT / "test_first_alarm.json", "A.first_alarm_s_max")

for (model, split), r in valid[(valid.alpha == 0.01) & (valid["mode"] == "realtime")].groupby(["model", "split"]):
    r = r.iloc[0]
    for k in ("tp", "fp", "fn"):
        add(f"valid.realtime.{model}.{split}.{k}", r[k], int(r[k]), TVT / "tvt_valid.csv", f"realtime/{model}/{split}/{k}")

# ---- 외부 인용 (예준 레포 원문) ----
add("yejun.corr_lower_current", 0.865, "0.865", "yejun/analysis/press_evidence/README.md:138", "구간 AI1 SD ~ 전류 RMS Spearman")
add("yejun.simple_rule.A", 0.890, "0.890", "yejun/press_guard/README.md:57", "단순 규칙 행 F1 A")
add("yejun.simple_rule.B", 0.900, "0.900", "yejun/press_guard/README.md:57", "단순 규칙 행 F1 B")
add("yejun.prob_cap", 55.0, "55.0", "yejun/press_guard/README.md:119·console_workspace_v2.png", "이상 확률 표시 상한 55%(π 1%, LR 121)")
add("kamp.date", "2022.12.23", "2022.12.23", "가이드북_소성가공_원문확인.md", "출처 표기 양식")
add("kamp.seq", 48, "48", "가이드북_소성가공_원문확인.md", "DATASET_SEQ")
add("yejun.brier.A", 0.0072, "0.0072", "yejun/press_guard/README.md", "이상 확률 교차 평가 표 A")
add("yejun.brier.B", 0.0056, "0.0056", "yejun/press_guard/README.md", "이상 확률 교차 평가 표 B")
add("yejun.uci.auroc_lo", 0.43, "0.43", "yejun/analysis/press_supplement/e2_uci_metrics.csv", "local 행")
add("yejun.uci.auroc_hi", 0.55, "0.55", "yejun/analysis/press_supplement/e2_uci_metrics.csv", "local 행")
add("guide.tons", 1000, "1000", "가이드북 p8", "1000톤")
add("guide.days", "2~3", "2~3", "가이드북 p8", "최대 2~3일")

# ---- 검증 실험 (04_validation.py) ----
vs = TVT / "validation_summary.json"
if vs.exists():
    j = json.loads(vs.read_text(encoding="utf-8"))["judgments"]
    add("V1b.max_cost_pp", j["V1b_max_cost_pp"], fmt(j["V1b_max_cost_pp"], 1), vs, "judgments.V1b_max_cost_pp")
    add("V1a_prime.share_pct", j["V1a_prime_release_within_8_share"], fmt(j["V1a_prime_release_within_8_share"] * 100, 1), vs, "judgments.V1a_prime_release_within_8_share")
    add("V1a_prime.cases", j["V1a_prime_cases"], j["V1a_prime_cases"], vs, "judgments.V1a_prime_cases")
    pod = pd.read_csv(TVT / "validation_v1_pod.csv")
    for _, r in pod.iterrows():
        for col, name in (("v2|detected", "v2"), ("v2+R1|detected", "v2R1"), ("v2+R1+R2|detected", "final"), ("v3_B1|detected", "v3B1")):
            add(f"pod.{r.split}.{r.family}.{r.target}.{r.strength}.{name}", r[col], fmt(r[col], 3), TVT / "validation_v1_pod.csv", f"{r.split}/{r.family}/{r.target}/{r.strength}/{name}")
    v5 = pd.read_csv(TVT / "validation_v5.csv")
    for r in v5.itertuples():
        add(f"v5.{r.split}.{r.test}.{r.level}.{r.variant}.alerted", r.alerted, int(r.alerted), TVT / "validation_v5.csv", f"{r.split}/{r.test}/{r.level}/{r.variant}")
        add(f"v5.{r.split}.{r.test}.{r.level}.{r.variant}.records", r.records, int(r.records), TVT / "validation_v5.csv", f"{r.split}/{r.test}/{r.level}/{r.variant}")
        add(f"v5.{r.split}.{r.test}.{r.level}.{r.variant}.pct", r.rate, fmt(r.rate * 100, 1), TVT / "validation_v5.csv", f"{r.split}/{r.test}/{r.level}/{r.variant}")
    sp = pd.read_csv(TVT / "validation_v3split.csv")
    for r in sp.itertuples():
        add(f"v3split.{r.fold}.{r.variant}.f1", r.f1, fmt(r.f1, 3), TVT / "validation_v3split.csv", f"{r.fold}/{r.variant}")
        add(f"v3split.{r.fold}.{r.variant}.f1_4", r.f1, fmt(r.f1, 4), TVT / "validation_v3split.csv", f"{r.fold}/{r.variant}")
        add(f"v3split.{r.fold}.{r.variant}.normal_alerted", r.normal_alerted_records, int(r.normal_alerted_records), TVT / "validation_v3split.csv", f"{r.fold}/{r.variant}")
    for _, r in pod.iterrows():
        for col, name in (("v2|detected", "v2"), ("v2+R1|detected", "v2R1"), ("v2+R1+R2|detected", "final")):
            add(f"podpct.{r.split}.{r.family}.{r.target}.{r.strength}.{name}", r[col], fmt(r[col] * 100, 1), TVT / "validation_v1_pod.csv", f"{r.split}/{r.family}/{r.target}/{r.strength}/{name} %")
    cost = pd.read_csv(TVT / "validation_cost.csv")
    add("cost.share_le8", (cost.latched_rows_next <= 8).mean(), fmt((cost.latched_rows_next <= 8).mean() * 100, 1), TVT / "validation_cost.csv", "latched_rows_next<=8 share")
    add("cost.share_le8_notshort", ((cost.latched_rows_next <= 8) & ~cost.next_short).mean(), fmt(((cost.latched_rows_next <= 8) & ~cost.next_short).mean() * 100, 1), TVT / "validation_cost.csv", "<=8 & not next_short share")
    add("cost.share_le7", (cost.latched_rows_next <= 7).mean(), fmt((cost.latched_rows_next <= 7).mean() * 100, 1), TVT / "validation_cost.csv", "latched_rows_next<=7 share")
    strict = ((cost.latched_rows_next <= 7) & ~cost.next_short).mean()
    add("cost.share_le7_notshort", strict, fmt(strict * 100, 1), TVT / "validation_cost.csv", "latched_rows_next<=7 & not next_short / all")
    add("cost.chain_rows_max", cost.chain_rows.max(), int(cost.chain_rows.max()), TVT / "validation_cost.csv", "chain_rows max")
    add("cost.chain_records_max", cost.chain_records.max(), int(cost.chain_records.max()), TVT / "validation_cost.csv", "chain_records max")
    add("cost.next_short", int(cost.next_short.sum()), int(cost.next_short.sum()), TVT / "validation_cost.csv", "next_short count")
    add("cost.median_rows", cost.latched_rows_next.median(), fmt(cost.latched_rows_next.median(), 0), TVT / "validation_cost.csv", "latched_rows_next median")
    add("cost.max_rows", cost.latched_rows_next.max(), int(cost.latched_rows_next.max()), TVT / "validation_cost.csv", "latched_rows_next max")
    add("cost.chain2", int((cost.chain_records >= 2).sum()), int((cost.chain_records >= 2).sum()), TVT / "validation_cost.csv", "chain_records>=2 count")
    chain = pd.read_csv(TVT / "validation_chain.csv").groupby(["family", "order", "variant"]).detected.mean()
    for (fam, order, var), v in chain.items():
        add(f"chain.{fam}.{order}.{var}", v, fmt(v, 3), TVT / "validation_chain.csv", f"{fam}/{order}/{var} mean")
    loss = pd.read_csv(TVT / "validation_loss.csv")
    lm = loss.groupby(["split", "target", "multiplier"])[[c for c in loss.columns if c.endswith("|detected")]].mean()
    for (s, tg, m), r in lm.iterrows():
        for col in lm.columns:
            add(f"loss.{s}.{tg}.{m}.{col}", r[col], fmt(r[col] * 100, 0), TVT / "validation_loss.csv", f"{s}/{tg}/{m}/{col} %")

# ---- v5: 도메인·사후 분석(code/press/domain/outputs) — JSON·CSV의 모든 숫자를 표시 형식별로 등록 ----
DOM = ROOT / "code/press/domain/outputs"


def add_number(fid, v, source):
    """소수 0~4자리, 비율이면 백분율 0~2자리, 부호 없는 값까지 표시 후보로 등록한다."""
    if isinstance(v, bool) or v is None:
        return
    try:
        x = float(v)
    except (TypeError, ValueError):
        return
    if not np.isfinite(x):
        return
    shown = {f"{x:.{d}f}" for d in range(5)} | {f"{abs(x):.{d}f}" for d in range(5)}
    if x == int(x):
        shown.add(str(int(x)))
    if -1 <= x <= 1:
        shown |= {f"{x * 100:.{d}f}" for d in range(3)} | {f"{abs(x) * 100:.{d}f}" for d in range(3)}
    for s in shown:
        add(fid, x, s, source, fid)


def walk(node, prefix, source):
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, f"{prefix}.{k}", source)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk(v, f"{prefix}[{i}]", source)
    else:
        add_number(prefix, node, source)


for js in sorted(DOM.glob("*.json")):
    walk(json.loads(js.read_text(encoding="utf-8")), js.stem, js)
for cs in sorted(DOM.glob("*.csv")):
    df = pd.read_csv(cs)
    for col in df.select_dtypes("number").columns:
        for v in pd.unique(df[col].dropna()):
            add_number(f"{cs.stem}.{col}", v, cs)

# ---- v5: 외부 근거 수치(report/research/*.md에 출처 URL과 함께 기록) ----
EXT = [
    ("grid.nominal_hz", 60, "60", "domain_sources.md 7장 전기사업법 시행규칙 별표 3"),
    ("grid.tolerance_hz", 0.2, "0.2", "domain_sources.md 7장"),
    ("grid.required_low", 59.4, "59.4", "01_signal_physics: fs=10이면 필요한 계통 주파수"),
    ("press.tonnage", 1000, "1000", "가이드북 p.8"),
    ("pump.teeth_lo", 9, "9", "domain_sources.md 2-1 Danfoss 특허"),
    ("pump.teeth_hi", 12, "12", "domain_sources.md 2-1"),
    ("wear.hours_lo", 960, "960", "Guo et al. 2020 표 3 (960.3h)"),
    ("wear.hours_hi", 982, "982", "Guo et al. 2020 (981.8h)"),
    ("wear.vol_eff", 70, "70", "Guo et al. 2020 체적효율 70%"),
    ("motor.1x_hz", 29, "29", "4극 60Hz 가정 약 29~30Hz (domain_sources.md 4장)"),
    ("gmf.lo", 260, "260", "잇수 9×29Hz 근사(가정)"),
    ("gmf.hi", 350, "350", "잇수 12×29Hz 근사(가정)"),
    ("oil.visc_lo", 100, "100", "VG46 25°C 약 100cSt (Walther 외삽, domain_sources.md 3장)"),
    ("oil.visc_hi", 135, "135", "VG46 20°C 약 135cSt"),
    ("pump.cold_start_max", 2000, "2000", "Rexroth AZPF 냉간 기동 최대 2000mm²/s"),
    ("isa.alarm_per_hour", 6, "6", "ISA-18.2(exida 재수록) 시간당 약 6건"),
    ("guide.f1_pct", 74.76, "74.76", "가이드북 p.41"),
    ("guide.fpr_pct", 1.95, "1.95", "가이드북 p.40~41 오경보 78/4,000 계산"),
    ("guide.rows_lo", 16000, "16,000", "가이드북 p.27 그림 판독(organizer_intent.md)"),
    ("guide.rows_hi", 19000, "19,000", "가이드북 p.27 그림 판독"),
    ("guide.downtime_days", 3, "2~3", "가이드북 p.8"),
    ("design.alpha_grid_pct", 0.83, "0.83", "1/121 (04_sequential_uncertainty)"),
    ("design.alpha_grid_den", 121, "121", "1/121"),
    ("cold.ratio", 15, "15", "2000/135 ≈ 14.8 → 1/15"),
    ("alias.block_range", 0.00066, "0.00066", "01_signal_physics pooled_f_block_range_hz"),
    ("shu.press_kn", 12000, "12,000", "Shu et al. 2023 12,000kN 프레스"),
    ("interval.lo1", 100.7, "100.7", "6/(60.2−0.6) ms 계산(±0.2Hz)"),
    ("interval.hi1", 101.4, "101.4", "6/(59.8−0.6) ms 계산"),
    ("interval.lo2", 98.7, "98.7", "6/(60.2+0.6) ms 계산"),
    ("interval.hi2", 99.3, "99.3", "6/(59.8+0.6) ms 계산"),
    ("quiet.upper_ratio", 0.52, "0.52", "06 표 정숙 0.0381 / 변동 0.0733"),
    ("quiet.lower_ratio", 0.40, "0.40", "06 표 정숙 0.0439 / 변동 0.1088"),
    ("guide.quality_pct", 96.66, "96.66", "가이드북 p.62~64 품질지수(organizer_intent.md)"),
    ("abn.row_share_pct", 2.9, "2.9", "600/20,600"),
    ("phase.abs_deg", 120, "120", "01 위상차 −122°의 크기(부호 미확정)"),
    ("oil.0c_cst", 580, "580", "Shell Tellus S2 M 46 0°C"),
    ("oil.temp_assume", 25, "25", "유온 가정 20~25°C"),
    ("prob.prev_brier_A", 0.112, "0.112", "yejun/press_guard/README.md 이상 확률 표"),
    ("prob.prev_brier_B", 0.082, "0.082", "yejun/press_guard/README.md 이상 확률 표"),
    ("regB.high_share", 66, "66", "06_operating_regime.csv B α5% 7모델 계산 52/79"),
    ("regB.mid_share", 33, "33", "26/79"),
    ("regB.high_rate", 14.0, "14.0", "52/(7×53)"),
    ("regB.all_rate", 3.8, "3.8", "79/(7×300)"),
    ("regB.ratio", 3.7, "3.7", "14.0/3.76"),
    ("seq.k_grid_edge", 4.42, "4.42", "04 요약: v2 보정 최댓값 A 4.42"),
    ("seq.k_grid_edge_B", 3.52, "3.52", "04 요약: B 3.52"),
    ("seq.p_ge3", 0.19, "0.19", "04 요약: P(≥3) ≈ 0.19"),
    ("prob.file_prior_A", 12.8, "12.8", "yejun README: 평가 파일 이상 비율 A 12.8%"),
    ("prob.file_prior_B", 9.0, "9.0", "B 9.0%"),
    ("prob.raw_brier_A", 0.0321, "0.0321", "yejun README: π 1% 파일 라벨 채점 Brier A"),
    ("prob.raw_brier_B", 0.0221, "0.0221", "B"),
    ("regB.pct_hi", 99.6, "99.6", "06 records B 학습 기준 분위"),
]
for fid, v, shown, src in EXT:
    add(fid, v, shown, "report/research", src)

out = pd.DataFrame(rows)
out.to_csv(Path(__file__).with_name("facts.csv"), index=False, encoding="utf-8-sig")
print(len(out), "facts")
