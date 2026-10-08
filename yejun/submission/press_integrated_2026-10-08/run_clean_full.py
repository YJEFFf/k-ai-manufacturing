"""Run one archive end to end in a fresh extraction and write a clean-run record.

    python run_clean_full.py --archive 북적북적_code_통합본_run.zip --python <venv python> --workdir <short temp path> --record-dir verification_final

The archive is extracted outside the repository, `python check_bundled.py` and `python run_all.py`
(default: official 26 steps, improvement study, added audits, tests) run once with the given interpreter,
and the step summary, reference comparisons and environment are saved as clean_full_run.json.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

HERE = Path(__file__).resolve().parent
NAME = "북적북적_code_통합본"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--record-dir", type=Path, required=True)
    args = parser.parse_args()
    archive = (HERE / args.archive).resolve() if not args.archive.is_absolute() else args.archive
    if args.workdir.exists():
        shutil.rmtree(args.workdir)
    args.workdir.mkdir(parents=True)
    with zipfile.ZipFile(archive) as handle:
        assert handle.testzip() is None
        handle.extractall(args.workdir)
    root = args.workdir / NAME
    env_info = subprocess.run([str(args.python), "-c", "import sys,platform;print(sys.version);print(platform.platform())"],
                              capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    freeze = subprocess.run([str(args.python), "-m", "pip", "freeze"], capture_output=True, text=True, encoding="utf-8").stdout
    pip_check = subprocess.run([str(args.python), "-m", "pip", "check"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    bundled = subprocess.run([str(args.python), "check_bundled.py"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    run = subprocess.run([str(args.python), "run_all.py"], cwd=root, capture_output=True, text=True, encoding="utf-8")
    seconds = round(time.perf_counter() - t0, 1)
    summary_path = root / "logs/integrated_run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
    official_log = (root / "logs/integrated_official.log").read_text(encoding="utf-8", errors="replace") if (root / "logs/integrated_official.log").is_file() else ""
    references = {group: json.loads((root / f"logs/extra_reference_{group}.json").read_text(encoding="utf-8"))
                  for group in ("improvement", "official") if (root / f"logs/extra_reference_{group}.json").is_file()}
    record = dict(
        archive_name=archive.name, archive_sha256=sha(archive), started_utc=started,
        finished_utc=datetime.now(timezone.utc).isoformat(), total_seconds=seconds,
        command="python run_all.py (default: official 26 steps, improvement study, added audits, tests)",
        extraction=str(root), interpreter=env_info, pip_check=pip_check,
        pip_freeze_sha256=hashlib.sha256(freeze.encode()).hexdigest(), pip_freeze=freeze.splitlines(),
        check_bundled=dict(returncode=bundled.returncode, output=bundled.stdout.splitlines()[-12:]),
        run_all=dict(returncode=run.returncode, stdout_tail=run.stdout.splitlines()[-40:], stderr_tail=run.stderr.splitlines()[-20:]),
        steps=summary["steps"] if summary else None, passed=bool(summary and summary.get("passed") and run.returncode == 0),
        official_comparison_line=[line for line in official_log.splitlines() if line.strip().startswith("대조")][-1:] or None,
        extra_reference=references,
        scope="Same previously observed data; reproduction of computations, not independent failure validation.")
    out = (HERE / args.record_dir) if not args.record_dir.is_absolute() else args.record_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "clean_full_run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(passed=record["passed"], total_seconds=seconds, steps=len(record["steps"] or [])), ensure_ascii=False))


if __name__ == "__main__":
    main()
