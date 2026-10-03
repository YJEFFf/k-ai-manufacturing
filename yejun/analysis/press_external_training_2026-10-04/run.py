"""Paired target-only versus external-training comparisons, fixed before scoring."""
from __future__ import annotations

import argparse
import gzip
import json
import platform
import time
from datetime import datetime, timezone

from basis import (HERE, CFG, core, guard, np, pd, sha, save, array_sha, load_target,
                   target_vectors, base_fit, record_max, rank_p, metric, select_pool, Neighbors)

import scipy
import sklearn
import torch
from torch import nn

torch.set_num_threads(1)
torch.set_num_interop_threads(1)
torch.use_deterministic_algorithms(True)


def autoencoder(seed):
    torch.manual_seed(seed)
    widths = CFG["methods"]["pretrained_ae"]["architecture"]
    layers = []
    for i, (a, b) in enumerate(zip(widths[:-1], widths[1:])):
        layers.append(nn.Linear(a, b))
        if i < len(widths)-2:
            layers.append(nn.SiLU())
    return nn.Sequential(*layers)


def phase(model, x, steps, seed):
    options = CFG["methods"]["pretrained_ae"]
    data = torch.tensor(x, dtype=torch.float32)
    rng = np.random.default_rng(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=options["learning_rate"])
    used = np.zeros(len(x), dtype=bool)
    for _ in range(steps):
        ix = rng.integers(len(x), size=options["batch_size"])
        used[ix] = True
        batch = data[ix]
        optimizer.zero_grad(set_to_none=True)
        loss = ((model(batch)-batch)**2).mean()
        loss.backward()
        optimizer.step()
    return dict(steps=steps, available_examples=len(x), consumed_distinct_examples=int(used.sum()), final_batch_loss=float(loss.detach()))


def ae_scores(model, x):
    with torch.no_grad():
        x = torch.tensor(x, dtype=torch.float32)
        return ((model(x)-x)**2).mean(dim=1).numpy().astype(float)


def source_sample(pools, source, desired, seed, normal_only):
    names = sorted(pools) if source == "all_four" else [source]
    vectors, ids, parts = [], [], []
    for j, name in enumerate(names):
        count = desired // len(names) + int(j < desired % len(names))
        ix = select_pool(pools[name], count, seed, normal_only)
        p = pools[name]
        vectors.append(p["x"][ix]); ids.extend(p["ids"][ix].tolist())
        parts.append(dict(source=name, requested=count, selected=len(ix),
                          available=int(p["normal"].sum()) if normal_only else len(p["x"]),
                          groups=len(set(p["groups"][ix])), ids_sha256=array_sha(p["ids"][ix])))
    return np.concatenate(vectors), np.asarray(ids), parts


def evaluate_arm(identity, raw, roles, base, writer, metrics, arms):
    fit_raw = raw["fit"]
    tail = guard.ExpTail(fit_raw)
    if not tail.ok:
        raise ValueError("No fit-only tail scale; do not silently change experiment")
    views = {
        "vibration_only": {r: np.where(np.isfinite(v), v, -1.) for r, v in raw.items()},
        "integrated": {r: np.fmax(base[r], tail(v)) for r, v in raw.items()}
    }
    audit = dict(identity, tail_ok=tail.ok, fit_score_sha256=array_sha(fit_raw),
                 calibration_labels="real target normal only", evaluation_hashes={})
    alphas = [CFG["metrics"]["primary_alpha"]] + CFG["metrics"]["secondary_alpha"]
    for view, scores in views.items():
        ps = rank_p(scores["cal"], scores["evaluation"])
        y = np.array([r.source_namespace == "abnormal" for r in roles["evaluation"]], dtype=int)
        supported = np.isfinite(raw["evaluation"]) if view == "vibration_only" else np.ones(len(y), bool)
        audit["evaluation_hashes"][view] = array_sha(scores["evaluation"])
        for alpha in alphas:
            pred = (ps <= alpha) & supported
            metrics.append(dict(identity, view=view, alpha=alpha,
                                **metric(y, pred, scores["evaluation"]),
                                normal_records=int((y == 0).sum()), abnormal_records=int(y.sum()),
                                supported_records=int(supported.sum()), total_records=len(y)))
        for role in ("cal", "evaluation"):
            for i, r in enumerate(roles[role]):
                row = dict(identity, view=view, role=role, parent_key=f"{r.source_namespace}:{r.parent}",
                           label=int(r.source_namespace == "abnormal"), n=len(r.x),
                           score=float(scores[role][i]), supported=bool(np.isfinite(raw[role][i])) if view == "vibration_only" else True)
                writer.write(json.dumps(row, allow_nan=False) + "\n")
    arms.append(audit)


def run(output):
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=True)
    artifacts = HERE / "artifacts" / output.name
    artifacts.mkdir(parents=True, exist_ok=True)
    source_audit = json.loads((HERE / "evidence/source_audit.json").read_text())
    if source_audit["protocol_sha256"] != sha(HERE / "protocol.json") or source_audit["representation_code_sha256"] != sha(HERE / "basis.py"):
        raise ValueError("Source cache is stale: rerun data.py")
    pools = {name: dict(np.load(HERE / "cache" / f"{name}.npz", allow_pickle=False)) for name in CFG["sources"] if name != "all_four"}
    for name, p in pools.items():
        if (array_sha(p["x"]) != source_audit["sources"][name]["representation_sha256"]
                or sha(HERE / "cache" / f"{name}.npz") != source_audit["sources"][name]["cache_sha256"]):
            raise ValueError("Source feature cache hash mismatch")
    inputs, target_audit = load_target()
    freeze = dict(created_utc=datetime.now(timezone.utc).isoformat(), protocol_sha256=sha(HERE / "protocol.json"),
                  code={name: sha(HERE/name) for name in ["basis.py", "data.py", "run.py"]},
                  source_audit_sha256=sha(HERE / "evidence/source_audit.json"), target_audit=target_audit,
                  environment=dict(python=platform.python_version(), platform=platform.platform(),
                                   numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                                   sklearn=sklearn.__version__, torch=torch.__version__, device="cpu", threads=1),
                  purpose="external data used for TRAINING, target data only for calibration/evaluation")
    save(output / "freeze.json", freeze)
    rows, arms, ledger, fold_audit = [], [], [], {}
    with gzip.open(output / "predictions.jsonl.gz", "wt", encoding="utf-8") as writer:
        for fold in CFG["folds"]:
            roles = core.split_records(inputs["normal"], fold)
            roles["evaluation"] = roles["evaluation"] + inputs["abnormal"]
            fit_ids, cal_ids, eval_ids = [{f"{r.source_namespace}:{r.parent}" for r in roles[role]} for role in ("fit", "cal", "evaluation")]
            assert not (fit_ids & cal_ids or fit_ids & eval_ids or cal_ids & eval_ids)
            vec = {role: target_vectors(recs) for role, recs in roles.items()}
            xfit, fit_mapping, vector_ids = vec["fit"]
            fold_audit[fold] = dict(role_counts={role: len(r) for role, r in roles.items()},
                                    fit_ids=sorted(fit_ids), cal_ids=sorted(cal_ids), evaluation_ids=sorted(eval_ids),
                                    fit_channel_examples=len(xfit), supported_records={role: len(set(v[1])) for role, v in vec.items()})
            base, model = base_fit(roles)
            save(artifacts / f"{fold}_fixed_base.json", model.state)
            # Fixed three-sensor reference: no transferred branch.
            y = np.array([r.source_namespace == "abnormal" for r in roles["evaluation"]], dtype=int)
            p = rank_p(base["cal"], base["evaluation"])
            for alpha in [0.05, 0.01, 0.03]:
                rows.append(dict(fold=fold, method="fixed_base", source="target_only", ratio=0, seed=0,
                                 view="integrated", alpha=alpha, **metric(y, p <= alpha, base["evaluation"]),
                                 normal_records=int((y == 0).sum()), abnormal_records=int(y.sum()),
                                 supported_records=len(y), total_records=len(y), external_examples=0))
            for role in ("cal", "evaluation"):
                for i, record in enumerate(roles[role]):
                    writer.write(json.dumps(dict(fold=fold, method="fixed_base", source="target_only", ratio=0, seed=0,
                                                 external_examples=0, view="integrated", role=role,
                                                 parent_key=f"{record.source_namespace}:{record.parent}",
                                                 label=int(record.source_namespace == "abnormal"), n=len(record.x),
                                                 score=float(base[role][i]), supported=True)) + "\n")
            for seed in CFG["seeds"]:
                for method in ("pooled_knn", "pretrained_ae"):
                    designs = [("target_only", 0)] + [(s, ratio) for s in CFG["sources"] for ratio in CFG["external_to_target_channel_example_ratios"]]
                    if method == "pooled_knn":
                        designs += [("target_repeat_control", 4)]
                    else:
                        designs += [("target_scratch_reference", 0)]
                    for source, ratio in designs:
                        identity = dict(fold=fold, method=method, source=source, ratio=ratio, seed=seed)
                        name = f"{fold}_{method}_{source}_{ratio}_{seed}"
                        print(name, flush=True)
                        external = source in CFG["sources"]
                        selected, selected_ids, parts = (np.empty((0, 16)), np.array([], dtype=str), [])
                        if external:
                            selected, selected_ids, parts = source_sample(pools, source, ratio*len(xfit), seed, method == "pooled_knn")
                        identity["external_examples"] = len(selected)
                        training = dict(identity, parts=parts, target_channel_examples=len(xfit))
                        if method == "pooled_knn":
                            if source == "target_repeat_control":
                                reference, ref_ids = np.tile(xfit, (5, 1)), np.tile(vector_ids, 5)
                            else:
                                reference, ref_ids = np.r_[xfit, selected], np.r_[vector_ids, selected_ids]
                            detector = Neighbors(reference, ref_ids)
                            parents = np.array([v.rsplit(":", 1)[0] for v in vector_ids])
                            raw = {role: record_max(detector.score(x, parents if role == "fit" else None), ix, len(roles[role])) for role, (x, ix, _) in vec.items()}
                            np.savez_compressed(artifacts / f"{name}.npz", x=detector.x, ids=detector.ids)
                            reloaded = dict(np.load(artifacts / f"{name}.npz", allow_pickle=False))
                            detector2 = Neighbors(reloaded["x"], reloaded["ids"])
                            assert np.array_equal(detector.score(vec["evaluation"][0]), detector2.score(vec["evaluation"][0]))
                            training.update(reference_examples=len(detector.x), reload_exact=True)
                        else:
                            detector = autoencoder(seed)
                            options = CFG["methods"]["pretrained_ae"]
                            if source != "target_scratch_reference":
                                pretrain = selected if external else xfit
                                training["pretrain"] = phase(detector, pretrain, options["pretrain_steps"], seed+1000)
                            training["finetune"] = phase(detector, xfit, options["finetune_steps"], seed+2000)
                            raw = {role: record_max(ae_scores(detector, x), ix, len(roles[role])) for role, (x, ix, _) in vec.items()}
                            torch.save(detector.state_dict(), artifacts / f"{name}.pt")
                            detector2 = autoencoder(seed)
                            detector2.load_state_dict(torch.load(artifacts / f"{name}.pt", weights_only=True))
                            assert np.array_equal(ae_scores(detector, vec["evaluation"][0]), ae_scores(detector2, vec["evaluation"][0]))
                            training["reload_exact"] = True
                        ledger.append(training)
                        evaluate_arm(identity, raw, roles, base, writer, rows, arms)
    pd.DataFrame(rows).to_csv(output / "metrics.csv", index=False)
    save(output / "training_ledger.json", ledger)
    save(output / "folds.json", fold_audit)
    save(output / "arms.json", arms)
    save(output / "completion.json", dict(complete=True, elapsed_seconds=time.monotonic()-started,
                                          arms=len(arms), metric_rows=len(rows), model_reload_checks=len(ledger),
                                          final_model_selected=False, training_utility_experiment_only=True))
    summarize(output)


def summarize(output):
    m = pd.read_csv(output / "metrics.csv")
    keys = ["fold", "method", "seed", "view", "alpha"]
    controls = m[m.source.eq("target_only") & ~m.method.eq("fixed_base")]
    values = ["f1", "fp", "fn", "tp", "auroc", "ap"]
    paired = m[m.source.isin(CFG["sources"])].merge(controls[keys+values], on=keys, suffixes=("", "_control"), validate="many_to_one")
    for v in values:
        paired[f"delta_{v}"] = paired[v]-paired[f"{v}_control"]
    paired.to_csv(output / "paired_comparisons.csv", index=False)
    primary = paired[paired.alpha.eq(.05)]
    summary = primary.groupby(["method", "source", "ratio", "view"], sort=False).agg(
        comparisons=("f1", "size"), control_f1_mean=("f1_control", "mean"), augmented_f1_mean=("f1", "mean"),
        delta_f1_mean=("delta_f1", "mean"), delta_f1_min=("delta_f1", "min"), delta_f1_max=("delta_f1", "max"),
        delta_fp_mean=("delta_fp", "mean"), delta_fn_mean=("delta_fn", "mean"),
        improved=("delta_f1", lambda x: int((x > 1e-12).sum())), worsened=("delta_f1", lambda x: int((x < -1e-12).sum())),
        external_examples_min=("external_examples", "min"), external_examples_max=("external_examples", "max")
    ).reset_index()
    summary.to_csv(output / "training_utility_summary.csv", index=False)
    repeat = m[m.source.eq("target_repeat_control")].merge(controls[keys+values], on=keys, suffixes=("", "_control"), validate="many_to_one")
    duplicate_exact = all(np.array_equal(repeat[v], repeat[v+"_control"]) for v in values)
    save(output / "controls.json", dict(duplicate_control_metric_rows=len(repeat), duplicate_control_exact=duplicate_exact,
                                        autoencoder_control="same seed, architecture, 300+300 updates and target fine-tuning batches",
                                        all_folds_share_the_same_abnormal_episode=True))
    if not duplicate_exact:
        raise AssertionError("Duplicating training IDs changed kNN results")
    print(summary[summary.view.eq("integrated")].to_string(index=False), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=str, default=str(HERE / "evidence"))
    p.add_argument("--summarize-only", action="store_true")
    args = p.parse_args()
    from pathlib import Path
    output = Path(args.output).resolve()
    summarize(output) if args.summarize_only else run(output)
