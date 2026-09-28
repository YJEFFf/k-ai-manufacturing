"""redC: 미래 시각 1행 뒤의 이상 600행을 옛 코드(6c61a88)와 새 코드(cc1aac2)가 각각 어떻게 처리하는가.

    python redC_time_glitch_old_vs_new.py --root <임시 사본>/yejun --label old|new
두 임시 사본에 같은 저장 모델(SHA-256 동일)을 둔다. 저장소 작업 사본은 쓰지 않는다.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--root", type=Path, required=True)
ap.add_argument("--label", required=True)
a = ap.parse_args()
GUARD = a.root / "press_guard"
sys.path.insert(0, str(GUARD))
import model as M  # noqa: E402
import simulate  # noqa: E402

D = M.D
assert Path(M.__file__).resolve().parent == GUARD.resolve()
normal, abnormal, _ = D.load()
ABN = D.inputs_only(abnormal).reset_index(drop=True)
out = {}
for sid in "AB":
    model = M.load_bundle(GUARD / "artifacts" / f"guard_{sid}.json")
    for label, shift in (("없음", None), ("+10초", pd.Timedelta(seconds=10)), ("+1시간", pd.Timedelta(hours=1)), ("+1일", pd.Timedelta(days=1))):
        frame = ABN
        if shift is not None:
            glitch = ABN.iloc[[0]].copy()
            glitch[D.TIME] = str(pd.to_datetime(ABN[D.TIME].iloc[0]) + shift)
            frame = pd.concat([glitch, ABN], ignore_index=True)
        pred = model.predict(frame, .01)
        body = pred.iloc[len(frame) - len(ABN):]
        log = simulate.run(frame, model, .01, chunk=1)
        out[f"{sid} {label}"] = dict(status=pred.status.value_counts().to_dict(), alarm_rows=int(body.alarm.sum()),
                                     abnormal_records_with_alarm=int(body.groupby("record_id").alarm.max().sum()),
                                     rows_not_judged=int(body.status.ne("ok").sum()),
                                     notifications=log[log.notify.eq(1)].kind.value_counts().to_dict())
        print(a.label, sid, label, out[f"{sid} {label}"], flush=True)
Path(__file__).with_name(f"redC_time_glitch_{a.label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
