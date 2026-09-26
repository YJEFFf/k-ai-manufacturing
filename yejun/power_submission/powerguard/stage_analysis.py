"""S6: 조건별 성능·기술점수·오차 조건 규칙·SHAP·피크 조건·FN/FP 집중 조건·계획 정보가치·절제."""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
from scipy import stats
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

# 조건의 발행 시점 가용성: 사전(달력) / 전날 확정 가정(운영일정) / 예보 대리(기상) / 사후(실적·정답 기반)
AVAILABILITY = {
    "month": "사전", "daytype4": "사전", "window": "사전", "holiday_or_vacation": "전날 확정 가정",
    "first_day_after_off": "사전", "regime": "전날 확정 가정", "regime_prev": "전날 확정 가정",
    "work_dayshift": "전날 확정 가정", "holiday_work": "전날 확정 가정", "calendar_operation_mismatch": "전날 확정 가정",
    "analog_atypical": "발행 시점", "temp_bin": "예보 대리", "prod_bin": "사후(실적)", "prod_change_bin": "사후(실적)",
    "running_without_plan": "사후(정답)", "plan_but_idle": "사후(정답)",
}
RULE_CONDITIONS = ["daytype4", "regime", "regime_prev", "work_dayshift", "holiday_work", "calendar_operation_mismatch",
                   "analog_atypical", "first_day_after_off", "window", "temp_bin"]  # 규칙 탐색에 쓰는 사전 목록(월 제외)


def _cvmask(iv: pd.DataFrame) -> np.ndarray:
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    m = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        m |= CV.eval_mask(y.index, usable, s, e)
    return m


def _temask(iv: pd.DataFrame) -> np.ndarray:
    return CV.eval_mask(iv.index, iv["usable"].to_numpy(), C.TEST_START, C.TEST_END)


def build_model(name: str, fam: str, feats: list[str], selection: dict | None = None, gate: bool = True):
    """이름 → 주어진 특징 목록으로 만든 모델 생성 함수(절제용). gate=False면 계획 정지 게이트 없이."""
    base = name.split("_")[0]
    g = (lambda m: M.gated(m, fam)) if gate else (lambda m: m)
    if base == "M1":
        return lambda: g(M.LGBModel(feats, objective="huber", alpha=10.0))
    if base == "M7":
        return lambda: g(M.Hybrid(feats, fam))
    if base == "M7c":
        return lambda: g(M.Hybrid(feats, fam, monotone=R.COOL_MONO))
    if base == "M8":
        mem = selection[fam]["blend_members"]
        return lambda: M.Blend([build_model(m, fam, feats, selection, gate)() for m in mem], [0.5, 0.5])
    return R.factory(fam, name, selection)


# ---------------------------------------------------------------- 조건 표

def condition_table(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """구간별 해석용 조건(모델 입력 아님). 가용성은 AVAILABILITY에 기록한다."""
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
    c["temp_bin"] = pd.cut(iv["temp"], [-50, 20, 26, 30, 50], labels=["<20", "20-26", "26-30", "30+"]).astype(str)
    c["holiday_or_vacation"] = (iv["holiday"].to_numpy() | (c["regime"].to_numpy() == 0)).astype(int)
    c["first_day_after_off"] = (c["daytype4"] == 0).astype(int)
    c["holiday_work"] = (iv["holiday"].to_numpy() & (c["regime"].to_numpy() == 2)).astype(int)
    # 달력–실제 가동 불일치: 달력상 '휴무 다음 평일'인데 전날 가동, 또는 '연속 평일'인데 전날 정지·부분
    mis = ((c["daytype4"] == 0) & (c["regime_prev"] == 2)) | ((c["daytype4"] == 1) & (c["regime_prev"] < 2))
    c["calendar_operation_mismatch"] = mis.astype(int)
    # 익일 유사일(발행 D-1 17:00, k=2)에 전날 체제가 다른 날이 섞였는가(야간조 이월 모양이 다른 유사일)
    ia = F.analog_indices(iv, st, 2, "regime", 2)
    rp = st["regime_prev"].to_numpy()
    atyp = np.array([any(j >= 0 and rp[j] != rp[i] for j in ia[i]) for i in range(len(ia))], dtype=int)
    c["analog_atypical"] = pd.Series(atyp, index=st.index).reindex(day).to_numpy()
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


def _skill_boot(y: np.ndarray, pm: np.ndarray, pb: np.ndarray, days: np.ndarray, n_boot: int = 500) -> tuple:
    d = pd.DataFrame({"d": days, "a": (pm - y) ** 2, "b": (pb - y) ** 2}).groupby("d").sum()
    A, B = d["a"].to_numpy(), d["b"].to_numpy()
    if B.sum() == 0:
        return np.nan, np.nan, np.nan
    point = 1 - np.sqrt(A.sum() / B.sum())
    rng = np.random.default_rng(C.SEED)
    bs = []
    for _ in range(n_boot):
        ix = rng.integers(0, len(A), len(A))
        if B[ix].sum() > 0:
            bs.append(1 - np.sqrt(A[ix].sum() / B[ix].sum()))
    return float(point), float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))


def condition_skill(iv: pd.DataFrame, cond: pd.DataFrame, selection: dict) -> pd.DataFrame:
    """조건 × 모델 × 기간(교차검증·시험): 표본 수·날짜 수·MAE·편향·최강 기준 대비 RMSE 기술점수와 90% 구간."""
    y = iv["y"]
    cvm = pd.read_csv(C.OUTPUT_DIR / "cv" / "cv_metrics.csv")
    cols = ["work_dayshift", "regime", "regime_prev", "daytype4", "window", "temp_bin", "holiday_work",
            "calendar_operation_mismatch", "analog_atypical", "first_day_after_off", "month"]
    rows = []
    for task, best_bl_override in (("B", None), ("A4", None), ("B", "BL3_profile"), ("A4", "BL3_profile")):
        fam = "A" if task.startswith("A") else "B"
        pooled = cvm[(cvm.task == task) & (cvm.split == "pooled")].set_index("model")["RMSE"]
        # 기준: 교차검증 최강 기준모델(주), 프로파일 BL3(시험에서 강했던 단순 기준과의 비교, 설명용)
        best_bl = best_bl_override or pooled[[m for m in pooled.index if m.startswith("BL")]].idxmin()
        if best_bl_override and best_bl_override == pooled[[m for m in pooled.index if m.startswith("BL")]].idxmin():
            continue
        models = list(dict.fromkeys([selection[fam]["chosen"], "M1_lgbm", best_bl]))
        for per, mask, src in (("cv", _cvmask(iv), "oof"), ("test", _temask(iv), "test")):
            pr = SM.load_predictions(src, task).reindex(y.index)
            for m in models:
                if m not in pr or (best_bl_override and m == best_bl):
                    continue
                for col in cols:
                    for val, ix in cond[mask].groupby(col).groups.items():
                        mm = np.zeros(len(y), bool)
                        mm[y.index.get_indexer(ix)] = True
                        mm &= pr[m].notna().to_numpy() & pr[best_bl].notna().to_numpy()
                        if mm.sum() < 40:
                            continue
                        yy, pa, pb = y.to_numpy()[mm], pr[m].to_numpy()[mm], pr[best_bl].to_numpy()[mm]
                        sk, lo, hi = _skill_boot(yy, pa, pb, y.index[mm].normalize().to_numpy()) if m != best_bl else (0.0, 0.0, 0.0)
                        dts = y.index[mm].normalize()
                        nd = int(len(np.unique(dts)))
                        # 게이트일(체제 0)은 ML 계열 예측이 구조 기준으로 바뀌므로, 모델 자체의 행동을 담은 날짜 수를 따로 센다
                        nd_ng = int(len(np.unique(dts[cond["regime"].to_numpy()[mm] != 0])))
                        gate_eq = bool((cond["regime"].to_numpy()[mm] == 0).all()) and best_bl != "BL3_profile"
                        flag = ("게이트로 모델≡기준" if gate_eq else
                                (f"사례(게이트일 제외 {nd_ng}일)" if nd_ng < 5 and nd_ng < nd else ("5일 미만(사례)" if nd < 5 else "")))
                        rows.append(dict(task=task, model=m, baseline=best_bl, period=per, condition=col, value=str(val),
                                         availability=AVAILABILITY.get(col, ""), n=int(mm.sum()), flag=flag,
                                         days=nd, days_excl_gate=nd_ng,
                                         MAE=float(np.mean(np.abs(pa - yy))), RMSE=float(np.sqrt(np.mean((pa - yy) ** 2))),
                                         bias=float(np.mean(pa - yy)), skill_vs_baseline=sk, skill_ci90_lo=lo, skill_ci90_hi=hi))
    return pd.DataFrame(rows)


def inversion_days(iv: pd.DataFrame, cond: pd.DataFrame, selection: dict) -> pd.DataFrame:
    """시험에서 선택 모델보다 좋았던 모델과의 차이를 날짜로 분해(사후 설명용).

    B: 선택 모델 vs BL3 프로파일·LightGBM, A4: 선택 모델 vs 앙상블·LightGBM. 날짜별 제곱오차 차이(선택 − 비교)와 점유율,
    조건 표시, 차이가 큰 4일을 뺀 RMSE."""
    y = iv["y"]
    temask = _temask(iv)
    cday = cond.groupby(cond.index.normalize()).first()
    rows = []
    for task, fam, others in (("B", "B", ("BL3_profile", "M1_lgbm")), ("A4", "A", ("M8_blend", "M1_lgbm"))):
        pt = SM.load_predictions("test", task).reindex(y.index)
        ch = selection[fam]["chosen"]
        for other in others:
            if other == ch or other not in pt:
                continue
            m = pd.Series(temask, index=y.index) & pt[ch].notna() & pt[other].notna()
            ea = ((pt[ch] - y) ** 2).where(m)
            eb = ((pt[other] - y) ** 2).where(m)
            d = pd.DataFrame({"sse_chosen": ea.groupby(y.index.normalize()).sum(),
                              "sse_other": eb.groupby(y.index.normalize()).sum(),
                              "n": m.groupby(y.index.normalize()).sum()})
            d = d[d["n"] > 0]
            d["diff"] = d["sse_chosen"] - d["sse_other"]
            tot = d["diff"].sum()
            top = d["diff"].sort_values(ascending=False).head(4).index
            rest = d.drop(index=top)
            rm_ch = float(np.sqrt(rest["sse_chosen"].sum() / rest["n"].sum()))
            rm_ot = float(np.sqrt(rest["sse_other"].sum() / rest["n"].sum()))
            for dt in d["diff"].sort_values(ascending=False).head(8).index:
                cr = cday.loc[dt]
                rows.append(dict(task=task, chosen=ch, other=other, date=dt, diff_SSE=float(d.at[dt, "diff"]),
                                 share_of_total_diff=float(d.at[dt, "diff"] / tot) if tot else np.nan,
                                 in_top4=dt in top, daytype4=cr["daytype4"], regime=cr["regime"], regime_prev=cr["regime_prev"],
                                 holiday_work=cr["holiday_work"], calendar_operation_mismatch=cr["calendar_operation_mismatch"],
                                 analog_atypical=cr["analog_atypical"],
                                 rmse_chosen_excl_top4=rm_ch, rmse_other_excl_top4=rm_ot,
                                 rmse_chosen_all=float(np.sqrt(d["sse_chosen"].sum() / d["n"].sum())),
                                 rmse_other_all=float(np.sqrt(d["sse_other"].sum() / d["n"].sum()))))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 규칙 탐색(교차검증에서 찾고 시험에서 재현 확인)

def encode_conditions(cond: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=cond.index)
    for c in ["daytype4", "regime", "regime_prev", "work_dayshift", "holiday_work", "calendar_operation_mismatch",
              "analog_atypical", "first_day_after_off"]:
        X[c] = cond[c].astype(float)
    for w in sorted(cond["window"].unique()):
        if w != "steady":
            X[f"win_{w}"] = (cond["window"] == w).astype(float)
    X["temp_level"] = cond["temp_bin"].map({"<20": 0, "20-26": 1, "26-30": 2, "30+": 3}).astype(float)
    return X  # 결측(자료 첫날의 전날 체제 등)은 규칙 적합에서 뺀다(코드값 −1로 채우지 않음)


def _leaves(tree: DecisionTreeRegressor, names: list[str]) -> list[tuple[str, list]]:
    tr = tree.tree_
    out = []

    def walk(node, conds):
        if tr.feature[node] == _tree.TREE_UNDEFINED:
            out.append((" & ".join(f"{f} {op} {th:.2f}" for f, op, th in conds) or "(전체)", conds))
            return
        f, th = names[tr.feature[node]], tr.threshold[node]
        walk(tr.children_left[node], conds + [(f, "<=", th)])
        walk(tr.children_right[node], conds + [(f, ">", th)])

    walk(0, [])
    return out


def _apply(X: pd.DataFrame, conds: list) -> np.ndarray:
    m = np.ones(len(X), bool)
    for f, op, th in conds:
        m &= (X[f].to_numpy() <= th) if op == "<=" else (X[f].to_numpy() > th)
    return m


def _mean_ci(v: np.ndarray, days: np.ndarray, n_boot: int = 500) -> tuple[float, float, float]:
    if len(v) == 0:
        return np.nan, np.nan, np.nan
    d = pd.DataFrame({"d": days, "v": v}).groupby("d")["v"].agg(["sum", "size"])
    S, N = d["sum"].to_numpy(), d["size"].to_numpy()
    rng = np.random.default_rng(C.SEED)
    bs = [S[ix].sum() / N[ix].sum() for ix in (rng.integers(0, len(S), len(S)) for _ in range(n_boot))]
    return float(S.sum() / N.sum()), float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))


def error_rules(iv: pd.DataFrame, cond: pd.DataFrame, selection: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """목표 두 가지: (a) 최강 기준 대비 손실 |e_모델| − |e_기준|(양수 = 기준보다 나쁨), (b) 가동 주간 안의 |e_모델|.
    교차검증에서 깊이 2 트리(잎 ≥150)로 규칙을 찾고, 같은 규칙을 시험에 적용해 재현 여부를 본다(월은 쓰지 않음)."""
    y = iv["y"]
    cvm = pd.read_csv(C.OUTPUT_DIR / "cv" / "cv_metrics.csv")
    X = encode_conditions(cond)
    cvmask, temask = _cvmask(iv), _temask(iv)
    work = cond["work_dayshift"].to_numpy() == 1
    rows, stab = [], []
    for task in ("B", "A4"):
        fam = "A" if task.startswith("A") else "B"
        chosen = selection[fam]["chosen"]
        pooled = cvm[(cvm.task == task) & (cvm.split == "pooled")].set_index("model")["RMSE"]
        best_bl = pooled[[m for m in pooled.index if m.startswith("BL")]].idxmin()
        po = SM.load_predictions("oof", task).reindex(y.index)
        pt = SM.load_predictions("test", task).reindex(y.index)
        for target in ("loss_vs_baseline", "abs_err_workday"):
            def tgt(p, mask):
                m = mask & p[chosen].notna().to_numpy() & p[best_bl].notna().to_numpy() & X.notna().all(axis=1).to_numpy()
                if target == "abs_err_workday":
                    m &= work
                else:
                    m &= cond["regime"].to_numpy() != 0  # 계획 정지일은 게이트로 모델 ≡ 기준(손실 0)이라 뺀다
                e = np.abs(p[chosen].to_numpy() - y.to_numpy())
                v = e - np.abs(p[best_bl].to_numpy() - y.to_numpy()) if target == "loss_vs_baseline" else e
                return m, v
            mc, vc = tgt(po, cvmask)
            mt, vt = tgt(pt, temask)
            tree = DecisionTreeRegressor(max_depth=2, min_samples_leaf=150, random_state=C.SEED).fit(X[mc], vc[mc])
            daysc, dayst = y.index.normalize().to_numpy(), y.index.normalize().to_numpy()
            oc = _mean_ci(vc[mc], daysc[mc])
            ot = _mean_ci(vt[mt], dayst[mt])
            rows.append(dict(task=task, model=chosen, baseline=best_bl, target=target, rule="(전체)", direction="",
                             n_cv=int(mc.sum()), mean_cv=oc[0], ci_cv_lo=oc[1], ci_cv_hi=oc[2], n_test=int(mt.sum()),
                             mean_test=ot[0], ci_test_lo=ot[1], ci_test_hi=ot[2], reproduced=np.nan))
            for text, conds in _leaves(tree, list(X.columns)):
                lc = mc & _apply(X, conds)
                lt = mt & _apply(X, conds)
                a = _mean_ci(vc[lc], daysc[lc])
                b = _mean_ci(vt[lt], dayst[lt])
                # 재현 판정 — 기준 대비 손실: 교차검증과 시험의 부호가 같고 시험 90% 구간이 0을 포함하지 않음.
                # 가동 주간 오차: 교차검증 잎이 전체보다 크면(작으면) 시험 잎의 90% 구간이 시험 전체 평균보다 위(아래)
                rep = np.nan
                if lt.sum() >= 40 and np.isfinite(b[0]):
                    if target == "loss_vs_baseline":  # 교차검증·시험 모두 구간이 0을 배제하고 부호가 같음
                        rep = float(np.sign(a[0]) == np.sign(b[0]) and (a[1] > 0 or a[2] < 0) and (b[1] > 0 or b[2] < 0))
                    else:  # 교차검증·시험 모두 잎 구간이 각 기간 전체 평균을 같은 쪽으로 배제
                        up = a[0] > oc[0]
                        rep = float(((a[1] > oc[0]) and (b[1] > ot[0])) if up else ((a[2] < oc[0]) and (b[2] < ot[0])))
                # 잎의 방향(교차검증 기준): 손실은 양수 = 모델이 기준보다 나쁨, 가동 주간 오차는 전체 평균보다 큼/작음
                if target == "loss_vs_baseline":
                    direction = "모델 열위(기준보다 나쁨)" if a[0] > 0 else "모델 우위(기준보다 좋음)"
                else:
                    direction = "오차 큼(전체 대비)" if a[0] > oc[0] else "오차 작음(전체 대비)"
                rows.append(dict(task=task, model=chosen, baseline=best_bl, target=target, rule=text, direction=direction,
                                 n_cv=int(lc.sum()), mean_cv=a[0], ci_cv_lo=a[1], ci_cv_hi=a[2], n_test=int(lt.sum()),
                                 mean_test=b[0], ci_test_lo=b[1], ci_test_hi=b[2], reproduced=rep))
            # 안정성: 교차검증 날짜 부트스트랩에서 첫 분할 변수와 깊이 2 구조 전체의 재등장 비율
            root = X.columns[tree.tree_.feature[0]] if tree.tree_.feature[0] >= 0 else None
            struct = tuple(sorted(X.columns[f] for f in tree.tree_.feature if f >= 0))
            rng = np.random.default_rng(C.SEED)
            ud = np.unique(daysc[mc])
            hits_root, hits_struct = 0, 0
            for _ in range(100):
                pick = rng.choice(ud, len(ud), replace=True)
                ix = np.concatenate([np.where(mc & (daysc == d))[0] for d in pick])
                tb = DecisionTreeRegressor(max_depth=2, min_samples_leaf=150, random_state=C.SEED).fit(X.iloc[ix], vc[ix])
                r0 = X.columns[tb.tree_.feature[0]] if tb.tree_.feature[0] >= 0 else None
                hits_root += int(r0 == root)
                hits_struct += int(tuple(sorted(X.columns[f] for f in tb.tree_.feature if f >= 0)) == struct)
            stab.append(dict(task=task, target=target, root_feature=root, root_recurrence=hits_root / 100,
                             structure=" | ".join(struct), structure_recurrence=hits_struct / 100))
    return pd.DataFrame(rows), pd.DataFrame(stab)


# ---------------------------------------------------------------- 피크 조건(서술)

def _plateau(v: np.ndarray) -> float:
    s = np.r_[v[36:40], v[42:48], v[53:60]]  # 09:00~11:59, 13:15~14:59(10:00 휴식·점심 제외)
    return float(np.nanmean(s))


def peak_conditions(iv: pd.DataFrame, st: pd.DataFrame, T: float) -> tuple[dict, pd.DataFrame]:
    y = iv["y"]
    day = iv.index.normalize()
    full = st.index[(st["regime"] == 2) & (st["daytype3"] == 0)]
    ymat = y.to_numpy().reshape(-1, 96)
    dates = pd.DatetimeIndex(st.index)
    tmax = iv["temp"].groupby(day).max()
    rows = []
    for i, d in enumerate(dates):
        if d not in full or np.isfinite(ymat[i]).sum() < 90 or d < C.MEASURED_START:
            continue
        v = ymat[i]
        am = int(np.nanargmax(v))
        plateau = _plateau(v)
        startup = np.nanmax(v[30:36])
        rows.append(dict(date=d, month=d.month, period="test" if d >= C.TEST_START else "pre_test",
                         max_slot=am, daymax=float(np.nanmax(v)), plateau=float(plateau),
                         startup_peak=float(startup), startup_excess=C.startup_excess(v),
                         type="startup" if 30 <= am <= 35 else ("plateau" if 36 <= am <= 63 else "other"),
                         tmax=float(tmax.get(d, np.nan)), over_T=bool(np.nanmax(v) >= T),
                         monday_like=int(st["daytype4"].get(d) == 0), day_index=int((d - C.MEASURED_START).days)))
    dd = pd.DataFrame(rows)
    out = {"n_days": int(len(dd)), "n_days_by_month": dd.groupby("month").size().to_dict()}
    out["type_share_by_month"] = dd.groupby("month")["type"].value_counts(normalize=True).round(3).unstack().fillna(0).to_dict()
    out["startup_excess_by_month_median"] = dd.groupby("month")["startup_excess"].median().round(2).to_dict()
    groups = [g["startup_excess"].to_numpy() for _, g in dd.groupby("month") if len(g) >= 3]
    out["startup_excess_kruskal_p"] = float(stats.kruskal(*groups).pvalue) if len(groups) >= 2 else None
    # 고원 수준 vs 최고기온: 단순 기울기(부트스트랩), 날짜 추세·월요일 통제 회귀, Theil–Sen
    for label, sub, note in (("summer_pre_test", dd[(dd.month.isin([6, 7])) & (dd.period == "pre_test")], "6·7월(시험 전)"),
                             ("summer_test", dd[dd.period == "test"], "8·9월(시험)"),
                             ("pooled_jun_sep_posthoc", dd[dd.month.isin([6, 7, 8, 9])], "6~9월 합동(사후, 참고)")):
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
        Z = np.column_stack([x, sub["day_index"].to_numpy(), sub["monday_like"].to_numpy(), np.ones(len(sub))])
        beta, *_ = np.linalg.lstsq(Z, yv, rcond=None)
        bz = []
        for _ in range(1000):
            ix = rng.integers(0, len(sub), len(sub))
            if np.ptp(x[ix]) > 0:
                bz.append(np.linalg.lstsq(Z[ix], yv[ix], rcond=None)[0][0])
        ts = stats.theilslopes(yv, x, alpha=0.90)
        out[f"plateau_slope_per_C_{label}"] = {
            "note": note, "slope": slope, "ci90": [float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))],
            "n_days": int(len(sub)), "corr": float(np.corrcoef(x, yv)[0, 1]),
            "slope_controlling_trend_monday": float(beta[0]),
            "slope_controlling_ci90": [float(np.quantile(bz, 0.05)), float(np.quantile(bz, 0.95))],
            "theil_sen": float(ts.slope), "theil_sen_ci90": [float(ts.low_slope), float(ts.high_slope)],
            "tmax_date_corr": float(np.corrcoef(x, sub["day_index"].to_numpy())[0, 1])}
    # 최대피크 분해: 월 최대 날과 상위 10일의 유형(기동 과도분 vs 고원)
    mon = dd.loc[dd.groupby("month")["daymax"].idxmax(), ["month", "date", "daymax", "type", "plateau", "startup_excess", "tmax"]]
    out["month_max_days"] = [{k: (str(v) if k == "date" else v) for k, v in r.items()} for r in mon.to_dict("records")]
    for per in ("pre_test", "test"):
        top = dd[dd.period == per].nlargest(10, "daymax")
        out[f"top10_type_counts_{per}"] = top["type"].value_counts().to_dict()
    return out, dd


def peak_logit(iv: pd.DataFrame, st: pd.DataFrame, T: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """전면 가동일 08~16시 15분 구간의 T 이상 여부 로지스틱(기준 범주 13~16시, 날짜 군집 부트스트랩)과 조건부 비율표."""
    y = iv["y"]
    day = iv.index.normalize()
    hour = iv["hour"].to_numpy()
    reg = st["regime"].reindex(day).to_numpy()
    base = (reg == 2) & y.notna().to_numpy() & (hour >= 8) & (hour < 17)
    cdd = np.maximum(iv["temp"].to_numpy() - 24, 0)
    X = pd.DataFrame({
        "startup_0800_0859": (hour == 8).astype(float),
        "morning_0900_1159": ((hour >= 9) & (hour < 12)).astype(float),
        "lunch_1200_1259": (hour == 12).astype(float),
        "monday_like": (st["daytype4"].reindex(day).to_numpy() == 0).astype(float),
        "cdd24": cdd,
    }, index=iv.index)
    X["startup_x_cdd24"] = X["startup_0800_0859"] * cdd
    X["morning_x_cdd24"] = X["morning_0900_1159"] * cdd
    m = base & (iv.index < C.TEST_START) & (iv.index >= C.MEASURED_START)
    Xm, lab = X[m], (y[m] >= T).astype(int).to_numpy()
    days = day[m]
    fit = LogisticRegression(C=1.0, max_iter=4000).fit(Xm, lab)
    rng = np.random.default_rng(C.SEED)
    ud = np.unique(days)
    boots = []
    for _ in range(200):
        pick = rng.choice(ud, len(ud), replace=True)
        ix = np.concatenate([np.where(days == d)[0] for d in pick])
        if lab[ix].min() == lab[ix].max():
            continue
        boots.append(LogisticRegression(C=1.0, max_iter=4000).fit(Xm.iloc[ix], lab[ix]).coef_[0])
    B = np.array(boots)
    odds = pd.DataFrame({"feature": Xm.columns, "odds_ratio": np.exp(fit.coef_[0]),
                         "or_ci05": np.exp(np.quantile(B, 0.05, axis=0)), "or_ci95": np.exp(np.quantile(B, 0.95, axis=0)),
                         "reference": "13~16시, cdd24=0", "n": len(lab), "positives": int(lab.sum())})
    rows = []
    band = pd.cut(pd.Series(hour), [7, 8, 11, 12, 16], labels=["08", "09-11", "12", "13-16"]).astype(str).to_numpy()
    tb = pd.cut(iv["temp"], [-50, 20, 26, 30, 50], labels=["<20", "20-26", "26-30", "30+"]).astype(str).to_numpy()
    for per, pm in (("pre_test", base & (iv.index < C.TEST_START)), ("test", base & (iv.index >= C.TEST_START))):
        d = pd.DataFrame({"band": band[pm], "temp": tb[pm], "peak": (y.to_numpy()[pm] >= T)})
        g = d.groupby(["band", "temp"])["peak"].agg(n="size", rate="mean").reset_index()
        g.insert(0, "period", per)
        rows.append(g)
    return odds, pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------- SHAP(LightGBM 기여도)

def _fit_shap(model, X_tr, y_tr, X_te, names_inner=None):
    model.fit(X_tr, y_tr)
    contrib = model.contrib(X_te)
    names = names_inner or model.features
    return names, np.abs(contrib[:, :-1]).mean(axis=0), model


def shap_importance(iv: pd.DataFrame, frames: dict, task: str, log=print) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """시험 시작 전 학습 가능 구간으로 적합해 시험 구간 기여도(평균 |SHAP|)를 계산한다.

    M1(LightGBM), M7c 하이브리드의 잔차 보정기(선택 모델의 ML 부분), 구조만 모델(지연·유사일 없이 달력·체제·기상,
    시각×기온 상호작용을 드러내기 위한 설명용)."""
    X = frames[task]
    fam = "A" if task.startswith("A") else "B"
    feats = F.feature_list(fam)
    tr = CV.train_mask(X.index, iv["trainable"].to_numpy(), C.TEST_START, fam)
    te = (X.index >= C.TEST_START) & iv["usable"].to_numpy()
    ytr = iv["y_train"][tr]
    rows = []
    inter = pd.DataFrame()
    dep = pd.DataFrame()
    struct_feats = F.CAL + F.SCHED + F.WEATHER
    models = (("M1_lgbm", M.LGBModel(feats, objective="huber", alpha=10.0)),
              ("M7c_hybrid_residual", M.Hybrid(feats, fam, monotone=R.COOL_MONO)),
              ("structure_only_lgbm", M.LGBModel(struct_feats, objective="huber", alpha=10.0)))
    for name, model in models:
        model.fit(X.loc[tr], ytr)
        contrib = model.contrib(X.loc[te])
        names = model.inner_.features if name.startswith("M7c") else model.features
        mean_abs = np.abs(contrib[:, :-1]).mean(axis=0)
        for f, v in zip(names, mean_abs):
            g = F.FEATURE_GLOSSARY.get(f, (f, "기타", ""))
            rows.append(dict(task=task, model=name, feature=f, feature_ko=g[0], group=g[1], availability=g[2],
                             mean_abs_shap=float(v)))
        if name in ("M1_lgbm", "structure_only_lgbm"):
            try:
                import shap
                inner = model.m_
                sample = X.loc[te, names].sample(n=min(400, int(te.sum())), random_state=C.SEED)
                iv_vals = shap.TreeExplainer(inner).shap_interaction_values(sample)
                A = np.abs(iv_vals).mean(axis=0)
                np.fill_diagonal(A, 0)
                pairs = sorted([(names[i], names[j], float(A[i, j] + A[j, i])) for i in range(len(names))
                                for j in range(i + 1, len(names))], key=lambda t: -t[2])
                t = pd.DataFrame(pairs, columns=["feature_1", "feature_2", "mean_abs_interaction"])
                t["rank"] = np.arange(1, len(t) + 1)
                t["n_pairs"] = len(t)
                wanted = {frozenset(x) for x in (("slot", "temp"), ("slot", "tmax_day"), ("hour", "temp"), ("hour", "cdd24"),
                                                 ("slot", "cdd24"), ("slot", "regime"), ("hour", "regime"), ("slot", "regime_prev"))}
                t["specified_pair"] = [frozenset((a, b)) in wanted for a, b in zip(t.feature_1, t.feature_2)]
                t = t[(t["rank"] <= 25) | t["specified_pair"]]
                t.insert(0, "model", name)
                t.insert(0, "task", task)
                inter = pd.concat([inter, t], ignore_index=True)
                if name == "structure_only_lgbm":
                    # 의존도: 기상 특징 SHAP 합을 시간대 × 기온 구간으로 평균(시각×기온 상호작용의 크기)
                    sv = shap.TreeExplainer(inner).shap_values(X.loc[te, names])
                    wx = [i for i, f in enumerate(names) if f in F.WEATHER]
                    s_wx = sv[:, wx].sum(axis=1)
                    hr = X.loc[te, "hour"].to_numpy()
                    tb = pd.cut(X.loc[te, "tmax_day"], [-50, 26, 28, 30, 32, 50], labels=["<26", "26-28", "28-30", "30-32", "32+"]).astype(str)
                    hb = pd.cut(pd.Series(hr), [-1, 6, 8, 11, 12, 16, 19, 23],
                                labels=["00-06", "07-08", "09-11", "12", "13-16", "17-19", "20-23"]).astype(str).to_numpy()
                    dep = pd.DataFrame({"hour_band": hb, "tmax_bin": tb.to_numpy(), "weather_shap": s_wx}).groupby(
                        ["hour_band", "tmax_bin"])["weather_shap"].agg(["mean", "size"]).reset_index()
                    dep.insert(0, "task", task)
            except Exception as e:  # shap 미설치 등
                log(f"  SHAP 상호작용 생략: {e}")
    imp = pd.DataFrame(rows).sort_values(["model", "mean_abs_shap"], ascending=[True, False])
    return imp, inter, dep


# ---------------------------------------------------------------- 피크 경보 FN/FP 집중 조건

def _rate_ci(num: np.ndarray, den: np.ndarray, days: np.ndarray, n_boot: int = 500) -> tuple[float, float, float]:
    d = pd.DataFrame({"d": days, "a": num, "b": den}).groupby("d").sum()
    A, B = d["a"].to_numpy(float), d["b"].to_numpy(float)
    if B.sum() == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(C.SEED)
    bs = []
    for _ in range(n_boot):
        ix = rng.integers(0, len(A), len(A))
        if B[ix].sum() > 0:
            bs.append(A[ix].sum() / B[ix].sum())
    return float(A.sum() / B.sum()), float(np.quantile(bs, 0.05)), float(np.quantile(bs, 0.95))


def alarm_error_conditions(iv: pd.DataFrame, st: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """다음 1시간 피크 경보(선택 확률 방법·F1 문턱)의 FN/FP를 목표 창 조건별로: 미탐률·오경보율(날짜 군집 90% 구간),
    FN 점유/양성 점유(lift), 같은 칸의 시각 규칙·기후값 확률 미탐률, 2원 표(시간대×월, 시간대×기온), 놓친 사건 목록."""
    pk = json.loads((C.OUTPUT_DIR / "peak" / "peak_summary.json").read_text(encoding="utf-8"))
    m = pk["prob_method"]["chosen"]
    tau = pk["tau"][m]["tau_f1"]
    tau_clim = pk["tau"].get("P_climatology", {}).get("tau_f1", 0.5)
    pr = pd.read_csv(C.ARTIFACT_DIR / "next_hour_prob.csv.gz", index_col=0, parse_dates=True).reindex(iv.index)
    ok = pr["common"].fillna(False).astype(bool).to_numpy()
    lab = pr["label"].to_numpy() == 1
    alarm = pr[m].to_numpy() >= tau
    alarm_clock = pr["R_clock"].to_numpy() >= 0.5
    alarm_clim = pr["P_climatology"].to_numpy() >= tau_clim
    idx = iv.index
    tgt = idx + pd.Timedelta(minutes=15)
    day = tgt.normalize()
    cond = pd.DataFrame(index=idx)
    cond["target_hour_band"] = pd.cut(tgt.hour, [-1, 6, 7, 8, 11, 12, 15, 19, 23],
                                      labels=["00-06", "07", "08", "09-11", "12", "13-15", "16-19", "20-23"]).astype(str)
    cond["daytype4"] = st["daytype4"].reindex(day).to_numpy()
    cond["regime_prev"] = st["regime_prev"].reindex(day).to_numpy()
    cond["temp_bin"] = pd.cut(iv["temp"].shift(-1), [-50, 20, 26, 30, 50], labels=["<20", "20-26", "26-30", "30+"]).astype(str)
    cond["month"] = tgt.month
    cond["now_above_T"] = (iv["y"].to_numpy() >= pr["T"].to_numpy()).astype(int)
    # 운영 창(다음 1시간의 첫 목표 구간 기준, 전면 가동일): 기동·휴식 복귀·점심·점심 복귀·주간조 종료
    slot = np.asarray(tgt.hour * 4 + tgt.minute // 15)
    reg_t = st["regime"].reindex(day).to_numpy()
    cond["operating_window"] = np.select(
        [reg_t != 2, (slot >= 30) & (slot <= 35), np.isin(slot, [40, 41, 60, 61]), (slot >= 48) & (slot <= 51),
         (slot >= 52) & (slot <= 53), (slot >= 68) & (slot <= 71), (slot >= 36) & (slot <= 79)],
        ["부분 가동·정지일", "기동 07:30~08:59", "휴식·복귀 10:00~10:29·15:00~15:29", "점심 12:00~12:59",
         "점심 복귀 13:00~13:29", "주간조 종료 17:00~17:59", "그 밖의 주간 09~19시"], default="야간·새벽")
    # 확률 예측의 여유: 놓친 피크의 초과폭(실제 최대 − T), 오경보의 부족폭(T − 실제 최대)
    ymax = pd.concat([iv["y"].shift(-k) for k in range(1, 5)], axis=1).max(axis=1).to_numpy()
    margin = ymax - pr["T"].to_numpy()
    rows, two, missed = [], [], []
    days = idx.normalize().to_numpy()
    for per, (s0, e0) in {"cv": (C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2]), "test": (C.TEST_START, C.TEST_END)}.items():
        pm = ok & (idx >= s0) & (idx < e0)
        tot_fn, tot_pos = int((pm & lab & ~alarm).sum()), int((pm & lab).sum())
        tot_fp = int((pm & ~lab & alarm).sum())
        for col in cond.columns:
            for val, ix in cond[pm].groupby(col).groups.items():
                mm = np.zeros(len(idx), bool)
                mm[idx.get_indexer(ix)] = True
                pos = int((mm & lab).sum())
                fn, fp = int((mm & lab & ~alarm).sum()), int((mm & ~lab & alarm).sum())
                mr = _rate_ci((mm & lab & ~alarm)[mm], (mm & lab)[mm], days[mm])
                far = _rate_ci((mm & ~lab & alarm)[mm], (mm & ~lab)[mm], days[mm])
                rows.append(dict(period=per, condition=col, value=str(val), n=int(mm.sum()), positives=pos, FN=fn, FP=fp,
                                 miss_rate=mr[0], miss_ci90_lo=mr[1], miss_ci90_hi=mr[2],
                                 false_alarm_rate=far[0], fa_ci90_lo=far[1], fa_ci90_hi=far[2],
                                 share_of_all_FN=fn / tot_fn if tot_fn else np.nan,
                                 share_of_all_FP=fp / tot_fp if tot_fp else np.nan,
                                 FN_lift=(fn / tot_fn) / (pos / tot_pos) if tot_fn and pos else np.nan,
                                 miss_rate_clock=float((mm & lab & ~alarm_clock).sum() / pos) if pos else np.nan,
                                 miss_rate_climatology=float((mm & lab & ~alarm_clim).sum() / pos) if pos else np.nan))
        for c2 in ("month", "temp_bin"):
            g = pd.DataFrame({"band": cond["target_hour_band"][pm], c2: cond[c2][pm], "pos": lab[pm],
                              "fn": (lab & ~alarm)[pm], "fp": (~lab & alarm)[pm]}).groupby(["band", c2]).sum().reset_index()
            g["miss_rate"] = g["fn"] / g["pos"].replace(0, np.nan)
            g.insert(0, "table", f"hour_band_x_{c2}")
            g.insert(0, "period", per)
            two.append(g.rename(columns={c2: "second"}))
        fnm = pm & lab & ~alarm
        fpm = pm & ~lab & alarm
        rows.append(dict(period=per, condition="margin", value="FN: 실제 최대 − T < 5", n=int(fnm.sum()),
                         miss_rate=float(np.mean(margin[fnm] < 5)) if fnm.any() else np.nan))
        rows.append(dict(period=per, condition="margin", value="FP: T − 실제 최대 < 5", n=int(fpm.sum()),
                         false_alarm_rate=float(np.mean(-margin[fpm] < 5)) if fpm.any() else np.nan))
    # 놓친 사건(시험): 사건 시작 전 1시간 발행 중 경보가 한 번도 없던 사건
    from . import peak as PK
    T_test = CV.peak_threshold(iv, C.TEST_START)
    ev = PK.events(iv["y"], iv["usable"].to_numpy(), T_test)
    for _, e in ev.iterrows():
        s = int(e["start"])
        if idx[s] < C.TEST_START or s < 4:
            continue
        cand = np.arange(s - 4, s)
        if not ok[cand].any():
            continue
        missed.append(dict(start=idx[s], n=int(e["n"]), peak=float(e["peak"]), detected_model=bool(alarm[cand].any()),
                           detected_clock=bool(alarm_clock[cand].any()), detected_climatology=bool(alarm_clim[cand].any()),
                           max_prob_before=float(np.nanmax(pr[m].to_numpy()[cand])), hour=int(idx[s].hour),
                           temp=float(iv["temp"].iloc[s])))
    return pd.DataFrame(rows), pd.concat(two, ignore_index=True), pd.DataFrame(missed)


def dayahead_slot_errors(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """익일 슬롯 피크 확률(CV F1 문턱)의 미탐을 시간대·월·기온으로 분해."""
    p = C.ARTIFACT_DIR / "dayahead_slot_prob.csv.gz"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p, parse_dates=["ts"])
    cv = d[d.period == "cv"]
    tau, _ = MT.best_f1_threshold(cv["label"].to_numpy(), cv["p"].to_numpy())
    d["alarm"] = d["p"] >= tau
    d["hour_band"] = pd.cut(d["ts"].dt.hour, [-1, 7, 8, 11, 12, 16, 19, 23],
                            labels=["00-07", "08", "09-11", "12", "13-16", "17-19", "20-23"]).astype(str)
    d["month"] = d["ts"].dt.month
    temp = iv["temp"].reindex(pd.DatetimeIndex(d["ts"])).to_numpy()
    d["temp_bin"] = pd.cut(pd.Series(temp), [-50, 20, 26, 30, 50], labels=["<20", "20-26", "26-30", "30+"]).astype(str).to_numpy()
    rows = []
    for per, g0 in d.groupby("period"):
        for col in ("hour_band", "month", "temp_bin", "rule"):
            for val, g in g0.groupby(col):
                pos = int(g["label"].sum())
                rows.append(dict(period=per, tau=tau, condition=col, value=str(val), n=len(g), positives=pos,
                                 FN=int((g["label"].astype(bool) & ~g["alarm"]).sum()),
                                 miss_rate=float((g["label"].astype(bool) & ~g["alarm"]).sum() / pos) if pos else np.nan,
                                 FP=int((~g["label"].astype(bool) & g["alarm"]).sum())))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 주 실행

def run(iv: pd.DataFrame, frames: dict, selection: dict, df: pd.DataFrame | None = None, diag=None,
        log=print) -> dict:
    miss = [r for r in ("cv/cv_metrics.csv", "peak/peak_summary.json") if not (C.OUTPUT_DIR / r).exists()]
    miss += [f"artifacts/{f}" for f in [f"{n}_{t}.csv.gz" for n in ("oof", "test") for t in TASKS]
             + ["next_hour_prob.csv.gz", "dayahead_slot_prob.csv.gz"] if not (C.ARTIFACT_DIR / f).exists()]
    if miss:
        raise FileNotFoundError(f"analysis 단계 선행 산출물이 없다: {miss} — models·peak를 먼저 실행한다")
    od = io.out_dir("analysis")
    y = iv["y"]
    st = F.schedule_table(iv)
    cond = condition_table(iv, st)
    temask = _temask(iv)
    summary = {"availability": AVAILABILITY}
    # 1) 조건별 성능(모든 모델, 시험) + 기술점수 + 부트스트랩
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
        others = [best_bl, naive, "M1_lgbm"] + (["BL3_profile"] if fam == "B" else ["M6_analog_level"])
        for other in dict.fromkeys(others):
            if other == chosen or other not in preds:
                continue
            for stat in ("RMSE", "MAE") + (("daymax_MAE",) if task == "B" else ()):
                for bd in (1, 7):
                    b = MT.paired_day_bootstrap(y, preds[chosen], preds[other], temask, stat=stat, block_days=bd)
                    boot_rows.append(dict(task=task, chosen=chosen, vs=other, block_days=bd, **b))
    io.write_csv(pd.concat(rows, ignore_index=True), od / "test_by_condition.csv")
    io.write_csv(pd.DataFrame(skill_rows), od / "test_skill.csv")
    io.write_csv(pd.DataFrame(boot_rows).assign(ci90=lambda d: d["ci90"].astype(str)), od / "test_bootstrap.csv")
    # 선택 모델의 시험 일별 오차 기여(상위 날짜)와 달력–가동 불일치 사례
    day_rows = []
    for task in ("B", "A4"):
        fam = "A" if task.startswith("A") else "B"
        pt = SM.load_predictions("test", task).reindex(y.index)
        ch = selection[fam]["chosen"]
        e2 = ((pt[ch] - y) ** 2).where(pd.Series(temask, index=y.index))
        g = e2.groupby(y.index.normalize()).agg(["sum", "count"])
        g = g[g["count"] > 0]
        g["share_of_SSE"] = g["sum"] / g["sum"].sum()
        g["day_RMSE"] = np.sqrt(g["sum"] / g["count"])
        g = g.sort_values("sum", ascending=False).head(10).reset_index().rename(columns={"index": "date", "ts": "date"})
        cday = cond.groupby(cond.index.normalize()).first()
        for r in g.itertuples():
            cr = cday.loc[r.date]
            day_rows.append(dict(task=task, model=ch, date=r.date, day_RMSE=r.day_RMSE, share_of_SSE=r.share_of_SSE,
                                 daytype4=cr["daytype4"], regime=cr["regime"], regime_prev=cr["regime_prev"],
                                 holiday_work=cr["holiday_work"], calendar_operation_mismatch=cr["calendar_operation_mismatch"],
                                 analog_atypical=cr["analog_atypical"]))
    io.write_csv(pd.DataFrame(day_rows), od / "test_top_error_days.csv")
    io.write_csv(inversion_days(iv, cond, selection), od / "test_inversion_days.csv")

    # 2) 조건 × 모델 기술점수(교차검증·시험, 90% 구간)
    io.write_csv(condition_skill(iv, cond, selection), od / "condition_skill.csv")

    # 3) 오차 조건 규칙(교차검증에서 찾고 시험에서 재현 확인)
    rules, stab = error_rules(iv, cond, selection)
    io.write_csv(rules, od / "error_rules.csv")
    io.write_csv(stab, od / "error_rule_stability.csv")

    # 4) SHAP
    imps, inters, deps = [], [], []
    for task in ("B", "A4"):
        imp, inter, dep = shap_importance(iv, frames, task, log=log)
        imps.append(imp)
        inters.append(inter)
        deps.append(dep)
    imp = pd.concat(imps, ignore_index=True)
    io.write_csv(imp, od / "shap_importance.csv")
    grp = imp.groupby(["task", "model", "group"])["mean_abs_shap"].sum().reset_index()
    grp["share"] = grp["mean_abs_shap"] / grp.groupby(["task", "model"])["mean_abs_shap"].transform("sum")
    io.write_csv(grp.sort_values(["task", "model", "share"], ascending=[True, True, False]), od / "shap_grouped.csv")
    io.write_csv(pd.concat(inters, ignore_index=True), od / "shap_interactions.csv")
    io.write_csv(pd.concat(deps, ignore_index=True), od / "shap_weather_dependence.csv")

    # 5) 피크 조건(서술) + 로지스틱 + 조건부 비율
    T = CV.peak_threshold(iv, C.TEST_START)
    pc_sum, pc_days = peak_conditions(iv, st, T)
    io.write_csv(pc_days, od / "peak_days.csv")
    io.write_json(pc_sum, od / "peak_conditions.json")
    odds, rates = peak_logit(iv, st, T)
    io.write_csv(odds, od / "peak_logit_odds.csv")
    io.write_csv(rates, od / "peak_conditional_rates.csv")
    if (C.ARTIFACT_DIR / "next_hour_prob.csv.gz").exists():
        a, b, c = alarm_error_conditions(iv, st)
        io.write_csv(a, od / "peak_alarm_error_conditions.csv")
        io.write_csv(b, od / "peak_alarm_error_2way.csv")
        io.write_csv(c, od / "peak_events_test_detection.csv")
    io.write_csv(dayahead_slot_errors(iv, st), od / "dayahead_slot_error_conditions.csv")
    summary["peak_conditions"] = pc_sum
    io.write_json(summary, od / "analysis_summary.json")
    return summary


# ---------------------------------------------------------------- 계획 정보가치·절제(재학습이 많아 별도 단계)

REGIME_ERROR_SEEDS = 10


def regime_error_summary(t: pd.DataFrame) -> pd.DataFrame:
    """체제 오류 반복의 요약: 오류율별 교차검증·시험 RMSE 평균[최소, 최대]와 헤드라인(오류 없음) 대비 평균 증가."""
    e = t[t["level"].str.startswith("L1a_regime_error")].copy()
    if e.empty:
        return pd.DataFrame()
    e["error_rate"] = e["level"].str.extract(r"error(\d+)")[0].astype(int) / 100
    base = t[t["level"] == "L1a_day_regime(headline)"].set_index(["task", "model"])
    rows = []
    for (task, model, err), g in e.groupby(["task", "model", "error_rate"]):
        b = base.loc[(task, model)] if (task, model) in base.index else None
        row = dict(task=task, model=model, error_rate=err, n_seeds=len(g))
        for col in ("cv_RMSE", "test_RMSE"):
            row.update({f"{col}_mean": g[col].mean(), f"{col}_min": g[col].min(), f"{col}_max": g[col].max(),
                        f"{col}_increase_vs_headline": g[col].mean() - b[col] if b is not None else np.nan})
        rows.append(row)
    return pd.DataFrame(rows)


def info_value(iv: pd.DataFrame, selection: dict, log=print) -> pd.DataFrame:
    """계획 정보 수준별 성능(교차검증 pooled·시험): M1(LightGBM)과 M7c(하이브리드, 선택 모델의 ML 부분).

    L0 달력만 / L1a 날짜 가동 체제(헤드라인) / L1b + 일 계획 세부(총량·첫/마지막 가동 시각) / L2 + 시간별 가동 여부
    / L3 + 시간별 생산 수량(오라클) / L1a_err: 계획 체제가 날짜의 5·10·20%에서 틀릴 때(모든 기간 같은 오류율, 난수 10개 —
    어느 날이 뒤집히는지에 따라 편차가 커서 평균[최소, 최대]로 요약한다)."""
    y = iv["y"]
    cvmask, temask = _cvmask(iv), _temask(iv)
    fr_or = CV.build_frames(iv, oracle=True, tasks=("B", "A4"))
    rows = []
    for task in ("B", "A4"):
        fam = "A" if task.startswith("A") else "B"
        levels = {
            "L0_calendar_only": (F.feature_list(fam, schedule_on=False), None),
            "L1a_day_regime(headline)": (F.feature_list(fam), None),
            "L1b_plus_day_plan_detail": (F.feature_list(fam, day_plan=True), None),
            "L2_plus_hourly_onoff": (F.feature_list(fam, hourly_onoff=True), None),
            "L3_plus_hourly_quantity_oracle": (F.feature_list(fam, oracle=True), None),
        }
        for err in (0.05, 0.10, 0.20):
            for sd in range(REGIME_ERROR_SEEDS):
                levels[f"L1a_regime_error{int(err * 100):02d}_seed{sd}"] = (F.feature_list(fam), (err, C.SEED + sd))
        for lvl, (feats, err) in levels.items():
            Xv = fr_or[task] if err is None else CV.build_frames(iv, regime_noise=err, tasks=(task,))[task]
            for mname in ("M1_lgbm", "M7c_hybrid_coolmono"):
                if lvl == "L0_calendar_only" and mname.startswith("M7"):
                    continue  # 하이브리드 기준(유사일)은 일정 정보를 쓰므로 L0에 없음
                if err is not None and not ((task == "B" and mname == "M1_lgbm") or (task == "A4" and mname.startswith("M7c"))):
                    continue  # 체제 오류 반복은 B LightGBM·A4 하이브리드만(실행 시간)
                if task == "A4" and mname == "M1_lgbm" and lvl == "L2_plus_hourly_onoff":
                    continue
                # L0(달력만)은 게이트 없이: 게이트가 체제로 정지일을 가려 달력만 수준에 체제 정보를 넣지 않게 한다
                fac = build_model(mname, fam, feats, selection, gate=lvl != "L0_calendar_only")
                t0 = time.time()
                pc = CV.run_cv(Xv, iv, fac, fam)
                pt = CV.run_test(Xv, iv, fac, fam)
                rc = MT.regression(y[cvmask], pc[cvmask])
                rt = MT.regression(y[temask], pt[temask])
                flips = ""
                if err is not None:
                    st0 = F.schedule_table(iv)
                    st1 = F.perturb_regime(st0, *err)
                    ch = (st0["regime"] != st1["regime"]) & st0["regime"].notna()
                    te_days = ch[(ch.index >= C.TEST_START) & (ch.index < C.TEST_END)]
                    flips = "; ".join(f"{int(a)}→{int(b)}:{n}" for (a, b), n in
                                      pd.DataFrame({"a": st0["regime"][te_days[te_days].index],
                                                    "b": st1["regime"][te_days[te_days].index]}).value_counts().items())
                rows.append(dict(task=task, level=lvl, model=mname, cv_RMSE=rc["RMSE"], cv_MAE=rc["MAE"],
                                 test_RMSE=rt["RMSE"], test_MAE=rt["MAE"], test_regime_flips=flips))
                log(f"  info {task} {lvl} {mname} {time.time() - t0:.0f}s")
    return pd.DataFrame(rows)


def weather_noise(iv: pd.DataFrame, selection: dict, log=print) -> pd.DataFrame:
    """기상 예보오차 민감도: 기온에 날짜별 편향 + 시간별 잡음(σ, σ/2)을 넣어 학습·예측 모두 예보 대리로 사용."""
    y = iv["y"]
    cvmask, temask = _cvmask(iv), _temask(iv)
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
        fr = CV.build_frames(ivn, tasks=("B", "A4"))
        for task, fam in (("B", "B"), ("A4", "A")):
            feats = F.feature_list(fam)
            chosen = selection[fam]["chosen"]
            for mname in dict.fromkeys([chosen, "M1_lgbm"]):
                fac = build_model(mname, fam, feats, selection)
                pc = CV.run_cv(fr[task], ivn, fac, fam)
                pt = CV.run_test(fr[task], ivn, fac, fam)
                rows.append(dict(sigma_C=sigma, task=task, model=mname,
                                 cv_RMSE=MT.regression(y[cvmask], pc[cvmask])["RMSE"],
                                 test_RMSE=MT.regression(y[temask], pt[temask])["RMSE"]))
                log(f"  weather-noise {sigma} {task} {mname}")
    return pd.DataFrame(rows)


def ablations(iv: pd.DataFrame, df: pd.DataFrame, diag, selection: dict, log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """절제: 기상 제외, 발행 24:00, 복제 포함 학습, 요일유형3·전날 체제 제외, 유사일 키에 전날 체제 추가(사후 민감도).

    각 행은 교차검증 pooled·시험 RMSE와, 헤드라인 설정 대비 시험 RMSE 차이의 날짜 부트스트랩 90% 구간."""
    y = iv["y"]
    cvmask, temask = _cvmask(iv), _temask(iv)
    rows, contrib = [], []
    frames = CV.build_frames(iv, tasks=("B", "A4"))
    base_pred = {}

    def headline(task, mname):
        key = (task, mname)
        if key not in base_pred:
            fam = "A" if task.startswith("A") else "B"
            src = SM.load_predictions("test", task).reindex(y.index)
            if mname in src:
                base_pred[key] = src[mname]
            else:
                base_pred[key] = CV.run_test(frames[task], iv, build_model(mname, fam, F.feature_list(fam), selection), fam)
        return base_pred[key]

    def rec(name, task, mname, pc, pt, posthoc=False):
        rc = MT.regression(y[cvmask], pc[cvmask])
        rt = MT.regression(y[temask], pt[temask])
        b = MT.paired_day_bootstrap(y, pt, headline(task, mname), temask, stat="RMSE")
        rows.append(dict(ablation=name, task=task, model=mname, cv_RMSE=rc["RMSE"], cv_MAE=rc["MAE"], test_RMSE=rt["RMSE"],
                         test_MAE=rt["MAE"], test_diff_vs_headline=b["diff"], diff_ci90=str(b["ci90"]),
                         posthoc_sensitivity=posthoc))
        log(f"  ablation {name} {task} {mname}")
        return pt

    models = {"B": list(dict.fromkeys([selection["B"]["chosen"], "M1_lgbm", "BL5_regime_analog"])),
              "A4": list(dict.fromkeys([selection["A"]["chosen"], "M1_lgbm", "M6_analog_level"]))}
    # 기상 제외
    for task, fam in (("B", "B"), ("A4", "A")):
        feats = F.feature_list(fam, weather_on=False)
        for mname in models[task]:
            if mname.startswith("BL") or mname.startswith("M6"):
                continue
            fac = build_model(mname, fam, feats, selection)
            rec("no_weather", task, mname, CV.run_cv(frames[task], iv, fac, fam), CV.run_test(frames[task], iv, fac, fam))
    # 발행 시각 24:00 (B)
    fr24 = CV.build_frames(iv, issue_hour_b=24, tasks=("B",))
    for mname in models["B"]:
        fac = build_model(mname, "B", F.feature_list("B"), selection)
        rec("issue_2400", "B", mname, CV.run_cv(fr24["B"], iv, fac, "B"), CV.run_test(fr24["B"], iv, fac, "B"))
    # 복제 포함 학습(복제·부분 복제를 학습 정답과 유사일 풀에 넣음, 평가는 그대로)
    iv_c = D.build_intervals(df, diag, train_on_copies=True)
    fr_c = CV.build_frames(iv_c, tasks=("B", "A4"))
    for task, fam in (("B", "B"), ("A4", "A")):
        for mname in models[task]:
            fac = build_model(mname, fam, F.feature_list(fam), selection)
            pt = rec("train_on_copies", task, mname, CV.run_cv(fr_c[task], iv_c, fac, fam), CV.run_test(fr_c[task], iv_c, fac, fam))
            e_a = ((pt - y) ** 2).where(pd.Series(temask, index=y.index))
            e_b = ((headline(task, mname) - y) ** 2).where(pd.Series(temask, index=y.index))
            dd = (e_a - e_b).groupby(y.index.normalize()).sum()
            tot = dd.sum()
            for d, v in dd.sort_values(ascending=False).head(5).items():
                contrib.append(dict(ablation="train_on_copies", task=task, model=mname, date=d, delta_SSE=v,
                                    share_of_total_delta=v / tot if tot else np.nan))
    # 요일유형3 유사일 키 + 전날 체제·요일유형4 특징 제외(야간조 이월 지식의 기여)
    fr3 = CV.build_frames(iv, analog_key=("daytype3",), tasks=("B", "A4"))
    for task, fam in (("B", "B"), ("A4", "A")):
        feats = [c for c in F.feature_list(fam) if c not in ("daytype4", "regime_prev")]
        for mname in models[task]:
            fac = build_model(mname, fam, feats, selection)
            rec("daytype3_no_prev_regime", task, mname, CV.run_cv(fr3[task], iv, fac, fam), CV.run_test(fr3[task], iv, fac, fam))
    # 계획 정지 게이트 제외(게이트 공개용: 선택 모델·LightGBM·하이브리드의 게이트 전후, 가동 주간은 게이트와 무관)
    for task, fam in (("B", "B"), ("A4", "A")):
        gate_models = [m for m in models[task] if not (m.startswith("BL") or m.startswith("M6"))]
        for mname in dict.fromkeys(gate_models + ["M7c_hybrid_coolmono"]):
            fac = build_model(mname, fam, F.feature_list(fam), selection, gate=False)
            pt = rec("no_plan_stop_gate", task, mname, CV.run_cv(frames[task], iv, fac, fam),
                     CV.run_test(frames[task], iv, fac, fam), posthoc=True)
    # 유사일 키에 전날 체제 추가(시험 오류 분석에서 나온 사후 민감도, 헤드라인 불변)
    frp = CV.build_frames(iv, analog_key=("daytype4", "regime_prev"), tasks=("B", "A4"))
    for task, fam in (("B", "B"), ("A4", "A")):
        for mname in models[task]:
            fac = build_model(mname, fam, F.feature_list(fam), selection)
            rec("analog_key_plus_prev_regime", task, mname, CV.run_cv(frp[task], iv, fac, fam),
                CV.run_test(frp[task], iv, fac, fam), posthoc=True)
    return pd.DataFrame(rows), pd.DataFrame(contrib)


def structural_retuned(iv: pd.DataFrame, selection: dict, log=print) -> tuple[pd.DataFrame, dict]:
    """사후 민감도(헤드라인 불변): 구조 기준의 초모수(B 유사일 k=2, A 수준 보정 ρ=0.9)는 v1(옛 복제 방향·옛 폴드)에서 고정했고
    현재 폴드에서 다시 고르지 않았다. 현재 폴드 교차검증 최선값(cv/structural_sweep.csv)으로 바꾼 기준모델(BL5·M6)과 선택 모델의
    차이(교차검증·시험, 날짜 짝 부트스트랩 90%)와, 그 기준을 후보에 넣고 선택 규칙을 다시 적용했을 때의 선택을 기록한다."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    cvmask, temask = _cvmask(iv), _temask(iv)
    sw = pd.read_csv(C.OUTPUT_DIR / "cv" / "structural_sweep.csv")
    k_best = int(sw[sw.param == "k"].sort_values("RMSE").iloc[0]["value"])
    rho_best = float(sw[sw.param == "rho"].sort_values("RMSE").iloc[0]["value"])
    st = F.schedule_table(iv)
    cvm = pd.read_csv(C.OUTPUT_DIR / "cv" / "cv_metrics.csv")
    blocks = CV.cv_blocks() + [("pooled", C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2])]
    work = SM.work_dayshift(iv)
    xmid = F.dayahead_features(iv, st, issue_hour=24)
    spec = {"B": (["B"], "BL5_regime_analog", "k", 2, k_best,
                  {"B": F.dayahead_features(iv, st, issue_hour=17, analog_k=k_best)}, lambda: M.AnalogDay("analog_regime")),
            "A": (["A1", "A2", "A3", "A4"], "M6_analog_level", "rho", 0.9, rho_best,
                  {f"A{h}": F.intraday_features(iv, h, xmid) for h in range(1, 5)}, lambda: M.AnalogLevel(rho_best))}
    rows, out = [], {"k_best": k_best, "rho_best": rho_best,
                     "note": "사후 민감도. 헤드라인 k=2·ρ=0.9는 v1에서 고정했고 현재 폴드에서 다시 고르지 않았다. 채택하지 않는다"}
    for fam, (tasks, base, param, v_head, v_best, frames, fac) in spec.items():
        chosen = selection[fam]["chosen"]
        oof = {t: SM.load_predictions("oof", t).reindex(y.index) for t in tasks}
        tst = {t: SM.load_predictions("test", t).reindex(y.index) for t in tasks}
        new_rows = []
        pc, pt = {}, {}
        for t in tasks:
            pc[t] = CV.run_cv(frames[t], iv, fac, fam)
            pt[t] = CV.run_test(frames[t], iv, fac, fam)
            SM._scores(y, pc[t], usable, iv, new_rows, t, base, blocks, work=work)
        for label, v, c_pred, t_pred in (("headline", v_head, {t: oof[t][base] for t in tasks}, {t: tst[t][base] for t in tasks}),
                                         ("retuned", v_best, pc, pt)):
            if len(tasks) == 1:
                bc = MT.paired_day_bootstrap(y, oof[tasks[0]][chosen], c_pred[tasks[0]], cvmask)
                bt = MT.paired_day_bootstrap(y, tst[tasks[0]][chosen], t_pred[tasks[0]], temask)
            else:
                bc = MT.multi_bootstrap_rmse(y, [oof[t][chosen] for t in tasks], [c_pred[t] for t in tasks], cvmask)
                bt = MT.multi_bootstrap_rmse(y, [tst[t][chosen] for t in tasks], [t_pred[t] for t in tasks], temask)
            rows.append(dict(family=fam, baseline=base, param=param, value=v, setting=label, chosen=chosen,
                             cv_RMSE=float(np.mean([MT.regression(y[cvmask], c_pred[t][cvmask])["RMSE"] for t in tasks])),
                             test_RMSE=float(np.mean([MT.regression(y[temask], t_pred[t][temask])["RMSE"] for t in tasks])),
                             chosen_minus_baseline_cv=bc["diff"], cv_ci90=str(bc["ci90"]),
                             chosen_minus_baseline_test=bt["diff"], test_ci90=str(bt["ci90"]), posthoc_sensitivity=True))
        # 선택 규칙 재적용: 기준모델 한 줄만 재조정 값으로 바꾼 교차검증 표·OOF
        cvm2 = pd.concat([cvm[~((cvm.task.isin(tasks)) & (cvm.model == base))], pd.DataFrame(new_rows)], ignore_index=True)
        oof2 = {t: oof[t].assign(**{base: pc[t]}) for t in tasks}
        s2 = SM.select(cvm2, oof2, iv, tasks)
        out[fam] = {"baseline": base, param: v_best, "rule_choice_with_retuned_baseline": s2["chosen"],
                    "headline_choice": chosen, "trail": s2["trail"]}
        log(f"  structural-retuned {fam} {base} {param}={v_best} → 규칙 선택 {s2['chosen']}")
    return pd.DataFrame(rows), out


NAIVE_FOLDS = [("V1_Apr", pd.Timestamp("2021-04-01"), pd.Timestamp("2021-05-01")),
               ("V2_May", pd.Timestamp("2021-05-01"), pd.Timestamp("2021-06-01")),
               ("V3_Jul", pd.Timestamp("2021-07-01"), pd.Timestamp("2021-08-01"))]
NAIVE_CANDIDATES = {"B": ["BL2_same_daytype", "BL3_profile", "BL5_regime_analog", "M9l_analog_level_adj", "M1_lgbm",
                          "M7c_hybrid_coolmono"],
                    "A": ["BL1_persistence", "BL6_analog_persist", "M6_analog_level", "M1_lgbm", "M7c_hybrid_coolmono"]}


def naive_protocol(df: pd.DataFrame, diag, selection: dict, log=print) -> pd.DataFrame:
    """반사실: 복제를 모르는 흔한 절차(손상·정전만 제외, 1~7월 원자료로 4·5·7월 폴드)에 같은 선택 규칙을 적용하면
    어떤 모델이 뽑히고, 교차검증 점수와 시험 점수가 어떻게 다른가. 시험 구간(8~9월)은 두 절차 모두 같은 정답이다."""
    iv_n = D.build_intervals(df, diag, naive=True)
    saved = C.CV_FOLDS
    rows = []
    try:
        C.CV_FOLDS = NAIVE_FOLDS
        frames = CV.build_frames(iv_n)
        cvm, oof = SM.run_cv_all(iv_n, frames, log=log, candidates=NAIVE_CANDIDATES)
        for fam, tasks in (("B", ["B"]), ("A", ["A1", "A2", "A3", "A4"])):
            s = SM.select(cvm, oof, iv_n, tasks)
            for mname in dict.fromkeys((s["chosen"], selection[fam]["chosen"])):
                if mname not in R.candidates(fam) and mname != "M8_blend":
                    continue
                cv_r, te_r = [], []
                for t in tasks:
                    fac = build_model(mname, fam, F.feature_list(fam), selection)
                    pt = CV.run_test(frames[t], iv_n, fac, fam)
                    te_r.append(MT.regression(iv_n["y"][_temask(iv_n)], pt[_temask(iv_n)])["RMSE"])
                    r = cvm[(cvm.task == t) & (cvm.split == "pooled") & (cvm.model == mname)]
                    cv_r.append(float(r["RMSE"].iloc[0]) if len(r) else np.nan)
                rows.append(dict(protocol="naive(복제 미인지)", family=fam, model=mname, chosen_by_protocol=mname == s["chosen"],
                                 cv_RMSE=float(np.mean(cv_r)), test_RMSE=float(np.mean(te_r))))
                log(f"  naive {fam} {mname}")
    finally:
        C.CV_FOLDS = saved
    cvm_h = pd.read_csv(C.OUTPUT_DIR / "cv" / "cv_metrics.csv")
    tm_h = pd.read_csv(C.OUTPUT_DIR / "test" / "test_metrics.csv")
    for fam, tasks in (("B", ["B"]), ("A", ["A1", "A2", "A3", "A4"])):
        ch = selection[fam]["chosen"]
        rows.append(dict(protocol="honest(헤드라인)", family=fam, model=ch, chosen_by_protocol=True,
                         cv_RMSE=float(cvm_h[(cvm_h.task.isin(tasks)) & (cvm_h.split == "pooled") & (cvm_h.model == ch)]["RMSE"].mean()),
                         test_RMSE=float(tm_h[(tm_h.task.isin(tasks)) & (tm_h.model == ch)]["RMSE"].mean())))
    return pd.DataFrame(rows)


def learning_curve(iv: pd.DataFrame, selection: dict, log=print) -> pd.DataFrame:
    """사후 설명용(시험 구간을 본 뒤 추가, 선택·설계에 쓰지 않음): 학습 창 길이(최근 N일)별 시험 성능."""
    y = iv["y"]
    temask = _temask(iv)
    frames = CV.build_frames(iv, tasks=("B", "A4"))
    rows = []
    for task in ("B", "A4"):
        fam = "A" if task.startswith("A") else "B"
        X = frames[task]
        feats = F.feature_list(fam)
        names = list(dict.fromkeys([selection[fam]["chosen"], "M1_lgbm", "M7c_hybrid_coolmono"]))
        for win in (30, 60, None):
            for mname in names:
                fac = build_model(mname, fam, feats, selection)
                pred = pd.Series(np.nan, index=X.index)
                for s0, e0 in CV.weekly_blocks(C.TEST_START, C.TEST_END):
                    tr = CV.train_mask(X.index, iv["trainable"].to_numpy(), s0, fam)
                    if win is not None:
                        tr &= X.index >= s0 - pd.Timedelta(days=win)
                    ev = (X.index >= s0) & (X.index < e0)
                    m = fac().fit(X.loc[tr], iv["y_train"][tr])
                    pred.loc[ev] = m.predict(X.loc[ev])
                r = MT.regression(y[temask], pred[temask])
                rows.append(dict(task=task, model=mname, train_window_days=win or "all", test_RMSE=r["RMSE"],
                                 test_MAE=r["MAE"]))
                log(f"  learning-curve {task} {mname} {win}")
    return pd.DataFrame(rows)


def run_heavy(iv: pd.DataFrame, df: pd.DataFrame, diag, selection: dict, log=print) -> None:
    """계획 정보가치·절제·반사실 절차·기상 예보오차·학습 창 곡선·LightGBM 격자(재학습이 많아 별도 단계)."""
    od = io.out_dir("analysis")
    io.write_csv(SM.ml_sweep(iv, CV.build_frames(iv, tasks=("B", "A4")), log=log), io.out_dir("cv") / "ml_sweep.csv")
    iv_t = info_value(iv, selection, log=log)
    io.write_csv(iv_t, od / "plan_information_value.csv")
    io.write_csv(regime_error_summary(iv_t), od / "plan_regime_error_summary.csv")
    ab, contrib = ablations(iv, df, diag, selection, log=log)
    io.write_csv(ab, od / "ablations.csv")
    io.write_csv(contrib, od / "ablation_copy_day_contrib.csv")
    sr, sr_sel = structural_retuned(iv, selection, log=log)
    io.write_csv(sr, od / "structural_retuned.csv")
    io.write_json(sr_sel, od / "structural_retuned_selection.json")
    io.write_csv(naive_protocol(df, diag, selection, log=log), od / "naive_protocol.csv")
    io.write_csv(weather_noise(iv, selection, log=log), od / "weather_forecast_error.csv")
    io.write_csv(learning_curve(iv, selection, log=log), od / "learning_curve.csv")
