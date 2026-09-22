"""Fixed chronological high-load classifier audit, without parameter search.

Run: /tmp/kamp-review-venv/bin/python analysis/energy_followup/classifier_experiment.py
Only classifier_* outputs in this directory are written; raw data are unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import signal
import zipfile

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def load_source(path):
    def timeout(signum, frame):
        raise TimeoutError('Source archive read exceeded 20 seconds')
    old = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(20)
    try:
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            member = next(n for n in z.namelist() if n.endswith('.csv'))
            raw = z.read(member)
        return pd.read_csv(io.BytesIO(raw)), hashlib.sha256(raw).hexdigest()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def calibration_threshold(normal_scores, budget):
    """Alarm iff score > threshold; ties conservative, empirical normal FP <= budget."""
    s = np.sort(np.asarray(normal_scores, dtype=float))
    assert len(s) and np.isfinite(s).all()
    k = int(np.floor(budget * len(s)))
    return float(s[len(s) - k - 1])


def counts(actual, predicted):
    actual = np.asarray(actual, dtype=bool)
    predicted = np.asarray(predicted, dtype=bool)
    tp = int((actual & predicted).sum())
    fp = int((~actual & predicted).sum())
    fn = int((actual & ~predicted).sum())
    tn = int((~actual & ~predicted).sum())
    return {
        'n': len(actual), 'positives': tp + fn, 'negatives': tn + fp,
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'recall': tp / (tp + fn) if tp + fn else None,
        'precision': tp / (tp + fp) if tp + fp else None,
        'false_positive_rate': fp / (fp + tn) if fp + tn else None,
        'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        'alarm_fraction': (tp + fp) / len(actual) if len(actual) else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', default='/tmp/kamp_contest_energy.zip')
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    d, digest = load_source(args.zip)
    quarters = ['15분', '30분', '45분', '60분']
    bad_days = sorted(d.loc[~d['시간'].between(0, 23), '날짜'].unique().tolist())
    profiles = {int(day): hashlib.sha256(g[quarters].to_numpy().tobytes()).hexdigest()
                for day, g in d.groupby('날짜')}
    first_seen = {}
    for day, sig in sorted(profiles.items()):
        first_seen.setdefault(sig, day)
    new_source_days = {day for day, sig in profiles.items() if first_seen[sig] == day}
    valid = d.loc[~d['날짜'].isin(bad_days)]
    base = pd.to_datetime(valid['날짜'].astype(str), format='%Y%m%d') + pd.to_timedelta(valid['시간'], unit='h')
    y = pd.concat([
        pd.Series(valid[c].to_numpy(), index=base + pd.to_timedelta(m, unit='min'))
        for c, m in zip(quarters, [15, 30, 45, 60])
    ]).sort_index().asfreq('15min')
    assert not y.index.has_duplicates
    prediction_tables, result_rows, fold_rows = [], [], []
    budgets = [.01, .03, .05]
    for h in [1, 4]:
        x = pd.DataFrame(index=y.index)
        for lag in sorted(set([h, h+1, h+2, h+3, h+4, h+8, h+12, h+24, 96, 97, 192, 672])):
            assert lag >= h
            x[f'lag_{lag}'] = y.shift(lag)
        for w in [4, 16, 96]:
            r = y.shift(h).rolling(w, min_periods=w)
            x[f'mean_{w}'], x[f'max_{w}'], x[f'min_{w}'] = r.mean(), r.max(), r.min()
        x['hour'] = y.index.hour
        x['quarter'] = y.index.minute // 15
        x['weekday'] = y.index.dayofweek
        x['month'] = y.index.month
        eligible = y.notna() & x.notna().all(axis=1)
        for month in range(5, 10):
            test_start = pd.Timestamp(2021, month, 1)
            test_end = pd.Timestamp(2021, month+1, 1) if month < 9 else pd.Timestamp('2021-09-15')
            cal_start = test_start - pd.DateOffset(months=1)
            train_end = cal_start - pd.Timedelta(minutes=15*h)
            cal_end = test_start - pd.Timedelta(minutes=15*h)
            train = eligible & (y.index <= train_end)
            cal = eligible & (y.index >= cal_start) & (y.index <= cal_end)
            test = eligible & (y.index >= test_start) & (y.index < test_end)
            assert not (train & cal).any() and not (cal & test).any()
            assert y.index[train].max() <= y.index[cal].min() - pd.Timedelta(minutes=15*h)
            assert y.index[cal].max() <= y.index[test].min() - pd.Timedelta(minutes=15*h)
            peak = float(y.loc[train].quantile(.95))
            train_label = y.loc[train].to_numpy() >= peak
            cal_label = y.loc[cal].to_numpy() >= peak
            test_label = y.loc[test].to_numpy() >= peak
            assert train_label.any() and (~train_label).any() and (~cal_label).any()
            hgb = HistGradientBoostingClassifier(
                max_iter=180, max_leaf_nodes=15, min_samples_leaf=30,
                learning_rate=.06, l2_regularization=2, early_stopping=False,
                random_state=42,
            )
            positive_weight = len(train_label) / (2 * train_label.sum())
            negative_weight = len(train_label) / (2 * (~train_label).sum())
            hgb.fit(x.loc[train], train_label,
                    sample_weight=np.where(train_label, positive_weight, negative_weight))
            logistic = make_pipeline(StandardScaler(), LogisticRegression(
                C=1., class_weight='balanced', max_iter=2000, random_state=42,
            ))
            logistic.fit(x.loc[train], train_label)
            scores = {
                'recent_value': (x.loc[cal, f'lag_{h}'].to_numpy(), x.loc[test, f'lag_{h}'].to_numpy()),
                'logistic': (logistic.predict_proba(x.loc[cal])[:, 1], logistic.predict_proba(x.loc[test])[:, 1]),
                'hgb_classifier': (hgb.predict_proba(x.loc[cal])[:, 1], hgb.predict_proba(x.loc[test])[:, 1]),
            }
            source_days = (y.index[test] - pd.Timedelta(minutes=1)).strftime('%Y%m%d').astype(int)
            new_profile = np.isin(source_days, list(new_source_days))
            fold_info = {
                'horizon_minutes': h*15, 'test_month': f'2021-{month:02}',
                'test_start': str(test_start), 'test_end_exclusive': str(test_end),
                'calibration_start': str(cal_start), 'calibration_label_end': str(cal_end),
                'training_label_end': str(train_end), 'training_n': int(train.sum()),
                'calibration_n': int(cal.sum()), 'test_n': int(test.sum()),
                'train_peak_threshold': peak,
                'training_positives': int(train_label.sum()),
                'calibration_positives': int(cal_label.sum()),
                'test_positives': int(test_label.sum()),
                'new_daily_profile_test_n': int(new_profile.sum()),
                'new_daily_profile_test_days': len(set(source_days[new_profile])),
                'repeated_daily_profile_test_n': int((~new_profile).sum()),
            }
            fold_rows.append(fold_info)
            for model_name, (cal_score, test_score) in scores.items():
                p = pd.DataFrame({
                    'timestamp': y.index[test], 'source_day': source_days,
                    'horizon_minutes': h*15, 'test_month': fold_info['test_month'],
                    'model': model_name, 'power': y.loc[test].to_numpy(),
                    'train_peak_threshold': peak, 'is_peak': test_label,
                    'score': test_score, 'is_new_daily_profile': new_profile,
                })
                ap = float(average_precision_score(test_label, test_score)) if test_label.any() else None
                auc = float(roc_auc_score(test_label, test_score)) if len(np.unique(test_label)) == 2 else None
                for budget in budgets:
                    threshold = calibration_threshold(cal_score[~cal_label], budget)
                    cal_alarm, test_alarm = cal_score > threshold, test_score > threshold
                    cal_metrics = counts(cal_label, cal_alarm)
                    assert cal_metrics['false_positive_rate'] <= budget + 1e-12
                    p[f'alarm_budget_{int(budget*100):02}pct'] = test_alarm
                    p[f'score_threshold_{int(budget*100):02}pct'] = threshold
                    for subset_name, subset in {
                        'all': np.ones(len(test_label), dtype=bool),
                        'new_daily_profile': new_profile,
                        'repeated_daily_profile': ~new_profile,
                    }.items():
                        metrics = counts(test_label[subset], test_alarm[subset])
                        result_rows.append({
                            **fold_info, 'model': model_name, 'calibration_fpr_budget': budget,
                            'score_threshold': threshold, 'subset': subset_name,
                            'calibration_actual_fpr': cal_metrics['false_positive_rate'],
                            'calibration_recall': cal_metrics['recall'],
                            'test_ap_all': ap, 'test_roc_auc_all': auc, **metrics,
                        })
                prediction_tables.append(p)
            print(f'complete horizon={h*15} test={month} train={train.sum()} cal={cal.sum()} test={test.sum()}', flush=True)
    results = pd.DataFrame(result_rows)
    results.to_csv(out/'classifier_monthly_metrics.csv', index=False)
    predictions = pd.concat(prediction_tables, ignore_index=True)
    predictions.to_csv(out/'classifier_predictions.csv.gz', index=False, compression='gzip')
    aggregate_rows = []
    for period, month_select in [('all_months', list(range(5, 10))), ('aug_sep_exploratory', [8, 9])]:
        selected = results[results['test_month'].str[-2:].astype(int).isin(month_select)]
        for keys, g in selected.groupby(['horizon_minutes', 'model', 'calibration_fpr_budget', 'subset']):
            h, model, budget, subset = keys
            tp, fp, fn, tn = [int(g[k].sum()) for k in ['tp', 'fp', 'fn', 'tn']]
            aggregate_rows.append({
                'period': period, 'horizon_minutes': int(h), 'model': model,
                'calibration_fpr_budget': float(budget), 'subset': subset,
                'n': tp+fp+fn+tn, 'positives': tp+fn, 'negatives': tn+fp,
                'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
                'recall': tp/(tp+fn) if tp+fn else None,
                'precision': tp/(tp+fp) if tp+fp else None,
                'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                'false_positive_rate': fp/(fp+tn) if fp+tn else None,
                'alarm_fraction': (tp+fp)/(tp+fp+fn+tn) if tp+fp+fn+tn else None,
            })
    pd.DataFrame(aggregate_rows).to_csv(out/'classifier_aggregate_metrics.csv', index=False)
    payload = {
        'source_zip': args.zip, 'source_csv_sha256': digest, 'invalid_source_dates_excluded': bad_days,
        'design': {
            'target': 'power at a single future 15-minute interval endpoint, not the maximum over the next hour',
            'event': 'target power >= training 95th percentile; statistical high load, not contractual demand limit',
            'time_convention': 'interval endpoints, monthly [00:00, next boundary); final Sep15 00:00 omitted as in initial audit',
            'features': 'strictly past power and target calendar only; no production/weather/staffing/same-hour mean',
            'training': 'all eligible earlier observations, ending at first calibration forecast origin',
            'calibration': 'previous month, labels ending at first test forecast origin; never refit on calibration',
            'threshold': 'normal-calibration order statistic, alarm if score strictly greater; ties conservative',
            'warning_budget': '1/3/5% empirical calibration-normal false alarm budget; test FPR may exceed it under drift',
            'models_fixed': True, 'parameter_search': False,
            'hgb': '180 iterations, 15 leaves, leaf min30, lr .06, l2=2, balanced sample weights, no early stopping, seed42',
            'logistic': 'training-only StandardScaler, C1, class_weight balanced, max_iter2000, seed42',
            'duplicate_audit': 'whole 96-value source-day hashes used only to stratify evaluation, never as a feature; new means first occurrence globally',
            'known_test_exposure': 'Aug-Sep already viewed during topic selection; all new results are follow-up exploration, not a fresh blind confirmation',
            'limitations': 'one supplied source, possible augmentation, no cost saving or physical fault/contract exceedance validation',
        },
        'folds': fold_rows, 'aggregate_results': aggregate_rows,
    }
    (out/'classifier_results.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(pd.DataFrame(aggregate_rows).query("period == 'aug_sep_exploratory' and subset == 'new_daily_profile'")
          [['horizon_minutes','model','calibration_fpr_budget','recall','false_positive_rate','precision','f1']].to_string(index=False))


if __name__ == '__main__':
    main()
