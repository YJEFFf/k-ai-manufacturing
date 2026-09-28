"""redJ1: E1 주입 탐지율 두 조건을 독립 구현으로 재확인(난수는 팀과 다르다)."""
import numpy as np, pandas as pd, runpy, io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns = runpy.run_path("redJ1_independent.py")
nor, sn, g = ns["nor"], ns["sn"], ns["g"]
M, segmax, pval, pos_in_seg, S = ns["M"], ns["segmax"], ns["pval"], ns["pos_in_seg"], ns["S"]
def quantX(X):
    o = X.copy(); o[:, :2] = np.round(o[:, :2]/1e-4)*1e-4; o[:, 2] = np.round(o[:, 2]/g)*g; return o
raw = nor[S].to_numpy(float)
for sid, (te, ce) in dict(A=(360, 480), B=(300, 420)).items():
    tr = sn < te; ca = (sn >= te) & (sn < ce); ts = sn >= ce
    m = M().fit(quantX(raw[tr]), sn[tr])
    cal = segmax(m.score(quantX(raw[ca]), sn[ca])[0], sn[ca])
    seg = sn[ts]; pos = pos_in_seg(seg); L = pd.Series(seg).groupby(seg).transform("size").to_numpy()
    elig = np.unique(seg[L >= 30]); mask = np.isin(seg, elig) & (pos >= 10)
    for fam, lv in (("none", 0), ("cur_noise", .1), ("vib_noise", 2), ("cur_offset", .2), ("cur_offset", .4), ("cur_gain", 1.15)):
        rates = []
        for rep in range(5 if "noise" in fam else 1):
            z = np.random.default_rng(777+rep).standard_normal((ts.sum(), 3))
            X = raw[ts].copy()
            if fam == "cur_noise": X[mask, 2] += lv*m.sd[2]*z[mask, 2]
            if fam == "vib_noise": X[mask, 0] += lv*m.sd[0]*z[mask, 0]; X[mask, 1] += lv*m.sd[1]*z[mask, 1]
            if fam == "cur_offset": X[mask, 2] += lv*np.sqrt(2)*m.sd[2]
            if fam == "cur_gain": X[mask, 2] = m.mu[2]+lv*(X[mask, 2]-m.mu[2])
            a = pval(cal, m.score(quantX(X), seg)[0]) <= .01
            det = [(a[(seg == r) & (pos >= 10) & (pos < 30)]).any() for r in elig]
            rates.append(np.mean(det))
        print(sid, fam, lv, "eligible", len(elig), "2s detect rate %.3f" % np.mean(rates))
