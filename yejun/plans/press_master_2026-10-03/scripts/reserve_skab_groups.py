"""Repair SKAB split by acquisition overlap before any model fitting.

Reserved files are read only inside mechanical overlap/annotation consistency
checks. No test performance or sensor distributions are computed.
"""
import csv
import hashlib
import json
from pathlib import Path
from collections import Counter

HERE=Path(__file__).resolve().parents[1]
YEJUN=HERE.parents[1]
old=json.loads((HERE/"evidence/skab_acquisition.json").read_text())
files=old["files"]
parents={f["source_path"]:f["source_path"] for f in files}


def find(x):
    while parents[x]!=x:
        parents[x]=parents[parents[x]]
        x=parents[x]
    return x


def union(a,b):
    a,b=find(a),find(b)
    if a!=b:
        parents[max(a,b)]=min(a,b)


seen={}
edges=Counter()
times={}
rows_per_file={}
annotations={}
for f in files:
    name=f["source_path"]
    timestamps=[]
    with (YEJUN/f["path"]).open() as stream:
        reader=csv.DictReader(stream,delimiter=";")
        columns=[c for c in reader.fieldnames if c not in ["anomaly","changepoint"]]
        hashes=set()
        for row in reader:
            timestamps.append(row["datetime"])
            # Normalize equivalent decimal text, without exposing sensor values.
            key=[row["datetime"]]+[float(row[c]).hex() for c in columns if c!="datetime"]
            digest=hashlib.sha256("|".join(key).encode()).hexdigest()
            hashes.add(digest)
            labels=tuple(int(float(row.get(c,"0"))) for c in ["anomaly","changepoint"])
            if any(label not in [0,1] for label in labels):
                raise ValueError("Non-binary labels")
            annotations.setdefault(digest,[]).append((name,labels))
    times[name]=(min(timestamps),max(timestamps))
    rows_per_file[name]=len(timestamps)
    for h in hashes:
        for prev in seen.get(h,[]):
            edges[tuple(sorted([prev,name]))]+=1
            union(prev,name)
        seen.setdefault(h,[]).append(name)

interval_edges=[]
names=sorted(times)
for i,a in enumerate(names):
    for b in names[i+1:]:
        if max(times[a][0],times[b][0])<=min(times[a][1],times[b][1]):
            interval_edges.append([a,b])
            union(a,b)
groups={}
for name in names:
    groups.setdefault(find(name),[]).append(name)
prior={f["source_path"]:f["split"] for f in files}
out=[]
for group in groups.values():
    roles={prior[f] for f in group}
    if "test" in roles:
        role="test"
    elif "data/anomaly-free/anomaly-free.csv" in group:
        role="fit"
    else:
        role=max(roles,key={"fit":0,"dev":1,"cal":2}.get)
    gid=hashlib.sha256("|".join(sorted(group)).encode()).hexdigest()[:16]
    for name in group:
        out.append(dict(path=name,group_id=gid,split=role,previous_split=prior[name],
                        rows=rows_per_file[name],time_start=times[name][0],time_end=times[name][1]))
result=dict(revision=old["revision"],
            rule="Union shared datetime+all sensors OR overlapping acquisition time intervals. Preserve original test groups; anomaly-free component to fit; remaining components cal > dev > fit. No model outcomes used.",
            exact_overlap_edges=[dict(a=a,b=b,shared_rows=n) for (a,b),n in sorted(edges.items())],
            overlapping_time_edges=interval_edges,group_count=len(groups),
            split_file_counts=dict(Counter(r["split"] for r in out)),
            split_group_counts={s:len({r["group_id"] for r in out if r["split"]==s}) for s in ["fit","dev","cal","test"]},
            files=sorted(out,key=lambda x:x["path"]),
            test_access="Downloaded and hashed. Datetime and sensor values canonicalized for overlap; labels checked only for duplicate-annotation conflicts. No test sensor summaries or model results inspected. Some files were structurally inspected before group repair; not a claim of fully unseen raw files.",
            caveat="Conservative same-capture grouping; absence of exact/time overlaps does not prove independent equipment, runs or near-duplicates. Use file/group weighting and inspect further provenance before stronger claims.")
(HERE/"evidence/skab_group_reservation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
conflicts=[]
for digest,items in annotations.items():
    any_conflict=len({labels for _,labels in items})>1
    if any_conflict:
        conflicts.append(dict(observation_sha256=digest,
                              sources=[dict(path=name,anomaly=label[0],changepoint=label[1]) for name,label in items],
                              anomaly_conflict=len({label[0] for _,label in items})>1))
mask_path=HERE/"cache/skab_label_conflicts.json"
mask_path.parent.mkdir(parents=True,exist_ok=True)
mask_path.write_text(json.dumps(conflicts,ensure_ascii=False,indent=2)+"\n")
by_path={r["path"]:r for r in out}
conflict_pairs=Counter()
conflict_splits=Counter()
for conflict in conflicts:
    sources=sorted({source["path"] for source in conflict["sources"]})
    conflict_pairs[tuple(sources)]+=1
    roles={by_path[name]["split"] for name in sources}
    if len(roles)!=1:
        raise ValueError("Conflicting observation crossed repaired split")
    conflict_splits[next(iter(roles))]+=1
summary=dict(scope="Mechanical duplicate-label consistency only, including reserved groups. anomaly-free rows treated as 0 by source description. No performance or overall test label distributions inspected.",
             conflicting_shared_observations=len(conflicts),
             conflicting_anomaly_observations=sum(c["anomaly_conflict"] for c in conflicts),
             conflicting_by_split=dict(conflict_splits),
             conflicting_by_source_set=[dict(paths=list(paths),observations=count) for paths,count in sorted(conflict_pairs.items())],
             mask_path=str(mask_path.relative_to(HERE)),
             mask_sha256=hashlib.sha256(mask_path.read_bytes()).hexdigest(),
             mask_policy="Row-derived mask stays local and is regenerated by this script. Only aggregate audit counts are committed.",
             policy="Do not treat any conflicting observation or overlapping input window as confirmed normal for fit/cal. Keep ambiguity/coverage and worst/best bounds in evaluation; never choose labels to favor a model.")
(HERE/"evidence/skab_label_consistency.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print("Conflicting observations:",summary["conflicting_shared_observations"],"anomaly:",summary["conflicting_anomaly_observations"])
print(json.dumps({k:v for k,v in result.items() if k!="files"},ensure_ascii=False,indent=2))
