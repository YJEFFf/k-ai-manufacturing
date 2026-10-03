"""이상 사건 안 추세 분석 — 냉간 기동(예열)·진행성 고장·정상상태 고장 가설 비교.

질문
 1. 이상 21기록(2022-07-17 일 10:51~10:53, 2분 46초)을 시간순으로 놓았을 때 정상 기준 대비 이탈 정도가
    줄어드는가 (a: 냉간 기동·예열 — 작동유 저온 고점도 → 흡입 캐비테이션 등이 데워지며 가라앉음),
    커지는가 (b: 진행성 고장), 변화가 없는가 (c: 정상상태 고장)?
 2. 이상 파일 첫 기록·첫 행부터 이상인가? 사건 안에서 정상 범위로 돌아오는 기록이 있는가?
 3. 정상 77분(2022-07-12 화 00:00~01:17)은 정상상태(stationary) 기준선으로 쓸 수 있는가?
 4. 정상·이상의 운전 조건(요일·시각·계측 설정) 차이는 데이터로 분리되는가?

방법
 - 입력: cases/common.py load_both(matched=True). 저장 정밀도를 맞춰 형식 누수를 지운 자료.
 - 기록별 특징 13종: case_table 9종 + 전류 RMS(std) + 전류 실효값(영점 기준 sqrt(mean x²))
   + 상/하부 진동 SD 비 + 전류 평균/RMS(직류 비).
 - 이탈 정도: 정상 600기록 분포 대비 robust z = (x − 중앙값) / (1.4826·MAD).
   척도형 특징(SD·진폭·RMS·비율)은 로그, 사인 R²는 log(1−R²)에서 계산한다(척도 모수는 곱으로 변하므로
   위·아래 이탈을 같은 무게로 보려면 로그가 맞다). 추세의 대상은 |z| = 정상에서 떨어진 거리.
 - 추세 검정: Spearman ρ, Theil–Sen 기울기(분당), Mann–Kendall(직접 구현, 동률 보정·연속성 보정),
   앞 7기록 vs 뒤 7기록 Mann–Whitney(정확 검정). 특징 13종을 한 가족으로 Holm 보정.
   21기록 전체와 10행 이상 17기록을 따로 낸다(10행 미만은 R²·lag1·상관이 불안정; 3행 기록은 사인 3모수
   적합이라 R²=1이 자동으로 나온다).
 - 검정력: 실제 기록 시각에 선형 추세 + 정규 잡음을 넣은 모의실험(seed 고정)으로 MK 80% 검정력에 필요한
   '사건 전체 변화량(잡음 SD 배수)'을 구하고, 특징별 잡음 크기로 환산한다.
 - 첫 기록 판정에는 길이를 맞춘 정상 기준(정상 기록을 같은 행 수로 자른 특징 분포)을 함께 쓴다.
   짧은 기록의 특징을 50행 기록 분포와 비교하면 길이 효과를 이상으로 착각하기 때문이다.

출력 (domain/outputs/)
 - 02_event_trend.json           : 전체 결과
 - 02_event_trend.csv            : 추세 검정표 (부분집합 × 대상 × 특징)
 - 02_event_trend_records.csv    : 이상 21기록 특징·z·정상 범위 여부
 - 02_event_trend_normal_bins.csv: 정상 10분 구간 중앙값(특징별 z·원값)
 - 02_event_trend_normal_bins2min.csv: 정상 2분 구간 중앙값(운전 구간 탐지용)
 - 02_event_trend_summary.md     : 요약
실행: PYTHONIOENCODING=utf-8 python 02_event_trend.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cases"))
from common import SENSORS, case_table, load_both  # noqa: E402

OUT = HERE / "outputs"
SEED = 20220717
MIN_LEN = 10          # 안정 특징을 위한 최소 행 수
K = 7                 # 앞·뒤 비교 기록 수
ALPHA = 0.05
N_SIM = 4000          # 검정력 모의실험 반복 수
CUR = SENSORS[2]

# 특징 이름: (한국어 이름, z 계산 척도)
FEATS = {
    "vib_upper_sd": ("상부 진동 SD", "log"),
    "vib_lower_sd": ("하부 진동 SD", "log"),
    "vib_sd_ratio": ("상/하부 진동 SD 비", "log"),
    "upper_lower_corr": ("상·하부 진동 상관", "raw"),
    "vib_upper_lag1": ("상부 진동 lag-1", "raw"),
    "vib_lower_lag1": ("하부 진동 lag-1", "raw"),
    "cur_rms": ("전류 RMS(std)", "log"),
    "cur_true_rms": ("전류 실효값(영점 기준)", "log"),
    "cur_amp": ("전류 사인 진폭(0.6Hz)", "log"),
    "cur_offset_ratio": ("전류 절편/진폭", "raw"),
    "cur_dc_ratio": ("전류 평균/RMS", "raw"),
    "cur_resid_ratio": ("전류 잔차/진폭", "log"),
    "cur_sine_r2": ("전류 사인 R²", "log1m"),
}
F = list(FEATS)
VIB = [f for f in F if f.startswith(("vib_", "upper_"))]
CURF = [f for f in F if f.startswith("cur_")]
# 종합 이탈 지수(|z| 중앙값): 전체·진동 계열·전류 계열. 검정 가족(Holm) 밖의 보조 지표다.
COMPOSITES = {"absz_median": ("종합 이탈(|z| 중앙값, 13종)", F),
              "absz_vib": ("진동 계열 이탈(|z| 중앙값, 6종)", VIB),
              "absz_cur": ("전류 계열 이탈(|z| 중앙값, 7종)", CURF)}
NAME = {**{f: v[0] for f, v in FEATS.items()}, **{c: v[0] for c, v in COMPOSITES.items()}}


# ───────────────────────────── 특징·기준 ─────────────────────────────
def record_features(df: pd.DataFrame) -> pd.DataFrame:
    """case_table 특징 + 전류 RMS·실효값·직류 비·진동 SD 비·기록 중앙 시각(분).

    교류 순시값의 물리적 실효값은 영점 기준 sqrt(mean(x²))다. std는 기록 평균을 뺀 값이라
    직류 성분(평균 이동)이 생기면 둘이 갈라진다. 둘 다 둔다.
    """
    ct = case_table(df).set_index("rec")
    g = df.groupby("rec")[CUR]
    ct["cur_rms"] = g.std(ddof=0)
    ct["cur_true_rms"] = np.sqrt(g.apply(lambda s: float(np.mean(np.square(s)))))
    ct["cur_peak_abs"] = g.apply(lambda s: float(np.abs(s).max()))   # 보조(검정 대상 아님): 길이 의존
    ct["cur_dc_ratio"] = g.mean() / ct["cur_rms"].replace(0, np.nan)
    ct["vib_sd_ratio"] = (ct.vib_upper_sd / ct.vib_lower_sd).replace([np.inf, -np.inf], np.nan)
    ct["t_mid_min"] = (ct.t0 + (ct.n - 1) * 0.05) / 60.0
    return ct.reset_index()


def tf(name: str, x) -> np.ndarray:
    """z 계산 척도로 변환. 0 SD(1행 기록 등)는 1e-6으로 바닥을 깐다."""
    x = np.asarray(x, float)
    kind = FEATS[name][1]
    with np.errstate(divide="ignore", invalid="ignore"):
        if kind == "log":
            return np.log(np.clip(x, 1e-6, None))
        if kind == "log1m":
            return np.log(np.clip(1.0 - x, 1e-6, None))
    return x


def reference(ref: pd.DataFrame) -> dict:
    """정상 기록 분포의 중앙값·robust 척도(변환 척도)와 1·99% 분위(원 척도)."""
    out = {}
    for f in F:
        raw = ref[f].dropna().to_numpy()
        v = tf(f, raw)
        med = float(np.median(v))
        mad = 1.4826 * float(np.median(np.abs(v - med)))
        out[f] = dict(med=med, scale=max(mad, 1e-9), q01=float(np.quantile(raw, 0.01)),
                      q99=float(np.quantile(raw, 0.99)), n=int(raw.size), sorted=np.sort(raw))
    return out


def zscore(ref: dict, f: str, x) -> np.ndarray:
    return (tf(f, x) - ref[f]["med"]) / ref[f]["scale"]


def pct(ref: dict, f: str, x: float) -> float:
    """정상 분포에서 x의 백분위(중간 순위, 0~100)."""
    s = ref[f]["sorted"]
    if not np.isfinite(x):
        return np.nan
    return 100.0 * (np.searchsorted(s, x, "left") + np.searchsorted(s, x, "right")) / 2 / s.size


def inside(ref: dict, f: str, x: float):
    if not np.isfinite(x):
        return None
    return bool(ref[f]["q01"] <= x <= ref[f]["q99"])


def truncated_reference(normal: pd.DataFrame, L: int) -> dict:
    """길이 맞춤 기준: L행 이상인 정상 기록을 앞 L행으로 잘라 특징 분포를 만든다."""
    size = normal.groupby("rec").pos.transform("size")
    return reference(record_features(normal[(size >= L) & (normal.pos < L)]))


# ───────────────────────────── 추세 검정 ─────────────────────────────
def mann_kendall(y) -> dict:
    """Mann–Kendall 추세 검정(양측). 동률 보정 분산, 연속성 보정 Z."""
    y = np.asarray(y, float)
    n = y.size
    iu = np.triu_indices(n, 1)
    s = float(np.sign(y[iu[1]] - y[iu[0]]).sum())
    _, c = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - (c * (c - 1) * (2 * c + 5)).sum()) / 18.0
    z = 0.0 if s == 0 else (s - np.sign(s)) / np.sqrt(var)
    return dict(S=s, Z=float(z), p=float(2 * stats.norm.sf(abs(z))), tau=s / (n * (n - 1) / 2))


def lag1(x) -> float:
    x = np.asarray(x, float) - np.mean(x)
    d = (x * x).sum()
    return float((x[1:] * x[:-1]).sum() / d) if d > 0 else np.nan


def trend(t, y) -> dict:
    """시간 t(분)에 대한 y의 단조 추세 묶음."""
    t, y = np.asarray(t, float), np.asarray(y, float)
    ok = np.isfinite(y)
    t, y = t[ok], y[ok]
    rho, p_rho = stats.spearmanr(t, y)
    ts = stats.theilslopes(y, t, alpha=0.95)
    mk = mann_kendall(y)
    front, back = y[:K], y[-K:]
    mw = stats.mannwhitneyu(back, front, alternative="two-sided", method="exact")
    resid = y - (ts.intercept + ts.slope * t)
    # 연속 기록은 한 사건의 조각이라 독립이 아니다. 추세 제거 잔차의 lag-1 자기상관 r1로
    # MK 분산을 AR(1) 팽창계수 (1+r1)/(1−r1)만큼 키운 보수적 p도 함께 낸다(r1≤0이면 보정 없음).
    r1 = lag1(resid)
    vif = (1 + r1) / (1 - r1) if np.isfinite(r1) and r1 > 0 else 1.0
    z_ar1 = mk["Z"] / np.sqrt(vif)
    return dict(
        n=int(y.size), spearman_rho=float(rho), spearman_p=float(p_rho),
        ts_slope_per_min=float(ts.slope), ts_lo=float(ts.low_slope), ts_hi=float(ts.high_slope),
        mk_S=mk["S"], mk_tau=mk["tau"], mk_Z=mk["Z"], mk_p=mk["p"],
        mk_p_ar1=float(2 * stats.norm.sf(abs(z_ar1))), ar1_vif=float(vif),
        front_median=float(np.median(front)), back_median=float(np.median(back)),
        mw_U_back=float(mw.statistic), mw_p=float(mw.pvalue),
        mw_rank_biserial=float(2 * mw.statistic / (K * K) - 1),   # >0: 뒤 7기록이 큼
        resid_robust_sd=float(1.4826 * np.median(np.abs(resid - np.median(resid)))),
        resid_lag1=r1,
        t_span_min=float(t.max() - t.min()),
    )


def verdict(tau: float, p: float, p_holm: float, p_ar1_holm: float = 0.0) -> str:
    """|z|(이탈 정도) 추세를 가설 (a)(b)(c)로 읽는다. 1차 기준은 MK + Holm, AR(1) 보정은 견고성 표시."""
    if p_holm < ALPHA:
        base = "(a) 감소 — 예열·수렴 부합" if tau < 0 else "(b) 증가 — 진행성 부합"
        return base + (" (AR1 보정 Holm 후 비유의 → 경향 수준)" if p_ar1_holm >= ALPHA else "")
    if p < ALPHA:
        return ("(a)" if tau < 0 else "(b)") + " 쪽 경향 — Holm 후 비유의"
    return "(c) 추세 없음과 부합 — (a)(b) 배제 못함"


def mk_power(t, rng, alphas=(ALPHA, ALPHA / len(F))) -> dict:
    """실제 기록 시각에서 y = Δ·(t 정규화) + N(0,1) 모의실험. MK 검정력 80%에 필요한 Δ(잡음 SD 배수)."""
    t = np.asarray(t, float)
    u = (t - t.min()) / (t.max() - t.min())
    n = u.size
    iu = np.triu_indices(n, 1)
    sd = np.sqrt(n * (n - 1) * (2 * n + 5) / 18.0)
    deltas = np.round(np.arange(0, 8.01, 0.1), 2)
    curve = {a: [] for a in alphas}
    for d in deltas:
        y = d * u + rng.standard_normal((N_SIM, n))
        s = np.sign(y[:, iu[1]] - y[:, iu[0]]).sum(1)
        z = (s - np.sign(s)) / sd
        p = 2 * stats.norm.sf(np.abs(z))
        for a in alphas:
            curve[a].append(float((p < a).mean()))
    need = {}
    for a in alphas:
        pw = np.array(curve[a])
        hit = np.nonzero(pw >= 0.8)[0]
        need[f"alpha_{a:.4f}"] = float(deltas[hit[0]]) if hit.size else None
    # Spearman 해석적 근사(Fieller: SE = sqrt(1.06/(n−3))): 80% 검정력의 최소 |ρ|
    rho80 = {f"alpha_{a:.4f}": float(np.tanh((stats.norm.isf(a / 2) + stats.norm.isf(0.2)) * np.sqrt(1.06 / (n - 3))))
             for a in alphas}
    rho_crit = {f"alpha_{a:.4f}": float(np.tanh(stats.norm.isf(a / 2) * np.sqrt(1.06 / (n - 3)))) for a in alphas}
    return dict(n=n, t_span_min=float(t.max() - t.min()), delta80_noise_sd=need,
                spearman_rho_crit=rho_crit, spearman_rho80=rho80)


# ───────────────────────────── 겉보기 주파수 ─────────────────────────────
FGRID = np.arange(0.02, 5.0001, 0.005)   # Hz (10Hz 표본의 나이퀴스트 5Hz까지)


def apparent_freq(x):
    """절편+사인+코사인을 주파수 격자 전체에 한 번에 적합해 R² 최대 주파수(Hz)와 그 R²."""
    x = np.asarray(x, float)
    k = np.arange(x.size)
    w = 2 * np.pi * FGRID[:, None] / 10.0 * k[None, :]
    X = np.stack([np.ones_like(w), np.sin(w), np.cos(w)], axis=2)          # (F, n, 3)
    xtx = np.einsum("fni,fnj->fij", X, X) + 1e-9 * np.eye(3)
    b = np.linalg.solve(xtx, np.einsum("fni,n->fi", X, x)[..., None])[..., 0]
    r = x[None, :] - np.einsum("fni,fi->fn", X, b)
    sst = ((x - x.mean()) ** 2).sum()
    r2 = 1 - (r ** 2).sum(1) / sst
    i = int(np.argmax(r2))
    return float(FGRID[i]), float(r2[i])


# ───────────────────────────── 보조 ─────────────────────────────
def holm(p) -> np.ndarray:
    p = np.asarray(p, float)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    if ok.any():
        out[ok] = multipletests(p[ok], method="holm")[1]
    return out


def clean(o):
    """JSON 직렬화: numpy → 파이썬, NaN → None, 실수는 유효숫자 6자리."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not (isinstance(v, np.ndarray) and k == "sorted")}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        o = float(o)
        return None if not np.isfinite(o) else float(f"{o:.6g}")
    if isinstance(o, np.bool_):
        return bool(o)
    return o


# ───────────────────────────── 본 분석 ─────────────────────────────
def section_event(nf, af, ref600):
    """1·2. 이상 사건 안 추세와 가설 판정."""
    rows = []
    for f in F:
        af[f"z_{f}"] = zscore(ref600, f, af[f])
        af[f"absz_{f}"] = af[f"z_{f}"].abs()
    for c, (_, members) in COMPOSITES.items():
        af[c] = af[[f"absz_{f}" for f in members]].median(axis=1)
    subsets = {"all21": af, f"ge{MIN_LEN}": af[af.n >= MIN_LEN]}
    for sname, d in subsets.items():
        for target in ("absz", "raw"):
            block = []
            for f in F + (list(COMPOSITES) if target == "absz" else []):
                col = f if (target == "raw" or f in COMPOSITES) else f"absz_{f}"
                r = trend(d.t_mid_min.to_numpy(), d[col].to_numpy())
                block.append(dict(subset=sname, target=target, feature=f,
                                  name=NAME[f], **r))
            # Holm: 같은 부분집합·대상 안 특징 13종이 한 가족(종합 지수는 가족 밖)
            fam = [i for i, b in enumerate(block) if b["feature"] in FEATS]
            for key in ("spearman_p", "mk_p", "mk_p_ar1", "mw_p"):
                adj = holm([block[i][key] for i in fam])
                for j, i in enumerate(fam):
                    block[i][key + "_holm"] = float(adj[j])
                for b in block:
                    b.setdefault(key + "_holm", np.nan)
            for b in block:
                if target == "absz":
                    comp = not np.isfinite(b["mk_p_holm"])      # 종합 지수는 가족 밖 → 원 p
                    b["verdict"] = verdict(b["mk_tau"], b["mk_p"], b["mk_p"] if comp else b["mk_p_holm"],
                                           b["mk_p_ar1"] if comp else b["mk_p_ar1_holm"])
                    b["start_absz_median"] = b["front_median"]
            rows += block
    return pd.DataFrame(rows)


def section_power(af, tests, rng):
    """검정력: MK 80%에 필요한 사건 전체 변화량을 특징별 |z| 단위·초기값 대비 비율로 환산."""
    out = {}
    for sname, d in (("all21", af), (f"ge{MIN_LEN}", af[af.n >= MIN_LEN])):
        pw = mk_power(d.t_mid_min.to_numpy(), rng)
        per = {}
        for f in F + list(COMPOSITES):
            r = tests[(tests.subset == sname) & (tests.target == "absz") & (tests.feature == f)].iloc[0]
            per[f] = {}
            for a, dl in pw["delta80_noise_sd"].items():
                need = dl * r.resid_robust_sd if dl is not None else np.nan
                per[f][a] = dict(change_needed_absz=need,
                                 share_of_front_median=need / r.front_median if r.front_median > 0 else np.nan)
        out[sname] = dict(**pw, per_feature=per)
    return out


def section_onset(normal, abnormal, af, ref600):
    """3. 사건 시작: 첫 기록·첫 행이 정상 범위 밖인가, 사건 안에서 정상 범위로 돌아오는 기록이 있는가."""
    refs_len = {int(L): truncated_reference(normal, int(L)) for L in sorted(af.n.unique())}
    rec_rows = []
    for _, r in af.iterrows():
        rl = refs_len[int(r.n)]
        row = dict(rec=int(r.rec), n=int(r.n), t_mid_min=r.t_mid_min)
        for f in F:
            row[f"in600_{f}"] = inside(ref600, f, r[f])
            row[f"inlen_{f}"] = inside(rl, f, r[f])
            row[f"pctlen_{f}"] = pct(rl, f, r[f])
            row[f"zlen_{f}"] = float(zscore(rl, f, [r[f]])[0])
        vals = [row[f"inlen_{f}"] for f in F if row[f"inlen_{f}"] is not None]
        row["n_feat_inside_len"] = int(sum(vals))
        row["n_feat_eval"] = len(vals)
        row["absz_len_median"] = float(np.nanmedian(np.abs([row[f"zlen_{f}"] for f in F])))
        rec_rows.append(row)
    rec = pd.DataFrame(rec_rows)

    # 첫 기록(rec 0)
    r0 = af.iloc[0]
    first_rec = dict(rec=int(r0.rec), n=int(r0.n), start=str(abnormal.TimeStamp.iloc[0]), features={})
    for f in F:
        first_rec["features"][f] = dict(
            value=r0[f], z600=float(zscore(ref600, f, [r0[f]])[0]), pct600=pct(ref600, f, r0[f]),
            pct_len=pct(refs_len[int(r0.n)], f, r0[f]), inside_len_1_99=inside(refs_len[int(r0.n)], f, r0[f]),
            inside600_1_99=inside(ref600, f, r0[f]))
    first_rec["n_feat_outside_len"] = int(sum(v["inside_len_1_99"] is False for v in first_rec["features"].values()))
    first_rec["n_feat_outside_600"] = int(sum(v["inside600_1_99"] is False for v in first_rec["features"].values()))

    # 첫 기록의 행 하나하나: 정상 전체 행 / 정상 기록 첫 행 분포 대비 백분위
    rows_all = {s: np.sort(normal[s].to_numpy()) for s in SENSORS}
    rows_pos0 = {s: np.sort(normal.loc[normal.pos == 0, s].to_numpy()) for s in SENSORS}
    p_of = lambda arr, x: 100.0 * (np.searchsorted(arr, x, "left") + np.searchsorted(arr, x, "right")) / 2 / arr.size
    normal_range = {s: dict(min=float(normal[s].min()), max=float(normal[s].max()),
                            q01=float(normal[s].quantile(0.01)), q99=float(normal[s].quantile(0.99))) for s in SENSORS}
    first_rows = []
    for i in range(int(r0.n)):
        rr = abnormal.iloc[i]
        d = dict(row=i, ts=str(rr.TimeStamp))
        for s in SENSORS:
            pa, p0 = p_of(rows_all[s], rr[s]), p_of(rows_pos0[s], rr[s])
            d[s] = dict(value=float(rr[s]), pct_all_rows=pa, pct_first_rows=p0, outside_1_99=bool(pa < 1 or pa > 99),
                        outside_normal_min_max=bool(rr[s] < normal_range[s]["min"] or rr[s] > normal_range[s]["max"]))
        # 상·하부 진동 동시 크기: 정상 행에서 (|상부|/SD상, |하부|/SD하) 둘 다 이 값 이상인 비율
        su, sl = normal.AI0_Vibration.std(), normal.AI1_Vibration.std()
        ju, jl = abs(rr.AI0_Vibration) / su, abs(rr.AI1_Vibration) / sl
        d["joint_vib_exceed_share"] = float(((normal.AI0_Vibration.abs() / su >= ju)
                                             & (normal.AI1_Vibration.abs() / sl >= jl)).mean())
        first_rows.append(d)

    # 사건 안 정상 복귀: 특징별 정상 1~99% 안에 드는 기록 수
    back = {}
    for f in F:
        back[f] = dict(name=FEATS[f][0],
                       inside600_all21=int(rec[f"in600_{f}"].fillna(False).sum()),
                       inside_len_all21=int(rec[f"inlen_{f}"].fillna(False).sum()),
                       inside600_ge10=int(rec.loc[rec.n >= MIN_LEN, f"in600_{f}"].fillna(False).sum()),
                       inside_len_ge10=int(rec.loc[rec.n >= MIN_LEN, f"inlen_{f}"].fillna(False).sum()),
                       recs_inside_len=rec.loc[rec[f"inlen_{f}"].fillna(False).astype(bool), "rec"].tolist())
    wave = ["cur_sine_r2", "cur_resid_ratio"]
    ge = rec[rec.n >= MIN_LEN]
    peak_lim = max(abs(normal_range[CUR]["min"]), abs(normal_range[CUR]["max"]))
    summary = dict(
        records_all_features_inside_len=rec.loc[rec.n_feat_inside_len == rec.n_feat_eval, "rec"].tolist(),
        records_majority_inside_len=rec.loc[rec.n_feat_inside_len > rec.n_feat_eval / 2, "rec"].tolist(),
        ge10_current_waveform_inside_len=int((ge[[f"inlen_{f}" for f in wave]].fillna(False).all(axis=1)).sum()),
        ge10_records=int(len(ge)),
        # 정상 20,000행 어디에도 없던 크기의 전류 순시값(|x| > 정상 최대)이 나온 기록
        normal_current_abs_max=peak_lim,
        records_current_peak_above_normal_max=af.loc[af.cur_peak_abs > peak_lim, "rec"].tolist(),
        current_peak_by_record=af[["rec", "cur_peak_abs"]].to_dict("records"),
    )
    return rec, dict(normal_row_range=normal_range, first_record=first_rec, first_record_rows=first_rows,
                     back_to_normal=back, back_summary=summary)


def low_activity_segment(nf: pd.DataFrame, t_start: pd.Timestamp):
    """정상 77분 안의 저진동·저부하 구간 탐지.

    10행 이상 기록의 2분 구간 중앙값에서 상부 진동 SD가 전체 중앙값의 0.6배 미만인 구간이
    가장 길게 이어지는 범위를 고른다(규칙은 정상 자료로만 정함, 이상 자료는 보지 않음).
    """
    d = nf[nf.n >= MIN_LEN].copy()
    d["bin2"] = (d.t_mid_min // 2).astype(int) * 2
    b2 = d.groupby("bin2").agg(n_records=("n", "size"), vib_upper_sd=("vib_upper_sd", "median"),
                               vib_lower_sd=("vib_lower_sd", "median"), upper_lower_corr=("upper_lower_corr", "median"),
                               cur_amp=("cur_amp", "median"), cur_true_rms=("cur_true_rms", "median"),
                               cur_sine_r2=("cur_sine_r2", "median"))
    thr = 0.6 * float(d.vib_upper_sd.median())
    low = [int(b) for b in b2.index[b2.vib_upper_sd < thr]]
    runs, cur = [], []
    for b in low:
        if cur and b != cur[-1] + 2:
            runs.append(cur)
            cur = []
        cur.append(b)
    if cur:
        runs.append(cur)
    seg = None
    if runs:
        best = max(runs, key=len)
        s, e = best[0], best[-1] + 2
        seg = dict(start_min=s, end_min=e, threshold_vib_upper_sd=thr,
                   clock_start=str((t_start + pd.Timedelta(minutes=s)).time())[:8],
                   clock_end=str((t_start + pd.Timedelta(minutes=e)).time())[:8])
    return b2.reset_index(), seg


def section_normal(nf, af, ref600, t_start):
    """4. 정상 77분 안정성: 시간 추세·10분 구간 중앙값·파일 시작 첫 10기록 vs 나머지·운전 구간(생산/저부하)."""
    nf = nf.sort_values("t_mid_min").reset_index(drop=True)
    for f in F:
        nf[f"z_{f}"] = zscore(ref600, f, nf[f])
    for c, (_, members) in COMPOSITES.items():
        nf[c] = nf[[f"z_{f}" for f in members]].abs().median(axis=1)
    nf["bin10"] = (nf.t_mid_min // 10).astype(int) * 10
    bins2, seg = low_activity_segment(nf, t_start)
    nf["regime"] = "생산"
    if seg:
        nf.loc[nf.t_mid_min.between(seg["start_min"], seg["end_min"], inclusive="left"), "regime"] = "저부하"
    ab_ge = af[af.n >= MIN_LEN]
    res, bins = [], []
    for f in F + list(COMPOSITES):
        zc = f"z_{f}" if f in FEATS else f
        d = nf[np.isfinite(nf[zc])]
        rho, p = stats.spearmanr(d.t_mid_min, d[zc])
        dg = d[d.n >= MIN_LEN]
        rho10, p10 = stats.spearmanr(dg.t_mid_min, dg[zc])
        ts = stats.theilslopes(dg[zc], dg.t_mid_min)
        span = float(dg.t_mid_min.max() - dg.t_mid_min.min())
        bm = dg.groupby("bin10")[zc].median()
        kw = stats.kruskal(*[g[zc].to_numpy() for _, g in dg.groupby("bin10")])
        first, rest = d.iloc[:10][zc], d.iloc[10:][zc]
        mw = stats.mannwhitneyu(first, rest, alternative="two-sided")
        # 생산 구간만(저부하 구간 제외)
        dp = dg[dg.regime == "생산"]
        rho_p, p_p = stats.spearmanr(dp.t_mid_min, dp[zc])
        bm_p = dp.groupby("bin10")[zc].median()
        dl = dg[dg.regime == "저부하"]
        ab_dev = float(ab_ge[f"absz_{f}"].median()) if f in FEATS else float(ab_ge[f].median())
        drift = float(abs(ts.slope) * span)
        res.append(dict(
            feature=f, name=NAME[f],
            spearman_rho_all600=float(rho), spearman_p_all600=float(p),
            spearman_rho_ge10=float(rho10), spearman_p_ge10=float(p10),
            ts_slope_z_per_10min=float(ts.slope * 10), drift_z_over_span=drift,
            bin_median_range_z=float(bm.max() - bm.min()), kruskal_p=float(kw.pvalue),
            first10_median_z=float(first.median()), rest_median_z=float(rest.median()),
            first10_vs_rest_p=float(mw.pvalue), first10_rank_biserial=float(2 * mw.statistic / (len(first) * len(rest)) - 1),
            abnormal_ge10_median_absz=ab_dev,
            drift_over_abnormal=drift / ab_dev if ab_dev > 0 else np.nan,
            bin_range_over_abnormal=float(bm.max() - bm.min()) / ab_dev if ab_dev > 0 else np.nan,
            stable=bool(abs(rho10) < 0.2 and float(bm.max() - bm.min()) < 1.0),
            prod_spearman_rho=float(rho_p), prod_spearman_p=float(p_p),
            prod_bin_median_range_z=float(bm_p.max() - bm_p.min()),
            prod_stable=bool(abs(rho_p) < 0.2 and float(bm_p.max() - bm_p.min()) < 1.0),
            prod_median_raw=float(dp[f].median()) if f in FEATS else float(dp[zc].median()),
            low_median_raw=float(dl[f].median()) if (f in FEATS and len(dl)) else np.nan,
            low_minus_prod_z=float(dl[zc].median() - dp[zc].median()) if len(dl) else np.nan,
        ))
        for b, v in bm.items():
            bins.append(dict(feature=f, bin_start_min=int(b), median_z=float(v),
                             median_raw=float(dg.loc[dg.bin10 == b, f].median()) if f in FEATS else float(v),
                             n_records=int((dg.bin10 == b).sum())))
    res = pd.DataFrame(res)
    fam = res.feature.isin(F)
    for key in ("spearman_p_ge10", "first10_vs_rest_p", "kruskal_p"):
        res.loc[fam, key + "_holm"] = holm(res.loc[fam, key])
    first10 = nf.iloc[:10][["rec", "n", "t0", "cur_sine_r2", "cur_amp", "vib_upper_sd", "vib_lower_sd"]]
    # 이상 기록의 진동 크기를 정상 '저부하' 구간 분포와도 비교(후반 저진동 기록 해석용)
    low = nf[(nf.regime == "저부하") & (nf.n >= MIN_LEN)]
    vs_low = []
    for _, r in af[af.n >= MIN_LEN].iterrows():
        vs_low.append(dict(rec=int(r.rec), vib_upper_sd=r.vib_upper_sd, vib_lower_sd=r.vib_lower_sd,
                           pct_upper_in_low=100 * float((low.vib_upper_sd < r.vib_upper_sd).mean()) if len(low) else np.nan,
                           pct_lower_in_low=100 * float((low.vib_lower_sd < r.vib_lower_sd).mean()) if len(low) else np.nan,
                           cur_true_rms=r.cur_true_rms,
                           pct_true_rms_in_normal_ge10=100 * float((nf.loc[nf.n >= MIN_LEN, "cur_true_rms"] < r.cur_true_rms).mean())))
    regime = dict(segment=seg, n_records_low=int((nf.regime == "저부하").sum()),
                  n_records_prod=int((nf.regime == "생산").sum()),
                  abnormal_ge10_vs_low_regime=vs_low)
    return res, pd.DataFrame(bins), bins2, first10, regime


def section_conditions(normal, abnormal, nf, af):
    """5. 운전·계측 조건: 시각·요일 + 전류 겉보기 주파수(기록별 최적 사인)."""
    def freq_table(df, recs):
        out = []
        for k, g in df.groupby("rec"):
            if k in recs and len(g) >= MIN_LEN:
                f, r2 = apparent_freq(g[CUR].to_numpy())
                out.append(dict(rec=int(k), n=len(g), f_hat_hz=f, r2_at_f_hat=r2))
        return pd.DataFrame(out)
    fn = freq_table(normal, set(nf.rec))
    fa = freq_table(abnormal, set(af.rec))
    q = lambda s: dict(median=float(s.median()), q25=float(s.quantile(0.25)), q75=float(s.quantile(0.75)),
                       min=float(s.min()), max=float(s.max()))
    tsn, tsa = pd.to_datetime(normal.TimeStamp), pd.to_datetime(abnormal.TimeStamp)
    return dict(
        normal=dict(start=str(tsn.min()), end=str(tsn.max()), weekday=tsn.min().day_name(),
                    minutes=float((tsn.max() - tsn.min()).total_seconds() / 60), records=int(nf.shape[0]),
                    cur_f_hat_hz=q(fn.f_hat_hz), cur_r2_at_f_hat=q(fn.r2_at_f_hat),
                    share_f_hat_within_0p59_0p62=float(fn.f_hat_hz.between(0.59, 0.62).mean()),
                    cur_rms_median=float(nf.loc[nf.n >= MIN_LEN, "cur_rms"].median())),
        abnormal=dict(start=str(tsa.min()), end=str(tsa.max()), weekday=tsa.min().day_name(),
                      minutes=float((tsa.max() - tsa.min()).total_seconds() / 60), records=int(af.shape[0]),
                      cur_f_hat_hz=q(fa.f_hat_hz), cur_r2_at_f_hat=q(fa.r2_at_f_hat),
                      share_f_hat_within_0p59_0p62=float(fa.f_hat_hz.between(0.59, 0.62).mean()),
                      cur_rms_median=float(af.loc[af.n >= MIN_LEN, "cur_rms"].median()),
                      f_hat_by_record=fa.to_dict("records")),
        gap_days=float((tsa.min() - tsn.max()).total_seconds() / 86400),
    )


def main():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    normal, abnormal = load_both(matched=True)
    nf = record_features(normal)
    af = record_features(abnormal).sort_values("t_mid_min").reset_index(drop=True)
    ref600 = reference(nf)

    tests = section_event(nf, af, ref600)
    power = section_power(af, tests, rng)
    rec_tab, onset = section_onset(normal, abnormal, af, ref600)
    stab, bins, bins2, first10, regime = section_normal(nf, af, ref600, pd.to_datetime(normal.TimeStamp.iloc[0]))
    cond = section_conditions(normal, abnormal, nf, af)
    cond["oil_viscosity_note"] = viscosity_note()

    # 가설 판정표: 특징 × 부분집합 (|z| 대상)
    hyp = []
    for f in F + list(COMPOSITES):
        a = tests[(tests.target == "absz") & (tests.feature == f)].set_index("subset")
        hyp.append(dict(feature=f, name=a.iloc[0]["name"],
                        **{f"{s}_{k}": a.loc[s, k] for s in ("all21", f"ge{MIN_LEN}")
                           for k in ("spearman_rho", "mk_tau", "mk_p", "mk_p_holm", "mk_p_ar1", "mk_p_ar1_holm",
                                     "ts_slope_per_min", "ts_lo", "ts_hi",
                                     "front_median", "back_median", "mw_p", "verdict")}))
    hyp = pd.DataFrame(hyp)

    # 저장
    tests.to_csv(OUT / "02_event_trend.csv", index=False, encoding="utf-8-sig")
    rec_out = af[["rec", "n", "t0", "t_mid_min"] + F + ["cur_peak_abs"] + [f"z_{f}" for f in F] + list(COMPOSITES)].merge(
        rec_tab.drop(columns=["n", "t_mid_min"]), on="rec")
    rec_out.to_csv(OUT / "02_event_trend_records.csv", index=False, encoding="utf-8-sig")
    bins.to_csv(OUT / "02_event_trend_normal_bins.csv", index=False, encoding="utf-8-sig")
    bins2.to_csv(OUT / "02_event_trend_normal_bins2min.csv", index=False, encoding="utf-8-sig")

    result = dict(
        meta=dict(script="domain/02_event_trend.py", run_date=str(date.today()), seed=SEED, min_len=MIN_LEN,
                  k_front_back=K, alpha=ALPHA, n_sim=N_SIM, features={f: dict(name=v[0], z_scale=v[1]) for f, v in FEATS.items()},
                  z_definition="robust z = (tf(x) − median_normal600) / (1.4826·MAD_normal600); tf=log(척도형), log(1−R²)(R²)",
                  holm_family="같은 부분집합·대상(|z| 또는 원값)·검정 안 특징 13종"),
        reference_normal600={f: dict(median_raw=float(np.median(ref600[f]["sorted"])), q01=ref600[f]["q01"],
                                     q99=ref600[f]["q99"], n=ref600[f]["n"]) for f in F},
        event_trend_tests=tests.to_dict("records"),
        hypothesis_table=hyp.to_dict("records"),
        power=power,
        onset=onset,
        normal_stability=dict(per_feature=stab.to_dict("records"),
                              first10_records=first10.to_dict("records"),
                              n_stable=int(stab.loc[stab.feature.isin(F), "stable"].sum()),
                              n_prod_stable=int(stab.loc[stab.feature.isin(F), "prod_stable"].sum()),
                              n_features=len(F), regime=regime, bins_2min=bins2.to_dict("records")),
        conditions=cond,
    )
    (OUT / "02_event_trend.json").write_text(json.dumps(clean(result), ensure_ascii=False, indent=1), encoding="utf-8")
    write_summary(tests, hyp, power, onset, stab, regime, cond, af, first10)
    print_console(hyp, power, onset, stab, cond)


def viscosity_note() -> dict:
    """냉간 기동 가설의 사전 개연성 점검용 일반론 계산(가정 명시).

    가정: ISO VG46 광유(40°C 46 cSt, 100°C 6.8 cSt — 점도지수 약 100의 대표값). 실제 유종·유온은 자료에 없다.
    Walther식 log10(log10(ν+0.7)) = A − B·log10(T[K])로 보간.
    """
    t1, t2, v1, v2 = 313.15, 373.15, 46.0, 6.8
    w = lambda v: np.log10(np.log10(v + 0.7))
    b = (w(v1) - w(v2)) / (np.log10(t2) - np.log10(t1))
    a = w(v1) + b * np.log10(t1)
    nu = lambda c: float(10 ** (10 ** (a - b * np.log10(c + 273.15))) - 0.7)
    temps = [0, 5, 10, 15, 20, 25, 30, 40, 50]
    return dict(assumption="ISO VG46 가정, Walther 보간(일반론·설비 사양 미확인)",
                viscosity_cSt={str(c): nu(c) for c in temps},
                ratio_to_40C={str(c): nu(c) / v1 for c in temps})


def print_console(hyp, power, onset, stab, cond):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print("== 가설 판정표 (|z| 추세) ==")
    print(hyp[["feature", "all21_spearman_rho", "all21_mk_p", "all21_mk_p_holm", "all21_ts_slope_per_min",
               "ge10_spearman_rho", "ge10_mk_p", "ge10_mk_p_holm", "ge10_ts_slope_per_min",
               "ge10_front_median", "ge10_back_median", "ge10_mw_p", "ge10_verdict"]].round(4).to_string())
    print("== 검정력 ==")
    for s, v in power.items():
        print(s, v["n"], round(v["t_span_min"], 3), v["delta80_noise_sd"], v["spearman_rho_crit"], v["spearman_rho80"])
    print("== 첫 기록 ==")
    fr = onset["first_record"]
    print(fr["n_feat_outside_len"], fr["n_feat_outside_600"])
    for f, v in fr["features"].items():
        print(f, {k: (round(x, 4) if isinstance(x, float) else x) for k, x in v.items()})
    for r in onset["first_record_rows"]:
        print(r["row"], r["ts"], {s: (round(r[s]["value"], 3), round(r[s]["pct_all_rows"], 2), round(r[s]["pct_first_rows"], 2)) for s in SENSORS},
              round(r["joint_vib_exceed_share"], 5))
    print("== 정상 복귀 ==")
    for f, v in onset["back_to_normal"].items():
        print(f, v)
    print(onset["back_summary"])
    print("== 정상 안정성 ==")
    print(stab.round(4).to_string())
    print("== 운전 구간 ==")
    print(stab[["feature", "stable", "prod_stable", "prod_spearman_rho", "prod_bin_median_range_z", "prod_median_raw", "low_median_raw", "low_minus_prod_z", "bin_range_over_abnormal"]].round(4).to_string())
    print("== 조건 ==")
    print(json.dumps(clean({k: v for k, v in cond.items()}), ensure_ascii=False)[:3000])


def write_summary(tests, hyp, power, onset, stab, regime, cond, af, first10):
    """요약 md. 수치는 모두 이번 실행 결과에서 끌어온다(해석 문장은 이 자료의 결과를 전제로 쓴 것)."""
    T = tests.set_index(["subset", "target", "feature"])
    S10 = f"ge{MIN_LEN}"
    g = lambda s, f, k, tg="absz": T.loc[(s, tg, f), k]
    fp = lambda x: "—" if not np.isfinite(x) else ("<0.001" if x < 0.001 else f"{x:.3f}")
    m = len(F)
    a_main, a_holm = f"alpha_{ALPHA:.4f}", f"alpha_{ALPHA / m:.4f}"
    St = stab.set_index("feature")

    # ── 1. 추세 표
    tab = ["| 특징 | 21기록 ρ | MK p (Holm) | 17기록 ρ | MK p (Holm) | AR1 보정 Holm p (21/17) "
           "| Theil–Sen |z|/분, 17기록 [95%] | 앞7→뒤7 |z| 중앙값, 17기록 (MW p) | 판정(17기록) |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for f in F + list(COMPOSITES):
        tab.append(
            f"| {NAME[f]} | {g('all21', f, 'spearman_rho'):+.2f} | {fp(g('all21', f, 'mk_p'))} ({fp(g('all21', f, 'mk_p_holm'))}) "
            f"| {g(S10, f, 'spearman_rho'):+.2f} | {fp(g(S10, f, 'mk_p'))} ({fp(g(S10, f, 'mk_p_holm'))}) "
            f"| {fp(g('all21', f, 'mk_p_ar1_holm'))} / {fp(g(S10, f, 'mk_p_ar1_holm'))} "
            f"| {g(S10, f, 'ts_slope_per_min'):+.2f} [{g(S10, f, 'ts_lo'):+.2f}, {g(S10, f, 'ts_hi'):+.2f}] "
            f"| {g(S10, f, 'front_median'):.2f} → {g(S10, f, 'back_median'):.2f} ({fp(g(S10, f, 'mw_p'))}) "
            f"| {g(S10, f, 'verdict')} |")
    sig = {s: [f for f in F if g(s, f, "mk_p_holm") < ALPHA] for s in ("all21", S10)}
    sig_ar1 = {s: [f for f in F if g(s, f, "mk_p_ar1_holm") < ALPHA] for s in ("all21", S10)}
    dec_raw = sorted({f for s in ("all21", S10) for f in F if g(s, f, "mk_tau") < 0 and g(s, f, "mk_p") < ALPHA})
    inc_sig = sorted(set(sig["all21"]) | set(sig[S10]), key=F.index)
    names = lambda fs: ", ".join(NAME[f] for f in fs) if fs else "없음"
    sig_ar1_all = sorted(set(sig_ar1["all21"]) | set(sig_ar1[S10]), key=F.index)
    wd = {"Monday": "월", "Tuesday": "화", "Wednesday": "수", "Thursday": "목", "Friday": "금", "Saturday": "토", "Sunday": "일"}
    pw21, pw10 = power["all21"], power[S10]
    share = lambda s, f, a: power[s]["per_feature"][f][a]["share_of_front_median"]

    # ── 3. 시작·복귀
    fr, rows, nr = onset["first_record"], onset["first_record_rows"], onset["normal_row_range"]
    bs, back = onset["back_summary"], onset["back_to_normal"]
    out_first = [NAME[f] for f, v in fr["features"].items() if v["inside_len_1_99"] is False]
    sens_kr = {"AI0_Vibration": "상부 진동", "AI1_Vibration": "하부 진동", "AI2_Current": "전류"}
    row_tab = ["| 행 | 시각 | 상부 진동 | 하부 진동 | 전류 | 상·하부 동시 크기를 넘는 정상 행 비율 |", "|---|---|---:|---:|---:|---:|"]
    for r in rows:
        cell = lambda s: f"{r[s]['value']:.3f}{' **범위 밖**' if r[s]['outside_normal_min_max'] else ''} ({r[s]['pct_all_rows']:.1f}%)"
        row_tab.append(f"| {r['row']} | {r['ts'][11:]} | {cell('AI0_Vibration')} | {cell('AI1_Vibration')} | {cell('AI2_Current')} "
                       f"| {100 * r['joint_vib_exceed_share']:.2f}% |")
    back_tab = ["| 특징 | 정상 1~99% 안 (21기록, 길이 맞춤) | (17기록, 길이 맞춤) | (21기록, 정상 600 기준) | 해당 기록 |",
                "|---|---:|---:|---:|---|"]
    for f, v in back.items():
        back_tab.append(f"| {v['name']} | {v['inside_len_all21']} | {v['inside_len_ge10']} | {v['inside600_all21']} "
                        f"| {', '.join(map(str, v['recs_inside_len'])) or '—'} |")
    ge = af[af.n >= MIN_LEN]
    # 종합 지수 민감도: 전류 실효값을 뺀 12종 중앙값의 17기록 Spearman
    rho_wo, p_wo = stats.spearmanr(ge.t_mid_min, ge[[f"absz_{f}" for f in F if f != "cur_true_rms"]].median(axis=1))
    r2_max_ab = float(ge.cur_sine_r2.max())
    vs_low = pd.DataFrame(regime["abnormal_ge10_vs_low_regime"])
    quiet = vs_low[vs_low.pct_upper_in_low < 10]
    hi_rms = vs_low[vs_low.pct_true_rms_in_normal_ge10 >= 98]
    hi_mean = (af.cur_dc_ratio * af.cur_rms)[af.rec.isin(hi_rms.rec)]
    quiet_late = quiet[quiet.rec.isin(hi_rms.rec)]
    quiet_early = quiet[~quiet.rec.isin(hi_rms.rec)]

    # ── 4. 정상 안정성
    seg = regime["segment"]
    n_stable = int(St.loc[F, "stable"].sum())
    n_prod = int(St.loc[F, "prod_stable"].sum())
    wave = ["cur_sine_r2", "cur_resid_ratio"]
    vib_ratio = St.loc[VIB, "bin_range_over_abnormal"]
    first10_min_holm = float(St.loc[F, "first10_vs_rest_p_holm"].min())
    stab_tab = ["| 특징 | ρ(시간, 10행+) | 10분 중앙값 범위(z) | 범위/이상 이탈 | 생산 구간만 ρ | 생산 구간만 범위(z) "
                "| 생산 중앙값 | 저부하 중앙값 | 첫 10기록 vs 나머지 Holm p |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for f in F:
        r = St.loc[f]
        stab_tab.append(f"| {NAME[f]} | {r.spearman_rho_ge10:+.2f} | {r.bin_median_range_z:.2f} | {100 * r.bin_range_over_abnormal:.0f}% "
                        f"| {r.prod_spearman_rho:+.2f} | {r.prod_bin_median_range_z:.2f} | {r.prod_median_raw:.4g} "
                        f"| {r.low_median_raw:.4g} | {fp(r.first10_vs_rest_p_holm)} |")

    # ── 5. 조건
    cn, ca, vis = cond["normal"], cond["abnormal"], cond["oil_viscosity_note"]

    md = f"""---
title: 프레스 이상 사건 안 추세 — 예열·진행성·정상상태 가설 점검
created: {date.today()}
updated: {date.today()}
tags: [contest/k-ai-manufacturing]
source: code/press/domain/02_event_trend.py (matched 정밀도, 정상 600기록·이상 21기록)
status: seed
---

# 이상 사건 안 추세 (02_event_trend)

> 상위: [[제조데이터 경진대회 MOC]] · 코드 `code/press/domain/02_event_trend.py` · 입력은 `cases/common.py` `load_both(matched=True)`(저장 형식 누수 제거)

## 결론

1. **예열 가설 (a)가 예측하는 '이탈 감소'는 보이지 않는다.** 13종 특징 중 이탈 정도(|z|)가 Holm 보정 후 유의하게 줄어든 특징은 0개, 보정 전 p<0.05로 줄어든 특징도 {len(dec_raw)}개{'(' + names(dec_raw) + ')' if dec_raw else ''}다. 진동 계열 종합 이탈은 17기록 ρ={g(S10, 'absz_vib', 'spearman_rho'):+.2f}(MK p={fp(g(S10, 'absz_vib', 'mk_p'))})로 방향만 감소 쪽이다.
2. **전류 계열 일부는 오히려 커진다.** Holm 후 유의한 증가: 21기록 {names(sig['all21'])} / 17기록 {names(sig[S10])}. 그러나 연속 기록의 자기상관을 AR(1)로 보정하면 {('Holm 후 유의한 특징은 ' + names(sig_ar1_all) + '만 남는다') if sig_ar1_all else 'Holm 후 유의한 특징이 하나도 남지 않는다'}. 그래서 '증가 경향'까지만 말할 수 있다.
3. **사건 안에서 정상으로 돌아온 기록은 없다.** 10행 이상 {bs['ge10_records']}기록 중 전류 파형(사인 R²·잔차비)이 정상 범위에 든 기록은 {bs['ge10_current_waveform_inside_len']}개다. 첫 기록 첫 행부터 하부 진동({rows[0]['AI1_Vibration']['value']:.3f})이 정상 20,000행 최솟값({nr['AI1_Vibration']['min']:.3f}) 밖에 있다. 사건은 파일이 시작되기 전에 이미 진행 중이었다.
4. **정상 77분은 운전 상태 두 개가 섞인 정상상태다.** {seg['clock_start'][:5]}~{seg['clock_end'][:5]} 저진동·저부하 구간({regime['n_records_low']}기록)을 빼면 13종 중 {n_prod}종이 안정 기준(|ρ|<0.2, 10분 구간 중앙값 범위 1 robust SD 미만)을 만족한다. 77분 전체로 보면 안정한 특징은 {n_stable}종이다. 파일 시작(00:00) 직후에 기동 과도는 없다(첫 10기록 vs 나머지 Holm p 최소 {fp(first10_min_holm)}).
5. **검정력이 낮다.** 21기록·{pw21['t_span_min']:.2f}분에서 MK 검정력 80%를 얻으려면 사건 동안 잡음 SD의 {pw21['delta80_noise_sd'][a_main]:.1f}배(Holm 1단계 α=0.05/{m}이면 {pw21['delta80_noise_sd'][a_holm]:.1f}배)만큼 변해야 한다. 진동 종합 이탈로 치면 초기값의 {100 * share('all21', 'absz_vib', a_main):.0f}%(Holm {100 * share('all21', 'absz_vib', a_holm):.0f}%) 넘게 줄어야 잡힌다. Spearman은 실제 |ρ|가 {pw21['spearman_rho80'][a_main]:.2f}(Holm {pw21['spearman_rho80'][a_holm]:.2f}) 이상이어야 검정력 80%가 나온다. 그러니 '감소 없음'을 '(a) 기각'으로 읽으면 안 된다.

## 1. 이상 사건 안 추세

- 기록별 특징을 정상 600기록 분포 대비 robust z = (x − 중앙값)/(1.4826·MAD)로 바꾸고, |z|(정상에서 떨어진 거리)의 시간 추세를 봤다. 척도형(SD·진폭·RMS·비율)은 로그, R²는 log(1−R²) 척도다.
- 검정: Spearman ρ, Theil–Sen(|z|/분), Mann–Kendall(직접 구현), 앞 7기록 vs 뒤 7기록 Mann–Whitney. Holm 가족은 같은 부분집합의 특징 {m}종이다(종합 지수 3개는 가족 밖 보조 지표).
- 'AR1 보정'은 추세를 뺀 잔차의 lag-1 자기상관 r1로 MK 분산을 (1+r1)/(1−r1)배 키운 보수적 p다. 21기록은 한 사건이 수집 공백으로 잘린 조각이라 서로 독립이 아니다.

{chr(10).join(tab)}

읽는 법
- 사인 R²·잔차비는 10행+ 이상 기록 전부가 바닥(R² ≤ {r2_max_ab:.2f})이라 |z|가 천장(R² |z| 중앙값 ≈ {g(S10, 'cur_sine_r2', 'front_median'):.1f})에 붙어 있다. 조금 덜 나빠지는 변화가 있어도 이 두 특징으로는 보이지 않는다.
- 3행 기록(5번)은 사인 3모수 적합이라 R²=1이 자동으로 나온다. 4행 기록(0·10번)도 R²·lag1·상관이 거의 무의미하다. 그래서 17기록 결과를 우선한다.
- 원값 기준으로는 하부 진동 SD가 줄어든다(21기록 ρ={g('all21', 'vib_lower_sd', 'spearman_rho', 'raw'):+.2f}, MK p={fp(g('all21', 'vib_lower_sd', 'mk_p', 'raw'))}, Holm {fp(g('all21', 'vib_lower_sd', 'mk_p_holm', 'raw'))}). 그런데 |z| 추세는 비유의다(21기록 ρ={g('all21', 'vib_lower_sd', 'spearman_rho'):+.2f}, MK p={fp(g('all21', 'vib_lower_sd', 'mk_p'))}). 20번처럼 정상보다 작은 쪽으로 넘어간 기록이 있어서다. 진동이 작아진다고 정상에 가까워지는 것은 아니다.
- 13종을 한데 묶은 종합 이탈은 특징 구성에 민감하다. 13종이면 17기록 ρ={g(S10, 'absz_median', 'spearman_rho'):+.2f}(p={fp(g(S10, 'absz_median', 'spearman_p'))})인데, 전류 실효값 하나를 빼면 ρ={rho_wo:+.2f}(p={fp(p_wo)})로 떨어진다. 그래서 진동·전류 계열을 나눠 본다.

## 2. 가설별 판정

| 가설 | 예측 | 관찰 | 판정 |
|---|---|---|---|
| (a) 냉간 기동·예열 (일요일 오전 기동 → 저온 고점도 → 흡입 캐비테이션 등) | 이탈이 줄고 후반 기록이 정상 범위에 다가간다 | Holm 후 유의한 감소 0/{m}. 진동 종합 ρ={g(S10, 'absz_vib', 'spearman_rho'):+.2f}(비유의). 정상 범위로 돌아온 기록 0 | 지지 근거 없음. 단 검정력·시간창 한계로 기각도 못 한다 |
| (b) 진행성 고장 | 이탈이 커진다 | 전류 실효값·전류 평균/RMS 증가(17기록 Holm p {fp(g(S10, 'cur_true_rms', 'mk_p_holm'))}·{fp(g(S10, 'cur_dc_ratio', 'mk_p_holm'))}, AR1 보정 Holm {fp(g(S10, 'cur_true_rms', 'mk_p_ar1_holm'))}·{fp(g(S10, 'cur_dc_ratio', 'mk_p_ar1_holm'))}). 진동은 커지지 않음 | 전류 채널만 경향 수준으로 부합 |
| (c) 정상상태 고장 | 추세가 없다 | 진동 6종·전류 파형(R²·잔차비)·전류 진폭에 추세 없음 | 진동과 전류 파형은 부합 |

현장 관점에서 덧붙일 점
- **시간 척도가 안 맞는다.** 작동유 탱크 온도는 보통 수십 분 단위로 오른다(일반론). 2분 46초 동안 유온이 거의 그대로였다면 (a)가 맞아도 이탈 감소는 보이지 않는 게 정상이다. 이 자료에는 (a)와 (c)를 가를 시간창이 없다.
- **계절 때문에 (a)의 사전 개연성이 낮다.** 7월 17일 오전이다. ISO VG46에 유온이 외기 수준(25°C 안팎)이라고 가정하면(Walther 보간, 설비 사양 미확인) 25°C 점도는 {vis['viscosity_cSt']['25']:.0f} cSt로 40°C의 {vis['ratio_to_40C']['25']:.1f}배다. 5°C면 {vis['viscosity_cSt']['5']:.0f} cSt({vis['ratio_to_40C']['5']:.1f}배)다. 여름 기동은 겨울 냉간 기동보다 점도 부담이 훨씬 작다.
- **기동 시점을 모른다.** 이상 파일은 10:51:07에 이미 이상 상태로 시작한다. 그 전에 언제 기동했는지는 자료에 없다.
- **전류 증가는 고장 진행보다 운전·계측 상태 변화로도 설명된다.** 후반 기록({', '.join(str(r) for r in hi_rms.rec)}번)은 전류 실효값이 정상 10행+ 기록의 98백분위 이상이고, 전류 순시값이 정상 20,000행 최대 |{bs['normal_current_abs_max']:.0f}|를 넘는 기록이 {len(bs['records_current_peak_above_normal_max'])}개({', '.join(map(str, bs['records_current_peak_above_normal_max']))}번, 최대 {max(x['cur_peak_abs'] for x in bs['current_peak_by_record']):.0f})다. 이들 기록의 전류 평균도 {hi_mean.min():+.0f}~{hi_mean.max():+.0f}로 한쪽에 쏠린다. 같은 시기 {', '.join(str(r) for r in quiet_late.rec)}번 기록의 상부 진동은 정상 저부하 구간보다도 작다(저부하 분포 하위 {quiet_late.pct_upper_in_low.max():.0f}% 이하{', 초반 ' + ', '.join(str(r) for r in quiet_early.rec) + '번도 비슷' if len(quiet_early) else ''}). 진동은 멎고 전류는 큰 조합은 램이 멈춘 채 펌프가 고압(릴리프)에서 부하를 받는 상황과 맞는다. 전류 센서 영점 이동·포화 같은 계측 원인과도 맞는다. 유도전동기 상전류에는 원래 직류 성분이 없으므로 평균 쏠림은 계측 경로부터 점검할 대상이다. 압력·유온 채널이 없어 둘을 가를 수 없다.
- 2분 46초 안의 증가를 '진행성 고장'으로 단정하기도 어렵다. 기계 손상이 그 속도로 진행했다기보다 운전 상태가 바뀐 속도에 가깝다.

## 3. 이상 사건의 시작과 정상 복귀

첫 기록(0번, {fr['n']}행, {fr['start'][11:]}~): 길이를 맞춘 정상 기준(정상 기록을 앞 {fr['n']}행으로 자른 분포)으로 보면 {m}종 중 {fr['n_feat_outside_len']}종이 1~99% 밖이다({', '.join(out_first)}).

첫 기록의 행별 값과 정상 20,000행 분포 대비 백분위('범위 밖' = 정상 최솟값~최댓값 밖)는 다음과 같다. 정상 범위는 상부 {nr['AI0_Vibration']['min']:.3f}~{nr['AI0_Vibration']['max']:.3f}, 하부 {nr['AI1_Vibration']['min']:.3f}~{nr['AI1_Vibration']['max']:.3f}, 전류 {nr['AI2_Current']['min']:.0f}~{nr['AI2_Current']['max']:.0f}이다.

{chr(10).join(row_tab)}

- 첫 행부터 진동 값 하나가 정상 전체 범위 밖이다. 상·하부를 함께 보면 4행 모두 정상 행에서 나온 적 없는 조합이다. `cases/README.md`의 '첫 표본은 값 하나로 구별 안 됨'은 v2 점수(4.19 < 문턱 4.68) 기준 이야기다. 센서별 정상 최소·최대만 봐도 첫 행은 범위 밖이다.
- 이상 파일이 이상 상태로 시작하므로 사건 시작 시점(onset)은 이 자료에 없다.

정상 복귀: 특징별로 정상 1~99% 범위에 든 기록 수

{chr(10).join(back_tab)}

- 13종이 모두 정상 범위에 든 기록은 {len(bs['records_all_features_inside_len'])}개다. 과반이 정상 범위인 기록({', '.join(map(str, bs['records_majority_inside_len']))}번)은 모두 3~8행짜리다. 길이 맞춤 기준의 폭이 넓어서 생긴 결과(정보 부족)이지 회복의 근거가 아니다.
- 상부 진동 SD가 정상 범위에 드는 {', '.join(map(str, back['vib_upper_sd']['recs_inside_len']))}번은 정상으로 돌아온 것이 아니라 진동이 작아진 기록이다(정상 저부하 구간 분포 하위 {quiet.pct_upper_in_low.min():.0f}~{quiet.pct_upper_in_low.max():.0f}%).
- 정상 600기록 기준의 1% 하한은 1~2행짜리 정상 기록(SD≈0) 때문에 0에 가깝게 내려간다. 그래서 정상 600 기준 열은 참고만 하고 길이 맞춤 열을 본다.

## 4. 정상 77분 안정성

- 파일은 {cn['start'][11:19]}에 시작한다. 자정 파일 분할로 보이며, 첫 기록부터 전류 사인 R² {first10.cur_sine_r2.iloc[0]:.3f}로 이미 정상 운전 중이다. 첫 10기록과 나머지를 비교하면 13종 모두 차이가 없다(Mann–Whitney Holm p 최소 {fp(first10_min_holm)}). 기동 과도 상태는 없다.
- **저부하 구간**: {seg['clock_start'][:5]}~{seg['clock_end'][:5]}({regime['n_records_low']}기록). 2분 구간 중앙값 상부 진동 SD가 {seg['threshold_vib_upper_sd']:.3f}(10행+ 전체 중앙값의 0.6배) 아래로 이어지는 범위다. 이 구간에서는 생산 구간 대비 상부 진동 SD가 {St.loc['vib_upper_sd', 'prod_median_raw']:.3f}→{St.loc['vib_upper_sd', 'low_median_raw']:.3f}, 하부 {St.loc['vib_lower_sd', 'prod_median_raw']:.3f}→{St.loc['vib_lower_sd', 'low_median_raw']:.3f}로 줄고, 전류 진폭은 {St.loc['cur_amp', 'prod_median_raw']:.0f}→{St.loc['cur_amp', 'low_median_raw']:.0f}, 상·하부 진동 상관은 {St.loc['upper_lower_corr', 'prod_median_raw']:+.2f}→{St.loc['upper_lower_corr', 'low_median_raw']:+.2f}로 바뀐다. 생산 구간에서도 전류 진폭이 높은 기록과 낮은 기록이 번갈아 나온다(파일 첫 10기록만 봐도 {first10.cur_amp.min():.0f}~{first10.cur_amp.max():.0f}). 저부하 구간은 낮은 상태가 12분 동안 이어진 것으로, 프레스 대기(무부하 운전)로 추정한다.
- 판단: **정상 기준선은 이 77분 동안 생산 운전 구간 안에서 정상상태다.** 전류 파형 특징(R²·잔차비)은 77분 전체에서도 10분 구간 변동이 이상 이탈의 {100 * St.loc[wave, 'bin_range_over_abnormal'].min():.0f}~{100 * St.loc[wave, 'bin_range_over_abnormal'].max():.0f}%뿐이다. 진동 특징은 저부하 구간 때문에 변동이 이상 이탈의 {100 * vib_ratio.min():.0f}~{100 * vib_ratio.max():.0f}%에 이른다. 진동 기준선은 운전 상태별(생산/저부하)로 나눠 잡는 편이 맞다.
- 600기록은 서로 이웃해 자기상관이 있어 p가 과소평가된다. 효과 크기(ρ, z 단위 변동)로 판단했다.

{chr(10).join(stab_tab)}

## 5. 한계 — 운전·계측 조건은 데이터로 분리할 수 없다

| 항목 | 정상 | 이상 |
|---|---|---|
| 날짜·요일 | {cn['start'][:10]} ({wd[cn['weekday']]}) | {ca['start'][:10]} ({wd[ca['weekday']]}) |
| 시각 | {cn['start'][11:16]}~{cn['end'][11:16]} (자정 직후) | {ca['start'][11:16]}~{ca['end'][11:16]} (오전) |
| 길이 | {cn['minutes']:.1f}분, {cn['records']}기록 | {ca['minutes']:.2f}분, {ca['records']}기록 |
| 두 파일 사이 | 공백 {cond['gap_days']:.1f}일 | |
| 전류 겉보기 주파수(10행+ 기록 최적 사인) | 중앙 {cn['cur_f_hat_hz']['median']:.3f} Hz, 0.59~0.62 Hz 기록 {100 * cn['share_f_hat_within_0p59_0p62']:.0f}%, R² 중앙 {cn['cur_r2_at_f_hat']['median']:.3f} | 0.59~0.62 Hz 기록 {100 * ca['share_f_hat_within_0p59_0p62']:.0f}%, 최적 주파수 {ca['cur_f_hat_hz']['min']:.2f}~{ca['cur_f_hat_hz']['max']:.2f} Hz로 흩어짐, R² 중앙 {ca['cur_r2_at_f_hat']['median']:.2f} |
| 전류 RMS(std) 중앙값(10행+) | {cn['cur_rms_median']:.1f} | {ca['cur_rms_median']:.1f} |
| 저장 형식 | 정밀도가 다름(형식 누수, `cases/README.md`) | |

- 정상과 이상이 서로 다른 날짜·요일·시각에 한 번씩뿐이다. 그래서 '고장 효과'와 '운전 조건 효과'가 완전히 겹친다. 운전 조건에는 교대·생산품·금형·부하, 외기온·유온, 주말 특별 운전이나 정비 후 시운전 여부가 들어간다. 이상 사건 안 추세의 해석이 갈리는 것도 같은 이유다.
- 전류 겉보기 0.6 Hz는 60 Hz 상전류를 10 Hz로 찍을 때 공급 주파수와 샘플링 클록의 차이가 만드는 맥놀이 |f_공급 − 6·f_s|다. 계통 주파수가 0.6 Hz나 벗어나는 일은 드물다. 그러니 정상 쪽 값부터 샘플링 클록이나 인버터 출력 주파수에 묶인 값으로 보인다. 이상에서 이 구조가 깨진 것은 고장(부하 변동에 의한 전류 변조)일 수도, 계측 설정·인버터 운전 차이일 수도 있다. 이 자료로는 가를 수 없다.
- 10 Hz 샘플링으로는 캐비테이션(kHz대 광대역 소음)이나 베어링 결함 주파수가 직접 보이지 않는다. 진동 SD는 고주파 에너지가 접혀 들어온 값이다. (a)의 기전(흡입 캐비테이션)은 이 자료로 직접 검증할 수 없다.
- 압력·유온·회전수 채널이 없다. 이상 사건은 1건뿐이고, 모든 결론은 그 한 사건에 대한 것이다.

## 재현

```bash
cd code/press/domain
PYTHONIOENCODING=utf-8 python 02_event_trend.py
```

출력(`domain/outputs/`): `02_event_trend.json`(전체), `02_event_trend.csv`(추세 검정표: 부분집합×대상×특징), `02_event_trend_records.csv`(이상 기록별 특징·z·정상 범위 여부), `02_event_trend_normal_bins.csv`(정상 10분 구간), `02_event_trend_normal_bins2min.csv`(정상 2분 구간). seed {SEED}, 검정력 모의실험 {N_SIM}회.
"""
    (OUT / "02_event_trend_summary.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
