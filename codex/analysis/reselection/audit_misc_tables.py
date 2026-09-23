"""Read every table in available secondary archives; retain counts and schemas."""
from pathlib import Path
import collections
import io
import json
import unicodedata
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
DATA = next(p for p in ROOT.iterdir() if unicodedata.normalize('NFC', p.name) == '데이터셋')
TERMS = ['Dataset_Meltingtank', '전자부품(배터리팩) 품질보증', '열처리 품질보증',
         '열처리 공정최적화', '의류 품질보증']


def summarize_chunks(chunks):
    count, missing, columns = 0, collections.Counter(), []
    labels = {}
    for df in chunks:
        count += len(df)
        columns = [str(c) for c in df.columns]
        missing.update({str(k): int(v) for k, v in df.isna().sum().items()})
        for c in df.columns:
            if str(c).lower() in {'label', 'passorfail', 'quality'} or '양품' in str(c) or '불량' in str(c):
                labels.setdefault(str(c), collections.Counter()).update({str(k): int(v) for k, v in df[c].value_counts(dropna=False).items()})
    return {'rows': count, 'columns': columns, 'missing': dict(missing),
            'label_counts': {k: dict(v) for k, v in labels.items()}}


def read_csv_complete(z, member):
    """Try complete decodes; an ASCII header does not establish UTF-8 encoding."""
    last_error = None
    for enc in ('utf-8-sig', 'cp949'):
        try:
            with z.open(member) as f:
                result = summarize_chunks(pd.read_csv(
                    f, encoding=enc, chunksize=100_000, low_memory=False))
            return dict(result, encoding=enc)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error


def main():
    rows = []
    for p in DATA.iterdir():
        if p.suffix != '.zip' or not any(t in p.name for t in TERMS):
            continue
        if p.stat().st_flags & 0x40000000:
            rows.append({'archive': p.name, 'status': 'cloud_pending'})
            continue
        with zipfile.ZipFile(p) as z:
            for member in z.infolist():
                name = member.filename
                ext = Path(name).suffix.lower()
                if ext not in {'.csv', '.xlsx', '.txt'}:
                    continue
                r = {'archive': p.name, 'member': name, 'bytes': member.file_size}
                try:
                    if ext == '.csv':
                        r.update(read_csv_complete(z, member))
                    elif ext == '.xlsx':
                        sheets = pd.read_excel(io.BytesIO(z.read(member)), sheet_name=None)
                        r['sheets'] = {k: summarize_chunks([v]) for k, v in sheets.items()}
                    else:
                        b = z.read(member)
                        try:
                            r['text'] = b.decode('utf-8-sig')
                        except UnicodeDecodeError:
                            r['text'] = b.decode('cp949', errors='replace')
                    r['status'] = 'all_rows_parsed'
                except Exception as exc:
                    r.update(status='parse_error', error=f'{type(exc).__name__}: {exc}')
                rows.append(r)
                (OUT / 'misc_table_profiles.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
                print(p.name, name, r['status'], r.get('rows', ''), flush=True)
    print('DONE', len(rows))


if __name__ == '__main__':
    main()
