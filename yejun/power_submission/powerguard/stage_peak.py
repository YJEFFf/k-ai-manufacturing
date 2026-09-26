"""S5: 피크 위험 확률·예측구간·경보·사건·월 최대 경신 위험.

'정직한 예측 흐름' = 교차검증 OOF(6·7월) + 시험(8~9월) 예측. 잔차 기반 분포는 이 흐름의 과거 잔차만 쓴다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from . import cv as CV
from . import features as F
from . import io
from . import metrics as MT
from . import models as M
from . import peak as PK
from . import stage_models as SM

KNOWN_A = pd.Timedelta(minutes=60)   # 과제 A: D일 첫 목표의 발행은 D 00:00보다 최대 60분 앞
KNOWN_B = pd.Timedelta(hours=7)      # 과제 B: D-1 17:00 발행
TAU_GRID = np.round(np.arange(0.05, 0.96, 0.05), 2)


def honest_stream(task: str, model: str) -> pd.Series:
    """OOF와 시험 예측을 하나의 시간순 흐름으로 합친다. 한쪽이라도 없으면 오류(조용히 건너뛰면 교차검증 구간이 비어
    뒤 단계가 틀린 산출물을 쓴다)."""
    parts = []
    for name in ("oof", "test"):
        f = C.ARTIFACT_DIR / f"{name}_{task}.csv.gz"
        if not f.exists():
            raise FileNotFoundError(f"행 단위 예측이 없다: {f} — models 단계를 먼저 실행한다(제출 묶음이면 artifacts/ 확인)")
        df = SM.load_predictions(name, task)
        if model not in df:
            raise KeyError(f"{f.name}에 {model} 예측이 없다")
        parts.append(df[model])
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated(keep="last")]


def period_masks(index: pd.DatetimeIndex) -> dict:
    cv_m = np.zeros(len(index), bool)
    for _, s, e in CV.cv_blocks():
        cv_m |= (index >= s) & (index < e)
    te = (index >= C.TEST_START) & (index < C.TEST_END)
    return {"cv": cv_m, "test": te}


def thresholds(iv: pd.DataFrame, index: pd.DatetimeIndex) -> np.ndarray:
    """구간별 피크 기준: 교차검증 폴드는 그 폴드 학습 q95, 시험은 7/31까지 q95."""
    T = np.full(len(index), np.nan)
    for _, s, e in CV.cv_blocks():
        m = (index >= s) & (index < e)
        T[m] = CV.peak_threshold(iv, s)
    m = (index >= C.TEST_START) & (index < C.TEST_END)
    T[m] = CV.peak_threshold(iv, C.TEST_START)
    return T


# ---------------------------------------------------------------- 분류기(직접)

def classifier_frame(frames: dict) -> pd.DataFrame:
    """발행 구간 i 행: 목표 i+1 특징(A1) + 다음 1시간 유사일 최대."""
    x1 = frames["A1"]
    Xc = x1.shift(-1)
    an = x1["analog_mean"]
    Xc["analog_next_max"] = pd.concat([an.shift(-k) for k in range(1, 5)], axis=1).max(axis=1)
    Xc["analog_next_minus_now"] = Xc["analog_next_max"] - x1["lag_0"].shift(-1)
    return Xc


def run_classifier(iv: pd.DataFrame, Xc: pd.DataFrame, labels: pd.DataFrame, T_arr: np.ndarray) -> pd.Series:
    """주간 재학습 LightGBM 분류기. 학습 라벨은 해당 블록의 기준 T로 만든다."""
    feats = F.feature_list("A") + ["analog_next_max", "analog_next_minus_now"]
    feats = [c for c in feats if c in Xc.columns and c != "horizon"]
    prob = pd.Series(np.nan, index=Xc.index)
    trainable_next = PK.next_hour_labels(iv["y_train"], iv["trainable"].to_numpy())
    blocks = []
    for _, s, e in CV.cv_blocks():
        blocks += CV.weekly_blocks(s, e)
    blocks += CV.weekly_blocks(C.TEST_START, C.TEST_END)
    idx = Xc.index
    for s, e in blocks:
        T = CV.peak_threshold(iv, s if s < C.TEST_START else C.TEST_START)
        if s < C.TEST_START:
            fold_start = max(fs for _, fs, _ in CV.cv_blocks() if fs <= s)
            T = CV.peak_threshold(iv, fold_start)
        lab = (trainable_next["max_next"] >= T).astype(float).where(trainable_next["valid"])
        tr = (idx < s - pd.Timedelta(minutes=75)) & lab.notna().to_numpy()
        ev = (idx >= s) & (idx < e)
        if tr.sum() < 500 or lab[tr].nunique() < 2:
            continue
        m = M.LGBClassifier(feats, params=dict(n_estimators=300, num_leaves=15, min_child_samples=40)).fit(Xc.loc[tr], lab[tr])
        prob.loc[ev] = m.predict_proba(Xc.loc[ev])
    return prob


def climatology_prob(iv: pd.DataFrame, labels: pd.DataFrame, regime_day: pd.Series) -> pd.Series:
    """확률형 기준: 발행 구간 i의 P(다음 1시간 최대 ≥ T)를 과거 빈도로 추정(키 = 목표일 체제 × 첫 목표 슬롯).

    주간 재학습과 같게 블록 시작 75분 전까지 끝난 발행만으로 빈도를 만들고, 키 표본이 10 미만이면 슬롯 → 전체 빈도.
    T는 블록이 속한 폴드(또는 시험)의 기준을 쓴다.
    """
    idx = iv.index
    tgt = idx + pd.Timedelta(minutes=15)
    reg = regime_day.reindex(tgt.normalize()).to_numpy()
    slot = (tgt.hour * 4 + tgt.minute // 15).to_numpy()
    valid = labels["valid"].to_numpy()
    mx = labels["max_next"].to_numpy()
    prob = pd.Series(np.nan, index=idx)
    blocks = []
    for name, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        blocks += [(s0, e0, s) for s0, e0 in CV.weekly_blocks(s, e)]
    for s0, e0, fold_start in blocks:
        T = CV.peak_threshold(iv, fold_start)
        tr = valid & (idx < s0 - pd.Timedelta(minutes=75)) & np.isfinite(reg)
        lab = (mx[tr] >= T).astype(float)
        d = pd.DataFrame({"r": reg[tr], "s": slot[tr], "l": lab})
        k2 = d.groupby(["r", "s"])["l"].agg(["mean", "size"])
        k1 = d.groupby("s")["l"].mean()
        base = float(d["l"].mean()) if len(d) else np.nan
        ev = (idx >= s0) & (idx < e0)
        key = pd.MultiIndex.from_arrays([reg[ev], slot[ev]])
        v2 = k2.reindex(key)
        pv = np.where(v2["size"].to_numpy() >= 10, v2["mean"].to_numpy(), np.nan)
        pv = np.where(np.isfinite(pv), pv, k1.reindex(slot[ev]).to_numpy())
        pv = np.where(np.isfinite(pv), pv, base)
        prob[ev] = pv
    return prob


def _day_boot(days: np.ndarray, fn, n_boot: int = 2000, block_days: int = 1, seed: int = 0) -> tuple[float, list]:
    """날짜(블록) 부트스트랩: fn(선택된 날짜 배열) → 통계. 점추정과 90% 구간."""
    ud = np.array(sorted(np.unique(days)))
    n = len(ud)
    rng = np.random.default_rng(seed)
    point = fn(ud)
    bs = []
    for _ in range(n_boot):
        if block_days <= 1:
            pick = ud[rng.integers(0, n, n)]
        else:
            st = rng.integers(0, max(n - block_days + 1, 1), int(np.ceil(n / block_days)))
            pick = np.concatenate([ud[s0:s0 + block_days] for s0 in st])[:n]
        bs.append(fn(pick))
    bs = np.array(bs, float)
    return float(point), [float(np.nanquantile(bs, 0.05)), float(np.nanquantile(bs, 0.95))]


def f1_difference_bootstrap(lab: np.ndarray, pa: np.ndarray, ta: float, pb: np.ndarray, tb: float, mask: np.ndarray,
                            index: pd.DatetimeIndex, block_days: int) -> dict:
    """발행 구간 F1 차이(a − b)의 날짜 블록 부트스트랩. 날짜별 TP·FP·FN을 합쳐 다시 계산한다."""
    day = index.normalize().to_numpy()
    m = mask
    a, b = (pa >= ta) & m, (pb >= tb) & m
    y = lab & m
    df = pd.DataFrame({"d": day[m], "tpa": (a & y)[m], "fpa": (a & ~y)[m], "fna": (~a & y)[m],
                       "tpb": (b & y)[m], "fpb": (b & ~y)[m], "fnb": (~b & y)[m]}).groupby("d").sum()

    def f1(tp, fp, fn):
        return 2 * tp / (2 * tp + fp + fn) if tp else 0.0

    def fn_(pick):
        s = df.loc[pick].sum()
        return f1(s.tpa, s.fpa, s.fna) - f1(s.tpb, s.fpb, s.fnb)

    point, ci = _day_boot(df.index.to_numpy(), fn_, block_days=block_days)
    return {"F1_diff": point, "ci90": ci, "n_days": int(len(df))}


def prob_quality_bootstrap(lab: np.ndarray, probs: dict, chosen: str, masks: dict, common: np.ndarray,
                           index: pd.DatetimeIndex, n_boot: int = 2000) -> pd.DataFrame:
    """확률 품질 차이의 날짜 블록 부트스트랩(1·7일 블록, 90% 구간): 선택 방법의 BSS(기후값 대비)와 Brier·PR-AUC 차이
    (선택 − 기후값, 선택 − LightGBM 분류기). 같은 재표집으로 두 비교를 함께 계산한다."""
    from sklearn.metrics import average_precision_score as ap
    day = index.normalize().to_numpy()
    rows = []
    for per in ("cv", "test"):
        m = masks[per] & common
        yy, dd = lab[m].astype(float), day[m]
        pa = probs[chosen].to_numpy()[m]
        others = {o: probs[o].to_numpy()[m] for o in ("P_climatology", "P_lgbm_classifier") if o != chosen}
        ud = np.array(sorted(np.unique(dd)))
        pos = {d: np.where(dd == d)[0] for d in ud}

        def stats(ix):
            y_, a_ = yy[ix], pa[ix]
            ba = np.mean((a_ - y_) ** 2)
            ok = 0 < y_.sum() < len(y_)
            ap_a = ap(y_, a_) if ok else np.nan
            out = []
            for pb in others.values():
                bb = np.mean((pb[ix] - y_) ** 2)
                out += [1 - ba / bb, ba - bb, (ap_a - ap(y_, pb[ix])) if ok else np.nan]
            return out

        point = stats(np.arange(len(yy)))
        for bd in (1, 7):
            rng = np.random.default_rng(C.SEED)
            bs = []
            for _ in range(n_boot):
                if bd <= 1:
                    pick = ud[rng.integers(0, len(ud), len(ud))]
                else:
                    st = rng.integers(0, max(len(ud) - bd + 1, 1), int(np.ceil(len(ud) / bd)))
                    pick = np.concatenate([ud[s0:s0 + bd] for s0 in st])[:len(ud)]
                bs.append(stats(np.concatenate([pos[d] for d in pick])))
            bs = np.array(bs, float)
            for j, o in enumerate(others):
                for k, metric in enumerate(("BSS", "Brier_diff", "PR_AUC_diff")):
                    c = 3 * j + k
                    rows.append(dict(method=chosen, vs=o, period=per, block_days=bd, metric=metric, value=point[c],
                                     ci90_lo=float(np.nanquantile(bs[:, c], 0.05)), ci90_hi=float(np.nanquantile(bs[:, c], 0.95)),
                                     n_days=int(len(ud))))
    return pd.DataFrame(rows)


def calibration_table(lab: np.ndarray, probs: dict, masks: dict, common: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    """확률 방법 × 보정(없음/등방 회귀)의 ECE·Brier. 교차검증은 폴드 교차 적합(한 폴드로 적합해 다른 폴드에 적용),
    시험은 교차검증 전체로 적합. 신뢰도 곡선용 10구간 표도 만든다."""
    from sklearn.isotonic import IsotonicRegression
    rows, rel = [], []
    folds = [(n, s, e) for n, s, e in CV.cv_blocks()]
    for pname, p in probs.items():
        pv = p.to_numpy()
        for calib in ("none", "isotonic"):
            out = np.full(len(pv), np.nan)
            if calib == "none":
                out = pv.copy()
            else:
                idx = p.index
                for i, (_, s, e) in enumerate(folds):
                    fit_m = common & masks["cv"] & ~((idx >= s) & (idx < e)) & np.isfinite(pv)
                    app = common & (idx >= s) & (idx < e) & np.isfinite(pv)
                    if fit_m.sum() > 100 and lab[fit_m].min() != lab[fit_m].max():
                        iso = IsotonicRegression(out_of_bounds="clip").fit(pv[fit_m], lab[fit_m].astype(float))
                        out[app] = iso.predict(pv[app])
                fit_m = common & masks["cv"] & np.isfinite(pv)
                iso = IsotonicRegression(out_of_bounds="clip").fit(pv[fit_m], lab[fit_m].astype(float))
                app = masks["test"] & np.isfinite(pv)
                out[app] = iso.predict(pv[app])
            for per in ("cv", "test"):
                m = masks[per] & common & np.isfinite(out)
                c = MT.classification(lab[m].astype(int), out[m], 0.5)
                rows.append(dict(method=pname, calibration=calib, period=per, n=c["n"], Brier=c.get("Brier"),
                                 ECE=c.get("ECE"), PR_AUC=c.get("PR_AUC")))
                if calib == "none" or pname == "P_lgbm_classifier":
                    edges = np.linspace(0, 1, 11)
                    b = np.clip(np.digitize(out[m], edges[1:-1]), 0, 9)
                    for k in range(10):
                        mm = b == k
                        if mm.any():
                            rel.append(dict(method=pname, calibration=calib, period=per, bin=k, n=int(mm.sum()),
                                            mean_prob=float(out[m][mm].mean()), observed=float(lab[m][mm].mean())))
    return pd.DataFrame(rows), pd.DataFrame(rel)


def coverage_gain_bootstrap(y: pd.Series, ivs: dict, groups: np.ndarray, mask: np.ndarray, alpha: float) -> dict:
    """Mondrian − 전역 보정의 가동 주간 포괄률·interval score 차이(날짜 부트스트랩 90% 구간)."""
    m = mask & (groups == 1) & np.isfinite(ivs["rolling_mondrian"]["lo"].to_numpy()) & np.isfinite(ivs["rolling_global"]["lo"].to_numpy())
    yy = y.to_numpy()
    rec = {}
    for k, v in ivs.items():
        lo, hi = v["lo"].to_numpy(), v["hi"].to_numpy()
        cov = ((yy >= lo) & (yy <= hi)).astype(float)
        sc = (hi - lo) + 2 / alpha * (lo - yy) * (yy < lo) + 2 / alpha * (yy - hi) * (yy > hi)
        rec[k] = (cov, sc)
    d = pd.DataFrame({"day": y.index.normalize()[m], "cm": rec["rolling_mondrian"][0][m], "cg": rec["rolling_global"][0][m],
                      "sm": rec["rolling_mondrian"][1][m], "sg": rec["rolling_global"][1][m]}).groupby("day").agg(["sum", "size"])
    days = d.index.to_numpy()

    def cov_diff(pick):
        s = d.loc[pick]
        return (s[("cm", "sum")].sum() - s[("cg", "sum")].sum()) / s[("cm", "size")].sum()

    def score_diff(pick):
        s = d.loc[pick]
        return (s[("sm", "sum")].sum() - s[("sg", "sum")].sum()) / s[("sm", "size")].sum()

    c, cci = _day_boot(days, cov_diff)
    sdiff, sci = _day_boot(days, score_diff)
    return {"coverage_diff": c, "coverage_diff_ci90": cci, "interval_score_diff": sdiff, "interval_score_diff_ci90": sci,
            "n_days": int(len(days))}


# ---------------------------------------------------------------- 주 실행

def run(iv: pd.DataFrame, frames: dict, selection: dict) -> dict:
    od = io.out_dir("peak")
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    idx = iv.index
    masks = period_masks(idx)
    T_arr = thresholds(iv, idx)
    st = F.schedule_table(iv)
    grp = PK.regime(iv, st["regime"])
    mA = selection["A"]["chosen"]
    mB = selection["B"]["chosen"]
    preds_h = {h: honest_stream(f"A{h}", mA).reindex(idx) for h in range(1, 5)}
    pred_B = honest_stream("B", mB).reindex(idx)
    res = {"model_A": mA, "model_B": mB, "T_test": float(CV.peak_threshold(iv, C.TEST_START)),
           "T_cv": {n: CV.peak_threshold(iv, s) for n, s, _ in CV.cv_blocks()}}

    # ---- 예측구간(롤링 split conformal / Mondrian / ACI). 잔차는 첫 발행 시각 전에 끝난 목표만.
    rows, cov_boot = [], []
    for task, pr in [("B", pred_B), ("A1", preds_h[1]), ("A4", preds_h[4])]:
        kb = KNOWN_B if task == "B" else KNOWN_A
        for alpha in (0.2, 0.1):
            variants = {
                "rolling_global": PK.rolling_intervals(y, pr, np.zeros(len(y), int), alpha, known_before=kb),
                "rolling_mondrian": PK.rolling_intervals(y, pr, grp, alpha, known_before=kb),
                "aci_mondrian": PK.rolling_intervals(y, pr, grp, alpha, aci_gamma=0.05, eval_mask=usable, known_before=kb),
            }
            for vname, iv_ in variants.items():
                for per, pm in masks.items():
                    for cond, cm in {"all": np.ones(len(y), bool), "work_dayshift": grp == 1,
                                     "other": grp == 0, "peak_y>=T": (y.to_numpy() >= T_arr)}.items():
                        m = pm & usable & cm
                        if m.sum() < 30:
                            continue
                        r = MT.interval_score(y[m], iv_["lo"][m], iv_["hi"][m], alpha)
                        rows.append(dict(task=task, alpha=alpha, method=vname, period=per, cond=cond, **r))
            for per, pm in masks.items():
                b = coverage_gain_bootstrap(y, variants, grp, pm & usable, alpha)
                cov_boot.append(dict(task=task, alpha=alpha, period=per, cond="work_dayshift",
                                     comparison="rolling_mondrian - rolling_global", **{k: (str(v) if isinstance(v, list) else v)
                                                                                        for k, v in b.items()}))
    io.write_csv(pd.DataFrame(rows), od / "interval_coverage.csv")
    io.write_csv(pd.DataFrame(cov_boot), od / "interval_coverage_gain_bootstrap.csv")

    # ---- 다음 1시간 최대 초과확률(C-A)
    labels = PK.next_hour_labels(y, usable)
    lab_T = labels["max_next"].to_numpy() >= T_arr
    grp_issue = PK.target_window_groups(grp)  # 목표 창(다음 1시간) 기준 체제
    prob_res = pd.Series(np.nan, index=idx)
    for name, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        T = CV.peak_threshold(iv, s if name != "test" else C.TEST_START)
        p = PK.next_hour_prob(idx, preds_h, y, T, grp_issue)
        m = (idx >= s) & (idx < e)
        prob_res[m] = p[m]
    Xc = classifier_frame(frames)
    prob_clf = run_classifier(iv, Xc, labels, T_arr)
    rule_persist = (y.to_numpy() >= T_arr).astype(float)
    an_next = Xc["analog_next_max"].to_numpy()
    rule_analog = (an_next >= T_arr - 5).astype(float)
    tgt_hour = ((idx + pd.Timedelta(minutes=15)).hour)
    reg_day = st["regime"].reindex((idx + pd.Timedelta(minutes=15)).normalize()).to_numpy()
    rule_clock = ((reg_day == 2) & (tgt_hour >= 8) & (tgt_hour < 16)).astype(float)
    reg_slot = st["regime"].reindex(idx.normalize()).to_numpy()
    rule_clock_slot = ((reg_slot == 2) & (idx.hour >= 8) & (idx.hour < 16)).astype(float)
    prob_clim = climatology_prob(iv, labels, st["regime"])
    probs = {"P_residual_sim": prob_res, "P_lgbm_classifier": prob_clf, "P_climatology": prob_clim,
             "R_persistence": pd.Series(rule_persist, index=idx), "R_analog": pd.Series(rule_analog, index=idx),
             "R_clock": pd.Series(rule_clock, index=idx)}
    valid = labels["valid"].to_numpy()
    # 모든 방법이 같은 행에서 평가되도록 공통 행(두 확률이 모두 있는 발행 구간)만 쓴다
    common = valid & np.isfinite(prob_res.to_numpy()) & np.isfinite(prob_clf.to_numpy())
    crow, arows = [], []
    brier_clim = {}
    for per, pm in masks.items():
        m = pm & common
        brier_clim[per] = MT.classification(lab_T[m].astype(int), prob_clim.to_numpy()[m], 0.5).get("Brier")
    for pname, p in probs.items():
        for per, pm in masks.items():
            m = pm & common
            if m.sum() == 0:
                continue
            c = MT.classification(lab_T[m].astype(int), p.to_numpy()[m], 0.5)
            bss = 1 - c["Brier"] / brier_clim[per] if c.get("Brier") is not None and brier_clim[per] else np.nan
            crow.append(dict(method=pname, period=per, tau=0.5, tau_rule="rule" if pname.startswith("R_") else "fixed_0.5",
                             base_rate=c["pos"] / c["n"], BSS_vs_climatology=bss, **c))
    # 확률 방법 선택: 공통 행 교차검증 Brier 최소(사전 규칙). 기후값은 비교 기준이라 후보가 아니다
    briers = {r["method"]: r.get("Brier", np.nan) for r in crow
              if r["period"] == "cv" and r["method"] in ("P_residual_sim", "P_lgbm_classifier")}
    prob_method = min(briers, key=lambda k: briers[k] if np.isfinite(briers[k]) else np.inf)
    p_star = probs[prob_method]
    # 확률 보정 판정: 교차검증 ECE가 0.02를 넘으면 등방 회귀 보정(교차검증 OOF로 적합, 시험에 적용)
    ece_cv = [r["ECE"] for r in crow if r["period"] == "cv" and r["method"] == prob_method][0]
    calib = {"rule": "교차검증 ECE > 0.02이면 등방 회귀 보정", "cv_ECE": ece_cv, "applied": bool(ece_cv > 0.02)}
    if calib["applied"]:
        # 교차검증 구간은 폴드 교차 적합(다른 폴드로 적합해 적용), 시험은 교차검증 전체로 적합. τ도 보정된 확률로 고른다
        from sklearn.isotonic import IsotonicRegression
        pv0 = p_star.to_numpy()
        pv = np.full(len(pv0), np.nan)
        for _, s, e in CV.cv_blocks():
            fit_m = masks["cv"] & common & ~((idx >= s) & (idx < e))
            app = (idx >= s) & (idx < e) & np.isfinite(pv0)
            iso = IsotonicRegression(out_of_bounds="clip").fit(pv0[fit_m], lab_T[fit_m].astype(float))
            pv[app] = iso.predict(pv0[app])
        iso = IsotonicRegression(out_of_bounds="clip").fit(pv0[masks["cv"] & common], lab_T[masks["cv"] & common].astype(float))
        mt = masks["test"] & np.isfinite(pv0)
        pv[mt] = iso.predict(pv0[mt])
        p_star = pd.Series(pv, index=idx)
        prob_method = prob_method + "_isotonic"
        probs[prob_method] = p_star
    res["prob_method"] = {"chosen": prob_method, "cv_brier_common_rows": briers, "calibration": calib}
    # 문턱: (1) 교차검증 F1 최대(주 운영점), (2) 시각 규칙과 같은 경보 시간(교차검증에서 맞춤)
    clock_cv = _alarm_eval(probs["R_clock"], labels, y, usable, T_arr, 0.5, masks["cv"] & common)
    tau_sel = {}
    for pname in dict.fromkeys(("P_residual_sim", "P_lgbm_classifier", "P_climatology", prob_method)):
        p = probs[pname]
        mcv = masks["cv"] & common
        f1_tau, _ = MT.best_f1_threshold(lab_T[mcv].astype(int), p.to_numpy()[mcv], TAU_GRID)
        match = None
        for tau in TAU_GRID:  # 경보 시간이 시각 규칙 이하가 되는 가장 낮은 τ
            r = _alarm_eval(p, labels, y, usable, T_arr, tau, mcv)
            arows.append(dict(method=pname, period="cv", tau_rule="grid", **r))
            if match is None and r["alarm_on_hours_per_day"] <= clock_cv["alarm_on_hours_per_day"]:
                match = float(tau)
        tau_sel[pname] = {"tau_f1": f1_tau, "tau_match_clock_hours": match,
                          "clock_alarm_on_hours_per_day_cv": clock_cv["alarm_on_hours_per_day"]}
        for label, tau in (("f1", f1_tau), ("match_clock_hours", match)):
            if tau is None:
                continue
            for per in ("cv", "test"):
                r = _alarm_eval(p, labels, y, usable, T_arr, tau, masks[per] & common)
                arows.append(dict(method=pname, period=per, tau_rule=label, **r))
    # 분류표: 확률 방법마다 자기 교차검증 F1 문턱 행(τ=0.5 고정 행은 기후값처럼 낮은 확률을 내는 방법의 F1을 깎는다)
    for pname in tau_sel:
        for per, pm in masks.items():
            m = pm & common
            c = MT.classification(lab_T[m].astype(int), probs[pname].to_numpy()[m], tau_sel[pname]["tau_f1"])
            bss = 1 - c["Brier"] / brier_clim[per] if c.get("Brier") is not None and brier_clim[per] else np.nan
            crow.append(dict(method=pname, period=per, tau=tau_sel[pname]["tau_f1"], tau_rule="cv_f1",
                             base_rate=c["pos"] / c["n"], BSS_vs_climatology=bss, **c))
    for rname in ("R_persistence", "R_analog", "R_clock"):
        for per in ("cv", "test"):
            r = _alarm_eval(probs[rname], labels, y, usable, T_arr, 0.5, masks[per] & common)
            arows.append(dict(method=rname, period=per, tau_rule="rule", **r))
    # 사건 병합 간격 민감도(선택 방법·F1 문턱): 0·15·30분
    tau_main = tau_sel[prob_method]["tau_f1"]
    for gap in (0, 1, 2):
        for pname, tau, rule in ((prob_method, tau_main, "f1"), ("R_clock", 0.5, "rule")):
            for per in ("cv", "test"):
                r = _alarm_eval(probs[pname], labels, y, usable, T_arr, tau, masks[per] & common, merge_gap=gap)
                arows.append(dict(method=pname, period=per, tau_rule=f"{rule}_mergegap{gap * 15}min", **r))
    # F1 차이 부트스트랩: 선택 방법(F1 문턱) vs 시각 규칙·기후값 확률(각 CV F1 문턱)
    fb = []
    tau_c = tau_sel["P_climatology"]["tau_f1"]
    for other, pb, tb in (("R_clock", probs["R_clock"].to_numpy(), 0.5), ("P_climatology", prob_clim.to_numpy(), tau_c)):
        for per in ("cv", "test"):
            for bd in (1, 7):
                b = f1_difference_bootstrap(lab_T, np.nan_to_num(p_star.to_numpy(), nan=-1), tau_sel[prob_method]["tau_f1"],
                                            np.nan_to_num(pb, nan=-1), tb, masks[per] & common, idx, bd)
                fb.append(dict(method=prob_method, vs=other, period=per, block_days=bd, F1_diff=b["F1_diff"],
                               ci90=str(b["ci90"]), n_days=b["n_days"]))
    io.write_csv(pd.DataFrame(fb), od / "next_hour_f1_bootstrap.csv")
    io.write_csv(prob_quality_bootstrap(lab_T, probs, prob_method, masks, common, idx), od / "next_hour_prob_quality_bootstrap.csv")
    ct, rel = calibration_table(lab_T, {k: probs[k] for k in ("P_residual_sim", "P_lgbm_classifier", "P_climatology")},
                                masks, common)
    io.write_csv(ct, od / "next_hour_calibration.csv")
    io.write_csv(rel, od / "next_hour_reliability.csv")
    # 시험 구간 예측 결과 파일(제출물 '테스트데이터 예측결과'): 선택 모델·확률·경보·예측구간
    ivB = PK.rolling_intervals(y, pred_B, grp, 0.2, known_before=KNOWN_B)
    ivA = PK.rolling_intervals(y, preds_h[4], grp, 0.2, known_before=KNOWN_A)
    te = masks["test"]
    out = pd.DataFrame({
        "interval_start": idx[te], "actual": y.to_numpy()[te], "usable": usable[te],
        f"dayahead_{mB}": pred_B.to_numpy()[te], "dayahead_lo80": ivB["lo"].to_numpy()[te],
        "dayahead_hi80": ivB["hi"].to_numpy()[te],
        **{f"intraday_h{h}_{mA}": preds_h[h].to_numpy()[te] for h in range(1, 5)},
        "intraday_h4_lo80": ivA["lo"].to_numpy()[te], "intraday_h4_hi80": ivA["hi"].to_numpy()[te],
        "p_next_hour_peak": p_star.to_numpy()[te],
        "alarm_next_hour": np.where(np.isfinite(p_star.to_numpy()[te]), (p_star.to_numpy()[te] >= tau_main).astype(float), np.nan),
        "peak_T": T_arr[te],
    })
    io.write_csv(out, io.out_dir("test") / "predictions_test.csv")
    cols_doc = [
        ("interval_start", "행 색인: 15분 구간 시작 시각(값은 구간 종료 뒤 확인)"),
        ("actual", "실측 15분 최대수요전력(원자료 단위)"), ("usable", "평가 가능 구간(정전·결측이면 False)"),
        (f"dayahead_{mB}", "익일 예측(발행 D-1 17:00), 이 구간(목표)의 값"),
        ("dayahead_lo80, dayahead_hi80", "익일 예측 80% 구간(롤링 Mondrian conformal)"),
        (f"intraday_h1..h4_{mA}", "실시간 예측: 이 구간(목표)을 15·30·45·60분 전에 발행한 값"),
        ("intraday_h4_lo80, intraday_h4_hi80", "60분 전 예측의 80% 구간"),
        ("p_next_hour_peak", "발행 구간 기준: 이 구간 종료 시점에 발행한 '다음 1시간(다음 네 구간) 최대 ≥ peak_T' 확률"),
        ("alarm_next_hour", "p_next_hour_peak ≥ τ(교차검증 F1 최대)이면 1, 확률 결측이면 빈칸"),
        ("peak_T", "피크 기준(시험 시작 전 학습 가능 구간 q95)"),
    ]
    io.write_csv(pd.DataFrame(cols_doc, columns=["column", "meaning"]), io.out_dir("test") / "test_prediction_columns.csv")
    C.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"P_residual_sim": prob_res, "P_lgbm_classifier": prob_clf, "P_climatology": prob_clim,
                  **({prob_method: p_star} if prob_method not in ("P_residual_sim", "P_lgbm_classifier") else {}),
                  "R_clock": probs["R_clock"], "R_analog": probs["R_analog"], "label": lab_T.astype(float),
                  "valid": valid, "common": common, "T": T_arr}).to_csv(C.ARTIFACT_DIR / "next_hour_prob.csv.gz",
                                                                     float_format="%.5f")
    io.write_csv(pd.DataFrame(crow), od / "next_hour_classification.csv")
    io.write_csv(pd.DataFrame(arows), od / "next_hour_alarms.csv")
    res["tau"] = tau_sel

    # ---- 익일 최대 ≥ T, 월 누적 최대 경신
    drows = []
    day_tables = []
    slot_rows = []
    for name, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        T = CV.peak_threshold(iv, s if name != "test" else C.TEST_START)
        dp, slot_p = PK.day_max_prob(pred_B, y, usable, T, st["regime"])
        msl = (idx >= s) & (idx < e) & usable & np.isfinite(slot_p.to_numpy())
        slot_rows.append(pd.DataFrame({"ts": idx[msl], "period": "test" if name == "test" else "cv", "p": slot_p.to_numpy()[msl],
                                       "rule": rule_clock_slot[msl], "label": (y.to_numpy()[msl] >= T).astype(int)}))
        dp = dp[(dp["date"] >= s) & (dp["date"] < e)].copy()
        dp["period"] = "test" if name == "test" else "cv"
        dp["T"] = T
        # 규칙: 전면 가동일, 유사일 일 최대 ≥ T
        dp["rule_fullday"] = (st["regime"].reindex(dp["date"]).to_numpy() == 2).astype(float)
        an_day = frames["B"]["analog_mean"].groupby(frames["B"].index.normalize()).max()
        dp["rule_analog"] = (an_day.reindex(dp["date"]).to_numpy() >= T).astype(float)
        day_tables.append(dp)
    days = pd.concat(day_tables, ignore_index=True)
    days = _add_mtd(days, y, usable, pred_B, st["regime"])
    for per in ("cv", "test"):
        d = days[(days.period == per) & days.label.notna()]
        for col in ("p_daymax", "rule_fullday", "rule_analog"):
            c = MT.classification(d["label"].astype(int), d[col], 0.5)
            drows.append(dict(target="daymax>=T", method=col, period=per, base_rate=c["pos"] / c["n"], **c))
        d2 = d[d["mtd_label"].notna()]
        for col in ("p_new_mtd", "rule_fullday"):
            c = MT.classification(d2["mtd_label"].astype(int), d2[col], 0.5)
            drows.append(dict(target="new_month_max", method=col, period=per, base_rate=c["pos"] / c["n"], **c))
        # 고위험일 순위: 예측 일 최대 상위 k일 중 실제 상위 k일 비율
        for k in (5, 10):
            if len(d) >= k:
                top_pred = set(d.nlargest(k, "pred_daymax")["date"])
                top_true = set(d.nlargest(k, "y_daymax")["date"])
                drows.append(dict(target=f"top{k}_days", method="pred_daymax_rank", period=per,
                                  precision_at_k=len(top_pred & top_true) / k))
    # 일 최대 크기 예측(순위·오차): 가동일만
    for per in ("cv", "test"):
        d = days[(days.period == per) & days.y_daymax.notna() & (days.rule_fullday == 1)]
        if len(d) >= 5:
            drows.append(dict(target="workday_daymax_error", method="pred_daymax", period=per, n=len(d),
                              daymax_MAE=float((d.pred_daymax - d.y_daymax).abs().mean()),
                              daymax_bias=float((d.pred_daymax - d.y_daymax).mean()),
                              spearman=float(d[["pred_daymax", "y_daymax"]].corr(method="spearman").iloc[0, 1])))
    # 피크 기준 민감도: q90·q97.5에서 잔차 표집 확률 vs 규칙(τ는 각 기준의 교차검증 F1 최대)
    srows = []
    for q in C.PEAK_Q_SENS + (C.PEAK_Q,):
        pq = pd.Series(np.nan, index=idx)
        Tq = np.full(len(idx), np.nan)
        for name, s0, e0 in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
            T = CV.peak_threshold(iv, s0 if name != "test" else C.TEST_START, q=q)
            m = (idx >= s0) & (idx < e0)
            pq[m] = PK.next_hour_prob(idx, preds_h, y, T, grp_issue)[m]
            Tq[m] = T
        labq = labels["max_next"].to_numpy() >= Tq
        rq = {"P_residual_sim": pq, "R_persistence": pd.Series((y.to_numpy() >= Tq).astype(float), index=idx),
              "R_analog": pd.Series((an_next >= Tq - 5).astype(float), index=idx), "R_clock": probs["R_clock"]}
        mcv = masks["cv"] & common & np.isfinite(pq.to_numpy())
        tq, _ = MT.best_f1_threshold(labq[mcv].astype(int), pq.to_numpy()[mcv], TAU_GRID)
        for pname, p in rq.items():
            for per, pm in masks.items():
                m = pm & common & np.isfinite(pq.to_numpy())
                tau = tq if pname.startswith("P_") else 0.5
                c = MT.classification(labq[m].astype(int), p.to_numpy()[m], tau)
                srows.append(dict(peak_q=q, method=pname, period=per, tau=tau, base_rate=c["pos"] / c["n"],
                                  **{k: c.get(k) for k in ("n", "pos", "precision", "recall", "F1", "PR_AUC", "Brier")}))
    io.write_csv(pd.DataFrame(srows), od / "next_hour_threshold_sensitivity.csv")
    sl = pd.concat(slot_rows, ignore_index=True)
    sl.to_csv(C.ARTIFACT_DIR / "dayahead_slot_prob.csv.gz", float_format="%.5f", index=False)
    for per in ("cv", "test"):
        d = sl[sl.period == per]
        mcv = sl[sl.period == "cv"]
        tau_s, _ = MT.best_f1_threshold(mcv["label"].to_numpy(), mcv["p"].to_numpy(), TAU_GRID)
        for col, tau in (("p", tau_s), ("rule", 0.5)):
            c = MT.classification(d["label"].to_numpy(), d[col].to_numpy(), tau)
            drows.append(dict(target="slot_y>=T_dayahead", method="p_slot_residual_sim" if col == "p" else "rule_fullday_0800_1600",
                              period=per, base_rate=c["pos"] / c["n"], tau=tau, **c))
    # 월 최대수요 예측: 익일 예측(발행 D-1 17:00)의 월 최대 vs 실측 월 최대(요금 기준 목표의 예측 오차)
    mrows = []
    yv_u = y.where(pd.Series(usable, index=idx))
    for per, pm in masks.items():
        for mth in sorted(np.unique(idx[pm].month)):
            mm = pm & (idx.month == mth)
            ya, pa = yv_u[mm], pred_B[mm]
            if ya.notna().sum() == 0 or pa.notna().sum() == 0:
                continue
            mrows.append(dict(period=per, month=int(mth), actual_month_max=float(ya.max()), actual_at=str(ya.idxmax()),
                              pred_month_max=float(pa.max()), pred_at=str(pa.idxmax()),
                              error=float(pa.max() - ya.max()),
                              pred_at_actual_peak_time=float(pa.get(ya.idxmax(), np.nan))))
    io.write_csv(pd.DataFrame(mrows), od / "month_max_prediction.csv")
    io.write_csv(days, od / "day_level.csv")
    io.write_csv(pd.DataFrame(drows), od / "day_level_metrics.csv")
    io.write_json(res, od / "peak_summary.json")
    return res


def _alarm_eval(p, labels, y, usable, T_arr, tau, mask, merge_gap: int = 1):
    """폴드(기준 T가 같은 기간)별로 평가해 합산한다. 선행시간 중앙값은 모든 사건을 합친 값."""
    rows = []
    for _, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        m = mask & (y.index >= s) & (y.index < e)
        if not m.any():
            continue
        T = float(np.nanmax(T_arr[m]))
        rows.append(PK.evaluate_alarms(p, labels, y, usable, T, tau, m, merge_gap=merge_gap))
    if not rows:
        return {}
    keys = ("n_issue", "pos", "TP", "FP", "FN", "events", "events_detected", "events_scheduled", "detected_scheduled",
            "events_unscheduled", "detected_unscheduled", "alarm_episodes", "false_episodes", "days")
    agg = {k: sum(r[k] for r in rows) for k in keys}
    prec = agg["TP"] / (agg["TP"] + agg["FP"]) if agg["TP"] + agg["FP"] else np.nan
    rec = agg["TP"] / (agg["TP"] + agg["FN"]) if agg["TP"] + agg["FN"] else np.nan
    leads = [v for r in rows for v in r["leads"]]
    leads_ep = [v for r in rows for v in r["leads_episode"]]
    on_hours = sum(r["alarm_on_hours_per_day"] * r["days"] for r in rows if np.isfinite(r["alarm_on_hours_per_day"]))
    return dict(tau=tau, **agg, precision=prec, recall=rec,
                F1=2 * prec * rec / (prec + rec) if agg["TP"] else 0.0,
                event_recall=agg["events_detected"] / agg["events"] if agg["events"] else np.nan,
                event_recall_scheduled=agg["detected_scheduled"] / agg["events_scheduled"] if agg["events_scheduled"] else np.nan,
                event_recall_unscheduled=agg["detected_unscheduled"] / agg["events_unscheduled"] if agg["events_unscheduled"] else np.nan,
                lead_median_min=float(np.median(leads)) if leads else np.nan,
                lead_episode_median_min=float(np.median(leads_ep)) if leads_ep else np.nan,
                lead_episode_p25_p75=(str([float(np.quantile(leads_ep, 0.25)), float(np.quantile(leads_ep, 0.75))])
                                      if leads_ep else ""),
                alarm_on_hours_per_day=on_hours / agg["days"] if agg["days"] else np.nan,
                episodes_per_day=agg["alarm_episodes"] / agg["days"] if agg["days"] else np.nan,
                false_episodes_per_day=agg["false_episodes"] / agg["days"] if agg["days"] else np.nan)


def _add_mtd(days: pd.DataFrame, y: pd.Series, usable: np.ndarray, pred_B: pd.Series,
             regime: pd.Series) -> pd.DataFrame:
    """월 누적 최대 경신: 기준 R = 그달 1일부터 D-2까지의 관측 최대(발행 D-1 17:00 기준으로 확정된 날).

    D-1은 발행 시점에 끝나지 않았으므로 16:45까지의 최대를 함께 반영한다. 매월 1일은 정의하지 않는다.
    확률 = day_max_prob와 같은 잔차 표집으로 max_s(ŷ_s + e_s) > R 인 비율.
    """
    yv = y.where(usable)
    day_key = yv.index.normalize()
    dmax = yv.groupby(day_key).max()
    part = yv[yv.index.hour < 17]
    dmax_part = part.groupby(part.index.normalize()).max()
    out = days.copy()
    R = {}
    for d in out["date"]:
        m0 = d.replace(day=1)
        full = dmax[(dmax.index >= m0) & (dmax.index < d - pd.Timedelta(days=1))].dropna()
        prev = dmax_part.get(d - pd.Timedelta(days=1), np.nan) if (d - pd.Timedelta(days=1)) >= m0 else np.nan
        vals = list(full.values) + ([prev] if np.isfinite(prev) else [])
        R[d] = float(max(vals)) if vals else np.nan
    Rs = pd.Series(R)
    out["mtd_ref"] = out["date"].map(Rs)
    out["mtd_label"] = [float(yd > r) if np.isfinite(r) and np.isfinite(yd) else np.nan
                        for yd, r in zip(out["y_daymax"], out["mtd_ref"])]
    dp, _ = day_max_prob_T(pred_B, y, usable, regime, Rs + 1e-9)
    out["p_new_mtd"] = out["date"].map(dp.set_index("date")["p_daymax"]) if len(dp) else np.nan
    return out


def day_max_prob_T(pred_B, y, usable, regime, T_by_date):
    return PK.day_max_prob(pred_B, y, usable, np.nan, regime, T_by_date=T_by_date)
