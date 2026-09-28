"""E-5 운영 통계: Beta-Binomial 알림 한도·수락 검사·알림 예산 역산·2단계 추정.

(1) 유도 확인: 문턱이 보정 n개 중 l번째 큰 값이면 실제 오경보율 ~ Beta(l, n+1−l), 새 m단위의 알림 수 ~ BetaBinomial(m, l, n+1−l).
(2) 모의: iid / 기록 사이 자기상관 / 상태 구성 변화에서 95% 한도의 실제 초과 확률.
(3) 실제 정상 자료에서 미끄러지는 창(보정 120 → 다음 60)으로 실제 초과 비율.
(4) 수락 검사의 검정력. (5) 알림 예산 역산. (6) 2단계 1/7 추정의 범위.
"""
from redE_common import *
from scipy import stats
import math

OUT = {}
rng = np.random.default_rng(20260928)


def lrank(alpha, n):
    return math.floor(alpha * (n + 1) + 1e-9)


def limit(alpha, n, m, level=.95):
    l = lrank(alpha, n)
    return int(stats.betabinom.ppf(level, m, l, n + 1 - l))


# ---------- (1)(2) 모의 ----------
def simulate(kind, alpha, n=120, m=60, reps=20000, rho=0.0, shift=0.0, mix=None):
    """한 번의 모의 = 보정 n단위 + 바로 뒤 m단위. 반환: 알림 수 배열."""
    l = lrank(alpha, n)
    if kind == "iid":
        x = rng.standard_normal((reps, n + m))
    elif kind == "ar1":
        e = rng.standard_normal((reps, n + m))
        x = np.empty_like(e); x[:, 0] = e[:, 0]
        s = math.sqrt(1 - rho * rho)
        for t in range(1, n + m):
            x[:, t] = rho * x[:, t - 1] + s * e[:, t]
    elif kind == "drift":            # 평가 구간의 평균이 보정보다 shift·SD만큼 다르다
        x = rng.standard_normal((reps, n + m)); x[:, n:] += shift
    elif kind == "mixture":          # 두 상태 혼합: 부하 상태는 점수가 높다. 보정과 평가의 부하 비율이 다르다
        p_cal, p_test, gap = mix
        st = np.c_[rng.random((reps, n)) < p_cal, rng.random((reps, m)) < p_test]
        x = rng.standard_normal((reps, n + m)) + gap * st
    thr = np.sort(x[:, :n], axis=1)[:, n - l]          # l번째 큰 값
    return (x[:, n:] > thr[:, None]).sum(axis=1)


sim_rows = []
for alpha in (.01, .03, .05):
    for m in (60, 180, 480):
        L95, L99 = limit(alpha, 120, m), limit(alpha, 120, m, .99)
        l = lrank(alpha, 120)
        theo95 = float(stats.betabinom.sf(L95, m, l, 121 - l))
        for lab, kw in (("iid", dict(kind="iid")), ("AR(1) ρ=0.3", dict(kind="ar1", rho=.3)), ("AR(1) ρ=0.6", dict(kind="ar1", rho=.6)),
                        ("평가가 0.3SD 높음", dict(kind="drift", shift=.3)), ("평가가 0.3SD 낮음", dict(kind="drift", shift=-.3)),
                        ("부하 비율 65%→22%(대회 A 방향)", dict(kind="mixture", mix=(.65, .22, 1.0))),
                        ("부하 비율 22%→65%(반대 방향)", dict(kind="mixture", mix=(.22, .65, 1.0)))):
            c = simulate(alpha=alpha, m=m, **kw)
            sim_rows.append(dict(alpha=alpha, m=m, limit95=L95, limit99=L99, theory_exceed95=theo95, scenario=lab,
                                 mean_alerts=float(c.mean()), nominal_mean=l / 121 * m, exceed95=float((c > L95).mean()), exceed99=float((c > L99).mean())))
sim = pd.DataFrame(sim_rows)
pd.set_option("display.width", 250)
print(sim[sim.m.eq(60)].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
OUT["simulation"] = sim.to_dict("records")

# ---------- (3) 실제 자료의 미끄러지는 창 ----------
from model import GuardModel
n_, a_ = raw()
seg = record_ids(n_)
fits = {"frozen_B(학습 0~299)": (models()["B"], 300), "frozen_A(학습 0~359)": (models()["A"], 360)}
m120 = GuardModel.fit(n_[seg < 120].reset_index(drop=True), n_[(seg >= 120) & (seg < 240)].reset_index(drop=True), split="redE_first120")
fits["재적합(학습 0~119)"] = (m120, 120)
real = []
for name, (model, first) in fits.items():
    p = model.predict(n_)
    smax = pd.Series(np.where(np.isfinite(p.score), p.score, -np.inf)).groupby(p.record_id.to_numpy()).max().to_numpy()
    for alpha in (.01, .03, .05):
        for ncal, m in ((120, 60), (99, 60), (120, 30)):
            l = lrank(alpha, ncal)
            if l < 1:
                continue
            L95 = limit(alpha, ncal, m)
            counts = []
            for s in range(first, 600 - ncal - m + 1):
                cal = smax[s:s + ncal]; hold = smax[s + ncal:s + ncal + m]
                thr = np.sort(cal)[ncal - l]
                counts.append(int((hold > thr).sum()))
            counts = np.array(counts)
            # 겹치지 않는 시작만(독립에 가까운 창)
            step = ncal + m
            nonover = counts[::step] if len(counts) else counts
            real.append(dict(scorer=name, alpha=alpha, n_cal=ncal, m=m, limit95=L95, positions=len(counts), mean_alerts=float(counts.mean()),
                             nominal_mean=l / (ncal + 1) * m, exceed95_share=float((counts > L95).mean()), max_alerts=int(counts.max()),
                             nonoverlap_positions=int(len(nonover)), nonoverlap_exceed=int((nonover > L95).sum())))
rd = pd.DataFrame(real)
print(rd.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
OUT["real_sliding"] = rd.to_dict("records")

# ---------- (4) 수락 검사의 검정력 ----------
acc = []
for alpha, ncal, m in ((.01, 120, 60), (.01, 99, 60), (.05, 120, 60), (.01, 120, 480)):
    l = lrank(alpha, ncal); nom = l / (ncal + 1); L = limit(alpha, ncal, m)
    acc.append(dict(alpha=alpha, n_cal=ncal, m=m, limit=L, false_reject_betabinom=float(stats.betabinom.sf(L, m, l, ncal + 1 - l)),
                    false_reject_if_rate_nominal=float(stats.binom.sf(L, m, nom)),
                    **{f"power_{c}x": float(stats.binom.sf(L, m, min(1, c * nom))) for c in (2, 3, 5, 10)}))
ad = pd.DataFrame(acc); print(ad.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
OUT["acceptance_power"] = ad.to_dict("records")

# ---------- (5) 알림 예산 역산 ----------
uph = 447.47
bud = []
for target in (1, 3, 5, 10, 30):
    alpha = target / (uph * 8)
    ncal = math.ceil(1 / alpha - 1e-9) - 1
    # 그 보정 수에서 실제 오경보율의 95% 상한과, 교대 알림 수의 95% 예측 상한
    far95 = float(stats.beta.ppf(.95, 1, ncal)); m = int(round(uph * 8))
    pred95 = int(stats.betabinom.ppf(.95, m, 1, ncal))
    p_exceed_target = float(stats.betabinom.sf(target, m, 1, ncal))
    bud.append(dict(target=target, alpha=alpha, n_cal=ncal, hours=ncal / uph, far_nominal=1 / (ncal + 1), far_cal95=far95,
                    shift_alerts_mean=m / (ncal + 1), shift_alerts_pred95=pred95, p_shift_alerts_gt_target=p_exceed_target))
bd = pd.DataFrame(bud); print(bd.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
OUT["budget"] = bd.to_dict("records")

# ---------- (6) 2단계 1/7 ----------
k2, k1 = 1, 7
nominal = 29.584993085306845
ratio_hi = float(stats.beta.ppf(.95, k2 + 1, k1 - k2)); ratio_lo = float(stats.beta.ppf(.05, k2, k1 - k2 + 1))
two = dict(ratio=k2 / k1, ratio_cp90=[ratio_lo, ratio_hi], point=nominal * k2 / k1, upper_team=nominal * ratio_hi, lower=nominal * ratio_lo)
# 1단계 비율의 불확실성까지 함께: 1단계 실제 오경보율 ~ Beta(1,120)(보정 조건부), 비 ~ Beta(1+1, 7-1+1) 사후(균등 사전)
r1 = stats.beta.rvs(1, 120, size=400000, random_state=1)
rr = stats.beta.rvs(k2 + 1, k1 - k2 + 1, size=400000, random_state=2)
units8h = uph * 8
joint = r1 * rr * units8h
two["joint_median"] = float(np.median(joint)); two["joint_p95"] = float(np.quantile(joint, .95)); two["joint_p05"] = float(np.quantile(joint, .05))
# 1단계를 B 관측(3/180)에 맞춘 경우: Beta(1+3, 120+177)
r1b = stats.beta.rvs(1 + 3, 120 + 177, size=400000, random_state=3)
jb = r1b * rr * units8h
two["joint_with_B_observed_median"] = float(np.median(jb)); two["joint_with_B_observed_p95"] = float(np.quantile(jb, .95))
print("2단계:", {k: (np.round(v, 2).tolist() if isinstance(v, (list, np.ndarray)) else round(v, 3)) for k, v in two.items()})
OUT["two_stage"] = two
dump(OUT, "redE_05_operations.json")
