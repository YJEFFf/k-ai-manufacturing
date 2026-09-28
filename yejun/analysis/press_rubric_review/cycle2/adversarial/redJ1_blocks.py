"""redJ1: 시간순 5겹 재확인 + 팀이 하지 않은 역방향·교차 블록 검증(정상 오경보율의 시간 안정성)."""
import numpy as np, pandas as pd, runpy, io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ns = runpy.run_path("redJ1_independent.py")
sn, sa, Xn, Xa = ns["sn"], ns["sa"], ns["Xn"], ns["Xa"]
M, segmax, pval = ns["M"], ns["segmax"], ns["pval"]
def run(tr, ca, ts, tag):
    m = M().fit(Xn[tr], sn[tr]); cal = segmax(m.score(Xn[ca], sn[ca])[0], sn[ca])
    sN = m.score(Xn[ts], sn[ts])[0]; sA = m.score(Xa, sa)[0]
    out = []
    for a in (.01, .03, .05):
        if np.floor(a*(len(cal)+1)) < 1: out.append("n/a"); continue
        aN = pval(cal, sN) <= a; aA = pval(cal, sA) <= a
        nseg = int(pd.Series(aN).groupby(sn[ts]).max().sum()); tot = len(np.unique(sn[ts]))
        tp = int(aA.sum()); fp = int(aN.sum())
        out.append(f"a={a}: normal {nseg}/{tot}, abn seg {int(pd.Series(aA).groupby(sa).max().sum())}/21, FN {600-tp}, F1 {2*tp/(2*tp+fp+600-tp):.4f}")
    print(tag, "|", " ; ".join(out), "| thr1%% = %.3f" % np.sort(cal)[-1])
print("== forward rolling (team protocol)")
for end in (180, 240, 300, 360, 420):
    run(sn < end, (sn >= end) & (sn < end+120), (sn >= end+120) & (sn < end+180), f"train 0-{end-1}, cal {end}-{end+119}, test {end+120}-{end+179}")
print("== reverse-time (train late, calibrate middle, test early)")
for start in (0, 60, 120, 180):
    ts = (sn >= start) & (sn < start+60); ca = (sn >= start+60) & (sn < start+180); tr = sn >= start+180
    run(tr, ca, ts, f"test {start}-{start+59}, cal {start+60}-{start+179}, train {start+180}-599")
print("== 5-block cross (each 120-seg block as test; calibrate on next block cyclically; train on the rest)")
tot_alarm = {a: 0 for a in (.01, .03, .05)}
for b in range(5):
    ts = (sn >= b*120) & (sn < (b+1)*120); cb = (b+1) % 5; ca = (sn >= cb*120) & (sn < (cb+1)*120); tr = ~ts & ~ca
    run(tr, ca, ts, f"test block {b} ({b*120}-{(b+1)*120-1}), cal block {cb}")
