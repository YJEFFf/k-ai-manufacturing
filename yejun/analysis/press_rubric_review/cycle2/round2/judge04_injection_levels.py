"""평가관 04 cycle2 round2: alert_levels_injection_v2.csv(E1식 계단형 주입의 단계별 2초 안 탐지율)를 독립 구현으로 대조한다.

주입 함수와 난수 씨앗은 팀과 같게 두고(recalibrate.inject, 씨앗 0~4), 탐지 판정은 여기서 따로 짠다.
  - 대상: 정상 평가 구간에서 길이 30행 이상인 알림 단위, 10행째부터 주입
  - 2초 창: 단위 안 위치 10~29행. 1단계 = 창 안 경보 행 존재, 2단계 = 창 안 단계 2 행 존재(model.predict의 alert_level)
실행(yejun/에서): OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python analysis/press_rubric_review/cycle2/round2/judge04_injection_levels.py
쓰는 파일: 이 폴더의 judge04_injection_levels.json. 저장 모델은 로컬 artifact(원본 재학습본과 해시 동일).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import D, HERE as GUARD, load_bundle  # noqa: E402
from recalibrate import inject, unit_layout  # noqa: E402

t0 = time.time()
csv = pd.read_csv(GUARD / "outputs" / "alert_levels_injection_v2.csv")
normal, _, _ = D.load()
CASES = (("A", "vib_noise", 2.0, 5), ("B", "vib_noise", 2.0, 5), ("A", "cur_offset", .2, 1), ("B", "cur_offset", .2, 1),
         ("B", "cur_noise", .1, 5), ("A", "cur_noise", .1, 5))
rows = []
for sid, fam, lv, reps in CASES:
    model = load_bundle(GUARD / "artifacts" / f"guard_{sid}.json")
    test = D.inputs_only(D.split_normal(normal, D.segments(normal), sid)["test"])
    units, in_unit, size = unit_layout(test)
    eligible = size >= 30
    mask = eligible & (in_unit >= 10)
    window = eligible & (in_unit >= 10) & (in_unit < 30)
    hits1, hits2 = [], []
    for rep in range(reps):
        p = model.predict(inject(test, model, fam, lv, mask, np.random.default_rng(rep)), .01)
        f = pd.DataFrame(dict(u=units, w=window, a=p.alarm.to_numpy() == 1, l2=p.alert_level.to_numpy() == 2))[eligible]
        g = f.assign(h1=f.w & f.a, h2=f.w & f.l2).groupby("u")[["h1", "h2"]].any()
        hits1.append(g.h1.to_numpy()); hits2.append(g.h2.to_numpy())
    l1, l2 = float(np.concatenate(hits1).mean()), float(np.concatenate(hits2).mean())
    c = csv[(csv.split == sid) & (csv.family == fam) & np.isclose(csv.level_value, lv) & np.isclose(csv.alpha, .01)].iloc[0]
    rows.append(dict(split=sid, family=fam, level=lv, reps=reps, units=int(len(hits1[0])), level1_detect_2s=l1, level2_detect_2s=l2,
                     csv_level1=float(c.level1_detect_2s), csv_level2=float(c.level2_detect_2s),
                     match=bool(np.isclose(l1, c.level1_detect_2s) and np.isclose(l2, c.level2_detect_2s))))
out = dict(rows=rows, all_match=all(r["match"] for r in rows), seconds=round(time.time() - t0, 1))
(HERE / "judge04_injection_levels.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
