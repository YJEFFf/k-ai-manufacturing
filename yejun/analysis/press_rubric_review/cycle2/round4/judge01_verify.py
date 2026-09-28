"""R4 데이터 평가관 독립 재계산. 원본 ZIP과 저장 모델을 읽고 자기 검수 파일만 쓴다.

데이터·상태·주파수·전환 합성은 팀 진단 코드를 import하지 않는다. 저장 모델의
점수와 일괄/스트림 상태를 비교할 때만 model.py를 읽기 전용 import한다.
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python <this file>
"""
from pathlib import Path
import hashlib
import io
import json
import sys
import time
import zipfile
import numpy as np
import pandas as pd
from scipy import optimize, stats
from scipy.signal import lombscargle
from sklearn.mixture import GaussianMixture

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
EVID = YEJUN / 'analysis/press_evidence'
GUARD = YEJUN / 'press_guard'
DATA = REPO / '데이터셋/프레스_유압펌프_예지보전'
SENS = ['AI0_Vibration', 'AI1_Vibration', 'AI2_Current']
LOW, LOAD = '저수준', '부하'
CHECKS = []


def check(name, ok, detail=''):
    CHECKS.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    if not ok:
        print('FAIL', name, detail, flush=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=lambda x: x.item() if isinstance(x, np.generic) else str(x)), encoding='utf-8')


def design(n, f):
    theta = 2 * np.pi * f * np.arange(n) * .1
    return np.column_stack((np.sin(theta), np.cos(theta), np.ones(n)))


def tone(x, f):
    return np.linalg.lstsq(design(len(x), f), x, rcond=None)[0]


def window_ratio(x):
    amplitudes = [np.hypot(*tone(x[i:i+17], .6)[:2]) for i in range(len(x)-16)]
    return max(amplitudes) / min(amplitudes)


def mixture(x, k, seed=0):
    return GaussianMixture(k, random_state=seed, n_init=5).fit(x)


def main():
    began = time.monotonic()
    R = {'kind': 'independent source ZIP recomputation; observational diagnostics and synthetic sensitivity only'}
    raw, segs, times, hashes = {}, {}, {}, {}
    with zipfile.ZipFile(DATA / 'Dataset_소성가공 예지보전 AI 데이터셋.zip') as archive:
        for key, fname in [('normal', 'press_data_normal.csv'), ('abnormal', 'outlier_data.csv')]:
            member = next(n for n in archive.namelist() if n.endswith(fname))
            data = archive.read(member)
            digest = hashlib.sha256(data).hexdigest()
            hashes[key] = digest
            for folder in [DATA / 'data/3_소성가공_예지보전', YEJUN / 'press_submission/data/3_소성가공_예지보전']:
                check(f'{key} ZIP/CSV hash {folder}', sha(folder / fname) == digest)
            frame = pd.read_csv(io.BytesIO(data))
            t = pd.to_datetime(frame.TimeStamp)
            s = np.cumsum(t.diff().dt.total_seconds().sub(.1).abs().gt(1e-6).to_numpy())
            raw[key], times[key], segs[key] = frame, t, s
    R['input_sha256'] = hashes
    R['quality'] = {k: dict(rows=len(f), records=len(np.unique(segs[k])), nonfinite=int((~np.isfinite(f[SENS].to_numpy(float))).sum()),
        duplicate_sensor_timestamp=int(f[['TimeStamp']+SENS].duplicated().sum()), recorded_seconds=.1*len(f), elapsed_seconds=(times[k].iloc[-1]-times[k].iloc[0]).total_seconds()) for k,f in raw.items()}
    n, sn = raw['normal'], segs['normal']
    blocks = {s: np.flatnonzero(sn == s) for s in np.unique(sn)}
    X = n[SENS].to_numpy(float)
    rows = []
    for record, ii in blocks.items():
        if len(ii) < 17:
            continue
        x = X[ii, 2]
        coef = tone(x, .6)
        rows.append(dict(record=int(record), length=len(x), current_rms_dm=float(x.std()), AI0_sd=float(X[ii,0].std(ddof=1)), AI1_sd=float(X[ii,1].std(ddof=1)),
            amp06=float(np.hypot(*coef[:2])), r2_06=float(1-((x-design(len(x),.6)@coef)**2).sum()/((x-x.mean())**2).sum()),
            win_amp_ratio=window_ratio(x), start=times['normal'].iloc[ii[0]], end=times['normal'].iloc[ii[-1]]))
    states = pd.DataFrame(rows).set_index('record')
    xl = np.log(states.current_rms_dm.to_numpy()).reshape(-1,1)
    gms = {k:mixture(xl,k) for k in range(1,7)}
    low_id = np.argmin(gms[2].means_.ravel())
    states['state'] = np.where(gms[2].predict(xl)==low_id, LOW, LOAD)
    states['p_low'] = gms[2].predict_proba(xl)[:,low_id]
    order = np.argsort(gms[4].means_.ravel())
    states['substate4'] = np.argsort(order)[gms[4].predict(xl)]
    centers = np.exp(gms[4].means_.ravel()[order])
    states['substate4_center'] = centers[states.substate4]
    for threshold in [90,92,95]:
        states[f'state_thr{threshold}'] = np.where(states.current_rms_dm<threshold,LOW,LOAD)
    med = states.groupby('state')[['AI0_sd','AI1_sd','amp06']].median()
    gain_up = (med.loc[LOAD]/med.loc[LOW]).to_numpy()
    states.to_csv(HERE/'judge01_expected_states.csv')
    seeds = {seed:min(range(1,7), key=lambda k: mixture(xl,k,seed).bic(xl)) for seed in range(5)}
    x2 = np.column_stack((xl[:,0],np.log(states.AI1_sd)))
    R['mixture'] = dict(bic_1d={k:g.bic(xl) for k,g in gms.items()}, best_by_seed=seeds,
        bic_2d={k:mixture(x2,k).bic(x2) for k in range(1,7)}, centers4=centers.tolist(), weights4=gms[4].weights_[order].tolist(),
        low_count=int(states.state.eq(LOW).sum()), load_count=int(states.state.eq(LOAD).sum()),
        low_jaccard={k:float(((g.predict(xl)==np.argmin(g.means_.ravel())) & states.state.eq(LOW)).sum()/((g.predict(xl)==np.argmin(g.means_.ravel())) | states.state.eq(LOW)).sum()) for k,g in gms.items() if k>=2})
    R['adjacent_transition'] = {}
    for source in range(4):
        mask = states.substate4.shift().eq(source) & states.index.to_series().diff().eq(1)
        R['adjacent_transition'][source] = {target:dict(n=int(mask.sum()), count=int((mask & states.substate4.eq(target)).sum())) for target in range(4)}
    R['gains_low_to_load_AI0_AI1_current'] = gain_up.tolist()
    # Independent step-power reconstruction, including record length weighting.
    rng = np.random.default_rng(0)
    power_rows = []
    for record, row in states.iterrows():
        x = X[blocks[record],2]
        gain = gain_up[2] if row.state==LOW else 1/gain_up[2]
        detected = 0
        for _ in range(4):
            at = int(rng.integers(1,len(x)))
            y = x.copy(); y[at:] = x.mean()+gain*(x[at:]-x.mean())
            detected += window_ratio(y)>1.3
        power_rows.append(dict(record=int(record), length=len(x), power=detected/4, crossing=min(1,2*(len(x)-1)*.1/20.5)))
    power = pd.DataFrame(power_rows)
    power.to_csv(HERE/'judge01_expected_power.csv', index=False)
    R['transition_observation'] = dict(observed=int((states.win_amp_ratio>1.3).sum()), ratio_max=float(states.win_amp_ratio.max()),
        power=float(power.power.mean()), power_long=float(power.loc[power.length>=40,'power'].mean()), expected_crossing=float(power.crossing.sum()),
        expected_detected_approx=float(power.crossing.sum()*power.power.mean()), expected_detected_length_weighted=float((power.crossing*power.power).sum()))
    pre = states[states.index<470]
    mid = ((pre.start-pre.start.iloc[0]).dt.total_seconds()+pre.length*.05).to_numpy()
    y = pre.state.eq(LOW).to_numpy(float); y -= y.mean()
    periods = np.linspace(8,80,2000)
    peak = lombscargle(mid,y,2*np.pi/periods,normalize=True)
    R['period'] = dict(lomb_scargle_peak_seconds=float(periods[peak.argmax()]), power=float(peak.max()))
    print('raw states, BIC, period, transition power complete', R['transition_observation'], flush=True)
    # Narrowband fit uses sin/cos reversed from team, plus independent bounded search.
    tone_rows=[]
    for key,frame in raw.items():
        for record in np.unique(segs[key]):
            ii=np.flatnonzero(segs[key]==record)
            if len(ii)!=50: continue
            x=frame[SENS].to_numpy(float)[ii]
            current=tone(x[:,2],.6); current_phase=np.arctan2(current[1],current[0])
            for channel,center,multiple in [(0,3.6,6),(1,1.8,3)]:
                vibration=x[:,channel]
                c=tone(vibration,center)
                def sse(f): return float(((vibration-design(50,f)@tone(vibration,f))**2).sum())
                grid=np.linspace(center-.15,center+.15,301)
                best=int(np.argmin([sse(f) for f in grid]))
                frequency=optimize.minimize_scalar(sse,bounds=(grid[max(0,best-1)],grid[min(300,best+1)]),method='bounded').x
                harmonic=np.column_stack([np.ones(50)]+[design(50,.6*h)[:,j] for h in range(1,9) for j in [0,1]])
                fitted=harmonic@np.linalg.lstsq(harmonic,vibration,rcond=None)[0]
                spec=np.abs(np.fft.rfft((vibration-vibration.mean())*np.hanning(50),n=500))**2
                hz=np.fft.rfftfreq(500,.1)
                # sin-based phase has extra pi/2 relative to cos convention. Match the physical cosine phase.
                delta=(np.arctan2(-c[0],c[1])-multiple*np.arctan2(-current[0],current[1]))%(2*np.pi)
                tone_rows.append(dict(file=key,record=int(record),sensor=SENS[channel],tone_frequency_hz=float(frequency), tone_amplitude=float(np.hypot(*c[:2])),
                    current_amplitude=float(np.hypot(*current[:2])), harmonic_r2=float(1-((vibration-fitted)**2).sum()/((vibration-vibration.mean())**2).sum()),
                    tone_rms_over_sd=float(np.hypot(*c[:2])/np.sqrt(2)/vibration.std()),phase_difference=float(delta),spectral_peak_hz=float(hz[1:][spec[1:].argmax()])))
    tones=pd.DataFrame(tone_rows); tones.to_csv(HERE/'judge01_expected_tones.csv',index=False)
    R['tone_summary']={}
    for (key,sensor),g in tones.groupby(['file','sensor']):
        R['tone_summary'][f'{key}|{sensor}']=dict(records=len(g),frequency_median=float(g.tone_frequency_hz.median()),harmonic_r2_median=float(g.harmonic_r2.median()),
            rms_ratio_median=float(g.tone_rms_over_sd.median()),amp_correlation=float(stats.spearmanr(g.tone_amplitude,g.current_amplitude).statistic),
            phase_R=float(np.abs(np.exp(1j*g.phase_difference).mean())),peak_quartiles=g.spectral_peak_hz.quantile([.25,.5,.75]).tolist(),
            peaks={int(k):float(v) for k,v in zip(g.record,g.spectral_peak_hz)} if key=='abnormal' else {})
    print('narrowband raw reconstruction complete',flush=True)
    sys.path.insert(0,str(GUARD))
    from model import GuardModel, StreamDetector
    models={sid:GuardModel.load(GUARD/'artifacts'/f'guard_{sid}.json') for sid in ['B','A']}
    R['model_sha256']={sid:sha(GUARD/'artifacts'/f'guard_{sid}.json') for sid in models}
    R['model_numeric_fingerprint']={sid:hashlib.sha256(np.concatenate([m.mean,m.coef,m.cal]).tobytes()).hexdigest() for sid,m in models.items()}
    alarms=[]; frozen_predictions={}
    for sid,model in models.items():
        start={'A':480,'B':420}[sid]
        test=n[sn>=start].reset_index(drop=True)
        pred=model.predict(test,.01); frozen_predictions[sid]=pred
        mp=pred.groupby('record_id').p_value.min(); mp.index=mp.index+start
        for alpha in [.01,.03,.05]:
            for state in [LOW,LOAD,'짧은 기록(<17)']:
                mask=states.state.reindex(mp.index).fillna('짧은 기록(<17)').eq(state)
                alarms.append(dict(split=sid,alpha=alpha,state=state,records=int(mask.sum()),alerted=int((mp[mask]<=alpha).sum()),records_alerted=mp[mask & (mp<=alpha)].index.tolist()))
        # Match each cumulative original-current RMS against independent prefix std; show future suffix cannot change it.
        local_seg=np.cumsum(pd.to_datetime(test.TimeStamp).diff().dt.total_seconds().sub(.1).abs().gt(1e-6).to_numpy())
        rms=np.array([test.AI2_Current.to_numpy()[np.flatnonzero((local_seg==r)&(np.arange(len(test))<=i))].std() for i,r in enumerate(local_seg)])
        count=pd.Series(local_seg).groupby(local_seg).cumcount().to_numpy()+1
        labels=np.where(count<17,'short',np.where(rms>=91.9,'load','low'))
        check(f'{sid} causal cumulative RMS',np.allclose(rms,pred.record_current_rms,atol=1e-10,rtol=0),np.max(np.abs(rms-pred.record_current_rms)))
        check(f'{sid} causal labels',np.array_equal(labels,pred.operating_state))
        for chunk in [1,7,128]:
            stream=StreamDetector(model)
            cut=test.iloc[:max(130,min(len(test),260))]
            streamed=pd.concat([stream.push(cut.iloc[i:i+chunk]) for i in range(0,len(cut),chunk)],ignore_index=True)
            check(f'{sid} chunk {chunk} state equality',np.array_equal(streamed.operating_state,pred.operating_state.iloc[:len(cut)]) and np.array_equal(streamed.record_current_rms,pred.record_current_rms.iloc[:len(cut)]))
    R['normal_alarms']=alarms
    R['loaded_calibration_test']=dict(n_cal_loaded=int(states.loc[(states.index>=300)&(states.index<420)].state.eq(LOAD).sum()),
        fixed_risk_binomial_p=float(stats.binom.sf(2,51,1/62)),shared_max_beta_binomial_p=float(stats.betabinom.sf(2,51,1,61)))
    print('frozen alerts and causal state verified',flush=True)
    # Synthetic splice reconstruction. Source pools and gains derive only from ZIP, never team states.
    rng=np.random.default_rng(20260928)
    summaries=[]
    for sid,model in models.items():
        pools={s:states.index[(states.index>={'A':480,'B':420}[sid])&states.length.eq(50)&states.state.eq(s)].to_numpy() for s in [LOW,LOAD]}
        syn,meta=[],[]
        for source,target in [(LOW,LOAD),(LOAD,LOW),(LOW,LOW),(LOAD,LOAD)]:
            for _ in range(200):
                r1=int(rng.choice(pools[source])); r2=int(rng.choice(pools[target][pools[target]!=r1]))
                a,b=X[blocks[r1]],X[blocks[r2]]
                ca,cb=tone(a[:,2],.6),tone(b[:,2],.6)
                phase=np.arctan2(ca[1],ca[0])+2*np.pi*.6*25*.1
                errors=np.abs(np.angle(np.exp(1j*(np.arctan2(cb[1],cb[0])+2*np.pi*.6*np.arange(17)*.1-phase))))
                offset=int(errors.argmin()); arr=np.vstack((a[:25],b[offset:offset+25])).copy(); arr[25:,2]+=ca[2]-cb[2]
                syn.append(arr); meta.append(dict(method='splice',direction=f'{source}→{target}',ramp_rows=0,source_record=r1,target_record=r2,control=source==target,
                    amp_ratio=states.loc[r2,'amp06']/states.loc[r1,'amp06'],phase_mismatch_deg=np.degrees(errors[offset])))
        for source,target in [(LOW,LOAD),(LOAD,LOW)]:
            gains=gain_up if source==LOW else 1/gain_up
            for ramp in [1,10,20]:
                for record in pools[source]:
                    x=X[blocks[record]]; w=np.clip((np.arange(50)-24)/ramp,0,1)
                    syn.append(x.mean(axis=0)+(x-x.mean(axis=0))*(1+w[:,None]*(gains-1)))
                    meta.append(dict(method='gain',direction=f'{source}→{target}',ramp_rows=ramp,source_record=int(record),target_record=int(record),control=False,
                        amp_ratio=gains[2],phase_mismatch_deg=0.0))
        frame=pd.DataFrame(np.concatenate(syn),columns=SENS)
        ticks=np.repeat(np.arange(len(syn))*9900,50)+np.tile(np.arange(50)*100,len(syn))
        frame.insert(0,'TimeStamp',(pd.Timestamp('2030-01-01')+pd.to_timedelta(ticks,unit='ms')).strftime('%Y-%m-%d %H:%M:%S.%f'))
        metadata=pd.DataFrame(meta)
        for alpha in [.01,.03,.05]:
            pred=model.predict(frame,alpha); alarm=pred.alarm.to_numpy().reshape(-1,50); reason=pred.reason.to_numpy().reshape(-1,50)
            check(f'{sid} alpha {alpha} synthetic boundaries',pred.record_id.nunique()==len(meta))
            ev=metadata.assign(pre=alarm[:,:25].any(1),post=alarm[:,25:].any(1),post2s=alarm[:,25:45].any(1))
            ev['first_reason']=[str(reason[i,25+np.flatnonzero(a[25:])[0]]) if a[25:].any() else '' for i,a in enumerate(alarm)]
            def summary(g,method,direction,ramp,stratum='all'):
                summaries.append(dict(split=sid,alpha=alpha,method=method,direction=direction,ramp_rows=int(ramp),stratum=stratum,records=len(g),source_records=g.source_record.nunique(),target_records=g.target_record.nunique(),
                    pre_alerted=int(g.pre.sum()),post_alerted=int(g.post.sum()),post2s_alerted=int(g.post2s.sum()),post_rate=float(g.post.mean()) if len(g) else np.nan,
                    phase_mismatch_median_deg=float(g.phase_mismatch_deg.median()),first_post_reasons=json.dumps(g.loc[g.post,'first_reason'].value_counts().to_dict(),ensure_ascii=False,sort_keys=True)))
            for (method,direction,ramp),g in ev.groupby(['method','direction','ramp_rows'],sort=False): summary(g,method,direction,ramp)
            ctl=ev[ev.control].copy(); ratio=np.maximum(ctl.amp_ratio,1/ctl.amp_ratio)
            ctl['stratum']=pd.cut(ratio,[1,1.1,1.3,1.6,np.inf],right=False,labels=['<1.1','1.1~1.3','1.3~1.6','≥1.6'])
            for label in ['<1.1','1.1~1.3','1.3~1.6','≥1.6']: summary(ctl[ctl.stratum==label],'splice_control','같은 상태',0,label)
        print(sid,'transition stress complete',flush=True)
    transition=pd.DataFrame(summaries); transition.to_csv(HERE/'judge01_expected_transition.csv',index=False)
    R['transition_alpha01']=transition[(transition.alpha==.01)&transition.stratum.eq('all')].to_dict('records')
    R['checks']=CHECKS; R['elapsed_s']=time.monotonic()-began
    R['code_sha256']={str(p.relative_to(REPO)):sha(p) for p in [Path(__file__),GUARD/'model.py',EVID/'diagnostic_probes.py',EVID/'build_diagnostics.py']}
    save('judge01_verify.json',R)
    print('DONE',len(CHECKS),'checks',sum(not c['ok'] for c in CHECKS),'failures',round(R['elapsed_s'],1),'seconds',flush=True)


if __name__=='__main__': main()
