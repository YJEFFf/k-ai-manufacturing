"""수집 시각 역행 때 사건 병합/알림 누락 반례. 제품 파일은 수정하지 않는다."""
from pathlib import Path
import json
import sys
import time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "press_guard"))
from model import D, load_bundle, layout, cases, incidents, timing_warning, StreamDetector
import simulate

start = time.perf_counter()
normal, _, _ = D.load()
model = load_bundle(ROOT / "press_guard/artifacts/guard_B.json")
source = D.inputs_only(D.split_normal(normal, D.segments(normal), "B")["test"]).reset_index(drop=True)
seg = layout(source)[1]
parts = []
for k in range(3):
    part = source[seg == 3].copy().reset_index(drop=True)
    part[D.TIME] = (pd.Timestamp("2022-07-14") - pd.Timedelta(days=k) + pd.to_timedelta(np.arange(len(part)) / 10, unit="s")).astype(str)
    parts.append(part)
frame = pd.concat(parts, ignore_index=True)
pred = model.predict(frame)
queue = incidents(cases(pred), pred)
log = simulate.run(frame, model, chunk=7)
chunks = {}
for size in (1, 7, 128):
    stream = StreamDetector(model)
    actual = pd.concat([stream.push(frame.iloc[i:i + size]) for i in range(0, len(frame), size)], ignore_index=True)
    try:
        pd.testing.assert_frame_equal(actual, pred, rtol=1e-10, atol=1e-10)
        chunks[str(size)] = True
    except AssertionError as exc:
        chunks[str(size)] = str(exc)
result = {"case": "three single-alarm records separated by a backward one-day timestamp jump", "rows": len(frame),
          "record_count": int(pred.record_id.nunique()), "statuses": pred.status.value_counts().to_dict(), "warnings": timing_warning(pred),
          "cases": cases(pred)[["first_timestamp", "alarm_rows", "level", "incident_id"]].to_dict("records"),
          "incidents": queue[["incident_id", "cases", "level", "escalation_row"]].to_dict("records"),
          "events": log[["timestamp", "record_id", "kind", "notify"]].to_dict("records"), "chunks_match_batch": chunks,
          "seconds": time.perf_counter() - start}
result["reversed_records_merged"] = any(pd.to_datetime(g.first_timestamp, format="mixed", utc=True).diff().dt.total_seconds().lt(0).any()
                                       for _, g in cases(pred).groupby("incident_id"))
result["collection_problem_visible"] = bool(result["warnings"] or pred.status.ne("ok").any())
quality_parts = []
for day, record in ((14, 0), (13, 3), (12, 41), (11, 0)):
    part = source[seg == record].copy().reset_index(drop=True)
    part[D.TIME] = (pd.Timestamp(f"2022-07-{day}") + pd.to_timedelta(np.arange(len(part)) / 10, unit="s")).astype(str)
    quality_parts.append(part)
quality_frame = pd.concat(quality_parts, ignore_index=True)
quality_pred = model.predict(quality_frame)
quality_cases = cases(quality_pred)
result["reverse_quality_windows"] = quality_cases[["first_timestamp", "suspect_from", "suspect_to", "suspect_seconds", "suspect_open"]].to_dict("records") if len(quality_cases) else []
result["negative_quality_window"] = bool((quality_cases.suspect_seconds < 0).any()) if len(quality_cases) else False
result["quality_input_rejected_rows"] = int(quality_pred.status.ne("ok").sum())
out = Path(__file__).with_suffix(".json")
def clean(value):
    value = D.to_jsonable(value)
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, list): return [clean(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value): return None
    return value
out.write_text(json.dumps(clean(result), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
print(json.dumps(clean(result), ensure_ascii=False, indent=2, allow_nan=False))
