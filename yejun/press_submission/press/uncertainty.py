"""W8 불확실성 — PLAN.md §5.3. 정상 평가 구간 알림 수의 시간 의존성 민감도(moving-block bootstrap).

관측 카운트가 주 결과다. 독립 가정 정확 이항 상한은 evaluate가 표에 넣는다. 여기서는 연속 기록구간 5·10·20개 블록으로
정상 평가 구간의 첫 알림 지시값을 재표집해 알림 수의 분포를 본다. 전부 0인 경우는 퇴화로 표시하고 구간으로 과장하지 않는다.
분할을 합산하지 않으며 하루치 재표집을 날짜 간 일반화로 해석하지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BLOCKS = (5, 10, 20)


def moving_block_bootstrap(x: np.ndarray, block: int, reps: int = 2000, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(x)
    if n == 0:
        return np.array([])
    block = min(block, n)
    starts_max = n - block + 1
    k = int(np.ceil(n / block))
    counts = np.empty(reps)
    for r in range(reps):
        st = rng.integers(0, starts_max, size=k)
        idx = np.concatenate([np.arange(s, s + block) for s in st])[:n]
        counts[r] = x[idx].sum()
    return counts


def run(records: dict, out, reps: int = 2000) -> pd.DataFrame:
    """records[sid] = evaluate records DataFrame(주 모델, 전 기준·α, source 포함)."""
    rows = []
    for sid, rec in records.items():
        r = rec[rec.source == "normal_test"]
        for (crit, alpha, unit), g in r.groupby(["criterion", "alpha", "calibration_unit"]):
            g = g.sort_values("record_id")
            x = g.first_notification.to_numpy(int)
            for b in BLOCKS:
                c = moving_block_bootstrap(x, b, reps=reps, seed=0)
                rows.append(dict(split=g.split.iloc[0], calibration_unit=unit, criterion=crit, alpha=alpha, block_length=b,
                                 n_segments=len(x), observed_alerts=int(x.sum()), boot_mean=float(c.mean()),
                                 boot_p2_5=float(np.percentile(c, 2.5)), boot_p97_5=float(np.percentile(c, 97.5)),
                                 degenerate_all_zero=bool(x.sum() == 0), reps=reps))
    df = pd.DataFrame(rows)
    df.to_csv(out / "uncertainty.csv", index=False)
    return df
