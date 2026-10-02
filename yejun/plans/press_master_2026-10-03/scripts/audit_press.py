"""Recalculate design-relevant facts; no new detector training or model selection."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
COLS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
EXPECTED = {
    "press_data_normal.csv": "f2d61cb3b3108f49a3305d2966b3a31f26942ac8af8ffc9eb531b432b945b0a7",
    "outlier_data.csv": "9fad8c238e63dba3257d8be32a32362548955c772171a95c0d2af61b0435ed2e",
}


def records(frame, rule):
    delta = frame.t.diff().dt.total_seconds()
    if rule == "gap500":
        start = delta.gt(0.5)
    else:
        ns = frame.t.astype("int64").diff()
        start = ~ns.between(80_000_000, 120_000_000, inclusive="both")
    start.iloc[0] = True
    out = frame.copy()
    out["record"] = start.cumsum().astype(int) - 1
    return out


def main():
    data = ROOT / "데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전"
    result = {"environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
              "scope": "source data audit and historical baseline recalculation, not v3 performance"}
    frames = {}
    for filename, expected in EXPECTED.items():
        path = data / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError("Contest source hash mismatch")
        raw = pd.read_csv(path)
        raw["t"] = pd.to_datetime(raw.TimeStamp)
        dup = raw.duplicated(["TimeStamp"] + COLS)
        f = records(raw.loc[~dup].copy(), "gap500")
        strict = records(raw.loc[~dup].copy(), "strict")
        lens = f.groupby("record").size()
        starts = f.groupby("record").t.min()
        ends = f.groupby("record").t.max()
        tag = "normal" if filename.startswith("press") else "abnormal"
        frames[tag] = (raw, f)
        result[tag] = dict(sha256=digest, rows=len(raw), retained_rows=len(f),
                           duplicate_zero_based_rows=list(map(int, raw.index[dup])),
                           finite_values=bool(np.isfinite(raw[COLS].to_numpy()).all()),
                           duplicate_timestamps=int(raw.t.duplicated().sum()),
                           nonpositive_deltas=int(raw.t.diff().le(pd.Timedelta(0)).sum()),
                           first=str(raw.t.iloc[0]), last=str(raw.t.iloc[-1]),
                           duration_s=(raw.t.iloc[-1]-raw.t.iloc[0]).total_seconds(),
                           records_gap500=len(lens), records_strict=int(strict.record.nunique()),
                           same_partition_after_dedup=bool(np.array_equal(f.record, strict.record)),
                           record_length_counts={str(int(k)): int(v) for k, v in lens.value_counts().sort_index().items()},
                           records_lt10=int((lens<10).sum()), records_ge10=int((lens>=10).sum()),
                           records_ge20=int((lens>=20).sum()),
                           record_start_spacing_median_s=float(starts.diff().dt.total_seconds().median()),
                           record_end_spacing_max_s=float(ends.diff().dt.total_seconds().max()),
                           logged_within_record_span_s=float((ends-starts).dt.total_seconds().sum()))
        if tag == "normal":
            start_m = (starts-raw.t.iloc[0]).dt.total_seconds()/60
            end_m = (ends-raw.t.iloc[0]).dt.total_seconds()/60
            folds = {}
            for name, bounds in {"P0": [0,10,20,40], "P1": [0,20,40,60], "P2": [0,40,60,1000]}.items():
                fold = {}
                for role, (lo,hi) in zip(["fit","cal","evaluation"],zip(bounds,bounds[1:])):
                    ids = lens.index[(start_m>=lo) & (end_m<hi)]
                    fold[role] = dict(n_records=len(ids), n_rows=int(lens.loc[ids].sum()),
                                      first_id=int(ids.min()), last_id=int(ids.max()),
                                      lt10=int((lens.loc[ids]<10).sum()),
                                      min_tail_p=1/(len(ids)+1))
                assigned=set()
                for lo,hi in zip(bounds,bounds[1:]):
                    assigned.update(lens.index[(start_m>=lo)&(end_m<hi)])
                relevant=set(lens.index[(start_m<bounds[-1]) & (end_m>=bounds[0])])
                fold["boundary_record_ids"]=sorted(map(int,relevant-assigned))
                folds[name]=fold
            result["forward_folds"]=folds
    nraw, _ = frames["normal"]
    araw, _ = frames["abnormal"]
    threshold=float(nraw.AI0_Vibration.iloc[:15000].abs().max())
    def outcomes(df, first, count, skip):
        rec = records(df, "gap500")
        x=df.AI0_Vibration.abs().to_numpy()
        full = rec.groupby("record").AI0_Vibration.transform(lambda a: a.abs().max()).to_numpy()
        starts=range(first+skip,first+count-20-100)
        return (sum(x[s:s+20].max()>threshold for s in starts),
                sum(full[s:s+20].max()>threshold for s in starts),len(starts))
    nn=outcomes(nraw,15000,5000,880)
    aa=outcomes(araw,0,600,300)
    result["historical_guide_windows"]={
        "threshold_raw":threshold, "normal_windows":nn[2], "abnormal_windows":aa[2],
        "window_only":dict(tp=int(aa[0]),fp=int(nn[0]),fn=int(aa[2]-aa[0]),f1=2*aa[0]/(aa[2]+aa[0]+nn[0])),
        "full_record_broadcast_retrospective":dict(tp=int(aa[1]),fp=int(nn[1]),fn=int(aa[2]-aa[1]),f1=2*aa[1]/(aa[2]+aa[1]+nn[1])),
        "always_normal_accuracy":nn[2]/(nn[2]+aa[2]),
        "warning":"Different information sets. Full-record labels are not causal window predictions."}
    n = frames["normal"][1]
    a = frames["abnormal"][1]
    m = lambda f,c:float(f.groupby("record")[c].mean()[f.groupby("record").size()>=10].abs().median())
    result["median_abs_record_mean_raw_units"]={tag:{c:m(f,c) for c in COLS[:2]}
                                                   for tag,f in [("normal",n),("abnormal",a)]}
    result["sampling_hypotheses"]={
        "physical_sampling_rate":"unknown; timing/quantization fits do not uniquely identify ADC settings",
        "if_1kHz_rows_duration_s":len(n)/1000,
        "if_1kHz_duty_fraction":len(n)/1000/result["normal"]["duration_s"],
        "if_10Hz_rows_duration_s":len(n)/10,
        "warning":"These two are conditional calculations, not measurements of physical coverage."}
    result["sample_size_scenarios"]={
        "binomial_iid_zero_fp_n_for_upper_1pct_at95":math.ceil(math.log(.05)/math.log(.99)),
        "binomial_iid_all_hits_n_for_lower_90pct_at95":math.ceil(math.log(.05)/math.log(.9)),
        "poisson_stationary_zero_fa_hours_for_upper_one_per8h_at95":-math.log(.05)/.125,
        "poisson_if_zero_fa_in_full_normal_upper_per_hour":-math.log(.05)/(result["normal"]["duration_s"]/3600),
        "warning":"Planning calculations conditional on iid Bernoulli / homogeneous Poisson assumptions. Not confidence guarantees for correlated press records."}
    out=HERE / "evidence/press_audit.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ["forward_folds","historical_guide_windows","sampling_hypotheses","sample_size_scenarios"]},ensure_ascii=False,indent=2))
    old=HERE.parent/"press_plan_merged_2026-10-02/eda/check_judge_findings.py"
    p=subprocess.run([sys.executable,str(old),"--root",str(data.parents[1])],capture_output=True,text=True,check=True)
    (HERE/"evidence/legacy_recalculation.txt").write_text(p.stdout)


if __name__ == "__main__":
    main()
