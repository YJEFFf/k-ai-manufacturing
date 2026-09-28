"""평가관02 최종 산출물 검수. 전체 재생성 완료 후 judge02_verify.py에 이어 실행한다.

현재 파일은 읽기만 하며 예측 파일은 시스템 임시 폴더에 만든다.
judge02_final.json·호출 측 로그만 이 검수 폴더에 남긴다.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
import pandas as pd
from markdown_it import MarkdownIt

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]
G = Y / "press_guard"
TMP = Path(tempfile.mkdtemp(prefix="judge02_c2r4_final_"))
PY = "/opt/anaconda3/bin/python"
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
checks = json.loads((HERE / "judge02_checks.json").read_text())
snapshot = Path(checks["provenance"]["code_extracted_to"])
result = {"temporary_outputs": str(TMP), "source_snapshot": str(snapshot), "checks": {}}
started = time.monotonic()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check(name, truth, detail=None):
    result["checks"][name] = {"pass": bool(truth), "detail": detail}
    print(name, bool(truth), json.dumps(detail, ensure_ascii=False) if detail is not None else "", flush=True)


# 마지막 독립 계산이 읽은 핵심 소스와 최종 검수 소스가 같아야 한다.
core = ["model.py", "probability.py", "train.py", "predict.py", "analyze.py", "insights.py"]
changes = [n for n in core if sha(G / n) != checks["provenance"]["source_sha256"]["yejun/press_guard/" + n]]
check("source_snapshot_current", not changes, changes)
artifacts = {}
for sid in "AB":
    for prefix in ("guard", "probability"):
        name = f"{prefix}_{sid}.json"
        artifacts[name] = {"saved": sha(G / "artifacts" / name), "independent_refit": sha(snapshot / "artifacts_refit" / name)}
check("all_four_artifacts_match_independent_refit", all(v["saved"] == v["independent_refit"] for v in artifacts.values()), artifacts)

sys.path.insert(0, str(G))
from probability import ProbabilityCalibrator, min_rank_nominal_likelihood_ratio

# 발견 때 사용한 합성 경계 입력. 대회 또는 현장 관측값이 아니다.
c = ProbabilityCalibrator.fit([0, 1, 2, 3], [2, 3, 4], calibration_units=120)
scores = np.linspace(0, 4, 401)
lr = c.likelihood_ratio(scores)
check("fixed_zero_to_positive_probability_monotonic", (np.diff(lr) >= -1e-12).all(), {
    "query": [1.0, 1.1, 1.5, 2.0], "lr": c.likelihood_ratio([1.0, 1.1, 1.5, 2.0]).tolist(),
    "scope": "합성 함수 경계 시험",
})
old_behavior_equal = {}
for sid in "AB":
    cal = ProbabilityCalibrator.load(G / "artifacts" / f"probability_{sid}.json")
    grid = np.r_[np.linspace(cal.x.min() - 1, cal.x.max() + 1, 4001), cal.x]
    p = cal.fitted(grid)
    raw = np.clip(p, 1e-9, 1 - 1e-9)
    raw = raw / (1 - raw) / (cal.pi_fit / (1 - cal.pi_fit))
    legacy = np.where(p <= 0, cal.lr_floor, np.minimum(raw, cal.lr_cap))
    old_behavior_equal[sid] = {"zero_knots": int((cal.y == 0).sum()), "exact_equal": bool(np.array_equal(legacy, cal.likelihood_ratio(grid)))}
check("existing_calibrator_behavior_unchanged", all(v["exact_equal"] for v in old_behavior_equal.values()), old_behavior_equal)

# 명목 FAR는 가정 입력이며 일반적 LR 상한이 아님을 수식과 최종 표에서 확인한다.
nominal = min_rank_nominal_likelihood_ratio(120, .955)
check("nominal_lr_counterexample", .955 / (1 / 242) > nominal, {
    "nominal_far_assumed": 1 / 121, "smaller_far_assumed": 1 / 242,
    "tpr_assumed": .955, "nominal_lr": nominal, "smaller_far_lr": .955 * 242,
    "scope": "수학적 가정 반례; 관측·현장 추정 아님",
})
lf = pd.read_csv(G / "outputs/label_free_alert_probability_v2.csv")
required = {"nominal_far", "nominal_lr_reference", "min_rank_nominal_lr_reference"}
check("label_free_named_scenario_columns", required.issubset(lf.columns) and "lr_bound" not in lf.columns, sorted(lf.columns))
if required.issubset(lf.columns):
    formula_ok = np.allclose(lf.nominal_lr_reference, lf.tpr / lf.nominal_far) and np.allclose(lf.min_rank_nominal_lr_reference, 121 * lf.tpr)
    check("label_free_scenario_formulas", formula_ok, {"rows": len(lf), "alphas": sorted(lf.alpha.unique().tolist())})
conv = pd.read_csv(G / "outputs/probability_conversion_v2.csv")
check("conversion_named_scenario_columns", {"label_free_min_rank_nominal_lr", "label_free_min_rank_nominal_p"}.issubset(conv.columns))

# 저장 모델만으로 최종 제출 예측 CSV를 다시 만들고 파일 전체를 비교한다.
manifest = json.loads((G / "outputs/manifest.json").read_text())
digest = json.loads((G / "outputs/expected/predictions_digest.json").read_text())
for sid in "AB":
    name = f"test_predictions_{sid}.csv"
    path = TMP / name
    cli = subprocess.run([PY, str(G / "predict.py"), "--split", sid, "--out", str(path)], cwd=Y, env=ENV, capture_output=True, text=True)
    detail = {"code": cli.returncode, "stdout": cli.stdout.strip(), "stderr": cli.stderr.strip()}
    if path.exists():
        detail.update(generated_sha256=sha(path), final_sha256=sha(G / "outputs" / name), manifest_sha256=manifest["outputs"][name], digest_sha256=digest[name]["sha256"])
        table = pd.read_csv(path)
        tp = int(((table.label == 1) & (table.alarm == 1)).sum())
        fp = int(((table.label == 0) & (table.alarm == 1)).sum())
        fn = int(((table.label == 1) & (table.alarm == 0)).sum())
        detail.update(rows=len(table), tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn))
        ok = cli.returncode == 0 and len({detail[k] for k in ("generated_sha256", "final_sha256", "manifest_sha256", "digest_sha256")}) == 1
    else:
        ok = False
    check(f"predict_split_{sid}_whole_file_identity", ok, detail)

md = (G / "outputs/model_comparison_v2.md").read_text()
html = MarkdownIt("commonmark").enable("table").render(md)
headers = re.findall(r"<th[^>]*>(.*?)</th>", html.split("</thead>")[0])
rows = [re.findall(r"<td[^>]*>(.*?)</td>", r) for r in html.split("<tbody>")[1].split("</tr>") if "<td" in r]
model_rows = [dict(zip(headers, row)) for row in rows if any("early6_ar2" in c for c in row)]
check("gfm_all_rows_have_correct_cells", len(headers) == 11 and len(rows) == 28 and all(len(r) == 11 for r in rows), {"headers": len(headers), "rows": len(rows)})
check("gfm_final_f1_in_correct_column", [r["F1(전체 행)"] for r in model_rows] == ["0.9619", "0.9710"], model_rows)

source = "\n".join((G / p).read_text() for p in ("README.md", "OPERATIONS.md", "probability.py", "web/index.html", "web/app.js"))
check("no_probability_lower_bound_display", "≥55" not in source and "≥ 55" not in source and "(모형 상한)" in source)
cli_snapshot = Path(json.loads((HERE / "judge02_cli.json").read_text())["temporary_snapshot"]) / "yejun/press_guard"
cli_sources = {k: sha(cli_snapshot / k) == sha(G / k) for k in ("model.py", "recalibrate.py", "predict.py", "simulate.py", "monitor.py")}
check("cli_tested_sources_current", all(cli_sources.values()), cli_sources)
web = subprocess.run(["node", str(G / "test_web.cjs")], cwd=Y, capture_output=True, text=True)
(HERE / "judge02_web.log").write_text(web.stdout + web.stderr)
check("web_vm_regressions", web.returncode == 0, web.stdout.strip())
result["elapsed_s"] = time.monotonic() - started
result["pass_count"] = sum(v["pass"] for v in result["checks"].values())
result["check_count"] = len(result["checks"])
(HERE / "judge02_final.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print("FINAL", result["pass_count"], "/", result["check_count"], "elapsed", result["elapsed_s"], flush=True)
raise SystemExit(0 if result["pass_count"] == result["check_count"] else 1)
