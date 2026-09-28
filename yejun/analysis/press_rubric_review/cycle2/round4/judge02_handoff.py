"""평가관02 인계 직전 영향 확인. 재학습·전체 실험은 반복하지 않는다."""
from pathlib import Path
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]
REPO = Y.parent
G = Y / "press_guard"
OLD = json.loads((HERE / "judge02_checks.json").read_text())
OLD_FINAL = json.loads((HERE / "judge02_final.json").read_text())
SNAP = Path(OLD["provenance"]["code_extracted_to"])
TMP = Path(tempfile.mkdtemp(prefix="judge02_handoff_"))
START = time.monotonic()
RESULT = {"head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
          "score": 38.0, "scope": "기존 모델 검수 이후 변경 영향·해시·저장 모델 추론만 재확인", "checks": {}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(name, passed, detail):
    RESULT["checks"][name] = {"pass": bool(passed), "detail": detail}
    print(name, bool(passed), json.dumps(detail, ensure_ascii=False), flush=True)


core = ["model.py", "probability.py", "train.py", "predict.py", "serve.py", "web/app.js", "README.md", "OPERATIONS.md"]
RESULT["final_source_sha256"] = {str((G / p).relative_to(Y)): sha(G / p) for p in core}
for name in ("probability.py", "train.py"):
    check(name + "_byte_identical", sha(G / name) == OLD["provenance"]["source_sha256"]["yejun/press_guard/" + name], sha(G / name))


def functions(path):
    tree = ast.parse(path.read_text())
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = ast.dump(node, include_attributes=False)
        elif isinstance(node, ast.ClassDef) and node.name == "GuardModel":
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    found["GuardModel." + child.name] = ast.dump(child, include_attributes=False)
    return found


before, after = functions(SNAP / "yejun/press_guard/model.py"), functions(G / "model.py")
math_names = ["sine_score", "ar_residual", "GuardModel.fit", "GuardModel.components"]
same = {name: before[name] == after[name] for name in math_names}
check("model_fit_and_score_math_ast_identical", all(same.values()), same)
artifacts = {}
for name, prior in OLD_FINAL["checks"]["all_four_artifacts_match_independent_refit"]["detail"].items():
    now = sha(G / "artifacts" / name)
    artifacts[name] = {"final_sha256": now, "previous_independent_refit_sha256": prior["independent_refit"], "same": now == prior["independent_refit"]}
check("four_artifacts_unchanged", all(v["same"] for v in artifacts.values()), artifacts)

# 모델·확률·지도학습·선정근거의 직접 CSV를 기존 독립 사본 해시와 비교한다.
folders = {"yejun/press_guard/outputs", "yejun/analysis/press_supervised", "yejun/analysis/press_selection"}
compared, changed = [], []
for rel, digest in OLD["provenance"]["source_sha256"].items():
    p = Path(rel)
    if p.suffix == ".csv" and str(p.parent) in folders:
        current = REPO / p
        info = {"path": rel, "previous_sha256": digest, "final_sha256": sha(current)}
        compared.append(info)
        if info["previous_sha256"] != info["final_sha256"]:
            changed.append(info)
RESULT["csv_hash_comparison"] = compared
check("model_related_csv_byte_identical", not changed, {"compared": len(compared), "changed": changed})

# 시간 역행 검사가 대회 원본 행을 새로 보류하거나 기록 경계를 바꾸지 않는다.
sys.path.insert(0, str(G))
from model import D, layout

normal, abnormal, source = D.load()
rows = {}
for name, frame in (("normal", normal), ("abnormal", abnormal)):
    status, record = layout(frame)
    rows[name] = {"rows": len(frame), "all_ok": bool((status == "ok").all()),
                  "record_boundary_equals_frozen_v1_rule": bool(np.array_equal(record, D.segments(frame)))}
check("original_rows_and_boundaries_unaffected", all(r["all_ok"] and r["record_boundary_equals_frozen_v1_rule"] for r in rows.values()), rows)

# 저장 모델로만 추론한다. 새 모델 학습이나 후보 탐색은 실행하지 않는다.
manifest = json.loads((G / "outputs/manifest.json").read_text())
frozen = json.loads((G / "outputs/expected/predictions_digest.json").read_text())
env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
for sid in "AB":
    name = f"test_predictions_{sid}.csv"
    output = TMP / name
    run = subprocess.run(["/opt/anaconda3/bin/python", str(G / "predict.py"), "--split", sid, "--out", str(output)],
                         cwd=Y, env=env, capture_output=True, text=True)
    values = {"generated": sha(output), "saved": sha(G / "outputs" / name),
              "manifest": manifest["outputs"][name], "digest": frozen[name]["sha256"],
              "judge02_prior": OLD_FINAL["checks"][f"predict_split_{sid}_whole_file_identity"]["detail"]["generated_sha256"]}
    check("final_saved_model_predict_" + sid, run.returncode == 0 and len(set(values.values())) == 1,
          {"hashes": values, "returncode": run.returncode, "stdout": run.stdout.strip(), "stderr": run.stderr.strip()})

web = subprocess.run(["node", str(G / "test_web.cjs")], cwd=Y, capture_output=True, text=True)
check("final_web_vm_regressions", web.returncode == 0, {"stdout": web.stdout.strip(), "stderr": web.stderr.strip()})
pipeline = json.loads((HERE / "field_final_rerun.json").read_text())
check("root_final_pipeline_record", all(r["returncode"] == 0 for r in pipeline),
      {"steps": len(pipeline), "source": "field_final_rerun.json", "note": "루트 실행 기록을 읽어 확인; 평가관02가 다시 실행한 것이 아님"})
RESULT["elapsed_s"] = time.monotonic() - START
RESULT["pass_count"] = sum(x["pass"] for x in RESULT["checks"].values())
RESULT["check_count"] = len(RESULT["checks"])
(HERE / "judge02_handoff.json").write_text(json.dumps(RESULT, ensure_ascii=False, indent=2))
print("HANDOFF", RESULT["pass_count"], "/", RESULT["check_count"], "seconds", RESULT["elapsed_s"])
raise SystemExit(0 if RESULT["pass_count"] == RESULT["check_count"] else 1)
