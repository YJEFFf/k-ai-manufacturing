"""P1 위원 독립 재계산: 원본 CSV(공식 ZIP)와 제출 artifacts의 행 단위 예측만으로 헤드라인을 다시 계산한다.

팀 코드(powerguard)를 import하지 않는다. 정답 마스크·기준모델·피크 기준·확률 지표를 따로 구현한다.
사용: python p1_independent_check.py <official_zip> <artifacts_dir> <out_json>
"""
from __future__ import annotations

import io
import json
import sys
import zipfile

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

ZIP, ART, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
P = ["15분", "30분", "45분", "60분"]
HOL = pd.to_datetime(["2021-01-01", "2021-02-11", "2021-02-12", "2021-02-13", "2021-03-01", "2021-05-05",
                      "2021-05-19", "2021-06-06", "2021-08-15", "2021-08-16"])
TEST_S, TEST_E = pd.Timestamp("2021-08-01"), pd.Timestamp("2021-09-15")
res: dict = {}

with zipfile.ZipFile(ZIP) as zf:
    raw = zf.read("data/okm_augumented_2021.csv")
df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
df["date"] = pd.to_datetime(df["날짜"].astype(str), format="%Y%m%d")

# ---- 1. 일 단위 복제(같은 96값), 시간 열 손상, 월별 고유 패턴
keys = {d: tuple(x[P].to_numpy().ravel()) for d, x in df.groupby("date", sort=True)}
grp: dict = {}
for d, k in keys.items():
    grp.setdefault(k, []).append(d)
n_days = len(keys)
n_unique = len(grp)
corrupt = sorted(d for d, x in df.groupby("date") if list(x["시간"]) != list(range(24)))
multi = [sorted(v) for v in grp.values() if len(v) > 1]
# 월별: 그 달 날짜 중 다른 날짜와 패턴을 공유하는 날 수
share = pd.Series({d: len(grp[keys[d]]) > 1 for d in keys})
res["copies"] = {
    "days": n_days, "unique_patterns": n_unique, "duplicate_days(=days-unique)": n_days - n_unique,
    "groups_multi": len(multi),
    "days_sharing_pattern_by_month": {int(m): int(v) for m, v in share.groupby(share.index.month).sum().items()},
    "groups_all_members_in_may_sep": sum(all(d.month >= 5 for d in g) for g in multi),
    "groups_with_member_in_test": sum(any(d >= TEST_S for d in g) for g in multi),
    "corrupt_hour_dates": [str(d.date()) for d in corrupt],
}

# ---- 2. 15분 시계열(손상일 제외), 정전(0), 시험 정답 마스크
good = df[~df["date"].isin(corrupt)]
rows = []
for q, c in enumerate(P):
    ts = good["date"] + pd.to_timedelta(good["시간"], unit="h") + pd.Timedelta(minutes=15 * q)
    rows.append(pd.Series(good[c].to_numpy(float), index=ts))
y_all = pd.concat(rows).sort_index()
full_idx = pd.date_range(df["date"].min(), df["date"].max() + pd.Timedelta(hours=23, minutes=45), freq="15min")
y_all = y_all.reindex(full_idx)
test_m = (y_all.index >= TEST_S) & (y_all.index < TEST_E)
y_meas = y_all.where(y_all > 0)
res["test_truth"] = {"test_intervals": int(test_m.sum()),
                     "test_intervals_power_gt0": int((test_m & (y_all > 0).to_numpy()).sum()),
                     "test_zero_power_intervals": int((test_m & (y_all == 0).to_numpy()).sum())}

# ---- 3. 가동 체제(일 생산 총량) — 팀과 같은 정보(전날 확정 가정)
prod_day = df[~df["date"].isin(corrupt)].groupby("date")["생산량"].sum()
regime = pd.Series(np.select([prod_day == 0, prod_day < 5000], [0, 1], 2), index=prod_day.index)
tdays = pd.date_range(TEST_S, TEST_E - pd.Timedelta(days=1))
res["test_regime_days"] = {int(k): int(v) for k, v in regime.reindex(tdays).value_counts().items()}
wd = pd.Series(tdays.dayofweek, index=tdays)
res["test_weekday_stop_days"] = [str(d.date()) for d in tdays if wd[d] < 5 and regime.get(d) == 0 and d not in HOL]
res["test_holiday_or_weekend_full_days"] = [str(d.date()) for d in tdays
                                            if (wd[d] >= 5 or d in HOL) and regime.get(d) == 2]


def daytype3(dates):
    dates = pd.DatetimeIndex(dates)
    return np.where(dates.isin(HOL) | (dates.dayofweek == 6), 2, np.where(dates.dayofweek == 5, 1, 0))


# ---- 4. 학습 풀(5/1~7/31): 손상일 제외, 복제군은 1개만, 0 제외 → q95 기준
pre = y_meas[(y_meas.index >= "2021-05-01") & (y_meas.index < TEST_S)]
dup_drop = set()
for g in multi:
    if any(pd.Timestamp("2021-05-01") <= d < TEST_S for d in g):
        keep = max(g)
        dup_drop |= {d for d in g if d != keep}
pre_nodup = pre[~pre.index.normalize().isin(list(dup_drop))]
res["peak_threshold"] = {
    "q95_may_jul_measured_nodup": float(np.quantile(pre_nodup.dropna(), 0.95)),
    "q95_may_jul_measured_nodup_excl_0709": float(np.quantile(
        pre_nodup[pre_nodup.index.normalize() != pd.Timestamp("2021-07-09")].dropna(), 0.95)),
    "q95_may_jul_measured_all": float(np.quantile(pre.dropna(), 0.95)),
    "dup_dropped_in_pool": [str(d.date()) for d in sorted(dup_drop) if d >= pd.Timestamp("2021-05-01")],
}
T = res["peak_threshold"]["q95_may_jul_measured_nodup_excl_0709"]

# ---- 5. 제출 행 단위 예측으로 시험 지표 재계산(내 정답 마스크)
yt = y_meas[test_m]


def met(p, y=yt, mask=None):
    d = pd.DataFrame({"y": y, "p": p}).dropna()
    if mask is not None:
        d = d[mask.reindex(d.index).fillna(False).to_numpy()]
    e = d["p"] - d["y"]
    return {"n": int(len(d)), "RMSE": round(float(np.sqrt((e ** 2).mean())), 4), "MAE": round(float(e.abs().mean()), 4)}


res["test_metrics_recomputed"] = {}
art = {}
for task in ("B", "A1", "A2", "A3", "A4"):
    a = pd.read_csv(f"{ART}/test_{task}.csv.gz", index_col=0, parse_dates=True)
    art[task] = a
    res["test_metrics_recomputed"][task] = {m: met(a[m]) for m in a.columns if m not in ("y", "usable")}

# ---- 6. 독립 기준모델(과제 B, D-1 17:00 발행): 7일 전 같은 슬롯, 달력 프로파일, 체제 프로파일(정적·주간 재학습)
day_of = y_meas.index.normalize()
slot = (y_meas.index.hour * 4 + y_meas.index.minute // 15).to_numpy()
dt3 = pd.Series(daytype3(day_of), index=y_meas.index)
reg_s = pd.Series(regime.reindex(day_of).to_numpy(), index=y_meas.index)
train_ok = pd.Series(False, index=y_meas.index)
train_ok[(y_meas.index >= "2021-05-01")] = True
train_ok &= ~day_of.isin(list(dup_drop)) & y_meas.notna()


def profile_pred(keys_fn, cutoff_blocks, fallback_fn=None):
    """키×슬롯 평균 → (fallback 키×슬롯) → 슬롯 평균. 학습 = 블록 시작 7시간 전까지 끝난 구간."""
    out = pd.Series(np.nan, index=yt.index)
    for s, e in cutoff_blocks:
        tr = train_ok & (y_meas.index < s - pd.Timedelta(hours=7))
        d = pd.DataFrame({"k": keys_fn(tr), "slot": slot[tr.to_numpy()], "y": y_meas[tr].to_numpy()})
        tab = d.groupby(["k", "slot"])["y"].mean()
        tab_s = d.groupby("slot")["y"].mean()
        ev = (yt.index >= s) & (yt.index < e)
        allm = (y_meas.index >= s) & (y_meas.index < e)
        k_ev = keys_fn(pd.Series(allm, index=y_meas.index))
        v = tab.reindex(pd.MultiIndex.from_arrays([k_ev, slot[allm]])).to_numpy()
        if fallback_fn is not None:
            d["f"] = fallback_fn(tr)
            tab_f = d.groupby(["f", "slot"])["y"].mean()
            f_ev = fallback_fn(pd.Series(allm, index=y_meas.index))
            v = np.where(np.isfinite(v), v, tab_f.reindex(pd.MultiIndex.from_arrays([f_ev, slot[allm]])).to_numpy())
        v = np.where(np.isfinite(v), v, tab_s.reindex(slot[allm]).to_numpy())
        out[ev] = v
    return out


static = [(TEST_S, TEST_E)]
mondays = [d for d in tdays if d.dayofweek == 0 and d != TEST_S]
starts = [TEST_S] + mondays
weekly = list(zip(starts, starts[1:] + [TEST_E]))
k_cal = lambda m: dt3[m.to_numpy()].to_numpy()
k_reg = lambda m: (reg_s[m.to_numpy()].to_numpy() * 10 + dt3[m.to_numpy()].to_numpy())
k_regonly = lambda m: reg_s[m.to_numpy()].to_numpy()
# 요일유형4: 휴무 다음 평일(월요일 등)을 따로 — 야간조 이월이 없는 날
_d3_prev = pd.Series(daytype3(day_of - pd.Timedelta(days=1)), index=y_meas.index)
dt4 = pd.Series(np.where(dt3 == 2, 3, np.where(dt3 == 1, 2, np.where(_d3_prev == 0, 1, 0))), index=y_meas.index)
k_reg4 = lambda m: (reg_s[m.to_numpy()].to_numpy() * 10 + dt4[m.to_numpy()].to_numpy())
sn7 = y_meas.shift(96 * 7)[test_m]
sn7 = sn7.fillna(y_meas.shift(96 * 14)[test_m])
ind = {
    "SN7_same_slot_last_week": sn7,
    "profile_daytype3_static": profile_pred(k_cal, static),
    "profile_regime_x_daytype3_static": profile_pred(k_reg, static, k_regonly),
    "profile_regime_x_daytype3_weekly": profile_pred(k_reg, weekly, k_regonly),
    "profile_regime_only_weekly": profile_pred(k_regonly, weekly),
    "profile_regime_x_daytype4_weekly": profile_pred(k_reg4, weekly, k_regonly),
}
res["independent_baselines_B_test"] = {k: met(v) for k, v in ind.items()}
chosen_B = art["B"]["M8_blend"]
# 날짜 짝 부트스트랩: M8_blend − 독립 체제 프로파일(주간)
d = pd.DataFrame({"y": yt, "a": chosen_B, "b": ind["profile_regime_x_daytype4_weekly"]}).dropna()
g = d.assign(ea=(d.a - d.y) ** 2, eb=(d.b - d.y) ** 2).groupby(d.index.normalize())
A, B, W = g["ea"].sum().to_numpy(), g["eb"].sum().to_numpy(), g.size().to_numpy().astype(float)
rng = np.random.default_rng(1)
bs = []
for _ in range(4000):
    ix = rng.integers(0, len(A), len(A))
    bs.append(np.sqrt(A[ix].sum() / W[ix].sum()) - np.sqrt(B[ix].sum() / W[ix].sum()))
res["B_chosen_minus_indep_regime_x_daytype4_profile_weekly"] = {
    "diff": round(float(np.sqrt(A.sum() / W.sum()) - np.sqrt(B.sum() / W.sum())), 4),
    "ci90": [round(float(np.quantile(bs, 0.05)), 4), round(float(np.quantile(bs, 0.95)), 4)], "n_days": int(len(A))}

# 시험 오차 집중: 날짜별 SSE 비중, 체제별 RMSE
e2 = ((chosen_B - yt) ** 2).dropna()
by_day = e2.groupby(e2.index.normalize()).sum().sort_values(ascending=False)
res["B_chosen_top_error_days"] = [{"date": str(k.date()), "sse_share": round(float(v / e2.sum()), 4),
                                   "regime": int(regime.get(k, -1)), "dow": int(k.dayofweek)} for k, v in by_day.head(5).items()]
res["B_chosen_rmse_excluding_0816"] = met(chosen_B, mask=pd.Series(yt.index.normalize() != pd.Timestamp("2021-08-16"), index=yt.index))
for r in (0, 1, 2):
    res[f"B_chosen_rmse_regime{r}"] = met(chosen_B, mask=pd.Series(reg_s[test_m].to_numpy() == r, index=yt.index))
    res[f"B_BL3_rmse_regime{r}"] = met(art["B"]["BL3_profile"], mask=pd.Series(reg_s[test_m].to_numpy() == r, index=yt.index))
sse_m = ((art["B"]["M8_blend"] - yt) ** 2).dropna()
sse_p = ((art["B"]["BL3_profile"] - yt) ** 2).dropna()
diff_day = (sse_m.groupby(sse_m.index.normalize()).sum() - sse_p.groupby(sse_p.index.normalize()).sum())
res["B_M8_minus_BL3_SSE"] = {"total": round(float(diff_day.sum()), 1),
                             "0816": round(float(diff_day.get(pd.Timestamp("2021-08-16"), np.nan)), 1),
                             "share_0816": round(float(diff_day.get(pd.Timestamp("2021-08-16")) / diff_day.sum()), 4)}

# ---- 7. 과제 A 지속성(내 구현)
for h in (1, 2, 3, 4):
    p = y_meas.shift(h)
    for k in range(1, 8):
        p = p.fillna(y_meas.shift(h + k))
    res.setdefault("persistence_A_test", {})[f"A{h}"] = met(p[test_m])

# ---- 8. 다음 1시간 피크 확률: 내 라벨로 재계산
nh = pd.read_csv(f"{ART}/next_hour_prob.csv.gz", index_col=0, parse_dates=True)
yv = y_meas.reindex(nh.index)
fut = pd.concat([yv.shift(-k) for k in range(1, 5)], axis=1)
valid = fut.notna().all(axis=1)
lab = (fut.max(axis=1) >= T) & valid
te = (nh.index >= TEST_S) & (nh.index < TEST_E)
common = nh["common"].astype(str).str.lower().eq("true").to_numpy()
m = te & common & valid.to_numpy()
res["next_hour_label_agreement_test"] = {"n_rows": int(m.sum()),
                                         "label_mismatch": int((lab[m].astype(int).to_numpy() != nh["label"][m].astype(float).astype(int).to_numpy()).sum()),
                                         "T_used": T}


def cls(prob, y, tau):
    a = prob >= tau
    tp, fp, fn = int((a & y).sum()), int((a & ~y).sum()), int((~a & y).sum())
    pr = tp / (tp + fp) if tp + fp else float("nan")
    rc = tp / (tp + fn) if tp + fn else float("nan")
    edges = np.linspace(0, 1, 11)
    b = np.clip(np.digitize(prob, edges[1:-1]), 0, 9)
    ece = sum((b == k).mean() * abs(prob[b == k].mean() - y[b == k].mean()) for k in range(10) if (b == k).any())
    return {"tau": tau, "base_rate": round(float(y.mean()), 4), "precision": round(pr, 4), "recall": round(rc, 4),
            "F1": round(2 * tp / (2 * tp + fp + fn), 4), "Brier": round(float(np.mean((prob - y) ** 2)), 5),
            "PR_AUC": round(float(average_precision_score(y, prob)), 4), "ECE": round(float(ece), 5)}


yy = lab[m].to_numpy()
res["next_hour_test_recomputed"] = {
    "P_residual_sim@0.5": cls(nh["P_residual_sim"].to_numpy()[m], yy, 0.5),
    "P_climatology@0.15(cv_tau)": cls(nh["P_climatology"].to_numpy()[m], yy, 0.15),
    "P_lgbm_classifier@0.1(cv_tau)": cls(nh["P_lgbm_classifier"].to_numpy()[m], yy, 0.1),
    "R_clock": cls(nh["R_clock"].to_numpy()[m], yy, 0.5),
}
bc = res["next_hour_test_recomputed"]["P_climatology@0.15(cv_tau)"]["Brier"]
res["next_hour_test_recomputed"]["BSS_vs_climatology"] = round(1 - res["next_hour_test_recomputed"]["P_residual_sim@0.5"]["Brier"] / bc, 4)
# 가동 주간(전면 가동일 08~16시 목표) 안에서만 본 판별력: 시각 규칙이 켜진 행으로 한정
on = nh["R_clock"].to_numpy()[m] == 1
res["next_hour_test_within_clock_on"] = {
    "n": int(on.sum()), "base_rate": round(float(yy[on].mean()), 4),
    "P_residual_sim_PR_AUC": round(float(average_precision_score(yy[on], nh["P_residual_sim"].to_numpy()[m][on])), 4),
    "P_climatology_PR_AUC": round(float(average_precision_score(yy[on], nh["P_climatology"].to_numpy()[m][on])), 4)}

# ---- 8b. 교차검증 OOF 재계산(내 정답: 6·7월, 전력>0, 손상일 제외, 7/30(7/28과 같은 96값) 제외)과 선택 단계 부트스트랩
cv_m = (y_meas.index >= "2021-06-01") & (y_meas.index < "2021-08-01") & (day_of != pd.Timestamp("2021-07-30"))
ycv = y_meas[cv_m]
oof = {t: pd.read_csv(f"{ART}/oof_{t}.csv.gz", index_col=0, parse_dates=True) for t in ("B", "A1", "A2", "A3", "A4")}
res["cv_pooled_recomputed"] = {t: {m: met(oof[t][m], y=ycv)["RMSE"] for m in ("M8_blend", "M1_lgbm", "M7c_hybrid_coolmono",
                                                                            "BL3_profile", "BL5_regime_analog")}
                               for t in oof}


def day_boot(tasks, ma, mb, y, src, n=4000, seed=7):
    per = []
    for t in tasks:
        d = pd.DataFrame({"y": y, "a": src[t][ma], "b": src[t][mb]}).dropna()
        g = d.assign(ea=(d.a - d.y) ** 2, eb=(d.b - d.y) ** 2).groupby(d.index.normalize())
        per.append(pd.DataFrame({"A": g["ea"].sum(), "B": g["eb"].sum(), "W": g.size()}))
    days = per[0].index
    for q in per[1:]:
        days = days.intersection(q.index)
    per = [q.reindex(days) for q in per]
    val = lambda ix: float(np.mean([np.sqrt(q["A"].to_numpy()[ix].sum() / q["W"].to_numpy()[ix].sum())
                                    - np.sqrt(q["B"].to_numpy()[ix].sum() / q["W"].to_numpy()[ix].sum()) for q in per]))
    rng = np.random.default_rng(seed)
    bs = [val(rng.integers(0, len(days), len(days))) for _ in range(n)]
    return {"diff": round(val(np.arange(len(days))), 4), "ci90": [round(float(np.quantile(bs, 0.05)), 4),
                                                                  round(float(np.quantile(bs, 0.95)), 4)], "n_days": int(len(days))}


A_ = ["A1", "A2", "A3", "A4"]
res["selection_steps_recomputed_cv"] = {
    "B: M8_blend - M1_lgbm": day_boot(["B"], "M8_blend", "M1_lgbm", ycv, oof),
    "A: M8_blend - M7c": day_boot(A_, "M8_blend", "M7c_hybrid_coolmono", ycv, oof),
    "A: M7c - M1_lgbm": day_boot(A_, "M7c_hybrid_coolmono", "M1_lgbm", ycv, oof),
}
res["same_comparisons_on_test"] = {
    "B: M8_blend - M1_lgbm": day_boot(["B"], "M8_blend", "M1_lgbm", yt, art),
    "B: M8_blend - BL3_profile": day_boot(["B"], "M8_blend", "BL3_profile", yt, art),
    "A: M8_blend - M7c": day_boot(A_, "M8_blend", "M7c_hybrid_coolmono", yt, art),
    "A: M7c - M1_lgbm": day_boot(A_, "M7c_hybrid_coolmono", "M1_lgbm", yt, art),
    "A: M7c - BL4_ridge": day_boot(A_, "M7c_hybrid_coolmono", "BL4_ridge", yt, art),
}
# 일 최대 오차(과제 B): 선택 모델 vs 프로파일 — 피크 과제에서 프로파일의 약점 확인
dm = pd.DataFrame({"y": yt, "m": art["B"]["M8_blend"], "p": art["B"]["BL3_profile"]}).dropna()
gd = dm.groupby(dm.index.normalize())
cnt = gd.size()
okd = cnt[cnt >= 80].index
ymax, mmax, pmax = gd["y"].max()[okd], gd["m"].max()[okd], gd["p"].max()[okd]
res["B_daymax_MAE_test"] = {"M8_blend": round(float((mmax - ymax).abs().mean()), 3),
                            "BL3_profile": round(float((pmax - ymax).abs().mean()), 3), "n_days": int(len(okd))}

# ---- 8c. 다음 1시간 경보(τ=0.5)의 FN/FP 집중: 첫 목표 구간 시각대(내 라벨)
tgt_h = (nh.index + pd.Timedelta(minutes=15)).hour[m]
band = pd.cut(tgt_h, [-1, 6, 7, 8, 11, 12, 15, 19, 23], labels=["00-06", "07", "08", "09-11", "12", "13-15", "16-19", "20-23"]).astype(str)
al = nh["P_residual_sim"].to_numpy()[m] >= 0.5
fnm, fpm = yy & ~al, ~yy & al
tab = pd.DataFrame({"band": band, "pos": yy, "fn": fnm, "fp": fpm}).groupby("band").sum()
tab["miss_rate"] = (tab["fn"] / tab["pos"]).round(4)
tab["fn_share"] = (tab["fn"] / tab["fn"].sum()).round(4)
res["next_hour_test_fn_fp_by_band"] = tab.astype(float).to_dict(orient="index")

# ---- 9. 월 최대(요금적용전력 근거)
mm = y_all.dropna()
res["monthly_max_raw"] = {int(k): float(v) for k, v in mm.groupby(mm.index.month).max().items() if k >= 5}

# ---- 10. 래칫 사다리(7~9월 날짜별 최대 내림차순)와 경보 등급 관측 초과율(시험, 선택 확률)
jm = y_all[(y_all.index >= "2021-07-01") & (y_all.index < TEST_E)].dropna()
dmax = jm.groupby(jm.index.normalize()).max().sort_values(ascending=False)
res["ratchet_top_days_jul_sep"] = [{"date": str(k.date()), "daymax": float(v)} for k, v in dmax.head(7).items()]
pg = nh["P_residual_sim"].to_numpy()[m]
grades = pd.cut(pg, [0, 0.2, 0.5, 0.8, 1.01], right=False, labels=["정상", "주의", "경계", "심각"])
gt = pd.DataFrame({"g": grades, "y": yy}).groupby("g", observed=False)["y"].agg(["size", "sum", "mean"])
res["alarm_grades_test_recomputed"] = {str(k): {"n": int(r["size"]), "exceed": int(r["sum"]), "rate": round(float(r["mean"]), 4)}
                                       for k, r in gt.iterrows()}

json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
