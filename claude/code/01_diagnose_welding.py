"""용접기 AI 데이터셋 진단 스크립트.

한 번 실행하면 데이터 진단 결과(D1~D10)를 재현해 outputs/diagnosis/ 에 쓴다.

    python code/01_diagnose_welding.py

산출물
    diagnosis_report.md    진단 보고서 (보고서 '데이터 이해 및 진단' 절의 근거)
    summary.json           핵심 수치
    rows_flagged.csv       행별 플래그 (복사 여부, 고가압력 블록, 범위 이탈 등) — 이후 모델링 입력
    copy_segments.csv      복사 구간 목록 (어디가 어디를 복사했는지)
    daily_table.csv        일별 센서 통계 + 불량 집계
    fig_timeline.png       날짜별 센서 시계열 + 복사 구간 표시
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "2_용접기"
OUT = ROOT / "code" / "outputs" / "diagnosis"

SENSORS = ["force", "current", "voltage", "weld_time"]
RAW_COLS = ["idx", "machine", "item", "day", "thick1", "thick2", *SENSORS]
WINDOW = 27  # 복사 탐지 창 길이. 통전시간 소수값이 27행 단위로 나타나는 데서 착안
HIGH_FORCE = 5.0  # bar. 정상 운전 중앙값(2.34)의 2배 이상


def load():
    xls = pd.ExcelFile(DATA / "Welding Data Set_01.xlsx")
    raw = xls.parse("Raw data")
    raw.columns = RAW_COLS
    raw["day"] = pd.to_datetime(raw["day"]).dt.date
    raw["row"] = np.arange(len(raw))

    res = xls.parse("result")
    res = res.iloc[:, :6]
    res.columns = ["result_idx", "machine", "item", "day", "defect", "defect_type"]
    res["day"] = pd.to_datetime(res["day"]).dt.date

    spec = xls.parse("data set").dropna(how="all").iloc[:, :3]
    spec.columns = ["column", "desc", "range"]

    scaled = pd.read_csv(DATA / "scaled_data.csv", encoding="cp949")
    scaled.columns = ["row", *SENSORS]
    return raw, res, spec, scaled


def parse_range(text):
    for sep in ("~", "-"):
        if isinstance(text, str) and sep in text and text.strip() != "-":
            lo, hi = text.split(sep)
            return float(lo), float(hi)
    return None


def find_copies(raw: pd.DataFrame, window: int):
    """같은 날짜 안의 연속 window 행을 해시해, 앞서 나온 창과 똑같은 창을 '복사'로 표시한다."""
    tokens = list(raw[SENSORS].round(4).itertuples(index=False, name=None))
    days = raw["day"].tolist()
    first_seen: dict[tuple, int] = {}
    occurrences = defaultdict(int)
    copy_of = np.full(len(raw), -1)  # 복사 창의 시작 행 -> 원본 창의 시작 행
    for i in range(len(raw) - window + 1):
        if days[i] != days[i + window - 1]:
            continue
        gram = tuple(tokens[i : i + window])
        occurrences[gram] += 1
        if gram in first_seen:
            copy_of[i] = first_seen[gram]
        else:
            first_seen[gram] = i

    is_copy = np.zeros(len(raw), bool)  # 앞선 창을 그대로 반복한 행
    in_repeated = np.zeros(len(raw), bool)  # 2번 이상 등장하는 창에 속한 행(원본 포함)
    source = np.arange(len(raw))  # 행 -> 이 행이 복제해 온 원본 행 (원본은 자기 자신)
    for i in range(len(raw) - window + 1):
        if copy_of[i] >= 0:
            is_copy[i : i + window] = True
            for k in range(window):
                if source[i + k] == i + k:  # 처음 배정된 원본을 유지
                    source[i + k] = copy_of[i] + k
    # 원본 창의 행이 다시 복제본인 경우가 있어 사슬을 끝까지 따라간다
    for _ in range(50):
        nxt = source[source]
        if np.array_equal(nxt, source):
            break
        source = nxt
    for gram, start in first_seen.items():
        if occurrences[gram] > 1:
            in_repeated[start : start + window] = True
    in_repeated |= is_copy

    # 연속된 복사 창을 구간으로 묶는다
    segments = []
    i = 0
    n = len(raw)
    while i < n - window + 1:
        if copy_of[i] < 0:
            i += 1
            continue
        start, src = i, copy_of[i]
        while i + 1 < n - window + 1 and copy_of[i + 1] >= 0 and copy_of[i + 1] == copy_of[i] + 1:
            i += 1
        end = i + window - 1
        segments.append(
            {
                "day": raw.at[start, "day"],
                "start_row": start,
                "end_row": end,
                "start_idx": int(raw.at[start, "idx"]),
                "end_idx": int(raw.at[end, "idx"]),
                "length": end - start + 1,
                "source_day": raw.at[src, "day"],
                "source_start_idx": int(raw.at[src, "idx"]),
            }
        )
        i += 1
    return is_copy, in_repeated, pd.DataFrame(segments), source


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw, res, spec, scaled = load()
    s: dict = {"n_rows": len(raw)}
    findings: list[str] = []

    # D4. 라벨 구조
    defects_by_day = res.pivot_table(index="day", columns="defect_type", values="defect", aggfunc="sum").fillna(0)
    defects_by_day.columns = [f"defect_type{c}" for c in defects_by_day.columns]
    defects_by_day["defects"] = defects_by_day.sum(axis=1)
    raw_days = sorted(raw["day"].unique())
    label_days = sorted(res["day"].unique())
    s["label_rows"] = len(res)
    s["defects_total"] = int(res["defect"].sum())
    s["days_raw"] = len(raw_days)
    s["days_labeled"] = len(label_days)
    s["days_without_label"] = [str(d) for d in raw_days if d not in label_days]
    s["result_idx_is_row_number"] = bool((res["result_idx"] == np.arange(1, len(res) + 1)).all())

    # D6. 날짜별 순번 무결성
    idx_issues = []
    for d, g in raw.groupby("day"):
        dup = int(g["idx"].duplicated().sum())
        srt = g["idx"].sort_values()
        gaps = [(int(a), int(b)) for a, b in zip(srt[:-1], srt[1:]) if b - a > 1]
        if dup or gaps or srt.iloc[0] != 1:
            idx_issues.append({"day": str(d), "n": len(g), "idx_max": int(srt.iloc[-1]), "dup": dup, "gaps": gaps})
    s["idx_issues"] = idx_issues

    # D7. 고정 변수
    s["constant_columns"] = {c: raw[c].iloc[0] for c in ["machine", "item", "thick1", "thick2"] if raw[c].nunique() == 1}
    s["constant_columns"] = {k: (float(v) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in s["constant_columns"].items()}

    # D10. 수집 범위(data set 시트) 대비 이탈
    col_map = dict(zip(["Thickness 1(mm)", "Thickness 2(mm)", "weld force(bar)", "weld current(kA)", "weld Voltage(v)", "weld time(ms)"],
                       ["thick1", "thick2", *SENSORS]))
    out_of_range = {}
    raw["out_of_spec"] = False
    for _, r in spec.iterrows():
        rng = parse_range(r["range"])
        col = col_map.get(str(r["column"]).strip())
        if rng and col:
            bad = ~raw[col].between(*rng)
            raw["out_of_spec"] |= bad
            out_of_range[col] = {"range": rng, "n_out": int(bad.sum()), "min": float(raw[col].min()), "max": float(raw[col].max())}
    s["out_of_spec"] = out_of_range

    # D1. 블록 복사
    is_copy, in_repeated, segments, source = find_copies(raw, WINDOW)
    raw["is_copy"] = is_copy
    raw["source_row"] = source
    raw["row"] = np.arange(len(raw))
    raw["in_repeated_block"] = in_repeated
    s["window"] = WINDOW
    s["unique_sensor_tuples"] = int(raw[SENSORS].round(4).drop_duplicates().shape[0])
    s["rows_in_repeated_block"] = int(in_repeated.sum())
    s["rows_copy_of_earlier"] = int(is_copy.sum())
    s["rows_original_estimate"] = int((~is_copy).sum())
    s["copy_segments"] = len(segments)
    s["original_rows_per_day"] = {str(d): int((~g["is_copy"]).sum()) for d, g in raw.groupby("day")}
    s["days_fully_copied"] = [d for d, v in s["original_rows_per_day"].items() if v == 0]
    sens = {}
    for w in (9, 27, 54, 81):
        c, r_, _, _ = find_copies(raw, w)
        sens[w] = {"copy_of_earlier": round(float(c.mean()), 4), "in_repeated": round(float(r_.mean()), 4)}
    s["window_sensitivity"] = sens

    # D2. 고가압력 블록
    hf = raw[raw["force"] > HIGH_FORCE]
    raw["high_force_block"] = raw["force"] > HIGH_FORCE
    blocks = {d: g[SENSORS].reset_index(drop=True) for d, g in hf.groupby("day")}
    base_day = next(iter(blocks)) if blocks else None
    s["high_force"] = {
        "threshold_bar": HIGH_FORCE,
        "rows_per_day": {str(d): len(b) for d, b in blocks.items()},
        "identical_across_days": all(blocks[base_day].equals(b) for b in blocks.values()) if blocks else None,
        "idx_span": {str(d): [int(g["idx"].min()), int(g["idx"].max())] for d, g in hf.groupby("day")},
        "force_range": [float(hf["force"].min()), float(hf["force"].max())] if len(hf) else None,
        "normal_force_median": float(raw.loc[raw["force"] <= HIGH_FORCE, "force"].median()),
    }

    # D3. 통전시간 소수값
    frac = raw["weld_time"] % 1 != 0
    raw["fractional_weld_time"] = frac
    s["fractional_weld_time"] = {"rows": int(frac.sum()), "per_day": {str(d): int(v) for d, v in raw[frac].groupby("day").size().items()},
                                 "values": sorted(map(float, raw.loc[frac, "weld_time"].unique()))}

    # D8. scaled_data.csv 와 Raw 의 관계
    rel = {}
    for c in SENSORS:
        ok = scaled[c].notna()
        rowwise = float(np.corrcoef(raw.loc[ok, c], scaled.loc[ok, c])[0, 1])
        a = np.sort(raw.loc[ok, c].to_numpy())
        b = np.sort(scaled.loc[ok, c].to_numpy())
        sorted_r = float(np.corrcoef(a, b)[0, 1])
        rel[c] = {"rowwise_corr": round(rowwise, 4), "sorted_value_corr": round(sorted_r, 4), "nulls": int((~ok).sum())}
    s["scaled_vs_raw"] = rel

    # D9. 일별 센서 통계와 불량 수
    daily = raw.groupby("day").agg(n=("idx", "size"), **{f"{c}_mean": (c, "mean") for c in SENSORS},
                                   **{f"{c}_std": (c, "std") for c in SENSORS},
                                   copy_share=("is_copy", "mean"), high_force_rows=("high_force_block", "sum"))
    daily = daily.join(defects_by_day, how="left")
    daily["defect_rate"] = daily["defects"] / daily["n"]
    lab = daily.dropna(subset=["defects"])
    corr = {c: round(float(lab[c].corr(lab["defects"], method="spearman")), 3)
            for c in daily.columns if c not in defects_by_day.columns and c != "defect_rate"}
    s["daily_spearman_vs_defects"] = corr
    s["high_force_days_defects"] = {str(d): (None if pd.isna(v) else float(v)) for d, v in daily.loc[daily["high_force_rows"] > 0, "defects"].items()}

    # ---------- 파일 출력 ----------
    raw.to_csv(OUT / "rows_flagged.csv", index=False, encoding="utf-8-sig")
    segments.to_csv(OUT / "copy_segments.csv", index=False, encoding="utf-8-sig")
    daily.round(5).to_csv(OUT / "daily_table.csv", encoding="utf-8-sig")
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    plot_timeline(raw)
    write_report(s, daily, segments)
    print(f"done -> {OUT}")
    for k in ["n_rows", "unique_sensor_tuples", "rows_in_repeated_block", "rows_copy_of_earlier", "copy_segments", "defects_total"]:
        print(f"  {k}: {s[k]}")


def plot_timeline(raw):
    days = sorted(raw["day"].unique())
    fig, axes = plt.subplots(len(SENSORS), 1, figsize=(16, 9), sharex=True)
    x = np.arange(len(raw))
    for ax, c in zip(axes, SENSORS):
        ax.plot(x, raw[c], lw=0.4, color="#333")
        ax.fill_between(x, raw[c].min(), raw[c].max(), where=raw["is_copy"], color="#e8a33d", alpha=0.25, step="mid", lw=0)
        ax.fill_between(x, raw[c].min(), raw[c].max(), where=raw["high_force_block"], color="#c0392b", alpha=0.35, step="mid", lw=0)
        ax.set_ylabel(c)
        for d in days:
            ax.axvline(raw.index[raw["day"] == d][0], color="#888", lw=0.6, ls=":")
    for d in days:
        axes[0].text(raw.index[raw["day"] == d][0] + 10, axes[0].get_ylim()[1], str(d)[5:], va="bottom", fontsize=8)
    axes[-1].set_xlabel("row (production order)")
    fig.suptitle(f"Welding raw data — orange: repeats an earlier {WINDOW}-row window, red: force > {HIGH_FORCE} bar block", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "fig_timeline.png", dpi=130)
    plt.close(fig)


def md_table(df: pd.DataFrame) -> str:
    """tabulate 없이 마크다운 표를 만든다."""
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def write_report(s, daily, segments):
    hf = s["high_force"]
    ft = s["fractional_weld_time"]
    lines = [
        "# 용접기 AI 데이터셋 진단 결과",
        "",
        "> `code/01_diagnose_welding.py` 실행 결과로 자동 생성. 수치를 손으로 고치지 말 것.",
        "",
        "## 핵심",
        "",
        f"**원본으로 볼 수 있는 행은 {s['rows_original_estimate']:,}개({s['rows_original_estimate']/s['n_rows']:.1%})뿐이다.** "
        + ", ".join(f"{d} {v:,}행" for d, v in s["original_rows_per_day"].items() if v)
        + f". 나머지 {len(s['days_fully_copied'])}일({', '.join(d[5:] for d in s['days_fully_copied'])})은 전부 앞선 구간을 이어 붙인 것이다"
        f" (창 {s['window']}행 기준, `fig_timeline.png` 주황 구간).",
        "",
        "## 요약",
        "",
        "| # | 진단 | 결과 |",
        "|---|---|---|",
        f"| D1 | 블록 복사 | {s['n_rows']:,}행 중 {s['rows_in_repeated_block']:,}행({s['rows_in_repeated_block']/s['n_rows']:.1%})이 2번 이상 등장하는 {s['window']}행 창에 속함. 앞선 창을 그대로 반복한 행 {s['rows_copy_of_earlier']:,}개, 복사 구간 {s['copy_segments']}개. 고유 센서 조합 {s['unique_sensor_tuples']:,}개 |",
        f"| D2 | 고가압력 블록 | 가압력 >{hf['threshold_bar']}bar 행이 {', '.join(f'{d} {n}행' for d, n in hf['rows_per_day'].items())}. 날짜 간 값·순서 완전 동일: **{hf['identical_across_days']}** (정상 중앙값 {hf['normal_force_median']:.2f}bar) |",
        f"| D3 | 통전시간 소수값 | {ft['rows']}행, 값 {ft['values']} |",
        f"| D4 | 라벨 구조 | result {s['label_rows']}행 = 날짜×불량유형×개수, 총 불량 {s['defects_total']}건. result.idx가 단순 행번호: {s['result_idx_is_row_number']} → Raw와 건별 연결 불가 |",
        f"| D5 | 라벨 없는 날 | {s['days_without_label']} (Raw {s['days_raw']}일 중 라벨 {s['days_labeled']}일) |",
        f"| D6 | 순번 오류 | {s['idx_issues']} |",
        f"| D7 | 고정 변수 | {s['constant_columns']} |",
        "| D8 | scaled_data.csv | Raw와 행 단위 상관 " + ", ".join(f"{c} {v['rowwise_corr']}" for c, v in s['scaled_vs_raw'].items()) + " → **Raw를 스케일링한 파일이 아님**. 결측 " + ", ".join(f"{c} {v['nulls']}" for c, v in s['scaled_vs_raw'].items()) + " |",
        f"| D9 | 일별 신호 | 라벨 있는 {s['days_labeled']}일 기준 일별 불량 수와의 순위상관: " + ", ".join(f"{k} {v:+.2f}" for k, v in s['daily_spearman_vs_defects'].items() if k.endswith('_mean') or k in ('copy_share', 'high_force_rows')) + " (표본 8개, 우연 수준과 구분 어려움) |",
        "| D10 | 수집 범위 이탈 | " + ", ".join(f"{c} {v['n_out']}행 (범위 {v['range']}, 실제 {v['min']:.3g}~{v['max']:.3g})" for c, v in s['out_of_spec'].items()) + " |",
        "",
        "## 복사 창 길이 민감도",
        "",
        "| 창 길이 | 앞선 창 반복 비율 | 반복 창 소속 비율 |",
        "|---|---|---|",
        *[f"| {w} | {v['copy_of_earlier']:.1%} | {v['in_repeated']:.1%} |" for w, v in s["window_sensitivity"].items()],
        "",
        "## 고가압력 블록이 있는 날의 실제 불량 수",
        "",
        "| 날짜 | 고가압력 행 | 그날 불량 수 |",
        "|---|---|---|",
        *[f"| {d} | {hf['rows_per_day'][d]} | {v if v is not None else '라벨 없음'} |" for d, v in s["high_force_days_defects"].items()],
        "",
        "→ 243행짜리 이상 구간이 있는 날도 불량은 4~8건으로 다른 날과 비슷하다. 이 블록을 불량으로 간주하면 안 된다.",
        "",
        "## 일별 표",
        "",
        md_table(daily.round(3).reset_index()),
        "",
        "## 가장 긴 복사 구간 10개",
        "",
        md_table(segments.sort_values("length", ascending=False).head(10)) if len(segments) else "(없음)",
        "",
        "## 모델링에 주는 함의",
        "",
        "1. 학습·평가 분할은 **날짜 단위**로 한다. 무작위 행 분할은 복사된 창이 양쪽에 들어가 성능을 부풀린다.",
        "2. 이상탐지 모델은 복사 구간을 '흔한 패턴'으로 학습한다. 중복 제거판과 원본판을 모두 돌려 차이를 보고한다.",
        "3. 고가압력 블록(D2)은 별도 플래그로 두고, 불량 신호인지 운전 조건 전환인지 모델 결과와 분리해 해석한다.",
        "4. 실제 라벨로 가능한 정량 평가는 일별 불량 수(8일)뿐이다. 건별 F1은 주입 벤치마크(시뮬레이션)로만 제시한다.",
        "5. `scaled_data.csv`는 Raw와 대응하지 않으므로 사용하지 않거나, 사용한다면 별개 데이터로 취급하고 그 근거를 쓴다.",
    ]
    (OUT / "diagnosis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
