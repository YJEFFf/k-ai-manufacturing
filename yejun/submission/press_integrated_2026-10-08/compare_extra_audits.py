"""Compare fresh final-ZIP audit tables with the separately executed local audits."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'verification'


def main():
    run = json.loads((EVIDENCE / 'extra_audits_clean_run.json').read_text(encoding='utf-8'))
    assert run['status'] == 'passed' and run['returncode'] == 0
    build = json.loads((HERE / 'build_result.json').read_text(encoding='utf-8'))
    assert run['archive_sha256'] == build['zip_sha256'] == hashlib.sha256(Path(build['zip']).read_bytes()).hexdigest()
    actual_root = Path(run['extracted_root']) / 'yejun/analysis/press_improvement/outputs'
    source_root = HERE.parents[1] / 'analysis/press_frontier_improvement_2026-10-08/outputs'
    checks = []
    for subdir in ('strong_baselines', 'normal_sensitivity'):
        source_files = {p.name for p in (source_root / subdir).glob('*.csv')}
        actual_files = {p.name for p in (actual_root / subdir).glob('*.csv')}
        assert source_files and source_files == actual_files, (subdir, source_files ^ actual_files)
        for filename in sorted(source_files):
            source = source_root / subdir / filename
            actual = actual_root / subdir / filename
            expected_frame = pd.read_csv(source)
            actual_frame = pd.read_csv(actual)
            pd.testing.assert_frame_equal(actual_frame, expected_frame, check_dtype=False,
                                          check_exact=False, rtol=1e-9, atol=1e-11)
            checks.append(dict(file=f'{subdir}/{filename}', rows=len(actual_frame),
                               source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                               actual_sha256=hashlib.sha256(actual.read_bytes()).hexdigest(), passed=True))
    result = dict(passed=True, final_archive_sha256=run['archive_sha256'],
                  csv_files=len(checks), table_rows=sum(row['rows'] for row in checks),
                  checks=checks, rtol=1e-9, atol=1e-11,
                  scope='Fresh added-audit reproduction matches the earlier local execution; same existing inputs, not independent failure validation.')
    target = EVIDENCE / 'extra_audits_reference_comparison.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, csv_files=len(checks), table_rows=result['table_rows'])))


if __name__ == '__main__':
    main()
