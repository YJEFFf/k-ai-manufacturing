"""E-4 다중 비교와 분석 갈림길.

A. 오류 분석 산출물에 들어 있는 p값의 수와, 문서가 인용한 유의 결과의 보정 뒤 값.
B. 위치 × 진동 미탐(6/6 대 20/36): 정의상 따라오는 결과인가, 기록 단위로 다시 검정하면, 경계를 바꾸면.
C. 오경보 × 운전 강도: 고유 기록 기준, 블록 크기·진폭 경계·α를 바꿔 다시 계산.
"""
from redE_common import *
from scipy import stats
from press import data as D

OUTD = GUARD / "outputs"
OUT = {}

# ---------- A. p값 수 ----------
def holm(p):
    p = np.asarray(p, float); o = np.argsort(p); m = len(p)
    adj = np.empty(m); run = 0
    for i, idx in enumerate(o):
        run = max(run, (m - i) * p[idx]); adj[idx] = min(1, run)
    return adj

def bh(p):
    p = np.asarray(p, float); o = np.argsort(p); m = len(p)
    adj = np.empty(m); q = p[o] * m / np.arange(1, m + 1)
    adj[o] = np.minimum(1, np.minimum.accumulate(q[::-1])[::-1])
    return adj

fam = {}
allp = []
for f, cols in (("error_conditions_stats_v2.csv", ["fisher_p_greater"]),
                ("fp_intensity_v2.csv", ["fisher_p_greater", "cmh_p", "permutation_p_greater", "spearman_p"]),
                ("fn_intensity_v2.csv", ["p_amp", "p_vib_sd"]),
                ("position_vibration_misses_v2.csv", ["fisher_p_normal_vs_high", "fisher_p_greater", "fisher_p_pos01_vs_ge2_greater"])):
    d = pd.read_csv(OUTD / f)
    for c in cols:
        v = d[c].dropna().to_numpy()
        # 같은 검정이 두 행에 복사된 경우(조건 안/밖 두 칸)는 한 번만 센다
        distinct = len(np.unique(np.round(v, 15)))
        fam[f"{f}:{c}"] = dict(p_values=int(len(v)), distinct_values=int(distinct), lt05=int((v < .05).sum()), lt05_lt1_excluded=int(((v < .05)).sum()))
        allp.extend([(f, c, x) for x in v])
tot = len(allp)
P = np.array([x[2] for x in allp])
print("오류 분석 산출물의 p값:", tot, "개; p<0.05:", int((P < .05).sum()), "; 전역 귀무에서 기대 거짓 양성:", round(tot * .05, 1))
for k, v in fam.items():
    print("   ", k, v)
OUT["families"] = fam; OUT["total_p_values"] = tot; OUT["total_lt05"] = int((P < .05).sum())

# 문서가 인용한 유의 결과
cited = {
    "위치0-1 × 진동 정상 범위 미탐 A (README:155)": 0.043889,
    "위치0-1 × 진동 정상 범위 미탐 B (README:155)": 0.0073887878765927,
    "고부하 고유 구간 α5% 단측 Fisher (README:162)": 1.804677e-06,
    "블록 층화 CMH α5% (README:142)": 2.9e-6,
    "블록 안 순열 α5% (README:142)": 5.0e-5,
    "부하 안 진폭 중앙 이분 Fisher α5% (README:142)": 0.0604549,
    "부하 안 Spearman α5% (README:142)": 0.000998,
    "A 진동 잡음 2σ×진폭 Spearman (README:141)": None,
}
fn = pd.read_csv(OUTD / "fn_intensity_v2.csv")
r = fn[(fn.split == "A") & (fn.family == "vib_noise")].iloc[0]
cited["A 진동 잡음 2σ×진폭 Spearman (README:141)"] = float(r.p_amp)
rows = []
for k, p in cited.items():
    rows.append(dict(claim=k, p=p, bonferroni_all=min(1, p * tot), bonferroni_36_position_table=min(1, p * 36),
                     survives_all=bool(p * tot < .05)))
ct = pd.DataFrame(rows); pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
print(ct.to_string(index=False))
OUT["cited"] = ct.to_dict("records")

# ---------- B. 위치 × 진동 ----------
n, a = raw()
M = models()
posB = {}
for sid, m in M.items():
    sp = split(n, sid)
    q = D.quantize(D.inputs_only(sp["train"]), "matched"); segt = D.segments(q)
    def feats(frame):
        fq = D.quantize(D.inputs_only(frame), "matched"); sg = D.segments(fq)
        v = fq[D.SENSORS[:2]].to_numpy(float)
        z = np.abs((v - m.mean[:2]) / m.scale[:2]).max(axis=1)
        zc = np.abs((fq[D.SENSORS[2]].to_numpy(float) - m.mean[2]) / m.scale[2])
        return pd.DataFrame(dict(seg=sg, z=z, zc=zc)).groupby("seg").agg(vib_maxz=("z", "max"), cur_maxz=("zc", "max")), sg, z, zc
    ftr, _, _, _ = feats(sp["train"])
    fab, sga, zrow, zcrow = feats(a)
    pa = m.predict(a)
    miss = pa.alarm.to_numpy() == 0; pos = pa.position.to_numpy(); rec = pa.record_id.to_numpy()
    thr = float(np.max(m.cal))
    # 크기 성분이 문턱을 넘는 |z| (꼬리 변환의 역): g_magnitude > thr 인 최소 |z|를 행에서 찾는다
    gmag = pa.g_magnitude.to_numpy(); mag = pa.magnitude.to_numpy()
    z_needed = float(mag[gmag > thr].min()) if (gmag > thr).any() else np.nan
    z_max_below = float(mag[gmag <= thr].max())
    res = {}
    for qn in (.90, .95, .99):
        cut = float(ftr.vib_maxz.quantile(qn))
        low_rec = fab.index[fab.vib_maxz <= cut].to_numpy()
        hi_rec = fab.index[fab.vib_maxz > cut].to_numpy()
        m01 = pos <= 1
        k1, n1 = int((miss & m01 & np.isin(rec, low_rec)).sum()), int((m01 & np.isin(rec, low_rec)).sum())
        k2, n2 = int((miss & m01 & np.isin(rec, hi_rec)).sum()), int((m01 & np.isin(rec, hi_rec)).sum())
        p_row = float(stats.fisher_exact([[k1, n1 - k1], [k2, n2 - k2]], alternative="greater").pvalue) if n1 and n2 else np.nan
        # 기록 단위: 위치 0·1을 모두 놓친 기록
        g = pd.DataFrame(dict(rec=rec[m01], miss=miss[m01])).groupby("rec").miss.agg(["sum", "size"])
        allmiss = g["sum"].eq(g["size"])
        a1, b1 = int(allmiss[allmiss.index.isin(low_rec)].sum()), int(len(low_rec))
        a2, b2 = int(allmiss[allmiss.index.isin(hi_rec)].sum()), int(len(hi_rec))
        p_rec = float(stats.fisher_exact([[a1, b1 - a1], [a2, b2 - a2]], alternative="greater").pvalue) if b1 and b2 else np.nan
        # 정의상 따라오는가: 진동 정상 범위 기록의 위치 0·1 행에서 크기 성분이 문턱을 넘을 수 있는 행(전류 |z| 포함)
        rows01 = m01 & np.isin(rec, low_rec)
        can_fire = int((mag[rows01] >= z_needed).sum())
        res[str(qn)] = dict(cut=cut, records_low=b1, records_high=b2, rows_low_miss=f"{k1}/{n1}", rows_high_miss=f"{k2}/{n2}", p_row_fisher=p_row,
                            rec_low_allmiss=f"{a1}/{b1}", rec_high_allmiss=f"{a2}/{b2}", p_record_fisher=p_rec,
                            magnitude_needed_absz=z_needed, low_records_max_vib_absz=float(fab.vib_maxz[fab.index.isin(low_rec)].max()) if b1 else None,
                            low_rows01_max_magnitude=float(mag[rows01].max()) if rows01.any() else None, low_rows01_that_could_fire=can_fire)
        print(f"[{sid}] q{int(qn*100)} 경계 {cut:.3f}: 진동 정상 범위 기록 {b1}개(행 미탐 {k1}/{n1}) 대 높은 기록 {b2}개({k2}/{n2}); 행 Fisher p={p_row:.4f}; "
              f"기록 단위(0·1 모두 미탐) {a1}/{b1} 대 {a2}/{b2}, p={p_rec:.4f}")
    print(f"[{sid}] 위치 0·1에서 경보가 나려면 크기 |z| ≥ {z_needed:.3f} (문턱 아래 최대 {z_max_below:.3f}); q95 경계 {res['0.95']['cut']:.3f} 이하인 기록은 진동 |z|가 모두 그 아래 → 정의상 발화 불가. "
          f"그 행들의 실제 최대 크기 {res['0.95']['low_rows01_max_magnitude']:.3f}")
    posB[sid] = res
OUT["position_vibration"] = posB

# ---------- C. 오경보 × 운전 강도 ----------
seg = record_ids(n)
ev = pd.read_csv(OUTD / "fp_events_v2.csv")
ev = ev[ev.same_calibration_as.isna()]
fits = {"frozen_A": (480, 600), "frozen_B": (420, 600), "rolling_test_300_359": (300, 360), "rolling_test_360_419": (360, 420), "rolling_test_540_599": (540, 600)}
qn_ = D.quantize(D.inputs_only(n), "matched")
cur_q = qn_[D.SENSORS[2]].to_numpy(float); cur_raw = pd.to_numeric(n[D.SENSORS[2]]).to_numpy(float)
g = pd.DataFrame(dict(seg=seg, cq=cur_q, cr=cur_raw)).groupby("seg")
feat = pd.DataFrame(dict(length=g.size(), amp=np.sqrt(2) * g.cq.std(ddof=0), rms=g.cr.std(ddof=0)))
feat["state"] = np.where(feat.length < 17, "short", np.where(feat.rms >= 91.9, "load", "low"))
btr = feat.loc[:299]; b_q75 = float(btr[btr.length >= 17].amp.quantile(.75))
t0 = pd.to_datetime(n["TimeStamp"]).groupby(seg).min()
C = {}
for alpha in (.01, .03, .05):
    e = ev[ev.alpha.eq(alpha)]
    units = []
    for name, (lo, hi) in fits.items():
        fa = set(e[e.model.eq(name)].record)
        for r in range(lo, hi):
            units.append(dict(fit=name, rec=r, fa=int(r in fa)))
    u = pd.DataFrame(units).join(feat, on="rec")
    uniq = u.groupby("rec").agg(fa=("fa", "max"), times_counted=("fa", "size"), fa_units=("fa", "sum")).join(feat)
    k_units, n_units = int(u.fa.sum()), len(u)
    k_uni, n_uni = int(uniq.fa.sum()), len(uniq)
    load_u = u.state.eq("load"); load_q = uniq.state.eq("load")
    c = dict(units=n_units, unit_alarms=k_units, unique_records=n_uni, unique_alarm_records=k_uni,
             records_counted_twice_or_more=int((uniq.times_counted > 1).sum()),
             alarm_records_counted_more_than_once=uniq[(uniq.fa == 1) & (uniq.fa_units > 1)].index.tolist(),
             load_units=f"{int(u[load_u].fa.sum())}/{int(load_u.sum())}", nonload_units=f"{int(u[~load_u].fa.sum())}/{int((~load_u).sum())}",
             load_unique=f"{int(uniq[load_q].fa.sum())}/{int(load_q.sum())}", nonload_unique=f"{int(uniq[~load_q].fa.sum())}/{int((~load_q).sum())}")
    c["fisher_units_load"] = float(stats.fisher_exact([[u[load_u].fa.sum(), load_u.sum() - u[load_u].fa.sum()], [u[~load_u].fa.sum(), (~load_u).sum() - u[~load_u].fa.sum()]], alternative="greater").pvalue)
    c["fisher_unique_load"] = float(stats.fisher_exact([[uniq[load_q].fa.sum(), load_q.sum() - uniq[load_q].fa.sum()], [uniq[~load_q].fa.sum(), (~load_q).sum() - uniq[~load_q].fa.sum()]], alternative="greater").pvalue)
    # 고유 기록, 블록 안 순열(노출 = 진폭 ≥ 경계), 블록 크기·경계 변형
    var = []
    rng = np.random.default_rng(7)
    for cut_lab, cut in (("B 학습 q75", b_q75), ("평가 q75", float(uniq[uniq.length >= 17].amp.quantile(.75))), ("평가 중앙", float(uniq[uniq.length >= 17].amp.quantile(.5))),
                         ("평가 q90", float(uniq[uniq.length >= 17].amp.quantile(.9)))):
        x = ((uniq.length >= 17) & (uniq.amp >= cut)).to_numpy(); y = uniq.fa.to_numpy().astype(bool)
        for bs in (30, 60, 100, 150, 300):
            lab = (uniq.index.to_numpy() - 300) // bs
            obs = int((x & y).sum()); cnt = np.zeros(20000, int)
            for b in np.unique(lab):
                ix = np.flatnonzero(lab == b)
                sh = rng.permuted(np.broadcast_to(x[ix], (20000, len(ix))), axis=1)
                cnt += sh[:, y[ix]].sum(axis=1)
            var.append(dict(cut=cut_lab, cut_value=cut, block=bs, exposed=int(x.sum()), exposed_alarms=obs, other_alarms=int((~x & y).sum()),
                            perm_p=float((1 + (cnt >= obs).sum()) / 20001)))
    c["unique_block_permutation"] = var
    # 경보 기록의 시간 군집(고유 기록): 이웃 경보 기록 사이 간격
    ar = uniq.index[uniq.fa == 1].to_numpy()
    c["alarm_records"] = ar.tolist()
    c["alarm_record_gaps"] = np.diff(ar).tolist()
    C[str(alpha)] = c
    v = pd.DataFrame(var)
    print(f"\nα={alpha}: 평가 단위 {n_units}(경보 {k_units}) → 고유 기록 {n_uni}(경보 {k_uni}); 두 번 이상 센 기록 {c['records_counted_twice_or_more']}개; 여러 번 센 경보 기록 {c['alarm_records_counted_more_than_once']}")
    print(f"   부하 상태: 단위 {c['load_units']} 대 {c['nonload_units']} (Fisher p={c['fisher_units_load']:.2e}) | 고유 {c['load_unique']} 대 {c['nonload_unique']} (p={c['fisher_unique_load']:.2e})")
    print(v.pivot(index=["cut", "exposed", "exposed_alarms", "other_alarms"], columns="block", values="perm_p").to_string(float_format=lambda z: f"{z:.4f}"))
    print("   경보 기록:", ar.tolist())
OUT["fp_intensity"] = C
dump(OUT, "redE_06_multiplicity.json")
