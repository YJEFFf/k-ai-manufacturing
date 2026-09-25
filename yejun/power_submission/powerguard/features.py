"""특징 생성(v1). 모든 특징은 발행 시점에 알 수 있는 정보만 사용한다.

과제 B(익일): 발행 = D-1 17:00(기본). 전력은 D-1 16:45 구간까지, 완전한 날은 D-2까지.
과제 A(실시간): 발행 = 구간 i 종료. 전력은 구간 i까지, 목표 = 구간 i+h (h=1..4). 완전한 날은 D-1까지.

전력 지연값·유사일 풀은 학습 가능 구간(`y_train`: 원본·복제 아님·정전 아님·체제 불일치 아님)만 쓴다.
운영일정(날짜별 가동 체제·가동 시간 패턴·일 계획 총량)은 생산계획/근무편성으로 사전 확정된다고 가정한다.
시간별 생산량 '수량'은 헤드라인 특징이 아니며 계획 정보가치 실험(ORACLE)에서만 쓴다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

STEPS = 96
ACTIVE_PROD = 100  # 시간 생산 계획이 이 값 이상이면 그 시간 '가동 예정'


# ---------------------------------------------------------------- 날짜 단위 표

def daytype3(dates: pd.DatetimeIndex) -> np.ndarray:
    """0=평일, 1=토, 2=일·공휴일."""
    dow = dates.dayofweek
    hol = dates.isin(C.HOLIDAYS)
    return np.where(hol | (dow == 6), 2, np.where(dow == 5, 1, 0))


def daytype4(dates: pd.DatetimeIndex) -> np.ndarray:
    """0=휴무 다음 평일(월요일 등), 1=연속 평일, 2=토, 3=일·공휴일."""
    d3 = daytype3(dates)
    prev = daytype3(dates - pd.Timedelta(days=1))
    return np.where(d3 == 2, 3, np.where(d3 == 1, 2, np.where(prev == 0, 1, 0)))


def schedule_table(iv: pd.DataFrame) -> pd.DataFrame:
    """날짜별 운영일정 요약. 가동 체제: 0 정지(계획 0), 1 부분(<5000), 2 전면."""
    hourly = iv[iv.index.minute == 0][["date", "hour", "prod"]]
    wide = hourly.pivot(index="date", columns="hour", values="prod")
    t = pd.DataFrame(index=wide.index)
    t["plan_total"] = wide.sum(axis=1, min_count=1)
    active = wide >= ACTIVE_PROD
    has = wide.notna().any(axis=1)
    t["plan_active_hours"] = active.sum(axis=1).where(has)
    t["plan_first_hour"] = active.idxmax(axis=1).where(active.any(axis=1)).astype(float)
    t["plan_last_hour"] = active.iloc[:, ::-1].idxmax(axis=1).where(active.any(axis=1)).astype(float)
    t["plan_night_active"] = active.loc[:, [0, 1, 2, 3, 4, 5, 6]].sum(axis=1).where(has)
    t["plan_day_active"] = active.loc[:, list(range(8, 20))].sum(axis=1).where(has)
    t["regime"] = np.select([t["plan_total"].isna(), t["plan_total"] == 0, t["plan_total"] < 5000],
                            [np.nan, 0, 1], default=2)
    dates = pd.DatetimeIndex(t.index)
    t["daytype3"] = daytype3(dates)
    t["daytype4"] = daytype4(dates)
    t["regime_prev"] = t["regime"].shift(1)
    t["active_vec"] = list(active.astype(int).to_numpy())
    return t


def trainable_days(iv: pd.DataFrame) -> pd.Series:
    """날짜별 '학습 가능 구간이 충분한 날'(유사일 풀 자격). 80구간 이상."""
    return iv.groupby("date")["trainable"].sum() >= 80


# ---------------------------------------------------------------- 유사일

def analog_indices(iv: pd.DataFrame, st: pd.DataFrame, pool_lag_days: int, method: str, k: int,
                   recency_days: float = 30.0) -> np.ndarray:
    """날짜 D마다 유사일 풀(D-pool_lag_days 이전 학습 가능일)에서 k개를 고른다(n×k, 없으면 -1).

    method='regime': 같은 요일유형4·같은 가동 체제의 최근 k일. 없으면 같은 체제의 최근 k일.
    method='schedule': 같은 가동 체제 안에서 가동 시간 패턴 거리 + 경과일/recency_days 최소 k일.
    """
    dates = pd.DatetimeIndex(st.index)
    ok = trainable_days(iv).reindex(dates).fillna(False).to_numpy().astype(bool)
    reg = st["regime"].to_numpy()
    d4 = st["daytype4"].to_numpy()
    av = np.vstack(st["active_vec"].to_numpy()).astype(float)
    n = len(dates)
    out = np.full((n, k), -1)
    for i in range(n):
        last = i - pool_lag_days
        if last < 0:
            continue
        past = np.where(ok[: last + 1])[0]
        if past.size == 0:
            continue
        same_reg = past[reg[past] == reg[i]] if np.isfinite(reg[i]) else past
        if method == "regime":
            cand = same_reg[d4[same_reg] == d4[i]]
            if cand.size == 0:
                cand = same_reg if same_reg.size else past
            sel = cand[::-1][:k]
        else:
            cand = same_reg if same_reg.size else past
            dist = np.abs(av[cand] - av[i]).mean(axis=1) + (i - cand) / recency_days + 0.05 * (d4[cand] != d4[i])
            sel = cand[np.argsort(dist, kind="stable")][:k]
        out[i, :sel.size] = sel
    return out


def analog_profile(iv: pd.DataFrame, idx: np.ndarray) -> np.ndarray:
    """유사일 k개의 같은 슬롯 평균(구간 단위 벡터)."""
    ymat = iv["y_train"].to_numpy().reshape(-1, STEPS)
    n = idx.shape[0]
    prof = np.full((n, STEPS), np.nan)
    for i in range(n):
        rows = [r for r in idx[i] if r >= 0]
        if rows:
            with np.errstate(all="ignore"):
                prof[i] = np.nanmean(ymat[rows], axis=0)
    return prof.ravel()


def _same_daytype_recent(iv: pd.DataFrame, st: pd.DataFrame, pool_lag: int) -> np.ndarray:
    dates = pd.DatetimeIndex(st.index)
    ok = trainable_days(iv).reindex(dates).fillna(False).to_numpy().astype(bool)
    d3 = st["daytype3"].to_numpy()
    out = np.full((len(dates), 1), -1)
    for i in range(len(dates)):
        last = i - pool_lag
        if last < 0:
            continue
        past = np.where(ok[: last + 1])[0]
        c = past[d3[past] == d3[i]]
        if c.size:
            out[i, 0] = c[-1]
    return out


# ---------------------------------------------------------------- 과제 공통 특징(목표 구간 기준)

def calendar_schedule(iv: pd.DataFrame, st: pd.DataFrame, oracle_plan: bool = False) -> pd.DataFrame:
    f = pd.DataFrame(index=iv.index)
    day = iv.index.normalize()
    f["slot"] = iv["slot"].to_numpy()
    f["hour"] = iv["hour"].to_numpy()
    f["dow"] = iv["dow"].to_numpy()
    f["q_in_hour"] = (iv.index.minute // 15).to_numpy()
    for c in ["daytype3", "daytype4", "regime", "regime_prev", "plan_total", "plan_active_hours",
              "plan_first_hour", "plan_last_hour", "plan_night_active", "plan_day_active"]:
        f[c] = st[c].reindex(day).to_numpy()
    f["holiday"] = iv["holiday"].astype(int).to_numpy()
    hour = f["hour"].to_numpy()
    f["hours_since_first"] = hour - f["plan_first_hour"].to_numpy()
    f["hours_to_last"] = f["plan_last_hour"].to_numpy() - hour
    act = (iv["prod"] >= ACTIVE_PROD).astype(float).where(iv["prod"].notna())
    same_day_next = (iv.index + pd.Timedelta(hours=1)).normalize() == day
    f["sched_active_h"] = act.to_numpy()
    f["sched_active_next"] = act.shift(-4).where(same_day_next).to_numpy()
    f["sched_active_prev"] = act.shift(4).to_numpy()
    f["tariff_season"] = iv["tariff"].to_numpy()
    if oracle_plan:
        prod = iv["prod"]
        f["plan_h"] = prod.to_numpy()
        f["plan_h_next"] = prod.shift(-4).where(same_day_next).to_numpy()
        f["plan_h_prev"] = prod.shift(4).to_numpy()
        tot = f["plan_total"].replace(0, np.nan)
        f["plan_share_h"] = f["plan_h"] / tot
    return f


def weather(iv: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=iv.index)
    day = iv.index.normalize()
    t = iv["temp"]
    f["temp"] = t.to_numpy()
    f["hum"] = iv["hum"].to_numpy()
    f["cdd24"] = np.maximum(t.to_numpy() - 24.0, 0)
    f["tmax_day"] = t.groupby(day).max().reindex(day).to_numpy()
    f["tmean_day"] = t.groupby(day).mean().reindex(day).to_numpy()
    f["cdd_day"] = np.maximum(f["tmax_day"].to_numpy() - 26.0, 0)
    return f


# ---------------------------------------------------------------- 과제 B: 익일

def dayahead_features(iv: pd.DataFrame, st: pd.DataFrame, issue_hour: int = 17,
                      analog_k: int = 2, oracle_plan: bool = False) -> pd.DataFrame:
    """issue_hour: D-1의 몇 시에 발행하는가(17 → D-1 16:45 구간까지 관측; 24 → D-1 전체)."""
    y = iv["y_train"]
    pool_lag = 1 if issue_hour >= 24 else 2
    known = issue_hour * 4  # D-1에서 관측된 구간 수
    f = pd.concat([calendar_schedule(iv, st, oracle_plan), weather(iv)], axis=1)
    slot = f["slot"].to_numpy()
    f["lag_d1"] = np.where(slot < known, y.shift(STEPS).to_numpy(), np.nan)
    f["lag_d2"] = y.shift(2 * STEPS).to_numpy()
    f["lag_d7"] = y.shift(7 * STEPS).to_numpy()
    ymat = y.to_numpy().reshape(-1, STEPS)
    nday = len(ymat)
    with np.errstate(all="ignore"):
        d1_day = np.nanmean(ymat[:, 32:min(known, 80)], axis=1) if known > 32 else np.full(nday, np.nan)
        part = np.where(np.isfinite(ymat[:, :known]), ymat[:, :known], -np.inf)
        d1_max = part.max(axis=1)
        d_mean = np.nanmean(ymat, axis=1)
        d_max = np.where(np.isfinite(ymat), ymat, -np.inf).max(axis=1)
    d1_max = np.where(np.isfinite(d1_max), d1_max, np.nan)
    d_max = np.where(np.isfinite(d_max), d_max, np.nan)
    di = np.repeat(np.arange(nday), STEPS)

    def prev(arr, lag):
        j = di - lag
        return np.where(j >= 0, arr[np.maximum(j, 0)], np.nan)

    f["d1_dayshift_mean"] = prev(d1_day, 1)
    f["d1_max_sofar"] = prev(d1_max, 1)
    f["d2_mean"] = prev(d_mean, 2)
    f["d2_max"] = prev(d_max, 2)
    ia = analog_indices(iv, st, pool_lag, "regime", analog_k)
    ib = analog_indices(iv, st, pool_lag, "schedule", analog_k)
    f["analog_regime"] = analog_profile(iv, ia)
    f["analog_sched"] = analog_profile(iv, ib)
    f["analog_regime_k1"] = analog_profile(iv, ia[:, :1])
    f["same_dt_last"] = analog_profile(iv, _same_daytype_recent(iv, st, pool_lag))
    # D-1 주간 수준 − D-1 자신의 유사일 주간 수준(더운 날·수준 이동 신호)
    prof = f["analog_regime"].to_numpy().reshape(-1, STEPS)
    with np.errstate(all="ignore"):
        prof_day = np.nanmean(prof[:, 32:min(known, 80)], axis=1) if known > 32 else np.full(nday, np.nan)
    f["d1_level_vs_analog"] = f["d1_dayshift_mean"].to_numpy() - prev(prof_day, 1)
    f["analog_gap"] = f["analog_regime"].to_numpy() - f["analog_sched"].to_numpy()
    f["analog_mean"] = f["analog_regime"].to_numpy()  # 기본 기준 유사일(구조 모델·하이브리드)
    # 유사일들의 일 최고기온 평균과 대상일(예보 대리) 차이: 냉방부하 보정 신호
    tmax_by_day = iv["temp"].groupby(iv.index.normalize()).max().reindex(pd.DatetimeIndex(st.index)).to_numpy()
    an_tmax = np.full(len(ia), np.nan)
    for i in range(len(ia)):
        rows = [r for r in ia[i] if r >= 0]
        if rows:
            an_tmax[i] = np.nanmean(tmax_by_day[rows])
    f["analog_tmax"] = np.repeat(an_tmax, STEPS)
    f["dtmax_vs_analog"] = f["tmax_day"].to_numpy() - f["analog_tmax"].to_numpy()
    hour = f["hour"].to_numpy()
    f["dayshift_full"] = ((f["regime"].to_numpy() == 2) & (hour >= 8) & (hour < 20)).astype(float)
    return f


# ---------------------------------------------------------------- 과제 A: 실시간

def intraday_features(iv: pd.DataFrame, h: int, day_feats_midnight: pd.DataFrame) -> pd.DataFrame:
    """행 = 목표 구간(i+h). 발행 구간 i = 목표 − h. 기준 유사일은 D-1까지의 풀(자정 발행 특징)."""
    y = iv["y_train"]
    f = day_feats_midnight.copy()
    f["horizon"] = h
    for k in range(8):
        f[f"lag_{k}"] = y.shift(h + k).to_numpy()
    f["diff_01"] = f["lag_0"] - f["lag_1"]
    f["diff_04"] = f["lag_0"] - f["lag_4"]
    f["roll4_mean"] = f[[f"lag_{k}" for k in range(4)]].mean(axis=1)
    f["roll8_max"] = f[[f"lag_{k}" for k in range(8)]].max(axis=1)
    f["lag_d1_target"] = y.shift(STEPS).to_numpy()
    # 전날 최대는 발행 시각까지만: 자정 직후 목표(발행이 D-1 23:xx)는 D-1의 발행 구간까지 누적 최대
    ym = y.to_numpy().reshape(-1, STEPS)
    cm = np.fmax.accumulate(np.where(np.isfinite(ym), ym, -np.inf), axis=1)
    cm = np.where(np.isfinite(cm), cm, np.nan)
    nday = ym.shape[0]
    di = np.repeat(np.arange(nday), STEPS)
    slot = np.tile(np.arange(STEPS), nday)
    issue_slot = slot - h
    prev = di - 1
    val = np.full(len(di), np.nan)
    okp = prev >= 0
    full = okp & (issue_slot >= 0)
    val[full] = cm[prev[full], STEPS - 1]
    part = okp & (issue_slot < 0)
    val[part] = cm[prev[part], STEPS + issue_slot[part]]
    f["d1_max_sofar"] = val
    an = pd.Series(f["analog_mean"].to_numpy(), index=iv.index)
    f["analog_now"] = an.shift(h).to_numpy()
    f["dev_analog_now"] = f["lag_0"] - f["analog_now"]
    f["dev_analog_roll4"] = (y - an).shift(h).rolling(4, min_periods=1).mean().to_numpy()
    f["analog_step"] = f["analog_mean"] - f["analog_now"]
    f["sched_active_issue"] = pd.Series(f["sched_active_h"].to_numpy(), index=iv.index).shift(h).to_numpy()
    return f


# ---------------------------------------------------------------- 특징 집합

CAL = ["slot", "hour", "dow", "q_in_hour", "daytype3", "daytype4", "holiday", "tariff_season"]
# 날짜 단위 운영일정(사전 확정 가정): 가동 체제·전날 체제·계획 총량·첫/마지막 가동 시간·주간/야간 가동 시간 수
SCHED = ["regime", "regime_prev", "plan_total", "plan_active_hours", "plan_first_hour", "plan_last_hour",
         "plan_night_active", "plan_day_active", "hours_since_first", "hours_to_last"]
# 시간 단위 가동 여부(시간별 생산량 ≥100에서 파생): 계획이 아닌 실적일 수 있어 헤드라인에서 제외, 정보가치 실험 L2 전용
HOURLY_ONOFF = ["sched_active_h", "sched_active_next", "sched_active_prev", "analog_sched", "analog_gap",
                "sched_active_issue"]
ORACLE = ["plan_h", "plan_h_next", "plan_h_prev", "plan_share_h"]
WEATHER = ["temp", "hum", "cdd24", "tmax_day", "tmean_day", "cdd_day"]
B_LAGS = ["lag_d1", "lag_d2", "lag_d7", "d1_dayshift_mean", "d1_max_sofar", "d2_mean", "d2_max",
          "analog_regime", "analog_regime_k1", "same_dt_last", "d1_level_vs_analog",
          "analog_tmax", "dtmax_vs_analog", "dayshift_full"]
A_LAGS = [f"lag_{k}" for k in range(8)] + ["diff_01", "diff_04", "roll4_mean", "roll8_max", "lag_d1_target",
                                           "analog_now", "dev_analog_now", "dev_analog_roll4", "analog_step"]
COOLING = ["cdd24", "cdd_day", "dtmax_vs_analog"]
SCHEDULE_DERIVED = ["analog_regime", "analog_regime_k1", "d1_level_vs_analog", "analog_tmax", "dtmax_vs_analog",
                    "dayshift_full", "analog_now", "dev_analog_now", "dev_analog_roll4", "analog_step"]


def feature_list(task: str, weather_on: bool = True, schedule_on: bool = True, oracle: bool = False,
                 hourly_onoff: bool = False) -> list[str]:
    """헤드라인 = 달력 + 날짜 단위 운영일정 + 기상 + 지연·유사일. hourly_onoff·oracle은 정보가치 실험 전용."""
    cols = list(CAL)
    if schedule_on:
        cols += SCHED
    if weather_on:
        cols += WEATHER
    cols += B_LAGS if task == "B" else B_LAGS + A_LAGS
    if hourly_onoff or oracle:
        cols += [c for c in HOURLY_ONOFF if task == "A" or c != "sched_active_issue"]
    if oracle:
        cols += ORACLE
    if not schedule_on:
        cols = [c for c in cols if c not in SCHEDULE_DERIVED]
    return cols
