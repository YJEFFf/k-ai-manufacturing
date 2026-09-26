"""S7: 현장 활용 시뮬레이션(가정 기반, 실측 절감 아님).

1) 요금 구조: 한전 기본요금의 요금적용전력(당월과 직전 12개월 중 12·1·2·7·8·9월 최대수요 중 최대, '래칫')
2) 수요제어기: 다음 1시간 목표전력 초과확률 경보 → 제어 가능 부하 r을 30분 차단, 이후 1시간(또는 저부하 시간, 또는 측정 기반
   여유 구간·그날 저녁)에 지연 에너지 회복. τ는 교차검증(6·7월)에서 가동일당 개입 예산 안에서 고른다.
3) 순차·선행 기동: 기동 과도분을 07:15~07:59로 분산(시험 전 중앙값으로 정한 고정 정책, 유지 부하 민감도)
4) 여름 냉방: 최고기온 기울기(시험 전 추정과 구간)로 사전 냉방(에너지를 05~06시로 이동) 시 주간 부하 경감
5) 야간 이동: 주간 가동 부하 일부를 야간조 시간으로 옮기는 산술 시나리오
6) 경보 등급표: 확률 구간별 실제 초과 빈도, 가동일당 부담(히스테리시스 포함), 조치·담당·확인 항목
7) 통합 운영 절차와 통합 시나리오(인터록 상한 + 기동 분산 + 사전 냉방 + 수요제어)의 월 최대·요금적용전력·래칫 결정 구간
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

TARGET_FRACTIONS = (0.88, 0.90, 0.92, 0.95)  # 시험 전 최대수요의 비율로 목표전력을 정한다
TARGET_SWEEP = (0.80, 0.85, 0.88, 0.90, 0.92, 0.95, 0.98, 1.00)  # 민감도(사후 설계 표시)
SHED = (0.05, 0.10, 0.15)  # 제어 가능 부하 비율 가정(공조·압축기·보조 설비 비중에 대한 가정값, 실측 아님)
SHED_LEN = 2      # 한 번 차단은 최대 30분(2구간)
REBOUND_LEN = 4   # 지연 에너지는 이후 1시간(4구간)에 고르게 회복, 회복 중에는 재차단하지 않는다
BUDGET_EPISODES_PER_WORKDAY = 2.0  # τ 선택 제약: 가동일당 차단 개입 수
RATCHET_MONTHS = (12, 1, 2, 7, 8, 9)
RATCHET_FIRST_IN_DATA = pd.Timestamp("2021-07-01")  # 자료 안 첫 래칫 대상 월
VALLEY_LEVEL = 140.0          # 익일 예측이 이 값 이하인 구간(점심·휴식·저녁)을 회복 구간으로 쓴다
TAU_CAND = (0.2, 0.3, 0.5, 0.7, 0.9)
PAYBACK = ("none", "valley", "immediate", "valley_capped")  # valley_capped(v2.1, v2.3 수정): 차단 직후 재경보 허용, 측정(차단 전)과 익일 예측에 여유가 있을 때만 회복
ROOM_MARGIN = 5.0


def pretest_max(iv: pd.DataFrame) -> float:
    return float(iv.loc[iv.index < C.TEST_START, "y_train"].max())


def targets_from_pretest(iv: pd.DataFrame, fractions=TARGET_FRACTIONS) -> tuple[float, ...]:
    """목표전력 = 시험 시작 전 학습 가능 구간의 최대 15분 수요 × 비율.

    기준값(시험 전 최대)은 시험 정보를 쓰지 않지만, 비율 0.88~0.95는 v1.2에서 시험 월 최대를 본 뒤 정한 195~210 범위를
    재현하므로 사후 설계다. 0.80~1.00 전 구간 민감도를 함께 낸다(demand_controller_sensitivity.csv)."""
    ref = pretest_max(iv)
    return tuple(round(ref * f, 1) for f in fractions)


# ---------------------------------------------------------------- 요금적용전력(래칫)

def billing_demand(month_max: dict) -> dict:
    """월별 요금적용전력 = max(당월 최대, 자료 안의 직전 12개월 중 12·1·2·7·8·9월 최대).

    자료는 2021년 5~9월 실측뿐이므로 2020년 달은 알 수 없다(값이 없는 달은 빼고 계산). 계약전력 30% 하한은 쓰지 않는다.
    """
    out = {}
    months = sorted(month_max)
    for m in months:
        cands = [month_max[m]] + [month_max[k] for k in months if k < m and k in RATCHET_MONTHS]
        out[m] = float(max(cands))
    return out


def ratchet_max(month_max: dict) -> float:
    """다음 12개월 기본요금을 정하는 값: 자료 안 7·8·9월 최대수요 중 최대."""
    v = [month_max[m] for m in month_max if m in RATCHET_MONTHS]
    return float(max(v)) if v else np.nan


def monthly_max(y: np.ndarray, index: pd.DatetimeIndex, months=(5, 6, 7, 8, 9)) -> dict:
    s = pd.Series(y, index=index)
    s = s[(s.index >= C.MEASURED_START) & (s.index < C.TEST_END)]
    mm = s.groupby(s.index.month).max()
    return {int(k): float(v) for k, v in mm.items() if int(k) in months and np.isfinite(v)}


SPIKE_JUMP = 15.0  # 앞뒤 두 구간보다 모두 이만큼 높으면 한 구간짜리 스파이크(7/19 11:15는 +15.0으로 경계 사례 → 10·20 민감도)
SPIKE_JUMP_SWEEP = (10.0, 15.0, 20.0)


def event_type(jump: float, slot: int, spike_jump: float = SPIKE_JUMP) -> str:
    """사건 유형: spike(앞뒤 구간보다 모두 spike_jump 이상 높은 한 구간), startup(08:00~08:59), plateau(09~16시), other."""
    if jump >= spike_jump:
        return "spike"
    if 32 <= slot <= 35:
        return "startup"
    if 36 <= slot <= 63:
        return "plateau"
    return "other"


def ratchet_events(iv: pd.DataFrame, top: int = 8, spike_jump: float = SPIKE_JUMP) -> pd.DataFrame:
    """래칫 대상 월(7·8·9월)의 날짜별 최대 15분 수요 상위 사건: 시각·유형·대응 대책."""
    y = iv["y"]
    tmax = iv["temp"].groupby(iv.index.normalize()).max()
    s = y[(y.index.month >= 7) & y.notna()]
    rows = []
    for ts, v in s.sort_values(ascending=False).items():
        d = ts.normalize()
        if any(r["date"] == d for r in rows):
            continue
        slot = ts.hour * 4 + ts.minute // 15
        prev = y.get(ts - pd.Timedelta(minutes=15), np.nan)
        nxt = y.get(ts + pd.Timedelta(minutes=15), np.nan)
        jump = float(v - np.nanmax([prev, nxt]))
        typ = event_type(jump, slot, spike_jump)
        rows.append(dict(date=d, time=ts.strftime("%H:%M"), value=float(v), prev_interval=prev, next_interval=nxt,
                         jump_vs_neighbors=jump, tmax=float(tmax.get(d, np.nan)), month=ts.month, type=typ,
                         period="test" if ts >= C.TEST_START else "pre_test", spike_jump=spike_jump,
                         measure={"spike": "동시 기동 인터록·15분 창 제어(당일 실시간)", "startup": "순차·선행 기동",
                                  "plateau": "사전 냉방·수요제어", "other": "수요제어"}[typ]))
        if len(rows) >= top:
            break
    return pd.DataFrame(rows)


def apply_interlock(y: np.ndarray, spike_jump: float = SPIKE_JUMP) -> tuple[np.ndarray, int]:
    """동시 기동 인터록의 가정 상한: 앞뒤 두 구간보다 모두 spike_jump 이상 높은 한 구간을 이웃 최대로 묶는다(스파이크가 모두
    동시 재기동 때문이고 인터록으로 막을 수 있다는 가정, 초과 에너지는 이동하지 않음). 묶은 구간 수를 함께 준다."""
    y2 = y.copy()
    nb = np.fmax(np.r_[np.nan, y[:-1]], np.r_[y[1:], np.nan])
    both = np.isfinite(np.r_[np.nan, y[:-1]]) & np.isfinite(np.r_[y[1:], np.nan]) & np.isfinite(y)
    hit = both & (y - nb >= spike_jump)
    y2[hit] = nb[hit]
    return y2, int(hit.sum())


def ratchet_ladder(iv: pd.DataFrame, top: int = 6) -> tuple[pd.DataFrame, pd.DataFrame]:
    """래칫 사다리: 7~9월 날짜별 최대를 큰 순으로 하나씩 막으면(그날 최대를 다음 사건 수준으로 묶음) 요금적용전력이 얼마나 내려가는가.
    완전 제어 상한: 목표 T를 넘은 구간을 모두 T로 묶을 때의 초과 구간·일수·에너지와 요금적용전력 변화."""
    y = iv["y"]
    s = y[(y.index >= RATCHET_FIRST_IN_DATA) & (y.index < C.TEST_END) & y.notna()]
    dmax = s.groupby(s.index.normalize()).max().sort_values(ascending=False)
    base = float(dmax.iloc[0])
    lad = [dict(step=0, capped_day="", ratchet=base, change_pct=0.0)]
    for k in range(1, min(top, len(dmax) - 1) + 1):
        new = float(dmax.iloc[k])
        lad.append(dict(step=k, capped_day=str(dmax.index[k - 1].date()), ratchet=new, change_pct=(new - base) / base * 100))
    ub = []
    ref = pretest_max(iv)
    for frac in (0.90, 0.92, 0.95, 0.98):
        T = round(ref * frac, 1)
        over = s[s > T]
        ub.append(dict(target=T, target_fraction=frac, intervals_over=int(len(over)),
                       days_over=int(over.index.normalize().nunique()),
                       energy_over_share=float((over - T).sum() / s.sum()),
                       ratchet_if_perfect=min(base, T), change_pct=(min(base, T) - base) / base * 100))
    return pd.DataFrame(lad), pd.DataFrame(ub)


def ratchet_risk_days(iv: pd.DataFrame, selection: dict, margin: float = 5.0) -> tuple[pd.DataFrame, dict]:
    """래칫 위험일 선별(익일 과제 B의 출력 → D-1 17:00 조치): 7월 이후 날짜 D의 기준 R_D = 발행 시점까지 확정된
    그해 래칫 대상 월(7월~)의 최대수요(D-2까지 전체 + D-1 16:45까지). 위험 = P(일 최대 ≥ R_D − margin).
    문턱은 7월(교차검증)에서 F1 최대로 고르고 8·9월(시험)에 그대로 적용한다."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    st = F.schedule_table(iv)
    predB = SP.honest_stream("B", selection["B"]["chosen"]).reindex(iv.index)
    yv = y.where(iv["usable"])
    dmax = yv.groupby(yv.index.normalize()).max()
    part = yv[yv.index.hour < 17]
    dmax_part = part.groupby(part.index.normalize()).max()
    R = {}
    for d in pd.date_range(RATCHET_FIRST_IN_DATA + pd.Timedelta(days=1), C.TEST_END - pd.Timedelta(days=1)):
        full = dmax[(dmax.index >= RATCHET_FIRST_IN_DATA) & (dmax.index < d - pd.Timedelta(days=1))].dropna()
        prev = dmax_part.get(d - pd.Timedelta(days=1), np.nan)
        vals = list(full.values) + ([prev] if np.isfinite(prev) else [])
        if vals:
            R[d] = float(max(vals)) - margin
    Rs = pd.Series(R)
    dp, _ = PK.day_max_prob(predB, y, usable, np.nan, st["regime"], T_by_date=Rs)
    if dp.empty:
        return dp, {}
    dp["R_minus_margin"] = dp["date"].map(Rs)
    dp["period"] = np.where(dp["date"] >= C.TEST_START, "test", "cv_jul")
    dp = dp[dp["label"].notna()].copy()
    dp["label"] = dp["label"].astype(bool).astype(int)
    cv = dp[dp.period == "cv_jul"]
    best = (0.2, -1.0)
    for tau in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5):
        a = cv["p_daymax"] >= tau
        tp = int((a & (cv["label"] == 1)).sum())
        fp = int((a & (cv["label"] == 0)).sum())
        fn = int((~a & (cv["label"] == 1)).sum())
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        if f1 >= best[1]:
            best = (tau, f1)
    dp["flag"] = (dp["p_daymax"] >= best[0]).astype(int)  # 운영 규칙(D-1 17:00 실행 가능): 7월 교차검증 문턱
    reg = st["regime"].reindex(pd.DatetimeIndex(dp["date"])).to_numpy()
    dp["workday"] = (reg == 2).astype(int)
    # 사후 순위 평가(운영 규칙 아님): 기간 안 가동일의 위험 확률 순위와 주당 상위 1일. 같은 주 뒤 날짜의 확률을 쓰므로
    # D-1 17:00에 실행할 수 없다. 인과 비교(확인용, 채택 아님): 직전 4가동일의 확률보다 모두 높으면 표시
    dp["rank_in_period"] = np.nan
    dp["week_top1_posthoc"] = 0
    dp["above_prev4_workdays"] = 0
    for per, g in dp[dp["workday"] == 1].groupby("period"):
        dp.loc[g.index, "rank_in_period"] = g["p_daymax"].rank(ascending=False, method="min")
        wk = pd.DatetimeIndex(g["date"]).to_period("W")
        top = g.groupby(wk)["p_daymax"].idxmax()
        dp.loc[top.to_numpy(), "week_top1_posthoc"] = 1
    gw_all = dp[dp["workday"] == 1].sort_values("date")
    prev_max = gw_all["p_daymax"].shift(1).rolling(4, min_periods=4).max()
    dp.loc[gw_all.index, "above_prev4_workdays"] = (gw_all["p_daymax"] > prev_max).astype(int).to_numpy()
    res = {"margin": margin, "tau_chosen_on_july": best[0],
           "note": ("운영 규칙은 7월 교차검증 문턱 τ(D-1 17:00 실행 가능). 7월 기준(초기 래칫 ≈201)에서 고른 τ는 시험(≈217)으로 옮기면 "
                    "맞지 않는다. 순위·주당 상위 1일은 같은 주 뒤 날짜의 확률을 쓰는 사후 순위 평가이고, 직전 4가동일 비교는 확인용 인과 "
                    "규칙이다(둘 다 채택하지 않음)")}
    for per, g in dp.groupby("period"):
        gw = g[g["workday"] == 1]
        tp = int(((g.flag == 1) & (g.label == 1)).sum())
        fp = int(((g.flag == 1) & (g.label == 0)).sum())
        fn = int(((g.flag == 0) & (g.label == 1)).sum())
        res[per] = {"days": int(len(g)), "workdays": int(len(gw)), "risk_days_actual": int((g.label == 1).sum()),
                    "flagged_tau": int(g.flag.sum()), "TP": tp, "FP": fp, "FN": fn,
                    "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
                    "flag_rate_workdays": float(gw.flag.mean()) if len(gw) else None,
                    "risk_day_ranks_among_workdays_posthoc": [int(r) for r in gw.loc[gw.label == 1, "rank_in_period"]],
                    "week_top1_posthoc_days": int(gw.week_top1_posthoc.sum()),
                    "week_top1_posthoc_hits": int(((gw.week_top1_posthoc == 1) & (gw.label == 1)).sum()),
                    "above_prev4_days": int(gw.above_prev4_workdays.sum()),
                    "above_prev4_hits": int(((gw.above_prev4_workdays == 1) & (gw.label == 1)).sum())}
    return dp, res


# ---------------------------------------------------------------- 수요제어기

EVENING_SLOTS = (80, 96)  # 20:00~23:59: 창 안에 못 푼 회복분을 나눠 만회하는 같은 날 저녁 구간(측정 기반 회복)


def _evening_catchup(t0: int, n: int, ok: np.ndarray, slot: np.ndarray) -> list[int]:
    """t0 이후 같은 날 20~23시의 유효 구간. 없으면(이미 밤이거나 자료 끝) t0부터 8구간(2시간)."""
    day_end = t0 + (95 - int(slot[min(t0, n - 1)]))
    cand = [t for t in range(t0, min(day_end + 1, n)) if ok[t] and slot[t] >= EVENING_SLOTS[0]]
    if not cand:
        cand = [t for t in range(t0, min(t0 + 8, n)) if ok[t]]
    return cand


def simulate(y: np.ndarray, alarm_issue: np.ndarray, r: float, valley: np.ndarray | None = None,
             search: int = 16, shed_len: int = SHED_LEN, rebound_len: int = REBOUND_LEN,
             room: np.ndarray | None = None, unlock_after_shed: bool = False,
             slot: np.ndarray | None = None, forecast: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """상태기계: 대기 → (발행 구간 i 경보) → i+1..i+shed_len 차단(부하 r 감소) → 에너지 회복 → 대기.

    회복: valley(익일 예측상 저부하 구간 표시)가 주어지면 차단 뒤 search 구간(4시간) 안의 저부하 구간
    최대 rebound_len개에 고르게 더한다(생산 만회를 저부하 시간으로 미룸). 없거나 valley가 없으면
    바로 뒤 rebound_len 구간에 더한다(최악의 반동). 마지막 회복 구간 종료 시점의 경보부터 다시 받는다.
    room(측정 기반 회복)은 아래 주석 참고. slot은 하루 안 구간 번호(0~95, 없으면 자정 시작 격자로 가정).
    forecast는 익일 예측(D-1 17:00 발행, 과제 B): 주어지면 그 구간 예측에도 여유가 있어야 회복분을 푼다.
    """
    n = len(y)
    y2 = y.copy()
    ok = np.isfinite(y)
    slot = np.arange(n) % 96 if slot is None else slot
    shed_amt = np.zeros(n)  # 구간별 차단량(운영자가 아는 값): 회복 판정에 차단 전 수요를 쓰기 위해
    added = np.zeros(n)     # 구간별로 이미 푼 회복분(여러 차단 사건의 회복분이 한 구간에 겹쳐 쌓이지 않게)
    i, episodes, shed_n, deferred, to_valley = 0, 0, 0, 0.0, 0
    ready_from = 0  # 이 발행 구간부터 새 경보를 받는다
    while i < n:
        if alarm_issue[i] and i >= ready_from:
            shed_idx = [t for t in range(i + 1, min(i + 1 + shed_len, n)) if ok[t]]
            if shed_idx:
                e = float(np.sum(y[shed_idx]) * r)
                y2[shed_idx] = y2[shed_idx] - y[shed_idx] * r
                shed_amt[shed_idx] += y[shed_idx] * r
                end = shed_idx[-1]
                rec = []
                if room is not None:
                    # 측정 기반 회복(v2.3): 직전 구간의 '차단 전' 수요(측정값 + 그 구간 차단량)와 그 구간의 익일 예측이 모두
                    # 그 구간에 이미 푼 회복분과 이번 회복분을 더해도 (목표 − 여유) 이하일 때만 푼다. v2.2는 차단으로 낮아진
                    # 측정값만 보고 차단 직후에 풀었고, 여러 사건의 회복분이 한 구간에 겹쳤다. 창(search) 안에 다 못 풀면 남은 양을
                    # 같은 날 20~23시에 고르게 나눠 만회한다(v2.2는 창 끝 한 구간에 몰았다). 인과적: 직전 측정·차단 기록과 D-1 예측만
                    # 쓴다. 예측할 수 없는 한 구간 급변(7/19 11:15처럼 직전이 낮은 경우)은 이 규칙으로도 막지 못한다(15분 창 제어의 몫).
                    share = e / rebound_len
                    left, t = e, end + 1
                    while left > 1e-9 and t < min(end + 1 + search, n):
                        head = y2[t - 1] + shed_amt[t - 1] if ok[t - 1] else np.inf
                        if forecast is not None:
                            head = max(head, forecast[t] if np.isfinite(forecast[t]) else np.inf)
                        if ok[t] and head + added[t] + share <= room[t]:
                            amt = min(share, left)
                            y2[t] += amt
                            added[t] += amt
                            left -= amt
                            rec.append(t)
                        t += 1
                    to_valley += int(left <= 1e-9)
                    if left > 1e-9:
                        late = _evening_catchup(min(end + 1 + search, n - 1), n, ok, slot)
                        if late:
                            y2[late] += left / len(late)
                            added[late] += left / len(late)
                            rec += late
                elif valley is not None:
                    rec = [t for t in range(end + 1, min(end + 1 + search, n)) if ok[t] and valley[t]][:rebound_len]
                    to_valley += int(bool(rec))
                if room is None and not rec:
                    rec = [t for t in range(end + 1, min(end + 1 + rebound_len, n)) if ok[t]]
                if room is None and rec:
                    y2[rec] += e / len(rec)
                episodes += 1
                shed_n += len(shed_idx)
                deferred += e
                ready_from = end if unlock_after_shed else (max(rec) if rec else end)
                i = end
                continue
        i += 1
    return y2, {"episodes": episodes, "shed_intervals": shed_n, "deferred_energy": deferred,
                "payback_to_valley_share": to_valley / episodes if episodes else np.nan}


def _run_policy(yfill, al, r, payback, valley, shed_len: int = SHED_LEN, rebound_len: int = REBOUND_LEN, room=None,
                slot=None, forecast=None):
    if payback == "none":
        y2 = yfill.copy()
        n = len(y2)
        ok = np.isfinite(yfill)
        i, ep, shed_n, ready_from = 0, 0, 0, 0
        while i < n:
            if al[i] and i >= ready_from:
                idx = [t for t in range(i + 1, min(i + 1 + shed_len, n)) if ok[t]]
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
    elif payback == "valley_capped":
        y2, info = simulate(yfill.copy(), al, r, valley, shed_len=shed_len, rebound_len=rebound_len,
                            room=room, unlock_after_shed=True, slot=slot, forecast=forecast)
    else:
        y2, info = simulate(yfill.copy(), al, r, valley if payback == "valley" else None,
                            shed_len=shed_len, rebound_len=rebound_len)
    return y2, info


class _Ctx:
    """수요제어 공통 입력(예측 흐름·확률·가동일)."""

    def __init__(self, iv: pd.DataFrame, selection: dict):
        self.iv = iv
        self.idx = iv.index
        self.st = F.schedule_table(iv)
        self.grp = PK.target_window_groups(PK.regime(iv, self.st["regime"]))
        mA = selection["A"]["chosen"]
        self.preds_h = {h: SP.honest_stream(f"A{h}", mA).reindex(self.idx) for h in range(1, 5)}
        predB = SP.honest_stream("B", selection["B"]["chosen"]).reindex(self.idx).to_numpy()
        self.predB = predB
        self.valley = np.nan_to_num(predB, nan=np.inf) <= VALLEY_LEVEL
        self.yfill = np.where(iv["usable"].to_numpy(), iv["y"].to_numpy(), np.nan)
        self.reg_day = self.st["regime"].reindex((self.idx + pd.Timedelta(minutes=15)).normalize()).to_numpy()
        self.nxt = self.idx + pd.Timedelta(minutes=15)
        self.slot = np.asarray(self.idx.hour * 4 + self.idx.minute // 15)
        self.periods = {"cv": (C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2]), "test": (C.TEST_START, C.TEST_END)}
        self._prob = {}

    def prob(self, T: float) -> np.ndarray:
        if T not in self._prob:
            self._prob[T] = np.nan_to_num(PK.next_hour_prob(self.idx, self.preds_h, self.iv["y"], T, self.grp).to_numpy())
        return self._prob[T]

    def workdays(self, m: np.ndarray) -> int:
        d = pd.DatetimeIndex(np.unique(self.idx[m].normalize()))
        return int((self.st["regime"].reindex(d) == 2).sum())

    def rules(self, T: float) -> dict:
        y0 = np.nan_to_num(self.yfill)
        return {
            "reactive_now>=T-5": y0 >= T - 5,
            "reactive_now>=T-10": y0 >= T - 10,
            "clock_0800_fullday": (self.reg_day == 2) & (self.nxt.hour == 8) & (self.nxt.minute == 0),
            "oracle_perfect": np.r_[(y0 >= T)[1:], False],
        }


def _evaluate(ctx: _Ctx, per: str, T: float, pname: str, al, r, payback, tau, shed_len=SHED_LEN, rebound_len=REBOUND_LEN):
    s0, e0 = ctx.periods[per]
    idx = ctx.idx
    m = (idx >= s0) & (idx < e0)
    wd = max(ctx.workdays(m), 1)
    room = np.full(len(ctx.yfill), T - ROOM_MARGIN)  # 측정 기반 회복의 상한(목표 − 여유)
    y2, info = _run_policy(ctx.yfill, al & m, r, payback, ctx.valley, shed_len, rebound_len, room=room, slot=ctx.slot,
                           forecast=ctx.predB)
    bm = pd.Series(ctx.yfill[m], index=idx[m]).groupby(idx[m].month).max()
    am = pd.Series(y2[m], index=idx[m]).groupby(idx[m].month).max()
    ob, oa = int(np.nansum(ctx.yfill[m] >= T)), int(np.nansum(y2[m] >= T))
    return dict(period=per, target=T, policy=pname, shed=r, payback=payback, tau=tau, shed_len=shed_len,
                rebound_len=rebound_len, intervals_over_before=ob, intervals_over_after=oa,
                over_reduction_share=(ob - oa) / ob if ob else np.nan,
                month_max_before=json.dumps({int(k): float(v) for k, v in bm.items()}),
                month_max_after=json.dumps({int(k): round(float(v), 2) for k, v in am.items()}),
                max_month_max_change=float((am - bm).max()), workdays=wd,
                episodes_per_workday=info["episodes"] / wd, shed_hours_per_workday=info["shed_intervals"] * 0.25 / wd,
                deferred_energy_share=info["deferred_energy"] / float(np.nansum(ctx.yfill[m])),
                payback_to_valley_share=info["payback_to_valley_share"]), y2


def choose_tau(ctx: _Ctx, T: float, r: float, payback: str, rows: list | None = None) -> float:
    """교차검증(6·7월)에서: 월 최대가 늘지 않고 가동일당 개입 ≤ 예산인 τ 중 초과 구간 감소율 최대. 없으면 가장 높은 τ."""
    cands = []
    for tau in TAU_CAND:
        row, _ = _evaluate(ctx, "cv", T, "model_prob", ctx.prob(T) >= tau, r, payback, tau)
        if rows is not None:
            rows.append({**row, "tau_selection": "candidate"})
        ok = row["max_month_max_change"] <= 0 and row["episodes_per_workday"] <= BUDGET_EPISODES_PER_WORKDAY
        red = row["over_reduction_share"] if np.isfinite(row["over_reduction_share"]) else -9
        cands.append((red, tau, ok))
    feasible = [c for c in cands if c[2]]
    if not feasible:
        return max(TAU_CAND)  # 조건을 만족하는 τ가 없으면 개입이 가장 적은(가장 높은) τ
    return max(feasible)[1]


def demand_controller(ctx: _Ctx, targets) -> tuple[pd.DataFrame, dict]:
    rows, chosen_tau = [], {}
    for T in targets:
        for r in SHED:
            for payback in PAYBACK:
                best = choose_tau(ctx, T, r, payback, rows)
                chosen_tau[f"T{T}_r{r}_{payback}"] = best
                for per in ctx.periods:
                    row, _ = _evaluate(ctx, per, T, "model_prob", ctx.prob(T) >= best, r, payback, best)
                    rows.append({**row, "tau_selection": "chosen_on_cv_budget"})
                    for pname, al in ctx.rules(T).items():
                        row, _ = _evaluate(ctx, per, T, pname, al, r, payback, np.nan)
                        rows.append({**row, "tau_selection": "rule"})
    return pd.DataFrame(rows), chosen_tau


def controller_pareto(ctx: _Ctx, T: float, r: float = 0.10, payback: str = "valley") -> pd.DataFrame:
    """개입 수 대비 효과(파레토): 모델 τ 격자 vs 반응형 문턱 격자, 교차검증·시험."""
    rows = []
    for per in ctx.periods:
        for tau in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
            row, _ = _evaluate(ctx, per, T, "model_prob", ctx.prob(T) >= tau, r, payback, tau)
            rows.append({**row, "knob": tau})
        y0 = np.nan_to_num(ctx.yfill)
        for dlt in (0, 5, 10, 15, 20):
            row, _ = _evaluate(ctx, per, T, "reactive_now>=T-d", y0 >= T - dlt, r, payback, np.nan)
            rows.append({**row, "knob": dlt})
    return pd.DataFrame(rows)


def controller_sensitivity(ctx: _Ctx) -> pd.DataFrame:
    """사후 설계 민감도: 목표 비율 0.80~1.00, 차단 길이 1~4구간, 회복 길이 2~8구간(τ는 각 설정의 교차검증에서)."""
    rows = []
    for frac, T in zip(TARGET_SWEEP, targets_from_pretest(ctx.iv, TARGET_SWEEP)):
        tau = choose_tau(ctx, T, 0.10, "valley")
        for per in ctx.periods:
            row, _ = _evaluate(ctx, per, T, "model_prob", ctx.prob(T) >= tau, 0.10, "valley", tau)
            rows.append({**row, "target_fraction": frac, "sweep": "target"})
    T = targets_from_pretest(ctx.iv, (0.92,))[0]
    tau = choose_tau(ctx, T, 0.10, "valley")
    for sl in (1, 2, 3, 4):
        for rl in (2, 4, 8):
            for per in ctx.periods:
                row, _ = _evaluate(ctx, per, T, "model_prob", ctx.prob(T) >= tau, 0.10, "valley", tau, sl, rl)
                rows.append({**row, "target_fraction": 0.92, "sweep": "shed_rebound"})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 순차·선행 기동

def _plateau(v: np.ndarray) -> float:
    return float(np.nanmean(v[C.PLATEAU_SLOTS]))  # 09:00~09:59(10:00 휴식 저부하 제외, config 공통 정의)


def startup_staggering(iv: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float]:
    """전면 가동 평일의 08:00~08:59 과도분(09시대 고원 초과분)을 07:15~07:59로 옮긴다.

    정책: 'day_specific'(그날 실제 과도분의 s 비율, 사후 최적 성격) / 'fixed_pretest'(시험 전 중앙 과도분 m의 s 비율을
    구간별 상한으로 고정, 표본 외 적용). hold = 앞당겨 켠 설비의 유지 부하(07:15~07:59 구간당 추가, 0·5·10).
    """
    y = iv["y"]
    st = F.schedule_table(iv)
    ymat = y.to_numpy().reshape(-1, 96)
    dates = pd.DatetimeIndex(st.index)
    ok_day = [i for i, d in enumerate(dates) if st["regime"].iloc[i] == 2 and st["daytype3"].iloc[i] == 0
              and np.isfinite(ymat[i]).sum() >= 90]
    pre = [i for i in ok_day if dates[i] < C.TEST_START]
    m_fixed = float(np.median([np.nanmax(np.clip(ymat[i][32:36] - _plateau(ymat[i]), 0, None)) for i in pre]))
    rows = []
    for i in ok_day:
        d = dates[i]
        v = ymat[i].copy()
        plateau = _plateau(v)
        exc = np.clip(v[32:36] - plateau, 0, None)
        for policy in ("day_specific", "fixed_pretest"):
            for s in (0.5, 1.0):
                for hold in (0.0, 5.0, 10.0):
                    w = v.copy()
                    move = exc * s if policy == "day_specific" else np.minimum(exc, m_fixed * s)
                    w[32:36] -= move
                    w[29:32] += move.sum() / 3 + hold
                    rows.append(dict(date=d, month=d.month, period="test" if d >= C.TEST_START else "pre_test",
                                     policy=policy, share=s, hold=hold, daymax_before=float(np.nanmax(v)),
                                     daymax_after=float(np.nanmax(w)), reduction=float(np.nanmax(v) - np.nanmax(w)),
                                     moved_energy=float(move.sum())))
    dd = pd.DataFrame(rows)
    mon = dd.groupby(["policy", "share", "hold", "month"]).agg(
        days=("date", "count"), mean_daily_reduction=("reduction", "mean"), days_worse=("reduction", lambda v: int((v < 0).sum())),
        month_max_before=("daymax_before", "max"), month_max_after=("daymax_after", "max")).reset_index()
    mon["month_max_reduction"] = mon["month_max_before"] - mon["month_max_after"]
    return dd, mon, m_fixed


def apply_staggering(y: np.ndarray, iv: pd.DataFrame, m_fixed: float, s: float = 0.5, hold: float = 0.0,
                     only_days=None) -> np.ndarray:
    """고정 정책을 전면 가동 평일(only_days가 있으면 그 날짜만)에 적용한 시계열."""
    st = F.schedule_table(iv)
    Y = y.reshape(-1, 96).copy()
    dates = pd.DatetimeIndex(st.index)
    only = None if only_days is None else set(pd.DatetimeIndex(only_days))
    for i in range(len(Y)):
        if not (st["regime"].iloc[i] == 2 and st["daytype3"].iloc[i] == 0) or np.isfinite(Y[i]).sum() < 90:
            continue
        if only is not None and dates[i] not in only:
            continue
        v = Y[i]
        exc = np.clip(v[32:36] - _plateau(v), 0, None)
        move = np.nan_to_num(np.minimum(exc, m_fixed * s))
        v[32:36] -= move
        v[29:32] += move.sum() / 3 + hold
    return Y.ravel()


# ---------------------------------------------------------------- 냉방·야간 이동

def apply_precool(y: np.ndarray, iv: pd.DataFrame, slope: float, c: float, base_temp: float = 28.0,
                  months=(7, 8, 9)) -> np.ndarray:
    """전면 가동일 11~16시: 최고기온이 base_temp를 넘는 만큼 slope×초과°C×c를 줄이고 그 에너지를 05~06시에 더한다."""
    st = F.schedule_table(iv)
    Y = y.reshape(-1, 96).copy()
    tmax = iv["temp"].groupby(iv.index.normalize()).max()
    dates = pd.DatetimeIndex(st.index)
    for i, d in enumerate(dates):
        if st["regime"].iloc[i] != 2 or d.month not in months:
            continue
        ex = max(float(tmax.get(d, np.nan)) - base_temp, 0.0)
        if not np.isfinite(ex) or ex <= 0:
            continue
        cut = slope * ex * c
        blk = slice(44, 68)
        okb = np.isfinite(Y[i, blk])
        e = cut * okb.sum()
        Y[i, blk] = Y[i, blk] - cut
        Y[i, 20:28] = Y[i, 20:28] + e / 8
    return Y.ravel()


def cooling_scenario(iv: pd.DataFrame, slope: dict, base_temp: float = 28.0) -> pd.DataFrame:
    """7~9월(7월은 기울기 추정 구간, 8·9월은 표본 외) 월 최대 변화. 기울기는 점추정·90% 구간 하한·상한."""
    y = np.where(iv["usable"].to_numpy(), iv["y"].to_numpy(), np.nan)
    base = monthly_max(y, iv.index)
    rows = []
    for sname in ("slope", "lo", "hi"):
        sl = slope[sname]
        for c in (0.3, 0.5):
            y2 = apply_precool(y, iv, sl, c, base_temp)
            after = monthly_max(y2, iv.index)
            for m in (7, 8, 9):
                rows.append(dict(slope_variant=sname, slope_per_C=sl, share_reducible=c, month=m, base_temp=base_temp,
                                 period="test" if m >= 8 else "pre_test(slope fitted)",
                                 month_max_before=base.get(m), month_max_after=after.get(m),
                                 month_max_reduction=base.get(m, np.nan) - after.get(m, np.nan)))
    return pd.DataFrame(rows)


def night_shift_scenario(iv: pd.DataFrame) -> pd.DataFrame:
    """전면 가동일 09~16시 가동 부하(고원 − 대기 22)의 k%를 같은 날 20~23시로 옮기는 산술 시나리오(설비 kW 자료 없음)."""
    y = np.where(iv["usable"].to_numpy(), iv["y"].to_numpy(), np.nan)
    st = F.schedule_table(iv)
    Y = y.reshape(-1, 96)
    dates = pd.DatetimeIndex(st.index)
    rows = []
    for k in (0.05, 0.10, 0.20):
        Z = Y.copy()
        for i in range(len(Z)):
            if st["regime"].iloc[i] != 2 or np.isfinite(Z[i]).sum() < 90:
                continue
            blk = slice(36, 68)
            mv = np.clip(Z[i, blk] - 22.0, 0, None) * k
            Z[i, blk] = Z[i, blk] - mv
            Z[i, 80:96] = Z[i, 80:96] + np.nansum(mv) / 16
        before, after = monthly_max(y, iv.index), monthly_max(Z.ravel(), iv.index)
        night_before = pd.Series(Y[:, 80:96].max(axis=1), index=dates)
        night_after = pd.Series(Z[:, 80:96].max(axis=1), index=dates)
        for m in (6, 7, 8, 9):
            mm = dates.month == m
            rows.append(dict(moved_share=k, month=m, month_max_before=before.get(m), month_max_after=after.get(m),
                             month_max_reduction=before.get(m, np.nan) - after.get(m, np.nan),
                             night_max_before=float(np.nanmax(night_before[mm])), night_max_after=float(np.nanmax(night_after[mm]))))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 경보 등급

GRADES = [(0.0, 0.2, "정상", "조치 없음", "-", "-"),
          (0.2, 0.5, "주의", "다음 1시간 기동 예정 설비 확인·대기", "현장 반장", "기동 예정 설비 목록, 현재 부하"),
          (0.5, 0.8, "경계", "비필수 부하(공조 설정·보조 설비) 준비, 동시 기동 금지", "설비 담당", "동시 기동 여부, 공조 설정온도"),
          (0.8, 1.01, "심각", "제어 가능 부하 차단·기동 지연(≤30분), 수요 담당자 통보", "에너지(수요) 담당", "차단 부하·회복 계획, 월 누적 최대")]
HOLD_INTERVALS = 2  # 히스테리시스: 등급을 내릴 때는 2구간(30분) 연속 아래 등급이어야 한다


def grade_sequence(p: np.ndarray, hold: int = HOLD_INTERVALS) -> np.ndarray:
    raw = np.digitize(np.nan_to_num(p), [0.2, 0.5, 0.8])
    out = raw.copy()
    below = 0
    for i in range(1, len(raw)):
        if raw[i] >= out[i - 1]:
            out[i] = raw[i]
            below = 0
        else:
            below += 1
            out[i] = raw[i] if below >= hold else out[i - 1]
            if below >= hold:
                below = 0
    return out


def alarm_grades(iv: pd.DataFrame, selection: dict, T_fixed: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """확률 구간별 실제 초과 빈도(보정 근거)·조치·담당·확인 항목, 가동일당 부담(히스테리시스 적용).

    T_fixed가 없으면 폴드별 q95(운전 상태 표시용), 있으면 요금 수준 목표(예: 시험 전 최대의 95%)로 계산한다."""
    y = iv["y"]
    idx = iv.index
    st = F.schedule_table(iv)
    grp = PK.target_window_groups(PK.regime(iv, st["regime"]))
    mA = selection["A"]["chosen"]
    preds_h = {h: SP.honest_stream(f"A{h}", mA).reindex(idx) for h in range(1, 5)}
    labels = PK.next_hour_labels(y, iv["usable"].to_numpy())
    rows, burden = [], []
    for name, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        T = CV.peak_threshold(iv, s) if T_fixed is None else T_fixed
        p = PK.next_hour_prob(idx, preds_h, y, T, grp).to_numpy()
        m = (idx >= s) & (idx < e) & labels["valid"].to_numpy() & np.isfinite(p)
        lab = labels["max_next"].to_numpy() >= T
        per = "test" if name == "test" else "cv"
        for lo, hi, g, act, owner, check in GRADES:
            b = m & (p >= lo) & (p < hi)
            rows.append(dict(period=per, fold=name, grade=g, p_lo=lo, p_hi=hi, n=int(b.sum()), exceed=int((lab & b).sum()),
                             action=act, owner=owner, check_items=check))
        # 부담: 가동일(전면 가동)만, 히스테리시스 등급
        pm = (idx >= s) & (idx < e) & np.isfinite(p)
        gseq = grade_sequence(np.where(pm, p, 0.0))
        days = pd.DatetimeIndex(np.unique(idx[pm].normalize()))
        wd = days[(st["regime"].reindex(days) == 2).to_numpy()]
        for k, gname in ((1, "주의 이상"), (2, "경계 이상"), (3, "심각")):
            on = pm & (gseq >= k) & np.isin(idx.normalize(), wd)
            ep = int(np.sum(on[1:] & ~on[:-1]) + (1 if on[0] else 0))
            first_times = []
            for d in wd:
                dm = on & (idx.normalize() == d)
                if dm.any():
                    first_times.append(idx[dm][0].hour * 60 + idx[dm][0].minute)
            burden.append(dict(period=per, fold=name, level=gname, workdays=len(wd),
                               hours_per_workday=float(on.sum()) * 0.25 / max(len(wd), 1),
                               episodes_per_workday=ep / max(len(wd), 1),
                               share_workdays_first_alarm_0715_0745=float(np.mean([(435 <= t <= 465) for t in first_times]))
                               if first_times else np.nan))
    t = pd.DataFrame(rows)
    agg = t.groupby(["period", "grade", "p_lo", "p_hi", "action", "owner", "check_items"], sort=False)[["n", "exceed"]].sum().reset_index()
    agg["observed_rate"] = agg["exceed"] / agg["n"].replace(0, np.nan)
    bd = pd.DataFrame(burden)
    bagg = bd.groupby(["period", "level"], sort=False).apply(
        lambda g: pd.Series({"workdays": g["workdays"].sum(),
                             "hours_per_workday": np.average(g["hours_per_workday"], weights=g["workdays"]),
                             "episodes_per_workday": np.average(g["episodes_per_workday"], weights=g["workdays"]),
                             "share_workdays_first_alarm_0715_0745": np.nanmean(g["share_workdays_first_alarm_0715_0745"])}),
        include_groups=False).reset_index()
    return agg, bagg


# ---------------------------------------------------------------- 통합 운영 절차

OPERATING_PROCEDURE = [
    ("D-1 17:00", "익일 96구간 예측(과제 B)·일 최대 초과확률, 익일 예보 최고기온",
     "래칫 대상 월(12·1·2·7·8·9월)이면 P(일 최대 ≥ 현재 요금적용전력 − 5) ≥ τ(7월 교차검증 F1)인 날을 위험일로 표시. "
     "예보 최고기온 > 28°C인 전면 가동일",
     "위험일: 수요 담당 대기·통보(준비 행동). 더운 날: 사전 냉방 예약(05~06시)", "생산관리·설비 담당",
     "위험일 적중·순위, 예측 일 최대 오차", "③ 사전 냉방(위험일 표시는 준비 행동이라 시뮬레이션하지 않음)"),
    ("당일 07:00~09:00", "상시 규칙", "전면 가동 평일(매일)", "순차·선행 기동(시험 전 중앙 과도분의 50%를 07:15~07:59로 분산)",
     "현장 반장", "기동 과도분, 08시대 최대", "② 순차 기동"),
    ("당일 매 15분", "다음 1시간 최대 초과확률(과제 A·C, 요금 목표 = 시험 전 최대의 95%)",
     "확률 ≥ τ(교차검증에서 가동일당 개입 예산 안에서 고름)이면 차단. 등급 주의 0.2/경계 0.5/심각 0.8은 표시·준비용"
     "(심각 = 준비·통보), 내릴 때 30분 유지",
     "제어 가능 부하 ≤30분 차단. 미룬 부하는 직전 구간의 차단 전 수요와 그 구간 익일 예측이 모두 회복분을 더해도 목표 − 5 "
     "이하일 때만 풀고, 4시간 안에 못 풀면 그날 20~23시에 나눠 만회", "에너지(수요) 담당", "경보 시간/가동일, 선행시간, 목표 초과 구간",
     "④ 수요제어"),
    ("당일 15분 창 안", "현재 15분 창의 누적 수요(수요제어기)", "창 끝 예상 수요가 목표를 넘거나 설비가 동시에 재기동하려 하면",
     "동시 기동 인터록(설비 재기동 순서 관리)·즉시 차단 — 전날 예측이 불가능한 한 구간 스파이크 대응", "설비 담당",
     "스파이크 건수, 창별 최대", "① 인터록(가정 상한: 한 구간 스파이크를 이웃 최대로 묶음)"),
    ("월중 매일", "월 누적 최대·요금적용전력", "월 누적 최대가 요금적용전력 − 5에 근접",
     "다음 날 위험일 문턱 하향·수요제어 목표 재설정", "에너지(수요) 담당", "요금적용전력 변화", "시뮬레이션 밖(운영 규칙)"),
]


def _stagger_days(iv: pd.DataFrame, only_days=None) -> int:
    """apply_staggering이 실제로 적용되는 날짜 수(전면 가동 평일, 유효 구간 ≥90, only_days 제한)."""
    st = F.schedule_table(iv)
    ymat = iv["y"].to_numpy().reshape(-1, 96)
    dates = pd.DatetimeIndex(st.index)
    only = None if only_days is None else set(pd.DatetimeIndex(only_days))
    return int(sum(1 for i, d in enumerate(dates) if st["regime"].iloc[i] == 2 and st["daytype3"].iloc[i] == 0
                   and np.isfinite(np.where(iv["usable"].to_numpy().reshape(-1, 96)[i], ymat[i], np.nan)).sum() >= 90
                   and (only is None or d in only)))


def _precool_days(iv: pd.DataFrame, base_temp: float = 28.0, months=(7, 8, 9)) -> int:
    """apply_precool이 실제로 적용되는 날짜 수(7~9월 전면 가동일 중 최고기온 > base_temp)."""
    st = F.schedule_table(iv)
    tmax = iv["temp"].groupby(iv.index.normalize()).max()
    return int(sum(1 for i, d in enumerate(pd.DatetimeIndex(st.index))
                   if st["regime"].iloc[i] == 2 and d.month in months and tmax.get(d, np.nan) > base_temp))


def _ratchet_setter(yy: np.ndarray, idx: pd.DatetimeIndex, spike_jump: float = SPIKE_JUMP) -> dict:
    """7~9월 최대(래칫)를 정하는 구간의 날짜·시각·유형."""
    m = (idx >= RATCHET_FIRST_IN_DATA) & (idx < C.TEST_END) & np.isfinite(yy)
    if not m.any():
        return {}
    k = np.flatnonzero(m)[int(np.nanargmax(yy[m]))]
    nb = np.nanmax([yy[k - 1] if k > 0 else np.nan, yy[k + 1] if k + 1 < len(yy) else np.nan])
    ts = idx[k]
    return {"ratchet_setter": ts.strftime("%m/%d %H:%M"),
            "ratchet_setter_type": event_type(float(yy[k] - nb), ts.hour * 4 + ts.minute // 15, spike_jump)}


def integrated_scenario(ctx: _Ctx, m_fixed: float, slope: float, risk_days) -> pd.DataFrame:
    """운영 절차(OPERATING_PROCEDURE)와 같은 정책의 누적. 모델이 필요 없는 상시 대책을 먼저, 모델 대책을 마지막에 쌓는다
    (모델의 추가 기여를 보수적으로 본다).
    ① 동시 기동 인터록(가정 상한: 앞뒤보다 SPIKE_JUMP 이상 높은 한 구간을 이웃 최대로 묶음, 절차 4행)
    ② 순차 기동(매 전면 가동 평일, 시험 전 고정 정책 50%, 절차 2행)
    ③ 사전 냉방(7~9월 전면 가동일 중 최고기온 > 28°C, c=0.3, 7월은 기울기 추정 구간이라 표본 내, 절차 1행)
    ④ 수요제어(목표 0.95×시험 전 최대, r=10%, τ는 교차검증, 측정 기반 회복, 절차 3행). 확률은 원래 부하의 예측 흐름(근사).
    비교 행: 인터록 없이 순차 기동만, 순차 기동을 위험일(7월 교차검증 τ 규칙)에만, 인터록 문턱 10·20.
    결과는 월 최대, 7~9월 최대(다음 12개월 기본요금 기준)의 변화 %, 래칫을 정하는 구간(날짜·시각·유형)."""
    iv = ctx.iv
    idx = ctx.idx
    y0 = ctx.yfill.copy()
    rd = pd.DatetimeIndex(risk_days)
    y1, n_lock = apply_interlock(y0)
    y2 = apply_staggering(y1, iv, m_fixed, 0.5)
    y3 = apply_precool(y2, iv, slope, 0.3) if np.isfinite(slope) and slope > 0 else y2
    T = targets_from_pretest(iv, (0.95,))[0]
    tau = choose_tau(ctx, T, 0.10, "valley_capped")
    room = np.full(len(y3), T - ROOM_MARGIN)
    y4, info = _run_policy(y3, ctx.prob(T) >= tau, 0.10, "valley_capped", ctx.valley, room=room, slot=ctx.slot,
                           forecast=ctx.predB)
    n_work = _stagger_days(iv)
    steps = [("기준(대책 없음)", y0, 0, ""),
             (f"① + 인터록(가정 상한, 스파이크 ≥{SPIKE_JUMP:g})", y1, n_lock, "구간"),
             ("② + 순차 기동(매 전면 가동 평일)", y2, n_work, "가동일"),
             ("③ + 사전 냉방(c=0.3, 7월은 표본 내)", y3, _precool_days(iv) if y3 is not y2 else 0, "일"),
             (f"④ + 수요제어(목표 {T}, τ={tau}, 측정 기반 회복)", y4, info["episodes"], "차단 에피소드")]
    steps.append(("(비교) 순차 기동만(매 전면 가동 평일, 인터록 없음)", apply_staggering(y0, iv, m_fixed, 0.5), n_work, "가동일"))
    steps.append(("(비교) 인터록 + 위험일만 순차 기동(7월 교차검증 τ 규칙)", apply_staggering(y1, iv, m_fixed, 0.5, only_days=rd),
                  _stagger_days(iv, rd), "가동일"))
    for sj in SPIKE_JUMP_SWEEP:
        if sj != SPIKE_JUMP:
            yl, nl = apply_interlock(y0, sj)
            steps.append((f"(비교) 인터록만(스파이크 ≥{sj:g})", yl, nl, "구간"))
    rows = []
    base = monthly_max(y0, idx)
    for name, yy, nint, unit in steps:
        mm = monthly_max(yy, idx)
        bill = billing_demand(mm)
        rows.append(dict(scenario=name, interventions=nint, intervention_unit=unit,
                         **{f"month_max_{m}": mm.get(m) for m in (5, 6, 7, 8, 9)},
                         ratchet_max_jul_sep=ratchet_max(mm), ratchet_change=ratchet_max(mm) - ratchet_max(base),
                         basic_charge_change_pct=(ratchet_max(mm) - ratchet_max(base)) / ratchet_max(base) * 100,
                         billing_demand_sep=bill.get(9), **_ratchet_setter(yy, idx)))
    return pd.DataFrame(rows)


def spike_jump_sensitivity(iv: pd.DataFrame) -> pd.DataFrame:
    """사건 유형의 SPIKE_JUMP 민감도(10·15·20): 상위 사건의 유형이 바뀌는가(7/19 11:15는 +15.0 경계 사례)."""
    return pd.concat([ratchet_events(iv, spike_jump=sj) for sj in SPIKE_JUMP_SWEEP], ignore_index=True)


def _require(*rels):
    """산출물을 하나라도 쓰기 전에 선행 산출물(outputs/·artifacts/)을 모두 확인한다."""
    miss = [r for r in rels if not (C.OUTPUT_DIR / r).exists()]
    miss += [f"artifacts/{n}_{t}.csv.gz" for n in ("oof", "test") for t in ("B", "A1", "A2", "A3", "A4")
             if not (C.ARTIFACT_DIR / f"{n}_{t}.csv.gz").exists()]
    if miss:
        raise FileNotFoundError(f"field 단계 선행 산출물이 없다: {miss} — models·peak·analysis 단계를 먼저 실행한다")


def run(iv: pd.DataFrame, frames: dict, selection: dict) -> dict:
    _require("peak/peak_summary.json", "analysis/peak_conditions.json")
    od = io.out_dir("field")
    ctx = _Ctx(iv, selection)
    targets = targets_from_pretest(iv)
    dc, taus = demand_controller(ctx, targets)
    io.write_csv(dc, od / "demand_controller.csv")
    io.write_csv(controller_pareto(ctx, targets_from_pretest(iv, (0.92,))[0]), od / "demand_controller_pareto.csv")
    io.write_csv(controller_sensitivity(ctx), od / "demand_controller_sensitivity.csv")
    io.write_json({"targets": list(targets), "target_fractions_of_pretest_max": list(TARGET_FRACTIONS),
                   "pretest_max": pretest_max(iv), "budget_episodes_per_workday": BUDGET_EPISODES_PER_WORKDAY,
                   "tau_by_setting_chosen_on_cv_budget": taus,
                   "note": ("S7 수요제어 설계(차단 30분·회복 방식)는 첫 구현 결함을 시험 결과로 발견한 뒤 수정한 사후 설계다. "
                            "목표는 시험 전 최대의 비율, τ는 교차검증(6·7월)에서 가동일당 개입 예산 안에서 고른다. "
                            "'되돌림 없음'은 상한 성격의 가정이고, 목표 비율·차단·회복 길이 민감도도 사후 설계다. "
                            "v2.3: 측정 기반 회복(valley_capped)의 판정을 차단 전 수요와 익일 예측(둘 다 여유일 때만)으로 바꾸고 창 밖 "
                            "잔여분을 그날 20~23시에 나눠 만회하도록 고쳤다(3차 검수에서 7월 사례와 합성 예로 찾은 설계 결함, 시험 결과로 "
                            "고른 것이 아님). τ는 같은 교차검증 규칙으로 다시 골랐다.")},
                  od / "demand_controller_settings.json")
    dd, mon, m_fixed = startup_staggering(iv)
    io.write_csv(dd, od / "startup_staggering_days.csv")
    io.write_csv(mon, od / "startup_staggering_monthly.csv")
    pc = json.loads((C.OUTPUT_DIR / "analysis" / "peak_conditions.json").read_text(encoding="utf-8"))
    sl = pc.get("plateau_slope_per_C_summer_pre_test", {})
    slope = {"slope": sl.get("slope", np.nan), "lo": (sl.get("ci90") or [np.nan, np.nan])[0],
             "hi": (sl.get("ci90") or [np.nan, np.nan])[1]}
    if np.isfinite(slope["slope"]) and slope["slope"] > 0:
        slope["lo"] = max(slope["lo"], 0.0)
        io.write_csv(cooling_scenario(iv, slope), od / "cooling_scenario.csv")
    io.write_csv(night_shift_scenario(iv), od / "night_shift_scenario.csv")
    grades, burden = alarm_grades(iv, selection)
    io.write_csv(grades, od / "alarm_grades.csv")
    io.write_csv(burden, od / "alarm_burden.csv")
    Tb = targets_from_pretest(iv, (0.95,))[0]
    gb, bb = alarm_grades(iv, selection, T_fixed=Tb)
    io.write_csv(gb.assign(T=Tb), od / "alarm_grades_billing_target.csv")
    io.write_csv(bb.assign(T=Tb), od / "alarm_burden_billing_target.csv")
    # 요금적용전력(래칫)
    y0 = np.where(iv["usable"].to_numpy(), iv["y"].to_numpy(), np.nan)
    mm = monthly_max(y0, iv.index)
    io.write_json({"month_max": mm, "billing_demand": billing_demand(mm), "ratchet_max_jul_sep": ratchet_max(mm),
                   "rule": "요금적용전력 = max(당월, 직전 12개월 중 12·1·2·7·8·9월 최대수요). 자료 밖(2020년) 달은 알 수 없어 제외",
                   "m_fixed_startup_excess_pretest_median": m_fixed},
                  od / "billing_ratchet.json")
    io.write_csv(ratchet_events(iv), od / "ratchet_events.csv")
    io.write_csv(spike_jump_sensitivity(iv), od / "ratchet_events_spike_jump_sensitivity.csv")
    lad, ub = ratchet_ladder(iv)
    io.write_csv(lad, od / "ratchet_ladder.csv")
    io.write_csv(ub, od / "ratchet_perfect_control_bound.csv")
    rd, rres = ratchet_risk_days(iv, selection)
    io.write_csv(rd, od / "ratchet_risk_days.csv")
    io.write_json(rres, od / "ratchet_risk_days_summary.json")
    risk_days = rd.loc[(rd["flag"] == 1), "date"] if len(rd) else []  # 운영 규칙(7월 τ, D-1 17:00 실행 가능)
    io.write_csv(integrated_scenario(ctx, m_fixed, slope["slope"], risk_days), od / "integrated_scenario.csv")
    io.write_csv(pd.DataFrame(OPERATING_PROCEDURE, columns=["when", "input", "decision_rule", "action", "owner", "kpi",
                                                            "scenario_step"]), od / "operating_procedure.csv")
    return {"taus": taus}
