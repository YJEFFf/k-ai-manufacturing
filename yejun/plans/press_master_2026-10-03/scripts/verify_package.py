"""Check evidence, split contracts, links and optionally locally acquired bytes.

This validates the research package, not future model performance or field safety.
No network, model fitting, test performance inspection or raw-data modification.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
YEJUN = HERE.parents[1]


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    def reject(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-data", action="store_true", help="verify raw archives, acquisition metadata and local conflict mask")
    parser.add_argument("--with-source-caches", action="store_true", help="also verify the locally retained, dated source-page snapshots")
    args = parser.parse_args()
    checks, failures = [], []
    verified_paths = set()

    def check(name, condition):
        checks.append(name)
        if not condition:
            failures.append(name)

    def verify_file(path, expected_sha, size=None):
        check(f"exists: {path.relative_to(ROOT)}", path.is_file())
        if not path.is_file():
            return
        check(f"sha256: {path.relative_to(ROOT)}", digest(path) == expected_sha)
        if size is not None:
            check(f"bytes: {path.relative_to(ROOT)}", path.stat().st_size == size)
        verified_paths.add(str(path.relative_to(ROOT)))

    for path in sorted((HERE / "scripts").glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        check(f"Python syntax: {path.name}", True)
    for path in sorted((HERE / "evidence").glob("*.json")):
        read_json(path)
        check(f"JSON syntax: {path.name}", True)
    protocol = read_json(HERE / "protocol.json")
    for path in sorted(HERE.glob("*.md")):
        for link in re.findall(r"\[[^\]]*\]\(([^)\n]+)\)", path.read_text()):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link) or link.startswith("#"):
                continue
            target = link.split("#", 1)[0].strip("<>")
            check(f"link: {path.name} -> {target}", (path.parent / target).exists())

    press = read_json(HERE / "evidence/press_audit.json")
    for role, expected_records in [("normal", 599), ("abnormal", 21)]:
        row = press[role]
        lengths = {int(k): n for k, n in row["record_length_counts"].items()}
        check(f"{role}: row/record conservation", sum(lengths.values()) == expected_records and
              sum(length * count for length, count in lengths.items()) == row["retained_rows"])
        check(f"{role}: boundary rules agree", row["same_partition_after_dedup"] and
              row["records_strict"] == expected_records == row["records_gap500"])
        check(f"{role}: source hash agrees with protocol", row["sha256"] == protocol["input"][f"{role}_sha256"])
    expected_folds = {"P0": [81, 77, 157], "P1": [158, 157, 156], "P2": [316, 156, 126]}
    for fold, counts in expected_folds.items():
        rows = press["forward_folds"][fold]
        roles = [rows[name] for name in ["fit", "cal", "evaluation"]]
        check(f"{fold}: fold counts", [row["n_records"] for row in roles] == counts)
        check(f"{fold}: no record range overlap", all(a["last_id"] < b["first_id"] for a, b in zip(roles, roles[1:])))
    guide = press["historical_guide_windows"]
    for mode in ["window_only", "full_record_broadcast_retrospective"]:
        row = guide[mode]
        check(f"{mode}: F1 arithmetic", math.isclose(row["f1"], 2 * row["tp"] / (2 * row["tp"] + row["fp"] + row["fn"])))
    check("P0 cannot support 1% empirical tail", 1 / (expected_folds["P0"][1] + 1) > .01)
    check("scenario sample sizes are not augmented counts", math.ceil(math.log(.05) / math.log(.99)) == 299 and
          math.ceil(math.log(.05) / math.log(.9)) == 29)
    check("main candidates have eight fixed settings", sum(protocol["models"][key].get("settings", len(protocol["models"][key].get("k", protocol["models"][key].get("degree", [])))) for key in ["B1", "B2", "B3", "C1", "C2"]) == 8)
    check("calibration excludes augmentation", protocol["calibration"]["real_normal_only"] and not protocol["augmentation"]["calibration_augmented"])
    check("heldout seeds differ", not set(protocol["random_seeds"]) & set(protocol["augmentation"]["heldout_seeds"]))
    check("selection excludes test", protocol["selection"]["test_based_reselection"] is False)
    check("physical rate and units remain unknown", protocol["input"]["physical_sampling_rate"] is None and protocol["input"]["physical_sensor_units"] is None)

    skab_acq = read_json(HERE / "evidence/skab_acquisition.json")
    skab = read_json(HERE / protocol["external"]["skab_reservation"])
    assigned = {row["path"]: row for row in skab["files"]}
    check("SKAB covers exactly acquired CSVs", set(assigned) == {row["source_path"] for row in skab_acq["files"]} and len(assigned) == 35)
    check("SKAB revision agrees", skab["revision"] == skab_acq["revision"] == protocol["external"]["skab_revision"])
    group_roles = defaultdict(set)
    for row in assigned.values():
        group_roles[row["group_id"]].add(row["split"])
    check("SKAB groups do not cross splits", len(group_roles) == 30 and all(len(roles) == 1 for roles in group_roles.values()))
    check("SKAB split file counts recompute", dict(Counter(row["split"] for row in assigned.values())) == skab["split_file_counts"])
    for split, n in skab["split_group_counts"].items():
        check(f"SKAB {split} group count recomputes", sum(roles == {split} for roles in group_roles.values()) == n)
    for edge in skab["exact_overlap_edges"]:
        check(f"SKAB shared data grouped: {edge['a']} / {edge['b']}", assigned[edge["a"]]["group_id"] == assigned[edge["b"]]["group_id"])
    for a, b in skab["overlapping_time_edges"]:
        check(f"SKAB shared time grouped: {a} / {b}", assigned[a]["group_id"] == assigned[b]["group_id"])
    check("SKAB no old test released", all(assigned[row["source_path"]]["split"] == "test" for row in skab_acq["files"] if row["split"] == "test"))
    conflicts = read_json(HERE / "evidence/skab_label_consistency.json")
    check("SKAB conflict aggregates agree", conflicts["conflicting_shared_observations"] == 237 == sum(conflicts["conflicting_by_split"].values()) == sum(row["observations"] for row in conflicts["conflicting_by_source_set"]) and conflicts["conflicting_anomaly_observations"] == 235)
    check("SKAB calibration and decision unit agree", protocol["external"]["skab_unit"]["samples"] == 20 and not protocol["external"]["skab_unit"]["overlap"])

    esp = read_json(HERE / "evidence/espset_audit.json")
    esp_roles = read_json(HERE / protocol["external"]["espset_reservation"])["files"]
    ids = [row["esp_id"] for row in esp_roles]
    check("ESPset whole-unit reservation", len(set(ids)) == len(ids) == esp["unique_esp_ids"] == 11)
    check("ESPset deterministic ID order", ids == sorted(ids, key=lambda unit: hashlib.sha256(f"press-master-v1|{unit}".encode()).hexdigest()))
    check("ESPset roles 5/2/2/2", [row["split"] for row in esp_roles] == ["fit"] * 5 + ["dev"] * 2 + ["cal"] * 2 + ["test"] * 2)
    check("ESPset labels and IDs account for rows", sum(esp["label_counts"].values()) == esp["rows"] == 6032 and esp["duplicate_unit_sample_ids"] == 0)
    ext = read_json(HERE / "evidence/external_audit.json")
    inspected = [row for row in ext["beihang"]["files"] if "pairs" in row]
    check("Beihang one healthy run timing audit only", len(inspected) == 1 and "/Healthy state/1.csv" in inspected[0]["file"])
    pairs = {row["signal"]: row for row in inspected[0]["pairs"]}
    check("Beihang channel time axes are distinct", len(pairs) == 11 and pairs["X vibration"]["valid_pairs"] == 270509 and pairs["Speed"]["valid_pairs"] == 2704)
    check("Beihang pressure discrepancy retained", math.isclose(pairs["Output pressure"]["implied_rate_hz"], 3000, rel_tol=1e-4))

    sources = read_json(HERE / "evidence/source_receipts.json")
    check("source receipt counts support dated text", len(sources) == 29 and sum(row["status"] == 200 for row in sources) == 26)
    uci = read_json(HERE / "evidence/uci_acquisition.json")
    bei = read_json(HERE / "evidence/beihang_acquisition.json")
    esp_acq = read_json(HERE / "evidence/espset_acquisition.json")
    raw = [uci] + skab_acq["files"] + bei["files"] + esp_acq["files"]
    check("four-source acquired byte total", sum(row["bytes"] for row in raw) == 392712909)
    check("UCI checksum provenance is local, not publisher", not uci["publisher_hash_verified"] and uci["hash_basis"] == "prior local acquisition receipt")
    check("Mendeley publisher hashes recorded", all(row["publisher_hash_verified"] for row in bei["files"] + esp_acq["files"]))

    provenance = read_json(HERE / "evidence/provenance.json")
    for row in provenance["input_files"]:
        verify_file(ROOT / row["path"], row["sha256"], row["bytes"])
    if args.with_data:
        for row in raw + skab_acq["notices"] + [bei["metadata"], esp_acq["metadata"]]:
            verify_file(YEJUN / row["path"], row["sha256"], row["bytes"])
        for row in read_json(HERE / "evidence/nln_metadata_acquisition.json")["files"]:
            verify_file(HERE / row["path"], row["sha256"], row["bytes"])
        verify_file(HERE / conflicts["mask_path"], conflicts["mask_sha256"])
        mask = read_json(HERE / conflicts["mask_path"])
        check("regenerated row mask supports aggregates", len(mask) == 237 and sum(row["anomaly_conflict"] for row in mask) == 235)
        press_root = ROOT / "데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전"
        for role, name in [("normal", "press_data_normal.csv"), ("abnormal", "outlier_data.csv")]:
            verify_file(press_root / name, press[role]["sha256"])
    if args.with_source_caches:
        for row in sources:
            if row["status"] == 200:
                verify_file(HERE / row["local_cache"], row["sha256"], row["bytes"])

    rel = HERE.relative_to(ROOT)
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", str(rel)], cwd=ROOT, capture_output=True, text=True, check=True)
    package = sorted({ROOT / line for line in listed.stdout.splitlines()})
    check("raw data/cache excluded from Git candidates", all(not {"data", "cache", "__pycache__"} & set(path.relative_to(HERE).parts) for path in package))
    check("no large Git candidates", all(path.stat().st_size < 1_000_000 for path in package))
    aggregate = hashlib.sha256()
    for path in package:
        if path.name == "verification.json":
            continue
        aggregate.update(f"{path.relative_to(HERE)}\0{digest(path)}\n".encode())
    report = dict(status="pass" if not failures else "fail", checked_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  scope="Package consistency and acquired-byte checks only; not new detector/augmentation/external performance validation.",
                  python=platform.python_version(), with_local_data=args.with_data,
                  with_source_caches=args.with_source_caches,
                  checks=len(checks), failures=failures, verified_file_count=len(verified_paths),
                  package_sha256_excluding_this_report=aggregate.hexdigest(), check_names=checks)
    (HERE / "evidence/verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "check_names"}, ensure_ascii=False, indent=2))
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
