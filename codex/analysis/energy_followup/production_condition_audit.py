"""Exploratory error strata using only completed-hour production records.

No fitting or new alarm policy. Production labels describe recorded quantities,
not verified machine running/stopped states or causal explanations.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile

import numpy as np
import pandas as pd


def summarize(group):
    truth = group.is_window_peak.to_numpy(dtype=bool)
    alarm = group.alarm_budget_03pct.to_numpy(dtype=bool)
    return dict(n=len(group), peak_windows=int(truth.sum()),
                nonpeak_windows=int((~truth).sum()), tp=int((truth & alarm).sum()),
                fn=int((truth & ~alarm).sum()), fp=int((~truth & alarm).sum()),
                tn=int((~truth & ~alarm).sum()),
                recall=float(alarm[truth].mean()) if truth.any() else None,
                fpr=float(alarm[~truth].mean()) if (~truth).any() else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.zip) as source:
        raw = source.read(next(n for n in source.namelist() if n.endswith('.csv')))
    data = pd.read_csv(io.BytesIO(raw))
    corrupt_dates = data.loc[~data['시간'].between(0, 23), '날짜'].unique()
    data = data[~data['날짜'].isin(corrupt_dates)].copy()
    base = pd.to_datetime(data['날짜'].astype(str), format='%Y%m%d') + pd.to_timedelta(data['시간'], unit='h')
    production = pd.Series(data['생산량'].to_numpy(), index=base)
    assert production.index.is_unique
    predictions = pd.read_csv(args.predictions, parse_dates=['origin_timestamp', 'window_end'])
    # A record at hour h covers that hour; h is usable only once h+1 has ended.
    recent_hour = predictions.origin_timestamp.dt.floor('h') - pd.Timedelta(hours=1)
    prior_hour = recent_hour - pd.Timedelta(hours=1)
    predictions['last_complete_hour'] = recent_hour
    predictions['production_last_complete_hour'] = production.reindex(recent_hour).to_numpy()
    predictions['production_previous_hour'] = production.reindex(prior_hour).to_numpy()
    assert ((recent_hour + pd.Timedelta(hours=1)) <= predictions.origin_timestamp).all()
    current = predictions.production_last_complete_hour
    previous = predictions.production_previous_hour
    predictions['production_record_state'] = np.select(
        [current.isna() | previous.isna(),
         (previous == 0) & (current == 0),
         (previous == 0) & (current > 0),
         (previous > 0) & (current == 0),
         (previous > 0) & (current > 0)],
        ['unknown', 'zero_to_zero', 'zero_to_positive', 'positive_to_zero', 'positive_to_positive'],
        default='other')
    ratio = predictions.origin_power / predictions.train_power95
    predictions['origin_load_band'] = pd.cut(ratio, [-np.inf, .8, .95, 1, np.inf],
                                             right=False, labels=['below80pct', '80to95pct', '95to100pct', 'already_high']).astype(str)
    rows = []
    scopes = [('all_months_exploratory', predictions),
              ('aug_sep_exploratory', predictions[predictions.month.isin([8, 9])])]
    for month, group in predictions.groupby('month'):
        scopes.append((f'month_{month}', group))
    for period, frame in scopes:
        for fields in [['production_record_state'], ['origin_load_band'],
                       ['production_record_state', 'origin_load_band']]:
            for keys, group in frame.groupby(['model'] + fields, observed=True):
                row = dict(period=period, stratification='+'.join(fields), model=keys[0])
                row.update(dict(zip(fields, keys[1:])))
                row.update(summarize(group))
                rows.append(row)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(rows)
    summary.to_csv(out/'stratified_errors.csv', index=False)
    columns = ['month', 'model', 'origin_timestamp', 'window_end', 'last_complete_hour',
               'production_last_complete_hour', 'production_previous_hour', 'production_record_state',
               'origin_power', 'train_power95', 'origin_load_band', 'is_window_peak', 'alarm_budget_03pct']
    predictions[columns].to_csv(out/'joined_audit.csv.gz', index=False, compression='gzip')
    metadata = dict(source_sha256=hashlib.sha256(raw).hexdigest(),
                    predictions_sha256=hashlib.sha256(Path(args.predictions).read_bytes()).hexdigest(),
                    assumption='Hourly production is available once its full hour has ended; actual ERP reporting delay unverified.',
                    limitations=['Zero recorded production does not prove equipment was stopped or energy was wasted.',
                                 'States describe the preceding two complete hours, not necessarily the current instant.',
                                 'No retraining, new feature selection, calibrated policy or causal improvement is tested.',
                                 'Windows overlap; subgroup denominators are not independent events.',
                                 'All dates were inspected earlier; this is post-hoc exploratory error diagnosis.',
                                 'A stratum association may be explained by time of day or season; no independent incremental effect claimed.'],
                    unknown_predictions=int((predictions.production_record_state == 'unknown').sum()))
    (out/'method.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    selected = summary.query("period=='aug_sep_exploratory' and model=='hgb_classifier' and stratification=='production_record_state'")
    print(selected.to_string(index=False))
    selected = summary.query("period=='aug_sep_exploratory' and model=='hgb_classifier' and stratification=='production_record_state+origin_load_band' and peak_windows>=10")
    print(selected.to_string(index=False))


if __name__ == '__main__':
    main()
