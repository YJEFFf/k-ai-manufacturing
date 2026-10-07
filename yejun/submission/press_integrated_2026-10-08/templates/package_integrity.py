"""Check immutable distribution files before running any experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify_package():
    manifest = json.loads((ROOT / "package_manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["immutable_files_sha256"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f"Missing or invalid package file: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Package file changed: {relative}")
    return dict(passed=True, checked_files=len(manifest["immutable_files_sha256"]),
                original_selection_lock_sha256=manifest["original_selection_lock_sha256"],
                packaged_selection_lock_sha256=manifest["packaged_selection_lock_sha256"],
                calculation_ast_equivalent=manifest["calculation_ast_equivalent"])


if __name__ == "__main__":
    print(json.dumps(verify_package(), ensure_ascii=False, indent=2))
