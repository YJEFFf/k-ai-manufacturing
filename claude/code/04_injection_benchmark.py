"""가상 불량 주입 벤치마크 — 건별 F1·FN·FP 평가.

건별 불량 라벨이 없으므로, 원본 행에 용접 물리에 맞춘 결함을 알려진 위치에 넣고 탐지 성능을 잰다.
결과는 '시뮬레이션 기반 검증'이며 실제 불량 탐지 성능이 아니다. 보고서에 반드시 이렇게 표기한다.

    python code/01_diagnose_welding.py
    python code/02_physics_lobe.py
    python code/04_injection_benchmark.py

결함 모델 (가정 — 보고서에 명시)
    용접부족(cold)  : 전류 −a, 통전시간 −b ms, 저항 유지 → 입열 부족
    파임(indent)    : 가압력 +c bar, 전류 +a', 가압력만큼 접촉저항 감소(1 bar당 1% 가정)
    크랙/날림(spike): 전류 급등 +d, 동저항 급락 −e (날림 시 저항이 급락하는 전형적 신호)
    전압은 V = R·I로 다시 계산하고, 모든 값은 원 데이터 정밀도로 반올림한다.

모델
    베이스라인: SPC, IsolationForest, AutoEncoder, RobustMahalanobis × (raw 센서 / phys 특징)
    문맥: Ctx(raw) = 원시 센서의 국소 잔차, PhysCtx = 물리 특징의 국소 잔차 (직전 W용접 중앙값 대비) + 로버스트 마할라노비스

산출물 (code/outputs/injection/)
    results_rows.csv, metrics.csv, recall_by_type_severity.csv, bench_report.md, summary.json, fig_f1.png, fig_recall_severity.png
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

from wlib import BASELINES, OUTPUTS, PHYS, SEED, SENSORS, add_features, load_physics, mahal2, make_folds, md_table, robust_cov

OUT = OUTPUTS / "injection"
K = 5
SEEDS = [SEED + i for i in range(5)]
RATE = 0.03  # 주 실험 불량 비율 (F1 추정이 안정되도록 실제 일별 불량률 0.33%보다 높게)
RATE_REALISTIC = 0.005  # 민감도 실험
W = 25  # 국소 문맥 창 (직전 용접 수)
SEVERITIES = ["small", "medium", "large"]
TYPES = ["cold", "indent", "spike"]
TYPE_KO = {"cold": "용접부족", "indent": "파임", "spike": "크랙/날림"}
PARAMS = {  # 심각도별 [small, medium, large]
    "cold": {"dI": [0.01, 0.025, 0.05], "dt": [0, 1, 3]},
    "indent": {"dF": [0.15, 0.4, 1.0], "dI": [0.005, 0.01, 0.02]},
    "spike": {"dI": [0.01, 0.025, 0.05], "dR": [0.01, 0.02, 0.04]},
}
CTX_RAW = SENSORS
CTX_PHYS = ["energy_J", "resistance_uohm", "force", "current", "weld_time"]


# ---------- 결함 주입 ----------
def inject(df: pd.DataFrame, rows: np.ndarray, rate: float, rng: np.random.Generator) -> pd.DataFrame:
    """rows(위치 인덱스) 중 rate 비율에 결함을 넣는다. y/dtype/severity 열을 붙여 반환."""
    df = df.copy()
    df["y"], df["dtype"], df["severity"] = 0, "", ""
    n = max(1, int(round(rate * len(rows))))
    pick = rng.choice(rows, size=n, replace=False)
    for pos in pick:
        t = TYPES[rng.integers(3)]
        k = rng.integers(3)
        I, V, tm, F = (df.iat[pos, df.columns.get_loc(c)] for c in ["current", "voltage", "weld_time", "force"])
        R = V / I  # V/kA 단위 그대로(비율만 쓰므로 단위 무관)
        p = PARAMS[t]
        if t == "cold":
            I2, t2, F2, R2 = I * (1 - p["dI"][k]), tm - p["dt"][k], F, R
        elif t == "indent":
            F2 = F + p["dF"][k]
            I2, t2, R2 = I * (1 + p["dI"][k]), tm, R * (1 - 0.01 * p["dF"][k])
        else:
            I2, t2, F2, R2 = I * (1 + p["dI"][k]), tm, F, R * (1 - p["dR"][k])
        df.iat[pos, df.columns.get_loc("current")] = round(I2, 2)
        df.iat[pos, df.columns.get_loc("voltage")] = round(R2 * round(I2, 2), 3)
        df.iat[pos, df.columns.get_loc("weld_time")] = round(t2)
        df.iat[pos, df.columns.get_loc("force")] = round(F2, 2)
        df.iat[pos, df.columns.get_loc("y")] = 1
        df.iat[pos, df.columns.get_loc("dtype")] = t
        df.iat[pos, df.columns.get_loc("severity")] = SEVERITIES[k]
    return df


# ---------- 문맥 잔차 ----------
def context_residuals(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """같은 날 안에서 직전 W용접의 중앙값을 뺀 잔차. 현재 용접은 문맥에 넣지 않는다(인과적)."""
    out = pd.DataFrame(index=df.index)
    for c in cols:
        g = df.groupby("day", sort=False)[c]
        ctx = g.transform(lambda s: s.shift(1).rolling(W, min_periods=5).median())
        ctx = ctx.fillna(g.transform(lambda s: s.shift(1).expanding().median())).fillna(df[c])
        out[f"r_{c}"] = df[c] - ctx
    return out


class CtxMahalanobis:
    def __init__(self, cols, name):
        self.cols, self.name = cols, name

    def fit(self, R: pd.DataFrame):
        self.sd = R.std().replace(0, 1)
        self.mu, self.cov = robust_cov((R / self.sd).to_numpy())
        return self

    def score(self, R: pd.DataFrame) -> np.ndarray:
        return mahal2((R / self.sd).to_numpy(), self.mu, self.cov)


def feature_views(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    f = add_features(df)
    return {"raw": f[SENSORS], "phys": f[PHYS],
            "ctx_raw": context_residuals(f, CTX_RAW), "ctx_phys": context_residuals(f, CTX_PHYS)}


def model_specs():
    specs = []
    for M in BASELINES:
        for view in ("raw", "phys"):
            specs.append((f"{M.name}|{view}", view, lambda M=M: M()))
    specs.append(("Ctx(raw)", "ctx_raw", lambda: CtxMahalanobis(CTX_RAW, "Ctx(raw)")))
    specs.append(("PhysCtx", "ctx_phys", lambda: CtxMahalanobis(CTX_PHYS, "PhysCtx")))
    return specs


def best_f1_threshold(y, s):
    order = np.argsort(-s)
    ys = y[order]
    tp = np.cumsum(ys)
    k = np.arange(1, len(ys) + 1)
    f1 = 2 * tp / (k + ys.sum())
    i = int(np.argmax(f1))
    return s[order][i]


# ---------- 실행 ----------
def run(base: pd.DataFrame, rate: float) -> pd.DataFrame:
    specs = model_specs()
    folds = base["fold"].to_numpy()
    clean_views = feature_views(base)
    records = []
    for f in range(K):
        tr_pos = np.where(folds != f)[0]
        te_pos = np.where(folds == f)[0]
        fitted = {name: make().fit(clean_views[view].iloc[tr_pos]) for name, view, make in specs}
        for seed in SEEDS:
            rng = np.random.default_rng(seed * 100 + f)
            val = inject(base, tr_pos, rate, rng)  # 임계값 결정용: 학습 구간에만 주입
            tst = inject(base, te_pos, rate, rng)  # 평가용: 평가 구간에만 주입
            vv, tv = feature_views(val), feature_views(tst)
            for name, view, _ in specs:
                m = fitted[name]
                thr = best_f1_threshold(val["y"].to_numpy()[tr_pos], m.score(vv[view].iloc[tr_pos]))
                s = m.score(tv[view].iloc[te_pos])
                rec = tst.iloc[te_pos][["row", "day", "y", "dtype", "severity", "high_force_block", "welds_since_reset", "current"]].copy()
                rec["model"], rec["seed"], rec["fold"], rec["score"], rec["pred"] = name, seed, f, s, (s >= thr).astype(int)
                records.append(rec)
        print(f"  rate={rate} fold {f} done")
    return pd.concat(records, ignore_index=True)


def scoped_metrics(res: pd.DataFrame) -> pd.DataFrame:
    """고가압력 블록(진단 D2) 안/밖을 나눠 본 성능. 이 블록은 운전 조건 자체가 요동치는 구간이다."""
    out = []
    for scope, g0 in [("전체", res), ("블록 밖", res[~res["high_force_block"]]), ("블록 안", res[res["high_force_block"]])]:
        for (m, seed), g in g0.groupby(["model", "seed"]):
            out.append({"scope": scope, "model": m, "F1": f1_score(g["y"], g["pred"]),
                        "precision": precision_score(g["y"], g["pred"], zero_division=0), "recall": recall_score(g["y"], g["pred"]),
                        "AP": average_precision_score(g["y"], g["score"]) if g["y"].sum() else np.nan})
    return pd.DataFrame(out).groupby(["scope", "model"])[["F1", "precision", "recall", "AP"]].mean().round(3).reset_index()


def metrics(res: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (m, seed), g in res.groupby(["model", "seed"]):
        rows.append({"model": m, "seed": seed,
                     "F1": f1_score(g["y"], g["pred"]), "precision": precision_score(g["y"], g["pred"], zero_division=0),
                     "recall": recall_score(g["y"], g["pred"]), "AP": average_precision_score(g["y"], g["score"]),
                     "FP_in_highforce_share": g.loc[(g["pred"] == 1) & (g["y"] == 0), "high_force_block"].mean()})
    per = pd.DataFrame(rows)
    agg = per.groupby("model").agg(["mean", "std"]).drop(columns="seed", level=0)
    agg.columns = [f"{a}_{b}" for a, b in agg.columns]
    return agg.sort_values("F1_mean", ascending=False).round(3)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_physics()
    df["day"] = df["day"].astype(str)
    df["fold"] = make_folds(df, K)
    base = df[~df["is_copy"]].sort_values("row").reset_index(drop=True)
    base = base[["row", "day", "idx", "fold", "is_copy", "high_force_block", "welds_since_reset", *SENSORS]]
    s = {"rows": len(base), "rate": RATE, "rate_realistic": RATE_REALISTIC, "seeds": SEEDS, "context_window": W, "params": PARAMS}

    res = run(base, RATE)
    met = metrics(res)
    s["metrics"] = met.reset_index().to_dict("records")

    rec = (res[res["y"] == 1].groupby(["model", "dtype", "severity"])["pred"].mean().unstack(["dtype", "severity"]))
    rec = rec.reindex(columns=pd.MultiIndex.from_product([TYPES, SEVERITIES])).round(3)
    rec.columns = [f"{TYPE_KO[a]}-{b}" for a, b in rec.columns]
    rec = rec.loc[met.index]

    # FP 위치: 제안 모델과 최상위 베이스라인 비교
    best_base = [m for m in met.index if "|" in m][0]
    fp_loc = {}
    for m in ["Ctx(raw)", "PhysCtx", best_base]:
        g = res[(res["model"] == m) & (res["y"] == 0)]
        fp = g[g["pred"] == 1]
        fp_loc[m] = {"FP_per_1000_clean": round(1000 * len(fp) / len(g), 2),
                     "FP_rate_highforce": round(float(g.loc[g["high_force_block"], "pred"].mean()), 4),
                     "FP_rate_normal": round(float(g.loc[~g["high_force_block"], "pred"].mean()), 4)}
    s["fp_location"] = fp_loc
    s["best_baseline"] = best_base

    scoped = scoped_metrics(res)
    s["scoped_metrics"] = scoped.to_dict("records")

    res_r = run(base, RATE_REALISTIC)
    met_r = metrics(res_r)
    s["metrics_realistic_rate"] = met_r.reset_index().to_dict("records")

    res.to_csv(OUT / "results_rows.csv", index=False, encoding="utf-8-sig")
    met.to_csv(OUT / "metrics.csv", encoding="utf-8-sig")
    met_r.to_csv(OUT / "metrics_realistic.csv", encoding="utf-8-sig")
    rec.to_csv(OUT / "recall_by_type_severity.csv", encoding="utf-8-sig")
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    plot(met, rec)
    scoped.to_csv(OUT / "metrics_scoped.csv", index=False, encoding="utf-8-sig")
    write_report(s, met, met_r, rec, scoped)
    print(f"done -> {OUT}")
    print(met[["F1_mean", "F1_std", "precision_mean", "recall_mean", "AP_mean"]].to_string())


def plot(met, rec):
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#d7301f" if "제안" in m else ("#fd8d3c" if m.startswith("Ctx") else "#9e9e9e") for m in met.index]
    ax.barh(met.index[::-1], met["F1_mean"][::-1], xerr=met["F1_std"][::-1], color=colors[::-1])
    ax.set_xlabel("F1 (mean ± std over 5 seeds, grouped 5-fold)")
    ax.set_title(f"Injection benchmark (rate {RATE:.0%}) — per-weld F1")
    fig.tight_layout()
    fig.savefig(OUT / "fig_f1.png", dpi=130)
    plt.close(fig)

    show = [m for m in rec.index if "제안" in m or m.startswith("Ctx")] + [m for m in rec.index if "|" in m][:2]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = np.arange(len(rec.columns))
    for j, m in enumerate(show):
        ax.bar(x + (j - len(show) / 2) * 0.2, rec.loc[m], 0.2, label=m)
    ax.set_xticks(x, rec.columns, rotation=30, ha="right")
    ax.set_ylabel("recall")
    ax.set_title("Recall by defect type × severity")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig_recall_severity.png", dpi=130)
    plt.close(fig)


def write_report(s, met, met_r, rec, scoped):
    cols = ["F1_mean", "F1_std", "precision_mean", "recall_mean", "AP_mean", "FP_in_highforce_share_mean"]
    lines = [
        "# 가상 불량 주입 벤치마크",
        "",
        "> `code/04_injection_benchmark.py` 자동 생성. **시뮬레이션 기반 검증이며 실제 불량 탐지 성능이 아니다.**",
        f"> 원본 {s['rows']:,}행, 원본 구간 5겹 분할, 시드 {len(s['seeds'])}개. 임계값은 학습 구간에 따로 주입한 데이터에서 F1 최대로 정하고 평가 구간에 적용.",
        "",
        "## 1. 결함 모델 (가정)",
        "",
        "| 유형 | 조작 | small / medium / large |",
        "|---|---|---|",
        f"| 용접부족 | 전류 감소, 통전시간 감소 | 전류 −{s['params']['cold']['dI']}, 시간 −{s['params']['cold']['dt']} ms |",
        f"| 파임 | 가압력·전류 증가, 가압력 1bar당 저항 1% 감소 | 가압력 +{s['params']['indent']['dF']} bar, 전류 +{s['params']['indent']['dI']} |",
        f"| 크랙/날림 | 전류 급등 + 동저항 급락 | 전류 +{s['params']['spike']['dI']}, 저항 −{s['params']['spike']['dR']} |",
        "",
        "## 2. 성능 (주입 비율 3%)",
        "",
        md_table(met[cols].reset_index()),
        "",
        "- Ctx(raw) = 원시 센서의 국소 잔차, PhysCtx = 물리 특징(입열량·동저항·가압력·전류·통전시간)의 국소 잔차. `…|phys` = 물리 특징(문맥 없음), `…|raw` = 원시 센서(문맥 없음).",
        "- 절제 비교: 문맥의 기여 = Ctx(raw) vs 베이스라인|raw, 물리 특징의 기여 = PhysCtx vs Ctx(raw).",
        "",
        "## 2-1. 고가압력 블록 안/밖 (진단 D2)",
        "",
        *sum([[f"**{sc}**", "", md_table(scoped[scoped['scope'] == sc].drop(columns='scope').sort_values('F1', ascending=False).head(6)), ""]
              for sc in ["블록 밖", "블록 안"]], []),
        "- 블록 안은 가압력이 5~10bar로 요동쳐 어떤 모델도 건별 판정이 안 된다(F1 < 0.15). 이 구간은 건별 불량 판정이 아니라 '운전 조건 이상' 경보로 따로 다루는 것이 타당하다.",
        "",
        "## 3. 유형 × 심각도별 재현율 (FN 분석)",
        "",
        md_table(rec.reset_index().rename(columns={"index": "model"})),
        "",
        "## 4. 오경보(FP) 위치",
        "",
        "| 모델 | 정상 1000건당 FP | 고가압력 블록 FP율 | 그 외 FP율 |",
        "|---|---|---|---|",
        *[f"| {m} | {v['FP_per_1000_clean']} | {v['FP_rate_highforce']} | {v['FP_rate_normal']} |" for m, v in s["fp_location"].items()],
        "",
        "## 5. 민감도: 현실적 불량 비율 0.5%",
        "",
        md_table(met_r[["F1_mean", "F1_std", "precision_mean", "recall_mean", "AP_mean"]].reset_index()),
        "",
        "## 6. 해석 시 주의",
        "",
        "- 결함 크기·형태는 가정이다. 결과는 '이런 종류의 이탈을 얼마나 잘 잡는가'이지 이 공장의 실제 불량 탐지율이 아니다.",
        "- 결함 모델을 바꿔도 순위가 유지되는지(강건성)는 PARAMS를 바꿔 재실행해 확인한다.",
    ]
    (OUT / "bench_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
