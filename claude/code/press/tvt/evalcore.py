"""2·3단계 공통 평가: 후보·규칙 조합을 검증(valid) 또는 시험(test) 구간에서 채점한다.

- 검증: 정상 검증 행은 자기 기록을 뺀 보정 p(LOO), 이상 검증 행은 전체 보정 p. 사건 지속은 검증 흐름 안에서만 이어진다
- 시험: 모든 행이 전체 보정 p(배포 상태). 정상 흐름은 검증 정상 → 시험 정상, 이상 흐름은 이상 21기록 전체를 시간순으로 돌리고
  시험 행만 채점한다. 직전 기록의 경보 상태는 이어지지만 라벨은 쓰지 않는다
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import f1_counts, record_flags, stream_rules

ROW_BASES = ["maxz3", "iforest", "knn5", "mlp_ae5", "lstm20", "v1", "v2", "v2+C1d1", "v2+C2d1"]
RULE_BASES = ["v2", "v2+C1d1", "v2+C2d1"]
RULES = {"": (False, False), "+H2": (False, True), "+H1": (True, False), "+H1+H2": (True, True)}
V3_RECORD = ["v3_B1", "v3_C1d1", "v3_C1d2", "v3_C2d1", "v3_C2d2", "v3_B3k5", "v3_B3k10"]


def candidates(complexity: dict):
    """(이름, 기반 모델, 사건 지속, 교차 확인, 기록 단위 전용, 복잡도)"""
    out = []
    for b in ROW_BASES:
        rules = RULES if b in RULE_BASES else {"": (False, False)}
        for suffix, (h1, h2) in rules.items():
            out.append((b + suffix, b, h1, h2, False, complexity[b] + h1 + h2))
    for b in V3_RECORD:
        out.append((b, b, False, False, True, complexity[b]))
    return out


def _p(table, mask, regime, full_col, loo_col):
    """검증 정상 행은 LOO p, 나머지는 전체 보정 p."""
    full = table.loc[mask, full_col].to_numpy()
    if regime != "valid":
        return full
    loo = table.loc[mask, loo_col].to_numpy()
    use = (table.loc[mask, "part"].to_numpy() == "valid") & (table.loc[mask, "subset"].to_numpy() == "normal")
    return np.where(use, loo, full)


def own_alarm(table, mask, base, alpha, regime, h2, r2_ref):
    p = _p(table, mask, regime, f"{base}|p_full", f"{base}|p_loo")
    alarm = np.isfinite(p) & (p <= alpha)
    if not h2:
        return alarm
    comps = [c.split("|")[2] for c in table.columns if c.startswith(f"{base}|cp_full|")]
    act = {}
    for c in comps:
        cp = _p(table, mask, regime, f"{base}|cp_full|{c}", f"{base}|cp_loo|{c}")
        act[c] = np.isfinite(cp) & (cp <= alpha)
    mag_only = act["magnitude"] & ~np.any([act[c] for c in comps if c != "magnitude"], axis=0)
    wave_ok = table.loc[mask, "prefix_r2"].to_numpy() >= r2_ref       # NaN(8행 미만)은 False → 보류하지 않음
    return alarm & ~(mag_only & wave_ok)


def evaluate(table: pd.DataFrame, cand, alpha: float, regime: str, r2_ref: float) -> dict:
    """regime: 'valid' 또는 'test'. 반환: 실시간·기록 단위 지표와 채점 행의 예측."""
    name, base, h1, h2, record_only, _ = cand
    preds_rt, preds_rec, ys = [], [], []
    for subset in ("normal", "abnormal"):
        if regime == "valid":
            stream = (table.subset == subset) & (table.part == "valid")
        else:
            stream = (table.subset == subset) & table.part.isin(["valid", "test"])
        stream = stream.to_numpy()
        sub = table.loc[stream]
        own = own_alarm(table, stream, base, alpha, regime, h2, r2_ref)
        rec = sub.rec.to_numpy()
        if record_only:
            rt, unrel = np.full(len(sub), np.nan), None
            rflag = own
        else:
            rt, unrel = stream_rules(sub.ts.to_numpy(), rec, own, sub.prefix_r2.to_numpy() >= r2_ref, h1)
            rflag = record_flags(rec, own, unrel if h1 else None)
        score_rows = (sub.part == ("valid" if regime == "valid" else "test")).to_numpy()
        preds_rt.append(rt[score_rows]); preds_rec.append(rflag[score_rows]); ys.append(sub.label.to_numpy()[score_rows] == 1)
    y = np.concatenate(ys)
    out = {"record": f1_counts(y, np.concatenate(preds_rec).astype(bool))}
    if not record_only:
        out["realtime"] = f1_counts(y, np.concatenate(preds_rt).astype(bool))
    return out


def v2_error_anatomy(table, alpha, regime, r2_ref):
    """v2가 틀린 행: 미탐의 기록 위치, 오경보의 원인 성분과 그 시점 전류 파형."""
    part = "valid" if regime == "valid" else "test"
    m = (table.part == part).to_numpy()
    sub = table.loc[m]
    p = _p(table, m, regime, "v2|p_full", "v2|p_loo")
    alarm = np.isfinite(p) & (p <= alpha)
    miss = sub[(sub.label == 1).to_numpy() & ~alarm]
    fa = sub[(sub.label == 0).to_numpy() & alarm]
    return dict(missed_rows=int(len(miss)), missed_by_position={str(k): int(v) for k, v in miss.groupby("pos").size().items()},
                missed_records=sorted(miss.seg.unique().tolist()),
                false_alarm_rows=int(len(fa)),
                false_alarms=[dict(record=r.rec, position=int(r.pos), prefix_r2=None if pd.isna(r.prefix_r2) else round(float(r.prefix_r2), 4),
                                   waveform_normal=bool(r.prefix_r2 >= r2_ref)) for r in fa.itertuples()])
