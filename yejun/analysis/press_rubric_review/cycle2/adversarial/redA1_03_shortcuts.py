"""A1-3 지름길(부수 성질) 시험과 한 줄짜리 검출기.

(a) 고장과 무관할 수 있는 기록 단위 특징의 분리력(AUROC)
(b) 한 줄짜리 검출기: 정상 보정 기록 최대값을 문턱으로(α=1% conformal과 같은 규칙) → 기록·행 단위 성능을 v2와 나란히
(c) 경보 유지(latch) 규칙이 행 F1에 주는 영향
팀 모듈을 import하지 않는다.
"""
import json

import numpy as np
import pandas as pd

import redA1_common as C

pd.set_option("display.width", 250, "display.max_columns", 60, "display.max_rows", 300)
normal, abnormal = C.load_raw()
seg_n, seg_a = C.segment_ids(normal[C.TIME]), C.segment_ids(abnormal[C.TIME])
pos_n, pos_a = C.positions(seg_n), C.positions(seg_a)
sec_n, sec_a = C.seconds(normal[C.TIME]), C.seconds(abnormal[C.TIME])
Xn, Xa = C.quantize(normal[C.SENS].to_numpy(float)), C.quantize(abnormal[C.SENS].to_numpy(float))
out = {}


# ---------- (a) 기록 단위 특징 ----------
def long_sine(x):
    """기록 전체에 단일 사인+상수 적합: (주파수, R², 진폭, 상수)."""
    n = len(x)
    if n < 17:
        return np.nan, np.nan, np.nan, np.nan
    t = np.arange(n) * C.DT
    sst = ((x - x.mean()) ** 2).sum()
    best = (np.inf, np.nan, None)
    for f in np.arange(0.05, 5.0, 0.005):
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(n)])
        b, *_ = np.linalg.lstsq(A, x, rcond=None)
        e = ((x - A @ b) ** 2).sum()
        if e < best[0]:
            best = (e, f, b)
    e, f, b = best
    return f, 1 - e / sst if sst > 0 else np.nan, float(np.hypot(b[0], b[1])), float(b[2])


def record_table(df, X, seg, sec, label):
    pos = C.positions(seg)
    rows = []
    starts = np.flatnonzero(pos == 0)
    ts = pd.to_datetime(df[C.TIME])
    for r, i0 in enumerate(starts):
        m = seg == r
        x = X[m]
        cur = x[:, 2]
        f, r2, amp, dc = long_sine(cur)
        gap = sec[i0] - sec[i0 - 1] if i0 > 0 else np.nan
        ms = ts.iloc[i0].microsecond / 1000.0
        d1 = np.abs(np.diff(cur)) if len(cur) > 1 else np.array([np.nan])
        d2 = np.abs(cur[2:] - 2 * cur[1:-1] + cur[:-2]) if len(cur) > 2 else np.array([np.nan])
        rows.append(dict(data=label, record=r, n=len(cur), gap_before_s=gap, start_ms_mod100=ms % 100, start_ms_mod1000=ms,
                         cur_mean=cur.mean(), cur_abs_mean=abs(cur.mean()), cur_rms=cur.std(), cur_max_abs=np.abs(cur).max(),
                         v0_mean=x[:, 0].mean(), v1_mean=x[:, 1].mean(), v0_abs_mean=abs(x[:, 0].mean()), v1_abs_mean=abs(x[:, 1].mean()),
                         v0_sd=x[:, 0].std(), v1_sd=x[:, 1].std(), v0_max_abs=np.abs(x[:, 0]).max(), v1_max_abs=np.abs(x[:, 1]).max(),
                         freq=f, sine_r2=r2, sine_amp=amp, sine_dc=dc, freq_dev=abs(f - 0.6) if np.isfinite(f) else np.nan,
                         d1_max=np.nanmax(d1), d2_max=np.nanmax(d2), first_row=int(i0)))
    return pd.DataFrame(rows)


rn = record_table(normal, Xn, seg_n, sec_n, "normal")
ra = record_table(abnormal, Xa, seg_a, sec_a, "abnormal")
rn.to_csv(C.OUT / "redA1_03_records_normal.csv", index=False)
ra.to_csv(C.OUT / "redA1_03_records_abnormal.csv", index=False)

features = ["n", "gap_before_s", "start_ms_mod100", "start_ms_mod1000", "cur_mean", "cur_abs_mean", "cur_rms", "cur_max_abs", "v0_mean", "v1_mean",
            "v0_abs_mean", "v1_abs_mean", "v0_sd", "v1_sd", "v0_max_abs", "v1_max_abs", "freq", "freq_dev", "sine_r2", "sine_amp", "sine_dc", "d1_max", "d2_max"]
nature = dict(n="수집", gap_before_s="수집", start_ms_mod100="수집", start_ms_mod1000="수집", cur_mean="수준(영점·위상)", cur_abs_mean="수준(영점·위상)",
              cur_rms="운전 수준", cur_max_abs="운전 수준", v0_mean="수준", v1_mean="수준", v0_abs_mean="수준", v1_abs_mean="수준", v0_sd="진동 크기",
              v1_sd="진동 크기", v0_max_abs="진동 크기", v1_max_abs="진동 크기", freq="전류 주파수", freq_dev="전류 주파수", sine_r2="전류 파형",
              sine_amp="운전 수준", sine_dc="수준(영점·위상)", d1_max="전류 매끄러움", d2_max="전류 매끄러움")
auc_rows = []
for sid, lo in (("A", 480), ("B", 420), ("all", 0)):
    tn = rn[rn.record >= lo]
    for f in features:
        a = C.auroc(tn[f], ra[f])
        auc_rows.append(dict(normal_set=f"정상 평가 {sid}" if sid != "all" else "정상 전체", feature=f, nature=nature[f],
                             n_normal=int(tn[f].notna().sum()), n_abnormal=int(ra[f].notna().sum()), auroc=a, separation=max(a, 1 - a),
                             normal_median=float(tn[f].median()), abnormal_median=float(ra[f].median()),
                             normal_min=float(tn[f].min()), normal_max=float(tn[f].max()), abnormal_min=float(ra[f].min()), abnormal_max=float(ra[f].max())))
auc = pd.DataFrame(auc_rows)
auc.to_csv(C.OUT / "redA1_03_record_feature_auroc.csv", index=False)
print("== (a) 기록 단위 특징 AUROC(분리력 = max(AUROC, 1−AUROC))")
print(auc.pivot(index="feature", columns="normal_set", values="separation").round(3).assign(nature=pd.Series(nature)).sort_values("정상 전체", ascending=False).to_string())
print(auc[auc.normal_set.eq("정상 전체")][["feature", "normal_median", "abnormal_median", "normal_min", "normal_max", "abnormal_min", "abnormal_max"]].round(4).to_string(index=False))

# ---------- (b) 한 줄짜리 검출기 ----------
print("\n== (b) 한 줄짜리 검출기(문턱 = 정상 보정 기록 최대, α=1% 규칙)")
W0 = 2 * np.cos(2 * np.pi * 0.6 * 0.1)   # 순수 0.6 Hz 진동자의 계수(적합 없음)


def row_stats(X, seg):
    cur = X[:, 2]
    n = len(cur)
    pos = C.positions(seg)
    d1 = np.full(n, np.nan); d2 = np.full(n, np.nan); osc = np.full(n, np.nan)
    i1 = C.windows_index(seg, 2); i2 = C.windows_index(seg, 3)
    d1[i1] = np.abs(cur[i1] - cur[i1 - 1])
    d2[i2] = np.abs(cur[i2] - 2 * cur[i2 - 1] + cur[i2 - 2])
    osc[i2] = np.abs(cur[i2] - W0 * cur[i2 - 1] + cur[i2 - 2])
    s = pd.Series(cur)
    g = s.groupby(seg)
    run_mean = g.expanding().mean().reset_index(level=0, drop=True).to_numpy()
    cnt = g.cumcount().to_numpy() + 1
    # 기록 안 누적 평균의 절댓값(17행 이상 본 뒤)
    dc = np.where(cnt >= 17, np.abs(run_mean), np.nan)
    v0 = np.abs(X[:, 0]); v1 = np.abs(X[:, 1])
    # 최근 3행 전류 범위가 너무 작거나(정체) 큰지: 최근 5행 표준편차
    return dict(abs_v0=v0, abs_v1=v1, abs_cur=np.abs(cur), d1_cur=d1, d2_cur=d2, osc06_fixed=osc, running_dc_17=dc,
                max_abs_vib=np.maximum(v0 / 0.074, v1 / 0.125))


def evaluate(score_cal, seg_cal, score_n, seg_nt, score_a, seg_ab, alpha=0.01, latch=False):
    cal = C.record_max(score_cal, seg_cal)   # 팀 규칙과 같이 점수 없는 기록은 −inf로 남겨 n=120 유지
    pn, pa = C.conformal_p(cal, score_n), C.conformal_p(cal, score_a)
    an, aa = np.isfinite(pn) & (pn <= alpha), np.isfinite(pa) & (pa <= alpha)
    if latch:
        an = pd.Series(an).groupby(seg_nt).cummax().to_numpy()
        aa = pd.Series(aa).groupby(seg_ab).cummax().to_numpy()
    r = C.f1_rows(an, aa)
    r.update(normal_records=int(pd.Series(an).groupby(seg_nt).max().sum()), n_normal_records=int(len(np.unique(seg_nt))),
             abnormal_records=int(pd.Series(aa).groupby(seg_ab).max().sum()), n_cal=int(len(cal)),
             scored_abnormal=float(np.isfinite(score_a).mean()))
    first = pd.Series(np.where(aa, C.positions(seg_ab), np.nan)).groupby(seg_ab).min()
    r.update(delay_median_s=float(first.median() * C.DT) if first.notna().any() else np.nan, delay_max_s=float(first.max() * C.DT) if first.notna().any() else np.nan)
    return r, an, aa


one = []
alarms = {}
for sid in ("A", "B"):
    m = C.split_frames(normal, seg_n, sid)
    Sc, Sn, Sa = row_stats(Xn[m["cal"]], seg_n[m["cal"]]), row_stats(Xn[m["test"]], seg_n[m["test"]]), row_stats(Xa, seg_a)
    det = C.Detector().fit(Xn[m["train"]], seg_n[m["train"]]).calibrate(Xn[m["cal"]], seg_n[m["cal"]])
    cc, cn, ca = det.components(Xn[m["cal"]], seg_n[m["cal"]]), det.components(Xn[m["test"]], seg_n[m["test"]]), det.components(Xa, seg_a)
    Sc["v2_score"], Sn["v2_score"], Sa["v2_score"] = cc["score"], cn["score"], ca["score"]
    Sc["v2_dynamics_only"], Sn["v2_dynamics_only"], Sa["v2_dynamics_only"] = cc["ga"], cn["ga"], ca["ga"]
    Sc["v2_waveform_only"], Sn["v2_waveform_only"], Sa["v2_waveform_only"] = cc["gs"], cn["gs"], ca["gs"]
    Sc["v2_magnitude_only"], Sn["v2_magnitude_only"], Sa["v2_magnitude_only"] = cc["gz"], cn["gz"], ca["gz"]
    # 적합 없는 두 줄 결합: 고정 진동자 잔차와 진동 절댓값을 각자 보정 최대로 나눠 큰 쪽(학습 구간을 쓰지 않는다)
    k_osc = np.nanmax(Sc["osc06_fixed"]); k_v0 = np.nanmax(Sc["abs_v0"]); k_v1 = np.nanmax(Sc["abs_v1"]); k_d2 = np.nanmax(Sc["d2_cur"])
    for S in (Sc, Sn, Sa):
        with np.errstate(all="ignore"):
            S["osc06_or_absvib(no_fit)"] = np.fmax(np.fmax(S["osc06_fixed"] / k_osc, S["abs_v0"] / k_v0), S["abs_v1"] / k_v1)
            S["d2_or_absvib(no_fit)"] = np.fmax(np.fmax(S["d2_cur"] / k_d2, S["abs_v0"] / k_v0), S["abs_v1"] / k_v1)
    for name in Sc:
        for latch in (False, True):
            r, an, aa = evaluate(Sc[name], seg_n[m["cal"]], Sn[name], seg_n[m["test"]], Sa[name], seg_a, latch=latch)
            one.append(dict(split=sid, detector=name, latch=latch, **r))
            alarms[(sid, name, latch)] = (an, aa)
one = pd.DataFrame(one)
one.to_csv(C.OUT / "redA1_03_one_line_detectors.csv", index=False)
show = one[["split", "detector", "latch", "tp", "fp", "fn", "f1", "normal_records", "abnormal_records", "delay_median_s", "delay_max_s", "scored_abnormal"]]
print(show.sort_values(["split", "latch", "f1"], ascending=[True, True, False]).to_string(index=False))

# ---------- (c) 위치별 점수 가능성과 천장 ----------
print("\n== (c) 구조적 천장")
length = pd.Series(seg_a).value_counts().sort_index().to_numpy()
ceil = []
for label, first_pos in (("크기(위치 0부터)", 0), ("AR(2)·2차 차분(위치 2부터)", 2), ("사인 6행 창(위치 5부터)", 5), ("사인 8행 창(위치 7부터)", 7),
                         ("MLP-AE 5행 창(위치 4부터)", 4), ("LSTM 20행 창(위치 19부터)", 19)):
    scor = int(np.maximum(length - first_pos, 0).sum())
    ceil.append(dict(component=label, first_position=first_pos, scorable_abnormal_rows=scor, share=scor / 600,
                     f1_ceiling_if_all_scorable_flagged_fp0=2 * scor / (2 * scor + (600 - scor)),
                     records_with_any_scorable_row=int((length > first_pos).sum())))
ceil = pd.DataFrame(ceil)
print(ceil.to_string(index=False))
ceil.to_csv(C.OUT / "redA1_03_structural_ceiling.csv", index=False)
out["record_feature_auroc_top"] = auc[auc.normal_set.eq("정상 전체")].sort_values("separation", ascending=False).head(12).to_dict("records")
out["one_line"] = one.to_dict("records")
out["ceiling"] = ceil.to_dict("records")
(C.OUT / "redA1_03_shortcuts.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
