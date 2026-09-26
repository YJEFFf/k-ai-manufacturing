"""분석용 그림(보고서용 아님). 집계 CSV만 읽는다."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
V2, V1, REF = "#2a78d6", "#eb6834", "#8a8a85"   # dataviz 기본 범주 1·2번(검증기 통과), 기준선은 회색
INK, MUTED, GRID = "#1f1f1e", "#5f5e58", "#e6e5df"
plt.rcParams.update({"font.family": ["AppleGothic", "DejaVu Sans"], "axes.unicode_minus": False, "font.size": 9,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False})
NAMES = {"vib_noise": "진동 잡음 s(×정상 σ)", "cur_noise": "전류 잡음 s(×정상 σ)", "cur_offset": "전류 오프셋 d(×진폭)", "cur_gain": "전류 배율 k"}


def fig_e1():
    s = pd.read_csv(HERE / "e1_summary.csv")
    s = s[s.alpha.eq(.01) & s["shape"].eq("step") & s.t0.eq(10)]
    # 두 분할 중 나쁜 쪽(탐지율 최소, 지연 최대)
    agg = s.groupby(["family", "level", "model"]).agg(rate=("detect_rate_2s", "min"), delay=("delay_median_s", "max")).reset_index()
    none = agg[agg.family.eq("none")].set_index("model").rate
    fig, axes = plt.subplots(2, 4, figsize=(12, 5.4), sharey="row")
    for j, fam in enumerate(NAMES):
        g = agg[agg.family.eq(fam)].sort_values("level")
        x = range(len(g.level.unique()))
        labels = [f"{v:g}" for v in sorted(g.level.unique())]
        for model, color, ls, mk, lab in (("guard_v2", V2, "-", "o", "v2"), ("baseline_v1", V1, "--", "s", "v1")):
            gm = g[g.model.eq(model)]
            axes[0, j].plot(x, gm.rate, ls, color=color, marker=mk, ms=6, lw=2, label=lab)
            axes[1, j].plot(x, gm.delay, ls, color=color, marker=mk, ms=6, lw=2, label=lab)
        axes[0, j].axhline(none["guard_v2"], color=REF, lw=1, ls=":")
        axes[0, j].axhline(.9, color=GRID, lw=1)
        for i in (0, 1):
            axes[i, j].set_xticks(list(x), labels)
            axes[i, j].grid(axis="y", color=GRID, lw=.6)
        axes[0, j].set_title(NAMES[fam], color=INK)
        axes[1, j].set_xlabel("세기")
    axes[0, 0].set_ylabel("2초 안 탐지율(두 분할 중 낮은 쪽)")
    axes[1, 0].set_ylabel("첫 경보 지연 중앙값(초, 높은 쪽)")
    axes[0, 0].legend(frameon=False, loc="lower right")
    axes[0, 0].text(0, none["guard_v2"] + .02, "주입 없음(v2)", color=MUTED, fontsize=8)
    fig.suptitle("E1 고장 주입: 시작 1초 뒤 계단형 주입, α=1%, 동결 모델", color=INK, x=.01, ha="left")
    fig.tight_layout()
    fig.savefig(HERE / "fig_e1_detection.png", dpi=150)


def fig_e3():
    s = pd.read_csv(HERE / "e3_stability.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for alpha, color, mk, lab in ((.01, V2, "o", "α=1% (보정 99·120·180)"), (.05, V1, "s", "α=5% (보정 19·40·60)")):
        g = s[s.alpha.eq(alpha)].sort_values("normal_minutes")
        axes[0].vlines(g.normal_minutes, g.missed_rows_median, g.missed_rows_max, color=color, lw=1, alpha=.6)
        axes[0].plot(g.normal_minutes, g.missed_rows_median, mk, color=color, ms=6, label=lab)
        axes[1].plot(g.normal_minutes, g.normal_notified_max, mk, color=color, ms=6, label=lab)
    axes[0].axhline(44, color=REF, ls=":", lw=1); axes[0].text(1, 45, "동결 A 44행", color=MUTED, fontsize=8)
    axes[0].set_ylabel("이상 미탐 행 /600 (점=시작 중앙값, 선=최악)")
    axes[1].set_ylabel("정상 알림 구간 /120 (시작 중 최대)")
    for ax in axes:
        ax.set_xlabel("재보정에 쓴 정상 자료(분, 0.1초×행)")
        ax.grid(color=GRID, lw=.6)
    axes[0].legend(frameon=False)
    fig.suptitle("E3 재보정: 학습+보정 정상 자료량별 성능, 정상 평가 480~599", color=INK, x=.01, ha="left")
    fig.tight_layout()
    fig.savefig(HERE / "fig_e3_recalibration.png", dpi=150)


if __name__ == "__main__":
    fig_e1()
    fig_e3()
