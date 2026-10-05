"""02·03·05와 domain/ 이 함께 쓰는 평가 함수. 후보·규칙 조합을 검증(valid) 또는 시험(test) 구간에서 채점한다(보고서 2.4·2.5절).

검증: 정상 검증 행은 자기 기록을 뺀 보정 p(LOO), 이상 검증 행은 전체 보정 p. 사건 지속은 검증 흐름 안에서만 이어진다.
시험: 모든 행이 전체 보정 p(배포 상태). 정상 흐름은 검증 정상 → 시험 정상, 이상 흐름은 이상 21기록 전체를 시간순으로 돌리고
시험 행만 채점한다. 직전 기록의 경보 상태는 이어지지만 라벨은 쓰지 않는다.
코드 이름 H1 = 보고서 R1(사건 지속), H2 = R2(교차 확인).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import f1_counts, record_flags, stream_rules

ROW_BASES = ["maxz3", "iforest", "knn5", "mlp_ae5", "lstm20", "v1", "v2", "v2+C1d1", "v2+C2d1"]
RULE_BASES = ["v2", "v2+C1d1", "v2+C2d1"]   # 성분 p가 있어 규칙을 얹을 수 있는 모델
RULES = {"": (False, False), "+H2": (False, True), "+H1": (True, False), "+H1+H2": (True, True)}  # (H1, H2)
V3_RECORD = ["v3_B1", "v3_C1d1", "v3_C1d2", "v3_C2d1", "v3_C2d2", "v3_B3k5", "v3_B3k10"]


def candidates(complexity: dict):
    """후보 목록. 원소 = (이름, 기반 모델, 사건 지속, 교차 확인, 기록 단위 전용, 복잡도 = 모델 복잡도 + 규칙 수)."""
    out = []
    for b in ROW_BASES:
        rules = RULES if b in RULE_BASES else {"": (False, False)}
        for suffix, (h1, h2) in rules.items():
            out.append((b + suffix, b, h1, h2, False, complexity[b] + h1 + h2))
    for b in V3_RECORD:
        out.append((b, b, False, False, True, complexity[b]))
    return out


def _p(table, mask, regime, full_col, loo_col):
    """검증 채점의 정상 검증 행은 LOO p, 나머지는 전체 보정 p. LOO는 자기 기록이 문턱을 정하는 데 끼지 않게 한다."""
    full = table.loc[mask, full_col].to_numpy()
    if regime != "valid":
        return full
    loo = table.loc[mask, loo_col].to_numpy()
    use = (table.loc[mask, "part"].to_numpy() == "valid") & (table.loc[mask, "subset"].to_numpy() == "normal")
    return np.where(use, loo, full)


def own_alarm(table, mask, base, alpha, regime, h2, r2_ref):
    """기록 자체 경보(p ≤ α). h2면 크기 성분 단독 + 전류 파형 정상인 경보를 보류한다(R2 교차 확인)."""
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


def _streams(table, cand, alpha, regime, r2_ref):
    """정상·이상 흐름마다 (흐름 행 표, 실시간 경보, 기록 단위 경보, 채점 행 마스크)를 낸다."""
    _, base, h1, h2, record_only, _ = cand
    parts = ["valid"] if regime == "valid" else ["valid", "test"]  # 시험은 검증 흐름에서 이어 돌린다
    scored = "valid" if regime == "valid" else "test"
    for subset in ("normal", "abnormal"):
        stream = ((table.subset == subset) & table.part.isin(parts)).to_numpy()
        sub = table.loc[stream]
        own = own_alarm(table, stream, base, alpha, regime, h2, r2_ref)
        rec = sub.rec.to_numpy()
        if record_only:  # v3 기록 단위 모델은 실시간 경보가 없다
            rt, rflag = np.full(len(sub), np.nan), own
        else:
            rt, unrel = stream_rules(sub.ts.to_numpy(), rec, own, sub.prefix_r2.to_numpy() >= r2_ref, h1)
            rflag = record_flags(rec, own, unrel if h1 else None)
        yield sub, rt, rflag, (sub.part == scored).to_numpy()


def evaluate(table: pd.DataFrame, cand, alpha: float, regime: str, r2_ref: float) -> dict:
    """regime: 'valid' 또는 'test'. 반환: {'record': 지표, 'realtime': 지표(기록 단위 전용 모델은 없음)}."""
    preds_rt, preds_rec, ys = [], [], []
    for sub, rt, rflag, keep in _streams(table, cand, alpha, regime, r2_ref):
        preds_rt.append(rt[keep]); preds_rec.append(rflag[keep]); ys.append(sub.label.to_numpy()[keep] == 1)
    y = np.concatenate(ys)
    out = {"record": f1_counts(y, np.concatenate(preds_rec).astype(bool))}
    if not cand[4]:  # cand[4] = 기록 단위 전용
        out["realtime"] = f1_counts(y, np.concatenate(preds_rt).astype(bool))
    return out


def predict_rows(table: pd.DataFrame, cand, alpha: float, regime: str, r2_ref: float) -> pd.DataFrame:
    """evaluate와 같은 계산으로 채점 행의 예측을 돌려준다(행 단위 예측 파일·첫 경보 지연용)."""
    out = []
    for sub, rt, rflag, keep in _streams(table, cand, alpha, regime, r2_ref):
        part = sub.loc[keep, ["subset", "label", "rec", "pos", "ts"]].copy()
        part["alarm_realtime"] = rt[keep]
        part["alarm_record"] = rflag[keep].astype(int)
        out.append(part)
    return pd.concat(out, ignore_index=True).assign(model=cand[0], alpha=alpha)


def v2_error_anatomy(table, alpha, regime, r2_ref):
    """v2가 틀린 행: 미탐의 기록 위치, 오경보 행과 그 시점 전류 파형이 정상이었는지."""
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
