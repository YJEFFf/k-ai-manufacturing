"""적대적 검수자 E 공용 도구 — 읽기 전용.

저장소 모듈은 import만 한다(GuardModel.load·predict). 팀의 생성 스크립트는 실행하지 않는다.
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python redE_XX.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
GUARD = YEJUN / "press_guard"
BASE = YEJUN / "press_submission"
DATA = BASE / "data" / "3_소성가공_예지보전"
for p in (str(GUARD), str(BASE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np
import pandas as pd


def raw():
    n = pd.read_csv(DATA / "press_data_normal.csv")
    a = pd.read_csv(DATA / "outlier_data.csv")
    return n, a


def record_ids(frame, tol=1e-6):
    t = pd.to_datetime(frame["TimeStamp"])
    gap = t.diff().dt.total_seconds()
    new = (gap.sub(0.1).abs() > tol).fillna(False).to_numpy()
    return np.cumsum(new)


def models():
    from model import load_bundle
    return {s: load_bundle(GUARD / "artifacts" / f"guard_{s}.json") for s in ("A", "B")}


SPLITS = {"A": (360, 480), "B": (300, 420)}


def split(normal, sid):
    seg = record_ids(normal)
    tr, ca = SPLITS[sid]
    return dict(train=normal[seg < tr].reset_index(drop=True), cal=normal[(seg >= tr) & (seg < ca)].reset_index(drop=True),
                test=normal[seg >= ca].reset_index(drop=True))


def dump(obj, name):
    import json

    def conv(o):
        if isinstance(o, dict):
            return {str(k): conv(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [conv(v) for v in o]
        if isinstance(o, np.ndarray):
            return conv(o.tolist())
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if not np.isfinite(o) else float(o)
        if isinstance(o, float):
            return None if not np.isfinite(o) else o
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return o
    (HERE / name).write_text(json.dumps(conv(obj), ensure_ascii=False, indent=2), encoding="utf-8")
