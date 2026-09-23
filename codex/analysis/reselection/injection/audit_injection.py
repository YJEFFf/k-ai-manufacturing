"""Read-only archive/table audit. Run with /tmp/kamp-review-venv/bin/python.

Cloud placeholders are skipped. ZIPs are read in memory; originals never edited.
"""
from pathlib import Path
import io, json, zipfile, unicodedata, hashlib, struct, zlib
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
DATA = next(p for p in ROOT.iterdir() if unicodedata.normalize('NFC', p.name) == '데이터셋')
KEYS = ['Molding', 'Machinevision', '사출성형 예지보전', '생산공정 최적화',
        '소성가공 품질보증', '주조 설비 예지보전', '주조 품질보증', '사출성형 공급망', 'Investment_Casting']

def csv_read(b):
    for enc in ['utf-8-sig', 'cp949', 'latin1']:
        try:
            return pd.read_csv(io.BytesIO(b), encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue

def profile(df):
    r = dict(shape=list(df.shape), columns=list(df.columns), dtypes={k:str(v) for k,v in df.dtypes.items()},
             missing={k:int(v) for k,v in df.isna().sum().items() if v},
             unique={k:int(v) for k,v in df.nunique(dropna=False).items()},
             duplicate_rows=int(df.duplicated().sum()), head=df.head(3).replace({np.nan:None}).to_dict('records'))
    r['small_value_counts'] = {k: {str(a):int(b) for a,b in df[k].value_counts(dropna=False).items()}
                               for k in df if df[k].nunique(dropna=False) <= 20}
    r['numeric_summary'] = df.select_dtypes('number').describe().replace({np.nan:None}).to_dict()
    return r

def contents(label, blob, report):
    ext = Path(label).suffix.lower()
    if ext == '.csv':
        try: report['tables'][label] = profile(csv_read(blob))
        except Exception as e: report['errors'][label] = repr(e)
    elif ext in ['.xlsx', '.xls'] and not Path(label).name.startswith('~$'):
        try:
            for name,df in pd.read_excel(io.BytesIO(blob), sheet_name=None).items():
                report['tables'][label+'::'+name] = profile(df)
        except Exception as e: report['errors'][label] = repr(e)
    elif ext == '.zip':
        archive(label, io.BytesIO(blob), report)

def archive(label, source, report):
    try:
        with zipfile.ZipFile(source) as z:
            report['archives'][label] = [dict(name=i.filename, bytes=i.file_size, compressed=i.compress_size,
                crc=i.CRC) for i in z.infolist()]
            for i in z.infolist():
                if i.is_dir():continue
                if Path(i.filename).suffix.lower() in ['.zip','.csv','.xlsx','.xls']:
                    if i.file_size < 250_000_000:
                        contents(label+'!'+i.filename, z.read(i), report)
                    else:report['errors'][label+'!'+i.filename] = 'Over 250 MB; use streaming follow-up'
    except Exception as e:report['errors'][label] = repr(e)

def recover_local_headers(path):
    """Inspect headers in truncated ZIP; only decompress complete CRC-valid members."""
    b=path.read_bytes(); pos=0; recovered=[]
    while pos+30 <= len(b) and b[pos:pos+4]==b'PK\x03\x04':
        h=struct.unpack_from('<IHHHHHIIIHH',b,pos)
        _,ver,flag,method,mtime,mdate,crc,csize,usize,flen,xlen=h
        name=b[pos+30:pos+30+flen].decode('utf-8' if flag&2048 else 'cp437',errors='replace')
        start=pos+30+flen+xlen; end=start+csize
        entry=dict(name=name,expected_bytes=usize,compressed=csize,available_compressed=max(0,min(csize,len(b)-start)),complete=end<=len(b),flag=flag)
        if entry['complete'] and not flag&8:
            try:
                raw=zlib.decompress(b[start:end],-15) if method==8 else b[start:end]
                entry['crc_ok']=zlib.crc32(raw)==crc
                if entry['crc_ok'] and name.lower().endswith('.csv'):
                    entry['table']=profile(csv_read(raw))
            except Exception as e:entry['error']=repr(e)
        elif not entry['complete'] and method==8 and name.lower().endswith('.csv'):
            # Diagnostic only: salvaged prefix has no valid whole-member CRC.
            try:
                dec=zlib.decompressobj(-15)
                raw=dec.decompress(b[start:])
                raw=raw[:raw.rfind(b'\n')+1]
                df=csv_read(raw)
                entry['partial_table_unverified']=profile(df)
                entry['partial_decompressed_bytes']=len(raw)
                if 'No_Shot' in df:
                    entry['partial_zero_shot_rows']=int((df.No_Shot==0).sum())
                features=[c for c in df if c not in ['No_Shot','_ID']]
                entry['partial_duplicate_sensor_rows']=int(df[features].duplicated().sum())
            except Exception as e:entry['partial_error']=repr(e)
        recovered.append(entry)
        if flag&8 or end>len(b):break
        pos=end
    return recovered

def main():
    report=dict(archives={}, tables={}, errors={}, files=[], truncated_local_headers={})
    for f in DATA.iterdir():
        if f.suffix.lower() not in ['.zip','.csv'] or not any(k in unicodedata.normalize('NFC',f.name) for k in KEYS):continue
        s=f.stat(); rec=dict(name=f.name, bytes=s.st_size, cloud=bool(s.st_flags&0x40000000));report['files'].append(rec)
        print(f.name,rec,flush=True)
        if rec['cloud']:continue
        rec['sha256']=hashlib.sha256(f.read_bytes()).hexdigest()
        if f.suffix=='.zip':
            archive(f.name,f,report)
            if f.name in report['errors']:
                report['truncated_local_headers'][f.name]=recover_local_headers(f)
        else:contents(f.name,f.read_bytes(),report)
    (OUT/'archive_table_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print('Tables',[(k,v['shape']) for k,v in report['tables'].items()],flush=True)
    print('Errors',report['errors'],flush=True)

if __name__=='__main__':main()
