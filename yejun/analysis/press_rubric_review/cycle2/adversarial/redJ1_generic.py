"""redJ1: 손으로 만든 사인·AR 특징 없이, 일반 창 모델(PCA 재구성 오차)을 같은 보정 규칙에 넣으면 어떤가(기준모델 공정성 점검)."""
import numpy as np, pandas as pd, runpy, io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns = runpy.run_path("redJ1_independent.py")
sn, sa, Xn, Xa = ns["sn"], ns["sa"], ns["Xn"], ns["Xa"]
Tail, segmax, pval, pos_in_seg, win_idx = ns["Tail"], ns["segmax"], ns["pval"], ns["pos_in_seg"], ns["win_idx"]
def windows(Z, seg, w, cols):
    idx = win_idx(seg, w)
    return idx, np.stack([Z[i-w+1:i+1][:, cols].ravel() for i in idx]) if len(idx) else np.empty((0, w*len(cols)))
class PCAwin:
    def __init__(s, w, cols, var=.99): s.w, s.cols, s.var = w, cols, var
    def fit(s, Z, seg):
        _, X = windows(Z, seg, s.w, s.cols); s.m = X.mean(0)
        U, S, Vt = np.linalg.svd(X-s.m, full_matrices=False)
        k = int(np.searchsorted(np.cumsum(S**2)/np.sum(S**2), s.var)+1); s.V = Vt[:k]; s.k = k; return s
    def score(s, Z, seg):
        o = np.full(len(Z), np.nan); idx, X = windows(Z, seg, s.w, s.cols)
        if len(idx):
            R = (X-s.m)-((X-s.m)@s.V.T)@s.V; o[idx] = np.sqrt((R*R).mean(1))
        return o
for cfg in (dict(w=6, cols=[2], var=.99), dict(w=6, cols=[0, 1, 2], var=.95), dict(w=3, cols=[2], var=.99), dict(w=4, cols=[2], var=.99)):
    for sid, (te, ce) in dict(A=(360, 480), B=(300, 420)).items():
        tr = sn < te; ca = (sn >= te) & (sn < ce); ts = sn >= ce
        mu, sd = Xn[tr].mean(0), Xn[tr].std(0)
        Z = lambda X: (X-mu)/sd
        p = PCAwin(**cfg).fit(Z(Xn[tr]), sn[tr])
        tz = Tail(np.abs(Z(Xn[tr])).max(1)); tp_ = Tail(p.score(Z(Xn[tr]), sn[tr]))
        sc = lambda X, s: np.fmax(tz(np.abs(Z(X)).max(1)), tp_(p.score(Z(X), s)))
        cal = segmax(sc(Xn[ca], sn[ca]), sn[ca])
        aN = pval(cal, sc(Xn[ts], sn[ts])) <= .01; aA = pval(cal, sc(Xa, sa)) <= .01
        tp, fp = int(aA.sum()), int(aN.sum()); fn = 600-tp
        print(f"PCA-window w={cfg['w']} cols={cfg['cols']} k={p.k} + max|z| (fmax, same conformal) split {sid}: TP {tp} FP {fp} FN {fn} F1 {2*tp/(2*tp+fp+fn):.4f} abn seg {int(pd.Series(aA).groupby(sa).max().sum())}/21 normal seg {int(pd.Series(aN).groupby(sn[ts]).max().sum())}/{len(np.unique(sn[ts]))}")
