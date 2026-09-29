"""검토 10: 6차 사건 단위 규칙(CollectionUnits: 0.1초 × j ± 40 ms, j ∈ [도착 − 보류 − 튄 행, 도착 − 표본일 수 없는 보류 행], 1 ms 중복)의 반례 탐색.
같은 입력을 판마다 돌려 줄 단위로 비교한다. 입력 구성은 검토 9 도구(review9_lib)의 부품·잇기만 쓴다(판과 무관).

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review10_cases.py [--stream] > 결과.tsv

출력 한 줄: 무리 \t 상황 \t (사건 수, 시작 알림, 격상 알림) \t 시작 알림 행 \t 사건마다 알림 두 번 \t 보류 행 \t 부호(2·3·4 수) \t [일괄=스트림(청크 1·2·3·7·64·무작위)]
무리(R7-01 상황 = [이상 11 →3초→ 정상 q0 10행 + 이상 12 →3초→ 이상 13], 원자료 (1,1,1). 14행 상황 = [이상 11 → q1 14행 → 이상 12], 원자료 (2,2,2))
 H1 이웃 두 행 순서 뒤바뀜(한 행이 한 칸 늦게 도착)
 H2 한 행이 2·3칸 늦게 도착(늦은 행은 보류)
 H3 시각이 빈 행을 표본 자리가 아닌 곳에 끼움(빈 줄·시각 없는 재전송)
 H4 튄 행 한 개 + 사양 안 흔들림(행마다 ±20 ms 이하): 튄 행 앞뒤 행이 반대로 흔들려 튐 예외(±20 ms)를 벗어남
 H5 '표본일 수 있는 보류 행'의 경계(기준 − 0.1초): 기록 끝 L 뒤에 시각 L − d인 행을 한 개 끼우고 다음 기록이 L + 0.2초에 시작(표본 하나 누락)
 H6 1 ms 중복 경계
 H7 사양 안 흔들림만(행마다 ±20 ms)으로 이웃 간격이 40 ms 벗어날 때 기록·보류·튐 판정
"""
import sys

import numpy as np
import pandas as pd

import review9_lib as L

STREAM = "--stream" in sys.argv
VERSION = ("a489001" if hasattr(L.M.CollectionUnits(), "extra") else ("873e4e1" if hasattr(L.M, "UNIT_TOL_S") else "8b65130")) if hasattr(L.M, "CollectionUnits") else "c7d8bba"
mdl = L.model()
(r11, r12, r13), (q0, q1), mag = L.parts()
print(f"# 판 {VERSION} · 사본 {L.ENV}", file=sys.stderr)
RNG = np.random.default_rng(10)


def run(group, tag, frame):
    p = mdl.predict(frame)
    ev = p.time_order_event.to_numpy()
    cells = [group, tag, str(L.summ(p)), str(L.start_rows(p)), f"중복 {L.dup_alerts(p)}", f"보류 {int((ev == 1).sum())}",
             f"부호2·3·4 {int((ev == 2).sum())}·{int((ev == 3).sum())}·{int((ev == 4).sum())}"]
    if STREAM:
        chunks = (1, 2, 3, 7, 64, list(RNG.integers(1, 9, 50)))
        cells.append("일괄=스트림 " + str(all(L.same(L.stream(frame, c), p) for c in chunks)))
    print("\t".join(cells), flush=True)
    return p


def move(frame, row, m):
    """row 행을 m칸 늦게 도착시킨다(시각은 그대로)."""
    order = list(range(len(frame)))
    order.pop(row)
    order.insert(row + m, row)
    return frame.iloc[order].reset_index(drop=True)


middle = pd.concat([L.D.inputs_only(q0.iloc[:10]), L.D.inputs_only(r12)], ignore_index=True)
frame, st = L.chain([r11, middle, r13], start="2022-07-21")
key = st[1] + 10                     # 이상 12의 첫 행(이 앞 10행이 정상)
frame14, st14 = L.chain([r11, q1.iloc[:14], r12])
mid14 = st14[1] + 7

run("H0", "R7-01 상황 원자료", frame)
run("H0", "14행 상황 원자료", frame14)

# H1 뒤바뀜
for r, name in ((key - 2, "정상 9·10번째"), (key - 1, "정상 끝 행과 첫 이상 행"), (key, "첫 이상 행과 둘째 이상 행"), (key + 5, "이상 6·7번째")):
    run("H1", f"R7-01 상황 {name} 뒤바뀜", move(frame, r, 1))
for r in (mid14 - 1, mid14, mid14 + 1):
    run("H1", f"14행 상황 {r - st14[1] + 1}·{r - st14[1] + 2}번째 행 뒤바뀜", move(frame14, r, 1))

# H2 늦게 도착
for m in (2, 3):
    run("H2", f"R7-01 상황 정상 끝 행 {m}칸 늦게", move(frame, key - 1, m))
    run("H2", f"R7-01 상황 첫 이상 행 {m}칸 늦게", move(frame, key, m))
    run("H2", f"14행 상황 7번째 행 {m}칸 늦게", move(frame14, mid14, m))

# H3 표본 자리가 아닌 빈 시각 행
run("H3", "R7-01 상황 첫 이상 행 앞에 빈 시각 1행 끼움", L.insert(frame, key, L.blank_rows(frame, 1, key)))
run("H3", "R7-01 상황 정상 5번째 행 앞에 빈 시각 1행 끼움", L.insert(frame, key - 5, L.blank_rows(frame, 1, key - 5)))
run("H3", "R7-01 상황 첫 이상 행을 빈 시각으로(표본 자리, 대조)", L.nat(frame, key))
run("H3", "14행 상황 가운데에 빈 시각 1행 끼움", L.insert(frame14, mid14, L.blank_rows(frame14, 1, mid14)))

# H4 튄 행 + 사양 안 흔들림
for r, name in ((key, "첫 이상 행"), (key - 1, "정상 끝 행"), (key + 3, "이상 4번째 행")):
    f = L.shift(frame, r, 5.0)
    run("H4", f"R7-01 상황 {name} +5초 튐(흔들림 없음, 대조)", f)
    for d in (0.012, 0.015, 0.02):
        g = L.shift(L.shift(f, r - 1, -d), r + 1, d)
        run("H4", f"R7-01 상황 {name} +5초 튐, 앞 행 −{d * 1000:.0f} ms·뒤 행 +{d * 1000:.0f} ms", g)
f = L.shift(frame14, mid14, 5.0)
run("H4", "14행 상황 7번째 행 +5초 튐(대조)", f)
for d in (0.012, 0.02):
    run("H4", f"14행 상황 7번째 행 +5초 튐, 앞 행 −{d * 1000:.0f} ms·뒤 행 +{d * 1000:.0f} ms", L.shift(L.shift(f, mid14 - 1, -d), mid14 + 1, d))
# 끼어든 튄 행(표본 대체가 아님): 첫 이상 행 앞에 +5초 사본, 앞 행 −12 ms·뒤 행 +12 ms(간격 0.124초 = 1칸 + 24 ms)
ins = frame.iloc[[key]].copy(); ins[L.D.TIME] = (L.times(frame)[key - 1] + pd.Timedelta(seconds=5)).strftime(L.FMT)
fi = L.insert(frame, key, ins)
run("H4", "R7-01 상황 첫 이상 행 앞에 +5초 행 끼움(대조)", fi)
run("H4", "R7-01 상황 첫 이상 행 앞에 +5초 행 끼움, 앞 행 −12 ms·뒤 행 +12 ms", L.shift(L.shift(fi, key - 1, -0.012), key + 1, 0.012))

# H5 보류 행의 '표본일 수 있음' 경계
frame5, st5 = L.chain([r11, q0.iloc[:30], r12], gap=[3.0, 0.2, 3.0])
last = L.times(frame5)[st5[2] - 1]
run("H5", "q0 30행 뒤 0.2초(표본 1 누락) 이상 12 원자료", frame5)
for d in (0.15, 0.1, 0.0999, 0.099, 0.05):
    row = frame5.iloc[[st5[2] - 1]].copy(); row[L.D.TIME] = (last - pd.Timedelta(seconds=d)).strftime(L.FMT)
    run("H5", f"q0 끝(L) 뒤에 시각 L−{d}초 행 끼움(보류)", L.insert(frame5, st5[2], row))
frame5b, st5b = L.chain([r11, q0.iloc[:30], r12], gap=[3.0, 0.3, 3.0])
last = L.times(frame5b)[st5b[2] - 1]
run("H5", "q0 30행 뒤 0.3초(표본 2 누락) 원자료", frame5b)
for d in (0.099, 0.05):
    rows = pd.concat([frame5b.iloc[[st5b[2] - 1]]] * 2, ignore_index=True); rows[L.D.TIME] = (last - pd.Timedelta(seconds=d)).strftime(L.FMT)
    run("H5", f"q0 끝(L) 뒤에 시각 L−{d}초 행 2개 끼움(보류)", L.insert(frame5b, st5b[2], rows))

# H6 1 ms 중복 경계(정상 끝 행을 다시 보냄, 시각 +e)
for e in (0.0, 0.0005, 0.001, 0.0011, 0.002):
    row = frame.iloc[[key - 1]].copy(); row[L.D.TIME] = (L.times(frame)[key - 1] + pd.Timedelta(seconds=e)).strftime(L.FMT)
    run("H6", f"R7-01 상황 정상 끝 행 재전송 +{e * 1000:.1f} ms", L.insert(frame, key, row))

# H7 사양 안 흔들림만: 한 행 −20 ms, 다음 행 +20 ms(이웃 간격 0.14초)
for r, name in ((key - 1, "정상 끝 행"), (key, "첫 이상 행")):
    run("H7", f"R7-01 상황 {name} −20 ms·다음 행 +20 ms", L.shift(L.shift(frame, r, -0.02), r + 1, 0.02))
run("H7", "14행 상황 7번째 −20 ms·8번째 +20 ms", L.shift(L.shift(frame14, mid14, -0.02), mid14 + 1, 0.02))
