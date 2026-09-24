"""③ 프레스 제출 패키지 — 한 명령 실행 (PLAN.md §7·§8).

    python run_all.py --root . --out outputs [--preprocess matched] [--no-verify]

1단계(현재): 데이터 검증·기록구간·분할·전처리 효과·진단·manifest·검사. 2단계 이후는 checks.json에 pending으로 표시한다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from press import data as D  # noqa: E402
from press import diagnosis  # noqa: E402
from press.artifact import Artifact  # noqa: E402

PENDING = ["scores_calibrate_evaluate(2단계)", "robustness_ablation_errors(3단계)", "baselines_lstm_uncertainty(4단계)",
           "field_persistence_evidence(5단계)", "freeze_env_clean_repro_zip(6단계)"]


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parent).stdout.strip()
    except Exception:
        return None


def scan_outputs_for_raw_values(out: Path) -> dict:
    """산출 CSV에 센서 원값 열이 없는지 확인한다(행 단위 원값은 Git 제외 대상)."""
    hits = {}
    for p in out.rglob("*.csv"):
        cols = pd.read_csv(p, nrows=0).columns.tolist()
        bad = [c for c in cols if c in D.SENSORS]
        if bad:
            hits[str(p.relative_to(out))] = bad
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=D.PACKAGE_DIR, help="data/3_소성가공_예지보전/ 를 포함하는 폴더")
    ap.add_argument("--out", type=Path, default=D.PACKAGE_DIR / "outputs")
    ap.add_argument("--artifacts", type=Path, default=None, help="기본: <out>/../artifacts")
    ap.add_argument("--preprocess", choices=list(D.QUANTIZATION), default="matched")
    ap.add_argument("--no-verify", action="store_true", help="입력 해시·행 수 검증을 건너뛴다(다른 자료로 실행할 때)")
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    art_dir = args.artifacts or out.parent / "artifacts"
    t0 = time.time()
    timings, checks = {}, {}

    # 1. 로드·검증
    normal, abnormal, load_report = D.load(args.root, verify=not args.no_verify)
    checks["input_hash_ok"] = all(v["sha256_ok"] for v in load_report["files"].values())
    checks["input_rows_ok"] = all(v["rows_ok"] for v in load_report["files"].values())
    status_n, status_a = D.validate_rows(normal), D.validate_rows(abnormal)
    seg_n, seg_a = D.segments(normal, status_n), D.segments(abnormal, status_a)
    vendor = D.load_vendor()
    checks["segments_equal_vendor_blocks"] = bool((seg_n == vendor.blocks(normal)).all() and (seg_a == vendor.blocks(abnormal)).all())
    checks["segment_counts"] = {"normal": int(len(np.unique(seg_n))), "abnormal": int(len(np.unique(seg_a)))}
    checks["segment_counts_ok"] = checks["segment_counts"] == D.EXPECTED_SEGMENTS if not args.no_verify else None
    checks["bad_rows"] = {"normal": int((status_n != "ok").sum()), "abnormal": int((status_a != "ok").sum())}
    timings["load_validate_s"] = round(time.time() - t0, 2)

    # 2. 분할
    rows = []
    for sid in D.SPLITS:
        sp = D.split_normal(normal, seg_n, sid)
        for part in ("train", "cal", "test"):
            rows.append(dict(split_id=sid, split=sp["name"], part=part, rows=len(sp[part]), segments=sp["segments"][part]))
        rows.append(dict(split_id=sid, split=sp["name"], part="abnormal_test", rows=len(abnormal), segments=int(len(np.unique(seg_a)))))
    splits = pd.DataFrame(rows)
    splits.to_csv(out / "splits.csv", index=False)
    checks["split_segment_counts"] = {sid: D.split_normal(normal, seg_n, sid)["segments"] for sid in D.SPLITS}

    # 3. 전처리 효과 (값이 바뀐 비율·평균 절대 변화). 주 전처리는 뒤 단계의 모든 모델에 동일 적용한다.
    eff = []
    for name in D.QUANTIZATION:
        for lab, df in (("normal", normal), ("abnormal", abnormal)):
            q = D.quantize(df, name)
            for c in D.SENSORS:
                diff = (q[c] - df[c]).abs().to_numpy()
                eff.append(dict(preprocess=name, set=lab, sensor=c, changed_fraction=float((diff > 0).mean()),
                                mean_abs_change=float(diff.mean()), max_abs_change=float(diff.max())))
    pd.DataFrame(eff).to_csv(out / "preprocess_effect.csv", index=False)
    timings["splits_preprocess_s"] = round(time.time() - t0 - timings["load_validate_s"], 2)

    # 4. 진단 (원본 기준; 주 전처리 후 형식 규칙 붕괴도 함께)
    t1 = time.time()
    numbers = diagnosis.run(out, args.root, normal, abnormal, seg_n, seg_a, status_n, status_a, args.preprocess)
    D.dump_json(numbers, out / "diagnosis.json")
    checks["diagnosis_generated"] = (out / "diagnosis.md").exists() and (out / "diagnosis.json").exists()
    rules_pre = pd.DataFrame(numbers[f"format_rules_{args.preprocess}"])
    checks["format_rules_after_preprocess_max_separability"] = float(rules_pre.separability.max())
    timings["diagnosis_s"] = round(time.time() - t1, 2)

    # 5. 산출물 계약 뼈대: 학습 상태 없는 artifact (2단계에서 state를 채운다)
    art = Artifact(model_id="skeleton_no_model", split="A", preprocess=args.preprocess, w=None,
                   input_sha256={k: v["sha256"] for k, v in load_report["files"].items()})
    art_path = art.save(art_dir / "skeleton.json")
    checks["artifact_roundtrip_ok"] = Artifact.load(art_path).model_id == art.model_id and not Artifact.load(art_path).trained

    # 6. 원값 유출 검사·manifest
    raw_hits = scan_outputs_for_raw_values(out)
    checks["outputs_free_of_raw_sensor_columns"] = not raw_hits
    checks["raw_column_hits"] = raw_hits
    checks["pending_steps"] = PENDING
    timings["total_s"] = round(time.time() - t0, 2)
    manifest = dict(protocol_version=D.PROTOCOL_VERSION, git_commit=git_commit(), args={k: str(v) for k, v in vars(args).items()},
                    environment=D.environment(), omp_num_threads=os.environ.get("OMP_NUM_THREADS"),
                    inputs=load_report, timings_s=timings,
                    outputs={str(p.relative_to(out)): D.sha256_file(p) for p in sorted(out.rglob("*")) if p.is_file() and p.name != "manifest.json"})
    D.dump_json(manifest, out / "manifest.json")
    D.dump_json(checks, out / "checks.json")
    print(json.dumps(D.to_jsonable(checks), ensure_ascii=False, indent=2))
    return checks


if __name__ == "__main__":
    main()
