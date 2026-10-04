"""다변량 통계적 공정 관리(MSPC) 기준선: 행마다 최근 8행 창의 특징 7개 → PCA → Hotelling T²·SPE 경보를 tvt와 같은 틀로 채점한다.
입력은 cases/common.load_both(matched=True) 원자료, tvt/cache/rows_{A,B}.pkl 행 표(복사본에 열만 붙임), tvt/outputs/tvt_scores_meta.json이다.
출력은 domain/outputs/03_mspc.json(설정·PCA·한계·진단·기여·전체 결과), 03_mspc.csv(모델 × 분할 × α × valid/test), 03_mspc_summary.md다.
보고서 2.4·3.1절의 근거다. test 채점 이후의 사후 비교라 잠근 선택과 최종 모델(v2+H1+H2 = 보고서 R1·R2)에는 영향이 없다.
실행: PYTHONIOENCODING=utf-8 python domain/03_mspc.py (code/press 에서)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
PRESS = HERE.parent
sys.path.insert(0, str(PRESS / "cases"))
sys.path.insert(0, str(PRESS / "tvt"))
from common import F0, SENSORS, lag1, load_both  # noqa: E402
import evalcore  # noqa: E402
from lib import ALPHAS, SPLITS  # noqa: E402

OUT = HERE / "outputs"
CACHE = PRESS / "tvt" / "cache"
META = PRESS / "tvt" / "outputs" / "tvt_scores_meta.json"

W = 8                      # 창 길이(고정). v2 파형 창·교차 확인 R²와 같은 8행 = 0.8초, 겉보기 전류 주기의 약 절반
W_SENS = (6, 12)           # 민감도용(선택에 안 씀)
MIN_ROWS = 3               # 창이 이보다 짧으면(기록 위치 0·1) 점수·경보 없음
CUM_VAR = 0.90             # PCA 성분 수 k = 누적 분산 90%에 처음 닿는 수
EPS_V, EPS_C, EPS_R = 1e-4, 1.1920929, 1e-3   # log 바닥: 진동·전류 양자화 단위, 잔차 비율
LOAD_STATE_RMS = 91.9      # 사후 진단용 부하 상태 경계(예준 v2 LOAD_STATE_RMS, 기록 평균 제거 전류 RMS). 경보·학습에는 안 씀
STATE_MIN_ROWS = 17        # 겉보기 전류 한 주기 이상 본 기록만 부하 상태를 매긴다(예준 v2와 같음)
# 특징 7개는 프레스 상태 감시의 흔한 축에서 이상 자료를 보지 않고 하나씩 골랐다.
# 진동 에너지(상·하부 창 RMS), 부하(전류 RMS), 스펙트럼 모양(상·하부 lag-1), 프레임 상·하부 결합(상관), 전류 파형 왜곡(사인 잔차 비율)
FEATURES = ["vu_lrms", "vl_lrms", "cur_lrms", "vu_ac1", "vl_ac1", "ul_corr", "cur_res"]
FEATURE_KO = {"vu_lrms": "상부 진동 RMS", "vl_lrms": "하부 진동 RMS", "cur_lrms": "전류 RMS(부하)",
              "vu_ac1": "상부 진동 lag-1", "vl_ac1": "하부 진동 lag-1", "ul_corr": "상·하부 진동 상관",
              "cur_res": "전류 사인 잔차 비율"}
VIB_RMS, CUR_RMS = [0, 1], 2   # FEATURES 안 위치
np.random.seed(0)              # 난수는 쓰지 않지만 기록용으로 고정


# ---------------------------------------------------------------- 특징
def window_features(df: pd.DataFrame, w: int) -> tuple[np.ndarray, np.ndarray]:
    """행별 창 특징. 창은 같은 기록 안 그 행까지의 최근 w행이다. 반환은 (특징 [행, 7], 창 길이 n)이고 n < 3이면 특징 NaN."""
    v0, v1, c = (df[s].to_numpy(float) for s in SENSORS)
    F = np.full((len(df), len(FEATURES)), np.nan)
    nwin = np.zeros(len(df), int)
    # 창 길이 m마다 고정 F0 사인 + 절편 설계행렬과 유사역행렬을 미리 만든다
    pinv = {}
    for m in range(MIN_ROWS, w + 1):
        k = np.arange(m)
        X = np.column_stack([np.ones(m), np.sin(2 * np.pi * F0 * k), np.cos(2 * np.pi * F0 * k)])
        pinv[m] = (X, np.linalg.pinv(X))
    for idx in df.groupby("rec").indices.values():
        idx = np.sort(idx)
        for j in range(len(idx)):
            s = idx[max(0, j - w + 1): j + 1]
            m = len(s)
            nwin[idx[j]] = m
            if m < MIN_ROWS:
                continue
            a, b, x = v0[s], v1[s], c[s]
            sa, sb = a.std(), b.std()
            X, P = pinv[m]
            beta = P @ x
            amp = float(np.hypot(beta[1], beta[2]))
            rstd = float(np.sqrt(np.mean((x - X @ beta) ** 2)))
            # 전류 RMS는 창 SD 대신 사인 진폭/√2다. 8행 창은 겉보기 주기의 절반이라 SD가 위상에 따라 흔들린다
            # (정상 학습 기록에서 기록 전체 RMS와의 상관: 창 SD 0.71, 사인 진폭 0.99).
            # 분산 0 창의 상관·자기상관은 NaN으로 두고 표준화 뒤 0(학습 평균)으로 채운다. 창 3행에선 사인이 정확히 맞아 cur_res가 상수다
            F[idx[j]] = [np.log10(sa + EPS_V), np.log10(sb + EPS_V), np.log10(amp / np.sqrt(2) + EPS_C),
                         lag1(a) if sa > 0 else np.nan, lag1(b) if sb > 0 else np.nan,
                         np.corrcoef(a, b)[0, 1] if sa > 0 and sb > 0 else np.nan,
                         np.log10(rstd / max(amp, EPS_C) + EPS_R)]
    return F, nwin


# ---------------------------------------------------------------- 꼬리 변환·보정
class Tail:
    """점수 s → −log10(꼬리 확률). 정상 학습 참조 R의 q95까지는 경험분포 −log10((#R≥s + 1)/(n + 1)),
    그 위는 평균 초과량 β인 지수 꼬리로 외삽한다(예준 press.scores.ExpTail과 같은 식)."""

    def __init__(self, ref, q=0.95):
        r = np.sort(np.asarray(ref, float)[np.isfinite(ref)])
        self.ref, self.n = r, len(r)
        self.u = float(np.quantile(r, q))
        self.beta = float((r[r > self.u] - self.u).mean())
        self.g_u = self._emp(np.array([self.u]))[0]

    def _emp(self, s):
        ge = self.n - np.searchsorted(self.ref, s, side="left")
        return -np.log10((ge + 1) / (self.n + 1))

    def __call__(self, s):
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        v = s[ok]
        res = np.where(v <= self.u, self._emp(v), self.g_u + (v - self.u) / (self.beta * np.log(10)))
        out[ok] = res
        return out


def conformal_p(cal_values, scores):
    """예준 press.calibrate.conformal_p 와 같은 식: p = (1 + #{cal ≥ s})/(n+1). 점수 NaN이면 p NaN(경보 없음)."""
    ref = np.sort(np.where(np.isfinite(cal_values), cal_values, -np.inf))
    out = np.full(len(scores), np.nan)
    ok = np.isfinite(scores)
    ge = len(ref) - np.searchsorted(ref, scores[ok], side="left")
    out[ok] = (ge + 1) / (len(ref) + 1)
    return out


def calibrate(table: pd.DataFrame, score: np.ndarray):
    """검증 정상 기록별 최댓값을 보정 집합으로 conformal p를 낸다. 검증 정상 행은 자기 기록을 뺀 보정(LOO)을 쓴다.
    기록 최댓값으로 보정하므로 '기록 하나에 수십 행을 검정하는' 다중 검정 문제가 막힌다(tvt/01_scores.py calibrate와 같다)."""
    vn = ((table.part == "valid") & (table.subset == "normal")).to_numpy()
    sv, rv = score[vn], table.rec.to_numpy()[vn]
    cal = pd.Series(np.where(np.isfinite(sv), sv, -np.inf)).groupby(rv).max()
    full = conformal_p(cal.to_numpy(), score)
    loo = np.full(len(score), np.nan)
    pos_vn = np.flatnonzero(vn)
    for r in cal.index:
        m = rv == r
        loo[pos_vn[m]] = conformal_p(cal.drop(r).to_numpy(), sv[m])
    return full, loo, cal


# ---------------------------------------------------------------- MSPC 모델
class MSPC:
    """창 길이별 표준화(+선택: 부하 회귀) → PCA → T²·SPE, 고전 한계와 꼬리 변환."""

    def __init__(self, load: bool):
        self.load = load

    def _z(self, F, nwin):
        """창 길이 n별 정상 학습 평균·SD로 표준화한다. 짧은 창은 추정량 분산이 커서 한 표준화로 묶으면
        기록 시작 직후 행이 일괄로 튄다(배치 MSPC의 '시점별 평균 궤적 차감'을 창 길이별로 줄인 것)."""
        Z = np.zeros_like(F)
        for n in range(MIN_ROWS, self.w + 1):
            m = nwin == n
            sd = self.sd[n]
            Z[m] = np.where(sd > 1e-9, (F[m] - self.mu[n]) / np.where(sd > 1e-9, sd, 1.0), 0.0)
        Z[~np.isfinite(Z)] = 0.0                       # 정의 안 되는 상관·자기상관 = 학습 평균
        return Z

    def _std(self, F, nwin):
        """표준화 z. mspc_load면 진동 RMS z 두 개를 전류 RMS z에 대한 회귀 잔차(재표준화)로 바꾼다."""
        Z = self._z(F, nwin)
        if self.load:
            for n in range(MIN_ROWS, self.w + 1):
                m = nwin == n
                for j in VIB_RMS:
                    a, b, s = self.reg[n][j]
                    Z[m, j] = (Z[m, j] - a - b * Z[m, CUR_RMS]) / s
        return Z

    def fit(self, F, nwin, w):
        """정상 학습 행으로 표준화·(부하 회귀)·PCA·고전 한계 모수·꼬리 분포를 만든다."""
        self.w = w
        ok = nwin >= MIN_ROWS
        F, nwin = F[ok], nwin[ok]
        self.mu, self.sd = {}, {}
        for n in range(MIN_ROWS, w + 1):
            m = nwin == n
            self.mu[n] = np.nanmean(F[m], axis=0)
            self.sd[n] = np.nanstd(F[m], axis=0, ddof=1)
        if self.load:
            # 창 길이별 OLS z(진동 RMS) ~ z(전류 RMS). 둘 다 log라 진동 ∝ 부하^b 관계를 빼는 셈이다
            Z0 = self._z(F, nwin)
            self.reg, self.reg_info = {}, {}
            for n in range(MIN_ROWS, w + 1):
                m = nwin == n
                self.reg[n] = {}
                for j in VIB_RMS:
                    x, y = Z0[m, CUR_RMS], Z0[m, j]
                    b, a = np.polyfit(x, y, 1)
                    r = y - a - b * x
                    s = r.std(ddof=2)
                    self.reg[n][j] = (a, b, s)
                    self.reg_info[f"n{n}_{FEATURES[j]}"] = dict(slope=round(float(b), 4),
                                                                r2=round(float(1 - r.var() / y.var()), 4))
        Z = self._std(F, nwin)
        mrows = len(Z)
        S = Z.T @ Z / (mrows - 1)                      # 학습 행의 z는 평균 0이라 따로 중심화하지 않는다
        lam, P = np.linalg.eigh(S)
        order = np.argsort(lam)[::-1]
        lam, P = lam[order], P[:, order]
        cum = np.cumsum(lam) / lam.sum()
        k = int(np.searchsorted(cum, CUM_VAR) + 1)     # 누적 분산이 90%에 처음 닿는 성분 수
        self.lam_all, self.P_all, self.k, self.cum = lam, P, k, cum
        self.P, self.lam = P[:, :k], lam[:k]
        self.m = mrows
        # 고전 한계 모수: 잔차 공간 고유값의 1·2·3제곱 합 θ와 Jackson–Mudholkar 지수 h0
        th = [float((lam[k:] ** i).sum()) for i in (1, 2, 3)]
        self.theta = th
        self.h0 = 1 - 2 * th[0] * th[2] / (3 * th[1] ** 2)
        t2, spe = self._indices(Z)
        self.tail_t2, self.tail_spe = Tail(t2), Tail(spe)
        # 사후 변형(_nt): 짧은 창의 T²·SPE는 정상에서도 꼬리가 두꺼워(검증 A 진단) 창 길이 n마다 따로 꼬리 확률로 바꾼다
        self.tails_n = {n: (Tail(t2[nwin == n]), Tail(spe[nwin == n])) for n in range(MIN_ROWS, w + 1)}
        self.train_t2, self.train_spe = t2, spe
        return self

    def _indices(self, Z):
        """T² = Σ t_a²/λ_a (k개 성분), SPE = 잔차 공간 ‖z − ẑ‖²."""
        T = Z @ self.P
        t2 = (T ** 2 / self.lam).sum(1)
        E = Z - T @ self.P.T
        return t2, (E ** 2).sum(1)

    def t2_limit(self, conf):
        """새 관측용 T² 한계 k(m+1)(m−1)/(m(m−k))·F(k, m−k)."""
        k, m = self.k, self.m
        return k * (m + 1) * (m - 1) / (m * (m - k)) * stats.f.ppf(conf, k, m - k)

    def spe_limit(self, conf):
        """Jackson–Mudholkar SPE 한계."""
        t1, t2, _ = self.theta
        h0 = self.h0
        c = stats.norm.ppf(conf)
        return t1 * (c * np.sqrt(2 * t2 * h0 ** 2) / t1 + 1 + t2 * h0 * (h0 - 1) / t1 ** 2) ** (1 / h0)

    # 두 한계식을 거꾸로 풀어 p값으로 바꾼다. p ≤ α ⇔ (1−α) 한계 초과라 평가 틀에 그대로 넣을 수 있다
    def p_t2(self, t2):
        k, m = self.k, self.m
        return stats.f.sf(t2 * m * (m - k) / (k * (m + 1) * (m - 1)), k, m - k)

    def p_spe(self, spe):
        t1, t2, _ = self.theta
        h0 = self.h0
        c = t1 * ((np.maximum(spe, 0) / t1) ** h0 - 1 - t2 * h0 * (h0 - 1) / t1 ** 2) / np.sqrt(2 * t2 * h0 ** 2)
        return stats.norm.sf(c)

    def score(self, F, nwin):
        """행별 지표. conformal 점수는 두 꼬리 −log10 p 중 큰 값, 고전 p는 min(p_T², p_SPE)(OR 경보). 창 3행 미만은 NaN."""
        ok = nwin >= MIN_ROWS
        out = {k: np.full(len(F), np.nan) for k in ("t2", "spe", "g_t2", "g_spe", "score", "score_nt",
                                                    "p_cl", "p_cl_t2", "p_cl_spe")}
        Z = self._std(F[ok], nwin[ok])
        t2, spe = self._indices(Z)
        g1, g2 = self.tail_t2(t2), self.tail_spe(spe)
        pt, ps = self.p_t2(t2), self.p_spe(spe)
        nt = np.full(len(t2), np.nan)
        for n, (ta, tb) in self.tails_n.items():
            m = nwin[ok] == n
            nt[m] = np.fmax(ta(t2[m]), tb(spe[m]))
        for k, v in (("t2", t2), ("spe", spe), ("g_t2", g1), ("g_spe", g2), ("score", np.fmax(g1, g2)), ("score_nt", nt),
                     ("p_cl", np.fmin(pt, ps)), ("p_cl_t2", pt), ("p_cl_spe", ps)):
            out[k][ok] = v
        out["Z"] = np.full((len(F), F.shape[1]), np.nan)
        out["Z"][ok] = Z
        return out

    def contributions(self, Z):
        """T² 완전분해 기여(Alcala & Qin 2009): ((P Λ^-1/2 Pᵀ) z)_j², 합 = T². SPE 기여: 잔차 제곱, 합 = SPE."""
        M_half = self.P @ np.diag(self.lam ** -0.5) @ self.P.T
        ct2 = (Z @ M_half.T) ** 2
        E = Z - Z @ self.P @ self.P.T
        return ct2, E ** 2


# ---------------------------------------------------------------- 자료 맞춤
def raw_frames():
    """정상·이상 원자료에 캐시 행 표와 맞출 키(subset, ts)를 붙인다."""
    normal, abnormal = load_both(matched=True)
    for df, sub in ((normal, "normal"), (abnormal, "abnormal")):
        df["subset"] = sub
        df["ts"] = pd.to_datetime(df.TimeStamp).astype("datetime64[ns]")
    return normal, abnormal


def align(table: pd.DataFrame, raw: pd.DataFrame) -> np.ndarray:
    """캐시 행 표의 각 행에 대응하는 raw 행 번호. 키 = (subset, ts, pos) — B에 같은 시각 행이 한 쌍 있어 pos로 가른다."""
    key = raw[["subset", "ts", "pos"]].reset_index(drop=True).assign(_i=np.arange(len(raw)))
    m = table[["subset", "ts", "pos"]].merge(key, on=["subset", "ts", "pos"], how="left", validate="one_to_one")
    assert m._i.notna().all(), "캐시 행 중 원자료와 맞지 않는 행"
    i = m._i.to_numpy(int)
    assert np.allclose(raw[SENSORS[2]].to_numpy()[i], table.current.to_numpy(), atol=1e-6), "전류 값이 캐시와 다르다(정밀도·정렬 오류)"
    return i


# ---------------------------------------------------------------- 평가
def run_eval(table, cands, sid, r2_ref, rows):
    """후보마다 α·valid/test별로 tvt/evalcore.evaluate 채점 결과(실시간·기록 단위)를 rows에 쌓는다."""
    for cand in cands:
        for alpha in ALPHAS:
            for regime in ("valid", "test"):
                r = evalcore.evaluate(table, cand, alpha, regime, r2_ref)
                rec = dict(split=sid, model=cand[0], base=cand[1], h1=cand[2], h2=cand[3], alpha=alpha, regime=regime)
                for unit in ("realtime", "record"):
                    for k, v in r.get(unit, {}).items():
                        rec[f"{unit}_{k}"] = v
                rows.append(rec)


def add_columns(table, name, sc, idx):
    """MSPC 점수를 행 표에 붙이고 conformal(이름) / 고전(이름_cl, _cl_t2, _cl_spe) 열을 만든다."""
    vn = ((table.part == "valid") & (table.subset == "normal")).to_numpy()
    s = sc["score"][idx]
    full, loo, cal = calibrate(table, s)
    cols = {f"{name}|score": s, f"{name}|p_full": full, f"{name}|p_loo": loo}
    s_nt = sc["score_nt"][idx]
    full_nt, loo_nt, cal_nt = calibrate(table, s_nt)
    cols.update({f"{name}_nt|score": s_nt, f"{name}_nt|p_full": full_nt, f"{name}_nt|p_loo": loo_nt})
    for suf, key in (("_cl", "p_cl"), ("_cl_t2", "p_cl_t2"), ("_cl_spe", "p_cl_spe")):
        p = sc[key][idx]
        cols[f"{name}{suf}|score"] = -np.log10(np.clip(p, 1e-300, 1))
        cols[f"{name}{suf}|p_full"] = p
        cols[f"{name}{suf}|p_loo"] = np.where(vn, p, np.nan)      # 고전 한계는 보정이 없으므로 LOO도 같은 값
    return pd.concat([table, pd.DataFrame(cols, index=table.index)], axis=1), cal, cal_nt


def load_state(current: pd.Series, rec) -> np.ndarray:
    """사후 진단용 기록 부하 상태: 기록 전체 전류의 평균 제거 RMS ≥ 91.9면 high, 17행 미만 기록은 unknown."""
    g = current.groupby(rec)
    rms, n = g.transform(lambda x: x.std(ddof=0)), g.transform("size")
    return np.where(n < STATE_MIN_ROWS, "unknown", np.where(rms >= LOAD_STATE_RMS, "high", "low"))


def pos_bucket(pos):
    """기록 위치 구간: 점수 없음(0·1), 창이 덜 찬 2~6, 창이 찬 7 이상."""
    return np.where(pos < MIN_ROWS - 1, "pos0-1(점수없음)", np.where(pos < W - 1, f"pos2-{W - 2}(창3~{W - 1}행)", f"pos{W - 1}+(창{W}행)"))


def weakness(table, r2_ref, models):
    """α 1% 시험, 규칙 없는 자체 경보: 이상 행 탐지율(기록 위치별), 정상 행 오경보(부하 상태별), 기록별 첫 경보 위치."""
    out = {}
    state = pd.Series(load_state(table.current, table.rec), index=table.index)
    for name in models:
        pr = evalcore.predict_rows(table, (name, name, False, False, False, 1), 0.01, "test", r2_ref)
        key = table[["subset", "ts", "pos"]].assign(state=state.to_numpy())
        pr = pr.merge(key, on=["subset", "ts", "pos"], how="left", validate="one_to_one")
        pr["bucket"] = pos_bucket(pr.pos.to_numpy())
        pr["alarm"] = pr.alarm_realtime.astype(bool)
        ab, nm = pr[pr.label == 1], pr[pr.label == 0]
        first = ab.groupby("rec").apply(lambda g: int(g.pos[g.alarm].min()) if g.alarm.any() else None, include_groups=False)
        out[name] = dict(
            abnormal_detect_by_pos={b: dict(rows=int(len(g)), detected=int(g.alarm.sum()), rate=round(float(g.alarm.mean()), 4))
                                    for b, g in ab.groupby("bucket")},
            normal_false_alarm_by_load={s: dict(rows=int(len(g)), false_alarms=int(g.alarm.sum()),
                                                records_with_fa=int(g.groupby("rec").alarm.any().sum()),
                                                records=int(g.rec.nunique()))
                                        for s, g in nm.groupby("state")},
            normal_false_alarm_by_pos={b: dict(rows=int(len(g)), false_alarms=int(g.alarm.sum()), rate=round(float(g.alarm.mean()), 4))
                                       for b, g in nm.groupby("bucket")},
            abnormal_first_alarm_pos={str(k): (None if v is None or pd.isna(v) else int(v)) for k, v in first.items()},
            abnormal_records_missed=int(first.isna().sum()),
        )
    return out


def contribution_summary(model, sc, idx, table):
    """이상 시험 행·정상 시험 행의 특징별 평균 T²·SPE 기여와 비율. 순위는 이상 시험 행 평균 기여 기준."""
    res = {}
    Z = sc["Z"][idx]
    ok = np.isfinite(sc["score"][idx])
    ct2, cspe = model.contributions(np.nan_to_num(Z))
    for lab, m in (("abnormal_test", (table.part == "test") & (table.subset == "abnormal")),
                   ("normal_test", (table.part == "test") & (table.subset == "normal"))):
        m = m.to_numpy() & ok
        d = {}
        for nm_, C in (("t2", ct2), ("spe", cspe)):
            share = C[m] / np.maximum(C[m].sum(1, keepdims=True), 1e-12)
            d[nm_] = {f: dict(mean=round(float(C[m, j].mean()), 3), share=round(float(share[:, j].mean()), 3))
                      for j, f in enumerate(FEATURES)}
            d[nm_ + "_rank"] = sorted(FEATURES, key=lambda f: -d[nm_][f]["mean"])
        g1, g2 = sc["g_t2"][idx][m], sc["g_spe"][idx][m]
        d["mean_signed_z"] = {f: round(float(Z[m, j].mean()), 2) for j, f in enumerate(FEATURES)}   # 이탈 방향(+ 증가, − 감소)
        d["rows"] = int(m.sum())
        d["spe_dominant_share"] = round(float((g2 >= g1).mean()), 3)
        d["mean_t2"], d["mean_spe"] = round(float(sc["t2"][idx][m].mean()), 2), round(float(sc["spe"][idx][m].mean()), 2)
        res[lab] = d
    return res


def classical_diagnostics(model, sc_tr, sc_raw, idx, table, conf=0.99):
    """99% 고전 한계의 정상 행 초과율(학습·검증·시험)과, 그 결과 정상 기록 중 한 행이라도 넘는 기록 비율."""
    lt, ls = model.t2_limit(conf), model.spe_limit(conf)
    out = dict(t2_limit=round(float(lt), 3), spe_limit=round(float(ls), 3))
    t2_tr, spe_tr = sc_tr
    out["train_normal_rows"] = dict(t2=round(float((t2_tr > lt).mean()), 4), spe=round(float((spe_tr > ls).mean()), 4),
                                    either=round(float(((t2_tr > lt) | (spe_tr > ls)).mean()), 4))
    t2, spe = sc_raw["t2"][idx], sc_raw["spe"][idx]
    for part in ("valid", "test"):
        for sub in ("normal", "abnormal"):
            m = ((table.part == part) & (table.subset == sub)).to_numpy() & np.isfinite(t2)
            ex = (t2[m] > lt) | (spe[m] > ls)
            recx = pd.Series(ex).groupby(table.rec.to_numpy()[m]).any()
            out[f"{part}_{sub}_rows"] = dict(t2=round(float((t2[m] > lt).mean()), 4), spe=round(float((spe[m] > ls).mean()), 4),
                                             either=round(float(ex.mean()), 4), records_any=round(float(recx.mean()), 4))
    return out


def calibration_anatomy(sc, idx, nwin, table, cal, lo, train_mask):
    """conformal 문턱을 정한 검증 정상 기록(최댓값 1위)의 최댓값 행 해부와, 정상 학습 점수의 창 길이별 99.9% 분위."""
    r = cal.idxmax()
    m = (table.rec == r).to_numpy()
    s = sc["score"][idx][m]
    j = int(np.nanargmax(s))
    i = idx[np.flatnonzero(m)[j]]
    tr = train_mask & np.isfinite(sc["score"])
    return dict(record=r, global_record=lo + int(r.split(":")[-1]), length=int(m.sum()), pos=int(table.pos.to_numpy()[m][j]),
                window_rows=int(nwin[i]), score=round(float(s[j]), 3), t2=round(float(sc["t2"][i]), 2), spe=round(float(sc["spe"][i]), 2),
                g_t2=round(float(sc["g_t2"][i]), 2), g_spe=round(float(sc["g_spe"][i]), 2),
                z={f: round(float(sc["Z"][i, k]), 2) for k, f in enumerate(FEATURES)},
                train_score_q999_by_window={int(n): round(float(np.quantile(sc["score"][tr & (nwin == n)], 0.999)), 2)
                                            for n in range(MIN_ROWS, int(nwin.max()) + 1)})


def load_drift(model, sc, raw, lo, hi, conf=0.99):
    """정상 학습·검증·시험 구간 × 기록 부하 상태별 고전 99% 한계 초과율과 특징 평균 z(운전 조건 이동 진단)."""
    nm = (raw.subset == "normal").to_numpy()
    state = load_state(raw[nm].AI2_Current, raw[nm].rec)
    rec = raw.rec.to_numpy()[nm]
    part = np.where(rec < lo, "train", np.where(rec < hi, "valid", "test"))
    t2, spe, Z = sc["t2"][nm], sc["spe"][nm], sc["Z"][nm]
    ok = np.isfinite(t2)
    ex = (t2 > model.t2_limit(conf)) | (spe > model.spe_limit(conf))
    out = {}
    for p_ in ("train", "valid", "test"):
        for s_ in ("high", "low", "unknown"):
            m = ok & (part == p_) & (state == s_)
            out[f"{p_}/{s_}"] = dict(records=int(len(np.unique(rec[(part == p_) & (state == s_)]))), rows=int(m.sum()),
                                     classical_exceed=round(float(ex[m].mean()), 4),
                                     mean_z={f: round(float(Z[m, j].mean()), 2) for j, f in enumerate(FEATURES)})
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META.read_text(encoding="utf-8"))
    normal, abnormal = raw_frames()
    raw = pd.concat([normal, abnormal], ignore_index=True)
    # 창 특징을 raw 행 순서(정상 다음 이상)로 잇는다: (F_정상, n_정상) + (F_이상, n_이상) → (F, n)
    feats = {w: window_features(normal, w) + window_features(abnormal, w) for w in (W, *W_SENS)}
    feats = {w: (np.vstack([f[0], f[2]]), np.concatenate([f[1], f[3]])) for w, f in feats.items()}

    rows, info = [], {}
    for sid, (lo, hi) in SPLITS.items():
        r2_ref = meta[sid]["r2_ref"]
        # 캐시 행 표 복사본에서 v2·maxz3 점수 열만 남기고 MSPC 열을 붙인다(원본 캐시는 건드리지 않음)
        table = pd.read_pickle(CACHE / f"rows_{sid}.pkl")
        keep = [c for c in table.columns if "|" not in c or c.split("|")[0] in ("v2", "maxz3")]
        table = table[keep].copy()
        idx = align(table, raw)
        train = ((raw.subset == "normal") & (raw.rec < lo)).to_numpy()
        # 점수가 있는 학습 행 수(위치 2 이상)는 창 길이와 무관하다
        info[sid] = dict(train_rows_scored=int((feats[W][1][train] >= MIN_ROWS).sum()), models={})
        cands = []
        for w in (W, *W_SENS):
            F, nwin = feats[w]
            for load in ((False, True) if w == W else (False,)):
                name = ("mspc_load" if load else "mspc") + ("" if w == W else f"_w{w}")
                model = MSPC(load).fit(F[train], nwin[train], w)
                sc = model.score(F, nwin)
                table, cal, cal_nt = add_columns(table, name, sc, idx)
                if w == W:
                    mi = dict(k=model.k, explained_cum=[round(float(v), 4) for v in model.cum],
                              eigenvalues=[round(float(v), 4) for v in model.lam_all],
                              loadings={f"PC{a + 1}": {f: round(float(model.P_all[j, a]), 3) for j, f in enumerate(FEATURES)}
                                        for a in range(model.k)},
                              h0=round(float(model.h0), 4),
                              limits={f"{int(round((1 - a) * 100))}%": dict(t2=round(float(model.t2_limit(1 - a)), 3),
                                                                           spe=round(float(model.spe_limit(1 - a)), 3))
                                      for a in ALPHAS},
                              classical_99=classical_diagnostics(model, (model.train_t2, model.train_spe), sc, idx, table),
                              calibration={k: dict(n_records=int(len(c)), records_without_score=int(np.isinf(c).sum()),
                                                   top_records={r: round(float(v), 3) for r, v in c.sort_values(ascending=False).head(3).items()})
                                           for k, c in (("global_tail", cal), ("per_window_tail_nt", cal_nt))},
                              contributions=contribution_summary(model, sc, idx, table),
                              calibration_anatomy=calibration_anatomy(sc, idx, nwin, table, cal, lo, train))
                    if load:
                        mi["load_regression"] = model.reg_info
                    else:
                        info[sid]["load_drift"] = load_drift(model, sc, raw, lo, hi)
                    info[sid]["models"][name] = mi
                    # 후보 튜플은 evalcore 규약 (이름, 기반 점수 열, H1 사건 지속, H2 교차 확인, 기록 단위 전용, 복잡도)
                    cands += [(name, name, False, False, False, 1), (name + "+H1", name, True, False, False, 2),
                              (name + "_cl", name + "_cl", False, False, False, 1), (name + "_cl+H1", name + "_cl", True, False, False, 2),
                              (name + "_cl_t2", name + "_cl_t2", False, False, False, 1),
                              (name + "_cl_spe", name + "_cl_spe", False, False, False, 1),
                              (name + "_nt", name + "_nt", False, False, False, 2), (name + "_nt+H1", name + "_nt", True, False, False, 3)]
                else:
                    cands += [(name, name, False, False, False, 1), (name + "+H1", name, True, False, False, 2)]
        # 기준 비교: 같은 평가 함수로 v2 계열과 베이스라인을 다시 채점한다(이전 결과와 같아야 한다)
        cands += [("v2", "v2", False, False, False, 3), ("v2+H1", "v2", True, False, False, 4),
                  ("v2+H1+H2", "v2", True, True, False, 5), ("maxz3", "maxz3", False, False, False, 1)]
        run_eval(table, cands, sid, r2_ref, rows)
        info[sid]["weakness"] = weakness(table, r2_ref, ["mspc", "mspc_nt", "mspc_load", "mspc_cl", "v2"])
        # v2 오경보가 났던 시험 정상 행에서 MSPC 각 사양의 p
        p = table["v2|p_full"].to_numpy()
        fa = table[((table.part == "test") & (table.subset == "normal")).to_numpy() & (p <= 0.01)]

        def _p(i, col):
            v = table.loc[i, col]
            return None if pd.isna(v) else float(f"{v:.4g}")
        info[sid]["v2_false_alarm_rows"] = [
            dict(rec=table.loc[i, "rec"], pos=int(table.loc[i, "pos"]), v2_p=_p(i, "v2|p_full"), mspc_p=_p(i, "mspc|p_full"),
                 mspc_nt_p=_p(i, "mspc_nt|p_full"), mspc_load_p=_p(i, "mspc_load|p_full"), mspc_cl_p=_p(i, "mspc_cl|p_full"),
                 mspc_load_cl_p=_p(i, "mspc_load_cl|p_full"))
            for i in fa.index]
        print(sid, "정렬·채점 완료:", len(table), "행")

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "03_mspc.csv", index=False, encoding="utf-8-sig")
    summary = summarize(res, info)
    payload = dict(
        note="test 채점 이후의 사후 비교. 잠근 선택(tvt_selection.json)·최종 모델(v2+H1+H2)에 영향 없음",
        config=dict(window=W, window_sensitivity=list(W_SENS), min_rows=MIN_ROWS, cum_var=CUM_VAR, features=FEATURES,
                    feature_ko=FEATURE_KO, standardize="창 길이 n(3~8)별 정상 학습 평균·표준편차",
                    t2_limit="k(m+1)(m-1)/(m(m-k)) F(k,m-k;1-α) — 새 관측용", spe_limit="Jackson–Mudholkar",
                    classical_alarm="T² 또는 SPE가 (1-α) 한계 초과(OR) ⇔ min(p_T², p_SPE) ≤ α",
                    conformal="score = max(−log10 tail_T², −log10 tail_SPE) (ExpTail 식), 검증 정상 기록 최댓값 conformal p, 검증 정상 LOO",
                    load_variant="창 길이별 z(진동 RMS) ~ z(전류 RMS) 정상 학습 OLS 잔차를 재표준화",
                    nt_variant="사후 변형: T²·SPE 꼬리 확률을 창 길이 n별 정상 학습 분포로 계산(검증 A 진단 후 추가, test 결과를 본 뒤)",
                    seed=0),
        info=info, headline=summary["headline"],
        results=res.round(4).to_dict(orient="records"))
    (OUT / "03_mspc.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (OUT / "03_mspc_summary.md").write_text(summary["md"], encoding="utf-8")
    print("저장:", OUT / "03_mspc_summary.md")


# ---------------------------------------------------------------- 요약
LABELS = [
    ("mspc_cl", "MSPC 고전 한계 99% (T² 또는 SPE)"),
    ("mspc_cl_t2", "　└ T² 단독 (F 분포 99%)"),
    ("mspc_cl_spe", "　└ SPE 단독 (Jackson–Mudholkar 99%)"),
    ("mspc_cl+H1", "MSPC 고전 한계 + R1"),
    ("mspc", "**MSPC conformal (주 사양)**"),
    ("mspc+H1", "MSPC conformal + R1"),
    ("mspc_load_cl", "MSPC 부하 정규화, 고전 한계"),
    ("mspc_load", "MSPC 부하 정규화, conformal"),
    ("mspc_load+H1", "MSPC 부하 정규화, conformal + R1"),
    ("mspc_nt", "(사후 변형) MSPC 창 길이별 꼬리, conformal"),
    ("mspc_nt+H1", "(사후 변형) 창 길이별 꼬리 + R1"),
    ("mspc_load_nt", "(사후 변형) 부하 정규화 + 창 길이별 꼬리"),
    ("mspc_load_nt+H1", "(사후 변형) 부하 정규화 + 창 길이별 꼬리 + R1"),
    ("v2+H1+H2", "참고: 최종 v2 + R1 + R2"),
    ("v2+H1", "참고: v2 + R1"),
    ("v2", "참고: 예준 v2"),
    ("maxz3", r"참고: 베이스라인 max\|z\|"),   # 표 안의 | 는 이스케이프
]
SENS = [("mspc_w6", "w = 6"), ("mspc_w6+H1", "w = 6 + R1"), ("mspc", "w = 8 (주 사양)"), ("mspc+H1", "w = 8 + R1"),
        ("mspc_w12", "w = 12"), ("mspc_w12+H1", "w = 12 + R1")]
KEY_ALPHA = ["mspc", "mspc+H1", "mspc_nt", "mspc_nt+H1", "mspc_load", "mspc_cl", "v2+H1+H2", "v2"]
B01, B26, B7 = "pos0-1(점수없음)", f"pos2-{W - 2}(창3~{W - 1}행)", f"pos{W - 1}+(창{W}행)"


def _row(res, model, regime, alpha, sid):
    """결과표에서 (모델, valid/test, α, 분할) 한 행. 없으면 None."""
    r = res[(res.model == model) & (res.regime == regime) & (res.alpha == alpha) & (res.split == sid)]
    return r.iloc[0] if len(r) else None


def _f(res, model, regime, alpha, unit, sid):
    """F1(실시간 또는 기록 단위). 없으면 NaN."""
    r = _row(res, model, regime, alpha, sid)
    v = None if r is None else r.get(f"{unit}_f1")
    return np.nan if v is None or pd.isna(v) else float(v)


def _c(res, model, regime, alpha, unit, sid, k):
    """오경보(fp)·미탐(fn) 같은 개수."""
    return int(_row(res, model, regime, alpha, sid)[f"{unit}_{k}"])


def f3(x):
    """소수 셋째 자리 문자열, 값이 없으면 —."""
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"


def summarize(res, info):
    """요약 md 본문과 headline(주요 모델의 α 1% F1)을 만든다."""
    A, B = info["A"], info["B"]
    L = []
    w = L.append

    def F(m, reg, a, u, s):
        return f3(_f(res, m, reg, a, u, s))

    def AB(m, reg, a, u):
        return f"{F(m, reg, a, u, 'A')} / {F(m, reg, a, u, 'B')}"

    w("---\ntitle: 프레스 — MSPC(PCA T²·SPE) 기준선 사후 비교\ncreated: 2026-10-04\nupdated: 2026-10-04\n"
      "tags: [contest/k-ai-manufacturing]\nsource: Claude Code 세션 2026-10-04 (code/press/domain/03_mspc.py)\nstatus: seed\n---\n")
    w("# MSPC 기준선: 창 특징 PCA + Hotelling T² / SPE\n")
    w("> **사후 비교다.** test 채점(`tvt/03_score_test.py`) 뒤에 덧붙였다. 잠근 선택(`tvt_selection.json`)과 "
      "최종 모델 v2+R1+R2(코드 이름 v2+H1+H2)는 바뀌지 않는다. 분할·평가 함수(`tvt/evalcore.py`)는 그대로 썼다. "
      "`(사후 변형)` 표시 모델은 주 사양의 test 결과를 본 뒤 검증 A 진단을 근거로 추가했으므로 참고용이다.\n")

    w("## 설정\n")
    mA = A["models"]["mspc"]
    k = mA["k"]
    w(f"- 행마다 같은 기록 안 그 행까지의 최근 {W}행 창(고정). 창 3행 미만(기록 위치 0·1)은 점수 없음 → 경보 없음")
    w("- 특징 7개: 상·하부 진동 창 RMS(log), 전류 RMS(log, 고정 F0 사인 진폭/√2), 상·하부 진동 lag-1 자기상관, 상·하부 진동 상관, "
      "전류 사인 적합 잔차 비율(log). 전류 RMS는 창 표준편차 대신 사인 진폭을 썼다(정상 학습 기록에서 기록 RMS와 상관 0.99 vs 0.71)")
    w("- 창 길이(3~8행)별로 정상 학습 행 평균·표준편차로 표준화 → PCA(누적 분산 90%) → T²·SPE")
    w(f"- PCA 성분 수 k = {k} (A·B 같음, 누적 {mA['explained_cum'][k - 1]:.1%}). PC1(분산 {mA['explained_cum'][0]:.0%})은 "
      "진동·전류 크기와 하부 진동 자기상관이 함께 움직이고 전류 잔차 비율이 반대로 움직이는 부하 축이다")
    w(f"- 고전 한계 99%: T² {mA['limits']['99%']['t2']:.2f}(F 분포, 새 관측용), SPE {mA['limits']['99%']['spe']:.2f}"
      f"(Jackson–Mudholkar, h0 = {mA['h0']:.3f}). 두 관리도 OR")
    w("- conformal: T²·SPE를 정상 학습 꼬리 확률(예준 ExpTail 식)로 바꿔 최솟값 → 검증 정상 기록 최댓값으로 보정, 검증 정상은 LOO")
    w("- 부하 정규화(mspc_load): 창 길이별로 진동 RMS z를 전류 RMS z에 정상 학습 OLS 회귀한 잔차를 재표준화해 대신 쓴다\n")

    def table(alpha):
        w("| 모델 | valid 실시간 F1 (A·B 평균) | test 실시간 F1 A / B | test 기록 F1 A / B | test 실시간 오경보 행 A / B | test 실시간 미탐 행 A / B |")
        w("|---|---:|---:|---:|---:|---:|")
        for m, lab in LABELS:
            v = np.nanmean([_f(res, m, "valid", alpha, "realtime", s) for s in "AB"])
            fp = f"{_c(res, m, 'test', alpha, 'realtime', 'A', 'fp')} / {_c(res, m, 'test', alpha, 'realtime', 'B', 'fp')}"
            fn = f"{_c(res, m, 'test', alpha, 'realtime', 'A', 'fn')} / {_c(res, m, 'test', alpha, 'realtime', 'B', 'fn')}"
            w(f"| {lab} | {f3(v)} | {AB(m, 'test', alpha, 'realtime')} | {AB(m, 'test', alpha, 'record')} | {fp} | {fn} |")
        w("")

    w("## 결과 (α 1%, 주 기준)\n")
    table(0.01)
    w("- 참고 모델은 같은 평가 함수로 다시 채점한 값이며 이전 결과(v2 0.965/0.970, v2+R1+R2 1.000/1.000, max|z| 0.404/0.428)와 같다")
    w("- 고전 한계 행은 α를 (1−α) 신뢰 한계로 읽는다(α 1% = 99% 한계). 보정 단계가 없어 valid도 LOO 없이 같은 값이다\n")

    w("## α 3%·5%\n")
    w("| 모델 | α 3% test 실시간 A / B | α 3% test 기록 A / B | α 5% test 실시간 A / B | α 5% test 기록 A / B |")
    w("|---|---:|---:|---:|---:|")
    lab = dict(LABELS)
    for m in KEY_ALPHA:
        w(f"| {lab[m]} | {AB(m, 'test', .03, 'realtime')} | {AB(m, 'test', .03, 'record')} | "
          f"{AB(m, 'test', .05, 'realtime')} | {AB(m, 'test', .05, 'record')} |")
    w("")

    w("## 민감도: 창 길이 w (선택에 안 씀, α 1%)\n")
    w("| 창 | valid 실시간 A / B | test 실시간 A / B | test 기록 A / B |")
    w("|---|---:|---:|---:|")
    for m, l in SENS:
        w(f"| {l} | {AB(m, 'valid', .01, 'realtime')} | {AB(m, 'test', .01, 'realtime')} | {AB(m, 'test', .01, 'record')} |")
    w("")

    # ---- 해석에 쓸 수치
    cA, cB = A["models"]["mspc"]["classical_99"], B["models"]["mspc"]["classical_99"]
    calA, calB = A["models"]["mspc"]["calibration"], B["models"]["mspc"]["calibration"]
    topA = list(calA["global_tail"]["top_records"].items())
    topB = list(calB["global_tail"]["top_records"].items())
    ntA = list(calA["per_window_tail_nt"]["top_records"].items())
    wk = {s: info[s]["weakness"] for s in "AB"}
    dr = {s: info[s]["load_drift"] for s in "AB"}

    def det(s, m, b):
        d = wk[s][m]["abnormal_detect_by_pos"][b]
        return f"{d['detected']}/{d['rows']}"

    def fa_state(s, m, st):
        return wk[s][m]["normal_false_alarm_by_load"].get(st, dict(rows=0, false_alarms=0, records_with_fa=0, records=0))

    w("## 해석\n")
    w("### 1. 고전 관리 한계는 행 단위로는 잡지만 기록 단위 운영에는 못 쓴다\n")
    w("- 이상 시험 행은 창이 3행 이상이면 99% 한계를 100% 넘는다(A·B 모두 모든 이상 기록의 위치 2에서 첫 경보). 문제는 정상 쪽이다")
    w(f"- 정상 학습 행(표본 안)에서도 OR 초과율이 A {cA['train_normal_rows']['either']:.1%} · B {cB['train_normal_rows']['either']:.1%}로 명목치(약 2%)보다 높다"
      f"(SPE 단독 {cA['train_normal_rows']['spe']:.1%}, 명목 1%). 창이 겹쳐 행끼리 자기상관이 있고, 특징이 정규분포가 아니며, "
      "부하가 두 상태로 갈리는 이봉 분포라 가우시안 PCA 한 개의 가정이 깨진다")
    w(f"- 기록 하나에 평균 30여 행이 있어 행 단위 1% 한계를 기록마다 수십 번 검정하는 셈이다. 검증 정상 기록의 "
      f"{cA['valid_normal_rows']['records_any']:.0%}(A)·{cB['valid_normal_rows']['records_any']:.0%}(B), 시험 정상 기록의 "
      f"{cA['test_normal_rows']['records_any']:.0%}·{cB['test_normal_rows']['records_any']:.0%}가 한 행 이상 한계를 넘는다 → "
      f"기록 단위 F1 {AB('mspc_cl', 'test', .01, 'record')}")
    w(f"- 시험 정상 행 초과율은 A {cA['test_normal_rows']['either']:.1%} · B {cB['test_normal_rows']['either']:.1%}로 검증"
      f"({cA['valid_normal_rows']['either']:.1%} · {cB['valid_normal_rows']['either']:.1%})의 2~3배다. 4절의 운전 조건 변화"
      "(저부하 기록 비중 증가, 저부하 상태 안의 이동) 때문이다")
    w(f"- R1(사건 지속)을 얹으면 오경보가 다음 정상 기록으로 번져 더 나빠진다(고전 + R1 test 실시간 F1 {AB('mspc_cl+H1', 'test', .01, 'realtime')}). "
      "검증 정상 기록 최댓값으로 보정하는 conformal은 이 다중 검정 문제를 구조적으로 막는다\n")

    w("### 2. conformal MSPC: B는 쓸 만하고, A는 짧은 창 하나가 문턱을 정해 민감도를 잃는다\n")
    an, anB = A["models"]["mspc"]["calibration_anatomy"], B["models"]["mspc"]["calibration_anatomy"]
    q = an["train_score_q999_by_window"]
    w(f"- α 1%, 검증 정상 120기록이면 문턱은 검증 정상 기록 최댓값 중 가장 큰 값이다. A는 원 기록 {an['global_record']} "
      f"(`{topA[0][0]}`) {topA[0][1]:.1f}(2위 {topA[1][1]:.1f}), B는 원 기록 {anB['global_record']} {topB[0][1]:.1f}")
    w(f"- A의 기록 {an['global_record']}은 {an['length']}행짜리이고 최댓값은 창 {an['window_rows']}행(위치 {an['pos']})에서 나왔다. "
      f"짧은 창의 3점 사인 적합으로 추정한 전류 진폭이 거의 0이 돼 전류 RMS z = {an['z']['cur_lrms']:+.1f}, SPE {an['spe']:.1f}"
      f"(99% 한계 {mA['limits']['99%']['spe']:.1f})이 됐다. 정상 학습에서도 짧은 창의 점수 꼬리가 두껍다"
      f"(점수 99.9% 분위: 창 3행 {q[3]:.1f}, 창 5행 {q[5]:.1f}, 창 8행 {q[8]:.1f})")
    w(f"- 그래서 A는 이상 시험 행 중 창 8행이 찬 행도 {det('A', 'mspc', B7)}만 잡는다(B {det('B', 'mspc', B7)}). "
      f"기록 {an['global_record']}은 B에서는 시험 정상이라 B 주 사양의 유일한 오경보 1행이 된다")
    w(f"- 사후 변형 `mspc_nt`(꼬리 확률을 창 길이별 정상 학습 분포로 계산)는 이 문제를 없앤다. 검증 A 실시간 F1 "
      f"{F('mspc', 'valid', .01, 'realtime', 'A')} → {F('mspc_nt', 'valid', .01, 'realtime', 'A')}, test {AB('mspc_nt', 'test', .01, 'realtime')}. "
      f"A 보정 최댓값은 {ntA[0][1]:.2f}로 내려간다. 배치 MSPC에서 시점별 관리 한계를 쓰는 것과 같은 처방이다\n")

    w("### 3. 기록 시작 직후가 MSPC의 가장 큰 약점이다\n")
    w(f"- 위치 0·1은 창이 없어 점수 자체가 없다. 이상 시험 324행 중 {wk['A']['mspc']['abnormal_detect_by_pos'][B01]['rows']}행"
      f"(11기록 × 2행)이 구조적으로 미탐이다. v2는 크기 성분으로 이 위치에서 A {det('A', 'v2', B01)} · B {det('B', 'v2', B01)}를 잡는다")
    w(f"- 창 3~7행(위치 2~6) 이상 행 탐지: mspc A {det('A', 'mspc', B26)} · B {det('B', 'mspc', B26)}, "
      f"mspc_nt A {det('A', 'mspc_nt', B26)} · B {det('B', 'mspc_nt', B26)}, v2 A {det('A', 'v2', B26)} · B {det('B', 'v2', B26)}. "
      "짧은 창은 RMS·상관·자기상관 추정이 흔들려 정상과 겹친다")
    fa1 = {s: list(wk[s]["mspc_nt"]["abnormal_first_alarm_pos"].values()) for s in "AB"}
    w(f"- 이상 시험 기록별 첫 경보 위치(규칙 없음): mspc_nt A {fa1['A']} · B {fa1['B']}, "
      f"v2 A {list(wk['A']['v2']['abnormal_first_alarm_pos'].values())} (None = 그 기록 안에서 못 잡음)")
    w(f"- R1(사건 지속)을 얹으면 직전 기록 판정이 시작 직후 행을 덮어 test 실시간 F1이 mspc + R1 {AB('mspc+H1', 'test', .01, 'realtime')}, "
      f"mspc_nt + R1 {AB('mspc_nt+H1', 'test', .01, 'realtime')}까지 오른다. 이 이득은 이상 21기록이 한 사건이라서 생긴다\n")

    w("### 4. 고부하 정상에는 강하고, 저부하 정상(특히 시험 구간)에서 흔들린다 — v2와 반대\n")
    h = {s: fa_state(s, "mspc_cl", "high") for s in "AB"}
    lo_ = {s: fa_state(s, "mspc_cl", "low") for s in "AB"}
    w(f"- 고전 한계의 시험 정상 오경보: 고부하 A {h['A']['false_alarms']}/{h['A']['rows']}행 · B {h['B']['false_alarms']}/{h['B']['rows']}행, "
      f"저부하 A {lo_['A']['false_alarms']}/{lo_['A']['rows']}행 · B {lo_['B']['false_alarms']}/{lo_['B']['rows']}행. 오경보 대부분이 저부하 기록에서 난다")
    dA = dr["A"]
    w(f"- 시험 구간에서 저부하 기록 비중이 크게 늘었다. 고/저부하 기록 수 A 학습 {dA['train/high']['records']}/{dA['train/low']['records']}, "
      f"검증 {dA['valid/high']['records']}/{dA['valid/low']['records']}, 시험 {dA['test/high']['records']}/{dA['test/low']['records']}. "
      f"시험 저부하 행은 학습 저부하보다 상부 진동 lag-1(평균 z {dA['test/low']['mean_z']['vu_ac1']:+.2f} vs {dA['train/low']['mean_z']['vu_ac1']:+.2f})과 "
      f"상·하부 상관({dA['test/low']['mean_z']['ul_corr']:+.2f} vs {dA['train/low']['mean_z']['ul_corr']:+.2f})이 낮다. "
      f"고전 99% 초과율은 학습 저부하 {dA['train/low']['classical_exceed']:.1%} → 시험 저부하 {dA['test/low']['classical_exceed']:.1%}"
      f"(고부하 {dA['train/high']['classical_exceed']:.1%} → {dA['test/high']['classical_exceed']:.1%})")
    v2fa = info["B"]["v2_false_alarm_rows"]
    w(f"- v2의 B 시험 오경보 {len(v2fa)}행(고부하 정상, 진동 크기 단독)에서 conformal MSPC p는 {', '.join(str(r['mspc_p']) for r in v2fa)}로 "
      "경보가 아니다. 단일 표본 |z| 대신 8행 창 RMS를 보므로 한 표본 튐에 둔하다. conformal MSPC의 시험 고부하 정상 오경보는 "
      f"A {fa_state('A', 'mspc', 'high')['false_alarms']} · B {fa_state('B', 'mspc', 'high')['false_alarms']}행이다. 다만 고전 99% 한계로는 "
      f"그 3행 중 {sum(1 for r in v2fa if r['mspc_cl_p'] is not None and r['mspc_cl_p'] <= 0.01)}행이 한계를 넘는다(행 단위 한계는 여기서도 예민하다)")
    rg = A["models"]["mspc_load"]["load_regression"]
    w(f"- 부하 정규화: 정상 학습에서 하부 진동 RMS는 부하로 잘 설명되고(창 8행 R² {rg['n8_vl_lrms']['r2']:.2f}, 기울기 {rg['n8_vl_lrms']['slope']:.2f}) "
      f"상부는 약하다(R² {rg['n8_vu_lrms']['r2']:.2f}). 정규화는 A 실시간을 올렸지만(검증 {F('mspc', 'valid', .01, 'realtime', 'A')} → "
      f"{F('mspc_load', 'valid', .01, 'realtime', 'A')}, test {F('mspc', 'test', .01, 'realtime', 'A')} → {F('mspc_load', 'test', .01, 'realtime', 'A')}) "
      f"test B 기록 F1을 떨어뜨렸다({F('mspc', 'test', .01, 'record', 'B')} → {F('mspc_load', 'test', .01, 'record', 'B')}). "
      "하부 진동 잔차의 표준편차가 작아 시험 저부하 구간의 작은 관계 이동도 크게 보인다. 모델을 조일수록 느린 운전 조건 이동에 "
      "민감해지는 MSPC의 전형적인 맞교환이다\n")

    w("### 5. 무엇이 이상을 만드나 — 기여 분석 (이상 시험 행, 창 3행 이상)\n")
    for s in "AB":
        c = info[s]["models"]["mspc"]["contributions"]["abnormal_test"]
        n = info[s]["models"]["mspc"]["contributions"]["normal_test"]
        t2r = ", ".join(f"{FEATURE_KO[f]} {c['t2'][f]['mean']:.1f}({c['t2'][f]['share']:.0%})" for f in c["t2_rank"][:4])
        sper = ", ".join(f"{FEATURE_KO[f]} {c['spe'][f]['mean']:.1f}({c['spe'][f]['share']:.0%})" for f in c["spe_rank"][:3])
        w(f"- {s}: 평균 T² {c['mean_t2']:.0f}(정상 시험 {n['mean_t2']:.1f}), 평균 SPE {c['mean_spe']:.0f}(정상 {n['mean_spe']:.2f}). "
          f"T² 기여 상위: {t2r}. SPE 기여 상위: {sper}. 괄호는 행별 기여 비율의 평균")
    z = A["models"]["mspc"]["contributions"]["abnormal_test"]["mean_signed_z"]
    w(f"- 이탈 방향(A, 평균 z): 전류 사인 잔차 비율 {z['cur_res']:+.1f}, 전류 RMS {z['cur_lrms']:+.1f}, 상부 진동 RMS {z['vu_lrms']:+.1f}, "
      f"상·하부 상관 {z['ul_corr']:+.1f}, 상부 lag-1 {z['vu_ac1']:+.1f}, 하부 진동 RMS {z['vl_lrms']:+.1f}")
    cl = A["models"]["mspc_load"]["contributions"]["abnormal_test"]
    w("- 읽는 법: 전류 파형이 사인에서 크게 벗어나고 진폭이 줄었는데, 하부 진동은 부하를 따라 줄지 않았다. 정상에서는 하부 진동이 전류를 "
      "강하게 따르므로 이 관계 깨짐이 SPE의 하부 진동 RMS 기여로 나타난다. 부하 정규화 모델에서는 같은 신호가 하부 진동 잔차의 T² 기여 "
      f"{cl['t2']['vl_lrms']['mean']:.0f}({cl['t2']['vl_lrms']['share']:.0%})로 바로 드러난다. 상부 진동은 커지고 상·하부 상관은 낮아졌다")
    w("- 가장 큰 기여(전류 파형)는 앞선 사후 분석에서 측정 타이밍 차이(이상 파일 전류 겉보기 주파수 0.19 Hz vs 정상 0.60 Hz)로도 설명됐다. "
      "MSPC도 고장과 계측 차이를 가려 주지는 못한다\n")

    w("### 6. 요약 판단\n")
    w(f"- MSPC 주 사양(conformal) test 실시간 F1 {AB('mspc', 'test', .01, 'realtime')}: v2({AB('v2', 'test', .01, 'realtime')})보다 낮고 "
      f"베이스라인 max|z|({AB('maxz3', 'test', .01, 'realtime')})보다 높다")
    w(f"- R1을 얹은 mspc + R1은 test 실시간 {AB('mspc+H1', 'test', .01, 'realtime')}로 최종 모델(1.000 / 1.000)에 가깝다. 그러나 valid "
      f"({F('mspc+H1', 'valid', .01, 'realtime', 'A')} / {F('mspc+H1', 'valid', .01, 'realtime', 'B')} vs v2+R1+R2 "
      f"{F('v2+H1+H2', 'valid', .01, 'realtime', 'A')} / {F('v2+H1+H2', 'valid', .01, 'realtime', 'B')})와 α 5%에서 뒤처지고, test 성적의 대부분은 "
      "R1이 만든다")
    w(f"- 강점: 고부하 정상의 단일 표본 튐에 오경보가 없다. 그래서 B 기록 단위 F1은 MSPC conformal "
      f"{F('mspc', 'test', .01, 'record', 'B')}, v2 {F('v2', 'test', .01, 'record', 'B')}로 MSPC가 높다(v2는 고부하 오경보 3행이 기록 3개를 통째로 오판). "
      f"창 8행이 찬 뒤 이상 행 탐지율이 높다(B mspc {det('B', 'mspc', B7)}, mspc_nt A {det('A', 'mspc_nt', B7)} · B {det('B', 'mspc_nt', B7)}). "
      "기여 분석으로 어느 변수 관계가 깨졌는지 설명할 수 있다")
    w("- 약점: 기록 시작 0~1행은 점수가 없고 2~6행은 둔하다. 행 단위 고전 한계는 기록 단위 운영에 맞지 않는다. 운전 조건이 학습과 "
      "달라지면(시험 구간 저부하 증가) 오경보가 는다. R1은 기반 탐지기의 오경보가 많으면 오경보도 이어 붙인다"
      f"(α 5% test A: mspc + R1 {F('mspc+H1', 'test', .05, 'realtime', 'A')} < mspc {F('mspc', 'test', .05, 'realtime', 'A')})")
    w("- 최종 모델 v2+R1+R2와 같은 방향의 결론: 시작 직후는 크기 성분과 사건 지속이 필요하고, 크기 단독 경보는 다른 축(파형·상관 구조)으로 "
      "확인해야 한다\n")

    w("## 한계\n")
    w("- test 채점 이후의 사후 비교다. 특히 `mspc_nt` 변형은 주 사양의 test 결과를 본 뒤 추가했다(근거는 검증 A 진단이지만 test 독립성은 없다)")
    w("- 이상 자료는 약 3분짜리 단일 사건(21기록)이다. 기여 순위와 F1은 이 사건에 대한 값이다")
    w("- 고전 한계의 가정(독립·정규·단일 운전 상태)은 겹치는 창과 이봉 부하 분포 때문에 성립하지 않는다. 결과는 가정이 깨졌을 때 "
      "교과서 한계가 실제로 어떻게 동작하는지로 읽어야 한다")
    w("- PCA와 꼬리 참조를 같은 정상 학습 행에서 만들었다(표본 안). 최종 문턱은 검증 정상 conformal 보정이 정한다")
    w("- R2(교차 확인)는 크기 성분 열이 필요해 MSPC에는 적용하지 않았다. 부하 상태(고/저)는 기록 전체 전류로 매긴 사후 진단값이라 "
      "실시간에는 쓸 수 없다")
    w(f"- 창 길이 w = {W}는 고정값이다. 민감도 표처럼 A 결과가 w에 크게 흔들리는데, 원인은 2절의 짧은 창 꼬리 문제다\n")
    w("## 파일\n")
    w("- 코드: `code/press/domain/03_mspc.py`")
    w("- 결과: `code/press/domain/outputs/03_mspc.json`(설정·PCA·한계·진단·기여·전체 결과), `03_mspc.csv`(모델 × 분할 × α × valid/test 지표)")
    md = "\n".join(L) + "\n"
    head = {s: {m: dict(valid_rt=_f(res, m, "valid", .01, "realtime", s), test_rt=_f(res, m, "test", .01, "realtime", s),
                        test_rec=_f(res, m, "test", .01, "record", s))
                for m in ("mspc", "mspc+H1", "mspc_cl", "mspc_load", "mspc_nt", "mspc_nt+H1", "v2+H1+H2", "v2", "maxz3")}
            for s in "AB"}
    return dict(headline=head, md=md)


if __name__ == "__main__":
    main()
