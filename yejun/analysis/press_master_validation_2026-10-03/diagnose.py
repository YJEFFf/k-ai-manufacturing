"""Post-result explanatory ablations; these cannot select a registered winner."""
import copy

import numpy as np
import pandas as pd

from core import (HERE, Detector, RankCalibration, features, load_records,
                  save_json, split_records)
from run import manifest


def main():
    meta=manifest("post_result_diagnosis")
    normal,_=load_records()
    abnormal,_=load_records("abnormal")
    ab=features(abnormal)
    rows, shifts, thresholds, abnormal_lengths=[] , [], [], []
    for fold in ["P0","P1","P2"]:
        roles=split_records(normal,fold)
        fit,cal,evaluation=[features(roles[k]) for k in ["fit","cal","evaluation"]]
        for name in ["B1","C1d1","C2d1"]:
            original=Detector(name).fit(fit)
            for mode in ["registered", "global_all", "global_features_only", "global_conditional_only"]:
                m=copy.deepcopy(original)
                if mode in ["global_all","global_features_only"]:
                    for scaler in m.pre.scalers.values(): scaler.by_length={}
                if mode in ["global_all","global_conditional_only"]:
                    for scaler in m.residual_scalers.values(): scaler.by_length={}
                calibration=RankCalibration().fit(m.score(cal))
                trace=m.score(evaluation,diagnostic=True)
                requests=calibration.p(trace["score"])<=.05
                hit=calibration.p(m.score(ab))<=.05
                rows.append(dict(fold=fold,model=name,ablation=mode,n=len(evaluation),
                                 requests=int(requests.sum()),abnormal_hits=int(hit.sum()),
                                 abnormal_n=len(ab),threshold=calibration.threshold(.05)))
                if mode=="registered":
                    threshold=calibration.threshold(.05)
                    for component in range(4):
                        thresholds.append(dict(fold=fold,model=name,component=component,
                            n_requests=int(requests.sum()),
                            crossing=int((trace["components"][:,component]>threshold).sum()),
                            sole_crossing=int(((trace["components"][:,component]>threshold)&
                                (np.sum(trace["components"]>threshold,axis=1)==1)).sum())))
                    for lo,hi in [(1,9),(10,19),(20,39),(40,50)]:
                        mask=ab.n.between(lo,hi).to_numpy()
                        abnormal_lengths.append(dict(fold=fold,model=name,length=f"{lo}-{hi}",
                                                     n=int(mask.sum()),hits=int(hit[mask].sum())))
        if fold=="P2":
            f=features(normal)
            f["minute"]=(f.end_m//10*10).astype(int)
            m=Detector("C1d1").fit(fit)
            for j in range(2): f[f"conditional_z{j}"]=m.conditional_z(f,j)
            for minute,g in f[f.n>=20].groupby("minute"):
                shifts.append(dict(minute=int(minute),n=len(g),
                    **{axis+"_median":float(g[axis].median()) for axis in
                       ["amplitude","v0_rms","v1_rms","i_residual","conditional_z0","conditional_z1"]}))
    out=HERE/"evidence/diagnosis"
    out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(out/"length_ablation.csv",index=False)
    pd.DataFrame(shifts).to_csv(out/"normal_state_shift.csv",index=False)
    pd.DataFrame(thresholds).to_csv(out/"threshold_components.csv",index=False)
    pd.DataFrame(abnormal_lengths).to_csv(out/"abnormal_by_length.csv",index=False)
    # Counterfactual: fixed fallback score, changed calibration distribution.
    loss=pd.read_csv(HERE/"evidence/v1/loss_cells.csv")
    bad=loss[(loss.model=="C1d1")&(loss.seed=="mean")&(loss.gain_pp < -5)]
    save_json(out/"diagnosis_manifest.json",dict(**meta,
        scope="Length ablation and attribution only; all outcomes observed, no blind inference",
        C1d1_failing_unique_mean_loss_cells=len(bad),
        C1d1_worst_loss_gain_pp=float(bad.gain_pp.min())))
    print(pd.DataFrame(rows).to_string(index=False))


if __name__=="__main__":
    main()
