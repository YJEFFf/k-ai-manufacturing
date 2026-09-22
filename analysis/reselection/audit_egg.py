"""CRC-check EGG members in memory, using inspected parser only for headers.

Parser source: https://github.com/jinyeong-park/unegg-egg-file-extractor
No archive paths are executed or extracted. Partial members remain invalid.
"""
from pathlib import Path
import collections
import hashlib
import json
import sys
import unicodedata
import zlib

sys.path.insert(0, '/tmp/kamp-unegg-reader')
import unegg

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATA = next(p for p in ROOT.iterdir() if unicodedata.normalize('NFC', p.name) == '데이터셋')


def audit(p):
    rows = []
    with p.open('rb') as f:
        unegg.parse_archive_header(f)
        entries = unegg.scan_entries(f, p.stat().st_size)
        scan_end = f.tell()
        for i, e in enumerate(entries):
            row = vars(e).copy()
            if not e.file_length:
                row['status'] = 'empty_entry'
                rows.append(row)
                continue
            if e.is_encrypted or e.compress_method not in (0, 1):
                row['status'] = 'unsupported'
                rows.append(row)
                continue
            if e.block_data_offset + e.compressed_size > p.stat().st_size:
                row['status'] = 'truncated_member'
                rows.append(row)
                continue
            crc, size = 0, 0
            digest = hashlib.sha256()
            decoder = zlib.decompressobj(-15) if e.compress_method == 1 else None
            f.seek(e.block_data_offset)
            remaining = e.compressed_size
            try:
                while remaining:
                    chunk = f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise EOFError('incomplete compressed bytes')
                    remaining -= len(chunk)
                    raw = decoder.decompress(chunk) if decoder else chunk
                    crc = zlib.crc32(raw, crc)
                    size += len(raw)
                    digest.update(raw)
                if decoder:
                    raw = decoder.flush()
                    crc = zlib.crc32(raw, crc)
                    size += len(raw)
                    digest.update(raw)
                    if not decoder.eof:
                        raise EOFError('deflate stream not complete')
                row.update(bytes_read=size, actual_crc32=crc & 0xffffffff, sha256=digest.hexdigest())
                row['status'] = 'crc_pass' if size == e.file_length and (crc & 0xffffffff) == e.crc32 else 'crc_or_size_mismatch'
            except Exception as exc:
                row.update(status='read_error', error=str(exc))
            rows.append(row)
            if i % 2000 == 0:
                print(p.name, i, len(entries), flush=True)
    result = {'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size,
              'scan_end': scan_end, 'counts': dict(collections.Counter(r['status'] for r in rows)),
              'members': rows}
    (OUT / (p.stem + '.egg_crc.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(p.name, result['counts'], flush=True)


if __name__ == '__main__':
    audit(next(DATA.glob('*.egg')))
    audit(DATA / '미확인 32652.crdownload')
