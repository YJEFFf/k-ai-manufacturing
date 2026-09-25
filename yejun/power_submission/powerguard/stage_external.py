"""S7-외부: KAMP 추가 자료. 주 데이터와 결합하지 않고 출처·메커니즘·제약 근거로만 쓴다.

- #41 표면처리 자원최적화: #27에서 파생되었는지 행 대응으로 판정(외부 검증 제외 근거)
- #46 소성가공 자원최적화: 프레스·로봇 동시 기동과 15분 합성 피크, 기동 분산 효과의 표본 내/외 차이
- #30 생산계획 최적화: 같은 회사 NC 공정의 주문·가공시간으로 일정 이동 여력(설비 가동률)
"""
from __future__ import annotations

import hashlib
import io as _io
import zipfile

import numpy as np
import pandas as pd

from . import config as C
from . import io

ZIP_NAMES = {"41": "Dataset_표면처리 자원최적화 AI 데이터셋.zip", "46": "Dataset_소성가공 자원최적화 AI 데이터셋.zip",
             "30": "Dataset_생산계획 최적화 AI 데이터셋.zip", "27": "Dataset_자원 최적화 AI 데이터셋.zip"}


def _zip(key: str):
    return getattr(C, "KAMP_DIR", C.REPO_ROOT / "데이터셋") / ZIP_NAMES[key]


def _zip_members(path) -> dict:
    """ZIP 안 파일 이름은 cp437로 깨져 있을 수 있으므로 원래 바이트를 cp949로 복원한다."""
    out = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename
            if not (info.flag_bits & 0x800):
                try:
                    name = info.filename.encode("cp437").decode("cp949")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            out[name] = info.filename
    return out


def _read_member(path, contains: str, **kw) -> tuple[pd.DataFrame, str]:
    mem = _zip_members(path)
    key = [k for k in mem if contains in k and k.lower().endswith(".csv")][0]
    with zipfile.ZipFile(path) as zf:
        raw = zf.read(mem[key])
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(_io.BytesIO(raw), encoding=enc, **kw), hashlib.sha256(raw).hexdigest()
        except UnicodeDecodeError:
            continue
    raise ValueError(key)


# ---------------------------------------------------------------- #41

def provenance_41() -> dict:
    a, sha41 = _read_member(_zip("41"), "")
    b, _ = _read_member(_zip("27"), "okm")
    bad = sorted(b.loc[b["시간"] > 23, "날짜"].unique())
    bb = b[~b["날짜"].isin(bad)].reset_index(drop=True)
    P = bb[["15분", "30분", "45분", "60분"]].to_numpy().reshape(-1).astype(float)
    n = len(a)
    out = {"rows_41": int(n), "rows_27_x4_minus_2days_minus1": int(len(P) - 1), "sha256_41": sha41,
           "dropped_27_dates": [int(d) for d in bad]}
    date = np.repeat(bb["날짜"].to_numpy(), 4)[1:n + 1]
    prod27 = np.repeat(bb["생산량"].to_numpy(), 4)[1:n + 1].astype(float)
    cols = {c.lower(): c for c in a.columns}
    U = a[cols.get("power_usage", "Power_Usage")].to_numpy(float)
    prod41 = a[cols.get("production", "Production")].to_numpy(float)
    Pp, Ps = P[0:n], P[1:n + 1]
    Pn = np.r_[P[2:n + 2], [np.nan] * max(0, n + 2 - len(P))][:n]
    ok = np.isfinite(Pn)
    X = np.c_[Pp[ok], Ps[ok], Pn[ok], np.ones(ok.sum())]
    coef, *_ = np.linalg.lstsq(X, U[ok], rcond=None)
    resid = U[ok] - X @ coef
    out["power_usage_regression_on_27_prev_same_next"] = [round(float(c), 4) for c in coef]
    out["power_usage_R2"] = round(float(1 - resid.var() / U[ok].var()), 4)
    out["production_corr_41_vs_27_div4"] = round(float(np.corrcoef(prod41, prod27 / 4)[0, 1]), 5)
    df = pd.DataFrame({"d": date, "p41": prod41, "p27": prod27})
    pc = df.groupby("d").apply(lambda x: np.corrcoef(x.p41, x.p27)[0, 1] if x.p27.std() > 0 else np.nan,
                               include_groups=False)
    out["dates_with_varying_production"] = int(pc.notna().sum())
    out["dates_production_corr_below_0.99"] = int((pc < 0.99).sum())
    out["verdict"] = "#41은 #27의 15분 구간(손상 2일 제외)과 행 단위로 대응하는 파생 자료 → 외부 검증에서 제외"
    return out


# ---------------------------------------------------------------- #46

FILES46 = {"R1": "로봇 1호", "R2": "로봇 2호", "P1": "프레스 1호", "P2": "프레스 2호", "P3": "프레스 3호", "P4": "프레스 4호"}
HOLD = {"P1": 5, "P2": 5, "P3": 5, "P4": 5, "R1": 15, "R2": 15}
THR = {"P1": 1, "P2": 1, "P3": 1, "P4": 1, "R1": 5, "R2": 5}


def mechanism_46() -> tuple[dict, pd.DataFrame]:
    raw = {}
    shas = {}
    for k, key in FILES46.items():
        x, sha = _read_member(_zip("46"), key)
        x.columns = ["i", "t", "v"]
        x["t"] = pd.to_datetime(x["t"])
        raw[k] = x.groupby("t")["v"].mean()
        shas[k] = sha
    t0, t1 = pd.Timestamp("2022-07-18 00:00"), pd.Timestamp("2022-08-31 23:59")
    grid = pd.date_range(t0, t1, freq="min")
    M = pd.DataFrame(index=grid)
    for k, s in raw.items():
        s2 = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="min"))
        M[k] = s2.ffill(limit=HOLD[k] - 1).reindex(grid)
    eq = list(FILES46)
    out = {"sha256": shas, "coverage_all6_after_hold": round(float(M[eq].notna().all(axis=1).mean()), 3)}
    allv = M[eq].notna().all(axis=1)
    V = M.loc[allv, eq]
    on = pd.DataFrame({k: V[k] > THR[k] for k in eq})
    k_on = on.sum(axis=1)
    out["share_minutes_by_n_on"] = {int(i): round(float(c), 4) for i, c in k_on.value_counts(normalize=True).sort_index().items()}
    out["P1P2_on_agreement"] = round(float((on.P1 == on.P2).mean()), 4)
    # 프레스 1·2 기동 동기화
    def starts(s):
        onv = s > 1.0
        gap = s.index.to_series().diff().dt.total_seconds() / 60
        return pd.Series(s.index[onv & (onv.shift(1) == False) & (gap <= 10)])  # noqa: E712
    s1, s2 = starts(raw["P1"]), starts(raw["P2"])
    lag = pd.Series([(t - s2[(s2 - t).abs().idxmin()]).total_seconds() / 60 for t in s1])
    out["press_starts"] = {"P1": int(len(s1)), "P2": int(len(s2)), "share_P1_start_within_3min_of_P2": round(float((lag.abs() <= 3).mean()), 3),
                           "P1_start_hours": {int(h): int(c) for h, c in s1.dt.hour.value_counts().sort_index().items()}}
    tot = M[eq].sum(axis=1, min_count=6)
    b = tot.resample("15min")
    d15 = b.mean()[b.count() >= 12]
    ind15 = {k: M[k].resample("15min").mean() for k in eq}
    out["peak_15min_sum_A"] = round(float(d15.max()), 2)
    out["sum_of_individual_15min_peaks_A"] = round(float(sum(v.max() for v in ind15.values())), 2)
    on15 = pd.DataFrame({k: (M[k] > THR[k]).astype(float).where(M[k].notna()).resample("15min").mean() for k in eq})
    top = d15[d15 >= d15.quantile(0.95)].index
    rest = d15[d15 < d15.quantile(0.5)].index
    out["top5pct_blocks_on_fraction"] = on15.loc[top].mean().round(3).to_dict()
    out["below_median_blocks_on_fraction"] = on15.loc[rest].mean().round(3).to_dict()

    # 기동 분산 실험: 일별 사후 최적(표본 내) vs 앞 기간에서 학습한 고정 분산(표본 외)
    def daily_max15(offs, days):
        parts = [M[k].shift(offs.get(k, 0)) for k in eq]
        t = pd.concat(parts, axis=1).sum(axis=1, min_count=6)
        bb = t.resample("15min")
        m = bb.mean()[bb.count() >= 12]
        return m.groupby(m.index.normalize()).max().reindex(days)

    wd = [d for d in pd.date_range("2022-07-19", "2022-08-30") if d.dayofweek < 5]
    rng = range(-60, 61, 5)
    rows = []
    for d in wd:
        base = daily_max15({}, [d]).iloc[0]
        if not np.isfinite(base):
            continue
        offs, best = {k: 0 for k in ["P1", "P2", "R1", "R2"]}, base
        for _ in range(2):
            for k in ["P1", "P2", "R1", "R2"]:
                for s in rng:
                    tr = dict(offs)
                    tr[k] = s
                    v = daily_max15(tr, [d]).iloc[0]
                    if np.isfinite(v) and v < best - 1e-9:
                        best, offs = v, tr
        rows.append(dict(day=d, base15=base, insample_best15=best, reduction_pct=100 * (1 - best / base)))
    per_day = pd.DataFrame(rows)
    train = [d for d in wd if d < pd.Timestamp("2022-08-10")]
    test = [d for d in wd if d >= pd.Timestamp("2022-08-10")]
    offs, best = {k: 0 for k in ["P1", "P2", "R1", "R2"]}, daily_max15({}, train).mean()
    for _ in range(2):
        for k in ["P1", "P2", "R1", "R2"]:
            for s in rng:
                tr = dict(offs)
                tr[k] = s
                v = daily_max15(tr, train).mean()
                if v < best - 1e-9:
                    best, offs = v, tr
    bt, at = daily_max15({}, test), daily_max15(offs, test)
    okm = bt.notna() & at.notna()
    red = 100 * (1 - at[okm] / bt[okm])
    out["stagger_insample_per_day_median_pct"] = round(float(per_day["reduction_pct"].median()), 2)
    out["stagger_fixed_policy_oos"] = {"offsets_min": offs, "median_pct": round(float(red.median()), 2),
                                       "mean_pct": round(float(red.mean()), 2), "days": int(okm.sum()),
                                       "days_worse": int((red < 0).sum())}
    out["note"] = "6대 설비는 한 탠덤 라인(생산 로그 라인 1개)이어서 개별 이동은 물리적 제약 확인이 필요"
    return out, per_day


# ---------------------------------------------------------------- #30

def schedule_slack_30() -> dict:
    """#30: 주문 수량 × 최단 가공시간(분/개)과 NC 설비 용량(설비당 하루 600분, 20시간 운전 참고)의 비교."""
    m, sha_m = _read_member(_zip("30"), "machine_info", dtype=str)
    o, sha_o = _read_member(_zip("30"), "order_info", dtype=str)
    m["capacity"] = m["capacity"].astype(float)
    o["수량"] = o["수량"].astype(float)
    o["영업납기"] = pd.to_datetime(o["영업납기"])
    ct = m.groupby("item")["capacity"].min()
    o["min_minutes"] = o["수량"] * o["중산도면"].map(ct)
    n_mach = m["machine"].nunique()
    span_days = (o["영업납기"].max() - o["영업납기"].min()).days
    out = {"sha256": {"machine_info": sha_m, "order_info": sha_o}, "orders": int(len(o)),
           "orders_with_cycle_time": int(o["min_minutes"].notna().sum()), "machines": int(n_mach),
           "due_span_days": int(span_days), "total_min_machine_minutes": round(float(o["min_minutes"].sum()), 1)}
    # 월별 필요 설비-분 vs 월 용량(설비 수 × 근무일 22일 × 600분)
    mon = o.groupby(o["영업납기"].dt.to_period("M"))["min_minutes"].sum()
    cap_month = n_mach * 22 * 600
    out["order_book_minutes_share_of_capacity_by_due_month"] = {str(k): round(float(v / cap_month), 4) for k, v in mon.items()}
    out["constraints"] = {"minutes_per_machine_per_day": 600, "reference_run_hours_per_day": [10, 20],
                          "cycle_time_rows": int(len(m)), "items": int(m["item"].nunique())}
    out["note"] = ("주문표 127건(가이드의 최적화 예제 범위)만의 최단 가공시간 합이므로 공장 전체 부하·가동률이 아니다. "
                   "일정 이동 시나리오의 제약값(설비당 600분/일, 품목×설비 가공시간, 납기)의 출처로만 쓰며, "
                   "설비별 kW가 없어 전력 절감량은 계산하지 않는다.")
    return out


def run() -> dict:
    od = io.out_dir("external")
    res = {}
    for name, fn in (("kamp41_provenance", provenance_41), ("kamp30_schedule_slack", schedule_slack_30)):
        try:
            res[name] = fn()
        except (FileNotFoundError, IndexError, KeyError) as e:
            res[name] = {"skipped": str(e)}
    try:
        m46, per_day = mechanism_46()
        res["kamp46_mechanism"] = m46
        io.write_csv(per_day, od / "kamp46_stagger_per_day.csv")
    except (FileNotFoundError, IndexError, KeyError) as e:
        res["kamp46_mechanism"] = {"skipped": str(e)}
    io.write_json(res, od / "external_summary.json")
    return res
