"""Reproducible normal-only selection followed by locked retrospective evaluation.

Run from any working directory with --data-dir pointing directly to the two
original CSV files. Development never opens the abnormal CSV, even to hash it.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
sys.dont_write_bytecode = True

import numpy as np
import pandas as pd
import scipy
import sklearn
from threadpoolctl import threadpool_limits

from frontier_model import FrontierSuite, ROOT, HERE, D, VIBRATION, candidate_grid
from scenarios import CausalGenerator, FAMILIES, ONSETS, DEVELOPMENT_SEEDS, EVALUATION_SEEDS

ALPHAS = (.01, .03, .05)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean_json(x) for x in value]
    if isinstance(value, np.generic):
        return clean_json(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def canonical_hash(value):
    return hashlib.sha256(json.dumps(clean_json(value), sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def file_hash(path, normalized=False):
    raw = Path(path).read_bytes()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n") if normalized else raw).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(clean_json(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def locked_sources():
    own = [HERE / name for name in ("PROTOCOL.md", "frontier_model.py", "scenarios.py", "run_experiment.py",
                                     "vibration_branch.py", "competitor_reference.py")]
    shared = [ROOT / "yejun/press_guard/model.py"] + [ROOT / "yejun/press_submission/press" / name
               for name in ("data.py", "scores.py", "calibrate.py", "validation.py")]
    return {str(p.relative_to(ROOT)).replace("\\", "/"): file_hash(p, True) for p in own + shared}


def write_lock(output, selection):
    payload = dict(schema=1, created_utc=utc_now(), selected=selection["selected"],
                   normal_only_selection=True, abnormal_file_read=False,
                   config_sha256=file_hash(output / "config.json"),
                   selection_sha256=file_hash(output / "selection.json"),
                   development_candidates_sha256=file_hash(output / "development_candidates.csv"),
                   source_sha256_lf=locked_sources())
    payload["lock_sha256"] = canonical_hash(payload)
    write_json(output / "selection_lock.json", payload)
    return payload


def verify_lock(path):
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("lock_sha256")
    if canonical_hash(payload) != expected:
        raise ValueError("Selection lock payload hash mismatch")
    if not payload.get("normal_only_selection") or payload.get("abnormal_file_read"):
        raise ValueError("Selection lock does not attest normal-only development")
    for key, name in (("config_sha256", "config.json"), ("selection_sha256", "selection.json"),
                      ("development_candidates_sha256", "development_candidates.csv")):
        if file_hash(path.parent / name) != payload[key]:
            raise ValueError(f"Locked {name} changed")
    if locked_sources() != payload["source_sha256_lf"]:
        raise ValueError("Locked experiment source changed; do not reuse the old selection")
    selected = json.loads((path.parent / "selection.json").read_text(encoding="utf-8"))["selected"]
    if selected != payload["selected"]:
        raise ValueError("Selected candidate inconsistent with lock")
    payload["lock_sha256"] = expected
    return payload


def load_records(data_dir, kind, lock_path=None):
    if kind not in ("normal", "abnormal"):
        raise ValueError(kind)
    if kind == "abnormal":
        if lock_path is None:
            raise ValueError("A verified selection lock is required before reading abnormal data")
        verify_lock(lock_path)  # Must precede opening/hashing the abnormal file.
    path = Path(data_dir) / D.FILES[kind]
    digest = file_hash(path)
    if digest != D.EXPECTED_SHA256[kind]:
        raise ValueError(f"Original {kind} CSV hash mismatch: {digest}")
    frame = pd.read_csv(path)
    status = D.validate_rows(frame)
    if len(frame) != D.EXPECTED_ROWS[kind] or np.any(status != "ok"):
        raise ValueError("Unexpected row count or invalid source data")
    seg = D.segments(frame, status)
    if len(np.unique(seg)) != D.EXPECTED_SEGMENTS[kind]:
        raise ValueError("Unexpected recording boundaries")
    values = D.quantize(D.inputs_only(frame), "matched")[D.SENSORS].to_numpy(float)
    records = [values[seg == i] for i in np.unique(seg)]
    return records, dict(path=str(path.resolve()), sha256=digest, rows=len(frame),
                         records=len(records), loaded_utc=utc_now(), quantization="matched")


def experiment_config():
    return dict(version="frontier-20261008-v1", study="retrospective_same_dataset_not_independent_test",
                development=dict(fit=[0, 120], calibration=[120, 240], selection=[240, 300]),
                evaluation_splits={"A": [360, 480, 600], "B": [300, 420, 600]},
                alphas=ALPHAS, injection_alpha=.01, candidates=candidate_grid(),
                or_comparators=[f"OR_V2_{v}" for v in VIBRATION],
                injection_families=FAMILIES, onset_fractions=ONSETS,
                development_seeds=DEVELOPMENT_SEEDS, evaluation_seeds=EVALUATION_SEEDS,
                quantization="Original CSV matched quantization before injection/stress; continuous additive deltas retained",
                normal_record_gate=.05, each_offset_fpr_increase_gate=.02,
                ranking=["max minimum of four family mean detection rates", "max family macro mean detection",
                         "min maximum stress record false alarm rate", "min complexity", "lexical name"],
                baseline_scope="59 protocol candidates plus four separately calibrated OR comparators. These VR/VD branches are not the earlier three-channel RidgeForecast. Feature-matched 5NN and earlier Ridge are historical report comparisons, not rerun here.",
                no_alarm_persistence=True, unavailable_rows="kept in all metric denominators",
                stress_assumptions="offset +/- train SD per sensor; gain .8/1.2; current load AC multiplier .5/1.5 about train mean; all-channel 4x quantization; stuck final half; jitter sigma .1/.5 ms on assumed 60.6Hz carrier")


def alarm_summary(alarms):
    rows = sum(map(len, alarms))
    return dict(rows=rows, alarm_rows=int(sum(np.count_nonzero(x) for x in alarms)),
                records=len(alarms), alarm_records=int(sum(np.any(x) for x in alarms)),
                row_rate=sum(np.count_nonzero(x) for x in alarms) / max(rows, 1),
                record_rate=sum(np.any(x) for x in alarms) / max(len(alarms), 1))


def injection_experiment(suite, gen, records, seeds, phase, output, offset=0):
    controls = suite.alarms(suite.score(records), .01)
    aggregates = []
    detail_path = output / "local" / f"{phase}_injection_records.csv.gz"
    detail_columns = ["phase", "family", "target", "strength", "onset_fraction", "seed", "alpha",
                      "model", "record", "onset", "rows", "detected", "control_detected", "pre_onset_alarm", "delay_s"]
    detail_file = gzip.open(detail_path, "wt", encoding="utf-8", newline="")
    writer = csv.DictWriter(detail_file, fieldnames=detail_columns)
    writer.writeheader()
    for family, spec in FAMILIES.items():
        for target in spec["targets"]:
            for strength in spec["strengths"]:
                for fraction in ONSETS:
                    onsets = [min(len(r) - 1, max(1, int(len(r) * fraction))) for r in records]
                    for seed in seeds:
                        injected = [gen.inject(r, family, target, strength, seed + 1009 * (k + offset), onset)
                                    for k, (r, onset) in enumerate(zip(records, onsets))]
                        alarms = suite.alarms(suite.score(injected), .01)
                        common = dict(phase=phase, family=family, target=target, strength=strength,
                                      onset_fraction=fraction, seed=seed, alpha=.01)
                        for model, values in alarms.items():
                            hits, paired, pre, delays = [], [], [], []
                            for k, (a, c, onset) in enumerate(zip(values, controls[model], onsets)):
                                pos = np.flatnonzero(a[onset:])
                                hit, control = bool(len(pos)), bool(np.any(c[onset:]))
                                delay = float(pos[0] * .1) if hit else None
                                hits.append(hit); paired.append(control); pre.append(bool(np.any(a[:onset])))
                                if hit:
                                    delays.append(delay)
                                writer.writerow(dict(**common, model=model, record=k + offset, onset=onset,
                                                    rows=len(a), detected=hit, control_detected=control,
                                                    pre_onset_alarm=pre[-1], delay_s=delay))
                            aggregates.append(dict(**common, model=model, records=len(records), eligible=len(records),
                                                   detected=sum(hits), missed=len(records)-sum(hits),
                                                   detection_rate=np.mean(hits), control_rate=np.mean(paired),
                                                   paired_increase=np.mean(hits)-np.mean(paired),
                                                   pre_onset_alarm_rate=np.mean(pre),
                                                   hit_only_median_delay_s=np.median(delays) if delays else None))
        print(f"{phase}: causal injection {family} complete", flush=True)
    result = pd.DataFrame(aggregates)
    result.to_csv(output / f"{phase}_injection.csv", index=False)
    detail_file.close()
    return result


def stress_experiment(suite, gen, normal, phase, output, abnormal=None, alphas=ALPHAS):
    result = []
    for spec in gen.stress_specs():
        ns = suite.score(gen.perturb(normal, **spec))
        ab = suite.score(gen.perturb(abnormal, **spec)) if abnormal is not None else None
        for alpha in alphas:
            na = suite.alarms(ns, alpha)
            aa = suite.alarms(ab, alpha) if ab is not None else None
            for model, alarms in na.items():
                summary = alarm_summary(alarms)
                row = dict(phase=phase, model=model, alpha=alpha, **spec,
                           normal_rows=summary["rows"], normal_fp_rows=summary["alarm_rows"],
                           normal_records=summary["records"], normal_fp_records=summary["alarm_records"],
                           normal_record_fpr=summary["record_rate"], normal_row_fpr=summary["row_rate"])
                if aa is not None:
                    a = alarm_summary(aa[model])
                    row.update(abnormal_records=a["records"], abnormal_detected_records=a["alarm_records"],
                               abnormal_detected_rows=a["alarm_rows"], abnormal_row_recall=a["row_rate"])
                result.append(row)
    result = pd.DataFrame(result)
    result.to_csv(output / f"{phase}_stress.csv", index=False)
    return result


def develop(normal, manifest, output):
    if (output / "selection_lock.json").exists():
        raise FileExistsError("Selection already locked; use --phase evaluate or a new output directory")
    config = experiment_config()
    write_json(output / "config.json", config)
    write_json(output / "development_started.json", dict(started_utc=utc_now(), input=manifest,
                                                         source_sha256_lf=locked_sources(), abnormal_read=False))
    train, cal, dev = normal[:120], normal[120:240], normal[240:300]
    print("development: fitting normal records 0..119; calibration 120..239", flush=True)
    suite = FrontierSuite().fit(train).calibrate(cal)
    gen = CausalGenerator().fit(train)
    baseline = suite.alarms(suite.score(dev), .01)
    normal_summary = {name: alarm_summary(values) for name, values in baseline.items()}
    stress = stress_experiment(suite, gen, dev, "development", output, alphas=(.01,))
    injection = injection_experiment(suite, gen, dev, DEVELOPMENT_SEEDS, "development", output, offset=240)
    rows = []
    specs = {x["name"]: x for x in candidate_grid()}
    for model in normal_summary:
        fpr = normal_summary[model]["record_rate"]
        ms = stress[stress.model.eq(model)]
        offset_increase = float((ms.loc[ms.kind.eq("offset"), "normal_record_fpr"] - fpr).max())
        families = injection[injection.model.eq(model)].groupby("family").detection_rate.mean()
        spec = specs.get(model, dict(selectable=False, complexity=3))
        passes = bool(fpr <= .05 + 1e-12 and offset_increase <= .02 + 1e-12)
        rows.append(dict(model=model, selectable=spec["selectable"], gate_pass=passes,
                         normal_record_fpr=fpr, offset_max_increase=offset_increase,
                         minimum_family_detection=float(families.min()),
                         macro_family_detection=float(families.mean()),
                         maximum_stress_fpr=float(ms.normal_record_fpr.max()), complexity=spec["complexity"],
                         **{f"detection_{name}": value for name, value in families.items()}))
    ranking = pd.DataFrame(rows).sort_values(
        ["gate_pass", "minimum_family_detection", "macro_family_detection", "maximum_stress_fpr", "complexity", "model"],
        ascending=[False, False, False, True, True, True])
    eligible = ranking[ranking.gate_pass & ranking.selectable]
    selected = None if eligible.empty else str(eligible.iloc[0].model)
    ranking.to_csv(output / "development_candidates.csv", index=False)
    selection = dict(selected=selected, selection_succeeded=selected is not None,
                     selected_metrics=eligible.iloc[0].to_dict() if selected else None,
                     normal_only=True, abnormal_read=False, completed_utc=utc_now(),
                     candidates=59, separately_calibrated_or_comparators=4,
                     gate_pass_selectable=int(len(eligible)), injection_scale=dict(
                         mean=gen.mean_, sd=gen.std_, ac_scale=gen.ac_scale_, current_residual_scale=gen.current_residual_scale_),
                     no_candidate_policy="Record failure; never relax gates after evaluation")
    write_json(output / "selection.json", selection)
    lock = write_lock(output, selection)
    print(f"LOCKED selected={selected}, sha256={lock['lock_sha256']}", flush=True)
    return lock


def actual_metrics(suite, normal, abnormal, split, output, normal_offset):
    ns, ads = suite.score(normal), suite.score(abnormal)
    metrics, record_rows = [], []
    local = pd.DataFrame(dict(source=["normal"] * sum(map(len, normal)) + ["abnormal"] * sum(map(len, abnormal)),
                              record=np.concatenate([np.full(len(r), k + off) for rs, off in ((normal, normal_offset), (abnormal, 0)) for k, r in enumerate(rs)]),
                              position=np.concatenate([np.arange(len(r)) for r in normal + abnormal])))
    for model in ns:
        local[model + "|score"] = np.concatenate(ns[model] + ads[model])
    # Build once to avoid fragmentation when adding all model/alpha predictions.
    alarm_columns = {}
    for alpha in ALPHAS:
        na, aa = suite.alarms(ns, alpha), suite.alarms(ads, alpha)
        for model in na:
            n = alarm_summary(na[model])
            alarm_columns[f"{model}|alarm@{alpha:g}"] = np.concatenate(na[model] + aa[model]).astype(np.int8)
            for subset, sl in (("front10", slice(0, 10)), ("back11", slice(10, 21)), ("all21", slice(0, 21))):
                values = aa[model][sl]
                a = alarm_summary(values)
                tp, fp, fn = a["alarm_rows"], n["alarm_rows"], a["rows"] - a["alarm_rows"]
                delays = [float(np.flatnonzero(x)[0] * .1) for x in values if np.any(x)]
                metrics.append(dict(split=split, alpha=alpha, model=model, abnormal_subset=subset,
                                    normal_rows=n["rows"], normal_fp_rows=fp, normal_records=n["records"],
                                    normal_fp_records=n["alarm_records"], normal_record_fpr=n["record_rate"],
                                    abnormal_rows=a["rows"], tp=tp, fn=fn,
                                    row_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0,
                                    row_precision=tp/(tp+fp) if tp+fp else 0.0, row_recall=a["row_rate"],
                                    abnormal_records=a["records"], detected_records=a["alarm_records"],
                                    missed_records=a["records"]-a["alarm_records"],
                                    hit_only_median_delay_s=np.median(delays) if delays else None,
                                    hit_only_max_delay_s=max(delays) if delays else None,
                                    normal_unscored_rows=int(sum(np.count_nonzero(~np.isfinite(x)) for x in ns.get(model, []))),
                                    abnormal_unscored_rows=int(sum(np.count_nonzero(~np.isfinite(x)) for x in ads.get(model, [])[sl])) if model in ads else None,
                                    equal_single_budget=not model.startswith("OR_")))
            for k, alarms in enumerate(aa[model]):
                pos = np.flatnonzero(alarms)
                record_rows.append(dict(split=split, alpha=alpha, model=model, record=k, rows=len(alarms),
                                        detected=bool(len(pos)), alarm_rows=int(alarms.sum()),
                                        first_alarm_position=int(pos[0]) if len(pos) else None,
                                        delay_s=float(pos[0] * .1) if len(pos) else None))
    local = pd.concat([local, pd.DataFrame(alarm_columns)], axis=1)
    local.to_csv(output / "local" / f"{split}_row_predictions.csv.gz", index=False, compression="gzip")
    pd.DataFrame(record_rows).to_csv(output / f"{split}_abnormal_records.csv", index=False)
    return pd.DataFrame(metrics)


def evaluate(normal, manifest, data_dir, output):
    lock = verify_lock(output / "selection_lock.json")
    abnormal, am = load_records(data_dir, "abnormal", output / "selection_lock.json")
    write_json(output / "evaluation_started.json", dict(started_utc=utc_now(), lock_sha256=lock["lock_sha256"],
                                                        normal=manifest, abnormal=am, environment=dict(
                                                            python=platform.python_version(), platform=platform.platform(),
                                                            numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__,
                                                            sklearn=sklearn.__version__)))
    tables = []
    for split, (train_end, cal_end, _) in experiment_config()["evaluation_splits"].items():
        print(f"evaluation {split}: fit {train_end}, cal {cal_end-train_end}, normal test {len(normal)-cal_end}", flush=True)
        train, cal, test = normal[:train_end], normal[train_end:cal_end], normal[cal_end:]
        suite = FrontierSuite().fit(train).calibrate(cal)
        gen = CausalGenerator().fit(train)
        write_json(output / f"{split}_fitted_metadata.json", dict(training_records=train_end,
                         calibration_records=cal_end-train_end, current_ar2=suite.guard_.coef,
                         difference_ar2=suite.diff_coef_, calibration_maxima=suite.cal_,
                         vibration={name: obj.metadata() for name, obj in suite.vibration_.items()},
                         mean=gen.mean_, sd=gen.std_, ac_scale=gen.ac_scale_, current_residual_scale=gen.current_residual_scale_))
        metric = actual_metrics(suite, test, abnormal, split, output, cal_end)
        metric.to_csv(output / f"{split}_actual_metrics.csv", index=False)
        tables.append(metric)
        stress_experiment(suite, gen, test, split, output, abnormal=abnormal)
        injection_experiment(suite, gen, test, EVALUATION_SEEDS, split, output, offset=cal_end)
        print(f"evaluation {split} complete", flush=True)
    combined = pd.concat(tables, ignore_index=True)
    combined.to_csv(output / "actual_metrics.csv", index=False)
    selected = lock["selected"]
    selected_rows = combined[combined.model.isin(["V2", selected]) & combined.alpha.eq(.01)]
    selected_rows.to_csv(output / "selected_vs_v2.csv", index=False)
    worsen = []
    if selected:
        for split in ("A", "B"):
            sub = combined[combined.split.eq(split) & combined.alpha.eq(.01) & combined.abnormal_subset.eq("all21")].set_index("model")
            if sub.loc[selected, "row_f1"] < sub.loc["V2", "row_f1"] or sub.loc[selected, "normal_record_fpr"] > sub.loc["V2", "normal_record_fpr"]:
                worsen.append(split)
    write_json(output / "decision.json", dict(selected=selected, lock_sha256=lock["lock_sha256"],
                     completed_utc=utc_now(), actual_worsening_splits=worsen,
                     official_model_replacement_recommended=False,
                     interpretation=("Selected candidate deteriorates on observed actual evaluation; retain original official model and discuss supplementary scope only" if worsen
                                     else "Retrospective result only; this does not establish independent failure generalization or justify overwriting the official model"),
                     missed_detection_delay_policy="Misses retained and counted separately; hit-only delay summaries are not a failure lead time",
                     limitation="21 abnormal recording fragments are not 21 independent failures; A/B overlap; no deployment timing guarantee"))
    verify_lock(output / "selection_lock.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "outputs")
    parser.add_argument("--phase", choices=("all", "develop", "evaluate"), default="all")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "local").mkdir(exist_ok=True)
    start = time.perf_counter()
    with threadpool_limits(limits=1):
        normal, manifest = load_records(args.data_dir, "normal")
        if args.phase in ("all", "develop"):
            develop(normal, manifest, output)
        if args.phase in ("all", "evaluate"):
            evaluate(normal, manifest, args.data_dir, output)
    print(f"Completed {args.phase} in {time.perf_counter()-start:.1f}s: {output}", flush=True)


if __name__ == "__main__":
    main()
