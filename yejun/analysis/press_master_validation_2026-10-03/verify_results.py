"""Check saved aggregates independently of detector fitting and result generation."""
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from core import HERE, MASTER, save_json, sha


def main():
    checks=[]
    def check(name,condition):checks.append(dict(name=name,passed=bool(condition)))
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text(),filename=str(path))
        check("syntax "+path.name,True)
    for path in HERE.glob("*.md"):
        for link in re.findall(r"\[[^\]]*\]\(([^)\n]+)\)",path.read_text()):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:",link) or link.startswith("#"):continue
            target=path.parent/link.split("#")[0].strip("<>")
            # The receipt is this command's output, not a prerequisite for its
            # first run. A failed write will raise rather than report success.
            if target.resolve()==(HERE/"evidence/verification.json").resolve():continue
            check("link "+link,target.exists())
    status=json.loads((MASTER/"execution_revision.json").read_text())["current_status"]
    conclusions=json.loads((HERE/"evidence/conclusions.json").read_text())
    for field_a,field_b in [
        ("normal_development_records","normal_development_parents"),
        ("normal_retrospective_audit_records","normal_retrospective_audit_parents"),
        ("provided_abnormal_records","provided_abnormal_records"),
        ("provided_abnormal_episodes","provided_abnormal_episodes"),
        ("unique_configurations_evaluated","unique_configurations"),
        ("new_candidates_evaluated","new_candidates"),
        ("new_candidates_meeting_all_admission_gates","new_candidates_eligible"),
        ("final_model","final_model"),("final_release_ready","final_release_ready")]:
        check("execution status agrees with evidence "+field_a,status[field_a]==conclusions[field_b])
    design=json.loads((HERE/"design_v1.json").read_text())
    for version in ["v1","v2"]:
        base=HERE/"evidence"/version
        receipt=json.loads((base/"run_manifest.json").read_text())
        for name,expected in receipt["code_sha256"].items():
            check(version+" original scoring code "+name,sha(HERE/name)==expected)
        check(version+" original master protocol",receipt["master_protocol_sha256"]==sha(MASTER/"protocol.json"))
        check(version+" disambiguations",receipt["design_sha256"]==sha(HERE/"design_v1.json"))
        if version=="v2":check(version+" revision freeze",receipt["revision_sha256"]==sha(HERE/"design_v2.json"))
        decision=json.loads((base/"selection.json").read_text())
        audit_receipt=json.loads((base/"audit_manifest.json").read_text())
        check(version+" audit references preceding decision",audit_receipt["selection_sha256"]==sha(base/"selection.json"))
        for prefix in ["","audit_"]:
            normal=pd.read_csv(base/(prefix+"normal_summary.csv"))
            blocks=pd.read_csv(base/(prefix+"timeblocks.csv" if prefix else "normal_timeblocks.csv"))
            summed=blocks.groupby(["fold","model","alpha"])[["n","total_requests"]].sum().sort_index()
            claimed=normal.set_index(["fold","model","alpha"])[["n","total_requests"]].sort_index()
            check(version+" "+prefix+" blocks conserve all records and requests",summed.equals(claimed))
            check(version+" "+prefix+" rates use real normal denominator",
                  np.allclose(normal.requests_per_100,100*normal.total_requests/normal.n))
            check(version+" "+prefix+" request accounting",
                  (normal.total_requests>=normal.normal_requests).all() and
                  (normal.total_requests<=normal.normal_requests+normal.quality_requests+normal.abstentions).all())
        normal=pd.read_csv(base/"normal_summary.csv").query("alpha == 0.05")
        blocks=pd.read_csv(base/"normal_timeblocks.csv").query("alpha == 0.05")
        curves=pd.read_csv(base/"synthetic_curves.csv")
        family=pd.read_csv(base/"development_family_pod.csv")
        fold_family=pd.read_csv(base/"development_fold_pod.csv")
        loss=pd.read_csv(base/"loss_cells.csv")
        check(version+" curve POD arithmetic",np.allclose(curves.pod,curves.detections/curves.parents))
        for spec in design["development"].values():
            curve=curves[curves.family.eq(spec["family"]) & curves.amplitude.isin(spec["selection"])]
            pooled=curve.groupby("model")[["detections","parents"]].sum()
            claimed=family.loc[family.family.eq(spec["family"])].set_index("model").pod
            check(version+" parent/target/strength/seed weighted POD "+spec["family"],
                  np.allclose((pooled.detections/pooled.parents).sort_index(),claimed.sort_index()))
        seed_loss=loss[loss.seed.ne("mean")].copy()
        keys=["fold","model","family","target","amplitude","mode","original_gate","seed"]
        for table in [seed_loss,curves]:
            table["mode"]=table["mode"].fillna("")
            table["seed"]=table["seed"].astype(str)
        matched=seed_loss.merge(curves[keys+["pod","valid"]],on=keys,suffixes=("_loss","_curve"),validate="one_to_one")
        check(version+" loss cells match independent curve aggregates",len(matched)==len(seed_loss) and
              np.allclose(matched.pod_loss,matched.pod_curve) and (matched.supported_parents==matched.valid).all())
        ref_normal=normal[normal.model.eq("B1")].set_index("fold").total_requests
        ref_blocks=blocks[blocks.model.eq("B1")].set_index(["fold","start_minute"]).total_requests
        for candidate in decision["candidates"]:
            name=candidate["model"]
            total=normal[normal.model.eq(name)].set_index("fold").total_requests
            block_delta=blocks[blocks.model.eq(name)].set_index(["fold","start_minute"]).total_requests-ref_blocks
            effects=family[family.model.eq(name)]
            improved=[]
            for _,effect in effects.iterrows():
                direction=fold_family[(fold_family.model==name)&(fold_family.family==effect.family)].gain_pp
                if effect.gain_pp>=10-1e-10 and direction.ge(-1e-10).all():improved.append(effect.family)
            path_a=ref_normal.sum()-total.sum()>=3 and (total<=ref_normal).all() and block_delta.le(1).all()
            path_b=len(improved)>=2 and block_delta.le(1).all()
            cells=loss[loss.model.eq(name)]
            loss_ok=cells.determinate.all() and cells.gain_pp.ge(-5-1e-10).all()
            expected=bool((path_a or path_b) and loss_ok and name!="B1")
            check(version+" admission recomputation "+name,
                  expected==candidate["eligible"] and bool(path_a)==candidate["path_a"] and bool(path_b)==candidate["path_b"])
        check(version+" new winner cannot bypass gates",decision["selected"] in [None,"B1"] or
              any(c["eligible"] and c["model"]==decision["selected"] for c in decision["candidates"]))
    replay=json.loads((HERE/"evidence/reproduction.json").read_text())
    check("fresh replay passed",replay["status"]=="pass" and all(r["matches"] for r in replay["comparisons"]))
    for name,expected in replay["code_sha256"].items():check("replay source "+name,sha(HERE/name)==expected)
    for row in replay["comparisons"]:check("replay output still intact "+row["path"],sha(HERE/row["path"])==row["expected_sha256"])
    paths=[p for p in HERE.rglob("*") if p.is_file() and not {"cache","__pycache__"}&set(p.relative_to(HERE).parts)]
    check("tracked candidate artifacts below 1 MB",all(p.stat().st_size<1_000_000 for p in paths))
    for path in (HERE/"evidence").rglob("*.csv"):
        columns=pd.read_csv(path,nrows=0).columns
        check("aggregate-only CSV "+str(path.relative_to(HERE)),
              not {"parent","parent_key","TimeStamp","AI0_Vibration","AI1_Vibration","AI2_Current","source_row"}&set(columns))
    failures=[c["name"] for c in checks if not c["passed"]]
    result=dict(status="fail" if failures else "pass",checked_utc=datetime.now(timezone.utc).isoformat(),
                scope="Aggregate arithmetic, admission logic, frozen inputs/code, numerical replay and artifact hygiene",
                checks=len(checks),failures=failures,check_results=checks)
    save_json(HERE/"evidence/verification.json",result)
    print(json.dumps({k:v for k,v in result.items() if k!="check_results"},indent=2))
    if failures:raise SystemExit(1)


if __name__=="__main__":main()
