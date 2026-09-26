"""평가관 01(데이터 이해 및 진단) 독립 재계산.

원본 CSV를 직접 읽어 진단 수치를 다시 계산하고, v1 진단 산출물(diagnosis.json·splits.csv)과 대조한다.
패키지 코드는 import하지 않는다(독립 구현). 결과는 이 폴더의 judge01_checks.json 한 파일에만 쓴다.

실행(yejun/ 작업 폴더):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python analysis/press_rubric_review/judge01_check.py
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
REPO = YEJUN.parent
RAW_DIR = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "data" / "3_소성가공_예지보전"
PKG_DIR = YEJUN / "press_submission" / "data" / "3_소성가공_예지보전"
ZIP = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "Dataset_소성가공 예지보전 AI 데이터셋.zip"
FILES = {"normal": "press_data_normal.csv", "abnormal": "outlier_data.csv"}
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
DIAG = YEJUN / "press_submission" / "outputs" / "diagnosis.json"
SPLITS_CSV = YEJUN / "press_submission" / "outputs" / "splits.csv"
OUT = HERE / "judge01_checks.json"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, float):
        return None if not np.isfinite(o) else o
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def seg_ids(t: pd.Series) -> np.ndarray:
    dt = t.diff().dt.total_seconds()
    new = (dt - 0.1).abs().gt(1e-6).fillna(False).to_numpy()
    return np.cumsum(new)


def decimals(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip().str.lstrip("-")
    return x.str.split(".").str[1].fillna("").str.len()


def main():
    R: dict = {"scope": "평가관 01 독립 재계산. 패키지 코드 import 없음."}

    # ---------- 1. 파일 동일성 ----------
    ident = {}
    with zipfile.ZipFile(ZIP) as z:
        zmem = {Path(n).name: sha(z.read(n)) for n in z.namelist() if n.endswith(".csv")}
    for k, f in FILES.items():
        a, b = (RAW_DIR / f).read_bytes(), (PKG_DIR / f).read_bytes()
        ident[k] = dict(raw_sha=sha(a), pkg_sha=sha(b), zip_sha=zmem.get(f), all_equal=sha(a) == sha(b) == zmem.get(f))
    R["file_identity"] = ident

    frames, strs = {}, {}
    for k, f in FILES.items():
        strs[k] = pd.read_csv(RAW_DIR / f, dtype=str, keep_default_na=False)
        frames[k] = pd.read_csv(RAW_DIR / f)

    # ---------- 2. 스키마·결측·중복 ----------
    schema = {}
    for k in FILES:
        s, d = strs[k], frames[k]
        idx_col = s.columns[0]
        idx = pd.to_numeric(s[idx_col], errors="coerce")
        t = pd.to_datetime(d["TimeStamp"], errors="coerce")
        num = d[SENS].apply(pd.to_numeric, errors="coerce")
        dup_ts = t.duplicated(keep=False)
        dup_rows = d.loc[dup_ts, ["TimeStamp"] + SENS]
        schema[k] = dict(
            columns=list(s.columns), rows=len(d),
            index_column_is_0_to_n_minus_1=bool((idx.to_numpy() == np.arange(len(d))).all()),
            empty_strings={c: int((s[c].str.strip() == "").sum()) for c in s.columns},
            nan_after_parse={c: int(num[c].isna().sum()) for c in SENS},
            nonfinite=int((~np.isfinite(num.to_numpy(float))).sum()),
            bad_timestamp=int(t.isna().sum()),
            ts_monotonic_nondecreasing=bool(t.is_monotonic_increasing),
            negative_dt=int((t.diff().dt.total_seconds() < 0).sum()),
            duplicate_timestamp_rows=int(t.duplicated().sum()),
            duplicate_timestamp_detail=dup_rows.assign(row=dup_rows.index).astype(str).to_dict("records"),
            full_row_duplicates_excl_index=int(d.drop(columns=[d.columns[0]]).duplicated().sum()),
            sensor_triplet_duplicates=int(d[SENS].duplicated().sum()),
            consecutive_identical_triplets=int((d[SENS].diff().abs().sum(axis=1) == 0).iloc[1:].sum()),
            label_values=sorted(d["Equipment_state"].unique().tolist()),
            ts_ms_digits=sorted(s["TimeStamp"].str.split(".").str[1].fillna("").str.len().unique().tolist()),
        )
    R["schema_missing_duplicates"] = schema

    # ---------- 3. 시간 구조·기록구간 ----------
    struct = {}
    segs = {}
    for k in FILES:
        d = frames[k]
        t = pd.to_datetime(d["TimeStamp"])
        dt = t.diff().dt.total_seconds().to_numpy()[1:]
        sg = seg_ids(t)
        segs[k] = sg
        lens = pd.Series(sg).value_counts().sort_index()
        gaps = dt[np.abs(dt - 0.1) > 1e-6]
        pos_gaps = gaps[gaps > 0]
        starts = t.groupby(sg).min()
        start_ms_mod100 = ((starts.dt.microsecond // 1000) % 100).to_numpy()
        # 구간 시작 행 번호가 50의 배수에 놓이는가(50행 묶음 구조 여부)
        start_rows = np.flatnonzero(np.r_[True, sg[1:] != sg[:-1]])
        struct[k] = dict(
            start=str(t.min()), end=str(t.max()),
            weekday=t.min().day_name(), elapsed_min=(t.max() - t.min()).total_seconds() / 60,
            recorded_min=len(d) * 0.1 / 60, recorded_fraction_of_elapsed=(len(d) * 0.1) / (t.max() - t.min()).total_seconds(),
            n_dt=len(dt), dt_exact_0_1=int((np.abs(dt - 0.1) <= 1e-6).sum()), dt_zero=int((dt == 0).sum()),
            dt_gt_0_15=int((dt > 0.15).sum()), dt_other=int(((dt > 0) & (dt <= 0.15) & (np.abs(dt - 0.1) > 1e-6)).sum()),
            gap_s_min=float(pos_gaps.min()), gap_s_q25=float(np.quantile(pos_gaps, .25)), gap_s_median=float(np.median(pos_gaps)),
            gap_s_q75=float(np.quantile(pos_gaps, .75)), gap_s_max=float(pos_gaps.max()),
            gaps_multiple_of_0_1_within_1ms=float(np.mean(np.abs(pos_gaps / 0.1 - np.round(pos_gaps / 0.1)) * 0.1 < 1e-3)),
            gaps_le_0_5s=int((pos_gaps <= 0.5).sum()),
            segments=int(len(lens)), len_min=int(lens.min()), len_median=float(lens.median()), len_mean=float(lens.mean()),
            len_max=int(lens.max()), len_eq_50=int((lens == 50).sum()), len_gt_50=int((lens > 50).sum()),
            len_lt_8=int((lens < 8).sum()), len_lt_10=int((lens < 10).sum()), len_lt_17=int((lens < 17).sum()),
            len_lt_20=int((lens < 20).sum()), len_ge_30=int((lens >= 30).sum()),
            rows_in_len_lt_17=int(lens[lens < 17].sum()),
            len_1_segments=[int(i) for i in lens[lens == 1].index],
            segment_start_ms_mod100_unique=int(len(np.unique(start_ms_mod100))),
            segment_start_rows_multiple_of_50=float(np.mean(start_rows % 50 == 0)),
            rows_scored_upper_bound={w: int(len(d) - np.minimum(lens.to_numpy(), w - 1).sum()) for w in (5, 8, 10, 20)},
        )
    R["time_structure"] = struct

    # 중복 시각이 만든 경계 확인
    tn = pd.to_datetime(frames["normal"]["TimeStamp"])
    dup_i = np.flatnonzero(tn.duplicated().to_numpy())
    R["duplicate_timestamp_boundary"] = [dict(row=int(i), seg_prev=int(segs["normal"][i - 1]), seg_this=int(segs["normal"][i]),
                                              len_prev=int((segs["normal"] == segs["normal"][i - 1]).sum()),
                                              len_this=int((segs["normal"] == segs["normal"][i]).sum()),
                                              dt_next=float((tn.iloc[i + 1] - tn.iloc[i]).total_seconds()) if i + 1 < len(tn) else None)
                                         for i in dup_i]

    # ---------- 4. 분할·불균형 ----------
    sgn = segs["normal"]
    splits = {}
    for sid, (tr, ca) in {"A": (360, 480), "B": (300, 420)}.items():
        parts = {"train": sgn < tr, "cal": (sgn >= tr) & (sgn < ca), "test": sgn >= ca}
        info = {p: dict(rows=int(m.sum()), segments=int(len(np.unique(sgn[m]))),
                        start=str(tn[m].min()), end=str(tn[m].max())) for p, m in parts.items()}
        nt_rows, nt_seg = info["test"]["rows"], info["test"]["segments"]
        info["test_abnormal_row_prevalence"] = 600 / (600 + nt_rows)
        info["test_abnormal_segment_prevalence"] = 21 / (21 + nt_seg)
        # 모두 양성으로 예측할 때의 행 F1(무정보 기준)
        p = info["test_abnormal_row_prevalence"]
        info["all_positive_row_f1"] = 2 * p / (1 + p)
        splits[sid] = info
    R["splits"] = splits
    R["imbalance"] = dict(row_ratio_abnormal_to_normal=600 / 20000, row_share_abnormal=600 / 20600,
                          segment_share_abnormal=21 / 621, recorded_seconds=dict(normal=2000.0, abnormal=60.0))
    sp = pd.read_csv(SPLITS_CSV)
    R["splits_csv_match"] = all(
        int(sp[(sp.split_id == s) & (sp.part == p)].rows.iloc[0]) == splits[s][p]["rows"] and
        int(sp[(sp.split_id == s) & (sp.part == p)].segments.iloc[0]) == splits[s][p]["segments"]
        for s in ("A", "B") for p in ("train", "cal", "test"))

    # ---------- 5. 저장 정밀도·양자화 ----------
    quant = {}
    for k in FILES:
        s, d = strs[k], frames[k]
        q = {}
        for c in SENS:
            dec = decimals(s[c])
            u = np.unique(d[c].to_numpy(float))
            steps = np.diff(u)
            q[c] = dict(dec_mode=int(dec.mode()[0]), dec_max=int(dec.max()),
                        dec_share_mode=float((dec == dec.mode()[0]).mean()),
                        dec_share_ge_10=float((dec >= 10).mean()),
                        n_unique=int(len(u)), min_positive_step=float(steps[steps > 0].min()))
        r = d["AI2_Current"].to_numpy(float) / 1.1920929
        res = np.abs(r - np.round(r))
        q["current_grid_1_1920929"] = dict(on_grid_tol_1e3=float((res < 1e-3).mean()), on_grid_tol_1e6=float((res < 1e-6).mean()),
                                           median_residual=float(np.median(res)))
        # 1.1920929 = 2^-23 * 1e7 (float32 기계 엡실론 × 1e7) 여부
        q["grid_equals_float32_eps_times_1e7"] = abs(1.1920929 - np.finfo(np.float32).eps * 1e7) < 1e-7
        for c in SENS[:2]:
            x = d[c].to_numpy(float) * 1e6
            q[c]["finer_than_1e-6_share"] = float((np.abs(x - np.round(x)) > 1e-3).mean())
        quant[k] = q
    R["quantization"] = quant

    # matched 후 lag-1(구간 내부) — 형식 정규화가 자기상관 차이를 지우는지
    def lag1(x, sg):
        same = sg[1:] == sg[:-1]
        a, b = x[:-1][same], x[1:][same]
        return float(np.corrcoef(a, b)[0, 1])

    def lag1_demeaned(x, sg):
        xm = x - pd.Series(x).groupby(sg).transform("mean").to_numpy()
        return lag1(xm, sg)

    ac = {}
    for k in FILES:
        d, sg = frames[k], segs[k]
        ac[k] = {}
        for c in SENS:
            x = d[c].to_numpy(float)
            step = 1e-4 if c != "AI2_Current" else 1.1920929
            xm = np.round(x / step) * step
            ac[k][c] = dict(raw=lag1(x, sg), matched=lag1(xm, sg), raw_segment_demeaned=lag1_demeaned(x, sg))
    R["lag1_within_segment"] = ac

    # ---------- 6. 이상치·범위 ----------
    outl = {}
    n, a = frames["normal"], frames["abnormal"]
    trA = sgn < 360
    for c in SENS:
        x = n[c].to_numpy(float)
        med = np.median(x[trA]); mad = 1.4826 * np.median(np.abs(x[trA] - med))
        z = (x - med) / mad
        za = (a[c].to_numpy(float) - med) / mad
        lo, hi = x[trA].min(), x[trA].max()
        outl[c] = dict(
            normal_train_A_median=float(med), normal_train_A_mad_sd=float(mad),
            normal_rows_abs_robust_z_gt_4=int((np.abs(z) > 4).sum()), normal_rows_abs_robust_z_gt_5=int((np.abs(z) > 5).sum()),
            normal_abs_robust_z_max=float(np.abs(z).max()),
            normal_rows_at_global_min_or_max=int(((x == x.min()) | (x == x.max())).sum()),
            normal_non_train_rows_outside_trainA_range=int(((x < lo) | (x > hi))[~trA].sum()),
            abnormal_rows_outside_trainA_range=int(((a[c] < lo) | (a[c] > hi)).sum()),
            abnormal_rows_abs_robust_z_gt_5=int((np.abs(za) > 5).sum()),
            abnormal_rows_at_min_or_max=int(((a[c] == a[c].min()) | (a[c] == a[c].max())).sum()),
        )
    # 전류는 사인형이라 MAD 기반 z가 부적절할 수 있음을 함께 기록
    outl["note"] = "전류는 부호가 바뀌는 사인형 값이라 행 단위 robust z는 참고치. 진동은 평균 0 근처 대칭 분포."
    # 이상 구간 중 어느 센서든 정상 학습 범위를 벗어난 행이 있는 구간 수
    seg_a = segs["abnormal"]
    lo = {c: n[c][trA].min() for c in SENS}; hi = {c: n[c][trA].max() for c in SENS}
    outside_any = np.zeros(len(a), bool); outside_vib = np.zeros(len(a), bool)
    for c in SENS:
        m = ((a[c] < lo[c]) | (a[c] > hi[c])).to_numpy()
        outside_any |= m
        if c != "AI2_Current":
            outside_vib |= m
    outl["abnormal_rows_outside_any_sensor"] = int(outside_any.sum())
    outl["abnormal_segments_with_row_outside_any"] = int(len(np.unique(seg_a[outside_any])))
    outl["abnormal_segments_with_row_outside_vibration"] = int(len(np.unique(seg_a[outside_vib])))
    R["outliers_ranges"] = outl

    # ---------- 7. 센서 간 관계·전류 성질 ----------
    rel = {}
    for k in FILES:
        d, sg = frames[k], segs[k]
        cm = d[SENS].corr().to_numpy()
        cur = d["AI2_Current"].to_numpy(float)
        lens = pd.Series(sg).value_counts()
        long_ids = lens[lens >= 17].index
        segmean = pd.Series(cur).groupby(sg).mean()
        demeaned = cur - pd.Series(cur).groupby(sg).transform("mean").to_numpy()
        # 사인 표본의 첨도는 1.5, 가우스는 3 (구간 평균 제거 후, 길이 17 이상)
        mk = np.isin(sg, long_ids)
        xm = demeaned[mk]
        kurt = float(np.mean(xm ** 4) / np.mean(xm ** 2) ** 2)
        rel[k] = dict(corr_AI0_AI1=float(cm[0, 1]), corr_AI0_AI2=float(cm[0, 2]), corr_AI1_AI2=float(cm[1, 2]),
                      current_negative_share=float((cur < 0).mean()),
                      current_segment_mean_median_len_ge17=float(segmean.loc[long_ids].median()),
                      current_demeaned_kurtosis_len_ge17=kurt,
                      vib_sd={c: float(d[c].std()) for c in SENS[:2]})
    R["sensor_relations"] = rel

    # ---------- 8. 정상 77분 안의 시간 변화(분할 부분별) ----------
    drift = {}
    for sid, (tr, ca) in {"A": (360, 480), "B": (300, 420)}.items():
        parts = {"train": sgn < tr, "cal": (sgn >= tr) & (sgn < ca), "test": sgn >= ca}
        drift[sid] = {}
        for p, m in parts.items():
            cur = n["AI2_Current"].to_numpy(float)[m]
            sgp = sgn[m]
            dm = cur - pd.Series(cur).groupby(sgp).transform("mean").to_numpy()
            drift[sid][p] = dict(AI0_sd=float(n["AI0_Vibration"][m].std()), AI1_sd=float(n["AI1_Vibration"][m].std()),
                                 current_rms_demeaned=float(np.sqrt(np.mean(dm ** 2))))
    R["normal_part_drift"] = drift

    # ---------- 9. 사인 적합 R² 독립 재현(길이 ≥10, 0~5Hz, 0.005Hz) ----------
    freqs = np.arange(0.0, 5.0001, 0.005)
    proj_cache: dict = {}

    def r2_best(x):
        m = len(x)
        if m not in proj_cache:
            tt = np.arange(m) * 0.1
            P = []
            for f in freqs:
                A = np.column_stack([np.sin(2 * np.pi * f * tt), np.cos(2 * np.pi * f * tt), np.ones(m)])
                Q, _ = np.linalg.qr(A)
                P.append(Q)
            proj_cache[m] = P
        sst = ((x - x.mean()) ** 2).sum()
        best, bf = -np.inf, None
        for f, Q in zip(freqs, proj_cache[m]):
            fit = Q @ (Q.T @ x)
            r2 = 1 - ((x - fit) ** 2).sum() / sst
            if r2 > best + 1e-12:
                best, bf = r2, f
        return best, bf

    wave = {}
    for k in FILES:
        d, sg = frames[k], segs[k]
        cur = d["AI2_Current"].to_numpy(float)
        r2s, fs = [], []
        for s in np.unique(sg):
            idx = np.flatnonzero(sg == s)
            if len(idx) < 10:
                continue
            r2, f = r2_best(cur[idx])
            r2s.append(r2); fs.append(f)
        r2s, fs = np.array(r2s), np.array(fs)
        wave[k] = dict(n=int(len(r2s)), r2_min=float(r2s.min()), r2_median=float(np.median(r2s)), r2_max=float(r2s.max()),
                       f_median=float(np.median(fs)), f_exact_0_6=int((np.abs(fs - 0.6) < 1e-9).sum()),
                       f_min=float(fs.min()), f_max=float(fs.max()))
    R["waveform_independent"] = wave
    # 앨리어싱 가설 아래 R²를 만드는 가우스 표본화 시각 흔들림(σ): 코히런트 비율 exp(-(2π·60·σ)^2)=R²
    R["alias_timing_equivalence"] = {
        "assumption": "전류가 60Hz 순시값이고 R² 저하가 전부 표본화 시각의 독립 가우스 흔들림에서 온다는 가정(검증 불가)",
        "sigma_ms_for_normal_median_r2": float(np.sqrt(-np.log(wave["normal"]["r2_median"])) / (2 * np.pi * 60) * 1e3),
        "sigma_ms_for_abnormal_median_r2": float(np.sqrt(-np.log(wave["abnormal"]["r2_median"])) / (2 * np.pi * 60) * 1e3),
        "sigma_ms_for_abnormal_max_r2": float(np.sqrt(-np.log(wave["abnormal"]["r2_max"])) / (2 * np.pi * 60) * 1e3),
    }

    # ---------- 9b. 정상 60구간 블록별 운전 수준(시간 관계) ----------
    blk = sgn // 60
    curn = n["AI2_Current"].to_numpy(float)
    dmn = curn - pd.Series(curn).groupby(sgn).transform("mean").to_numpy()
    g = pd.DataFrame(dict(blk=blk, AI0=n["AI0_Vibration"], AI1=n["AI1_Vibration"], dm=dmn, t=tn))
    R["normal_60seg_blocks"] = {
        f"{int(b) * 60}-{int(b) * 60 + 59}": dict(start=str(x.t.min())[11:19], end=str(x.t.max())[11:19],
                                                  AI0_sd=float(x.AI0.std()), AI1_sd=float(x.AI1.std()),
                                                  current_rms_demeaned=float(np.sqrt(np.mean(x.dm ** 2))))
        for b, x in g.groupby("blk")}
    # 구간 최대 진동 |z|(분할 A 학습 평균·표준편차) — 정상 학습 q95 초과 구간 비율
    vib = n[SENS[:2]]
    zv = ((vib - vib[trA].mean()) / vib[trA].std()).abs().max(axis=1)
    segmax = zv.groupby(sgn).max()
    q95 = float(segmax[segmax.index < 360].quantile(.95))
    parts_all = {"A_train": (0, 360), "A_cal": (360, 480), "A_test": (480, 600), "B_cal": (300, 420), "B_test": (420, 600),
                 "block_420_479": (420, 480), "block_480_539": (480, 540), "block_540_599": (540, 600)}
    R["segment_vibration_maxz"] = dict(trainA_q95=q95, parts={
        k: dict(n=int(((segmax.index >= lo) & (segmax.index < hi)).sum()),
                mean=float(segmax[(segmax.index >= lo) & (segmax.index < hi)].mean()),
                n_gt_q95=int((segmax[(segmax.index >= lo) & (segmax.index < hi)] > q95).sum()))
        for k, (lo, hi) in parts_all.items()})

    # ---------- 9c. v2 저장 모델: 보정 구간 최대 점수 vs 평가 구간 최대 점수(교환가능성 점검) ----------
    from scipy.stats import mannwhitneyu
    v2 = {}
    for s_, off in (("A", 480), ("B", 420)):
        stt = json.loads((YEJUN / "press_guard" / "artifacts" / f"guard_{s_}.json").read_text(encoding="utf-8"))["state"]
        cal = np.asarray(stt["calibration"], float)
        pr = pd.read_csv(YEJUN / "press_guard" / "outputs" / f"predictions_normal_{s_}.csv")
        rec = pr.groupby("record_id")["score"].max()
        tm = rec.to_numpy()
        alarm_rec = pr.groupby("record_id")["alarm"].max()
        cm_ = float(np.median(cal))
        blocks = {}
        for b, v in rec.groupby((rec.index + off) // 60):
            blocks[f"{int(b) * 60}-{int(b) * 60 + 59}"] = dict(n=int(len(v)), median=float(v.median()),
                                                                share_gt_cal_median=float((v > cm_).mean()))
        v2[s_] = dict(cal_n=int(len(cal)), cal_median=cm_, test_n=int(len(tm)), test_median=float(np.median(tm)),
                      share_test_gt_cal_median=float((tm > cm_).mean()),
                      mannwhitney_p_two_sided=float(mannwhitneyu(tm, cal, alternative="two-sided").pvalue),
                      test_blocks=blocks,
                      alarm_segments_absolute=[int(r + off) for r in alarm_rec[alarm_rec > 0].index],
                      duplicate_row_segment_347_cal_rank_from_top=(int((cal > cal[347 - 300]).sum()) + 1) if s_ == "B" else None)
    R["v2_calibration_vs_test_exchangeability"] = v2

    # ---------- 9d. 구간별 상·하부 진동 상관(길이 17 이상) ----------
    sc_ = {}
    for k in FILES:
        d, sg = frames[k], segs[k]
        r = []
        for _, gg in d.groupby(sg):
            if len(gg) >= 17:
                r.append(np.corrcoef(gg["AI0_Vibration"], gg["AI1_Vibration"])[0, 1])
        r = np.asarray(r)
        sc_[k] = dict(n=int(len(r)), median=float(np.median(r)), negative_share=float((r < 0).mean()), n_negative=int((r < 0).sum()))
    R["segment_corr_AI0_AI1_len_ge17"] = sc_

    # ---------- 9e. 이상 전류 격자 간격 최소제곱 추정(엄격 허용오차 해석) ----------
    xa = a["AI2_Current"].to_numpy(float)
    kk = np.round(xa / 1.1920929)
    mk_ = kk != 0
    g_ls = float(np.sum(xa[mk_] * kk[mk_]) / np.sum(kk[mk_] ** 2))
    grid = {}
    for name, G in (("1.1920929", 1.1920929), ("ls_estimate", g_ls)):
        res = np.abs(xa - np.round(xa / G) * G)
        grid[name] = dict(step=G, value_residual_max=float(res.max()), value_residual_median=float(np.median(res)),
                          grid_unit_tol_1e6_share=float((res / G < 1e-6).mean()))
    grid["max_abs_multiple"] = int(np.abs(kk).max())
    R["abnormal_current_grid_ls"] = grid

    # ---------- 10. 패키지 진단값 대조 ----------
    dj = json.loads(DIAG.read_text(encoding="utf-8"))
    cmp = {}
    for k in FILES:
        s_ = dj["structure"][k]; m_ = struct[k]; sc = schema[k]
        cmp[k] = dict(
            rows=s_["rows"] == sc["rows"], segments=s_["segments"] == m_["segments"],
            len_min=s_["seg_len_min"] == m_["len_min"], len_median=s_["seg_len_median"] == m_["len_median"],
            len_max=s_["seg_len_max"] == m_["len_max"], len_50=s_["segments_len_50"] == m_["len_eq_50"],
            dup_ts=s_["duplicate_timestamps"] == sc["duplicate_timestamp_rows"],
            missing=s_["missing_values"] == sum(sc["nan_after_parse"].values()),
            dt_exact=s_["dt"]["exact_0_1"] == m_["dt_exact_0_1"], dt_zero=s_["dt"]["zero_gap"] == m_["dt_zero"],
            dt_gt=s_["dt"]["gaps_over_0_15s"] == m_["dt_gt_0_15"],
            max_gap=abs(s_["dt"]["max_gap_s"] - m_["gap_s_max"]) < 1e-9,
            elapsed=abs(s_["elapsed_min"] - m_["elapsed_min"]) < 1e-9,
            lag1={c: abs(s_["lag1"][c] - ac[k][c]["raw"]) < 1e-9 for c in SENS},
            decimals={c: (dj["decimals"][k][c]["mode"], dj["decimals"][k][c]["max"]) == (quant[k][c]["dec_mode"], quant[k][c]["dec_max"]) for c in SENS},
            grid_legacy=abs([r for r in dj["format_rules_raw"] if r["rule"] == "current_on_grid"][0][f"{k}_fire_rate"] - quant[k]["current_grid_1_1920929"]["on_grid_tol_1e3"]) < 1e-12,
            wave_n=dj["waveform"][k]["segments_fitted"] == wave[k]["n"],
            wave_r2_median=abs(dj["waveform"][k]["r2_median"] - wave[k]["r2_median"]) < 1e-6,
            wave_f_exact=dj["waveform"][k]["f_exact_0_600"] == wave[k]["f_exact_0_6"],
        )
    R["diagnosis_json_match"] = cmp

    OUT.write_text(json.dumps(jsonable(R), ensure_ascii=False, indent=2), encoding="utf-8")
    flat = json.dumps(jsonable(cmp))
    print("diagnosis_json_match all true:", "false" not in flat)
    print("splits_csv_match:", R["splits_csv_match"])
    print("file identity:", {k: v["all_equal"] for k, v in ident.items()})
    for k in FILES:
        m_ = struct[k]
        print(k, "segments", m_["segments"], "len min/med/max", m_["len_min"], m_["len_median"], m_["len_max"],
              "len50", m_["len_eq_50"], "gap median/max", round(m_["gap_s_median"], 3), m_["gap_s_max"],
              "start-row%50", round(m_["segment_start_rows_multiple_of_50"], 3))
    for s_ in ("A", "B"):
        v = v2[s_]
        print(f"v2 {s_}: cal median {v['cal_median']:.3f} test median {v['test_median']:.3f} "
              f"share test>cal median {v['share_test_gt_cal_median']:.3f} MWU p {v['mannwhitney_p_two_sided']:.2e} "
              f"alarm segs {v['alarm_segments_absolute']}")
    print("segment vib max|z| parts:", {k: (v["n_gt_q95"], v["n"]) for k, v in R["segment_vibration_maxz"]["parts"].items()})
    print("segment corr AI0-AI1:", sc_)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
