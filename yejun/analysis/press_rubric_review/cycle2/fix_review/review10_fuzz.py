"""검토 10: 6차 규칙의 불변식 무작위 시험. 검토 9 fuzz에 없던 오류(이웃 행 뒤바뀜, 2~3칸 늦은 행, 튄 행 + 사양 안 흔들림으로 생긴 보류,
기준보다 조금 이른(0.1초 안) 보류 행, 표본 자리가 아닌 빈 시각 행, 1 ms 안팎 중복)와 모든 행의 흔들림 U(±s)를 겹쳐 넣는다.

(a) 일괄 = 스트림(청크 1·2·3·7·64·무작위 크기 목록), (b) 접두부 인과(무작위 위치 8곳 + 오류 행 주변에서 predict(앞 k행) = 전체 예측의 앞 k행),
(c) 사건마다 시작·격상 알림 한 번 이하, (d) 경보 행이 있는데 시작 알림이 없는 사건이 없는가.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review10_fuzz.py --trials 60 --workers 2
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

_W = {}
KINDS = ("swap", "late2", "late3", "spike_jit", "near_held", "blank", "dup_ms", "nat", "spike", "insert_spike")
COLS = ["status", "record_id", "position", "alarm", "notification", "alert_level", "escalation", "incident_id", "incident_notification",
        "incident_escalation", "incident_update", "time_order_event", "reason"]


def init():
    import review9_lib as L
    _W["L"] = L
    _W["parts"] = L.parts()
    _W["m"] = L.model()


def compose(rng):
    L = _W["L"]
    (r11, r12, r13), (q0, q1), mag = _W["parts"]
    pool = [r11, r12, r13, q0, q1, q0.iloc[:10], q1.iloc[:14], q0.iloc[:30]]
    parts = [pool[int(i)] for i in rng.integers(0, len(pool), int(rng.integers(4, 8)))]
    gaps = [float(rng.choice((0.2, 0.3, 0.5, 1.5, 3.0, 70.0))) for _ in parts]
    frame, _ = L.chain(parts, gap=gaps, start="2022-07-23")
    s = float(rng.choice((0.0, 0.0, 0.01, 0.02)))
    if s:
        t = L.times(frame)
        e = rng.uniform(-s, s, len(frame))
        frame[L.D.TIME] = (t + pd.to_timedelta(np.round(e * 1e6), unit="us")).dt.strftime(L.FMT)
    kinds = []
    for _ in range(int(rng.integers(1, 4))):
        n = len(frame)
        k = str(rng.choice(KINDS)); r = int(rng.integers(2, n - 4)); kinds.append(k)
        t = L.times(frame)
        if k in ("swap", "late2", "late3"):
            m = {"swap": 1, "late2": 2, "late3": 3}[k]
            order = list(range(n)); order.pop(r); order.insert(r + m, r)
            frame = frame.iloc[order].reset_index(drop=True)
        elif k == "spike_jit":
            frame = L.shift(L.shift(L.shift(frame, r, 5.0), r - 1, -0.015), r + 1, 0.015)
        elif k == "spike":
            frame = L.shift(frame, r, float(rng.choice((0.5, 5.0, 3600.0))))
        elif k == "insert_spike":
            row = frame.iloc[[r]].copy(); row[L.D.TIME] = (t[r] + pd.Timedelta(seconds=5)).strftime(L.FMT) if pd.notna(t[r]) else ""
            frame = L.insert(frame, r + 1, row)
        elif k == "near_held":
            cnt = int(rng.integers(1, 6))
            if pd.notna(t[r]):
                rows = pd.concat([frame.iloc[[r]]] * cnt, ignore_index=True); rows[L.D.TIME] = (t[r] - pd.Timedelta(seconds=0.05)).strftime(L.FMT)
                frame = L.insert(frame, r + 1, rows)
        elif k == "blank":
            frame = L.insert(frame, r, L.blank_rows(frame, int(rng.integers(1, 4)), r))
        elif k == "dup_ms":
            if pd.notna(t[r]):
                row = frame.iloc[[r]].copy(); row[L.D.TIME] = (t[r] + pd.Timedelta(seconds=float(rng.choice((0.0, 0.0009, 0.0011))))).strftime(L.FMT)
                frame = L.insert(frame, r + 1, row)
        elif k == "nat":
            frame = L.nat(frame, r)
    return frame.reset_index(drop=True), kinds, s


def job(seed):
    L, m = _W["L"], _W["m"]
    rng = np.random.default_rng(seed)
    frame, kinds, s = compose(rng)
    p = m.predict(frame)
    out = dict(seed=seed, kinds="+".join(kinds), jitter=s, rows=len(frame), incidents=int(p.incident_id.max()), held=int((p.time_order_event == 1).sum()))
    chunks = (1, 2, 3, 7, 64, list(rng.integers(1, 12, 40)))
    out["stream_bad"] = int(not all(L.same(L.stream(frame, c)[COLS], p[COLS]) for c in chunks))
    cut = sorted(set(int(x) for x in rng.integers(1, len(frame), 8)))
    bad = 0
    for k in cut:
        q = m.predict(frame.iloc[:k])
        bad += int(not L.same(q[COLS], p.iloc[:k][COLS]))
    out["prefix_bad"], out["prefix_n"] = bad, len(cut)
    out["dup_alerts"], out["no_start"] = L.dup_alerts(p), L.no_start(p)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=60)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    import review9_lib as L
    ver = ("a489001" if hasattr(L.M.CollectionUnits(), "extra") else "other") if hasattr(L.M, "CollectionUnits") else "c7d8bba"
    print(f"# 판 {ver} · 사본 {L.ENV} · 시행 {a.trials}", flush=True)
    with mp.get_context("fork").Pool(a.workers, initializer=init) as pool:
        rows = list(pool.imap(job, range(10_000, 10_000 + a.trials)))
    d = pd.DataFrame(rows)
    kinds = pd.Series("+".join(d.kinds).split("+")).value_counts().to_dict()
    print(f"오류 종류별 개수: {kinds} · 흔들림 ±10 ms {int((d.jitter == 0.01).sum())}회 · ±20 ms {int((d.jitter == 0.02).sum())}회")
    print(f"일괄 ≠ 스트림 시행: {int(d.stream_bad.sum())} / {len(d)}")
    print(f"접두부 불일치: {int(d.prefix_bad.sum())} / {int(d.prefix_n.sum())}")
    print(f"사건마다 알림 두 번: {int(d.dup_alerts.sum())} · 시작 없는 사건: {int(d.no_start.sum())} · 보류 행 합 {int(d.held.sum())}")
    v = d[(d.stream_bad > 0) | (d.prefix_bad > 0) | (d.dup_alerts > 0) | (d.no_start > 0)]
    print("위반 시행: " + (v.to_string() if len(v) else "없음"))
