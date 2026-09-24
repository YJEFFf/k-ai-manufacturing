"""평가 집계 — PLAN.md §3·§4.2·§5.1. 주 지표: 이상 탐지 구간, 정상 알림 구간, 판정 가능 구간·행, 첫 경보 지연.

vendor summarize_records(frame, scores, threshold, source, common)를 두 기준 모두에 쓴다:
경보 ⇔ score > threshold 이며, conformal 문턱은 calibrate.conformal_threshold로 p ≤ α와 동치가 되게 정한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score

from .calibrate import binomial_upper95, conformal_p, segment_max, thresholds_for


def _safe_f1(truth, pred):
    return float(f1_score(truth, pred)) if pred.any() or truth.any() else 0.0


def evaluate_models(vendor, split_name: str, preprocess: str, model_scores: dict, frames: dict, segs: dict,
                    comp_bounds: dict | None = None, threshold_override: dict | None = None, units=("recording_segments", "rows")):
    """model_scores[model] = {"cal": arr, "test": arr, "abn": arr}. frames/segs: cal, test, abn.
    comp_bounds[model] = 사인 성분의 이론상 최댓값 변환값 g_s(1) (결합 모델만).
    threshold_override[(model, unit)] = thresholds_for() 형식의 행 목록 → 보정셋 대신 고정 문턱 사용(동결 진단용).
    반환 (metrics, records)."""
    cal, test, abn = frames["cal"], frames["test"], frames["abn"]
    metrics, records = [], []
    for model, sc in model_scores.items():
        cal_seg_max = segment_max(sc["cal"], segs["cal"])
        for unit, cal_values in (("recording_segments", cal_seg_max), ("rows", sc["cal"])):
            if unit not in units:
                continue
            th_rows = (threshold_override or {}).get((model, unit)) or thresholds_for(cal_values, unit)
            for th in th_rows:
                thr = th["threshold"]
                common = dict(split=split_name, preprocess=preprocess, model=model, calibration_unit=unit,
                              criterion=th["criterion"], alpha=th["alpha"])
                cs, _, _, ca = vendor.summarize_records(cal, sc["cal"], thr, "normal_calibration", common)
                ns, nr, _, na = vendor.summarize_records(test, sc["test"], thr, "normal_test", common)
                as_, ar, _, aa = vendor.summarize_records(abn, sc["abn"], thr, "abnormal_test", common)
                truth = np.r_[np.zeros(len(test), int), np.ones(len(abn), int)]
                alarm = np.r_[na, aa].astype(int)
                allsc = np.r_[sc["test"], sc["abn"]]
                valid = np.isfinite(allsc)
                tn, fp, fn, tp = confusion_matrix(truth, alarm, labels=[0, 1]).ravel()
                k, n_norm = ns["notified_segments"], ns["recording_segments"]
                row = dict(**common, alpha_grid=th["alpha_grid"], allowed_exceedances=th["allowed_exceedances"],
                           n_calibration=th["n_calibration"], threshold=thr, alarm_possible=bool(th["alarm_possible"]),
                           calibration_notified_segments=cs["notified_segments"], calibration_alarm_rows=cs["alarm_rows"],
                           normal_segments=n_norm, normal_notified_segments=k, normal_alarm_rows=ns["alarm_rows"],
                           normal_alarm_runs=ns["alarm_runs"], normal_notified_fraction=k / n_norm,
                           normal_binomial_upper95=binomial_upper95(k, n_norm),
                           normal_scored_segments=ns["scored_segments"], normal_row_coverage=ns["row_coverage"],
                           abnormal_segments=as_["recording_segments"], abnormal_notified_segments=as_["notified_segments"],
                           abnormal_missed_segments=as_["recording_segments"] - as_["notified_segments"],
                           abnormal_alarm_rows=as_["alarm_rows"], abnormal_alarm_runs=as_["alarm_runs"],
                           abnormal_scored_segments=as_["scored_segments"], abnormal_row_coverage=as_["row_coverage"],
                           abnormal_row_recall=float(aa.mean()),
                           delay_median_s=as_["conditional_median_first_alarm_delay_seconds"],
                           delay_p90_s=as_["conditional_p90_first_alarm_delay_seconds"],
                           delay_max_s=max([r["first_alarm_delay_seconds"] for r in ar if r["first_notification"]], default=None),
                           tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
                           precision=float(tp / (tp + fp)) if tp + fp else 0.0, recall=float(tp / (tp + fn)) if tp + fn else 0.0,
                           f1_all_rows=_safe_f1(truth, alarm), f1_scored_rows=_safe_f1(truth[valid], alarm[valid]),
                           ap_scored_rows=float(average_precision_score(truth[valid], allsc[valid])) if valid.any() and truth[valid].any() else float("nan"))
                if comp_bounds and model in comp_bounds:
                    row["sine_component_max_transformed"] = comp_bounds[model]
                    row["waveform_only_alarm_possible"] = bool(np.isfinite(comp_bounds[model]) and comp_bounds[model] > thr)
                if unit == "recording_segments" and th["criterion"] == "conformal":
                    p_all = conformal_p(cal_values, allsc)
                    row["conformal_p_alarm_rows_equal_threshold_rows"] = bool(((np.nan_to_num(p_all, nan=1.0) <= th["alpha"]).astype(int) == alarm).all())
                metrics.append(row)
                records.extend(nr + ar)
    return pd.DataFrame(metrics), pd.DataFrame(records)


def comparison_markdown(mt: pd.DataFrame, path, unit="recording_segments", criterion="conformal"):
    """보고서용 요약표: 셀 = 이상 탐지/21 · 정상 알림/n · 전체 행 F1 (지정 기준)."""
    t = mt[(mt.calibration_unit == unit) & (mt.criterion == criterion)].copy()
    t["cell"] = (t.abnormal_notified_segments.astype(str) + "/" + t.abnormal_segments.astype(str) + " · "
                 + t.normal_notified_segments.astype(str) + "/" + t.normal_segments.astype(str) + " · " + t.f1_all_rows.round(3).astype(str))
    lines = [f"# 모델 비교 (자동 생성) — 보정 단위 {unit}, 기준 {criterion}", "",
             "셀 = 이상 탐지 구간 · 정상 알림 구간 · 전체 행 F1. 문턱은 정상 보정 구간에서만 정한다. 성능 수치는 이미 본 자료에 대한 탐색적 평가다.", ""]
    for pre, g in t.groupby("preprocess"):
        pv = g.pivot_table(index="model", columns=["split", "alpha"], values="cell", aggfunc="first")
        head = ["model"] + [f"{s} α={a:g}" for s, a in pv.columns]
        lines += [f"## 전처리 {pre}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        lines += ["| " + " | ".join([str(i)] + [str(v) for v in pv.loc[i]]) + " |" for i in pv.index]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
