"""S6: 조건별 성능·부트스트랩·오차 조건 규칙·SHAP·피크 조건·계획 정보가치·절제."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeRegressor, _tree

from . import config as C
from . import cv as CV
from . import data as D
from . import features as F
from . import io
from . import metrics as MT
from . import models as M
from . import registry as R
from . import stage_models as SM

TASKS = ["B", "A1", "A2", "A3", "A4"]


# ---------------------------------------------------------------- 조건 표

def condition_table(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """구간별 해석용 조건(사후 분석 전용, 모델 입력 아님)."""
    idx = iv.index
    day = idx.normalize()
    slot = iv["slot"].to_numpy()
    c = pd.DataFrame(index=idx)
    c["month"] = idx.month
    c["daytype4"] = st["daytype4"].reindex(day).to_numpy()
    c["regime"] = st["regime"].reindex(day).to_numpy()
    c["regime_prev"] = st["regime_prev"].reindex(day).to_numpy()
    hour = iv["hour"].to_numpy()
    c["work_dayshift"] = ((c["regime"] == 2) & (hour >= 8) & (hour < 20)).astype(int)
    win = np.full(len(idx), "steady", dtype=object)
    windows = {
        "startup_0730_0845": (30, 35), "break_1000": (40, 41), "lunch_1145_1315": (47, 52),
        "break_1500": (60, 61), "break_1645_1745": (67, 70), "shift_end_1945_2030": (79, 81),
        "night_break_0000": (0, 1), "night_break_0300": (12, 13), "night_break_0500": (20, 21),
        "night_break_2200": (88, 89)}
    for name, (a, b) in windows.items():
        win[(slot >= a) & (slot <= b)] = name
    c["window"] = win
    prod = iv["prod"]
    c["prod_bin"] = pd.cut(prod, [-1, 0, 500, 1500, np.inf], labels=["0", "1-500", "500-1500", "1500+"]).astype(str)
    dprod = (prod - prod.shift(4)).abs()
    c["prod_change_bin"] = pd.cut(dprod, [-1, 100, 1000, np.inf], labels=["<100", "100-1000", "1000+"]).astype(str)
    y = iv["y_raw"]
    c["running_without_plan"] = ((prod < 100) & (y > 100)).astype(int)
    c["plan_but_idle"] = ((prod >= 500) & (y < 40)).astype(int)
    c["temp_bin"] = pd.cut(iv["temp"], [-50, 10, 20, 26, 30, 50], labels=["<10", "10-20", "20-26", "26-30", "30+"]).astype(str)
    c["holiday_or_vacation"] = (iv["holiday"].to_numpy() | (c["regime"].to_numpy() == 0)).astype(int)
    c["first_day_after_off"] = (c["daytype4"] == 0).astype(int)
    return c


def by_condition(y, preds: dict, cond: pd.DataFrame, mask: np.ndarray, cols: list[str]) -> pd.DataFrame:
    rows = []
    for model, p in preds.items():
        base = MT.regression(y[mask], p[mask])
        for col in cols:
            for val, idxs in cond[mask].groupby(col).groups.items():
                m = np.zeros(len(y), bool)
                m[y.index.get_indexer(idxs)] = True
                if m.sum() < 20:
                    continue
                r = MT.regression(y[m], p[m])
                rows.append(dict(model=model, condition=col, value=str(val), n=r["n"], MAE=r["MAE"], RMSE=r["RMSE"],
                                 bias=r["bias"], MAE_ratio=r["MAE"] / base["MAE"]))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 규칙 탐색

def tree_rules(X: pd.DataFrame, target: np.ndarray, max_depth: int = 3, min_leaf: int = 150) -> list[dict]:
    t = DecisionTreeRegressor(max_depth=max_depth, min_samples_leaf=min_leaf, random_state=C.SEED).fit(X, target)
    tr = t.tree_
    names = list(X.columns)
    out = []
    overall = float(np.mean(target))

    def walk(node, conds):
        if tr.feature[node] == _tree.TREE_UNDEFINED:
            out.append(dict(rule=" & ".join(conds) if conds else "(전체)", n=int(tr.n_node_samples[node]),
                            mean_abs_err=float(tr.value[node][0][0]), ratio=float(tr.value[node][0][0] / overall)))
            return
        f = names[tr.feature[node]]
        th = tr.threshold[node]
        walk(tr.children_left[node], conds + [f"{f} <= {th:.2f}"])
        walk(tr.children_right[node], conds + [f"{f} > {th:.2f}"])

    walk(0, [])
    return sorted(out, key=lambda r: -r["ratio"])


def rule_stability(X: pd.DataFrame, target: np.ndarray, days: np.ndarray, n_rep: int = 100) -> pd.DataFrame:
    """날짜 부트스트랩마다 트리를 다시 맞추고 첫 두 분할 변수의 선택 빈도를 센다."""
    rng = np.random.default_rng(C.SEED)
    ud = np.unique(days)
    cnt = {}
    for _ in range(n_rep):
        pick = rng.choice(ud, len(ud), replace=True)
        ix = np.concatenate([np.where(days == d)[0] for d in pick])
        t = DecisionTreeRegressor(max_depth=2, min_samples_leaf=150, random_state=C.SEED).fit(X.iloc[ix], target[ix])
        feats = {X.columns[f] for f in t.tree_.feature if f >= 0}
        for f in feats:
            cnt[f] = cnt.get(f, 0) + 1
    return pd.Series(cnt, name="selected_share").div(n_rep).sort_values(ascending=False).reset_index().rename(
        columns={"index": "feature"})


def encode_conditions(cond: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=cond.index)
    for c in ["daytype4", "regime", "regime_prev", "work_dayshift", "running_without_plan", "plan_but_idle",
              "holiday_or_vacation", "first_day_after_off", "month"]:
        X[c] = cond[c].astype(float)
    for w in cond["window"].unique():
        if w != "steady":
            X[f"win_{w}"] = (cond["window"] == w).astype(float)
    X["prod_level"] = cond["prod_bin"].map({"0": 0, "1-500": 1, "500-1500": 2, "1500+": 3}).astype(float)
    X["prod_change"] = cond["prod_change_bin"].map({"<100": 0, "100-1000": 1, "1000+": 2}).astype(float)
    X["temp_level"] = cond["temp_bin"].map({"<10": 0, "10-20": 1, "20-26": 2, "26-30": 3, "30+": 4}).astype(float)
    return X.fillna(-1)


# ---------------------------------------------------------------- 피크 조건(서술)

def peak_conditions(iv: pd.DataFrame, st: pd.DataFrame, T: float) -> dict:
    y = iv["y_train"]
    day = iv.index.normalize()
    full = st.index[(st["regime"] == 2) & (st["daytype3"] == 0)]
    ymat = y.to_numpy().reshape(-1, 96)
    dates = pd.DatetimeIndex(st.index)
    rows = []
    tmax = iv["temp"].groupby(day).max()
    for i, d in enumerate(dates):
        if d not in full or np.isfinite(ymat[i]).sum() < 90:
            continue
        v = ymat[i]
        am = int(np.nanargmax(v))
        plateau = np.nanmean(np.r_[v[36:48], v[53:60]])
        startup = np.nanmax(v[30:36])
        rows.append(dict(date=d, month=d.month, period="test" if d >= C.TEST_START else "pre_test",
                         max_slot=am, daymax=float(np.nanmax(v)), plateau=float(plateau),
                         startup_peak=float(startup), startup_excess=float(startup - plateau),
                         type="startup" if 30 <= am <= 35 else ("plateau" if 36 <= am <= 63 else "other"),
                         tmax=float(tmax.get(d, np.nan)), over_T=bool(np.nanmax(v) >= T)))
    dd = pd.DataFrame(rows)
    out = {"n_days": int(len(dd))}
    out["type_share_by_month"] = dd.groupby("month")["type"].value_counts(normalize=True).round(3).unstack().fillna(0).to_dict()
    out["startup_excess_by_month_median"] = dd.groupby("month")["startup_excess"].median().round(2).to_dict()
    # 여름(6~9월) 가동일 고원 수준 vs 최고기온 기울기(날짜 부트스트랩)
    for label, sub in (("summer_pre_test", dd[(dd.month.isin([6, 7, 8, 9])) & (dd.period == "pre_test")]),
                       ("summer_test", dd[(dd.period == "test")]),
                       ("spring_winter", dd[dd.month.isin([1, 2, 3, 4, 5])])):
        if len(sub) < 8:
            continue
        x, yv = sub["tmax"].to_numpy(), sub["plateau"].to_numpy()
        slope = float(np.polyfit(x, yv, 1)[0])
        rng = np.random.default_rng(C.SEED)
        bs = []
        for _ in range(1000):
            ix = rng.integers(0, len(sub), len(sub))
            if np.ptp(x[ix]) > 0:
                bs.append(np.polyfit(x[ix], yv[ix], 1)[0])
        out[f"plateau_slope_per_C_{label}"] = {"slope": slope, "ci90": [float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))],
                                              "n_days": int(len(sub)), "corr": float(np.corrcoef(x, yv)[0, 1])}
    return out, dd


def peak_logit(iv: pd.DataFrame, st: pd.DataFrame, T: float) -> pd.DataFrame:
    """가동일(전면 가동) 15분 구간의 T 이상 여부에 대한 해석용 로지스틱(날짜 부트스트랩 신뢰구간)."""
    y = iv["y_train"]
    day = iv.index.normalize()
    m = (st["regime"].reindex(day).to_numpy() == 2) & y.notna().to_numpy() & (iv.index < C.TEST_START)
    hour = iv["hour"].to_numpy()
    slot = iv["slot"].to_numpy()
    X = pd.DataFrame({
        "startup_0800_0900": ((slot >= 32) & (slot <= 35)).astype(float),
        "morning_0900_1200": ((hour >= 9) & (hour < 12)).astype(float),
        "afternoon_1300_1600": ((hour >= 13) & (hour < 16)).astype(float),
        "late_1600_2000": ((hour >= 16) & (hour < 20)).astype(float),
        "monday_like": (st["daytype4"].reindex(day).to_numpy() == 0).astype(float),
        "saturday": (st["daytype4"].reindex(day).to_numpy() == 2).astype(float),
        "cdd24": np.maximum(iv["temp"].to_numpy() - 24, 0),
        "summer": iv.index.month.isin([6, 7, 8, 9]).astype(float),
    }, index=iv.index)[m]
    lab = (y[m] >= T).astype(int).to_numpy()
    days = day[m]
    X = X.loc[:, X.nunique() > 1]  # 시험 전 표본에서 변화가 없는 조건(예: 전면 가동 토요일)은 제외
    fit = LogisticRegression(C=10.0, max_iter=2000).fit(X, lab)
    coef = pd.Series(fit.coef_[0], index=X.columns)
    rng = np.random.default_rng(C.SEED)
    ud = np.unique(days)
    boots = []
    for _ in range(200):
        pick = rng.choice(ud, len(ud), replace=True)
        ix = np.concatenate([np.where(days == d)[0] for d in pick])
        if lab[ix].min() == lab[ix].max():
            continue
        boots.append(LogisticRegression(C=10.0, max_iter=2000).fit(X.iloc[ix], lab[ix]).coef_[0])
    B = np.array(boots)
    return pd.DataFrame({"feature": X.columns, "odds_ratio": np.exp(coef.to_numpy()),
                         "or_ci05": np.exp(np.quantile(B, 0.05, axis=0)), "or_ci95": np.exp(np.quantile(B, 0.95, axis=0)),
                         "n": len(lab), "positives": int(lab.sum())})


# ---------------------------------------------------------------- SHAP(LightGBM 기여도)

def shap_importance(iv: pd.DataFrame, frames: dict, task: str, log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """시험 시작 전 학습 가능 구간으로 M1(LightGBM)과 하이브리드 보정기를 적합해 시험 구간 기여도를 계산."""
    X = frames[task]
    fam = "A" if task.startswith("A") else "B"
    feats = F.feature_list(fam)
    tr = CV.train_mask(X.index, iv["trainable"].to_numpy(), C.TEST_START, fam)
    te = (X.index >= C.TEST_START) & iv["usable"].to_numpy()
    rows = []
    inter = pd.DataFrame()
    for name, model in (("M1_lgbm", M.LGBModel(feats, objective="huber", alpha=10.0)),
                        ("M7_hybrid_residual", M.Hybrid(feats, fam))):
        model.fit(X.loc[tr], iv["y_train"][tr])
        contrib = model.contrib(X.loc[te])
        names = (model.features if name == "M1_lgbm" else model.inner_.features)
        mean_abs = np.abs(contrib[:, :-1]).mean(axis=0)
        for f, v in zip(names, mean_abs):
            rows.append(dict(task=task, model=name, feature=f, mean_abs_shap=float(v)))
        if name == "M1_lgbm":
            try:
                import shap
                sample = X.loc[te, names].sample(n=min(400, int(te.sum())), random_state=C.SEED)
                iv_vals = shap.TreeExplainer(model.m_).shap_interaction_values(sample)
                A = np.abs(iv_vals).mean(axis=0)
                np.fill_diagonal(A, 0)
                pairs = []
                for i in range(len(names)):
                    for j in range(i + 1, len(names)):
                        pairs.append((names[i], names[j], float(A[i, j] + A[j, i])))
                inter = pd.DataFrame(sorted(pairs, key=lambda t: -t[2])[:25], columns=["feature_1", "feature_2", "mean_abs_interaction"])
                inter.insert(0, "task", task)
            except Exception as e:  # shap 미설치 등
                log(f"  SHAP 상호작용 생략: {e}")
    imp = pd.DataFrame(rows).sort_values(["model", "mean_abs_shap"], ascending=[True, False])
    return imp, inter


# ---------------------------------------------------------------- 계획 정보가치·절제

def info_value(iv: pd.DataFrame, log=print) -> pd.DataFrame:
    """계획 정보 수준별 성능(교차검증 pooled·시험). LightGBM(M1)과 하이브리드(M7)로 비교.

    L0 달력만 / L1 날짜 단위 운영일정(헤드라인) / L2 + 시간별 가동 여부(생산량 ≥100에서 파생)
    / L3 + 시간별 생산 수량(오라클) / L3 잡음: 수량에 시간 단위 곱셈 잡음(한 시간의 네 구간은 같은 잡음).
    """
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    fr_or = CV.build_frames(iv, oracle=True)
    cvmask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        cvmask |= CV.eval_mask(y.index, usable, s, e)
    temask = CV.eval_mask(y.index, usable, C.TEST_START, C.TEST_END)
    rows = []
    rng = np.random.default_rng(C.SEED)
    hour_key = iv.index.floor("h")
    uniq_hours = pd.DatetimeIndex(hour_key.unique())
    for task in ("B", "A4"):
        fam = "A" if task.startswith("A") else "B"
        X = fr_or[task]
        levels = {
            "L0_calendar_only": (F.feature_list(fam, schedule_on=False), None),
            "L1_day_schedule(headline)": (F.feature_list(fam), None),
            "L2_plus_hourly_onoff": (F.feature_list(fam, hourly_onoff=True), None),
            "L3_plus_hourly_quantity_oracle": (F.feature_list(fam, oracle=True), None),
        }
        for sigma in (0.1, 0.25, 0.5):
            levels[f"L3_hourly_quantity_noise{int(sigma * 100)}"] = (F.feature_list(fam, oracle=True), sigma)
        for lvl, (feats, sigma) in levels.items():
            Xv = X
            if sigma is not None:
                Xv = X.copy()
                hn = pd.Series(np.exp(rng.normal(0, sigma, len(uniq_hours)) - sigma ** 2 / 2), index=uniq_hours)
                noise = hn.reindex(hour_key).to_numpy()
                Xv["plan_h"] = X["plan_h"] * noise
                Xv["plan_h_next"] = X["plan_h_next"] * hn.reindex(hour_key + pd.Timedelta(hours=1)).to_numpy()
                Xv["plan_h_prev"] = X["plan_h_prev"] * hn.reindex(hour_key - pd.Timedelta(hours=1)).to_numpy()
                Xv["plan_share_h"] = Xv["plan_h"] / Xv["plan_total"].replace(0, np.nan)
            for mname, fac in (("M1_lgbm", lambda f=feats: M.LGBModel(f, objective="huber", alpha=10.0)),
                               ("M7_hybrid", lambda f=feats: M.Hybrid(f, fam))):
                if lvl == "L0_calendar_only" and mname == "M7_hybrid":
                    continue  # 하이브리드 기준(유사일)은 일정 정보를 쓰므로 L0에 없음
                t0 = time.time()
                pc = CV.run_cv(Xv, iv, fac, fam)
                pt = CV.run_test(Xv, iv, fac, fam)
                rc = MT.regression(y[cvmask], pc[cvmask])
                rt = MT.regression(y[temask], pt[temask])
                rows.append(dict(task=task, level=lvl, model=mname, cv_RMSE=rc["RMSE"], cv_MAE=rc["MAE"],
                                 test_RMSE=rt["RMSE"], test_MAE=rt["MAE"]))
                log(f"  info {task} {lvl} {mname} {time.time() - t0:.0f}s")
    return pd.DataFrame(rows)


def weather_noise(iv: pd.DataFrame, selection: dict, log=print) -> pd.DataFrame:
    """기상 예보오차 민감도: 기온에 날짜별 편향 + 시간별 잡음(σ, σ/2)을 넣어 학습·예측 모두 예보 대리로 사용."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    cvmask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        cvmask |= CV.eval_mask(y.index, usable, s, e)
    temask = CV.eval_mask(y.index, usable, C.TEST_START, C.TEST_END)
    rows = []
    for sigma in (0.0, 1.5, 3.0):
        ivn = iv.copy()
        if sigma > 0:
            rng = np.random.default_rng(C.SEED + int(sigma * 10))
            days = pd.DatetimeIndex(iv.index.normalize().unique())
            hours = pd.DatetimeIndex(iv.index.floor("h").unique())
            b = pd.Series(rng.normal(0, sigma, len(days)), index=days).reindex(iv.index.normalize()).to_numpy()
            e = pd.Series(rng.normal(0, sigma / 2, len(hours)), index=hours).reindex(iv.index.floor("h")).to_numpy()
            ivn["temp"] = iv["temp"] + b + e
        fr = CV.build_frames(ivn)
        for task, fam in (("B", "B"), ("A4", "A")):
            feats = F.feature_list(fam)
            chosen = selection[fam]["chosen"]
            reg = R.candidates(fam)
            pairs = [(chosen, reg[chosen])]
            if chosen != "M1_lgbm":
                pairs.append(("M1_lgbm", lambda f=feats: M.LGBModel(f, objective="huber", alpha=10.0)))
            for mname, fac in pairs:
                pc = CV.run_cv(fr[task], ivn, fac, fam)
                pt = CV.run_test(fr[task], ivn, fac, fam)
                rows.append(dict(sigma_C=sigma, task=task, model=mname,
                                 cv_RMSE=MT.regression(y[cvmask], pc[cvmask])["RMSE"],
                                 test_RMSE=MT.regression(y[temask], pt[temask])["RMSE"]))
                log(f"  weather-noise {sigma} {task} {mname}")
    return pd.DataFrame(rows)


def ablations(iv: pd.DataFrame, df: pd.DataFrame, diag, log=print) -> pd.DataFrame:
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    cvmask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        cvmask |= CV.eval_mask(y.index, usable, s, e)
    temask = CV.eval_mask(y.index, usable, C.TEST_START, C.TEST_END)
    rows = []

    def rec(name, task, pc, pt):
        rc = MT.regression(y[cvmask], pc[cvmask])
        rt = MT.regression(y[temask], pt[temask])
        rows.append(dict(ablation=name, task=task, cv_RMSE=rc["RMSE"], cv_MAE=rc["MAE"], test_RMSE=rt["RMSE"],
                         test_MAE=rt["MAE"]))
        log(f"  ablation {name} {task}")

    frames = CV.build_frames(iv)
    # 기상 제외
    for task, fam in (("B", "B"), ("A4", "A")):
        fac = lambda f=F.feature_list(fam, weather_on=False): M.Hybrid(f, fam)
        rec("hybrid_no_weather", task, CV.run_cv(frames[task], iv, fac, fam), CV.run_test(frames[task], iv, fac, fam))
    # 발행 시각 24:00 (B)
    fr24 = CV.build_frames(iv, issue_hour_b=24)
    for mname, fac in (("BL5_regime_analog", lambda: M.AnalogDay("analog_regime")),
                       ("M9l_analog_level_adj", lambda: M.AnalogAdjusted(True, False))):
        rec(f"issue_2400_{mname}", "B", CV.run_cv(fr24["B"], iv, fac, "B"), CV.run_test(fr24["B"], iv, fac, "B"))
    # 복제 포함 학습
    iv_c = D.build_intervals(df, diag, train_on_copies=True)
    fr_c = CV.build_frames(iv_c)
    for task, fam, mname, fac in (("B", "B", "M1_lgbm", lambda: M.LGBModel(F.feature_list("B"), objective="huber", alpha=10.0)),
                                  ("B", "B", "BL5_regime_analog", lambda: M.AnalogDay("analog_regime")),
                                  ("A4", "A", "M1_lgbm", lambda: M.LGBModel(F.feature_list("A"), objective="huber", alpha=10.0)),
                                  ("A4", "A", "M7_hybrid", lambda: M.Hybrid(F.feature_list("A"), "A"))):
        rec(f"train_on_copies_{mname}", task, CV.run_cv(fr_c[task], iv_c, fac, fam), CV.run_test(fr_c[task], iv_c, fac, fam))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 피크 경보 FN/FP 집중 조건

def alarm_error_conditions(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """다음 1시간 피크 경보(선택 확률 방법·F1 문턱)의 FN/FP를 목표 창 조건별로 교차집계(분모 병기)."""
    import json
    pk = json.loads((C.OUTPUT_DIR / "peak" / "peak_summary.json").read_text(encoding="utf-8"))
    m = pk["prob_method"]["chosen"]
    tau = pk["tau"][m]["tau_f1"]
    pr = pd.read_csv(C.ARTIFACT_DIR / "next_hour_prob.csv.gz", index_col=0, parse_dates=True).reindex(iv.index)
    ok = pr["common"].fillna(False).astype(bool).to_numpy()
    lab = pr["label"].to_numpy() == 1
    alarm = pr[m].to_numpy() >= tau
    idx = iv.index
    tgt = idx + pd.Timedelta(minutes=15)  # 목표 창의 첫 구간
    day = tgt.normalize()
    cond = pd.DataFrame(index=idx)
    cond["target_hour_band"] = pd.cut(tgt.hour, [-1, 6, 7, 8, 11, 12, 15, 19, 23],
                                      labels=["00-06", "07", "08", "09-11", "12", "13-15", "16-19", "20-23"]).astype(str)
    cond["daytype4"] = st["daytype4"].reindex(day).to_numpy()
    cond["regime"] = st["regime"].reindex(day).to_numpy()
    cond["regime_prev"] = st["regime_prev"].reindex(day).to_numpy()
    cond["temp_bin"] = pd.cut(iv["temp"].shift(-1), [-50, 20, 26, 30, 50], labels=["<20", "20-26", "26-30", "30+"]).astype(str)
    cond["month"] = tgt.month
    cond["now_above_T"] = (iv["y"].to_numpy() >= pr["T"].to_numpy()).astype(int)
    rows = []
    for per, (s0, e0) in {"cv": (C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2]), "test": (C.TEST_START, C.TEST_END)}.items():
        pm = ok & (idx >= s0) & (idx < e0)
        tot_fn = int((pm & lab & ~alarm).sum())
        tot_fp = int((pm & ~lab & alarm).sum())
        for col in cond.columns:
            for val, ix in cond[pm].groupby(col).groups.items():
                mm = np.zeros(len(idx), bool)
                mm[idx.get_indexer(ix)] = True
                pos = int((mm & lab).sum())
                neg = int((mm & ~lab).sum())
                fn = int((mm & lab & ~alarm).sum())
                fp = int((mm & ~lab & alarm).sum())
                rows.append(dict(period=per, condition=col, value=str(val), n=int(mm.sum()), positives=pos,
                                 FN=fn, FP=fp, miss_rate=fn / pos if pos else np.nan,
                                 false_alarm_rate=fp / neg if neg else np.nan,
                                 share_of_all_FN=fn / tot_fn if tot_fn else np.nan,
                                 share_of_all_FP=fp / tot_fp if tot_fp else np.nan))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 주 실행

def run(iv: pd.DataFrame, frames: dict, selection: dict, df: pd.DataFrame | None = None, diag=None,
        log=print) -> dict:
    od = io.out_dir("analysis")
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    st = F.schedule_table(iv)
    cond = condition_table(iv, st)
    temask = CV.eval_mask(y.index, usable, C.TEST_START, C.TEST_END)
    cvmask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        cvmask |= CV.eval_mask(y.index, usable, s, e)
    summary = {}
    # 1) 조건별 성능(모든 모델) + 기술점수
    rows, skill_rows, boot_rows = [], [], []
    cvm = pd.read_csv(C.OUTPUT_DIR / "cv" / "cv_metrics.csv")
    for task in TASKS:
        pt = SM.load_predictions("test", task).reindex(y.index)
        models = [c for c in pt.columns if c not in ("y", "usable")]
        preds = {m: pt[m] for m in models}
        t = by_condition(y, preds, cond, temask, ["work_dayshift", "month", "daytype4", "regime", "window"])
        t.insert(0, "task", task)
        rows.append(t)
        fam = "A" if task.startswith("A") else "B"
        chosen = selection[fam]["chosen"]
        pooled = cvm[(cvm.task == task) & (cvm.split == "pooled")].set_index("model")["RMSE"]
        bl = [m for m in pooled.index if m.startswith("BL")]
        best_bl = pooled[bl].idxmin()
        naive = "BL1_persistence" if fam == "A" else "BL2_same_daytype"
        for m in models:
            r = MT.regression(y[temask], preds[m][temask])
            rb = MT.regression(y[temask], preds[best_bl][temask])
            rn = MT.regression(y[temask], preds[naive][temask])
            skill_rows.append(dict(task=task, model=m, test_RMSE=r["RMSE"], test_MAE=r["MAE"],
                                   skill_vs_best_baseline=1 - r["RMSE"] / rb["RMSE"], best_baseline=best_bl,
                                   skill_vs_naive=1 - r["RMSE"] / rn["RMSE"], naive=naive))
        for other in (best_bl, naive):
            if other == chosen:
                continue
            for stat in ("RMSE", "MAE") + (("daymax_MAE",) if task == "B" else ()):
                for bd in (1, 7):
                    b = MT.paired_day_bootstrap(y, preds[chosen], preds[other], temask, stat=stat, block_days=bd)
                    boot_rows.append(dict(task=task, chosen=chosen, vs=other, block_days=bd, **b))
    io.write_csv(pd.concat(rows, ignore_index=True), od / "test_by_condition.csv")
    io.write_csv(pd.DataFrame(skill_rows), od / "test_skill.csv")
    io.write_csv(pd.DataFrame(boot_rows).assign(ci90=lambda d: d["ci90"].astype(str)), od / "test_bootstrap.csv")

    # 2) 오차가 큰 조건: 선택 모델, 시험·교차검증
    rule_out = []
    stab_out = []
    for task in ("B", "A4"):
        fam = "A" if task.startswith("A") else "B"
        chosen = selection[fam]["chosen"]
        for per, mask in (("test", temask), ("cv", cvmask)):
            src = "test" if per == "test" else "oof"
            p = SM.load_predictions(src, task).reindex(y.index)[chosen]
            m = mask & p.notna().to_numpy()
            err = np.abs(p[m] - y[m]).to_numpy()
            Xc = encode_conditions(cond[m])
            for r in tree_rules(Xc, err):
                rule_out.append(dict(task=task, model=chosen, period=per, **r))
            s = rule_stability(Xc, err, Xc.index.normalize().to_numpy())
            s.insert(0, "period", per)
            s.insert(0, "task", task)
            stab_out.append(s)
    io.write_csv(pd.DataFrame(rule_out), od / "error_rules.csv")
    io.write_csv(pd.concat(stab_out, ignore_index=True), od / "error_rule_stability.csv")

    # 3) SHAP
    imps, inters = [], []
    for task in ("B", "A4"):
        imp, inter = shap_importance(iv, frames, task, log=log)
        imps.append(imp)
        inters.append(inter)
    io.write_csv(pd.concat(imps, ignore_index=True), od / "shap_importance.csv")
    io.write_csv(pd.concat(inters, ignore_index=True), od / "shap_interactions.csv")

    # 4) 피크 조건(서술) + 로지스틱
    T = CV.peak_threshold(iv, C.TEST_START)
    pc_sum, pc_days = peak_conditions(iv, st, T)
    io.write_csv(pc_days, od / "peak_days.csv")
    io.write_json(pc_sum, od / "peak_conditions.json")
    io.write_csv(peak_logit(iv, st, T), od / "peak_logit_odds.csv")
    if (C.ARTIFACT_DIR / "next_hour_prob.csv.gz").exists():
        io.write_csv(alarm_error_conditions(iv, st), od / "peak_alarm_error_conditions.csv")
    summary["peak_conditions"] = pc_sum

    io.write_json(summary, od / "analysis_summary.json")
    return summary


def learning_curve(iv: pd.DataFrame, log=print) -> pd.DataFrame:
    """사후 설명용(시험 구간을 본 뒤 추가, 선택·설계에 쓰지 않음): 학습 창 길이(최근 N일)별 시험 성능.
    주간 재학습마다 같은 길이의 창을 쓴다."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    temask = CV.eval_mask(y.index, usable, C.TEST_START, C.TEST_END)
    frames = CV.build_frames(iv)
    rows = []
    for task in ("B", "A4"):
        fam = "A" if task.startswith("A") else "B"
        X = frames[task]
        feats = F.feature_list(fam)
        for win in (30, 60, 90, None):
            for mname, fac in (("M1_lgbm", lambda: M.LGBModel(feats, objective="huber", alpha=10.0)),
                               ("M7c_hybrid_coolmono", lambda: M.Hybrid(feats, fam, monotone=R.COOL_MONO)),
                               ("M9l_analog_level_adj", lambda: M.AnalogAdjusted(True, False))):
                if mname == "M9l_analog_level_adj" and fam == "A":
                    continue
                iv_w = iv
                pred = pd.Series(np.nan, index=X.index)
                for s0, e0 in CV.weekly_blocks(C.TEST_START, C.TEST_END):
                    tr = CV.train_mask(X.index, iv["trainable"].to_numpy(), s0, fam)
                    if win is not None:
                        tr &= X.index >= s0 - pd.Timedelta(days=win)
                    ev = (X.index >= s0) & (X.index < e0)
                    m = fac().fit(X.loc[tr], iv_w["y_train"][tr])
                    pred.loc[ev] = m.predict(X.loc[ev])
                r = MT.regression(y[temask], pred[temask])
                rows.append(dict(task=task, model=mname, train_window_days=win or "all", test_RMSE=r["RMSE"],
                                 test_MAE=r["MAE"]))
                log(f"  learning-curve {task} {mname} {win}")
    return pd.DataFrame(rows)


def run_heavy(iv: pd.DataFrame, df: pd.DataFrame, diag, selection: dict, log=print) -> None:
    """계획 정보가치 곡선·절제·기상 예보오차·학습 창 곡선(재학습이 많아 별도 단계)."""
    od = io.out_dir("analysis")
    io.write_csv(info_value(iv, log=log), od / "plan_information_value.csv")
    io.write_csv(ablations(iv, df, diag, log=log), od / "ablations.csv")
    io.write_csv(weather_noise(iv, selection, log=log), od / "weather_forecast_error.csv")
    io.write_csv(learning_curve(iv, log=log), od / "learning_curve.csv")
