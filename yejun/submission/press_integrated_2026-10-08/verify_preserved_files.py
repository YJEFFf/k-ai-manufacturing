"""Check original submission, held report copies and the historical selection lock."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STUDY = ROOT / 'yejun/analysis/press_frontier_improvement_2026-10-08'


def main():
    manifest = json.loads((STUDY / 'source_manifest.json').read_text(encoding='utf-8'))
    review = json.loads((STUDY / 'review/claude_review_resolution_2026-10-08.json').read_text(encoding='utf-8'))
    checks = []
    for relative, expected in manifest['protected_files'].items():
        payload = (ROOT / relative).read_bytes()
        if relative.endswith('.md'):
            payload = payload.replace(b'\r\n', b'\n')
        actual = hashlib.sha256(payload).hexdigest()
        assert actual == expected, relative
        checks.append(dict(file=relative, sha256=actual, unchanged=True,
                           normalization='LF' if relative.endswith('.md') else 'none'))
    report_dir = ROOT / manifest['report_copy_dir']
    for suffix, key in (('.md', 'markdown'), ('.hwpx', 'hwpx'), ('.pdf', 'pdf')):
        candidates = [p for p in report_dir.iterdir() if p.suffix == suffix and p.name != 'README.md']
        assert len(candidates) == 1, [p.name for p in candidates]
        path = candidates[0]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == review['report_hashes_unchanged'][key]
        checks.append(dict(file=path.relative_to(ROOT).as_posix(), sha256=digest,
                           normalization='none', unchanged=True))
    sys.path.insert(0, str(STUDY))
    from run_experiment import verify_lock
    lock = verify_lock(STUDY / 'outputs/selection_lock.json')
    assert lock['lock_sha256'] == '20c992cd930c02c59f3ef4d3b7cccc1b15e2f3eda1fd78065fd06452a3c1ce2b'
    result = dict(passed=True, protected_files=checks, original_selection_lock=lock,
                  report_update_performed=False)
    target = HERE / 'verification/preserved_sources_and_reports.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, files=len(checks), selected=lock['selected'])))


if __name__ == '__main__':
    main()
