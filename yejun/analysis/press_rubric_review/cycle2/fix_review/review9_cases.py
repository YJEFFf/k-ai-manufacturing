"""검토 9: 5차 사건 단위 규칙(CollectionUnits, '도착한 행 수로 설명되는 간격')의 반례 탐색. 같은 입력을 판마다 돌려 줄 단위로 비교한다.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review9_cases.py [--stream] > review9_cases_<판>.tsv

출력 한 줄: 무리 \t 상황 \t (사건 수, 시작 알림, 격상 알림) \t 시작 알림 행 \t 사건마다 알림 두 번 \t [일괄=스트림(청크 1·7·64)]
무리
 G1 빈 시각 행: [이상 11 →3초→ 정상 q0 30행 →g초→ 이상 12]의 q0 끝과 이상 12 사이(또는 이상 11과 q0 사이)에 시각이 빈 행 k개를 끼운다.
    (행 수가 공백 길이와 맞지 않는 시각 결측 행: 빈 줄·헤더·시각 없는 재전송). 원자료는 (2,2,2).
 G2 보류 행: 같은 자리에 지난 자료 k행을 역순(계속 보류) 또는 정순 2행(새 기준 전)으로 끼운다.
 G3 기록 사이 공백 g와 k의 경계: 공백 g초, 빈 시각 행 k개. 5차 규칙이 이을 조건은 g ≤ 0.1·(k+1) + 0.05.
 G4 중복 행(같은 시각 그대로 재전송): R7-01 상황(정상 10행 + 이상 12, 첫 이상 행)과 14행 정상 기록 가운데.
 G5 흔들림 경계: R7-01 상황의 첫 이상 행 하나를 ±0.045·±0.05·±0.055초, 또는 이웃 두 행을 반대 방향으로 ±0.03초.
 G6 진행 중 이상의 시계 되감기 d초·끝 k행 재전송(README 알려진 한계 '0.35초 이상·5행 이상' 확인).
 G7 옮겨진 행이 붙는 간격 폭: 이상 11 끝 행을 +d초(q0 앞), 이상 12 첫 경보 행을 −d초(q0 뒤).
 G8 짧은 정상 기록 1~9행(공백 1.5초)을 사이에 둔 두 이상.
"""
import sys

import numpy as np
import pandas as pd

import review9_lib as L

STREAM = "--stream" in sys.argv
mdl = L.model()
(r11, r12, r13), (q0, q1), mag = L.parts()
print(f"# 판 {L.VERSION} · 사본 {L.ENV} · 부품 행 수 r11 {len(r11)} r12 {len(r12)} r13 {len(r13)} q0 {len(q0)} q1 {len(q1)}", file=sys.stderr)


def run(group, tag, frame):
    p = mdl.predict(frame)
    cells = [group, tag, str(L.summ(p)), str(L.start_rows(p)), f"중복 {L.dup_alerts(p)}"]
    if STREAM:
        cells.append("일괄=스트림 " + str(all(L.same(L.stream(frame, c), p) for c in (1, 7, 64))))
    print("\t".join(cells), flush=True)
    return p


# G1·G2·G3: q0 30행을 사이에 둔 두 이상, 공백 g
def base(g_before=3.0, g_after=3.0, m=30):
    return L.chain([r11, q0.iloc[:m], r12], gap=[g_before, g_after, 3.0])


for g in (0.3, 0.5, 1.0, 1.5, 2.0, 3.0):
    frame, st = base(3.0, g)
    run("G1", f"q0 뒤 공백 {g}초 원자료", frame)
    for k in (2, 5, 10, 15, 20, 30):
        run("G1", f"q0 뒤 공백 {g}초 빈 시각 {k}행(q0 끝과 이상 12 사이)", L.insert(frame, st[2], L.blank_rows(frame, k, st[1])))
for g in (1.5, 3.0):
    frame, st = base(g, 3.0)
    for k in (10, 20, 30):
        run("G1", f"q0 앞 공백 {g}초 빈 시각 {k}행(이상 11 끝과 q0 사이)", L.insert(frame, st[1], L.blank_rows(frame, k, st[1])))

for g in (0.3, 0.5, 1.5, 3.0):
    frame, st = base(3.0, g)
    q_end = st[2]
    for k in (2, 5, 10, 20, 30):
        late = frame.iloc[st[1]:st[1] + k].iloc[::-1].reset_index(drop=True)      # q0 앞 k행을 역순으로 다시 보냄(계속 보류)
        run("G2", f"q0 뒤 공백 {g}초 q0 앞 {k}행 역순 재전송", L.insert(frame, q_end, late))
    late = frame.iloc[st[1]:st[1] + 2].reset_index(drop=True)                     # 정순 2행(새 기준 전)
    run("G2", f"q0 뒤 공백 {g}초 q0 앞 2행 정순 재전송", L.insert(frame, q_end, late))

# G4 중복 행
middle = pd.concat([L.D.inputs_only(q0.iloc[:10]), L.D.inputs_only(r12)], ignore_index=True)
frame, st = L.chain([r11, middle, r13], start="2022-07-21")
key = st[1] + 10
run("G4", "R7-01 상황 원자료", frame)
run("G4", "R7-01 상황 첫 이상 행 중복(같은 시각)", L.dup(frame, key))
run("G4", "R7-01 상황 첫 이상 행 앞 행 중복", L.dup(frame, key - 1))
frame14, st14 = L.chain([r11, q1.iloc[:14], r12])
run("G4", "14행 정상 기록 원자료", frame14)
run("G4", "14행 정상 기록 가운데(7번째) 행 중복", L.dup(frame14, st14[1] + 7))

# G5 흔들림 경계
for d in (0.045, 0.049, 0.05, 0.051, 0.055, -0.045, -0.049, -0.05, -0.051, -0.055):
    run("G5", f"R7-01 상황 첫 이상 행 {d:+}초", L.shift(frame, key, d))
for d in (0.025, 0.03, 0.04):
    run("G5", f"R7-01 상황 첫 이상 행 +{d}초·다음 행 −{d}초", L.shift(L.shift(frame, key, d), key + 1, -d))
    run("G5", f"R7-01 상황 첫 이상 행 −{d}초·다음 행 +{d}초", L.shift(L.shift(frame, key, -d), key + 1, d))
for d in (0.025, 0.03):
    run("G5", f"14행 정상 기록 7·8번째 행 +{d}·−{d}초", L.shift(L.shift(frame14, st14[1] + 7, d), st14[1] + 8, -d))

# G6 진행 중 이상(이상 12, 42행)의 시계 되감기·재전송
frame6, st6 = L.chain([r11, r12, r13])
mid = st6[1] + 20
run("G6", "이상 11·12·13 원자료", frame6)
for d in (0.2, 0.3, 0.31, 0.33, 0.35, 0.4, 1.0):
    run("G6", f"이상 12 21행부터 끝까지 −{d}초", L.shift(frame6, list(range(mid, st6[2])), -d))
for k in (2, 3, 4, 5, 6):
    resend = frame6.iloc[mid - k:mid].reset_index(drop=True)
    run("G6", f"이상 12 20행 뒤 앞 {k}행(20행까지) 정순 재전송", L.insert(frame6, mid, resend))

# G7 옮겨진 행이 붙는 간격
frame7, st7 = base(3.0, 3.0)
for d in (2.8, 2.84, 2.85, 2.86, 2.88, 2.9, 2.92, 2.94, 2.95, 2.96, 3.0):
    run("G7", f"이상 11 끝 행 +{d}초(q0 첫 행 {3.0 - d:.2f}초 앞)", L.shift(frame7, st7[1] - 1, d))
second = pd.concat([L.D.inputs_only(mag.iloc[:1]), L.D.inputs_only(r12)], ignore_index=True)
frame7b, st7b = L.chain([r11, q0.iloc[:30], second])
for d in (2.8, 2.84, 2.85, 2.86, 2.88, 2.9, 2.92, 2.94, 2.95, 2.96, 3.0):
    run("G7", f"이상 12 첫 경보 행 −{d}초(q0 끝 {3.0 - d:.2f}초 뒤)", L.shift(frame7b, st7b[2], -d))

# G8 짧은 정상 기록
for m in range(1, 10):
    f8, _ = L.chain([r11, q0.iloc[:m], r12], gap=1.5)
    run("G8", f"정상 {m}행(공백 1.5초)", f8)
