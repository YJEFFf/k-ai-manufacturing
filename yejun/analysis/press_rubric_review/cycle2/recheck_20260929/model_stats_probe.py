"""Review-only probes of Claude X-01/02/03/07 and AR-order sensitivity.

Reads raw inputs, stored models and source; writes only model_stats_results.json
beside this script. No source, frozen results or model regeneration.
Run from any cwd with OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
GUARD = YEJUN / "press_guard"
BASE = YEJUN / "press_submission"
sys.path[:0] = [str(GUARD), str(BASE)]

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score
from model import load_bundle
from press.scores import sine_score

SENSORS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
DATA = BASE / "data/3_소성가공_예지보전"
SPLITS = {"A": (360, 480), "B": (300, 420)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def segment(df):
    time = pd.to_datetime(df.TimeStamp)
    gap = time.diff().dt.total_seconds().to_numpy()
    return np.cumsum(np.r_[False, np.abs(gap[1:] - 0.1) > 0.02])


def positions(seg):
    rows = np.arange(len(seg))
    first = np.maximum.accumulate(np.where(np.r_[True, np.diff(seg) != 0], rows, 0))
    return rows - first


def matched(df):
    q = df.copy()
    for col, step in zip(SENSORS, (1e-4, 1e-4, 1.1920929)):
        q[col] = np.round(q[col].to_numpy(float) / step) * step
    return q


def max_by_record(score, seg):
    return pd.Series(np.where(np.isfinite(score), score, -np.inf)).groupby(seg).max().to_numpy()


def conformal(cal, score):
    cal = np.sort(cal)
    return (1 + len(cal) - np.searchsorted(cal, score, side="left")) / (1 + len(cal))


def row_metrics(an, aa, sn, sa):
    tp, fp, fn = int(aa.sum()), int(an.sum()), int((~aa).sum())
    return dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn),
                normal_records=int(pd.Series(an).groupby(sn).max().sum()),
                abnormal_records=int(pd.Series(aa).groupby(sa).max().sum()))


def fixed_components(df, seg):
    x = df[SENSORS].to_numpy(float)
    cur = x[:, 2]
    osc = np.full(len(cur), np.nan)
    idx = np.flatnonzero(positions(seg) >= 2)
    osc[idx] = np.abs(cur[idx] - 2 * np.cos(2 * np.pi * .6 * .1) * cur[idx - 1] + cur[idx - 2])
    return np.column_stack([osc, np.abs(x[:, 0]), np.abs(x[:, 1])])


def tail(ref, x):
    ref = np.sort(ref[np.isfinite(ref)])
    u = np.quantile(ref, .95)
    beta = np.mean(ref[ref > u] - u)
    out = -np.log10((1 + len(ref) - np.searchsorted(ref, x, side="left")) / (1 + len(ref)))
    gu = -np.log10((1 + len(ref) - np.searchsorted(ref, u, side="left")) / (1 + len(ref)))
    out = np.where(x > u, gu + (x - u) / (beta * np.log(10)), out)
    return np.where(np.isfinite(x), out, np.nan)


def ar_fit(cur, pos, mask, order, common_rows=False):
    idx = np.flatnonzero(mask & (pos >= (4 if common_rows else order)))
    design = np.column_stack([np.ones(len(idx))] + [cur[idx - lag] for lag in range(1, order + 1)])
    coef = np.linalg.lstsq(design, cur[idx], rcond=None)[0]
    residual = cur[idx] - design @ coef
    bic = len(idx) * np.log(np.mean(residual ** 2)) + (order + 1) * np.log(len(idx))
    return coef, float(bic)


def ar_residual(cur, pos, coef):
    idx = np.flatnonzero(pos >= len(coef) - 1)
    pred = coef[0] + sum(coef[lag] * cur[idx - lag] for lag in range(1, len(coef)))
    out = np.full(len(cur), np.nan)
    out[idx] = np.abs(cur[idx] - pred)
    return out


protected = [GUARD / "model.py", BASE / "press/scores.py"]
protected += list((GUARD / "artifacts").glob("*.json"))
protected += [DATA / name for name in ("press_data_normal.csv", "outlier_data.csv")]
before = {str(p.relative_to(YEJUN)): digest(p) for p in protected}
normal = pd.read_csv(DATA / "press_data_normal.csv")
abnormal = pd.read_csv(DATA / "outlier_data.csv")
sn, sa = segment(normal), segment(abnormal)
pn, pa = positions(sn), positions(sa)
qn, qa = matched(normal), matched(abnormal)
raw_times = pd.to_datetime(abnormal.TimeStamp)
starts = raw_times[pa == 0].reset_index(drop=True)
ends = raw_times[np.r_[np.diff(sa) != 0, True]].reset_index(drop=True)
gaps = (starts.iloc[1:].reset_index(drop=True) - ends.iloc[:-1].reset_index(drop=True)).dt.total_seconds()
out = dict(
    source_hashes_before=before,
    abnormal_structure=dict(rows=len(abnormal), recording_segments=int(sa.max() + 1),
                            elapsed_seconds=float((raw_times.iloc[-1] - raw_times.iloc[0]).total_seconds()),
                            start=str(raw_times.iloc[0]), end=str(raw_times.iloc[-1]),
                            inter_segment_gap_range_seconds=[float(gaps.min()), float(gaps.max())],
                            onset_or_independent_failure_identifiers_available=False,
                            cp_lower_if_21_independent_successes=.05 ** (1 / 21),
                            cp_lower_if_1_independent_success=.05),
    splits={},
)
out["grid_concentration_at_Claude_reported_steps"] = {}
for col, step in zip(SENSORS, (1.10378983113685e-5, 1.15737184721145e-5, 1.192125)):
    out["grid_concentration_at_Claude_reported_steps"][col] = dict(
        step=step,
        abnormal=float(abs(np.exp(2j * np.pi * (abnormal[col].to_numpy() / step % 1)).mean())),
        normal=float(abs(np.exp(2j * np.pi * (normal[col].to_numpy() / step % 1)).mean())),
        note="Checks the reported grid only; does not identify ADC hardware or signal-processing causation.",
    )

# Counterexamples are analytical probes, not claims about the contest inputs.
ncal = 120
out["same_calibration_three_max_OR_counterexample"] = dict(
    assumptions="Three independent continuous components, each thresholded by its own maximum of 120 normal records",
    nominal_single_component=1 / (ncal + 1),
    true_union_false_alarm_rate=1 - (ncal / (ncal + 1)) ** 3,
)
c1 = np.zeros(ncal)
c2 = c1.copy(); c2[0] = 10
out["fmax_recalibration_counterexample"] = dict(
    v1_cal_max=float(c1.max()), v2_cal_max=float(c2.max()),
    test_v1_score=2, test_v2_score=2,
    test_v1_p=float(conformal(c1, np.array([2]))[0]),
    test_v2_p=float(conformal(c2, np.array([2]))[0]),
    note="Component addition raises one calibration maximum; v2 >= v1 scores does not guarantee calibrated alarm containment across datasets.",
)

fc_n, fc_a = fixed_components(qn, sn), fixed_components(qa, sa)
for sid, (train_end, cal_end) in SPLITS.items():
    m = load_bundle(GUARD / "artifacts" / f"guard_{sid}.json")
    predn, preda = m.predict(normal), m.predict(abnormal)
    train_mask = sn < train_end
    cal_mask = (sn >= train_end) & (sn < cal_end)
    test_mask = sn >= cal_end
    compn = {c: predn[c].to_numpy() for c in ("g_magnitude", "g_waveform", "g_dynamics")}
    compa = {c: preda[c].to_numpy() for c in compn}
    s1n = np.fmax(compn["g_magnitude"], m.tails["sine8"](sine_score(qn[SENSORS[2]].to_numpy(), sn, 8)))
    s1a = np.fmax(compa["g_magnitude"], m.tails["sine8"](sine_score(qa[SENSORS[2]].to_numpy(), sa, 8)))
    cal1 = max_by_record(s1n[cal_mask], sn[cal_mask])
    cal2 = max_by_record(predn.score.to_numpy()[cal_mask], sn[cal_mask])
    threshold1, threshold2 = float(cal1.max()), float(cal2.max())
    assert np.allclose(np.sort(cal2), np.sort(m.cal), atol=1e-12, rtol=0)
    a1, a2 = s1a > threshold1, preda.alarm.to_numpy().astype(bool)
    n1, n2 = s1n[test_mask] > threshold1, predn.alarm.to_numpy()[test_mask].astype(bool)
    gains = a2 & ~a1
    per_record = pd.DataFrame(dict(record=sa, v1=(~a1).astype(int), v2=(~a2).astype(int))).groupby("record").sum()
    delta = per_record.v1 - per_record.v2
    improved, worse = int((delta > 0).sum()), int((delta < 0).sum())
    record_n_score = max_by_record(predn.score.to_numpy()[test_mask], sn[test_mask])
    record_a_score = max_by_record(preda.score.to_numpy(), sa)
    pos_decomp = []
    for name, mask in (("0-1", pa <= 1), ("2-6", (pa >= 2) & (pa <= 6)), (">=7", pa >= 7)):
        pos_decomp.append(dict(position=name, rows=int(mask.sum()), v1_fn=int((~a1 & mask).sum()),
                               v2_fn=int((~a2 & mask).sum()), gains=int((gains & mask).sum())))
    d = dict(v1=row_metrics(n1, a1, sn[test_mask], sa), v2=row_metrics(n2, a2, sn[test_mask], sa),
             threshold_v1=threshold1, threshold_v2=threshold2, same_threshold=threshold1 == threshold2,
             v2_score_dominates_v1_normal=bool(np.all(predn.score.to_numpy() >= s1n)),
             v2_score_dominates_v1_abnormal=bool(np.all(preda.score.to_numpy() >= s1a)),
             abnormal_v1_only_alarm_rows=int((a1 & ~a2).sum()),
             improved_equal_worse_records=[improved, int((delta == 0).sum()), worse],
             sign_p=float(stats.binomtest(improved, improved + worse, .5, alternative="greater").pvalue),
             gain_rows=int(gains.sum()), gains_first_seven_fraction=float(gains[pa <= 6].sum() / gains.sum()),
             by_position=pos_decomp,
             record_maximum_separation=dict(normal_max=float(record_n_score.max()), abnormal_min=float(record_a_score.min()),
                                            auroc=float(roc_auc_score(np.r_[np.zeros(len(record_n_score)), np.ones(len(record_a_score))], np.r_[record_n_score, record_a_score]))))
    # Independently reconstruct the post-hoc fixed-oscillator OR comparator.
    scale = np.nanmax(fc_n[cal_mask], axis=0)
    fc_score_n = np.fmax.reduce(fc_n / scale, axis=1)
    fc_score_a = np.fmax.reduce(fc_a / scale, axis=1)
    fc_cal = max_by_record(fc_score_n[cal_mask], sn[cal_mask])
    assert fc_cal.max() == 1
    fan, faa = fc_score_n[test_mask] > 1, fc_score_a > 1
    d["posthoc_fixed_oscillator_OR"] = dict(calibration_component_scales=scale.tolist(),
                                            **row_metrics(fan, faa, sn[test_mask], sa))
    # Review sensitivity: keep that post-hoc feature formula, but estimate its
    # scales from training data so calibration only chooses one fixed-score cutoff.
    train_scale = np.nanmax(fc_n[train_mask], axis=0)
    fixed_train_n = np.fmax.reduce(fc_n / train_scale, axis=1)
    fixed_train_a = np.fmax.reduce(fc_a / train_scale, axis=1)
    fixed_train_cal = max_by_record(fixed_train_n[cal_mask], sn[cal_mask])
    d["posthoc_fixed_oscillator_OR_train_scaled"] = dict(
        train_component_scales=train_scale.tolist(), threshold=float(fixed_train_cal.max()),
        **row_metrics(fixed_train_n[test_mask] > fixed_train_cal.max(), fixed_train_a > fixed_train_cal.max(), sn[test_mask], sa),
        note="Post-hoc sensitivity only; not a prespecified independent baseline. Score scales fixed without calibration data.",
    )
    latn = pd.Series(fan).groupby(sn[test_mask]).cummax().to_numpy()
    lata = pd.Series(faa).groupby(sa).cummax().to_numpy()
    d["posthoc_fixed_oscillator_OR_latched"] = row_metrics(latn, lata, sn[test_mask], sa)
    recscores = max_by_record(predn.score.to_numpy(), sn)
    cal_indices = np.arange(train_end, cal_end)
    topidx = cal_indices[np.argsort(recscores[cal_indices])[-3:][::-1]]
    d["normal_calibration"] = dict(
        top3=[dict(global_record_id=int(i), max_score=float(recscores[i])) for i in topidx],
        normal_alarm_record_ids=np.flatnonzero((np.arange(len(recscores)) >= cal_end) & (recscores > threshold2)).tolist(),
        test_above_cal_median=int((recscores[cal_end:] > np.median(recscores[train_end:cal_end])).sum()),
        mannwhitney_test_vs_cal_p=float(stats.mannwhitneyu(recscores[cal_end:], recscores[train_end:cal_end]).pvalue),
    )
    k, n = int(n2.sum()), int(len(np.unique(sn[test_mask])))
    p0 = 1 / 121
    crit = int(stats.binom.ppf(.95, n, p0))
    d["iid_binomial_only"] = dict(
        events=k, records=n,
        upper_one_sided_95=float(stats.beta.ppf(.95, k + 1, n - k)),
        two_times_nominal_reject_power=float(stats.binom.sf(crit, n, 2 * p0)),
        three_times_nominal_reject_power=float(stats.binom.sf(crit, n, 3 * p0)),
        note="Conditional iid approximation, not evidence that temporal records are independent.",
    )
    cur_n, cur_a = qn[SENSORS[2]].to_numpy(), qa[SENSORS[2]].to_numpy()
    arp = {}
    for order in (1, 2, 3, 4):
        coef, _ = ar_fit(cur_n, pn, train_mask, order)
        _, bic = ar_fit(cur_n, pn, train_mask, order, common_rows=True)
        en, ea = ar_residual(cur_n, pn, coef), ar_residual(cur_a, pa, coef)
        gn, ga = tail(en[train_mask], en), tail(en[train_mask], ea)
        scn = np.fmax(np.fmax(compn["g_magnitude"], compn["g_waveform"]), gn)
        sca = np.fmax(np.fmax(compa["g_magnitude"], compa["g_waveform"]), ga)
        acal = max_by_record(scn[cal_mask], sn[cal_mask])
        arp[str(order)] = dict(normal_bic_common_rows=bic, coef=coef.tolist(),
                               fn_by_position={name: int(((sca <= acal.max()) & mask).sum())
                                               for name, mask in (("0-1", pa <= 1), ("2-3", (pa >= 2) & (pa <= 3)),
                                                                  ("4-6", (pa >= 4) & (pa <= 6)), (">=7", pa >= 7))},
                               **row_metrics(scn[test_mask] > acal.max(), sca > acal.max(), sn[test_mask], sa))
    d["AR_order_independent_refit"] = arp
    # E-07: low vibration alone cannot logically force a miss, because current
    # magnitude is an active component even at positions 0 and 1.
    vib_train = np.abs((qn.loc[train_mask, SENSORS[:2]].to_numpy() - m.mean[:2]) / m.scale[:2]).max(axis=1)
    vib_cut = np.quantile(max_by_record(vib_train, sn[train_mask]), .95)
    vib_abn = np.abs((qa[SENSORS[:2]].to_numpy() - m.mean[:2]) / m.scale[:2]).max(axis=1)
    low_records = np.flatnonzero(max_by_record(vib_abn, sa) <= vib_cut)
    rid = int(low_records[0])
    counterframe = abnormal[sa == rid].copy().reset_index(drop=True)
    counterframe.loc[0, SENSORS[2]] = m.mean[2] + 20 * m.scale[2]
    counterpred = m.predict(counterframe)
    d["low_vibration_does_not_imply_miss_counterexample"] = dict(
        original_record_id=rid, vibration_values_unchanged=True, vib_cut=float(vib_cut),
        record_vib_max=float(max_by_record(vib_abn, sa)[rid]),
        changed_only_first_row_current_z=20,
        first_row_position=int(counterpred.position.iloc[0]), first_row_alarm=int(counterpred.alarm.iloc[0]),
        first_row_reason=str(counterpred.reason.iloc[0]),
    )
    out["splits"][sid] = d

pcols = {
    "error_conditions_stats_v2.csv": ["fisher_p_greater"],
    "fp_intensity_v2.csv": ["fisher_p_greater", "cmh_p", "permutation_p_greater", "spearman_p"],
    "fn_intensity_v2.csv": ["p_amp", "p_vib_sd"],
    "position_vibration_misses_v2.csv": ["fisher_p_normal_vs_high", "fisher_p_greater", "fisher_p_pos01_vs_ge2_greater"],
}
allp, unique_by_column = [], []
for filename, cols in pcols.items():
    table = pd.read_csv(GUARD / "outputs" / filename)
    for col in cols:
        values = table[col].dropna().to_numpy()
        allp.extend(values)
        unique_by_column.extend(np.unique(values))
out["p_value_inventory"] = dict(
    cells=len(allp), distinct_numeric_values_across_all_columns=len(np.unique(allp)),
    sum_of_per_column_unique_counts=len(unique_by_column),
    note="Neither count identifies hypothesis families or the number of distinct hypotheses; equal p-values need not be duplicated tests.",
)

after = {str(p.relative_to(YEJUN)): digest(p) for p in protected}
assert before == after
out["protected_inputs_unchanged"] = True
out["verification_limits"] = [
    "Product prediction/sine primitives were read-only imports; independent reconstructions cover metrics, segmentation, fixed-rule baseline, AR coefficients/tails/BIC and statistical formulas.",
    "No new failure episode or deployment data exist here; no generalization score was estimated.",
    "A2's full split/hyperparameter grid was read, not re-executed; targeted AR-order results were independently refitted.",
]
dest = HERE / "model_stats_results.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(json.dumps({"output": str(dest.relative_to(YEJUN.parent)), "protected_inputs_unchanged": True,
                  "splits": {s: {k: out["splits"][s][k] for k in ("v1", "v2", "by_position", "posthoc_fixed_oscillator_OR", "normal_calibration")} for s in SPLITS}}, ensure_ascii=False, indent=2))
