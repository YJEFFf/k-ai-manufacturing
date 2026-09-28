"""평가관 01(데이터 이해 및 진단) — 사이클2 3회차 독립 재계산.

기준 커밋 061fac8. 대회 ZIP 멤버를 직접 읽어
  (A) 2회차 보완 목록 R2-D1~D3의 새 산출물(operating_states·operating_states_summary·split_state_composition·
      normal_alarms_by_state, 정정된 production_unit_evidence·sensor_relations·decision_table_diagnosis_v2, 그림 3장)을
      다시 계산해 대조하고,
  (B) 1회차 항목(D1~D7) 산출물이 재실행 뒤에도 원본과 맞는지 회귀 검사하고,
  (C) 2회차 권고 자체의 한계(성분 수, 동기화 검정의 비교 기준)를 추가로 점검한다.
데이터 수준 검사는 패키지 코드를 import하지 않는다(독립 구현). 동결 모델 점수와 시간순 5겹 재적합이 필요한 검사만
press_guard.model을 읽기 전용으로 import한다(PYTHONDONTWRITEBYTECODE=1 필수). 결과는 이 폴더의 judge01_verify.json·.log에만 쓴다.

실행(저장소 루트):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      yejun/analysis/press_rubric_review/cycle2/round3/judge01_verify.py
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
from scipy.signal import lombscargle  # noqa: E402
from sklearn.mixture import GaussianMixture  # noqa: E402

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
LOW, LOADED, SHORT = "저수준", "부하", "짧은 기록(<17)"
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
    """길이 ≥10 구간마다 0~5 Hz(0.005 간격) 사인+상수 최소제곱. 최적 주파수, R², 계수."""
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


def expand_span(span: str) -> list[int]:
    if "-" in span:
        a, b = map(int, span.split("-"))
        return list(range(a, b + 1))
    return [int(x) for x in span.split(",")]


def gmm(x, k, seed=0):
    return GaussianMixture(k, random_state=seed, n_init=5).fit(x)


def win_ratio(x):
    w = [np.hypot(*fit_sine(x[i:i + 17], .6)[:2]) for i in range(len(x) - 16)]
    return max(w) / min(w)


def main():
    t_start = time.monotonic()
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    R: dict = {"scope": "평가관 01 사이클2 3회차 독립 재계산", "head_at_start": head}
    log("HEAD", head)

    # ===== 0. 원본·모델 동일성, 인용 파일 해시 =====
    with zipfile.ZipFile(ZIP) as z:
        zmem = {Path(n).name: z.read(n) for n in z.namelist() if n.endswith(".csv")}
    ev_man = json.loads((EVID / "manifest.json").read_text())
    dg_man = json.loads((EVID / "diagnostics_manifest.json").read_text())
    ident = {}
    for k, f in FILES.items():
        hs = dict(zip=sha(zmem[f]), raw=sha_file(RAW_DIR / f), pkg=sha_file(PKG_DIR / f),
                  evidence_manifest=ev_man["input_hashes"][k], diagnostics_manifest=dg_man["input_hashes"][k])
        ident[k] = dict(hs, all_equal=len(set(hs.values())) == 1)
        check(f"S0 원본 해시 일치 {k}", ident[k]["all_equal"], hs)
    art = {p: sha_file(GUARD / "artifacts" / p) for p in ("guard_A.json", "guard_B.json")}
    check("S0 동결 모델 해시 = diagnostics_manifest", art == dg_man["artifacts"], art)
    stale = {p: h for p, h in dg_man["cited"].items() if sha_file(REPO / p) != h}
    check("S0 결정표·대응표 인용 파일 해시가 현재 파일과 같음", not stale, stale)
    code_stale = {p: h for p, h in dg_man["code_sha256"].items() if sha_file(REPO / p) != h}
    check("S0 diagnostics_manifest 코드 해시가 현재 코드와 같음", not code_stale, code_stale)
    out_stale = {p: h for p, h in dg_man["outputs"].items() if sha_file((EVID / p) if "/" not in p else (REPO / p)) != h}
    check("S0 diagnostics_manifest 산출물 해시가 현재 파일과 같음(25개)", not out_stale and len(dg_man["outputs"]) == 25, (len(dg_man["outputs"]), out_stale))
    R["file_identity"] = dict(ident=ident, artifacts=art, stale_cited=stale, stale_code=code_stale, stale_outputs=out_stale)
    log("S0 identity:", {k: v["all_equal"] for k, v in ident.items()}, "artifacts ok:", art == dg_man["artifacts"],
        "stale cited/code/outputs:", len(stale), len(code_stale), len(out_stale))

    raw = {k: pd.read_csv(io.BytesIO(zmem[f])) for k, f in FILES.items()}
    n, a = raw["normal"], raw["abnormal"]
    t = {k: pd.to_datetime(f.TimeStamp, format="%Y-%m-%d %H:%M:%S.%f") for k, f in raw.items()}
    seg = {k: seg_ids(t[k]) for k in raw}
    sn, sa = seg["normal"], seg["abnormal"]
    st = {k: seg_stats(raw[k], seg[k], t[k]) for k in raw}
    stn, sta = st["normal"], st["abnormal"]
    Ln, La = stn[stn.n >= 17], sta[sta.n >= 17]
    trA = sn < 360
    muV, sdV = n.loc[trA, VIB].mean().to_numpy(), n.loc[trA, VIB].std(ddof=0).to_numpy()
    cur = n.AI2_Current.to_numpy(float)
    ids = np.unique(sn)
    rows_of = {s: np.flatnonzero(sn == s) for s in ids}

    # ===== 1. R2-D1 정상 운전 상태 — operating_states.csv 469행 독립 재계산 =====
    ost = pd.read_csv(EVID / "operating_states.csv").set_index("record")
    L = Ln.copy()
    amp, r2, wr = [], [], []
    for s in L.index:
        x = cur[rows_of[s]]
        c = fit_sine(x, .6)
        tt = np.arange(len(x)) * .1
        res = x - np.column_stack([np.sin(2 * np.pi * .6 * tt), np.cos(2 * np.pi * .6 * tt), np.ones(len(x))]) @ c
        amp.append(float(np.hypot(c[0], c[1])))
        r2.append(float(1 - (res ** 2).sum() / ((x - x.mean()) ** 2).sum()))
        wr.append(win_ratio(x))
    L["amp06"], L["r2_06"], L["wr"] = amp, r2, wr
    xl = np.log(L.crms_dm.to_numpy()).reshape(-1, 1)
    gms = {k: gmm(xl, k) for k in range(1, 7)}
    g2 = gms[2]
    lo = int(np.argmin(g2.means_.ravel()))
    grid = np.linspace(np.log(60), np.log(200), 14001).reshape(-1, 1)
    post = g2.predict_proba(grid)[:, lo]
    xs_grid = np.exp(grid[:, 0])
    cross = xs_grid[np.where(np.diff(np.sign(post - .5)) != 0)[0]]
    boundary = float([c for c in cross if c > np.exp(g2.means_.ravel()[lo])][0])
    L["p_low"] = g2.predict_proba(xl)[:, lo]
    L["state"] = np.where(g2.predict(xl) == lo, LOW, LOADED)
    check("R2-D1 표 기록 목록 = 길이≥17 정상 기록 469개", list(ost.index) == list(L.index) and len(L) == 469, (len(ost), len(L)))
    per = dict(length=(ost.length.to_numpy(), L.n.to_numpy(), 0), current_rms_dm=(ost.current_rms_dm.to_numpy(), L.crms_dm.to_numpy(), 1e-9),
               AI0_sd=(ost.AI0_sd.to_numpy(), L.sd0.to_numpy(), 1e-12), AI1_sd=(ost.AI1_sd.to_numpy(), L.sd1.to_numpy(), 1e-12),
               amp06=(ost.amp06.to_numpy(), L.amp06.to_numpy(), 1e-9), r2_06=(ost.r2_06.to_numpy(), L.r2_06.to_numpy(), 1e-9),
               win_amp_ratio=(ost.win_amp_ratio.to_numpy(), L.wr.to_numpy(), 1e-9), p_low=(ost.p_low.to_numpy(), L.p_low.to_numpy(), 1e-6))
    for col, (mine_t, mine_m, tol) in per.items():
        ok = np.allclose(mine_t.astype(float), mine_m.astype(float), rtol=0, atol=tol)
        check(f"R2-D1 operating_states.{col} 469행", ok, float(np.max(np.abs(mine_t.astype(float) - mine_m.astype(float)))))
    check("R2-D1 operating_states.state 469행", (ost.state.to_numpy() == L.state.to_numpy()).all(), int((ost.state.to_numpy() != L.state.to_numpy()).sum()))
    for thr in (90, 92, 95):
        mine = np.where(L.crms_dm < thr, LOW, LOADED)
        check(f"R2-D1 operating_states.state_thr{thr}", (ost[f"state_thr{thr}"].to_numpy() == mine).all())
    ts = (ost.start == L.start.dt.strftime("%H:%M:%S.%f").str[:-3].to_numpy()).all() and (ost.end == L.end.dt.strftime("%H:%M:%S.%f").str[:-3].to_numpy()).all()
    check("R2-D1 operating_states.start·end 469행", ts)
    check("R2-D1 GMM 상태 = 경계 91.9 문턱 분류(단조 경계)", ((L.crms_dm < boundary) == (L.state == LOW)).all())

    # summary 표
    sm = pd.read_csv(EVID / "operating_states_summary.csv")
    smi = sm.set_index("item")
    bic = {k: float(g.bic(xl)) for k, g in gms.items()}
    means = {k: sorted(np.exp(g.means_.ravel()).round(1).tolist()) for k, g in gms.items()}
    for k in (1, 2, 3):
        r_ = smi.loc[f"가우스 혼합 {k}성분 BIC(로그 전류 RMS)"]
        check(f"R2-D1 BIC {k}성분", close(bic[k], r_.value, 1e-9) and str(means[k]) in r_.note, (bic[k], r_.value, means[k], r_.note))
    low_sd = float(np.sqrt(g2.covariances_.ravel()[lo]))
    r_ = smi.loc["2성분 경계(저수준 사후확률 0.5)"]
    check("R2-D1 2성분 경계 91.886·로그 SD 0.036", close(boundary, r_.value, 1e-9) and f"{low_sd:.3f}" in r_.note, (boundary, r_.value, low_sd))
    hist, edges = np.histogram(L.crms_dm, bins=np.arange(70, 195, 5))
    htxt = " ".join(f"{int(e_)}~{int(e_) + 5}:{h}" for e_, h in zip(edges[:-1], hist) if 80 <= e_ < 100)
    check("R2-D1 전류 RMS 80~100 분포", htxt == smi.loc["전류 RMS 분포(5 간격) 80~100 구간 개수", "value"], (htxt,))
    tr = L[L.index < 360]
    gt = gmm(np.log(tr.crms_dm.to_numpy()).reshape(-1, 1), 2)
    ltr = int(np.argmin(gt.means_.ravel()))
    ptr = gt.predict_proba(grid)[:, ltr]
    ctr = xs_grid[np.where(np.diff(np.sign(ptr - .5)) != 0)[0]]
    check("R2-D1 A 학습만 2성분 경계 116.57", close(float(ctr[0]), smi.loc["A 학습 구간만으로 맞춘 2성분 경계", "value"], 1e-9), (ctr, ))
    xs1 = np.log(L.sd1.to_numpy()).reshape(-1, 1)
    gv = gmm(xs1, 2)
    agree = float(((gv.predict(xs1) == int(np.argmin(gv.means_.ravel()))) == (L.state == LOW).to_numpy()).mean())
    check("R2-D1 AI1 SD 2성분 일치율 95.5%", close(agree, smi.loc["AI1 SD만으로 나눈 2성분과 상태 일치율", "value"], 1e-12), agree)
    per_state = {}
    for s_, g in L.groupby("state"):
        per_state[s_] = dict(n=len(g), crms=float(g.crms_dm.median()), amp=float(g.amp06.median()), sd0=float(g.sd0.median()), sd1=float(g.sd1.median()),
                             r2med=float(g.r2_06.median()), r2min=float(g.r2_06.min()))
        r_ = smi.loc[f"{s_}: 전류 RMS 중앙 / 0.6 Hz 진폭 중앙"]
        ok = (close(per_state[s_]["crms"], r_.value, 1e-9) and close(per_state[s_]["amp"], r_.value2, 1e-9) and int(r_.n) == len(g)
              and f"AI0 SD 중앙 {per_state[s_]['sd0']:.3f}" in r_.note and f"AI1 SD 중앙 {per_state[s_]['sd1']:.3f}" in r_.note
              and f"{per_state[s_]['r2med']:.4f}(최소 {per_state[s_]['r2min']:.4f})" in r_.note)
        check(f"R2-D1 상태별 값 {s_}", ok, (per_state[s_], r_.to_dict()))
    ratio = per_state[LOADED]["amp"] / per_state[LOW]["amp"]
    check("R2-D1 부하/저수준 진폭 비 1.75", close(ratio, smi.loc["부하/저수준 0.6 Hz 진폭 비", "value"], 1e-12), ratio)
    # 주기
    pre = L[L.index < 470]
    mid = ((pre.start - pre.start.iloc[0]).dt.total_seconds() + pre.n * .05).to_numpy()
    sv = (pre.state == LOW).to_numpy().astype(float)
    iu = np.triu_indices(len(mid), 1)
    lagd = (mid[None, :] - mid[:, None])[iu]
    lagc = {}
    for l0 in range(6, 84, 6):
        m = (lagd >= l0) & (lagd < l0 + 6)
        c = float(np.corrcoef(sv[iu[0]][m], sv[iu[1]][m])[0, 1])
        lagc[l0] = (c, int(m.sum()))
        r_ = smi.loc[f"기록 중앙 시각 차 {l0}~{l0 + 6}초 쌍의 상태 상관"]
        check(f"R2-D1 시차 {l0}~{l0 + 6}초 상태 상관", close(c, r_.value, 1e-12) and int(r_.n) == int(m.sum()), (c, r_.value))
    on = [i for i in range(1, len(sv)) if sv[i] == 1 and sv[i - 1] == 0]
    iv = np.diff(pre.start.to_numpy()[on]) / np.timedelta64(1, "s")
    r_ = smi.loc["저수준 시작 간격 중앙 / 사분위"]
    check("R2-D1 저수준 시작 간격 중앙 34.5초", close(np.median(iv), r_.value, 1e-12) and r_.value2 == f"{np.percentile(iv, 25):.1f}~{np.percentile(iv, 75):.1f}" and int(r_.n) == len(iv),
          (np.median(iv), r_.value2))
    hh, _ = np.histogram(iv, bins=np.arange(0, 95, 5))
    htxt2 = " ".join(f"{a_}~{a_ + 5}:{c_}" for a_, c_ in zip(range(0, 90, 5), hh) if c_)
    check("R2-D1 저수준 시작 간격 분포", htxt2 in r_.note, htxt2)
    for lag in range(1, 5):
        c = float(np.corrcoef(sv[:-lag], sv[lag:])[0, 1])
        check(f"R2-D1 기록 순서 {lag}칸 상태 상관", close(c, smi.loc[f"기록 순서 {lag}칸 뒤 상태 상관", "value"], 1e-12), c)
    s01 = (L.state == LOW).to_numpy().astype(int)
    runs, cs, ln_, first = [], s01[0], 1, L.index[0]
    for i in range(1, len(s01)):
        if s01[i] == cs:
            ln_ += 1
        else:
            runs.append((cs, ln_, first, L.index[i - 1])); cs, ln_, first = s01[i], 1, L.index[i]
    runs.append((cs, ln_, first, L.index[-1]))
    rdf = pd.DataFrame(runs, columns=["low", "len", "first", "last"])
    longest = rdf[rdf.low == 1].sort_values("len").iloc[-1]
    check("R2-D1 상태 전환 227회", len(rdf) - 1 == int(smi.loc["상태 전환 횟수(길이≥17 기록 순서)", "value"]), len(rdf) - 1)
    r_ = smi.loc["가장 긴 저수준 연속(길이≥17 기록)"]
    lt = f"{L.loc[int(longest['first']), 'start']:%H:%M:%S}~{L.loc[int(longest['last']), 'end']:%H:%M:%S}"
    check("R2-D1 가장 긴 저수준 연속 72기록 473~563", int(longest.len) == int(r_.value) == 72 and r_.value2 == f"구간 {int(longest['first'])}~{int(longest['last'])}" and lt in r_.note,
          (int(longest.len), int(longest["first"]), int(longest["last"]), lt))
    # 동기화
    q = np.quantile(L.wr, [.5, .9, .99, 1])
    r_ = smi.loc["기록 안 17행 창 0.6 Hz 진폭의 최대/최소 비(중앙·90%·99%·최대)"]
    check("R2-D1 기록 안 진폭 비 분위", close(q[-1], r_.value, 1e-9) and r_.value2 == " / ".join(f"{v:.3f}" for v in q), (q, r_.value2))
    check("R2-D1 진폭 비 1.3 초과 0/469", int((L.wr > 1.3).sum()) == int(smi.loc["진폭 비 1.3 초과 기록", "value"]) == 0)
    st_all = pd.Series(np.where(stn.n >= 17, np.where(stn.index.isin(L.index[L.state == LOW]), LOW, LOADED), SHORT), index=stn.index)
    prev = st_all.shift(1)
    okm = (st_all != SHORT) & (prev != SHORT) & prev.notna()
    gapb = (stn.start - stn.end.shift(1)).dt.total_seconds()
    chg, same = (st_all != prev) & okm, (st_all == prev) & okm
    mw_gap = float(stats.mannwhitneyu(gapb[chg], gapb[same]).pvalue)
    r_ = smi.loc["직전 기록과 상태가 바뀐 공백 / 같은 공백의 길이 중앙(초)"]
    check("R2-D1 전환 공백 대 비전환 공백 3.12·3.12초 p=0.28", close(gapb[chg].median(), r_.value, 1e-9) and close(gapb[same].median(), r_.value2, 1e-9)
          and f"p={mw_gap:.2f}" in r_.note and f"바뀜 {int(chg.sum())}·같음 {int(same.sum())}" in r_.note, (gapb[chg].median(), gapb[same].median(), mw_gap))
    # 상태 안 결합
    within = {}
    for s_, g in L.groupby("state"):
        within[s_] = (float(stats.spearmanr(g.sd0, g.crms_dm)[0]), float(stats.spearmanr(g.sd1, g.crms_dm)[0]), float(stats.spearmanr(g.sd0, g.sd1)[0]))
        r_ = smi.loc[f"{s_}: AI0 SD~전류 RMS / AI1 SD~전류 RMS(Spearman)"]
        check(f"R2-D1 상태 안 결합 {s_}", close(within[s_][0], r_.value, 1e-12) and close(within[s_][1], r_.value2, 1e-12) and f"{within[s_][2]:.3f}" in r_.note, within[s_])
    b10 = L.groupby(L.start.dt.floor("10min")).agg(low_share=("state", lambda x: float((x == LOW).mean())))
    lm = L[L.state == LOADED].groupby(L[L.state == LOADED].start.dt.floor("10min")).crms_dm.median()
    r_ = smi.loc["10분 블록별 부하 상태 전류 RMS 중앙 최소~최대"]
    check("R2-D1 부하 수준 안 변동 122~157", close(lm.min(), r_.value, 1e-9) and close(lm.max(), r_.value2, 1e-9)
          and " ".join(f"{k:%H:%M}:{v:.2f}" for k, v in b10.low_share.items()) in r_.note, (lm.min(), lm.max()))
    R["R2_D1"] = dict(bic=bic, means=means, boundary=boundary, low_sd=low_sd, agree_ai1=agree, per_state=per_state, amp_ratio=ratio,
                      lag_corr={f"{k}-{k + 6}s": v for k, v in lagc.items()}, onset=dict(median=float(np.median(iv)), n=len(iv), hist=htxt2),
                      switches=len(rdf) - 1, longest=dict(len=int(longest.len), first=int(longest["first"]), last=int(longest["last"]), time=lt),
                      win_ratio_q=q.tolist(), gt_1_3=int((L.wr > 1.3).sum()), gap_change_same=(float(gapb[chg].median()), float(gapb[same].median()), mw_gap),
                      within=within, loaded_block_median=(float(lm.min()), float(lm.max())))
    log("R2-D1 BIC k=1..6:", {k: round(v, 1) for k, v in bic.items()}, "means:", means)
    log("R2-D1 boundary", round(boundary, 2), "low log-SD", round(low_sd, 3), "AI1 agree", round(agree, 4), "per state:",
        {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in per_state.items()})
    log("R2-D1 lag corr:", {k: round(v[0], 3) for k, v in lagc.items()}, "onset median", round(float(np.median(iv)), 2), htxt2)
    log("R2-D1 sync: ratio q", np.round(q, 3).tolist(), ">1.3:", int((L.wr > 1.3).sum()), "gap chg/same", round(gapb[chg].median(), 3), round(gapb[same].median(), 3), "p", round(mw_gap, 3))
    log("R2-D1 longest low run:", R["R2_D1"]["longest"], "within:", {k: np.round(v, 3).tolist() for k, v in within.items()}, "loaded block med:", R["R2_D1"]["loaded_block_median"])

    # ===== 2. 2회차 권고 자체의 한계 점검(새) =====
    # (a) 성분 수: BIC 1~6성분(로그 전류 RMS), 2차원(로그 전류 RMS·로그 AI1 SD), 시드 민감도
    bic_seeds = {k: [round(float(gmm(xl, k, s_).bic(xl)), 1) for s_ in range(5)] for k in range(1, 7)}
    X2 = np.column_stack([np.log(L.crms_dm), np.log(L.sd1)])
    bic2d = {k: float(GaussianMixture(k, random_state=0, n_init=5).fit(X2).bic(X2)) for k in range(1, 6)}
    kbest = min(bic, key=bic.get)
    kbest2d = min(bic2d, key=bic2d.get)
    g4 = gms[4]
    order4 = np.argsort(g4.means_.ravel())
    c4 = np.argsort(order4)[g4.predict(xl)]
    L["c4"] = c4
    prevL = L.shift(1)
    adj = pd.Series(L.index, index=L.index).diff().eq(1)
    trans4 = pd.crosstab(prevL.c4[adj].astype(int), L.c4[adj], normalize="index").round(2)
    blk4 = pd.crosstab(L.start.dt.floor("10min").dt.strftime("%H:%M"), L.c4)
    hist_full = np.histogram(L.crms_dm, bins=np.arange(75, 190, 5))
    R["component_count"] = dict(bic_log_crms=bic, bic_seeds=bic_seeds, bic_2d=bic2d, k_best=kbest, k_best_2d=kbest2d,
                                means_k4=np.sort(np.exp(g4.means_.ravel())).round(1).tolist(), weights_k4=g4.weights_[order4].round(3).tolist(),
                                transition_k4=trans4.to_dict(), blocks_k4=blk4.to_dict(),
                                hist_75_190_by5=dict(zip([int(e_) for e_ in hist_full[1][:-1]], hist_full[0].tolist())))
    log("NEW 성분 수: BIC 최소 k =", kbest, "(로그 전류 RMS)", {k: round(v, 1) for k, v in bic.items()}, "| 2차원 최소 k =", kbest2d, {k: round(v, 1) for k, v in bic2d.items()})
    log("NEW k=4 성분 중앙", R["component_count"]["means_k4"], "가중치", R["component_count"]["weights_k4"])
    log("NEW k=4 인접 기록 전이(행=앞, 열=뒤):", trans4.to_dict("index"))
    log("NEW 10분 블록 × k=4 성분:", blk4.to_dict("index"))
    log("NEW 전류 RMS 5 간격 분포(75~190):", R["component_count"]["hist_75_190_by5"])
    # 저수준 대 그 밖의 분류가 성분 수와 무관한가(저수준 성분이 k=2~6에서 같은 기록을 고르는가)
    low_sets = {}
    for k in range(2, 7):
        g = gms[k]
        lo_k = int(np.argmin(g.means_.ravel()))
        low_sets[k] = set(L.index[g.predict(xl) == lo_k])
    base = set(L.index[L.state == LOW])
    low_overlap = {k: dict(n=len(v), jaccard=len(v & base) / len(v | base)) for k, v in low_sets.items()}
    R["component_count"]["low_component_overlap"] = low_overlap
    log("NEW 저수준 성분(k=2~6)과 2성분 저수준의 일치(Jaccard):", {k: (v["n"], round(v["jaccard"], 3)) for k, v in low_overlap.items()})

    # (b) 약 20초 주기의 독립 확인: Lomb–Scargle(상태 지표·로그 전류 RMS), 섞은 귀무
    periods = np.linspace(8, 80, 2000)
    w = 2 * np.pi / periods
    y = sv - sv.mean()
    P = lombscargle(mid, y, w, normalize=True)
    yc = np.log(pre.crms_dm.to_numpy()); yc = yc - yc.mean()
    Pc = lombscargle(mid, yc, w, normalize=True)
    rng = np.random.default_rng(20260928)
    null = np.array([lombscargle(mid, rng.permutation(y), w, normalize=True).max() for _ in range(300)])
    halves = {}
    for lo_, hi_ in ((0, 235), (235, 470)):
        m_ = (pre.index >= lo_) & (pre.index < hi_)
        yy = sv[m_] - sv[m_].mean()
        Ph = lombscargle(mid[m_], yy, w, normalize=True)
        halves[f"{lo_}-{hi_}"] = (float(periods[Ph.argmax()]), float(Ph.max()))
    R["period_lomb_scargle"] = dict(state_peak=(float(periods[P.argmax()]), float(P.max())), crms_peak=(float(periods[Pc.argmax()]), float(Pc.max())),
                                    null_q95_q99=np.quantile(null, [.95, .99]).tolist(), halves=halves)
    check("NEW 약 20초 주기(Lomb–Scargle 최고점 18~22초, 섞은 귀무 99% 초과)", 18 <= periods[P.argmax()] <= 22 and P.max() > np.quantile(null, .99), R["period_lomb_scargle"])
    log("NEW Lomb–Scargle:", R["period_lomb_scargle"])

    # (c) 기록-상태 동기화 검정의 검정력: 실제 기록에 무작위 위치 상태 전환(진폭 118↔207)을 넣어 1.3 초과 비율
    rngp = np.random.default_rng(0)
    det, tot, det_long, tot_long = 0, 0, 0, 0
    for s in L.index:
        x = cur[rows_of[s]]
        m_ = x.mean()
        fac = per_state[LOW]["amp"] / per_state[LOADED]["amp"] if L.loc[s, "state"] == LOADED else per_state[LOADED]["amp"] / per_state[LOW]["amp"]
        for _ in range(4):
            k = int(rngp.integers(1, len(x)))
            yv = x.copy(); yv[k:] = (x[k:] - m_) * fac + m_
            d_ = win_ratio(yv) > 1.3
            det += d_; tot += 1
            if len(x) >= 40:
                det_long += d_; tot_long += 1
    power = det / tot
    dur = (L.n.to_numpy() - 1) * .1
    p_str = np.minimum(1, 2 * dur / 20.5)
    R["sync_power"] = dict(power=power, power_len_ge40=det_long / tot_long, straddle_mean=float(p_str.mean()), expected_straddle=float(p_str.sum()),
                           expected_detected=float(p_str.sum() * power), observed=int((L.wr > 1.3).sum()),
                           poisson_p_zero=float(stats.poisson.pmf(0, p_str.sum() * power)))
    check("NEW 동기화 결론 유지(무작위 시각 기대 탐지 수 ≫ 0, 관측 0)", R["sync_power"]["expected_detected"] > 20 and R["sync_power"]["observed"] == 0, R["sync_power"])
    log("NEW 동기화 검정력:", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in R["sync_power"].items()})

    # (d) 연속 저수준 473~563 안의 짧은 기록
    short_in = [s for s in range(473, 564) if stn.loc[s, "n"] < 17]
    short_rms = {s: float(stn.loc[s, "crms_dm"]) for s in short_in}
    R["long_low_run_short_records"] = dict(n=len(short_in), lengths=[int(stn.loc[s, "n"]) for s in short_in], crms=short_rms,
                                           above_boundary=[s for s, v in short_rms.items() if v > boundary])
    log("NEW 473~563 안 짧은 기록:", len(short_in), "경계 초과:", R["long_low_run_short_records"]["above_boundary"],
        {s: round(v, 1) for s, v in short_rms.items()})

    # ===== 3. R2-D1 문구 정정·그림 =====
    rd = (EVID / "README.md").read_text(encoding="utf-8")
    rdl = rd.splitlines()
    pu = pd.read_csv(EVID / "production_unit_evidence.csv")
    s_trig = "0.6 Hz 위상에 맞춘 트리거가 아니다"
    s_unit = "기록 안(4.9초)에는 행정 정보가 없다. 기록 사이에는 약 20초 주기의 2수준 교대가 보이고"
    check("R2-D1⑥ production_unit_evidence.csv:2 트리거 문구 정정", s_trig in pu.iloc[0].interpretation and "사건 트리거" not in pu.iloc[0].interpretation, pu.iloc[0].interpretation)
    check("R2-D1⑥ production_unit_evidence.csv:5 생산단위 문구 정정·가설 표기", s_unit in pu.iloc[3].interpretation and "(가설)" in pu.iloc[3].interpretation
          and "복원할 수 없다" not in pu.iloc[3].interpretation and pu.iloc[3].basis == "관측·가설", (pu.iloc[3].interpretation, pu.iloc[3].basis))
    check("R2-D1⑥ README D4 표(177행) 트리거 문구", s_trig in rdl[176] and "기록 경계는 운전 상태 전환과 맞물린다" in rdl[176], rdl[176][:120])
    check("R2-D1⑥ README D4 결론(184행) 생산단위 문구", s_unit in rdl[183] and "(가설)" in rdl[183] and "0/469" in rdl[183], rdl[183][:120])
    check("R2-D1⑥ README 정상 운전변화 정의(131~136행) 세 요소", "2수준 교대" in rdl[131] and "연속 저수준 구간" in rdl[132] and "부하 수준 안 변동" in rdl[133]
          and "122~157" in rdl[133] and "가설" in rdl[135], [rdl[i][:60] for i in range(130, 136)])
    old_hits = []
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "yejun"], capture_output=True, text=True).stdout.splitlines()
    for rp in tracked:
        p = REPO / rp
        if not rp.endswith((".md", ".csv")) or "press_rubric_review" in p.parts or "expected" in p.parts or not p.exists():
            continue
        try:
            tx = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(tx.splitlines(), 1):
            if ("신호로도 복원" in line or "사건 트리거" in line or "시간 기반 수집" in line) and "→" not in line:
                old_hits.append(f"{p.relative_to(REPO)}:{i}")
    check("R2-D1⑥ 옛 결론 문구가 정정 기록 밖에 남지 않음", not old_hits, old_hits)
    rel = pd.read_csv(EVID / "sensor_relations.csv")
    for pair, key in (("AI0 SD~AI2 RMS", 0), ("AI1 SD~AI2 RMS", 1), ("AI0 SD~AI1 SD", 2)):
        note = rel[(rel.section == "구간 수준 결합") & (rel.subset == "normal") & (rel.pair == pair)].note.iloc[0]
        check(f"R2-D1⑤ sensor_relations 상태 안 값 {pair}", f"부하 {within[LOADED][key]:.3f}, 저수준 {within[LOW][key]:.3f}" in note, note[-90:])
    d_tab = pd.read_csv(EVID / "decision_table_diagnosis_v2.csv")
    check("R2-D1⑥ 결정표 2행 한계 칸(기록 안 전환 0/469, 가설, 인용)", "기록 안 전환 0/469" in d_tab.iloc[0].limitation and "(가설)" in d_tab.iloc[0].limitation
          and "operating_states_summary.csv:33" in d_tab.iloc[0].limitation, d_tab.iloc[0].limitation)
    # 그림
    figs = {}
    from PIL import Image
    for p in sorted((EVID / "figures").glob("*.png")):
        with Image.open(p) as im:
            figs[p.name] = dict(size=im.size, manifest_ok=dg_man["outputs"].get(f"yejun/analysis/press_evidence/figures/{p.name}") == sha_file(p))
    check("R2-D1⑦ 그림 5장·manifest 해시", len(figs) == 5 and all(v["manifest_ok"] for v in figs.values()), figs)
    check("R2-D1⑦ fig_d2c 정상 예시 5=부하(151.4)·480=저수준(85.0)", L.loc[5, "state"] == LOADED and L.loc[480, "state"] == LOW and L.loc[5, "n"] == 50 and L.loc[480, "n"] == 50
          and f"{L.loc[5, 'crms_dm']:.1f}" == "151.4" and f"{L.loc[480, 'crms_dm']:.1f}" == "85.0" and f"{L.loc[5, 'start']:%H:%M:%S}" == "00:00:39"
          and f"{L.loc[480, 'start']:%H:%M:%S}" == "01:00:50", (L.loc[5, ["state", "crms_dm"]].tolist(), L.loc[480, ["state", "crms_dm"]].tolist()))
    fp = (EVID / "figures.py").read_text(encoding="utf-8")
    check("R2-D1⑦ figures.py가 상태 수·상관을 표와 assert로 대조", fp.count("assert") >= 15 and "operating_states.csv" in fp and 'ost.loc[pick_n[0], "state"] == "부하"' in fp, fp.count("assert"))
    counts = st_all.value_counts().to_dict()
    check("R2-D1⑦ fig_d2a 범례 수(부하 260·저수준 209·짧은 131)", counts == {LOADED: 260, LOW: 209, SHORT: 131}, counts)

    # ===== 4. R2-D2 분할별 상태 구성·상태별 정상 알림(동결 모델·롤링 재적합) =====
    ssc = pd.read_csv(EVID / "split_state_composition.csv").set_index("part")
    parts = {"A 학습": (0, 360), "A 보정": (360, 480), "A 평가": (480, 600), "B 학습": (0, 300), "B 보정": (300, 420), "B 평가": (420, 600)}
    comp = {}
    for nm, (p0, p1) in parts.items():
        sub = L[(L.index >= p0) & (L.index < p1)]
        comp[nm] = (int((sub.state == LOW).sum()), len(sub))
        r_ = ssc.loc[nm]
        ok = int(r_.low) == comp[nm][0] and int(r_.records_len17) == comp[nm][1] and close(r_.low_share, comp[nm][0] / comp[nm][1], 1e-12) and all(
            int(r_[f"low_thr{th}"]) == int((sub.crms_dm < th).sum()) for th in (90, 92, 95))
        check(f"R2-D2 분할 구성 {nm}", ok, (comp[nm], r_.to_dict()))
    fisher = {}
    for sid in SPLITS:
        (lc, nc), (le, ne) = comp[f"{sid} 보정"], comp[f"{sid} 평가"]
        odds, p = stats.fisher_exact([[lc, nc - lc], [le, ne - le]])
        fisher[sid] = (float(p), float(odds))
        r_ = ssc.loc[f"{sid} 평가"]
        check(f"R2-D2 Fisher {sid}", close(p, r_.fisher_cal_vs_eval_p, 1e-9) and close(odds, r_.odds_ratio, 1e-12), (p, odds))
    sys.path.insert(0, str(GUARD))
    from model import GuardModel  # noqa: E402
    frozen = {sid: GuardModel.load(GUARD / "artifacts" / f"guard_{sid}.json") for sid in SPLITS}
    minp = {}
    fa = {}
    for sid, (tr_end, ca_end) in SPLITS.items():
        te = n[sn >= ca_end].reset_index(drop=True)
        pr = frozen[sid].predict(te, .01)
        mp = pr.groupby("record_id").p_value.min().fillna(1.0)
        minp[f"동결 {sid}"] = pd.Series(mp.to_numpy(), index=mp.index.to_numpy() + ca_end)
        fa[sid] = sorted(int(r) + ca_end for r in pr.loc[pr.alarm.eq(1), "record_id"].unique())
    check("R2-D2 동결 B 오경보 423·461·570, A 0건(재동결 모델)", fa["B"] == [423, 461, 570] and fa["A"] == [], fa)
    folds = []
    roll_ref = pd.read_csv(GUARD / "outputs" / "rolling.csv")
    for end in (180, 240, 300, 360, 420):
        trn = n[sn < end].reset_index(drop=True)
        ca = n[(sn >= end) & (sn < end + 120)].reset_index(drop=True)
        te = n[(sn >= end + 120) & (sn < end + 180)].reset_index(drop=True)
        mdl = GuardModel.fit(trn, ca, split=f"train_to_{end}")
        mp = mdl.predict(te, .01).groupby("record_id").p_value.min().fillna(1.0)
        same_as = [sid for sid, fm in frozen.items() if np.array_equal(fm.cal, mdl.cal) and np.array_equal(fm.coef, mdl.coef) and np.array_equal(fm.mean, mdl.mean)]
        folds.append(dict(fold=f"normal_{end + 120}_{end + 179}", end=end, n_cal=len(mdl.cal), minp=pd.Series(mp.to_numpy(), index=mp.index.to_numpy() + end + 120),
                          same=same_as[0] if same_as else ""))
    for f in folds:
        for alpha in (.01, .03, .05):
            r_ = roll_ref[roll_ref.split.eq(f["fold"]) & roll_ref.model.eq("guard_v2") & np.isclose(roll_ref.alpha, alpha)].iloc[0]
            check(f"O1a {f['fold']} α={alpha} = rolling.csv", int((f["minp"] <= alpha).sum()) == int(r_.normal_notified_segments), (int((f["minp"] <= alpha).sum()), r_.normal_notified_segments))
        check(f"O1a {f['fold']} 동결 모델과 같음", f["same"] == {300: "B", 360: "A"}.get(f["end"], ""), f["same"])
    minp["독립 롤링 3겹"] = pd.concat([f["minp"] for f in folds if not f["same"]])
    minp["롤링 5겹 전체"] = pd.concat([f["minp"] for f in folds])
    nab = pd.read_csv(EVID / "normal_alarms_by_state.csv")
    state = L.state
    alarm_tab = {}
    for group, mp in minp.items():
        stt = state.reindex(mp.index).fillna(SHORT)
        for alpha in (.01, .03, .05):
            for g in (LOADED, LOW, SHORT):
                m_ = stt == g
                x_, n_ = int((mp[m_] <= alpha).sum()), int(m_.sum())
                alarm_tab[(group, alpha, g)] = (x_, n_)
                r_ = nab[nab.section.eq("상태별 정상 알림") & nab.group.eq(group) & np.isclose(nab.alpha, alpha) & nab.state.eq(g)]
                check(f"R2-D2 상태별 알림 {group} α={alpha} {g}", len(r_) == 1 and int(r_.alerted.iloc[0]) == x_ and int(r_.records.iloc[0]) == n_, (x_, n_, r_[["alerted", "records"]].values.tolist()))
    pooled = pd.concat([minp["동결 A"], minp["동결 B"], minp["독립 롤링 3겹"]])
    for thr in (90.0, 95.0):
        stt = pd.Series(np.where(L.crms_dm < thr, LOW, LOADED), index=L.index).reindex(pooled.index).fillna(SHORT)
        for alpha in (.01, .03, .05):
            for g in (LOADED, LOW, SHORT):
                m_ = stt == g
                r_ = nab[nab.section.eq(f"경계 {thr:g} 민감도(동결 A·B + 독립 3겹)") & np.isclose(nab.alpha, alpha) & nab.state.eq(g)]
                check(f"R2-D2 경계 {thr:g} 민감도 α={alpha} {g}", int(r_.alerted.iloc[0]) == int((pooled[m_] <= alpha).sum()) and int(r_.records.iloc[0]) == int(m_.sum()))
    # 성분 수를 바꿔도(k=4, 저수준 대 그 밖) 모든 알림이 저수준 밖인가
    low4 = pd.Series(np.where(L.c4 == 0, LOW, LOADED), index=L.index)
    alarms_low_k4 = sum(int(((mp <= al) & (low4.reindex(mp.index).fillna(SHORT) == LOW)).sum()) for mp in (minp["동결 A"], minp["동결 B"], minp["독립 롤링 3겹"]) for al in (.01, .03, .05))
    check("NEW k=4 저수준에서도 정상 알림 0", alarms_low_k4 == 0, alarms_low_k4)
    # 알림이 난 기록의 k=4 성분
    alarm_c4 = {}
    for grp in ("동결 B", "독립 롤링 3겹", "동결 A"):
        mp = minp[grp]
        for al in (.01, .03, .05):
            hit = mp.index[(mp <= al).to_numpy()]
            alarm_c4[f"{grp}|{al}"] = {int(h): (int(L.loc[h, "c4"]) if h in L.index else "short") for h in hit}
    R["alarm_records_k4_class"] = alarm_c4
    log("NEW 알림 기록의 k=4 성분(0 저수준·1 약 102·2 약 141·3 약 172):", alarm_c4)
    cal_idx = np.arange(300, 420)
    calB = pd.Series(frozen["B"].cal, index=cal_idx)
    cst = state.reindex(cal_idx).fillna(SHORT)
    top10 = cst[calB.sort_values(ascending=False).index[:10]].value_counts().to_dict()
    mw = stats.mannwhitneyu(calB[cst == LOADED], calB[cst == LOW], alternative="greater")
    r_ = nab[nab.group.eq("동결 B 보정 120구간")].iloc[0]
    check("R2-D2 B 보정 상위 10개 모두 부하·MWU p=0.0024", top10 == {LOADED: 10} and int(r_.alerted) == 10 and close(mw.pvalue, r_.p_value, 1e-9), (top10, mw.pvalue))
    nl_cal = int((cst == LOADED).sum())
    stB = state.reindex(minp["동결 B"].index).fillna(SHORT)
    xB, nB = int(((minp["동결 B"] <= .01) & (stB == LOADED)).sum()), int((stB == LOADED).sum())
    bp = float(stats.binomtest(xB, nB, 1 / (nl_cal + 1), alternative="greater").pvalue)
    r_ = nab[nab.group.eq("동결 B 평가 부하 기록(α 1%)")].iloc[0]
    check("R2-D2 B 부하 3/51 대 1/62 이항 p=0.049", (xB, nB, nl_cal) == (3, 51, 61) and int(r_.alerted) == 3 and int(r_.records) == 51 and close(r_.value, 1 / 62, 1e-12) and close(bp, r_.p_value, 1e-9),
          (xB, nB, nl_cal, bp))
    R["R2_D2"] = dict(comp=comp, fisher=fisher, alarms={f"{k[0]}|{k[1]}|{k[2]}": v for k, v in alarm_tab.items()}, calB_top10=top10, mw_p=float(mw.pvalue),
                      binom=(xB, nB, nl_cal, bp), false_alarms=fa)
    log("R2-D2 comp:", comp, "fisher:", fisher)
    log("R2-D2 alarms α=1%:", {k: v for k, v in R["R2_D2"]["alarms"].items() if "|0.01|" in k})
    log("R2-D2 calB top10:", top10, "MWU p", round(mw.pvalue, 5), "binom", (xB, nB, nl_cal, round(bp, 4)))
    # 문서 반영
    check("R2-D2④ README R1 결론(32행) 분모", "A의 0/120은 부하 기록 21개, B의 3/180은 부하 기록 51개" in rdl[31] and "A 78% 대 35%, B 65% 대 32%" in rdl[31], rdl[31][:120])
    lim14 = d_tab.iloc[12].limitation
    check("R2-D2④ 결정표 14행 한계 칸", d_tab.iloc[12]["item"] == "A/B·시간순 분할" and "A 보정 33/94(35%)·평가 75/96(78%)" in lim14 and "B 보정 29/90(32%)·평가 94/145(65%)" in lim14
          and "A 0/120은 부하 기록 21개" in lim14 and "B 3/180은 부하 기록 51개" in lim14, lim14)
    check("R2-D2 사후 분석 표기", "사후 분석" in rdl[31] and "사후 기술 통계" in rd and "사후 분석" in rdl[328], rdl[328][:80])

    # ===== 5. R2-D3 결정표 블록 부트스트랩 행 =====
    ub = pd.read_csv(GUARD / "outputs" / "uncertainty_v2.csv")
    row16 = d_tab.iloc[14]
    cites16 = re.findall(r"(yejun/[^\s;:()]+):(\d+(?:[-,]\d+)*)", row16.evidence)
    lines16 = {f"{p}:{sp}": [read_line(REPO / p, i) for i in expand_span(sp)] for p, sp in cites16}
    okv2 = all(l.split(",")[2] == "v2" for ls in lines16.values() for l in ls)
    subA = ub[ub.split_id.eq("A") & ub.model.eq("v2") & np.isclose(ub.alpha, .01) & ub.side.eq("normal") & ub.statistic.eq("notified_segments")]
    subB = ub[ub.split_id.eq("B") & ub.model.eq("v2") & np.isclose(ub.alpha, .01) & ub.side.eq("normal") & ub.statistic.eq("notified_segments")]
    txtB = "·".join(f"{r.boot_p2_5:g}~{r.boot_p97_5:g}" for r in subB.itertuples())
    check("R2-D3 블록 부트스트랩 행이 v2 행을 인용", row16["item"] == "블록 부트스트랩" and okv2 and len(cites16) == 2
          and [c for c in lines16] == ["yejun/press_guard/outputs/uncertainty_v2.csv:23-25", "yejun/press_guard/outputs/uncertainty_v2.csv:65-67"], lines16)
    check("R2-D3 값: A 관측 0(퇴화), B 관측 3(95% 0~6·0~6·0~5)", (subA.observed == 0).all() and (subA.boot_p97_5 == 0).all() and (subB.observed == 3).all()
          and txtB == "0~6·0~6·0~5" and f"B 관측 3(95% {txtB})" in row16.evidence and "A 관측 0(퇴화" in row16.evidence, (txtB, row16.evidence[:140]))

    # ===== 6. 결정표 인용 41개 =====
    token = {
        "gaps.csv:2": "normal,", "model.py:85": "def alert_units", "operating_states_summary.csv:33": "진폭 비 1.3 초과 기록",
        "variable_dictionary.csv:7": "Equipment_state,", "label_bypass.csv:2": "timestamps_shifted_5_days", "segment_rule_tolerance.csv:7": "normal,0.099,",
        "README.md:31": "잘못된 행", "test_guard.py:58": "def test_invalid_reset_and_no_false_normal", "duplicate_rows.csv:2": "00:43:33.196",
        "gaps.csv:3": "abnormal,", "outliers.csv:5": "어느 센서든", "outlier_rules.csv:8": "진동 두 센서 중 하나라도", "diagnosis.md:43": "| either | matched |",
        "random_rows.csv:10": "decimal_digits(AI0)", "model.py:232": "def fit", "model.py:267": "np.where(pos < 7",
        "ablation_v2.csv:26": "no_early_switch,recording_segments,conformal,0.01", "ar2_oscillator.csv:2": "A,",
        "ablation_v2.csv:20": "no_dynamics,recording_segments,conformal,0.01", "imbalance.csv:3": "A 평가",
        "grouped_records.csv:30": "A,window_plus_v2,logistic,21fold,conformal", "splits.csv:2": "A,normal_60_20_20,train",
        "rolling_calibration_curve.csv:4": "normal_420_479", "split_state_composition.csv:4": "A 평가,",
        "normal_alarms_by_state.csv:11": "상태별 정상 알림,동결 B,0.01,부하", "calibration_curve.csv:14": "B,1,", "rolling_calibration_curve.csv:7": "합산(5겹)",
        "uncertainty_v2.csv:23": "A,normal_60_20_20,v2,0.01,normal,notified_segments,5", "uncertainty_v2.csv:24": "A,normal_60_20_20,v2,0.01,normal,notified_segments,10",
        "uncertainty_v2.csv:25": "A,normal_60_20_20,v2,0.01,normal,notified_segments,20", "uncertainty_v2.csv:65": "B,normal_50_20_30,v2,0.01,normal,notified_segments,5",
        "uncertainty_v2.csv:66": "B,normal_50_20_30,v2,0.01,normal,notified_segments,10", "uncertainty_v2.csv:67": "B,normal_50_20_30,v2,0.01,normal,notified_segments,20",
        "e1_detection_floor.csv:7": "cur_noise,guard_v2", "e2_uci_metrics.csv:2": "local_normal_reference,3,v2_4ch", "e3_stability.csv:2": "0.01,15,99,"}
    n_cite, bad = 0, []
    for _, r_ in d_tab.iterrows():
        text = " ".join(str(r_[k]) for k in ("evidence", "limitation", "alternative_and_result", "decision"))
        for path, span in re.findall(r"(yejun/[^\s;:()]+):(\d+(?:[-,]\d+)*)", text):
            n_cite += 1
            for i in expand_span(span):
                key = f"{Path(path).name}:{i}"
                tok = token.get(key)
                if tok is None and "guidebook_protocol_vs_records.csv" in path:
                    tok = r_["item"].split("(")[0]
                line = read_line(REPO / path, i) or ""
                if tok is None or tok not in line:
                    bad.append((key, r_["item"], line[:80]))
    check("S6 결정표 인용 41개가 모두 의도한 행", n_cite == 41 and not bad, (n_cite, bad))
    per_row = {int(i + 2): len(re.findall(r"yejun/[^\s;:()]+:\d+", str(r_.evidence))) for i, r_ in d_tab.iterrows()}
    check("S6 결정표 모든 행이 근거 칸에 인용 1개 이상", min(per_row.values()) >= 1 and len(d_tab) == 27, per_row)
    R["decision_table"] = dict(rows=len(d_tab), citations=n_cite, bad=bad)
    log("S6 decision table rows", len(d_tab), "citations", n_cite, "bad", bad)

    # ===== 7. 1회차 항목 회귀(D1·D4·D5·D6·D3 가이드북·O4·O1a) =====
    res1 = {}
    for sub, f in raw.items():
        for tr_name, x in (("원값", f[SENS]), ("절댓값(가이드북 코드 14)", f[SENS].abs())):
            c = x.corr()
            for p1, p2, lab in (("AI0_Vibration", "AI1_Vibration", "AI0~AI1"), ("AI0_Vibration", "AI2_Current", "AI0~AI2"), ("AI1_Vibration", "AI2_Current", "AI1~AI2")):
                v = float(c.loc[p1, p2])
                row = rel[(rel.section == "행 상관") & (rel.subset == sub) & (rel["transform"] == tr_name) & (rel.pair == lab)]
                check(f"D1 행 상관 {sub} {tr_name} {lab}", len(row) == 1 and close(v, row.value.iloc[0], 1e-12), (v, row.value.tolist()))
                res1[f"{sub}|{tr_name}|{lab}"] = v
    for sub, LL in (("normal", Ln), ("abnormal", La)):
        for xa, xb, lab in (("sd0", "crms_dm", "AI0 SD~AI2 RMS"), ("sd1", "crms_dm", "AI1 SD~AI2 RMS"), ("sd0", "sd1", "AI0 SD~AI1 SD")):
            r, p = stats.spearmanr(LL[xa], LL[xb])
            row = rel[(rel.section == "구간 수준 결합") & (rel.subset == sub) & (rel.pair == lab)]
            check(f"D1 구간 결합 {sub} {lab}", len(row) == 1 and close(r, row.value.iloc[0], 1e-12) and close(p, row.p_value.iloc[0], 1e-6), (r, p))
            res1[f"{sub}|{lab}"] = dict(rho=r, p=p, n=len(LL))
    ov = pd.read_csv(EVID / "operating_variation.csv")
    med = Ln[["crms_raw", "sd0", "sd1"]].median()
    mine = []
    for b, g in Ln.groupby(Ln.start.dt.floor("10min")):
        mine.append(dict(block_start=f"{b:%H:%M}", current_rms_rel=float(g.crms_raw.median() / med.crms_raw), AI0_sd_rel=float(g.sd0.median() / med.sd0), AI1_sd_rel=float(g.sd1.median() / med.sd1)))
    mine = pd.DataFrame(mine)
    check("D1 operating_variation 8블록", len(mine) == len(ov) and all(np.allclose(mine[c], ov[c], rtol=0, atol=1e-9) for c in ("current_rms_rel", "AI0_sd_rel", "AI1_sd_rel")))
    fal = pd.read_csv(EVID / "false_alarm_operating_level.csv").set_index("segment")
    lv = {}
    for s in fa["B"]:
        r_ = stn.loc[s]
        pct = {k: float((stn[k] < r_[k]).mean()) for k in ("sd0", "sd1", "crms_dm")}
        lv[s] = dict(AI0_top=1 - pct["sd0"], cur_top=1 - pct["crms_dm"], state=str(st_all.get(s)), c4=int(L.loc[s, "c4"]) if s in L.index else None)
        check(f"D1 오경보 운전 수준 {s}", close(pct["sd0"], fal.loc[s, "AI0_sd_pct"], 1e-12) and close(pct["crms_dm"], fal.loc[s, "current_rms_pct"], 1e-12))
    R["D1_false_alarm_levels"] = lv
    log("D1 B false alarm levels/state:", lv)
    # D4
    sine = {k: sine_grid(raw[k].AI2_Current.to_numpy(float), seg[k]) for k in raw}
    fn_ = sine["normal"]
    at06 = fn_[np.isclose(fn_.f, 0.6)]
    ph = np.array([np.arctan2(*fit_sine(cur[r_.start_row:r_.start_row + r_.length], .6)[[1, 0]]) for r_ in at06.itertuples()])
    rb, rp = rayleigh(ph)
    pos = pd.Series(sn).groupby(sn).cumcount().to_numpy()
    zmax = np.abs((n[VIB].to_numpy(float) - muV) / sdV).max(1)
    groups = [zmax[(pos // 5) == b] for b in range(10)]
    prof = [float(g.mean()) for g in groups]
    kw = stats.kruskal(*groups).pvalue
    full = fn_[(fn_.length == 50) & np.isclose(fn_.f, .6)]
    segs50 = [cur[r_.start_row:r_.start_row + 50] for r_ in full.itertuples()]
    gain = np.array([harmonic_r2(x, .6, 3) - harmonic_r2(x, .6, 1) for x in segs50])
    ratio50 = np.array([np.hypot(*fit_sine(x[25:], .6)[:2]) / np.hypot(*fit_sine(x[:25], .6)[:2]) for x in segs50])
    exact9 = total = 0
    spans = []
    for k, f in raw.items():
        dt = t[k].diff().dt.total_seconds().to_numpy()[1:]
        wi = seg[k][1:] == seg[k][:-1]
        exact9 += int((np.abs(dt[wi] - .1) <= 1e-9).sum()); total += int(wi.sum())
        lens = pd.Series(seg[k]).value_counts()
        for s in lens[lens == 50].index:
            tt = t[k][seg[k] == s]
            spans.append((tt.iloc[-1] - tt.iloc[0]).total_seconds())
    spans = np.asarray(spans)
    mine_pu = [(rb, rp, len(at06)), (min(prof), max(prof), len(n)), (float(np.median(gain)), float(np.quantile(gain, .95)), len(full)),
               (float(np.median(ratio50)), f"{np.quantile(ratio50, .05):.3f}~{np.quantile(ratio50, .95):.3f}", len(full)),
               (exact9, total, total), (float(spans.min()), float(spans.max()), len(spans))]
    for i, (v1, v2, nn) in enumerate(mine_pu):
        r_ = pu.iloc[i]
        ok2 = (str(v2) == str(r_.value2)) if isinstance(v2, str) else close(v2, r_.value2, 1e-9)
        check(f"D4 {r_['item']}", close(v1, r_.value, 1e-9) and ok2 and int(r_.n) == nn, (v1, v2, nn, r_.value, r_.value2, r_.n))
    check("D4 앨리어싱 일반형 k·10 ± 0.6 Hz", "k·10 ± 0.6 Hz" in pu.iloc[6].reference and close(pu.iloc[6].value, 6.06 / 60, 1e-12))
    # O4(a) 관측 성질(새 열 포함)
    obs = pd.read_csv(EVID / "observability.csv")
    obs_new = {}
    for k, f in raw.items():
        same_ = np.r_[False, seg[k][1:] == seg[k][:-1]]
        for c in SENS:
            x = f[c].to_numpy(float)
            lag = float(np.corrcoef(x[1:][same_[1:]], x[:-1][same_[1:]])[0, 1])
            Pw, lagr = [], []
            for r in np.unique(seg[k]):
                idx = np.flatnonzero(seg[k] == r)
                if len(idx) < 20:
                    continue
                v = x[idx[:20]] - x[idx[:20]].mean()
                Pw.append(np.abs(np.fft.rfft(v)) ** 2)
                wv = x[idx] - x[idx].mean()
                lagr.append(float(np.corrcoef(wv[1:], wv[:-1])[0, 1]))
            Pw = np.mean(Pw, 0)
            fq = np.fft.rfftfreq(20, .1)
            share = float(Pw[(fq > 0) & (fq <= 1.0)].sum() / Pw[fq > 0].sum())
            xm = x - pd.Series(x).groupby(seg[k]).transform("mean").to_numpy()
            lmr = float(np.corrcoef(xm[1:][same_[1:]], xm[:-1][same_[1:]])[0, 1])
            gt5 = int(np.sum(np.asarray(lagr) > .5))
            r_ = obs[(obs.file == k) & (obs.sensor == c)].iloc[0]
            ok = (close(x.mean(), r_["mean"], 1e-9) and close(lag, r_.lag1_within, 1e-9) and close(share, r_.share_power_le_1hz, 1e-9)
                  and close(lmr, r_.lag1_mean_removed, 1e-9) and int(r_.records_ge20) == len(lagr) and int(r_.records_lag1_gt_0_5) == gt5)
            check(f"O4a 관측 성질 {k} {c}", ok, (lag, share, lmr, len(lagr), gt5))
            obs_new[f"{k}|{c}"] = dict(lag1=lag, share_le_1hz=share, lag1_mean_removed=lmr, records_ge20=len(lagr), gt_0_5=gt5)
    R["O4a_observability"] = obs_new
    log("O4a 1 Hz 이하 비중·lag-1:", {k: (round(v["share_le_1hz"], 3), round(v["lag1_mean_removed"], 3), v["gt_0_5"], v["records_ge20"]) for k, v in obs_new.items()})
    # D5
    vmax_n = pd.Series(zmax).groupby(sn).max()
    thr99 = float(vmax_n[vmax_n.index >= 360].quantile(.99))
    r2min = float(fn_.r2.min())
    zmax_a = np.abs((a[VIB].to_numpy(float) - muV) / sdV).max(1)
    vmax_a = pd.Series(zmax_a).groupby(sa).max()
    ab = pd.read_csv(EVID / "abnormal_segments.csv").set_index("segment")
    fa_ = sine["abnormal"]
    kinds = {}
    for s in range(21):
        r2v = float(fa_.r2.get(s, np.nan))
        vo, ro = bool(vmax_a[s] > thr99), bool(np.isfinite(r2v) and r2v < r2min)
        kinds[s] = "진동·파형 모두" if vo and ro else ("진동만" if vo else ("파형만" if ro else "없음"))
        check(f"D5 이상 구간 {s}", close(vmax_a[s], ab.loc[s, "vib_segmax_z"], 1e-9) and kinds[s] == ab.loc[s, "outside_normal"])
    # D6
    orl = pd.read_csv(EVID / "outlier_rules.csv")
    uni = [np.zeros((~trA).sum(), bool), np.zeros(len(a), bool)]
    for c in VIB:
        x, yv = n[c].to_numpy(float), a[c].to_numpy(float)
        q1, q3 = np.percentile(x[trA], [25, 75])
        lo_, hi_ = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
        uni[0] |= ((x < lo_) | (x > hi_))[~trA]; uni[1] |= (yv < lo_) | (yv > hi_)
    r_ = orl[(orl.rule == "1.5×IQR") & orl.sensor.str.startswith("진동")].iloc[0]
    check("D6 1.5×IQR 진동 합집합 206·246", int(r_.normal_nontrain_rows) == int(uni[0].sum()) == 206 and int(r_.abnormal_rows) == int(uni[1].sum()) == 246)
    # D3 가이드북 대비
    gp = pd.read_csv(EVID / "guidebook_protocol_vs_records.csv")
    idx = np.arange(len(n) - 121)
    tt = t["normal"].to_numpy()
    lead = (tt[idx + 120] - tt[idx + 19]) / np.timedelta64(1, "s")
    mine_gp = [f"구간 {sn[15000]}의 {pos[15000] + 1}번째 행({t['normal'][15000]:%H:%M:%S.%f}"[:-3] + ")", f"{((sn[idx + 19] - sn[idx]) > 0).mean():.1%}",
               f"{((sn[idx + 120] - sn[idx + 19]) > 0).mean():.1%}", f"중앙 {np.median(lead):.1f}초(5~95% {np.quantile(lead, .05):.1f}~{np.quantile(lead, .95):.1f}초)"]
    for i, v in enumerate(mine_gp):
        check(f"D3 가이드북 대비 {i + 2}행", v == gp.iloc[i].value, (v, gp.iloc[i].value))
    # O4(b) 위상
    tsec = (t["normal"] - t["normal"].iloc[0]).dt.total_seconds().to_numpy()

    def phase_abs(ix_list, f):
        out = np.empty(len(ix_list))
        for i, ix in enumerate(ix_list):
            A = np.column_stack([np.cos(2 * np.pi * f * tsec[ix]), np.sin(2 * np.pi * f * tsec[ix]), np.ones(len(ix))])
            cc = np.linalg.lstsq(A, cur[ix], rcond=None)[0]
            out[i] = np.arctan2(cc[1], cc[0])
        return out
    pairs = [(rows_of[s][-20:], rows_of[s + 1][:20]) for s in ids[:-1] if len(rows_of[s]) >= 20 and len(rows_of[s + 1]) >= 20]
    d = phase_abs([p_[1] for p_ in pairs], .6) - phase_abs([p_[0] for p_ in pairs], .6)
    pc = pd.read_csv(EVID / "phase_continuity.csv")
    check("O4b 이웃 기록 R 0.060(355쌍)", int(pc.iloc[1].pairs) == len(d) == 355 and close(resultant(d), pc.iloc[1].R, 1e-9), (len(d), resultant(d)))
    # O1a 합산
    rc = pd.read_csv(EVID / "rolling_calibration_curve.csv")
    pooled_k = {}
    for k in (1, 3, 6, 12):
        x_ = sum(int((f["minp"] <= k / (f["n_cal"] + 1) + 1e-12).sum()) for f in folds)
        pooled_k[k] = x_
        check(f"O1a 합산 k={k}", x_ == int(rc[(rc.fold == "합산(5겹)") & (rc.k == k)].alerted.iloc[0]), x_)
    log("O1a pooled:", pooled_k)

    # ===== 8. README 수치(진단 보강 2 절과 수정된 문장) =====
    uminus = lambda v, d_=3: (f"{v:.{d_}f}" if v >= 0 else f"−{abs(v):.{d_}f}")
    tok = [f"{bic[1]:.1f} / −{abs(bic[2]):.1f} / −{abs(bic[3]):.1f}", f"전류 RMS {boundary:.1f}(골 88~95)", f"{float(ctr[0]):.1f}으로 흔들려",
           f"{per_state[LOW]['n']}기록, 전류 RMS 중앙 {per_state[LOW]['crms']:.1f}(로그 SD {low_sd:.3f}), 0.6 Hz 진폭 {per_state[LOW]['amp']:.0f}, AI0 SD {per_state[LOW]['sd0']:.3f}, AI1 SD {per_state[LOW]['sd1']:.3f}",
           f"{per_state[LOADED]['n']}기록, 전류 RMS 중앙 {per_state[LOADED]['crms']:.1f}, 진폭 {per_state[LOADED]['amp']:.0f}({ratio:.2f}배), AI0 SD {per_state[LOADED]['sd0']:.3f}, AI1 SD {per_state[LOADED]['sd1']:.3f}",
           f"{agree:.1%} 일치", f"시차 18~24초에서 +{lagc[18][0]:.2f}, 36~42초에서 +{lagc[36][0]:.2f}", f"(중앙 {np.median(iv):.1f}초)",
           f"최대 {q[-1]:.3f}, 1.3 초과 0/469", f"(중앙 {gapb[chg].median():.2f}초 대 {gapb[same].median():.2f}초, p={mw_gap:.2f})",
           f"01:00~01:12(구간 {int(longest['first'])}~{int(longest['last'])})에 저수준 {int(longest.len)}기록",
           f"부하: AI1 SD~전류 {within[LOADED][1]:.3f}, AI0 {within[LOADED][0]:.3f}. 저수준: {uminus(within[LOW][1], 2)}, {uminus(within[LOW][0], 3)}",
           f"{comp['A 학습'][0]}/{comp['A 학습'][1]} (36%)", f"**{comp['A 평가'][0]}/{comp['A 평가'][1]} (78%)**", f"**{comp['B 평가'][0]}/{comp['B 평가'][1]} (65%)**",
           f"{fisher['A'][0]:.1e}".replace("e-09", "e-9"), f"{fisher['B'][0]:.1e}".replace("e-06", "e-6"),
           "| 동결 A | " + "·".join(str(alarm_tab[("동결 A", al, LOADED)][0]) for al in (.01, .03, .05)) + f" / {alarm_tab[('동결 A', .01, LOADED)][1]} | 0 / {alarm_tab[('동결 A', .01, LOW)][1]} | 0 / {alarm_tab[('동결 A', .01, SHORT)][1]} |",
           "| 동결 B | " + "·".join(str(alarm_tab[("동결 B", al, LOADED)][0]) for al in (.01, .03, .05)) + f" / {alarm_tab[('동결 B', .01, LOADED)][1]} | 0 / {alarm_tab[('동결 B', .01, LOW)][1]} | 0 / {alarm_tab[('동결 B', .01, SHORT)][1]} |",
           "| 동결과 독립인 롤링 3겹 | " + "·".join(str(alarm_tab[("독립 롤링 3겹", al, LOADED)][0]) for al in (.01, .03, .05)) + f" / {alarm_tab[('독립 롤링 3겹', .01, LOADED)][1]} | 0 / {alarm_tab[('독립 롤링 3겹', .01, LOW)][1]} |",
           f"p={mw.pvalue:.4f}", f"{xB}/{nB}({xB / nB:.1%})", f"1/{nl_cal + 1}", f"p={bp:.3f}",
           f"부하(전류 RMS 중앙 {per_state[LOADED]['crms']:.1f}, 0.6 Hz 진폭 {per_state[LOADED]['amp']:.0f})와 저수준({per_state[LOW]['crms']:.1f}, {per_state[LOW]['amp']:.0f})",
           f"{lm.min():.0f}~{lm.max():.0f}", f"0.735 ({len(Ln)}구간; 상태 안 부하 {within[LOADED][0]:.3f}·저수준 {uminus(within[LOW][0])})",
           f"0.865 (상태 안 부하 {within[LOADED][1]:.3f}·저수준 {uminus(within[LOW][1])})",
           f"{obs_new['abnormal|AI0_Vibration']['lag1']:.3f}·{obs_new['abnormal|AI1_Vibration']['lag1']:.3f}",
           f"{obs_new['abnormal|AI0_Vibration']['lag1_mean_removed']:.3f}·{obs_new['abnormal|AI1_Vibration']['lag1_mean_removed']:.3f}",
           f"기록 {obs_new['abnormal|AI0_Vibration']['records_ge20']}개 중 {obs_new['abnormal|AI0_Vibration']['gt_0_5']}·{obs_new['abnormal|AI1_Vibration']['gt_0_5']}개",
           f"{obs_new['abnormal|AI0_Vibration']['share_le_1hz']:.2f}·{obs_new['abnormal|AI1_Vibration']['share_le_1hz']:.2f}로, 정상({obs_new['normal|AI0_Vibration']['share_le_1hz']:.2f}·{obs_new['normal|AI1_Vibration']['share_le_1hz']:.2f})",
           f"R̄ {rb:.3f}, Rayleigh p={rp:.2f}", f"{min(prof):.3f}~{max(prof):.3f}, Kruskal–Wallis p={kw:.2f}", "19,979개", "모두 4.900초",
           f"q99({thr99:.2f})", f"({r2min:.4f})", "206 (2.6%)", "**246 (41%)**", f"{pooled_k[1]} (0.67%)", f"{pooled_k[12]} (9.33%)",
           f"{res1['normal|원값|AI0~AI1']:+.3f}", "상위 2.7%·3.0%, 전류 RMS 상위 4.5%·7.5%", "p=2.9e-11"]
    miss = [x for x in tok if x not in rd]
    check("S8 README 수치(보강 1·2 절)가 재계산과 일치", not miss, miss)
    R["readme_tokens"] = dict(checked=len(tok), missing=miss)
    log("S8 README tokens checked:", len(tok), "missing:", miss)
    gr = (GUARD / "README.md").read_text(encoding="utf-8")
    for s_ in ("12/120", "p=2.9e-11", "420~479 폴드는 B와, 480~539 폴드는 A와", "오경보 근거로 합산하지 않는다", "300~359·360~419·540~599 3개이고 모두 0/60"):
        check(f"S8 press_guard README '{s_}'", s_ in gr)
    R["press_guard_readme_mentions_loaded_denominator"] = ("부하 기록" in gr) or ("operating_states" in gr) or ("normal_alarms_by_state" in gr)
    R["press_evidence_R2_line41"] = rdl[40]
    log("press_guard README가 부하 기록 분모를 언급하는가:", R["press_guard_readme_mentions_loaded_denominator"])
    log("press_evidence README 41행:", rdl[40])

    # ===== 마무리 =====
    head_end = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    R["head_at_end"] = head_end
    R["checks"] = dict(total=len(CHECKS), failed=[c for c in CHECKS if not c["ok"]])
    R["elapsed_s"] = time.monotonic() - t_start
    log(f"HEAD end {head_end}")
    log(f"checks: {len(CHECKS)} total, {len(R['checks']['failed'])} failed")
    OUT_JSON.write_text(json.dumps(jsonable(R), ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.append(f"wrote {OUT_JSON.name} ({R['elapsed_s']:.1f}s)")
    OUT_LOG.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(LOG[-1])


if __name__ == "__main__":
    main()
