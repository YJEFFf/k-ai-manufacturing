"""이상일 전류 증거 표 — 이상일(07-17 오전) 전류의 사인파 붕괴를 여러 검사로 재고, 각 검사가 어느 가설과 맞고
어긋나는지를 양성 대조 모사로 확인된 범위에서만 표시한다. 가설 점수 합산은 하지 않는다.

목적: 정상일 전류는 60Hz 교류를 10Hz로 점샘플한 0.6Hz 앨리어스 사인파(R²≈0.996)인데 이상일은 사인에서 벗어난다.
  가설과 하위 메커니즘(괄호 = 모사, '없음' = 모사하지 않아 방향 판정 밖):
    H1 타이밍·클록        iid 샘플 시각 지터(jitter) / 클록 오프셋 = 상수 앨리어스 이동(없음)
    H2 구동 주파수        순간 주파수 랜덤워크(fm) / 선형 드리프트(M2로만 검사) / 주파수 계단(없음)
    H3 부하 진폭          느린 진폭 변화(am_slow) / 부하 계단(없음)
    H4 파형 왜곡·기어 부하 접힘  샘플마다 독립인 빠른 진폭 변동 = 기어 부하 변동의 접힘(am_fast) / 2·3·5차 고조파(harmonic)
    H5 계측 사슬 이상     위상과 무관한 가법 광대역 잡음(additive) / 양자화·포맷 변화(없음)
  탐지 모델(fused_acat) 설정은 건드리지 않는다. 이상 데이터는 평가·서술에만 쓰고, 문턱·격자·대조 어느 것도 이상 라벨을 보고 고르지 않는다.
방법:
  1) 구간 표: 이상 구간(길이≥10, 17개) + 정상 구간(길이≥10) 분포 요약. 반송파 = 0.55~0.65Hz 사인+상수 적합의 R²·진폭(car_r2, car_amp).
     car_amp는 구간별 가법 흰 산포(차분 σ)만 있는 같은 길이 백색잡음의 대역 최대 진폭과도 비교한다(소실 여부:
     q95 초과 구간 수를 우연 5%에 대한 이항검정으로 본다).
  2) 잔차 모형(길이≥30, 정상·이상 모두). 비선형 모수는 격자, 선형 모수는 최소제곱(직교 기저 투영):
     M0 사인+상수(0~5Hz, 0.005Hz) / M1F(명세판) M0 + 고정 1.2·1.8·3.0Hz(60.6Hz 2·3·5차 앨리어스) /
     M1(참고) M0 + fold(k·f) 자유 기본(클록 이동 가정) / M2 선형 chirp(f0 = M0 격자, 변화율 ±0.1Hz/s 0.005 간격 ∪ ±0.5Hz/s 0.02 간격,
     변화율 0 = M0 해) / M3 (a0+a1·t)·사인 / M5 M0+계단 1개(f = M0 격자) — M1F·M2·M3·M5는 모두 M0를 품는다.
     M4 지터 지문 rho4t = M5 적합 |잔차|와 |cos 위상|의 편순위상관(시간 추세 1·t·|t−중앙| 통제), M5 위상 폭 ≥360° 구간만.
     (M2 chirp은 선형 드리프트, fm 모사는 랜덤워크라 서로 다른 모형이다.)
  3) 대조(표시만, 방향 판정에는 안 씀): (a) 같은 길이 백색잡음 (b) 정상 구간 앞 L관측 (c) 대리 = M0 적합 + 위상 무작위 M0 잔차 200개
     (d) M1F = 비고조파 고정 3주파수 빗 50개(0.3~4.7Hz, 0.6·1.2·1.8·3.0Hz에서 0.1Hz 이상), M1 = 비정수 배수 빗 50개.
  4) 양성 대조 모사: 정상 구간 40개에 가설별 교란을 넣고 강도를 이분 탐색해 이상 구간과 같은 M0 R² 중앙으로 맞춘다.
     |모사 R² 중앙 − 목표| > 0.02면 맞춤 실패로 표시하고 비교에서 뺀다(anomaly_day_sim_info.csv).
  5) 방향 규칙(개정 때 고정, 모든 가설에 대칭): 지문 c·모사 k마다 이상 구간 값의 모사 분포 안 양측 경험 p.
     p<0.05 구간 비율(불일치 비율) ≥0.5면 k '어긋남', ≤0.2면 '일치', 사이면 '애매', 유효 구간 <5면 '미확인'.
     가설 방향: 자기 모사가 모두 '어긋남'이면 반대. 아니고 자기 모사 중 '일치'가 있으면서 다른 가설 하나 이상이 반대면
     (검사가 가설을 가름) 지지. 그 밖은 중립(하위 메커니즘 하나만 어긋나는 경우 포함). 모사가 없는 검사는 모두 중립.
     반대는 모사한 하위 메커니즘에 한하고, 지지는 여러 가설에 동시에 붙을 수 있다(합산하지 않는다).
  6) 모사 방향이 없는 관찰(수준-산포, 구간 수준 이동, 진폭, 극값 분해, 진동·진폭·시각 Spearman, 저장 형식)은 중립으로 둔다.
사전/사후: M0·M2·M3·M5·M4(rho4)·백색잡음/정상 대조·모사 지문(ac1·첨도·crest·부분R²)·Spearman은 1차 실행 전 명세였고 M1F도 명세다.
  반송파 검사, 대리·빗 대조, 계단 통제(rho4s), 수준-산포는 1차 결과를 본 뒤 추가했다. 시간 통제 rho4t·위상 폭 조건·M1F 빗 대조·
  극값 분해·반송파 흰 산포 대조·방향 규칙·수준-산포 사분위 문턱은 검토 뒤 개정에서 정했다. 표의 '사전_사후' 열에 표시한다.
한계: 정상·이상이 서로 다른 하루(자정 직후 vs 오전)이고 저장 형식도 달라 날짜·수집 차이와 고장을 분리할 수 없다.
  길이≥30 이상 구간은 10개뿐이다. 타임스탬프가 명목 100ms라 실제 샘플 시각(지터)을 직접 볼 수 없고,
  앨리어스 이동은 전원/구동 주파수 변화(H2)와 샘플링 클록 변화(H1)를 구분하지 못한다. 모사는 단순 생성모형이고 수준 이동은
  어떤 모사에도 없다. 대리는 정상 과정이라 시간 이분산을 보존하지 않는다(rho4t는 시간 추세를 통제해 이를 줄인다).
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")  # 결정성: BLAS 스레드 수에 따라 1e-13 수준 차이가 난다 (numpy import 전)

import warnings  # noqa: E402
from functools import lru_cache  # noqa: E402
from pathlib import Path  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from scipy.stats import binomtest, kurtosis, norm, rankdata, spearmanr  # noqa: E402

from data import DEFAULT_ROOT, SENSORS, load, load_vendor  # noqa: E402
from scores import FREQS  # noqa: E402

plt.rcParams["font.family"] = [f for f in ("Malgun Gothic", "AppleGothic", "NanumGothic")
                               if f in {x.name for x in font_manager.fontManager.ttflist}] + ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "pipeline"
MIN_TABLE, MIN_FIT = 10, 30
HARM = (2, 3, 5)
FIXED = (1.2, 1.8, 3.0)                                 # 명세 M1: 60.6(또는 59.4)Hz 2·3·5차 고조파의 10Hz 앨리어스
BAND = (0.55, 0.65)                                     # 정상 앨리어스 0.600Hz ± 0.05
F_BAND = FREQS[(FREQS > BAND[0] - 1e-9) & (FREQS < BAND[1] + 1e-9)]
RATES = np.unique(np.round(np.r_[np.arange(-0.1, 0.1001, 0.005), np.arange(-0.5, 0.5001, 0.02)], 4)) + 0.0
EXTRA = ("M1", "M1F", "M2", "M3", "M5")
FP = ("f_M0", "car", "p_M1F", "p_M2", "p_M3", "p_M5", "rho4t", "ac1", "kurt", "crest")   # 모사 비교 지문
SUR_COLS = ("p_M1", "p_M1F", "p_M2", "p_M3", "p_M5", "rho4", "rho4s", "rho4t", "ac1", "car")
SIMS = {"jitter": "H1", "fm": "H2", "am_slow": "H3", "am_fast": "H4", "harmonic": "H4", "additive": "H5"}
S_MAX = {"jitter": 4.0, "fm": 3.0, "am_slow": 10.0, "am_fast": 10.0, "harmonic": 10.0, "additive": 10.0}
HYP = {"H1": "타이밍·클록", "H2": "구동 주파수", "H3": "부하 진폭", "H4": "파형 왜곡·기어 부하 접힘", "H5": "계측 사슬 이상"}
HCOL = {h: f"{h}_{n}(모사 {'·'.join(k for k, v in SIMS.items() if v == h)})" for h, n in HYP.items()}
N_NOISE, N_SUR, N_SIM, N_COMB, N_COMB_REF, N_BOOT, SEED, CHUNK = 200, 200, 40, 50, 40, 1000, 0, 2000
LINE_HZ, Q_CUR, WIN_LS = 60.0, 1.1920929, 5
R2_TOL = 0.02                                           # 모사 R² 맞춤 성공: |모사 중앙 − 목표| ≤ 0.02
MISS_P, MISS_AGAINST, MISS_MATCH, MIN_DIR_SEG, MIN_NULL = 0.05, 0.5, 0.2, 5, 10
NEU = {h: "중립" for h in HYP}


# ---------- 격자 피팅 ----------
def _fold(f):
    """10Hz 샘플에서 보이는 주파수: 가장 가까운 10의 배수까지 거리([0, 5]Hz)."""
    return np.abs((np.asarray(f, float) + 5.0) % 10.0 - 5.0)


def _sc(ph):
    return [np.sin(ph), np.cos(ph)]


def _designs(model, L, mult=None):
    """(격자 모수 (G, 2), 설계 행렬 (G, L, p)) 조각. 모든 모형에 상수항이 있다.
    mult = M1 빗의 배수(기본 HARM) 또는 M1F의 고정 주파수(기본 FIXED)."""
    t = np.arange(L) * 0.1
    if model in ("M0", "MC", "M1", "M1F", "M3"):
        fr = F_BAND if model == "MC" else FREQS
        ph = 2 * np.pi * fr[:, None] * t
        cols = _sc(ph)
        if model == "M1":
            for k in (HARM if mult is None else mult):
                cols += _sc(2 * np.pi * _fold(k * fr)[:, None] * t)
        if model == "M1F":
            for fq in (FIXED if mult is None else mult):
                cols += _sc(np.broadcast_to(2 * np.pi * fq * t, ph.shape))
        if model == "M3":
            cols += [c * (t - t.mean()) for c in _sc(ph)]
        yield np.c_[fr, np.zeros(len(fr))], np.stack(cols + [np.ones_like(ph)], -1)
        return
    if model == "M2":
        a, b = np.meshgrid(FREQS, RATES, indexing="ij")
    else:  # M5: 계단 위치 k (앞뒤 3관측 이상)
        a, b = np.meshgrid(FREQS, np.arange(3, L - 2), indexing="ij")
    a, b = a.ravel(), b.ravel()
    for i in range(0, len(a), CHUNK):
        f0, q = a[i:i + CHUNK, None], b[i:i + CHUNK, None]
        if model == "M2":
            ph = 2 * np.pi * (f0 * t + 0.5 * q * t * t)
            cols = _sc(ph) + [np.ones_like(ph)]
        else:
            ph = 2 * np.pi * f0 * t
            cols = _sc(ph) + [np.ones_like(ph), (np.arange(L) >= q).astype(float)]
        yield np.c_[a[i:i + CHUNK], b[i:i + CHUNK]], np.stack(cols, -1)


def _basis(A):
    """설계 행렬 묶음의 직교 기저. 퇴화 열(예: 0Hz·5Hz의 sin, 고정 주파수와 겹친 기본)은 0으로 둔다."""
    U, s, _ = np.linalg.svd(A, full_matrices=False)
    return U * (s > s[:, :1] * 1e-9)[:, None, :]


def _flat(par, A):
    U = _basis(A)
    return par, U.transpose(1, 0, 2).reshape(A.shape[1], -1), U.shape[2]


@lru_cache(maxsize=None)
def _cached(model, L):
    return _flat(*next(_designs(model, L)))


def _bases(model, L, mult=None):
    if model in ("M0", "MC") or (model in ("M1", "M1F") and mult is None):
        yield _cached(model, L)
        return
    for par, A in _designs(model, L, mult):
        yield _flat(par, A)


def _best(Xc, model, mult=None):
    """중심화된 X (n, L)의 격자 최대 설명 제곱합과 그 격자 모수."""
    n, L = Xc.shape
    best, bpar = np.full(n, -np.inf), np.zeros((n, 2))
    for par, Uf, p in _bases(model, L, mult):
        E = ((Xc @ Uf) ** 2).reshape(n, -1, p).sum(2)
        j = E.argmax(1)
        e = E[np.arange(n), j]
        up = e > best
        best[up], bpar[up] = e[up], par[j[up]]
    return best, bpar


def _m0_r2(X):
    Xc = X - X.mean(1, keepdims=True)
    return _best(Xc, "M0")[0] / (Xc ** 2).sum(1)


def _m0_detail(X, model="M0"):
    """사인+상수 적합(M0 전 대역 / MC 반송파 대역): R², 주파수, 진폭 R, 위상 φ (fit = c + R·sin φ), 적합값, 잔차."""
    n, L = X.shape
    Xc = X - X.mean(1, keepdims=True)
    e0, par = _best(Xc, model)
    f = par[:, 0]
    ph = 2 * np.pi * f[:, None] * np.arange(L) * 0.1
    A = np.stack(_sc(ph) + [np.ones_like(ph)], -1)
    coef = (np.linalg.pinv(A) @ X[..., None])[..., 0]
    fit = (A @ coef[..., None])[..., 0]
    phase = ph + np.arctan2(coef[:, 1], coef[:, 0])[:, None]
    return dict(r2=e0 / (Xc ** 2).sum(1), f=f, R=np.hypot(coef[:, 0], coef[:, 1]), c=coef[:, 2],
                phase=phase, fit=fit, res=X - fit)


def _rowcorr(a, b):
    a = a - a.mean(1, keepdims=True)
    b = b - b.mean(1, keepdims=True)
    den = np.sqrt((a * a).sum(1) * (b * b).sum(1))
    return np.where(den > 1e-12, (a * b).sum(1) / np.where(den > 1e-12, den, 1), np.nan)


def _partial_rank(a, b):
    """행별 편순위상관: 두 순위를 시간 추세(1, t, |t−중앙|)에 회귀한 잔차끼리의 상관."""
    L = a.shape[1]
    tt = np.arange(L, dtype=float)
    Z = np.c_[np.ones(L), tt, np.abs(tt - tt.mean())]
    H = np.eye(L) - Z @ np.linalg.pinv(Z)
    return _rowcorr(rankdata(a, axis=1) @ H, rankdata(b, axis=1) @ H)


def fit_models(X):
    """같은 길이 시계열 (n, L) → 행별 지문 DataFrame."""
    n, L = X.shape
    Xc = X - X.mean(1, keepdims=True)
    sst = (Xc ** 2).sum(1)
    d0 = _m0_detail(X)
    out = dict(r2_M0=d0["r2"], f_M0=d0["f"])
    e0 = d0["r2"] * sst
    for m in EXTRA:
        e, par = _best(Xc, m)
        r2 = np.maximum(e, e0) / sst
        out[f"r2_{m}"], out[f"d_{m}"] = r2, r2 - d0["r2"]
        out[f"p_{m}"] = (r2 - d0["r2"]) / np.maximum(1 - d0["r2"], 1e-12)
        if m == "M2":
            out["rate_M2"] = par[:, 1]
        if m == "M5":
            par5 = par
    res = d0["res"]
    out["rho4"] = _rowcorr(rankdata(np.abs(res), axis=1), rankdata(np.abs(np.cos(d0["phase"])), axis=1))
    # 계단 통제 M4: M5 적합 잔차·위상으로 다시 잰다(rho4s). 판정판 rho4t는 시간 추세까지 통제하고 위상 폭 ≥360°만 쓴다
    t = np.arange(L) * 0.1
    ph5 = 2 * np.pi * par5[:, [0]] * t
    A5 = np.stack(_sc(ph5) + [np.ones_like(ph5), (np.arange(L) >= par5[:, [1]]).astype(float)], -1)
    c5 = (np.linalg.pinv(A5) @ X[..., None])[..., 0]
    a5 = np.abs(X - (A5 @ c5[..., None])[..., 0])
    cos5 = np.abs(np.cos(ph5 + np.arctan2(c5[:, 1], c5[:, 0])[:, None]))
    out["f_M5"] = par5[:, 0]
    out["span_M5"] = 360.0 * par5[:, 0] * (L - 1) * 0.1
    out["rho4s"] = _rowcorr(rankdata(a5, axis=1), rankdata(cos5, axis=1))
    out["rho4t"] = np.where(out["span_M5"] >= 360.0, _partial_rank(a5, cos5), np.nan)
    out["ac1"] = _rowcorr(res[:, :-1], res[:, 1:])
    out["kurt"] = kurtosis(X, axis=1, fisher=False)
    out["crest"] = np.abs(Xc).max(1) / np.sqrt(2 * Xc.var(1))
    mc = _m0_detail(X, "MC")
    out["car"], out["car_amp"] = mc["r2"], mc["R"]
    return pd.DataFrame(out)


def fit_all(series):
    """길이가 섞인 시계열 목록 → 입력 순서의 지문 (길이별로 묶어 적합)."""
    lens = np.array([len(s) for s in series])
    parts = []
    for L in np.unique(lens):
        idx = np.flatnonzero(lens == L)
        parts.append(fit_models(np.stack([series[i] for i in idx]).astype(float)).set_index(idx))
    return pd.concat(parts).sort_index()


# ---------- 엄격한 대조 ----------
def _surrogates(x, rng, n):
    """M0 적합 + 위상 무작위 M0 잔차: 잔차 스펙트럼(자기상관)은 보존, 반송파 위상과의 결합·국소 계단·비정상성은 파괴."""
    d = _m0_detail(np.asarray(x, float)[None])
    L = len(x)
    F = np.fft.rfft(d["res"][0])
    ph = rng.uniform(0, 2 * np.pi, (n, len(F)))
    ph[:, 0] = 0
    if L % 2 == 0:
        ph[:, -1] = 0
    return d["fit"][0] + np.fft.irfft(np.abs(F) * np.exp(1j * ph), n=L)


def _combs():
    """M1(자유 기본) 대조: 비정수 배수 빗."""
    rng = np.random.default_rng([SEED, 2])
    out = []
    while len(out) < N_COMB:
        m = rng.uniform(1.2, 5.8, len(HARM))
        if np.all(np.abs(m - np.round(m)) >= 0.2):
            out.append(tuple(m))
    return out


def _fixed_combs():
    """M1F(고정 고조파) 대조: 반송파·고조파 앨리어스에서 0.1Hz 이상 떨어진 고정 3주파수 빗."""
    rng = np.random.default_rng([SEED, 4])
    avoid = np.r_[0.6, FIXED]
    out = []
    while len(out) < N_COMB:
        f = np.sort(np.round(rng.uniform(0.3, 4.7, len(FIXED)), 3))
        if np.abs(f[:, None] - avoid).min() >= 0.1 and np.diff(f).min() >= 0.1:
            out.append(tuple(f))
    return out


def comb_quantile(X, model, ref, combs):
    """ref 빗(고조파) 부분 R²가 같은 자유도 대조 빗들 사이에서 몇 분위인가 (0.5 = 고조파가 특별하지 않음)."""
    Xc = X - X.mean(1, keepdims=True)
    sst = (Xc ** 2).sum(1)
    e0 = _best(Xc, "M0")[0]

    def part(mult):
        return (np.maximum(_best(Xc, model, mult)[0], e0) - e0) / np.maximum(sst - e0, 1e-12)

    ph = part(ref)
    P = np.stack([part(c) for c in combs], 1)
    return (np.sum(P < ph[:, None], 1) + 0.5 * np.sum(P == ph[:, None], 1)) / len(combs)


# ---------- 1) 구간 표 ----------
def _series(frame, yj, min_len):
    b = yj.blocks(frame)
    x = frame.AI2_Current.to_numpy(float)
    ids, cnt = np.unique(b, return_counts=True)
    return {int(s): x[b == s] for s in ids[cnt >= min_len]}


def segment_table(frame, yj, mu, sd, cur_max):
    b = yj.blocks(frame)
    ts = pd.to_datetime(frame.TimeStamp)
    S = frame[SENSORS].to_numpy(float)
    z = np.abs((S - mu) / sd)
    xs = _series(frame, yj, MIN_TABLE)
    keys = list(xs)
    lens = np.array([len(xs[k]) for k in keys])
    fit = {c: np.empty(len(keys)) for c in ("r2", "f", "car_r2", "car_amp")}
    for L in np.unique(lens):
        idx = np.flatnonzero(lens == L)
        X = np.stack([xs[keys[i]] for i in idx])
        d, c = _m0_detail(X), _m0_detail(X, "MC")
        fit["r2"][idx], fit["f"][idx], fit["car_r2"][idx], fit["car_amp"][idx] = d["r2"], d["f"], c["r2"], c["R"]
    rows = []
    for i, s in enumerate(keys):
        m = b == s
        x = xs[s]
        zz = z[m]
        r2 = fit["r2"][i]
        rows.append(dict(segment=s, start=ts[m].iloc[0], length=len(x), sine_r2=r2, alias_f=fit["f"][i], mean=x.mean(),
                         amp=np.sqrt(2 * x.var()), abs_max=np.abs(x).max(), n_over_normal_max=int((np.abs(x) > cur_max).sum()),
                         abs_max_centered=np.abs(x - x.mean()).max(), diff_sigma=np.sqrt(np.mean(np.diff(x) ** 2) / 2),
                         vib0_std=S[m, 0].std(ddof=1), vib1_std=S[m, 1].std(ddof=1), maxz=zz.max(),
                         maxz_sensor=SENSORS[int(zz.max(0).argmax())], car_r2=fit["car_r2"][i], car_amp=fit["car_amp"][i],
                         jitter_ms_equiv=np.sqrt(-np.log(np.clip(r2, 1e-12, 1))) / (2 * np.pi * LINE_HZ) * 1e3))
    return pd.DataFrame(rows)


def car_white_q(xs, rng):
    """구간마다 car_amp가 '가법 흰 산포(차분 σ)만 있는 같은 길이 백색잡음'의 반송파 대역 최대 진폭 분포의 몇 분위인가."""
    out = {}
    for s, x in xs.items():
        x = np.asarray(x, float)
        sig = np.sqrt(np.mean(np.diff(x) ** 2) / 2)
        Rn = _m0_detail(rng.standard_normal((N_NOISE, len(x))) * sig, "MC")["R"]
        out[s] = dict(q_white=_q(Rn, _m0_detail(x[None], "MC")["R"][0]), white_q95=float(np.quantile(Rn, .95)))
    return pd.DataFrame(out).T.rename_axis("segment").reset_index()


def level_scatter(frame, yj):
    """구간 안 겹치지 않는 WIN_LS관측 창: |평균|, 차분 산포 √(mean(Δx²)/2)."""
    b = yj.blocks(frame)
    x = frame.AI2_Current.to_numpy(float)
    M, S = [], []
    for s in np.unique(b):
        v = x[b == s]
        for i in range(0, len(v) - WIN_LS + 1, WIN_LS):
            w = v[i:i + WIN_LS]
            M.append(abs(w.mean()))
            S.append(np.sqrt(np.mean(np.diff(w) ** 2) / 2))
    return np.array(M), np.array(S)


# ---------- 4) 양성 대조 모사 ----------
def _rw(rng, n, L):
    w = np.cumsum(rng.standard_normal((n, L)), 1)
    return (w - w.mean(1, keepdims=True)) / w.std(1, keepdims=True)


def _sim(kind, s, base, dr):
    c, R, th, e0 = base["c"][:, None], base["R"][:, None], base["phase"], base["res"]
    if kind == "jitter":        # H1: 샘플 시각 오차 → 반송파 위상 오차 (iid)
        return c + R * np.sin(th + s * dr["xi"]) + e0
    if kind == "fm":            # H2: 순간 주파수 랜덤워크 (rms s Hz)
        return c + R * np.sin(th + 2 * np.pi * 0.1 * np.cumsum(s * dr["w"], 1)) + e0
    if kind == "am_slow":       # H3: 느린 진폭(부하) 변화
        return c + R * (1 + s * dr["w"]) * np.sin(th) + e0
    if kind == "am_fast":       # H4: 빠른 부하 변동(기어 맞물림 등)이 접힌 것 = 샘플마다 독립인 진폭 변동
        return c + R * (1 + s * dr["xi"]) * np.sin(th) + e0
    if kind == "harmonic":      # H4: 반송파 k차 고조파 (10Hz 샘플에서 위상 kφ)
        h = sum(np.sin(k * th + dr["psi"][:, [i]]) for i, k in enumerate(HARM)) / np.sqrt(len(HARM))
        return c + R * np.sin(th) + s * R * h + e0
    if kind == "additive":      # H5: 위상과 무관한 광대역 가법(계측) 잡음
        return c + R * np.sin(th) + e0 + s * R * dr["xi"] / np.sqrt(2)
    raise ValueError(kind)


def _match(kind, base, dr, target):
    """모사 M0 R² 중앙값이 target이 되는 강도 (로그 이분 탐색). 도달 못 하면 상한 — 맞춤 성공 여부는 R2_TOL로 따로 판정."""
    r2 = lambda s: float(np.median(_m0_r2(_sim(kind, s, base, dr))))  # noqa: E731
    lo, hi = 1e-4, S_MAX[kind]
    if r2(hi) > target:
        return hi, r2(hi)
    for _ in range(30):
        mid = np.sqrt(lo * hi)
        lo, hi = (mid, hi) if r2(mid) > target else (lo, mid)
    return hi, r2(hi)


def simulate(xa, xn, targets):
    """이상 구간마다: 같은 길이 정상 구간 N_SIM개에 가설별 교란을 넣어 R²를 맞춘다."""
    series, tags, info = [], [], []
    for s, x in xa.items():
        L = len(x)
        pool = [v[:L] for v in xn.values() if len(v) >= L]
        rng = np.random.default_rng([SEED, s])
        base = _m0_detail(np.stack([pool[i] for i in rng.choice(len(pool), N_SIM, replace=False)]))
        dr = dict(xi=rng.standard_normal((N_SIM, L)), w=_rw(rng, N_SIM, L),
                  psi=rng.uniform(0, 2 * np.pi, (N_SIM, len(HARM))))
        for kind in SIMS:
            st, got = _match(kind, base, dr, targets[s])
            X = _sim(kind, st, base, dr)
            series += list(X)
            tags += [("sim", (s, kind))] * N_SIM
            info.append(dict(segment=s, kind=kind, hypothesis=SIMS[kind], strength=st, s_max=S_MAX[kind],
                             r2_target=targets[s], r2_sim_median=got, fit_ok=bool(abs(got - targets[s]) <= R2_TOL)))
    return series, tags, pd.DataFrame(info)


# ---------- 통계 도우미 ----------
def _q(null, v):
    null = np.asarray(null, float)
    null = null[np.isfinite(null)]
    if not np.isfinite(v) or not len(null):
        return np.nan
    return (np.sum(null < v) + 0.5 * np.sum(null == v)) / len(null)


def _z(null, v):
    """null이 퇴화(std < 1e-9)하면 NaN — 1e10 같은 무의미한 z를 막는다."""
    null = np.asarray(null, float)
    null = null[np.isfinite(null)]
    if len(null) < 2 or not np.isfinite(v):
        return np.nan
    sd = null.std()
    return (v - null.mean()) / sd if sd >= 1e-9 else np.nan


def _stouffer(qs, n):
    qs = np.asarray(qs, float)
    qs = qs[np.isfinite(qs)]
    return float(norm.ppf(np.clip(qs, 0.5 / n, 1 - 0.5 / n)).sum() / np.sqrt(len(qs))) if len(qs) else np.nan


def _nan(fn, v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return float(fn(v)) if len(v) else np.nan


def _summary_rows(df, cols, label, n):
    rows = []
    for stat, fn in (("min", np.min), ("q05", lambda v: np.quantile(v, .05)), ("median", np.median),
                     ("q95", lambda v: np.quantile(v, .95)), ("max", np.max)):
        r = dict(set=label, stat=stat, n=n)
        r.update({c: _nan(fn, df[c]) for c in cols})
        rows.append(r)
    return rows


def _dist(v, fmt="{:.3f}", q=False):
    """'중앙 m [min~max] (n)' 또는 q=True면 [q05~q95]."""
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return "—"
    lo, hi = (np.quantile(v, .05), np.quantile(v, .95)) if q else (v.min(), v.max())
    return f"중앙 {fmt.format(np.median(v))} [{'q05~q95 ' if q else ''}{fmt.format(lo)}~{fmt.format(hi)}] (n={len(v)})"


def _directions(cmp, fps):
    """방향 규칙(docstring 5). cmp = 구간×모사×지문 비교표. → (가설별 방향, 위치 문자열)."""
    st = {}
    for kind in SIMS:
        d = cmp[(cmp.kind == kind) & cmp.fit_ok & cmp.fp.isin(fps) & cmp.p2.notna()]
        nseg = int(d.segment.nunique())
        if nseg < MIN_DIR_SEG:
            st[kind] = ("미확인", np.nan, nseg)
        else:
            miss = float((d.p2 < MISS_P).mean())
            st[kind] = ("어긋남" if miss >= MISS_AGAINST else "일치" if miss <= MISS_MATCH else "애매", miss, nseg)
    mine = {h: [st[k][0] for k, v in SIMS.items() if v == h] for h in HYP}
    against = {h: bool(mine[h]) and all(m == "어긋남" for m in mine[h]) for h in HYP}
    dirs = {}
    for h in HYP:
        if against[h]:
            dirs[h] = "반대"
        elif "일치" in mine[h] and any(against[g] for g in HYP if g != h):
            dirs[h] = "지지"
        else:
            dirs[h] = "중립"
    pos = "모사 불일치 비율(구간 수): " + " · ".join(
        f"{k} {'—' if not np.isfinite(m) else f'{m:.2f}'}({n})" for k, (_, m, n) in st.items())
    return dirs, pos


# ---------- 실행 ----------
def run(out: Path, root, yj):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    normal, abnormal = load(root)
    mu, sd = normal[SENSORS].mean().to_numpy(), normal[SENSORS].std(ddof=0).to_numpy()
    cur_max = float(normal.AI2_Current.abs().max())
    seg_a = segment_table(abnormal, yj, mu, sd, cur_max)
    seg_n = segment_table(normal, yj, mu, sd, cur_max)
    t0 = seg_a.start.min()
    seg_a["t_sec"] = (seg_a.start - t0).dt.total_seconds()
    seg_a = seg_a.merge(car_white_q(_series(abnormal, yj, MIN_TABLE), np.random.default_rng([SEED, 6])),
                        on="segment", how="left")

    # 2)·3)·4) 피팅 묶음: 이상·정상(전 길이) + 길이별 백색잡음·정상(앞 L관측) + 대리 + 모사
    xa, xn = _series(abnormal, yj, MIN_FIT), _series(normal, yj, MIN_FIT)
    rng = np.random.default_rng(SEED)
    series, tags = [], []
    for tag, d in (("anom", xa), ("normal", xn)):
        series += list(d.values())
        tags += [(tag, s) for s in d]
    for L in sorted({len(x) for x in xa.values()}):
        series += list(rng.standard_normal((N_NOISE, L)))
        tags += [("noise", L)] * N_NOISE
        trunc = [v[:L] for v in xn.values() if len(v) >= L]
        series += trunc
        tags += [("normal_L", L)] * len(trunc)
    for s, x in xa.items():
        series += list(_surrogates(x, np.random.default_rng([SEED, 1, s]), N_SUR))
        tags += [("sur", s)] * N_SUR
    s_series, s_tags, sim_info = simulate(xa, xn, dict(zip(seg_a.segment, seg_a.sine_r2)))
    fp = fit_all(series + s_series)
    fp["tag"] = [t for t, _ in tags + s_tags]
    fp["key"] = [k for _, k in tags + s_tags]
    fp["simkey"] = [f"{k[0]}|{k[1]}" if t == "sim" else "" for t, k in tags + s_tags]

    # 빗 대조: 이상 구간 + 같은 길이 정상(앞 L관측) 표본(양성 대조 — 정상 전류의 실제 고조파를 잡는지)
    combs = {"q_comb": ("M1", HARM, _combs()), "q_combF": ("M1F", FIXED, _fixed_combs())}
    fp["q_comb"], fp["q_combF"] = np.nan, np.nan
    rng2 = np.random.default_rng([SEED, 3])
    for L in sorted({len(x) for x in xa.values()}):
        ia = [i for i, (t, k) in enumerate(tags) if t == "anom" and len(xa[k]) == L]
        il = [i for i, (t, k) in enumerate(tags) if t == "normal_L" and k == L]
        idx = ia + [int(i) for i in rng2.choice(il, min(N_COMB_REF, len(il)), replace=False)]
        X = np.stack([series[i] for i in idx]).astype(float)
        for col, (model, ref, cb) in combs.items():
            fp.loc[idx, col] = comb_quantile(X, model, ref, cb)

    # 구간별 검정 열 + 모사 비교표
    A = fp[fp.tag == "anom"].set_index("key")
    ok = {(r.segment, r.kind): r.fit_ok for r in sim_info.itertuples()}
    extra_rows, cmp_rows = [], []
    for s, r in A.iterrows():
        L = len(xa[s])
        nz = fp[(fp.tag == "noise") & (fp.key == L)]
        nl = fp[(fp.tag == "normal_L") & (fp.key == L)]
        sg = fp[(fp.tag == "sur") & (fp.key == s)]
        e = dict(segment=s)
        for m in EXTRA:
            for st in ("d", "p"):
                v = r[f"{st}_{m}"]
                e[f"z_noise_{st}_{m}"], e[f"q_noise_{st}_{m}"] = _z(nz[f"{st}_{m}"], v), _q(nz[f"{st}_{m}"], v)
                e[f"z_normal_{st}_{m}"], e[f"q_normal_{st}_{m}"] = _z(nl[f"{st}_{m}"], v), _q(nl[f"{st}_{m}"], v)
        for c in ("rho4", "rho4t", "ac1", "kurt", "crest", "car"):
            e[f"q_noise_{c}"], e[f"q_normal_{c}"] = _q(nz[c], r[c]), _q(nl[c], r[c])
        for c in SUR_COLS:
            e[f"z_sur_{c}"], e[f"q_sur_{c}"] = _z(sg[c], r[c]), _q(sg[c], r[c])
        for kind in SIMS:
            sm = fp[fp.simkey == f"{s}|{kind}"]
            p2 = []
            for c in FP:
                nv = int(np.isfinite(sm[c].to_numpy(float)).sum())
                q = _q(sm[c], r[c]) if nv >= MIN_NULL else np.nan
                p = float(np.clip(2 * min(q, 1 - q), 1 / (nv + 1), 1)) if np.isfinite(q) else np.nan
                p2.append(p)
                cmp_rows.append(dict(segment=s, kind=kind, fit_ok=ok[(s, kind)], fp=c, value=r[c],
                                     sim_median=_nan(np.median, sm[c]), n_sim=nv, p2=p))
            good = ok[(s, kind)] and np.isfinite(p2).any()
            e[f"sim_{kind}_medp"] = float(np.nanmedian(p2)) if good else np.nan
            e[f"sim_{kind}_miss"] = int(np.nansum(np.array(p2) < MISS_P)) if good else np.nan
        extra_rows.append(e)
    cmp = pd.DataFrame(cmp_rows)
    fit_cols = ["r2_M0", "f_M0"] + [f"{a}_{m}" for m in EXTRA for a in ("r2", "d", "p")] + \
               ["rate_M2", "f_M5", "span_M5", "rho4", "rho4s", "rho4t", "ac1", "kurt", "crest", "car", "car_amp",
                "q_comb", "q_combF"]
    ex = pd.DataFrame(extra_rows)
    # 퇴화 z 열 제거: null std<1e-9로 전부 NaN인 열 + z_normal_d_*(정상 ΔR²가 0에 붙어(잔차 0.4%) z가 10²~10³으로
    # 부풀어 무의미 — 분위 q_normal_d만 남긴다)
    ex = ex.drop(columns=[c for c in ex if c.startswith("z_") and (ex[c].isna().all() or c.startswith("z_normal_d_"))])
    seg_full = seg_a.merge(A[fit_cols].rename_axis("segment").reset_index(), on="segment", how="left") \
                    .merge(ex, on="segment", how="left")
    seg_full.insert(0, "set", "이상")
    seg_full.insert(2, "stat", "")
    seg_full.insert(3, "n", 1)
    table_cols = ["length", "sine_r2", "alias_f", "mean", "amp", "abs_max", "n_over_normal_max", "abs_max_centered",
                  "diff_sigma", "vib0_std", "vib1_std", "maxz", "car_r2", "car_amp", "jitter_ms_equiv"]
    N = fp[fp.tag == "normal"]
    NC = fp[(fp.tag == "normal_L") & fp.q_comb.notna()]
    summ = _summary_rows(seg_n, table_cols, f"정상요약(길이≥{MIN_TABLE})", len(seg_n)) + \
        _summary_rows(N, [c for c in fit_cols if not c.startswith("q_comb")], f"정상요약_피팅(길이≥{MIN_FIT})", len(N)) + \
        _summary_rows(NC, ["q_comb", "q_combF"], "정상요약_빗대조(앞 L관측 표본)", len(NC))
    seg_out = pd.concat([seg_full, pd.DataFrame(summ)], ignore_index=True)
    seg_out["start"] = seg_out.start.astype(str).replace("NaT", "")
    seg_out.to_csv(out / "anomaly_day_segments.csv", index=False, float_format="%.10g")

    wide = cmp.pivot_table(index=["segment", "kind"], columns="fp", values=["p2", "sim_median"], aggfunc="first")
    wide.columns = [f"{'p' if a == 'p2' else 'simmed'}_{b}" for a, b in wide.columns]
    sim_out = sim_info.merge(wide.reset_index(), on=["segment", "kind"], how="left")
    sim_out.to_csv(out / "anomaly_day_sim_info.csv", index=False, float_format="%.10g")

    n_norm = int(pd.Series([k for t, k in tags if t == "normal_L"]).value_counts().min())
    ev = evidence(seg_a, seg_n, seg_full, fp, cmp, sim_info, normal, abnormal, cur_max, n_norm, yj)
    ev.to_csv(out / "anomaly_day_hypotheses.csv", index=False, float_format="%.10g")
    figure(out, xa, xn, seg_full, fp, series + s_series, ok)
    return ev


def evidence(seg_a, seg_n, seg_full, fp, cmp, sim_info, normal, abnormal, cur_max, n_norm, yj):
    """증거 표: 검사마다 무엇을 재는지, 정상·이상 값, 대조 대비 위치, 사전/사후, 가설별 방향(모사 확인분만)."""
    rows = []

    def add(test, what, nv, av, pos, pp, dirs, note=""):
        r = {"검사": test, "무엇을_재는가": what, "정상_값": nv, "이상_값": av, "대조_대비_위치": pos, "사전_사후": pp}
        r.update({HCOL[h]: (dirs[h] if isinstance(dirs, dict) else dirs) for h in HYP})
        r["비고"] = note
        rows.append(r)

    L = seg_full[seg_full.r2_M0.notna()]
    nL = len(L)
    NN, NZ = fp[fp.tag == "normal"], fp[fp.tag == "noise"]
    nA = len(seg_a)
    fail = sim_info[~sim_info.fit_ok]
    fail_s = ", ".join(f"{k}:{','.join(str(int(s)) for s in g.segment)}" for k, g in fail.groupby("kind", sort=False)) or "없음"
    no_sim = "모사 없음 → 방향 없음"

    # --- 사인 붕괴 자체 ---
    add("사인 R² (M0)", "0~5Hz 단일 사인+상수가 설명하는 분산 비율", _dist(seg_n.sine_r2), _dist(seg_a.sine_r2),
        f"이상 {int((seg_a.sine_r2 < seg_n.sine_r2.min()).sum())}/{nA}구간이 정상 최소 미만 · "
        f"백색잡음(길이≥{MIN_FIT} 같은 길이) M0 R² 중앙 {NZ.r2_M0.median():.3f}", "사전", NEU,
        "모사는 이 값에 맞춰 만들었으므로 방향 없음")
    dirs, spos = _directions(cmp, ["f_M0"])
    f_norm = float(seg_n.alias_f.median())
    near = int(((seg_a.alias_f - f_norm).abs() < 0.1).sum())
    add("앨리어스 주파수 (M0 최적 f, Hz)", "구간에서 가장 강한 사인 성분의 주파수", _dist(seg_n.alias_f, q=True),
        _dist(seg_a.alias_f), f"정상 {f_norm:.3f}±0.1Hz 안 이상 구간 {near}/{nA}; {spos}", "사전", dirs,
        "클록 오프셋(H1)·주파수 계단(H2)은 모사하지 않았다 — 둘 다 이 이동을 낼 수 있고 앨리어스만으로는 구분 불가")

    # --- 반송파 ---
    nq = int((seg_a.q_white >= 0.95).sum())
    p_car = float(binomtest(nq, nA, 0.05, alternative="greater").pvalue)   # 반송파가 없으면 구간마다 5%만 q95를 넘는다
    add("0.6Hz 반송파 진폭 (car_amp)", "0.55~0.65Hz 사인+상수 적합 진폭", _dist(seg_n.car_amp, "{:.0f}"),
        _dist(seg_a.car_amp, "{:.0f}"),
        f"구간별 가법 흰 산포(차분 σ)만 있는 같은 길이 백색잡음의 대역 최대 진폭 q95를 넘는 이상 구간 {nq}/{nA} "
        f"(우연 기대 {0.05 * nA:.2f}, 이항 p={p_car:.1e}; 분위 중앙 {seg_a.q_white.median():.2f}) · 정상 최소 "
        f"{seg_n.car_amp.min():.0f} 미만 {int((seg_a.car_amp < seg_n.car_amp.min()).sum())}/{nA}", "사후", NEU,
        "모사 비교는 다음 행(car_r2)에서 한다. 이항 p<0.05면 '소실 아님'으로 읽되, q95 미만 구간은 흰 산포 수준과 구분 불가. "
        "차분 σ는 계단·느린 성분도 포함해 흰 산포를 과대 추정하므로 보수적")
    dirs, spos = _directions(cmp, ["car"])
    add("0.6Hz 반송파 설명력 (car_r2)", "0.55~0.65Hz 사인+상수가 설명하는 분산 비율", _dist(seg_n.car_r2),
        _dist(seg_a.car_r2), f"이상 {int((seg_a.car_r2 < seg_n.car_r2.min()).sum())}/{nA}구간이 정상 최소 미만; {spos}",
        "사후", dirs, "정상 최소 미만 규칙은 R² 맞춤 모사도 모두 걸려 가설을 가르지 못해 모사 분포 대비 위치로 바꿨다. "
        "클록 오프셋·주파수 계단(반송파를 다른 주파수로 옮김)은 모사 밖")

    # --- 잔차 모형 ---
    q_refF = float(fp.loc[(fp.tag == "normal_L") & fp.q_combF.notna(), "q_combF"].median())
    q_ref = float(fp.loc[(fp.tag == "normal_L") & fp.q_comb.notna(), "q_comb"].median())
    spec = {"M1F": ("M1F 고정 고조파 1.2·1.8·3.0Hz 부분R² (명세판)", "M0 잔차 중 60.6Hz 2·3·5차 고조파 앨리어스가 설명하는 비율",
                    "사전(명세) · 빗 대조는 사후", "비고조파 고정 빗으로 같은 자유도의 유연성을 통제"),
            "M2": ("M2 선형 chirp 부분R²", "M0 잔차 중 선형 주파수 드리프트가 추가로 설명하는 비율", "사전 · 대리 대조는 사후",
                   "격자 f0 0.005Hz × 변화율 81개(0 포함 = M0 해). fm 모사(랜덤워크)와 모형이 다름. 대리는 계단도 파괴"),
            "M3": ("M3 선형 시변 진폭 부분R²", "M0 잔차 중 진폭의 선형 변화가 설명하는 비율", "사전 · 대리 대조는 사후", ""),
            "M5": ("M5 계단 1개 부분R²", "M0 잔차 중 수준 도약 하나가 설명하는 비율", "사전 · 대리 대조는 사후",
                   "백색잡음 대비 과대 유의는 잔차 자기상관(유색) 때문")}
    for m, (name, what, pp, note) in spec.items():
        Zw, Zs = _stouffer(L[f"q_noise_p_{m}"], N_NOISE), _stouffer(L[f"q_sur_p_{m}"], N_SUR)
        qn = float(np.nanmedian(L[f"q_normal_p_{m}"]))
        pos = f"백색잡음 Z={Zw:.2f} · 대리 Z={Zs:.2f} · 정상(앞 L관측) 분위 중앙 {qn:.2f}"
        if m == "M1F":
            pos = (f"비고조파 고정 빗 {N_COMB}개 대비 Z={_stouffer(L.q_combF, N_COMB):.2f} (이상 분위 중앙 "
                   f"{L.q_combF.median():.2f}, 정상 양성 대조 분위 중앙 {q_refF:.2f}) · " + pos)
        dirs, spos = _directions(cmp, [f"p_{m}"])
        add(name, what, _dist(NN[f"p_{m}"], q=True), _dist(L[f"p_{m}"]), f"{pos}; {spos}", pp, dirs,
            f"길이≥{MIN_FIT} 이상 구간 {nL}개. " + note)
    Zw1 = _stouffer(L.q_noise_p_M1, N_NOISE)
    add("M1 자유 기본 고조파 부분R² (참고)", "기본 주파수를 0~5Hz에서 자유롭게 고른 fold(2·3·5·f) 추가 설명 비율 (클록 이동 가정)",
        _dist(NN.p_M1, q=True), _dist(L.p_M1),
        f"비정수 배수 빗 {N_COMB}개 대비 Z={_stouffer(L.q_comb, N_COMB):.2f} (이상 분위 중앙 {L.q_comb.median():.2f}, "
        f"정상 양성 대조 {q_ref:.2f}) · 백색잡음 Z={Zw1:.2f} · 대리 Z={_stouffer(L.q_sur_p_M1, N_SUR):.2f}",
        "참고(명세와 다른 구현)", NEU,
        "이상 구간에서 기본이 느린 성분으로 잡혀 '고조파'가 느린 추세 기저가 된다. 백색잡음 대비 유의는 잔차가 유색(느린 성분)이기 "
        "때문이지 유연성 때문이 아니다(백색잡음 대조는 유연성을 이미 맞춤). 방향은 명세판(M1F)으로만 본다")

    # --- M4 지터 지문 ---
    elig = L[L.rho4t.notna()]
    dirs, spos = _directions(cmp, ["rho4t"])
    add("M4 지터 지문 rho4t", "M5 적합 |잔차|와 |cos 위상|의 편순위상관(시간 추세 통제). 지터면 +, 빠른 진폭 변동이면 −",
        _dist(NN.rho4t), _dist(elig.rho4t),
        f"위상 폭 ≥360° 이상 구간 {len(elig)}/{nL} ({', '.join(str(int(s)) for s in elig.segment) or '없음'}) · "
        f"대리 Z={_stouffer(L.q_sur_rho4t, N_SUR):.2f} · 백색잡음 Z={_stouffer(L.q_noise_rho4t, N_NOISE):.2f}; {spos}",
        "사후", dirs,
        f"참고: rho4(M0판) 중앙 {L.rho4.median():.3f}(대리 Z={_stouffer(L.q_sur_rho4, N_SUR):.2f}), "
        f"rho4s(계단 통제) 중앙 {L.rho4s.median():.3f}(대리 Z={_stouffer(L.q_sur_rho4s, N_SUR):.2f}) — "
        "위상 폭 반 주기 구간에서는 |cos 위상|이 시간의 단조 함수라 잔차 분산의 시간 추세를 잰다. "
        f"적격 구간의 M5 사인 주파수 {', '.join(f'{v:.2f}' for v in elig.f_M5)}Hz — 0.6Hz 반송파 위상이 아닐 수 있다")

    # --- 잔차·값 분포 지문 ---
    for c, name, what, note in (
            ("ac1", "M0 잔차 lag-1 자기상관", "잔차의 매끈함 (주파수 변동·느린 진폭 → 큼, 흰 산포 → 0 근처)", ""),
            ("kurt", "첨도", "값 분포 모양 (순수 사인 1.5)", ""),
            ("crest", "crest (최대|x−평균| / √(2var))", "첨두 대 진폭 비 (순수 사인 1.0)", "")):
        dirs, spos = _directions(cmp, [c])
        sur = f"대리 Z={_stouffer(L[f'q_sur_{c}'], N_SUR):.2f} · " if f"q_sur_{c}" in L else ""
        add(name, what, _dist(NN[c]), _dist(L[c]),
            f"{sur}백색잡음 분위 중앙 {np.nanmedian(L[f'q_noise_{c}']):.2f} · "
            f"정상 분위 중앙 {np.nanmedian(L[f'q_normal_{c}']):.2f}; {spos}", "사전", dirs, note)

    # --- 모사 종합 ---
    dirs, spos = _directions(cmp, list(FP))
    add("양성 대조 모사 종합 일치도", f"지문 {len(FP)}개({', '.join(FP)}) 전체의 불일치(p<{MISS_P}) 비율",
        "—", f"길이≥{MIN_FIT} 이상 구간 {nL}개", spos + f" · 맞춤 실패(제외) {fail_s}", "사전 방식 · 지문 목록 사후 개정",
        dirs, "개별 지문 행과 같은 규칙. 모사가 R² 목표에 못 미친 (구간, 모사) 쌍은 anomaly_day_sim_info.csv fit_ok=False")

    # --- 모사 없는 관찰 ---
    M, S = level_scatter(abnormal, yj)
    rho, p = spearmanr(M, S)
    q25, q75 = np.quantile(M, [.25, .75])
    lo, hi = S[M <= q25], S[M >= q75]
    rng = np.random.default_rng([SEED, 5])
    bs = [np.median(rng.choice(hi, len(hi))) / np.median(rng.choice(lo, len(lo))) for _ in range(N_BOOT)]
    ci = np.quantile(bs, [.025, .975])
    sig = float(np.median(S))
    add("수준-산포 (5관측 창 |평균| vs 차분 산포)", "흰 산포가 수준에 비례하는지 (곱셈형 +, 지터 −, 가법 0 예측)",
        "비교 불가(정상은 반송파 기울기가 창 산포를 지배)",
        f"창 {len(M)}개 Spearman rho={rho:.3f} (p={p:.2f}); 산포 중앙 σ={sig:.0f}",
        f"|평균| 상위 25% / 하위 25% 산포비 {np.median(hi) / np.median(lo):.2f} "
        f"(부트스트랩 95% [{ci[0]:.2f}~{ci[1]:.2f}], 창 {len(hi)}·{len(lo)}개)", "사후 (문턱은 개정에서 사분위로 고정)", NEU,
        f"{no_sim}(모사는 0.6Hz 반송파가 움직여 창 평균·산포가 비교 불가). 산포가 수준과 무관 = 가법형과 가장 단순히 맞음")
    nmax = float(seg_n["mean"].abs().max())
    add("구간 수준 이동 (구간 평균)", "기록구간 평균 전류", f"|평균| {_dist(seg_n['mean'].abs(), '{:.1f}')}",
        _dist(seg_a["mean"], "{:.1f}"),
        f"|평균|이 정상 최대 {nmax:.1f} 초과인 이상 구간 {int((seg_a['mean'].abs() > nmax).sum())}/{nA}", "사후", NEU,
        f"{no_sim}(어떤 모사도 수준 이동을 넣지 않음)")
    add("진폭 √(2var)", "구간 값 산포의 사인 진폭 환산", _dist(seg_n.amp, "{:.1f}"), _dist(seg_a.amp, "{:.1f}"),
        f"정상 범위 [{seg_n.amp.min():.1f}~{seg_n.amp.max():.1f}] 안 이상 구간 "
        f"{int(seg_a.amp.between(seg_n.amp.min(), seg_n.amp.max()).sum())}/{nA}", "사후", NEU, no_sim)
    x = abnormal.AI2_Current.to_numpy(float)
    b = yj.blocks(abnormal)
    xc = x - pd.Series(x).groupby(b).transform("mean").to_numpy()
    n_over = int((np.abs(x) > cur_max).sum())
    ncm = float(seg_n.abs_max_centered.max())
    add("극값 분해 (정상 최대 초과)", "|전류|가 정상일 최대를 넘는 행이 수준 이동과 흰 산포로 설명되는가",
        f"정상 최대 |x| {cur_max:.1f} · 구간 평균 뺀 최대 {ncm:.1f}",
        f"초과 {n_over}행({n_over / len(x):.1%}) · {int((seg_a.n_over_normal_max > 0).sum())}/{nA}구간 · 최대 {np.abs(x).max():.1f}",
        f"구간 평균을 빼면 정상 최대({cur_max:.1f}) 초과 {int((np.abs(xc) > cur_max).sum())}행, "
        f"정상 최대+2σ({cur_max + 2 * sig:.0f}) 초과 {int((np.abs(xc) > cur_max + 2 * sig).sum())}행, "
        f"정상 '평균 뺀 최대'({ncm:.1f}) 초과 {int((np.abs(xc) > ncm).sum())}행 (σ={sig:.0f} = 수준-산포 창 산포 중앙); "
        f"평균을 안 빼면 +2σ 초과 {int((np.abs(x) > cur_max + 2 * sig).sum())}행, +3σ 초과 {int((np.abs(x) > cur_max + 3 * sig).sum())}행",
        "사후", NEU, f"{no_sim}. 진폭 √(2var)은 정상 범위라 '진폭 증가'가 아니라 극값 증가")
    for c, lab, pp in (("vib0_std", "상부 진동 std", "사전"), ("vib1_std", "하부 진동 std", "사전"),
                       ("amp", "진폭 √(2var)", "사전"), ("t_sec", "시각(초)", "사전")):
        r_a, p_a = spearmanr(seg_a.sine_r2, seg_a[c])
        nv = "—"
        if c != "t_sec":
            r_n, p_n = spearmanr(seg_n.sine_r2, seg_n[c])
            nv = f"rho={r_n:.3f} (p={p_n:.2g}, n={len(seg_n)})"
        add(f"R² vs {lab} (Spearman)", "이상 구간 안에서 사인 붕괴 정도와의 순위상관", nv,
            f"rho={r_a:.3f} (p={p_a:.3f}, n={nA})", "n=17이라 검정력 낮음", pp, NEU,
            no_sim + (". 기어 마모→진동→전류 경로의 직접 증거 여부" if c.startswith("vib") else ""))
    on = lambda s: float((np.abs(s / Q_CUR - np.round(s / Q_CUR)) < 1e-3).mean())  # noqa: E731
    fine = lambda s: float((np.abs(s * 1e6 - np.round(s * 1e6)) > 1e-3).mean())  # noqa: E731
    add("저장 형식", f"전류 {Q_CUR} 양자 격자 위 값 비율 · 진동 1e-6보다 세밀한 값 비율",
        f"전류 {on(normal.AI2_Current):.3f} · 진동 {fine(normal.AI0_Vibration):.3f}",
        f"전류 {on(abnormal.AI2_Current):.3f} · 진동 {fine(abnormal.AI0_Vibration):.3f}", "—", "사후", NEU,
        f"수집 사슬(양자화·포맷)이 달랐다는 직접 관찰. H5와 부합하지만 모사로 확인한 방향은 아님({no_sim})")
    add("등가 지터 크기", "R²=exp(−σφ²), σφ=2π·60Hz·σt 가정의 샘플 시각 σ(ms)", _dist(seg_n.jitter_ms_equiv),
        _dist(seg_a.jitter_ms_equiv), "—", "사전", NEU, "가능성 크기만 보임. iid 지터는 반송파를 남긴다(반송파 행 참고)")
    add("날짜·시간대 교란", "정상·이상 수집 시점", "07-12 00:00~01:17", "07-17 10:51~10:54", "—", "사전", NEU,
        "가이드북: 기어형 펌프·고장=기어 마모(진동 증가)·전류센서=펌프 전력선·PLC 수집. 하루씩이라 날짜 효과와 분리 불가")

    # --- 결론: 관찰 사실만 ---
    r_v0, p_v0 = spearmanr(seg_a.sine_r2, seg_a.vib0_std)
    r_v1, p_v1 = spearmanr(seg_a.sine_r2, seg_a.vib1_std)
    r_am, p_am = spearmanr(seg_a.sine_r2, seg_a.amp)
    # 문구는 계산값이 조건을 만족할 때만 단정한다 (조건은 개정 때 고정)
    n_c = int((np.abs(xc) > cur_max).sum())
    in_rng = seg_n.amp.min() <= seg_a.amp.median() <= seg_n.amp.max()
    facts = [
        f"0.6Hz 반송파 {'약화' if seg_a.car_amp.median() < seg_n.car_amp.min() else '유지'}: car_amp 정상 중앙 "
        f"{seg_n.car_amp.median():.0f} → 이상 {seg_a.car_amp.median():.0f} "
        f"({'소실 아님' if p_car < 0.05 else '소실과 구분 불가'}: 흰 산포 대조 q95 초과 {nq}/{nA}구간, 우연 기대 "
        f"{0.05 * nA:.2f}, 이항 p={p_car:.1e}; 나머지 {nA - nq}구간은 흰 산포 수준과 구분 불가)",
        f"구간 수준 이동: 구간 평균 최대 {seg_a['mean'].max():.0f} (정상 |평균| 최대 {nmax:.0f})",
        f"진폭 √(2var)은 정상 범위 {'안' if in_rng else '밖'}: 이상 중앙 {seg_a.amp.median():.1f} vs 정상 {seg_n.amp.median():.1f}",
        f"극값 증가는 수준 이동 + 가법 흰 산포(σ≈{sig:.0f})로 {'대부분 설명' if n_c * 2 <= n_over else '설명 안 됨'}: "
        f"정상 최대 초과 {n_over}행 중 구간 평균을 빼면 {n_c}행, +2σ 초과 {int((np.abs(xc) > cur_max + 2 * sig).sum())}행",
        f"진동과 {'무상관' if min(p_v0, p_v1) > 0.05 else '상관'}: R² vs 상부/하부 진동 Spearman {r_v0:.2f}/{r_v1:.2f} "
        f"(p={p_v0:.2f}/{p_v1:.2f})",
        f"진폭과 {'양의 상관' if p_am < 0.05 and r_am > 0 else '유의한 양의 상관 없음'}: R² vs √(2var) Spearman "
        f"{r_am:.2f} (p={p_am:.3f})"]
    add("결론", "단일 가설로 분리 불가", "—", "—", "—", "—", {h: "-" for h in HYP}, " / ".join(facts))
    return pd.DataFrame(rows)


def figure(out, xa, xn, seg_full, fp, all_series, ok):
    """대표 구간 잔차 vs 위상: 정상, 이상(대표 + 전체), 지터 모사(H1), 빠른 부하 변동 접힘 모사(H4)."""
    L = seg_full[seg_full.r2_M0.notna()]
    rep = int(L.iloc[(L.r2_M0 - L.r2_M0.median()).abs().argmin()].segment)
    n50 = {s: x for s, x in xn.items() if len(x) == len(xa[rep])}
    nr2 = _m0_detail(np.stack(list(n50.values())))["r2"]
    nrep = list(n50)[int(np.abs(nr2 - np.median(nr2)).argmin())]

    def resid_phase(X):
        d = _m0_detail(np.atleast_2d(X))
        ph = np.degrees(np.mod(d["phase"] + np.pi / 2, 2 * np.pi)) - 90   # fit 영교차(상승) = 0°
        return ph, d["res"] / d["R"][:, None], d

    def fp_rows(sel):
        return fp[sel][["rho4s", "rho4t"]].to_numpy(float)

    fig, axes = plt.subplots(2, 2, figsize=(10, 6.8), sharex=True)
    bins = np.linspace(-90, 270, 13)
    panels = [(xn[nrep][None], None, (fp.tag == "normal") & (fp.key == nrep), f"정상 구간 {nrep}"),
              (xa[rep][None], list(xa.values()), (fp.tag == "anom") & (fp.key == rep),
               f"이상 구간 {rep} (회색: 길이≥{MIN_FIT} 이상 구간 {len(xa)}개)"),
              (None, "jitter", fp.simkey == f"{rep}|jitter", f"양성 대조 H1: 지터 (구간 {rep}에 R² 맞춤)"),
              (None, "am_fast", fp.simkey == f"{rep}|am_fast", f"양성 대조 H4: 빠른 부하 변동 접힘 (구간 {rep}에 R² 맞춤)")]
    for ax, (X, extra, sel, title) in zip(axes.ravel(), panels):
        if isinstance(extra, str):
            X = np.stack([all_series[i] for i in fp.index[sel]])
            if not ok[(rep, extra)]:
                title += " — 맞춤 실패"
            extra = None
        for x in extra or []:
            ph, r, _ = resid_phase(x[None])
            ax.plot(ph.ravel(), r.ravel(), ".", ms=3, color="#b4b2a9", alpha=.6)
        ph, r, d = resid_phase(X)
        ax.plot(ph.ravel(), r.ravel(), "o", ms=3.5 if len(X) == 1 else 2, color="#2a78d6",
                alpha=1 if len(X) == 1 else .35, label="M0 잔차 / 진폭")
        k = np.digitize(ph.ravel(), bins) - 1
        m = np.array([np.abs(r.ravel()[k == i]).mean() if (k == i).any() else np.nan for i in range(len(bins) - 1)])
        ax.stairs(m, bins, baseline=None, color="#eb6834", lw=2, label="|잔차| 구간 평균")
        ax.axhline(0, color="#52514e", lw=.6)
        for v in (0, 180):
            ax.axvline(v, color="#52514e", lw=.6, ls=":")
        rs = fp_rows(sel)
        r2 = d["r2"].mean() if len(X) > 1 else d["r2"][0]
        f0 = f", f={d['f'][0]:.3f}Hz" if len(X) == 1 else ""
        med = " (중앙값)" if len(X) > 1 else ""
        r4t = _nan(np.median, rs[:, 1])
        ax.set_title(f"{title}\nR²={r2:.3f}{f0}, rho4s={_nan(np.median, rs[:, 0]):.2f}, "
                     f"rho4t={'위상 폭<360°' if not np.isfinite(r4t) else f'{r4t:.2f}'}{med}", fontsize=9)
    for ax in axes[1]:
        ax.set_xlabel("M0 적합 위상 (°, 0·180 = 적합 사인 영교차 = 기울기 최대)")
        ax.set_xticks([-90, 0, 90, 180, 270])
    for ax in axes[:, 0]:
        ax.set_ylabel("잔차 / 적합 진폭")
    axes[0, 0].legend(fontsize=8, loc="upper right")
    fig.suptitle("지터면 영교차(0°·180°)에서, 빠른 부하 변동이면 봉우리(±90°)에서 잔차가 커진다 "
                 "(이상 구간의 M0는 0.6Hz 반송파가 아닌 느린 성분에 맞음, rho4s·rho4t는 M5 적합 기준)", fontsize=9)
    fig.tight_layout()
    fig.savefig(out / "fig_anomaly_day_residual.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    import time

    t = time.time()
    res = run(OUT, DEFAULT_ROOT, load_vendor())
    with pd.option_context("display.width", 250, "display.max_colwidth", 60):
        print(res[["검사", "이상_값"] + list(HCOL.values())].to_string())
    print(f"{time.time() - t:.1f}s")
