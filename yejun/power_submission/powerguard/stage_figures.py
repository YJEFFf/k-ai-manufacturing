"""분석용 그림(보고서 그림 아님). 기준 팔레트(파랑·주황·청록 순서 고정), 얇은 선, 옅은 격자, 한 축."""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from . import config as C  # noqa: E402
from . import features as F  # noqa: E402
from . import io  # noqa: E402
from . import stage_models as SM  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
SEQ = LinearSegmentedColormap.from_list("seq_blue", ["#f4f8fd", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])


def _style():
    plt.rcParams.update({
        "font.family": ["Apple SD Gothic Neo", "NanumGothic", "AppleGothic", "DejaVu Sans"],
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


def fig_copy_forensics(iv: pd.DataFrame):
    """날짜×슬롯 전력 히트맵과 복제·부분 복제·손상·정전 표시."""
    days = pd.read_csv(C.OUTPUT_DIR / "diagnostics" / "days.csv", parse_dates=["date"]).set_index("date")
    Y = iv["y_raw"].to_numpy().reshape(-1, 96)
    fig, ax = plt.subplots(figsize=(9, 7.5))
    im = ax.imshow(Y, aspect="auto", cmap=SEQ, interpolation="nearest", vmin=0, vmax=220)
    ax.set_xticks(range(0, 96, 8), [f"{h:02d}시" for h in range(0, 24, 2)])
    ticks = [i for i, d in enumerate(days.index) if d.day == 1]
    ax.set_yticks(ticks, [days.index[i].strftime("%m월") for i in ticks])
    flags = {"복제일(전력 96값 동일)": ("copied", SERIES[1]), "부분 복제일": ("partial_copy", SERIES[3]),
             "시간 열 손상": ("corrupt_hour", SERIES[7])}
    for label, (col, colr) in flags.items():
        rows = np.where(days[col].to_numpy())[0]
        ax.scatter(np.full(len(rows), 97.5), rows, s=6, marker="s", color=colr, label=label, clip_on=False)
    ax.set_xlim(-0.5, 99)
    ax.grid(False)
    ax.set_title("일별 15분 전력 패턴과 데이터 결함 표시(오른쪽 표식)")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.12)
    cb.set_label("15분 최대수요전력(원자료 단위)")
    _save(fig, "01_copy_forensics_heatmap.png")


def fig_profiles(iv: pd.DataFrame):
    prof = pd.read_csv(C.OUTPUT_DIR / "diagnostics" / "slot_profile.csv")
    names = {0: "휴무 다음 평일", 1: "연속 평일", 2: "토요일", 3: "일·공휴일"}
    fig, ax = plt.subplots(figsize=(9, 3.6))
    x = np.arange(96) / 4
    for i, (d4, lab) in enumerate(names.items()):
        sub = prof[(prof.daytype4 == d4) & (prof.regime == (2 if d4 < 2 else prof[prof.daytype4 == d4].regime.max()))]
        if sub.empty:
            continue
        s = sub.set_index("slot")["mean"].reindex(range(96))
        ax.plot(x, s.to_numpy(), color=SERIES[i], label=f"{lab}(최다 체제)")
    ax.set_xticks(range(0, 25, 2))
    ax.set_xlabel("시각")
    ax.set_ylabel("평균 15분 전력")
    ax.set_title("요일유형별 평균 부하 곡선: 00~07시는 전날 야간조, 08시 기동, 12시 점심")
    ax.legend(ncol=4, loc="upper left", fontsize=8)
    _save(fig, "02_daytype_profiles.png")


def fig_model_comparison():
    cvm = pd.read_csv(C.OUTPUT_DIR / "cv" / "cv_metrics.csv")
    tm = pd.read_csv(C.OUTPUT_DIR / "test" / "test_metrics.csv")
    sel = json.loads((C.OUTPUT_DIR / "cv" / "selection.json").read_text(encoding="utf-8"))
    for task, fam in (("B", "B"), ("A4", "A")):
        cv = cvm[(cvm.task == task) & (cvm.split == "pooled")].set_index("model")["RMSE"]
        te = tm[(tm.task == task)].set_index("model")["RMSE"]
        order = cv.sort_values().index.tolist()
        fig, ax = plt.subplots(figsize=(8, 0.34 * len(order) + 1.2))
        yy = np.arange(len(order))
        ax.barh(yy - 0.18, cv[order].to_numpy(), height=0.34, color=SERIES[0], label="교차검증(4·5·7월)")
        ax.barh(yy + 0.18, te.reindex(order).to_numpy(), height=0.34, color=SERIES[1], label="시험(8/1~9/14)")
        ax.set_yticks(yy, [f"{m} ★" if m == sel[fam]["chosen"] else m for m in order])
        ax.invert_yaxis()
        ax.set_xlabel("RMSE(낮을수록 좋음)")
        ax.set_title(("익일 96구간" if task == "B" else "60분 뒤") + " 예측 모델 비교(★ 사전 규칙으로 선택)")
        ax.legend(loc="upper right", fontsize=8)
        for i, m in enumerate(order):
            v = te.get(m, np.nan)
            if np.isfinite(v):
                ax.text(v + 0.3, i + 0.18, f"{v:.1f}", va="center", fontsize=7, color=INK2)
        _save(fig, f"03_model_comparison_{task}.png")


def fig_test_timeseries(iv: pd.DataFrame):
    sel = json.loads((C.OUTPUT_DIR / "cv" / "selection.json").read_text(encoding="utf-8"))
    pB = SM.load_predictions("test", "B")
    pA = SM.load_predictions("test", "A4")
    y = iv["y"]
    for label, (s, e) in {"휴가주_복귀": ("2021-08-06", "2021-08-12"), "9월_가동주": ("2021-09-06", "2021-09-11")}.items():
        m = (y.index >= s) & (y.index < e)
        fig, ax = plt.subplots(figsize=(10, 3.4))
        ax.plot(y.index[m], y[m], color=INK2, linewidth=1.2, label="실제")
        ax.plot(pB.index, pB[sel["B"]["chosen"]], color=SERIES[0], label=f"익일 예측({sel['B']['chosen']})")
        ax.plot(pA.index, pA[sel["A"]["chosen"]], color=SERIES[1], linewidth=1.2, label=f"60분 뒤 예측({sel['A']['chosen']})")
        ax.set_xlim(pd.Timestamp(s), pd.Timestamp(e))
        ax.set_ylabel("15분 전력")
        ax.set_title(f"시험 구간 예측 예시: {label.replace('_', ' ')}")
        ax.legend(ncol=3, loc="upper left", fontsize=8)
        _save(fig, f"04_test_timeseries_{label}.png")


def fig_peak_conditions():
    dd = pd.read_csv(C.OUTPUT_DIR / "analysis" / "peak_days.csv", parse_dates=["date"])
    share = dd.groupby("month")["type"].value_counts(normalize=True).unstack().fillna(0)
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    cols = [c for c in ["startup", "plateau", "other"] if c in share.columns]
    bottom = np.zeros(len(share))
    names = {"startup": "기동형(07:30~08:59 최대)", "plateau": "고원형(09~16시 최대)", "other": "기타"}
    for i, c in enumerate(cols):
        ax.bar(share.index.astype(str), share[c].to_numpy(), bottom=bottom, color=SERIES[i], label=names[c],
               edgecolor=SURFACE, linewidth=2)
        bottom += share[c].to_numpy()
    ax.set_ylabel("가동일 비율")
    ax.set_xlabel("월")
    ax.set_title("일 최대 발생 유형: 겨울·봄 기동형 → 여름 고원형(냉방)")
    ax.legend(fontsize=8, loc="upper right")
    _save(fig, "05_peak_type_by_month.png")
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for i, (lab, sub) in enumerate({"1~5월": dd[dd.month <= 5], "7월(시험 전)": dd[(dd.month == 7)],
                                    "8~9월(시험)": dd[dd.month >= 8]}.items()):
        ax.scatter(sub["tmax"], sub["plateau"], s=18, color=SERIES[i], label=lab, edgecolor=SURFACE, linewidth=0.6)
    ax.set_xlabel("일 최고기온(°C)")
    ax.set_ylabel("주간 고원 평균 전력")
    ax.set_title("가동일 주간 부하와 기온: 여름에는 기온이 오를수록 높아진다")
    ax.legend(fontsize=8)
    _save(fig, "06_plateau_vs_tmax.png")


def fig_alarm_calibration():
    p = C.OUTPUT_DIR / "field" / "alarm_grades.csv"
    if not p.exists():
        return
    g = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    for i, per in enumerate(["cv", "test"]):
        sub = g[g.period == per]
        mid = (sub.p_lo + sub.p_hi.clip(upper=1.0)) / 2
        ax.plot(mid, sub.observed_rate, marker="o", markersize=5, color=SERIES[i],
                label={"cv": "교차검증", "test": "시험"}[per])
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
    p = C.OUTPUT_DIR / "field" / "demand_controller.csv"
    if not p.exists():
        return
    d = pd.read_csv(p)
    d = d[(d.period == "test") & (d.shed == 0.10) & (d.tau_selection != "candidate")]
    pols = ["model_prob", "reactive_now>=T-5", "clock_0800_fullday", "oracle_perfect"]
    names = {"model_prob": "모델 확률 경보", "reactive_now>=T-5": "현재값 반응", "clock_0800_fullday": "08시 고정 차단",
             "oracle_perfect": "완전 예지(상한)"}
    modes = {"none": "되돌림 없음(공조 완화 등)", "valley": "저부하 시간에 만회", "immediate": "직후 1시간에 만회"}
    targets = sorted(d.target.unique())
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    w = 0.2
    for ax, (mode, title) in zip(axes, modes.items()):
        sub_m = d[d.payback == mode]
        for i, pol in enumerate(pols):
            sub = sub_m[sub_m.policy == pol].set_index("target").reindex(targets)
            ax.bar(np.arange(len(targets)) + (i - 1.5) * w, sub["over_reduction_share"].to_numpy() * 100, width=w,
                   color=SERIES[i], label=names[pol], edgecolor=SURFACE, linewidth=1.2)
        ax.axhline(0, color=INK2, linewidth=0.8)
        ax.set_xticks(range(len(targets)), [f"{int(t)}" for t in targets])
        ax.set_xlabel("목표전력")
        ax.set_title(title, fontsize=10)
    axes[0].set_ylabel("목표 초과 15분 구간 감소율(%)")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle("수요제어 시뮬레이션(시험 8/1~9/14, 제어 가능 부하 10%·30분 차단 가정)", fontsize=11, fontweight="bold", y=1.04)
    _save(fig, "08_demand_controller.png")


def fig_info_value():
    p = C.OUTPUT_DIR / "analysis" / "plan_information_value.csv"
    if not p.exists():
        return
    d = pd.read_csv(p)
    for task in ("B", "A4"):
        sub = d[(d.task == task) & (d.model == "M1_lgbm")]
        if sub.empty:
            continue
        fig, ax = plt.subplots(figsize=(7, 3.0))
        yy = np.arange(len(sub))
        ax.barh(yy - 0.18, sub.cv_RMSE, height=0.34, color=SERIES[0], label="교차검증")
        ax.barh(yy + 0.18, sub.test_RMSE, height=0.34, color=SERIES[1], label="시험")
        ax.set_yticks(yy, sub.level)
        ax.invert_yaxis()
        ax.set_xlabel("RMSE")
        ax.set_title(("익일" if task == "B" else "60분 뒤") + " 예측의 계획 정보가치(LightGBM)")
        ax.legend(fontsize=8)
        _save(fig, f"09_plan_information_value_{task}.png")


def fig_interval_coverage():
    p = C.OUTPUT_DIR / "peak" / "interval_coverage.csv"
    if not p.exists():
        return
    d = pd.read_csv(p)
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
    p = C.OUTPUT_DIR / "analysis" / "learning_curve.csv"
    if not p.exists():
        return
    d = pd.read_csv(p)
    order = ["30", "60", "90", "all"]
    d["w"] = d["train_window_days"].astype(str)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    for ax, task, title in ((axes[0], "A4", "60분 뒤"), (axes[1], "B", "익일")):
        sub = d[d.task == task]
        for i, m in enumerate(sorted(sub.model.unique())):
            t = sub[sub.model == m].set_index("w").reindex(order)
            ax.plot(range(len(order)), t["test_RMSE"].to_numpy(), marker="o", markersize=5, color=SERIES[i], label=m)
        ax.set_xticks(range(len(order)), ["최근 30일", "최근 60일", "최근 90일", "전체(1~7월)"])
        ax.set_ylabel("시험 RMSE")
        ax.set_title(f"{title}: 학습 창 길이별 성능(설명용)", fontsize=10)
        ax.legend(fontsize=7)
    _save(fig, "11_learning_curve.png")


def run(iv: pd.DataFrame) -> None:
    _style()
    for fn in (fig_copy_forensics, fig_profiles):
        fn(iv)
    for fn in (fig_model_comparison, fig_peak_conditions, fig_alarm_calibration, fig_demand_controller, fig_info_value,
               fig_interval_coverage, fig_learning_curve):
        try:
            fn()
        except FileNotFoundError:
            pass
    fig_test_timeseries(iv)
