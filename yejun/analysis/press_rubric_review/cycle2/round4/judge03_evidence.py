"""4회차 평가관03: 센서 기여·관측 상호작용·12행 인용을 읽기 전용 독립 검증."""
import json
import re
import time

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

import judge03_verify as V
from model import GuardModel, D, layout, sine_score
from press.calibrate import conformal_p, segment_max
from press.scores import ExpTail
from press.diagnosis import sine_fit, MIN_FIT_LEN

Y, G, O, H, S = V.Y, V.G, V.O, V.HERE, V.S
START=time.monotonic()
R={}


def main():
    normal,abnormal,_=D.load(Y/'press_submission')
    models={s:GuardModel.load(G/'artifacts'/f'guard_{s}.json') for s in 'AB'}
    splits={s:D.split_normal(normal,D.segments(normal),s) for s in 'AB'}
    si=pd.read_csv(O/'sensor_importance_v2.csv')
    pv=pd.read_csv(O/'position_vibration_misses_v2.csv')
    cf=pd.read_csv(O/'coupling_fit_v2.csv')
    cr=pd.read_csv(O/'coupling_records_v2.csv')
    ab=pd.read_csv(O/'ablation_v2.csv')
    readme=(G/'README.md').read_text()
    names={'full':((0,1,2),True),'drop_AI0':((1,2),True),'drop_AI1':((0,2),True),
           'drop_AI2_from_magnitude':((0,1),True),'current_only':((2,),True),'vibration_only':((0,1),False)}
    details={}
    for sid,model in models.items():
        frames={'train':splits[sid]['train'],'cal':splits[sid]['cal'],'test':splits[sid]['test'],'abn':abnormal}
        parts={}
        for name,frame in frames.items():
            q,seg=V.prep(frame)
            comp=model.components(q,seg)
            z=np.abs((q[S].to_numpy(float)-model.mean)/model.scale)
            parts[name]=dict(q=q,seg=seg,comp=comp,z=z)
        sens_rows=[]
        for name,(sensors,shape) in names.items():
            tail=ExpTail(parts['train']['z'][:,list(sensors)].max(1))
            sc={}
            for k in ('cal','test','abn'):
                mag=tail(parts[k]['z'][:,list(sensors)].max(1))
                sc[k]=np.fmax.reduce([mag,parts[k]['comp']['g_waveform'],parts[k]['comp']['g_dynamics']]) if shape else mag
            cal=segment_max(sc['cal'],parts['cal']['seg'])
            for alpha in (.01,.03,.05):
                alarms={k:np.nan_to_num(conformal_p(cal,sc[k]),nan=1)<=alpha for k in ('test','abn')}
                tp,fp=int(alarms['abn'].sum()),int(alarms['test'].sum())
                fn=600-tp
                vals=dict(tp=tp,fp=fp,fn=fn,f1=2*tp/(2*tp+fp+fn),
                          normal_alerted_segments=int(pd.Series(alarms['test']).groupby(parts['test']['seg']).max().sum()),
                          abnormal_detected_segments=int(pd.Series(alarms['abn']).groupby(parts['abn']['seg']).max().sum()))
                row=si[si.split.eq(sid)&si.method.eq('refit_ablation')&si.variant.eq(name)&si.alpha.eq(alpha)].iloc[0]
                V.check_numbers(f'sensor/{sid}/{name}/{alpha}',row,vals)
                if alpha==.01:
                    sens_rows.append(dict(variant=name,**vals))
        # Same 20 temporal channel donor repetitions, implemented from the definition.
        raw_test=D.inputs_only(frames['test']).reset_index(drop=True)
        raw_abn=D.inputs_only(abnormal).reset_index(drop=True)
        segt,sega=layout(raw_test)[1],layout(raw_abn)[1]
        lens=pd.Series(segt).value_counts()
        swap=[]
        for sensor in S:
            misses,dets=[],[]
            for rep in range(20):
                rng=np.random.default_rng(1000+rep)
                frame=raw_abn.copy()
                for rid in np.unique(sega):
                    ix=np.flatnonzero(sega==rid)
                    donors=lens[lens>=len(ix)].index.to_numpy()
                    donor=np.flatnonzero(segt==rng.choice(donors))[:len(ix)]
                    frame.loc[ix,sensor]=raw_test[sensor].to_numpy()[donor]
                pred=model.predict(frame,.01)
                misses.append(int((pred.alarm==0).sum()))
                dets.append(int(pred.groupby('record_id').alarm.max().sum()))
            row=si[si.split.eq(sid)&si.method.eq('channel_swap')&si.variant.eq(f'swap_{sensor}')].iloc[0]
            vals=dict(fn=float(np.median(misses)),abnormal_detected_segments=float(np.median(dets)),
                      fn_min=min(misses),fn_max=max(misses),detected_min=min(dets),detected_max=max(dets),repeats=20)
            V.check_numbers(f'swap/{sid}/{sensor}',row,vals)
            swap.append(dict(sensor=sensor,**vals))
        # Explanatory univariate ranking and magnitude threshold.
        univ={}
        for sensor in S:
            sn=raw_test.groupby(segt)[sensor].std().dropna()
            sa=raw_abn.groupby(sega)[sensor].std().dropna()
            auc=roc_auc_score(np.r_[np.zeros(len(sn)),np.ones(len(sa))],np.r_[sn,sa])
            row=si[si.split.eq(sid)&si.method.eq('univariate_segment_sd')&si.variant.eq(sensor)].iloc[0]
            V.check(f'AUROC/{sid}/{sensor}',row.auroc,auc)
            univ[sensor]=auc
        thr=np.sort(model.cal)[-1]
        grid=np.arange(0,40.0001,.0001)
        zstar=grid[np.argmax(model.tails['magnitude'](grid)>thr)]
        over=(parts['abn']['z']>zstar).sum(0)
        # no_early_switch component recalibration.
        sc={}
        for k in ('cal','test','abn'):
            cur=parts[k]['q'][S[2]].to_numpy(float)
            s8=model.tails['sine8'](sine_score(cur,parts[k]['seg'],8))
            sc[k]=np.fmax.reduce([parts[k]['comp']['g_magnitude'],s8,parts[k]['comp']['g_dynamics']])
        cal=segment_max(sc['cal'],parts['cal']['seg'])
        an=np.nan_to_num(conformal_p(cal,sc['test']),nan=1)<=.01
        aa=np.nan_to_num(conformal_p(cal,sc['abn']),nan=1)<=.01
        row=ab[ab.split_id.eq(sid)&ab.model.eq('no_early_switch')&ab.criterion.eq('conformal')&ab.alpha.eq(.01)].iloc[0]
        V.check_numbers(f'no_early/{sid}',row,dict(fn=int((~aa).sum()),fp=int(an.sum())))
        # Position by observed vibration level, all 20 rows and their CIs.
        vmax=pd.Series(parts['train']['z'][:,:2].max(1)).groupby(parts['train']['seg']).max()
        q95=vmax.quantile(.95)
        avmax=pd.Series(parts['abn']['z'][:,:2].max(1)).groupby(parts['abn']['seg']).max()
        pred=model.predict(abnormal,.01)
        is_high=pred.record_id.map(avmax>q95).to_numpy(bool)
        pos=pred.position.to_numpy()
        miss=pred.alarm.to_numpy()==0
        for ix,row in pv[pv.split.eq(sid)].iterrows():
            pm={'0-1':pos<=1,'2-6':(pos>=2)&(pos<=6),'>=7':pos>=7,'>=2':pos>=2}[row.position]
            vm={'all':np.ones(len(pos),bool),'vibration_high':is_high,'vibration_normal_range':~is_high}[row.vibration]
            k,n=int((miss&pm&vm).sum()),int((pm&vm).sum())
            lo,hi=V.cp(k,n)
            V.check_numbers(f'position/{ix+2}',row,dict(missed_rows=k,rows=n,miss_rate=k/n,ci_low=lo,ci_high=hi,
                          records=int(np.unique(pred.record_id.to_numpy()[pm&vm]).size),vib_threshold_train_q95=q95))
        # Correlation of log amplitudes; sine-fit R2 utility only, not team insights helper.
        tr=parts['train'];f=V.features(tr['q'],tr['seg'])
        cur=tr['q'][S[2]].to_numpy(float)
        r2=np.array([sine_fit(cur[tr['seg']==rid])[1] if length>=MIN_FIT_LEN else np.nan for rid,length in zip(f.record,f.length)])
        usable=(f.length>=17)&(r2>=np.nanquantile(r2,.05))&(f.amp>0)&(f.vib_sd>0)
        x,y=np.log(f.amp[usable]),np.log(f.vib_sd[usable])
        regression=stats.linregress(x,y)
        sd=np.std(y-(regression.intercept+regression.slope*x),ddof=2)
        row=cf[cf.split.eq(sid)].iloc[0]
        V.check_numbers(f'coupling/{sid}',row,dict(records=int(usable.sum()),r=regression.rvalue,slope=regression.slope,
                        intercept=regression.intercept,resid_sd=sd))
        rec=cr[cr.split.eq(sid)&cr.subset.eq('abnormal')]
        V.check(f'coupling/{sid}/abnormal_residuals',rec.resid_z,(np.log(rec.vib_sd)-(regression.intercept+regression.slope*np.log(rec.current_amp)))/sd)
        details[sid]=dict(sensor_refit=sens_rows,swap=swap,univariate=univ,z_threshold=float(zstar),rows_over_threshold=over.tolist(),
                          z_p95=np.quantile(parts['abn']['z'],.95,axis=0).tolist(),coupling_abnormal_residual_median=float(rec.resid_z.median()))
        V.log('Sensor contribution, observed interactions verified',sid)
    R['influence_details']=details
    # All source row sets are reselected independently for the 12 summaries.
    sm=pd.read_csv(O/'error_condition_summary_v2.csv')
    fn=pd.read_csv(O/'fn_intensity_v2.csv');fp=pd.read_csv(O/'fp_intensity_v2.csv')
    fpe=pd.read_csv(O/'fp_events_v2.csv');nm=pd.read_csv(O/'near_miss_corr_v2.csv');rb=pd.read_csv(O/'robustness_v2.csv')
    e1=pd.read_csv(Y/'analysis/press_supplement/e1_summary.csv');sel=pd.read_csv(Y/'analysis/press_selection/fp_mitigation_injection_v2.csv')
    ds=pd.read_csv(Y/'analysis/press_dayshift/v2_current_scale.csv')
    def lines(mask): return (np.flatnonzero(np.asarray(mask))+2).tolist()
    def e1mask(fam,level,t0): return e1.model.eq('guard_v2')&e1.alpha.eq(.01)&e1.family.eq(fam)&e1.level.eq(level)&e1.t0.eq(t0)&e1['shape'].eq('step')
    prefix='press_guard/outputs/'
    selections=[
        {prefix+'position_vibration_misses_v2.csv':lines(pv.position.eq('0-1')&pv.vibration.isin(['vibration_normal_range','vibration_high']))},
        {prefix+'position_vibration_misses_v2.csv':lines(pv.vibration.eq('all'))},
        {'analysis/press_supplement/e1_summary.csv':lines(e1mask('cur_offset',.8,0)|e1mask('cur_offset',.8,10))},
        {'analysis/press_supplement/e1_summary.csv':lines(e1mask('cur_gain',1.15,10)),prefix+'fn_intensity_v2.csv':lines(fn.family.eq('cur_gain')&fn.level_value.eq(1.15))},
        {prefix+'fn_intensity_v2.csv':lines(fn.family.eq('vib_noise'))},
        {prefix+'fn_intensity_v2.csv':lines(fn.family.eq('cur_offset'))},
        {'analysis/press_selection/fp_mitigation_injection_v2.csv':lines(sel.alpha.eq(.01)&sel.family.eq('vib_shock')&sel.level.isin([4.,6.]))},
        {prefix+'fp_intensity_v2.csv':lines((fp.condition.eq('amp_high')&fp.value.str.contains('B 정상 학습'))|
            (fp.alpha.eq(.05)&fp.condition.eq('vib_sd_quartile'))|(fp.condition.eq('operating_state')&fp.value.eq('load'))|
            (fp.condition.eq('amp_high_block_stratified')&fp.value.eq('B 정상 학습 q75'))|(fp.alpha.eq(.05)&fp.condition.eq('amp_within_load')))},
        {prefix+'fp_events_v2.csv':lines(fpe.independent&fpe.alpha.eq(.05))},
        {prefix+'near_miss_corr_v2.csv':lines(nm.split.eq('B'))},
        {'analysis/press_dayshift/v2_current_scale.csv':lines(ds.alpha.eq(.01)&((ds.split_id.eq('A')&ds.k.eq(1.5))|(ds.split_id.eq('B')&ds.k.isin([1.,1.05,1.5]))))},
        {prefix+'robustness_v2.csv':lines(rb.criterion.eq('conformal')&rb.alpha.eq(.01)&rb.version.eq('v2')&rb.input_variant.isin(['matched','coarse']))}
    ]
    for i,expected in enumerate(selections):
        got={}
        for entry in sm.iloc[i].source.split(';'):
            path,nums=entry.strip().rsplit(':',1)
            acc=got.setdefault(path,[])
            for val in nums.split(','):
                if '-' in val:
                    lo,hi=map(int,val.split('-'));acc.extend(range(lo,hi+1))
                else:acc.append(int(val))
        got={k:sorted(v) for k,v in got.items()}
        V.check(f'citations_exact/{i+2}',got==expected,True)
    for sid in 'AB':
        expected=[]
        p=pv[pv.split.eq(sid)]
        z=p[p.position.eq('0-1')&p.vibration.eq('vibration_normal_range')].iloc[0]
        c=p[p.position.eq('0-1')&p.vibration.eq('vibration_high')].iloc[0]
        expected.append((z.missed_rows,z.rows,c.miss_rate))
        z=p[p.position.eq('0-1')&p.vibration.eq('all')].iloc[0]
        c=p[p.position.eq('>=2')&p.vibration.eq('all')].iloc[0]
        expected.append((z.missed_rows,z.rows,c.miss_rate))
        for fam,level,t0 in [('cur_offset',.8,0),('cur_gain',1.15,10)]:
            z=e1[e1mask(fam,level,t0)&e1.split.eq(sid)].iloc[0]
            c=e1[e1mask(fam,level,10)&e1.split.eq(sid)].iloc[0]
            expected.append((round((1-z.detect_rate_2s)*z.trials),z.trials,1-c.detect_rate_2s if fam=='cur_offset' else np.nan))
        for fam,level,qt,compqt in [('vib_noise',2.,'Q1','Q4'),('cur_offset',.2,'Q4','Q1')]:
            z=fn[fn.split.eq(sid)&fn.family.eq(fam)&fn.level_value.eq(level)].iloc[0]
            expected.append((z[f'units_amp_{qt}']-z[f'detected_amp_{qt}'],z[f'units_amp_{qt}'],1-z[f'detected_amp_{compqt}']/z[f'units_amp_{compqt}']))
        z=sel[sel.split_id.eq(sid)&sel.alpha.eq(.01)&sel.family.eq('vib_shock')&sel.level.eq(4.)].iloc[0]
        c=sel[sel.split_id.eq(sid)&sel.alpha.eq(.01)&sel.family.eq('vib_shock')&sel.level.eq(6.)].iloc[0]
        expected.append((round((1-z.v2_detect_2s)*z.units*z.reps),z.units*z.reps,1-c.v2_detect_2s))
        z=fp[fp.alpha.eq(.01 if sid=='A' else .05)&fp.condition.eq('amp_high')&fp.value.str.contains('B 정상 학습')].iloc[0]
        expected.append((z.false_alarms,z.denominator,z.comparison_false_alarms/z.comparison_denominator))
        ind=fpe[fpe.independent&fpe.alpha.eq(.05)]
        k=int(((ind.reasons=='magnitude')&(ind.magnitude_sensor==S[0])).sum()) if sid=='A' else int((ind.alarm_rows==1).sum())
        expected.append((k,len(ind),np.nan))
        z=nm[nm.split.eq('B')&nm.condition.eq('vib_maxz')].iloc[0]
        expected.append((0,0,np.nan) if sid=='A' else (z.records_ge_0_9,z.records,np.nan))
        z=ds[ds.split_id.eq(sid)&ds.alpha.eq(.01)&ds.k.eq(1.5)].iloc[0]
        c=ds[ds.split_id.eq(sid)&ds.alpha.eq(.01)&ds.k.eq(1.)].iloc[0]
        expected.append((z.normal_notified_segments,z.normal_segments,np.nan if sid=='A' else c.normal_notified_segments/c.normal_segments))
        use=rb.split_id.eq(sid)&rb.alpha.eq(.01)&rb.criterion.eq('conformal')&rb.version.eq('v2')
        z=rb[use&rb.input_variant.eq('coarse')].iloc[0]
        c=rb[use&rb.input_variant.eq('matched')].iloc[0]
        expected.append((z.normal_notified_segments,z.normal_segments,c.normal_notified_segments/c.normal_segments))
        for i,(k,n,c) in enumerate(expected):
            V.check(f'summary_source_numbers/{i+2}/{sid}',sm.iloc[i][[f'errors_{sid}',f'denominator_{sid}',f'comparison_rate_{sid}']].to_numpy(float),[k,n,c])
    # State denominators agree between independent evaluation rows and press_evidence.
    ev=pd.read_csv(H/'judge03_fp_evaluations.csv')
    states=pd.read_csv(Y/'analysis/press_evidence/normal_alarms_by_state.csv')
    group_map={'frozen_A':'동결 A','frozen_B':'동결 B'}
    snames={'load':'부하','low':'저수준','short':'짧은 기록(<17)'}
    for alpha in (.01,.03,.05):
        for state,label in snames.items():
            for model,group in group_map.items():
                ee=ev[ev.model.eq(model)&ev.alpha.eq(alpha)&ev.state.eq(state)]
                rr=states[states.section.eq('상태별 정상 알림')&states.group.eq(group)&states.alpha.eq(alpha)&states.state.eq(label)].iloc[0]
                V.check(f'states/{alpha}/{state}/{model}',[ee.fa.sum(),len(ee)],[rr.alerted,rr.records])
    V.check('README/component_values',all(x in readme for x in ['44→133·31→112','86·71','56·56','46·33']),True)
    V.check('README/repeats50','잡음 50회(시드 0~49)' in readme,True)
    V.check('README/BH_Bonferroni','Bonferroni는 9검정 p=0.0974, 18검정 p=0.1948' in readme,True)
    V.check('README/E1_difference','E1의 74.4%·93.9%는 별도 난수 반복 결과' in readme,True)
    V.check('README/summary_count','조건 12행 요약' in readme,True)
    R['checks']=V.CHECKS
    R['failed']=[x for x in V.CHECKS if not x['ok']]
    R['elapsed_s']=round(time.monotonic()-START,2)
    (H/'judge03_evidence.json').write_text(json.dumps(D.to_jsonable(R),ensure_ascii=False,indent=2),encoding='utf-8')
    V.log('DONE evidence',len(V.CHECKS),'checks, failed',len(R['failed']),'time',R['elapsed_s'])


if __name__=='__main__': main()
