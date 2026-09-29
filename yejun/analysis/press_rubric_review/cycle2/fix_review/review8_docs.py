"""검토 8: README·OPERATIONS의 시각 규칙 문장을 직접 잰다(8b65130 사본).

 1) "기록 첫 행이 0.12~0.3초 늦게 찍히면 그 뒤 1~2행이 보류된다": TimeOrder만 돌려 첫 행 지연 d별 보류 행 수.
 2) "입력의 맨 첫 행이 튀면 … 뒤 1~2행을 보류한 뒤 이어 간다(튄 행으로 확인하지 않는다)": 모델 예측의 부호.
 3) 경고 문구(R7-05 수정): 기록 끝 튐 뒤 기록이 짧을 때 경고가 세는 보류 행 수와 실제 보류 행 수.
 4) 품질 시간창: 이르게 찍힌 이상 첫 행(1행으로도 경보가 나는 행)이 앞 정상 기록 끝에 붙을 때 사건별 창(두 판 비교는 판마다 실행).
 5) CollectionUnits 단위 판정의 경계: 정상 간격 판정 abs(gap − 0.1) ≤ 0.02의 부동소수 경계(±20 ms 대칭인가).

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_docs.py
"""
import numpy as np
import pandas as pd

import review8_lib as L

M, D = L.M, L.D
print(f"# 판 {L.VERSION}")
t0 = pd.Timestamp("2022-07-22 10:00:00", tz="UTC")

print("## 1) 기록 첫 행 지연 d초 → 보류 행 수·부호(앞 기록 10행 → 3초 → 뒤 기록 10행, 뒤 기록 첫 행만 +d)")
for d in (0.05, 0.1, 0.101, 0.11, 0.119, 0.12, 0.13, 0.2, 0.201, 0.25, 0.3, 0.301, 0.35, 0.5):
    ts = [t0 + pd.Timedelta(seconds=0.1 * i) for i in range(10)]
    s2 = ts[-1] + pd.Timedelta(seconds=3)
    ts += [s2 + pd.Timedelta(seconds=0.1 * i + (d if i == 0 else 0)) for i in range(10)]
    codes, _ = M.timestamp_order(pd.Series(ts))
    print(f"  d={d:<6}: 보류 {int((codes == M.ORDER_HELD).sum())}행 · 부호 {''.join(map(str, codes[10:]))}")

mdl = L.model()
(r11, r12, r13), (q0, q1), mag = L.parts()
print("## 2) 입력 맨 첫 행 튐(이상 기록 11 → 3초 → 이상 12, 행 0을 +X초)")
frame, st = L.chain([r11, r12])
for x in (0.5, 5, 3600):
    p = mdl.predict(L.shift(frame, 0, x))
    print(f"  +{x}초: 보류 {int((p.status == 'bad_time_order').sum())}행 · 앞 6행 부호 {p.time_order_event.iloc[:6].tolist()} · 사건 {L.summ(p)} · 시작 행 {L.start_rows(p)}")

print("## 3) 기록 끝 튐 뒤 짧은 기록: 경고 문구의 보류 행 수 대 실제 보류 행 수")
for n in (1, 2, 3, 10):
    frame, st = L.chain([r11, q0.iloc[:n], r12])
    f = L.shift(frame, st[1] - 1, 10.0)     # 이상 11 끝 행 +10초(다음 기록들보다 늦음)
    p = mdl.predict(f)
    held = int((p.status == "bad_time_order").sum())
    w = M.timing_warning(p)
    seg = [s for s in w.split(". ") if "튄" in s]
    print(f"  뒤 정상 기록 {n}행: 실제 보류 {held}행 · 부호 4 {int((p.time_order_event == 4).sum())} · 경고: {seg[0] if seg else '(튐 경고 없음)'}")

print("## 4) 품질 시간창(사건별 suspect_from ~ suspect_to, open)")
second = pd.concat([D.inputs_only(mag.iloc[:1]), D.inputs_only(r12)], ignore_index=True)
for m in (14, 38):
    frame, st = L.chain([r11, q0.iloc[:m], second])
    for tag, f in (("원자료", frame), ("첫 행 −2.7초", L.shift(frame, st[2], -2.7))):
        p = mdl.predict(f)
        q = M.cases(p)
        inc = M.incidents(q, p) if len(q) else pd.DataFrame()
        rows = [(int(r.incident_id), str(r.suspect_from)[11:23], str(r.suspect_to)[11:23], bool(r.suspect_open)) for r in inc.itertuples()] if len(inc) else []
        print(f"  m={m} {tag}: 사건 {L.summ(p)} · 창 {rows}")

print("## 5) 정상 간격 판정의 부동소수 경계(바로 이웃 행 간격 g초가 정상 간격인가)")
if hasattr(M, "CollectionUnits"):
    for g in (0.079, 0.08, 0.0801, 0.12, 0.1199, 0.1201):
        u = M.CollectionUnits()
        out = [u.step(t0 + pd.Timedelta(seconds=x), True) for x in (0, 5, 5 + g, 5 + g + 0.1)]
        print(f"  g={g}: 공백 뒤 첫 행이 혼자 단위인가 {out[1][0] != out[2][0]} · abs(g−0.1)={abs(g - D.DT)!r}")
else:
    print("  (이 판에는 CollectionUnits가 없다)")
b = pd.Series([t0, t0 + pd.Timedelta(seconds=0.08), t0 + pd.Timedelta(seconds=0.2)])
print(f"  layout 기록 경계(간격 0.08초·0.12초): {b.diff().dt.total_seconds().sub(D.DT).abs().gt(M.TIME_TOL_S).tolist()}")
