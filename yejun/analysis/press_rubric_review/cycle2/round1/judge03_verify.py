"""평가관 03 2차 검수(영향요인·오류분석, 15점) — 원본·동결 v2·커밋 산출물로 직접 다시 계산한다.

    cd yejun
    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
        analysis/press_rubric_review/cycle2/round1/judge03_verify.py > analysis/press_rubric_review/cycle2/round1/judge03_verify.log

읽기 전용 검수. 쓰기는 이 폴더의 judge03_verify.json 하나다. 모델·문턱·분할·기존 산출물은 바꾸지 않는다.
센서 절제·채널 교체·오경보 풀링은 "지적한 결함을 기존 자료만으로 고칠 수 있는지"를 확인하는 검수용 사후 계산이며
성능 근거나 대회 수치가 아니다. 이미 본 이상 21구간을 재사용한다.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
GUARD = YEJUN / "press_guard"
OUT = GUARD / "outputs"
sys.path.insert(0, str(GUARD))
from model import GuardModel, D, ALPHAS, layout  # noqa: E402
from press.calibrate import conformal_p, segment_max  # noqa: E402
from press.scores import ExpTail  # noqa: E402
import analyze as AN  # noqa: E402  조건 경계·구간 특징 정의를 그대로 재사용

T0 = time.monotonic()
SENSOR_SHORT = ("AI0", "AI1", "AI2")


def log(*a):
    print(f"[{time.monotonic() - T0:6.1f}s]", *a, flush=True)


def cp95(k, n):
    """Clopper–Pearson 양측 95%."""
    lo = 0.0 if k == 0 else float(stats.beta.ppf(.025, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(.975, k + 1, n - k))
    return [round(lo, 4), round(hi, 4)]


def fisher_greater(err_in, n_in, err_out, n_out):
    """조건 안의 오류 비율이 조건 밖보다 큰가(단측 Fisher)."""
    return float(stats.fisher_exact([[err_in, n_in - err_in], [err_out, n_out - err_out]], alternative="greater")[1])


def seg_features(model, train, test, abn):
    q = {k: D.quantize(D.inputs_only(f), "matched") for k, f in (("train", train), ("test", test), ("abn", abn))}
    ft = {k: AN.segment_feature_table(v, D.segments(v), model.mean, model.scale) for k, v in q.items()}
    bounds = AN.condition_bounds(ft["train"])
    for f in ft.values():
        f["vib_high"] = f.vibz_max > bounds["vib_high"]
        f["wave"] = AN._wave(f, bounds)
        f["vib_q"] = AN._quartile(f.vib_std, bounds["vib"])
        f["amp_q"] = AN._quartile(f.amp_proxy, bounds["amp"])
    return ft, bounds


def fp_segments(pn, feats, abs_offset, seg_times, alpha, tag):
    """정상 평가에서 경보가 난 구간과 그 조건."""
    rows = []
    f = feats.set_index("record_id")
    for rid, g in pn.groupby("record_id"):
        a = g[g.alarm.eq(1)]
        if not len(a):
            continue
        abs_seg = int(abs_offset + rid)
        rows.append(dict(tag=tag, alpha=alpha, record_id=int(rid), abs_segment=abs_seg, block=f"{abs_seg // 60 * 60}~{abs_seg // 60 * 60 + 59}",
                         start=str(seg_times[abs_seg]), length=int(len(g)), alarm_rows=int(len(a)), alarm_positions=a.position.astype(int).tolist(),
                         reasons=sorted(set("+".join(a.reason).split("+")) - {""}),
                         magnitude_sensors=sorted(set(a[a.reason.str.contains("magnitude")].magnitude_sensor)) if "magnitude_sensor" in a else [],
                         vib_high=bool(f.loc[rid, "vib_high"]), wave=str(f.loc[rid, "wave"]), vib_q=str(f.loc[rid, "vib_q"]),
                         amp_q=str(f.loc[rid, "amp_q"]), vibz_max=round(float(f.loc[rid, "vibz_max"]), 3)))
    return rows


# ---------------------------------------------------------------- 센서 절제(재보정)
def ablate(model, split, abnormal, sensors, shape, dynamics):
    """크기 성분에 쓰는 센서 부분집합과 전류 성분 사용 여부를 바꾸고, 크기 꼬리는 정상 학습에서 다시 적합, 문턱은 정상 보정에서 다시 보정."""
    def prep(frame):
        q = D.quantize(D.inputs_only(frame), "matched")
        return q, layout(q)[1]
    (tq, ts), (cq, cs), (nq, ns) = (prep(split[k]) for k in ("train", "cal", "test"))
    aq, as_ = prep(abnormal)
    tail = None
    if sensors:
        ztr = (tq[D.SENSORS].to_numpy(float) - model.mean) / model.scale
        tail = ExpTail(np.abs(ztr[:, sensors]).max(1))

    def score(q, s):
        comp = model.components(q, s)
        parts = []
        if sensors:
            z = (q[D.SENSORS].to_numpy(float) - model.mean) / model.scale
            parts.append(tail(np.abs(z[:, sensors]).max(1)))
        if shape:
            parts.append(comp["g_waveform"])
        if dynamics:
            parts.append(comp["g_dynamics"])
        out = parts[0]
        for p in parts[1:]:
            out = np.fmax(out, p)
        return out
    cal = segment_max(score(cq, cs), cs)
    result = {}
    for alpha in ALPHAS:
        pn, pa = conformal_p(cal, score(nq, ns)), conformal_p(cal, score(aq, as_))
        an, aa = np.isfinite(pn) & (pn <= alpha), np.isfinite(pa) & (pa <= alpha)
        tp, fp = int(aa.sum()), int(an.sum())
        fn = len(aa) - tp
        result[str(alpha)] = dict(tp=tp, fp=fp, fn=fn, f1=round(2 * tp / (2 * tp + fp + fn), 6),
                                  normal_alert_segments=int(pd.Series(an).groupby(ns).max().sum()),
                                  abnormal_detected_segments=int(pd.Series(aa).groupby(as_).max().sum()))
    return result


# ---------------------------------------------------------------- 채널 교체(시간 구조를 보존하는 순열 중요도)
def channel_swap(model, test, abnormal, channels, reps, seed):
    """이상 기록마다, 같은 분할 정상 평가 기록(길이 ≥ L) 하나를 무작위로 골라 앞 L행의 지정 채널을 옮겨 넣는다."""
    rng = np.random.default_rng(seed)
    test = test.reset_index(drop=True)
    tseg = D.segments(test)
    tlen = pd.Series(tseg).value_counts()
    abn = abnormal.reset_index(drop=True)
    aseg = D.segments(abn)
    cols = [D.SENSORS[c] for c in channels]
    out = []
    for _ in range(reps):
        mod = abn.copy()
        for rec in np.unique(aseg):
            rows = np.flatnonzero(aseg == rec)
            donors = tlen[tlen >= len(rows)].index.to_numpy()
            d = rng.choice(donors)
            drows = np.flatnonzero(tseg == d)[:len(rows)]
            for c in cols:
                mod.loc[rows, c] = test.loc[drows, c].to_numpy()
        p = model.predict(mod, .01)
        out.append(dict(fn=int((p.alarm == 0).sum()), detected=int(p.groupby("record_id").alarm.max().sum())))
    fn = np.array([o["fn"] for o in out]); det = np.array([o["detected"] for o in out])
    return dict(channels="+".join(SENSOR_SHORT[c] for c in channels), reps=reps, fn_mean=round(float(fn.mean()), 1),
                fn_min=int(fn.min()), fn_max=int(fn.max()), detected_mean=round(float(det.mean()), 2), detected_min=int(det.min()))


def main():
    res = dict(base="HEAD dcd300a(검수 시작 f6ec6b8; 검수 대상 파일은 두 커밋에서 같음) 산출물 + 원본 재계산", splits={})
    normal, abnormal, report = D.load()
    res["input_sha256"] = {k: v["sha256"] for k, v in report["files"].items()}
    seg_all = D.segments(normal)
    seg_times = pd.to_datetime(normal[D.TIME]).groupby(seg_all).min().dt.strftime("%H:%M:%S").to_dict()
    metrics = pd.read_csv(OUT / "metrics.csv")
    errors = pd.read_csv(OUT / "error_conditions_v2.csv")
    segerr = pd.read_csv(OUT / "error_conditions_segments_v2.csv")
    comparison = pd.read_csv(OUT / "model_comparison_v2.csv")
    ablation_saved = pd.read_csv(OUT / "ablation_v2.csv")

    # ---- 산출물 사이의 사실: 크기 성분에서 전류(AI2)는 한 번도 결정적이지 않다(maxz_vib2 = maxz_3)
    main = comparison[comparison.calibration_unit.eq("recording_segments") & comparison.criterion.eq("conformal")]
    same = []
    for sid in D.SPLITS:
        for alpha in ALPHAS:
            a = main[main.split_id.eq(sid) & main.alpha.eq(alpha) & main.model.eq("maxz_vib2")].iloc[0]
            b = main[main.split_id.eq(sid) & main.alpha.eq(alpha) & main.model.eq("maxz_3")].iloc[0]
            same.append(all(a[k] == b[k] for k in ("tp", "fp", "fn", "normal_notified_segments", "abnormal_notified_segments")))
    res["maxz_vib2_equals_maxz_3_all_alpha"] = bool(all(same))

    pooled_fp = []
    for sid in D.SPLITS:
        log(sid, "시작")
        r = {}
        model = GuardModel.load(GUARD / "artifacts" / f"guard_{sid}.json")
        split = D.split_normal(normal, seg_all, sid)
        _, train_end, cal_end = D.SPLITS[sid]
        preds = {a: (model.predict(split["test"], a), model.predict(abnormal, a)) for a in ALPHAS}

        # 1) 새 추론 재집계와 저장 표 일치
        recount = {}
        for alpha, (pn, pa) in preds.items():
            got = dict(tp=int(pa.alarm.sum()), fp=int(pn.alarm.sum()), fn=int((pa.alarm == 0).sum()),
                       normal_notified_segments=int(pn.groupby("record_id").alarm.max().sum()),
                       abnormal_notified_segments=int(pa.groupby("record_id").alarm.max().sum()))
            saved = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(alpha)].iloc[0]
            got["matches_metrics_csv"] = all(int(saved[k]) == v for k, v in got.items() if k != "matches_metrics_csv")
            for subset, p, kind in (("normal", pn, "fp"), ("abnormal", pa, "fn")):
                t = errors[errors.split_id.eq(sid) & errors.model.eq("v2") & errors.alpha.eq(alpha) & errors.subset.eq(subset)]
                got[f"row_table_sums_ok_{subset}"] = bool(all(g.rows.sum() == len(p) and g.error_rows.sum() == got[kind] for _, g in t.groupby("condition")))
            recount[str(alpha)] = got
        r["recount"] = recount
        assert all(v["matches_metrics_csv"] for v in recount.values())
        assert int(pd.Series(preds[.01][0].record_id).nunique()) == len(np.unique(seg_all[seg_all >= cal_end]))

        ft, bounds = seg_features(model, split["train"], split["test"], abnormal)
        r["bounds"] = {k: (list(np.round(v, 4)) if isinstance(v, tuple) else round(v, 4)) for k, v in bounds.items()}

        # 2) 미탐(행): 위치 × 진동 수준 상호작용, 위치를 통제한 진동 효과
        pn, pa = preds[.01]
        pa = pa.merge(ft["abn"][["record_id", "vib_high", "vib_q", "wave", "length"]], on="record_id")
        pa["pos_grp"] = np.select([pa.position.le(1), pa.position.le(6)], ["0-1", "2-6"], "7+")
        pa["fn"] = pa.alarm.eq(0).astype(int)
        tab = pa.groupby(["pos_grp", "vib_high"]).agg(rows=("fn", "size"), fn=("fn", "sum")).reset_index()
        tab["rate"] = (tab.fn / tab.rows).round(4)
        tab["ci95"] = [cp95(int(k), int(n)) for k, n in zip(tab.fn, tab.rows)]
        r["fn_position_x_vibration"] = tab.to_dict("records")
        early, late = pa[pa.position.le(1)], pa[pa.position.ge(2)]
        r["fn_early_vs_late"] = dict(early=f"{int(early.fn.sum())}/{len(early)}", late=f"{int(late.fn.sum())}/{len(late)}",
                                     fisher_p=fisher_greater(int(early.fn.sum()), len(early), int(late.fn.sum()), len(late)))
        for name, g in (("pos0_1", early), ("pos2plus", late)):
            lo, hi = g[~g.vib_high], g[g.vib_high]
            r[f"fn_vib_normal_vs_high_{name}"] = dict(vib_normal=f"{int(lo.fn.sum())}/{len(lo)}", vib_high=f"{int(hi.fn.sum())}/{len(hi)}",
                                                     fisher_p=fisher_greater(int(lo.fn.sum()), len(lo), int(hi.fn.sum()), len(hi)))
        r["abnormal_vib_normal_segments"] = ft["abn"][~ft["abn"].vib_high][["record_id", "length", "vibz_max", "wave"]].to_dict("records")
        # 행 단위 조건표(길이·진폭)가 위치(초반 창)와 교락되는가: 전체 대 위치 ≥2 층의 비율
        pa["len_bin"] = [AN._bin(n, AN.LEN_BINS) for n in pa.length]
        pa = pa.merge(ft["abn"][["record_id", "amp_q"]], on="record_id")
        strat = {}
        for cond in ("len_bin", "amp_q", "vib_q"):
            allr = pa.groupby(cond).fn.agg(["sum", "size"])
            lat = pa[pa.position.ge(2)].groupby(cond).fn.agg(["sum", "size"])
            early_share = pa[pa.position.le(1)].groupby(cond).size() / pa.groupby(cond).size()
            strat[cond] = {str(k): dict(all=f"{int(allr.loc[k, 'sum'])}/{int(allr.loc[k, 'size'])}",
                                        pos2plus=f"{int(lat.loc[k, 'sum'])}/{int(lat.loc[k, 'size'])}" if k in lat.index else None,
                                        share_rows_pos0_1=round(float(early_share.get(k, 0)), 3)) for k in allr.index}
        r["fn_condition_stratified_by_position"] = strat
        # 위치 0·1 미탐은 크기 성분만 존재하는 행이다: 그 행들의 크기 성분 발화 센서
        r["fn_rows_pos0_1_magnitude_sensor"] = early[early.fn.eq(1)].magnitude_sensor.value_counts().to_dict()

        # 3) 오경보: 조건·시간대·통계 검정
        fps = []
        for alpha, (pn_a, _) in preds.items():
            fps += fp_segments(pn_a, ft["test"], cal_end, seg_times, alpha, f"{sid}_frozen")
        r["fp_segments"] = fps
        pooled_fp += [dict(f, pool=f"{sid}_frozen") for f in fps]
        tf = ft["test"].copy()
        tf["alert"] = tf.record_id.map(pn.groupby("record_id").alarm.max()).fillna(0).astype(int)
        k_in, n_in = int(tf[tf.vib_high].alert.sum()), int(tf.vib_high.sum())
        k_out, n_out = int(tf[~tf.vib_high].alert.sum()), int((~tf.vib_high).sum())
        r["fp_vib_high_concentration_alpha1"] = dict(vib_high=f"{k_in}/{n_in}", ci95=cp95(k_in, n_in) if n_in else None,
                                                     normal_range=f"{k_out}/{n_out}",
                                                     fisher_p=fisher_greater(k_in, n_in, k_out, n_out) if n_in else None)
        # 오경보에 못 미친 근접 구간: 정상 평가 구간 최대 점수 / α=1% 문턱
        from serve import score_threshold
        thr = score_threshold(model.cal, .01)
        segmax = pn.groupby("record_id").score.max()
        tf["ratio"] = tf.record_id.map(segmax) / thr
        rho = {c: round(float(stats.spearmanr(tf[c], tf.ratio, nan_policy="omit")[0]), 3) for c in ("vibz_max", "vib_std", "amp_proxy", "length")}
        tf["abs_segment"] = tf.record_id + cal_end
        rho["abs_segment(time)"] = round(float(stats.spearmanr(tf.abs_segment, tf.ratio)[0]), 3)
        top = tf.sort_values("ratio", ascending=False).head(10)
        r["near_miss"] = dict(threshold=round(float(thr), 4), spearman_ratio_vs=rho,
                              segments_ratio_ge_0_8=int((tf.ratio >= .8).sum()), segments_ratio_ge_0_9=int((tf.ratio >= .9).sum()),
                              top10=top[["record_id", "abs_segment", "length", "vibz_max", "vib_high", "wave", "amp_q", "ratio"]].round(3).to_dict("records"),
                              top10_vib_high=int(top.vib_high.sum()))
        # 진동-전류 진폭 결합(부하 결합): 정상 학습 구간(길이≥17, 사인 유사)에서 log 진동 산포 ~ log 진폭
        tr = ft["train"]
        m = tr.amp_reliable & tr.wave.eq("sine-like") & tr.vib_std.gt(0)
        slope, icpt, rr, _, _ = stats.linregress(np.log(tr[m].amp_proxy), np.log(tr[m].vib_std))
        rho_tr = float(stats.spearmanr(tr[m].amp_proxy, tr[m].vibz_max)[0])
        mt = tf.amp_reliable & tf.vib_std.gt(0)
        tf.loc[mt, "vib_resid"] = np.log(tf[mt].vib_std) - (icpt + slope * np.log(tf[mt].amp_proxy))
        fp_ids = tf[tf.alert.eq(1)].record_id.tolist()
        rank = tf.vib_resid.rank(ascending=False)
        r["load_coupling"] = dict(train_segments=int(m.sum()), loglog_slope=round(float(slope), 3), loglog_r=round(float(rr), 3),
                                  spearman_amp_vs_vibzmax_train=round(rho_tr, 3),
                                  fp_vib_resid_rank=[int(rank[tf.record_id.eq(i)].iloc[0]) if tf.loc[tf.record_id.eq(i), "vib_resid"].notna().all() else None for i in fp_ids],
                                  fp_vibzmax_rank=[int(tf.vibz_max.rank(ascending=False)[tf.record_id.eq(i)].iloc[0]) for i in fp_ids],
                                  n_resid=int(mt.sum()))
        # 결합의 견고성: 센서별·Spearman·학습 기간 안 블록별, 그리고 이상 구간이 이 결합에서 얼마나 벗어나는가(전류 RMS를 부하 대리로)
        q_tr = D.quantize(D.inputs_only(split["train"]), "matched")
        s_tr = D.segments(q_tr)
        per = pd.DataFrame(dict(seg=s_tr, a0=q_tr[D.SENSORS[0]], a1=q_tr[D.SENSORS[1]], c=q_tr[D.SENSORS[2]]))
        g = per.groupby("seg")
        sd = pd.DataFrame(dict(n=g.size(), a0=g.a0.std(), a1=g.a1.std(), c=g.c.std(ddof=0)))
        sd = sd[sd.n.ge(17) & sd.index.isin(tr[m].record_id)]
        by_sensor = {k: round(float(np.corrcoef(np.log(sd[k]), np.log(sd.c))[0, 1]), 3) for k in ("a0", "a1")}
        blocks = {}
        for b0 in range(0, train_end, 60):
            mm = sd.index.to_series().between(b0, b0 + 59)
            if mm.sum() >= 10:
                blocks[f"{b0}~{b0 + 59}"] = round(float(np.corrcoef(np.log(sd[mm].a0 ** 2 + sd[mm].a1 ** 2) / 2, np.log(sd[mm].c))[0, 1]), 3)
        resid_sd = float(np.std(np.log(tr[m].vib_std) - (icpt + slope * np.log(tr[m].amp_proxy)), ddof=2))
        fa = ft["abn"]
        ma = fa.amp_reliable & fa.vib_std.gt(0)
        za = (np.log(fa[ma].vib_std) - (icpt + slope * np.log(fa[ma].amp_proxy))) / resid_sd
        zt = (tf.loc[mt, "vib_resid"]) / resid_sd
        r["load_coupling"].update(pearson_log_sd_by_sensor=by_sensor, pearson_within_train_blocks=blocks,
                                  spearman_vibstd_amp_train=round(float(stats.spearmanr(tr[m].vib_std, tr[m].amp_proxy)[0]), 3),
                                  resid_sd=round(resid_sd, 4),
                                  abnormal_resid_z=dict(n=int(ma.sum()), median=round(float(np.median(za)), 2), min=round(float(za.min()), 2),
                                                        gt3=int((za > 3).sum())),
                                  normal_test_resid_z=dict(n=int(mt.sum()), median=round(float(np.median(zt)), 2), max=round(float(zt.max()), 2),
                                                           gt3=int((zt > 3).sum())),
                                  fp_amp_q=[str(tf.loc[tf.record_id.eq(i), "amp_q"].iloc[0]) for i in fp_ids],
                                  test_amp_q4_alert=f"{int(tf[tf.amp_q.eq('Q4(≥q75)')].alert.sum())}/{int(tf.amp_q.eq('Q4(≥q75)').sum())}")

        # 4) 센서 수준 기여: 행 귀속(고정 문턱)과 절제(재보정)
        pa1 = preds[.01][1]
        al = pa1[pa1.alarm.eq(1)].copy()
        act = {k: conformal_p(model.cal, al[f"g_{k}"].to_numpy()) <= .01 for k in ("magnitude", "waveform", "dynamics")}
        cur_only = ~act["magnitude"] & (act["waveform"] | act["dynamics"])
        mag_only = act["magnitude"] & ~(act["waveform"] | act["dynamics"])
        r["row_attribution_alpha1"] = dict(alarm_rows=int(len(al)),
                                           magnitude_active_by_sensor=al[act["magnitude"]].magnitude_sensor.value_counts().to_dict(),
                                           only_vibration_magnitude=al[mag_only].magnitude_sensor.value_counts().to_dict(),
                                           only_current_components=int(cur_only.sum()))
        variants = {"full(v2)": ([0, 1, 2], True, True), "no_AI0": ([1, 2], True, True), "no_AI1": ([0, 2], True, True),
                    "no_AI2_in_magnitude": ([0, 1], True, True), "current_only(AI2 all comps)": ([2], True, True),
                    "no_magnitude(waveform+dynamics)": ([], True, True), "vibration_only(AI0+AI1)": ([0, 1], False, False),
                    "AI0_only": ([0], False, False), "AI1_only": ([1], False, False)}
        abl = {name: ablate(model, split, abnormal, *cfg) for name, cfg in variants.items()}
        full = abl["full(v2)"]["0.01"]
        saved = metrics[metrics.split.eq(sid) & metrics.model.eq("guard_v2") & metrics.alpha.eq(.01)].iloc[0]
        assert (full["tp"], full["fp"], full["fn"]) == (int(saved.tp), int(saved.fp), int(saved.fn)), "절제 재현 실패"
        nm = abl["no_magnitude(waveform+dynamics)"]["0.01"]
        s_nm = ablation_saved[ablation_saved.split_id.eq(sid) & ablation_saved.model.eq("no_magnitude") & ablation_saved.criterion.eq("conformal") & ablation_saved.alpha.eq(.01)].iloc[0]
        r["sensor_ablation_full_reproduces_saved"] = True
        r["sensor_ablation_no_magnitude_matches_ablation_v2"] = (nm["tp"], nm["fp"], nm["fn"]) == (int(s_nm.tp), int(s_nm.fp), int(s_nm.fn))
        r["sensor_ablation"] = abl
        log(sid, "센서 절제 끝")
        r["channel_swap"] = [channel_swap(model, split["test"], abnormal, ch, 20, 20260927 + k)
                             for k, ch in enumerate(([0], [1], [2], [0, 1], [0, 1, 2]))]
        log(sid, "채널 교체 끝")
        res["splits"][sid] = r

    # 5) 시간순 재적합 5개 폴드의 오경보(α 1·3·5%)를 모아 조건 확인. 420~479 폴드는 B와 학습·보정이 같다.
    folds = []
    for end in (180, 240, 300, 360, 420):
        tr = normal[seg_all < end].reset_index(drop=True)
        ca = normal[(seg_all >= end) & (seg_all < end + 120)].reset_index(drop=True)
        te = normal[(seg_all >= end + 120) & (seg_all < end + 180)].reset_index(drop=True)
        m = GuardModel.fit(tr, ca, split=f"train_to_{end}")
        ft, _ = seg_features(m, tr, te, abnormal)
        info = dict(fold=f"{end + 120}~{end + 179}", train_end=end)
        if end == 300:
            b = GuardModel.load(GUARD / "artifacts" / "guard_B.json")
            info["identical_to_guard_B_calibration"] = bool(np.array_equal(np.asarray(m.cal), np.asarray(b.cal)))
        if end == 360:
            a_ = GuardModel.load(GUARD / "artifacts" / "guard_A.json")
            info["identical_to_guard_A_calibration"] = bool(np.array_equal(np.asarray(m.cal), np.asarray(a_.cal)))
        for alpha in ALPHAS:
            p = m.predict(te, alpha)
            f = fp_segments(p, ft["test"], end + 120, seg_times, alpha, f"fold_{end + 120}")
            info[f"fp_segments_alpha_{alpha}"] = len(f)
            pooled_fp += [dict(x, pool=f"fold_{end + 120}") for x in f]
        folds.append(info)
    res["rolling_folds"] = folds
    log("폴드 끝")

    # 오경보 풀링: (폴드/분할, 절대 구간) 기준 α=5% 사건(α=1·3%는 부분집합). 모델이 같은 폴드는 중복 제거.
    pf = pd.DataFrame(pooled_fp)
    pf5 = pf[pf.alpha.eq(.05)].copy()
    # A 동결 = 폴드 480 모델(학습 <360, 보정 360~479), B 동결 = 폴드 420 모델(학습 <300). 같은 모델·같은 구간 중복을 지운다.
    pf5["model_key"] = pf5.pool.map({"A_frozen": "fold_480", "B_frozen": "fold_420"}).fillna(pf5.pool)
    uniq = pf5.drop_duplicates(["model_key", "abs_segment"])
    res["fp_pooled_alpha5"] = dict(events=int(len(uniq)), unique_segments=int(uniq.abs_segment.nunique()),
                                   vib_high=int(uniq.vib_high.sum()), sine_like=int(uniq.wave.eq("sine-like").sum()),
                                   length_ge30=int(uniq.length.ge(30).sum()),
                                   magnitude_only=int(uniq.reasons.map(lambda x: x == ["magnitude"]).sum()),
                                   single_alarm_row=int(uniq.alarm_rows.eq(1).sum()),
                                   magnitude_sensor_counts=pd.Series([s for x in uniq.magnitude_sensors for s in x]).value_counts().to_dict(),
                                   by_block=uniq.block.value_counts().to_dict(),
                                   events_detail=uniq.drop(columns=["model_key"]).to_dict("records"))

    # 6) v1 패키지의 B 오경보 구간이 v2와 같은가(v1의 지속성·진폭 정규화 개선 시도를 v2 오경보에 옮길 수 있는지)
    v1 = pd.read_csv(YEJUN / "press_submission/outputs/predictions_B.csv")
    v1n = v1[v1.source.eq("normal_test")]
    v1_fp = sorted(v1n[v1n.alarm.eq(1)].record_id.unique().tolist())
    res["v1_B_fp_records(v1 numbering)"] = v1_fp
    res["v2_B_fp_records"] = sorted({f["record_id"] for f in res["splits"]["B"]["fp_segments"] if f["alpha"] == .01})

    # 7) 오류 조건표에 구간·비율의 신뢰구간이나 검정 열이 있는가
    res["condition_tables_have_ci_or_test_columns"] = bool(any(c for c in list(errors.columns) + list(segerr.columns)
                                                               if any(s in c.lower() for s in ("ci", "upper", "lower", "p_value", "fisher", "lift"))))
    res["elapsed_s"] = round(time.monotonic() - T0, 1)
    (HERE / "judge03_verify.json").write_text(json.dumps(D.to_jsonable(res), ensure_ascii=False, indent=1))
    log("완료")
    print(json.dumps(D.to_jsonable({k: v for k, v in res.items() if k != "fp_pooled_alpha5"}), ensure_ascii=False, indent=1)[:20000])
    print(json.dumps(D.to_jsonable({k: v for k, v in res["fp_pooled_alpha5"].items() if k != "events_detail"}), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
