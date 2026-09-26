"""E1 고장 주입 — 동결 v2(와 v1 기준선)가 시작 시각을 아는 인공 이상을 몇 초 만에·어느 세기부터 잡는가.

같은 날·같은 시간대 정상 평가 기록에 주입하므로 날짜 교락이 없다. 인공 신호이며 실제 고장 물리가 아니다.
"""
import argparse
import time

from common import *  # noqa: F403
import contract


def run_split(sid, normal, zs):
    model = frozen(sid)
    rows = split_rows(normal, sid)
    test = D.inputs_only(normal.iloc[rows["test"]])
    cal = D.inputs_only(normal.iloc[rows["cal"]])
    seg = D.segments(test)
    pos, length = D.segment_positions(seg)
    p_clean, _ = v2_pvalues(model, test)
    p1_clean = v1_pvalues(model, cal, test)
    configs = [("none", 0.0, "step", 10), ("none", 0.0, "step", 0)]
    for fam, spec in E1["families"].items():
        for lv in spec["levels"]:
            configs.append((fam, lv, "step", 10))
            configs.append((fam, lv, "step", 0))
            if fam in ("vib_noise", "cur_noise"):
                configs.append((fam, lv, "ramp", 10))
    summary, records = [], []
    for fam, lv, shape, t0 in configs:
        eligible = np.unique(seg[length >= (30 if t0 == 10 else 20)])
        mask = np.isin(seg, eligible) & (pos >= t0)
        ramp = np.minimum(1.0, (pos - t0 + 1) / POST_WINDOW) if shape == "ramp" else np.ones(len(pos))
        reps = range(5) if fam in ("vib_noise", "cur_noise") else range(1)
        for rep in reps:
            frame = inject(test, rows["test"], model, fam, lv, mask, ramp, zs[rep])
            p2, pred = v2_pvalues(model, frame)
            p1 = v1_pvalues(model, cal, frame)
            # 인과성: 주입 전 행의 p값은 원본과 같아야 한다
            before = ~mask
            assert np.allclose(np.nan_to_num(p2[before], nan=-1), np.nan_to_num(p_clean[before], nan=-1))
            assert np.allclose(np.nan_to_num(p1[before], nan=-1), np.nan_to_num(p1_clean[before], nan=-1))
            for name, p in (("guard_v2", p2), ("baseline_v1", p1)):
                for alpha in ALPHAS:
                    det = record_detection(p, seg, pos, eligible, t0, alpha)
                    if name == "guard_v2" and alpha == .01:
                        first_rows = [np.flatnonzero((seg == r.record) & (pos == r.first_post))[0] for r in det.itertuples() if pd.notna(r.first_post)]
                        reasons = pred.reason.to_numpy()[first_rows]
                        det["first_reason"] = None
                        det.loc[det.first_post.notna(), "first_reason"] = reasons
                    records.append(det.assign(split=sid, family=fam, level=lv, shape=shape, t0=t0, rep=rep, model=name, alpha=alpha))
        print(f"{sid} {fam} {lv} {shape} t0={t0}", flush=True)
    return pd.concat(records, ignore_index=True)


def summarize(rec):
    keys = ["split", "family", "level", "shape", "t0", "model", "alpha"]
    out = []
    for key, g in rec.groupby(keys, sort=False):
        det = g[g.first_post.notna()]
        row = dict(zip(keys, key), records=g.record.nunique(), trials=len(g),
                   detect_rate_2s=g.detected_2s.mean(), detect_rate_any=g.first_post.notna().mean(),
                   delay_median_s=det.delay_s.median() if len(det) else np.nan,
                   delay_p90_s=det.delay_s.quantile(.9) if len(det) else np.nan,
                   post_row_recall=g.post_alarm_rows.sum() / g.post_rows.sum(),
                   pre_alarm_records=int(g[g.rep.eq(0)].pre_alarm.sum()))
        if "first_reason" in g and g.first_reason.notna().any():
            for reason, n in g.first_reason.dropna().str.split("+").explode().value_counts().items():
                row[f"first_reason_{reason}"] = int(n)
        out.append(row)
    return pd.DataFrame(out)


def detection_floor(summary):
    """족별로 두 분할 모두 탐지율 ≥ 90%(α=1%, 계단형, t0=10)인 가장 약한 세기."""
    rows = []
    s = summary[summary.alpha.eq(.01) & summary["shape"].eq("step") & summary.t0.eq(10) & summary.family.ne("none")]
    for (fam, model), g in s.groupby(["family", "model"]):
        ok = g.groupby("level").detect_rate_2s.min()
        levels = E1["families"][fam]["levels"]
        if fam == "cur_gain":
            # 1 아래/위 방향을 따로 본다: 1에 가까울수록 약하다
            for side, lv in (("down", [l for l in levels if l < 1][::-1]), ("up", [l for l in levels if l > 1])):
                hit = [l for l in lv if ok.get(l, 0) >= .9]
                rows.append(dict(family=f"{fam}_{side}", model=model, floor=hit[0] if hit else None,
                                 min_rate_at_floor=ok.get(hit[0]) if hit else None))
        else:
            hit = [l for l in levels if ok.get(l, 0) >= .9]
            rows.append(dict(family=fam, model=model, floor=hit[0] if hit else None,
                             min_rate_at_floor=ok.get(hit[0]) if hit else None))
    return pd.DataFrame(rows)


def reference(normal, abnormal):
    """관측 이상 21구간과 정상 평가 구간을 주입 세기 축에 놓기 위한 기술 통계(모델 적합에 쓰지 않음)."""
    model = frozen("A")
    rows = []
    for name, frame in (("abnormal", abnormal), ("normal_test_A", normal.iloc[split_rows(normal, "A")["test"]])):
        x = D.quantize(D.inputs_only(frame), "matched")
        seg = D.segments(x)
        res = x[D.SENSORS[2]].to_numpy() - model.coef[0] - model.coef[1] * x[D.SENSORS[2]].shift(1).to_numpy() - model.coef[2] * x[D.SENSORS[2]].shift(2).to_numpy()
        pos, _ = D.segment_positions(seg)
        res[pos < 2] = np.nan
        g = pd.DataFrame(dict(seg=seg, v0=x[D.SENSORS[0]], v1=x[D.SENSORS[1]], c=x[D.SENSORS[2]], r=res)).groupby("seg")
        t = pd.DataFrame(dict(n=g.size(), vib0_std_ratio=g.v0.std() / model.scale[0], vib1_std_ratio=g.v1.std() / model.scale[1],
                              cur_mean_over_A=(g.c.mean() - model.mean[2]) / (np.sqrt(2) * model.scale[2]),
                              ar_resid_std=g.r.std()))
        rows.append(t.assign(source=name))
    out = pd.concat(rows).reset_index()
    ref_std = out[out.source.eq("normal_test_A")].ar_resid_std.median()
    out["ar_resid_std_over_normal_median"] = out.ar_resid_std / ref_std
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE, help="산출물 폴더(재현 검사는 임시 폴더를 쓴다)")
    OUT = ap.parse_args(argv).out
    OUT.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    normal, abnormal, hashes = load_data()
    zs = [standard_noise(len(normal), rep) for rep in range(5)]
    rec = pd.concat([run_split(sid, normal, zs) for sid in D.SPLITS], ignore_index=True)
    summary = summarize(rec)
    rec.to_csv(OUT / "predictions_e1_records.csv", index=False)   # Git 제외(기록×조건 단위, .gitignore predictions*)
    summary.to_csv(OUT / "e1_summary.csv", index=False)
    floor = detection_floor(summary)
    floor.to_csv(OUT / "e1_detection_floor.csv", index=False)
    ref = reference(normal, abnormal)
    ref.to_csv(OUT / "e1_reference_segments.csv", index=False)
    contract.write_manifest("E1", OUT, start, config=dict(noise_seeds=[20260926 + r for r in range(5)], repetitions=5, onset=[10, 0],
                                                         post_window_rows=POST_WINDOW, alphas=list(ALPHAS)))
    print(floor.to_string(index=False))


if __name__ == "__main__":
    main()
