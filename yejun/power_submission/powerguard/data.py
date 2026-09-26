"""원본 적재, 데이터 진단, 15분 구간 시계열 구성.

원본 한 행은 (날짜, 시간) 한 시간이고 `15분·30분·45분·60분`은 그 시간 안의 연속된 네 15분 구간 전력이다.
구간은 시작 시각으로 색인하며, 값은 구간이 끝난 뒤에 알 수 있다.
"""
from __future__ import annotations

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


# ---------------------------------------------------------------- 적재

def resolve_source(path: str | Path | None = None) -> Path:
    """CSV 또는 ZIP 경로를 정한다. 우선순위: 인자 → 환경변수 POWERGUARD_DATA → data/ 안의 CSV → 저장소 데이터셋 ZIP."""
    if path is None:
        path = os.environ.get("POWERGUARD_DATA") or None
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


def load_raw(path: str | Path | None = None, check_hash: bool = True, cache: bool = True) -> tuple[pd.DataFrame, dict]:
    """원본 적재. 해시가 맞고 data/에 사본이 없으면 data/okm_augumented_2021.csv로 저장한다(이후 테스트·실행은 인자 없이 동작)."""
    src = resolve_source(path)
    raw_bytes = read_bytes(src)
    sha = hashlib.sha256(raw_bytes).hexdigest()
    if check_hash and sha != C.CSV_SHA256:
        raise ValueError(f"CSV SHA-256 불일치: {sha}")
    local = C.DATA_DIR / C.CSV_NAME
    if cache and sha == C.CSV_SHA256 and not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(raw_bytes)
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
    copy_groups: pd.DataFrame | None = None   # 복제군 구성원별 정합성과 원본 여부


def _round_half_up(x: np.ndarray) -> np.ndarray:
    return np.floor(x + 0.5)


def _longest_true_run(b: np.ndarray) -> int:
    """불리언 배열에서 가장 긴 True 연속 길이."""
    if not b.any():
        return 0
    x = np.concatenate([[0], b.astype(np.int8), [0]])
    d = np.diff(x)
    return int((np.where(d == -1)[0] - np.where(d == 1)[0]).max())


def consistency_table(df: pd.DataFrame, corrupt: set, night_power_on: float = C.NIGHT_POWER_ON,
                      night_prod_on: float = C.NIGHT_PROD_ON, day_power_on: float = C.DAY_POWER_ON,
                      day_prod_on: float = C.DAY_PROD_ON, evening_power_on: float = C.EVENING_POWER_ON,
                      evening_prod_on: float = C.EVENING_PROD_ON) -> pd.DataFrame:
    """날짜별 전력 패턴–생산 기록 정합성. 손상일(시간 열 손상)은 판정하지 않는다(NaN).

    night_ok:   01~05시 평균 전력이 야간 가동 수준인지와 00~06시에 생산 기록이 있는지가 일치
    day_ok:     09~16시 평균 전력이 주간 가동 수준인지와 08~19시에 생산 기록이 있는지가 일치
    evening_ok: 20~23시 평균 전력이 야간조 수준인지와 20~23시에 생산 기록이 있는지가 일치(v2.1)
    """
    hr = df["시간"]
    pw = df[C.POWER_COLS].mean(axis=1)
    g = df["date"]
    t = pd.DataFrame({
        "night_power": pw[(hr >= 1) & (hr <= 5)].groupby(g[(hr >= 1) & (hr <= 5)]).mean(),
        "day_power": pw[(hr >= 9) & (hr <= 16)].groupby(g[(hr >= 9) & (hr <= 16)]).mean(),
        "night_prod": df.loc[hr <= 6, "생산량"].groupby(g[hr <= 6]).sum(),
        "day_prod": df.loc[(hr >= 8) & (hr <= 19), "생산량"].groupby(g[(hr >= 8) & (hr <= 19)]).sum(),
        "evening_power": pw[(hr >= 20) & (hr <= 23)].groupby(g[(hr >= 20) & (hr <= 23)]).mean(),
        "evening_prod": df.loc[(hr >= 20) & (hr <= 23), "생산량"].groupby(g[(hr >= 20) & (hr <= 23)]).sum(),
    }).reindex(pd.DatetimeIndex(sorted(g.unique())))
    night_ok = (t["night_power"] > night_power_on) == (t["night_prod"] > night_prod_on)
    day_ok = (t["day_power"] > day_power_on) == (t["day_prod"] > day_prod_on)
    evening_ok = (t["evening_power"] > evening_power_on) == (t["evening_prod"] > evening_prod_on)
    t["night_ok"] = night_ok.astype(float)
    t["day_ok"] = day_ok.astype(float)
    t["evening_ok"] = evening_ok.astype(float)
    t["consistent"] = (night_ok & day_ok & evening_ok).astype(float)
    bad = t.index.isin(list(corrupt)) | t[["night_power", "day_power", "evening_power"]].isna().any(axis=1)
    t.loc[bad, ["night_ok", "day_ok", "evening_ok", "consistent"]] = np.nan
    return t


def choose_origin(members: list, consistent: pd.Series, rule: str) -> pd.Timestamp:
    """복제군(날짜 오름차순)의 원본. 'earliest'(v1.x) 또는 'latest_consistent'(v2.0: 정합 구성원 중 가장 늦은 날)."""
    if rule == "earliest" or len(members) == 1:
        return members[0]
    ok = [m for m in members if consistent.get(m) == 1]
    return ok[-1] if ok else members[-1]


def copy_origin_evidence(days: pd.DataFrame) -> dict:
    """원본 판정 근거: 복제군의 가장 이른/늦은 구성원 정합 비율과 단독 날짜(복제 없음)의 정합 비율."""
    from scipy.stats import binomtest
    multi = days[days["copy_group_size"] > 1]
    grp = multi.groupby("power_src")
    first_ok = grp.apply(lambda x: x.sort_index()["consistent"].iloc[0], include_groups=False)
    last_ok = grp.apply(lambda x: x.sort_index()["consistent"].iloc[-1], include_groups=False)
    single = days[(days["copy_group_size"] == 1) & days["consistent"].notna()]
    meas = single[single.index >= C.MEASURED_START]
    p_single = float(single["consistent"].mean())
    n = int(first_ok.notna().sum())
    k = int((first_ok == 1).sum())
    return {
        "copy_groups_multi": int(len(first_ok)),
        "copy_groups_earliest_member_consistent": f"{k}/{n}",
        "copy_groups_latest_member_consistent": f"{int((last_ok == 1).sum())}/{int(last_ok.notna().sum())}",
        "copy_groups_chosen_origin_consistent": f"{int((days.loc[days['copy_group_size'] > 1].query('~copied')['consistent'] == 1).sum())}/{len(first_ok)}",
        "singleton_days_consistent": f"{int(single['consistent'].sum())}/{len(single)}",
        "singleton_days_consistent_measured_period": f"{int(meas['consistent'].sum())}/{len(meas)}",
        # 가장 이른 구성원이 실제 측정이라면 단독 날짜와 같은 비율로 정합해야 한다(이항 검정, 한쪽)
        "earliest_is_origin_binom_p": float(binomtest(k, n, p_single, alternative="less").pvalue) if n else None,
    }


def copy_group_table(days: pd.DataFrame) -> pd.DataFrame:
    multi = days[days["copy_group_size"] > 1].copy()
    multi["is_origin"] = ~multi["copied"]
    first = multi.groupby("power_src").apply(lambda x: x.index.min(), include_groups=False)
    multi["is_earliest"] = multi.index == multi["power_src"].map(first)
    cols = ["power_src", "copy_group_size", "weekday", "month", "holiday", "is_origin", "is_earliest", "consistent",
            "night_ok", "day_ok", "evening_ok", "night_power", "night_prod", "day_power", "day_prod", "evening_power",
            "evening_prod", "prod_total"]
    return multi[cols].rename(columns={"power_src": "group_origin"}).reset_index().sort_values(["group_origin", "date"])


def contradiction_reason(r) -> str:
    parts = []
    if r.night_ok == 0:
        parts.append("야간 생산 없는데 야간조 전력" if r.night_power > C.NIGHT_POWER_ON else "야간 생산 있는데 대기 전력")
    if r.day_ok == 0:
        parts.append("주간 생산 없는데 가동 전력" if r.day_power > C.DAY_POWER_ON else "주간 생산 있는데 대기 전력")
    if getattr(r, "evening_ok", 1) == 0:
        parts.append("저녁 생산 없는데 야간조 전력" if r.evening_power > C.EVENING_POWER_ON else "저녁 생산 있는데 대기 전력")
    tag = "공휴일" if r.holiday else ("일요일" if r.weekday == 6 else ("토요일" if r.weekday == 5 else "평일"))
    return f"{tag}: " + "·".join(parts)


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

    # 날짜별 전력 패턴과 생산 기록의 정합성: 야간조 이월(01~05시 전력 ↔ 00~06시 생산), 주간 가동(09~16시 ↔ 08~19시)
    cons = consistency_table(df, corrupt_set)

    # 일 단위 전력 패턴 복제: 같은 96값을 가진 날짜 묶음(복제군)에서 원본 하나를 정하고 나머지를 복제로 본다
    keys = {d: tuple(x[P].to_numpy().ravel().tolist()) for d, x in df.groupby("date", sort=True)}
    members: dict[tuple, list] = {}
    for d, k in keys.items():
        members.setdefault(k, []).append(d)
    origin = {}
    for k, ms in members.items():
        origin.update({m: choose_origin(sorted(ms), cons["consistent"], C.COPY_ORIGIN) for m in ms})
    rows = []
    first_prod: dict[tuple, pd.Timestamp] = {}
    for d, x in df.groupby("date", sort=True):
        pkey = tuple(x["생산량"].tolist())
        first_prod.setdefault(pkey, d)
        rows.append(dict(
            date=d, weekday=int(d.dayofweek), month=int(d.month),
            power_src=origin[d], copied=origin[d] != d, copy_group_size=len(members[keys[d]]),
            prod_src=first_prod[pkey],
            prod_total=float(x["생산량"].sum()),
            power_mean=float(x[P].to_numpy().mean()),
            power_max=float(x[P].to_numpy().max()),
            holiday=bool(d in set(C.HOLIDAYS)),
        ))
    days = pd.DataFrame(rows).set_index("date")
    days = days.join(cons)
    days["corrupt_hour"] = days.index.isin(corrupt_dates)
    s["copy_origin_rule"] = C.COPY_ORIGIN
    s.update(copy_origin_evidence(days))
    out.copy_groups = copy_group_table(days)
    s["unique_daily_power_patterns"] = int((~days["copied"]).sum())
    s["copied_power_days"] = int(days["copied"].sum())
    s["copied_by_month"] = {int(k): int(v) for k, v in days.groupby("month")["copied"].sum().items()}
    s["original_by_month"] = {int(k): int(v) for k, v in (~days["copied"]).groupby(days["month"]).sum().items()}
    cp = days[days["copied"]].copy()
    cp["src_same_dom"] = cp["power_src"].dt.day == cp.index.day
    cp["src_same_weekday"] = cp["power_src"].dt.dayofweek == cp.index.dayofweek
    cp["src_offset_days"] = (cp["power_src"] - cp.index).dt.days
    cp["src_month"] = cp["power_src"].dt.month
    # 생산 기록은 날짜 고유값이다: 생산 벡터가 다른 날과 같은 복제일은 모두 생산 0인 날이다
    same_prod = cp["prod_src"] != cp.index
    s["copied_days_with_production_vector_equal_to_other_day"] = int(same_prod.sum())
    s["copied_days_with_production_vector_equal_to_other_day_all_zero"] = int((same_prod & (cp["prod_total"] == 0)).sum())
    s["copied_src_same_weekday_share"] = round(float(cp["src_same_weekday"].mean()), 4)
    s["copied_src_same_day_of_month_share"] = round(float(cp["src_same_dom"].mean()), 4)
    s["copied_src_later_share"] = round(float((cp["src_offset_days"] > 0).mean()), 4)
    s["copied_by_src_month"] = {f"{int(a)}<-{int(b)}": int(n) for (a, b), n in
                                cp.groupby([cp.index.month, cp["src_month"]]).size().items()}
    s["copy_groups"] = int(days[days["copied"]]["power_src"].nunique())
    out.copied = cp.reset_index()

    # 부분 복제: 완전 복제가 아닌 날 중, 다른 패턴 날짜와 16구간(4시간) 이상 연속으로 값이 같은 날.
    # 두 패턴 중 어느 쪽이 원본인지는 복제군과 같은 규칙(C.COPY_ORIGIN)으로 정하고 원본이 아닌 쪽만 표시한다.
    # 서로 다른 날짜 쌍의 자연 발생 최장 동일 연속은 11구간 이하였다(진단 표 참고).
    ymat = {d: x[P].to_numpy().ravel() for d, x in df.groupby("date", sort=True)}
    dlist = list(days.index)
    src = days["power_src"]
    cons_s = days["consistent"]
    longest = {}
    for d in dlist:
        best, best_src = 0, None
        if not days.at[d, "copied"]:
            for e in dlist:
                if e == d or src[e] == src[d]:
                    continue
                mx = _longest_true_run(ymat[d] == ymat[e])
                if mx >= C.PARTIAL_COPY_RUN and choose_origin(sorted([d, src[e]]), cons_s, C.COPY_ORIGIN) == d:
                    continue  # 이 날이 원본 쪽이면 표시하지 않는다
                if mx > best:
                    best, best_src = mx, src[e]
        longest[d] = (best, best_src)
    days["longest_equal_run"] = [longest[d][0] for d in dlist]
    days["longest_equal_src"] = [longest[d][1] for d in dlist]
    # 시간 단위 복제: 가동 시간(네 값 평균 > 40)의 네 값이 다른 패턴 날짜의 같은 시간과 완전히 같음.
    # 같은 시간 값을 가진 패턴들 중 원본(복제군과 같은 규칙) 아닌 쪽의 그 시간을 복제로 본다.
    hmat = {d: x[P].to_numpy().astype(int) for d, x in df.groupby("date", sort=True)}
    ok_dates = [d for d in dlist if d not in corrupt_set]
    holders: dict[tuple, set] = {}
    for d in ok_dates:
        for h in range(24):
            v = hmat[d][h]
            if v.mean() > C.RUNNING_HOUR_MEAN:
                holders.setdefault((h, tuple(v)), set()).add(src[d])
    hour_copy_rows = []
    for d in ok_dates:
        if days.at[d, "copied"]:
            continue
        for h in range(24):
            v = hmat[d][h]
            if v.mean() <= C.RUNNING_HOUR_MEAN:
                continue
            pats = holders[(h, tuple(v))]
            if len(pats) > 1:
                o = choose_origin(sorted(pats), cons_s, C.COPY_ORIGIN)
                if o != d:
                    hour_copy_rows.append(dict(date=d, hour=h, src=o))
    hc = pd.DataFrame(hour_copy_rows, columns=["date", "hour", "src"])
    # 위약 검정: h시 값이 다른 패턴 날짜의 h+1시 값과 같은 경우(우연 일치 수준)
    placebo, tot = 0, 0
    for d in ok_dates:
        for h in range(23):
            v = hmat[d][h]
            if v.mean() <= C.RUNNING_HOUR_MEAN:
                continue
            tot += 1
            if any(p != src[d] for p in holders.get((h + 1, tuple(v)), ())):
                placebo += 1
    s["hour_copy_placebo_matches"] = f"{placebo}/{tot}"
    n_hc = hc.groupby("date").size() if len(hc) else pd.Series(dtype=int)
    days["copied_running_hours"] = n_hc.reindex(days.index).fillna(0).astype(int)
    days["partial_copy"] = (~days["copied"]) & (
        (days["longest_equal_run"] >= C.PARTIAL_COPY_RUN) | (days["copied_running_hours"] >= C.PARTIAL_COPY_HOURS))
    s["partial_copy_days"] = [str(d.date()) for d in days.index[days["partial_copy"]]]
    orig_hc = hc
    s["hour_copies_on_non_copied_days"] = {str(d.date()): int(n) for d, n in orig_hc.groupby("date").size().items()}
    out.hour_copies = orig_hc
    s["natural_max_equal_run_below_threshold"] = int(
        days.loc[~days["copied"] & ~days["partial_copy"], "longest_equal_run"].max())

    # 달력·생산과 모순되는 복제 전력(양방향): 복제일의 생산 기록과 복제된 전력 패턴이 맞지 않는 경우
    con = cp[cp["consistent"] == 0].copy()
    con["src_prod_total"] = con["power_src"].map(days["prod_total"])
    con["reason"] = [contradiction_reason(r) for r in con.itertuples()]
    out.contradictions = con.reset_index()[["date", "weekday", "holiday", "prod_total", "night_prod", "night_power",
                                            "day_prod", "day_power", "evening_prod", "evening_power", "power_src",
                                            "src_prod_total", "reason"]]
    s["copied_calendar_contradictions"] = int(len(con))

    # 원본일 중 생산 0인데 가동 전력(생산기록 없는 가동)
    orig = days[~days["copied"] & ~days["corrupt_hour"] & ~days["partial_copy"]]
    s["orig_days_prod0_but_running"] = [str(d.date()) for d in orig[(orig["prod_total"] == 0) & (orig["power_mean"] > 90)].index]

    # 원본일인데 전력 패턴이 그 날짜의 생산 기록과 맞지 않는 날(사후 판정): 학습·유사일 풀에서만 뺀다
    days["day_shift_mean"] = days["day_power"]
    days["regime_mismatch"] = (~days["copied"]) & (~days["partial_copy"]) & (~days["corrupt_hour"]) & (days["consistent"] == 0)
    s["regime_mismatch_days"] = [str(d.date()) for d in days.index[days["regime_mismatch"]]]
    ok_days = days[~days["copied"] & ~days["partial_copy"] & ~days["corrupt_hour"]]
    s["genuine_days_by_month"] = {int(k): int(v) for k, v in
                                  (ok_days["consistent"] == 1).groupby(ok_days["month"]).sum().items()}
    s["days_by_month"] = {int(k): int(v) for k, v in days.groupby("month").size().items()}

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

def build_intervals(df: pd.DataFrame, diag: Diagnosis, train_on_copies: bool = False, naive: bool = False) -> pd.DataFrame:
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
    if naive:
        # 반사실 절차(절제 실험): 복제를 모르는 흔한 처리 — 손상·정전만 빼고 모든 날을 학습·평가에 쓴다
        out["usable"] = (~out["corrupt"]) & (~out["outage"]) & out["y_raw"].notna()
        out["trainable"] = out["usable"]
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
