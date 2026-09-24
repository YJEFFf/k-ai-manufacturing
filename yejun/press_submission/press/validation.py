"""단계별 필수 검사·산출물 계약. 실행기와 검증기가 같은 완료 기준을 사용한다."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


RESULTS_BY_STEP = {
    1: {"diagnosis.json", "waveform_segments.csv", "preprocess_effect.csv", "splits.csv"},
    2: {"conformal_mc.csv", "model_comparison.csv", "operating_points.csv", "tail_params.csv", "thresholds_main.csv"},
    3: {"sensitivity.csv", "sensitivity_params.csv", "quantization_frozen.csv", "ablation.csv", "label_bypass.csv",
        "segment_features.csv", "error_conditions_fn.csv", "error_conditions_fp.csv", "alarm_components.csv",
        "influence.csv", "interaction_2x2.csv"},
    4: {"uncertainty.csv", "lstm_guidebook_history.csv", "lstm_guidebook_reproduction.json",
        "lstm_common_history_A.csv", "lstm_common_history_B.csv", "lstm_common_meta.csv",
        "model_comparison_lstm.csv", "model_comparison_all.csv"},
    5: {"workload.csv", "persistence.csv", "load_normalization.csv", "load_normalization_meta.csv"},
}
OTHER_OUTPUTS_BY_STEP = {
    1: {"diagnosis.md", "fig_current_waveform.png", "fig_segment_length.png"},
    2: {"predictions_A.csv", "predictions_B.csv", "records_main_A.csv", "records_main_B.csv",
        "model_comparison.md", "model_comparison_cutoff.md"},
    3: {"fig_vibration_vs_waveform.png", "fig_recall_by_position.png", "fig_error_examples.png"},
    4: {"model_comparison_all.md"},
    5: {"numbers.json", "field_decision_table.md"},
}
CHECKS_BY_STEP = {
    1: {"segments_equal_vendor_blocks", "diagnosis_generated", "outputs_free_of_raw_sensor_columns"},
    2: {"conformal_mc_within_4se", "step2_all_ok"},
    3: {"step3_label_bypass_ok"},
}
INPUT_CHECKS = {"input_hash_ok", "input_rows_ok", "segment_counts_ok"}
SPLIT_CHECKS = {"stream_equals_evaluation", "shuffle_invariant", "prediction_alarm_counts_equal_table",
                "conformal_p_equals_threshold_alarms"}
RUNTIME_ARGS = {"root", "out", "artifacts", "retrain_lstm"}


def validate_steps(steps: int) -> int:
    if type(steps) is not int or steps not in range(1, 6):
        raise ValueError("steps는 1~5의 정수여야 한다")
    return steps


def _through_step(by_step: dict, steps: int) -> set[str]:
    validate_steps(steps)
    return set().union(*(values for stage, values in by_step.items() if stage <= steps))


def result_names(steps: int) -> set[str]:
    return _through_step(RESULTS_BY_STEP, steps)


def output_names(steps: int) -> set[str]:
    return result_names(steps) | _through_step(OTHER_OUTPUTS_BY_STEP, steps)


def required_check_names(steps: int, verify_inputs: bool = True) -> set[str]:
    return _through_step(CHECKS_BY_STEP, steps) | (INPUT_CHECKS if verify_inputs else set())


def check_required(checks: dict, steps: int, *, verify_inputs: bool = True, summary: bool = True) -> list[str]:
    """항목이 없거나 True가 아니면 실패. 요약 플래그만으로 개별 검사 누락을 통과시키지 않는다."""
    bad = [k for k in sorted(required_check_names(steps, verify_inputs)) if checks.get(k) is not True]
    if steps >= 2:
        splits = checks.get("step2", {})
        for sid in ("A", "B"):
            values = splits.get(sid, {}) if isinstance(splits, dict) else {}
            for key in sorted(SPLIT_CHECKS):
                if not isinstance(values, dict) or values.get(key) is not True:
                    bad.append(f"step2.{sid}.{key}")
    if summary:
        if checks.get("required_checks_ok") is not True:
            bad.append("required_checks_ok")
        if checks.get("required_checks_failed") != []:
            bad.append("required_checks_failed")
    return bad


def declared_steps(manifest: dict, checks: dict) -> int:
    steps = validate_steps(checks.get("steps_run"))
    if int(manifest.get("args", {}).get("steps", 0)) != steps:
        raise ValueError("manifest.args.steps와 checks.steps_run이 일치하지 않는다")
    return steps


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_files(out: Path, manifest: dict, names: set[str]) -> list[str]:
    """실행 시 기록한 해시와 실제 파일을 대조한다. 예측값·숫자·checks도 포함한다."""
    hashes = manifest.get("outputs", {})
    bad = []
    for name in sorted(names):
        path = out / name
        if not path.is_file():
            bad.append(f"{name}: 없음")
        elif name not in hashes:
            bad.append(f"{name}: manifest 해시 없음")
        elif file_hash(path) != hashes[name]:
            bad.append(f"{name}: 실행 후 내용 변경")
    return bad


def run_fingerprint(code_hash: str, args: dict, inputs: dict, environment: dict) -> str:
    """같은 코드의 설정·입력·환경 차이를 식별한다. 저장 경로와 캐시 사용 여부는 제외한다."""
    payload = {"code_sha256": code_hash,
               "config": {k: str(v) for k, v in args.items() if k not in RUNTIME_ARGS},
               "inputs": {k: v["sha256"] for k, v in inputs["files"].items()},
               "environment": environment}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
