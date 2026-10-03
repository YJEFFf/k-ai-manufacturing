"""Derive the training-use conclusion; do not train or select another model."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCES = ["uci", "skab", "beihang", "espset", "all_four"]


def summarize(e):
    m = pd.read_csv(e/"metrics.csv")
    primary = m[m.alpha.eq(.05)].copy()
    scratch = primary[primary.source.eq("target_scratch_reference")][["fold", "seed", "view", "f1", "fp", "fn"]]
    base = primary[primary.method.eq("fixed_base")][["fold", "f1", "fp", "fn"]]
    aug = primary[primary.source.isin(SOURCES)].copy()
    against = aug.merge(base, on="fold", suffixes=("", "_base"), validate="many_to_one")
    against["delta_f1_vs_base"] = against.f1-against.f1_base
    against.to_csv(e/"against_fixed_target_base.csv", index=False)
    ae = aug[aug.method.eq("pretrained_ae")].merge(scratch, on=["fold", "seed", "view"], suffixes=("", "_scratch"), validate="many_to_one")
    ae["delta_f1_vs_scratch"] = ae.f1-ae.f1_scratch
    ae.to_csv(e/"against_target_scratch.csv", index=False)
    headline = primary[primary.view.eq("integrated") & (primary.ratio.eq(1) | (primary.source.eq("target_only") & ~primary.method.eq("fixed_base")))].groupby(["method", "source"])[["f1", "fp", "fn"]].mean().reset_index()
    headline.to_csv(e/"headline_ratio1.csv", index=False)
    folds = json.loads((e/"folds.json").read_text())
    resolution = []
    for fold, roles in folds.items():
        for alpha in [.05, .01, .03]:
            n = roles["role_counts"]["cal"]
            resolution.append(dict(fold=fold, normal_cal_records=n, alpha=alpha, minimum_attainable_p=1/(n+1), threshold_can_alarm=1/(n+1) <= alpha))
    pd.DataFrame(resolution).to_csv(e/"calibration_resolution.csv", index=False)
    summary = pd.read_csv(e/"training_utility_summary.csv")
    scratch_mean = float(primary[primary.source.eq("target_scratch_reference") & primary.view.eq("vibration_only")].f1.mean())
    above_base = int((against.view.eq("integrated") & against.delta_f1_vs_base.gt(1e-12)).sum())
    # These interpretation sentences must be re-reviewed if regenerated numbers change.
    assert (summary[summary.method.eq("pooled_knn") & summary.view.eq("vibration_only")].delta_f1_mean < 0).all()
    assert (summary[summary.method.eq("pretrained_ae") & summary.view.eq("vibration_only")].augmented_f1_mean < scratch_mean).all()
    assert above_base == 0
    conclusion = {
        "scope": "Two registered shared-vibration training routes only; no claim that all possible transfer learning is ineffective.",
        "technical_training_connection": dict.fromkeys(SOURCES[:-1], "implemented and trained"),
        "direct_three_sensor_row_concatenation": "not performed; missing current and differing physical inputs were not fabricated",
        "normal_pooling_vibration_view": "every source and both amount settings have lower mean F1 than target-only kNN",
        "pretraining_vibration_view": "some mean gains against 600-step target-only control, but all source-setting means below the 300-step target-only reference; mixed seed/fold directions",
        "target_scratch_vibration_mean_f1": scratch_mean,
        "fixed_target_base_mean_f1": float(base.f1.mean()),
        "external_integrated_comparisons_above_same_fold_fixed_base": above_base,
        "external_integrated_comparisons": int(against.view.eq("integrated").sum()),
        "interpretation_of_small_integrated_gains": "SKAB normal pooling cancels one extra P0 false positive introduced by the spectral branch; at best ties the fixed target-only base, does not surpass it.",
        "recommendation": "Do not adopt any of the four or their mixture as proven beneficial training augmentation on this evidence. Retain as technically usable transfer sources, with this experiment and its negative results preserved.",
        "target_validation_limit": "all three folds reuse the same previously explored abnormal episode; no new independent fault generalization evidence",
        "new_model_selection": "out of scope; no existing final-model decision changed"
    }
    (e/"training_use_conclusion.json").write_text(json.dumps(conclusion, ensure_ascii=False, indent=2)+"\n")
    print(headline.to_string(index=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=str(HERE/"evidence"))
    args = p.parse_args()
    summarize(Path(args.output).resolve())
