"""Exploratory event-level audit of existing, already inspected predictions.

No fitting or threshold selection. A notification uses only its stored alarm,
current measured power, and past notification time. Quarter-end lead time is
also converted to the conservative lead before the first high interval starts.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import pandas as pd


QUARTER = pd.Timedelta(minutes=15)
HOUR = pd.Timedelta(minutes=60)


def events_from_trace(frame, merge_low_minutes):
    threshold = float(frame.train_power95.iloc[0])
    origins = pd.Series(frame.origin_power.to_numpy(), index=frame.origin_timestamp)
    ends = pd.Series(frame.endpoint_power.to_numpy(), index=frame.window_end)
    both = pd.concat([origins, ends])
    assert both.groupby(level=0).nunique().max() == 1
    trace = both.groupby(level=0).first().sort_index()
    # Verify stored future labels against the recovered measurement trace.
    for offset in [15, 30, 45, 60]:
        assert trace.reindex(frame.origin_timestamp + pd.Timedelta(minutes=offset)).notna().all()
    future = np.column_stack([
        trace.reindex(frame.origin_timestamp + pd.Timedelta(minutes=k)).to_numpy()
        for k in [15, 30, 45, 60]
    ])
    assert np.allclose(future.max(axis=1), frame.future_four_quarter_max)
    assert np.array_equal(future.max(axis=1) >= threshold, frame.is_window_peak)
    runs = []
    for timestamp, value in trace.items():
        if value < threshold:
            continue
        if runs and timestamp - runs[-1][1] == QUARTER:
            runs[-1][1] = timestamp
        else:
            runs.append([timestamp, timestamp])
    merged = []
    for start, end in runs:
        contiguous_bridge = False
        if merged:
            bridge = pd.date_range(merged[-1][1], start, freq='15min')
            contiguous_bridge = trace.reindex(bridge).notna().all()
        if (merged and contiguous_bridge and
                start - merged[-1][1] <= QUARTER + pd.Timedelta(minutes=merge_low_minutes)):
            merged[-1][1] = end
        else:
            merged.append([start, end])
    available_origins = set(frame.origin_timestamp)
    eligible = []
    censored = 0
    for start, end in merged:
        if not (frame.window_end.min() <= start <= frame.window_end.max()):
            continue
        previous = trace.get(start - QUARTER, np.nan)
        full_forecast_history = all(start - pd.Timedelta(minutes=k) in available_origins
                                    for k in [15, 30, 45, 60])
        if not np.isfinite(previous) or previous >= threshold or not full_forecast_history:
            censored += 1
            continue
        eligible.append((start, end))
    return eligible, censored


def notifications(frame, budget, cooldown_minutes):
    result = []
    previous_notice = None
    cooldown = pd.Timedelta(minutes=cooldown_minutes)
    for row in frame.itertuples(index=False):
        alarm = getattr(row, f'alarm_budget_{budget:02}pct')
        # Current power is observed at forecast origin, so this gate is causal.
        if not alarm or row.origin_power >= row.train_power95:
            continue
        if previous_notice is not None and row.origin_timestamp - previous_notice < cooldown:
            continue
        result.append((row.origin_timestamp, bool(row.is_window_peak)))
        previous_notice = row.origin_timestamp
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = Path(args.predictions)
    frame = pd.read_csv(path, parse_dates=['origin_timestamp', 'window_end'])
    assert not frame.duplicated(['month', 'model', 'origin_timestamp']).any()
    models = sorted(frame.model.unique())
    truth_cols = ['origin_timestamp', 'window_end', 'origin_power', 'endpoint_power',
                  'future_four_quarter_max', 'train_power95', 'is_window_peak']
    rows, detail = [], []
    for month, month_frame in frame.groupby('month'):
        canonical = month_frame[month_frame.model == models[0]].sort_values('origin_timestamp')
        for model in models[1:]:
            other = month_frame[month_frame.model == model].sort_values('origin_timestamp')
            pd.testing.assert_frame_equal(canonical[truth_cols].reset_index(drop=True),
                                          other[truth_cols].reset_index(drop=True))
        for merge in [0, 15, 30]:
            events, censored = events_from_trace(canonical, merge)
            for model, group in month_frame.groupby('model'):
                group = group.sort_values('origin_timestamp')
                for budget in [1, 3, 5]:
                    for cooldown in [0, 60, 120]:
                        notices = notifications(group, budget, cooldown)
                        notice_times = [time for time, _ in notices]
                        leads = []
                        for start, end in events:
                            matches = [time for time in notice_times if start - HOUR <= time < start]
                            if matches:
                                lead = (start - QUARTER - min(matches)).total_seconds() / 60
                                leads.append(lead)
                            else:
                                lead = None
                            if merge == 0 and budget == 3 and cooldown == 60:
                                detail.append(dict(month=int(month), model=model,
                                    first_high_quarter_end=str(start), last_high_quarter_end=str(end),
                                    lead_before_first_high_interval_start_minutes=lead))
                        n = len(events)
                        rows.append(dict(month=int(month), model=model, budget=budget,
                            merge_low_minutes=merge, cooldown_minutes=cooldown,
                            forecasts=len(group), exposure_days=len(group)/96,
                            eligible_events=n, censored_events=censored,
                            detected_events=len(leads),
                            early15_events=sum(lead >= 15 for lead in leads),
                            event_recall=len(leads)/n if n else None,
                            early15_recall=sum(lead >= 15 for lead in leads)/n if n else None,
                            median_lead_before_interval_start_minutes=float(np.median(leads)) if leads else None,
                            notifications=len(notices),
                            false_notifications=sum(not flag for _, flag in notices),
                            notifications_per_exposure_day=len(notices)/(len(group)/96),
                            false_notifications_per_exposure_day=sum(not flag for _, flag in notices)/(len(group)/96)))
    monthly = pd.DataFrame(rows)
    aggregate = []
    for period, months in [('all_months_exploratory', [5, 6, 7, 8, 9]),
                           ('aug_sep_exploratory', [8, 9])]:
        for keys, group in monthly[monthly.month.isin(months)].groupby(
                ['model', 'budget', 'merge_low_minutes', 'cooldown_minutes']):
            row = dict(zip(['model', 'budget', 'merge_low_minutes', 'cooldown_minutes'], keys))
            row['period'] = period
            for col in ['forecasts', 'exposure_days', 'eligible_events', 'censored_events',
                        'detected_events', 'early15_events', 'notifications', 'false_notifications']:
                row[col] = group[col].sum()
            row['event_recall'] = row['detected_events']/row['eligible_events']
            row['early15_recall'] = row['early15_events']/row['eligible_events']
            row['notifications_per_exposure_day'] = row['notifications']/row['exposure_days']
            row['false_notifications_per_exposure_day'] = row['false_notifications']/row['exposure_days']
            aggregate.append(row)
    aggregate = pd.DataFrame(aggregate)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out/'monthly.csv', index=False)
    aggregate.to_csv(out/'aggregate.csv', index=False)
    pd.DataFrame(detail).to_csv(out/'primary_event_details.csv', index=False)
    metadata = dict(
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        known_test_exposure='All dates were previously inspected; exploratory feasibility audit only.',
        event='Consecutive high quarter intervals at monthly training threshold; bridge 0/15/30 low minutes.',
        censoring='Require low preceding quarter and all four previous forecast origins. Monthly boundaries and cooldown states reset separately.',
        alarm='Existing fixed thresholds only; origin power below high threshold; shared past-only cooldown 0/60/120 min.',
        primary='Predefined before this audit: calibration FPR budget3%, cooldown60min, merge0min.',
        lead='Minutes before START of first high quarter, not its measurement end. 0 is permitted; >=15 separately counted.',
        false_notification='Sent notification with no high quarter in next60min. It is not industrial hazard ground truth.',
        uncertainty='Events can remain dependent. No confidence interval or new independent validation claimed.',
        workload='Equal cooldown/calibration rules are not equal realized notification burdens.',
        policy_calibration_limit='Thresholds were calibrated for the original window alarms, before this new origin-low gate/cooldown. Recalibrate the complete notification policy on earlier calibration data before claiming a fair operational advantage. In August the recent-value3% cutoff is175 and peak threshold176: integer power cannot satisfy 175<power<176, so this new gate suppresses all its alerts.',
        event_dependence='One notice can cover more than one nearby event; event counts are not independent, and merge15/30 sensitivity must accompany merge0.',
        units='Exposure day=96 available forecast origins; fractional days allowed around gaps.'
    )
    (out/'method.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    primary = aggregate.query("period=='aug_sep_exploratory' and budget==3 and cooldown_minutes==60 and merge_low_minutes==0")
    print(primary.to_string(index=False))


if __name__ == '__main__':
    main()
