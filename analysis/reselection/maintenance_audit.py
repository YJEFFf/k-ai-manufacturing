"""Read-only audit of maintenance candidates; never extracts archives to disk.

Run with /tmp/kamp-review-venv/bin/python analysis/reselection/maintenance_audit.py
Skip macOS dataless files until iCloud supplies their contents.
"""
from pathlib import Path
import json
import zipfile
import unicodedata
import hashlib
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = next(p for p in ROOT.iterdir() if p.is_dir() and unicodedata.normalize('NFC',p.name) == '데이터셋')
OUT = Path(__file__).with_suffix('.json')
KEYS = ['소성가공 예지보전', '회전기계', 'Mixer', 'Drier', 'FordEngine', 'Press', '기계부품', '장비이상 조기탐지', '열처리 예지보전', '로봇용접 예지보전']

def serial(x):
    if isinstance(x, (np.integer, np.floating)): return x.item()
    if isinstance(x, np.ndarray): return x.tolist()
    return str(x)

def profile(df):
    nums = df.select_dtypes(include='number')
    real = df.drop(columns=[c for c in df if c.startswith('Unnamed:')], errors='ignore')
    features = real.drop(columns=[c for c in real if 'time' in c.lower() or 'date' in c.lower()], errors='ignore')
    ans = {
        'shape':list(df.shape), 'columns':list(df.columns),
        'missing':df.isna().sum().to_dict(), 'nunique':df.nunique(dropna=False).to_dict(),
        'duplicate_full_rows':int(df.duplicated().sum()),
        'duplicate_excluding_index_timestamp':int(features.duplicated().sum()),
        'numeric_summary':nums.describe().to_dict(),
        'small_cardinality_values':{c:df[c].value_counts(dropna=False).to_dict() for c in df if df[c].nunique() <= 15},
        'head':df.head(3).to_dict(orient='records'), 'tail':df.tail(3).to_dict(orient='records'),
    }
    for col in [c for c in df if 'time' in c.lower() or 'date' in c.lower()]:
        t = pd.to_datetime(df[col].astype(str).str.strip(),errors='coerce')
        if t.notna().mean()>.9:
            ans.setdefault('timestamps',{})[col] = {'min':str(t.min()),'max':str(t.max()),'unique':int(t.nunique()),'monotonic':bool(t.is_monotonic_increasing),'steps_seconds_top':t.diff().dt.total_seconds().value_counts().head(10).to_dict(),'date_counts':t.dt.date.astype(str).value_counts().sort_index().to_dict()}
    return ans

def main():
    result={'candidates':[], 'limitations':[]}
    for p in DATA.glob('*.zip'):
        if not any(k in p.name for k in KEYS): continue
        st=p.stat()
        rec={'path':str(p.relative_to(ROOT)),'bytes':st.st_size,'dataless':bool(st.st_flags & 0x40000000)}
        result['candidates'].append(rec)
        if rec['dataless'] or not rec['bytes']:
            rec['status']='unavailable_local_content'; continue
        print('READ',p.name,flush=True)
        with zipfile.ZipFile(p) as z:
            rec['members']=[{'name':i.filename,'bytes':i.file_size} for i in z.infolist()]
            frames={}
            for i in z.infolist():
                if not i.filename.lower().endswith(('.csv','.txt','.tsv')): continue
                if '__MACOSX' in i.filename: continue
                if i.file_size > 350_000_000:
                    rec.setdefault('skipped_members',[]).append(i.filename); continue
                for enc in ['utf-8-sig','cp949','latin1']:
                    try:
                        with z.open(i) as f:
                            df=pd.read_csv(f,encoding=enc)
                        break
                    except UnicodeDecodeError: continue
                if df.shape[1]==1 and ('Ford' in p.name):
                    with z.open(i) as f: df=pd.read_csv(f,sep=r'\s+',header=None)
                    df.columns=['label']+[f'x{k}' for k in range(1,len(df.columns))]
                rec.setdefault('tables',{})[i.filename]=profile(df)
                if '기계부품' in p.name: frames[i.filename]=df
                print(i.filename,df.shape,flush=True)
            if '기계부품' in p.name and len(frames)==2:
                raw=next(v for k,v in frames.items() if 'raw_total' in k)
                exercise=next(v for k,v in frames.items() if '실습' in k)
                cols=[c for c in exercise if c in raw]
                rawff=raw[cols].ffill()
                equal=(rawff.eq(exercise[cols]) | (rawff.isna() & exercise[cols].isna()))
                rec['raw_to_exercise']={'forward_fill_equal_cells':int(equal.to_numpy().sum()),'compared_cells':int(equal.size),'not_equal_columns':{k:int(v) for k,v in (~equal).sum().items() if v}, 'raw_missing_total':int(raw.isna().to_numpy().sum()),'exercise_missing_total':int(exercise.isna().to_numpy().sum())}
                y=exercise['MAIN_MOTOR_ALM.xlsx'].ne(0)
                group=y.ne(y.shift()).cumsum()
                episodes=[{'first_row':int(a.index[0]),'last_row':int(a.index[-1]),'rows':len(a),'start':a.Timestamp.iloc[0],'end':a.Timestamp.iloc[-1]} for _,a in exercise[y].groupby(group[y])]
                rec['alarm_proxy_caution']={'target':'MAIN_MOTOR_ALM.xlsx != 0','positive_rows':int(y.sum()),'episodes':episodes,'identical_other_alarm_flags':[c for c in ['KO1_MOTOR_INVERTER_ALM.xlsx','CUTTING_INVERTER_ALM_ERR_CD.xlsx'] if ((exercise[c]==8995)==y).all()], 'chronological_last_20_percent':{'rows':len(y.iloc[int(len(y)*.8):]),'positive_rows':int(y.iloc[int(len(y)*.8):].sum())}}
        rec['status']='read_and_profiled'
        OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=serial))
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=serial))

if __name__ == '__main__': main()
