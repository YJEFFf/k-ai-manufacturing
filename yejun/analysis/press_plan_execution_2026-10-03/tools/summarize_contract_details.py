"""Post-run reporting only: no candidate selection or heldout model fitting.

Consumes frozen predictions/states and previously used normal calibration inputs.
Its source hash is recorded separately from the model-evaluation freeze.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import pickle
import json

from common import HERE, core, np, pd, csv, save, load_press, rank, metrics, sha, now


def length_bins(n):
    return np.select([n < 10, n < 20, n < 40, n <= 50], ["1-9", "10-19", "20-39", "40-50"], default="outside")


def main(output):
    prediction = pd.read_csv(output.parent / "cache/press_development_predictions.csv.gz")
    models = pickle.loads((output.parent / "artifacts/press_development.pkl").read_bytes())
    normal, _ = load_press()
    result = []
    for fold in ["P0", "P1"]:
        calibration = core.features(core.split_records(normal, fold)["cal"])
        calibration["length_bin"] = length_bins(calibration.n)
        calibration["original_gate"] = models[fold]["B1"].model.condition(calibration)
        for alpha in [.05, .03, .01]:
            selected = prediction.loc[prediction.fold.eq(fold) & prediction.alpha.eq(alpha)]
            k1 = selected.loc[selected.model.eq("K1")].copy()
            k1["length_bin"] = length_bins(k1.n)
            wide = selected.loc[selected.model.isin(["B1", "C1d1", "K1"])].pivot(index="parent_key", columns="model", values="bit")
            calibration["route"] = models[fold]["K1"].predict(calibration, alpha)["route"]
            for (length, gate, route), group in k1.groupby(["length_bin", "original_gate", "route"]):
                ref = calibration.loc[calibration.length_bin.eq(length) & calibration.original_gate.eq(gate)]
                decisions = wide.loc[group.parent_key]
                result.append(dict(fold=fold, alpha=alpha, length_bin=length, original_gate=gate, route=route,
                    evaluation_parents=len(group), same_length_gate_cal_parents=len(ref),
                    same_length_gate_route_cal_parents=int(ref.route.eq(route).sum()),
                    actual_reference_n=int(group.n_cal.iloc[0]), unsupported=int((~group.supported).sum()),
                    B1_mechanical_requests=int(decisions.B1.sum()), C1_mechanical_requests=int(decisions.C1d1.sum()),
                    K1_mechanical_requests=int(decisions.K1.sum()),
                    K1_B1_disagreements=int(decisions.K1.ne(decisions.B1).sum()),
                    K1_C1_disagreements=int(decisions.K1.ne(decisions.C1d1).sum()),
                    reason="unsupported alpha resolution" if not group.supported.all() else
                           "conditional-only C1 calibration ranks" if route == "conditional_reference" else "exact pooled B1 fallback"))
    csv(output / "K1_route_by_length_gate.csv", result)
    state = pickle.loads((output.parent / "artifacts/probability.pkl").read_bytes())
    probabilities = pd.read_csv(output.parent / "cache/probability_predictions.csv.gz")
    threshold_rows = []
    for name, group in probabilities.loc[probabilities.q.eq(.1)].groupby("model"):
        model = state["models"][name]
        if name == "K1":
            raise ValueError("K1 probability rank report requires its stored gate, not raw-score ranking")
        p, supported = rank(group.raw_score.to_numpy(), model.reference, .05)
        threshold_rows.append(dict(model=name, threshold_cal_normal_minutes="50-60", n_cal=len(model.reference),
            alpha=.05, threshold_scope="probability diagnostic only; separate from main P2 cal 40-60",
            **metrics(group.label, p <= .05, group.raw_score)))
    csv(output / "probability_separate_threshold_metrics.csv", threshold_rows)
    save(output / "postrun_aggregation.json", dict(created_utc=now(), source_sha256=sha(__file__),
         scope="Route/calibration contribution aggregation and separate probability diagnostic threshold; no model changes",
         frozen_artifacts_unchanged=True, selected_candidate=json.loads((output / "selection.json").read_text(encoding="utf-8"))["selected_candidate"]))
    print(json.dumps(dict(route_cells=len(result), probability_threshold_models=len(threshold_rows))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "evidence")
    main(parser.parse_args().output.resolve())
