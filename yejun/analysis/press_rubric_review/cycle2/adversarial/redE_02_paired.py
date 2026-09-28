"""E-1b v2 대 v1 짝 비교(18/3/0, p 3.8e-6)와 ΔF1 붓스트랩 구간의 재검토.

질문 1. v2 경보 집합이 v1 경보 집합을 구조적으로 포함하는가(악화 0이 설계상 보장인가).
질문 2. 개선이 나온 위치는 어디인가(v1이 구조적으로 점수를 못 내는 위치인가).
질문 3. 21기록을 독립으로 본 부호검정·붓스트랩을, 기록 사이 의존을 넣으면 어떻게 되는가.
"""
from redE_common import *
from scipy import stats
from press import data as D
from press.calibrate import conformal_p, segment_max
from press.scores import sine_score

n, a = raw()
M = models()
res = {}


def v1_score(model, frame):
    x = D.quantize(D.inputs_only(frame), "matched")
    seg = D.segments(x)
    comp = model.components(x, seg)
    s8 = model.tails["sine8"](sine_score(x[D.SENSORS[2]].to_numpy(), seg, 8))
    return np.fmax(comp["g_magnitude"], s8), seg, comp


for sid, m in M.items():
    sp = split(n, sid)
    s1c, segc, compc = v1_score(m, sp["cal"])
    ref1 = segment_max(s1c, segc)
    thr1 = float(np.sort(ref1)[-1]); thr2 = float(np.sort(m.cal)[-1])
    # 보정 최댓값을 만든 성분
    calmax_row = int(np.nanargmax(np.where(np.isfinite(compc["score"]), compc["score"], -np.inf)))
    which = {k: float(compc[k][calmax_row]) for k in ("g_magnitude", "g_waveform", "g_dynamics")}
    pa = m.predict(a)
    s1a, sega, compa = v1_score(m, a)
    p1 = conformal_p(ref1, s1a)
    al1 = (np.isfinite(p1) & (p1 <= .01)).astype(int)
    al2 = pa.alarm.to_numpy()
    pos = pa.position.to_numpy(); rec = pa.record_id.to_numpy()
    sup = bool(np.all(al2 >= al1))
    print(f"[{sid}] thr v1 {thr1:.6f} thr v2 {thr2:.6f} same={abs(thr1-thr2)<1e-12}  cal-max component {which}")
    print(f"[{sid}] v1 FN {int((al1==0).sum())} v2 FN {int((al2==0).sum())}  v2 alarms ⊇ v1 alarms: {sup}  rows v1=1&v2=0: {int(((al1==1)&(al2==0)).sum())}")
    # 위치별 분해
    gained = (al2 == 1) & (al1 == 0)
    byp = pd.DataFrame(dict(pos=pos, gained=gained, v1miss=al1 == 0, v2miss=al2 == 0))
    byp["bin"] = pd.cut(byp.pos, [-1, 1, 4, 6, 9, 1000], labels=["0-1", "2-4", "5-6", "7-9", ">=10"])
    tab = byp.groupby("bin", observed=True).agg(rows=("pos", "size"), v1_miss=("v1miss", "sum"), v2_miss=("v2miss", "sum"), gained=("gained", "sum"))
    print(tab.to_string())
    # v1이 구조적으로 파형 점수를 낼 수 없는 위치(0~6)에서 얻은 개선 비율
    share_struct = float(gained[pos <= 6].sum() / max(gained.sum(), 1))
    # 개선 행의 v2 근거 성분
    reason = pa.reason[gained].value_counts().to_dict()
    print(f"[{sid}] gained rows {int(gained.sum())}, share at positions 0-6 (v1 has no waveform score): {share_struct:.3f}; reasons {reason}")
    # 기록별
    g = pd.DataFrame(dict(rec=rec, m1=al1 == 0, m2=al2 == 0)).groupby("rec").agg(rows=("m1", "size"), v1=("m1", "sum"), v2=("m2", "sum"))
    g["d"] = g.v1 - g.v2
    imp, same, worse = int((g.d > 0).sum()), int((g.d == 0).sum()), int((g.d < 0).sum())
    p_sign = float(stats.binomtest(imp, imp + worse, .5, alternative="greater").pvalue)
    print(f"[{sid}] improve/same/worse {imp}/{same}/{worse}  sign-test p {p_sign:.3g}")
    # 길이와 개선의 관계: 개선이 없는 기록은 어떤 기록인가
    print(g.assign(tag=np.where(g.d > 0, "imp", "same")).to_string())
    # 기록 사이 자기상관(Δ, 미탐률)
    def acf1(x):
        x = np.asarray(x, float); x = x - x.mean()
        return float((x[1:] * x[:-1]).sum() / (x * x).sum()) if (x * x).sum() > 0 else float("nan")
    r_d = acf1(g.d); r_v2 = acf1(g.v2 / g.rows); r_len = acf1(g.rows)
    print(f"[{sid}] lag-1 autocorr across records: Δ {r_d:.3f}, v2 miss rate {r_v2:.3f}, record length {r_len:.3f}")
    # F1 차이의 기록 붓스트랩: iid(팀 방식) 대 이동 블록/원형 블록
    fp1 = fp2 = int(m.predict(sp["test"]).alarm.sum())   # v1·v2 정상 경보 행 수(같음: 아래에서 확인)
    s1t, segt, _ = v1_score(m, sp["test"]); p1t = conformal_p(ref1, s1t); fp1 = int((np.isfinite(p1t) & (p1t <= .01)).sum())
    rows_r = g.rows.to_numpy(); m1 = g.v1.to_numpy(); m2 = g.v2.to_numpy()

    def f1(tp, fp, fn):
        return 2 * tp / (2 * tp + fp + fn)

    def dF1(idx):
        r = rows_r[idx].sum(); a1 = m1[idx].sum(); a2 = m2[idx].sum()
        return f1(r - a2, fp2, a2) - f1(r - a1, fp1, a1)
    rng = np.random.default_rng(20260928)
    R = 10000
    k = len(g)
    boots = {}
    boots["iid_records"] = np.array([dF1(rng.integers(0, k, k)) for _ in range(R)])
    for b in (3, 5, 7, 10):
        nb = int(np.ceil(k / b))
        vals = np.empty(R)
        for r in range(R):
            st = rng.integers(0, k, nb)                       # 원형 블록
            idx = np.concatenate([(s + np.arange(b)) % k for s in st])[:k]
            vals[r] = dF1(idx)
        boots[f"circular_block_{b}"] = vals
    obs = dF1(np.arange(k))
    summ = {kk: dict(lo=float(np.percentile(v, 2.5)), hi=float(np.percentile(v, 97.5)), sd=float(v.std())) for kk, v in boots.items()}
    print(f"[{sid}] ΔF1 obs {obs:.4f}  fp v1 {fp1} v2 {fp2}")
    for kk, v in summ.items():
        print(f"    {kk:20s} [{v['lo']:.4f}, {v['hi']:.4f}] sd {v['sd']:.4f}")
    # 행 단위 자기상관과 유효 표본 수(기록 안 0.1초 간격)
    def within_acf(x, rec, lag):
        num = den = 0.0
        mu = x.mean()
        for r in np.unique(rec):
            v = x[rec == r] - mu
            if len(v) > lag:
                num += (v[lag:] * v[:-lag]).sum()
            den += (v * v).sum()
        return num / den if den > 0 else np.nan
    row = {}
    for nm, x in (("v2_miss", (al2 == 0).astype(float)), ("v1_miss", (al1 == 0).astype(float)), ("v2_score", np.nan_to_num(pa.score.to_numpy()))):
        row[nm] = [float(within_acf(x, rec, L)) for L in (1, 2, 3, 5, 10)]
    print(f"[{sid}] within-record row autocorr lag1,2,3,5,10:", {k_: np.round(v, 3).tolist() for k_, v in row.items()})
    # 기록 군집 설계효과: 미탐 지시값의 기록내 상관(ICC, ANOVA 추정)
    def icc(x, rec):
        df = pd.DataFrame(dict(x=x, r=rec)); gm = df.x.mean(); grp = df.groupby("r").x
        kk = grp.ngroups; N = len(df); ni = grp.size().to_numpy()
        msb = (ni * (grp.mean().to_numpy() - gm) ** 2).sum() / (kk - 1)
        msw = ((df.x - grp.transform("mean")) ** 2).sum() / (N - kk)
        n0 = (N - (ni ** 2).sum() / N) / (kk - 1)
        return float((msb - msw) / (msb + (n0 - 1) * msw)), float(n0)
    ic, n0 = icc((al2 == 0).astype(float), rec)
    res[sid] = dict(thr_v1=thr1, thr_v2=thr2, threshold_same=bool(abs(thr1 - thr2) < 1e-12), calmax_component=which,
                    v2_superset_of_v1=sup, v1_fn=int((al1 == 0).sum()), v2_fn=int((al2 == 0).sum()), by_position=tab.reset_index().astype({"bin": str}).to_dict("records"),
                    gained_rows=int(gained.sum()), gained_share_pos_le6=share_struct, gained_reasons=reason,
                    improve_same_worse=[imp, same, worse], sign_p=p_sign, lag1_delta=r_d, lag1_v2_missrate=r_v2, lag1_length=r_len,
                    dF1_obs=float(obs), bootstrap=summ, within_record_acf=row, icc_v2_miss=ic, icc_n0=n0,
                    per_record=g.reset_index().to_dict("records"))
    print(f"[{sid}] ICC(v2 miss | record) {ic:.3f} (n0 {n0:.1f})")
    print()
dump(res, "redE_02_paired.json")
