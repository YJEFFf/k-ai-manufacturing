"""검증 4·5: 운영 규칙의 사후성과 낙관 크기. redA2_01·02 결과를 다시 쓰고, 적합은 A·B 두 번만 한다.

1. 2단계 격상 기준 k(1·2·3행): 분할 격자의 정상 오경보 기록별 경보 행 수로 2단계 비율(2단계/1단계)을 분할 종류별로 센다.
   팀 주추정(비중첩 폴드 α5% 1/7 → 교대 8시간 4.2건)과 비교한다. B 오경보 기록 423·461·570이 다른 분할에서 2행이 되는지 본다.
2. 사건 공백: 이상 21기록 사이 공백으로 공백 기준별 사건 수. 정상 격자에서 여러 기록이 한 사건으로 묶인 경우.
3. 기록 경계 허용 오차: 정상·이상의 기록 경계 시각 간격 최솟값(허용 오차가 결과를 바꾸는 범위).
4. 운전 상태 경계 91.9: B α1% 오경보 3기록의 RMS, 경계를 바꿨을 때 상태별 오경보 분모.
5. AR 차수: 정상 학습만으로 고르는 기준(BIC)이 무엇을 고르는가.
6. 낙관 크기: 공개 A·B 값과 분할 격자·초모수 격자 분포(중앙값·사분위).
출력: redA2_05_rules_optimism.json
"""
import json

import numpy as np
import pandas as pd

import redA2_common as C

H = C.HERE
out = {}
grid = pd.read_csv(H / "redA2_01_split_grid.csv")
fp = pd.read_csv(H / "redA2_01_fp_records.csv")
NOMINAL_L1_PER_8H = 29.584993   # 팀 alert_levels_v2.csv B α1% 명목 1단계(교대 8시간)

# 1. 2단계 기준
esc = []
for kind in ("forward", "reverse", "window60", "random"):
    for alpha in C.ALPHAS:
        g = fp[fp.kind.eq(kind) & np.isclose(fp.alpha, alpha)]
        if not len(g):
            continue
        for k in (2, 3):
            r = float((g.alarm_rows >= k).mean())
            esc.append(dict(kind=kind, alpha=alpha, k=k, alerted_record_instances=len(g), level2_instances=int((g.alarm_rows >= k).sum()),
                            level2_ratio=round(r, 4), implied_level2_per_8h=round(NOMINAL_L1_PER_8H * r, 2)))
out["escalation"] = esc
out["team_primary"] = dict(ratio=1 / 7, per_8h=4.23, upper95=15.4, source="expected_effect_v2.csv 비중첩 폴드 300~359+360~419 α5%")
b_fp = fp[fp.record.isin([423, 461, 570]) & fp.kind.eq("forward")]
out["b_false_alarm_records_other_splits"] = (b_fp.groupby(["record", "alpha"]).alarm_rows.agg(["size", "min", "max", lambda s: int((s >= 2).sum())])
                                             .rename(columns={"<lambda_0>": "splits_with_2plus_rows"}).reset_index().to_dict("records"))
# 이상 기록별 경보 행(A·B, α 1%): k=3이면 2단계 격상 기록 수와 지연
data = C.Data()
rec = np.arange(600)
fits = {sid: C.Fitted(data, rec[:t], rec[t:c], C.V2) for sid, (t, c, e) in C.SPLITS.items()}
ab = {}
for sid, fit in fits.items():
    for alpha in (.01,):
        al = fit.alarm("a", alpha)
        f = pd.DataFrame(dict(r=data.seg["a"], a=al, pos=data.pos["a"]))
        f["cum"] = f.groupby("r").a.cumsum()
        rows = f.groupby("r").a.sum()
        esc_pos = {k: f[f.a & f.cum.eq(k)].groupby("r").pos.min() * C.D.DT for k in (2, 3)}
        ab[sid] = dict(records_ge2=int((rows >= 2).sum()), records_ge3=int((rows >= 3).sum()),
                       escalation_delay_max_s_k2=float(esc_pos[2].max()), escalation_delay_max_s_k3=float(esc_pos[3].max()),
                       min_alarm_rows_per_record=int(rows.min()))
out["abnormal_escalation_by_k"] = ab

# 2. 사건 공백
t = data.time["a"]
seg = data.seg["a"]
first, last = t.groupby(seg).min(), t.groupby(seg).max()
gaps = (first.iloc[1:].reset_index(drop=True) - last.iloc[:-1].reset_index(drop=True)).dt.total_seconds().to_numpy()
out["incident_gap"] = dict(abnormal_record_gaps_s=dict(min=float(gaps.min()), max=float(gaps.max())),
                           abnormal_incidents_by_gap={str(g): int(1 + (gaps > g).sum()) for g in (1, 2, 3, 5, 8, 9, 10, 20, 60)},
                           normal_multi_record_incidents_in_split_grid=int(grid.incident_multi_record.fillna(0).sum()),
                           normal_incident_rows=int(grid.incidents.notna().sum()))
tn = data.time["n"]; sn = data.seg["n"]
gn = (tn.groupby(sn).min().iloc[1:].reset_index(drop=True) - tn.groupby(sn).max().iloc[:-1].reset_index(drop=True)).dt.total_seconds().to_numpy()
out["incident_gap"]["normal_record_gaps_s"] = dict(min=float(gn.min()), median=float(np.median(gn)), max=float(gn.max()), share_le_60=float((gn <= 60).mean()))

# 3. 기록 경계 허용 오차
tol = {}
for key in ("n", "a"):
    dt = data.time[key].diff().dt.total_seconds().to_numpy()[1:]
    dev = np.abs(dt - 0.1)
    inner = dev[dev <= 1e-6]
    outer = dev[dev > 1e-6]
    tol[key] = dict(max_inner_deviation_s=float(inner.max()), min_boundary_deviation_s=float(outer.min()),
                    min_positive_boundary_dt_s=float(dt[(dev > 1e-6) & (dt > 0)].min()), duplicate_timestamp_boundaries=int((dt == 0).sum()))
out["time_tolerance"] = tol

# 4. 운전 상태 경계 91.9 — B α1%, 정상 평가(420~599) 17행 이상 기록
raw_cur = data.raw["n"][C.D.SENSORS[2]].to_numpy(float)
rms, _ = C.M.current_states(raw_cur, sn)
rec_rms = pd.Series(rms).groupby(sn).last()
rec_len = pd.Series(sn).groupby(sn).size()
fitB = fits["B"]
alB = pd.Series(fitB.alarm("n", .01)).groupby(sn).any()
test = (rec_rms.index >= 420) & (rec_len.to_numpy() >= 17)
state = {}
for thr in (80, 85, 88, 91.9, 95, 100, 110):
    load = test & (rec_rms.to_numpy() >= thr)
    low = test & (rec_rms.to_numpy() < thr)
    state[str(thr)] = dict(load_alerted=int(alB[load].sum()), load_records=int(load.sum()), low_alerted=int(alB[low].sum()), low_records=int(low.sum()))
out["state_boundary"] = dict(b_false_alarm_record_rms={int(r): round(float(rec_rms.loc[r]), 1) for r in (423, 461, 570)},
                             by_boundary=state, b_test_ge17_rms_quantiles={str(q): round(float(np.quantile(rec_rms[test], q)), 1) for q in (.1, .25, .5, .75, .9)})

# 5. AR 차수 — 정상 학습만의 BIC(기록 경계를 넘지 않는 설계행렬, 같은 행 집합: 차수 4가 가능한 행)
from press.scores import window_index
bic = {}
for sid, (t_end, c_end, _) in C.SPLITS.items():
    tr = np.isin(sn, rec[:t_end])
    cur = data.cur["n"]
    idx = window_index(sn, 5)
    idx = idx[tr[idx]]
    res = {}
    for p in (1, 2, 3, 4):
        X = np.column_stack([np.ones(len(idx))] + [cur[idx - k] for k in range(1, p + 1)])
        beta = np.linalg.lstsq(X, cur[idx], rcond=None)[0]
        rss = float(((cur[idx] - X @ beta) ** 2).sum())
        n = len(idx)
        res[p] = dict(bic=round(n * np.log(rss / n) + (p + 1) * np.log(n), 1), rss_per_row=round(rss / n, 2), coef=[round(float(b), 4) for b in beta])
    best = min(res, key=lambda p: res[p]["bic"])
    bic[sid] = dict(n_rows=int(len(idx)), best_order_by_bic=best, **{f"ar{p}": v for p, v in res.items()})
out["ar_order_bic_normal_only"] = bic

# 6. 낙관 크기
pub = {"A": dict(f1=0.961938, fn=44, normal_alerted=0, normal_records=120), "B": dict(f1=0.970990, fn=31, normal_alerted=3, normal_records=180)}
opt = {}
for alpha in C.ALPHAS:
    for label, pool in (("forward_all", grid[grid.kind.eq("forward")]), ("forward_c120", grid[grid.kind.eq("forward") & grid.c.eq(120)]),
                        ("reverse_all", grid[grid.kind.eq("reverse")]), ("window60_c120", grid[grid.kind.eq("window60")]),
                        ("random", grid[grid.kind.eq("random")])):
        p = pool[np.isclose(pool.alpha, alpha)]
        opt[f"{alpha}_{label}"] = dict(n=len(p), f1_median=round(float(p.f1.median()), 4), f1_q25=round(float(p.f1.quantile(.25)), 4),
                                       f1_q75=round(float(p.f1.quantile(.75)), 4), fn_median=float(p.fn.median()), fn_q75=float(p.fn.quantile(.75)),
                                       normal_alert_rate_pooled=round(float(p.normal_units_alerted.sum() / p.normal_units.sum()), 4),
                                       normal_alert_rate_median=round(float(p.normal_alert_rate.median()), 4),
                                       share_zero_normal_alert=round(float(p.normal_units_alerted.eq(0).mean()), 3))
fwd = grid[grid.kind.eq("forward") & grid.c.eq(120) & np.isclose(grid.alpha, .01)].set_index("t")
opt["published"] = pub
opt["A_B_rank_forward_c120_alpha1"] = dict(
    A=dict(f1_share_better=float((fwd.f1 > fwd.loc[360, "f1"]).mean()), fn_share_better=float((fwd.fn < 44).mean()),
           normal_rate_share_better=float((fwd.normal_alert_rate < fwd.loc[360, "normal_alert_rate"]).mean())),
    B=dict(f1_share_better=float((fwd.f1 > fwd.loc[300, "f1"]).mean()), fn_share_better=float((fwd.fn < 31).mean()),
           normal_rate_share_worse=float((fwd.normal_alert_rate > fwd.loc[300, "normal_alert_rate"]).mean()),
           threshold=float(fwd.loc[300, "threshold"]), threshold_rank_low=int((fwd.threshold < fwd.loc[300, "threshold"]).sum()) + 1, n=len(fwd)))
hw = pd.read_csv(H / "redA2_02_hyper_grid_wide.csv")
hw["f1_mean"] = np.nan
hg = pd.read_csv(H / "redA2_02_hyper_grid.csv")
h1 = hg[np.isclose(hg.alpha, .01)].pivot_table(index="config", columns="split", values="f1")
fmax_ar2 = hw[hw.rule.eq("fmax") & hw.ar_order.astype(str).eq("2")].config
opt["hyper_grid_alpha1"] = {
    name: dict(configs=len(sub), f1_A_median=round(float(h1.loc[sub, "A"].median()), 4), f1_B_median=round(float(h1.loc[sub, "B"].median()), 4),
               f1_A_q25=round(float(h1.loc[sub, "A"].quantile(.25)), 4), f1_B_q25=round(float(h1.loc[sub, "B"].quantile(.25)), 4),
               v2_share_better_A=round(float((h1.loc[sub, "A"] > 0.961938).mean()), 3), v2_share_better_B=round(float((h1.loc[sub, "B"] > 0.970990).mean()), 3))
    for name, sub in (("all_1440", h1.index), ("fmax_480", hw[hw.rule.eq("fmax")].config), ("fmax_AR2_96", fmax_ar2),
                      ("fmax_noAR_96(v1 계열)", hw[hw.rule.eq("fmax") & hw.ar_order.astype(str).eq("none")].config))}
out["optimism"] = opt
(H / "redA2_05_rules_optimism.json").write_text(json.dumps(C.D.to_jsonable(out), ensure_ascii=False, indent=1), encoding="utf-8")
pd.set_option("display.width", 220)
print(pd.DataFrame(esc).to_string(index=False))
for k in ("b_false_alarm_records_other_splits", "abnormal_escalation_by_k", "incident_gap", "time_tolerance", "state_boundary", "ar_order_bic_normal_only"):
    print(k, json.dumps(C.D.to_jsonable(out[k]), ensure_ascii=False))
print(json.dumps(C.D.to_jsonable({k: v for k, v in opt.items() if k.startswith("0.01") or k in ("A_B_rank_forward_c120_alpha1", "hyper_grid_alpha1")}), ensure_ascii=False, indent=0))
