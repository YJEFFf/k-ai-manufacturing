"""Full reads of 2/9/11/18 recovered archives, without extracting archives."""
from pathlib import Path
import zipfile,io,json,hashlib
import pandas as pd,numpy as np
OUT=Path(__file__).resolve().parent;CACHE=Path('/tmp/kamp-followup-cache');out={}
def dprofile(d):
 return {'rows':len(d),'columns':list(d.columns),'missing_cells':int(d.isna().sum().sum()),'full_row_duplicates':int(d.duplicated().sum()),'nunique':{str(c):int(v) for c,v in d.nunique().items()}}
for ident,pat in [(2,'02.*zip'),(9,'09.*zip'),(11,'11.*zip'),(18,'*회전기계*zip')]:
 p=next(CACHE.glob(pat));r={'archive':str(p),'files':{}};out[str(ident)]=r
 with zipfile.ZipFile(p) as z:
  r['crc_bad_member']=z.testzip()
  for info in z.infolist():
   name=info.filename
   if ident==2 and (name.endswith('.txt') or name.endswith('.arff')) and ('TRAIN' in name or 'TEST' in name):
    raw=z.read(name)
    if b'\x00' in raw:
     r['files'][name]={'status':'invalid_embedded_nulls','bytes':len(raw),'nul_bytes':raw.count(b'\x00'),'first_nul_byte':raw.find(b'\x00')};continue
    if name.endswith('.arff'):
     import re
     body=re.split(r'@data\s*',raw.decode(),flags=re.IGNORECASE,maxsplit=1)[1];d=pd.read_csv(io.StringIO(body),header=None);d=pd.concat([d.iloc[:,-1],d.iloc[:,:-1]],axis=1);d.columns=range(d.shape[1])
    else:
     arr=np.fromstring(raw.decode(),sep=' ');assert len(arr)%501==0;d=pd.DataFrame(arr.reshape(-1,501))
    x=d.iloc[:,1:];q=dprofile(d);q['file_linefeeds']=raw.count(b'\n');q['labels']=d.iloc[:,0].value_counts().to_dict();q['row_mean_abs_max']=float(x.mean(axis=1).abs().max());q['row_std_population_minmax']=[float(x.std(axis=1,ddof=0).min()),float(x.std(axis=1,ddof=0).max())]
    q['signal_hashes']=[hashlib.sha256(np.asarray(row,dtype='<f8').tobytes()).hexdigest() for row in x.to_numpy()];r['files'][name]=q
   elif name.endswith('.csv'):
    data=z.read(name)
    for enc in ['utf-8-sig','cp949']:
     try:d=pd.read_csv(io.BytesIO(data),encoding=enc,header=None if ident==18 else 0);break
     except UnicodeDecodeError:pass
    q=dprofile(d);q['encoding']=enc
    if 'Date' in d:
     q['date_minmax']=[str(d.Date.min()),str(d.Date.max())];q['date_groups']=int(d.Date.nunique());q['date_group_sizes']=d.groupby('Date').size().value_counts().to_dict()
     if 'Quality' in d:q['quality_counts']=d.Quality.value_counts().to_dict();q['mixed_quality_dates']=int((d.groupby('Date').Quality.nunique()>1).sum());q['quality_by_day']=pd.crosstab(d.Date.astype(str).str[:10],d.Quality).to_dict('index');q['abs_sensor_over2_label_mismatches']=int(((d.Sensor.abs()>2)!=(d.Quality=='FAILED')).sum())
     if 'Sensor' in d:
      hashes=[(str(k),hashlib.sha256(np.asarray(v.Sensor,dtype='<f8').tobytes()).hexdigest()) for k,v in d.groupby('Date',sort=False)];q['unique_date_waveforms']=len(set(v for _,v in hashes));q['date_waveform_hashes']=dict(hashes)
    elif ident==18:
     q['first_last']=d.iloc[[0,-1]].to_dict('records');q['numeric_minmax']={str(c):[float(d[c].min()),float(d[c].max())] for c in d.select_dtypes('number')}
    r['files'][name]=q
 tr=set(r['files'].get('dataset/FordA_TRAIN.arff',{}).get('signal_hashes',[]));te=r['files'].get('dataset/FordA_TEST.arff',{}).get('signal_hashes',[])
 if ident==2:r['exact_train_test_signal_overlap']=sum(v in tr for v in te)
 if ident==11:
  fs=list(r['files'].values());a=set(fs[0].get('date_waveform_hashes',{}).values());b=list(fs[1].get('date_waveform_hashes',{}).values());r['cross_file_equal_waveforms']=sum(v in a for v in b)
 (OUT/'supplemental_signal_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda x:int(x)))
 print(ident,{k:{kk:vv for kk,vv in v.items() if kk in ['rows','missing_cells','labels','quality_counts','date_groups','date_group_sizes','unique_date_waveforms','mixed_quality_dates']} for k,v in r['files'].items()},flush=True)
