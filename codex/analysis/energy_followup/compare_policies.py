"""Join independent model outputs, verify alignment and audit alarm trade-offs."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
from common import event_metrics

NAMES={'persistence':'최근값 유지','damped_trend':'단순 추세','mean_hgb':'평균 회귀',
       'q95_hgb':'상위 95% 분위수','mean_persistence_max':'회귀·최근값 최대',
       'logistic':'로지스틱 분류','hgb_classifier':'트리 분류'}


def counts_array(y,p):
    return np.array([(y&p).sum(),(~y&p).sum(),(y&~p).sum(),(~y&~p).sum()],dtype=float)


def paired_bootstrap(frame,model,baseline,budget,reps=2000):
    # Paired one-day and contiguous seven-day resampling: descriptive sensitivity,
    # not a guarantee under augmentation, drift, or post-selection.
    y=frame.event.to_numpy(bool)
    a=frame[f'alarm__{model}__{budget:.2f}'].to_numpy(bool)
    b=frame[f'alarm__{baseline}__{budget:.2f}'].to_numpy(bool)
    groups=pd.to_datetime(frame.timestamp).dt.normalize()
    days=sorted(groups.unique());av=[];bv=[]
    for day in days:
        m=(groups==day).to_numpy();av.append(counts_array(y[m],a[m]));bv.append(counts_array(y[m],b[m]))
    av=np.array(av);bv=np.array(bv);n=len(days);rng=np.random.default_rng(20260922)
    output=[]
    for width in [1,7]:
        deltas=[]
        for _ in range(reps):
            if width==1:ix=rng.integers(0,n,n)
            else:
                starts=rng.integers(0,max(1,n-width+1),int(np.ceil(n/width)))
                ix=np.concatenate([np.arange(s,min(s+width,n)) for s in starts])[:n]
            ac=av[ix].sum(axis=0);bc=bv[ix].sum(axis=0)
            if ac[0]+ac[2]==0:continue
            recall=ac[0]/(ac[0]+ac[2])-bc[0]/(bc[0]+bc[2])
            fpr=ac[1]/(ac[1]+ac[3])-bc[1]/(bc[1]+bc[3])
            deltas.append([recall,fpr])
        d=np.array(deltas)
        output.append({'model':model,'baseline':baseline,'budget':budget,'block_days':width,
                       'days':n,'replicates':len(d),'recall_delta_percentile_2_5_97_5':np.quantile(d[:,0],[.025,.975]).tolist(),
                       'fpr_delta_percentile_2_5_97_5':np.quantile(d[:,1],[.025,.975]).tolist()})
    return output


def plot_results(aggregate,monthly,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font=Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')
    if font.exists():
        font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus']=False
    colors={'persistence':'#6b7280','mean_hgb':'#3b82f6','q95_hgb':'#eab308','logistic':'#059669','hgb_classifier':'#9333ea'}
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),constrained_layout=True)
    for ax,h in zip(axes,[15,60]):
        f=aggregate[(aggregate.horizon_minutes==h)&(aggregate.period=='aug_sep')&(aggregate.subset=='all')]
        for model,color in colors.items():
            g=f[f.model==model].sort_values('budget')
            ax.plot(g.fpr*100,g.recall*100,'o-',label=NAMES[model],color=color)
        ax.set(xlabel='실제 평가 오경보율 (%)',ylabel='피크 재현율 (%)',title=f'{h}분 뒤 고부하 경보 · 8~9월')
        ax.grid(alpha=.2);ax.legend(fontsize=8,loc='lower right')
    fig.suptitle('보정월에서 1·3·5% 예산 설정 → 다음 달에서 관측한 결과',fontsize=13)
    fig.savefig(out/'alarm_tradeoff.png',dpi=170);fig.savefig(out/'alarm_tradeoff.svg');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.3),constrained_layout=True)
    for ax,h in zip(axes,[15,60]):
        for model,color in colors.items():
            g=monthly[(monthly.horizon_minutes==h)&(monthly.model==model)&(monthly.budget==.05)&(monthly.subset=='all')]
            ax.plot(g.month,g.fpr*100,'o-',label=NAMES[model],color=color)
        ax.axhline(5,color='black',linestyle='--',linewidth=1,label='보정월 예산 5%')
        ax.set(xlabel='평가 월 (2021년)',ylabel='실제 오경보율 (%)',title=f'{h}분 뒤: 다음 달에도 5%가 보장되지는 않음',xticks=list(range(5,10)))
        ax.grid(alpha=.2)
    axes[1].legend(fontsize=8);fig.savefig(out/'monthly_false_alarms.png',dpi=170);plt.close(fig)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--interval-dir',default='/tmp/kamp-energy-interval-results')
    ap.add_argument('--output',default='/tmp/kamp-energy-comparison');args=ap.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    p=pd.read_csv(Path(args.interval_dir)/'predictions.csv.gz')
    c=pd.read_csv(Path(__file__).parent/'classifier_predictions.csv.gz')
    keys=['horizon_minutes','timestamp']
    assert not p.duplicated(keys).any()
    joined=p.set_index(keys)
    for model in ['recent_value','logistic','hgb_classifier']:
        other=c[c.model==model].set_index(keys).reindex(joined.index)
        assert len(other)==len(joined) and other.power.notna().all()
        assert np.array_equal(other.power.to_numpy(),joined.truth.to_numpy())
        assert np.array_equal(other.train_peak_threshold.to_numpy(),joined.event_threshold.to_numpy())
        assert np.array_equal(other.is_peak.to_numpy(),joined.event.to_numpy())
        for budget in [.01,.03,.05]:
            a=other[f'alarm_budget_{round(100*budget):02d}pct'].to_numpy(bool)
            if model=='recent_value':assert np.array_equal(a,joined[f'alarm__persistence__{budget:.2f}'].to_numpy())
            else:joined[f'alarm__{model}__{budget:.2f}']=a
        if model!='recent_value':joined[model]=other.score.to_numpy()
    p=joined.reset_index()
    p['onset']=p.event&(p.persistence<p.event_threshold)
    p['already_high']=p.persistence>=p.event_threshold
    p['date']=pd.to_datetime(p.timestamp).dt.strftime('%Y-%m-%d')
    p['hour']=pd.to_datetime(p.timestamp).dt.hour
    p['time_band']=pd.cut(p.hour,[-1,5,11,17,23],labels=['00–05','06–11','12–17','18–23'])
    models=list(NAMES);monthly=[];aggregate=[];slices=[];bootstrap=[]
    for h,hf in p.groupby('horizon_minutes'):
        for period,frame in [('all_months',hf),('aug_sep',hf[hf.month>=8])]:
            for subset,mask in [('all',np.ones(len(frame),bool)),('new_daily_profile',frame.new_daily_profile.to_numpy(bool))]:
                f=frame.loc[mask]
                for model in models:
                    for budget in [.01,.03,.05]:
                        pred=f[f'alarm__{model}__{budget:.2f}'].to_numpy(bool)
                        metrics=event_metrics(f.event,pred,f[model])
                        onset=f.onset.to_numpy(bool)
                        aggregate.append(dict(period=period,horizon_minutes=int(h),subset=subset,model=model,budget=budget,
                            onset_n=int(onset.sum()),onset_recall=float(pred[onset].mean()) if onset.any() else None,**metrics))
            if period=='aug_sep':
                for model in ['q95_hgb','logistic','hgb_classifier']:
                    for row in paired_bootstrap(frame,model,'persistence',.05):bootstrap.append(dict(horizon_minutes=int(h),**row))
        for month,f in hf.groupby('month'):
            for model in models:
                for budget in [.01,.03,.05]:
                    pred=f[f'alarm__{model}__{budget:.2f}'].to_numpy(bool)
                    monthly.append(dict(horizon_minutes=int(h),month=int(month),subset='all',model=model,budget=budget,**event_metrics(f.event,pred)))
        af=hf[hf.month>=8]
        for groupcol in ['time_band','already_high','new_daily_profile']:
            for value,f in af.groupby(groupcol,observed=True):
                for model in ['persistence','q95_hgb','logistic','hgb_classifier']:
                    slices.append(dict(horizon_minutes=int(h),group=groupcol,value=str(value),model=model,budget=.05,
                        **event_metrics(f.event,f[f'alarm__{model}__0.05'])))
    ag=pd.DataFrame(aggregate);mo=pd.DataFrame(monthly)
    ag.to_csv(out/'aggregate.csv',index=False);mo.to_csv(out/'monthly.csv',index=False)
    pd.DataFrame(slices).to_csv(out/'failure_conditions.csv',index=False)
    (out/'bootstrap.json').write_text(json.dumps(bootstrap,ensure_ascii=False,indent=2))
    p.to_csv(out/'joined_predictions.csv.gz',index=False,compression='gzip')
    checks={'independent_implementations_same_truth_and_threshold':True,
            'all_three_baseline_alarm_budgets_identical':True,'prediction_rows':len(p),
            'unique_prediction_keys':not p.duplicated(keys).any(),
            'known_test_exposure':'exploratory; these dates informed topic selection',
            'bootstrap_note':'paired day/block sensitivity, not a guarantee under drift or multiple model selection'}
    (out/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    plot_results(ag,mo,out)
    print(ag.query('period=="aug_sep" and subset=="all" and budget==.05')[['horizon_minutes','model','recall','fpr','f1','onset_recall']].round(4).to_string(index=False))
    print('RESULTS',out,flush=True)


if __name__=='__main__':main()
