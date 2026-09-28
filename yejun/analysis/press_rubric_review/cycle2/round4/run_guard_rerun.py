"""Run from yejun. Preserve the initial model hashes and main metrics during the final rerun."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    logs = Path(__file__).resolve().parent
    initial = json.loads((logs / "initial_checks.json").read_text())
    out = Path("press_guard/outputs")
    before = {name: (out / name).read_bytes() for name in ("metrics.csv", "rolling.csv")}
    steps = [("train", ["press_guard/train.py", "--rolling"]), ("analyze", ["press_guard/analyze.py"]),
             ("audit", ["press_guard/audit.py"]), ("freeze", ["press_guard/verify.py", "--freeze"]),
             ("verify", ["press_guard/verify.py"])]
    results = []
    for name, command in steps:
        print(f"{args.prefix}: {name}", flush=True)
        started = time.monotonic()
        log = logs / f"{args.prefix}_{name}.log"
        with log.open("w", encoding="utf-8") as stream:
            rc = subprocess.run([sys.executable, *command], stdout=stream, stderr=subprocess.STDOUT).returncode
        result = dict(step=name, returncode=rc, seconds=round(time.monotonic() - started, 2))
        results.append(result)
        (logs / f"{args.prefix}_rerun.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        print(result, flush=True)
        if rc:
            print("\n".join(log.read_text().splitlines()[-25:]))
            return rc
        if name == "train":
            artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path("press_guard/artifacts").glob("*.json")}
            assert artifacts == initial["unchanged_model_artifact_sha256"]
            for file, content in before.items():
                pd.testing.assert_frame_equal(pd.read_csv(io.BytesIO(content)), pd.read_csv(out / file), check_exact=True)
            (logs / f"{args.prefix}_regression.json").write_text(json.dumps(dict(
                passed=True, model_and_probability_artifacts_unchanged=True,
                metrics_and_rolling_unchanged=True, artifact_sha256=artifacts), ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
