"""베이스라인 이상탐지 4종 + 누수 없는 검증 틀.

    python code/01_diagnose_welding.py
    python code/02_physics_lobe.py
    python code/03_baselines.py

하는 일
    1. 누수 점검: 무작위 행 분할 vs 원본 구간 분할에서, 평가 행이 학습에 '같은 원본'으로 들어가 있는 비율
    2. 원본 구간 5겹 분할로 베이스라인 4종 × 특징 2종(원시 센서 / 물리 특징) × 학습 2방식(중복 제거 / 전체)의 out-of-fold 점수
    3. 실제 라벨로 가능한 유일한 점검: 일별 불량 수 LODO (다른 날의 불량률로 임계값을 정해 남긴 날의 불량 수 예측)
    4. 모델 간 일치도와, 상위 1% 경보가 어디에 몰리는지(고가압력 블록·복사 경계·스테퍼 구간)

산출물 (code/outputs/baselines/)
    oof_scores.csv, daily_lodo.csv, baseline_report.md, summary.json, fig_daily_lodo.png
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wlib import BASELINES, OUTPUTS, PHYS, SEED, SENSORS, load_daily_labels, load_physics, make_folds, md_table

OUT = OUTPUTS / "baselines"
K = 5
FEATURE_SETS = {"raw": SENSORS, "phys": PHYS}
FIT_MODES = ("dedup", "all")  # dedup: 학습 구간의 원본 행만 / all: 복제 행 포함 전체


def leakage_check(df: pd.DataFrame, folds: np.ndarray) -> dict:
    rng = np.random.default_rng(SEED)
    out = {}
    rand_test = rng.random(len(df)) < 0.2
    src = df["source_row"].to_numpy()
    out["random_row_split"] = float(np.isin(src[rand_test], src[~rand_test]).mean())
    leaks = [float(np.isin(src[folds == f], src[folds != f]).mean()) for f in range(K)]
    out["grouped_split"] = float(np.mean(leaks))
    return out


def oof_scores(df: pd.DataFrame, folds: np.ndarray) -> pd.DataFrame:
    scores = pd.DataFrame(index=df.index)
    for fs_name, cols in FEATURE_SETS.items():
        X = df[cols]
        for mode in FIT_MODES:
            for Model in BASELINES:
                col = f"{Model.name}|{fs_name}|{mode}"
                s = np.full(len(df), np.nan)
                for f in range(K):
                    tr = folds != f
                    if mode == "dedup":
                        tr &= ~df["is_copy"].to_numpy()
                    m = Model().fit(X[tr])
                    te = folds == f
                    s[te] = m.score(X[te])
                scores[col] = s
                print(f"  scored {col}")
    return scores


def daily_lodo(df: pd.DataFrame, scores: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """다른 7일의 불량률로 경보 임계값을 정하고, 남긴 날의 경보 수를 불량 수 예측으로 본다."""
    days = [d for d in labels.index if d in set(df["day"])]
    n = df.groupby("day").size()
    rows = []
    for col in scores.columns:
        for d in days:
            others = [x for x in days if x != d]
            rate = labels.loc[others, "defect_total"].sum() / n[others].sum()
            ref = scores.loc[df["day"].isin(others), col]
            thr = np.quantile(ref, 1 - rate)
            pred = int((scores.loc[df["day"] == d, col] > thr).sum())
            rows.append({"model": col, "day": d, "actual": float(labels.at[d, "defect_total"]),
                         "pred": pred, "naive": rate * n[d]})
    out = pd.DataFrame(rows)
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_physics()
    df["day"] = df["day"].astype(str)
    folds = make_folds(df, K)
    df["fold"] = folds
    labels = load_daily_labels()
    s: dict = {"folds": {int(f): int((folds == f).sum()) for f in range(K)}}

    s["leakage"] = leakage_check(df, folds)
    print("leakage:", s["leakage"])

    scores = oof_scores(df, folds)

    lodo = daily_lodo(df, scores, labels)
    summ = lodo.groupby("model").apply(lambda g: pd.Series({
        "MAE_model": (g["pred"] - g["actual"]).abs().mean(),
        "MAE_naive": (g["naive"] - g["actual"]).abs().mean(),
        "spearman_pred_actual": g["pred"].corr(g["actual"], method="spearman"),
        "pred_total": g["pred"].sum(),
    }), include_groups=False).round(3).sort_values("MAE_model")
    s["daily_lodo"] = summ.reset_index().to_dict("records")
    s["actual_total_labeled"] = float(labels["defect_total"].sum())

    # 모델 간 일치도 (dedup 학습, 원시·물리 각각)
    main_cols = [c for c in scores.columns if c.endswith("|dedup")]
    s["spearman_between_models"] = scores[main_cols].corr(method="spearman").round(3).to_dict()
    top = {c: set(scores[c].nlargest(int(0.01 * len(df))).index) for c in main_cols}
    s["top1pct_jaccard"] = {f"{a.split('|')[0]} vs {b.split('|')[0]} ({a.split('|')[1]})": round(len(top[a] & top[b]) / len(top[a] | top[b]), 3)
                            for i, a in enumerate(main_cols) for b in main_cols[i + 1:] if a.split("|")[1] == b.split("|")[1]}

    # 상위 1% 경보가 어디에 몰리나
    stepper_zone = df["welds_since_reset"].notna() & (df["current"] > df["current"].quantile(0.9))
    where = {}
    for c in main_cols:
        t = scores[c] >= scores[c].quantile(0.99)
        where[c] = {"high_force_block": round(float(df.loc[t, "high_force_block"].mean()), 3),
                    "copy_boundary": round(float(df.loc[t, "copy_boundary"].mean()), 3),
                    "high_current_stepper_zone": round(float(stepper_zone[t].mean()), 3)}
    s["top1pct_location"] = where
    s["base_rates"] = {"high_force_block": round(float(df["high_force_block"].mean()), 3),
                       "copy_boundary": round(float(df["copy_boundary"].mean()), 3),
                       "high_current_stepper_zone": round(float(stepper_zone.mean()), 3)}

    out = pd.concat([df[["row", "day", "idx", "fold", "is_copy", "source_row", "high_force_block"]], scores], axis=1)
    out.to_csv(OUT / "oof_scores.csv", index=False, encoding="utf-8-sig")
    lodo.to_csv(OUT / "daily_lodo.csv", index=False, encoding="utf-8-sig")
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    plot_lodo(lodo, summ)
    write_report(s, summ)
    print(f"done -> {OUT}")
    print(summ.head(8).to_string())


def plot_lodo(lodo, summ):
    best = summ.index[:3].tolist()
    fig, ax = plt.subplots(figsize=(10, 5))
    days = lodo["day"].unique()
    x = np.arange(len(days))
    act = lodo.drop_duplicates("day").set_index("day").loc[days]
    ax.bar(x - 0.3, act["actual"], 0.15, label="actual defects", color="#333")
    ax.bar(x - 0.15, act["naive"], 0.15, label="naive (rate × n)", color="#bbb")
    for j, m in enumerate(best):
        g = lodo[lodo["model"] == m].set_index("day").loc[days]
        ax.bar(x + 0.15 * j, g["pred"], 0.15, label=m)
    ax.set_xticks(x, [d[5:] for d in days])
    ax.set_ylabel("defects per day")
    ax.set_title("Leave-one-day-out daily defect count — top-3 baselines vs naive")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "fig_daily_lodo.png", dpi=130)
    plt.close(fig)


def write_report(s, summ):
    lk = s["leakage"]
    loc = pd.DataFrame(s["top1pct_location"]).T.reset_index().rename(columns={"index": "model"})
    lines = [
        "# 베이스라인 이상탐지 · 검증 틀",
        "",
        "> `code/03_baselines.py` 자동 생성. 점수는 모두 out-of-fold(원본 구간 5겹 분할)이다.",
        "",
        "## 1. 왜 원본 구간 단위로 나눠야 하나 (누수 점검)",
        "",
        "| 분할 방식 | 평가 행 중 '같은 원본'이 학습에도 있는 비율 |",
        "|---|---|",
        f"| 무작위 행 분할(80/20) | **{lk['random_row_split']:.1%}** |",
        f"| 원본 구간 5겹 분할(우리 방식) | {lk['grouped_split']:.1%} |",
        "",
        "→ 무작위로 나누면 평가 데이터 대부분이 학습 데이터와 똑같은 행이다. 이렇게 나온 성능은 의미가 없다.",
        "",
        "## 2. 모델",
        "",
        "| 모델 | 방식 |",
        "|---|---|",
        "| SPC | 변수별 로버스트 z의 최대 절댓값 — 현장 관리한계 규칙 |",
        "| IsolationForest | 트리 분할로 쉽게 고립되는 점을 이상으로 봄 |",
        "| AutoEncoder | 병목층 신경망의 복원 오차 — 원 가이드북 방식 재현 |",
        "| RobustMahalanobis | 로버스트 공분산 기준 통계적 거리 |",
        "",
        "특징: raw = 가압력·전류·전압·통전시간 / phys = 입열량·동저항·가압력·전류·통전시간. 학습: dedup = 학습 구간의 원본 행만 / all = 복제 행 포함.",
        "",
        "## 3. 일별 불량 수 LODO (실제 라벨, 8일)",
        "",
        f"다른 7일의 불량률로 임계값을 정하고 남긴 날의 경보 수를 불량 수로 본다. 실제 총 불량 {s['actual_total_labeled']:.0f}건.",
        "",
        md_table(summ.reset_index()),
        "",
        "- MAE_naive = '다른 날 평균 불량률 × 그날 용접 수'. 모델이 이를 못 이기면 센서 이상점수가 일별 불량 수를 설명하지 못한다는 뜻이다.",
        "- 날짜 간 센서 구간이 복제돼 있어(진단 D1) 이 점검의 검정력은 매우 낮다. 건별 성능은 04 주입 벤치마크로 본다.",
        "",
        "## 4. 모델 간 일치도 (상위 1% 경보 Jaccard)",
        "",
        "| 쌍 | Jaccard |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s["top1pct_jaccard"].items()],
        "",
        "## 5. 상위 1% 경보가 몰리는 곳 (오경보 후보)",
        "",
        md_table(loc),
        "",
        f"기준 비율: {s['base_rates']}",
        "",
        "- 고가압력 블록이 전체의 8%인데 경보의 대부분을 차지한다면, 베이스라인은 '평소와 다른 운전 조건'을 이상으로 잡고 있는 것이다. 이것이 불량인지는 라벨로 확인할 수 없다(해당 날짜 불량 4~8건으로 평범 — 진단 D2).",
    ]
    (OUT / "baseline_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
