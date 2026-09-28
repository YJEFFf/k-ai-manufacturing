"""redJ1: 운전 상태 분모·공백·부하 상태 오경보 재확인."""
import numpy as np, pandas as pd, runpy, io, contextlib
from scipy import stats
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns = runpy.run_path("redJ1_independent.py")
nor, ab, sn, sa, res, tn, ta = ns["nor"], ns["ab"], ns["sn"], ns["sa"], ns["res"], ns["tn"], ns["ta"]
g = pd.DataFrame(dict(seg=sn, x=nor.AI2_Current.to_numpy())).groupby("seg").x
rms = g.std(ddof=0); n = g.size()
state = pd.Series(np.where(n < 17, "short", np.where(rms >= 91.9, "load", "low")), index=rms.index)
print("normal states:", state.value_counts().to_dict())
for sid, (te, ce) in dict(A=(360, 480), B=(300, 420)).items():
    for part, m in (("cal", (state.index >= te) & (state.index < ce)), ("test", state.index >= ce)):
        s = state[m]; long = s[s != "short"]
        print(sid, part, s.value_counts().to_dict(), "low share among len>=17: %.3f" % (long == "low").mean())
    r = res[sid]; al = pd.Series(r["aN"]).groupby(sn[r["ts"]]).max()
    print(sid, "alarmed normal test records:", al[al].index.tolist(), "states:", state[al[al].index].tolist())
    load_test = state[(state.index >= ce) & (state == "load")]
    k = int(al[load_test.index].sum()); m_ = len(load_test)
    print(sid, "load-state alarm rate %d/%d" % (k, m_), " binomial one-sided p vs 1/121: %.4f" % stats.binom.sf(k-1, m_, 1/121) if k else "")
# gaps
for name, t, s in (("normal", tn, sn), ("abn", ta, sa)):
    d = t.diff().dt.total_seconds().to_numpy(); gaps = d[1:][s[1:] != s[:-1]]
    print(name, "gaps min/median/max: %.3f %.3f %.3f n=%d" % (gaps.min(), np.median(gaps), gaps.max(), len(gaps)))
# abnormal rows outside training range (A train)
tr = sn < 360
lo, hi = nor[tr][["AI0_Vibration", "AI1_Vibration", "AI2_Current"]].min(), nor[tr][["AI0_Vibration", "AI1_Vibration", "AI2_Current"]].max()
out = ((ab[lo.index] < lo) | (ab[lo.index] > hi))
print("abnormal rows outside A-train range: any", int(out.any(axis=1).sum()), out.sum().to_dict())
# how long is the quiet block: low-state run
print("alert units per elapsed hour (A test):", 120/((tn[sn >= 480].iloc[-1]-tn[sn >= 480].iloc[0]).total_seconds()/3600))
