"""Chronological, strictly lagged screening benchmark for contest task 5.

No future production, weather, staffing, mean, or same-hour electricity is used.
Invalid-hour dates are excluded, not silently repaired. Metrics use source units.
Run: /tmp/kamp-review-venv/bin/python energy_forecast_audit.py --zip FILE
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.metrics import precision_score, recall_score, f1_score

parser = argparse.ArgumentParser()
parser.add_argument("--zip", default="/tmp/kamp_contest_energy.zip")
args = parser.parse_args()
outdir = Path(__file__).with_name("energy_vision")
with zipfile.ZipFile(args.zip) as z:
    assert z.testzip() is None
    n = next(n for n in z.namelist() if n.endswith(".csv"))
    raw = z.read(n)
d = pd.read_csv(io.BytesIO(raw))
quarters = ["15분", "30분", "45분", "60분"]
date = pd.to_datetime(d["날짜"].astype(str), format="%Y%m%d")
bad_hours = ~d["시간"].between(0, 23)
bad_dates = sorted(d.loc[bad_hours, "날짜"].unique().tolist())
summed = d[quarters].sum(axis=1)
ratio = d["생산량"] / summed
worker_ok = np.isclose(ratio, d["공장인원"], atol=1e-7, rtol=0, equal_nan=False)
source_audit = {
    "official_source": "https://www.kamp-ai.kr/contestNoticeDetail?CPT_NOTICE_SEQ=28",
    "attachment_fileSeq": 8081, "csv_sha256": hashlib.sha256(raw).hexdigest(),
    "shape": list(d.shape), "missing": d.isna().sum().astype(int).to_dict(),
    "date_min": str(date.min()), "date_max": str(date.max()), "days": int(date.nunique()),
    "rows_per_date_counts": d.groupby("날짜").size().value_counts().astype(int).to_dict(),
    "invalid_hour_count": int(bad_hours.sum()), "invalid_hour_dates": bad_dates,
    "invalid_hour_values": d.loc[bad_hours, ["날짜", "시간"]].values.tolist(),
    "duplicate_entire_rows": int(d.duplicated().sum()),
    "quarter_vector_unique_count": int(d[quarters].drop_duplicates().shape[0]),
    "all_four_electricity_zero_rows": int((summed == 0).sum()),
    "staffing_ratio_nonmissing_rows": int(ratio.notna().sum()),
    "staffing_ratio_exact_within_1e_7": int(worker_ok.sum()),
    "staffing_ratio_max_abs_error": float((ratio-d["공장인원"]).abs().max()),
    "staffing_formula": "공장인원 = 생산량 / (15분 + 30분 + 45분 + 60분)",
    "mean_matches_round_half_up": int(np.floor(d[quarters].mean(axis=1)+.5).eq(d["평균"]).sum()),
    "max_mean_abs_deviation": float((d[quarters].mean(axis=1)-d["평균"]).abs().max()),
    "weekday_inconsistent": int(((date.dt.dayofweek+1) != d["day"]).sum()),
    "month_inconsistent": int((date.dt.month != d["m"]).sum()),
    "day_inconsistent": int((date.dt.day != d["d"]).sum()),
}
profiles = {int(day): hashlib.sha256(frame[quarters].to_numpy().tobytes()).hexdigest()
            for day, frame in d.groupby("날짜")}
profile_groups = {}
for day, sig in profiles.items():
    profile_groups.setdefault(sig, []).append(day)
source_audit["unique_96_value_daily_profiles"] = len(profile_groups)
source_audit["duplicate_daily_profile_extra_dates"] = len(profiles)-len(profile_groups)
source_audit["duplicate_daily_profile_groups"] = sorted(
    [v for v in profile_groups.values() if len(v)>1], key=len, reverse=True)
print(json.dumps(source_audit, ensure_ascii=False, indent=2), flush=True)

# Quarter columns are indexed by interval ending time; no day reconstruction.
parts = []
valid = d[~d["날짜"].isin(bad_dates)].copy()
dates = pd.to_datetime(valid["날짜"].astype(str), format="%Y%m%d")
base = dates + pd.to_timedelta(valid["시간"], unit="h")
for c, minute in zip(quarters, [15, 30, 45, 60]):
    parts.append(pd.Series(valid[c].values, index=base+pd.to_timedelta(minute, unit="min")))
y = pd.concat(parts).sort_index()
assert not y.index.duplicated().any()
y = y.asfreq("15min")
source_audit["valid_hour_rows_for_benchmark"] = len(valid)
source_audit["quarter_observations_for_benchmark"] = int(y.notna().sum())
source_audit["quarter_missing_after_calendar_reindex"] = int(y.isna().sum())
sequence_signatures = {}
for window in [27, 32]:
    windows = np.lib.stride_tricks.sliding_window_view(y.to_numpy(), window)
    values = [None] * (window-1)
    values.extend(hashlib.sha256(v.tobytes()).hexdigest() if np.isfinite(v).all() else None for v in windows)
    sequence_signatures[window] = pd.Series(values, index=y.index)

folds = [("2021-05-01", "2021-06-01"), ("2021-06-01", "2021-07-01"),
         ("2021-07-01", "2021-08-01"), ("2021-08-01", "2021-09-15")]
results = []
daily_peaks = []
for h in [1, 4]:
    x = pd.DataFrame(index=y.index)
    for lag in sorted(set([h, h+1, h+2, h+3, h+4, h+8, h+12, h+24, 96, 97, 192, 672])):
        x[f"lag_{lag}"] = y.shift(lag)
    for window in [4, 16, 96]:
        r = y.shift(h).rolling(window, min_periods=window)
        x[f"mean_{window}"] = r.mean()
        x[f"max_{window}"] = r.max()
        x[f"min_{window}"] = r.min()
    x["hour"] = y.index.hour
    x["quarter"] = y.index.minute // 15
    x["weekday"] = y.index.dayofweek
    x["month"] = y.index.month
    # Complete lag windows prevent prediction across omitted/corrupted days.
    eligible = y.notna() & x.notna().all(axis=1)
    for start, end in folds:
        # Freeze the model at the first forecast origin, including horizon purge.
        # For h=4 the final 3 pre-boundary targets would otherwise be future labels
        # relative to the first forecast's origin.
        train_cutoff = pd.Timestamp(start)-pd.Timedelta(minutes=h*15)
        train = eligible & (y.index <= train_cutoff)
        test = eligible & (y.index >= pd.Timestamp(start)) & (y.index < pd.Timestamp(end))
        xt, yt = x.loc[train], y.loc[train]
        xv, truth = x.loc[test], y.loc[test]
        model = HistGradientBoostingRegressor(max_iter=180, max_leaf_nodes=15,
                    min_samples_leaf=30, learning_rate=.06, l2_regularization=2,
                    early_stopping=False, random_state=42)
        model.fit(xt, yt)
        preds = {"persistence": xv[f"lag_{h}"].to_numpy(),
                 "previous_day": xv["lag_96"].to_numpy(),
                 "previous_week": xv["lag_672"].to_numpy(),
                 "hist_gradient_boosting": model.predict(xv)}
        threshold = float(yt.quantile(.95))
        actual_event = truth.to_numpy() >= threshold
        for name, pred in preds.items():
            event = pred >= threshold
            rec = {"horizon_minutes": h*15, "test_start": start, "test_end_exclusive": end,
                   "training_label_cutoff": str(train_cutoff),
                   "model": name, "train_n": len(yt), "test_n": len(truth),
                   "mae": float(mean_absolute_error(truth, pred)),
                   "rmse": float(mean_squared_error(truth, pred)**.5), "r2": float(r2_score(truth, pred)),
                   "training_95pct_threshold": threshold, "actual_peak_n": int(actual_event.sum()),
                   "predicted_peak_n": int(event.sum()),
                   "peak_precision": float(precision_score(actual_event,event,zero_division=0)),
                   "peak_recall": float(recall_score(actual_event,event,zero_division=0)),
                   "peak_f1": float(f1_score(actual_event,event,zero_division=0)),
                   "peak_mae": float(np.abs(truth.to_numpy()[actual_event]-pred[actual_event]).mean()) if actual_event.any() else None,
                   "event_definition": "statistical high load >= training 95th percentile, not contract peak violation",
                   "metric_units": "original source value units; kW/kWh not independently confirmed"}
            results.append(rec)
            # Additional audit: evaluate first occurrence of day profiles not seen
            # on any earlier source date. This is a selected audit subset, not an
            # estimate of deployment frequency or a causal intervention test.
            start_day = int(pd.Timestamp(start).strftime("%Y%m%d"))
            seen = {sig for day, sig in profiles.items() if day < start_day}
            new_days = set()
            end_day = int(pd.Timestamp(end).strftime("%Y%m%d"))
            for day in sorted(profiles):
                if start_day <= day < end_day:
                    sig = profiles[day]
                    if sig not in seen:
                        new_days.add(day)
                    seen.add(sig)
            # Each 00:00 observation belongs to the previous hourly source day.
            source_days = (truth.index-pd.Timedelta(minutes=1)).strftime("%Y%m%d").astype(int)
            subset = np.isin(source_days, list(new_days))
            rec["new_daily_profile_dates"] = len(set(source_days[subset]))
            rec["new_daily_profile_n"] = int(subset.sum())
            rec["new_daily_profile_mae"] = float(mean_absolute_error(truth[subset], pred[subset])) if subset.any() else None
            rec["new_daily_profile_r2"] = float(r2_score(truth[subset], pred[subset])) if subset.sum()>1 else None
            rec["new_daily_profile_peak_f1"] = float(f1_score(actual_event[subset], event[subset], zero_division=0)) if subset.any() else None
            for w, signatures in sequence_signatures.items():
                seen_windows = set(signatures.loc[signatures.index <= train_cutoff].dropna())
                unseen = ~signatures.loc[truth.index].isin(seen_windows).to_numpy()
                rec[f"unseen_{w}_quarter_window_n"] = int(unseen.sum())
                rec[f"unseen_{w}_quarter_window_mae"] = float(mean_absolute_error(truth[unseen], pred[unseen])) if unseen.any() else None
        print(f"finished horizon={h*15} fold={start} n={len(truth)}", flush=True)

payload = {"source_audit": source_audit,
           "benchmark_design": {"target": "future 15-minute column value", "fixed_model_without_tuning": True,
              "features": "past electricity and known calendar only", "time_convention": "15/30/45/60 columns as interval ends",
              "invalid_hours": "entire two dates omitted; gaps retained", "eligible": "all selected lags and rolling windows available",
              "limitations": "screening baseline, not final model or contest score; no intervention/cost saving validation"},
           "results": results}
(outdir/"energy_forecast_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
pd.DataFrame(results).to_csv(outdir/"energy_forecast_results.csv", index=False)
print(pd.DataFrame(results)[["horizon_minutes","test_start","model","mae","r2","peak_recall","peak_f1"]].to_string(index=False))
