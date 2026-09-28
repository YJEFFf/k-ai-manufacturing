"""review4: 정상 평가 기록 전류에 +δ(영점 이동 모의)를 더했을 때 경보 행의 권장 확인(action_for 규칙) 분포. 팀 함수 미사용."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent)); import review4_indep as I
ACT = dict(v="진동·부하 확인", vc="진동·전류 함께 점검", c="전류 크기·부하·계측 확인", cs="전류 크기·파형·계측 확인", s="전류 파형·계측 확인")
def action(row):
    comps = row.reason.split("+"); mag = "magnitude" in comps; shape = "waveform" in comps or "dynamics" in comps
    cur = row.magnitude_sensor == "AI2_Current"; vib = mag and not cur; c = mag and cur
    if vib and (shape or c): return ACT["vc"]
    if vib: return ACT["v"]
    if c and shape: return ACT["cs"]
    if c: return ACT["c"]
    return ACT["s"]
n, a = I.load_raw(); rn = I.records(n.TimeStamp)
for sid, start in (("A", 480), ("B", 420)):
    m = I.Model(sid); t = n[rn >= start].reset_index(drop=True); v0 = t[I.SENS].to_numpy(float)
    for d in (150, 230):
        v = v0.copy(); v[:, 2] += d
        p = m.predict(v, t.TimeStamp); al = p[p.alarm.eq(1)]
        first = al.groupby("record").head(1)
        print(sid, f"+{d}", "경보 행 조치:", al.apply(action, axis=1).value_counts().to_dict(), "| 기록 첫 경보 조치:", first.apply(action, axis=1).value_counts().to_dict())
