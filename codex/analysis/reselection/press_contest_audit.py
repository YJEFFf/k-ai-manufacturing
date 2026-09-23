"""Audit official contest attachment 8079; only normal data train/calibrate.

python press_contest_audit.py [/tmp/kamp_contest_8079.zip]
No dates, file names, index or Equipment_state are used as model features.
Windows never cross a non-0.1-second gap or a chronological split boundary.
This evaluates provided anomaly labels, not real prospective failures or RUL.
"""
from pathlib import Path
import sys,zipfile,json,hashlib
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import precision_score,recall_score,f1_score,roc_auc_score,average_precision_score,confusion_matrix

OUT=Path(__file__).resolve().parent
ARCHIVE=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/kamp_contest_8079.zip')
COLS=['AI0_Vibration','AI1_Vibration','AI2_Current']

def blocks(df):
    t=pd.to_datetime(df.TimeStamp)
    split=t.diff().dt.total_seconds().sub(.1).abs().gt(1e-6)
    split.iloc[0]=True
    return split.cumsum()-1

def summary(df):
    ts=pd.to_datetime(df.TimeStamp);g=blocks(df)
    return {'rows':len(df),'columns':list(df.columns),'labels':df.Equipment_state.value_counts().to_dict(),
        'missing':df.isna().sum().to_dict(),'numeric_summary':df[COLS].describe().to_dict(),
        'first_timestamp':str(ts.min()),'last_timestamp':str(ts.max()),'unique_timestamps':int(ts.nunique()),
        'time_step_counts':ts.diff().dt.total_seconds().value_counts().head(12).to_dict(),
        'duplicate_sensor_rows':int(df[COLS].duplicated().sum()),'contiguous_100ms_blocks':int(g.nunique()),
        'block_length_histogram':g.value_counts().value_counts().sort_index().to_dict(),
        'note':'Blocks are recording segments, not verified independent fault events.'}

def metrics(y,s,threshold):
    pred=s>threshold
    return {'threshold':float(threshold),'precision':float(precision_score(y,pred,zero_division=0)),
        'recall':float(recall_score(y,pred,zero_division=0)),'f1':float(f1_score(y,pred,zero_division=0)),
        'roc_auc':float(roc_auc_score(y,s)),'average_precision':float(average_precision_score(y,s)),
        'confusion_matrix_tn_fp_fn_tp':confusion_matrix(y,pred).ravel().tolist(),
        'normal_false_alarm_rate':float(pred[y==0].mean())}

def main():
    result={'source':{'url':'https://www.kamp-ai.kr/cptFileDownload','post_fileSeq':8079,
        'archive_sha256':hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()},'limitations':['Only one normal date and one anomaly date. No independent future normal day or independent fault event validation.','Physical fault cause, real versus injected anomaly provenance and RUL cannot be determined from these CSVs alone.']}
    with zipfile.ZipFile(ARCHIVE) as z:
        assert z.testzip() is None
        ds={n.rsplit('/',1)[-1]:pd.read_csv(z.open(n)) for n in z.namelist() if n.endswith('.csv')}
    normal=ds['press_data_normal.csv'];abnormal=ds['outlier_data.csv']
    result['normal']=summary(normal);result['outlier']=summary(abnormal)
    result['cross_label_identical_sensor_rows']=len(abnormal[COLS].merge(normal[COLS].drop_duplicates(),on=COLS))
    ng=blocks(normal);ag=blocks(abnormal)
    cut1=int(ng.nunique()*.6);cut2=int(ng.nunique()*.8)
    train=normal[ng<cut1];cal=normal[(ng>=cut1)&(ng<cut2)];test_n=normal[ng>=cut2]
    result['split']={'method':'chronological contiguous-block normal 60/20/20; every provided outlier is held out','train_normal':len(train),'calibration_normal':len(cal),'test_normal':len(test_n),'test_outlier':len(abnormal),'train_blocks':cut1,'calibration_blocks':cut2-cut1,'test_normal_blocks':int(ng.nunique())-cut2,'outlier_blocks':int(ag.nunique())}
    scaler=StandardScaler().fit(train[COLS]);xt=scaler.transform(train[COLS]);xc=scaler.transform(cal[COLS]);xx=scaler.transform(pd.concat([test_n[COLS],abnormal[COLS]]))
    y=np.r_[np.zeros(len(test_n),dtype=int),np.ones(len(abnormal),dtype=int)]
    allscores={}
    for j,c in enumerate(COLS):allscores[f'abs_standardized_{c}']=(np.abs(xc[:,j]),np.abs(xx[:,j]))
    allscores['max_abs_standardized']=(np.abs(xc).max(axis=1),np.abs(xx).max(axis=1))
    allscores['squared_standardized_distance']=((xc**2).sum(axis=1),(xx**2).sum(axis=1))
    nn=NearestNeighbors(n_neighbors=5).fit(xt)
    allscores['5nn_distance']=(nn.kneighbors(xc)[0].mean(axis=1),nn.kneighbors(xx)[0].mean(axis=1))
    model=IsolationForest(n_estimators=200,random_state=42,n_jobs=2).fit(xt)
    allscores['isolation_forest']=(-model.score_samples(xc),-model.score_samples(xx))
    result['pointwise_baselines']={name:metrics(y,st,np.quantile(sc,.99)) for name,(sc,st) in allscores.items()}
    # Block-respecting, trailing RMS, causally evaluated after five observed samples.
    def rms(df,window=5):
        z=scaler.transform(df[COLS]);g=blocks(df).to_numpy()
        r=pd.DataFrame(z*z).groupby(g).rolling(window,min_periods=window).mean().reset_index(level=0,drop=True).sort_index()
        return np.sqrt(r.max(axis=1,skipna=False)).to_numpy()
    rc=rms(cal);rn=rms(test_n);ra=rms(abnormal)
    st=np.r_[rn,ra];valid=np.isfinite(st);yv=y[valid];st=st[valid]
    threshold=np.quantile(rc[np.isfinite(rc)],.99)
    result['trailing_5_point_rms']=metrics(yv,st,threshold)
    result['trailing_5_point_rms'].update({'warmup_excluded_normal':int(np.isnan(rn).sum()),'warmup_excluded_outlier':int(np.isnan(ra).sum()),'scored_normal':int(np.isfinite(rn).sum()),'scored_outlier':int(np.isfinite(ra).sum()),'limitation':'Scored points only: warm-up samples omitted. Not directly identical evaluation denominator to pointwise scores.'})
    # Perfect metadata prediction is a warning, never a candidate deployed model.
    result['metadata_leakage_warning']={'date_predicts_provided_label_perfectly':bool(set(pd.to_datetime(normal.TimeStamp).dt.date).isdisjoint(set(pd.to_datetime(abnormal.TimeStamp).dt.date))),'Equipment_state_is_target_not_feature':True,'filenames_encode_label':True}
    (OUT/'press_contest_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)))
    print(json.dumps({'split':result['split'],'pointwise_baselines':result['pointwise_baselines'],'trailing_5_point_rms':result['trailing_5_point_rms']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
