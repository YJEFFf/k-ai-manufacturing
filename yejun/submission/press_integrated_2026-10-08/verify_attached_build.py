"""Check that the final archive equals the executed archive except for the attached run records.

    python verify_attached_build.py --run 북적북적_code_통합본_run.zip --final 북적북적_code_통합본.zip

Every member of the executed archive must exist in the final archive with identical bytes, except
package_manifest.json (it gains verification_basis and the record hashes). The final archive may add only
verification/*.json, and its manifest must name the executed archive's SHA-256.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def members(path):
    with zipfile.ZipFile(path) as handle:
        return {info.filename: hashlib.sha256(handle.read(info)).hexdigest() for info in handle.infolist() if not info.is_dir()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    args = parser.parse_args()
    run_zip, final_zip = (HERE / args.run).resolve(), (HERE / args.final).resolve()
    run, final = members(run_zip), members(final_zip)
    manifest_name = next(name for name in final if name.endswith("/package_manifest.json"))
    changed = sorted(name for name in run if name != manifest_name and final.get(name) != run[name])
    added = sorted(set(final) - set(run))
    assert not changed, f"Executed files changed: {changed[:5]}"
    assert added and all("/verification/" in name and name.endswith(".json") for name in added), added
    with zipfile.ZipFile(final_zip) as handle:
        manifest = json.loads(handle.read(manifest_name))
    run_sha = hashlib.sha256(run_zip.read_bytes()).hexdigest()
    assert manifest["verification_basis"]["run_archive_sha256"] == run_sha
    result = dict(passed=True, run_archive=run_zip.name, run_archive_sha256=run_sha,
                  final_archive=final_zip.name, final_archive_sha256=hashlib.sha256(final_zip.read_bytes()).hexdigest(),
                  identical_members=len(run) - 1, added_members=added,
                  note="Only package_manifest.json and the attached run records differ; all executed files are byte-identical.")
    (HERE / "verification_final" / "attached_build_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
