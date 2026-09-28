"""Independent R4 reproducibility probes; writes only review records and a temporary copy.

Run from the repository root:
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
  yejun/analysis/press_rubric_review/cycle2/round4/judge06_preflight.py
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

import pandas as pd
from markdown_it import MarkdownIt


ROOT = Path.cwd()
REPORT = Path(__file__).resolve().parent
SCRATCH = Path((REPORT / "judge06_scratch.txt").read_text(encoding="utf-8").strip())
ENV = {**os.environ, "OMP_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
RESULT = {"phase": "preflight before final regeneration", "python": sys.version, "probes": []}


def record(name, **kwargs):
    row = dict(name=name, **kwargs)
    RESULT["probes"].append(row)
    print(json.dumps(row, ensure_ascii=False), flush=True)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


package = load_module("independent_package", ROOT / "yejun/press_guard/tools/package_manifest.py")
table = package.collect()
snapshot = SCRATCH / "preflight_no_git"
snapshot.mkdir()
excluded = []
for rel in table.path:
    # A fresh checkout has no raw data, fitted artifacts, or generated predictions.
    if "/artifacts/" in rel or "/data/" in rel or re.search(r"/outputs/(test_)?predictions_", rel):
        excluded.append(rel)
        continue
    src, dst = ROOT / rel, snapshot / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
record("snapshot", files=len(table) - len(excluded), excluded=excluded, git_present=(snapshot / ".git").exists())

for condition in ("no_inputs", "raw_data_only"):
    if condition == "raw_data_only":
        for group, rel in package.GENERATED:
            if group == "training_data":
                dst = snapshot / "yejun" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / "yejun" / rel, dst)
    for name in ("evidence", "advance", "supervised", "selection", "supplement"):
        relative = f"yejun/analysis/press_{name}/test_contract.py"
        cmd = [sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider", relative]
        started = time.monotonic()
        proc = subprocess.run(cmd, cwd=snapshot, env=ENV, capture_output=True, text=True, encoding="utf-8")
        text = proc.stdout + proc.stderr
        logfile = REPORT / f"judge06_preflight_{condition}_{name}.log"
        logfile.write_text("$ " + " ".join(cmd) + "\n" + text, encoding="utf-8")
        record(f"prerequisite_{condition}_{name}", returncode=proc.returncode,
               seconds=round(time.monotonic() - started, 2), skipped="skipped" in text,
               guidance="reproduce.py" in text, traceback="Traceback" in text,
               tail=text.strip().splitlines()[-1], log=logfile.name)

# Read independently with a CommonMark parser instead of the package's regular expressions.
md = MarkdownIt()
included = {(ROOT / p).resolve() for p in table.path}
links, broken, markers = [], [], []
for rel in table.path:
    p = ROOT / rel
    if p.suffix == ".md":
        body = p.read_text(encoding="utf-8")
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
            resolved = (p.parent / unquote(parsed.path)).resolve()
            valid = resolved in included or (resolved.is_dir() and any(resolved in q.parents for q in included))
            item = dict(document=rel, target=target, included=valid)
            links.append(item)
            if not valid:
                broken.append(item)
        markers.extend(dict(file=rel, line=i, text=s) for i, s in enumerate(body.splitlines(), 1)
                       if re.search(r"루브릭|사이클[ ]?2|평가관|press_rubric_review|press_implementation_review", s))
    elif p.name == "requirements-lock.txt":
        markers.extend(dict(file=rel, line=i, text=s) for i, s in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                       if re.search(r"루브릭|사이클[ ]?2|평가관|press_rubric_review|press_implementation_review", s))
record("documents", package_files=len(table), local_links=len(links), broken=broken,
       internal_markers=markers, package_blind_checks=package.blind_checks(table))

# Probe the actual package link check on the copied documentation, never on the workspace.
package.REPO = snapshot
package.YEJUN = snapshot / "yejun"
package.HERE = snapshot / "yejun/press_guard"
doc = snapshot / "yejun/press_guard/README.md"
doc.write_text(doc.read_text(encoding="utf-8") + "\n[broken probe](judge06_missing_file.csv)\n", encoding="utf-8")
link_failures = package.document_link_checks(table)
record("broken_document_probe", caught=any("judge06_missing_file.csv" in x for x in link_failures), failures=link_failures)

sys.path.insert(0, str(ROOT / "yejun/press_guard"))
import verify

# Final regeneration has not happened. Add the new digest lock only to this scratch baseline.
expected = SCRATCH / "preflight_expected"
shutil.copytree(ROOT / "yejun/press_guard/outputs/expected", expected)
mp = expected / "manifest.json"
manifest = json.loads(mp.read_text(encoding="utf-8"))
digest_path = expected / verify.DIGEST
manifest["prediction_digest_sha256"] = hashlib.sha256(digest_path.read_bytes()).hexdigest()
mp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
baseline_errors = verify.expected_integrity(expected)
record("scratch_digest_baseline", errors=baseline_errors)
original = digest_path.read_bytes()
for field in ("alarm_rows", "sha256", "exact_sha256"):
    data = json.loads(original)
    first = next(iter(data))
    data[first][field] = int(data[first][field]) + 1 if field == "alarm_rows" else "0" * 64
    digest_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    errors = verify.expected_integrity(expected)
    record(f"digest_tamper_{field}", caught=any(verify.DIGEST in s for s in errors), errors=errors)
    digest_path.write_bytes(original)

pred_dir = SCRATCH / "preflight_prediction"
pred_dir.mkdir()
exp_dir = pred_dir / "expected"
exp_dir.mkdir()
filename = "test_predictions_B.csv"
base = pd.read_csv(ROOT / "yejun/press_guard/outputs" / filename)
base.to_csv(pred_dir / filename, index=False)
base_digest = verify.prediction_digest(pred_dir / filename)
(exp_dir / verify.DIGEST).write_text(json.dumps({filename: base_digest}), encoding="utf-8")
verify.PREDICTIONS = (filename,)
record("prediction_baseline", result=verify.compare_predictions(pred_dir, exp_dir), exact_columns=base_digest["exact_columns"])
for column in ("incident_id", "incident_notification", "incident_escalation", "magnitude_sensor", "timestamp", "probability_source"):
    frame = base.copy()
    pairs = frame[column].drop_duplicates().index.tolist()
    assert len(pairs) >= 2, column
    a, b = pairs[:2]
    frame.loc[[a, b], column] = frame.loc[[b, a], column].to_numpy()
    frame.to_csv(pred_dir / filename, index=False)
    result = verify.compare_predictions(pred_dir, exp_dir)
    record(f"exact_column_swap_{column}", caught=not result[0]["ok"], result=result)

for column, multiplier in (("score", 1.0), ("likelihood_ratio", 1.001)):
    frame = base.copy()
    index = frame[column].first_valid_index()
    frame.loc[index, column] = frame.loc[index, column] * multiplier + (1e-4 if column == "score" else 0)
    frame.to_csv(pred_dir / filename, index=False)
    result = verify.compare_predictions(pred_dir, exp_dir)
    record(f"documented_float_tolerance_{column}", result=result)

# Additional dtype inference protection: a new unknown categorical column is exact automatically.
frame = base.copy()
frame["future_text_field"] = ["state_a"] + ["state_b"] * (len(frame) - 1)
frame.to_csv(pred_dir / filename, index=False)
(exp_dir / verify.DIGEST).write_text(json.dumps({filename: verify.prediction_digest(pred_dir / filename)}), encoding="utf-8")
frame.loc[[0, 1], "future_text_field"] = ["state_b", "state_a"]
frame.to_csv(pred_dir / filename, index=False)
result = verify.compare_predictions(pred_dir, exp_dir)
record("unknown_text_column_swap", caught=not result[0]["ok"], result=result)

(REPORT / "judge06_preflight.json").write_text(json.dumps(RESULT, ensure_ascii=False, indent=2), encoding="utf-8")
