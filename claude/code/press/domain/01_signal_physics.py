"""신호 물리 점검: 표본 간격(앨리어싱), 진동 저주파 스펙트럼·상하부 위상, 진동 SD의 의미, 부하와 진동의 관계, 수집 구조.

입력은 cases/common.load_both(matched=True)로 읽은 정상·이상 원자료(저장 정밀도를 맞춘 것)다.
출력은 domain/outputs/01_signal_physics.json, _records.csv(기록별 표), _psd.csv(평균 PSD·위상)이고 _summary.md는 따로 썼다.
보고서 1.4·1.5·2.2절의 근거다. test 채점 이후의 사후 분석이며 백색잡음 모의는 seed 0.
실행: PYTHONIOENCODING=utf-8 python code/press/domain/01_signal_physics.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal, stats
from scipy.special import gammaln
from sklearn.isotonic import IsotonicRegression

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cases"))
from common import F0, SENSORS, lag1, load_both, sine_fit  # noqa: E402

OUT = HERE / "outputs"
FS_NOM = 10.0                     # 타임스탬프상 표본 주파수(Hz)
DT_NOM = 0.1                      # 공칭 표본 간격(s)
LINE = 60.0                       # 계통 공칭 주파수(Hz)
GRID_TOL = 0.2                    # 가정: 한국 계통 주파수 허용 범위 ±0.2 Hz (출처 확인 중)
F_GRID = np.round(np.arange(0.3, 0.9 + 1e-9, 0.0005), 4)      # 겉보기 주파수 탐색 격자(과제 지정)
F_WIDE = np.round(np.arange(0.005, 4.995 + 1e-9, 0.0025), 4)  # 이상 기록 보조 탐색(0 Hz·나이퀴스트 제외)
NFFT = 50                         # 10 Hz / 50 = 0.2 Hz 주파수 격자
BANDS = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.5), (3.5, 5.01)]
BAND_KEYS = [f"{lo:g}-{min(hi, 5):g}Hz" for lo, hi in BANDS]
SPLIT_A = (360, 480)              # 분할 A: 학습 <360, 검증 360~479, 시험 ≥480
RNG = np.random.default_rng(0)    # 백색잡음 기준 모의 전용
UP, LO, CUR = SENSORS


def r(x, k=4):
    """JSON용 반올림. numpy 스칼라는 float로, NaN은 None으로."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), k)


def qsum(s, k=4):
    """분포 요약: 개수, 최소·5·25·50·75·95%·최대."""
    s = pd.Series(s).dropna()
    return dict(n=int(s.size), min=r(s.min(), k), q05=r(s.quantile(.05), k), q25=r(s.quantile(.25), k),
                median=r(s.median(), k), q75=r(s.quantile(.75), k), q95=r(s.quantile(.95), k), max=r(s.max(), k))


# ---------------------------------------------------------------- 1. 앨리어싱
def grid_sine(x, freqs, dt=DT_NOM):
    """절편 + 사인 + 코사인 최소제곱을 주파수 격자 전체에 한 번에 푼다. (R², 진폭, 위상, 잔차 SD) 배열."""
    x = np.asarray(x, float)
    n = len(x)
    t = np.arange(n) * dt
    w = 2 * np.pi * freqs[:, None] * t[None, :]
    S, C = np.sin(w), np.cos(w)
    # 주파수마다 3×3 정규방정식 G·b = Xᵀx를 쌓아 한 번에 푼다. SSE = x·x − b·(Xᵀx)
    G = np.empty((len(freqs), 3, 3))
    G[:, 0, 0] = n
    G[:, 0, 1] = G[:, 1, 0] = S.sum(1)
    G[:, 0, 2] = G[:, 2, 0] = C.sum(1)
    G[:, 1, 1] = (S * S).sum(1)
    G[:, 1, 2] = G[:, 2, 1] = (S * C).sum(1)
    G[:, 2, 2] = (C * C).sum(1)
    rhs = np.stack([np.full(len(freqs), x.sum()), S @ x, C @ x], 1)
    b = np.linalg.solve(G, rhs[..., None])[..., 0]
    sse = x @ x - (b * rhs).sum(1)
    sst = ((x - x.mean()) ** 2).sum()
    return 1 - sse / sst, np.hypot(b[:, 1], b[:, 2]), np.arctan2(b[:, 2], b[:, 1]), np.sqrt(np.maximum(sse, 0) / n)


def harmonic_fit(x, f, orders=(1,)):
    """절편 + f의 orders차 사인·코사인 최소제곱. (잔차, 계수[절편, sin1, cos1, ...])."""
    t = np.arange(len(x)) * DT_NOM
    cols = [np.ones(len(x))]
    for h in orders:
        cols += [np.sin(2 * np.pi * h * f * t), np.cos(2 * np.pi * h * f * t)]
    X = np.column_stack(cols)
    b, *_ = np.linalg.lstsq(X, x, rcond=None)
    return x - X @ b, b


def sse_curve(x, grid):
    """격자 주파수별 사인 적합 잔차 제곱합. 기록별 곡선을 더해 최소를 찾으면 '주파수만 공통'인 합동 적합이 된다."""
    r2 = grid_sine(x, grid)[0]
    return (1 - r2) * ((x - x.mean()) ** 2).sum()


def alias_section(normal, abnormal, recs):
    """1. 전류 겉보기 주파수 f_a로 실제 표본 간격을 역산하고, 이상 기록에서도 같은 추정이 되는지 본다."""
    out = {}
    # 1-0 기록 안 타임스탬프 간격이 모두 100 ms인지, 기록 시작 ms를 4로 나눈 나머지 분포
    ts_diff = {}
    for name, d in (("normal", normal), ("abnormal", abnormal)):
        ts = pd.to_datetime(d.TimeStamp)
        us = ts.diff().dt.total_seconds().mul(1e6).round()
        inrec = us[d.rec.diff().eq(0)]
        vc = inrec.value_counts()
        start_ms = (ts.groupby(d.rec).first() - ts.iloc[0].normalize()).dt.total_seconds().mul(1000).round().astype(int)
        ts_diff[name] = dict(
            within_record_intervals=int(inrec.size),
            distinct_values_us={str(int(k)): int(v) for k, v in vc.items()},
            all_exactly_100ms=bool((inrec == 100000).all()),
            timestamp_resolution="1 ms (원본 문자열 소수 셋째 자리)",
            record_start_ms_mod4_share={str(k): r(v, 3) for k, v in (start_ms % 4).value_counts(normalize=True).sort_index().items()})
    out["timestamp_check"] = ts_diff

    # 1-1 30행 이상 기록마다 F_GRID에서 R²가 가장 큰 겉보기 주파수
    rows = []
    for name, d in (("normal", normal), ("abnormal", abnormal)):
        for k, g in d.groupby("rec"):
            if len(g) < 30:
                continue
            x = g[CUR].to_numpy()
            r2, amp, _, rs = grid_sine(x, F_GRID)
            j = int(np.argmax(r2))
            row = dict(set=name, rec=int(k), n=len(x), f_alias=F_GRID[j], f_r2=r2[j], f_amp=amp[j], f_resid_sd=rs[j],
                       f_at_grid_edge=bool(j in (0, len(F_GRID) - 1)))
            if name == "abnormal":
                r2w = grid_sine(x, F_WIDE)[0]
                jw = int(np.argmax(r2w))
                row.update(f_wide=F_WIDE[jw], f_wide_r2=r2w[jw])
            rows.append(row)
    F = pd.DataFrame(rows)
    fn = F[F.set == "normal"]
    fa = F[F.set == "abnormal"]
    cur = {k: g[CUR].to_numpy() for k, g in recs.items()}

    # 주파수 추정 표준오차의 CRLB(백색잡음 가정): var(ω̂) = 12σ²/(A²·N(N²−1)). 표본당 rad를 공칭 Hz로 바꾼다
    N = fn.n.to_numpy()
    crlb = np.sqrt(12 * fn.f_resid_sd.to_numpy() ** 2 / (fn.f_amp.to_numpy() ** 2 * N * (N ** 2 - 1))) / (2 * np.pi) * FS_NOM

    # 공통 주파수 합동 추정(0.59~0.61 Hz, 0.00002 Hz 격자). 1σ 범위는 SSE가 최소 + s² 이하인 격자점
    pool_grid = np.round(np.arange(0.590, 0.610 + 1e-12, 0.00002), 5)
    curves = {k: sse_curve(cur[k], pool_grid) for k in fn.rec}
    sse = sum(curves.values())
    dof = int((fn.n - 3).sum())                     # 기록마다 절편·사인·코사인 3모수
    jp = int(np.argmin(sse))
    s2 = sse[jp] / (dof - 1)
    inside = pool_grid[sse <= sse[jp] + s2]
    f_pool = float(pool_grid[jp])

    # 정상 기록을 시간순 5등분해 블록마다 합동 주파수를 구한다(77분간 주파수 표류)
    blocks = []
    edges = np.quantile(fn.rec, np.linspace(0, 1, 6))
    for b in range(5):
        ks = fn.rec[(fn.rec >= edges[b]) & ((fn.rec < edges[b + 1]) if b < 4 else (fn.rec <= edges[b + 1]))]
        sse_b = sum(curves[k] for k in ks)
        t0 = normal.loc[normal.rec == ks.iloc[0], "t"].iloc[0]
        t1 = normal.loc[normal.rec == ks.iloc[-1], "t"].iloc[0]
        blocks.append(dict(block=b, records=int(ks.size), t_start_min=r(t0 / 60, 1), t_end_min=r(t1 / 60, 1),
                           f_pooled=r(pool_grid[int(np.argmin(sse_b))], 5)))

    # f_a를 표본 간격으로 바꾼다. 60 Hz를 fs로 찍으면 f_a = |60 − 6·fs| 이므로 fs 후보는 10 Hz 위·아래 두 개다.
    # 거꾸로 fs가 정확히 10 Hz라면 계통이 60 ± f_a Hz여야 하므로 허용 범위(GRID_TOL)와 견준다
    def candidates(f_a):
        c = f_a / FS_NOM                                   # 표본당 cycle (타임스탬프 가정과 무관한 불변량)
        return dict(
            f_alias_nominal_hz=r(f_a, 5), cycles_per_sample=r(c, 6),
            exact_interval_ms=dict(fs_below_10=r((6 + c) / LINE * 1000, 4), fs_above_10=r((6 - c) / LINE * 1000, 4)),
            exact_fs_hz=dict(fs_below_10=r(LINE / (6 + c), 5), fs_above_10=r(LINE / (6 - c), 5)),
            formula_fs_eq_60_minus_fa_over_6_ms=dict(fs_below_10=r(6000 / (LINE - f_a), 4), fs_above_10=r(6000 / (LINE + f_a), 4)),
            required_line_hz_if_fs_exactly_10=dict(low=r(LINE - f_a, 4), high=r(LINE + f_a, 4)),
            deviation_vs_tolerance=r(f_a / GRID_TOL, 2))

    q25, q50, q75 = fn.f_alias.quantile([.25, .5, .75])

    # 홀수 고조파: 50행 정상 기록에서 기본파(f = q50)를 뺀 잔차의 평균 PSD
    P = []
    for k in fn.rec[fn.n == 50]:
        fr, p = signal.periodogram(harmonic_fit(cur[k], q50)[0], fs=FS_NOM, window="hann", nfft=NFFT, detrend=False)
        P.append(p)
    P = np.mean(P, 0)
    harm = {}
    # 배경 = 고조파가 접혀 들어오는 bin을 뺀 0.1 Hz 초과 bin의 중앙값
    base = np.median(P[(fr > 0.1) & ~np.isin(np.round(fr, 1), [0.4, 0.6, 0.8, 1.6, 1.8, 2.0, 2.8, 3.0, 3.2, 4.0, 4.2, 4.4])])
    for h in (2, 3, 4, 5, 6, 7, 9):
        fh = abs(((h * q50 / FS_NOM + 0.5) % 1) - 0.5) * FS_NOM   # h·f_a를 0~5 Hz 안으로 접은 위치
        i = int(np.argmin(np.abs(fr - fh)))
        harm[f"h{h}"] = dict(line_hz=h * 60, folded_hz=r(fh, 3), bin_hz=r(fr[i], 1), psd_over_background=r(P[i] / base, 1))

    # 표본 시각 흔들림 σ_t의 상한. 시각 오차 δ는 60 Hz 성분에 크기 2π·60·A·δ인 잡음을 더하므로
    # 고조파(1·3·5·7차) 제거 잔차 분산 = a + b·(A²/2), b = (2π·60·σ_t)². 기울기 + 2SE로 σ_t를 역산한다
    jit = []
    for k, f in zip(fn.rec, fn.f_alias):
        res, b = harmonic_fit(cur[k], float(f), (1, 3, 5, 7))
        jit.append((float(res.var()), float(np.hypot(b[1], b[2])) ** 2 / 2))
    jit = np.array(jit)
    lr = stats.linregress(jit[:, 1], jit[:, 0])
    b_ub = max(lr.slope + 2 * lr.stderr, 0.0)
    sigma_t_ms = np.sqrt(b_ub) / (2 * np.pi * LINE) * 1000

    out["normal_records_ge30"] = dict(
        n_records=int(len(fn)), f_alias=qsum(fn.f_alias, 5), f_alias_iqr=r(q75 - q25, 5), f_alias_sd=r(fn.f_alias.std(), 5),
        r2=qsum(fn.f_r2, 5), r2_share_ge_0_99=r((fn.f_r2 >= 0.99).mean(), 3), r2_share_ge_0_9=r((fn.f_r2 >= 0.9).mean(), 3),
        at_grid_edge=int(fn.f_at_grid_edge.sum()),
        crlb_se_median_hz=r(np.median(crlb), 5),
        lag1_autocorr_of_f_across_records=r(fn.f_alias.autocorr(1), 3),
        spearman_f_vs_time=r(stats.spearmanr(fn.rec, fn.f_alias).statistic, 3),
        spearman_f_vs_current_amp=r(stats.spearmanr(fn.f_amp, fn.f_alias).statistic, 3),
        pooled_common_f=dict(f=r(f_pool, 5), one_sigma_range=[r(inside.min(), 5), r(inside.max(), 5)],
                             note="기록마다 진폭·위상·절편 별도, 주파수만 공통. 잔차가 고조파로 백색이 아니라 범위는 과소평가일 수 있음"),
        pooled_f_by_time_block=blocks,
        pooled_f_block_range_hz=r(max(b["f_pooled"] for b in blocks) - min(b["f_pooled"] for b in blocks), 5),
        reference_common_F0_hz=r(F0 * FS_NOM, 4))
    out["interval_candidates_from_median"] = candidates(q50)
    out["interval_candidates_from_iqr"] = dict(q25=candidates(q25), q75=candidates(q75))
    out["interval_candidates_from_pooled"] = candidates(f_pool)
    out["odd_harmonics_in_current_residual"] = dict(
        records=int((fn.n == 50).sum()), background_psd=r(base, 3), harmonics=harm,
        note="h차 고조파(60h Hz)는 h·f_a 위치로 접힌다. 홀수(3·5·7차)만 크고 짝수는 배경 수준이면 교류 파형의 반파 대칭과 일치")
    out["sampling_jitter_upper_bound"] = dict(
        model="잔차분산(기본+3·5·7차 제거) = a + b·(A²/2), b=(2π·60·σ_t)²", slope=r(lr.slope, 7), slope_se=r(lr.stderr, 7),
        intercept_resid_var=r(lr.intercept, 2), sigma_t_upper_ms=r(sigma_t_ms, 4),
        resid_sd_fundamental_only_median=r(fn.f_resid_sd.median(), 2),
        note="b 상한(기울기+2SE)으로 계산. 진폭 비례 잔차를 전부 시각 흔들림으로 돌린 보수적 상한. "
             "기본파만 적합한 잔차(SD 약 5.8)는 대부분 3·5·7차 고조파이고, 고조파를 빼면 잔차 분산이 수 단위로 줄어든다")
    out["abnormal_records_ge30"] = dict(
        n_records=int(len(fa)), r2=qsum(fa.f_r2, 4), records_r2_ge_0_9=int((fa.f_r2 >= 0.9).sum()),
        wide_band_0_005_to_5hz_max_r2=r(fa.f_wide_r2.max(), 4),
        wide_band_records_r2_ge_0_9=int((fa.f_wide_r2 >= 0.9).sum()),
        per_record=[dict(rec=int(a.rec), n=int(a.n), f_0p3_0p9=r(a.f_alias, 4), r2=r(a.f_r2, 3),
                         f_wide=r(a.f_wide, 4), r2_wide=r(a.f_wide_r2, 3)) for a in fa.itertuples()],
        conclusion="R² ≥ 0.9인 이상 기록이 없어 겉보기 주파수(→표본 간격) 추정 불가")
    return out, F


# ---------------------------------------------------------------- 2·3. 진동 스펙트럼·위상
def psd_rec(x):
    """기록 하나의 Hann 창 periodogram(평균 제거, 0.2 Hz 격자)."""
    x = np.asarray(x, float)
    return signal.periodogram(x - x.mean(), fs=FS_NOM, window="hann", nfft=NFFT, detrend=False, scaling="density")


def csd_rec(x, y):
    """기록 하나의 교차 스펙트럼 conj(X)·Y. 구간을 나누지 않고 기록 전체를 한 구간으로 쓴다."""
    x = np.asarray(x, float) - np.mean(x)
    y = np.asarray(y, float) - np.mean(y)
    return signal.csd(x, y, fs=FS_NOM, window="hann", nperseg=len(x), nfft=NFFT, detrend=False, scaling="density")


def flatness(p):
    """스펙트럼 평탄도 = 기하평균 / 산술평균. 백색이면 1에 가깝다."""
    p = np.asarray(p, float)
    return float(np.exp(np.mean(np.log(p))) / np.mean(p))


def band_share(fr, p):
    """BANDS 대역별 에너지 비율(4자리 반올림)."""
    df = fr[1] - fr[0]
    tot = p.sum() * df
    return {k: r(p[(fr >= lo) & (fr < hi)].sum() * df / tot, 4) for k, (lo, hi) in zip(BAND_KEYS, BANDS)}


def side_stats(fr, P, lags):
    """센서 하나(상부 또는 하부)의 기록별 PSD 묶음 P로 평탄도·대역 비율·lag-1 중앙값을 낸다."""
    mid = (fr >= 0.4) & (fr <= 4.8)   # 평균 제거·Hann 창의 영향을 받는 0~0.2 Hz와 나이퀴스트 제외
    mp = P.mean(0)
    shares = [band_share(fr, p) for p in P]
    return dict(flatness_0p4_4p8=r(flatness(mp[mid]), 4),
                max_over_min_0p4_4p8=r(mp[mid].max() / mp[mid].min(), 3),
                band_share_of_mean_psd=band_share(fr, mp),
                band_share_per_record_median={k: r(np.median([s[k] for s in shares]), 4) for k in BAND_KEYS},
                lag1_median=r(np.median(lags), 3))


def spectrum_section(normal, abnormal):
    """2·3. 32행 이상 기록의 상·하부 진동 PSD와 교차 스펙트럼을 기록 평균해 모양·백색성·위상·coherence를 본다."""
    res, per_rec, mean_psd, lens, sxy_rec = {}, [], {}, {}, {}
    for name, d in (("normal", normal), ("abnormal", abnormal)):
        Pu, Pl, Sxy, corr, lag_u, lag_l = [], [], [], [], [], []
        lens[name] = []
        for k, g in d.groupby("rec"):
            if len(g) < 32:
                continue
            lens[name].append(len(g))
            u, l_ = g[UP].to_numpy(), g[LO].to_numpy()
            fr, pu = psd_rec(u)
            pl = psd_rec(l_)[1]
            Pu.append(pu)
            Pl.append(pl)
            Sxy.append(csd_rec(u, l_)[1])
            corr.append(np.corrcoef(u, l_)[0, 1])
            lag_u.append(lag1(g[UP]))
            lag_l.append(lag1(g[LO]))
            m = fr >= 0.2
            per_rec.append(dict(set=name, rec=int(k), n=len(g),
                                upper_peak_hz=r(fr[m][np.argmax(pu[m])], 1), lower_peak_hz=r(fr[m][np.argmax(pl[m])], 1),
                                upper_lag1=r(lag1(u), 3), lower_lag1=r(lag1(l_), 3), ul_corr=r(corr[-1], 3)))
        Pu, Pl, Sxy = np.array(Pu), np.array(Pl), np.array(Sxy)
        sxy_rec[name] = Sxy
        # coherence는 기록을 앙상블로 평균해야 뜻이 있다(한 구간짜리 coherence는 항상 1)
        mean_psd[name] = dict(upper=Pu.mean(0), lower=Pl.mean(0), sxy=Sxy.mean(0),
                              coh=np.abs(Sxy.mean(0)) ** 2 / (Pu.mean(0) * Pl.mean(0)))
        res[name] = dict(records_ge32=len(Pu), upper=side_stats(fr, Pu, lag_u), lower=side_stats(fr, Pl, lag_l),
                         ul_corr=qsum(corr, 3), ul_corr_negative_share=r(np.mean(np.array(corr) < 0), 3))
    mid = (fr >= 0.4) & (fr <= 4.8)

    # 백색잡음 기준: 같은 기록 길이의 N(0,1) 잡음으로 평탄도·대역 비율의 귀무 분포를 만든다(seed 0, 500회)
    def null(lengths, reps=500):
        fl, sh = [], []
        for _ in range(reps):
            P = np.mean([psd_rec(RNG.standard_normal(n))[1] for n in lengths], 0)
            fl.append(flatness(P[mid]))
            sh.append(list(band_share(fr, P).values()))
        sh = np.array(sh)
        return dict(flatness_q01=r(np.quantile(fl, .01), 4), flatness_q05=r(np.quantile(fl, .05), 4), flatness_median=r(np.median(fl), 4),
                    band_share_median={k: r(v, 4) for k, v in zip(BAND_KEYS, np.median(sh, 0))},
                    band_share_q025={k: r(v, 4) for k, v in zip(BAND_KEYS, np.quantile(sh, .025, 0))},
                    band_share_q975={k: r(v, 4) for k, v in zip(BAND_KEYS, np.quantile(sh, .975, 0))})
    res["white_noise_reference"] = {name: null(lens[name]) for name in lens}

    # 2배 계통 주파수(120 Hz) 자기 소음이 접히는 위치(2·f_a ≈ 1.2 Hz)에서 정상 진동 PSD가 튀어나오는지
    for s in ("upper", "lower"):
        p = mean_psd["normal"][s]
        nb = mid & (np.round(fr, 1) != 1.2)
        res["normal"][s]["psd_1p2hz_over_median_other"] = r(p[np.isclose(fr, 1.2)][0] / np.median(p[nb]), 3)

    pr = pd.DataFrame(per_rec)
    ab = pr[pr.set == "abnormal"]
    res["abnormal_dominant_freq"] = dict(
        upper=ab.upper_peak_hz.value_counts().sort_index().rename(lambda v: f"{v:g}").to_dict(),
        lower=ab.lower_peak_hz.value_counts().sort_index().rename(lambda v: f"{v:g}").to_dict(),
        upper_median_hz=r(ab.upper_peak_hz.median(), 2), lower_median_hz=r(ab.lower_peak_hz.median(), 2),
        upper_share_below_1hz=r((ab.upper_peak_hz < 1.0).mean(), 3), lower_share_below_1hz=r((ab.lower_peak_hz < 1.0).mean(), 3))
    nm = pr[pr.set == "normal"]
    res["normal_peak_freq_spread"] = dict(upper=qsum(nm.upper_peak_hz, 1), lower=qsum(nm.lower_peak_hz, 1),
                                          note="백색이면 기록별 최대 PSD 위치가 0.2~5 Hz에 고르게 퍼진다")

    # 3. 위상: 이상 우세 대역 = 상·하부 이상 평균 PSD를 각각 합 1로 정규화해 더한 값이 최댓값의 절반 이상인 0.2 Hz 이상 bin.
    # 교차 스펙트럼을 대역 안에서 더한 뒤 각도를 재고, 과제 지정 4대역도 같이 낸다
    abn = mean_psd["abnormal"]
    nrm = mean_psd["normal"]
    score = abn["upper"] / abn["upper"].sum() + abn["lower"] / abn["lower"].sum()
    score[fr < 0.2] = 0
    dom_mask = score >= 0.5 * score.max()
    dom_band = f"{fr[dom_mask].min():.1f}-{fr[dom_mask].max():.1f}Hz bins"
    cand = {k: (fr >= max(lo, 0.2)) & (fr < hi) for k, (lo, hi) in zip(BAND_KEYS, BANDS)}
    cand[dom_band] = dom_mask
    phase = {}
    for name, mp in (("normal", nrm), ("abnormal", abn)):
        rows = {}
        for bname, m in cand.items():
            sxy = mp["sxy"][m].sum()
            rows[bname] = dict(phase_deg_lower_minus_upper=r(np.degrees(np.angle(sxy)), 1),
                               coherence_mean=r(mp["coh"][m].mean(), 3),
                               coherence_band=r(np.abs(sxy) ** 2 / (mp["upper"][m].sum() * mp["lower"][m].sum()), 3))
        phase[name] = rows
    # 이상 기록별 우세 대역 위상의 원형 통계. 합성 길이 R̄ = |평균 e^{iθ}|, 1이면 모든 기록이 같은 위상
    per_phase = np.array([np.angle(s[dom_mask].sum()) for s in sxy_rec["abnormal"]])
    Rbar = np.abs(np.exp(1j * per_phase).mean())
    phase["abnormal_dominant_band"] = dom_band
    phase["abnormal_per_record_phase_deg"] = [r(np.degrees(v), 1) for v in per_phase]
    phase["abnormal_per_record_circular_mean_deg"] = r(np.degrees(np.angle(np.exp(1j * per_phase).mean())), 1)
    phase["abnormal_per_record_resultant_length"] = r(Rbar, 3)
    phase["abnormal_per_record_share_within_45deg_of_180"] = r(np.mean(np.abs(np.abs(np.degrees(per_phase)) - 180) <= 45), 3)
    phase["note"] = "교차 스펙트럼 = conj(상부)·하부 → 위상은 '하부 − 상부'. coherence는 기록을 앙상블로 평균(한 기록 안 단일 구간 coherence는 항상 1이라 무의미)"
    res["phase"] = phase

    psd_tab = pd.DataFrame(dict(freq_hz=np.round(fr, 2),
                                normal_upper=nrm["upper"], normal_lower=nrm["lower"],
                                abnormal_upper=abn["upper"], abnormal_lower=abn["lower"],
                                normal_coh=nrm["coh"], abnormal_coh=abn["coh"],
                                normal_phase_deg=np.degrees(np.angle(nrm["sxy"])),
                                abnormal_phase_deg=np.degrees(np.angle(abn["sxy"]))))
    return res, pr, psd_tab


# ---------------------------------------------------------------- 2b. 정상 진동의 협대역 성분(톤)
def tone_section(recs, cases, F, f_pool, reps=200):
    """2b. 정상 진동의 돌출 톤(하부 ≈1.8 Hz, 상부 ≈3.6 Hz)이 전류 고조파(3·f_a, 6·f_a)에 묶였는지, 부하에 따라 어떻게 변하는지 본다."""
    fn = F[F.set == "normal"][["rec", "f_alias"]]
    c = cases[cases.set == "normal"].merge(fn, on="rec")          # 30행 이상 정상 기록
    groups = {"high_load(cur_amp>180)": c.cur_amp > 180, "low_load(cur_amp<130)": c.cur_amp < 130, "all": c.cur_amp > 0}
    rng = np.random.default_rng(0)

    def sse_curves(series, grid):
        return np.array([sse_curve(x, grid) for x in series])

    # 합동 주파수(곡선 합의 최소)와 기록 단위 부트스트랩 95% 구간(seed 0)
    def pooled_ci(curves, grid):
        f_hat = grid[np.argmin(curves.sum(0))]
        bs = [grid[np.argmin(curves[rng.integers(0, len(curves), len(curves))].sum(0))] for _ in range(reps)]
        return r(f_hat, 4), [r(np.quantile(bs, .025), 4), r(np.quantile(bs, .975), 4)]

    out = {}
    # 전류에는 짝수 고조파가 없어(6차 PSD/배경 ≈ 1) 상부 톤은 전류와 직접 비교할 수 없다 → 6·f_a와만 비교
    specs = (("lower_tone_vs_current_h3", LO, 3, np.round(np.arange(1.75, 1.85 + 1e-9, 0.0001), 4), True),
             ("upper_tone_vs_6fa", UP, 6, np.round(np.arange(3.55, 3.65 + 1e-9, 0.0001), 4), False))
    for name, col, h, grid, with_current in specs:
        res = dict(expected_if_locked_hz=r(h * f_pool, 4), compared_with_current_harmonic=with_current)
        # 기록별 톤 진폭: 넓힌 격자에서 R²가 가장 큰 주파수의 사인 진폭
        wide = np.round(np.arange(grid[0] - 0.25, grid[-1] + 0.25, 0.0005), 4)
        amp_tone, r2_tone = [], []
        for k in c.rec:
            r2, amp, *_ = grid_sine(recs[k][col].to_numpy(), wide)
            j = int(np.argmax(r2))
            amp_tone.append(amp[j])
            r2_tone.append(r2[j])
        c[f"{name}_amp"] = amp_tone
        c[f"{name}_r2"] = r2_tone
        res["spearman_tone_amp_vs_current_amp"] = r(stats.spearmanr(c.cur_amp, c[f"{name}_amp"]).statistic, 3)
        for gname, m in groups.items():
            ks = c.rec[m].to_numpy()
            fv, civ = pooled_ci(sse_curves([recs[k][col].to_numpy() for k in ks], grid), grid)
            res[gname] = dict(records=int(len(ks)), vib_tone_f=fv, vib_tone_ci95=civ,
                              diff_vib_minus_expected=r(fv - h * f_pool, 4),
                              tone_amp_median=r(np.median(c.loc[m, f"{name}_amp"]), 4), tone_r2_median=r(np.median(c.loc[m, f"{name}_r2"]), 3))
            if with_current:
                # 같은 기록의 전류에서 기본파(기록별 f_a)를 뺀 잔차로 h차 고조파 위치를 같은 방식으로 잰다
                cres = [harmonic_fit(recs[k][CUR].to_numpy(), float(f))[0] for k, f in zip(ks, c.f_alias[m])]
                fc, cic = pooled_ci(sse_curves(cres, grid), grid)
                res[gname].update(current_harmonic_f=fc, current_harmonic_ci95=cic, diff_vib_minus_current=r(fv - fc, 4))
        hi, lo_ = res["high_load(cur_amp>180)"], res["low_load(cur_amp<130)"]
        res["tone_amp_high_over_low"] = r(hi["tone_amp_median"] / lo_["tone_amp_median"], 2)
        out[name] = res
    out["note"] = ("겉보기 주파수(공칭 Hz). 전류 3차 고조파(180 Hz)는 3·f_a=1.80, 6차(360 Hz)는 3.60에 접힌다. "
                   "진동 톤이 전류 고조파와 같은 주파수면 전기적으로 묶인 성분(또는 크로스토크), 다르면 별개 원천. "
                   "물리 주파수는 접힘 때문에 하나로 정할 수 없다(f·Δ mod 1 이 같은 모든 주파수가 후보)")
    return out


# ---------------------------------------------------------------- 4. 진동 SD의 의미
def sd_section(normal, abnormal, recs, cases):
    """4. 진동 SD가 무엇을 재는지 점검한다. 안티앨리어싱 없는 10 Hz 점 표본이면 표본 분산 ≈ 원 진동 전체 분산(RMS²)이다."""
    out = {}
    cn = cases[cases.set == "normal"]
    ca = cases[cases.set == "abnormal"]
    # 4-1 정상 SD 분포 (20행 이상)
    for s, col in (("upper", "sd_upper"), ("lower", "sd_lower")):
        v = cn.loc[cn.n >= 20, col]
        out[f"normal_{s}_sd_ge20"] = dict(**qsum(v, 4), cv_across_records=r(v.std() / v.mean(), 3))
    # 4-2 길이 구간별 SD 중앙값. 백색이면 길이와 무관하고, 저주파 성분이 크면 짧은 기록일수록 작다
    bins = [(2, 9), (10, 19), (20, 29), (30, 39), (40, 49), (50, 50)]
    lenmap = {}
    for lo_, hi_ in bins:
        m = cn.n.between(lo_, hi_)
        lenmap[f"{lo_}-{hi_}"] = dict(records=int(m.sum()), upper_median=r(cn.loc[m, "sd_upper"].median(), 4),
                                      lower_median=r(cn.loc[m, "sd_lower"].median(), 4))
    out["normal_sd_by_length"] = lenmap
    out["normal_spearman_length_vs_sd"] = dict(
        upper=r(stats.spearmanr(cn.n, cn.sd_upper).statistic, 3), lower=r(stats.spearmanr(cn.n, cn.sd_lower).statistic, 3),
        note="고부하(전류 진폭 큼) 기록이 길이와 얽혀 있을 수 있어 부하 효과가 섞인다")
    # 4-3 50행 기록의 앞 k행 SD / 50행 SD. iid 정규면 c4(k)/c4(50) 근처다(c4 = 표본 SD의 편향 계수)
    def c4(n):
        return np.sqrt(2 / (n - 1)) * np.exp(gammaln(n / 2) - gammaln((n - 1) / 2))
    pref = {}
    full = [k for k, g in recs.items() if len(g) == 50]
    for s, col in (("upper", UP), ("lower", LO)):
        rows = {}
        for k_ in (5, 10, 20, 30, 40):
            ratio = [recs[k][col].to_numpy()[:k_].std(ddof=1) / recs[k][col].std(ddof=1) for k in full]
            rows[f"first{k_}"] = dict(median_ratio=r(np.median(ratio), 3), iid_expected=r(c4(k_) / c4(50), 3))
        pref[s] = rows
    out["normal_prefix_sd_ratio_50row_records"] = dict(records=len(full), **pref)
    # 4-4 반분 일치도: log(앞 25행 SD / 뒤 25행 SD)의 SD를 iid 정규 이론값과 견준다.
    # 반쪽마다 var(log s) ≈ 1/(2·24)라 차의 SD는 sqrt(2/(2·24)), 첨도 κ를 넣으면 var(log s) ≈ (κ − 1)/(4n)
    half = {}
    for s, col in (("upper", UP), ("lower", LO)):
        lr_, ku = [], []
        for k in full:
            x = recs[k][col].to_numpy()
            lr_.append(np.log(x[:25].std(ddof=1) / x[25:].std(ddof=1)))
            ku.append(stats.kurtosis(x, fisher=False))
        kmed = float(np.median(ku))
        th_gauss = np.sqrt(2 / (2 * 24))
        th_kurt = np.sqrt(2 * (kmed - 1 + 2 / 24) / (4 * 25))
        half[s] = dict(sd_of_log_half_ratio=r(np.std(lr_, ddof=1), 3), iid_gauss_theory=r(th_gauss, 3),
                       iid_theory_with_observed_kurtosis=r(th_kurt, 3), kurtosis_median=r(kmed, 2))
    out["normal_half_split_consistency"] = half
    # 4-5 기록 안에서 표준화한 뒤 모은 표본의 첨도. 가우스는 3, 단일 사인은 1.5
    kurt = {}
    for name, d in (("normal", normal), ("abnormal", abnormal)):
        z = d.groupby("rec").filter(lambda g: len(g) >= 20).groupby("rec")[[UP, LO]].transform(lambda v: (v - v.mean()) / v.std())
        kurt[name] = dict(upper=r(stats.kurtosis(z[UP], fisher=False), 2), lower=r(stats.kurtosis(z[LO], fisher=False), 2))
    out["pooled_within_record_kurtosis"] = kurt
    # 4-6 정상 대비 이상 SD 배수(기록 중앙값 기준 20행 이상·2행 이상, 그리고 행 전체 SD)
    mult = {}
    for s, col, sens in (("upper", "sd_upper", UP), ("lower", "sd_lower", LO)):
        mult[s] = dict(
            records_ge20=r(ca.loc[ca.n >= 20, col].median() / cn.loc[cn.n >= 20, col].median(), 2),
            records_ge2=r(ca.loc[ca.n >= 2, col].median() / cn.loc[cn.n >= 2, col].median(), 2),
            pooled_rows=r(abnormal[sens].std() / normal[sens].std(), 2),
            abnormal_records_ge20_below_normal_median=int((ca.loc[ca.n >= 20, col] < cn.loc[cn.n >= 20, col].median()).sum()),
            abnormal_records_ge20=int((ca.n >= 20).sum()))
    out["abnormal_over_normal_sd_multiple"] = mult
    return out


# ---------------------------------------------------------------- 5. 부하와 진동
def load_section(cases):
    """5. 부하 정규화: 정상 학습 기록(분할 A)에서 log 진동 SD ~ log 전류(진폭 또는 RMS)를 OLS·단조 회귀로 맞추고,
    모든 기록의 잔차를 학습 잔차 SD 단위 z로 나타낸다. log-log라 기울기는 '진동 ∝ 부하^b'의 지수다."""
    c = cases[cases.n >= 20].copy()
    c["split"] = np.where(c.set == "abnormal", "abnormal",
                          np.where(c.rec < SPLIT_A[0], "train", np.where(c.rec < SPLIT_A[1], "valid", "test")))
    out = dict(min_rows=20, records={k: int(v) for k, v in c.split.value_counts().items()})
    cn = c[c.set == "normal"]
    out["normal_spearman"] = {
        f"{y}_vs_{x}": r(stats.spearmanr(cn[x], cn[y]).statistic, 3)
        for y in ("sd_lower", "sd_upper") for x in ("cur_amp", "cur_rms")}
    out["normal_spearman_train_only"] = {
        f"{y}_vs_cur_amp": r(stats.spearmanr(cn.loc[cn.rec < SPLIT_A[0], "cur_amp"], cn.loc[cn.rec < SPLIT_A[0], y]).statistic, 3)
        for y in ("sd_lower", "sd_upper")}
    tr = c[c.split == "train"]
    models = {}
    for x in ("cur_amp", "cur_rms"):
        for y in ("sd_lower", "sd_upper"):
            lx, ly = np.log(tr[x]), np.log(tr[y])
            fit = stats.linregress(lx, ly)
            res_tr = ly - (fit.intercept + fit.slope * lx)
            s_ols = res_tr.std(ddof=2)                     # 모수 2개(절편·기울기)를 뺀 자유도
            iso = IsotonicRegression(increasing=True, out_of_bounds="clip").fit(lx, ly)
            s_iso = (ly - iso.predict(lx)).std(ddof=1)
            key = f"{y}~{x}"
            zc_ols = f"z_ols_{y}_{x}"
            zc_iso = f"z_iso_{y}_{x}"
            c[zc_ols] = (np.log(c[y]) - (fit.intercept + fit.slope * np.log(c[x]))) / s_ols
            c[zc_iso] = (np.log(c[y]) - iso.predict(np.log(c[x]))) / s_iso
            summ = {}
            for sp in ("train", "valid", "test", "abnormal"):
                m = c.split == sp
                summ[sp] = dict(
                    ols=dict(median=r(c.loc[m, zc_ols].median(), 2), q05=r(c.loc[m, zc_ols].quantile(.05), 2),
                             q95=r(c.loc[m, zc_ols].quantile(.95), 2), max=r(c.loc[m, zc_ols].max(), 2),
                             share_gt3=r((c.loc[m, zc_ols] > 3).mean(), 3)),
                    iso=dict(median=r(c.loc[m, zc_iso].median(), 2), max=r(c.loc[m, zc_iso].max(), 2),
                             share_gt3=r((c.loc[m, zc_iso] > 3).mean(), 3)))
            x_rng = (tr[x].min(), tr[x].max())
            ab = c[c.split == "abnormal"]
            models[key] = dict(
                ols_slope_loglog=r(fit.slope, 3), ols_slope_se=r(fit.stderr, 3), ols_r2_train=r(fit.rvalue ** 2, 3),
                resid_sd_log_train_ols=r(s_ols, 4), resid_sd_log_train_iso=r(s_iso, 4),
                train_x_range=[r(x_rng[0], 1), r(x_rng[1], 1)],
                abnormal_x_outside_train_range=int(((ab[x] < x_rng[0]) | (ab[x] > x_rng[1])).sum()),
                z=summ,
                abnormal_unexplained_factor_median=r(np.exp(c.loc[c.split == "abnormal", zc_ols].median() * s_ols), 2))
    out["models"] = models
    nz = c[c.set == "normal"]
    out["normal_z_time_trend"] = {
        k: dict(spearman_vs_record_index=r(stats.spearmanr(nz.rec, nz[k]).statistic, 3),
                median_by_split={sp: r(nz.loc[nz.split == sp, k].median(), 2) for sp in ("train", "valid", "test")})
        for k in ("z_ols_sd_lower_cur_amp", "z_ols_sd_upper_cur_amp")}
    out["current_level"] = dict(
        normal_cur_rms=qsum(nz.cur_rms, 1), abnormal_cur_rms=qsum(c.loc[c.split == "abnormal", "cur_rms"], 1),
        abnormal_cur_sine_r2=qsum(c.loc[c.split == "abnormal", "cur_sine_r2"], 3),
        abnormal_abs_mean_over_rms=qsum((c.loc[c.split == "abnormal", "cur_mean"].abs() / c.loc[c.split == "abnormal", "cur_rms"]), 2))
    out["note"] = ("z = (log 진동 SD − 정상 학습 회귀 예측) / 정상 학습 잔차 SD. "
                   "unexplained_factor = exp(z 중앙값 × 잔차 SD) = 부하로 설명되지 않는 진동 SD 배수. "
                   "이상 기록은 전류 사인 적합이 깨져(20행 이상 13기록, 고정 F0 사인 R² 중앙값 0.07·최대 0.62) "
                   "cur_amp가 부하를 뜻하지 않으므로 cur_rms 모델을 주로 본다")
    return out, c


# ---------------------------------------------------------------- 6. 수집 구조
def acq_section(normal, abnormal):
    """6. 수집 구조: 기록 길이·공백·시작 간격 분포, 자기상관, 기록 시작·끝 시각의 주기 고정(위상 잠금) 여부."""
    out = {}
    for name, d in (("normal", normal), ("abnormal", abnormal)):
        g = d.groupby("rec")
        st = g.t.first().to_numpy()
        L = g.size().to_numpy()
        last = g.t.last().to_numpy()
        end = last + DT_NOM
        gap = st[1:] - last[:-1]
        s2s = np.diff(st)
        span = d.t.iloc[-1] - d.t.iloc[0] + DT_NOM
        Ls = pd.Series(L.astype(float))
        s2 = pd.Series(s2s)
        # 후보 주기 P(4~12 s)마다 시각을 위상 2π·t/P로 바꿔 합성 길이 R을 잰다. 시각이 P 격자에 묶여 있으면 R이 1에 가깝다
        P = np.arange(4.0, 12.0, 0.0005)
        ray = lambda x: np.abs(np.exp(2j * np.pi * x[None, :] / P[:, None]).mean(1))
        rs, re = ray(st), ray(end)
        js, je = int(np.argmax(rs)), int(np.argmax(re))
        o = dict(
            records=int(L.size), length=qsum(L, 1), length_share_50=r((L == 50).mean(), 3),
            length_share_lt10=r((L < 10).mean(), 3), length_max=int(L.max()),
            gap_last_to_next_first_s=qsum(gap, 3), gap_iqr_s=r(np.quantile(gap, .75) - np.quantile(gap, .25), 3),
            gap_zero_count=int((np.abs(gap) < 1e-6).sum()),
            start_to_start_s=qsum(s2s, 3), start_to_start_iqr_s=r(np.quantile(s2s, .75) - np.quantile(s2s, .25), 3),
            measured_share=r(len(d) * DT_NOM / span, 4), span_s=r(span, 1),
            spearman_length_vs_following_gap=r(stats.spearmanr(L[:-1], gap).statistic, 3),
            phase_lock_scan_4_to_12s=dict(
                start_best_period_s=r(P[js], 4), start_R=r(rs[js], 3),
                end_best_period_s=r(P[je], 4), end_R=r(re[je], 3), null_R_approx=r(1 / np.sqrt(L.size), 3),
                note="R = |평균 exp(2πi·시각/P)|. 1이면 모든 시각이 같은 위상, 무작위면 약 1/√n"))
        if name == "normal":
            o["length_acf_lag1_10"] = [r(Ls.autocorr(k), 3) for k in range(1, 11)]
            o["start_to_start_acf_lag1_10"] = [r(s2.autocorr(k), 3) for k in range(1, 11)]
            f, p = signal.periodogram(Ls - Ls.mean(), window="hann")
            kk = int(np.argmax(p[1:]) + 1)
            o["length_sequence_dominant_period_records"] = r(1 / f[kk], 2)
            o["length_sequence_dominant_period_s"] = r(1 / f[kk] * s2s.mean(), 1)
            Ps, Pe = P[js], P[je]
            # 시작·끝이 서로 다른 주기에 묶이면 두 주기의 맥놀이 1/|1/Pe − 1/Ps| 마다 기록 길이가 한 바퀴 돈다
            o["beat_period_from_start_end_locks_s"] = r(1 / abs(1 / Pe - 1 / Ps), 1)
            o["start_R_truncated_vs_full"] = [r(np.abs(np.exp(2j * np.pi * st[L < 50] / Ps).mean()), 3),
                                              r(np.abs(np.exp(2j * np.pi * st[L == 50] / Ps).mean()), 3)]
            o["end_R_truncated_vs_full"] = [r(np.abs(np.exp(2j * np.pi * end[L < 50] / Pe).mean()), 3),
                                            r(np.abs(np.exp(2j * np.pi * end[L == 50] / Pe).mean()), 3)]
            o["first_40_lengths"] = [int(v) for v in L[:40]]
        out[name] = o
    out["interpretation_estimate"] = (
        "추정: 기록 길이 상한 50행(공칭 5 s)과 '시작 시각 + n×100 ms' 형태의 기록 안 타임스탬프는 PLC가 표본을 "
        "최대 50개 버퍼로 모아 블록 단위로 올리고 수집기가 블록 시작 시각만 실제로 찍는 구조와 맞는다. "
        "시작은 약 8 s 격자, 끝은 약 6.8 s 격자에 묶여 두 주기의 맥놀이로 길이가 톱니 모양(50→13)으로 줄었다 "
        "다시 50으로 돌아온다. 원인 주기의 정체(통신 폴링, 버퍼 플러시, 프레스 행정 등)는 데이터로 확인 불가.")
    return out


# ---------------------------------------------------------------- 기록 표
def record_table(normal, abnormal):
    """2행 이상 기록마다 진동 SD와 전류 부하 지표(고정 F0 사인 진폭·RMS·평균·R²)."""
    rows = []
    for name, d in (("normal", normal), ("abnormal", abnormal)):
        for k, g in d.groupby("rec"):
            if len(g) < 2:
                continue
            amp, _, _, r2 = sine_fit(g[CUR].to_numpy())
            rows.append(dict(set=name, rec=int(k), n=len(g), t0=g.t.iloc[0],
                             sd_upper=g[UP].std(), sd_lower=g[LO].std(),
                             cur_amp=amp, cur_rms=g[CUR].std(), cur_mean=g[CUR].mean(), cur_sine_r2=r2))
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    normal, abnormal = load_both(matched=True)
    recs = dict(list(normal.groupby("rec")))         # 정상 기록 번호 → 그 기록의 행

    result = dict(meta=dict(
        input="cases/common.load_both(matched=True)", normal_rows=len(normal), abnormal_rows=len(abnormal),
        normal_records=len(recs), abnormal_records=abnormal.rec.nunique(),
        assumption_grid_tolerance_hz=f"60 ± {GRID_TOL} (가정, 출처 확인 중)",
        f_grid="0.3~0.9 Hz, 0.0005 Hz (공칭 시간축 t = n × 0.1 s)", seed=0))

    alias, F = alias_section(normal, abnormal, recs)
    result["1_alias_sampling_interval"] = alias
    spec, pr, psd_tab = spectrum_section(normal, abnormal)
    result["2_3_vibration_spectrum_and_phase"] = spec
    cases = record_table(normal, abnormal)
    result["2b_normal_vibration_tones"] = tone_section(
        recs, cases, F, alias["normal_records_ge30"]["pooled_common_f"]["f"])
    result["4_vibration_sd_meaning"] = sd_section(normal, abnormal, recs, cases)
    load_res, lc = load_section(cases)
    result["5_load_vs_vibration"] = load_res
    result["6_acquisition_structure"] = acq_section(normal, abnormal)

    # 기록별 표: 부하 지표 + 겉보기 주파수 + 스펙트럼 + 부하 정규화 z
    tab = cases.merge(F.drop(columns=["n"]), on=["set", "rec"], how="left") \
               .merge(pr.drop(columns=["n"]), on=["set", "rec"], how="left") \
               .merge(lc[["set", "rec", "split"] + [c for c in lc.columns if c.startswith("z_")]], on=["set", "rec"], how="left")
    tab.to_csv(OUT / "01_signal_physics_records.csv", index=False, encoding="utf-8-sig")
    psd_tab.to_csv(OUT / "01_signal_physics_psd.csv", index=False, encoding="utf-8-sig")
    (OUT / "01_signal_physics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("저장:", OUT / "01_signal_physics.json")


if __name__ == "__main__":
    main()
