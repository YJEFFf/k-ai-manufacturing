"""Run from yejun after the simulation and timestamp-order fixes are finalized."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
RESULTS = []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(name, arguments):
    started = time.monotonic()
    print(f"start {name}", flush=True)
    log = HERE / f"field_final_{name}.log"
    with log.open("w", encoding="utf-8") as stream:
        rc = subprocess.run([sys.executable, *arguments], stdout=stream, stderr=subprocess.STDOUT).returncode
    item = dict(step=name, arguments=arguments, returncode=rc, seconds=round(time.monotonic() - started, 2))
    print(json.dumps(item, ensure_ascii=False), flush=True)
    return item


def record(item):
    RESULTS.append(item)
    (HERE / "field_final_rerun.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if item["returncode"]:
        print((HERE / f"field_final_{item['step']}.log").read_text(encoding="utf-8")[-6000:], flush=True)
        raise SystemExit(item["returncode"])


def step(name, *arguments):
    record(run(name, list(arguments)))


def main():
    out = Path("press_guard/outputs")
    all_csv = list(out.glob("*.csv"))
    all_csv += list(Path("analysis/press_supplement").glob("*.csv"))
    before = {p.as_posix(): sha(p) for p in all_csv}
    step("train", "press_guard/train.py", "--rolling")
    artifacts = {p.name: sha(p) for p in Path("press_guard/artifacts").glob("*.json")}
    initial = json.loads((HERE / "initial_checks.json").read_text(encoding="utf-8"))
    assert artifacts == initial["unchanged_model_artifact_sha256"]
    for name in ("metrics.csv", "rolling.csv"):
        assert sha(out / name) == before[(out / name).as_posix()]
    regression = dict(passed=True, model_and_probability_artifacts_unchanged=True,
                      metrics_and_rolling_unchanged=True, artifact_sha256=artifacts)
    (HERE / "field_final_regression.json").write_text(json.dumps(regression, indent=2) + "\n", encoding="utf-8")
    experiments = [("e1", ["analysis/press_supplement/fault_injection.py"]),
                   ("e2", ["analysis/press_supplement/uci_v2.py"]),
                   ("e3", ["analysis/press_supplement/recalibration.py"])]
    # Each experiment owns different output/manifest files; all read the same frozen models.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run, name, command) for name, command in experiments]
        for future in futures:
            record(future.result())
    step("supplement_figures", "analysis/press_supplement/figures.py")
    step("supplement_freeze", "analysis/press_supplement/verify.py", "--freeze")
    step("supplement_verify", "analysis/press_supplement/verify.py", "--strict")
    for name, command in [("analyze", "press_guard/analyze.py"), ("audit", "press_guard/audit.py")]:
        step(name, command)
    step("guard_freeze", "press_guard/verify.py", "--freeze")
    step("guard_verify", "press_guard/verify.py")
    for package in ("press_supervised", "press_selection"):
        step(package, f"analysis/{package}/run.py")
        step(f"{package}_freeze", "analysis/package_contract.py", "--package", f"analysis/{package}", "--freeze")
        step(f"{package}_verify", "analysis/package_contract.py", "--package", f"analysis/{package}")
    step("evidence_tables", "analysis/press_evidence/build_tables.py")
    step("evidence_diagnostics", "analysis/press_evidence/build_diagnostics.py")
    step("evidence_freeze", "analysis/package_contract.py", "--package", "analysis/press_evidence", "--freeze")
    step("evidence_verify", "analysis/package_contract.py", "--package", "analysis/press_evidence")
    step("advance_verify", "analysis/package_contract.py", "--package", "analysis/press_advance")
    step("v1_verify", "press_submission/verify.py", "--out", "press_submission/outputs")
    delta = [dict(path=name, before=value, after=sha(Path(name))) for name, value in before.items() if sha(Path(name)) != value]
    (HERE / "field_final_csv_delta.json").write_text(json.dumps(dict(compared=len(before), changed=delta), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Complete. {len(before)} existing CSVs compared; {len(delta)} changed.", flush=True)


if __name__ == "__main__":
    main()
