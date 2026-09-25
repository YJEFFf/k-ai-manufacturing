"""날짜·시간대 교락 참고 분석 — protocol.json(커밋 b3d6562에 결과 없이 먼저 고정)을 구현한다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python yejun/analysis/press_dayshift/run_analysis.py

참고 자료(KAMP 소성가공 자원최적화, 다른 구축 기관·다른 공정의 프레스 4대)는 대회 프레스의 추가 날짜가 아니다.
결과는 다른 현장의 참고치와 v2 민감도이며 v2 검증·교락 해소가 아니다. v2 산식·문턱·저장 모델은 바꾸지 않는다.
원자료는 ZIP에서 바로 읽고, 저장소에는 일·시간대·구간 단위 집계만 남긴다.
"""
from pathlib import Path
import hashlib
import json
import sys
import time
import unicodedata
import zipfile

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
ROOT = YEJUN.parent
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import GuardModel, D  # noqa: E402  (press_submission 경로도 model.py가 추가한다)

ZIP = ROOT / "데이터셋" / "Dataset_소성가공 자원최적화 AI 데이터셋.zip"
ARTIFACTS = YEJUN / "press_guard" / "artifacts"
PROTOCOL_COMMIT = "b3d6562"
PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))

OPERATING_A = 0.5                 # protocol reference_rules.operating_rule
SENSITIVITY_A = (0.1, 0.5, 2.0)
MIN_DAY_OPERATING = 30            # 약 1시간(2분 간격)
MIN_WINDOW_OPERATING = 10
MIN_DAYS_PRESS = 10
MIN_DAYS_TIME_OF_DAY = 5          # 구현 세부: R2를 해석 규칙에 쓰려면 적격 날 5일 이상(README에 명시)
AMP_MIN_LEN = 17
NIGHT_HOURS, MORNING_HOURS = (0, 1), (10, 11)
ALPHAS = (0.01, 0.03, 0.05)
GRID = np.unique(np.round(np.r_[np.arange(0.50, 1.5001, 0.05), np.arange(0.90, 1.1001, 0.01)], 2))
COLOR_A, COLOR_B = "#b07510", "#178cc2"   # dataviz 검증기 통과 쌍


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def q(x, p):
    x = np.asarray(x, float)
    return float(np.percentile(x, p)) if len(x) else np.nan


# ---------- 참고 자료 ----------
def load_reference():
    frames, members, columns = {}, [], {}
    with zipfile.ZipFile(ZIP) as z:
        if z.testzip() is not None:
            raise ValueError("ZIP CRC 오류")
        for info in z.infolist():
            name = unicodedata.normalize("NFC", info.filename)
            members.append(dict(name=name, bytes=info.file_size, crc32=f"{info.CRC:08x}"))
            if "프레스" in name and name.endswith(".csv"):
                press = int(name.split("프레스")[1].strip()[0])
                raw = pd.read_csv(z.open(info))
                columns[press] = list(raw.columns)
                df = pd.DataFrame({"time": pd.to_datetime(raw.iloc[:, 1]), "rms": pd.to_numeric(raw.iloc[:, 2], errors="coerce")})
                frames[press] = df.sort_values("time").reset_index(drop=True)
    return dict(sorted(frames.items())), members, columns


def reference_quality(frames):
    rows = []
    for press, df in frames.items():
        gaps = df.time.diff().dt.total_seconds().dropna()
        rows.append(dict(press=press, rows=len(df), start=str(df.time.min()), end=str(df.time.max()), days=int(df.time.dt.date.nunique()),
                         missing_values=int(df.rms.isna().sum()), negative_values=int((df.rms < 0).sum()), duplicate_times=int(df.time.duplicated().sum()),
                         gap_median_s=float(gaps.median()), gap_p90_s=float(gaps.quantile(.9)), gap_max_s=float(gaps.max()),
                         operating_fraction_all=float((df.rms >= OPERATING_A).mean())))
    return pd.DataFrame(rows)


def daily_table(frames):
    rows = []
    for threshold in SENSITIVITY_A:
        for press, df in frames.items():
            d = df.dropna().copy()
            d["date"] = d.time.dt.date
            for date, g in d.groupby("date"):
                op = g.rms[g.rms >= threshold]
                ts = pd.Timestamp(date)
                rows.append(dict(press=press, threshold_a=threshold, date=str(date), weekday=ts.day_name(), dayofweek=int(ts.dayofweek),
                                 samples=int(len(g)), operating_samples=int(len(op)), operating_fraction=float(len(op) / len(g)),
                                 included=bool(len(op) >= MIN_DAY_OPERATING),
                                 median_a=float(op.median()) if len(op) else np.nan,
                                 p10_a=float(op.quantile(.1)) if len(op) else np.nan,
                                 p90_a=float(op.quantile(.9)) if len(op) else np.nan))
    return pd.DataFrame(rows)


def summarize_ratios(r):
    r = np.asarray(r, float)
    fold = np.maximum(r, 1 / r) if len(r) else r
    return dict(n=int(len(r)), r_p1=q(r, 1), r_p5=q(r, 5), r_p50=q(r, 50), r_p95=q(r, 95), r_p99=q(r, 99),
                r_min=float(r.min()) if len(r) else np.nan, r_max=float(r.max()) if len(r) else np.nan,
                fold_p50=q(fold, 50), fold_p90=q(fold, 90), fold_p95=q(fold, 95), fold_p99=q(fold, 99),
                fold_max=float(fold.max()) if len(fold) else np.nan)


def day_pairs(daily):
    """R1: 포함된 날의 모든 순서쌍 비와 연속한 날 쌍의 비."""
    ratios, rows = {}, []
    for (press, thr), g in daily[daily.included].groupby(["press", "threshold_a"]):
        if len(g) < MIN_DAYS_PRESS:
            rows.append(dict(press=press, threshold_a=thr, pair_type="all", included_days=len(g), press_included=False))
            continue
        m = g.median_a.to_numpy()
        dates = pd.to_datetime(g.date).to_numpy()
        i, j = np.meshgrid(np.arange(len(m)), np.arange(len(m)), indexing="ij")
        off = i != j
        lag = ((dates[j] - dates[i]) / np.timedelta64(1, "D"))
        r_all = (m[j] / m[i])[off]
        r_cons = (m[j] / m[i])[lag == 1]
        ratios[(press, thr)] = dict(all=r_all, consecutive=r_cons)
        for kind, r in (("all", r_all), ("consecutive", r_cons)):
            rows.append(dict(press=press, threshold_a=thr, pair_type=kind, included_days=len(g), press_included=True, **summarize_ratios(r)))
    return pd.DataFrame(rows), ratios


def time_of_day(frames):
    """R2: 같은 날 오전 창(10~11시) 가동 중앙값 / 심야 창(00~01시) 가동 중앙값. R4(사후 추가): 다른 날 오전 / 심야."""
    rows, windows = [], []
    for press, df in frames.items():
        d = df.dropna().copy()
        d = d[d.rms >= OPERATING_A]
        d["date"] = d.time.dt.date
        d["hour"] = d.time.dt.hour
        for date, g in d.groupby("date"):
            night, morning = g.rms[g.hour.isin(NIGHT_HOURS)], g.rms[g.hour.isin(MORNING_HOURS)]
            nm = float(night.median()) if len(night) >= MIN_WINDOW_OPERATING else np.nan
            mm = float(morning.median()) if len(morning) >= MIN_WINDOW_OPERATING else np.nan
            ts = pd.Timestamp(date)
            rows.append(dict(press=press, date=str(date), weekday=ts.day_name(), night_operating=int(len(night)), morning_operating=int(len(morning)),
                             night_median_a=nm, morning_median_a=mm, included=bool(np.isfinite(nm) and np.isfinite(mm)),
                             ratio_morning_over_night=mm / nm if np.isfinite(nm) and np.isfinite(mm) else np.nan))
            windows.append(dict(press=press, date=pd.Timestamp(date), night=nm, morning=mm))
    tod = pd.DataFrame(rows)
    win = pd.DataFrame(windows)
    same_day, cross_day = {}, {}
    for press, g in tod.groupby("press"):
        same_day[press] = g[g.included].ratio_morning_over_night.to_numpy()
    for press, g in win.groupby("press"):
        n = g.dropna(subset=["night"]); m = g.dropna(subset=["morning"])
        if len(n) and len(m):
            r = (m.morning.to_numpy()[None, :] / n.night.to_numpy()[:, None])
            diff = m.date.to_numpy()[None, :] != n.date.to_numpy()[:, None]
            cross_day[press] = r[diff]
        else:
            cross_day[press] = np.array([])
    return tod, same_day, cross_day


def weekday_table(daily):
    """R3: 일요일·토요일·평일(월~금)의 가동 비율과 일 중앙값."""
    rows = []
    d = daily[daily.threshold_a.eq(OPERATING_A)]
    for press, g in d.groupby("press"):
        groups = {"sunday": g[g.dayofweek.eq(6)], "saturday": g[g.dayofweek.eq(5)], "weekday_mon_fri": g[g.dayofweek.lt(5)]}
        med = {}
        for name, x in groups.items():
            xi = x[x.included]
            med[name] = float(xi.median_a.median()) if len(xi) else np.nan
            rows.append(dict(press=press, group=name, days=int(len(x)), included_days=int(len(xi)),
                             median_operating_fraction=float(x.operating_fraction.median()) if len(x) else np.nan,
                             median_of_daily_medians_a=med[name], ratio_to_weekday=np.nan))
        for r in rows:
            if r["press"] == press and np.isfinite(med["weekday_mon_fri"]) and np.isfinite(r["median_of_daily_medians_a"]):
                r["ratio_to_weekday"] = r["median_of_daily_medians_a"] / med["weekday_mon_fri"]
    return pd.DataFrame(rows)


# ---------- 대회 자료 ----------
def contest_levels(normal, abnormal):
    rows = []
    for label, f in (("normal", normal), ("abnormal", abnormal)):
        seg = D.segments(f)
        x = f[D.SENSORS[2]].to_numpy(float)
        t = pd.to_datetime(f[D.TIME])
        for s in np.unique(seg):
            idx = np.flatnonzero(seg == s)
            v = x[idx]
            rows.append(dict(set=label, record_id=int(s), start=str(t.iloc[idx[0]]), length=int(len(idx)), reliable=bool(len(idx) >= AMP_MIN_LEN),
                             rms=float(np.sqrt(np.mean(v ** 2))), std=float(v.std(ddof=0)), mean=float(v.mean())))
    seg = pd.DataFrame(rows)
    summary = []
    for basis, stat, subset in (("primary", "rms", "reliable"), ("secondary", "std", "reliable"), ("secondary", "rms", "all")):
        s = seg[seg.reliable] if subset == "reliable" else seg
        n_med = float(s[s.set.eq("normal")][stat].median()); a_med = float(s[s.set.eq("abnormal")][stat].median())
        summary.append(dict(basis=basis, statistic=stat, segments=subset, normal_segments=int(s.set.eq("normal").sum()), abnormal_segments=int(s.set.eq("abnormal").sum()),
                            normal_median=n_med, abnormal_median=a_med, ratio_abnormal_over_normal=a_med / n_med, fold=max(a_med / n_med, n_med / a_med)))
    return seg, pd.DataFrame(summary)


# ---------- 사후 진단(프로토콜 외 추가): 비교 가능성 ----------
def reference_operating_distribution(frames):
    """P2: 참고 현장 가동 표본 RMS의 분위수. 좁으면 부하 변동이 아니라 무부하 운전 전류를 기록한 것이다."""
    rows = []
    for press, df in frames.items():
        op = df.rms[df.rms >= OPERATING_A].dropna()
        row = dict(press=press, operating_samples=int(len(op)), share_above_10a=float((op > 10).mean()) if len(op) else np.nan)
        row.update({f"p{p}_a": q(op, p) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)})
        row["p90_over_p10"] = row["p90_a"] / row["p10_a"] if len(op) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def contest_within_window(seg_levels):
    """P1: 대회 정상 77분 안의 10분·5분 블록 중앙값 / 정상 전체 중앙값(길이 17 이상 구간). 이상 3분 비와 같은 방식의 기간 중앙값 비교."""
    r = seg_levels[seg_levels.reliable].copy()
    r["t"] = pd.to_datetime(r.start, format="mixed")
    n = r[r.set.eq("normal")]
    rows = []
    for stat in ("rms", "std"):
        base = float(n[stat].median())
        abn = float(r[r.set.eq("abnormal")][stat].median()) / base
        for minutes in (10, 5):
            b = n.groupby(n.t.dt.floor(f"{minutes}min"))[stat].agg(["size", "median"])
            b = b[b["size"] >= 10]
            for t, row in b.iterrows():
                rows.append(dict(statistic=stat, block_minutes=minutes, block_start=str(t), segments=int(row["size"]), block_median=float(row["median"]),
                                 relative_to_normal=float(row["median"] / base), abnormal_relative=abn,
                                 block_min_relative=float((b["median"] / base).min()), block_max_relative=float((b["median"] / base).max())))
    return pd.DataFrame(rows)


# ---------- v2 전류 배율 스트레스 ----------
def _alarm_counts(pred, alpha):
    alarm = (np.isfinite(pred.p_value.to_numpy()) & (pred.p_value.to_numpy() <= alpha)).astype(int)
    per = pd.Series(alarm).groupby(pred.record_id.to_numpy()).max()
    return per, alarm


def v2_current_scale(models, normal, abnormal):
    rows = []
    for sid, model in models.items():
        split = D.split_normal(normal, D.segments(normal), sid)
        frames = {"normal": D.inputs_only(split["test"]), "abnormal": D.inputs_only(abnormal)}
        for k in GRID:
            preds = {}
            for label, f in frames.items():
                g = f.copy()
                g[D.SENSORS[2]] = g[D.SENSORS[2]].astype(float) * k
                preds[label] = model.predict(g, 0.01)
            for alpha in ALPHAS:
                pn, an = _alarm_counts(preds["normal"], alpha)
                pa, aa = _alarm_counts(preds["abnormal"], alpha)
                rows.append(dict(split_id=sid, k=float(k), alpha=alpha, normal_segments=int(len(pn)), normal_notified_segments=int(pn.sum()),
                                 normal_alarm_rows=int(an.sum()), abnormal_segments=int(len(pa)), abnormal_detected_segments=int(pa.sum()),
                                 abnormal_fn_rows=int((aa == 0).sum()), abnormal_rows=int(len(aa))))
        print(f"  v2 {sid}: 전류 배율 {len(GRID)}개", flush=True)
    return pd.DataFrame(rows)


def tolerance_band(scale):
    s = scale[scale.alpha.eq(0.01)]
    base = s[np.isclose(s.k, 1.0)].set_index("split_id").normal_notified_segments
    ks = np.array(sorted(s.k.unique()))
    ok = np.array([all(int(s[np.isclose(s.k, k) & s.split_id.eq(sid)].normal_notified_segments.iloc[0]) <= int(base[sid]) for sid in base.index) for k in ks])
    i1 = int(np.flatnonzero(np.isclose(ks, 1.0))[0])
    lo = i1
    while lo - 1 >= 0 and ok[lo - 1]:
        lo -= 1
    hi = i1
    while hi + 1 < len(ks) and ok[hi + 1]:
        hi += 1
    return dict(k_low=float(ks[lo]), k_high=float(ks[hi]), first_fail_below=float(ks[lo - 1]) if lo > 0 else None,
                first_fail_above=float(ks[hi + 1]) if hi + 1 < len(ks) else None, baseline_normal_notified={k: int(v) for k, v in base.items()},
                grid_min=float(ks.min()), grid_max=float(ks.max()))


def abnormal_level_normalized(models, abnormal, k_abn):
    rows = []
    f = D.inputs_only(abnormal).copy()
    f[D.SENSORS[2]] = f[D.SENSORS[2]].astype(float) * k_abn
    for sid, model in models.items():
        pred = model.predict(f, 0.01)
        base = model.predict(D.inputs_only(abnormal), 0.01)
        for alpha in ALPHAS:
            per, alarm = _alarm_counts(pred, alpha)
            per0, alarm0 = _alarm_counts(base, alpha)
            rows.append(dict(split_id=sid, k_abnormal=float(k_abn), alpha=alpha, detected_segments=int(per.sum()), segments=int(len(per)),
                             fn_rows=int((alarm == 0).sum()), baseline_detected_segments=int(per0.sum()), baseline_fn_rows=int((alarm0 == 0).sum()),
                             lost_segments=" ".join(str(int(r)) for r in per.index[(per == 0).to_numpy()])))
    return pd.DataFrame(rows)


# ---------- 결합·해석 ----------
def combination(pairs_ratios, same_day, cross_day, band, c_ratio, presses):
    c_fold = max(c_ratio, 1 / c_ratio)
    rows = []
    for press in presses:
        r1 = pairs_ratios[(press, OPERATING_A)]["all"]
        r2 = same_day.get(press, np.array([]))
        r4 = cross_day.get(press, np.array([]))
        for metric, r in (("R1_day_to_day", r1), ("R1_consecutive", pairs_ratios[(press, OPERATING_A)]["consecutive"]),
                          ("R2_same_day_morning_over_night", r2), ("R4_posthoc_other_day_morning_over_night", r4)):
            if not len(r):
                rows.append(dict(press=press, metric=metric, n=0))
                continue
            fold = np.maximum(r, 1 / r)
            rows.append(dict(press=press, metric=metric, n=int(len(r)), **{k: v for k, v in summarize_ratios(r).items() if k != "n"},
                             outside_band_fraction=float(np.mean((r < band["k_low"]) | (r > band["k_high"]))),
                             contest_fold=c_fold, contest_fold_percentile=float(np.mean(fold <= c_fold) * 100)))
    return pd.DataFrame(rows)


def level_rule_all_bases(comb, level_summary, presses):
    """프로토콜 2차 지표(표준편차 기준, 전체 구간)에도 같은 C1 규칙을 적용한 결과. 1차 판정은 verdicts()가 낸다."""
    out = {}
    for row in level_summary.itertuples():
        fold = row.fold
        above = all(fold > comb[(comb.press == p) & (comb.metric == m)].fold_p99.iloc[0] for p in presses for m in ("R1_day_to_day", "R2_same_day_morning_over_night"))
        within = any(fold <= comb[(comb.press == p) & (comb.metric == m)].fold_p95.iloc[0] for p in presses for m in ("R1_day_to_day", "R2_same_day_morning_over_night"))
        out[f"{row.statistic}_{row.segments}"] = dict(ratio=row.ratio_abnormal_over_normal, fold=fold,
                                                      rule="exceeds_reference_variation" if above else ("indistinguishable_from_reference_variation" if within else "borderline"))
    return out


def verdicts(comb, band, s2, presses):
    usable = {}
    for press in presses:
        r1 = comb[(comb.press == press) & (comb.metric == "R1_day_to_day")].iloc[0]
        r2 = comb[(comb.press == press) & (comb.metric == "R2_same_day_morning_over_night")].iloc[0]
        usable[press] = dict(r1=r1, r2=r2 if r2.n >= MIN_DAYS_TIME_OF_DAY else None)
    c_fold = float(comb.contest_fold.dropna().iloc[0])
    above99 = all(c_fold > u["r1"].fold_p99 and (u["r2"] is None or c_fold > u["r2"].fold_p99) for u in usable.values())
    within95 = any(c_fold <= u["r1"].fold_p95 or (u["r2"] is not None and c_fold <= u["r2"].fold_p95) for u in usable.values())
    level = "exceeds_reference_variation" if above99 else ("indistinguishable_from_reference_variation" if within95 else "borderline")
    band_ok = all(u["r1"].r_p5 >= band["k_low"] and u["r1"].r_p95 <= band["k_high"] for u in usable.values())
    s2_ok = bool((s2[s2.alpha.eq(0.01)].detected_segments == 21).all())
    return dict(contest_fold=c_fold, level_rule=level, r2_available={p: u["r2"] is not None for p, u in usable.items()},
                band_rule="reference_day_variation_within_band" if band_ok else "reference_day_variation_exceeds_band",
                s2_rule="detection_not_level_dependent" if s2_ok else "detection_lost_some_segments")


# ---------- 그림 ----------
def figures(daily, band, c_ratio, scale, pair_summary, presses, within):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": ["Apple SD Gothic Neo", "AppleGothic", "Nanum Gothic", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 8.5})
    d = daily[daily.threshold_a.eq(OPERATING_A) & daily.included & daily.press.isin(presses)].copy()
    d["date"] = pd.to_datetime(d.date)
    blocks = within[(within.statistic == "rms") & (within.block_minutes == 10)].copy()
    blocks["t"] = pd.to_datetime(blocks.block_start)
    press_colors = {1: "#6d55c9", 2: "#178cc2"}          # dataviz 검증기 통과 3색(#6d55c9·#178cc2·#b07510)
    ylo = min(0.8, blocks.relative_to_normal.min() - 0.05); yhi = max(1.4, float(blocks.abnormal_relative.iloc[0]) + 0.08)
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.5), sharey=True, gridspec_kw={"width_ratios": [1.6, 1]})
    ax = axes[0]
    for press in presses:
        g = d[d.press.eq(press)].sort_values("date")
        rel = g.median_a / g.median_a.median()
        ax.plot(g.date, rel, color=press_colors.get(press, "#566469"), linewidth=1.6, marker="o", markersize=3, label=f"프레스 {press}호 ({len(g)}일)")
        ax.text(g.date.iloc[-1], rel.iloc[-1] + (0.02 if press == presses[0] else -0.035), f" {press}호", color=press_colors.get(press, "#566469"), fontsize=7.5)
    ax.axhline(1.0, color="#9aa7ad", linewidth=0.8)
    ax.set_ylim(ylo, yhi); ax.set_ylabel("기간 중앙 전류 / 전체 중앙")
    ax.set_title("참고 현장(다른 공정) 유압모터 · 일 중앙값 46일", fontsize=9)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7); ax.legend(frameon=False, fontsize=7.5, loc="upper left")
    ax = axes[1]
    ax.plot(blocks.t, blocks.relative_to_normal, color="#3b4a50", linewidth=1.6, marker="o", markersize=3.5, label="대회 정상 10분 블록 중앙값")
    ax.axhline(1.0, color="#9aa7ad", linewidth=0.8)
    abn = float(blocks.abnormal_relative.iloc[0])
    ax.axhline(abn, color="#b07510", linewidth=1.4, linestyle="--")
    ax.text(blocks.t.iloc[0], abn + 0.015, f"이상 3분(07-17 10:51) 중앙값 {abn:.2f}", color="#b07510", fontsize=7.5)
    ax.set_title("대회 프레스 · 정상 07-12 00:00~01:17", fontsize=9)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    for a in axes:
        a.spines[["top", "right"]].set_visible(False); a.grid(axis="y", color="#eef1f2")
    fig.suptitle("전류 수준의 기간 중앙값 변동: 참고 현장은 46일간 ±4% 안, 대회 정상은 77분 안에서 0.85~1.29배", fontsize=9)
    fig.tight_layout()
    fig.savefig(HERE / "fig_reference_daily.png", dpi=150)
    plt.close(fig)

    s = scale[scale.alpha.eq(0.01)]
    lo = min(pair_summary[(pair_summary.threshold_a == OPERATING_A) & (pair_summary.pair_type == "all") & pair_summary.press.isin(presses)].r_p5)
    hi = max(pair_summary[(pair_summary.threshold_a == OPERATING_A) & (pair_summary.pair_type == "all") & pair_summary.press.isin(presses)].r_p95)
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.2), sharex=True)
    from matplotlib.ticker import MaxNLocator
    for ax, col, title in ((axes[0], "normal_notified_segments", "정상 평가 구간 중 알림 구간 수"), (axes[1], "abnormal_fn_rows", "이상 600행 중 미탐 행 수")):
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.axvspan(lo, hi, color="#e6ecee", zorder=0)
        for sid, color, marker in (("A", COLOR_A, "o"), ("B", COLOR_B, "D")):
            g = s[s.split_id.eq(sid)].sort_values("k")
            ax.plot(g.k, g[col], color=color, linewidth=1.8, marker=marker, markersize=3.5, label=f"분할 {sid}")
        ax.axvline(1.0, color="#9aa7ad", linewidth=0.8)
        ax.set_title(title, fontsize=9)
        ax.set_xlabel("전류에 곱한 배율 k (진동 불변, α=1%)")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(color="#eef1f2")
    axes[0].text(lo, axes[0].get_ylim()[1] * 0.92, " 참고 현장 날짜 간 비 5~95%", fontsize=7.5, color="#566469")
    if band["first_fail_above"] is not None:
        axes[0].axvline(band["first_fail_above"], color="#b3412e", linewidth=0.9, linestyle=":")
        axes[0].text(band["first_fail_above"], axes[0].get_ylim()[1] * 0.55, f" k={band['first_fail_above']:.2f}부터\n 분할 B 정상 알림 증가", color="#b3412e", fontsize=7.5)
    axes[0].legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, 0.85))
    detected = s.groupby("split_id").abnormal_detected_segments.agg(["min", "max"])
    det_text = " · ".join(f"{sid} {int(r['min'])}/21" if r["min"] == r["max"] else f"{sid} {int(r['min'])}~{int(r['max'])}/21" for sid, r in detected.iterrows())
    axes[1].text(0.98, 0.95, "이상 구간 탐지(모든 k): " + det_text,
                 transform=axes[1].transAxes, ha="right", va="top", fontsize=7.5, color="#3b4a50")
    fig.suptitle("v2 전류 수준 스트레스: 저장 모델 그대로, 전류만 배율 조정", fontsize=9)
    fig.tight_layout()
    fig.savefig(HERE / "fig_v2_current_scale.png", dpi=150)
    plt.close(fig)


def main():
    start = time.monotonic()
    frames, members, columns = load_reference()
    quality = reference_quality(frames)
    daily = daily_table(frames)
    pair_summary, pair_ratios = day_pairs(daily)
    tod, same_day, cross_day = time_of_day(frames)
    weekday = weekday_table(daily)
    presses = sorted(p for (p, thr) in pair_ratios if thr == OPERATING_A)
    print("참고 프레스(포함):", presses, flush=True)

    normal, abnormal, load_report = D.load()
    seg_levels, level_summary = contest_levels(normal, abnormal)
    c_ratio = float(level_summary[level_summary.basis.eq("primary")].ratio_abnormal_over_normal.iloc[0])
    print(f"대회 전류 RMS 비(이상/정상, 길이≥17): {c_ratio:.4f}", flush=True)

    models = {sid: GuardModel.load(ARTIFACTS / f"guard_{sid}.json") for sid in D.SPLITS}
    scale = v2_current_scale(models, normal, abnormal)
    base = scale[np.isclose(scale.k, 1.0) & scale.alpha.eq(0.01)].set_index("split_id")
    expected = {"A": (0, 21, 44), "B": (3, 21, 31)}   # press_guard/outputs/metrics.csv의 α=1% 주 결과
    for sid, (nn, ad, fn) in expected.items():
        got = (int(base.loc[sid, "normal_notified_segments"]), int(base.loc[sid, "abnormal_detected_segments"]), int(base.loc[sid, "abnormal_fn_rows"]))
        assert got == (nn, ad, fn), (sid, got)
    band = tolerance_band(scale)
    s2 = abnormal_level_normalized(models, abnormal, 1 / c_ratio)
    comb = combination(pair_ratios, same_day, cross_day, band, c_ratio, presses)
    verdict = verdicts(comb, band, s2, presses)
    verdict["level_rule_all_bases"] = level_rule_all_bases(comb, level_summary, presses)
    operating = reference_operating_distribution(frames)
    within = contest_within_window(seg_levels)
    w10 = within[(within.statistic == "rms") & (within.block_minutes == 10)]
    ref_within_day = float(daily[daily.threshold_a.eq(OPERATING_A) & daily.included].eval("p90_a / p10_a").median())
    verdict["posthoc_comparability"] = dict(
        reference_operating_p1_p99={int(r.press): [round(r.p1_a, 3), round(r.p99_a, 3)] for r in operating[operating.press.isin(presses)].itertuples()},
        reference_within_day_p90_over_p10_median=ref_within_day,
        contest_normal_10min_block_relative_range=[float(w10.block_min_relative.iloc[0]), float(w10.block_max_relative.iloc[0])],
        contest_abnormal_relative=float(w10.abnormal_relative.iloc[0]),
        abnormal_within_normal_block_range=bool(w10.block_min_relative.iloc[0] <= w10.abnormal_relative.iloc[0] <= w10.block_max_relative.iloc[0] * 1.02),
        note="참고 현장 전류는 가동 중 거의 일정한 무부하 운전 전류라 대회 전류와 비교 가능한 양이 아니다. 대회 정상 77분 안의 10분 블록 변동이 이상 3분의 수준 차이와 비슷하다. 사전 규칙의 exceeds 판정은 교락 반박 근거로 쓰지 않는다.")

    quality.to_csv(HERE / "reference_quality.csv", index=False)
    daily.to_csv(HERE / "reference_daily.csv", index=False)
    pair_summary.to_csv(HERE / "reference_pairs_summary.csv", index=False)
    tod.to_csv(HERE / "reference_time_of_day.csv", index=False)
    weekday.to_csv(HERE / "reference_weekday.csv", index=False)
    seg_levels.to_csv(HERE / "contest_segment_rms.csv", index=False)
    level_summary.to_csv(HERE / "contest_level_summary.csv", index=False)
    scale.to_csv(HERE / "v2_current_scale.csv", index=False)
    s2.to_csv(HERE / "v2_abnormal_level_normalized.csv", index=False)
    comb.to_csv(HERE / "combination.csv", index=False)
    operating.to_csv(HERE / "reference_operating_distribution.csv", index=False)
    within.to_csv(HERE / "contest_within_window.csv", index=False)
    figures(daily, band, c_ratio, scale, pair_summary, presses, within)

    provenance = dict(PROTOCOL["provenance"], reference_zip=str(ZIP.relative_to(ROOT)), reference_zip_sha256=sha256(ZIP), reference_members=members,
                      reference_columns={str(k): v for k, v in columns.items()},
                      contest_recording=dict(normal="2022-07-12(화) 00:00:00~01:16:55, 600구간", abnormal="2022-07-17(일) 10:51:07~10:53:53, 21구간"))
    D.dump_json(provenance, HERE / "provenance.json")
    manifest = dict(protocol_commit=PROTOCOL_COMMIT, protocol_sha256=sha256(HERE / "protocol.json"), script_sha256=sha256(Path(__file__)),
                    contest_inputs={k: v["sha256"] for k, v in load_report["files"].items()}, reference_zip_sha256=provenance["reference_zip_sha256"],
                    v2_artifacts={p.name: sha256(p) for p in sorted(ARTIFACTS.glob("guard_*.json"))},
                    settings=dict(operating_a=OPERATING_A, sensitivity_a=SENSITIVITY_A, min_day_operating=MIN_DAY_OPERATING, min_window_operating=MIN_WINDOW_OPERATING,
                                  min_days_press=MIN_DAYS_PRESS, min_days_time_of_day=MIN_DAYS_TIME_OF_DAY, night_hours=NIGHT_HOURS, morning_hours=MORNING_HOURS,
                                  grid=GRID.tolist(), alphas=ALPHAS, amp_min_len=AMP_MIN_LEN),
                    presses_included=presses, contest_rms_ratio=c_ratio, tolerance_band=band, verdict=verdict,
                    posthoc_additions=["R4: 다른 날 오전 창 / 심야 창 비(대회 구조와 같은 날짜+시간대 차이). 프로토콜 외 추가, 해석 규칙에 쓰지 않음",
                                       "reference_quality.csv: 파일 품질 요약. 프로토콜 외 추가",
                                       "P1 contest_within_window.csv: 대회 정상 77분 안의 10·5분 블록 중앙값 비. 결과를 본 뒤 추가",
                                       "P2 reference_operating_distribution.csv: 참고 현장 가동 전류 분위수. 결과를 본 뒤 추가",
                                       "level_rule_all_bases: 프로토콜 2차 지표에 C1 규칙 적용",
                                       "fig_reference_daily.png: 참고 현장 일 중앙값과 대회 정상 10분 블록을 같은 축에 비교하도록 설계 변경"],
                    environment=D.environment(), elapsed_s=round(time.monotonic() - start, 1))
    D.dump_json(manifest, HERE / "manifest.json")
    print(json.dumps(D.to_jsonable(dict(band=band, verdict=verdict)), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
