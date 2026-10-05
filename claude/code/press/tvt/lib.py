"""train/valid/test 분석 공통 모듈(보고서 1.7절 분할·검증 전략, 2.3절 규칙 R1·R2). tvt/·domain/ 스크립트가 import한다.

분할(실행 전 고정): 정상은 예준 v2와 같은 기록 번호로 A 학습 0~359 / 검증 360~479 / 시험 480~599, B 0~299 / 300~419 / 420~599.
이상 21기록은 시간순 앞 10기록 = 검증, 뒤 11기록 = 시험이고 학습에는 쓰지 않는다.
conformal 문턱은 검증 정상 기록으로만 보정한다. 검증 정상 행의 p값은 그 기록을 뺀 나머지로 계산한다(leave-one-record-out).
예준 코드(팀 레포)를 그대로 불러 쓴다: yejun/press_guard(v2), yejun/press_submission(v1·베이스라인·LSTM), yejun/analysis/press_master_validation_2026-10-03(v3).
보고서 이름과 코드 이름: R1 사건 지속 = H1, R2 교차 확인 = H2.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
CACHE = HERE / "cache"
SPLITS = {"A": (360, 480), "B": (300, 420)}  # (학습 끝, 검증 끝) 정상 기록 번호
ABN_VALID_RECORDS = 10           # 이상 앞 10기록 = 검증
ALPHAS = (0.01, 0.03, 0.05)
PRIMARY_ALPHA = 0.01
GAP_S = 60.0                     # R1 사건 지속: 예준 v2 사건 규칙(INCIDENT_MAX_GAP_S)과 같은 값
CONFIRM_ROWS = 2                 # R1 사건 지속: 예준 v2 2단계 격상 규칙(ESCALATION_ALARM_ROWS)과 같은 값
R2_Q = 0.005                     # R2 교차 확인: 학습 정상 prefix R²의 0.5% 분위
R2_MIN_LEN = 8                   # prefix R²는 기록 8행째부터 계산한다
F0 = 0.6064 / 10                 # 정상 전류 겉보기 주기(표본당). 예준 AR(2) 진동자 0.6064 Hz
V3_COMPONENT_MIN_LEN = 20        # v3 조건부 성분은 기록 앞부분이 20행 이상일 때만 (v3 gate n>=20)


def repo_arg(argv=None):
    """--repo 인자 또는 PRESS_REPO 환경변수에서 팀 레포 경로를 받는다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=os.environ.get("PRESS_REPO"),
                    help="팀 레포 클론 경로. 데이터는 yejun/press_submission/data/3_소성가공_예지보전/")
    args = ap.parse_args(argv)
    if args.repo is None:
        raise SystemExit("--repo 또는 PRESS_REPO 환경변수로 팀 레포 경로를 지정한다")
    return args.repo.resolve()


def setup(repo: Path):
    """예준 모듈 경로를 sys.path에 넣고 import한 모듈 묶음(dict)을 돌려준다."""
    for p in (repo / "yejun/press_guard", repo / "yejun/press_submission",
              repo / "yejun/analysis/press_master_validation_2026-10-03"):
        sys.path.insert(0, str(p))
    import runtime
    runtime.setup()
    import model as guard           # press_guard/model.py
    import core as v3               # press_master_validation_2026-10-03/core.py
    from press import data as D, lstm_ae
    from press.calibrate import conformal_p, segment_max
    from press.scores import ExpTail, Scorer, sine_score
    return dict(guard=guard, v3=v3, D=D, lstm_ae=lstm_ae, conformal_p=conformal_p,
                segment_max=segment_max, ExpTail=ExpTail, Scorer=Scorer, sine_score=sine_score)


def ns_time(frame):
    """v3 core는 시각을 나노초 정수로 계산한다. pandas 3은 문자열 시각을 마이크로초로 읽으므로 나노초로 고정해 넘긴다."""
    return frame.assign(TimeStamp=pd.to_datetime(frame.TimeStamp).astype("datetime64[ns]"))


def v3_records(M, q, ns):
    """프레임을 v3 Record 목록으로 바꾸고 출처 이름(source_namespace)을 붙인다."""
    recs, _ = M["v3"].records_from_frame(ns_time(q))
    return [dataclasses.replace(r, source_namespace=ns) for r in recs]


def sha256_file(path: Path) -> str:
    """파일 SHA-256. 선택 결과·점수 캐시 잠금에 쓴다."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sine_r2(x: np.ndarray) -> float:
    """주파수를 F0로 고정한 사인 + 절편 적합의 R²."""
    x = np.asarray(x, float)
    n = np.arange(len(x))
    X = np.column_stack([np.ones(len(x)), np.sin(2 * np.pi * F0 * n), np.cos(2 * np.pi * F0 * n)])
    b, *_ = np.linalg.lstsq(X, x, rcond=None)
    sst = ((x - x.mean()) ** 2).sum()
    return float(1 - ((x - X @ b) ** 2).sum() / sst) if sst > 0 else np.nan


def prefix_r2(current: np.ndarray, rec: np.ndarray) -> np.ndarray:
    """각 행까지(포함) 같은 기록 안 전류의 사인 적합 R². 그 시점까지 들어온 값만 쓴다. 기록 앞 7행은 NaN."""
    out = np.full(len(current), np.nan)
    for r in pd.unique(rec):
        idx = np.flatnonzero(rec == r)
        for j in range(R2_MIN_LEN - 1, len(idx)):
            out[idx[j]] = sine_r2(current[idx[: j + 1]])
    return out


def stream_rules(ts: np.ndarray, rec: np.ndarray, own: np.ndarray, wave_ok: np.ndarray, latch: bool):
    """R1 사건 지속(H1)을 시간순으로 적용한다. 직전 기록의 판정만 쓰고 라벨은 쓰지 않는다.

    직전 기록(끝난 지 60초 안)이 '확인된 이상'이면 새 기록은 첫 행부터 경보를 이어받는다.
    확인된 이상 = 자기 경보 2행 이상, 또는 이어받은 경보가 기록 끝까지 안 풀림.
    이어받은 경보는 새 기록의 전류 파형이 정상으로 확인되는 행(wave_ok)에서 풀린다.
    반환: (행 경보, 기록별 '이어받은 경보가 끝까지 안 풀림')
    """
    alarm = own.copy()
    unreleased = {}
    prev_end, prev_confirmed = None, False
    for r in pd.unique(rec):
        idx = np.flatnonzero(rec == r)
        # 첫 기록은 prev_confirmed가 False라 prev_end(None)를 보지 않는다
        on = latch and prev_confirmed and (ts[idx[0]] - prev_end) / np.timedelta64(1, "s") <= GAP_S
        if on:
            for i in idx:
                if wave_ok[i]:
                    on = False
                    break
                alarm[i] = True
        unreleased[r] = bool(on)
        prev_confirmed = own[idx].sum() >= CONFIRM_ROWS or bool(on)
        prev_end = ts[idx[-1]]
    return alarm, unreleased


def record_flags(rec: np.ndarray, own: np.ndarray, unreleased: dict | None) -> np.ndarray:
    """기록 단위 판정: 기록 안 자기 경보가 1행이라도 있거나, 이어받은 경보가 끝까지 안 풀렸으면 기록 전체가 이상."""
    hit = pd.Series(own.astype(int)).groupby(rec).transform("max").to_numpy().astype(bool)
    if unreleased:
        hit |= np.array([unreleased[r] for r in rec])
    return hit


def f1_counts(y: np.ndarray, a: np.ndarray) -> dict:
    """행 단위 TP·FP·FN·F1."""
    y, a = y.astype(bool), a.astype(bool)
    tp, fp, fn = int((a & y).sum()), int((a & ~y).sum()), int((~a & y).sum())
    return dict(tp=tp, fp=fp, fn=fn, f1=2 * tp / (2 * tp + fp + fn) if tp else 0.0)
