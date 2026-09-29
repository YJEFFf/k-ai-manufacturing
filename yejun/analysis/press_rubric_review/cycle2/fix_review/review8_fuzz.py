"""검토 8: 4차 사건 단위 규칙의 불변식 무작위 시험. 기록 경계·짧은 공백·경보가 드문 구성에 오류를 여러 개 겹쳐 넣는다.

(a) 일괄 = 스트림(청크 1·2·5·13·64·무작위 크기 목록), (b) 접두부 인과(오류 행 주변과 무작위 위치에서 predict(앞 k행) = 전체 예측의 앞 k행),
(c) 사건마다 시작·격상 알림 한 번 이하, (d) 시작 알림 없는 사건(경보 행이 있는데 시작이 0)이 없는가.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_fuzz.py --trials 120 --workers 2
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

_W = {}
GAPS = (0.2, 0.3, 0.45, 0.55, 0.8, 1.5, 3.0, 70.0)
KINDS = ("attach_late", "attach_early", "jitter", "drop", "dup", "nat", "nan", "spike", "spike_small", "insert_spike", "move", "clock_back")


def init():
    import review8_lib as L
    _W["L"] = L
    _W["parts"] = L.parts()
    _W["m"] = L.model()


def compose(rng):
    L = _W["L"]
    (r11, r12, r13), (q0, q1), mag = _W["parts"]
    pool = []
    for _ in range(rng.integers(5, 9)):
        c = rng.integers(0, 6)
        if c == 0:
            pool.append([r11, r12, r13][rng.integers(0, 3)])
        elif c == 1:
            q = [q0, q1][rng.integers(0, 2)]; k = int(rng.integers(1, len(q) + 1)); pool.append(q.iloc[:k])
        elif c == 2:
            pool.append(mag.iloc[:int(rng.integers(1, 3))])
        elif c == 3:
            pool.append(pd.concat([L.D.inputs_only(mag.iloc[:1]), L.D.inputs_only(q0.iloc[:int(rng.integers(8, 30))])], ignore_index=True))
        elif c == 4:
            pool.append(pd.concat([L.D.inputs_only(q1.iloc[:int(rng.integers(8, 40))]), L.D.inputs_only(mag.iloc[:1])], ignore_index=True))
        else:
            q = q1.iloc[:int(rng.integers(8, 20))]
            pool.append(pd.concat([L.D.inputs_only(q), L.D.inputs_only(mag.iloc[:1]), L.D.inputs_only(q0.iloc[:int(rng.integers(3, 15))])], ignore_index=True))
    gaps = [float(rng.choice(GAPS)) for _ in pool]
    return L.chain(pool, gap=gaps), gaps


def fault(frame, starts, gaps, rng):
    L = _W["L"]
    kind = str(rng.choice(KINDS))
    n = len(frame)
    t = pd.to_datetime(frame[L.D.TIME], errors="coerce")
    b = int(rng.integers(1, len(starts))) if len(starts) > 1 else 0
    if kind == "attach_late" and b:          # 앞 부분 끝 행을 다음 부분 앞 0.05~0.45초로
        row = starts[b] - 1; d = gaps[b - 1] - float(rng.uniform(0.05, 0.45)); f = L.shift(frame, row, max(d, 0.0))
    elif kind == "attach_early" and b and starts[b] < n:
        row = starts[b]; d = gaps[b - 1] - float(rng.uniform(0.05, 0.45)); f = L.shift(frame, row, -max(d, 0.0))
    elif kind == "clock_back" and b and starts[b] < n:
        row = starts[b]; d = gaps[b - 1] - float(rng.uniform(0.05, 0.45)); f = frame.copy()
        f.loc[row:, L.D.TIME] = (t[row:] - pd.Timedelta(seconds=max(d, 0.0))).dt.strftime(L.FMT)
    else:
        row = int(rng.integers(1, n - 1))
        if kind == "jitter":
            f = L.shift(frame, row, float(rng.choice([-0.05, -0.03, 0.021, 0.03, 0.05, 0.2])))
        elif kind == "drop":
            f = L.drop(frame, row)
        elif kind == "dup":
            f = L.dup(frame, row)
        elif kind == "nat":
            f = L.nat(frame, row)
        elif kind == "nan":
            f = L.sensor_nan(frame, row)
        elif kind == "spike":
            f = L.shift(frame, row, float(rng.choice([5.0, 3600.0])))
        elif kind == "spike_small":
            f = L.shift(frame, row, float(rng.choice([0.3, 0.4, 0.6])))
        elif kind == "insert_spike":
            extra = frame.iloc[[row]].copy()
            extra[L.D.TIME] = (t[row] + pd.Timedelta(seconds=5)).strftime(L.FMT)
            f = pd.concat([frame.iloc[:row + 1], extra, frame.iloc[row + 1:]], ignore_index=True)
        else:   # move: 1~3행 늦게 도착
            k = int(rng.integers(1, 4)); rows = list(range(n)); rows.pop(row); rows.insert(min(row + k, n - 1), row)
            f = frame.iloc[rows].reset_index(drop=True)
    return f.reset_index(drop=True), kind, row


def job(seed):
    L, mdl = _W["L"], _W["m"]
    rng = np.random.default_rng(seed)
    (frame, starts), gaps = compose(rng)
    kinds, rows = [], []
    for _ in range(int(rng.integers(2, 7))):
        frame, k, r = fault(frame, starts, gaps, rng)
        kinds.append(k); rows.append(r)
    p = mdl.predict(frame)
    bad_stream = []
    rand = [int(x) for x in rng.integers(1, 40, size=6)]
    for c in (1, 2, 5, 13, 64, rand):
        if not L.same(L.stream(frame, c), p):
            bad_stream.append(str(c))
    ks = sorted({min(len(frame), max(1, r + o)) for r in rows for o in (-1, 0, 1, 2)} | {int(x) for x in rng.integers(1, len(frame), size=6)})
    bad_prefix = [k for k in ks if not L.same(mdl.predict(frame.iloc[:k]), p.iloc[:k])]
    per = p[p.incident_id.gt(0)].groupby("incident_id")[["incident_notification", "incident_escalation"]].sum()
    return dict(seed=seed, rows=len(frame), kinds="+".join(kinds), alarms=int(p.alarm.sum()), incidents=int(p.incident_id.max()),
                codes=dict(zip(*np.unique(p.time_order_event, return_counts=True))), bad_stream=bad_stream, bad_prefix=bad_prefix,
                prefixes=len(ks), dup=int((per > 1).any(axis=1).sum()), nostart=int((per.incident_notification == 0).sum()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=120)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    with mp.get_context("fork").Pool(a.workers, initializer=init) as pool:
        res = list(pool.imap(job, range(8000, 8000 + a.trials)))
    import review8_lib as L
    print(f"# 판 {L.VERSION} · 시행 {len(res)} · 행 합 {sum(r['rows'] for r in res)} · 오류 {sum(len(r['kinds'].split('+')) for r in res)}개")
    kinds = pd.Series([k for r in res for k in r["kinds"].split("+")]).value_counts().to_dict()
    print(f"오류 종류 분포 {kinds}")
    codes = {}
    for r in res:
        for k, v in r["codes"].items():
            codes[int(k)] = codes.get(int(k), 0) + int(v)
    print(f"부호 합 {codes}")
    print(f"(a) 일괄≠스트림 시행 {sum(bool(r['bad_stream']) for r in res)} {[(r['seed'], r['bad_stream']) for r in res if r['bad_stream']]}")
    print(f"(b) 접두부 불일치 시행 {sum(bool(r['bad_prefix']) for r in res)} · 대조한 접두부 {sum(r['prefixes'] for r in res)}곳 "
          f"{[(r['seed'], r['bad_prefix'][:5]) for r in res if r['bad_prefix']]}")
    print(f"(c) 시작·격상 중복 사건이 있는 시행 {sum(r['dup'] > 0 for r in res)} · (d) 시작 없는 사건이 있는 시행 {sum(r['nostart'] > 0 for r in res)}")
    print("R8DONE")
