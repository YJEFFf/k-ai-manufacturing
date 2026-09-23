"""용접 물리 특징 + 경험적 용접 로브(운전 창) 분석.

01_diagnose_welding.py 결과(rows_flagged.csv)를 입력으로 쓴다.

    python code/01_diagnose_welding.py   # 먼저 한 번
    python code/02_physics_lobe.py

하는 일
    1. 건별 물리 특징: 입열량 E=V·I·t, 전력 P=V·I, 동저항 R=V/I, I²t, 직전 용접 대비 변화량
    2. 물리 정합성 검사: 가압력↑→접촉저항↓ 등 교과서 관계가 데이터에서 성립하는지
    3. 전류 스테퍼(전극 마모 보정) 단계 탐지 — 연속성이 보장되는 원본 구간에서만
    4. 경험적 용접 로브: 원본·정상 가압력 구간을 기준으로 운전 창과 로버스트 마할라노비스 거리
    5. 방향성 위험 점수(가설): 입열 부족→용접부족, 가압·입열 과다→파임, 급변→크랙
    6. 일별 집계와 실제 일별 불량 수(유형별) 비교 — 표본 8일이라 기술통계로만

산출물 (code/outputs/physics/)
    features.csv, physics_report.md, summary.json, fig_lobe.png, fig_energy_force.png, fig_stepper.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wlib import add_features, mahal2, md_table, robust_cov, robust_z

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "code" / "outputs" / "diagnosis" / "rows_flagged.csv"
RESULT_XLSX = ROOT / "data" / "2_용접기" / "Welding Data Set_01.xlsx"
OUT = ROOT / "code" / "outputs" / "physics"

LOBE_QUANTILE = 0.99  # 기준 집합 마할라노비스² 분포의 경험적 분위수. 통전시간이 정수(70~73ms)라 정규분포 가정(카이제곱)이 맞지 않는다
STEP_WINDOW = 25  # 스테퍼 탐지용 이동 중앙값 창(용접 수)
STEP_MIN_KA = 0.08  # 이 이상 전류 수준이 바뀌면 스테퍼 단계로 본다
DEFECT_NAMES = {1: "파임", 2: "용접부족", 3: "크랙"}


def detect_stepper(df: pd.DataFrame) -> pd.DataFrame:
    """원본(비복사) 연속 구간에서 전류 이동 중앙값의 계단 변화를 찾는다.

    up   = 스테퍼가 전류를 올린 지점(전극 마모 보정)
    down = 전류가 한 번에 떨어진 지점 → 전극 팁 드레싱으로 리셋된 후보
    방향별로 따로 중복을 제거해, 올라간 직후의 리셋도 놓치지 않는다.
    """
    events = []
    orig = df[~df["is_copy"]]
    for day, g in orig.groupby("day", sort=False):
        g = g.reset_index()
        rm = g["current"].rolling(STEP_WINDOW, center=True, min_periods=STEP_WINDOW // 2).median()
        jump = rm.shift(-STEP_WINDOW // 2) - rm.shift(STEP_WINDOW // 2)
        for direction, cand in (("up", jump[jump >= STEP_MIN_KA]), ("down", jump[jump <= -STEP_MIN_KA])):
            last = -10**9
            for i, v in cand.items():
                if i - last > STEP_WINDOW:
                    pos = int(i + (cand.loc[i:i + STEP_WINDOW].abs().idxmax() - i))  # 창 안에서 변화가 가장 큰 지점
                    events.append({"day": day, "pos_in_day": pos, "idx": int(g.at[pos, "idx"]), "row": int(g.at[pos, "index"]),
                                   "level_before_kA": round(float(rm.iloc[max(pos - STEP_WINDOW, 0)]), 3),
                                   "level_after_kA": round(float(rm.iloc[min(pos + STEP_WINDOW, len(rm) - 1)]), 3),
                                   "direction": direction})
                    last = i
    ev = pd.DataFrame(events)
    return ev.sort_values(["row"]).reset_index(drop=True) if len(ev) else ev


def welds_since_reset(df: pd.DataFrame, steps: pd.DataFrame) -> pd.Series:
    """원본 행에 대해 마지막 리셋(down) 이후 용접 수. 복사 행과 리셋 전 구간은 NaN."""
    out = pd.Series(np.nan, index=df.index)
    if steps.empty:
        return out
    for day, g in df[~df["is_copy"]].groupby("day", sort=False):
        resets = sorted(steps.loc[(steps["day"] == day) & (steps["direction"] == "down"), "row"])
        rows = g.index.to_numpy()
        for k, r0 in enumerate(resets):
            r1 = resets[k + 1] if k + 1 < len(resets) else rows.max() + 1
            seg = rows[(rows >= r0) & (rows < r1)]
            out.loc[seg] = np.arange(len(seg))
    return out


def main():
    if not DIAG.exists():
        raise SystemExit("먼저 python code/01_diagnose_welding.py 를 실행하세요.")
    OUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(DIAG, encoding="utf-8-sig")
    df = add_features(raw)
    s: dict = {}

    # 기준 집합: 원본 행 + 정상 가압력. 복사 행은 같은 상태를 여러 번 세게 되므로 기준에서 뺀다
    ref_mask = (~df["is_copy"]) & (~df["high_force_block"])
    ref = df[ref_mask]
    s["reference_rows"] = int(ref_mask.sum())

    # 1) 물리 특징 요약
    feats = ["energy_J", "power_kW", "resistance_uohm", "i2t", "force", "current", "voltage", "weld_time"]
    s["feature_summary_reference"] = ref[feats].describe().round(4).to_dict()

    # 2) 물리 정합성 검사 (원본 행 기준)
    orig = df[~df["is_copy"]]
    sp = lambda a, b: round(float(orig[a].corr(orig[b], method="spearman")), 3)
    hb = orig[orig["high_force_block"]]
    checks = [
        {"check": "가압력↑ → 접촉저항(R)↓", "expected": "음(-)", "observed": sp("force", "resistance_uohm")},
        {"check": "통전시간↑ → 입열량↑", "expected": "양(+)", "observed": sp("weld_time", "energy_J")},
        {"check": "전류↑ → 입열량↑", "expected": "양(+)", "observed": sp("current", "energy_J")},
        {"check": "전압 변동계수(CV)", "expected": "저항 변화에 따라 변동", "observed": round(float(ref["voltage"].std() / ref["voltage"].mean()), 5)},
        {"check": "고가압력 블록의 R 중앙값 − 정상 R 중앙값 (µΩ)", "expected": "음(-): 가압력 3배면 R 감소",
         "observed": round(float(hb["resistance_uohm"].median() - ref["resistance_uohm"].median()), 3) if len(hb) else None},
    ]
    for c in checks:
        exp_sign = {"음(-)": -1, "양(+)": 1}.get(c["expected"].split(":")[0])
        c["consistent"] = None if exp_sign is None or c["observed"] is None else bool(np.sign(c["observed"]) == exp_sign)
    s["physics_checks"] = checks

    # 3) 스테퍼
    steps = detect_stepper(df)
    wsr = welds_since_reset(df, steps)
    df["welds_since_reset"] = df["source_row"].map(wsr)  # 복제 행은 자기 원본 행의 값을 물려받는다
    s["stepper_events"] = steps.to_dict("records")
    downs = steps[steps["direction"] == "down"] if len(steps) else steps
    s["reset_cycle_lengths"] = {d: np.diff(sorted(g["row"])).tolist() for d, g in downs.groupby("day")} if len(downs) else {}

    # 4) 경험적 로브: 운전 창(분위수) + 로버스트 마할라노비스 [E, R, force]
    lo, hi = ref[["current", "weld_time", "energy_J", "force"]].quantile(0.005), ref[["current", "weld_time", "energy_J", "force"]].quantile(0.995)
    s["operating_window_0.5_99.5"] = {c: [round(float(lo[c]), 4), round(float(hi[c]), 4)] for c in lo.index}
    df["outside_window"] = False
    for c in lo.index:
        df["outside_window"] |= ~df[c].between(lo[c], hi[c])
    X_cols = ["energy_J", "resistance_uohm", "force"]
    mu, cov = robust_cov(ref[X_cols].to_numpy())
    df["mahal2"] = mahal2(df[X_cols].to_numpy(), mu, cov)
    lobe_thr = float(np.quantile(df.loc[ref_mask, "mahal2"], LOBE_QUANTILE))
    df["outside_lobe"] = df["mahal2"] > lobe_thr
    s["lobe_threshold_mahal2"] = round(lobe_thr, 3)
    s["lobe_center"] = dict(zip(X_cols, np.round(mu, 3).tolist()))
    s["outside_lobe_rows"] = int(df["outside_lobe"].sum())
    s["outside_lobe_by_group"] = {
        "reference(원본·정상가압)": int(df.loc[ref_mask, "outside_lobe"].sum()),
        "high_force_block": int(df.loc[df["high_force_block"], "outside_lobe"].sum()),
        "copied_normal": int(df.loc[df["is_copy"] & ~df["high_force_block"], "outside_lobe"].sum()),
    }

    # 5) 방향성 위험 점수 (가설 — 라벨로 검증된 것이 아님)
    zE = robust_z(df["energy_J"], ref["energy_J"])
    zF = robust_z(df["force"], ref["force"])
    zdI = robust_z(df["d_current"].abs(), ref["d_current"].abs().dropna())
    zdR = robust_z(df["d_resistance_uohm"].abs(), ref["d_resistance_uohm"].abs().dropna())
    df["risk_cold"] = (-zE).clip(lower=0)  # 입열 부족 → 용접부족(2)
    df["risk_indent"] = zF.clip(lower=0) + 0.5 * zE.clip(lower=0)  # 가압·입열 과다 → 파임(1)
    df["risk_unstable"] = (zdI.fillna(0).clip(lower=0) + zdR.fillna(0).clip(lower=0)) / 2  # 급변 → 크랙(3)
    df.loc[df["copy_boundary"], "risk_unstable"] = np.nan  # 복사 경계의 변화량은 인공적이므로 제외

    # 6) 일별 집계 vs 실제 불량
    res = pd.ExcelFile(RESULT_XLSX).parse("result").iloc[:, :6]
    res.columns = ["result_idx", "machine", "item", "day", "defect", "defect_type"]
    res["day"] = pd.to_datetime(res["day"]).dt.strftime("%Y-%m-%d")
    lab = res.pivot_table(index="day", columns="defect_type", values="defect", aggfunc="sum")
    lab.columns = [f"defect_{DEFECT_NAMES[c]}" for c in lab.columns]
    lab["defect_total"] = lab.sum(axis=1)
    daily = df.groupby("day").agg(
        n=("idx", "size"),
        outside_lobe=("outside_lobe", "sum"),
        outside_window=("outside_window", "sum"),
        risk_cold_p99=("risk_cold", lambda x: x.quantile(0.99)),
        risk_indent_p99=("risk_indent", lambda x: x.quantile(0.99)),
        risk_unstable_p99=("risk_unstable", lambda x: x.quantile(0.99)),
        energy_mean=("energy_J", "mean"),
    ).join(lab, how="left")
    pairs = [("risk_cold_p99", "defect_용접부족"), ("risk_indent_p99", "defect_파임"),
             ("risk_unstable_p99", "defect_크랙"), ("outside_lobe", "defect_total"), ("energy_mean", "defect_total")]
    labd = daily.dropna(subset=["defect_total"])
    s["daily_spearman"] = {f"{a} ~ {b}": round(float(labd[a].corr(labd[b], method="spearman")), 3) for a, b in pairs}

    # 출력
    df.to_csv(OUT / "features.csv", index=False, encoding="utf-8-sig")
    daily.round(4).to_csv(OUT / "daily_physics.csv", encoding="utf-8-sig")
    steps.to_csv(OUT / "stepper_events.csv", index=False, encoding="utf-8-sig")
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    plot_all(df, ref_mask, lo, hi, steps)
    write_report(s, daily, steps)
    print(f"done -> {OUT}")
    for c in checks:
        print(f"  [{'OK' if c['consistent'] else ('--' if c['consistent'] is None else 'X ')}] {c['check']}: {c['observed']} (기대 {c['expected']})")
    print(f"  stepper events: {len(steps)}, outside lobe: {s['outside_lobe_by_group']}")


def plot_all(df, ref_mask, lo, hi, steps):
    rng = np.random.default_rng(0)
    # 로브: 전류 × 통전시간
    fig, ax = plt.subplots(figsize=(8, 6))
    jit = rng.uniform(-0.25, 0.25, len(df))
    for mask, color, label in [(df["is_copy"] & ~df["high_force_block"], "#bbbbbb", "copied rows"),
                               (ref_mask, "#2c7fb8", "reference (original, normal force)"),
                               (df["high_force_block"], "#d7301f", "high-force block")]:
        ax.scatter(df.loc[mask, "current"], df.loc[mask, "weld_time"] + jit[mask.to_numpy()], s=4, alpha=0.5, c=color, label=label)
    ax.add_patch(plt.Rectangle((lo["current"], lo["weld_time"]), hi["current"] - lo["current"], hi["weld_time"] - lo["weld_time"],
                               fill=False, ec="k", lw=1.2, ls="--", label="operating window (0.5–99.5%)"))
    ax.set_xlabel("weld current (kA)")
    ax.set_ylabel("weld time (ms, jittered)")
    ax.set_title("Empirical weld lobe — current × weld time")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "fig_lobe.png", dpi=130)
    plt.close(fig)

    # 입열량 × 가압력 + 저항 정합성
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    orig = ~df["is_copy"]
    sc = axes[0].scatter(df.loc[orig, "force"], df.loc[orig, "energy_J"], c=np.log1p(df.loc[orig, "mahal2"]), s=5, cmap="viridis")
    fig.colorbar(sc, ax=axes[0], label="log(1 + Mahalanobis²)")
    axes[0].set_xlabel("weld force (bar)")
    axes[0].set_ylabel("heat input E = V·I·t (J)")
    axes[0].set_title("Heat input vs force (original rows)")
    axes[1].scatter(df.loc[orig & ~df["high_force_block"], "force"], df.loc[orig & ~df["high_force_block"], "resistance_uohm"], s=4, c="#2c7fb8", label="normal force")
    axes[1].scatter(df.loc[orig & df["high_force_block"], "force"], df.loc[orig & df["high_force_block"], "resistance_uohm"], s=4, c="#d7301f", label="high-force block")
    axes[1].set_xlabel("weld force (bar)")
    axes[1].set_ylabel("dynamic resistance R = V/I (µΩ)")
    axes[1].set_title("Physics check: force↑ should lower contact resistance")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_energy_force.png", dpi=130)
    plt.close(fig)

    # 스테퍼
    orig_days = df.loc[~df["is_copy"], "day"].unique()
    fig, axes = plt.subplots(len(orig_days), 1, figsize=(13, 3.2 * len(orig_days)), squeeze=False)
    for ax, d in zip(axes[:, 0], orig_days):
        g = df[(df["day"] == d) & ~df["is_copy"]].reset_index(drop=True)
        ax.plot(g.index, g["current"], lw=0.5, c="#555")
        ax.plot(g.index, g["current"].rolling(STEP_WINDOW, center=True, min_periods=5).median(), lw=1.5, c="#2c7fb8")
        for _, e in steps[steps["day"] == d].iterrows():
            ax.axvline(e["pos_in_day"], c="#d7301f" if e["direction"] == "down" else "#31a354", ls="--", lw=1)
        ax.set_title(f"{d} (original rows) — current; green = stepper up, red = reset (tip dressing candidate)")
        ax.set_ylabel("current (kA)")
    axes[-1, 0].set_xlabel("weld order within day (file order)")
    fig.tight_layout()
    fig.savefig(OUT / "fig_stepper.png", dpi=130)
    plt.close(fig)


def write_report(s, daily, steps):
    ref = s["feature_summary_reference"]
    checks = pd.DataFrame(s["physics_checks"])
    checks["consistent"] = checks["consistent"].map({True: "✅ 성립", False: "❌ 불일치", None: "—"})
    win = s["operating_window_0.5_99.5"]
    lines = [
        "# 용접 물리 특징 · 경험적 로브 분석",
        "",
        "> `code/02_physics_lobe.py` 자동 생성. 기준 집합 = 원본(비복사) 행 중 정상 가압력 구간 "
        f"{s['reference_rows']:,}행.",
        "",
        "## 1. 물리 특징의 크기 (기준 집합 중앙값)",
        "",
        "| 특징 | 식 | 중앙값 | 비고 |",
        "|---|---|---|---|",
        f"| 입열량 E | V·I·t | {ref['energy_J']['50%']:.0f} J | 박판 스폿용접 수 kJ 수준으로 현실적 |",
        f"| 동저항 R | V/I | {ref['resistance_uohm']['50%']:.1f} µΩ | 수백 µΩ 이하로 현실적 |",
        f"| 전력 P | V·I | {ref['power_kW']['50%']:.1f} kW | |",
        f"| I²t | I²·t | {ref['i2t']['50%']:.0f} kA²·ms | 로브의 표준 축 |",
        "",
        "## 2. 물리 정합성 검사",
        "",
        md_table(checks[["check", "expected", "observed", "consistent"]]),
        "",
        "- 전압 변동계수가 매우 작다 → 전압이 사실상 고정이라 R은 전류의 역수에 가깝다. R을 독립 정보로 과대해석하지 않는다.",
        "- 가압력이 3배 넘게 높은 블록에서 R이 내려가지 않으면, 이 '가압력' 값이 전극 가압력이 아니거나(공압 실린더 압력 등) 블록이 실측이 아닐 가능성을 시사한다 → 진단 D2와 함께 보고.",
        "",
        "## 3. 전류 스테퍼(전극 마모 보정) 단계",
        "",
        md_table(steps) if len(steps) else "(탐지된 단계 없음)",
        "",
        "- up = 스테퍼 전류 증가(전극 마모 보정), down = 한 번에 떨어진 리셋 → 전극 팁 드레싱 후보.",
        f"- 리셋 사이 용접 수(드레싱 주기 후보): {s['reset_cycle_lengths']}",
        "- 원본 구간에서만 탐지. 복사 구간에서 보이는 전류 톱니 모양은 원본 구간을 이어 붙인 흔적이라 따로 해석하지 않는다.",
        "- `welds_since_reset`(리셋 후 용접 수)은 전극 마모 대용 특징으로 features.csv에 들어 있다. 복제 행은 `source_row`로 원본 값을 물려받는다.",
        "",
        "## 4. 경험적 용접 로브 (운전 창)",
        "",
        "| 변수 | 0.5% | 99.5% |",
        "|---|---|---|",
        *[f"| {k} | {v[0]} | {v[1]} |" for k, v in win.items()],
        "",
        f"로버스트 마할라노비스(입열량·동저항·가압력, 기준 집합 경험적 99% 경계 d²={s['lobe_threshold_mahal2']}) 밖: 전체 {s['outside_lobe_rows']:,}행 — "
        + ", ".join(f"{k} {v:,}" for k, v in s["outside_lobe_by_group"].items()),
        "",
        "- 문헌상 로브(너겟 형성 ~ 날림 사이 창)는 품질 라벨로 그리는 것이다. 이 데이터에는 건별 라벨이 없어 **관측된 안정 운전 창**으로 대신한다. 과제문의 '안정 공정조건 범위' 제안은 이 창을 근거로 하되 인과가 아닌 관측 기반임을 명시한다.",
        "",
        "## 5. 방향성 위험 점수 (가설)",
        "",
        "| 점수 | 정의 | 대응 가설 |",
        "|---|---|---|",
        "| risk_cold | 입열량이 기준보다 낮은 정도(로버스트 z) | 용접부족 |",
        "| risk_indent | 가압력 초과 + 0.5 × 입열 초과 | 파임 |",
        "| risk_unstable | 직전 용접 대비 전류·저항 급변 (복사 경계 제외) | 크랙 |",
        "",
        "## 6. 일별 집계 vs 실제 불량 (라벨 8일, 기술통계)",
        "",
        "| 비교 | 순위상관 |",
        "|---|---|",
        *[f"| {k} | {v:+.3f} |" for k, v in s["daily_spearman"].items()],
        "",
        md_table(daily.round(3).reset_index()),
        "",
        "- n=8이라 |ρ|<0.74는 5% 유의수준에서 우연과 구분되지 않는다. 날짜 간 센서 구간이 복제돼 있어 일별 비교 자체가 약하다(진단 D1). 위험 점수의 성능 검증은 다음 단계의 가상 불량 주입 벤치마크로 한다.",
    ]
    (OUT / "physics_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
