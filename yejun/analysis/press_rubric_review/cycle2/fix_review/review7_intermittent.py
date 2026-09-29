"""검토 7: 기록 앞부분이 경보 없는 간헐 이상에서, 기록 한가운데의 오류 한 행(튐·시각 결측·센서 결측·20 ms 넘는 흔들림)이
경보 단위를 '경보 없는 8행 이상 조각'과 나머지로 쪼개 사건을 닫는가.

입력: 이상 기록 11(50행) → 3초 → [경보 없는 정상 기록의 앞 k행 + 이상 기록 12의 42행]을 0.1초 간격으로 이은 한 기록 → 3초 → 이상 기록 13.
원자료(오류 없음)는 둘째 기록 전체가 경보 단위 하나라 사건 1개다. 오류는 둘째 기록의 k번째 행(첫 이상 행) 또는 그 앞뒤에 넣는다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_intermittent.py
"""
from review7_lib import *  # noqa: F401,F403

mdl = model("B")
ab, ta = base_abnormal()
seg = D.segments(ab)
nt = normal_test("B")
pn = mdl.predict(nt)
rec = pn.record_id.to_numpy()
quiet = [r for r in np.unique(rec) if pn.alarm[rec == r].sum() == 0 and (rec == r).sum() >= 30]
r11, r12, r13 = ab[seg == 11], ab[seg == 12], ab[seg == 13]
print(f"# 판: {ENV.parent.name}")
for k in (8, 10, 15):
    lead = nt[rec == quiet[0]].iloc[:k]
    mid = pd.concat([D.inputs_only(lead), D.inputs_only(r12)], ignore_index=True)
    parts = [D.inputs_only(r11), mid, D.inputs_only(r13)]
    frame = pd.concat(parts, ignore_index=True)
    t0 = pd.Timestamp("2022-07-21 00:00:00")
    times, t = [], t0
    for j, p in enumerate(parts):
        for i in range(len(p)):
            times.append(t); t = t + pd.Timedelta(seconds=0.1)
        t = times[-1] + pd.Timedelta(seconds=3.0)
    times = pd.Series(times)
    base = mdl.predict(with_times(frame, times))
    s0 = len(r11)                      # 둘째 기록 첫 행
    first_abn = s0 + k
    lead_alarm = int(base.alarm.iloc[s0:first_abn].sum())
    print(f"k={k}: 원자료 사건 {int(base.incident_id.max())}·시작 {int(base.incident_notification.sum())}·격상 {int(base.incident_escalation.sum())}, "
          f"둘째 기록 앞 {k}행 경보 {lead_alarm}행, 첫 경보 행 위치 {int(np.flatnonzero(base.alarm.iloc[s0:].to_numpy())[0])}")
    for label, faults in (("첫 이상 행 +5초 튐(대체)", [("replace", first_abn, 5)]),
                          ("첫 이상 행 뒤에 +5초 끼어듦", [("insert_after", first_abn - 1, 5)]),
                          ("첫 이상 행 시각 결측", [("nat", first_abn, 0)]),
                          ("첫 이상 행 센서 결측", [("nan", first_abn, 0)]),
                          ("첫 이상 행 +0.03초 흔들림", [("replace", first_abn, 0.03)]),
                          ("첫 이상 행 −0.15초(한 행 과거)", [("replace", first_abn, -0.15)]),
                          ("앞 조각 안 +5초 튐(행 k−3)", [("replace", s0 + k - 3, 5)])):
        f, err, _ = build(frame, times, faults)
        p = mdl.predict(f)
        s = summarize(p, err)
        print(f"    {label:28s}: 보류 {s['held']} 부호2·4 {s['c2']}·{s['c4']} · 본체 사건 {s['body_incidents']} · 시작 {s['starts']} · 격상 {s['escalations']}"
              + ("  ← 나뉨" if s["body_incidents"] > 1 else ""))

print("# 반대 방향: 두 이상 사이의 짧은 정상 기록(m행)이 오류 한 행으로 8행 미만 두 조각이 되면 사건이 닫히지 않아 둘째 이상의 시작·격상 알림이 없어지는가")
for m in (8, 10, 14, 16):
    normal_part = nt[rec == quiet[1]].iloc[:m]
    parts = [D.inputs_only(r11), D.inputs_only(normal_part), D.inputs_only(r12)]
    frame = pd.concat(parts, ignore_index=True)
    times, t = [], pd.Timestamp("2022-07-22 00:00:00")
    for p in parts:
        for i in range(len(p)):
            times.append(t); t = t + pd.Timedelta(seconds=0.1)
        t = times[-1] + pd.Timedelta(seconds=3.0)
    times = pd.Series(times)
    base = mdl.predict(with_times(frame, times))
    s0 = len(r11); mid = s0 + m // 2
    print(f"m={m}: 원자료 사건 {int(base.incident_id.max())}·시작 {int(base.incident_notification.sum())}·격상 {int(base.incident_escalation.sum())} "
          f"(정상 기록 경보 {int(base.alarm.iloc[s0:s0 + m].sum())}행)")
    for label, faults in (("정상 기록 가운데 +5초 튐", [("replace", mid, 5)]), ("정상 기록 가운데 시각 결측", [("nat", mid, 0)]),
                          ("정상 기록 가운데 센서 결측", [("nan", mid, 0)]), ("정상 기록 가운데 +0.03초 흔들림", [("replace", mid, 0.03)])):
        f, err, _ = build(frame, times, faults)
        p = mdl.predict(f)
        s = summarize(p, err)
        second = p.iloc[s0 + m + 1:]
        print(f"    {label:24s}: 사건 {s['incidents']} · 시작 {s['starts']} · 격상 {s['escalations']} · 둘째 이상의 시작·격상 알림 "
              f"{int(second.incident_notification.sum())}·{int(second.incident_escalation.sum())}")
