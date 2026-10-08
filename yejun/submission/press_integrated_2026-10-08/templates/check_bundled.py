"""설치 없이 하는 빠른 확인(파이썬 표준 라이브러리만 사용, 수 초).

    python check_bundled.py

1. package_manifest.json의 파일 해시로 배포 파일이 바뀌지 않았는지 확인한다.
2. 동봉한 공식 test 예측 파일(reference_results/official_predictions/)의 해시를 expected_results.json과 대조한다.
3. 같은 파일의 label과 경보 열로 행 F1을 다시 계산해 보고서 값(expected_results.json)과 대조한다.
모델을 다시 학습하거나 예측을 다시 만들지 않는다. 전체 재현은 run_all.py로 한다.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PRED = ROOT / "reference_results" / "official_predictions"
# 보고서 이름 ↔ 예측 파일 열 ↔ 기대값 파일의 모델 이름
COLUMNS = (("1단계 잠금 모델 v2+R1(공식 성능)", "locked_v2_R1_realtime", "v2+H1"),
           ("2단계 모델 v2+R1+R2", "final_v2_R1_R2_realtime", "v2+H1+H2"),
           ("기반 모델 v2(R1 없음)", "v2_realtime", "v2"))


def utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def lf_sha256(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def truthy(value):
    return value.strip() in ("1", "True", "true")


def row_f1(path, column):
    tp = fp = fn = 0
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            label, alarm = truthy(row["label"]), truthy(row[column])
            tp += label and alarm
            fp += (not label) and alarm
            fn += label and not alarm
    return (2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0), tp, fp, fn


def main():
    utf8_console()
    failures = []
    manifest = json.loads((ROOT / "package_manifest.json").read_text(encoding="utf-8"))
    changed = [rel for rel, expected in manifest["immutable_files_sha256"].items()
               if not (ROOT / rel).is_file() or hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != expected]
    print(f"[1] 배포 파일 해시: {len(manifest['immutable_files_sha256']) - len(changed)}/{len(manifest['immutable_files_sha256'])} 일치")
    failures += [f"파일 변경: {rel}" for rel in changed]

    expected = json.loads((ROOT / "expected_results.json").read_text(encoding="utf-8"))["checks"]
    for check in expected:
        if check["kind"] == "sha256" and check["file"].startswith("predictions/"):
            path = PRED / Path(check["file"]).name
            ok = path.is_file() and lf_sha256(path) == check["value"]
            print(f"[2] {check['name']}: {'일치' if ok else '불일치'}")
            if not ok:
                failures.append(check["name"])

    targets = {(c["where"]["split"], c["where"]["model"]): c["value"] for c in expected
               if c["kind"] == "csv" and c["file"].endswith("tvt_test.csv") and c["column"] == "f1"
               and c["where"].get("mode") == "realtime" and c["where"].get("alpha") == "0.01"}
    print("[3] 동봉 예측 파일로 다시 계산한 test 실시간 행 F1(A / B)")
    for label, column, model in COLUMNS:
        values = []
        for split in ("A", "B"):
            f1, tp, fp, fn = row_f1(PRED / f"test_predictions_{split}.csv", column)
            target = targets.get((split, model))
            ok = target is not None and abs(f1 - target) <= 1e-9
            values.append(f"{f1:.6f}(오경보 {fp}행·미탐 {fn}행){'' if ok else ' ≠ 보고값'}")
            if not ok:
                failures.append(f"{label} {split}")
        print(f"    {label}: " + " / ".join(values))

    if failures:
        print("확인 실패:", "; ".join(failures))
        raise SystemExit(1)
    print("모두 일치. 전체 재현(전처리→학습→예측→대조)은 run_all.py로 실행한다.")


if __name__ == "__main__":
    main()
