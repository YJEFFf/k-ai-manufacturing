"""Independent real-prediction probes for nonfinite kinds and positions.

Use --source <copy root> after the final reproduction and --tag final to retain
both pre-fix and post-fix evidence. No implementation or expected file is edited.
"""
from pathlib import Path
import argparse
import json
import re
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd


ap = argparse.ArgumentParser()
ap.add_argument("--source", type=Path, default=Path.cwd())
ap.add_argument("--tag", default="pre")
ap.add_argument("--frozen", action="store_true", help="Compare against the supplied run's actual frozen digest.")
args = ap.parse_args()
assert re.fullmatch(r"[a-z0-9_]+", args.tag)
report = Path(__file__).resolve().parent
base = Path((report / "judge06_scratch.txt").read_text(encoding="utf-8").strip())
scratch = Path(tempfile.mkdtemp(prefix=f"nonfinite_{args.tag}_", dir=base))
sys.path.insert(0, str(args.source / "yejun/press_guard"))
import verify

name = "test_predictions_B.csv"
frame = pd.read_csv(args.source / "yejun/press_guard/outputs" / name)
nonfinite = {c: int((~np.isfinite(frame[c].to_numpy(float))).sum()) for c in frame.select_dtypes("float").columns}
expected = scratch / "expected"
expected.mkdir()
frame.to_csv(scratch / name, index=False)
if args.frozen:
    shutil.copy2(args.source / "yejun/press_guard/outputs/expected" / verify.DIGEST, expected / verify.DIGEST)
else:
    (expected / verify.DIGEST).write_text(json.dumps({name: verify.prediction_digest(scratch / name)}), encoding="utf-8")
verify.PREDICTIONS = (name,)
baseline = verify.compare_predictions(scratch, expected)
assert baseline[0]["ok"], baseline
results = []
for column in ("current_residual", "g_waveform", "g_dynamics"):
    index = frame.index[frame[column].isna()][0]
    other = frame.index[np.isfinite(frame[column].to_numpy(float))][0]
    for kind in ("NaN_to_posinf", "NaN_to_neginf", "NaN_position_swap"):
        changed = frame.copy()
        if kind == "NaN_position_swap":
            changed.loc[[index, other], column] = changed.loc[[other, index], column].to_numpy()
        else:
            changed.loc[index, column] = np.inf if kind == "NaN_to_posinf" else -np.inf
        changed.to_csv(scratch / name, index=False)
        result = verify.compare_predictions(scratch, expected)[0]
        row = dict(column=column, row=int(index), change=kind, caught=not result["ok"], result=result)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
(report / f"judge06_nonfinite_{args.tag}.json").write_text(json.dumps(dict(frozen_digest=args.frozen, baseline=baseline, nonfinite=nonfinite, results=results), ensure_ascii=False, indent=2), encoding="utf-8")
