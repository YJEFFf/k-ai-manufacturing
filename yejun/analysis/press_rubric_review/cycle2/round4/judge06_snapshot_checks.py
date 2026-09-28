"""Snapshot current regenerated run for read-only document and digest-mutation checks."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


root = Path.cwd()
report = Path(__file__).resolve().parent
scratch = Path((report / "judge06_scratch.txt").read_text(encoding="utf-8").strip())
dest = Path(tempfile.mkdtemp(prefix="regenerated_snapshot_", dir=scratch))


def load_package(repo, module_name):
    spec = importlib.util.spec_from_file_location(module_name, repo / "yejun/press_guard/tools/package_manifest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package = load_package(root, "source_package")
table = package.collect()
paths = set(table.path)
paths |= {f"yejun/press_guard/outputs/predictions_{kind}_{split}.csv" for kind in ("normal", "abnormal") for split in "AB"}
paths |= {f"yejun/press_submission/outputs/predictions_{split}.csv" for split in "AB"}
inventory = []
for rel in sorted(paths):
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / rel, target)
    inventory.append(dict(path=rel, sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
result = dict(snapshot=str(dest), inventory=inventory)
env = {**os.environ, "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "", "MPLCONFIGDIR": str(scratch / "mplconfig_snapshot")}
digest_path = dest / "yejun/press_guard/outputs/expected/predictions_digest.json"
original = digest_path.read_bytes()
checks = []
for field in (None, "alarm_rows", "sha256", "exact_sha256"):
    tag = field or "baseline"
    if field:
        data = json.loads(original)
        first = next(iter(data))
        data[first][field] = int(data[first][field]) + 1 if field == "alarm_rows" else "0" * 64
        digest_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run([sys.executable, "yejun/press_guard/verify.py"], cwd=dest, env=env, capture_output=True, text=True, encoding="utf-8")
    text = proc.stdout + proc.stderr
    (report / f"judge06_regenerated_digest_{tag}.log").write_text(text, encoding="utf-8")
    check = dict(mutation=tag, returncode=proc.returncode, failure_lines=[s for s in text.splitlines() if s.startswith("FAIL")])
    checks.append(check)
    print(json.dumps(check, ensure_ascii=False), flush=True)
    digest_path.write_bytes(original)
result["full_verify"] = checks

package = load_package(dest, "snapshot_package")
table = package.collect()
included = {(dest / rel).resolve() for rel in table.path}
md, links, broken, markers = MarkdownIt(), [], [], []
for rel in table.path:
    path = dest / rel
    if path.suffix == ".md":
        body = path.read_text(encoding="utf-8")
        stack = list(md.parse(body))
        while stack:
            token = stack.pop()
            stack.extend(token.children or [])
            target = token.attrGet("href") if token.type == "link_open" else token.attrGet("src") if token.type == "image" else None
            if not target:
                continue
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            present = resolved in included or (resolved.is_dir() and any(resolved in p.parents for p in included))
            item = dict(document=rel, target=target, present=present)
            links.append(item)
            if not present:
                broken.append(item)
        markers.extend(dict(file=rel, line=i, text=s) for i, s in enumerate(body.splitlines(), 1)
                       if re.search(r"루브릭|사이클[ ]?2|평가관|press_rubric_review|press_implementation_review", s))
    elif path.name == "requirements-lock.txt":
        markers.extend(dict(file=rel, line=i, text=s) for i, s in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                       if re.search(r"루브릭|사이클[ ]?2|평가관|press_rubric_review|press_implementation_review", s))
result["documents"] = dict(files=len(table), local_links=len(links), broken=broken, internal_markers=markers, package_checks=package.blind_checks(table))
print(json.dumps(result["documents"], ensure_ascii=False), flush=True)

proc = subprocess.run([sys.executable, str(report / "judge06_nonfinite_probe.py"), "--source", str(dest), "--tag", "regenerated", "--frozen"],
                      cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
(report / "judge06_nonfinite_regenerated.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
result["nonfinite_probe_returncode"] = proc.returncode
(report / "judge06_regenerated_snapshot.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("Snapshot:", dest, flush=True)
