"""Inspect downloaded archives without expanding them on disk.

Cloud-only files and incomplete downloads remain explicitly unverified.
Run again after iCloud has materialized more files.
"""
from pathlib import Path
import collections
import hashlib
import json
import time
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = next(p for p in ROOT.iterdir() if unicodedata.normalize('NFC', p.name) == '데이터셋')


def main():
    prior_path = OUT / 'archive_checks.json'
    prior = {r['path']: r for r in json.loads(prior_path.read_text())} if prior_path.exists() else {}
    records = []
    for p in sorted(DATA.iterdir()):
        if p.suffix.lower() not in {'.zip', '.egg', '.crdownload'}:
            continue
        st = p.stat()
        rel = str(p.relative_to(ROOT))
        row = {'path': rel, 'bytes': st.st_size, 'mtime_ns': st.st_mtime_ns,
               'cloud_only': bool(st.st_flags & 0x40000000)}
        old = prior.get(rel, {})
        if old.get('status') == 'zip_crc_all_pass' and old.get('mtime_ns') == st.st_mtime_ns and old.get('bytes') == st.st_size:
            records.append(old)
            continue
        if row['cloud_only']:
            row['status'] = 'cloud_pending'
        elif not st.st_size:
            row['status'] = 'empty_file'
        else:
            with p.open('rb') as f:
                row['header_hex'] = f.read(100).hex()
            if row['header_hex'].startswith('45474741'):
                row['status'] = 'egg_format_requires_reader'
            else:
                try:
                    with zipfile.ZipFile(p) as z:
                        row['members'] = []
                        for info in z.infolist():
                            item = {'name': info.filename, 'bytes': info.file_size,
                                    'compressed_bytes': info.compress_size, 'crc32': info.CRC}
                            if not info.is_dir():
                                digest = hashlib.sha256()
                                read_bytes = 0
                                with z.open(info) as f:
                                    while chunk := f.read(1024 * 1024):
                                        digest.update(chunk)
                                        read_bytes += len(chunk)
                                item.update(sha256=digest.hexdigest(), bytes_read=read_bytes, crc_checked=True)
                            row['members'].append(item)
                        row['status'] = 'zip_crc_all_pass'
                        row['uncompressed_bytes'] = sum(i.file_size for i in z.infolist())
                except Exception as exc:
                    row['status'] = 'archive_error'
                    row['error'] = f'{type(exc).__name__}: {exc}'
        row['checked_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        records.append(row)
        prior_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(p.name, row['status'], flush=True)
    prior_path.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(json.dumps(dict(collections.Counter(r['status'] for r in records)), ensure_ascii=False))


if __name__ == '__main__':
    main()
