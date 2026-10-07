"""Fixed-model frequency, injection-family and calibration sensitivity on normal data.

This audit never evaluates the abnormal file, selects a replacement model, or
changes the original selection lock. Its protocol is saved before model fitting.
"""
from __future__ import annotations

import argparse
import csv
from functools import lru_cache
import gzip
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from frontier_model import FrontierSuite, record_maxima
from run_experiment import (canonical_hash, clean_json, file_hash, load_records,
                            utc_now, verify_lock, write_json)
from scenarios import CausalGenerator
from press.calibrate import conformal_p

HERE = Path(__file__).resolve().parent
SELECTED = "V2+VD3@1"
MODELS = ("V2", SELECTED)
ALPHA = .01
DT = .1
CURRENT_STEP = 1.1920929
FREQUENCY_GRID = np.arange(.30, .9001, .0005)
DELTAS = (0., .005, -.005, .01, -.01, .02, -.02, .05, -.05, .1, -.1)
ONSET_FRACTIONS = (.25, .6)
NEW_FAMILIES = {
    "slow_vibration_level_ramp": dict(targets=[0, 1], strengths=[.5, 1.], signs=[-1, 1], seeds=[0]),
    "intermittent_zeroing": dict(targets=[0, 1, 2], strengths=[1, 3], signs=[1], seeds=[811, 1217, 2027]),
    "gradual_current_amplitude_reduction": dict(targets=[2], strengths=[.2, .4], signs=[1], seeds=[0]),
}


def protocol():
    return dict(
        schema="normal-sensitivity-v1", models=list(MODELS), alpha=ALPHA,
        scope="Previously observed normal data and synthetic changes; no independent failure validation",
        no_model_or_policy_change=True, abnormal_file_read=False,
        splits={"A": [360, 480, 600], "B": [300, 420, 600]},
        frequency=dict(grid_hz=[.30, .90, .0005], minimum_rows=8, deltas_hz=list(DELTAS),
                       residual_preserved=True, current_requantization_step=CURRENT_STEP,
                       controls=["original", "delta_zero_resynthesis"],
                       short_records="Unchanged and retained in all denominators",
                       interpretation="Whole-record sine reconstruction; retrospective sensor/drive sensitivity, not causal online signal transformation"),
        new_families=NEW_FAMILIES, onset_fractions=ONSET_FRACTIONS,
        injection_definitions=dict(
            slow_vibration_level_ramp="Signed additive ramp, reaches strength * training within-record AC RMS after 20 post-onset samples and then stays constant",
            intermittent_zeroing="Zero selected sensor for strength samples every 10 post-onset samples; seed fixes phase; timestamps/rows retained",
            gradual_current_amplitude_reduction="Linearly reduce current AC about frozen training mean by strength over 20 post-onset samples, then hold",
            controls="Same unmodified recording; alarms counted only from onset to recording end; pre-onset arrays must be byte-identical",
            scales="Fit on the original A or B normal training records only; no per-evaluation-record centering",
            continuous_deltas="Retained after original matched input quantization, as in the original causal injection experiment"),
        leave_one_family_out=dict(source="development_candidates.csv", gates="Original selectable and gate_pass flags unchanged",
                                  ranking=["max remaining-family minimum", "max remaining-family mean", "min original maximum_stress_fpr", "min complexity", "lexical model"],
                                  selection_role="Descriptive stability audit; original selected candidate remains fixed"),
        calibration_contamination=dict(counts=[1, 2, 5], records="First 1/2/5 calibration recordings with at least 8 rows",
            scenarios=[dict(family="vibration_impulse", target=1, strength=4., onset_fraction=.25, seed=919),
                       dict(family="current_distortion", target=2, strength=1., onset_fraction=.25, seed=919)],
            statistic="Replace only calibration record maxima; fit, branch scales, candidates and alpha remain fixed",
            evaluations="Unmodified normal test records and the already fixed new-family injections"))


def install_normal_only_guard(data_dir):
    """Fail closed if this process tries to open the abnormal raw file."""
    from frontier_model import D
    allowed = (Path(data_dir) / D.FILES["normal"]).resolve()
    abnormal_name = D.FILES["abnormal"].casefold()
    directory = Path(data_dir).resolve()

    def guard(event, args):
        if event != "open" or not args or not isinstance(args[0], (str, bytes, Path)):
            return
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
        if path.name.casefold() == abnormal_name or (path.is_relative_to(directory) and path != allowed):
            raise PermissionError("Normal-only audit forbids every other raw input, including the abnormal file")

    sys.addaudithook(guard)
    return allowed


def lock_protocol(output, experiment_output, normal_manifest):
    selection = verify_lock(experiment_output / "selection_lock.json")
    if selection["selected"] != SELECTED:
        raise ValueError("This audit is fixed to the previously selected V2+VD3@1 candidate")
    payload = dict(protocol=protocol(), source_sha256_lf=file_hash(Path(__file__), True),
                   original_selection_lock_sha256=selection["lock_sha256"],
                   development_candidates_sha256=file_hash(experiment_output / "development_candidates.csv"),
                   normal_csv_sha256=normal_manifest["sha256"], abnormal_file_read=False)
    path = output / "protocol_lock.json"
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        digest = saved.pop("protocol_lock_sha256")
        if canonical_hash(saved) != digest:
            raise ValueError("Normal-sensitivity protocol lock was changed")
        saved.pop("created_utc")
        if saved != clean_json(payload):
            raise ValueError("Protocol/code/input changed; use a new output directory")
        return digest
    payload["created_utc"] = utc_now()
    payload["protocol_lock_sha256"] = canonical_hash(payload)
    write_json(path, payload)
    return payload["protocol_lock_sha256"]


def onset_for(record, fraction):
    return min(len(record) - 1, max(1, int(len(record) * fraction)))


def new_injection(record, gen, family, target, strength, onset, seed=0, sign=1):
    x = np.asarray(record, float)
    if not 0 <= onset < len(x):
        raise ValueError("onset outside record")
    spec = NEW_FAMILIES[family]
    if target not in spec["targets"] or strength < 0 or sign not in (-1, 1):
        raise ValueError("Unsupported injection parameters")
    out = x.copy()
    if strength == 0:
        return out
    k = np.arange(len(x) - onset)
    ramp = np.minimum((k + 1) / 20., 1.)
    if family == "slow_vibration_level_ramp":
        out[onset:, target] += sign * strength * gen.ac_scale_[target] * ramp
    elif family == "intermittent_zeroing":
        width = int(strength)
        if strength != width or not 1 <= width < 10:
            raise ValueError("Zeroing duration must be an integer in 1..9")
        phase = int(np.random.default_rng(seed).integers(0, 10))
        mask = (k + phase) % 10 < width
        out[onset + np.flatnonzero(mask), target] = 0.
    else:
        if strength > 1:
            raise ValueError("Amplitude reduction must be in [0,1]")
        out[onset:, target] = gen.mean_[target] + (x[onset:, target] - gen.mean_[target]) * (1 - strength * ramp)
    assert out[:onset].tobytes() == x[:onset].tobytes()
    assert out[:, [i for i in range(3) if i != target]].tobytes() == x[:, [i for i in range(3) if i != target]].tobytes()
    return out


@lru_cache(maxsize=64)
def sine_designs(length):
    t = np.arange(length) * DT
    return tuple(np.column_stack([np.sin(2 * np.pi * f * t),
                                  np.cos(2 * np.pi * f * t), np.ones(length)]) for f in FREQUENCY_GRID)


def fit_sine(current):
    """Same grid, least-squares solve and strict minimum as the reviewed probe."""
    best = None
    for f, design in zip(FREQUENCY_GRID, sine_designs(len(current))):
        coef = np.linalg.lstsq(design, current, rcond=None)[0]
        sse = float(np.sum((current - design @ coef) ** 2))
        if best is None or sse < best[0]:
            best = (sse, float(f), coef)
    return best[1], best[2]


def shift_frequency(record, delta, fitted=None):
    out = np.asarray(record, float).copy()
    if len(out) < 8:
        return out
    frequency, (a, b, c) = fit_sine(out[:, 2]) if fitted is None else fitted
    t = np.arange(len(out)) * DT
    old = a * np.sin(2*np.pi*frequency*t) + b*np.cos(2*np.pi*frequency*t) + c
    residual = out[:, 2] - old
    new = a*np.sin(2*np.pi*(frequency+delta)*t) + b*np.cos(2*np.pi*(frequency+delta)*t) + c + residual
    out[:, 2] = np.round(new/CURRENT_STEP)*CURRENT_STEP
    return out


def target_scores(suite, records):
    """Evaluate the unchanged two paths without calculating unused candidates."""
    v2 = suite.current_parts(records)["V2"]
    vd3 = suite.vibration_["VD3"].score(records)
    fused = [np.fmax(suite.fusion_tails_["V2"](a), suite.fusion_tails_["VD3"](b))
             for a, b in zip(v2, vd3)]
    return {"V2": v2, SELECTED: fused}


def alarms(scores, calibration):
    return {model: [np.nan_to_num(conformal_p(calibration[model], score), nan=1.) <= ALPHA
                    for score in values] for model, values in scores.items()}


def alarm_counts(values):
    return dict(rows=sum(map(len, values)), alarm_rows=sum(int(np.count_nonzero(x)) for x in values),
                records=len(values), alarm_records=sum(bool(np.any(x)) for x in values))


def paired_summary(injected, controls, onsets):
    hits, baseline, pre, delays = [], [], [], []
    for alarm, control, onset in zip(injected, controls, onsets):
        where = np.flatnonzero(alarm[onset:])
        hits.append(bool(len(where)))
        baseline.append(bool(np.any(control[onset:])))
        pre.append(bool(np.any(alarm[:onset])))
        delays.append(float(where[0]*DT) if len(where) else None)
    return dict(records=len(hits), detected=sum(hits), missed=len(hits)-sum(hits),
                control_detected=sum(baseline), detection_rate=float(np.mean(hits)),
                control_rate=float(np.mean(baseline)), paired_increase=float(np.mean(hits)-np.mean(baseline)),
                pre_onset_alarm_records=sum(pre), hit_only_median_delay_s=float(np.median([x for x in delays if x is not None])) if any(hits) else None), (hits, baseline, pre, delays)


def leave_one_family_out(frame, selected=SELECTED):
    columns = [c for c in frame.columns if c.startswith("detection_")]
    if len(columns) != 4:
        raise ValueError("Expected the original four family columns")
    pool = frame[frame.selectable & frame.gate_pass].copy()
    rows = []
    for dropped in [None, *columns]:
        used = [c for c in columns if c != dropped]
        ranked = pool.assign(audit_min=pool[used].min(axis=1), audit_macro=pool[used].mean(axis=1)).sort_values(
            ["audit_min", "audit_macro", "maximum_stress_fpr", "complexity", "model"],
            ascending=[False, False, True, True, True])
        chosen = ranked.iloc[0]
        original = ranked[ranked.model.eq(selected)].iloc[0]
        rows.append(dict(excluded_family=dropped.removeprefix("detection_") if dropped else "none",
                         audit_choice=chosen.model, original_choice=selected, choice_changed=chosen.model != selected,
                         remaining_minimum=float(chosen.audit_min), remaining_macro=float(chosen.audit_macro),
                         original_choice_rank=int(np.flatnonzero(ranked.model.eq(selected).to_numpy())[0])+1,
                         original_remaining_minimum=float(original.audit_min),
                         original_remaining_macro=float(original.audit_macro), eligible_candidates=len(pool),
                         selection_applied=False))
    if rows[0]["audit_choice"] != selected:
        raise ValueError("Original four-family ranking does not reproduce the locked selection")
    return pd.DataFrame(rows)


def run_split(split, bounds, normal, output, frequency_fits):
    train_end, cal_end, test_end = bounds
    train, cal, test = normal[:train_end], normal[train_end:cal_end], normal[cal_end:test_end]
    suite = FrontierSuite().fit(train).calibrate(cal)
    gen = CausalGenerator().fit(train)
    calibration = {model: suite.cal_[model].copy() for model in MODELS}
    computed_cal = target_scores(suite, cal)
    for model in MODELS:
        np.testing.assert_allclose(record_maxima(computed_cal[model]), calibration[model], rtol=0, atol=0)
    baseline_scores = target_scores(suite, test)
    controls = alarms(baseline_scores, calibration)
    frequency_rows = []
    for label, delta in [("original", None), *[("delta_zero_resynthesis" if d == 0 else "frequency_shift", d) for d in DELTAS]]:
        changed = test if delta is None else [shift_frequency(record, delta, frequency_fits.get(i+cal_end)) for i, record in enumerate(test)]
        predictions = controls if delta is None else alarms(target_scores(suite, changed), calibration)
        for model in MODELS:
            count = alarm_counts(predictions[model])
            base = alarm_counts(controls[model])
            frequency_rows.append(dict(split=split, model=model, scenario=label, delta_hz=delta, alpha=ALPHA,
                eligible_records=sum(len(r)>=8 for r in test), short_records=sum(len(r)<8 for r in test),
                **count, normal_record_fpr=count["alarm_records"]/len(test),
                record_fpr_change=count["alarm_records"]/len(test)-base["alarm_records"]/len(test)))
        print(f"{split} frequency {label} delta={delta}: " + str({m: alarm_counts(predictions[m])["alarm_records"] for m in MODELS}), flush=True)
    pd.DataFrame(frequency_rows).to_csv(output/f"{split}_frequency.csv", index=False)

    injection_rows, cached = [], []
    detail_path = output / "local" / f"{split}_new_family_records.csv.gz"
    with gzip.open(detail_path, "wt", encoding="utf-8", newline="") as handle:
        fields = ["split", "family", "target", "strength", "sign", "seed", "onset_fraction", "model", "record", "onset", "rows", "detected", "control_detected", "pre_onset_alarm", "delay_s"]
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for family, spec in NEW_FAMILIES.items():
            for target in spec["targets"]:
                for strength in spec["strengths"]:
                    for sign in spec["signs"]:
                        for fraction in ONSET_FRACTIONS:
                            onsets = [onset_for(record, fraction) for record in test]
                            for seed in spec["seeds"]:
                                injected = [new_injection(record, gen, family, target, strength, onset,
                                             seed + 1009*(cal_end+i), sign) for i,(record,onset) in enumerate(zip(test,onsets))]
                                scored = target_scores(suite, injected)
                                predicted = alarms(scored, calibration)
                                scenario = dict(split=split, family=family, target=target, strength=strength,
                                                sign=sign, seed=seed, onset_fraction=fraction)
                                cached.append((scenario, scored, onsets))
                                for model in MODELS:
                                    result, detail = paired_summary(predicted[model], controls[model], onsets)
                                    injection_rows.append(dict(**scenario, model=model, alpha=ALPHA, **result))
                                    for i, (hit, control, pre, delay) in enumerate(zip(*detail)):
                                        writer.writerow(dict(**scenario, model=model, record=cal_end+i,
                                            onset=onsets[i], rows=len(test[i]), detected=hit, control_detected=control,
                                            pre_onset_alarm=pre, delay_s=delay))
            print(f"{split} new family {family} completed", flush=True)
    pd.DataFrame(injection_rows).to_csv(output/f"{split}_new_families.csv", index=False)

    contamination_rows = []
    eligible = [i for i,record in enumerate(cal) if len(record)>=8]
    for spec in protocol()["calibration_contamination"]["scenarios"]:
        for count in (0, 1, 2, 5):
            perturbed = [r.copy() for r in cal]
            for i in eligible[:count]:
                perturbed[i] = gen.inject(cal[i], spec["family"], spec["target"], spec["strength"],
                                         spec["seed"]+1009*(train_end+i), onset_for(cal[i],spec["onset_fraction"]))
            changed_scores = computed_cal if count == 0 else target_scores(suite, perturbed)
            changed_cal = {m: record_maxima(changed_scores[m]) for m in MODELS}
            test_alarms = alarms(baseline_scores, changed_cal)
            family_hits = {m: {} for m in MODELS}
            for scenario, scores, onsets in cached:
                predicted = alarms(scores, changed_cal)
                for model in MODELS:
                    row, _ = paired_summary(predicted[model], test_alarms[model], onsets)
                    family_hits[model].setdefault(scenario["family"], []).append(row)
            for model in MODELS:
                counts = alarm_counts(test_alarms[model])
                for family, values in family_hits[model].items():
                    contamination_rows.append(dict(split=split, model=model, alpha=ALPHA,
                        contamination_family=spec["family"], contaminated_records=count,
                        calibration_records=len(cal), contaminated_record_ids=json.dumps([train_end+i for i in eligible[:count]]),
                        baseline_maximum=float(np.max(calibration[model])), contaminated_maximum=float(np.max(changed_cal[model])),
                        normal_fp_records=counts["alarm_records"], normal_records=counts["records"],
                        evaluation_family=family, mean_detection_rate=float(np.mean([x["detection_rate"] for x in values])),
                        mean_control_rate=float(np.mean([x["control_rate"] for x in values])),
                        mean_paired_increase=float(np.mean([x["paired_increase"] for x in values]))))
    pd.DataFrame(contamination_rows).to_csv(output/f"{split}_calibration_contamination.csv", index=False)
    write_json(output/f"{split}_metadata.json", dict(split=split, train_record_ids=[0,train_end-1],
        calibration_record_ids=[train_end,cal_end-1], normal_test_record_ids=[cal_end,test_end-1],
        target_calibration_scores_identical=True, injection_scales=dict(mean=gen.mean_, ac_rms=gen.ac_scale_),
        calibration_maxima={m:float(np.max(calibration[m])) for m in MODELS},
        causal_prefix_preserved=True, other_channels_preserved=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--experiment-output", type=Path, default=HERE/"outputs")
    parser.add_argument("--output", type=Path, default=HERE/"outputs/normal_sensitivity")
    args = parser.parse_args()
    data_dir, experiment, output = args.data_dir.resolve(), args.experiment_output.resolve(), args.output.resolve()
    install_normal_only_guard(data_dir)
    original_lock = verify_lock(experiment/"selection_lock.json")
    normal, manifest = load_records(data_dir, "normal")
    output.mkdir(parents=True, exist_ok=True); (output/"local").mkdir(exist_ok=True)
    (output/".gitignore").write_text("/local/\n", encoding="utf-8")
    digest = lock_protocol(output, experiment, manifest)
    print(f"Normal-only sensitivity protocol locked: {digest}", flush=True)
    ranking = leave_one_family_out(pd.read_csv(experiment/"development_candidates.csv"))
    ranking.to_csv(output/"leave_one_family_out.csv", index=False)
    fits = {i:fit_sine(r[:,2]) for i,r in enumerate(normal) if i>=420 and len(r)>=8}
    pd.DataFrame([dict(record=i,rows=len(normal[i]),frequency_hz=f[0]) for i,f in fits.items()]).to_csv(output/"normal_frequency_fits.csv",index=False)
    with threadpool_limits(limits=1):
        for split,bounds in protocol()["splits"].items():
            run_split(split,bounds,normal,output,fits)
    after = verify_lock(experiment/"selection_lock.json")
    if after["lock_sha256"] != original_lock["lock_sha256"]:
        raise ValueError("Original selection changed during sensitivity audit")
    files = {p.name:file_hash(p) for p in sorted(output.iterdir()) if p.suffix in (".csv",".json") and p.name!="summary.json"}
    write_json(output/"summary.json",dict(passed=True, completed_utc=utc_now(), protocol_lock_sha256=digest,
        original_selection_lock_sha256=after["lock_sha256"], selected_model_unchanged=SELECTED,
        abnormal_file_read=False, independent_failure_validation=False,
        no_new_filter_gate_or_alarm_policy=True, normal_input=manifest,
        leave_one_family_out_choices=ranking.to_dict(orient="records"), output_sha256=files))
    print(f"Normal-only sensitivity audit complete: {output}",flush=True)


if __name__ == "__main__":
    main()
