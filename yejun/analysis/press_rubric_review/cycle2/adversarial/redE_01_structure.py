"""E-1a 자료 구조: 기록 시각·간격·길이, 이상 21기록이 한 에피소드인지, 정상 오경보의 시간 간격."""
from redE_common import *

n, a = raw()
out = {}
for name, f in (("normal", n), ("abnormal", a)):
    seg = record_ids(f)
    t = pd.to_datetime(f["TimeStamp"])
    g = pd.DataFrame(dict(seg=seg, t=t)).groupby("seg").t.agg(["min", "max", "size"])
    gap = (g["min"].iloc[1:].to_numpy() - g["max"].iloc[:-1].to_numpy()) / np.timedelta64(1, "s")
    out[name] = dict(rows=len(f), records=len(g), start=str(t.min()), end=str(t.max()),
                     elapsed_s=float((t.max() - t.min()).total_seconds()), recorded_s=float(len(f) * .1),
                     duty=float(len(f) * .1 / (t.max() - t.min()).total_seconds()),
                     len_min=int(g["size"].min()), len_median=float(g["size"].median()), len_max=int(g["size"].max()),
                     gap_min=float(gap.min()), gap_median=float(np.median(gap)), gap_max=float(gap.max()),
                     records_lt8=int((g["size"] < 8).sum()), records_lt17=int((g["size"] < 17).sum()), records_lt30=int((g["size"] < 30).sum()))
    print(name, out[name])
    if name == "abnormal":
        print(g.assign(gap_before=np.r_[np.nan, gap]).to_string())
    if name == "normal":
        for r in (423, 461, 570):
            print("FA record", r, g.loc[r].to_dict())
        ts = g["min"]
        print("423->461 s", (ts[461] - ts[423]).total_seconds(), "461->570 s", (ts[570] - ts[461]).total_seconds())
        out["false_alarm_records"] = {str(r): str(ts[r]) for r in (423, 461, 570)}
        out["fa_gap_s"] = [float((ts[461] - ts[423]).total_seconds()), float((ts[570] - ts[461]).total_seconds())]
        for lab, lo, hi in (("A_cal", 360, 480), ("A_test", 480, 600), ("B_cal", 300, 420), ("B_test", 420, 600)):
            print(lab, str(g["min"][lo]), "~", str(g["max"][hi - 1]), "elapsed min", (g["max"][hi - 1] - g["min"][lo]).total_seconds() / 60)
            out[lab] = dict(start=str(g["min"][lo]), end=str(g["max"][hi - 1]), elapsed_min=float((g["max"][hi - 1] - g["min"][lo]).total_seconds() / 60))
dump(out, "redE_01_structure.json")
