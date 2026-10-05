"""성분 융합: 극값 이론 꼬리 p값 + Cauchy 결합(ACAT). 모든 계산은 로그 영역(언더플로·포화 없음).

1. 성분마다 정상 학습 점수로 꼬리 모델을 만든다 (TailModel)
   - 문턱 u(학습 98분위) 이하: 경험 꼬리확률 #{ref >= s}/n
   - u 초과: 일반화 파레토(GPD) peaks-over-threshold — Pickands–Balkema–de Haan, 이상탐지 문턱 SPOT(Siffer et al., KDD 2017)
     형상 ξ<0(유한 끝점)이면 ξ=0(지수 꼬리)으로 둬서 p가 0이 되지 않게 한다
2. 성분 p값을 ACAT(Liu & Xie, JASA 2020)로 결합: T = mean tan((0.5 - p_i)π), p = 0.5 - arctan(T)/π
   - 성분 간 상관이 있어도 꼬리에서 유효한 결합. 가중치는 균등, 사전 고정. 점수가 없는 성분(창 준비 중)은 빼고 평균
   - p가 아주 작으면 tan((0.5-p)π) ≈ 1/(πp) 이므로 log T = logsumexp(-log p_i) - log(πk) 로 계산 (포화 없음)
3. 결합 점수 -log10(p_ACAT)는 보정 구간에서 다시 conformal 보정한다 (evaluate.py) → 오경보 보장은 그 단계에서 나온다
"""
import numpy as np
from scipy.special import logsumexp
from scipy.stats import genpareto

TAIL_Q = 0.98
SMALL = 1e-8          # 이보다 작은 p는 tan 대신 1/(πp) 근사를 로그로 계산
LN10 = np.log(10)


class TailModel:
    def __init__(self, ref):
        ref = np.asarray(ref, float)
        ref = ref[np.isfinite(ref)]
        self.sorted, self.n = np.sort(ref), len(ref)
        self.u = float(np.quantile(ref, TAIL_Q))
        exc = ref[ref > self.u] - self.u
        self.pu = len(exc) / self.n
        xi, _, sigma = genpareto.fit(exc, floc=0)
        if xi < 0:
            xi, sigma = 0.0, float(exc.mean())
        self.xi, self.sigma = float(xi), float(sigma)

    def logp(self, s):
        """자연로그 꼬리확률. NaN 점수는 NaN."""
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        v = s[ok]
        ge = self.n - np.searchsorted(self.sorted, v, side="left")
        lp = np.log(np.maximum(ge / self.n, self.pu))
        hi = v > self.u
        x = (v[hi] - self.u) / self.sigma
        lp[hi] = np.log(self.pu) + (-x if self.xi == 0 else -np.log1p(self.xi * x) / self.xi)
        out[ok] = np.minimum(lp, 0.0)
        return out

    def p(self, s):
        return np.exp(self.logp(s))


def acat_log10(LP):
    """LP (n, k) 자연로그 p, NaN = 성분 없음. 반환: -log10(p_ACAT) (n,) — 상한 없음."""
    avail = np.isfinite(LP)
    k = np.maximum(avail.sum(1), 1)
    p = np.exp(np.where(avail, LP, 0.0))
    small = avail & (p < SMALL)
    # 보통 항: tan((0.5-p)π)
    t_norm = np.where(avail & ~small, np.tan((0.5 - np.where(avail & ~small, p, 0.5)) * np.pi), 0.0).sum(1)
    # 큰 항: log(1/(πp)) = -log p - log π
    big = np.where(small, -LP - np.log(np.pi), -np.inf)
    has_big = small.any(1)
    lse = logsumexp(big, axis=1, keepdims=False) if big.size else np.full(len(LP), -np.inf)
    out = np.empty(len(LP))
    # 큰 항이 있으면 T ≈ exp(lse)/k (보통 항은 상대적으로 무시할 만큼 작지만 보정해 더한다)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        rel = t_norm[has_big] * np.exp(-lse[has_big])
        logT = lse[has_big] + np.log1p(np.clip(rel, -0.999999, None)) - np.log(k[has_big])
        out[has_big] = (np.log(np.pi) + logT) / LN10          # p ≈ 1/(πT)
    T = t_norm[~has_big] / k[~has_big]
    p_acat = np.where(T > 1e12, 1 / (np.pi * np.maximum(T, 1e-300)), 0.5 - np.arctan(T) / np.pi)
    out[~has_big] = -np.log10(np.clip(p_acat, 1e-300, 1.0))
    return out


class Fusion:
    """성분 이름 목록으로 꼬리 모델을 만들고, 결합 점수(-log10 p)와 성분 p값을 낸다."""

    def __init__(self, train_components, names):
        self.names = list(names)
        self.tails = {n: TailModel(train_components[n]) for n in self.names}

    def component_logp(self, comp):
        return {n: self.tails[n].logp(comp[n]) for n in self.names}

    def component_p(self, comp):
        return {n: self.tails[n].p(comp[n]) for n in self.names}

    def score(self, comp, subset=None, how="acat"):
        """반환: (결합 점수 -log10 p, p). 점수는 상한이 없고, p는 표시용(아주 작으면 0으로 보일 수 있음)."""
        names = self.names if subset is None else list(subset)
        LP = np.column_stack([self.tails[n].logp(comp[n]) for n in names])
        if how == "acat":
            s = acat_log10(LP)
        elif how == "min":  # 민감도: 가장 작은 성분 p (max 융합과 같은 순서)
            s = -np.nanmin(LP, axis=1) / LN10
        else:
            raise ValueError(how)
        return s, np.power(10.0, -s)
