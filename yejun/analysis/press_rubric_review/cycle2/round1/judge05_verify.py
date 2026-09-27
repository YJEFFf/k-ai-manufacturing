"""평가관 05(창의성·차별성) cycle2 round1 — 커밋된 산출물·원본에서 직접 다시 계산한 검사.

읽기: 원본 CSV 2개(해시 확인), 저장 모델 press_guard/artifacts/guard_{A,B}.json(outputs/manifest.json 해시 확인),
      커밋된 산출물 CSV(press_guard/outputs, analysis/press_evidence, analysis/press_supplement).
쓰기: 이 폴더의 judge05_verify.json 하나. 재보정 실행(C11)의 모델·보고서는 시스템 임시 폴더에 쓴다.

C0  출처: HEAD, 모델·원본 해시, 미커밋 파일 목록(채점 제외 기록용)
C1  주 수치 재현: 원본 → 저장 모델 추론 → TP/FP/FN(α 1·3·5%)
C2  AR(2) 특성근 ↔ 사인 0.6 Hz
C3  A/B 명목 대비 실현 기록 경보율(k/121) ↔ press_evidence/calibration_curve.csv
C4  시간순 5겹(train.py --rolling과 같은 분할) 보정 곡선 + 보정집합 조건부 Beta-Binomial 예측 구간
C5  배치 문턱의 기록당 오경보율: Beta(l, n+1−l) 사전 → 평가 반영 사후, 8시간 알림 수 예측 구간
C6  재보정 수락 검사 (a)의 이항 한도가 정확한 귀무분포(Beta-Binomial)에서 갖는 거부 확률
C7  결합 규칙 민감도(심사 확인용, 채택 근거 아님): fmax(=Tippett 최소 p) vs Fisher vs Stouffer vs 합
C8  경보 → 이상 확률 환산(기저율 시나리오, 라벨 적합 없음)
C9  0.6 Hz 전류 진동의 기록 간 위상 일관성(제조지식 가설 검정)
C10 진동 채널의 관측 성질(부호·평균·lag-1): 10 Hz 순시값 표본인지
C11 recalibrate.py 수락 검사를 정상 0~479구간으로 실행(README 142행 재현)
C12 E1 탐지 하한 재확인(e1_summary.csv)
C9b 이웃 기록 사이 0.6 Hz 위상 연속성
C13 지도학습 기준선(press_supervised)에 불균형 가중(class_weight)을 넣은 심사 확인
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/analysis/press_rubric_review/cycle2/round1/judge05_verify.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import json
import math
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import betaln, gammaln

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]                     # yejun/
ROOT = Y.parent
G = Y / "press_guard"
EV = Y / "analysis" / "press_evidence"
SUP = Y / "analysis" / "press_supplement"
sys.path.insert(0, str(G))
from model import GuardModel, D, alert_units, layout  # noqa: E402  (model이 press_submission을 경로에 넣는다)
from press.calibrate import conformal_p, segment_max  # noqa: E402

T_START = time.monotonic()
OUT: dict = {}
LOG: list[str] = []


def log(msg):
    LOG.append(msg)
    print(msg, flush=True)


def bb_pmf(x, m, a, b):
    """Beta-Binomial(m, a, b) 확률질량."""
    x = np.asarray(x, float)
    return np.exp(gammaln(m + 1) - gammaln(x + 1) - gammaln(m - x + 1) + betaln(x + a, m - x + b) - betaln(a, b))


def bb_quantile(q, m, a, b):
    cdf = np.cumsum(bb_pmf(np.arange(m + 1), m, a, b))
    return int(np.searchsorted(cdf, q - 1e-12))


def upper95(k, n):
    return 1.0 if k >= n else float(stats.beta.ppf(.95, k + 1, n - k))


# ---------------------------------------------------------------- C0 출처
head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
porcelain = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "yejun"], capture_output=True, text=True).stdout.splitlines()
manifest = json.loads((G / "outputs" / "manifest.json").read_text())
art_ok = {n: D.sha256_file(G / "artifacts" / n) == h for n, h in manifest["artifacts"].items()}
normal, abnormal, rep = D.load(Y / "press_submission")          # 해시·행 수가 다르면 예외
inputs_ok = {k: v["sha256"] == manifest["input_hashes"][k] for k, v in rep["files"].items()}
OUT["C0_provenance"] = dict(head=head, artifacts_match_manifest=art_ok, inputs_match_manifest=inputs_ok,
                            uncommitted_under_yejun=porcelain,
                            note="미커밋 파일은 채점 대상이 아니다(HEAD 기준).")
assert all(art_ok.values()) and all(inputs_ok.values())
log(f"C0 HEAD {head[:7]} · 모델·원본 해시 일치 · 미커밋 {len(porcelain)}건")

seg_all = D.segments(normal)
models = {s: GuardModel.load(G / "artifacts" / f"guard_{s}.json") for s in "AB"}
splits = {s: D.split_normal(normal, seg_all, s) for s in "AB"}


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
log(f"C1 A α1% {c1['A']['0.01']['tp']}/{c1['A']['0.01']['fp']}/{c1['A']['0.01']['fn']} · "
    f"B {c1['B']['0.01']['tp']}/{c1['B']['0.01']['fp']}/{c1['B']['0.01']['fn']} (metrics.csv 일치)")

# ---------------------------------------------------------------- C2 AR(2)
c2, ar_csv = {}, pd.read_csv(EV / "ar2_oscillator.csv").set_index("split")
for s in "AB":
    c = models[s].coef
    roots = np.roots([1, -c[1], -c[2]])
    f = float(abs(np.angle(roots[0])) / (2 * np.pi * D.DT))
    c2[s] = dict(phi=[float(c[1]), float(c[2])], modulus=float(abs(roots[0])), implied_hz=f,
                 matches_evidence=bool(abs(f - ar_csv.loc[s, "implied_freq_hz"]) < 1e-9),
                 pure_sine_0p6_phi1=float(2 * np.cos(2 * np.pi * .6 * D.DT)))
OUT["C2_ar2"] = c2
log(f"C2 AR(2) 암시 주파수 A {c2['A']['implied_hz']:.4f} Hz |r| {c2['A']['modulus']:.4f} · B {c2['B']['implied_hz']:.4f} Hz")


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
log(f"C3 A/B 곡선 재계산이 calibration_curve.csv와 일치: A {c3['A']['alerted_by_k']} B {c3['B']['alerted_by_k']}")

# ---------------------------------------------------------------- C4 시간순 5겹 보정 곡선
rolling_ref = pd.read_csv(G / "outputs" / "rolling.csv")
folds, fold_minp, fold_cal = [], {}, {}
for end in (180, 240, 300, 360, 420):
    tr = normal[seg_all < end].reset_index(drop=True)
    ca = normal[(seg_all >= end) & (seg_all < end + 120)].reset_index(drop=True)
    te = normal[(seg_all >= end + 120) & (seg_all < end + 180)].reset_index(drop=True)
    mdl = GuardModel.fit(tr, ca, split=f"train_to_{end}")
    pn = mdl.predict(te, .01)
    name = f"normal_{end + 120}_{end + 179}"
    fold_minp[name], fold_cal[name] = record_minp(pn), len(mdl.cal)
    for a in (.01, .03, .05):
        got = int((fold_minp[name] <= a).sum())
        ref = rolling_ref[(rolling_ref.split == name) & (rolling_ref.model == "guard_v2") & np.isclose(rolling_ref.alpha, a)].iloc[0]
        folds.append(dict(fold=name, alpha=a, alerted=got, ref=int(ref.normal_notified_segments), match=got == int(ref.normal_notified_segments)))
assert all(f["match"] for f in folds), folds
curve = []
rng = np.random.default_rng(0)
for k in range(1, 13):
    per = {f: int((mp <= k / 121 + 1e-12).sum()) for f, mp in fold_minp.items()}
    pooled = sum(per.values())
    # 각 겹의 문턱 초과율 ~ Beta(k, 121−k)(교환가능성). 겹마다 독립으로 근사해 합의 예측 분포를 모의한다.
    far = rng.beta(k, 121 - k, size=(200000, 5))
    sims = rng.binomial(60, far).sum(1)
    lo, hi = np.percentile(sims, [5, 95])
    per_hi = bb_quantile(.95, 60, k, 121 - k)
    curve.append(dict(k=k, nominal=k / 121, per_fold=per, pooled=pooled, pooled_rate=pooled / 300,
                      pooled_bb90=[int(lo), int(hi)], pooled_within_bb90=bool(lo <= pooled <= hi),
                      per_fold_bb95_upper=per_hi, folds_above_bb95=[f for f, v in per.items() if v > per_hi]))
OUT["C4_rolling_calibration"] = dict(folds=folds, curve=curve, n_cal_each=list(fold_cal.values()),
                                     note="각 겹: 학습 0~end−1, 보정 end~end+119(바로 앞 120구간), 평가 다음 60구간. 5겹 평가 300구간은 서로 겹치지 않는다. "
                                          "보정 구간은 60구간씩 겹치므로 독립 근사 구간은 실제보다 약간 좁다.")
log("C4 시간순 5겹(평가 300구간) 실현 대 명목: " + ", ".join(
    f"k={c['k']} {c['pooled']}/300({c['pooled_rate']:.2%}) vs {c['nominal']:.2%} 90%[{c['pooled_bb90'][0]},{c['pooled_bb90'][1]}]" for c in curve if c["k"] in (1, 3, 6, 12)))

# ---------------------------------------------------------------- C5 배치 문턱의 오경보율(보정집합 조건부)
units_per_8h = {r.split_id: float(r.units_per_elapsed_hour) * 8 for r in pd.read_csv(G / "outputs" / "workload_v2.csv").drop_duplicates("split_id").itertuples()}
c5 = {}
for s, (x, m_eval) in {"A": (0, 120), "B": (3, 180)}.items():
    n = len(models[s].cal)
    rows = {}
    for a in (.01, .03, .05):
        l = math.floor(a * (n + 1) + 1e-9)
        xa = int((record_minp(preds[s][0]) <= a).sum())
        prior = stats.beta(l, n + 1 - l)
        post = stats.beta(l + xa, n + 1 - l + m_eval - xa)
        U = units_per_8h[s]
        rows[str(a)] = dict(l=l, alpha_grid=l / (n + 1), prior_mean=prior.mean(), prior_q05=prior.ppf(.05), prior_q95=prior.ppf(.95),
                            prior_P_far_gt_nominal_alpha=float(prior.sf(a)), prior_P_far_gt_2x_grid=float(prior.sf(2 * l / (n + 1))),
                            eval_alerted=xa, eval_records=m_eval, clopper_pearson_upper95=upper95(xa, m_eval),
                            posterior_mean=post.mean(), posterior_q95=post.ppf(.95),
                            alerts_per_8h=dict(units=U, nominal=U * l / (n + 1), prior_q95=U * prior.ppf(.95),
                                               cp_upper95=U * upper95(xa, m_eval), posterior_mean=U * post.mean(),
                                               posterior_q95=U * post.ppf(.95)))
    c5[s] = rows
OUT["C5_conditional_far"] = c5
log(f"C5 α1% 보정 조건부 Beta(1,120): 평균 {c5['A']['0.01']['prior_mean']:.4f}, 95% {c5['A']['0.01']['prior_q95']:.4f}, "
    f"P(실제>1%)={c5['A']['0.01']['prior_P_far_gt_nominal_alpha']:.3f} · B 사후 95% {c5['B']['0.01']['posterior_q95']:.4f} "
    f"(8시간 {c5['B']['0.01']['alerts_per_8h']['posterior_q95']:.0f}건 vs CP상한 {c5['B']['0.01']['alerts_per_8h']['cp_upper95']:.0f}건)")

# ---------------------------------------------------------------- C6 수락 검사 (a)의 귀무분포
c6 = {}
for a in (.01, .03, .05):
    n, m = 120, 60
    l = math.floor(a * (n + 1) + 1e-9)
    limit = int(stats.binom.ppf(.95, m, l / (n + 1)))
    reject_binom = float(stats.binom.sf(limit, m, l / (n + 1)))
    reject_bb = float(bb_pmf(np.arange(limit + 1, m + 1), m, l, n + 1 - l).sum())
    c6[str(a)] = dict(n_cal=n, holdout=m, l=l, binomial_limit=limit, reject_prob_if_binomial=reject_binom,
                      reject_prob_exact_betabinomial=reject_bb, bb_q95=bb_quantile(.95, m, l, n + 1 - l))
OUT["C6_acceptance_null"] = c6
log("C6 수락 검사 (a) 정상인데 거부될 확률(정확 귀무 Beta-Binomial): " + ", ".join(
    f"α{a} 한도 {v['binomial_limit']} → {v['reject_prob_exact_betabinomial']:.3f}(이항 가정 {v['reject_prob_if_binomial']:.3f})" for a, v in c6.items()))


# ---------------------------------------------------------------- C7 결합 규칙 민감도
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
    return dict(fmax_tippett=fmax, fisher=fisher, stouffer=stouffer, sum_g=sg, mean_g=mean_g)


c7 = {}
for s in "AB":
    mdl = models[s]
    cc_, cseg, cpos, cunits = components(mdl, splits[s]["cal"])
    assert np.allclose(segment_max(cc_["score"], cunits), mdl.cal), "보정값 재계산 불일치"
    tc, tseg, _, _ = components(mdl, splits[s]["test"])
    ac, aseg, apos, _ = components(mdl, abnormal)
    fc, ft, fa = fusions(cc_), fusions(tc), fusions(ac)
    assert np.allclose(np.nan_to_num(ft["fmax_tippett"], nan=-1), np.nan_to_num(tc["score"], nan=-1))
    rows = {}
    # 근거 성분: 각 성분 g가 주 모델(fmax) 문턱을 넘는가(GuardModel.predict의 reason과 같은 판정)
    g_ab = np.column_stack([ac["g_magnitude"], ac["g_waveform"], ac["g_dynamics"]])
    reason_any = np.column_stack([conformal_p(mdl.cal, g_ab[:, j]) <= .01 for j in range(3)]).any(1)
    for name in fc:
        cal = segment_max(fc[name], cunits)
        pt, pa_ = conformal_p(cal, ft[name]), conformal_p(cal, fa[name])
        al_t, al_a = np.isfinite(pt) & (pt <= .01), np.isfinite(pa_) & (pa_ <= .01)
        tp, fp = int(al_a.sum()), int(al_t.sum())
        fn = len(al_a) - tp
        first = pd.Series(np.where(al_a, apos, 10 ** 6)).groupby(aseg).min()
        rows[name] = dict(tp=tp, fp=fp, fn=fn, f1=round(2 * tp / (2 * tp + fp + fn), 6),
                          normal_records=int(pd.Series(al_t).groupby(tseg).any().sum()),
                          abnormal_records=int(pd.Series(al_a).groupby(aseg).any().sum()),
                          missed_pos0_1=int((~al_a & (apos <= 1)).sum()), missed_pos2plus=int((~al_a & (apos >= 2)).sum()),
                          abnormal_alarms_without_single_component_reason=int((al_a & ~reason_any).sum()),
                          first_alarm_max_s=float(first[first < 10 ** 6].max() * D.DT) if (first < 10 ** 6).any() else None)
    # 주 모델(fmax) 경보 행의 성분 조합(press_evidence/component_combinations.csv 대조)
    act = np.column_stack([conformal_p(mdl.cal, g_ab[:, j]) <= .01 for j in range(3)])
    main_alarm = np.isfinite(conformal_p(mdl.cal, ac["score"])) & (conformal_p(mdl.cal, ac["score"]) <= .01)
    names = np.array(["magnitude", "waveform", "dynamics"])
    combo = pd.Series(["+".join(names[a]) for a in act[main_alarm]]).value_counts()
    ref_combo = pd.read_csv(EV / "component_combinations.csv")
    ref_combo = ref_combo[(ref_combo.split == s) & (ref_combo.subset == "abnormal")].set_index("combination").alarm_rows
    rows["_main_model_combinations"] = dict(alarm_rows=int(main_alarm.sum()), counts=combo.to_dict(),
                                            single_component_rows=int(sum(v for k, v in combo.items() if "+" not in k)),
                                            matches_evidence=bool(combo.sort_index().to_dict() == ref_combo.sort_index().to_dict()))
    c7[s] = rows
OUT["C7_fusion_sensitivity"] = dict(results=c7, note="심사 확인용 사후 민감도. 이상 자료를 이미 본 뒤의 비교이므로 주 모델 교체 근거가 아니다. "
                                                     "g=−log10(정상 꼬리 확률)이므로 fmax(g)=Tippett 최소 p 결합이다.")
log("C7 결합 규칙(α1%, TP/FP/FN·F1·정상 알림·근거 없는 이상 경보): " + " | ".join(
    f"{s} " + ", ".join(f"{k} {v['tp']}/{v['fp']}/{v['fn']} {v['f1']:.3f} n{v['normal_records']} r{v['abnormal_alarms_without_single_component_reason']}"
                        for k, v in c7[s].items() if not k.startswith("_")) for s in "AB"))
log("C7 주 모델 경보 행 성분 조합: " + " | ".join(
    f"{s} 단일 성분 {c7[s]['_main_model_combinations']['single_component_rows']}/{c7[s]['_main_model_combinations']['alarm_rows']}"
    f" (evidence 일치 {c7[s]['_main_model_combinations']['matches_evidence']})" for s in "AB"))

# ---------------------------------------------------------------- C8 경보 → 이상 확률(기저율 시나리오)
e1 = pd.read_csv(SUP / "e1_summary.csv")
tpr = {}
for fam, lev in (("cur_noise", .1), ("cur_offset", .4), ("vib_noise", 4.0), ("vib_noise", 2.0), ("cur_gain", 1.15)):
    r = e1[(e1.family == fam) & np.isclose(e1.level, lev) & (e1["shape"] == "step") & (e1.t0 == 10) & (e1.model == "guard_v2") & np.isclose(e1.alpha, .01)]
    tpr[f"{fam}_{lev:g}"] = float(r.detect_rate_2s.min())
tpr["contest_21of21_cp_lower95"] = float(.05 ** (1 / 21))
far = {"nominal_1of121": 1 / 121, "prior_q95_beta(1,120)": float(stats.beta.ppf(.95, 1, 120)),
       "B_posterior_mean": c5["B"]["0.01"]["posterior_mean"], "B_posterior_q95": c5["B"]["0.01"]["posterior_q95"]}
table = []
for pi in (1e-4, 1e-3, 1e-2):
    for fname, fv in far.items():
        for tname in ("cur_noise_0.1", "cur_offset_0.4", "vib_noise_2", "contest_21of21_cp_lower95"):
            t = tpr[tname]
            table.append(dict(prior_per_record=pi, far=fname, far_value=fv, tpr=tname, tpr_value=t, lr_plus=t / fv,
                              p_anomaly_given_alert=pi * t / (pi * t + (1 - pi) * fv),
                              p_anomaly_given_no_alert=pi * (1 - t) / (pi * (1 - t) + (1 - pi) * (1 - fv))))
OUT["C8_alert_probability"] = dict(tpr=tpr, far=far, table=table,
                                   max_lr_by_calibration_resolution={str(n): (n + 1) for n in (99, 120, 180, 500, 1000)},
                                   note="라벨로 사후확률을 적합하지 않는다. 오경보율은 정상 보정에서, 탐지율은 시작 시각을 아는 주입(E1)에서 온다. "
                                        "p값의 최솟값이 1/(n+1)이므로 알림 한 건의 우도비는 명목상 (n+1)·TPR을 넘을 수 없다.")
pick = [r for r in table if r["far"] == "nominal_1of121" and r["tpr"] == "cur_noise_0.1"]
log("C8 α1% 알림의 이상 확률(명목 FAR 1/121, 전류 잡음 0.1σ 탐지율): " + ", ".join(
    f"π={r['prior_per_record']:g} → {r['p_anomaly_given_alert']:.3f}" for r in pick))

# ---------------------------------------------------------------- C9 0.6 Hz 위상 일관성
t_abs = pd.to_datetime(normal[D.TIME], format="mixed")
tsec = (t_abs - t_abs.iloc[0]).dt.total_seconds().to_numpy()
cur = normal[D.SENSORS[2]].to_numpy(float)
pos_all, len_all = D.segment_positions(seg_all)
use = len_all >= 20
rec = seg_all[use]
ts, xs = tsec[use], cur[use]
rid, rinv = np.unique(rec, return_inverse=True)


def per_record_phase(f, t=ts, x=xs, inv=rinv, nrec=None):
    nrec = nrec or len(np.unique(inv))
    c, s_ = np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t)
    cols = [c, s_, np.ones_like(t)]
    M = np.zeros((nrec, 3, 3))
    v = np.zeros((nrec, 3))
    for i in range(3):
        v[:, i] = np.bincount(inv, cols[i] * x, nrec)
        for j in range(3):
            M[:, i, j] = np.bincount(inv, cols[i] * cols[j], nrec)
    coef = np.linalg.solve(M + 1e-9 * np.eye(3), v[..., None])[..., 0]
    return np.arctan2(coef[:, 1], coef[:, 0]), np.hypot(coef[:, 0], coef[:, 1])


def coherence(freqs, **kw):
    out = []
    for f in freqs:
        ph, amp = per_record_phase(f, **kw)
        out.append(float(np.abs(np.mean(np.exp(1j * ph)))))
    return np.asarray(out)


coarse = np.arange(0.590, 0.610 + 1e-12, 2e-5)
R_coarse = coherence(coarse)
f0 = float(coarse[R_coarse.argmax()])
fine = np.arange(f0 - 4e-5, f0 + 4e-5 + 1e-12, 1e-6)
R_fine = coherence(fine)
f_star = float(fine[R_fine.argmax()])
ph_star, amp_star = per_record_phase(f_star)
# 귀무 비교: 기록 시작 시각을 기록끼리 섞은 뒤(기록 안 상대 시각은 유지) 같은 탐색을 한 최대 R
starts = pd.Series(ts).groupby(rinv).transform("min").to_numpy()
null_max = []
rng = np.random.default_rng(1)
perm_starts = pd.Series(ts).groupby(rinv).min().to_numpy()
for _ in range(20):
    sh = rng.permutation(perm_starts)
    t_null = ts - starts + sh[rinv]
    null_max.append(float(coherence(coarse[::5], t=t_null).max()))
# 시간 블록별(약 15분) 위상 일관성과 블록별 최적 주파수
blocks = []
edges = np.quantile(perm_starts, [0, .2, .4, .6, .8, 1.0])
for b in range(5):
    sel_rec = (perm_starts >= edges[b]) & (perm_starts <= edges[b + 1] if b == 4 else perm_starts < edges[b + 1])
    rows_sel = sel_rec[rinv]
    inv_b = np.unique(rinv[rows_sel], return_inverse=True)[1]
    Rb = coherence(coarse, t=ts[rows_sel], x=xs[rows_sel], inv=inv_b)
    blocks.append(dict(block=b, records=int(sel_rec.sum()), best_hz=float(coarse[Rb.argmax()]), best_R=float(Rb.max()),
                       R_at_global_fstar=float(coherence([f_star], t=ts[rows_sel], x=xs[rows_sel], inv=inv_b)[0])))
OUT["C9_phase_coherence"] = dict(records=int(len(rid)), coarse_grid=[float(coarse[0]), float(coarse[-1]), 2e-5],
                                 f_star_hz=f_star, R_at_f_star=float(R_fine.max()), R_at_0p600=float(coherence([0.6])[0]),
                                 null_shuffled_starts_maxR=dict(mean=float(np.mean(null_max)), max=float(np.max(null_max)), reps=len(null_max)),
                                 amplitude_median=float(np.median(amp_star)), time_blocks=blocks,
                                 aliasing_arithmetic=dict(fs_hz=10.0, line_candidates_hz=[60 - f_star, 60 + f_star],
                                                          fs_if_line_60hz=[60 / (6 + f_star / 10), 60 / (6 - f_star / 10)]),
                                 note="기록마다 절대 시각 기준으로 cos·sin·상수를 적합해 위상을 얻고, 기록 간 위상의 평균 합성 길이 R(0~1)을 본다. "
                                      "R이 1에 가까우면 77분 동안 위상이 이어지는 하나의 진동이다.")
log(f"C9 위상 일관성: f*={f_star:.6f} Hz, R={R_fine.max():.3f} (0.600 Hz에서 {OUT['C9_phase_coherence']['R_at_0p600']:.3f}), "
    f"시작 시각 섞은 귀무 최대 R {np.max(null_max):.3f}; 블록별 최적 " + ", ".join(f"{b['best_hz']:.5f}(R {b['best_R']:.2f})" for b in blocks))

# ---------------------------------------------------------------- C9b 이웃 기록 사이 위상 연속성
# 기록 r의 마지막 20관측과 기록 r+1의 처음 20관측을 같은 절대 시각 기준으로 적합해 위상 차이를 본다.
# 진동이 기록 사이 공백에도 이어지면(같은 주파수, 위상 재시작 없음) 위상 차이가 0 근처에 모인다.
rec_codes = np.unique(seg_all)
ends, begins = [], []
for r in rec_codes[:-1]:
    a_idx = np.flatnonzero(seg_all == r)
    b_idx = np.flatnonzero(seg_all == r + 1)
    if len(a_idx) >= 20 and len(b_idx) >= 20:
        ends.append(a_idx[-20:]); begins.append(b_idx[:20])
ends, begins = np.array(ends), np.array(begins)
gaps = tsec[begins[:, 0]] - tsec[ends[:, -1]]


def window_phase(idx, f):
    t, x = tsec[idx], cur[idx]
    out = np.empty(len(idx))
    for i in range(len(idx)):
        A = np.column_stack([np.cos(2 * np.pi * f * t[i]), np.sin(2 * np.pi * f * t[i]), np.ones(idx.shape[1])])
        c = np.linalg.lstsq(A, x[i], rcond=None)[0]
        out[i] = np.arctan2(c[1], c[0])
    return out


pair_scan = []
for f in np.arange(0.55, 0.65 + 1e-12, 0.0025):
    d = window_phase(begins, f) - window_phase(ends, f)
    pair_scan.append((float(f), float(np.abs(np.mean(np.exp(1j * d))))))
f_pair = max(pair_scan, key=lambda z: z[1])[0]
d_best = window_phase(begins, f_pair) - window_phase(ends, f_pair)
d_06 = window_phase(begins, 0.6) - window_phase(ends, 0.6)
rng = np.random.default_rng(2)
null_pair = []
ph_b, ph_e = window_phase(begins, 0.6), window_phase(ends, 0.6)
for _ in range(200):
    null_pair.append(float(np.abs(np.mean(np.exp(1j * (rng.permutation(ph_b) - ph_e))))))
short = gaps < np.median(gaps)
# 양성 대조: 같은 기록(50행) 안의 처음 20관측과 마지막 20관측(사이 1초)은 위상이 이어져야 한다.
long_recs = [np.flatnonzero(seg_all == r) for r in rec_codes if (seg_all == r).sum() >= 50]
first20, last20 = np.array([ix[:20] for ix in long_recs]), np.array([ix[-20:] for ix in long_recs])
d_ctrl = window_phase(last20, 0.6) - window_phase(first20, 0.6)
# 기록 시작 위상(기록 안 상대 시각 기준): 수집이 진동의 특정 위상에서 시작되는지(트리거 고정)
starts_rel = []
for ix in [np.flatnonzero(seg_all == r) for r in rec_codes if (seg_all == r).sum() >= 20]:
    t = tsec[ix[:20]] - tsec[ix[0]]
    A = np.column_stack([np.cos(2 * np.pi * .6 * t), np.sin(2 * np.pi * .6 * t), np.ones(20)])
    c = np.linalg.lstsq(A, cur[ix[:20]], rcond=None)[0]
    starts_rel.append(np.arctan2(c[1], c[0]))
starts_rel = np.asarray(starts_rel)
OUT["C9b_pair_phase_continuity"] = dict(pairs=int(len(gaps)), gap_s_median=float(np.median(gaps)), gap_s_range=[float(gaps.min()), float(gaps.max())],
                                        R_at_0p6=float(np.abs(np.mean(np.exp(1j * d_06)))), best_f=f_pair, R_at_best=float(np.abs(np.mean(np.exp(1j * d_best)))),
                                        R_short_gaps=float(np.abs(np.mean(np.exp(1j * d_06[short])))), R_long_gaps=float(np.abs(np.mean(np.exp(1j * d_06[~short])))),
                                        null_shuffled_R=dict(mean=float(np.mean(null_pair)), q95=float(np.quantile(null_pair, .95))),
                                        scan=pair_scan,
                                        positive_control_within_record=dict(records=len(long_recs), R=float(np.abs(np.mean(np.exp(1j * d_ctrl))))),
                                        record_start_phase_local=dict(records=int(len(starts_rel)), R=float(np.abs(np.mean(np.exp(1j * starts_rel))))))
log(f"C9b 이웃 기록 위상 연속성: 쌍 {len(gaps)}개(공백 중앙 {np.median(gaps):.2f}초), R(0.6 Hz) {OUT['C9b_pair_phase_continuity']['R_at_0p6']:.3f}, "
    f"최적 f {f_pair:.4f} R {OUT['C9b_pair_phase_continuity']['R_at_best']:.3f}, 짧은/긴 공백 R {OUT['C9b_pair_phase_continuity']['R_short_gaps']:.3f}/"
    f"{OUT['C9b_pair_phase_continuity']['R_long_gaps']:.3f}, 섞은 귀무 95% {np.quantile(null_pair, .95):.3f}; "
    f"양성 대조(기록 안 1초 간격) R {OUT['C9b_pair_phase_continuity']['positive_control_within_record']['R']:.3f}, "
    f"기록 시작 위상 R {OUT['C9b_pair_phase_continuity']['record_start_phase_local']['R']:.3f}")

# ---------------------------------------------------------------- C10 진동 채널 관측 성질
c10 = {}
for name, fr in (("normal", normal), ("abnormal", abnormal)):
    sg = D.segments(fr)
    row = {}
    for c in D.SENSORS:
        x = fr[c].to_numpy(float)
        same = np.r_[False, sg[1:] == sg[:-1]]
        lag1 = float(np.corrcoef(x[1:][same[1:]], x[:-1][same[1:]])[0, 1])
        row[c] = dict(mean=float(x.mean()), sd=float(x.std()), share_negative=float((x < 0).mean()), lag1_within=lag1)
    c10[name] = row
OUT["C10_vibration_observability"] = c10
log("C10 음수 비율·lag-1(정상): " + ", ".join(f"{c} {v['share_negative']:.3f}/{v['lag1_within']:.3f}" for c, v in c10["normal"].items()))

# ---------------------------------------------------------------- C11 재보정 수락 검사 실행
import recalibrate  # noqa: E402

with tempfile.TemporaryDirectory(prefix="judge05_recal_") as tmp:
    src = Path(tmp) / "normal_0_479.csv"
    normal[seg_all < 480].to_csv(src, index=False)
    code = recalibrate.main(["--normal", str(src), "--out", str(Path(tmp) / "site.json"), "--report", str(Path(tmp) / "site_report.json")])
    report = json.loads((Path(tmp) / "site_report.json").read_text())
OUT["C11_recalibrate"] = dict(exit_code=code, passed=report["passed"], units=report["units"],
                              checks=[{k: c[k] for k in ("name", "value", "limit", "ok")} for c in report["checks"]])
log(f"C11 recalibrate 종료 코드 {code}, 통과 {report['passed']}: " + "; ".join(f"{c['name']} = {c['value']}" for c in report["checks"]))

# ---------------------------------------------------------------- C12 E1 하한 재확인
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
log("C12 E1 하한: " + ", ".join(f"{k} {v['floor']}" for k, v in c12.items()))

# ---------------------------------------------------------------- C13 지도학습 기준선에 불균형 가중을 넣으면
# press_supervised/run.py의 함수(특징·교차검증·주입)를 그대로 쓰고 모델만 class_weight="balanced"로 바꾼다. 파일을 쓰지 않는다.
import importlib.util  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

spec = importlib.util.spec_from_file_location("judge05_supervised_run", Y / "analysis" / "press_supervised" / "run.py")
sup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sup)
sup.MODELS = {"logistic_balanced": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")),
              "hgb_balanced": lambda: HistGradientBoostingClassifier(random_state=0, class_weight="balanced")}
gr = sup.grouped_records(normal, abnormal)
inj = sup.injection(normal, abnormal)
OUT["C13_supervised_class_weight"] = dict(
    grouped_records=gr[["split", "model", "threshold", "tp", "fp", "fn", "f1", "normal_alerted_segments", "abnormal_detected_segments"]].to_dict("records"),
    injection=inj[["family", "level", "model", "detect_rate_2s", "v2_detect_rate_2s"]].to_dict("records"),
    note="press_supervised 기준선(기본 가중)에 불균형 가중만 더한 심사 확인. 초모수는 그대로다.")
log("C13 가중 지도학습(기록 묶음 교차검증, 문턱 0.5): " + ", ".join(
    f"{r.split} {r.model} F1 {r.f1:.3f} 정상 알림 {r.normal_alerted_segments} 탐지 {r.abnormal_detected_segments}/21"
    for r in gr[gr.threshold == "0.5"].itertuples()))
sel = inj[inj.family.isin(["cur_noise", "cur_offset", "vib_noise", "none"])]
log("C13 가중 지도학습 주입 2초 탐지율(v2): " + ", ".join(
    f"{r.family} {r.level:g} {r.model} {r.detect_rate_2s:.2f}({r.v2_detect_rate_2s:.2f})" for r in sel.itertuples()
    if (r.family, r.level) in {("cur_noise", .1), ("cur_noise", .2), ("cur_offset", .4), ("cur_offset", .8), ("vib_noise", 2.0), ("vib_noise", 4.0), ("none", 0.0)}))

OUT["elapsed_s"] = round(time.monotonic() - T_START, 1)
(HERE / "judge05_verify.json").write_text(json.dumps(D.to_jsonable(OUT), ensure_ascii=False, indent=2))
log(f"완료 {OUT['elapsed_s']}초 → {HERE / 'judge05_verify.json'}")
