"""Build compact audit tables from saved aggregate evidence, without refitting."""
import json

import numpy as np
import pandas as pd

from core import HERE, save_json


def main():
    rows=[]
    for version in ["v1","v2"]:
        base=HERE/"evidence"/version
        decision=json.loads((base/"selection.json").read_text())
        normal=pd.read_csv(base/"normal_summary.csv").query("alpha == 0.05")
        audit=pd.read_csv(base/"audit_normal_summary.csv").query("alpha == 0.05")
        abnormal=pd.read_csv(base/"provided_abnormal.csv")
        losses=pd.read_csv(base/"loss_cells.csv")
        family=pd.read_csv(base/"development_family_pod.csv")
        for candidate in decision["candidates"]:
            name=candidate["model"]
            if version=="v2" and name=="B1":continue
            n=normal.loc[normal.model.eq(name)].set_index("fold")
            tp=abnormal.loc[abnormal.model.eq(name)].set_index("fold").mechanical_hits
            f=family.loc[family.model.eq(name)].set_index("family")
            loss=losses.loc[losses.model.eq(name)]
            mean=loss.loc[loss.seed.eq("mean")]
            fp=int(audit.loc[audit.model.eq(name),"total_requests"].iloc[0])
            positives=int(tp["P2"])
            row=dict(stage=version,model=name,
                normal_P0=int(n.loc["P0","total_requests"]),normal_P1=int(n.loc["P1","total_requests"]),
                normal_dev=int(n.total_requests.sum()),normal_P2=fp,
                provided_tp_P0=int(tp["P0"]),provided_tp_P1=int(tp["P1"]),provided_tp_P2=positives,
                provided_n_each_fold=21,provided_episodes=1,
                P2_f1=2*positives/(2*positives+fp+(21-positives)),
                worst_loss_gain_pp=float(loss.gain_pp.min()),
                failing_unique_mean_cells=int((mean.determinate & mean.gain_pp.lt(-5-1e-10)).sum()),
                failing_seed_cells=int((loss.seed.ne("mean") & loss.determinate & loss.gain_pp.lt(-5-1e-10)).sum()),
                indeterminate_cells=int((~mean.determinate).sum()),
                path_a=candidate["path_a"],path_b=candidate["path_b"],eligible=candidate["eligible"])
            for family_name in ["band_noise","damped_impulse","current_residual"]:
                row[family_name+"_pod"]=float(f.loc[family_name,"pod"])
                row[family_name+"_gain_pp"]=float(f.loc[family_name,"gain_pp"])
            rows.append(row)
    comparison=pd.DataFrame(rows)
    comparison.to_csv(HERE/"evidence/comparison.csv",index=False)
    curves=pd.read_csv(HERE/"evidence/v1/synthetic_curves.csv")
    representative=curves[(curves.model.isin(["B1","C1d1"])) & (
        (curves.family.eq("band_noise") & curves.amplitude.isin([.5,1])) |
        (curves.family.eq("damped_impulse") & curves.amplitude.isin([2,4])))]
    by_target=representative.groupby(["fold","model","family","target","amplitude","original_gate"])[
        ["detections","parents","new_detections","valid"]].sum().reset_index()
    # Counts in this intermediate aggregation include the three seeds. Divide
    # back to distinct real parents, never describe the larger count as n.
    by_target["distinct_parents"]=by_target.parents//3
    by_target["pod"]=by_target.detections/by_target.parents
    by_target["new_request_fraction"]=by_target.new_detections/by_target.parents
    by_target=by_target.rename(columns={"parents":"parent_seed_evaluations","detections":"detected_parent_seed_evaluations"})
    by_target.to_csv(HERE/"evidence/representative_target_pod.csv",index=False)
    save_json(HERE/"evidence/conclusions.json",dict(
        final_model=None, final_release_ready=False,
        reference_retained="B1 is the experiment comparator, not an approved final detector",
        unique_configurations=len(comparison),new_candidates=int(comparison.model.ne("B1").sum()),
        new_candidates_eligible=int(comparison.eligible.sum()),
        normal_development_parents=313,normal_retrospective_audit_parents=126,
        provided_abnormal_records=21,provided_abnormal_episodes=1,
        synthetic_seed_values=[11,29,47],synthetic_seeds_are_not_independent_faults=True,
        external_model_test_opened=False,heldout_H1_H2_generated=False,
        v1="Implemented master plus frozen disambiguations; press was already explored",
        v2="Exploratory follow-up designed after v1 outcomes including P2; not a fresh holdout",
        product_v2_restoration=False,
        limits=["No final candidate has met the registered joint burden/sensitivity/loss gates",
                "POD is response to declared synthetic perturbations, not actual independent fault recall",
                "P2 F1 uses 126 normal and the same 21 provided abnormal records; do not average folds",
                "External data are acquired and structurally audited, but external model performance is pending"]
    ))
    print(comparison[["model","normal_dev","normal_P2","provided_tp_P2","worst_loss_gain_pp","eligible"]].round(3).to_string(index=False))


if __name__=="__main__":main()
