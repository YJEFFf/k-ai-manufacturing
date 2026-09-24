"""Independent implementation review; all destructive probes use temporary copies.

Run with press_submission/requirements.txt installed:
  python review_checks.py --package ../../press_submission --outputs <rerun outputs> --out review_results.json
The package and its outputs are never changed. A reproduced issue is recorded,
not treated as a successful production acceptance test.
Report generation was removed at the user's request on 2026-09-25.
The R5 probe now checks absence; it never recreates a report draft.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--outputs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    pkg, outputs = args.package.resolve(), args.outputs.resolve()
    sys.path.insert(0, str(pkg))
    import numpy as np
    import pandas as pd
    import torch
    from press import data as D, lstm_ae
    from press.artifact import Artifact
    from press.field import persistence_score
    from predict import predict_frame
    import verify

    findings = {}
    env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="press-review-probes-") as scratch:
        tmp = Path(scratch)

        def add(name, **facts):
            findings[name] = facts
            print(name + ": " + json.dumps(facts, ensure_ascii=False), flush=True)

        def verify_case(name, edit):
            d = tmp / name
            shutil.copytree(pkg / "outputs", d)
            edit(d)
            r = subprocess.run([sys.executable, str(pkg / "verify.py"), "--out", str(d)],
                               env=env, text=True, capture_output=True)
            return dict(exit_code=r.returncode, summary=r.stdout.strip().splitlines()[-1],
                        failures=[line for line in r.stdout.splitlines() if line.startswith("FAIL")])

        normal, abnormal, load_info = D.load(pkg)
        mt = pd.read_csv(outputs / "operating_points.csv")
        main_rows, before_rows = [], []
        for sid, (_, train_end, cal_end) in D.SPLITS.items():
            # Reconstruct boundaries and metrics without the package evaluator.
            nt = pd.to_datetime(normal[D.TIME])
            group = (nt.diff().dt.total_seconds().sub(0.1).abs() > 1e-6).cumsum().to_numpy()
            test = normal[group >= cal_end].reset_index(drop=True)
            stream = pd.concat([test, abnormal], ignore_index=True)
            art = Artifact.load(pkg / "artifacts" / f"main_{sid}.json")
            pred = predict_frame(art, stream)
            pfile = pd.read_csv(outputs / f"predictions_{sid}.csv")
            t = pd.to_datetime(stream[D.TIME])
            record = (t.diff().dt.total_seconds().sub(0.1).abs() > 1e-6).cumsum()
            truth = np.arange(len(stream)) >= len(test)
            alarm = pred.alarm.to_numpy(bool)
            fp, fn = int((alarm & ~truth).sum()), int((~alarm & truth).sum())
            tp = int((alarm & truth).sum())
            notified_n = int(pd.Series(alarm[~truth]).groupby(record[~truth].to_numpy()).max().sum())
            notified_a = int(pd.Series(alarm[truth]).groupby(record[truth].to_numpy()).max().sum())
            f1 = 2 * tp / (2 * tp + fp + fn)
            selected = mt[(mt.split_id == sid) & (mt.criterion == "conformal") &
                          (mt.calibration_unit == "recording_segments") & (mt.alpha == .01)].iloc[0]
            main_rows.append(dict(split=sid, normal_notified=notified_n, abnormal_detected=notified_a,
                                  fp_rows=fp, fn_rows=fn, f1=f1,
                                  metrics_equal=bool(notified_n == selected.normal_notified_segments and
                                                     notified_a == selected.abnormal_notified_segments and
                                                     abs(f1-selected.f1_all_rows) < 1e-12),
                                  cli_prediction_path_equal=bool(np.allclose(pred.combined_score,
                                      pfile.combined_score, equal_nan=True) and np.array_equal(alarm,pfile.alarm))))
            fn_table = pd.read_csv(outputs / "error_conditions_fn.csv")
            for alpha, col in ((.01,"alarm"),(.03,"alarm_conformal_0.03"),(.05,"alarm_conformal_0.05")):
                a = pred[col].to_numpy(bool)
                count = 0
                for rid in np.unique(record[truth]):
                    ix = np.flatnonzero(record.to_numpy() == rid)
                    hits = np.flatnonzero(a[ix])
                    count += int(hits[0]) if len(hits) else len(ix)
                tab = fn_table[(fn_table.split == D.SPLITS[sid][0]) & (fn_table.alpha == alpha) &
                               (fn_table.condition == "pos_bin")]
                reported = int(tab.rows_before_first_alarm.sum())
                before_rows.append(dict(split=sid,alpha=alpha,reported=reported,recomputed=count,
                                        equal=reported == count))
            prefix = predict_frame(art, abnormal.head(40))
            full = predict_frame(art, abnormal)
            assert np.allclose(prefix.combined_score, full.combined_score.iloc[:40], equal_nan=True)
            damaged = abnormal.head(40).copy()
            damaged.loc[10,D.SENSORS[0]] = np.nan
            damaged.loc[20,D.TIME] = "bad timestamp"
            checked = predict_frame(art, damaged)
            assert list(checked.loc[[10,20],"status"]) == ["bad_value","bad_timestamp"]
            assert checked.loc[[10,20],"is_scored"].sum() == 0
            assert len(checked) == len(damaged)
        add("main_metrics_independent", rows=main_rows, prefix_and_bad_input_checks=True)
        add("first_alarm_counts_by_alpha", issue_reproduced=any(not r["equal"] for r in before_rows), rows=before_rows)

        missing = verify_case("missing_result", lambda d: (d/"model_comparison_all.csv").unlink())
        add("verify_missing_result", issue_reproduced=missing["exit_code"] == 0, **missing)

        def empty_results(d):
            for f in d.iterdir():
                if f.is_file() and f.name != "manifest.json": f.unlink()
        missing_all = verify_case("all_results_missing", empty_results)
        add("verify_all_results_missing", issue_reproduced=missing_all["exit_code"] == 0, **missing_all)

        def corrupt_diagnosis(d):
            p=d/"diagnosis.json"; obj=json.loads(p.read_text()); obj["structure"]["normal"]["rows"] = -123
            p.write_text(json.dumps(obj))
        diag = verify_case("wrong_diagnosis", corrupt_diagnosis)
        add("verify_corrupted_diagnosis", issue_reproduced=diag["exit_code"] == 0, **diag)

        def change_runtime_metadata(d):
            p=d/"lstm_guidebook_reproduction.json"; obj=json.loads(p.read_text())
            obj.update(cached=False,train_seconds=1.0); p.write_text(json.dumps(obj))
        cold = verify_case("cold_metadata_only", change_runtime_metadata)
        add("verify_cold_runtime_metadata", issue_reproduced=cold["exit_code"] != 0, **cold)

        a,b=tmp/"finite_a.csv",tmp/"finite_b.csv"
        pd.DataFrame({"threshold":[np.inf]}).to_csv(a,index=False)
        pd.DataFrame({"threshold":[np.nan]}).to_csv(b,index=False)
        nf=verify.compare_csv(a,b)
        add("verify_inf_to_nan", issue_reproduced=nf["ok"], comparison=nf)

        # Exercise the public runner with a failed required check. Its exit code
        # must not claim success merely because metrics could still be written.
        fail_out=tmp/"failed_check_output"
        injected=("import run_all,sys; "
                  "run_all.mc_check_conformal=lambda: [dict(realized=1.0,alpha_grid=.01,mc_se=.001)]; "
                  "run_all.main(sys.argv[1:])")
        gate=subprocess.run([sys.executable,"-c",injected,"--root",str(pkg),"--out",str(fail_out),
                             "--artifacts",str(tmp/"failed_check_artifacts"),"--steps","2","--no-baselines"],
                            cwd=pkg,env=env,text=True,capture_output=True)
        failed=json.loads((fail_out/"checks.json").read_text())["conformal_mc_within_4se"]
        add("runner_failed_check_exit",issue_reproduced=gate.returncode==0 and not failed,
            exit_code=gate.returncode,conformal_mc_within_4se=failed)

        score=np.array([10.,10.,10.,np.nan,0.,0.,0.])
        got=persistence_score(score,np.zeros(len(score),int),2,3)
        want=np.array([np.nan,np.nan,10.,np.nan,np.nan,np.nan,0.])
        add("persistence_missing_reset", issue_reproduced=not np.allclose(got,want,equal_nan=True),
            actual=got.tolist(), expected=want.tolist())

        # A tiny real training run, then change the model's implementation while
        # retaining the input/config. The cached scores must not conceal that change.
        rng=np.random.default_rng(7)
        train=pd.DataFrame(rng.normal(size=(180,3)),columns=D.SENSORS)
        seg=np.repeat(np.arange(6),30)
        frames={k:train.iloc[:60].copy() for k in ("cal","test","abn")}
        segs={k:np.repeat(np.arange(2),30) for k in frames}
        cache=tmp/"tiny_lstm_cache"
        extra={"split":"review_synthetic","preprocess":"raw","inputs":{"synthetic":"same-input"}}
        call=(train,seg,frames,segs,np.zeros(3),np.ones(3),cache,1,1,0,extra)
        old,_,_,_=lstm_ae.protocol_common(*call,log=lambda *_:None)
        src=(pkg/"press"/"lstm_ae.py").read_text()
        assert "return self.out(h)" in src
        modified=tmp/"modified_lstm_ae.py"
        modified.write_text(src.replace("return self.out(h)","return self.out(h) + 100.0"))
        spec=importlib.util.spec_from_file_location("press.review_modified_lstm",modified)
        altered=importlib.util.module_from_spec(spec); spec.loader.exec_module(altered)
        cached,_,meta,_=altered.protocol_common(*call,log=lambda *_:None)
        fresh,_,fresh_meta,_=altered.protocol_common(*call,retrain=True,log=lambda *_:None)
        same=all(np.allclose(old[k],cached[k],equal_nan=True) for k in old)
        delta=float(np.nanmax(np.abs(cached["test"]-fresh["test"])))
        add("cache_reuses_changed_implementation", issue_reproduced=bool(meta["cached"] and same and delta>1),
            cache_hit_after_code_change=meta["cached"], old_scores_reused=same,
            forced_retrain_max_score_delta=delta, cache_key=meta["cache_key"])

        legacy_generator=(pkg/"press/evidence.py").exists()
        report_draft=(pkg/"evidence/보고서_근거_장별.md").exists()
        add("report_generation_removed", issue_reproduced=legacy_generator or report_draft,
            legacy_generator_exists=legacy_generator, report_draft_exists=report_draft,
            report_work="deferred_until_explicit_user_instruction")

        manifest=json.loads((outputs/"manifest.json").read_text())
        stale_hash=[]
        for name,digest in manifest["outputs"].items():
            p=outputs/name
            if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()!=digest: stale_hash.append(name)
        add("manifest_output_hashes", issue_reproduced=bool(stale_hash), mismatches=stale_hash,
            checks_json_in_manifest="checks.json" in manifest["outputs"],
            git_commit=manifest.get("git_commit"), run_id=json.loads((outputs/"numbers.json").read_text()).get("run_id"))

    result={"reviewed_package":str(pkg),"torch":torch.__version__,"python":sys.version,
            "findings":findings}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=True))


if __name__=="__main__": main()
