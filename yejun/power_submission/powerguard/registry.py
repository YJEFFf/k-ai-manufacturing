"""과제별 비교 모델 목록(v1, 사전 고정). 이름 접두어: BL=기준모델, M=제안 후보."""
from __future__ import annotations

from . import features as F
from . import models as M

COOL_MONO = {c: 1 for c in F.COOLING}

# 단순한 순서(선택 규칙의 동률 판정용): 작을수록 단순
COMPLEXITY = {"BL1": 0, "BL2": 0, "BL3": 0, "BL5": 1, "BL6": 1, "M5": 1, "M6": 1, "BL4": 2, "M9": 2, "M9l": 2,
              "M1": 3, "M3": 3, "M3d": 3, "M7": 4, "M7c": 4, "M8": 5}


def complexity(name: str) -> int:
    return COMPLEXITY.get(name.split("_")[0], 9)


def candidates(task: str) -> dict:
    """task: 'A'(실시간, 지평별 동일 구성) 또는 'B'(익일)."""
    feats = F.feature_list(task)
    reg = {}
    if task == "A":
        reg["BL1_persistence"] = lambda: M.Persistence()
    reg["BL2_same_daytype"] = lambda: M.SameDaytype()
    reg["BL3_profile"] = lambda: M.Profile()
    reg["BL4_ridge"] = lambda: M.RidgeModel(feats)
    reg["BL5_regime_analog"] = lambda: M.AnalogDay("analog_regime")
    if task == "A":
        reg["BL6_analog_persist"] = lambda: M.AnalogLevel(1.0)
        reg["M6_analog_level"] = lambda: M.AnalogLevel(0.9)
    else:
        reg["M9_analog_adjusted"] = lambda: M.AnalogAdjusted(use_level=True, use_temp=True)
        reg["M9l_analog_level_adj"] = lambda: M.AnalogAdjusted(use_level=True, use_temp=False)
        reg["M3d_dayvec_mlp"] = lambda: M.DayVectorMLP()
    reg["M1_lgbm"] = lambda: M.LGBModel(feats, objective="huber", alpha=10.0)
    reg["M3_mlp"] = lambda: M.MLPModel(feats)
    reg["M7_hybrid"] = lambda: M.Hybrid(feats, task)
    reg["M7c_hybrid_coolmono"] = lambda: M.Hybrid(feats, task, monotone=COOL_MONO)
    return reg

