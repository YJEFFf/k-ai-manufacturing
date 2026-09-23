"""Audit the supplied welding data and demonstrate UNLABELLED anomaly scores.

Run from any directory: python analysis/welding/deep_dive.py
No defect labels are inferred, no input files are modified, and no network is used.
Scores and reference quantiles below are not defect probabilities or F1 results.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import zipfile
from collections import Counter
from difflib import SequenceMatcher
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler
from sklearn.svm import OneClassSVM


FEATURES = ["weld force(bar)", "weld current(kA)", "weld Voltage(v)", "weld time(ms)"]
DATE = "working time"
SEED = 7


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean_json(value.tolist())
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return clean_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def keys(frame, rounded=False):
    # Tuples preserve equality semantics without relying on hash collision odds.
    x = frame[FEATURES].round(6) if rounded else frame[FEATURES]
    return list(x.itertuples(index=False, name=None))


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 1.0


def top_indices(score, n):
    # Fixed stable tie handling; repeated identical records remain tied in reality.
    return set(np.argsort(-np.asarray(score), kind="stable")[:n].tolist())


def audit(root, out, plots):
    archives = sorted(root.glob("**/2.*.zip"))
    if len(archives) > 1:
        raise ValueError(f"Ambiguous task-2 archives: {archives}")
    if archives:
        source = archives[0]
        zip_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        with zipfile.ZipFile(source) as archive:
            book_name = next(n for n in archive.namelist() if n.endswith("Welding Data Set_01.xlsx"))
            csv_name = next(n for n in archive.namelist() if n.endswith("scaled_data.csv"))
            book_bytes = archive.read(book_name)
            csv_bytes = archive.read(csv_name)
    else:
        books = sorted(root.rglob("Welding Data Set_01.xlsx"))
        if len(books) != 1:
            raise ValueError(f"Expected one extracted workbook, found: {books}")
        source = books[0]
        zip_sha = None
        book_bytes = source.read_bytes()
        csv_bytes = (source.parent / "scaled_data.csv").read_bytes()
    sheets = pd.read_excel(io.BytesIO(book_bytes), sheet_name=None)
    raw = sheets["Raw data"].copy()
    raw.columns = raw.columns.str.strip()
    result = sheets["result"].copy()
    result.columns = result.columns.str.strip()
    scaled = pd.read_csv(io.BytesIO(csv_bytes), encoding="cp949")
    out.mkdir(parents=True, exist_ok=True)

    report = {
        "scope": "Data audit and unlabelled scoring demonstration; NOT defect prediction validation",
        "input_source": str(source.relative_to(root)),
        "sha256": {"zip": zip_sha,
                   "xlsx": hashlib.sha256(book_bytes).hexdigest(),
                   "csv": hashlib.sha256(csv_bytes).hexdigest()},
        "versions": {"python": platform.python_version(), **{p: version(p) for p in
                     ["numpy", "pandas", "scipy", "scikit-learn", "openpyxl"]}},
        "seed": SEED,
        "sheet_shapes": {s: list(d.shape) for s, d in sheets.items()},
        "raw_missing": raw.isna().sum().to_dict(),
        "scaled_missing": scaled.isna().sum().to_dict(),
        "constant_columns": [c for c in raw if raw[c].nunique(dropna=False) == 1],
        "sensor_summary": raw[FEATURES].describe(percentiles=[.01, .05, .5, .95, .99]).to_dict(),
        "unique_sensor_vectors_exact": len(set(keys(raw))),
        "unique_sensor_vectors_rounded6": len(set(keys(raw, True))),
        "duplicate_date_idx_rows": raw[raw.duplicated([DATE, "idx"], keep=False)].assign(
            excel_row=lambda d: d.index + 2).to_dict("records"),
        "result_defect_sum_NOT_unique_bad_parts": int(result["defect"].sum()),
        "result_label_status": "Likely counts by date/type; row linkage, unit and inspection denominator unconfirmed",
    }

    workbook = load_workbook(io.BytesIO(book_bytes), data_only=False)
    report["workbook_metadata"] = {}
    for sheet in workbook:
        cells = [c for row in sheet.iter_rows() for c in row if c.value is not None]
        report["workbook_metadata"][sheet.title] = {
            "visibility": sheet.sheet_state,
            "formula_count": sum(c.data_type == "f" for c in cells),
            "comment_count": sum(c.comment is not None for c in cells),
            "hidden_rows": [n for n, d in sheet.row_dimensions.items() if d.hidden],
            "hidden_columns": [n for n, d in sheet.column_dimensions.items() if d.hidden],
        }
    report["suspected_date_typos_NOT_corrected"] = {
        address: workbook["Raw data"][address].value.isoformat()
        for address in ("D3552", "D5201")}
    report["extracted_input_matches_zip"] = {} if archives else None
    if archives:
        for filename, archive_bytes in (("Welding Data Set_01.xlsx", book_bytes), ("scaled_data.csv", csv_bytes)):
            for local_file in root.rglob(filename):
                report["extracted_input_matches_zip"][str(local_file.relative_to(root))] = (
                    hashlib.sha256(local_file.read_bytes()).digest() == hashlib.sha256(archive_bytes).digest())

    # Inferred affine inverse, checked against workbook display precision.
    # This is NOT an official scaler nor a recovered physical-record identity.
    slopes = np.array([118.26, 139.78, 95.78, 2170.])
    offsets = np.array([1.74, 14.52, 2.46, 70.])
    inverse = scaled.iloc[:, 1:].to_numpy() * slopes + offsets
    lower, upper = np.array([1, 12, 1.5, 30]), np.array([12, 18, 3.5, 120])
    missing = np.isnan(inverse)
    outside = (inverse < lower) | (inverse > upper)
    flagged = missing | outside
    display_scale = np.array([100., 100., 100., 1.])
    raw_display = np.floor(raw[FEATURES].to_numpy() * display_scale + .50000001) / display_scale
    csv_display = np.column_stack([np.round(inverse[:, i], 2 if i < 3 else 0) for i in range(4)])
    raw_counter = Counter(map(tuple, raw_display))
    csv_unflagged = csv_display[~flagged.any(axis=1)]
    report["scaled_csv_candidate_reconstruction"] = {
        "status": "Inferred and numerically checked; official preprocessing provenance unavailable",
        "feature_order": FEATURES, "slopes": slopes, "offsets": offsets,
        "minimum": np.nanmin(inverse, axis=0), "maximum": np.nanmax(inverse, axis=0),
        "missing_by_feature": missing.sum(axis=0), "outside_collection_range_by_feature": outside.sum(axis=0),
        "flagged_cells": flagged.sum(), "flagged_rows": flagged.any(axis=1).sum(),
        "unflagged_rows": len(csv_unflagged),
        "unflagged_rows_matching_raw_display_multiset": sum((raw_counter & Counter(map(tuple, csv_unflagged))).values()),
        "note": "Collection limits are not weld quality labels; matching repeated tuples does not identify a unique row",
    }

    # Only declared collection limits, not quality-acceptance or safe-process limits.
    limits = {"Thickness 1(mm)": (.3, 2.3), "Thickness 2(mm)": (.3, 2.3),
              FEATURES[0]: (1, 12), FEATURES[1]: (12, 18),
              FEATURES[2]: (1.5, 3.5), FEATURES[3]: (30, 120)}
    report["outside_declared_collection_range"] = {
        c: int((~raw[c].between(lo, hi)).sum()) for c, (lo, hi) in limits.items()}

    dates = sorted(raw[DATE].unique())
    daily = []
    prior_exact, prior_rounded = set(), set()
    for date in dates:
        g = raw[raw[DATE] == date]
        ek, rk = keys(g), keys(g, True)
        rr = result[result[DATE] == date]
        row = {
            "date": str(date)[:10], "records": len(g), "idx_unique": g["idx"].nunique(),
            "idx_min": g["idx"].min(), "idx_max": g["idx"].max(),
            "idx_monotonic_in_file": g["idx"].is_monotonic_increasing,
            "unique_vectors_exact": len(set(ek)),
            "seen_in_earlier_dates_exact": sum(k in prior_exact for k in ek),
            "seen_in_earlier_dates_rounded6": sum(k in prior_rounded for k in rk),
            "pressure_gt5_descriptive_only": int((g[FEATURES[0]] > 5).sum()),
            "recorded_defect_sum_NOT_unique_parts": rr["defect"].sum() if len(rr) else None,
        }
        for defect_type in (1, 2, 3):
            v = rr.loc[rr["defect type"] == defect_type, "defect"]
            row[f"recorded_type{defect_type}"] = int(v.iloc[0]) if len(v) == 1 else None
        daily.append(row)
        prior_exact.update(ek)
        prior_rounded.update(rk)
    daily_df = pd.DataFrame(daily)
    daily_df.to_csv(out / "daily_audit.csv", index=False)
    report["daily"] = daily

    # Search contiguous sensor sequences in workbook file order, NOT sorted idx.
    matches = []
    for i, date_a in enumerate(dates):
        a = raw[raw[DATE] == date_a]
        for date_b in dates[i + 1:]:
            b = raw[raw[DATE] == date_b]
            for mode in ("exact", "rounded6"):
                m = SequenceMatcher(None, keys(a, mode == "rounded6"),
                                    keys(b, mode == "rounded6"), autojunk=False).find_longest_match()
                if m.size >= 100:
                    matches.append({"date_a": str(date_a)[:10], "date_b": str(date_b)[:10],
                                    "mode": mode, "offset_a_0based": m.a,
                                    "offset_b_0based": m.b, "length": m.size})
    report["long_contiguous_repeated_sensor_sequences"] = matches
    pd.DataFrame(matches).to_csv(out / "repeated_sequences.csv", index=False)

    # First two dates already cover every exact sensor vector in later dates.
    # These demonstrations explicitly do not offer independent future validation.
    train = raw[raw[DATE] <= dates[1]].copy()
    test = raw[raw[DATE] > dates[1]].copy()
    x_train = train[FEATURES].to_numpy()
    x_test = test[FEATURES].to_numpy()
    x_unique = train[FEATURES].drop_duplicates().to_numpy()
    center = np.median(x_train, axis=0)
    mad = 1.4826 * np.median(np.abs(x_train - center), axis=0)
    mad = np.where(mad > 0, mad, np.std(x_train, axis=0))
    mad = np.where(mad > 0, mad, 1)
    robust = lambda x: np.max(np.abs((x - center) / mad), axis=1)

    scaler = RobustScaler().fit(x_train)
    scaled_train, scaled_test = scaler.transform(x_train), scaler.transform(x_test)
    isolation = IsolationForest(n_estimators=300, max_samples=256, random_state=SEED,
                                contamination="auto", n_jobs=1).fit(scaled_train)
    svm = OneClassSVM(kernel="rbf", gamma="scale", nu=.01).fit(scaled_train)
    train_scores = {"robust_deviation": robust(x_train),
                    "isolation_forest": -isolation.score_samples(scaled_train),
                    "one_class_svm": -svm.score_samples(scaled_train)}
    test_scores = {"robust_deviation": robust(x_test),
                   "isolation_forest": -isolation.score_samples(scaled_test),
                   "one_class_svm": -svm.score_samples(scaled_test)}
    scores = test[[DATE, "idx"] + FEATURES].copy()
    scores.insert(0, "excel_row", test.index + 2)
    thresholds = {}
    for name, score in test_scores.items():
        thresholds[name] = float(np.quantile(train_scores[name], .99))
        scores[name + "_score"] = score
        scores[name + "_reference_exceedance"] = score > thresholds[name]
    scores.to_csv(out / "unlabelled_scores.csv", index=False)
    rates = scores.groupby(DATE)[[c for c in scores if c.endswith("_reference_exceedance")]].mean()
    rates.to_csv(out / "reference_exceedance_by_date.csv")
    selections = []
    for date, group in scores.groupby(DATE):
        masks = {name: group[name + "_reference_exceedance"] for name in test_scores}
        selections.append({"date": str(date)[:10],
                           "counts": {name: int(mask.sum()) for name, mask in masks.items()},
                           "robust_and_isolation": int((masks["robust_deviation"] & masks["isolation_forest"]).sum()),
                           "all_three": int(np.logical_and.reduce(list(masks.values())).sum())})

    # Repeated record frequency changes a density detector. Measure sensitivity,
    # rather than assuming either weighting represents true production frequency.
    unique_scaled = scaler.transform(x_unique)
    top_n = int(np.ceil(.05 * len(x_unique)))
    reference_top = top_indices(-isolation.score_samples(unique_scaled), top_n)
    iso_dedup = IsolationForest(n_estimators=300, max_samples=256, random_state=SEED,
                                contamination="auto", n_jobs=1).fit(unique_scaled)
    dedup_top = top_indices(-iso_dedup.score_samples(unique_scaled), top_n)
    stability = []
    for seed in (0, 7, 42):
        model = IsolationForest(n_estimators=300, max_samples=256, random_state=seed,
                                contamination="auto", n_jobs=1).fit(scaled_train)
        selected = top_indices(-model.score_samples(unique_scaled), top_n)
        stability.append({"seed": seed, "top5pct_jaccard_vs_seed7": jaccard(reference_top, selected)})
    unique_scores = {"robust_deviation": robust(x_unique),
                     "isolation_forest": -isolation.score_samples(unique_scaled),
                     "one_class_svm": -svm.score_samples(unique_scaled)}
    agreement = {}
    for a in unique_scores:
        for b in unique_scores:
            if a < b:
                agreement[a + "__" + b] = jaccard(top_indices(unique_scores[a], top_n),
                                                  top_indices(unique_scores[b], top_n))
    reference_keys = set(keys(train))
    report["unlabelled_model_demonstration"] = {
        "reference_dates": [str(dates[0])[:10], str(dates[1])[:10]],
        "reference_rows": len(train), "reference_unique_vectors": len(x_unique),
        "later_rows": len(test),
        "later_vectors_seen_in_reference_exact": sum(k in reference_keys for k in keys(test)),
        "threshold_rule": "99th percentile on fitted reference records; NOT calibrated false positive rate",
        "thresholds": thresholds,
        "later_reference_exceedance_rates": rates.reset_index().to_dict("records"),
        "reference_exceedance_selection_overlap": selections,
        "top5pct_unique_vector_count": top_n,
        "top5pct_pairwise_jaccard": agreement,
        "isolation_forest_top5pct_jaccard_raw_vs_deduplicated_fit": jaccard(reference_top, dedup_top),
        "isolation_forest_seed_sensitivity": stability,
        "quality_metrics": None,
        "limitations": ["No individual defect labels", "All later exact sensor vectors already observed",
                        "Reference data not verified defect-free", "Density sensitive to duplicate frequency",
                        "SVM nu=.01 is a regularization setting, not a measured defect rate",
                        "No defect F1, miss rate, false alarm rate or optimal model selection justified"],
    }

    if plots:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 1, figsize=(12, 10), constrained_layout=True)
        for date in dates:
            g = raw[raw[DATE] == date]
            axes[0].scatter(g.index, g[FEATURES[0]], s=3, label=str(date)[5:10], alpha=.7)
        axes[0].set(title="Observed pressure by workbook row (not quality labels)",
                    xlabel="Workbook data row, zero-based", ylabel="Pressure (bar)")
        axes[0].legend(ncol=9, fontsize=8, loc="upper left")
        axes[1].bar(daily_df["date"].str[5:],
                    100 * daily_df["seen_in_earlier_dates_exact"] / daily_df["records"], color="#3477a1")
        axes[1].set(title="Exact sensor vectors already seen in earlier dates", ylabel="Records (%)", ylim=(0, 108))
        # Entire 800-record 4/3 block is replayed within 3/25. Overlay deliberately.
        a = raw[raw[DATE] == pd.Timestamp("2020-03-25")][FEATURES[0]].iloc[270:1070].to_numpy()
        b = raw[raw[DATE] == pd.Timestamp("2020-04-03")][FEATURES[0]].to_numpy()
        axes[2].plot(a, color="#3477a1", linewidth=3, label="03-25 records 271-1070")
        axes[2].plot(b, color="#e17b30", linestyle="--", linewidth=1, label="04-03 all 800 records")
        axes[2].set(title="Repeated 800-record sequence (all four sensors match)",
                    xlabel="Position in compared sequence", ylabel="Pressure (bar)")
        axes[2].legend()
        fig.savefig(out / "welding_data_audit.png", dpi=170)
        plt.close(fig)
        report["versions"]["matplotlib"] = version("matplotlib")

    (out / "audit.json").write_text(json.dumps(clean_json(report), ensure_ascii=False, indent=2,
                                              allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(clean_json({"rows": len(raw), "unique_vectors": report["unique_sensor_vectors_exact"],
                                "output": str(out), "model_demo": report["unlabelled_model_demonstration"]}),
                     ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "outputs")
    parser.add_argument("--plots", action="store_true", help="Requires matplotlib")
    args = parser.parse_args()
    audit(args.root.resolve(), args.out.resolve(), args.plots)
