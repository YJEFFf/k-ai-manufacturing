"""워크플로우 감사용 재계산. 원본·모델·기대값을 변경하지 않고 이 폴더에 근거만 쓴다.

실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      yejun/analysis/press_workflow_audit/check_workflow.py
기존 검수의 판정은 읽지 않는다. 구간·분할·계수·순위·집계는 별도로 대조하고,
후보 점수 함수와 외부 특징/모델 적합은 명시적으로 해당 구현을 사용한다.
"""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import importlib.util
import json
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
Y = HERE.parents[1]
BASE = Y / "press_submission"
sys.path.insert(0, str(Y / "press_guard"))
from model import GuardModel, D


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def segments(frame):
    t = pd.to_datetime(frame.TimeStamp)
    return t.diff().dt.total_seconds().sub(.1).abs().gt(1e-6).cumsum().to_numpy()


def quantize(frame):
    out = frame.copy()
    out.loc[:, D.SENSORS[:2]] = np.round(out[D.SENSORS[:2]] / 1e-4) * 1e-4
    out.loc[:, D.SENSORS[2]] = np.round(out[D.SENSORS[2]] / 1.1920929) * 1.1920929
    return out


def rank_p(reference, scores):
    return np.array([(1 + np.count_nonzero(reference >= s)) / (len(reference) + 1)
                     if np.isfinite(s) else np.nan for s in scores])


def counts(normal, abnormal, seg_n, seg_a, alpha):
    an, aa = normal <= alpha, abnormal <= alpha
    tp, fp = int(aa.sum()), int(an.sum())
    fn, tn = len(aa) - tp, len(an) - fp
    first = [np.flatnonzero(aa[seg_a == s])[0] * .1 for s in np.unique(seg_a) if aa[seg_a == s].any()]
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, f1=2*tp/(2*tp+fp+fn),
                normal_notified_segments=int(sum(an[seg_n == s].any() for s in np.unique(seg_n))),
                abnormal_notified_segments=int(sum(aa[seg_a == s].any() for s in np.unique(seg_a))),
                delay_max_s=max(first) if first else None)


def main():
    fact = dict(head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Y, text=True).strip(),
                script_sha256=digest(__file__), environment=D.environment(), data={}, splits={}, fits={}, checks={})
    frames = {}
    for kind, name in D.FILES.items():
        path = BASE / D.DATA_SUBDIR / name
        frame = pd.read_csv(path); frames[kind] = frame
        seg = segments(frame)
        dates = pd.to_datetime(frame.TimeStamp).dt.date.astype(str)
        fact["data"][kind] = dict(rows=len(frame), segments=len(np.unique(seg)), sha256=digest(path),
                                  dates=dates.unique().tolist(), labels=frame.Equipment_state.value_counts().to_dict(),
                                  recorded_seconds=len(frame)*.1,
                                  date_label_counts=pd.crosstab(dates, frame.Equipment_state).to_dict())
        assert digest(path) == D.EXPECTED_SHA256[kind]
        assert np.array_equal(seg, D.segments(frame))
    normal, abnormal = frames["normal"], frames["abnormal"]
    sn, sa = segments(normal), segments(abnormal)
    assert (len(np.unique(sn)), len(np.unique(sa))) == (600, 21)
    fact["checks"]["raw_hashes_and_independent_boundaries"] = True
    fact["overlap"] = dict(normal_test_A_and_B_segments=len(set(sn[sn >= 480]) & set(sn[sn >= 420])),
                           abnormal_A_and_B_segments=len(set(sa)),
                           note="같은 기록의 재사용. 독립 반복 두 건으로 합산 불가")
    recorded = pd.read_csv(Y / "press_guard/outputs/metrics.csv")
    metrics, early_rows, condition_definitions = [], [], []
    early = module("workflow_early", Y / "analysis/press_early/run_experiment.py")
    for sid, (end_tr, end_ca) in {"A": (360, 480), "B": (300, 420)}.items():
        parts = {"train": normal[sn < end_tr].reset_index(drop=True),
                 "cal": normal[(sn >= end_tr) & (sn < end_ca)].reset_index(drop=True),
                 "test": normal[sn >= end_ca].reset_index(drop=True)}
        fact["splits"][sid] = {k: dict(rows=len(f), segments=len(np.unique(segments(f)))) for k, f in parts.items()}
        for subset, frame in (("normal", parts["test"]), ("abnormal", abnormal)):
            features = []
            for _, g in frame.groupby(segments(frame)):
                cur_g = g[D.SENSORS[2]].to_numpy(float)
                features.append(dict(length=len(g), amp_proxy=float(np.sqrt(2*np.mean((cur_g-cur_g.mean())**2))),
                                     vib_std=float(np.sqrt(g[D.SENSORS[:2]].var(ddof=1).sum())) if len(g)>1 else np.nan))
            ft = pd.DataFrame(features)
            for feature in ("amp_proxy", "vib_std"):
                q = np.nanpercentile(ft[feature], [25, 50, 75])
                condition_definitions.append(dict(split=sid, subset=subset, feature=feature,
                    q25=q[0], q50=q[1], q75=q[2], segments=len(ft),
                    segments_length_under17=int(ft.length.lt(17).sum()), rows_length_under17=int(ft[ft.length.lt(17)].length.sum())))
        m = GuardModel.load(Y / "press_guard/artifacts" / f"guard_{sid}.json")
        tr = quantize(parts["train"]); x = tr[D.SENSORS].to_numpy(float)
        sg = segments(tr); pos = pd.Series(np.ones(len(tr), dtype=int)).groupby(sg).cumcount().to_numpy()
        idx = np.flatnonzero(pos >= 2); cur = x[:, 2]
        coef = np.linalg.lstsq(np.column_stack([np.ones(len(idx)), cur[idx-1], cur[idx-2]]), cur[idx], rcond=None)[0]
        np.testing.assert_allclose(m.mean, x.mean(axis=0), atol=1e-12, rtol=0)
        np.testing.assert_allclose(m.scale, x.std(axis=0), atol=1e-12, rtol=0)
        np.testing.assert_allclose(m.coef, coef, atol=1e-12, rtol=0)
        pc = m.predict(parts["cal"])
        cal = pc.groupby("record_id").score.max().to_numpy()
        np.testing.assert_allclose(cal, m.cal, atol=1e-12, rtol=0)
        fact["fits"][sid] = dict(mean_max_difference=float(abs(m.mean-x.mean(axis=0)).max()),
                                 scale_max_difference=float(abs(m.scale-x.std(axis=0)).max()),
                                 ar2_max_difference=float(abs(m.coef-coef).max()),
                                 calibration_max_difference=float(abs(cal-m.cal).max()), n_cal=len(cal), min_p=1/(len(cal)+1))
        for alpha in (.01, .03, .05):
            pn, pa = m.predict(parts["test"], alpha), m.predict(abnormal, alpha)
            pv_n, pv_a = rank_p(cal, pn.score), rank_p(cal, pa.score)
            np.testing.assert_allclose(pv_n, pn.p_value, atol=0, rtol=0)
            np.testing.assert_allclose(pv_a, pa.p_value, atol=0, rtol=0)
            row = dict(split=sid, alpha=alpha, **counts(pv_n, pv_a, segments(parts["test"]), sa, alpha))
            saved = recorded[recorded.split.eq(sid) & recorded.model.eq("guard_v2") & recorded.alpha.eq(alpha)].iloc[0]
            for key in row.keys() - {"split", "alpha"}:
                assert abs(row[key] - saved[key]) < 1e-12, (sid, alpha, key)
            metrics.append(row)
        # 최신 후보의 위치 0/1을 직접 집계한다. 점수는 후보 구현, 순위·혼동행렬은 위의 별도 구현.
        base = early.Scorer(tr, sg, D.load_vendor(), wins=(6, 8), baselines=False)
        ar2, ar1 = early.Linear(tr, sg, 2), early.Linear(tr, sg, 1)
        joint = early.Joint(base.scaler, tr)
        cal_frame, test_frame, ab_frame = quantize(parts["cal"]), quantize(parts["test"]), quantize(abnormal)
        cal_seg, test_seg = segments(cal_frame), segments(test_frame)
        sc = early.scores(base, ar2, joint, ar1, cal_frame, cal_seg)
        st = early.scores(base, ar2, joint, ar1, test_frame, test_seg)
        ab = early.scores(base, ar2, joint, ar1, ab_frame, sa)
        positions = pd.Series(np.ones(len(abnormal), dtype=int)).groupby(sa).cumcount().to_numpy()
        expected = pd.read_csv(Y / "analysis/press_early/primary.csv")
        for name in sc:
            ref = pd.Series(sc[name]).groupby(cal_seg).max().fillna(-np.inf).to_numpy()
            pn, pa = rank_p(ref, st[name]), rank_p(ref, ab[name])
            c = counts(pn, pa, test_seg, sa, .01)
            e = expected[expected.split_id.eq(sid) & expected.model.eq(name)].iloc[0]
            for key in ("tp", "fp", "fn", "normal_notified_segments", "abnormal_notified_segments"):
                assert c[key] == e[key], (sid, name, key)
            miss = ~np.isfinite(pa) | (pa > .01)
            early_rows.append(dict(split=sid, model=name, **c, fn_pos0=int(miss[positions == 0].sum()),
                                   fn_pos1=int(miss[positions == 1].sum()), fn_pos2plus=int(miss[positions >= 2].sum())))
    fact["checks"].update(normal_only_fit_state_matches=True, all_six_v2_operating_points_recounted=True,
                           early_primary_twelve_rows_recounted=True)
    pd.DataFrame(metrics).to_csv(HERE / "v2_recount.csv", index=False)
    pd.DataFrame(early_rows).to_csv(HERE / "early_position_recount.csv", index=False)
    pd.DataFrame(condition_definitions).to_csv(HERE / "condition_definition_audit.csv", index=False)
    fact["candidate_tables"] = {}
    for sub, name in (("press_improvement", "candidate_metrics.csv"), ("press_advance", "metrics.csv"), ("press_early", "metrics.csv")):
        table = pd.read_csv(Y / "analysis" / sub / name)
        fact["candidate_tables"][sub] = dict(rows=len(table), criteria=table.criterion.value_counts().to_dict(), models=table.model.nunique())
    cond = pd.read_csv(Y / "press_guard/outputs/error_conditions_v2.csv")
    fact["v2_error_schema"] = dict(columns=cond.columns.tolist(), conditions=cond.condition.unique().tolist())
    for key, group in cond.groupby(["split_id", "model", "alpha", "subset", "condition"]):
        expected_n = 600 if key[3] == "abnormal" else fact["splits"][key[0]]["test"]["rows"]
        assert group.rows.sum() == expected_n, key
    fact["checks"]["v2_condition_row_denominators"] = True
    # audit.py의 검사식을 미탐 1구간인 합법적인 결과에 적용하는 반례.
    specimen = pd.DataFrame({"record_id": [0, 0, 1, 1], "alarm": [1, 1, 0, 0], "notification": [1, 0, 0, 0]})
    fact["notification_gate_probe"] = dict(current_all_records_have_one=bool(specimen.groupby("record_id").notification.sum().eq(1).all()),
        one_if_and_only_if_alarm=bool(specimen.groupby("record_id").notification.sum().eq(specimen.groupby("record_id").alarm.max()).all()),
        meaning="미탐 구간의 알림0은 정상 동작인데 현재 audit 식은 실패한다. 현재 21/21 수치에는 영향 없음")
    external = Y / "analysis/press_external"
    archive = external / "data/hydraulic.zip"
    acquisition = json.loads((external / "acquisition.json").read_text())
    em = json.loads((external / "manifest.json").read_text())
    assert digest(archive) == acquisition["sha256"] == em["input_sha256"]
    sys.path.insert(0, str(external))
    ex = module("workflow_external", external / "evaluate.py")
    x, profile = ex.features(archive)
    stored = pd.read_csv(external / "metrics.csv")
    partitions = pd.read_csv(external / "partitions.csv")
    ext_rows = []
    for (mode, cooler), g in partitions.groupby(["mode", "cooler"]):
        ids = {p: g[g.partition.eq(p)].cycle_id.to_numpy(int) for p in ("train", "cal", "test")}
        assert not (set(ids["train"]) & set(ids["cal"]) or set(ids["train"]) & set(ids["test"]) or set(ids["cal"]) & set(ids["test"]))
        assert profile.pump.iloc[ids["train"]].eq(0).all() and profile.pump.iloc[ids["cal"]].eq(0).all()
        scores = ex.fit_scores(x, ids["train"])
        leak = profile.pump.iloc[ids["test"]].to_numpy() != 0
        for name, score in scores.items():
            pv = rank_p(score[ids["cal"]], score[ids["test"]]); alarm = pv <= .05
            tp, fp = int((alarm & leak).sum()), int((alarm & ~leak).sum())
            fn, tn = int((~alarm & leak).sum()), int((~alarm & ~leak).sum())
            e = stored[stored['mode'].eq(mode) & stored.cooler.eq(cooler) & stored.model.eq(name)].iloc[0]
            assert (tp, fp, fn, tn) == (e.tp, e.fp, e.fn, e.tn)
            ext_rows.append(dict(mode=mode, cooler=int(cooler), model=name, tp=tp, fp=fp, fn=fn, tn=tn))
    fact["external"] = dict(sha256=digest(archive), cycles=len(profile), stable=int(profile.unstable.eq(0).sum()),
                              recalculated_operating_points=len(ext_rows), note="대회 GuardModel과 별개인 외부 모델 3종")
    fact["checks"]["external_eighteen_operating_points_and_disjoint_partitions"] = True
    pd.DataFrame(ext_rows).to_csv(HERE / "external_recount.csv", index=False)
    D.dump_json(fact, HERE / "facts.json")
    print(json.dumps(dict(checks=fact["checks"], fits=fact["fits"], tables=fact["candidate_tables"], external=fact["external"]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
