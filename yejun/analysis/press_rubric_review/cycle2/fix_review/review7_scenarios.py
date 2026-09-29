"""검토 7: 시각 오류 상황표. 대회 이상 파일(600행, 원자료 사건 1·시작 1·격상 1·경보 569행)과, 앞뒤에 경보 없는 정상 기록을 붙인
맥락 자료(정상 6기록 → 3초 → 이상 파일 → 3초 → 정상 6기록)에 시각 오류를 넣고 판별 결과를 센다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_scenarios.py [--stream] [--out 파일.jsonl]
--stream이면 상황마다 스트림(청크 1·2·3·7·128·무작위)과 일괄이 같은지, 부호가 있는 행 주변의 접두부 예측이 바뀌지 않는지(인과)도 본다.
'본체'는 오류를 넣은 행(튄·끼운·옮긴·재전송 행)을 뺀 행이다. 본체 사건 수가 원자료보다 많으면 오류 한 번이 이상 한 번을 나눈 것이다.
"""
import argparse
import json
import sys

from review7_lib import *  # noqa: F401,F403

ap = argparse.ArgumentParser()
ap.add_argument("--stream", action="store_true")
ap.add_argument("--out")
ap.add_argument("--only")
args = ap.parse_args()

from review7_scenarios_ctx import MDL as mdl, AB, TA, CF, TC, N0, N1, BASE  # noqa: E402
# 기록 11 = 280~329행, 기록 12 = 330~371행(기록 사이 공백 2.583초)
SC = []


def sc(sid, group, desc, base, faults=None, frame=None, err=None):
    SC.append(dict(sid=sid, group=group, desc=desc, base=base, faults=faults or [], frame=frame, err=err))


def times_frame(base, times, err_rows=()):
    fr = AB if base == "ab" else CF
    err = np.zeros(len(fr), bool); err[list(err_rows)] = True
    return with_times(fr, times), err


def reorder(base, order, err_positions):
    fr = AB if base == "ab" else CF
    f = fr.iloc[order].reset_index(drop=True)
    err = np.zeros(len(f), bool); err[list(err_positions)] = True
    return f, err


# A. 기록 안 한 행의 시각 오류(행 305, 기록 11 안)
for d in (0.05, 0.13, 0.2, 0.3, 0.5, 5, 61, 3600):
    sc(f"A1_{d}", "A 기록 안 한 행", f"행 305 시각 +{d}초(표본 대체)", "ab", [("replace", 305, d)])
for d in (0.05, 0.13, 0.5, 5, 3600):
    sc(f"A2_{d}", "A 기록 안 한 행", f"행 305 뒤에 +{d}초 사본 끼움(끼어듦)", "ab", [("insert_after", 305, d)])
for d in (0.05, 0.15, 0.3, 1, 3600):
    sc(f"A3_{d}", "A 기록 안 한 행", f"행 305 시각 −{d}초(한 행 과거로)", "ab", [("replace", 305, -d)])
# B. 기록 경계의 튐
for d in (0.5, 2.7, 5, 61, 3600):
    sc(f"B1_{d}", "B 기록 경계", f"기록 끝 행 329 +{d}초(공백 2.58초)", "ab", [("replace", 329, d)])
for d in (0.13, 0.25, 0.5, 5, 3600):
    sc(f"B2_{d}", "B 기록 경계", f"기록 첫 행 330 +{d}초", "ab", [("replace", 330, d)])
for d in (0.5, 5, 3600):
    sc(f"B3_{d}", "B 기록 경계", f"기록 끝 329 뒤에 +{d}초 사본 끼움", "ab", [("insert_after", 329, d)])
sc("B4_5", "B 기록 경계", "자료 첫 행 0 +5초", "ab", [("replace", 0, 5)])
sc("B4_3600", "B 기록 경계", "자료 첫 행 0 +3600초", "ab", [("replace", 0, 3600)])
sc("B5_5", "B 기록 경계", "자료 끝 행 599 +5초", "ab", [("replace", 599, 5)])
# C. 연속·여러 튐
for d in (5, 3600):
    sc(f"C1_{d}", "C 연속 튐", f"행 305·306 모두 +{d}초(2행)", "ab", [("replace", 305, d), ("replace", 306, d)])
    sc(f"C2_{d}", "C 연속 튐", f"행 305~307 모두 +{d}초(3행)", "ab", [("replace", 305, d), ("replace", 306, d), ("replace", 307, d)])
sc("C3", "C 연속 튐", "같은 기록 안 두 곳(305·310) +5초", "ab", [("replace", 305, 5), ("replace", 310, 5)])
sc("C4a", "C 연속 튐", "305 +7초, 306 +5초(둘째가 첫째보다 이름)", "ab", [("replace", 305, 7), ("replace", 306, 5)])
sc("C4b", "C 연속 튐", "305 +5초, 306 +7초(둘째가 더 늦음)", "ab", [("replace", 305, 5), ("replace", 306, 7)])
sc("C5", "C 연속 튐", "튄 행(+5초 끼어듦) 두 번 도착(R5-04)", "ab", [("insert_after", 305, 5), ("insert_after", 305, 5)])
# D. 재전송·중복·역순·늦은 도착
sc("D1a", "D 재전송·순서", "행 305 두 번(바로 뒤 재전송)", "ab", [("dup", 305, 0)])
sc("D1b", "D 재전송·순서", "기록 끝 행 329 두 번", "ab", [("dup", 329, 0)])
for n in (1, 2, 3, 5, 10):
    order = list(range(310)) + list(range(300, 300 + n)) + list(range(310, 600))
    f, e = reorder("ab", order, range(310, 310 + n))
    sc(f"D2_{n}", "D 재전송·순서", f"행 300~{299 + n}({n}행)을 309 뒤에 재전송", "ab", frame=f, err=e)
order = list(range(280)) + list(range(329, 279, -1)) + list(range(330, 600))
f, e = reorder("ab", order, range(280, 330))
sc("D3", "D 재전송·순서", "기록 11(50행)을 역순으로 보냄", "ab", frame=f, err=e)
sc("D4a", "D 재전송·순서", "이웃 두 행 305·306 맞바뀜", "ab", [("move", 305, 1)])
sc("D4b", "D 재전송·순서", "기록 경계 두 행 329·330 맞바뀜", "ab", [("move", 329, 1)])
sc("D5a", "D 재전송·순서", "행 305가 2행 늦게 도착", "ab", [("move", 305, 2)])
sc("D5b", "D 재전송·순서", "행 305가 4행 늦게 도착", "ab", [("move", 305, 4)])
# E. 시계 재설정(305행부터 끝까지 이동)
for d in (-0.2, -0.5, -1, -60, -3600, 5, 61, 3600):
    tt = TA.copy(); tt.iloc[305:] += pd.Timedelta(seconds=d)
    f, e = times_frame("ab", tt)
    sc(f"E1_{d}", "E 시계 재설정", f"305행부터 시계 {d:+g}초(영구)", "ab", frame=f, err=e)
for d in (-1, -2.5, -5):
    tt = TA.copy(); tt.iloc[331:] += pd.Timedelta(seconds=d)
    f, e = times_frame("ab", tt)
    sc(f"E3_{d}", "E 시계 재설정", f"기록 12 첫 행 뒤(331행부터) 시계 {d:+g}초", "ab", frame=f, err=e)
# F. 긴 수집 중단 뒤 과거 행(기록 12부터 P초 밀고, 새 기록 첫 행 330 뒤에 과거 행)
for P in (60, 600, 3600):
    tt = TA.copy(); tt.iloc[330:] += pd.Timedelta(seconds=P)
    base_t = tt
    for label, offs in (("공백 안 +10초 한 행", [10.0]), ("앞 기록 끝 +0.1·0.2·0.3초 세 행(늦게 온 꼬리)", [0.1, 0.2, 0.3]),
                        ("앞 기록 끝 +30초부터 10행(밀린 자료)", [30 + 0.1 * k for k in range(10)])):
        rows = list(range(331)) + [None] * len(offs) + list(range(331, 600))
        src = [r if r is not None else 300 for r in rows]
        f = AB.iloc[src].reset_index(drop=True)
        stamps = [base_t.iloc[r] if r is not None else None for r in rows]
        k = 0
        for j, r in enumerate(rows):
            if r is None:
                stamps[j] = TA.iloc[329] + pd.Timedelta(seconds=offs[k]); k += 1
        f = with_times(f, stamps)
        e = np.array([r is None for r in rows])
        sc(f"F_{P}_{len(offs)}", "F 긴 중단 뒤 과거 행", f"{P}초 중단, 새 기록 첫 행 뒤 {label}", "ab", frame=f, err=e)
    f, e = times_frame("ab", base_t)
    sc(f"F_{P}_0", "F 긴 중단 뒤 과거 행", f"{P}초 중단만(과거 행 없음, 대조)", "ab", frame=f, err=e)
# G. 동률·결측 조합
tt = TA.copy(); tt.iloc[305] = tt.iloc[304]
f, e = times_frame("ab", tt, [305]); sc("G1", "G 동률·결측 조합", "행 305 시각 = 304(동률)", "ab", frame=f, err=e)
sc("G2", "G 동률·결측 조합", "305 뒤 +5초 끼움 + 바로 뒤 306 시각 결측", "ab", [("insert_after", 305, 5), ("nat", 306, 0)])
_g3 = list(range(306)) + [305, 305] + list(range(306, 600))
_g3t = list(TA.iloc[:306]) + [TA.iloc[305] + pd.Timedelta(seconds=5), TA.iloc[305] - pd.Timedelta(seconds=3600)] + list(TA.iloc[306:])
f = with_times(AB.iloc[_g3].reset_index(drop=True), _g3t); e = np.zeros(len(f), bool); e[[306, 307]] = True
sc("G3", "G 동률·결측 조합", "305 뒤 +5초 끼움 + 그 뒤 −1시간 한 행 끼움", "ab", frame=f, err=e)
sc("G4", "G 동률·결측 조합", "행 305 시각 결측", "ab", [("nat", 305, 0)])
sc("G5", "G 동률·결측 조합", "+5초 튄 행 305가 센서 결측", "ab", [("replace", 305, 5), ("nan", 305, 0)])
sc("G6", "G 동률·결측 조합", "+5초 튄 행 305 다음 행(확인 행) 306이 센서 결측", "ab", [("replace", 305, 5), ("nan", 306, 0)])
sc("G7", "G 동률·결측 조합", "기록 끝 329 +5초 + 다음 기록 첫 행 330 시각 결측", "ab", [("replace", 329, 5), ("nat", 330, 0)])
sc("G8", "G 동률·결측 조합", "기록 끝 329 +5초 + 다음 기록 331 센서 결측(보류 행)", "ab", [("replace", 329, 5), ("nan", 331, 0)])
sc("G9", "G 동률·결측 조합", "기록 끝 329 +5초 + 새 기준 행 332가 센서 결측", "ab", [("replace", 329, 5), ("nan", 332, 0)])
sc("G10", "G 동률·결측 조합", "기록 끝 329 +5초가 센서 결측", "ab", [("replace", 329, 5), ("nan", 329, 0)])
# H. 이상 시작·끝(맥락 자료: 앞 정상 6기록 → 이상 → 뒤 정상 6기록)
sc("H0", "H 이상 시작·끝", "맥락 자료 원본(대조)", "cf", [])
for d in (0.5, 5, 3600):
    sc(f"H1_{d}", "H 이상 시작·끝", f"이상 첫 행 +{d}초", "cf", [("replace", N0, d)])
sc("H2", "H 이상 시작·끝", "정상 마지막 행이 이상 첫 행 뒤에 도착(경계 맞바뀜)", "cf", [("move", N0 - 1, 1)])
sc("H2b", "H 이상 시작·끝", "정상 마지막 두 행이 이상 첫 행 뒤에 역순 도착", "cf", frame=None, err=None)
for d in (0.5, 2, 5):
    sc(f"H3_{d}", "H 이상 시작·끝", f"이상 마지막 행 +{d}초(뒤 공백 3초)", "cf", [("replace", N1 - 1, d)])
    sc(f"H4_{d}", "H 이상 시작·끝", f"정상 복귀 첫 행 +{d}초", "cf", [("replace", N1, d)])
    sc(f"H5_{d}", "H 이상 시작·끝", f"이상 직전 정상 마지막 행 +{d}초", "cf", [("replace", N0 - 1, d)])
# H2b: 정상 마지막 두 행(N0-2, N0-1)이 이상 첫 행 뒤에 N0-1, N0-2 순서로 도착
order = list(range(N0 - 2)) + [N0, N0 - 1, N0 - 2] + list(range(N0 + 1, len(CF)))
f, e = reorder("cf", order, [N0 - 1, N0])
SC[[s["sid"] for s in SC].index("H2b")].update(frame=f, err=e)


def materialize(s):
    fr, tt = (AB, TA) if s["base"] == "ab" else (CF, TC)
    if s["frame"] is not None:
        return s["frame"], s["err"]
    f, err, _ = build(fr, tt, s["faults"])
    return f, err


rng = np.random.default_rng(7)
out = open(args.out, "w") if args.out else None
print(f"# 판: {ENV.parent.name} · 원자료 이상 파일 {BASE['ab']} · 맥락 {BASE['cf']}")
for s in SC:
    if args.only and not s["sid"].startswith(tuple(args.only.split(","))):
        continue
    f, err = materialize(s)
    p = mdl.predict(f)
    r = summarize(p, err)
    r.update(sid=s["sid"], group=s["group"], desc=s["desc"], base=s["base"])
    r["body_alarm_loss"] = BASE[s["base"]]["body_alarms"] - r["body_alarms"]
    r["split"] = int(r["body_incidents"] > BASE[s["base"]]["body_incidents"])
    r["quality"] = quality(p) if s["base"] == "cf" else None
    if args.stream:
        sizes = rng.integers(1, 40, 200).tolist()
        r["stream"] = {str(c): same(stream_predict(mdl, f, c), p) for c in (1, 2, 3, 7, 128)}
        r["stream"]["rand"] = same(stream_predict(mdl, f, sizes), p)
        ev = p.time_order_event.to_numpy()
        cut = set()
        for i in np.flatnonzero(ev):
            cut.update(range(max(1, i - 3), min(len(f), i + 4)))
        cut.update(rng.choice(np.arange(1, len(f)), 5, replace=False).tolist())
        r["prefix_ok"] = all(same(mdl.predict(f.iloc[:k]), p.iloc[:k]) for k in sorted(cut))
        r["prefix_n"] = len(cut)
    line = {k: (v if not isinstance(v, (np.integer,)) else int(v)) for k, v in r.items()}
    print(json.dumps(line, ensure_ascii=False, default=str))
    if out:
        out.write(json.dumps(line, ensure_ascii=False, default=str) + "\n"); out.flush()
