"""Audit peak entry versus continued high load from saved predictions, without refitting."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from classifier_experiment import counts

out = Path(__file__).resolve().parent
p = pd.read_csv(out/'classifier_predictions.csv.gz', parse_dates=['timestamp'])
if 'origin_power' not in p:
    origin = p.loc[p['model'].eq('recent_value'), ['timestamp', 'horizon_minutes', 'score']].rename(columns={'score': 'origin_power'})
    assert not origin.duplicated(['timestamp', 'horizon_minutes']).any()
    p = p.merge(origin, on=['timestamp', 'horizon_minutes'], how='left', validate='many_to_one')
    p['origin_timestamp'] = p['timestamp'] - pd.to_timedelta(p['horizon_minutes'], unit='min')
    p['origin_is_peak'] = p['origin_power'] >= p['train_peak_threshold']
    p['new_peak_entry'] = p['is_peak'] & ~p['origin_is_peak']
    p['continued_peak'] = p['is_peak'] & p['origin_is_peak']
    assert p['origin_power'].notna().all()
    temp = out/'classifier_predictions.tmp.csv.gz'
    p.to_csv(temp, index=False, compression='gzip')
    temp.replace(out/'classifier_predictions.csv.gz')

records = []
periods = {m: p['test_month'].eq(m) for m in sorted(p['test_month'].unique())}
periods['all_months'] = np.ones(len(p), dtype=bool)
periods['aug_sep_exploratory'] = p['test_month'].isin(['2021-08', '2021-09'])
for period, selected in periods.items():
    for profile_subset, profile_mask in {
        'all': np.ones(len(p), dtype=bool),
        'new_daily_profile': p['is_new_daily_profile'],
        'repeated_daily_profile': ~p['is_new_daily_profile'],
    }.items():
        q = p.loc[selected & profile_mask]
        for (h, model), g in q.groupby(['horizon_minutes', 'model']):
            for budget in [.01, .03, .05]:
                alarm = g[f'alarm_budget_{int(budget*100):02}pct'].to_numpy()
                new = g['new_peak_entry'].to_numpy()
                continuing = g['continued_peak'].to_numpy()
                origin_normal = ~g['origin_is_peak'].to_numpy()
                origin_normal_stats = counts(g['is_peak'].to_numpy()[origin_normal], alarm[origin_normal])
                records.append({
                    'period': period, 'subset': profile_subset,
                    'horizon_minutes': int(h), 'model': model, 'calibration_fpr_budget': budget,
                    'new_peak_entry_n': int(new.sum()),
                    'new_peak_entry_detected': int(alarm[new].sum()),
                    'new_peak_entry_recall': float(alarm[new].mean()) if new.any() else None,
                    'continued_peak_n': int(continuing.sum()),
                    'continued_peak_detected': int(alarm[continuing].sum()),
                    'continued_peak_recall': float(alarm[continuing].mean()) if continuing.any() else None,
                    'origin_normal_target_normal_n': origin_normal_stats['negatives'],
                    'origin_normal_false_alarms': origin_normal_stats['fp'],
                    'origin_normal_false_positive_rate': origin_normal_stats['false_positive_rate'],
                })
pd.DataFrame(records).to_csv(out/'classifier_transition_metrics.csv', index=False)
(out/'classifier_transition_results.json').write_text(json.dumps({
    'definition': 'new entry: target power >= train95 threshold and forecast-origin power < same threshold; continued peak: both >= threshold',
    'interpretation': 'Counts target quarters, not independent peak episodes. A 60-minute endpoint is not any-time-within-hour warning.',
    'origin_power_reconstruction': 'Same timestamp+horizon recent_value score from saved model predictions; no additional fit or outcome-based threshold selection.',
    'results': records,
}, ensure_ascii=False, indent=2))
print(pd.DataFrame(records).query("period == 'aug_sep_exploratory' and subset == 'new_daily_profile' and calibration_fpr_budget == .05").to_string(index=False))
