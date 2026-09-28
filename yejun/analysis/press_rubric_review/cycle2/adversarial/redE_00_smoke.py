from redE_common import *
n, a = raw()
print(len(n), len(a), len(np.unique(record_ids(n))), len(np.unique(record_ids(a))))
m = models()
for s, mod in m.items():
    sp = split(n, s)
    pn = mod.predict(sp["test"]); pa = mod.predict(a)
    tp, fp = int(pa.alarm.sum()), int(pn.alarm.sum()); fn = len(pa) - tp
    print(s, "cal n", len(mod.cal), "thr(max cal)", float(np.max(mod.cal)), "tp fp fn", tp, fp, fn, "F1", 2*tp/(2*tp+fp+fn),
          "normal rec alarms", int(pn.groupby("record_id").alarm.max().sum()), "/", pn.record_id.nunique(),
          "prob attached", mod.probability is not None)
