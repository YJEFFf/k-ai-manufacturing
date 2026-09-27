"""라벨 지도학습 기준선 — 흔한 평가(무작위 행 분할)와 엄격한 평가(이상 기록 묶음 교차검증·고장 주입 전이)를 나란히 본다.

    python yejun/analysis/press_supervised/run.py   # 약 2.5분

최종모델 v2(이상 라벨 미사용)의 선정근거를 정확히 적기 위한 비교이며 대회 보고서가 아니다. 설계는 protocol.json(v2).
정상 학습·보정·평가 구간은 v2와 같다. 특징은 창 특징만 쓴 것과 v2 성분을 더한 것 두 가지다.
"""
from pathlib import Path
import argparse
import json
import sys
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
sys.path.insert(0, str(YEJUN / "analysis" / "press_supplement"))
from common import D, BASE, frozen, inject, standard_noise, record_detection, E1  # noqa: E402
from model import layout  # noqa: E402

PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
MODELS = {
    "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
    "hgb": lambda: HistGradientBoostingClassifier(random_state=0),
    "logistic_balanced": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")),
    "hgb_balanced": lambda: HistGradientBoostingClassifier(random_state=0, class_weight="balanced"),
}
FOLDS = {"3fold": (np.arange(0, 7), np.arange(7, 14), np.arange(14, 21)), "21fold": tuple(np.array([k]) for k in range(21))}
ALPHA = .01


def window_features(frame, quant="matched"):
    """기록구간 안의 창 특징 22개. 라벨·시각·파일명은 쓰지 않는다."""
    q = D.quantize(D.inputs_only(frame), quant)
    seg = D.segments(q)
    pos, _ = D.segment_positions(seg)
    out = pd.DataFrame(index=q.index)
    for c in D.SENSORS:
        x = q[c]
        g = x.groupby(seg)
        out[c] = x
        for w in (3, 8):
            out[f"{c}_mean{w}"] = g.transform(lambda s: s.rolling(w, min_periods=1).mean())
            out[f"{c}_std{w}"] = g.transform(lambda s: s.rolling(w, min_periods=2).std()).fillna(0)
        out[f"{c}_d1"] = g.diff().fillna(0)
    out["position"] = np.minimum(pos, 10)
    return out.reset_index(drop=True)


def features(frame, kind, model):
    """kind='window'은 창 특징만, 'window_plus_v2'는 같은 분할 v2 모델(정상 학습만으로 적합)의 성분을 더한다."""
    x = window_features(frame)
    if kind == "window":
        return x
    q = D.quantize(D.inputs_only(frame), "matched")
    comp = model.components(q, layout(q)[1])
    for key in ("magnitude", "current_residual", "g_magnitude", "g_waveform", "g_dynamics"):
        v = np.asarray(comp[key], float)
        x[f"v2_{key}"] = np.where(np.isfinite(v), v, -1.0)
        if key in ("current_residual", "g_waveform", "g_dynamics"):
            x[f"v2_{key}_missing"] = (~np.isfinite(v)).astype(float)
    return x


def conformal_threshold(model, X_cal, seg_cal):
    """정상 보정 기록구간의 최대 확률로 문턱을 정한다(α=1%, 보정 120구간이면 최댓값). 확률이 문턱보다 커야 경보."""
    record_max = pd.Series(model.predict_proba(X_cal)[:, 1]).groupby(seg_cal).max().to_numpy()
    n = len(record_max)
    allowed = int(np.floor(ALPHA * (n + 1) - 1 + 1e-9))
    return float(np.sort(record_max)[::-1][allowed]) if 0 <= allowed < n else float("inf")


def row_metrics(y, alarm):
    tp, fp = int((alarm & (y == 1)).sum()), int((alarm & (y == 0)).sum())
    fn = int((~alarm & (y == 1)).sum())
    return dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0,
                precision=tp / (tp + fp) if tp + fp else 0.0, recall=tp / (tp + fn))


def random_rows(normal, abnormal):
    rows = []
    y = np.r_[np.zeros(len(normal)), np.ones(len(abnormal))]
    for quant in ("raw", "matched"):
        X = pd.concat([window_features(normal, quant), window_features(abnormal, quant)], ignore_index=True)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.3, stratify=y, random_state=0)
        for name, make in MODELS.items():
            alarm = make().fit(Xtr, ytr).predict_proba(Xte)[:, 1] >= .5
            rows.append(dict(protocol="random_rows", features=f"window({quant})", model=name, rows_test=len(yte), **row_metrics(yte, alarm)))
    text = {k: pd.read_csv(D.data_dir(BASE) / D.FILES[k], dtype=str, keep_default_na=False) for k in D.FILES}
    digits = lambda s: s.str.strip().str.lstrip("-").str.split(".").str[1].fillna("").str.len()
    for label, cols in (("decimal_digits(AI0)", D.SENSORS[:1]), ("decimal_digits(3 sensors)", D.SENSORS)):
        X = pd.DataFrame({c: pd.concat([digits(text["normal"][c]), digits(text["abnormal"][c])], ignore_index=True) for c in cols})
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.3, stratify=y, random_state=0)
        alarm = MODELS["hgb"]().fit(Xtr, ytr).predict_proba(Xte)[:, 1] >= .5
        rows.append(dict(protocol="format_shortcut", features=label, model="hgb", rows_test=len(yte), **row_metrics(yte, alarm)))
    return pd.DataFrame(rows)


def split_data(normal, abnormal, sid):
    seg_all = D.segments(normal)
    _, train_end, cal_end = D.SPLITS[sid]
    parts = {"train": normal[seg_all < train_end], "cal": normal[(seg_all >= train_end) & (seg_all < cal_end)], "test": normal[seg_all >= cal_end]}
    return parts, frozen(sid)


def grouped_records(normal, abnormal):
    rows = []
    seg_a = D.segments(abnormal)
    y_a_pos, _ = D.segment_positions(seg_a)
    for sid in D.SPLITS:
        parts, v2 = split_data(normal, abnormal, sid)
        seg_cal, seg_test = D.segments(parts["cal"]), D.segments(parts["test"])
        for kind in PROTOCOL["features"]:
            Xn, Xc, Xt, Xa = (features(f, kind, v2) for f in (parts["train"], parts["cal"], parts["test"], abnormal))
            for name, make in MODELS.items():
                full = make().fit(pd.concat([Xn, Xa], ignore_index=True), np.r_[np.zeros(len(Xn)), np.ones(len(Xa))])
                thr_full = conformal_threshold(full, Xc, seg_cal)
                pn = full.predict_proba(Xt)[:, 1]
                for cv, folds in FOLDS.items():
                    pa, ta = np.full(len(abnormal), np.nan), np.full(len(abnormal), np.nan)
                    for hold in folds:
                        keep = ~np.isin(seg_a, hold)
                        m = make().fit(pd.concat([Xn, Xa[keep]], ignore_index=True), np.r_[np.zeros(len(Xn)), np.ones(keep.sum())])
                        pa[~keep] = m.predict_proba(Xa[~keep])[:, 1]
                        ta[~keep] = conformal_threshold(m, Xc, seg_cal)
                    y, p = np.r_[np.zeros(len(pn)), np.ones(len(pa))], np.r_[pn, pa]
                    grid = np.unique(np.r_[p, .5])
                    best = max(grid, key=lambda t: row_metrics(y, p >= t)["f1"])
                    for threshold, alarm_n, alarm_a in (("0.5", pn >= .5, pa >= .5), ("conformal", pn > thr_full, pa > ta),
                                                        ("oracle", pn >= best, pa >= best)):
                        alarm = np.r_[alarm_n, alarm_a]
                        first = pd.Series(np.where(alarm_a, y_a_pos, np.nan)).groupby(seg_a).min()
                        rows.append(dict(split=sid, features=kind, model=name, cv=cv, threshold=threshold,
                                         threshold_value=float(thr_full if threshold == "conformal" else (.5 if threshold == "0.5" else best)),
                                         **row_metrics(y, alarm),
                                         normal_alerted_segments=int(pd.Series(alarm_n).groupby(seg_test).max().sum()), normal_segments=int(seg_test.max() + 1),
                                         abnormal_detected_segments=int(pd.Series(alarm_a).groupby(seg_a).max().sum()), abnormal_segments=21,
                                         delay_max_s=float(first.max() * D.DT) if first.notna().any() else np.nan))
            print(f"grouped {sid} {kind}", flush=True)
    return pd.DataFrame(rows)


def injection(normal, abnormal):
    e1 = pd.read_csv(YEJUN / "analysis" / "press_supplement" / "e1_summary.csv")
    v2_rates = e1[e1.model.eq("guard_v2") & e1.alpha.eq(ALPHA) & e1["shape"].eq("step") & e1.t0.eq(10)].set_index(["split", "family", "level"]).detect_rate_2s
    grid = [("none", 0.0)] + [(fam, lv) for fam, spec in E1["families"].items() for lv in spec["levels"]]
    rows = []
    for sid in D.SPLITS:
        parts, v2 = split_data(normal, abnormal, sid)
        test_rows = np.flatnonzero(D.segments(normal) >= D.SPLITS[sid][2])
        test = D.inputs_only(parts["test"])
        seg = D.segments(test)
        pos, length = D.segment_positions(seg)
        eligible = np.unique(seg[length >= 30])
        mask = np.isin(seg, eligible) & (pos >= 10)
        seg_cal = D.segments(parts["cal"])
        fitted = {}
        for kind in PROTOCOL["features"]:
            Xn, Xc, Xa = (features(f, kind, v2) for f in (parts["train"], parts["cal"], abnormal))
            for name, make in MODELS.items():
                m = make().fit(pd.concat([Xn, Xa], ignore_index=True), np.r_[np.zeros(len(Xn)), np.ones(len(Xa))])
                fitted[kind, name] = (m, conformal_threshold(m, Xc, seg_cal))
        zs = [standard_noise(len(normal), rep) for rep in range(5)]
        for fam, lv in grid:
            reps = range(5) if fam in ("vib_noise", "cur_noise") else range(1)
            acc = {}
            for rep in reps:
                frame = inject(test, test_rows, v2, fam, lv, mask, np.ones(len(pos)), zs[rep])
                X = {kind: features(frame, kind, v2) for kind in PROTOCOL["features"]}
                for (kind, name), (m, thr) in fitted.items():
                    prob = m.predict_proba(X[kind])[:, 1]
                    for threshold, alarm in (("0.5", prob >= .5), ("conformal", prob > thr)):
                        det = record_detection(np.where(alarm, 0.0, 1.0), seg, pos, eligible, 10, ALPHA)   # 경보 행을 p=0으로 두어 E1과 같은 집계
                        acc.setdefault((kind, name, threshold), []).append((det.detected_2s.mean(), det.pre_alarm.mean()))
            for (kind, name, threshold), vals in acc.items():
                rows.append(dict(split=sid, features=kind, model=name, threshold=threshold, family=fam, level=lv, reps=len(vals), records=len(eligible),
                                 detect_rate_2s=float(np.mean([v[0] for v in vals])), pre_alarm_records_rate=float(np.mean([v[1] for v in vals])),
                                 v2_detect_rate_2s=float(v2_rates.get((sid, fam, lv), np.nan))))
            print(f"injection {sid} {fam} {lv}", flush=True)
    return pd.DataFrame(rows)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):     # 한국어 Windows(CP949) 콘솔에서 못 쓰는 기호는 바꿔 쓴다
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE)
    out = ap.parse_args(argv).out
    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    normal, abnormal, report = D.load(BASE)
    tables = {"random_rows.csv": random_rows(normal, abnormal), "grouped_records.csv": grouped_records(normal, abnormal),
              "injection.csv": injection(normal, abnormal)}
    for name, t in tables.items():
        t.to_csv(out / name, index=False)
    sup = YEJUN / "analysis" / "press_supplement"
    D.dump_json(dict(protocol=PROTOCOL["version"], input_hashes={k: v["sha256"] for k, v in report["files"].items()},
                     code_sha256={n: D.sha256_file(HERE / n) for n in ("run.py", "protocol.json")},
                     dependencies={"press_supplement/common.py": D.sha256_file(sup / "common.py"), "press_supplement/e1_summary.csv": D.sha256_file(sup / "e1_summary.csv"),
                                   "press_guard/model.py": D.sha256_file(YEJUN / "press_guard" / "model.py"),
                                   **{f"press_guard/artifacts/guard_{s}.json": D.sha256_file(YEJUN / "press_guard" / "artifacts" / f"guard_{s}.json") for s in D.SPLITS}},
                     outputs={n: D.sha256_file(out / n) for n in tables}, environment=D.environment(),
                     elapsed_s=round(time.monotonic() - start, 1)), out / "manifest.json")
    print("done", round(time.monotonic() - start, 1), "s")


if __name__ == "__main__":
    main()
