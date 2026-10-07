"""보고서 수치 근거표(facts.csv)를 분석 산출물에서 다시 읽어 만든다.

입력: code/press/{cases,tvt,domain}/outputs, code/press/outputs/{alias,requantize}, 아래 EXT 표(외부 문헌·가이드북 수치)
출력: report/facts.csv — 각 행 id, value(원값), shown(본문 표시형), source(파일), locator(키·행열)
실행: python report/facts_build.py  → 이어서 check_facts.py가 본문 숫자를 shown 값과 대조한다
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "code/press/cases/outputs"
TVT = ROOT / "code/press/tvt/outputs"
DOM = ROOT / "code/press/domain/outputs"
REQ = ROOT / "code/press/outputs/requantize"
ALIAS = ROOT / "code/press/outputs/alias/segment_sine_fit.csv"
FX = CASES / "facts_extra.json"
SEP = CASES / "feature_separation.csv"
rows = []


def add(fid, value, shown, source, locator):
    """근거 한 행을 쌓는다. source가 절대 경로면 볼트 기준 상대 경로로 적는다."""
    rows.append(dict(id=fid, value=value, shown=str(shown), source=str(Path(source).relative_to(ROOT)) if Path(source).is_absolute() else source,
                     locator=locator))


def fmt(x, d):
    return f"{x:.{d}f}"


# ---- 1장: 데이터 ----
fx = json.loads(FX.read_text(encoding="utf-8"))
for side in ("normal", "abnormal"):
    f = fx[side]
    add(f"{side}.rows", f["rows"], f"{f['rows']:,}", FX, f"{side}.rows")
    add(f"{side}.records", f["records"], f["records"], FX, f"{side}.records")
    add(f"{side}.measured_pct", f["measured_share"], fmt(f["measured_share"] * 100, 1), FX, f"{side}.measured_share")
    add(f"{side}.measured_pct0", f["measured_share"], fmt(f["measured_share"] * 100, 0), FX, f"{side}.measured_share")
    add(f"{side}.vib_upper_sd", f["vib_upper_sd"], fmt(f["vib_upper_sd"], 3), FX, f"{side}.vib_upper_sd")
    add(f"{side}.vib_lower_sd", f["vib_lower_sd"], fmt(f["vib_lower_sd"], 3), FX, f"{side}.vib_lower_sd")
    add(f"{side}.current_mean", f["current_mean"], fmt(f["current_mean"], 1), FX, f"{side}.current_mean")
    add(f"{side}.corr_median", f["upper_lower_corr_median"], fmt(f["upper_lower_corr_median"], 2), FX, f"{side}.upper_lower_corr_median")
    add(f"{side}.ratio_median", f["upper_over_lower_sd_median"], fmt(f["upper_over_lower_sd_median"], 2), FX, f"{side}.upper_over_lower_sd_median")
    add(f"{side}.rec_mean_min", f["record_current_mean_min"], fmt(f["record_current_mean_min"], 1), FX, f"{side}.record_current_mean_min")
    add(f"{side}.rec_mean_max", f["record_current_mean_max"], fmt(f["record_current_mean_max"], 1), FX, f"{side}.record_current_mean_max")
    add(f"{side}.ge10", f["records_ge10"], f["records_ge10"], FX, f"{side}.records_ge10")
    add(f"{side}.ge10_offset", f["records_ge10_abs_mean_gt_sd"], f["records_ge10_abs_mean_gt_sd"], FX, f"{side}.records_ge10_abs_mean_gt_sd")
nf, af = fx["normal"], fx["abnormal"]
add("normal.exactly50", nf["records_exactly_50"], nf["records_exactly_50"], FX, "normal.records_exactly_50")
add("normal.over50", nf["records_over_50"], nf["records_over_50"], FX, "normal.records_over_50")
add("normal.negative_pct", nf["current_negative_share"], fmt(nf["current_negative_share"] * 100, 1), FX, "normal.current_negative_share")
add("abnormal.corr_negative_pct", af["upper_lower_corr_negative_share"], fmt(af["upper_lower_corr_negative_share"] * 100, 0), FX, "abnormal.upper_lower_corr_negative_share")
add("normal.duplicate", nf["duplicate_rows"], nf["duplicate_rows"], FX, "normal.duplicate_rows")
add("normal.span_min", nf["span_s"] / 60, fmt(nf["span_s"] / 60, 0), FX, "normal.span_s/60")
add("normal.measured_min", nf["measured_s"] / 60, fmt(nf["measured_s"] / 60, 0), FX, "normal.measured_s/60")
ratio = af["vib_upper_sd"] / nf["vib_upper_sd"]
add("ratio.upper_sd", ratio, fmt(ratio, 1), FX, "abnormal/normal vib_upper_sd")
fl = fx["format_leak"]
add("leak.raw_f1", fl["raw"]["f1"], fmt(fl["raw"]["f1"], 3), FX, "format_leak.raw.f1")
add("leak.matched_f1", fl["matched"]["f1"], fmt(fl["matched"]["f1"], 3), FX, "format_leak.matched.f1")
for side, key in (("normal", "normal_digits_share"), ("abnormal", "abnormal_digits_share")):
    for tag in ("raw", "matched"):
        for dg, v in fl[tag][key].items():
            add(f"leak.{tag}.{side}.digits{dg}", v, fmt(v * 100, 1), FX, f"format_leak.{tag}.{key}.{dg}")
add("abnormal.abs_mean_median", af["record_abs_mean_median"], fmt(af["record_abs_mean_median"], 1), FX, "abnormal.record_abs_mean_median")
pm = pd.read_csv(REQ / "policy_metrics_by_variant.csv")
pm = pm[(pm.budget == 0.01) & (pm.calibration_unit == "rows")]
for r in pm.itertuples():
    add(f"requant.{r.variant}.{r.split}.{r.model}.f1", r.f1_all_rows, fmt(r.f1_all_rows, 3), REQ / "policy_metrics_by_variant.csv", f"{r.variant}/{r.split}/{r.model}/α0.01 rows")
for r in pd.read_csv(REQ / "shortcut_rules.csv").itertuples():
    add(f"shortcut.{r.variant}.{r.rule}.f1", r.f1, fmt(r.f1, 3), REQ / "shortcut_rules.csv", f"{r.variant}/{r.rule}")
leak = json.loads((CASES / "leak_demo.json").read_text(encoding="utf-8"))
add("leak.f1_all", leak["f1"], fmt(leak["f1"], 3), CASES / "leak_demo.json", "f1")
alias = pd.read_csv(ALIAS)
fa_normal, fa_abnormal = alias[alias.set == "normal"].f_alias.median(), alias[alias.set != "normal"].f_alias.median()
add("alias.normal", fa_normal, fmt(fa_normal, 2), ALIAS, "set=normal f_alias median")
add("alias.abnormal", fa_abnormal, fmt(fa_abnormal, 2), ALIAS, "set!=normal f_alias median")

# ---- 2장: 케이스 특징 ----
sep = pd.read_csv(SEP).set_index("feature")
for feat in sep.index:
    add(f"auroc.{feat}", sep.loc[feat, "auroc"], fmt(sep.loc[feat, "auroc"], 3), SEP, f"{feat}.auroc")
    add(f"outside.{feat}", sep.loc[feat, "abnormal_outside_normal"], int(sep.loc[feat, "abnormal_outside_normal"]), SEP, f"{feat}.abnormal_outside_normal")
for fid, feat, col in (("r2.normal_median", "cur_sine_r2", "normal_median"), ("r2.abnormal_median", "cur_sine_r2", "abnormal_median"),
                       ("r2.abnormal_max", "cur_sine_r2", "abnormal_max"), ("lag1.normal_median", "vib_upper_lag1", "normal_median"),
                       ("lag1.abnormal_median", "vib_upper_lag1", "abnormal_median")):
    add(fid, sep.loc[feat, col], fmt(sep.loc[feat, col], 3), SEP, f"{feat}.{col}")
pre = pd.read_csv(CASES / "precursor_scan.csv")
add("precursor.count", len(pre), len(pre), CASES / "precursor_scan.csv", "rows")
add("precursor.r2_min", pre.cur_sine_r2.min(), fmt(pre.cur_sine_r2.min(), 3), CASES / "precursor_scan.csv", "cur_sine_r2 min")
add("precursor.r2_max", pre.cur_sine_r2.max(), fmt(pre.cur_sine_r2.max(), 3), CASES / "precursor_scan.csv", "cur_sine_r2 max")

# ---- 2.4절 † 열: 기록 하나를 1개로 센 F1(tvt/06, 사후) ----
RC = TVT / "tvt_record_count.csv"
rcount = pd.read_csv(RC)
for r in rcount.itertuples():
    loc = f"{r.regime}/{r.model}/{r.split}"
    add(f"reccount.{loc}.f1", r.rec_f1, fmt(r.rec_f1, 3), RC, loc)
    add(f"reccount.{loc}.tp", r.rec_tp, int(r.rec_tp), RC, loc + "/tp")
    add(f"reccount.{loc}.fp", r.rec_fp, int(r.rec_fp), RC, loc + "/fp")
_v2b = rcount.query("split == 'B' and regime == 'test' and model == 'v2'").iloc[0]
assert (round(_v2b.rec_f1, 3), _v2b.rec_tp, _v2b.rec_fp) == (0.88, 11, 3), _v2b
assert set(rcount.query("regime == 'test' and model == 'v2+H1+H2'").rec_f1) == {1.0}

# ---- 2.4절 †: R1을 기준선에도 붙인 비교, 창 때문에 점수 없는 행(tvt/07, 사후) ----
R1B = TVT / "tvt_r1_baselines.csv"
r1b = pd.read_csv(R1B)
for r in r1b.itertuples():
    loc = f"{r.model}/{r.split}"
    for col in ("valid_f1", "test_f1", "test_only_f1"):
        add(f"r1base.{loc}.{col}", getattr(r, col), fmt(getattr(r, col), 3), R1B, f"{loc}/{col}")
    for col in ("test_tp", "test_fp", "test_fn"):
        add(f"r1base.{loc}.{col}", getattr(r, col), int(getattr(r, col)), R1B, f"{loc}/{col}")
for model, v in r1b.groupby("model").valid_f1.mean().items():
    add(f"r1base.{model}.valid_mean", v, fmt(v, 3), R1B, f"{model}/valid_f1 A·B 평균")
_ifb = r1b.query("split == 'B' and model == 'iforest+H1'").iloc[0]
assert (_ifb.test_f1, round(_ifb.test_only_f1, 3)) == (1.0, 0.609), _ifb
UNS = TVT / "tvt_unscored.csv"
for r in pd.read_csv(UNS).itertuples():
    add(f"unscored.{r.model}.{r.split}", r.no_score_rows, int(r.no_score_rows), UNS, f"{r.model}/{r.split}")
    add(f"unscored.{r.model}.{r.split}.pct", 100 * r.no_score_rows / r.test_abnormal_rows, fmt(100 * r.no_score_rows / r.test_abnormal_rows, 1),
        UNS, f"{r.model}/{r.split} 비율(%)")
add("lstm.unscored_prefix", 19, "19", "code/press/tvt/lib.py", "20행 창은 기록 앞 19행에 점수가 없다")

# ---- 2.5절: 이상 확률(tvt/08, valid로만 보정, test로 채점) ----
PRB = TVT / "tvt_probability.json"
prb = json.loads(PRB.read_text(encoding="utf-8"))
for s, v in prb.items():
    add(f"prob.{s}.pi_file_pct", 100 * v["pi_file"], fmt(100 * v["pi_file"], 1), PRB, f"{s}/pi_file(%)")
    for k in ("brier_fileprior", "brier_site1pct", "brier_constant"):
        for d in (3, 4):
            add(f"prob.{s}.{k}.{d}", v[k], fmt(v[k], d), PRB, f"{s}/{k}")
    add(f"prob.{s}.max_pct", 100 * v["max_prob_site1pct"], fmt(100 * v["max_prob_site1pct"], 0), PRB, f"{s}/max_prob_site1pct(%)")
    add(f"prob.{s}.units", v["calibration_units"], int(v["calibration_units"]), PRB, f"{s}/calibration_units")
assert prb["B"]["brier_fileprior"] < prb["B"]["brier_constant"]
add("script.tvt08", 8, "08", "code/press/tvt/08_probability.py", "6장 단계 표의 스크립트 번호")

# ---- 4.2절: 이상 기록 양상(domain/07, 사후) ----
APT = ROOT / "code/press/domain/outputs/07_anomaly_patterns.json"
apt = json.loads(APT.read_text(encoding="utf-8"))
for kind, n in apt["counts"].items():
    add(f"pattern.{kind}", n, int(n), APT, f"counts/{kind}")
add("pattern.judged", sum(n for k, n in apt["counts"].items() if not k.startswith("판단 보류")), "17", APT, "10행 이상 기록 수")
assert apt["wave_broken_share"] == 1.0 and apt["offset_share"] == 1.0

# ---- 3회차(10/5): 2.4 표 PCA·CUSUM·EWMA 미탐·오경보, 3.2 합산 비율과 Clopper–Pearson 양측 95% 구간, 3.1 0.865 대상 기록 수 ----
from scipy.stats import beta as _beta


def cp_pct(k, n):
    lo = 0.0 if k == 0 else _beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else _beta.ppf(0.975, k + 1, n - k)
    return 100 * lo, 100 * hi


MS = DOM / "03_mspc.csv"
ms = pd.read_csv(MS)
for r in ms.query("alpha == 0.01 and regime == 'test' and model in ['mspc', 'mspc+H1']").itertuples():
    for col in ("realtime_fn", "realtime_fp"):
        add(f"mspc.{r.model}.{r.split}.{col}", getattr(r, col), int(getattr(r, col)), MS, f"{r.model}/{r.split}/test/{col}")
SQ = DOM / "04_sequential_uncertainty.csv"
for r in pd.read_csv(SQ).query("regime == 'test' and key in ['CUSUM-carry', 'EWMA-carry']").itertuples():
    for col in ("fn", "fp"):
        add(f"seq.{r.key}.{r.split}.{col}", getattr(r, col), int(getattr(r, col)), SQ, f"{r.key}/{r.split}/test/{col}")
OR = DOM / "06_operating_regime.csv"
orx = pd.read_csv(OR).query("scheme == 'gmm' and grouping == 'state' and split == 'B' and alpha == 0.05 and part == 'valid+test'")
seven = ["maxz3", "knn5", "mlp_ae5", "lstm20", "iforest", "v1", "v2"]
pairs = {}
for state in ("busy_high", "all"):
    g = orx[(orx.state == state) & orx.model.isin(seven)]
    assert g.model.nunique() == 7, (state, g.model.unique())
    pairs[state] = (int(g.fa_records.sum()), int(g.n_records.sum()))
for model in ("v2", "v2+H2"):
    g = orx[(orx.state == "busy_high") & (orx.model == model)].iloc[0]
    pairs[model] = (int(g.fa_records), int(g.n_records))
assert pairs["busy_high"] == (52, 371) and pairs["all"] == (79, 2100) and pairs["v2"] == (9, 53) and pairs["v2+H2"] == (1, 53), pairs
for name, (k, n) in pairs.items():
    lo, hi = cp_pct(k, n)
    add(f"regB.cp.{name}.k", k, k, OR, f"{name} fa_records 합"); add(f"regB.cp.{name}.n", n, n, OR, f"{name} n_records 합")
    for d in (1, 2):
        add(f"regB.cp.{name}.lo.{d}", lo, fmt(lo, d), OR, f"{name} Clopper–Pearson 하한(%)")
        add(f"regB.cp.{name}.hi.{d}", hi, fmt(hi, d), OR, f"{name} Clopper–Pearson 상한(%)")
SR = ROOT / "submission/북적북적_code/yejun/analysis/press_evidence/sensor_relations.csv"
sr = pd.read_csv(SR)
n469 = sr[(sr.astype(str).apply(lambda c: c.str.contains("AI1 SD")).any(axis=1)) & (sr.astype(str).apply(lambda c: c.str.contains("AI2 RMS")).any(axis=1))]
assert 469 in set(pd.to_numeric(n469.stack(), errors="coerce").dropna().astype(int)), "sensor_relations에서 469를 찾지 못함"
add("yejun.corr_lower_current.n", 469, "469", SR, "구간 수준 결합 AI1 SD~AI2 RMS 정상 기록 수")

# ---- 2·3장: 모델 비교 ----
test = pd.read_csv(TVT / "tvt_test.csv")
valid = pd.read_csv(TVT / "tvt_valid.csv")
for mode in ("realtime", "record"):
    for (model, split, alpha), r in test[test["mode"] == mode].groupby(["model", "split", "alpha"]):
        r = r.iloc[0]
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
    pos01 = e["missed_by_position"].get("0", 0) + e["missed_by_position"].get("1", 0)   # 기록 첫 두 행의 미탐
    add(f"v2err.{s}.pos01", pos01, pos01, TVT / "tvt_hypotheses.json", f"v2_test_errors.{s}.pos0+1")
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

# ---- 검증 실험 (04_validation.py). --quick 실행에서는 이 산출물이 없어 건너뛴다 ----
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
    for r in pd.read_csv(TVT / "validation_v5.csv").itertuples():
        key = f"{r.split}/{r.test}/{r.level}/{r.variant}"
        add(f"v5.{r.split}.{r.test}.{r.level}.{r.variant}.alerted", r.alerted, int(r.alerted), TVT / "validation_v5.csv", key)
        add(f"v5.{r.split}.{r.test}.{r.level}.{r.variant}.records", r.records, int(r.records), TVT / "validation_v5.csv", key)
        add(f"v5.{r.split}.{r.test}.{r.level}.{r.variant}.pct", r.rate, fmt(r.rate * 100, 1), TVT / "validation_v5.csv", key)
    for r in pd.read_csv(TVT / "validation_v3split.csv").itertuples():
        key = f"{r.fold}/{r.variant}"
        add(f"v3split.{r.fold}.{r.variant}.f1", r.f1, fmt(r.f1, 3), TVT / "validation_v3split.csv", key)
        add(f"v3split.{r.fold}.{r.variant}.f1_4", r.f1, fmt(r.f1, 4), TVT / "validation_v3split.csv", key)
        add(f"v3split.{r.fold}.{r.variant}.normal_alerted", r.normal_alerted_records, int(r.normal_alerted_records), TVT / "validation_v3split.csv", key)
    # 같은 탐지율을 백분율 표시형으로도 등록한다(위 pod.* 와 행 순서를 지키려고 따로 돈다)
    for _, r in pod.iterrows():
        for col, name in (("v2|detected", "v2"), ("v2+R1|detected", "v2R1"), ("v2+R1+R2|detected", "final")):
            add(f"podpct.{r.split}.{r.family}.{r.target}.{r.strength}.{name}", r[col], fmt(r[col] * 100, 1), TVT / "validation_v1_pod.csv", f"{r.split}/{r.family}/{r.target}/{r.strength}/{name} %")
    cost = pd.read_csv(TVT / "validation_cost.csv")
    le8, le7, short = cost.latched_rows_next <= 8, cost.latched_rows_next <= 7, cost.next_short
    for fid, v, loc in (("cost.share_le8", le8.mean(), "latched_rows_next<=8 share"), ("cost.share_le8_notshort", (le8 & ~short).mean(), "<=8 & not next_short share"),
                        ("cost.share_le7", le7.mean(), "latched_rows_next<=7 share"),
                        ("cost.share_le7_notshort", (le7 & ~short).mean(), "latched_rows_next<=7 & not next_short / all")):
        add(fid, v, fmt(v * 100, 1), TVT / "validation_cost.csv", loc)
    add("cost.chain_rows_max", cost.chain_rows.max(), int(cost.chain_rows.max()), TVT / "validation_cost.csv", "chain_rows max")
    add("cost.chain_records_max", cost.chain_records.max(), int(cost.chain_records.max()), TVT / "validation_cost.csv", "chain_records max")
    add("cost.next_short", int(short.sum()), int(short.sum()), TVT / "validation_cost.csv", "next_short count")
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


# ---- v5: 도메인·사후 분석(domain/outputs) — JSON·CSV의 모든 숫자를 표시 형식별로 등록 ----
def add_number(fid, v, source):
    """숫자 하나를 본문에 나올 수 있는 표시형(소수 0~4자리, 부호 없는 값, 비율이면 백분율 0~2자리)으로 모두 등록한다."""
    if isinstance(v, bool):     # True/False는 숫자로 치지 않는다
        return
    try:
        x = float(v)
    except (TypeError, ValueError):     # 문자열·None
        return
    if not np.isfinite(x):
        return
    shown = {f"{x:.{d}f}" for d in range(5)} | {f"{abs(x):.{d}f}" for d in range(5)}
    if x == int(x):
        shown.add(str(int(x)))
    if -1 <= x <= 1:
        shown |= {f"{x * 100:.{d}f}" for d in range(3)} | {f"{abs(x) * 100:.{d}f}" for d in range(3)}
    for s in sorted(shown):     # 정렬: set 순회 순서는 실행마다 달라 facts.csv가 바이트 단위로 재현되지 않는다
        add(fid, x, s, source, fid)


def walk(node, prefix, source):
    """JSON을 끝까지 내려가며 잎 값마다 add_number를 부른다. id는 키 경로(a.b[0].c)."""
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

# ---- 사후 2.4절 †: 문턱과 무관한 비교(tvt/10)와 성분 절제(tvt/09) ----
TF = TVT / "threshold_free.csv"
for r in pd.read_csv(TF).itertuples():
    for col in ("auroc", "prauc", "f1"):
        add(f"tf.{r.split}.{r.model}.{col}", getattr(r, col), fmt(getattr(r, col), 3), TF, f"{r.split}/{r.model}/{col}")
TB = TVT / "threshold_free_boot.csv"
for r in pd.read_csv(TB).itertuples():
    for col in ("d_f1_lo", "d_f1_hi", "d_auroc_lo", "d_auroc_hi"):
        v = getattr(r, col)
        add(f"tfboot.{r.split}.{r.other}.{col}", v, fmt(v, 3), TB, f"{r.split}/{r.other}/{col}")
        add(f"tfboot.{r.split}.{r.other}.{col}.2", v, fmt(v, 2), TB, f"{r.split}/{r.other}/{col}")
ABL = TVT / "ablation_pod.csv"
for _, r in pd.read_csv(ABL).iterrows():
    for col in ("크기", "파형", "동역학", "크기+파형", "v2"):
        add(f"abl.{r.split}.{r.family}.{r.target}.{r.strength}.{col}", r[col], fmt(r[col] * 100, 1), ABL,
            f"{r.split}/{r.family}/{r.target}/{r.strength}/{col}")

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
    ("env.python", 3.13, "3.13", "실행 환경 파이썬 판"),
    ("env.python_old", 3.12, "3.12", "팀원 예전 환경 파일 판"),
    ("run.full_min", 63, "63", "새 환경(C:/Temp/bj_v3/run4) run_all.py 전체 62.8분, 10/7, 최종 zip"),
    ("run.quick_min", 24, "24", "같은 실행의 quick 단계 시간 합 24.3분(logs/run_summary.json)"),
    ("run.checks", 31, "31", "run_all.py 결과 대조 31/31"),
    ("run.cpu_cores", 16, "16", "검증 PC Core Ultra 7 155H 16코어"),
    # 2.3절 보완 LSTM 비교(†): 예준 yejun/final-review 62482a5, research/yejun_lstm_improvement_62482a5/
    ("lstm.variants", 516, "516", "LSTM README: 변형 516개(설정 26 × 채점)"),
    ("lstm.test_A", 0.974684, "0.975", "06_summary 주 비교 보완 LSTM e345 test A"),
    ("lstm.test_B", 0.971698, "0.972", "06_summary 주 비교 보완 LSTM e345 test B"),
    ("lstm.miss_rows", 31, "31", "06_summary test 미탐 16+15, 위치 0·1·2~7 = 12·10·9"),
    ("v2.miss_rows", 38, "38", "06_summary v2 test 미탐 22+16"),
    ("v2.miss_0_7", 36, "36", "06_summary 미탐 위치 v2 13+13+10"),
    ("lstm.fa_B_a5", 20, "20", "06_summary α 민감도 B test 오경보 α 5%"),
    ("lstm.v1_max_pct", 0.6, "0.6", "06_summary current_residual B L:e345 0.006"),
    ("v2.v1_max_pct", 66.3, "66.3", "06_summary current_residual B strength 1 v2 0.663"),
    ("lstm.shift_A", 115, "115", "06_summary V5 current_shift 81.4 A L:e345 0.9583×120"),
    ("lstm.shift_B", 173, "173", "06_summary V5 current_shift 81.4 B L:e345 0.9611×180"),
    ("lstmR.shift_A", 105, "105", "07_summary LSTM+R1+R2-L2 전류 +81.4 A"),
    ("lstmR.shift_B", 164, "164", "07_summary LSTM+R1+R2-L2 전류 +81.4 B"),
    ("lstm.vib_max_pct", 46.9, "46.9", "06_summary damped_impulse B target1 strength4 L:e345 0.469"),
    ("lstm.vib_cells", 16, "16", "06_summary 진동 단독 주입 16칸"),
    ("lstm.vib_cells_lt25", 11, "11", "06_summary 16칸 중 25% 미만 11칸"),
    ("lstm.vib_cut_pct", 25, "25", "README: 25% 미만"),
    ("lstm.other_pc_A", 0.285, "0.285", "06_summary lstm20 이 PC test A"),
    ("lstm.other_pc_B", 0.215, "0.215", "06_summary lstm20 이 PC test B"),
    ("lstm.train_runs", 162, "162", "LSTM README: 학습 162회"),
    ("lstm.train_hours", 8, "8", "LSTM README: 약 8시간"),
    ("lstm.configs", 26, "26", "LSTM README: 설정 26개"),
    ("lstm.valid", 0.9684605, "0.968", "06_summary 교체 조건 1 lstm valid 평균"),
    ("lstm.seed_sd", 0.005, "0.005", "LSTM README: 최종 잠금 설정 단일 seed 표준편차"),
    ("lstm.seed_test_lo", 0.9635, "0.964", "06_summary 단일 seed test 범위"),
    ("lstm.seed_test_hi", 0.9755, "0.976", "06_summary 단일 seed test 범위"),
    ("lstm.e345_test_mean", 0.973, "0.973", "LSTM README: e345 test 평균"),
    ("lstm.e012_test_best", 0.9707, "0.971", "06_summary 사후 낙관 상한 none 최고"),
    ("lstm.epochs", 1000, "1000", "LSTM README: 1000에폭 예산"),
    ("lstmR1.valid", 0.990199, "0.990", "06_summary 교체 조건 1 L+R1 valid"),
    ("lstmR1.test_B", 0.984802, "0.985", "06_summary L+R1 test B"),
    ("lstm.rec_F1_B", 0.936, "0.936", "06_summary test 기록 판정 F1 B"),
    ("lstmR.fa_rows_a5", 34, "34", "07_summary B 정상 300기록 α5% L+R1+R2-L2 경보 34행"),
    ("lstm.jitter_max_pct", 0.7, "0.7", "README 강건성 시각 흔들림 0.1ms B 0.7%"),
    ("v2.jitter_A_pct", 7.7, "7.7", "06_summary jitter 0.1 A v2 0.0771"),
    ("v2.jitter_B_pct", 31.3, "31.3", "06_summary jitter 0.1 B v2 0.3131"),
    ("lstm.env_torch", 2.5, "2.5", "LSTM README: torch 2.5.1"),
    ("lstmR.valid", 0.999, "0.999", "07_summary L+R1+R2b(넓힌 R2) α1% valid 평균"),
    # 최종 심층 평가 MAJOR 반영(2026-10-07): scratchpad major_numbers.py로 계산, 원자료 경로는 각 항목
    ("maxzR.valid", 0.9973, "0.997", "evalcore로 max|z|+R1+R2(R2 = prefix R² 정상이면 보류) α1% valid A 0.9964·B 0.9982 평균"),
    ("loo.others", 119, "119", "valid 120기록 LOO: 자기 기록을 뺀 119기록(01_scores calibrate)"),
    ("jitter.recA", 96, "96", "04_validation JITTER: 17행 이상 정상 test 기록 A 96개 × 5회 = 480"),
    ("jitter.recB", 145, "145", "04_validation JITTER: B 145개 × 5회 = 725"),
    ("prob.auroc_A", 0.9767, "0.977", "test_predictions_A.csv v2_prob 행 AUROC"),
    ("prob.auroc_B", 0.9794, "0.979", "test_predictions_B.csv v2_prob 행 AUROC"),
    ("prob.ece_A", 0.0071, "0.007", "test_predictions_A.csv v2_prob_fileprior ECE(구간 0·0.01·0.1·0.5·0.9·1)"),
    ("prob.ece_B", 0.0064, "0.006", "test_predictions_B.csv v2_prob_fileprior ECE"),
    ("gap.median_s", 4.22, "4.2", "press_data_normal.csv 기록 사이 공백(>0.15s) 중앙값, 598개"),
    ("gap.p90_s", 8.4, "8.4", "같은 공백 90% 분위"),
    ("tfboot.n", 2000, "2,000", "tvt/10 부트스트랩 반복 수"),
    ("tfboot.base_min_lo", 0.3261, "0.33", "threshold_free_boot.csv 베이스라인 대비 d_f1_lo 최솟값(B mlp_ae5)"),
    ("lstm.ctrl_B_pct", 0.6, "0.6", "LSTM README: 주입 없는 대조 경보율 B 0.6%"),
]
for fid, v, shown, src in EXT:
    add(fid, v, shown, "report/research", src)

out = pd.DataFrame(rows)
out.to_csv(Path(__file__).with_name("facts.csv"), index=False, encoding="utf-8-sig")
print(len(out), "facts")
