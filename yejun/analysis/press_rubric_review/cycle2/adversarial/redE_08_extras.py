"""E 보강: (a) 기록 길이와 기록 최대 점수 — 연속 수집(모든 단위 50행)에서 명목 1/121이 유지되는가
(b) 오류 분석 산출물의 서로 다른 p값 수  (c) '대회 21/21의 95% 하한'의 사용처."""
from redE_common import *
from scipy import stats

n, a = raw()
M = models()
OUT = {}
seg = record_ids(n)
length = pd.Series(seg).groupby(seg).size().to_numpy()
for sid, m in M.items():
    p = m.predict(n)
    smax = pd.Series(np.where(np.isfinite(p.score), p.score, -np.inf)).groupby(p.record_id.to_numpy()).max().to_numpy()
    tr, ca = SPLITS[sid]
    cal = np.sort(smax[tr:ca])[::-1]
    L = length[tr:ca]
    res = {}
    # 보정 기록의 순위 비율: 50행 기록이 보정 상위 k개에서 차지하는 비율 대 전체 비율
    order = np.argsort(-smax[tr:ca])
    share50 = float((L == 50).mean())
    for k in (1, 3, 6, 12, 24):
        res[f"cal_top{k}_share50"] = float((L[order[:k]] == 50).mean())
    # 보정 이후 전체(평가) 기록에서 길이별 초과율: 보정 분포의 상위 분위(명목 k/121) 문턱
    post = np.arange(ca, 600)
    rows = []
    for k in (1, 3, 6, 12, 24, 36):
        thr = cal[k - 1]
        e = smax[post] > thr
        g50, gs = length[post] == 50, length[post] < 50
        rows.append(dict(k=k, nominal=k / 121, all=f"{int(e.sum())}/{len(post)}", rate_all=float(e.mean()),
                         len50=f"{int(e[g50].sum())}/{int(g50.sum())}", rate50=float(e[g50].mean()),
                         lenlt50=f"{int(e[gs].sum())}/{int(gs.sum())}", rate_lt50=float(e[gs].mean())))
    # 전체 600기록(보정 외)에서 50행 대 나머지의 최대 점수 순위 비교
    other = np.r_[np.arange(0, tr), post]
    mw = stats.mannwhitneyu(smax[other][length[other] == 50], smax[other][length[other] < 50], alternative="greater")
    # 보정 분포에 대한 conformal p의 평균: 교환가능하면 약 0.5
    def cp(v):
        return (1 + (smax[tr:ca][None, :] >= v[:, None]).sum(1)) / 121
    p50 = cp(smax[other][length[other] == 50]); plt50 = cp(smax[other][length[other] < 50])
    res.update(cal_share50=share50, exceed_by_length=rows, mw_len50_gt_short_p=float(mw.pvalue),
               mean_conformal_p_len50=float(p50.mean()), mean_conformal_p_lt50=float(plt50.mean()),
               share_p_le_0_1_len50=float((p50 <= .1).mean()), share_p_le_0_1_lt50=float((plt50 <= .1).mean()),
               n_len50=int((length[other] == 50).sum()), n_lt50=int((length[other] < 50).sum()))
    OUT[sid] = res
    print(f"[{sid}] 보정 120기록 중 50행 비율 {share50:.2f}; 보정 상위 1·3·6·12·24개 중 50행 비율",
          [round(res[f'cal_top{k}_share50'], 2) for k in (1, 3, 6, 12, 24)])
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"[{sid}] 보정 밖 기록: 50행 {res['n_len50']}개 대 짧은 기록 {res['n_lt50']}개 — 평균 conformal p {res['mean_conformal_p_len50']:.3f} 대 {res['mean_conformal_p_lt50']:.3f}; "
          f"p≤0.1 비율 {res['share_p_le_0_1_len50']:.3f} 대 {res['share_p_le_0_1_lt50']:.3f}; MW(50행>짧은) p={res['mw_len50_gt_short_p']:.2e}")

# (b) 서로 다른 p값
OUTD = GUARD / "outputs"
vals = []
for f, cols in (("error_conditions_stats_v2.csv", ["fisher_p_greater"]),
                ("fp_intensity_v2.csv", ["fisher_p_greater", "cmh_p", "permutation_p_greater", "spearman_p"]),
                ("fn_intensity_v2.csv", ["p_amp", "p_vib_sd"]),
                ("position_vibration_misses_v2.csv", ["fisher_p_normal_vs_high", "fisher_p_greater", "fisher_p_pos01_vs_ge2_greater"])):
    d = pd.read_csv(OUTD / f)
    for c in cols:
        for v in d[c].dropna().unique():
            vals.append((f, c, float(v)))
dv = pd.DataFrame(vals, columns=["file", "col", "p"])
OUT["distinct_p"] = dict(distinct=int(len(dv)), distinct_lt1=int((dv.p < 1).sum()), distinct_lt05=int((dv.p < .05).sum()),
                         expected_false_pos_among_distinct_lt1=float((dv.p < 1).sum() * .05),
                         bonferroni_survivors=int((dv.p * len(dv) < .05).sum()), bh_survivors=None)
q = np.sort(dv.p.to_numpy()); mtot = len(q)
bh_k = np.max(np.nonzero(q <= .05 * np.arange(1, mtot + 1) / mtot)[0]) + 1 if np.any(q <= .05 * np.arange(1, mtot + 1) / mtot) else 0
OUT["distinct_p"]["bh_survivors"] = int(bh_k)
print("서로 다른 p값:", OUT["distinct_p"])

# (c) 21/21 95% 하한의 사용처
lb = .05 ** (1 / 21)
ee = pd.read_csv(OUTD / "expected_effect_v2.csv"); lf = pd.read_csv(OUTD / "label_free_alert_probability_v2.csv")
OUT["lb_21"] = dict(value=lb, expected_effect_rows=int(np.isclose(ee.source_detect_probability, lb).sum()), expected_effect_total=len(ee),
                    label_free_rows=int(lf.tpr_basis.str.contains("21/21").sum()), label_free_total=len(lf),
                    one_episode_lower95=0.05)
print("21/21 95% 하한", round(lb, 4), "사용: expected_effect", OUT["lb_21"]["expected_effect_rows"], "/", len(ee), "행, label_free", OUT["lb_21"]["label_free_rows"], "/", len(lf), "행")
dump(OUT, "redE_08_extras.json")
