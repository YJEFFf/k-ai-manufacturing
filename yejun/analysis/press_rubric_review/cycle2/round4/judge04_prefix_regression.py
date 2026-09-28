"""모의 화면의 관측 접두부 집계를 Python 사건/품질창 함수와 대조한다."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "press_guard"))
from model import D, layout, cases, incidents
from serve import Console

started = time.perf_counter()
console = Console()
n, _, _ = D.load()
b = D.inputs_only(D.split_normal(n, D.segments(n), "B")["test"]).reset_index(drop=True)
seg = layout(b)[1]
frames = []
parts, start = [], pd.Timestamp("2022-07-12")
for record in (0, 3, 41, 0):
    part = b[seg == record].copy().reset_index(drop=True)
    part[D.TIME] = (start + pd.to_timedelta(np.arange(len(part)) / 10, unit="s")).astype(str)
    start += pd.Timedelta(seconds=(len(part) - 1) / 10 + 2)
    parts.append(part)
frames.append(("single_alarm_pair", pd.concat(parts, ignore_index=True), .01))
continuous = b.copy()
continuous[D.TIME] = (pd.Timestamp("2022-07-12") + pd.to_timedelta(np.arange(len(continuous)) / 10, unit="s")).astype(str)
frames.append(("continuous_joined_normal", continuous, .01))
frames.append(("B_normal_alpha5", b, .05))
invalid = pd.concat(parts, ignore_index=True)
invalid.loc[88:, D.TIME] = (pd.Timestamp("2022-07-11") + pd.to_timedelta(np.arange(len(invalid) - 88) / 10, unit="s")).astype(str)
frames.append(("clock_reversal", invalid, .01))

scenarios = []
for name, frame, alpha in frames:
    response = console.analyze(dict(split="B", alpha=alpha, prior=.01, dataset="upload", csv=frame.to_csv(index=False)))
    points = pd.DataFrame(response["points"])
    event_rows = points.loc[points.incident_notification.eq(1) | points.incident_escalation.eq(1), "row_id"].astype(int).tolist()
    cursors = sorted(set([0, len(points) - 1, *event_rows, *[r - 1 for r in event_rows if r > 0], *[r + 1 for r in event_rows if r + 1 < len(points)]]))
    if len(cursors) > 75:
        cursors = [cursors[i] for i in np.linspace(0, len(cursors) - 1, 75, dtype=int)]
    expected = []
    for cursor in cursors:
        prefix = points[points.row_id.le(cursor)].copy()
        q = cases(prefix)
        iq = incidents(q, prefix)
        expected.append(dict(cursor=cursor, cases=json.loads(q.to_json(orient="records", double_precision=12)),
                             incidents=json.loads(iq.to_json(orient="records", double_precision=12))))
    scenarios.append(dict(name=name, response=response, expected=expected))

with tempfile.TemporaryDirectory(prefix="judge04_prefix_") as tmp:
    path = Path(tmp) / "scenarios.json"
    path.write_text(json.dumps(scenarios, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run(["node", str(Path(__file__).with_suffix(".cjs")), str(path)], check=False, text=True, capture_output=True)
    print(result.stdout)
    if result.stderr: print(result.stderr, file=sys.stderr)
out = Path(__file__).with_suffix(".json")
data = json.loads(out.read_text())
data["seconds"] = time.perf_counter() - started
data["app_js_sha256"] = hashlib.sha256((ROOT / "press_guard/web/app.js").read_bytes()).hexdigest()
data["model_py_sha256"] = hashlib.sha256((ROOT / "press_guard/model.py").read_bytes()).hexdigest()
out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
raise SystemExit(result.returncode)
