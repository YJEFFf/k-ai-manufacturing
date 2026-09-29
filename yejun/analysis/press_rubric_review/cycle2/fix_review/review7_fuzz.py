"""검토 7: 무작위 시각 오류의 불변식. 시행마다 여러 오류(표본 대체·끼어듦 튐, 한 행 과거로, 늦은 도착, 재전송(한 행·여러 행),
시계 재설정(앞·뒤), 기록 첫 행 뒤 늦은 꼬리·밀린 자료, 시각 결측, 센서 결측)를 섞고 다음을 본다.
  (a) 일괄 predict = 스트림(청크 1·2·3·7·128·무작위 크기)   (b) 접두부 예측 = 전체 예측의 앞부분(인과)
  (c) 사건마다 시작 ≤ 1·격상 ≤ 1

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_fuzz.py --trials 96 --workers 4 --out 결과.jsonl
"""
import argparse
import json
import multiprocessing as mp

import numpy as np

_W = {}
KINDS = ["replace", "replace", "replace_edge", "insert_after", "back", "move", "dup", "rexmit", "step", "tail", "backlog", "nat", "nan"]


def init():
    import review7_lib as L
    import review7_scenarios_ctx as C
    _W["L"], _W["C"] = L, C


def make_faults(rng, n_rows, edges, k):
    faults = []
    for _ in range(k):
        kind = rng.choice(KINDS)
        pos = int(rng.integers(1, n_rows - 6))
        if kind == "replace_edge":
            pos = int(rng.choice(edges)); kind = "replace"
        if kind == "replace":
            faults.append(("replace", pos, float(rng.choice([0.13, 0.2, 0.3, 0.5, 2, 5, 30, 61, 3600]))))
        elif kind == "insert_after":
            faults.append(("insert_after", pos, float(rng.choice([0.13, 0.5, 5, 3600]))))
        elif kind == "back":
            faults.append(("replace", pos, -float(rng.choice([0.15, 0.3, 1, 3600]))))
        elif kind == "move":
            faults.append(("move", pos, int(rng.integers(1, 6))))
        elif kind == "dup":
            faults.append(("dup", pos, 0))
        elif kind == "rexmit":
            faults.append(("rexmit", pos, int(rng.choice([2, 3, 5, 10]))))
        elif kind == "step":
            faults.append(("step", pos, float(rng.choice([-3600, -5, -1, -0.5, 0.5, 5, 61]))))
        elif kind in ("tail", "backlog"):
            faults.append((kind, int(rng.choice(edges)), int(rng.choice([1, 2, 3, 5]))))
        elif kind == "nat":
            faults.append(("nat", pos, 0))
        else:
            faults.append(("nan", pos, 0))
    # 같은 행에 오류 두 개가 겹치면 하나만 남긴다(행 찾기 규칙을 단순하게)
    seen, out = set(), []
    for f in faults:
        if f[1] in seen and f[0] not in ("nan", "step"):
            continue
        seen.add(f[1]); out.append(f)
    return out


def job(trial):
    L, C = _W["L"], _W["C"]
    rng = np.random.default_rng(1000 + trial)
    base = "cf" if trial % 4 == 3 else "ab"
    fr, tt = (C.AB, C.TA) if base == "ab" else (C.CF, C.TC)
    seg = L.D.segments(fr)
    edges = np.flatnonzero(np.r_[False, seg[1:] != seg[:-1]])       # 기록 첫 행
    edges = np.unique(np.r_[edges, edges - 1]); edges = edges[(edges > 0) & (edges < len(fr) - 6)]
    faults = make_faults(rng, len(fr), edges, int(rng.integers(2, 9)))
    try:
        f, err, _ = L.build(fr, tt, faults)
    except StopIteration:
        return dict(trial=trial, skipped=True)
    p = C.MDL.predict(f)
    res = dict(trial=trial, base=base, rows=len(f), faults=[(a, int(b), float(c)) for a, b, c in faults])
    ev = p.time_order_event.to_numpy()
    res["codes"] = {int(k): int(v) for k, v in zip(*np.unique(ev, return_counts=True))}
    sizes = rng.integers(1, 30, 400).tolist()
    res["stream"] = {str(c): L.same(L.stream_predict(C.MDL, f, c), p) for c in (1, 2, 3, 7, 128)}
    res["stream"]["rand"] = L.same(L.stream_predict(C.MDL, f, sizes), p)
    cut = set()
    for i in np.flatnonzero(ev):
        cut.update(range(max(1, i - 2), min(len(f), i + 3)))
    cut.update(rng.choice(np.arange(1, len(f)), 8, replace=False).tolist())
    res["prefix_n"] = len(cut)
    res["prefix_bad"] = [int(k) for k in sorted(cut) if not L.same(C.MDL.predict(f.iloc[:k]), p.iloc[:k])]
    per = p[p.incident_id.gt(0)].groupby("incident_id")[["incident_notification", "incident_escalation"]].sum()
    res["dup_alerts"] = int((per > 1).any(axis=1).sum()) if len(per) else 0
    res["no_start"] = int((per.incident_notification == 0).sum()) if len(per) else 0
    s = L.summarize(p, err)
    res.update(held=s["held"], incidents=s["incidents"], body_incidents=s["body_incidents"], starts=s["starts"], escalations=s["escalations"])
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=96)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with mp.get_context("fork").Pool(args.workers, initializer=init) as pool, open(args.out, "w") as out:
        for r in pool.imap_unordered(job, range(args.trials)):
            out.write(json.dumps(r, ensure_ascii=False) + "\n"); out.flush()
    rows = [json.loads(x) for x in open(args.out)]
    rows = [r for r in rows if not r.get("skipped")]
    bad_stream = [r["trial"] for r in rows if not all(r["stream"].values())]
    bad_prefix = [r["trial"] for r in rows if r["prefix_bad"]]
    dup = [r["trial"] for r in rows if r["dup_alerts"]]
    nostart = [r["trial"] for r in rows if r["no_start"]]
    codes = {}
    for r in rows:
        for k, v in r["codes"].items():
            codes[k] = codes.get(k, 0) + v
    print(f"시행 {len(rows)} · 부호 합 {dict(sorted(codes.items()))} · 부호 4가 나온 시행 {sum('4' in r['codes'] for r in rows)}")
    print(f"(a) 일괄≠스트림 시행 {len(bad_stream)} {bad_stream[:10]}")
    print(f"(b) 접두부 불일치 시행 {len(bad_prefix)} {bad_prefix[:10]} · 대조한 접두부 {sum(r['prefix_n'] for r in rows)}곳")
    print(f"(c) 시작·격상 중복 사건이 있는 시행 {len(dup)} {dup[:10]} · 시작 없는 사건이 있는 시행 {len(nostart)}")
