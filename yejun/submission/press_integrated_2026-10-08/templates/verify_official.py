"""Recheck every original expected result against regenerated outputs."""
import argparse
import json
from pathlib import Path

from run_official import compare

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    rows = compare(args.quick)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    assert rows and all(row["ok"] for row in rows), "Original expected-result comparison failed"
