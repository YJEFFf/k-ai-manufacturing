"""redJ1 독립 재계산: 팀 코드를 import하지 않고 원본 CSV에서 핵심 수치를 다시 만든다."""
import numpy as np, pandas as pd, sys, re
from pathlib import Path
RAW = Path("/Volumes/YJSSD/공모전/k-제조데이터/yejun/press_submission/data/3_소성가공_예지보전")
S = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
nor = pd.read_csv(RAW/"press_data_normal.csv"); ab = pd.read_csv(RAW/"outlier_data.csv")
print("rows", len(nor), len(ab), "cols", list(nor.columns))
print("label uniq", nor.Equipment_state.unique(), ab.Equipment_state.unique())
print("NaN", int(nor[S].isna().sum().sum()), int(ab[S].isna().sum().sum()))

def segs(df, tol=0.02):
    t = pd.to_datetime(df.TimeStamp)
    d = t.diff().dt.total_seconds()
    new = (d.sub(0.1).abs() > tol).fillna(False).to_numpy()
    new[0] = False
    return np.cumsum(new), t
sn, tn = segs(nor); sa, ta = segs(ab)
print("segments", sn.max()+1, sa.max()+1)
ln = pd.Series(sn).value_counts(); la = pd.Series(sa).value_counts()
print("normal seg len: min/med/max", ln.min(), ln.median(), ln.max(), " n(len==50)", int((ln==50).sum()), " n(len<17)", int((ln<17).sum()), "n(len<8)", int((ln<8).sum()))
print("abn seg len: min/med/max", la.min(), la.median(), la.max(), " n(len==50)", int((la==50).sum()), sorted(la.sort_index().tolist()))
print("time normal", tn.iloc[0], tn.iloc[-1], "elapsed min", (tn.iloc[-1]-tn.iloc[0]).total_seconds()/60, "recorded s", len(nor)*0.1)
print("time abn", ta.iloc[0], ta.iloc[-1], "elapsed min", (ta.iloc[-1]-ta.iloc[0]).total_seconds()/60, "recorded s", len(ab)*0.1)
print("coverage normal", len(nor)*0.1/((tn.iloc[-1]-tn.iloc[0]).total_seconds()+0.1), "abn", len(ab)*0.1/((ta.iloc[-1]-ta.iloc[0]).total_seconds()+0.1))
print("weekday", tn.iloc[0].day_name(), ta.iloc[0].day_name())
# duplicates
print("dup full rows normal", int(nor.drop(columns=nor.columns[0]).duplicated().sum()), "dup ts", int(nor.TimeStamp.duplicated().sum()))
# storage format: decimals from raw text
def decimals(path, col):
    raw = pd.read_csv(path, dtype=str)
    return raw[col].map(lambda s: len(s.split(".")[1]) if "." in s and "e" not in s.lower() else -1)
for c in S:
    dn = decimals(RAW/"press_data_normal.csv", c); da = decimals(RAW/"outlier_data.csv", c)
    print(c, "normal decimals mode", dn.mode().iloc[0], "max", dn.max(), "| abn mode", da.mode().iloc[0], "max", da.max(),
          "| rule decimals>=7 -> flags normal", int((dn>=7).sum()), "abn", int((da>=7).sum()))
# current grid
g = 1.1920929
for name, df in (("normal", nor), ("abn", ab)):
    r = np.abs(df.AI2_Current/g - np.round(df.AI2_Current/g))*g
    print(name, "current on grid(tol1e-3)", float((r<1e-3).mean()))
print("SD normal", nor[S].std().round(4).to_dict(), "SD abn", ab[S].std().round(4).to_dict())
print("corr AI0-AI1 normal", round(nor.AI0_Vibration.corr(nor.AI1_Vibration),3), "abn", round(ab.AI0_Vibration.corr(ab.AI1_Vibration),3))

# ---------- independent v2 ----------
FREQS = np.arange(0.0, 5.0001, 0.005)
def quant(df):
    o = df[S].to_numpy(float).copy()
    o[:, :2] = np.round(o[:, :2]/1e-4)*1e-4
    o[:, 2] = np.round(o[:, 2]/g)*g
    return o
def win_idx(seg, w):
    i = np.arange(w-1, len(seg)); return i[seg[i] == seg[i-w+1]]
_H = {}
def hats(w):
    if w not in _H:
        t = np.arange(w)*0.1; hs = []
        for f in FREQS:
            A = np.column_stack([np.sin(2*np.pi*f*t), np.cos(2*np.pi*f*t), np.ones(w)])
            hs.append(A @ np.linalg.pinv(A))
        _H[w] = np.stack(hs)
    return _H[w]
def sine(x, seg, w):
    out = np.full(len(x), np.nan); idx = win_idx(seg, w)
    if not len(idx): return out
    W = np.stack([x[i-w+1:i+1] for i in idx])
    sst = ((W-W.mean(1, keepdims=True))**2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in hats(w):
        r = W - W @ H.T
        best = np.minimum(best, (r*r).sum(1))
    v = np.where(sst > 0, best/np.where(sst > 0, sst, 1), np.nan)
    out[idx] = np.clip(v, 0, None); return out
class Tail:
    def __init__(s, ref, q=.95):
        r = np.sort(ref[np.isfinite(ref)]); s.r = r; s.n = len(r); s.u = np.quantile(r, q)
        e = r[r > s.u]-s.u; s.b = e.mean(); s.gu = s.emp(np.array([s.u]))[0]
    def emp(s, v):
        ge = s.n-np.searchsorted(s.r, v, side="left"); return -np.log10((ge+1)/(s.n+1))
    def __call__(s, v):
        v = np.asarray(v, float); o = np.full(v.shape, np.nan); ok = np.isfinite(v); x = v[ok]
        res = np.where(x <= s.u, s.emp(x), s.gu+(x-s.u)/(s.b*np.log(10))); o[ok] = res; return o
def pos_in_seg(seg):
    return pd.Series(seg).groupby(seg).cumcount().to_numpy()
class M:
    def fit(s, X, seg):
        s.mu = X.mean(0); s.sd = X.std(0)
        z = np.abs((X-s.mu)/s.sd).max(1)
        x = X[:, 2]; i = win_idx(seg, 3)
        D_ = np.column_stack([np.ones(len(i)), x[i-1], x[i-2]])
        s.c = np.linalg.lstsq(D_, x[i], rcond=None)[0]
        s.tz = Tail(z); s.t6 = Tail(sine(x, seg, 6)); s.t8 = Tail(sine(x, seg, 8)); s.ta = Tail(s.ar(x, seg)); return s
    def ar(s, x, seg):
        o = np.full(len(x), np.nan); i = win_idx(seg, 3)
        o[i] = np.abs(x[i]-s.c[0]-s.c[1]*x[i-1]-s.c[2]*x[i-2]); return o
    def score(s, X, seg, v1=False):
        z = np.abs((X-s.mu)/s.sd).max(1); x = X[:, 2]; p = pos_in_seg(seg)
        gz = s.tz(z); g8 = s.t8(sine(x, seg, 8))
        if v1: return np.fmax(gz, g8), dict(gz=gz)
        gs = np.where(p < 7, s.t6(sine(x, seg, 6)), g8); ga = s.ta(s.ar(x, seg))
        return np.fmax(np.fmax(gz, gs), ga), dict(gz=gz, gs=gs, ga=ga)
def segmax(sc, seg):
    return pd.Series(np.where(np.isfinite(sc), sc, -np.inf)).groupby(seg).max().to_numpy()
def pval(cal, sc):
    r = np.sort(cal); o = np.full(len(sc), np.nan); ok = np.isfinite(sc)
    o[ok] = (len(r)-np.searchsorted(r, sc[ok], side="left")+1)/(len(r)+1); return o
Xn = quant(nor); Xa = quant(ab)
res = {}
for sid, (te, ce) in dict(A=(360, 480), B=(300, 420)).items():
    tr = sn < te; ca = (sn >= te) & (sn < ce); ts = sn >= ce
    m = M().fit(Xn[tr], sn[tr])
    for v1 in (False, True):
        cal = segmax(m.score(Xn[ca], sn[ca], v1)[0], sn[ca])
        sN, cN = m.score(Xn[ts], sn[ts], v1); sA, cA = m.score(Xa, sa, v1)
        for a in (.01, .03, .05):
            aN = pval(cal, sN) <= a; aA = pval(cal, sA) <= a
            tp, fp = int(aA.sum()), int(aN.sum()); fn = len(aA)-tp
            nseg = int(pd.Series(aN).groupby(sn[ts]).max().sum()); aseg = int(pd.Series(aA).groupby(sa).max().sum())
            f1 = 2*tp/(2*tp+fp+fn)
            first = pd.DataFrame(dict(s=sa, p=pos_in_seg(sa), a=aA)).query("a").groupby("s").p.min()
            print(f"{sid} {'v1' if v1 else 'v2'} a={a}: TP {tp} FP {fp} FN {fn} F1 {f1:.6f} normal_seg {nseg}/{len(np.unique(sn[ts]))} abn_seg {aseg}/21 max_first_delay {first.max()*0.1:.1f}s thr={np.sort(cal)[::-1][int(np.floor(a*(len(cal)+1)))-1]:.3f}")
            if not v1 and a == .01:
                res[sid] = dict(aA=aA, aN=aN, sN=sN, sA=sA, cal=cal, ts=ts, comp=cA)
    print(sid, "AR2 coef", m.c.round(4), "test rows", int(ts.sum()), "anom frac", round(600/(600+ts.sum()), 4), "all-positive F1", round(2*600/(2*600+ts.sum()), 3))
# position-wise misses
for sid in "AB":
    p = pos_in_seg(sa); miss = ~res[sid]["aA"]
    print(sid, "miss pos<2:", int(miss[p < 2].sum()), "/", int((p < 2).sum()), " pos>=2:", int(miss[p >= 2].sum()), "/", int((p >= 2).sum()))
np.save("/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/redJ1_work/redJ1_alarmA.npy", res["A"]["aA"])
