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


def _scores(y, p, usable, iv, rows, task, model, split_blocks):
    for name, s, e in split_blocks:
        ev = CV.eval_mask(y.index, usable, s, e) & np.isfinite(p.to_numpy())
        if not ev.any():
            continue
        T = CV.peak_threshold(iv, s if name != "test" else C.TEST_START)
        r = MT.regression(y[ev], p[ev], T=T, mask_work=((iv["hour"] >= 8) & (iv["hour"] < 20)).to_numpy()[ev])
        c = MT.classification((y[ev] >= T).astype(int), (p[ev] >= T).astype(float), 0.5)
        extra = {}
        if task == "B":
            dp = MT.daily_peak(pd.DataFrame({"y": y[ev], "p": p[ev]}), "p")
            extra = {k: dp.get(k) for k in ("daymax_MAE", "daymax_bias", "peak_slot_hit_pm1")}
        rows.append(dict(task=task, model=model, split=name, T=T, **r, **extra,
                         n_missing_pred=int((CV.eval_mask(y.index, usable, s, e) & ~np.isfinite(p.to_numpy())).sum()),
                         peak_precision=c["precision"], peak_recall=c["recall"], peak_F1=c["F1"]))


def run_cv_all(iv: pd.DataFrame, frames: dict, log=print) -> tuple[pd.DataFrame, dict]:
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    rows, oof = [], {}
    blocks = CV.cv_blocks()
    pooled_block = [("pooled", C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2])]
    for task in TASKS:
        X = frames[task]
        oof[task] = {}
        for model, fac in R.candidates(_family(task)).items():
            t0 = time.time()
            p = CV.run_cv(X, iv, fac, _family(task))
            oof[task][model] = p
            _scores(y, p, usable, iv, rows, task, model, blocks + pooled_block)
            log(f"  CV {task} {model} {time.time() - t0:.1f}s")
    cvm = pd.DataFrame(rows)
    # 6월은 원본일 2일뿐이라 pooled 구간(4/1~7/31)에서 사실상 제외된다.
    return cvm, oof


def add_blend(cvm: pd.DataFrame, oof: dict, iv: pd.DataFrame, family_tasks: list[str]) -> tuple[pd.DataFrame, dict]:
    """가족(A 또는 B)별 pooled RMSE 상위 2개 단일 모델의 동일 가중 평균을 M8_blend로 추가한다."""
    y = iv["y"]
    usable = iv["usable"].to_numpy()
    sub = cvm[(cvm.task.isin(family_tasks)) & (cvm.split == "pooled")]
    rank = sub.groupby("model")["RMSE"].mean().sort_values()
    top2 = [m for m in rank.index if not m.startswith("BL")][:2]
    rows = []
    blocks = CV.cv_blocks() + [("pooled", C.CV_FOLDS[0][1], C.CV_FOLDS[-1][2])]
    for task in family_tasks:
        p = (oof[task][top2[0]] + oof[task][top2[1]]) / 2
        oof[task]["M8_blend"] = p
        _scores(y, p, usable, iv, rows, task, "M8_blend", blocks)
    return pd.concat([cvm, pd.DataFrame(rows)], ignore_index=True), {"members": top2}


def select(cvm: pd.DataFrame, oof: dict, iv: pd.DataFrame, family_tasks: list[str]) -> dict:
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
    v3 = sub[sub.split == "V3_Jul"].groupby("model")["RMSE"].mean()
    trail = []
    cur = pooled.index[0]
    while True:
        simpler = [m for m in pooled.index if R.complexity(m) < R.complexity(cur)]
        if not simpler:
            break
        c = min(simpler, key=lambda m: pooled[m])
        if len(family_tasks) == 1:
            t = family_tasks[0]
            bt = MT.paired_day_bootstrap(y, oof[t][cur], oof[t][c], mask, stat="RMSE")
        else:
            bt = MT.multi_bootstrap_rmse(y, [oof[t][cur] for t in family_tasks], [oof[t][c] for t in family_tasks], mask)
        step = {"model": cur, "vs_simpler": c, "rmse_boot": bt}
        sig = bt["ci90"][1] < 0
        if not sig and family_tasks == ["B"]:
            bd = MT.paired_day_bootstrap(y, oof["B"][cur], oof["B"][c], mask, stat="daymax_MAE")
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
            bt = MT.paired_day_bootstrap(y, oof[family_tasks[0]][v1], oof[family_tasks[0]][c], mask, stat="RMSE")
        else:
            bt = MT.multi_bootstrap_rmse(y, [oof[t][v1] for t in family_tasks], [oof[t][c] for t in family_tasks], mask)
        if bt["ci90"][1] < 0:
            break
        v1 = c
    return {"chosen": cur, "v1_rule_choice": v1,
            "rule": "pooled RMSE 최소 → 더 단순한 등급 최선 모델과 날짜 부트스트랩(90%) 비교, "
                    "B는 동률 시 일 최대 오차로 2차 비교(v1.1, 교차검증 비교 후 추가)",
            "trail": trail, "pooled_RMSE": pooled.round(4).to_dict(), "V3_RMSE": v3.sort_values().round(4).to_dict()}


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


def run(iv: pd.DataFrame, log=print) -> dict:
    frames = CV.build_frames(iv)
    cvm, oof = run_cv_all(iv, frames, log=log)
    blend_members = {}
    for fam, tasks in (("B", ["B"]), ("A", ["A1", "A2", "A3", "A4"])):
        cvm, info = add_blend(cvm, oof, iv, tasks)
        blend_members[fam] = info["members"]
    sel = {fam: select(cvm, oof, iv, tasks) for fam, tasks in (("B", ["B"]), ("A", ["A1", "A2", "A3", "A4"]))}
    for fam in sel:
        sel[fam]["blend_members"] = blend_members[fam]
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
        if m == "M8_blend":
            continue
        fam = _family(task)
        p = CV.run_test(frames[task], iv, R.candidates(fam)[m], fam, weekly=False)
        _scores(iv["y"], p, iv["usable"].to_numpy(), iv, static_rows, task, m + "_static", [("test", C.TEST_START, C.TEST_END)])
    io.write_csv(pd.DataFrame(static_rows), tdir / "test_metrics_static_refit.csv")
    return {"selection": sel, "frames": frames}
