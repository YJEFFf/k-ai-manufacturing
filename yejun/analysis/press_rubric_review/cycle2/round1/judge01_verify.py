"""평가관 01(데이터 이해 및 진단) — 2차 순환 1회차 독립 재계산.

원본 CSV(대회 ZIP 멤버와 해시 대조)를 직접 읽어
  (1) 커밋된 진단 산출물(press_submission/outputs/diagnosis.json·splits.csv, analysis/press_evidence/*.csv)의 수치를 다시 계산해 대조하고,
  (2) 이번 회차에서 새로 보는 진단 공백(센서 간 관계, 기록 동기화, 관행적 이상치 기준, 라벨 일관성, 0.6 Hz 해석 조건,
      이상 구간의 시간 추세, 근거 분산도)을 계산한다.
데이터 수준 검사는 패키지 코드를 import하지 않는다(독립 구현). 동결 v2 점수가 필요한 R1·R19 검사만
press_guard.model을 읽기 전용으로 import한다(PYTHONDONTWRITEBYTECODE=1 필수).
결과는 이 폴더의 judge01_verify.json·judge01_verify.log에만 쓴다.

실행(저장소 루트):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      yejun/analysis/press_rubric_review/cycle2/round1/judge01_verify.py
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
RAW_DIR = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "data" / "3_소성가공_예지보전"
ZIP = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "Dataset_소성가공 예지보전 AI 데이터셋.zip"
PKG_DIR = YEJUN / "press_submission" / "data" / "3_소성가공_예지보전"
EVID = YEJUN / "analysis" / "press_evidence"
V1OUT = YEJUN / "press_submission" / "outputs"
GUARD = YEJUN / "press_guard"
FILES = {"normal": "press_data_normal.csv", "abnormal": "outlier_data.csv"}
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
GRID = 1.1920929
SPLITS = {"A": (360, 480), "B": (300, 420)}
FREQS = np.arange(0.0, 5.0001, 0.005)
OUT_JSON = HERE / "judge01_verify.json"
OUT_LOG = HERE / "judge01_verify.log"
LOG: list[str] = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def seg_ids(t: pd.Series, tol: float = 1e-6) -> np.ndarray:
    dt = t.diff().dt.total_seconds()
    return np.cumsum((dt - 0.1).abs().gt(tol).fillna(False).to_numpy())


def decimals(s: pd.Series) -> pd.Series:
    x = s.astype(str).str.strip().str.lstrip("-")
    return x.str.split(".").str[1].fillna("").str.len()


def matched(df: pd.DataFrame) -> pd.DataFrame:
    q = df.copy()
    for c in SENS[:2]:
        q[c] = np.round(q[c] / 1e-4) * 1e-4
    q[SENS[2]] = np.round(q[SENS[2]] / GRID) * GRID
    return q


def lag1(x: np.ndarray, seg: np.ndarray) -> float:
    same = seg[1:] == seg[:-1]
    return float(np.corrcoef(x[:-1][same], x[1:][same])[0, 1])


def demean(x: np.ndarray, seg: np.ndarray) -> np.ndarray:
    return x - pd.Series(x).groupby(seg).transform("mean").to_numpy()


def close(a, b, tol=1e-6) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        if np.isnan(a) and np.isnan(b):
            return True
    except TypeError:
        pass
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


# ---------- 사인 적합(독립 구현): 구간 길이별로 모든 주파수의 투영 행렬을 한 번에 만든다 ----------
def design(L: int, freqs: np.ndarray) -> np.ndarray:
    t = np.arange(L) * 0.1
    w = 2 * np.pi * freqs[:, None] * t[None, :]
    return np.stack([np.sin(w), np.cos(w), np.ones_like(w)], axis=2)  # (F, L, 3)


def sine_fit_group(X: np.ndarray):
    """X: (n_seg, L). 반환: best freq, R², (a,b,c) at best freq, R² at 0.6 Hz."""
    n, L = X.shape
    A = design(L, FREQS)
    P = np.linalg.pinv(A)                     # (F, 3, L)
    beta = np.einsum("fkl,nl->fnk", P, X)     # (F, n, 3)
    fit = np.einsum("flk,fnk->fnl", A, beta)  # (F, n, L)
    sse = ((X[None] - fit) ** 2).sum(2)       # (F, n)
    sst = ((X - X.mean(1, keepdims=True)) ** 2).sum(1)
    k = sse.argmin(0)
    r2 = np.where(sst > 0, 1 - sse[k, np.arange(n)] / np.where(sst > 0, sst, 1), np.nan)
    i06 = int(np.argmin(np.abs(FREQS - 0.6)))
    r2_06 = np.where(sst > 0, 1 - sse[i06] / np.where(sst > 0, sst, 1), np.nan)
    return FREQS[k], r2, beta[k, np.arange(n)], r2_06, beta[i06]


def segment_sine_table(cur: np.ndarray, seg: np.ndarray, min_len: int = 10) -> pd.DataFrame:
    rows = []
    ids, starts, lens = np.unique(seg, return_index=True, return_counts=True)
    by_len: dict[int, list[int]] = {}
    for s, st, L in zip(ids, starts, lens):
        if L >= min_len:
            by_len.setdefault(int(L), []).append(int(st))
    for L, sts in by_len.items():
        X = np.stack([cur[s:s + L] for s in sts])
        f, r2, b, r2_06, b06 = sine_fit_group(X)
        for j, s in enumerate(sts):
            rows.append(dict(start_row=s, segment=int(seg[s]), length=L, f=float(f[j]), r2=float(r2[j]),
                             a=float(b[j, 0]), b=float(b[j, 1]), c=float(b[j, 2]), r2_06=float(r2_06[j]),
                             a06=float(b06[j, 0]), b06=float(b06[j, 1])))
    return pd.DataFrame(rows).sort_values("segment").reset_index(drop=True)


def harmonic_r2(x: np.ndarray, f: float, harmonics: int) -> float:
    t = np.arange(len(x)) * 0.1
    cols = [np.ones_like(t)]
    for h in range(1, harmonics + 1):
        cols += [np.sin(2 * np.pi * h * f * t), np.cos(2 * np.pi * h * f * t)]
    A = np.column_stack(cols)
    beta = np.linalg.lstsq(A, x, rcond=None)[0]
    sse = ((x - A @ beta) ** 2).sum()
    sst = ((x - x.mean()) ** 2).sum()
    return float(1 - sse / sst)


def rayleigh(phases: np.ndarray):
    n = len(phases)
    R = np.abs(np.mean(np.exp(1j * phases)))
    Z = n * R ** 2
    p = np.exp(np.sqrt(1 + 4 * n + 4 * (n ** 2 - (n * R) ** 2)) - (1 + 2 * n))  # Zar(1999) 근사
    return dict(n=n, mean_resultant_length=float(R), Z=float(Z), p=float(min(1.0, p)))


def main():
    t_start = time.monotonic()
    R: dict = {"scope": "평가관 01 2차 순환 1회차 독립 재계산", "head": subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}

    # ===== 0. 원본 동일성 =====
    with zipfile.ZipFile(ZIP) as z:
        zmem = {Path(n).name: z.read(n) for n in z.namelist() if n.endswith(".csv")}
    ev_manifest = json.loads((EVID / "manifest.json").read_text())
    ident = {}
    for k, f in FILES.items():
        a, b = (RAW_DIR / f).read_bytes(), (PKG_DIR / f).read_bytes()
        ident[k] = dict(raw=sha(a), pkg=sha(b), zip=sha(zmem[f]),
                        evidence_manifest=ev_manifest["input_hashes"][k])
        ident[k]["all_equal"] = len({ident[k][x] for x in ("raw", "pkg", "zip", "evidence_manifest")}) == 1
    R["file_identity"] = ident
    log("file identity:", {k: v["all_equal"] for k, v in ident.items()})

    raw = {k: pd.read_csv(io.BytesIO(zmem[f])) for k, f in FILES.items()}
    txt = {k: pd.read_csv(io.BytesIO(zmem[f]), dtype=str, keep_default_na=False) for k, f in FILES.items()}
    n, a = raw["normal"], raw["abnormal"]
    t = {k: pd.to_datetime(f.TimeStamp, format="%Y-%m-%d %H:%M:%S.%f", errors="coerce") for k, f in raw.items()}
    seg = {k: seg_ids(t[k]) for k in raw}

    # ===== 1. 스키마·결측·중복·시각 =====
    schema = {}
    for k, f in raw.items():
        body = f.drop(columns=[f.columns[0]])
        ts_ok = txt[k].TimeStamp.str.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}")
        dt = t[k].diff().dt.total_seconds().to_numpy()[1:]
        schema[k] = dict(
            columns=list(f.columns), rows=len(f), index_is_arange=bool((f.iloc[:, 0].to_numpy() == np.arange(len(f))).all()),
            label_values=sorted(f.Equipment_state.unique().tolist()), missing=int(f.isna().sum().sum()),
            nonfinite=int((~np.isfinite(f[SENS].to_numpy(float))).sum()), ts_parse_fail=int(t[k].isna().sum()),
            ts_ms3_format_share=float(ts_ok.mean()), reverse_steps=int((dt < 0).sum()),
            dup_full_rows_excl_index=int(body.duplicated().sum()), dup_timestamps=int(f.TimeStamp.duplicated().sum()),
            dt_exact_0p1=int((np.abs(dt - 0.1) <= 1e-6).sum()), dt_zero=int((dt == 0).sum()), dt_gt_0p15=int((dt > 0.15).sum()),
            dt_between_0p1_and_1p5=int(((dt > 0.1 + 1e-6) & (dt < 1.5)).sum()),
            weekday=str(t[k].min().day_name()), start=str(t[k].min()), end=str(t[k].max()),
            elapsed_s=float((t[k].max() - t[k].min()).total_seconds()), recorded_s=len(f) * 0.1)
        schema[k]["recorded_share_of_elapsed"] = schema[k]["recorded_s"] / schema[k]["elapsed_s"]
    R["schema"] = schema
    log("schema normal:", {x: schema["normal"][x] for x in ("rows", "missing", "dup_full_rows_excl_index", "dup_timestamps", "reverse_steps", "dt_exact_0p1", "dt_zero", "dt_gt_0p15", "recorded_share_of_elapsed")})
    log("schema abnormal:", {x: schema["abnormal"][x] for x in ("rows", "missing", "dup_full_rows_excl_index", "dup_timestamps", "reverse_steps", "dt_exact_0p1", "dt_zero", "dt_gt_0p15", "recorded_share_of_elapsed")})

    # ===== 2. 기록구간·공백·규칙 허용오차 (R22 대조) =====
    gaps_ev = pd.read_csv(EVID / "gaps.csv").set_index("file")
    tol_ev = pd.read_csv(EVID / "segment_rule_tolerance.csv")
    struct, gap_cmp, tol_cmp = {}, {}, []
    for k in raw:
        s = seg[k]
        lens = pd.Series(s).value_counts()
        dt = t[k].diff().dt.total_seconds().to_numpy()[1:]
        pos = dt[(np.abs(dt - 0.1) > 1e-6) & (dt > 0)]
        starts = t[k].groupby(s).min()
        mine = dict(segments=int(len(lens)), segments_len50=int((lens == 50).sum()), segments_len_gt50=int((lens > 50).sum()),
                    gap_min_s=float(pos.min()), gap_median_s=float(np.median(pos)), gap_max_s=float(pos.max()),
                    gaps_near_0p1_multiple=float(np.mean(np.abs(pos / .1 - np.round(pos / .1)) * .1 < 1e-3)),
                    start_phase_ms_unique=int(len(np.unique((starts.dt.microsecond // 1000) % 100))))
        struct[k] = dict(mine, len_min=int(lens.min()), len_median=float(lens.median()), len_max=int(lens.max()),
                         len1=int((lens == 1).sum()))
        ev = gaps_ev.loc[k]
        gap_cmp[k] = {c: dict(mine=mine[c], evidence=float(ev[c]), ok=close(mine[c], float(ev[c]), 1e-9)) for c in mine}
        for _, r in tol_ev[tol_ev.file.eq(k)].iterrows():
            got = int(seg_ids(t[k], r.tolerance_s).max() + 1)
            tol_cmp.append(dict(file=k, tol=r.tolerance_s, mine=got, evidence=int(r.segments), ok=got == int(r.segments)))
    R["structure"] = struct
    R["gaps_vs_evidence"] = gap_cmp
    R["tolerance_vs_evidence_all_ok"] = all(x["ok"] for x in tol_cmp)
    log("structure:", struct)
    log("gaps vs evidence all ok:", all(v["ok"] for g in gap_cmp.values() for v in g.values()), "tolerance all ok:", R["tolerance_vs_evidence_all_ok"])

    # ===== 3. 변수 사전 사실 + 가이드북 표 2·3 대조 (R2) =====
    guide = {"normal": {"AI0_Vibration": (-0.000094, 0.070634, -0.314570, -0.000172, 0.351699),
                        "AI1_Vibration": (-0.000093, 0.118888, -0.366498, -0.009317, 0.399782),
                        "AI2_Current": (1.446209, 122.664494, -271.568330, 1.849830, 273.235000)},
             "abnormal": {"AI0_Vibration": (0.007578, 0.447928, -1.502735, 0.015771, 1.803204),
                          "AI1_Vibration": (-0.008137, 0.241226, -0.751253, 0.002161, 0.509321),
                          "AI2_Current": (57.329741, 153.172619, -399.351170, 53.644187, 538.826050)}}
    gb = {}
    for k, f in raw.items():
        for c in SENS:
            x = f[c].to_numpy(float)
            mine = (x.mean(), x.std(ddof=1), x.min(), np.median(x), x.max())
            gb[f"{k}.{c}"] = dict(mine=[round(v, 6) for v in mine], guidebook=list(guide[k][c]),
                                  ok=all(abs(m - g) <= 1.5e-6 for m, g in zip(mine, guide[k][c])))
    R["guidebook_table2_3_match"] = gb
    dec = {k: {c: int(decimals(txt[k][c]).mode()[0]) for c in SENS} for k in raw}
    R["variable_facts"] = dict(decimal_mode=dec, current_negative_share_normal=float((n.AI2_Current < 0).mean()),
                               current_negative_share_abnormal=float((a.AI2_Current < 0).mean()),
                               guidebook_table_all_match=all(v["ok"] for v in gb.values()))
    log("guidebook table 2/3 all match:", R["variable_facts"]["guidebook_table_all_match"], "decimals:", dec,
        "cur neg share normal:", round(R["variable_facts"]["current_negative_share_normal"], 4))

    # ===== 4. 불균형 (R3) =====
    sn = seg["normal"]
    imb_ev = pd.read_csv(EVID / "imbalance.csv").set_index("scope")
    imb = {}
    for sid, (tr, ca) in SPLITS.items():
        test = sn >= ca
        nr = int(test.sum())
        prev = 600 / (600 + nr)
        imb[sid] = dict(test_rows=nr, test_segments=int(len(np.unique(sn[test]))), abnormal_row_share=prev,
                        all_positive_f1=2 * prev / (1 + prev),
                        evidence_all_positive_f1=float(imb_ev.loc[f"{sid} 평가", "all_positive_row_f1"]))
        imb[sid]["ok"] = close(imb[sid]["all_positive_f1"], imb[sid]["evidence_all_positive_f1"], 1e-12)
    splits_csv = pd.read_csv(V1OUT / "splits.csv")
    sp_ok = []
    for sid, (tr, ca) in SPLITS.items():
        for part, m in (("train", sn < tr), ("cal", (sn >= tr) & (sn < ca)), ("test", sn >= ca)):
            r = splits_csv[(splits_csv.split_id == sid) & (splits_csv.part == part)].iloc[0]
            sp_ok.append(int(r.rows) == int(m.sum()) and int(r.segments) == len(np.unique(sn[m])))
    R["imbalance"] = imb
    R["splits_csv_match"] = all(sp_ok)
    log("imbalance:", {s: (v["test_rows"], round(v["all_positive_f1"], 4), v["ok"]) for s, v in imb.items()}, "splits.csv match:", all(sp_ok))

    # ===== 5. 이상치 (R3) + 관행 기준(IQR·3σ) 비교 =====
    trA = sn < 360
    out_ev = pd.read_csv(EVID / "outliers.csv").set_index("sensor")
    outl, any_out, vib_out = {}, np.zeros(len(a), bool), np.zeros(len(a), bool)
    for c in SENS:
        x, y = n[c].to_numpy(float), a[c].to_numpy(float)
        med = np.median(x[trA]); mad = 1.4826 * np.median(np.abs(x[trA] - med))
        lo, hi = x[trA].min(), x[trA].max()
        q1, q3 = np.percentile(x[trA], [25, 75]); iqr = q3 - q1
        mu, sd = x[trA].mean(), x[trA].std(ddof=1)
        o = (y < lo) | (y > hi)
        any_out |= o
        if c != SENS[2]:
            vib_out |= o
        outl[c] = dict(normal_robust_z_max=float(np.abs((x - med) / mad).max()),
                       abnormal_rows_outside_trainA=int(o.sum()), normal_nontrain_outside_trainA=int(((x < lo) | (x > hi))[~trA].sum()),
                       iqr15_normal_nontrain_rows=int(((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr))[~trA].sum()),
                       iqr15_normal_nontrain_share=float(((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr))[~trA].mean()),
                       iqr15_abnormal_rows=int(((y < q1 - 1.5 * iqr) | (y > q3 + 1.5 * iqr)).sum()),
                       sigma3_normal_nontrain_rows=int((np.abs(x - mu) > 3 * sd)[~trA].sum()),
                       sigma3_abnormal_rows=int((np.abs(y - mu) > 3 * sd).sum()))
        outl[c]["evidence_ok"] = (close(outl[c]["normal_robust_z_max"], float(out_ev.loc[c, "normal_robust_z_max"]), 1e-9)
                                  and outl[c]["abnormal_rows_outside_trainA"] == int(out_ev.loc[c, "abnormal_rows_outside_trainA_range"]))
    sa = seg["abnormal"]
    outl["any"] = dict(abnormal_rows_outside=int(any_out.sum()), segments=int(len(np.unique(sa[any_out]))),
                       segments_vib=int(len(np.unique(sa[vib_out]))))
    # 관행 기준으로 '이상치 제거'를 하면 어떻게 되나: 두 센서 이상 IQR 규칙으로 행을 지우면 이상 행의 몇 %가 사라지나
    iqr_any_ab = np.zeros(len(a), bool); iqr_any_nn = np.zeros((~trA).sum(), bool)
    for c in SENS[:2]:
        x, y = n[c].to_numpy(float), a[c].to_numpy(float)
        q1, q3 = np.percentile(x[trA], [25, 75]); iqr = q3 - q1
        iqr_any_ab |= (y < q1 - 1.5 * iqr) | (y > q3 + 1.5 * iqr)
        iqr_any_nn |= ((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr))[~trA]
    outl["iqr15_vibration_removal"] = dict(abnormal_rows_removed=int(iqr_any_ab.sum()), abnormal_share=float(iqr_any_ab.mean()),
                                           normal_nontrain_rows_removed=int(iqr_any_nn.sum()), normal_nontrain_share=float(iqr_any_nn.mean()))
    R["outliers"] = outl
    log("outliers:", {c: (round(v["normal_robust_z_max"], 3), v["abnormal_rows_outside_trainA"], v["iqr15_normal_nontrain_rows"], v["iqr15_abnormal_rows"], v["evidence_ok"]) for c, v in outl.items() if c in SENS})
    log("outliers any:", outl["any"], "IQR vib removal:", outl["iqr15_vibration_removal"])

    # ===== 6. 가이드북 품질 지수 (R3) =====
    qi = {}
    for k, f in raw.items():
        body = f.drop(columns=[f.columns[0]])
        vc = body.value_counts()
        uniq = (len(vc) - int((vc > 1).sum())) / len(vc) * 100
        qi[k] = dict(uniqueness=uniq, uniqueness_round2=round(uniq, 2))
    # 가이드북 표 1(정상)의 가중 합계 96.66%: 완전성 60%, 유일성·유효성·일관성·무결성 각 10%
    qi["normal"]["weighted_total_guidebook_formula"] = 0.6 * 100 + 0.1 * (round(qi["normal"]["uniqueness"], 2) + 100 + 100 + 66.67)
    R["quality_index"] = qi
    qev = pd.read_csv(EVID / "quality_index.csv")
    R["quality_index_evidence_has_weighted_total"] = bool(qev["index"].str.contains("weight|total|가중", regex=True).any())
    log("quality:", qi, "evidence has weighted total row:", R["quality_index_evidence_has_weighted_total"])

    # ===== 7. 클래스 차이 (R4) =====
    q = {k: matched(f) for k, f in raw.items()}
    cd = {}
    for k in raw:
        s = seg[k]
        lens = pd.Series(s).value_counts()
        long17 = np.isin(s, lens[lens >= 17].index)
        cors = [np.corrcoef(g.AI0_Vibration, g.AI1_Vibration)[0, 1] for _, g in q[k].groupby(s) if len(g) >= 17]
        cur = q[k].AI2_Current.to_numpy(float)
        cd[k] = dict(lag1_AI0=lag1(q[k].AI0_Vibration.to_numpy(float), s), lag1_AI1=lag1(q[k].AI1_Vibration.to_numpy(float), s),
                     lag1_AI2=lag1(cur, s),
                     lag1_AI0_demeaned=lag1(demean(q[k].AI0_Vibration.to_numpy(float), s), s),
                     corr_pooled=float(np.corrcoef(q[k].AI0_Vibration, q[k].AI1_Vibration)[0, 1]),
                     corr_seg_median=float(np.median(cors)), corr_seg_negative=f"{int((np.asarray(cors) < 0).sum())}/{len(cors)}",
                     current_seg_mean_median_len17=float(pd.Series(cur).groupby(s).mean()[lens[lens >= 17].index].median()),
                     sd_AI0=float(raw[k].AI0_Vibration.std()), sd_AI1=float(raw[k].AI1_Vibration.std()))
    cd["pure_sine_0p6_lag1"] = float(np.cos(2 * np.pi * 0.6 * 0.1))
    cdev = pd.read_csv(EVID / "class_differences.csv").set_index("feature")
    cd["evidence_ok"] = dict(
        lag1_AI0=close(round(cd["normal"]["lag1_AI0"], 3), float(cdev.loc["AI0 lag-1(구간 안, matched)", "normal"]), 1e-9)
        and close(round(cd["abnormal"]["lag1_AI0"], 3), float(cdev.loc["AI0 lag-1(구간 안, matched)", "abnormal"]), 1e-9),
        corr=close(round(cd["normal"]["corr_pooled"], 3), float(cdev.loc["상·하부 진동 상관(합동)", "normal"]), 1e-9)
        and close(round(cd["abnormal"]["corr_pooled"], 3), float(cdev.loc["상·하부 진동 상관(합동)", "abnormal"]), 1e-9),
        cur_mean=close(round(cd["normal"]["current_seg_mean_median_len17"], 2), float(cdev.loc["전류 구간 평균 중앙값(길이≥17)", "normal"]), 1e-9)
        and close(round(cd["abnormal"]["current_seg_mean_median_len17"], 2), float(cdev.loc["전류 구간 평균 중앙값(길이≥17)", "abnormal"]), 1e-9))
    # 7b. 저장 형식 규칙(누설 경로): 원값과 matched에서 발화율
    fmt = {}
    for k in raw:
        for name, fr in (("raw", raw[k]), ("matched", q[k])):
            v = fr[SENS[:2]].to_numpy(float)
            finer = (np.abs(v * 1e6 - np.round(v * 1e6)) > 1e-3).any(axis=1)
            c = fr[SENS[2]].to_numpy(float)
            grid = np.abs(c / GRID - np.round(c / GRID)) < 1e-3
            fmt[f"{k}.{name}"] = dict(vib_finer_than_1e6=float(finer.mean()), current_on_grid=float(grid.mean()))
    cd["format_rules"] = fmt
    R["class_differences"] = cd
    log("format rules:", fmt)
    log("class diff:", {k: {x: (round(v, 4) if isinstance(v, float) else v) for x, v in cd[k].items()} for k in ("normal", "abnormal")}, "evidence ok:", cd["evidence_ok"])

    # ===== 8. 전류 사인 적합(독립) + 0.6 Hz 해석 조건 + 기록 동기화 =====
    sine = {k: segment_sine_table(raw[k].AI2_Current.to_numpy(float), seg[k]) for k in raw}
    wf = {}
    for k, tb in sine.items():
        wf[k] = dict(fitted=len(tb), r2_min=float(tb.r2.min()), r2_median=float(tb.r2.median()), r2_max=float(tb.r2.max()),
                     f_median=float(tb.f.median()), f_exact_0p6=int(np.isclose(tb.f, 0.6).sum()),
                     f_q05=float(tb.f.quantile(.05)), f_q95=float(tb.f.quantile(.95)))
    dj = json.loads((V1OUT / "diagnosis.json").read_text())["waveform"]
    wf["diagnosis_json_ok"] = all(close(wf[k][c], dj[k][m], 1e-9) for k in raw for c, m in
                                  (("fitted", "segments_fitted"), ("r2_min", "r2_min"), ("r2_median", "r2_median"), ("r2_max", "r2_max"), ("f_exact_0p6", "f_exact_0_600")))
    # (a) 앨리어싱 조건: 60 Hz가 0.6 Hz로 보이려면 표본화 주기가 1% 달라야 한다(또는 원 신호가 59.4/60.6 Hz)
    wf["alias_condition"] = dict(fs_needed_hz=[60 / 6.06, 60 / 5.94], dt_needed_s=[6.06 / 60, 5.94 / 60],
                                 drift_per_50_rows_ms=[(6.06 / 60 - 0.1) * 49 * 1e3, (5.94 / 60 - 0.1) * 49 * 1e3],
                                 timestamps_within_segment_all_exact_0p1=schema["normal"]["dt_exact_0p1"] + schema["abnormal"]["dt_exact_0p1"] == 19400 + 579)
    # (b) 고조파: 정상 50행 구간에서 기본파 대비 2·3차 고조파가 설명하는 추가 분산
    tb = sine["normal"]
    full = tb[(tb.length == 50) & np.isclose(tb.f, 0.6)]
    cur_n = n.AI2_Current.to_numpy(float)
    h1 = np.array([harmonic_r2(cur_n[s:s + 50], 0.6, 1) for s in full.start_row])
    h3 = np.array([harmonic_r2(cur_n[s:s + 50], 0.6, 3) for s in full.start_row])
    wf["harmonics_len50_f0p6"] = dict(segments=len(full), r2_fund_median=float(np.median(h1)), r2_h3_median=float(np.median(h3)),
                                      gain_median=float(np.median(h3 - h1)), gain_q95=float(np.quantile(h3 - h1, .95)))
    # (c) 진폭 변조: 같은 0.6 Hz로 앞 25행·뒤 25행 진폭 비
    ratios = []
    for s in full.start_row:
        amps = []
        for off in (0, 25):
            x = cur_n[s + off:s + off + 25]
            A = design(25, np.array([0.6]))[0]
            b = np.linalg.lstsq(A, x, rcond=None)[0]
            amps.append(np.hypot(b[0], b[1]))
        ratios.append(amps[1] / amps[0])
    ratios = np.asarray(ratios)
    wf["amplitude_half_ratio_len50"] = dict(median=float(np.median(ratios)), q05=float(np.quantile(ratios, .05)), q95=float(np.quantile(ratios, .95)))
    # (d) 기록 시작 위상: 0.6 Hz 사인의 구간 시작 위상이 한쪽에 몰리면 신호 주기에 맞춘 트리거 수집이다
    sel = tb[np.isclose(tb.f, 0.6)]
    phases = np.arctan2(sel.b.to_numpy(), sel.a.to_numpy())
    wf["start_phase_rayleigh_normal"] = rayleigh(phases)
    R["waveform"] = wf
    log("waveform:", {k: wf[k] for k in raw}, "diagnosis.json ok:", wf["diagnosis_json_ok"])
    log("alias condition:", wf["alias_condition"])
    log("harmonics:", wf["harmonics_len50_f0p6"], "amp half ratio:", wf["amplitude_half_ratio_len50"], "start phase:", wf["start_phase_rayleigh_normal"])

    # (e) 기록구간 안 위치별 진동 크기: 사건(타격) 트리거 수집이면 특정 위치에 진동이 몰린다
    pos_n = pd.Series(sn).groupby(sn).cumcount().to_numpy()
    zA = np.abs((n[SENS[:2]].to_numpy(float) - n[SENS[:2]][trA].mean().to_numpy()) / n[SENS[:2]][trA].std(ddof=0).to_numpy()).max(1)
    bins = pos_n // 5
    grp = [zA[bins == b] for b in range(10)]
    kw = stats.kruskal(*grp)
    prof = [float(np.mean(g)) for g in grp]
    R["position_profile_normal"] = dict(mean_vib_maxz_by_5row_bin=prof, max_over_min=float(max(prof) / min(prof)), kruskal_p=float(kw.pvalue))
    log("position profile (normal vib max|z| by 5-row bin):", [round(p, 3) for p in prof], "KW p:", kw.pvalue)

    # ===== 9. 센서 간 관계(설비 관계): 원값·절댓값 상관, 구간 단위 진동–전류 관계, 시간 추세 =====
    rel = {}
    for k, f in raw.items():
        rel[k] = dict(raw_corr=f[SENS].corr().round(4).to_dict(), abs_corr=f[SENS].abs().corr().round(4).to_dict())
    feats = {}
    for k, f in raw.items():
        s = seg[k]
        g = pd.DataFrame(dict(seg=s, AI0=f.AI0_Vibration, AI1=f.AI1_Vibration, cur=f.AI2_Current))
        agg = g.groupby("seg").agg(n=("AI0", "size"), sd0=("AI0", "std"), sd1=("AI1", "std"),
                                   cur_rms=("cur", lambda x: float(np.sqrt(np.mean((x - x.mean()) ** 2)))))
        feats[k] = agg[agg.n >= 17].copy()
    fn = feats["normal"]
    rel["normal_segment_spearman"] = dict(
        sd0_vs_cur=float(stats.spearmanr(fn.sd0, fn.cur_rms)[0]), sd1_vs_cur=float(stats.spearmanr(fn.sd1, fn.cur_rms)[0]),
        sd0_vs_sd1=float(stats.spearmanr(fn.sd0, fn.sd1)[0]), segments=len(fn),
        sd0_vs_time=float(stats.spearmanr(fn.index, fn.sd0)[0]), cur_vs_time=float(stats.spearmanr(fn.index, fn.cur_rms)[0]))
    fa = feats["abnormal"]
    rel["abnormal_segment_spearman"] = dict(sd0_vs_cur=float(stats.spearmanr(fa.sd0, fa.cur_rms)[0]), segments=len(fa),
                                            sd0_vs_time=float(stats.spearmanr(fa.index, fa.sd0)[0]),
                                            cur_vs_time=float(stats.spearmanr(fa.index, fa.cur_rms)[0]),
                                            sd0_vs_time_p=float(stats.spearmanr(fa.index, fa.sd0)[1]))
    rel["abnormal_segment_spearman"]["sd1_vs_cur"] = float(stats.spearmanr(fa.sd1, fa.cur_rms)[0])
    # 문서화 여부: v1 진폭 정규화 후보의 메타(행 단위 trailing-17 상관)만 있고 진단 표에는 없다
    ln = pd.read_csv(V1OUT / "load_normalization_meta.csv")
    rel["v1_load_normalization_meta_amp_vib_corr"] = ln.amp_vib_corr_trainA.round(3).tolist()
    ev_text = " ".join((EVID / p).read_text() for p in ("README.md", "class_differences.csv", "variable_dictionary.csv"))
    rel["evidence_mentions_vib_current_relation"] = bool(re.search(r"진동.{0,12}전류.{0,12}(상관|함께|결합)|전류.{0,12}진동.{0,12}(상관|함께|결합)", ev_text))
    R["sensor_relations"] = rel
    log("raw corr normal:", rel["normal"]["raw_corr"], "\nabs corr normal:", rel["normal"]["abs_corr"])
    log("raw corr abnormal:", rel["abnormal"]["raw_corr"], "\nabs corr abnormal:", rel["abnormal"]["abs_corr"])
    log("segment relations:", rel["normal_segment_spearman"], rel["abnormal_segment_spearman"],
        "v1 loadnorm meta corr:", rel["v1_load_normalization_meta_amp_vib_corr"], "evidence mentions relation:", rel["evidence_mentions_vib_current_relation"])

    # 9b. dayshift §3·§4 전류 수준 수치 재계산(길이≥17 구간 RMS 중앙값 비, 10분 블록 상대 범위)
    lvl = {}
    for k, f in raw.items():
        s = seg[k]
        g = pd.DataFrame(dict(seg=s, cur=f.AI2_Current.to_numpy(float), t=t[k]))
        agg = g.groupby("seg").agg(n=("cur", "size"), rms=("cur", lambda x: float(np.sqrt(np.mean(x ** 2)))), start=("t", "min"))
        lvl[k] = agg
    nr = lvl["normal"][lvl["normal"].n >= 17]; ar = lvl["abnormal"][lvl["abnormal"].n >= 17]
    ratio = float(ar.rms.median() / nr.rms.median())
    blk = nr.groupby(nr.start.dt.floor("10min")).rms.median() / nr.rms.median()
    R["dayshift_levels"] = dict(c1_ratio=ratio, block10_rel_min=float(blk.min()), block10_rel_max=float(blk.max()),
                                ok=close(ratio, 1.302098629578778, 1e-9) and close(float(blk.min()), 0.8540295359656999, 1e-9) and close(float(blk.max()), 1.2940379150315584, 1e-9))
    log("dayshift levels:", R["dayshift_levels"])

    # ===== 10. 라벨 일관성: 이상 21구간 중 정상 범위 안에 드는 구간이 있는가 =====
    sc = n[SENS[:2]][trA]
    mu0, sd0_ = sc.mean().to_numpy(), sc.std(ddof=0).to_numpy()
    def seg_vmax(f, s):
        z = np.abs((f[SENS[:2]].to_numpy(float) - mu0) / sd0_).max(1)
        return pd.Series(z).groupby(s).max()
    vmax_n = seg_vmax(n, sn); vmax_a = seg_vmax(a, sa)
    ntest = vmax_n[vmax_n.index >= 360]
    thr_v = float(ntest.quantile(.99)); r2_min_normal = float(sine["normal"].r2.min())
    ta = sine["abnormal"].set_index("segment")
    rows = []
    for s_ in range(21):
        r2 = float(ta.r2.get(s_, np.nan))
        rows.append(dict(segment=s_, length=int((sa == s_).sum()), vib_segmax_z=float(vmax_a[s_]), r2=r2,
                         vib_out=bool(vmax_a[s_] > thr_v), r2_out=bool(np.isfinite(r2) and r2 < r2_min_normal)))
    lab = pd.DataFrame(rows)
    R["label_consistency"] = dict(vib_thr_normal_nontrainA_q99=thr_v, r2_min_normal=r2_min_normal,
                                  segments_out_on_any=int((lab.vib_out | lab.r2_out).sum()),
                                  segments_vib_out=int(lab.vib_out.sum()), segments_r2_out=int(lab.r2_out.sum()),
                                  short_unfittable=lab[~np.isfinite(lab.r2)][["segment", "length", "vib_segmax_z", "vib_out"]].to_dict("records"),
                                  low_vibration=lab[~lab.vib_out][["segment", "length", "vib_segmax_z", "r2"]].to_dict("records"),
                                  normal_looking_segments=lab[~(lab.vib_out | lab.r2_out)].to_dict("records"))
    log("label consistency:", {k: v for k, v in R["label_consistency"].items() if k != "normal_looking_segments"}, "normal-looking:", R["label_consistency"]["normal_looking_segments"])

    # ===== 11. R1 분할 맥락(데이터 수준 독립 + 동결 v2 점수) =====
    sys.path.insert(0, str(GUARD))
    from model import GuardModel, layout  # noqa: E402  (읽기 전용 사용)
    sys.path.insert(0, str(YEJUN / "press_submission"))
    from press.calibrate import segment_max, conformal_p  # noqa: E402
    ctx_ev = pd.read_csv(EVID / "split_context.csv").set_index(["split", "part"])
    cur_dm = demean(n.AI2_Current.to_numpy(float), sn)
    ctx = {}
    for sid, (tr, ca) in SPLITS.items():
        m = GuardModel.load(GUARD / "artifacts" / f"guard_{sid}.json")
        cal_med = float(np.median(m.cal))
        for part, mask in (("cal", (sn >= tr) & (sn < ca)), ("test", sn >= ca)):
            fr = n[mask].reset_index(drop=True)
            qq = matched(fr[["TimeStamp"] + SENS])
            sg = layout(qq)[1]
            smax = segment_max(m.components(qq, sg)["score"], sg)
            d = dict(AI0_sd=float(n.AI0_Vibration[mask].std()), AI1_sd=float(n.AI1_Vibration[mask].std()),
                     cur_rms_dm=float(np.sqrt(np.mean(cur_dm[mask] ** 2))), n=len(smax),
                     gt_cal_median=int((smax > cal_med).sum()), share=float((smax > cal_med).mean()))
            if part == "test":
                d["mwu_p"] = float(stats.mannwhitneyu(smax, m.cal).pvalue)
                p = conformal_p(m.cal, m.components(qq, sg)["score"])
                recmin = pd.Series(p).groupby(sg).min()
                d["alerts_by_k"] = {kk: int((recmin <= kk / 121 + 1e-12).sum()) for kk in range(1, 7)}
                d["alert_segments_k1"] = [int(i) + ca for i in recmin.index[recmin <= 1 / 121 + 1e-12]]
            ev = ctx_ev.loc[(sid, part)]
            d["evidence_ok"] = (close(d["AI0_sd"], ev.AI0_sd, 1e-9) and close(d["cur_rms_dm"], ev.current_rms_demeaned, 1e-9)
                                and close(d["share"], ev.share_gt_cal_median, 1e-12))
            ctx[f"{sid}_{part}"] = d
    # B 오경보 구간의 운전 수준(정상 전체 구간 대비 백분위): 운전변화와 오경보의 연결
    fall = pd.DataFrame(dict(seg=sn, AI0=n.AI0_Vibration, AI1=n.AI1_Vibration, cur=cur_dm)).groupby("seg").agg(
        n=("AI0", "size"), sd0=("AI0", "std"), sd1=("AI1", "std"), cur_rms=("cur", lambda x: float(np.sqrt(np.mean(x ** 2)))))
    ctx["B_false_alarm_levels"] = [dict(segment=int(s_), length=int(fall.loc[s_, "n"]),
                                        sd0_pct=float((fall.sd0 < fall.loc[s_, "sd0"]).mean()), sd1_pct=float((fall.sd1 < fall.loc[s_, "sd1"]).mean()),
                                        cur_rms_pct=float((fall.cur_rms < fall.loc[s_, "cur_rms"]).mean()))
                                   for s_ in ctx["B_test"]["alert_segments_k1"]]
    log("B false alarm levels (percentile among 600 normal segments):", ctx["B_false_alarm_levels"])
    cc = pd.read_csv(EVID / "calibration_curve.csv")
    ctx["calibration_curve_ok"] = all(int(cc[(cc.split == sid) & (cc.k == kk)].alerted_records.iloc[0]) == ctx[f"{sid}_test"]["alerts_by_k"][kk]
                                      for sid in SPLITS for kk in range(1, 7))
    # 60구간 블록
    blocks = {}
    for b in range(10):
        mk = (sn >= 60 * b) & (sn < 60 * b + 60)
        blocks[f"{60 * b}-{60 * b + 59}"] = dict(AI0_sd=round(float(n.AI0_Vibration[mk].std()), 4), AI1_sd=round(float(n.AI1_Vibration[mk].std()), 4),
                                                 cur_rms_dm=round(float(np.sqrt(np.mean(cur_dm[mk] ** 2))), 1))
    ctx["blocks"] = blocks
    R["split_context"] = ctx
    log("split context:", {k: v for k, v in ctx.items() if k != "blocks"})
    log("blocks:", blocks)

    # ===== 12. 문서 간 수치 일치(R1 인용 수치) =====
    readme = (GUARD / "README.md").read_text()
    supp = (YEJUN / "analysis" / "press_supplement" / "README.md").read_text()
    evr = (EVID / "README.md").read_text()
    R["doc_consistency"] = dict(
        guard_readme_12_of_120=("12/120" in readme) and ctx["A_test"]["gt_cal_median"] == 12,
        guard_readme_50_of_180=("50/180" in readme) and ctx["B_test"]["gt_cal_median"] == 50,
        supplement_12_of_120=("12/120" in supp), evidence_10pct=("**10%**" in evr) and round(ctx["A_test"]["share"], 3) == 0.1,
        B_false_alarm_segments=ctx["B_test"]["alert_segments_k1"])
    log("doc consistency:", R["doc_consistency"])

    # ===== 12b. 가이드북 전처리·분할과 기록 구조의 충돌(정량) =====
    pos_all = pd.Series(sn).groupby(sn).cumcount().to_numpy()
    idx = np.arange(len(n) - 121)
    lstm_note = json.loads((V1OUT / "lstm_guidebook_reproduction.json").read_text()).get("notes", "")
    tt = t["normal"].to_numpy()
    lead_s = (tt[idx + 120] - tt[idx + 19]) / np.timedelta64(1, "s")   # 가이드북: 입력 끝(index+19) → 라벨 행(index+120)
    R["guidebook_protocol_vs_records"] = dict(
        split_row_15000_segment=int(sn[15000]), split_row_15000_position=int(pos_all[15000]), split_row_15000_time=str(t["normal"][15000]),
        input20_windows_crossing_gap_share=float(((sn[idx + 19] - sn[idx]) > 0).mean()),
        label_row_in_other_record_share=float(((sn[idx + 120] - sn[idx + 19]) > 0).mean()),
        median_records_spanned_input_to_label=float(np.median(sn[idx + 120] - sn[idx]) + 1),
        nominal_lead_s=10.1, actual_lead_s_median=float(np.median(lead_s)), actual_lead_s_q05=float(np.quantile(lead_s, .05)),
        actual_lead_s_q95=float(np.quantile(lead_s, .95)),
        team_note_mentions_gap_crossing=("가로지" in lstm_note), team_note_quantified=bool(re.search(r"\d+(\.\d+)?\s*%", lstm_note)))
    log("guidebook protocol vs records:", R["guidebook_protocol_vs_records"])

    # ===== 12c. 주최 측 문의로 남은 문구 =====
    plan = (YEJUN / "press_submission" / "PLAN.md").read_text().splitlines()
    R["pending_inquiry_lines"] = [dict(file="press_submission/PLAN.md", line=i + 1, text=l[:120]) for i, l in enumerate(plan) if "문의 초안" in l]
    log("pending inquiry lines:", R["pending_inquiry_lines"])

    # ===== 13. v1 diagnosis.md 원표의 엄격 격자 행(R21 잔여) =====
    diag_md = (V1OUT / "diagnosis.md").read_text().splitlines()
    strict = [i + 1 for i, l in enumerate(diag_md) if "current_on_grid_strict | raw" in l]
    R["diagnosis_md_strict_row"] = dict(lines=strict, annotated=any("판별 의미" in l or "유효숫자" in l for l in diag_md))
    log("diagnosis.md strict row:", R["diagnosis_md_strict_row"])

    # ===== 14. 진단 그림·근거 분산도 =====
    figs = {}
    for d in ("press_submission/outputs", "press_guard/outputs", "analysis/press_evidence", "analysis/press_dayshift", "analysis/press_supplement"):
        figs[d] = sorted(p.name for p in (YEJUN / d).glob("*.png"))
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "yejun/analysis/press_evidence"], capture_output=True, text=True).stdout.split()
    R["figures"] = figs
    R["evidence_tracked_files"] = len(tracked)
    R["evidence_csv_count"] = sum(1 for x in tracked if x.endswith(".csv"))
    log("figures:", figs, "evidence tracked files:", len(tracked), "csv:", R["evidence_csv_count"])

    # ===== 15. 검증전략: 무작위 행 분할의 형식 지름길(press_supervised, dcd300a) 독립 재현 =====
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    y = np.r_[np.zeros(len(n)), np.ones(len(a))]
    d0 = np.r_[decimals(txt["normal"].AI0_Vibration).to_numpy(), decimals(txt["abnormal"].AI0_Vibration).to_numpy()]
    rule = d0 >= 7
    tp, fp, fn_ = int((rule & (y == 1)).sum()), int((rule & (y == 0)).sum()), int((~rule & (y == 1)).sum())
    Xtr, Xte, ytr, yte = train_test_split(pd.DataFrame({"d0": d0}), y, test_size=.3, stratify=y, random_state=0)
    pr = HistGradientBoostingClassifier(random_state=0).fit(Xtr, ytr).predict_proba(Xte)[:, 1] >= .5
    tp2, fp2, fn2 = int((pr & (yte == 1)).sum()), int((pr & (yte == 0)).sum()), int((~pr & (yte == 1)).sum())
    sup = pd.read_csv(YEJUN / "analysis" / "press_supervised" / "random_rows.csv")
    ref = sup[sup.features.eq("소수 자릿수(AI0 하나)")].iloc[0]
    R["format_shortcut_random_split"] = dict(
        rule_decimals_ge7_all_rows=dict(tp=tp, fp=fp, fn=fn_, f1=2 * tp / (2 * tp + fp + fn_)),
        hgb_same_split=dict(tp=tp2, fp=fp2, fn=fn2, f1=2 * tp2 / (2 * tp2 + fp2 + fn2)),
        committed=dict(tp=int(ref.tp), fp=int(ref.fp), fn=int(ref.fn), f1=float(ref.f1)),
        ok=(tp2, fp2, fn2) == (int(ref.tp), int(ref.fp), int(ref.fn)))
    log("format shortcut (random row split):", R["format_shortcut_random_split"])

    R["elapsed_s"] = time.monotonic() - t_start
    OUT_JSON.write_text(json.dumps(jsonable(R), ensure_ascii=False, indent=2))
    LOG.append(f"wrote {OUT_JSON.name} ({R['elapsed_s']:.1f}s)")
    OUT_LOG.write_text("\n".join(LOG) + "\n")
    print(LOG[-1])


if __name__ == "__main__":
    main()
