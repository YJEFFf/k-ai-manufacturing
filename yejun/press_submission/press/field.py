"""W10 현장 활용 — PLAN.md §6. 업무량 표, 지속성 (k,n) 규칙, 진폭 정규화 후보, 작업자 판단표.

- 업무량: 첫 알림 구간 수, 경보 run 수, 기록 관측시간(0.1초×행) 기준 알림률과 경과시간 기준을 따로 적는다. 하루 알림 수는 가정이 있는 시나리오다.
- 지속성: (k,n) ∈ {(1,1),(2,3),(3,3)}. 같은 구간 최근 n개 유효 결합 점수 중 k번째 큰 값을 정책 점수로 삼고 보정 구간에서 다시 보정한다.
  창을 못 채운 행(구간 첫 n−1행·결측)은 미판정. 각 정책은 자기 문턱·p값·지연을 가지며 미탐 분모를 유지한다.
- 진폭 정규화 후보: 정상 학습 안의 시간순 A/B로 trailing-17 진동 표준편차 ~ trailing-17 전류 진폭(대리 지표) 선형 관계를 적합하고,
  그 잔차를 크기 성분으로 쓰는 결합 후보를 평가한다. 사후 구간 전체 특징은 실시간 점수에 넣지 않는다. 결과가 좋아도 주 모델을 자동 교체하지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D
from .calibrate import ALPHAS
from .evaluate import evaluate_models
from .scores import ExpTail, MAIN_W, window_index

PERSISTENCE = ((1, 1), (2, 3), (3, 3))
AMP_WIN = 17
OPERATING_HOURS = (8, 16, 24)


# ---------- 업무량 ----------
def workload(ops: pd.DataFrame, frames_by_split: dict) -> pd.DataFrame:
    rows = []
    for split, fr in frames_by_split.items():
        test = fr["test"]
        t = pd.to_datetime(test[D.TIME])
        recorded_h = len(test) * D.DT / 3600
        elapsed_h = (t.max() - t.min()).total_seconds() / 3600
        o = ops[ops.split == split]
        for r in o.itertuples():
            base = dict(split=split, calibration_unit=r.calibration_unit, criterion=r.criterion, alpha=r.alpha, alpha_grid=r.alpha_grid,
                        normal_segments=r.normal_segments, first_alert_segments=r.normal_notified_segments, alarm_runs=r.normal_alarm_runs,
                        alarm_rows=r.normal_alarm_rows, binomial_upper95=r.normal_binomial_upper95,
                        recorded_hours=recorded_h, elapsed_hours=elapsed_h,
                        alerts_per_recorded_hour=r.normal_notified_segments / recorded_h,
                        alerts_per_elapsed_hour=r.normal_notified_segments / elapsed_h,
                        abnormal_detected=r.abnormal_notified_segments, delay_median_s=r.delay_median_s, delay_p90_s=r.delay_p90_s)
            for h in OPERATING_HOURS:
                base[f"scenario_alerts_per_day_{h}h_recorded_rate"] = r.normal_notified_segments / recorded_h * h
            rows.append(base)
    df = pd.DataFrame(rows)
    df.attrs["note"] = "하루 알림 수 시나리오 = 기록 관측시간 기준 알림률 × 가정 가동시간. 실제 가동 상태·기록 밀도는 자료에 없다."
    return df


# ---------- 지속성 ----------
def persistence_score(score: np.ndarray, seg: np.ndarray, k: int, n: int) -> np.ndarray:
    """같은 구간 최근 n개 유효 점수 중 k번째 큰 값. n개가 다 없으면 NaN."""
    out = np.full(len(score), np.nan)
    if n == 1:
        return score.copy()
    valid = np.isfinite(score)
    # 구간 내 유효 점수 누적 위치
    for s in np.unique(seg):
        idx = np.flatnonzero(seg == s)
        buf = []
        for i in idx:
            if valid[i]:
                buf.append(score[i])
            if len(buf) >= n:
                out[i] = np.sort(buf[-n:])[-k]
    return out


def persistence(vendor, split_name: str, preprocess: str, main_scores: dict, frames: dict, segs: dict) -> pd.DataFrame:
    models = {f"persist_k{k}n{n}": {key: persistence_score(main_scores[key], segs[key], k, n) for key in main_scores} for k, n in PERSISTENCE}
    mt, _ = evaluate_models(vendor, split_name, preprocess, models, frames, segs, units=("recording_segments",))
    mt["k"] = mt.model.str.extract(r"k(\d)").astype(int)
    mt["n"] = mt.model.str.extract(r"n(\d)").astype(int)
    return mt


# ---------- 진폭 정규화 후보 ----------
def trailing_feature(x: np.ndarray, seg: np.ndarray, win: int, fn) -> np.ndarray:
    out = np.full(len(x), np.nan)
    idx = window_index(seg, win)
    if len(idx):
        W = np.stack([x[i - win + 1:i + 1] for i in idx])
        out[idx] = fn(W)
    return out


def _amp(W):
    return np.sqrt(2 * ((W - W.mean(1, keepdims=True)) ** 2).mean(1))


def _std(W):
    return W.std(1, ddof=1)


class LoadNormalizer:
    """정상 학습 A(앞 80% 구간)에서 vib_std17 = a + b·amp17 을 적합하고 잔차의 표준화값을 낸다."""

    def __init__(self, train: pd.DataFrame, seg_train: np.ndarray):
        ids = np.unique(seg_train)
        cut = ids[int(len(ids) * 0.8)]
        a_mask = seg_train < cut
        tr = train[a_mask].reset_index(drop=True)
        sg = seg_train[a_mask]
        amp = trailing_feature(tr[D.SENSORS[2]].to_numpy(float), sg, AMP_WIN, _amp)
        vib = trailing_feature(tr[D.SENSORS[0]].to_numpy(float), sg, AMP_WIN, _std)
        ok = np.isfinite(amp) & np.isfinite(vib)
        X = np.column_stack([np.ones(ok.sum()), amp[ok]])
        self.coef, *_ = np.linalg.lstsq(X, vib[ok], rcond=None)
        res = vib[ok] - X @ self.coef
        self.res_sd = float(res.std(ddof=1)) if len(res) > 2 else np.nan
        self.slope_corr = float(np.corrcoef(amp[ok], vib[ok])[0, 1]) if ok.sum() > 2 else np.nan
        self.n_fit = int(ok.sum())
        # 학습 B(뒤 20%)에서 잔차 분포 확인 + 참조(꼬리)는 학습 전체의 잔차 점수로
        self.ref = self.score(train, seg_train)

    def score(self, frame: pd.DataFrame, seg: np.ndarray) -> np.ndarray:
        amp = trailing_feature(frame[D.SENSORS[2]].to_numpy(float), seg, AMP_WIN, _amp)
        vib = trailing_feature(frame[D.SENSORS[0]].to_numpy(float), seg, AMP_WIN, _std)
        res = vib - (self.coef[0] + self.coef[1] * amp)
        return res / self.res_sd


def load_normalization(vendor, split_name: str, preprocess: str, train, seg_train, scorer, frames, segs) -> tuple[pd.DataFrame, dict]:
    ln = LoadNormalizer(train, seg_train)
    tail = ExpTail(ln.ref)
    models = {}
    for key in ("cal", "test", "abn"):
        comp, _ = scorer.components(frames[key], segs[key])
        g_res = tail(ln.score(frames[key], segs[key]))
        mag = np.where(np.isfinite(g_res), g_res, comp["g_maxz3"])         # 17관측 전에는 max-z 그대로
        models.setdefault("loadnorm_resid_plus_sine", {})[key] = np.fmax(mag, comp[f"g_sine_{MAIN_W}"])
        models.setdefault("loadnorm_resid_only", {})[key] = g_res
        models.setdefault("main_combined_w8(reference)", {})[key] = np.fmax(comp["g_maxz3"], comp[f"g_sine_{MAIN_W}"])
    mt, _ = evaluate_models(vendor, split_name, preprocess, models, frames, segs, units=("recording_segments",))
    meta = dict(split=split_name, fit_rows=ln.n_fit, intercept=float(ln.coef[0]), slope=float(ln.coef[1]), amp_vib_corr_trainA=ln.slope_corr,
                residual_sd=ln.res_sd, tail_ok=tail.ok, note="trailing-17 온라인 특징만 사용. 실제 부하 측정이 아닌 전류 진폭 대리 지표.")
    return mt, meta


# ---------- 판단표 ----------
def decision_table(ops: pd.DataFrame, path) -> None:
    L = ["# 작업자 판단표 (자동 생성)", "",
         "경보는 기록구간마다 첫 1회 알림이다. 사유는 어느 성분이 문턱을 넘었는지이며, 특정 부품의 고장 원인을 확정하지 않는다(가설 표기).", "",
         "| 관측 | 판단 | 확인 대상(가설) | 조치 후보 | 검증 가능한 지표 |", "|---|---|---|---|---|",
         "| 사유 `maxz`(상부/하부 진동 크기) | 진동 크기가 정상 학습 범위를 벗어남. 고부하 운전에서 오경보 가능성 | 펌프 상부·하부 진동, 커플링·베어링, 현재 부하 상태 | 부하 상태 확인 후 진동 재측정, 지속되면 점검 요청 | 정상 알림 구간 수, 진동 Q4 구간의 오경보율 |",
         "| 사유 `sine`(전류 파형 붕괴) | 진동은 정상 수준인데 전류 파형이 사인에서 벗어남 | 모터·전원·부하 계통, 전류 센서 수집 상태 | 전류 파형 확인, 수집 상태 점검 후 설비 점검 | 파형만으로 잡은 이상 구간 수(2×2 표) |",
         "| 사유 `both` | 두 성분 모두 이탈 | 위 두 항목 | 즉시 점검 요청 | 첫 경보 지연 |",
         "| 판정 불가(`is_scored=0`) | 구간 첫 관측 또는 상수 전류 창 | — | 다음 관측을 기다림. 구간 첫 7행은 max-z만 판정 | 미판정 행 비율 |",
         "| 진폭 신뢰 제한(길이<17) | 진폭 대리 지표를 근거로 쓰지 않음 | — | 진동·파형 사유만 사용 | — |", "",
         "## 운영점 선택지 (주 모델, 기록구간 보정, conformal)", "",
         "1%·3%·5%는 비교 가능한 선택지이며 단일 최적 운영점이나 절감액을 만들지 않는다. 실제 업무량 허용치는 현장에서 정한다.", "",
         "| 분할 | α | alpha_grid | 정상 알림 k/n | 독립 가정 95% 상한 | 이상 탐지 | 지연 중앙값(초) |", "|---|---|---|---|---|---|---|"]
    o = ops[(ops.calibration_unit == "recording_segments") & (ops.criterion == "conformal")]
    for r in o.itertuples():
        L.append(f"| {r.split} | {r.alpha:g} | {r.alpha_grid:.4f} | {int(r.normal_notified_segments)}/{int(r.normal_segments)} | {r.normal_binomial_upper95:.3f} | {int(r.abnormal_notified_segments)}/{int(r.abnormal_segments)} | {r.delay_median_s} |")
    L += ["", "- 지연은 기록구간 첫 관측 이후 첫 경보까지이며 고장 발생 전 선행시간이 아니다.", "- 정상 알림 0/n은 오경보율 0%가 아니다. 독립 가정 상한과 시간 의존성 민감도(`uncertainty.csv`)를 함께 본다."]
    path.write_text("\n".join(L), encoding="utf-8")


def run(out, vendor, ctx2: dict, preprocess: str, ops: pd.DataFrame, log=print) -> dict:
    frames_by_split = {c["name"]: c["frames"] for c in ctx2.values()}
    wl = workload(ops, frames_by_split)
    wl.to_csv(out / "workload.csv", index=False)
    pers, ln_rows, ln_meta = [], [], []
    for sid, c in ctx2.items():
        key = f"combined_w{MAIN_W}"
        main_scores = {k: c["scorer"].score(c["frames"][k], c["segs"][k])[0][key] for k in ("cal", "test", "abn")}
        p = persistence(vendor, c["name"], preprocess, main_scores, c["frames"], c["segs"])
        p["split_id"] = sid
        pers.append(p)
        mt, meta = load_normalization(vendor, c["name"], preprocess, c["train"], c["seg_train"], c["scorer"], c["frames"], c["segs"])
        mt["split_id"] = sid
        ln_rows.append(mt)
        ln_meta.append(meta)
        log(f"  field {sid} done")
    pers = pd.concat(pers, ignore_index=True)
    pers.to_csv(out / "persistence.csv", index=False)
    ln = pd.concat(ln_rows, ignore_index=True)
    ln.to_csv(out / "load_normalization.csv", index=False)
    pd.DataFrame(ln_meta).to_csv(out / "load_normalization_meta.csv", index=False)
    decision_table(ops, out / "field_decision_table.md")
    p1 = pers[(pers.criterion == "conformal") & (pers.alpha == 0.01)]
    l1 = ln[(ln.criterion == "conformal") & (ln.alpha == 0.01)]
    return {"persistence_conformal_1pct": {f"{r.model}@{r.split}": f"{int(r.abnormal_notified_segments)}/21 · {int(r.normal_notified_segments)}/{int(r.normal_segments)} · delay {r.delay_median_s}" for r in p1.itertuples()},
            "load_normalization_conformal_1pct": {f"{r.model}@{r.split}": f"{int(r.abnormal_notified_segments)}/21 · {int(r.normal_notified_segments)}/{int(r.normal_segments)}" for r in l1.itertuples()},
            "workload_rows": int(len(wl))}
