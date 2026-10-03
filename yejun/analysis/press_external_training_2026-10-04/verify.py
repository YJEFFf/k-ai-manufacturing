"""Independent reaggregation of saved decisions and checks of training provenance."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(output):
    checks = []
    def check(name, passed):
        checks.append(dict(check=name, passed=bool(passed)))
        if not passed:
            raise AssertionError(name)
    freeze = json.loads((output/"freeze.json").read_text())
    check("protocol unchanged since execution freeze", sha(HERE/"protocol.json") == freeze["protocol_sha256"])
    for name, expected in freeze["code"].items():
        check(f"frozen code {name}", sha(HERE/name) == expected)
    check("source audit unchanged", sha(HERE/"evidence/source_audit.json") == freeze["source_audit_sha256"])
    folds = json.loads((output/"folds.json").read_text())
    for fold, roles in folds.items():
        fit, cal, ev = [set(roles[r+"_ids"]) for r in ("fit", "cal", "evaluation")]
        check(f"{fold} no target role overlap", not (fit & cal or fit & ev or cal & ev))
        check(f"{fold} target fitting normal only", all(k.startswith("normal:") for k in fit))
        check(f"{fold} exactly 21 original abnormal records", sum(k.startswith("abnormal:") for k in ev) == 21)
    m = pd.read_csv(output/"metrics.csv")
    with gzip.open(output/"predictions.jsonl.gz", "rt", encoding="utf-8") as stream:
        pred = pd.DataFrame(json.loads(line) for line in stream)
    keys = ["fold", "method", "source", "ratio", "seed", "view"]
    indexed_metrics = m.set_index(keys+["alpha"])
    metric_checks = 0
    for key, group in pred.groupby(keys, sort=False):
        cal, ev = [group[group.role.eq(role)] for role in ("cal", "evaluation")]
        check(f"calibration is original normal {key}", (cal.label == 0).all() and len(cal) == folds[key[0]]["role_counts"]["cal"])
        check(f"all evaluation records retained {key}", set(ev.parent_key) == set(folds[key[0]]["evaluation_ids"]))
        check(f"unique evaluation records {key}", ev.parent_key.is_unique)
        # Deliberately use direct comparisons, not the production searchsorted implementation.
        p = (1 + (cal.score.to_numpy()[:, None] >= ev.score.to_numpy()[None, :]).sum(axis=0))/(len(cal)+1)
        for alpha in (.05, .01, .03):
            alarm = (p <= alpha) & ev.supported.to_numpy()
            y = ev.label.to_numpy()
            counts = dict(tp=int(np.sum(alarm & (y == 1))), fp=int(np.sum(alarm & (y == 0))),
                          fn=int(np.sum(~alarm & (y == 1))), tn=int(np.sum(~alarm & (y == 0))))
            expected = indexed_metrics.loc[(*key, alpha)]
            check(f"confusion matrix {key} {alpha}", all(counts[k] == expected[k] for k in counts))
            tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
            check(f"F1 {key} {alpha}", abs(2*tp/(2*tp+fp+fn)-expected.f1) < 1e-12)
            check(f"ranking metrics {key} {alpha}", abs(roc_auc_score(y, ev.score)-expected.auroc) < 1e-12 and abs(average_precision_score(y, ev.score)-expected.ap) < 1e-12)
            metric_checks += 1
    check("all metric rows independently recalculated", metric_checks == len(m))
    for key, group in pred[pred.method.eq("pooled_knn")].groupby(["fold", "seed", "view", "role"]):
        a = group[group.source.eq("target_only")].set_index("parent_key").sort_index()
        b = group[group.source.eq("target_repeat_control")].set_index("parent_key").sort_index()
        check(f"duplicate control full scores {key}", np.array_equal(a.score.to_numpy(), b.score.to_numpy()))
    ledger = json.loads((output/"training_ledger.json").read_text())
    for arm in ledger:
        check(f"saved model reload {arm['fold']} {arm['method']} {arm['source']} {arm['ratio']} {arm['seed']}", arm["reload_exact"])
        check("external count equals actual selected examples", arm["external_examples"] == sum(p["selected"] for p in arm["parts"]))
        for part in arm["parts"]:
            check("source sampling never invents extra examples", part["selected"] <= min(part["available"], part["requested"]))
        if arm["method"] == "pretrained_ae":
            check("same target fine tuning amount", arm["finetune"]["steps"] == 300 and arm["finetune"]["available_examples"] == arm["target_channel_examples"])
            if arm["source"] != "target_scratch_reference":
                check("matched pretraining optimizer steps", arm["pretrain"]["steps"] == 300)
    result = dict(passed=True, checks=len(checks), recalculated_metric_rows=metric_checks,
                  prediction_rows=len(pred), target_training_role_checks=True,
                  all_model_reload_checks=True, duplicate_control_full_scores_exact=True)
    (output/"verification.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=str(HERE/"evidence"))
    args = p.parse_args()
    verify(Path(args.output).resolve())
