"""평가관 05(창의성·차별성) cycle2 round2 — 1회차 O1~O7 완료 기준과 새 산출물을 원본·커밋 코드로 다시 계산한다.

읽기: 원본 CSV 2개(해시 확인), 저장 모델 press_guard/artifacts/{guard,probability}_{A,B}.json(outputs/manifest.json 해시 확인),
      커밋된 산출물 CSV(press_guard/outputs, analysis/press_evidence, press_selection, press_supervised, press_supplement).
쓰기: 이 폴더의 judge05_verify.json 하나. 재보정 실행(C11)과 지도학습 재실행(C13)은 시스템 임시 폴더에 쓴다.

C0  출처: HEAD, 모델·확률 보정기·원본 해시, 미커밋 파일
C1  주 수치 재현(α 1·3·5%)
C2  AR(2) 특성근
C3  A/B 명목 대비 실현 곡선 ↔ press_evidence/calibration_curve.csv
C4  O1(a) 시간순 5겹 재적합 → k=1~12 겹별·합산 ↔ rolling_calibration_curve.csv, 90% 예측 구간
C5  O1(b) 보정 조건부 Beta와 사후 95% ↔ workload_v2.csv
C6  O7 수락 한도: Beta-Binomial 95백분위, 정상 거부 확률 ↔ monitor.alert_limit
C7  O3 결합 규칙 5종(α 1·3·5%) ↔ press_selection/combination_rules.csv
C8  O2 라벨 없는 환산 ↔ label_free_alert_probability_v2.csv
C8b O2 확률 층: 상한 121, 21겹 교차 적합 Brier·ECE ↔ probability_eval_v2.csv, 경보와 확률의 정합(경보 행 중 LR<1)
C8c SBB "보수적 상한" 문장의 타당성: conformal 알림 사건(p=1/121)에서 P(이상|알림) 모의
C9b O4(b) 0.6 Hz 위상 시험 ↔ phase_continuity.csv
C10 O4(a) 관측 성질 ↔ observability.csv
C11 O7 recalibrate.py를 정상 0~479구간으로 실행
C12 E1 탐지 하한 재확인
C13 O5·O6 지도학습 기준선 재실행(임시 폴더) → 커밋 CSV와 바이트 비교, README 문장 대조
C14 O4(c) 판단표 FM 참조 ⊂ 고장 모드 대응표 ID
C15 O2 "p·1−p를 확률로 부르는 문장" 검사
C16 이상 진동의 주파수 성격(1 Hz 이하 비중, lag-1) ↔ 고장 모드 대응표 FM1·FM2의 "접힌 광대역" 가설, 관측 가능성 표 이상 행 해석
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/analysis/press_rubric_review/cycle2/round2/judge05_verify.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import filecmp
import json
import math
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import betaln, gammaln
from sklearn.isotonic import IsotonicRegression

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]                     # yejun/
ROOT = Y.parent
G = Y / "press_guard"
EV = Y / "analysis" / "press_evidence"
SUP = Y / "analysis" / "press_supplement"
SEL = Y / "analysis" / "press_selection"
SV = Y / "analysis" / "press_supervised"
sys.path.insert(0, str(G))
from model import GuardModel, D, alert_units, layout, load_bundle  # noqa: E402  (model이 press_submission을 경로에 넣는다)
from press.calibrate import conformal_p, segment_max  # noqa: E402

T_START = time.monotonic()
OUT: dict = {}
LOG: list[str] = []
TIMES: dict = {}


def log(msg):
    LOG.append(msg)
    print(msg, flush=True)


def tick(name, t0):
    TIMES[name] = round(time.monotonic() - t0, 1)


def bb_pmf(x, m, a, b):
    x = np.asarray(x, float)
    return np.exp(gammaln(m + 1) - gammaln(x + 1) - gammaln(m - x + 1) + betaln(x + a, m - x + b) - betaln(a, b))


def bb_quantile(q, m, a, b):
    cdf = np.cumsum(bb_pmf(np.arange(m + 1), m, a, b))
    return int(np.searchsorted(cdf, q - 1e-12))


def upper95(k, n):
    return 1.0 if k >= n else float(stats.beta.ppf(.95, k + 1, n - k))


# ---------------------------------------------------------------- C0 출처
t0 = time.monotonic()
head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
porcelain = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "yejun"], capture_output=True, text=True).stdout.splitlines()
manifest = json.loads((G / "outputs" / "manifest.json").read_text())
art_ok = {n: D.sha256_file(G / "artifacts" / n) == h for n, h in manifest["artifacts"].items()}
normal, abnormal, rep = D.load(Y / "press_submission")          # 해시·행 수가 다르면 예외
inputs_ok = {k: v["sha256"] == manifest["input_hashes"][k] for k, v in rep["files"].items()}
OUT["C0_provenance"] = dict(head=head, artifacts_match_manifest=art_ok, inputs_match_manifest=inputs_ok,
                            uncommitted_under_yejun=porcelain, note="미커밋 파일은 채점 대상이 아니다(HEAD 기준). 이 폴더의 judge05_* 는 이번 검수 산출물이다.")
assert all(art_ok.values()) and all(inputs_ok.values())
log(f"C0 HEAD {head[:7]} · 모델·확률 보정기·원본 해시 일치({', '.join(art_ok)}) · 미커밋 {len(porcelain)}건")

seg_all = D.segments(normal)
models = {s: load_bundle(G / "artifacts" / f"guard_{s}.json") for s in "AB"}
assert all(m.probability is not None for m in models.values())
splits = {s: D.split_normal(normal, seg_all, s) for s in "AB"}
tick("C0", t0)


def components(model, frame):
    status, seg = layout(frame)
    clean = D.inputs_only(frame)
    for c in D.SENSORS:
        clean[c] = pd.to_numeric(clean[c], errors="coerce").where(status == "ok")
    clean = D.quantize(clean, "matched")
    comp = model.components(clean, seg)
    pos = D.segment_positions(seg)[0]
    return comp, seg, pos, alert_units(seg, pos)


# ---------------------------------------------------------------- C1 주 수치
t0 = time.monotonic()
metrics = pd.read_csv(G / "outputs" / "metrics.csv")
preds, c1 = {}, {}
for s in "AB":
    m = models[s]
    pn, pa = m.predict(splits[s]["test"], .01), m.predict(abnormal, .01)
    preds[s] = (pn, pa)
    rows = {}
    for a in (.01, .03, .05):
        an, aa = pn.p_value.le(a) & pn.p_value.notna(), pa.p_value.le(a) & pa.p_value.notna()
        tp, fp = int(aa.sum()), int(an.sum())
        fn = len(pa) - tp
        ref = metrics[(metrics.split == s) & (metrics.model == "guard_v2") & np.isclose(metrics.alpha, a)].iloc[0]
        rows[str(a)] = dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn),
                            normal_records=int(an.groupby(pn.record_id).any().sum()),
                            abnormal_records=int(aa.groupby(pa.record_id).any().sum()),
                            matches_metrics_csv=bool((tp, fp, fn) == (ref.tp, ref.fp, ref.fn)))
    c1[s] = rows
OUT["C1_main_metrics"] = c1
assert all(r["matches_metrics_csv"] for s in c1.values() for r in s.values())
log(f"C1 A α1% {c1['A']['0.01']['tp']}/{c1['A']['0.01']['fp']}/{c1['A']['0.01']['fn']} F1 {c1['A']['0.01']['f1']:.6f} · "
    f"B {c1['B']['0.01']['tp']}/{c1['B']['0.01']['fp']}/{c1['B']['0.01']['fn']} F1 {c1['B']['0.01']['f1']:.6f} (metrics.csv 일치, α 3·5%도)")

# ---------------------------------------------------------------- C2 AR(2)
c2 = {}
for s in "AB":
    c = models[s].coef
    roots = np.roots([1, -c[1], -c[2]])
    c2[s] = dict(phi=[float(c[1]), float(c[2])], modulus=float(abs(roots[0])), implied_hz=float(abs(np.angle(roots[0])) / (2 * np.pi * D.DT)))
OUT["C2_ar2"] = c2
log(f"C2 AR(2) 암시 주파수 A {c2['A']['implied_hz']:.4f} Hz |r| {c2['A']['modulus']:.4f} · B {c2['B']['implied_hz']:.4f} Hz")
tick("C1_C2", t0)


# ---------------------------------------------------------------- C3 A/B 보정 곡선
def record_minp(pred):
    return pred.groupby("record_id").p_value.min().fillna(1.0).to_numpy()


cc = pd.read_csv(EV / "calibration_curve.csv")
c3 = {}
for s in "AB":
    mp = record_minp(preds[s][0])
    n_cal = len(models[s].cal)
    got = [int((mp <= k / (n_cal + 1) + 1e-12).sum()) for k in range(1, 13)]
    ref = cc[cc.split == s].sort_values("k").alerted_records.tolist()
    c3[s] = dict(n_records=len(mp), alerted_by_k=got, matches_evidence=got == ref)
OUT["C3_calibration_AB"] = c3
assert all(v["matches_evidence"] for v in c3.values())
log(f"C3 A/B 곡선이 calibration_curve.csv와 일치: A {c3['A']['alerted_by_k']} B {c3['B']['alerted_by_k']}")

# ---------------------------------------------------------------- C4 O1(a) 시간순 5겹 보정 곡선
t0 = time.monotonic()
rolling_ref = pd.read_csv(G / "outputs" / "rolling.csv")
rc = pd.read_csv(EV / "rolling_calibration_curve.csv")
folds, fold_minp = [], {}
for end in (180, 240, 300, 360, 420):
    tr = normal[seg_all < end].reset_index(drop=True)
    ca = normal[(seg_all >= end) & (seg_all < end + 120)].reset_index(drop=True)
    te = normal[(seg_all >= end + 120) & (seg_all < end + 180)].reset_index(drop=True)
    mdl = GuardModel.fit(tr, ca, split=f"train_to_{end}")
    name = f"normal_{end + 120}_{end + 179}"
    fold_minp[name] = record_minp(mdl.predict(te, .01))
    same = [s for s in "AB" if np.array_equal(models[s].cal, mdl.cal) and np.array_equal(models[s].coef, mdl.coef)]
    for a in (.01, .03, .05):
        got = int((fold_minp[name] <= a).sum())
        ref = rolling_ref[(rolling_ref.split == name) & (rolling_ref.model == "guard_v2") & np.isclose(rolling_ref.alpha, a)].iloc[0]
        folds.append(dict(fold=name, alpha=a, alerted=got, ref=int(ref.normal_notified_segments), match=got == int(ref.normal_notified_segments),
                          same_as_frozen=same))
assert all(f["match"] for f in folds), folds
curve, mism = [], []
rng = np.random.default_rng(0)
for k in range(1, 13):
    per = {f: int((mp <= k / 121 + 1e-12).sum()) for f, mp in fold_minp.items()}
    pooled = sum(per.values())
    far = rng.beta(k, 121 - k, size=(200000, 5))
    sims = rng.binomial(60, far).sum(1)
    lo, hi = (int(v) for v in np.percentile(sims, [5, 95]))
    ref_p = rc[(rc.fold == "합산(5겹)") & (rc.k == k)].iloc[0]
    for f, v in per.items():
        r = rc[(rc.fold == f) & (rc.k == k)].iloc[0]
        if int(r.alerted) != v:
            mism.append((f, k, v, int(r.alerted)))
    per_lo, per_hi = (int(v) for v in stats.betabinom(60, k, 121 - k).ppf([.05, .95]))
    curve.append(dict(k=k, nominal=k / 121, per_fold=per, pooled=pooled, pooled_pi90=[lo, hi], within=bool(lo <= pooled <= hi),
                      committed_pooled=int(ref_p.alerted), committed_pi90=[int(ref_p.pi90_low), int(ref_p.pi90_high)],
                      per_fold_bb90=[per_lo, per_hi], per_fold_above=[f for f, v in per.items() if v > per_hi],
                      per_fold_below=[f for f, v in per.items() if v < per_lo]))
OUT["C4_O1a_rolling_curve"] = dict(folds=folds, curve=curve, per_fold_mismatch_vs_committed=mism,
                                   all_pooled_match=all(c["pooled"] == c["committed_pooled"] for c in curve),
                                   all_pi90_match=all(c["pooled_pi90"] == c["committed_pi90"] for c in curve),
                                   all_within=all(c["within"] for c in curve))
log("C4 O1(a) 시간순 5겹 합산: " + ", ".join(f"k={c['k']} {c['pooled']}/300 [{c['pooled_pi90'][0]},{c['pooled_pi90'][1]}]" for c in curve if c["k"] in (1, 3, 6, 12))
    + f" · 커밋 표와 겹별 불일치 {len(mism)}건 · 합산·구간 일치 {OUT['C4_O1a_rolling_curve']['all_pooled_match']}/{OUT['C4_O1a_rolling_curve']['all_pi90_match']}"
    + f" · 모든 k 구간 안 {OUT['C4_O1a_rolling_curve']['all_within']} · 겹별 위로 벗어남 {sum(len(c['per_fold_above']) for c in curve)}건, 아래 {sum(len(c['per_fold_below']) for c in curve)}건")
tick("C3_C4", t0)

# ---------------------------------------------------------------- C5 O1(b) 배치 문턱의 오경보율
wl = pd.read_csv(G / "outputs" / "workload_v2.csv")
c5 = {}
for s, (x_obs, m_eval) in {"A": (0, 120), "B": (3, 180)}.items():
    n = len(models[s].cal)
    rows = {}
    for a in (.01, .03, .05):
        l = math.floor(a * (n + 1) + 1e-9)
        xa = int((record_minp(preds[s][0]) <= a).sum())
        prior, post = stats.beta(l, n + 1 - l), stats.beta(l + xa, n + 1 - l + m_eval - xa)
        w = wl[(wl.split_id == s) & (wl.model == "guard_v2") & np.isclose(wl.alpha, a)].iloc[0]
        U = float(w.units_per_elapsed_hour) * 8
        rows[str(a)] = dict(l=l, prior_q95=float(prior.ppf(.95)), p_far_gt_alpha=float(prior.sf(a)), eval_alerted=xa,
                            posterior_q95=float(post.ppf(.95)), alerts8h_cp=U * upper95(xa, m_eval), alerts8h_post95=U * float(post.ppf(.95)),
                            matches_workload=bool(np.isclose(post.ppf(.95), w.posterior95_rate) and np.isclose(prior.sf(a), w.far_conditional_p_exceeds_alpha)
                                                  and np.isclose(U * post.ppf(.95), w.posterior95_alerts_per_8h_elapsed)))
    c5[s] = rows
OUT["C5_O1b_conditional_far"] = c5
assert all(r["matches_workload"] for v in c5.values() for r in v.values())
log(f"C5 O1(b) α1%: P(실제>1%)={c5['A']['0.01']['p_far_gt_alpha']:.3f}, Beta(1,120) 95% {c5['A']['0.01']['prior_q95']:.4f} · 사후 95% A {c5['A']['0.01']['posterior_q95']:.4f}·B {c5['B']['0.01']['posterior_q95']:.4f}"
    f" · 8시간 A {c5['A']['0.01']['alerts8h_post95']:.0f}(CP {c5['A']['0.01']['alerts8h_cp']:.0f})·B {c5['B']['0.01']['alerts8h_post95']:.0f}(CP {c5['B']['0.01']['alerts8h_cp']:.0f}) — workload_v2.csv 일치")

# ---------------------------------------------------------------- C6 O7 수락 한도
from monitor import alert_limit, beta_params  # noqa: E402

c6 = {}
for a in (.01, .03, .05):
    n, m = 120, 60
    l = math.floor(a * (n + 1) + 1e-9)
    lim_binom = int(stats.binom.ppf(.95, m, l / (n + 1)))
    lim_bb = bb_quantile(.95, m, l, n + 1 - l)
    c6[str(a)] = dict(l=l, binomial_limit_old=lim_binom, betabinom_limit=lim_bb, code_limit=alert_limit(a, n, m),
                      reject_old_exact=float(bb_pmf(np.arange(lim_binom + 1, m + 1), m, l, n + 1 - l).sum()),
                      reject_new_exact=float(bb_pmf(np.arange(lim_bb + 1, m + 1), m, l, n + 1 - l).sum()))
OUT["C6_O7_acceptance"] = c6
assert all(v["code_limit"] == v["betabinom_limit"] for v in c6.values())
log("C6 O7 수락 한도(보정 120·수락 60): " + ", ".join(
    f"α{a} {v['binomial_limit_old']}→{v['betabinom_limit']}(코드 {v['code_limit']}), 정상 거부 {v['reject_old_exact']:.3f}→{v['reject_new_exact']:.3f}" for a, v in c6.items()))


# ---------------------------------------------------------------- C7 O3 결합 규칙
t0 = time.monotonic()


def fusions(comp):
    g = np.column_stack([comp["g_magnitude"], comp["g_waveform"], comp["g_dynamics"]])
    k = np.isfinite(g).sum(1)
    none = k == 0
    with np.errstate(all="ignore"):
        fmax = np.where(none, np.nan, np.nanmax(np.where(np.isfinite(g), g, -np.inf), 1))
        sg = np.where(none, np.nan, np.nansum(g, 1))
        fisher = np.where(none, np.nan, -stats.chi2.logsf(2 * np.log(10) * sg, 2 * np.maximum(k, 1)) / np.log(10))
        z = stats.norm.isf(np.clip(10.0 ** (-g), 1e-300, 1))
        stouffer = np.where(none, np.nan, np.nansum(z, 1) / np.sqrt(np.maximum(k, 1)))
        mean_g = sg / np.maximum(k, 1)
    return dict(tippett_fmax=fmax, fisher=fisher, stouffer=stouffer, sum=sg, mean=mean_g)


crules = pd.read_csv(SEL / "combination_rules.csv")
c7, c7_mism = {}, []
for s in "AB":
    mdl = models[s]
    cc_, cseg, cpos, cunits = components(mdl, splits[s]["cal"])
    assert np.allclose(segment_max(cc_["score"], cunits), mdl.cal)
    tc, tseg, _, _ = components(mdl, splits[s]["test"])
    ac, aseg, apos, _ = components(mdl, abnormal)
    fc, ft, fa = fusions(cc_), fusions(tc), fusions(ac)
    g_ab = np.column_stack([ac["g_magnitude"], ac["g_waveform"], ac["g_dynamics"]])
    g_te = np.column_stack([tc["g_magnitude"], tc["g_waveform"], tc["g_dynamics"]])
    rows = {}
    for a in (.01, .03, .05):
        reason_ab = np.column_stack([conformal_p(mdl.cal, g_ab[:, j]) <= a for j in range(3)]).any(1)
        reason_te = np.column_stack([conformal_p(mdl.cal, g_te[:, j]) <= a for j in range(3)]).any(1)
        for name in fc:
            cal = segment_max(fc[name], cunits)
            pt, pa_ = conformal_p(cal, ft[name]), conformal_p(cal, fa[name])
            al_t, al_a = np.isfinite(pt) & (pt <= a), np.isfinite(pa_) & (pa_ <= a)
            tp, fp = int(al_a.sum()), int(al_t.sum())
            got = dict(tp=tp, fp=fp, fn=len(al_a) - tp, normal_alerted=int(pd.Series(al_t).groupby(tseg).any().sum()),
                       fn_pos0_1=int((~al_a & (apos <= 1)).sum()), fn_pos2plus=int((~al_a & (apos >= 2)).sum()),
                       no_evidence_alarms_abnormal=int((al_a & ~reason_ab).sum()), no_evidence_alarms_normal=int((al_t & ~reason_te).sum()))
            ref = crules[(crules.split_id == s) & np.isclose(crules.alpha, a) & (crules.rule == name)]
            match = len(ref) == 1 and all(int(ref.iloc[0][k]) == v for k, v in got.items())
            if not match:
                c7_mism.append((s, a, name, got, ref.iloc[0][list(got)].to_dict() if len(ref) else None))
            rows[f"{a}_{name}"] = dict(**got, match=match)
    c7[s] = rows
remarks = crules[np.isclose(crules.alpha, .01)][["split_id", "rule", "status", "remark"]].to_dict("records")
OUT["C7_O3_fusion"] = dict(results=c7, mismatches=c7_mism, status_remark_alpha1=remarks,
                           note="사후 민감도. 성분 g = −log10(정상 꼬리 확률)이므로 fmax(g) = Tippett 최소 p 결합이다.")
log("C7 O3 결합 규칙 α1%(TP/FP/FN·정상 알림·근거 없는 이상 경보): " + " | ".join(
    f"{s} " + ", ".join(f"{k.split('_', 1)[1]} {v['tp']}/{v['fp']}/{v['fn']} n{v['normal_alerted']} r{v['no_evidence_alarms_abnormal']}"
                        for k, v in c7[s].items() if k.startswith("0.01")) for s in "AB")
    + f" · combination_rules.csv와 불일치 {len(c7_mism)}건(α 1·3·5% × 5규칙 × 2분할)")
tick("C7", t0)

# ---------------------------------------------------------------- C8 O2 라벨 없는 환산
e1 = pd.read_csv(SUP / "e1_summary.csv")
lf = pd.read_csv(G / "outputs" / "label_free_alert_probability_v2.csv")
c8_mism, c8_pick = [], {}
obs = {("A", .01): (0, 120), ("A", .03): (1, 120), ("A", .05): (1, 120), ("B", .01): (3, 180), ("B", .03): (5, 180), ("B", .05): (7, 180)}
for s in "AB":
    n = len(models[s].cal)
    for a in (.01, .03, .05):
        l = math.floor(a * (n + 1) + 1e-9)
        x, m = obs[(s, a)]
        fars = {"nominal": l / (n + 1), "calibrated95": float(stats.beta.ppf(.95, l, n + 1 - l)), "posterior95": float(stats.beta.ppf(.95, l + x, n + 1 - l + m - x))}
        tprs = {}
        for fam, lev in (("cur_noise", .1), ("cur_offset", .4), ("vib_noise", 2.0)):
            r = e1[(e1.model == "guard_v2") & (e1["shape"] == "step") & (e1.t0 == 10) & (e1.split == s) & (e1.family == fam) & np.isclose(e1.level, lev) & np.isclose(e1.alpha, a)]
            tprs[f"E1 {fam} {lev:g}"] = float(r.detect_rate_2s.iloc[0])
        tprs["대회 21/21 95% 하한"] = .05 ** (1 / 21)
        for fb, far in fars.items():
            for tb, tpr in tprs.items():
                for pi in (1e-4, 1e-3, 1e-2):
                    p = pi * tpr / (pi * tpr + (1 - pi) * far)
                    ref = lf[(lf.split == s) & np.isclose(lf.alpha, a) & (lf.far_basis == fb) & (lf.tpr_basis == tb) & np.isclose(lf.prior, pi)]
                    if len(ref) != 1 or not np.isclose(ref.p_anomaly_given_alert.iloc[0], p, rtol=0, atol=1e-12):
                        c8_mism.append((s, a, fb, tb, pi, p))
                    if s == "A" and a == .01 and tb == "E1 cur_noise 0.1":
                        c8_pick[f"{fb}_pi{pi:g}"] = p
OUT["C8_O2_label_free"] = dict(mismatches=c8_mism, A_alpha1_cur_noise01=c8_pick, rows_checked=len(lf))
assert not c8_mism
log(f"C8 O2 라벨 없는 환산 216행 재계산 일치 · A α1% 전류 잡음 0.1σ: 명목 π0.1% {c8_pick['nominal_pi0.001']:.3f}·π1% {c8_pick['nominal_pi0.01']:.3f}, "
    f"보정 95% {c8_pick['calibrated95_pi0.001']:.3f}·{c8_pick['calibrated95_pi0.01']:.3f}")

# ---------------------------------------------------------------- C8b O2 확률 층(등방 회귀 LR)
t0 = time.monotonic()


def iso_lr(cal_scores, abn_scores, cap):
    """독립 재구현: 정상 보정 행(0)·이상 행(1) 등방 회귀 → 우도비(적합 자료 odds로 나눔), 상한 cap, 하한 = 가장 작은 유한 LR."""
    s0, s1 = cal_scores[np.isfinite(cal_scores)], abn_scores[np.isfinite(abn_scores)]
    x = np.r_[s0, s1]
    y = np.r_[np.zeros(len(s0)), np.ones(len(s1))]
    iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip").fit(x, y)
    odds = y.mean() / (1 - y.mean())
    inner = iso.y_thresholds_[(iso.y_thresholds_ > 0) & (iso.y_thresholds_ < 1)]
    floor = min((inner / (1 - inner) / odds).min(), cap) if len(inner) else 1.0

    def lr(s):
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        p = iso.predict(s[ok])
        q = np.clip(p, 1e-9, 1 - 1e-9)
        v = q / (1 - q) / odds
        out[ok] = np.where(p <= 0, floor, np.minimum(v, cap))
        return out
    return lr


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    tot = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & ((p < hi) | (hi == 1))
        if k.any():
            tot += k.mean() * abs(p[k].mean() - y[k].mean())
    return float(tot)


pev = pd.read_csv(G / "outputs" / "probability_eval_v2.csv")
pconv = pd.read_csv(G / "outputs" / "probability_conversion_v2.csv")
c8b = {}
for s in "AB":
    mdl = models[s]
    cap = len(mdl.cal) + 1
    cal_scores = mdl.predict(splits[s]["cal"]).score.to_numpy()
    pt, pa = mdl.predict(splits[s]["test"]), mdl.predict(abnormal)
    st, sa, ra = pt.score.to_numpy(), pa.score.to_numpy(), pa.record_id.to_numpy()
    la, ln_ = np.full(len(sa), np.nan), []
    for r in np.unique(ra):
        keep = ra != r
        f = iso_lr(cal_scores, sa[keep], cap)
        la[~keep] = f(sa[~keep])
        ln_.append(f(st))
    ln = np.median(ln_, axis=0)
    y = np.r_[np.zeros(len(st)), np.ones(len(sa))]
    pi_rows = len(sa) / len(y)
    lr_all = np.r_[ln, la]
    p = pi_rows * lr_all / (pi_rows * lr_all + 1 - pi_rows)
    q = np.clip(np.nan_to_num(p, nan=pi_rows), 1e-9, 1 - 1e-9)
    brier, e = float(np.mean((q - y) ** 2)), ece(y, q)
    ref = pev[(pev.split == s) & (pev.cv == "21fold") & (pev.unit == "rows") & (pev.method == "calibrated_isotonic")].iloc[0]
    # 배포 보정기(저장본) 상한·하한, 모든 행 LR 최대
    deploy = mdl.probability
    lr_dep_all = deploy.likelihood_ratio(np.r_[cal_scores, st, sa])
    # 경보 행의 확률이 사전 비율보다 낮은(LR<1) 비율: 정상 평가 행(배포 보정기), 이상 행(교차 적합)
    alarm_t, alarm_a = pt.alarm.to_numpy(bool), pa.alarm.to_numpy(bool)
    lr_t_dep = deploy.likelihood_ratio(st)
    thr = float(np.sort(mdl.cal)[-1])
    c8b[s] = dict(lr_cap_saved=deploy.lr_cap, lr_floor_saved=deploy.lr_floor, max_lr_deploy_all_rows=float(np.nanmax(lr_dep_all)),
                  max_lr_oof=float(np.nanmax(la)), brier_21fold=brier, ece_21fold=e, committed_brier=float(ref.brier), committed_ece=float(ref.ece),
                  matches_committed=bool(np.isclose(brier, ref.brier, atol=1e-9) and np.isclose(e, ref.ece, atol=1e-9)),
                  lr_at_threshold_deploy=float(deploy.likelihood_ratio([thr + 1e-9])[0]),
                  committed_lr_at_threshold=float(pconv[pconv.split == s].lr_at_threshold.iloc[0]),
                  abnormal_alarm_rows=int(alarm_a.sum()), abnormal_alarm_rows_lr_lt1_oof=int((alarm_a & (la < 1)).sum()),
                  normal_alarm_rows=int(alarm_t.sum()), normal_alarm_rows_lr_lt1=int((alarm_t & (lr_t_dep < 1)).sum()),
                  normal_alarm_rows_prob_pi1pct=[float(v) for v in (0.01 * lr_t_dep[alarm_t] / (0.01 * lr_t_dep[alarm_t] + .99))])
OUT["C8b_O2_probability_layer"] = c8b
log("C8b 확률 층: " + " | ".join(
    f"{s} 저장 상한 {v['lr_cap_saved']:.0f}·모든 행 LR 최대 {v['max_lr_deploy_all_rows']:.1f}·교차 최대 {v['max_lr_oof']:.1f}, 21겹 Brier {v['brier_21fold']:.4f} ECE {v['ece_21fold']:.4f}"
    f"(커밋 {v['committed_brier']:.4f}/{v['committed_ece']:.4f}, 일치 {v['matches_committed']}), 문턱 LR {v['lr_at_threshold_deploy']:.3f}, "
    f"경보 행 중 LR<1: 이상 {v['abnormal_alarm_rows_lr_lt1_oof']}/{v['abnormal_alarm_rows']}·정상 {v['normal_alarm_rows_lr_lt1']}/{v['normal_alarm_rows']}"
    for s, v in c8b.items()))
tick("C8_C8b", t0)

# ---------------------------------------------------------------- C8c SBB 문장의 타당성(모의)
# README:105 "p값 하나의 보수적 상한(Sellke–Bayarri–Berger, 우도비 ≤ 9.3)을 쓰면 π 1%에서 8.6% 이하다".
# α=1%·보정 120단위에서 알림은 "새 단위 점수 > 보정 최대"(p = 1/121, 가장 작은 격자값) 사건이다. 교환가능한 정상에서 이 사건의 확률은 1/121,
# 이상에서 탐지율(TPR)이다. 보정 표본을 매번 새로 뽑아 알림 가운데 이상 비율을 센다.
t0 = time.monotonic()
rng = np.random.default_rng(7)
pi, tpr, n_cal, draws, per_draw = .01, .955, 120, 4000, 20000
alarm_normal, alarm_anom, ratio_by_draw = 0, 0, []
for _ in range(draws):
    far = 1.0 - rng.beta(n_cal, 1)                  # 정상 단위가 보정 최대를 넘을 확률(= 1 − max(U_1..U_n)), 분포 Beta(1, n)
    is_anom = rng.random(per_draw) < pi
    an = int((~is_anom & (rng.random(per_draw) < far)).sum())
    aa = int((is_anom & (rng.random(per_draw) < tpr)).sum())
    alarm_normal += an
    alarm_anom += aa
    if an + aa:
        ratio_by_draw.append(aa / (an + aa))
p_emp = alarm_anom / (alarm_normal + alarm_anom)
sbb_bf = -math.e * (1 / 121) * math.log(1 / 121)
sbb_p = pi * (1 / sbb_bf) / (pi * (1 / sbb_bf) + 1 - pi)
OUT["C8c_SBB_claim"] = dict(setting=dict(pi=pi, tpr=tpr, n_cal=n_cal, draws=draws, units_per_draw=per_draw),
                            p_value_at_every_alarm=1 / 121, empirical_P_anomaly_given_alarm=p_emp,
                            analytic=pi * tpr / (pi * tpr + (1 - pi) / 121), sbb_lr_bound=1 / sbb_bf, sbb_claimed_upper=sbb_p,
                            share_of_calibration_draws_exceeding_sbb_claim=float(np.mean(np.asarray(ratio_by_draw) > sbb_p)),
                            readme_label_free_same_pi=0.538493,
                            note="모든 알림의 conformal p값은 1/121로 같다. 그런데도 알림 가운데 이상 비율은 SBB '상한' 8.6%를 크게 넘는다. "
                                 "conformal 알림은 p ≤ 1/121 사건이라 우도비 상한이 121·TPR이다. SBB 보정(−e·p·ln p)은 연속 p값을 정확히 관측하고 "
                                 "대립에서 p가 Beta(ξ,1)을 따른다는 추가 가정 아래의 값이라 이 사건의 상한이 아니다.")
log(f"C8c SBB 문장: 알림 p값은 모두 1/121인데 모의 P(이상|알림) {p_emp:.3f}(해석값 {OUT['C8c_SBB_claim']['analytic']:.3f}) > SBB '상한' {sbb_p:.3f}; "
    f"보정 표본 {draws}회 중 {OUT['C8c_SBB_claim']['share_of_calibration_draws_exceeding_sbb_claim']:.1%}에서 상한을 넘음")
tick("C8c", t0)

# ---------------------------------------------------------------- C9b O4(b) 0.6 Hz 위상 시험
t0 = time.monotonic()
t_abs = pd.to_datetime(normal[D.TIME], format="mixed")
tsec = (t_abs - t_abs.iloc[0]).dt.total_seconds().to_numpy()
cur = normal[D.SENSORS[2]].to_numpy(float)
rec_codes = np.unique(seg_all)
ends, begins = [], []
for r in rec_codes[:-1]:
    a_idx, b_idx = np.flatnonzero(seg_all == r), np.flatnonzero(seg_all == r + 1)
    if len(a_idx) >= 20 and len(b_idx) >= 20:
        ends.append(a_idx[-20:]); begins.append(b_idx[:20])
ends, begins = np.array(ends), np.array(begins)
gaps = tsec[begins[:, 0]] - tsec[ends[:, -1]]


def window_phase(idx, f, t_rel=False):
    out = np.empty(len(idx))
    for i in range(len(idx)):
        t = tsec[idx[i]] - (tsec[idx[i][0]] if t_rel else 0)
        A = np.column_stack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(idx.shape[1])])
        c = np.linalg.lstsq(A, cur[idx[i]], rcond=None)[0]
        out[i] = np.arctan2(c[1], c[0])
    return out


def R(d):
    return float(np.abs(np.mean(np.exp(1j * d))))


ph_b, ph_e = window_phase(begins, .6), window_phase(ends, .6)
d06 = ph_b - ph_e
rng = np.random.default_rng(2)
null = [R(rng.permutation(ph_b) - ph_e) for _ in range(200)]
long_recs = [np.flatnonzero(seg_all == r) for r in rec_codes if (seg_all == r).sum() >= 50]
ctrl = window_phase(np.array([ix[-20:] for ix in long_recs]), .6) - window_phase(np.array([ix[:20] for ix in long_recs]), .6)
starts = window_phase(np.array([np.flatnonzero(seg_all == r)[:20] for r in rec_codes if (seg_all == r).sum() >= 20]), .6, t_rel=True)
short = gaps < np.median(gaps)
pc = pd.read_csv(EV / "phase_continuity.csv")
c9b = dict(pairs=int(len(gaps)), gap_range=[float(gaps.min()), float(gaps.max())], gap_median=float(np.median(gaps)),
           R_neighbors=R(d06), null_q95_my_seed=float(np.quantile(null, .95)), R_short=R(d06[short]), R_long=R(d06[~short]),
           positive_control=dict(records=len(long_recs), R=R(ctrl)), start_phase=dict(records=int(len(starts)), R=R(starts)),
           committed=pc[["test", "pairs", "R", "null_q95"]].to_dict("records"))
c9b["matches_committed_R"] = bool(np.isclose(c9b["R_neighbors"], pc.R.iloc[1], atol=1e-9) and np.isclose(c9b["positive_control"]["R"], pc.R.iloc[0], atol=1e-9)
                                  and np.isclose(c9b["start_phase"]["R"], pc.R.iloc[5], atol=1e-9))
OUT["C9b_O4b_phase"] = c9b
log(f"C9b O4(b) 위상: 양성 대조 R {c9b['positive_control']['R']:.3f}({c9b['positive_control']['records']}기록), 이웃 {c9b['pairs']}쌍 R {c9b['R_neighbors']:.3f}"
    f"(공백 {c9b['gap_range'][0]:.2f}~{c9b['gap_range'][1]:.2f}초), 섞은 귀무 95% {c9b['null_q95_my_seed']:.3f}(커밋 {pc.null_q95.iloc[1]:.3f}), "
    f"짧은/긴 공백 {c9b['R_short']:.3f}/{c9b['R_long']:.3f}, 시작 위상 R {c9b['start_phase']['R']:.3f}({c9b['start_phase']['records']}기록) · 커밋 R 일치 {c9b['matches_committed_R']}")

# ---------------------------------------------------------------- C10 O4(a) 관측 성질
obs_t = pd.read_csv(EV / "observability.csv")
c10 = {}
for name, fr in (("normal", normal), ("abnormal", abnormal)):
    sg = D.segments(fr)
    for c in D.SENSORS:
        x = fr[c].to_numpy(float)
        same = np.r_[False, sg[1:] == sg[:-1]]
        lag1 = float(np.corrcoef(x[1:][same[1:]], x[:-1][same[1:]])[0, 1])
        ref = obs_t[(obs_t.file == name) & (obs_t.sensor == c)].iloc[0]
        c10[f"{name}/{c}"] = dict(share_negative=float((x < 0).mean()), lag1_within=lag1,
                                  matches=bool(np.isclose((x < 0).mean(), ref.share_negative) and np.isclose(lag1, ref.lag1_within)),
                                  committed_interpretation=ref.interpretation)
OUT["C10_O4a_observability"] = c10
log("C10 O4(a) 음수 비율·lag-1: " + ", ".join(f"{k} {v['share_negative']:.3f}/{v['lag1_within']:.3f}" for k, v in c10.items() if "Current" not in k)
    + f" · 커밋 표 일치 {all(v['matches'] for v in c10.values())}")
tick("C9b_C10", t0)

# ---------------------------------------------------------------- C11 O7 재보정 실행
t0 = time.monotonic()
import recalibrate  # noqa: E402

with tempfile.TemporaryDirectory(prefix="judge05r2_recal_") as tmp:
    src = Path(tmp) / "normal_0_479.csv"
    normal[seg_all < 480].to_csv(src, index=False)
    code = recalibrate.main(["--normal", str(src), "--out", str(Path(tmp) / "site.json"), "--report", str(Path(tmp) / "site_report.json")])
    report = json.loads((Path(tmp) / "site_report.json").read_text())
OUT["C11_O7_recalibrate"] = dict(exit_code=code, passed=report["passed"], units=report["units"],
                                 checks=[{k: c.get(k) for k in ("name", "value", "limit", "ok", "false_reject_rate", "power_if_rate_multiplied")} for c in report["checks"]])
log(f"C11 O7 recalibrate 종료 코드 {code}, 통과 {report['passed']}: " + "; ".join(f"{c['name']} = {c['value']} (한도 {c['limit']})" for c in report["checks"]))
tick("C11", t0)

# ---------------------------------------------------------------- C12 E1 하한
floor = pd.read_csv(SUP / "e1_detection_floor.csv")
c12 = {}
for fam in ("cur_noise", "cur_offset", "vib_noise"):
    for model_name in ("guard_v2", "baseline_v1"):
        r = e1[(e1.family == fam) & (e1["shape"] == "step") & (e1.t0 == 10) & (e1.model == model_name) & np.isclose(e1.alpha, .01)]
        ok = r.groupby("level").detect_rate_2s.min()
        lev = ok[ok >= .9].index.min() if (ok >= .9).any() else None
        ref = floor[(floor.family == fam) & (floor.model == model_name)].floor.iloc[0]
        c12[f"{fam}/{model_name}"] = dict(floor=lev, ref=ref, match=bool(lev == ref))
OUT["C12_e1_floor"] = c12
log("C12 E1 하한: " + ", ".join(f"{k} {v['floor']}" for k, v in c12.items()) + f" · 일치 {all(v['match'] for v in c12.values())}")

# ---------------------------------------------------------------- C13 O5·O6 지도학습 재실행
t0 = time.monotonic()
with tempfile.TemporaryDirectory(prefix="judge05r2_sup_") as tmp:
    proc = subprocess.run([sys.executable, str(SV / "run.py"), "--out", tmp], capture_output=True, text=True,
                          env=dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1"))
    same_bytes = {n: filecmp.cmp(Path(tmp) / n, SV / n, shallow=False) for n in ("random_rows.csv", "grouped_records.csv", "injection.csv")}
    gr = pd.read_csv(Path(tmp) / "grouped_records.csv")
    inj = pd.read_csv(Path(tmp) / "injection.csv")
sel = gr[(gr.cv == "21fold") & (gr.threshold == "conformal")]
v2f1 = {"A": c1["A"]["0.01"]["f1"], "B": c1["B"]["0.01"]["f1"]}
diffs = [float(r.f1 - v2f1[r.split]) for r in sel[sel.features == "window_plus_v2"].itertuples() if r.model in ("logistic", "hgb")]
diffs_bal = [float(r.f1 - v2f1[r.split]) for r in sel[sel.features == "window_plus_v2"].itertuples() if r.model.endswith("balanced")]
wlog = inj[(inj.features == "window") & (inj.model == "logistic_balanced") & (inj.threshold == "0.5") & (inj.family == "none")]
OUT["C13_O5_O6_supervised"] = dict(returncode=proc.returncode, csv_byte_identical=same_bytes,
                                   f1_minus_v2_unweighted_range=[min(diffs), max(diffs)], f1_minus_v2_balanced_range=[min(diffs_bal), max(diffs_bal)],
                                   weighted_logistic_window_no_injection_alarm=wlog.set_index("split").detect_rate_2s.to_dict(),
                                   table_21fold_conformal=sel[["split", "features", "model", "f1", "fn", "normal_alerted_segments", "abnormal_detected_segments"]].to_dict("records"),
                                   stdout_tail=proc.stdout.strip().splitlines()[-1:] if proc.stdout else [], stderr_tail=proc.stderr.strip().splitlines()[-3:])
log(f"C13 지도학습 재실행 코드 {proc.returncode}, CSV 바이트 동일 {same_bytes} · 창+v2 지도학습−v2 F1 {min(diffs):+.3f}~{max(diffs):+.3f}"
    f"(가중 변형 {min(diffs_bal):+.3f}~{max(diffs_bal):+.3f}) · 가중 로지스틱(창, 0.5) 무주입 경보 " + ", ".join(f"{k} {v:.1%}" for k, v in OUT['C13_O5_O6_supervised']['weighted_logistic_window_no_injection_alarm'].items()))
tick("C13", t0)

# ---------------------------------------------------------------- C14 O4(c) FM 참조
fm = pd.read_csv(EV / "failure_mode_map.csv")
dt = pd.read_csv(G / "outputs" / "decision_table_v2.csv")
refs = sorted({x for v in dt.failure_modes.dropna() for x in re.findall(r"FM\d", v)})
phys = [p for p in (G / "README.md", EV / "README.md", G / "OPERATIONS.md") if re.search(r"물리 모델로 검증(?!한 것이 아니다|하지 않)", p.read_text(encoding="utf-8"))]
OUT["C14_O4c_failure_modes"] = dict(fm_ids=fm.fm_id.tolist(), decision_table_refs=refs, all_refs_exist=set(refs) <= set(fm.fm_id),
                                    rows_have_hypothesis_and_confirmed=bool(fm.hypothesis_general_engineering.notna().all() and fm.confirmed_in_this_data.notna().all()),
                                    positive_physics_validation_claims=[str(p.relative_to(Y)) for p in phys])
log(f"C14 O4(c) 판단표 FM 참조 {refs} ⊂ {fm.fm_id.tolist()}: {OUT['C14_O4c_failure_modes']['all_refs_exist']} · '물리 모델로 검증' 긍정 문장 {len(phys)}건")

# ---------------------------------------------------------------- C15 O2 용어 검사
hits = []
for p in [G / "README.md", G / "OPERATIONS.md", G / "web" / "index.html", G / "web" / "app.js", EV / "README.md", SEL / "README.md", SV / "README.md"]:
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"1\s*[−-]\s*p", line) and "확률" in line:
            hits.append(dict(file=str(p.relative_to(Y)), line=i, negated=bool(re.search(r"확률\s*아님|확률이 아니", line))))
OUT["C15_O2_wording"] = dict(lines_with_1_minus_p_and_probability=hits, all_negated=all(h["negated"] for h in hits))
log(f"C15 '1−p'와 '확률'이 같은 줄: {len(hits)}줄, 모두 '확률 아님' 표기 {OUT['C15_O2_wording']['all_negated']}")

# ---------------------------------------------------------------- C16 이상 진동의 주파수 성격(O4 대응표·관측 가능성 표와 대조)
# 기록 20행 이상인 기록의 처음 20관측(평균 제거)으로 주기도표를 평균한다. 해상도 0.5 Hz, 1 Hz 이하 = 0.5·1.0 Hz 두 칸.
# 흰 잡음(E1 vib_noise 주입과 같은 모양)이면 1 Hz 이하 비중의 기대값은 2/10 = 0.2다.
t0 = time.monotonic()
fmm = fm.set_index("fm_id")
c16 = {}
for name, fr in (("normal", normal), ("abnormal", abnormal)):
    sg = D.segments(fr)
    for c in D.SENSORS[:2]:
        x = fr[c].to_numpy(float)
        P, lag_rec = [], []
        for r in np.unique(sg):
            idx = np.flatnonzero(sg == r)
            if len(idx) < 20:
                continue
            v = x[idx[:20]] - x[idx[:20]].mean()
            P.append(np.abs(np.fft.rfft(v)) ** 2)
            w = x[idx] - x[idx].mean()
            lag_rec.append(float(np.corrcoef(w[1:], w[:-1])[0, 1]))
        P = np.mean(P, 0)
        f = np.fft.rfftfreq(20, D.DT)
        same = np.r_[False, sg[1:] == sg[:-1]]
        xm = x - pd.Series(x).groupby(sg).transform("mean").to_numpy()
        c16[f"{name}/{c}"] = dict(records_ge20=len(lag_rec), share_power_le_1hz=float(P[(f > 0) & (f <= 1.0)].sum() / P[f > 0].sum()),
                                  lag1_record_mean_removed=float(np.corrcoef(xm[1:][same[1:]], xm[:-1][same[1:]])[0, 1]),
                                  lag1_per_record_median=float(np.median(lag_rec)),
                                  records_lag1_gt_0p5=int(np.sum(np.asarray(lag_rec) > .5)))
white = 2 / 10
obs_ab = obs_t[(obs_t.file == "abnormal") & obs_t.sensor.isin(D.SENSORS[:2])]
OUT["C16_abnormal_vibration_spectrum"] = dict(
    by_file_sensor=c16, white_noise_expected_share_le_1hz=white,
    observability_abnormal_rows=obs_ab[["sensor", "lag1_within", "interpretation"]].to_dict("records"),
    observability_abnormal_says_low_lag1=bool(obs_ab.interpretation.str.contains("이웃 표본 상관 낮음").all()),
    fm1_expected_change=fmm.loc["FM1", "expected_change_10hz"], fm2_expected_change=fmm.loc["FM2", "expected_change_10hz"],
    note="이상 진동은 1 Hz 이하 저주파 비중이 흰 잡음 기대값(0.2)의 약 3배이고 기록 안 lag-1이 높다. 대응표 FM1·FM2가 예측하는 '접힌 광대역 변화'나 "
         "E1 진동 잡음 주입(흰 잡음)과 모양이 다르다. 관측 가능성 표의 이상 행 해석('이웃 표본 상관 낮음')은 이 값과 맞지 않는다.")
log("C16 1 Hz 이하 전력 비중·평균 제거 lag-1: " + ", ".join(
    f"{k} {v['share_power_le_1hz']:.2f}/{v['lag1_record_mean_removed']:.3f}(기록 {v['records_ge20']}, lag-1>0.5 {v['records_lag1_gt_0p5']})" for k, v in c16.items())
    + f" · 흰 잡음 기대 {white:.2f} · 관측 가능성 표 이상 행 '이웃 표본 상관 낮음' 표기 {OUT['C16_abnormal_vibration_spectrum']['observability_abnormal_says_low_lag1']}")
tick("C16", t0)

OUT["timing_s"] = TIMES
OUT["elapsed_s"] = round(time.monotonic() - T_START, 1)
(HERE / "judge05_verify.json").write_text(json.dumps(D.to_jsonable(OUT), ensure_ascii=False, indent=2), encoding="utf-8")
log(f"완료 {OUT['elapsed_s']}초 (구간별 {TIMES}) → {HERE / 'judge05_verify.json'}")
