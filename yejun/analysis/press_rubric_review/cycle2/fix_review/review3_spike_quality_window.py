"""검토 3: 경보 없는 미래 튐 한 행이 품질 의심 시간창(cases의 suspect_from/to)의 경계가 되는가.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_spike_quality_window.py
사건 추적은 튄 행의 효과를 되돌리지만(110afa2), cases()는 튄 행도 '경보 없는 유효 단위'로 본다.
"""
import os, sys
from pathlib import Path
ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np, pandas as pd
from model import D, layout, load_bundle, cases, incidents

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
CLEAN = TEST[layout(TEST)[1] == 0].reset_index(drop=True)
T0 = pd.Timestamp("2022-07-17 10:00:00")


def stamp(frame, start):
    out = frame.copy().reset_index(drop=True)
    out[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(out)) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
    return out


rec = ABN[D.segments(abnormal) == 1]                       # 경보 기록(50행)
before = stamp(CLEAN, T0)                                   # 앞 정상 기록 0.0~3.7초
alarmed = stamp(rec, T0 + pd.Timedelta(seconds=6))          # 경보 기록 6.0~10.9초
after = stamp(CLEAN, T0 + pd.Timedelta(seconds=13))         # 뒤 정상 기록 13.0초~
spike = stamp(CLEAN.iloc[[5]], T0 + pd.Timedelta(hours=1))  # 경보 없는 +1시간 튐 한 행
cols = ["record_id", "suspect_from", "suspect_to", "suspect_seconds", "suspect_open"]
for title, parts in (("튐 없음", [before, alarmed, after]),
                     ("경보 기록 바로 뒤에 튄 행", [before, alarmed, spike, after]),
                     ("경보 기록 바로 앞에 튄 행", [before, spike, alarmed, after])):
    frame = pd.concat(parts, ignore_index=True)
    pred = MODEL.predict(frame)
    c = cases(pred)
    print(f"### {title}: 경보 {int(pred.alarm.sum())}행, 시각 순서 사건 {pred.time_order_event.value_counts().to_dict()}, "
          f"사건 {int(pred.incident_id.max())}")
    print(c[cols].to_string(index=False))
