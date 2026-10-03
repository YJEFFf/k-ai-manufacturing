"""E4 probability and policy diagnostics, after model selection."""
from __future__ import annotations
import json
import pickle
from scipy.optimize import minimize
from scipy.special import expit
from dataclasses import replace

from common import (HERE, core, np, pd, load_press, save, csv, policy, event_response, ratio)
from press import fit_candidates


def selected_names(selection):
    selected = selection["selected_candidate"]
    return ["B1", "C1d1"] if selected is None else ["B1", selected+"_s11" if selected.startswith("A2") else selected]


def logistic_head(score, labels, q):
    score, y = np.asarray(score), np.asarray(labels)
    finite = np.isfinite(score)
    x, y = score[finite], y[finite]
    n0, n1 = int((y == 0).sum()), int((y == 1).sum())
    if not n0 or not n1:
        return dict(status="unsupported_missing_class", q=q, excluded=int((~finite).sum()))
    weights = np.where(y == 1, q/n1, (1-q)/n0)
    mean = float(weights@x)
    std = float(np.sqrt(weights@((x-mean)**2)))
    if np.ptp(x) == 0 or std == 0:
        return dict(status="uninformative", q=q, mean=mean, std=1., a=0., b=float(np.log(q/(1-q))))
    x = (x-mean)/std
    def objective(theta):
        a, b = theta
        eta = a*x+b
        error = (expit(eta)-y)*weights
        return float(weights@(np.logaddexp(0, eta)-y*eta)+.5*a*a), np.array([error@x+a, error.sum()])
    result = minimize(objective, [0., np.log(q/(1-q))], method="L-BFGS-B", jac=True,
                      bounds=[(0, None), (None, None)], options=dict(maxiter=10000, ftol=1e-12, gtol=1e-8))
    a, b = result.x
    gradient = objective(result.x)[1]
    if a == 0:
        gradient[0] = min(0., gradient[0])
    projected = float(np.max(np.abs(gradient)))
    valid = projected <= 1e-6 and np.isfinite(result.fun) and a >= 0
    return dict(status="fitted" if valid else "optimizer_failure", a=float(a), b=float(b), q=q,
                mean=mean, std=std, projected_gradient=projected, objective=float(result.fun),
                optimizer_success=bool(result.success), message=str(result.message),
                n0=n0, n1=n1, excluded=int((~finite).sum()))


def probability(output, selection):
    normal, _ = load_press()
    abnormal, _ = load_press("abnormal")
    fit_records = [r for r in normal if r.start_m >= 0 and r.end_m < 40]
    head_records = [r for r in normal if r.start_m >= 40 and r.end_m < 50] + [r for r in abnormal if r.parent <= 13]
    cal_records = [r for r in normal if r.start_m >= 50 and r.end_m < 60]
    eval_records = [r for r in normal if r.start_m >= 60] + [r for r in abnormal if r.parent >= 14]
    h, e, cf = core.features(head_records), core.features(eval_records), core.features(cal_records)
    yh = np.array([r.source_namespace == "abnormal" for r in head_records], int)
    ye = np.array([r.source_namespace == "abnormal" for r in eval_records], int)
    names = selected_names(selection)
    models, _, _ = fit_candidates(fit_records, cf, "probability", augment=any(n.startswith("A2") for n in names))
    results, predictions, states = [], [], {}
    for name in names:
        scores = models[name].raw_score(h)
        eval_scores = models[name].raw_score(e)
        for q in [.01, .05, .1, .2]:
            state = logistic_head(scores, yh, q)
            states[f"{name}:{q}"] = state
            available = np.isfinite(eval_scores) & (state["status"] in ("fitted", "uninformative"))
            eta = np.full(len(e), np.nan)
            if available.any():
                eta[available] = state["a"]*(eval_scores[available]-state["mean"])/state["std"]+state["b"]
            p = expit(eta)
            row = dict(model=name, q=q, status=state["status"], n=len(e), available=int(available.sum()),
                       normal_n=int((ye == 0).sum()), positive_n=int(ye.sum()),
                       normal_supported=int((available & (ye == 0)).sum()), positive_supported=int((available & (ye == 1)).sum()),
                       probability_min=float(np.nanmin(p)) if available.any() else None,
                       probability_max=float(np.nanmax(p)) if available.any() else None,
                       probability_median=float(np.nanmedian(p)) if available.any() else None,
                       unique_predictions=len(np.unique(p[available])))
            if available.any() and len(np.unique(ye[available])) == 2:
                y, prob, logit = ye[available], p[available], eta[available]
                weights = np.where(y == 1, q/(y == 1).sum(), (1-q)/(y == 0).sum())
                loss = np.logaddexp(0, logit)-y*logit
                const_loss = -(y*np.log(q)+(1-y)*np.log1p(-q))
                row.update(brier_actual=float(np.mean((prob-y)**2)), logloss_actual=float(np.mean(loss)),
                           constant_brier_actual=float(np.mean((q-y)**2)), constant_logloss_actual=float(np.mean(const_loss)),
                           brier_q_weighted=float(weights@((prob-y)**2)), logloss_q_weighted=float(weights@loss),
                           constant_brier_q_weighted=float(weights@((q-y)**2)), constant_logloss_q_weighted=float(weights@const_loss))
                row["gain_established"] = bool(available.all() and row["brier_q_weighted"] < row["constant_brier_q_weighted"]
                                              and row["logloss_q_weighted"] < row["constant_logloss_q_weighted"])
            else:
                row["gain_established"] = False
            results.append(row)
            predictions.append(pd.DataFrame(dict(model=name, q=q, parent_key=e.parent_key, label=ye,
                                                  raw_score=eval_scores, probability=p, supported=available,
                                                  target="provided anomaly-episode label under declared q")))
    csv(output / "probability_metrics.csv", results)
    csv(output.parent / "cache/probability_predictions.csv.gz", pd.concat(predictions, ignore_index=True))
    save(output / "probability_heads.json", states)
    (output.parent / "artifacts/probability.pkl").write_bytes(pickle.dumps(dict(models=models, heads=states), protocol=5))
    save(output / "probability_roles.json", dict(fit=[r.parent for r in fit_records],
         head=[f"{r.source_namespace}:{r.parent}" for r in head_records],
         threshold_cal=[r.parent for r in cal_records], evaluation=[f"{r.source_namespace}:{r.parent}" for r in eval_records],
         field_fault_probability=False, one_positive_capture_episode=True,
         threshold_calibration_is_separate_from_main_P2=True))


def paired_response(times, bits, supported, quality, start, deadline):
    pair = {}
    for name in ["I0", "P23"]:
        result = policy(times, bits, supported, quality, name)
        pair[name] = event_response(result, times, start, deadline)
    a, b = pair["I0"], pair["P23"]
    return dict(I0_detected=a["detected"], P23_detected=b["detected"],
                lost=bool(a["detected"] and not b["detected"]),
                additional_decisions=b["valid_decision_ordinal"]-a["valid_decision_ordinal"] if a["detected"] and b["detected"] else None,
                I0_delay_s=a["delay_s"], P23_delay_s=b["delay_s"],
                I0_preexisting=a["preexisting_request"], P23_preexisting=b["preexisting_request"])


def policies(output, selection, states):
    normal, _ = load_press()
    selected = selection["selected_candidate"]
    name = "B1" if selected is None else selected+"_s11" if selected.startswith("A2") else selected
    synthetic = pd.read_csv(output.parent / "cache/press_development_synthetic.csv.gz", keep_default_na=False)
    synthetic = synthetic.loc[synthetic.model.eq(name) & synthetic.selection]
    summaries, changes, ramps, logs = [], [], [], []
    for fold in ["P0", "P1"]:
        records = core.split_records(normal, fold)["evaluation"]
        f = core.features(records)
        model = states[fold][name]
        original = model.predict(f)
        times = f.decision_m.to_numpy()*60
        parent_position = dict(zip(f.parent, range(len(f))))
        for pname in ["I0", "P23"]:
            result = policy(times, original["bit"], original["supported"], original["quality"], pname)
            summaries.append(dict(fold=fold, model=name, policy=pname,
                **{key:result[key] for key in ["mechanical_starts", "quality_tickets", "total_tickets", "threshold_positive", "suppressed", "occupancy_s"]}))
            logs.extend(dict(fold=fold, model=name, policy=pname, **r) for r in result["trace"])
        for row in synthetic.loc[synthetic.fold.eq(fold)].itertuples(index=False):
            j = parent_position[row.parent]
            if row.valid:
                b, valid, quality = [original[k].copy() for k in ["bit", "supported", "quality"]]
                b[j], valid[j], quality[j] = row.raw_bit, row.supported, row.quality
                response = paired_response(times, b, valid, quality, records[j].start_m*60, times[j])
            else:
                response = dict(I0_detected=False, P23_detected=False, lost=False, additional_decisions=None)
            changes.append(dict(fold=fold, parent=row.parent, family=row.family, target=row.target,
                                amplitude=row.amplitude, seed=row.seed, mode=row.mode, supported=row.valid, **response))
        for length in [20, 60]:
            for offset in range(0, len(records), length):
                window = records[offset:offset+length]
                supported = len(window) == length and np.all(np.diff(times[offset:offset+length]) <= 30)
                for target in [0, 1]:
                    for amplitude in [0., .25, .5]:
                        response = dict(I0_detected=False, P23_detected=False, lost=False, additional_decisions=None)
                        if supported:
                            changed = []
                            for j, r in enumerate(window):
                                x = r.x.copy()
                                if amplitude:
                                    dc = x[:, target].mean()
                                    x[:, target] = dc+(x[:, target]-dc)*(1+amplitude*j/(length-1))
                                changed.append(replace(r, x=x))
                            pp = model.predict(core.features(changed))
                            b, valid, quality = [original[k].copy() for k in ["bit", "supported", "quality"]]
                            b[offset:offset+length], valid[offset:offset+length], quality[offset:offset+length] = pp["bit"], pp["supported"], pp["quality"]
                            response = paired_response(times, b, valid, quality, window[1].start_m*60, times[offset+length-1])
                        ramps.append(dict(fold=fold, offset=offset, length=length, target=target, amplitude=amplitude,
                                          supported=supported, first_changed_start=window[1].start_m*60 if len(window)>1 else None,
                                          last_waveform_time=window[-1].end_m*60, **response))
        print(f"E4 {fold}: policy replay completed", flush=True)
    sums, changes, ramps = pd.DataFrame(summaries), pd.DataFrame(changes), pd.DataFrame(ramps)
    a = sums.loc[sums.policy.eq("I0")].set_index("fold")
    b = sums.loc[sums.policy.eq("P23")].set_index("fold")
    external = json.loads((output / "skab_policy_selection.json").read_text(encoding="utf-8"))
    nonzero_ramps = ramps.loc[ramps.amplitude.ne(0)]
    checks = dict(reduces_tickets=bool(b.total_tickets.sum() <= a.total_tickets.sum()-1),
                  no_fold_ticket_increase=bool((b.total_tickets <= a.total_tickets).all()),
                  no_fold_occupancy_increase=bool((b.occupancy_s <= a.occupancy_s+1e-10).all()),
                  single_no_lost_event=not bool(changes.lost.any()), ramp_no_lost_event=not bool(nonzero_ramps.lost.any()),
                  single_delay_cap=bool(changes.additional_decisions.dropna().le(1).all()),
                  ramp_delay_cap=bool(nonzero_ramps.additional_decisions.dropna().le(1).all()),
                  supported_each_fold=all(changes.loc[changes.fold.eq(fold), "supported"].any() for fold in ["P0", "P1"]),
                  external_counterexamples_pass=all(all(v for k, v in r["checks"].items() if k != "reduces_normal_tickets") for r in external.values()))
    decision = dict(model=name, policy="P23" if all(checks.values()) else "I0", checks=checks,
                    single_events=len(changes), single_supported=int(changes.supported.sum()), single_lost=int(changes.lost.sum()),
                    ramp_scenarios=len(ramps), ramp_supported=int(ramps.supported.sum()), ramp_lost=int(nonzero_ramps.lost.sum()),
                    ramp_zero_controls=int(ramps.amplitude.eq(0).sum()),
                    not_a_field_delay_SLA=True)
    csv(output / "press_policy_normal.csv", sums)
    csv(output / "press_policy_single_summary.csv", changes.groupby(["fold", "family"]).agg(
        scenarios=("supported", "size"), supported=("supported", "sum"), I0_detected=("I0_detected", "sum"),
        P23_detected=("P23_detected", "sum"), lost=("lost", "sum"), max_extra_decisions=("additional_decisions", "max")).reset_index())
    csv(output / "press_policy_ramps.csv", ramps)
    csv(output.parent / "cache/press_policy_single_events.csv.gz", changes)
    csv(output.parent / "cache/press_policy_normal_requests.csv.gz", logs)
    save(output / "press_policy_selection.json", decision)
    return decision
