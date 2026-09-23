"""Fixed quantile/mean models and calibration-only alarm-policy comparison.

No tuning on the test months. These months have been inspected during topic
selection, so this is exploratory chronological evaluation, not a blind trial.
"""
from pathlib import Path
import argparse
import json
import platform
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error,mean_squared_error
from common import load_energy,make_features,month_folds,alarm_threshold,event_metrics,finite_sample_quantile


def estimator(quantile=None):
    kw=dict(max_iter=180,max_leaf_nodes=15,min_samples_leaf=30,learning_rate=.06,
            l2_regularization=2,early_stopping=False,random_state=42)
    if quantile is not None:kw.update(loss='quantile',quantile=quantile)
    return HistGradientBoostingRegressor(**kw)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--zip',default='/tmp/kamp_contest_energy.zip')
    ap.add_argument('--output',default=str(Path(__file__).parent/'interval_results'))
    args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    y,novel,source=load_energy(args.zip)
    metrics,regression,intervals,fold_audit,predictions=[],[],[],[],[]
    for h in [1,4]:
        x,eligible=make_features(y,h)
        for fold in month_folds(y,eligible,h):
            tr,ca,te=[fold[k] for k in ['train','cal','test']]
            yt,yc,yv=[y.loc[m].to_numpy() for m in [tr,ca,te]]
            event_cutoff=float(np.quantile(yt,.95));cal_event=yc>=event_cutoff;event=yv>=event_cutoff
            info={k:v for k,v in fold.items() if k not in ['train','cal','test']}
            info.update(horizon_minutes=15*h,train_n=len(yt),calibration_n=len(yc),test_n=len(yv),
                        event_threshold=event_cutoff,calibration_events=int(cal_event.sum()),test_events=int(event.sum()))
            fold_audit.append(info)
            cal_scores={'persistence':x.loc[ca,f'lag_{h}'].to_numpy()}
            test_scores={'persistence':x.loc[te,f'lag_{h}'].to_numpy()}
            cal_scores['damped_trend']=cal_scores['persistence']+.25*h*(cal_scores['persistence']-x.loc[ca,f'lag_{h+1}'].to_numpy())
            test_scores['damped_trend']=test_scores['persistence']+.25*h*(test_scores['persistence']-x.loc[te,f'lag_{h+1}'].to_numpy())
            for name,q in [('mean_hgb',None),('q05_hgb',.05),('q95_hgb',.95)]:
                model=estimator(q);model.fit(x.loc[tr],yt)
                cal_scores[name]=model.predict(x.loc[ca]);test_scores[name]=model.predict(x.loc[te])
            cal_scores['mean_persistence_max']=np.maximum(cal_scores['mean_hgb'],cal_scores['persistence'])
            test_scores['mean_persistence_max']=np.maximum(test_scores['mean_hgb'],test_scores['persistence'])
            # Quantile crossing is addressed without using any target labels.
            clo=np.minimum(cal_scores['q05_hgb'],cal_scores['q95_hgb'])
            chi=np.maximum(cal_scores['q05_hgb'],cal_scores['q95_hgb'])
            lo=np.minimum(test_scores['q05_hgb'],test_scores['q95_hgb'])
            hi=np.maximum(test_scores['q05_hgb'],test_scores['q95_hgb'])
            errors=np.maximum.reduce([clo-yc,yc-chi,np.zeros_like(yc)])
            adjustment=finite_sample_quantile(errors,.90)
            for label,l,u in [('raw_90pct_quantiles',lo,hi),('calibrated_90pct_interval',lo-adjustment,hi+adjustment)]:
                covered=(yv>=l)&(yv<=u)
                intervals.append(dict(info,interval=label,empirical_coverage=float(covered.mean()),
                    peak_coverage=float(covered[event].mean()) if event.any() else None,
                    mean_width=float(np.mean(u-l)),calibration_adjustment=adjustment,
                    note='Empirical coverage only; temporal dependence/drift precludes an iid coverage guarantee'))
            subset_new=novel.loc[te].to_numpy()
            p=pd.DataFrame({'timestamp':y.index[te].astype(str),'source_date':(y.index[te]-pd.Timedelta(minutes=1)).strftime('%Y-%m-%d'),
                'month':fold['month'],'horizon_minutes':h*15,'truth':yv,'event':event,'event_threshold':event_cutoff,
                'new_daily_profile':subset_new,'lower90':lo-adjustment,'upper90':hi+adjustment})
            for name,pred in test_scores.items():p[name]=pred
            for name in ['persistence','damped_trend','mean_hgb']:
                regression.append(dict(info,model=name,mae=float(mean_absolute_error(yv,test_scores[name])),
                    rmse=float(mean_squared_error(yv,test_scores[name])**.5)))
            for name in ['persistence','damped_trend','mean_hgb','q95_hgb','mean_persistence_max']:
                for budget in [.01,.03,.05]:
                    threshold=alarm_threshold(cal_scores[name],cal_event,budget)
                    pred=test_scores[name]>threshold
                    key=f'alarm__{name}__{budget:.2f}';p[key]=pred
                    for subset,mask in [('all',np.ones(len(yv),dtype=bool)),('new_daily_profile',subset_new)]:
                        if not mask.any():continue
                        metrics.append(dict(info,model=name,calibration_fpr_budget=budget,score_threshold=threshold,
                            calibration_realized_fpr=float((cal_scores[name][~cal_event]>threshold).mean()),
                            subset=subset,**event_metrics(event[mask],pred[mask],test_scores[name][mask])))
            predictions.append(p)
            print(f"done horizon={h*15} month={fold['month']} train/cal/test={len(yt)}/{len(yc)}/{len(yv)}",flush=True)
            # Checkpoint only summaries, so interrupted runs retain completed folds.
            (out/'metrics.json').write_text(json.dumps({'source':source,'folds':fold_audit,'alarms':metrics,
                'regression':regression,'intervals':intervals},ensure_ascii=False,indent=2))
    all_preds=pd.concat(predictions,ignore_index=True)
    all_preds.to_csv(out/'predictions.csv.gz',index=False,compression='gzip')
    pd.DataFrame(metrics).to_csv(out/'alarms.csv',index=False)
    pd.DataFrame(regression).to_csv(out/'regression.csv',index=False)
    pd.DataFrame(intervals).to_csv(out/'intervals.csv',index=False)
    (out/'environment.json').write_text(json.dumps({'python':platform.python_version(),'numpy':np.__version__,
        'pandas':pd.__version__,'scikit_learn':sklearn.__version__},indent=2))
    print('Finished:',out,flush=True)


if __name__=='__main__':main()
