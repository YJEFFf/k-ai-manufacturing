"""E-6 합성 주입(E1)의 해석.

(1) 주입 세기의 단위: '정상 σ의 0.1배'에서 σ는 0.6 Hz 사인을 포함한 전류 전체의 표준편차다. 정상 잡음 바닥(AR(2) 잔차·사인 적합 잔차) 대비로는 몇 배인가.
(2) 탐지율의 불확실성: 같은 기록을 5번 재사용한 시행을 독립으로 보면 구간이 얼마나 좁아지는가(기록 군집 붓스트랩).
(3) 관측 이상과의 연결: 이상 21기록의 잔차 크기 대 주입 하한.
"""
from redE_common import *
from scipy import stats
from press import data as D
from press.scores import window_index, sine_score

n, a = raw()
M = models()
OUT = {}
SUP = YEJUN / "analysis" / "press_supplement"
for sid, m in M.items():
    sp = split(n, sid)
    tq = D.quantize(D.inputs_only(sp["train"]), "matched"); seg = D.segments(tq)
    cur = tq[D.SENSORS[2]].to_numpy(float)
    idx = window_index(seg, 3)
    res = cur[idx] - m.coef[0] - m.coef[1] * cur[idx - 1] - m.coef[2] * cur[idx - 2]
    sigma = float(m.scale[2])
    ar_sd = float(np.std(res)); ar_mad = float(1.4826 * np.median(np.abs(res - np.median(res))))
    gain = float(np.sqrt(1 + m.coef[1] ** 2 + m.coef[2] ** 2))
    # 사인 적합 잔차(8행 창): 1−R² × 창 분산 → 잔차 SD
    s8 = sine_score(cur, seg, 8); i8 = window_index(seg, 8)
    wvar = np.array([np.var(cur[i - 7:i + 1]) for i in i8])
    sine_res_sd = float(np.sqrt(np.nanmedian(s8[i8] * wvar)))
    # 진동: scale이 곧 잡음 수준(진동은 주기 성분이 약함)
    rows = []
    for s in (.02, .05, .1, .2, .4):
        inj_sd = s * sigma
        resid_after = np.sqrt(ar_sd ** 2 + (gain * inj_sd) ** 2)
        rows.append(dict(level=s, injected_sd=inj_sd, injected_over_ar_resid_sd=inj_sd / ar_sd, injected_over_ar_resid_mad=inj_sd / ar_mad,
                         injected_over_sine_resid_sd=inj_sd / sine_res_sd, ar_resid_sd_multiplier=resid_after / ar_sd))
    t = pd.DataFrame(rows)
    # 경보에 필요한 예측 오차 크기(동역학 성분이 문턱을 넘는 |잔차|)와 정상 잔차의 비
    pa = m.predict(a); thr = float(np.max(m.cal))
    g = pa.g_dynamics.to_numpy(); r_abs = pa.current_residual.to_numpy()
    need = float(np.nanmin(r_abs[g > thr])) if np.any(g > thr) else np.nan
    OUT[sid] = dict(sigma_current=sigma, amplitude_sqrt2sigma=float(np.sqrt(2) * sigma), ar2=m.coef.tolist(), ar_resid_sd=ar_sd, ar_resid_robust_sd=ar_mad,
                    ar_resid_sd_over_sigma=ar_sd / sigma, white_noise_gain=gain, sine_resid_sd=sine_res_sd, levels=t.to_dict("records"),
                    abs_residual_needed_for_alarm=need, needed_over_ar_resid_sd=need / ar_sd, threshold=thr,
                    sigma_vib=[float(m.scale[0]), float(m.scale[1])])
    print(f"[{sid}] 전류 σ(전체) {sigma:.2f} (사인 진폭 ≈ √2σ = {np.sqrt(2)*sigma:.1f}); 정상 AR(2) 잔차 SD {ar_sd:.2f} (σ의 {ar_sd/sigma:.3f}배, 강건 SD {ar_mad:.2f}); 사인 적합 잔차 SD(중앙) {sine_res_sd:.2f}")
    print(f"[{sid}] 백색잡음 → AR 잔차 증폭 √(1+φ1²+φ2²) = {gain:.3f}; 동역학 성분 경보에 필요한 |잔차| ≥ {need:.1f} (정상 잔차 SD의 {need/ar_sd:.1f}배)")
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

# (2) 탐지율 구간: 시행 독립 가정 대 기록 군집
rec = pd.read_csv(SUP / "predictions_e1_records.csv")
sel = rec[rec.model.eq("guard_v2") & rec.alpha.eq(.01) & rec["shape"].eq("step") & rec.t0.eq(10)]
rng = np.random.default_rng(3)
ci = []
for (sid, fam, lv), g in sel.groupby(["split", "family", "level"]):
    if (fam, lv) not in (("cur_noise", .1), ("cur_noise", .05), ("vib_noise", 2.0), ("vib_noise", 4.0), ("cur_offset", .2), ("cur_offset", .4), ("none", 0.0)):
        continue
    k, N = int(g.detected_2s.sum()), len(g)
    lo = stats.beta.ppf(.025, k, N - k + 1) if k else 0.0; hi = stats.beta.ppf(.975, k + 1, N - k) if k < N else 1.0
    pr = g.groupby("record").detected_2s.mean()
    ix = rng.integers(0, len(pr), (4000, len(pr)))
    bs = pr.to_numpy()[ix].mean(axis=1)
    # 기록 안 반복 사이 일치도(ICC에 해당): 기록 평균의 분산 / 이항 분산
    reps = g.groupby("record").size().iloc[0]
    p = k / N
    var_between = pr.var(ddof=1)
    deff = var_between * reps / (p * (1 - p)) if 0 < p < 1 else np.nan
    ci.append(dict(split=sid, family=fam, level=lv, records=len(pr), reps=int(reps), trials=N, rate=p, iid_lo=float(lo), iid_hi=float(hi),
                   cluster_lo=float(np.quantile(bs, .025)), cluster_hi=float(np.quantile(bs, .975)), design_effect=float(deff),
                   records_never_detected=int((pr == 0).sum()), records_always_detected=int((pr == 1).sum())))
ct = pd.DataFrame(ci)
pd.set_option("display.width", 250)
print(ct.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
OUT["rates"] = ct.to_dict("records")

# (3) 관측 이상과의 연결
ref = pd.read_csv(SUP / "e1_reference_segments.csv")
ab = ref[ref.source.eq("abnormal")]
OUT["observed_abnormal"] = dict(ar_resid_ratio_median=float(ab.ar_resid_std_over_normal_median.median()), ar_resid_ratio_min=float(ab.ar_resid_std_over_normal_median.min()),
                                ar_resid_ratio_max=float(ab.ar_resid_std_over_normal_median.max()), records_with_value=int(ab.ar_resid_std_over_normal_median.notna().sum()),
                                vib0_ratio_median=float(ab.vib0_std_ratio.median()), vib1_ratio_median=float(ab.vib1_std_ratio.median()),
                                cur_mean_over_A_median_abs=float(ab.cur_mean_over_A.abs().median()))
print("관측 이상 21기록: AR 잔차 SD / 정상 중앙값 — 중앙", round(OUT["observed_abnormal"]["ar_resid_ratio_median"], 2), "범위", round(OUT["observed_abnormal"]["ar_resid_ratio_min"], 2), "~", round(OUT["observed_abnormal"]["ar_resid_ratio_max"], 2))
dump(OUT, "redE_07_injection.json")
