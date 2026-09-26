"""과제별 비교 모델 목록(v2.0, 사전 고정). 이름 접두어: BL=기준모델, M=제안 후보."""
from __future__ import annotations

from . import features as F
from . import models as M

COOL_MONO = {c: 1 for c in F.COOLING}

# 단순한 순서(선택 규칙의 동률 판정용): 작을수록 단순
COMPLEXITY = {"BL1": 0, "BL2": 0, "BL3": 0, "BL5": 1, "BL6": 1, "M5": 1, "M6": 1, "BL4": 2, "M9": 2, "M9l": 2,
              "M1": 3, "M3": 3, "M3d": 3, "M7": 4, "M7c": 4, "M8": 5}


# 모델 계열(앙상블 구성원은 서로 다른 계열에서 고른다, v2.0)
FAMILY = {"BL1": "naive", "BL2": "naive", "BL3": "profile", "BL4": "linear", "BL5": "analog", "BL6": "analog",
          "M6": "analog", "M9": "analog", "M9l": "analog", "M1": "tree", "M3": "nn", "M3d": "nn",
          "M7": "hybrid", "M7c": "hybrid"}


def complexity(name: str) -> int:
    return COMPLEXITY.get(name.split("_")[0], 9)


def family(name: str) -> str:
    return FAMILY.get(name.split("_")[0], name)


def candidates(task: str) -> dict:
    """task: 'A'(실시간, 지평별 동일 구성) 또는 'B'(익일)."""
    feats = F.feature_list(task)
    reg = {}
    if task == "A":
        reg["BL1_persistence"] = lambda: M.Persistence()
    reg["BL2_same_daytype"] = lambda: M.SameDaytype()
    reg["BL3_profile"] = lambda: M.Profile()
    g = lambda m: M.gated(m, task)  # 계획 정지 게이트(ML 계열, v2.0)
    reg["BL4_ridge"] = lambda: g(M.RidgeModel(feats))
    reg["BL5_regime_analog"] = lambda: M.AnalogDay("analog_regime")
    if task == "A":
        reg["BL6_analog_persist"] = lambda: M.AnalogLevel(1.0)
        reg["M6_analog_level"] = lambda: M.AnalogLevel(0.9)
    else:
        reg["M9_analog_adjusted"] = lambda: M.AnalogAdjusted(use_level=True, use_temp=True)
        reg["M9l_analog_level_adj"] = lambda: M.AnalogAdjusted(use_level=True, use_temp=False)
        reg["M3d_dayvec_mlp"] = lambda: g(M.DayVectorMLP())
    reg["M1_lgbm"] = lambda: g(M.LGBModel(feats, objective="huber", alpha=10.0))
    reg["M3_mlp"] = lambda: g(M.MLPModel(feats))
    reg["M7_hybrid"] = lambda: g(M.Hybrid(feats, task))
    reg["M7c_hybrid_coolmono"] = lambda: g(M.Hybrid(feats, task, monotone=COOL_MONO))
    return reg



def factory(fam: str, name: str, selection: dict | None = None):
    """모델 이름 → 생성 함수. M8_blend는 선택 기록의 구성원 두 모델의 동일 가중 평균으로 다시 만든다."""
    reg = candidates(fam)
    if name == "M8_blend":
        mem = (selection or {}).get(fam, {}).get("blend_members")
        if not mem:
            raise KeyError("M8_blend 구성원이 선택 기록에 없다")
        return lambda: M.Blend([reg[m]() for m in mem], [0.5, 0.5])
    return reg[name]
