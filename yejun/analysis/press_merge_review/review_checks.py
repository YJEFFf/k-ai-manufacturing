"""Independent checks of PR #2; leaves the merged Claude files untouched.

Run with the dependencies in claude/code/press/pipeline/requirements.txt:
    python yejun/analysis/press_merge_review/review_checks.py --root DATA_ROOT

DATA_ROOT contains data/3_소성가공_예지보전/{press_data_normal,outlier_data}.csv.
Optionally pass --reproduction OUTPUT_DIR from run_all.py for CSV comparison.
The extra quantization checks are exploratory checks on already inspected data.
"""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PIPE = REPO / "claude/code/press/pipeline"
SAVED = PIPE.parent / "outputs/pipeline"
sys.path.insert(0, str(PIPE))
from data import load, load_vendor, split_sets
from evaluate import conformal_p
from scores import Scorer
from select_w import select_w


def compare_csvs(reproduction):
    rows = []
    for src in sorted(SAVED.glob("*.csv")):
        dest = reproduction / src.name
        a, b = pd.read_csv(src), pd.read_csv(dest)
        same_layout = a.shape == b.shape and a.columns.equals(b.columns)
        bad_columns, max_diff = [], 0.0
        if same_layout:
            for c in a.columns:
                if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c]):
                    av, bv = a[c].to_numpy(float), b[c].to_numpy(float)
                    ok = np.isclose(av, bv, rtol=0, atol=1e-9, equal_nan=True).all()
                    finite = np.isfinite(av) & np.isfinite(bv)
                    max_diff = max(max_diff, float(np.abs(av[finite] - bv[finite]).max(initial=0)))
                else:
                    ok = a[c].fillna("<missing>").equals(b[c].fillna("<missing>"))
                if not ok:
                    bad_columns.append(c)
        rows.append(dict(file=src.name, rows=len(a), same_layout=same_layout,
                         equal_at_1e_9=same_layout and not bad_columns,
                         max_numeric_abs_diff=max_diff, differing_columns=";".join(bad_columns)))
    return pd.DataFrame(rows)


def alarm_metrics(yj, test, abnormal, ts, ass, calmax, budget):
    threshold = yj.cutoff_at_budget(calmax, budget)
    scores = np.r_[ts, ass]
    truth = np.r_[np.zeros(len(test), int), np.ones(len(abnormal), int)]
    cut = np.isfinite(scores) & (scores > threshold)
    conf = np.nan_to_num(conformal_p(calmax, scores), nan=1.0) <= budget
    row = dict(threshold=threshold, differing_rows=int((cut != conf).sum()))
    for policy, alarm in (("cutoff", cut), ("conformal", conf)):
        row[f"{policy}_f1"] = f1_score(truth, alarm)
        row[f"{policy}_tp"] = int(alarm[len(test):].sum())
        row[f"{policy}_fp"] = int(alarm[:len(test)].sum())
        row[f"{policy}_normal_segments"] = int(pd.Series(alarm[:len(test)]).groupby(yj.blocks(test)).any().sum())
        row[f"{policy}_abnormal_segments"] = int(pd.Series(alarm[len(test):]).groupby(yj.blocks(abnormal)).any().sum())
    return row


def extra_checks(root):
    spec = importlib.util.spec_from_file_location("requantize_review", PIPE.parent / "05_requantize_audit.py")
    rq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rq)
    yj = load_vendor()
    normal, abnormal = load(root)
    original_choices = json.loads((SAVED / "checks.json").read_text())
    rows, selections, saturation = [], [], []
    for variant, quantization in rq.VARIANTS.items():
        n, a = rq.quantize(normal, quantization), rq.quantize(abnormal, quantization)
        for split, train_end, cal_end in yj.SPLITS:
            train, cal, test = split_sets(n, yj, train_end, cal_end)
            chosen, table, ties = select_w(yj, train, cal)
            selections.append(table.assign(variant=variant, split=split, selected=lambda d: d.w == chosen))
            original = original_choices[split]["w_rule"]
            scorer = Scorer(train, yj.blocks, wins=sorted({5, 8, 10, chosen}), baselines=False)
            score_sets = [scorer.score(d, yj)[0] for d in (cal, test, a)]
            for model in score_sets[0]:
                cs, ts, ass = [d[model] for d in score_sets]
                calmax = yj.segment_max(cs, yj.blocks(cal))
                if model.startswith("maxz_plus_sine_"):
                    w = int(model.rsplit("_", 1)[-1])
                    cap = float(np.log10(np.isfinite(scorer.ref_s[w]).sum() + 1))
                    threshold = yj.cutoff_at_budget(calmax, .01)
                    saturation.append(dict(variant=variant, split=split, w=w,
                                           sine_score_ceiling=cap, threshold=threshold,
                                           cal_segments_at_or_above_sine_ceiling=int((calmax >= cap).sum()),
                                           min_p_for_sine_only=float(conformal_p(calmax, np.array([cap]))[0]),
                                           cutoff_disables_sine=bool(threshold >= cap)))
                for budget in yj.BUDGETS:
                    rows.append(dict(variant=variant, split=split, model=model, budget=budget,
                                     original_rule=model == f"maxz_plus_sine_{original}",
                                     reselected_rule=model == f"maxz_plus_sine_{chosen}",
                                     selected_w=chosen,
                                     **alarm_metrics(yj, test, a, ts, ass, calmax, budget)))
            print(f"checked {variant} {split}: selected w={chosen}, ties={ties}", flush=True)
    return pd.DataFrame(rows), pd.concat(selections, ignore_index=True), pd.DataFrame(saturation)


def path_checks(root, reproduction):
    """Reproduce the child invocation used when cached 05 outputs are absent."""
    with tempfile.TemporaryDirectory(prefix="press-review-child-") as temp:
        child = Path(temp) / "claude/code/press/05_requantize_audit.py"
        child.parent.mkdir(parents=True)
        shutil.copy2(PIPE.parent / child.name, child)
        result = subprocess.run([sys.executable, str(child), "--audit",
                                 str(PIPE / "vendor/press_policy_audit.py")],
                                text=True, capture_output=True)
        return dict(custom_root_csv_exists=(root / "data/3_소성가공_예지보전/press_data_normal.csv").exists(),
                    child_returncode=result.returncode,
                    last_error_line=result.stderr.splitlines()[-1] if result.stderr else "",
                    child_command="05_requantize_audit.py --audit <vendor file> (same arguments as run_all.py)",
                    custom_out_diagnosis_omits_requantization="36설정" not in (reproduction / "diagnosis.md").read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--reproduction", type=Path)
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {"reviewed_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "python": sys.version.split()[0], "packages": {
        p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scikit-learn", "matplotlib", "scipy")},
        "input_sha256": {},
        "quantization": "05.quantize applied directly to all train/cal/test inputs; no CSV rounding step",
        "comparison_tolerance": "absolute 1e-9, relative 0",
        "scope": "Exploratory verification of already inspected data, not independent validation"}
    for p in sorted((args.root / "data/3_소성가공_예지보전").glob("*.csv")):
        manifest["input_sha256"][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    vendor = PIPE / "vendor/press_policy_audit.py"
    upstream = REPO / "yejun/analysis/press_welding_review/press_policy_audit.py"
    manifest["vendor_equal_to_codex"] = vendor.read_bytes() == upstream.read_bytes()
    if args.reproduction:
        comparison = compare_csvs(args.reproduction)
        comparison.to_csv(args.out / "reproduction_comparison.csv", index=False)
        manifest["all_csvs_reproduced_at_1e_9"] = bool(comparison.equal_at_1e_9.all())
        manifest["checks_json_equal"] = (json.loads((args.reproduction / "checks.json").read_text()) ==
                                        json.loads((SAVED / "checks.json").read_text()))
        manifest["custom_out_diagnosis_has_requantization"] = "36설정" in (args.reproduction / "diagnosis.md").read_text()
        paths = path_checks(args.root, args.reproduction)
        (args.out / "path_checks.json").write_text(json.dumps(paths, ensure_ascii=False, indent=2) + "\n")
    metrics, selections, saturation = extra_checks(args.root)
    metrics.to_csv(args.out / "quantization_and_alarm_policies.csv", index=False)
    selections.to_csv(args.out / "quantization_window_selection.csv", index=False)
    saturation.to_csv(args.out / "saturation_probe.csv", index=False)
    (args.out / "review_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    chosen = metrics[(metrics.budget == .01) & metrics.reselected_rule]
    print(chosen[["variant", "split", "selected_w", "cutoff_f1", "cutoff_normal_segments",
                  "cutoff_abnormal_segments", "conformal_f1", "conformal_abnormal_segments"]].to_string(index=False))


if __name__ == "__main__":
    main()
