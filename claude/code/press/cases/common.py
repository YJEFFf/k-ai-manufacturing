"""케이스(기록구간) 분할 분석 공통 함수.

- 원본: data/3_소성가공_예지보전/ 의 두 CSV
- 전처리: 예준 v2와 같은 matched 정밀도(진동 1e-4, 전류 1.1920929 격자)로 두 파일의 저장 형식 차이를 지운다
- 기록구간: 이웃 행 간격이 0.1초에서 1e-6초 넘게 벗어나면 새 기록 (예준 data.segments와 같은 규칙, 정상 600·이상 21)
- 분할: A 학습 0~359 / 보정 360~479 / 평가 480~599, B 0~299 / 300~419 / 420~599 (예준과 같음)
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "3_소성가공_예지보전"
OUT = Path(__file__).resolve().parent / "outputs"
SENSORS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
SPLITS = {"A": (360, 480), "B": (300, 420)}
F0 = 0.6064 / 10  # 정상 전류의 겉보기 주기(표본당 cycle). 예준 AR(2) 진동자 0.6064 Hz


def load(name: str, matched: bool = True) -> pd.DataFrame:
    df = pd.read_csv(DATA / name)
    if matched:
        for c in SENSORS[:2]:
            df[c] = np.round(df[c] / 1e-4) * 1e-4
        df[SENSORS[2]] = np.round(df[SENSORS[2]] / 1.1920929) * 1.1920929
    ts = pd.to_datetime(df.TimeStamp)
    gap = ts.diff().dt.total_seconds()
    df["rec"] = gap.sub(0.1).abs().gt(1e-6).fillna(False).cumsum()
    df["pos"] = df.groupby("rec").cumcount()
    df["t"] = (ts - ts.iloc[0]).dt.total_seconds()
    return df


def load_both(matched: bool = True):
    return load("press_data_normal.csv", matched), load("outlier_data.csv", matched)


def sine_fit(x: np.ndarray):
    """고정 주파수 F0 사인 + 절편 적합. (진폭, 절편, 잔차 표준편차, R²)"""
    x = np.asarray(x, float)
    n = np.arange(len(x))
    X = np.column_stack([np.ones(len(x)), np.sin(2 * np.pi * F0 * n), np.cos(2 * np.pi * F0 * n)])
    b, *_ = np.linalg.lstsq(X, x, rcond=None)
    r = x - X @ b
    sst = ((x - x.mean()) ** 2).sum()
    r2 = 1 - (r ** 2).sum() / sst if sst > 0 else np.nan
    return np.hypot(b[1], b[2]), b[0], r.std(), r2


def lag1(x: np.ndarray) -> float:
    x = np.asarray(x, float) - np.mean(x)
    d = (x * x).sum()
    return float((x[1:] * x[:-1]).sum() / d) if d > 0 else np.nan


def case_features(g: pd.DataFrame) -> dict:
    """기록 하나(케이스)를 다변량 시계열로 보고 요약 특징을 낸다."""
    v0, v1, c = (g[s].to_numpy() for s in SENSORS)
    amp, off, res, r2 = sine_fit(c)
    sd0, sd1 = v0.std(), v1.std()
    return dict(
        n=len(g), t0=g.t.iloc[0],
        vib_upper_sd=sd0, vib_lower_sd=sd1,
        upper_lower_log_ratio=np.log(sd0 / sd1) if sd0 > 0 and sd1 > 0 else np.nan,
        upper_lower_corr=np.corrcoef(v0, v1)[0, 1] if len(g) > 2 and sd0 > 0 and sd1 > 0 else np.nan,
        vib_upper_lag1=lag1(v0), vib_lower_lag1=lag1(v1),
        cur_amp=amp, cur_offset_ratio=off / amp if amp > 0 else np.nan,
        cur_resid_ratio=res / amp if amp > 0 else np.nan, cur_sine_r2=r2,
    )


def case_table(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([dict(rec=k, **case_features(g)) for k, g in df.groupby("rec")])


def prefix_r2(df: pd.DataFrame, min_len: int = 8) -> np.ndarray:
    """각 행까지(그 행 포함) 같은 기록 안 전류의 사인 적합 R². 실시간으로 계산 가능한 값만 쓴다."""
    out = np.full(len(df), np.nan)
    cur = df[SENSORS[2]].to_numpy()
    for _, idx in df.groupby("rec").indices.items():
        for j in range(min_len - 1, len(idx)):
            out[idx[j]] = sine_fit(cur[idx[: j + 1]])[3]
    return out
