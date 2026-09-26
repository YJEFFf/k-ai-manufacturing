"""Read-only source/artifact/manifest audit for the reproducibility rubric."""
from pathlib import Path
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
SUPPLEMENT = YEJUN / "analysis" / "press_supplement"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    results = {}
    for experiment in ("e1", "e2", "e3"):
        manifest = json.loads((SUPPLEMENT / f"{experiment}_manifest.json").read_text())
        code = {n: sha(SUPPLEMENT / n) == v for n, v in manifest["code_sha256"].items()}
        artifacts = {
            n: sha(YEJUN / "press_guard" / "artifacts" / n) == v
            for n, v in manifest.get("artifacts", {}).items()
        }
        results[experiment] = {
            "declared_code_hashes_match": code,
            "declared_artifact_hashes_match": artifacts,
            "manifest_keys": sorted(manifest),
            "output_hash_contract_present": any(k in manifest for k in ("outputs", "output_hashes", "output_sha256")),
            "shared_dependency_hash_contract_present": any(k in manifest for k in ("dependency_hashes", "base_code_sha256", "source_hashes")),
            "environment": manifest["environment"],
            "current_output_hashes_for_review_only": {
                p.name: sha(p) for p in sorted(SUPPLEMENT.glob(f"{experiment}_*.csv"))
            },
        }
    old_protocol = subprocess.check_output(
        ["git", "show", "a102ecf:yejun/analysis/press_supplement/protocol.json"], cwd=YEJUN
    )
    results["protocol_matches_preregistered_commit"] = hashlib.sha256(old_protocol).hexdigest() == sha(SUPPLEMENT / "protocol.json")
    results["current_guard_hashes"] = {
        f"guard_{sid}.json": sha(YEJUN / "press_guard" / "artifacts" / f"guard_{sid}.json")
        for sid in ("A", "B")
    }
    results["source_input_hashes"] = {
        p.name: sha(p) for p in sorted((YEJUN / "press_submission" / "data" / "3_소성가공_예지보전").glob("*.csv"))
    }
    results["uci_hash_matches_e2_manifest"] = sha(YEJUN / "analysis" / "press_external" / "data" / "hydraulic.zip") == json.loads((SUPPLEMENT / "e2_manifest.json").read_text())["uci_sha256"]
    results["review_scope"] = "Listed hashes and contract presence, not full E1/E2/E3 numerical reruns."
    (HERE / "judge06_hash_audit.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in results.items() if k not in ("e1", "e2", "e3")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
