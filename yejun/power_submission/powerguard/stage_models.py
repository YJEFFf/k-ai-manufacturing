"""S2~S4: 교차검증 비교 → 사전 규칙으로 주 모델 선택 → 시험 구간 주간 재학습 예측·평가."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import config as C
from . import cv as CV
from . import features as F
from . import models as M
from . import io
from . import metrics as MT
from . import registry as R

TASKS = ["B", "A1", "A2", "A3", "A4"]


def _family(task: str) -> str:
    return "A" if task.startswith("A") else "B"


def work_dayshift(iv: pd.DataFrame) -> np.ndarray:
    """전면 가동일(체제 2)의 08~20시 구간."""
    reg = F.schedule_table(iv)["regime"].reindex(iv.index.normalize()).to_numpy()
    h = iv["hour"].to_numpy()
    return (reg == 2) & (h >= 8) & (h < 20)


def _threshold_array(iv: pd.DataFrame, index: pd.DatetimeIndex) -> np.ndarray:
    """구간별 피크 기준 T: 교차검증 폴드는 폴드 시작 전 학습 q95, 시험은 시험 시작 전 q95."""
    T = np.full(len(index), np.nan)
    for _, s, e in CV.cv_blocks() + [("test", C.TEST_START, C.TEST_END)]:
        T[(index >= s) & (index < e)] = CV.peak_threshold(iv, s)
    return T


def _scores(y, p, usable, iv, rows, task, model, split_blocks, work=None, Tarr=None):
    work = work_dayshift(iv) if work is None else work
    Tarr = _threshold_array(iv, y.index) if Tarr is None else Tarr
    for name, s, e in split_blocks:
        ev = CV.eval_mask(y.index, usable, s, e) & np.isfinite(p.to_numpy())
        if not ev.any():
            continue
        Tv = Tarr[ev]
        r = MT.regression(y[ev], p[ev], T=Tv, mask_work=work[ev])
        c = MT.classification((y[ev].to_numpy() >= Tv).astype(int), (p[ev].to_numpy() >= Tv).astype(float), 0.5)
        extra = {}
        if task == "B":
            dp = MT.daily_peak(pd.DataFrame({"y": y[ev], "p": p[ev]}), "p")
            extra = {k: dp.get(k) for k in ("daymax_MAE", "daymax_bias", "peak_slot_hit_pm1")}
        rows.append(dict(task=task, model=model, split=name, T=float(np.nanmax(Tv)) if name != "pooled" else np.nan,
                         **r, **extra,
                         n_missing_pred=int((CV.eval_mask(y.index, usable, s, e) & ~np.isfinite(p.to_numpy())).sum()),
                         peak_precision=c["precision"], peak_recall=c["recall"], peak_F1=c["F1"]))


def run_cv_all(iv: pd.DataFrame, frames: dict, log=print, candidates=None) -> tuple[pd.DataFrame, dict]:
    """candidates: {'A': [...], 'B': [...]}로 후보를 줄일 수 있다(절제 실험용)."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    work = work_dayshift(iv)
    rows, oof = [], {}
    blocks = CV.cv_blocks()
    pooled_block = [("pooled", C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2])]
    for task in TASKS:
        X = frames[task]
        oof[task] = {}
        for model, fac in R.candidates(_family(task)).items():
            if candidates is not None and model not in candidates[_family(task)]:
                continue
            t0 = time.time()
            p = CV.run_cv(X, iv, fac, _family(task))
            oof[task][model] = p
            _scores(y, p, usable, iv, rows, task, model, blocks + pooled_block, work=work)
            log(f"  CV {task} {model} {time.time() - t0:.1f}s")
    cvm = pd.DataFrame(rows)
    return cvm, oof


def blend_members(rank: pd.Series) -> list[str]:
    """pooled RMSE 순위에서 기준모델이 아닌 최선 모델과, 그와 다른 계열의 최선 모델(v2.0)."""
    cand = [m for m in rank.index if not m.startswith("BL") and m != "M8_blend"]
    first = cand[0]
    second = next((m for m in cand[1:] if R.family(m) != R.family(first)), cand[1])
    return [first, second]


def add_blend(cvm: pd.DataFrame, oof: dict, iv: pd.DataFrame, family_tasks: list[str]) -> tuple[pd.DataFrame, dict]:
    """가족(A 또는 B)별 pooled RMSE 기준 서로 다른 계열 상위 2개 모델의 동일 가중 평균을 M8_blend로 추가한다."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    sub = cvm[(cvm.task.isin(family_tasks)) & (cvm.split == "pooled")]
    rank = sub.groupby("model")["RMSE"].mean().sort_values()
    top2 = blend_members(rank)
    rows = []
    blocks = CV.cv_blocks() + [("pooled", C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2])]
    corrs = []
    for task in family_tasks:
        p = (oof[task][top2[0]] + oof[task][top2[1]]) / 2
        oof[task]["M8_blend"] = p
        _scores(y, p, usable, iv, rows, task, "M8_blend", blocks)
        ra, rb = (oof[task][top2[0]] - y), (oof[task][top2[1]] - y)
        ok = ra.notna() & rb.notna() & pd.Series(usable, index=y.index)
        corrs.append(float(np.corrcoef(ra[ok], rb[ok])[0, 1]))
    return pd.concat([cvm, pd.DataFrame(rows)], ignore_index=True), {"members": top2,
                                                                    "cv_residual_corr": float(np.mean(corrs))}


def select(cvm: pd.DataFrame, oof: dict, iv: pd.DataFrame, family_tasks: list[str], seed: int = 0,
           n_boot: int = 2000) -> dict:
    """사전 고정 선택 규칙(PLAN §4).

    1) pooled OOF RMSE(A는 네 지평 평균) 최소 모델 m*.
    2) m*보다 단순한 등급 중 RMSE 최소 모델 c*와 날짜 블록 부트스트랩(2,000회) 비교.
       RMSE 차이의 90% 구간이 0을 포함하면: B는 일 최대 절대오차로 2차 비교해 m*가 유의하게 좋으면 유지,
       아니면 c*로 내려가 같은 비교를 반복한다. A는 바로 c*로 내려간다.
    """
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    mask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        mask |= CV.eval_mask(y.index, usable, s, e)
    sub = cvm[cvm.task.isin(family_tasks)]
    pooled = sub[sub.split == "pooled"].groupby("model")["RMSE"].mean().sort_values()
    last_fold = C.CV_FOLDS[-1][0]
    v3 = sub[sub.split == last_fold].groupby("model")["RMSE"].mean()
    trail = []
    cur = pooled.index[0]
    while True:
        simpler = [m for m in pooled.index if R.complexity(m) < R.complexity(cur)]
        if not simpler:
            break
        c = min(simpler, key=lambda m: pooled[m])
        if len(family_tasks) == 1:
            t = family_tasks[0]
            bt = MT.paired_day_bootstrap(y, oof[t][cur], oof[t][c], mask, stat="RMSE", seed=seed, n_boot=n_boot)
        else:
            bt = MT.multi_bootstrap_rmse(y, [oof[t][cur] for t in family_tasks], [oof[t][c] for t in family_tasks], mask,
                                         seed=seed, n_boot=n_boot)
        step = {"model": cur, "vs_simpler": c, "rmse_boot": bt}
        sig = bt["ci90"][1] < 0
        if not sig and family_tasks == ["B"]:
            bd = MT.paired_day_bootstrap(y, oof["B"][cur], oof["B"][c], mask, stat="daymax_MAE", seed=seed, n_boot=n_boot)
            step["daymax_boot"] = bd
            sig = bd["ci90"][1] < 0
        step["keep"] = bool(sig)
        trail.append(step)
        if sig:
            break
        cur = c
    # v1 규칙(2차 기준 없이 RMSE 부트스트랩만)이었다면의 선택: v1.1의 과제 B 2차 기준은 교차검증 비교를 본 뒤 추가됨
    v1 = pooled.index[0]
    while True:
        simpler = [m for m in pooled.index if R.complexity(m) < R.complexity(v1)]
        if not simpler:
            break
        c = min(simpler, key=lambda m: pooled[m])
        if len(family_tasks) == 1:
            bt = MT.paired_day_bootstrap(y, oof[family_tasks[0]][v1], oof[family_tasks[0]][c], mask, stat="RMSE",
                                         seed=seed, n_boot=n_boot)
        else:
            bt = MT.multi_bootstrap_rmse(y, [oof[t][v1] for t in family_tasks], [oof[t][c] for t in family_tasks], mask,
                                         seed=seed, n_boot=n_boot)
        if bt["ci90"][1] < 0:
            break
        v1 = c
    return {"chosen": cur, "v1_rule_choice": v1,
            "rule": "pooled RMSE 최소 → 더 단순한 등급 최선 모델과 날짜 부트스트랩(90%) 비교, "
                    "B는 동률 시 일 최대 오차로 2차 비교(v1.1, 교차검증 비교 후 추가)",
            "bootstrap": {"seed": seed, "n_boot": n_boot},
            "trail": trail, "pooled_RMSE": pooled.round(4).to_dict(),
            f"{last_fold}_RMSE": v3.sort_values().round(4).to_dict()}


def selection_robustness(cvm: pd.DataFrame, oof: dict, iv: pd.DataFrame, seeds=range(20), n_boot_big: int = 20000) -> pd.DataFrame:
    """선택 규칙의 부트스트랩 난수·반복 수 민감도(헤드라인은 seed 0·2,000회로 사전 고정)."""
    rows = []
    for fam, tasks in (("B", ["B"]), ("A", ["A1", "A2", "A3", "A4"])):
        for seed in seeds:
            s = select(cvm, oof, iv, tasks, seed=seed, n_boot=2000)
            rows.append(dict(family=fam, seed=seed, n_boot=2000, chosen=s["chosen"], v1_rule_choice=s["v1_rule_choice"],
                             first_step_ci90_hi=s["trail"][0]["rmse_boot"]["ci90"][1] if s["trail"] else np.nan))
        s = select(cvm, oof, iv, tasks, seed=0, n_boot=n_boot_big)
        rows.append(dict(family=fam, seed=0, n_boot=n_boot_big, chosen=s["chosen"], v1_rule_choice=s["v1_rule_choice"],
                         first_step_ci90_hi=s["trail"][0]["rmse_boot"]["ci90"][1] if s["trail"] else np.nan))
    return pd.DataFrame(rows)


ML_GRID = [  # (이름, LightGBM 설정 덮어쓰기, 목적함수) — 교차검증 전용 민감도. 헤드라인 M1 = 기본값
    ("default_huber", {}, "huber"),
    ("leaves7_min100", dict(num_leaves=7, min_child_samples=100), "huber"),
    ("leaves15_min50", dict(num_leaves=15, min_child_samples=50), "huber"),
    ("leaves63_min20", dict(num_leaves=63, min_child_samples=20), "huber"),
    ("leaves31_min100", dict(num_leaves=31, min_child_samples=100), "huber"),
    ("default_l2", {}, "regression"),
]


def ml_sweep(iv: pd.DataFrame, frames: dict, log=print) -> pd.DataFrame:
    """LightGBM 소형 격자(교차검증 pooled). 교차검증 최선 설정의 시험 성능도 함께 기록한다(선택에는 쓰지 않음)."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    cvmask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        cvmask |= CV.eval_mask(y.index, usable, s, e)
    temask = CV.eval_mask(y.index, usable, C.TEST_START, C.TEST_END)
    rows = []
    for task in ("B", "A4"):
        fam = _family(task)
        feats = F.feature_list(fam)
        res = []
        for name, params, obj in ML_GRID:
            fac = lambda p=params, o=obj: M.gated(M.LGBModel(feats, params=p, objective=o,
                                                             alpha=10.0 if o == "huber" else None), fam)
            pc = CV.run_cv(frames[task], iv, fac, fam)
            res.append((name, fac, MT.regression(y[cvmask], pc[cvmask])["RMSE"]))
            log(f"  ml-sweep {task} {name}")
        best = min(res, key=lambda r: r[2])
        for name, fac, cv_rmse in res:
            row = dict(task=task, config=name, cv_RMSE=cv_rmse, cv_best=name == best[0], test_RMSE=np.nan)
            if name in (best[0], "default_huber"):
                pt = CV.run_test(frames[task], iv, fac, fam)
                row["test_RMSE"] = MT.regression(y[temask], pt[temask])["RMSE"]
            rows.append(row)
    return pd.DataFrame(rows)


def structural_sweep(iv: pd.DataFrame) -> pd.DataFrame:
    """구조 모델 초모수 탐색 기록(교차검증 pooled): 체제별 유사일 k, 유사일 수준 보정 ρ."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    mask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        mask |= CV.eval_mask(y.index, usable, s, e)
    st = F.schedule_table(iv)
    rows = []
    for k in (1, 2, 3, 4):
        X = F.dayahead_features(iv, st, issue_hour=17, analog_k=k)
        p = CV.run_cv(X, iv, lambda: M.AnalogDay("analog_regime"), "B")
        r = MT.regression(y[mask], p[mask])
        rows.append(dict(task="B", model="BL5_regime_analog", param="k", value=k, RMSE=r["RMSE"], MAE=r["MAE"]))
    xmid = F.dayahead_features(iv, st, issue_hour=24)
    for rho in (0.8, 0.85, 0.9, 0.95, 1.0):
        vals = []
        for h in (1, 2, 3, 4):
            X = F.intraday_features(iv, h, xmid)
            p = CV.run_cv(X, iv, lambda rho=rho: M.AnalogLevel(rho), "A")
            vals.append(MT.regression(y[mask], p[mask])["RMSE"])
        rows.append(dict(task="A(mean h1-4)", model="M6_analog_level", param="rho", value=rho,
                         RMSE=float(np.mean(vals)), MAE=np.nan))
    return pd.DataFrame(rows)


def run_test_all(iv: pd.DataFrame, frames: dict, models_by_task: dict, blend_members: dict,
                 weekly: bool = True, log=print) -> tuple[pd.DataFrame, dict]:
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    rows, preds = [], {}
    tb = [("test", C.TEST_START, C.TEST_END)]
    for task in TASKS:
        X = frames[task]
        fam = _family(task)
        reg = R.candidates(fam)
        preds[task] = {}
        for model in models_by_task[task]:
            if model == "M8_blend":
                continue
            t0 = time.time()
            p = CV.run_test(X, iv, reg[model], fam, weekly=weekly)
            preds[task][model] = p
            _scores(y, p, usable, iv, rows, task, model, tb)
            log(f"  TEST {task} {model} {time.time() - t0:.1f}s")
        mem = blend_members[fam]
        if all(m in preds[task] for m in mem):
            p = (preds[task][mem[0]] + preds[task][mem[1]]) / 2
            preds[task]["M8_blend"] = p
            _scores(y, p, usable, iv, rows, task, "M8_blend", tb)
    return pd.DataFrame(rows), preds


def save_predictions(preds: dict, iv: pd.DataFrame, name: str) -> None:
    """행 단위 예측(모든 모델)을 artifacts/에 저장(Git 제외)."""
    C.ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for task, d in preds.items():
        df = pd.DataFrame(d)
        df.insert(0, "y", iv["y"])
        df.insert(1, "usable", iv["usable"])
        df = df[df.drop(columns=["y", "usable"]).notna().any(axis=1)]
        df.to_csv(C.ARTIFACT_DIR / f"{name}_{task}.csv.gz", float_format="%.4f")


def load_predictions(name: str, task: str) -> pd.DataFrame:
    return pd.read_csv(C.ARTIFACT_DIR / f"{name}_{task}.csv.gz", index_col=0, parse_dates=True)


def selection_table(iv: pd.DataFrame, cvm: pd.DataFrame, tm: pd.DataFrame, oof: dict, preds: dict, sel: dict) -> pd.DataFrame:
    """과제별 한 장 선택표: 교차검증 평균과 선택 모델 대비 차이(90% 구간), 시험 값과 차이, 일 최대·가동 주간·피크 지표.

    A는 네 지평 평균 RMSE(차이는 날짜 짝 부트스트랩), 보조 지표는 A4. 시험 값은 선택에 쓰지 않았다.
    """
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    cvmask = np.zeros(len(y), bool)
    for _, s, e in CV.cv_blocks():
        cvmask |= CV.eval_mask(y.index, usable, s, e)
    temask = CV.eval_mask(y.index, usable, C.TEST_START, C.TEST_END)
    rows = []
    for fam, tasks, aux in (("B", ["B"], "B"), ("A", ["A1", "A2", "A3", "A4"], "A4")):
        ch = sel[fam]["chosen"]
        models = [m for m in oof[tasks[0]] if all(m in oof[t] and m in preds[t] for t in tasks)]
        for m in models:
            cvp = cvm[(cvm.task.isin(tasks)) & (cvm.split == "pooled") & (cvm.model == m)]
            tep = tm[(tm.task.isin(tasks)) & (tm.model == m)]
            a_cv = cvm[(cvm.task == aux) & (cvm.split == "pooled") & (cvm.model == m)].iloc[0]
            a_te = tm[(tm.task == aux) & (tm.model == m)].iloc[0]
            row = dict(family=fam, model=m, complexity=R.complexity(m), model_family=R.family(m),
                       cv_RMSE=cvp["RMSE"].mean(), test_RMSE=tep["RMSE"].mean(),
                       chosen=m == ch, v1_rule_choice=m == sel[fam]["v1_rule_choice"],
                       blend_member=m in sel[fam].get("blend_members", []))
            if m != ch:
                for per, mask, src in (("cv", cvmask, oof), ("test", temask, preds)):
                    if len(tasks) == 1:
                        b = MT.paired_day_bootstrap(y, src[tasks[0]][m], src[tasks[0]][ch], mask, stat="RMSE")
                    else:
                        b = MT.multi_bootstrap_rmse(y, [src[t][m] for t in tasks], [src[t][ch] for t in tasks], mask)
                    row[f"{per}_diff_vs_chosen"] = b["diff"]
                    row[f"{per}_diff_ci90_lo"], row[f"{per}_diff_ci90_hi"] = b["ci90"]
            for per, r in (("cv", a_cv), ("test", a_te)):
                row[f"{per}_{aux}_RMSE_work"] = r.get("RMSE_work")
                row[f"{per}_{aux}_MAE_peak"] = r.get("MAE_peak")
                row[f"{per}_{aux}_bias_peak"] = r.get("bias_peak")
                row[f"{per}_{aux}_peak_recall"] = r.get("peak_recall")
                if fam == "B":
                    row[f"{per}_daymax_MAE"] = r.get("daymax_MAE")
            rows.append(row)
    return pd.DataFrame(rows).sort_values(["family", "cv_RMSE"])


def run(iv: pd.DataFrame, log=print) -> dict:
    frames = CV.build_frames(iv)
    cvm, oof = run_cv_all(iv, frames, log=log)
    blend_members, blend_corr = {}, {}
    for fam, tasks in (("B", ["B"]), ("A", ["A1", "A2", "A3", "A4"])):
        cvm, info = add_blend(cvm, oof, iv, tasks)
        blend_members[fam] = info["members"]
        blend_corr[fam] = info["cv_residual_corr"]
    sel = {fam: select(cvm, oof, iv, tasks) for fam, tasks in (("B", ["B"]), ("A", ["A1", "A2", "A3", "A4"]))}
    for fam in sel:
        sel[fam]["blend_members"] = blend_members[fam]
        sel[fam]["blend_members_cv_residual_corr"] = blend_corr[fam]
    od = io.out_dir("cv")
    io.write_csv(cvm, od / "cv_metrics.csv")
    io.write_csv(structural_sweep(iv), od / "structural_sweep.csv")
    io.write_json(sel, od / "selection.json")
    save_predictions(oof, iv, "oof")

    models_by_task = {t: list(oof[t].keys()) for t in TASKS}
    tm, preds = run_test_all(iv, frames, models_by_task, blend_members, weekly=True, log=log)
    tdir = io.out_dir("test")
    io.write_csv(tm, tdir / "test_metrics.csv")
    save_predictions(preds, iv, "test")
    # 정적 학습(7/31까지 1회) 민감도: 선택 모델만
    chosen = {t: sel[_family(t)]["chosen"] for t in TASKS}
    static_rows = []
    for task in TASKS:
        m = chosen[task]
        fam = _family(task)
        p = CV.run_test(frames[task], iv, R.factory(fam, m, sel), fam, weekly=False)
        _scores(iv["y"], p, iv["usable"].to_numpy(), iv, static_rows, task, m + "_static", [("test", C.TEST_START, C.TEST_END)])
    io.write_csv(pd.DataFrame(static_rows), tdir / "test_metrics_static_refit.csv")
    io.write_csv(selection_table(iv, cvm, tm, oof, preds, sel), od / "selection_summary.csv")
    io.write_csv(selection_robustness(cvm, oof, iv), od / "selection_robustness.csv")
    return {"selection": sel, "frames": frames}
