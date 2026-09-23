"""Exploratory normal-only sensor-relation comparison for topic selection.

All model definitions, splits, and calibration budgets are fixed in this file.
No anomaly labels are used for fitting or threshold selection. Recording blocks
are not independent failures. All anomaly rows, including block starts, count.
Run from codex/: python analysis/press_welding_review/sensor_relation_audit.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score
from sklearn.preprocessing import StandardScaler

COLS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]


def blocks(df):
    delta = pd.to_datetime(df.TimeStamp).diff().dt.total_seconds()
    return (~np.isclose(delta, 0.1, atol=1e-6, rtol=0)).cumsum() - 1


def evaluate(normal, abnormal, sn, sa, threshold):
    pn, pa = sn > threshold, sa > threshold
    y = np.r_[np.zeros(len(sn), dtype=int), np.ones(len(sa), dtype=int)]
    pred = np.r_[pn, pa]
    gbn, gba = blocks(normal), blocks(abnormal)
    nblock = pd.Series(pn).groupby(gbn).any()
    ablock = pd.Series(pa).groupby(gba).any()
    delays = []
    times = pd.to_datetime(abnormal.TimeStamp)
    for _, group in abnormal.groupby(gba):
        indices = group.index.to_numpy()
        hits = indices[pa[indices]]
        if len(hits):
            delays.append((times.iloc[hits[0]] - times.iloc[indices[0]]).total_seconds())
    return {
        "threshold": float(threshold),
        "f1": float(f1_score(y, pred)),
        "ap": float(average_precision_score(y, np.r_[sn, sa])),
        "tn_fp_fn_tp": confusion_matrix(y, pred).ravel().tolist(),
        "normal_row_false_alarm_rate": float(pn.mean()),
        "normal_alert_blocks": int(nblock.sum()),
        "normal_total_blocks": len(nblock),
        "abnormal_detected_blocks": int(ablock.sum()),
        "abnormal_total_blocks": len(ablock),
        "median_delay_seconds_detected_blocks_only": float(np.median(delays)) if delays else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    archive = args.archive or next(root.rglob("Dataset_소성가공 예지보전 AI 데이터셋.zip"))
    with zipfile.ZipFile(archive) as z:
        members = {Path(n).name: n for n in z.namelist() if n.endswith(".csv")}
        raw = {name: z.read(members[name]) for name in ("press_data_normal.csv", "outlier_data.csv")}
        import io
        normal, abnormal = [pd.read_csv(io.BytesIO(raw[name])) for name in raw]
    ng = blocks(normal)
    results = []
    for train_fraction in (0.6, 0.5):
        train_end = int(ng.max() + 1) * train_fraction
        cal_end = int(ng.max() + 1) * (train_fraction + 0.2)
        tr = normal[ng < train_end].reset_index(drop=True)
        cal = normal[(ng >= train_end) & (ng < cal_end)].reset_index(drop=True)
        te = normal[ng >= cal_end].reset_index(drop=True)
        scaler = StandardScaler().fit(tr[COLS])
        xt, xc, xn, xa = [scaler.transform(df[COLS]) for df in (tr, cal, te, abnormal)]
        models = {
            "max_abs_z": [np.abs(x).max(axis=1) for x in (xc, xn, xa)],
            "diagonal_squared_distance": [(x * x).sum(axis=1) for x in (xc, xn, xa)],
        }
        for name, cols in (("full_sensor_covariance", [0, 1, 2]), ("vibration_covariance", [0, 1])):
            model = LedoitWolf().fit(xt[:, cols])
            models[name] = [model.mahalanobis(x[:, cols]) for x in (xc, xn, xa)]
        within = ((abnormal[COLS] >= tr[COLS].min()) & (abnormal[COLS] <= tr[COLS].max())).all(axis=1).to_numpy()
        for name, (sc, sn, sa) in models.items():
            for budget in (0.01, 0.03, 0.05):
                threshold = np.quantile(sc, 1 - budget)
                result = evaluate(te, abnormal, sn, sa, threshold)
                result.update({
                    "split": f"{int(train_fraction*100)}/20/{int(round((0.8-train_fraction)*100))}",
                    "model": name, "calibration_row_budget": budget,
                    "train_rows": len(tr), "calibration_rows": len(cal),
                    "test_normal_rows": len(te), "test_anomaly_rows": len(abnormal),
                    "anomaly_rows_within_all_train_sensor_ranges": int(within.sum()),
                    "detected_within_train_ranges": int(((sa > threshold) & within).sum()),
                    "calibration_actual_row_fpr": float((sc > threshold).mean()),
                })
                results.append(result)
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "source_csv_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in raw.items()},
        "scope": "Exploratory model comparison on already-seen data; not a new blind test or independent failure validation.",
        "model_selection": "All four fixed score definitions reported; no anomaly-based tuning or best-budget selection.",
        "limitations": [
            "One normal date and one abnormal date; date/state confounding remains.",
            "Row calibration budgets do not equate actual inspection workload; normal alerted blocks are also reported.",
            "Detected-block delay begins at first available abnormal observation, not physical fault onset.",
            "Comparing covariance scores probes statistical dependence, not a causal fault mechanism.",
        ],
        "results": results,
    }
    (args.out / "sensor_relation_results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    pd.DataFrame(results).to_csv(args.out / "sensor_relation_metrics.csv", index=False)
    print(pd.DataFrame(results)[["split", "model", "calibration_row_budget", "f1", "normal_alert_blocks", "abnormal_detected_blocks", "detected_within_train_ranges"]].to_string(index=False))


if __name__ == "__main__":
    main()
