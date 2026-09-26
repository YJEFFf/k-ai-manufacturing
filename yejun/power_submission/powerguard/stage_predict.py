"""추론 전용 단계: models 단계가 저장한 선택 모델(시험 주간 재학습)을 불러 시험 구간 예측을 다시 만든다.

학습 없이 몇 초 안에 시험 예측(점예측)을 재생성하고, 학습 때 만든 예측(artifacts/test_*.csv.gz)과의 최대 절대 차이를
outputs/test/inference_check.json에 남긴다. 모델 파일은 SHA-256으로 확인한다. 학습 때 예측은 소수 넷째 자리로 저장되므로
통과 기준은 최대 차이 ≤ 5e-5(저장 반올림 폭)이고, 재생성 예측도 같은 자리수(%.4f)로 저장한다.
"""
from __future__ import annotations

import hashlib
import json

import joblib
import numpy as np
import pandas as pd

from . import config as C
from . import io
from . import stage_models as SM

TASKS = ["B", "A1", "A2", "A3", "A4"]
TOL = 5e-5 + 1e-9  # 저장 반올림(소수 넷째 자리)의 최대 폭 + 부동소수 여유


def run(iv: pd.DataFrame, frames: dict, selection: dict) -> dict:
    mp = SM.MODEL_DIR / "manifest.json"
    if not mp.exists():
        raise FileNotFoundError(f"저장된 모델 목록이 없다: {mp} — models 단계를 먼저 실행한다")
    man = json.loads(mp.read_text(encoding="utf-8"))["models"]
    out = pd.DataFrame(index=iv.index[(iv.index >= C.TEST_START) & (iv.index < C.TEST_END)])
    out.index.name = "interval_start"
    summary = {"n_model_files": len(man), "tasks": {}}
    for task in TASKS:
        fam = "A" if task.startswith("A") else "B"
        chosen = selection[fam]["chosen"]
        members = selection[fam]["blend_members"] if chosen == "M8_blend" else [chosen]
        X = frames[task]
        parts = []
        for model in members:
            p = pd.Series(np.nan, index=X.index)
            entries = [m for m in man if m["task"] == task and m["model"] == model]
            if not entries:
                raise FileNotFoundError(f"저장된 모델 없음: {task} {model}")
            for m in entries:
                f = C.ARTIFACT_DIR / m["file"]
                if hashlib.sha256(f.read_bytes()).hexdigest() != m["sha256"]:
                    raise ValueError(f"모델 파일 SHA-256 불일치: {f}")
                est = joblib.load(f)
                s, e = pd.Timestamp(m["block_start"]), pd.Timestamp(m["block_end"])
                ev = (X.index >= s) & (X.index < e)
                p.loc[ev] = est.predict(X.loc[ev])
            parts.append(p)
        pred = sum(parts) / len(parts)
        col = f"{task}_{chosen}"
        out[col] = pred.reindex(out.index).to_numpy()
        ref = SM.load_predictions("test", task)[chosen].reindex(out.index)
        d = np.abs(out[col] - ref).dropna()
        dr = np.abs(out[col].round(4) - ref).dropna()
        summary["tasks"][task] = {"model": chosen, "members": members, "n": int(d.size),
                                  "max_abs_diff_vs_training_run": float(d.max()) if d.size else None,
                                  # 반올림 경계(다섯째 자리 5)에서 부동소수 끝자리 차이로 넷째 자리가 1 다른 행 수(차이 ≤ 1e-4)
                                  "rows_differing_after_4dp_rounding": int((dr > 1e-9).sum()),
                                  "pass": bool(d.size and d.max() <= TOL)}
    summary["pass_criterion"] = "모든 과제의 max_abs_diff_vs_training_run ≤ 5e-5(학습 때 예측의 소수 넷째 자리 저장 반올림 폭)"
    summary["pass"] = all(v["pass"] for v in summary["tasks"].values())
    io.write_csv(out.reset_index(), io.out_dir("test") / "predictions_from_saved_models.csv", float_fmt="%.4f")
    io.write_json(summary, io.out_dir("test") / "inference_check.json")
    if not summary["pass"]:
        raise ValueError(f"저장 모델 추론이 학습 때 예측과 다르다(기준 ≤ 5e-5): {summary['tasks']}")
    return summary
