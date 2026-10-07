"""Reproduce the original submission and the normal-only improvement study."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from package_integrity import verify_package

ROOT = Path(__file__).resolve().parent
STUDY = ROOT / "yejun/analysis/press_improvement"
DATA = ROOT / "data/3_소성가공_예지보전"
LOGS = ROOT / "logs"


def execute(label, args, summary):
    start = time.perf_counter()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MPLBACKEND="Agg")
    logfile = LOGS / f"integrated_{label}.log"
    print(f"[{label}] running; log: {logfile.relative_to(ROOT)}", flush=True)
    with logfile.open("w", encoding="utf-8") as stream:
        completed = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT,
                                   env=env, stdout=stream, stderr=subprocess.STDOUT)
    summary["steps"].append(dict(name=label, returncode=completed.returncode,
                                  seconds=round(time.perf_counter() - start, 3),
                                  log=str(logfile.relative_to(ROOT))))
    save(summary)
    if completed.returncode:
        print(logfile.read_text(encoding="utf-8")[-12000:])
        raise SystemExit(completed.returncode)
    print(f"[{label}] passed in {summary['steps'][-1]['seconds']:.1f}s", flush=True)


def save(summary):
    (LOGS / "integrated_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=("all", "official", "improvement"), default="all")
    parser.add_argument("--quick", action="store_true", help="Use the original pipeline's quick subset; improvement still runs in full")
    parser.add_argument("--verify-only", action="store_true", help="Recheck existing outputs without regenerating the full experiment")
    parser.add_argument("--extra-audits", action="store_true", help="Also run precommitted strong baselines and normal-condition sensitivity audits")
    parser.add_argument("--extra-audits-only", action="store_true", help="Run added audits against existing validated improvement outputs, without repeating model selection")
    args = parser.parse_args()
    if args.extra_audits_only:
        if args.section != "improvement" or args.verify_only or args.quick:
            parser.error("--extra-audits-only requires --section improvement and cannot be combined with --quick or --verify-only")
        args.extra_audits = True
    if args.extra_audits and (args.verify_only or args.section == "official"):
        parser.error("--extra-audits requires a fresh improvement or all-section run")
    if args.extra_audits:
        for filename in ("audit_strong_baselines.py", "audit_normal_sensitivity.py", "verify_normal_sensitivity.py"):
            if not (STUDY / filename).is_file():
                parser.error(f"This archive does not include the requested audit: {filename}")
    LOGS.mkdir(exist_ok=True)
    summary = dict(section=args.section, quick=args.quick, verify_only=args.verify_only, extra_audits=args.extra_audits,
                   extra_audits_only=args.extra_audits_only,
                   python=sys.version, integrity=verify_package(), steps=[], passed=False)
    save(summary)
    if args.section in ("all", "official"):
        if args.verify_only:
            execute("official_verify", [ROOT / "verify_official.py", *( ["--quick"] if args.quick else [])], summary)
        else:
            execute("official", [ROOT / "run_official.py", *( ["--quick"] if args.quick else [])], summary)
    if args.section in ("all", "improvement"):
        if not args.verify_only and not args.extra_audits_only:
            execute("improvement", [STUDY / "run_experiment.py", "--data-dir", DATA,
                                      "--output", STUDY / "outputs", "--phase", "all"], summary)
        if not args.extra_audits_only:
            execute("metrics", [STUDY / "verify_results.py", "--output", STUDY / "outputs"], summary)
            execute("replay", [STUDY / "verify_replay.py", "--data-dir", DATA,
                                "--output", STUDY / "outputs"], summary)
        execute("reference", [ROOT / "verify_improvement.py"], summary)
        if not args.extra_audits_only:
            execute("independent", [STUDY / "validate_holdout.py", "audit", "--data-dir", DATA,
                                     "--experiment-output", STUDY / "outputs"], summary)
        if not args.verify_only and not args.extra_audits_only:
            execute("freeze", [STUDY / "validate_holdout.py", "freeze", "--data-dir", DATA,
                                "--experiment-output", STUDY / "outputs",
                                "--artifact", STUDY / "outputs/frozen_holdout"], summary)
        if args.extra_audits:
            execute("strong_baselines", [STUDY / "audit_strong_baselines.py", "--data-dir", DATA,
                                          "--parent-output", STUDY / "outputs",
                                          "--output", STUDY / "outputs/strong_baselines", "--phase", "all"], summary)
            execute("normal_sensitivity", [STUDY / "audit_normal_sensitivity.py", "--data-dir", DATA,
                                            "--experiment-output", STUDY / "outputs",
                                            "--output", STUDY / "outputs/normal_sensitivity"], summary)
            execute("normal_aggregation", [STUDY / "verify_normal_sensitivity.py",
                                            "--experiment-output", STUDY / "outputs",
                                            "--output", STUDY / "outputs/normal_sensitivity"], summary)
        execute("tests", ["-m", "pytest", "-q", STUDY / "tests"], summary)
    required = []
    if args.section in ("all", "official"):
        required.append("official_verify" if args.verify_only else "official")
    if args.section in ("all", "improvement"):
        required.extend((["improvement"] if not args.verify_only and not args.extra_audits_only else []) +
                        (["metrics", "replay"] if not args.extra_audits_only else []) + ["reference"] +
                        (["independent"] if not args.extra_audits_only else []) +
                        (["freeze"] if not args.verify_only and not args.extra_audits_only else []) +
                        (["strong_baselines", "normal_sensitivity", "normal_aggregation"] if args.extra_audits else []) + ["tests"])
    assert [step["name"] for step in summary["steps"]] == required
    assert all(step["returncode"] == 0 for step in summary["steps"])
    summary["required_steps"] = required
    summary["passed"] = True
    save(summary)
    print(("Added audits passed; this run did not repeat the base experiment. " if args.extra_audits_only
           else "Integrated reproduction passed. ") + "See logs/integrated_run_summary.json", flush=True)


if __name__ == "__main__":
    main()
