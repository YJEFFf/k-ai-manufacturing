"""Read-only audit of review scoring/document claims; writes this review's JSON only."""
from __future__ import annotations

import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
CYCLE = ROOT / "yejun/analysis/press_rubric_review/cycle2"
sources: dict[str, str] = {}


def read(rel: str) -> str:
    path = ROOT / rel
    raw = path.read_bytes()
    sources[rel] = hashlib.sha256(raw).hexdigest()
    return raw.decode("utf-8")


def lines(rel: str, start: int, end: int | None = None) -> dict:
    text = read(rel).splitlines()
    return {"path": rel, "start_line": start, "end_line": end or start,
            "text": "\n".join(text[start - 1:end or start])}


def table(rel: str) -> list[dict]:
    return list(csv.DictReader(read(rel).splitlines()))


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


# Read the supplied HWPX directly rather than assuming the internal extract is official.
official = []
for path in sorted((ROOT / "관련 자료").glob("*.hwpx")):
    rel = path.relative_to(ROOT).as_posix()
    sources[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    texts = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("Contents/section") and name.endswith(".xml"):
                texts.extend(e.text or "" for e in ET.fromstring(archive.read(name)).iter()
                             if e.tag.endswith("}t"))
    normalized_name = unicodedata.normalize("NFC", path.name)
    if "과제공개" in normalized_name:
        weights = []
        for criterion in ["데이터 이해 및 진단", "AI 예측모델 개발", "영향요인 및 오류분석",
                          "현장 활용방안", "창의성·차별성", "코드 및 재현성"]:
            start = next(i for i, text in enumerate(texts) if criterion in text)
            end = next(i for i in range(start + 1, len(texts)) if texts[i].strip().isdigit())
            weights.append({"criterion": criterion, "weight": int(texts[end]),
                            "xml_text_element_index_0": start, "source_text": texts[start:end + 1]})
        official.append({"path": rel, "weights": weights})
    elif "양식" in normalized_name:
        official.append({"path": rel, "guidance": [
            {"xml_text_element_index_0": i, "text": text}
            for i, text in enumerate(texts)
            if any(k in text for k in ["제1장", "제2장", "제3장", "제4장", "제5장", "제6장",
                                      "제조공정의", "동일한 평가조건", "실패하는 조건", "현장 판단",
                                      "새로운 알고리즘", "어떤 기여", "제출자료"])]})
assert official[0].get("weights") or official[1].get("weights")
weights = next(item["weights"] for item in official if "weights" in item)
assert [item["weight"] for item in weights] == [15, 40, 15, 10, 10, 10]

# Explicit transcription of red_M's forecast table, checked against cited original text.
# '안팎/전후' has no stated interval. For the reported 13/15 check it is a point ±0.1.
forecast_spec = [
    ("data", 1, "13.5", "14", "13.6", "round1/judge_01_data.md", 14, "explicit"),
    ("data", 2, "14.5", "14.5", "14.4", "round2/judge_01_data.md", 18, "explicit_point; original also gives 14.0~15.0"),
    ("data", 3, "15", "15", "15", "round3/judge_01_data.md", 26, "derived from zero remaining deductions"),
    ("model", 2, "38", "38", "38.1", "round2/judge_02_model.md", 26, "approximate point"),
    ("model", 3, "38.5", "38.5", "38", "round3/judge_02_model.md", 23, "explicit"),
    ("errors", 1, "13", "13.5", "13", "round1/judge_03_errors.md", 17, "explicit"),
    ("errors", 3, "14.55", "14.55", "14.5", "round3/judge_03_errors.md", 49, "derived:14.1+0.45"),
    ("field", 1, "8.5", "8.5", "8.5", "round1/judge_04_field.md", 23, "approximate point"),
    ("field", 2, "9", "9", "9.1", "round2/judge_04_field.md", 25, "approximate point"),
    ("field", 3, "9.4", "9.5", "9.5", "round3/judge_04_field.md", 28, "explicit"),
    ("originality", 1, "8.5", "9", "8.8", "round1/judge_05_originality.md", 16, "explicit"),
    ("originality", 2, "9", "9.2", "9.2", "round2/judge_05_originality.md", 30, "explicit"),
    ("originality", 3, "9.4", "9.4", "9.4", "round3/judge_05_originality.md", 34, "explicit"),
    ("repro", 1, "9.5", "9.5", "9", "round1/judge_06_repro.md", 19, "approximate point"),
    ("repro", 3, "10", "10", "10", "round3/judge_06_repro.md", 42, "derived:9.7+0.3"),
]
forecasts = []
for criterion, source_round, low, high, observed, rel, line, kind in forecast_spec:
    lo, hi, score = map(Decimal, (low, high, observed))
    forecasts.append({"criterion": criterion, "forecast_round": source_round,
                      "low": float(lo), "high": float(hi), "next_score": float(score),
                      "kind": kind, "inside_declared_range": lo <= score <= hi,
                      "within_0_1": lo - Decimal("0.1") <= score <= hi + Decimal("0.1"),
                      "source": lines("yejun/analysis/press_rubric_review/cycle2/" + rel, line)})
forecast_summary = {"n": len(forecasts),
                    "within_0_1": sum(f["within_0_1"] for f in forecasts),
                    "literal_interval": sum(f["inside_declared_range"] for f in forecasts),
                    "round4_literal_interval": sum(f["inside_declared_range"] for f in forecasts if f["forecast_round"] == 3),
                    "round4_within_0_1": sum(f["within_0_1"] for f in forecasts if f["forecast_round"] == 3),
                    "nonmatches": [f["criterion"] + "_round" + str(f["forecast_round"] + 1)
                                   for f in forecasts if not f["within_0_1"]]}
assert forecast_summary["within_0_1"] == 13

scores = []
for file in ["red_J1_cold_score_academic.md", "red_J2_cold_score_industry.md"]:
    text = read("yejun/analysis/press_rubric_review/cycle2/adversarial/" + file)
    first_table = text[text.index("| 항목"):text.index("## ②")]
    values = []
    for row in first_table.splitlines():
        parts = [p.strip().replace("**", "") for p in row.split("|")[1:-1]]
        if parts and re.match(r"^[1-6][. ]", parts[0]):
            values.append(Decimal(parts[2]))
    scores.append({"path": file, "criterion_scores": [float(v) for v in values],
                   "sum": float(sum(values)), "interpretation": "subjective LLM rubric score; not a statistical interval"})
assert [s["sum"] for s in scores] == [75.5, 74.5]
score_differences = [abs(a - b) for a, b in zip(scores[0]["criterion_scores"], scores[1]["criterion_scores"])]
score_agreement = {"differences": score_differences,
                   "exact_matches": sum(d == 0 for d in score_differences),
                   "within_0_5": sum(d <= 0.5 for d in score_differences),
                   "max_difference": max(score_differences)}

# CLI rejects this alpha during argument parsing, before it can read/write a model.
with tempfile.TemporaryDirectory(prefix="scoring_docs_alpha_") as tmp:
    temp = Path(tmp)
    alpha_probe = subprocess.run(
        [sys.executable, str(ROOT / "yejun/press_guard/recalibrate.py"),
         "--normal", str(temp / "absent.csv"), "--out", str(temp / "must_not_exist.json"),
         "--alpha", "0.0008"], text=True, capture_output=True)
    alpha_probe_result = {"returncode": alpha_probe.returncode, "stderr": alpha_probe.stderr,
                          "files_created": [p.name for p in temp.iterdir()]}
assert alpha_probe_result["returncode"] == 2
assert "invalid choice" in alpha_probe_result["stderr"]
assert not alpha_probe_result["files_created"]

review_k3 = json.loads(read("yejun/analysis/press_rubric_review/cycle2/round3/judge02_checks.json"))["K3_supervised"]["per_split"]
supervised_evidence = {split: {key: value for key, value in values.items()
                               if key.startswith("threshold_") or key == "record2" or key.startswith("round1_features:")}
                       for split, values in review_k3.items()}
assert round(supervised_evidence["A"]["threshold_min"], 3) == 0.248
assert round(supervised_evidence["A"]["threshold_max"], 3) == 0.997
assert supervised_evidence["A"]["record2"]["fn"] == 47

metrics = table("yejun/press_guard/outputs/metrics.csv")
metric_check = []
for split in ["A", "B"]:
    rows = [r for r in metrics if r["split"] == split and Decimal(r["alpha"]) == Decimal("0.01")]
    metric_check.append({"split": split, "rows": rows,
                         "record_alarm_counts_identical": len({(r["normal_notified_segments"], r["abnormal_notified_segments"]) for r in rows}) == 1,
                         "max_first_alarm_delay_values": sorted({r["delay_max_s"] for r in rows})})

package_rows = table("yejun/analysis/press_rubric_review/cycle2/round4/package_files_final.csv")
package_paths = [r["path"] for r in package_rows]
selection_evidence = table("yejun/analysis/press_selection/selection_evidence.csv")
bad_source_rows = [{"csv_line": i + 2, **r} for i, r in enumerate(selection_evidence)
                   if "judge_02_model.md" in r["source"]]
markers = []
original_marker_regex = re.compile(r"루브릭|사이클[ ]?2|평가관|press_rubric_review|press_implementation_review")
broader_markers = []
for relative in package_paths:
    path = ROOT / relative
    if not path.exists():
        path = ROOT / "yejun" / relative
    if not path.exists() or path.suffix not in {".md", ".py", ".csv", ".txt"}:
        continue
    rel = path.relative_to(ROOT).as_posix()
    text = read(rel)
    for i, line in enumerate(text.splitlines(), 1):
        if original_marker_regex.search(line):
            entry = {"path": rel, "line": i, "text": line}
            broader_markers.append(entry)
            if path.suffix == ".md" or path.name == "requirements-lock.txt":
                markers.append(entry)

diagnostics_manifest = json.loads(read("yejun/analysis/press_evidence/diagnostics_manifest.json"))
diagnostics_counts = {"total": len(diagnostics_manifest["outputs"]),
                      "csv": sum(p.endswith(".csv") for p in diagnostics_manifest["outputs"]),
                      "png": sum(p.endswith(".png") for p in diagnostics_manifest["outputs"])}

snippets_spec = [
    ("yejun/AGENTS.md", 7, 15),
    ("yejun/analysis/press_rubric_review/cycle2/judge_prompts.md", 64, 66),
    ("yejun/analysis/press_rubric_review/cycle2/judge_prompts.md", 74, 95),
    ("yejun/analysis/press_rubric_review/cycle2/round4/review_protocol.md", 5, 11),
    ("yejun/analysis/press_rubric_review/cycle2/round3/judge_01_data.md", 53, 59),
    ("yejun/analysis/press_rubric_review/cycle2/round3/judge_06_repro.md", 24, 24),
    ("yejun/press_guard/README.md", 19, 24),
    ("yejun/press_guard/README.md", 41, 63),
    ("yejun/press_guard/README.md", 106, 114),
    ("yejun/press_guard/README.md", 215, 219),
    ("yejun/press_guard/OPERATIONS.md", 12, 16),
    ("yejun/press_guard/outputs/error_condition_summary_v2.csv", 8, 10),
    ("yejun/analysis/press_evidence/decision_table_diagnosis_v2.csv", 4, 7),
    ("yejun/press_guard/model.py", 31, 45),
    ("yejun/press_guard/web/index.html", 27, 27),
    ("yejun/analysis/press_supplement/README.md", 74, 75),
    ("yejun/analysis/press_evidence/README.md", 104, 114),
    ("yejun/analysis/press_selection/README.md", 150, 151),
    ("yejun/analysis/press_supervised/README.md", 37, 38),
    ("yejun/analysis/press_rubric_review/cycle2/round4/judge06_final_checks.py", 99, 105),
    ("yejun/analysis/press_rubric_review/cycle2/adversarial/README.md", 33, 45),
    ("yejun/press_guard/recalibrate.py", 26, 27),
    ("yejun/press_guard/recalibrate.py", 137, 145),
]
snippets = [lines(*spec) for spec in snippets_spec]
historical_prompt = git("show", "6c61a88:yejun/analysis/press_rubric_review/cycle2/judge_prompts.md")
historical_rank_instructions = [line for line in historical_prompt.splitlines()
                                if any(k in line for k in ["순위", "유보", "상위 8"])]
commit_tools = {commit: git("show", "-s", "--format=%B", commit).split("도구:")[-1].splitlines()[0].strip()
                for commit in ["6c61a88", "cc1aac2"]}

result = {"head": git("rev-parse", "HEAD"), "product_baseline": "cc1aac2",
          "method": "local source and CSV/HWPX read-only audit; alpha CLI rejects before any file access",
          "official": official, "scores": scores,
          "score_agreement": score_agreement, "alpha_cli_probe": alpha_probe_result,
          "supervised_numbers_already_in_committed_review": supervised_evidence,
          "forecasts": forecasts, "forecast_summary": forecast_summary,
          "historical_rank_instructions": historical_rank_instructions, "commit_tools": commit_tools,
          "alpha1_v1_v2": metric_check,
          "diagnostics_counts": diagnostics_counts,
          "package_source_citations_missing": bad_source_rows,
          "judge_02_model_in_package": any("judge_02_model.md" in p for p in package_paths),
          "original_marker_scope_hits": markers,
          "broader_marker_line_count": len(broader_markers),
          "broader_marker_file_count": len({m["path"] for m in broader_markers}),
          "reproduce_summary_in_package": any(p.endswith("reproduce_summary.json") for p in package_paths),
          "snippets": snippets, "source_sha256": sources}
output = HERE / "scoring_docs_audit.json"
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"forecasts": forecast_summary, "scores": scores, "diagnostics": diagnostics_counts,
                  "score_agreement": score_agreement, "alpha_cli_probe": alpha_probe_result["returncode"],
                  "original_marker_scope_hits": len(markers), "broader_marker_line_count": len(broader_markers),
                  "commit_tools": commit_tools, "output": output.relative_to(ROOT).as_posix()}, ensure_ascii=False))
