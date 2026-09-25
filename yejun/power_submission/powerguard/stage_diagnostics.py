"""S1 데이터 진단 산출물."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from . import features as F
from . import io


def run(df: pd.DataFrame, meta: dict, diag: D.Diagnosis, iv: pd.DataFrame) -> dict:
    od = io.out_dir("diagnostics")
    days = diag.days.copy()
    days["daytype3"] = F.daytype3(pd.DatetimeIndex(days.index))
    days["daytype4"] = F.daytype4(pd.DatetimeIndex(days.index))
    days["usable_day"] = iv.groupby("date")["usable"].any().reindex(days.index).to_numpy()
    days["usable_intervals"] = iv.groupby("date")["usable"].sum().reindex(days.index).to_numpy()
    io.write_csv(days.reset_index(), od / "days.csv")
    io.write_csv(diag.copied[["date", "power_src", "src_same_weekday", "src_same_dom", "prod_total", "power_mean"]],
                 od / "copy_map.csv")
    io.write_csv(diag.contradictions, od / "copy_contradictions.csv")
    # 전력 0 구간(정전/무계측): 원본 값은 쓰지 않고 연속 구간의 시작·끝·구간 수만 기록
    z = iv["outage"].to_numpy()
    spans, k = [], 0
    while k < len(z):
        if z[k]:
            j = k
            while j + 1 < len(z) and z[j + 1]:
                j += 1
            spans.append(dict(start=iv.index[k], end=iv.index[j] + pd.Timedelta(minutes=15), n_intervals=j - k + 1,
                              weekday=int(iv.index[k].dayofweek)))
            k = j + 1
        else:
            k += 1
    io.write_csv(pd.DataFrame(spans), od / "outage_spans.csv")
    io.write_csv(diag.missing, od / "missing.csv")
    if diag.hour_copies is not None:
        io.write_csv(diag.hour_copies, od / "hour_copies.csv")

    # 사용 가능 구간 요약
    u = iv[iv["usable"]]
    split = pd.Series(np.where(u.index < C.TEST_START, "train_pool", "test"), index=u.index)
    usable_summary = {
        "usable_days": int(days["usable_day"].sum()),
        "usable_intervals": int(iv["usable"].sum()),
        "usable_days_before_test": int(days.loc[days.index < C.TEST_START, "usable_day"].sum()),
        "usable_days_test": int(days.loc[days.index >= C.TEST_START, "usable_day"].sum()),
        "test_intervals_usable": int((split == "test").sum()),
        "trainable_intervals": int(iv["trainable"].sum()),
        "outage_intervals": int(iv["outage"].sum()),
        "excluded_intervals": {
            "copied": int(iv["copied"].sum()),
            "partial_copy": int(iv["partial_copy"].sum()),
            "corrupt": int(iv["corrupt"].sum()),
            "outage": int(iv["outage"].sum()),
            "hour_copy": int(iv["hour_copy"].sum()),
            "regime_mismatch_train_only": int((iv["usable"] & ~iv["trainable"]).sum()),
        },
    }

    # 가동일(원본·평일·생산 계획 ≥5000) 슬롯 프로파일과 일 최대 발생 슬롯
    st = F.schedule_table(iv)
    u2 = iv[iv["trainable"]].copy()
    u2["daytype4"] = F.daytype4(u2.index.normalize())
    u2["regime"] = st["regime"].reindex(u2.index.normalize()).to_numpy()
    prof = u2.groupby(["daytype4", "regime", "slot"])["y"].agg(["mean", "std", "count"]).reset_index()
    io.write_csv(prof, od / "slot_profile.csv")
    work_days = days.index[(days["usable_day"]) & (days["daytype3"] == 0) & (days["prod_total"] >= 5000)
                           & (~days["regime_mismatch"])]
    w = u2[u2.index.normalize().isin(work_days)]
    dmax_slot = w.groupby(w.index.normalize())["y"].idxmax()
    peak_slot = pd.Series([t.hour * 4 + t.minute // 15 for t in dmax_slot], name="slot")
    pk = peak_slot.value_counts().sort_index().rename("n_days").reset_index()
    pk["time"] = [f"{s // 4:02d}:{(s % 4) * 15:02d}" for s in pk["slot"]]
    io.write_csv(pk, od / "daily_max_slot_workdays.csv")
    g = w.pivot_table(index=w.index.normalize(), columns="slot", values="y")
    startup_excess = (g.loc[:, 33:35].max(axis=1) - g.loc[:, 36:43].mean(axis=1)).dropna()

    thr = float(np.quantile(iv.loc[iv.index < C.TEST_START, "y_train"].dropna(), C.PEAK_Q))
    month_share = pd.Series(peak_slot.between(30, 35).to_numpy(),
                            index=[t.month for t in dmax_slot.index]).groupby(level=0).mean()
    peak_summary = {
        "T_q95_train_pool": thr,
        "workdays": int(len(work_days)),
        "daily_max_in_0730_0859_share_by_month": {int(k): round(float(v), 3) for k, v in month_share.items()},
        "daily_max_in_0815_0900_share": float(peak_slot.between(33, 35).mean()),
        "startup_excess_median": float(startup_excess.median()),
        "startup_excess_iqr": [float(startup_excess.quantile(0.25)), float(startup_excess.quantile(0.75))],
    }
    # 시험 기간 구성(휴가·휴일)
    test_days = days[days.index >= C.TEST_START]
    test_summary = {
        "test_days": int(len(test_days)),
        "test_plan_zero_days": [str(d.date()) for d in test_days.index[test_days["prod_total"] == 0]],
        "test_holidays": [str(d.date()) for d in test_days.index[test_days["holiday"]]],
    }
    summary = {"meta": meta, "diagnosis": diag.summary, "usable": usable_summary, "peak": peak_summary,
               "test_composition": test_summary}
    io.write_json(summary, od / "summary.json")
    return summary
