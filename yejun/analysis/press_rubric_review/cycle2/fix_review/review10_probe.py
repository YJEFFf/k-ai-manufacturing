"""검토 10: 결함의 기전을 CollectionUnits 계수기로 직접 보이고, '표본일 수 있는 보류 행'(기준 − 0.1초보다 늦은 보류 행)이 공백을 잇는지 판마다 잰다.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review10_probe.py

1) 계수기 추적(6차 사본에서만): 튄 행 + 앞 −12 ms·뒤 +12 ms, 이웃 두 행 뒤바뀜, 2칸 늦은 행, 끼운 빈 시각 행.
   각 받아들인 행에서 (간격, j, 도착, 보류, 표본일 수 없는 보류, 튄 행, [하한, 상한], 같은 단위?)를 찍는다.
2) 공백에 낀 '조금 이른' 보류 행: [이상 11 →3초→ q0 30행 →g초→ 이상 12]의 q0 끝(L)과 이상 12 사이에 시각이 L − 0.05초로 멈춘 행 k개.
   6차 규칙에서 이 행은 표본일 수 있는 보류 행이라 j의 상한을 k만큼 올리고 하한을 k만큼 내린다(공백을 '정확히' 메울 필요가 없다).
"""
import numpy as np
import pandas as pd

import review9_lib as L

M = L.M
NEW = hasattr(M, "CollectionUnits") and hasattr(M.CollectionUnits(), "extra")
VERSION = "a489001" if NEW else ("c7d8bba" if not hasattr(M, "CollectionUnits") else "other")
print(f"# 판 {VERSION} · 사본 {L.ENV}")
mdl = L.model()
(r11, r12, r13), (q0, q1), mag = L.parts()


def trace(name, secs):
    """secs: 도착 순서의 시각(초, None = 시각 결측). TimeOrder 부호를 먼저 매기고 incident_columns와 같은 순서로 계수기를 돌린다."""
    t0 = pd.Timestamp("2022-07-22 10:00:00", tz="UTC")
    ts = [None if x is None else t0 + pd.Timedelta(microseconds=int(round(x * 1e6))) for x in secs]
    codes, _ = M.timestamp_order(pd.Series(ts, dtype="datetime64[ns, UTC]"))
    has = np.array([x is not None for x in secs])
    spike = M.spike_rows(codes, has)
    u = M.CollectionUnits()
    print(f"## {name}")
    for i, (x, t, ev) in enumerate(zip(secs, ts, codes)):
        if ev in M.SPIKE_EVENTS and spike[i] >= 0:
            u.undo()
        acc = x is not None and ev != M.ORDER_HELD
        info = ""
        if acc and u.last is not None:
            held_now = u.held
            gap = (t - u.last).total_seconds(); j = int(round(gap / 0.1)); arrived = u.index + 1 - u.last_index
            lo, hi = arrived - held_now - u.undone, arrived - u.extra
            info = f"간격 {gap:.3f} j {j} 도착 {arrived} 보류 {held_now} 표본아닌보류 {u.extra} 튄행 {u.undone} → [{lo}, {hi}]"
        run, block = u.step(t, acc, ev == M.ORDER_HELD)
        print(f"  행 {i}: 시각 {x} 부호 {int(ev)} {'받아들임' if acc else ('보류' if ev == M.ORDER_HELD else '시각 없음')} → 단위 ({run}, {block}) {info}")


if NEW:
    trace("튄 행(0.2초 자리 대체) + 앞 행 −12 ms·뒤 행 +12 ms (행마다 흔들림 ±12 ms)", [0, .1 - .012, 5.2, .3 + .012, .4, .5])
    trace("튄 행(대체), 흔들림 없음(대조)", [0, .1, 5.2, .3, .4, .5])
    trace("이웃 두 행 뒤바뀜(0.2초 행이 먼저 옴)", [0, .1, .3, .2, .4, .5])
    trace("한 행 2칸 늦게(0.2초 행이 0.4초 뒤에 옴)", [0, .1, .3, .4, .2, .5, .6])
    trace("0.2초 자리에 빈 시각 행을 끼움(표본 대체 아님)", [0, .1, None, .2, .3])

print("## 2) 공백 안에 시각이 L − 0.05초로 멈춘 행 k개 (원자료 (2, 2, 2))")
for g, ks in ((0.3, (1, 2)), (0.5, (1, 2, 4, 5)), (1.0, (5, 9, 10)), (1.5, (5, 14, 15, 20)), (3.0, (29, 30))):
    frame, st = L.chain([r11, q0.iloc[:30], r12], gap=[3.0, g, 3.0])
    last = L.times(frame)[st[2] - 1]
    base = L.summ(mdl.predict(frame))
    out = []
    for k in ks:
        rows = pd.concat([frame.iloc[[st[2] - 1]]] * k, ignore_index=True)
        rows[L.D.TIME] = (last - pd.Timedelta(seconds=0.05)).strftime(L.FMT)
        p = mdl.predict(L.insert(frame, st[2], rows))
        out.append(f"k={k}: {L.summ(p)} 보류 {int((p.time_order_event == 1).sum())}")
    print(f"  공백 {g}초 원자료 {base} · " + " · ".join(out), flush=True)
