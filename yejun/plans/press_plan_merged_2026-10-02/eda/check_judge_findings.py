"""통합안 점검 ②: 블라인드 심사자가 원자료로 제기한 정정을 독립 재계산한다.

① 진동 내보내기 경로: 감도 격자(LSB/S)를 넓게 훑어 버스트 안 차분이 어느 감도에 맞는지, 버스트 평균(DC)이 남아 있는지
② 공식(가이드북) 시험 창에서 한 줄 규칙: 버스트 판정을 창에 적용한 판 대 창 자신의 20행만 쓴 판, 모두-정상 정확도
③ 드리프트: 가압 버스트 부하 보정 잔차의 10분 블록 중앙값(블록 단위 단조성)

실행: python check_judge_findings.py --root <데이터셋/프레스_유압펌프_예지보전>   (원본 CSV 읽기 전용, 수 초)
"""
import argparse, os, sys, math
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'press_research_claude_2026-10-01', 'eda'))
from eda_facts import load

ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)
LSB = 10 / 2**23

# ① 감도 격자: 버스트 안 차분이 LSB/S의 정수배에 가까운 비율(허용 ±0.05 계수)
def diffs(df, col):
    out = []
    for _, g in df.groupby('burst'):
        if len(g) >= 2: out.append(np.diff(g[col].values))
    return np.concatenate(out)
def share(d, step, tol=0.05):
    k = d / step; return float(np.mean(np.abs(k - np.round(k)) < tol))
sens = np.round(np.arange(0.0900, 0.1200 + 1e-9, 0.0005), 4)
print('① sensitivity scan of within-burst differences (share on LSB/S lattice, tol 0.05 counts)')
for nm, df in [('normal', N), ('abnormal', A)]:
    for col in ['AI0_Vibration', 'AI1_Vibration']:
        d = diffs(df, col); d = d[d != 0]
        sh = np.array([share(d, LSB / s) for s in sens]); i = int(np.argmax(sh))
        top = sorted(zip(sh, sens), reverse=True)[:3]
        ctrl = share(d + np.random.default_rng(0).uniform(-0.5, 0.5, len(d)) * LSB / sens[i], LSB / sens[i])
        print(f'   {nm:8s} {col}: best S = {sens[i]:.4f} V/g share {sh[i]:.3f} | top3 {[(round(float(s),4), round(float(v),3)) for v, s in top]} | jitter control {ctrl:.3f} | n diffs {len(d)}')
for nm, df in [('normal', N), ('abnormal', A)]:
    g = df.groupby('burst'); n = g.size()
    for col in ['AI0_Vibration', 'AI1_Vibration']:
        m = g[col].mean()[n >= 10].abs()
        print(f'   {nm:8s} {col}: |burst mean| median {m.median():.2e} g, p90 {m.quantile(.9):.2e}; file mean {df[col].mean():+.4f}')

# ② 가이드북 시험 창(20행, +100 시점): 정상 15,000–19,999행의 창 중 880번째부터 4,000개, 이상 0–599행의 창 중 300번째부터 180개
seq, ahead = 20, 100
def wins(n0, n, skip): return [(n0 + i, n0 + i + seq) for i in range(n - seq - ahead)][skip:]
wN = wins(15000, 5000, 880); wA = wins(0, 600, 300)
print(f'\n② guidebook test windows: normal {len(wN)} (rows {wN[0][0]}–{wN[-1][1]-1}), abnormal {len(wA)} (rows {wA[0][0]}–{wA[-1][1]-1}); all-normal accuracy {len(wN)/(len(wN)+len(wA)):.4f} (whole-file row ratio {20000/20600:.4f})')
thr = N.AI0_Vibration.iloc[:15000].abs().max()
xN, xA = N.AI0_Vibration.abs().values, A.AI0_Vibration.abs().values
bN = N.groupby('burst').AI0_Vibration.transform(lambda s: s.abs().max()).values > thr
bA = A.groupby('burst').AI0_Vibration.transform(lambda s: s.abs().max()).values > thr
f1 = lambda tp, fp, fn: 2 * tp / (2 * tp + fp + fn)
for nm, pn, pa in [('window own 20 rows', [xN[s:e].max() > thr for s, e in wN], [xA[s:e].max() > thr for s, e in wA]),
                   ('burst decision (atomic snapshot)', [bN[s:e].any() for s, e in wN], [bA[s:e].any() for s, e in wA]),
                   ('last row of window only', [xN[e-1] > thr for s, e in wN], [xA[e-1] > thr for s, e in wA])]:
    pn, pa = np.array(pn), np.array(pa); tp, fp, fn = int(pa.sum()), int(pn.sum()), int((~pa).sum())
    print(f'   threshold {thr:.4f} | {nm:32s}: TP {tp:3d} FP {fp} FN {fn:3d} F1 {f1(tp, fp, fn):.3f}')
gb = A.groupby('burst').AI0_Vibration.apply(lambda s: s.abs().max())
quiet = [(int(b), int(A.index[A.burst == b].min()), int(A.index[A.burst == b].max())) for b in gb.index[gb <= thr]]
print(f'   abnormal bursts over threshold {int((gb > thr).sum())}/21; under-threshold bursts (id, first row, last row): {quiet}')

# ③ 드리프트: 가압(A60 > 180) 버스트, log RMS(AI1)를 log 부하 3차식으로 보정한 잔차의 10분 블록 중앙값(0–60분)
def a60(x):
    k = np.arange(len(x)); X = np.column_stack([np.ones(len(x)), np.cos(2*np.pi*0.06*k), np.sin(2*np.pi*0.06*k)])
    b = np.linalg.lstsq(X, x, rcond=None)[0]; return np.hypot(b[1], b[2])
rows = [dict(t0=d.ts.iloc[0], amp=a60(d.AI2_Current.values), v1=np.sqrt(np.mean(d.AI1_Vibration**2)))
        for _, d in N.groupby('burst') if len(d) >= 10]
B = pd.DataFrame(rows); L = B[(B.t0 < 3600) & (B.amp > 180)].copy()
X = np.column_stack([np.ones(len(L))] + [np.log(L.amp.values) ** k for k in (1, 2, 3)])
y = np.log(L.v1.values); r = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
L['r'] = r; L['blk'] = (L.t0 // 600).astype(int)
med = L.groupby('blk').r.median()
mono = bool(np.all(np.diff(med.values) > 0))
print('\n③ loaded-burst residual (AI1) 10-min block medians:', [round(float(v), 3) for v in med.values], '| strictly increasing:', mono,
      f'| exact one-sided permutation p for a perfectly increasing order of {len(med)} blocks = 1/{math.factorial(len(med))} = {1/math.factorial(len(med)):.4f}')
ac1 = np.corrcoef(r[:-1], r[1:])[0, 1]
print(f'   lag-1 autocorrelation of residual series (time order) {ac1:.2f}')

# ④ 진동 정합(버스트 평균 제거, 감도 환산) 뒤에도 규칙이 유지되는가
def aligned(df, upper_scale=1.0, lower_scale=1.0):
    d = df.copy()
    for col, sc in [('AI0_Vibration', upper_scale), ('AI1_Vibration', lower_scale)]:
        d[col] = (d[col] - d.groupby('burst')[col].transform('mean')) * sc
    return d
print('\n④ rules after vibration alignment (burst-mean removal; abnormal also rescaled to the 105 mV/g convention: upper x0.108/0.105, lower x0.103/0.105)')
for label, Nn, Aa in [('raw (as exported)', N, A),
                      ('burst-mean removed', aligned(N), aligned(A)),
                      ('mean removed + abnormal rescaled', aligned(N), aligned(A, 0.108/0.105, 0.103/0.105))]:
    thr_r = Nn.AI0_Vibration.iloc[:15000].abs().max()
    gbm = Aa.groupby('burst').AI0_Vibration.apply(lambda s: s.abs().max())
    rms = lambda d: float(np.sqrt(np.mean(d.AI0_Vibration**2)))
    nb = [(d.ts.iloc[0], rms(d)) for _, d in Nn.groupby('burst') if len(d) >= 10]
    env = max(r for t, r in nb if t < 2400); test = [r for t, r in nb if t >= 2400]
    ab = [rms(d) for _, d in Aa.groupby('burst') if len(d) >= 10]
    print(f'   {label:34s}: one-line rule {int((gbm > thr_r).sum())}/21 (thr {thr_r:.4f}) | upper-RMS envelope rule abnormal {sum(r > env for r in ab)}/{len(ab)}, normal 40-77 min {sum(r > env for r in test)}/{len(test)}')
