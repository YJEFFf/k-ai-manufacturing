"""S7: 현장 활용 시뮬레이션(가정 기반, 실측 절감 아님).

1) 수요제어기: 다음 1시간 목표전력 초과확률 경보 → 제어 가능 부하 r을 30분 차단, 이후 30분에 지연 에너지 회복
2) 순차·선행 기동: 기동 과도분을 07:15~07:59로 분산
3) 여름 냉방: 최고기온 기울기(시험 전 추정)로 사전 냉방·설정온도 조정 시 가동 주간 부하 경감
4) 경보 등급표: 확률 구간별 실제 초과 빈도(교차검증·시험)와 조치
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config as C
from . import cv as CV
from . import features as F
from . import io
from . import peak as PK
from . import stage_peak as SP

TARGET_FRACTIONS = (0.88, 0.90, 0.92, 0.95)  # 시험 전 최대수요(요금 기준)의 비율로 목표전력을 정한다


def targets_from_pretest(iv: pd.DataFrame) -> tuple[float, ...]:
    """목표전력 = 시험 시작 전 학습 가능 구간의 최대 15분 수요 × 비율(시험 정보를 쓰지 않음)."""
    ref = float(iv.loc[iv.index < C.TEST_START, "y_train"].max())
    return tuple(round(ref * f, 1) for f in TARGET_FRACTIONS)
SHED = (0.05, 0.10, 0.15)
SHED_LEN = 2      # 한 번 차단은 최대 30분(2구간)
REBOUND_LEN = 4   # 지연 에너지는 이후 1시간(4구간)에 고르게 회복, 회복 중에는 재차단하지 않는다


def simulate(y: np.ndarray, alarm_issue: np.ndarray, r: float, valley: np.ndarray | None = None,
             search: int = 16) -> tuple[np.ndarray, dict]:
    """상태기계: 대기 → (발행 구간 i 경보) → i+1..i+SHED_LEN 차단(부하 r 감소) → 에너지 회복 → 대기.

    회복: valley(익일 예측상 저부하 구간 표시)가 주어지면 차단 뒤 search 구간(4시간) 안의 저부하 구간
    최대 REBOUND_LEN개에 고르게 더한다(생산 만회를 저부하 시간으로 미룸). 없거나 valley가 없으면
    바로 뒤 REBOUND_LEN 구간에 더한다(최악의 반동). 마지막 회복 구간 종료 시점의 경보부터 다시 받는다.
    """
    n = len(y)
    y2 = y.copy()
    ok = np.isfinite(y)
    i, episodes, shed_n, deferred, to_valley = 0, 0, 0, 0.0, 0
    ready_from = 0  # 이 발행 구간부터 새 경보를 받는다
    while i < n:
        if alarm_issue[i] and i >= ready_from:
            shed_idx = [t for t in range(i + 1, min(i + 1 + SHED_LEN, n)) if ok[t]]
            if shed_idx:
                e = float(np.sum(y[shed_idx]) * r)
                y2[shed_idx] = y2[shed_idx] - y[shed_idx] * r
                end = shed_idx[-1]
                rec = []
                if valley is not None:
                    rec = [t for t in range(end + 1, min(end + 1 + search, n)) if ok[t] and valley[t]][:REBOUND_LEN]
                    to_valley += int(bool(rec))
                if not rec:
                    rec = [t for t in range(end + 1, min(end + 1 + REBOUND_LEN, n)) if ok[t]]
                if rec:
                    y2[rec] += e / len(rec)
                episodes += 1
                shed_n += len(shed_idx)
                deferred += e
                ready_from = max(rec) if rec else end
                i = end
                continue
        i += 1
    return y2, {"episodes": episodes, "shed_intervals": shed_n, "deferred_energy": deferred,
                "payback_to_valley_share": to_valley / episodes if episodes else np.nan}


VALLEY_LEVEL = 140.0          # 익일 예측이 이 값 이하인 구간(점심·휴식·저녁)을 회복 구간으로 쓴다
TAU_CAND = (0.2, 0.3, 0.5, 0.7, 0.9)
PAYBACK = ("none", "valley", "immediate")


def _run_policy(yfill, al, r, payback, valley, m):
    if payback == "none":
        y2 = yfill.copy()
        n = len(y2)
        ok = np.isfinite(yfill)
        i, ep, shed_n, ready_from = 0, 0, 0, 0
        while i < n:
            if al[i] and i >= ready_from:
                idx = [t for t in range(i + 1, min(i + 1 + SHED_LEN, n)) if ok[t]]
                if idx:
                    y2[idx] = yfill[idx] * (1 - r)
                    ep += 1
                    shed_n += len(idx)
                    ready_from = idx[-1]   # 마지막 차단 구간 종료 시점의 경보로 이어서 차단할 수 있다
                    i = idx[-1]
                    continue
            i += 1
        info = {"episodes": ep, "shed_intervals": shed_n, "deferred_energy": float(np.nansum(yfill - y2)),
                "payback_to_valley_share": np.nan}
    else:
        y2, info = simulate(yfill.copy(), al, r, valley if payback == "valley" else None)
    return y2, info


def demand_controller(iv: pd.DataFrame, selection: dict, tau_default: float) -> tuple[pd.DataFrame, dict]:
    """목표전력 T별 수요제어 비교. 모델 정책의 τ는 7월(교차검증)에서 T마다 고르고 시험에 고정 적용한다."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    idx = iv.index
    st = F.schedule_table(iv)
    grp = PK.target_window_groups(PK.regime(iv, st["regime"]))
    mA = selection["A"]["chosen"]
    preds_h = {h: SP.honest_stream(f"A{h}", mA).reindex(idx) for h in range(1, 5)}
    predB = SP.honest_stream("B", selection["B"]["chosen"]).reindex(idx).to_numpy()
    TARGETS = targets_from_pretest(iv)
    valley = np.nan_to_num(predB, nan=np.inf) <= VALLEY_LEVEL
    yfill = np.where(usable, y.to_numpy(), np.nan)
    reg_day = st["regime"].reindex((idx + pd.Timedelta(minutes=15)).normalize()).to_numpy()
    nxt = idx + pd.Timedelta(minutes=15)
    periods = {"cv_jul": (pd.Timestamp("2021-07-01"), pd.Timestamp("2021-08-01")), "test": (C.TEST_START, C.TEST_END)}
    rows, chosen_tau = [], {}
    probs = {T: np.nan_to_num(PK.next_hour_prob(idx, preds_h, y, T, grp).to_numpy()) for T in TARGETS}

    def evaluate(per, T, pname, al, r, payback, tau):
        s0, e0 = periods[per]
        m = (idx >= s0) & (idx < e0)
        days = len(np.unique(idx[m].normalize()))
        y2, info = _run_policy(yfill, al & m, r, payback, valley, m)
        bm = pd.Series(yfill[m], index=idx[m]).groupby(idx[m].month).max()
        am = pd.Series(y2[m], index=idx[m]).groupby(idx[m].month).max()
        ob, oa = int(np.nansum(yfill[m] >= T)), int(np.nansum(y2[m] >= T))
        return dict(period=per, target=T, policy=pname, shed=r, payback=payback, tau=tau,
                    intervals_over_before=ob, intervals_over_after=oa,
                    over_reduction_share=(ob - oa) / ob if ob else np.nan,
                    month_max_before=json.dumps({int(k): float(v) for k, v in bm.items()}),
                    month_max_after=json.dumps({int(k): round(float(v), 2) for k, v in am.items()}),
                    max_month_max_change=float((am - bm).max()),
                    episodes_per_day=info["episodes"] / days, shed_intervals_per_day=info["shed_intervals"] / days,
                    deferred_energy_share=info["deferred_energy"] / float(np.nansum(yfill[m])),
                    payback_to_valley_share=info["payback_to_valley_share"])

    for T in TARGETS:
        rules = {
            "reactive_now>=T-5": np.nan_to_num(yfill) >= T - 5,
            "clock_0800_fullday": (reg_day == 2) & (nxt.hour == 8) & (nxt.minute == 0),
            "oracle_perfect": np.r_[(np.nan_to_num(yfill) >= T)[1:], False],
        }
        for r in SHED:
            for payback in PAYBACK:
                # 모델 정책 τ: 7월에서 초과 구간 감소율 최대(월 최대가 늘지 않는 τ 중), 없으면 가장 높은 τ
                cands = []
                for tau in TAU_CAND:
                    row = evaluate("cv_jul", T, "model_prob", probs[T] >= tau, r, payback, tau)
                    rows.append({**row, "tau_selection": "candidate"})
                    ok = row["max_month_max_change"] <= 0
                    cands.append((ok, row["over_reduction_share"] if np.isfinite(row["over_reduction_share"]) else -9, -tau, tau))
                best = max(cands)[3]
                chosen_tau[f"T{int(T)}_r{r}_{payback}"] = best
                for per in periods:
                    rows.append({**evaluate(per, T, "model_prob", probs[T] >= best, r, payback, best),
                                 "tau_selection": "chosen_on_cv_jul"})
                    for pname, al in rules.items():
                        rows.append({**evaluate(per, T, pname, al, r, payback, np.nan), "tau_selection": "rule"})
    return pd.DataFrame(rows), chosen_tau


def startup_staggering(iv: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """전면 가동 평일의 08:00~08:59 과도분(정상 고원 초과분)의 s 비율을 07:15~07:59로 옮긴다."""
    y = iv["y_train"]
    st = F.schedule_table(iv)
    ymat = y.to_numpy().reshape(-1, 96)
    dates = pd.DatetimeIndex(st.index)
    rows = []
    for i, d in enumerate(dates):
        if not (st["regime"].iloc[i] == 2 and st["daytype3"].iloc[i] == 0) or np.isfinite(ymat[i]).sum() < 90:
            continue
        v = ymat[i].copy()
        plateau = np.nanmean(v[36:44])
        for s in (0.5, 1.0):
            w = v.copy()
            excess = np.clip(w[32:36] - plateau, 0, None) * s
            w[32:36] -= excess
            w[29:32] += excess.sum() / 3
            rows.append(dict(date=d, month=d.month, period="test" if d >= C.TEST_START else "pre_test", share=s,
                             daymax_before=float(np.nanmax(v)), daymax_after=float(np.nanmax(w)),
                             reduction=float(np.nanmax(v) - np.nanmax(w)), moved_energy=float(excess.sum())))
    dd = pd.DataFrame(rows)
    mon = dd.groupby(["share", "month"]).agg(days=("date", "count"), mean_daily_reduction=("reduction", "mean"),
                                              month_max_before=("daymax_before", "max"),
                                              month_max_after=("daymax_after", "max")).reset_index()
    mon["month_max_reduction"] = mon["month_max_before"] - mon["month_max_after"]
    return dd, mon


def cooling_scenario(iv: pd.DataFrame, slope: float, base_temp: float = 28.0) -> pd.DataFrame:
    """시험 기간 전면 가동일 주간(08~20시): 최고기온이 base_temp를 넘는 만큼 slope×초과°C × c를 경감."""
    y = iv["y"]
    st = F.schedule_table(iv)
    day = iv.index.normalize()
    tmax = iv["temp"].groupby(day).max()
    rows = []
    m_test = (iv.index >= C.TEST_START) & iv["usable"].to_numpy()
    work = (st["regime"].reindex(day).to_numpy() == 2) & (iv["hour"].to_numpy() >= 8) & (iv["hour"].to_numpy() < 20)
    excess = np.maximum(tmax.reindex(day).to_numpy() - base_temp, 0)
    for c in (0.3, 0.5):
        cut = slope * excess * c * work
        y2 = y.to_numpy() - cut
        for mon in (8, 9):
            mm = m_test & (iv.index.month == mon)
            rows.append(dict(share_reducible=c, month=mon, slope_per_C=slope, base_temp=base_temp,
                             month_max_before=float(np.nanmax(y.to_numpy()[mm])), month_max_after=float(np.nanmax(y2[mm])),
                             hot_workdays=int(len(np.unique(day[mm & (excess > 0) & work])))))
    out = pd.DataFrame(rows)
    out["month_max_reduction"] = out["month_max_before"] - out["month_max_after"]
    return out


def alarm_grades(iv: pd.DataFrame, selection: dict) -> pd.DataFrame:
    """확률 구간별 실제 초과 빈도(보정 근거)와 권장 조치."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    idx = iv.index
    st = F.schedule_table(iv)
    grp = PK.target_window_groups(PK.regime(iv, st["regime"]))
    mA = selection["A"]["chosen"]
    preds_h = {h: SP.honest_stream(f"A{h}", mA).reindex(idx) for h in range(1, 5)}
    labels = PK.next_hour_labels(y, usable)
    T_arr = SP.thresholds(iv, idx)
    bands = [(0.0, 0.2, "정상", "조치 없음"), (0.2, 0.5, "주의", "다음 1시간 기동 예정 설비 확인·대기"),
             (0.5, 0.8, "경계", "비필수 부하(공조 설정·보조 설비) 준비, 동시 기동 금지"),
             (0.8, 1.01, "심각", "제어 가능 부하 차단·기동 지연(≤30분), 수요 담당자 통보")]
    rows = []
    for name, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        T = CV.peak_threshold(iv, s if name != "test" else C.TEST_START)
        p = PK.next_hour_prob(idx, preds_h, y, T, grp).to_numpy()
        m = (idx >= s) & (idx < e) & labels["valid"].to_numpy() & np.isfinite(p)
        lab = labels["max_next"].to_numpy() >= T
        per = "test" if name == "test" else "cv"
        for lo, hi, g, act in bands:
            b = m & (p >= lo) & (p < hi)
            rows.append(dict(period=per, fold=name, grade=g, p_lo=lo, p_hi=hi, n=int(b.sum()), exceed=int((lab & b).sum()),
                             action=act))
    t = pd.DataFrame(rows)
    agg = t.groupby(["period", "grade", "p_lo", "p_hi", "action"], sort=False)[["n", "exceed"]].sum().reset_index()
    agg["observed_rate"] = agg["exceed"] / agg["n"].replace(0, np.nan)
    return agg


def run(iv: pd.DataFrame, frames: dict, selection: dict) -> dict:
    od = io.out_dir("field")
    peak = json.loads((C.OUTPUT_DIR / "peak" / "peak_summary.json").read_text(encoding="utf-8"))
    tau = peak["tau"][peak["prob_method"]["chosen"]]["tau_f1"]
    dc, taus = demand_controller(iv, selection, tau)
    io.write_csv(dc, od / "demand_controller.csv")
    io.write_json({"targets": list(targets_from_pretest(iv)), "target_fractions_of_pretest_max": list(TARGET_FRACTIONS),
                   "pretest_max": float(iv.loc[iv.index < C.TEST_START, "y_train"].max()),
                   "tau_by_setting_chosen_on_cv_jul": taus,
                   "note": ("S7 수요제어 설계(차단 30분·회복 방식)는 첫 구현 결함을 시험 결과로 발견한 뒤 수정한 사후 설계다. "
                            "목표는 시험 전 최대의 비율, τ는 7월에서만 고른다. '되돌림 없음'은 상한 성격의 가정이다.")},
                  od / "demand_controller_settings.json")
    dd, mon = startup_staggering(iv)
    io.write_csv(dd, od / "startup_staggering_days.csv")
    io.write_csv(mon, od / "startup_staggering_monthly.csv")
    pc = json.loads((C.OUTPUT_DIR / "analysis" / "peak_conditions.json").read_text(encoding="utf-8"))
    slope = pc.get("plateau_slope_per_C_summer_pre_test", {}).get("slope", np.nan)
    if np.isfinite(slope) and slope > 0:
        io.write_csv(cooling_scenario(iv, slope), od / "cooling_scenario.csv")
    io.write_csv(alarm_grades(iv, selection), od / "alarm_grades.csv")
    return {"tau": tau}
