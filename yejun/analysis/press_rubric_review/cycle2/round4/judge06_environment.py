"""Build a clean lock-only Python environment for the independent final reproduction."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time

root = Path.cwd()
report = Path(__file__).resolve().parent
scratch = Path((report / "judge06_scratch.txt").read_text(encoding="utf-8").strip())
venv = scratch / "clean_venv"
base_python = Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12")
lock = root / "yejun/press_guard/requirements-lock.txt"
env = {**os.environ, "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONPATH": "",
       "PIP_CACHE_DIR": str(scratch / "pip_cache")}
commands = [
    [str(base_python), "-m", "venv", str(venv)],
    [str(venv / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "-r", str(lock)],
    [str(venv / "bin/python"), "-m", "pip", "check"],
    [str(venv / "bin/python"), "-m", "pip", "freeze"],
    [str(venv / "bin/python"), "-c", "import sys,importlib.util,json; print(json.dumps({'version':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'torch_present':bool(importlib.util.find_spec('torch')),'sys_path':sys.path},indent=2))"],
]
results = []
started = time.monotonic()
for i, cmd in enumerate(commands):
    now = time.monotonic()
    proc = subprocess.run(cmd, cwd=scratch, env=env, capture_output=True, text=True, encoding="utf-8")
    log = report / f"judge06_environment_{i}.log"
    log.write_text("$ " + " ".join(cmd) + "\n" + proc.stdout + proc.stderr, encoding="utf-8")
    result = dict(command=cmd, returncode=proc.returncode, seconds=round(time.monotonic() - now, 2), log=log.name)
    results.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    if proc.returncode:
        break
(report / "judge06_environment.json").write_text(json.dumps(dict(
    lock_sha256=hashlib.sha256(lock.read_bytes()).hexdigest(), total_seconds=round(time.monotonic() - started, 2),
    results=results, ready=len(results) == len(commands) and all(r["returncode"] == 0 for r in results)),
    ensure_ascii=False, indent=2), encoding="utf-8")
