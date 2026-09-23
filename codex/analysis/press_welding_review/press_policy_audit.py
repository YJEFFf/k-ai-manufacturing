"""Bounded exploratory audit: row alarms versus recording-segment workload.

Only normal records fit the scaler/models and calibrate thresholds. Abnormal
labels are used only for the final tables. Recording segments are not verified
independent faults; time to first alarm is not pre-failure warning lead time.
"""
from pathlib import Path
import argparse
import json
import math
import zipfile

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


COLS = ['AI0_Vibration', 'AI1_Vibration', 'AI2_Current']
BUDGETS = [.01, .03, .05]
# Fixed before this audit; no abnormal-label-based selection.
SPLITS = [('normal_60_20_20', 360, 480), ('normal_50_20_30', 300, 420)]


def blocks(frame):
    gap = pd.to_datetime(frame.TimeStamp).diff().dt.total_seconds()
    return gap.sub(.1).abs().gt(1e-6).fillna(False).cumsum().to_numpy()


def rms5(frame, scaler):
    z = scaler.transform(frame[COLS])
    values = (pd.DataFrame(z*z).groupby(blocks(frame))
              .rolling(5, min_periods=5).mean()
              .reset_index(level=0, drop=True).sort_index())
    return np.sqrt(values.max(axis=1, skipna=False)).to_numpy()


def cutoff_at_budget(scores, budget):
    # Unscored observations/segments consume coverage but never send an alarm.
    values = np.sort(np.where(np.isfinite(scores), scores, -np.inf))
    allowed = math.floor(budget*len(values))
    threshold = float(values[max(0, len(values)-allowed-1)])
    assert (values > threshold).sum() <= allowed
    return threshold


def segment_max(scores, group):
    safe = np.where(np.isfinite(scores), scores, -np.inf)
    return pd.Series(safe).groupby(group).max().to_numpy()


def summarize_records(frame, scores, threshold, source, common):
    group = blocks(frame)
    timestamps = pd.to_datetime(frame.TimeStamp).reset_index(drop=True)
    valid = np.isfinite(scores)
    alarm = valid & (scores > threshold)
    records, runs = [], []
    for block in np.unique(group):
        idx = np.flatnonzero(group == block)
        hit = idx[alarm[idx]]
        starts = idx[alarm[idx] & ~np.r_[False, alarm[idx[:-1]]]]
        ends = idx[alarm[idx] & ~np.r_[alarm[idx[1:]], False]]
        assert len(starts) == len(ends)
        first_delay = float((timestamps.iloc[hit[0]]-timestamps.iloc[idx[0]])
                            .total_seconds()) if len(hit) else None
        records.append(dict(**common, source=source, record_id=int(block),
                            record_start=str(timestamps.iloc[idx[0]]),
                            record_end=str(timestamps.iloc[idx[-1]]),
                            rows=len(idx), scored_rows=int(valid[idx].sum()),
                            alarm_rows=len(hit), alarm_runs=len(starts),
                            first_notification=int(bool(len(hit))),
                            first_alarm_delay_seconds=first_delay))
        for start, end in zip(starts, ends):
            runs.append(dict(**common, source=source, record_id=int(block),
                             alarm_start=str(timestamps.iloc[start]),
                             alarm_end=str(timestamps.iloc[end]),
                             alarm_rows=int(end-start+1),
                             delay_from_record_start_seconds=float(
                                 (timestamps.iloc[start]-timestamps.iloc[idx[0]])
                                 .total_seconds())))
    delays = [r['first_alarm_delay_seconds'] for r in records
              if r['first_notification']]
    summary = dict(rows=len(frame), scored_rows=int(valid.sum()),
                   row_coverage=float(valid.mean()), alarm_rows=int(alarm.sum()),
                   recording_segments=len(records),
                   scored_segments=sum(r['scored_rows'] > 0 for r in records),
                   notified_segments=sum(r['first_notification'] for r in records),
                   notification_segment_fraction=float(np.mean(
                       [r['first_notification'] for r in records])),
                   alarm_runs=len(runs),
                   conditional_median_first_alarm_delay_seconds=float(np.median(delays)) if delays else None,
                   conditional_p90_first_alarm_delay_seconds=float(np.quantile(delays, .9)) if delays else None)
    return summary, records, runs, alarm


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--output', type=Path,
                        default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    if args.zip is None:
        matches = list(Path(__file__).resolve().parents[3].glob('*/*소성가공 예지*zip'))
        assert len(matches) == 1, matches
        args.zip = matches[0]
    with zipfile.ZipFile(args.zip) as archive:
        source = {name.rsplit('/', 1)[-1]: pd.read_csv(archive.open(name))
                  for name in archive.namelist() if name.endswith('.csv')}
    normal = source['press_data_normal.csv']
    abnormal = source['outlier_data.csv']
    assert len(normal) == 20000 and len(abnormal) == 600
    assert normal.Equipment_state.eq(0).all() and abnormal.Equipment_state.eq(1).all()
    normal_blocks = blocks(normal)
    assert len(np.unique(normal_blocks)) == 600
    assert len(np.unique(blocks(abnormal))) == 21
    metrics, records, runs, split_manifest = [], [], [], []
    for split, train_end, cal_end in SPLITS:
        train = normal[normal_blocks < train_end].reset_index(drop=True)
        cal = normal[(normal_blocks >= train_end) & (normal_blocks < cal_end)].reset_index(drop=True)
        test = normal[normal_blocks >= cal_end].reset_index(drop=True)
        split_manifest.append(dict(split=split, train_normal_rows=len(train),
                                   calibration_normal_rows=len(cal), test_normal_rows=len(test),
                                   train_blocks=train_end, calibration_blocks=cal_end-train_end,
                                   test_normal_blocks=600-cal_end, test_abnormal_rows=600,
                                   test_abnormal_blocks=21))
        scaler = StandardScaler().fit(train[COLS])
        xtrain = scaler.transform(train[COLS])
        matrices = [scaler.transform(d[COLS]) for d in [cal, test, abnormal]]
        nn = NearestNeighbors(n_neighbors=5).fit(xtrain)
        scores = {
            'max_abs_z': [np.abs(x).max(axis=1) for x in matrices],
            '5nn_distance': [nn.kneighbors(x)[0].mean(axis=1) for x in matrices],
            'trailing_rms5': [rms5(d, scaler) for d in [cal, test, abnormal]],
        }
        cal_groups = blocks(cal)
        for model, (cal_score, test_score, abnormal_score) in scores.items():
            for unit in ['rows', 'recording_segments']:
                calibrating_scores = cal_score if unit == 'rows' else segment_max(cal_score, cal_groups)
                for budget in BUDGETS:
                    threshold = cutoff_at_budget(calibrating_scores, budget)
                    common = dict(split=split, model=model,
                                  calibration_unit=unit, budget=budget)
                    cal_summary, _, _, cal_alarm = summarize_records(cal, cal_score, threshold, 'normal_calibration', common)
                    ns, nr, ne, na = summarize_records(test, test_score, threshold, 'normal_test', common)
                    aus, ar, ae, aa = summarize_records(abnormal, abnormal_score, threshold, 'abnormal_test', common)
                    records.extend(nr+ar)
                    runs.extend(ne+ae)
                    truth = np.r_[np.zeros(len(test), dtype=int), np.ones(len(abnormal), dtype=int)]
                    alarm = np.r_[na, aa]
                    all_score = np.r_[test_score, abnormal_score]
                    valid = np.isfinite(all_score)
                    tn, fp, fn, tp = confusion_matrix(truth, alarm).ravel()
                    result = dict(**common, threshold=threshold,
                                  tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
                                  f1_all_rows=float(f1_score(truth, alarm)),
                                  f1_scored_rows=float(f1_score(truth[valid], alarm[valid])),
                                  ap_scored_rows=float(average_precision_score(truth[valid], all_score[valid])),
                                  abnormal_recall_all_rows=float(aa.mean()),
                                  normal_false_alarm_rate_all_rows=float(na.mean()),
                                  calibration_row_false_alarm_rate=float(cal_alarm.mean()),
                                  calibration_segment_false_alarm_rate=cal_summary['notification_segment_fraction'])
                    result.update({f'normal_{key}': value for key, value in ns.items()})
                    result.update({f'abnormal_{key}': value for key, value in aus.items()})
                    metrics.append(result)
        print(f'Completed {split}', flush=True)
    table = pd.DataFrame(metrics)
    manifest = dict(source=str(args.zip), design='Exploratory re-evaluation of previously inspected data.',
                    fixed_splits=split_manifest, models=list(scores), budgets=BUDGETS,
                    threshold='Strict score > past-normal order statistic. All calibration observations or recording segments are in budget denominators. Missing RMS scores never alarm.',
                    state='All trailing windows and consecutive-alarm runs reset at a non-0.1-second timestamp step. No histories cross split boundaries.',
                    first_notification='At most one first notification per recording segment; equivalent to thresholding the maximum observed score of that segment for calibration counts. Applied online as soon as the score crosses the fixed threshold.',
                    alarm_runs='Every consecutive sequence of positive row alarms is a separate run. A negative or unavailable score ends a run. No cooldown tuned on abnormal records.',
                    coverage='RMS requires five observed points. Unscored abnormal rows count as missed in all-row recall/F1; all 21 abnormal recording segments stay in segment-recall denominator.',
                    delay='Time since FIRST OBSERVATION of this abnormal recording segment; conditional on being detected. Not lead before physical fault, whose onset is unavailable.',
                    workload='Same normal-calibration budget is not the same realized test burden. Row, first-per-record and run counts are all reported. Runs themselves have not been equal-budget calibrated.',
                    limitations=['One normal date and one abnormal date; date and provided class are confounded.',
                                 'Recording segments are not independent verified failures or machine starts/stops.',
                                 'Two normal splits reuse the same abnormal data; they are sensitivity analyses, not independent replications.',
                                 'RMS coverage loss must accompany scored-row metrics.',
                                 'No abnormal-label tuning, threshold selection or hyperparameter search.',
                                 'No inference of real field false-alert rates, maintenance savings or future generalization.'])
    args.output.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.output/'press_policy_metrics.csv', index=False)
    pd.DataFrame(records).to_csv(args.output/'press_record_notifications.csv', index=False)
    pd.DataFrame(runs).to_csv(args.output/'press_alarm_runs.csv', index=False)
    (args.output/'press_policy_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(table[['split', 'model', 'calibration_unit', 'budget', 'f1_all_rows',
                 'normal_notified_segments', 'normal_recording_segments',
                 'abnormal_notified_segments', 'abnormal_recording_segments',
                 'normal_alarm_runs', 'abnormal_alarm_runs']].to_string(index=False))


if __name__ == '__main__':
    main()
