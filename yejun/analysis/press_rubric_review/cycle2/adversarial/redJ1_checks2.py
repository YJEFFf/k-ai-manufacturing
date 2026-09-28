"""redJ1 추가 점검: 교환가능성, 단순 규칙 대비, 구간 단위 분리도, 워밍업 뒤 재현율."""
import numpy as np, pandas as pd, runpy, sys, io, contextlib
from scipy import stats
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns = runpy.run_path("redJ1_independent.py")
res, sn, sa, Xn, Xa = ns["res"], ns["sn"], ns["sa"], ns["Xn"], ns["Xa"]
pos_in_seg, segmax, M, pval, sine, win_idx = ns["pos_in_seg"], ns["segmax"], ns["M"], ns["pval"], ns["sine"], ns["win_idx"]
for sid in "AB":
    r = res[sid]
    tmax = segmax(r["sN"], sn[r["ts"]]); cal = r["cal"]
    med = np.median(cal)
    u = stats.mannwhitneyu(tmax, cal, alternative="two-sided")
    print(sid, "test seg max > cal median:", int((tmax > med).sum()), "/", len(tmax), " MWU p=%.2e" % u.pvalue,
          "| cal max(thr)=%.3f 2nd=%.3f 3rd=%.3f" % tuple(np.sort(cal)[::-1][:3]), "| test max top3", np.sort(tmax)[::-1][:3].round(3))
    amax = segmax(r["sA"], sa)
    print("   abnormal seg max: min %.2f median %.2f ; n abnormal seg max > every normal test seg max: %d/21 ; normal test max %.2f" % (amax.min(), np.median(amax), int((amax > tmax.max()).sum()), tmax.max()))
    p = pos_in_seg(sa); a = r["aA"]
    print("   recall at pos>=7: %d/%d = %.4f ; pos 2-6: %d/%d ; pos 0-1: %d/%d" % (a[p >= 7].sum(), (p >= 7).sum(), a[p >= 7].mean(), a[(p >= 2) & (p < 7)].sum(), ((p >= 2) & (p < 7)).sum(), a[p < 2].sum(), (p < 2).sum()))
    # upper bound of row F1 if everything at pos>=2 is caught and no FP
    for k in (0, 2, 7):
        tp = int((p >= k).sum()); print("   F1 if all rows with pos>=%d detected, 0 FP: %.4f" % (k, 2*tp/(2*tp+600-tp)), end="")
    print()
# very simple rule: |second difference of current| scaled by train sd, threshold = max over calibration segments (same conformal unit)
def d2(X, seg):
    x = X[:, 2]; o = np.full(len(x), np.nan); i = win_idx(seg, 3); o[i] = np.abs(x[i]-2*x[i-1]+x[i-2]); return o
def d1(X, seg):
    x = X[:, 2]; o = np.full(len(x), np.nan); i = win_idx(seg, 2); o[i] = np.abs(x[i]-x[i-1]); return o
for name, f in (("|2nd diff current|", d2), ("|1st diff current|", d1)):
    for sid, (te, ce) in dict(A=(360, 480), B=(300, 420)).items():
        ca = (sn >= te) & (sn < ce); ts = sn >= ce
        cal = segmax(f(Xn[ca], sn[ca]), sn[ca]); thr = np.sort(cal)[::-1][0]
        aN = f(Xn[ts], sn[ts]) > thr; aA = f(Xa, sa) > thr
        tp, fp = int(aA.sum()), int(aN.sum()); fn = 600-tp
        print(f"simple rule {name} split {sid}: TP {tp} FP {fp} FN {fn} F1 {2*tp/(2*tp+fp+fn):.4f} abn seg {int(pd.Series(aA).groupby(sa).max().sum())}/21 normal seg {int(pd.Series(aN).groupby(sn[ts]).max().sum())}")
# OR of simple rules: max|z| conformal OR 2nd diff (each calibrated at max; union)
for sid, (te, ce) in dict(A=(360, 480), B=(300, 420)).items():
    tr = sn < te; ca = (sn >= te) & (sn < ce); ts = sn >= ce
    mu, sd = Xn[tr].mean(0), Xn[tr].std(0)
    z = lambda X: np.abs((X-mu)/sd).max(1)
    sd2 = np.nanstd(d2(Xn[tr], sn[tr])); 
    comb = lambda X, s: np.fmax(z(X)/np.quantile(z(Xn[tr]), .999), d2(X, s)/np.nanquantile(d2(Xn[tr], sn[tr]), .999))
    cal = segmax(comb(Xn[ca], sn[ca]), sn[ca]); thr = cal.max()
    aN = comb(Xn[ts], sn[ts]) > thr; aA = comb(Xa, sa) > thr
    tp, fp = int(aA.sum()), int(aN.sum()); fn = 600-tp
    print(f"simple 2-feature max(z/q999, d2/q999) split {sid}: TP {tp} FP {fp} FN {fn} F1 {2*tp/(2*tp+fp+fn):.4f} abn seg {int(pd.Series(aA).groupby(sa).max().sum())}/21 normal seg {int(pd.Series(aN).groupby(sn[ts]).max().sum())}/{len(np.unique(sn[ts]))}")
