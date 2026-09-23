"""Point-in-time features and explicit monthly train/calibration/test splits."""
from pathlib import Path
import hashlib
import io
import zipfile
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

QUARTERS=['15분','30분','45분','60분']


def load_energy(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        raw=z.read(next(n for n in z.namelist() if n.endswith('.csv')))
    d=pd.read_csv(io.BytesIO(raw))
    bad_dates=d.loc[~d['시간'].between(0,23),'날짜'].unique()
    good=d[~d['날짜'].isin(bad_dates)]
    base=pd.to_datetime(good['날짜'].astype(str),format='%Y%m%d')+pd.to_timedelta(good['시간'],unit='h')
    y=pd.concat([pd.Series(good[c].to_numpy(),index=base+pd.to_timedelta(m,unit='min'))
                 for c,m in zip(QUARTERS,[15,30,45,60])]).sort_index().asfreq('15min')
    assert y.index.is_unique
    seen=set();novel={}
    for day,rows in d.groupby('날짜',sort=True):
        sig=hashlib.sha256(rows[QUARTERS].to_numpy().tobytes()).hexdigest()
        novel[int(day)]=sig not in seen
        seen.add(sig)
    source_day=(y.index-pd.Timedelta(minutes=1)).strftime('%Y%m%d').astype(int)
    novel_mask=pd.Series([novel.get(day,False) for day in source_day],index=y.index)
    meta={'csv_sha256':hashlib.sha256(raw).hexdigest(),'raw_rows':len(d),
          'invalid_hour_dates':bad_dates.tolist(),'time_convention':'quarter columns are interval ends',
          'novel_day_definition':'first exact 96-value profile in original source dates; retrospective audit only'}
    return y,novel_mask,meta


def make_features(y,h):
    x=pd.DataFrame(index=y.index)
    for lag in sorted(set([h,h+1,h+2,h+3,h+4,h+8,h+12,h+24,96,97,192,672])):
        assert lag>=h
        x[f'lag_{lag}']=y.shift(lag)
    for window in [4,16,96]:
        rolling=y.shift(h).rolling(window,min_periods=window)
        x[f'mean_{window}']=rolling.mean()
        x[f'max_{window}']=rolling.max()
        x[f'min_{window}']=rolling.min()
    x['hour']=y.index.hour;x['quarter']=y.index.minute//15
    x['weekday']=y.index.dayofweek;x['month']=y.index.month
    return x,y.notna()&x.notna().all(axis=1)


def month_folds(y,eligible,h):
    for month in range(5,10):
        start=pd.Timestamp(2021,month,1)
        end=pd.Timestamp(2021,month+1,1) if month<9 else pd.Timestamp('2021-09-15')
        cal_start=start-pd.DateOffset(months=1)
        train_end=cal_start-pd.Timedelta(minutes=15*h)
        cal_end=start-pd.Timedelta(minutes=15*h)
        train=eligible&(y.index<=train_end)
        cal=eligible&(y.index>=cal_start)&(y.index<=cal_end)
        test=eligible&(y.index>=start)&(y.index<end)
        assert not (train&cal).any() and not (cal&test).any()
        assert y.index[train].max()<=y.index[cal].min()-pd.Timedelta(minutes=15*h)
        assert y.index[cal].max()<=y.index[test].min()-pd.Timedelta(minutes=15*h)
        yield {'month':month,'test_start':str(start),'test_end_exclusive':str(end),
               'train_label_end':str(train_end),'calibration_start':str(cal_start),
               'calibration_label_end':str(cal_end),'train':train,'cal':cal,'test':test}


def alarm_threshold(scores,is_event,budget):
    """Strict > threshold; tied normal scores are never arbitrarily split."""
    normal=np.sort(np.asarray(scores)[~np.asarray(is_event,dtype=bool)])
    if not len(normal):raise ValueError('No calibration negatives')
    allowed=int(np.floor(budget*len(normal)))
    cutoff=float(normal[max(0,len(normal)-allowed-1)])
    assert np.mean(normal>cutoff)<=budget+1e-12
    return cutoff


def event_metrics(truth,pred,scores=None):
    truth=np.asarray(truth,dtype=bool);pred=np.asarray(pred,dtype=bool)
    tp=int((truth&pred).sum());fp=int((~truth&pred).sum())
    fn=int((truth&~pred).sum());tn=int((~truth&~pred).sum())
    result={'n':len(truth),'tp':tp,'fp':fp,'fn':fn,'tn':tn,
            'precision':tp/(tp+fp) if tp+fp else 0,
            'recall':tp/(tp+fn) if tp+fn else None,
            'fpr':fp/(fp+tn) if fp+tn else None,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,
            'alarm_rate':float(pred.mean()) if len(pred) else None}
    if scores is not None and len(np.unique(truth))==2:
        result['average_precision']=float(average_precision_score(truth,scores))
        result['roc_auc']=float(roc_auc_score(truth,scores))
    return result


def finite_sample_quantile(a,coverage):
    a=np.sort(np.asarray(a))
    k=min(len(a)-1,int(np.ceil((len(a)+1)*coverage))-1)
    return float(a[max(k,0)])
