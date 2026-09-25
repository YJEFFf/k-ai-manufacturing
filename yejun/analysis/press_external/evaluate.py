"""UCI 별도 검증. 대회 모델/데이터와 합치거나 대회 성능에 합산하지 않는다."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import sys
import time

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "press_submission"))
from press import data as D
from press.calibrate import conformal_p
from acquire import acquire


def features(archive):
    with ZipFile(archive) as z:
        profile = pd.read_csv(z.open("profile.txt"), sep="\t", header=None,
                              names=["cooler", "valve", "pump", "accumulator", "unstable"])
        blocks = []
        sensors = ["PS1", "EPS1", "FS1", "VS1"]
        for sensor in sensors:
            raw = np.loadtxt(z.open(sensor + ".txt"))
            assert raw.shape[0] == 2205 and np.isfinite(raw).all()
            blocks.append(raw.reshape(2205, 12, -1).mean(axis=2))
            print(sensor, raw.shape, flush=True)
    return np.stack(blocks, axis=1), profile


def fit_scores(x, train):
    means = x.mean(axis=2)
    simple = StandardScaler().fit(means[train])
    marginal = np.abs(simple.transform(means)).max(axis=1)
    flat = x.reshape(len(x), -1)
    scaler = StandardScaler().fit(flat[train])
    z = scaler.transform(flat)
    cov = LedoitWolf().fit(z[train])
    signature = np.sqrt(cov.mahalanobis(z))
    p, power, flow = x[:,0], x[:,1], x[:,2]
    assert (p > 0).all() and (power > 0).all() and (flow > 0).all()
    efficiency = np.log(power/(p*flow))
    normalizer = StandardScaler().fit(efficiency[train])
    eff_score = np.abs(normalizer.transform(efficiency)).max(axis=1)
    return dict(marginal_maxz=marginal, normal_signature=signature, hydraulic_efficiency=eff_score)


def main():
    start = time.monotonic()
    protocol = json.loads((HERE / "protocol.json").read_text())
    archive = acquire()
    x, profile = features(archive)
    stable = profile.unstable.eq(0).to_numpy()
    normal = profile.pump.eq(0).to_numpy()
    parts = np.full(len(profile), "excluded", dtype=object)
    for _, g in profile[stable & normal].groupby(["cooler", "valve", "accumulator"]):
        ids = g.index.to_numpy()
        n = len(ids)
        parts[ids[:int(.6*n)]] = "train"
        parts[ids[int(.6*n):int(.8*n)]] = "cal"
        parts[ids[int(.8*n):]] = "test_normal"
    parts[stable & ~normal] = "test_leak"
    rows, strata, partition_rows, prediction_rows = [], [], [], []
    for mode in ("local_normal_reference", "unseen_cooler"):
        for cooler in (3,20,100):
            here = profile.cooler.eq(cooler).to_numpy()
            source = here if mode == "local_normal_reference" else ~here
            train = np.flatnonzero((parts == "train") & source)
            cal = np.flatnonzero((parts == "cal") & source)
            test = np.flatnonzero(here & ((parts == "test_normal") | (parts == "test_leak"))) if mode == "local_normal_reference" else np.flatnonzero(here & stable)
            assert not set(train)&set(cal) and not set(train)&set(test) and not set(cal)&set(test)
            assert normal[train].all() and normal[cal].all()
            for name, ids in (("train",train),("cal",cal),("test",test)):
                partition_rows.extend(dict(mode=mode, cooler=cooler, partition=name, cycle_id=int(i)) for i in ids)
            all_scores = fit_scores(x, train)
            assert list(all_scores) == protocol["models"]
            y = (~normal[test]).astype(int)
            for model, score in all_scores.items():
                pv = conformal_p(score[cal], score[test])
                alarm = pv <= protocol["alpha"]
                tp = int((alarm & (y==1)).sum()); fp = int((alarm & (y==0)).sum())
                fn = int((~alarm & (y==1)).sum()); tn = int((~alarm & (y==0)).sum())
                row = dict(mode=mode, cooler=cooler, model=model, n_train=len(train), n_cal=len(cal),
                           n_test=len(test), alpha=protocol["alpha"], min_p=1/(len(cal)+1), tp=tp, fp=fp, fn=fn, tn=tn,
                           precision=tp/(tp+fp) if tp+fp else 0, recall=tp/(tp+fn),
                           f1=f1_score(y,alarm), normal_alarm_rate=fp/(tn+fp), auroc=roc_auc_score(y,score[test]))
                rows.append(row)
                for level in (0,1,2):
                    m = profile.pump.to_numpy()[test] == level
                    strata.append(dict(mode=mode,cooler=cooler,model=model,pump_leakage=level,n=int(m.sum()),alarms=int(alarm[m].sum()),alarm_rate=float(alarm[m].mean())))
                prediction_rows.extend(dict(mode=mode,cooler=cooler,model=model,cycle_id=int(i),pump_leakage=int(profile.pump.iloc[i]),score=float(s),p_value=float(p),alarm=int(a)) for i,s,p,a in zip(test,score[test],pv,alarm))
    pd.DataFrame(rows).to_csv(HERE/"metrics.csv",index=False)
    pd.DataFrame(strata).to_csv(HERE/"strata.csv",index=False)
    pd.DataFrame(partition_rows).to_csv(HERE/"partitions.csv",index=False)
    pd.DataFrame(prediction_rows).to_csv(HERE/"predictions_external.csv",index=False)
    audit = dict(cycles=len(profile), stable=int(stable.sum()), transient=int((~stable).sum()),
                 stable_leakage_counts=profile[stable].pump.value_counts().sort_index().to_dict(),
                 missing_features=int((~np.isfinite(x)).sum()), exact_duplicate_feature_cycles=int(pd.DataFrame(x.reshape(len(x),-1)).duplicated().sum()),
                 feature_shape=list(x.shape),partition_counts=pd.Series(parts).value_counts().to_dict())
    D.dump_json(dict(protocol=protocol,audit=audit,environment=D.environment(),input_sha256=D.sha256_file(archive),
                     code_sha256=D.sha256_file(Path(__file__)),elapsed_s=time.monotonic()-start,
                     output_hashes={n:D.sha256_file(HERE/n) for n in ("metrics.csv","strata.csv","partitions.csv")}),HERE/"manifest.json")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
