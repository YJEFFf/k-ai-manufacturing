"""검토 7 공용 자료: 대회 이상 파일(AB·TA)과 맥락 자료(CF·TC: 경보 없는 정상 6기록 → 3초 → 이상 파일 → 3초 → 정상 6기록)."""
from review7_lib import *  # noqa: F401,F403

MDL = model("B")
AB, TA = base_abnormal()


def _context():
    nt = normal_test("B")
    pn = MDL.predict(nt)
    rec = pn.record_id.to_numpy()
    quiet = [r for r in np.unique(rec) if pn.alarm[rec == r].sum() == 0 and (rec == r).sum() >= 20]
    pre = pd.concat([nt[rec == r] for r in quiet[:6]], ignore_index=True)
    post = pd.concat([nt[rec == r] for r in quiet[6:12]], ignore_index=True)

    def restamp(frame, start):
        tt = pd.to_datetime(frame[D.TIME]); out = [pd.Timestamp(start)]
        for k in range(1, len(frame)):
            d = (tt.iloc[k] - tt.iloc[k - 1]).total_seconds()
            out.append(out[-1] + pd.Timedelta(seconds=0.1 if abs(d - 0.1) < 1e-6 else 3.0))
        return out
    pre_t = restamp(pre, TA.iloc[0])
    shift = (pre_t[-1] - TA.iloc[0]) + pd.Timedelta(seconds=3)
    pre_t = [x - shift for x in pre_t]
    post_t = restamp(post, TA.iloc[-1] + pd.Timedelta(seconds=3))
    full = pd.concat([D.inputs_only(pre), AB, D.inputs_only(post)], ignore_index=True)
    times = pd.Series(pre_t + list(TA) + post_t)
    return with_times(full, times), times, len(pre), len(pre) + len(AB)


CF, TC, N0, N1 = _context()
BASE = {"ab": summarize(MDL.predict(AB)), "cf": summarize(MDL.predict(CF))}
_SEG = {"ab": D.segments(AB), "cf": D.segments(CF)}


def position_class(base, pos):
    seg = _SEG[base]
    n = len(seg)
    if pos == 0:
        return "file_first"
    if pos == n - 1:
        return "file_last"
    first = seg[pos] != seg[pos - 1]
    last = seg[pos] != seg[pos + 1]
    if first and last:
        return "record_single"
    return "record_first" if first else ("record_last" if last else "interior")
