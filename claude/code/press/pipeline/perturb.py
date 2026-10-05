"""계측 섭동 강건성 곡선 — 전류 파형 성분이 계측 조건 차이에 얼마나 민감한가.

목적: 정상 평가 구간 전류에 계측 섭동을 넣고, 깨끗한 데이터로 정한 문턱에서 정상 알림 구간 비율이 얼마나 늘어나는지 잰다.
    대상은 최종 모델(fused_acat)과 사인 성분 단독(-log10 p_sine). 이상 데이터는 쓰지 않는다(어떤 설정도 이상 라벨을 보지 않는다).
핵심 가정 — 전원 앨리어싱 (데이터로 검증되지 않음):
- 0.1초 간격 전류가 구간마다 0~5Hz 단일 사인(앨리어스 f_a, 긴 구간 중앙값 약 0.6Hz)으로 잘 맞는다. 이것을 60Hz 계통
  전류가 10Hz 표본화에서 접힌 결과로 보고 참 주파수를 60±f_a Hz로 가정한다. 기본은 f_true = f_a+60.
- diagnosis.md 기록대로 타임스탬프가 명목 100ms라 실제 샘플 간격으로 이 가정을 확인할 수 없다. 지터·주기 오프셋 결과는
  전부 이 가정 아래의 조건부 값이다. perturb_curve.csv 의 f_true_assumption·mains_offset_hz 열에 행마다 가정을 적는다.
- 대조 조건 (같은 난수·같은 격자):
    jitter, period_offset                        f_true = f_a+60  (기본 가정)
    jitter_sign_flip, period_offset_sign_flip    f_true = 60−f_a  (부호 반전)
    jitter_control_no_alias                      f_true = f_a     (앨리어싱 없음)
  f_a+60k (k≥2), 10kHz대 접힘 같은 다른 차수는 보지 않는다.
- 구현: 부호 있는 주파수 f_a+m (m = +60, −60, 0)으로 다시 뽑는다. m=−60 은 |f| = 60−f_a Hz이고, 명목 시각 i·0.1초에서
  sin(2π(f_a−60)·0.1i) = sin(2π f_a·0.1i)라 피팅 계수를 그대로 쓴다(검사 nominal_resample_identity_maxabs).
방법:
- 분할 normal_60_20_20. 깨끗한 학습 구간으로 Scorer(w=8)·Fusion 적합, 깨끗한 보정 구간 기록구간 최댓값으로
  conformal 문턱(α=1%, 5%)을 모델마다 만든다. 섭동은 평가 구간 AI2_Current에만 넣는다(진동·타임스탬프는 그대로)
- 지터·주기 오프셋: 구간마다 전류를 단일 사인(0~5Hz 격자, f_a)+상수로 피팅하고, 참 신호를 위 가정의 사인으로 본다
  (0.1초 간격에서 같은 표본). 표본 시각을 t_i+ε_i (ε~N(0,σ)) 또는 i·(0.1+δ)로 바꿔 다시 뽑고, 피팅 잔차는 그대로 더한다
- 지터는 시드 0 공통 난수 5회. σ끼리, 가정끼리 같은 ε 모양을 크기만 바꿔 쓴다. 반복 간 alarm_segment_fraction_sd 는
  표본 sd(ddof=1, 반복 1회면 NaN)이고 reps_exceeding_alpha 는 α를 넘은 반복 수다. 이 sd는 고정된 평가 120구간 위의
  지터 난수 변동뿐이며 평가 표본 변동은 들어 있지 않다
- 재양자화(1.1920929 격자), 이득 ×g, 오프셋 +o. 사인+상수 적합은 아핀 불변이라 사인 1−R²가 그대로여야 한다(검사)
- 허용 지터 = (kind, 모델, α)마다 정상 알림 구간 비율(5회 평균)이 α를 처음 넘는 σ (지정 격자 위 값). 0.01·0.02·0.05ms는
  보조 격자로 tolerance_sigma_ms_fine 에 따로 적는다. 격자 안(σ≤3ms)에서 한 번도 넘지 않으면 NaN(= 3ms 초과)
- 주기 오프셋 행에는 유효 앨리어스 주파수 f_a + (f_a+m)·δ/0.1 (f_a=긴 구간 중앙값)을 적는다. m의 부호에 따라 δ 방향이 뒤집힌다
- 8관측 창의 SST·SSE 중앙값(sine_window_sst_median, sine_window_sse_median, SSE = (1−R²)·SST)을 함께 적어
  1−R² 변화가 창 내 분산 변화인지 잔차 변화인지 나눠 볼 수 있게 한다
- 검사값은 실제 계산값으로 perturb_checks.json 에 저장하고 assert 한다(python -O 에서도 파일의 값은 그대로 맞다)
한계:
- 앨리어싱 가정(위). 주기 오프셋 결과는 참 주파수 부호에 따라 δ↔−δ로 뒤집히고, f_true=f_a 대조에서는 지터 영향이
  훨씬 작다. 따라서 '허용 지터 수십 μs'는 센서·모델의 성질이 아니라 이 가정에 따른 조건부 결론이다
- 지터는 전류 채널에만 적용했다. 실제 ADC 클럭 지터는 진동 채널에도 동시에 걸리지만 여기선 반영하지 않았다
  (최종 모델 곡선은 진동 성분이 지터의 영향을 받지 않는다는 가정을 깐다)
- 섭동 아래의 탐지력(이상 구간 탐지)은 평가하지 않았다. 여기 값은 정상 알림 증가뿐이다. 섭동 조건에서 문턱을 다시
  보정하면 알림 비율은 α로 돌아가지만 그만큼 탐지력이 변하며, 그 크기는 모른다
- 길이 10 미만 구간은 주파수를 긴 구간 f_a 중앙값으로 고정하고, 관측 3개 미만은 최소노름 해라 참 신호 복원이 임의적이다
- 8관측보다 짧은 평가 구간(검사 segments_shorter_than_w)은 사인 점수가 없어 사인 단독 알림 비율의 상한이 그만큼 낮다.
  최종 모델은 그 구간에서도 다른 성분(maxz·knn5·ae5)으로 알림이 날 수 있으므로 같은 이유로 설명되지 않는다
- 지터는 독립 정규, 잔차는 시각 이동 없이 그대로 더한 단순 모형. 평가 구간 120개라 비율 해상도가 1/120
- 문턱은 깨끗한 보정 구간 기준이다
"""
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")  # MLP 수치 재현 — numpy import 전에 둔다

import json  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import DEFAULT_ROOT, load, load_vendor, split_sets  # noqa: E402
from evaluate import conformal_cutoff  # noqa: E402
from fusion import LN10, Fusion  # noqa: E402
from scores import FREQS, Scorer, _window_index  # noqa: E402

plt.rcParams["font.family"] = [f for f in ("Malgun Gothic", "AppleGothic", "NanumGothic")
                               if f in {x.name for x in font_manager.fontManager.ttflist}] + ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "outputs" / "pipeline"
SPLIT = "normal_60_20_20"
W = 8
NAMES = ["maxz", "knn5", "ae5", f"sine_{W}"]
MODELS = ("fused_acat", "sine_only")
ALPHAS = (0.01, 0.05)
SEED, REPS = 0, 5
MAINS = 60.0
# 참 주파수 가정: 부호 있는 주파수 f_a + m. kind → (m, 표기). 여기 없는 kind는 시각을 건드리지 않는다
ASSUME = {"jitter": (MAINS, "f_a+60"), "period_offset": (MAINS, "f_a+60"),
          "jitter_sign_flip": (-MAINS, "60-f_a"), "period_offset_sign_flip": (-MAINS, "60-f_a"),
          "jitter_control_no_alias": (0.0, "f_a (no alias)")}
JITTER_KINDS = ("jitter", "jitter_sign_flip", "jitter_control_no_alias")
MIN_FIT = 10
Q_CUR = 1.1920929
JITTER_MS = (0, 0.1, 0.2, 0.5, 1, 2, 3)
JITTER_FINE_MS = (0.01, 0.02, 0.05)  # 보조 격자 (허용 지터가 0.1ms 아래일 때 위치 확인)
PERIOD_MS = (-1, -0.5, -0.1, 0.1, 0.5, 1)
GAINS = (0.5, 0.8, 1.25, 2)
OFFSETS = (-50, -10, 10, 50)
COLORS = {"fused_acat": "#2a78d6", "sine_only": "#eb6834"}
LABELS = {"fused_acat": "최종 모델 (fused_acat)", "sine_only": "사인 성분 단독"}


def _grid_fit(x, t, freqs):
    """x를 사인(freqs 중 SSE 최소)+상수로 최소제곱. 반환: (f, [a, b, c])."""
    ph = 2 * np.pi * np.asarray(freqs)[:, None] * t[None, :]
    A = np.stack([np.sin(ph), np.cos(ph), np.ones_like(ph)], axis=2)
    coef = np.linalg.pinv(A, rcond=1e-10) @ x
    sse = ((x - np.einsum("fnk,fk->fn", A, coef)) ** 2).sum(1)
    k = int(np.argmin(sse))
    return float(freqs[k]), coef[k]


def fit_segments(x, groups):
    """구간마다 사인+상수 피팅. 반환: 행별 [f_a, a, b, c, 구간 내 순번], 짧은 구간용 f_a, 긴 구간 f_a 목록."""
    segs = [np.flatnonzero(groups == g) for g in np.unique(groups)]
    t = lambda n: np.arange(n) * 0.1  # noqa: E731
    fits = {k: _grid_fit(x[ix], t(len(ix)), FREQS) for k, ix in enumerate(segs) if len(ix) >= MIN_FIT}
    f_short = float(np.median([f for f, _ in fits.values()]))
    P = np.empty((len(x), 5))
    for k, ix in enumerate(segs):
        f, coef = fits[k] if k in fits else _grid_fit(x[ix], t(len(ix)), np.array([f_short]))
        P[ix] = np.column_stack([np.full(len(ix), f), np.tile(coef, (len(ix), 1)), np.arange(len(ix))])
    return P, f_short, np.array([f for f, _ in fits.values()])


def true_signal(P, tt, m):
    """가정한 참 신호: 부호 있는 주파수 f_a+m 사인 + 상수를 시각 tt(초, 구간 시작 기준)에서."""
    f, a, b, c, _ = P.T
    ph = 2 * np.pi * (f + m) * tt
    return a * np.sin(ph) + b * np.cos(ph) + c


def resample(x, P, tau, m=MAINS):
    """참 신호(f_a+m Hz)를 시각 tau에서 다시 뽑고 원래 피팅 잔차(명목 시각 기준)를 더한다."""
    return true_signal(P, tau, m) + (x - true_signal(P, P[:, 4] * 0.1, m))


def perturbations(x, P):
    """(종류, 수준, 단위, [섭동된 전류 배열...]) 목록. 지터 계열만 반복 5회. 대조 조건은 뒤에 붙인다."""
    i = P[:, 4]
    Z = np.random.default_rng(SEED).standard_normal((REPS, len(x)))
    sig = sorted(JITTER_MS + JITTER_FINE_MS)

    def jitter(kind):
        return [(kind, s, "ms", [resample(x, P, i * 0.1 + s / 1000 * z, ASSUME[kind][0]) for z in Z]) for s in sig]

    def period(kind):
        return [(kind, d, "ms", [resample(x, P, i * (0.1 + d / 1000), ASSUME[kind][0])]) for d in PERIOD_MS]

    out = [("clean", 0.0, "-", [x])]
    out += jitter("jitter") + period("period_offset")
    out += [("requantize", Q_CUR, "grid", [np.round(x / Q_CUR) * Q_CUR])]
    out += [("gain", g, "x", [x * g]) for g in GAINS]
    out += [("offset", o, "raw", [x + o]) for o in OFFSETS]
    out += jitter("jitter_sign_flip") + jitter("jitter_control_no_alias") + period("period_offset_sign_flip")
    return out


def model_scores(scorer, fu, frame):
    comp = scorer.components(frame)[0]
    lp = fu.component_logp(comp)
    return {"fused_acat": fu.score(comp, NAMES, "acat")[0], "sine_only": -lp[f"sine_{W}"] / LN10}, comp, lp


def window_sst(x, groups):
    """사인 점수와 같은 창(같은 기록구간 최근 W관측)의 행 번호와 창 내 제곱합 SST."""
    idx = _window_index(groups, W)
    Wm = np.stack([x[i - W + 1:i + 1] for i in idx])
    return idx, ((Wm - Wm.mean(1, keepdims=True)) ** 2).sum(1)


def _nan2none(v):
    if isinstance(v, dict):
        return {k: _nan2none(u) for k, u in v.items()}
    if isinstance(v, (list, tuple)):
        return [_nan2none(u) for u in v]
    if isinstance(v, float) and not np.isfinite(v):
        return None
    return v


def run(out: Path, root=DEFAULT_ROOT, yj=None):
    t0 = time.time()
    yj = yj or load_vendor()
    normal, _ = load(root)  # 이상 데이터는 쓰지 않는다
    _, train_end, cal_end = next(s for s in yj.SPLITS if s[0] == SPLIT)
    train, cal, test = split_sets(normal, yj, train_end, cal_end)
    scorer = Scorer(train, yj.blocks, wins=(W,), baselines=False)
    fu = Fusion(scorer.train_components, NAMES)
    cal_s = model_scores(scorer, fu, cal)[0]
    gcal, gte = yj.blocks(cal), yj.blocks(test)
    thr = {(m, a): conformal_cutoff(yj.segment_max(cal_s[m], gcal), a) for m in MODELS for a in ALPHAS}

    x = test["AI2_Current"].to_numpy(float)
    P, f_short, f_long = fit_segments(x, gte)
    clean_sine = None
    rows = []
    for kind, level, unit, xs in perturbations(x, P):
        reps = []
        for xp in xs:
            frame = test.copy()
            frame["AI2_Current"] = xp
            s, comp, lp = model_scores(scorer, fu, frame)
            if clean_sine is None:
                clean_sine = comp[f"sine_{W}"]
            nlp = np.column_stack([np.where(np.isfinite(lp[n]), -lp[n] / LN10, -np.inf) for n in NAMES])
            widx, sst = window_sst(xp, gte)
            r = dict(sine_median=float(np.nanmedian(comp[f"sine_{W}"])),
                     sine_diff=float(np.nanmax(np.abs(comp[f"sine_{W}"] - clean_sine))),
                     sst_median=float(np.median(sst)), sse_median=float(np.median(comp[f"sine_{W}"][widx] * sst)))
            for m in MODELS:
                for a in ALPHAS:
                    alarm = s[m] > thr[(m, a)]
                    seg = pd.Series(alarm).groupby(gte).any()
                    dom = pd.Series(np.array(NAMES)[nlp[alarm].argmax(1)]).value_counts() if alarm.any() else None
                    r[(m, a)] = (int(seg.sum()), float(seg.mean()), float(alarm.mean()),
                                 dom.index[0] if dom is not None else "")
            reps.append(r)
        m_off, assume = ASSUME.get(kind, (np.nan, "-"))
        for m in MODELS:
            for a in ALPHAS:
                v = [r[(m, a)] for r in reps]
                frac = np.array([q[1] for q in v])
                rows.append(dict(kind=kind, level=level, unit=unit, f_true_assumption=assume, mains_offset_hz=m_off,
                                 reps=len(reps), model=m, alpha=a,
                                 threshold=thr[(m, a)], n_segments=len(np.unique(gte)),
                                 alarm_segments_mean=float(np.mean([q[0] for q in v])),
                                 alarm_segment_fraction=float(frac.mean()),
                                 alarm_segment_fraction_sd=float(frac.std(ddof=1)) if len(frac) > 1 else np.nan,
                                 alarm_segment_fraction_max=float(frac.max()),
                                 reps_exceeding_alpha=int((frac > a).sum()),
                                 row_alarm_rate=float(np.mean([q[2] for q in v])),
                                 exceeds_alpha=bool(frac.mean() > a),
                                 top_component=pd.Series([q[3] for q in v if q[3]]).mode().iloc[0]
                                 if any(q[3] for q in v) else "",
                                 sine_misfit_median=float(np.mean([r["sine_median"] for r in reps])),
                                 sine_misfit_maxabs_diff_vs_clean=float(np.max([r["sine_diff"] for r in reps])),
                                 sine_window_sst_median=float(np.mean([r["sst_median"] for r in reps])),
                                 sine_window_sse_median=float(np.mean([r["sse_median"] for r in reps]))))
    df = pd.DataFrame(rows)

    # 허용 지터: (kind, 모델, α)마다 격자 위에서 알림 비율이 α를 처음 넘는 σ (지정 격자 / 보조 격자 포함)
    isj = df.kind.isin(JITTER_KINDS)
    df["jitter_grid"] = np.where(~isj, "", np.where(df.level.isin(JITTER_FINE_MS), "fine", "spec"))
    tol, tol_fine = {}, {}
    for (k, m, a), g in df[isj].groupby(["kind", "model", "alpha"]):
        over = g[g.exceeds_alpha]
        tol[(k, m, a)] = float(over[over.jitter_grid == "spec"].level.min()) if (over.jitter_grid == "spec").any() else np.nan
        tol_fine[(k, m, a)] = float(over.level.min()) if len(over) else np.nan
    df["tolerance_sigma_ms"] = [tol[(r.kind, r.model, r.alpha)] if r.kind in JITTER_KINDS else np.nan
                                for r in df.itertuples()]
    df["tolerance_sigma_ms_fine"] = [tol_fine[(r.kind, r.model, r.alpha)] if r.kind in JITTER_KINDS else np.nan
                                     for r in df.itertuples()]
    fa = float(np.median(f_long))
    df["alias_freq_eff_hz"] = np.where(df.kind.str.startswith("period_offset"),
                                       fa + (fa + df.mains_offset_hz) * df.level / 1000 / 0.1, np.nan)

    # 검사 — 전부 실제 계산값
    key = ["model", "alpha"]
    clean = df[df.kind == "clean"].set_index(key).alarm_segments_mean
    sigma0 = {}
    for k in JITTER_KINDS:
        j0 = df[(df.kind == k) & (df.level == 0)].set_index(key)
        sigma0[k] = bool((j0.alarm_segments_mean == clean).all() and (j0.sine_misfit_maxabs_diff_vs_clean < 1e-9).all())
    s_fa = true_signal(P, P[:, 4] * 0.1, 0.0)
    ident = {ASSUME[k][1]: float(np.max(np.abs(true_signal(P, P[:, 4] * 0.1, ASSUME[k][0]) - s_fa)))
             for k in ("jitter", "jitter_sign_flip")}
    aff = df[df.kind.isin(["gain", "offset"])]
    aff_diff = float(aff.sine_misfit_maxabs_diff_vs_clean.max())
    affine_sine_same = bool(all(r.alarm_segments_mean == clean[(r.model, r.alpha)]
                                for r in aff[aff.model == "sine_only"].itertuples()))
    ref = out / "model_comparison.csv"
    ref_ok = None
    if ref.exists():
        mc = pd.read_csv(ref)
        mc = mc[(mc.split == SPLIT) & (mc.model == "fused_acat") & (mc.rule == "conformal")
                & (mc.calibration_unit == "recording_segments")].set_index("budget").normal_notified_segments
        ref_ok = bool(all(a in mc.index and mc[a] == clean[("fused_acat", a)] for a in ALPHAS))
    jm = df[(df.kind == "jitter") & (df.reps_exceeding_alpha > 0) & (df.reps_exceeding_alpha < df.reps)]
    seg_len = pd.Series(gte).value_counts()
    checks = dict(
        f_true_assumption="참 주파수 60±f_a Hz(전원 앨리어싱), 기본 f_a+60. 데이터로 검증되지 않음(diagnosis.md)",
        sigma0_equals_clean=all(sigma0.values()), sigma0_equals_clean_by_kind=sigma0,
        nominal_resample_identity_maxabs=ident,
        nominal_resample_identity_ok=bool(max(ident.values()) < 1e-6 * float(np.std(x))),
        affine_sine_misfit_maxabs_diff=aff_diff, affine_sine_misfit_invariant=bool(aff_diff < 1e-9),
        affine_sine_alarms_equal_clean=affine_sine_same,
        model_comparison_found=ref.exists(), clean_fused_matches_model_comparison=ref_ok,
        alias_f_long_median=fa, alias_f_long_range=(float(f_long.min()), float(f_long.max())),
        short_segments=int(len(seg_len) - len(f_long)), segments_shorter_than_w=int((seg_len < W).sum()), f_short=f_short,
        tolerance_sigma_ms={k: {f"{m}@{a}": v for (kk, m, a), v in tol.items() if kk == k} for k in JITTER_KINDS},
        tolerance_sigma_ms_fine={k: {f"{m}@{a}": v for (kk, m, a), v in tol_fine.items() if kk == k}
                                 for k in JITTER_KINDS},
        tolerance_note="NaN/null = 격자(σ≤3ms) 안에서 α를 넘지 않음",
        jitter_mixed_reps=[dict(model=r.model, alpha=r.alpha, sigma_ms=r.level, mean_segments=r.alarm_segments_mean,
                                max_fraction=r.alarm_segment_fraction_max, reps_exceeding_alpha=r.reps_exceeding_alpha,
                                exceeds_alpha_mean=r.exceeds_alpha) for r in jm.itertuples()],
    )
    passed = ["sigma0_equals_clean", "nominal_resample_identity_ok", "affine_sine_misfit_invariant",
              "affine_sine_alarms_equal_clean"] + (["clean_fused_matches_model_comparison"] if ref.exists() else [])
    checks["all_passed"] = all(checks[k] for k in passed)
    checks["checked"] = passed

    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "perturb_curve.csv", index=False)
    plot_jitter(df, out / "fig_perturb_jitter.png")
    checks["seconds"] = round(time.time() - t0, 1)
    (out / "perturb_checks.json").write_text(json.dumps(_nan2none(checks), ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(json.dumps(_nan2none({k: checks[k] for k in passed + ["all_passed", "seconds"]}), ensure_ascii=False),
          flush=True)
    assert checks["sigma0_equals_clean"], f"σ=0 지터가 깨끗한 결과와 다름: {sigma0}"
    assert checks["nominal_resample_identity_ok"], f"가정별 참 신호가 명목 시각에서 피팅과 다름: {ident}"
    assert checks["affine_sine_misfit_invariant"], f"이득·오프셋에서 사인 1−R² 변함: {aff_diff}"
    assert checks["affine_sine_alarms_equal_clean"], "이득·오프셋에서 사인 단독 알림이 깨끗한 결과와 다름"
    if ref.exists():
        assert ref_ok, "깨끗한 fused_acat 정상 알림이 model_comparison.csv 와 다름"
    return df


def plot_jitter(df, path):
    """기본 가정(f_a+60) 지터 곡선. 보조 격자는 속 빈 마커, 사인 단독 f_true=f_a 대조는 회색 점선."""
    jit = df[df.kind == "jitter"]
    ctl = df[df.kind == "jitter_control_no_alias"]
    fig, axes = plt.subplots(1, len(ALPHAS), figsize=(10.5, 4.3), sharey=True)
    for ax, a in zip(axes, ALPHAS):
        for m, mk in zip(MODELS, ("o", "s")):
            g = jit[(jit.model == m) & (jit.alpha == a)].sort_values("level")
            sd = g.alarm_segment_fraction_sd.fillna(0)
            ax.fill_between(g.level, np.clip(g.alarm_segment_fraction - sd, 0, None), g.alarm_segment_fraction + sd,
                            color=COLORS[m], alpha=.15, lw=0)
            ax.plot(g.level, g.alarm_segment_fraction, lw=2, color=COLORS[m])
            sp, fi = g[g.jitter_grid == "spec"], g[g.jitter_grid == "fine"]
            ax.plot(sp.level, sp.alarm_segment_fraction, ls="none", marker=mk, ms=6, color=COLORS[m])
            ax.plot(fi.level, fi.alarm_segment_fraction, ls="none", marker=mk, ms=6, mfc="white", mec=COLORS[m], mew=1.5)
        c = ctl[(ctl.model == "sine_only") & (ctl.alpha == a)].sort_values("level")
        ax.plot(c.level, c.alarm_segment_fraction, color="#8a8984", ls="--", lw=1.2)
        ax.axhline(a, color="#52514e", ls="--", lw=1)
        ax.text(1.8, a, f"α={a:.0%}", va="bottom", ha="right", fontsize=8, color="#52514e")
        g = jit[(jit.model == "sine_only") & (jit.alpha == a)]
        tf, ts = g.tolerance_sigma_ms_fine.iloc[0], g.tolerance_sigma_ms.iloc[0]
        if np.isfinite(tf):
            ax.axvline(tf, color=COLORS["sine_only"], ls=":", lw=1)
            spec = f"{ts:g}ms" if np.isfinite(ts) else "초과 없음"
            ax.annotate(f"사인 단독:\n보조 격자 기준 첫 초과 σ={tf:g}ms\n(지정 격자 {spec})", xy=(tf, 0.97),
                        xycoords=("data", "axes fraction"), xytext=(-4, 0), textcoords="offset points",
                        ha="right", va="top", fontsize=8, color="#52514e")
        ticks = sorted(JITTER_MS + JITTER_FINE_MS)
        ax.set_xscale("symlog", linthresh=0.01, linscale=0.4)
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{s:g}" for s in ticks], fontsize=7)
        ax.set_xlim(-0.001, 3.5)
        ax.set_ylim(0, 1.02)
        ax.grid(alpha=.3, lw=.5)
        ax.set_xlabel("샘플 타이밍 지터 σ (ms)")
        ax.set_title(f"conformal 문턱 α={a:.0%} (깨끗한 보정 구간)", fontsize=10)
    axes[0].set_ylabel("정상 알림 구간 비율 (평가 120구간)")
    handles = [Line2D([], [], color=COLORS[m], lw=2, marker=mk, ms=6, label=LABELS[m])
               for m, mk in zip(MODELS, ("o", "s"))]
    handles += [Line2D([], [], color="#52514e", ls="none", marker="o", ms=6, mfc="white", mew=1.5,
                       label="속 빈 마커 = 보조 격자 (0.01·0.02·0.05ms)"),
                Line2D([], [], color="#8a8984", ls="--", lw=1.2, label="사인 단독, 대조 f_true=f_a (앨리어싱 없음)")]
    axes[0].legend(handles=handles, fontsize=7.5, loc="center left")
    fig.suptitle(f"전류 샘플 지터에 대한 정상 알림 증가 ({SPLIT}, 참 주파수 f_a+60Hz 가정, 5회 평균 ±1 표본 sd)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    res = run(OUT, DEFAULT_ROOT, load_vendor())
    with pd.option_context("display.width", 220, "display.max_rows", 300):
        print(res[["kind", "level", "f_true_assumption", "model", "alpha", "alarm_segments_mean",
                   "alarm_segment_fraction", "reps_exceeding_alpha", "row_alarm_rate", "sine_misfit_median",
                   "top_component", "alias_freq_eff_hz"]].to_string())
