"""평가관 04 보충 검증: 끊김 없는 연속 입력(R7)에서 이상 시작이 새 알림을 받는지, 인위 접합 없이 확인한다.

judge04_field_check.py의 연속 스트림(정상 B 평가 180구간 + 이상을 0.1초 간격으로 이어 붙임)은 정상 기록 사이 인위 접합이
179곳 생겨 정상 부분 경보 행이 부풀었다. 여기서는 접합을 이상 시작점 한 곳으로 줄인다.
  S1: 경보 없는 정상 기록 1개(50행) + 이상 600행   → 이상 시작 블록이 새 알림을 받는가
  S2: 끝 무렵 오경보가 있는 정상 기록 1개 + 이상 600행 → 바로 앞 블록 경보와 묶여 새 알림이 없는가(가려짐)
  S3: 큰 합성 스트림의 경보 행이 인위 접합 근처에 몰리는가
실행(yejun/에서): OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python analysis/press_rubric_review/cycle2/round1/judge04_stream_check.py
쓰는 파일: 이 폴더의 judge04_stream_check.json. 저장 모델은 로컬 artifact(judge04_field_check.json에서 원본 재학습본과 해시 동일 확인).
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
sys.path.insert(0, str(YEJUN / "analysis" / "press_supplement"))
from model import GuardModel, StreamDetector, cases, D  # noqa: E402
from common import split_rows  # noqa: E402

m = GuardModel.load(YEJUN / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
test = D.inputs_only(normal.iloc[split_rows(normal, "B")["test"]]).reset_index(drop=True)
ab = D.inputs_only(abnormal)
res = {}


def restamp(frame, start="2026-09-27 08:00:00"):
    g = frame.copy()
    g[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(g)) * D.DT, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


def run(frame, n_lead, chunk=128):
    sd = StreamDetector(m, .01)
    p = pd.concat([sd.push(frame.iloc[i:i + chunk]) for i in range(0, len(frame), chunk)], ignore_index=True)
    q = cases(p)
    note = p.index[p.notification == 1].tolist()
    return p, dict(rows=len(frame), lead_rows=n_lead, records=int(p.record_id.nunique()),
                   notifications=note, notifications_after_onset=[i - n_lead for i in note if i >= n_lead],
                   first_alarm_after_onset=int(p.index[(p.alarm == 1) & (p.index >= n_lead)][0] - n_lead) if ((p.alarm == 1) & (p.index >= n_lead)).any() else None,
                   cases=q[["first_row", "first_alarm_position", "alarm_rows", "observed_rows", "alert_units", "evidence", "action"]].to_dict("records"))


pt = m.predict(test, .01)
per = pt.groupby("record_id").agg(n=("alarm", "size"), a=("alarm", "sum"))
clean = per[(per.n == 50) & (per.a == 0)].index[0]
late_fa = per[(per.n == 50) & (per.a > 0)].index
late_fa = int(late_fa[0]) if len(late_fa) else None
res["picked"] = dict(clean_record=int(clean), false_alarm_record=late_fa,
                     false_alarm_positions=pt[(pt.record_id == late_fa) & (pt.alarm == 1)].position.tolist() if late_fa is not None else None)

lead = test[pt.record_id.to_numpy() == clean]
s1 = restamp(pd.concat([lead, ab], ignore_index=True))
p1, res["S1_clean_lead"] = run(s1, len(lead))
_, r1 = run(s1, len(lead), chunk=1)
res["S1_chunk1_same_notifications"] = r1["notifications"] == res["S1_clean_lead"]["notifications"]
if late_fa is not None:
    lead2 = test[pt.record_id.to_numpy() == late_fa]
    s2 = restamp(pd.concat([lead2, ab], ignore_index=True))
    _, res["S2_false_alarm_lead"] = run(s2, len(lead2))

# S3: 큰 합성 스트림(정상 B 평가 전체 + 이상)의 경보 행과 인위 접합(원래 기록 경계)의 거리
big = restamp(pd.concat([test, ab], ignore_index=True))
pb, _ = run(big, len(test))
orig_seg = np.r_[D.segments(test), D.segments(ab) + D.segments(test).max() + 1]
junction = np.flatnonzero(np.r_[False, orig_seg[1:] != orig_seg[:-1]])
dist = np.array([np.min(np.abs(junction - i)) for i in range(len(big))])
alarm_normal = (pb.alarm.to_numpy() == 1) & (np.arange(len(big)) < len(test))
blocks = pb.assign(blk=pb.position // 50).groupby("blk").alarm.max()
res["S3_big_stream"] = dict(normal_alarm_rows=int(alarm_normal.sum()), artificial_junctions_in_normal=int((junction < len(test)).sum()),
                            normal_alarm_rows_within_7_of_junction=int((alarm_normal & (dist <= 7)).sum()),
                            normal_blocks=int(len(test) // 50 + 1), alarmed_blocks_total=int(blocks.sum()), blocks_total=int(len(blocks)),
                            notifications=int(pb.notification.sum()), cases=int(len(cases(pb))))
out = HERE / "judge04_stream_check.json"
out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
