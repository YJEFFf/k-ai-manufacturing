"""J4 위원 독립 점검 1: 원본 CSV만으로 데이터 구조·핵심 수치 재계산.

팀 코드를 import하지 않는다. 원본 두 CSV만 읽는다. 결과는 j4_data_check.json.
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python j4_data_check.py <데이터폴더>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(sys.argv[1])
out = Path(__file__).with_name("j4_data_check.json")
S = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
res = {}


def decimals(series):
    s = series.astype(str)
    frac = s.str.split(".").str[1].fillna("")
    frac = frac.str.replace(r"e.*$", "", regex=True)
    return frac.str.len()


def records(df, tol_s):
    t = pd.to_datetime(df.TimeStamp)
    gap = t.diff().dt.total_seconds()
    new = (gap - 0.1).abs().gt(tol_s).fillna(False).to_numpy()
    return np.cumsum(new), gap


def auroc(neg, pos):
    neg, pos = np.asarray(neg, float), np.asarray(pos, float)
    allv = np.r_[neg, pos]
    ranks = pd.Series(allv).rank(method="average").to_numpy()
    rp = ranks[len(neg):].sum()
    return float((rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


frames = {k: pd.read_csv(root / f) for k, f in {"normal": "press_data_normal.csv", "abnormal": "outlier_data.csv"}.items()}
for k, df in frames.items():
    info = dict(rows=len(df), columns=list(df.columns), label_counts=df.Equipment_state.value_counts().to_dict(),
                missing=int(df.isna().sum().sum()), dup_timestamp=int(df.TimeStamp.duplicated().sum()),
                dup_rows_sensor_time=int(df[["TimeStamp"] + S].duplicated().sum()),
                first=df.TimeStamp.iloc[0], last=df.TimeStamp.iloc[-1])
    t = pd.to_datetime(df.TimeStamp)
    info["elapsed_s"] = float((t.iloc[-1] - t.iloc[0]).total_seconds())
    info["monotonic"] = bool(t.is_monotonic_increasing)
    for tol in (1e-6, 0.02):
        seg, gap = records(df, tol)
        n = int(seg.max() + 1)
        lens = pd.Series(seg).value_counts().sort_index()
        info[f"records_tol_{tol}"] = n
        info[f"record_len_tol_{tol}"] = dict(min=int(lens.min()), median=float(lens.median()), max=int(lens.max()),
                                            mean=float(lens.mean()))
    seg, gap = records(df, 1e-6)
    between = gap[(gap - 0.1).abs() > 1e-6].dropna()
    info["between_record_gap_s"] = dict(min=float(between.min()), median=float(between.median()), max=float(between.max()))
    within = gap[(gap - 0.1).abs() <= 1e-6]
    info["within_gap_exact_0.1_share"] = float(len(within) / max(1, gap.notna().sum()))
    info["decimals"] = {c: pd.Series(decimals(df[c])).value_counts().sort_index().head(12).to_dict() for c in S}
    info["describe"] = {c: dict(mean=float(df[c].mean()), sd=float(df[c].std()), min=float(df[c].min()), max=float(df[c].max())) for c in S}
    res[k] = info

# 수집 밀도: 경과 1시간당 기록 수
nrm = frames["normal"]
seg_n, _ = records(nrm, 1e-6)
res["records_per_elapsed_hour"] = float((seg_n.max() + 1) / (res["normal"]["elapsed_s"] / 3600))
res["rows_per_elapsed_hour"] = float(len(nrm) / (res["normal"]["elapsed_s"] / 3600))
res["alerts_per_8h_at_1_over_121"] = float(res["records_per_elapsed_hour"] * 8 / 121)

# 기록 단위 통계
ab = frames["abnormal"]
seg_a, _ = records(ab, 1e-6)
rec = {}
for name, df, seg in (("normal", nrm, seg_n), ("abnormal", ab, seg_a)):
    g = df.assign(rec=seg).groupby("rec")
    r = pd.DataFrame({f"sd_{c}": g[c].std(ddof=1) for c in S})
    r["len"] = g.size()
    r["cur_mean"] = g[S[2]].mean()
    r["cur_sd"] = g[S[2]].std(ddof=1)
    r["cur_rms_demeaned"] = g[S[2]].apply(lambda x: float(np.sqrt(np.mean((x - x.mean()) ** 2))))
    rec[name] = r
res["current_level_bias_len_ge10"] = {
    k: f"{int(((v.len >= 10) & (v.cur_mean.abs() > v.cur_sd)).sum())}/{int((v.len >= 10).sum())}" for k, v in rec.items()}

# 분할별 평가 구간(A: 480~599, B: 420~599)의 기록 SD 단변량 AUROC(이상 21 대 정상 평가)
splits = {"A": (360, 480), "B": (300, 420)}
au = {}
for sp, (tr_end, cal_end) in splits.items():
    test = rec["normal"].loc[rec["normal"].index >= cal_end]
    au[sp] = {c: round(auroc(test[f"sd_{c}"], rec["abnormal"][f"sd_{c}"]), 3) for c in S}
res["record_sd_auroc_test_vs_abnormal"] = au

# 아주 단순한 기준선(팀 코드와 무관한 J4 구현): 정상 학습 구간의 센서별 평균·SD로 z, 행 점수=max|z|,
# 기록 점수=기록 최대, 보정 기록 최대 점수의 최댓값을 문턱(α≈1/121)으로. 원 입력(정밀도 보정 없음)과 소수 4자리 반올림 둘 다.
def simple_rule(quant):
    out = {}
    for sp, (tr_end, cal_end) in splits.items():
        n = nrm.copy(); a = ab.copy()
        if quant:
            for c in S[:2]:
                n[c] = n[c].round(4); a[c] = a[c].round(4)
            q = 1.1920929
            n[S[2]] = (n[S[2]] / q).round() * q; a[S[2]] = (a[S[2]] / q).round() * q
        tr = n[seg_n < tr_end]
        mu, sd = tr[S].mean(), tr[S].std(ddof=0)
        zn = ((n[S] - mu) / sd).abs().max(axis=1)
        za = ((a[S] - mu) / sd).abs().max(axis=1)
        cal_max = zn[(seg_n >= tr_end) & (seg_n < cal_end)].groupby(seg_n[(seg_n >= tr_end) & (seg_n < cal_end)]).max()
        thr = float(cal_max.max())
        test_mask = seg_n >= cal_end
        test_rec_max = zn[test_mask].groupby(seg_n[test_mask]).max()
        ab_rec_max = za.groupby(seg_a).max()
        tp = int((za > thr).sum()); fn = int((za <= thr).sum()); fp = int((zn[test_mask] > thr).sum())
        f1 = 2 * tp / (2 * tp + fp + fn)
        out[sp] = dict(threshold=round(thr, 3), normal_records_alerted=f"{int((test_rec_max > thr).sum())}/{len(test_rec_max)}",
                       abnormal_records_detected=f"{int((ab_rec_max > thr).sum())}/{len(ab_rec_max)}",
                       row_tp=tp, row_fn=fn, row_fp=fp, row_f1=round(f1, 4),
                       record_auroc=round(auroc(test_rec_max, ab_rec_max), 4))
    return out


res["j4_simple_maxabsz_raw"] = simple_rule(False)
res["j4_simple_maxabsz_matched"] = simple_rule(True)

# 분할 부분별 진동 SD(README '가장 조용한 A 평가 구간' 주장 점검)
parts = {"A_cal": (360, 480), "A_test": (480, 600), "B_cal": (300, 420), "B_test": (420, 600)}
res["split_part_vibration_sd"] = {k: {c: round(float(nrm.loc[(seg_n >= a) & (seg_n < b), c].std()), 3) for c in S[:2]} for k, (a, b) in parts.items()}

# 이상 기록 21개: 기록 사이 공백과 길이
seg_a_lens = pd.Series(seg_a).value_counts().sort_index()
res["abnormal_record_lengths"] = seg_a_lens.tolist()
t = pd.to_datetime(ab.TimeStamp)
g = t.diff().dt.total_seconds()
res["abnormal_between_gaps_s"] = sorted(round(float(x), 2) for x in g[(g - 0.1).abs() > 1e-6].dropna())
out.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: res[k] for k in ("split_part_vibration_sd", "records_per_elapsed_hour", "alerts_per_8h_at_1_over_121", "current_level_bias_len_ge10",
                                      "record_sd_auroc_test_vs_abnormal", "j4_simple_maxabsz_raw", "j4_simple_maxabsz_matched")},
                 ensure_ascii=False, indent=1))
