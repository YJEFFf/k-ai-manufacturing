"""Predict any high-load 15-minute interval in the next 60 minutes.

Fixed models and chronological calibration, distinct from the endpoint task.
Writes window_* files only; see window_report.md for interpretation limits.
"""
from pathlib import Path
import argparse
import hashlib
import json
import signal

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from common import load_energy, make_features, month_folds, alarm_threshold
from classifier_experiment import counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--zip', default='/tmp/kamp_contest_energy.zip')
    args = ap.parse_args()
    out = Path(__file__).resolve().parent
    def timeout(signum, frame):
        raise TimeoutError('Source read exceeded 20 seconds')
    old = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(20)
    try:
        y, novel, source = load_energy(args.zip)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    h = 4
    x, eligible = make_features(y, h)
    # At index t the forecast origin is t-60 minutes, so these values are
    # exactly the four future interval ends t-45, t-30, t-15, t.
    window_max = y.rolling(4, min_periods=4).max()
    eligible &= window_max.notna()
    all_quarters_novel = novel.astype(int).rolling(4, min_periods=4).sum().eq(4)
    folds, rows, prediction_tables = [], [], []
    budgets = [.01, .03, .05]
    for fold in month_folds(y, eligible, h):
        tr, ca, te = [fold[k] for k in ['train', 'cal', 'test']]
        # The high-load threshold is from original per-quarter electricity,
        # NOT the 95th percentile of the rolling maxima.
        peak = float(y.loc[tr].quantile(.95))
        train_label = window_max.loc[tr].to_numpy() >= peak
        cal_label = window_max.loc[ca].to_numpy() >= peak
        test_label = window_max.loc[te].to_numpy() >= peak
        assert train_label.any() and (~train_label).any() and (~cal_label).any()
        model = HistGradientBoostingClassifier(
            max_iter=180, max_leaf_nodes=15, min_samples_leaf=30,
            learning_rate=.06, l2_regularization=2, early_stopping=False,
            random_state=42,
        )
        weights = np.where(train_label, len(train_label)/(2*train_label.sum()),
                           len(train_label)/(2*(~train_label).sum()))
        model.fit(x.loc[tr], train_label, sample_weight=weights)
        logistic = make_pipeline(StandardScaler(), LogisticRegression(
            C=1., class_weight='balanced', max_iter=2000, random_state=42,
        ))
        logistic.fit(x.loc[tr], train_label)
        scores = {
            'recent_value': (x.loc[ca, 'lag_4'].to_numpy(), x.loc[te, 'lag_4'].to_numpy()),
            'logistic': (logistic.predict_proba(x.loc[ca])[:, 1], logistic.predict_proba(x.loc[te])[:, 1]),
            'hgb_classifier': (model.predict_proba(x.loc[ca])[:, 1], model.predict_proba(x.loc[te])[:, 1]),
        }
        info = {k: v for k, v in fold.items() if k not in ['train', 'cal', 'test']}
        info.update(
            horizon_minutes=60, target_kind='any_of_next_four_quarters_high',
            power_threshold=peak, train_n=int(tr.sum()), calibration_n=int(ca.sum()), test_n=int(te.sum()),
            train_event_n=int(train_label.sum()), calibration_event_n=int(cal_label.sum()),
            test_event_n=int(test_label.sum()),
        )
        folds.append(info)
        origin = x.loc[te, 'lag_4'].to_numpy()
        origin_high = origin >= peak
        onset = test_label & ~origin_high
        values = np.column_stack([y.shift(k).loc[te].to_numpy() for k in [3, 2, 1, 0]])
        assert np.allclose(values.max(axis=1), window_max.loc[te].to_numpy())
        first_cross = np.where(test_label, (values >= peak).argmax(axis=1)*15+15, np.nan)
        subset_masks = {
            'all': np.ones(len(test_label), dtype=bool),
            'new_endpoint_source_day': novel.loc[te].to_numpy(),
            'all_target_quarters_new_profile': all_quarters_novel.loc[te].to_numpy(),
            'has_repeated_target_source_day': ~all_quarters_novel.loc[te].to_numpy(),
        }
        for name, (cal_score, test_score) in scores.items():
            p = pd.DataFrame({
                'window_end': y.index[te], 'origin_timestamp': y.index[te]-pd.Timedelta(minutes=60),
                'source_day_at_window_end': (y.index[te]-pd.Timedelta(minutes=1)).strftime('%Y-%m-%d'),
                'month': fold['month'], 'horizon_minutes': 60, 'model': name,
                'origin_power': origin, 'endpoint_power': y.loc[te].to_numpy(),
                'future_four_quarter_max': window_max.loc[te].to_numpy(),
                'train_power95': peak, 'is_window_peak': test_label,
                'origin_is_peak': origin_high, 'new_window_peak_entry': onset,
                'first_peak_quarter_end_minutes_from_origin': first_cross,
                'new_endpoint_source_day': subset_masks['new_endpoint_source_day'],
                'all_target_quarters_new_profile': subset_masks['all_target_quarters_new_profile'],
                'score': test_score,
            })
            ap_value = float(average_precision_score(test_label, test_score)) if test_label.any() else None
            auc = float(roc_auc_score(test_label, test_score)) if len(np.unique(test_label)) == 2 else None
            for budget in budgets:
                threshold = alarm_threshold(cal_score, cal_label, budget)
                cal_alarm, alarm = cal_score > threshold, test_score > threshold
                cal_metrics = counts(cal_label, cal_alarm)
                assert cal_metrics['false_positive_rate'] <= budget+1e-12
                p[f'alarm_budget_{int(budget*100):02}pct'] = alarm
                p[f'score_threshold_{int(budget*100):02}pct'] = threshold
                for subset, mask in subset_masks.items():
                    this_onset = onset[mask]
                    this_alarm = alarm[mask]
                    rows.append({
                        **info, 'model': name, 'budget': budget, 'subset': subset,
                        'score_threshold': threshold,
                        'calibration_realized_fpr': cal_metrics['false_positive_rate'],
                        'calibration_recall': cal_metrics['recall'],
                        'new_window_peak_entry_n': int(this_onset.sum()),
                        'new_window_peak_entry_detected': int(this_alarm[this_onset].sum()),
                        'new_window_peak_entry_recall': float(this_alarm[this_onset].mean()) if this_onset.any() else None,
                        'monthly_ap_all': ap_value, 'monthly_auc_all': auc,
                        **counts(test_label[mask], this_alarm),
                    })
            prediction_tables.append(p)
        print(f"done window60 month={fold['month']} n={te.sum()} events={test_label.sum()} new_entries={onset.sum()}", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(out/'window_monthly_metrics.csv', index=False)
    predictions = pd.concat(prediction_tables, ignore_index=True)
    predictions.to_csv(out/'window_predictions.csv.gz', index=False, compression='gzip')
    aggregates = []
    for period, months in [('all_months', list(range(5, 10))), ('aug_sep_exploratory', [8, 9])]:
        selected = frame[frame['month'].isin(months)]
        for (model, budget, subset), g in selected.groupby(['model', 'budget', 'subset']):
            tp, fp, fn, tn = [int(g[c].sum()) for c in ['tp', 'fp', 'fn', 'tn']]
            n_entry = int(g['new_window_peak_entry_n'].sum())
            entry_detected = int(g['new_window_peak_entry_detected'].sum())
            aggregates.append({
                'period': period, 'horizon_minutes': 60, 'target_kind': 'any_of_next_four_quarters_high',
                'model': model, 'budget': float(budget), 'subset': subset,
                'n': tp+fp+fn+tn, 'positives': tp+fn, 'negatives': tn+fp,
                'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
                'recall': tp/(tp+fn) if tp+fn else None,
                'precision': tp/(tp+fp) if tp+fp else None,
                'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                'false_positive_rate': fp/(fp+tn) if fp+tn else None,
                'alarm_fraction': (tp+fp)/(tp+fp+fn+tn) if tp+fp+fn+tn else None,
                'new_window_peak_entry_n': n_entry, 'new_window_peak_entry_detected': entry_detected,
                'new_window_peak_entry_recall': entry_detected/n_entry if n_entry else None,
            })
    pd.DataFrame(aggregates).to_csv(out/'window_aggregate_metrics.csv', index=False)
    result = {
        'source': source, 'features_code_sha256': hashlib.sha256((out/'common.py').read_bytes()).hexdigest(),
        'design': {
            'target': 'maximum of 4 interval values strictly after origin through origin+60min >= training raw-quarter power95',
            'target_is_not': 'endpoint-only exceedance, instantaneous electrical peak, contract violation, or independent physical event count',
            'features': 'same fixed endpoint-indexed features as previous 60-minute task; all lags >=4 quarters',
            'training_label_end': 'no later than first calibration forecast origin',
            'calibration_label_end': 'no later than first test forecast origin',
            'threshold': 'raw per-quarter training power95, not rolling-max95; monthly fixed',
            'alert_policy': 'strict score > calibration-normal order statistic at 1/3/5% budgets, ties conservative',
            'models': 'same fixed balanced logistic/HGB as classifier_experiment; no hyperparameter search',
            'overlap': 'one forecast window every15min; adjacent windows share3 future quarters',
            'novel_profile_audit': 'retrospective daily-hash masks only; all_target_quarters_new_profile requires all4 source-day masks true',
            'known_test_exposure': 'exploratory follow-up; these dates informed topic selection and endpoint experiments',
        },
        'folds': folds, 'aggregate_results': aggregates,
    }
    (out/'window_results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(pd.DataFrame(aggregates).query("period == 'aug_sep_exploratory' and subset == 'all'")
          [['model','budget','n','positives','recall','false_positive_rate','precision','f1','new_window_peak_entry_recall']].to_string(index=False))


if __name__ == '__main__':
    main()
