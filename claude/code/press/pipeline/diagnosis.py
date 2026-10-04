"""T4: 데이터 진단 보고서(diagnosis.md) + 그림 2장. 모든 수치는 원천 데이터·산출 CSV에서 계산한다(하드코딩 없음).

형식 누수·재양자화 결과는 05_requantize_audit.py 산출물(outputs/requantize/)을 읽는다. 없으면 해당 절을 건너뛴다.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from data import SENSORS, load  # noqa: E402
from scores import FREQS  # noqa: E402

from matplotlib import font_manager  # noqa: E402

plt.rcParams["font.family"] = [f for f in ("Malgun Gothic", "AppleGothic", "NanumGothic")
                               if f in {x.name for x in font_manager.fontManager.ttflist}] + ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _decimals(series):
    s = series.astype(str).str.lstrip("-")
    return s.str.split(".").str[1].fillna("").str.len()


def _sine_fit(x):
    t = np.arange(len(x)) * 0.1
    sst = ((x - x.mean()) ** 2).sum()
    best = (np.inf, None, None)
    for f in FREQS:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones_like(t)])
        c, *_ = np.linalg.lstsq(A, x, rcond=None)
        sse = ((x - A @ c) ** 2).sum()
        if sse < best[0]:
            best = (sse, f, A @ c)
    return best[1], 1 - best[0] / sst, best[2]


def run(out: Path, root, yj):
    normal, abnormal = load(root)
    raw_n = pd.read_csv(Path(root) / "data" / "3_소성가공_예지보전" / "press_data_normal.csv", dtype=str)
    raw_a = pd.read_csv(Path(root) / "data" / "3_소성가공_예지보전" / "outlier_data.csv", dtype=str)
    L = ["# 데이터 진단 (자동 생성)", ""]

    # 1. 구조
    bn, ba = yj.blocks(normal), yj.blocks(abnormal)
    ln = pd.Series(bn).value_counts()
    la = pd.Series(ba).value_counts().sort_index()
    tn = pd.to_datetime(normal.TimeStamp)
    ta = pd.to_datetime(abnormal.TimeStamp)
    dup = int(tn.duplicated().sum())
    L += ["## 1. 구조", "",
          "| 항목 | 정상 | 이상 |", "|---|---|---|",
          f"| 행 | {len(normal):,} | {len(abnormal):,} |",
          f"| 기간 | {tn.min():%m-%d %H:%M:%S} ~ {tn.max():%H:%M:%S} | {ta.min():%m-%d %H:%M:%S} ~ {ta.max():%H:%M:%S} |",
          f"| 기록구간(0.1초 아닌 간격에서 끊음) | {len(ln)} | {len(la)} |",
          f"| 구간 길이 최소/중앙/최대 | {ln.min()}/{int(ln.median())}/{ln.max()} | {la.min()}/{int(la.median())}/{la.max()} |",
          f"| 중복 타임스탬프 | {dup} | {int(ta.duplicated().sum())} |",
          f"| 결측 | {int(normal[SENSORS].isna().sum().sum())} | {int(abnormal[SENSORS].isna().sum().sum())} |",
          f"| `Equipment_state` | 전부 {normal.Equipment_state.unique().tolist()} | 전부 {abnormal.Equipment_state.unique().tolist()} |",
          "",
          f"- 10Hz라면 {len(normal):,}행은 {len(normal) / 10 / 60:.0f}분 분량인데 실제 기간은 "
          f"{(tn.max() - tn.min()).total_seconds() / 60:.0f}분 → 기록 공백이 많다. 연속 창은 기록구간 안에서만 만든다",
          "- 정상·이상이 서로 다른 하루씩이라 **날짜·운전조건 차이와 고장 차이를 분리할 수 없다**. 모든 성능은 제공 라벨 기준이다",
          ""]

    # 2. 형식 누수
    L += ["## 2. 저장 형식 차이 (지름길)", ""]
    fine = lambda s: float((np.abs(s * 1e6 - np.round(s * 1e6)) > 1e-3).mean())  # noqa: E731
    for name, col in (("상부 진동", "AI0_Vibration"), ("하부 진동", "AI1_Vibration")):
        dn, da = _decimals(raw_n[col]), _decimals(raw_a[col])
        L.append(f"- {name}: 저장 자릿수 최빈값 정상 {dn.mode()[0]}자리, 이상 {da.mode()[0]}자리 · "
                 f"1e-6보다 세밀한 값 비율 정상 {fine(normal[col]):.1%}, 이상 {fine(abnormal[col]):.1%}")
    q = 1.1920929
    on = lambda s: float((np.abs(s / q - np.round(s / q)) < 1e-3).mean())  # noqa: E731
    L.append(f"- 전류가 {q} 격자 위에 있는 비율: 정상 {on(normal.AI2_Current):.1%}, 이상 {on(abnormal.AI2_Current):.1%}")
    rq = out.parent / "requantize"
    if (rq / "shortcut_rules.csv").exists():
        sr = pd.read_csv(rq / "shortcut_rules.csv")
        pm = pd.read_csv(rq / "policy_metrics_by_variant.csv")
        raw_f1 = sr[sr.variant == "raw"].set_index("rule").f1
        mat_f1 = sr[sr.variant == "matched"].set_index("rule").f1
        piv = pm.pivot_table(index=["split", "model", "calibration_unit", "budget"], columns="variant", values="f1_all_rows")
        dmax = float((piv[["matched", "coarse"]].sub(piv.raw, axis=0)).abs().max().max())
        L += [f"- 형식만 보는 규칙의 F1: 전류 격자 {raw_f1['current_on_grid']:.3f}, 진동 자릿수 {raw_f1['vib_finer_than_1e-6']:.3f} "
              f"→ 두 날짜를 같은 양자화로 맞추면 {mat_f1['current_on_grid']:.3f}, {mat_f1['vib_finer_than_1e-6']:.3f}",
              f"- 재양자화 후 max-z·5NN·RMS 36설정 F1 최대 변화 {dmax:.3f} → 크기 기반 모델은 형식 지름길을 쓰지 않는다"]
    L += ["- 원자료 문자열·소수부를 읽는 모델은 이 지름길로 F1≈1을 낼 수 있다 → 비교 시 주의", ""]

    # 3. 전류 파형
    rows = []
    for lab, df, b in (("정상", normal, bn), ("이상", abnormal, ba)):
        for s in np.unique(b):
            x = df.AI2_Current.to_numpy(float)[b == s]
            if len(x) >= 10:
                f, r2, _ = _sine_fit(x)
                rows.append(dict(set=lab, f=f, r2=r2))
    sf = pd.DataFrame(rows)
    g = sf.groupby("set")
    L += ["## 3. 전류 파형 (10Hz로 찍힌 60Hz 교류)", "",
          "| | 구간 수(길이≥10) | 사인 R² 최소~최대 | 앨리어싱 주파수 중앙값(Hz) |", "|---|---|---|---|"]
    for lab in ("정상", "이상"):
        t = g.get_group(lab)
        L.append(f"| {lab} | {len(t)} | {t.r2.min():.3f} ~ {t.r2.max():.3f} | {t.f.median():.3f} |")
    L += ["", "- 정상 전류는 거의 완벽한 사인파, 이상 구간은 모두 사인파에서 벗어난다. 고장 때문인지 이상일 수집 설정 차이 때문인지는 분리 불가",
          "- 타임스탬프 간격은 두 파일 모두 명목 100ms라 실제 샘플링 간격으로 앨리어싱 주파수를 검증할 수 없다", ""]
    (out / "diagnosis.md").write_text("\n".join(L), encoding="utf-8")

    # 그림: 전류 파형 예시 (정상 1구간, 이상 2구간, 길이 50)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3), sharey=True)
    picks = [("정상", normal, bn, ln[ln == 50].index[0])]
    la50 = la[la == 50].index
    picks += [("이상", abnormal, ba, la50[0]), ("이상", abnormal, ba, la50[-1])]
    for ax, (lab, df, b, s) in zip(axes, picks):
        x = df.AI2_Current.to_numpy(float)[b == s]
        f, r2, fit = _sine_fit(x)
        ax.plot(np.arange(len(x)) * 0.1, x, "o", ms=3, label="측정")
        ax.plot(np.arange(len(x)) * 0.1, fit, "-", lw=1, label="사인 피팅")
        ax.set_title(f"{lab} 구간 {s}: R²={r2:.3f}", fontsize=10)
        ax.set_xlabel("구간 내 시간(초)")
    axes[0].set_ylabel("전류 AI2")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_current_waveform.png", dpi=150)
    plt.close(fig)

    # 그림: 구간 길이 분포
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.hist(ln.values, bins=range(0, 52, 2), alpha=.7, label="정상", density=True)
    ax.hist(la.values, bins=range(0, 52, 2), alpha=.7, label="이상", density=True)
    ax.set_xlabel("기록구간 길이(관측 수)")
    ax.set_ylabel("밀도")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "fig_segment_length.png", dpi=150)
    plt.close(fig)
