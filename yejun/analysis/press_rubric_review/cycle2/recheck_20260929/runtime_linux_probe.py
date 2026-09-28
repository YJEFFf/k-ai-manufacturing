"""Targeted Linux numerical/retraining check in an isolated container copy.

This does not run/freeze the product pipeline. JSON models and prediction CSVs are
written only into a TemporaryDirectory; stdout is the small review result.
"""
from pathlib import Path
import json
import platform
import sys
import tempfile

import numpy as np
import pandas as pd

root = Path(sys.argv[1])
guard = root / "yejun/press_guard"
sys.path.insert(0, str(guard))
import runtime
runtime.setup()
import model as M
sys.path.insert(0, str(guard))
import train
import verify
from press import scores

D = M.D
normal, abnormal, report = D.load()
hashes = {k: v["sha256"] for k, v in report["files"].items()}
expected = json.loads((guard / "outputs/expected/predictions_digest.json").read_text())
out = {"environment": {"platform": platform.platform(), "python": platform.python_version(),
                       "machine": platform.machine(), "numpy": np.__version__, "pandas": pd.__version__},
       "splits": {}}
out["nyquist_trace"] = {str(w): float(np.trace(scores._hats(w)[-1])) for w in (6, 8)}


def compare(sid, model, part):
    pred = model.predict(part)
    pred["probability_source"] = "deployment_calibrator"
    with tempfile.TemporaryDirectory(prefix="press-numerics-") as scratch:
        path = Path(scratch) / f"predictions_normal_{sid}.csv"
        pred.to_csv(path, index=False)
        digest = verify.prediction_digest(path)
    exp = expected[f"predictions_normal_{sid}.csv"]
    fails = {c: {"expected": exp["numeric_summary"][c], "actual": digest["numeric_summary"][c]}
             for c in exp["numeric_summary"] if not verify._close(exp["numeric_summary"][c], digest["numeric_summary"][c])}
    baseline = pd.read_csv(guard / "outputs" / f"predictions_normal_{sid}.csv")
    details = {}
    for c in ("score", "g_waveform", "sine6", "sine8", "p_value", "likelihood_ratio"):
        if c not in pred or c not in baseline:
            continue
        a, b = pred[c].to_numpy(float), baseline[c].to_numpy(float)
        delta = np.abs(a-b)
        details[c] = {"rows_changed_gt_1e9": int((delta>1e-9).sum()), "max_abs_delta": float(np.nanmax(delta))}
    return {"exact_columns_equal": digest["exact_sha256"] == exp["exact_sha256"],
            "nonfinite_positions_equal": digest["nonfinite_sha256"] == exp["nonfinite_sha256"],
            "failed_float_summaries": fails, "host_row_comparison": details,
            "normal_alarm_rows": int(pred.alarm.sum()),
            "abnormal_alarm_rows": int(model.predict(abnormal).alarm.sum())}


for sid in "AB":
    split = D.split_normal(normal, D.segments(normal), sid)
    frozen = M.load_bundle(guard / "artifacts" / f"guard_{sid}.json")
    loaded_result = compare(sid, frozen, split["test"])
    trained = M.GuardModel.fit(split["train"], split["cal"], split=sid, input_hashes=hashes)
    probability, _ = train.fit_probability(trained, split["cal"], abnormal, sid, hashes)
    trained.attach_probability(probability)
    with tempfile.TemporaryDirectory(prefix="press-retrained-") as scratch:
        model_path, probability_path = Path(scratch)/f"guard_{sid}.json", Path(scratch)/f"probability_{sid}.json"
        trained.save(model_path)
        probability.save(probability_path)
        saved_sha = {p.name: {"host": D.sha256_file(guard/"artifacts"/p.name), "retrained": D.sha256_file(p)} for p in (model_path, probability_path)}
    out["splits"][sid] = {"frozen_model_inference": loaded_result,
                          "local_refit_inference": compare(sid, trained, split["test"]), "artifacts": saved_sha}

# Diagnostic ablation in this process only: correct only the final Nyquist hat.
# This is a causation test, not a product change or an accepted fix.
original_hats = M._hats
corrected = {}
for win in (6, 8):
    h = original_hats(win).copy()
    t = np.arange(win)*D.DT
    a = np.column_stack([np.sin(2*np.pi*5*t), np.cos(2*np.pi*5*t), np.ones(win)])
    h[-1] = a @ np.linalg.pinv(a, rcond=1e-10)
    corrected[win] = h
M._hats = lambda win: corrected.get(win, original_hats(win))
for sid in "AB":
    split = D.split_normal(normal, D.segments(normal), sid)
    model = M.GuardModel.fit(split["train"], split["cal"], split=sid, input_hashes=hashes)
    probability, _ = train.fit_probability(model, split["cal"], abnormal, sid, hashes)
    model.attach_probability(probability)
    out["splits"][sid]["nyquist_only_ablation_refit"] = compare(sid, model, split["test"])
print(json.dumps(out, ensure_ascii=False, indent=2))
