"""보고서 그림 13개를 만든다(그림 12는 콘솔 캡처를 잘라 씀). 숫자는 모두 분석 산출물에서 읽는다(facts.csv와 같은 원천).

입력: code/press/{tvt,cases,domain}/outputs, code/press/tvt/cache/rows_B.pkl, data/3_소성가공_예지보전/*.csv, report/console_source/console_workspace_v2.png
출력: report/figures/fig*.png (200 dpi). 보고서 번호 → 파일: 1 fig1_structure, 2 fig8_observability, 3 fig0_leak, 4 fig2_collection,
      5 fig9_regime_timeline, 6 fig3_flow, 7 fig10_load_vibration, 8 fig11_model_structure, 9 fig5_models, 10 fig4_miss_position,
      11 fig6_rules, 12 fig7_console, 13 fig12_alarm_card
실행: python report/make_figures.py
      그림 13(fig_alarm_card)이 읽는 rows_B.pkl은 pandas 3에서 저장돼 pandas 2로는 못 읽는다(예: ~/.venvs/hbmg 의 python으로 실행)
색: dataviz 기본 팔레트 슬롯 1·2(파랑 #2a78d6 = 분할 A, 주황 #eb6834 = 분할 B), 검증 통과(validate_palette.js, light)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TVT = ROOT / "code/press/tvt/outputs"
DOM = ROOT / "code/press/domain/outputs"
DATA = ROOT / "data/3_소성가공_예지보전"
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
A, B, GREY, INK, INK2 = "#2a78d6", "#eb6834", "#b8b6b0", "#0b0b0b", "#52514e"
HATCH = {"A": {}, "B": {"hatch": "//", "edgecolor": "white"}}   # 흑백 인쇄에서 분할 B 막대를 빗금으로 구별
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 10,
                     "axes.edgecolor": GREY, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False})


def save(fig, name):
    """흰 배경 200 dpi로 저장하고 닫는다."""
    fig.savefig(FIG / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def box(ax, xy, w, h, text, fc="#f3f2ef", ec=GREY, size=9.5, weight="normal"):
    """둥근 상자와 가운데 글자(계통도·흐름도용)."""
    ax.add_patch(FancyBboxPatch(xy, w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=fc, ec=ec, lw=1))
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center", fontsize=size, color=INK, weight=weight)


def arrow(ax, p, q):
    """p → q 화살표."""
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=12, color=INK2, lw=1))


def fig_structure():
    """[그림 1] 설비 계통도: 모터-기어펌프 유닛(센서 3개) → 압력원(어큐뮬레이터·비례밸브) → 실린더 3계통(파인블랭킹 3중 동작)."""
    fig, ax = plt.subplots(figsize=(7.6, 4.1))
    ax.set_xlim(0, 10.5); ax.set_ylim(-0.25, 5.0); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.25, 0.75), 2.6, 3.65, boxstyle="round,pad=0.02,rounding_size=0.08", fc="none", ec=GREY, lw=1, ls="--"))
    ax.text(1.55, 4.55, "모터-펌프 유닛", ha="center", fontsize=8.5, color=INK2)
    box(ax, (0.55, 2.75), 2.0, 1.25, "전기 모터")
    box(ax, (0.55, 1.0), 2.0, 1.3, "기어형 유압펌프\n(외접 기어, 추정)", size=8.8)
    arrow(ax, (1.55, 2.75), (1.55, 2.3))
    box(ax, (4.45, 2.6), 2.6, 1.2, "압력원\n어큐뮬레이터 충전", size=8.8)
    box(ax, (4.45, 0.85), 2.6, 1.2, "압력 제어(비례)밸브\n설정압 도달 시 탱크 언로딩", size=8.0)
    arrow(ax, (2.55, 1.65), (4.45, 3.0)); arrow(ax, (5.75, 2.6), (5.75, 2.05))
    cyl = [("블랭킹 실린더(주 램)", 3.55), ("V링 실린더(판재 고정)", 2.45), ("역압 실린더(아래에서 받침)", 1.35)]
    for label, y in cyl:
        box(ax, (7.65, y - 0.42), 2.7, 0.84, label, size=8.2)
        arrow(ax, (7.05, 3.2), (7.65, y))
    ax.text(9.0, 4.55, "파인블랭킹 프레스(약 1000톤) 3중 동작", ha="center", fontsize=8.5, color=INK2)
    # 진동센서 위치 근거는 "모터-펌프 유닛 상부·하부"까지라 점선 유닛 테두리의 위·아래 모서리에 둔다
    for ey, ly, s in ((4.4, 4.72, "AI0 상부 진동"), (0.75, 0.43, "AI1 하부 진동")):
        ax.plot([2.45, 2.45, 2.95], [ey, ly, ly], color=A, lw=1.5); ax.plot(2.45, ey, "o", color=A, ms=5)
        ax.text(3.0, ly, s, va="center", fontsize=8.3, color=INK)
    ax.plot([0.12, 0.12, 0.55], [4.85, 3.4, 3.4], color=B, lw=1.5); ax.plot(0.55, 3.4, "o", color=B, ms=5)
    ax.text(0.2, 4.88, "AI2 모터 전력선 전류", fontsize=8.3, color=INK, va="bottom")
    ax.text(5.2, -0.15, "(일반 구조, 추정) 펌프 모터 부하는 행정(고속 접근→감속·감지→저속 블랭킹→고속 복귀)과 어큐뮬레이터 충전·언로딩에 따라 오르내린다",
            fontsize=7.6, color=INK2, ha="center")
    save(fig, "fig1_structure.png")


def fig_collection():
    """[그림 4] 수집 구조: 측정된 기록(막대)과 수집 공백(빈칸). 정상 앞 3분과 이상 전체."""
    span = 180
    n = pd.read_csv(DATA / "press_data_normal.csv"); a = pd.read_csv(DATA / "outlier_data.csv")
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 2.6), gridspec_kw={"hspace": 0.9})
    for ax, d, title, color in ((axes[0], n, "정상 파일 앞 3분 (2022-07-12 화 00:00~)", A),
                                (axes[1], a, "이상 파일 전체 2분 46초 (2022-07-17 일 10:51~)", B)):
        t = pd.to_datetime(d.TimeStamp); s = (t - t.iloc[0]).dt.total_seconds()
        rec = (s.diff().sub(0.1).abs() > 0.02).cumsum()   # 행 간격이 0.1초에서 벗어나면 새 기록
        keep = s <= span
        for _, g in s[keep].groupby(rec[keep]):
            ax.add_patch(plt.Rectangle((g.iloc[0], 0), max(g.iloc[-1] - g.iloc[0], 0.1), 1, color=color, lw=0))
        ax.set_xlim(0, span); ax.set_ylim(0, 1); ax.set_yticks([])
        ax.set_title(title, fontsize=9.5, loc="left", color=INK)
        ax.set_xlabel("경과 시간(초)  · 막대 = 측정된 기록(최대 50행·5초), 빈칸 = 수집 공백", fontsize=8.5)
    save(fig, "fig2_collection.png")


def fig_flow():
    """[그림 6] 분석 흐름 8단계(실제 진행 순서, 4개씩 두 줄). '사후' 상자는 test 채점 뒤에 한 분석이다."""
    steps = ["데이터·구조\n확인", "데이터 결함\n진단", "모델 v1~v3·\n규칙 R1·R2\n(전체 데이터 봄)", "잠금(v2+R1)·\ntest 채점",
             "test 확인 뒤\n2단계 승격 R2\n(v2+R1+R2)", "의심과 검증\n(2.6절)", "사후: 설비 물리·\n표준 기법·운전 상태", "사후:\n보완 LSTM 대조"]
    dx, w, h, ys = 2.15, 1.75, 0.95, (1.45, 0.1)     # 칸 간격, 상자 폭·높이, 두 줄의 상자 아래 y
    fig, ax = plt.subplots(figsize=(8.4, 2.4))
    ax.set_xlim(0, 4 * dx); ax.set_ylim(0, 2.5); ax.axis("off")
    for i, s in enumerate(steps):
        x, y = (i % 4) * dx + 0.1, ys[i // 4]
        box(ax, (x, y), w, h, s, size=8.4)
        if i % 4:
            arrow(ax, (x - dx + w, y + h / 2), (x, y + h / 2))
    # 첫 줄 끝 → 둘째 줄 처음(꺾은 연결선)
    x4, x5, ym = 3 * dx + 0.1 + w / 2, 0.1 + w / 2, (ys[0] + ys[1] + h) / 2
    ax.plot([x4, x4, x5], [ys[0], ym, ym], color=INK2, lw=1)
    arrow(ax, (x5, ym), (x5, ys[1] + h))
    save(fig, "fig3_flow.png")


def fig_miss_position():
    """[그림 10] v2 test 미탐 행의 기록 안 위치."""
    e = json.loads((TVT / "tvt_hypotheses.json").read_text(encoding="utf-8"))["v2_test_errors"]
    pos = sorted({int(k) for s in "AB" for k in e[s]["missed_by_position"]})
    x = np.arange(len(pos)); w = 0.38
    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    for off, s, c in ((-w / 2, "A", A), (w / 2, "B", B)):
        v = [e[s]["missed_by_position"].get(str(p), 0) for p in pos]
        ax.bar(x + off, v, w - 0.04, color=c, label=f"분할 {s} (미탐 {e[s]['missed_rows']}행)", **HATCH[s])
        for xi, vi in zip(x + off, v):
            if vi:
                ax.text(xi, vi + 0.15, str(vi), ha="center", fontsize=8, color=INK2)
    ax.set_xticks(x, [str(p) for p in pos]); ax.set_xlabel("기록 안 위치(행, 0 = 기록 첫 행; 미탐 없는 위치 생략)"); ax.set_ylabel("v2 미탐 행 수")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_title("v2의 test 미탐은 기록 시작 직후에 몰린다", fontsize=10, loc="left", color=INK)
    save(fig, "fig4_miss_position.png")


# 모델 비교 그림의 막대 순서와 표시 이름(내부 이름 H1·H2 = 보고서의 R1·R2)
NAMES = {"iforest": "IsolationForest", "lstm20": "LSTM-AE(가이드북, 20행)", "maxz3": "max|z|", "knn5": "5NN", "mlp_ae5": "MLP-AE(5행)",
         "v1": "v1", "v2": "기반 모델 v2", "v2+C1d1": "v2+v3 조건부", "v2+H1": "v2+R1(제출 1단계)", "v2+H1+H2": "v2+R1+R2(제출 2단계)"}


def fig_models():
    """[그림 9] 같은 분할·같은 보정에서 모델별 test F1(α 1%, 실시간)."""
    t = pd.read_csv(TVT / "tvt_test.csv")
    t = t[(t.alpha == 0.01) & (t["mode"] == "realtime") & t.model.isin(NAMES)]
    p = t.pivot_table(index="model", columns="split", values="f1").loc[list(NAMES)]
    # 사후 보완 LSTM(예준 실험의 잠금 설정, 새 seed 3·4·5 앙상블)을 가이드북 LSTM 바로 아래에 회색으로 덧붙인다
    lx = pd.read_csv(HERE / "research" / "yejun_lstm_improvement_62482a5" / "03_test.csv")
    lx = lx[(lx.variant == "lx:W10-var-128x64-e1000p100:ct-mean:e345") & (lx.rule == "none") & (lx.alpha == 0.01)
            & (lx.regime == "test") & (lx["mode"] == "realtime")].set_index("split").f1
    rj = json.loads((TVT / "ridge_baseline.json").read_text(encoding="utf-8"))["ridge"]     # 사후 Ridge 예측 오차(tvt/14)
    rows = list(p.index)
    extra = pd.DataFrame([[lx["A"], lx["B"]], [rj["A"]["ridge"]["test_f1"], rj["B"]["ridge"]["test_f1"]]], index=["lstm_imp", "ridge"], columns=p.columns)
    p = pd.concat([p.loc[:"lstm20"], extra, p.loc[rows[rows.index("lstm20") + 1]:]])
    labels = {**NAMES, "lstm_imp": "보완 LSTM-AE(사후)", "ridge": "Ridge 예측 오차(사후)"}
    y = np.arange(len(p)); h = 0.38
    fig, ax = plt.subplots(figsize=(6.4, 4.3))
    post = np.array([m in ("lstm_imp", "ridge") for m in p.index])
    for off, s, c in ((h / 2, "A", A), (-h / 2, "B", B)):
        ax.barh(y + off, p[s], h - 0.05, color=[GREY if q else c for q in post], label=f"분할 {s}", **HATCH[s])
    for yi, (ma, mb) in zip(y, p[["A", "B"]].to_numpy()):
        ax.text(max(ma, mb) + 0.01, yi, f"{ma:.3f} / {mb:.3f}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, [labels[m] for m in p.index]); ax.set_xlim(0, 1.18); ax.set_xlabel("test 실시간 행 단위 F1 (α 1%)")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax.set_title("같은 분할·같은 보정에서의 모델 비교", fontsize=10, loc="left", color=INK)
    save(fig, "fig5_models.png")


def fig_rules():
    """[그림 11] 규칙 R1·R2를 더할 때 test 미탐·오경보 행 수."""
    t = pd.read_csv(TVT / "tvt_test.csv")
    t = t[(t.alpha == 0.01) & (t["mode"] == "realtime")]
    order = ["v2", "v2+H2", "v2+H1", "v2+H1+H2"]; labels = ["v2", "+R2", "+R1", "+R1+R2"]
    x = np.arange(len(order)); w = 0.38
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6))
    for ax, col, title in ((axes[0], "fn", "미탐 행"), (axes[1], "fp", "오경보 행")):
        for off, s, c in ((-w / 2, "A", A), (w / 2, "B", B)):
            v = [int(t[(t.model == m) & (t.split == s)][col].iloc[0]) for m in order]
            ax.bar(x + off, v, w - 0.04, color=c, label=f"분할 {s}", **HATCH[s])
            for xi, vi in zip(x + off, v):
                ax.text(xi, vi + 0.3, str(vi), ha="center", fontsize=8, color=INK2)
        top = max(int(t[t.model.isin(order)][col].max()), 1)
        ax.set_ylim(0, top * 1.3); ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.set_xticks(x, labels); ax.set_title(f"test {title}", fontsize=10, loc="left", color=INK, pad=10)
    axes[0].legend(frameon=False, fontsize=8.5)
    save(fig, "fig6_rules.png")


def fig_leak():
    """[그림 3] 형식 누수: 상부 진동값 소수 자릿수 분포(원본 / 정밀도 맞춘 뒤)."""
    leak = json.loads((ROOT / "code/press/cases/outputs/facts_extra.json").read_text(encoding="utf-8"))["format_leak"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.6), sharey=True)
    for ax, tag, title in ((axes[0], "raw", "원본 그대로"), (axes[1], "matched", "정밀도 맞춘 뒤")):
        d = leak[tag]
        nd, ad = d["normal_digits_share"], d["abnormal_digits_share"]   # 자릿수(문자열 키) → 행 비율
        # 두 파일 모두 0.5% 미만인 자릿수는 그리지 않는다
        keys = [k for k in sorted({int(k) for k in (*nd, *ad)}) if max(nd.get(str(k), 0), ad.get(str(k), 0)) >= 0.005]
        x = np.arange(len(keys)); w = 0.38
        ax.bar(x - w / 2, [nd.get(str(k), 0) for k in keys], w - 0.04, color=A, label="정상 파일")
        ax.bar(x + w / 2, [ad.get(str(k), 0) for k in keys], w - 0.04, color=B, hatch="//", edgecolor="white", label="이상 파일")
        ax.set_xticks(x, [str(k) for k in keys]); ax.set_xlabel("상부 진동값의 소수 자릿수")
        sub = (f"'상부 진동 소수 자릿수 > 6' 규칙\n행 F1 {d['f1']:.3f}" if tag == "raw"
               else f"같은 규칙 F1 {d['f1']:.3f}\n(분포가 같아짐)")
        ax.set_title(f"{title}: {sub}", fontsize=9.5, loc="left", color=INK)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    axes[0].set_ylabel("행 비율"); axes[0].legend(frameon=False, fontsize=8.5)
    save(fig, "fig0_leak.png")


def fig_console():
    """[그림 12] Press Guard 콘솔 화면 캡처(1600×1500)에서 사이드바·헤더·설정 줄을 빼고
    KPI 카드·점검 대기열·경보 근거(이상 확률 55.0% 줄, 전류 관측 차트까지)만 잘라 쓴다. 좌표는 원본 픽셀."""
    from PIL import Image
    img = Image.open(HERE / "console_source" / "console_workspace_v2.png")
    img.crop((110, 360, 1570, 1122)).save(FIG / "fig7_console.png")


def fig_observability():
    """[그림 2] 초당 10회 점 표본으로 무엇을 볼 수 있나: 주파수 축(로그) 위 현상 대역과 접힘(에일리어싱)."""
    ph = json.loads((DOM / "01_signal_physics.json").read_text(encoding="utf-8"))
    fa = ph["1_alias_sampling_interval"]["normal_records_ge30"]["f_alias"]["median"]
    rows = [  # (이름, 시작 Hz, 끝 Hz, 색, 근거)
        ("프레스 행정 주기", 0.3, 1.7, A, "추정"),
        ("모터 회전 1X·2X(4극 가정 약 29·59Hz)", 28, 60, GREY, "가정"),
        ("전원 60Hz와 홀수 고조파 180·300·420Hz", 60, 420, B, "전류 고조파와 부합(가설)"),
        ("기어 맞물림(잇수 9~12 × 회전, 약 260~350Hz)", 260, 350, GREY, "가정"),
        ("캐비테이션 고주파 광대역", 1000, 20000, GREY, "추정"),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    ax.axvspan(0.1, 5, color="#e8f0fb", lw=0)
    ax.text(0.12, len(rows) + 0.15, "초당 10회 점 표본이 직접 담는 대역(나이퀴스트 5Hz 이하)", fontsize=8, color=A, va="bottom")
    for i, (name, lo, hi, c, src) in enumerate(rows[::-1]):
        y = i + 0.5
        ax.plot([lo, hi], [y, y], color=c, lw=6, solid_capstyle="butt")
        ax.text(hi * 1.25 if hi < 5000 else lo / 1.3, y, f"{name} [{src}]", va="center", fontsize=7.8, color=INK,
                ha="left" if hi < 5000 else "right")
    # 전원 60Hz와 3고조파가 초당 10회 표본에서 접혀 보이는 주파수. 꼬리는 막대 아래, 머리 높이·곡률을 달리해 교차를 피한다
    for f_src, f_app, y_head, rad in ((60, fa, 2.1, -0.04), (180, 3 * fa, 1.85, -0.12)):
        ax.annotate("", xy=(f_app, y_head), xytext=(f_src, 2.3),
                    arrowprops=dict(arrowstyle="-|>", color=B, lw=0.9, ls="--", connectionstyle=f"arc3,rad={rad}"))
        ax.plot(f_app, y_head - 0.05, "v", color=B, ms=4)
    ax.text(fa * 0.9, 1.12, f"접힘(가설): 60Hz 계열→{fa:.2f}Hz, 180Hz→{3*fa:.2f}Hz", fontsize=7.6, color=B)
    ax.set_xscale("log"); ax.set_xlim(0.1, 30000); ax.set_ylim(0, len(rows) + 0.6); ax.set_yticks([])
    ax.set_xticks([0.1, 1, 5, 10, 100, 1000, 10000], ["0.1", "1", "5", "10", "100", "1k", "10k"])
    ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_xlabel("주파수(Hz, 로그 축)")
    ax.spines["left"].set_visible(False)
    save(fig, "fig8_observability.png")


def fig_regime_timeline():
    """[그림 5] 정상 77분의 운전 상태: 기록별 부하(전류 진폭)·하부 진동, 정숙 구간, 분할 경계, v2 오경보 기록."""
    r = pd.read_csv(DOM / "06_operating_regime_records.csv")
    t0 = pd.to_datetime(r.ts0.iloc[0])
    m = (pd.to_datetime(r.ts0) - t0).dt.total_seconds() / 60
    q = r.regime == "quiet"
    big = r.n >= 8     # 8행 미만 기록은 사인 진폭이 불안정해 점으로 찍지 않는다(06_operating_regime.py MIN_ROWS)
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 3.6), sharex=True, gridspec_kw={"hspace": 0.18})
    for ax, col, lab in ((axes[0], "cur_amp", "전류 사인 진폭(부하)"), (axes[1], "vib_lower_sd", "하부 진동 SD")):
        ax.axvspan(m[q].min(), m[q].max(), color="#efeeea", lw=0)
        ax.scatter(m[big], r.loc[big, col], s=5, color=A, lw=0)
        ax.set_ylabel(lab, fontsize=8.5)
    axes[0].set_ylim(bottom=0)
    fa = (r["fa1_B_v2"].fillna(0) > 0) & big
    axes[0].scatter(m[fa], r.loc[fa, "cur_amp"], s=40, facecolor="none", edgecolor=B, lw=1.3, label="분할 B v2 오경보 기록(α 1%, valid·test)")
    axes[0].legend(frameon=True, framealpha=0.92, edgecolor="none", fontsize=7.6, loc="lower left")
    # 분할 경계 = 각 분할에서 valid·test가 시작하는 첫 기록
    bounds = [(m[r[f"part_{s}"] == p].min(), f"{s} {a}|{p}", ls) for s, ls in (("B", ":"), ("A", "--")) for a, p in (("train", "valid"), ("valid", "test"))]
    for x, lab, ls in bounds:
        for ax in axes:
            ax.axvline(x, color=GREY, lw=0.8, ls=ls)
        axes[0].text(x + 0.3, 1.02 if lab.startswith("B") else 1.11, lab, transform=axes[0].get_xaxis_transform(), fontsize=6.4, color=INK2, ha="left", va="bottom")
    # 정숙 구간과 가이드북 구간 글자는 그 안을 지나는 경계선 오른쪽에서 시작한다
    xq = max(x for x, _, _ in bounds if m[q].min() < x < m[q].max()) + 0.4
    q_min = (pd.to_datetime(r.loc[q, "ts1"]).max() - pd.to_datetime(r.loc[q, "ts0"]).min()).total_seconds() / 60
    axes[0].text(xq, 75, f"정숙 구간 {q_min:.0f}분\n(연속 저부하)", ha="left", va="center", fontsize=6.8, color=INK2)
    gr = (r.row1 >= 16000) & (r.row0 <= 19000)     # 가이드북 16,000~19,000행에 걸친 기록
    g0 = m[gr].min(); g1 = (pd.to_datetime(r.loc[gr, "ts1"]).max() - t0).total_seconds() / 60
    axes[0].annotate("", xy=(g0, 35), xytext=(g1, 35), arrowprops=dict(arrowstyle="|-|", color=INK2, lw=0.8, mutation_scale=3))
    axes[0].text(xq, 17, "가이드북 16,000~19,000행", ha="left", va="center", fontsize=6.6, color=INK2)
    axes[1].set_xlabel("정상 파일 경과 시간(분, 2022-07-12 00:00~)")
    save(fig, "fig9_regime_timeline.png")


def fig_load_vibration():
    """[그림 7] 부하(전류 RMS)와 진동 SD의 정상 관계, 그리고 그 관계에서 벗어난 이상 기록(로그-로그)."""
    s = pd.read_csv(DOM / "01_signal_physics_records.csv")
    s = s[s.n >= 20]
    # split = 01_signal_physics.py가 분할 A 경계로 나눈 정상 기록의 train/valid/test, 이상은 "abnormal"
    nrm, ab, tr = s[s.set == "normal"], s[s.set == "abnormal"], s[s.split == "train"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    for ax, col, lab in ((axes[0], "sd_lower", "하부 진동 SD"), (axes[1], "sd_upper", "상부 진동 SD")):
        ax.scatter(nrm.cur_rms, nrm[col], s=6, color=A, alpha=0.6, lw=0, label=f"정상 기록(20행 이상, {len(nrm)}개)")
        ax.scatter(ab.cur_rms, ab[col], s=22, color=B, lw=0, label=f"이상 기록(20행 이상, {len(ab)}개)")
        b1, b0 = np.polyfit(np.log(tr.cur_rms), np.log(tr[col]), 1)
        xx = np.linspace(np.log(tr.cur_rms.min()), np.log(tr.cur_rms.max()), 50)
        ax.plot(np.exp(xx), np.exp(b0 + b1 * xx), color=INK2, lw=1, label=f"로그-로그 회귀(분할 A 학습 정상 기록 {len(tr)}개로 적합)")
        ax.text(0.98, 0.04, f"정상 기울기 {b1:.2f}", transform=ax.transAxes, ha="right", fontsize=7.6, color=INK2)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("전류 RMS(직류 제외), 부하 대리변수", fontsize=8.5)
        yt = [0.03, 0.05, 0.1, 0.2, 0.3] if col == "sd_lower" else [0.03, 0.1, 0.3, 1.0]
        ax.set_xticks([60, 80, 100, 150, 200], ["60", "80", "100", "150", "200"]); ax.set_yticks(yt, [f"{v:g}" for v in yt])
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_title(lab, fontsize=9.5, loc="left", color=INK)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=7.6, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.24))
    save(fig, "fig10_load_vibration.png")


def fig_model_structure():
    """[그림 8] 2단계 경보 구조: 센서 3개 → v2 세 성분 → conformal 문턱 → R2 교차 확인 → R1 사건 지속 → 2단계 경보, 아래에 확률 층."""
    fig, ax = plt.subplots(figsize=(7.8, 3.9))
    ax.set_xlim(0, 13.2); ax.set_ylim(0, 5.9); ax.axis("off")
    for i, name in enumerate(["상부 진동", "하부 진동", "모터 전류"]):
        box(ax, (0.1, 3.95 - i * 1.15), 1.45, 0.75, name, size=8.4)
    comps = ["크기\n세 센서의\n표준화 최댓값", "파형\n최근 6~8행 전류의\n사인 적합 1-R²", "동역학\nAR(2) 예측 오차"]
    for i, c in enumerate(comps):
        box(ax, (2.05, 3.8 - i * 1.15), 2.45, 1.05, c, fc="#e8f0fb", ec=A, size=7.6)
    # 입력 연결(2.3절 설정표): 크기는 세 센서 모두, 파형·동역학은 전류만 쓴다
    for i in range(3):   # 크기 상자로 들어가는 끝점을 위·가운데·아래로 나눈다
        arrow(ax, (1.55, 4.32 - i * 1.15), (2.05, 4.6 - i * 0.28))
    for j in (1, 2):
        arrow(ax, (1.55, 4.32 - 2 * 1.15), (2.05, 4.32 - j * 1.15))
    box(ax, (5.0, 2.45), 2.1, 1.75, "성분별 꼬리 점수\n(꼬리 확률의 -log10)\n중 최댓값 →\nconformal 문턱\n(valid 정상, α 1%)", size=7.2)
    for i in range(3):
        arrow(ax, (4.5, 4.32 - i * 1.15), (5.0, 3.32))
    box(ax, (7.55, 2.45), 2.2, 1.75, "R2 교차 확인\n크기 단독 경보이고\n전류 R²(8행 이상)가\n기준 이상이면 보류", fc="#fdeee6", ec=B, size=6.8)
    box(ax, (10.2, 2.45), 2.9, 1.75, "R1 사건 지속\n직전 기록(60초 안)이\n확인된 이상(경보 2행↑)이면\n첫 행부터 유지,\n8행 이상 R² 정상 시 해제", fc="#fdeee6", ec=B, size=6.8)
    arrow(ax, (7.1, 3.32), (7.55, 3.32)); arrow(ax, (9.75, 3.32), (10.2, 3.32))
    box(ax, (10.2, 0.2), 2.9, 1.5, "1단계 주의 = R1만 거침\n(잠금 모델 v2+R1)\n2단계 점검 요청 =\nR2·R1 통과(v2+R1+R2)", fc="white", ec=INK2, size=7.0, weight="bold")
    ax.annotate("", xy=(10.35, 4.05), xytext=(6.9, 4.05), arrowprops=dict(arrowstyle="->", color=INK2, lw=0.9, ls="--", connectionstyle="arc3,rad=-0.3"))
    ax.text(8.65, 5.0, "1단계는 R2를 거치지 않음", ha="center", fontsize=7.2, color=INK2)
    arrow(ax, (11.65, 2.45), (11.65, 1.7))
    box(ax, (2.05, 0.2), 7.7, 1.2, "확률 층(경보와 별도)\nv2 점수 → 단조 회귀(valid로만 맞춤) → 우도비 × 사전 오즈\n→ 이상 확률(예측 파일 열)",
        fc="#f3f2ef", size=7.2)
    arrow(ax, (6.05, 2.45), (6.05, 1.4))
    ax.text(4.55, 5.55, "기반 모델 v2(정상만 학습)", ha="center", fontsize=8.5, color=A)
    ax.text(10.35, 5.55, "규칙(경보 운영)", ha="center", fontsize=8.5, color=B)
    save(fig, "fig11_model_structure.png")


def fig_alarm_card():
    """[그림 13] 2단계 경보 카드 예시(분할 B test): 이상 기록 하나와, v2는 울렸지만 R2가 보류한 정상 기록 하나."""
    t = pd.read_pickle(ROOT / "code/press/tvt/cache/rows_B.pkl")
    pred = pd.read_csv(TVT / "test_predictions_B.csv")
    t = t[t.part == "test"].merge(pred[["subset", "rec", "pos", "final_v2_R1_R2_realtime", "locked_v2_R1_realtime", "v2_realtime"]], on=["subset", "rec", "pos"])
    held = pred[(pred.subset == "normal") & pred.v2_realtime & ~pred.final_v2_R1_R2_realtime].rec.unique()
    cases = [("abnormal", "test:abnormal:11", "(a) 이상 기록 11(상부 진동만 큰 양상)\nv2가 끊긴 행까지 R1이 채워\n기록 전체가 경보 → 2단계"),
             ("normal", held[0], f"(b) 분할 B 정상 기록 {420 + int(held[0].split(':')[-1])}(test)\nv2 크기만 넘어 1단계 주의,\nR2로 2단계는 보류")]
    lanes = [("크기 문턱", "magnitude", A), ("파형 문턱", "waveform", A), ("동역학 문턱", "dynamics", A), ("v2 경보", None, INK2), ("1단계 경보", None, INK2), ("2단계 경보", None, B)]
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.2), sharey=True)
    for ax, (sub, rec, title) in zip(axes, cases):
        r = t[(t.subset == sub) & (t.rec == rec)].sort_values("pos")
        for i, (name, comp, col) in enumerate(lanes):
            if comp:     # 성분 꼬리 확률이 α 1% 이하인 행(그 성분이 문턱을 넘음)
                on = r.pos[r[f"v2|cp_full|{comp}"] <= 0.01]
            else:
                on = r.pos[r[{"v2 경보": "v2_realtime", "1단계 경보": "locked_v2_R1_realtime"}.get(name, "final_v2_R1_R2_realtime")].astype(bool)]
            y = len(lanes) - 1 - i
            ax.broken_barh([(p - 0.5, 1) for p in on], (y - 0.38, 0.76), color=col, lw=0)
            ax.plot([r.pos.min() - 0.5, r.pos.max() + 0.5], [y - 0.42, y - 0.42], color="#e6e5e1", lw=0.6)
            if name == "2단계 경보" and on.empty:
                ax.text((r.pos.min() + r.pos.max()) / 2, y, "2단계 없음(R2 보류)", ha="center", va="center", fontsize=8.5, color=B)
        ax.set_xlim(r.pos.min() - 0.5, r.pos.max() + 0.5)
        ax.set_title(title, fontsize=9, loc="left", color=INK)
        ax.set_xlabel("기록 안 위치(행, 0.1초)", fontsize=8)
    axes[0].set_yticks(range(len(lanes)), [n for n, _, _ in lanes][::-1], fontsize=9)
    axes[0].tick_params(axis="y", length=0)
    save(fig, "fig12_alarm_card.png")


def fig_stage_timeline():
    """[그림 14] 제출 예측 파일(분할 B test)의 기록별 두 단계 경보: 정상 180기록(시간순)과 이상 11기록."""
    pred = pd.read_csv(TVT / "test_predictions_B.csv")
    g = pred.groupby(["subset", "rec"], sort=False).agg(s1=("locked_v2_R1_realtime", "any"), s2=("final_v2_R1_R2_realtime", "any")).reset_index()
    g["k"] = g.rec.str.split(":").str[-1].astype(int)
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 1.9), sharey=True, gridspec_kw=dict(width_ratios=[180, 34]))
    for ax, sub, title in zip(axes, ("normal", "abnormal"), ("(a) 정상 test 180기록(시간순)", "(b) 이상 test 11기록")):
        d = g[g.subset == sub].sort_values("k").reset_index(drop=True)
        for lane, col, color, y in (("1단계", "s1", INK2, 1), ("2단계", "s2", B, 0)):
            on = d.index[d[col].astype(bool)]
            ax.broken_barh([(i - 0.45, 0.9) for i in on], (y - 0.35, 0.7), color=color, lw=0)
            ax.plot([-0.5, len(d) - 0.5], [y - 0.42] * 2, color="#e6e5e1", lw=0.6)
            ax.text(len(d) - 0.5, y + 0.38, f"{len(on)}기록", ha="right", va="bottom", fontsize=7.5, color=color)
        ax.set_xlim(-0.5, len(d) - 0.5); ax.set_ylim(-0.6, 1.75)
        ax.set_title(title, fontsize=9, loc="left", color=INK)
        ax.set_xlabel("기록 순서", fontsize=8)
    axes[0].set_yticks([1, 0], ["1단계 주의", "2단계 점검 요청"], fontsize=9)
    axes[0].tick_params(axis="y", length=0)
    save(fig, "fig13_stage_timeline.png")


if __name__ == "__main__":
    fig_structure(); fig_collection(); fig_flow(); fig_miss_position(); fig_models(); fig_rules(); fig_leak(); fig_console()
    fig_observability(); fig_regime_timeline(); fig_load_vibration(); fig_model_structure(); fig_alarm_card(); fig_stage_timeline()
    print(sorted(p.name for p in FIG.glob("*.png")))
