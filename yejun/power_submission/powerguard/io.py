"""산출물 저장 도우미: 결정적인 CSV/JSON 쓰기."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C


def out_dir(*parts: str) -> Path:
    p = C.OUTPUT_DIR.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        if math.isnan(f) or math.isinf(f):
            return None
        return float(f"{f:.6g}") if f != 0 and abs(f) < 1e-3 else round(f, 6)  # 아주 작은 값(p값 등)은 유효숫자로
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    return o


def write_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def write_csv(df: pd.DataFrame, path: Path, float_fmt: str = "%.6g", index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, float_format=float_fmt, lineterminator="\n")
