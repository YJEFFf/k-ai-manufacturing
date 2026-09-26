"""S1 데이터 진단 산출물."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import cv as CV
from . import data as D
from . import features as F
from . import io

# 원자료 18열 사전: (가이드 정의(8쪽), 단위/형, 시간 해상도, 출처, 파생 관계, 사용 여부, 사유)
VARIABLES = {
    "날짜": ("공장운영 날짜", "YYYYMMDD", "일", "공장 운영", "", "색인", "달력·요일유형·공휴일 생성"),
    "시간": ("공장운영 시간", "0~23", "시", "공장 운영", "", "색인", "7/13·7/15는 70~188로 손상 → 두 날 전력·생산 결측"),
    "15분": ("0~15분까지의 피크전기 사용량(최대수요전력)", "단위 미기재", "15분", "변압기 센서", "", "정답", "한 시간 안 첫 15분 구간"),
    "30분": ("15~30분까지의 피크전기 사용량", "단위 미기재", "15분", "변압기 센서", "", "정답", "두 번째 15분 구간"),
    "45분": ("30~45분까지의 피크전기 사용량", "단위 미기재", "15분", "변압기 센서", "", "정답", "세 번째 15분 구간"),
    "60분": ("45~60분까지의 피크전기 사용량", "단위 미기재", "15분", "변압기 센서", "", "정답", "네 번째 15분 구간"),
    "평균": ("15·30·45·60분 값의 평균", "단위 미기재", "시", "파생", "floor(네 값 평균+0.5)와 전 행 일치", "제외", "정답에서 파생(누설)"),
    "생산량": ("해당 시점에 생산해야 할 생산량", "개(추정)", "시", "ERP", "빈칸은 0으로 채움(가이드 9쪽)", "일 단위 체제만",
            "시간별 값은 실적 기록 시점일 수 있어 정보가치 실험에서만 사용"),
    "기온": ("해당 시점의 기온", "°C", "시", "기상청", "", "사용", "실측을 예보 대리로 사용(예보오차 민감도 별도)"),
    "풍속": ("해당 시점의 풍속", "m/s", "시", "기상청", "", "제외", "냉방부하와 무관, 결측 3행"),
    "습도": ("해당 시점의 습도", "%", "시", "기상청", "98에서 상한", "사용", "냉방부하 보조"),
    "강수량": ("해당 시점의 강수량", "mm(누적 성격)", "시", "기상청", "하루 안 비감소(누적값) 다수", "제외", "시간 값이 아니라 누적값으로 보임"),
    "전기요금(계절)": ("해당 시점의 전기요금", "월 상수", "월", "한국전력", "1~2월 109.8, 3~5·9월 167.2, 6~8월 191.6", "계절 표시만",
                 "하루 안 변화 없음, 요금 계산에 쓰지 않음"),
    "day": ("요일 값(월=1)", "1~7", "일", "파생", "날짜의 요일과 전 행 일치", "제외", "날짜와 중복"),
    "d": ("일 값", "1~31", "일", "파생", "날짜와 전 행 일치", "제외", "날짜와 중복"),
    "m": ("월 값", "1~9", "일", "파생", "날짜와 전 행 일치", "제외", "날짜와 중복"),
    "공장인원": ("해당 시점에 공장이 보유한 생산력", "비율", "시", "파생", "생산량 ÷ 네 값 합과 전 행 일치", "제외", "정답에서 파생(누설)"),
    "인건비": ("야간 및 주간 인건비에 대한 비율값", "1.0/1.5", "시", "파생", "09~17시 1.0, 그 외 1.5(모든 날)", "제외", "시각과 중복"),
}


def variable_dictionary(df: pd.DataFrame, diag: D.Diagnosis) -> pd.DataFrame:
    rows = []
    for col, (desc, unit, res, src, derived, use, why) in VARIABLES.items():
        x = df[col]
        rows.append(dict(column=col, guide_definition=desc, unit=unit, resolution=res, source=src,
                         observed_min=float(x.min()), observed_median=float(x.median()), observed_max=float(x.max()),
                         n_missing=int(x.isna().sum()), derived_relation=derived, used_as=use, reason=why))
    return pd.DataFrame(rows)


def missing_outlier_treatment(df: pd.DataFrame, diag: D.Diagnosis, iv: pd.DataFrame) -> pd.DataFrame:
    """결측·이상·결함별 탐지 규칙, 건수, 처리."""
    s = diag.summary
    rain = df.groupby("date")["강수량"]
    rain_days = int((rain.max() > 0).sum())
    rain_monotone = int(rain.apply(lambda v: (v.max() > 0) and v.is_monotonic_increasing).sum())
    hum_run = (df["습도"] == 98).astype(int)
    # 전력 고립 급등락: 앞뒤 구간과 모두 40 이상 차이 나는 단일 구간(정전 제외)
    yv = iv["y_raw"].to_numpy()
    d1, d2 = yv[1:-1] - yv[:-2], yv[1:-1] - yv[2:]
    spikes = int(np.nansum((np.abs(d1) >= 40) & (np.abs(d2) >= 40) & (np.sign(d1) == np.sign(d2))
                           & (yv[1:-1] > 0) & (yv[:-2] > 0) & (yv[2:] > 0)))
    rows = [
        ("전력 일 단위 복제", "96값이 다른 날짜와 완전히 같음", int(s["copied_power_days"]), "일",
         "복제군에서 정합하는 가장 늦은 날짜만 원본, 나머지 학습·평가 제외", "copy_groups.csv"),
        ("전력 부분 복제", "다른 패턴과 16구간 연속 동일 또는 가동 3시간 이상 동일", len(s["partial_copy_days"]), "일",
         "그날 전체 제외", "days.csv"),
        ("시간 단위 복제", "가동 시간 네 값이 다른 패턴 날짜와 같음", int(sum(s["hour_copies_on_non_copied_days"].values())), "시간",
         "해당 시간 제외(3시간 이상이면 그날 제외)", "hour_copies.csv"),
        ("시간 열 손상", "날짜 안 시간이 0..23 순서가 아님", len(s["corrupt_hour_dates"]), "일", "전력·생산 결측(기상은 행 순서로 배정)", "summary.json"),
        ("전력 0(정전·무계측)", "15분 값 = 0", int(iv["outage"].sum()), "구간", "학습·평가 제외, 구간별 표시", "outage_spans.csv"),
        ("전력–생산 기록 불일치", "야간·주간 전력 수준과 생산 기록이 모순(원본일)", len(s["regime_mismatch_days"]), "일",
         "학습·유사일 풀에서만 제외(사후 판정이라 평가에는 유지)", "days.csv"),
        ("전력 고립 급등락", "앞뒤 구간과 모두 40 이상 같은 방향 차이", spikes, "구간", "없음(처리 불필요)", "-"),
        ("풍속 결측", "NaN", int(df["풍속"].isna().sum()), "행", "입력에서 제외한 변수", "missing.csv"),
        ("강수량 결측", "NaN", int(df["강수량"].isna().sum()), "행", "입력에서 제외한 변수", "missing.csv"),
        ("강수량 누적 성격", "비 온 날 중 하루 안 비감소", rain_monotone, f"일(비 온 {rain_days}일 중)", "입력 제외", "-"),
        ("습도 상한", "습도 = 98", int(hum_run.sum()), "행", "그대로 사용(상한 표시 없음)", "-"),
        ("공장인원 결측", "생산량/전력합 0/0", int(df["공장인원"].isna().sum()), "행", "누설 열이라 입력 제외", "missing.csv"),
        ("생산량 0", "가이드: 빈칸을 0으로 채움 → 결측과 비생산이 섞임", int((df["생산량"] == 0).sum()), "행",
         "시간 값 대신 일 단위 체제만 헤드라인에 사용", "-"),
    ]
    return pd.DataFrame(rows, columns=["item", "detection_rule", "count", "unit", "treatment", "detail_file"])


def preprocessing_waterfall(iv: pd.DataFrame) -> pd.DataFrame:
    """배타·순차 구간 흐름: 전체 → 복제 → 부분 복제 → 손상 → 시간 복제 → 정전 → 평가 가능 → 학습 가능."""
    rem = np.ones(len(iv), bool)
    rows = [dict(step="전체 15분 구간", removed=0, remaining=int(rem.sum()))]
    for name, col in (("일 단위 복제", "copied"), ("부분 복제일", "partial_copy"), ("시간 열 손상일", "corrupt"),
                      ("시간 단위 복제", "hour_copy"), ("전력 0(정전)", "outage")):
        m = rem & iv[col].to_numpy()
        rem &= ~m
        rows.append(dict(step=name, removed=int(m.sum()), remaining=int(rem.sum())))
    assert int(rem.sum()) == int(iv["usable"].sum())
    pre = rem & (iv.index < C.TEST_START)
    rows.append(dict(step="평가 가능: 시험 전(5~7월)", removed=0, remaining=int(pre.sum())))
    rows.append(dict(step="평가 가능: 시험(8/1~9/14)", removed=0, remaining=int((rem & (iv.index >= C.TEST_START)).sum())))
    mis = pre & ~iv["trainable"].to_numpy()
    rows.append(dict(step="학습 가능(시험 전, 전력–생산 불일치일 제외)", removed=int(mis.sum()), remaining=int((pre & ~mis).sum())))
    return pd.DataFrame(rows)


def split_composition(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """분할(교차검증 폴드·시험)별 평가일·체제 구성·피크 양성 수(폴드 기준 T)와 학습 창 길이."""
    rows = []
    for name, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        m = (iv.index >= s) & (iv.index < e) & iv["usable"].to_numpy()
        T = CV.peak_threshold(iv, s)
        dd = pd.DatetimeIndex(np.unique(iv.index[m].normalize()))
        reg = st["regime"].reindex(dd)
        pre = iv.loc[iv.index < s, "trainable"]
        rows.append(dict(split=name, start=s.date(), end=(e - pd.Timedelta(days=1)).date(), eval_days=len(dd),
                         days_full=int((reg == 2).sum()), days_partial=int((reg == 1).sum()), days_stop=int((reg == 0).sum()),
                         eval_intervals=int(m.sum()), T_q95=T, peak_intervals=int((iv["y"].to_numpy()[m] >= T).sum()),
                         peak_base_rate=float((iv["y"].to_numpy()[m] >= T).mean()),
                         train_days_available=int((pre.groupby(pre.index.normalize()).sum() >= 80).sum())))
    return pd.DataFrame(rows)


def imbalance(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """피크(y ≥ 시험 기준 T) 기저율: 월 × 체제 × 시간대(평가 가능 구간)."""
    T = CV.peak_threshold(iv, C.TEST_START)
    u = iv[iv["usable"]]
    band = pd.cut(u["hour"], [-1, 6, 7, 11, 12, 16, 19, 23], labels=["00-06", "07", "08-11", "12", "13-16", "17-19", "20-23"])
    reg = st["regime"].reindex(u.index.normalize()).to_numpy()
    d = pd.DataFrame({"month": u.index.month, "regime": reg, "hour_band": band.astype(str), "peak": u["y"] >= T})
    out = d.groupby(["month", "regime", "hour_band"])["peak"].agg(n="size", positives="sum", base_rate="mean").reset_index()
    out.insert(0, "T", T)
    return out


def production_power_relation(iv: pd.DataFrame, st: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """생산량과 전력의 관계(시험 전 학습 가능 구간). 시간 단위(가동 안 편차)와 날짜 단위를 분리한다."""
    u = iv[iv["trainable"] & (iv.index < C.TEST_START)]
    hourly = u.groupby(u.index.floor("h")).agg(y=("y_train", "mean"), prod=("prod", "first"))
    hourly["date"] = hourly.index.normalize()
    hourly["hour"] = hourly.index.hour
    hourly["regime"] = st["regime"].reindex(hourly["date"]).to_numpy()
    hourly["daytype4"] = st["daytype4"].reindex(hourly["date"]).to_numpy()
    rows = []
    # (1) 가동 주간(전면 가동일 08~19시, 생산 ≥100) 안에서 같은 요일유형·체제 최근 2일 같은 시간 대비 편차의 상관
    w = hourly[(hourly.regime == 2) & hourly.hour.between(8, 19)].copy()
    dev_rows = []
    for (dt, h), g in w.groupby(["daytype4", "hour"]):
        g = g.sort_index()
        ref_y = g["y"].shift(1).rolling(2, min_periods=1).mean()
        ref_p = g["prod"].shift(1).rolling(2, min_periods=1).mean()
        dev_rows.append(pd.DataFrame({"dy": g["y"] - ref_y, "dp": g["prod"] - ref_p, "prod": g["prod"]}))
    dv = pd.concat(dev_rows).dropna()
    dv = dv[dv["prod"] >= 100]
    rows.append(dict(level="hour", scope="전면 가동일 08~19시, 생산≥100: 최근 같은 유형 2일 대비 편차", n=len(dv),
                     pearson=float(dv[["dy", "dp"]].corr().iloc[0, 1])))
    # (2) 가동 주간 원시 상관(시간별 생산량 vs 전력)
    w2 = w[w["prod"] >= 100]
    rows.append(dict(level="hour", scope="전면 가동일 08~19시, 생산≥100: 원시값", n=len(w2),
                     pearson=float(w2[["y", "prod"]].corr().iloc[0, 1])))
    # (3) 날짜 단위: 전면 가동일 일 생산 총량 vs 주간 평균 전력
    day = hourly.groupby("date").agg(y_day=("y", lambda v: v.iloc[8:20].mean() if len(v) >= 20 else np.nan),
                                     prod=("prod", "sum"), regime=("regime", "first"))
    full = day[day.regime == 2].dropna()
    rows.append(dict(level="day", scope="전면 가동일: 일 생산 총량 vs 08~19시 평균 전력", n=len(full),
                     pearson=float(full[["y_day", "prod"]].corr().iloc[0, 1])))
    # (4) 모든 날: 체제(정지/부분/전면)별 주간 평균 전력
    for r, g in day.dropna().groupby("regime"):
        rows.append(dict(level="day", scope=f"체제 {int(r)} 날의 08~19시 평균 전력(평균)", n=len(g), pearson=np.nan,
                         mean_power=float(g["y_day"].mean())))
    # (5) 시간별 생산 프로파일(전면 가동일): 생산 기록이 몰리는 시각
    prof = w.groupby("hour").agg(mean_prod=("prod", "mean"), mean_power=("y", "mean")).reset_index()
    return pd.DataFrame(rows), prof


def operating_states(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """시험 전 학습 가능 구간의 운영 상태별 전력 범위(분위수)와 빈도. 상태는 체제·시각으로 정의한다."""
    u = iv[iv["trainable"] & (iv.index < C.TEST_START)].copy()
    reg = st["regime"].reindex(u.index.normalize()).to_numpy()
    prev = st["regime_prev"].reindex(u.index.normalize()).to_numpy()
    slot = u["slot"].to_numpy()
    h = u["hour"].to_numpy()
    states = {
        "대기(정지일 전 구간)": reg == 0,
        "야간조 이월(전날 가동, 00~06시)": (h < 7) & (prev == 2),
        "야간 정지(전날 정지, 00~06시)": (h < 7) & (prev == 0),
        "기동(전면 가동일 07:30~08:59)": (reg == 2) & (slot >= 30) & (slot <= 35),
        "주간 가동(전면 가동일 09~11·13~16시)": (reg == 2) & (((h >= 9) & (h < 12)) | ((h >= 13) & (h < 16))),
        "점심 저부하(전면 가동일 12시)": (reg == 2) & (h == 12),
        "휴식 저부하(10:00·15:00 구간)": (reg == 2) & np.isin(slot, [40, 60]),
        "저녁(전면 가동일 17~19시)": (reg == 2) & (h >= 17) & (h < 20),
        "야간조(전면 가동일 20~23시)": (reg == 2) & (h >= 20),
    }
    rows = []
    for name, m in states.items():
        v = u["y_train"].to_numpy()[m]
        v = v[np.isfinite(v)]
        if len(v) == 0:
            continue
        rows.append(dict(state=name, n_intervals=len(v), share=len(v) / len(u), p10=float(np.quantile(v, 0.1)),
                         median=float(np.median(v)), p90=float(np.quantile(v, 0.9)), max=float(v.max())))
    return pd.DataFrame(rows)


def origin_sensitivity(df: pd.DataFrame, diag: D.Diagnosis) -> pd.DataFrame:
    """원본 판정 근거의 문턱 민감도: 정합 판정 문턱을 바꿔도 '가장 늦은 구성원 정합 ≫ 가장 이른 구성원 정합'인가."""
    days = diag.days
    corrupt = set(days.index[days["corrupt_hour"]])
    multi = days[days["copy_group_size"] > 1]
    rows = []
    import itertools
    for npw, dpw, dprod, nprod in itertools.product((40, 60, 80), (80, 100, 120), (500, 1000, 3000), (1, 100, 400)):
        if True:
            if True:
                cons = D.consistency_table(df, corrupt, night_power_on=npw, day_power_on=dpw, day_prod_on=dprod,
                                           night_prod_on=nprod)["consistent"]
                g = multi.groupby("power_src")
                first = g.apply(lambda x: cons.get(x.index.min()), include_groups=False)
                last = g.apply(lambda x: cons.get(x.index.max()), include_groups=False)
                single = days.index[(days["copy_group_size"] == 1) & ~days["corrupt_hour"]]
                rows.append(dict(night_power_on=npw, day_power_on=dpw, day_prod_on=dprod, night_prod_on=nprod, groups=len(first),
                                 earliest_consistent=int((first == 1).sum()), latest_consistent=int((last == 1).sum()),
                                 singleton_consistent_share=float(cons.reindex(single).mean())))
    return pd.DataFrame(rows)


def direction_checks(df: pd.DataFrame, diag: D.Diagnosis) -> tuple[pd.DataFrame, dict]:
    """생산 기록을 쓰지 않는 복제 방향 증거(전력·달력·기상만).

    - 자정 연속성: 전날 21~23시 야간조 가동 여부(평균 > 60)와 당일 01~05시 가동 여부가 같은가(실측이면 거의 항상 같다)
    - 휴무 다음 날: 전날이 일요일·공휴일인 평일의 01~05시에 야간조 전력이 있는가(실측이면 거의 없다)
    - 복제군 안: 가장 이른/늦은 구성원의 앞뒤 자정 연속성
    - 기상(약함): 가동 패턴 복제군의 13~16시 고원 전력과 일 최고기온 상관(가장 늦은/이른 날짜 기준)
    """
    from scipy.stats import pearsonr
    P = C.POWER_COLS
    hr = df["시간"]
    pw = df[P].mean(axis=1)
    g = df["date"]
    days = diag.days
    corrupt = set(days.index[days["corrupt_hour"]])
    night = pw[(hr >= 1) & (hr <= 5)].groupby(g[(hr >= 1) & (hr <= 5)]).mean() > C.NIGHT_POWER_ON
    eve = pw[(hr >= 21) & (hr <= 23)].groupby(g[(hr >= 21) & (hr <= 23)]).mean() > C.EVENING_POWER_ON
    plateau = pw[(hr >= 13) & (hr <= 16)].groupby(g[(hr >= 13) & (hr <= 16)]).mean()
    tmax = df.groupby("date")["기온"].max()
    idx = pd.DatetimeIndex(sorted(g.unique()))
    one = pd.Timedelta(days=1)

    def cont_prev(d):
        if d in corrupt or (d - one) in corrupt or (d - one) not in eve.index:
            return np.nan
        return float(eve[d - one] == night[d])

    def cont_next(d):
        if d in corrupt or (d + one) in corrupt or (d + one) not in night.index:
            return np.nan
        return float(eve[d] == night[d + one])

    cp = pd.Series({d: cont_prev(d) for d in idx})
    rows, res = [], {}
    for label, m in (("1~4월", idx < C.MEASURED_START), ("5~9월", idx >= C.MEASURED_START)):
        v = cp[m].dropna()
        rows.append(dict(check="자정 연속성(전날 21~23시 ↔ 당일 01~05시)", subset=label, k=int(v.sum()), n=len(v),
                         rate=float(v.mean())))
    d3 = F.daytype3(idx)
    prev_rest = pd.Series(F.daytype3(idx - one) == 2, index=idx) & pd.Series(d3 == 0, index=idx)
    for label, m in (("1~4월", idx < C.MEASURED_START), ("5~9월", idx >= C.MEASURED_START)):
        dd = idx[m & prev_rest.to_numpy() & ~idx.isin(list(corrupt))]
        v = night.reindex(dd).astype(float)
        rows.append(dict(check="휴무 다음 평일의 01~05시 야간조 전력", subset=label, k=int(v.sum()), n=len(v), rate=float(v.mean())))
    multi = days[days["copy_group_size"] > 1]
    both = {}
    for which in ("earliest", "latest"):
        vals = []
        for _, x in multi.groupby("power_src"):
            d = x.index.min() if which == "earliest" else x.index.max()
            a, b = cont_prev(d), cont_next(d)
            vals.append(np.nan if (np.isnan(a) or np.isnan(b)) else float(a == 1 and b == 1))
        v = pd.Series(vals).dropna()
        both[which] = pd.Series(vals)
        rows.append(dict(check="복제군 구성원의 앞뒤 자정 연속성", subset=f"가장 {'이른' if which == 'earliest' else '늦은'} 구성원",
                         k=int(v.sum()), n=len(v), rate=float(v.mean())))
    only_late = int(((both["latest"] == 1) & (both["earliest"] == 0)).sum())
    only_early = int(((both["latest"] == 0) & (both["earliest"] == 1)).sum())
    rows.append(dict(check="복제군 구성원의 앞뒤 자정 연속성", subset="가장 늦은 쪽만 연속 / 가장 이른 쪽만 연속",
                     k=only_late, n=only_early, rate=np.nan))
    run_groups = [x for _, x in multi.groupby("power_src") if plateau.get(x.index.max(), 0) > C.DAY_POWER_ON]
    for which in ("latest", "earliest"):
        xs = [tmax[(x.index.max() if which == "latest" else x.index.min())] for x in run_groups]
        ys = [plateau[x.index.max()] for x in run_groups]
        r, p = pearsonr(xs, ys) if len(xs) >= 5 else (np.nan, np.nan)
        rows.append(dict(check="가동 패턴 복제군: 13~16시 고원 전력 vs 일 최고기온", subset=f"{'가장 늦은' if which == 'latest' else '가장 이른'} 날짜 기온",
                         k=np.nan, n=len(xs), rate=float(r), p_value=float(p)))
    t = pd.DataFrame(rows)
    res = {f"{r.check}|{r.subset}": (f"{int(r.k)}/{int(r.n)}" if np.isfinite(r.k) and "고원" not in r.check else r.rate)
           for r in t.itertuples()}
    return t, res


def input_support(iv: pd.DataFrame, st: pd.DataFrame) -> pd.DataFrame:
    """정답을 쓰지 않는 입력 지원 점검: 시험 날짜의 (요일유형4, 체제)와 (요일유형4, 체제, 전날 체제) 조합이 시험 전 학습 가능일에
    몇 번 있었는가. 0이면 모델이 외삽한다(예: 하계휴가 평일 정지, 대체공휴일 가동)."""
    days = pd.DatetimeIndex(st.index)
    tr_ok = (iv.groupby("date")["trainable"].sum() >= 80).reindex(days).fillna(False).to_numpy() & (days < C.TEST_START)
    tr = st[tr_ok]
    te = st[(days >= C.TEST_START) & (days < C.TEST_END)]
    k2 = tr.groupby(["daytype4", "regime"]).size()
    k3 = tr.groupby(["daytype4", "regime", "regime_prev"]).size()
    rows = []
    for d, r in te.iterrows():
        a = int(k2.get((r["daytype4"], r["regime"]), 0))
        b = int(k3.get((r["daytype4"], r["regime"], r["regime_prev"]), 0))
        rows.append(dict(date=d, daytype4=r["daytype4"], regime=r["regime"], regime_prev=r["regime_prev"],
                         train_days_same_daytype_regime=a, train_days_same_daytype_regime_prev=b,
                         unseen=("요일유형·체제 조합 없음" if a == 0 else ("전날 체제까지 보면 없음" if b == 0 else ""))))
    return pd.DataFrame(rows)


def run(df: pd.DataFrame, meta: dict, diag: D.Diagnosis, iv: pd.DataFrame) -> dict:
    od = io.out_dir("diagnostics")
    days = diag.days.copy()
    days["daytype3"] = F.daytype3(pd.DatetimeIndex(days.index))
    days["daytype4"] = F.daytype4(pd.DatetimeIndex(days.index))
    days["usable_day"] = iv.groupby("date")["usable"].any().reindex(days.index).to_numpy()
    days["usable_intervals"] = iv.groupby("date")["usable"].sum().reindex(days.index).to_numpy()
    io.write_csv(days.reset_index(), od / "days.csv")
    cm = diag.copied.copy()
    cm["category"] = np.select(
        [cm["src_month"] == 6, (cm["src_month"] == 5) & (cm["month"] <= 4), cm["src_month"] == cm["month"]],
        ["6월 패턴 역채움", "5월 패턴 역채움", "같은 달 안 복제"], default="기타")
    io.write_csv(cm[["date", "weekday", "month", "power_src", "src_month", "src_offset_days", "src_same_weekday",
                     "src_same_dom", "category", "consistent", "prod_total", "power_mean"]], od / "copy_map.csv")
    io.write_csv(diag.copy_groups, od / "copy_groups.csv")
    io.write_csv(origin_sensitivity(df, diag), od / "copy_origin_sensitivity.csv")
    dchk, dres = direction_checks(df, diag)
    io.write_csv(dchk, od / "copy_direction_checks.csv")
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
    io.write_csv(variable_dictionary(df, diag), od / "variable_dictionary.csv")
    io.write_csv(missing_outlier_treatment(df, diag, iv), od / "missing_outlier_treatment.csv")
    io.write_csv(preprocessing_waterfall(iv), od / "preprocessing_waterfall.csv")
    st = F.schedule_table(iv)
    io.write_csv(split_composition(iv, st), od / "split_composition.csv")
    io.write_csv(imbalance(iv, st), od / "imbalance.csv")
    rel, prod_prof = production_power_relation(iv, st)
    io.write_csv(rel, od / "production_power_relation.csv")
    io.write_csv(prod_prof, od / "production_hour_profile_workdays.csv")
    io.write_csv(operating_states(iv, st), od / "operating_states.csv")
    sup = input_support(iv, st)
    io.write_csv(sup, od / "input_support_test_days.csv")

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
        "first_usable_day": str(days.index[days["usable_day"].astype(bool)].min().date()),
        "waterfall_file": "diagnostics/preprocessing_waterfall.csv",
    }

    # 가동일(원본·평일·전면 가동) 슬롯 프로파일(시험 전)과 일 최대 발생 슬롯
    u2 = iv[iv["trainable"] & (iv.index < C.TEST_START)].copy()
    u2["daytype4"] = F.daytype4(u2.index.normalize())
    u2["regime"] = st["regime"].reindex(u2.index.normalize()).to_numpy()
    prof = u2.groupby(["daytype4", "regime", "slot"])["y"].agg(["mean", "std", "count"]).reset_index()
    prof["n_days"] = (prof["count"]).astype(int)
    io.write_csv(prof.drop(columns="n_days"), od / "slot_profile.csv")
    reg_all = st["regime"].reindex(days.index)
    # 전면 가동 평일(평가 가능 구간 90개 이상) — 분석 단계 peak_days와 같은 모집단
    ucount = iv.groupby("date")["usable"].sum().reindex(days.index)
    work_days = days.index[(ucount >= 90).to_numpy() & (days["daytype3"] == 0).to_numpy() & (reg_all == 2).to_numpy()
                           & (days.index >= C.MEASURED_START)]
    w = iv[iv["usable"] & iv.index.normalize().isin(work_days)]
    dmax_slot = w.groupby(w.index.normalize())["y"].idxmax()
    peak_slot = pd.Series([t.hour * 4 + t.minute // 15 for t in dmax_slot], name="slot")
    pk = peak_slot.value_counts().sort_index().rename("n_days").reset_index()
    pk["time"] = [f"{s // 4:02d}:{(s % 4) * 15:02d}" for s in pk["slot"]]
    io.write_csv(pk, od / "daily_max_slot_workdays.csv")
    g = w.pivot_table(index=w.index.normalize(), columns="slot", values="y")
    gv = g.reindex(columns=range(96))
    startup_excess = pd.Series([C.startup_excess(r) for r in gv.to_numpy()], index=gv.index).dropna()

    thr = CV.peak_threshold(iv, C.TEST_START)
    is_start = pd.Series(peak_slot.between(30, 35).to_numpy(), index=[t.month for t in dmax_slot.index])
    month_share = {}
    for mth, v in is_start.groupby(level=0):
        k, n = int(v.sum()), int(len(v))
        lo, hi = _wilson(k, n)
        month_share[int(mth)] = {"share": round(k / n, 3), "k": k, "n": n, "ci90": [round(lo, 3), round(hi, 3)]}
    peak_summary = {
        "T_q95_train_pool": thr,
        "workdays": int(len(work_days)),
        "daily_max_in_0730_0859_by_month": month_share,
        "daily_max_in_0815_0900_share": float(peak_slot.between(33, 35).mean()),
        "startup_excess_median": float(startup_excess.median()),
        "startup_excess_iqr": [float(startup_excess.quantile(0.25)), float(startup_excess.quantile(0.75))],
        "startup_excess_definition": "08:00~08:59 최대 − 09:00~09:59 평균(10:00 휴식 구간 제외, 모든 단계 공통)",
    }
    # 시험 기간 구성(휴가·휴일)
    test_days = days[days.index >= C.TEST_START]
    test_summary = {
        "test_days": int(len(test_days)),
        "test_plan_zero_days": [str(d.date()) for d in test_days.index[test_days["prod_total"] == 0]],
        "test_holidays": [str(d.date()) for d in test_days.index[test_days["holiday"]]],
    }
    summary = {"meta": meta, "diagnosis": diag.summary, "direction_checks_power_only": dres, "usable": usable_summary,
               "peak": peak_summary, "test_composition": test_summary}
    io.write_json(summary, od / "summary.json")
    return summary


def _wilson(k: int, n: int, z: float = 1.645) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h
