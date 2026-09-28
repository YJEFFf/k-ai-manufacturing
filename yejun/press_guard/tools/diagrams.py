"""운영 흐름도·구성도(OPERATIONS.md의 그림)를 그린다. 수치가 없는 설명 그림이라 verify 동결 대상이 아니다.

    python yejun/press_guard/tools/diagrams.py      # → press_guard/docs/fig_operation_flow.png, fig_architecture.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
DOCS = HERE / "docs"
plt.rcParams.update({"font.family": runtime.korean_fonts(),
                     "axes.unicode_minus": False, "font.size": 9, "svg.hashsalt": "press-guard", "path.simplify": False})
INK, MUTED, GREEN, AMBER, RED, BLUE = "#192a31", "#72838b", "#176d55", "#b07510", "#b3412e", "#2f4a66"


def box(ax, x, y, w, h, title, body="", color=GREEN, fill="#f4f8f6"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02", linewidth=1.3, edgecolor=color, facecolor=fill))
    ax.text(x + w / 2, y + h - 0.035, title, ha="center", va="top", fontsize=9.5, fontweight="bold", color=INK)
    if body:
        ax.text(x + w / 2, y + h - 0.085, body, ha="center", va="top", fontsize=7.6, color=MUTED, linespacing=1.45)


def arrow(ax, a, b, color=INK, style="-|>", ls="-", text="", text_xy=None):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=11, linewidth=1.2, color=color, linestyle=ls, shrinkA=2, shrinkB=2))
    if text:
        tx, ty = text_xy or ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        ax.text(tx, ty, text, ha="center", va="center", fontsize=7.4, color=color, backgroundcolor="white")


def operation_flow(path):
    fig, ax = plt.subplots(figsize=(11.5, 7.2))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    w, h = .2, .14
    top = [(.02, "0 정상 수집", "같은 설비·운전 조건 정상 CSV\n보정 ≥99단위+수락 60단위\n시각 간격 0.1초 ± 20 ms"),
           (.27, "1 재보정·수락 검사", "recalibrate.py\n정상 알림 Beta-Binomial 한도\n주입 3종 2초 탐지 ≥90%"),
           (.52, "2 운영 설정", "재보정 모델·α 1%·사전 비율 π\n1단계=기록, 2단계=출동"),
           (.77, "3 실시간 감시", "StreamDetector(10 Hz)\n사건 대기열(공백 60초 이하 묶음)")]
    for x, t, b in top:
        box(ax, x, .78, w, h, t, b)
    for (x1, *_), (x2, *_) in zip(top, top[1:]):
        arrow(ax, (x1 + w, .85), (x2, .85))
    box(ax, .60, .52, .17, .15, "1단계 주의", "사건 시작 · 화면 확인·기록\n다음 샘플 검사 앞당김", color=AMBER, fill="#fdf6e7")
    box(ax, .80, .52, .18, .15, "2단계 점검 요청", "사건 안 경보 2행 · 한 번만\n현장 점검(목표: 10분 안 시작*)", color=RED, fill="#fbeeea")
    arrow(ax, (.87, .78), (.69, .67), text="첫 경보", text_xy=(.76, .735))
    arrow(ax, (.87, .78), (.89, .67), text="격상", text_xy=(.915, .735))
    arrow(ax, (.77, .595), (.80, .595), color=RED, text="", ls="--")
    box(ax, .55, .27, .2, .17, "4 판단표 점검", "근거 → 확인 대상 → 점검 항목\n고장 모드 후보 FM1~FM6\n(decision_table_v2.csv)", color=BLUE, fill="#f1f5fa")
    box(ax, .78, .27, .2, .17, "5 품질 조치", "의심 생산 시간창 가공품 보류\n전단면·버·치수·평탄도 전수 확인\n(quality_windows_v2.csv)", color=BLUE, fill="#f1f5fa")
    arrow(ax, (.89, .52), (.89, .44)); arrow(ax, (.83, .52), (.65, .44))
    arrow(ax, (.78, .355), (.75, .355))
    box(ax, .30, .27, .2, .17, "6 결과 기록", "콘솔 양식: 확인 시각·담당\n결과(정상 확인/이상 확인/보류)\n조치·상태 → CSV 내보내기", color=GREEN)
    arrow(ax, (.55, .355), (.50, .355))
    box(ax, .05, .27, .2, .17, "7 정상 복귀 확인", "다음 정상 기록에서 알림이\n멎는지 확인. 멎지 않으면\n2단계 유지", color=GREEN)
    arrow(ax, (.30, .355), (.25, .355))
    box(ax, .05, .03, .27, .16, "8 교대·주간 감시", "monitor.py: 창별 알림 단위 수 vs Beta-Binomial\n변경 기록·수준 이동 있음 → 재보정 검토\n없음 → 설비 점검 요청(열화 의심)", color=MUTED, fill="#f5f7f8")
    box(ax, .40, .03, .27, .16, "9 재보정·교체", "미확인 사건의 의심 시간창은 뺌(--outcomes)\n점검 요청 창은 '정상 확인' 뒤에만 사용\n수락 통과 모델로 교체 → 1로 돌아감", color=MUTED, fill="#f5f7f8")
    arrow(ax, (.15, .27), (.15, .19)); arrow(ax, (.32, .11), (.40, .11), text="검토", text_xy=(.36, .135))
    box(ax, .72, .03, .26, .16, "예외: 수집 오류", "결측·비유한 값·시각 오류 행은 판정 보류\n'수집 상태 확인'(FM6): 케이블·커넥터\n수집 PC 시각 동기화", color=RED, fill="#fbeeea")
    ax.text(.02, .985, "Press Guard 운영 흐름 — 제안(가정 표시 *: 현장 합의로 정할 값)", fontsize=11, fontweight="bold", color=INK, va="top")
    ax.text(.98, .985, "설비 제어·자동 정지 명령 없음 · 권고만", fontsize=8, color=MUTED, va="top", ha="right")
    fig.savefig(path, dpi=150, bbox_inches="tight", metadata={"Software": None}); plt.close(fig)


def architecture(path):
    fig, ax = plt.subplots(figsize=(11.5, 4.4))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    items = [(.025, "센서", "AI0·AI1 진동(상·하부)\nAI2 전류\n10 Hz 순시값"),
             (.225, "수집 PC", "CSV 파일 또는 스트림\nTimeStamp + 3개 값\n시각 동기화"),
             (.425, "Press Guard", "StreamDetector\n(직전 7행만 보관)\n점수·p값·경보·2단계\n이상 확률(사전 비율 π)"),
             (.625, "알림 채널", "점검 콘솔 대기열\n경광등·메신저\nCMMS 작업요청\n(on_alert 콜백)"),
             (.825, "기록·감시", "결과 CSV\n(확인 시각·담당·결과)\nmonitor.py 교대 감시\n재보정 자료 선별")]
    w = .15
    for x, t, b in items:
        box(ax, x, .5, w, .38, t, b, color=GREEN if t == "Press Guard" else BLUE, fill="#eef6f1" if t == "Press Guard" else "#f4f7fb")
    for (x1, *_), (x2, *_) in zip(items, items[1:]):
        arrow(ax, (x1 + w, .69), (x2, .69))
    ax.plot([.9, .9, .5], [.5, .40, .40], color=MUTED, linestyle="--", linewidth=1.2)
    arrow(ax, (.5, .40), (.5, .5), color=MUTED, ls="--")
    ax.text(.695, .345, "재보정(recalibrate.py): '정상 확인' 구간으로 다시 맞추고 수락 검사 통과 모델만 교체", fontsize=7.6, color=MUTED, ha="center")
    ax.text(.5, .2, "수집 오류(결측·비유한 값·시각 오류·역순) → 판정 보류, '수집 상태 확인' 알림", fontsize=8, color=RED, ha="center")
    ax.text(.5, .1, "모의 운용: simulate.py가 CSV를 10 Hz로 흘려 같은 알림을 재현(일괄 분석과 같은 행, test_simulate.py)", fontsize=8, color=MUTED, ha="center")
    ax.text(.01, .98, "Press Guard 연계 구성 — 제안", fontsize=11, fontweight="bold", color=INK, va="top")
    fig.savefig(path, dpi=150, bbox_inches="tight", metadata={"Software": None}); plt.close(fig)


def main():
    DOCS.mkdir(exist_ok=True)
    operation_flow(DOCS / "fig_operation_flow.png")
    architecture(DOCS / "fig_architecture.png")
    print("docs/fig_operation_flow.png, docs/fig_architecture.png")


if __name__ == "__main__":
    main()
