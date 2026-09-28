"""평가관05 cycle2 round4. 원본/현재 작업사본 읽기, 이 폴더의 검수 JSON만 쓰기.

독립 계산: 결합 규칙·순위 p·교차 적합 LR·베타 이항·음조/조화/위상.
팀 모델의 특징 추출 및 추론은 그대로 사용해 실제 구현과 연결한다.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
from scipy import optimize, stats
from scipy.special import betaln, gammaln
from sklearn.isotonic import IsotonicRegression
from sklearn.neighbors import NearestNeighbors

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]
G = Y / "press_guard"
E = Y / "analysis/press_evidence"
S = Y / "analysis/press_selection"
sys.path.insert(0, str(G))
from model import D, alert_units, layout, load_bundle
import monitor
from probability import ProbabilityCalibrator

START = time.monotonic()
OUT = {"scope": "현재 승인된 작업사본의 창의성·차별성 검수. 대회 보고서 아님", "checks": {}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot():
    paths = [G / f for f in ("model.py", "probability.py", "monitor.py", "recalibrate.py", "insights.py", "README.md", "OPERATIONS.md", "web/app.js", "web/index.html", "outputs/manifest.json")]
    paths += sorted((G / "artifacts").glob("*.json"))
    paths += [E / f for f in ("README.md", "build_diagnostics.py", "diagnostic_probes.py", "observability.csv", "vibration_tones.csv", "failure_mode_map.csv", "normal_alarms_by_state.csv", "operating_states.csv", "state_transition_stress.csv")]
    paths += [S / f for f in ("README.md", "run.py", "combination_rules.csv", "same_feature_alternatives.csv", "rule_transfer_injection_v2.csv")]
    paths += [G / "outputs" / f for f in ("probability_eval_v2.csv", "probability_conversion_v2.csv", "label_free_alert_probability_v2.csv", "monitor_gain_v2.csv", "expected_effect_v2.csv", "workload_v2.csv", "alert_levels_v2.csv", "test_predictions_A.csv", "test_predictions_B.csv")]
    return {str(p.relative_to(Y)): sha(p) for p in paths}


def record(name, value):
    OUT["checks"][name] = value
    OUT["elapsed_seconds"] = round(time.monotonic() - START, 3)
    (HERE / "judge05_verify.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(name, json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def cpmax(values, groups):
    return pd.Series(values).groupby(groups).max().to_numpy()


def cp(cal, values):
    ref = np.sort(np.where(np.isfinite(cal), cal, -np.inf))
    values = np.asarray(values)
    return np.where(np.isfinite(values), (len(ref) + 1 - np.searchsorted(ref, values, side="left")) / (len(ref) + 1), np.nan)


def comps(model, frame):
    quant = D.quantize(D.inputs_only(frame), "matched")
    seg = layout(quant)[1]
    pos = D.segment_positions(seg)[0]
    return model.components(quant, seg), seg, pos, alert_units(seg, pos)


def rules(comp, nn=None):
    g = np.column_stack([comp[f"g_{key}"] for key in ("magnitude", "waveform", "dynamics")])
    k = np.isfinite(g).sum(axis=1)
    sums = np.nansum(g, axis=1)
    with np.errstate(all="ignore"):
        stouffer = np.nansum(stats.norm.isf(np.clip(10.0 ** -g, 1e-300, 1)), axis=1) / np.sqrt(np.maximum(k, 1))
    out = dict(v2_fmax=comp["score"], fisher=-stats.chi2.logsf(2 * np.log(10) * sums, 2 * np.maximum(k, 1)) / np.log(10),
               stouffer=stouffer, sum=sums, mean=sums / np.maximum(k, 1))
    out = {key: np.where(k > 0, values, np.nan) for key, values in out.items()}
    if nn is not None:
        out["5nn"] = nn.kneighbors(np.nan_to_num(g, nan=0))[0].mean(axis=1)
    return out


OUT["head_start"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Y, text=True).strip()
OUT["hashes_start"] = snapshot()
normal, abnormal, report = D.load(Y / "press_submission")
manifest = json.loads((G / "outputs/manifest.json").read_text())
model_hashes = {name: sha(G / "artifacts" / name) for name in manifest["artifacts"]}
assert model_hashes == manifest["artifacts"]
assert all(report["files"][k]["sha256"] == v for k, v in manifest["input_hashes"].items())
models = {s: load_bundle(G / "artifacts" / f"guard_{s}.json") for s in "AB"}
splits = {s: D.split_normal(normal, D.segments(normal), s) for s in "AB"}
record("C0_provenance", {"models": model_hashes, "input_sha256": manifest["input_hashes"], "working_tree_authorized": True})

# R3-O1: 현재 모델의 예측을 넣어 실제 감시 분기 및 재보정 자료 필터 실행.
mb = models["B"]
ref = monitor.Reference.from_frame(pd.concat([splits["B"]["train"], splits["B"]["cal"]], ignore_index=True))
test = D.inputs_only(splits["B"]["test"]).copy()
for c in D.SENSORS:
    test[c] = pd.to_numeric(test[c])
scenarios = {}
for gain in (1.0, 1.3, 1.5):
    frame = test.copy()
    frame[D.SENSORS[2]] *= gain
    pred = mb.predict(frame, .01)
    no = monitor.monitor_windows(pred, frame, .01, len(mb.cal), ref)
    yes = monitor.monitor_windows(pred, frame, .01, len(mb.cal), ref, operating_changes=no.start.tolist())
    assert yes.loc[yes.recalibration_review, "recommended_action"].eq(monitor.ACTION_RECALIBRATE).all()
    assert no.loc[~no.recalibration_review, "recommended_action"].eq(monitor.ACTION_OBSERVE).all()
    assert no.loc[no.recalibration_review & no.drift_up, "recommended_action"].eq(monitor.ACTION_INSPECT_SHIFT).all()
    assert no.loc[no.recalibration_review & ~no.drift_up, "recommended_action"].eq(monitor.ACTION_INSPECT).all()
    cols = ["window", "alerted_units", "limit95", "limit99", "current_ratio", "recommended_action"]
    scenarios[str(gain)] = {"no_change": no[cols].to_dict("records"), "change_record": yes.recommended_action.tolist()}
    if gain == 1.5:
        assert no.recommended_action.iloc[0] == monitor.ACTION_INSPECT_SHIFT
    if gain == 1.3:
        assert no.recommended_action.iloc[0] == monitor.ACTION_INSPECT
rng = np.random.default_rng(11)
frame = test.copy()
for k, c in enumerate(D.SENSORS[:2]):
    frame[c] += 2 * mb.scale[k] * rng.standard_normal(len(frame))
vwin = monitor.monitor_windows(mb.predict(frame, .01), frame, .01, len(mb.cal), ref)
assert vwin.loc[vwin.recalibration_review, "recommended_action"].eq(monitor.ACTION_INSPECT).all()
scenarios["vibration_noise_2sigma"] = vwin[["window", "alerted_units", "recommended_action"]].to_dict("records")
filters = []
for action in (monitor.ACTION_INSPECT_SHIFT, monitor.ACTION_INSPECT, monitor.ACTION_RECALIBRATE, monitor.ACTION_OBSERVE):
    for outcome in (None, "", "보류", "이상 확인", "정상 확인"):
        win = pd.DataFrame([dict(start=test[D.TIME].iloc[100], end=test[D.TIME].iloc[149], recommended_action=action)])
        if outcome is not None:
            win["outcome"] = outcome
        kept, info = monitor.exclude_unconfirmed_windows(test, win)
        expected = 50 if action.startswith("설비 점검 요청") and outcome != "정상 확인" else 0
        assert info["rows_removed"] == expected
        filters.append(dict(action=action, outcome=outcome, rows_removed=info["rows_removed"]))
record("C1_R3_O1_monitor_and_filter", dict(scenarios=scenarios, band_high=ref.band_high, outcome_filter_cases=filters))

# Beta-Binomial 정규화상수부터 독립 계산. 3/51의 공유 문턱 참고 p 포함.
def bbprob(m, a, b):
    k = np.arange(m + 1)
    return np.exp(gammaln(m + 1) - gammaln(k + 1) - gammaln(m - k + 1) + betaln(k + a, m - k + b) - betaln(a, b))

bb = []
for alpha in (.01, .03, .05):
    ell = math.floor(alpha * 121 + 1e-9)
    p = bbprob(60, ell, 121 - ell)
    limits = [int(np.searchsorted(p.cumsum(), level)) for level in (.95, .99)]
    assert limits == [monitor.alert_limit(alpha, 120, 60, level) for level in (.95, .99)]
    bb.append(dict(alpha=alpha, limits=limits, false_rejection95=float(p[limits[0] + 1:].sum())))
load_p = float(bbprob(51, 1, 61)[3:].sum())
assert abs(load_p - stats.betabinom.sf(2, 51, 1, 61)) < 1e-12
record("C2_beta_binomial", dict(limits=bb, load_3_of_51_shared_threshold_tail=load_p, fixed_rate_binomial_tail=float(stats.binom.sf(2, 51, 1 / 62))))

# 같은 특징·같은 정상 보정 규칙: 대회 관측 성능과 합성 전이의 이득/비용 재계산.
comb = pd.read_csv(S / "combination_rules.csv")
transfer = pd.read_csv(S / "rule_transfer_injection_v2.csv")
fusion_rows, transfer_rows, main = [], [], {}
component_cache = {}
for sid, model in models.items():
    ct, _, _, _ = comps(model, splits[sid]["train"])
    nn = NearestNeighbors(n_neighbors=5).fit(np.nan_to_num(np.column_stack([ct[f"g_{k}"] for k in ("magnitude", "waveform", "dynamics")]), nan=0))
    cc, _, _, uc = comps(model, splits[sid]["cal"])
    cn, sn, pn, un = comps(model, splits[sid]["test"])
    ca, sa, pa, ua = comps(model, abnormal)
    component_cache[sid] = cc, cn, ca, sa
    cal = {k: cpmax(v, uc) for k, v in rules(cc, nn).items()}
    assert np.array_equal(cal["v2_fmax"], model.cal)
    rn, ra = rules(cn, nn), rules(ca, nn)
    for alpha in (.01, .03, .05):
        reason_a = np.column_stack([cp(model.cal, ca[f"g_{k}"]) <= alpha for k in ("magnitude", "waveform", "dynamics")]).any(axis=1)
        for rule in ("v2_fmax", "fisher", "stouffer", "sum", "mean", "5nn"):
            an, aa = cp(cal[rule], rn[rule]) <= alpha, cp(cal[rule], ra[rule]) <= alpha
            got = dict(tp=int(aa.sum()), fp=int(an.sum()), fn=int((~aa).sum()), normal_alerted=int(cpmax(an, un).sum()),
                       no_evidence_alarms_abnormal=int((aa & ~reason_a).sum()))
            if rule != "5nn":
                refrow = comb[comb.split_id.eq(sid) & comb.alpha.eq(alpha) & comb.rule.eq("tippett_fmax" if rule == "v2_fmax" else rule)].iloc[0]
                assert all(int(refrow[k]) == v for k, v in got.items()), (sid, alpha, rule, got)
            else:
                alt = pd.read_csv(S / "same_feature_alternatives.csv")
                refrow = alt[alt.split_id.eq(sid) & alt.alpha.eq(alpha) & alt.candidate.eq("5NN(v2 성분)")].iloc[0]
                assert all(int(refrow[k]) == v for k, v in got.items()), (sid, alpha, rule, got)
            fusion_rows.append(dict(split=sid, alpha=alpha, rule=rule, **got))
            if alpha == .01 and rule == "v2_fmax":
                main[sid] = dict(**got, f1=2 * got["tp"] / (2 * got["tp"] + got["fp"] + got["fn"]))
    testframe = D.inputs_only(splits[sid]["test"]).copy()
    for c in D.SENSORS:
        testframe[c] = pd.to_numeric(testframe[c])
    size = pd.Series(un).map(pd.Series(un).value_counts()).to_numpy()
    eligible, local = size >= 30, pn % 50
    window = eligible & (local >= 10) & (local < 30)
    for family, level in (("none", 0), ("cur_noise", .1), ("cur_offset", .2), ("vib_noise", 2), ("vib_shock", 4)):
        reps = 5 if family in ("cur_noise", "vib_noise", "vib_shock") else 1
        hit = {(alpha, r): [] for alpha in (.01, .03, .05) for r in ("v2_fmax", "fisher", "stouffer", "sum", "5nn")}
        for rep in range(reps):
            rng = np.random.default_rng(rep)
            frame = testframe.copy()
            mask = eligible & (local >= 10)
            if family == "cur_noise":
                frame.loc[mask, D.SENSORS[2]] += level * model.scale[2] * rng.standard_normal(mask.sum())
            elif family == "cur_offset":
                frame.loc[mask, D.SENSORS[2]] += level * np.sqrt(2) * model.scale[2]
            elif family == "vib_noise":
                for k, c in enumerate(D.SENSORS[:2]):
                    frame.loc[mask, c] += level * model.scale[k] * rng.standard_normal(mask.sum())
            elif family == "vib_shock":
                mask = eligible & (local == 10)
                signs = rng.choice([-1., 1.], size=(mask.sum(), 2))
                for k, c in enumerate(D.SENSORS[:2]):
                    frame.loc[mask, c] += level * model.scale[k] * signs[:, k]
            rc = rules(comps(model, frame)[0], nn)
            for (alpha, rule), data in hit.items():
                al = (cp(cal[rule], rc[rule]) <= alpha) & window
                data.append(cpmax(al[eligible], un[eligible]))
        for alpha in (.01, .03, .05):
            expected = transfer[transfer.split_id.eq(sid) & transfer.alpha.eq(alpha) & transfer.family.eq(family) & transfer.level.eq(level)].iloc[0]
            got = {rule: float(np.concatenate(hit[alpha, rule]).mean()) for rule in ("v2_fmax", "fisher", "stouffer", "sum", "5nn")}
            assert all(abs(expected[f"{rule}_detect_2s"] - value) < 1e-12 for rule, value in got.items()), (sid, alpha, family, got)
            transfer_rows.append(dict(split=sid, alpha=alpha, family=family, level=level, **got))
record("C3_fusion_transfer", dict(main=main, observed_combinations=fusion_rows, transfer_conditions=transfer_rows, checked_transfer_values=len(transfer_rows) * 5))

# 21기록 leave-one-out 보정: 별도 IsotonicRegression으로 LR 및 확률 수치 확인.
prob_eval = pd.read_csv(G / "outputs/probability_eval_v2.csv")
def own_lr(normal_scores, anomaly_scores, values, cap=121):
    s0, s1 = normal_scores[np.isfinite(normal_scores)], anomaly_scores[np.isfinite(anomaly_scores)]
    y = np.r_[np.zeros(len(s0)), np.ones(len(s1))]
    iso = IsotonicRegression(out_of_bounds="clip").fit(np.r_[s0, s1], y)
    odds = len(s1) / len(s0)
    inner = iso.y_thresholds_[(iso.y_thresholds_ > 0) & (iso.y_thresholds_ < 1)]
    floor = min(float((inner / (1 - inner) / odds).min()), cap) if len(inner) else 1
    p = np.clip(iso.predict(values), 1e-9, 1 - 1e-9)
    return np.clip(p / (1 - p) / odds, floor, cap)

def ece(y, p):
    total = 0
    for lo, hi in zip(np.linspace(0, 1, 11)[:-1], np.linspace(0, 1, 11)[1:]):
        take = (p >= lo) & ((p < hi) | (hi == 1))
        if take.any():
            total += take.mean() * abs(p[take].mean() - y[take].mean())
    return float(total)

prob = {}
for sid, model in models.items():
    cc, cn, ca, sa = component_cache[sid]
    n_lr, a_lr = [], np.empty(len(sa))
    for record_id in np.unique(sa):
        hold = sa == record_id
        values = np.r_[cn["score"], ca["score"][hold]]
        lr = own_lr(cc["score"], ca["score"][~hold], values)
        n_lr.append(lr[:len(cn["score"])]); a_lr[hold] = lr[len(cn["score"]):]
    # 배포·평가 구현은 정상 평가 행에 21개 보정기의 LR 중앙값을 사용한다.
    n_lr = np.median(n_lr, axis=0)
    y = np.r_[np.zeros(len(n_lr)), np.ones(len(a_lr))]
    pi = y.mean(); lr = np.r_[n_lr, a_lr]; p = pi * lr / (pi * lr + 1 - pi)
    brier = float(np.mean((y - p) ** 2)); err = ece(y, p)
    row = prob_eval[prob_eval.split.eq(sid) & prob_eval.cv.eq("21fold") & prob_eval.unit.eq("rows") & prob_eval.method.eq("calibrated_isotonic")].iloc[0]
    assert np.isclose(brier, row.brier, atol=1e-12) and np.isclose(err, row.ece, atol=1e-12)
    calibrator = model.probability
    grid = np.unique(np.r_[np.linspace(calibrator.x.min() - 1, calibrator.x.max() + 1, 20001), calibrator.x])
    grid_lr = calibrator.likelihood_ratio(grid)
    assert np.all(np.diff(grid_lr) >= -1e-12)
    assert np.isclose(grid_lr.max(), 121)
    prob[sid] = dict(brier=brier, ece=err, grid_points=len(grid), minimum_LR_increment=float(np.diff(grid_lr).min()), cap=float(grid_lr.max()))
lf = pd.read_csv(G / "outputs/label_free_alert_probability_v2.csv")
for r in lf.itertuples():
    p = r.prior * r.tpr / (r.prior * r.tpr + (1 - r.prior) * r.far)
    assert abs(r.p_anomaly_given_alert - p) < 1e-12
    assert abs(r.nominal_lr_reference - r.tpr / r.nominal_far) < 1e-10
    assert abs(r.min_rank_nominal_lr_reference - 121 * r.tpr) < 1e-10
record("C4_probability", dict(crossfit=prob, label_free_rows=len(lf), nominal_far_counterexample=dict(n=120, actual_far=.001, tpr=.955, actual_lr=.955/.001, min_rank_nominal_lr=.955*121),
                               units="라벨 보정 π=행 비율; 라벨 없는 환산 π=알림 단위 비율"))

# R3-O2/O3: 원본 50행 기록 207개×2센서를 팀 진단 함수 없이 재계산.
def design(n, f):
    angle = 2 * np.pi * f * np.arange(n) * .1
    return np.column_stack([np.cos(angle), np.sin(angle), np.ones(n)])

frequency_cache = {}
for center, width in ((.6, .1), (1.8, .15), (3.6, .15)):
    grid = np.linspace(center - width, center + width, 251)
    mats = np.array([design(50, f) for f in grid])
    frequency_cache[center] = grid, mats, np.linalg.pinv(mats)

def best_frequency(x, center):
    grid, mats, inverse = frequency_cache[center]
    coef = inverse @ x
    fit = np.einsum("fij,fj->fi", mats, coef)
    i = int(np.argmin(np.square(fit - x).sum(axis=1)))
    def residual(f):
        mat = design(50, f)
        return float(np.square(x - mat @ np.linalg.lstsq(mat, x, rcond=None)[0]).sum())
    return float(optimize.minimize_scalar(residual, bounds=(grid[max(0, i - 1)], grid[min(len(grid) - 1, i + 1)]), method="bounded").x)

rows = []
harmonic = np.column_stack([np.ones(50)] + [design(50, .6 * k)[:, c] for k in range(1, 9) for c in (0, 1)])
for name, frame in (("normal", normal), ("abnormal", abnormal)):
    seg = D.segments(frame)
    values = frame[list(D.SENSORS)].to_numpy(float)
    for rec in np.unique(seg):
        x = values[seg == rec]
        if len(x) != 50:
            continue
        cu = np.linalg.lstsq(design(50, .6), x[:, 2], rcond=None)[0]
        fc = best_frequency(x[:, 2], .6)
        phase_c = math.atan2(-cu[1], cu[0])
        for k, f0, multiple in ((0, 3.6, 6), (1, 1.8, 3)):
            v = x[:, k]
            coef = np.linalg.lstsq(design(50, f0), v, rcond=None)[0]
            amp = float(np.hypot(*coef[:2]))
            fit = harmonic @ np.linalg.lstsq(harmonic, v, rcond=None)[0]
            spectrum = np.abs(np.fft.rfft((v - v.mean()) * np.hanning(50), 500)) ** 2
            rows.append(dict(file=name, record=int(rec), sensor=D.SENSORS[k], current_frequency_hz=fc, current_amplitude=float(np.hypot(*cu[:2])),
                             tone_frequency_hz=best_frequency(v-v.mean(), f0), tone_amplitude=amp, harmonic_r2=float(1 - np.square(v-fit).sum()/np.square(v-v.mean()).sum()),
                             tone_rms_over_sd=float(amp / np.sqrt(2) / v.std()), phase_difference=float((math.atan2(-coef[1], coef[0])-multiple*phase_c)%(2*np.pi)),
                             spectral_peak_hz=float(np.fft.rfftfreq(500, .1)[1:][np.argmax(spectrum[1:])])))
got = pd.DataFrame(rows).set_index(["file", "record", "sensor"]).sort_index()
ref_tones = pd.read_csv(E / "vibration_tones.csv").set_index(["file", "record", "sensor"]).sort_index()
assert got.index.equals(ref_tones.index)
max_diffs = {col: float(abs(got[col] - ref_tones[col]).max()) for col in got}
assert max(max_diffs.values()) < 1e-5, max_diffs
summaries = {}
for (file, sensor), group in got.groupby(level=["file", "sensor"]):
    summaries[f"{file}_{sensor}"] = dict(records=len(group), frequency_median=float(group.tone_frequency_hz.median()), harmonic_r2_median=float(group.harmonic_r2.median()),
                                         rms_over_sd=float(group.tone_rms_over_sd.median()), amplitude_spearman=float(stats.spearmanr(group.current_amplitude, group.tone_amplitude).statistic),
                                         phase_R=float(abs(np.exp(1j*group.phase_difference).mean())), spectral_peak_iqr=group.spectral_peak_hz.quantile([.25,.5,.75]).tolist())
fm = pd.read_csv(E / "failure_mode_map.csv").set_index("fm_id")
fm3 = fm.loc["FM3", "confirmed_in_this_data"]
assert "이 행이 가정한 접힌 광대역" not in fm3 and "저주파라는 이유만으로 배제할 수 없다" in fm3
for sensor in D.SENSORS[:2]:
    abnormal_peaks = got.xs(("abnormal", sensor), level=("file", "sensor")).spectral_peak_hz
    assert all(f"{rec}:{value:.2f}" in fm3 for rec, value in abnormal_peaks.items())
record("C5_R3_O2_O3_tones", dict(rows=len(got), max_absolute_error=max_diffs, summary=summaries, fm3_five_record_peaks_match=True))

# 2단계 추정의 분모/겹침/사후성 및 사후 FAR 작업량을 독립 산식으로 대조.
levels = pd.read_csv(G / "outputs/alert_levels_v2.csv")
effects = pd.read_csv(G / "outputs/expected_effect_v2.csv")
primary = levels[levels.normal_window.isin(["300~359", "360~419"]) & levels.alpha.eq(.05)]
counts = primary.groupby("level").normal_alerted_segments.sum()
k, n = int(counts[2]), int(counts[1])
nominal = float(levels[levels.model.eq("frozen_B") & levels.alpha.eq(.01) & levels.level.eq(1)].nominal_alerts_per_8h_elapsed.iloc[0])
upper = float(stats.beta.ppf(.95, k + 1, n - k))
point_rows = effects[effects.alert_scenario.eq("비중첩 폴드 추정(주추정)")]
upper_rows = effects[effects.alert_scenario.eq("비중첩 폴드 추정 95% 상한")]
assert (k, n) == (1, 7) and np.allclose(point_rows.level2_per_8h, nominal*k/n) and np.allclose(upper_rows.level2_per_8h, nominal*upper)
assert point_rows.rule_selected_post_hoc.all() and (~point_rows.evaluation_overlaps_rule_selection).all()
work = pd.read_csv(G / "outputs/workload_v2.csv")
work_checked = []
for r in work[work.model.eq("guard_v2")].itertuples():
    ell = math.floor(r.alpha*121+1e-9)
    q = stats.beta.ppf(.95, ell+r.first_alert_segments, 121-ell+r.normal_segments-r.first_alert_segments)
    value = q*r.units_per_elapsed_hour*8
    assert np.isclose(value, r.posterior95_alerts_per_8h_elapsed, atol=1e-10)
    work_checked.append(dict(split=r.split_id, alpha=r.alpha, posterior95_per8h=float(value)))
record("C6_workload", dict(level2_ratio=[k,n], level1_nominal=nominal, level2_point=nominal*k/n, level2_upper95=nominal*upper,
                            ratio_source_alpha=.05, target_nominal_alpha=.01, posthoc=True, same_day=True, workload=work_checked))
OUT["head_end"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Y, text=True).strip()
OUT["hashes_end"] = snapshot()
OUT["files_changed_during_check"] = [p for p, h in OUT["hashes_start"].items() if OUT["hashes_end"].get(p) != h]
OUT["script_sha256"] = sha(__file__)
record("C7_complete", {"all_checks_passed": True, "changed_during_check": OUT["files_changed_during_check"]})
