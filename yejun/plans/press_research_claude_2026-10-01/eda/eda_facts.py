"""프레스 과제 재설계용 데이터 진단 수치 (읽기 전용 원본 → eda_facts.json, 그림 3장).

실행: python eda_facts.py --root <데이터셋/프레스_유압펌프_예지보전 폴더>
의존성: numpy, pandas, scipy, scikit-learn, matplotlib
"""
import argparse, json, os
import numpy as np, pandas as pd
from scipy import stats
from sklearn.covariance import MinCovDet
from sklearn.ensemble import IsolationForest
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastsine import sinefit  # 0.02–5 Hz, 0.002 Hz 격자 사인+오프셋 최소제곱

COLS = ['AI0_Vibration', 'AI1_Vibration', 'AI2_Current']
GAP_S = 0.5            # 0.1 s 간격보다 크면 새 버스트


def load(root):
    out = []
    sub = os.path.join(root, 'data', '3_소성가공_예지보전')
    for name, lab in [('press_data_normal.csv', 0), ('outlier_data.csv', 1)]:
        df = pd.read_csv(os.path.join(sub, name))
        df.columns = ['idx'] + list(df.columns[1:])
        df['t'] = pd.to_datetime(df.TimeStamp)
        df['file'] = lab
        df['dt'] = df.t.diff().dt.total_seconds()
        df['burst'] = (df.dt > GAP_S).cumsum().fillna(0).astype(int)
        df['pos'] = df.groupby('burst').cumcount()
        df['ts'] = (df.t - df.t.iloc[0]).dt.total_seconds()
        out.append(df)
    return out


def burst_features(df, minlen=10):
    rows = []
    for b, d in df.groupby('burst'):
        if len(d) < minlen:
            continue
        t = d.pos.values * 0.1
        r = dict(burst=int(b), n=len(d), ts=float(d.ts.iloc[0]), file=int(d.file.iloc[0]))
        for c, k in zip(COLS, ['v0', 'v1', 'i']):
            x = d[c].values
            for kk, vv in sinefit(t, x).items():
                r[f'{k}_{kk}'] = vv
            r[f'{k}_rms'] = float(np.sqrt(np.mean(x ** 2)))
            r[f'{k}_maxabs'] = float(np.abs(x).max())
            r[f'{k}_kurt'] = float(stats.kurtosis(x))
            r[f'{k}_ac1'] = float(np.corrcoef(x[:-1], x[1:])[0, 1])
        r['c01'] = float(np.corrcoef(d.AI0_Vibration, d.AI1_Vibration)[0, 1])
        rows.append(r)
    return pd.DataFrame(rows)


def q(a, ps=(0, 5, 50, 95, 100)):
    return {f'p{p}': round(float(np.nanpercentile(a, p)), 4) for p in ps}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--out', default='.')
    a = ap.parse_args()
    N, A = load(a.root)
    facts = {}
    for nm, df in [('normal', N), ('abnormal', A)]:
        lens = df.groupby('burst').size()
        starts = df.groupby('burst').t.first().diff().dt.total_seconds().dropna()
        within = df[df.pos > 0].dt
        facts[nm] = dict(
            rows=len(df), first=df.TimeStamp.iloc[0], last=df.TimeStamp.iloc[-1],
            bursts=int(lens.size), full50=int((lens == 50).sum()), burst_len=q(lens),
            burst_start_interval_s=q(starts), within_burst_dt_ms=sorted(set((within * 1000).round().astype(int))),
            nonpositive_dt=int((df.dt <= 0).sum()),
            duplicate_rows=int(df.duplicated(subset=['TimeStamp'] + COLS).sum()),
            maxabs={c: round(float(df[c].abs().max()), 4) for c in COLS})
    F = pd.concat([burst_features(N), burst_features(A)], ignore_index=True)
    F.to_csv(os.path.join(a.out, 'burst_features.csv'), index=False)
    Nf, Af = F[F.file == 0].copy(), F[F.file == 1].copy()
    facts['burst_level'] = {k: {'normal': q(Nf[k]), 'abnormal': q(Af[k])}
                            for k in ['i_f', 'i_amp', 'i_r2', 'i_rres', 'v0_rms', 'v1_rms', 'v0_ac1', 'v1_ac1', 'c01']}
    # 부하(전류 진폭)–하부진동 관계
    cf = np.polyfit(Nf.i_amp, Nf.v1_rms, 2)
    pred = np.polyval(cf, Nf.i_amp)
    facts['load_vibration'] = dict(spearman_iamp_v1rms=round(float(stats.spearmanr(Nf.i_amp, Nf.v1_rms)[0]), 3),
                                   spearman_iamp_v0rms=round(float(stats.spearmanr(Nf.i_amp, Nf.v0_rms)[0]), 3),
                                   quad_r2_v1=round(float(1 - np.sum((Nf.v1_rms - pred) ** 2) / np.sum((Nf.v1_rms - Nf.v1_rms.mean()) ** 2)), 3))
    # 운전 상태 타임라인 (10분 창, 버스트 진폭 기준: >180 가압, <130 대기)
    Nf['win10'] = (Nf.ts // 600).astype(int)
    facts['state_timeline'] = {int(w): dict(n=int(len(d)), loaded=round(float((d.i_amp > 180).mean()), 2),
                                            idle=round(float((d.i_amp < 130).mean()), 2),
                                            c01_median=round(float(d.c01.median()), 2))
                               for w, d in Nf.groupby('win10')}
    # 한 줄 규칙: 정상 최대 |AI0| 초과
    thr0 = N.AI0_Vibration.abs().max()
    hit = A[A.AI0_Vibration.abs() > thr0]
    facts['one_line_rule_AI0'] = dict(threshold=round(float(thr0), 4), rows=f'{len(hit)}/{len(A)}',
                                      bursts=f'{hit.burst.nunique()}/{A.burst.nunique()}')
    facts['sine_fit_separation'] = dict(normal_min_r2=round(float(Nf.i_r2.min()), 4), abnormal_max_r2=round(float(Af.i_r2.max()), 4),
                                        normal_max_rres=round(float(Nf.i_rres.max()), 2), abnormal_min_rres=round(float(Af.i_rres.min()), 2))
    # 운전 상태 변화 오경보 실험: 0–50분 학습 → 구간별 경보율 (임계값=학습 99%)
    feat = ['i_amp', 'i_rres', 'v0_rms', 'v1_rms', 'v0_ac1', 'v1_ac1', 'c01', 'v0_kurt', 'v1_kurt', 'v0_maxabs', 'v1_maxabs']
    tr = Nf[Nf.ts < 3000]
    mu, sd = tr[feat].mean(), tr[feat].std()
    Z = lambda d: (d[feat] - mu) / sd
    mcd = MinCovDet(random_state=0).fit(Z(tr)); thr_m = np.quantile(mcd.mahalanobis(Z(tr)), 0.99)
    iso = IsolationForest(n_estimators=300, random_state=0).fit(Z(tr)); thr_i = np.quantile(-iso.score_samples(Z(tr)), 0.99)
    cfv = np.polyfit(tr.i_amp, tr.v1_rms, 2)
    res_sd = np.std(tr.v1_rms - np.polyval(cfv, tr.i_amp))
    hi_rres, hi_v0 = np.quantile(tr.i_rres, 0.99), np.quantile(tr.v0_rms, 0.99)
    segs = {'50-60min': Nf[(Nf.ts >= 3000) & (Nf.ts < 3600)], '60-72min_standby': Nf[(Nf.ts >= 3600) & (Nf.ts < 4320)],
            '72-77min': Nf[Nf.ts >= 4320], 'abnormal': Af}
    out = {}
    for k, d in segs.items():
        phys = ((d.v1_rms - np.polyval(cfv, d.i_amp.clip(upper=280))).abs() > 4 * res_sd) | (d.i_rres > hi_rres) | (d.v0_rms > hi_v0)
        out[k] = dict(n=int(len(d)), mcd=round(float(np.mean(mcd.mahalanobis(Z(d)) > thr_m)), 3),
                      iforest=round(float(np.mean(-iso.score_samples(Z(d)) > thr_i)), 3), physics_rule=round(float(phys.mean()), 3))
    facts['state_change_false_alarm_probe'] = out
    with open(os.path.join(a.out, 'eda_facts.json'), 'w') as f:
        json.dump(facts, f, ensure_ascii=False, indent=1)
    print(json.dumps(facts, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
