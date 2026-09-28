"""검토 1: 이상 자료의 한 기록을 역순으로 보내면(가장 늦은 행부터) 판정 보류·경고 없이 1행 기록으로 판정되는가.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_reversed_record.py
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["REVIEW_ENV"]) / "press_guard"))
import numpy as np, pandas as pd
from model import D, load_bundle, timing_warning, time_order_events

model = load_bundle(Path(os.environ["REVIEW_ENV"]) / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
abn = D.inputs_only(abnormal).reset_index(drop=True)
seg = D.segments(abnormal)
base = model.predict(abn)
for r in (5, 12):
    idx = np.flatnonzero(seg == r)
    order = np.r_[np.arange(idx[0]), idx[::-1], np.arange(idx[-1] + 1, len(abn))]
    f = abn.iloc[order].reset_index(drop=True)
    p = model.predict(f)
    rows = p.iloc[idx[0]:idx[-1] + 1]
    print(f"기록 {r}({len(idx)}행)을 역순으로: bad_time_order {int(p.status.eq('bad_time_order').sum())}행, "
          f"그 기록의 기록 수 {rows.record_id.nunique()}, 경보 {int(rows.alarm.sum())}행(원래 순서 {int(base.alarm.iloc[idx].sum())}행), "
          f"time_order_events {time_order_events(p)}, 경고='{timing_warning(p)}'")
