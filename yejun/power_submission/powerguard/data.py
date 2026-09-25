"""원본 적재, 데이터 진단, 15분 구간 시계열 구성.

원본 한 행은 (날짜, 시간) 한 시간이고 `15분·30분·45분·60분`은 그 시간 안의 연속된 네 15분 구간 전력이다.
구간은 시작 시각으로 색인하며, 값은 구간이 끝난 뒤에 알 수 있다.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


# ---------------------------------------------------------------- 적재

def resolve_source(path: str | Path | None = None) -> Path:
    """CSV 또는 ZIP 경로를 정한다. 우선순위: 인자 → data/ 안의 CSV → 저장소 데이터셋 ZIP."""
    if path is not None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        return p
    local = C.DATA_DIR / C.CSV_NAME
    if local.exists():
        return local
    if C.DEFAULT_ZIP.exists():
        return C.DEFAULT_ZIP
    raise FileNotFoundError(
        f"원본을 찾지 못했다. {local} 에 CSV를 두거나 --data 로 ZIP/CSV 경로를 지정한다.")


def read_bytes(src: Path) -> bytes:
    if src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as zf:
            return zf.read(C.ZIP_MEMBER)
    return src.read_bytes()


def load_raw(path: str | Path | None = None, check_hash: bool = True) -> tuple[pd.DataFrame, dict]:
    src = resolve_source(path)
    raw_bytes = read_bytes(src)
    sha = hashlib.sha256(raw_bytes).hexdigest()
    if check_hash and sha != C.CSV_SHA256:
        raise ValueError(f"CSV SHA-256 불일치: {sha}")
    df = pd.read_csv(io.BytesIO(raw_bytes), encoding="utf-8-sig")
    expected = ["날짜", "시간", *C.POWER_COLS, "평균", "생산량", "기온", "풍속", "습도", "강수량",
                "전기요금(계절)", "day", "d", "m", "공장인원", "인건비"]
    if list(df.columns) != expected:
        raise ValueError(f"열 구성이 다르다: {list(df.columns)}")
    df["date"] = pd.to_datetime(df["날짜"].astype(int).astype(str), format="%Y%m%d")
    meta = {"source": str(src.name), "sha256": sha, "rows": int(len(df)), "cols": int(df.shape[1] - 1)}
    return df, meta


# ---------------------------------------------------------------- 진단

@dataclass
class Diagnosis:
    summary: dict = field(default_factory=dict)
    days: pd.DataFrame | None = None          # 날짜별 표시(복제·손상·정전 등)
    copied: pd.DataFrame | None = None        # 복제일 → 원본일 매핑
    contradictions: pd.DataFrame | None = None
    outage: pd.DataFrame | None = None
    missing: pd.DataFrame | None = None
    hour_copies: pd.DataFrame | None = None


def _round_half_up(x: np.ndarray) -> np.ndarray:
    return np.floor(x + 0.5)


def diagnose(df: pd.DataFrame) -> Diagnosis:
    P = C.POWER_COLS
    out = Diagnosis()
    s = out.summary
    s["n_days"] = int(df["date"].nunique())
    s["date_min"] = str(df["date"].min().date())
    s["date_max"] = str(df["date"].max().date())
    s["rows_per_day_all_24"] = bool((df.groupby("date").size() == 24).all())

    # 파생 열 누설
    pw = df[P].to_numpy(dtype=float)
    s["평균_equals_round_half_up_mean"] = int((_round_half_up(pw.mean(1)) == df["평균"]).sum())
    tot = pw.sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = df["생산량"].to_numpy(float) / tot
    ok = df["공장인원"].notna()
    s["공장인원_nonnull"] = int(ok.sum())
    s["공장인원_equals_prod_div_power_sum"] = int((np.abs(ratio[ok] - df.loc[ok, "공장인원"]) < 1e-6).sum())

    # 보조 달력 열 일관성 (day: 월=1 … 일=7)
    s["day_col_matches_weekday"] = int((df["day"] == df["date"].dt.dayofweek + 1).sum())
    s["d_col_matches_day"] = int((df["d"] == df["date"].dt.day).sum())
    s["m_col_matches_month"] = int((df["m"] == df["date"].dt.month).sum())

    # 시간 열 손상: 날짜 안의 시간이 0..23 순서가 아닌 날짜
    hour_ok = df.groupby("date")["시간"].apply(lambda h: list(h) == list(range(24)))
    corrupt_dates = sorted(hour_ok[~hour_ok].index)
    corrupt_set = set(corrupt_dates)
    s["corrupt_hour_dates"] = [str(d.date()) for d in corrupt_dates]
    # 손상일의 행이 시간 열 값 기준으로 정렬되어 있는지, 기온은 일중 패턴을 유지하는지 참고 기록
    s["corrupt_rows_sorted_by_hour_col"] = {
        str(d.date()): bool(df.loc[df["date"] == d, "시간"].is_monotonic_increasing) for d in corrupt_dates}

    # 일 단위 전력 패턴 복제
    rows = []
    first: dict[tuple, pd.Timestamp] = {}
    first_prod: dict[tuple, pd.Timestamp] = {}
    for d, x in df.groupby("date", sort=True):
        key = tuple(x[P].to_numpy().ravel().tolist())
        pkey = tuple(x["생산량"].tolist())
        is_orig = key not in first
        first.setdefault(key, d)
        first_prod.setdefault(pkey, d)
        rows.append(dict(
            date=d, weekday=int(d.dayofweek), month=int(d.month),
            power_src=first[key], copied=not is_orig,
            prod_src=first_prod[pkey],
            prod_total=float(x["생산량"].sum()),
            power_mean=float(x[P].to_numpy().mean()),
            power_max=float(x[P].to_numpy().max()),
            holiday=bool(d in set(C.HOLIDAYS)),
        ))
    days = pd.DataFrame(rows).set_index("date")
    days["corrupt_hour"] = days.index.isin(corrupt_dates)
    s["unique_daily_power_patterns"] = int((~days["copied"]).sum())
    s["copied_power_days"] = int(days["copied"].sum())
    s["copied_by_month"] = {int(k): int(v) for k, v in days.groupby("month")["copied"].sum().items()}
    s["original_by_month"] = {int(k): int(v) for k, v in (~days["copied"]).groupby(days["month"]).sum().items()}
    cp = days[days["copied"]].copy()
    cp["src_same_dom"] = cp["power_src"].dt.day == cp.index.day
    cp["src_same_weekday"] = cp["power_src"].dt.dayofweek == cp.index.dayofweek
    cp["prod_copied_from_same_src"] = cp["prod_src"] == cp["power_src"]
    s["copied_prod_also_copied_same_src"] = int(cp["prod_copied_from_same_src"].sum())
    s["copied_src_same_weekday_share"] = round(float(cp["src_same_weekday"].mean()), 4)
    s["copied_src_same_day_of_month_share"] = round(float(cp["src_same_dom"].mean()), 4)
    s["copy_groups"] = int(days[days["copied"]]["power_src"].nunique())
    out.copied = cp.reset_index()

    # 부분 복제: 완전 복제가 아닌 날 중, 앞선 다른 패턴 날짜와 16구간(4시간) 이상 연속으로 값이 같은 날.
    # 서로 다른 날짜 쌍의 자연 발생 최장 동일 연속은 11구간 이하였다(진단 표 참고).
    ymat = {d: x[P].to_numpy().ravel() for d, x in df.groupby("date", sort=True)}
    dlist = list(days.index)
    longest = {}
    for i, d in enumerate(dlist):
        best, best_src = 0, None
        for j in range(i):
            e = dlist[j]
            if days.at[e, "power_src"] == days.at[d, "power_src"]:
                continue
            eq = ymat[d] == ymat[e]
            run = mx = 0
            for v in eq:
                run = run + 1 if v else 0
                mx = max(mx, run)
            if mx > best:
                best, best_src = mx, e
        longest[d] = (best, best_src)
    days["longest_equal_run"] = [longest[d][0] for d in dlist]
    days["longest_equal_src"] = [longest[d][1] for d in dlist]
    # 시간 단위 복제: 가동 시간(네 값 평균 > 40)의 네 값이 이전 날짜 같은 시간과 완전히 같음
    hmat = {d: x[P].to_numpy().astype(int) for d, x in df.groupby("date", sort=True)}
    hour_copy_rows = []
    for i, d in enumerate(dlist):
        if d in corrupt_set:
            continue
        for h in range(24):
            v = hmat[d][h]
            if v.mean() <= C.RUNNING_HOUR_MEAN:
                continue
            for e in dlist[:i]:
                if e in corrupt_set:
                    continue
                if np.array_equal(hmat[e][h], v):
                    hour_copy_rows.append(dict(date=d, hour=h, src=e))
                    break
    hc = pd.DataFrame(hour_copy_rows, columns=["date", "hour", "src"])
    # 위약 검정: h시 값이 다른 날짜의 h+1시 값과 같은 경우(우연 일치 수준)
    placebo, tot = 0, 0
    for i, d in enumerate(dlist):
        if d in corrupt_set:
            continue
        for h in range(23):
            v = hmat[d][h]
            if v.mean() <= C.RUNNING_HOUR_MEAN:
                continue
            tot += 1
            if any(np.array_equal(hmat[e][h + 1], v) for e in dlist[:i] if e not in corrupt_set):
                placebo += 1
    s["hour_copy_placebo_matches"] = f"{placebo}/{tot}"
    n_hc = hc.groupby("date").size() if len(hc) else pd.Series(dtype=int)
    days["copied_running_hours"] = n_hc.reindex(days.index).fillna(0).astype(int)
    days["partial_copy"] = (~days["copied"]) & (
        (days["longest_equal_run"] >= C.PARTIAL_COPY_RUN) | (days["copied_running_hours"] >= C.PARTIAL_COPY_HOURS))
    s["partial_copy_days"] = [str(d.date()) for d in days.index[days["partial_copy"]]]
    orig_hc = hc[hc["date"].map(lambda d: not days.at[d, "copied"])] if len(hc) else hc
    s["hour_copies_on_non_copied_days"] = {str(d.date()): int(n) for d, n in orig_hc.groupby("date").size().items()}
    out.hour_copies = orig_hc
    s["natural_max_equal_run_below_threshold"] = int(
        days.loc[~days["copied"] & ~days["partial_copy"], "longest_equal_run"].max())

    # 달력·생산과 모순되는 복제 전력: 생산 0(휴일·일요일 포함)인데 가동일 수준 전력, 또는 반대
    src_stats = days[["prod_total", "power_mean"]]
    con = cp[(cp["prod_total"] == 0) & (cp["power_mean"] > 90)].copy()
    con["src_prod_total"] = con["power_src"].map(src_stats["prod_total"])
    con["reason"] = np.where(con["holiday"], "공휴일·생산0인데 가동 전력",
                             np.where(con.index.dayofweek == 6, "일요일·생산0인데 가동 전력", "생산0인데 가동 전력"))
    out.contradictions = con.reset_index()[["date", "weekday", "holiday", "prod_total", "power_mean",
                                            "power_src", "src_prod_total", "reason"]]
    s["copied_calendar_contradictions"] = int(len(con))

    # 원본일 중 생산 0인데 가동 전력(생산기록 없는 가동)
    orig = days[~days["copied"] & ~days["corrupt_hour"] & ~days["partial_copy"]]
    s["orig_days_prod0_but_running"] = [str(d.date()) for d in orig[(orig["prod_total"] == 0) & (orig["power_mean"] > 90)].index]

    # 생산기록–전력 체제 불일치(사후 판정): 계획 전면 가동인데 주간 전력이 대기 수준, 또는 생산≈0인데 주간 가동 전력
    ds = df[(df["시간"] >= 9) & (df["시간"] <= 16)].groupby("date")[P].mean().mean(axis=1)
    days["day_shift_mean"] = ds.reindex(days.index)
    days["regime_mismatch"] = (~days["copied"]) & (~days["partial_copy"]) & (~days["corrupt_hour"]) & (
        ((days["prod_total"] >= 5000) & (days["day_shift_mean"] < 80))
        | ((days["prod_total"] < 500) & (days["day_shift_mean"] > 110)))
    s["regime_mismatch_days"] = [str(d.date()) for d in days.index[days["regime_mismatch"]]]

    # 전력 0 (정전/무계측)
    zero_all = (df[P] == 0).all(axis=1)
    zero_any = (df[P] == 0).any(axis=1)
    s["rows_all_power_zero"] = int(zero_all.sum())
    s["rows_any_power_zero"] = int(zero_any.sum())
    nz = pw[pw > 0]
    s["min_nonzero_power"] = float(nz.min())
    z = df.loc[zero_any, ["date", "시간", *P, "생산량"]].copy()
    out.outage = z
    days["outage_hours"] = df.loc[zero_any].groupby("date").size().reindex(days.index).fillna(0).astype(int)

    # 결측
    miss = df.drop(columns=["date"]).isna().sum()
    out.missing = miss[miss > 0].rename("n_missing").reset_index().rename(columns={"index": "column"})

    # 인건비·계절요금 구조
    s["인건비_by_hour"] = {int(h): sorted(df.loc[df["시간"] == h, "인건비"].unique().tolist())
                        for h in range(24)}
    s["전기요금_by_month"] = {int(m): sorted(df.loc[df["m"] == m, "전기요금(계절)"].unique().tolist())
                          for m in sorted(df["m"].unique())}
    out.days = days
    return out


# ---------------------------------------------------------------- 15분 구간 시계열

def build_intervals(df: pd.DataFrame, diag: Diagnosis, train_on_copies: bool = False) -> pd.DataFrame:
    """15분 구간 표. 색인 = 구간 시작 시각.

    열
    - y_raw: 원본 값(손상일은 슬롯을 알 수 없어 NaN)
    - copied / corrupt / outage: 날짜·구간 표시
    - y: 학습·평가에 쓰는 정답 = 원본(복제 아님)·손상 아님·정전 아님일 때만 값
    - prod: 그 시간의 생산량(시간 값을 네 구간에 동일 배정). 손상일은 NaN
    - 기상·요금·인건비: 시간 값 반복
    """
    P = C.POWER_COLS
    days = diag.days
    corrupt = set(days.index[days["corrupt_hour"]])
    idx = pd.date_range(df["date"].min(), df["date"].max() + pd.Timedelta(hours=23, minutes=45), freq="15min")
    out = pd.DataFrame(index=idx)
    out.index.name = "ts"

    good = df[~df["date"].isin(corrupt)].copy()
    hour_start = good["date"] + pd.to_timedelta(good["시간"], unit="h")
    for q, col in enumerate(P):
        ts = hour_start + pd.Timedelta(minutes=15 * q)
        out.loc[ts.to_numpy(), "y_raw"] = good[col].to_numpy(dtype=float)

    # 시간 단위 외생 변수: 손상일도 날씨는 시간순을 유지하므로 행 순서(0..23)로 배정한다
    # 단, 손상일 생산량은 전부 0으로 기록되어 있어 신뢰할 수 없으므로 NaN
    hourly = df.copy()
    hourly["hour_by_order"] = hourly.groupby("date").cumcount()
    hourly["hour_start"] = hourly["date"] + pd.to_timedelta(hourly["hour_by_order"], unit="h")
    hourly.loc[hourly["date"].isin(corrupt), "생산량"] = np.nan
    hmap = hourly.set_index("hour_start")[["생산량", "기온", "풍속", "습도", "강수량", "전기요금(계절)", "인건비"]]
    hmap.columns = ["prod", "temp", "wind", "hum", "rain", "tariff", "labor"]
    hour_key = out.index.floor("h")
    for c in hmap.columns:
        out[c] = hmap[c].reindex(hour_key).to_numpy()

    date_key = out.index.normalize()
    out["date"] = date_key
    out["copied"] = days["copied"].reindex(date_key).to_numpy()
    out["partial_copy"] = days["partial_copy"].reindex(date_key).to_numpy()
    out["corrupt"] = days["corrupt_hour"].reindex(date_key).to_numpy()
    out["outage"] = (out["y_raw"] == 0).to_numpy()
    out["hour_copy"] = False
    if diag.hour_copies is not None and len(diag.hour_copies):
        for _, r in diag.hour_copies.iterrows():
            t0 = r["date"] + pd.Timedelta(hours=int(r["hour"]))
            out.loc[t0:t0 + pd.Timedelta(minutes=45), "hour_copy"] = True
    out["regime_mismatch"] = days["regime_mismatch"].reindex(date_key).to_numpy()
    out["usable"] = ((~out["copied"]) & (~out["partial_copy"]) & (~out["corrupt"]) & (~out["outage"])
                     & (~out["hour_copy"]) & out["y_raw"].notna())
    # 학습·지연값·유사일 풀에 쓰는 구간: 평가 가능 구간에서 체제 불일치일(사후 판정)을 더 뺀다
    out["trainable"] = out["usable"] & (~out["regime_mismatch"])
    if train_on_copies:
        # 절제 실험: 복제·부분 복제 구간도 학습·유사일 풀에 넣는다(평가 대상은 그대로)
        extra = (out["copied"] | out["partial_copy"] | out["hour_copy"]) & (~out["corrupt"]) & (~out["outage"]) \
            & out["y_raw"].notna() & (out.index < C.TEST_START)
        out["trainable"] = out["trainable"] | extra
    out["y"] = out["y_raw"].where(out["usable"])
    out["y_train"] = out["y_raw"].where(out["trainable"])
    out["slot"] = out.index.hour * 4 + out.index.minute // 15
    out["hour"] = out.index.hour
    out["dow"] = out.index.dayofweek
    out["month"] = out.index.month
    out["holiday"] = date_key.isin(C.HOLIDAYS)
    return out


def usable_days(iv: pd.DataFrame) -> pd.DatetimeIndex:
    """정답을 쓸 수 있는 날짜(원본·손상 아님). 정전 구간이 있는 날도 나머지 구간은 사용."""
    g = iv.groupby("date")
    ok = g["usable"].any()
    return pd.DatetimeIndex(ok[ok].index)
