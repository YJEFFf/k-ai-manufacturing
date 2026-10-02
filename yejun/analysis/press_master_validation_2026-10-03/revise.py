"""Small, declared post-diagnosis experiment. Never rewrites registered v1 results."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist

from core import (HERE, BINS, Detector, RankCalibration, RobustLength, features,
                  finite_max, load_records, robust, save_json, sha, split_records)
from run import (manifest, normal_evaluation, selection_tables, summarize_synthetic,
                 synthetic_evaluation)

REVISION=json.loads((HERE/"design_v2.json").read_text())


class PooledLength(RobustLength):
    def fit(self,x,n):
        x,n=np.asarray(x),np.asarray(n)
        self.global_stats=robust(x)
        self.by_length={}
        c,s=self.global_stats
        for lo,hi in BINS:
            mask=(n>=lo)&(n<=hi)&np.isfinite(x)
            local_c,local_s=robust(x[mask])
            if mask.sum()<2 or not np.isfinite([c,s,local_c,local_s]).all():
                continue
            w=mask.sum()/(mask.sum()+30)
            self.by_length[(lo,hi)]=((1-w)*c+w*local_c,
                np.sqrt((1-w)*s*s+w*local_s*local_s+w*(1-w)*(local_c-c)**2))
        return self


class RevisedDetector(Detector):
    def __init__(self,label):
        base="C1d1" if label in ["S1_global_C1","S2_lower_C1","S3_shrink_C1"] else "B1"
        super().__init__(base)
        self.label=label

    def fit(self,f):
        super().fit(f)
        if "global" in self.label or self.label in ["S2_lower_C1","S5_vibration_knn_current"]:
            for scaler in self.pre.scalers.values(): scaler.by_length={}
            for scaler in self.residual_scalers.values(): scaler.by_length={}
        if "shrink" in self.label:
            for axis in self.pre.scalers:
                self.pre.scalers[axis]=PooledLength().fit(self.pre.logs(f,axis),f.n)
            mask=self.condition(f)
            if self.available:
                for j in range(2):
                    residual=self.pre.logs(f.loc[mask],f"v{j}_rms")-self.expected_log_rms(f.loc[mask],j)
                    self.residual_scalers[j]=PooledLength().fit(residual,f.loc[mask,"n"])
        if self.label=="S5_vibration_knn_current":
            self.vreference=self.vvector(f)
            d=cdist(self.vreference,self.vreference)
            np.fill_diagonal(d,np.inf)
            loo=np.mean(np.partition(d,4,axis=1)[:,:5],axis=1)
            vscore=finite_max(np.column_stack([np.abs(self.pre.z(f,f"v{j}_rms")) for j in range(2)]))
            self.distance_multiplier=float(np.nanquantile(vscore,.95)/np.quantile(loo,.95))
        return self

    def vvector(self,f):
        out=[]
        for axis in ["v0_rms","v1_rms","v0_peak","v1_peak"]:
            raw=self.pre.logs(f,axis)
            raw=np.where(np.isfinite(raw),raw,self.pre.medians[axis])
            out.append(np.nan_to_num(self.pre.scalers[axis].transform(raw,f.n),nan=0.))
        return np.column_stack(out)

    def score(self,f,diagnostic=False):
        trace=super().score(f,diagnostic=True)
        if self.label=="S2_lower_C1":
            trace["components"][:,0]=np.abs(trace["global_z"][:,0])
            trace["score"]=finite_max(trace["components"])
        elif self.label=="S5_vibration_knn_current":
            d=cdist(self.vvector(f),self.vreference)
            d[f.parent_key.to_numpy()[:,None]==self.fit_ids[None,:]]=np.inf
            distance=np.mean(np.partition(d,4,axis=1)[:,:5],axis=1)*self.distance_multiplier
            trace["components"][:,:2]=np.column_stack([distance,np.full(len(f),np.nan)])
            trace["score"]=finite_max(trace["components"])
        return trace if diagnostic else trace["score"]

    def parameters(self):
        out=super().parameters()
        out["revision_label"]=self.label
        if self.label=="S5_vibration_knn_current":out["distance_multiplier"]=self.distance_multiplier
        return out


def suite(fit,cal):
    models={name:RevisedDetector(name).fit(fit) for name in REVISION["models"]}
    calibrations={name:RankCalibration().fit(model.score(cal)) for name,model in models.items()}
    return models,calibrations


def development():
    start=time.perf_counter()
    meta=manifest("post_diagnosis_development",REVISION)
    meta["revision_sha256"]=sha(HERE/"design_v2.json")
    normal,contract=load_records()
    normals,synthetics,summary,blocks,strata,checks=[],[],[],[],[],[]
    parameters={}
    for fold in ["P0","P1"]:
        roles=split_records(normal,fold)
        fit,cal,evaluation=[features(roles[r]) for r in ["fit","cal","evaluation"]]
        models,calibrations=suite(fit,cal)
        nr,ns,nb,nt=normal_evaluation(evaluation,models,calibrations,fold)
        normals.append(nr);summary.extend(ns);blocks.extend(nb);strata.extend(nt)
        syn,sc=synthetic_evaluation(roles["evaluation"],evaluation,fit,models,calibrations,fold)
        synthetics.append(syn);checks.extend(sc)
        parameters[fold]={name:m.parameters() for name,m in models.items()}
        print(f"{fold}: bounded revision scored",flush=True)
    synthetic=pd.concat(synthetics,ignore_index=True)
    out=HERE/"evidence/v2"
    out.mkdir(parents=True,exist_ok=True)
    pd.concat(normals).to_csv(HERE/"cache/v2_normal_predictions.csv.gz",index=False)
    synthetic.to_csv(HERE/"cache/v2_synthetic_predictions.csv.gz",index=False)
    pd.DataFrame(summary).to_csv(out/"normal_summary.csv",index=False)
    pd.DataFrame(blocks).to_csv(out/"normal_timeblocks.csv",index=False)
    pd.DataFrame(strata).to_csv(out/"normal_strata.csv",index=False)
    pd.DataFrame(checks).to_csv(out/"injection_checks.csv",index=False)
    summarize_synthetic(synthetic).to_csv(out/"synthetic_curves.csv",index=False)
    decision,family,fold_family,loss=selection_tables(synthetic,summary,blocks)
    decision["status"]="Post-diagnosis exploratory screening; not a preregistered independent result"
    save_json(out/"selection.json",decision)
    family.to_csv(out/"development_family_pod.csv",index=False)
    fold_family.to_csv(out/"development_fold_pod.csv",index=False)
    loss.to_csv(out/"loss_cells.csv",index=False)
    save_json(out/"model_parameters.json",parameters)
    meta.update(data_contract=contract,completed_utc=datetime.now(timezone.utc).isoformat(),
                elapsed_s=time.perf_counter()-start,synthetic_score_rows=len(synthetic),
                selection_sha256=sha(out/"selection.json"))
    save_json(out/"run_manifest.json",meta)
    print(pd.DataFrame(summary).query("alpha==.05")[["fold","model","total_requests"]].to_string(index=False))
    print(decision)


def audit():
    decision_path=HERE/"evidence/v2/selection.json"
    if not decision_path.exists():raise ValueError("First record development decision")
    meta=manifest("post_diagnosis_audit",REVISION)
    meta["revision_sha256"]=sha(HERE/"design_v2.json")
    meta["selection_sha256"]=sha(decision_path)
    meta["selected_before_audit"]=json.loads(decision_path.read_text())["selected"]
    normal,_=load_records()
    abnormal,_=load_records("abnormal")
    af=features(abnormal)
    positives=[]
    for fold in ["P0","P1","P2"]:
        roles=split_records(normal,fold)
        fit,cal,evaluation=[features(roles[r]) for r in ["fit","cal","evaluation"]]
        models,calibrations=suite(fit,cal)
        if fold=="P2":
            nr,ns,nb,nt=normal_evaluation(evaluation,models,calibrations,fold)
        for name,model in models.items():
            s=model.score(af)
            positives.append(dict(fold=fold,model=name,n=len(af),episodes=1,
                mechanical_hits=int((calibrations[name].p(s)<=.05).sum()),
                condition_available=int(model.condition(af).sum())))
    out=HERE/"evidence/v2"
    nr.to_csv(HERE/"cache/v2_audit_predictions.csv.gz",index=False)
    pd.DataFrame(ns).to_csv(out/"audit_normal_summary.csv",index=False)
    pd.DataFrame(nb).to_csv(out/"audit_timeblocks.csv",index=False)
    pd.DataFrame(nt).to_csv(out/"audit_strata.csv",index=False)
    pd.DataFrame(positives).to_csv(out/"provided_abnormal.csv",index=False)
    meta["completed_utc"]=datetime.now(timezone.utc).isoformat()
    save_json(out/"audit_manifest.json",meta)
    print(pd.DataFrame(ns).query("alpha==.05")[["model","total_requests"]].to_string(index=False))
    print(pd.DataFrame(positives).to_string(index=False))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["development","audit"])
    args=parser.parse_args()
    development() if args.mode=="development" else audit()
