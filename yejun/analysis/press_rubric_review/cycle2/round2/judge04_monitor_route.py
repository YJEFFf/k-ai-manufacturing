"""평가관 04 cycle2 round2: 운영 감시(monitor.py)가 '정상 운전변화'와 '진행성 이상'을 다른 조치로 보내는지 확인한다.

출제배경의 두 오류(정상 운전변화를 이상으로 오인 / 초기 이상징후를 놓침)를 감시 규칙이 구별하는지 본다.
  G: 전류 전체 배율 ×1.3(analysis/press_dayshift와 같은 정상 운전변화 모의, 저장소 monitor_gain_v2.csv와 같은 조건)
  V: 마지막 감시 창(60단위)에만 약한 진동 잡음 1σ·2σ를 10행째부터 더함(보완 실험 E1·recalibrate.inject와 같은 주입, 인공 신호)
  C: 마지막 감시 창에만 약한 전류 오프셋 0.2×진폭
각 경우 창별 알림 단위·2단계 격상·전류 수준 비·재보정 검토 여부·사유를 적는다. 저장 모델은 로컬 artifact(원본 재학습본과 해시 동일,
judge04_r2_check.json retrain_from_raw)를 쓴다.
실행(yejun/에서): OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python analysis/press_rubric_review/cycle2/round2/judge04_monitor_route.py
쓰는 파일: 이 폴더의 judge04_monitor_route.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import D, HERE as GUARD, load_bundle  # noqa: E402
from monitor import Reference, monitor_windows  # noqa: E402
from recalibrate import inject, unit_layout  # noqa: E402

model = load_bundle(GUARD / "artifacts" / "guard_B.json")
normal, _, _ = D.load()
sp = D.split_normal(normal, D.segments(normal), "B")
ref = Reference.from_frame(pd.concat([sp["train"], sp["cal"]], ignore_index=True))
test = D.inputs_only(sp["test"])
units, in_unit, size = unit_layout(test)
last_window = units >= 120
mask = last_window & (size >= 30) & (in_unit >= 10)


def show(frame, alpha=.01):
    w = monitor_windows(model.predict(frame, alpha), frame, alpha, len(model.cal), ref)
    return w[["window", "alerted_units", "limit95", "limit99", "level1_notifications", "level2_escalations", "current_ratio",
              "drift_up", "recalibration_review", "reason"]].to_dict("records")


out = {"note": "모든 경우가 같은 출력(recalibration_review)으로 끝나는지, 사유 문자열로 구별되는지 본다. 주입은 인공 신호다",
       "masked_units": int(pd.Series(units[mask]).nunique())}
out["nominal"] = show(test)
g = test.copy()
g[D.SENSORS[2]] = pd.to_numeric(g[D.SENSORS[2]]) * 1.3
out["G_current_gain_1.3"] = show(g)
for lv in (1.0, 2.0):
    out[f"V_vib_noise_{lv:g}sigma_last_window"] = show(inject(test, model, "vib_noise", lv, mask, np.random.default_rng(0)))
out["C_cur_offset_0.2_last_window"] = show(inject(test, model, "cur_offset", .2, mask, np.random.default_rng(0)))
(HERE / "judge04_monitor_route.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                                 encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
