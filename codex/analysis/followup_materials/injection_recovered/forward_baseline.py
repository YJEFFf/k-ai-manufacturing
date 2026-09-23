"""Fixed baselines on restored physical measurements with chronological tests."""
from pathlib import Path
import json, math
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler,OneHotEncoder
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score,precision_recall_fscore_support,roc_auc_score

HERE=Path(__file__).parent

def metrics(y,s,dates):
    y=np.asarray(y,dtype=int);s=np.asarray(s);pred=s>=.5
    p,r,f,_=precision_recall_fscore_support(y,pred,average='binary',zero_division=0)
    result={'n':len(y),'positive':int(y.sum()),'prevalence':float(y.mean()),'AP':float(average_precision_score(y,s)) if y.sum() else None,
        'precision_at_0_5':float(p),'recall_at_0_5':float(r),'f1_at_0_5':float(f),'flagged_at_0_5':int(pred.sum()),'inspection_budgets':{}}
    for quota in (.1,.2,.3):
        chosen=[]
        for date in sorted(set(dates)):
            ix=np.flatnonzero(np.asarray(dates)==date);order=np.argsort(-s[ix],kind='stable');chosen.extend(ix[order[:math.ceil(quota*len(ix))]].tolist())
        result['inspection_budgets'][str(quota)]={'selected':len(chosen),'positive_found':int(y[chosen].sum()),'recall':float(y[chosen].sum()/y.sum()) if y.sum() else None,
            'random_expected_positive':float(sum(y[np.asarray(dates)==day].sum()*math.ceil(quota*sum(np.asarray(dates)==day))/sum(np.asarray(dates)==day) for day in set(dates)))}
    return result

def main():
    d=pd.read_csv(HERE/'labeled_unique_with_metadata.csv',keep_default_na=False)
    d=d[d.PART_NAME.str.startswith(('CN7','RG3'))].copy()
    d['product']=d.PART_NAME.str[:3];d['date']=d.TimeStamp.str[:10]
    d=d.sort_values(['TimeStamp','PART_NAME','_id']).reset_index(drop=True)
    sensors=list(d.columns[d.columns.get_loc('Injection_Time'):d.columns.get_loc('Mold_Temperature_12')+1])
    splits={
       'original_contest_period_to_all_later':(d.date<='2020-10-23',d.date>'2020-10-23'),
       'past_to_november':(d.date<='2020-10-30',d.date>='2020-11-03'),
       'rg3_oct22_to_oct23':((d['product']=='RG3')&(d.date<='2020-10-22'),(d['product']=='RG3')&(d.date=='2020-10-23')),
    }
    records=[];predictions=[]
    for split,(train,test) in splits.items():
        a,b=d[train],d[test];feat=[c for c in sensors if a[c].nunique()>1]
        check={'train_n':len(a),'train_positive':int(a.y.sum()),'test_n':len(b),'test_positive':int(b.y.sum()),
               'train_dates':sorted(a.date.unique()),'test_dates':sorted(b.date.unique()),
               'id_overlap':len(set(a._id)&set(b._id)),
               'shot_time_overlap':len(set(zip(a.EQUIP_CD,a.TimeStamp))&set(zip(b.EQUIP_CD,b.TimeStamp)))}
        group_rate=a.groupby('PART_NAME').y.mean();scores=b.PART_NAME.map(group_rate).fillna(a.y.mean()).to_numpy()
        records.append({'split':split,'model':'part_name_prior','inputs':'known part name only','integrity':check,'all':metrics(b.y,scores,b.date)})
        for include_part in (False,True):
            for name in ('LR','RF','HGB'):
                transformers=[('sensors',StandardScaler(),feat)]
                if include_part:transformers.append(('part',OneHotEncoder(handle_unknown='ignore',sparse_output=False),['PART_NAME']))
                prep=ColumnTransformer(transformers)
                if name=='LR':est=LogisticRegression(C=.1,class_weight='balanced',max_iter=2000,random_state=42)
                elif name=='RF':est=RandomForestClassifier(n_estimators=300,min_samples_leaf=3,max_features=.7,class_weight='balanced',random_state=42,n_jobs=2)
                else:est=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=10,class_weight='balanced',random_state=42)
                model=make_pipeline(prep,est);model.fit(a,a.y);s=model.predict_proba(b)[:,1]
                rec={'split':split,'model':name,'inputs':'physical_sensors+part_name' if include_part else 'physical_sensors', 'integrity':check,
                     'all':metrics(b.y,s,b.date),'by_product':{},'by_date':{}}
                for p in b['product'].unique():
                    ix=(b['product']==p).to_numpy();rec['by_product'][p]=metrics(b.y[ix],s[ix],b.date[ix])
                for date in sorted(b.date.unique()):
                    ix=(b.date==date).to_numpy();rec['by_date'][date]=metrics(b.y[ix],s[ix],b.date[ix])
                # Sensitivity excludes the 10 explicitly marked startup-allowance failures,
                # without relabelling them or choosing the model on this subset.
                ix=(b.Reason!='초기허용불량').to_numpy();rec['excluding_startup_allowance']=metrics(b.y[ix],s[ix],b.date[ix])
                records.append(rec)
                for row,score in zip(b.itertuples(),s):predictions.append({'split':split,'model':name,'part_input':include_part,'id':str(d.loc[row.Index,'_id']),
                    'date':row.date,'part':row.PART_NAME,'y':int(row.y),'probability':float(score)})
                print(split,name,include_part,rec['all'],flush=True)
    (HERE/'forward_baseline_results.json').write_text(json.dumps({'protocol':'Fixed models; exact duplicate records removed first; TimeStamp dates split before fitting; Reason/ERR_FACT_QTY/id/time/serial are never predictor inputs; no test tuning',
         'records':records},ensure_ascii=False,indent=2))
    pd.DataFrame(predictions).to_csv(HERE/'forward_predictions.csv',index=False)

if __name__=='__main__':main()
