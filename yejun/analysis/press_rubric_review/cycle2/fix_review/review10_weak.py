"""검토 10: 약한 이상(검토 7·8·9와 같은 주입: 정상 평가 B 기록 20~49 전류에 N(0, (Lσ)²), 시드 20260929)의 모든 위치에
검토 7이 약한 이상에서 재지 않은 '한 행' 오류를 넣고, 사건 수가 오류 없는 입력과 달라지는 위치 수를 판마다 센다.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review10_weak.py --level 0.1 --workers 2 --out 결과.csv

종류
 move1   한 행이 한 칸 늦게 도착(이웃 두 행 순서 뒤바뀜)
 move2   한 행이 두 칸 늦게 도착(늦은 행은 보류)
 dup     같은 행을 바로 뒤에 같은 시각으로 다시 보냄(6차가 고쳤다는 중복)
 blank   행 앞에 시각이 빈 행 한 개를 끼움(표본 자리가 아닌 빈 줄)
 nat     행의 시각 결측(표본 자리, R7-01 대조)
 spike   +5초 튐(표본 대체, 대조)
 spikej  +5초 튐 + 앞 행 −15 ms·뒤 행 +15 ms(행마다 사양 ±20 ms 안의 흔들림)
 jit     앞 행 −15 ms·뒤 행 +15 ms만(튐 없음, spikej 대조)
사건 수는 오류 행(끼운 행·옮긴 행·튄 행·보류 행)의 경보를 뺀 경보 행이 속한 사건 수다(검토 7 incident_view와 같은 정의). 알림은 모두 센다.
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

KINDS = ("move1", "move2", "dup", "blank", "nat", "spike", "spikej", "jit")
_W = {}


def make(L, F, T, kind, pos):
    if kind == "move1":
        f, err, _ = L.build(F, T, [("move", pos, 1)])
    elif kind == "move2":
        f, err, _ = L.build(F, T, [("move", pos, 2)])
    elif kind == "dup":
        f, err, _ = L.build(F, T, [("dup", pos, 0)])
    elif kind == "blank":
        f, err, _ = L.build(F, T, [("insert", pos, 0)])
        f.loc[pos, L.D.TIME] = ""
    elif kind == "nat":
        f, err, _ = L.build(F, T, [("nat", pos, 0)])
    elif kind == "spike":
        f, err, _ = L.build(F, T, [("replace", pos, 5.0)])
    elif kind == "spikej":
        f, err, _ = L.build(F, T, [("replace", pos, 5.0), ("replace", pos - 1, -0.015), ("replace", pos + 1, 0.015)])
        err = np.zeros(len(f), bool); err[pos] = True
    elif kind == "jit":
        f, err, _ = L.build(F, T, [("replace", pos - 1, -0.015), ("replace", pos + 1, 0.015)])
        err = np.zeros(len(f), bool)
    return f, err


def init(level):
    import review7_weak as W
    _W["W"] = W
    _W["L"], _W["M"], _W["F"], _W["T"] = W.setup(level)
    _W["B"] = _W["M"].predict(_W["F"])


def job(args):
    pos, kind = args
    W, L, M, F, T, b = _W["W"], _W["L"], _W["M"], _W["F"], _W["T"], _W["B"]
    f, err = make(L, F, T, kind, pos)
    p = M.predict(f)
    err = err | p.status.eq("bad_time_order").to_numpy()
    n, s, e = W.incident_view(p, err)
    base_err = np.zeros(len(b), bool); base_err[pos] = True
    bn, bs, be = W.incident_view(b, base_err)
    ev = p.time_order_event.to_numpy()
    return dict(pos=pos, kind=kind, incidents=n, starts=s, escalations=e, base_incidents=bn, base_starts=bs, base_escalations=be,
                held=int((ev == 1).sum()), spike=int(np.isin(ev, (2, 4)).sum()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--level", type=float, default=0.1)
    args = ap.parse_args()
    import review7_weak as W
    L, M, F, T = W.setup(args.level)
    b = M.predict(F)
    ver = ("a489001" if hasattr(L.M.CollectionUnits(), "extra") else "other") if hasattr(L.M, "CollectionUnits") else "c7d8bba"
    print(f"# 판 {ver} · 사본 {L.ENV} · 세기 {args.level}σ · {len(F)}행 · 경보 {int(b.alarm.sum())}행 · 사건 {int(b.incident_id.max())} · "
          f"시작 {int(b.incident_notification.sum())} · 격상 {int(b.incident_escalation.sum())}", flush=True)
    jobs = [(pos, k) for pos in range(1, len(F) - 2) for k in KINDS]
    with mp.get_context("fork").Pool(args.workers, initializer=init, initargs=(args.level,)) as pool:
        rows = list(pool.imap(job, jobs, chunksize=16))
    d = pd.DataFrame(rows)
    d.to_csv(args.out, index=False)
    d["delta"] = d.incidents - d.base_incidents
    for k in KINDS:
        g = d[d.kind == k]
        print(f"  {k:7s}: 위치 {len(g)} · 분할(사건 늘어남) {int((g.delta > 0).sum())} · 합침 {int((g.delta < 0).sum())} · "
              f"시작 알림 +{int((g.starts > g.base_starts).sum())}곳/−{int((g.starts < g.base_starts).sum())}곳 · "
              f"격상 +{int((g.escalations > g.base_escalations).sum())}곳/−{int((g.escalations < g.base_escalations).sum())}곳 · "
              f"보류 있는 위치 {int((g.held > 0).sum())} · 튐 확인 위치 {int((g.spike > 0).sum())}", flush=True)
