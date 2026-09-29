"""검토 9: 5차 규칙의 작동 방식 확인(873e4e1 사본 전용).

 1) CollectionUnits의 허용오차 검사(abs(gap − j·0.1) ≤ UNIT_TOL_S)가 결과를 바꾸는 간격이 있는가(j = round(gap/0.1)이라 늘 참인지).
    간격 0~2초(1 µs 해상도 대신 0.1 ms 격자)와 도착 행 수 n = 1~20에서 '1 ≤ j ≤ n'만으로 정한 결과와 비교한다. 이어지는 간격의 범위도 적는다.
 2) G1 반례의 단위 배정: [이상 11 →3초→ q0 30행 →1.5초→ 이상 12] 사이에 빈 시각 15행. 행마다 (연속 수집, 블록)·경보·사건.
 3) 약한 이상 0.1σ, 경계 577에 앞 기록 끝 30행 역순 재전송(review9_weak에서 5차만 사건 +1).
 4) 연속 흔들림 분해: 약한 이상 0.1σ에 U(±30 ms)·U(±40 ms)(시드 1000~1004). 흔들린 예측의 경보를 그대로 두고 사건 단위만
    흔들리지 않은 시각으로 다시 매기면 사건 수가 어떻게 되는가(사건 증가가 단위 규칙 탓인지, 경보 감소 탓인지).

    REVIEW_ENV=<873e4e1 사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review9_probe.py
"""
import numpy as np
import pandas as pd

import review7_weak as W
import review9_lib as L

M = L.M
assert L.VERSION == "873e4e1", L.VERSION

print("## 1) 허용오차 검사가 결과를 바꾸는 간격")
t0 = pd.Timestamp("2022-07-22 10:00:00", tz="UTC")
changed = 0
ranges = {}
for n in range(1, 21):
    ok = []
    for us in range(0, 2_000_001, 100):
        gap = pd.Timedelta(microseconds=us).total_seconds()
        j = int(round(gap / M.D.DT))
        full = 1 <= j <= n and abs(gap - j * M.D.DT) <= M.UNIT_TOL_S
        only = 1 <= j <= n
        changed += full != only
        if full:
            ok.append(gap)
    ranges[n] = (min(ok), max(ok)) if ok else None
print(f"  허용오차 검사로 결과가 달라진 (간격, n) 칸: {changed}")
print("  같은 단위로 잇는 간격 범위(0.1 ms 격자) n: (최소, 최대) = " + ", ".join(f"{n}: {r}" for n, r in ranges.items() if n in (1, 2, 3, 5, 10, 15, 20)))


def show(p, lo, hi, units_times=None):
    u = M.CollectionUnits()
    tt = pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce")
    ru = [u.step(t, not pd.isna(t) and ev != M.ORDER_HELD) for t, ev in zip(tt, p.time_order_event)]
    for i in range(lo, hi):
        r = p.iloc[i]
        print(f"  행 {i:4d} 시각 {str(r.timestamp)[11:23]:12s} 상태 {r.status:15s} 부호 {int(r.time_order_event)} 단위 {ru[i]} 경보 {int(r.alarm)} "
              f"사건 {int(r.incident_id)} 시작 {int(r.incident_notification)}")


print("## 2) G1 반례: 공백 1.5초 사이 빈 시각 15행")
(r11, r12, r13), (q0, q1), mag = L.parts()
mdl = L.model()
frame, st = L.chain([r11, q0.iloc[:30], r12], gap=[3.0, 1.5, 3.0])
f = L.insert(frame, st[2], L.blank_rows(frame, 15, st[1]))
p = mdl.predict(f)
print(f"  원자료 {L.summ(mdl.predict(frame))} → 빈 시각 15행 {L.summ(p)}")
show(p, st[1] - 1, st[1] + 1)
show(p, st[2] - 2, st[2] + 15 + 12)

print("## 3) 약한 이상 0.1σ 경계 577 앞 기록 끝 30행 역순 재전송")
_, WM, F, T = W.setup(0.1)
base = WM.predict(F)
rec = L.D.segments(F)
starts = np.flatnonzero(np.r_[True, rec[1:] != rec[:-1]])
s = 577
prev = int(starts[starts < s][-1])
late = F.iloc[max(prev, s - 30):s].iloc[::-1].reset_index(drop=True)
g = L.insert(F, s, late)
pg = WM.predict(g)
print(f"  원자료 {L.summ(base)} → {L.summ(pg)} · 앞 기록 행 {prev}~{s - 1}({s - prev}행), 재전송 {len(late)}행")
print(f"  원자료 사건 시작 행 {L.start_rows(base)} · 변형 사건 시작 행 {L.start_rows(pg)}")
show(pg, s - 2, s + 2)
show(pg, s + len(late) - 1, s + len(late) + 12)

print("## 4) 연속 흔들림 분해")
for sj in (0.03, 0.04):
    out = []
    for seed in range(5):
        e = np.random.default_rng(1000 + seed).uniform(-sj, sj, len(F))
        fj = F.copy()
        fj[L.D.TIME] = (T + pd.to_timedelta(np.round(e * 1e6), unit="us")).dt.strftime(L.FMT)
        pj = WM.predict(fj)
        a = pj.alarm.to_numpy(); why = pj.reason.to_numpy(); ok = pj.status.eq("ok").to_numpy()
        orig_t = pd.to_datetime(F[L.D.TIME], format="mixed", utc=True)
        inc_orig_units = M.incident_columns(a, why, orig_t, ok, np.zeros(len(a), int))
        inc_jit = M.incident_columns(a, why, pd.to_datetime(pj.timestamp, format="mixed", utc=True, errors="coerce"), ok, pj.time_order_event.to_numpy())
        out.append((int(pj.alarm.sum()), int(inc_jit[:, 0].max()), int(inc_orig_units[:, 0].max())))
    print(f"  ±{sj * 1000:.0f} ms (경보 행, 사건: 흔들린 시각 단위, 사건: 흔들리지 않은 시각 단위) = {out}")

print("## 5) 약한 이상 0.05σ 경계 716에 빈 시각 30행(review9_weak에서 5차만 사건 +1)")
_, WM5, F5, T5 = W.setup(0.05)
b5 = WM5.predict(F5)
s = 716
g5 = L.insert(F5, s, L.blank_rows(F5, 30, s))
p5 = WM5.predict(g5)
rec5 = L.D.segments(F5)
st5 = np.flatnonzero(np.r_[True, rec5[1:] != rec5[:-1]])
prev = int(st5[st5 < s][-1]); nxt = int(st5[st5 > s][0])
print(f"  원자료 {L.summ(b5)} → {L.summ(p5)} · 앞 기록 {prev}~{s - 1}, 뒤 기록 {s}~{nxt - 1}, 공백 {(T5[s] - T5[s - 1]).total_seconds():.2f}초")
print(f"  원자료 시작 행 {L.start_rows(b5)} · 변형 시작 행 {L.start_rows(p5)}(변형은 {s}행부터 30행 밀림)")
print("  원자료:")
show(b5, prev, nxt + 3)
print("  변형:")
show(p5, prev, s + 1)
show(p5, s + 30, nxt + 30 + 3)
