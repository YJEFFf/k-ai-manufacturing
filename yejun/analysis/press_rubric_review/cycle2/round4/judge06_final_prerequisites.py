"""Recheck prerequisite skips against the exact final source after the new runtime fixes."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

report = Path(__file__).resolve().parent
setup = json.loads((report / "judge06_final_setup.json").read_text(encoding="utf-8"))
source = Path(setup["snapshot"])
scratch = Path((report / "judge06_scratch.txt").read_text(encoding="utf-8").strip())
dest = Path(tempfile.mkdtemp(prefix="final_prereq_", dir=scratch))
shutil.copytree(source / "yejun", dest / "yejun", ignore=shutil.ignore_patterns("data", "artifacts", "__pycache__", ".pytest_cache", "reproduce_logs"))
env = {**os.environ, "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "", "MPLCONFIGDIR": str(scratch / "mplconfig")}
results = []
for condition in ("no_inputs", "raw_data_only"):
    if condition == "raw_data_only":
        shutil.copytree(source / "yejun/press_submission/data", dest / "yejun/press_submission/data")
    for package in ("evidence", "advance", "supervised", "selection", "supplement"):
        cmd = [sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider", f"yejun/analysis/press_{package}/test_contract.py"]
        proc = subprocess.run(cmd, cwd=dest, env=env, capture_output=True, text=True, encoding="utf-8")
        output = proc.stdout + proc.stderr
        log = report / f"judge06_final_prereq_{condition}_{package}.log"
        log.write_text("$ " + " ".join(cmd) + "\n" + output, encoding="utf-8")
        result = dict(condition=condition, package=package, returncode=proc.returncode,
                      skipped="skipped" in output, guidance="reproduce.py" in output,
                      traceback="Traceback" in output, last_line=output.strip().splitlines()[-1], log=log.name)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
(report / "judge06_final_prerequisites.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
assert all(x["returncode"] == 0 and x["skipped"] and x["guidance"] and not x["traceback"] for x in results)
