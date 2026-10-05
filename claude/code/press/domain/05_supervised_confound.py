"""공개된 방식의 지도학습(1초 창 통계 + 부스팅, F1 0.944)을 재현하고, 그 점수가 고장이 아니라 세션 차이로도 나오는지 대조 실험으로 본다.

정상(07-12 00시)과 이상(07-17 10시)은 날짜·시각대·저장 형식이 모두 달라 라벨과 세션이 겹친다(교락).
입력: data/3_소성가공_예지보전 두 CSV(cases/common.load). 출력: outputs/05_supervised_confound.json · .csv(seed별 결과) · _summary.md
보고서 2.4절의 근거. test 채점 이후의 사후 분석이다.
실행: PYTHONIOENCODING=utf-8 python 05_supervised_confound.py [--md-only: JSON에서 요약 md만 다시 쓴다]
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.stats import mannwhitneyu
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "cases"))
from common import DATA, F0, SENSORS, case_table, load  # noqa: E402

warnings.filterwarnings("ignore")

OUT = HERE / "outputs"
STEM = "05_supervised_confound"
SEEDS = list(range(10))     # seed가 겹 배정(shuffle)과 모델 난수를 함께 정한다
PI_SEEDS = [0, 1, 2]        # 순열 중요도용 seed
N_SPLITS = 5
N_JOBS = 10  # seed(또는 seed×겹, 블록 쌍) 단위 프로세스 병렬. 작업마다 seed를 직접 받으므로 결과는 병렬 수와 무관하다
WIN = 10     # 창 길이 10행 = 1초
BLOCK = 21  # 이상 기록 수와 같은 블록 크기
MODELS = ["HGB", "RF", "LR"]
F0_HZ = F0 * 10  # 정상 전류 겉보기 주파수 0.6064 Hz
CUR = SENSORS[2]
SHORT = {"AI0_Vibration": "up", "AI1_Vibration": "lo", "AI2_Current": "cur"}
WIN_FEATS = [f"{SHORT[s]}_{k}" for s in SENSORS for k in ("mean", "std", "rms", "min", "max")]
# 기록 단위 특징 10개. case_table의 n·t0은 세션·수집 정보라 뺀다
CASE_FEATS = ["vib_upper_sd", "vib_lower_sd", "upper_lower_log_ratio", "upper_lower_corr", "vib_upper_lag1",
              "vib_lower_lag1", "cur_amp", "cur_offset_ratio", "cur_resid_ratio", "cur_sine_r2"]
DIG_FEATS = ["dig_up", "dig_lo"]   # 진동 값의 유효 소수 자릿수. 원본 두 파일의 저장 형식 차이(누수 통로)
TIER0 = ["n", "gap_prev", "clock_sin", "clock_cos", "tphase_sin", "tphase_cos"]   # 정의상 고장 무관(meta_table 참고)
TIER1 = ["cur_offset_abs", "cur_freq_hat", "cur_phase0_sin", "cur_phase0_cos"]   # 조건부 고장 무관
WIN_GROUPS = {"상부진동(up_*)": [f for f in WIN_FEATS if f.startswith("up_")],
              "하부진동(lo_*)": [f for f in WIN_FEATS if f.startswith("lo_")],
              "전류(cur_*)": [f for f in WIN_FEATS if f.startswith("cur_")]}
CASE_GROUPS = {"진동 크기": ["vib_upper_sd", "vib_lower_sd"],
               "진동 모양": ["upper_lower_log_ratio", "upper_lower_corr", "vib_upper_lag1", "vib_lower_lag1"],
               "전류 크기": ["cur_amp"],
               "전류 파형": ["cur_offset_ratio", "cur_resid_ratio", "cur_sine_r2"]}
FREQ_GRID = np.arange(0.02, 5.0, 0.002)   # 전류 겉보기 주파수 탐색 격자(Hz)
STRESS = {"none": None, "cur_shift_+81.4": 81.4, "cur_shift_+272.4": 272.4, "jitter_0.1ms_60.6Hz": 0.1}
STRESS_MIN_LEN = 17  # 보고서 V5와 같이 17행 이상 기록만 센다
if "--quick" in sys.argv:  # 점검용. seed 1개, 출력은 QUICK_OUT 폴더
    import os
    SEEDS, PI_SEEDS, OUT = [0], [0], Path(os.environ["QUICK_OUT"])


# ───────────────────────── 자료 ─────────────────────────
def decimals(s: pd.Series) -> np.ndarray:
    """CSV에 적힌 문자열 그대로의 유효 소수 자릿수(1e-05 같은 지수 표기도 처리)."""
    return s.map(lambda v: max(0, -Decimal(str(v).strip()).as_tuple().exponent)).to_numpy(float)


def load_raw(name: str) -> pd.DataFrame:
    """정밀도를 맞추지 않은 원본 + 진동 소수 자릿수 열(dig_up, dig_lo)."""
    df = load(name, matched=False)
    s = pd.read_csv(DATA / name, usecols=SENSORS[:2], dtype=str)   # 자릿수는 숫자로 읽기 전 문자열에서 센다
    df["dig_up"], df["dig_lo"] = decimals(s[SENSORS[0]]), decimals(s[SENSORS[1]])
    return df


def window_table(df: pd.DataFrame, extra=()) -> pd.DataFrame:
    """기록 안 비중첩 10행 창(1초)의 센서별 mean/std/RMS/min/max. 10행이 다 찬 창만 쓴다(10행 미만 기록은 빠진다)."""
    d = df.assign(win=df["pos"] // WIN)
    d = d[d.groupby(["rec", "win"])["pos"].transform("size") == WIN]
    keys = [d["rec"], d["win"]]
    g = d.groupby(keys)
    cols = {}
    for s in SENSORS:
        k = SHORT[s]
        cols[f"{k}_mean"] = g[s].mean()
        cols[f"{k}_std"] = g[s].std(ddof=0)
        cols[f"{k}_rms"] = np.sqrt(d[s].pow(2).groupby(keys).mean())
        cols[f"{k}_min"] = g[s].min()
        cols[f"{k}_max"] = g[s].max()
    for c in extra:
        cols[c] = g[c].mean()
    return pd.DataFrame(cols).reset_index()


def case_rep(df: pd.DataFrame, extra=()) -> pd.DataFrame:
    """기록 단위 표현(common.case_table). extra 열은 기록 평균으로 붙인다."""
    ct = case_table(df)
    for c in extra:
        ct[c] = df.groupby("rec")[c].mean().reindex(ct["rec"]).to_numpy()
    return ct


def freq_scan(x: np.ndarray) -> float:
    """사인+절편 적합 R²가 최대인 겉보기 주파수(Hz, 0.02~5 Hz 격자)."""
    # 주파수마다 lstsq를 부르면 느려서, 3×3 정규방정식을 격자 전체에 대해 한 번에 푼다. 잔차 제곱합이 최소인 주파수가 R² 최대다
    m = len(x)
    w = 2 * np.pi * FREQ_GRID[:, None] * np.arange(m)[None, :] / 10
    S, C = np.sin(w), np.cos(w)
    G = np.empty((len(FREQ_GRID), 3, 3))
    G[:, 0, 0] = m
    G[:, 0, 1] = G[:, 1, 0] = S.sum(1)
    G[:, 0, 2] = G[:, 2, 0] = C.sum(1)
    G[:, 1, 1], G[:, 2, 2] = (S * S).sum(1), (C * C).sum(1)
    G[:, 1, 2] = G[:, 2, 1] = (S * C).sum(1)
    b = np.stack([np.full(len(FREQ_GRID), x.sum()), S @ x, C @ x], 1)
    coef = np.linalg.solve(G + 1e-9 * np.eye(3), b[..., None])[..., 0]   # 1e-9는 특이 행렬 방지
    rss = (x ** 2).sum() - (coef * b).sum(1)
    return float(FREQ_GRID[np.argmin(rss)])


def meta_table(df: pd.DataFrame) -> pd.DataFrame:
    """기록마다 '고장과 무관해야 할' 특징. 2b 시험에서 이것만으로 정상/이상이 갈리는지 본다.

    Tier 0 — 정의상 고장 무관. 로거가 정하는 수집 메타데이터이고 설비 물리량이 아니다.
      n(기록 길이, 로거가 최대 50행씩 끊고 수집 공백에서 잘림), gap_prev(직전 기록과의 공백, 저장 주기),
      clock(시작 시각의 0.1초 격자 안 위치 ms mod 100, 로거 시계 위상), tphase(시작 시각을 0.6064 Hz 시계로 본 위상, 시각만의 함수).
    Tier 1 — 조건부 고장 무관. 모터가 60 Hz 계통에 직결돼 있다는 가정이 필요하다.
      cur_offset_abs(|전류 절편|/진폭): 교류 전류는 평균이 0이라 절편은 주기를 다 못 덮었거나 센서 DC 편차일 때 생긴다.
        단 인버터 스위치 고장처럼 실제 DC 성분을 만드는 고장도 있다.
      cur_freq_hat(겉보기 주파수, 20행 이상만): 60 Hz를 10 Hz로 찍은 앨리어스라 직결이면 전원 주파수와 표본화 간격이 정한다.
        이상 파일은 전류가 사인 꼴이 아니어서(R² 중앙값 0.1) 추정치에 파형 붕괴가 섞일 수 있다.
      cur_phase0(0.6064 Hz 사인의 기록 시작 위상): 기록을 언제 시작했는지(로거)가 정한다.
    시각대(00시 vs 10시)·날짜는 완벽히 가르지만 자명해서 넣지 않았다.
    """
    ts = pd.to_datetime(df["TimeStamp"])
    g = df.assign(ts=ts).groupby("rec")
    st, en, n = g["ts"].first(), g["ts"].last(), g.size()
    gap = (st - en.shift()).dt.total_seconds() - 0.1          # 정상 표본 간격 0.1초를 뺀 순수 공백
    clock = 2 * np.pi * ((st.dt.microsecond / 1000.0) % 100.0) / 100.0
    epoch = (st - pd.Timestamp("2022-07-01")).dt.total_seconds()
    tph = 2 * np.pi * ((epoch * F0_HZ) % 1.0)
    rows = []
    cur = df[CUR].to_numpy(float)
    for r, idx in df.groupby("rec").indices.items():
        x = cur[idx]
        k = np.arange(len(x))
        X = np.column_stack([np.ones(len(x)), np.sin(2 * np.pi * F0 * k), np.cos(2 * np.pi * F0 * k)])
        b, *_ = np.linalg.lstsq(X, x, rcond=None)      # 고정 주파수 F0 사인 + 절편 적합
        amp = np.hypot(b[1], b[2])
        ph0 = np.arctan2(b[2], b[1])
        rows.append(dict(rec=r, cur_offset_abs=abs(b[0]) / amp if amp > 0 else np.nan,
                         cur_freq_hat=freq_scan(x) if len(x) >= 20 else np.nan,
                         cur_phase0_sin=np.sin(ph0), cur_phase0_cos=np.cos(ph0)))
    t = pd.DataFrame(rows).set_index("rec")
    t["n"], t["gap_prev"] = n, gap
    t["clock_sin"], t["clock_cos"] = np.sin(clock), np.cos(clock)
    t["tphase_sin"], t["tphase_cos"] = np.sin(tph), np.cos(tph)
    return t.reset_index()


def stack(tab_n: pd.DataFrame, tab_a: pd.DataFrame, feats):
    """정상·이상 표를 쌓아 X, y(이상=1), 그룹(기록 번호. 이상은 +100000으로 정상과 겹치지 않게)을 만든다."""
    X = np.vstack([tab_n[feats].to_numpy(float), tab_a[feats].to_numpy(float)])
    y = np.r_[np.zeros(len(tab_n)), np.ones(len(tab_a))].astype(int)
    g = np.r_[tab_n["rec"].to_numpy(), tab_a["rec"].to_numpy() + 100000]
    return X, y, g


# ───────────────────────── 모델·검증 ─────────────────────────
def make_model(name: str, seed: int):
    """HGB·RF·LR. 셋 다 class_weight=balanced, 결측은 HGB가 자체 처리하고 나머지는 중앙값으로 채운다."""
    if name == "HGB":  # catboost가 설치돼 있지 않아 공개 분석의 CatBoost 대신 쓴다
        return HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, min_samples_leaf=5,
                                              class_weight="balanced", random_state=seed)
    if name == "RF":  # seed 단위로 프로세스 병렬을 쓰므로 나무 적합은 단일 스레드
        return make_pipeline(SimpleImputer(strategy="median"),
                             RandomForestClassifier(n_estimators=200, class_weight="balanced", n_jobs=1, random_state=seed))
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                         LogisticRegression(class_weight="balanced", max_iter=5000))


def folds(y, g, seed):
    """기록 단위 그룹 5겹(라벨 비율 층화). 같은 기록의 창은 학습·평가에 나뉘지 않는다."""
    return list(StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed).split(np.zeros(len(y)), y, g))


def oof(X, y, g, model, seed):
    """5겹 out-of-fold 양성 확률."""
    p = np.full(len(y), np.nan)
    for tr, te in folds(y, g, seed):
        p[te] = make_model(model, seed).fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return p


def metrics(y, p, thr=0.5) -> dict:
    """F1·balanced acc는 문턱 0.5 판정으로, PR-AUC·ROC-AUC는 확률 그대로 잰다."""
    yhat = (p >= thr).astype(int)
    return dict(f1=f1_score(y, yhat, zero_division=0), pr_auc=average_precision_score(y, p),
                roc_auc=roc_auc_score(y, p), bal_acc=balanced_accuracy_score(y, yhat))


# 아래 _*_one 함수는 joblib 작업자 프로세스에서 돈다. 작업자에는 모듈 첫머리의 경고 끄기가 적용되지 않아 다시 끈다
def _cv_one(X, y, g, model, seed) -> dict:
    """seed 하나의 OOF 지표."""
    warnings.filterwarnings("ignore")
    return dict(n=len(y), n_pos=int(y.sum()), n_pos_groups=int(len(np.unique(g[y == 1]))), prevalence=float(y.mean()),
                **metrics(y, oof(X, y, g, model, seed)))


def run_cv(exp, variant, rep, X, y_of_seed, g) -> list:
    """모델별로 seed 10개의 5겹 OOF 지표를 낸다. y_of_seed는 가짜 라벨처럼 seed마다 라벨이 바뀌는 경우를 위한 함수다."""
    # to_numpy·vstack 결과는 F 순서다. 메모리 배치에 따라 LR 수치 끝자리가 달라질 수 있어, 기존 결과와 같은 C 순서로 넘긴다
    X = np.ascontiguousarray(X)
    rows = []
    for model in MODELS:
        t = time.time()
        res = Parallel(n_jobs=N_JOBS)(delayed(_cv_one)(X, y_of_seed(seed), g, model, seed) for seed in SEEDS)
        rows += [dict(exp=exp, variant=variant, rep=rep, model=model, seed=s, **r) for s, r in zip(SEEDS, res)]
        print(f"  {exp:16s} {variant:16s} {rep:6s} {model:3s} "
              f"AUC {np.mean([r['roc_auc'] for r in res]):.3f} ({time.time() - t:.0f}s)", flush=True)
    return rows


def _pair_one(X, g, blk, i, j, model, seed=0) -> dict:
    """블록 i(음성) vs 블록 j(양성, j = -1이면 이상 21기록)만 남겨 5겹 그룹 교차검증."""
    warnings.filterwarnings("ignore")
    m = (blk == i) | (blk == j)
    y = (blk[m] == j).astype(int)
    return metrics(y, oof(X[m], y, g[m], model, seed))


GAP_BINS = [(1, 1), (2, 4), (5, 9), (10, 19), (20, 27)]   # 블록 간격 구간(블록 1개 ≈ 2.7분)


def block_pair_summary(pair_df: pd.DataFrame) -> list:
    """블록 쌍 ROC-AUC 분포 요약. 이상-vs-블록 AUC가 정상 블록끼리 분포의 몇 분위인지도 낸다."""
    q = lambda s, p: float(np.quantile(s, p))
    out = []
    for (rep, model), d in pair_df.groupby(["rep", "model"], sort=False):
        bb = d[d.variant == "block_vs_block"]
        ab = d[d.variant == "abnormal_vs_block"]
        row = dict(rep=rep, model=model, n_block_pairs=len(bb), n_abnormal_pairs=len(ab),
                   bb_auc_median=q(bb.roc_auc, .5), bb_auc_q10=q(bb.roc_auc, .1), bb_auc_q90=q(bb.roc_auc, .9),
                   bb_auc_max=float(bb.roc_auc.max()), bb_share_auc_ge_0_9=float((bb.roc_auc >= .9).mean()),
                   bb_share_auc_ge_0_95=float((bb.roc_auc >= .95).mean()),
                   ab_auc_median=q(ab.roc_auc, .5), ab_auc_min=float(ab.roc_auc.min()),
                   ab_share_auc_ge_0_95=float((ab.roc_auc >= .95).mean()),
                   ab_median_percentile_in_bb=float((bb.roc_auc < ab.roc_auc.median()).mean()))
        for lo, hi in GAP_BINS:
            s = bb[(bb.block_gap >= lo) & (bb.block_gap <= hi)]
            row[f"bb_auc_median_gap{lo}-{hi}"] = q(s.roc_auc, .5)
            row[f"bb_auc_min_gap{lo}-{hi}"] = float(s.roc_auc.min())
            row[f"bb_auc_q75_gap{lo}-{hi}"] = q(s.roc_auc, .75)
            row[f"bb_share_ge_0_9_gap{lo}-{hi}"] = float((s.roc_auc >= .9).mean())
            row[f"minutes_gap{lo}-{hi}"] = float(s.minutes_apart.median())
        out.append(row)
    return out


def summarize(df: pd.DataFrame, keys, cols) -> pd.DataFrame:
    """seed별 지표를 묶어 평균·표준편차를 낸다. 표본 수 열은 seed마다 같아 첫 값을 쓴다."""
    agg = df.groupby(keys, sort=False)[cols].agg(["mean", "std"])
    agg.columns = [f"{a}_{b}" for a, b in agg.columns]
    first = df.groupby(keys, sort=False)[["n", "n_pos", "n_pos_groups", "prevalence"]].first()
    return first.join(agg).reset_index()


# ───────────────────────── 순열 중요도 ─────────────────────────
def _pi_one(X, y, feats, groups_map, model, seed, k_fold, tr, te, n_rep):
    """한 겹에서 단일 특징·묶음 순열 중요도(평가 겹 PR-AUC 감소량)."""
    warnings.filterwarnings("ignore")
    rng = np.random.default_rng([seed, k_fold])
    m = make_model(model, seed).fit(X[tr], y[tr])
    Xte, yte = X[te], y[te]
    r = permutation_importance(m, Xte, yte, scoring="average_precision", n_repeats=n_rep, random_state=seed)
    base = average_precision_score(yte, m.predict_proba(Xte)[:, 1])
    # std·RMS처럼 서로 대신하는 특징은 하나씩 섞으면 중요도가 쪼개져 작게 나온다. 센서(묶음) 단위로 열을 같이 섞어 본다
    grouped = {}
    for k, cols in groups_map.items():
        ci = [feats.index(c) for c in cols]
        drops = []
        for _ in range(n_rep):
            Xp = Xte.copy()
            Xp[:, ci] = Xte[rng.permutation(len(te))][:, ci]  # 묶음 안 열은 같은 순서로 함께 섞는다
            drops.append(base - average_precision_score(yte, m.predict_proba(Xp)[:, 1]))
        grouped[k] = float(np.mean(drops))
    return dict(zip(feats, r.importances_mean)), grouped


def perm_importance(X, y, g, feats, groups_map, model) -> dict:
    """seed 0~2 × 5겹 순열 중요도의 평균·표준편차. 반복은 10회(RF는 느려서 5회)."""
    n_rep = 5 if model == "RF" else 10
    tasks = [(seed, k, tr, te) for seed in PI_SEEDS for k, (tr, te) in enumerate(folds(y, g, seed))]
    res = Parallel(n_jobs=N_JOBS)(delayed(_pi_one)(X, y, feats, groups_map, model, s, k, tr, te, n_rep) for s, k, tr, te in tasks)
    single = {f: [r[0][f] for r in res] for f in feats}
    grouped = {k: [r[1][k] for r in res] for k in groups_map}
    fmt = lambda d: {k: dict(mean=float(np.mean(v)), sd=float(np.std(v))) for k, v in d.items()}
    single, grouped = fmt(single), fmt(grouped)
    return dict(model=model, n_repeats=n_rep, seeds=PI_SEEDS,
                single=dict(sorted(single.items(), key=lambda kv: -kv[1]["mean"])),
                grouped=dict(sorted(grouped.items(), key=lambda kv: -kv[1]["mean"])))


# ───────────────────────── 수집 조건 조작(V5와 같은 종류) ─────────────────────────
def shift_current(df, amount):
    """전류 전체를 amount만큼 옮긴다(센서 오프셋·영점 변화 흉내)."""
    return df.assign(**{CUR: df[CUR] + amount})


def jitter_current(df, sigma_ms, rng, f_hz=60.6, min_len=STRESS_MIN_LEN):
    """정상 전류에 표본화 시각 흔들림을 넣는다. 보고서 V5(예준 jitter_stress)와 같은 생성 원리다.

    0.6064 Hz 사인 + 잔차로 나눈 뒤 사인 위상에만 60.6 Hz × N(0, σ) 시각 오차를 더해 다시 합친다.
    V5와 달리 기록별 적합 주파수 대신 고정 F0를 쓴다.
    """
    x = df[CUR].to_numpy(float).copy()
    for _, idx in df.groupby("rec").indices.items():
        if len(idx) < min_len:
            continue
        k = np.arange(len(idx))
        w = 2 * np.pi * F0 * k
        X = np.column_stack([np.cos(w), np.sin(w), np.ones(len(idx))])
        c, *_ = np.linalg.lstsq(X, x[idx], rcond=None)
        resid = x[idx] - X @ c
        # 실제 전류는 60.6 Hz라 시각 오차 δ는 겉보기 0.6 Hz가 아니라 원 주파수 기준 위상 2π·60.6·δ로 나타난다
        ph = w + 2 * np.pi * f_hz * rng.normal(0, sigma_ms / 1e3, len(idx))
        x[idx] = c[0] * np.cos(ph) + c[1] * np.sin(ph) + c[2] + resid
    return df.assign(**{CUR: x})


def stress_test(normal, X, y, g, rep, feats, fixed_tabs) -> list:
    """matched 지도학습 모델을 학습 겹으로 적합하고, 평가 겹 정상 기록(17행 이상)을 조작했을 때 이상 판정 비율을 잰다.

    기록 경보는 window면 창 하나라도, case면 기록 확률이 0.5 이상일 때다.
    """
    long_recs = normal.groupby("rec").size().pipe(lambda s: s[s >= STRESS_MIN_LEN].index.to_numpy())
    rows = []
    for model in MODELS:
        res = Parallel(n_jobs=N_JOBS)(delayed(_stress_one)(normal, X, y, g, rep, feats, fixed_tabs, model, s, long_recs) for s in SEEDS)
        for seed, cnt in zip(SEEDS, res):
            for k, (a, n) in cnt.items():
                rows.append(dict(exp="stress", variant=k, rep=rep, model=model, seed=seed, alerted=a, records=n, alarm_rate=a / n))
    return rows


def _stress_one(normal, X, y, g, rep, feats, fixed_tabs, model, seed, long_recs) -> dict:
    """seed 하나에서 조작별 (경보 기록 수, 기록 수). 흔들림은 seed마다 새로 만든다."""
    warnings.filterwarnings("ignore")
    tabs = dict(fixed_tabs)
    jd = jitter_current(normal, STRESS["jitter_0.1ms_60.6Hz"], np.random.default_rng(seed))
    tabs["jitter_0.1ms_60.6Hz"] = window_table(jd) if rep == "window" else case_rep(jd)
    cnt = {k: [0, 0] for k in tabs}
    for tr, te in folds(y, g, seed):
        m = make_model(model, seed).fit(X[tr], y[tr])
        recs = np.intersect1d(np.unique(g[te][y[te] == 0]), long_recs)
        for k, tab in tabs.items():
            sub = tab[tab["rec"].isin(recs)]
            p = m.predict_proba(sub[feats].to_numpy(float))[:, 1]
            flag = pd.Series(p >= 0.5).groupby(sub["rec"].to_numpy()).max()
            cnt[k][0] += int(flag.sum())
            cnt[k][1] += int(len(flag))
    return cnt


# ───────────────────────── 본 실행 ─────────────────────────
def main():
    """실험 1(지도학습 재현)과 2a~2d(세션 교락 시험)를 돌려 JSON·CSV·요약 md를 쓴다."""
    t_all = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    print("자료 적재 …", flush=True)
    nm, am = load("press_data_normal.csv", True), load("outlier_data.csv", True)
    nr, ar = load_raw("press_data_normal.csv"), load_raw("outlier_data.csv")

    # 자료 4종 × 표현 2종. matched = 정밀도를 맞춰 형식 누수를 지운 자료, raw = 원본,
    # raw+digits = 원본 + 진동 소수 자릿수, raw digits-only = 자릿수 특징만
    tabs = {
        ("matched", "window"): (window_table(nm), window_table(am), WIN_FEATS),
        ("matched", "case"): (case_rep(nm), case_rep(am), CASE_FEATS),
        ("raw", "window"): (window_table(nr), window_table(ar), WIN_FEATS),
        ("raw", "case"): (case_rep(nr), case_rep(ar), CASE_FEATS),
    }
    rw_n, rw_a = window_table(nr, DIG_FEATS), window_table(ar, DIG_FEATS)
    rc_n, rc_a = case_rep(nr, DIG_FEATS), case_rep(ar, DIG_FEATS)
    tabs[("raw+digits", "window")] = (rw_n, rw_a, WIN_FEATS + DIG_FEATS)
    tabs[("raw+digits", "case")] = (rc_n, rc_a, CASE_FEATS + DIG_FEATS)
    tabs[("raw digits-only", "window")] = (rw_n, rw_a, DIG_FEATS)
    tabs[("raw digits-only", "case")] = (rc_n, rc_a, DIG_FEATS)

    # 원본 두 파일의 저장 형식 차이(누수 통로). grid는 전류 값이 1.1920929 격자 위에 있는 행 비율
    grid = lambda d: float((np.abs(d[CUR] / 1.1920929 - np.round(d[CUR] / 1.1920929)) < 1e-3).mean())
    facts = dict(
        windows=dict(normal=int(len(tabs[("matched", "window")][0])), abnormal=int(len(tabs[("matched", "window")][1])),
                     normal_records_with_window=int(tabs[("matched", "window")][0]["rec"].nunique()),
                     abnormal_records_with_window=int(tabs[("matched", "window")][1]["rec"].nunique())),
        records=dict(normal=int(nm["rec"].nunique()), abnormal=int(am["rec"].nunique())),
        vib_upper_digits_mean=dict(normal=float(nr["dig_up"].mean()), abnormal=float(ar["dig_up"].mean())),
        vib_upper_digits_gt6_share=dict(normal=float((nr["dig_up"] > 6).mean()), abnormal=float((ar["dig_up"] > 6).mean())),
        current_on_grid_share=dict(normal=grid(nr), abnormal=grid(ar), grid=1.1920929,
                                   note="원본 이상 파일 전류는 모두 1.1920929 격자 위, 정상은 거의 아님 — 진동 자릿수 외 두 번째 형식 누수"),
    )

    rows = []
    # 1. 지도학습 재현. 자료 × 표현 × 모델 3개 × 5겹 그룹 CV × seed 10개
    print("1. 지도학습 재현", flush=True)
    for (variant, rep), (tn, ta, feats) in tabs.items():
        X, y, g = stack(tn, ta, feats)
        rows += run_cv("supervised", variant, rep, X, lambda s, y=y: y, g)

    # 2a. 가짜 라벨. 고장이 없는 정상 파일 안에서 두 집단을 같은 파이프라인으로 가른다.
    # time 판본이 random 판본보다 잘 갈리면 '시간 인접성(세션)'만으로도 분류가 된다는 뜻이다.
    # 기록 단위 그룹 CV는 같은 구간의 이웃 기록을 학습·평가에 나눠 넣어 이 단서를 막지 못한다(이상 21기록도 같은 구조)
    print("2a. 가짜 라벨", flush=True)
    recs = np.arange(nm["rec"].nunique())
    block_starts = {s: int(np.random.default_rng(1000 + s).integers(0, len(recs) - BLOCK + 1)) for s in SEEDS}
    label_sets = {
        "half_time": lambda s: recs[recs >= 300],                                                  # 뒤 38분 vs 앞 38분
        "half_random": lambda s: np.random.default_rng(2000 + s).choice(recs, 300, replace=False),  # 영가설 대조(AUC 0.5 기대)
        "block21_time": lambda s: np.arange(block_starts[s], block_starts[s] + BLOCK),             # 이상 사건 크기의 연속 21기록
        "block21_random": lambda s: np.random.default_rng(3000 + s).choice(recs, BLOCK, replace=False),
    }
    fake_tabs = {"window": (tabs[("matched", "window")][0], WIN_FEATS), "case": (tabs[("matched", "case")][0], CASE_FEATS)}
    for lab, fn in label_sets.items():
        for rep, (tab, feats) in fake_tabs.items():
            X, g = tab[feats].to_numpy(float), tab["rec"].to_numpy()
            rows += run_cv("fake_label", lab, rep, X, lambda s, g=g, fn=fn: np.isin(g, fn(s)).astype(int), g)
    # 2a′ 블록 쌍 분리도 지도. 정상 기록 0~587을 21기록(약 2.7분) 블록 28개로 나누고 모든 블록 쌍(378)을 분류한다.
    # 같은 기준으로 '이상 21기록 vs 각 정상 블록'(28)도 분류해, 같은 날 표류의 크기와 이상-정상 분리를 한 분포 위에서 비교한다
    print("2a'. 블록 쌍 분리도 지도", flush=True)
    nb = len(recs) // BLOCK
    rec_t0 = tabs[("matched", "case")][0].set_index("rec")["t0"]
    pair_rows = []
    for rep in ("window", "case"):
        tn, ta, feats = tabs[("matched", rep)]
        X, y, g = stack(tn, ta, feats)
        blk = np.where(y == 1, -1, g // BLOCK)  # 이상 = -1, 정상 = 블록 번호(28번 이후 12기록은 쓰지 않음)
        tasks = [(i, j) for i in range(nb) for j in range(i + 1, nb)] + [(i, -1) for i in range(nb)]
        for model in MODELS:
            t = time.time()
            res = Parallel(n_jobs=N_JOBS, batch_size=8)(delayed(_pair_one)(X, g, blk, i, j, model) for i, j in tasks)
            for (i, j), r in zip(tasks, res):
                pair_rows.append(dict(exp="block_pair", rep=rep, model=model, block_a=i, block_b=j,
                                      variant="abnormal_vs_block" if j < 0 else "block_vs_block",
                                      block_gap=(j - i) if j >= 0 else np.nan,
                                      minutes_apart=(rec_t0[j * BLOCK] - rec_t0[i * BLOCK]) / 60 if j >= 0 else np.nan, **r))
            print(f"  {rep} {model} ({time.time() - t:.0f}s)", flush=True)
    pair_df = pd.DataFrame(pair_rows)
    pair_summary = block_pair_summary(pair_df)

    # 2b. 고장과 무관해야 할 특징(Tier 0·1)만으로 정상/이상이 갈리는지
    print("2b. 고장 무관 특징", flush=True)
    mt_n, mt_a = meta_table(nm), meta_table(am)
    uni = []
    for f in TIER0 + TIER1:
        a, b = mt_n[f].dropna().to_numpy(), mt_a[f].dropna().to_numpy()
        u = mannwhitneyu(b, a, alternative="two-sided")
        auc = u.statistic / (len(a) * len(b))      # Mann-Whitney U를 표본 수 곱으로 나누면 단변량 ROC-AUC다
        uni.append(dict(feature=f, tier="Tier0" if f in TIER0 else "Tier1", n_normal=len(a), n_abnormal=len(b),
                        median_normal=float(np.median(a)), median_abnormal=float(np.median(b)),
                        auc_abnormal_higher=float(auc), auc_sep=float(max(auc, 1 - auc)), p_mannwhitney=float(u.pvalue)))
    for name, feats in (("Tier0", TIER0), ("Tier1", TIER1), ("Tier0+Tier1", TIER0 + TIER1)):
        X, y, g = stack(mt_n, mt_a, feats)
        rows += run_cv("fault_irrelevant", name, "case", X, lambda s, y=y: y, g)

    # 2c. 순열 중요도. 지도학습 모델과 가짜 라벨(앞/뒤 절반) 모델이 어느 특징·센서 묶음에 기대는지
    print("2c. 순열 중요도", flush=True)
    pi = {}
    for (variant, rep), models in ((("matched", "window"), ["HGB", "RF"]), (("matched", "case"), ["HGB", "RF"]),
                                   (("raw+digits", "window"), ["HGB", "RF"]), (("raw+digits", "case"), ["HGB"])):
        tn, ta, feats = tabs[(variant, rep)]
        X, y, g = stack(tn, ta, feats)
        gm = dict(WIN_GROUPS if rep == "window" else CASE_GROUPS)
        if "digits" in variant:
            gm["소수 자릿수(dig_*)"] = DIG_FEATS
        for model in models:
            t = time.time()
            pi[f"supervised|{variant}|{rep}|{model}"] = perm_importance(X, y, g, feats, gm, model)
            print(f"  {variant} {rep} {model} ({time.time() - t:.0f}s)", flush=True)
    for rep, (tab, feats) in fake_tabs.items():
        X, g = tab[feats].to_numpy(float), tab["rec"].to_numpy()
        y = (g >= 300).astype(int)
        pi[f"fake_label|half_time|{rep}|HGB"] = perm_importance(X, y, g, feats, WIN_GROUPS if rep == "window" else CASE_GROUPS, "HGB")
        print(f"  half_time {rep} HGB", flush=True)

    # 2d. 수집 조건 이동 반응. 보고서 V5와 같은 조작(전류 +81.4·+272.4 이동, 0.1 ms 표본화 흔들림)을 지도학습 모델에 넣는다.
    # 이동 조작은 seed와 무관해 미리 만들고, 흔들림은 seed마다 작업자 안에서 만든다
    print("2d. 수집 조건 이동 반응", flush=True)
    srows = []
    for rep in ("window", "case"):
        tn, ta, feats = tabs[("matched", rep)]
        X, y, g = stack(tn, ta, feats)
        mk = window_table if rep == "window" else case_rep
        fixed = {"none": tn, "cur_shift_+81.4": mk(shift_current(nm, 81.4)), "cur_shift_+272.4": mk(shift_current(nm, 272.4))}
        t = time.time()
        srows += stress_test(nm, X, y, g, rep, feats, fixed)
        print(f"  {rep} ({time.time() - t:.0f}s)", flush=True)

    res = pd.DataFrame(rows)
    sres = pd.DataFrame(srows)
    pd.concat([res, pair_df, sres], ignore_index=True).to_csv(OUT / f"{STEM}.csv", index=False, encoding="utf-8-sig")
    mcols = ["f1", "pr_auc", "roc_auc", "bal_acc"]
    summ = summarize(res, ["exp", "variant", "rep", "model"], mcols)
    ssum = sres.groupby(["variant", "rep", "model"], sort=False).agg(
        alarm_rate_mean=("alarm_rate", "mean"), alarm_rate_sd=("alarm_rate", "std"), records=("records", "first")).reset_index()

    out = dict(
        meta=dict(created="2026-10-04", seeds=SEEDS, n_splits=N_SPLITS, window_rows=WIN, models=MODELS,
                  model_settings=dict(HGB="HistGradientBoosting(max_iter=150, lr=0.1, min_samples_leaf=5, class_weight=balanced) — CatBoost 대체(catboost 미설치)",
                                      RF="RandomForest(n_estimators=200, class_weight=balanced, 중앙값 대치)",
                                      LR="LogisticRegression(class_weight=balanced, 표준화, 중앙값 대치)"),
                  threshold=0.5, metric_note="seed마다 5겹 OOF 확률을 모아 계산, 10 seed 평균±표준편차",
                  window_feats=WIN_FEATS, case_feats=CASE_FEATS, digit_feats=DIG_FEATS, tier0=TIER0, tier1=TIER1,
                  block21_starts=block_starts, block_size=BLOCK, n_blocks=nb,
                  competitor=dict(repo="공개된 지도학습 분석(이름 생략)", f1=0.944),
                  runtime_s=round(time.time() - t_all, 1)),
        facts=facts,
        supervised=summ[summ.exp == "supervised"].to_dict("records"),
        fake_label=summ[summ.exp == "fake_label"].to_dict("records"),
        block_pair=pair_summary,
        fault_irrelevant=dict(univariate=uni, multivariate=summ[summ.exp == "fault_irrelevant"].to_dict("records")),
        permutation_importance=pi,
        stress=ssum.to_dict("records"),
    )
    (OUT / f"{STEM}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    write_md(out)
    print(f"완료 {time.time() - t_all:.0f}s", flush=True)


# ───────────────────────── 요약 md ─────────────────────────
def ms(r, k, d=3):
    """'평균 ± 표준편차' 문자열."""
    return f"{r[f'{k}_mean']:.{d}f} ± {r[f'{k}_std']:.{d}f}"


def _one(rows, **kw):
    """조건에 맞는 요약 행을 하나 찾는다. 0개나 2개 이상이면 멈춘다."""
    hit = [r for r in rows if all(r.get(k) == v for k, v in kw.items())]
    assert len(hit) == 1, (kw, len(hit))
    return hit[0]


def _by_model(rows, metric, d=3, sd=True, **kw):
    """HGB / RF / LR 값을 ' / '로 잇는다. sd=False면 평균만."""
    return " / ".join((ms(_one(rows, model=m, **kw), metric, d) if sd else f"{_one(rows, model=m, **kw)[metric + '_mean']:.{d}f}")
                      for m in MODELS)


def render(out: dict) -> str:
    """JSON 결과로 요약 md를 만든다. 문장 틀은 고정이고 수치만 결과에서 채운다."""
    # 부록·본문에 그대로 넣는 전체 표
    L = []
    L.append("| 자료 | 표현 | 모델 | 표본(이상) | F1 | PR-AUC | ROC-AUC | balanced acc |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in out["supervised"]:
        L.append(f"| {r['variant']} | {r['rep']} | {r['model']} | {r['n']}({r['n_pos']}) | {ms(r, 'f1')} | {ms(r, 'pr_auc')} | {ms(r, 'roc_auc')} | {ms(r, 'bal_acc')} |")
    sup = "\n".join(L)
    L = ["| 가짜 라벨 | 표현 | 모델 | 양성 비율 | ROC-AUC | PR-AUC | F1 | balanced acc |", "|---|---|---|---|---|---|---|---|"]
    for r in out["fake_label"]:
        L.append(f"| {r['variant']} | {r['rep']} | {r['model']} | {r['prevalence']:.3f} | {ms(r, 'roc_auc')} | {ms(r, 'pr_auc')} | {ms(r, 'f1')} | {ms(r, 'bal_acc')} |")
    fake = "\n".join(L)
    L = ["| 표현 | 모델 | 정상 블록 쌍 AUC 중앙값 [10%, 90%] | 정상 쌍 AUC ≥ 0.9 비율 | 간격별 중앙값 (1 / 2-4 / 5-9 / 10-19 / 20-27 블록) | 이상 vs 정상 블록 AUC 중앙값 (최소) |",
         "|---|---|---|---|---|---|"]
    for r in out["block_pair"]:
        gaps = " / ".join(f"{r[f'bb_auc_median_gap{lo}-{hi}']:.2f}" for lo, hi in GAP_BINS)
        L.append(f"| {r['rep']} | {r['model']} | {r['bb_auc_median']:.3f} [{r['bb_auc_q10']:.2f}, {r['bb_auc_q90']:.2f}] | "
                 f"{r['bb_share_auc_ge_0_9']:.3f} | {gaps} | {r['ab_auc_median']:.3f} ({r['ab_auc_min']:.3f}) |")
    dist = "\n".join(L)
    L = ["| 특징 | 묶음 | 중앙값 정상 | 중앙값 이상 | 단변량 AUC(방향 무관) | Mann-Whitney p |", "|---|---|---|---|---|---|"]
    for r in out["fault_irrelevant"]["univariate"]:
        L.append(f"| {r['feature']} | {r['tier']} | {r['median_normal']:.3g} | {r['median_abnormal']:.3g} | {r['auc_sep']:.3f} | {r['p_mannwhitney']:.2g} |")
    uni = "\n".join(L)
    L = ["| 특징 묶음 | 모델 | ROC-AUC | PR-AUC | F1 | balanced acc |", "|---|---|---|---|---|---|"]
    for r in out["fault_irrelevant"]["multivariate"]:
        L.append(f"| {r['variant']} | {r['model']} | {ms(r, 'roc_auc')} | {ms(r, 'pr_auc')} | {ms(r, 'f1')} | {ms(r, 'bal_acc')} |")
    multi = "\n".join(L)
    L = ["| 설정 | 묶음 순열 중요도(PR-AUC 감소, 큰 순) | 단일 특징 상위 3 |", "|---|---|---|"]
    for k, v in out["permutation_importance"].items():
        grp = " · ".join(f"{g} {d['mean']:.3f}" for g, d in v["grouped"].items())
        top = " · ".join(f"{f} {d['mean']:.3f}" for f, d in list(v["single"].items())[:3])
        L.append(f"| {k.replace('|', ' / ')} | {grp} | {top} |")
    pim = "\n".join(L)
    L = ["| 조작 | 표현 | 모델 | 정상 기록 경보율 | 기록 수 |", "|---|---|---|---|---|"]
    for r in out["stress"]:
        L.append(f"| {r['variant']} | {r['rep']} | {r['model']} | {r['alarm_rate_mean']:.3f} ± {r['alarm_rate_sd']:.3f} | {r['records']} |")
    stress = "\n".join(L)

    S, FK, FI, ST, BP = out["supervised"], out["fake_label"], out["fault_irrelevant"], out["stress"], out["block_pair"]
    fx = out["facts"]

    def rng_(rows, metric, **kw):           # 세 모델 평균값의 (최소, 최대)
        v = [_one(rows, model=m, **kw)[metric + "_mean"] for m in MODELS]
        return min(v), max(v)

    # 1. 지도학습 압축 표
    t1 = ["| 자료 | 표현 | 표본 (이상) | F1 (HGB / RF / LR) | PR-AUC (HGB / RF / LR) |", "|---|---|---|---|---|"]
    for v in ("matched", "raw", "raw+digits", "raw digits-only"):
        for rep in ("window", "case"):
            r0 = _one(S, variant=v, rep=rep, model="HGB")
            t1.append(f"| {v} | {rep} | {r0['n']} ({r0['n_pos']}) | {_by_model(S, 'f1', variant=v, rep=rep)} | "
                      f"{_by_model(S, 'pr_auc', sd=False, variant=v, rep=rep)} |")
    # 2a 가짜 라벨 압축 표
    t2 = ["| 가짜 라벨 | 표현 | 양성 비율 | ROC-AUC (HGB / RF / LR) | PR-AUC (HGB / RF / LR) |", "|---|---|---|---|---|"]
    for v in ("half_time", "half_random", "block21_time", "block21_random"):
        for rep in ("window", "case"):
            r0 = _one(FK, variant=v, rep=rep, model="HGB")
            t2.append(f"| {v} | {rep} | {r0['prevalence']:.3f} | {_by_model(FK, 'roc_auc', variant=v, rep=rep)} | "
                      f"{_by_model(FK, 'pr_auc', sd=False, variant=v, rep=rep)} |")
    # 2b 다변량 압축 표
    t5 = ["| 특징 묶음 | ROC-AUC (HGB / RF / LR) | PR-AUC (HGB / RF / LR) | F1 (HGB / RF / LR) |", "|---|---|---|---|"]
    for v in ("Tier0", "Tier1", "Tier0+Tier1"):
        t5.append(f"| {v} | {_by_model(FI['multivariate'], 'roc_auc', variant=v)} | "
                  f"{_by_model(FI['multivariate'], 'pr_auc', sd=False, variant=v)} | "
                  f"{_by_model(FI['multivariate'], 'f1', sd=False, variant=v)} |")
    # 2d 압축 표
    v5 = {"none": "—", "cur_shift_+81.4": "A 0/120 (0%) · B 7/180 (3.9%)", "cur_shift_+272.4": "A 118/120 · B 180/180",
          "jitter_0.1ms_60.6Hz": "A 8.8% · B 35.2%"}
    t7 = ["| 조작 (정상 평가 기록, 17행 이상) | window 경보율 (HGB / RF / LR) | case 경보율 (HGB / RF / LR) | 보고서 V5 (우리 정상 학습 모델) |",
          "|---|---|---|---|"]
    for v in STRESS:
        cell = lambda rep: " / ".join(f"{_one(ST, variant=v, rep=rep, model=m)['alarm_rate_mean']:.3f}" for m in MODELS)
        t7.append(f"| {v} | {cell('window')} | {cell('case')} | {v5[v]} |")

    mw = rng_(S, "f1", variant="matched", rep="window")
    mc = rng_(S, "f1", variant="matched", rep="case")
    mwp = rng_(S, "pr_auc", variant="matched", rep="window")
    rw = rng_(S, "f1", variant="raw", rep="window")
    dg = rng_(S, "f1", variant="raw digits-only", rep="window")
    ht = rng_(FK, "roc_auc", variant="half_time", rep="window")
    htc = rng_(FK, "roc_auc", variant="half_time", rep="case")
    hr = rng_(FK, "roc_auc", variant="half_random", rep="window")
    hrc = rng_(FK, "roc_auc", variant="half_random", rep="case")
    bt = rng_(FK, "roc_auc", variant="block21_time", rep="window")
    btc = rng_(FK, "roc_auc", variant="block21_time", rep="case")
    br = rng_(FK, "roc_auc", variant="block21_random", rep="window")
    brc = rng_(FK, "roc_auc", variant="block21_random", rep="case")
    t0 = rng_(FI["multivariate"], "roc_auc", variant="Tier0")
    t1r = rng_(FI["multivariate"], "roc_auc", variant="Tier1")
    span = lambda key: (min(r[key] for r in BP), max(r[key] for r in BP))  # 표현·모델 6조합의 (최소, 최대)
    bb_far, bb_adj, bb_share = span("bb_auc_median_gap20-27"), span("bb_auc_median_gap1-1"), span("bb_share_auc_ge_0_9")
    ab_med, ab_pct = span("ab_auc_median"), span("ab_median_percentile_in_bb")
    far_min = _one(BP, rep="window", model="RF")["minutes_gap20-27"]
    far_share, far_q75, far_lo = span("bb_share_ge_0_9_gap20-27"), span("bb_auc_q75_gap20-27"), span("bb_auc_min_gap20-27")
    ab_min = span("ab_auc_min")
    top2 = "`·`".join(list(out["permutation_importance"]["supervised|matched|window|HGB"]["single"])[:2])

    def pr(vals):  # 비율 목록을 '0%' 또는 'a%~b%'로
        return "0%" if max(vals) == 0 else f"{min(vals):.1%}~{max(vals):.1%}"
    sh81w = [_one(ST, variant="cur_shift_+81.4", rep="window", model=m)["alarm_rate_mean"] for m in MODELS]
    sh81c = [_one(ST, variant="cur_shift_+81.4", rep="case", model=m)["alarm_rate_mean"] for m in MODELS]
    jw = [_one(ST, variant="jitter_0.1ms_60.6Hz", rep="window", model=m)["alarm_rate_mean"] for m in MODELS]
    jc = [_one(ST, variant="jitter_0.1ms_60.6Hz", rep="case", model=m)["alarm_rate_mean"] for m in MODELS]
    pi = out["permutation_importance"]
    g_mw = pi["supervised|matched|window|HGB"]["grouped"]
    g_mc = pi["supervised|matched|case|HGB"]["grouped"]
    g_dg = pi["supervised|raw+digits|window|HGB"]["grouped"]
    ud = {r["feature"]: r for r in FI["univariate"]}
    f2 = lambda t: f"{t[0]:.2f}~{t[1]:.2f}"
    f3 = lambda t: f"{t[0]:.3f}~{t[1]:.3f}"
    nl = "\n"

    return f"""---
title: 프레스 — 지도학습 재현과 세션 교락 시험
created: 2026-10-04
updated: 2026-10-04
tags: [contest/k-ai-manufacturing]
source: Claude Code 세션 2026-10-04 (공개된 지도학습 분석 방식 재현 + 교락 대조 실험)
status: seed
---

# 지도학습 재현과 세션 교락 시험

> 상위: [[제조데이터 경진대회 MOC]] · 코드 `code/press/domain/05_supervised_confound.py` · 수치 `outputs/05_supervised_confound.json`·`.csv`

**한 줄 결론**: 형식 누수를 지운 자료로도 라벨로 학습하면 F1 {min(mw[0], mc[0]):.2f}~{max(mw[1], mc[1]):.2f}이 쉽게 나온다(공개 분석 0.944와 같은 수준). 그런데 같은 파이프라인이 **고장이 전혀 없는 같은 날 정상 구간끼리도** 간격이 1시간쯤 벌어지면 ROC-AUC 중앙값 {f2(bb_far)}로 가른다. 이상-정상 분리({f2(ab_med)})는 이보다 크고 한결같지만, 정상과 이상은 5일 떨어진 다른 세션이다. 따라서 지도학습 고득점으로는 '고장 탐지 능력'과 '세션(날짜·운전 조건·수집 설정) 구분 능력'을 가를 수 없다.

## 실행

```bash
cd code/press/domain
PYTHONIOENCODING=utf-8 python 05_supervised_confound.py            # 전체 (약 {out['meta']['runtime_s'] / 60:.0f}분, 10프로세스 병렬)
PYTHONIOENCODING=utf-8 python 05_supervised_confound.py --md-only  # 이 문서만 다시 쓰기
```

- 모델: catboost가 설치돼 있지 않아 CatBoost 대신 **sklearn HistGradientBoosting**(HGB)을 썼다. RandomForest(RF)·LogisticRegression(LR)도 함께 돌렸다. 셋 다 class_weight=balanced, 문턱 0.5
- 검증: StratifiedGroupKFold 5겹(그룹 = 기록) × seed 10개(0~9). seed마다 OOF 확률을 모아 지표를 계산하고 평균 ± 표준편차를 냈다
- 표현: window = 기록 안 비중첩 1초(10행) 창의 센서별 mean/std/RMS/min/max 15개(정상 {fx['windows']['normal']}창/{fx['windows']['normal_records_with_window']}기록, 이상 {fx['windows']['abnormal']}창/{fx['windows']['abnormal_records_with_window']}기록. 10행 미만 기록은 창이 없다). case = `common.case_table` 기록 특징 10개(n·t0 제외, 정상 600·이상 21기록)

## 1. 공개된 방식의 지도학습 재현

{nl.join(t1)}

- 형식 누수를 지운 matched 자료에서 window F1 {f3(mw)}(PR-AUC {f3(mwp)}), case F1 {f3(mc)}이다. 공개 분석 F1 0.944와 같은 수준이다
- 원본 그대로(raw)의 창 통계도 F1 {f3(rw)}로 matched와 거의 같다. 창 통계를 받는 트리·선형 모델은 값의 크기로만 나누므로 자릿수 정보를 쓰지 못한다. **공개된 방식의 창 통계 점수는 자릿수 누수 때문이 아니다**
- 자릿수 특징을 넣으면 1.000에 붙는다. 자릿수 2개만으로도 F1 {f3(dg)}이다. 원본 이상 파일 상부 진동은 {fx['vib_upper_digits_gt6_share']['abnormal']:.1%}가 7자리 이상이고, 정상은 {fx['vib_upper_digits_gt6_share']['normal']:.3%}다
- 형식 누수 통로가 하나 더 있다. **원본 이상 파일 전류는 {fx['current_on_grid_share']['abnormal']:.0%}가 1.1920929 격자 위**에 있고, 정상은 {fx['current_on_grid_share']['normal']:.2%}만 그렇다. matched에서는 둘 다 격자로 맞춰 지워진다

## 2. 세션 교락 시험

### 2a. 가짜 라벨 — 같은 날 정상끼리 나눠도 갈리나

{nl.join(t2)}

- 정상 파일 안 **앞 절반 vs 뒤 절반**(각 약 38분)은 ROC-AUC window {f2(ht)}, case {f2(htc)}로 갈린다. 무작위 절반 대조는 window {f2(hr)}, case {f2(hrc)}이다. 고장이 없는데도 시간대만으로 분류가 된다
- **연속 21기록(약 2.7분) vs 나머지 579기록**은 window {f3(bt)}, case {f3(btc)}이다. 무작위 21기록 대조(window {f3(br)}, case {f3(brc)})보다 조금 높을 뿐이다. 대신 seed(블록 위치)에 따라 표준편차가 약 0.14로 크게 흔들린다. 같은 날 안에서는 3분 블록 하나를 나머지 75분 전체에서 골라내기 어렵고, 잘 갈리는 위치가 따로 있다는 뜻이다(2a′에서 쌍 단위로 다시 본다)

### 2a′. 블록 쌍 분리도 지도 — 시간 간격이 벌어지면 얼마나 갈리나

정상 기록 0~587을 21기록 블록 28개로 나누고, 모든 쌍 378개를 같은 파이프라인(seed 0)으로 분류했다. 같은 방식으로 이상 21기록 vs 각 정상 블록 28쌍도 분류했다.

{dist}

- 같은 날 정상끼리도 **간격이 벌어질수록 잘 갈린다**. 인접 블록은 중앙값 {f2(bb_adj)}(우연 수준)이다. 20~27블록(약 {far_min:.0f}분) 떨어지면 {f2(bb_far)}까지 오른다. 정상 블록 쌍의 {bb_share[0]:.0%}~{bb_share[1]:.0%}가 AUC 0.9 이상이다
- 이상 vs 정상 블록은 중앙값 {f2(ab_med)}이다. 정상끼리 분포의 {ab_pct[0]:.0%}~{ab_pct[1]:.0%} 분위로 상단에 있다. 약 1시간 떨어진 정상 쌍은 {far_share[0]:.0%}~{far_share[1]:.0%}가 AUC 0.9 이상이고, 그 상위 25% 경계는 {f2(far_q75)}이다. 값의 크기만 보면 이상-정상 분리와 겹친다
- 차이도 있다. 이상은 정상 28블록 **모두**와 일관되게 갈린다(최소 {f3(ab_min)}). 정상끼리는 같은 1시간 간격에서도 최소 {f2(far_lo)}까지 내려가 들쭉날쭉하다. 즉 이상-정상 차이는 '같은 날 안의 표류'보다 크고 한결같다. 그 원인이 고장인지, 5일 간격 세션 차이인지는 이 비교로 가를 수 없다
- 정상과 이상은 **5일**(약 7,200분) 떨어져 있다. 이 데이터 안에서 볼 수 있는 최대 간격은 약 75분이고, 그 안에서 이미 분리도가 간격과 함께 커진다. 5일 간격의 세션 차이만으로 얼마가 나오는지는 이 데이터로 잴 수 없다. 이것이 교락의 핵심이다

### 2b. 고장과 무관해야 할 특징만으로 정상/이상 분류

근거(상세는 스크립트 docstring):

- **Tier 0 — 정의상 고장 무관(로거가 정하는 수집 메타데이터)**: 기록 길이 n, 직전 기록과의 공백 gap_prev, 기록 시작 시각의 0.1초 격자 위상(clock), 시작 시각을 0.6064 Hz 시계로 본 위상(tphase)
- **Tier 1 — 조건부 고장 무관(가정: 모터가 60 Hz 계통에 직결)**: 전류 절편/진폭 비, 전류 겉보기 주파수, 0.6 Hz 사인의 기록 시작 위상
  - 교류 전류는 물리적으로 평균이 0이다. 절편이 0에서 벗어나는 건 겉보기 주파수와 기록 길이가 맞지 않거나 센서에 DC 편차가 있을 때다
  - 겉보기 주파수는 60 Hz를 10 Hz로 찍은 앨리어스라서 전원 주파수와 표본화 간격이 정한다
  - 단, 인버터 고장처럼 실제 DC 성분을 만드는 고장도 있다. 또 이상 파일 전류는 사인 꼴이 아니라서(R² 중앙값 약 0.1) 주파수 추정치에 파형 붕괴가 함께 섞인다

{uni}

{nl.join(t5)}

- **Tier 0으로는 갈리지 않는다**(ROC-AUC {f2(t0)}). 단변량에서는 gap_prev(정상 중앙값 {ud['gap_prev']['median_normal']:.2f}초 vs 이상 {ud['gap_prev']['median_abnormal']:.2f}초, AUC {ud['gap_prev']['auc_sep']:.2f}, p={ud['gap_prev']['p_mannwhitney']:.2g})만 약한 차이를 보인다. 트리 모델의 0.5 미만 값은 신호가 없을 때 양성이 적은 교차검증에서 생기는 역학습(anti-learning) 효과다. 로거 메타데이터 자체는 누수 통로가 아니다
- **Tier 1로는 거의 완전히 갈린다**(ROC-AUC {f2(t1r)}). 전류 절편 비 단독 AUC {ud['cur_offset_abs']['auc_sep']:.3f}(중앙값 {ud['cur_offset_abs']['median_normal']:.3f} vs {ud['cur_offset_abs']['median_abnormal']:.2f}), 겉보기 주파수 {ud['cur_freq_hat']['auc_sep']:.3f}(정상 {ud['cur_freq_hat']['median_normal']:.3f} Hz vs 이상 {ud['cur_freq_hat']['median_abnormal']:.3f} Hz)
- 직결 구동이라면 두 값은 수집 타이밍(표본화 간격·전원 주파수)이 정하므로, 이 분리는 '세션 단서'다. 반대로 파형 붕괴가 고장 때문이라면 '고장 신호'다. **데이터만으로는 어느 쪽인지 가를 수 없고, 그 자체가 교락의 증거다**

### 2c. 순열 중요도 — 지도학습 모델은 무엇에 기대나

평가 겹에서 열을 섞었을 때 PR-AUC가 줄어든 양이다(seed 0~2 × 5겹 평균). 묶음은 센서(또는 특징 묶음) 단위로 함께 섞은 값이다.

{pim}

- matched window 모델(HGB)은 상부진동 묶음({g_mw['상부진동(up_*)']['mean']:.2f})과 전류 묶음({g_mw['전류(cur_*)']['mean']:.2f})에 기댄다. 단일 특징 상위 둘은 `{top2}`이다. 창 안 전류 최솟값·최댓값에는 사인 진폭과 **DC 오프셋**이 함께 담긴다. 이상 파일의 큰 오프셋은 2b의 Tier 1(세션 단서일 수 있는 값)과 같은 정보다
- matched case 모델(HGB)은 전류 파형 묶음(R²·잔차·절편 비, {g_mc['전류 파형']['mean']:.2f})에 거의 전부 기댄다. 이 값도 겉보기 주파수가 바뀌면(측정 타이밍 가설) 그대로 재현된다
- raw+digits 모델(HGB)에서는 자릿수 묶음이 {g_dg['소수 자릿수(dig_*)']['mean']:.2f}이고, 나머지 센서는 0에 가깝다. 쉬운 누수가 있으면 모델은 물리 신호보다 그것을 먼저 쓴다
- 가짜 라벨(앞/뒤 절반) 모델은 전류·진동의 크기와 모양을 고루 쓴다. 같은 날 안의 시간 표류도 센서 하나가 아니라 운전 상태 전반에 퍼져 있다

### 2d. 수집 조건 이동 반응 — 보고서 V5와 같은 조작을 지도학습 모델에

matched 지도학습 모델을 5겹 학습 겹으로 적합했다. 평가 겹의 정상 기록(17행 이상)을 조작해 넣고, 이상으로 판정된 기록 비율을 쟀다(window = 창 하나라도 p ≥ 0.5, case = 기록 p ≥ 0.5, seed 10개 평균).

{nl.join(t7)}

- 공개된 방식의 창 통계 모델은 **전류를 +81.4 옮기기만 해도 정상 기록의 {min(sh81w):.0%}~{max(sh81w):.0%}를 이상으로 판정**한다. 이 조작은 센서 오프셋·영점 변화 같은 수집 조건 변화에 해당한다. 같은 이동에서 우리 정상 학습 모델은 A 0%·B 3.9%였다(보고서 V5)
- 반대로 0.1 ms 표본화 시각 흔들림에는 창 통계 모델이 둔감하다({pr(jw)}, 조작 없을 때와 같은 수준). 창 통계는 위상·파형 정보를 보지 않는다. 우리 모델은 이 조작에 민감했다(A 8.8%·B 35.2%)
- case 지도학습 모델은 두 조작 모두에 둔감했다(+81.4 이동 {pr(sh81c)}, 흔들림 {pr(jc)}). 이 모델은 이동에 둔감한 전류 사인 R²에 기댄다(2c). 0.1 ms 흔들림으로는 R²가 이상 수준(≤0.62)까지 떨어지지 않는다
- 어느 방식이든 **어떤 수집 조건 변화에는 민감하다**. 지도학습이라고 수집 조건 문제에서 자유롭지 않다. 민감한 방향만 다르다
- 비교 주의: V5는 시간순 test 정상 기록(A 120, B 180)을 1단계 경보 기준으로 쟀고, 여기서는 5겹 평가 겹의 정상 기록 469개를 쟀다. 흔들림 생성도 기록별 적합 주파수 대신 고정 F0(0.6064 Hz)를 썼다

## 3. 해석 — 왜 정상만 학습 + 형식 누수 제거 + 시간순 분할인가

1. **지도학습 고득점은 이 데이터에서 '고장 탐지 능력'의 증거가 될 수 없다.** 라벨(정상/이상)이 날짜·요일·시각대·저장 형식, 그리고 아마도 운전 조건과 완전히 겹친다. 이상 사건이 하나뿐이라 세션을 그룹으로 두면 이상 그룹이 1개다. 그래서 세션 단위 교차검증(leave-one-session-out)이 원리적으로 불가능하다. 기록 단위 그룹 CV는 같은 사건의 이웃 조각을 학습·평가 양쪽에 넣으므로 세션 단서를 막지 못한다
2. 같은 파이프라인이 **고장 없는 같은 날 정상 구간끼리도** 1시간 간격이면 AUC 중앙값 최대 {bb_far[1]:.2f}로 가른다(2a′). 앞/뒤 절반도 최대 {ht[1]:.2f}이다(2a). 5일 떨어진 세션끼리라면 고장이 없어도 높은 점수가 나올 수 있다. 관측된 이상-정상 분리(AUC {f2(ab_med)})는 같은 날 표류보다 크고 한결같다. 하지만 5일 간격 세션 차이의 범위를 넘는지는 이 데이터로 판정할 수 없다
3. 가장 강한 분리 특징(전류 오프셋·겉보기 주파수·파형 R²)은 수집 타이밍 가설로도 설명된다(2b). 지도학습 모델은 실제로 여기에 기댄다(2c)
4. 그래서 우리 파이프라인은 세 가지를 택했다
   - **정상만 학습**: 라벨을 학습에 쓰지 않는다. 그러면 이상 세션 고유의 특이점(오프셋 크기, 자릿수, 격자 등)을 외워 맞히는 경로가 막힌다. 경보 기준은 정상 분포만으로 정한다. 가이드북이 안내하는 방식과도 같다
   - **형식 누수 제거**(정밀도 맞춤): 자릿수 2개만으로 F1 {dg[0]:.3f}이고, 전류 격자 비율은 {fx['current_on_grid_share']['abnormal']:.0%} 대 {fx['current_on_grid_share']['normal']:.2%}다. 지우지 않으면 어떤 모델이든 이것부터 쓴다(2c)
   - **시간순 분할**: 같은 날 안에서도 간격이 벌어질수록 분포가 달라진다(2a′). 무작위 분할이나 기록 단위 분할은 평가를 낙관적으로 만든다. 시간순 분할은 미래 구간에 대한 일반화를 그대로 잰다

## 4. 한계

- **정상만 학습한 우리 모델도 세션 차이를 완전히 배제하지 못한다.** 이상 점수는 '학습한 정상 분포에서 얼마나 먼가'를 잰다. 날짜나 수집 설정이 바뀐 정상도 멀게 나타난다. 보고서 V5에서도 **수집 조건에 민감**했다(전류 수준 +81.4 이동에 B 3.9%, 0.1 ms 표본화 흔들림에 정상 기록 경보율 A 8.8%·B 35.2%). 이상 파일의 전류 파형 붕괴가 고장 때문인지 계측 때문인지는 여전히 분리되지 않는다. Tier 1 결과와 같은 문제다
- 이 시험이 보인 것은 '지도학습 점수로는 가를 수 없다'까지다. '정상 학습이 고장을 잡았다'는 적극적 증거는 아니다. 이를 가르려면 같은 날·같은 수집 설정의 정상-이상 자료나, 다른 날 정상 자료(세션 간 표류 측정)가 필요하다
- 블록 쌍 지도는 75분 안의 표류만 잰다. 5일 간격으로 외삽하는 것은 검증할 수 없다. 블록 쌍은 seed 0 하나로 쟀다(쌍 378개가 반복 역할을 한다)
- 공개 분석의 CatBoost를 sklearn HGB로 대체했다. 창은 기록 안 비중첩 10행으로 정했다(공개 분석의 정확한 창 구성은 확인하지 않았다). 수치가 같은 수준이라는 것이지 정확히 재현했다는 뜻은 아니다
- Tier 분류는 '직결 구동' 가정에 기댄다. 인버터 구동이면 겉보기 주파수가 운전 지령(운전 조건)에 따라 바뀐다. 그 경우에도 고장 고유 신호는 아니다
- 이상은 단일 사건(21기록, 약 3분)이다. 모든 지도학습 수치는 이 사건 하나에 대한 것이다

## 부록 A. 지도학습 전체 표 (평균 ± 표준편차, 10 seed)

{sup}

## 부록 B. 가짜 라벨 전체 표

{fake}

## 부록 C. 고장 무관 특징 다변량 전체 표

{multi}

## 부록 D. 수집 조건 이동 반응 전체 표

{stress}
"""


def write_md(out: dict):
    """요약 md를 쓴다. --md-only면 저장된 JSON에서 이것만 다시 돈다."""
    (OUT / f"{STEM}_summary.md").write_text(render(out), encoding="utf-8")


if __name__ == "__main__":
    if "--md-only" in sys.argv:
        write_md(json.loads((OUT / f"{STEM}.json").read_text(encoding="utf-8")))
    else:
        main()
