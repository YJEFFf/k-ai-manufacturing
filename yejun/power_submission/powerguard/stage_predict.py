"""추론 전용 단계: models 단계가 저장한 선택 모델(시험 주간 재학습)을 불러 시험 구간 예측을 다시 만든다.

학습 없이 몇 초 안에 시험 예측(점예측)을 재생성하고, 학습 때 만든 예측(artifacts/test_*.csv.gz)과의 최대 절대 차이를
outputs/test/inference_check.json에 남긴다. 모델 파일은 SHA-256으로 확인한다.
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
        summary["tasks"][task] = {"model": chosen, "members": members, "n": int(d.size),
                                  "max_abs_diff_vs_training_run": float(d.max()) if d.size else None}
    io.write_csv(out.reset_index(), io.out_dir("test") / "predictions_from_saved_models.csv")
    io.write_json(summary, io.out_dir("test") / "inference_check.json")
    return summary
