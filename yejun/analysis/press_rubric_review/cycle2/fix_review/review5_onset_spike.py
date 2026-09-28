"""검토 5: 진행 중 사건이 없을 때(이상의 시작점) 경보가 난 튄 행이 끼면, 튐 크기와 상관없이 한 이상에 사건 2개·시작 알림 2건인가.
README는 '경보가 난 +1시간 튄 행은 … 따로 사건 시작 알림 한 건을 낼 수 있다'고만 적는다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_onset_spike.py
입력: 경보 없는 정상 기록(38행) 바로 다음 표본부터 대회 이상 파일 600행. 그 사이에 이상 첫 행을 +Δ 시각으로 한 행 끼운다
(끼운 튐: 다음 행이 튀기 전 기준의 다음 표본이라 튐 예외가 발동한다).
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, layout, load_bundle, time_order_events

M = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
T = pd.to_datetime(ABN[D.TIME])
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
CLEAN = TEST[layout(TEST)[1] == 0].reset_index(drop=True)
fmt = "%Y-%m-%d %H:%M:%S.%f"
t0 = T.iloc[0] - pd.Timedelta(seconds=10)
clean = CLEAN.copy(); clean[D.TIME] = (t0 + pd.to_timedelta(np.arange(len(CLEAN)) * .1, unit="s")).strftime(fmt)
end = pd.Timestamp(clean[D.TIME].iloc[-1])
a = ABN.copy(); a[D.TIME] = (T + (end + pd.Timedelta(seconds=.1) - T.iloc[0])).dt.strftime(fmt)
for delta in (None, 0.5, 5.0, 3600.0):
    parts = [clean]
    if delta is not None:
        ins = ABN.iloc[[0]].copy(); ins[D.TIME] = (end + pd.Timedelta(seconds=delta)).strftime(fmt); parts.append(ins)
    f = pd.concat(parts + [a], ignore_index=True)
    p = M.predict(f)
    print(f"끼운 튐 {'없음' if delta is None else f'+{delta:g}초'}: 시각 사건(보류·새기준·튐) {time_order_events(p)}, 사건 {int(p.incident_id.max())}, "
          f"시작 알림 {int(p.incident_notification.sum())}, 격상 {int(p.incident_escalation.sum())}"
          + (f", 튄 행 경보 {int(p.alarm.iloc[len(clean)])}·사건 {int(p.incident_id.iloc[len(clean)])}, 다음 경보 행 사건 {int(p.incident_id[p.alarm.eq(1)].iloc[1])}" if delta else ""))
