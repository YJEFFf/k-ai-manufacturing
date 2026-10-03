"""1단계: 기록구간을 케이스로 나눠 다변량 시계열 특징을 비교한다.

산출물(outputs/):
- case_features_normal.csv, case_features_abnormal.csv : 케이스별 특징
- feature_separation.csv : 특징별 정상·이상 분포와 기록 단위 AUROC (10행 이상 기록)
- abnormal_timeline.csv : 이상 21케이스의 시간순 특징 (고장 구간 안의 진행)
- precursor_scan.csv : 정상 날 기록 중 이상 서명을 2개 이상 가진 기록 (전조 후보)
- leak_demo.json : 저장 형식(소수 자릿수)만으로 분류했을 때의 행 F1
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from common import OUT, SENSORS, case_table, load_both, load

FEATS = ["vib_upper_sd", "vib_lower_sd", "upper_lower_log_ratio", "upper_lower_corr",
         "vib_upper_lag1", "vib_lower_lag1", "cur_offset_ratio", "cur_resid_ratio", "cur_sine_r2"]
SIGNATURE = {  # 이상 쪽으로 가는 방향
    "cur_sine_r2": "low", "cur_resid_ratio": "high", "upper_lower_corr": "low", "vib_upper_lag1": "high",
}


def main():
    OUT.mkdir(exist_ok=True)
    normal, abnormal = load_both()
    N, A = case_table(normal), case_table(abnormal)
    N.to_csv(OUT / "case_features_normal.csv", index=False)
    A.to_csv(OUT / "case_features_abnormal.csv", index=False)

    n10, a10 = N[N.n >= 10], A[A.n >= 10]
    rows = []
    for f in FEATS:
        y = np.r_[np.zeros(len(n10)), np.ones(len(a10))]
        s = np.r_[n10[f], a10[f]]
        ok = ~np.isnan(s)
        auc = roc_auc_score(y[ok], s[ok])
        lo, hi = n10[f].quantile([0.005, 0.995])
        rows.append(dict(feature=f, normal_median=n10[f].median(), normal_q005=lo, normal_q995=hi,
                         abnormal_median=a10[f].median(), abnormal_min=a10[f].min(), abnormal_max=a10[f].max(),
                         auroc=max(auc, 1 - auc),
                         abnormal_outside_normal=int(((a10[f] < lo) | (a10[f] > hi)).sum()), abnormal_n=len(a10)))
    sep = pd.DataFrame(rows)
    sep.to_csv(OUT / "feature_separation.csv", index=False)

    A.to_csv(OUT / "abnormal_timeline.csv", index=False)

    # 전조 후보: 정상 기록 중 이상 서명 2개 이상 (기준은 정상 전체 10행 이상 기록의 0.5%/99.5% 분위)
    flags = pd.DataFrame(index=N.index)
    for f, d in SIGNATURE.items():
        lo, hi = n10[f].quantile([0.005, 0.995])
        flags[f] = (N[f] < lo) if d == "low" else (N[f] > hi)
    N["signature_count"] = flags.sum(axis=1)
    pre = N[(N.n >= 10) & (N.signature_count >= 2)]
    pre.to_csv(OUT / "precursor_scan.csv", index=False)
    A_flags = pd.DataFrame({f: ((A[f] < n10[f].quantile(.005)) if d == "low" else (A[f] > n10[f].quantile(.995)))
                            for f, d in SIGNATURE.items()})
    A["signature_count"] = A_flags.sum(axis=1)

    # 저장 형식 누수 시연: 원본(형식 맞춤 전)에서 진동 소수 자릿수 > 6 이면 이상
    rawN, rawA = load("press_data_normal.csv", matched=False), load("outlier_data.csv", matched=False)
    def digits(v):
        s = v.astype(str).str.split(".").str[1].fillna("")
        return s.str.len()
    pred = np.r_[(digits(rawN.AI0_Vibration) > 6).to_numpy(), (digits(rawA.AI0_Vibration) > 6).to_numpy()]
    y = np.r_[np.zeros(len(rawN)), np.ones(len(rawA))]
    tp, fp, fn = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum())
    leak = dict(rule="진동 AI0 소수 자릿수 > 6 이면 이상", tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn))
    (OUT / "leak_demo.json").write_text(json.dumps(leak, ensure_ascii=False, indent=2), encoding="utf-8")

    pd.set_option("display.width", 250)
    print("== 특징별 분리 (10행 이상 기록: 정상", len(n10), "/ 이상", len(a10), ")")
    print(sep.round(3).to_string(index=False))
    print("\n== 이상 21케이스 시간순")
    print(A[["rec", "n", "t0", "vib_upper_sd", "vib_lower_sd", "upper_lower_corr", "vib_upper_lag1",
             "cur_amp", "cur_offset_ratio", "cur_sine_r2", "signature_count"]].round(3).to_string(index=False))
    print("\n== 전조 후보(정상 날, 서명 2개 이상):", len(pre), "기록")
    if len(pre):
        print(pre[["rec", "n", "t0", "signature_count"] + list(SIGNATURE)].round(3).to_string(index=False))
    print("\n== 정상 기록 서명 개수 분포:", N[N.n >= 10].signature_count.value_counts().sort_index().to_dict())
    print("== 이상 기록 서명 개수 분포:", A.signature_count.value_counts().sort_index().to_dict())
    print("\n== 누수 시연:", leak)


if __name__ == "__main__":
    main()
