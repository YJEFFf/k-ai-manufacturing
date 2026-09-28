"""검토 1: README "8행 미만의 무경보 조각은 ... 품질 시간창의 끝도 정하지 않는다"가 cases()에 구현돼 있는가.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_suspect_window.py
"""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ["REVIEW_ENV"]) / "press_guard"))
import numpy as np, pandas as pd
from model import D, load_bundle, layout, cases, incidents

model = load_bundle(Path(os.environ["REVIEW_ENV"]) / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
abn = D.inputs_only(abnormal).reset_index(drop=True)
rec0 = abn.iloc[np.flatnonzero(D.segments(abnormal) == 1)]   # 50행 이상 기록
split = D.split_normal(normal, D.segments(normal), "B")
test = D.inputs_only(split["test"]).reset_index(drop=True)
rec = layout(test)[1]
quiet = test[rec == 0].reset_index(drop=True)          # 경보 없는 정상 기록(50행)
t0 = pd.Timestamp("2022-07-17 10:00:00")
steps = np.r_[0, np.full(len(rec0) - 1, .1), 2.0, .1, .1, .13, np.full(len(quiet) - 4, .1)]   # 기록 사이 2초, 정상 기록의 3행째 뒤 130 ms
frame = pd.concat([rec0, quiet], ignore_index=True)
frame[D.TIME] = (t0 + pd.to_timedelta(np.cumsum(steps), unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
p = model.predict(frame)
c = cases(p)
after = p.iloc[len(rec0):]
print("경보 기록 뒤 정상 기록을 3행 + 나머지로 쪼갬(3행째 뒤 간격 130 ms): 뒤 기록 조각 길이", after.groupby("record_id").size().tolist(),
      "경보", int(after.alarm.sum()))
print("건의 suspect_to:", c.suspect_to.tolist(), "| 3행 조각 시작:", pd.Timestamp(frame[D.TIME].iloc[len(rec0)]).isoformat(),
      "| 8행 이상 조각 시작:", pd.Timestamp(frame[D.TIME].iloc[len(rec0) + 3]).isoformat())
