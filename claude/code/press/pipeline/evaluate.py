"""평가: 예준 press_policy_audit.main()의 평가 루프 복제본 + 구간 단위 conformal p값.

예준 파일의 루프는 main() 안에 있어 import할 수 없으므로 여기서 복제했다(07_policy_with_sine.py와 같음).
헬퍼(cutoff_at_budget, segment_max, summarize_records, blocks)는 vendor에서 import한다.
"""
import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score


def conformal_p(cal_segment_max, scores):
    """구간 단위 conformal p값: (1 + #{보정 구간 최댓값 >= s}) / (n+1). NaN 점수는 NaN."""
    ref = np.sort(np.where(np.isfinite(cal_segment_max), cal_segment_max, -np.inf))
    out = np.full(len(scores), np.nan)
    ok = np.isfinite(scores)
    ge = len(ref) - np.searchsorted(ref, scores[ok], side="left")
    out[ok] = (ge + 1) / (len(ref) + 1)
    return out


def evaluate(yj, split, sets, model_scores):
    """sets = (cal, test, abnormal) 프레임, model_scores = {model: (cal, test, abn) 점수}.
    반환: metrics 행 목록, records 행 목록, conformal 단위 테스트 결과."""
    cal, test, abnormal = sets
    cal_groups = yj.blocks(cal)
    metrics, records, unit = [], [], []
    for model, (cs, ts, as_) in model_scores.items():
        for unit_name in ["rows", "recording_segments"]:
            calib = cs if unit_name == "rows" else yj.segment_max(cs, cal_groups)
            for budget in yj.BUDGETS:
                thr = yj.cutoff_at_budget(calib, budget)
                common = dict(split=split, model=model, calibration_unit=unit_name, budget=budget)
                cal_sum, _, _, cal_alarm = yj.summarize_records(cal, cs, thr, "normal_calibration", common)
                ns, nr, _, na = yj.summarize_records(test, ts, thr, "normal_test", common)
                aus, ar, _, aa = yj.summarize_records(abnormal, as_, thr, "abnormal_test", common)
                records.extend(nr + ar)
                truth = np.r_[np.zeros(len(test), int), np.ones(len(abnormal), int)]
                alarm = np.r_[na, aa]
                allsc = np.r_[ts, as_]
                valid = np.isfinite(allsc)
                tn, fp, fn, tp = confusion_matrix(truth, alarm).ravel()
                res = dict(**common, threshold=thr, tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
                           f1_all_rows=f1_score(truth, alarm),
                           f1_scored_rows=f1_score(truth[valid], alarm[valid]),
                           ap_scored_rows=average_precision_score(truth[valid], allsc[valid]),
                           abnormal_recall_all_rows=aa.mean(),
                           normal_false_alarm_rate_all_rows=na.mean(),
                           calibration_row_false_alarm_rate=cal_alarm.mean(),
                           calibration_segment_false_alarm_rate=cal_sum["notification_segment_fraction"])
                res.update({f"normal_{k}": v for k, v in ns.items()})
                res.update({f"abnormal_{k}": v for k, v in aus.items()})
                if unit_name == "recording_segments":
                    # conformal 경보(p <= α)와 예준 문턱 경보(score > thr)가 같은 행을 고르는지
                    p_all = conformal_p(calib, allsc)
                    conf_alarm = np.nan_to_num(p_all, nan=1.0) <= budget
                    res["conformal_alarm_diff_rows"] = int((conf_alarm != alarm.astype(bool)).sum())
                    unit.append(dict(split=split, model=model, budget=budget,
                                     diff_rows=res["conformal_alarm_diff_rows"]))
                metrics.append(res)
    return metrics, records, unit
