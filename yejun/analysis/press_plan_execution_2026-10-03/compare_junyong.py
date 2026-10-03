"""Read-only reproduction of Junyong's pipeline and a same-fold record audit."""
from __future__ import annotations
import sys
import pickle

from common import (HERE, ROOT, core, pd, np, save, csv, import_file, metrics,
                    load_press, rank, canonical_sha, now)

SOURCE = ROOT / "claude/code/press/pipeline"


def modules():
    sys.dont_write_bytecode = True
    data = import_file("data", SOURCE / "data.py")
    scorer = import_file("scores", SOURCE / "scores.py")
    selection = import_file("junyong_select_w", SOURCE / "select_w.py")
    evaluate = import_file("junyong_evaluate", SOURCE / "evaluate.py")
    return data, scorer, selection, evaluate


def historical(output):
    before = {str(p.relative_to(SOURCE)):canonical_sha(p) for p in SOURCE.rglob("*.py")}
    data, sm, select, evaluation = modules()
    helper = data.load_vendor()
    normal, abnormal = [pd.read_csv(HERE / "data/press" / name) for name in ["press_data_normal.csv", "outlier_data.csv"]]
    result, windows, headline = [], [], []
    for split, train_end, cal_end in helper.SPLITS:
        train, cal, test = data.split_sets(normal, helper, train_end, cal_end)
        w, wt, tie = select.select_w(helper, train, cal)
        windows.append(wt.assign(split=split, selected=lambda d:d.w == w))
        scorer = sm.Scorer(train, helper.blocks, wins=sorted({8, w}), baselines=True)
        scores = [scorer.score(d, helper)[0] for d in [cal, test, abnormal]]
        ms, _, _ = evaluation.evaluate(helper, split, (cal, test, abnormal), {key:tuple(s[key] for s in scores) for key in scores[0]})
        result.extend(dict(**r, w_rule=w) for r in ms)
        for win, label in [(w, "normal_selected_window"), (8, "fixed_exploratory_window")]:
            key = f"maxz_plus_sine_{win}"
            ref = helper.segment_max(scores[0][key], helper.blocks(cal))
            threshold = helper.cutoff_at_budget(ref, .01)
            score = np.r_[scores[1][key], scores[2][key]]
            truth = np.r_[np.zeros(len(test), int), np.ones(len(abnormal), int)]
            pred = np.isfinite(score) & (score > threshold)
            headline.append(dict(split=split, model=key, window_policy=label, evaluation_unit="causal row",
                                 alpha=.01, **metrics(truth, pred, score)))
    table = pd.DataFrame(result)
    reference = pd.read_csv(SOURCE.parent / "outputs/pipeline/model_comparison.csv")
    keys = ["split", "model", "calibration_unit", "budget"]
    joined = table.merge(reference, on=keys, suffixes=("", "_stored"), validate="one_to_one")
    fields = ["tn", "fp", "fn", "tp", "normal_notified_segments", "abnormal_notified_segments"]
    exact = {c:bool(joined[c].eq(joined[c+"_stored"]).all()) for c in fields}
    csv(output / "junyong_historical_metrics.csv", table)
    csv(output / "junyong_historical_headline.csv", headline)
    csv(output / "junyong_window_selection.csv", pd.concat(windows, ignore_index=True))
    after = {str(p.relative_to(SOURCE)):canonical_sha(p) for p in SOURCE.rglob("*.py")}
    save(output / "junyong_reproduction.json", dict(source_unchanged=before == after, source_sha256=before,
        cells=len(joined), expected_cells=len(reference), exact_count_comparison=exact,
        max_abs_f1_difference=float((joined.f1_all_rows-joined.f1_all_rows_stored).abs().max()),
        reproduced_at_utc=now(), own_output_directory=True,
        note="Historical 1%/3%/5% order-statistic thresholds; original 600 normal segments retained here"))
    print("Junyong original pipeline metrics recalculated", flush=True)


def frame_for(records, raw):
    indices = [i for r in records for i in r.source_rows]
    return raw.iloc[indices].drop_duplicates(["TimeStamp"]+core.COLS).reset_index(drop=True)


def common_reference(output, fold="P2"):
    data, sm, _, _ = modules()
    helper = data.load_vendor()
    normal, _ = load_press()
    abnormal, _ = load_press("abnormal")
    raw = pd.read_csv(HERE / "data/press/press_data_normal.csv")
    ar = pd.read_csv(HERE / "data/press/outlier_data.csv")
    roles = core.split_records(normal, fold)
    fit, cal, ev = [frame_for(roles[role], raw) for role in ["fit", "cal", "evaluation"]]
    abnormal_frame = frame_for(abnormal, ar)
    scorer = sm.Scorer(fit, helper.blocks, wins=(8,), baselines=False)
    # Structural baseline fixed from the historical experiment, not selected on current evaluation.
    score = [scorer.score(frame, helper)[0]["maxz_plus_sine_8"] for frame in [cal, ev, abnormal_frame]]
    maxima = [helper.segment_max(s, helper.blocks(frame)) for s, frame in zip(score, [cal, ev, abnormal_frame])]
    assert [len(s) for s in maxima] == [len(roles["cal"]), len(roles["evaluation"]), len(abnormal)]
    combined = np.r_[maxima[1], maxima[2]]
    p, supported = rank(combined, maxima[0], .05)
    y = np.r_[np.zeros(len(roles["evaluation"]), int), np.ones(len(abnormal), int)]
    result = dict(model="Junyong_fixed_w8", fold=fold, evaluation_unit="completed record", alpha=.05,
                  **metrics(y, p <= .05, combined), score_definition="maximum causal row combination score within record",
                  calibration="same empirical rank as master plan", labels_used_for_fit=False)
    cache = pd.DataFrame(dict(model="Junyong_fixed_w8", parent_key=[f"{r.source_namespace}:{r.parent}" for r in roles["evaluation"]+abnormal],
                              score=combined, p=p, bit=p <= .05, supported=supported, label=y,
                              decision_m=[r.decision_m for r in roles["evaluation"]+abnormal]))
    csv(output.parent / f"cache/junyong_common_{fold}_predictions.csv.gz", cache)
    return result


if __name__ == "__main__":
    historical(HERE / "evidence")
