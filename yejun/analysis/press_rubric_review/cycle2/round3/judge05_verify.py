"""평가관 05(창의성·차별성) cycle2 round3 — 2회차 R2-O8~O12 완료 기준과 새 산출물을 원본·커밋 코드로 다시 계산한다.

읽기: 원본 CSV 2개(해시 확인), 저장 모델 press_guard/artifacts/{guard,probability}_{A,B}.json(outputs/manifest.json 해시 확인),
      커밋된 산출물(press_guard/outputs, analysis/press_evidence·press_selection·press_supervised·press_supplement),
      로컬 테스트 예측 파일(manifest 해시와 같을 때만 사용).
쓰기: 이 폴더의 judge05_verify.json 하나. 재보정 실행(C11)과 지도학습 재실행(C13)은 시스템 임시 폴더에 쓴다.

2회차 검사(같은 번호, 기준 커밋만 바뀜)
C0  출처: HEAD, 모델·확률 보정기·원본·테스트 예측 파일 해시, 미커밋 파일
C1  주 수치(α 1·3·5%)           C3  A/B 명목 대비 실현 곡선        C4  시간순 5겹 재적합 보정 곡선
C5  보정 조건부 Beta·사후 95% 업무량 + R2-O9 표시(OPERATIONS·콘솔)
C6  수락 한도 Beta-Binomial      C7  결합 규칙 5종                  C8  라벨 없는 환산 216행
C8b 확률 층: 21겹 Brier·ECE, 상한 121 + R2-O12(경보 행 최소 LR, LR<1, 오경보 확률, B 문턱 계단)
C8c R2-O8: SBB 모의와 문구 검사(README·docstring·CSV·콘솔·운영 문서)
C8d 테스트 예측 파일 채점(π 1%·파일 비율), 상한 행 수, 신뢰도 최상위 구간의 보수성
C9b 0.6 Hz 위상 시험           C10 관측 성질(음수 비율·lag-1)
C11 recalibrate.py 실행         C12 E1 하한                        C13 지도학습 재실행(임시 폴더, 바이트 비교)
C14 판단표 FM 참조              C15 '1−p'를 확률로 부른 줄        C16 R2-O10: 이상 진동 저주파 성격·표 해석·FM 인용
3회차 새 검사
C17 R2-O11: 앨리어싱 조건 일반형과 남은 60 Hz 단정 문장
C18 정상 운전 2수준 상태(가우스 혼합 BIC·경계·분할 구성·상태별 정상 알림) 독립 재계산
C19 감시 조치 분기 기능 시험(전류 배율·진동 잡음·운전 조건 변경 기록) + 고장 모드표 FM4·FM5 대리 주입과의 관계
C20 같은 특징 대안 주입 전이표 일부 독립 재구현(주입·결합·conformal p를 이 파일에서 다시 씀)
C21 2단계 비사후 업무량 추정(3.3건·상한 12.7건)
C22 정상 진동의 좁은 대역 구조(전류 0.6 Hz의 약 3·6배), 이상 진동과 비교, FM3 문구 대조(탐색)
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/analysis/press_rubric_review/cycle2/round3/judge05_verify.py
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import filecmp
import hashlib
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
from sklearn.mixture import GaussianMixture
from sklearn.neighbors import NearestNeighbors

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

SKIP_SUP = "--skip-supervised" in sys.argv
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


def read(p):
    return Path(p).read_text(encoding="utf-8")


def lines_of(p):
    return read(p).splitlines()


# ---------------------------------------------------------------- C0 출처
t0 = time.monotonic()
head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
porcelain = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "yejun"], capture_output=True, text=True).stdout.splitlines()
manifest = json.loads((G / "outputs" / "manifest.json").read_text())
art_ok = {n: D.sha256_file(G / "artifacts" / n) == h for n, h in manifest["artifacts"].items()}
normal, abnormal, rep = D.load(Y / "press_submission")          # 해시·행 수가 다르면 예외
inputs_ok = {k: v["sha256"] == manifest["input_hashes"][k] for k, v in rep["files"].items()}
local_pred_ok = {n: D.sha256_file(G / "outputs" / n) == manifest["outputs"].get(n) for n in ("test_predictions_A.csv", "test_predictions_B.csv")}
OUT["C0_provenance"] = dict(head=head, artifacts_match_manifest=art_ok, inputs_match_manifest=inputs_ok, local_test_predictions_match_manifest=local_pred_ok,
                            uncommitted_under_yejun=porcelain, note="미커밋 파일은 채점 대상이 아니다(HEAD 기준). 이 폴더의 judge05_* 는 이번 검수 산출물이다.")
assert all(art_ok.values()) and all(inputs_ok.values())
log(f"C0 HEAD {head[:7]} · 모델·확률 보정기·원본 해시 일치({', '.join(art_ok)}) · 로컬 테스트 예측 파일 manifest 일치 {local_pred_ok} · 미커밋 {len(porcelain)}건")

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
tick("C1", t0)


def record_minp(pred):
    return pred.groupby("record_id").p_value.min().fillna(1.0).to_numpy()


# ---------------------------------------------------------------- C3 A/B 보정 곡선
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
log(f"C3 A/B 곡선 calibration_curve.csv 일치: A {c3['A']['alerted_by_k']} B {c3['B']['alerted_by_k']}")

# ---------------------------------------------------------------- C4 시간순 5겹 보정 곡선
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
    for a in (.01, .03, .05):
        got = int((fold_minp[name] <= a).sum())
        ref = rolling_ref[(rolling_ref.split == name) & (rolling_ref.model == "guard_v2") & np.isclose(rolling_ref.alpha, a)].iloc[0]
        folds.append(dict(fold=name, alpha=a, alerted=got, ref=int(ref.normal_notified_segments), match=got == int(ref.normal_notified_segments)))
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
    curve.append(dict(k=k, pooled=pooled, pooled_pi90=[lo, hi], within=bool(lo <= pooled <= hi),
                      committed_pooled=int(ref_p.alerted), committed_pi90=[int(ref_p.pi90_low), int(ref_p.pi90_high)]))
OUT["C4_rolling_curve"] = dict(folds=folds, curve=curve, per_fold_mismatch_vs_committed=mism,
                               all_pooled_match=all(c["pooled"] == c["committed_pooled"] for c in curve),
                               all_pi90_match=all(c["pooled_pi90"] == c["committed_pi90"] for c in curve),
                               all_within=all(c["within"] for c in curve))
log("C4 시간순 5겹 합산: " + ", ".join(f"k={c['k']} {c['pooled']}/300 [{c['pooled_pi90'][0]},{c['pooled_pi90'][1]}]" for c in curve if c["k"] in (1, 3, 6, 12))
    + f" · 겹별 불일치 {len(mism)}건 · 합산·구간 일치 {OUT['C4_rolling_curve']['all_pooled_match']}/{OUT['C4_rolling_curve']['all_pi90_match']} · 모든 k 구간 안 {OUT['C4_rolling_curve']['all_within']}")
tick("C4", t0)

# ---------------------------------------------------------------- C5 보정 조건부·사후 95% + R2-O9 표시
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
                                                  and np.isclose(U * post.ppf(.95), w.posterior95_alerts_per_8h_elapsed)
                                                  and np.isclose(U * upper95(xa, m_eval), w.upper95_alerts_per_8h_elapsed)))
    c5[s] = rows
ops = lines_of(G / "OPERATIONS.md")
ops_l1 = [(i, ln) for i, ln in enumerate(ops, 1) if ln.startswith("| 1단계(주의) 교대 8시간")]
appjs = read(G / "web" / "app.js")
wl_fn = appjs[appjs.find("function renderWorkload"):appjs.find("function renderDecisionTable")]
idx_html = lines_of(G / "web" / "index.html")
wl_note = [(i, ln) for i, ln in enumerate(idx_html, 1) if 'id="workload"' in ln]
a44, b92 = round(c5["A"]["0.01"]["alerts8h_post95"]), round(c5["B"]["0.01"]["alerts8h_post95"])
c5_doc = dict(operations_line=ops_l1[0][0] if ops_l1 else None,
              operations_has_post95_values=bool(ops_l1 and f"A {a44}" in ops_l1[0][1] and f"B {b92}" in ops_l1[0][1]),
              operations_has_assumption=bool(ops_l1 and "교환가능성" in ops_l1[0][1]),
              operations_has_cp=bool(ops_l1 and "152" in ops_l1[0][1]),
              console_table_has_cp_and_post95_columns=("upper95_alerts_per_8h_elapsed" in wl_fn and "posterior95_alerts_per_8h_elapsed" in wl_fn),
              console_note_line=wl_note[0][0] if wl_note else None,
              console_note_has_assumption=bool(wl_note and "교환가능성" in wl_note[0][1] and "사후 95%" in wl_note[0][1]))
OUT["C5_workload_and_R2_O9"] = dict(values=c5, display=c5_doc)
assert all(r["matches_workload"] for v in c5.values() for r in v.values())
log(f"C5 α1%: P(실제>1%)={c5['A']['0.01']['p_far_gt_alpha']:.3f}, Beta(1,120) 95% {c5['A']['0.01']['prior_q95']:.4f} · 사후 95% A {c5['A']['0.01']['posterior_q95']:.4f}·B {c5['B']['0.01']['posterior_q95']:.4f}"
    f" · 8시간 A {c5['A']['0.01']['alerts8h_post95']:.2f}(CP {c5['A']['0.01']['alerts8h_cp']:.2f})·B {c5['B']['0.01']['alerts8h_post95']:.2f}(CP {c5['B']['0.01']['alerts8h_cp']:.2f}) — workload_v2.csv 일치"
    f" · R2-O9 표시: OPERATIONS:{c5_doc['operations_line']} 값 {c5_doc['operations_has_post95_values']}·가정 {c5_doc['operations_has_assumption']}·CP {c5_doc['operations_has_cp']}, "
    f"콘솔 표 두 열 {c5_doc['console_table_has_cp_and_post95_columns']}, index.html:{c5_doc['console_note_line']} 가정 {c5_doc['console_note_has_assumption']}")

# ---------------------------------------------------------------- C6 수락 한도
from monitor import alert_limit  # noqa: E402

c6 = {}
for a in (.01, .03, .05):
    n, m = 120, 60
    l = math.floor(a * (n + 1) + 1e-9)
    lim_binom = int(stats.binom.ppf(.95, m, l / (n + 1)))
    lim_bb = bb_quantile(.95, m, l, n + 1 - l)
    c6[str(a)] = dict(l=l, binomial_limit_old=lim_binom, betabinom_limit=lim_bb, code_limit=alert_limit(a, n, m),
                      reject_old_exact=float(bb_pmf(np.arange(lim_binom + 1, m + 1), m, l, n + 1 - l).sum()),
                      reject_new_exact=float(bb_pmf(np.arange(lim_bb + 1, m + 1), m, l, n + 1 - l).sum()))
OUT["C6_acceptance"] = c6
assert all(v["code_limit"] == v["betabinom_limit"] for v in c6.values())
log("C6 수락 한도(보정 120·수락 60): " + ", ".join(
    f"α{a} {v['binomial_limit_old']}→{v['betabinom_limit']}(코드 {v['code_limit']}), 정상 거부 {v['reject_old_exact']:.3f}→{v['reject_new_exact']:.3f}" for a, v in c6.items()))


# ---------------------------------------------------------------- C7 결합 규칙
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
                c7_mism.append((s, a, name, got))
            rows[f"{a}_{name}"] = dict(**got, match=match)
    c7[s] = rows
OUT["C7_fusion"] = dict(results=c7, mismatches=c7_mism)
log("C7 결합 규칙 α1%(TP/FP/FN·정상 알림·근거 없는 이상 경보): " + " | ".join(
    f"{s} " + ", ".join(f"{k.split('_', 1)[1]} {v['tp']}/{v['fp']}/{v['fn']} n{v['normal_alerted']} r{v['no_evidence_alarms_abnormal']}"
                        for k, v in c7[s].items() if k.startswith("0.01")) for s in "AB")
    + f" · combination_rules.csv와 불일치 {len(c7_mism)}건(α 3개 × 5규칙 × 2분할)")
tick("C7", t0)

# ---------------------------------------------------------------- C8 라벨 없는 환산
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
OUT["C8_label_free"] = dict(mismatches=c8_mism, A_alpha1_cur_noise01=c8_pick, rows_checked=len(lf))
assert not c8_mism
log(f"C8 라벨 없는 환산 {len(lf)}행 재계산 일치 · A α1% 전류 잡음 0.1σ: 명목 π0.1% {c8_pick['nominal_pi0.001']:.3f}·π1% {c8_pick['nominal_pi0.01']:.3f}, "
    f"보정 95% {c8_pick['calibrated95_pi0.001']:.3f}·{c8_pick['calibrated95_pi0.01']:.3f}")

# ---------------------------------------------------------------- C8b 확률 층 + R2-O12
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
    return lr, iso, float(y.mean())


def ece(y, p, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    tot = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & ((p < hi) | (hi == 1))
        if k.any():
            tot += k.mean() * abs(p[k].mean() - y[k].mean())
    return float(tot)


def post(lr, pi):
    return pi * lr / (pi * lr + 1 - pi)


pev = pd.read_csv(G / "outputs" / "probability_eval_v2.csv")
pconv = pd.read_csv(G / "outputs" / "probability_conversion_v2.csv")
c8b, oof = {}, {}
for s in "AB":
    mdl = models[s]
    cap = len(mdl.cal) + 1
    cal_scores = mdl.predict(splits[s]["cal"]).score.to_numpy()
    pt, pa = preds[s]
    st, sa, ra = pt.score.to_numpy(), pa.score.to_numpy(), pa.record_id.to_numpy()
    la, ln_ = np.full(len(sa), np.nan), []
    for r in np.unique(ra):
        keep = ra != r
        f, _, _ = iso_lr(cal_scores, sa[keep], cap)
        la[~keep] = f(sa[~keep])
        ln_.append(f(st))
    oof[s] = la
    ln = np.median(ln_, axis=0)
    y = np.r_[np.zeros(len(st)), np.ones(len(sa))]
    pi_rows = len(sa) / len(y)
    q = np.clip(np.nan_to_num(post(np.r_[ln, la], pi_rows), nan=pi_rows), 1e-9, 1 - 1e-9)
    brier, e = float(np.mean((q - y) ** 2)), ece(y, q)
    ref = pev[(pev.split == s) & (pev.cv == "21fold") & (pev.unit == "rows") & (pev.method == "calibrated_isotonic")].iloc[0]
    # 배포 보정기(전체 이상 행으로 적합)와 저장본 비교
    f_all, iso_all, pi_fit = iso_lr(cal_scores, sa, cap)
    deploy = mdl.probability
    thr = float(np.sort(mdl.cal)[-1])
    lr_thr = float(deploy.likelihood_ratio([thr + 1e-9])[0])
    xs, ys = np.asarray(deploy.x), np.asarray(deploy.y)
    lo_x = float(xs[xs < thr].max())
    hi_x = float(xs[xs > thr].min())
    step_norm = int(((cal_scores >= lo_x) & (cal_scores <= thr)).sum())
    step_abn = int(((sa >= lo_x) & (sa <= thr)).sum())
    y_left = float(np.interp((lo_x + thr) / 2, xs, ys))
    y_right = float(np.interp(hi_x, xs, ys))
    # 경보 행(α 1%): 정상 평가 행은 배포 보정기, 이상 행은 그 기록을 뺀 교차 적합(예측 파일과 같은 규칙)
    at, aa = pt.alarm.to_numpy(bool), pa.alarm.to_numpy(bool)
    lr_n_alarm = deploy.likelihood_ratio(st[at]) if at.any() else np.array([])
    lr_a_alarm = la[aa]
    both = np.r_[lr_n_alarm, lr_a_alarm]
    row = pconv[(pconv.split == s) & np.isclose(pconv.prior, .01)].iloc[0]
    c8b[s] = dict(lr_cap_saved=deploy.lr_cap, brier_21fold=brier, ece_21fold=e, committed_brier=float(ref.brier), committed_ece=float(ref.ece),
                  matches_committed=bool(np.isclose(brier, ref.brier, atol=1e-9) and np.isclose(e, ref.ece, atol=1e-9)),
                  threshold=thr, lr_at_threshold=lr_thr, p_at_threshold_pi1=float(post(lr_thr, .01)),
                  iso_step_left=lo_x, iso_step_right=hi_x, step_normal_cal_rows=step_norm, step_abnormal_rows=step_abn,
                  step_fitted_left=y_left, fitted_at_right_knot=y_right, pi_fit=float(deploy.pi_fit), pi_fit_recomputed=pi_fit,
                  alarm_rows=int(len(both)), alarm_rows_min_lr=float(both.min()), alarm_rows_min_p_pi1=float(post(both.min(), .01)),
                  alarm_rows_lr_below_1=int((both < 1).sum()), abnormal_alarm_rows=int(aa.sum()), abnormal_alarm_lr_below_1=int((lr_a_alarm < 1).sum()),
                  false_alarm_rows=int(at.sum()), false_alarm_lr=[float(v) for v in lr_n_alarm], false_alarm_p_pi1=[float(post(v, .01)) for v in lr_n_alarm],
                  matches_conversion_csv=bool(np.isclose(row.alarm_rows_min_lr, both.min()) and int(row.alarm_rows) == len(both)
                                              and int(row.alarm_rows_lr_below_1) == int((both < 1).sum()) and np.isclose(row.lr_at_threshold, lr_thr)
                                              and np.isclose(row.iso_step_left, lo_x) and np.isclose(row.iso_step_right, hi_x)
                                              and int(row.step_normal_cal_rows) == step_norm and int(row.step_abnormal_rows) == step_abn))
rd = read(G / "README.md")
r2o12_doc = dict(has_min_lr=("108.9" in rd and "2.42" in rd), has_lr_below_1_zero=("LR<1 0행" in rd),
                 has_false_alarm_055=("B 정상 오경보 3행도 LR 상한 121이라 π 1%에서 0.55" in rd), has_cannot_filter=("확률 층으로 오경보를 거를 수 없다" in rd),
                 has_step_text=("[2.896, 3.520]" in rd and "정상 보정 9행과 이상 1행" in rd and "3.561" in rd))
OUT["C8b_probability_layer_and_R2_O12"] = dict(splits=c8b, readme=r2o12_doc)
log("C8b 확률 층: " + " | ".join(
    f"{s} 21겹 Brier {v['brier_21fold']:.4f} ECE {v['ece_21fold']:.4f}(커밋 일치 {v['matches_committed']}), 상한 {v['lr_cap_saved']:.0f}, "
    f"문턱 {v['threshold']:.3f} LR {v['lr_at_threshold']:.3f}(π1% {v['p_at_threshold_pi1']:.3f}), 계단 [{v['iso_step_left']:.3f}, 문턱] 정상 {v['step_normal_cal_rows']}·이상 {v['step_abnormal_rows']} "
    f"P̂ {v['step_fitted_left']:.3f}(π_fit {v['pi_fit']:.3f}), 다음 매듭 {v['iso_step_right']:.3f} P̂ {v['fitted_at_right_knot']:.2f}, "
    f"경보 {v['alarm_rows']}행 최소 LR {v['alarm_rows_min_lr']:.2f}(π1% {v['alarm_rows_min_p_pi1']:.3f}) LR<1 {v['alarm_rows_lr_below_1']}, "
    f"오경보 {v['false_alarm_rows']}행 확률 {[round(p, 3) for p in v['false_alarm_p_pi1']]} · 변환표 일치 {v['matches_conversion_csv']}"
    for s, v in c8b.items()) + f" · README R2-O12 문장 {r2o12_doc}")
tick("C8b", t0)

# ---------------------------------------------------------------- C8c R2-O8: SBB 모의와 문구
t0 = time.monotonic()
rng = np.random.default_rng(7)
pi, tpr, n_cal, draws, per_draw = .01, .955, 120, 4000, 20000
alarm_normal, alarm_anom, ratio_by_draw = 0, 0, []
for _ in range(draws):
    far = 1.0 - rng.beta(n_cal, 1)
    is_anom = rng.random(per_draw) < pi
    an = int((~is_anom & (rng.random(per_draw) < far)).sum())
    aa_ = int((is_anom & (rng.random(per_draw) < tpr)).sum())
    alarm_normal += an
    alarm_anom += aa_
    if an + aa_:
        ratio_by_draw.append(aa_ / (an + aa_))
p_emp = alarm_anom / (alarm_normal + alarm_anom)
sbb_bf = -math.e * (1 / 121) * math.log(1 / 121)
sbb_p = pi * (1 / sbb_bf) / (pi * (1 / sbb_bf) + 1 - pi)
scan_files = [G / "README.md", G / "OPERATIONS.md", G / "probability.py", G / "insights.py", G / "web" / "index.html", G / "web" / "app.js",
              G / "outputs" / "probability_conversion_v2.csv", G / "outputs" / "label_free_alert_probability_v2.csv", G / "HISTORY.md"]
sbb_lines, bad = [], []
for p in scan_files:
    L = lines_of(p)
    for i, ln in enumerate(L, 1):
        if re.search(r"sellke|sbb|bayarri", ln, re.I):
            if p.suffix == ".py" and re.match(r"\s*(from|import)\s", ln):
                continue                                  # import 줄(식별자 alert_evidence_bound 등)은 주장이 아니다
            # docstring은 몇 줄 이어진다: 같은 줄과 다음 세 줄을 한 문맥으로 본다
            ctx = " ".join(L[i - 1:i + 3]) if p.suffix == ".py" else ln
            claims_bound = bool(re.search(r"상한|이하", ctx))
            negated = bool(re.search(r"상한이 아니|상한 아님", ctx))
            sbb_lines.append(dict(file=str(p.relative_to(Y)), line=i, claims_bound=claims_bound, negated=negated, reference=("참고" in ctx)))
            if claims_bound and not negated:
                bad.append((str(p.relative_to(Y)), i))
conv_df = pd.read_csv(G / "outputs" / "probability_conversion_v2.csv")
csv_cols = conv_df.columns.tolist()
sbb_note_ok = bool(conv_df.sbb_note.str.contains("참고값").all() and conv_df.sbb_note.str.contains("상한이 아니다").all())
OUT["C8c_R2_O8_SBB"] = dict(setting=dict(pi=pi, tpr=tpr, n_cal=n_cal, draws=draws, units_per_draw=per_draw),
                            empirical_P_anomaly_given_alarm=p_emp, analytic=pi * tpr / (pi * tpr + (1 - pi) / 121), sbb_lr=1 / sbb_bf, sbb_p=sbb_p,
                            share_of_draws_exceeding_sbb=float(np.mean(np.asarray(ratio_by_draw) > sbb_p)),
                            sbb_mentions=sbb_lines, unnegated_bound_claims=bad,
                            csv_columns_sbb=[c for c in csv_cols if c.startswith("sbb")], csv_sbb_note_reference_and_not_bound=sbb_note_ok,
                            old_column_names_absent=not any(c in csv_cols for c in ("sbb_lr_bound", "sbb_p_bound")))
log(f"C8c R2-O8: 알림 p값은 모두 1/121인데 모의 P(이상|알림) {p_emp:.3f}(해석값 {OUT['C8c_R2_O8_SBB']['analytic']:.3f}) > SBB 값 {sbb_p:.3f}; "
    f"보정 표본 {draws}회 중 {OUT['C8c_R2_O8_SBB']['share_of_draws_exceeding_sbb']:.1%}에서 넘음 · SBB 언급 {len(sbb_lines)}곳, 부정 없는 상한 주장 {len(bad)}곳, "
    f"CSV 열 {OUT['C8c_R2_O8_SBB']['csv_columns_sbb']}(옛 열 없음 {OUT['C8c_R2_O8_SBB']['old_column_names_absent']}, 설명 열 10행 '참고값·상한이 아니다' {sbb_note_ok})")
tick("C8c", t0)

# ---------------------------------------------------------------- C8d 테스트 예측 파일 채점·상한 행·신뢰도 최상위 구간
c8d = {}
rel = pd.read_csv(G / "outputs" / "probability_reliability_v2.csv")
for s in "AB":
    tp_ = pd.read_csv(G / "outputs" / f"test_predictions_{s}.csv")
    yv = tp_.label.to_numpy(float)
    p1 = np.clip(tp_.anomaly_probability.to_numpy(float), 1e-9, 1 - 1e-9)
    pf = np.clip(tp_.anomaly_probability_file_prior.to_numpy(float), 1e-9, 1 - 1e-9)
    at_cap = np.isclose(tp_.likelihood_ratio.to_numpy(float), 121.0)
    ab = tp_.subset.eq("abnormal").to_numpy()
    fa = (~ab) & (tp_.alarm.to_numpy() == 1)
    # 파일의 이상 행 LR이 이 검수의 교차 적합(C8b)과 같은가
    same_oof = bool(np.allclose(tp_.likelihood_ratio.to_numpy(float)[ab], oof[s], rtol=1e-9, atol=1e-9))
    top = rel[(rel.split == s)].iloc[-1]
    c8d[s] = dict(rows=len(tp_), file_prior=float(tp_.file_prior.iloc[0]), brier_pi1=float(np.mean((p1 - yv) ** 2)), ece_pi1=ece(yv, p1),
                  brier_file_prior=float(np.mean((pf - yv) ** 2)), ece_file_prior=ece(yv, pf),
                  abnormal_rows_at_cap=int((at_cap & ab).sum()), false_alarm_rows_at_cap=int((at_cap & fa).sum()), false_alarm_rows=int(fa.sum()),
                  abnormal_lr_equals_judge_oof=same_oof,
                  reliability_top_bin=dict(bin=top["bin"], mean_predicted=float(top.mean_predicted), observed=float(top.observed),
                                           conservative=bool(top.mean_predicted < top.observed)))
OUT["C8d_prediction_file_probability"] = c8d
log("C8d 예측 파일: " + " | ".join(
    f"{s} π1% Brier {v['brier_pi1']:.4f} ECE {v['ece_pi1']:.4f}, 파일 비율 {v['file_prior']:.3f} Brier {v['brier_file_prior']:.4f} ECE {v['ece_file_prior']:.4f}, "
    f"상한 행 이상 {v['abnormal_rows_at_cap']}/600·오경보 {v['false_alarm_rows_at_cap']}/{v['false_alarm_rows']}, 이상 행 LR = 검수 교차 적합 {v['abnormal_lr_equals_judge_oof']}, "
    f"최상위 구간 예측 {v['reliability_top_bin']['mean_predicted']:.3f} < 관측 {v['reliability_top_bin']['observed']:.3f}: {v['reliability_top_bin']['conservative']}"
    for s, v in c8d.items()))

# ---------------------------------------------------------------- C9b 0.6 Hz 위상 시험
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


def window_phase(idx, f, t_rel=False):
    out = np.empty(len(idx))
    for i in range(len(idx)):
        t = tsec[idx[i]] - (tsec[idx[i][0]] if t_rel else 0)
        A = np.column_stack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(idx.shape[1])])
        c = np.linalg.lstsq(A, cur[idx[i]], rcond=None)[0]
        out[i] = np.arctan2(c[1], c[0])
    return out


def R(d):
    return float(np.abs(np.mean(np.exp(1j * np.asarray(d)))))


d06 = window_phase(begins, .6) - window_phase(ends, .6)
long_recs = [np.flatnonzero(seg_all == r) for r in rec_codes if (seg_all == r).sum() >= 50]
ctrl = window_phase(np.array([ix[-20:] for ix in long_recs]), .6) - window_phase(np.array([ix[:20] for ix in long_recs]), .6)
starts = window_phase(np.array([np.flatnonzero(seg_all == r)[:20] for r in rec_codes if (seg_all == r).sum() >= 20]), .6, t_rel=True)
pc = pd.read_csv(EV / "phase_continuity.csv")
c9b = dict(pairs=int(len(d06)), R_neighbors=R(d06), positive_control=R(ctrl), start_phase=R(starts))
c9b["matches_committed_R"] = bool(np.isclose(c9b["R_neighbors"], pc.R.iloc[1], atol=1e-9) and np.isclose(c9b["positive_control"], pc.R.iloc[0], atol=1e-9)
                                  and np.isclose(c9b["start_phase"], pc.R.iloc[5], atol=1e-9))
OUT["C9b_phase"] = c9b
log(f"C9b 위상: 양성 대조 R {c9b['positive_control']:.3f}, 이웃 {c9b['pairs']}쌍 R {c9b['R_neighbors']:.3f}, 시작 위상 R {c9b['start_phase']:.3f} · 커밋 일치 {c9b['matches_committed_R']}")

# ---------------------------------------------------------------- C10·C16 관측 성질 + R2-O10
obs_t = pd.read_csv(EV / "observability.csv")
obs_lines = lines_of(EV / "observability.csv")
c10 = {}
for name, fr in (("normal", normal), ("abnormal", abnormal)):
    sg = D.segments(fr)
    same = np.r_[False, sg[1:] == sg[:-1]]
    for c in D.SENSORS:
        x = fr[c].to_numpy(float)
        lag1 = float(np.corrcoef(x[1:][same[1:]], x[:-1][same[1:]])[0, 1])
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
        xm = x - pd.Series(x).groupby(sg).transform("mean").to_numpy()
        ref = obs_t[(obs_t.file == name) & (obs_t.sensor == c)].iloc[0]
        got = dict(share_negative=float((x < 0).mean()), lag1_within=lag1,
                   lag1_mean_removed=float(np.corrcoef(xm[1:][same[1:]], xm[:-1][same[1:]])[0, 1]),
                   share_power_le_1hz=float(P[(f > 0) & (f <= 1.0)].sum() / P[f > 0].sum()), records_ge20=len(lag_rec),
                   records_lag1_gt_0_5=int(np.sum(np.asarray(lag_rec) > .5)))
        c10[f"{name}/{c}"] = dict(**got, matches=all(np.isclose(v, ref[k]) for k, v in got.items()), interpretation=ref.interpretation)
ab_vib = obs_t[(obs_t.file == "abnormal") & obs_t.sensor.isin(D.SENSORS[:2])]
ab_cur = obs_t[(obs_t.file == "abnormal") & (obs_t.sensor == D.SENSORS[2])].iloc[0]
fm = pd.read_csv(EV / "failure_mode_map.csv")
fmm = fm.set_index("fm_id")
cite = "yejun/analysis/press_evidence/observability.csv:5-6"
cited_rows = [obs_lines[4].split(",")[:2], obs_lines[5].split(",")[:2]]
r2o10 = dict(abnormal_vib_no_low_lag_phrase=not ab_vib.interpretation.str.contains("이웃 표본 상관 낮음").any(),
             abnormal_vib_says_high_lag=bool(ab_vib.interpretation.str.contains("이웃 표본 상관이 높다").all()),
             abnormal_current_not_called_sine=("0.6 Hz 사인형" not in ab_cur.interpretation) and ("사인형이 깨졌다" in ab_cur.interpretation),
             fm_rows_citing=[k for k in ("FM1", "FM2", "FM3") if cite in str(fmm.loc[k, "confirmed_in_this_data"])],
             cited_lines_are_abnormal_vibration=cited_rows == [["abnormal", "AI0_Vibration"], ["abnormal", "AI1_Vibration"]],
             readme_O4a_has_values=all(t in read(EV / "README.md") for t in ("0.704·0.632", "0.60·0.55", "12·13개")))
OUT["C10_C16_observability_and_R2_O10"] = dict(by_file_sensor=c10, R2_O10=r2o10)
log("C10·C16 관측 성질(음수 비율/lag-1/평균 제거 lag-1/1 Hz 이하 비중/lag-1>0.5 기록): " + ", ".join(
    f"{k} {v['share_negative']:.3f}/{v['lag1_within']:.3f}/{v['lag1_mean_removed']:.3f}/{v['share_power_le_1hz']:.2f}/{v['records_lag1_gt_0_5']}of{v['records_ge20']}"
    for k, v in c10.items() if "Current" not in k) + f" · 커밋 표 일치 {all(v['matches'] for v in c10.values())} · R2-O10 {r2o10}")

# ---------------------------------------------------------------- C11 재보정 실행
t0 = time.monotonic()
import recalibrate  # noqa: E402

with tempfile.TemporaryDirectory(prefix="judge05r3_recal_") as tmp:
    src = Path(tmp) / "normal_0_479.csv"
    normal[seg_all < 480].to_csv(src, index=False)
    code = recalibrate.main(["--normal", str(src), "--out", str(Path(tmp) / "site.json"), "--report", str(Path(tmp) / "site_report.json")])
    report = json.loads((Path(tmp) / "site_report.json").read_text())
OUT["C11_recalibrate"] = dict(exit_code=code, passed=report["passed"], units=report["units"],
                              checks=[{k: c.get(k) for k in ("name", "value", "limit", "ok", "false_reject_rate", "power_if_rate_multiplied")} for c in report["checks"]])
log(f"C11 recalibrate 종료 코드 {code}, 통과 {report['passed']}: " + "; ".join(f"{c['name']} = {c['value']} (한도 {c['limit']})" for c in report["checks"]))
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

# ---------------------------------------------------------------- C13 지도학습 재실행
if not SKIP_SUP:
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="judge05r3_sup_") as tmp:
        proc = subprocess.run([sys.executable, str(SV / "run.py"), "--out", tmp], capture_output=True, text=True,
                              env=dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1"))
        same_bytes = {n: filecmp.cmp(Path(tmp) / n, SV / n, shallow=False) for n in ("random_rows.csv", "grouped_records.csv", "injection.csv")}
        gr = pd.read_csv(Path(tmp) / "grouped_records.csv")
    sel = gr[(gr.cv == "21fold") & (gr.threshold == "conformal")]
    v2f1 = {"A": c1["A"]["0.01"]["f1"], "B": c1["B"]["0.01"]["f1"]}
    diffs = [float(r.f1 - v2f1[r.split]) for r in sel[sel.features == "window_plus_v2"].itertuples() if r.model in ("logistic", "hgb")]
    diffs_bal = [float(r.f1 - v2f1[r.split]) for r in sel[sel.features == "window_plus_v2"].itertuples() if r.model.endswith("balanced")]
    OUT["C13_supervised"] = dict(returncode=proc.returncode, csv_byte_identical=same_bytes, f1_minus_v2_unweighted_range=[min(diffs), max(diffs)],
                                 f1_minus_v2_all_range=[min(diffs + diffs_bal), max(diffs + diffs_bal)], stderr_tail=proc.stderr.strip().splitlines()[-3:])
    log(f"C13 지도학습 재실행 코드 {proc.returncode}, CSV 바이트 동일 {same_bytes} · 창+v2 지도학습−v2 F1(가중치 없음) {min(diffs):+.3f}~{max(diffs):+.3f}, "
        f"가중 포함 {min(diffs + diffs_bal):+.3f}~{max(diffs + diffs_bal):+.3f}")
    tick("C13", t0)

# ---------------------------------------------------------------- C14·C15
dt = pd.read_csv(G / "outputs" / "decision_table_v2.csv")
refs = sorted({x for v in dt.failure_modes.dropna() for x in re.findall(r"FM\d", v)})
OUT["C14_failure_mode_refs"] = dict(decision_table_refs=refs, all_refs_exist=set(refs) <= set(fm.fm_id))
hits = []
for p in [G / "README.md", G / "OPERATIONS.md", G / "web" / "index.html", G / "web" / "app.js", EV / "README.md", SEL / "README.md", SV / "README.md"]:
    for i, line in enumerate(lines_of(p), 1):
        if re.search(r"1\s*[−-]\s*p", line) and "확률" in line:
            hits.append(dict(file=str(p.relative_to(Y)), line=i, negated=bool(re.search(r"확률\s*아님|확률이 아니", line))))
OUT["C15_one_minus_p_wording"] = dict(lines=hits, all_negated=all(h["negated"] for h in hits))
log(f"C14 판단표 FM 참조 {refs} 모두 존재 {OUT['C14_failure_mode_refs']['all_refs_exist']} · C15 '1−p'+'확률' {len(hits)}줄, 모두 '확률 아님' {OUT['C15_one_minus_p_wording']['all_negated']}")

# ---------------------------------------------------------------- C17 R2-O11 앨리어싱 조건
evr = lines_of(EV / "README.md")
gen = [i for i, ln in enumerate(evr, 1) if "k·10 ± 0.6 Hz" in ln]
inverter = [i for i, ln in enumerate(evr, 1) if "인버터" in ln and "50.6·40.6" in ln]
pue = pd.read_csv(EV / "production_unit_evidence.csv")
pue_row = pue[pue.item.str.contains("0.6 Hz 해석 조건", na=False)]
old_claim = []
for p in [EV / "README.md", G / "README.md", EV / "failure_mode_map.csv", EV / "production_unit_evidence.csv", EV / "variable_dictionary.csv"]:
    for i, ln in enumerate(lines_of(p), 1):
        if re.search(r"따라서.*59\.4·60\.6 Hz다|원 신호가 59\.4·60\.6 Hz다", ln):
            old_claim.append((str(p.relative_to(Y)), i))
phase_line = [i for i, ln in enumerate(evr, 1) if "위상 시험은 앨리어싱의 원 주파수를 가리지 않는다" in ln]
OUT["C17_R2_O11_aliasing"] = dict(readme_general_form_lines=gen, readme_inverter_lines=inverter, production_unit_row=pue_row.interpretation.tolist(),
                                  old_unconditional_claims=old_claim, phase_test_consistency_lines=phase_line,
                                  remaining_60hz_conditionals=[(str(p.relative_to(Y)), i) for p in (EV / "failure_mode_map.csv", EV / "ar2_oscillator.csv", EV / "class_differences.csv")
                                                               for i, ln in enumerate(lines_of(p), 1) if "60 Hz 앨리어싱" in ln or "60 Hz 순시값" in ln])
log(f"C17 R2-O11: 일반형 README:{gen}, 인버터 예시 {inverter}, 생산단위 표 행 {len(pue_row)}, 옛 단정 문장 {old_claim}, 위상 시험 일관 문장 {phase_line}, "
    f"남은 '60 Hz' 조건문 {len(OUT['C17_R2_O11_aliasing']['remaining_60hz_conditionals'])}곳(가정형)")

# ---------------------------------------------------------------- C18 정상 운전 2수준 상태(독립 재계산)
t0 = time.monotonic()
curN = normal.AI2_Current.to_numpy(float)
segdf = pd.DataFrame(dict(seg=seg_all, cur=curN)).groupby("seg").cur
n_by = segdf.size()
rms = segdf.apply(lambda x: float(np.sqrt(np.mean((x - x.mean()) ** 2))))
Lrec = rms[n_by >= 17]
xl = np.log(Lrec.to_numpy()).reshape(-1, 1)
gms = {k: GaussianMixture(k, random_state=0, n_init=5).fit(xl) for k in (1, 2, 3)}
bic = {k: float(g.bic(xl)) for k, g in gms.items()}
g2 = gms[2]
lo_c = int(np.argmin(g2.means_.ravel()))
grid = np.linspace(np.log(60), np.log(200), 14001).reshape(-1, 1)
pl = g2.predict_proba(grid)[:, lo_c]
cross = np.exp(grid[:, 0])[np.where(np.diff(np.sign(pl - .5)) != 0)[0]]
boundary = float([c for c in cross if c > np.exp(g2.means_.ravel()[lo_c])][0])
state = pd.Series(np.where(g2.predict(xl) == lo_c, "low", "load"), index=Lrec.index)
comp_split = {}
for sid, (lo, hi) in {"A cal": (360, 480), "A eval": (480, 600), "B cal": (300, 420), "B eval": (420, 600)}.items():
    sub = state[(state.index >= lo) & (state.index < hi)]
    comp_split[sid] = [int((sub == "low").sum()), int(len(sub))]
alarms_by_state = {}
for s in "AB":
    mp = pd.Series(record_minp(preds[s][0]))
    mp.index = mp.index + D.SPLITS[s][2]
    st_ = state.reindex(mp.index).fillna("short")
    alarms_by_state[s] = {str(a): {g: [int((mp[st_ == g] <= a).sum()), int((st_ == g).sum())] for g in ("load", "low", "short")} for a in (.01, .03, .05)}
oss = pd.read_csv(EV / "operating_states_summary.csv")
committed_bic = oss[oss.item.str.contains("BIC")].value.astype(float).tolist()
committed_boundary = float(oss[oss.item.str.contains("2성분 경계\\(저수준")].value.iloc[0])
ssc = pd.read_csv(EV / "split_state_composition.csv").set_index("part")
comp_match = all(comp_split[k] == [int(ssc.loc[p, "low"]), int(ssc.loc[p, "records_len17"])] for k, p in
                 (("A cal", "A 보정"), ("A eval", "A 평가"), ("B cal", "B 보정"), ("B eval", "B 평가")))
nas = pd.read_csv(EV / "normal_alarms_by_state.csv")
nas_match = True
for s in "AB":
    for a in (.01, .03, .05):
        for g, kor in (("load", "부하"), ("low", "저수준"), ("short", "짧은 기록(<17)")):
            r = nas[(nas.section == "상태별 정상 알림") & (nas.group == f"동결 {s}") & np.isclose(nas.alpha, a) & (nas.state == kor)].iloc[0]
            nas_match &= [int(r.alerted), int(r.records)] == alarms_by_state[s][str(a)][g]
OUT["C18_operating_states"] = dict(records_len17=int(len(Lrec)), bic=bic, committed_bic=committed_bic, boundary=boundary, committed_boundary=committed_boundary,
                                   state_counts=state.value_counts().to_dict(), split_composition=comp_split, split_composition_matches=bool(comp_match),
                                   normal_alarms_by_state=alarms_by_state, normal_alarms_by_state_matches=bool(nas_match),
                                   all_normal_alarms_in_load=all(v["low"][0] == 0 and v["short"][0] == 0 for s in alarms_by_state.values() for v in s.values()))
log(f"C18 운전 상태: 기록 {len(Lrec)}, BIC 1·2·3 {bic[1]:.1f}/{bic[2]:.1f}/{bic[3]:.1f}(커밋 {[round(v, 1) for v in committed_bic]}), 경계 {boundary:.2f}(커밋 {committed_boundary:.2f}), "
    f"상태 {state.value_counts().to_dict()}, 분할 저수준 {comp_split}(일치 {comp_match}), 상태별 정상 알림 A {alarms_by_state['A']['0.01']['load']}·{alarms_by_state['A']['0.03']['load']}·{alarms_by_state['A']['0.05']['load']} "
    f"B {alarms_by_state['B']['0.01']['load']}·{alarms_by_state['B']['0.03']['load']}·{alarms_by_state['B']['0.05']['load']}(부하), 모든 정상 알림 부하 {OUT['C18_operating_states']['all_normal_alarms_in_load']}, 커밋 표 일치 {nas_match}")
tick("C18", t0)

# ---------------------------------------------------------------- C19 감시 조치 분기 기능 시험
t0 = time.monotonic()
import monitor  # noqa: E402

mB = models["B"]
refB = monitor.Reference.from_frame(pd.concat([splits["B"]["train"], splits["B"]["cal"]], ignore_index=True))
testB = D.inputs_only(splits["B"]["test"]).copy()
for c in D.SENSORS:
    testB[c] = pd.to_numeric(testB[c], errors="coerce")
first_ts = str(testB[D.TIME].iloc[5])


def run_monitor(frame, changes=()):
    win = monitor.monitor_windows(mB.predict(frame, .01), frame, .01, len(mB.cal), refB, 60, changes)
    return [dict(window=int(r.window), alerted=int(r.alerted_units), limit95=int(r.limit95), limit99=int(r.limit99), drift_up=bool(r.drift_up),
                 change=bool(r.operating_change), ratio=round(float(r.current_ratio), 3), action=r.recommended_action) for r in win.itertuples()]


scen = {}
for gain in (1.0, 1.3, 1.5):
    f = testB.copy()
    f[D.SENSORS[2]] = f[D.SENSORS[2]] * gain
    scen[f"current_gain_{gain:g}"] = run_monitor(f)
    if gain == 1.3:
        scen["current_gain_1.3_with_change_record"] = run_monitor(f, [first_ts])
rng = np.random.default_rng(11)
fv = testB.copy()
for k, c in enumerate(D.SENSORS[:2]):
    fv[c] = fv[c] + 2.0 * mB.scale[k] * rng.standard_normal(len(fv))
scen["vibration_noise_2sigma_all_rows"] = run_monitor(fv)
OUT["C19_monitor_branch"] = dict(scenarios=scen, band_high=refB.band_high,
                                 fm4_uses_current_gain_proxy=("전류 배율" in str(fmm.loc["FM4", "e1_proxy"]) and "1.5 A 72.0%" in str(fmm.loc["FM4", "evidence"])),
                                 fm5_uses_current_gain_proxy=("전류 배율" in str(fmm.loc["FM5", "e1_proxy"]) and "1.5 A 72.0%" in str(fmm.loc["FM5", "evidence"])),
                                 fm4_expected_change=str(fmm.loc["FM4", "expected_change_10hz"]),
                                 note="전류 배율 1.5는 고장 모드표 FM4·FM5의 대리 주입이다. 변경 기록이 없어도 수준 이동 창은 '재보정 검토'로 분기한다.")
log("C19 감시 분기(B, α1%, 창 60단위): " + " | ".join(f"{k}: " + ", ".join(f"창{w['window']} {w['alerted']}(한도 {w['limit95']}/{w['limit99']}) 비 {w['ratio']} → {w['action']}" for w in v)
                                                     for k, v in scen.items()) + f" · FM4·FM5 대리 주입에 배율 1.5 사용 {OUT['C19_monitor_branch']['fm4_uses_current_gain_proxy']}/{OUT['C19_monitor_branch']['fm5_uses_current_gain_proxy']}")
tick("C19", t0)

# ---------------------------------------------------------------- C20 같은 특징 대안 주입 전이(독립 재구현 일부)
t0 = time.monotonic()
rt = pd.read_csv(SEL / "rule_transfer_injection_v2.csv")


def my_conformal_p(cal, s):
    ref = np.sort(np.where(np.isfinite(cal), cal, -np.inf))
    out = np.full(len(s), np.nan)
    ok = np.isfinite(s)
    out[ok] = (len(ref) - np.searchsorted(ref, s[ok], side="left") + 1) / (len(ref) + 1)
    return out


def my_rules(comp, nn):
    g = np.column_stack([comp["g_magnitude"], comp["g_waveform"], comp["g_dynamics"]])
    fu = fusions(comp)
    return {"v2_fmax": comp["score"], "fisher": fu["fisher"], "stouffer": fu["stouffer"], "sum": fu["sum"],
            "5nn": nn.kneighbors(np.nan_to_num(g, nan=0.0))[0].mean(1)}


def comp_of(model, frame):
    q = D.quantize(D.inputs_only(frame), "matched")
    seg = layout(q)[1]
    pos = D.segment_positions(seg)[0]
    return model.components(q, seg), seg, pos


c20, c20_mism = [], []
for s in "AB":
    mdl = models[s]
    ctr, _, _ = comp_of(mdl, splits[s]["train"])
    nn = NearestNeighbors(n_neighbors=5).fit(np.nan_to_num(np.column_stack([ctr["g_magnitude"], ctr["g_waveform"], ctr["g_dynamics"]]), nan=0.0))
    ccal, cseg, cpos = comp_of(mdl, splits[s]["cal"])
    cun = alert_units(cseg, cpos)
    rule_cal = {k: segment_max(v, cun) for k, v in my_rules(ccal, nn).items()}
    assert np.array_equal(rule_cal["v2_fmax"], mdl.cal)
    test = splits[s]["test"]
    _, tseg = layout(test)
    tpos = D.segment_positions(tseg)[0]
    units = alert_units(tseg, tpos)
    in_unit = tpos % 50
    size = pd.Series(units).map(pd.Series(units).value_counts()).to_numpy()
    elig = size >= 30
    window = (in_unit >= 10) & (in_unit < 30)
    for family, level in (("vib_shock", 4.0), ("vib_noise", 2.0), ("cur_offset", .2)):
        reps = 1 if family == "cur_offset" else 5
        hits = {k: [] for k in rule_cal}
        for rep in range(reps):
            r_ = np.random.default_rng(rep)
            X = D.inputs_only(test).copy()
            for c in D.SENSORS:
                X[c] = pd.to_numeric(X[c], errors="coerce")
            if family == "vib_shock":
                mask = elig & (in_unit == 10)
                sign = r_.choice(np.array([-1.0, 1.0]), size=(int(mask.sum()), 2))
                for k, c in enumerate(D.SENSORS[:2]):
                    X.loc[mask, c] += level * mdl.scale[k] * sign[:, k]
            else:
                mask = elig & (in_unit >= 10)
                if family == "vib_noise":
                    for k, c in enumerate(D.SENSORS[:2]):
                        X.loc[mask, c] += level * mdl.scale[k] * r_.standard_normal(int(mask.sum()))
                else:
                    X.loc[mask, D.SENSORS[2]] += level * np.sqrt(2) * mdl.scale[2]
            comp, _, _ = comp_of(mdl, X)
            for k, sc in my_rules(comp, nn).items():
                hit = (np.nan_to_num(my_conformal_p(rule_cal[k], sc), nan=1.0) <= .01) & window & elig
                hits[k].append(pd.Series(hit[elig]).groupby(units[elig]).any().to_numpy())
        ref = rt[(rt.split_id == s) & np.isclose(rt.alpha, .01) & (rt.family == family) & np.isclose(rt.level, level)].iloc[0]
        got = {k: float(np.concatenate(v).mean()) for k, v in hits.items()}
        ok = all(np.isclose(got[k], ref[f"{k}_detect_2s"], atol=1e-12) for k in got)
        if not ok:
            c20_mism.append((s, family, level, got))
        c20.append(dict(split=s, family=family, level=level, reps=reps, units=int(len(np.unique(units[elig]))), **{k: round(v * 100, 1) for k, v in got.items()}, match=ok))
OUT["C20_rule_transfer_partial"] = dict(rows=c20, mismatches=c20_mism)
log("C20 전이표 독립 재구현(α1%, fmax/Fisher/합/5NN/Stouffer %): " + " | ".join(
    f"{r['split']} {r['family']} {r['level']:g}: {r['v2_fmax']}/{r['fisher']}/{r['sum']}/{r['5nn']}/{r['stouffer']} 일치 {r['match']}" for r in c20))
tick("C20", t0)

# ---------------------------------------------------------------- C21 2단계 비사후 업무량
ee = pd.read_csv(G / "outputs" / "expected_effect_v2.csv")
wB = wl[(wl.split_id == "B") & (wl.model == "guard_v2") & np.isclose(wl.alpha, .01)].iloc[0]
nominal_l1 = float(wB.nominal_alerts_per_8h_elapsed)
ratio = 1 / 9
ub = float(stats.beta.ppf(.95, 1 + 1, 9 - 1))
est, est_ub = nominal_l1 * ratio, nominal_l1 * ub
r_est = ee[ee.alert_scenario.str.startswith("비사후 추정(")].level2_per_8h.iloc[0]
r_ub = ee[ee.alert_scenario.str.startswith("비사후 추정 95%")].level2_per_8h.iloc[0]
OUT["C21_level2_non_post_hoc"] = dict(nominal_level1_8h=nominal_l1, ratio=ratio, cp_upper=ub, estimate=est, estimate_upper=est_ub,
                                      committed=[float(r_est), float(r_ub)], match=bool(np.isclose(est, r_est) and np.isclose(est_ub, r_ub)))
log(f"C21 2단계 비사후: 1단계 명목 {nominal_l1:.2f} × 1/9 = {est:.2f}건, CP 95% 상한 비 {ub:.3f} → {est_ub:.2f}건 · 커밋 일치 {OUT['C21_level2_non_post_hoc']['match']}")

# ---------------------------------------------------------------- C22 정상 진동의 좁은 대역 구조(탐색)
t0 = time.monotonic()
DT = D.DT


def tone(x, f):
    t = np.arange(len(x)) * DT
    A = np.column_stack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(len(x))])
    c = np.linalg.lstsq(A, x, rcond=None)[0]
    return c


def best_f(x, f0, span=.15):
    """사인+상수 최소제곱의 잔차 제곱합을 최소로 하는 주파수(격자 301점 뒤 구간 정밀화)."""
    from scipy import optimize
    t = np.arange(len(x)) * DT

    def rss(f):
        A = np.column_stack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(len(x))])
        c = np.linalg.lstsq(A, x, rcond=None)[0]
        return float(((x - A @ c) ** 2).sum())
    fs = np.linspace(f0 - span, f0 + span, 301)
    i = int(np.argmin([rss(f) for f in fs]))
    r = optimize.minimize_scalar(rss, bounds=(fs[max(i - 1, 0)], fs[min(i + 1, len(fs) - 1)]), method="bounded")
    return float(r.x)


def harm_r2(x, n=8):
    t = np.arange(len(x)) * DT
    H = np.column_stack([np.ones(len(x))] + [g(2 * np.pi * .6 * k * t) for k in range(1, n + 1) for g in (np.cos, np.sin)])
    c = np.linalg.lstsq(H, x, rcond=None)[0]
    return float(1 - ((x - H @ c) ** 2).sum() / ((x - x.mean()) ** 2).sum())


c22 = {}
for name, fr in (("normal", normal), ("abnormal", abnormal)):
    sg = D.segments(fr)
    rows = []
    for r in np.unique(sg):
        idx = np.flatnonzero(sg == r)
        if len(idx) < 50:
            continue
        idx = idx[:50]
        cu, v0, v1 = (fr[c].to_numpy(float)[idx] for c in ("AI2_Current", "AI0_Vibration", "AI1_Vibration"))
        fc = best_f(cu, .6, .1)
        f0, f1 = best_f(v0 - v0.mean(), 3.6), best_f(v1 - v1.mean(), 1.8)
        cc_, c0, c1_ = tone(cu, .6), tone(v0, 3.6), tone(v1, 1.8)
        ph = lambda c: np.arctan2(-c[1], c[0])
        fz = np.fft.rfftfreq(500, DT)
        pk = lambda v: float(fz[1:][int(np.argmax((np.abs(np.fft.rfft((v - v.mean()) * np.hanning(50), n=500)) ** 2)[1:]))])   # 0 Hz 제외 최대
        rows.append(dict(record=int(r), fc=fc, f0=f0, f1=f1, amp_c=float(np.hypot(*cc_[:2])), amp0=float(np.hypot(*c0[:2])), amp1=float(np.hypot(*c1_[:2])),
                         sd0=float(v0.std()), sd1=float(v1.std()), d0=float((ph(c0) - 6 * ph(cc_)) % (2 * np.pi)), d1=float((ph(c1_) - 3 * ph(cc_)) % (2 * np.pi)),
                         peak0=pk(v0), peak1=pk(v1),
                         r2h0=harm_r2(v0), r2h1=harm_r2(v1)))
    d = pd.DataFrame(rows)
    c22[name] = dict(records_50rows=len(d), current_freq_median=float(d.fc.median()), current_freq_sd=float(d.fc.std()),
                     AI0_tone_freq_median=float(d.f0.median()), AI0_ratio_median=float((d.f0 / d.fc).median()), AI0_ratio_iqr=[float((d.f0 / d.fc).quantile(q)) for q in (.25, .75)],
                     AI1_tone_freq_median=float(d.f1.median()), AI1_ratio_median=float((d.f1 / d.fc).median()), AI1_ratio_iqr=[float((d.f1 / d.fc).quantile(q)) for q in (.25, .75)],
                     harmonic_r2_median_AI0=float(d.r2h0.median()), harmonic_r2_median_AI1=float(d.r2h1.median()),
                     tone_rms_share_of_sd_AI0=float(np.median(d.amp0 / np.sqrt(2) / d.sd0)), tone_rms_share_of_sd_AI1=float(np.median(d.amp1 / np.sqrt(2) / d.sd1)),
                     tone_amp_median_AI0=float(d.amp0.median()), tone_amp_median_AI1=float(d.amp1.median()),
                     spearman_AI1_tone_amp_vs_current_amp=float(stats.spearmanr(d.amp1, d.amp_c)[0]), spearman_AI0_tone_amp_vs_current_amp=float(stats.spearmanr(d.amp0, d.amp_c)[0]),
                     spearman_AI1_tone_freq_vs_current_amp=float(stats.spearmanr(d.f1, d.amp_c)[0]),
                     phase_lock_R_AI0_vs_6x=R(d.d0), phase_lock_R_AI1_vs_3x=R(d.d1), random_R_scale=float(1 / np.sqrt(len(d))),
                     per_record_AI1_tone_freq=[round(v, 3) for v in d.f1.tolist()] if name == "abnormal" else None,
                     spectral_peak_AI0_iqr=[float(d.peak0.quantile(q)) for q in (.25, .5, .75)], spectral_peak_AI1_iqr=[float(d.peak1.quantile(q)) for q in (.25, .5, .75)],
                     spectral_peak_AI0_per_record=[round(v, 2) for v in d.peak0.tolist()] if name == "abnormal" else None,
                     spectral_peak_AI1_per_record=[round(v, 2) for v in d.peak1.tolist()] if name == "abnormal" else None)
fm3_hyp = str(fmm.loc["FM3", "expected_change_10hz"])
fm3_conf = str(fmm.loc["FM3", "confirmed_in_this_data"])
OUT["C22_vibration_tones"] = dict(by_file=c22, fm3_expected_change=fm3_hyp,
                                  fm3_confirmed_says_assumed_broadband=("이 행이 가정한 접힌 광대역 변화" in fm3_conf),
                                  fm3_premise_is_narrowband=("1×·2× 성분" in fm3_hyp),
                                  observability_mentions_tones=bool(obs_t.interpretation.str.contains(r"1\.8 Hz|3\.6 Hz|좁은 대역|조화").any()),
                                  evidence_readme_mentions_tones=bool(re.search(r"1\.8 Hz|3\.6 Hz|좁은 대역", read(EV / "README.md"))),
                                  note="탐색 분석. 50행 기록의 처음 50관측. 조화 R²는 0.6 Hz의 1~8배 사인·코사인 모형. 위상 R은 기록 상대 시각 기준 (진동 위상 − 3·6×전류 위상).")
n22, a22 = c22["normal"], c22["abnormal"]
log(f"C22 정상 진동(50행 {n22['records_50rows']}기록): 전류 {n22['current_freq_median']:.4f}±{n22['current_freq_sd']:.4f} Hz, AI1 성분 {n22['AI1_tone_freq_median']:.3f} Hz(비 {n22['AI1_ratio_median']:.3f}), "
    f"AI0 {n22['AI0_tone_freq_median']:.3f} Hz(비 {n22['AI0_ratio_median']:.3f}), 0.6 Hz 배수 조화 R² 중앙 AI1 {n22['harmonic_r2_median_AI1']:.3f}·AI0 {n22['harmonic_r2_median_AI0']:.3f}, "
    f"AI1 성분 진폭~전류 진폭 ρ {n22['spearman_AI1_tone_amp_vs_current_amp']:.3f}(AI0 {n22['spearman_AI0_tone_amp_vs_current_amp']:.3f}), AI1 성분 주파수~전류 진폭 ρ {n22['spearman_AI1_tone_freq_vs_current_amp']:.3f}, "
    f"위상 고정 R {n22['phase_lock_R_AI1_vs_3x']:.3f}·{n22['phase_lock_R_AI0_vs_6x']:.3f}(무작위 ≈{n22['random_R_scale']:.3f}), 성분 진폭 중앙 AI1 {n22['tone_amp_median_AI1']:.4f}·AI0 {n22['tone_amp_median_AI0']:.4f} · "
    f"이상(50행 {a22['records_50rows']}기록): 조화 R² AI1 {a22['harmonic_r2_median_AI1']:.3f}·AI0 {a22['harmonic_r2_median_AI0']:.3f}, 성분 RMS/SD AI1 {a22['tone_rms_share_of_sd_AI1']:.2f}·AI0 {a22['tone_rms_share_of_sd_AI0']:.2f}"
    f"(정상 {n22['tone_rms_share_of_sd_AI1']:.2f}·{n22['tone_rms_share_of_sd_AI0']:.2f}), 성분 진폭 중앙 AI1 {a22['tone_amp_median_AI1']:.4f}·AI0 {a22['tone_amp_median_AI0']:.4f} · "
    f"기록별 주기도표 최대 주파수: 정상 AI0 사분위 {[round(v, 2) for v in n22['spectral_peak_AI0_iqr']]}·AI1 {[round(v, 2) for v in n22['spectral_peak_AI1_iqr']]}, "
    f"이상 AI0 {a22['spectral_peak_AI0_per_record']}·AI1 {a22['spectral_peak_AI1_per_record']} · "
    f"FM3 전제 좁은 대역 {OUT['C22_vibration_tones']['fm3_premise_is_narrowband']}인데 '이 행이 가정한 접힌 광대역' 문구 {OUT['C22_vibration_tones']['fm3_confirmed_says_assumed_broadband']}, "
    f"관측·README에 좁은 대역 언급 {OUT['C22_vibration_tones']['observability_mentions_tones']}/{OUT['C22_vibration_tones']['evidence_readme_mentions_tones']}")
tick("C22", t0)

OUT["timing_s"] = TIMES
OUT["elapsed_s"] = round(time.monotonic() - T_START, 1)
(HERE / "judge05_verify.json").write_text(json.dumps(D.to_jsonable(OUT), ensure_ascii=False, indent=2), encoding="utf-8")
log(f"완료 {OUT['elapsed_s']}초 (구간별 {TIMES}) → {HERE / 'judge05_verify.json'}")
