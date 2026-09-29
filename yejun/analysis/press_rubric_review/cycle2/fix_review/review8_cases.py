"""검토 8: 4차 사건 단위 규칙(CollectionUnits·undo_link)의 반례 탐색. 같은 입력을 두 판(8b65130·c7d8bba)에 넣어 비교한다.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_cases.py [--stream]

칸: (사건 수, 시작 알림, 격상 알림) · 시작 알림 행(입력 행 번호) · [--stream이면 청크 1·3·7·64 일괄=스트림, 핵심 행 앞뒤 접두부 인과].
무리
 A 끝 행 경보: [이상 11 → 3초 → 정상 m행 + 경보 행 1개(기록 끝) → 3초 → 이상 12]. 끝 경보 행에 흔들림·표본 누락 등 오류 한 번.
 B 첫 행 경보: [이상 11 → 3초 → 경보 행 1개(기록 첫 행) + 정상 m행 → 3초 → 이상 12]. 둘째 행에 오류 한 번.
 C 두 오류: [이상 11 → 3초 → 정상 10행 + 경보 행 + 정상 15행 → 3초 → 이상 12]. 경보 행 흔들림/앞 표본 누락 + 바로 뒤 행 +5초 튐.
 D 붙은 행 두 개: 이상 11 끝 두 행을 +d초(다음 정상 기록 앞에 붙음), 또는 이상 12 앞 경보 두 행을 −d초(앞 정상 기록 끝에 붙음).
 E 공백 0.5초 안팎의 연속 운전: [이상 11, 정상 30, 이상 12, 정상 30, 이상 13]을 공백 g초로 잇는다.
"""
import sys

import numpy as np
import pandas as pd

import review8_lib as L

STREAM = "--stream" in sys.argv
mdl = L.model()
(r11, r12, r13), (q0, q1), mag = L.parts()
print(f"# 판 {L.VERSION} · 사본 {L.ENV}")


def run(tag, frame, key=None, note=""):
    p = mdl.predict(frame)
    cells = [f"{tag:44s}", f"{L.summ(p)}", f"시작행 {L.start_rows(p)}", f"중복 {L.dup_alerts(p)}"]
    if key is not None:
        cells.append(f"핵심행 경보 {int(p.alarm.iloc[key])}·부호 {int(p.time_order_event.iloc[key])}")
    if STREAM:
        ok = all(L.same(L.stream(frame, c), p) for c in (1, 3, 7, 64))
        pre = True
        if key is not None:
            for k in range(max(1, key - 2), min(len(frame), key + 4)):
                pre &= L.same(mdl.predict(frame.iloc[:k]), p.iloc[:k])
        cells.append(f"일괄=스트림 {ok} · 접두부 {pre}")
    print(" | ".join(cells) + (f" | {note}" if note else ""))
    return p


print("## A 끝 행 경보(기록 끝 경보 행의 오류 한 번)")
for m in (8, 10, 20, 30):
    middle = pd.concat([L.D.inputs_only(q0.iloc[:m]), L.D.inputs_only(mag.iloc[:1])], ignore_index=True)
    frame, st = L.chain([r11, middle, r12])
    key = st[1] + m
    run(f"A m={m} 원자료", frame, key)
    for d in (0.021, 0.03, 0.05, 0.2, -0.03):
        run(f"A m={m} 끝 행 {d:+}초", L.shift(frame, key, d), key)
    run(f"A m={m} 끝 행 앞 표본 1개 누락", L.drop(frame, key - 1), key - 1)
    run(f"A m={m} 끝 행 앞 행 시각 결측", L.nat(frame, key - 1), key)
    run(f"A m={m} 끝 행 앞 행 센서 결측", L.sensor_nan(frame, key - 1), key)
    run(f"A m={m} 끝 행 바로 재전송", L.dup(frame, key), key)

print("## B 첫 행 경보(기록 첫 경보 행 다음 행의 오류 한 번)")
for m in (10, 20, 40):
    middle = pd.concat([L.D.inputs_only(mag.iloc[:1]), L.D.inputs_only(q0.iloc[:m])], ignore_index=True)
    frame, st = L.chain([r11, middle, r12])
    key = st[1]
    run(f"B m={m} 원자료", frame, key)
    run(f"B m={m} 둘째 행 시각 결측", L.nat(frame, key + 1), key)
    run(f"B m={m} 둘째 행 센서 결측", L.sensor_nan(frame, key + 1), key)
    run(f"B m={m} 둘째 행 +0.03초", L.shift(frame, key + 1, 0.03), key)
    run(f"B m={m} 둘째 행 −0.03초", L.shift(frame, key + 1, -0.03), key)
    run(f"B m={m} 둘째 행 누락(표본 1개)", L.drop(frame, key + 1), key)
    run(f"B m={m} 첫 행 바로 재전송", L.dup(frame, key), key)
    run(f"B m={m} 둘째 행 +5초 튐", L.shift(frame, key + 1, 5), key)
    run(f"B m={m} 셋째 행 시각 결측(대조)", L.nat(frame, key + 2), key)

print("## C 두 오류(경보 행 흔들림·앞 표본 누락 + 바로 뒤 +5초 튐)")
middle = pd.concat([L.D.inputs_only(q0.iloc[:10]), L.D.inputs_only(mag.iloc[:1]), L.D.inputs_only(q1.iloc[:15])], ignore_index=True)
frame, st = L.chain([r11, middle, r12])
key = st[1] + 10
run("C 원자료", frame, key)
run("C 경보 행 +0.03초", L.shift(frame, key, 0.03), key)
run("C 경보 행 뒤 행 +5초 튐", L.shift(frame, key + 1, 5), key)
run("C 경보 행 +0.03초 + 뒤 행 +5초 튐", L.shift(L.shift(frame, key, 0.03), key + 1, 5), key)
run("C 경보 행 앞 표본 누락", L.drop(frame, key - 1), key - 1)
run("C 경보 행 앞 표본 누락 + 뒤 행 +5초 튐", L.shift(L.drop(frame, key - 1), key, 5), key - 1)
run("C 경보 행 +0.03초 + 뒤 행 +0.4초 튐", L.shift(L.shift(frame, key, 0.03), key + 1, 0.4), key)

print("## D 붙은 행 두 개")
frame, st = L.chain([r11, q1.iloc[:14], r12])
last = st[1] - 1
run("D 늦게 찍힌 이상 끝 한 행 원자료", frame, last)
for d in (2.6, 2.7, 2.8):
    run(f"D 이상 끝 한 행 +{d}초", L.shift(frame, last, d), last)
    run(f"D 이상 끝 두 행 +{d}초", L.shift(L.shift(frame, last, d), last - 1, d), last)
second = pd.concat([L.D.inputs_only(mag.iloc[:2]), L.D.inputs_only(r12)], ignore_index=True)
frame, st = L.chain([r11, q1.iloc[:14], second])
first = st[2]
run("D 이르게 찍힌 이상 첫 행 원자료", frame, first)
for d in (2.6, 2.7, 2.8):
    run(f"D 이상 첫 한 행 −{d}초", L.shift(frame, first, -d), first)
    run(f"D 이상 첫 두 행 −{d}초", L.shift(L.shift(frame, first, -d), first + 1, -d), first)

print("## D2 붙은 행 수·간격 격자(정상 기록 m행, 붙은 간격 = 3초 − d)")
for m in (10, 14, 20, 38):
    for k in (1, 2, 3):
        cells = []
        for d in (2.55, 2.6, 2.7, 2.8, 2.85, 2.95):
            frame, st = L.chain([r11, q0.iloc[:m], r12])
            f = frame
            for j in range(k):
                f = L.shift(f, st[1] - 1 - j, d)
            cells.append(f"{d}:{''.join(map(str, L.summ(mdl.predict(f))))}")
        second = pd.concat([L.D.inputs_only(mag.iloc[:k]), L.D.inputs_only(r12)], ignore_index=True)
        cells2 = []
        for d in (2.55, 2.6, 2.7, 2.8, 2.85, 2.95):
            frame, st = L.chain([r11, q0.iloc[:m], second])
            f = frame
            for j in range(k):
                f = L.shift(f, st[2] + j, -d)
            cells2.append(f"{d}:{''.join(map(str, L.summ(mdl.predict(f))))}")
        print(f"D2 m={m:2d} k={k} 늦게 찍힌 끝 k행 " + " ".join(cells) + " || 이르게 찍힌 첫 k행 " + " ".join(cells2))

print("## D3 시계를 기록 경계에서 한 번 뒤로(이상 12부터 끝까지 −d초, 오류 한 번). 기록 사이 공백 3초가 3 − d초가 된다")
for m in (14, 38):
    frame, st = L.chain([r11, q0.iloc[:m], r12])
    t = pd.to_datetime(frame[L.D.TIME])
    for d in (2.4, 2.6, 2.8, 2.88, 2.95):
        f = frame.copy()
        f.loc[st[2]:, L.D.TIME] = (t[st[2]:] - pd.Timedelta(seconds=d)).dt.strftime(L.FMT)
        run(f"D3 m={m} 이상 12부터 −{d}초", f, st[2])

print("## E 공백 0.5초 안팎의 연속 운전")
for n in (30, 49):
    for g in (0.3, 0.45, 0.5, 0.55, 1.0, 3.0):
        frame, st = L.chain([r11, q1.iloc[:n], r12, q1.iloc[:n], r13], gap=g)
        run(f"E 정상 {n}행 · 공백 {g}초", frame, None, f"부분 시작 {st}")
cont = pd.concat([L.D.inputs_only(r11), L.D.inputs_only(q1), L.D.inputs_only(q0), L.D.inputs_only(r12)], ignore_index=True)
for g in (0.3, 3.0):
    frame, st = L.chain([r11, q1, q0, r12], gap=g)
    run(f"E 정상 {len(q1)}+{len(q0)}행(두 기록) · 공백 {g}초", frame, None, f"부분 시작 {st}")
print("R8DONE")
