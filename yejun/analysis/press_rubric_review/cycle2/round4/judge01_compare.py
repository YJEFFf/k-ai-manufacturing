"""최종 생성 완료 이후 실행: 독립 ZIP 계산과 팀 표·인용·해시를 비교한다."""
from pathlib import Path
import hashlib
import json
import re
import sys
import numpy as np
import pandas as pd
from scipy import stats

HERE=Path(__file__).resolve().parent
YEJUN=HERE.parents[3]
REPO=YEJUN.parent
EVID=YEJUN/'analysis/press_evidence'
GUARD=YEJUN/'press_guard'
CHECKS=[]


def check(name,ok,detail=''):
    CHECKS.append(dict(name=name,ok=bool(ok),detail=str(detail)))
    if not ok: print('FAIL',name,detail)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(a,b,tol=1e-9): return np.allclose(np.asarray(a,float),np.asarray(b,float),rtol=0,atol=tol,equal_nan=True)


def frame_columns(tag,expected,actual,keys,cols,tol=1e-9):
    a=expected.set_index(keys).sort_index(); b=actual.set_index(keys).sort_index()
    check(tag+' row identity',a.index.equals(b.index),(len(a),len(b)))
    if not a.index.equals(b.index): return
    for col in cols:
        if pd.api.types.is_numeric_dtype(a[col]):
            delta=float(np.nanmax(np.abs(a[col].to_numpy(float)-b[col].to_numpy(float)))) if len(a) else 0
            check(tag+' '+col,close(a[col],b[col],tol),delta)
        elif col=='first_post_reasons':
            check(tag+' '+col,[json.loads(v) for v in a[col]]==[json.loads(v) for v in b[col]])
        else: check(tag+' '+col,a[col].fillna('').tolist()==b[col].fillna('').tolist())


def main():
    raw=json.loads((HERE/'judge01_verify.json').read_text())
    independent=pd.read_csv(HERE/'judge01_expected_states.csv')
    final=pd.read_csv(EVID/'operating_states.csv')
    cols=['length','current_rms_dm','AI0_sd','AI1_sd','amp06','r2_06','win_amp_ratio','p_low','state',
          'state_thr90','state_thr92','state_thr95','substate4','substate4_center']
    frame_columns('states 469',independent,final,['record'],cols)
    for col in ['start','end']:
        expected=pd.to_datetime(independent[col]).dt.strftime('%H:%M:%S.%f').str[:-3]
        check('states '+col,expected.tolist()==final[col].tolist())
    states=independent.set_index('record')
    summary=pd.read_csv(EVID/'operating_states_summary.csv').set_index('item')
    def summ(name,value,col='value',tol=1e-9):
        check('summary '+name+' '+col,name in summary.index and close(float(summary.loc[name,col]),value,tol))
    for k,v in raw['mixture']['bic_1d'].items(): summ(f'가우스 혼합 {k}성분 BIC(로그 전류 RMS)',v)
    for k,v in raw['mixture']['bic_2d'].items(): summ(f'가우스 혼합 {k}성분 BIC(로그 전류 RMS·AI1 SD)',v)
    for k,v in raw['mixture']['best_by_seed'].items(): summ(f'시드 {k} BIC 최소 성분 수',v)
    for k,v in raw['mixture']['low_jaccard'].items(): summ(f'{k}성분 저수준과 2성분 저수준 Jaccard',v)
    for k,center in enumerate(raw['mixture']['centers4']):
        summ(f'하위 수준 {k}: 전류 RMS 성분 중앙 / 혼합 가중치',center)
        summ(f'하위 수준 {k}: 전류 RMS 성분 중앙 / 혼합 가중치',raw['mixture']['weights4'][k],'value2')
    for source,targets in raw['adjacent_transition'].items():
        for target,v in targets.items():
            name=f'하위 수준 {source}→{target}'
            summ(name,v['count']/v['n']); summ(name,v['count'],'value2'); summ(name,v['n'],'n')
    sync=raw['transition_observation']
    summ('진폭 비 1.3 초과 기록',sync['observed'])
    summ('기록 안 17행 창 0.6 Hz 진폭의 최대/최소 비(중앙·90%·99%·최대)',sync['ratio_max'])
    summ('전환 관측 검정력(기록당 계단 4위치, 진폭 비>1.3)',sync['power'])
    summ('전환 관측 검정력(기록당 계단 4위치, 진폭 비>1.3)',sync['power_long'],'value2')
    summ('무작위 시각 수집의 기대 가로지름 / 평균 검정력 반영 기대 탐지',sync['expected_crossing'])
    summ('무작위 시각 수집의 기대 가로지름 / 평균 검정력 반영 기대 탐지',sync['expected_detected_approx'],'value2')
    summ('기록 길이별 검정력 가중 기대 탐지',sync['expected_detected_length_weighted'])
    transition=pd.read_csv(HERE/'judge01_expected_transition.csv')
    frame_columns('transition 84',transition,pd.read_csv(EVID/'state_transition_stress.csv'),['split','alpha','method','direction','ramp_rows','stratum'],
        ['records','source_records','target_records','pre_alerted','post_alerted','post2s_alerted','post_rate','phase_mismatch_median_deg','first_post_reasons'])
    tone=pd.read_csv(HERE/'judge01_expected_tones.csv')
    final_tone=pd.read_csv(EVID/'vibration_tones.csv')
    frame_columns('narrowband 414',tone,final_tone,['file','record','sensor'],['tone_frequency_hz'],tol=2e-7)
    frame_columns('narrowband 414',tone,final_tone,['file','record','sensor'],['tone_amplitude','current_amplitude','harmonic_r2','tone_rms_over_sd','phase_difference','spectral_peak_hz'])
    obs=pd.read_csv(EVID/'observability.csv').set_index(['file','sensor'])
    mapping={'records':'records_50rows','frequency_median':'tone_frequency_hz_median','harmonic_r2_median':'harmonic_r2_median','rms_ratio_median':'tone_rms_over_sd_median','amp_correlation':'tone_amp_current_spearman','phase_R':'phase_lock_R'}
    for key,v in raw['tone_summary'].items():
        file,sensor=key.split('|'); row=obs.loc[(file,sensor)]
        for source,col in mapping.items(): check('observability '+key+' '+col,close(row[col],v[source],2e-7))
    fm3=pd.read_csv(EVID/'failure_mode_map.csv').set_index('fm_id').loc['FM3']
    check('FM3 distinguishes narrowband aliasing',all(s in fm3.confirmed_in_this_data for s in ['1 Hz 아래','최대 주파수','5초 5기록','저주파라는 이유만으로 배제할 수 없다']))
    alarm=pd.read_csv(EVID/'normal_alarms_by_state.csv')
    for r in raw['normal_alarms']:
        mask=alarm.section.eq('상태별 정상 알림')&alarm.group.eq('동결 '+r['split'])&np.isclose(alarm.alpha,r['alpha'])&alarm.state.eq(r['state'])
        actual=alarm[mask]
        check(f"normal {r['split']} {r['alpha']} {r['state']}",len(actual)==1 and int(actual.records.iloc[0])==r['records'] and int(actual.alerted.iloc[0])==r['alerted'])
    for sid in ['A','B']:
        for alpha in [.01,.03,.05]:
            ids=sum([r['records_alerted'] for r in raw['normal_alarms'] if r['split']==sid and r['alpha']==alpha],[])
            for level in range(4):
                actual=alarm[alarm.section.eq('4성분 하위 수준별 정상 알림')&alarm.group.eq('동결 '+sid)&np.isclose(alarm.alpha,alpha)&alarm.state.eq(f'하위 {level}')].iloc[0]
                subset=states[(states.index>={'A':480,'B':420}[sid])&states.substate4.eq(level)]
                check(f'substate alarms {sid} {alpha} {level}',actual.records==len(subset) and actual.alerted==len(set(ids)&set(subset.index)))
    p=alarm[alarm.group.eq('동결 B 평가 부하 기록(α 1%)')].iloc[0]
    check('shared threshold p',close(p.p_shared_calibration,raw['loaded_calibration_test']['shared_max_beta_binomial_p']))
    check('binomial retained only as independent approximation',close(p.p_value,raw['loaded_calibration_test']['fixed_risk_binomial_p']) and '고정' in p.note and '5% 수준 위반을 단정하지 않는다' in p.note)
    comp=pd.read_csv(EVID/'split_state_composition.csv').set_index('part')
    splits={'A 학습':(0,360),'A 보정':(360,480),'A 평가':(480,600),'B 학습':(0,300),'B 보정':(300,420),'B 평가':(420,600)}
    for name,(begin,end) in splits.items():
        sub=states[(states.index>=begin)&(states.index<end)]; row=comp.loc[name]
        check('split '+name,int(row.records_len17)==len(sub) and int(row.low)==int(sub.state.eq('저수준').sum()) and int(row.records_len17-row.low)==int(sub.state.eq('부하').sum()))
    for sid in ['A','B']:
        cal,ev=comp.loc[sid+' 보정'],comp.loc[sid+' 평가']
        check('split Fisher '+sid,close(stats.fisher_exact([[cal.low,cal.records_len17-cal.low],[ev.low,ev.records_len17-ev.low]]).pvalue,ev.fisher_cal_vs_eval_p))
    var=pd.read_csv(EVID/'variable_dictionary.csv').set_index('column').loc['AI2_Current']
    check('AI2 meaning link',all(s in var.observed for s in ['저수준(중앙 83)','부하 범위(92~185)','operating_states_summary.csv']))
    decision=pd.read_csv(EVID/'decision_table_diagnosis_v2.csv')
    citations=[]
    for cell in decision.astype(str).to_numpy().ravel():
        for path,n in re.findall(r'(yejun/[\w./-]+):(\d+)',cell):
            pth=REPO/path; lineno=int(n)
            check(f'citation {path}:{n}',pth.is_file() and lineno<=len(pth.read_text().splitlines()))
            citations.append(f'{path}:{n}')
    dtext=(EVID/'decision_table_diagnosis_v2.csv').read_text()
    check('decision transition link two required rows',sum('state_transition_stress.csv:' in str(row) for row in decision.astype(str).to_numpy())>=2)
    check('decision conditional guarantee limit',all(s in dtext for s in ['주변 보장','상태 조건부 보장은 아니다','공유 보정 최대값','0.091']))
    readme=(EVID/'README.md').read_text(); guard_readme=(GUARD/'README.md').read_text()
    check('README revised relationships',all(s in readme for s in ['제품·로트·금형·스트로크 식별 열은 없다','저수준 대 부하 범위(하위 2~3수준)','실제 전환 속도·모양','Beta-Binomial(51,1,61)']))
    check('guard README state denominators',all(s in guard_readme for s in ['부하 기록은 21개','부하 기록은 51개','평가 A 78%·B 65%','보정 A 35%·B 32%']))
    check('guard continuous transition constraint','전환이 든 정상 연속 자료로 재보정·재검증하기 전에는 대회 오경보 수치를 옮기지 않는다' in guard_readme)
    # Final manifest coverage, outputs, model/source/citation hashes; contract verifies frozen expected values separately.
    sys.path.insert(0,str(YEJUN/'analysis'))
    import package_contract as pc
    contract=pc.load_contract(EVID)
    for manifest,spec in contract['manifests'].items():
        payload=json.loads((EVID/manifest).read_text())
        for group,rule in spec['groups'].items():
            for key,digest in payload[group].items():
                path=pc.resolve(key,rule,EVID,EVID)
                check(f'manifest {manifest} {group} {key}',path is not None and path.is_file() and sha(path)==digest)
    check('contract includes transitions and tones',all(s in contract['outputs'] for s in ['state_transition_stress.csv','vibration_tones.csv']))
    sys.path.insert(0,str(GUARD))
    from model import GuardModel
    for sid,expected in raw['model_numeric_fingerprint'].items():
        model=GuardModel.load(GUARD/'artifacts'/f'guard_{sid}.json')
        got=hashlib.sha256(np.concatenate([model.mean,model.coef,model.cal]).tobytes()).hexdigest()
        check('frozen numeric parameters '+sid,got==expected)
    result=dict(checks=CHECKS,passed=sum(c['ok'] for c in CHECKS),failed=sum(not c['ok'] for c in CHECKS),citations=citations,
        final_files={str(p.relative_to(REPO)):sha(p) for p in [EVID/'build_diagnostics.py',EVID/'diagnostic_probes.py',EVID/'build_tables.py',EVID/'figures.py',EVID/'README.md',GUARD/'model.py',GUARD/'README.md']})
    (HERE/'judge01_compare.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('DONE',len(CHECKS),'checks',result['failed'],'failures')
    raise SystemExit(bool(result['failed']))


if __name__=='__main__': main()
