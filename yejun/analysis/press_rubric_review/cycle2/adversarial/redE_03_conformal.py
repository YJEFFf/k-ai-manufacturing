"""E-2 conformal 보장 문장의 전제와 검정력.

(a) 0/120·3/180이 α=1%(명목 1/121)와 양립하는가, 이 관측으로 α 수준을 확인할 수 있는가(검정력).
(b) 교환가능성: 보정 대 평가 기록 최대 점수의 분포 차이, 기록 사이 자기상관, 상태 구성.
(c) A·B 평가 겹침: 두 관측이 독립 확인 두 건인가.
(d) 오경보 3건의 시간 간격과 군집.
"""
from redE_common import *
from scipy import stats

n, a = raw()
M = models()
seg_all = record_ids(n)
OUT = {}

# ---------- (a) 검정력 ----------
p0 = 1 / 121
pw = {}
for lab, k, m in (("A 0/120", 0, 120), ("B 3/180", 3, 180)):
    # 정확 이항: H0 p = 1/121
    p_le = float(stats.binom.cdf(k, m, p0)); p_ge = float(stats.binom.sf(k - 1, m, p0))
    lo = float(stats.beta.ppf(.025, k, m - k + 1)) if k > 0 else 0.0
    hi = float(stats.beta.ppf(.975, k + 1, m - k))
    hi1 = float(stats.beta.ppf(.95, k + 1, m - k))
    # 보정 표본 흔들림 포함: 실제 오경보율 ~ Beta(1,120), 개수 ~ BetaBinomial(m,1,120)
    bb_le = float(stats.betabinom.cdf(k, m, 1, 120)); bb_ge = float(stats.betabinom.sf(k - 1, m, 1, 120))
    pw[lab] = dict(binom_P_le_k=p_le, binom_P_ge_k=p_ge, cp95_two_sided=[lo, hi], cp95_one_sided_upper=hi1,
                   ratio_upper_to_nominal=hi1 / p0, betabinom_P_le_k=bb_le, betabinom_P_ge_k=bb_ge)
    print(f"{lab}: 이항 P(X≤k)={p_le:.3f} P(X≥k)={p_ge:.3f}; 95% CP 양측 [{lo:.4f},{hi:.4f}] 단측 상한 {hi1:.4f} (= 명목의 {hi1/p0:.1f}배); "
          f"Beta-Binomial P(X≤k)={bb_le:.3f} P(X≥k)={bb_ge:.3f}")
# "실제 오경보율이 명목의 c배일 때, m단위에서 5% 단측 검정으로 그것을 알아챌 확률"
rows = []
for m in (120, 180, 300, 600, 2000, 5000):
    crit = int(stats.binom.ppf(.95, m, p0))            # X > crit 이면 기각
    size = float(stats.binom.sf(crit, m, p0))
    for c in (2, 3, 5):
        rows.append(dict(units=m, reject_if_gt=crit, size=size, true_rate_multiple=c, power=float(stats.binom.sf(crit, m, min(1, c * p0)))))
pt = pd.DataFrame(rows)
print(pt.pivot(index=["units", "reject_if_gt", "size"], columns="true_rate_multiple", values="power").to_string(float_format=lambda v: f"{v:.3f}"))
# 명목의 2배를 검정력 80%로 가려내는 데 필요한 단위 수
need = {}
for c in (2, 3, 5):
    for m in range(50, 20001, 10):
        crit = int(stats.binom.ppf(.95, m, p0))
        if stats.binom.sf(crit, m, c * p0) >= .8:
            need[c] = m; break
print("검정력 80%에 필요한 정상 평가 단위 수(단측 5%):", need, " 대회 밀도 447단위/시간 → 시간:", {k: round(v / 447, 2) for k, v in need.items()})
OUT["power"] = dict(observed=pw, table=pt.to_dict("records"), units_needed_power80=need)

# ---------- (b) 교환가능성 ----------
ex = {}
for sid, m in M.items():
    p = m.predict(n)                                       # 600기록 전체 점수(학습 구간 포함, 참고)
    rec = p.record_id.to_numpy()
    assert np.array_equal(rec, seg_all) or len(np.unique(rec)) == 600
    smax = pd.Series(np.where(np.isfinite(p.score), p.score, -np.inf)).groupby(rec).max().to_numpy()
    tr, ca = SPLITS[sid]
    cal, test = smax[tr:ca], smax[ca:]
    assert np.allclose(np.sort(cal), np.sort(m.cal))
    mw = stats.mannwhitneyu(test, cal, alternative="two-sided")
    ks = stats.ks_2samp(test, cal)
    above = int((test > np.median(cal)).sum())
    # 기록 사이 자기상관(평가 구간·보정+평가 구간)
    def acf(x, L):
        x = np.asarray(x, float) - np.mean(x)
        return float((x[L:] * x[:-L]).sum() / (x * x).sum())
    seq = smax[tr:]
    ac = {L: acf(seq, L) for L in (1, 2, 3, 5, 10, 20)}
    rho1 = ac[1]
    neff_ar1 = len(test) * (1 - rho1) / (1 + rho1)
    # 초과 지시값(상위 10% 문턱)의 군집: 연속 초과의 런
    q90 = np.quantile(cal, .9)
    exc = (seq > q90).astype(int)
    ac_exc = acf(exc, 1)
    # 기록 길이와 최대 점수(길이가 길수록 최대가 크다: 교환가능성은 길이·상태 혼합 위의 성질)
    length = pd.Series(rec).groupby(rec).size().to_numpy()
    rho_len = float(stats.spearmanr(length[tr:], smax[tr:]).statistic)
    # 시간순 5등분 평균(드리프트)
    fifth = [float(np.mean(s)) for s in np.array_split(seq, 5)]
    ex[sid] = dict(n_cal=len(cal), n_test=len(test), test_above_cal_median=above, expected_if_exchangeable=len(test) / 2,
                   mannwhitney_p=float(mw.pvalue), ks_p=float(ks.pvalue), acf_record_max=ac, neff_test_ar1=float(neff_ar1),
                   acf1_exceed_q90=float(ac_exc), spearman_length_vs_max=rho_len, mean_by_time_fifth=fifth,
                   threshold=float(np.max(cal)), second=float(np.sort(cal)[-2]), test_exceed=int((test > np.max(cal)).sum()))
    print(f"[{sid}] 평가 중 보정 중앙값 초과 {above}/{len(test)} (교환가능하면 {len(test)/2:.0f}); MW p={mw.pvalue:.2e}, KS p={ks.pvalue:.2e}")
    print(f"[{sid}] 기록 최대 점수 자기상관 lag1,2,3,5,10,20: {[round(v,3) for v in ac.values()]}; AR(1) 유효 표본 수(평가) {neff_ar1:.0f}/{len(test)}; 길이-최대점수 ρ={rho_len:.2f}")
    print(f"[{sid}] 시간순 5등분 평균 최대 점수(보정+평가): {[round(v,2) for v in fifth]}")
OUT["exchangeability"] = ex

# ---------- (c) A·B 겹침 ----------
pA = M["A"].predict(split(n, "A")["test"]); pB = M["B"].predict(split(n, "B")["test"])
ra = pA.groupby("record_id").alarm.max(); rb = pB.groupby("record_id").alarm.max()
fa_b = (rb[rb.eq(1)].index.to_numpy() + 420).tolist()
ov = dict(A_test=[480, 599], B_test=[420, 599], shared_records=120, share_of_A=1.0, share_of_B=120 / 180,
          B_false_alarm_records=fa_b, B_false_alarms_in_shared=int(sum(r >= 480 for r in fa_b)), A_false_alarms=int(ra.sum()),
          B_only_part=dict(records="420~479", alarms=int(sum(r < 480 for r in fa_b)), n=60))
# B 모델로 겹치는 구간(480~599)만 보면
ov["B_alarms_in_480_599"] = f"{int(sum(r >= 480 for r in fa_b))}/120"
# 570번 기록: A 문턱에서는 왜 경보가 아닌가
s570 = pB[pB.record_id.eq(570 - 420)].score.max()
ov["record570_max_score"] = float(s570); ov["thr_A"] = float(np.max(M["A"].cal)); ov["thr_B"] = float(np.max(M["B"].cal))
print("겹침:", ov)
OUT["overlap"] = ov

# ---------- (d) 오경보 시간 간격 ----------
t = pd.to_datetime(n["TimeStamp"])
g = pd.DataFrame(dict(seg=seg_all, t=t)).groupby("seg").t.min()
span = (g[599] - g[420]).total_seconds()
ts = np.array([(g[r] - g[420]).total_seconds() for r in fa_b])
# 균일 배치 가정에서 세 점의 최소 간격이 관측 이하일 확률(모의)
rng = np.random.default_rng(1)
sim = np.sort(rng.uniform(0, span, (200000, 3)), axis=1)
min_gap = np.diff(sim, axis=1).min(axis=1)
obs_gap = float(np.diff(np.sort(ts)).min())
OUT["false_alarm_timing"] = dict(times_s_from_B_test_start=ts.tolist(), span_s=float(span), gaps_s=np.diff(np.sort(ts)).tolist(),
                                 p_min_gap_le_obs_uniform=float((min_gap <= obs_gap).mean()))
print("오경보 시각(평가 시작 기준 초):", np.round(ts, 1), "간격", np.round(np.diff(np.sort(ts)), 1), f"균일 가정에서 최소 간격 ≤ 관측일 확률 {OUT['false_alarm_timing']['p_min_gap_le_obs_uniform']:.3f}")
dump(OUT, "redE_03_conformal.json")
