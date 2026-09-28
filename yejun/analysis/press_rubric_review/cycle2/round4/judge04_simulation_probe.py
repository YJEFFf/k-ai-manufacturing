"""실제 콘솔 분석 결과로 모의 운용 UI를 Node VM에서 검사한다."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "press_guard"))
from model import D, layout
from serve import Console

normal, _, _ = D.load()
frame = D.inputs_only(D.split_normal(normal, D.segments(normal), "B")["test"]).reset_index(drop=True)
seg = layout(frame)[1]
parts, start = [], pd.Timestamp("2022-07-12T00:00:00")
for record in (0, 3, 41, 0):
    part = frame[seg == record].copy().reset_index(drop=True)
    part[D.TIME] = (start + pd.to_timedelta(np.arange(len(part)) / 10, unit="s")).astype(str)
    start += pd.Timedelta(seconds=(len(part) - 1) / 10 + 2)
    parts.append(part)
pair = pd.concat(parts, ignore_index=True)
data = Console().analyze(dict(split="B", alpha=.01, prior=.01, dataset="upload", csv=pair.to_csv(index=False)))
with tempfile.TemporaryDirectory(prefix="judge04_ui_") as tmp:
    path = Path(tmp) / "actual_api.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["node", str(Path(__file__).with_suffix(".cjs")), str(path)], check=True)

out = Path(__file__).with_suffix(".json")
result = json.loads(out.read_text())
result["app_js_sha256"] = hashlib.sha256((ROOT / "press_guard/web/app.js").read_bytes()).hexdigest()
out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
