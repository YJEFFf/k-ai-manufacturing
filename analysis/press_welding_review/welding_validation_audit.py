"""Bounded welding audit: real daily labels and purged synthetic sensitivity.

Run with the reviewed Claude branch's code directory, for example:
  /opt/anaconda3/bin/python analysis/press_welding_review/welding_validation_audit.py \
    --claude-code /tmp/kai-claude-review.XP9eUV/claude/code

Daily models and alpha=10 are fixed before examining results. The synthetic
experiment reuses identical original validation/test injections across modes.
No per-weld real quality labels are invented.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import Ridge
from sklearn.metrics import average_precision_score, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ALPHA = 10.0
SENSOR_NAMES = ["force", "current", "voltage", "weld_time"]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def daily_audit(raw, labels, out):
    stats = raw.groupby("day")[SENSOR_NAMES].agg(["mean", "std"])
    stats.columns = [f"{a}_{b}" for a, b in stats.columns]
    stats["n_welds"] = raw.groupby("day").size()
    stats["actual"] = labels.groupby("day")["defect"].sum()
    days = stats.dropna(subset=["actual"]).copy()
    sensor_cols = [f"{c}_{s}" for c in SENSOR_NAMES for s in ["mean", "std"]]
    feature_sets = {
        "ridge_volume_alpha10": ["n_welds"],
        "ridge_sensors_alpha10": sensor_cols,
        "ridge_volume_sensors_alpha10": ["n_welds", *sensor_cols],
    }
    rows = []
    for day in days.index:
        train = days.drop(index=day)
        test = days.loc[[day]]
        predictions = {
            "mean_daily_count": float(train["actual"].mean()),
            "pooled_defect_rate_x_volume": float(train["actual"].sum() / train["n_welds"].sum() * test["n_welds"].iloc[0]),
        }
        for name, cols in feature_sets.items():
            model = make_pipeline(StandardScaler(), Ridge(alpha=ALPHA))
            model.fit(train[cols], train["actual"])
            predictions[name] = max(0.0, float(model.predict(test[cols])[0]))
        for name, pred in predictions.items():
            actual = float(test["actual"].iloc[0])
            rows.append({"model": name, "heldout_day": day, "n_train_days": len(train),
                         "test_welds": int(test["n_welds"].iloc[0]), "actual": actual,
                         "prediction": pred, "absolute_error": abs(pred - actual),
                         "squared_error": (pred - actual) ** 2})
    predictions = pd.DataFrame(rows)
    summaries = []
    mean_errors = predictions[predictions["model"] == "mean_daily_count"].set_index("heldout_day")["absolute_error"]
    rate_errors = predictions[predictions["model"] == "pooled_defect_rate_x_volume"].set_index("heldout_day")["absolute_error"]
    for name, group in predictions.groupby("model", sort=False):
        errors = group.set_index("heldout_day")["absolute_error"]
        summaries.append({"model": name, "MAE": float(errors.mean()),
                          "RMSE": float(np.sqrt(group["squared_error"].mean())),
                          "predicted_total": float(group["prediction"].sum()),
                          "days_better_than_mean": int((errors < mean_errors).sum()),
                          "days_better_than_rate": int((errors < rate_errors).sum()),
                          "MAE_improvement_vs_mean": float(mean_errors.mean() - errors.mean()),
                          "MAE_improvement_vs_rate": float(rate_errors.mean() - errors.mean())})
    summary = pd.DataFrame(summaries)
    stats.to_csv(out / "welding_daily_features.csv", index_label="day")
    predictions.to_csv(out / "welding_daily_lodo_predictions.csv", index=False)
    summary.to_csv(out / "welding_daily_lodo_metrics.csv", index=False)
    return summary, feature_sets, len(days)


def purge_mask(base, heldout, width=25):
    """Exclude training observations within width positions of test, within day."""
    train = ~heldout.copy()
    for _, group in base.groupby("day", sort=False):
        positions = group.index.to_numpy()
        local_test = heldout[positions]
        near = pd.Series(local_test.astype(int)).rolling(2 * width + 1, center=True, min_periods=1).max().to_numpy().astype(bool)
        train[positions[near]] = False
    return train


def contaminated_training_count(base, train, heldout, width=25):
    count = 0
    for _, group in base.groupby("day", sort=False):
        positions = group.index.to_numpy()
        for local, position in enumerate(positions):
            if train[position] and heldout[positions[max(0, local - width):local]].any():
                count += 1
    return count


def injection_audit(base, bench, out):
    specs = [spec for spec in bench.model_specs() if spec[0] in {"Ctx(raw)", "IsolationForest|phys"}]
    clean_views = bench.feature_views(base)
    fold_rows, counts, all_metrics = [], [], []
    for rate in [0.03, 0.005]:
        results = {"original": [], "purged_25": []}
        for fold in range(5):
            heldout = base["fold"].to_numpy() == fold
            original_train = ~heldout
            purged_train = purge_mask(base, heldout)
            masks = {"original": original_train, "purged_25": purged_train}
            if rate == 0.03:
                for mode, train in masks.items():
                    counts.append({"fold": fold, "mode": mode, "train_rows": int(train.sum()),
                                   "purged_rows": int(original_train.sum() - train.sum()),
                                   "test_rows": int(heldout.sum()),
                                   "training_context_using_test_history": contaminated_training_count(base, train, heldout)})
            fitted = {
                mode: {name: make().fit(clean_views[view].loc[train]) for name, view, make in specs}
                for mode, train in masks.items()
            }
            train_pos, test_pos = np.flatnonzero(original_train), np.flatnonzero(heldout)
            for seed in bench.SEEDS:
                rng = np.random.default_rng(seed * 100 + fold)
                validation = bench.inject(base, train_pos, rate, rng)
                test = bench.inject(base, test_pos, rate, rng)
                validation_views, test_views = bench.feature_views(validation), bench.feature_views(test)
                truth = test.loc[heldout, "y"].to_numpy()
                for mode, train in masks.items():
                    for name, view, _ in specs:
                        model = fitted[mode][name]
                        threshold = bench.best_f1_threshold(validation.loc[train, "y"].to_numpy(), model.score(validation_views[view].loc[train]))
                        scores = model.score(test_views[view].loc[heldout])
                        predicted = (scores >= threshold).astype(int)
                        tp = int(((truth == 1) & (predicted == 1)).sum())
                        fp = int(((truth == 0) & (predicted == 1)).sum())
                        fn = int(((truth == 1) & (predicted == 0)).sum())
                        tn = int(((truth == 0) & (predicted == 0)).sum())
                        fold_rows.append({"rate": rate, "mode": mode, "model": name, "fold": fold,
                                          "seed": seed, "n_train": int(train.sum()), "n_test": len(truth),
                                          "n_validation_positive": int(validation.loc[train, "y"].sum()),
                                          "n_test_positive": int(truth.sum()), "threshold": threshold,
                                          "TP": tp, "FP": fp, "FN": fn, "TN": tn,
                                          "F1": f1_score(truth, predicted, zero_division=0)})
                        results[mode].append(pd.DataFrame({"model": name, "seed": seed, "fold": fold,
                                                          "y": truth, "prediction": predicted, "score": scores,
                                                          "high_force": base.loc[heldout, "high_force_block"].to_numpy()}))
            print(f"injection rate={rate} fold={fold} original+purged complete", flush=True)
        for mode, pieces in results.items():
            joined = pd.concat(pieces, ignore_index=True)
            for (name, seed), group in joined.groupby(["model", "seed"]):
                for scope, selected in [("all", group), ("outside_high_force", group[~group["high_force"]])]:
                    y, p = selected["y"], selected["prediction"]
                    tp = int(((y == 1) & (p == 1)).sum())
                    fp = int(((y == 0) & (p == 1)).sum())
                    fn = int(((y == 1) & (p == 0)).sum())
                    all_metrics.append({"rate": rate, "mode": mode, "model": name, "seed": seed,
                                        "scope": scope, "n_test": len(selected), "n_positive": int(y.sum()),
                                        "TP": tp, "FP": fp, "FN": fn,
                                        "F1": f1_score(y, p, zero_division=0),
                                        "precision": tp / (tp + fp) if tp + fp else 0,
                                        "recall": tp / (tp + fn) if tp + fn else 0,
                                        "AP_pooled_scores": average_precision_score(y, selected["score"]),
                                        "alerts_per_1000": float(1000 * p.mean())})
    fold_counts = pd.DataFrame(counts)
    metrics = pd.DataFrame(all_metrics)
    summary = metrics.groupby(["rate", "mode", "model", "scope"])[["F1", "precision", "recall", "AP_pooled_scores", "alerts_per_1000"]].agg(["mean", "std"])
    summary.columns = [f"{a}_{b}" for a, b in summary.columns]
    summary = summary.reset_index()
    fold_counts.to_csv(out / "welding_injection_fold_counts.csv", index=False)
    pd.DataFrame(fold_rows).to_csv(out / "welding_injection_fold_results.csv", index=False)
    metrics.to_csv(out / "welding_injection_seed_metrics.csv", index=False)
    summary.to_csv(out / "welding_injection_metrics.csv", index=False)
    return summary, fold_counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude-code", type=Path, required=True)
    parser.add_argument("--xlsx", type=Path)
    parser.add_argument("--daily-only", action="store_true")
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    repo = out.parents[1]
    xlsx = args.xlsx or next(repo.rglob("Welding Data Set_01.xlsx"))
    sys.path.insert(0, str(args.claude_code))
    import wlib
    diag = load_module("claude_diag_review", args.claude_code / "01_diagnose_welding.py")
    bench = load_module("claude_injection_review", args.claude_code / "04_injection_benchmark.py")
    xls = pd.ExcelFile(xlsx)
    raw = xls.parse("Raw data")
    raw.columns = diag.RAW_COLS
    raw["day"] = pd.to_datetime(raw["day"]).dt.strftime("%Y-%m-%d")
    raw["row"] = np.arange(len(raw))
    labels = xls.parse("result").iloc[:, :6]
    labels.columns = ["idx", "machine", "item", "day", "defect", "defect_type"]
    labels["day"] = pd.to_datetime(labels["day"]).dt.strftime("%Y-%m-%d")
    daily, feature_sets, n_days = daily_audit(raw, labels, out)
    print("DAILY STRICT LODO", flush=True)
    print(daily.to_string(index=False), flush=True)
    manifest = {
        "python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
        "sklearn": sklearn.__version__, "source_xlsx": str(xlsx),
        "xlsx_sha256": hashlib.sha256(xlsx.read_bytes()).hexdigest(),
        "claude_code_dir": str(args.claude_code),
        "code_sha256": {name: hashlib.sha256((args.claude_code / name).read_bytes()).hexdigest()
                        for name in ["01_diagnose_welding.py", "04_injection_benchmark.py", "wlib.py"]},
        "daily_alpha_fixed_in_advance": ALPHA, "daily_feature_sets_fixed_in_advance": feature_sets,
        "label_days": n_days, "label_rows": len(labels), "total_real_defects": int(labels["defect"].sum()),
        "daily_metrics": daily.to_dict("records"),
        "daily_task": "After all same-day sensor values are observed, estimate daily defect count; no per-weld prediction or advance forecast.",
        "limitations": ["Eight labeled days with repeated sensor sequences are not eight convincingly independent production samples.",
                        "Daily models are exploratory, pre-fixed alpha10 comparisons; no independent final confirmation set.",
                        "Synthetic labels mark prescribed perturbations; unmodified rows are not verified good products.",
                        "Purging removes adjacent training observations; calibration still uses perturbed fitting-source rows.",
                        "AP pools scores from separate fold models and is retained only for comparison with the original report."],
    }
    if not args.daily_only:
        raw["is_copy"], _, _, raw["source_row"] = diag.find_copies(raw, 27)
        raw["fold"] = wlib.make_folds(raw)
        raw["high_force_block"] = raw["force"] > 5
        raw["welds_since_reset"] = np.nan
        base = raw[~raw["is_copy"]].sort_values("row").reset_index(drop=True)
        injection, fold_counts = injection_audit(base, bench, out)
        manifest["representative_rows"] = len(base)
        manifest["injection_seeds"] = bench.SEEDS
        manifest["injection_fold_counts"] = fold_counts.to_dict("records")
        manifest["injection_metrics"] = injection.to_dict("records")
        print("SYNTHETIC SENSITIVITY", flush=True)
        print(injection[injection["scope"] == "all"].to_string(index=False), flush=True)
    (out / "welding_validation_summary.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
