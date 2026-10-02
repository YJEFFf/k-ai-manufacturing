"""통합안 점검 ①: 상태별(Mondrian) 보정이 이 데이터에서 가능한가, 노출 시간을 어떻게 정의할까.

- 정상 버스트(10행 이상)를 부하 구간·10분 블록·장시간 대기로 센다.
- 블록 하나를 시험으로 뺄 때 보정 집합의 상태별 n과 해상도 1/(n+1)을 α_op/2 = 0.5 %와 비교한다.
- 시간순 분할(학습 0–40, 보정 40–60, 시험 60–77분)의 보정 집합에 장시간 대기가 있는지 본다.
- 경보율 분모(노출 시간) 후보 세 가지를 계산한다.

실행: python check_calibration_units.py --root <데이터셋/프레스_유압펌프_예지보전>   (원본 CSV 읽기 전용, 수 초)
"""
import argparse, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'press_research_claude_2026-10-01', 'eda'))
from eda_facts import load  # 버스트 분리 규칙(간격 > 0.5초)과 ts(초)를 v2 진단과 같게 쓴다

ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args()
N, A = load(a.root)

def a60(x):
    k = np.arange(len(x)); X = np.column_stack([np.ones(len(x)), np.cos(2*np.pi*0.06*k), np.sin(2*np.pi*0.06*k)])
    b = np.linalg.lstsq(X, x, rcond=None)[0]; return np.hypot(b[1], b[2])

rows = []
for b, d in N.groupby('burst'):
    rows.append(dict(burst=b, n=len(d), t0=d.ts.iloc[0], tend=d.ts.iloc[-1],
                     amp=a60(d.AI2_Current.values) if len(d) >= 10 else np.nan))
B = pd.DataFrame(rows)
F = B[B.n >= 10].copy()
F['block'] = (F.tend // 600).astype(int)
F['load_bin'] = pd.cut(F.amp, [0, 130, 180, 1e9], labels=['noload<130', 'mid130-180', 'press>180'])
print(f'bursts all={len(B)}  >=10 rows={len(F)}')
print('\n[1] >=10-row normal bursts by 10-min block x load bin')
print(pd.crosstab(F.block, F.load_bin, margins=True).to_string())

# 장시간 대기 후보: 무부하(<130) 연속 구간 길이 (마지막 행 실시각 기준)
F = F.sort_values('tend').reset_index(drop=True)
noload = (F.amp < 130).values
runs, start = [], None
for i, nl in enumerate(noload):
    if nl and start is None: start = i
    if (not nl or i == len(F) - 1) and start is not None:
        end = i if nl else i - 1
        runs.append((F.tend[start], F.tend[end], end - start + 1)); start = None
R = pd.DataFrame(runs, columns=['t_start', 't_end', 'n_bursts']); R['dur_s'] = R.t_end - R.t_start
print('\n[2] longest consecutive no-load runs (last-row time)')
print(R.sort_values('dur_s', ascending=False).head(6).assign(t_start_min=lambda r: (r.t_start/60).round(1), t_end_min=lambda r: (r.t_end/60).round(1))[['t_start_min','t_end_min','n_bursts','dur_s']].to_string(index=False))
for thr in (60, 120, 180):
    pre = R[(R.t_end < 3600) & (R.dur_s >= thr)]
    print(f'   no-load runs >= {thr:3d}s ending before 60 min: {len(pre)} runs, {int(pre.n_bursts.sum())} bursts')
idle = (F.tend >= 3600) & (F.tend < 4320)
print(f'   bursts in 60-72 min (long standby window): {int(idle.sum())}')

# [3] 블록 하나를 뺀 보정 집합: 상태별 n과 해상도
print('\n[3] leave-one-10-min-block-out calibration size and resolution 1/(n+1)')
out = []
for blk in sorted(F.block.unique()):
    cal = F[F.block != blk]
    rec = dict(test_block=blk, pooled_n=len(cal))
    for lb in ['noload<130', 'mid130-180', 'press>180']:
        rec[lb] = int((cal.load_bin == lb).sum())
    rec['standby_60_72_n'] = int(((cal.tend >= 3600) & (cal.tend < 4320)).sum())
    out.append(rec)
O = pd.DataFrame(out)
for c in ['pooled_n', 'noload<130', 'mid130-180', 'press>180', 'standby_60_72_n']:
    O[c + '_res%'] = (100 / (O[c] + 1)).round(2)
print(O.to_string(index=False))
print('   alpha_op/2 = 0.50 % ; bins whose resolution > 0.50 % cannot reach the stage-2 per-channel level')

# [4] 시간순 분할의 보정 집합(40–60분)에 장시간 대기가 있는가
cal = F[(F.tend >= 2400) & (F.tend < 3600)]
print(f'\n[4] time split calibration 40-60 min: n={len(cal)}, no-load={int((cal.amp<130).sum())}, standby(60-72)=0 by construction; '
      f'no-load runs >=180 s inside: {int(((R.t_start>=2400)&(R.t_end<3600)&(R.dur_s>=180)).sum())}')

# [5] 노출 시간(분모) 후보
tend = np.sort(B.tend.values)
gaps = np.diff(tend)
print('\n[5] exposure definitions for FA/h (normal file)')
print(f'   wall clock first->last burst (last-row time): {(tend[-1]-tend[0])/3600:.3f} h')
for cap in (12, 20, 30):
    print(f'   sum of inter-burst intervals <= {cap:2d} s: {gaps[gaps<=cap].sum()/3600:.3f} h  (gaps > {cap} s: {(gaps>cap).sum()}, max {gaps.max():.1f} s)')
print(f'   nominal rows x 0.1 s: {len(N)*0.1/3600:.3f} h ; bursts x median period: {len(B)*np.median(gaps)/3600:.3f} h')
g = N.groupby('burst').ts.agg(['first', 'last'])
print(f'   gap last-row -> next first-row: min {np.min(g["first"].values[1:]-g["last"].values[:-1]):.2f} s, max {np.max(g["first"].values[1:]-g["last"].values[:-1]):.2f} s')
