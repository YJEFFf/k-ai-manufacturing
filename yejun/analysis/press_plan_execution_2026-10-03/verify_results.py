"""Independent count reconciliation, historical regression and checkpoint checks."""
import json
import pickle

from common import (HERE, LEGACY, np, pd, core, load_press, save, csv, metrics, sha, environment)
from heldout import verify_freeze
from press import fit_candidates
from predict import predict


def verify(output):
    checks = []
    def check(name, ok, details=None):
        checks.append(dict(check=name, passed=bool(ok), details=details))
    verify_freeze(output)
    check("frozen_inputs_code_environment_and_artifacts", True)
    normal, audit = load_press()
    abnormal, _ = load_press("abnormal")
    selected = json.loads((output / "selection.json").read_text(encoding="utf-8"))
    check("no_candidate_is_not_baseline_adoption", selected["selected_candidate"] is not None or not selected["improvement_established"])
    check("original_20000_rows_and_one_duplicate_preserved", audit["source_mapping_rows"] == 20000 and audit["records"] == 599)
    predictions = pd.read_csv(output.parent / "cache/press_P2_predictions.csv.gz")
    table = pd.read_csv(output / "press_common_metrics.csv")
    for model, rows in predictions.groupby("model"):
        result = metrics(rows.label, rows.bit, rows.score)
        stored = table.loc[table.model.eq(model)].iloc[0]
        for key in ["n", "tp", "fp", "fn", "tn", "f1", "precision", "recall", "accuracy"]:
            check(f"P2_{model}_{key}", np.isclose(result[key], stored[key], rtol=0, atol=1e-14))
    old = pd.read_csv(LEGACY / "evidence/v1/normal_summary.csv").query("alpha == 0.05")
    new = pd.read_csv(output / "press_normal_summary.csv").query("alpha == 0.05")
    for model in ["B1", "C1d1"]:
        a = old.loc[old.model.eq(model)].sort_values("fold").total_requests.to_numpy()
        b = new.loc[new.model.eq(model)].sort_values("fold").total_requests.to_numpy()
        check(f"historical_{model}_normal_requests", np.array_equal(a, b))
    old_pod = pd.read_csv(LEGACY / "evidence/v1/development_family_pod.csv")
    new_pod = pd.read_csv(output / "press_family_pod.csv")
    for model in ["B1", "C1d1"]:
        a = old_pod.loc[old_pod.model.eq(model)].sort_values("family").pod.to_numpy()
        b = new_pod.loc[new_pod.model.eq(model)].sort_values("family").pod.to_numpy()
        check(f"historical_{model}_registered_sensitivity", np.allclose(a, b, rtol=0, atol=1e-15))
    states = pickle.loads((output.parent / "artifacts/press_development.pkl").read_bytes())
    for fold in ["P0", "P1"]:
        roles = core.split_records(normal, fold)
        models, _, _ = fit_candidates(roles["fit"], core.features(roles["cal"]), fold)
        f = core.features(roles["evaluation"])
        for name in models:
            a, b = models[name].predict(f), states[fold][name].predict(f)
            check(f"refit_and_reload_{fold}_{name}", all(np.array_equal(a[k], b[k], equal_nan=True)
                  if a[k].dtype != object else np.array_equal(a[k], b[k]) for k in a))
    for role in ["dev", "test"]:
        p = pd.read_csv(output.parent / f"cache/skab_{role}_predictions.csv.gz")
        scores = pd.read_csv(output / f"skab_{role}_pooled.csv")
        for name, rows in p.groupby("model"):
            mask = ~rows.conflict & rows.lower.eq(rows.upper)
            result = metrics(rows.loc[mask, "lower"], rows.loc[mask, "bit"])
            stored = scores.loc[scores.model.eq(name)].iloc[0]
            check(f"skab_{role}_{name}_counts", all(result[k] == stored[k] for k in ["n", "tp", "fp", "fn", "tn"]))
            check(f"skab_{role}_{name}_partials_not_dropped", len(rows) >= result["n"] and not rows.loc[rows.n.ne(20), "supported"].any())
    access = json.loads((output / "skab_development_access.json").read_text(encoding="utf-8"))
    check("development_did_not_open_test", all(r["role"] != "test" for r in access))
    external = json.loads((output / "skab_test_access.json").read_text(encoding="utf-8"))
    freeze = json.loads((output / "freeze.json").read_text(encoding="utf-8"))
    check("external_test_only_after_freeze", all(r["at_utc"] >= freeze["frozen_utc"] for r in external))
    heads = json.loads((output / "probability_heads.json").read_text(encoding="utf-8"))
    check("probability_optimizer_contracts", all(v["status"] in ["uninformative", "unsupported_missing_class"] or
          (v["status"] == "fitted" and v["projected_gradient"] <= 1e-6) for v in heads.values()))
    curves = pd.read_csv(output / "heldout_curves.csv")
    h2 = curves.loc[curves.family.eq("H2")]
    check("H2_RMS_only_negative_control", bool(h2.new_detections.eq(0).all()))
    repro = json.loads((output / "junyong_reproduction.json").read_text(encoding="utf-8"))
    check("junyong_read_only", repro["source_unchanged"])
    check("junyong_full_metric_grid_reproduced", repro["cells"] == repro["expected_cells"] and all(repro["exact_count_comparison"].values()) and repro["max_abs_f1_difference"] < 1e-12)
    # Relabel and rename input CSV: inference still uses only timestamp and sensors.
    original = pd.read_csv(HERE / "data/press/outlier_data.csv")
    original["Equipment_state"] = 0
    altered = output.parent / "cache/unknown_unlabelled_input.csv"
    original.drop(columns=["Equipment_state"]).to_csv(altered, index=False)
    pp = predict(altered, output.parent / "artifacts/press_frozen.pkl", output.parent / "cache/unknown_predictions.csv.gz")
    check("unknown_CSV_all_rows_mapped", len(pp) == 600*len(freeze["press_test_models"]))
    for name, rows in pp.groupby("model"):
        inferred = rows.groupby("record", sort=True).first()
        expected = predictions.loc[predictions.model.eq(name) & predictions.label.eq(1)].sort_values("parent")
        check(f"label_filename_independent_{name}", np.array_equal(inferred.mechanical_request, expected.bit))
    result = dict(checks=checks, passed=sum(c["passed"] for c in checks), total=len(checks),
                  all_passed=all(c["passed"] for c in checks), environment=environment(),
                  candidate_admitted=selected["selected_candidate"] is not None, field_validated=False)
    save(output / "verification.json", result)
    if not result["all_passed"]:
        raise AssertionError([r for r in checks if not r["passed"]])
    print(f"E6 verification {result['passed']}/{result['total']}", flush=True)
    return result


if __name__ == "__main__":
    verify(HERE / "evidence")
