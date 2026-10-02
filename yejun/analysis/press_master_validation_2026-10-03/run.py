"""Reproduce registered development first, then a separately recorded P2 audit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import itertools
import platform
import time

import numpy as np
import pandas as pd
import scipy

from core import (HERE, MASTER, DESIGN, PROTOCOL, BINS, Detector, Generator,
                  features, fit_suite, load_records, save_json, sha, split_records)


def manifest(mode, design=DESIGN):
    return dict(mode=mode, started_utc=datetime.now(timezone.utc).isoformat(),
                design=design, design_sha256=sha(HERE / "design_v1.json"),
                master_protocol_sha256=sha(MASTER / "protocol.json"),
                code_sha256={p.name: sha(p) for p in sorted(HERE.glob("*.py"))},
                inputs=PROTOCOL["input"],
                environment=dict(python=platform.python_version(), numpy=np.__version__,
                                 pandas=pd.__version__, scipy=scipy.__version__))


def normal_evaluation(f, models, calibrations, fold):
    rows, summaries, blocks, strata = [], [], [], []
    common_gate = models["B1"].condition(f)
    for name, model in models.items():
        trace = model.score(f, diagnostic=True)
        score = trace["score"]
        p = calibrations[name].p(score)
        abstain = ~np.isfinite(score)
        quality = f.quality.to_numpy()
        row = f.copy()
        row["model"], row["fold"] = name, fold
        row["score"], row["p"] = score, p
        row["gate"] = trace["gate"]
        row["original_gate"] = common_gate
        row["dominant"] = np.argmax(np.nan_to_num(trace["components"], nan=-np.inf), axis=1)
        row["component_v0"], row["component_v1"] = trace["components"][:, :2].T
        row["component_i_raw"], row["component_i_residual"] = trace["components"][:, 2:].T
        for j in range(2):
            row[f"conditional_z{j}"] = trace["conditional_z"][:, j]
            row[f"global_z{j}"] = trace["global_z"][:, j]
        for alpha in DESIGN["alpha"]:
            mechanical = p <= alpha
            any_request = mechanical | quality | abstain
            support = 1/(len(calibrations[name].scores)+1) <= alpha
            summary = dict(fold=fold, model=name, alpha=alpha, n=len(f),
                           normal_requests=int(mechanical.sum()),
                           quality_requests=int(quality.sum()), abstentions=int(abstain.sum()),
                           total_requests=int(any_request.sum()),
                           requests_per_100=float(any_request.mean()*100),
                           n_cal=len(calibrations[name].scores), cal_excluded=calibrations[name].excluded,
                           alpha_supported=support, threshold=calibrations[name].threshold(alpha),
                           condition_available=int(trace["gate"].sum()))
            summaries.append(summary)
            grouping = (f.end_m//10*10).astype(int).to_numpy()
            for minute in np.unique(grouping):
                m = grouping == minute
                blocks.append(dict(fold=fold, model=name, alpha=alpha, start_minute=int(minute),
                                   n=int(m.sum()), total_requests=int(any_request[m].sum()),
                                   mechanical_requests=int(mechanical[m].sum())))
            masks = {f"n{lo}_{hi}": f.n.between(lo, hi).to_numpy() for lo, hi in BINS}
            masks.update(condition_available=common_gate, condition_unavailable=~common_gate)
            for group, mask in masks.items():
                strata.append(dict(fold=fold, model=name, alpha=alpha, stratum=group,
                                   n=int(mask.sum()), requests=int(any_request[mask].sum()),
                                   mechanical_requests=int(mechanical[mask].sum())))
        row["mechanical_request"] = p <= .05
        row["any_request"] = (p <= .05) | quality | abstain
        rows.append(row)
    return pd.concat(rows), summaries, blocks, strata


def scenarios():
    for kind, spec in DESIGN["development"].items():
        for target, amp in itertools.product(spec["targets"], spec["amplitudes"]):
            yield spec["family"], target, amp, "", amp in spec["selection"], "development"
    spec = DESIGN["loss"]["L1"]
    for target, amp in itertools.product(spec["targets"], spec["multipliers"]):
        yield spec["family"], target, amp, "", amp in spec["selection"], "loss"
    spec = DESIGN["loss"]["L2"]
    for target, amp, mode in itertools.product(spec["targets"], spec["amplitudes"], spec["current_modes"]):
        yield spec["family"], target, amp, mode, True, "loss"


def synthetic_evaluation(records, f, fit_features, models, calibrations, fold):
    generator = Generator(fit_features, fold)
    gate = generator.model.condition(f)
    scales = {j: generator.scales(f, f"v{j}_rms" if j < 2 else "i_residual") for j in range(3)}
    baseline = {name: calibrations[name].p(m.score(f)) <= .05 for name, m in models.items()}
    rows, checks = [], []
    for family, target, amplitude, mode, selected, role in scenarios():
        for seed in DESIGN["seeds"]:
            injected, info = zip(*(generator.inject(r, family, target, amplitude, seed, scale, mode)
                                   for r, scale in zip(records, scales[target])))
            sf = features(injected)
            valid = np.array([v["valid"] for v in info])
            post_gate = generator.model.condition(sf)
            if family == "compound_unavailable":
                valid &= ~post_gate
            delta = np.array([v["delta_rms"] for v in info])
            checks.append(dict(fold=fold, family=family, target=target, amplitude=amplitude,
                               mode=mode, seed=seed, n=len(f), valid=int(valid.sum()),
                               unsupported=int((~valid).sum()), positive_energy=int((delta > 0).sum()),
                               post_gate=int(post_gate.sum()), pre_gate=int(gate.sum()),
                               min_delta_rms=float(delta.min()), max_delta_rms=float(delta.max())))
            for name, model in models.items():
                score = model.score(sf)
                p = calibrations[name].p(score)
                mechanical = p <= .05
                quality = sf.quality.to_numpy() | ~np.isfinite(score)
                rows.append(pd.DataFrame(dict(
                    fold=fold, model=name, parent=f.parent.to_numpy(), n=f.n.to_numpy(),
                    family=family, target=target, amplitude=amplitude, mode=mode, seed=seed,
                    selection=selected, role=role, original_gate=gate, post_gate=post_gate,
                    valid=valid, detected=mechanical & valid,
                    any_detected=(mechanical | quality) & valid,
                    new_detected=mechanical & ~baseline[name] & valid,
                    original_request=baseline[name], quality=quality)))
    return pd.concat(rows, ignore_index=True), checks


def summarize_synthetic(synthetic):
    keys = ["fold", "model", "family", "target", "amplitude", "mode", "seed", "original_gate"]
    grouped = synthetic.groupby(keys, dropna=False)
    out = grouped.agg(parents=("parent", "nunique"), valid=("valid", "sum"),
                      detections=("detected", "sum"), any_detections=("any_detected", "sum"),
                      new_detections=("new_detected", "sum"), original_requests=("original_request", "sum"),
                      quality_requests=("quality", "sum"), post_gate=("post_gate", "sum")).reset_index()
    out["pod"] = out.detections/out.parents
    out["pod_supported_only"] = out.detections/out.valid.replace(0, np.nan)
    out["new_request_fraction"] = out.new_detections/out.parents
    return out


def selection_tables(synthetic, summaries, timeblocks):
    dev = synthetic.loc[synthetic.role.eq("development") & synthetic.selection]
    # Equal amplitudes, then targets, then seeds within each real parent.
    parent = dev.groupby(["fold", "model", "family", "parent", "seed", "target"]).detected.mean()
    parent = parent.groupby(["fold", "model", "family", "parent", "seed"]).mean()
    parent = parent.groupby(["fold", "model", "family", "parent"]).mean().rename("pod").reset_index()
    families = parent.groupby(["model", "family"]).agg(pod=("pod", "mean"), parents=("parent", "size")).reset_index()
    fold_families = parent.groupby(["fold", "model", "family"]).pod.mean().reset_index()
    nsum = pd.DataFrame(summaries).query("alpha == 0.05")
    blocks = pd.DataFrame(timeblocks).query("alpha == 0.05")
    loss = synthetic.loc[synthetic.role.eq("loss") & synthetic.selection]
    cell = ["fold", "model", "family", "target", "amplitude", "mode", "original_gate"]
    loss_seed = loss.groupby(cell+["seed"], dropna=False).agg(
        pod=("detected", "mean"), parents=("parent", "nunique"), supported_parents=("valid", "sum")).reset_index()
    loss_mean = loss_seed.groupby(cell, dropna=False).agg(
        pod=("pod", "mean"), parents=("parents", "min"), supported_parents=("supported_parents", "min")).reset_index()
    loss_mean["seed"] = "mean"
    loss_seed["seed"] = loss_seed.seed.astype(str)
    loss_all = pd.concat([loss_seed, loss_mean], ignore_index=True)
    join = [k for k in cell if k != "model"]+["seed"]
    ref = loss_all.loc[loss_all.model.eq("B1"), join+["pod"]].rename(columns={"pod": "b1_pod"})
    loss_all = loss_all.merge(ref, on=join, validate="many_to_one")
    loss_all["gain_pp"] = 100*(loss_all.pod-loss_all.b1_pod)
    loss_all["determinate"] = (loss_all.parents >= 20) & (loss_all.supported_parents >= 20)
    baseline_total = int(nsum.loc[nsum.model.eq("B1"), "total_requests"].sum())
    baseline_blocks = blocks.loc[blocks.model.eq("B1")].set_index(["fold", "start_minute"]).total_requests
    baseline_folds = nsum.loc[nsum.model.eq("B1")].set_index("fold").total_requests
    decisions = []
    family_delta = families.merge(families.loc[families.model.eq("B1"), ["family", "pod"]]
                                 .rename(columns={"pod": "b1_pod"}), on="family", validate="many_to_one")
    family_delta["gain_pp"] = 100*(family_delta.pod-family_delta.b1_pod)
    fold_delta = fold_families.merge(fold_families.loc[fold_families.model.eq("B1"), ["fold", "family", "pod"]]
                                    .rename(columns={"pod": "b1_pod"}), on=["fold", "family"], validate="many_to_one")
    fold_delta["gain_pp"] = 100*(fold_delta.pod-fold_delta.b1_pod)
    for name in nsum.model.unique():
        total = int(nsum.loc[nsum.model.eq(name), "total_requests"].sum())
        block_diff = blocks.loc[blocks.model.eq(name)].set_index(["fold", "start_minute"]).total_requests-baseline_blocks
        fold_diff = nsum.loc[nsum.model.eq(name)].set_index("fold").total_requests-baseline_folds
        effects = family_delta.loc[family_delta.model.eq(name)]
        improved = effects.loc[effects.gain_pp.ge(10-1e-10), "family"].tolist()
        consistent = [family for family in improved if
                      fold_delta.loc[fold_delta.model.eq(name) & fold_delta.family.eq(family), "gain_pp"].ge(-1e-10).all()]
        loss_cells = loss_all.loc[loss_all.model.eq(name)]
        failed = loss_cells.loc[loss_cells.determinate & loss_cells.gain_pp.lt(-5-1e-10)]
        unknown = loss_cells.loc[~loss_cells.determinate]
        cap = bool(block_diff.le(1).all())
        path_a = baseline_total-total >= 3 and cap and bool(fold_diff.le(0).all())
        path_b = len(consistent) >= 2 and cap
        passed = bool((path_a or path_b) and len(failed) == 0 and len(unknown) == 0 and name != "B1")
        decisions.append(dict(model=name, total_normal_requests=total, b1_requests=baseline_total,
                              normal_request_delta=total-baseline_total,
                              worst_ten_minute_increase=int(block_diff.max()),
                              path_a=path_a, path_b=path_b, improved_families=consistent,
                              minimum_family_pod=float(effects.pod.min()),
                              loss_failing_cells=len(failed), loss_indeterminate_cells=len(unknown),
                              worst_loss_gain_pp=float(loss_cells.gain_pp.min()), eligible=passed))
    eligible = sorted([r for r in decisions if r["eligible"]],
                      key=lambda r: (r["total_normal_requests"], -r["minimum_family_pod"], r["model"]))
    # Lexical tie cannot silently stand in for registered complexity/cost tie-break.
    tie = len(eligible) > 1 and (eligible[0]["total_normal_requests"], eligible[0]["minimum_family_pod"]) == (
        eligible[1]["total_normal_requests"], eligible[1]["minimum_family_pod"])
    selected = None if tie else (eligible[0]["model"] if eligible else "B1")
    return dict(selected=selected, unresolved_complexity_tie=tie, candidates=decisions,
                interpretation="Development screening, not independent generalization evidence",
                fallback="B1 experimental comparator if no new candidate qualifies; never v2 restoration"), family_delta, fold_delta, loss_all


def run_development():
    start = time.perf_counter()
    meta = manifest("registered_development")
    records, contract = load_records()
    normals, synthetics, summary, blocks, strata, injection_checks = [], [], [], [], [], []
    parameters, correlations = {}, []
    for fold in ["P0", "P1"]:
        roles = split_records(records, fold)
        fit, cal, evaluation = [features(roles[r]) for r in ["fit", "cal", "evaluation"]]
        models, calibrations = fit_suite(fit, cal)
        parameters[fold] = {name: model.parameters() for name, model in models.items()}
        nr, ns, nb, nt = normal_evaluation(evaluation, models, calibrations, fold)
        normals.append(nr); summary.extend(ns); blocks.extend(nb); strata.extend(nt)
        model = models["C1d1"]
        mask = model.condition(fit)
        for j in range(2):
            from core import robust
            y = model.pre.logs(fit.loc[mask], f"v{j}_rms")
            residual = y-model.expected_log_rms(fit.loc[mask], j)
            correlations.append(dict(fold=fold, channel=j, n=int(mask.sum()),
                fit_log_correlation=float(np.corrcoef(np.log(fit.loc[mask, "amplitude"]), y)[0,1]),
                residual_to_global_MAD_same_parents=float(robust(residual)[1]/robust(y)[1])))
        synthetic, checks = synthetic_evaluation(roles["evaluation"], evaluation, fit, models, calibrations, fold)
        synthetics.append(synthetic); injection_checks.extend(checks)
        print(f"{fold}: fit/cal/eval={len(fit)}/{len(cal)}/{len(evaluation)}, scenarios scored", flush=True)
    synthetic = pd.concat(synthetics, ignore_index=True)
    out = HERE / "evidence/v1"
    out.mkdir(parents=True, exist_ok=True)
    pd.concat(normals).to_csv(HERE / "cache/v1_normal_predictions.csv.gz", index=False)
    synthetic.to_csv(HERE / "cache/v1_synthetic_predictions.csv.gz", index=False)
    pd.DataFrame(summary).to_csv(out / "normal_summary.csv", index=False)
    pd.DataFrame(blocks).to_csv(out / "normal_timeblocks.csv", index=False)
    pd.DataFrame(strata).to_csv(out / "normal_strata.csv", index=False)
    pd.DataFrame(injection_checks).to_csv(out / "injection_checks.csv", index=False)
    pd.DataFrame(correlations).to_csv(out / "fit_associations.csv", index=False)
    summarize_synthetic(synthetic).to_csv(out / "synthetic_curves.csv", index=False)
    decision, family, fold_family, loss = selection_tables(synthetic, summary, blocks)
    save_json(out / "selection.json", decision)
    family.to_csv(out / "development_family_pod.csv", index=False)
    fold_family.to_csv(out / "development_fold_pod.csv", index=False)
    loss.to_csv(out / "loss_cells.csv", index=False)
    save_json(out / "model_parameters.json", parameters)
    meta.update(data_contract=contract, completed_utc=datetime.now(timezone.utc).isoformat(),
                elapsed_s=time.perf_counter()-start, synthetic_score_rows=len(synthetic),
                selection_sha256=sha(out / "selection.json"))
    save_json(out / "run_manifest.json", meta)
    print(pd.DataFrame(summary).query("alpha == 0.05")[["fold", "model", "total_requests"]].to_string(index=False))
    print(decision)


def run_audit():
    import json
    selected_path = HERE / "evidence/v1/selection.json"
    if not selected_path.exists():
        raise ValueError("Development selection must be recorded first")
    meta = manifest("retrospective_audit")
    meta["selection_before_audit"] = json.loads(selected_path.read_text())
    meta["selection_sha256"] = sha(selected_path)
    normal, _ = load_records()
    abnormal, abnormal_contract = load_records("abnormal")
    all_rows, summaries, blocks, strata, positives = [], [], [], [], []
    for fold in ["P0", "P1", "P2"]:
        roles = split_records(normal, fold)
        fit, cal, evaluation = [features(roles[r]) for r in ["fit", "cal", "evaluation"]]
        models, calibrations = fit_suite(fit, cal)
        if fold == "P2":
            nr, ns, nb, nt = normal_evaluation(evaluation, models, calibrations, fold)
            all_rows.append(nr); summaries.extend(ns); blocks.extend(nb); strata.extend(nt)
        af = features(abnormal)
        for name, model in models.items():
            scores = model.score(af)
            p = calibrations[name].p(scores)
            mechanical = p <= .05
            gate = model.condition(af)
            positives.append(dict(fold=fold, model=name, n=len(af), episodes=1,
                                  mechanical_hits=int(mechanical.sum()),
                                  any_hits=int((mechanical | af.quality.to_numpy() | ~np.isfinite(scores)).sum()),
                                  condition_available=int(gate.sum()), n_ge20=int(af.n.ge(20).sum()),
                                  ge20_condition_available=int((gate & af.n.ge(20).to_numpy()).sum())))
    out = HERE / "evidence/v1"
    pd.concat(all_rows).to_csv(HERE / "cache/v1_audit_predictions.csv.gz", index=False)
    pd.DataFrame(summaries).to_csv(out / "audit_normal_summary.csv", index=False)
    pd.DataFrame(blocks).to_csv(out / "audit_timeblocks.csv", index=False)
    pd.DataFrame(strata).to_csv(out / "audit_strata.csv", index=False)
    pd.DataFrame(positives).to_csv(out / "provided_abnormal.csv", index=False)
    meta.update(abnormal_contract=abnormal_contract, completed_utc=datetime.now(timezone.utc).isoformat())
    save_json(out / "audit_manifest.json", meta)
    print(pd.DataFrame(summaries).query("alpha == 0.05")[["fold", "model", "total_requests"]].to_string(index=False))
    print(pd.DataFrame(positives).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["development", "audit"])
    args = parser.parse_args()
    (HERE / "cache").mkdir(exist_ok=True)
    run_development() if args.mode == "development" else run_audit()
