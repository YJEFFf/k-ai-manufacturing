"""SKAB G/C adapters. Development cannot open any reserved test capture."""
from __future__ import annotations
import csv as csvlib
import hashlib
import json
import pickle
from collections import defaultdict

from common import (HERE, MASTER, CONTRACT, core, np, pd, sha, save, csv, now,
                    metrics, interval_metrics, rank, policy, event_response, ratio)

SENSORS = ["Accelerometer1RMS", "Accelerometer2RMS", "Current", "Pressure", "Temperature",
           "Thermocouple", "Voltage", "Volume Flow RateRMS"]
RESERVATION = json.loads((MASTER / "evidence/skab_group_reservation.json").read_text(encoding="utf-8"))
RECEIPT = json.loads((MASTER / "evidence/skab_acquisition.json").read_text(encoding="utf-8"))
HASHES = {r["source_path"]: r["sha256"] for r in RECEIPT["files"]}


def load_groups(roles, access_log):
    groups, entries = {}, defaultdict(list)
    for item in RESERVATION["files"]:
        if item["split"] in roles:
            entries[item["group_id"]].append(item)
    for gid, files in entries.items():
        seen = {}
        for item in sorted(files, key=lambda r: r["path"]):
            path = HERE / "data/skab" / item["path"]
            if sha(path) != HASHES[item["path"]]:
                raise ValueError("SKAB input hash mismatch")
            access_log.append(dict(path=item["path"], role=item["split"], at_utc=now(), purpose="model_input"))
            last = None
            with path.open(encoding="utf-8", newline="") as stream:
                for row_number, row in enumerate(csvlib.DictReader(stream, delimiter=";")):
                    time = pd.Timestamp(row["datetime"]).value / 1e9
                    values = [float(row[c]) for c in SENSORS]
                    if not np.isfinite(time) or not np.isfinite(values).all() or min(values[:2]) < 0:
                        raise ValueError(f"input_contract_failed: {item['path']} row {row_number}")
                    if last is not None and time < last:
                        raise ValueError("input_contract_failed: time reversal")
                    last = time
                    key = hashlib.sha256("|".join([row["datetime"]]+[v.hex() for v in values]).encode()).hexdigest()
                    labels = []
                    for label in ["anomaly", "changepoint"]:
                        value = row.get(label)
                        if value is None and item["path"] == CONTRACT["skab"]["normal_label_exception"]["source_path"]:
                            value = "0"
                        try:
                            value = float(value)
                        except (TypeError, ValueError):
                            value = np.nan
                        labels.append(int(value) if value in (0, 1) else None)
                    if key not in seen:
                        seen[key] = dict(time=time, values=values, labels=[], source_rows=[], observation_sha256=key)
                    seen[key]["labels"].append(labels)
                    seen[key]["source_rows"].append([item["path"], row_number])
        rows = sorted(seen.values(), key=lambda r: r["time"])
        if np.any(np.diff([r["time"] for r in rows]) <= 0):
            raise ValueError("input_contract_failed: conflicting same timestamp")
        for row in rows:
            row["_labels"] = row.pop("labels")
        groups[gid] = dict(role=files[0]["split"], rows=rows)
    return groups


def finalize_labels(groups):
    """No label information is passed to a numerical model."""
    for group in groups.values():
        for row in group["rows"]:
            labels = row.pop("_labels")
            a, cp = [v[0] for v in labels], [v[1] for v in labels]
            invalid = None in a or None in cp
            row.update(lower=0 if None in a else min(a), upper=1 if None in a else max(a),
                       conflict=invalid or len(set(a)) > 1 or len(set(cp)) > 1,
                       anomaly_conflict=len(set(a)) > 1,
                       changepoint=int(1 in cp), label_invalid=invalid)
    return groups


def blocks(groups, dt):
    output, mapping, events, changepoints = [], [], [], []
    for gid, group in groups.items():
        rows = group["rows"]
        times = np.array([r["time"] for r in rows])
        segment = np.r_[0, np.cumsum(np.diff(times) > 1.5*dt)]
        for seg in np.unique(segment):
            positions = np.flatnonzero(segment == seg)
            for offset in range(0, len(positions), 20):
                ix = positions[offset:offset+20]
                selected = [rows[i] for i in ix]
                x = np.array([r["values"][:3] for r in selected])
                current = np.median(x[:, 2])
                feature = [np.median(x[:, 0]), np.median(x[:, 1]), abs(current),
                           np.median(np.abs(x[:, 2]-current))]
                uid = f"{gid}:{int(seg)}:{offset//20}"
                output.append(dict(group=gid, role=group["role"], segment=int(seg), parent_key=uid,
                                   n=len(ix), time=times[ix[-1]], start=times[ix[0]],
                                   lower=max(r["lower"] for r in selected), upper=max(r["upper"] for r in selected),
                                   conflict=any(r["conflict"] for r in selected),
                                   f0=feature[0], f1=feature[1], f2=feature[2], f3=feature[3]))
                for i in ix:
                    mapping.append(dict(parent_key=uid, observation_sha256=rows[i]["observation_sha256"],
                                        time=times[i], source_rows=rows[i]["source_rows"]))
            i = 0
            while i < len(positions):
                current = rows[positions[i]]
                if current["lower"] != 1 or current["conflict"]:
                    i += 1
                    continue
                first = i
                while i+1 < len(positions) and rows[positions[i+1]]["lower"] == 1 and not rows[positions[i+1]]["conflict"]:
                    i += 1
                last = i
                prior = rows[positions[first-1]] if first else None
                after = rows[positions[last+1]] if last+1 < len(positions) else None
                eligible = prior is not None and prior["upper"] == 0 and not prior["conflict"]
                right = after is None or after["conflict"]
                events.append(dict(group=gid, role=group["role"], event_id=f"{gid}:{int(seg)}:{first}",
                                   segment=int(seg), onset=times[positions[first]], deadline=times[positions[last]],
                                   eligible=eligible, left_censored=prior is None,
                                   onset_ambiguous=prior is not None and prior["conflict"],
                                   right_censored=right, boundary_uncertain=right or (prior is not None and prior["conflict"])))
                i += 1
        changepoints.extend(dict(group=gid, time=r["time"], conflict=r["conflict"])
                            for r in rows if r["changepoint"])
    return pd.DataFrame(output), mapping, events, changepoints


class Detector:
    def fit(self, fit):
        values = fit[[f"f{j}" for j in range(4)]].to_numpy()
        self.floor = np.array([np.median(v[v > 0])*1e-6 if np.any(v > 0) else np.nan for v in values.T])
        x = np.log(np.maximum(values, self.floor))
        self.center, self.scale = np.array([core.robust(v) for v in x.T]).T
        self.support = np.quantile(values[values[:, 2] > 0, 2], [.01, .99])
        mask = (values[:, 2] >= self.support[0]) & (values[:, 2] <= self.support[1])
        self.conditional_n = int(mask.sum())
        self.available = mask.sum() >= 30
        if self.available:
            condition = x[mask, 2]
            self.mean, self.std = condition.mean(), condition.std()
            if self.std == 0:
                self.std = 1.
            design = np.column_stack([np.ones(mask.sum()), (condition-self.mean)/self.std])
            self.beta = np.linalg.solve(design.T@design + np.diag([0, len(design)*.001]), design.T@x[mask, :2])
            residual = x[mask, :2]-design@self.beta
            self.res_center, self.res_scale = np.array([core.robust(v) for v in residual.T]).T
            self.available = bool(np.isfinite(self.res_scale).all())
        return self

    def scores(self, f):
        values = f[[f"f{j}" for j in range(4)]].to_numpy()
        x = np.log(np.maximum(values, self.floor))
        z = (x-self.center)/self.scale
        components = np.column_stack([np.abs(z[:, :3]), np.maximum(z[:, 3], 0)])
        g = (values[:, 2] > 0) & (values[:, 2] >= self.support[0]) & (values[:, 2] <= self.support[1]) & self.available
        conditional = components.copy()
        if self.available:
            design = np.column_stack([np.ones(len(x)), (x[:, 2]-self.mean)/self.std])
            rz = (x[:, :2]-design@self.beta-self.res_center)/self.res_scale
            g &= np.isfinite(rz).all(axis=1)
            conditional[g, :2] = np.abs(rz[g])
        complete = f.n.to_numpy() == 20
        return dict(G=np.where(complete, core.finite_max(components), np.nan),
                    C=np.where(complete, core.finite_max(conditional), np.nan), gate=g & complete)


def summarize_group(f, pred, event_list, cp_list, model, pname):
    response = policy(f.time, pred["bit"], pred["supported"], name=pname)
    trace = pd.DataFrame(response["trace"])
    certain = ~f.conflict.to_numpy() & (f.lower.to_numpy() == f.upper.to_numpy())
    normal = (f.upper.to_numpy() == 0)
    possible_normal = f.lower.to_numpy() == 0
    certain_normal = normal & ~f.conflict.to_numpy()
    count = int((trace.ticket_start.to_numpy() & certain_normal).sum())
    def occupancy(mask):
        end = np.r_[np.minimum(f.time.to_numpy()[1:], f.time.to_numpy()[:-1]+30), f.time.iloc[-1]]
        return float(sum((end-f.time.to_numpy())*mask*trace.active.to_numpy()))
    m = metrics(f.lower.to_numpy()[certain], pred["bit"][certain], pred["score"][certain])
    row = dict(group=f.group.iloc[0], model=model, policy=pname, **m,
               all_blocks=len(f), partial=int(f.n.ne(20).sum()), excluded_conflicting=int((~certain).sum()),
               normal_blocks=int(certain_normal.sum()), normal_tickets=count,
               normal_tickets_per_100=ratio(100*count, certain_normal.sum()),
               normal_ticket_upper=int((trace.ticket_start.to_numpy() & possible_normal).sum()),
               normal_occupancy_s=occupancy(certain_normal), possible_normal_occupancy_s=occupancy(possible_normal),
               mechanical_starts=response["mechanical_starts"], quality_tickets=response["quality_tickets"],
               total_tickets=response["total_tickets"], threshold_positive=response["threshold_positive"],
               suppressed=response["suppressed"], occupancy_s=response["occupancy_s"])
    events = []
    for event in event_list:
        after = f.loc[(f.time > event["deadline"]) & (f.n == 20), "time"]
        late = after.iloc[0] if len(after) else event["deadline"]
        events.append(dict(**event, model=model, policy=pname,
                           **event_response(response, f.time, event["onset"], event["deadline"], late)))
    eligible = [e for e in events if e["eligible"]]
    row.update(confirmed_events=len(eligible), detected_events=sum(e["detected"] for e in eligible),
               event_recall=ratio(sum(e["detected"] for e in eligible), len(eligible)),
               left_censored_events=sum(e["left_censored"] for e in events),
               ambiguous_onsets=sum(e["onset_ambiguous"] for e in events))
    for suffix, subset in [("completed", [e for e in eligible if not e["right_censored"]]),
                           ("right_censored", [e for e in eligible if e["right_censored"]])]:
        row[f"{suffix}_events"] = len(subset)
        row[f"{suffix}_detected"] = sum(e["detected"] for e in subset)
    cp = []
    start_times = f.time.to_numpy()[response["starts"]]
    for item in cp_list:
        later = start_times[start_times >= item["time"]]
        cp.append(dict(**item, model=model, policy=pname,
                       next_start_delay_s=float(later[0]-item["time"]) if len(later) else None))
    trace["group"], trace["model"], trace["policy"] = row["group"], model, pname
    return row, events, trace, cp


def evaluate(f, raw_events, cp, state, output, role):
    all_predictions, summaries, all_events, traces, cps = [], [], [], [], []
    scores = state["model"].scores(f)
    for model in state["models"]:
        p, supported = rank(scores[model], state["cal"][model])
        prediction = f.copy()
        prediction["model"], prediction["score"], prediction["p"] = model, scores[model], p
        prediction["supported"], prediction["bit"], prediction["gate"] = supported, p <= .05, scores["gate"]
        prediction["n_cal"], prediction["alpha"] = len(state["cal"][model]), .05
        all_predictions.append(prediction)
        for gid, group in prediction.groupby("group", sort=False):
            group = group.sort_values("time").reset_index(drop=True)
            info = {k: group[k].to_numpy() for k in ("score", "bit", "supported")}
            for pname in ("I0", "P23"):
                summary, events, trace, changes = summarize_group(group, info,
                    [e for e in raw_events if e["group"] == gid], [c for c in cp if c["group"] == gid], model, pname)
                summaries.append(summary); all_events.extend(events); traces.append(trace); cps.extend(changes)
    predictions = pd.concat(all_predictions, ignore_index=True)
    summary = pd.DataFrame(summaries)
    events = pd.DataFrame(all_events)
    csv(output / f"skab_{role}_groups.csv", summary)
    csv(output / f"skab_{role}_events.csv", events)
    csv(output / f"skab_{role}_changepoints.csv", cps)
    csv(output.parent / "cache" / f"skab_{role}_predictions.csv.gz", predictions)
    csv(output.parent / "cache" / f"skab_{role}_requests.csv.gz", pd.concat(traces, ignore_index=True))
    pooled = []
    bounds = []
    macro = []
    for model, group in predictions.groupby("model"):
        mask = ~group.conflict & group.lower.eq(group.upper)
        pooled.append(dict(model=model, role=role, **metrics(group.loc[mask, "lower"], group.loc[mask, "bit"], group.loc[mask, "score"])))
        bounds.append(dict(model=model, role=role, **interval_metrics(group.lower, group.upper, group.bit)))
        for metric in ("f1", "precision", "recall", "normal_tickets_per_100", "event_recall"):
            values = summary.loc[summary.model.eq(model) & summary.policy.eq("I0"), metric]
            macro.append(dict(model=model, metric=metric, equal_group_mean=values.mean(),
                              groups_available=int(values.notna().sum()), groups_undefined=int(values.isna().sum()),
                              exclusion_reason="zero required denominator"))
    csv(output / f"skab_{role}_pooled.csv", pooled)
    csv(output / f"skab_{role}_bounds.csv", bounds)
    csv(output / f"skab_{role}_macro.csv", macro)
    return summary, events


def policy_choices(summary, events):
    choices = {}
    for model in sorted(summary.model.unique()):
        base = summary.loc[summary.model.eq(model) & summary.policy.eq("I0")].set_index("group")
        other = summary.loc[summary.model.eq(model) & summary.policy.eq("P23")].set_index("group")
        checks = dict(reduces_normal_tickets=bool(other.normal_tickets.sum() <= base.normal_tickets.sum()-1))
        for col in ("normal_tickets", "normal_occupancy_s", "normal_ticket_upper", "possible_normal_occupancy_s"):
            checks[col+"_nonincreasing"] = bool((other[col] <= base[col]+1e-10).all())
        es = events.loc[events.model.eq(model) & events.eligible]
        a = es.loc[es.policy.eq("I0")].set_index("event_id")
        b = es.loc[es.policy.eq("P23")].set_index("event_id")
        checks["has_confirmed_event"] = len(a) > 0
        checks["no_lost_event"] = bool((~a.detected | b.detected).all())
        both = a.detected & b.detected
        checks["at_most_one_extra_decision"] = bool((b.loc[both, "valid_decision_ordinal"]-a.loc[both, "valid_decision_ordinal"] <= 1).all())
        choices[model] = dict(policy="P23" if all(checks.values()) else "I0", checks=checks,
                              events=len(a), lost_events=int((a.detected & ~b.detected).sum()))
    return choices


def development(output):
    access = []
    groups = finalize_labels(load_groups({"fit", "dev", "cal"}, access))
    dt = float(np.median([np.median(np.diff([r["time"] for r in g["rows"]]))
                          for g in groups.values() if g["role"] == "fit"]))
    f, mapping, events, cp = blocks(groups, dt)
    allowed = f.n.eq(20) & f.upper.eq(0) & ~f.conflict
    fit = f.loc[f.role.eq("fit") & allowed]
    cal = f.loc[f.role.eq("cal") & allowed]
    model = Detector().fit(fit)
    cal_scores = model.scores(cal)
    state = dict(model=model, dt=dt, models=["G", "C"], cal={k: cal_scores[k] for k in ["G", "C"]})
    artifacts = output.parent / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "skab.pkl").write_bytes(pickle.dumps(state, protocol=5))
    save(output.parent / "cache/skab_development_record_map.json", mapping)
    save(output / "skab_development_access.json", access)
    conflicts = sum(r["conflict"] for g in groups.values() for r in g["rows"])
    if conflicts != 237:
        raise AssertionError(f"Conflict-mask mismatch: {conflicts}")
    audit = f.groupby(["role", "group"]).agg(blocks=("n", "size"), samples=("n", "sum"))
    audit["normal_complete_used"] = f.loc[allowed].groupby(["role", "group"]).size()
    audit["partial"] = f.loc[f.n.ne(20)].groupby(["role", "group"]).size()
    audit["conflict"] = f.loc[f.conflict].groupby(["role", "group"]).size()
    csv(output / "skab_development_input.csv", audit.fillna(0).reset_index())
    cal_table = cal.copy()
    for key in ["G", "C"]:
        cal_table[key] = cal_scores[key]
    csv(output.parent / "cache/skab_cal_reference.csv.gz", cal_table)
    contributions = []
    for key in ["G", "C"]:
        threshold = np.sort(cal_scores[key])[max(0, len(cal)-int(np.floor(.05*(len(cal)+1))))]
        for gid, cg in cal_table.groupby("group"):
            contributions.append(dict(group=gid, model=key, normal_cal_blocks=len(cg), tail_blocks=int(cg[key].ge(threshold).sum())))
    csv(output / "skab_cal_contributions.csv", contributions)
    summary, event_table = evaluate(f.loc[f.role.eq("dev")].reset_index(drop=True),
        [e for e in events if e["role"] == "dev"], cp, state, output, "dev")
    choices = policy_choices(summary, event_table)
    save(output / "skab_policy_selection.json", choices)
    save(output / "skab_state_summary.json", dict(dt=dt, normal_fit=len(fit), normal_cal=len(cal),
         conditional_fit=model.conditional_n, conditional_available=model.available, conflicting_observations=conflicts,
         groups={r:sum(g["role"] == r for g in groups.values()) for r in ("fit", "dev", "cal")},
         test_opened=False))
    print("E1 SKAB development completed", flush=True)
    return state


def test(output):
    access = []
    state = pickle.loads((output.parent / "artifacts/skab.pkl").read_bytes())
    groups = finalize_labels(load_groups({"test"}, access))
    f, mapping, events, cp = blocks(groups, state["dt"])
    summary, event_table = evaluate(f, events, cp, state, output, "test")
    save(output / "skab_test_access.json", access)
    save(output.parent / "cache/skab_test_record_map.json", mapping)
    base = summary.loc[summary.model.eq("G") & summary.policy.eq("I0")].set_index("group")
    other = summary.loc[summary.model.eq("C") & summary.policy.eq("I0")].set_index("group")
    a = event_table.loc[event_table.model.eq("G") & event_table.policy.eq("I0") & event_table.eligible].set_index("event_id")
    b = event_table.loc[event_table.model.eq("C") & event_table.policy.eq("I0") & event_table.eligible].set_index("event_id")
    both = a.detected & b.detected
    checks = dict(normal_denominators_complete=bool(base.normal_tickets_per_100.notna().all()),
                  all_groups_have_confirmed_events=bool((base.confirmed_events > 0).all()),
                  normal_rate_nonincreasing=bool((other.normal_tickets_per_100 <= base.normal_tickets_per_100+1e-10).all()),
                  no_lost_event=bool((~a.detected | b.detected).all()),
                  latency_nonincreasing=bool((b.loc[both, "delay_s"] <= a.loc[both, "delay_s"]+1e-10).all()),
                  at_least_one_strict=bool((other.normal_tickets_per_100 < base.normal_tickets_per_100-1e-10).any()
                    or (~a.detected & b.detected).any() or (b.loc[both, "delay_s"] < a.loc[both, "delay_s"]-1e-10).any()))
    save(output / "skab_external_claim.json", dict(improvement_established=all(checks.values()), checks=checks,
         qualification="Other SKAB capture groups; not independent press faults"))
