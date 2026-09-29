"""검토 7: 체계적인 작은 시각 오류(모든 기록의 첫 행 또는 끝 행이 δ초 늦게 찍힘, 예: 수집 시작 지연)가 보류·탐지·사건에 주는 영향.
대회 이상 파일(21기록)과 정상 평가 구간(B, 180기록)에 넣고 판마다 비교한다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_systematic.py
"""
from review7_lib import *  # noqa: F401,F403

mdl = model("B")
ab, ta = base_abnormal()
nt = normal_test("B")
tn = pd.to_datetime(nt[D.TIME])


def shifted(frame, times, which, delta):
    seg = D.segments(frame)
    first = np.r_[True, seg[1:] != seg[:-1]]
    last = np.r_[seg[1:] != seg[:-1], True]
    mask = first if which == "first" else last
    tt = times.copy()
    tt[mask] = tt[mask] + pd.Timedelta(seconds=delta)
    return with_times(frame, tt), mask, seg


print(f"# 판: {ENV.parent.name}")
for which in ("first", "last"):
    for delta in (0.0, 0.05, 0.13, 0.15, 0.2, 0.25, 0.3, 0.5, 1.0):
        fa, ma, sa = shifted(ab, ta, which, delta)
        fn, mn, sn = shifted(nt, tn, which, delta)
        pa, pn = mdl.predict(fa), mdl.predict(fn)
        detected = pd.Series(pa.alarm.to_numpy()).groupby(sa).max().sum()
        fp_rec = pd.Series(pn.alarm.to_numpy()).groupby(sn).max().sum()
        print(f"{'첫' if which == 'first' else '끝'} 행 +{delta:<5g}: 이상 보류 {int((pa.status == 'bad_time_order').sum()):3d}행 · 경보 {int(pa.alarm.sum())}행 · "
              f"탐지 기록 {int(detected)}/21 · 사건 {int(pa.incident_id.max())}·시작 {int(pa.incident_notification.sum())} | "
              f"정상 보류 {int((pn.status == 'bad_time_order').sum()):4d}행 · 오경보 {int(pn.alarm.sum())}행·{int(fp_rec)}기록 · "
              f"부호2 {int((pn.time_order_event == 2).sum())}·부호4 {int((pn.time_order_event == 4).sum())}")
