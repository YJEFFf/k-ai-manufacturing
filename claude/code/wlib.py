"""용접 분석 공통 모듈: 경로, 물리 특징, 로버스트 통계, 누수 없는 분할, 이상점수 모델."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "2_용접기"
OUTPUTS = ROOT / "code" / "outputs"
RESULT_XLSX = DATA / "Welding Data Set_01.xlsx"

SENSORS = ["force", "current", "voltage", "weld_time"]
PHYS = ["energy_J", "resistance_uohm", "force", "current", "weld_time"]
DEFECT_NAMES = {1: "파임", 2: "용접부족", 3: "크랙"}
SEED = 7


# ---------- 통계 도구 ----------
def robust_z(x: pd.Series, ref: pd.Series) -> pd.Series:
    med = ref.median()
    mad = 1.4826 * (ref - med).abs().median()
    return (x - med) / (mad if mad > 0 else ref.std())


def mahal2(X, mu, cov):
    diff = X - mu
    return np.einsum("ij,jk,ik->i", diff, np.linalg.pinv(cov), diff)


def robust_cov(X: np.ndarray, trim: float = 0.95, iters: int = 5):
    """가장 바깥 5%를 반복적으로 깎아 내는 간이 MCD."""
    keep = np.ones(len(X), bool)
    for _ in range(iters):
        mu, cov = X[keep].mean(0), np.cov(X[keep].T)
        d2 = mahal2(X, mu, cov)
        keep = d2 <= np.quantile(d2, trim)
    return X[keep].mean(0), np.cov(X[keep].T)


def md_table(df: pd.DataFrame) -> str:
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "---|" * len(df.columns)
    body = ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


# ---------- 데이터 ----------
def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """건별 물리 특징. 입력은 SENSORS 열과 day, is_copy 열을 가진 표."""
    df = df.copy()
    df["energy_J"] = df["voltage"] * df["current"] * 1e3 * df["weld_time"] * 1e-3
    df["power_kW"] = df["voltage"] * df["current"]
    df["resistance_uohm"] = df["voltage"] / (df["current"] * 1e3) * 1e6
    df["i2t"] = df["current"] ** 2 * df["weld_time"]
    df["energy_per_bar"] = df["energy_J"] / df["force"]
    g = df.groupby("day", sort=False)
    for c in ["current", "voltage", "resistance_uohm", "force"]:
        df[f"d_{c}"] = g[c].diff()
    df["copy_boundary"] = df["is_copy"].ne(g["is_copy"].shift())
    return df


def load_flagged() -> pd.DataFrame:
    p = OUTPUTS / "diagnosis" / "rows_flagged.csv"
    if not p.exists():
        raise SystemExit("먼저 python code/01_diagnose_welding.py 를 실행하세요.")
    return pd.read_csv(p, encoding="utf-8-sig")


def load_physics() -> pd.DataFrame:
    p = OUTPUTS / "physics" / "features.csv"
    if not p.exists():
        raise SystemExit("먼저 python code/02_physics_lobe.py 를 실행하세요.")
    return pd.read_csv(p, encoding="utf-8-sig")


def load_daily_labels() -> pd.DataFrame:
    res = pd.ExcelFile(RESULT_XLSX).parse("result").iloc[:, :6]
    res.columns = ["result_idx", "machine", "item", "day", "defect", "defect_type"]
    res["day"] = pd.to_datetime(res["day"]).dt.strftime("%Y-%m-%d")
    lab = res.pivot_table(index="day", columns="defect_type", values="defect", aggfunc="sum")
    lab.columns = [f"defect_{DEFECT_NAMES[c]}" for c in lab.columns]
    lab["defect_total"] = lab.sum(axis=1)
    return lab


def make_folds(df: pd.DataFrame, k: int = 5) -> np.ndarray:
    """원본 행을 파일 순서대로 k개 연속 구간으로 나누고, 복제 행은 자기 원본의 구간을 따른다.

    같은 원본에서 나온 행이 학습과 평가 양쪽에 들어가지 않게 하는 누수 방지 분할이다.
    연속 구간으로 자르는 이유: 인접 용접은 서로 비슷하므로 무작위로 섞으면 이웃 정보가 샌다.
    """
    orig_rows = np.sort(df.loc[~df["is_copy"], "row"].to_numpy())
    fold_of_orig = pd.Series(np.arange(len(orig_rows)) * k // len(orig_rows), index=orig_rows)
    return df["source_row"].map(fold_of_orig).to_numpy()


# ---------- 이상점수 모델 (점수가 클수록 이상) ----------
class SPCScore:
    """관리한계(Shewhart) 방식: 변수별 로버스트 z의 최대 절댓값."""

    name = "SPC"

    def fit(self, X: pd.DataFrame):
        self.med = X.median()
        self.mad = 1.4826 * (X - self.med).abs().median().replace(0, np.nan).fillna(X.std())
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        return ((X - self.med) / self.mad).abs().max(axis=1).to_numpy()


class IForestScore:
    name = "IsolationForest"

    def fit(self, X: pd.DataFrame):
        from sklearn.ensemble import IsolationForest

        self.m = IsolationForest(n_estimators=300, random_state=SEED).fit(X.to_numpy())
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        return -self.m.score_samples(X.to_numpy())


class AEScore:
    """오토인코더(가이드북 방식 재현). sklearn MLP로 입력을 병목층을 거쳐 복원하고, 복원 오차를 점수로 쓴다."""

    name = "AutoEncoder"

    def fit(self, X: pd.DataFrame):
        from sklearn.neural_network import MLPRegressor
        from sklearn.preprocessing import StandardScaler

        self.sc = StandardScaler().fit(X.to_numpy())
        Z = self.sc.transform(X.to_numpy())
        h = max(2, Z.shape[1] // 2)
        self.m = MLPRegressor(hidden_layer_sizes=(8, h, 8), activation="tanh", max_iter=2000,
                              early_stopping=True, random_state=SEED).fit(Z, Z)
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        Z = self.sc.transform(X.to_numpy())
        return ((self.m.predict(Z) - Z) ** 2).mean(axis=1)


class MahalanobisScore:
    name = "RobustMahalanobis"

    def fit(self, X: pd.DataFrame):
        from sklearn.preprocessing import StandardScaler

        self.sc = StandardScaler().fit(X.to_numpy())
        self.mu, self.cov = robust_cov(self.sc.transform(X.to_numpy()))
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        return mahal2(self.sc.transform(X.to_numpy()), self.mu, self.cov)


BASELINES = [SPCScore, IForestScore, AEScore, MahalanobisScore]
