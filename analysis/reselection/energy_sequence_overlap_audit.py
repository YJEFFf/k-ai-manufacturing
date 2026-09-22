"""Independent exact-sequence overlap audit, not a predictive performance score."""
from pathlib import Path
import zipfile,json
import pandas as pd
import numpy as np

with zipfile.ZipFile('/tmp/kamp_contest_energy.zip') as z:
    d=pd.read_csv(z.open(next(n for n in z.namelist() if n.endswith('.csv'))))
bad=d.loc[~d['시간'].between(0,23),'날짜'].unique()
d=d[~d['날짜'].isin(bad)]
base=pd.to_datetime(d['날짜'].astype(str))+pd.to_timedelta(d['시간'],unit='h')
y=pd.concat([pd.Series(d[c].values,index=base+pd.to_timedelta(m,unit='m')) for c,m in zip(['15분','30분','45분','60분'],[15,30,45,60])]).sort_index().asfreq('15min')
result=[]
for length in [4,8,16,24,48,96]:
    w=np.lib.stride_tricks.sliding_window_view(y.to_numpy(),length)
    valid=np.isfinite(w).all(axis=1)
    times=y.index[length-1:]
    hashes=pd.util.hash_pandas_object(pd.DataFrame(w),index=False).to_numpy()
    for start,end in [('2021-05-01','2021-06-01'),('2021-06-01','2021-07-01'),('2021-07-01','2021-08-01'),('2021-08-01','2021-09-15')]:
        tr=valid&(times<pd.Timestamp(start))
        te=valid&(times>=pd.Timestamp(start))&(times<pd.Timestamp(end))
        seen=set(hashes[tr]);matches=sum(h in seen for h in hashes[te])
        result.append({'window_points_including_target':length,'start':start,'test_windows':int(te.sum()),'exact_window_seen_in_training':matches,'fraction':matches/int(te.sum())})
out=Path(__file__).resolve().parent/'energy_vision'/'independent_sequence_overlap.json'
out.write_text(json.dumps(result,indent=2))
print(pd.DataFrame(result).round(4).to_string(index=False))
