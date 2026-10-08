"""Reproduce the original submission, the normal-only improvement study and the added audits.

    python run_all.py                     # everything (official 26 steps, improvement study, added audits)
    python run_all.py --skip-extra-audits # official + improvement study only
    python run_all.py --section official [--quick]
    python run_all.py --section improvement
    python run_all.py --verify-only       # recheck outputs of an earlier run in this folder
"""
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
IMPROVEMENT_AUDITS = ("audit_strong_baselines.py", "audit_normal_sensitivity.py", "verify_normal_sensitivity.py")


def utf8_console():
    """Korean Windows consoles and redirected output default to cp949; never fail while printing a log."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def execute(label, args, summary, extra_env=None):
    start = time.perf_counter()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1",
               PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MPLBACKEND="Agg", **(extra_env or {}))
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
        print(logfile.read_text(encoding="utf-8", errors="replace")[-12000:])
        raise SystemExit(completed.returncode)
    print(f"[{label}] passed in {summary['steps'][-1]['seconds']:.1f}s", flush=True)


def save(summary):
    (LOGS / "integrated_run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def expand(argument):
    return str(argument).replace("{ROOT}", str(ROOT)).replace("{DATA}", str(DATA)).replace("{STUDY}", str(STUDY))


def main():
    utf8_console()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--section", choices=("all", "official", "improvement"), default="all")
    parser.add_argument("--quick", action="store_true", help="Use the original pipeline's quick subset; improvement still runs in full")
    parser.add_argument("--verify-only", action="store_true", help="Recheck outputs of an earlier run in this folder (no regeneration)")
    parser.add_argument("--skip-extra-audits", action="store_true", help="Do not run the added audits (they run by default in full runs)")
    parser.add_argument("--extra-audits", action="store_true", help="Accepted for compatibility; added audits already run by default")
    parser.add_argument("--extra-audits-only", action="store_true", help="Run added improvement audits against existing validated improvement outputs")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "package_manifest.json").read_text(encoding="utf-8"))
    official_audits = manifest.get("official_audits", [])
    if args.extra_audits and args.skip_extra_audits:
        parser.error("--extra-audits and --skip-extra-audits cannot be combined")
    if args.extra_audits_only:
        if args.section != "improvement" or args.verify_only or args.quick:
            parser.error("--extra-audits-only requires --section improvement and cannot be combined with --quick or --verify-only")
    run_improvement_audits = args.extra_audits_only or (
        not args.skip_extra_audits and not args.verify_only and args.section in ("all", "improvement"))
    run_official_audits = (not args.skip_extra_audits and not args.verify_only and not args.quick
                           and args.section == "all" and bool(official_audits))
    if run_improvement_audits:
        for filename in IMPROVEMENT_AUDITS:
            if not (STUDY / filename).is_file():
                parser.error(f"This archive does not include the added audit: {filename}")
    if args.verify_only:
        missing = []
        if args.section in ("all", "official") and not (ROOT / "code/press/tvt/outputs/tvt_test.csv").is_file():
            missing.append("기존 파이프라인 결과(code/press/tvt/outputs)")
        if args.section in ("all", "improvement") and not (STUDY / "outputs/selection_lock.json").is_file():
            missing.append("개선 실험 결과(yejun/analysis/press_improvement/outputs)")
        if missing:
            print("--verify-only는 이 폴더에서 먼저 실행한 결과를 다시 검사한다. 아직 없는 결과: " + ", ".join(missing))
            print("처음 확인할 때는 설치 없이 'python check_bundled.py'를, 전체 재현은 'python run_all.py'를 실행한다.")
            raise SystemExit(2)
    LOGS.mkdir(exist_ok=True)
    summary = dict(section=args.section, quick=args.quick, verify_only=args.verify_only,
                   improvement_audits=run_improvement_audits, official_audits=run_official_audits,
                   extra_audits_only=args.extra_audits_only,
                   python=sys.version, integrity=verify_package(), steps=[], passed=False)
    save(summary)
    required = []

    def step(label, arguments, extra_env=None):
        required.append(label)
        execute(label, arguments, summary, extra_env)

    if args.section in ("all", "official"):
        if args.verify_only:
            step("official_verify", [ROOT / "verify_official.py", *(["--quick"] if args.quick else [])])
        else:
            step("official", [ROOT / "run_official.py", *(["--quick"] if args.quick else [])])
    if args.section in ("all", "improvement"):
        if not args.verify_only and not args.extra_audits_only:
            step("improvement", [STUDY / "run_experiment.py", "--data-dir", DATA,
                                 "--output", STUDY / "outputs", "--phase", "all"])
        if not args.extra_audits_only:
            step("metrics", [STUDY / "verify_results.py", "--output", STUDY / "outputs"])
            step("replay", [STUDY / "verify_replay.py", "--data-dir", DATA, "--output", STUDY / "outputs"])
        step("reference", [ROOT / "verify_improvement.py"])
        if not args.extra_audits_only:
            step("independent", [STUDY / "validate_holdout.py", "audit", "--data-dir", DATA,
                                 "--experiment-output", STUDY / "outputs"])
        if not args.verify_only and not args.extra_audits_only:
            step("freeze", [STUDY / "validate_holdout.py", "freeze", "--data-dir", DATA,
                            "--experiment-output", STUDY / "outputs",
                            "--artifact", STUDY / "outputs/frozen_holdout"])
        if run_improvement_audits:
            step("strong_baselines", [STUDY / "audit_strong_baselines.py", "--data-dir", DATA,
                                      "--parent-output", STUDY / "outputs",
                                      "--output", STUDY / "outputs/strong_baselines", "--phase", "all"])
            step("normal_sensitivity", [STUDY / "audit_normal_sensitivity.py", "--data-dir", DATA,
                                        "--experiment-output", STUDY / "outputs",
                                        "--output", STUDY / "outputs/normal_sensitivity"])
            step("normal_aggregation", [STUDY / "verify_normal_sensitivity.py",
                                        "--experiment-output", STUDY / "outputs",
                                        "--output", STUDY / "outputs/normal_sensitivity"])
            step("improvement_audit_reference", [ROOT / "verify_extra.py", "--group", "improvement"])
        step("tests", ["-m", "pytest", "-q", STUDY / "tests"])
    if run_official_audits:
        # Audits that read the official pipeline outputs created above (no model or rule is changed).
        for audit in official_audits:
            step(audit["name"], [expand(argument) for argument in audit["args"]],
                 {key: expand(value) for key, value in audit.get("env", {}).items()})
        step("official_audit_reference", [ROOT / "verify_extra.py", "--group", "official"])
    assert [item["name"] for item in summary["steps"]] == required
    assert all(item["returncode"] == 0 for item in summary["steps"])
    summary["required_steps"] = required
    summary["passed"] = True
    save(summary)
    print(("Added audits passed; this run did not repeat the base experiment. " if args.extra_audits_only
           else "Integrated reproduction passed. ") + "See logs/integrated_run_summary.json", flush=True)


if __name__ == "__main__":
    main()
