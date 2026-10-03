"""E2/E3: fixed K1 calibration and all registered parent-controlled crops."""
from __future__ import annotations
from dataclasses import replace
import pickle
import time
from scipy.spatial.distance import cdist

from common import (HERE, CONTRACT, core, legacy_run, load_press, np, pd, save, csv,
                    rank, rng_for, sha, now)


class ParentKNN:
    def __init__(self, fit, children=None):
        self.pre = core.Preprocessing().fit(fit)
        reference = fit if children is None or len(children) == 0 else pd.concat([fit, children], ignore_index=True)
        order = np.argsort(reference.parent_key.to_numpy(), kind="stable")
        keys = reference.parent_key.to_numpy()[order]
        self.parents, self.starts = np.unique(keys, return_index=True)
        self.reference = self.pre.vector(reference)[order]

    def score(self, f):
        distances = cdist(self.pre.vector(f), self.reference)
        distances = np.minimum.reduceat(distances, self.starts, axis=1)
        distances[f.parent_key.to_numpy()[:, None] == self.parents[None, :]] = np.inf
        if len(self.parents) < 5:
            return np.full(len(f), np.nan)
        score = np.partition(distances, 4, axis=1)[:, :5].mean(axis=1)
        return np.where(np.isfinite(score), score, np.nan)


class Candidate:
    def __init__(self, name, model, cal, baseline=None, conditional=None):
        self.name, self.model = name, model
        self.reference = model.score(cal)
        self.reference = np.sort(self.reference[np.isfinite(self.reference)])
        self.baseline, self.conditional = baseline, conditional
        if name == "K1":
            gate = self.gate(cal)
            self.conditional_reference = conditional.score(cal)[gate]
            self.conditional_reference = np.sort(self.conditional_reference[np.isfinite(self.conditional_reference)])

    def gate(self, f):
        if self.name != "K1":
            return self.model.condition(f) if hasattr(self.model, "condition") else np.zeros(len(f), bool)
        rz = np.column_stack([self.conditional.conditional_z(f, j) for j in range(2)])
        return (self.conditional.condition(f) & np.isfinite(rz).all(axis=1)
                & np.isfinite(self.baseline.score(f)) & np.isfinite(self.conditional.score(f)))

    def raw_score(self, f):
        if self.name == "K1":
            return np.where(self.gate(f), self.conditional.score(f), self.baseline.score(f))
        return self.model.score(f)

    def predict(self, f, alpha=.05):
        s = self.model.score(f)
        p, supported = rank(s, self.reference, alpha)
        gate = self.gate(f)
        route = np.full(len(f), "pooled_reference", dtype=object)
        ncal = np.full(len(f), len(self.reference))
        if self.name == "K1":
            route[:] = "baseline_reference"
            conditional_supported = len(self.conditional_reference) >= max(39, int(np.ceil(1/alpha))-1)
            chosen = gate & conditional_supported & supported
            c = self.conditional.score(f)
            cp, _ = rank(c, self.conditional_reference, alpha)
            p[chosen], s[chosen] = cp[chosen], c[chosen]
            route[chosen], ncal[chosen] = "conditional_reference", len(self.conditional_reference)
        quality = f.quality.to_numpy() | ~supported
        return dict(score=s, p=p, gate=gate, route=route, n_cal=ncal, supported=supported,
                    bit=p <= alpha, quality=quality, any_request=(p <= alpha) | quality)


def crop_children(records, fold, ratio_value, seed):
    eligible = [r for r in records if any(k < len(r.x) for k in [20, 30, 40])]
    count = int(np.floor(ratio_value*len(records)))
    if not eligible:
        return [], [], dict(target=count, generated=0, failed=count, eligible_parents=0)
    allocation_rng = rng_for(["normal_crop", fold, "allocation", seed])
    order = allocation_rng.permutation(len(eligible))
    allocation = np.full(len(eligible), count//len(eligible))
    allocation[order[:count % len(eligible)]] += 1
    children, lineage = [], []
    failed = 0
    for r, amount in zip(eligible, allocation):
        key = f"{r.source_namespace}:{r.parent}"
        rng = rng_for(["normal_crop", fold, key, seed])
        available = {length:list(range(len(r.x)-length+1)) for length in [20, 30, 40] if length < len(r.x)}
        for child_index in range(int(amount)):
            lengths = [length for length, starts in available.items() if starts]
            if not lengths:
                failed += 1
                continue
            length = int(rng.choice(lengths))
            start = int(rng.choice(available[length]))
            available[length].remove(start)
            # Parent ID is retained for exclusion; child time is its own crop time.
            child = replace(r, x=r.x[start:start+length].copy(), start_m=r.start_m+start*.1/60,
                            end_m=r.start_m+(start+length-1)*.1/60,
                            decision_m=r.start_m+(start+length-1)*.1/60+.5/60,
                            source_rows=())
            children.append(child)
            lineage.append(dict(fold=fold, ratio=ratio_value, seed=seed, parent_key=key,
                                child_id=f"{key}:s{seed}:{child_index}", start=start, length=length,
                                source_sample_positions=list(range(start, start+length))))
    return children, lineage, dict(target=count, generated=len(children), failed=failed, eligible_parents=len(eligible))


def fit_candidates(records, cal, fold, augment=True):
    f = core.features(records)
    b = core.Detector("B1").fit(f)
    c = core.Detector("C1d1").fit(f)
    models = {"B1":Candidate("B1", b, cal), "C1d1":Candidate("C1d1", c, cal),
              "K1":Candidate("K1", b, cal, b, c), "A0":Candidate("A0", ParentKNN(f), cal)}
    lineage, audits = [], []
    if augment:
        by_parent = {f"{r.source_namespace}:{r.parent}": r for r in records}
        for seed in [11, 29, 47]:
            for value, token in [(.5, "05"), (1., "10")]:
                children, links, audit = crop_children(records, fold, value, seed)
                cf = core.features(children) if children else None
                repeats = [by_parent[l["parent_key"]] for l in links]
                rf = core.features(repeats) if repeats else None
                base_vector = models["A0"].model.pre.vector(f)
                child_vector = models["A0"].model.pre.vector(cf) if cf is not None else np.empty((0, base_vector.shape[1]))
                parents = dict(zip(f.parent_key, range(len(f))))
                same = sum(np.array_equal(child_vector[i], base_vector[parents[l["parent_key"]]]) for i, l in enumerate(links))
                audits.append(dict(fold=fold, ratio=value, seed=seed, **audit,
                                   feature_identical_children=same, feature_changed_children=len(links)-same,
                                   distinct_used_parents=len({l["parent_key"] for l in links})))
                for prefix, feature in [("A1", rf), ("A2", cf)]:
                    name = f"{prefix}_r{token}_s{seed}"
                    models[name] = Candidate(name, ParentKNN(f, feature), cal)
                lineage.extend(links)
    return models, lineage, audits


def normal_evaluation(f, models, fold):
    rows, summary, blocks = [], [], []
    original_gate = models["B1"].model.condition(f)
    for name, model in models.items():
        for alpha in [.05, .03, .01]:
            pred = model.predict(f, alpha)
            summary.append(dict(fold=fold, model=name, alpha=alpha, n=len(f),
                                normal_requests=int(pred["bit"].sum()), quality_requests=int(pred["quality"].sum()),
                                total_requests=int(pred["any_request"].sum()), unsupported=int((~pred["supported"]).sum()),
                                baseline_cal=len(model.reference), conditional_cal=len(model.conditional_reference) if name == "K1" else None,
                                conditional_route=int((pred["route"] == "conditional_reference").sum())))
            for minute in sorted(set((f.end_m//10*10).astype(int))):
                mask = (f.end_m//10*10).astype(int).eq(minute).to_numpy()
                blocks.append(dict(fold=fold, model=name, alpha=alpha, start_minute=minute,
                                   n=int(mask.sum()), total_requests=int(pred["any_request"][mask].sum())))
            r = f.copy()
            for key, value in pred.items():
                r[key] = value
            r["model"], r["fold"], r["alpha"], r["original_gate"] = name, fold, alpha, original_gate
            rows.append(r)
    return pd.concat(rows, ignore_index=True), summary, blocks


def synthetic_evaluation(records, fit, models, fold):
    f = core.features(records)
    generator = core.Generator(fit, fold)
    gate = generator.model.condition(f)
    scales = {j:generator.scales(f, f"v{j}_rms" if j < 2 else "i_residual") for j in range(3)}
    original = {name:model.predict(f) for name, model in models.items()}
    result, generation, identity_checks = [], [], 0
    for family, target, amplitude, mode, selected, role in legacy_run.scenarios():
        for seed in [11, 29, 47]:
            changed, info = zip(*(generator.inject(r, family, target, amplitude, seed, scale, mode)
                                   for r, scale in zip(records, scales[target])))
            feature = core.features(changed)
            valid = np.array([i["valid"] for i in info])
            post_gate = generator.model.condition(feature)
            if family == "compound_unavailable":
                valid &= ~post_gate
            generation.append(dict(fold=fold, family=family, target=target, amplitude=amplitude, mode=mode,
                                   seed=seed, parents=len(f), supported=int(valid.sum()), failed=int((~valid).sum()),
                                   max_delta_rms=max(i["delta_rms"] for i in info)))
            base_knn = models["A0"].predict(feature)
            base_b1 = models["B1"].predict(feature)
            for name, model in models.items():
                pred = base_knn if name == "A0" else base_b1 if name == "B1" else model.predict(feature)
                if name.startswith("A1"):
                    for key in ["score", "p", "bit", "any_request"]:
                        np.testing.assert_array_equal(pred[key], base_knn[key])
                    identity_checks += len(f)
                if name == "K1":
                    mask = ~pred["gate"]
                    for key in ["score", "p", "bit"]:
                        np.testing.assert_array_equal(pred[key][mask], base_b1[key][mask])
                result.append(pd.DataFrame(dict(fold=fold, model=name, parent=f.parent.to_numpy(), n=f.n.to_numpy(),
                    family=family, target=target, amplitude=amplitude, mode=mode, seed=seed,
                    selection=selected, role=role, original_gate=gate, post_gate=post_gate, valid=valid,
                    detected=pred["bit"] & valid, any_detected=pred["any_request"] & valid,
                    new_detected=pred["bit"] & ~original[name]["bit"] & valid,
                    original_request=original[name]["bit"], quality=pred["quality"],
                    raw_bit=pred["bit"], supported=pred["supported"])))
    return pd.concat(result, ignore_index=True), generation, identity_checks


def select(synthetic, summary, blocks, states):
    selection, families, folds, loss = legacy_run.selection_tables(synthetic, summary, blocks)
    # The identical repetitions are controls, never candidates. Each A2 must also pass against A0.
    keep = ~synthetic.model.isin(["B1", "C1d1", "K1"])
    against_a0 = synthetic.loc[keep].copy()
    against_a0["model"] = against_a0.model.replace({"A0":"B1"})
    summary0 = pd.DataFrame(summary).loc[lambda d:~d.model.isin(["B1", "C1d1", "K1"])].copy()
    summary0["model"] = summary0.model.replace({"A0":"B1"})
    blocks0 = pd.DataFrame(blocks).loc[lambda d:~d.model.isin(["B1", "C1d1", "K1"])].copy()
    blocks0["model"] = blocks0.model.replace({"A0":"B1"})
    aug_selection, aug_families, _, aug_loss = legacy_run.selection_tables(against_a0, summary0, blocks0)
    decisions = {r["model"]:r for r in selection["candidates"]}
    aug_decisions = {r["model"]:r for r in aug_selection["candidates"]}
    choices = []
    k1_supported = all(len(states[fold]["K1"].conditional_reference) >= 39 for fold in ["P0", "P1"])
    choices.append(dict(candidate="K1", eligible=decisions["K1"]["eligible"] and k1_supported,
                        calibration_supported_both_folds=k1_supported, normal_requests=decisions["K1"]["total_normal_requests"],
                        min_pod=decisions["K1"]["minimum_family_pod"], complexity=2))
    for ratio_token in ["05", "10"]:
        names = [f"A2_r{ratio_token}_s{seed}" for seed in [11, 29, 47]]
        passed = all(decisions[n]["eligible"] and aug_decisions[n]["eligible"] for n in names)
        min_pod = families.loc[families.model.isin(names)].groupby("family").pod.mean().min()
        choices.append(dict(candidate=f"A2_r{ratio_token}", eligible=passed,
                            normal_requests=sum(decisions[n]["total_normal_requests"] for n in names)/3,
                            normal_requests_integer_sum=sum(decisions[n]["total_normal_requests"] for n in names),
                            min_pod=float(min_pod), complexity=3,
                            per_seed_pass={n:decisions[n]["eligible"] and aug_decisions[n]["eligible"] for n in names}))
    eligible = [r for r in choices if r["eligible"]]
    eligible.sort(key=lambda r:(r["normal_requests"], -r["min_pod"], r["complexity"], r["candidate"]))
    unresolved = len(eligible) > 1 and (eligible[0]["normal_requests"], eligible[0]["min_pod"], eligible[0]["complexity"]) == (eligible[1]["normal_requests"], eligible[1]["min_pod"], eligible[1]["complexity"])
    if unresolved:
        raise ValueError("Cost tie-break required before selection")
    selected = eligible[0]["candidate"] if eligible else None
    return dict(selected_candidate=selected, comparison_reference="B1", improvement_established=selected is not None,
                candidates=choices, per_model_against_B1=selection["candidates"],
                per_model_against_A0=aug_selection["candidates"], deployment_seed=11,
                probability_not_used_for_selection=True, selected_utc=now()), families, folds, loss, aug_families, aug_loss


def development(output):
    started = time.perf_counter()
    normal, input_audit = load_press()
    normals, synthetic, summary, blocks, lineage, crop_audit, generation = [], [], [], [], [], [], []
    states, record_map = {}, []
    checks = 0
    for fold in ["P0", "P1"]:
        roles = core.split_records(normal, fold)
        fit, cal, evaluation = [core.features(roles[k]) for k in ["fit", "cal", "evaluation"]]
        models, links, audits = fit_candidates(roles["fit"], cal, fold)
        states[fold] = models
        nr, ns, nb = normal_evaluation(evaluation, models, fold)
        sy, ge, checked = synthetic_evaluation(roles["evaluation"], fit, models, fold)
        normals.append(nr); synthetic.append(sy); summary.extend(ns); blocks.extend(nb)
        lineage.extend(links); crop_audit.extend(audits); generation.extend(ge); checks += checked
        for role, records in roles.items():
            record_map.extend(dict(fold=fold, role=role, parent=r.parent, source_namespace=r.source_namespace,
                                   source_rows=r.source_rows, start_m=r.start_m, end_m=r.end_m,
                                   decision_m=r.decision_m) for r in records)
        print(f"E2/E3 {fold}: {len(models)} models, {len(sy)} paired synthetic rows", flush=True)
    sy = pd.concat(synthetic, ignore_index=True)
    decision, families, folds, loss, aug_families, aug_loss = select(sy, summary, blocks, states)
    csv(output / "press_normal_summary.csv", summary)
    csv(output / "press_normal_timeblocks.csv", blocks)
    csv(output / "press_family_pod.csv", families)
    csv(output / "press_fold_family_pod.csv", folds)
    csv(output / "press_loss_cells.csv", loss)
    csv(output / "augmentation_family_gain.csv", aug_families)
    csv(output / "augmentation_loss_cells.csv", aug_loss)
    csv(output / "augmentation_generation.csv", crop_audit)
    csv(output / "development_generation.csv", generation)
    csv(output / "development_curves.csv", legacy_run.summarize_synthetic(sy))
    csv(output.parent / "cache/press_development_predictions.csv.gz", pd.concat(normals, ignore_index=True))
    csv(output.parent / "cache/press_development_synthetic.csv.gz", sy)
    save(output.parent / "cache/augmentation_lineage.json", lineage)
    save(output.parent / "cache/press_development_record_map.json", record_map)
    save(output / "selection.json", decision)
    artifacts = output.parent / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "press_development.pkl").write_bytes(pickle.dumps(states, protocol=5))
    save(output / "press_development_run.json", dict(input=input_audit, completed_utc=now(),
        runtime_s=time.perf_counter()-started, A1_identity_rows=checks, synthetic_rows=len(sy),
        K1_conditional_cal={fold:len(s["K1"].conditional_reference) for fold, s in states.items()},
        source_rows_preserved=True, P2_used_for_selection=False, provided_abnormal_used_for_selection=False))
    return decision, states
