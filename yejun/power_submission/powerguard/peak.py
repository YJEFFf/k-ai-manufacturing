"""피크 위험 확률·예측구간·경보·사건 평가.

잔차 기반 예측분포: 점예측 ŷ에 과거의 '정직한'(학습에 쓰이지 않은 OOF·시험 온라인) 잔차를 더해 분포를 만든다.
- 보정 창: 발행일 이전의 최근 W일(정답 사용 가능일) 잔차만 사용한다(시간 국소 split conformal).
- Mondrian 그룹: 가동 조건(가동일×주간 08~20시) / 그 외. 그룹별로 잔차를 따로 쓴다.
- 다음 1시간 최대(과제 C-A): 네 지평 잔차 벡터를 함께 뽑아 지평 간 상관을 보존한다.
- 익일 최대(과제 C-B): 과거 날짜의 96구간 잔차 벡터를 통째로 더한다.
확률적 보장을 주장하지 않는다(시간 의존·분포 변화).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

STEPS = 96


def regime(iv: pd.DataFrame, plan_class: pd.Series) -> np.ndarray:
    """1 = 가동일(계획 등급 2)의 08~20시, 0 = 그 외."""
    pc = plan_class.reindex(iv.index.normalize()).to_numpy()
    return ((pc == 2) & (iv["hour"].to_numpy() >= 8) & (iv["hour"].to_numpy() < 20)).astype(int)


def _day_index(index: pd.DatetimeIndex) -> np.ndarray:
    return ((index.normalize() - index[0].normalize()).days).to_numpy()


# ---------------------------------------------------------------- 예측구간

def rolling_intervals(y: pd.Series, pred: pd.Series, groups: np.ndarray, alpha: float, window_days: int = 21,
                      min_n: int = 50, aci_gamma: float | None = None, eval_mask: np.ndarray | None = None,
                      known_before: pd.Timedelta = pd.Timedelta(minutes=60)) -> pd.DataFrame:
    """날짜 순으로 진행하며 D일 구간은 'D일 첫 발행 시각'에 이미 끝난 목표의 잔차로 만든다.

    known_before: D 00:00 기준 첫 발행이 얼마나 앞서는가(과제 A 최대 60분, 과제 B D-1 17:00 = 7시간).
    적응형 conformal(aci_gamma)의 날짜별 오포함률도 그 날의 모든 목표가 끝난 뒤(= 발행 시각 이전)에만 반영한다.
    """
    idx = y.index
    day = _day_index(idx)
    day0 = idx.normalize()
    resid = (y - pred).to_numpy()
    ok = np.isfinite(resid)
    ends = idx + pd.Timedelta(minutes=15)
    lo = np.full(len(y), np.nan)
    hi = np.full(len(y), np.nan)
    a_t = {g: alpha for g in np.unique(groups)}
    pending: list[tuple[pd.Timestamp, int, float]] = []  # (그 날 마지막 목표의 끝, 그룹, 오포함률)
    pv = pred.to_numpy()
    days = np.unique(day[np.isfinite(pv)])
    for d in days:
        today = (day == d) & np.isfinite(pv)
        d_start = day0[today][0]
        cutoff = d_start - known_before
        if aci_gamma is not None:
            ready = [q for q in pending if q[0] <= cutoff]
            pending = [q for q in pending if q[0] > cutoff]
            for _, g, miss in ready:
                a_t[g] = a_t[g] + aci_gamma * (alpha - miss)
        past = ok & (ends <= cutoff) & (idx >= d_start - pd.Timedelta(days=window_days))
        for g in np.unique(groups):
            tg = today & (groups == g)
            if not tg.any():
                continue
            r = resid[past & (groups == g)]
            if r.size < min_n:
                r = resid[past]
            if r.size < min_n:
                continue
            a = min(max(a_t[g], 1e-3), 0.999)
            ql, qh = np.quantile(r, [a / 2, 1 - a / 2])
            lo[tg] = pv[tg] + ql
            hi[tg] = pv[tg] + qh
            if aci_gamma is not None:
                obs = tg & ok & (eval_mask if eval_mask is not None else True)
                if obs.any():
                    yy = y.to_numpy()[obs]
                    pending.append((d_start + pd.Timedelta(days=1), g,
                                    float(np.mean((yy < lo[obs]) | (yy > hi[obs])))))
    return pd.DataFrame({"lo": lo, "hi": hi}, index=idx)


# ---------------------------------------------------------------- 다음 1시간 최대 초과확률

def target_window_groups(groups: np.ndarray) -> np.ndarray:
    """발행 구간 i의 그룹 = 목표 창(i+1..i+4) 중 하나라도 가동 주간이면 1."""
    g = pd.Series(groups.astype(float))
    return pd.concat([g.shift(-k) for k in range(1, 5)], axis=1).max(axis=1).fillna(0).astype(int).to_numpy()


def next_hour_labels(y: pd.Series, usable: np.ndarray) -> pd.DataFrame:
    """행 = 발행 구간 i. 목표 = i+1..i+4의 최대. 네 구간 모두 사용 가능할 때만 정의."""
    yv = y.to_numpy()
    n = len(yv)
    fut = np.full((n, 4), np.nan)
    okf = np.zeros((n, 4), bool)
    for h in range(1, 5):
        fut[: n - h, h - 1] = yv[h:]
        okf[: n - h, h - 1] = usable[h:]
    allok = okf.all(axis=1)
    mx = np.where(allok, np.nanmax(np.where(okf, fut, -np.inf), axis=1), np.nan)
    return pd.DataFrame({"max_next": mx, "valid": allok, "now": yv}, index=y.index)


def next_hour_prob(issue_index: pd.DatetimeIndex, preds_h: dict[int, pd.Series], y: pd.Series, T: float,
                   groups_issue: np.ndarray, window_days: int = 21, min_n: int = 50) -> pd.Series:
    """발행 구간 i의 P(max_{h=1..4} y_{i+h} ≥ T).

    preds_h[h]는 목표 구간 색인의 예측이므로 발행 구간 기준으로 h만큼 당겨 정렬한다.
    잔차 벡터 = 과거 발행 j의 (y_{j+h} − ŷ_{j+h})_{h=1..4}. 날짜 D의 첫 발행(i0)보다 먼저 네 목표가 모두 끝난
    벡터(j + 4 ≤ i0)만 쓴다. groups_issue는 target_window_groups로 만든 목표 창 기준 그룹을 권장한다.
    """
    n = len(issue_index)
    P = np.column_stack([preds_h[h].shift(-h).to_numpy() for h in range(1, 5)])
    Y = np.column_stack([y.shift(-h).to_numpy() for h in range(1, 5)])
    E = Y - P
    eok = np.isfinite(E).all(axis=1)
    pok = np.isfinite(P).all(axis=1)
    day = _day_index(issue_index)
    pos = np.arange(n)
    prob = np.full(n, np.nan)
    for d in np.unique(day[pok]):
        today = (day == d) & pok
        i0 = int(np.argmax(day == d))
        past = eok & (pos + 4 <= i0) & (day >= d - window_days)
        for g in np.unique(groups_issue):
            tg = today & (groups_issue == g)
            if not tg.any():
                continue
            r = E[past & (groups_issue == g)]
            if len(r) < min_n:
                r = E[past]
            if len(r) < min_n:
                continue
            sim = P[tg][:, None, :] + r[None, :, :]
            prob[tg] = (sim.max(axis=2) >= T).mean(axis=1)
    return pd.Series(prob, index=issue_index)


def day_max_prob(pred: pd.Series, y: pd.Series, usable: np.ndarray, T: float, day_class: pd.Series,
                 window_days: int = 28, min_days: int = 5, T_by_date: pd.Series | None = None):
    """D일 최대 ≥ T 확률과 슬롯별 초과확률. 같은 계획 등급 과거일의 96구간 잔차 벡터를 더한다.

    T_by_date가 있으면 날짜별 기준(예: 월 누적 최대)을 쓰고, 값이 없는 날은 건너뛴다.
    과거 잔차는 발행 시점(D-1 17:00)에 확정된 날(D-2 이전)만 쓴다.
    """
    dates = pd.DatetimeIndex(pred.index.normalize().unique())
    Pm = pred.to_numpy().reshape(-1, STEPS)
    Ym = y.to_numpy().reshape(-1, STEPS)
    Um = usable.reshape(-1, STEPS)
    Em = np.where(Um, Ym - Pm, np.nan)
    cls = day_class.reindex(dates).to_numpy()
    good_day = (np.isfinite(Em).sum(axis=1) >= 90)
    rows, slot_prob = [], np.full(Pm.shape, np.nan)
    for i, d in enumerate(dates):
        if not np.isfinite(Pm[i]).all():
            continue
        Td = T if T_by_date is None else T_by_date.get(d, np.nan)
        if not np.isfinite(Td):
            continue
        cand = [j for j in range(max(0, i - window_days), i - 1) if good_day[j] and cls[j] == cls[i]]
        if len(cand) < min_days:
            cand = [j for j in range(max(0, i - window_days), i - 1) if good_day[j]]
        if len(cand) < min_days:
            continue
        E = np.nan_to_num(Em[cand], nan=0.0)
        sim = Pm[i][None, :] + E
        p_day = float((sim.max(axis=1) >= Td).mean())
        slot_prob[i] = (sim >= Td).mean(axis=0)
        ymax = np.nanmax(np.where(Um[i], Ym[i], np.nan)) if Um[i].sum() >= 90 else np.nan
        rows.append(dict(date=d, p_daymax=p_day, pred_daymax=float(Pm[i].max()), y_daymax=ymax,
                         label=(ymax >= Td) if np.isfinite(ymax) else np.nan, n_cal_days=len(cand)))
    return pd.DataFrame(rows), pd.Series(slot_prob.ravel(), index=pred.index)


# ---------------------------------------------------------------- 경보·사건

def events(y: pd.Series, usable: np.ndarray, T: float, merge_gap: int = 1) -> pd.DataFrame:
    """T 이상 연속 구간을 사건으로 묶는다(merge_gap 구간 이하의 공백은 병합). 사용 불가 구간에서 끊는다."""
    hi = (y.to_numpy() >= T) & usable
    idx = np.where(hi)[0]
    ev = []
    if idx.size == 0:
        return pd.DataFrame(columns=["start", "end", "n", "start_ts", "peak"])
    s = p = idx[0]
    for k in idx[1:]:
        gap_ok = (k - p - 1) <= merge_gap and usable[p:k + 1].all()
        if gap_ok:
            p = k
        else:
            ev.append((s, p))
            s = p = k
    ev.append((s, p))
    yv = y.to_numpy()
    return pd.DataFrame([dict(start=a, end=b, n=b - a + 1, start_ts=y.index[a], peak=float(np.nanmax(yv[a:b + 1])))
                         for a, b in ev])


SCHEDULED_START_SLOTS = set(range(30, 36)) | {41, 42, 52, 53, 61, 62, 69, 70, 71}  # 기동·휴식 복귀 직후 시작


def evaluate_alarms(prob: pd.Series, labels: pd.DataFrame, y: pd.Series, usable: np.ndarray, T: float, tau: float,
                    mask: np.ndarray, merge_gap: int = 1) -> dict:
    """발행 구간 단위 F1과 사건 단위 탐지·선행시간·알림 부담.

    사건 시작 구간 s는 발행 구간 i ∈ [s−4, s−1]의 경보로 탐지된다(15~60분 전 발행 → 선행 0~45분).
    일정형 사건 = 기동(07:30~08:59)·휴식 복귀 직후에 시작한 사건, 그 외는 비일정형.
    경보 부담 = 에피소드 수와 경보가 켜져 있던 시간(시간/일).
    """
    p = prob.to_numpy()
    lab = labels["max_next"].to_numpy() >= T
    valid = labels["valid"].to_numpy() & np.isfinite(p) & mask
    alarm = (p >= tau) & valid
    tp = int((alarm & lab).sum())
    fp = int((alarm & ~lab).sum())
    fn = int((~alarm & lab & valid).sum())
    prec = tp / (tp + fp) if tp + fp else np.nan
    rec = tp / (tp + fn) if tp + fn else np.nan
    f1 = 2 * prec * rec / (prec + rec) if tp else 0.0
    ev = events(y, usable, T, merge_gap)
    slots = (y.index.hour * 4 + y.index.minute // 15).to_numpy()
    det, leads, n_ev = 0, [], 0
    by_type = {"scheduled": [0, 0], "unscheduled": [0, 0]}
    for _, e in ev.iterrows():
        s = int(e["start"])
        if s < 4 or not mask[s]:
            continue
        cand = np.arange(s - 4, s)
        if not valid[cand].any():
            continue
        n_ev += 1
        typ = "scheduled" if slots[s] in SCHEDULED_START_SLOTS else "unscheduled"
        by_type[typ][0] += 1
        hit = cand[alarm[cand]]
        if hit.size:
            det += 1
            by_type[typ][1] += 1
            leads.append((s - hit.min() - 1) * 15)
    ep, fep = 0, 0
    k = 0
    n = len(alarm)
    while k < n:
        if alarm[k]:
            j = k
            while j + 1 < n and alarm[j + 1]:
                j += 1
            ep += 1
            if not lab[k:j + 1].any():
                fep += 1
            k = j + 1
        else:
            k += 1
    ndays = len(np.unique(prob.index[valid].normalize()))
    return dict(tau=tau, n_issue=int(valid.sum()), pos=int((lab & valid).sum()), TP=tp, FP=fp, FN=fn,
                precision=prec, recall=rec, F1=f1, events=n_ev, events_detected=det,
                event_recall=det / n_ev if n_ev else np.nan,
                events_scheduled=by_type["scheduled"][0], detected_scheduled=by_type["scheduled"][1],
                events_unscheduled=by_type["unscheduled"][0], detected_unscheduled=by_type["unscheduled"][1],
                lead_median_min=float(np.median(leads)) if leads else np.nan, leads=leads,
                alarm_episodes=ep, false_episodes=fep, days=ndays,
                alarm_on_hours_per_day=float(alarm.sum()) * 0.25 / ndays if ndays else np.nan,
                episodes_per_day=ep / ndays if ndays else np.nan,
                false_episodes_per_day=fep / ndays if ndays else np.nan)
