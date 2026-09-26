"""분석용 그림(보고서 그림 아님). 기준 팔레트(파랑·주황·청록·노랑 순서 고정), 얇은 선, 옅은 격자, 한 축.

색 검증: 앞 네 색은 dataviz 검증 스크립트로 명도·채도·색각이상 구분 통과, 청록·노랑은 밝은 바탕 대비 3:1 미만이라
범례와 직접 표기를 함께 둔다. 발산형(기술점수)은 파랑↔빨강, 0은 회색.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from . import config as C  # noqa: E402
from . import io  # noqa: E402
from . import stage_models as SM  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SEQ = LinearSegmentedColormap.from_list("seq_blue", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
DIV = LinearSegmentedColormap.from_list("div_red_blue", ["#e34948", "#f0efec", "#2a78d6"])


KOREAN_FONTS = ["Apple SD Gothic Neo", "AppleGothic", "Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR"]


def _style():
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    found = [f for f in KOREAN_FONTS if f in have]
    if not found:
        print("[figures] 경고: 한글 글꼴(Apple SD Gothic Neo·맑은 고딕·나눔고딕·Noto Sans CJK KR)을 찾지 못해 "
              "그림의 한글이 깨질 수 있다. 수치 산출물(CSV/JSON)에는 영향이 없다.", flush=True)
    plt.rcParams.update({
        "font.family": found + ["DejaVu Sans"],
        "axes.unicode_minus": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
        "axes.spines.right": False, "lines.linewidth": 1.6, "font.size": 9, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.titlecolor": INK, "legend.frameon": False, "savefig.dpi": 150,
    })


def _save(fig, name):
    p = io.out_dir("figures") / name
    fig.savefig(p, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def _read(rel):
    p = C.OUTPUT_DIR / rel
    if not p.exists():
        raise FileNotFoundError(p)
    return pd.read_csv(p) if p.suffix == ".csv" else json.loads(p.read_text(encoding="utf-8"))


def fig_copy_forensics(iv: pd.DataFrame):
    """날짜×슬롯 전력 히트맵과 복제·부분 복제·손상·불일치 표시, 실측 시작선."""
    days = pd.read_csv(C.OUTPUT_DIR / "diagnostics" / "days.csv", parse_dates=["date"]).set_index("date")
    Y = iv["y_raw"].to_numpy().reshape(-1, 96)
    fig, ax = plt.subplots(figsize=(9, 7.5))
    im = ax.imshow(Y, aspect="auto", cmap=SEQ, interpolation="nearest", vmin=0, vmax=220)
    ax.set_xticks(range(0, 96, 8), [f"{h:02d}시" for h in range(0, 24, 2)])
    ticks = [i for i, d in enumerate(days.index) if d.day == 1]
    ax.set_yticks(ticks, [days.index[i].strftime("%m월") for i in ticks])
    flags = {"복제일(다른 날짜의 96값 사본)": ("copied", SERIES[1]), "부분 복제일": ("partial_copy", SERIES[3]),
             "시간 열 손상": ("corrupt_hour", SERIES[7]), "전력–생산 기록 불일치": ("regime_mismatch", SERIES[6])}
    for k, (label, (col, colr)) in enumerate(flags.items()):
        rows = np.where(days[col].to_numpy().astype(bool))[0]
        ax.scatter(np.full(len(rows), 97.5 + 1.2 * k), rows, s=6, marker="s", color=colr, label=label, clip_on=False)
    start = int(np.where(days.index == C.MEASURED_START)[0][0])
    ax.axhline(start - 0.5, color=INK, linewidth=1.0)
    ax.text(1, start - 1.5, "실측 시작(5/1) — 위쪽 1~4월은 5·6월 패턴의 역채움", fontsize=8, color=INK)
    ax.set_xlim(-0.5, 103)
    ax.grid(False)
    ax.set_title("일별 15분 전력 패턴과 데이터 결함 표시(오른쪽 표식)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.16)
    cb.set_label("15분 최대수요전력(원자료 단위)")
    _save(fig, "01_copy_forensics_heatmap.png")


def fig_copy_direction():
    """복제군별 구성원: 달력·생산 정합(채움)/모순(빈 원), 원본(가장 늦은 정합 구성원) 표시."""
    g = _read("diagnostics/copy_groups.csv")
    g["date"] = pd.to_datetime(g["date"])
    g["group_origin"] = pd.to_datetime(g["group_origin"])
    order = sorted(g["group_origin"].unique())
    ypos = {o: i for i, o in enumerate(order)}
    fig, ax = plt.subplots(figsize=(9, 7))
    for _, r in g.iterrows():
        y = ypos[r["group_origin"]]
        ok = r["consistent"] == 1
        ax.scatter(r["date"], y, s=26, marker="o", facecolor=SERIES[0] if ok else SURFACE,
                   edgecolor=SERIES[0] if ok else SERIES[7], linewidth=1.2, zorder=3)
        if r["is_origin"]:
            ax.scatter(r["date"], y, s=90, marker="o", facecolor="none", edgecolor=INK, linewidth=1.0, zorder=4)
    for o in order:
        mem = g[g.group_origin == o]["date"]
        ax.plot([mem.min(), mem.max()], [ypos[o]] * 2, color=GRID, linewidth=1.0, zorder=1)
    ax.axvline(C.MEASURED_START, color=INK2, linewidth=0.8, linestyle="--")
    ax.set_yticks([])
    ax.set_ylabel(f"복제군 {len(order)}개(원본 날짜 순)")
    s = _read("diagnostics/summary.json")["diagnosis"]
    ax.set_title(f"복제군 구성원의 달력·생산 정합: 가장 늦은 구성원 {s['copy_groups_latest_member_consistent']}, "
                 f"가장 이른 구성원 {s['copy_groups_earliest_member_consistent']}", fontsize=10)
    h = [plt.Line2D([], [], marker="o", linestyle="", markerfacecolor=SERIES[0], markeredgecolor=SERIES[0], label="전력 패턴이 그 날짜의 달력·생산과 정합"),
         plt.Line2D([], [], marker="o", linestyle="", markerfacecolor=SURFACE, markeredgecolor=SERIES[7], label="모순(예: 일요일·생산 0인데 가동 전력)"),
         plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="none", markeredgecolor=INK, markersize=10, label="원본으로 판정(정합하는 가장 늦은 날짜)")]
    ax.legend(handles=h, loc="lower left", fontsize=8)
    _save(fig, "01b_copy_direction.png")


def fig_profiles(iv: pd.DataFrame):
    prof = pd.read_csv(C.OUTPUT_DIR / "diagnostics" / "slot_profile.csv")
    names = {0: "휴무 다음 평일", 1: "연속 평일", 2: "토요일", 3: "일·공휴일"}
    fig, ax = plt.subplots(figsize=(9, 3.6))
    x = np.arange(96) / 4
    for i, (d4, lab) in enumerate(names.items()):
        sub = prof[prof.daytype4 == d4]
        if sub.empty:
            continue
        ndays = sub[sub.slot == 0].set_index("regime")["count"]
        reg = 2 if d4 < 2 else int(ndays.idxmax())
        s = sub[sub.regime == reg].set_index("slot")["mean"].reindex(range(96))
        n = int(ndays.get(reg, 0))
        ax.plot(x, s.to_numpy(), color=SERIES[i], label=f"{lab}(체제 {reg}, {n}일)")
    ax.set_xticks(range(0, 25, 2))
    ax.set_xlabel("시각")
    ax.set_ylabel("평균 15분 전력")
    ax.set_title("요일유형별 평균 부하 곡선(시험 전 5~7월): 00~07시는 전날 야간조, 08시 기동, 12시 점심")
    ax.legend(ncol=2, loc="upper left", fontsize=8)
    _save(fig, "02_daytype_profiles.png")


def fig_model_comparison():
    cvm = _read("cv/cv_metrics.csv")
    tm = _read("test/test_metrics.csv")
    sel = _read("cv/selection.json")
    for task, fam in (("B", "B"), ("A4", "A")):
        cv = cvm[(cvm.task == task) & (cvm.split == "pooled")].set_index("model")["RMSE"]
        te = tm[(tm.task == task)].set_index("model")["RMSE"]
        order = cv.sort_values().index.tolist()
        fig, ax = plt.subplots(figsize=(8, 0.34 * len(order) + 1.2))
        yy = np.arange(len(order))
        ax.barh(yy - 0.18, cv[order].to_numpy(), height=0.34, color=SERIES[0], label="교차검증(6·7월)")
        ax.barh(yy + 0.18, te.reindex(order).to_numpy(), height=0.34, color=SERIES[1], label="시험(8/1~9/14)")
        ax.set_yticks(yy, [f"{m} ★" if m == sel[fam]["chosen"] else m for m in order])
        ax.invert_yaxis()
        ax.set_xlabel("RMSE(낮을수록 좋음)")
        ax.set_title(("익일 96구간" if task == "B" else "60분 뒤") + " 예측 모델 비교(★ 교차검증 사전 규칙으로 선택)")
        ax.legend(loc="lower right", fontsize=8)
        for i, m in enumerate(order):
            v = te.get(m, np.nan)
            if np.isfinite(v):
                ax.text(v + 0.3, i + 0.18, f"{v:.1f}", va="center", fontsize=7, color=INK2)
        _save(fig, f"03_model_comparison_{task}.png")


def fig_test_timeseries(iv: pd.DataFrame):
    sel = _read("cv/selection.json")
    pB = SM.load_predictions("test", "B")
    pA = SM.load_predictions("test", "A4")
    y = iv["y"]
    for label, (s, e) in {"vacation_return": ("2021-08-06", "2021-08-12"), "sep_workweek": ("2021-09-06", "2021-09-11"),
                          "holiday_work": ("2021-08-13", "2021-08-19")}.items():
        m = (y.index >= s) & (y.index < e)
        fig, ax = plt.subplots(figsize=(10, 3.4))
        ax.plot(y.index[m], y[m], color=INK2, linewidth=1.2, label="실제")
        ax.plot(pB.index, pB[sel["B"]["chosen"]], color=SERIES[0], label=f"익일 예측({sel['B']['chosen']})")
        ax.plot(pA.index, pA[sel["A"]["chosen"]], color=SERIES[1], linewidth=1.2, label=f"60분 뒤 예측({sel['A']['chosen']})")
        ax.set_xlim(pd.Timestamp(s), pd.Timestamp(e))
        ax.set_ylabel("15분 전력")
        ko = {"vacation_return": "하계휴가 뒤 복귀", "sep_workweek": "9월 가동 주", "holiday_work": "대체공휴일 가동 주"}[label]
        ax.set_title(f"시험 구간 예측 예시: {ko}")
        ax.legend(ncol=3, loc="upper left", fontsize=8)
        _save(fig, f"04_test_timeseries_{label}.png")


def fig_peak_conditions():
    dd = _read("analysis/peak_days.csv")
    share = dd.groupby("month")["type"].value_counts(normalize=True).unstack().fillna(0)
    n = dd.groupby("month").size()
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    cols = [c for c in ["startup", "plateau", "other"] if c in share.columns]
    bottom = np.zeros(len(share))
    names = {"startup": "기동형(07:30~08:59 최대)", "plateau": "고원형(09~15시 최대)", "other": "기타"}
    xl = [f"{m}월\n(n={n[m]})" for m in share.index]
    for i, c in enumerate(cols):
        ax.bar(xl, share[c].to_numpy(), bottom=bottom, color=SERIES[i], label=names[c], edgecolor=SURFACE, linewidth=2)
        bottom += share[c].to_numpy()
    ax.set_ylabel("전면 가동 평일 비율")
    ax.set_title("일 최대 발생 유형: 5·6월 기동형 → 7·8월 고원형(냉방)")
    ax.legend(fontsize=8, loc="upper right")
    _save(fig, "05_peak_type_by_month.png")
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for i, (lab, sub) in enumerate({"5~6월(시험 전)": dd[dd.month <= 6], "7월(시험 전)": dd[(dd.month == 7)],
                                    "8~9월(시험)": dd[dd.month >= 8]}.items()):
        ax.scatter(sub["tmax"], sub["plateau"], s=18, color=SERIES[i], label=f"{lab} n={len(sub)}", edgecolor=SURFACE, linewidth=0.6)
    ax.set_xlabel("일 최고기온(°C)")
    ax.set_ylabel("주간 고원 평균 전력")
    ax.set_title("전면 가동 평일의 주간 부하와 기온")
    ax.legend(fontsize=8)
    _save(fig, "06_plateau_vs_tmax.png")


def fig_alarm_calibration():
    g = _read("field/alarm_grades.csv")
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    for i, per in enumerate(["cv", "test"]):
        sub = g[g.period == per]
        mid = (sub.p_lo + sub.p_hi.clip(upper=1.0)) / 2
        ax.plot(mid, sub.observed_rate, marker="o", markersize=5, color=SERIES[i],
                label={"cv": "교차검증(6·7월)", "test": "시험"}[per])
        for x, r, n in zip(mid, sub.observed_rate, sub.n):
            ax.annotate(f"n={n}", (x, r), textcoords="offset points", xytext=(4, -10 if per == "test" else 6),
                        fontsize=7, color=INK2)
    ax.plot([0, 1], [0, 1], color=GRID, linestyle="--", linewidth=1)
    ax.set_xlabel("예측 초과확률 구간 중앙")
    ax.set_ylabel("실제 다음 1시간 피크 비율")
    ax.set_title("경보 등급별 실제 피크 빈도(확률 보정 점검)")
    ax.legend(fontsize=8)
    _save(fig, "07_alarm_grade_calibration.png")


def fig_demand_controller():
    d = _read("field/demand_controller.csv")
    d = d[(d.period == "test") & (d.shed == 0.10) & (d.tau_selection != "candidate")]
    pols = ["model_prob", "reactive_now>=T-5", "clock_0800_fullday", "oracle_perfect"]
    names = {"model_prob": "모델 확률 경보", "reactive_now>=T-5": "현재값 반응(T−5)", "clock_0800_fullday": "08시 고정 차단",
             "oracle_perfect": "완전 예지(상한)"}
    modes = {"none": "되돌림 없음(상한 가정)", "valley": "저부하 시간에 만회", "valley_capped": "여유 구간 만회·차단 직후 재경보",
             "immediate": "직후 1시간에 만회"}
    targets = sorted(d.target.unique())
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.4), sharey=True)
    w = 0.2
    for ax, (mode, title) in zip(axes, modes.items()):
        sub_m = d[d.payback == mode]
        for i, pol in enumerate(pols):
            sub = sub_m[sub_m.policy == pol].set_index("target").reindex(targets)
            ax.bar(np.arange(len(targets)) + (i - 1.5) * w, sub["over_reduction_share"].to_numpy() * 100, width=w,
                   color=SERIES[i], label=names[pol], edgecolor=SURFACE, linewidth=1.2)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_xticks(range(len(targets)), [f"{t:g}" for t in targets])
        ax.set_xlabel("목표전력(시험 전 최대의 88·90·92·95%)")
        ax.set_title(title, fontsize=10)
    axes[0].set_ylabel("목표 초과 15분 구간 감소율(%)")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle("수요제어 시뮬레이션(시험, 제어 가능 부하 10%·30분 차단 가정, 사후 설계)", fontsize=11, fontweight="bold", y=1.04)
    _save(fig, "08_demand_controller.png")


def fig_info_value():
    d = _read("analysis/plan_information_value.csv")
    for task in ("B", "A4"):
        sub = d[d.task == task]
        if sub.empty:
            continue
        levels = list(dict.fromkeys(sub.level))
        fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(levels) + 1.2))
        yy = {lv: i for i, lv in enumerate(levels)}
        for i, (mname, lab) in enumerate((("M1_lgbm", "LightGBM"), ("M7c_hybrid_coolmono", "하이브리드(M7c)"))):
            s = sub[sub.model == mname]
            for per, mk, off in (("cv", "o", -0.12), ("test", "s", 0.12)):
                ax.scatter(s[f"{per}_RMSE"], [yy[lv] + off for lv in s.level], color=SERIES[i], marker=mk, s=30,
                           label=f"{lab} {'교차검증' if per == 'cv' else '시험'}", edgecolor=SURFACE, linewidth=0.6)
        ax.set_yticks(range(len(levels)), levels)
        ax.invert_yaxis()
        ax.set_xlabel("RMSE")
        ax.set_title(("익일" if task == "B" else "60분 뒤") + " 예측의 계획 정보가치(원 = 교차검증, 사각 = 시험)")
        ax.legend(fontsize=7, ncol=2, loc="lower right")
        _save(fig, f"09_plan_information_value_{task}.png")


def fig_interval_coverage():
    d = _read("peak/interval_coverage.csv")
    d = d[(d.alpha == 0.2) & (d.period == "test") & (d.task == "A4")]
    conds = ["all", "work_dayshift", "other", "peak_y>=T"]
    labels = {"all": "전체", "work_dayshift": "가동일 주간", "other": "그 외", "peak_y>=T": "피크 구간"}
    methods = {"rolling_global": "전체 한 분포로 보정", "rolling_mondrian": "가동 체제별 보정", "aci_mondrian": "체제별+적응형"}
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    w = 0.26
    for i, (mth, lab) in enumerate(methods.items()):
        sub = d[d.method == mth].set_index("cond").reindex(conds)
        ax.bar(np.arange(len(conds)) + (i - 1) * w, sub["coverage"].to_numpy() * 100, width=w, color=SERIES[i],
               label=lab, edgecolor=SURFACE, linewidth=1.2)
    ax.axhline(80, color=INK2, linewidth=1, linestyle="--")
    ax.text(len(conds) - 0.5, 81, "명목 80%", fontsize=7, color=INK2, ha="right")
    ax.set_xticks(range(len(conds)), [labels[c] for c in conds])
    ax.set_ylabel("실제 포괄률(%)")
    ax.set_ylim(0, 100)
    ax.set_title("60분 뒤 예측 80% 구간의 조건별 포괄률(시험)")
    ax.legend(fontsize=8, loc="lower left")
    _save(fig, "10_interval_coverage_A4.png")


def fig_learning_curve():
    d = _read("analysis/learning_curve.csv")
    order = ["30", "60", "all"]
    d["w"] = d["train_window_days"].astype(str)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    for ax, task, title in ((axes[0], "A4", "60분 뒤"), (axes[1], "B", "익일")):
        sub = d[d.task == task]
        for i, m in enumerate(sorted(sub.model.unique())):
            t = sub[sub.model == m].set_index("w").reindex(order)
            ax.plot(range(len(order)), t["test_RMSE"].to_numpy(), marker="o", markersize=5, color=SERIES[i], label=m)
        ax.set_xticks(range(len(order)), ["최근 30일", "최근 60일", "전체(5~7월)"])
        ax.set_ylabel("시험 RMSE")
        ax.set_title(f"{title}: 학습 창 길이별 성능(사후 설명용)", fontsize=10)
        ax.legend(fontsize=7)
    _save(fig, "11_learning_curve.png")


def fig_condition_skill():
    """선택 모델의 최강 기준 대비 RMSE 기술점수(조건 × 기간). 파랑 = 기준보다 좋음, 빨강 = 나쁨."""
    d = _read("analysis/condition_skill.csv")
    sel = _read("cv/selection.json")
    keep = ["work_dayshift", "regime", "regime_prev", "daytype4", "window", "temp_bin", "calendar_operation_mismatch",
            "analog_atypical", "holiday_work"]
    for task, fam in (("A4", "A"), ("B", "B")):
        sub = d[(d.task == task) & (d.model == sel[fam]["chosen"]) & d.condition.isin(keep)].copy()
        if sub.empty:
            continue
        bls = list(dict.fromkeys(sub["baseline"]))
        primary = next((b for b in bls if b != "BL3_profile"), bls[0])  # 교차검증 최강 기준(주 비교)
        sub = sub[sub["baseline"] == primary]
        sub["row"] = sub["condition"] + "=" + sub["value"]
        piv = sub.pivot_table(index="row", columns="period", values="skill_vs_baseline")
        nn = sub.pivot_table(index="row", columns="period", values="days")
        piv = piv.reindex(columns=["cv", "test"])
        fig, ax = plt.subplots(figsize=(5.2, 0.28 * len(piv) + 1.4))
        lim = max(0.05, float(np.nanmax(np.abs(piv.to_numpy()))))
        im = ax.imshow(piv.to_numpy(), aspect="auto", cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim))
        ax.set_xticks([0, 1], ["교차검증", "시험"])
        ax.set_yticks(range(len(piv)), piv.index, fontsize=7)
        for i in range(len(piv)):
            for j, col in enumerate(piv.columns):
                v = piv.iloc[i, j]
                if np.isfinite(v):
                    ax.text(j, i, f"{v:+.2f} ({int(nn.iloc[i][col]) if np.isfinite(nn.iloc[i][col]) else 0}일)",
                            ha="center", va="center", fontsize=6.5, color=INK)
        ax.grid(False)
        bl = sub["baseline"].iloc[0]
        ax.set_title(f"{'60분 뒤' if task == 'A4' else '익일'}: {sel[fam]['chosen']}의 {bl} 대비 기술점수", fontsize=9)
        cb = fig.colorbar(im, ax=ax, fraction=0.05)
        cb.set_label("1 − RMSE/RMSE_기준")
        _save(fig, f"12_condition_skill_{task}.png")


def fig_reliability():
    d = _read("peak/next_hour_reliability.csv")
    d = d[(d.period == "test") & (d.calibration == "none")]
    fig, ax = plt.subplots(figsize=(5.6, 4.0))
    names = {"P_residual_sim": "잔차 표집 확률(선택)", "P_lgbm_classifier": "LightGBM 분류기", "P_climatology": "기후값(체제×슬롯)"}
    for i, (m, lab) in enumerate(names.items()):
        s = d[d.method == m]
        ax.plot(s["mean_prob"], s["observed"], marker="o", markersize=5, color=SERIES[i], label=lab)
    ax.plot([0, 1], [0, 1], color=GRID, linestyle="--", linewidth=1)
    ax.set_xlabel("예측 확률(10구간 평균)")
    ax.set_ylabel("실제 비율")
    ax.set_title("다음 1시간 피크 확률의 신뢰도(시험)")
    ax.legend(fontsize=8, loc="upper left")
    _save(fig, "13_reliability_next_hour.png")


def fig_waterfall():
    d = _read("diagnostics/preprocessing_waterfall.csv")
    d = d.iloc[:6]
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    yy = np.arange(len(d))
    ax.barh(yy, d["remaining"], color=SERIES[0], height=0.55)
    for i, r in d.iterrows():
        txt = f"{int(r['remaining']):,}" + (f"  (−{int(r['removed']):,})" if r["removed"] else "")
        ax.text(r["remaining"] + 200, i, txt, va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(yy, d["step"])
    ax.invert_yaxis()
    ax.set_xlabel("남은 15분 구간 수")
    ax.set_xlim(0, d["remaining"].max() * 1.25)
    ax.set_title("전처리 흐름: 전체 → 평가 가능 구간")
    _save(fig, "14_preprocessing_waterfall.png")


def fig_integrated():
    """래칫 사다리(상위 사건을 하나씩 막을 때)와 완전 제어 상한, 운영 절차 정책의 통합 시나리오."""
    lad = _read("field/ratchet_ladder.csv")
    ub = _read("field/ratchet_perfect_control_bound.csv")
    d = _read("field/integrated_scenario.csv")
    fig, axes = plt.subplots(1, 3, figsize=(15, 3.4))
    ax = axes[0]
    ax.plot(lad["step"], lad["ratchet"], marker="o", markersize=5, color=SERIES[0])
    for _, r in lad.iterrows():
        ax.annotate(f"{r['ratchet']:.0f} ({r['change_pct']:+.1f}%)", (r["step"], r["ratchet"]), textcoords="offset points",
                    xytext=(4, 4), fontsize=7, color=INK2)
    ax.set_xlabel("막은 상위 사건 수(7~9월 날짜별 최대 순)")
    ax.set_ylabel("요금적용전력(7~9월 최대)")
    ax.set_title("래칫 사다리: 몇 개의 15분이 1년 기본요금을 정한다", fontsize=10)
    ax = axes[1]
    ax.bar([f"{t:g}" for t in ub["target"]], -ub["change_pct"], color=SERIES[0], edgecolor=SURFACE, linewidth=2)
    for i, r in ub.reset_index(drop=True).iterrows():
        ax.text(i, -r["change_pct"] + 0.2, f"{int(r['intervals_over'])}구간·{int(r['days_over'])}일", ha="center", fontsize=7, color=INK2)
    ax.set_xlabel("목표 T(시험 전 최대의 90~98%)")
    ax.set_ylabel("기본요금 감소 상한(%)")
    ax.set_title("완전 제어 상한: 넘은 구간만 T로 묶을 때", fontsize=10)
    ax = axes[2]
    yy = np.arange(len(d))
    ax.barh(yy, d["ratchet_max_jul_sep"], color=SERIES[0], height=0.55)
    for i, r in d.iterrows():
        ax.text(r["ratchet_max_jul_sep"] + 0.3, i, f"{r['ratchet_max_jul_sep']:.1f} ({r['basic_charge_change_pct']:+.1f}%)",
                va="center", fontsize=7, color=INK2)
    ax.set_yticks(yy, d["scenario"], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(float(d["ratchet_max_jul_sep"].min()) - 12, float(d["ratchet_max_jul_sep"].max()) + 8)
    ax.set_xlabel("요금적용전력(7~9월 최대)")
    ax.set_title("운영 절차 정책의 누적(가정 기반)", fontsize=10)
    _save(fig, "15_integrated_ratchet.png")


def fig_copy_direction_checks():
    """생산 기록을 쓰지 않는 복제 방향 증거(전력·달력만)."""
    t = _read("diagnostics/copy_direction_checks.csv")
    t = t[t["rate"].notna() & ~t["check"].str.contains("고원")]
    fig, ax = plt.subplots(figsize=(7.5, 3.0))
    labels = [f"{c.split('(')[0]} | {s}" for c, s in zip(t["check"], t["subset"])]
    yy = np.arange(len(t))
    cols = [SERIES[0] if ("5~9월" in s or "늦은" in s) else SERIES[1] for s in t["subset"]]
    ax.barh(yy, t["rate"] * 100, color=cols, height=0.55)
    for i, (r, k, n) in enumerate(zip(t["rate"], t["k"], t["n"])):
        ax.text(r * 100 + 1, i, f"{r * 100:.0f}% ({int(k)}/{int(n)})", va="center", fontsize=7.5, color=INK2)
    ax.set_yticks(yy, labels, fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlim(0, 115)
    ax.set_xlabel("비율(%)")
    ax.set_title("복제 방향의 생산 무관 증거: 5~9월·가장 늦은 구성원만 실측처럼 이어진다", fontsize=10)
    _save(fig, "01c_copy_direction_power_only.png")


def run(iv: pd.DataFrame) -> None:
    _style()
    for fn in (fig_copy_forensics, fig_profiles, fig_test_timeseries):
        fn(iv)
    for fn in (fig_copy_direction, fig_copy_direction_checks, fig_model_comparison, fig_peak_conditions, fig_alarm_calibration,
               fig_demand_controller,
               fig_info_value, fig_interval_coverage, fig_learning_curve, fig_condition_skill, fig_reliability,
               fig_waterfall, fig_integrated):
        try:
            fn()
        except FileNotFoundError:
            pass
