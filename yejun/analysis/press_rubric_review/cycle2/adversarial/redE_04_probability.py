"""E-3 확률 층 독립 재계산.

팀의 ProbabilityCalibrator를 쓰지 않고 sklearn IsotonicRegression으로 직접 다시 만든다.
(1) 기록 단위 교차 적합이 실제로 빠지는가  (2) 사전확률(π)에 따른 Brier·ECE  (3) 분해능·판별력
(4) 경보 지시값만 쓴 2수준 예측과의 비교  (5) 상한(cap) 민감도  (6) 예측 파일 열과의 일치
"""
from redE_common import *
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

n, a = raw()
M = models()
OUT = {}


def post(lr, pi):
    lr = np.asarray(lr, float)
    return pi * lr / (pi * lr + 1 - pi)


def fit_lr(s0, s1, cap=121.0):
    s0 = s0[np.isfinite(s0)]; s1 = s1[np.isfinite(s1)]
    x = np.r_[s0, s1]; y = np.r_[np.zeros(len(s0)), np.ones(len(s1))]
    iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip").fit(x, y)
    odds = y.mean() / (1 - y.mean())
    inner = iso.y_thresholds_[(iso.y_thresholds_ > 0) & (iso.y_thresholds_ < 1)]
    floor = float((inner / (1 - inner) / odds).min()) if len(inner) else 1.0
    floor = min(floor, cap)

    def lr(s):
        s = np.asarray(s, float)
        p = np.clip(iso.predict(np.nan_to_num(s, nan=-1e9)), 1e-9, 1 - 1e-9)
        v = np.clip(p / (1 - p) / odds, floor, cap)
        return np.where(np.isfinite(s), v, np.nan)
    return lr, dict(floor=floor, cap=cap, steps=int(len(iso.X_thresholds_)), n0=int(len(s0)), n1=int(len(s1)), pi_fit=float(y.mean()))


def ece(y, p, bins=10, quantile=False):
    y, p = np.asarray(y, float), np.asarray(p, float)
    if quantile:
        edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
        idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    else:
        idx = np.clip((p * bins).astype(int), 0, bins - 1)
    tot = 0.0
    for b in np.unique(idx):
        k = idx == b
        tot += k.mean() * abs(p[k].mean() - y[k].mean())
    return float(tot)


def murphy(y, p, edges=(0, .01, .05, .1, .3, .5, .7, .9, .99, 1.0000001)):
    """Brier 분해(구간 묶음): 신뢰도 − 분해능 + 불확실성 (+ 구간 안 분산 항은 나머지로 둔다).
    예측값이 완전히 같은 행끼리 묶으면, 이상 행은 기록별 교차 보정기·정상 행은 배포 보정기라 값이 미세하게 달라
    묶음이 라벨별로 갈린다(분해능이 불확실성과 같아지는 퇴화). 그래서 팀 신뢰도 표와 같은 구간으로 묶는다."""
    b = np.clip(np.searchsorted(np.asarray(edges), p, side="right") - 1, 0, len(edges) - 2)
    df = pd.DataFrame(dict(y=y, p=p, b=b))
    g = df.groupby("b").agg(ym=("y", "mean"), pm=("p", "mean"), size=("y", "size"))
    ybar = df.y.mean(); N = len(df)
    rel = float((g["size"] * (g.pm - g.ym) ** 2).sum() / N)
    res = float((g["size"] * (g.ym - ybar) ** 2).sum() / N)
    unc = float(ybar * (1 - ybar))
    return rel, res, unc


def pure_groups(y, p):
    """예측값이 정확히 같은 행 묶음 가운데 두 라벨이 섞인 묶음 수(0이면 값만으로 라벨이 갈린다)."""
    df = pd.DataFrame(dict(y=y, p=np.round(p, 12)))
    g = df.groupby("p").y.agg(["mean", "size"])
    mixed = g[(g["mean"] > 0) & (g["mean"] < 1)]
    return int(len(g)), int(len(mixed)), int(mixed["size"].sum())


for sid, m in M.items():
    sp = split(n, sid)
    pc, pt, pa = m.predict(sp["cal"]), m.predict(sp["test"]), m.predict(a)
    s0, st, sa = pc.score.to_numpy(), pt.score.to_numpy(), pa.score.to_numpy()
    ra = pa.record_id.to_numpy()
    y = np.r_[np.zeros(len(st)), np.ones(len(sa))]
    alarm = np.r_[pt.alarm.to_numpy(), pa.alarm.to_numpy()]
    file_prior = float(y.mean())
    n_cal_units = len(m.cal)
    o = dict(rows_cal=int(np.isfinite(s0).sum()), rows_test=len(st), rows_abn=len(sa), file_prior=file_prior)

    # ---- (1) 교차 적합: 기록 r을 뺀 적합으로 기록 r 점수 매기기
    dep_lr, info = fit_lr(s0, sa)
    oof = np.full(len(sa), np.nan); ln = []
    changed = 0
    for r in np.unique(ra):
        keep = ra != r
        f, inf_r = fit_lr(s0, sa[keep])
        assert inf_r["n1"] == int(np.isfinite(sa[keep]).sum())
        oof[~keep] = f(sa[~keep]); ln.append(f(st))
    dep_a = dep_lr(sa)
    changed = int((np.abs(oof - dep_a) > 1e-9).sum())
    ln_med = np.median(ln, axis=0); ln_dep = dep_lr(st)
    o["fit_info"] = info
    o["abn_rows_where_oof_lr_differs_from_in_sample"] = changed
    o["abn_rows_oof_lower"] = int((oof < dep_a - 1e-9).sum()); o["abn_rows_oof_higher"] = int((oof > dep_a + 1e-9).sum())
    # 팀 예측 파일과 대조
    fpath = GUARD / "outputs" / f"test_predictions_{sid}.csv"
    tf = pd.read_csv(fpath)
    fa = tf[tf.subset.eq("abnormal")]; fn_ = tf[tf.subset.eq("normal_test")]
    o["file_vs_mine_abn_lr_maxabs"] = float(np.nanmax(np.abs(fa.likelihood_ratio.to_numpy() - oof)))
    o["file_vs_mine_normal_lr_maxabs"] = float(np.nanmax(np.abs(fn_.likelihood_ratio.to_numpy() - ln_dep)))
    o["file_probability_source"] = tf.probability_source.value_counts().to_dict()
    o["file_prior_in_file"] = float(tf.file_prior.iloc[0])
    print(f"[{sid}] rows cal {o['rows_cal']} test {len(st)} abn {len(sa)}  file prior {file_prior:.4f}  fit {info}")
    print(f"[{sid}] OOF vs in-sample LR differ in {changed} abnormal rows (lower {o['abn_rows_oof_lower']}, higher {o['abn_rows_oof_higher']}); "
          f"file vs mine max|Δ| abn {o['file_vs_mine_abn_lr_maxabs']:.3g} normal {o['file_vs_mine_normal_lr_maxabs']:.3g}")

    # ---- (2) π에 따른 채점(정상 평가 행은 배포 보정기, 이상 행은 OOF — 예측 파일과 같은 구성)
    lr_all = np.r_[ln_dep, oof]
    lr_all_med = np.r_[ln_med, oof]
    rows = []
    for lab, pi in (("0.001", .001), ("0.01(배포 기본)", .01), ("0.05", .05), ("file_prior(라벨)", file_prior), ("0.3", .3), ("0.5", .5)):
        p = np.clip(post(lr_all, pi), 1e-9, 1 - 1e-9)
        rel, res, unc = murphy(y, p)
        rows.append(dict(prior=lab, brier=brier_score_loss(y, p), logloss=log_loss(y, p), ece10=ece(y, p), ece_q10=ece(y, p, quantile=True),
                         auroc=roc_auc_score(y, p), reliability=rel, resolution=res, uncertainty=unc, distinct=int(len(np.unique(np.round(p, 12))))))
    t = pd.DataFrame(rows)
    print(t.to_string(index=False, float_format=lambda v: f"{v:.5f}"))
    o["by_prior"] = t.to_dict("records")
    pm = np.clip(post(lr_all_med, file_prior), 1e-9, 1 - 1e-9)
    o["team_style_median_normal"] = dict(brier=float(brier_score_loss(y, pm)), logloss=float(log_loss(y, pm)), ece=ece(y, pm))
    print(f"[{sid}] team-style(정상=겹 중앙값) file prior: Brier {o['team_style_median_normal']['brier']:.6f} logloss {o['team_style_median_normal']['logloss']:.5f} ECE {o['team_style_median_normal']['ece']:.5f}")

    # ---- (3) 분해능: 값의 종류와 상한·하한에 몰린 비율
    at_cap = np.isclose(lr_all, 121.0); at_floor = np.isclose(lr_all, info["floor"]) | (lr_all <= np.nanmin(lr_all) + 1e-12)
    o["share_at_cap_all"] = float(at_cap.mean()); o["share_at_floor_all"] = float(at_floor.mean())
    o["abn_rows_at_cap"] = int(at_cap[y == 1].sum()); o["normal_rows_at_cap"] = int(at_cap[y == 0].sum())
    o["alarm_rows"] = int(alarm.sum()); o["alarm_rows_at_cap"] = int((at_cap & (alarm == 1)).sum())
    o["distinct_lr_values"] = int(len(np.unique(np.round(lr_all[np.isfinite(lr_all)], 9))))
    o["rows_between_floor_and_cap"] = int((~at_cap & ~at_floor & np.isfinite(lr_all)).sum())
    print(f"[{sid}] LR 값 종류 {o['distinct_lr_values']}; 상한 {at_cap.sum()}행({at_cap.mean():.1%}), 하한 {at_floor.sum()}행({at_floor.mean():.1%}), 사이 {o['rows_between_floor_and_cap']}행; "
          f"경보 {o['alarm_rows']}행 중 상한 {o['alarm_rows_at_cap']}행")
    pf = post(lr_all, file_prior)
    ng, nmixed, rows_mixed = pure_groups(y, pf)
    o["probability_value_groups"] = ng; o["groups_with_both_labels"] = nmixed; o["rows_in_mixed_groups"] = rows_mixed
    floor_norm = float(np.nanmin(ln_dep)); ab_floorish = oof[oof < 1]
    o["normal_floor_lr"] = floor_norm
    o["abn_rows_lr_below_normal_floor"] = int((oof < floor_norm - 1e-12).sum()); o["abn_rows_lr_lt1"] = int(len(ab_floorish))
    print(f"[{sid}] 값이 같은 묶음 {ng}개 중 두 라벨이 섞인 묶음 {nmixed}개({rows_mixed}행). 정상 하한 LR {floor_norm:.6f}; 이상 행 중 그보다 작은 LR {o['abn_rows_lr_below_normal_floor']}행")
    ka_ = alarm == 1
    o["ece_alarm_rows_file_prior"] = float(abs(pf[ka_].mean() - y[ka_].mean()))
    o["alarm_rows_mean_p_file_prior"] = float(pf[ka_].mean()); o["alarm_rows_observed"] = float(y[ka_].mean())
    from scipy import stats as _st
    k_, n_ = int(y[ka_].sum()), int(ka_.sum())
    o["alarm_rows_observed_ci95"] = [float(_st.beta.ppf(.025, k_, n_ - k_ + 1)) if k_ > 0 else 0.0, float(_st.beta.ppf(.975, k_ + 1, n_ - k_)) if k_ < n_ else 1.0]
    print(f"[{sid}] 경보 행만: 평균 예측 {pf[ka_].mean():.4f} 대 관측 {y[ka_].mean():.4f} (95% {o['alarm_rows_observed_ci95'][0]:.4f}~{o['alarm_rows_observed_ci95'][1]:.4f}) → 경보 행 보정 오차 {o['ece_alarm_rows_file_prior']:.4f}")
    # 경보 행 안에서 참/거짓 경보 판별
    ka = alarm == 1
    if (y[ka] == 0).any():
        o["auroc_within_alarms"] = float(roc_auc_score(y[ka], lr_all[ka]))
        o["false_alarm_lr"] = lr_all[ka & (y == 0)].tolist()
        print(f"[{sid}] 경보 행 안 AUROC(참 대 거짓 경보) {o['auroc_within_alarms']:.3f}; 거짓 경보 LR {o['false_alarm_lr']}")
    else:
        o["auroc_within_alarms"] = None
    # 점수 자체와 확률의 판별력 비교(확률 변환으로 잃은 순위 정보)
    sc_all = np.r_[st, sa]; okk = np.isfinite(sc_all)
    o["auroc_raw_score"] = float(roc_auc_score(y[okk], sc_all[okk])); o["auroc_probability"] = float(roc_auc_score(y[okk], lr_all[okk]))
    print(f"[{sid}] AUROC 원점수 {o['auroc_raw_score']:.4f} → 확률(상한·하한 뒤) {o['auroc_probability']:.4f}")

    # ---- (4) 경보 지시값만 쓰는 2수준 예측(기록 교차 적합): P(y|경보), P(y|무경보)
    al_t, al_a = pt.alarm.to_numpy(), pa.alarm.to_numpy()
    al_c = pc.alarm.to_numpy()
    p2 = np.full(len(y), np.nan)
    # 정상 쪽 비율은 보정 행에서, 이상 쪽 비율은 남은 20기록에서. 사전 오즈는 file_prior(팀과 같은 조건)
    def two_level(al0, al1_train):
        out = {}
        for v in (0, 1):
            p1 = ((al1_train == v).sum() + .5) / (len(al1_train) + 1)       # P(경보=v | 이상), 0 방지
            p0 = ((al0 == v).sum() + .5) / (len(al0) + 1)                    # P(경보=v | 정상)
            out[v] = p1 / p0
        return out
    pa2 = np.full(len(sa), np.nan); pn2 = []
    for r in np.unique(ra):
        keep = ra != r
        L = two_level(al_c, al_a[keep])
        pa2[~keep] = np.where(al_a[~keep] == 1, L[1], L[0])
        pn2.append(np.where(al_t == 1, L[1], L[0]))
    lr2 = np.r_[np.median(pn2, axis=0), pa2]
    for lab, pi in (("file_prior", file_prior), ("0.01", .01)):
        q = np.clip(post(lr2, pi), 1e-9, 1 - 1e-9); q_cap = np.clip(post(np.minimum(lr2, 121.0), pi), 1e-9, 1 - 1e-9)
        o[f"two_level_alarm_only_{lab}"] = dict(brier=float(brier_score_loss(y, q)), logloss=float(log_loss(y, q)), ece=ece(y, q),
                                                 brier_capped121=float(brier_score_loss(y, q_cap)), logloss_capped121=float(log_loss(y, q_cap)), ece_capped121=ece(y, q_cap))
        print(f"[{sid}] 경보만 쓴 2수준 예측 π={lab}: Brier {o[f'two_level_alarm_only_{lab}']['brier']:.5f} logloss {o[f'two_level_alarm_only_{lab}']['logloss']:.4f} ECE {o[f'two_level_alarm_only_{lab}']['ece']:.4f}"
              f" | LR 상한 121 적용 Brier {o[f'two_level_alarm_only_{lab}']['brier_capped121']:.5f} ECE {o[f'two_level_alarm_only_{lab}']['ece_capped121']:.4f}")

    # ---- (5) 상한 민감도: 경보 행이 받는 확률(π 1%)
    caps = {}
    for cap in (121.0, 500.0, 1000.0, float(o["rows_cal"] + 1), 1e9):
        f, _ = fit_lr(s0, sa, cap=cap)
        v = f(sa[pa.alarm.to_numpy() == 1])
        caps[str(cap)] = dict(p_at_cap_pi1=float(post(cap, .01)), median_alarm_p_pi1=float(np.median(post(v, .01))),
                              share_alarm_at_cap=float(np.isclose(v, cap).mean()))
    o["cap_sensitivity"] = caps
    print(f"[{sid}] 상한 민감도(π=1%, 이상 경보 행의 확률 중앙값):", {k: round(v["median_alarm_p_pi1"], 4) for k, v in caps.items()})
    OUT[sid] = o
    print()
dump(OUT, "redE_04_probability.json")
