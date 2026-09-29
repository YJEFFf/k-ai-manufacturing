"""검토 7: 반례의 빈도·피해. 오류 한 번(시계 재설정, 여러 행 재전송, 여러 행 연속 튐)을 이상 파일의 모든 위치에 넣고,
이상 시작점(정상 → 이상)이 21번 있는 자료에서 시작점 주변 오류를 넣어 사건 분할·알림 중복·보류 행을 센다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_counter.py --out 결과.csv [--workers 4]
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

_W = {}


def init():
    import review7_lib as L
    import review7_scenarios_ctx as C
    _W["L"], _W["C"] = L, C
    _W["O"] = onset_frame(L, C)


def onset_frame(L, C):
    """정상 기록(경보 없음) 3초 → 이상 기록 하나 → 70초 공백을 21번 되풀이한다. 이상 기록마다 사건 하나(시작 1)가 원자료 기준이다."""
    nt = L.normal_test("B")
    pn = C.MDL.predict(nt)
    rec = pn.record_id.to_numpy()
    quiet = [r for r in np.unique(rec) if pn.alarm[rec == r].sum() == 0 and (rec == r).sum() >= 20]
    seg = L.D.segments(C.AB)
    parts, times, onsets, kinds = [], [], [], []
    t = pd.Timestamp("2022-07-20 00:00:00")
    for k, r in enumerate(np.unique(seg)):
        normal_rec = nt[rec == quiet[k]].reset_index(drop=True)
        abn = C.AB[seg == r].reset_index(drop=True)
        for frame, kind in ((normal_rec, "n"), (abn, "a")):
            if kind == "a":
                onsets.append(len(times))
            parts.append(L.D.inputs_only(frame))
            times += [t + pd.Timedelta(seconds=0.1 * j) for j in range(len(frame))]
            kinds += [kind] * len(frame)
            t = times[-1] + pd.Timedelta(seconds=3.0 if kind == "n" else 70.0)
    frame = L.with_times(pd.concat(parts, ignore_index=True), times)
    return frame, pd.Series(times), onsets, np.array(kinds)


def run(frame, err, base):
    L, C = _W["L"], _W["C"]
    p = C.MDL.predict(frame)
    s = L.summarize(p, err)
    return dict(held=s["held"], c2=s["c2"], c3=s["c3"], c4=s["c4"], body_incidents=s["body_incidents"], starts=s["starts"],
                escalations=s["escalations"], split=int(s["body_incidents"] > base["body_incidents"]),
                extra_starts=s["starts"] - base["starts"], extra_esc=s["escalations"] - base["escalations"],
                alarm_loss=base["body_alarms"] - s["body_alarms"], dup_alerts=s["dup_alerts"], alarms=s["alarms"])


def job(args):
    L, C = _W["L"], _W["C"]
    kind, pos, value = args
    if kind in ("step", "rexmit", "multi"):
        fr, tt, base = C.AB, C.TA, C.BASE["ab"]
        if kind == "step":
            faults = [("step", pos, value)]
        elif kind == "rexmit":
            if pos - value + 1 < 0:
                return None
            faults = [("rexmit", pos, value)]
        else:
            n, d = value
            if pos + n > len(fr):
                return None
            faults = [("replace", pos + j, d) for j in range(n)]
        f, err, _ = L.build(fr, tt, faults)
        r = run(f, err, base)
    else:                                            # 이상 시작점 k번째(pos)의 오류
        fr, tt, onsets, _ = _W["O"]
        if "obase" not in _W:
            _W["obase"] = L.summarize(C.MDL.predict(fr))
        base = _W["obase"]
        o = onsets[pos]
        if kind == "late1":
            faults = [("move", o - 1, 1)]
        elif kind == "late2rev":
            order = list(range(o - 2)) + [o, o - 1, o - 2] + list(range(o + 1, len(fr)))
            f = fr.iloc[order].reset_index(drop=True); err = np.zeros(len(f), bool); err[[o - 1, o]] = True
            return dict(kind=kind, pos=pos, value=str(value), **run(f, err, base))
        elif kind == "onset_spike":
            faults = [("replace", o, value)]
        elif kind == "onset_step":
            faults = [("step", o + 1, value)]
        elif kind == "onset_backlog":
            faults = [("backlog", o, value)]
        elif kind == "onset_tail":
            faults = [("tail", o, value)]
        f, err, _ = L.build(fr, tt, faults)
        r = run(f, err, base)
    return dict(kind=kind, pos=pos, value=str(value), **r)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--onset-only", action="store_true", help="이상 시작점 21곳 오류만(판 비교용)")
    args = ap.parse_args()
    jobs = [] if args.onset_only else [("step", p, -y) for p in range(1, 600) for y in (0.2, 0.3, 0.35, 0.5, 1, 5, 60, 3600)]
    jobs += [] if args.onset_only else [("rexmit", p, n) for p in range(1, 599) for n in (2, 3, 5, 10, 20)]
    jobs += [] if args.onset_only else [("multi", p, (n, d)) for p in range(1, 599) for n in (2, 3, 5) for d in (5.0, 3600.0)]
    jobs += [(k, o, v) for o in range(21) for k, v in (("late1", 1), ("late2rev", 2), ("onset_spike", 0.5), ("onset_spike", 5.0),
                                                        ("onset_spike", 3600.0), ("onset_step", -1.0), ("onset_step", -2.0),
                                                        ("onset_backlog", 10), ("onset_tail", 1), ("onset_tail", 3))]
    with mp.get_context("fork").Pool(args.workers, initializer=init) as pool:
        rows = [r for r in pool.imap(job, jobs, chunksize=8) if r is not None]
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows)}건 → {args.out}")
