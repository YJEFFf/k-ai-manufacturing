"""시간순 분할: 교차검증 폴드와 시험 주간 재학습."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from . import config as C
from . import features as F

GAP = pd.Timedelta(minutes=60)      # 과제 A: 블록 첫 목표의 발행(최대 60분 전) 시점에 알려진 정답까지만 학습
GAP_B = pd.Timedelta(hours=7)       # 과제 B: 블록 첫날 D의 발행 = D-1 17:00 → 그 시각까지 끝난 구간만 학습


def peak_threshold(iv: pd.DataFrame, before: pd.Timestamp, q: float = C.PEAK_Q) -> float:
    y = iv.loc[iv.index < before, "y_train"].dropna()
    return float(np.quantile(y, q))


def train_mask(index: pd.DatetimeIndex, trainable: np.ndarray, start: pd.Timestamp, task: str) -> np.ndarray:
    """학습 정답 구간(시작 시각 t, 끝 t+15분)이 블록 첫 발행 시각 전에 끝나야 한다."""
    cut = start - (GAP if task == "A" else GAP_B)
    return trainable & (index + pd.Timedelta(minutes=15) <= cut)


def eval_mask(index: pd.DatetimeIndex, usable: np.ndarray, start: pd.Timestamp, end: pd.Timestamp) -> np.ndarray:
    return usable & (index >= start) & (index < end)


def build_frames(iv: pd.DataFrame, issue_hour_b: int = 17, oracle: bool = False, analog_key: tuple = F.ANALOG_KEY,
                 regime_noise: tuple[float, int] | None = None, tasks=("B", "A1", "A2", "A3", "A4")) -> dict:
    """과제별 특징 행렬: {'B': X_B, 'A1'..'A4': X_A(h)}. 행 = 목표 구간.

    analog_key: 유사일 키(절제용). regime_noise=(비율, 난수): 계획 체제 오류 민감도(모든 기간에 같은 오류).
    """
    st = F.schedule_table(iv)
    if regime_noise is not None:
        st = F.perturb_regime(st, *regime_noise)
    xb = F.dayahead_features(iv, st, issue_hour=issue_hour_b, oracle_plan=oracle, analog_key=analog_key)
    if not any(t.startswith("A") for t in tasks):
        return {"B": xb}
    xmid = xb if issue_hour_b >= 24 else F.dayahead_features(iv, st, issue_hour=24, oracle_plan=oracle, analog_key=analog_key)
    frames = {"B": xb}
    for h in (1, 2, 3, 4):
        if f"A{h}" in tasks:
            frames[f"A{h}"] = F.intraday_features(iv, h, xmid)
    return frames


def refit_starts(start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """재학습 시점: 구간 시작일 + 그 뒤의 매주 월요일 00:00."""
    days = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
    mondays = [d for d in days if d.dayofweek == 0 and d != start]
    return [start] + mondays


def weekly_blocks(start: pd.Timestamp, end: pd.Timestamp, weekly: bool = True) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if not weekly:
        return [(start, end)]
    st = refit_starts(start, end)
    return list(zip(st, st[1:] + [end]))


def run_split(X: pd.DataFrame, iv: pd.DataFrame, factory: Callable, task: str,
              blocks: list[tuple[pd.Timestamp, pd.Timestamp]], store: list | None = None) -> pd.Series:
    """blocks의 각 (시작, 끝)마다 시작 이전의 학습 가능 구간으로 학습하고 그 블록을 예측한다.

    store가 주어지면 (시작, 끝, 학습된 모델)을 담는다(추론 전용 단계용 모델 저장)."""
    pred = pd.Series(np.nan, index=X.index)
    idx = X.index
    trainable = iv["trainable"].to_numpy()
    y_fit = iv["y_train"]
    for s, e in blocks:
        tr = train_mask(idx, trainable, s, task)
        ev = (idx >= s) & (idx < e)
        if not ev.any():
            continue
        m = factory()
        m.fit(X.loc[tr], y_fit[tr])
        pred.loc[ev] = m.predict(X.loc[ev])
        if store is not None:
            store.append((s, e, m))
    return pred


def cv_blocks() -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    return [(n, s, e) for n, s, e in C.CV_FOLDS]


def run_cv(X: pd.DataFrame, iv: pd.DataFrame, factory: Callable, task: str, weekly: bool = True) -> pd.Series:
    """교차검증 OOF 예측: 각 폴드 안에서도 시험과 같은 주간 재학습을 적용한다."""
    pred = pd.Series(np.nan, index=X.index)
    for _, s, e in cv_blocks():
        p = run_split(X, iv, factory, task, weekly_blocks(s, e, weekly))
        m = (X.index >= s) & (X.index < e)
        pred.loc[m] = p.loc[m]
    return pred


def run_test(X: pd.DataFrame, iv: pd.DataFrame, factory: Callable, task: str, weekly: bool = True,
             store: list | None = None) -> pd.Series:
    return run_split(X, iv, factory, task, weekly_blocks(C.TEST_START, C.TEST_END, weekly), store=store)


def fold_of(index: pd.DatetimeIndex) -> np.ndarray:
    lab = np.full(len(index), "", dtype=object)
    for n, s, e in cv_blocks():
        lab[(index >= s) & (index < e)] = n
    lab[(index >= C.TEST_START) & (index < C.TEST_END)] = "test"
    return lab
