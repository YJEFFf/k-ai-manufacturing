"""Independent checks against the completed, immutable-source final copy."""
from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

import pandas as pd
from markdown_it import MarkdownIt


REPORT = Path(__file__).resolve().parent
SCRATCH = Path((REPORT / "judge06_scratch.txt").read_text(encoding="utf-8").strip())
SOURCE = SCRATCH / "final_source_no_git"
PYTHON = SCRATCH / "clean_venv/bin/python"
OUT = SOURCE / "yejun/press_guard/outputs"
SETUP = json.loads((REPORT / "judge06_final_setup.json").read_text(encoding="utf-8"))
RESULTS = []
os.environ.setdefault("MPLCONFIGDIR", str(SCRATCH / "mplconfig"))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def record(name, **kwargs):
    result = dict(name=name, **kwargs)
    RESULTS.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


for kind, directory in (("artifacts", SOURCE / "yejun/press_guard/artifacts"), ("predictions", OUT)):
    comparisons = {name: dict(expected=digest, actual=sha(directory / name), identical=sha(directory / name) == digest)
                   for name, digest in SETUP[f"original_{kind}"].items()}
    record(f"bit_identical_{kind}", all_identical=all(v["identical"] for v in comparisons.values()), files=comparisons)

round3_artifacts = {name: sha(SOURCE / "yejun/press_guard/artifacts" / name) == digest
                    for name, digest in SETUP["round3_artifacts"].items()}
record("stored_model_preserved_since_round3", baseline_commit="061fac8", all_identical=all(round3_artifacts.values()), files=round3_artifacts)

for split in "AB":
    pred = pd.read_csv(OUT / f"test_predictions_{split}.csv")
    tp = int((pred.label.eq(1) & pred.alarm.eq(1)).sum())
    fp = int((pred.label.eq(0) & pred.alarm.eq(1)).sum())
    fn = int((pred.label.eq(1) & pred.alarm.eq(0)).sum())
    f1 = 2 * tp / (2 * tp + fp + fn)
    normal = pred[pred.label.eq(0)]
    event_rows = pred.index[pred.incident_escalation.eq(1)].to_list()
    incidents = pd.read_csv(OUT / f"incidents_{split}.csv")
    saved_rows = incidents.loc[incidents.level.eq(2), "escalation_row"].astype(int).to_list()
    record(f"independent_metrics_{split}", rows=len(pred), abnormal_rows=int(pred.label.sum()), TP=tp, FP=fp, FN=fn, F1=f1,
           normal_records=int(normal.record_id.nunique()), normal_alert_records=int(normal.loc[normal.alarm.eq(1), "record_id"].nunique()),
           prediction_escalation_rows=event_rows, incident_escalation_rows=saved_rows,
           escalation_matches=sorted(event_rows) == sorted(saved_rows),
           escalation_missing_for_level1=int(incidents.loc[incidents.level.eq(1), "escalation_row"].isna().sum()),
           level1_incidents=int(incidents.level.eq(1).sum()))

immutable = [x for x in SETUP["files"] if "/expected/" in x["path"]
             or ("/outputs/" not in x["path"] and Path(x["path"]).suffix in (".py", ".md", ".txt", ".yml", ".js", ".cjs", ".css", ".html", ".sh"))]
changed = [x["path"] for x in immutable if not (SOURCE / x["path"]).is_file() or sha(SOURCE / x["path"]) != x["sha256"]]
record("immutable_sources_and_frozen_files", checked=len(immutable), changed=changed)

spec = importlib.util.spec_from_file_location("independent_final_package", SOURCE / "yejun/press_guard/tools/package_manifest.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
table = package.collect()
table.to_csv(REPORT / "judge06_final_file_list.csv", index=False)
listed = {(SOURCE / p).resolve() for p in table.path}
md = MarkdownIt()
links, broken, markers = [], [], []
for rel in table.path:
    path = SOURCE / rel
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
            good = resolved in listed or (resolved.is_dir() and any(resolved in q.parents for q in listed))
            item = dict(document=rel, target=target, present=good)
            links.append(item)
            if not good:
                broken.append(item)
        markers.extend(dict(file=rel, line=i, text=s) for i, s in enumerate(body.splitlines(), 1)
                       if re.search(r"루브릭|사이클[ ]?2|평가관|press_rubric_review|press_implementation_review", s))
    elif path.name == "requirements-lock.txt":
        markers.extend(dict(file=rel, line=i, text=s) for i, s in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                       if re.search(r"루브릭|사이클[ ]?2|평가관|press_rubric_review|press_implementation_review", s))
record("documents", package_files=len(table), megabytes=float(table.bytes.sum() / 2 ** 20), local_links=len(links), broken=broken,
       internal_markers=markers, package_blind_checks=package.blind_checks(table))

sys.path.insert(0, str(SOURCE / "yejun/press_guard"))
import verify

mutation = Path(tempfile.mkdtemp(prefix="final_mutation_", dir=SCRATCH))
copy_out = mutation / "outputs"
shutil.copytree(OUT, copy_out)
digest_path = copy_out / "expected" / verify.DIGEST
original = digest_path.read_bytes()
for field in ("alarm_rows", "sha256", "exact_sha256"):
    frozen = json.loads(original)
    first = next(iter(frozen))
    frozen[first][field] = int(frozen[first][field]) + 1 if field == "alarm_rows" else "0" * 64
    digest_path.write_text(json.dumps(frozen, ensure_ascii=False), encoding="utf-8")
    log = io.StringIO()
    with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        rc = verify.main(["--out", str(copy_out), "--artifacts", str(SOURCE / "yejun/press_guard/artifacts")])
    (REPORT / f"judge06_final_digest_{field}.log").write_text(log.getvalue(), encoding="utf-8")
    record(f"full_verify_digest_tamper_{field}", returncode=rc,
           failure_lines=[s for s in log.getvalue().splitlines() if s.startswith("FAIL")])
    digest_path.write_bytes(original)

filename = "test_predictions_B.csv"
baseline = pd.read_csv(OUT / filename)
verify.PREDICTIONS = (filename,)
for column in ("incident_id", "incident_notification", "incident_escalation", "magnitude_sensor", "timestamp", "probability_source", "operating_state"):
    frame = baseline.copy()
    a, b = frame[column].drop_duplicates().index.to_list()[:2]
    frame.loc[[a, b], column] = frame.loc[[b, a], column].to_numpy()
    frame.to_csv(copy_out / filename, index=False)
    result = verify.compare_predictions(copy_out, OUT / "expected")
    record(f"exact_column_swap_{column}", caught=not result[0]["ok"], result=result)

for column, multiplier in (("score", 1.0), ("likelihood_ratio", 1.001)):
    frame = baseline.copy()
    index = frame[column].first_valid_index()
    frame.loc[index, column] = frame.loc[index, column] * multiplier + (1e-4 if column == "score" else 0)
    frame.to_csv(copy_out / filename, index=False)
    record(f"documented_float_tolerance_{column}", result=verify.compare_predictions(copy_out, OUT / "expected"))

env = {**os.environ, "OMP_NUM_THREADS": "1", "PRESS_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONPATH": ""}
for split in "AB":
    prediction = SCRATCH / f"final_inference_only_{split}.csv"
    cmd = [str(PYTHON), "yejun/press_guard/predict.py", "--split", split, "--chunk", "7", "--out", str(prediction)]
    proc = subprocess.run(cmd, cwd=SOURCE, env=env, capture_output=True, text=True, encoding="utf-8")
    (REPORT / f"judge06_final_inference_{split}.log").write_text("$ " + " ".join(cmd) + "\n" + proc.stdout + proc.stderr, encoding="utf-8")
    record(f"saved_model_inference_{split}", returncode=proc.returncode,
           identical=prediction.is_file() and sha(prediction) == sha(OUT / f"test_predictions_{split}.csv"), stdout=proc.stdout.strip())

(REPORT / "judge06_final_checks.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
