"""Single command: restored inputs -> development -> freeze -> heldout -> audit."""
import argparse
from pathlib import Path
import json
import pickle
import subprocess
import sys

from common import HERE, save, environment, now
import skab
import press
import diagnostics
import heldout
import compare_junyong
import verify_results
import benchmark


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["all", "development", "freeze", "test", "verify"])
    parser.add_argument("--output", type=Path, default=HERE / "evidence")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.mode in ["all", "development"]:
        subprocess.run([sys.executable, "-X", "utf8", "-m", "pytest", str(HERE / "test_execution.py"), "-q"], check=True)
        skab.development(output)
        selection, states = press.development(output)
        diagnostics.probability(output, selection)
        diagnostics.policies(output, selection, states)
        compare_junyong.historical(output)
    if args.mode in ["all", "freeze"]:
        heldout.freeze(output)
        print("Candidate and policy freeze saved", flush=True)
    if args.mode in ["all", "test"]:
        heldout.verify_freeze(output)
        heldout.evaluate(output)
        skab.test(output)
    if args.mode in ["all", "verify"]:
        verification = verify_results.verify(output)
        benchmark.run(output)
        save(output / "completion.json", dict(design_closed=True, implementation_complete=verification["all_passed"],
             candidate_admitted=verification["candidate_admitted"], external_evaluated=True, field_validated=False,
             Beihang_optional="not_run; external conclusion restricted to SKAB", report_or_slides_written=False,
             completed_utc=now(), environment=environment(), cold_reproduction="separate comparison receipt required"))


if __name__ == "__main__":
    main()
