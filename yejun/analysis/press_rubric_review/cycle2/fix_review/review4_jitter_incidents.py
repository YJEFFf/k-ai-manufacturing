"""review4: 흔들림 스트레스의 '1단계 경보 기록 비율'과 운영 절차의 사건 단위 '1단계 알림·2단계 격상'을 비교한다.

팀 GuardModel.predict(사건 번호·알림 열)를 쓰되, 흔들린 입력은 review4_jitter.py와 같은 방식(같은 시드·순서)으로 만든다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import review4_indep as I  # noqa: E402

W = Path(__file__).parent / "review4_work" / "yejun"
sys.path.insert(0, str(W / "press_guard"))
from model import GuardModel  # noqa: E402

SEED = 20260929
SPL = {"A": 480, "B": 420}
n, a = I.load_raw()
rec_all = I.records(n.TimeStamp)
rows = []
for sid in ("A", "B"):
    model = GuardModel.load(W / "press_guard" / "artifacts" / f"guard_{sid}.json")
    mask = rec_all >= SPL[sid]
    test = n[mask].reset_index(drop=True)
    seg = rec_all[mask]
    x0 = test.AI2_Current.to_numpy(float)
    L = pd.Series(seg).value_counts()
    fits = {}
    for s in sorted(L[L >= 17].index):
        idx = np.flatnonzero(seg == s)
        f = I.best_sine(x0[idx])[0]
        coef, resid = I.ls_tone(x0[idx], f)
        fits[s] = (idx, f, coef, resid)
    keep = np.isin(seg, list(fits))
    for sigma in (0.0, 0.1, 0.2):
        rng = np.random.default_rng(SEED)
        x = x0.copy()
        for s, (idx, f, coef, resid) in fits.items():
            ph = 2 * np.pi * f * np.arange(len(idx)) * .1
            if sigma > 0:
                ph = ph + 2 * np.pi * 60.6 * rng.normal(0, sigma / 1e3, len(idx))
            x[idx] = coef[0] * np.cos(ph) + coef[1] * np.sin(ph) + coef[2] + resid
        frame = test.copy(); frame["AI2_Current"] = x
        p = model.predict(frame, .01)
        rec_alarm = p[keep].groupby(seg[keep]).alarm.max()
        multi = p[p.alarm.eq(1)].groupby("record_id").head(1).reason.str.contains(r"\+").mean() if p.alarm.any() else np.nan
        rows.append(dict(split=sid, sigma_ms=sigma, records_ge17=len(fits), records_alarmed=int(rec_alarm.sum()),
                         record_rate=round(rec_alarm.mean(), 3), all_records=int(p.record_id.nunique()),
                         incident_level1_notifications=int(p.incident_notification.sum()), incident_level2_escalations=int(p.incident_escalation.sum()),
                         alarm_rows=int(p.alarm.sum()), first_alarm_multi_component_share=round(float(multi), 3) if multi == multi else None,
                         recorded_minutes=round(len(p) * 0.1 / 60, 1),
                         elapsed_minutes=round((pd.to_datetime(test.TimeStamp).iloc[-1] - pd.to_datetime(test.TimeStamp).iloc[0]).total_seconds() / 60, 1)))
print(pd.DataFrame(rows).to_string(index=False))
