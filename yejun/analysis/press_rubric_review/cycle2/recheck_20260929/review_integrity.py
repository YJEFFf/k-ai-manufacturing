"""검수 기록의 연결·문법·수치와 제품 보존을 확인한다. 제품을 실행/수정하지 않는다."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
REL = HERE.relative_to(REPO).as_posix() + "/"
REVIEW_HEAD = "be0c8b224f1fe4732056ff7979b798abc9153567"
PRODUCT_HEAD = "cc1aac2e24f4ed9f954b0f7b76db06021be02afd"
OUT = HERE / "review_integrity.json"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    checks = []
    tracked_changes = git("diff", "--name-only", REVIEW_HEAD, "--").splitlines()
    outside = [p for p in tracked_changes if not p.startswith(REL)]
    checks.append(dict(check="no_tracked_change_outside_review_folder", ok=not outside, paths=outside))
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    unexpected = [p for p in untracked if not p.startswith(REL)]
    checks.append(dict(check="no_untracked_change_outside_review_folder", ok=not unexpected, paths=unexpected))
    claude_diff = git("diff", "--name-only", PRODUCT_HEAD, REVIEW_HEAD, "--").splitlines()
    only_prior_review = all(p.startswith("yejun/analysis/press_rubric_review/cycle2/adversarial/") for p in claude_diff)
    checks.append(dict(check="claude_commit_only_added_review", ok=only_prior_review, files=len(claude_diff)))

    original_snapshot = json.loads((HERE / "scoring_docs_audit.json").read_text())["source_sha256"]
    mismatches = [p for p, expected in original_snapshot.items()
                  if not (REPO / p).is_file() or sha(REPO / p) != expected]
    checks.append(dict(check="audited_sources_and_inputs_unchanged", ok=not mismatches,
                       files=len(original_snapshot), mismatches=mismatches))
    probe_snapshot = json.loads((HERE / "model_stats_results.json").read_text())["source_hashes_before"]
    mismatches2 = [p for p, expected in probe_snapshot.items()
                   if sha(REPO / "yejun" / p) != expected]
    checks.append(dict(check="model_probe_sources_and_artifacts_unchanged", ok=not mismatches2,
                       files=len(probe_snapshot), mismatches=mismatches2))

    known = {
        "yejun/press_guard/artifacts/guard_A.json": "c938707f1dd16e7c239b8053e7f032d8fac828d6c753de2b898ba9130a594f10",
        "yejun/press_guard/artifacts/guard_B.json": "b64ac3b30bc697034104287964f3154e88c8a50749ccdec04f6d4f8744fd6969",
        "yejun/press_guard/artifacts/probability_A.json": "1a8100e78046393d9292fc7c305b5ec57b46c4e2c73b03abeb596052a8705f8a",
        "yejun/press_guard/artifacts/probability_B.json": "7fde4cd1bdfa74e78e2d3f07c5dbd9c27619e19b2e94ceb8fab786c27abcaae8",
        "yejun/press_guard/outputs/test_predictions_A.csv": "2941bf9dde2c9b66308eb6e26d19e4a41f93de1441833c8b476e0534e47e98c8",
        "yejun/press_guard/outputs/test_predictions_B.csv": "9bd02a7cf086ad9ff81542166c2af768aefee944d4385e343a2d771d8a2f5524",
    }
    state = {p: dict(expected=h, actual=sha(REPO / p)) for p, h in known.items()}
    checks.append(dict(check="round4_models_and_predictions_preserved",
                       ok=all(v["expected"] == v["actual"] for v in state.values()), files=state))

    syntax_errors = []
    scripts = sorted(HERE.glob("*.py"))
    for p in scripts:
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
        except SyntaxError as exc:
            syntax_errors.append(dict(file=p.name, error=str(exc)))
    checks.append(dict(check="review_scripts_parse", ok=not syntax_errors, files=len(scripts), errors=syntax_errors))
    json_errors = []
    for p in sorted(HERE.glob("*.json")):
        if p == OUT:
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"), parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
        except ValueError as exc:
            json_errors.append(dict(file=p.name, error=str(exc)))
    checks.append(dict(check="review_json_strict_parse", ok=not json_errors, errors=json_errors))
    broken = []
    link_count = 0
    for p in sorted(HERE.glob("*.md")):
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", p.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "#")):
                continue
            link_count += 1
            target = target.split("#", 1)[0]
            resolved = (p.parent / target).resolve()
            if resolved != OUT and not resolved.exists():
                broken.append(dict(file=p.name, target=target))
    checks.append(dict(check="review_document_links", ok=not broken, links=link_count, broken=broken))

    numeric_json = json.loads((HERE / "probability_review.json").read_text())["results"]
    numeric_csv = pd.read_csv(HERE / "probability_review.csv")
    expected = pd.DataFrame(numeric_json)
    equal_columns = list(expected.columns) == list(numeric_csv.columns)
    numeric_ok = equal_columns and len(expected) == len(numeric_csv)
    if numeric_ok:
        for c in expected.columns:
            if pd.api.types.is_numeric_dtype(expected[c]):
                numeric_ok &= bool(np.allclose(expected[c], numeric_csv[c], rtol=1e-12, atol=1e-14))
            else:
                numeric_ok &= expected[c].equals(numeric_csv[c])
    checks.append(dict(check="probability_csv_json_consistent", ok=bool(numeric_ok), rows=len(expected)))

    files = {p.name: dict(bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(HERE.iterdir())
             if p.is_file() and p != OUT}
    result = dict(product_commit=PRODUCT_HEAD, reviewed_commit=REVIEW_HEAD,
                  observed_head=git("rev-parse", "HEAD"),
                  scope="Review-only. No full product test suite was rerun in this review.",
                  all_ok=all(c["ok"] for c in checks), checks=checks,
                  review_files_excluding_this_self_referential_output=files)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for c in checks:
        print(("PASS " if c["ok"] else "FAIL ") + c["check"])
    print(f"{sum(c['ok'] for c in checks)}/{len(checks)}; review files: {len(files)}")
    if not result["all_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
