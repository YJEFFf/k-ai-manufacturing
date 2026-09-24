"""Re-audit the public contest ZIP without changing the user's local XLSX."""
from pathlib import Path
import collections
import hashlib
import io
import json
import zipfile
import pandas as pd

OUT = Path(__file__).parent
ZIP = Path('/tmp/kamp-contest-originals/8078.zip')


def main():
    result = {'source': 'https://www.kamp-ai.kr/contestNoticeDetail?CPT_NOTICE_SEQ=28',
              'attachment_id': 8078, 'members': []}
    with zipfile.ZipFile(ZIP) as z:
        for m in z.infolist():
            if m.is_dir():
                continue
            b = z.read(m)
            result['members'].append({'name': m.filename, 'bytes': len(b),
                                      'sha256': hashlib.sha256(b).hexdigest(), 'crc_pass': True})
            if m.filename.endswith('.xlsx'):
                frames = pd.read_excel(io.BytesIO(b), sheet_name=None)
    raw, labels = frames['Raw data'], frames['result']
    features = ['weld force(bar)', 'weld current(kA)', 'weld Voltage(v)', 'weld time(ms)']
    tuples = [tuple(row) for row in raw[features].to_numpy()]
    repeated_windows = {}
    for width in (27,):
        covered = set()
        seen = {}
        for start in range(len(raw) - width + 1):
            end = start + width
            # Never construct a window across a date boundary.
            dates = raw['working time'].iloc[start:end]
            if dates.nunique() != 1:
                continue
            key = tuple(tuples[start:end])
            if key in seen:
                covered.update(range(start, end))
            else:
                seen[key] = start
        repeated_windows[str(width)] = {'covered_later_rows': len(covered),
                                        'fraction_all_rows': len(covered) / len(raw)}
    result.update(
        sheets={k: {'rows': len(v), 'columns': list(v.columns)} for k, v in frames.items()},
        unique_sensor_vectors=len(set(tuples)),
        constant_columns=[c for c in raw if raw[c].nunique(dropna=False) == 1],
        raw_by_date={str(k): int(v) for k, v in raw.groupby('working time').size().items()},
        result_records=labels.to_dict('records'),
        defect_count_sum=int(labels['defect'].sum()),
        defect_sum_interpretation='sum of date/type counts, not verified unique defective products',
        repeated_window_rows=repeated_windows,
        sensor_stats=raw[features].describe().to_dict(),
        missing=raw.isna().sum().to_dict())
    (OUT / 'welding_fresh_audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print('rows',len(raw),'unique sensors',result['unique_sensor_vectors'],'defect count sum',result['defect_count_sum'])
    print(repeated_windows)


if __name__ == '__main__':
    main()
