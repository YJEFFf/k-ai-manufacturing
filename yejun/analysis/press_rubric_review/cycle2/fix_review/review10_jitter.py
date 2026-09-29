"""검토 10: README가 '사양 안'이라 부른 흔들림(행마다 ±20 ms 이하)이 모든 행에 있을 때 튄 행 한 개가 사건을 나누는가.
약한 이상 0.1σ(검토 7 주입)의 모든 행 시각에 U(−s, +s)(시드 5개)를 더한 입력을 기준으로, 5행마다 한 행을 +5초로 바꾼(표본 대체) 입력을 만든다.
사건 수는 튄 행·보류 행의 경보를 뺀 경보 행이 속한 사건 수다(검토 7 incident_view). 판마다 같은 입력.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review10_jitter.py [--workers 2] [--level 0.1]
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

_W = {}


def jittered(L, F, T, s, seed):
    e = np.random.default_rng(1000 + seed).uniform(-s, s, len(F))
    return [t + pd.Timedelta(microseconds=int(round(x * 1e6))) for t, x in zip(T, e)]


def init(level):
    import review7_weak as W
    _W["W"] = W
    _W["L"], _W["M"], _W["F"], _W["T"] = W.setup(level)


def job(args):
    s, seed, pos = args
    W, L, M, F, T = _W["W"], _W["L"], _W["M"], _W["F"], _W["T"]
    TJ = jittered(L, F, T, s, seed)
    key = (s, seed)
    if key not in _W:
        b = M.predict(L.with_times(F, TJ))
        _W[key] = b
    b = _W[key]
    f, err, _ = L.build(F, pd.Series(TJ), [("replace", pos, 5.0)])
    p = M.predict(f)
    err = err | p.status.eq("bad_time_order").to_numpy()
    n, st, es = W.incident_view(p, err)
    be = np.zeros(len(b), bool); be[pos] = True
    bn, bs, bes = W.incident_view(b, be)
    ev = p.time_order_event.to_numpy()
    return dict(s=s, seed=seed, pos=pos, incidents=n, base_incidents=bn, starts=st, base_starts=bs, esc=es, base_esc=bes,
                held=int((ev == 1).sum()), skipped=int((ev == 2).sum()), spike_reanchor=int((ev == 4).sum()), reanchor=int((ev == 3).sum()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--level", type=float, default=0.1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import review7_weak as W
    L, M, F, T = W.setup(a.level)
    ver = ("a489001" if hasattr(L.M.CollectionUnits(), "extra") else "other") if hasattr(L.M, "CollectionUnits") else "c7d8bba"
    print(f"# 판 {ver} · 사본 {L.ENV} · 세기 {a.level}σ · {len(F)}행", flush=True)
    for s in (0.0, 0.01, 0.02):
        for seed in range(5 if s else 1):
            b = M.predict(L.with_times(F, jittered(L, F, T, s, seed)))
            print(f"  흔들림 ±{s * 1000:.0f} ms 시드 {seed}: 튐 없는 기준 (사건, 시작, 격상) = {L.summ(b) if hasattr(L, 'summ') else (int(b.incident_id.max()), int(b.incident_notification.sum()), int(b.incident_escalation.sum()))}, 경보 {int(b.alarm.sum())}행, 기록 {b.record_id.nunique()}", flush=True)
    jobs = [(s, seed, pos) for s in (0.0, 0.01, 0.02) for seed in range(5 if s else 1) for pos in range(2, len(F) - 2, 5)]
    with mp.get_context("fork").Pool(a.workers, initializer=init, initargs=(a.level,)) as pool:
        rows = list(pool.imap(job, jobs, chunksize=8))
    d = pd.DataFrame(rows)
    d.to_csv(a.out, index=False)
    d["delta"] = d.incidents - d.base_incidents
    for (s, seed), g in d.groupby(["s", "seed"]):
        print(f"  ±{s * 1000:.0f} ms 시드 {seed}: 튄 위치 {len(g)} · 분할 {int((g.delta > 0).sum())} · 합침 {int((g.delta < 0).sum())} · "
              f"시작 알림 늘어난 위치 {int((g.starts > g.base_starts).sum())} · 보류 생긴 위치 {int((g.held > 0).sum())} · "
              f"튐 확인(2) {int((g.skipped > 0).sum())} · 튐 확인(4) {int((g.spike_reanchor > 0).sum())} · 새 기준(3) {int((g.reanchor > 0).sum())}", flush=True)
    for s, g in d.groupby("s"):
        print(f"  ±{s * 1000:.0f} ms 합계: 튄 위치 {len(g)} · 분할 {int((g.delta > 0).sum())} · 합침 {int((g.delta < 0).sum())} · 보류 생긴 위치 {int((g.held > 0).sum())}"
              f" · 보류 생긴 위치 중 분할 {int(((g.held > 0) & (g.delta > 0)).sum())}", flush=True)
