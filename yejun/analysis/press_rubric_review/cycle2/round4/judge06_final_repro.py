"""Run only after the parent confirms the final review may start.

A separate lock-only venv recreates the final pipeline from source without Git,
fitted artifacts, raw data, or current v2 computed outputs. Frozen expected files
and the pre-rendered console screenshots used as documentation remain.
The organizer ZIP is the sole runtime input. No workspace implementation is edited.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import time


ROOT = Path.cwd()
REPORT = Path(__file__).resolve().parent
SCRATCH = Path((REPORT / "judge06_scratch.txt").read_text(encoding="utf-8").strip())
DEST = SCRATCH / "final_source_no_git"
PYTHON = SCRATCH / "clean_venv/bin/python"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


environment = json.loads((REPORT / "judge06_environment.json").read_text(encoding="utf-8"))
assert environment["ready"] and sha(ROOT / "yejun/press_guard/requirements-lock.txt") == environment["lock_sha256"]
spec = importlib.util.spec_from_file_location("package_final", ROOT / "yejun/press_guard/tools/package_manifest.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
table = package.collect()
DEST.mkdir()
copied, skipped = [], []
for rel in table.path:
    if ("/artifacts/" in rel or "/data/" in rel or re.search(r"/outputs/(test_)?predictions_", rel)
            or (rel.startswith("yejun/press_guard/outputs/") and not rel.startswith(("yejun/press_guard/outputs/expected/", "yejun/press_guard/outputs/console/")))):
        skipped.append(rel)
        continue
    source, target = ROOT / rel, DEST / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied.append(dict(path=rel, sha256=sha(target), bytes=target.stat().st_size))

source_zip = next((ROOT / "데이터셋/프레스_유압펌프_예지보전").glob("Dataset_*.zip"))
local_zip = SCRATCH / source_zip.name
shutil.copy2(source_zip, local_zip)
assert sha(source_zip) == sha(local_zip)
# The same sole input ZIP is also discoverable by test_install_data_from_organizer_zip.
# This exercises that optional test instead of skipping it merely because of the snapshot layout.
test_zip = DEST / "데이터셋/프레스_유압펌프_예지보전" / source_zip.name
test_zip.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(local_zip, test_zip)

expected = DEST / "yejun/press_guard/outputs/expected/manifest.json"
frozen_manifest = json.loads(expected.read_text(encoding="utf-8"))
assert frozen_manifest.get("prediction_digest_sha256"), "Final regenerated digest lock is mandatory before final review."
setup = dict(head=git("rev-parse", "HEAD").strip(), status=git("status", "--short"), files=copied, excluded=skipped,
             organizer_zip_sha256=sha(local_zip), organizer_zip=local_zip.name,
             organizer_zip_visible_to_install_test=True,
             original_artifacts={p.name: sha(p) for p in (ROOT / "yejun/press_guard/artifacts").glob("*.json")},
             original_predictions={p.name: sha(p) for p in (ROOT / "yejun/press_guard/outputs").glob("*predictions_*.csv")},
             round3_artifacts=json.loads(git("show", "061fac8:yejun/press_guard/outputs/expected/manifest.json"))["artifacts"],
             load_start=os.getloadavg(), no_git=not (DEST / ".git").exists(), python=str(PYTHON), snapshot=str(DEST))
(REPORT / "judge06_final_setup.json").write_text(json.dumps(setup, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: setup[k] for k in ("head", "no_git", "snapshot", "load_start", "organizer_zip_sha256")}, ensure_ascii=False), flush=True)
print(f"Source files copied: {len(copied)}; generated/data/model files excluded: {len(skipped)}", flush=True)

env = {**os.environ, "OMP_NUM_THREADS": "1", "PRESS_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1",
       "PYTHONNOUSERSITE": "1", "PYTHONPATH": "", "MPLCONFIGDIR": str(SCRATCH / "mplconfig"),
       "PIP_CACHE_DIR": str(SCRATCH / "pip_cache")}
command = [str(PYTHON), "yejun/press_guard/reproduce.py", "--data", str(local_zip), "--tests"]
start = time.monotonic()
log = REPORT / "judge06_final_repro.log"
with log.open("w", encoding="utf-8") as stream:
    stream.write("$ " + " ".join(command) + "\n")
    stream.flush()
    proc = subprocess.Popen(command, cwd=DEST, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    for line in proc.stdout:
        stream.write(line)
        stream.flush()
        print(line, end="", flush=True)
    rc = proc.wait()
summary_file = DEST / "yejun/press_guard/outputs/reproduce_summary.json"
summary = json.loads(summary_file.read_text(encoding="utf-8")) if summary_file.is_file() else None
result = dict(returncode=rc, seconds=round(time.monotonic() - start, 2), load_end=os.getloadavg(),
              workspace_head_after=git("rev-parse", "HEAD").strip(), summary=summary)
(REPORT / "judge06_final_repro.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
if summary is not None:
    for source in (DEST / "yejun/press_guard/outputs/reproduce_logs").glob("*.log"):
        shutil.copy2(source, REPORT / f"judge06_final_step_{source.stem}.log")
print(json.dumps({k: result[k] for k in ("returncode", "seconds", "load_end", "workspace_head_after")}, ensure_ascii=False), flush=True)
raise SystemExit(rc)
