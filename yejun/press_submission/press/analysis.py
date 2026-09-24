"""W9 영향요인·오류(FN/FP) 조건 분석 — PLAN.md §1·§5.3.

주 모델(conformal α=1%, 3%·5% 병기)의 행별 예측(predictions_*.csv)과 평가 스트림의 센서값으로 기록구간 특징을 만들고,
조건별 분모를 포함한 FN/FP 표, 진동 수준×파형 특성 2×2 표, 단변량 AUROC, 그림 3장을 만든다.
- 구간 전체 R²(사후 진단)와 trailing 창 1−R²(경보 특징)는 다른 값이며 표·그림에 어느 것인지 적는다.
- 전류 진폭 대리 지표 = 구간 전체 평균 제거 RMS×√2. 길이 17 미만은 신뢰 제한으로 표시하되 분모에서 빼지 않는다.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from . import data as D  # noqa: E402
from .diagnosis import MIN_FIT_LEN, sine_fit  # noqa: E402

AMP_MIN_LEN = 17
LEN_BINS = [(1, 4, "≤4"), (5, 9, "5–9"), (10, 29, "10–29"), (30, 10**9, "≥30")]
ALARM_COLS = {0.01: "alarm", 0.03: "alarm_conformal_0.03", 0.05: "alarm_conformal_0.05"}


def segment_features(frame: pd.DataFrame, seg: np.ndarray) -> pd.DataFrame:
    rows = []
    v0, v1, cur = (frame[c].to_numpy(float) for c in D.SENSORS)
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s)
        c = cur[idx]
        r2 = sine_fit(c)[1] if len(idx) >= MIN_FIT_LEN else np.nan
        rows.append(dict(record_id=int(s), length=int(len(idx)),
                         vib0_std=float(v0[idx].std(ddof=1)) if len(idx) > 1 else np.nan,
                         vib1_std=float(v1[idx].std(ddof=1)) if len(idx) > 1 else np.nan,
                         amp_proxy=float(np.sqrt(2 * np.mean((c - c.mean()) ** 2))), amp_reliable=bool(len(idx) >= AMP_MIN_LEN),
                         r2_segment=r2))
    return pd.DataFrame(rows)


def _len_bin(n):
    return next(lab for lo, hi, lab in LEN_BINS if lo <= n <= hi)


def _quartile_bin(x, q):
    if not np.isfinite(x):
        return "NA"
    return "Q1(<q25)" if x < q[0] else "Q2" if x < q[1] else "Q3" if x < q[2] else "Q4(≥q75)"


def analyze_split(sid: str, name: str, train: pd.DataFrame, seg_train: np.ndarray, stream: pd.DataFrame, seg_stream: np.ndarray,
                  pred: pd.DataFrame, w: int, state: dict):
    feat = segment_features(stream, seg_stream)
    agg = pred.groupby("record_id").agg(source=("source", "first"), maxz_max=("score_maxz3", "max"), combined_max=("combined_score", "max"),
                                        sine_trailing_median=("score_sine", "median"), alarm=("alarm", "max"),
                                        alarm_003=(ALARM_COLS[0.03], "max"), alarm_005=(ALARM_COLS[0.05], "max")).reset_index()
    first = pred[pred.alarm == 1].groupby("record_id").agg(first_alarm_pos=("position_in_record", "min"))
    first_reason = pred[pred.alarm == 1].sort_values("position_in_record").groupby("record_id").alarm_reason.first().rename("first_reason")
    feat = feat.merge(agg, on="record_id").merge(first, on="record_id", how="left").merge(first_reason, on="record_id", how="left")
    feat["label"] = (feat.source == "abnormal").astype(int)
    feat["len_bin"] = feat.length.map(_len_bin)
    # 정상 학습 구간 기준 사분위 (진폭은 신뢰 구간만)
    ftr = segment_features(train, seg_train)
    mean, scale = np.asarray(state["scaler_mean"]), np.asarray(state["scaler_scale"])
    ztr = np.abs((train[D.SENSORS].to_numpy(float) - mean) / scale).max(1)
    ftr["maxz_max"] = pd.Series(ztr).groupby(seg_train).max().to_numpy()
    q_amp = ftr[ftr.amp_reliable].amp_proxy.quantile([.25, .5, .75]).to_numpy()
    q_vib = ftr.vib0_std.dropna().quantile([.25, .5, .75]).to_numpy()
    feat["amp_bin"] = [_quartile_bin(x, q_amp) for x in feat.amp_proxy]
    feat["vib_bin"] = [_quartile_bin(x, q_vib) for x in feat.vib0_std]
    vib_hi_thr = float(ftr.maxz_max.quantile(.95))
    r2_lo_thr = float(ftr.r2_segment.dropna().quantile(.05))
    feat["vib_high"] = feat.maxz_max > vib_hi_thr
    feat["wave"] = np.where(feat.r2_segment.isna(), "unfittable(<10)", np.where(feat.r2_segment < r2_lo_thr, "broken", "sine-like"))
    feat.insert(0, "split", name)
    p = pred.merge(feat[["record_id", "len_bin", "amp_bin", "vib_bin", "amp_reliable", "length"]], on="record_id")
    p["pos_bin"] = np.where(p.position_in_record < w - 1, f"warmup(<{w-1})", "scored")
    abn = p[p.source == "abnormal"]

    # FN 조건표(행 단위, 분모 포함) · FP 조건표(정상 평가 구간 단위)
    fn_rows, fp_rows = [], []
    for alpha, col in ALARM_COLS.items():
        for cond in ("pos_bin", "len_bin", "amp_bin", "vib_bin"):
            for val, g in abn.groupby(cond):
                fn_rows.append(dict(split=name, alpha=alpha, condition=cond, value=val, abnormal_rows=len(g),
                                    fn_rows=int((g[col] == 0).sum()), fn_rate=float((g[col] == 0).mean()),
                                    rows_before_first_alarm=int((g.position_in_record < g.record_id.map(first.first_alarm_pos).fillna(10**9)).sum())))
            nt = feat[feat.source == "normal_test"]
            acol = {0.01: "alarm", 0.03: "alarm_003", 0.05: "alarm_005"}[alpha]
            for val, g in nt.groupby(cond if cond != "pos_bin" else "len_bin"):
                if cond == "pos_bin":
                    continue
                fp_rows.append(dict(split=name, alpha=alpha, condition=cond, value=val, normal_segments=len(g),
                                    fp_segments=int(g[acol].sum()), fp_rate=float(g[acol].mean()),
                                    unreliable_amp_segments=int((~g.amp_reliable).sum()) if cond == "amp_bin" else None))
    # 발화 성분
    comp = []
    for alpha, col in ALARM_COLS.items():
        ar = abn[abn[col] == 1]
        if alpha == 0.01:
            for k, v in ar.alarm_reason.value_counts(normalize=True).items():
                comp.append(dict(split=name, alpha=alpha, kind="abnormal_alarm_row_reason", item=k, share=float(v), n=len(ar)))
            for k, v in ar[ar.alarm_reason.isin(["maxz", "both"])].maxz_sensor.value_counts(normalize=True).items():
                comp.append(dict(split=name, alpha=alpha, kind="maxz_sensor_share", item=k, share=float(v), n=int(ar.alarm_reason.isin(["maxz", "both"]).sum())))
            fpseg = feat[(feat.source == "normal_test") & (feat.alarm == 1)]
            for k, v in fpseg.first_reason.value_counts(normalize=True).items():
                comp.append(dict(split=name, alpha=alpha, kind="fp_segment_first_reason", item=k, share=float(v), n=len(fpseg)))
    # 단변량 AUROC (구간 단위; 이상 21구간은 카운트)
    infl = []
    for c in ("vib0_std", "vib1_std", "amp_proxy", "r2_segment", "sine_trailing_median", "maxz_max", "length"):
        g = feat[[c, "label"]].dropna()
        if g.label.nunique() == 2:
            au = float(roc_auc_score(g.label, g[c]))
            infl.append(dict(split=name, feature=c, auroc=au, direction="higher⇒abnormal" if au >= 0.5 else "lower⇒abnormal",
                             separability=max(au, 1 - au), n_normal=int((g.label == 0).sum()), n_abnormal=int((g.label == 1).sum()),
                             definition={"r2_segment": "구간 전체 사인 R²(사후)", "sine_trailing_median": f"trailing-{w} 1−R² 중앙값(경보 특징)", "amp_proxy": "평균 제거 RMS×√2(길이<17 신뢰 제한)"}.get(c, "")))
    # 2×2: 진동 수준 × 파형
    cells = []
    for (vh, wv), g in feat.groupby(["vib_high", "wave"]):
        a, nt = g[g.label == 1], g[g.label == 0]
        cells.append(dict(split=name, vib_high=bool(vh), vib_threshold=f"segment max|z| > q95 of normal-train ({vib_hi_thr:.2f})",
                          wave=wv, wave_threshold=f"segment R² < q05 of normal-train ({r2_lo_thr:.3f})",
                          abnormal_segments=len(a), abnormal_detected=int(a.alarm.sum()), abnormal_missed=int((a.alarm == 0).sum()),
                          normal_segments=len(nt), normal_alerted=int(nt.alarm.sum())))
    return feat, pd.DataFrame(fn_rows), pd.DataFrame(fp_rows), pd.DataFrame(comp), pd.DataFrame(infl), pd.DataFrame(cells), p


def figures(out, feats: pd.DataFrame, preds: dict, streams: dict, w: int):
    # 1. 진동 수준 × 구간 R² (마지막 분할 기준)
    name = sorted(feats.split.unique())[-1]
    s = feats[feats.split == name]
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for lab, nm, mk in ((0, "정상 평가 구간", "o"), (1, "이상 구간", "^")):
        t = s[(s.label == lab) & s.r2_segment.notna()]
        ax.scatter(t.vib0_std, t.r2_segment, s=18, marker=mk, alpha=.7, label=nm)
    t = s[(s.label == 0) & (s.alarm == 1) & s.r2_segment.notna()]
    ax.scatter(t.vib0_std, t.r2_segment, s=90, facecolors="none", edgecolors="red", label="정상 알림(FP, α=1%)")
    t = s[(s.label == 1) & (s.alarm == 0) & s.r2_segment.notna()]
    if len(t):
        ax.scatter(t.vib0_std, t.r2_segment, s=90, facecolors="none", edgecolors="black", label="이상 미탐")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("상부 진동(AI0) 구간 표준편차 (log)")
    ax.set_ylabel("구간 전체 전류 사인 적합 R² (사후 진단, 길이≥10)")
    ax.set_title(f"기록구간별 진동 수준 × 전류 파형 ({name})")
    ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "fig_vibration_vs_waveform.png", dpi=150); plt.close(fig)
    # 2. 구간 내 위치별 이상 행 경보율
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for sid, p in preds.items():
        g = p[p.source == "abnormal"]
        r = g.groupby(g.position_in_record.clip(upper=20)).alarm.mean()
        ax.plot(r.index, r.values, marker="o", ms=3, label=f"{D.SPLITS[sid][0]} (conformal α=1%)")
    ax.axvline(w - 1, color="gray", ls=":", lw=1)
    ax.set_xlabel("기록구간 내 관측 순서 (20 이상은 묶음)"); ax.set_ylabel("이상 행 경보율"); ax.set_ylim(0, 1.05)
    ax.set_title(f"구간 초반은 max-z만 판정(사인 창 w={w}은 {w-1}행 뒤부터)")
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(out / "fig_recall_by_position.png", dpi=150); plt.close(fig)
    # 3. 사례: 사인만으로 잡은 이상 구간 / 정상 알림(FP) 구간 / 가장 늦게 잡은 이상 구간
    sid = sorted(preds)[-1]
    p, st = preds[sid], streams[sid]
    seg = D.segments(st)
    picks = []
    ab = feats[(feats.split == D.SPLITS[sid][0]) & (feats.label == 1)]
    only_sine = ab[ab.first_reason == "sine"].sort_values("maxz_max").head(1)
    if len(only_sine):
        picks.append((int(only_sine.record_id.iloc[0]), "이상: 파형으로만 경보"))
    fp = feats[(feats.split == D.SPLITS[sid][0]) & (feats.label == 0) & (feats.alarm == 1)].head(1)
    if len(fp):
        picks.append((int(fp.record_id.iloc[0]), "정상 알림(FP)"))
    late = ab.sort_values("first_alarm_pos", ascending=False)
    late = late[~late.record_id.isin([r for r, _ in picks])].head(1)
    if len(late):
        picks.append((int(late.record_id.iloc[0]), "이상: 첫 경보가 가장 늦은 구간(다른 구간 중)"))
    if picks:
        fig, axes = plt.subplots(len(picks), 1, figsize=(8, 2.6 * len(picks)), squeeze=False)
        for ax, (rid, title) in zip(axes[:, 0], picks):
            idx = np.flatnonzero(seg == rid)
            t = np.arange(len(idx)) * D.DT
            ax.plot(t, st[D.SENSORS[2]].to_numpy(float)[idx], "-o", ms=2.5, lw=.8, label="전류(전처리 후)")
            ax2 = ax.twinx()
            ax2.plot(t, p.score_maxz3.to_numpy()[idx], "s-", ms=2.5, lw=.8, color="tab:orange", label="max|z|")
            al = p.alarm.to_numpy()[idx] == 1
            if al.any():
                ax.scatter(t[al], st[D.SENSORS[2]].to_numpy(float)[idx][al], s=60, facecolors="none", edgecolors="red", zorder=5, label="경보 행")
            ax.set_title(f"{title} — 구간 {rid} ({D.SPLITS[sid][0]}, α=1%)", fontsize=10)
            ax.set_xlabel("구간 내 시간(초)"); ax.set_ylabel("전류"); ax2.set_ylabel("max|z|")
            h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
            ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper right")
        fig.tight_layout(); fig.savefig(out / "fig_error_examples.png", dpi=150); plt.close(fig)


def run(out, ctx2: dict, w: int, log=print):
    """ctx2[sid] = dict(name, train, seg_train, stream, seg_stream, pred, state)."""
    feats, fns, fps, comps, infls, cells, preds, streams = [], [], [], [], [], [], {}, {}
    for sid, c in ctx2.items():
        f, fn, fp, comp, infl, cell, p = analyze_split(sid, c["name"], c["train"], c["seg_train"], c["stream"], c["seg_stream"], c["pred"], w, c["state"])
        feats.append(f); fns.append(fn); fps.append(fp); comps.append(comp); infls.append(infl); cells.append(cell)
        preds[sid], streams[sid] = p, c["stream"]
        log(f"  analysis {sid} done")
    feats = pd.concat(feats, ignore_index=True)
    feats.drop(columns=[]).to_csv(out / "segment_features.csv", index=False)
    pd.concat(fns, ignore_index=True).to_csv(out / "error_conditions_fn.csv", index=False)
    pd.concat(fps, ignore_index=True).to_csv(out / "error_conditions_fp.csv", index=False)
    pd.concat(comps, ignore_index=True).to_csv(out / "alarm_components.csv", index=False)
    pd.concat(infls, ignore_index=True).to_csv(out / "influence.csv", index=False)
    pd.concat(cells, ignore_index=True).to_csv(out / "interaction_2x2.csv", index=False)
    figures(out, feats, preds, streams, w)
    fn_all = pd.concat(fns, ignore_index=True)
    return {"fn_table_rows": int(len(fn_all)), "abnormal_segments_missed_alpha1pct": int((feats[feats.label == 1].alarm == 0).sum()),
            "normal_test_segments_alerted_alpha1pct": {str(s): int(g[g.label == 0].alarm.sum()) for s, g in feats.groupby("split")}}
