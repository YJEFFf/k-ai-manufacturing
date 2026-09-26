"""Read-only E3 audit: independent aggregation and selected full refits.

Run from the repository root with the project's Python environment.
Only files in this review directory are written.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SUPPLEMENT = HERE.parent / "press_supplement"
sys.path.insert(0, str(SUPPLEMENT))
import recalibration as experiment


def main():
    curve = pd.read_csv(SUPPLEMENT / "e3_curve.csv")
    stored = pd.read_csv(SUPPLEMENT / "e3_stability.csv")
    baseline = pd.read_csv(SUPPLEMENT / "e3_domain_shift.csv")
    baseline = baseline[(baseline.gain == 1) & (baseline.condition == "frozen")].iloc[0]
    relative_floor = float(baseline.inject_min - 0.1)
    rows = []
    for (alpha, nt, nc), group in curve.groupby(["alpha", "n_train", "n_cal"]):
        row = dict(alpha=alpha, n_train=int(nt), n_cal=int(nc), starts=len(group),
                   normal_minutes_median=float(group.normal_minutes.median()),
                   normal_notified_max=int(group.normal_notified.max()),
                   abnormal_detected_min=int(group.abnormal_detected.min()),
                   injection_min=float(group.inject_min.min()),
                   f1_min=float(group.f1.min()))
        eligible = bool((group.normal_notified <= 3).all() and (group.abnormal_detected == 21).all())
        row["preregistered_pass"] = eligible and bool((group.inject_min >= 0.9).all())
        row["posthoc_relative_pass"] = eligible and bool((group.inject_min >= relative_floor).all())
        original = stored[(stored.alpha == alpha) & (stored.n_train == nt) & (stored.n_cal == nc)].iloc[0]
        assert bool(original.stable) == row["preregistered_pass"]
        assert np.isclose(original.normal_minutes, row["normal_minutes_median"])
        assert np.isclose(original.f1_min, row["f1_min"])
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(HERE / "e3_independent_stability.csv", index=False)
    selected = []
    for alpha in (0.01, 0.05):
        group = summary[(summary.alpha == alpha) & summary.posthoc_relative_pass]
        selected.append(group.sort_values("normal_minutes_median").iloc[0].to_dict())

    # Refit representative small and larger configurations without touching
    # the frozen artifacts or original experiment outputs.
    spot = []
    for cfg in [(0.01, 15, 99, 0), (0.01, 15, 99, 360), (0.05, 60, 40, 0)]:
        fresh = experiment.run_config(cfg)
        alpha, nt, nc, start = cfg
        old = curve[(curve.alpha == alpha) & (curve.n_train == nt) &
                    (curve.n_cal == nc) & (curve.start == start)].iloc[0]
        diff = {key: float(value - old[key]) for key, value in fresh.items()
                if isinstance(value, (int, float, np.number))}
        assert all(abs(d) < 1e-10 for d in diff.values()), (cfg, diff)
        spot.append(dict(config=cfg, max_absolute_difference=max(abs(d) for d in diff.values()),
                         fresh=fresh))
        print("Refit matched:", cfg, flush=True)

    report = dict(configurations=len(curve), settings=len(summary),
                  preregistered_pass_count=int(summary.preregistered_pass.sum()),
                  posthoc_relative_floor=relative_floor,
                  posthoc_minimum_settings=selected, refit_checks=spot,
                  scope="same-day exploratory evidence; no new-date or real-failure validation")
    (HERE / "e3_independent_checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
