"""기준모델과 ML 모델. 모두 fit(X, y) / predict(X) 인터페이스."""
from __future__ import annotations

import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import config as C

CATEGORICAL = ["slot", "daytype3", "daytype4", "regime", "regime_prev", "hour", "dow", "q_in_hour"]


# ---------------------------------------------------------------- 기준모델

class Persistence:
    """발행 시점 마지막 관측값 유지(과제 A). 마지막 구간이 결측이면 그 이전 최근 관측 → 같은 요일유형 최근일 → 학습 평균."""
    name = "BL1_persistence"

    def fit(self, X, y):
        self.mu_ = float(np.nanmean(y))
        return self

    def predict(self, X):
        p = X["lag_0"].to_numpy(dtype=float).copy()
        for c in [f"lag_{k}" for k in range(1, 8)] + ["same_dt_last"]:
            m = ~np.isfinite(p)
            if not m.any():
                break
            p[m] = X[c].to_numpy(dtype=float)[m]
        p[~np.isfinite(p)] = self.mu_
        return p


class SameDaytype:
    """같은 요일유형의 가장 최근 원본일 같은 슬롯. 없으면 전주 → 전일 → 학습 슬롯 평균."""
    name = "BL2_same_daytype"

    def fit(self, X, y):
        self.slot_mean_ = pd.Series(np.asarray(y), index=X["slot"].to_numpy()).groupby(level=0).mean()
        return self

    def predict(self, X):
        p = X["same_dt_last"].to_numpy(dtype=float).copy()
        for c in ("lag_d7", "lag_d1"):
            m = np.isnan(p)
            p[m] = X[c].to_numpy(dtype=float)[m]
        m = np.isnan(p)
        p[m] = self.slot_mean_.reindex(X["slot"].to_numpy()[m]).to_numpy()
        return p


class Profile:
    """학습기간 (요일유형4 × 가동 체제 × 슬롯) 평균. 체제: 0 정지, 1 부분(<5000), 2 전면 가동."""
    name = "BL3_profile"

    def __init__(self, use_plan: bool = True):
        self.use_plan = use_plan

    def fit(self, X, y):
        d = pd.DataFrame({"dt": X["daytype4"].to_numpy(), "pc": X["regime"].to_numpy() if self.use_plan else 0,
                          "slot": X["slot"].to_numpy(), "y": np.asarray(y, float)})
        self.t3_ = d.groupby(["dt", "pc", "slot"])["y"].mean()
        self.t_pc_ = d.groupby(["pc", "slot"])["y"].mean()
        self.t_slot_ = d.groupby("slot")["y"].mean()
        return self

    def predict(self, X):
        pc = X["regime"].to_numpy() if self.use_plan else np.zeros(len(X))
        k3 = pd.MultiIndex.from_arrays([X["daytype4"].to_numpy(), pc, X["slot"].to_numpy()])
        p = self.t3_.reindex(k3).to_numpy(dtype=float).copy()
        m = np.isnan(p)
        if m.any():
            k2 = pd.MultiIndex.from_arrays([pc[m], X["slot"].to_numpy()[m]])
            p[m] = self.t_pc_.reindex(k2).to_numpy()
        m = np.isnan(p)
        if m.any():
            p[m] = self.t_slot_.reindex(X["slot"].to_numpy()[m]).to_numpy()
        return p


# ---------------------------------------------------------------- 선형·트리·신경망

def _prep(features: list[str], scale: bool = True) -> ColumnTransformer:
    cats = [c for c in features if c in CATEGORICAL]
    nums = [c for c in features if c not in CATEGORICAL]
    num_steps = [("imp", SimpleImputer(strategy="median", add_indicator=True))]
    if scale:
        num_steps.append(("sc", StandardScaler()))
    return ColumnTransformer([
        ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                          ("oh", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), cats),
        ("num", Pipeline(num_steps), nums),
    ])


class RidgeModel:
    name = "BL4_ridge"

    def __init__(self, features, alpha: float = 3.0):
        self.features = list(features)
        self.alpha = alpha

    def fit(self, X, y):
        self.pipe_ = Pipeline([("prep", _prep(self.features)), ("m", Ridge(alpha=self.alpha))])
        self.pipe_.fit(X[self.features], y)
        return self

    def predict(self, X):
        return self.pipe_.predict(X[self.features])


class MLPModel:
    name = "M3_mlp"

    def __init__(self, features, hidden=(128, 64), alpha=1e-3, seed=C.SEED):
        self.features = list(features)
        self.hidden = hidden
        self.alpha = alpha
        self.seed = seed

    def fit(self, X, y):
        y = np.asarray(y, float)
        self.mu_, self.sd_ = y.mean(), y.std() + 1e-9
        self.pipe_ = Pipeline([("prep", _prep(self.features)),
                               ("m", MLPRegressor(hidden_layer_sizes=self.hidden, alpha=self.alpha,
                                                  learning_rate_init=1e-3, max_iter=400, early_stopping=True,
                                                  validation_fraction=0.15, n_iter_no_change=20,
                                                  random_state=self.seed))])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.pipe_.fit(X[self.features], (y - self.mu_) / self.sd_)
        return self

    def predict(self, X):
        return self.pipe_.predict(X[self.features]) * self.sd_ + self.mu_


class HGBModel:
    name = "M2_hgb"

    def __init__(self, features, max_iter=600, learning_rate=0.04, max_leaf_nodes=31, min_samples_leaf=20,
                 l2=1.0, seed=C.SEED):
        self.features = list(features)
        self.kw = dict(max_iter=max_iter, learning_rate=learning_rate, max_leaf_nodes=max_leaf_nodes,
                       min_samples_leaf=min_samples_leaf, l2_regularization=l2, random_state=seed)

    def fit(self, X, y):
        self.m_ = HistGradientBoostingRegressor(**self.kw).fit(X[self.features], y)
        return self

    def predict(self, X):
        return self.m_.predict(X[self.features])


LGB_BASE = dict(n_estimators=800, learning_rate=0.03, num_leaves=31, min_child_samples=20,
                subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0,
                n_jobs=4, deterministic=True, force_row_wise=True, verbose=-1)


class LGBModel:
    name = "M1_lgbm"

    def __init__(self, features, params: dict | None = None, monotone: dict | None = None,
                 objective: str = "regression", alpha: float | None = None, seed: int = C.SEED):
        self.features = list(features)
        self.params = {**LGB_BASE, **(params or {})}
        self.monotone = monotone or {}
        self.objective = objective
        self.alpha = alpha
        self.seed = seed

    def _model(self):
        kw = dict(self.params, random_state=self.seed, objective=self.objective)
        if self.alpha is not None:
            kw["alpha"] = self.alpha
        if self.monotone:
            kw["monotone_constraints"] = [int(self.monotone.get(c, 0)) for c in self.features]
            kw["monotone_constraints_method"] = "advanced"
        return lgb.LGBMRegressor(**kw)

    def fit(self, X, y):
        self.m_ = self._model().fit(X[self.features], np.asarray(y, float))
        return self

    def predict(self, X):
        return self.m_.predict(X[self.features])

    def contrib(self, X):
        return self.m_.predict(X[self.features], pred_contrib=True)


class LGBClassifier:
    name = "C_lgbm"

    def __init__(self, features, params: dict | None = None, seed: int = C.SEED):
        self.features = list(features)
        p = {**LGB_BASE, "n_estimators": 400, **(params or {})}
        self.params = p
        self.seed = seed

    def fit(self, X, y):
        self.m_ = lgb.LGBMClassifier(**self.params, random_state=self.seed).fit(X[self.features], np.asarray(y, int))
        return self

    def predict_proba(self, X):
        return self.m_.predict_proba(X[self.features])[:, 1]


# ---------------------------------------------------------------- 구조 모델: 유사 계획일·수준 보정·잔차 보정

def _analog_base(X) -> np.ndarray:
    """기준 유사일(체제별) → 없으면 같은 요일유형 최근일 → 전주 같은 슬롯."""
    p = X["analog_mean"].to_numpy(dtype=float).copy()
    for c in ("same_dt_last", "lag_d7"):
        m = ~np.isfinite(p)
        if m.any():
            p[m] = X[c].to_numpy(dtype=float)[m]
    return p


class AnalogDay:
    """유사일 모델. col='analog_regime'(체제별 최근 k일, BL5) 또는 'analog_sched'(운영일정 kNN, M5)."""
    name = "BL5_regime_analog"

    def __init__(self, col: str = "analog_regime"):
        self.col = col

    def fit(self, X, y):
        self.mu_ = float(np.nanmean(y))
        return self

    def predict(self, X):
        p = X[self.col].to_numpy(dtype=float).copy()
        for c in ("same_dt_last", "lag_d7"):
            m = ~np.isfinite(p)
            if m.any():
                p[m] = X[c].to_numpy(dtype=float)[m]
        p[~np.isfinite(p)] = self.mu_
        return p


def analog_level(X, rho: float) -> np.ndarray:
    """과제 A: 유사일 프로파일 + 발행 시점 편차의 지수 감쇠 보정."""
    h = int(X["horizon"].iloc[0])
    a = _analog_base(X)
    dev = X["lag_0"].to_numpy(dtype=float) - X["analog_now"].to_numpy(dtype=float)
    p = a + (rho ** h) * np.nan_to_num(dev)
    m = ~np.isfinite(p)
    p[m] = X["lag_0"].to_numpy(dtype=float)[m]
    return p


class AnalogLevel:
    name = "M6_analog_level"

    def __init__(self, rho: float = 0.9):
        self.rho = rho

    def fit(self, X, y):
        self.mu_ = float(np.nanmean(y))
        return self

    def predict(self, X):
        p = analog_level(X, self.rho)
        p[~np.isfinite(p)] = self.mu_
        return p


HYBRID_PARAMS = dict(num_leaves=15, min_child_samples=50, n_estimators=300, learning_rate=0.03)
HYBRID_PARAMS_B = dict(num_leaves=7, min_child_samples=100, n_estimators=200, learning_rate=0.03)


class Hybrid:
    """구조 모델 예측을 기준값으로 두고 LightGBM(Huber)이 잔차를 보정한다.

    task='A': 기준 = AnalogLevel(rho). task='B': 기준 = AnalogDay.
    기준 예측값 자체도 특징(base_pred)으로 넣는다. 단조 제약은 선택.
    """
    name = "M7_hybrid"

    def __init__(self, features, task: str, rho: float = 0.9, params: dict | None = None,
                 huber_alpha: float = 10.0, monotone: dict | None = None, seed: int = C.SEED):
        self.features = list(features)
        self.task = task
        self.rho = rho
        self.params = params or (HYBRID_PARAMS if task == "A" else HYBRID_PARAMS_B)
        self.huber_alpha = huber_alpha
        self.monotone = monotone
        self.seed = seed

    def base(self, X):
        return analog_level(X, self.rho) if self.task == "A" else _analog_base(X)

    def fit(self, X, y):
        b = self.base(X)
        ok = np.isfinite(b)
        Xf = X.assign(base_pred=b)
        self.inner_ = LGBModel(self.features + ["base_pred"], params=self.params, objective="huber",
                               alpha=self.huber_alpha, monotone=self.monotone, seed=self.seed)
        self.inner_.fit(Xf.loc[ok], np.asarray(y, float)[ok] - b[ok])
        self.mu_ = float(np.nanmean(y))
        return self

    def predict(self, X):
        b = self.base(X)
        p = b + self.inner_.predict(X.assign(base_pred=b))
        p[~np.isfinite(p)] = self.mu_
        return p

    def contrib(self, X):
        b = self.base(X)
        return self.inner_.contrib(X.assign(base_pred=b))


class Blend:
    """고정 가중 평균 앙상블(가중치는 교차검증 OOF에서 정한다)."""
    name = "M8_blend"

    def __init__(self, members: list, weights: list[float]):
        self.members = members
        self.weights = weights

    def fit(self, X, y):
        for m in self.members:
            m.fit(X, y)
        return self

    def predict(self, X):
        return sum(w * m.predict(X) for m, w in zip(self.members, self.weights))


class DayVectorMLP:
    """과제 B: 하루 96구간을 한 번에 출력하는 다층 퍼셉트론(유사일 프로파일 대비 잔차를 학습).

    입력 = 날짜 단위(체제·전날 체제·요일유형4 원핫·일 최고/평균 기온·D-1 주간 수준·D-2 평균/최대)
    + 유사일 프로파일 96. 출력 = y(96) − 유사일(96). v2.0: 시간별 생산량 파생 일 계획 세부는 입력에서 뺐다.
    학습일 = 정답 96개가 모두 학습 가능한 날.
    """
    name = "M3d_dayvec_mlp"
    DAY_COLS = ["regime", "regime_prev", "tmax_day", "tmean_day", "d1_dayshift_mean", "d2_mean", "d2_max"]

    def __init__(self, hidden=(64,), alpha=1e-2, seed=C.SEED):
        self.hidden = hidden
        self.alpha = alpha
        self.seed = seed

    def _day_matrix(self, X):
        g = X.groupby(X.index.normalize())
        dates, feats, base = [], [], []
        for d, x in g:
            if len(x) != 96:
                continue
            x = x.sort_index()
            row = [x[c].iloc[0] for c in self.DAY_COLS]
            row += list(np.eye(4)[int(x["daytype4"].iloc[0])])
            b = x["analog_regime"].to_numpy(dtype=float).copy()
            for c in ("same_dt_last", "lag_d7"):
                m = ~np.isfinite(b)
                b[m] = x[c].to_numpy(dtype=float)[m]
            dates.append(d)
            feats.append(row)
            base.append(b)
        return dates, np.array(feats, float), np.array(base, float)

    def fit(self, X, y):
        dates, F_, B = self._day_matrix(X)
        yv = pd.Series(np.asarray(y, float), index=X.index)
        Y = np.array([yv.loc[d:d + pd.Timedelta(minutes=23 * 60 + 45)].to_numpy() if len(yv.loc[d:d + pd.Timedelta(minutes=23 * 60 + 45)]) == 96 else np.full(96, np.nan) for d in dates])
        ok = np.isfinite(Y).all(axis=1) & np.isfinite(B).all(axis=1)
        self.fill_ = np.nanmean(Y[ok], axis=0) if ok.any() else np.zeros(96)
        Xin = np.hstack([F_, np.nan_to_num(B, nan=0.0) / 100.0])
        self.imp_ = SimpleImputer(strategy="median").fit(Xin[ok])
        self.sc_ = StandardScaler().fit(self.imp_.transform(Xin[ok]))
        R = (Y[ok] - B[ok]) / 20.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.m_ = MLPRegressor(hidden_layer_sizes=self.hidden, alpha=self.alpha, max_iter=2000,
                                   learning_rate_init=1e-3, random_state=self.seed)
            self.m_.fit(self.sc_.transform(self.imp_.transform(Xin[ok])), R)
        self.mu_ = float(np.nanmean(y))
        return self

    def predict(self, X):
        dates, F_, B = self._day_matrix(X)
        out = pd.Series(np.nan, index=X.index)
        if dates:
            Bf = np.where(np.isfinite(B), B, self.fill_)
            Xin = np.hstack([F_, np.nan_to_num(B, nan=0.0) / 100.0])
            R = self.m_.predict(self.sc_.transform(self.imp_.transform(Xin))) * 20.0
            P = Bf + R.reshape(len(dates), 96)
            for d, pv in zip(dates, P):
                sl = out.loc[d:d + pd.Timedelta(minutes=23 * 60 + 45)]
                out.loc[sl.index] = pv[: len(sl)]
        p = out.to_numpy(dtype=float).copy()
        p[~np.isfinite(p)] = self.mu_
        return p


class AnalogAdjusted:
    """과제 B 구조 모델: 유사일 + 선형 보정(가동일 주간에만).

    ŷ = 유사일 + 가동주간 × (β1·기온차(대상일 최고기온 − 유사일 최고기온 평균) + β2·D-1 주간 수준 편차).
    β는 학습 구간의 유사일 잔차에 대한 최소제곱(가동 주간 구간만). 기온차 계수는 0 이상으로 제한(냉방부하).
    """
    name = "M9_analog_adjusted"

    def __init__(self, use_level: bool = True, use_temp: bool = True):
        self.use_level = use_level
        self.use_temp = use_temp

    def _Z(self, X):
        cols = []
        if self.use_temp:
            cols.append(np.nan_to_num(X["dtmax_vs_analog"].to_numpy(float)))
        if self.use_level:
            cols.append(np.nan_to_num(X["d1_level_vs_analog"].to_numpy(float)))
        return np.column_stack(cols) if cols else np.zeros((len(X), 0))

    def fit(self, X, y):
        b = _analog_base(X)
        w = X["dayshift_full"].to_numpy(float) == 1
        ok = w & np.isfinite(b) & np.isfinite(np.asarray(y, float))
        Z = self._Z(X)[ok]
        r = np.asarray(y, float)[ok] - b[ok]
        self.beta_ = np.zeros(Z.shape[1])
        if Z.shape[0] > 50 and Z.shape[1]:
            beta, *_ = np.linalg.lstsq(Z, r, rcond=None)
            if self.use_temp:
                beta[0] = max(beta[0], 0.0)
                if Z.shape[1] > 1:  # 기온 계수를 고정하고 나머지 재적합
                    r2 = r - Z[:, 0] * beta[0]
                    b2, *_ = np.linalg.lstsq(Z[:, 1:], r2, rcond=None)
                    beta[1:] = b2
            self.beta_ = beta
        self.mu_ = float(np.nanmean(y))
        return self

    def predict(self, X):
        b = _analog_base(X)
        w = X["dayshift_full"].to_numpy(float) == 1
        p = b + w * (self._Z(X) @ self.beta_)
        p[~np.isfinite(p)] = self.mu_
        return p


class PlanStopGate:
    """계획 정지일(당일 가동 체제 0)에는 ML 예측 대신 구조 기준값(A: 수준 보정 유사일, B: 체제별 유사일)을 쓴다.

    학습 자료(5~7월 실측)에는 평일 정지일이 없어 ML이 요일로 외삽해 가동 수준을 예측한다(v2.0 첫 시험 실행에서
    휴가 주간 8/2~8/6에 확인, 사후 추가). 유사일 기준값은 같은 체제 날짜에서 오므로 정지일에 대기 전력을 준다.
    """

    def __init__(self, inner, task: str, rho: float = 0.9):
        self.inner = inner
        self.task = task
        self.rho = rho

    @property
    def name(self):
        return getattr(self.inner, "name", "gated")

    @property
    def features(self):
        return self.inner.features

    def fit(self, X, y):
        self.inner.fit(X, y)
        return self

    def predict(self, X):
        p = np.asarray(self.inner.predict(X), dtype=float).copy()
        stop = X["regime"].to_numpy() == 0
        if stop.any():
            base = analog_level(X, self.rho) if self.task == "A" else _analog_base(X)
            idx = np.where(stop & np.isfinite(base))[0]
            p[idx] = base[idx]
        return p

    def contrib(self, X):
        return self.inner.contrib(X)

    def __getattr__(self, item):  # inner_, m_ 등 내부 속성 접근(설명 분석용)
        if item == "inner":
            raise AttributeError(item)
        return getattr(self.inner, item)


def gated(model, task: str):
    return PlanStopGate(model, task)
