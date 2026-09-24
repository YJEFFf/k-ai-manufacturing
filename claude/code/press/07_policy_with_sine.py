"""③ 프레스: 예준 press_policy_audit.py 틀에 전류 사인 R² 모델 2개를 추가해 두 분할로 재평가.

추가 모델
- sine_r2_8: 기록구간 안 최근 8관측 전류에 단일 사인파(0~5Hz 격자)를 피팅, 점수 = 1 - R².
  구간 시작 7관측은 점수 없음(경보 없음, 분모 유지 — 예준 RMS와 같은 규칙).
- maxz_plus_sine: 두 점수를 정상 '학습' 구간의 ECDF 꼬리확률로 바꿔 -log10(p)의 최댓값.
  사인 점수가 없는 구간 초반은 max-z만 쓴다. 문턱은 하나 → 오경보 예산이 두 규칙 합산으로 적용된다.
분할·예산·분모·집계 함수는 예준 스크립트를 그대로 import 해서 쓴다. 이상 라벨로 고른 설정 없음
(창 길이 8은 06_alias_frequency_audit 탐색에서 정했으므로 '이미 본 데이터의 탐색'임을 보고서에 밝힌다).

실행: python code/press/07_policy_with_sine.py [--audit <press_policy_audit.py>] [--zip <원본 zip>] [--wins 6 8 10 12 --out <폴더>]
"""
import argparse
import importlib.util
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs" / "policy_sine"
DATA = HERE.parents[1] / "data" / "3_소성가공_예지보전"
DEFAULT_AUDIT = HERE.parents[2] / "codex" / "analysis" / "press_welding_review" / "press_policy_audit.py"
WINDOWS = [8]  # --wins 로 민감도 실행 (예: 6 8 10 12)
FREQS = np.arange(0.0, 5.0001, 0.005)


def build_hats(win):
    """주파수별 사인+상수 모델의 hat 행렬 (F, win, win)."""
    t = np.arange(win) * 0.1
    hats = []
    for f in FREQS:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
        hats.append(A @ np.linalg.pinv(A))
    return np.stack(hats)


def sine_score(frame, blocks_fn, win=8):
    """행별 1 - R² (최근 win관측, 같은 기록구간 안에서만)."""
    WIN, HATS = win, build_hats(win)
    x = frame["AI2_Current"].to_numpy(float)
    grp = blocks_fn(frame)
    score = np.full(len(x), np.nan)
    idx = [i for i in range(WIN - 1, len(x)) if grp[i] == grp[i - WIN + 1]]
    if not idx:
        return score
    idx = np.array(idx)
    W = np.stack([x[i - WIN + 1:i + 1] for i in idx])  # (n, W)
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in HATS:
        r = W - W @ H.T
        np.minimum(best, (r * r).sum(1), out=best)
    score[idx] = np.where(sst > 0, best / sst, 0.0)
    return score


def tail_logp(ref, values):
    """정상 학습 점수 ref 대비 꼬리확률 -log10((#ref >= v + 1)/(n+1)). NaN 유지."""
    ref = np.sort(ref[np.isfinite(ref)])
    out = np.full(len(values), np.nan)
    ok = np.isfinite(values)
    ge = len(ref) - np.searchsorted(ref, values[ok], side="left")
    out[ok] = -np.log10((ge + 1) / (len(ref) + 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    ap.add_argument("--zip", type=Path, help="원본 zip. 없으면 DATA 폴더의 CSV 2개를 읽는다")
    ap.add_argument("--wins", type=int, nargs="+", default=WINDOWS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    spec = importlib.util.spec_from_file_location("yj", args.audit)
    yj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(yj)

    if args.zip:
        with zipfile.ZipFile(args.zip) as z:
            src = {n.rsplit("/", 1)[-1]: pd.read_csv(z.open(n)) for n in z.namelist() if n.endswith(".csv")}
    else:
        src = {n: pd.read_csv(DATA / n) for n in ("press_data_normal.csv", "outlier_data.csv")}
    normal, abnormal = src["press_data_normal.csv"], src["outlier_data.csv"]
    nb = yj.blocks(normal)

    metrics, records = [], []
    for split, train_end, cal_end in yj.SPLITS:
        train = normal[nb < train_end].reset_index(drop=True)
        cal = normal[(nb >= train_end) & (nb < cal_end)].reset_index(drop=True)
        test = normal[nb >= cal_end].reset_index(drop=True)
        sets = [cal, test, abnormal]
        scaler = StandardScaler().fit(train[yj.COLS])
        xtrain = scaler.transform(train[yj.COLS])
        mats = [scaler.transform(d[yj.COLS]) for d in sets]
        nn = NearestNeighbors(n_neighbors=5).fit(xtrain)

        maxz = [np.abs(m).max(1) for m in mats]
        ref_z = np.abs(xtrain).max(1)
        scores = {
            "max_abs_z": maxz,
            "5nn_distance": [nn.kneighbors(m)[0].mean(1) for m in mats],
            "trailing_rms5": [yj.rms5(d, scaler) for d in sets],
        }
        for w in args.wins:
            sine = [sine_score(d, yj.blocks, w) for d in sets]
            ref_s = sine_score(train, yj.blocks, w)
            # fmax: 사인 점수가 없는(구간 초반) 쪽은 max-z만 사용
            comb = [np.fmax(tail_logp(ref_z, z_), tail_logp(ref_s, s_)) for z_, s_ in zip(maxz, sine)]
            scores[f"sine_r2_{w}"] = sine
            scores[f"maxz_plus_sine_{w}"] = comb
        cal_groups = yj.blocks(cal)
        for model, (cs, ts, as_) in scores.items():
            for unit in ["rows", "recording_segments"]:
                calib = cs if unit == "rows" else yj.segment_max(cs, cal_groups)
                for budget in yj.BUDGETS:
                    thr = yj.cutoff_at_budget(calib, budget)
                    common = dict(split=split, model=model, calibration_unit=unit, budget=budget)
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
                    metrics.append(res)
        print("done", split, flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    tab = pd.DataFrame(metrics)
    tab.to_csv(args.out / "policy_metrics_with_sine.csv", index=False)
    pd.DataFrame(records).to_csv(args.out / "record_notifications_with_sine.csv", index=False)
    tab["abn_seg"] = tab.abnormal_notified_segments.astype(str) + "/21"
    tab["norm_seg"] = tab.normal_notified_segments.astype(str) + "/" + tab.normal_recording_segments.astype(str)
    tab["delay_med"] = tab.abnormal_conditional_median_first_alarm_delay_seconds
    cols = ["split", "calibration_unit", "budget", "model", "f1_all_rows", "abnormal_recall_all_rows",
            "abn_seg", "norm_seg", "normal_alarm_runs", "delay_med"]
    print(tab[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
