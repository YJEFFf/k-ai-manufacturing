"""Full-table audit of recovered KAMP 50/51/52. No source modification."""
from pathlib import Path
import io,json,zipfile,hashlib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split,GroupShuffleSplit
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import precision_score,recall_score,f1_score,average_precision_score

OUT=Path(__file__).resolve().parent;CACHE=Path('/tmp/kamp-followup-cache')
FEATURES=['DV_R','DA_R','AV_R','AA_R','PM_R']
def tables(pattern):
 p=next(CACHE.glob(pattern));result={}
 with zipfile.ZipFile(p) as z:
  for n in z.namelist():
   if n.endswith('.csv'):result[n]=pd.read_csv(io.BytesIO(z.read(n)))
 return result
def profile(d,label,features,group=None):
 g=d.groupby(features,dropna=False)[label].agg(['size','nunique'])
 out={'rows':len(d),'columns':list(d.columns),'missing_cells':int(d.isna().sum().sum()),'label_counts':{str(k):int(v) for k,v in d[label].value_counts().items()},'full_row_duplicates':int(d.duplicated().sum()),'sensor_vector_unique':len(g),'sensor_vector_duplicate_rows':int(d[features].duplicated().sum()),'conflicting_sensor_groups':int((g['nunique']>1).sum()),'rows_in_conflicting_sensor_groups':int(g.loc[g['nunique']>1,'size'].sum()),'feature_ranges':{c:[float(d[c].min()),float(d[c].max()),int(d[c].nunique())] for c in features},'constant_columns':d.columns[d.nunique(dropna=False)<=1].tolist()}
 if group:
  q=d.groupby(group)[label].agg(['size','nunique','min','max'])
  out['groups']={'field':group,'n':len(q),'mixed_label_groups':int((q['nunique']>1).sum()),'row_count_quantiles':{str(k):float(v) for k,v in q['size'].quantile([0,.25,.5,.75,1]).items()},'all_negative_groups':int((q['max']==0).sum()),'all_positive_groups':int((q['min']==1).sum())}
 return out
def metrics(y,s):
 pred=s>=.5
 return {'n':len(y),'positive_n':int(np.asarray(y).sum()),'precision':float(precision_score(y,pred,zero_division=0)),'recall':float(recall_score(y,pred,zero_division=0)),'f1':float(f1_score(y,pred,zero_division=0)),'ap':float(average_precision_score(y,s)) if np.asarray(y).sum() else None}
out={}
d50=next(iter(tables('*정밀가공 품질보증*zip').values()));f50=[c for c in d50 if c not in ['SerialNo','ReceivedDateTime','passorfail']]
out['50']=profile(d50,'passorfail',f50,'SerialNo')
dates=pd.to_datetime(d50.ReceivedDateTime);days=dates.dt.strftime('%Y-%m-%d')
out['50']['dates']={str(k):{str(kk):int(vv) for kk,vv in v.items()} for k,v in d50.groupby(days).passorfail.value_counts().unstack(fill_value=0).to_dict('index').items()}
out['50']['timestamp_monotonic']=bool(dates.is_monotonic_increasing)
out['50']['benchmarks']=[]
splits=[('random_stratified',*train_test_split(np.arange(len(d50)),test_size=.3,stratify=d50.passorfail,random_state=42))]
unique_days=sorted(days.unique())
for day in unique_days[2:]:splits.append(('past_to_'+day,np.where(days<day)[0],np.where(days==day)[0]))
for label,tr,te in splits:
 if d50.iloc[tr].passorfail.nunique()<2:continue
 m=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,l2_regularization=1,random_state=42).fit(d50.iloc[tr][f50],d50.iloc[tr].passorfail)
 out['50']['benchmarks'].append({'split':label,'train_n':len(tr),'train_positive':int(d50.iloc[tr].passorfail.sum()),**metrics(d50.iloc[te].passorfail,m.predict_proba(d50.iloc[te][f50])[:,1])})

t51=tables('*용접 예지*zip');out['51']={}
for name,d in t51.items():
 r=profile(d,'FIN_JGMT',FEATURES,'PIPE_NO');r['duplicates_excluding_storage_index']=int(d.drop(columns=['Unnamed: 0'],errors='ignore').duplicated().sum())
 date=d.WK_DT.astype(str).str[:8];r['date_label_counts']=pd.crosstab(date,d.FIN_JGMT).to_dict('index');r['timestamp_unique']=int(d.WK_DT.nunique());r['timestamp_monotonic']=bool(d.WK_DT.is_monotonic_increasing)
 h=pd.util.hash_pandas_object(d[FEATURES],index=False).to_numpy();r['best_short_repeat_offsets']=sorted([{'offset':i,'equal_fraction':float(np.mean(h[i:]==h[:-i]))} for i in range(1,min(2001,len(h)))],key=lambda x:-x['equal_fraction'])[:10]
 r['most_common_sensor_vectors']=d.groupby(FEATURES).size().nlargest(5).reset_index(name='count').to_dict('records');out['51'][name]=r
n51=t51['data/normal_data.csv'];a51=t51['data/outlier_data.csv']
out['51']['single_feature_separation']={c:{'normal_min':float(n51[c].min()),'normal_max':float(n51[c].max()),'abnormal_min':float(a51[c].min()),'abnormal_max':float(a51[c].max()),'disjoint_range':bool(n51[c].min()>a51[c].max() or a51[c].min()>n51[c].max())} for c in FEATURES}

d52=next(iter(tables('*용접 공정*zip').values()));out['52']=profile(d52,'FIN_JGMT',FEATURES,'PIPE_NO')
# Defect-positive metrics, explicitly invert raw 1=good labels.
X=d52[FEATURES];y=1-d52.FIN_JGMT;groups=d52.PIPE_NO
idx=np.arange(len(d52));tr,te=train_test_split(idx,test_size=.3,stratify=y,random_state=42)
splits=[('row_random',tr,te)]
tr,te=next(GroupShuffleSplit(n_splits=1,test_size=.3,random_state=42).split(X,y,groups));splits.append(('pipe_group',tr,te))
out['52']['benchmarks']=[]
for label,tr,te in splits:
 m=DecisionTreeClassifier(max_depth=8,min_samples_leaf=20,random_state=42).fit(X.iloc[tr],y.iloc[tr]);s=m.predict_proba(X.iloc[te])[:,1]
 trhash=set(pd.util.hash_pandas_object(X.iloc[tr],index=False));tehash=pd.util.hash_pandas_object(X.iloc[te],index=False)
 out['52']['benchmarks'].append({'split':label,'train_n':len(tr),'train_pipes':int(groups.iloc[tr].nunique()),'test_pipes':int(groups.iloc[te].nunique()),'pipe_overlap':len(set(groups.iloc[tr])&set(groups.iloc[te])),'test_seen_exact_vector_fraction':float(tehash.isin(trhash).mean()),**metrics(y.iloc[te],s)})
basehash={cols:set(pd.util.hash_pandas_object(d52[list(cols)],index=False)) for cols in [tuple(FEATURES),tuple(['PIPE_NO']+FEATURES)]}
out['51_vs_52']={}
for name,d in t51.items():
 out['51_vs_52'][name]={'shared_pipes':len(set(d.PIPE_NO)&set(d52.PIPE_NO)),'pipes_51':int(d.PIPE_NO.nunique()),'matching_rows':{'|'.join(cols):int(pd.util.hash_pandas_object(d[list(cols)],index=False).isin(h).sum()) for cols,h in basehash.items()}}
(OUT/'new_table_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=lambda x:int(x)))
print(json.dumps({k:({kk:vv for kk,vv in v.items() if kk in ['rows','label_counts','dates','groups','benchmarks']} if k in ['50','52'] else v if k=='51_vs_52' else {'single_feature_separation':v['single_feature_separation']}) for k,v in out.items()},ensure_ascii=False,indent=2))
