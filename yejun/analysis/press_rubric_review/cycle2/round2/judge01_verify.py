"""평가관 01(데이터 이해 및 진단) — 사이클2 2회차 독립 재계산.

기준 커밋 e9ed90f. 대회 ZIP 멤버를 직접 읽어
  (A) 1회차 보완 목록 D1~D7의 새 산출물(analysis/press_evidence의 사이클2 표 16개·README·그림)을 다시 계산해 대조하고,
  (B) 결정표의 `파일:행` 인용과 인용 수치를 원천 파일과 대조하고,
  (C) 2회차에서 새로 보는 진단 공백(정상 운전 상태의 구조와 분할별 구성)을 계산한다.
데이터 수준 검사는 패키지 코드를 import하지 않는다(독립 구현). 동결 모델 점수와 시간순 5겹 재적합이 필요한 검사만
press_guard.model을 읽기 전용으로 import한다(PYTHONDONTWRITEBYTECODE=1 필수). 결과는 이 폴더의 judge01_verify.json·.log에만 쓴다.

실행(저장소 루트):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      yejun/analysis/press_rubric_review/cycle2/round2/judge01_verify.py
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

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
ZIP = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "Dataset_소성가공 예지보전 AI 데이터셋.zip"
RAW_DIR = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "data" / "3_소성가공_예지보전"
PKG_DIR = YEJUN / "press_submission" / "data" / "3_소성가공_예지보전"
EVID = YEJUN / "analysis" / "press_evidence"
V1 = YEJUN / "press_submission"
V1OUT = V1 / "outputs"
GUARD = YEJUN / "press_guard"
SUPP = YEJUN / "analysis" / "press_supplement"
SUPV = YEJUN / "analysis" / "press_supervised"
FILES = {"normal": "press_data_normal.csv", "abnormal": "outlier_data.csv"}
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
VIB = SENS[:2]
SPLITS = {"A": (360, 480), "B": (300, 420)}
FREQS = np.arange(0.0, 5.0001, 0.005)
OUT_JSON = HERE / "judge01_verify.json"
OUT_LOG = HERE / "judge01_verify.log"
LOG: list[str] = []
CHECKS: list[dict] = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    print(s)


def check(name, ok, detail=""):
    CHECKS.append(dict(name=name, ok=bool(ok), detail=str(detail)[:400]))
    if not ok:
        log(f"  [불일치] {name}: {detail}")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    return sha(Path(p).read_bytes())


def close(a, b, tol=1e-9):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    if np.isnan(a) and np.isnan(b):
        return True
    return abs(a - b) <= tol * max(1.0, abs(b))


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def seg_ids(t: pd.Series, tol: float = 1e-6) -> np.ndarray:
    dt = t.diff().dt.total_seconds()
    return np.cumsum((dt - 0.1).abs().gt(tol).fillna(False).to_numpy())


def design(L: int, freqs: np.ndarray) -> np.ndarray:
    tt = np.arange(L) * 0.1
    w = 2 * np.pi * freqs[:, None] * tt[None, :]
    return np.stack([np.sin(w), np.cos(w), np.ones_like(w)], axis=2)


def sine_grid(cur: np.ndarray, seg: np.ndarray, min_len: int = 10) -> pd.DataFrame:
    """길이 ≥10 구간마다 0~5 Hz(0.005 간격) 사인+상수 최소제곱. 최적 주파수, R², 계수(sin, cos, 상수)."""
    ids, starts, lens = np.unique(seg, return_index=True, return_counts=True)
    by_len: dict[int, list[int]] = {}
    for s, st, L in zip(ids, starts, lens):
        if L >= min_len:
            by_len.setdefault(int(L), []).append(int(st))
    rows = []
    for L, sts in by_len.items():
        X = np.stack([cur[s:s + L] for s in sts])
        A = design(L, FREQS)
        P = np.linalg.pinv(A)
        beta = np.einsum("fkl,nl->fnk", P, X)
        fit = np.einsum("flk,fnk->fnl", A, beta)
        sse = ((X[None] - fit) ** 2).sum(2)
        sst = ((X - X.mean(1, keepdims=True)) ** 2).sum(1)
        k = sse.argmin(0)
        r2 = np.where(sst > 0, 1 - sse[k, np.arange(len(sts))] / np.where(sst > 0, sst, 1), np.nan)
        b = beta[k, np.arange(len(sts))]
        for j, s in enumerate(sts):
            rows.append(dict(segment=int(seg[s]), start_row=s, length=L, f=float(FREQS[k[j]]), r2=float(r2[j]),
                             a=float(b[j, 0]), b=float(b[j, 1])))
    return pd.DataFrame(rows).set_index("segment").sort_index()


def fit_sine(x, f, tt=None):
    tt = np.arange(len(x)) * 0.1 if tt is None else tt
    A = np.column_stack([np.sin(2 * np.pi * f * tt), np.cos(2 * np.pi * f * tt), np.ones(len(x))])
    return np.linalg.lstsq(A, x, rcond=None)[0]


def harmonic_r2(x, f, h):
    tt = np.arange(len(x)) * 0.1
    cols = [np.ones_like(tt)]
    for k in range(1, h + 1):
        cols += [np.sin(2 * np.pi * k * f * tt), np.cos(2 * np.pi * k * f * tt)]
    A = np.column_stack(cols)
    r = x - A @ np.linalg.lstsq(A, x, rcond=None)[0]
    return float(1 - (r ** 2).sum() / ((x - x.mean()) ** 2).sum())


def rayleigh(ph):
    n = len(ph)
    R = float(np.abs(np.mean(np.exp(1j * ph))))
    p = float(np.exp(np.sqrt(1 + 4 * n + 4 * (n ** 2 - (n * R) ** 2)) - (1 + 2 * n)))
    return R, min(1.0, p)


def resultant(d):
    return float(np.abs(np.mean(np.exp(1j * np.asarray(d)))))


def seg_stats(frame, seg, t):
    g = pd.DataFrame(dict(seg=seg, a0=frame.AI0_Vibration.to_numpy(float), a1=frame.AI1_Vibration.to_numpy(float),
                          c=frame.AI2_Current.to_numpy(float), t=t))
    gr = g.groupby("seg")
    out = gr.agg(n=("a0", "size"), sd0=("a0", "std"), sd1=("a1", "std"), start=("t", "min"), end=("t", "max"))
    out["crms_dm"] = gr.c.apply(lambda x: float(np.sqrt(np.mean((x - x.mean()) ** 2))))
    out["crms_raw"] = gr.c.apply(lambda x: float(np.sqrt(np.mean(x ** 2))))
    return out


def read_line(path: Path, n: int) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[n - 1] if 1 <= n <= len(lines) else None


def main():
    t_start = time.monotonic()
    R: dict = {"scope": "평가관 01 사이클2 2회차 독립 재계산",
               "head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}
    log("HEAD", R["head"])

    # ===== 0. 원본 동일성 =====
    with zipfile.ZipFile(ZIP) as z:
        zmem = {Path(n).name: z.read(n) for n in z.namelist() if n.endswith(".csv")}
    ev_man = json.loads((EVID / "manifest.json").read_text())
    dg_man = json.loads((EVID / "diagnostics_manifest.json").read_text())
    ident = {}
    for k, f in FILES.items():
        hs = dict(zip=sha(zmem[f]), raw=sha_file(RAW_DIR / f), pkg=sha_file(PKG_DIR / f),
                  evidence_manifest=ev_man["input_hashes"][k], diagnostics_manifest=dg_man["input_hashes"][k])
        ident[k] = dict(hs, all_equal=len(set(hs.values())) == 1)
        check(f"원본 해시 일치 {k}", ident[k]["all_equal"], hs)
    art = {p: sha_file(GUARD / "artifacts" / p) for p in ("guard_A.json", "guard_B.json")}
    check("동결 모델 해시 = diagnostics_manifest", art == dg_man["artifacts"], art)
    R["file_identity"] = ident
    log("file identity:", {k: v["all_equal"] for k, v in ident.items()}, "artifacts ok:", art == dg_man["artifacts"])

    raw = {k: pd.read_csv(io.BytesIO(zmem[f])) for k, f in FILES.items()}
    txt = {k: pd.read_csv(io.BytesIO(zmem[f]), dtype=str, keep_default_na=False) for k, f in FILES.items()}
    n, a = raw["normal"], raw["abnormal"]
    t = {k: pd.to_datetime(f.TimeStamp, format="%Y-%m-%d %H:%M:%S.%f") for k, f in raw.items()}
    seg = {k: seg_ids(t[k]) for k in raw}
    sn, sa = seg["normal"], seg["abnormal"]
    st = {k: seg_stats(raw[k], seg[k], t[k]) for k in raw}
    stn, sta = st["normal"], st["abnormal"]
    Ln, La = stn[stn.n >= 17], sta[sta.n >= 17]
    trA = sn < 360
    muV, sdV = n.loc[trA, VIB].mean().to_numpy(), n.loc[trA, VIB].std(ddof=0).to_numpy()

    # ===== 1. D1 센서 관계 =====
    rel = pd.read_csv(EVID / "sensor_relations.csv")
    res1 = {}
    for sub, f in raw.items():
        for tr_name, x in (("원값", f[SENS]), ("절댓값(가이드북 코드 14)", f[SENS].abs())):
            c = x.corr()
            for p1, p2, lab in (("AI0_Vibration", "AI1_Vibration", "AI0~AI1"), ("AI0_Vibration", "AI2_Current", "AI0~AI2"),
                                ("AI1_Vibration", "AI2_Current", "AI1~AI2")):
                v = float(c.loc[p1, p2])
                row = rel[(rel.section == "행 상관") & (rel.subset == sub) & (rel["transform"] == tr_name) & (rel.pair == lab)]
                ok = len(row) == 1 and close(v, row.value.iloc[0], 1e-12) and int(row.n.iloc[0]) == len(f)
                check(f"D1 행 상관 {sub} {tr_name} {lab}", ok, (v, row.value.tolist()))
                res1[f"{sub}|{tr_name}|{lab}"] = v
    for sub, L in (("normal", Ln), ("abnormal", La)):
        for xa, xb, lab in (("sd0", "crms_dm", "AI0 SD~AI2 RMS"), ("sd1", "crms_dm", "AI1 SD~AI2 RMS"), ("sd0", "sd1", "AI0 SD~AI1 SD")):
            r, p = stats.spearmanr(L[xa], L[xb])
            row = rel[(rel.section == "구간 수준 결합") & (rel.subset == sub) & (rel.pair == lab)]
            ok = len(row) == 1 and close(r, row.value.iloc[0], 1e-12) and close(p, row.p_value.iloc[0], 1e-6) and int(row.n.iloc[0]) == len(L)
            check(f"D1 구간 결합 {sub} {lab}", ok, (r, p, len(L), row[["value", "p_value", "n"]].values.tolist()))
            res1[f"{sub}|{lab}"] = dict(rho=r, p=p, n=len(L))
    cf = pd.read_csv(GUARD / "outputs" / "coupling_fit_v2.csv").set_index("split")
    ln = pd.read_csv(V1OUT / "load_normalization_meta.csv").set_index("split")
    xr = rel[rel.section == "교차 참조"]
    for r_ in xr.itertuples():
        path, line = r_.source.rsplit(":", 1)
        txt_line = read_line(REPO / path, int(line))
        if "coupling_fit" in path:
            sid = r_.subset[-2]
            ok = close(r_.value, cf.loc[sid, "r"], 1e-12) and txt_line.startswith(f"{sid},") and int(r_.n) == int(cf.loc[sid, "records"])
        else:
            key = r_.subset[r_.subset.index("(") + 1:-1]
            ok = close(r_.value, ln.loc[key, "amp_vib_corr_trainA"], 1e-12) and txt_line.startswith(f"{key},") and int(r_.n) == int(ln.loc[key, "fit_rows"])
        check(f"D1 교차 참조 {r_.source}", ok, (r_.value, txt_line[:60]))
    R["D1_sensor_relations"] = res1
    log("D1 relations:", {k: (round(v, 4) if isinstance(v, float) else {kk: round(vv, 4) for kk, vv in v.items()}) for k, v in res1.items()})

    # D1 운전변화(10분 블록)
    ov = pd.read_csv(EVID / "operating_variation.csv")
    L = Ln.copy()
    med = L[["crms_raw", "sd0", "sd1"]].median()
    mine = []
    for b, g in L.groupby(L.start.dt.floor("10min")):
        mine.append(dict(block_start=f"{b:%H:%M}", segments=len(g), first_segment=int(g.index.min()), last_segment=int(g.index.max()),
                         current_rms_median=float(g.crms_raw.median()), current_rms_rel=float(g.crms_raw.median() / med.crms_raw),
                         AI0_sd_rel=float(g.sd0.median() / med.sd0), AI1_sd_rel=float(g.sd1.median() / med.sd1)))
    mine = pd.DataFrame(mine)
    ok = len(mine) == len(ov) and (mine.block_start == ov.block_start).all() and all(
        np.allclose(mine[c].to_numpy(float), ov[c].to_numpy(float), rtol=0, atol=1e-9) for c in mine.columns if c != "block_start")
    check("D1 operating_variation 8블록 전부", ok, mine.round(4).to_dict("records"))
    R["D1_operating_variation"] = dict(rel_min=float(mine.current_rms_rel.min()), rel_max=float(mine.current_rms_rel.max()),
                                       block_0100=mine[mine.block_start == "01:00"].round(4).to_dict("records"))
    log("D1 operating variation rel range:", round(mine.current_rms_rel.min(), 4), round(mine.current_rms_rel.max(), 4),
        "01:00 block:", R["D1_operating_variation"]["block_0100"])

    # D1 B 오경보 구간의 운전 수준 — 동결 B 모델(읽기 전용)으로 오경보 구간을 찾는다
    sys.path.insert(0, str(GUARD))
    from model import GuardModel  # noqa: E402
    frozen = {sid: GuardModel.load(GUARD / "artifacts" / f"guard_{sid}.json") for sid in SPLITS}
    fa = {}
    minp_frozen = {}
    for sid, (tr_end, ca_end) in SPLITS.items():
        te = n[sn >= ca_end].reset_index(drop=True)
        pr = frozen[sid].predict(te, .01)
        mp = pr.groupby("record_id").p_value.min().fillna(1.0)
        minp_frozen[sid] = pd.Series(mp.to_numpy(), index=mp.index.to_numpy() + ca_end)
        fa[sid] = sorted(int(r) + ca_end for r in pr.loc[pr.alarm.eq(1), "record_id"].unique())
    tpB = GUARD / "outputs" / "test_predictions_B.csv"
    if tpB.exists():
        tp = pd.read_csv(tpB, usecols=["subset", "record_id", "alarm"])
        fa_file = sorted(int(r) + 420 for r in tp[(tp.subset == "normal_test") & (tp.alarm == 1)].record_id.unique())
        check("D1 B 오경보 구간 = test_predictions_B.csv", fa_file == fa["B"], (fa_file, fa["B"]))
    check("D1 B 오경보 구간 423·461·570, A 0건", fa["B"] == [423, 461, 570] and fa["A"] == [], fa)
    fal = pd.read_csv(EVID / "false_alarm_operating_level.csv").set_index("segment")
    lv = {}
    for s in fa["B"]:
        r_ = stn.loc[s]
        pct = {k: float((stn[k] < r_[k]).mean()) for k in ("sd0", "sd1", "crms_dm")}
        lv[s] = dict(AI0_top=1 - pct["sd0"], AI1_pct=pct["sd1"], cur_top=1 - pct["crms_dm"])
        ok = (close(pct["sd0"], fal.loc[s, "AI0_sd_pct"], 1e-12) and close(pct["sd1"], fal.loc[s, "AI1_sd_pct"], 1e-12)
              and close(pct["crms_dm"], fal.loc[s, "current_rms_pct"], 1e-12) and close(r_.sd0, fal.loc[s, "AI0_sd"], 1e-12))
        check(f"D1 오경보 운전 수준 {s}", ok, (lv[s], fal.loc[s].to_dict()))
    R["D1_false_alarm_levels"] = lv
    log("D1 B false alarms:", fa, "levels:", {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in lv.items()})

    # ===== 2. D4 생산단위·전류 의미 =====
    sine = {k: sine_grid(raw[k].AI2_Current.to_numpy(float), seg[k]) for k in raw}
    fn_ = sine["normal"]
    cur = n.AI2_Current.to_numpy(float)
    at06 = fn_[np.isclose(fn_.f, 0.6)]
    ph = np.array([np.arctan2(*fit_sine(cur[r.start_row:r.start_row + r.length], .6)[[1, 0]]) for r in at06.itertuples()])
    rb, rp = rayleigh(ph)
    pos = pd.Series(sn).groupby(sn).cumcount().to_numpy()
    zmax = np.abs((n[VIB].to_numpy(float) - muV) / sdV).max(1)
    groups = [zmax[(pos // 5) == b] for b in range(10)]
    prof = [float(g.mean()) for g in groups]
    kw = stats.kruskal(*groups).pvalue
    full = fn_[(fn_.length == 50) & np.isclose(fn_.f, .6)]
    segs50 = [cur[r.start_row:r.start_row + 50] for r in full.itertuples()]
    gain = np.array([harmonic_r2(x, .6, 3) - harmonic_r2(x, .6, 1) for x in segs50])
    ratio = np.array([np.hypot(*fit_sine(x[25:], .6)[:2]) / np.hypot(*fit_sine(x[:25], .6)[:2]) for x in segs50])
    exact9 = exact6 = total = 0
    spans = []
    for k, f in raw.items():
        dt = t[k].diff().dt.total_seconds().to_numpy()[1:]
        within = seg[k][1:] == seg[k][:-1]
        exact6 += int((np.abs(dt[within] - .1) <= 1e-6).sum())
        exact9 += int((np.abs(dt[within] - .1) <= 1e-9).sum())
        total += int(within.sum())
        lens = pd.Series(seg[k]).value_counts()
        for s in lens[lens == 50].index:
            tt = t[k][seg[k] == s]
            spans.append((tt.iloc[-1] - tt.iloc[0]).total_seconds())
    spans = np.asarray(spans)
    pu = pd.read_csv(EVID / "production_unit_evidence.csv")
    mine_pu = [(rb, rp, len(at06)), (min(prof), max(prof), len(n)), (float(np.median(gain)), float(np.quantile(gain, .95)), len(full)),
               (float(np.median(ratio)), f"{np.quantile(ratio, .05):.3f}~{np.quantile(ratio, .95):.3f}", len(full)),
               (exact6, total, total), (float(spans.min()), float(spans.max()), len(spans))]
    for i, (v1, v2, nn) in enumerate(mine_pu):
        r_ = pu.iloc[i]
        ok2 = (str(v2) == str(r_.value2)) if isinstance(v2, str) else close(v2, r_.value2, 1e-9)
        check(f"D4 {r_['item']}", close(v1, r_.value, 1e-9) and ok2 and int(r_.n) == nn, (v1, v2, nn, r_.value, r_.value2, r_.n))
    check("D4 Kruskal–Wallis p=0.89 표기", f"p={kw:.2f}" == pu.iloc[1].reference, (kw, pu.iloc[1].reference))
    check("D4 기록 안 간격이 1e-9 허용에서도 모두 0.100초(규칙의 동어반복이 아님)", exact9 == total == 19979, (exact9, total))
    check("D4 0.6 Hz 앨리어싱 필요 간격 0.101·0.099초", close(pu.iloc[6].value, 6.06 / 60, 1e-12) and close(pu.iloc[6].value2, 5.94 / 60, 1e-12), pu.iloc[6].tolist())
    R["D4_production_unit"] = dict(rayleigh=(rb, rp, len(at06)), position_profile=prof, kw_p=kw, harmonic_gain=(float(np.median(gain)), float(np.quantile(gain, .95)), len(full)),
                                   amp_ratio=(float(np.median(ratio)), float(np.quantile(ratio, .05)), float(np.quantile(ratio, .95))),
                                   intervals=(exact6, exact9, total), spans=(float(spans.min()), float(spans.max()), len(spans)))
    log("D4:", {k: v for k, v in R["D4_production_unit"].items() if k != "position_profile"})

    # D4 변수 기대 신호(관측 성질 수치)와 O4(a) 관측 가능성
    obs = pd.read_csv(EVID / "observability.csv")
    vexp = pd.read_csv(EVID / "variable_expected_signals.csv").set_index("column")
    for k, f in raw.items():
        same = np.r_[False, seg[k][1:] == seg[k][:-1]]
        for c in SENS:
            x = f[c].to_numpy(float)
            lag = float(np.corrcoef(x[1:][same[1:]], x[:-1][same[1:]])[0, 1])
            r_ = obs[(obs.file == k) & (obs.sensor == c)].iloc[0]
            ok = close(x.mean(), r_["mean"], 1e-9) and close(x.std(), r_.sd, 1e-9) and close((x < 0).mean(), r_.share_negative, 1e-12) and close(lag, r_.lag1_within, 1e-9)
            check(f"O4a 관측 성질 {k} {c}", ok, (x.mean(), x.std(), (x < 0).mean(), lag))
            if k == "normal":
                s = vexp.loc[c, "observed_property"]
                ok = f"{(x < 0).mean():.1%}" in s and f"{lag:.3f}" in s
                check(f"D4 기대 신호 표 관측 수치 {c}", ok, s[:120])
    check("O4a 순수 0.6 Hz 사인 lag-1 0.930", close(obs[obs.file == "기준"].lag1_within.iloc[0], np.cos(2 * np.pi * .06), 1e-12))
    for c, ln_no in (("AI0_Vibration", 4), ("AI1_Vibration", 5), ("AI2_Current", 6)):
        path, no = vexp.loc[c, "dictionary"].rsplit(":", 1)
        check(f"D4 변수 사전 인용 {c}", int(no) == ln_no and read_line(REPO / path, int(no)).startswith(f"{c},"), vexp.loc[c, "dictionary"])

    # ===== 3. D5 라벨 일관성 =====
    vmax_n = pd.Series(zmax).groupby(sn).max()
    thr = float(vmax_n[vmax_n.index >= 360].quantile(.99))
    r2min = float(fn_.r2.min())
    zmax_a = np.abs((a[VIB].to_numpy(float) - muV) / sdV).max(1)
    vmax_a = pd.Series(zmax_a).groupby(sa).max()
    ab = pd.read_csv(EVID / "abnormal_segments.csv").set_index("segment")
    fa_ = sine["abnormal"]
    kinds = {}
    for s in range(21):
        r2 = float(fa_.r2.get(s, np.nan))
        vo, ro = bool(vmax_a[s] > thr), bool(np.isfinite(r2) and r2 < r2min)
        kind = "진동·파형 모두" if vo and ro else ("진동만" if vo else ("파형만" if ro else "없음"))
        kinds[s] = kind
        r_ = ab.loc[s]
        ok = (close(vmax_a[s], r_.vib_segmax_z, 1e-9) and close(thr, r_.vib_threshold_q99, 1e-12) and close(r2, r_.r2, 1e-8)
              and close(r2min, r_.r2_normal_min, 1e-9) and kind == r_.outside_normal and int(r_.length) == int(sta.loc[s, "n"])
              and close(sta.loc[s, "sd0"], r_.AI0_sd, 1e-12) and close(sta.loc[s, "crms_dm"], r_.current_rms_dm, 1e-9))
        check(f"D5 이상 구간 {s}", ok, (vmax_a[s], r2, kind, r_.to_dict()))
    kk = pd.Series(kinds)
    trend = {c: stats.spearmanr(La.index, La[c]) for c in ("sd0", "crms_dm")}
    summ = pd.read_csv(EVID / "abnormal_summary.csv")
    mine_s = [(kk != "없음").sum(), kk.isin(["진동·파형 모두", "진동만"]).sum(), kk.isin(["진동·파형 모두", "파형만"]).sum(),
              (kk == "파형만").sum(), (kk == "진동만").sum(), trend["sd0"][0], trend["crms_dm"][0]]
    for i, v in enumerate(mine_s):
        check(f"D5 요약 {summ.iloc[i]['item']}", close(v, summ.iloc[i].value, 1e-12), (v, summ.iloc[i].value))
    R["D5_label_consistency"] = dict(threshold_q99=thr, r2_normal_min=r2min, kinds=kk.value_counts().to_dict(),
                                     wave_only=kk[kk == "파형만"].index.tolist(), vib_only=kk[kk == "진동만"].index.tolist(),
                                     trend=dict(sd0=(float(trend["sd0"][0]), float(trend["sd0"][1])), cur=(float(trend["crms_dm"][0]), float(trend["crms_dm"][1]))))
    log("D5:", R["D5_label_consistency"])

    # ===== 4. D6 관행 이상치 기준·가중 품질 지수·가이드북 표 =====
    orl = pd.read_csv(EVID / "outlier_rules.csv")
    uni = {"1.5×IQR": (np.zeros((~trA).sum(), bool), np.zeros(len(a), bool)), "3σ": (np.zeros((~trA).sum(), bool), np.zeros(len(a), bool))}
    for c in SENS:
        x, y = n[c].to_numpy(float), a[c].to_numpy(float)
        q1, q3 = np.percentile(x[trA], [25, 75])
        mu, sdv = x[trA].mean(), x[trA].std(ddof=1)
        for rule, lo, hi in (("1.5×IQR", q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)), ("3σ", mu - 3 * sdv, mu + 3 * sdv)):
            fnn, faa = ((x < lo) | (x > hi))[~trA], (y < lo) | (y > hi)
            if c != "AI2_Current":
                uni[rule][0][:] |= fnn
                uni[rule][1][:] |= faa
            r_ = orl[(orl.rule == rule) & (orl.sensor == c)].iloc[0]
            check(f"D6 {rule} {c}", int(r_.normal_nontrain_rows) == int(fnn.sum()) and int(r_.abnormal_rows) == int(faa.sum()) and close(lo, r_.lower, 1e-12),
                  (int(fnn.sum()), int(faa.sum()), r_.normal_nontrain_rows, r_.abnormal_rows))
    for rule, (fnn, faa) in uni.items():
        r_ = orl[(orl.rule == rule) & orl.sensor.str.startswith("진동")].iloc[0]
        check(f"D6 {rule} 진동 합집합", int(r_.normal_nontrain_rows) == int(fnn.sum()) and int(r_.abnormal_rows) == int(faa.sum()),
              (int(fnn.sum()), int(faa.sum()), float(faa.mean())))
    R["D6_outlier_union"] = {k: (int(v[0].sum()), float(v[0].mean()), int(v[1].sum()), float(v[1].mean())) for k, v in uni.items()}
    qw = pd.read_csv(EVID / "quality_index_weighted.csv")
    days = {"normal": ("2022-07-12", "2022-07-13"), "abnormal": ("2022-07-17", "2022-07-18")}
    W = dict(completeness=.6, uniqueness=.1, validity=.1, consistency=.1, integrity=.1)
    tot = {}
    for k, f in raw.items():
        body = f.drop(columns=[f.columns[0]])
        vc = body.value_counts()
        uniq = round((len(vc) - int((vc > 1).sum())) / len(vc) * 100, 2)
        valid = float(((t[k] >= days[k][0]) & (t[k] < days[k][1])).mean() * 100)
        q = dict(completeness=(1 - body.isna().sum().sum() / body.size) * 100, uniqueness=uniq, validity=valid, consistency=100.0)
        q["integrity"] = (1 - sum(v < 100 for v in (q["uniqueness"], q["validity"], q["consistency"])) / 3) * 100
        tot[k] = sum(q[i] * w for i, w in W.items())
        r_ = qw[(qw.file == k) & (qw["index"] == "total")].iloc[0]
        check(f"D6 가중 품질 지수 {k}", close(tot[k], r_.weighted_index, 1e-9) and abs(round(tot[k], 2) - r_.guidebook_weighted_index) <= 0.011, (tot[k], r_.guidebook_weighted_index))
    R["D6_quality_weighted"] = tot
    guide = {"normal": {"AI0_Vibration": (-0.000094, 0.070634, -0.314570, -0.000172, 0.351699), "AI1_Vibration": (-0.000093, 0.118888, -0.366498, -0.009317, 0.399782),
                        "AI2_Current": (1.446209, 122.664494, -271.568330, 1.849830, 273.235000)},
             "abnormal": {"AI0_Vibration": (0.007578, 0.447928, -1.502735, 0.015771, 1.803204), "AI1_Vibration": (-0.008137, 0.241226, -0.751253, 0.002161, 0.509321),
                          "AI2_Current": (57.329741, 153.172619, -399.351170, 53.644187, 538.826050)}}
    gsm = pd.read_csv(EVID / "guidebook_stats_match.csv")
    n_ok = 0
    for k, f in raw.items():
        for c in SENS:
            x = f[c].to_numpy(float)
            for nm, m, g in zip(("mean", "std", "min", "median", "max"), (x.mean(), x.std(ddof=1), x.min(), np.median(x), x.max()), guide[k][c]):
                r_ = gsm[(gsm.file == k) & (gsm.sensor == c) & (gsm.stat == nm)].iloc[0]
                ok = abs(m - g) <= 1.5e-6 and close(m, r_.recomputed, 1e-12) and bool(r_.match)
                n_ok += ok
    check("D6 가이드북 표 2·3 30개 값", n_ok == 30, n_ok)

    # ===== 5. D3 가이드북 프로토콜 대비 =====
    gp = pd.read_csv(EVID / "guidebook_protocol_vs_records.csv")
    idx = np.arange(len(n) - 121)
    tt = t["normal"].to_numpy()
    lead = (tt[idx + 120] - tt[idx + 19]) / np.timedelta64(1, "s")
    mine_gp = [f"구간 {sn[15000]}의 {pos[15000] + 1}번째 행({t['normal'][15000]:%H:%M:%S.%f}"[:-3] + ")",
               f"{((sn[idx + 19] - sn[idx]) > 0).mean():.1%}", f"{((sn[idx + 120] - sn[idx + 19]) > 0).mean():.1%}",
               f"중앙 {np.median(lead):.1f}초(5~95% {np.quantile(lead, .05):.1f}~{np.quantile(lead, .95):.1f}초)",
               f"상·하부 원값 상관 {res1['normal|원값|AI0~AI1']:+.3f} → {res1['abnormal|원값|AI0~AI1']:+.3f}, 절댓값 {res1['normal|절댓값(가이드북 코드 14)|AI0~AI1']:+.3f} → {res1['abnormal|절댓값(가이드북 코드 14)|AI0~AI1']:+.3f}"]
    for i, v in enumerate(mine_gp):
        check(f"D3 가이드북 대비 {gp.iloc[i]['item'][:24]}", v == gp.iloc[i].value, (v, gp.iloc[i].value))
    R["D3_guidebook_protocol"] = mine_gp
    log("D3 guidebook protocol:", mine_gp)

    # ===== 6. O4(b) 위상 연속성(독립 구현) =====
    tsec = (t["normal"] - t["normal"].iloc[0]).dt.total_seconds().to_numpy()
    ids = np.unique(sn)
    rows_of = {s: np.flatnonzero(sn == s) for s in ids}

    def phase_abs(ix_list, f):
        out = np.empty(len(ix_list))
        for i, ix in enumerate(ix_list):
            A = np.column_stack([np.cos(2 * np.pi * f * tsec[ix]), np.sin(2 * np.pi * f * tsec[ix]), np.ones(len(ix))])
            c = np.linalg.lstsq(A, cur[ix], rcond=None)[0]
            out[i] = np.arctan2(c[1], c[0])
        return out

    pairs = [(rows_of[s][-20:], rows_of[s + 1][:20]) for s in ids[:-1] if len(rows_of[s]) >= 20 and len(rows_of[s + 1]) >= 20]
    ends = [p[0] for p in pairs]; begins = [p[1] for p in pairs]
    gaps = np.array([tsec[b[0]] - tsec[e[-1]] for e, b in pairs])
    d = phase_abs(begins, .6) - phase_abs(ends, .6)
    short = gaps < np.median(gaps)
    long_recs = [rows_of[s] for s in ids if len(rows_of[s]) >= 50]
    ctrl = phase_abs([ix[-20:] for ix in long_recs], .6) - phase_abs([ix[:20] for ix in long_recs], .6)
    scan = [(float(f), resultant(phase_abs(begins, f) - phase_abs(ends, f))) for f in np.arange(.55, .65 + 1e-12, .0025)]
    f_best, r_best = max(scan, key=lambda z: z[1])
    starts = []
    for s in ids:
        ix = rows_of[s]
        if len(ix) >= 20:
            c = fit_sine(cur[ix[:20]], .6)
            starts.append(np.arctan2(c[1], c[0]))
    r_start, p_start = rayleigh(np.asarray(starts))
    rng = np.random.default_rng(20260927)
    pb, pe = phase_abs(begins, .6), phase_abs(ends, .6)
    null = np.array([resultant(rng.permutation(pb) - pe) for _ in range(2000)])
    pc = pd.read_csv(EVID / "phase_continuity.csv")
    mine_pc = [(len(long_recs), resultant(ctrl)), (len(d), resultant(d)), (int(short.sum()), resultant(d[short])), (int((~short).sum()), resultant(d[~short])),
               (len(d), r_best), (len(starts), r_start)]
    for i, (np_, rv) in enumerate(mine_pc):
        check(f"O4b 위상 {pc.iloc[i].test[:28]}", int(pc.iloc[i].pairs) == np_ and close(rv, pc.iloc[i].R, 1e-9), (np_, rv, pc.iloc[i].pairs, pc.iloc[i].R))
    check("O4b 섞은 귀무 95%(내 2000회) ≈ 표(200회)", abs(float(np.quantile(null, .95)) - float(pc.iloc[1].null_q95)) < 0.015,
          (float(np.quantile(null, .95)), pc.iloc[1].null_q95))
    check("O4b 공백 범위 1.55~8.43초·중앙 3.05초", f"{gaps.min():.2f}~{gaps.max():.2f}(중앙 {np.median(gaps):.2f})" == pc.iloc[1].gap_s, (gaps.min(), gaps.max(), np.median(gaps)))
    R["O4b_phase"] = dict(control=mine_pc[0], adjacent=mine_pc[1], short=mine_pc[2], long=mine_pc[3], scan_best=(f_best, r_best), start=(r_start, p_start, len(starts)),
                          my_null_q95=float(np.quantile(null, .95)), p_adjacent_vs_null=float((null >= resultant(d)).mean()))
    log("O4b phase:", R["O4b_phase"])

    # ===== 7. O1(a) 시간순 5겹 보정 곡선(재적합: press_guard.model 읽기 전용) =====
    rc = pd.read_csv(EVID / "rolling_calibration_curve.csv")
    roll_ref = pd.read_csv(GUARD / "outputs" / "rolling.csv")
    folds = []
    for end in (180, 240, 300, 360, 420):
        tr = n[sn < end].reset_index(drop=True)
        ca = n[(sn >= end) & (sn < end + 120)].reset_index(drop=True)
        te = n[(sn >= end + 120) & (sn < end + 180)].reset_index(drop=True)
        m = GuardModel.fit(tr, ca, split=f"train_to_{end}")
        mp = m.predict(te, .01).groupby("record_id").p_value.min().fillna(1.0)
        same = [sid for sid, fm in frozen.items() if np.array_equal(fm.cal, m.cal) and np.array_equal(fm.coef, m.coef) and np.array_equal(fm.mean, m.mean)]
        folds.append(dict(fold=f"normal_{end + 120}_{end + 179}", end=end, n_cal=len(m.cal), minp=pd.Series(mp.to_numpy(), index=mp.index.to_numpy() + end + 120),
                          same=same[0] if same else "", cal=np.asarray(m.cal)))
    for f in folds:
        for alpha in (.01, .03, .05):
            r_ = roll_ref[roll_ref.split.eq(f["fold"]) & roll_ref.model.eq("guard_v2") & np.isclose(roll_ref.alpha, alpha)].iloc[0]
            check(f"O1a {f['fold']} α={alpha} = rolling.csv", int((f["minp"] <= alpha).sum()) == int(r_.normal_notified_segments), (int((f["minp"] <= alpha).sum()), r_.normal_notified_segments))
        exp_same = {300: "B", 360: "A"}.get(f["end"], "")
        check(f"O1a {f['fold']} 동결 모델과 같음={exp_same or '없음'}", f["same"] == exp_same, f["same"])
    rng0 = np.random.default_rng(0)
    pooled = {}
    for k in range(1, 13):
        per = []
        for f in folds:
            x = int((f["minp"] <= k / (f["n_cal"] + 1) + 1e-12).sum())
            lo, hi = stats.betabinom(60, k, f["n_cal"] + 1 - k).ppf([.05, .95])
            r_ = rc[(rc.fold == f["fold"]) & (rc.k == k)].iloc[0]
            check(f"O1a {f['fold']} k={k}", x == int(r_.alerted) and int(lo) == int(r_.pi90_low) and int(hi) == int(r_.pi90_high), (x, lo, hi, r_.alerted, r_.pi90_low, r_.pi90_high))
            per.append(x)
        far = rng0.beta(k, 121 - k, size=(200_000, 5))
        sims = rng0.binomial(60, far).sum(axis=1)
        lo, hi = np.percentile(sims, [5, 95])
        r_ = rc[(rc.fold == "합산(5겹)") & (rc.k == k)].iloc[0]
        check(f"O1a 합산 k={k}", sum(per) == int(r_.alerted) and int(lo) == int(r_.pi90_low) and int(hi) == int(r_.pi90_high), (sum(per), lo, hi, r_.alerted, r_.pi90_low, r_.pi90_high))
        pooled[k] = (sum(per), int(lo), int(hi))
    R["O1a_pooled"] = pooled
    log("O1a pooled (alerted, pi90):", {k: pooled[k] for k in (1, 3, 6, 12)})

    # ===== 8. D3 결정표 인용·수치 =====
    dtab = pd.read_csv(EVID / "decision_table_diagnosis_v2.csv")
    cites = []
    for i, r_ in dtab.iterrows():
        for path, no in re.findall(r"(yejun/[^\s;:()]+):(\d+)", r_.evidence + " " + str(r_.limitation) + " " + str(r_.alternative_and_result)):
            line = read_line(REPO / path, int(no))
            cites.append(dict(row=i + 2, item=r_["item"], cite=f"{path}:{no}", line=(line or "")[:90]))
    expect_tokens = {
        "yejun/analysis/press_evidence/gaps.csv:2": "normal,", "yejun/press_guard/model.py:78": "def alert_units",
        "yejun/analysis/press_evidence/variable_dictionary.csv:7": "Equipment_state,", "yejun/press_submission/outputs/label_bypass.csv:2": "timestamps_shifted_5_days",
        "yejun/analysis/press_evidence/segment_rule_tolerance.csv:7": "normal,0.099,", "yejun/press_submission/README.md:31": "잘못된 행",
        "yejun/press_guard/test_guard.py:58": "def test_invalid_reset_and_no_false_normal", "yejun/analysis/press_evidence/duplicate_rows.csv:2": "00:43:33.196",
        "yejun/analysis/press_evidence/gaps.csv:3": "abnormal,", "yejun/analysis/press_evidence/outliers.csv:5": "어느 센서든",
        "yejun/analysis/press_evidence/outlier_rules.csv:8": "진동 두 센서 중 하나라도", "yejun/press_submission/outputs/diagnosis.md:43": "| either | matched |",
        "yejun/analysis/press_supervised/random_rows.csv:10": "decimal_digits(AI0)", "yejun/press_guard/model.py:185": "def fit",
        "yejun/press_guard/model.py:220": "np.where(pos < 7", "yejun/press_guard/outputs/ablation_v2.csv:26": "no_early_switch,recording_segments,conformal,0.01",
        "yejun/analysis/press_evidence/ar2_oscillator.csv:2": "A,", "yejun/press_guard/outputs/ablation_v2.csv:20": "no_dynamics,recording_segments,conformal,0.01",
        "yejun/analysis/press_evidence/imbalance.csv:3": "A 평가", "yejun/analysis/press_supervised/grouped_records.csv:30": "A,window_plus_v2,logistic,21fold,conformal",
        "yejun/press_submission/outputs/splits.csv:2": "A,normal_60_20_20,train", "yejun/analysis/press_evidence/rolling_calibration_curve.csv:4": "normal_420_479",
        "yejun/analysis/press_evidence/calibration_curve.csv:14": "B,1,", "yejun/analysis/press_evidence/rolling_calibration_curve.csv:7": "합산(5겹)",
        "yejun/press_guard/outputs/uncertainty_v2.csv:2": "A,normal_60_20_20,v1,0.01,normal,notified_segments,5",
        "yejun/analysis/press_supplement/e1_detection_floor.csv:7": "cur_noise,guard_v2", "yejun/analysis/press_supplement/e2_uci_metrics.csv:2": "local_normal_reference,3,v2_4ch",
        "yejun/analysis/press_supplement/e3_stability.csv:2": "0.01,15,99,"}
    for c in cites:
        tok = expect_tokens.get(c["cite"])
        if tok is None and "guidebook_protocol_vs_records.csv" in c["cite"]:
            tok = c["item"].split("(")[0]
        check(f"D3 결정표 인용 {c['cite']}", tok is not None and tok in (read_line(REPO / c["cite"].rsplit(":", 1)[0], int(c["cite"].rsplit(":", 1)[1])) or ""), c)
    stale = {p: h for p, h in dg_man["cited"].items() if sha_file(REPO / p) != h}
    check("D3 인용 파일 해시가 현재 파일과 같음(낡은 행 번호 없음)", not stale, stale)
    # 결정표 인용 수치
    abl = pd.read_csv(GUARD / "outputs" / "ablation_v2.csv")
    fnn = lambda mdl, sid: int(abl[abl.model.eq(mdl) & abl.criterion.eq("conformal") & np.isclose(abl.alpha, .01) & abl.split_id.eq(sid)].fn.iloc[0])
    grp = pd.read_csv(SUPV / "grouped_records.csv")
    g21 = grp[grp.cv.eq("21fold") & grp.threshold.eq("conformal") & grp.features.eq("window_plus_v2") & grp.model.eq("logistic")].set_index("split").f1
    floor = pd.read_csv(SUPP / "e1_detection_floor.csv").set_index(["family", "model"]).floor
    e2 = pd.read_csv(SUPP / "e2_uci_metrics.csv"); e2l = e2[e2["mode"] == "local_normal_reference"].auroc
    e3 = pd.read_csv(SUPP / "e3_stability.csv")
    txt_all = " ".join(dtab.evidence.astype(str)) + " " + " ".join(dtab.decision.astype(str)) + " " + " ".join(dtab.alternative_and_result.astype(str))
    nums = {
        "ablation 파형": f"미탐 A {fnn('v2', 'A')}→{fnn('no_waveform', 'A')}·B {fnn('v2', 'B')}→{fnn('no_waveform', 'B')}",
        "ablation 조기 전환": f"조기 전환 제거 시 A {fnn('no_early_switch', 'A')}·B {fnn('no_early_switch', 'B')}",
        "ablation 예측 오차": f"미탐 A {fnn('v2', 'A')}→{fnn('no_dynamics', 'A')}·B {fnn('v2', 'B')}→{fnn('no_dynamics', 'B')}",
        "21겹 로지스틱": f"A {g21['A']:.3f}·B {g21['B']:.3f}",
        "E1 하한": f"전류 잡음 {floor[('cur_noise', 'guard_v2')]:g}σ·오프셋 {floor[('cur_offset', 'guard_v2')]:g}×진폭·진동 잡음 {floor[('vib_noise', 'guard_v2')]:g}σ",
        "E2": f"AUROC {e2l.min():.2f}~{e2l.max():.2f}", "E3": f"충족 {int(e3.stable.sum())}/{len(e3)}",
        "롤링 합산": f"{pooled[1][0]}/300·{pooled[3][0]}/300·{pooled[6][0]}/300·{pooled[12][0]}/300",
        "B 오경보": "3/180(구간 423, 461, 570)", "시간 적용률": "정상 43.3%·이상 36.2%",
        "IQR": f"이상 {R['D6_outlier_union']['1.5×IQR'][2]}/600행({R['D6_outlier_union']['1.5×IQR'][3]:.0%})·정상 비학습 {R['D6_outlier_union']['1.5×IQR'][0]}행({R['D6_outlier_union']['1.5×IQR'][1]:.1%})",
    }
    for k, s in nums.items():
        check(f"D3 결정표 수치 {k}", s in txt_all, s)
    diag_md = (V1OUT / "diagnosis.md").read_text().splitlines()
    check("D3 결정표 raw AUROC 0.999 → matched 0.500 = diagnosis.md",
          any(l.startswith("| either | raw |") and l.rstrip().endswith("0.999 |") for l in diag_md) and any(l.startswith("| either | matched |") and l.rstrip().endswith("0.500 |") for l in diag_md))
    R["D3_decision_table"] = dict(rows=len(dtab), stages=dtab.stage.value_counts().to_dict(), citations=len(cites), stale=stale,
                                  bootstrap_row_cites=[c for c in cites if "uncertainty_v2.csv" in c["cite"]],
                                  bootstrap_v2_rows={"A": read_line(GUARD / "outputs" / "uncertainty_v2.csv", 23), "B": read_line(GUARD / "outputs" / "uncertainty_v2.csv", 65)})
    log("D3 decision table:", R["D3_decision_table"])

    # ===== 9. README 수치(사이클2 절) =====
    rd = (EVID / "README.md").read_text()
    e1 = pd.read_csv(SUPP / "e1_summary.csv")

    def e1r(fam, lev, t0=10):
        x = e1[(e1.model == "guard_v2") & np.isclose(e1.alpha, .01) & (e1["shape"] == "step") & (e1.t0 == t0) & (e1.family == fam) & np.isclose(e1.level, lev)].set_index("split").detect_rate_2s
        return f"{x['A']:.0%}·{x['B']:.0%}"
    r1n, r1a = res1["normal|AI0 SD~AI2 RMS"], res1["abnormal|AI0 SD~AI2 RMS"]
    tok = [f"{res1['normal|원값|AI0~AI1']:+.3f}", f"{res1['normal|절댓값(가이드북 코드 14)|AI0~AI1']:+.3f}", f"{res1['abnormal|절댓값(가이드북 코드 14)|AI0~AI1']:+.3f}",
           f"{res1['normal|원값|AI0~AI2']:.3f}·{res1['normal|원값|AI1~AI2']:.3f}", f"{res1['abnormal|원값|AI0~AI2']:.3f}·{res1['abnormal|원값|AI1~AI2']:.3f}",
           f"{r1n['rho']:.3f} ({r1n['n']}구간)", f"−{abs(r1a['rho']):.2f} ({r1a['n']}구간)", f"{res1['normal|AI1 SD~AI2 RMS']['rho']:.3f}",
           f"{res1['normal|AI0 SD~AI1 SD']['rho']:.3f}", f"{res1['abnormal|AI0 SD~AI1 SD']['rho']:.2f}",
           f"{R['D1_operating_variation']['rel_min']:.2f}~{R['D1_operating_variation']['rel_max']:.2f}배",
           f"상위 {lv[423]['AI0_top']:.1%}·{lv[461]['AI0_top']:.1%}, 전류 RMS 상위 {lv[423]['cur_top']:.1%}·{lv[461]['cur_top']:.1%}",
           f"상위 {lv[570]['AI0_top']:.1%}(전류는 상위 {lv[570]['cur_top']:.0%})",
           f"R̄ {rb:.3f}, Rayleigh p={rp:.2f}", f"{min(prof):.3f}~{max(prof):.3f}, Kruskal–Wallis p={kw:.2f}",
           f"중앙 {np.median(gain):.2%}, 95백분위 {np.quantile(gain, .95):.2%}", f"중앙 {np.median(ratio):.3f}(5~95% {np.quantile(ratio, .05):.3f}~{np.quantile(ratio, .95):.3f})",
           "19,979개", "모두 4.900초", f"q99({thr:.2f})", f"({r2min:.4f})", "0.93~1.54", "3~8행", f"{trend['sd0'][0]:.3f}(p={trend['sd0'][1]:.2f}, 14구간)",
           f"{R['D6_outlier_union']['1.5×IQR'][0]} ({R['D6_outlier_union']['1.5×IQR'][1]:.1%})", f"{R['D6_outlier_union']['1.5×IQR'][2]} ({R['D6_outlier_union']['1.5×IQR'][3]:.0%})",
           "26 / 1 / 0", "202 / 69 / 19", f"{tot['normal']:.3f}",
           f"{pooled[1][0]} (0.67%) | {pooled[1][1]}~{pooled[1][2]}", f"{pooled[3][0]} (2.67%) | {pooled[3][1]}~{pooled[3][2]}",
           f"{pooled[6][0]} (4.67%) | {pooled[6][1]}~{pooled[6][2]}", f"{pooled[12][0]} (9.33%) | {pooled[12][1]}~{pooled[12][2]}",
           f"| {len(long_recs)} | {resultant(ctrl):.3f} |", f"| {len(d)} | {resultant(d):.3f} | {pc.iloc[1].null_q95:.3f} |",
           f"{short.sum()} / {(~short).sum()} | {resultant(d[short]):.3f} / {resultant(d[~short]):.3f}", f"| {r_best:.3f} |", f"| {len(starts)} | {r_start:.3f} |",
           f"공백 {gaps.min():.2f}~{gaps.max():.2f}초, 중앙 {np.median(gaps):.2f}초",
           e1r("vib_noise", 2), e1r("vib_noise", 4), e1r("cur_noise", .1), e1r("cur_offset", .8, t0=0), e1r("cur_gain", 1.15), e1r("cur_gain", 1.5)]
    miss = [x for x in tok if x not in rd]
    check("README 사이클2 절 수치가 표·재계산과 일치", not miss, miss)
    R["readme_tokens_checked"] = len(tok)
    R["readme_tokens_missing"] = miss
    log("README tokens checked:", len(tok), "missing:", miss)

    # ===== 10. D2 그림 =====
    from PIL import Image
    figs = {}
    for p in sorted((EVID / "figures").glob("*.png")):
        with Image.open(p) as im:
            figs[p.name] = dict(size=im.size, sha=sha_file(p), manifest_ok=dg_man["outputs"].get(f"yejun/analysis/press_evidence/figures/{p.name}") == sha_file(p))
    check("D2 그림 5장·manifest 해시 일치", len(figs) == 5 and all(v["manifest_ok"] for v in figs.values()), figs)
    gaps_all = (stn.start.to_numpy()[1:] - stn.end.to_numpy()[:-1]) / np.timedelta64(1, "s")
    gaps_pos = gaps_all[gaps_all > 0]
    ela_n = (t["normal"].max() - t["normal"].min()).total_seconds(); ela_a = (t["abnormal"].max() - t["abnormal"].min()).total_seconds()
    zoom = ((stn.start >= pd.Timestamp("2022-07-12 00:30:00")) & (stn.end + pd.Timedelta(seconds=.1) <= pd.Timestamp("2022-07-12 00:32:00"))).sum()
    fig_txt = dict(normal=f"{len(stn)}구간·{len(n):,}행, 기록 {len(n) * .1:,.0f}초 / 경과 {ela_n:,.0f}초({len(n) * .1 / ela_n:.1%})",
                   abnormal=f"{len(sta)}구간·{len(a)}행, 기록 {len(a) * .1:.0f}초 / 경과 {ela_a:.1f}초({len(a) * .1 / ela_a:.1%})",
                   zoom=f"기록 {int(zoom)}개, 공백 중앙 {np.median(gaps_pos):.1f}초(전체 {gaps_pos.min():.2f}~{gaps_pos.max():.1f}초, {len(gaps_pos)}곳)")
    R["D2_figures"] = dict(files=figs, title_numbers=fig_txt)
    log("D2 figure title numbers (그림에서 읽은 값과 대조):", fig_txt)

    # ===== 11. D7·문서 간 일치 =====
    v1r = (V1 / "README.md").read_text()
    check("D7 v1 README 참조 두 줄", ("current_on_grid_strict" in v1r and "current_grid.csv" in v1r and "W13 문의 초안" in v1r and "§6의 4번" in v1r))
    strict = [i + 1 for i, l in enumerate(diag_md) if l.startswith("| current_on_grid_strict | raw |")]
    plan = (V1 / "PLAN.md").read_text().splitlines()
    R["D7"] = dict(diagnosis_md_strict_row=strict, plan_inquiry_lines=[i + 1 for i, l in enumerate(plan) if "문의 초안" in l])
    gr = (GUARD / "README.md").read_text()
    for s_ in ("12/120", "p=2.9e-11", "420~479 폴드는 B와, 480~539 폴드는 A와", "오경보 근거로 합산하지 않는다", "300~359·360~419·540~599 3개이고 모두 0/60"):
        check(f"문서 일치 press_guard README '{s_}'", s_ in gr)
    for s_ in ("오경보 판단의 주 근거는 B의 3/180", "합산하지 않는다(평가관 03 E6)"):
        check(f"문서 일치 press_evidence README '{s_}'", s_ in rd)
    log("D7:", R["D7"])

    # ===== 12. 새 진단: 정상 운전 상태의 구조(2회차 신규) =====
    from sklearn.mixture import GaussianMixture
    Lx = Ln.copy()
    xl = np.log(Lx.crms_dm.to_numpy()).reshape(-1, 1)
    bic = {}
    for kk_ in (1, 2, 3):
        gm = GaussianMixture(kk_, random_state=0, n_init=5).fit(xl)
        bic[kk_] = dict(bic=float(gm.bic(xl)), means=np.sort(np.exp(gm.means_.ravel())).round(1).tolist())
    gm2 = GaussianMixture(2, random_state=0, n_init=5).fit(xl)
    lo_comp = int(np.argmin(gm2.means_.ravel()))
    grid = np.linspace(np.log(60), np.log(200), 14001).reshape(-1, 1)
    post = gm2.predict_proba(grid)[:, lo_comp]
    xs_grid = np.exp(grid[:, 0])
    crossings = xs_grid[np.where(np.diff(np.sign(post - .5)) != 0)[0]]
    boundary = float([c for c in crossings if c > np.exp(gm2.means_.ravel()[lo_comp])][0])   # 저수준 봉우리 위쪽 경계
    low_sd_log = float(np.sqrt(gm2.covariances_.ravel()[lo_comp]))
    Lx["low"] = gm2.predict(xl) == lo_comp
    # A 학습 구간만으로 맞춘 2성분 혼합(불안정 여부 확인용)
    xtr = np.log(Lx[Lx.index < 360].crms_dm.to_numpy()).reshape(-1, 1)
    gtr = GaussianMixture(2, random_state=0, n_init=5).fit(xtr)
    ltr = int(np.argmin(gtr.means_.ravel()))
    ptr = gtr.predict_proba(grid)[:, ltr]
    ctr = xs_grid[np.where(np.diff(np.sign(ptr - .5)) != 0)[0]]
    train_only = dict(means=np.sort(np.exp(gtr.means_.ravel())).round(1).tolist(), crossings=np.round(ctr, 1).tolist())
    # 경계 민감도: 90·92·95와 혼합 경계
    parts = {"A 학습": (0, 360), "A 보정": (360, 480), "A 평가": (480, 600), "B 학습": (0, 300), "B 보정": (300, 420), "B 평가": (420, 600)}
    sens = {}
    for thr_ in (90.0, 92.0, 95.0, round(boundary, 1)):
        lowm = Lx.crms_dm < thr_
        sens[str(thr_)] = {nm: f"{int(lowm[(Lx.index >= p0) & (Lx.index < p1)].sum())}/{int(((Lx.index >= p0) & (Lx.index < p1)).sum())}" for nm, (p0, p1) in parts.items()}
    # 주기성: 기록 중앙 시각 사이 시차별 상태 상관(연속 저수준 473~563 이전, 구간 <470)
    pre = Lx[Lx.index < 470]
    mid = ((pre.start - pre.start.iloc[0]).dt.total_seconds() + pre.n * .05).to_numpy()
    sv = pre.low.to_numpy().astype(float)
    iu = np.triu_indices(len(mid), 1)
    lagd = (mid[None, :] - mid[:, None])[iu]
    lag_corr = {}
    for l0 in range(6, 84, 6):
        mm = (lagd >= l0) & (lagd < l0 + 6)
        lag_corr[f"{l0}-{l0 + 6}s"] = dict(pairs=int(mm.sum()), corr=float(np.corrcoef(sv[iu[0]][mm], sv[iu[1]][mm])[0, 1]))
    on = [i for i in range(1, len(sv)) if sv[i] == 1 and sv[i - 1] == 0]
    onset_iv = np.diff(pre.start.to_numpy()[on]) / np.timedelta64(1, "s")
    onset_hist = np.histogram(onset_iv, bins=np.arange(0, 95, 5))[0].tolist()
    rec_lag = {lag: float(np.corrcoef(sv[:-lag], sv[lag:])[0, 1]) for lag in range(1, 5)}
    # 상태별 전류 0.6 Hz 진폭·사인 R²
    amp_r2 = []
    for s_ in Lx.index:
        xv = cur[rows_of[s_]]
        cf_ = fit_sine(xv, .6)
        tt_ = np.arange(len(xv)) * .1
        res_ = xv - np.column_stack([np.sin(2 * np.pi * .6 * tt_), np.cos(2 * np.pi * .6 * tt_), np.ones(len(xv))]) @ cf_
        amp_r2.append((np.hypot(cf_[0], cf_[1]), 1 - (res_ ** 2).sum() / ((xv - xv.mean()) ** 2).sum()))
    Lx["amp06"], Lx["r2_06"] = np.array(amp_r2).T
    # 기록 안 상태 전환: 17행(약 1주기) 이동 창의 0.6 Hz 진폭 최대/최소 비. 두 상태 진폭 비는 약 1.75
    wr = []
    for s_ in Lx.index:
        xv = cur[rows_of[s_]]
        w_ = [np.hypot(*fit_sine(xv[i:i + 17], .6)[:2]) for i in range(0, len(xv) - 16)]
        wr.append(max(w_) / min(w_))
    Lx["win_ratio"] = wr
    gap_b = (stn.start - stn.end.shift(1)).dt.total_seconds()
    st_all = pd.Series(np.where(stn.n >= 17, np.where(stn.index.isin(Lx.index[Lx.low]), "low", "loaded"), "short"), index=stn.index)
    prev_ = st_all.shift(1)
    mm_ = (st_all != "short") & (prev_ != "short") & prev_.notna()
    chg_, same_ = (st_all != prev_) & mm_, (st_all == prev_) & mm_
    within_record = dict(records=len(Lx), ratio_q=np.quantile(Lx.win_ratio, [.5, .9, .99, 1]).round(3).tolist(), ratio_gt_1_3=int((Lx.win_ratio > 1.3).sum()),
                         state_amp_ratio=None, expected_straddle_random_timing=round(2 * 4.9 / 20.5, 2),
                         gap_before_change=dict(median=float(gap_b[chg_].median()), n=int(chg_.sum())),
                         gap_before_same=dict(median=float(gap_b[same_].median()), n=int(same_.sum())),
                         gap_mwu_p=float(stats.mannwhitneyu(gap_b[chg_], gap_b[same_]).pvalue))
    hist_c, edges = np.histogram(Lx.crms_dm, bins=np.arange(70, 195, 5))
    xs1 = np.log(Lx.sd1.to_numpy()).reshape(-1, 1)
    gv = GaussianMixture(2, random_state=0, n_init=5).fit(xs1)
    low_v = gv.predict(xs1) == int(np.argmin(gv.means_.ravel()))
    agree = float((low_v == Lx.low.to_numpy()).mean())
    s = Lx.low.to_numpy().astype(int)
    runs = []
    cur_s, ln_, first = s[0], 1, Lx.index[0]
    for i in range(1, len(s)):
        if s[i] == cur_s:
            ln_ += 1
        else:
            runs.append((cur_s, ln_, first, Lx.index[i - 1])); cur_s, ln_, first = s[i], 1, Lx.index[i]
    runs.append((cur_s, ln_, first, Lx.index[-1]))
    rdf = pd.DataFrame(runs, columns=["low", "len", "first", "last"])
    longest = rdf[rdf.low == 1].sort_values("len").iloc[-1]
    comp = {}
    for nm, (lo_, hi_) in {"A 학습": (0, 360), "A 보정": (360, 480), "A 평가": (480, 600), "B 학습": (0, 300), "B 보정": (300, 420), "B 평가": (420, 600)}.items():
        sub = Lx[(Lx.index >= lo_) & (Lx.index < hi_)]
        comp[nm] = dict(records_len17=len(sub), low=int(sub.low.sum()), low_share=float(sub.low.mean()))
    fisher = {sid: stats.fisher_exact([[comp[f"{sid} 보정"]["low"], comp[f"{sid} 보정"]["records_len17"] - comp[f"{sid} 보정"]["low"]],
                                       [comp[f"{sid} 평가"]["low"], comp[f"{sid} 평가"]["records_len17"] - comp[f"{sid} 평가"]["low"]]]) for sid in SPLITS}
    within = {}
    for lab, sub in Lx.groupby("low"):
        within["low" if lab else "loaded"] = dict(n=len(sub), sd0_cur=float(stats.spearmanr(sub.sd0, sub.crms_dm)[0]), sd1_cur=float(stats.spearmanr(sub.sd1, sub.crms_dm)[0]),
                                                  sd0_sd1=float(stats.spearmanr(sub.sd0, sub.sd1)[0]), crms_med=float(sub.crms_dm.median()),
                                                  sd0_med=float(sub.sd0.median()), sd1_med=float(sub.sd1.median()),
                                                  amp06_med=float(sub.amp06.median()), r2_06_med=float(sub.r2_06.median()), r2_06_min=float(sub.r2_06.min()))
    b10 = Lx.groupby(Lx.start.dt.floor("10min")).agg(records=("low", "size"), low_share=("low", "mean"))
    b10["loaded_crms_med"] = Lx[~Lx.low].groupby(Lx[~Lx.low].start.dt.floor("10min")).crms_dm.median()
    # 상태별 정상 알림(α 1·3·5%): 동결 A·B 평가, 시간순 5겹 합산. 길이 <17 기록은 '미분류'
    state = pd.Series(np.where(Lx.low, "low", "loaded"), index=Lx.index)

    def by_state(minp: pd.Series):
        out = {}
        stt = state.reindex(minp.index).fillna("short")
        for alpha in (.01, .03, .05):
            out[alpha] = {g: f"{int((minp[stt == g] <= alpha).sum())}/{int((stt == g).sum())}" for g in ("loaded", "low", "short")}
        return out
    alarms = {f"frozen_{sid}": by_state(minp_frozen[sid]) for sid in SPLITS}
    roll_all = pd.concat([f["minp"] for f in folds if not f["same"]])
    alarms["rolling_independent_3folds"] = by_state(roll_all)
    alarms["rolling_all_5folds"] = by_state(pd.concat([f["minp"] for f in folds]))
    # 경계 민감도: 90·95에서도 모든 정상 알림이 부하 상태인가
    alarm_sens = {}
    for thr_ in (90.0, 95.0):
        st_ = pd.Series(np.where(Lx.crms_dm < thr_, "low", "loaded"), index=Lx.index)
        allp = pd.concat([minp_frozen["A"], minp_frozen["B"]] + [f["minp"] for f in folds if not f["same"]])
        stt = st_.reindex(allp.index).fillna("short")
        alarm_sens[str(thr_)] = {str(al): {g: int((allp[stt == g] <= al).sum()) for g in ("loaded", "low", "short")} for al in (.01, .03, .05)}
    # 각 행의 결정표 인용 수
    per_row = {int(i + 2): len(re.findall(r"yejun/[^\s;:()]+:\d+", str(r_.evidence))) for i, r_ in dtab.iterrows()}
    check("D3 결정표 모든 행이 근거 칸에 파일:행 인용을 1개 이상 가진다", min(per_row.values()) >= 1, per_row)
    # 보정 기록(동결 B)의 최대 점수 순위와 상태
    cal_idx = np.arange(300, 420)
    calB = pd.Series(frozen["B"].cal, index=cal_idx)
    cal_state = state.reindex(cal_idx).fillna("short")
    top10 = cal_state[calB.sort_values(ascending=False).index[:10]].value_counts().to_dict()
    mw = stats.mannwhitneyu(calB[cal_state == "loaded"], calB[cal_state == "low"], alternative="greater")
    # 부하 상태 기록의 B α=1% 알림률 대 명목(참고): 보정의 부하 상태 기록 수+1 기준
    nl_cal = int((cal_state == "loaded").sum())
    nB_loaded = int((state.reindex(minp_frozen["B"].index).fillna("short") == "loaded").sum())
    xB_loaded = int(((minp_frozen["B"] <= .01) & (state.reindex(minp_frozen["B"].index).fillna("short") == "loaded")).sum())
    binom_p = float(stats.binomtest(xB_loaded, nB_loaded, 1 / (nl_cal + 1), alternative="greater").pvalue)
    within_record["state_amp_ratio"] = float(within["loaded"]["amp06_med"] / within["low"]["amp06_med"])
    R["NEW_operating_states"] = dict(
        within_record_transitions=within_record,
        gmm_bic=bic, boundary_crms=boundary, low_component_sd_log=low_sd_log, train_only_gmm=train_only, threshold_sensitivity=sens,
        alarms_threshold_sensitivity=alarm_sens, lag_corr_by_time=lag_corr, lag_corr_by_record=rec_lag,
        onset_interval=dict(median=float(np.median(onset_iv)), q25=float(np.percentile(onset_iv, 25)), q75=float(np.percentile(onset_iv, 75)),
                            n=len(onset_iv), hist_0_95_by5=onset_hist),
        hist_crms_70_195_by5=hist_c.tolist(), ai1_sd_gmm_agreement=agree,
        low_share=float(Lx.low.mean()), n_len17=len(Lx), switches=len(rdf) - 1,
        run_len=dict(low=rdf[rdf.low == 1].len.describe().round(2).to_dict(), loaded=rdf[rdf.low == 0].len.describe().round(2).to_dict()),
        longest_low_run=dict(len=int(longest.len), first=int(longest["first"]), last=int(longest["last"]),
                             start=str(stn.loc[int(longest["first"]), "start"]), end=str(stn.loc[int(longest["last"]), "end"])),
        split_composition=comp, fisher_cal_vs_eval={k: (float(v[0]), float(v[1])) for k, v in fisher.items()}, within_state=within,
        block10=b10.round(3).reset_index().astype(str).to_dict("records"),
        B_false_alarm_states={s_: state.get(s_, "short") for s_ in fa["B"]}, normal_alarms_by_state=alarms,
        calB_top10_state=top10, calB_loaded_vs_low_mwu_p=float(mw.pvalue), calB_loaded_records=nl_cal,
        B_loaded_alarm_rate=dict(x=xB_loaded, n=nB_loaded, nominal=1 / (nl_cal + 1), binom_p_greater=binom_p),
        documented=bool(re.search(r"두 상태|2상태|이봉|쌍봉|bimodal|운전 상태", rd)))
    log("NEW states: BIC", bic, "boundary", round(boundary, 1), "low comp log-SD", round(low_sd_log, 3), "low share", round(float(Lx.low.mean()), 3),
        "AI1 agreement", round(agree, 3), "switches", len(rdf) - 1, "longest low run", R["NEW_operating_states"]["longest_low_run"])
    log("NEW within-record transitions:", within_record)
    log("NEW train-only GMM (불안정 확인):", train_only, "threshold sensitivity:", sens)
    log("NEW periodicity: record-lag corr", {k: round(v, 3) for k, v in rec_lag.items()}, "time-lag corr",
        {k: round(v["corr"], 3) for k, v in lag_corr.items()}, "onset interval", R["NEW_operating_states"]["onset_interval"])
    log("NEW alarms by state, threshold sensitivity (frozen A·B + 독립 3겹):", alarm_sens)
    log("NEW split composition:", {k: (v["low"], v["records_len17"], round(v["low_share"], 3)) for k, v in comp.items()},
        "fisher cal vs eval:", R["NEW_operating_states"]["fisher_cal_vs_eval"])
    log("NEW within-state:", {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in within.items()})
    log("NEW block10:", b10.round(3).to_dict("index"))
    log("NEW alarms by state:", alarms)
    log("NEW calB top10 state:", top10, "MWU loaded>low p:", mw.pvalue, "B loaded α=1%:", R["NEW_operating_states"]["B_loaded_alarm_rate"],
        "documented in evidence README:", R["NEW_operating_states"]["documented"])

    # ===== 마무리 =====
    R["checks"] = dict(total=len(CHECKS), failed=[c for c in CHECKS if not c["ok"]])
    R["elapsed_s"] = time.monotonic() - t_start
    log(f"checks: {len(CHECKS)} total, {len(R['checks']['failed'])} failed")
    OUT_JSON.write_text(json.dumps(jsonable(R), ensure_ascii=False, indent=2))
    LOG.append(f"wrote {OUT_JSON.name} ({R['elapsed_s']:.1f}s)")
    OUT_LOG.write_text("\n".join(LOG) + "\n")
    print(LOG[-1])


if __name__ == "__main__":
    main()
