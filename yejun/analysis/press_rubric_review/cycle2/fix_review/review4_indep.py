"""review4: 팀 코드(press_guard·press_submission·press_evidence)를 import하지 않는 독립 구현.

- 원본 CSV를 직접 읽고, 기록 경계·matched 양자화·v2 세 성분·ExpTail 변환·conformal p를 동결 JSON 상태만으로 다시 계산한다.
- 이 모듈은 다른 review4_ 스크립트가 import해서 쓴다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

SNAP = Path(os.environ["REVIEW_ENV"])   # 검토한 작업본 사본의 yejun 폴더(검토 당시 임시 폴더)
DATA = SNAP / "press_submission" / "data" / "3_소성가공_예지보전"
ART = SNAP / "press_guard" / "artifacts"
SENS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
GRID = 1.1920929
FREQS = np.arange(0.0, 5.0001, 0.005)
LN10 = np.log(10.0)


def load_raw():
    n = pd.read_csv(DATA / "press_data_normal.csv")
    a = pd.read_csv(DATA / "outlier_data.csv")
    return n, a


def records(ts, tol=1e-6):
    t = pd.to_datetime(pd.Series(ts).reset_index(drop=True))
    d = t.diff().dt.total_seconds().to_numpy()
    new = np.zeros(len(t), bool)
    new[1:] = np.abs(d[1:] - 0.1) > tol
    return np.cumsum(new)


def positions(rec):
    rec = np.asarray(rec)
    pos = np.zeros(len(rec), int)
    for i in range(1, len(rec)):
        pos[i] = pos[i - 1] + 1 if rec[i] == rec[i - 1] else 0
    return pos


def quantize(values):
    """values: (n,3) 원값 → matched 양자화(진동 1e-4, 전류 1.1920929 격자 반올림)."""
    v = np.array(values, float, copy=True)
    v[:, :2] = np.round(v[:, :2] / 1e-4) * 1e-4
    v[:, 2] = np.round(v[:, 2] / GRID) * GRID
    return v


_H = {}


def hats(win):
    if win not in _H:
        t = np.arange(win) * 0.1
        mats = []
        for f in FREQS:
            A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(win)])
            mats.append(A @ np.linalg.pinv(A, rcond=1e-10))
        _H[win] = np.stack(mats)
    return _H[win]


def windows_ok(rec, win):
    idx = np.arange(win - 1, len(rec))
    return idx[rec[idx] == rec[idx - win + 1]]


def sine_ratio(x, rec, win):
    out = np.full(len(x), np.nan)
    idx = windows_ok(rec, win)
    if not len(idx):
        return out
    W = np.stack([x[i - win + 1:i + 1] for i in idx])
    sst = ((W - W.mean(1, keepdims=True)) ** 2).sum(1)
    best = np.full(len(idx), np.inf)
    for H in hats(win):
        r = W - W @ H.T
        best = np.minimum(best, (r * r).sum(1))
    with np.errstate(invalid="ignore", divide="ignore"):
        best = np.where(sst > 0, best / sst, np.nan)
    out[idx] = np.clip(best, 0, None)
    return out


class Tail:
    def __init__(self, st):
        self.n, self.u, self.beta = int(st["n"]), float(st["u"]), float(st["beta"])
        self.ref = np.asarray(st["ref_sorted"], float)
        self.g_u = self.emp(np.array([self.u]))[0]

    def emp(self, s):
        ge = self.n - np.searchsorted(self.ref, s, side="left")
        return -np.log10((ge + 1) / (self.n + 1))

    def __call__(self, s):
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        v = s[ok]
        res = np.where(v <= self.u, self.emp(v), self.g_u + (v - self.u) / (self.beta * LN10))
        out[ok] = res
        return out


class Model:
    def __init__(self, sid):
        st = json.loads((ART / f"guard_{sid}.json").read_text(encoding="utf-8"))["state"]
        self.sid = sid
        self.mean = np.asarray(st["mean"], float)
        self.scale = np.asarray(st["scale"], float)
        self.ar = np.asarray(st["ar2"], float)
        self.tails = {k: Tail(v) for k, v in st["tails"].items()}
        self.cal = np.sort(np.asarray(st["calibration"], float))

    def pval(self, s):
        s = np.asarray(s, float)
        out = np.full(len(s), np.nan)
        ok = np.isfinite(s)
        ge = len(self.cal) - np.searchsorted(self.cal, s[ok], side="left")
        out[ok] = (ge + 1) / (len(self.cal) + 1)
        return out

    def predict(self, values, ts, alpha=0.01, rec=None):
        """values: (n,3) 원값(양자화 전), ts: 시각 문자열. 반환 DataFrame(record, pos, alarm, reason, magnitude_sensor, g_*)."""
        if rec is None:
            rec = records(ts, 0.02)
        rec = np.asarray(rec)
        pos = positions(rec)
        q = quantize(values)
        z = (q - self.mean) / self.scale
        mag = np.abs(z).max(1)
        msens = np.asarray(SENS)[np.abs(z).argmax(1)]
        cur = q[:, 2]
        s6, s8 = sine_ratio(cur, rec, 6), sine_ratio(cur, rec, 8)
        idx = windows_ok(rec, 3)
        res = np.full(len(cur), np.nan)
        res[idx] = np.abs(cur[idx] - self.ar[0] - self.ar[1] * cur[idx - 1] - self.ar[2] * cur[idx - 2])
        gz = self.tails["magnitude"](mag)
        gs = np.where(pos < 7, self.tails["sine6"](s6), self.tails["sine8"](s8))
        ga = self.tails["dynamics"](res)
        score = np.fmax(np.fmax(gz, gs), ga)
        p = self.pval(score)
        alarm = np.isfinite(p) & (p <= alpha)
        act = np.column_stack([self.pval(g) <= alpha for g in (gz, gs, ga)])
        names = np.array(["magnitude", "waveform", "dynamics"])
        reason = ["+".join(names[act[i]]) if alarm[i] else "" for i in range(len(p))]
        return pd.DataFrame(dict(record=rec, pos=pos, alarm=alarm.astype(int), reason=reason, magnitude_sensor=msens,
                                 g_magnitude=gz, g_waveform=gs, g_dynamics=ga, score=score, p=p, residual=res))


# ---------- 독립 사인 적합(0~5 Hz 격자, 사인+코사인+상수) ----------
_FH = {}


def fit_hats(n):
    if n not in _FH:
        t = np.arange(n) * 0.1
        mats = []
        for f in FREQS:
            A = np.column_stack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(n)])
            mats.append(A @ np.linalg.pinv(A))
        _FH[n] = np.stack(mats)
    return _FH[n]


def best_sine(x):
    x = np.asarray(x, float)
    fitted = fit_hats(len(x)) @ x
    sse = ((x[None, :] - fitted) ** 2).sum(1)
    k = int(np.argmin(sse))
    sst = float(((x - x.mean()) ** 2).sum())
    return float(FREQS[k]), (1 - sse[k] / sst) if sst > 0 else np.nan, fitted[k]


def ls_tone(x, f):
    t = np.arange(len(x)) * 0.1
    A = np.column_stack([np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(len(x))])
    coef, *_ = np.linalg.lstsq(A, x, rcond=None)
    return coef, x - A @ coef
