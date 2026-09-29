"""검토 10: 긴 연속 수집(기록이 50행보다 긴 현장 운전)에서 건(cases: 기록구간 × 50행 블록)과 사건(incident_columns: 6차는 연속 수집 × 5초 블록)의
단위가 어긋나 사건 대기열(incidents(cases(p), p))이 행별 사건 열·알림과 맞지 않는지 잰다.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review10_queue.py

입력: 정상 평가 B 기록 20~49(995행)을 0.1초 간격 한 기록으로 다시 찍고, d번째 행의 시각을 비운다(오류 한 행: 기록은 d에서 나뉘고,
6차의 연속 수집은 이어진다). 경보 열은 판정 대신 정해 준 경보 행으로 바꾸고, 그 판의 사건 규칙(predict와 같은 인자)으로 사건 열을 다시 계산한 뒤
cases()·incidents()를 만든다. 경보 모양을 직접 정해야 '경보 행 사이에 경보 없는 5초 블록'을 만들 수 있어서다(연속으로 이은 실측 자료는 이음매에서 경보가 촘촘하다).
검사: (가) 경보 행의 사건 번호 가운데 사건 대기열에 없는 번호, (나) 경보 행이 둘 이상의 사건에 걸친 건, (다) 사건 대기열의 단계(level 2)와
      행별 격상 알림(incident_escalation) 유무가 다른 사건. 1) 정해 둔 예(d = 24, 경보 행 30·110), 2) 무작위 300가지(d, 경보 2~6행).
"""
import numpy as np
import pandas as pd

import review7_lib as L

M = L.M
NEW = hasattr(M, "CollectionUnits")
ver = ("a489001" if hasattr(M.CollectionUnits(), "extra") else "other") if NEW else "c7d8bba"
print(f"# 판 {ver} · 사본 {L.ENV}")
mdl = L.model("B")
nt = L.normal_test("B")
seg = L.D.segments(nt)
F = nt.iloc[np.flatnonzero((seg >= 20) & (seg < 50))].reset_index(drop=True)
t0 = pd.Timestamp("2022-07-25 08:00:00")
CONT = [t0 + pd.Timedelta(milliseconds=100 * i) for i in range(len(F))]


def build(d):
    f = L.with_times(F, CONT)
    f.loc[d, L.D.TIME] = ""
    return mdl.predict(f)


def relabel(p0, rows):
    p = p0.copy()
    a = np.zeros(len(p), bool); a[list(rows)] = True
    a &= p.status.eq("ok").to_numpy()
    p["alarm"] = a.astype(int)
    p["reason"] = np.where(a, "magnitude", np.where(p.status.eq("ok"), "", "invalid_input"))
    times = pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce")
    if NEW:
        inc = M.incident_columns(a, p.reason.to_numpy(), times, p.status.eq("ok").to_numpy(), p.time_order_event.to_numpy())
    else:
        inc = M.incident_columns(p.record_id.to_numpy(), p.alert_unit.to_numpy(), a, p.reason.to_numpy(), times, p.status.eq("ok").to_numpy(), p.time_order_event.to_numpy())
    p["incident_id"], p["incident_notification"], p["incident_escalation"], p["incident_update"] = inc.T
    return p


def check(p):
    q = M.cases(p)
    iq = M.incidents(q, p) if len(q) else pd.DataFrame()
    alarm = p.alarm.eq(1).to_numpy()
    ids = set(p.incident_id[alarm].astype(int))
    qids = set(iq.incident_id.astype(int)) if len(iq) else set()
    span = sum(int(p.iloc[c.row_from:c.row_to + 1].query("alarm == 1").incident_id.nunique() > 1) for c in q.itertuples()) if len(q) else 0
    esc = set(p[p.incident_escalation.eq(1)].incident_id.astype(int))
    lvl = sum(int((r.level == 2) != (int(r.incident_id) in esc)) for r in iq.itertuples()) if len(iq) else 0
    return len(ids - qids), span, lvl, q, iq


p0 = build(24)
p = relabel(p0, [30, 110])
miss, span, lvl, q, iq = check(p)
print("## 1) d = 24(시각 결측), 경보 행 30·110")
print(f"  기록: 행 0~23 = 기록 {p.record_id[0]}, 행 25~ = 기록 {p.record_id[25]}(위치 {p.position[30]}·{p.position[110]}, 알림 블록 {p.alert_unit[30]}·{p.alert_unit[110]})")
print(f"  행별 사건 열: 행 30 사건 {p.incident_id[30]} 시작 {p.incident_notification[30]} · 행 110 사건 {p.incident_id[110]} 시작 {p.incident_notification[110]} 격상 {p.incident_escalation[110]}"
      f" · 시작 알림 합 {int(p.incident_notification.sum())} · 격상 알림 합 {int(p.incident_escalation.sum())}")
print(f"  건 대기열: {q[['case_uid', 'incident_id', 'record_id', 'alarm_rows', 'level', 'escalation_row']].to_dict('records')}")
print(f"  사건 대기열: {iq[['incident_id', 'cases', 'alarm_rows', 'level', 'escalation_row']].to_dict('records')}")
print(f"  대기열에 없는 사건 {miss} · 두 사건에 걸친 건 {span} · 단계 불일치 사건 {lvl}")

print("## 2) 무작위 300가지: d ∈ 1~49, 경보 2~6행을 행 0~399에서 고름")
rng = np.random.default_rng(2026)
cache = {}
tot = np.zeros(3, int); bad = 0; ex = []
for k in range(300):
    d = int(rng.integers(1, 50))
    if d not in cache:
        cache[d] = build(d)
    rows = sorted(rng.choice(400, int(rng.integers(2, 7)), replace=False).tolist())
    r = check(relabel(cache[d], rows))[:3]
    tot += np.array(r)
    if any(r):
        bad += 1
        if len(ex) < 5:
            ex.append((d, rows, r))
print(f"  어긋난 경우 {bad}/300 · 대기열에 없는 사건 합 {tot[0]} · 두 사건에 걸친 건 합 {tot[1]} · 단계 불일치 합 {tot[2]} · 예 {ex}")
