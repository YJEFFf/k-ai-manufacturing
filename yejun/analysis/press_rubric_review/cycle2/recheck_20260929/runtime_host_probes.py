"""Read-only re-review probes; product imports read inputs, all scratch writes use tempfile.

OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
  yejun/analysis/press_rubric_review/cycle2/recheck_20260929/runtime_host_probes.py
"""
from pathlib import Path
import hashlib
import json
import platform
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
GUARD = ROOT / "yejun/press_guard"
sys.path.insert(0, str(GUARD))
import model as M
sys.path.insert(0, str(GUARD))
import monitor
import simulate
import verify
from press import scores

D = M.D
normal, abnormal, _ = D.load()
ab = D.inputs_only(abnormal).reset_index(drop=True)
models = {s: M.load_bundle(GUARD / "artifacts" / f"guard_{s}.json") for s in "AB"}
out = {"environment": {"platform": platform.platform(), "python": sys.version,
                       "numpy": np.__version__, "pandas": pd.__version__}}


def summary(p):
    return {"alarm_rows": int(p.alarm.sum()),
            "detected_records": int(p.groupby("record_id").alarm.max().sum()),
            "status": p.status.value_counts().to_dict(),
            "incident_starts": int(p.incident_notification.sum()),
            "incident_escalations": int(p.incident_escalation.sum())}


future = {}
for sid, model in models.items():
    base = model.predict(ab)
    glitch = ab.iloc[[0]].copy()
    glitch[D.TIME] = str(pd.Timestamp(ab[D.TIME].iloc[0]) + pd.Timedelta(hours=1))
    frame = pd.concat([glitch, ab], ignore_index=True)
    pred = model.predict(frame)
    detector = M.StreamDetector(model)
    streamed = pd.concat([detector.push(frame.iloc[i:i+128]) for i in range(0, len(frame), 128)], ignore_index=True)
    events = simulate.run(frame, model, chunk=128)
    fresh = M.StreamDetector(model).push(ab)
    future[sid] = {"baseline": summary(base), "all_rows_with_glitch": summary(pred),
                   "original_600_rows_after_glitch": summary(pred.iloc[1:]),
                   "stream_status_alarm_equal": bool(pred[["status", "alarm"]].equals(streamed[["status", "alarm"]])),
                   "notifications": events.loc[events.notify.eq(1), "kind"].value_counts().to_dict(),
                   "warning": M.timing_warning(pred), "new_stream_recovery": summary(fresh)}
catchup = ab.iloc[:5].copy()
t = pd.Timestamp("2022-07-17 11:51:00")
catchup[D.TIME] = [str(t), str(t-pd.Timedelta(minutes=1)), str(t-pd.Timedelta(milliseconds=100)),
                  str(t), str(t+pd.Timedelta(milliseconds=100))]
future["catchup_boundary_status"] = M.layout(catchup)[0].tolist()
out["X06_forward_timestamp"] = future

model = models["B"]
missing = ab.copy()
mask = np.random.default_rng(20260928).random(len(ab)) < .05
missing.loc[mask, D.TIME] = ""
mp = model.predict(missing)
events = simulate.run(missing, model, chunk=128)
tr = M.IncidentTracker()
t = pd.Timestamp("2022-07-17 10:00:00", tz="UTC")
with_invalid = [tr.update(0, 0, True, "magnitude", t),
                tr.update(1, 0, False, "", t+pd.Timedelta(seconds=1)),
                tr.update(2, 0, True, "magnitude", t+pd.Timedelta(seconds=2))]
tr = M.IncidentTracker()
without_invalid = [tr.update(0, 0, True, "magnitude", t),
                   tr.update(2, 0, True, "magnitude", t+pd.Timedelta(seconds=2))]
out["C02_invalid_incident_boundary"] = {
    "baseline": summary(model.predict(ab)), "missing_rows": int(mask.sum()), "after_missing": summary(mp),
    "all_notifications": events.loc[events.notify.eq(1), "kind"].value_counts().to_dict(),
    "tracker_two_alarm_rows_with_invalid_unit": with_invalid,
    "tracker_two_alarm_rows_without_invalid_unit": without_invalid}

with tempfile.TemporaryDirectory(prefix="press-review-float-") as temp:
    tmp = Path(temp)
    expected = tmp / "expected"
    expected.mkdir()
    original = pd.read_csv(GUARD / "outputs/test_predictions_B.csv")
    fn = int(original.index[original.label.eq(1) & original.alarm.eq(0)][0])
    fp = int(original.index[original.label.eq(0) & original.alarm.eq(1)][0])
    path = tmp / "probe.csv"
    original.to_csv(path, index=False)
    digest = verify.prediction_digest(path)
    (expected / verify.DIGEST).write_text(json.dumps({path.name: digest}), encoding="utf-8")
    swapped = original.copy()
    cols = ["score", "p_value", "anomaly_score", "likelihood_ratio", "anomaly_probability"]
    swapped.loc[[fn, fp], cols] = original.loc[[fp, fn], cols].to_numpy()
    swapped.to_csv(path, index=False)
    after = verify.prediction_digest(path)
    original_predictions = verify.PREDICTIONS
    verify.PREDICTIONS = (path.name,)
    try:
        compared = verify.compare_predictions(tmp, expected)
    finally:
        verify.PREDICTIONS = original_predictions
    out["C03_float_row_swap"] = {"swapped_rows": [fn, fp], "columns": cols,
                               "file_sha_changed": digest["sha256"] != after["sha256"],
                               "exact_column_sha_unchanged": digest["exact_sha256"] == after["exact_sha256"],
                               "compare_predictions": compared,
                               "scope": "Fallback comparator only; unchanged full-run manifest would reject changed file bytes."}

split = D.split_normal(normal, D.segments(normal), "B")
reference = monitor.Reference.from_frame(pd.concat([split["train"], split["cal"]], ignore_index=True))
p = model.predict(ab)
windows = monitor.monitor_windows(p, ab, .01, len(model.cal), reference, window_units=5,
                                  operating_changes=[ab[D.TIME].iloc[0]])
kept, filtering = monitor.exclude_unconfirmed_windows(ab, windows)
window_cases = {}
for action in [monitor.ACTION_INSPECT, " " + monitor.ACTION_INSPECT, monitor.ACTION_RECALIBRATE,
               "재보정 검토(운전 조건 변경·수준 이동)"]:
    w = pd.DataFrame([dict(start=ab[D.TIME].iloc[0], end=ab[D.TIME].iloc[-1], recommended_action=action)])
    _, result = monitor.exclude_unconfirmed_windows(ab, w)
    window_cases[action] = result
out["C04_recalibration_windows"] = {"windows": windows[["window", "units", "alerted_units", "alarm_rows", "recommended_action"]].to_dict("records"),
                                  "filter_result": filtering, "action_string_cases": window_cases,
                                  "scope": "Filter eligibility only; not an executed recalibration or accepted replacement model."}

states = {}
for sid, model in models.items():
    p = model.predict(ab)
    alarms = p.loc[p.alarm.eq(1)].groupby("record_id", sort=False).first()
    records = p.groupby("record_id").size()
    states[sid] = {"abnormal_first_alarm_states": alarms.operating_state.value_counts().to_dict(),
                   "short_records_under_17": int(records.lt(17).sum()),
                   "records_reaching_state": int(records.ge(17).sum()),
                   "first_state_position": 16, "elapsed_from_first_row_seconds": 1.6}
out["C05_first_alarm_state"] = states

nyquist = {}
for win in [6, 8]:
    time = np.arange(win) * D.DT
    design = np.column_stack([np.sin(2*np.pi*5*time), np.cos(2*np.pi*5*time), np.ones(win)])
    sv = np.linalg.svd(design, compute_uv=False)
    default = design @ np.linalg.pinv(design)
    strict = design @ np.linalg.pinv(design, rcond=1e-10)
    nyquist[str(win)] = {"singular_values": sv.tolist(), "min_max_ratio": float(sv[-1]/sv[0]),
                        "default_hat_trace": float(np.trace(default)), "strict_hat_trace": float(np.trace(strict)),
                        "product_hat_equal": bool(np.array_equal(default, scores._hats(win)[-1]))}
q = D.quantize(ab, "matched")
seg = M.layout(q)[1]
cur = q[D.SENSORS[2]].to_numpy(float)
idx = M.window_index(seg, 8)
w = np.stack([cur[i-7:i+1] for i in idx])
sst = np.square(w-w.mean(axis=1, keepdims=True)).sum(axis=1)
hats = scores._hats(8)
best_old = np.full(len(w), np.inf)
best_corrected = np.full(len(w), np.inf)
for k, hat in enumerate(hats):
    residue = w-np.einsum("ij,kj->ik", w, hat, optimize=False)
    err = np.square(residue).sum(axis=1)
    best_old = np.minimum(best_old, err)
    if k < len(hats)-1:
        best_corrected = np.minimum(best_corrected, err)
time = np.arange(8)*D.DT
design = np.column_stack([np.sin(2*np.pi*5*time), np.cos(2*np.pi*5*time), np.ones(8)])
strict = design @ np.linalg.pinv(design, rcond=1e-10)
residue = w-np.einsum("ij,kj->ik", w, strict, optimize=False)
best_corrected = np.minimum(best_corrected, np.square(residue).sum(axis=1))
old, corrected = best_old/sst, best_corrected/sst
different = np.abs(old-corrected) > 1e-9
nyquist["abnormal_win8"] = {"changed_rows": int(different.sum()),
                            "median_old_changed": float(np.median(old[different])),
                            "median_corrected_changed": float(np.median(corrected[different])),
                            "max_score_delta": float(np.max(np.abs(old-corrected))),
                            "changed_original_row_ids": idx[different].tolist()}
out["A1_6_nyquist"] = nyquist

selection = pd.read_csv(ROOT / "yejun/analysis/press_selection/fp_mitigation_injection_v2.csv")
intensity = pd.read_csv(GUARD / "outputs/fn_intensity_v2.csv")
out["C06_distinct_injection_experiments"] = {
    "selection": selection[selection.split_id.eq("A") & selection.family.eq("vib_noise") & selection.level.eq(2) & selection.alpha.eq(.01)].to_dict("records"),
    "intensity": intensity[intensity.split.eq("A") & intensity.family.eq("vib_noise") & intensity.level_value.eq(2)][["detect_mean", "injection_repeats", "injection_seed_start", "injection_seed_end"]].to_dict("records"),
    "source_note": "selection/run.py:418-422 fixes 5 repeats; selection/README.md:56 discloses 5 repeats, :139 different random draws vs E1."}

target = Path(__file__).with_suffix(".json")
target.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
