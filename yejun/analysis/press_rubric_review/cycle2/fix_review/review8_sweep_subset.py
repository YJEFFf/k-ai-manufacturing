"""검토 8: 검토 7 전수 모의(review7_sweep.py: 오류 32가지)를 4차 규칙이 작동하는 위치만 골라 두 판에서 다시 돌린다.
위치: 대회 이상 파일 각 기록의 첫 행·둘째 행·끝 앞 행·끝 행, 맥락 자료(정상 → 이상 → 정상)의 이상 시작·끝 ±3행.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review8_sweep_subset.py --out 결과.csv --workers 2
    python review8_sweep_subset.py --compare <8b65130 csv> <c7d8bba csv>
"""
import argparse
import multiprocessing as mp
import sys

import numpy as np
import pandas as pd

if "--compare" in sys.argv:
    i = sys.argv.index("--compare")
    a, b = pd.read_csv(sys.argv[i + 1]), pd.read_csv(sys.argv[i + 2])
    key = ["base", "pos", "kind", "value"]
    m = a.merge(b, on=key, suffixes=("", "_old"))
    print(f"대조 {len(m)}건 (8b65130 {len(a)}, c7d8bba {len(b)})")
    for col in ("split", "body_incidents", "held", "extra_starts", "body_extra_starts", "alarm_loss", "dup_alerts", "escalations"):
        worse = m[m[col] > m[col + "_old"]]
        better = m[m[col] < m[col + "_old"]]
        print(f"{col:18s}: 8b65130이 큼 {len(worse):5d}건 · 작음 {len(better):5d}건")
        for tag, part in (("큼", worse), ("작음", better)):
            if len(part):
                print(f"    {tag}:", part.groupby(["base", "kind", "value", "cls"]).size().to_dict())
    for label, x in (("8b65130", a), ("c7d8bba", b)):
        print(f"{label}: {len(x)}건 · 사건 분할 {int(x.split.sum())} · 본체 추가 시작 {int((x.body_extra_starts > 0).sum())} · 중복 알림 {int(x.dup_alerts.sum())} · "
              f"보류 합 {int(x.held.sum())} · 경보 감소 합 {int(x.alarm_loss.sum())}")
    sys.exit(0)

import review7_sweep as S  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    import review7_scenarios_ctx as C
    seg = C.D.segments(C.AB)
    first = np.flatnonzero(np.r_[True, seg[1:] != seg[:-1]])
    last = np.r_[first[1:] - 1, len(seg) - 1]
    pos = sorted({int(x) for x in np.r_[first, first + 1, last - 1, last] if 0 <= x < len(seg)})
    jobs = [("ab", p, k, v) for p in pos for k, v in S.FAULTS]
    jobs += [("cf", p, k, v) for p in list(range(C.N0 - 3, C.N0 + 4)) + list(range(C.N1 - 3, C.N1 + 4)) for k, v in S.FAULTS]
    with mp.get_context("fork").Pool(args.workers, initializer=S.init) as pool:
        rows = [r for r in pool.imap(S.job, jobs, chunksize=16) if r is not None]
    pd.DataFrame(rows).to_csv(args.out, index=False)
    print(f"위치 {len(pos)}+14곳 · {len(rows)}건 → {args.out}")
