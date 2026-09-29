"""검토 8: 대회 자료(시각 오류 없음)에서 판정 열이 두 판(8b65130·c7d8bba)에서 같은가. 판마다 한 번 돌려 해시를 찍고 눈으로 대조한다.
또 train.combine_streams(정상 평가 + 이상 파일을 한 흐름으로 이은 사건 재번호)의 사건 열 해시도 찍는다.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_invariance.py
"""
import hashlib

import numpy as np
import pandas as pd

import review8_lib as L

COLS = ["status", "record_id", "alarm", "notification", "alert_level", "escalation", "incident_id", "incident_notification",
        "incident_escalation", "incident_update", "reason", "time_order_event"]
normal, abnormal, _ = L.D.load()
print(f"# 판 {L.VERSION}")


def h(p):
    cols = [c for c in COLS if c in p]
    return hashlib.sha256(p[cols].astype(str).to_csv(index=False).encode()).hexdigest()[:16]


for split in ("A", "B"):
    mdl = L.load_bundle(L.HERE / "artifacts" / f"guard_{split}.json")
    sp = L.D.split_normal(normal, L.D.segments(normal), split)
    for name, frame in (("정상 평가", L.D.inputs_only(sp["test"]).reset_index(drop=True)), ("이상", L.D.inputs_only(abnormal).reset_index(drop=True))):
        for a in (.01, .03, .05):
            p = mdl.predict(frame, a)
            print(f"{split} {name} α{a}: 행 {len(p)} 경보 {int(p.alarm.sum())} 사건 {int(p.incident_id.max())} 시작 {int(p.incident_notification.sum())} "
                  f"격상 {int(p.incident_escalation.sum())} 판정 열 해시 {h(p)}")
    if split == "B":
        p = mdl.predict(L.D.inputs_only(normal).reset_index(drop=True), .01)
        print(f"B 정상 전체 α0.01: 행 {len(p)} 경보 {int(p.alarm.sum())} 사건 {int(p.incident_id.max())} 판정 열 해시 {h(p)}")
import train  # noqa: E402
for split in ("A", "B"):
    mdl = L.load_bundle(L.HERE / "artifacts" / f"guard_{split}.json")
    sp = L.D.split_normal(normal, L.D.segments(normal), split)
    pn = mdl.predict(L.D.inputs_only(sp["test"]).reset_index(drop=True), .01)
    pa = mdl.predict(L.D.inputs_only(abnormal).reset_index(drop=True), .01)
    out = train.combine_streams(pn, pa, return_predictions=True)
    both = out[1] if isinstance(out, tuple) else out
    if isinstance(both, pd.DataFrame) and "incident_id" in both:
        print(f"{split} combine_streams α0.01: 사건 {int(both.incident_id.max())} 시작 {int(both.incident_notification.sum())} 격상 {int(both.incident_escalation.sum())} "
              f"사건 열 해시 {hashlib.sha256(both[['incident_id', 'incident_notification', 'incident_escalation', 'incident_update']].to_csv(index=False).encode()).hexdigest()[:16]}")
    else:
        print(f"{split} combine_streams 반환 형태 {type(out)}")
