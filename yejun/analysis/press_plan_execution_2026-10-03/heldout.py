"""E5: frozen P2 reference audit and registered H1/H2 changes."""
from __future__ import annotations
from dataclasses import replace
import json
import pickle

from common import (HERE, MASTER, LEGACY, CONTRACT, core, np, pd, save, csv, sha, canonical_sha,
                    environment, load_press, now, rng_for, metrics, policy)
from press import fit_candidates
from compare_junyong import common_reference


def code_hashes():
    paths = list(HERE.glob("*.py")) + [LEGACY / "core.py", LEGACY / "run.py"]
    paths += list((HERE.parents[2] / "claude/code/press/pipeline").rglob("*.py"))
    return {str(p.relative_to(HERE.parents[2])):canonical_sha(p) for p in sorted(paths)}


def freeze(output):
    selection = json.loads((output / "selection.json").read_text(encoding="utf-8"))
    normal, _ = load_press()
    roles = core.split_records(normal, "P2")
    chosen = selection["selected_candidate"]
    names = ["B1", "C1d1"]
    if chosen:
        names.append(chosen+"_s11" if chosen.startswith("A2") else chosen)
    names = list(dict.fromkeys(names))
    candidates, lineage, _ = fit_candidates(roles["fit"], core.features(roles["cal"]), "P2", augment=bool(chosen and chosen.startswith("A2")))
    state = dict(models={n:candidates[n] for n in names}, generator=core.Generator(core.features(roles["fit"]), "P2"))
    artifact = output.parent / "artifacts/press_frozen.pkl"
    artifact.write_bytes(pickle.dumps(state, protocol=5))
    paths = [MASTER / n for n in ["protocol.json", "execution_contracts.json", "execution_revision.json",
                                  "evidence/skab_group_reservation.json", "evidence/skab_label_consistency.json"]]
    paths += [output / n for n in ["selection.json", "press_policy_selection.json", "skab_policy_selection.json", "probability_heads.json"]]
    artifacts = [artifact, output.parent / "artifacts/skab.pkl", output.parent / "artifacts/probability.pkl",
                 output.parent / "artifacts/press_development.pkl"]
    inputs = {str(p.relative_to(HERE)):sha(p) for p in sorted((HERE / "data").rglob("*.csv"))}
    frozen = dict(frozen_utc=now(), selected_candidate=chosen, comparison_reference="B1",
                  press_test_models=names, skab_test_models=["G", "C"],
                  additional_user_requested_comparator="Junyong_fixed_w8, same P2 fit/cal/record/time/alpha; never selection",
                  code_sha256=code_hashes(), environment=environment(), input_sha256=inputs,
                  protocol_and_selection_sha256={str(p.relative_to(HERE.parents[2])):canonical_sha(p) for p in paths},
                  artifact_sha256={str(p.relative_to(HERE)):sha(p) for p in artifacts},
                  seed=11, alpha=.05, heldout_generators=CONTRACT["future_injections"],
                  label_event_denominators=CONTRACT["skab"], claim_rules=CONTRACT["selection"],
                  augmentation_lineage_sha256=sha(output.parent / "cache/augmentation_lineage.json"),
                  heldout_lineage=lineage, test_reselection_allowed=False,
                  P2_is_already_explored=True, press_abnormal_independent_episodes=1,
                  external_test_performance_opened=False)
    save(output / "freeze.json", frozen)
    return frozen


def verify_freeze(output):
    path = output / "freeze.json"
    frozen = json.loads(path.read_text(encoding="utf-8"))
    if frozen["code_sha256"] != code_hashes() or frozen["environment"] != environment():
        raise ValueError("Frozen code/environment changed")
    for name, digest in frozen["input_sha256"].items():
        if sha(HERE / name) != digest:
            raise ValueError("Frozen input changed")
    for name, digest in frozen["protocol_and_selection_sha256"].items():
        if canonical_sha(HERE.parents[2] / name) != digest:
            raise ValueError("Frozen protocol or selection changed")
    for name, digest in frozen["artifact_sha256"].items():
        if sha(HERE / name) != digest:
            raise ValueError("Frozen fitted artifact changed")
    return frozen


def tone_frequencies(records):
    frequencies = np.fft.rfftfreq(512)
    mask = (frequencies >= .01) & (frequencies <= .49)
    tones = []
    for target in [0, 1]:
        spectra = []
        for record in records:
            if len(record.x) < 20:
                continue
            x = record.x[:, target]-record.x[:, target].mean()
            power = np.abs(np.fft.rfft(x, n=512)[mask])**2
            if power.sum() > 0 and np.isfinite(power).all():
                spectra.append(power/power.sum())
        tones.append(float(frequencies[mask][np.argmax(np.mean(spectra, axis=0))]) if spectra else None)
    eligible = [f for f in [.1, .25, .4] if all(t is not None and abs(f-t) > .02 for t in tones)]
    return tones, eligible


def off_tone(record, target, frequency, amplitude, seed, scale):
    x = record.x.copy()
    valid = len(x) >= 20
    phase = float(rng_for(["heldout", "P2", f"{record.source_namespace}:{record.parent}", "H1", target,
                           f"{frequency:.2f}", seed]).uniform(0, 2*np.pi))
    if valid and amplitude:
        wave = np.sin(2*np.pi*frequency*np.arange(len(x))+phase)
        wave -= wave.mean()
        norm = np.sqrt(np.mean(wave**2))
        valid = np.isfinite(norm) and norm > 0
        if valid:
            x[:, target] += amplitude*scale*wave/norm
    delta = float(np.sqrt(np.mean((x[:, target]-record.x[:, target])**2)))
    return replace(record, x=x), dict(valid=bool(valid), phase=phase, reference_rms=float(scale), delta_rms=delta)


def phase_change(record, target, delta, floor):
    x = record.x.copy()
    n = len(x)
    original = x[:, target].copy()
    dc = original.mean()
    ac = original-dc
    rms = np.sqrt(np.mean(ac**2))
    ft = np.fft.rfft(ac)
    last = -1 if n % 2 == 0 else None
    rotatable = ft[1:last]
    rot_energy = 2*np.sum(np.abs(rotatable)**2)
    total = np.sum(np.abs(ft)**2 * np.r_[1, np.full(max(0, len(ft)-2), 2), 1 if n % 2 == 0 else 2]) if n > 1 else 0
    valid = n >= 20 and total > 0 and rot_energy > 1e-12*total
    invariance = True
    atol = 1e-12*max(float(rms), float(floor))
    if valid and delta:
        changed = ft.copy()
        changed[1:last] *= np.exp(1j*delta)
        x[:, target] = np.fft.irfft(changed, n=n)+dc
        new_ac = x[:, target]-x[:, target].mean()
        checks = [np.isclose(x[:, target].mean(), dc, rtol=1e-10, atol=atol),
                  np.isclose(np.sqrt(np.mean(new_ac**2)), rms, rtol=1e-10, atol=atol),
                  np.allclose(np.abs(np.fft.rfft(new_ac)), np.abs(ft), rtol=1e-10, atol=atol*n)]
        invariance = bool(all(checks))
        valid = valid and float(np.sqrt(np.mean((x[:, target]-original)**2))) > atol
    return replace(record, x=x), dict(valid=bool(valid), invariant=invariance,
                                     delta_rms=float(np.sqrt(np.mean((x[:, target]-original)**2))))


def evaluate(output):
    frozen = verify_freeze(output)
    state = pickle.loads((output.parent / "artifacts/press_frozen.pkl").read_bytes())
    normal, _ = load_press()
    abnormal, abnormal_audit = load_press("abnormal")
    roles = core.split_records(normal, "P2")
    records = roles["evaluation"]
    f = core.features(records)
    combined_f = core.features(records+abnormal)
    y = np.r_[np.zeros(len(records), int), np.ones(len(abnormal), int)]
    metrics_table, predictions, requests = [], [], []
    for name, model in state["models"].items():
        pred = model.predict(combined_f)
        metrics_table.append(dict(model=name, fold="P2", evaluation_unit="completed record", alpha=.05,
                                  **metrics(y, pred["bit"], pred["score"])))
        result = combined_f.copy()
        for k, value in pred.items():
            result[k] = value
        result["label"], result["model"] = y, name
        predictions.append(result)
        for label, subset in [(0, result.loc[result.label.eq(0)]), (1, result.loc[result.label.eq(1)])]:
            for pname in ["I0", "P23"]:
                pp = policy(subset.decision_m.to_numpy()*60, subset.bit, subset.supported, subset.quality, pname)
                requests.append(dict(model=name, label=label, policy=pname,
                    **{k:pp[k] for k in ["mechanical_starts", "quality_tickets", "total_tickets", "occupancy_s", "threshold_positive", "suppressed"]}))
    metrics_table.append(common_reference(output, "P2"))
    csv(output / "press_common_metrics.csv", metrics_table)
    csv(output / "press_P2_policies.csv", requests)
    csv(output.parent / "cache/press_P2_predictions.csv.gz", pd.concat(predictions, ignore_index=True))
    save(output.parent / "cache/press_P2_record_map.json", [dict(namespace=r.source_namespace, parent=r.parent,
         source_rows=r.source_rows, decision_m=r.decision_m, label=int(r.source_namespace == "abnormal")) for r in records+abnormal])
    tones, frequencies = tone_frequencies(roles["fit"])
    save(output / "heldout_tones.json", dict(fit_tones=tones, eligible_frequencies=frequencies,
         fit_only=True, original_parents=len(records)))
    baselines = {name:model.predict(f) for name, model in state["models"].items()}
    raw_rows = []
    scenarios = [("H1", target, frequency, amplitude, seed) for target in [0, 1] for frequency in frequencies
                  for amplitude in [0., .1, .25, .5, 1.] for seed in [101, 211, 307]]
    scenarios += [("H2", target, 0., delta, 0) for target in [0, 1] for delta in [0., -np.pi/3, -np.pi/6, np.pi/6, np.pi/3]]
    for family, target, frequency, amplitude, seed in scenarios:
        scale = state["generator"].scales(f, f"v{target}_rms")
        transformed = [off_tone(r, target, frequency, amplitude, seed, s) if family == "H1" else
                       phase_change(r, target, amplitude, state["models"]["B1"].model.pre.floors[f"v{target}_rms"])
                       for r, s in zip(records, scale)]
        changed, info = zip(*transformed)
        valid = np.array([r["valid"] for r in info])
        if family == "H2" and not all(r["invariant"] for r in info):
            raise AssertionError("H2 Fourier invariance failed")
        cf = core.features(changed)
        for name, model in state["models"].items():
            pred = model.predict(cf)
            original = baselines[name]
            close = np.isclose(pred["score"], original["score"], rtol=1e-10, atol=1e-12)
            numerical = (family == "H2") & close & (pred["bit"] != original["bit"])
            for i, r in enumerate(records):
                raw_rows.append(dict(family=family, model=name, target=target, frequency=frequency, amplitude=amplitude,
                    seed=seed, parent=r.parent, n=len(r.x), supported=valid[i], detected=bool(pred["bit"][i] and valid[i]),
                    original_request=original["bit"][i], new_detected=bool(pred["bit"][i] and not original["bit"][i] and valid[i] and not numerical[i]),
                    raw_bit=pred["bit"][i], numerical_boundary=bool(numerical[i]),
                    abs_score_change=abs(pred["score"][i]-original["score"][i]), **{k:v for k, v in info[i].items() if k != "valid"}))
    raw = pd.DataFrame(raw_rows)
    keys = ["family", "model", "target", "frequency", "amplitude", "seed"]
    curves = raw.groupby(keys).agg(parents=("parent", "size"), supported=("supported", "sum"),
        detections=("detected", "sum"), new_detections=("new_detected", "sum"),
        baseline_requests=("original_request", "sum"), numerical_boundaries=("numerical_boundary", "sum"),
        max_abs_score_change=("abs_score_change", "max")).reset_index()
    curves["pod"] = curves.detections/curves.parents
    curves["pod_supported_only"] = curves.detections/curves.supported.replace(0, np.nan)
    csv(output / "heldout_curves.csv", curves)
    csv(output.parent / "cache/heldout_predictions.csv.gz", raw)
    save(output / "heldout_run.json", dict(freeze_sha256=sha(output / "freeze.json"), completed_utc=now(),
        abnormal_contract=abnormal_audit, original_P2_parents=len(records),
        H1_supported=bool(frequencies), H2_invariance_passed=True, no_reselection=True,
        compared_press_models=frozen["press_test_models"], no_independent_press_fault_claim=True))
    print("E5 press retrospective and heldout changes completed", flush=True)
