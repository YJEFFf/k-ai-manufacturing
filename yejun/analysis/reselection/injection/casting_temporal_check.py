"""Additional dataset 53 temporal diagnostic; NOT a contest-task-1 score."""
from pathlib import Path
import json, unicodedata
import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, confusion_matrix

ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
DATA=next(p for p in ROOT.iterdir() if unicodedata.normalize('NFC',p.name)=='데이터셋')
d=pd.read_csv(DATA/'Investment_Casting.csv')
r={'dataset':53, 'note':'Additional metal casting data; not original task-1 performance.',
   'rows':len(d),'missing_target':int(d.PassOrFail.isna().sum())}
d=d[d.PassOrFail.notna()].copy()
d['dt']=pd.to_datetime(d.timestamp+' '+d.date)
d=d.sort_values('dt')
dates=sorted(d.timestamp.unique())
r['date_span']=[dates[0],dates[-1]]
r['dates']=len(dates)
r['daily']=d.groupby('timestamp').PassOrFail.agg(['size','sum','mean']).to_dict('index')
features=[c for c in d.select_dtypes('number') if c not in ['production_count','PassOrFail'] and d[c].nunique()>1]
r['sensor_duplicate_rows']=int(d[features].duplicated().sum())
r['features']=features
r['checks']=[]
for train_fraction,test_end in [(0.5,0.75),(0.75,1.0)]:
    train_dates=dates[:int(len(dates)*train_fraction)]
    test_dates=dates[int(len(dates)*train_fraction):int(len(dates)*test_end)]
    tr=d.timestamp.isin(train_dates);te=d.timestamp.isin(test_dates)
    htr=set(pd.util.hash_pandas_object(d.loc[tr,features],index=False))
    hte=pd.util.hash_pandas_object(d.loc[te,features],index=False)
    split={'train_span':[train_dates[0],train_dates[-1]],'test_span':[test_dates[0],test_dates[-1]],
           'train_rows':int(tr.sum()),'test_rows':int(te.sum()),'train_defects':int(d.loc[tr,'PassOrFail'].sum()),
           'test_defects':int(d.loc[te,'PassOrFail'].sum()),'test_sensor_seen_train':int(hte.isin(htr).sum()),'models':{}}
    for key,cols in [('all_process',features),('without_strength_thickness',[c for c in features if c not in ['mechanical_strength','biscuit_thickness']])]:
        model=HistGradientBoostingClassifier(max_iter=150,max_leaf_nodes=15,min_samples_leaf=30,
            l2_regularization=1,random_state=2026,early_stopping=False)
        model.fit(d.loc[tr,cols],d.loc[tr,'PassOrFail'])
        p=model.predict_proba(d.loc[te,cols])[:,1]; pred=(p>=0.5).astype(int); y=d.loc[te,'PassOrFail']
        split['models'][key]={'average_precision':average_precision_score(y,p),'f1_at_0_5':f1_score(y,pred),
            'precision_at_0_5':precision_score(y,pred,zero_division=0),'recall_at_0_5':recall_score(y,pred),
            'confusion_matrix':confusion_matrix(y,pred).tolist()}
    r['checks'].append(split)
(OUT/'casting_temporal_check.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,default=str))
print(json.dumps({k:v for k,v in r.items() if k!='daily'},ensure_ascii=False,indent=2))
