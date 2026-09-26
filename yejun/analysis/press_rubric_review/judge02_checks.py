"""Independent model-review checks. Existing experiment outputs are read-only.

OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
  analysis/press_rubric_review/judge02_checks.py e1|e2
"""
from pathlib import Path
import json
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

REVIEW = Path(__file__).resolve().parent
SUPP = REVIEW.parent / "press_supplement"
sys.path.insert(0, str(SUPP))
import common as C
import fault_injection as E1


def e1():
    raw = pd.read_csv(SUPP / "predictions_e1_records.csv")
    saved = pd.read_csv(SUPP / "e1_summary.csv")
    keys = ["split", "family", "level", "shape", "t0", "model", "alpha"]
    recalculated = E1.summarize(raw)
    pd.testing.assert_frame_equal(saved.sort_values(keys).reset_index(drop=True),
                                  recalculated[saved.columns].sort_values(keys).reset_index(drop=True),
                                  check_dtype=False, atol=1e-12, rtol=1e-12)
    floors = E1.detection_floor(recalculated)
    pd.testing.assert_frame_equal(pd.read_csv(SUPP / "e1_detection_floor.csv"), floors,
                                  check_dtype=False, atol=1e-12, rtol=1e-12)
    normal, abnormal, _ = C.load_data()
    checked, metrics = [], []
    # Independent row-count and rank formula, including shared-sample selection limits.
    for sid in C.D.SPLITS:
        model = C.frozen(sid)
        ix = C.split_rows(normal, sid)
        test = C.D.inputs_only(normal.iloc[ix["test"]])
        cal = C.D.inputs_only(normal.iloc[ix["cal"]])
        pred = model.predict(test)
        ap = model.predict(abnormal)
        manual = (1 + (model.cal[:, None] >= pred.score.to_numpy()[None, :]).sum(axis=0)) / (len(model.cal) + 1)
        assert np.array_equal(manual, pred.p_value.to_numpy())
        counts = dict(split=sid, tp=int(ap.alarm.sum()), fp=int(pred.alarm.sum()), fn=int((1-ap.alarm).sum()))
        counts["f1"] = 2*counts["tp"]/(2*counts["tp"]+counts["fp"]+counts["fn"])
        metrics.append(counts)
        seg = C.D.segments(test)
        pos, length = C.D.segment_positions(seg)
        clean_v1 = C.v1_pvalues(model, cal, test)
        configs = [("vib_noise", 4., "step", 10), ("cur_noise", .1, "step", 10),
                   ("cur_noise", .2, "ramp", 10), ("cur_offset", .4, "step", 10),
                   ("cur_offset", .8, "step", 0), ("cur_gain", 1.5, "step", 10)]
        for family, level, shape, onset in configs:
            eligible = np.unique(seg[length >= (30 if onset == 10 else 20)])
            mask = np.isin(seg, eligible) & (pos >= onset)
            ramp = np.minimum(1., (pos-onset+1)/20) if shape == "ramp" else np.ones(len(pos))
            z = C.standard_noise(len(normal), 0)
            changed = C.inject(test, ix["test"], model, family, level, mask, ramp, z)
            assert np.array_equal(test.loc[~mask, C.D.SENSORS], changed.loc[~mask, C.D.SENSORS])
            p2 = model.predict(changed).p_value.to_numpy()
            p1 = C.v1_pvalues(model, cal, changed)
            assert np.array_equal(p2[~mask], pred.p_value.to_numpy()[~mask])
            np.testing.assert_allclose(p1[~mask], clean_v1[~mask], atol=0, rtol=0)
            for name, pv in (("guard_v2", p2), ("baseline_v1", p1)):
                sel = raw[(raw.split == sid) & (raw.family == family) & (raw.level == level) &
                          (raw["shape"] == shape) & (raw.t0 == onset) & (raw.rep == 0) &
                          (raw.model == name) & (raw.alpha == .01)].set_index("record")
                # Directly derive each record's true post-onset first hit, no record_detection use.
                for rec in eligible:
                    p = pos[seg == rec]
                    alarms = pv[seg == rec] <= .01
                    hits = p[(p >= onset) & alarms]
                    first = int(hits[0]) if len(hits) else np.nan
                    row = sel.loc[rec]
                    assert (pd.isna(first) and pd.isna(row.first_post)) or first == row.first_post
                    assert bool(row.detected_2s) == bool(len(hits) and first-onset < 20)
                    assert row.pre_alarm == bool(alarms[p < onset].any())
                    assert row.post_rows == int((p >= onset).sum())
                    assert row.post_alarm_rows == int(alarms[p >= onset].sum())
                checked.append(dict(split=sid, family=family, level=level, shape=shape, onset=onset,
                                    model=name, records=int(len(eligible))))
            print(sid, family, level, shape, onset, "PASS", flush=True)
    result = dict(summary_groups=len(saved),record_trials=len(raw),floors=floors.fillna("none").to_dict("records"),
                  metrics=metrics,spot_checks=checked,spot_record_checks=sum(c["records"] for c in checked))
    (REVIEW / "judge02_e1_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))


def e2():
    import uci_v2 as U
    with tempfile.TemporaryDirectory(prefix="judge02_uci_") as d:
        out = Path(d)
        for name in ("common.py", "uci_v2.py", "protocol.json"):
            shutil.copy2(SUPP / name, out / name)
        U.HERE = out  # redirect every output, leaving source imports and inputs intact
        U.main()
        checked = []
        for name in ("e2_uci_metrics.csv", "e2_uci_strata.csv", "e2_uci_component_diagnostic_posthoc.csv", "e2_uci_comparison.csv"):
            actual, expected = pd.read_csv(out / name), pd.read_csv(SUPP / name)
            pd.testing.assert_frame_equal(actual, expected, check_dtype=False, rtol=1e-10, atol=1e-10)
            checked.append(dict(file=name, rows=len(actual)))
        result = dict(full_rerun_matches=True, tables=checked, manifest=json.loads((out / "e2_manifest.json").read_text()))
        (REVIEW / "judge02_e2_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    {"e1": e1, "e2": e2}[sys.argv[1]]()
