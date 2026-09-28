"""진단 그림 5장(평가관 01 D2) — 원본과 build_diagnostics.py의 표에서 다시 그린다.

그림 속 수치는 원본에서 다시 계산해 표 값과 같은지 assert로 대조한 뒤에만 그린다. 축의 센서 값은 단위가 적혀 있지 않은
원값 또는 표준화 척도다. 보고서 서술이 아니다.

    python yejun/analysis/press_evidence/figures.py

단독 실행은 그림만 다시 그린다. manifest까지 갱신하려면 build_diagnostics.py를 실행한다.
"""
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FixedLocator, FuncFormatter  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import D, BASE  # noqa: E402

FIG = HERE / "figures"
_fonts = {f.name for f in fm.fontManager.ttflist}
plt.rcParams.update({"font.family": [f for f in ("AppleGothic", "Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic", "Nanum Gothic", "Noto Sans CJK KR") if f in _fonts] + ["DejaVu Sans"],
                     "axes.unicode_minus": False, "mathtext.fontset": "dejavusans", "font.size": 9, "axes.titlesize": 10, "axes.edgecolor": "#c3c2b7", "axes.linewidth": .8,
                     "xtick.color": "#52514e", "ytick.color": "#52514e", "axes.labelcolor": "#0b0b0b", "text.color": "#0b0b0b",
                     "axes.grid": True, "grid.color": "#e4e3df", "grid.linewidth": .6, "axes.axisbelow": True,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb"})
NORMAL, ABNORMAL, FALSE_ALARM = "#2a78d6", "#eb6834", "#1baf7a"     # 범주 1~3번(검증 팔레트, 전체 쌍 통과)
MUTED, INK2 = "#b8b7b2", "#52514e"
STAGE = {"학습": "#9ec5f4", "보정": "#3987e5", "평가": "#184f95"}     # 순서형 한 색상 단계
QUIET = "#ecebe7"
UNIT = "단위 미기재"
STATE_COLOR = {"부하": "#5b3fa0", "저수준": "#b9a8e6", "짧은 기록(<17)": "#dcdbd5"}   # 운전 상태(한 색상 명암, 다른 범주색과 겹치지 않음)


def _save(fig, name):
    FIG.mkdir(exist_ok=True)
    path = FIG / name
    fig.savefig(path, dpi=150, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return path


def _clean(ax, grid_axis="y"):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x" if grid_axis == "y" else "y", visible=False)


def _minutes(tt, day0):
    return (tt - day0).dt.total_seconds().to_numpy() / 60


# ---------- (a) 수집 타임라인 ----------
def timeline(raw, seg, t, tables):
    gaps = pd.read_csv(HERE / "gaps.csv").set_index("file")
    fig, axes = plt.subplots(3, 1, figsize=(11, 7.2), gridspec_kw=dict(height_ratios=[2.2, 1.0, 1.0], hspace=.55))
    day0 = t["normal"].dt.normalize().iloc[0]
    start = t["normal"].groupby(seg["normal"]).min(); end = t["normal"].groupby(seg["normal"]).max()
    s_min, e_min = _minutes(start, day0), _minutes(end, day0) + D.DT / 60
    assert len(s_min) == int(gaps.loc["normal", "segments"]) and len(np.unique(seg["abnormal"])) == int(gaps.loc["abnormal", "segments"])
    rows = [("기록구간(운전 상태)", None)] + [(f"분할 {sid}", sid) for sid in D.SPLITS] + [(f"롤링 {e + 120}~{e + 179}", e) for e in (180, 240, 300, 360, 420)]
    roll = tables["rolling_calibration_curve.csv"]
    same = dict(roll[roll.same_as_frozen.fillna("").ne("") & roll.k.eq(1)][["train_end", "same_as_frozen"]].astype({"train_end": int}).values.tolist())
    for train_end, sid in same.items():      # '= 동결' 표시는 학습·보정 경계가 그 분할과 같은 폴드에만 붙는다
        assert (train_end, train_end + 120) == D.SPLITS[sid][1:], (train_end, sid)
    ax = axes[0]
    q0, q1 = s_min[480], e_min[539]
    ax.axvspan(q0, q1, color=QUIET, zorder=0)
    ost = tables["operating_states.csv"]
    summ = tables["operating_states_summary.csv"].set_index("item")
    run = summ.loc["가장 긴 저수준 연속(길이≥17 기록)"]
    ax.text((q0 + q1) / 2, len(rows) - .35, f"가장 조용한 블록 480~539\n(연속 저수준 {run.value2}, {int(run.value)}기록)", ha="center", va="bottom", fontsize=8, color=INK2)
    y = len(rows) - 1
    state = pd.Series("짧은 기록(<17)", index=np.arange(len(s_min)))
    state.loc[ost.record.to_numpy()] = ost.state.to_numpy()
    lens = pd.Series(seg["normal"]).value_counts().sort_index()
    assert ((lens >= 17).to_numpy() == state.ne("짧은 기록(<17)").to_numpy()).all()
    assert int(state.eq("저수준").sum()) == int((ost.state == "저수준").sum())
    for st_name, color in STATE_COLOR.items():
        m = state.eq(st_name).to_numpy()
        ax.broken_barh(list(zip(s_min[m], (e_min - s_min)[m])), (y - .3, .6), color=color, linewidth=0, label=f"{st_name} {int(m.sum())}")
    bound = lambda s: s_min[s] if s < len(s_min) else e_min[-1]
    for i, (label, key) in enumerate(rows[1:], 1):
        yy = y - i
        if isinstance(key, str):
            _, tr, ca = D.SPLITS[key]
            spans = (("학습", 0, tr), ("보정", tr, ca), ("평가", ca, 600))
        else:
            spans = (("학습", 0, key), ("보정", key, key + 120), ("평가", key + 120, key + 180))
            if key in same:
                label += f" (= 동결 {same[key]})"
        for stage, a, b in spans:
            ax.broken_barh([(bound(a), bound(b) - bound(a))], (yy - .3, .6), color=STAGE[stage], linewidth=0)
        rows[i] = (label, key)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1])
    ax.set_xlim(0, e_min[-1] + .5)
    ticks = np.arange(0, 80, 10)
    ax.set_xticks(ticks); ax.set_xticklabels([f"00:{m:02d}" if m < 60 else f"01:{m - 60:02d}" for m in ticks])
    rec_s, ela_s = len(raw["normal"]) * D.DT, (t["normal"].max() - t["normal"].min()).total_seconds()
    ax.set_title(f"정상 2022-07-12(화): {len(s_min)}구간·{len(raw['normal']):,}행, 기록 {rec_s:,.0f}초 / 경과 {ela_s:,.0f}초({rec_s / ela_s:.1%})", loc="left")
    h_state, l_state = ax.get_legend_handles_labels()          # 한 범례에 운전 상태(기록 수)와 분할 역할을 함께 둔다
    stage_handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in STAGE.values()]
    ax.legend(h_state + stage_handles, [f"기록: {l}" for l in l_state] + [f"분할: {k}" for k in STAGE], loc="upper left",
              bbox_to_anchor=(1.0, 1.0), frameon=False, fontsize=8)
    _clean(ax, "y")
    # 확대: 2분
    ax = axes[1]
    lo, hi = 30.0, 32.0
    m = (s_min >= lo) & (e_min <= hi)
    for st_name, color in STATE_COLOR.items():
        subset = m & state.eq(st_name).to_numpy()
        ax.broken_barh(list(zip(s_min[subset], e_min[subset] - s_min[subset])), (-.3, .6), color=color, linewidth=0)
    rms = raw["normal"].AI2_Current.groupby(seg["normal"]).apply(lambda x: float(np.sqrt(np.mean((x - x.mean()) ** 2))))
    assert np.allclose(rms.loc[ost.record], ost.current_rms_dm, rtol=0, atol=1e-10)
    for record in np.flatnonzero(m):
        ax.text((s_min[record] + e_min[record]) / 2, .36, f"{record}\n{rms.loc[record]:.0f}", ha="center", va="bottom", fontsize=7, color=INK2)
    ax.set_ylim(-.45, 1.2)
    gap = (start.to_numpy()[1:] - end.to_numpy()[:-1]) / np.timedelta64(1, "s")      # 앞 기록 마지막 행 → 다음 기록 첫 행
    gap = gap[gap > 0]                                                                   # 중복 시각 경계(0초) 1곳 제외
    assert abs(np.median(gap) - float(gaps.loc["normal", "gap_median_s"])) < 1e-9 and abs(gap.min() - float(gaps.loc["normal", "gap_min_s"])) < 1e-9
    ax.set_xlim(lo, hi); ax.set_yticks([])
    ax.set_xticks(np.arange(lo, hi + .01, .25)); ax.set_xticklabels([f"00:{int(v):02d}:{int(round((v % 1) * 60)):02d}" for v in np.arange(lo, hi + .01, .25)])
    ax.set_title(f"확대 00:30~00:32: {int(m.sum())}기록, 위 숫자는 기록 번호 / 전류 RMS. 공백 중앙 {np.median(gap):.1f}초(전체 {gap.min():.2f}~{gap.max():.1f}초)", loc="left")
    _clean(ax, "y")
    # 이상 3분
    ax = axes[2]
    day1 = t["abnormal"].dt.normalize().iloc[0]
    sa = t["abnormal"].groupby(seg["abnormal"]).min(); ea = t["abnormal"].groupby(seg["abnormal"]).max()
    sa_m, ea_m = _minutes(sa, day1), _minutes(ea, day1) + D.DT / 60
    ax.broken_barh(list(zip(sa_m, ea_m - sa_m)), (-.3, .6), color=ABNORMAL, linewidth=0)
    ax.set_yticks([])
    tk = np.arange(np.floor(sa_m.min()), np.ceil(ea_m.max()) + .01, .5)
    ax.set_xticks(tk); ax.set_xticklabels([f"{int(v // 60):02d}:{int(v % 60):02d}:{int(round((v % 1) * 60)):02d}" for v in tk])
    rec_a, ela_a = len(raw["abnormal"]) * D.DT, (t["abnormal"].max() - t["abnormal"].min()).total_seconds()
    ax.set_title(f"이상 2022-07-17(일): {len(sa_m)}구간·{len(raw['abnormal'])}행, 기록 {rec_a:.0f}초 / 경과 {ela_a:.1f}초({rec_a / ela_a:.1%})", loc="left")
    _clean(ax, "y")
    fig.suptitle("수집 타임라인 — 막대 하나가 기록구간 하나. 기록 색은 저수준·부하 범위(약 20초 주기로 교대, 물리 해석은 가설)",
                 x=.01, ha="left", fontsize=10.5)
    return _save(fig, "fig_d2a_timeline.png")


# ---------- (b) 60구간 블록 ----------
def blocks(raw, seg):
    n, sn = raw["normal"], seg["normal"]
    cur = n.AI2_Current.to_numpy(float)
    dm = cur - pd.Series(cur).groupby(sn).transform("mean").to_numpy()
    ref = pd.read_csv(HERE / "block_context.csv")
    vals = {"AI0_sd": [], "AI1_sd": [], "current_rms_demeaned": []}
    for b in range(10):
        m = (sn >= 60 * b) & (sn < 60 * b + 60)
        vals["AI0_sd"].append(float(n.AI0_Vibration[m].std())); vals["AI1_sd"].append(float(n.AI1_Vibration[m].std()))
        vals["current_rms_demeaned"].append(float(np.sqrt(np.mean(dm[m] ** 2))))
    for k, v in vals.items():
        assert np.allclose(v, ref[k].to_numpy(), rtol=0, atol=1e-12), k
    fig = plt.figure(figsize=(11, 4.6))
    gs = fig.add_gridspec(2, 3, height_ratios=[4, 1], hspace=.35, wspace=.28)
    labels = [f"{60 * b}~{60 * b + 59}" for b in range(10)]
    quiet = 8
    titles = {"AI0_sd": f"상부 진동 AI0 SD({UNIT})", "AI1_sd": f"하부 진동 AI1 SD({UNIT})", "current_rms_demeaned": f"전류 RMS, 구간 평균 제거({UNIT})"}
    for j, (k, v) in enumerate(vals.items()):
        ax = fig.add_subplot(gs[0, j])
        colors = [NORMAL if b == quiet else MUTED for b in range(10)]
        ax.bar(range(10), v, width=.62, color=colors)
        ax.text(quiet, v[quiet], f"{v[quiet]:.3g}", ha="center", va="bottom", fontsize=8)
        ax.text(int(np.argmax(v)), max(v), f"{max(v):.3g}", ha="center", va="bottom", fontsize=8, color=INK2)
        ax.set_xticks(range(10)); ax.set_xticklabels(labels, rotation=60, fontsize=7)
        ax.set_title(titles[k], loc="left", fontsize=9)
        _clean(ax)
        sx = fig.add_subplot(gs[1, j])
        for r, sid in enumerate(D.SPLITS):
            _, tr, ca = D.SPLITS[sid]
            for b in range(10):
                stage = "학습" if 60 * b < tr else ("보정" if 60 * b < ca else "평가")
                sx.add_patch(plt.Rectangle((b - .45, 1 - r - .4), .9, .8, color=STAGE[stage], linewidth=0))
        sx.set_xlim(-.6, 9.6); sx.set_ylim(-.6, 1.6); sx.set_xticks([]); sx.set_yticks([0, 1]); sx.set_yticklabels(["B", "A"])
        sx.grid(False)
        for side in ("top", "right", "bottom", "left"):
            sx.spines[side].set_visible(False)
    fig.suptitle("정상 60구간 블록별 운전 수준(블록당 60구간). 파란 막대 480~539는 A 평가 앞부분의 가장 조용한 블록. 아래 띠는 분할 역할(연한→진한: 학습·보정·평가)",
                 x=.01, ha="left", fontsize=10)
    return _save(fig, "fig_d2b_blocks.png")


# ---------- (c) 원시 신호 예시 ----------
def raw_examples(raw, seg, tables):
    n, a = raw["normal"], raw["abnormal"]
    ost = tables["operating_states.csv"].set_index("record")
    tr = n[seg["normal"] < D.SPLITS["A"][1]]
    mu, sdv = tr[D.SENSORS].mean(), tr[D.SENSORS].std(ddof=0)
    lens_n = pd.Series(seg["normal"]).value_counts(); lens_a = pd.Series(seg["abnormal"]).value_counts()
    loaded50 = [int(s) for s in sorted(lens_n[lens_n == 50].index) if ost.loc[s, "state"] == "부하"]
    pick_n = [loaded50[0], int(min(s for s in lens_n[lens_n == 50].index if s >= 480))]      # 부하 기록 하나, 가장 조용한 블록의 저수준 기록 하나
    assert ost.loc[pick_n[0], "state"] == "부하" and ost.loc[pick_n[1], "state"] == "저수준"
    pick_a = sorted(int(s) for s in lens_a[lens_a == 50].index)[:2]
    cases = [(f"정상·{ost.loc[s, 'state']}", n, seg["normal"], s, NORMAL) for s in pick_n] + [("이상", a, seg["abnormal"], s, ABNORMAL) for s in pick_a]
    fig, axes = plt.subplots(3, 4, figsize=(11, 6), sharey="row", sharex=True)
    for j, (kind, f, sg, s, color) in enumerate(cases):
        sub = f[sg == s]
        assert len(sub) == 50
        z = (sub[D.SENSORS] - mu) / sdv
        tt = np.arange(50) * D.DT
        for i, c in enumerate(D.SENSORS):
            ax = axes[i, j]
            ax.plot(tt, z[c].to_numpy(), color=color, linewidth=1.3)
            if i == 0:
                rms = float(np.sqrt(np.mean((sub.AI2_Current - sub.AI2_Current.mean()) ** 2)))
                if kind.startswith("정상"):
                    assert abs(rms - float(ost.loc[s, "current_rms_dm"])) < 1e-9
                ax.set_title(f"{kind} 구간 {s}\n{pd.to_datetime(sub.TimeStamp.iloc[0]):%H:%M:%S} · 전류 RMS {rms:.1f}", fontsize=8.5, loc="left")
            if j == 0:
                ax.set_ylabel(f"{c}\n(A 학습 표준화 z)", fontsize=8)
            _clean(ax)
    for ax in axes[-1]:
        ax.set_xlabel("기록 안 시간(초)")
    fig.suptitle("같은 척도의 원시 신호 예시 — 정상 2(부하·저수준 상태)·이상 2 기록구간(각 4.9초). 가이드북 코드 12·13(26~27쪽)은 파일 전체를 행 번호로 이어 그려 "
                 "기록 공백(정상 599곳·이상 20곳)이 보이지 않고 센서·파일마다 세로 척도가 다르다", x=.01, ha="left", fontsize=9.5, wrap=True)
    return _save(fig, "fig_d2c_raw_examples.png")


# ---------- (d) 센서 관계 ----------
def relations(raw, st, fb, tables):
    rel = tables["sensor_relations.csv"]
    get = lambda sub, pair, tr=None, sec="행 상관": float(rel[(rel.section == sec) & (rel.subset == sub) & (rel.pair == pair)
                                                           & ((rel["transform"] == tr) if tr else True)].value.iloc[0])
    for sub, f in raw.items():
        assert abs(np.corrcoef(f.AI0_Vibration, f.AI1_Vibration)[0, 1] - get(sub, "AI0~AI1", "원값")) < 1e-12
        assert abs(np.corrcoef(f.AI0_Vibration.abs(), f.AI1_Vibration.abs())[0, 1] - get(sub, "AI0~AI1", "절댓값(가이드북 코드 14)")) < 1e-12
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2), gridspec_kw=dict(wspace=.3))
    ax = axes[0]
    ax.scatter(raw["normal"].AI0_Vibration, raw["normal"].AI1_Vibration, s=2, color=NORMAL, alpha=.25, linewidths=0, label=f"정상 {len(raw['normal']):,}행")
    ax.scatter(raw["abnormal"].AI0_Vibration, raw["abnormal"].AI1_Vibration, s=6, color=ABNORMAL, alpha=.7, linewidths=0, label=f"이상 {len(raw['abnormal'])}행")
    ax.set_xlabel(f"AI0 상부 진동 원값({UNIT})"); ax.set_ylabel(f"AI1 하부 진동 원값({UNIT})")
    ax.set_title(f"원값 상관 정상 {get('normal', 'AI0~AI1', '원값'):+.3f} → 이상 {get('abnormal', 'AI0~AI1', '원값'):+.3f}\n"
                 f"(절댓값 변환 뒤 {get('normal', 'AI0~AI1', '절댓값(가이드북 코드 14)'):+.3f} → {get('abnormal', 'AI0~AI1', '절댓값(가이드북 코드 14)'):+.3f}: 반전이 가려진다)",
                 loc="left", fontsize=9)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.16), ncol=2, frameon=False, markerscale=3, scatterpoints=1)
    _clean(ax)
    offsets = {423: (6, 5), 461: (6, -12), 570: (6, 4)}
    ost = tables["operating_states.csv"].set_index("record")
    summ = tables["operating_states_summary.csv"]
    for ax, col, pair in ((axes[1], "sd0", "AI0 SD~AI2 RMS"), (axes[2], "sd1", "AI1 SD~AI2 RMS")):
        sn, sa = st["normal"][st["normal"].n >= 17], st["abnormal"][st["abnormal"].n >= 17]
        rn, ra = stats.spearmanr(sn[col], sn.cur_rms_dm)[0], stats.spearmanr(sa[col], sa.cur_rms_dm)[0]
        assert abs(rn - get("normal", pair, sec="구간 수준 결합")) < 1e-12 and abs(ra - get("abnormal", pair, sec="구간 수준 결합")) < 1e-12
        sstate = ost.state.reindex(sn.index)
        for st_name in ("부하", "저수준"):
            g = sn[sstate == st_name]
            rw = stats.spearmanr(g[col], g.cur_rms_dm)[0]
            ref = summ[summ.item.eq(f"{st_name}: AI0 SD~전류 RMS / AI1 SD~전류 RMS(Spearman)")].iloc[0]
            assert abs(rw - float(ref.value if col == "sd0" else ref.value2)) < 1e-12
            ax.scatter(g.cur_rms_dm, g[col], s=10, color=STATE_COLOR[st_name], alpha=.75, linewidths=0,
                       label=f"정상 {st_name} {len(g)}구간(상태 안 {rw:.2f})")
        ax.scatter(sa.cur_rms_dm, sa[col], s=22, color=ABNORMAL, edgecolors="#fcfcfb", linewidths=.8, label=f"이상 {len(sa)}구간(순위상관 {ra:.2f})")
        fa = st["normal"].loc[fb]
        ax.scatter(fa.cur_rms_dm, fa[col], s=36, marker="D", color=FALSE_ALARM, edgecolors="#fcfcfb", linewidths=.8, label="B 오경보 구간(α=1%)")
        for s, r in fa.iterrows():
            ax.annotate(str(s), (r.cur_rms_dm, r[col]), xytext=offsets.get(s, (6, 4)), textcoords="offset points", fontsize=8, color=INK2)
        ax.set_xscale("log"); ax.set_yscale("log")
        for axis in (ax.xaxis, ax.yaxis):          # 로그 눈금을 일반 숫자로(한글 글꼴에 수학 기호 빼기 글리프가 없다)
            axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
            axis.set_minor_formatter(FuncFormatter(lambda v, _: ""))
        ax.set_xlabel(f"구간 전류 RMS, 평균 제거({UNIT}, 로그)"); ax.set_ylabel(f"구간 {'AI0' if col == 'sd0' else 'AI1'} 진동 SD({UNIT}, 로그)")
        ax.set_title(f"{'상부' if col == 'sd0' else '하부'} 진동–전류 진폭 결합(길이≥17 구간, Spearman)\n정상 전체 {rn:.2f}는 두 운전 상태 사이의 차이를 포함", loc="left", fontsize=9)
        ax.xaxis.set_major_locator(FixedLocator([50, 70, 100, 150, 200]))
        ax.yaxis.set_major_locator(FixedLocator([.02, .05, .1, .2, .5, 1]))
        ax.legend(loc="upper center", bbox_to_anchor=(.5, -.16), ncol=1, frameon=False, fontsize=7.5, scatterpoints=1)
        _clean(ax)
    fig.subplots_adjust(top=.80)
    fig.suptitle("센서 간 관계(기술 통계, 인과·고장 근거 아님)", x=.01, y=.99, ha="left", fontsize=11)
    return _save(fig, "fig_d2d_relations.png")


# ---------- (e) 저장 형식 누설 ----------
def format_leak(raw, text):
    cd = pd.read_csv(HERE / "class_differences.csv").set_index("feature")
    grid_ref = pd.read_csv(HERE / "current_grid.csv")
    dec = {k: text[k].AI0_Vibration.astype(str).str.strip().str.lstrip("-").str.split(".").str[1].fillna("").str.len() for k in text}
    assert int(dec["normal"].mode()[0]) == int(cd.loc["진동 저장 소수 자릿수(최빈)", "normal"])
    assert int(dec["abnormal"].mode()[0]) == int(cd.loc["진동 저장 소수 자릿수(최빈)", "abnormal"])
    g = 1.1920929
    rates = {}
    for k, f in raw.items():
        for name, fr in (("raw", f), ("matched", D.quantize(D.inputs_only(f), "matched"))):
            c = fr.AI2_Current.to_numpy(float)
            v = fr[D.SENSORS[:2]].to_numpy(float) * 1e6
            rates[(k, name)] = (float((np.abs(c / g - np.round(c / g)) < 1e-3).mean()), float((np.abs(v - np.round(v)) > 1e-3).any(axis=1).mean()))
    for k in raw:
        ref = float(grid_ref[(grid_ref.file == k) & (grid_ref.step_name == "상수 1.1920929")].share_tol_1e3.iloc[0])
        assert abs(rates[(k, "raw")][0] - ref) < 1e-12
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw=dict(width_ratios=[1, 1.3], wspace=.25))
    ax = axes[0]
    xs = np.arange(0, 11)
    for off, (k, color, label) in zip((-.18, .18), (("normal", NORMAL, "정상"), ("abnormal", ABNORMAL, "이상"))):
        share = dec[k].value_counts(normalize=True).reindex(xs, fill_value=0)
        ax.bar(xs + off, share.values, width=.34, color=color, label=f"{label}(최빈 {int(dec[k].mode()[0])}자리)")
    ax.set_xticks(xs); ax.set_xlabel("AI0 저장 소수 자릿수"); ax.set_ylabel("행 비율")
    ax.set_title(f"AI0 저장 소수 자릿수 분포(정상 {len(dec['normal']):,}행·이상 {len(dec['abnormal'])}행)", loc="left")
    ax.legend(frameon=False, loc="center left", bbox_to_anchor=(.66, .62), handlelength=1.2)
    _clean(ax)
    ax = axes[1]
    groups = [("전류 격자 일치\n(원값)", 0, "raw"), ("전류 격자 일치\n(matched)", 0, "matched"), ("진동 1e-6보다 세밀\n(원값)", 1, "raw"), ("진동 1e-6보다 세밀\n(matched)", 1, "matched")]
    for off, (k, color, label) in zip((-.18, .18), (("normal", NORMAL, "정상"), ("abnormal", ABNORMAL, "이상"))):
        vals = [rates[(k, pre)][i] for _, i, pre in groups]
        ax.bar(np.arange(4) + off, vals, width=.34, color=color, label=label)
        for x, v in zip(np.arange(4) + off, vals):
            ax.text(x, v + .02, f"{v:.1%}" if 0 < v < .01 else f"{v:.0%}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(range(4)); ax.set_xticklabels([g_[0] for g_ in groups], fontsize=8)
    ax.set_ylim(0, 1.15); ax.set_ylabel("규칙이 참인 행 비율")
    ax.set_title("형식 규칙 발화율: 원값에서는 파일(=라벨)을 가르고 matched 뒤에는 같아진다", loc="left", fontsize=9)
    ax.legend(frameon=False, loc="center right")
    _clean(ax)
    fig.subplots_adjust(top=.84)
    fig.suptitle("저장 형식 누설과 matched 양자화(진동 1e-4, 전류 격자 1.1920929 반올림을 두 클래스에 같게 적용)", x=.01, ha="left", fontsize=10.5)
    return _save(fig, "fig_d2e_format_leak.png")


def draw_all(raw, seg, t, st, mu=None, sd=None, fb=None, tables=None, text=None):
    tables = tables or {n: pd.read_csv(HERE / n) for n in ("sensor_relations.csv", "rolling_calibration_curve.csv", "operating_states.csv", "operating_states_summary.csv")}
    if text is None:
        text = {k: pd.read_csv(D.data_dir(BASE) / D.FILES[k], dtype=str, keep_default_na=False) for k in raw}
    return [timeline(raw, seg, t, tables), blocks(raw, seg), raw_examples(raw, seg, tables), relations(raw, st, fb, tables), format_leak(raw, text)]


def main():
    for stream in (sys.stdout, sys.stderr):     # 한국어 Windows(CP949) 콘솔에서 못 쓰는 기호는 바꿔 쓴다
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    import build_diagnostics as B
    normal, abnormal, _ = D.load(BASE)
    raw = {"normal": normal, "abnormal": abnormal}
    seg = {k: D.segments(f) for k, f in raw.items()}
    t = {k: pd.to_datetime(f.TimeStamp) for k, f in raw.items()}
    st = {k: B.segment_stats(raw[k], seg[k]) for k in raw}
    fb = B.frozen_false_alarms(normal, seg["normal"], "B")
    for p in draw_all(raw, seg, t, st, fb=fb):
        print(p.relative_to(YEJUN.parent))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    main()
