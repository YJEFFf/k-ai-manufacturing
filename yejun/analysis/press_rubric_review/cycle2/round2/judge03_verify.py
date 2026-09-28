"""평가관 03 사이클2 2회차 검수(영향요인·오류분석, 15점) — 원본 CSV·동결 v2·커밋 코드로 1회차 E1~E8 완료 기준을 직접 다시 계산한다.

    cd yejun
    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
        analysis/press_rubric_review/cycle2/round2/judge03_verify.py > analysis/press_rubric_review/cycle2/round2/judge03_verify.log 2>&1

읽기 전용 검수. 쓰기는 이 폴더의 judge03_verify.json, judge03_fp_intensity.csv, judge03_e1_host_intensity.csv 세 개다.
모델·문턱·분할·기존 산출물은 바꾸지 않는다. insights.py의 함수는 부르지 않고 같은 정의를 이 파일에서 따로 구현해
팀 산출물(sensor_importance_v2 등)과 대조한다. 새 분석(N1 오경보×운전 강도, N2 주입 탐지×운전 강도)은
"지금 자료로 고칠 수 있는 부족분"을 가리기 위한 검수용 사후 계산이며 성능 근거가 아니다.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
GUARD = YEJUN / "press_guard"
OUT = GUARD / "outputs"
ART = GUARD / "artifacts"
sys.path.insert(0, str(GUARD))
from model import GuardModel, D, ALPHAS, layout  # noqa: E402
from press.calibrate import conformal_p, segment_max  # noqa: E402
from press.scores import ExpTail  # noqa: E402
from press.diagnosis import sine_fit, MIN_FIT_LEN  # noqa: E402

T0 = time.monotonic()
S = D.SENSORS
RES: dict = {}
TIMING: dict = {}
LEN_BINS = [(1, 4, "≤4"), (5, 9, "5–9"), (10, 29, "10–29"), (30, 10**9, "≥30")]


def log(*a):
    print(f"[{time.monotonic() - T0:6.1f}s]", *a, flush=True)


def cp(k, n):
    """Clopper–Pearson 양측 95%."""
    if n == 0:
        return [np.nan, np.nan]
    lo = 0.0 if k == 0 else float(stats.beta.ppf(.025, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(.975, k + 1, n - k))
    return [lo, hi]


def fisher(k1, n1, k2, n2, alt="greater"):
    return float(stats.fisher_exact([[k1, n1 - k1], [k2, n2 - k2]], alternative=alt).pvalue)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


WATCH = [GUARD, YEJUN / "press_submission" / "outputs", *(YEJUN / "analysis" / p for p in
         ("press_evidence", "press_selection", "press_supplement", "press_dayshift", "press_supervised", "press_advance", "press_early", "press_external"))]


def snapshot():
    out = {}
    for d in WATCH:
        for p in sorted(d.rglob("*")):
            if p.is_file():
                out[str(p.relative_to(YEJUN))] = sha(p)
    return out


def prep(frame):
    q = D.quantize(D.inputs_only(frame), "matched")
    return q, layout(q)[1]


def rec_feats(q, seg, model):
    """기록구간 특징: 길이, 진동 SD(두 센서 합성), 센서별 SD, 전류 진폭(√2×평균 제거 RMS), 진동 max|z|, 사인 R²(길이≥10)."""
    v = q[S[:2]].to_numpy(float)
    cur = q[S[2]].to_numpy(float)
    zv = np.abs((v - model.mean[:2]) / model.scale[:2]).max(1)
    rows = []
    for r in np.unique(seg):
        i = np.flatnonzero(seg == r)
        c = cur[i]
        rows.append(dict(record=int(r), length=len(i),
                         vib_sd=float(np.sqrt(v[i, 0].var(ddof=1) + v[i, 1].var(ddof=1))) if len(i) > 1 else np.nan,
                         ai0_sd=float(v[i, 0].std(ddof=1)) if len(i) > 1 else np.nan, ai1_sd=float(v[i, 1].std(ddof=1)) if len(i) > 1 else np.nan,
                         amp=float(np.sqrt(2 * np.mean((c - c.mean()) ** 2))), vib_maxz=float(zv[i].max()),
                         r2=float(sine_fit(c)[1]) if len(i) >= MIN_FIT_LEN else np.nan))
    return pd.DataFrame(rows)


def main():
    RES["head"] = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    RES["git_status_short_yejun"] = subprocess.run(["git", "-C", str(REPO), "status", "--short", "--", "yejun"], capture_output=True, text=True).stdout.strip()
    before = snapshot()
    pyc_before = sorted(str(p.relative_to(YEJUN)) for p in YEJUN.rglob("__pycache__"))
    normal, abnormal, report = D.load(YEJUN / "press_submission")
    RES["input_sha256"] = {k: v["sha256"] for k, v in report["files"].items()}
    man = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    RES["model_sha256_matches_manifest"] = {s: sha(ART / f"guard_{s}.json") == man["artifacts"][f"guard_{s}.json"] for s in "AB"}
    seg_all = D.segments(normal)
    t_all = pd.to_datetime(normal[D.TIME])
    metrics = pd.read_csv(OUT / "metrics.csv")
    models = {s: GuardModel.load(ART / f"guard_{s}.json") for s in "AB"}
    splits = {s: D.split_normal(normal, seg_all, s) for s in "AB"}

    # ------------------------------------------------------------------ S1 재추론
    t = time.monotonic()
    rec = {}
    preds = {}
    for s, m in models.items():
        for a in ALPHAS:
            pn, pa = m.predict(splits[s]["test"], a), m.predict(abnormal, a)
            preds[(s, a)] = (pn, pa)
            got = dict(tp=int(pa.alarm.sum()), fp=int(pn.alarm.sum()), fn=int((pa.alarm == 0).sum()),
                       normal_notified_segments=int(pn.groupby("record_id").alarm.max().sum()),
                       abnormal_notified_segments=int(pa.groupby("record_id").alarm.max().sum()))
            saved = metrics[metrics.split.eq(s) & metrics.model.eq("guard_v2") & metrics.alpha.eq(a)].iloc[0]
            got["matches_metrics_csv"] = all(int(saved[k]) == v for k, v in got.items())
            rec[f"{s}_{a}"] = got
    RES["S1_recount"] = rec
    TIMING["S1"] = time.monotonic() - t
    log("S1", {k: v["matches_metrics_csv"] for k, v in rec.items()})

    # ------------------------------------------------------------------ S2 E1 센서 중요도
    t = time.monotonic()
    si = pd.read_csv(OUT / "sensor_importance_v2.csv")
    e1 = {"refit_ablation": {}, "channel_swap": {}, "attribution": {}, "univariate": {}, "explain": {}}
    variants = {"full": ((0, 1, 2), True), "drop_AI0": ((1, 2), True), "drop_AI1": ((0, 2), True), "drop_AI2_from_magnitude": ((0, 1), True),
                "current_only": ((2,), True), "vibration_only": ((0, 1), False)}
    mism = []
    for s, m in models.items():
        sp = splits[s]
        C = {}
        for k, fr in (("train", sp["train"]), ("cal", sp["cal"]), ("test", sp["test"]), ("abn", abnormal)):
            q, sg = prep(fr)
            comp = m.components(q, sg)
            C[k] = dict(z=np.abs((q[S].to_numpy(float) - m.mean) / m.scale), gw=comp["g_waveform"], gd=comp["g_dynamics"], seg=sg)
        for name, (sens, shape) in variants.items():
            tail = ExpTail(C["train"]["z"][:, list(sens)].max(1))

            def score(k):
                sc = tail(C[k]["z"][:, list(sens)].max(1))
                return np.fmax(np.fmax(sc, C[k]["gw"]), C[k]["gd"]) if shape else sc
            cal = segment_max(score("cal"), C["cal"]["seg"])
            for a in ALPHAS:
                pn, pa = conformal_p(cal, score("test")), conformal_p(cal, score("abn"))
                an, aa = np.isfinite(pn) & (pn <= a), np.isfinite(pa) & (pa <= a)
                r = dict(tp=int(aa.sum()), fp=int(an.sum()), fn=int(len(aa) - aa.sum()),
                         normal_alerted=int(pd.Series(an).groupby(C["test"]["seg"]).max().sum()),
                         abnormal_detected=int(pd.Series(aa).groupby(C["abn"]["seg"]).max().sum()))
                r["f1"] = 2 * r["tp"] / (2 * r["tp"] + r["fp"] + r["fn"])
                e1["refit_ablation"][f"{s}_{name}_{a}"] = r
                row = si[si.method.eq("refit_ablation") & si.split.eq(s) & si.variant.eq(name) & np.isclose(si.alpha, a)].iloc[0]
                if (r["tp"], r["fp"], r["fn"], r["normal_alerted"], r["abnormal_detected"]) != (int(row.tp), int(row.fp), int(row.fn), int(row.normal_alerted_segments), int(row.abnormal_detected_segments)):
                    mism.append((s, name, a, r, row.to_dict()))
        # 채널 교체(팀과 다른 난수열 20회)
        test = D.inputs_only(sp["test"]).reset_index(drop=True)
        tseg = D.segments(test)
        tlen = pd.Series(tseg).value_counts()
        abn = D.inputs_only(abnormal).reset_index(drop=True)
        aseg = D.segments(abn)
        for label, cols in (("AI0", [0]), ("AI1", [1]), ("AI2", [2]), ("AI0+AI1", [0, 1]), ("all", [0, 1, 2])):
            rng = np.random.default_rng(777 + len(label) + (0 if s == "A" else 100))
            fns, dets = [], []
            for rep in range(20):
                mod = abn.copy()
                for rr in np.unique(aseg):
                    rows = np.flatnonzero(aseg == rr)
                    donors = tlen[tlen >= len(rows)].index.to_numpy()
                    drows = np.flatnonzero(tseg == rng.choice(donors))[:len(rows)]
                    for c in cols:
                        mod.loc[rows, S[c]] = test.loc[drows, S[c]].to_numpy()
                p = m.predict(mod, .01)
                fns.append(int((p.alarm == 0).sum())); dets.append(int(p.groupby("record_id").alarm.max().sum()))
            e1["channel_swap"][f"{s}_{label}"] = dict(fn_median=float(np.median(fns)), fn_min=min(fns), fn_max=max(fns), det_median=float(np.median(dets)),
                                                     det_min=min(dets), det_max=max(dets))
            if label in ("AI0", "AI1", "AI2"):
                row = si[si.method.eq("channel_swap") & si.split.eq(s) & si.variant.eq(f"swap_{S[cols[0]]}")].iloc[0]
                e1["channel_swap"][f"{s}_{label}"]["matches_table_median"] = (float(np.median(fns)) == float(row.fn)) and (float(np.median(dets)) == float(row.abnormal_detected_segments))
        # 경보 행 귀속
        pa = preds[(s, .01)][1]
        al = pa[pa.alarm.eq(1)]
        mag = al.reason.str.contains("magnitude")
        att = {f"magnitude_{x}": int((mag & al.magnitude_sensor.eq(S[i])).sum()) for i, x in enumerate(("AI0", "AI1", "AI2"))}
        att["current_components_only"] = int((~mag).sum())
        att["alarm_rows"] = int(len(al))
        tab = si[si.method.eq("alarm_attribution") & si.split.eq(s)].set_index("variant").tp
        att["matches_table"] = all(int(tab[k]) == v for k, v in att.items() if k in tab.index)
        e1["attribution"][s] = att
        # 단변량 판별력(구간 SD AUROC, 원값)
        tr_raw = D.inputs_only(sp["test"]); segt = layout(tr_raw)[1]
        ab_raw = D.inputs_only(abnormal); sega = layout(ab_raw)[1]
        uni = {}
        for i, c in enumerate(S):
            sdn = tr_raw.groupby(segt)[c].std().dropna(); sda = ab_raw.groupby(sega)[c].std().dropna()
            auc = roc_auc_score(np.r_[np.zeros(len(sdn)), np.ones(len(sda))], np.r_[sdn, sda])
            row = si[si.method.eq("univariate_segment_sd") & si.split.eq(s) & si.variant.eq(c)].iloc[0]
            uni[c] = dict(auroc=float(auc), table=float(row.auroc), normal_test_sd_median_over_scale=float(sdn.median() / m.scale[i]),
                          normal_test_sd_iqr_over_scale=float((sdn.quantile(.75) - sdn.quantile(.25)) / m.scale[i]),
                          abnormal_sd_median_over_scale=float(sda.median() / m.scale[i]))
        e1["univariate"][s] = uni
        # 순위 역전 설명용: α=1% 문턱에서 크기 성분이 넘는 |z| 수준과, 센서별로 그 수준을 넘는 이상·정상 평가 행
        thr = float(np.sort(m.cal)[-1])
        tl = m.tails["magnitude"]
        grid = np.linspace(0, 40, 400001)
        assert tl(grid[-1:])[0] > thr
        zstar = float(grid[np.argmax(tl(grid) > thr)])
        zt, za = C["test"]["z"], C["abn"]["z"]
        e1["explain"][s] = dict(alpha1_threshold_score=thr, magnitude_z_needed=zstar,
                                abnormal_rows_over=dict(zip(("AI0", "AI1", "AI2"), map(int, (za > zstar).sum(0)))),
                                normal_test_rows_over=dict(zip(("AI0", "AI1", "AI2"), map(int, (zt > zstar).sum(0)))),
                                abnormal_records_any_over=dict(zip(("AI0", "AI1", "AI2"), [int(pd.Series(za[:, j] > zstar).groupby(C["abn"]["seg"]).max().sum()) for j in range(3)])),
                                abnormal_row_absz_p95=dict(zip(("AI0", "AI1", "AI2"), map(float, np.nanpercentile(za, 95, axis=0)))))
    e1["refit_mismatches"] = mism
    RES["S2_E1"] = e1
    TIMING["S2"] = time.monotonic() - t
    log("S2 E1 mismatches", len(mism), {k: v.get("matches_table_median") for k, v in e1["channel_swap"].items()})

    # ------------------------------------------------------------------ S3 E2 위치×진동, 층화, 결합
    t = time.monotonic()
    pvm = pd.read_csv(OUT / "position_vibration_misses_v2.csv")
    ec = pd.read_csv(OUT / "error_conditions_v2.csv")
    cfit = pd.read_csv(OUT / "coupling_fit_v2.csv")
    crec = pd.read_csv(OUT / "coupling_records_v2.csv")
    e2 = {"pos_vib": {}, "pos_ge2_len": {}, "coupling": {}}
    feats = {}
    for s, m in models.items():
        sp = splits[s]
        _, train_end, cal_end = D.SPLITS[s]
        qtr, str_ = prep(sp["train"]); qte, ste = prep(sp["test"]); qab, sab = prep(abnormal)
        ftr, fte, fab = rec_feats(qtr, str_, m), rec_feats(qte, ste, m), rec_feats(qab, sab, m)
        feats[s] = (ftr, fte, fab)
        q95 = float(ftr.vib_maxz.quantile(.95))
        pa = preds[(s, .01)][1]
        pos = pa.position.to_numpy(); miss = pa.alarm.to_numpy() == 0
        vh = pa.record_id.map(fab.set_index("record").vib_maxz > q95).to_numpy(bool)
        cells = {}
        for pl, pm in (("0-1", pos <= 1), ("2-6", (pos >= 2) & (pos <= 6)), (">=7", pos >= 7), (">=2", pos >= 2)):
            for vl, vm in (("vibration_normal_range", ~vh), ("vibration_high", vh)):
                k, n = int((miss & pm & vm).sum()), int((pm & vm).sum())
                row = pvm[pvm.split.eq(s) & pvm.position.eq(pl) & pvm.vibration.eq(vl)].iloc[0]
                cells[f"{pl}|{vl}"] = dict(k=k, n=n, ci=cp(k, n), table=(int(row.missed_rows), int(row.rows)), match=(k, n) == (int(row.missed_rows), int(row.rows)))
            a1, b1 = cells[f"{pl}|vibration_normal_range"], cells[f"{pl}|vibration_high"]
            if a1["n"] and b1["n"]:
                cells[f"{pl}|fisher_greater"] = fisher(a1["k"], a1["n"], b1["k"], b1["n"])
                cells[f"{pl}|fisher_two_sided"] = fisher(a1["k"], a1["n"], b1["k"], b1["n"], "two-sided")
        k01, n01 = int((miss & (pos <= 1)).sum()), int((pos <= 1).sum()); k2, n2 = int((miss & (pos >= 2)).sum()), int((pos >= 2).sum())
        cells["pos01_vs_ge2"] = dict(pos01=(k01, n01), ge2=(k2, n2), fisher_greater=fisher(k01, n01, k2, n2))
        cells["vib_normal_records"] = fab[~(fab.vib_maxz > q95)].record.tolist()
        cells["q95"] = q95
        e2["pos_vib"][s] = cells
        # 위치 ≥2 층의 길이 조건(행 조건표의 *_pos_ge2 열)
        ln = pa.groupby("record_id").position.transform("size").to_numpy()
        lay = {}
        for lo, hi, lab in LEN_BINS:
            mm = (ln >= lo) & (ln <= hi)
            k_all, n_all = int((miss & mm).sum()), int(mm.sum())
            k_2, n_2 = int((miss & mm & (pos >= 2)).sum()), int((mm & (pos >= 2)).sum())
            row = ec[ec.split_id.eq(s) & ec.model.eq("v2") & np.isclose(ec.alpha, .01) & ec.subset.eq("abnormal") & ec.condition.eq("len_bin") & ec.value.eq(lab)].iloc[0]
            lay[lab] = dict(all=(k_all, n_all), pos_ge2=(k_2, n_2), match=(k_all, n_all, k_2, n_2) == (int(row.error_rows), int(row.rows), int(row.error_rows_pos_ge2), int(row.rows_pos_ge2)))
        e2["pos_ge2_len"][s] = lay
        # 진동–전류 진폭 결합
        r2_low = float(ftr.r2.dropna().quantile(.05))
        ok = (ftr.length >= 17) & (ftr.r2 >= r2_low) & (ftr.vib_sd > 0) & (ftr.amp > 0)
        x, y = np.log(ftr.amp[ok]), np.log(ftr.vib_sd[ok])
        lr = stats.linregress(x, y)
        rsd = float(np.std(y - (lr.intercept + lr.slope * x), ddof=2))
        blocks = []
        for b in range(0, train_end, 60):
            mb = ok & (ftr.record >= b) & (ftr.record < b + 60)
            if mb.sum() >= 10:
                blocks.append(float(np.corrcoef(np.log(ftr.amp[mb]), np.log(ftr.vib_sd[mb]))[0, 1]))

        def resid(f):
            f = f[(f.length >= 17) & (f.vib_sd > 0) & (f.amp > 0)].copy()
            f["z"] = (np.log(f.vib_sd) - (lr.intercept + lr.slope * np.log(f.amp))) / rsd
            return f
        ra, rt = resid(fab), resid(fte)
        fa_rel = sorted(preds[(s, .01)][0].groupby("record_id").alarm.max().pipe(lambda x: x[x.eq(1)]).index.tolist())
        rt["rank"] = rt.z.rank(ascending=False).astype(int)
        cf = cfit[cfit.split.eq(s)].iloc[0]
        e2["coupling"][s] = dict(records=int(ok.sum()), slope=float(lr.slope), r=float(lr.rvalue), resid_sd=rsd,
                                 r_ai0=float(np.corrcoef(x, np.log(ftr.ai0_sd[ok]))[0, 1]), r_ai1=float(np.corrcoef(x, np.log(ftr.ai1_sd[ok]))[0, 1]),
                                 block_r=[min(blocks), max(blocks), len(blocks)],
                                 table=dict(records=int(cf.records), slope=float(cf.slope), r=float(cf.r), r_ai0=float(cf.r_ai0), r_ai1=float(cf.r_ai1),
                                            block_r=[float(cf.block_r_min), float(cf.block_r_max), int(cf.blocks)]),
                                 abnormal_z=dict(n=len(ra), median=float(ra.z.median()), gt3=int((ra.z > 3).sum())),
                                 normal_test_z=dict(n=len(rt), max=float(rt.z.max())),
                                 fa_relative=fa_rel, fa_absolute=[cal_end + r for r in fa_rel],
                                 fa_resid_rank=[int(rt.set_index("record").loc[r, "rank"]) for r in fa_rel if r in set(rt.record)],
                                 fa_amp_pct_in_test=[float((rt.amp < rt.set_index("record").loc[r, "amp"]).mean()) for r in fa_rel if r in set(rt.record)])
        # 표의 값과 대조
        cr = crec[crec.split.eq(s)]
        e2["coupling"][s]["records_table_abnormal_median"] = float(cr[cr.subset.eq("abnormal")].resid_z.median())
        e2["coupling"][s]["records_table_uses_relative_ids"] = sorted(cr[cr.false_alarm.astype(bool)].record.tolist()) == fa_rel
    RES["S3_E2"] = e2
    TIMING["S3"] = time.monotonic() - t
    log("S3 E2", {s: all(v["match"] for k, v in e2["pos_vib"][s].items() if isinstance(v, dict) and "match" in v) for s in "AB"},
        {s: all(v["match"] for v in e2["pos_ge2_len"][s].values()) for s in "AB"})

    # ------------------------------------------------------------------ S4 E3 오경보 모음·근접·(N1) 운전 강도별 조건부 오경보율
    t = time.monotonic()
    fits = {"frozen_A": (models["A"], 480, 600), "frozen_B": (models["B"], 420, 600)}
    ident = {}
    for end in (180, 240, 300, 360, 420):
        tr = normal[seg_all < end]; ca = normal[(seg_all >= end) & (seg_all < end + 120)]
        mm = GuardModel.fit(tr, ca, split=f"train_to_{end}")
        fits[f"rolling_test_{end + 120}_{end + 179}"] = (mm, end + 120, end + 180)
        if end == 300:
            ident["fold_420_479_equals_B"] = bool(np.array_equal(np.sort(mm.cal), np.sort(models["B"].cal)))
        if end == 360:
            ident["fold_480_539_equals_A"] = bool(np.array_equal(np.sort(mm.cal), np.sort(models["A"].cal)))
    seen, ev, evals = {}, [], []
    for name, (mm, lo, hi) in fits.items():
        key = tuple(np.round(np.sort(mm.cal), 12))
        same = seen.get(key); seen.setdefault(key, name)
        mask = (seg_all >= lo) & (seg_all < hi)
        frame = normal[mask]
        rid = seg_all[mask]
        q, sg = prep(frame)
        f = rec_feats(q, sg, mm)
        f["absolute"] = [int(rid[np.flatnonzero(sg == r)[0]]) for r in f.record]
        for a in ALPHAS:
            p = mm.predict(frame, a)
            al = p.groupby("record_id").alarm.max()
            for r, g in p.groupby("record_id"):
                if g.alarm.any():
                    first = g[g.alarm.eq(1)].iloc[0]
                    ev.append(dict(model=name, same=same or "", alpha=a, record=int(rid[g.index[0]]), length=len(g), alarm_rows=int(g.alarm.sum()),
                                   first_pos=int(first.position), reasons="+".join(sorted(set("+".join(g[g.alarm.eq(1)].reason).split("+")) - {""})),
                                   sensor=first.magnitude_sensor if "magnitude" in first.reason else ""))
            evals.append(f.assign(model=name, same=same or "", alpha=a, fa=f.record.map(al).fillna(0).astype(int).to_numpy()))
    ev = pd.DataFrame(ev)
    evals = pd.concat(evals, ignore_index=True)
    team = pd.read_csv(OUT / "fp_events_v2.csv").fillna("")
    mine = ev.assign(independent=ev.same.eq(""))
    key_cols = ["model", "alpha", "record", "length", "alarm_rows", "reasons"]
    a_set = {tuple(x) for x in mine[key_cols].astype(str).itertuples(index=False)}
    b_set = {tuple(x) for x in team.rename(columns={"first_alarm_position": "first_pos"})[key_cols].astype(str).itertuples(index=False)}
    ind5 = mine[mine.independent & np.isclose(mine.alpha, .05)]
    e3 = dict(calibration_identity=ident, events_match_table=a_set == b_set, n_mine=len(mine), n_table=len(team),
              alpha5_independent=dict(events=len(ind5), unique_records=int(ind5.record.nunique()),
                                      ai0_magnitude_only=int(((ind5.reasons == "magnitude") & (ind5.sensor == "AI0_Vibration")).sum()),
                                      length_ge30=int((ind5.length >= 30).sum()), single_alarm_row=int((ind5.alarm_rows == 1).sum()),
                                      block_480_539=int(((ind5.record >= 480) & (ind5.record < 540)).sum()),
                                      record_570_models=sorted(ind5[ind5.record.eq(570)].model.tolist())),
              table_has_columns=dict(wave=any(c in team.columns for c in ("wave", "r2", "sine_like")),
                                     amp_quartile=any("quartile" in c or c.endswith("_q") for c in team.columns)))
    # 사인 유사 여부(모델별 정상 학습 경계가 아니라 B 학습 r2 q05로 통일해 확인)
    r2_low_B = float(feats["B"][0].r2.dropna().quantile(.05))
    ev5 = evals[evals.same.eq("") & np.isclose(evals.alpha, .05) & evals.fa.eq(1)]
    e3["alpha5_independent"]["sine_like_by_B_train_q05"] = int((ev5.r2 >= r2_low_B).sum())
    # 근접 오경보
    nm = pd.read_csv(OUT / "near_miss_corr_v2.csv")
    near = {}
    for s, m in models.items():
        lo = D.SPLITS[s][2]
        frame = normal[seg_all >= lo]
        q, sg = prep(frame)
        f = rec_feats(q, sg, m)
        smax = segment_max(m.components(q, sg)["score"], sg)
        f["ratio"] = smax / np.sort(m.cal)[-1]
        f["time"] = np.arange(len(f))
        rho = {c: float(stats.spearmanr(f.ratio[f[c].notna()], f[c].dropna()).statistic) for c in ("vib_maxz", "vib_sd", "amp", "time")}
        tb = nm[nm.split.eq(s)].set_index("condition").spearman
        near[s] = dict(spearman=rho, ge_0_9=int((f.ratio >= .9).sum()),
                       match=all(abs(rho[a] - tb[b]) < 1e-9 for a, b in (("vib_maxz", "vib_maxz"), ("vib_sd", "vib_sd"), ("amp", "current_amp"), ("time", "time_order"))))
    e3["near_miss"] = near
    # N1: 독립 모델 5개(동결 A·B, 시간순 300·360·540 폴드)의 평가 구간을 분모로 한 운전 강도별 조건부 오경보율
    ind = evals[evals.same.eq("")].copy()
    n1 = {}
    rows_out = []
    # 운전 강도 사분위: 평가된 구간 자체의 분포(구간 × 모델 평가 480건, 길이 ≥17만 진폭 신뢰)로 통일한 경계
    base = ind[np.isclose(ind.alpha, .01)]
    amp_q = base[base.length >= 17].amp.quantile([.25, .5, .75]).to_numpy()
    vsd_q = base.vib_sd.dropna().quantile([.25, .5, .75]).to_numpy()
    ftrB = feats["B"][0]
    amp_q75_btrain = float(ftrB[ftrB.length >= 17].amp.quantile(.75))   # 팀 조건표와 같은 정의(B 정상 학습 구간, 길이 ≥17)
    for a in ALPHAS:
        g = ind[np.isclose(ind.alpha, a)].copy()
        g["amp_Q"] = np.where(g.length < 17, "short(<17)", pd.cut(g.amp, [-np.inf, *amp_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str))
        g["vsd_Q"] = pd.cut(g.vib_sd, [-np.inf, *vsd_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str)
        g["block"] = (g.absolute // 60 * 60).astype(str) + "~" + (g.absolute // 60 * 60 + 59).astype(str)
        res_a = {}
        for cond in ("amp_Q", "vsd_Q", "block"):
            tot_k, tot_n = int(g.fa.sum()), len(g)
            per = {}
            for v, gg in g.groupby(cond):
                k, n = int(gg.fa.sum()), len(gg)
                per[v] = dict(fa=k, n=n, rate=k / n, ci=cp(k, n), lift=(k / n) / (tot_k / tot_n) if tot_k else np.nan,
                              fisher_greater_vs_rest=fisher(k, n, tot_k - k, tot_n - n) if n < tot_n else np.nan)
                rows_out.append(dict(alpha=a, condition=cond, value=v, false_alarm_evaluations=k, evaluations=n, rate=k / n, ci_low=cp(k, n)[0], ci_high=cp(k, n)[1],
                                     lift=per[v]["lift"], fisher_greater_vs_rest=per[v]["fisher_greater_vs_rest"]))
            res_a[cond] = per
        # 고유 구간(300~599, 한 모델이라도 경보) 기준
        u = g.groupby("absolute").agg(fa=("fa", "max"), amp=("amp", "first"), length=("length", "first"), vib_sd=("vib_sd", "first"))
        for lab, cut in (("unique_segments_ampQ4_eval_boundary", amp_q[2]), ("unique_segments_amp_ge_Btrain_q75", amp_q75_btrain)):
            hi_ = (u.length >= 17) & (u.amp >= cut)
            k1, n1_ = int(u[hi_].fa.sum()), int(hi_.sum()); k0, n0 = int(u[~hi_].fa.sum()), int((~hi_).sum())
            res_a[lab] = dict(high=(k1, n1_), rest=(k0, n0), fisher_greater=fisher(k1, n1_, k0, n0) if n1_ and n0 else np.nan, segments=len(u), cut=float(cut))
        res_a["spearman_eval_amp_vs_fa"] = float(stats.spearmanr(g.amp, g.fa).statistic)
        n1[str(a)] = res_a
    n1["boundaries"] = dict(amp=list(map(float, amp_q)), vib_sd=list(map(float, vsd_q)), evaluations=int(len(base)))
    e3["N1_fp_by_intensity"] = n1
    pd.DataFrame(rows_out).to_csv(HERE / "judge03_fp_intensity.csv", index=False)
    RES["S4_E3"] = e3
    TIMING["S4"] = time.monotonic() - t
    log("S4 E3", ident, e3["events_match_table"], e3["alpha5_independent"], {s: v["match"] for s, v in near.items()})
    log("N1 α=5% amp_Q", {k: (v["fa"], v["n"], round(v["lift"], 2), f"{v['fisher_greater_vs_rest']:.2g}") for k, v in n1["0.05"]["amp_Q"].items()})

    # ------------------------------------------------------------------ S5 E4 조건표 통계 열
    t = time.monotonic()
    st = pd.read_csv(OUT / "error_conditions_stats_v2.csv")
    dif = []
    for key, g in st.groupby(["split_id", "model", "alpha", "subset", "condition"], sort=False):
        tk, tn = int(g.error_segments.sum()), int(g.segments.sum())
        for r in g.itertuples():
            lo, hi = cp(int(r.error_segments), int(r.segments))
            p = fisher(int(r.error_segments), int(r.segments), tk - int(r.error_segments), tn - int(r.segments)) if tn - int(r.segments) > 0 else np.nan
            dif.append(max(abs(lo - r.ci_low), abs(hi - r.ci_high), 0 if (np.isnan(p) and np.isnan(r.fisher_p_greater)) else abs(p - r.fisher_p_greater)))
    bvh = st[st.split_id.eq("B") & st.model.eq("v2") & np.isclose(st.alpha, .01) & st.subset.eq("normal") & st.condition.eq("vib_high") & st.value.astype(str).str.startswith("high")].iloc[0]
    RES["S5_E4"] = dict(rows=len(st), max_abs_diff_ci_fisher=float(np.nanmax(dif)), B_vib_high=dict(k=int(bvh.error_segments), n=int(bvh.segments), ci=[float(bvh.ci_low), float(bvh.ci_high)], p=float(bvh.fisher_p_greater)),
                        row_table_has_ci_columns=any(c in ec.columns for c in ("ci_low", "ci_high")))
    TIMING["S5"] = time.monotonic() - t
    log("S5 E4", RES["S5_E4"])

    # ------------------------------------------------------------------ S6 E5 요약표 인용 추적
    t = time.monotonic()
    sm = pd.read_csv(OUT / "error_condition_summary_v2.csv")
    cites = []
    for i, r in sm.iterrows():
        parts = [x.strip() for x in str(r.source).split(";")]
        got = []
        for part in parts:
            path, lines = part.rsplit(":", 1)
            ln = [int(x) for x in lines.split(",")]
            full = pd.read_csv(YEJUN / path)
            got.append((path, ln, full.iloc[[x - 2 for x in ln]]))
        cites.append((i, got))

    def ok_row(i):
        got = dict(cites)[i]
        path, ln, rows = got[0]
        if i == 0:
            v = rows.set_index(["split", "vibration"])
            return (int(v.loc[("A", "vibration_normal_range")].missed_rows), int(v.loc[("A", "vibration_normal_range")].rows), int(v.loc[("B", "vibration_high")].missed_rows)) == (6, 6, 14)
        if i == 1:
            v = rows.set_index(["split", "position"])
            return (int(v.loc[("A", "0-1")].missed_rows), int(v.loc[("B", ">=2")].missed_rows), int(v.loc[("B", ">=2")].rows)) == (26, 11, 558)
        if i in (2, 3, 4, 5):
            fam = {2: ("cur_offset", .8, 0), 3: ("cur_gain", 1.15, 10), 4: ("vib_noise", 2.0, 10), 5: ("cur_offset", .2, 10)}[i]
            okk = all((rows.family == fam[0]) & np.isclose(rows.level, fam[1]) & (rows.t0 == fam[2]) & (rows.model == "guard_v2") & np.isclose(rows.alpha, .01))
            det = rows.set_index("split").detect_rate_2s
            want = {2: (.0326, .2878), 3: (0.0, .0631), 4: (.744, .9387), 5: (.4, .5225)}[i]
            return okk and abs(det["A"] - want[0]) < 5e-4 and abs(det["B"] - want[1]) < 5e-4
        if i == 6:
            full = pd.read_csv(YEJUN / path)
            n_cond = int((full.independent & np.isclose(full.alpha, .05)).sum())
            return dict(cited_rows=len(ln), rows_meeting_condition_in_file=n_cond, cited_all=len(ln) == n_cond)
        if i == 7:
            v = rows.assign(hi=rows.value.astype(str).str.startswith("high")).set_index(["split_id", "hi"])
            return (int(v.loc[("B", True)].error_segments), int(v.loc[("B", True)].segments), int(v.loc[("A", True)].segments)) == (3, 8, 2)
        if i == 8:
            v = rows.set_index("condition").spearman
            return abs(v["vib_maxz"] - .6137) < 1e-3 and abs(v["time_order"] + .312) < 1e-3
        if i == 9:
            v = rows.set_index("k").normal_notified_segments
            return dict(B_values=(int(v[1.0]), int(v[1.05]), int(v[1.5])), A_value_cited=bool((rows.split_id == "A").any()))
        if i == 10:
            v = rows.set_index(["split_id", "input_variant"]).normal_notified_segments
            return (int(v[("A", "coarse")]), int(v[("B", "coarse")]), int(v[("B", "matched")])) == (0, 5, 3)
        return None
    RES["S6_E5"] = dict(rows=len(sm), columns=list(sm.columns), checks={int(i): ok_row(i) for i in range(len(sm))},
                        has_ci_or_lift_columns=any(c in sm.columns for c in ("ci_low", "ci_high", "lift")))
    TIMING["S6"] = time.monotonic() - t
    log("S6 E5", RES["S6_E5"]["checks"])

    # ------------------------------------------------------------------ S7 E7 지속성 변형(위치 0·1은 원래 크기) 재계산
    t = time.monotonic()
    fm = pd.read_csv(YEJUN / "analysis/press_selection/fp_mitigation_v2.csv")
    e7 = {}
    for s, m in models.items():
        sp = splits[s]

        def pscore(frame):
            q, sg = prep(frame)
            c = m.components(q, sg)
            pos, _ = D.segment_positions(sg)
            g = pd.Series(c["g_magnitude"])
            second = g.groupby(sg).transform(lambda x: x.rolling(3, min_periods=3).apply(lambda w: np.sort(w)[-2], raw=True))
            gm = np.where(pos >= 2, second.to_numpy(), c["g_magnitude"])
            return np.fmax(np.fmax(gm, c["g_waveform"]), c["g_dynamics"]), sg
        sc, sgc = pscore(sp["cal"]); stt, sgt = pscore(sp["test"]); sa, sga = pscore(abnormal)
        cal = segment_max(sc, sgc)
        for a in ALPHAS:
            pn, pa_ = conformal_p(cal, stt), conformal_p(cal, sa)
            an, aa = pn <= a, pa_ <= a
            alerted = pd.Series(an).groupby(sgt).max()
            row = fm[fm.split_id.eq(s) & np.isclose(fm.alpha, a) & fm.variant.eq("v2_mag_persist2of3_fill")].iloc[0]
            got = dict(normal_alerted=int(alerted.sum()), fn=int((~aa).sum()),
                       alerted_records_absolute=sorted(int(D.SPLITS[s][2] + r) for r in alerted[alerted].index))
            got["match"] = (got["normal_alerted"], got["fn"]) == (int(row.normal_alerted), int(row.fn_rows))
            e7[f"{s}_{a}"] = got
    RES["S7_E7"] = e7
    TIMING["S7"] = time.monotonic() - t
    log("S7 E7", {k: v["match"] for k, v in e7.items()})

    # ------------------------------------------------------------------ S8 (N2) 주입 탐지 × 주입받은 정상 기록의 운전 강도
    t = time.monotonic()
    e1m = json.loads((YEJUN / "analysis/press_supplement/e1_manifest.json").read_text(encoding="utf-8"))
    rec_path = YEJUN / "analysis/press_supplement/predictions_e1_records.csv"
    n2 = dict(file_sha_matches_manifest=sha(rec_path) == e1m["local_outputs"]["predictions_e1_records.csv"])
    er = pd.read_csv(rec_path)
    er = er[er.model.eq("guard_v2") & np.isclose(er.alpha, .01) & er["shape"].eq("step")]
    out_rows = []
    for s, m in models.items():
        _, _, cal_end = D.SPLITS[s]
        test = D.inputs_only(normal[seg_all >= cal_end]).reset_index(drop=True)
        q, sg = prep(test)
        seg_raw = D.segments(test)
        assert np.array_equal(sg, seg_raw)
        f = rec_feats(q, sg, m).set_index("record")
        for fam, lv, t0 in (("vib_noise", 2.0, 10), ("vib_noise", 4.0, 10), ("cur_noise", .1, 10), ("cur_offset", .2, 10), ("cur_offset", .8, 0), ("cur_gain", 1.15, 10), ("cur_gain", 1.3, 10), ("cur_gain", 1.5, 10)):
            g = er[er.split.eq(s) & er.family.eq(fam) & np.isclose(er.level, lv) & er.t0.eq(t0)]
            if not len(g):
                continue
            d = g.groupby("record").detected_2s.mean().to_frame("det")
            d = d.join(f[["amp", "vib_sd", "length"]])
            d = d[d.length >= 17]
            qs = d.amp.quantile([.25, .5, .75]).to_numpy()
            d["ampQ"] = pd.cut(d.amp, [-np.inf, *qs, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str)
            vq = d.vib_sd.quantile([.25, .5, .75]).to_numpy()
            d["vsdQ"] = pd.cut(d.vib_sd, [-np.inf, *vq, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str)
            rho_a = stats.spearmanr(d.amp, d.det); rho_v = stats.spearmanr(d.vib_sd, d.det)
            byq = {k: f"{v.sum():.1f}/{len(v)}={v.mean():.3f}" for k, v in d.groupby("ampQ").det}
            byv = {k: f"{v.sum():.1f}/{len(v)}={v.mean():.3f}" for k, v in d.groupby("vsdQ").det}
            lo_hi = stats.mannwhitneyu(d[d.ampQ.eq("Q1")].det, d[d.ampQ.eq("Q4")].det).pvalue if d.det.nunique() > 1 else np.nan
            out_rows.append(dict(split=s, family=fam, level=lv, t0=t0, records=len(d), detect_mean=float(d.det.mean()),
                                 spearman_amp=float(rho_a.statistic), p_amp=float(rho_a.pvalue), spearman_vib_sd=float(rho_v.statistic), p_vib_sd=float(rho_v.pvalue),
                                 det_by_ampQ=json.dumps(byq), det_by_vibsdQ=json.dumps(byv), mannwhitney_ampQ1_vs_Q4=float(lo_hi)))
    n2t = pd.DataFrame(out_rows)
    n2t.to_csv(HERE / "judge03_e1_host_intensity.csv", index=False)
    n2["table"] = n2t.to_dict("records")
    RES["S8_N2"] = n2
    TIMING["S8"] = time.monotonic() - t
    log("S8 N2", n2["file_sha_matches_manifest"])
    for r in out_rows:
        log("   ", r["split"], r["family"], r["level"], r["t0"], "det", round(r["detect_mean"], 3), "ρ_amp", round(r["spearman_amp"], 2), f"p={r['p_amp']:.2g}",
            "ρ_vsd", round(r["spearman_vib_sd"], 2), f"p={r['p_vib_sd']:.2g}", r["det_by_ampQ"])

    # ------------------------------------------------------------------ S10 (N3) 전류 배율 스트레스 오경보 × 원래 운전 강도
    t = time.monotonic()
    ds = pd.read_csv(YEJUN / "analysis/press_dayshift/v2_current_scale.csv")
    n3 = {}
    for s, m in models.items():
        test = D.inputs_only(splits[s]["test"])
        q, sg = prep(test)
        f = rec_feats(q, sg, m).set_index("record")
        ftr = feats[s][0]
        cut = float(ftr[ftr.length >= 17].amp.quantile(.75))
        hi_ = (f.length >= 17) & (f.amp >= cut)
        for k in (1.05, 1.2, 1.5):
            g = test.copy()
            g[S[2]] = g[S[2]].astype(float) * k
            al = m.predict(g, .01).groupby("record_id").alarm.max()
            kk, nn = int(al[hi_.reindex(al.index).to_numpy()].sum()), int(hi_.sum())
            k0, n0 = int(al.sum()) - kk, len(al) - nn
            saved = int(ds[ds.split_id.eq(s) & np.isclose(ds.k, k) & np.isclose(ds.alpha, .01)].normal_notified_segments.iloc[0])
            n3[f"{s}_{k}"] = dict(alerted=int(al.sum()), matches_dayshift=int(al.sum()) == saved, amp_ge_train_q75=(kk, nn), rest=(k0, n0),
                                  fisher_greater=fisher(kk, nn, k0, n0) if nn and n0 else np.nan, cut=cut)
    RES["S10_N3_current_scale_by_intensity"] = n3
    TIMING["S10"] = time.monotonic() - t
    log("S10 N3", {k: (v["alerted"], v["matches_dayshift"], v["amp_ge_train_q75"], v["rest"], f"{v['fisher_greater']:.2g}") for k, v in n3.items()})

    # ------------------------------------------------------------------ S9 문서 확인(해석 문장·번호 체계·그림)
    docs = {p: (YEJUN / p).read_text(encoding="utf-8") for p in ("press_guard/README.md", "press_guard/OPERATIONS.md", "analysis/press_evidence/README.md",
                                                                "analysis/press_selection/README.md", "analysis/press_supplement/README.md", "analysis/press_dayshift/README.md")}
    ins = (GUARD / "insights.py").read_text(encoding="utf-8")

    def has(pat):
        return {p: bool(re.search(pat, t)) for p, t in docs.items() if re.search(pat, t)}
    RES["S9_docs"] = dict(
        shap_or_row_permutation_reason=has(r"SHAP|행 순열|permutation"),
        sensor_rank_statement=has(r"AI2\s*[≫>]|센서 순위|전류\s*≫|전류가 가장"),
        univariate_vs_model_rank=has(r"단변량|AUROC.*AI1|AI1.*AUROC"),
        word_interaction=has(r"상호작용"),
        fmax_no_product_interaction=has(r"곱 상호작용|OR 결합|곱셈"),
        near_miss_ids_relative_note=bool(re.search(r"상대 번호|분할 안 번호|평가 구간 안 번호|relative id", ins + "".join(docs.values()))),
        figures=sorted(p.name for p in OUT.glob("fig_*_v2.png")),
        position_vibration_figure=any("position_vibration" in p.name or "interaction" in p.name for p in OUT.glob("fig_*.png")))
    nmv = pd.read_csv(OUT / "near_miss_v2.csv")
    RES["S9_docs"]["near_miss_B_top3_records(file ids)"] = nmv[nmv.split.eq("B")].sort_values("ratio_to_threshold", ascending=False).record.head(3).tolist()

    after = snapshot()
    pyc_after = sorted(str(p.relative_to(YEJUN)) for p in YEJUN.rglob("__pycache__"))
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    RES["write_check"] = dict(files_hashed=len(before), changed=changed, pycache_before=pyc_before, pycache_after=pyc_after)
    RES["timing_s"] = {k: round(v, 1) for k, v in TIMING.items()}
    RES["elapsed_s"] = round(time.monotonic() - T0, 1)
    (HERE / "judge03_verify.json").write_text(json.dumps(D.to_jsonable(RES), ensure_ascii=False, indent=1), encoding="utf-8")
    log("쓰기 확인", len(before), "개 파일, 바뀐 파일", changed, "__pycache__", pyc_after == pyc_before)
    log("완료", RES["elapsed_s"], "초")


if __name__ == "__main__":
    main()
