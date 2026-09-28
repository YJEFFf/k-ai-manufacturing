"""평가관 03 사이클2 3회차 검수(영향요인·오류분석, 15점) — 2회차 R2-01~R2-06 완료 기준을 원본 CSV·동결 v2·커밋 코드로 다시 계산한다.

    cd yejun
    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
        analysis/press_rubric_review/cycle2/round3/judge03_verify.py > analysis/press_rubric_review/cycle2/round3/judge03_verify.log 2>&1

읽기 전용 검수다. 쓰기는 이 폴더의 judge03_* 파일뿐이다. insights.py의 함수(fp_intensity, fn_intensity, error_condition_summary 등)는
부르지 않는다. 같은 정의를 여기서 따로 구현해 팀 산출물과 대조한다. N1~N6은 남은 부족분을 가리기 위한 검수용 사후 계산이며 성능 근거가 아니다.
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
from statsmodels.stats.contingency_tables import StratifiedTable

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
GUARD = YEJUN / "press_guard"
OUT = GUARD / "outputs"
ART = GUARD / "artifacts"
EVID = YEJUN / "analysis" / "press_evidence"
sys.path.insert(0, str(GUARD))
from model import GuardModel, D, ALPHAS, layout, alert_units  # noqa: E402
from press.calibrate import conformal_p, segment_max  # noqa: E402
from press.scores import ExpTail  # noqa: E402

T0 = time.monotonic()
S = D.SENSORS
RES: dict = {}
TIMING: dict = {}


def log(*a):
    print(f"[{time.monotonic() - T0:6.1f}s]", *a, flush=True)


def cp(k, n):
    """Clopper–Pearson 양측 95%(팀과 같은 공식, 소수 k도 그대로 넣는다)."""
    if n == 0:
        return [np.nan, np.nan]
    lo = 0.0 if k <= 0 else float(stats.beta.ppf(.025, k, n - k + 1))
    hi = 1.0 if k >= n else float(stats.beta.ppf(.975, k + 1, n - k))
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


def rec_feats(q, seg):
    """기록구간 특징(모델과 무관한 것만): 길이, 진동 SD(두 센서 합성), 센서별 SD, 전류 진폭(√2×평균 제거 RMS)."""
    v = q[S[:2]].to_numpy(float)
    cur = q[S[2]].to_numpy(float)
    rows = []
    for r in np.unique(seg):
        i = np.flatnonzero(seg == r)
        c = cur[i]
        rows.append(dict(record=int(r), length=len(i),
                         vib_sd=float(np.sqrt(v[i, 0].var(ddof=1) + v[i, 1].var(ddof=1))) if len(i) > 1 else np.nan,
                         ai0_sd=float(v[i, 0].std(ddof=1)) if len(i) > 1 else np.nan, ai1_sd=float(v[i, 1].std(ddof=1)) if len(i) > 1 else np.nan,
                         amp=float(np.sqrt(2 * np.mean((c - c.mean()) ** 2)))))
    return pd.DataFrame(rows)


def bh(p):
    """Benjamini–Hochberg q값."""
    p = np.asarray(p, float)
    order = np.argsort(p)
    q = np.empty_like(p)
    m = len(p)
    prev = 1.0
    for rank, i in reversed(list(enumerate(order, start=1))):
        prev = min(prev, p[i] * m / rank)
        q[i] = prev
    return q


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
    models = {s: GuardModel.load(ART / f"guard_{s}.json") for s in "AB"}
    splits = {s: D.split_normal(normal, seg_all, s) for s in "AB"}
    metrics = pd.read_csv(OUT / "metrics.csv")

    # ------------------------------------------------------------------ S1 재추론(주 지표가 그대로인가)
    t = time.monotonic()
    s1 = {}
    for s, m in models.items():
        for a in ALPHAS:
            pn, pa = m.predict(splits[s]["test"], a), m.predict(abnormal, a)
            got = dict(tp=int(pa.alarm.sum()), fp=int(pn.alarm.sum()), fn=int((pa.alarm == 0).sum()),
                       normal_notified_segments=int(pn.groupby("record_id").alarm.max().sum()),
                       abnormal_notified_segments=int(pa.groupby("record_id").alarm.max().sum()))
            saved = metrics[metrics.split.eq(s) & metrics.model.eq("guard_v2") & metrics.alpha.eq(a)].iloc[0]
            got["matches_metrics_csv"] = all(int(saved[k]) == v for k, v in got.items())
            s1[f"{s}_{a}"] = got
    RES["S1_recount"] = s1
    TIMING["S1"] = time.monotonic() - t
    log("S1", {k: v["matches_metrics_csv"] for k, v in s1.items()})

    # ------------------------------------------------------------------ S2 R2-01 운전 강도·블록별 조건부 오경보율(독립 적합 5개)
    t = time.monotonic()
    fits = {"frozen_A": (models["A"], 480, 600), "frozen_B": (models["B"], 420, 600)}
    for end in (180, 240, 300, 360, 420):
        tr = normal[seg_all < end]; ca = normal[(seg_all >= end) & (seg_all < end + 120)]
        fits[f"rolling_{end + 120}_{end + 179}"] = (GuardModel.fit(tr, ca, split=f"judge_train_to_{end}"), end + 120, end + 180)
    seen, ev = {}, []
    ident = {}
    for name, (mm, lo, hi) in fits.items():
        key = tuple(np.round(np.sort(mm.cal), 12))
        if key in seen:
            ident[name] = seen[key]
            continue
        seen[key] = name
        mask = (seg_all >= lo) & (seg_all < hi)
        frame = normal[mask]
        rid = seg_all[mask]
        q, sg = prep(frame)
        f = rec_feats(q, sg)
        f["absolute"] = [int(rid[np.flatnonzero(sg == r)[0]]) for r in f.record]
        for a in ALPHAS:
            al = mm.predict(frame, a).groupby("record_id").alarm.max()
            ev.append(f.assign(model=name, alpha=a, fa=f.record.map(al).fillna(0).astype(int).to_numpy()))
    ev = pd.concat(ev, ignore_index=True)
    base = ev[np.isclose(ev.alpha, .01)]
    amp_q = base[base.length >= 17].amp.quantile([.25, .5, .75]).to_numpy()
    vsd_q = base.vib_sd.dropna().quantile([.25, .5, .75]).to_numpy()
    qb, sgb = prep(splits["B"]["train"])
    fb = rec_feats(qb, sgb)
    b_q75 = float(fb[fb.length >= 17].amp.quantile(.75))
    mine = []
    for a in ALPHAS:
        g = ev[np.isclose(ev.alpha, a)].copy()
        g["amp_quartile"] = np.where(g.length < 17, "짧은 기록(<17)", pd.cut(g.amp, [-np.inf, *amp_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str))
        g["vib_sd_quartile"] = pd.cut(g.vib_sd, [-np.inf, *vsd_q, np.inf], labels=["Q1", "Q2", "Q3", "Q4"]).astype(str)
        g["block"] = (g.absolute // 60 * 60).astype(str) + "~" + (g.absolute // 60 * 60 + 59).astype(str)
        tk, tn = int(g.fa.sum()), len(g)
        for cond in ("amp_quartile", "vib_sd_quartile", "block"):
            for v, gg in g.groupby(cond):
                k, n = int(gg.fa.sum()), len(gg)
                lo_, hi_ = cp(k, n)
                mine.append(dict(alpha=a, condition=cond, value=str(v), false_alarms=k, denominator=n, ci_low=lo_, ci_high=hi_,
                                 lift=(k / n) / (tk / tn) if tk else np.nan, fisher_p_greater=fisher(k, n, tk - k, tn - n) if n < tn else np.nan))
        u = g.groupby("absolute").agg(fa=("fa", "max"), amp=("amp", "first"), length=("length", "first"))
        for lab, cut in (("평가 분포 q75", amp_q[2]), ("B 정상 학습 q75", b_q75)):
            hi_m = (u.length >= 17) & (u.amp >= cut)
            k1, n1 = int(u[hi_m].fa.sum()), int(hi_m.sum()); k0, n0 = int(u[~hi_m].fa.sum()), int((~hi_m).sum())
            lo_, hi_ = cp(k1, n1)
            mine.append(dict(alpha=a, condition="amp_high", value=lab, false_alarms=k1, denominator=n1, ci_low=lo_, ci_high=hi_,
                             lift=(k1 / n1) / ((k1 + k0) / (n1 + n0)) if k1 + k0 else np.nan, fisher_p_greater=fisher(k1, n1, k0, n0), rest=f"{k0}/{n0}"))
    mine = pd.DataFrame(mine)
    team = pd.read_csv(OUT / "fp_intensity_v2.csv")
    team["value_key"] = np.where(team.condition.eq("amp_high"), np.where(team.value.str.contains("B 정상 학습"), "B 정상 학습 q75", "평가 분포 q75"), team.value.astype(str))
    diffs, unmatched = [], []
    for r in mine.itertuples():
        tt = team[np.isclose(team.alpha, r.alpha) & team.condition.eq(r.condition) & team.value_key.eq(r.value)]
        if len(tt) != 1:
            unmatched.append((r.alpha, r.condition, r.value))
            continue
        tt = tt.iloc[0]
        same_counts = (int(tt.false_alarms), int(tt.denominator)) == (r.false_alarms, r.denominator)
        d = max(abs(tt.ci_low - r.ci_low), abs(tt.ci_high - r.ci_high), 0 if np.isnan(r.lift) and np.isnan(tt.lift) else abs(tt.lift - r.lift),
                0 if np.isnan(r.fisher_p_greater) and np.isnan(tt.fisher_p_greater) else abs(tt.fisher_p_greater - r.fisher_p_greater))
        diffs.append(dict(alpha=r.alpha, condition=r.condition, value=r.value, counts_match=same_counts, max_abs_diff=float(d),
                          rest_match=(str(tt.note).replace("나머지 ", "") == r.rest) if r.condition == "amp_high" else None))
    diffs = pd.DataFrame(diffs)

    def pick(a, cond, val):
        x = mine[np.isclose(mine.alpha, a) & mine.condition.eq(cond) & mine.value.eq(val)].iloc[0]
        return dict(k=int(x.false_alarms), n=int(x.denominator), ci=[round(x.ci_low, 4), round(x.ci_high, 4)], lift=round(float(x.lift), 3) if pd.notna(x.lift) else None,
                    p=float(x.fisher_p_greater), rest=getattr(x, "rest", None) if isinstance(getattr(x, "rest", None), str) else None)
    s2 = dict(independent_fits=list(seen.values()), duplicate_fits=ident, evaluations_per_alpha=int(len(base)),
              amp_quartile_bounds=list(map(float, amp_q)), vib_sd_quartile_bounds=list(map(float, vsd_q)), b_train_q75=b_q75,
              team_rows=int(len(team)), mine_rows=int(len(mine)), unmatched=unmatched, all_counts_match=bool(diffs.counts_match.all()),
              max_abs_diff_ci_lift_p=float(diffs.max_abs_diff.max()), rest_all_match=bool(diffs.rest_match.dropna().all()),
              criterion=dict(a5_Bq75=pick(.05, "amp_high", "B 정상 학습 q75"), a3_Bq75=pick(.03, "amp_high", "B 정상 학습 q75"),
                             a1_Bq75=pick(.01, "amp_high", "B 정상 학습 q75"), a5_ampQ4=pick(.05, "amp_quartile", "Q4"),
                             a5_ampQ1=pick(.05, "amp_quartile", "Q1"), a5_ampQ2=pick(.05, "amp_quartile", "Q2"), a5_short=pick(.05, "amp_quartile", "짧은 기록(<17)"),
                             a5_vsdQ4=pick(.05, "vib_sd_quartile", "Q4"), a5_block_480=pick(.05, "block", "480~539")),
              team_small_sample_alpha1=bool(team[np.isclose(team.alpha, .01)].small_sample.all()),
              team_vsd_note=sorted(team[team.condition.eq("vib_sd_quartile")].note.dropna().unique().tolist()))
    RES["S2_R2_01"] = s2
    TIMING["S2"] = time.monotonic() - t
    log("S2 R2-01", s2["all_counts_match"], s2["max_abs_diff_ci_lift_p"], s2["unmatched"], s2["criterion"]["a5_Bq75"], s2["criterion"]["a5_ampQ4"])

    # ------------------------------------------------------------------ N1 운전 강도 효과가 시간 블록과 운전 상태로 설명되는가(층화)
    t = time.monotonic()
    st = pd.read_csv(EVID / "operating_states.csv")
    seg_len = pd.Series(seg_all).value_counts()
    st_ok = bool((st.set_index("record").length == seg_len.reindex(st.record).to_numpy()).all())
    state = st.set_index("record").state
    n1 = dict(state_table_rows=len(st), state_records_match_segments=st_ok)
    ev["state"] = np.where(ev.length < 17, "짧은 기록(<17)", ev.absolute.map(state).fillna("미분류"))
    ev["block"] = (ev.absolute // 60 * 60)
    ev["amp_hi_B"] = (ev.length >= 17) & (ev.amp >= b_q75)
    ev["amp_Q4"] = (ev.length >= 17) & (ev.amp > amp_q[2])
    # 상태별 오경보(동결 A·B, 독립 롤링 3겹) — press_evidence normal_alarms_by_state.csv와 대조
    nab = pd.read_csv(EVID / "normal_alarms_by_state.csv")
    grp = {"frozen_A": "동결 A", "frozen_B": "동결 B"}
    by_state, st_match = [], []
    for a in ALPHAS:
        g = ev[np.isclose(ev.alpha, a)]
        for lab, sel in (("동결 A", g.model.eq("frozen_A")), ("동결 B", g.model.eq("frozen_B")), ("독립 롤링 3겹", g.model.str.startswith("rolling")), ("합침(5적합)", pd.Series(True, index=g.index))):
            for s_, gg in g[sel].groupby("state"):
                k, n = int(gg.fa.sum()), len(gg)
                by_state.append(dict(alpha=a, group=lab, state=s_, fa=k, n=n))
                if lab != "합침(5적합)":
                    tt = nab[nab.section.eq("상태별 정상 알림") & nab.group.eq(lab) & np.isclose(nab.alpha, a) & nab.state.eq(s_)]
                    st_match.append(len(tt) == 1 and (int(tt.alerted.iloc[0]), int(tt.records.iloc[0])) == (k, n))
    by_state = pd.DataFrame(by_state)
    n1["by_state_matches_press_evidence"] = bool(all(st_match)) and len(st_match) > 0
    comb = by_state[by_state.group.eq("합침(5적합)")]
    n1["combined_by_state"] = {f"{a}": {r.state: f"{r.fa}/{r.n}" for r in comb[np.isclose(comb.alpha, a)].itertuples()} for a in ALPHAS}
    for a in (.03, .05):
        c = comb[np.isclose(comb.alpha, a)].set_index("state")
        k1, n1_ = int(c.loc["부하"].fa), int(c.loc["부하"].n)
        k0, n0 = int(c.drop("부하").fa.sum()), int(c.drop("부하").n.sum())
        n1[f"load_vs_rest_{a}"] = dict(load=f"{k1}/{n1_}", rest=f"{k0}/{n0}", ci=cp(k1, n1_), p=fisher(k1, n1_, k0, n0))
    # 진폭 효과: 블록 층화(CMH·정확 순열), 부하 상태 안 진폭 효과
    strat_rows = []
    rng = np.random.default_rng(3)
    for a in (.03, .05):
        g = ev[np.isclose(ev.alpha, a)].copy()
        for expo in ("amp_hi_B", "amp_Q4"):
            tabs, per_block = [], {}
            for b, gg in g.groupby("block"):
                x = gg[expo].to_numpy(); y = gg.fa.to_numpy()
                t2 = np.array([[int((x & (y == 1)).sum()), int((x & (y == 0)).sum())], [int((~x & (y == 1)).sum()), int((~x & (y == 0)).sum())]])
                per_block[f"{b}~{b + 59}"] = f"{t2[0, 0]}/{t2[0].sum()} 대 {t2[1, 0]}/{t2[1].sum()}"
                if t2.sum(0).min() > 0 and t2.sum(1).min() > 0:
                    tabs.append(t2)
            stt = StratifiedTable([tt.astype(float) + 0 for tt in tabs])
            cmh = stt.test_null_odds(correction=True)
            # 정확 순열(블록 안에서 노출을 섞는다): 노출 안 오경보 수
            obs = int((g[expo] & g.fa.eq(1)).sum())
            blocks = [np.flatnonzero(g.block.to_numpy() == b) for b in np.unique(g.block)]
            ex, y = g[expo].to_numpy(), g.fa.to_numpy()
            cnt = 0
            B = 20000
            for _ in range(B):
                perm = ex.copy()
                for ix in blocks:
                    perm[ix] = rng.permutation(ex[ix])
                cnt += int((perm & (y == 1)).sum()) >= obs
            strat_rows.append(dict(alpha=a, exposure=expo, unit="평가 단위(적합×구간)", per_block=per_block, mh_pooled_or=float(stt.oddsratio_pooled),
                                   cmh_p=float(cmh.pvalue), perm_p_within_block_greater=(cnt + 1) / (B + 1), observed_exposed_fa=obs))
        # 부하 상태 안에서 진폭(상태 경계 이상의 강도) 효과
        gl = g[g.state.eq("부하")]
        med = float(gl.amp.median())
        hi_l = gl.amp >= med
        k1, n1_ = int(gl[hi_l].fa.sum()), int(hi_l.sum()); k0, n0 = int(gl[~hi_l].fa.sum()), int((~hi_l).sum())
        rho = stats.spearmanr(gl.amp, gl.fa)
        strat_rows.append(dict(alpha=a, exposure="부하 상태 안 진폭 ≥ 중앙", unit="평가 단위(부하 상태)", per_block=dict(high=f"{k1}/{n1_}", low=f"{k0}/{n0}", median_amp=med),
                               mh_pooled_or=np.nan, cmh_p=np.nan, perm_p_within_block_greater=fisher(k1, n1_, k0, n0), observed_exposed_fa=k1,
                               spearman_amp_fa_in_load=float(rho.statistic), spearman_p=float(rho.pvalue)))
    n1["stratified"] = strat_rows
    # 진폭 상위 기록이 어느 블록에 있는가(고유 구간)
    u = ev[np.isclose(ev.alpha, .05)].groupby("absolute").agg(amp=("amp", "first"), length=("length", "first"), state=("state", "first"), fa=("fa", "max"))
    u["block"] = u.index // 60 * 60
    u["hiB"] = (u.length >= 17) & (u.amp >= b_q75)
    n1["unique_amp_hiB_by_block"] = {f"{b}~{b + 59}": f"{int(g.hiB.sum())}/{len(g)} (오경보 {int(g[g.hiB].fa.sum())}·{int(g[~g.hiB].fa.sum())})" for b, g in u.groupby("block")}
    n1["unique_state_by_block_load_share"] = {f"{b}~{b + 59}": f"{int(g.state.eq('부하').sum())}/{len(g)}" for b, g in u.groupby("block")}
    n1["unique_hiB_all_load"] = bool(u[u.hiB].state.eq("부하").all())
    by_state.to_csv(HERE / "judge03_fp_state.csv", index=False)
    RES["N1_fp_block_state"] = n1
    TIMING["N1"] = time.monotonic() - t
    log("N1", n1["by_state_matches_press_evidence"], n1["combined_by_state"], [(r["alpha"], r["exposure"], round(r["cmh_p"], 5) if pd.notna(r["cmh_p"]) else None, round(r["perm_p_within_block_greater"], 5)) for r in strat_rows])

    # ------------------------------------------------------------------ S3 R2-02 고장 모양 × 운전 강도 미탐(주입, 독립 구현)
    t = time.monotonic()
    fn_team = pd.read_csv(OUT / "fn_intensity_v2.csv")
    FAMS = (("vib_noise", 2.0), ("cur_noise", .1), ("cur_offset", .2), ("cur_gain", 1.15), ("cur_gain", 1.3))
    s3 = {}
    per_unit = {}
    host = {}
    fn_rows = []
    for s, m in models.items():
        test = D.inputs_only(splits[s]["test"]).reset_index(drop=True)
        for c in S:
            test[c] = pd.to_numeric(test[c], errors="coerce")
        seg = D.segments(test)
        pos, length = D.segment_positions(seg)
        units = alert_units(layout(test)[1], D.segment_positions(layout(test)[1])[0])
        s3[f"{s}_units_equal_records"] = bool(pd.Series(units).groupby(seg).nunique().max() == 1 and pd.Series(seg).groupby(units).nunique().max() == 1)
        elig_rec = np.unique(seg[length >= 30])
        mask = np.isin(seg, elig_rec) & (pos >= 10)
        q, sg = prep(test)
        f = rec_feats(q, sg).set_index("record")
        amp = f.loc[elig_rec, "amp"].to_numpy(); vsd = f.loc[elig_rec, "vib_sd"].to_numpy()
        ampq = pd.qcut(amp, 4, labels=["Q1", "Q2", "Q3", "Q4"])
        host[s] = dict(records=elig_rec, amp=amp, vsd=vsd, ampq=np.asarray(ampq.astype(str)), state=pd.Series(elig_rec + D.SPLITS[s][2]).map(state).fillna("미분류").to_numpy())
        win_rows = (pos >= 10) & (pos < 30)

        def detect(frame):
            pr = m.predict(frame, .01)
            hit = (pr.alarm.to_numpy() == 1) & win_rows
            return pd.Series(hit).groupby(seg).any().reindex(elig_rec).to_numpy(float)

        def injected(fam, lv, rng):
            out = test.copy()
            n = int(mask.sum())
            if fam == "cur_noise":
                out.loc[mask, S[2]] += lv * m.scale[2] * rng.standard_normal(n)
            elif fam == "cur_offset":
                out.loc[mask, S[2]] += lv * np.sqrt(2) * m.scale[2]
            elif fam == "vib_noise":
                for k in (0, 1):
                    out.loc[mask, S[k]] += lv * m.scale[k] * rng.standard_normal(n)
            elif fam == "cur_gain":
                x = out[S[2]].to_numpy(float)
                out[S[2]] = np.where(mask, m.mean[2] + lv * (x - m.mean[2]), x)
            return out
        for fam, lv in FAMS:
            reps = 5 if fam in ("vib_noise", "cur_noise") else 1
            det = np.mean([detect(injected(fam, lv, np.random.default_rng(r))) for r in range(reps)], axis=0)
            per_unit[(s, fam, lv)] = det
            ra = stats.spearmanr(amp, det) if det.std() > 0 else None
            row = dict(split=s, family=fam, level=lv, units=len(elig_rec), detect_mean=float(det.mean()),
                       spearman_amp=float(ra.statistic) if ra else np.nan, p_amp=float(ra.pvalue) if ra else np.nan)
            for qq in ("Q1", "Q2", "Q3", "Q4"):
                mq = host[s]["ampq"] == qq
                row[f"det_{qq}"] = float(det[mq].sum()); row[f"n_{qq}"] = int(mq.sum())
            tt = fn_team[fn_team.split.eq(s) & fn_team.family.eq(fam) & np.isclose(fn_team.level_value, lv)].iloc[0]
            row["match_team"] = bool(int(tt.units) == row["units"] and abs(tt.detect_mean - row["detect_mean"]) < 1e-12
                                     and all(abs(tt[f"detected_amp_{qq}"] - row[f"det_{qq}"]) < 1e-9 and int(tt[f"units_amp_{qq}"]) == row[f"n_{qq}"] for qq in ("Q1", "Q2", "Q3", "Q4"))
                                     and (np.isnan(row["spearman_amp"]) and np.isnan(tt.spearman_amp) or abs(tt.spearman_amp - row["spearman_amp"]) < 1e-9))
            fn_rows.append(row)
    fn_mine = pd.DataFrame(fn_rows)
    s3["all_rows_match_team"] = bool(fn_mine.match_team.all())
    s3["rows"] = fn_mine.to_dict("records")
    s3["team_has_ci_columns"] = any("ci" in c for c in fn_team.columns)
    s3["team_note"] = str(fn_team.note.iloc[0])
    s3["team_note_mentions_rng_or_e1"] = bool(re.search(r"난수|E1과 다", str(fn_team.note.iloc[0])))
    s3["team_note_mentions_same_day"] = bool(re.search(r"같은 날|의존", str(fn_team.note.iloc[0])))
    # E1 기록별 결과와 대조(같은 족, 같은 기록; 잡음 족은 난수가 다르다)
    e1m = json.loads((YEJUN / "analysis/press_supplement/e1_manifest.json").read_text(encoding="utf-8"))
    rec_path = YEJUN / "analysis/press_supplement/predictions_e1_records.csv"
    s3["e1_records_sha_matches_manifest"] = rec_path.is_file() and sha(rec_path) == e1m["local_outputs"]["predictions_e1_records.csv"]
    e1cmp = []
    if rec_path.is_file():
        er = pd.read_csv(rec_path)
        er = er[er.model.eq("guard_v2") & np.isclose(er.alpha, .01) & er["shape"].eq("step") & er.t0.eq(10)]
        for s in "AB":
            for fam, lv in FAMS:
                g = er[er.split.eq(s) & er.family.eq(fam) & np.isclose(er.level, lv)]
                d = g.groupby("record").detected_2s.mean().reindex(host[s]["records"]).to_numpy(float)
                mq = {qq: host[s]["ampq"] == qq for qq in ("Q1", "Q4")}
                rho = stats.spearmanr(host[s]["amp"], d) if np.nanstd(d) > 0 else None
                mine_det = per_unit[(s, fam, lv)]
                e1cmp.append(dict(split=s, family=fam, level=lv, e1_detect=float(np.mean(d)), judge_team_seed_detect=float(mine_det.mean()),
                                  e1_Q1=float(d[mq["Q1"]].mean()), e1_Q4=float(d[mq["Q4"]].mean()),
                                  team_seed_Q1=float(mine_det[mq["Q1"]].mean()), team_seed_Q4=float(mine_det[mq["Q4"]].mean()),
                                  e1_spearman=float(rho.statistic) if rho else np.nan, e1_p=float(rho.pvalue) if rho else np.nan,
                                  deterministic_identical=bool(np.array_equal(d, mine_det)) if fam in ("cur_offset", "cur_gain") else None))
    s3["e1_vs_team_seed"] = e1cmp
    RES["S3_R2_02"] = s3
    TIMING["S3"] = time.monotonic() - t
    log("S3 R2-02 match", s3["all_rows_match_team"], "units=records", {k: v for k, v in s3.items() if k.endswith("units_equal_records")})
    for r in e1cmp:
        log("   E1 vs 팀 난수", r["split"], r["family"], r["level"], round(r["e1_detect"], 3), round(r["judge_team_seed_detect"], 3), "Q1", round(r["e1_Q1"], 3), round(r["team_seed_Q1"], 3),
            "Q4", round(r["e1_Q4"], 3), round(r["team_seed_Q4"], 3), "ρ_E1", round(r["e1_spearman"], 3) if pd.notna(r["e1_spearman"]) else None, r["deterministic_identical"])

    # ------------------------------------------------------------------ N2 난수 민감도(진동 잡음 2σ: 5회 묶음 10개) · 교차 상호작용 검정 · 다중 비교
    t = time.monotonic()
    n2 = {"vib_noise_seed_sets": {}, "interaction_bootstrap": {}, "bh": {}}
    sweep_rows = []
    for s, m in models.items():
        test = D.inputs_only(splits[s]["test"]).reset_index(drop=True)
        for c in S:
            test[c] = pd.to_numeric(test[c], errors="coerce")
        seg = D.segments(test)
        pos, length = D.segment_positions(seg)
        elig_rec = host[s]["records"]
        mask = np.isin(seg, elig_rec) & (pos >= 10)
        win_rows = (pos >= 10) & (pos < 30)
        dets = []
        for r in range(50):
            rng = np.random.default_rng(1000 + r)
            out = test.copy()
            n = int(mask.sum())
            for k in (0, 1):
                out.loc[mask, S[k]] += 2.0 * m.scale[k] * rng.standard_normal(n)
            pr = m.predict(out, .01)
            dets.append(pd.Series((pr.alarm.to_numpy() == 1) & win_rows).groupby(seg).any().reindex(elig_rec).to_numpy(float))
        dets = np.array(dets)
        q1, q4 = host[s]["ampq"] == "Q1", host[s]["ampq"] == "Q4"
        sets = []
        for j in range(10):
            d = dets[5 * j:5 * j + 5].mean(0)
            rho = stats.spearmanr(host[s]["amp"], d)
            sets.append(dict(Q1=float(d[q1].mean()), Q4=float(d[q4].mean()), rho=float(rho.statistic), p=float(rho.pvalue)))
            sweep_rows.append(dict(split=s, seed_set=j, **sets[-1]))
        pooled = dets.mean(0)
        rho_all = stats.spearmanr(host[s]["amp"], pooled)
        by_state = {st_: f"{pooled[host[s]['state'] == st_].mean():.3f} (n={int((host[s]['state'] == st_).sum())})" for st_ in np.unique(host[s]["state"])}
        n2["vib_noise_seed_sets"][s] = dict(Q1_range=[min(x["Q1"] for x in sets), max(x["Q1"] for x in sets)], Q4_range=[min(x["Q4"] for x in sets), max(x["Q4"] for x in sets)],
                                            rho_range=[min(x["rho"] for x in sets), max(x["rho"] for x in sets)], p_range=[min(x["p"] for x in sets), max(x["p"] for x in sets)],
                                            Q4_gt_Q1_all_sets=all(x["Q4"] > x["Q1"] for x in sets),
                                            pooled50=dict(Q1=float(pooled[q1].mean()), Q4=float(pooled[q4].mean()), rho=float(rho_all.statistic), p=float(rho_all.pvalue)),
                                            pooled50_by_state=by_state)
        # 교차 상호작용: 같은 단위에서 ρ(진폭, 진동 잡음 탐지) − ρ(진폭, 오프셋 탐지)의 붓스트랩 분포
        dv, do = per_unit[(s, "vib_noise", 2.0)], per_unit[(s, "cur_offset", .2)]
        amp = host[s]["amp"]
        obs = stats.spearmanr(amp, dv).statistic - stats.spearmanr(amp, do).statistic
        rb = np.random.default_rng(11)
        boots = []
        for _ in range(4000):
            ix = rb.integers(0, len(amp), len(amp))
            if dv[ix].std() == 0 or do[ix].std() == 0:
                continue
            boots.append(stats.spearmanr(amp[ix], dv[ix]).statistic - stats.spearmanr(amp[ix], do[ix]).statistic)
        boots = np.array(boots)
        n2["interaction_bootstrap"][s] = dict(observed_diff=float(obs), ci95=[float(np.quantile(boots, .025)), float(np.quantile(boots, .975))],
                                             share_le_0=float((boots <= 0).mean()), boots=len(boots))
    ps = fn_team.dropna(subset=["p_amp"])
    qv = bh(ps.p_amp.to_numpy())
    n2["bh"] = {f"{r.split}_{r.family}_{r.level_value:g}": dict(p=float(r.p_amp), q=float(q), bonferroni=float(min(1, r.p_amp * len(ps))))
                for r, q in zip(ps.itertuples(), qv)}
    pd.DataFrame(sweep_rows).to_csv(HERE / "judge03_fn_seed_sweep.csv", index=False)
    RES["N2_fn_robustness"] = n2
    TIMING["N2"] = time.monotonic() - t
    log("N2", {s: (v["Q1_range"], v["Q4_range"], v["rho_range"], v["Q4_gt_Q1_all_sets"], v["pooled50"]) for s, v in n2["vib_noise_seed_sets"].items()})
    log("N2 교차", n2["interaction_bootstrap"])
    log("N2 BH", {k: (round(v["p"], 5), round(v["q"], 4)) for k, v in n2["bh"].items()})

    # ------------------------------------------------------------------ S4 R2-03 영향변수 절(README 수치)
    t = time.monotonic()
    si = pd.read_csv(OUT / "sensor_importance_v2.csv")
    readme = (GUARD / "README.md").read_text(encoding="utf-8")
    sec = readme.split("## 영향변수와 상호작용")[1].split("## 미탐·오경보가 몰리는 조건")[0]
    e = {"refit": {}, "explain": {}, "univariate": {}, "swap": {}}
    variants = {"full": ((0, 1, 2), True), "drop_AI0": ((1, 2), True), "drop_AI1": ((0, 2), True), "current_only": ((2,), True), "vibration_only": ((0, 1), False)}
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
            pn, pa = conformal_p(cal, score("test")), conformal_p(cal, score("abn"))
            an, aa = np.isfinite(pn) & (pn <= .01), np.isfinite(pa) & (pa <= .01)
            tp, fp, fn = int(aa.sum()), int(an.sum()), int(len(aa) - aa.sum())
            det = int(pd.Series(aa).groupby(C["abn"]["seg"]).max().sum())
            e["refit"][f"{s}_{name}"] = dict(f1=round(2 * tp / (2 * tp + fp + fn), 3), fn=fn, detected=det)
        thr = float(np.sort(m.cal)[-1])
        tl = m.tails["magnitude"]
        grid = np.linspace(0, 40, 400001)
        zstar = float(grid[np.argmax(tl(grid) > thr)])
        za = C["abn"]["z"]
        e["explain"][s] = dict(z_needed=round(zstar, 2), abnormal_rows_over=dict(zip(("AI0", "AI1", "AI2"), map(int, (za > zstar).sum(0)))),
                               p95=dict(zip(("AI0", "AI1", "AI2"), [round(float(x), 1) for x in np.nanpercentile(za, 95, axis=0)])))
        tr_raw = D.inputs_only(sp["test"]); segt = layout(tr_raw)[1]
        ab_raw = D.inputs_only(abnormal); sega = layout(ab_raw)[1]
        for i, c in enumerate(S):
            sdn = tr_raw.groupby(segt)[c].std().dropna(); sda = ab_raw.groupby(sega)[c].std().dropna()
            e["univariate"][f"{s}_{c}"] = round(float(roc_auc_score(np.r_[np.zeros(len(sdn)), np.ones(len(sda))], np.r_[sdn, sda])), 2)
        sw = si[si.method.eq("channel_swap") & si.split.eq(s)].set_index("variant")
        e["swap"][s] = {c: (float(sw.loc[f"swap_{c}"].fn), int(sw.loc[f"swap_{c}"].abnormal_detected_segments)) for c in S}
    want = {"센서 순위": r"전류\(AI2\) ≫ 상부 진동\(AI0\) > 하부 진동\(AI1\)",
            "재적합 F1": rf"F1 {e['refit']['A_current_only']['f1']:.3f}·{e['refit']['B_current_only']['f1']:.3f}\({e['refit']['A_current_only']['detected']}/21\).*{e['refit']['A_vibration_only']['f1']:.3f}·{e['refit']['B_vibration_only']['f1']:.3f}\({e['refit']['A_vibration_only']['detected']}/21\)",
            "AI0·AI1 제거 미탐": rf"44→{e['refit']['A_drop_AI0']['fn']}·31→{e['refit']['B_drop_AI0']['fn']}.*{e['refit']['A_drop_AI1']['fn']}·{e['refit']['B_drop_AI1']['fn']}",
            "채널 교체": rf"AI2 미탐 {int(e['swap']['A']['AI2_Current'][0])}·{int(e['swap']['B']['AI2_Current'][0])}행\(18/21\), AI0 {int(e['swap']['A']['AI0_Vibration'][0])}·{int(e['swap']['B']['AI0_Vibration'][0])}, AI1 {int(e['swap']['A']['AI1_Vibration'][0])}·{int(e['swap']['B']['AI1_Vibration'][0])}",
            "SHAP 이유": r"SHAP·행 순열을 쓰지 않는 이유",
            "AUROC": rf"AI1 {e['univariate']['A_AI1_Vibration']:.2f}·{e['univariate']['B_AI1_Vibration']:.2f}이 AI0 {e['univariate']['A_AI0_Vibration']:.2f}·{e['univariate']['B_AI0_Vibration']:.2f}",
            "문턱 z": rf"A {e['explain']['A']['z_needed']:.2f}·B {e['explain']['B']['z_needed']:.2f}",
            "넘는 행": rf"AI0 {e['explain']['A']['abnormal_rows_over']['AI0']}·{e['explain']['B']['abnormal_rows_over']['AI0']}, AI1 {e['explain']['A']['abnormal_rows_over']['AI1']}·{e['explain']['B']['abnormal_rows_over']['AI1']}, 전류 {e['explain']['A']['abnormal_rows_over']['AI2']}·{e['explain']['B']['abnormal_rows_over']['AI2']}",
            "p95": rf"AI0 {e['explain']['A']['p95']['AI0']}, AI1 {e['explain']['A']['p95']['AI1']}",
            "전류 AUROC": rf"AUROC {e['univariate']['A_AI2_Current']:.2f}·{e['univariate']['B_AI2_Current']:.2f}",
            "fmax 곱 항 없음": r"곱 상호작용 항은 없다",
            "상호작용 네 개": r"① 위치 × 진동 수준.*② 진동–전류 진폭 결합.*③ 고장 모양 × 운전 강도.*④ 오경보 × 운전 강도"}
    e["readme_section_checks"] = {k: bool(re.search(v, sec, re.S)) for k, v in want.items()}
    sup = (YEJUN / "analysis/press_supervised/README.md").read_text(encoding="utf-8")
    e["supervised_f1_0994_in_source"] = "0.994" in sup
    RES["S4_R2_03"] = e
    TIMING["S4"] = time.monotonic() - t
    log("S4 R2-03", e["readme_section_checks"], e["refit"], e["explain"], e["univariate"])

    # ------------------------------------------------------------------ S5 R2-04 그림(분모·α·문턱이 표와 같은가)
    t = time.monotonic()
    crec = pd.read_csv(OUT / "coupling_records_v2.csv")
    cnt = {s: (int(((crec.split == s) & (crec.subset == "normal_test")).sum()), int(((crec.split == s) & (crec.subset == "abnormal")).sum())) for s in "AB"}
    from serve import score_threshold  # noqa: E402
    thrB = score_threshold(models["B"].cal, .01)
    figs = sorted(p.name for p in OUT.glob("fig_*_v2.png"))
    fman = {k: v for k, v in man.get("outputs", {}).items()} if isinstance(man.get("outputs"), dict) else {}
    RES["S5_R2_04"] = dict(coupling_counts=cnt, expected_in_title="A 96·14, B 145·14", B_alpha1_score_threshold=round(thrB, 2), figures=figs,
                           position_vibration_figure=(OUT / "fig_position_vibration_v2.png").is_file(),
                           figure_hashes_in_manifest={f: (f in json.dumps(man)) for f in figs},
                           intensity_bar_figure=any("intensity" in f for f in figs))
    TIMING["S5"] = time.monotonic() - t
    log("S5 R2-04", RES["S5_R2_04"])

    # ------------------------------------------------------------------ S6 R2-05 요약표 12행: 인용 행 = 조건을 만족하는 행 전체, 값 재현, CI·lift
    t = time.monotonic()
    sm = pd.read_csv(OUT / "error_condition_summary_v2.csv")

    def lines(path, mask):
        return sorted(int(i) + 2 for i in np.flatnonzero(np.asarray(mask, bool)))

    def parse(src):
        """'경로:행,행-행; 경로:행' → {경로: 정렬된 행}. 같은 경로가 두 번 나오면 합친다."""
        out: dict = {}
        for part in [x.strip() for x in str(src).split(";")]:
            path, spec = part.rsplit(":", 1)
            ln = out.setdefault(path, [])
            for tok in spec.split(","):
                if "-" in tok:
                    a, b = map(int, tok.split("-")); ln += list(range(a, b + 1))
                else:
                    ln.append(int(tok))
        return [(p, sorted(v)) for p, v in out.items()]
    F = {n: pd.read_csv(OUT / n) for n in ("position_vibration_misses_v2.csv", "fn_intensity_v2.csv", "fp_intensity_v2.csv", "fp_events_v2.csv", "near_miss_corr_v2.csv", "robustness_v2.csv")}
    e1s = pd.read_csv(YEJUN / "analysis/press_supplement/e1_summary.csv")
    sel = pd.read_csv(YEJUN / "analysis/press_selection/fp_mitigation_injection_v2.csv")
    dsh = pd.read_csv(YEJUN / "analysis/press_dayshift/v2_current_scale.csv")
    pv, fnt, fpi, fpe, nmc, rb = (F[n] for n in ("position_vibration_misses_v2.csv", "fn_intensity_v2.csv", "fp_intensity_v2.csv", "fp_events_v2.csv", "near_miss_corr_v2.csv", "robustness_v2.csv"))

    def e1mask(fam, lv, t0):
        return e1s.family.eq(fam) & np.isclose(e1s.level, lv) & e1s.t0.eq(t0) & e1s.model.eq("guard_v2") & np.isclose(e1s.alpha, .01) & e1s["shape"].eq("step")

    def e1miss(fam, lv, t0, s):
        r = e1s[e1mask(fam, lv, t0) & e1s.split.eq(s)].iloc[0]
        return int(round((1 - r.detect_rate_2s) * r.records)), int(r.records)

    def fnrow(s, fam, lv):
        return fnt[fnt.split.eq(s) & fnt.family.eq(fam) & np.isclose(fnt.level_value, lv)].iloc[0]

    def shock(s, lv):
        return sel[np.isclose(sel.alpha, .01) & sel.family.eq("vib_shock") & np.isclose(sel.level, lv) & sel.split_id.eq(s)].iloc[0]
    bq = fpi[fpi.condition.eq("amp_high") & fpi.value.str.contains("B 정상 학습")]
    ind5 = fpe.independent & np.isclose(fpe.alpha, .05)
    exp = [
        dict(cite={"press_guard/outputs/position_vibration_misses_v2.csv": lines("", pv.position.eq("0-1") & pv.vibration.isin(["vibration_normal_range", "vibration_high"]))},
             A=(6, 6), B=(6, 6), cA=20 / 36, cB=14 / 36),
        dict(cite={"press_guard/outputs/position_vibration_misses_v2.csv": lines("", pv.vibration.eq("all"))}, A=(26, 42), B=(20, 42), cA=18 / 558, cB=11 / 558),
        dict(cite={"analysis/press_supplement/e1_summary.csv": lines("", e1mask("cur_offset", .8, 0) | e1mask("cur_offset", .8, 10))},
             A=e1miss("cur_offset", .8, 0, "A"), B=e1miss("cur_offset", .8, 0, "B"), cA=0.0, cB=0.0),
        dict(cite={"analysis/press_supplement/e1_summary.csv": lines("", e1mask("cur_gain", 1.15, 10)), "press_guard/outputs/fn_intensity_v2.csv": lines("", fnt.family.eq("cur_gain") & np.isclose(fnt.level_value, 1.15))},
             A=e1miss("cur_gain", 1.15, 10, "A"), B=e1miss("cur_gain", 1.15, 10, "B"), cA=np.nan, cB=np.nan),
        dict(cite={"press_guard/outputs/fn_intensity_v2.csv": lines("", fnt.family.eq("vib_noise"))},
             A=(round(float(fnrow("A", "vib_noise", 2).units_amp_Q1 - fnrow("A", "vib_noise", 2).detected_amp_Q1), 1), int(fnrow("A", "vib_noise", 2).units_amp_Q1)),
             B=(round(float(fnrow("B", "vib_noise", 2).units_amp_Q1 - fnrow("B", "vib_noise", 2).detected_amp_Q1), 1), int(fnrow("B", "vib_noise", 2).units_amp_Q1)),
             cA=1 - fnrow("A", "vib_noise", 2).detected_amp_Q4 / fnrow("A", "vib_noise", 2).units_amp_Q4, cB=1 - fnrow("B", "vib_noise", 2).detected_amp_Q4 / fnrow("B", "vib_noise", 2).units_amp_Q4),
        dict(cite={"press_guard/outputs/fn_intensity_v2.csv": lines("", fnt.family.eq("cur_offset"))},
             A=(int(fnrow("A", "cur_offset", .2).units_amp_Q4 - fnrow("A", "cur_offset", .2).detected_amp_Q4), int(fnrow("A", "cur_offset", .2).units_amp_Q4)),
             B=(int(fnrow("B", "cur_offset", .2).units_amp_Q4 - fnrow("B", "cur_offset", .2).detected_amp_Q4), int(fnrow("B", "cur_offset", .2).units_amp_Q4)),
             cA=1 - fnrow("A", "cur_offset", .2).detected_amp_Q1 / fnrow("A", "cur_offset", .2).units_amp_Q1, cB=1 - fnrow("B", "cur_offset", .2).detected_amp_Q1 / fnrow("B", "cur_offset", .2).units_amp_Q1),
        dict(cite={"analysis/press_selection/fp_mitigation_injection_v2.csv": lines("", np.isclose(sel.alpha, .01) & sel.family.eq("vib_shock") & (np.isclose(sel.level, 4) | np.isclose(sel.level, 6)))},
             A=(int(round((1 - shock("A", 4).v2_detect_2s) * shock("A", 4).units * shock("A", 4).reps)), int(shock("A", 4).units * shock("A", 4).reps)),
             B=(int(round((1 - shock("B", 4).v2_detect_2s) * shock("B", 4).units * shock("B", 4).reps)), int(shock("B", 4).units * shock("B", 4).reps)),
             cA=1 - shock("A", 6).v2_detect_2s, cB=1 - shock("B", 6).v2_detect_2s),
        dict(cite={"press_guard/outputs/fp_intensity_v2.csv": lines("", (fpi.condition.eq("amp_high") & fpi.value.str.contains("B 정상 학습")) | (np.isclose(fpi.alpha, .05) & fpi.condition.eq("vib_sd_quartile")))},
             A=(int(bq[np.isclose(bq.alpha, .01)].false_alarms.iloc[0]), int(bq[np.isclose(bq.alpha, .01)].denominator.iloc[0])),
             B=(int(bq[np.isclose(bq.alpha, .05)].false_alarms.iloc[0]), int(bq[np.isclose(bq.alpha, .05)].denominator.iloc[0])), cA=1 / 254, cB=4 / 254),
        dict(cite={"press_guard/outputs/fp_events_v2.csv": lines("", ind5)},
             A=(int(((fpe[ind5].reasons == "magnitude") & (fpe[ind5].magnitude_sensor == "AI0_Vibration")).sum()), int(ind5.sum())),
             B=(int((fpe[ind5].alarm_rows == 1).sum()), int(ind5.sum())), cA=np.nan, cB=np.nan),
        dict(cite={"press_guard/outputs/near_miss_corr_v2.csv": lines("", nmc.split.eq("B"))}, A=(0, 0), B=(int(nmc[nmc.split.eq("B")].records_ge_0_9.iloc[0]), 180), cA=np.nan, cB=np.nan),
        dict(cite={"analysis/press_dayshift/v2_current_scale.csv": lines("", np.isclose(dsh.alpha, .01) & ((dsh.split_id.eq("A") & np.isclose(dsh.k, 1.5)) | (dsh.split_id.eq("B") & dsh.k.isin([1.0, 1.05, 1.5]))))},
             A=(0, 120), B=(17, 180), cA=np.nan, cB=3 / 180),
        dict(cite={"press_guard/outputs/robustness_v2.csv": lines("", rb.criterion.eq("conformal") & np.isclose(rb.alpha, .01) & rb.version.eq("v2") & rb.input_variant.isin(["matched", "coarse"]))},
             A=(0, 120), B=(5, 180), cA=0.0, cB=3 / 180),
    ]
    chk = []
    for i, (r, x) in enumerate(zip(sm.itertuples(), exp)):
        got = dict(parse(r.source))
        cite_ok = {p: got.get(p) == ln for p, ln in x["cite"].items()}
        extra = sorted(set(got) - set(x["cite"]))
        val = []
        for lab in "AB":
            k, n = x[lab]
            kk, nn = getattr(r, f"errors_{lab}"), getattr(r, f"denominator_{lab}")
            ok = abs(float(kk) - float(k)) < 1e-9 and int(nn) == int(n)
            if n:
                lo, hi = cp(k, n)
                ok = ok and abs(lo - getattr(r, f"ci_low_{lab}")) < 1e-9 and abs(hi - getattr(r, f"ci_high_{lab}")) < 1e-9
            comp = x[f"c{lab}"]
            tc = getattr(r, f"comparison_rate_{lab}")
            ok = ok and ((np.isnan(comp) and np.isnan(tc)) or abs(comp - tc) < 1e-9)
            lift_t = getattr(r, f"lift_{lab}")
            lift = (k / n) / comp if n and comp and np.isfinite(comp) and comp > 0 else np.nan
            ok = ok and ((np.isnan(lift) and np.isnan(lift_t)) or abs(lift - lift_t) < 1e-6)
            val.append(ok)
        chk.append(dict(line=i + 2, condition=r.condition, cite_exact=cite_ok, extra_paths=extra, values_A_B_ok=val))
    readme_rows = re.findall(r"^\| (미탐|오경보) \|", readme, re.M)
    RES["S6_R2_05"] = dict(rows=len(sm), checks=chk, all_cites_exact=all(all(c["cite_exact"].values()) and not c["extra_paths"] for c in chk),
                           all_values_ok=all(all(c["values_A_B_ok"]) for c in chk), has_ci_lift_columns=all(c in sm.columns for c in ("ci_low_A", "lift_A", "ci_low_B", "lift_B")),
                           readme_table_rows=len(readme_rows), readme_says_11_rows=bool(re.search(r"error_condition_summary_v2\.csv` \| FN·FP가 몰리는 조건 11행", readme)),
                           readme_says_12_rows=bool(re.search(r"12행 표", readme)))
    TIMING["S6"] = time.monotonic() - t
    log("S6 R2-05", RES["S6_R2_05"]["all_cites_exact"], RES["S6_R2_05"]["all_values_ok"], [(c["line"], c["cite_exact"], c["values_A_B_ok"]) for c in chk if not (all(c["cite_exact"].values()) and all(c["values_A_B_ok"]))])

    # ------------------------------------------------------------------ S7 R2-06 절대 구간 번호
    t = time.monotonic()
    nm = pd.read_csv(OUT / "near_miss_v2.csv")
    fa_team = sorted(fpe[fpe.model.eq("frozen_B") & np.isclose(fpe.alpha, .01)].record.tolist())
    RES["S7_R2_06"] = dict(fp_events_B_alpha1=fa_team,
                           near_miss_B_ratio_ge1_absolute=sorted(nm[nm.split.eq("B") & (nm.ratio_to_threshold > 1)].absolute_record.tolist()),
                           coupling_B_false_alarm_absolute=sorted(crec[crec.split.eq("B") & crec.false_alarm.astype(bool)].absolute_record.tolist()),
                           near_miss_abs_equals_rel_plus_cal_end=bool(all((g.absolute_record - g.record == D.SPLITS[s][2]).all() for s, g in nm.groupby("split"))),
                           coupling_normal_abs_ok=bool(all((g[g.subset.eq("normal_test")].absolute_record - g[g.subset.eq("normal_test")].record == D.SPLITS[s][2]).all() for s, g in crec.groupby("split"))),
                           readme_note=bool(re.search(r"B 오경보 3·41·150 = 절대 423·461·570", readme)))
    TIMING["S7"] = time.monotonic() - t
    log("S7 R2-06", RES["S7_R2_06"])

    # ------------------------------------------------------------------ N3 진동–전류 결합의 상태 안 상관(README ② 해석 점검)
    t = time.monotonic()
    n3 = {}
    cfit = pd.read_csv(OUT / "coupling_fit_v2.csv")
    for s in "AB":
        q, sg = prep(splits[s]["train"])
        f = rec_feats(q, sg)
        f["state"] = f.record.map(state)
        from press.diagnosis import sine_fit, MIN_FIT_LEN  # noqa: E402
        cur = q[S[2]].to_numpy(float)
        f["r2"] = [float(sine_fit(cur[np.flatnonzero(sg == r)])[1]) if l >= MIN_FIT_LEN else np.nan for r, l in zip(f.record, f.length)]
        ok = (f.length >= 17) & (f.r2 >= f.r2.dropna().quantile(.05)) & (f.vib_sd > 0) & (f.amp > 0)
        x, y = np.log(f.amp[ok]), np.log(f.vib_sd[ok])
        res = dict(all=dict(n=int(ok.sum()), r=float(np.corrcoef(x, y)[0, 1]), table_r=float(cfit[cfit.split.eq(s)].r.iloc[0])))
        for st_ in ("부하", "저수준"):
            mm_ = ok & f.state.eq(st_)
            res[st_] = dict(n=int(mm_.sum()), r=float(np.corrcoef(np.log(f.amp[mm_]), np.log(f.vib_sd[mm_]))[0, 1]))
        n3[s] = res
    press_guard_readme_mentions_states = bool(re.search(r"2수준|저수준|운전 상태", sec))
    n3["press_guard_readme_interaction_section_mentions_states"] = press_guard_readme_mentions_states
    summary_mentions_state = bool(sm.apply(lambda r: bool(re.search(r"2수준|저수준|부하 상태|운전 상태", " ".join(map(str, r.values)))), axis=1).any())
    n3["error_summary_mentions_operating_state"] = summary_mentions_state
    RES["N3_coupling_within_state"] = n3
    TIMING["N3"] = time.monotonic() - t
    log("N3", n3)

    # ------------------------------------------------------------------ S8 오경보 사건표 열(1회차 E3 잔여)
    RES["S8_E3_fp_events_columns"] = dict(columns=list(fpe.columns), has_r2=any(c in fpe.columns for c in ("r2", "sine_r2", "wave")),
                                          has_quartile_or_state=any(("quartile" in c) or (c in ("state", "amp_q")) for c in fpe.columns),
                                          independent_documented_in_docstring="보정값이 같은 모델은 한 번만 센다" in (GUARD / "insights.py").read_text(encoding="utf-8"))

    after = snapshot()
    pyc_after = sorted(str(p.relative_to(YEJUN)) for p in YEJUN.rglob("__pycache__"))
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    RES["head_after"] = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    RES["write_check"] = dict(files_hashed=len(before), changed=changed, pycache_before=pyc_before, pycache_after=pyc_after)
    RES["timing_s"] = {k: round(v, 1) for k, v in TIMING.items()}
    RES["elapsed_s"] = round(time.monotonic() - T0, 1)
    (HERE / "judge03_verify.json").write_text(json.dumps(D.to_jsonable(RES), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    log("쓰기 확인", len(before), "개 파일, 바뀐 파일", changed, "__pycache__ 같음", pyc_after == pyc_before)
    log("완료", RES["elapsed_s"], "초")


if __name__ == "__main__":
    main()
