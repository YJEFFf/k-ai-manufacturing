"""영향요인·오류(FN/FP) 분석. run_all.py 산출물(predictions_test.csv, model_comparison.csv)만 읽는다.

- influence.csv: 경보 사유(성분) 비율, max-z를 만든 센서 비율, 성분 ablation 효과, 구간 특징별 단변량 AUROC
- error_conditions.csv: 예산별 FN(놓친 이상 행)의 위치·원인 요약
- fp_segments.csv: 정상 알림 구간 하나하나의 조건 (사례 수가 적어 일반화하지 않는다)
- segment_features.csv: 기록구간 특징
- 그림 2장
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from data import SENSORS  # noqa: E402

from matplotlib import font_manager  # noqa: E402

plt.rcParams["font.family"] = [f for f in ("Malgun Gothic", "AppleGothic", "NanumGothic")
                               if f in {x.name for x in font_manager.fontManager.ttflist}] + ["DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
FINAL = "fused_acat"


def segment_features(d):
    assert d[SENSORS].notna().all().all()
    g = d.groupby(["split", "source", "record_uid"])
    f = g.agg(length=("timestamp", "size"), vib0_std=("AI0_Vibration", "std"), vib1_std=("AI1_Vibration", "std"),
              current_amp=("AI2_Current", lambda x: np.sqrt(2 * np.mean(x ** 2))),
              sine_misfit_median=("comp_sine", "median"), maxz_max=("comp_maxz", "max"),
              fused_max=("score_fused", "max"), alarm=("alarm", "max")).reset_index()
    f["label"] = (f.source == "abnormal").astype(int)
    return f


def run(out: Path, root):
    d = pd.read_csv(out / "predictions_test.csv")
    d["alarm_reason"] = d.alarm_reason.fillna("")
    mt = pd.read_csv(out / "model_comparison.csv")
    seg = segment_features(d)
    seg.to_csv(out / "segment_features.csv", index=False)

    inf = []
    # 1) 경보 사유(성분)와 max-z 센서
    for split, g in d[d.alarm == 1].groupby("split"):
        for src, h in g.groupby("source"):
            for k, v in h.alarm_reason.value_counts(normalize=True).items():
                inf.append(dict(split=split, source=src, kind="alarm_reason", item=k, value=v, n=len(h)))
            mz = h[h.alarm_reason.str.contains("크기")]
            for k, v in mz.maxz_sensor.value_counts(normalize=True).items():
                inf.append(dict(split=split, source=src, kind="maxz_sensor", item=k, value=v, n=len(mz)))
    # 2) 성분 ablation: 주 결과 조건(conformal, 기록구간)에서 성분을 뺐을 때 탐지 구간 변화
    main = mt[(mt.rule == "conformal") & (mt.calibration_unit == "recording_segments")]
    for (split, b), g in main.groupby(["split", "budget"]):
        full = g[g.model == FINAL].iloc[0]
        for _, r in g[g.model.str.startswith("ablate_")].iterrows():
            inf.append(dict(split=split, source=f"budget={b}", kind="ablation", item=r.model,
                            value=int(r.abnormal_notified_segments - full.abnormal_notified_segments),
                            n=int(r.normal_notified_segments - full.normal_notified_segments)))
    # 3) 구간 특징 단변량 AUROC (정상 평가 vs 이상, 구간 단위)
    feats = ["vib0_std", "vib1_std", "current_amp", "sine_misfit_median", "maxz_max", "length"]
    for split, g in seg.groupby("split"):
        for c in feats:
            x = g[c].fillna(g.loc[g.label == 0, c].median())
            inf.append(dict(split=split, source="segment", kind="univariate_auroc", item=c,
                            value=roc_auc_score(g.label, x), n=len(g)))
    pd.DataFrame(inf).to_csv(out / "influence.csv", index=False)

    # 오류 분석: 최종 모델, conformal, 기록구간, 예산별
    err, fps = [], []
    for split, g in d.groupby("split"):
        w = int(g.w.iloc[0])
        for b in (0.01, 0.03, 0.05):
            row = main[(main.split == split) & (main.model == FINAL) & (main.budget == b)].iloc[0]
            alarm = g.score_fused > row.threshold
            ab = g[g.source == "abnormal"]
            fn = ab[~alarm[ab.index]]
            assert len(fn) == row.fn, (len(fn), row.fn)
            err.append(dict(split=split, budget=b, w=w, fn_rows=len(fn), abnormal_rows=len(ab),
                            fn_in_sine_warmup=int((fn.row_in_record < w - 1).sum()),
                            warmup_rows=int((ab.row_in_record < w - 1).sum()),
                            recall_warmup=float(alarm[ab.index][ab.row_in_record < w - 1].mean()),
                            recall_after_warmup=float(alarm[ab.index][ab.row_in_record >= w - 1].mean()),
                            fn_median_row_in_record=float(fn.row_in_record.median()) if len(fn) else np.nan))
            nt = g[g.source == "normal_test"].assign(a=alarm[g.source == "normal_test"])
            fp_ids = nt.groupby("record_uid").a.max()
            fp_ids = fp_ids[fp_ids].index
            assert len(fp_ids) == row.normal_notified_segments
            med = seg[(seg.split == split) & (seg.source == "normal_test")][
                ["current_amp", "vib0_std", "vib1_std", "length"]].median()
            comp_cols = {"neglog10p_maxz": "진동/전류 크기", "neglog10p_knn5": "센서 조합",
                         "neglog10p_ae5": "시계열 재구성", "neglog10p_sine": "전류 파형"}
            for uid in fp_ids:
                h = nt[(nt.record_uid == uid) & nt.a]
                s = seg[(seg.split == split) & (seg.record_uid == uid)].iloc[0]
                # 이 예산의 문턱에서 성분 하나만으로도 넘는 성분 = 사유 (예측 파일의 사유 열은 1% 기준)
                fired = sorted({lab for c, lab in comp_cols.items() for v in h[c] if pd.notna(v) and v > row.threshold})
                fps.append(dict(split=split, budget=b, record_uid=uid, alarm_rows=len(h),
                                reasons="+".join(fired) if fired else "복합",
                                current_amp=s.current_amp, current_amp_normal_median=med.current_amp,
                                vib0_std=s.vib0_std, vib0_std_normal_median=med.vib0_std,
                                length=s.length, max_comp_maxz=float(h.comp_maxz.max()),
                                maxz_sensor=";".join(sorted(set(h.maxz_sensor)))))
    pd.DataFrame(err).to_csv(out / "error_conditions.csv", index=False)
    pd.DataFrame(fps).to_csv(out / "fp_segments.csv", index=False)

    # 그림 1: 진동 수준 × 전류 사인 적합도 (기록구간), 기본 분할
    split0 = "normal_60_20_20"
    s = seg[seg.split == split0]
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for lab, name, mk in ((0, "정상 평가 구간", "o"), (1, "이상 구간", "^")):
        t = s[s.label == lab]
        ax.scatter(t.vib0_std, 1 - t.sine_misfit_median, s=18, marker=mk, alpha=.7, label=name)
    t = s[(s.label == 0) & (s.alarm == 1)]
    ax.scatter(t.vib0_std, 1 - t.sine_misfit_median, s=80, facecolors="none", edgecolors="red", label="정상 알림(FP)")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("상부 진동(AI0) 구간 표준편차 (log)")
    ax.set_ylabel("전류 사인 피팅 R² (구간 중앙값)")
    ax.set_title(f"기록구간별 진동 수준 × 전류 파형 ({split0})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_vibration_vs_sineR2.png", dpi=150)
    plt.close(fig)

    # 그림 2: 구간 내 위치별 이상 행 재현율 (conformal 1%)
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for split, g in d[d.source == "abnormal"].groupby("split"):
        r = g.groupby(g.row_in_record.clip(upper=20)).alarm.mean()
        ax.plot(r.index, r.values, marker="o", ms=3, label=f"{split} (w={int(g.w.iloc[0])})")
    w0 = int(d.w.iloc[0])
    ax.axvline(w0 - 1, color="gray", ls=":", lw=1)
    ax.text(w0 - 1 + 0.2, 0.05, f"사인 창이 차는 지점 ({w0}번째 관측)", fontsize=8, color="gray")
    ax.set_xlabel("기록구간 내 관측 순서 (20 이상은 묶음)")
    ax.set_ylabel("이상 행 재현율")
    ax.set_ylim(0, 1.05)
    ax.set_title("구간 시작 직후 미탐 — 전류 파형 창이 차기 전")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "fig_recall_by_position.png", dpi=150)
    plt.close(fig)
    return pd.DataFrame(inf), pd.DataFrame(err)
