"""검토 9: 5차 사건 단위 규칙의 불변식 무작위 시험. 짧은 공백·짧은 기록·경보가 드문 구성에 오류를 여러 개 겹쳐 넣는다.
검토 8의 오류 12종에 '도착 행 수를 부풀리는' 오류(빈 시각 행 묶음, 지난 행 역순 재전송)와 연속 흔들림 구간을 더했다.

(a) 일괄 = 스트림(청크 1·3·7·64·무작위 크기 목록), (b) 접두부 인과(오류 행 주변과 무작위 위치에서 predict(앞 k행) = 전체 예측의 앞 k행),
(c) 사건마다 시작·격상 알림 한 번 이하, (d) 경보 행이 있는데 시작 알림이 없는 사건이 없는가.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review9_fuzz.py --trials 80 --workers 2
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

_W = {}
GAPS = (0.12, 0.2, 0.3, 0.45, 0.55, 1.5, 3.0, 70.0)
KINDS = ("attach_late", "attach_early", "jitter", "drop", "dup", "nat", "nan", "spike", "insert_spike", "clock_back",
         "blank_rows", "reverse_resend", "jitter_burst", "resend_fwd")


def init():
    import review9_lib as L
    _W["L"] = L
    _W["parts"] = L.parts()
    _W["m"] = L.model()


def compose(rng):
    L = _W["L"]
    (r11, r12, r13), (q0, q1), mag = _W["parts"]
    pool = []
    for _ in range(rng.integers(5, 9)):
        c = rng.integers(0, 5)
        if c == 0:
            pool.append([r11, r12, r13][rng.integers(0, 3)])
        elif c == 1:
            q = [q0, q1][rng.integers(0, 2)]; pool.append(q.iloc[:int(rng.integers(1, len(q) + 1))])
        elif c == 2:
            pool.append(mag.iloc[:int(rng.integers(1, 3))])
        elif c == 3:
            pool.append(pd.concat([L.D.inputs_only(mag.iloc[:1]), L.D.inputs_only(q0.iloc[:int(rng.integers(8, 30))])], ignore_index=True))
        else:
            pool.append(pd.concat([L.D.inputs_only(q1.iloc[:int(rng.integers(5, 20))]), L.D.inputs_only(r12)], ignore_index=True))
    gaps = [float(rng.choice(GAPS)) for _ in pool]
    return L.chain(pool, gap=gaps, start=f"2022-07-{int(rng.integers(20, 28))}")


def fault(frame, rng):
    L = _W["L"]
    kind = str(rng.choice(KINDS))
    n = len(frame)
    i = int(rng.integers(1, n - 1))
    t = L.times(frame)
    if kind == "attach_late":
        return L.shift(frame, list(range(i, min(n, i + int(rng.integers(1, 4))))), float(rng.uniform(0.15, 3.0))), kind, i
    if kind == "attach_early":
        return L.shift(frame, list(range(i, min(n, i + int(rng.integers(1, 4))))), -float(rng.uniform(0.15, 3.0))), kind, i
    if kind == "jitter":
        return L.shift(frame, i, float(rng.uniform(-0.06, 0.06))), kind, i
    if kind == "drop":
        return L.drop(frame, i), kind, i
    if kind == "dup":
        return L.dup(frame, i), kind, i
    if kind == "nat":
        return L.nat(frame, list(range(i, min(n, i + int(rng.integers(1, 4)))))), kind, i
    if kind == "nan":
        return L.sensor_nan(frame, i), kind, i
    if kind == "spike":
        return L.shift(frame, i, float(rng.choice([0.5, 5.0, 3600.0]))), kind, i
    if kind == "insert_spike":
        r = frame.iloc[[i]].copy(); r[L.D.TIME] = (t[i] + pd.Timedelta(seconds=float(rng.choice([0.5, 5.0])))).strftime(L.FMT)
        return L.insert(frame, i + 1, r), kind, i + 1
    if kind == "clock_back":
        f = frame.copy(); d = float(rng.choice([0.2, 0.3, 0.4, 1.0]))
        f.loc[i:, L.D.TIME] = (t[i:] - pd.Timedelta(seconds=d)).dt.strftime(L.FMT)
        return f, kind, i
    if kind == "blank_rows":
        return L.insert(frame, i, L.blank_rows(frame, int(rng.integers(2, 25)), i)), kind, i
    if kind == "reverse_resend":
        k = int(rng.integers(2, 12)); lo = max(0, i - k - 3)
        return L.insert(frame, i, frame.iloc[lo:lo + k].iloc[::-1].reset_index(drop=True)), kind, i
    if kind == "resend_fwd":
        k = int(rng.integers(2, 6)); lo = max(0, i - k)
        return L.insert(frame, i, frame.iloc[lo:i].reset_index(drop=True)), kind, i
    # jitter_burst: 연속 10~40행에 독립 흔들림 ±s
    f = frame.copy(); m = int(rng.integers(10, 41)); s = float(rng.choice([0.02, 0.03, 0.045]))
    rows = list(range(i, min(n, i + m)))
    e = rng.uniform(-s, s, len(rows))
    f.loc[rows, L.D.TIME] = (t[rows] + pd.to_timedelta(np.round(e * 1e6), unit="us")).dt.strftime(L.FMT).to_numpy()
    return f, kind, i


def job(seed):
    L, mdl = _W["L"], _W["m"]
    rng = np.random.default_rng(seed)
    frame, _ = compose(rng)
    kinds, keys = [], []
    for _ in range(int(rng.integers(2, 6))):
        frame, kind, key = fault(frame, rng)
        kinds.append(kind); keys.append(key)
    frame = frame.reset_index(drop=True)
    p = mdl.predict(frame)
    chunks = [1, 3, 7, 64, [int(x) for x in rng.integers(1, 20, 6)]]
    stream_bad = [str(c) for c in chunks if not L.same(L.stream(frame, c), p)]
    pos = sorted(set([k for k in keys if 1 <= k < len(frame)] + [int(x) for x in rng.integers(1, len(frame), 4)]))
    prefix_bad = [k for k in pos if not L.same(mdl.predict(frame.iloc[:k]), p.iloc[:k])]
    ev = p.time_order_event.to_numpy()
    return dict(seed=seed, rows=len(frame), kinds="+".join(kinds), stream_bad=";".join(stream_bad), prefix_checked=len(pos),
                prefix_bad=len(prefix_bad), dup=L.dup_alerts(p), no_start=L.no_start(p), incidents=int(p.incident_id.max()),
                held=int((ev == 1).sum()), spike=int(np.isin(ev, (2, 4)).sum()), reanchor=int((ev == 3).sum()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=80)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seed0", type=int, default=9000)
    a = ap.parse_args()
    import review9_lib as L0
    print(f"# 판 {L0.VERSION} · 사본 {L0.ENV} · 시행 {a.trials}", flush=True)
    with mp.get_context("fork").Pool(a.workers, initializer=init) as pool:
        rows = list(pool.imap(job, range(a.seed0, a.seed0 + a.trials)))
    d = pd.DataFrame(rows)
    counts = pd.Series("+".join(d.kinds).split("+")).value_counts()
    print(f"오류 종류별 개수: {dict(counts)}")
    print(f"일괄 ≠ 스트림 시행: {int((d.stream_bad != '').sum())} / {len(d)}")
    print(f"접두부 불일치: {int(d.prefix_bad.sum())} / {int(d.prefix_checked.sum())}")
    print(f"사건마다 알림 두 번: {int(d.dup.sum())} · 시작 없는 사건: {int(d.no_start.sum())}")
    print(f"부호 합계: 보류 {int(d.held.sum())} · 튄 행 확인 {int(d.spike.sum())} · 새 기준 {int(d.reanchor.sum())}")
    bad = d[(d.stream_bad != "") | (d.prefix_bad > 0) | (d.dup > 0) | (d.no_start > 0)]
    print("위반 시행:" if len(bad) else "위반 시행 없음")
    if len(bad):
        print(bad.to_string(index=False))
