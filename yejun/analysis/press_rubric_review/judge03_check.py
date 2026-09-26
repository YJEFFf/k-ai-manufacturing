"""Read-only numerical review of final press error analysis and E1/E3 outputs.

Run with OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python.
Only writes this review directory; does not train or change source outputs.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
sys.path.insert(0, str(YEJUN / "analysis/press_supplement"))
import common as C


def main():
    out = {}
    normal, abnormal, hashes = C.load_data()
    metrics = pd.read_csv(YEJUN / "press_guard/outputs/metrics.csv")
    errors = pd.read_csv(YEJUN / "press_guard/outputs/error_conditions_v2.csv")
    segerrors = pd.read_csv(YEJUN / "press_guard/outputs/error_conditions_segments_v2.csv")
    recount = []
    for sid in C.D.SPLITS:
        model = C.frozen(sid)
        rows = C.split_rows(normal, sid)["test"]
        pn = model.predict(C.D.inputs_only(normal.iloc[rows]))
        pa = model.predict(C.D.inputs_only(abnormal))
        for alpha in C.ALPHAS:
            an = pn.p_value.le(alpha)
            aa = pa.p_value.le(alpha)
            got = dict(tp=int(aa.sum()), fp=int(an.sum()), fn=int((~aa).sum()), tn=int((~an).sum()),
                       normal_notified_segments=int(an.groupby(pn.record_id).max().sum()),
                       abnormal_notified_segments=int(aa.groupby(pa.record_id).max().sum()))
            saved = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(alpha)].iloc[0]
            assert all(got[k] == saved[k] for k in got)
            for subset, prediction, alarms, kind in (("normal", pn, an, "fp"), ("abnormal", pa, aa, "fn")):
                table = errors[errors.split_id.eq(sid) & errors.model.eq("v2") & errors.alpha.eq(alpha) & errors.subset.eq(subset)]
                for condition, g in table.groupby("condition"):
                    assert g.rows.sum() == len(prediction), (sid, alpha, condition)
                    assert g.error_rows.sum() == got[kind], (sid, alpha, condition)
                table = segerrors[segerrors.split_id.eq(sid) & segerrors.model.eq("v2") & segerrors.alpha.eq(alpha) & segerrors.subset.eq(subset)]
                n = prediction.record_id.nunique()
                n_alarm = int(alarms.groupby(prediction.record_id).max().sum())
                for condition, g in table.groupby("condition"):
                    assert g.segments.sum() == n
                    assert g.error_segments.sum() == (n - n_alarm if subset == "abnormal" else n_alarm)
            recount.append(dict(split=sid, alpha=alpha, **got))
    out["fresh_prediction_recount"] = recount
    out["input_hashes"] = hashes

    raw = pd.read_csv(YEJUN / "analysis/press_supplement/predictions_e1_records.csv")
    keys = ["split", "family", "level", "shape", "t0", "model", "alpha"]
    saved = pd.read_csv(YEJUN / "analysis/press_supplement/e1_summary.csv").set_index(keys)
    max_diff = 0.
    for key, g in raw.groupby(keys, sort=False):
        hit = g.first_post.notna()
        expected_2s = hit & ((g.first_post - g.t0) < 20)
        assert (g.detected_2s == expected_2s).all()
        assert np.allclose(g.loc[hit, "delay_s"], .1 * (g.loc[hit, "first_post"] - g.loc[hit, "t0"]))
        row = dict(records=g.record.nunique(), trials=len(g), detect_rate_2s=expected_2s.mean(),
                   detect_rate_any=hit.mean(), delay_median_s=g.loc[hit, "delay_s"].median(),
                   delay_p90_s=g.loc[hit, "delay_s"].quantile(.9),
                   post_row_recall=g.post_alarm_rows.sum()/g.post_rows.sum(),
                   pre_alarm_records=int(g[g.rep.eq(0)].pre_alarm.sum()))
        for col, value in row.items():
            target = saved.loc[key, col]
            assert (pd.isna(value) and pd.isna(target)) or np.isclose(value, target, rtol=0, atol=1e-12), (key, col)
            if pd.notna(value):
                max_diff = max(max_diff, abs(float(value) - float(target)))
    out["E1_reaggregate"] = dict(raw_trials=len(raw), summary_groups=len(saved), max_abs_difference=max_diff,
                                pre_alarm_trials=int(raw.pre_alarm.sum()))
    fresh_injections = []
    for sid in C.D.SPLITS:
        model = C.frozen(sid)
        source_rows = C.split_rows(normal, sid)["test"]
        original = C.D.inputs_only(normal.iloc[source_rows])
        seg = C.D.segments(original)
        pos, length = C.D.segment_positions(seg)
        noise = np.random.default_rng(20260926).standard_normal((len(normal), 3))
        original_p = model.predict(original).p_value.to_numpy()
        for fam, level, t0 in (("cur_noise", .1, 10), ("cur_offset", .8, 0), ("cur_offset", .8, 10)):
            eligible = np.unique(seg[length >= (30 if t0 == 10 else 20)])
            mask = np.isin(seg, eligible) & (pos >= t0)
            f = original.copy()
            x = f[C.D.SENSORS[2]].to_numpy().copy()
            x[mask] += (level * model.scale[2] * noise[source_rows, 2][mask] if fam == "cur_noise"
                        else level * np.sqrt(2) * model.scale[2])
            f[C.D.SENSORS[2]] = x
            p = model.predict(f).p_value.to_numpy()
            assert np.allclose(p[~mask], original_p[~mask], equal_nan=True)
            target = raw[raw.split.eq(sid) & raw.family.eq(fam) & raw.level.eq(level) & raw["shape"].eq("step")
                         & raw.t0.eq(t0) & raw.model.eq("guard_v2") & raw.alpha.eq(.01) & raw.rep.eq(0)].set_index("record")
            for rec in eligible:
                hits = pos[(seg == rec) & (pos >= t0) & (p <= .01)]
                first = hits.min() if len(hits) else np.nan
                assert (pd.isna(first) and pd.isna(target.loc[rec, "first_post"])) or first == target.loc[rec, "first_post"]
            fresh_injections.append(dict(split=sid, family=fam, level=level, t0=t0, records=len(eligible), match=True))
    out["E1_fresh_injection_checks"] = fresh_injections
    selected = raw[raw.model.eq("guard_v2") & raw.alpha.eq(.01) & raw["shape"].eq("step") & raw.t0.eq(10) &
                   (((raw.family.eq("cur_noise")) & raw.level.eq(.1)) | ((raw.family.eq("vib_noise")) & raw.level.eq(2)))]
    grouped = []
    for key, g in selected.groupby(["split", "family", "level"]):
        per_rep = g.groupby("rep").detected_2s.mean()
        grouped.append(dict(split=key[0], family=key[1], level=key[2], records=g.record.nunique(), trials=len(g),
                            detections=int(g.detected_2s.sum()), min_seed_rate=float(per_rep.min()), max_seed_rate=float(per_rep.max())))
    out["E1_seed_ranges"] = grouped
    paired = []
    for sid in C.D.SPLITS:
        g = raw[raw.model.eq("guard_v2") & raw.alpha.eq(.01) & raw["shape"].eq("step") & raw.split.eq(sid) & raw.family.eq("cur_offset") & raw.level.eq(.8)]
        common_ids = set(g[g.t0.eq(10)].record)
        for t0, h in g[g.record.isin(common_ids)].groupby("t0"):
            paired.append(dict(split=sid, t0=int(t0), records=len(h), detect_rate_2s=h.detected_2s.mean()))
    out["E1_same_records_offset_onset"] = paired
    ref = pd.read_csv(YEJUN / "analysis/press_supplement/e1_reference_segments.csv")
    a = ref[ref.source.eq("abnormal")]
    model = C.frozen("A")
    equivalent = a.ar_resid_std / (model.scale[2] * np.sqrt(1 + model.coef[1]**2 + model.coef[2]**2))
    out["E1_ar_white_noise_equivalent"] = dict(n=int(equivalent.count()), total_abnormal_segments=len(a),
                                              min=float(equivalent.min()), median=float(equivalent.median()), max=float(equivalent.max()),
                                              note="White-noise-equivalent AR residual magnitude, not actual fault severity")
    curve = pd.read_csv(YEJUN / "analysis/press_supplement/e3_curve.csv")
    out["E3_offset_under_100pct"] = curve[curve.inject_cur_offset.lt(1)][["alpha", "n_train", "n_cal", "start", "inject_cur_offset"]].to_dict("records")
    out["E3_offset_min"] = float(curve.inject_cur_offset.min())
    out["E3_noise_min"] = float(curve.inject_cur_noise.min())
    (HERE / "judge03_checks.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
