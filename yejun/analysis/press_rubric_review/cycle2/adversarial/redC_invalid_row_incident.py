"""redC: 오류 행 하나가 사건을 끊는 동작이 옛 코드(6c61a88)에도 있었는지 대조한다. 임시 사본만 쓴다.

    python redC_invalid_row_incident.py --root <임시 사본>/yejun --label old|new
"""
import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser(); ap.add_argument("--root", type=Path, required=True); ap.add_argument("--label", required=True); a = ap.parse_args()
sys.path.insert(0, str(a.root / "press_guard"))
import model as M  # noqa: E402
D = M.D
normal, abnormal, _ = D.load()
model = M.load_bundle(a.root / "press_guard" / "artifacts" / "guard_B.json")
test = D.inputs_only(D.split_normal(normal, D.segments(normal), "B")["test"]).reset_index(drop=True)
rec = M.layout(test)[1]
def at(f, start):
    f = f.copy().reset_index(drop=True); f[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(f)) * .1, unit="s")).astype(str); return f
r3, r41 = test[rec == 3], test[rec == 41]
out = {}
bad = r3.iloc[[0]].copy(); bad[D.SENSORS[0]] = np.nan
frame = pd.concat([at(r3, "2022-07-12 00:00:00"), at(bad, "2022-07-12 00:00:05.9"), at(r41, "2022-07-12 00:00:06.9")], ignore_index=True)
p = model.predict(frame)
out["경보 1행 두 기록 사이 결측 1행(2초 안)"] = dict(incident_starts=int(p.incident_notification.sum()), escalations=int(p.incident_escalation.sum()))
ab = D.inputs_only(abnormal).reset_index(drop=True)
ab.loc[np.random.default_rng(20260928).random(len(ab)) < .05, D.TIME] = ""
p = model.predict(ab)
out["이상 600행·시각 5% 결측"] = dict(incident_starts=int(p.incident_notification.sum()), escalations=int(p.incident_escalation.sum()), bad_rows=int(p.status.ne("ok").sum()))
print(a.label, json.dumps(out, ensure_ascii=False))
Path(__file__).with_name(f"redC_invalid_row_incident_{a.label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
