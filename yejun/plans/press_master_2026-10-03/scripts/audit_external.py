"""Reproduce the initial structural audit, before SKAB group repair.

The six originally reserved test files stay unparsed here. Later mechanical
group/label checks cover all files and supersede that historical reservation.
No model performance is computed by either audit.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parents[1]
YEJUN=HERE.parents[1]


def skab():
    rec=json.loads((HERE/"evidence/skab_acquisition.json").read_text())
    rows=[]
    fingerprints={}
    duplicate_observations=0
    for file in rec["files"]:
        if file["split"]=="test":
            rows.append({"file":file["source_path"],"split":"test","status":"hash only; schema/values/labels reserved"})
            continue
        df=pd.read_csv(YEJUN/file["path"],sep=";")
        t=pd.to_datetime(df.datetime)
        sensors=[c for c in df if c not in ["datetime","anomaly","changepoint"]]
        payload=pd.util.hash_pandas_object(df[["datetime"]+sensors],index=False)
        for h in set(payload.tolist()):
            if h in fingerprints and fingerprints[h]!=file["source_path"]:
                duplicate_observations+=1
            fingerprints[h]=file["source_path"]
        row=dict(file=file["source_path"],split=file["split"],rows=len(df),columns=list(df),
                 missing=int(df.isna().sum().sum()),finite_sensors=bool(np.isfinite(df[sensors].to_numpy()).all()),
                 nonincreasing_times=int(t.diff().le(pd.Timedelta(0)).sum()),
                 dt_median_s=float(t.diff().dt.total_seconds().median()),
                 dt_max_s=float(t.diff().dt.total_seconds().max()))
        if "anomaly" in df:
            y=df.anomaly.to_numpy()
            row.update(normal_rows=int((y==0).sum()),abnormal_rows=int((y==1).sum()),
                       labels_binary=bool(np.isin(y,[0,1]).all()),
                       abnormal_starts=int(((y==1)&np.r_[True,y[:-1]!=1]).sum()),
                       changepoint_marks=int(df.changepoint.sum()))
        else:
            row["label_policy"]="normal-only by source description, no anomaly/changepoint columns"
        rows.append(row)
    return dict(files=rows,cross_file_identical_datetime_sensor_rows_non_test=duplicate_observations,
                total_parsed_rows=sum(r.get("rows",0) for r in rows),
                unparsed_test_files=sum(r["split"]=="test" for r in rows),
                scope="Historical acquisition split: structure and labels on its fit/dev/cal only; no model performance",
                reservation_superseded_by="evidence/skab_group_reservation.json; one former fit file is now reserved test")


def beihang():
    path=next((HERE/"data/beihang").glob("*.zip"))
    rows=[]
    with zipfile.ZipFile(path) as archive:
        names=sorted(n for n in archive.namelist() if n.endswith(".csv"))
        for name in names:
            with archive.open(name) as stream:
                header=next(csv.reader(io.TextIOWrapper(stream,encoding="utf-8-sig")))
            row=dict(file=name,columns=header,inspection="header/CRC only; values reserved")
            if "/Healthy state/1.csv" in name:
                with archive.open(name) as stream:
                    df=pd.read_csv(stream)
                pairs=[]
                for j in range(0,len(df.columns),2):
                    pair=df.iloc[:,j:j+2].dropna()
                    d=pair.iloc[:,0].diff()
                    positive=d[d>0]
                    med=float(positive.median())
                    pairs.append(dict(signal=str(df.columns[j+1]),valid_pairs=len(pair),
                                      start_time=float(pair.iloc[0,0]),end_time=float(pair.iloc[-1,0]),
                                      median_dt_s=med,implied_rate_hz=1/med,
                                      nonpositive_time_steps=int((d<=0).sum()),
                                      large_gaps_gt3median=int((positive>3*med).sum()),
                                      finite=bool(np.isfinite(pair.to_numpy()).all())))
                row.update(rows=len(df),pairs=pairs,inspection="full timing/missingness audit of healthy run 1 only")
            rows.append(row)
    return dict(files=rows,healthy_runs=2,fault_files=9,
                warning="Columns have separate time axes; never concatenate their row indices as synchronous samples.",
                reservation={"development":"healthy run 1, metadata and timing audit", "reserved":"healthy run 2 and all nine fault files; headers and archive CRC only"})


if __name__=="__main__":
    result={"skab":skab(),"beihang":beihang()}
    path=HERE/"evidence/external_audit.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"skab_rows":result["skab"]["total_parsed_rows"],
                      "skab_test_unparsed":result["skab"]["unparsed_test_files"],
                      "skab_duplicate_rows":result["skab"]["cross_file_identical_datetime_sensor_rows_non_test"],
                      "beihang_healthy1":[r for r in result["beihang"]["files"] if "pairs" in r]},ensure_ascii=False,indent=2))
