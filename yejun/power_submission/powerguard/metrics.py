"""회귀·분류·사건 지표."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def regression(y, p, T=None, mask_work=None) -> dict:
    """T: 피크 기준(스칼라 또는 y와 같은 길이의 배열)."""
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    ok = np.isfinite(y) & np.isfinite(p)
    y, p = y[ok], p[ok]
    if T is not None and np.ndim(T):
        T = np.asarray(T, float)[ok]
    e = p - y
    out = {
        "n": int(len(y)),
        "MAE": float(np.mean(np.abs(e))),
        "RMSE": float(np.sqrt(np.mean(e ** 2))),
        "bias": float(np.mean(e)),
        "nMAE": float(np.mean(np.abs(e)) / np.mean(y)),
        "CV_RMSE": float(np.sqrt(np.mean(e ** 2)) / np.mean(y)),
        "R2": float(1 - np.sum(e ** 2) / np.sum((y - y.mean()) ** 2)),
    }
    if T is not None:
        pk = y >= T
        out["n_peak"] = int(pk.sum())
        out["MAE_peak"] = float(np.mean(np.abs(e[pk]))) if pk.any() else np.nan
        out["bias_peak"] = float(np.mean(e[pk])) if pk.any() else np.nan
    if mask_work is not None:
        w = np.asarray(mask_work, bool)[ok]
        out["MAE_work"] = float(np.mean(np.abs(e[w]))) if w.any() else np.nan
        out["RMSE_work"] = float(np.sqrt(np.mean(e[w] ** 2))) if w.any() else np.nan
    return out


def classification(y, prob, thr: float) -> dict:
    y = np.asarray(y, int)
    prob = np.asarray(prob, float)
    ok = np.isfinite(prob)
    y, prob = y[ok], prob[ok]
    a = prob >= thr
    tp = int((a & (y == 1)).sum())
    fp = int((a & (y == 0)).sum())
    fn = int((~a & (y == 1)).sum())
    tn = int((~a & (y == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else np.nan
    rec = tp / (tp + fn) if tp + fn else np.nan
    f1 = 2 * prec * rec / (prec + rec) if tp else 0.0
    out = dict(n=int(len(y)), pos=int(y.sum()), TP=tp, FP=fp, FN=fn, TN=tn, precision=prec, recall=rec, F1=f1,
               FPR=fp / (fp + tn) if fp + tn else np.nan)
    if 0 < y.sum() < len(y) and np.unique(prob).size > 1:
        out["PR_AUC"] = float(average_precision_score(y, prob))
        out["ROC_AUC"] = float(roc_auc_score(y, prob))
    if np.all((prob >= 0) & (prob <= 1)):
        out["Brier"] = float(brier_score_loss(y, prob))
        out["ECE"] = ece(y, prob)
    return out


def ece(y, prob, bins: int = 10) -> float:
    y = np.asarray(y, float)
    prob = np.asarray(prob, float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(prob, edges[1:-1]), 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            tot += m.mean() * abs(prob[m].mean() - y[m].mean())
    return float(tot)


def best_f1_threshold(y, prob, grid=None) -> tuple[float, float]:
    """F1 최대 문턱(동률이면 더 높은 문턱 = 경보 수가 적은 쪽)."""
    y = np.asarray(y, int)
    prob = np.asarray(prob, float)
    if grid is None:
        grid = np.round(np.arange(0.05, 0.951, 0.01), 2)
    best = (0.5, -1.0)
    for t in grid:
        f = classification(y, prob, t)["F1"]
        if f >= best[1] - 1e-12:
            best = (float(t), float(f))
    return best


def interval_score(y, lo, hi, alpha: float) -> dict:
    y, lo, hi = (np.asarray(v, float) for v in (y, lo, hi))
    ok = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    y, lo, hi = y[ok], lo[ok], hi[ok]
    cov = (y >= lo) & (y <= hi)
    width = hi - lo
    iscore = width + 2 / alpha * (lo - y) * (y < lo) + 2 / alpha * (y - hi) * (y > hi)
    return {"n": int(len(y)), "coverage": float(cov.mean()), "width": float(width.mean()),
            "interval_score": float(iscore.mean())}


def daily_peak(df: pd.DataFrame, pred_col: str, y_col: str = "y") -> dict:
    """날짜별 최대값 오차와 최대 발생 슬롯 적중(±1구간)."""
    g = df.dropna(subset=[y_col, pred_col]).groupby(df.dropna(subset=[y_col, pred_col]).index.normalize())
    rows = []
    for d, x in g:
        if len(x) < 80:
            continue
        ia, ip = x[y_col].idxmax(), x[pred_col].idxmax()  # 시각으로 비교(결측 구간이 있어도 슬롯이 어긋나지 않음)
        rows.append(dict(date=d, ymax=x[y_col].max(), pmax=x[pred_col].max(),
                         slot_err=abs(int((ia - ip) / pd.Timedelta(minutes=15)))))
    r = pd.DataFrame(rows)
    if r.empty:
        return {}
    return {"n_days": int(len(r)), "daymax_MAE": float((r.pmax - r.ymax).abs().mean()),
            "daymax_bias": float((r.pmax - r.ymax).mean()), "peak_slot_hit_pm1": float((r.slot_err <= 1).mean())}


def paired_day_bootstrap(y: pd.Series, p_a: pd.Series, p_b: pd.Series, mask: np.ndarray, n_boot: int = 2000,
                         block_days: int = 1, seed: int = 0, stat: str = "RMSE") -> dict:
    """날짜 블록 부트스트랩으로 (a − b) 지표 차이의 분포. 음수면 a가 더 좋다.

    stat: 'RMSE' | 'MAE' | 'daymax_MAE'(일 최대 절대오차 평균).
    block_days>1이면 연속 날짜 블록(이동 블록)을 뽑는다.
    """
    d = pd.DataFrame({"y": y, "a": p_a, "b": p_b})[mask].dropna()
    day = d.index.normalize()
    if stat == "daymax_MAE":
        g = d.groupby(day)
        per_day = pd.DataFrame({"ea": (g["a"].max() - g["y"].max()).abs(), "eb": (g["b"].max() - g["y"].max()).abs(),
                                "n": g.size()})
        per_day = per_day[per_day["n"] >= 80]
        A, B, W = per_day["ea"].to_numpy(), per_day["eb"].to_numpy(), np.ones(len(per_day))
        keys = per_day.index
    else:
        ea = (d["a"] - d["y"]).to_numpy()
        eb = (d["b"] - d["y"]).to_numpy()
        f = (lambda e: e ** 2) if stat == "RMSE" else np.abs
        s = pd.DataFrame({"a": f(ea), "b": f(eb), "day": day}).groupby("day")
        A, B, W = s["a"].sum().to_numpy(), s["b"].sum().to_numpy(), s.size().to_numpy().astype(float)
        keys = s.size().index
    n = len(keys)
    rng = np.random.default_rng(seed)

    def value(ix):
        wa = A[ix].sum() / W[ix].sum()
        wb = B[ix].sum() / W[ix].sum()
        if stat == "RMSE":
            return np.sqrt(wa) - np.sqrt(wb)
        return wa - wb

    point = value(np.arange(n))
    boots = []
    starts_max = max(n - block_days + 1, 1)
    for _ in range(n_boot):
        if block_days <= 1:
            ix = rng.integers(0, n, n)
        else:
            nb = int(np.ceil(n / block_days))
            st = rng.integers(0, starts_max, nb)
            ix = np.concatenate([np.arange(s0, min(s0 + block_days, n)) for s0 in st])[:n]
        boots.append(value(ix))
    boots = np.array(boots)
    return {"stat": stat, "diff": float(point), "ci90": [float(np.quantile(boots, 0.05)), float(np.quantile(boots, 0.95))],
            "p_a_better": float(np.mean(boots < 0)), "n_days": int(n)}


def multi_bootstrap_rmse(y: pd.Series, pa: list[pd.Series], pb: list[pd.Series], mask: np.ndarray,
                         n_boot: int = 2000, seed: int = 0) -> dict:
    """여러 지평(목록)의 RMSE 평균 차이(a − b)를 날짜 단위로 짝지어 부트스트랩한다."""
    per = []
    days_all = None
    for a, b in zip(pa, pb):
        d = pd.DataFrame({"y": y, "a": a, "b": b})[mask].dropna()
        g = pd.DataFrame({"ea": (d["a"] - d["y"]) ** 2, "eb": (d["b"] - d["y"]) ** 2}).groupby(d.index.normalize())
        t = pd.DataFrame({"A": g["ea"].sum(), "B": g["eb"].sum(), "W": g.size()})
        per.append(t)
        days_all = t.index if days_all is None else days_all.intersection(t.index)
    per = [t.reindex(days_all) for t in per]
    n = len(days_all)
    rng = np.random.default_rng(seed)

    def value(ix):
        return float(np.mean([np.sqrt(t["A"].to_numpy()[ix].sum() / t["W"].to_numpy()[ix].sum())
                              - np.sqrt(t["B"].to_numpy()[ix].sum() / t["W"].to_numpy()[ix].sum()) for t in per]))

    point = value(np.arange(n))
    boots = np.array([value(rng.integers(0, n, n)) for _ in range(n_boot)])
    return {"stat": "mean_RMSE", "diff": point, "ci90": [float(np.quantile(boots, 0.05)), float(np.quantile(boots, 0.95))],
            "p_a_better": float(np.mean(boots < 0)), "n_days": int(n)}
