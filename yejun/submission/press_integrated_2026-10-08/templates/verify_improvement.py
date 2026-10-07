"""Compare regenerated improvement tables to the frozen reference tables."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
STUDY = ROOT / "yejun/analysis/press_improvement"


def main():
    reference = ROOT / "reference_results/improvement"
    actual = STUDY / "outputs"
    checks = []
    manifest = json.loads((ROOT / "package_manifest.json").read_text(encoding="utf-8"))
    declared = set(manifest["improvement_reference_csv_files"])
    found = {path.name for path in reference.glob("*.csv")}
    assert declared and found == declared, "Missing or unexpected reference tables"
    for source in sorted(reference.glob("*.csv")):
        expected = pd.read_csv(source)
        result = pd.read_csv(actual / source.name)
        pd.testing.assert_frame_equal(result, expected, check_dtype=False, check_exact=False,
                                      rtol=1e-9, atol=1e-11)
        checks.append(dict(file=source.name, rows=len(expected), columns=len(expected.columns), passed=True))
    assert len(checks) == len(declared)
    expected_selection = json.loads((reference / "selection.json").read_text(encoding="utf-8"))
    actual_selection = json.loads((actual / "selection.json").read_text(encoding="utf-8"))
    expected_config = json.loads((reference / "config.json").read_text(encoding="utf-8"))
    actual_config = json.loads((actual / "config.json").read_text(encoding="utf-8"))
    assert actual_config == expected_config, "Frozen retained-candidate protocol changed"
    for field in ("selected", "normal_only", "abnormal_read", "candidates", "gate_pass_selectable"):
        assert actual_selection[field] == expected_selection[field], field
    result = dict(passed=True, selected=actual_selection["selected"], csv_checks=checks,
                  retained_protocol_equal=True,
                  rtol=1e-9, atol=1e-11,
                  scope="Independent regeneration of existing results; not a new independent failure dataset")
    (actual / "reference_comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
