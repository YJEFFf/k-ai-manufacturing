"""라벨 지도학습 기준선 — 흔한 평가(무작위 행 분할)와 엄격한 평가(이상 기록 묶음 교차검증·고장 주입)를 나란히 본다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/analysis/press_supervised/run.py   # 약 2분

최종모델 v2(이상 라벨 미사용)의 선정근거를 보강하는 비교이며 대회 보고서가 아니다. 설계는 protocol.json.
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
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
sys.path.insert(0, str(YEJUN / "analysis" / "press_supplement"))
from common import D, BASE, split_rows, frozen, inject, standard_noise, record_detection, E1  # noqa: E402

PROTOCOL = json.loads((HERE / "protocol.json").read_text())
MODELS = {"logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)),
          "hgb": lambda: HistGradientBoostingClassifier(random_state=0)}
FOLDS = (np.arange(0, 7), np.arange(7, 14), np.arange(14, 21))


def features(frame, quant="matched"):
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


def row_metrics(y, alarm):
    tp, fp = int((alarm & (y == 1)).sum()), int((alarm & (y == 0)).sum())
    fn = int((~alarm & (y == 1)).sum())
    return dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0,
                precision=tp / (tp + fp) if tp + fp else 0.0, recall=tp / (tp + fn))


def random_rows(normal, abnormal):
    rows = []
    y = np.r_[np.zeros(len(normal)), np.ones(len(abnormal))]
    for quant in ("raw", "matched"):
        X = pd.concat([features(normal, quant), features(abnormal, quant)], ignore_index=True)
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.3, stratify=y, random_state=0)
        for name, make in MODELS.items():
            alarm = make().fit(Xtr, ytr).predict_proba(Xte)[:, 1] >= .5
            rows.append(dict(protocol="random_rows", features=f"창 특징({quant})", model=name, rows_test=len(yte), **row_metrics(yte, alarm)))
    text = {k: pd.read_csv(D.data_dir(BASE) / D.FILES[k], dtype=str, keep_default_na=False) for k in D.FILES}
    digits = lambda s: s.str.strip().str.lstrip("-").str.split(".").str[1].fillna("").str.len()
    for label, cols in (("소수 자릿수(AI0 하나)", D.SENSORS[:1]), ("소수 자릿수(세 센서)", D.SENSORS)):
        X = pd.DataFrame({c: pd.concat([digits(text["normal"][c]), digits(text["abnormal"][c])], ignore_index=True) for c in cols})
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=.3, stratify=y, random_state=0)
        alarm = MODELS["hgb"]().fit(Xtr, ytr).predict_proba(Xte)[:, 1] >= .5
        rows.append(dict(protocol="format_shortcut", features=label, model="hgb", rows_test=len(yte), **row_metrics(yte, alarm)))
    return pd.DataFrame(rows)


def grouped_records(normal, abnormal):
    rows, seg_all = [], D.segments(normal)
    Xa, seg_a = features(abnormal), D.segments(abnormal)
    for sid in D.SPLITS:
        _, _, cal_end = D.SPLITS[sid]
        train, test = normal[seg_all < cal_end], normal[seg_all >= cal_end]
        Xn, Xt, seg_t = features(train), features(test), D.segments(test)
        for name, make in MODELS.items():
            pa, pn = np.full(len(abnormal), np.nan), []
            for hold in FOLDS:
                keep = ~np.isin(seg_a, hold)
                m = make().fit(pd.concat([Xn, Xa[keep]], ignore_index=True), np.r_[np.zeros(len(Xn)), np.ones(keep.sum())])
                pa[~keep] = m.predict_proba(Xa[~keep])[:, 1]
                pn.append(m.predict_proba(Xt)[:, 1])
            pn = np.mean(pn, axis=0)
            y, p = np.r_[np.zeros(len(pn)), np.ones(len(pa))], np.r_[pn, pa]
            grid = np.unique(np.r_[p, .5])
            best = max(grid, key=lambda t: row_metrics(y, p >= t)["f1"])
            for kind, t in (("0.5", .5), ("사후 최적(평가 라벨 사용)", best)):
                alarm = p >= t
                normal_alert = pd.Series(alarm[:len(pn)]).groupby(seg_t).max()
                abnormal_detect = pd.Series(alarm[len(pn):]).groupby(seg_a).max()
                first = pd.Series(np.where(alarm[len(pn):], D.segment_positions(seg_a)[0], np.nan)).groupby(seg_a).min()
                rows.append(dict(protocol="grouped_records", split=sid, model=name, threshold=kind, threshold_value=float(t),
                                 **row_metrics(y, alarm), normal_alerted_segments=int(normal_alert.sum()), normal_segments=len(normal_alert),
                                 abnormal_detected_segments=int(abnormal_detect.sum()), abnormal_segments=len(abnormal_detect),
                                 delay_max_s=float(first.max() * D.DT) if first.notna().any() else np.nan))
    return pd.DataFrame(rows)


def injection(normal, abnormal):
    rows_ = split_rows(normal, "A")
    train = normal.iloc[np.r_[rows_["train"], rows_["cal"]]]
    Xn, Xa = features(train), features(abnormal)
    models = {name: make().fit(pd.concat([Xn, Xa], ignore_index=True), np.r_[np.zeros(len(Xn)), np.ones(len(Xa))]) for name, make in MODELS.items()}
    test = D.inputs_only(normal.iloc[rows_["test"]])
    seg = D.segments(test)
    pos, length = D.segment_positions(seg)
    eligible = np.unique(seg[length >= 30])
    mask = np.isin(seg, eligible) & (pos >= 10)
    ref, z = frozen("A"), standard_noise(len(normal), 0)
    grid = [("none", 0.0)] + [(fam, lv) for fam, spec in E1["families"].items() for lv in spec["levels"]]
    rows = []
    for fam, lv in grid:
        frame = inject(test, rows_["test"], ref, fam, lv, mask, np.ones(len(pos)), z)
        X = features(frame)
        for name, m in models.items():
            pv = np.where(m.predict_proba(X)[:, 1] >= .5, 0.0, 1.0)   # 경보 행을 p=0으로 표시해 E1과 같은 탐지 집계를 쓴다
            det = record_detection(pv, seg, pos, eligible, 10, .01)
            rows.append(dict(family=fam, level=lv, model=name, records=len(det), detect_rate_2s=float(det.detected_2s.mean()),
                             pre_alarm_records=int(det.pre_alarm.sum())))
    t = pd.DataFrame(rows)
    e1 = pd.read_csv(YEJUN / "analysis" / "press_supplement" / "e1_summary.csv")
    v2 = e1[e1.split.eq("A") & e1.model.eq("guard_v2") & e1.alpha.eq(.01) & e1["shape"].eq("step") & e1.t0.eq(10)]
    v2 = v2.set_index(["family", "level"]).detect_rate_2s
    t["v2_detect_rate_2s"] = [float(v2.get((f, l), np.nan)) for f, l in zip(t.family, t.level)]
    return t


def main(argv=None):
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
    D.dump_json(dict(protocol=PROTOCOL["version"], input_hashes={k: v["sha256"] for k, v in report["files"].items()},
                     code_sha256={n: D.sha256_file(HERE / n) for n in ("run.py", "protocol.json")},
                     dependencies={"press_supplement/common.py": D.sha256_file(YEJUN / "analysis" / "press_supplement" / "common.py"),
                                   "press_supplement/e1_summary.csv": D.sha256_file(YEJUN / "analysis" / "press_supplement" / "e1_summary.csv"),
                                   "press_guard/artifacts/guard_A.json": D.sha256_file(YEJUN / "press_guard" / "artifacts" / "guard_A.json")},
                     outputs={n: D.sha256_file(out / n) for n in tables}, environment=D.environment(),
                     elapsed_s=round(time.monotonic() - start, 1)), out / "manifest.json")
    for name, t in tables.items():
        print(name); print(t.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
