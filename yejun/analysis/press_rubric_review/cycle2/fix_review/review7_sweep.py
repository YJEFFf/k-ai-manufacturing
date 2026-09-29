"""검토 7: 한 행 시각 오류의 전수 모의. 대회 이상 파일 600행의 모든 행과, 맥락 자료(정상 → 이상 → 정상)의 이상 시작·끝 주변 행에
한 가지 오류를 넣고 보류 행·부호·본체 사건 수·알림 수를 센다. 오류는 모두 '한 번'이다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_sweep.py --out 결과.csv [--workers 4]
종류: replace(+Δ, 표본 대체), insert_after(+Δ 사본을 바로 뒤에 끼움), back(−Δ, 한 행 과거로), move(m행 늦게 도착), dup(바로 뒤 재전송).
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

FAULTS = ([("replace", d) for d in (0.05, 0.13, 0.2, 0.25, 0.3, 0.35, 0.5, 1, 2, 5, 10, 16.7, 30, 59.9, 60.1, 3600)]
          + [("insert_after", d) for d in (0.13, 0.5, 5, 60.1, 3600)]
          + [("replace", -d) for d in (0.05, 0.15, 0.3, 1, 5, 3600)]
          + [("move", m) for m in (1, 2, 3, 5)] + [("dup", 0)])
_W = {}


def init():
    import review7_lib as L
    import review7_scenarios_ctx as C
    _W["L"], _W["C"] = L, C


def job(args):
    base, pos, kind, value = args
    L, C = _W["L"], _W["C"]
    fr, tt = (C.AB, C.TA) if base == "ab" else (C.CF, C.TC)
    if kind == "move" and pos + value >= len(fr):
        return None
    f, err, _ = L.build(fr, tt, [(kind, pos, value)])
    p = C.MDL.predict(f)
    s = L.summarize(p, err)
    b = C.BASE[base]
    return dict(base=base, pos=pos, cls=C.position_class(base, pos), kind=kind if kind != "replace" or value > 0 else "back",
                value=abs(value) if kind == "replace" else value, held=s["held"], c2=s["c2"], c3=s["c3"], c4=s["c4"],
                alarm_loss=b["body_alarms"] - s["body_alarms"], body_incidents=s["body_incidents"],
                split=int(s["body_incidents"] > b["body_incidents"]), starts=s["starts"], escalations=s["escalations"],
                extra_starts=s["starts"] - b["starts"], body_extra_starts=s["body_starts"] - b["body_starts"], dup_alerts=s["dup_alerts"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    import review7_scenarios_ctx as C
    jobs = [("ab", pos, k, v) for pos in range(600) for k, v in FAULTS]
    jobs += [("cf", pos, k, v) for pos in list(range(C.N0 - 3, C.N0 + 4)) + list(range(C.N1 - 3, C.N1 + 4)) for k, v in FAULTS]
    with mp.get_context("fork").Pool(args.workers, initializer=init) as pool:
        rows = [r for r in pool.imap(job, jobs, chunksize=16) if r is not None]
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"{len(rows)}건 → {args.out}")
