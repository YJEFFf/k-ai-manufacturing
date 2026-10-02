"""Reproduce this plan's data audits; no detector training or test performance."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true", help="acquire/reverify four data sources and the two NLN metadata documents")
    parser.add_argument("--with-source-caches", action="store_true", help="validate existing dated source-page snapshots; does not fetch new versions")
    args = parser.parse_args()
    jobs = []
    if args.acquire:
        jobs += [("acquire_data.py", ["--dataset", "core"]), ("acquire_nln_metadata.py", [])]
    jobs += [(name, []) for name in ["audit_press.py", "audit_external.py", "reserve_skab_groups.py", "audit_espset.py"]]
    logs = HERE / "cache/reproduction"
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    rows = []
    for name, options in jobs:
        start = time.monotonic()
        result = subprocess.run([sys.executable, str(HERE / "scripts" / name), *options], cwd=ROOT,
                                env=env, capture_output=True, text=True)
        (logs / f"{name}.log").write_text(result.stdout + result.stderr)
        rows.append(dict(script=name, options=options, returncode=result.returncode,
                         elapsed_s=round(time.monotonic() - start, 3)))
        print(f"{name}: {'pass' if result.returncode == 0 else 'FAIL'}", flush=True)
        if result.returncode:
            print(result.stderr or result.stdout)
            raise SystemExit(result.returncode)
    record = dict(completed_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  scope="Acquisition/structural and historical numerical audits only; no new model outcomes.",
                  python=platform.python_version(), platform=platform.platform(),
                  installed_packages=dict(sorted((d.metadata["Name"], d.version) for d in importlib.metadata.distributions())),
                  steps=rows, validation_report="evidence/verification.json",
                  raw_source_pages_refetched=False)
    (HERE / "evidence/audit_run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    options = ["--with-data"] + (["--with-source-caches"] if args.with_source_caches else [])
    subprocess.run([sys.executable, str(HERE / "scripts/verify_package.py"), *options], cwd=ROOT,
                   env=env, check=True)


if __name__ == "__main__":
    main()
