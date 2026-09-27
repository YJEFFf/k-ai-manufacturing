"""분석용 그림(보고서용 아님). 집계 CSV만 읽는다."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

HERE = Path(__file__).resolve().parent
V2, V1, REF = "#2a78d6", "#eb6834", "#8a8a85"   # dataviz 기본 범주 1·2번(검증기 통과), 기준선은 회색
INK, MUTED, GRID = "#1f1f1e", "#5f5e58", "#e6e5df"
# 한글 글꼴: macOS·Windows·Linux 순서. 설치된 것만 넣어 없는 글꼴 경고를 내지 않는다(macOS는 첫 글꼴 그대로라 그림이 바뀌지 않는다).
KOREAN_FONTS = ("AppleGothic", "Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic", "Nanum Gothic", "Noto Sans CJK KR")
_installed = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams.update({"font.family": [f for f in KOREAN_FONTS if f in _installed] + ["DejaVu Sans"], "axes.unicode_minus": False, "font.size": 9,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False})
NAMES = {"vib_noise": "진동 잡음 s(×정상 σ)", "cur_noise": "전류 잡음 s(×정상 σ)", "cur_offset": "전류 오프셋 d(×진폭)", "cur_gain": "전류 배율 k"}


def fig_e1():
    s = pd.read_csv(HERE / "e1_summary.csv")
    s = s[s.alpha.eq(.01) & s["shape"].eq("step") & s.t0.eq(10)]
    # 신호 탐지는 두 분할 중 나쁜 쪽(탐지율 최소, 지연 최대). 지연은 탐지된 기록만의 중앙값이라 탐지율과 함께 읽는다.
    agg = s.groupby(["family", "level", "model"]).agg(rate=("detect_rate_2s", "min"), any_rate=("detect_rate_any", "min"),
                                                     delay=("delay_median_s", "max")).reset_index()
    none = s[s.family.eq("none") & s.model.eq("guard_v2")].set_index("split")
    records = none.records.astype(int).to_dict()
    fig, axes = plt.subplots(2, 4, figsize=(12, 5.8), sharey="row")
    for j, fam in enumerate(NAMES):
        g = agg[agg.family.eq(fam)].sort_values("level")
        x = range(len(g.level.unique()))
        labels = [f"{v:g}" for v in sorted(g.level.unique())]
        for model, color, ls, mk, lab in (("guard_v2", V2, "-", "o", "v2"), ("baseline_v1", V1, "--", "s", "v1")):
            gm = g[g.model.eq(model)].reset_index(drop=True)
            axes[0, j].plot(x, gm.rate, ls, color=color, marker=mk, ms=6, lw=2, label=lab)
            axes[1, j].plot(x, gm.delay, ls, color=color, lw=2)
            few = gm.any_rate < .5   # 탐지된 기록이 절반 미만이면 지연은 소수 기록의 값: 빈 표시
            axes[1, j].plot([i for i in x if not few[i]], gm.delay[~few], mk, color=color, ms=6, label=lab)
            axes[1, j].plot([i for i in x if few[i]], gm.delay[few], mk, color=color, ms=6, mfc="white", mew=1.5)
        # 무주입 경보율은 오경보 관점이라 두 분할 중 높은 쪽을 기준선으로 그린다
        axes[0, j].axhline(none.detect_rate_2s.max(), color=REF, lw=1, ls=":")
        axes[0, j].axhline(.9, color=GRID, lw=1)
        for i in (0, 1):
            axes[i, j].set_xticks(list(x), labels)
            axes[i, j].grid(axis="y", color=GRID, lw=.6)
        axes[0, j].set_title(NAMES[fam], color=INK)
        axes[1, j].set_xlabel("세기")
    axes[0, 0].set_ylabel("2초 안 탐지율(두 분할 중 낮은 쪽)")
    axes[1, 0].set_ylabel("첫 경보 지연 중앙값(초)\n탐지된 기록만, 두 분할 중 늦은 쪽")
    rate = none.detect_rate_2s
    handles, names = axes[0, 0].get_legend_handles_labels()
    handles += [plt.Line2D([], [], color=REF, lw=1, ls=":"),
                plt.Line2D([], [], color=MUTED, marker="o", ls="", ms=6, mfc="white", mew=1.5)]
    names += [f"주입 없음 2초 창 경보율(A {rate['A']:.1%}·B {rate['B']:.1%}, 높은 쪽 표시)", "빈 표시: 탐지된 기록 50% 미만이라 지연이 소수 기록의 값"]
    fig.legend(handles, names, loc="lower center", ncol=4, frameon=False, fontsize=8)   # 그래프 밖: 선과 겹치지 않는다
    fig.suptitle(f"E1 고장 주입: 시작 1초 뒤 계단형 주입, α=1%, 동결 모델 · 기록 A {records['A']}개·B {records['B']}개, 잡음 족은 반복 5회(독립 시험 아님)",
                 color=INK, x=.01, ha="left")
    fig.tight_layout(rect=(0, .05, 1, 1))
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
    fig.suptitle("E3 재보정: 학습+보정 정상 자료량별 성능 · 정상 평가 480~599는 보정보다 조용한 시간대 · 사전 안정 규칙 충족 0/36", color=INK, x=.01, ha="left")
    fig.tight_layout()
    fig.savefig(HERE / "fig_e3_recalibration.png", dpi=150)


if __name__ == "__main__":
    fig_e1()
    fig_e3()
