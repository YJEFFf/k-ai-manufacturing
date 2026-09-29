"""검토 7: 경보가 드문 약한 이상(정상 평가 기록 30개에 전류 잡음 주입)에서 오류 한 행이 사건 구성을 바꾸는 비율.
대회 이상 파일은 경보가 촘촘해(569/600행, 기록 앞 무경보 최대 5행) 경보 단위가 쪼개져도 사건이 바뀌지 않는다. 경보가 드문 이상에서는
오류 한 행이 경보 단위를 '무경보 8행 이상 조각'으로 잘라 사건을 닫거나(분할), 무경보 기록을 8행 미만 두 조각으로 잘라 사건을 잇는다(합침).

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_weak.py --out 결과.csv [--workers 4] [--level 0.1]
주입: 정상 평가 B의 기록 20~49(30기록, 원래 시각·공백 그대로) 전류에 N(0, (L·σ_I)²)(보완 실험 E1의 cur_noise와 같은 정의, 시드 고정).
오류(한 행): +5초 튐(대체), 시각 결측, 센서 결측, +0.03초 흔들림, −0.15초(한 행 과거). 튄 행 자체의 경보·알림은 본체에서 뺀다.
"""
import argparse
import multiprocessing as mp

import numpy as np
import pandas as pd

_W = {}
FAULTS = [("replace", 5.0), ("nat", 0), ("nan", 0), ("replace", 0.03), ("replace", -0.15)]


def setup(level):
    import review7_lib as L
    mdl = L.model("B")
    nt = L.normal_test("B")
    seg = L.D.segments(nt)
    rows = np.flatnonzero((seg >= 20) & (seg < 50))
    frame = nt.iloc[rows].reset_index(drop=True).copy()
    z = np.random.default_rng(20260929).standard_normal(len(frame))
    cur = L.D.SENSORS[2]
    frame[cur] = frame[cur].to_numpy(float) + level * mdl.scale[2] * z
    times = pd.to_datetime(frame[L.D.TIME])
    return L, mdl, frame, times


def init(level):
    _W["L"], _W["M"], _W["F"], _W["T"] = setup(level)
    base = _W["M"].predict(_W["F"])
    _W["B"] = base


def incident_view(pred, err):
    """(오류 행을 뺀 경보 행이 속한 사건 수, 전체 시작 알림 수, 전체 격상 알림 수). 알림은 오류 행에서 나간 것도 사람에게 간 알림이라 모두 센다."""
    alarm = pred.alarm.eq(1).to_numpy() & ~err
    inc = pred.incident_id.to_numpy()
    return (len(set(inc[alarm])), int(pred.incident_notification.sum()), int(pred.incident_escalation.sum()))


def job(args):
    pos, kind, value = args
    L, M, F, T = _W["L"], _W["M"], _W["F"], _W["T"]
    f, err, _ = L.build(F, T, [(kind, pos, value)])
    p = M.predict(f)
    n, s, e = incident_view(p, err)
    b = _W["B"]
    base_err = np.zeros(len(b), bool); base_err[pos] = True          # 원자료에서도 같은 행의 경보는 뺀다
    bn, bs, be = incident_view(b, base_err)
    return dict(pos=pos, kind=kind, value=value, incidents=n, starts=s, escalations=e, base_incidents=bn, base_starts=bs, base_escalations=be,
                held=int((p.status == "bad_time_order").sum()), dup=int((p[p.incident_id.gt(0)].groupby("incident_id")[["incident_notification", "incident_escalation"]].sum() > 1).any(axis=1).sum()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--level", type=float, default=0.1)
    args = ap.parse_args()
    L, M, F, T = setup(args.level)
    b = M.predict(F)
    seg = b.record_id.to_numpy()
    rec_alarm = pd.Series(b.alarm.to_numpy()).groupby(seg).sum()
    print(f"# 판: {L.ENV.parent.name} · 주입 세기 {args.level}σ · {len(F)}행 {len(rec_alarm)}기록 · 경보 {int(b.alarm.sum())}행 · 경보 기록 {int((rec_alarm > 0).sum())} · "
          f"사건 {int(b.incident_id.max())} · 시작 {int(b.incident_notification.sum())} · 격상 {int(b.incident_escalation.sum())}")
    jobs = [(pos, k, v) for pos in range(1, len(F) - 1) for k, v in FAULTS]
    with mp.get_context("fork").Pool(args.workers, initializer=init, initargs=(args.level,)) as pool:
        rows = list(pool.imap(job, jobs, chunksize=16))
    d = pd.DataFrame(rows)
    d.to_csv(args.out, index=False)
    d["delta_inc"] = d.incidents - d.base_incidents
    for (k, v), g in d.groupby(["kind", "value"], sort=False):
        print(f"  {k:8s} {v:>6}: 위치 {len(g)} · 사건 늘어남(분할) {int((g.delta_inc > 0).sum())} · 줄어듦(합침) {int((g.delta_inc < 0).sum())} · "
              f"시작 알림 +{int((g.starts > g.base_starts).sum())}곳/−{int((g.starts < g.base_starts).sum())}곳 · 격상 +{int((g.escalations > g.base_escalations).sum())}곳/"
              f"−{int((g.escalations < g.base_escalations).sum())}곳 · 중복 알림 사건 {int(g.dup.sum())}")
