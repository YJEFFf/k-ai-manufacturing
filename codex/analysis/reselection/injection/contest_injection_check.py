"""Audit official contest fileSeq=8077; group-aware diagnostics, no ID predictors.

Input: /tmp/kamp_contest_8077_injection.zip, downloaded through official public
POST https://www.kamp-ai.kr/cptFileDownload with fileSeq=8077.
Metrics use class 1 as positive. Label semantics must be checked separately.
"""
from pathlib import Path
import hashlib, io, json, zipfile
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, confusion_matrix

OUT=Path(__file__).resolve().parent
ARCHIVE=Path('/tmp/kamp_contest_8077_injection.zip')

def metrics(y,p):
    y=np.asarray(y);p=np.asarray(p);pred=p>=.5
    r={'n':len(y),'class1':int(y.sum()),'average_precision':float(average_precision_score(y,p)) if y.sum() else None,
       'f1_at_0_5':float(f1_score(y,pred,zero_division=0)),
       'precision_at_0_5':float(precision_score(y,pred,zero_division=0)),
       'recall_at_0_5':float(recall_score(y,pred,zero_division=0)),
       'confusion_matrix':confusion_matrix(y,pred,labels=[0,1]).tolist()}
    for budget in [.05,.1,.2]:
        k=int(np.ceil(len(y)*budget));order=np.argsort(-p,kind='stable')
        r[f'recall_at_top_{int(budget*100)}pct_rows_tie_order_dependent']=float(y[order[:k]].sum()/y.sum()) if y.sum() else None
    return r

def models():
    return {'logistic_balanced':LogisticRegression(C=.1,class_weight='balanced',max_iter=2000),
            'rf_balanced':RandomForestClassifier(n_estimators=300,min_samples_leaf=3,max_features=.7,class_weight='balanced',random_state=2026,n_jobs=2),
            'hgb_balanced':HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=10,
                class_weight='balanced',l2_regularization=3,early_stopping=False,random_state=2026)}

def main():
    z=zipfile.ZipFile(ARCHIVE);r={'source':'https://www.kamp-ai.kr/cptFileDownload','fileSeq':8077,
        'zip_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),'zip_bytes':ARCHIVE.stat().st_size,
        'crc_test_bad_member':z.testzip(),'tables':{},'metrics_positive_class':1,'experiments':[]}
    tables={};all_labeled=[]
    for name in z.namelist():
        if not name.endswith('.csv'):continue
        b=z.read(name);d=pd.read_csv(io.BytesIO(b));short=Path(name).stem;tables[short]=d
        cols=[c for c in d if c not in ['Unnamed: 0','PassOrFail']]
        x=d[cols];h=pd.util.hash_pandas_object(x,index=False)
        p={'rows':len(d),'columns':list(d),'sha256':hashlib.sha256(b).hexdigest(),
           'missing_cells':int(d.isna().sum().sum()),'unique_sensor_rows':int(h.nunique()),
           'duplicate_sensor_rows':int(h.duplicated().sum()),'adjacent_identical_sensors':int((h==h.shift()).sum()),
           'group_size_frequencies':{str(k):int(v) for k,v in h.value_counts().value_counts().items()},
           'index_range':[int(d.iloc[:,0].min()),int(d.iloc[:,0].max())],
           'mean_by_sensor':x.mean().to_dict(),'population_std_by_sensor':x.std(ddof=0).to_dict()}
        if 'PassOrFail' in d:
            g=d.groupby(h).PassOrFail.agg(['size','sum','nunique'])
            p['label_counts']={str(k):int(v) for k,v in d.PassOrFail.value_counts().items()}
            p['conflicting_groups']=int((g['nunique']>1).sum())
            p['conflicting_rows']=int(g.loc[g['nunique']>1,'size'].sum())
            p['positive_groups']=int((g['sum']>0).sum())
            p['all_positive_groups']=int((g['sum']==g['size']).sum())
            # Exact upper bound for this pair structure: predict 1 for all groups containing any 1.
            oracle=(h.map(g['sum'])>0).astype(int)
            p['same_input_deterministic_full_sample_f1_upper_bound']=float(f1_score(d.PassOrFail,oracle))
            p['sensor_conflict_examples']=[]
            for group in g.index[g['nunique']>1][:4]:
                p['sensor_conflict_examples'].append(d.loc[h==group,['Unnamed: 0','PassOrFail']].to_dict('records'))
            d=d.copy();d['product']=short.rsplit('_',1)[-1];d['sensor_hash']=h.astype(str);all_labeled.append(d)
        r['tables'][short]=p
    d=pd.concat(all_labeled,ignore_index=True)
    features=[c for c in d if c not in ['Unnamed: 0','PassOrFail','product','sensor_hash'] and d[c].nunique()>1]
    x=d[features];y=d.PassOrFail.to_numpy();groups=d['product']+'_'+d.sensor_hash
    r['all_labeled']={'rows':len(d),'class1':int(y.sum()),'sensor_groups':int(groups.nunique()),'features':features}
    sgkf=StratifiedGroupKFold(n_splits=5,shuffle=True,random_state=2026)
    splits=list(sgkf.split(x,y,groups))
    for model_name in models():
        pred=np.zeros(len(d));folds=[]
        for tr,te in splits:
            model=models()[model_name];model.fit(x.iloc[tr],y[tr]);pred[te]=model.predict_proba(x.iloc[te])[:,1]
            folds.append({'train_groups':int(groups.iloc[tr].nunique()),'test_groups':int(groups.iloc[te].nunique()),
                'group_intersection':len(set(groups.iloc[tr])&set(groups.iloc[te])),**metrics(y[te],pred[te])})
        r['experiments'].append({'split':'5-fold stratified sensor-group split; not temporal validation',
            'model':model_name,'pooled':metrics(y,pred),'folds':folds,
            'by_product':{p:metrics(y[d['product']==p],pred[d['product']==p]) for p in ['cn7','rg3']}})
    for product in ['cn7','rg3']:
        sub=d.loc[d['product']==product].reset_index(drop=True)
        xx=sub[features];yy=sub.PassOrFail.to_numpy();gg=sub.sensor_hash
        psplits=list(StratifiedGroupKFold(n_splits=5,shuffle=True,random_state=2026).split(xx,yy,gg))
        for model_name in models():
            pp=np.zeros(len(sub));folds=[]
            for tr,te in psplits:
                model=models()[model_name];model.fit(xx.iloc[tr],yy[tr]);pp[te]=model.predict_proba(xx.iloc[te])[:,1]
                folds.append({'group_intersection':len(set(gg.iloc[tr])&set(gg.iloc[te])),**metrics(yy[te],pp[te])})
            r['experiments'].append({'split':f'{product} product-specific 5-fold sensor-group; not temporal',
                'model':model_name,'pooled':metrics(yy,pp),'folds':folds})
    # Different product: neither source-to-target adaptation nor test tuning.
    for source,target in [('cn7','rg3'),('rg3','cn7')]:
        tr=d['product']==source;te=d['product']==target
        for model_name,model in models().items():
            model.fit(x.loc[tr],y[tr]);p=model.predict_proba(x.loc[te])[:,1]
            r['experiments'].append({'split':f'product {source} -> {target}; each CSV independently standardized',
                'model':model_name,**metrics(y[te],p)})
    # Index-prefix holdout, sensor hashes crossing boundary removed from training.
    # Index order is not a timestamp and must not be called a future-date test.
    for product in ['cn7','rg3']:
        sub=d.loc[d['product']==product].sort_values('Unnamed: 0')
        cut=int(len(sub)*.7);train=sub.iloc[:cut];test=sub.iloc[cut:]
        train=train.loc[~train.sensor_hash.isin(test.sensor_hash)]
        for model_name,model in models().items():
            model.fit(train[features],train.PassOrFail)
            p=model.predict_proba(test[features])[:,1]
            r['experiments'].append({'split':f'{product} index-prefix70% -> suffix30%; chronology unverified',
                'model':model_name,'train_rows':len(train),'train_class1':int(train.PassOrFail.sum()),
                **metrics(test.PassOrFail,p)})
    (OUT/'contest_injection_check.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,default=str))
    print(json.dumps({'all_labeled':r['all_labeled'],'experiments':[
        {k:v for k,v in e.items() if k not in ['folds','by_product']} for e in r['experiments']]},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
