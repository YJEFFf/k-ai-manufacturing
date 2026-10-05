"""보고서 그림 11개를 그린다. 숫자는 모두 분석 산출물에서 읽는다(facts.csv와 같은 원천).

입력: code/press/{tvt,cases,domain}/outputs, data/3_소성가공_예지보전/*.csv, report/console_source/console_workspace_v2.png
출력: report/figures/fig*.png (200 dpi)
실행: python report/make_figures.py
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
    fig, ax = plt.subplots(figsize=(7.6, 3.9))
    ax.set_xlim(0, 10.5); ax.set_ylim(0, 5.0); ax.axis("off")
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
    for y, s in ((3.75, "AI0 상부 진동"), (1.25, "AI1 하부 진동")):
        ax.plot([2.55, 3.0], [y, y], color=A, lw=1.5); ax.plot(2.55, y, "o", color=A, ms=5)
        ax.text(3.05, y, s, va="center", fontsize=8.3, color=INK)
    ax.plot([0.12, 0.12, 0.55], [4.85, 3.4, 3.4], color=B, lw=1.5); ax.plot(0.55, 3.4, "o", color=B, ms=5)
    ax.text(0.2, 4.88, "AI2 모터 전력선 전류", fontsize=8.3, color=INK, va="bottom")
    ax.text(5.2, 0.28, "(일반 구조, 추정) 펌프 모터 부하는 행정(고속 접근→감지→저속 블랭킹→고속 복귀)과 어큐뮬레이터 충전·언로딩에 따라 오르내린다(추정)",
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
    """[그림 6] 분석 흐름 7단계."""
    steps = ["데이터·구조\n확인", "데이터 결함\n진단", "오류 분석과\n규칙 R1·R2", "train/valid/test\n잠금 채점", "의심과 검증\n(2.6절)", "사후: 설비 물리\n·관측 가능성", "사후: 표준 기법\n·운전 상태"]
    fig, ax = plt.subplots(figsize=(8.4, 1.5))
    ax.set_xlim(0, len(steps) * 1.5); ax.set_ylim(0, 1.2); ax.axis("off")
    for i, s in enumerate(steps):
        box(ax, (i * 1.5 + 0.03, 0.15), 1.3, 0.9, s, size=7.8)
        if i:
            arrow(ax, (i * 1.5 - 0.17, 0.6), (i * 1.5 + 0.03, 0.6))
    save(fig, "fig3_flow.png")


def fig_miss_position():
    """[그림 9] v2 test 미탐 행의 기록 안 위치."""
    e = json.loads((TVT / "tvt_hypotheses.json").read_text(encoding="utf-8"))["v2_test_errors"]
    pos = sorted({int(k) for s in "AB" for k in e[s]["missed_by_position"]})
    x = np.arange(len(pos)); w = 0.38
    fig, ax = plt.subplots(figsize=(6.2, 2.6))
    for off, s, c in ((-w / 2, "A", A), (w / 2, "B", B)):
        v = [e[s]["missed_by_position"].get(str(p), 0) for p in pos]
        ax.bar(x + off, v, w - 0.04, color=c, label=f"분할 {s} (미탐 {e[s]['missed_rows']}행)")
        for xi, vi in zip(x + off, v):
            if vi:
                ax.text(xi, vi + 0.15, str(vi), ha="center", fontsize=8, color=INK2)
    ax.set_xticks(x, [str(p) for p in pos]); ax.set_xlabel("기록 안 위치(행, 0 = 기록 첫 행)"); ax.set_ylabel("v2 미탐 행 수")
    ax.legend(frameon=False, fontsize=8.5)
    ax.set_title("v2의 test 미탐은 기록 시작 직후에 몰린다", fontsize=10, loc="left", color=INK)
    save(fig, "fig4_miss_position.png")


# 모델 비교 그림의 막대 순서와 표시 이름(내부 이름 H1·H2 = 보고서의 R1·R2)
NAMES = {"iforest": "IsolationForest", "lstm20": "LSTM-AE(20행)", "maxz3": "max|z|", "knn5": "5NN", "mlp_ae5": "MLP-AE(5행)",
         "v1": "v1", "v2": "기반 모델 v2", "v2+C1d1": "v2+v3 조건부", "v2+H1": "v2+R1(잠금 선택)", "v2+H1+H2": "v2+R1+R2(최종)"}


def fig_models():
    """[그림 8] 같은 분할·같은 보정에서 모델별 test F1(α 1%, 실시간)."""
    t = pd.read_csv(TVT / "tvt_test.csv")
    t = t[(t.alpha == 0.01) & (t["mode"] == "realtime") & t.model.isin(NAMES)]
    p = t.pivot_table(index="model", columns="split", values="f1").loc[list(NAMES)]
    y = np.arange(len(p)); h = 0.38
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for off, s, c in ((h / 2, "A", A), (-h / 2, "B", B)):
        ax.barh(y + off, p[s], h - 0.05, color=c, label=f"분할 {s}")
    for yi, (ma, mb) in zip(y, p[["A", "B"]].to_numpy()):
        ax.text(max(ma, mb) + 0.01, yi, f"{ma:.3f} / {mb:.3f}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, [NAMES[m] for m in p.index]); ax.set_xlim(0, 1.18); ax.set_xlabel("test 실시간 행 단위 F1 (α 1%)")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax.set_title("같은 분할·같은 보정에서의 모델 비교", fontsize=10, loc="left", color=INK)
    save(fig, "fig5_models.png")


def fig_rules():
    """[그림 10] 규칙 R1·R2를 더할 때 test 미탐·오경보 행 수."""
    t = pd.read_csv(TVT / "tvt_test.csv")
    t = t[(t.alpha == 0.01) & (t["mode"] == "realtime")]
    order = ["v2", "v2+H2", "v2+H1", "v2+H1+H2"]; labels = ["v2", "+R2", "+R1", "+R1+R2"]
    x = np.arange(len(order)); w = 0.38
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6))
    for ax, col, title in ((axes[0], "fn", "미탐 행"), (axes[1], "fp", "오경보 행")):
        for off, s, c in ((-w / 2, "A", A), (w / 2, "B", B)):
            v = [int(t[(t.model == m) & (t.split == s)][col].iloc[0]) for m in order]
            ax.bar(x + off, v, w - 0.04, color=c, label=f"분할 {s}")
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
        ax.bar(x + w / 2, [ad.get(str(k), 0) for k in keys], w - 0.04, color=B, label="이상 파일")
        ax.set_xticks(x, [str(k) for k in keys]); ax.set_xlabel("상부 진동값의 소수 자릿수")
        sub = f"'자릿수 > 6' 규칙 F1 {d['f1']:.3f}" if tag == "raw" else "두 파일의 자릿수 분포가 같아짐"
        ax.set_title(f"{title}: {sub}", fontsize=10, loc="left", color=INK)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    axes[0].set_ylabel("행 비율"); axes[0].legend(frameon=False, fontsize=8.5)
    save(fig, "fig0_leak.png")


def fig_console():
    """[그림 11] Press Guard 콘솔 화면 캡처의 위쪽 1300픽셀만 잘라 쓴다."""
    from PIL import Image
    img = Image.open(HERE / "console_source" / "console_workspace_v2.png")
    img.crop((0, 0, img.width, min(img.height, 1300))).save(FIG / "fig7_console.png")


def fig_observability():
    """[그림 2] 10Hz 점 샘플로 무엇을 볼 수 있나: 주파수 축(로그) 위 현상 대역과 접힘(에일리어싱)."""
    ph = json.loads((DOM / "01_signal_physics.json").read_text(encoding="utf-8"))
    fa = ph["1_alias_sampling_interval"]["normal_records_ge30"]["f_alias"]["median"]
    rows = [  # (이름, 시작 Hz, 끝 Hz, 색, 근거)
        ("프레스 행정 주기(수십~최대 100spm)", 0.3, 1.7, A, "추정"),
        ("모터 회전 1X·2X(4극 가정 약 29·59Hz)", 28, 60, GREY, "가정"),
        ("전원 60Hz와 홀수 고조파 180·300·420Hz", 60, 420, B, "전류 고조파와 부합(가설)"),
        ("기어 맞물림(잇수 9~12 × 회전, 약 260~350Hz)", 260, 350, GREY, "가정"),
        ("캐비테이션 고주파 광대역", 1000, 20000, GREY, "추정"),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    ax.axvspan(0.1, 5, color="#e8f0fb", lw=0)
    ax.text(0.12, len(rows) + 0.15, "10Hz 점 샘플이 직접 담는 대역(나이퀴스트 5Hz 이하)", fontsize=8, color=A, va="bottom")
    for i, (name, lo, hi, c, src) in enumerate(rows[::-1]):
        y = i + 0.5
        ax.plot([lo, hi], [y, y], color=c, lw=6, solid_capstyle="butt")
        ax.text(hi * 1.25 if hi < 5000 else lo / 1.3, y, f"{name} [{src}]", va="center", fontsize=7.8, color=INK,
                ha="left" if hi < 5000 else "right")
    for f_src, f_app in ((60, fa), (180, 3 * fa)):   # 전원 60Hz와 3고조파가 10Hz 샘플에서 접혀 보이는 주파수
        ax.annotate("", xy=(f_app, 2.5 - 0.35), xytext=(f_src, 2.5 - 0.1),
                    arrowprops=dict(arrowstyle="-|>", color=B, lw=0.9, ls="--", connectionstyle="arc3,rad=0.25"))
        ax.plot(f_app, 2.15, "v", color=B, ms=4)
    ax.text(fa * 1.15, 1.75, f"접힘(가설): 60Hz 계열→{fa:.2f}Hz, 180Hz→{3*fa:.2f}Hz", fontsize=7.6, color=B)
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
    fig, axes = plt.subplots(2, 1, figsize=(7.4, 3.6), sharex=True, gridspec_kw={"hspace": 0.18})
    for ax, col, lab in ((axes[0], "cur_amp", "전류 사인 진폭(부하)"), (axes[1], "vib_lower_sd", "하부 진동 SD")):
        ax.axvspan(m[q].min(), m[q].max(), color="#efeeea", lw=0)
        ax.scatter(m, r[col], s=5, color=A, lw=0)
        ax.set_ylabel(lab, fontsize=8.5)
    fa = r["fa1_B_v2"].fillna(0) > 0
    axes[0].scatter(m[fa], r.loc[fa, "cur_amp"], s=40, facecolor="none", edgecolor=B, lw=1.3, label="v2 오경보 기록(α 1%, valid·test)")
    axes[0].legend(frameon=True, framealpha=0.92, edgecolor="none", fontsize=7.6, loc="lower left")
    axes[0].text(m[q].mean(), 45, "정숙 구간 12분(연속 저부하)", ha="center", va="center", fontsize=6.8, color=INK2)
    # 가이드북 16,000~19,000행 구간 = 기록 481~570
    g0 = m[r.rec == 481].iloc[0]; g1 = (pd.to_datetime(r.loc[r.rec == 570, "ts1"]).iloc[0] - t0).total_seconds() / 60
    axes[0].annotate("", xy=(g0, 22), xytext=(g1, 22), arrowprops=dict(arrowstyle="|-|", color=INK2, lw=0.8, mutation_scale=3))
    axes[0].text((g0 + g1) / 2, 6, "가이드북 16,000~19,000행", ha="center", va="center", fontsize=6.6, color=INK2)
    for rec, lab, ls in ((300, "B 학습|검증", ":"), (360, "A 학습|검증", "--"), (420, "B 검증|시험", ":"), (480, "A 검증|시험", "--")):
        x = m[r.rec == rec].iloc[0]
        for ax in axes:
            ax.axvline(x, color=GREY, lw=0.8, ls=ls)
        axes[0].text(x, 1.02 if lab.startswith("B") else 1.11, lab, transform=axes[0].get_xaxis_transform(), fontsize=6.4, color=INK2, ha="center", va="bottom")
    axes[1].set_xlabel("정상 파일 경과 시간(분, 2022-07-12 00:00~)")
    save(fig, "fig9_regime_timeline.png")


def fig_load_vibration():
    """[그림 7] 부하(전류 RMS)와 진동 SD의 정상 관계, 그리고 그 관계에서 벗어난 이상 기록(로그-로그)."""
    s = pd.read_csv(DOM / "01_signal_physics_records.csv")
    s = s[s.n >= 20]
    nrm, ab, tr = s[s.set == "normal"], s[s.set == "abnormal"], s[s.split == "train"]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    for ax, col, lab in ((axes[0], "sd_lower", "하부 진동 SD"), (axes[1], "sd_upper", "상부 진동 SD")):
        ax.scatter(nrm.cur_rms, nrm[col], s=6, color=A, alpha=0.6, lw=0, label="정상 기록(20행 이상)")
        ax.scatter(ab.cur_rms, ab[col], s=22, color=B, lw=0, label="이상 기록")
        b1, b0 = np.polyfit(np.log(tr.cur_rms), np.log(tr[col]), 1)
        xx = np.linspace(np.log(tr.cur_rms.min()), np.log(tr.cur_rms.max()), 50)
        ax.plot(np.exp(xx), np.exp(b0 + b1 * xx), color=INK2, lw=1, label="정상 학습 기록의 로그-로그 회귀")
        ax.text(0.98, 0.04, f"정상 기울기 {b1:.2f}", transform=ax.transAxes, ha="right", fontsize=7.6, color=INK2)
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("전류 RMS(부하 대리변수)", fontsize=8.5)
        yt = [0.03, 0.05, 0.1, 0.2, 0.3] if col == "sd_lower" else [0.03, 0.1, 0.3, 1.0]
        ax.set_xticks([60, 80, 100, 150, 200], ["60", "80", "100", "150", "200"]); ax.set_yticks(yt, [f"{v:g}" for v in yt])
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter()); ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_title(lab, fontsize=9.5, loc="left", color=INK)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=7.6, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.17))
    save(fig, "fig10_load_vibration.png")


if __name__ == "__main__":
    fig_structure(); fig_collection(); fig_flow(); fig_miss_position(); fig_models(); fig_rules(); fig_leak(); fig_console()
    fig_observability(); fig_regime_timeline(); fig_load_vibration()
    print(sorted(p.name for p in FIG.glob("*.png")))
