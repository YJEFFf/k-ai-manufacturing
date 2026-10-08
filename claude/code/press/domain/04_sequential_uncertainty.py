"""R1(사건 지속)을 표준 순차 검출(CUSUM·EWMA)과 비교하고, 최종 모델 결과의 불확실성과 경보 운영 지표를 낸다.

입력: tvt 캐시 rows_{A,B}.pkl, tvt 잠금 산출물(tvt_selection.json·tvt_scores_meta.json·test_predictions_{A,B}.csv). 읽기만 한다.
출력: outputs/04_sequential_uncertainty.json · .csv(비교 표) · _grid.csv(검증 격자) · _delays.csv(첫 경보 지연) · _ops.csv(운영 지표) · _summary.md
보고서 2.4·2.5절의 근거. test 채점 이후의 사후 분석이라 잠금 선택(v2+R1)과 최종 모델(v2+R1+R2) 결정에는 영향이 없다.
실행: PYTHONIOENCODING=utf-8 python 04_sequential_uncertainty.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.dont_write_bytecode = True          # tvt/ 폴더에 캐시 파일을 새로 쓰지 않는다
HERE = Path(__file__).resolve().parent
TVT = HERE.parent / "tvt"
sys.path.insert(0, str(TVT))
from lib import CACHE, GAP_S, PRIMARY_ALPHA, SPLITS, f1_counts, sha256_file, stream_rules  # noqa: E402
from lib import OUT as TVT_OUT  # noqa: E402
from evalcore import candidates, own_alarm, predict_rows  # noqa: E402

OUT = HERE / "outputs"
STEM = "04_sequential_uncertainty"
ALPHAS = (0.01, 0.03, 0.05)
ROW_S = 0.1                                  # 표본 간격(초)
CUSUM_K = (0.5, 1.0, 1.5, 2.0, 3.0, 5.0)     # v2 점수 단위(-log10). 검증 정상 평균 μ0 ≈ 0.84
EWMA_L = (0.1, 0.2, 0.3, 0.5)
TIE = 0.002                                  # tvt 선택 규칙과 같은 동률 폭
N_BOOT = 10_000
SEED = 0
SPLICE_GAP_S = 5.0                           # 가상 접합 간격(60초 안이면 이어짐). 이상 기록 사이 간격 중앙값 ≈ 5.35초
REF = {"v2": "v2", "v2+H1": "v2+R1", "v2+H1+H2": "v2+R1+R2(최종)"}   # 코드 이름 H1·H2 = 보고서의 R1·R2
N_CAL = 120                                  # α 격자를 정하는 검증 정상 기록 수


# ---------------------------------------------------------------- 보정(팀 레포와 같은 식)
def conformal_p(cal_values: np.ndarray, scores: np.ndarray) -> np.ndarray:
    """conformal p = (1 + #{보정값 ≥ s}) / (n + 1). 팀 레포 press/calibrate.py와 같은 식."""
    ref = np.sort(np.where(np.isfinite(cal_values), cal_values, -np.inf))   # NaN 등은 -inf로 둬 어떤 점수보다 작게 센다
    out = np.full(len(scores), np.nan)
    ok = np.isfinite(scores)
    ge = len(ref) - np.searchsorted(ref, scores[ok], side="left")
    out[ok] = (ge + 1) / (len(ref) + 1)
    return out


def alpha_grid(alpha: float, n: int) -> float:
    """보정 기록 n개일 때 실제로 걸리는 α. p가 1/(n+1) 단위로만 움직여서 floor(α(n+1))/(n+1)이 된다."""
    return math.floor(alpha * (n + 1)) / (n + 1)


def conformal_threshold(cal: np.ndarray, alpha: float) -> float:
    """'통계량 > 문턱'이 p ≤ α와 같아지는 문턱. (a+1)번째로 큰 보정값이고 a = floor(α(n+1)) − 1이다."""
    ref = np.sort(cal)[::-1]
    a = math.floor(alpha * (len(ref) + 1)) - 1
    return float("inf") if a < 0 else float(ref[a])


def calibrate(T: np.ndarray, t: pd.DataFrame):
    """검증 정상 기록별 최댓값으로 보정한 p(전체)와 p(LOO). tvt/01_scores.py calibrate와 같은 방식."""
    vn = ((t.part == "valid") & (t.subset == "normal")).to_numpy()
    rec = t.rec.to_numpy()
    cal = pd.Series(np.where(np.isfinite(T[vn]), T[vn], -np.inf)).groupby(rec[vn]).max()
    p_full = conformal_p(cal.to_numpy(), T)
    # 검증 정상 행을 자기 기록이 들어간 보정으로 채점하면 p가 낙관적이 된다. 그 기록 하나를 빼고 다시 보정한다(LOO)
    p_loo = np.full(len(T), np.nan)
    for r in cal.index:
        m = rec == r
        p_loo[m] = conformal_p(cal.drop(r).to_numpy(), T[m])
    return cal.to_numpy(), p_full, p_loo


# ---------------------------------------------------------------- 순차 통계량
def blocks(rec: np.ndarray):
    """흐름 안에서 같은 기록이 이어지는 (시작, 끝) 구간. 한 기록이 둘로 끊겨 있으면 assert로 멈춘다."""
    change = np.flatnonzero(rec[1:] != rec[:-1]) + 1
    b = list(zip(np.r_[0, change], np.r_[change, len(rec)]))
    assert len(b) == len(pd.unique(rec)), "기록이 흐름 안에서 끊겨 있다"
    return b


def seq_stat(s, ts, rec, kind, par, carry, mu0):
    """v2 점수 s_t에 CUSUM 또는 EWMA를 돌린 통계량.

    CUSUM S_t = max(0, S_{t-1} + s_t - k), S_0 = 0 / EWMA z_t = λ s_t + (1-λ) z_{t-1}, z_0 = μ0(검증 정상 평균).
    reset은 기록마다 초기값에서 시작한다. carry는 직전 기록이 끝난 지 GAP_S(60초) 안이면 상태를 그대로 넘긴다.
    R1과 같은 시간 규칙이지만 R1처럼 '확인된 이상'만 넘기지 않고 누적값 자체를 넘긴다.
    """
    T = np.empty(len(s))
    state, prev_end = None, None
    for a, b in blocks(rec):
        cont = carry and prev_end is not None and (ts[a] - prev_end) / np.timedelta64(1, "s") <= GAP_S
        if not cont:
            state = 0.0 if kind == "cusum" else mu0
        for i in range(a, b):
            state = max(0.0, state + s[i] - par) if kind == "cusum" else par * s[i] + (1 - par) * state
            T[i] = state
        prev_end = ts[b - 1]
    return T


def seq_table_stat(t, kind, par, carry, mu0):
    """행 표 전체의 순차 통계량. 정상·이상 흐름을 따로 돌린다."""
    T = np.full(len(t), np.nan)
    s, ts, rec = t["v2|score"].to_numpy(float), t.ts.to_numpy(), t.rec.to_numpy()
    for sub in ("normal", "abnormal"):
        # evalcore 시험 흐름처럼 검증→시험을 이어 돌린다. 검증 흐름은 그 앞부분이라 검증 채점 값도 같다
        idx = np.flatnonzero(((t.subset == sub) & t.part.isin(["valid", "test"])).to_numpy())
        assert pd.Series(ts[idx]).is_monotonic_increasing
        T[idx] = seq_stat(s[idx], ts[idx], rec[idx], kind, par, carry, mu0)
    return T


def seq_predict(t, p_full, p_loo, alpha, regime):
    """순차 통계량의 p로 채점 행 경보를 낸다. evalcore._p처럼 검증 채점의 정상 행만 LOO p를 쓴다."""
    part = "valid" if regime == "valid" else "test"
    out = []
    for sub in ("normal", "abnormal"):
        m = ((t.subset == sub) & (t.part == part)).to_numpy()
        p = p_loo[m] if (regime == "valid" and sub == "normal") else p_full[m]
        d = t.loc[m, ["subset", "label", "rec", "pos", "ts"]].copy()
        d["alarm_realtime"] = np.isfinite(p) & (p <= alpha)
        out.append(d)
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- 지표
def first_alarm(ab: pd.DataFrame) -> pd.DataFrame:
    """이상 기록마다 첫 실시간 경보의 위치(행)와 기록 시작에서 잰 지연(초). 미탐이면 None."""
    rows = []
    for r, g in ab.groupby("rec", sort=False):
        a = g.alarm_realtime.to_numpy().astype(bool)
        i = int(np.argmax(a)) if a.any() else None
        rows.append(dict(rec=r, rows_in_record=len(g),
                         first_alarm_row=None if i is None else int(g.pos.iloc[i]),
                         first_alarm_s=None if i is None else round((g.ts.iloc[i] - g.ts.iloc[0]).total_seconds(), 3)))
    return pd.DataFrame(rows)


def summarize(pred: pd.DataFrame) -> dict:
    """채점 행 예측 하나를 F1·오경보 기록·탐지 기록·첫 경보 지연으로 요약한다."""
    y, a = pred.label.to_numpy() == 1, pred.alarm_realtime.to_numpy().astype(bool)
    c = f1_counts(y, a)
    nrm, ab = pred[pred.subset == "normal"], pred[pred.subset == "abnormal"]
    fa = first_alarm(ab)
    d_rows = fa.first_alarm_row.dropna().astype(float)
    d_s = fa.first_alarm_s.dropna().astype(float)
    return dict(f1=round(c["f1"], 6), tp=c["tp"], fp=c["fp"], fn=c["fn"],
                normal_fa_records=int(nrm.groupby("rec").alarm_realtime.max().astype(bool).sum()),
                normal_records=int(nrm.rec.nunique()),
                abnormal_detected_records=int(fa.first_alarm_row.notna().sum()), abnormal_records=int(len(fa)),
                first_row_records=int((d_rows == 0).sum()),
                delay_rows_median=float(d_rows.median()) if len(d_rows) else None,
                delay_rows_max=float(d_rows.max()) if len(d_rows) else None,
                delay_s_median=float(d_s.median()) if len(d_s) else None,
                delay_s_max=float(d_s.max()) if len(d_s) else None)


def cp_upper(k, n, conf=0.95):
    """비율 k/n의 Clopper-Pearson 상한. 이항 정확 구간은 베타 분포 분위수로 바로 구한다."""
    return 1.0 if k >= n else float(stats.beta.ppf(conf, k + 1, n - k))


def cp_lower(k, n, conf=0.95):
    """비율 k/n의 Clopper-Pearson 하한."""
    return 0.0 if k <= 0 else float(stats.beta.ppf(1 - conf, k, n - k + 1))


def poisson_upper(k, conf=0.95):
    """포아송 평균의 정확 단측 상한 χ²(conf; 2k+2)/2. k=0이면 -ln(0.05) ≈ 2.996이라 흔히 쓰는 3/T 규칙이 된다."""
    return float(stats.chi2.ppf(conf, 2 * k + 2) / 2)


def alarm_events(ts: np.ndarray, alarm: np.ndarray) -> int:
    """경보 시작 횟수. 직전 경보 행에서 60초 안에 다시 울린 경보는 같은 사건으로 묶는다."""
    tt = np.sort(ts[alarm])
    if len(tt) == 0:
        return 0
    return 1 + int((np.diff(tt) / np.timedelta64(1, "s") > GAP_S).sum())


def per_record_counts(pred):
    """(subset, 기록)별 tp·fp·fn 행 수. 부트스트랩은 이 기록 단위 묶음을 다시 뽑는다."""
    y, a = pred.label.to_numpy() == 1, pred.alarm_realtime.to_numpy().astype(bool)
    g = pd.DataFrame(dict(subset=pred.subset, rec=pred.rec, tp=y & a, fp=~y & a, fn=y & ~a))
    return g.groupby(["subset", "rec"], sort=True)[["tp", "fp", "fn"]].sum()


def bootstrap(preds: dict, split: str):
    """행 단위 F1의 기록 단위 부트스트랩 95% 구간과 최종 − v2 차이의 구간."""
    rng = np.random.default_rng(SEED)
    counts = {m: per_record_counts(p) for m, p in preds.items()}
    first = next(iter(counts.values()))
    nN, nA = int((first.index.get_level_values(0) == "normal").sum()), int((first.index.get_level_values(0) == "abnormal").sum())
    # 정상·이상 기록을 따로 복원 추출한다(층화). 같은 첨자를 모든 모델에 써서 모델 간 차이의 구간도 같은 재표본으로 낸다
    iN = rng.integers(0, nN, size=(N_BOOT, nN))
    iA = rng.integers(0, nA, size=(N_BOOT, nA))
    f1s, out = {}, {}
    for m, c in counts.items():
        assert c.index.equals(first.index)
        N = c.loc["normal"].to_numpy(float)
        A = c.loc["abnormal"].to_numpy(float)
        tot = N[iN].sum(axis=1) + A[iA].sum(axis=1)                 # (N_BOOT, 3) = 재표본별 tp, fp, fn 합
        f1 = 2 * tot[:, 0] / (2 * tot[:, 0] + tot[:, 1] + tot[:, 2])
        f1s[m] = f1
        lo, hi = np.percentile(f1, [2.5, 97.5])
        out[m] = dict(point=round(f1_counts(preds[m].label.to_numpy() == 1, preds[m].alarm_realtime.to_numpy().astype(bool))["f1"], 6),
                      ci95=[round(float(lo), 6), round(float(hi), 6)], mean=round(float(f1.mean()), 6),
                      share_f1_eq_1=round(float((f1 == 1).mean()), 4),
                      records=dict(normal=nN, abnormal=nA), n_boot=N_BOOT, seed=SEED, split=split)
    diff = f1s["v2+H1+H2"] - f1s["v2"]
    lo, hi = np.percentile(diff, [2.5, 97.5])
    out["diff_final_minus_v2"] = dict(point=round(out["v2+H1+H2"]["point"] - out["v2"]["point"], 6),
                                      ci95=[round(float(lo), 6), round(float(hi), 6)],
                                      share_le_0=round(float((diff <= 0).mean()), 4))
    return out


# ---------------------------------------------------------------- 가상 접합(해제 동작 예시)
def splice(t, r2_ref, seq_chosen, mu0):
    """이상 21기록 끝 SPLICE_GAP_S초 뒤에 정상 시험 기록을 붙인 가상 흐름에서 경보가 언제 풀리는지 센다.

    실제 데이터에는 고장 뒤 정상 기록이 없어 해제 동작을 실측할 수 없다. 채점 지표가 아니라 예시다.
    """
    ab_m = (t.subset == "abnormal").to_numpy()
    nt_m = ((t.subset == "normal") & (t.part == "test")).to_numpy()
    ab, nt = np.flatnonzero(ab_m), np.flatnonzero(nt_m)
    ts, rec, r2 = t.ts.to_numpy(), t.rec.to_numpy(), t.prefix_r2.to_numpy()
    # 정상 시험 구간 전체를 평행 이동해 이상 마지막 행 5초 뒤에서 시작하게 한다(60초 안이라 상태가 이어진다)
    shift = ts[ab[-1]] + np.timedelta64(int(SPLICE_GAP_S * 1e3), "ms") - ts[nt[0]]
    ts_syn = np.r_[ts[ab], ts[nt] + shift]
    rec_syn = np.r_[rec[ab], rec[nt]]
    wave_ok = np.r_[r2[ab], r2[nt]] >= r2_ref
    is_norm = np.r_[np.zeros(len(ab), bool), np.ones(len(nt), bool)]
    norm_ts, norm_rec = ts_syn[is_norm], rec_syn[is_norm]
    first = norm_rec == norm_rec[0]
    res = []

    def record(name, alarm, state_end=None):
        a = alarm[is_norm]
        lead = int(np.argmin(a)) if not a.all() else int(len(a))          # 정상 구간 첫 행부터 이어진 경보 행 수
        rel_s = None if a.all() else round((norm_ts[lead] - norm_ts[0]) / np.timedelta64(1, "s"), 3)
        res.append(dict(model=name, normal_rows=int(len(a)), alarm_rows=int(a.sum()), leading_alarm_rows=lead,
                        release_after_s=rel_s, released=bool(not a.all()),
                        alarm_rows_first_record=int(a[first].sum()),
                        rows_first_record=int(first.sum()),
                        fa_records=int(pd.Series(a).groupby(norm_rec).max().sum()),
                        state_at_fault_end=state_end))

    for name, (h1, h2) in (("v2", (False, False)), ("v2+H1", (True, False)), ("v2+H1+H2", (True, True))):
        own = np.r_[own_alarm(t, ab_m, "v2", PRIMARY_ALPHA, "test", h2, r2_ref),
                    own_alarm(t, nt_m, "v2", PRIMARY_ALPHA, "test", h2, r2_ref)]
        alarm, _ = stream_rules(ts_syn, rec_syn, own, wave_ok, h1)
        record(name, alarm)
    score = t["v2|score"].to_numpy(float)
    s_syn = np.r_[score[ab], score[nt]]
    for fam, (kind, carry, par, cal) in seq_chosen.items():
        T = seq_stat(s_syn, ts_syn, rec_syn, kind, par, carry, mu0)
        record(fam, conformal_p(cal, T) <= PRIMARY_ALPHA, round(float(T[len(ab) - 1]), 3))
    return res


# ---------------------------------------------------------------- 실행
def main():
    OUT.mkdir(exist_ok=True)
    sel = json.loads((TVT_OUT / "tvt_selection.json").read_text(encoding="utf-8"))
    meta = json.loads((TVT_OUT / "tvt_scores_meta.json").read_text(encoding="utf-8"))
    cands = {c[0]: c for c in candidates(meta["A"]["complexity"])}
    # 잠금 선택과 점수 캐시가 test 채점 때 그대로인지 해시로 확인한다
    checks = {"selection_sha256_ok": sha256_file(TVT_OUT / "tvt_selection.json") == (TVT_OUT / "tvt_selection.sha256").read_text(encoding="utf-8").strip()}
    tables, mu0, v2_cal_max = {}, {}, {}
    for s in SPLITS:
        t = pd.read_pickle(CACHE / f"rows_{s}.pkl")
        checks[f"rows_{s}_sha256_ok"] = sha256_file(CACHE / f"rows_{s}.pkl") == sel["inputs"]["rows_sha256"][s]
        # 보정 구현 확인. 같은 방식으로 v2 점수를 보정하면 캐시의 v2 p값(01_scores)과 같아야 한다
        cal_v2, pf, pl = calibrate(t["v2|score"].to_numpy(float), t)
        v2_cal_max[s] = round(float(cal_v2.max()), 6)
        vn = ((t.part == "valid") & (t.subset == "normal")).to_numpy()
        checks[f"{s}_calibrate_matches_v2_p_full"] = bool(np.allclose(pf, t["v2|p_full"].to_numpy(), equal_nan=True))
        checks[f"{s}_calibrate_matches_v2_p_loo"] = bool(np.allclose(pl[vn], t["v2|p_loo"].to_numpy()[vn]))
        tables[s] = t
        mu0[s] = float(t.loc[vn, "v2|score"].mean())
    assert all(checks.values()), checks

    # ---- 비교 대상 v2·v2+R1·최종의 예측(evalcore) ----
    ref_pred = {s: {(m, a): {g: predict_rows(tables[s], cands[m], a, g, meta[s]["r2_ref"]) for g in ("valid", "test")}
                    for m in REF for a in ALPHAS} for s in SPLITS}
    for s in SPLITS:          # tvt 05_test_predictions 결과(α 1%)와 같은지 확인
        csv = pd.read_csv(TVT_OUT / f"test_predictions_{s}.csv")
        for m, col in (("v2+H1+H2", "final_v2_R1_R2_realtime"), ("v2+H1", "locked_v2_R1_realtime"), ("v2", "v2_realtime")):
            mine = ref_pred[s][(m, PRIMARY_ALPHA)]["test"]
            checks[f"{s}_{m}_matches_test_predictions_csv"] = bool(
                (mine.alarm_realtime.to_numpy().astype(bool) == csv[col].astype(bool).to_numpy()).all() and (mine.rec.to_numpy() == csv.rec.to_numpy()).all())
    assert all(checks.values()), checks

    # ---- 1. 검증 격자로 파라미터 선택. CUSUM·EWMA × reset·carry 네 계열 ----
    families = {f"{kind.upper()}-{'carry' if carry else 'reset'}": (kind, carry, CUSUM_K if kind == "cusum" else EWMA_L)
                for kind in ("cusum", "ewma") for carry in (False, True)}
    cache, grid = {}, []
    for fam, (kind, carry, pars) in families.items():
        for par in pars:
            for s in SPLITS:
                T = seq_table_stat(tables[s], kind, par, carry, mu0[s])
                cal, pf, pl = calibrate(T, tables[s])
                cache[(fam, par, s)] = (cal, pf, pl)
                # 보정 퇴화 점검. CUSUM의 k가 정상 점수보다 크면 보정 기록 최댓값이 모두 0이 되어 문턱이 0('S>0이면 경보')으로 퇴화한다
                grid.append(dict(family=fam, param=par, split=s, **summarize(seq_predict(tables[s], pf, pl, PRIMARY_ALPHA, "valid")),
                                 cal_threshold_a1=round(conformal_threshold(cal, PRIMARY_ALPHA), 6),
                                 cal_zero_share=round(float((cal == 0).mean()), 4)))
    grid = pd.DataFrame(grid)
    chosen = {}
    for fam, (kind, carry, pars) in families.items():
        # valid 실시간 F1(A·B 평균)로만 고른다. test는 고른 값으로 한 번만 채점한다
        g = grid[grid.family == fam].groupby("param").f1.mean()
        best = g.max()
        tied = g[g >= best - TIE]
        par = float(max(tied.index))           # 동률이면 기억이 짧은 쪽(큰 k, 큰 λ)
        gg = grid[(grid.family == fam) & (grid.param == par)].set_index("split")
        chosen[fam] = dict(kind=kind, carry=carry, param=par, valid_f1_mean=round(float(g[par]), 6),
                           valid_f1_best=round(float(best), 6), tied_params=[float(x) for x in tied.index],
                           param_name="k" if kind == "cusum" else "lambda",
                           at_grid_edge=bool(par in (min(pars), max(pars))),
                           cal_threshold_a1={s: float(gg.loc[s, "cal_threshold_a1"]) for s in SPLITS},
                           cal_zero_share={s: float(gg.loc[s, "cal_zero_share"]) for s in SPLITS})

    # ---- 1. 비교 표 (valid·test, α 1%) ----
    rows, delays, preds_test = [], [], {s: {} for s in SPLITS}
    for s in SPLITS:
        for m, label in REF.items():
            for g in ("valid", "test"):
                p = ref_pred[s][(m, PRIMARY_ALPHA)][g]
                rows.append(dict(detector=label, key=m, split=s, regime=g, param=None, **summarize(p)))
                if g == "test":
                    preds_test[s][m] = p
        for fam, c in chosen.items():
            cal, pf, pl = cache[(fam, c["param"], s)]
            for g in ("valid", "test"):
                p = seq_predict(tables[s], pf, pl, PRIMARY_ALPHA, g)
                rows.append(dict(detector=f"{fam}({c['param_name']}={c['param']:g})", key=fam, split=s, regime=g, param=c["param"], **summarize(p)))
                if g == "test":
                    preds_test[s][fam] = p
        delays += [first_alarm(p[p.subset == "abnormal"]).assign(split=s, key=key) for key, p in preds_test[s].items()]
    comp = pd.DataFrame(rows)
    delays = pd.concat(delays, ignore_index=True)
    v2_miss = {}
    for s in SPLITS:          # v2 test 미탐 행이 기록 앞부분(0~6행)에 몰려 있는지
        p = preds_test[s]["v2"]
        fn = p[(p.label == 1) & ~p.alarm_realtime.astype(bool)]
        v2_miss[s] = dict(fn_rows=int(len(fn)), fn_rows_pos_le_6=int((fn.pos <= 6).sum()),
                          by_position={str(k): int(v) for k, v in fn.groupby("pos").size().items()})

    # ---- 2. 불확실성 ----
    # 이상 21기록(검증 10·시험 11)은 고장 사건 하나의 연속 구간이라 사건 단위 표본은 1이다
    abn = tables["A"][tables["A"].subset == "abnormal"]
    abn_test = abn[abn.part == "test"]
    event = dict(abnormal_records_total=int(abn.rec.nunique()), abnormal_test_records=int(abn_test.rec.nunique()),
                 event_start=str(abn.ts.min()), event_end=str(abn.ts.max()),
                 event_span_s=round((abn.ts.max() - abn.ts.min()).total_seconds(), 3),
                 test_span_s=round((abn_test.ts.max() - abn_test.ts.min()).total_seconds(), 3),
                 independent_event_samples=1,
                 note="이상 21기록(검증 10·시험 11)은 2022-07-17 한 고장 사건의 연속 구간이다. 기록 단위 구간은 '이 사건 안에서 기록을 다시 뽑는다면'의 변동만 반영하고, "
                      "다른 고장 사건으로의 일반화 불확실성(사건 단위 표본 1)은 반영하지 못한다")
    unc = {"event_sample": event, "clopper_pearson": [], "bootstrap": {}}
    a_nom = alpha_grid(PRIMARY_ALPHA, N_CAL)      # 설계 오경보율 1/121
    for s in SPLITS:
        for m in REF:
            r = comp[(comp.key == m) & (comp.split == s) & (comp.regime == "test")].iloc[0]
            k, n = int(r.normal_fa_records), int(r.normal_records)
            kd, nd = int(r.abnormal_detected_records), int(r.abnormal_records)
            # (a) 정상 오경보 기록 비율의 상한, (b) 이상 탐지 기록 비율의 하한. 양측 95%는 각 꼬리 2.5%라 conf=0.975
            unc["clopper_pearson"].append(dict(
                split=s, model=REF[m], normal_fa_records=f"{k}/{n}",
                fa_rate_upper95_one_sided=round(cp_upper(k, n), 4), fa_rate_ci95_two_sided=[round(cp_lower(k, n, 0.975), 4), round(cp_upper(k, n, 0.975), 4)],
                fa_nominal_alpha_grid=round(a_nom, 4), fa_expected_records_at_nominal=round(a_nom * n, 2),
                fa_binom_p_ge_k_at_nominal=round(float(stats.binom.sf(k - 1, n, a_nom)), 4),   # 설계값이 맞을 때 k건 이상 볼 확률
                abnormal_detected_records=f"{kd}/{nd}",
                detect_rate_lower95_one_sided=round(cp_lower(kd, nd), 4), detect_rate_ci95_two_sided=[round(cp_lower(kd, nd, 0.975), 4), round(cp_upper(kd, nd, 0.975), 4)]))
        unc["bootstrap"][s] = bootstrap({m: preds_test[s][m] for m in REF}, s)
    unc["note_overlap"] = "A 시험 정상 기록(480~599)은 B 시험 정상 기록(420~599)에 포함된다. A·B 구간을 합쳐 독립 표본처럼 다루면 안 된다"

    # ---- 3. 경보 운영 지표 (정상 시험 구간) ----
    ops = []
    for s in SPLITS:
        t = tables[s]
        nt = t[(t.subset == "normal") & (t.part == "test")]
        meas_h = len(nt) * ROW_S / 3600                                  # 측정 시간 = 행 수 × 0.1초
        cal_h = (nt.ts.max() - nt.ts.min()).total_seconds() / 3600       # 달력 시간 = 첫~끝 타임스탬프(수집 공백 포함)
        n_rec = nt.rec.nunique()
        entries = [(m, a, ref_pred[s][(m, a)]["test"]) for m in REF for a in ALPHAS] + \
                  [(fam, PRIMARY_ALPHA, preds_test[s][fam]) for fam in chosen]
        for key, a, p in entries:
            pn = p[p.subset == "normal"]
            al = pn.alarm_realtime.to_numpy().astype(bool)
            ev = alarm_events(pn.ts.to_numpy(), al)
            up = poisson_upper(ev)        # 경보 사건 수의 95% 상한. 시간으로 나누면 시간당 상한이 된다
            ops.append(dict(split=s, model=REF.get(key, key), alpha=a, normal_rows=len(pn), measured_s=round(meas_h * 3600, 1),
                            calendar_s=round(cal_h * 3600, 1), normal_records=n_rec, alarm_rows=int(al.sum()),
                            alarm_records=int(pn.groupby("rec").alarm_realtime.max().astype(bool).sum()), alarm_events=ev,
                            events_per_h_measured=round(ev / meas_h, 3), events_per_h_calendar=round(ev / cal_h, 3),
                            poisson_upper95_count=round(up, 3),
                            events_per_h_upper95_measured=round(up / meas_h, 2), events_per_h_upper95_calendar=round(up / cal_h, 2),
                            records_per_h_calendar=round(n_rec / cal_h, 1),
                            nominal_fa_records_per_h_calendar=round(alpha_grid(a, N_CAL) * n_rec / cal_h, 2)))
    ops = pd.DataFrame(ops)

    # ---- 4. 가상 접합(해제 동작). 순차 통계량은 고른 파라미터의 검증 보정값으로 판정한다 ----
    spl = {}
    for s in SPLITS:
        seq_c = {fam: (c["kind"], c["carry"], c["param"], cache[(fam, c["param"], s)][0]) for fam, c in chosen.items()}
        spl[s] = splice(tables[s], meta[s]["r2_ref"], seq_c, mu0[s])

    result = dict(
        note="test 채점(잠금 선택 v2+R1, 최종 v2+R1+R2) 이후에 추가한 사후 비교다. tvt/ 산출물은 읽기만 했고 잠금 선택과 최종 모델 결정에 영향이 없다",
        settings=dict(alpha=PRIMARY_ALPHA, alphas_ops=list(ALPHAS), cusum_k_grid=list(CUSUM_K), ewma_lambda_grid=list(EWMA_L),
                      ewma_z0="검증 정상 행 v2 점수 평균 μ0", mu0={s: round(v, 6) for s, v in mu0.items()}, v2_cal_max=v2_cal_max, gap_s=GAP_S, tie=TIE,
                      selection="검증 실시간 행 F1(A·B 평균) 최고, 0.002 이내 동률이면 큰 k·큰 λ", n_boot=N_BOOT, seed=SEED,
                      splice_gap_s=SPLICE_GAP_S, row_s=ROW_S),
        checks=checks,
        selection=chosen,
        comparison=comp.to_dict(orient="records"),
        v2_test_miss_positions=v2_miss,
        first_alarm_delay=delays.to_dict(orient="records"),
        uncertainty=unc,
        operations=ops.to_dict(orient="records"),
        splice_release=spl,
    )
    (OUT / f"{STEM}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    comp.to_csv(OUT / f"{STEM}.csv", index=False, encoding="utf-8-sig")
    grid.to_csv(OUT / f"{STEM}_grid.csv", index=False, encoding="utf-8-sig")
    delays.to_csv(OUT / f"{STEM}_delays.csv", index=False, encoding="utf-8-sig")
    ops.to_csv(OUT / f"{STEM}_ops.csv", index=False, encoding="utf-8-sig")
    write_summary(result, comp, grid, delays, ops)
    return result


def _md(header, rows):
    """마크다운 표 줄 목록. 첫 열은 왼쪽, 나머지는 오른쪽 정렬."""
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] + ["---:"] * (len(header) - 1)) + "|"]
    return out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def _n(x, d=4):
    """소수 d자리 문자열. 값이 없으면 '—'."""
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


def write_summary(res, comp, grid, delays, ops):
    """결과를 사람이 읽는 요약 md로 쓴다. 문장 틀은 고정이고 수치만 결과에서 채운다."""
    sel, unc, spl = res["selection"], res["uncertainty"], res["splice_release"]
    names = {**REF, **{f: f"{f}({'k' if c['kind'] == 'cusum' else 'λ'}={c['param']:g})" for f, c in sel.items()}}
    order = list(REF) + list(sel)

    def cv(key, s, g, col):                 # 비교 표의 한 칸
        return comp[(comp.key == key) & (comp.split == s) & (comp.regime == g)].iloc[0][col]

    def ab(key, g, col, d=4):               # 'A값 / B값'. d=None이면 정수
        return " / ".join(_n(cv(key, s, g, col), d) if d is not None else str(int(cv(key, s, g, col))) for s in SPLITS)

    def sp(s, m):                           # 가상 접합 결과 한 줄
        return next(r for r in spl[s] if r["model"] == m)

    cc, ce = sel["CUSUM-carry"], sel["EWMA-carry"]
    cp_rows = {(r["split"], r["model"]): r for r in unc["clopper_pearson"]}
    fin_cp = {s: cp_rows[(s, REF["v2+H1+H2"])] for s in SPLITS}
    boot = unc["bootstrap"]
    opsf = ops[(ops.model == REF["v2+H1+H2"]) & (ops.alpha == PRIMARY_ALPHA)].set_index("split")
    ev = unc["event_sample"]

    L = ["---", "title: 프레스 — 순차 검출(CUSUM·EWMA) 비교·불확실성·경보 운영 지표 (사후 분석)",
         "created: 2026-10-04", "updated: 2026-10-04", "tags: [contest/k-ai-manufacturing]",
         "source: code/press/domain/04_sequential_uncertainty.py (tvt 캐시 rows_{A,B}.pkl·evalcore 재사용)",
         "status: seed", "---", "",
         "# 순차 검출 비교 · 불확실성 · 경보 운영 지표 (사후 분석)", "",
         "> 상위: `code/press/tvt/README.md` · 산출: `outputs/04_sequential_uncertainty.json`(전체), `.csv`(비교 표), "
         "`_grid.csv`(검증 격자), `_delays.csv`(첫 경보 지연), `_ops.csv`(운영 지표)", "",
         "> **test 채점 이후에 추가한 사후 비교다.** 잠금 선택(v2+R1)과 최종 모델(v2+R1+R2) 결정에는 영향이 없다. "
         "tvt/ 산출물은 읽기만 했고(캐시·선택 파일 해시 확인), CUSUM·EWMA 파라미터는 valid로만 고른 뒤 test를 그 값으로 한 번 채점했다.", "",
         "## 요약", "",
         f"- **이득의 핵심은 상태를 수집 공백 너머로 넘기는 것이다.** 표준 CUSUM·EWMA도 기록 경계에서 상태를 이어 가면(carry, R1과 같은 60초 규칙) "
         f"test 실시간 F1이 R1 수준으로 오른다: CUSUM-carry(k={cc['param']:g}) A/B {ab('CUSUM-carry', 'test', 'f1', 3)}, "
         f"EWMA-carry(λ={ce['param']:g}) {ab('EWMA-carry', 'test', 'f1', 3)} (v2+R1 {ab('v2+H1', 'test', 'f1', 3)}, 최종 {ab('v2+H1+H2', 'test', 'f1', 3)}). "
         f"기록마다 리셋하면 CUSUM {ab('CUSUM-reset', 'test', 'f1', 3)}, EWMA {ab('EWMA-reset', 'test', 'f1', 3)}로 v2({ab('v2', 'test', 'f1', 3)})에서 조금 오르는 데 그친다. "
         f"v2의 test 미탐은 기록 첫 0~6행에 몰려 있어서(A {res['v2_test_miss_positions']['A']['fn_rows']}행 중 "
         f"{res['v2_test_miss_positions']['A']['fn_rows_pos_le_6']}행, B {res['v2_test_miss_positions']['B']['fn_rows']}행 중 "
         f"{res['v2_test_miss_positions']['B']['fn_rows_pos_le_6']}행) 기록 안에서만 쌓는 통계량은 첫 행을 구하지 못한다",
         "- **그래서 이 데이터의 F1만으로는 R1이 표준 기법보다 낫다고 말할 수 없다.** 차이는 경보를 푸는 방식에서 난다. "
         f"고장 직후 정상 기록을 5초 간격으로 붙인 가상 흐름에서 R1은 {sp('A', 'v2+H1')['leading_alarm_rows']}행({sp('A', 'v2+H1')['release_after_s']:.1f}초) 만에 풀렸고, "
         f"CUSUM-carry는 {sp('A', 'CUSUM-carry')['leading_alarm_rows']:,}~{sp('B', 'CUSUM-carry')['leading_alarm_rows']:,}행"
         f"({sp('A', 'CUSUM-carry')['release_after_s'] / 60:.1f}~{sp('B', 'CUSUM-carry')['release_after_s'] / 60:.1f}분, 정상 기록 "
         f"{sp('A', 'CUSUM-carry')['fa_records']}~{sp('B', 'CUSUM-carry')['fa_records']}개) 동안 경보가 이어졌다. "
         f"EWMA-carry(λ={ce['param']:g})는 {sp('A', 'EWMA-carry')['leading_alarm_rows']}~{sp('B', 'EWMA-carry')['leading_alarm_rows']}행이었다",
         f"- CUSUM-carry가 고른 k={cc['param']:g}는 **격자 끝값이고 보정이 퇴화했다.** k가 검증 정상 점수 최댓값"
         f"(A {res['settings']['v2_cal_max']['A']:.2f}, B {res['settings']['v2_cal_max']['B']:.2f})보다 커서 "
         f"검증 정상 기록 최댓값이 전부 0(비율 A {cc['cal_zero_share']['A']:.0%} · B {cc['cal_zero_share']['B']:.0%})이고, 문턱은 'S>0이면 경보'가 된다. "
         "이때 실질 문턱은 α가 아니라 원점수 k=5다. B test에서 v2·v2+R1의 오경보 3행(점수 3.97~4.59)을 피한 것도 이 높은 문턱 때문이다",
         f"- 최종 모델의 test 결과는 표본이 작아 구간이 넓다. 정상 오경보 기록 {fin_cp['A']['normal_fa_records']}(A)·{fin_cp['B']['normal_fa_records']}(B)의 "
         f"Clopper–Pearson 단측 95% 상한은 {fin_cp['A']['fa_rate_upper95_one_sided']:.1%}·{fin_cp['B']['fa_rate_upper95_one_sided']:.1%}로 설계값 α_grid "
         f"{fin_cp['A']['fa_nominal_alpha_grid']:.2%}(=1/121)보다 크다. 이상 시험 기록 탐지 {fin_cp['A']['abnormal_detected_records']}의 단측 95% 하한은 "
         f"{fin_cp['A']['detect_rate_lower95_one_sided']:.1%}(양측 {fin_cp['A']['detect_rate_ci95_two_sided'][0]:.1%})다",
         f"- 기록 단위 부트스트랩(10,000회)에서 최종 모델 F1 구간은 [1.000, 1.000]으로 퇴화한다. 오류가 하나도 없어서 다시 뽑아도 오류가 생기지 않을 뿐, "
         f"불확실성이 없다는 뜻이 아니다. v2는 A [{boot['A']['v2']['ci95'][0]:.3f}, {boot['A']['v2']['ci95'][1]:.3f}]·B "
         f"[{boot['B']['v2']['ci95'][0]:.3f}, {boot['B']['v2']['ci95'][1]:.3f}], 최종−v2 차이는 A [{boot['A']['diff_final_minus_v2']['ci95'][0]:.3f}, "
         f"{boot['A']['diff_final_minus_v2']['ci95'][1]:.3f}]·B [{boot['B']['diff_final_minus_v2']['ci95'][0]:.3f}, {boot['B']['diff_final_minus_v2']['ci95'][1]:.3f}]로 "
         "이 사건 안에서는 개선이 기록 재추출에 흔들리지 않는다",
         f"- **이상 시험 11기록은 한 고장 사건({ev['event_start'][:19]}부터 {ev['event_span_s']:.0f}초)의 연속 구간이다. 사건 단위 표본은 1이다.** "
         "위 구간들은 모두 '이 사건 안에서'의 변동만 반영한다",
         f"- 정상 시험 구간은 측정 {opsf.loc['A', 'measured_s']:.0f}초(A)·{opsf.loc['B', 'measured_s']:.0f}초(B), 달력 "
         f"{opsf.loc['A', 'calendar_s'] / 60:.1f}분·{opsf.loc['B', 'calendar_s'] / 60:.1f}분뿐이다. 최종 모델 경보 사건 0건의 포아송 95% 상한은 "
         f"시간당 {opsf.loc['A', 'events_per_h_upper95_calendar']:.1f}건(A)·{opsf.loc['B', 'events_per_h_upper95_calendar']:.1f}건(B, 달력 기준), "
         f"측정 시간 기준이면 {opsf.loc['A', 'events_per_h_upper95_measured']:.1f}건·{opsf.loc['B', 'events_per_h_upper95_measured']:.1f}건이다. "
         f"α 1% 기록 단위 보정을 연속 운전(시간당 약 {opsf.loc['A', 'records_per_h_calendar']:.0f}기록)에 옮기면 설계 오경보율은 시간당 "
         f"{opsf.loc['A', 'nominal_fa_records_per_h_calendar']:.1f}기록(교환가능성 가정, R2 보류·60초 묶음 전)이다. 이 데이터로는 0과 3.7을 구별할 수 없다",
         ""]

    # ---- 1. 비교 표
    L += ["## 1. 순차 검출 비교 (α 1%, 실시간 행 단위)", "",
          "- 입력 점수는 v2 결합 점수(성분별 −log10 꼬리확률의 최댓값). 검증 정상 행 평균 μ0 = "
          f"{res['settings']['mu0']['A']:.3f}(A)·{res['settings']['mu0']['B']:.3f}(B)",
          "- CUSUM S_t = max(0, S_{t−1} + s_t − k), S_0 = 0 · EWMA z_t = λ s_t + (1−λ) z_{t−1}, z_0 = μ0",
          "- reset: 기록마다 초기값 · carry: 직전 기록이 끝난 지 60초 안이면 상태를 이어 감(정상·이상 흐름 모두 기록 간격 최대 17초라 사실상 항상 이어짐)",
          "- 문턱: 검증 정상 기록별 통계량 최댓값으로 conformal p(검증 정상 행은 LOO), p ≤ 1%이면 경보. 흐름·채점 행은 evalcore와 같다",
          "- 파라미터: valid 실시간 F1(A·B 평균) 최고, 0.002 안 동률이면 큰 k·큰 λ. test는 고른 값 1회", ""]
    hdr = ["검출기", "valid F1 A / B", "test F1 A / B", "test 미탐 행 A / B", "test 오경보 행 A / B",
           "정상 시험 오경보 기록 A / B", "첫 행 경보 기록(/11) A / B", "첫 경보 지연 최대 행(초) A / B"]
    rows = []
    for k in order:
        rows.append([("**" + names[k] + "**") if k == "v2+H1+H2" else names[k], ab(k, "valid", "f1"), ab(k, "test", "f1"),
                     ab(k, "test", "fn", None), ab(k, "test", "fp", None), ab(k, "test", "normal_fa_records", None),
                     ab(k, "test", "first_row_records", None),
                     " / ".join(f"{int(cv(k, s, 'test', 'delay_rows_max'))}({cv(k, s, 'test', 'delay_s_max'):.1f})" for s in SPLITS)])
    L += _md(hdr, rows) + [""]
    L += ["### valid 격자 (실시간 F1, A·B 평균 · 괄호는 보정 기록 최댓값이 0인 비율 A/B)", ""]
    grows = []
    for fam in sel:
        g = grid[grid.family == fam]
        cells = []
        for par, gg in g.groupby("param"):
            z = gg.set_index("split").cal_zero_share
            mark = "**" if par == sel[fam]["param"] else ""
            zs = f" ({z['A']:.0%}/{z['B']:.0%})" if fam.startswith("CUSUM") and (z > 0).any() else ""
            cells.append(f"{'k' if fam.startswith('CUSUM') else 'λ'}={par:g}: {mark}{gg.f1.mean():.4f}{mark}{zs}")
        grows.append([fam, " · ".join(cells)])
    L += _md(["계열", "파라미터별 valid F1 (굵게 = 선택)"], grows) + [""]
    L += ["- CUSUM k=0.5는 정상 평균(≈0.84)보다 작아 정상에서도 통계량이 계속 자란다. carry 방식에서는 기록 경계를 넘어 누적돼 valid F1이 0.86으로 떨어진다",
          f"- k가 커질수록 보정 기록 최댓값 중 0의 비율이 오른다. reset 선택 k={sel['CUSUM-reset']['param']:g}도 94~95%가 0이라 문턱이 소수 기록에 걸려 있고, "
          f"carry 선택 k={cc['param']:g}는 100%라 문턱이 0으로 퇴화했다(v2 보정 최댓값 A {res['settings']['v2_cal_max']['A']:.2f}·B {res['settings']['v2_cal_max']['B']:.2f} < k)",
          "- EWMA는 λ에 둔감하다(reset·carry 모두 네 값이 0.002 안 동률)", ""]

    # 첫 경보 지연 (기록별)
    L += ["### 이상 시험 기록별 첫 경보 위치 (행, A / B · 0 = 기록 첫 행)", ""]
    recs = sorted(delays[delays.split == "A"].rec.unique(), key=lambda r: int(r.split(":")[-1]))
    drows = []
    for r in recs:
        row = [r.split(":")[-1], int(delays[(delays.split == "A") & (delays.rec == r)].rows_in_record.iloc[0])]
        for k in order:
            v = [delays[(delays.split == s) & (delays.rec == r) & (delays.key == k)].first_alarm_row.iloc[0] for s in SPLITS]
            row.append(" / ".join("미탐" if pd.isna(x) else str(int(x)) for x in v))
        drows.append(row)
    L += _md(["이상 기록", "행 수"] + [names[k] for k in order], drows) + [""]
    L += ["- 지연(초)은 첫 경보 행 시각 − 기록 첫 행 시각이다(`_delays.csv`). 이 데이터는 행 간격이 0.1초라 행 수 × 0.1초와 같다", ""]

    # 가상 접합
    L += ["### 보충: 고장 뒤 정상 복귀 시 해제 (가상 접합, 채점 지표 아님)", "",
          f"- 이상 21기록 마지막 행 {SPLICE_GAP_S:g}초 뒤에 정상 시험 기록을 이어 붙인 흐름. 실제 데이터에는 고장 뒤 정상 기록이 없어서 해제 동작을 실측할 수 없다", ""]
    srows = []
    for k in order:
        a, b = sp("A", k), sp("B", k)
        rel = " / ".join("안 풀림" if not x["released"] else f"{x['leading_alarm_rows']:,}행({x['release_after_s']:.1f}초)" for x in (a, b))
        srows.append([names[k], rel, f"{a['alarm_rows']:,} / {b['alarm_rows']:,}", f"{a['fa_records']} / {b['fa_records']}",
                      "—" if a["state_at_fault_end"] is None else f"{a['state_at_fault_end']:,.1f} / {b['state_at_fault_end']:,.1f}"])
    L += _md(["검출기", "정상 첫 행부터 이어진 경보(해제까지) A / B", "정상 구간 경보 행 A / B", "경보 기록 A / B", "고장 끝 통계량 A / B"], srows) + [""]
    L += ["- R1의 7행은 파형 R² 계산에 8행이 필요해서 생기는 최소 지연이다(고장 규모와 무관)",
          f"- CUSUM은 고장 동안 쌓인 양(A {sp('A', 'CUSUM-carry')['state_at_fault_end']:,.0f})이 (k − s_t) 속도로만 줄어들어 오래 울린다. 실무에서는 상한(cap)이나 확인 후 리셋을 붙인다",
          ""]

    # ---- 2. 불확실성
    L += ["## 2. 불확실성 (test, α 1%)", "",
          "### (a)(b) 기록 단위 비율의 Clopper–Pearson 구간", ""]
    crow = []
    for (s, m), r in cp_rows.items():
        crow.append([s, m, r["normal_fa_records"], f"{r['fa_rate_upper95_one_sided']:.2%}",
                     f"[{r['fa_rate_ci95_two_sided'][0]:.2%}, {r['fa_rate_ci95_two_sided'][1]:.2%}]",
                     f"{r['fa_expected_records_at_nominal']:.2f}", f"{r['fa_binom_p_ge_k_at_nominal']:.3f}",
                     r["abnormal_detected_records"], f"{r['detect_rate_lower95_one_sided']:.1%}",
                     f"[{r['detect_rate_ci95_two_sided'][0]:.1%}, {r['detect_rate_ci95_two_sided'][1]:.0%}]"])
    L += _md(["분할", "모델", "정상 오경보 기록", "단측 95% 상한", "양측 95% 구간", "설계값(1/121)이면 기대 기록", "설계값에서 P(≥관측)",
              "이상 기록 탐지", "단측 95% 하한", "양측 95% 구간"], crow) + [""]
    L += ["- 정상 오경보 기록 = 실시간 경보가 1행이라도 난 정상 시험 기록. 이상 기록 탐지 = 경보가 1행이라도 난 이상 시험 기록",
          "- B v2·v2+R1의 3/180도 설계값 기대(1.49기록)와 통계적으로 구별되지 않는다(P(≥3) ≈ 0.19). 오경보 0건과 3건 모두 α 1% 설계와 어긋나지 않는다",
          f"- {unc['note_overlap']}", ""]
    L += ["### (c) 행 단위 F1의 기록 단위 부트스트랩 (정상·이상 시험 기록을 따로 복원 추출, 10,000회, seed 0, 백분위 95%)", ""]
    brow = []
    for s in SPLITS:
        for m in list(REF) + ["diff_final_minus_v2"]:
            b = boot[s][m]
            lab = "최종 − v2 (같은 재표본)" if m.startswith("diff") else REF[m]
            extra = f"재표본 중 F1=1 비율 {b['share_f1_eq_1']:.1%}" if "share_f1_eq_1" in b else f"재표본 중 차이 ≤ 0 비율 {b['share_le_0']:.1%}"
            brow.append([s, lab, f"{b['point']:.4f}", f"[{b['ci95'][0]:.4f}, {b['ci95'][1]:.4f}]", extra])
    L += _md(["분할", "모델", "점추정", "95% 구간", "비고"], brow) + [""]
    L += ["- 오류가 0인 모델은 재추출해도 오류가 생기지 않아 구간이 [1, 1]이 된다. 이런 경우의 불확실성은 (a)(b)의 이항 구간으로 읽어야 한다",
          "- 기록을 독립으로 보고 다시 뽑는다. 실제 기록은 시간순으로 이어지고 R1은 앞 기록 상태를 넘기므로 독립이 아니다", "",
          "### (d) 사건 단위 표본", "",
          f"- 이상 21기록(검증 10·시험 11)은 {ev['event_start'][:19]} ~ {ev['event_end'][:19]}({ev['event_span_s']:.0f}초)의 한 고장 사건이다. "
          f"시험 11기록은 그중 뒤쪽 {ev['test_span_s']:.0f}초다",
          "- 기록 324행·11기록은 사건 하나를 잘게 나눈 것이라, 다른 고장 사건으로 일반화하는 근거로는 표본 1개다. 위 (a)~(c)는 이 사건 안의 변동만 반영한다", ""]

    # ---- 3. 운영 지표
    L += ["## 3. 경보 운영 지표 (정상 시험 구간)", ""]
    for s in SPLITS:
        o = ops[ops.split == s].iloc[0]
        L.append(f"- {s}: 정상 시험 {int(o.normal_records)}기록 · {int(o.normal_rows):,}행 → 측정 {o.measured_s:.1f}초({o.measured_s / 60:.1f}분), "
                 f"달력 {o.calendar_s:.1f}초({o.calendar_s / 60:.1f}분, 첫~끝 타임스탬프) · 달력 기준 시간당 {o.records_per_h_calendar:.0f}기록")
    L += ["- 경보 사건 = 경보 시작 횟수. 직전 경보 행에서 60초 안에 다시 울린 경보는 같은 사건. 95% 상한은 포아송 정확식 χ²(0.95; 2k+2)/2 ÷ T (0건이면 2.996/T ≈ 3/T)",
          "- 설계 기대 = α_grid × 시간당 기록 수. 검증 정상 120기록으로 보정한 기록 단위 α를 연속 운전에 옮긴 값이다(v2 기준, R1·R2 효과와 60초 묶음 전)", ""]
    orow = []
    for r in ops.itertuples():
        orow.append([r.split, r.model, f"{r.alpha:.0%}", r.alarm_rows, r.alarm_records, r.alarm_events,
                     f"{r.events_per_h_measured:.1f} / {r.events_per_h_calendar:.1f}",
                     f"{r.events_per_h_upper95_measured:.1f} / {r.events_per_h_upper95_calendar:.1f}", f"{r.nominal_fa_records_per_h_calendar:.1f}"])
    L += _md(["분할", "모델", "α", "경보 행", "경보 기록", "경보 사건", "시간당 사건 (측정 / 달력)", "시간당 95% 상한 (측정 / 달력)", "설계 기대 (기록/시간, 달력)"], orow) + [""]
    L += ["- 최종 모델은 α 1%에서 A·B 모두 0건이다. 0건이어도 상한이 시간당 7~26건이라, 교대(8시간)당 오경보 수 같은 운영 목표를 검증하기에는 정상 시간이 모자라다",
          "- α를 3·5%로 올리면 B에서 v2+R1은 오경보 행이 21·32행으로 늘지만 사건으로 묶으면 4건이다. R1이 확인된 오경보를 다음 기록으로 넘겨 행 수를 불린다. 최종 모델(R2 포함)은 1건이다",
          ""]

    # ---- 4. 해석
    L += ["## 4. 해석 — R1과 CUSUM·EWMA는 무엇이 같고 다른가", "",
          "**같은 점**", "",
          "- 셋 다 한 행만 보지 않고 앞의 증거를 기억한다. carry 방식 CUSUM·EWMA는 R1과 같은 60초 규칙으로 수집 공백을 넘는다",
          "- 이번 데이터에서 v2의 미탐은 거의 모두 기록 첫 몇 행이다. 기록 첫 0~4행은 파형 성분, 0~1행은 동역학 성분이 아직 없어 크기 성분만으로 판정한다. "
          "수집 공백을 넘는 기억이 있으면 어떤 형태든 이 미탐을 없앤다. reset 방식이 v2보다 조금밖에 나아지지 않는 것이 그 반증이다", "",
          "**다른 점**", "",
          "1. **넘기는 것**: CUSUM·EWMA는 점수의 크기를 누적·평활해서 넘긴다. R1은 '확인된 이상'(자기 경보 2행 이상 또는 이어받은 경보 미해제)이라는 이진 상태만 넘긴다. "
          "정상 기록의 오경보 1행은 다음 기록으로 넘어가지 않는다",
          "2. **푸는 조건**: CUSUM·EWMA는 통계량이 문턱 아래로 감쇠할 때 풀린다. 감쇠 시간은 쌓인 양과 기억 길이에 달려 있어서 큰 고장일수록 늦게 풀린다(가상 접합에서 CUSUM 11~12분). "
          "R1은 새 기록에서 전류 파형이 정상이라는 반대 증거(prefix R² ≥ 기준)가 나오면 풀린다. 해제 시간이 고장 규모와 무관하고 최소 0.7초(8행)다. "
          f"EWMA λ={ce['param']:g}는 기억이 짧아(반감기 1행) R1보다 빨리 풀렸다({sp('A', 'EWMA-carry')['release_after_s']:.1f}~{sp('B', 'EWMA-carry')['release_after_s']:.1f}초). "
          "대신 기록 경계를 넘겨 주는 힘도 고장 점수 크기에 달려 있어, 점수가 문턱 근처인 약한 이상이면 다음 기록 첫 행까지 상태가 남지 않을 수 있다",
          "3. **기록 안 동작**: CUSUM·EWMA는 기록 안에서도 평활하므로 새 사건의 첫 반응이 늦어질 수 있다(작은 λ, 큰 k). R1은 기록 안에서는 v2 그대로이고 기록 경계에서만 기억을 쓴다",
          "4. **보정**: CUSUM·EWMA는 통계량마다 다시 보정해야 하고, carry 방식에서는 보정 기록의 통계량이 앞 기록 상태에 좌우된다. "
          f"CUSUM k={cc['param']:g}처럼 k가 정상 점수보다 크면 보정이 퇴화해 α가 의미를 잃는다. R1은 v2의 보정 문턱을 그대로 쓰고 상수 두 개(60초, 2행)만 더한다",
          "5. **CUSUM이 유리할 수 있는 곳**: 문턱 아래의 작은 이탈이 오래 이어지는 서서히 시작되는 이상. 이번 사건은 점수 중앙값이 약 25(문턱 3.5~4.4의 6배 이상)인 급격한 이상이라 이 장점이 드러날 여지가 없었다", "",
          "**운영 판단**: 이 데이터에서는 F1로 R1과 carry 방식 표준 기법을 가를 수 없다. EWMA-carry는 성능이 거의 같고 해제도 빨랐다. "
          "R1에 남는 장점은 해제가 점수 크기와 무관하게 '정상 파형 확인'에 묶여 있다는 점(고장 규모에 따라 경보가 길게 끌리지 않음)과 v2 보정을 그대로 쓴다는 점이다. "
          "CUSUM을 쓴다면 상한이나 정상 확인 리셋을 붙여야 하고, 정상 확인 리셋을 붙이면 해제 부분은 R1과 같은 구조가 된다", ""]

    # ---- 5. 한계
    L += ["## 5. 한계", "",
          "- test를 본 뒤 추가한 분석이다. CUSUM·EWMA 격자와 동률 규칙은 이번에 정했고 test 이후 바꾸지 않았다. R1·R2 상수 자체는 전체 데이터를 본 초기 탐색에서 착안했다(tvt README 경위 1)",
          "- 고장 사건이 하나(급격한 이상)다. 다른 형태의 이상에서 순위가 바뀔 수 있다",
          "- 고장 뒤 정상 복귀 구간이 데이터에 없다. 해제 동작은 가상 접합으로만 봤고, 접합 흐름은 실제 시간 순서가 아니다",
          "- 정상 시험 시간이 측정 7~10분, 달력 16~24분이라 시간당 경보율 상한이 넓다",
          "- A 시험 정상 기록이 B 시험 정상 기록에 포함돼 A·B는 독립 반복이 아니다",
          "- Clopper–Pearson·부트스트랩은 기록 독립을 가정한다. carry·R1에서는 이웃 기록이 상태를 공유한다",
          "- carry 방식의 LOO 보정은 자기 기록 최댓값만 빼고, 그 기록이 다음 기록 초기 상태에 준 영향은 남는다. EWMA 초기값 μ0도 검증 정상 전체 평균이다",
          f"- CUSUM-carry k={cc['param']:g}는 격자 끝값이다. 격자를 넓혔다면 다른 값이 뽑혔을 수 있다", ""]

    L += ["## 재현", "", "```bash", "cd code/press/domain", "PYTHONIOENCODING=utf-8 python 04_sequential_uncertainty.py   # 약 10초, 팀 레포 불필요(tvt 캐시 사용)", "```", "",
          "- 실행 전 확인(모두 통과): tvt 선택 파일·점수 캐시 해시, 이 스크립트의 보정이 캐시의 v2 p값(전체·LOO)과 같음, "
          "evalcore로 계산한 v2·v2+R1·최종 test 예측이 `tvt/outputs/test_predictions_{A,B}.csv`와 같음", ""]
    (OUT / f"{STEM}_summary.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    res = main()
    print(json.dumps({k: res[k] for k in ("checks", "selection")}, ensure_ascii=False, indent=1))
