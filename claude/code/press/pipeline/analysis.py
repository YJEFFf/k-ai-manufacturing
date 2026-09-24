"""T3: 영향요인·오류(FN/FP) 분석. run_all.py 산출물(predictions_test.csv, model_comparison.csv)만 읽는다.

- influence.csv: 경보 사유(max-z/사인/둘 다) 비율, max-z를 만든 센서 비율, 구간 특징별 단변량 AUROC
- error_conditions.csv: 예산별 FN(놓친 이상 행)의 위치·원인, FP(정상 알림 구간)의 조건
- segment_features.csv: 기록구간 특징 (진동 표준편차, 전류 진폭, 사인 R² 중앙값, 길이, 결합 점수 최댓값)
- 그림 2장
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from data import SENSORS  # noqa: E402

plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def segment_features(pred):
    """예측 파일(센서 원값 포함)에서 기록구간 특징을 만든다."""
    d = pred
    assert d[SENSORS].notna().all().all()
    g = d.groupby(["split", "source", "record_uid"])
    f = g.agg(length=("timestamp", "size"), vib0_std=("AI0_Vibration", "std"), vib1_std=("AI1_Vibration", "std"),
              current_amp=("AI2_Current", lambda x: np.sqrt(2 * np.mean(x ** 2))),
              sine_1mR2_median=("score_sine", "median"), maxz_max=("score_maxz", "max"),
              comb_max=("score_comb", "max"), alarm=("alarm", "max")).reset_index()
    f["label"] = (f.source == "abnormal").astype(int)
    return d, f


def run(out: Path, root):
    pred = pd.read_csv(out / "predictions_test.csv")
    mt = pd.read_csv(out / "model_comparison.csv")
    d, seg = segment_features(pred)
    seg.to_csv(out / "segment_features.csv", index=False)

    # 영향요인 1: 경보 사유, max-z 센서
    inf = []
    for split, g in d[d.alarm == 1].groupby("split"):
        for src, h in g.groupby("source"):
            for k, v in h.alarm_reason.value_counts(normalize=True).items():
                inf.append(dict(split=split, source=src, kind="alarm_reason", item=k, share=v, n=len(h)))
            mz = h[h.alarm_reason.isin(["maxz", "both"])]
            for k, v in mz.maxz_sensor.value_counts(normalize=True).items():
                inf.append(dict(split=split, source=src, kind="maxz_sensor", item=k, share=v, n=len(mz)))
    # 영향요인 2: 구간 특징 단변량 AUROC (정상 평가 vs 이상, 구간 단위)
    feats = ["vib0_std", "vib1_std", "current_amp", "sine_1mR2_median", "maxz_max", "length"]
    for split, g in seg.groupby("split"):
        for c in feats:
            x = g[c].fillna(g[c].median())
            inf.append(dict(split=split, source="segment", kind="univariate_auroc", item=c,
                            share=roc_auc_score(g.label, x), n=len(g)))
    pd.DataFrame(inf).to_csv(out / "influence.csv", index=False)

    # 오류 분석: 결합 모델, 기록구간 보정, 예산별
    err = []
    for split, g in d.groupby("split"):
        model = g.model.iloc[0]
        for budget in (0.01, 0.03, 0.05):
            row = mt[(mt.split == split) & (mt.model == model) & (mt.calibration_unit == "recording_segments")
                     & (mt.budget == budget)].iloc[0]
            alarm = np.isfinite(g.score_comb) & (g.score_comb > row.threshold)
            ab = g[g.source == "abnormal"]
            fn = ab[~alarm[ab.index]]
            assert len(fn) == row.fn, (len(fn), row.fn)
            w = int(g.w.iloc[0])
            err.append(dict(split=split, budget=budget, kind="FN_rows", count=len(fn),
                            in_sine_warmup=int((fn.row_in_record < w - 1).sum()),
                            median_row_in_record=float(fn.row_in_record.median()) if len(fn) else np.nan,
                            median_maxz=float(fn.score_maxz.median()) if len(fn) else np.nan,
                            median_sine_1mR2=float(fn.score_sine.median()) if len(fn) else np.nan))
            nt = g[g.source == "normal_test"].assign(a=alarm[g.source == "normal_test"])
            fp_seg = nt.groupby("record_uid").a.max()
            fp_ids = fp_seg[fp_seg].index
            assert len(fp_ids) == row.normal_notified_segments
            sf = seg[(seg.split == split) & seg.record_uid.isin(fp_ids)]
            ok = seg[(seg.split == split) & (seg.source == "normal_test") & ~seg.record_uid.isin(fp_ids)]
            fpr = nt[nt.a]
            err.append(dict(split=split, budget=budget, kind="FP_segments", count=len(fp_ids),
                            fp_alarm_rows=len(fpr),
                            fp_rows_maxz_fired=int((fpr.score_maxz_logp > row.threshold).sum()),
                            fp_median_current_amp=float(sf.current_amp.median()) if len(sf) else np.nan,
                            ok_median_current_amp=float(ok.current_amp.median()),
                            fp_median_vib0_std=float(sf.vib0_std.median()) if len(sf) else np.nan,
                            ok_median_vib0_std=float(ok.vib0_std.median()),
                            fp_median_length=float(sf.length.median()) if len(sf) else np.nan,
                            ok_median_length=float(ok.length.median()),
                            fp_record_uids=";".join(fp_ids)))
    pd.DataFrame(err).to_csv(out / "error_conditions.csv", index=False)

    # 그림 1: 진동 수준 × 사인 R² (기록구간), 첫 분할
    split0 = sorted(seg.split.unique())[-1]
    s = seg[seg.split == split0]
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for lab, name, mk in ((0, "정상 평가 구간", "o"), (1, "이상 구간", "^")):
        t = s[s.label == lab]
        ax.scatter(t.vib0_std, 1 - t.sine_1mR2_median, s=18, marker=mk, alpha=.7, label=name)
    t = s[(s.label == 0) & (s.alarm == 1)]
    ax.scatter(t.vib0_std, 1 - t.sine_1mR2_median, s=80, facecolors="none", edgecolors="red", label="정상 알림(FP)")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("상부 진동(AI0) 구간 표준편차 (log)")
    ax.set_ylabel("전류 사인 피팅 R² (구간 중앙값)")
    ax.set_title(f"기록구간별 진동 수준 × 전류 파형 ({split0})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_vibration_vs_sineR2.png", dpi=150)
    plt.close(fig)

    # 그림 2: 구간 내 위치별 이상 행 재현율 (1% 예산)
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for split, g in d[d.source == "abnormal"].groupby("split"):
        r = g.groupby(g.row_in_record.clip(upper=20)).alarm.mean()
        ax.plot(r.index, r.values, marker="o", ms=3, label=f"{split} (w={int(g.w.iloc[0])})")
    ax.set_xlabel("기록구간 내 관측 순서 (20 이상은 묶음)")
    ax.set_ylabel("이상 행 재현율")
    ax.set_ylim(0, 1.05)
    ax.set_title("구간 시작 직후 미탐 — 사인 창이 차기 전 구간")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_recall_by_position.png", dpi=150)
    plt.close(fig)
    return pd.DataFrame(inf), pd.DataFrame(err)
