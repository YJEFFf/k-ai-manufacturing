"""평가관03 4회차 읽기 전용 검수. 팀 insights 함수 없이 원자료·저장모델로 재계산.

OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
  analysis/press_rubric_review/cycle2/round4/judge03_verify.py
쓰기는 이 디렉터리의 judge03_*뿐이다. 통계 참고 구현은 statsmodels/scipy다.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import time
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.contingency_tables import StratifiedTable
from statsmodels.stats.multitest import multipletests

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]
G = Y / 'press_guard'
O = G / 'outputs'
sys.path.insert(0, str(G))
from model import GuardModel, D, layout, alert_units
from press.calibrate import conformal_p, segment_max
from press.scores import ExpTail

START = time.monotonic()
RESULT = {}
CHECKS = []
S = D.SENSORS
ALPHAS = (.01, .03, .05)
FAMILIES = (('vib_noise', 2.), ('cur_noise', .1), ('cur_offset', .2), ('cur_gain', 1.15), ('cur_gain', 1.3))


def log(*args):
    print(f'[{time.monotonic() - START:.1f}s]', *args, flush=True)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check(name, got, expected, atol=1e-9):
    if isinstance(expected, (str, bool)):
        ok = got == expected
        err = None
    else:
        ok = np.allclose(got, expected, rtol=1e-9, atol=atol, equal_nan=True)
        diff = np.abs(np.asarray(got, float) - np.asarray(expected, float))
        err = float(np.nanmax(diff)) if np.isfinite(diff).any() else 0.
    CHECKS.append(dict(name=name, ok=bool(ok), max_abs_error=err))
    if not ok:
        log('MISMATCH', name, got, expected)
    return bool(ok)


def cp(k, n):
    if not n:
        return np.nan, np.nan
    return (float(stats.beta.ppf(.025, k, n-k+1)) if k else 0.,
            float(stats.beta.ppf(.975, k+1, n-k)) if k < n else 1.)


def fisher(k, n, k0, n0):
    return stats.fisher_exact([[k, n-k], [k0, n0-k0]], alternative='greater').pvalue


def prep(frame):
    q = D.quantize(D.inputs_only(frame), 'matched')
    return q, layout(q)[1]


def features(frame, seg):
    values = frame[S].to_numpy(float)
    rows = []
    for rid in np.unique(seg):
        x = values[seg == rid]
        var = x.var(axis=0, ddof=1) if len(x) > 1 else [np.nan] * 3
        rms = np.sqrt(np.mean((x[:, 2] - x[:, 2].mean()) ** 2))
        rows.append(dict(record=int(rid), length=len(x), amp=float(np.sqrt(2)*rms),
                         rms=float(rms), vib_sd=float(np.sqrt(var[0]+var[1]))))
    return pd.DataFrame(rows)


def check_numbers(label, row, values):
    for key, value in values.items():
        check(f'{label}/{key}', row[key], value)


def boot_mean_miss(detection, seed=11, repeats=4000):
    d = np.asarray(detection, float)
    ix = np.random.default_rng(seed).integers(len(d), size=(repeats, len(d)))
    return np.quantile(1 - d[ix].mean(axis=1), [.025, .975])


def block_reference(g, exposure):
    """층별 2×2 표 + 조건부 hypergeometric 합의 정확분포도 계산한다."""
    x, y = np.asarray(exposure, bool), g.fa.to_numpy(bool)
    labels = g.absolute.to_numpy() // 60
    tabs, dist, all_tabs = [], np.array([1.]), []
    perm = np.zeros(20000, int)
    rng = np.random.default_rng(3)
    for label in np.unique(labels):
        ix = np.flatnonzero(labels == label)
        n, ne, na = len(ix), int(x[ix].sum()), int(y[ix].sum())
        a = int((x[ix] & y[ix]).sum())
        tab = np.array([[a, ne-a], [na-a, n-ne-na+a]], dtype=float)
        all_tabs.append(dict(block=int(label), table=tab.tolist()))
        if tab.sum(0).min() > 0 and tab.sum(1).min() > 0:
            tabs.append(tab)
        dist = np.convolve(dist, stats.hypergeom.pmf(np.arange(min(ne, na)+1), n, ne, na))
        # RNG convention reproduction, independent from team helper.
        draws = rng.permuted(np.tile(x[ix], (20000, 1)), axis=1)
        perm += draws[:, y[ix]].sum(1)
    ref = StratifiedTable(tabs)
    cmh = ref.test_null_odds(correction=True)
    obs = int((x & y).sum())
    return dict(mh_pooled_or=float(ref.oddsratio_pooled), cmh_statistic=float(cmh.statistic),
                cmh_p=float(cmh.pvalue), cmh_continuity_correction=.5,
                cmh_informative_blocks=len(tabs), permutation_p_greater=float((1+(perm >= obs).sum())/20001),
                permutation_repeats=20000, permutation_seed=3, exact_conditional_p=float(dist[obs:].sum()),
                block_tables=all_tabs)


def main():
    watched = [G / 'insights.py', G / 'test_insights.py', G / 'model.py', G / 'README.md',
               Y / 'analysis/press_evidence/README.md', Y / 'analysis/press_evidence/normal_alarms_by_state.csv',
               Y / 'analysis/press_evidence/operating_states.csv', Y / 'analysis/press_selection/fp_mitigation_injection_v2.csv',
               Y / 'analysis/press_supplement/e1_summary.csv', Y / 'analysis/press_supplement/e1_manifest.json']
    watched += [O / name for name in ('fp_intensity_v2.csv', 'fn_intensity_v2.csv', 'error_condition_summary_v2.csv',
                'sensor_importance_v2.csv', 'ablation_v2.csv', 'position_vibration_misses_v2.csv', 'coupling_fit_v2.csv',
                'coupling_records_v2.csv', 'fp_events_v2.csv', 'near_miss_v2.csv', 'near_miss_corr_v2.csv')]
    watched += sorted((G / 'artifacts').glob('*.json'))
    before = {str(p.relative_to(Y)): sha(p) for p in watched}
    RESULT['head'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Y, text=True).strip()
    RESULT['initial_hashes'] = before
    normal, abnormal, report = D.load(Y / 'press_submission')
    RESULT['input_sha256'] = {k: v['sha256'] for k, v in report['files'].items()}
    models = {sid: GuardModel.load(G / 'artifacts' / f'guard_{sid}.json') for sid in 'AB'}
    seg_all = D.segments(normal)
    splits = {sid: D.split_normal(normal, seg_all, sid) for sid in 'AB'}
    manifest = json.loads((O / 'manifest.json').read_text())
    RESULT['model_manifest_matches'] = {sid: sha(G/'artifacts'/f'guard_{sid}.json') == manifest['artifacts'][f'guard_{sid}.json'] for sid in 'AB'}
    baseline = json.loads(subprocess.check_output(['git', 'show', '6c61a88:yejun/press_guard/outputs/manifest.json'], cwd=Y, text=True))
    RESULT['all_model_hashes_unchanged_from_baseline'] = {name: digest == baseline['artifacts'].get(name)
                                                       for name, digest in manifest['artifacts'].items()}
    metrics = pd.read_csv(O / 'metrics.csv')
    recount = []
    for sid, model in models.items():
        for alpha in ALPHAS:
            pn, pa = model.predict(splits[sid]['test'], alpha), model.predict(abnormal, alpha)
            row = metrics[metrics.split.eq(sid) & metrics.model.eq('guard_v2') & metrics.alpha.eq(alpha)].iloc[0]
            vals = dict(tp=int(pa.alarm.sum()), fp=int(pn.alarm.sum()), fn=int((1-pa.alarm).sum()),
                        normal_notified_segments=int(pn.groupby('record_id').alarm.max().sum()),
                        abnormal_notified_segments=int(pa.groupby('record_id').alarm.max().sum()))
            check_numbers(f'primary/{sid}/{alpha}', row, vals)
            recount.append(dict(split=sid, alpha=alpha, **vals))
    RESULT['primary_recount'] = recount
    log('Primary predictions verified')

    # FP: all seven fits, deduplicate identical calibration, then rebuild each table row.
    fits = {'frozen_A': (models['A'], 480, 600), 'frozen_B': (models['B'], 420, 600)}
    for end in (180, 240, 300, 360, 420):
        mm = GuardModel.fit(normal[seg_all < end], normal[(seg_all >= end) & (seg_all < end+120)], split=f'judge_{end}')
        fits[f'rolling_test_{end+120}_{end+179}'] = (mm, end+120, end+180)
    ev, seen, duplicate = [], {}, {}
    for name, (model, lo, hi) in fits.items():
        key = tuple(np.round(np.sort(model.cal), 12))
        if key in seen:
            duplicate[name] = seen[key]
            continue
        seen[key] = name
        frame = normal[(seg_all >= lo) & (seg_all < hi)]
        q, seg = prep(frame)
        f, raw = features(q, seg), features(D.inputs_only(frame), seg)
        f['state'] = np.where(f.length < 17, 'short', np.where(raw.rms >= 91.9, 'load', 'low'))
        f['raw_rms'] = raw.rms
        f['absolute'] = f.record + lo
        for alpha in ALPHAS:
            pr = model.predict(frame, alpha)
            ev.append(f.assign(model=name, alpha=alpha, fa=f.record.map(pr.groupby('record_id').alarm.max())))
    ev = pd.concat(ev, ignore_index=True)
    ev.to_csv(HERE / 'judge03_fp_evaluations.csv', index=False)
    base = ev[ev.alpha.eq(.01)]
    ampq = base[base.length >= 17].amp.quantile([.25, .5, .75]).to_numpy()
    vsdq = base.vib_sd.quantile([.25, .5, .75]).to_numpy()
    qb, sb = prep(splits['B']['train'])
    fb = features(qb, sb)
    bq75 = fb[fb.length >= 17].amp.quantile(.75)
    fp = pd.read_csv(O / 'fp_intensity_v2.csv')
    fp_details = []
    for idx, row in fp.iterrows():
        if pd.isna(row.value):
            row['value'] = 'nan'  # CSV's literal category "nan" is read as NA.
        g = ev[ev.alpha.eq(row.alpha)].reset_index(drop=True)
        extra = {}
        if row.condition == 'amp_quartile':
            labels = np.where(g.length < 17, '짧은 기록(<17)', pd.cut(g.amp, [-np.inf, *ampq, np.inf], labels=['Q1', 'Q2', 'Q3', 'Q4']).astype(str))
            use = labels == row.value
        elif row.condition == 'vib_sd_quartile':
            use = pd.cut(g.vib_sd, [-np.inf, *vsdq, np.inf], labels=['Q1','Q2','Q3','Q4']).astype(str) == row.value
        elif row.condition == 'block':
            use = g.absolute // 60 == int(row.value.split('~')[0]) // 60
        elif row.condition == 'operating_state':
            use = g.state == row.value
            extra.update(state_rms_threshold=91.9, state_min_rows=17)
        elif row.condition == 'amp_high':
            g = g.groupby('absolute').agg(fa=('fa','max'), amp=('amp','first'), length=('length','first'), state=('state','first'))
            cutoff = bq75 if 'B 정상 학습' in row.value else ampq[2]
            use = (g.length >= 17) & (g.amp >= cutoff)
            check(f'FP/{idx+2}/all_load', row.exposed_all_load, bool(g.loc[use].state.eq('load').all()))
        elif row.condition == 'amp_high_block_stratified':
            cutoff = bq75 if 'B 정상 학습' in row.value else ampq[2]
            use = (g.length >= 17) & (g.amp >= cutoff)
            ref = block_reference(g, use)
            extra.update({k: v for k,v in ref.items() if k not in ('exact_conditional_p', 'block_tables')})
            extra['threshold'] = cutoff
            fp_details.append(dict(alpha=row.alpha, exposure=row.value, **ref))
        elif row.condition == 'amp_within_load':
            g = g[g.state.eq('load')]
            cutoff = float(g.amp.median())
            use = g.amp >= cutoff
            rho = stats.spearmanr(g.amp, g.fa)
            extra.update(threshold=cutoff, spearman_amp=rho.statistic, spearman_p=rho.pvalue)
        else:
            raise ValueError(row.condition)
        k, n = int(g.loc[use].fa.sum()), int(np.sum(use))
        assert n > 0, (idx, row.condition, row.value)
        k0, n0 = int(g.loc[~use].fa.sum()), int(np.sum(~use))
        low, high = cp(k, n)
        expected = dict(false_alarms=k, denominator=n, rate=k/n, ci_low=low, ci_high=high,
                        comparison_false_alarms=k0, comparison_denominator=n0,
                        lift=(k/n)/((k+k0)/(n+n0)) if k+k0 else np.nan, **extra)
        if pd.notna(row.fisher_p_greater):
            expected['fisher_p_greater'] = fisher(k, n, k0, n0)
        check_numbers(f'FP/{idx+2}', row, expected)
    state_team = pd.read_csv(Y / 'analysis/press_evidence/normal_alarms_by_state.csv')
    state_name = {'load': '부하', 'low':'저수준', 'short':'짧은 기록(<17)'}
    matches = []
    for alpha in ALPHAS:
        for state in ('load', 'low', 'short'):
            g = ev[ev.alpha.eq(alpha) & ev.state.eq(state)]
            tt = state_team[state_team.group.eq('독립 적합 합침') & state_team.alpha.eq(alpha) & state_team.state.eq(state_name[state])]
            if len(tt):
                matches.append(check(f'state_evidence/{alpha}/{state}', [int(g.fa.sum()), len(g)], tt.iloc[0][['alerted','records']].to_numpy(float)))
    RESULT['FP'] = dict(rows=len(fp), evaluation_count=len(base), unique_count=base.absolute.nunique(), fits=list(seen.values()), duplicates=duplicate,
                        quartiles=ampq.tolist(), b_train_q75=float(bq75), block_results=fp_details,
                        state_totals=ev.groupby(['alpha','state']).agg(alerts=('fa','sum'), records=('fa','size')).reset_index().to_dict('records'),
                        evidence_group_candidates=state_team.group.unique().tolist(), evidence_matches=matches)
    log('FP verified', len(fp), 'rows, blocks via statsmodels and exact hypergeometric convolution')

    # FN: independent injection implementation, seeds 0..49, unit bootstrap, paired correlations.
    fn = pd.read_csv(O / 'fn_intensity_v2.csv')
    host, outcomes, fn_details, shock_details = {}, {}, [], []
    for sid, model in models.items():
        frame = D.inputs_only(splits[sid]['test']).reset_index(drop=True)
        for c in S:
            frame[c] = pd.to_numeric(frame[c])
        seg = layout(frame)[1]
        pos, length = D.segment_positions(seg)
        units = alert_units(seg, pos)
        check(f'{sid}/record_equals_unit', np.array_equal(seg, units), True)
        eligible = np.unique(seg[length >= 30])
        mask = np.isin(seg, eligible) & (pos >= 10)
        window = (pos >= 10) & (pos < 30)
        q, _ = prep(frame)
        f = features(q, seg).set_index('record').loc[eligible]
        amp, vsd = f.amp.to_numpy(), f.vib_sd.to_numpy()
        aq = np.asarray(pd.qcut(amp, 4, labels=['Q1','Q2','Q3','Q4']).astype(str))
        host[sid] = dict(amp=amp, vsd=vsd, aq=aq, eligible=eligible)
        for family, level in FAMILIES:
            detections = []
            nrep = 50 if family in ('cur_noise','vib_noise') else 1
            for rep in range(nrep):
                rng, injected = np.random.default_rng(rep), frame.copy()
                if family == 'vib_noise':
                    for j in (0, 1):
                        injected.loc[mask,S[j]] += level * model.scale[j] * rng.normal(size=int(mask.sum()))
                elif family == 'cur_noise':
                    injected.loc[mask,S[2]] += level * model.scale[2] * rng.normal(size=int(mask.sum()))
                elif family == 'cur_offset':
                    injected.loc[mask,S[2]] += level * np.sqrt(2) * model.scale[2]
                elif family == 'cur_gain':
                    injected.loc[mask,S[2]] = model.mean[2] + level * (injected.loc[mask,S[2]] - model.mean[2])
                pred = model.predict(injected, .01)
                det = pd.Series(pred.alarm.to_numpy(bool) & window).groupby(seg).any().reindex(eligible).to_numpy(float)
                detections.append(det)
            arr = np.asarray(detections)
            d = arr.mean(0)
            outcomes[(sid, family, level)] = d
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                ra, rv = stats.spearmanr(amp,d), stats.spearmanr(vsd,d)
            vals = dict(units=len(eligible), detect_mean=d.mean(), spearman_amp=ra.statistic, p_amp=ra.pvalue,
                        spearman_vib_sd=rv.statistic, p_vib_sd=rv.pvalue, injection_repeats=nrep,
                        injection_seed_start=0 if nrep>1 else np.nan, injection_seed_end=nrep-1 if nrep>1 else np.nan)
            for lab in ('Q1','Q2','Q3','Q4'):
                dd = d[aq == lab]
                lo, hi = boot_mean_miss(dd)
                vals.update({f'detected_amp_{lab}': dd.sum(), f'units_amp_{lab}':len(dd),
                             f'miss_amp_{lab}_ci_low':lo, f'miss_amp_{lab}_ci_high':hi})
            row = fn[fn.split.eq(sid) & fn.family.eq(family) & np.isclose(fn.level_value,level)].iloc[0]
            check_numbers(f'FN/{sid}/{family}/{level}',row,vals)
            fn_details.append(dict(split=sid,family=family,level=level,**vals))
            pd.DataFrame(dict(record=eligible, amp=amp, vib_sd=vsd, quartile=aq, mean_detection=d)).to_csv(
                HERE/f'judge03_fn_units_{sid}_{family}_{level:g}.csv',index=False)
            log('FN',sid,family,level,'mean',round(float(d.mean()),6))
        dv, do = outcomes[(sid,'vib_noise',2.)], outcomes[(sid,'cur_offset',.2)]
        rng = np.random.default_rng(11)
        boots = []
        for _ in range(4000):
            ix = rng.integers(len(amp),size=len(amp))
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                delta = stats.spearmanr(amp[ix],dv[ix]).statistic - stats.spearmanr(amp[ix],do[ix]).statistic
            if np.isfinite(delta):
                boots.append(delta)
        ci = np.quantile(boots,[.025,.975])
        row = fn[fn.split.eq(sid) & fn.family.eq('vib_noise')].iloc[0]
        vals = dict(interaction_rho_difference=stats.spearmanr(amp,dv).statistic-stats.spearmanr(amp,do).statistic,
                    interaction_ci_low=ci[0],interaction_ci_high=ci[1],interaction_bootstrap_repeats=4000,
                    interaction_bootstrap_valid=len(boots),interaction_bootstrap_seed=11,
                    interaction_bootstrap_share_le_zero=float(np.mean(np.asarray(boots)<=0)))
        check_numbers(f'interaction/{sid}',row,vals)
        RESULT[f'interaction_{sid}'] = vals
        # 단발 충격의 공개 요약값을 독립 재계산하고 반복 의존성 규모를 참고로 확인한다.
        for level in (4.,6.):
            draws=[]
            imask=np.isin(seg,eligible)&(pos==10)
            for rep in range(5):
                injected=frame.copy()
                signs=np.random.default_rng(rep).choice([-1.,1.],size=(int(imask.sum()),2))
                for j in (0,1):
                    injected.loc[imask,S[j]] += level*model.scale[j]*signs[:,j]
                pred=model.predict(injected,.01)
                draws.append(pd.Series(pred.alarm.to_numpy(bool)&window).groupby(seg).any().reindex(eligible).to_numpy(float))
            ds=np.asarray(draws)
            ss=pd.read_csv(Y/'analysis/press_selection/fp_mitigation_injection_v2.csv')
            rr=ss[ss.split_id.eq(sid)&ss.alpha.eq(.01)&ss.family.eq('vib_shock')&ss.level.eq(level)].iloc[0]
            check(f'shock/{sid}/{level}',rr.v2_detect_2s,ds.mean())
            shock_details.append(dict(split=sid,level=level,units=len(eligible),repeats=5,detect=float(ds.mean()),
                                      misses=int((1-ds).sum()),bernoulli_trial_ci=cp(int((1-ds).sum()),ds.size),
                                      unit_bootstrap_miss_ci=boot_mean_miss(ds.mean(0)).tolist()))
    for key,pvals in [('amp',fn.p_amp.to_numpy()),('joint',np.r_[fn.p_amp,fn.p_vib_sd])]:
        keep=np.isfinite(pvals)
        qvals=np.full_like(pvals,np.nan)
        qvals[keep]=multipletests(pvals[keep],method='fdr_bh')[1]
        if key=='amp':
            check('BH/amp',fn.q_amp_bh,qvals)
            check('BH/amp_count',fn.n_tests_amp,np.full(len(fn),keep.sum()))
            check('Bonferroni/amp',fn.p_amp_bonferroni,np.minimum(1,pvals*keep.sum()))
        else:
            check('BH/joint_amp',fn.q_amp_joint_bh,qvals[:len(fn)])
            check('BH/joint_vib',fn.q_vib_sd_joint_bh,qvals[len(fn):])
            check('BH/joint_count',fn.n_tests_amp_vib_sd,np.full(len(fn),keep.sum()))
            check('Bonferroni/joint',fn.p_amp_joint_bonferroni,np.minimum(1,fn.p_amp*keep.sum()))
    RESULT['FN']=fn_details
    RESULT['shock_reference']=shock_details
    # E1 record outputs are input evidence only; their hashes establish identity.
    erpath=Y/'analysis/press_supplement/predictions_e1_records.csv'
    erm=json.loads((Y/'analysis/press_supplement/e1_manifest.json').read_text())
    RESULT['E1_record_hash_matches']=sha(erpath)==erm['local_outputs']['predictions_e1_records.csv']
    er=pd.read_csv(erpath)
    er=er[er.model.eq('guard_v2')&er.alpha.eq(.01)&er['shape'].eq('step')&er.t0.eq(10)]
    e1cmp=[]
    for sid in 'AB':
        for family,level in FAMILIES:
            g=er[er.split.eq(sid)&er.family.eq(family)&np.isclose(er.level,level)]
            d=g.groupby('record').detected_2s.mean().reindex(host[sid]['eligible']).to_numpy()
            if family not in ('cur_noise','vib_noise'):
                check(f'E1_deterministic/{sid}/{family}/{level}',d,outcomes[(sid,family,level)])
            e1cmp.append(dict(split=sid,family=family,level=level,mean=float(d.mean())))
    RESULT['E1_comparison']=e1cmp
    log('FN, paired bootstrap, BH and E1 checked')

    # Component ablation: recombine saved-model components, independently recalibrate each variant.
    ab=pd.read_csv(O/'ablation_v2.csv')
    RESULT['ablation']=[]
    for sid,model in models.items():
        parts={}
        for name,frame in [('cal',splits[sid]['cal']),('test',splits[sid]['test']),('abn',abnormal)]:
            q,seg=prep(frame)
            parts[name]=(model.components(q,seg),seg)
        # names are matched to declared CSV variants below.
        for variant,keep in [('v2',('g_magnitude','g_waveform','g_dynamics')),
                             ('v2_no_waveform',('g_magnitude','g_dynamics')),
                             ('v2_no_dynamics',('g_magnitude','g_waveform')),
                             ('v2_no_magnitude',('g_waveform','g_dynamics'))]:
            scores={k:np.fmax.reduce([v[0][c] for c in keep]) for k,v in parts.items()}
            cal=segment_max(scores['cal'],parts['cal'][1])
            alarm={k:np.nan_to_num(conformal_p(cal,scores[k]),nan=1)<=.01 for k in ('test','abn')}
            vals=dict(fn=int((~alarm['abn']).sum()),fp=int(alarm['test'].sum()),
                      abnormal_notified_segments=int(pd.Series(alarm['abn']).groupby(parts['abn'][1]).max().sum()),
                      normal_notified_segments=int(pd.Series(alarm['test']).groupby(parts['test'][1]).max().sum()))
            candidate=ab[ab.split_id.eq(sid)&ab.criterion.eq('conformal')&ab.alpha.eq(.01)]
            match=candidate[(candidate.fn==vals['fn'])&(candidate.fp==vals['fp'])]
            check(f'ablation/{sid}/{variant}/matching_row_count',len(match)>=1,True)
            RESULT['ablation'].append(dict(split=sid,variant=variant,**vals,matching_csv_models=match.model.tolist()))
    RESULT['ablation_csv_variants']=ab.model.unique().tolist()
    log('Component ablations checked')

    # Summary: all cited CSV rows must exist; numeric ratios/CI/lift must be self-consistent.
    sm=pd.read_csv(O/'error_condition_summary_v2.csv')
    check('summary/count',len(sm),12)
    check('summary/readme_rows',len(re.findall(r'^\| (미탐|오경보) \|',(G/'README.md').read_text(),re.M)),12)
    citation_records=[]
    for i,row in sm.iterrows():
        cited={}
        for entry in row.source.split(';'):
            path,spec=entry.strip().rsplit(':',1)
            lines=[]
            for token in spec.split(','):
                if '-' in token:
                    lo,hi=map(int,token.split('-'))
                    lines.extend(range(lo,hi+1))
                else:
                    lines.append(int(token))
            data=pd.read_csv(Y/path)
            check(f'cite/{i+2}/{path}',all(2<=ln<=len(data)+1 for ln in lines),True)
            cited[path]=lines
        citation_records.append(dict(row=i+2,condition=row.condition,citations=cited))
        for sid in 'AB':
            k,n=row[f'errors_{sid}'],row[f'denominator_{sid}']
            rate=k/n if n else np.nan
            check(f'summary/{i+2}/{sid}/rate',row[f'rate_{sid}'],rate)
            comp=row[f'comparison_rate_{sid}']
            lift=rate/comp if comp>0 else np.nan
            check(f'summary/{i+2}/{sid}/lift',row[f'lift_{sid}'],lift)
            if i==4:
                rr=fn[fn.split.eq(sid)&fn.family.eq('vib_noise')].iloc[0]
                expected=[rr.miss_amp_Q1_ci_low,rr.miss_amp_Q1_ci_high]
                check(f'summary/{i+2}/{sid}/fractional_mean',k,float(rr.units_amp_Q1-rr.detected_amp_Q1))
                check(f'summary/{i+2}/{sid}/bootstrap_method','재표집' in row.ci_method,True)
            else:
                expected=cp(k,n)
            check(f'summary/{i+2}/{sid}/CI',[row[f'ci_low_{sid}'],row[f'ci_high_{sid}']],expected)
    RESULT['summary_citations']=citation_records
    # Numerators from source tables for all summaries, with split/alpha exceptions explicit.
    fp_ev=pd.read_csv(O/'fp_events_v2.csv')
    ind=fp_ev[fp_ev.independent&fp_ev.alpha.eq(.05)]
    check('summary/AI0_events',sm.iloc[8][['errors_A','denominator_A']].to_numpy(float),[int(((ind.reasons=='magnitude')&(ind.magnitude_sensor==S[0])).sum()),len(ind)])
    check('summary/single_row_events',sm.iloc[8][['errors_B','denominator_B']].to_numpy(float),[int((ind.alarm_rows==1).sum()),len(ind)])
    pv=pd.read_csv(O/'position_vibration_misses_v2.csv')
    for sid in 'AB':
        for i,vib in [(0,'vibration_normal_range'),(1,'all')]:
            rr=pv[pv.split.eq(sid)&pv.position.eq('0-1')&pv.vibration.eq(vib)].iloc[0]
            check(f'summary/{i+2}/{sid}/position_source',sm.iloc[i][[f'errors_{sid}',f'denominator_{sid}']].to_numpy(float),[rr.missed_rows,rr.rows])
        for i,family,level,q in [(4,'vib_noise',2.,'Q1'),(5,'cur_offset',.2,'Q4')]:
            rr=fn[fn.split.eq(sid)&fn.family.eq(family)&fn.level_value.eq(level)].iloc[0]
            check(f'summary/{i+2}/{sid}/fn_source',sm.iloc[i][[f'errors_{sid}',f'denominator_{sid}']].to_numpy(float),[rr[f'units_amp_{q}']-rr[f'detected_amp_{q}'],rr[f'units_amp_{q}']])
    RESULT['shared_threshold_reference_p']=float(stats.betabinom.sf(2,51,1,61))
    # 423/461/570 identifiers preserved across evidence tables.
    nm=pd.read_csv(O/'near_miss_v2.csv')
    cr=pd.read_csv(O/'coupling_records_v2.csv')
    check('IDs/fp',sorted(fp_ev[fp_ev.model.eq('frozen_B')&fp_ev.alpha.eq(.01)].record),[423,461,570])
    check('IDs/near_miss',sorted(nm[nm.split.eq('B')&(nm.ratio_to_threshold>1)].absolute_record),[423,461,570])
    check('IDs/coupling',sorted(cr[cr.split.eq('B')&cr.false_alarm.astype(bool)].absolute_record),[423,461,570])
    after={str(p.relative_to(Y)):sha(p) for p in watched}
    RESULT['final_hashes']=after
    RESULT['changed_files_during_review']=[p for p in before if before[p]!=after[p]]
    RESULT['head_after']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Y,text=True).strip()
    RESULT['checks']=CHECKS
    RESULT['checks_total']=len(CHECKS)
    RESULT['checks_failed']=[c for c in CHECKS if not c['ok']]
    RESULT['elapsed_s']=round(time.monotonic()-START,2)
    (HERE/'judge03_verify.json').write_text(json.dumps(D.to_jsonable(RESULT),ensure_ascii=False,indent=2),encoding='utf-8')
    log('DONE',len(CHECKS),'checks, failed',len(RESULT['checks_failed']),'elapsed',RESULT['elapsed_s'])


if __name__=='__main__':
    main()
