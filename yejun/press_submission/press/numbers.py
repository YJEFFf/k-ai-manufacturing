"""실행 결과를 검수용 numbers.json으로 집계한다. 대회 보고서는 생성하지 않는다."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import data as D


def run(out: Path, manifest: dict) -> dict:
    run_id = manifest.get("run_id") or manifest.get("git_commit") or "uncommitted"
    diag = json.loads((out / "diagnosis.json").read_text(encoding="utf-8"))
    comparison = out / "model_comparison_all.csv"
    mc = pd.read_csv(comparison if comparison.exists() else out / "model_comparison.csv")
    cells = pd.read_csv(out / "interaction_2x2.csv")
    pre = diag["preprocess"]
    seg_conf = mc[(mc.calibration_unit == "recording_segments") & (mc.criterion == "conformal")]
    main = seg_conf[(seg_conf.model == "combined_w8") & (seg_conf.alpha == 0.01)]
    numbers = {"run_id": run_id, "protocol_version": D.PROTOCOL_VERSION, "preprocess_main": pre, "items": {}}

    def add(key, value, **prov):
        numbers["items"][key] = {"value": value, **prov, "run_id": run_id}

    structure = diag["structure"]
    for label in ("normal", "abnormal"):
        add(f"{label}_rows", structure[label]["rows"], unit="rows")
        add(f"{label}_segments", structure[label]["segments"], unit="segments")
    for mode in ("raw", pre):
        rules = pd.DataFrame(diag[f"format_rules_{mode}"])
        add(f"format_rule_max_separability_{mode}", float(rules.separability.max()), unit="auroc")

    for r in main.itertuples():
        add(f"main_conformal_1pct_abnormal_detected@{r.split}", int(r.abnormal_notified_segments),
            model="combined_w8", split=r.split, preprocess=pre, criterion="conformal", alpha=0.01,
            unit="segments", denominator=int(r.abnormal_segments))
        add(f"main_conformal_1pct_normal_notified@{r.split}", int(r.normal_notified_segments),
            model="combined_w8", split=r.split, preprocess=pre, criterion="conformal", alpha=0.01,
            unit="segments", denominator=int(r.normal_segments))
        add(f"main_conformal_1pct_f1_all_rows@{r.split}", round(float(r.f1_all_rows), 4),
            model="combined_w8", split=r.split, preprocess=pre, criterion="conformal", alpha=0.01, unit="f1")
        add(f"main_conformal_1pct_binomial_upper95@{r.split}", round(float(r.normal_binomial_upper95), 4),
            model="combined_w8", split=r.split, criterion="conformal", alpha=0.01,
            unit="rate", assumption="독립 정상 구간")

    for model in ("maxz_3", "sine_w8", "lstm20", "lstm20_plus_maxz"):
        for r in seg_conf[(seg_conf.model == model) & (seg_conf.alpha == 0.01)].itertuples():
            add(f"{model}_conformal_1pct_abnormal_detected@{r.split}", int(r.abnormal_notified_segments),
                model=model, split=r.split, preprocess=pre, criterion="conformal", alpha=0.01,
                unit="segments", denominator=int(r.abnormal_segments))

    guide_path = out / "lstm_guidebook_reproduction.json"
    if guide_path.exists():
        guide = json.loads(guide_path.read_text(encoding="utf-8"))
        add("lstm_guidebook_repro_f1", round(guide["f1"], 4), protocol="guidebook_reproduction_pytorch",
            unit="f1", note="이상 라벨로 문턱 선택; 주 비교표와 다른 프로토콜")

    for r in cells[(cells.vib_high == False) & (cells.wave == "broken")].itertuples():  # noqa: E712
        add(f"abnormal_low_vibration_broken_wave_detected@{r.split}", int(r.abnormal_detected),
            unit="segments", denominator=int(r.abnormal_segments), source="interaction_2x2.csv")

    workload_path = out / "workload.csv"
    if workload_path.exists():
        workload = pd.read_csv(workload_path)
        selected = workload[(workload.calibration_unit == "recording_segments")
                            & (workload.criterion == "conformal") & (workload.alpha == 0.01)]
        for r in selected.itertuples():
            add(f"alerts_per_recorded_hour_conformal_1pct@{r.split}", round(float(r.alerts_per_recorded_hour), 3),
                unit="alerts/hour", basis="recorded time = 0.1s × rows", split=r.split)

    D.dump_json(numbers, out / "numbers.json")
    return {"numbers_items": len(numbers["items"])}
