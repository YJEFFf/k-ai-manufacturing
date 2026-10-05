"""평가: 예준 press_policy_audit.main()의 평가 루프 복제본 + 두 경보 규칙.

- rule="conformal" (주 결과): 보정 초과 수 k = floor(α(n+1) − 1) 까지만 허용 → p = (1+#{보정 ≥ s})/(n+1) ≤ α 와 같다.
  α=1%, n=120 이면 k=0 (보정 최댓값을 넘어야 경보).
- rule="cutoff_yj" (예준 호환): floor(αn) 개 초과 허용 → 실제 상한 (k+1)/(n+1) (예: 1.65%).
예준 파일의 루프는 main() 안에 있어 import할 수 없어 여기서 복제했다. 헬퍼는 vendor에서 import한다.
"""
import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score

RULES = ("conformal", "cutoff_yj")


def conformal_p(cal_max, scores):
    """구간 단위 conformal p값: (1 + #{보정 구간 최댓값 >= s}) / (n+1). NaN 점수는 NaN."""
    ref = np.sort(np.where(np.isfinite(cal_max), cal_max, -np.inf))
    out = np.full(len(scores), np.nan)
    ok = np.isfinite(scores)
    ge = len(ref) - np.searchsorted(ref, scores[ok], side="left")
    out[ok] = (ge + 1) / (len(ref) + 1)
    return out


def conformal_cutoff(calib, budget):
    """strict `score > thr` 경보가 conformal p ≤ α 와 같아지는 문턱. 불가능하면 +inf."""
    v = np.sort(np.where(np.isfinite(calib), calib, -np.inf))[::-1]
    k = int(np.floor(budget * (len(v) + 1) - 1 + 1e-12))
    return float("inf") if k < 0 else float(v[k])


def threshold(yj, calib, budget, rule):
    return conformal_cutoff(calib, budget) if rule == "conformal" else yj.cutoff_at_budget(calib, budget)


def evaluate(yj, split, sets, model_scores, rules=RULES):
    """sets = (cal, test, abnormal) 프레임, model_scores = {model: (cal, test, abn) 점수}.
    반환: metrics 행 목록, records 행 목록."""
    cal, test, abnormal = sets
    cal_groups = yj.blocks(cal)
    metrics, records = [], []
    for model, (cs, ts, as_) in model_scores.items():
        for unit_name in ["rows", "recording_segments"]:
            calib = cs if unit_name == "rows" else yj.segment_max(cs, cal_groups)
            for rule in rules:
                for budget in yj.BUDGETS:
                    thr = threshold(yj, calib, budget, rule)
                    common = dict(split=split, model=model, calibration_unit=unit_name, rule=rule, budget=budget)
                    cal_sum, _, _, cal_alarm = yj.summarize_records(cal, cs, thr, "normal_calibration", common)
                    ns, nr, _, na = yj.summarize_records(test, ts, thr, "normal_test", common)
                    aus, ar, _, aa = yj.summarize_records(abnormal, as_, thr, "abnormal_test", common)
                    records.extend(nr + ar)
                    truth = np.r_[np.zeros(len(test), int), np.ones(len(abnormal), int)]
                    alarm = np.r_[na, aa]
                    allsc = np.r_[ts, as_]
                    valid = np.isfinite(allsc)
                    tn, fp, fn, tp = confusion_matrix(truth, alarm, labels=[0, 1]).ravel()
                    cal_exceed = int(np.sum(np.where(np.isfinite(calib), calib, -np.inf) > thr))
                    res = dict(**common, threshold=thr, tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
                               f1_all_rows=f1_score(truth, alarm, zero_division=0),
                               f1_scored_rows=f1_score(truth[valid], alarm[valid], zero_division=0),
                               ap_scored_rows=average_precision_score(truth[valid], allsc[valid]),
                               abnormal_recall_all_rows=aa.mean(),
                               normal_false_alarm_rate_all_rows=na.mean(),
                               calibration_exceedances=cal_exceed, calibration_units=len(calib),
                               calibration_row_false_alarm_rate=cal_alarm.mean(),
                               calibration_segment_false_alarm_rate=cal_sum["notification_segment_fraction"])
                    res.update({f"normal_{k}": v for k, v in ns.items()})
                    res.update({f"abnormal_{k}": v for k, v in aus.items()})
                    metrics.append(res)
    return metrics, records
