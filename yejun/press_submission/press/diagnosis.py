"""W6 데이터 진단 — 원본에서 계산해 diagnosis.md / diagnosis.json / 그림 2장을 만든다 (PLAN §5.3).

모든 수치는 이 실행의 입력 파일에서 계산한다. 하드코딩한 결과 수치는 없다.
'0.7ms 지터'·확정적 수집 경로·DC 오프셋 해석은 쓰지 않는다. 60Hz 앨리어싱은 가설로 적는다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .data import DT, FILES, GAP_TOL, SENSORS, TIME, data_dir, quantize  # noqa: E402

import matplotlib.font_manager as _fm
_avail = {f.name for f in _fm.fontManager.ttflist}
plt.rcParams["font.family"] = [f for f in ("AppleGothic", "Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic") if f in _avail] + ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

FREQS = np.arange(0.0, 5.0001, 0.005)
CURRENT_GRID = 1.1920929          # 기존 05 감사의 간격
GRID_TOL_LEGACY, GRID_TOL_STRICT = 1e-3, 1e-6
MIN_FIT_LEN = 10


# ---------- 저장 형식 규칙 ----------
def format_rules(frame: pd.DataFrame) -> dict:
    """형식만 보는 규칙(1 = '이상 파일 형식'). 값의 크기는 보지 않는다."""
    r = frame[SENSORS[2]].to_numpy(float) / CURRENT_GRID
    resid = np.abs(r - np.round(r))
    fine = np.zeros(len(frame), dtype=int)
    for c in SENSORS[:2]:
        x = frame[c].to_numpy(float) * 1e6
        fine |= (np.abs(x - np.round(x)) > 1e-3).astype(int)
    on_legacy = (resid < GRID_TOL_LEGACY).astype(int)
    return {"current_on_grid": on_legacy, "current_on_grid_strict": (resid < GRID_TOL_STRICT).astype(int),
            "vib_finer_than_1e-6": fine, "either": on_legacy | fine}


def rule_stats(normal: pd.DataFrame, abnormal: pd.DataFrame) -> pd.DataFrame:
    """규칙별 파일 발화율과 양방향 판별력(AUROC). 이상=양성."""
    rn, ra = format_rules(normal), format_rules(abnormal)
    rows = []
    for k in rn:
        fpr, tpr = float(rn[k].mean()), float(ra[k].mean())
        auroc = 0.5 * (tpr + (1 - fpr))
        rows.append(dict(rule=k, normal_fire_rate=fpr, abnormal_fire_rate=tpr,
                         auroc=auroc, auroc_reversed=1 - auroc, separability=max(auroc, 1 - auroc)))
    return pd.DataFrame(rows)


def decimals(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.lstrip("-")
    return s.str.split(".").str[1].fillna("").str.len()


# ---------- 파형 ----------
@lru_cache(maxsize=None)
def _hats(n: int) -> np.ndarray:
    t = np.arange(n) * DT
    hats = []
    for f in FREQS:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(n)])
        hats.append(A @ np.linalg.pinv(A))
    return np.stack(hats)


def sine_fit(x: np.ndarray):
    """단일 사인 + 상수, f∈[0,5]Hz 격자 최소제곱. 반환 (f, R², 적합값). SST=0이면 R²=NaN."""
    x = np.asarray(x, float)
    sst = float(((x - x.mean()) ** 2).sum())
    fitted = _hats(len(x)) @ x
    sse = ((x[None, :] - fitted) ** 2).sum(1)
    k = int(np.argmin(sse))
    r2 = 1 - sse[k] / sst if sst > 0 else np.nan
    return float(FREQS[k]), float(r2), fitted[k]


def waveform_table(frame: pd.DataFrame, seg: np.ndarray, label: str, min_len: int = MIN_FIT_LEN) -> pd.DataFrame:
    rows = []
    x_all = frame[SENSORS[2]].to_numpy(float)
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s)
        if len(idx) < min_len:
            continue
        f, r2, _ = sine_fit(x_all[idx])
        rows.append(dict(set=label, segment=int(s), length=int(len(idx)), f_alias=f, r2=r2))
    return pd.DataFrame(rows)


# ---------- 구조 ----------
def dt_stats(frame: pd.DataFrame) -> dict:
    """행 간 시간 차. 0.1초 정확·0초(중복 시각)·그 밖(공백)을 센다. SD는 0 간격 포함/제외를 나눠 적는다."""
    dt = pd.to_datetime(frame[TIME]).diff().dt.total_seconds().to_numpy()[1:]
    exact = np.abs(dt - DT) < GAP_TOL
    zero = dt == 0
    small = dt[dt <= 0.15]
    return dict(n_gaps=int(len(dt)), exact_0_1=int(exact.sum()), zero_gap=int(zero.sum()),
                other_small=int(((small != 0) & (np.abs(small - DT) >= GAP_TOL)).sum()),
                gaps_over_0_15s=int((dt > 0.15).sum()),
                sd_small_incl_zero_s=float(small.std()) if len(small) else float("nan"),
                sd_small_excl_zero_s=float(small[small > 0].std()) if (small > 0).any() else float("nan"),
                max_gap_s=float(dt.max()))


def lag1_autocorr(frame: pd.DataFrame, seg: np.ndarray) -> dict:
    """구간 경계를 넘지 않는 lag-1 자기상관(센서별). 같은 구간 안의 (t, t+1) 쌍만 사용."""
    same = seg[1:] == seg[:-1]
    out = {}
    for c in SENSORS:
        x = frame[c].to_numpy(float)
        a, b = x[:-1][same], x[1:][same]
        out[c] = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else float("nan")
    out["pairs"] = int(same.sum())
    return out


def structure(frame: pd.DataFrame, seg: np.ndarray, status: np.ndarray) -> dict:
    t = pd.to_datetime(frame[TIME], errors="coerce")
    lengths = pd.Series(seg).value_counts()
    return dict(rows=int(len(frame)), bad_rows=int((status != "ok").sum()),
                start=str(t.min()), end=str(t.max()),
                elapsed_min=float((t.max() - t.min()).total_seconds() / 60),
                recorded_min=float(len(frame) * DT / 60),
                segments=int(len(lengths)), seg_len_min=int(lengths.min()), seg_len_median=float(lengths.median()),
                seg_len_max=int(lengths.max()), segments_len_50=int((lengths == 50).sum()),
                duplicate_timestamps=int(t.duplicated().sum()),
                missing_values=int(frame[SENSORS].isna().sum().sum()),
                label_values=sorted(frame["Equipment_state"].unique().tolist()) if "Equipment_state" in frame else None,
                dt=dt_stats(frame), lag1=lag1_autocorr(frame, seg))


# ---------- 실행 ----------
def run(out: Path, root, normal, abnormal, seg_n, seg_a, status_n, status_a, preprocess: str) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    raw_str = {k: pd.read_csv(data_dir(root) / v, dtype=str) for k, v in FILES.items()}
    N = {"normal": structure(normal, seg_n, status_n), "abnormal": structure(abnormal, seg_a, status_a)}

    # 저장 형식
    dec = {}
    for k, df in raw_str.items():
        dec[k] = {c: {"mode": int(decimals(df[c]).mode()[0]), "max": int(decimals(df[c]).max())} for c in SENSORS}
    rules_raw = rule_stats(normal, abnormal)
    rules_pre = rule_stats(quantize(normal, preprocess), quantize(abnormal, preprocess))

    # 기술 통계·구간 평균 범위
    stats = {}
    for k, df, seg in (("normal", normal, seg_n), ("abnormal", abnormal, seg_a)):
        d = df[SENSORS].describe().loc[["mean", "std", "min", "max"]]
        segmean = df[SENSORS[2]].groupby(seg).mean()
        stats[k] = {"describe": {c: d[c].to_dict() for c in SENSORS},
                    "current_segment_mean_min": float(segmean.min()), "current_segment_mean_max": float(segmean.max())}

    # 파형
    wf = pd.concat([waveform_table(normal, seg_n, "normal"), waveform_table(abnormal, seg_a, "abnormal")], ignore_index=True)
    wave = {}
    for k, g in wf.groupby("set"):
        wave[k] = dict(segments_fitted=int(len(g)), r2_min=float(g.r2.min()), r2_median=float(g.r2.median()),
                       r2_max=float(g.r2.max()), f_median=float(g.f_alias.median()),
                       f_q25=float(g.f_alias.quantile(.25)), f_q75=float(g.f_alias.quantile(.75)),
                       f_exact_0_600=int((np.abs(g.f_alias - 0.6) < 1e-9).sum()))
    wf.to_csv(out / "waveform_segments.csv", index=False)

    numbers = {"structure": N, "decimals": dec, "format_rules_raw": rules_raw.to_dict("records"),
               f"format_rules_{preprocess}": rules_pre.to_dict("records"), "stats": stats, "waveform": wave,
               "preprocess": preprocess}

    # ---------- 문서 ----------
    n, a = N["normal"], N["abnormal"]
    L = ["# 데이터 진단 (자동 생성)", "",
         f"입력: `{FILES['normal']}`, `{FILES['abnormal']}` (해시는 manifest.json). 주 전처리: `{preprocess}`.", "",
         "## 1. 구조", "", "| 항목 | 정상 | 이상 |", "|---|---|---|",
         f"| 행 (잘못된 행) | {n['rows']:,} ({n['bad_rows']}) | {a['rows']:,} ({a['bad_rows']}) |",
         f"| 기간 | {n['start'][:19]} ~ {n['end'][11:19]} | {a['start'][:19]} ~ {a['end'][11:19]} |",
         f"| 경과 시간 / 기록 시간(0.1초×행) | {n['elapsed_min']:.1f}분 / {n['recorded_min']:.1f}분 | {a['elapsed_min']:.1f}분 / {a['recorded_min']:.1f}분 |",
         f"| 기록구간(Δt≠0.1초에서 끊음) | {n['segments']} | {a['segments']} |",
         f"| 구간 길이 최소/중앙/최대 (50행 구간 수) | {n['seg_len_min']}/{n['seg_len_median']:.0f}/{n['seg_len_max']} ({n['segments_len_50']}) | {a['seg_len_min']}/{a['seg_len_median']:.0f}/{a['seg_len_max']} ({a['segments_len_50']}) |",
         f"| 중복 타임스탬프 / 결측 | {n['duplicate_timestamps']} / {n['missing_values']} | {a['duplicate_timestamps']} / {a['missing_values']} |",
         f"| `Equipment_state` 값 | {n['label_values']} | {a['label_values']} |",
         f"| Δt 정확히 0.1초 / 0초 / 0.15초 초과 공백 | {n['dt']['exact_0_1']:,} / {n['dt']['zero_gap']} / {n['dt']['gaps_over_0_15s']} | {a['dt']['exact_0_1']:,} / {a['dt']['zero_gap']} / {a['dt']['gaps_over_0_15s']} |",
         f"| 0.15초 이하 Δt의 SD (0초 포함 / 제외) | {n['dt']['sd_small_incl_zero_s']*1000:.3f}ms / {n['dt']['sd_small_excl_zero_s']*1000:.3f}ms | {a['dt']['sd_small_incl_zero_s']*1000:.3f}ms / {a['dt']['sd_small_excl_zero_s']*1000:.3f}ms |",
         f"| 구간 내 lag-1 자기상관 (AI0/AI1/AI2) | {n['lag1'][SENSORS[0]]:.3f}/{n['lag1'][SENSORS[1]]:.3f}/{n['lag1'][SENSORS[2]]:.3f} | {a['lag1'][SENSORS[0]]:.3f}/{a['lag1'][SENSORS[1]]:.3f}/{a['lag1'][SENSORS[2]]:.3f} |",
         "",
         "- 기록구간은 타임스탬프 간격이 0.1초가 아닌 곳에서 나눈 기록 단위다. 설비 기동·프레스 스트로크·독립 고장 사건을 뜻하지 않는다.",
         "- 0초 간격은 중복 타임스탬프이며, 0.15초 이하 Δt의 SD는 그 중복 시각을 포함할 때만 0이 아니다. 샘플링 클록 지터의 증거로 쓰지 않는다.",
         "- 라벨은 파일 단위 상수이고 정상·이상이 서로 다른 하루씩이라 상태·파일·날짜가 교락되어 있다. 이 데이터로는 분리할 수 없다.",
         "", "## 2. 저장 형식", "", "| 항목 | 정상 | 이상 |", "|---|---|---|"]
    for c, nm in zip(SENSORS, ("상부 진동", "하부 진동", "전류")):
        L.append(f"| {nm} 소수 자릿수 최빈/최대 | {dec['normal'][c]['mode']}/{dec['normal'][c]['max']} | {dec['abnormal'][c]['mode']}/{dec['abnormal'][c]['max']} |")
    L += ["", f"형식만 보는 규칙의 발화율과 판별력 (전류 격자 간격 {CURRENT_GRID}, 무차원 잔차 허용오차 기존 {GRID_TOL_LEGACY:g} / 엄격 {GRID_TOL_STRICT:g}):", "",
          "| 규칙 | 전처리 | 정상 발화율 | 이상 발화율 | 판별력(AUROC, 큰 방향) |", "|---|---|---:|---:|---:|"]
    for tag, tbl in (("raw", rules_raw), (preprocess, rules_pre)):
        for r in tbl.itertuples():
            L.append(f"| {r.rule} | {tag} | {r.normal_fire_rate:.3f} | {r.abnormal_fire_rate:.3f} | {r.separability:.3f} |")
    L += ["", "- 원자료 문자열·소수부·격자를 읽는 모델은 값의 크기와 무관하게 두 파일을 구분할 수 있다. 주 전처리는 두 클래스에 같은 간격의 round를 적용해 이 정보를 제거한다.",
          "- 저장 정밀도 차이는 관측 사실이다. 수집 장치·필터·클록이 달랐는지는 이 자료로 확인할 수 없는 가설이다.",
          "", "## 3. 센서 통계", "", "| 센서 | 정상 평균/표준편차/최소/최대 | 이상 평균/표준편차/최소/최대 |", "|---|---|---|"]
    for c in SENSORS:
        dn, da = stats["normal"]["describe"][c], stats["abnormal"]["describe"][c]
        L.append(f"| {c} | {dn['mean']:.3f} / {dn['std']:.3f} / {dn['min']:.3f} / {dn['max']:.3f} | {da['mean']:.3f} / {da['std']:.3f} / {da['min']:.3f} / {da['max']:.3f} |")
    L += ["", f"- 전류의 기록구간 평균 범위: 정상 {stats['normal']['current_segment_mean_min']:.1f} ~ {stats['normal']['current_segment_mean_max']:.1f}, "
          f"이상 {stats['abnormal']['current_segment_mean_min']:.1f} ~ {stats['abnormal']['current_segment_mean_max']:.1f}. 짧고 불연속인 파형의 표본평균은 위상에 따라 크게 움직이므로 파일 평균 차이를 물리적 오프셋으로 해석하지 않는다.",
          "", "## 4. 전류 파형", "", f"기록구간(길이 ≥ {MIN_FIT_LEN}) 전체에 단일 사인+상수를 0~5Hz 격자에서 적합한 사후 진단이다. 경보 특징(trailing 창 R²)과는 정의가 다르다.", "",
          "| | 적합 구간 수 | R² 최소/중앙/최대 | 적합 주파수 중앙값 (사분위) | 정확히 0.600Hz인 구간 |", "|---|---:|---|---|---:|"]
    for k, nm in (("normal", "정상"), ("abnormal", "이상")):
        w = wave[k]
        L.append(f"| {nm} | {w['segments_fitted']} | {w['r2_min']:.3f}/{w['r2_median']:.3f}/{w['r2_max']:.3f} | {w['f_median']:.3f} ({w['f_q25']:.3f}~{w['f_q75']:.3f}) | {w['f_exact_0_600']} |")
    L += ["", "- 정상 구간의 전류는 약 0.6Hz 사인파로 잘 설명되고 이상 구간은 그렇지 않다. '60Hz 교류를 10Hz로 표본화한 앨리어싱'이라는 설명은 실제 표본화 간격을 확인하지 못한 가설이다.",
          "- 그림 `fig_current_waveform.png`는 정상 1구간·이상 2구간(길이 50)의 측정값과 구간 전체 사인 적합이다.", ""]
    (out / "diagnosis.md").write_text("\n".join(L), encoding="utf-8")

    # ---------- 그림 ----------
    ln, la = pd.Series(seg_n).value_counts(), pd.Series(seg_a).value_counts().sort_index()
    picks = [("정상", normal, seg_n, int(ln[ln == 50].index[0]))]
    la50 = la[la == 50].index
    picks += [("이상", abnormal, seg_a, int(la50[0])), ("이상", abnormal, seg_a, int(la50[-1]))]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3), sharey=True)
    for ax, (lab, df, sg, s) in zip(axes, picks):
        x = df[SENSORS[2]].to_numpy(float)[sg == s]
        f, r2, fit = sine_fit(x)
        tt = np.arange(len(x)) * DT
        ax.plot(tt, x, "o", ms=3, label="측정")
        ax.plot(tt, fit, "-", lw=1, label=f"사인 적합 f={f:.2f}Hz")
        ax.set_title(f"{lab} 구간 {s}: R²={r2:.3f}", fontsize=10)
        ax.set_xlabel("구간 내 시간(초)")
    axes[0].set_ylabel("전류 AI2 (원값)")
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "fig_current_waveform.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.hist(ln.values, bins=range(0, 52, 2), alpha=.7, label=f"정상 ({len(ln)}구간)", density=True)
    ax.hist(la.values, bins=range(0, 52, 2), alpha=.7, label=f"이상 ({len(la)}구간)", density=True)
    ax.set_xlabel("기록구간 길이(관측 수)")
    ax.set_ylabel("밀도")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "fig_segment_length.png", dpi=150)
    plt.close(fig)
    return numbers
