"""선정근거·사후 민감도 — 루브릭 사이클2 1회차 평가관 02(M3·M4·M5)·05(O3)·03(E7) 보완.

주 모델(v2 early6_ar2)·문턱·분할은 바꾸지 않는다. 여기 대안은 모두 이미 본 이상 21구간에 대한 사후 비교다.
결과가 v2보다 좋아도 채택하지 않는다. 같은 이상 자료에 대한 사후 선택이 한 번 더 늘기 때문이다. 대회 보고서가 아니다.

    cd yejun && OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python analysis/press_selection/run.py
    ... run.py --check    # 임시 폴더에 다시 계산해 이 폴더 산출물과 해시 대조(파일을 바꾸지 않음)

산출물(이 폴더)
  same_feature_alternatives.csv   M3  v2 세 성분을 그대로 넣은 5NN·IF·합, AR 차수 1~4, 같은 보정 규칙의 단일 성분(크기·파형·예측 오차)
  combination_rules.csv           O3  Tippett(=fmax)·Fisher·Stouffer·합·평균, 근거 성분 없는 경보
  fp_mitigation_v2.csv            E7  크기 성분 지속성 2/3, 전류 진폭 조건부 진동 잔차(v1 방식 이식), v1 결과 대조
  search_ledger.csv               M4  같은 이상 21구간에서 본 점수 규칙 장부
  candidate_universe.csv          M4  선정 전 후보 39개 재계산(분할별)과 커밋 표 대조
  nested_selection.csv            M4  선택 규칙의 이상 기록 1개 빼기 중첩 적용(21겹)
  paired_records.csv              M4  v1 대비 기록구간 짝 비교
  selection_evidence.csv          M4  선정 근거 한 장 요약
  unified_comparison.csv/.md      M5  통합 비교표(입력 조건·라벨 사용·무임계 지표·기록구간 지표)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
REPO = YEJUN.parent
GUARD = YEJUN / "press_guard"
sys.path.insert(0, str(GUARD))


def _import_guard(name):
    """press_guard는 다른 세션이 고치는 중일 수 있다. import가 순간 실패하면 잠시 뒤 다시 시도한다(읽기만 한다)."""
    for attempt in range(24):
        try:
            return importlib.import_module(name)
        except Exception:  # noqa: BLE001
            if attempt == 23:
                raise
            sys.modules.pop(name, None)
            time.sleep(5)


M = _import_guard("model")
D, GuardModel, layout, alert_units = M.D, M.GuardModel, M.layout, M.alert_units
from press.calibrate import conformal_p, conformal_threshold, segment_max  # noqa: E402
from press.field import LoadNormalizer, persistence_score  # noqa: E402
from press.scores import ExpTail, Scorer, window_index  # noqa: E402
from sklearn.ensemble import IsolationForest  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.neighbors import NearestNeighbors  # noqa: E402

ALPHAS = (.01, .03, .05)
COMP = ("g_magnitude", "g_waveform", "g_dynamics")
N_ABN = 21
SEED = 20260927          # 기록구간 부트스트랩(평가관 02 C3와 같은 시드·순서)
BOOT = 10_000
V2_INPUT = "v2 세 성분 g(크기 max|z|, 초반 6→8 사인 1−R², AR(2) 전류 잔차; 정상 학습 꼬리 변환)"
POSTHOC = "사후 민감도(이상 21구간을 이미 본 뒤의 비교). 채택 근거가 아니다"
KEEP_FMAX = ("fmax 유지 이유: ① 사전 선택 유지 — 결합 규칙은 v1 계획부터 쓴 fmax이고, 이상 21구간을 본 뒤 대안(Fisher·합·5NN)으로 바꾸면 "
             "사후 선택이 한 번 더 는다. 대안이 대회 F1·주입 탐지에서 같거나 나은 경우가 있다는 사실은 공개한다(rule_transfer_injection_v2.csv) "
             "② 경보마다 단독으로 문턱을 넘은 성분이 있어 근거→조치 판단표(model.DECISION_TABLE)가 성립한다. "
             "참고: 결합 점수 하나를 한 번만 재보정하는 것은 성분별 문턱의 OR 규칙보다 나은 점이며 Fisher·합·5NN과의 차이는 아니다. "
             "g=−log10(정상 꼬리 확률)의 최댓값은 Tippett 최소 p 결합이다")
OUTPUTS = ("same_feature_alternatives.csv", "combination_rules.csv", "fp_mitigation_v2.csv", "fp_mitigation_injection_v2.csv", "search_ledger.csv",
           "candidate_universe.csv", "nested_selection.csv", "paired_records.csv", "selection_evidence.csv",
           "unified_comparison.csv", "unified_comparison.md", "rule_transfer_injection_v2.csv")
# 프로토콜(또는 계획)과 결과 파일이 처음 커밋된 곳. 실행 시 git 기록으로 다시 확인한다(git이 없으면 manifest에 미확인으로 남는다).
PRECOMMIT = (
    dict(stage="v1 패키지", protocol="yejun/press_submission/PLAN.md", protocol_commit="4135c68", protocol_date="2026-09-24 16:29:59",
         result="yejun/press_submission/outputs/sensitivity.csv", result_commit="f029b42", result_date="2026-09-24 20:28:39",
         status="계획 문서가 결과보다 먼저 커밋됨. 비교 모델·창 목록 전체의 사전 고정 여부는 이 표에서 판정하지 않는다"),
    dict(stage="press_improvement(초반 짧은 창)", protocol="yejun/analysis/press_improvement/config.json", protocol_commit="40239b7",
         protocol_date="2026-09-25 15:31:44", result="yejun/analysis/press_improvement/candidate_metrics.csv", result_commit="40239b7",
         result_date="2026-09-25 15:31:44", status="프로토콜과 결과가 같은 커밋. 사전 고정을 커밋 기록으로 확인할 수 없다"),
    dict(stage="press_advance(AR(2) → v2 선정)", protocol="yejun/analysis/press_advance/protocol.json", protocol_commit="bb0bc94",
         protocol_date="2026-09-25 16:06:00", result="yejun/analysis/press_advance/metrics.csv", result_commit="bb0bc94",
         result_date="2026-09-25 16:06:00", status="프로토콜·결과·press_guard/model.py(v2)가 같은 커밋. 사전 고정을 커밋 기록으로 확인할 수 없다"),
    dict(stage="press_early(위치 0·1 후보)", protocol="yejun/analysis/press_early/protocol.json", protocol_commit="0afea45",
         protocol_date="2026-09-25 20:43:02", result="yejun/analysis/press_early/metrics.csv", result_commit="0afea45",
         result_date="2026-09-25 20:43:02",
         status="프로토콜과 결과가 같은 커밋. protocol.json의 registered_before_scores=true는 커밋 기록으로 확인할 수 없다"),
    dict(stage="press_supplement E1~E3", protocol="yejun/analysis/press_supplement/protocol.json", protocol_commit="a102ecf",
         protocol_date="2026-09-26 15:15:47", result="yejun/analysis/press_supplement/e1_summary.csv", result_commit="875f269",
         result_date="2026-09-26 15:35:48", status="프로토콜이 결과보다 20분 먼저 별도 커밋(결과 없음). 커밋 기록으로 확인되는 사전 고정"),
)


# ---------------------------------------------------------------- 공통
def f1(tp, fp, fn):
    d = 2 * tp + fp + fn
    return 2 * tp / d if d else 0.0


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def filled(score, low):
    s = np.asarray(score, float)
    return np.where(np.isfinite(s), s, low)


def oracle_f1(y, s):
    """행 점수 문턱을 평가 라벨로 고른 사후 최적 F1(낙관적 상한, 참고)."""
    order = np.argsort(-s, kind="mergesort")
    ys, ss = y[order], s[order]
    tp, fp = np.cumsum(ys), np.cumsum(1 - ys)
    last = np.r_[ss[1:] != ss[:-1], True]            # 같은 점수 묶음의 끝에서만 문턱을 둔다
    tp, fp = tp[last], fp[last]
    fn = ys.sum() - tp
    return float((2 * tp / (2 * tp + fp + fn)).max())


def record_ids(P, key):
    return P[key]["seg"]


class Context:
    """분할 하나: 동결 v2 모델과 정상 학습·보정·평가, 이상 행의 성분(모델 predict와 같은 전처리·구간 규칙)."""

    def __init__(self, sid, normal, abnormal, seg_all):
        self.sid = sid
        self.name, self.train_end, self.cal_end = D.SPLITS[sid]
        split = D.split_normal(normal, seg_all, sid)
        self.model = GuardModel.load(GUARD / "artifacts" / f"guard_{sid}.json")
        self.parts = {}
        for key, frame in (("train", split["train"]), ("cal", split["cal"]), ("test", split["test"]), ("abn", abnormal)):
            q = D.quantize(D.inputs_only(frame), "matched")
            seg = layout(q)[1]
            pos = D.segment_positions(seg)[0]
            self.parts[key] = dict(q=q, seg=seg, pos=pos, units=alert_units(seg, pos), comp=self.model.components(q, seg))
        cal_max = segment_max(self.parts["cal"]["comp"]["score"], self.parts["cal"]["units"])
        assert np.array_equal(cal_max, self.model.cal), "보정값 재계산이 동결 모델과 다르다"
        self.global_test_offset = self.cal_end      # 평가 기록구간 번호 → 정상 전체 기록구간 번호

    def comps(self, key):
        c = self.parts[key]["comp"]
        return np.column_stack([c[k] for k in COMP])

    def v1_score(self, key):
        """v1 기준선 = fmax(크기, 사인8). press_guard/train.baseline과 같은 산식(동결 v2 모델의 꼬리 사용)."""
        P = self.parts[key]
        s8 = self.model.tails["sine8"](M.sine_score(P["q"][D.SENSORS[2]].to_numpy(float), P["seg"], 8))
        return np.fmax(P["comp"]["g_magnitude"], s8)

    def component_alarm(self, key, alpha, evidence=None, cal=None):
        """성분 g가 단독으로 fmax 문턱을 넘는가 — GuardModel.predict의 reason과 같은 판정.
        기본은 v2 세 성분과 v2 보정값. evidence를 주면 그 성분(자기 fmax 결합)과 그 결합의 보정값으로 판정한다."""
        g, ref = (self.comps(key), self.model.cal) if evidence is None else (evidence[key], cal)
        return np.column_stack([np.nan_to_num(conformal_p(ref, g[:, j]), nan=1.0) <= alpha for j in range(g.shape[1])])

    def evaluate(self, scores, alpha, evidence=None):
        """scores: {'cal','test','abn'} 행 점수. 보정 = 정상 보정 알림 단위(대회 자료에서는 기록구간) 최대 점수, conformal p ≤ α.
        근거 성분 없는 경보: 경보인데 어떤 성분도 단독으로 fmax 문턱을 넘지 않는 행(evidence 설명은 component_alarm)."""
        cal = segment_max(scores["cal"], self.parts["cal"]["units"])
        alarms = {k: np.nan_to_num(conformal_p(cal, scores[k]), nan=1.0) <= alpha for k in ("test", "abn")}
        at, aa = alarms["test"], alarms["abn"]
        T, A = self.parts["test"], self.parts["abn"]
        tp, fp = int(aa.sum()), int(at.sum())
        fn = len(aa) - tp
        normal_alerted = pd.Series(at).groupby(T["seg"]).any()
        detected = pd.Series(aa).groupby(A["seg"]).any()
        first = pd.Series(np.where(aa, A["pos"], np.nan)).groupby(A["seg"]).min().dropna() * D.DT
        comp_t = self.component_alarm("test", alpha, evidence, cal).any(1)
        comp_a = self.component_alarm("abn", alpha, evidence, cal).any(1)
        y = np.r_[np.zeros(len(at)), np.ones(len(aa))]
        raw = np.r_[scores["test"], scores["abn"]]
        low = np.nanmin(np.r_[raw, scores["cal"]]) - 1
        s = filled(raw, low)
        rec = pd.DataFrame(dict(r=np.r_[T["seg"], A["seg"] + 100_000], y=y, s=s)).groupby("r").agg(y=("y", "max"), s=("s", "max"))
        nn, na = int(normal_alerted.sum()), int(detected.sum())
        out = dict(threshold=conformal_threshold(cal, alpha)[0], tp=tp, fp=fp, fn=fn, precision=tp / (tp + fp) if tp + fp else 0.0,
                   recall=tp / len(aa), f1_rows=f1(tp, fp, fn),
                   normal_alerted=nn, normal_records=len(normal_alerted), abnormal_detected=na, abnormal_records=len(detected),
                   fn_pos0_1=int((~aa & (A["pos"] <= 1)).sum()), fn_pos2plus=int((~aa & (A["pos"] >= 2)).sum()),
                   delay_median_s=round(float(first.median()), 3) if len(first) else np.nan,
                   delay_max_s=round(float(first.max()), 3) if len(first) else np.nan,
                   no_evidence_alarms_abnormal=int((aa & ~comp_a).sum()), no_evidence_alarms_normal=int((at & ~comp_t).sum()),
                   row_auroc=float(roc_auc_score(y, s)), row_ap=float(average_precision_score(y, s)), oracle_f1_rows=oracle_f1(y, s),
                   record_f1=f1(na, nn, len(detected) - na), record_auroc=float(roc_auc_score(rec.y, rec.s)))
        return out, alarms

    def alerted_global(self, alarm_test):
        """오경보가 난 정상 평가 기록구간의 정상 전체 기록구간 번호."""
        T = self.parts["test"]
        rec = pd.Series(alarm_test).groupby(T["seg"]).any()
        return [int(r) + self.global_test_offset for r in rec[rec].index]


# ---------------------------------------------------------------- M3 · O3 · E7 점수
class ARp:
    """정상 학습 전류의 p차 선형 예측(상수항 포함) 절대 잔차와 정상 학습 꼬리. p=2는 v2의 AR(2)와 같은 계수."""

    def __init__(self, P, order):
        self.order = order
        x = P["q"][D.SENSORS[2]].to_numpy(float)
        idx = window_index(P["seg"], order + 1)
        design = np.column_stack([np.ones(len(idx))] + [x[idx - k] for k in range(1, order + 1)])
        self.coef = np.linalg.lstsq(design, x[idx], rcond=None)[0]
        self.tail = ExpTail(self.residual(P))

    def residual(self, P):
        x = P["q"][D.SENSORS[2]].to_numpy(float)
        idx = window_index(P["seg"], self.order + 1)
        pred = self.coef[0] + sum(self.coef[k] * x[idx - k] for k in range(1, self.order + 1))
        out = np.full(len(x), np.nan)
        out[idx] = np.abs(x[idx] - pred)
        return out

    def g(self, P):
        return self.tail(self.residual(P))


def fusions(g):
    """성분 g=−log10(정상 꼬리 확률) 세 개를 묶는 규칙. 성분이 모두 결측이면 결측."""
    k = np.isfinite(g).sum(1)
    none = k == 0
    kk = np.maximum(k, 1)
    with np.errstate(all="ignore"):
        tippett = np.where(none, np.nan, np.nanmax(np.where(np.isfinite(g), g, -np.inf), 1))
        total = np.where(none, np.nan, np.nansum(g, 1))
        fisher = np.where(none, np.nan, -stats.chi2.logsf(2 * np.log(10) * total, 2 * kk) / np.log(10))
        z = stats.norm.isf(np.clip(10.0 ** (-g), 1e-300, 1))
        stouffer = np.where(none, np.nan, np.nansum(z, 1) / np.sqrt(kk))
    return {"tippett_fmax": tippett, "fisher": fisher, "stouffer": stouffer, "sum": total, "mean": total / kk}


FUSION_TEXT = {
    "tippett_fmax": "fmax(g) = Tippett 최소 p(주 모델 v2)",
    "fisher": "Fisher −2Σln p ~ χ²(2k)의 −log10 꼬리",
    "stouffer": "Stouffer Σz/√k(z=Φ⁻¹(1−p))",
    "sum": "합 Σg",
    "mean": "평균 Σg/k",
}


def same_feature_alternatives(ctxs):
    rows, checks = [], {}
    for sid, C in ctxs.items():
        mats = {k: np.nan_to_num(C.comps(k), nan=0.0) for k in ("train", "cal", "test", "abn")}
        nn5 = NearestNeighbors(n_neighbors=5).fit(mats["train"])
        iso = IsolationForest(random_state=0).fit(mats["train"])
        early = {k: np.fmax(C.parts[k]["comp"]["g_magnitude"], C.parts[k]["comp"]["g_waveform"]) for k in ("train", "cal", "test", "abn")}
        cand = {
            "v2 (fmax, AR(2))": ("v2 주 모델", V2_INPUT, {k: C.parts[k]["comp"]["score"] for k in ("cal", "test", "abn")}),
            "5NN(v2 성분)": ("같은 특징 대안", V2_INPUT + ". 정상 학습 성분 공간의 5-최근접 평균 거리(결측 성분 0)",
                            {k: nn5.kneighbors(mats[k])[0].mean(1) for k in ("cal", "test", "abn")}),
            "IF(v2 성분)": ("같은 특징 대안", V2_INPUT + ". Isolation Forest(random_state=0) 이상 점수(결측 성분 0)",
                           {k: -iso.score_samples(mats[k]) for k in ("cal", "test", "abn")}),
            "합(v2 성분)": ("같은 특징 대안", V2_INPUT + ". 성분 합(결측 성분 0)", {k: mats[k].sum(1) for k in ("cal", "test", "abn")}),
        }
        # 같은 보정 규칙에서 성분 하나만 쓴 탐지기(적대적 채점 J1: 일반 시계열 기준선). 예측 오차 단독이 정상 학습 AR(2) 잔차 하나다.
        for label, key, text in SINGLE_COMPONENTS:
            one = {k: C.parts[k]["comp"][key] for k in ("cal", "test", "abn")}
            cand[label] = ("단일 성분", text, one, {k: v[:, None] for k, v in one.items()})
        for order in (1, 2, 3, 4):
            ar = ARp(C.parts["train"], order)
            if order == 2:
                checks[f"{sid}_ar2_coef_equals_frozen"] = bool(np.allclose(ar.coef, C.model.coef, rtol=0, atol=1e-12))
            gar = {k: ar.g(C.parts[k]) for k in ("cal", "test", "abn")}
            own = {k: np.column_stack([C.parts[k]["comp"]["g_magnitude"], C.parts[k]["comp"]["g_waveform"], gar[k]]) for k in gar}
            cand[f"early+AR({order})"] = ("이웃 설계(AR 차수)",
                                          f"크기 + 초반 6→8 사인 + AR({order}) 전류 잔차(정상 학습 적합·꼬리), fmax",
                                          {k: np.fmax(early[k], gar[k]) for k in gar}, own)
        for alpha in ALPHAS:
            ref = None
            for name, spec in cand.items():
                family, inputs, scores = spec[:3]
                r, al = C.evaluate(scores, alpha, spec[3] if len(spec) > 3 else None)
                if name.startswith("v2 "):
                    ref = al
                if name == "early+AR(2)":
                    checks[f"{sid}_{alpha}_ar2_generic_equals_v2"] = bool(all(np.array_equal(al[k], ref[k]) for k in al))
                rows.append(dict(split_id=sid, alpha=alpha, candidate=name, family=family, input_condition=inputs,
                                 uses_abnormal_labels="아니오", **r, status=("주 모델" if name.startswith("v2 ") else POSTHOC),
                                 remark=ALT_REMARK.get(name, "")))
    return pd.DataFrame(rows), checks


SINGLE_COMPONENTS = (("크기 단독", "g_magnitude", "세 센서 max|z|(정상 학습 꼬리) 하나"),
                     ("파형 단독", "g_waveform", "전류 초반 6→8 사인 1−R²(정상 학습 꼬리) 하나"),
                     ("예측 오차(AR(2)) 단독", "g_dynamics", "전류 AR(2) 잔차(정상 학습 적합·꼬리) 하나 — 일반 시계열 기준선"))
ALT_REMARK = {
    "v2 (fmax, AR(2))": KEEP_FMAX,
    "5NN(v2 성분)": ("같은 입력이면 5NN이 미탐을 조금 줄인다(α=1%: A 44→36, B 31→29, 정상 알림 같음). α=1% 주입 전이에서도 A는 모든 족에서 fmax와 같거나 높고 "
                    "B는 단발 진동 충격 4σ에서만 낮다(rule_transfer_injection_v2.csv). 대신 단독으로 문턱을 넘은 성분이 없는 경보가 생겨 "
                    "근거→조치 판단표가 끊긴다. 사후 비교라 채택하지 않는다"),
    "IF(v2 성분)": "α=1%에서 미탐이 크게 늘고(A 120, B 117) 이상 1구간을 놓친다",
    "합(v2 성분)": "α=1%에서 A는 미탐이 조금 줄고(44→40) B는 늘며(31→39) B 정상 알림은 3→2다. 단독 성분 근거가 없는 경보가 생긴다",
    "early+AR(1)": "AR(2)보다 미탐이 많다",
    "early+AR(2)": "일반 구현으로 다시 적합한 AR(2). v2와 경보가 같음을 확인하는 대조",
    "early+AR(3)": "AR(2)보다 미탐이 많다",
    "early+AR(4)": "AR(2)보다 미탐이 많고 B 정상 알림이 늘어난다",
    "크기 단독": "같은 보정 규칙의 단일 성분(사후 비교). 이상 기록 3개를 놓치고 행 미탐이 크게 는다",
    "파형 단독": "같은 보정 규칙의 단일 성분(사후 비교). 이상 기록 3개를 놓친다",
    "예측 오차(AR(2)) 단독": ("같은 보정 규칙의 일반 시계열 기준선(사후 비교). 이상 기록 1개를 놓치고 행 F1이 v2보다 낮다. "
                               "B에서는 정상 알림이 v2보다 적어(1/180 대 3/180) 기록 F1은 더 높다"),
}
RULE_REMARK = {
    "tippett_fmax": KEEP_FMAX,
    "fisher": ("α=1%에서 A 미탐이 적고(44→32) B 정상 알림이 적다(3→1). α=1% 주입 전이는 A에서 fmax와 같거나 높고 B의 진동 잡음 2σ·전류 잡음 0.1σ·단발 충격 4σ·6σ에서 낮다"
               "(rule_transfer_injection_v2.csv). 대신 어느 성분도 단독으로 문턱을 넘지 않은 경보가 생긴다(A 12행, B 1행). 사후 비교라 채택하지 않는다"),
    "stouffer": "정상 알림은 적으나 미탐이 늘고(α=1%: A 39, B 39) 근거 없는 경보가 생긴다",
    "sum": "α=1%에서 A는 미탐이 조금 줄고(44→40) B는 늘며(31→39) B 정상 알림은 3→2다. 단독 성분 근거가 없는 경보가 생긴다",
    "mean": "정상 알림은 적으나 두 분할 모두 미탐이 늘고(α=1%: 42) A에서 근거 없는 경보가 생긴다",
}


def combination_rules(ctxs):
    rows = []
    for sid, C in ctxs.items():
        fu = {k: fusions(C.comps(k)) for k in ("cal", "test", "abn")}
        assert np.array_equal(np.nan_to_num(fu["test"]["tippett_fmax"], nan=-1), np.nan_to_num(C.parts["test"]["comp"]["score"], nan=-1))
        for alpha in ALPHAS:
            for name in FUSION_TEXT:
                r, _ = C.evaluate({k: fu[k][name] for k in fu}, alpha)
                rows.append(dict(split_id=sid, alpha=alpha, rule=name, definition=FUSION_TEXT[name], input_condition=V2_INPUT,
                                 calibration="규칙마다 결합 점수 하나를 정상 보정 기록구간 최대로 conformal 재보정",
                                 **r, status=("주 모델" if name == "tippett_fmax" else POSTHOC), remark=RULE_REMARK[name]))
    return pd.DataFrame(rows)


def fp_mitigation(ctxs):
    """E7: v1에서 오경보를 줄이려고 시험한 두 대응(지속성, 진폭 정규화)을 v2 성분에 옮겨 α 1·3·5%로 한 번 평가."""
    rows = []
    for sid, C in ctxs.items():
        ln = LoadNormalizer(C.parts["train"]["q"], C.parts["train"]["seg"])
        tail = ExpTail(ln.ref)
        ln_note = f" [적합 {ln.n_fit}행, 진폭–진동 상관 {ln.slope_corr:.3f}, 꼬리 적합 {tail.ok}]"
        variants = {}
        for k in ("cal", "test", "abn"):
            P = C.parts[k]
            c = P["comp"]
            p23 = persistence_score(c["g_magnitude"], P["seg"], 2, 3)
            p23_fill = np.where(np.isfinite(p23), p23, c["g_magnitude"])
            g_res = tail(ln.score(P["q"], P["seg"]))
            mag_ln = np.where(np.isfinite(g_res), g_res, c["g_magnitude"])
            rest = np.fmax(c["g_waveform"], c["g_dynamics"])
            variants.setdefault("v2", {})[k] = c["score"]
            variants.setdefault("v2_mag_persist2of3", {})[k] = np.fmax(p23, rest)
            variants.setdefault("v2_mag_persist2of3_fill", {})[k] = np.fmax(p23_fill, rest)
            variants.setdefault("v2_loadnorm", {})[k] = np.fmax(mag_ln, rest)
        text = {
            "v2": "주 모델(기준)",
            "v2_mag_persist2of3": "크기 성분만 같은 기록구간 최근 3행 중 2번째 큰 값(v1 persistence_score). 위치 0·1은 크기 미판정",
            "v2_mag_persist2of3_fill": "위와 같되 3행이 쌓이기 전(위치 0·1)은 원래 크기 성분",
            "v2_loadnorm": ("크기 성분을 전류 진폭 조건부 진동 잔차로 대체(v1 LoadNormalizer: 정상 학습 앞 80% 기록에서 "
                            "AI0 trailing-17 표준편차 ~ 전류 trailing-17 진폭 선형 적합, 잔차/SD의 정상 꼬리). 17행 전은 원래 크기" + ln_note),
        }
        for alpha in ALPHAS:
            base, base_al = C.evaluate(variants["v2"], alpha)
            base_fp = set(C.alerted_global(base_al["test"]))
            for name, sc in variants.items():
                r, al = C.evaluate(sc, alpha)
                fp_rec = set(C.alerted_global(al["test"]))
                rows.append(dict(split_id=sid, alpha=alpha, variant=name, source="v2 성분(이 폴더 계산)", definition=text[name],
                                 threshold=r["threshold"], normal_alerted=r["normal_alerted"], normal_records=r["normal_records"], fp_rows=r["fp"],
                                 fn_rows=r["fn"], fn_pos0_1=r["fn_pos0_1"], fn_pos2plus=r["fn_pos2plus"],
                                 abnormal_detected=r["abnormal_detected"], delay_median_s=r["delay_median_s"], delay_max_s=r["delay_max_s"],
                                 f1_rows=r["f1_rows"], delta_normal_alerted=r["normal_alerted"] - base["normal_alerted"],
                                 delta_fn_rows=r["fn"] - base["fn"],
                                 alerted_normal_records=" ".join(map(str, sorted(fp_rec))),
                                 removed_vs_v2=" ".join(map(str, sorted(base_fp - fp_rec))), added_vs_v2=" ".join(map(str, sorted(fp_rec - base_fp))),
                                 status=("주 모델" if name == "v2" else POSTHOC + ". 채택하지 않음"), remark=MITIGATION_REMARK[name]))
    # v1에서 같은 대응을 시험한 커밋 결과(참고 행)
    sub = YEJUN / "press_submission" / "outputs"
    ref_rows = []
    for file, model, ref, label in (("load_normalization.csv", "loadnorm_resid_plus_sine", "main_combined_w8(reference)", "v1_loadnorm"),
                                    ("persistence.csv", "persist_k2n3", "persist_k1n1", "v1_persist2of3(결합 점수 전체)")):
        t = pd.read_csv(sub / file)
        t = t[t.criterion.eq("conformal") & t.calibration_unit.eq("recording_segments") & t.preprocess.eq("matched")]
        for sid in ctxs:
            name = D.SPLITS[sid][0]
            for alpha in ALPHAS:
                a = t[t.split.eq(name) & t.model.eq(model) & np.isclose(t.alpha, alpha)].iloc[0]
                b = t[t.split.eq(name) & t.model.eq(ref) & np.isclose(t.alpha, alpha)].iloc[0]
                ref_rows.append(dict(split_id=sid, alpha=alpha, variant=label, source=f"yejun/press_submission/outputs/{file}(커밋, v1 기준선)",
                                     definition=f"v1 결합 fmax(크기, 사인8)에 적용. 기준 = {ref}",
                                     normal_alerted=int(a.normal_notified_segments), normal_records=int(a.normal_segments), fp_rows=int(a.fp),
                                     fn_rows=int(a.fn), abnormal_detected=int(a.abnormal_notified_segments),
                                     delay_median_s=float(a.delay_median_s), delay_max_s=float(a.delay_max_s), f1_rows=float(a.f1_all_rows),
                                     delta_normal_alerted=int(a.normal_notified_segments - b.normal_notified_segments),
                                     delta_fn_rows=int(a.fn - b.fn), status="v1 기존 결과(참고)"))
    imp = pd.read_csv(YEJUN / "analysis" / "press_improvement" / "candidate_metrics.csv")
    imp = imp[imp.criterion.eq("conformal") & imp.eval_preprocess.eq("matched")]
    for sid in ctxs:
        name = D.SPLITS[sid][0]
        for alpha in ALPHAS:
            a = imp[imp.split.eq(name) & imp.model.eq("magnitude_persist2of3") & np.isclose(imp.alpha, alpha)].iloc[0]
            b = imp[imp.split.eq(name) & imp.model.eq("baseline_w8") & np.isclose(imp.alpha, alpha)].iloc[0]
            ref_rows.append(dict(split_id=sid, alpha=alpha, variant="v1_mag_persist2of3", source="yejun/analysis/press_improvement/candidate_metrics.csv(커밋)",
                                 definition="v1 결합에서 크기 성분만 2/3 지속성. 기준 = baseline_w8",
                                 normal_alerted=int(a.normal_notified_segments), normal_records=int(a.normal_segments), fp_rows=int(a.fp),
                                 fn_rows=int(a.fn), abnormal_detected=int(a.abnormal_notified_segments),
                                 delay_median_s=float(a.delay_median_s), delay_max_s=float(a.delay_max_s), f1_rows=float(a.f1_all_rows),
                                 delta_normal_alerted=int(a.normal_notified_segments - b.normal_notified_segments),
                                 delta_fn_rows=int(a.fn - b.fn), status="v1 기존 결과(참고)"))
    return pd.concat([pd.DataFrame(rows), pd.DataFrame(ref_rows)], ignore_index=True)


MITIGATION_REMARK = {
    "v2": "",
    "v2_mag_persist2of3": "위치 0·1에서 크기 성분이 빠져 그 위치 미탐이 늘어난다",
    "v2_mag_persist2of3_fill": ("사후로는 두 분할·모든 α에서 v2보다 정상 알림과 미탐이 같거나 적다. 원인은 문턱이다: 보정 기록구간 최대 점수를 만든 "
                                "단발(1행) 크기 급등이 지속성으로 빠져 conformal 문턱이 낮아졌다(threshold 열). 대가로 1행짜리 진동 충격형 이상은 "
                                "위치 2 이후 경보하지 않는다(주입 비용은 fp_mitigation_injection_v2.csv). 탐색 장부 뒤에 이미 본 이상 자료로 더한 사후 후보다. 채택하지 않는다"),
    "v2_loadnorm": "v1의 진폭 정규화를 옮긴 것. B에서 오경보 3→1(구간 423·461 제거)로 v1과 같은 방향이나 A에서 정상 알림 1(구간 570)이 생긴다",
}


# E7 보강: 지속성 변형의 비용을 주입으로 잰다. 주입 방식은 press_guard/recalibrate.py 수락 검사(b)와 같다
# (30행 이상 정상 평가 단위, 10행째부터 계단형, 2초 안 탐지). 잡음·충격 족은 반복 5회(np.random.default_rng(rep)).
INJ_FAMILIES = (("none", 0.0), ("cur_noise", .1), ("cur_noise", .2), ("cur_offset", .2), ("cur_offset", .4), ("vib_noise", 2.0),
                ("vib_noise", 4.0), ("vib_shock", 4.0), ("vib_shock", 6.0), ("vib_shock", 8.0))
INJ_REPS = 5
INJ_TEXT = {"none": "주입 없음(2초 창 안 경보율 = 오경보 기준선)", "cur_noise": "전류 잡음 level×σ(10행째부터)",
            "cur_offset": "전류 오프셋 level×√2×σ(10행째부터)", "vib_noise": "진동 두 센서 잡음 level×σ(10행째부터)",
            "vib_shock": "단발 진동 충격: 10행째 한 행에만 진동 두 센서 ±level×σ(부호 rng)"}


def persist_fill_score(comp, seg):
    """fp_mitigation_v2.csv의 v2_mag_persist2of3_fill과 같은 점수."""
    p23 = persistence_score(comp["g_magnitude"], seg, 2, 3)
    return np.fmax(np.where(np.isfinite(p23), p23, comp["g_magnitude"]), np.fmax(comp["g_waveform"], comp["g_dynamics"]))


def vib_shock(frame, model, level, mask, rng):
    """단위의 10행째 한 행에만 진동 두 센서에 ±level×σ 충격(부호는 rng). recalibrate.inject와 같은 입력 정리."""
    out = D.inputs_only(frame).copy()
    for c in D.SENSORS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    sign = rng.choice(np.array([-1.0, 1.0]), size=(int(mask.sum()), 2))
    for k, c in enumerate(D.SENSORS[:2]):
        out.loc[mask, c] += level * model.scale[k] * sign[:, k]
    return out


RULES_T = ("v2_fmax", "fisher", "stouffer", "sum", "5nn")
RULE_T_TEXT = {"v2_fmax": "fmax = Tippett(v2 주 모델)", "fisher": "Fisher", "stouffer": "Stouffer", "sum": "합 Σg", "5nn": "5NN(v2 성분 공간)"}


def rule_scores(comp, nn5):
    """같은 특징 대안의 결합 점수(same_feature_alternatives·combination_rules와 같은 정의)."""
    g = np.column_stack([comp[k] for k in COMP])
    fu = fusions(g)
    return {"v2_fmax": comp["score"], "fisher": fu["fisher"], "stouffer": fu["stouffer"], "sum": fu["sum"],
            "5nn": nn5.kneighbors(np.nan_to_num(g, nan=0.0))[0].mean(1)}


def fp_mitigation_injection(ctxs, normal, seg_all):
    """E7 지속성 변형의 주입 비용과, 같은 주입에서 같은 특징 대안(Fisher·Stouffer·합·5NN)의 전이(평가관 02 2회차 R2-M1).
    두 표 모두 사후 비교다."""
    R = _import_guard("recalibrate")
    rows, rule_rows, checks = [], [], {}
    for sid, C in ctxs.items():
        nn5 = NearestNeighbors(n_neighbors=5).fit(np.nan_to_num(C.comps("train"), nan=0.0))
        rule_cals = {k: segment_max(v, C.parts["cal"]["units"]) for k, v in rule_scores(C.parts["cal"]["comp"], nn5).items()}
        assert np.array_equal(rule_cals["v2_fmax"], C.model.cal)
        rule_per = {}
        test = D.split_normal(normal, seg_all, sid)["test"]
        units, in_unit, size = R.unit_layout(test)
        eligible = size >= R.MIN_UNIT_ROWS
        window = (in_unit >= R.T0) & (in_unit < R.T0 + R.WINDOW)
        n_units = int(pd.Series(units[eligible]).nunique())
        cals = {"v2": C.model.cal,
                "persist_fill": segment_max(persist_fill_score(C.parts["cal"]["comp"], C.parts["cal"]["seg"]), C.parts["cal"]["units"])}
        results = {}
        for family, level in INJ_FAMILIES:
            reps = INJ_REPS if family in ("cur_noise", "vib_noise", "vib_shock") else 1
            per = {(m, a): [] for m in cals for a in ALPHAS}
            rper = {(m, a): [] for m in rule_cals for a in ALPHAS}
            for rep in range(reps):
                rng = np.random.default_rng(rep)
                if family == "none":
                    X = D.inputs_only(test)
                elif family == "vib_shock":
                    X = vib_shock(test, C.model, level, eligible & (in_unit == R.T0), rng)
                else:
                    X = R.inject(test, C.model, family, level, eligible & (in_unit >= R.T0), rng)
                q = D.quantize(D.inputs_only(X), "matched")
                seg = layout(q)[1]
                comp = C.model.components(q, seg)
                scores = {"v2": comp["score"], "persist_fill": persist_fill_score(comp, seg)}
                for m, sc in scores.items():
                    for a in ALPHAS:
                        alarm = np.nan_to_num(conformal_p(cals[m], sc), nan=1.0) <= a
                        if m == "v2" and rep == 0 and a == .01 and family in ("vib_shock", "cur_noise") and level in (6.0, .1):
                            checks[f"{sid}_{family}_v2_alarm_equals_predict"] = bool(np.array_equal(alarm, C.model.predict(X, a).alarm.to_numpy(bool)))
                        hit = alarm & window & eligible
                        f = pd.DataFrame(dict(u=units[eligible], hit=hit[eligible], d=np.where(hit, in_unit - R.T0, np.nan)[eligible])).groupby("u")
                        per[(m, a)].append((f.hit.any().to_numpy(), f.d.min().to_numpy()))
                for m, sc in rule_scores(comp, nn5).items():
                    for a in ALPHAS:
                        hit = (np.nan_to_num(conformal_p(rule_cals[m], sc), nan=1.0) <= a) & window & eligible
                        rper[(m, a)].append(pd.Series(hit[eligible]).groupby(units[eligible]).any().to_numpy())
            results[(family, level)] = (reps, per)
            rule_per[(family, level)] = (reps, rper)
        for a in ALPHAS:
            none = {m: float(np.concatenate([h for h, _ in results[("none", 0.0)][1][(m, a)]]).mean()) for m in cals}
            for family, level in INJ_FAMILIES:
                reps, per = results[(family, level)]
                row = dict(split_id=sid, alpha=a, family=family, level=level, definition=INJ_TEXT[family], reps=reps, units=n_units)
                for m in cals:
                    hits = np.concatenate([h for h, _ in per[(m, a)]])
                    delays = np.concatenate([d for _, d in per[(m, a)]])
                    row[f"{m}_detect_2s"] = float(hits.mean())
                    row[f"{m}_delay_median_s"] = float(np.nanmedian(delays) * D.DT) if np.isfinite(delays).any() else np.nan
                    row[f"{m}_none_alarm_rate"] = none[m]
                row["detect_diff"] = row["persist_fill_detect_2s"] - row["v2_detect_2s"]
                row["status"] = "사후 비용 측정. 지속성 변형은 채택하지 않음"
                rows.append(row)
                reps_r, rper = rule_per[(family, level)]
                rr = dict(split_id=sid, alpha=a, family=family, level=level, definition=INJ_TEXT[family], reps=reps_r, units=n_units)
                for m in rule_cals:
                    rr[f"{m}_detect_2s"] = float(np.concatenate(rper[(m, a)]).mean())
                assert rr["v2_fmax_detect_2s"] == row["v2_detect_2s"]
                alts = [m for m in rule_cals if m != "v2_fmax"]
                rr["best_alternative"] = max(alts, key=lambda m: rr[f"{m}_detect_2s"])
                rr["fmax_minus_best_alternative"] = rr["v2_fmax_detect_2s"] - rr[f"{rr['best_alternative']}_detect_2s"]
                rr["status"] = "사후 비교(이상 21구간을 이미 본 뒤). 채택 근거가 아니다. 각 규칙은 자기 결합 점수를 정상 보정 최대로 재보정"
                rule_rows.append(rr)
    return pd.DataFrame(rows), pd.DataFrame(rule_rows), checks


# ---------------------------------------------------------------- M4 선정 근거
WINS = (5, 6, 8, 10, 12, 15, 20)
V1_NAME, V2_NAME = "advance:baseline_w8", "advance:early6_ar2"


def candidate_universe(normal, abnormal, seg_all):
    """선정 전 단계(v1 패키지·improvement·advance·early)의 점수 규칙을 원래 코드로 다시 계산한다(α=1%, conformal, matched)."""
    adv = load_module("sel_adv", YEJUN / "analysis" / "press_advance" / "run_experiment.py")
    imp = load_module("sel_imp", YEJUN / "analysis" / "press_improvement" / "run_experiment.py")
    ear = load_module("sel_ear", YEJUN / "analysis" / "press_early" / "run_experiment.py")
    vendor = D.load_vendor()
    stats_, segs_all = {}, {}
    for sid in D.SPLITS:
        split = D.split_normal(normal, seg_all, sid)
        tr = D.quantize(split["train"], "matched")
        seg_tr = D.segments(tr)
        frames = dict(cal=D.quantize(split["cal"], "matched"), test=D.quantize(split["test"], "matched"), abn=D.quantize(abnormal, "matched"))
        segs = {k: D.segments(f) for k, f in frames.items()}
        segs_all[sid] = segs
        u = {}
        sc = Scorer(tr, seg_tr, vendor, wins=WINS, baselines=True)
        per = {k: sc.score(frames[k], segs[k])[0] for k in frames}
        u.update({f"v1pkg:{n}": {k: per[k][n] for k in frames} for n in per["cal"]})
        cs = imp.CandidateScorer(tr, seg_tr, vendor)
        per = {k: cs.score(frames[k], segs[k]) for k in frames}
        u.update({f"improve:{n}": {k: per[k][n] for k in frames} for n in per["cal"]})
        base = Scorer(tr, seg_tr, vendor, wins=(6, 8), baselines=False)
        dyn = adv.Dynamics(tr, seg_tr)
        per = {k: adv.scores(base, dyn, frames[k], segs[k]) for k in frames}
        u.update({f"advance:{n}": {k: per[k][n] for k in frames} for n in per["cal"]})
        ar2, ar1, joint = ear.Linear(tr, seg_tr, 2), ear.Linear(tr, seg_tr, 1), ear.Joint(base.scaler, tr)
        per = {k: ear.scores(base, ar2, joint, ar1, frames[k], segs[k]) for k in frames}
        u.update({f"early:{n}": {k: per[k][n] for k in frames} for n in per["cal"]})
        for name, s in u.items():
            cal = segment_max(s["cal"], segs["cal"])
            an = np.nan_to_num(conformal_p(cal, s["test"]), nan=1.0) <= .01
            aa = np.nan_to_num(conformal_p(cal, s["abn"]), nan=1.0) <= .01
            g = pd.DataFrame(dict(r=segs["abn"], a=aa)).groupby("r").a
            stats_[(sid, name)] = dict(normal_alerted=int(pd.Series(an).groupby(segs["test"]).any().sum()), fp=int(an.sum()),
                                       fn_by_rec=(g.size() - g.sum()).to_numpy(int), det_by_rec=g.any().to_numpy(bool),
                                       alarm_abn=aa, alarm_test=an)
    # 커밋 표와 대조(평가관 02 C4와 같은 원표·필터)
    sub = YEJUN / "press_submission" / "outputs"
    v1all = pd.read_csv(sub / "model_comparison_all.csv")
    v1all = v1all[v1all.criterion.eq("conformal") & np.isclose(v1all.alpha, .01) & v1all.calibration_unit.eq("recording_segments")]
    sens = pd.read_csv(sub / "sensitivity.csv")
    sens = sens[sens.criterion.eq("conformal") & np.isclose(sens.alpha, .01) & sens.preprocess.eq("matched")]
    impt = pd.read_csv(YEJUN / "analysis" / "press_improvement" / "candidate_metrics.csv")
    impt = impt[impt.criterion.eq("conformal") & np.isclose(impt.alpha, .01) & impt.eval_preprocess.eq("matched")]
    advt = pd.read_csv(YEJUN / "analysis" / "press_advance" / "metrics.csv")
    advt = advt[advt.criterion.eq("conformal") & np.isclose(advt.alpha, .01) & advt.input_variant.eq("matched")]
    eart = pd.read_csv(YEJUN / "analysis" / "press_early" / "metrics.csv")
    eart = eart[eart.criterion.eq("conformal") & np.isclose(eart.alpha, .01) & eart.input_variant.eq("matched")]
    ref = {"v1pkg": (pd.concat([v1all, sens]), "press_submission/outputs/model_comparison_all.csv·sensitivity.csv"),
           "improve": (impt, "analysis/press_improvement/candidate_metrics.csv"),
           "advance": (advt, "analysis/press_advance/metrics.csv"), "early": (eart, "analysis/press_early/metrics.csv")}
    names = sorted({n for (_, n) in stats_})
    sig = {}
    for n in names:
        key = np.r_[stats_[("A", n)]["alarm_abn"], stats_[("A", n)]["alarm_test"], stats_[("B", n)]["alarm_abn"],
                    stats_[("B", n)]["alarm_test"]].astype(np.uint8).tobytes()
        sig.setdefault(key, []).append(n)
    pattern_of = {n: i for i, group in enumerate(sorted(sig.values())) for n in group}
    rows = []
    for sid in D.SPLITS:
        for n in names:
            st = stats_[(sid, n)]
            fam, model_name = n.split(":", 1)
            t, src = ref[fam]
            c = t[t.split.eq(D.SPLITS[sid][0]) & t.model.eq(model_name)]
            fn = int(st["fn_by_rec"].sum())
            row = dict(split_id=sid, candidate=n, stage=fam, alarm_pattern=pattern_of[n], normal_alerted=st["normal_alerted"], fp=st["fp"],
                       fn=fn, abnormal_detected=int(st["det_by_rec"].sum()), f1_rows=f1(600 - fn, st["fp"], fn), committed_source=src)
            if len(c):
                c = c.iloc[0]
                row.update(committed_fn=int(c.fn), committed_normal_alerted=int(c.normal_notified_segments), committed_fp=int(c.fp),
                           matches_committed=bool(fn == c.fn and st["normal_alerted"] == c.normal_notified_segments and st["fp"] == c.fp))
            rows.append(row)
    universe = pd.DataFrame(rows)
    return universe, stats_, sig, pattern_of


def nested_selection(stats_, sig):
    """선택 규칙: 두 분할 모두 정상 알림 ≤ v1, 학습에 쓴 이상 구간 전부 탐지, 두 분할 미탐 합 최소(동률: 정상 알림 합, 이름).
    같은 경보 벡터의 후보는 하나로 합친다. 이상 기록 1개를 빼고 규칙을 적용해 뽑힌 후보의 뺀 기록 미탐을 더한다."""
    unique = sorted(group[0] for group in sig.values())
    rep = {n: group[0] for group in sig.values() for n in group}
    v1, v2 = rep[V1_NAME], rep[V2_NAME]
    lim = {s: stats_[(s, v1)]["normal_alerted"] for s in "AB"}
    eligible = [u for u in unique if all(stats_[(s, u)]["normal_alerted"] <= lim[s] for s in "AB")]
    rows = []
    for j in range(N_ABN):
        keep = np.arange(N_ABN) != j
        best = None
        for u in eligible:
            if not all(stats_[(s, u)]["det_by_rec"][keep].all() for s in "AB"):
                continue
            key = (sum(int(stats_[(s, u)]["fn_by_rec"][keep].sum()) for s in "AB"),
                   stats_[("A", u)]["normal_alerted"] + stats_[("B", u)]["normal_alerted"], u)
            best = key if best is None or key < best else best
        chosen = best[2]
        rows.append(dict(held_out_record=j, chosen=chosen, chosen_is_v2=chosen == v2, train_fn_total=best[0],
                         held_out_fn_A=int(stats_[("A", chosen)]["fn_by_rec"][j]), held_out_fn_B=int(stats_[("B", chosen)]["fn_by_rec"][j]),
                         v2_held_out_fn_A=int(stats_[("A", v2)]["fn_by_rec"][j]), v2_held_out_fn_B=int(stats_[("B", v2)]["fn_by_rec"][j])))
    return pd.DataFrame(rows), dict(eligible=eligible, v1_limit=lim, v2_rep=v2, aliases={g[0]: g[1:] for g in sig.values() if len(g) > 1})


def paired_records(ctxs):
    """v1 대비 기록구간 짝 비교. 커밋 산출물(records_first_alarm_v2.csv)을 쓰고 이 폴더의 재계산과 대조한다."""
    rec = pd.read_csv(GUARD / "outputs" / "records_first_alarm_v2.csv")
    metrics = pd.read_csv(GUARD / "outputs" / "metrics.csv")
    rng = np.random.default_rng(SEED)
    rows, summary, checks = [], {}, {}
    for sid, C in ctxs.items():
        r = rec[rec.split_id.eq(sid)].sort_values("record_id")
        fn1, fn2 = r.v1_fn_rows.to_numpy(int), r.v2_fn_rows.to_numpy(int)
        # 재계산 대조
        s1 = {k: C.v1_score(k) for k in ("cal", "test", "abn")}
        _, al1 = C.evaluate(s1, .01)
        _, al2 = C.evaluate({k: C.parts[k]["comp"]["score"] for k in ("cal", "test", "abn")}, .01)
        A = C.parts["abn"]
        g1 = pd.DataFrame(dict(r=A["seg"], a=al1["abn"])).groupby("r").a
        g2 = pd.DataFrame(dict(r=A["seg"], a=al2["abn"])).groupby("r").a
        checks[f"{sid}_records_match_recomputed"] = bool(np.array_equal((g1.size() - g1.sum()).to_numpy(), fn1)
                                                        and np.array_equal((g2.size() - g2.sum()).to_numpy(), fn2))
        m = metrics[metrics.split.eq(sid) & np.isclose(metrics.alpha, .01)].set_index("model")
        fp1, fp2 = int(m.loc["baseline_v1", "fp"]), int(m.loc["guard_v2", "fp"])
        rows_per = r.rows.to_numpy(int)
        better, equal, worse = int((fn2 < fn1).sum()), int((fn2 == fn1).sum()), int((fn2 > fn1).sum())
        sign_p = float(stats.binom.sf(better - 1, better + worse, .5)) if better + worse else 1.0
        dfn, df1 = [], []
        for _ in range(BOOT):
            idx = rng.integers(0, len(fn1), len(fn1))
            n_rows = rows_per[idx].sum()
            a1, a2 = fn1[idx].sum(), fn2[idx].sum()
            dfn.append(a1 - a2)
            df1.append(f1(n_rows - a2, fp2, a2) - f1(n_rows - a1, fp1, a1))
        summary[sid] = dict(fn_v1=int(fn1.sum()), fn_v2=int(fn2.sum()), better=better, equal=equal, worse=worse, sign_p=sign_p,
                            delta_f1=f1(600 - fn2.sum(), fp2, fn2.sum()) - f1(600 - fn1.sum(), fp1, fn1.sum()),
                            delta_f1_ci=(float(np.percentile(df1, 2.5)), float(np.percentile(df1, 97.5))),
                            delta_fn_ci=(float(np.percentile(dfn, 2.5)), float(np.percentile(dfn, 97.5))), fp_v1=fp1, fp_v2=fp2)
        for k in range(len(r)):
            rows.append(dict(split_id=sid, record_id=int(r.record_id.iloc[k]), rows=int(rows_per[k]), v1_fn_rows=int(fn1[k]),
                             v2_fn_rows=int(fn2[k]), comparison=("v2 개선" if fn2[k] < fn1[k] else "동일" if fn2[k] == fn1[k] else "v2 악화")))
    return pd.DataFrame(rows), summary, checks


def search_ledger():
    """같은 이상 21구간에서 성능을 본 점수 규칙(단계별 이름 기준, 평가관 02 C5와 같은 규칙)."""
    Y = YEJUN
    stages = (
        ("v1 비교", "press_submission/outputs/model_comparison_all.csv", "model", True),
        ("v1 창 민감도", "press_submission/outputs/sensitivity.csv", "model", True),
        ("v1 절제", "press_submission/outputs/ablation.csv", "ablation", True),
        ("v1 지속성", "press_submission/outputs/persistence.csv", "model", True),
        ("v1 진폭 정규화", "press_submission/outputs/load_normalization.csv", "model", True),
        ("improvement", "analysis/press_improvement/candidate_metrics.csv", "model", True),
        ("advance(v2 선정)", "analysis/press_advance/metrics.csv", "model", True),
        ("early", "analysis/press_early/metrics.csv", "model", True),
        ("v2 절제", "press_guard/outputs/ablation_v2.csv", "model", False),
        ("지도학습 기준선", "analysis/press_supervised/grouped_records.csv", "model", False),
        ("가이드북 LSTM-AE", "press_submission/outputs/lstm_guidebook_reproduction.json", None, False),
    )
    rows = []
    for stage, path, col, before in stages:
        names = ["guidebook_lstm_ae"] if col is None else sorted(pd.read_csv(Y / path)[col].unique().tolist())
        rows.append(dict(stage=stage, source=f"yejun/{path}", rules=len(names), names=" ".join(names),
                         before_v2_selection=("예" if before else "아니오(선정 후 설명·비교)")))
    return pd.DataFrame(rows)


def git_first_add(path):
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%h %ad", "--date=format:%Y-%m-%d %H:%M:%S", "--", path],
                             cwd=REPO, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = out.stdout.strip().splitlines() if out.returncode == 0 else []
    return lines[-1] if lines else None


def verify_precommit():
    """PRECOMMIT의 해시·시각을 git 기록과 대조한다. git이 없으면 None(미확인)."""
    result = {}
    for p in PRECOMMIT:
        for side in ("protocol", "result"):
            got = git_first_add(p[side])
            if got is None:
                result[p[side]] = None
                continue
            h, when = got.split(" ", 1)
            result[p[side]] = h.startswith(p[side + "_commit"]) and when == p[side + "_date"]
    return result


def ledger_at(commit, path, col="model"):
    """과거 커밋의 표에서 규칙 이름 수(평가관 02 기준 커밋 대조용). git이 없으면 None."""
    try:
        out = subprocess.run(["git", "show", f"{commit}:yejun/{path}"], cwd=REPO, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    import io
    return int(pd.read_csv(io.BytesIO(out.stdout))[col].nunique())


def tradeoff_rows():
    """절제·시간순·α 트레이드오프(커밋 산출물 인용)."""
    rows = []
    ab = pd.read_csv(GUARD / "outputs" / "ablation_v2.csv")
    ab = ab[ab.criterion.eq("conformal") & np.isclose(ab.alpha, .01)]
    for sid, name in (("A", "normal_60_20_20"), ("B", "normal_50_20_30")):
        t = ab[ab.split.eq(name)].set_index("model")
        v = t.loc["v2"]
        for m, label in (("no_dynamics", "예측 오차 제거"), ("no_waveform", "파형 제거"), ("no_magnitude", "크기 제거"), ("no_early_switch", "초반 6→8 전환 제거")):
            x = t.loc[m]
            rows.append(dict(section="절제(α=1%)", item=label, split=sid,
                             value=f"미탐 {int(v.fn)}→{int(x.fn)}, 탐지 {int(v.abnormal_notified_segments)}→{int(x.abnormal_notified_segments)}/21, "
                                   f"정상 알림 {int(v.normal_notified_segments)}→{int(x.normal_notified_segments)}",
                             source="yejun/press_guard/outputs/ablation_v2.csv"))
    ro = pd.read_csv(GUARD / "outputs" / "rolling.csv")
    ro = ro[np.isclose(ro.alpha, .01)]
    for fold in sorted(ro.split.unique()):
        t = ro[ro.split.eq(fold)].set_index("model")
        same = {"normal_420_479": "B와 같은 모델(보정값 동일)", "normal_480_539": "A와 같은 모델(보정값 동일)"}.get(fold, "동결 모델과 독립")
        rows.append(dict(section="시간순 5겹(α=1%)", item=fold, split="-",
                         value=f"v2 F1 {t.loc['guard_v2', 'f1']:.3f} 대 v1 {t.loc['baseline_v1', 'f1']:.3f}, 정상 알림 "
                               f"{int(t.loc['guard_v2', 'normal_notified_segments'])}·{int(t.loc['baseline_v1', 'normal_notified_segments'])}/60, {same}",
                         source="yejun/press_guard/outputs/rolling.csv"))
    me = pd.read_csv(GUARD / "outputs" / "metrics.csv")
    for sid in ("A", "B"):
        for alpha in ALPHAS:
            t = me[me.split.eq(sid) & np.isclose(me.alpha, alpha)].set_index("model")
            rows.append(dict(section="α 트레이드오프", item=f"α={alpha:g}", split=sid,
                             value=f"v2 F1 {t.loc['guard_v2', 'f1']:.3f}(미탐 {int(t.loc['guard_v2', 'fn'])}, 정상 알림 "
                                   f"{int(t.loc['guard_v2', 'normal_notified_segments'])}) 대 v1 {t.loc['baseline_v1', 'f1']:.3f}"
                                   f"(미탐 {int(t.loc['baseline_v1', 'fn'])}, 정상 알림 {int(t.loc['baseline_v1', 'normal_notified_segments'])})",
                             source="yejun/press_guard/outputs/metrics.csv"))
    return rows


def selection_evidence(ledger, universe, nested, nested_meta, paired_summary, sig):
    rows = []
    before = ledger[ledger.before_v2_selection.eq("예")]
    rows.append(dict(section="탐색 장부", item="같은 이상 21구간에서 본 점수 규칙(단계별 이름 기준, 현재 HEAD)", split="-",
                     value=f"{int(ledger.rules.sum())}개(선정 전 {int(before.rules.sum())}, 선정 후 {int(ledger.rules.sum() - before.rules.sum())})",
                     source="search_ledger.csv"))
    rows.append(dict(section="탐색 장부", item="커밋 dcd300a 시점", split="-",
                     value="63개. 이후 3ad2452(지도학습 v2)가 가중 변형 2개(logistic_balanced·hgb_balanced)를 더해 현재 65개",
                     source="search_ledger.csv, git 기록(커밋 dcd300a의 표)"))
    rows.append(dict(section="탐색 장부", item="이 폴더의 사후 대안(선정에 쓰지 않음)", split="-",
                     value="5NN·IF·합·AR(1)·AR(3)·AR(4)·Fisher·Stouffer·평균·지속성 2종·진폭 조건부 1종·단일 성분 3종 = 15개",
                     source="same_feature_alternatives.csv, combination_rules.csv, fp_mitigation_v2.csv"))
    for sid in ("A", "B"):
        u = universe[universe.split_id.eq(sid)]
        rows.append(dict(section="후보 재계산", item="선정 전 후보 점수 규칙(원래 코드로 재계산)", split=sid,
                         value=f"{len(u)}개, 커밋 표와 일치 {int(u.matches_committed.fillna(False).sum())}/{int(u.matches_committed.notna().sum())}",
                         source="candidate_universe.csv"))
    rows.append(dict(section="후보 재계산", item="서로 다른 경보 패턴(A·B 이상·정상 경보 벡터 기준)", split="-", value=f"{len(sig)}종",
                     source="candidate_universe.csv(alarm_pattern)"))
    lim = nested_meta["v1_limit"]
    rows.append(dict(section="선택 규칙", item="규칙", split="-",
                     value=f"α=1%·matched·conformal. 두 분할 모두 정상 알림 ≤ v1(A {lim['A']}, B {lim['B']}), 학습에 쓴 이상 구간 전부 탐지, "
                           "두 분할 미탐 합 최소(동률: 정상 알림 합, 이름)",
                     source="yejun/analysis/press_advance/protocol.json(selection)"))
    rows.append(dict(section="선택 규칙", item="정상 알림 조건을 통과한 경보 패턴", split="-", value=f"{len(nested_meta['eligible'])}종",
                     source="nested_selection.csv"))
    chosen = nested.chosen.value_counts()
    rows.append(dict(section="중첩 선택", item="이상 기록 1개 빼기 21겹", split="-",
                     value=f"v2 선택 {int(nested.chosen_is_v2.sum())}/21 ({', '.join(f'{k} {v}' for k, v in chosen.items())})",
                     source="nested_selection.csv"))
    rows.append(dict(section="중첩 선택", item="중첩 미탐 합(뺀 기록에서만)", split="-",
                     value=f"A {int(nested.held_out_fn_A.sum())}, B {int(nested.held_out_fn_B.sum())} "
                           f"(외견 v2 A {int(nested.v2_held_out_fn_A.sum())}, B {int(nested.v2_held_out_fn_B.sum())}; 후보 사이 선택의 낙관 편향 "
                           f"{int(nested.held_out_fn_A.sum() - nested.v2_held_out_fn_A.sum() + nested.held_out_fn_B.sum() - nested.v2_held_out_fn_B.sum())}행)",
                     source="nested_selection.csv"))
    for sid in ("A", "B"):
        s = paired_summary[sid]
        rows.append(dict(section="v1 대비 짝 비교", item="기록구간 개선/동일/악화", split=sid, value=f"{s['better']}/{s['equal']}/{s['worse']}",
                         source="paired_records.csv ← yejun/press_guard/outputs/records_first_alarm_v2.csv"))
        rows.append(dict(section="v1 대비 짝 비교", item="부호검정 단측 p(동일 제외)", split=sid, value=f"{s['sign_p']:.2g}", source="paired_records.csv"))
        rows.append(dict(section="v1 대비 짝 비교", item=f"ΔF1 [95% 기록구간 부트스트랩, {BOOT}회, 시드 {SEED}]", split=sid,
                         value=f"+{s['delta_f1']:.3f} [{s['delta_f1_ci'][0]:.3f}, {s['delta_f1_ci'][1]:.3f}]", source="paired_records.csv"))
        rows.append(dict(section="v1 대비 짝 비교", item="미탐 행 v1→v2 (Δ 95% 구간)", split=sid,
                         value=f"{s['fn_v1']}→{s['fn_v2']} ({s['delta_fn_ci'][0]:.0f}~{s['delta_fn_ci'][1]:.0f}행 감소)", source="paired_records.csv"))
    for p in PRECOMMIT:
        rows.append(dict(section="사전 커밋", item=p["stage"], split="-",
                         value=f"프로토콜 {p['protocol_commit']}({p['protocol_date']}) → 결과 {p['result_commit']}({p['result_date']}). {p['status']}",
                         source=f"{p['protocol']} · {p['result']}"))
    rows += tradeoff_rows()
    rows.append(dict(section="한계", item="L1 독립 검증 없음", split="-",
                     value="이상 21구간은 07-17 3분 연속 기록 하나이고 A·B가 공유한다. 정상과 이상은 다른 날이다", source="press_guard/README.md 한계 절, analysis/press_evidence(날짜·수집 조건)"))
    rows.append(dict(section="한계", item="L2 설계의 사후성", split="-",
                     value="초반 창과 AR(2)는 같은 이상 자료에서 v1 미탐을 본 뒤 설계했다. 중첩 선택은 후보 사이의 선택 편향만 잰다",
                     source="press_guard/model.py state['selection']"))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- M5 통합 비교
def supervised_rows(normal, abnormal):
    """press_supervised(커밋 run.py)의 21겹 conformal을 로지스틱·부스팅 × 두 특징으로 다시 돌려 무임계 지표를 더한다."""
    sup = load_module("sel_sup", YEJUN / "analysis" / "press_supervised" / "run.py")
    committed = pd.read_csv(YEJUN / "analysis" / "press_supervised" / "grouped_records.csv")
    rows, checks = [], {}
    seg_a = D.segments(abnormal)
    pos_a = D.segment_positions(seg_a)[0]
    for sid in D.SPLITS:
        parts, v2 = sup.split_data(normal, abnormal, sid)
        seg_cal, seg_test = D.segments(parts["cal"]), D.segments(parts["test"])
        for kind in ("window", "window_plus_v2"):
            Xn, Xc, Xt, Xa = (sup.features(f, kind, v2) for f in (parts["train"], parts["cal"], parts["test"], abnormal))
            for name in ("logistic", "hgb"):
                make = sup.MODELS[name]
                full = make().fit(pd.concat([Xn, Xa], ignore_index=True), np.r_[np.zeros(len(Xn)), np.ones(len(Xa))])
                thr_full = sup.conformal_threshold(full, Xc, seg_cal)
                pn = full.predict_proba(Xt)[:, 1]
                pa, ta = np.full(len(abnormal), np.nan), np.full(len(abnormal), np.nan)
                for k in range(N_ABN):
                    keep = seg_a != k
                    m = make().fit(pd.concat([Xn, Xa[keep]], ignore_index=True), np.r_[np.zeros(len(Xn)), np.ones(keep.sum())])
                    pa[~keep] = m.predict_proba(Xa[~keep])[:, 1]
                    ta[~keep] = sup.conformal_threshold(m, Xc, seg_cal)
                an, aa = pn > thr_full, pa > ta
                tp, fp = int(aa.sum()), int(an.sum())
                fn = len(aa) - tp
                y, s = np.r_[np.zeros(len(pn)), np.ones(len(pa))], np.r_[pn, pa]
                normal_alerted = int(pd.Series(an).groupby(seg_test).any().sum())
                detected = int(pd.Series(aa).groupby(seg_a).any().sum())
                first = pd.Series(np.where(aa, pos_a, np.nan)).groupby(seg_a).min().dropna() * D.DT
                rec = pd.DataFrame(dict(r=np.r_[seg_test, seg_a + 100_000], y=y, s=s)).groupby("r").agg(y=("y", "max"), s=("s", "max"))
                c = committed[committed.split.eq(sid) & committed.features.eq(kind) & committed.model.eq(name)
                              & committed.cv.eq("21fold") & committed.threshold.eq("conformal")].iloc[0]
                checks[f"{sid}_{kind}_{name}"] = bool((tp, fp, fn, normal_alerted, detected)
                                                      == (c.tp, c.fp, c.fn, c.normal_alerted_segments, c.abnormal_detected_segments))
                rows.append(dict(split_id=sid, model=f"지도학습 {name}({'창+v2 성분' if kind == 'window_plus_v2' else '창 특징'})",
                                 family="라벨 지도학습 기준선", protocol="정상 보정 conformal α=1%(보정 기록구간 최대 확률), 이상 21구간 1개 빼기 21겹",
                                 input_condition=("창 특징 22개 + v2 성분(크기·전류 잔차·세 꼬리 점수)" if kind == "window_plus_v2" else "창 특징 22개(센서값·3·8행 평균·표준편차·차분·위치)"),
                                 uses_abnormal_labels="예(20구간으로 학습, 뺀 1구간 예측)", tp=tp, fp=fp, fn=fn,
                                 precision=tp / (tp + fp) if tp + fp else 0.0, recall=tp / len(aa), f1_rows=f1(tp, fp, fn), oracle_f1_rows=oracle_f1(y, s),
                                 row_auroc=float(roc_auc_score(y, s)), row_ap=float(average_precision_score(y, s)),
                                 normal_alerted=normal_alerted, normal_records=int(seg_test.max() + 1), abnormal_detected=detected, abnormal_records=N_ABN,
                                 delay_median_s=round(float(first.median()), 3) if len(first) else np.nan,
                                 delay_max_s=round(float(first.max()), 3) if len(first) else np.nan,
                                 record_f1=f1(detected, normal_alerted, N_ABN - detected), record_auroc=float(roc_auc_score(rec.y, rec.s)),
                                 note="행 확률: 정상 평가는 전체 모델, 이상은 뺀 겹 모델(OOF). 커밋 grouped_records.csv와 건수 일치 확인",
                                 source="yejun/analysis/press_supervised/run.py(커밋 코드 재실행)"))
    return rows, checks


def unified_comparison(ctxs, alternatives, rules, sup_rows):
    rows = []
    gb = json.loads((YEJUN / "press_submission" / "outputs" / "lstm_guidebook_reproduction.json").read_text(encoding="utf-8"))
    rows.append(dict(split_id="가이드북", model="가이드북 LSTM-AE(재현)", family="가이드북 기준선(별도 프로토콜)",
                     protocol="가이드북 프로토콜: 20행 창, 행 15000 분할, 검증 이상 창으로 문턱 선택",
                     input_condition="세 센서 20행 창(기록 공백을 건넘)", uses_abnormal_labels="예(문턱 선택)",
                     tp=gb["tp"], fp=gb["fp"], fn=gb["fn"], precision=gb["precision"], recall=gb["recall"], f1_rows=gb["f1"],
                     normal_alerted=gb["fp"], normal_records=gb["tn"] + gb["fp"],
                     note=f"창 단위 지표(정상 창 {gb['tn'] + gb['fp']}, 이상 창 {gb['tp'] + gb['fn']}). 가이드북 보고치 F1 {gb['guide_reported']['f1']}. "
                          "주 비교와 분모·분할이 달라 직접 비교하지 않는다",
                     source="yejun/press_submission/outputs/lstm_guidebook_reproduction.json"))
    for sid, C in ctxs.items():
        r1, _ = C.evaluate({k: C.v1_score(k) for k in ("cal", "test", "abn")}, .01)
        rows.append(dict(split_id=sid, model="v1 기준선(크기+사인8)", family="베이스라인", protocol="정상 보정 conformal α=1%",
                         input_condition="크기 max|z| + 사인 8행 1−R²(정상 학습 꼬리), fmax", uses_abnormal_labels="아니오", **r1,
                         note="v1 패키지 combined_w8과 같은 경보", source="이 폴더 계산(동결 v2 모델 꼬리) = press_guard/outputs/metrics.csv baseline_v1"))
        alt = alternatives[alternatives.split_id.eq(sid) & np.isclose(alternatives.alpha, .01)].set_index("candidate")
        for name, label in (("5NN(v2 성분)", "5NN(v2 성분)"), ("합(v2 성분)", "합(v2 성분)")):
            a = alt.loc[name]
            rows.append(dict(split_id=sid, model=label, family="같은 특징 대안(사후)", protocol="정상 보정 conformal α=1%",
                             input_condition=a.input_condition, uses_abnormal_labels="아니오",
                             **{k: a[k] for k in METRIC_COLS}, note=POSTHOC, source="same_feature_alternatives.csv"))
        for label, _, _ in SINGLE_COMPONENTS:
            a = alt.loc[label]
            rows.append(dict(split_id=sid, model=label, family="단일 성분(같은 보정 규칙, 사후)", protocol="정상 보정 conformal α=1%",
                             input_condition=a.input_condition, uses_abnormal_labels="아니오",
                             **{k: a[k] for k in METRIC_COLS}, note=ALT_REMARK[label], source="same_feature_alternatives.csv"))
        fi = rules[rules.split_id.eq(sid) & np.isclose(rules.alpha, .01) & rules.rule.eq("fisher")].iloc[0]
        rows.append(dict(split_id=sid, model="Fisher 결합(v2 성분)", family="같은 특징 대안(사후)", protocol="정상 보정 conformal α=1%",
                         input_condition=V2_INPUT, uses_abnormal_labels="아니오", **{k: fi[k] for k in METRIC_COLS},
                         note=POSTHOC + f". 근거 성분 없는 이상 경보 {int(fi.no_evidence_alarms_abnormal)}행", source="combination_rules.csv"))
        rows += [dict(r) for r in sup_rows if r["split_id"] == sid]
        v2 = alt.loc["v2 (fmax, AR(2))"]
        rows.append(dict(split_id=sid, model="v2 최종(fmax)", family="최종 모델", protocol="정상 보정 conformal α=1%",
                         input_condition=V2_INPUT, uses_abnormal_labels="아니오", **{k: v2[k] for k in METRIC_COLS},
                         note="보정 문턱 F1과 사후 최적 F1(평가 라벨로 고른 낙관적 상한)이 거의 같다", source="same_feature_alternatives.csv"))
    out = pd.DataFrame(rows)
    out["input_short"] = [INPUT_SHORT.get(m, "창 특징 + v2 성분" if "v2 성분" in m else "창 특징 22개") for m in out.model]
    return out[[c for c in UNIFIED_COLS if c in out.columns]]


METRIC_COLS = ("tp", "fp", "fn", "precision", "recall", "f1_rows", "oracle_f1_rows", "row_auroc", "row_ap", "normal_alerted", "normal_records",
               "abnormal_detected", "abnormal_records", "delay_median_s", "delay_max_s", "record_f1", "record_auroc")
UNIFIED_COLS = ("split_id", "model", "family", "protocol", "input_short", "input_condition", "uses_abnormal_labels") + METRIC_COLS + ("note", "source")
INPUT_SHORT = {"가이드북 LSTM-AE(재현)": "세 센서 20행 창", "v1 기준선(크기+사인8)": "크기 + 사인8", "5NN(v2 성분)": "v2 세 성분",
               "합(v2 성분)": "v2 세 성분", "Fisher 결합(v2 성분)": "v2 세 성분", "v2 최종(fmax)": "v2 세 성분",
               "크기 단독": "v2 크기 성분", "파형 단독": "v2 파형 성분", "예측 오차(AR(2)) 단독": "v2 예측 오차 성분"}


def unified_markdown(u):
    def num(x, fmt):
        return "—" if pd.isna(x) else format(x, fmt)
    lines = ["# 통합 비교표 (M5) — 자동 생성, 대회 보고서가 아니다", "",
             "`run.py`가 만든다. 주 비교는 정상 보정 conformal α=1%이고 이상 라벨을 쓰지 않는다. 지도학습은 이상 21구간 1개 빼기 21겹이다. "
             "가이드북 LSTM-AE는 분모·분할이 다른 별도 프로토콜이다. 같은 특징 대안은 사후 비교이며 채택 근거가 아니다.", "",
             "| 분할 | 모델 | 입력 조건 | 이상 라벨 | 행 F1 (정밀도/재현율) | 사후 최적 F1 | 행 AUROC / AP | 정상 알림 | 이상 탐지 | 지연 중앙/최대(초) | 기록구간 F1 / AUROC |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in u.itertuples():
        det = "—" if pd.isna(r.abnormal_detected) else f"{int(r.abnormal_detected)}/{int(r.abnormal_records)}"
        lines.append(f"| {r.split_id} | {r.model} | {r.input_short} | {r.uses_abnormal_labels} | {num(r.f1_rows, '.3f')} "
                     f"({num(r.precision, '.3f')}/{num(r.recall, '.3f')}) | {num(r.oracle_f1_rows, '.3f')} | {num(r.row_auroc, '.3f')} / {num(r.row_ap, '.3f')} | "
                     f"{int(r.normal_alerted)}/{int(r.normal_records)} | {det} | {num(r.delay_median_s, '.1f')} / {num(r.delay_max_s, '.1f')} | "
                     f"{num(r.record_f1, '.3f')} / {num(r.record_auroc, '.3f')} |")
    lines += ["", "- 기록구간 AUROC는 v1·v2 모두 1.0이다(구간 단위로는 포화). 구간 단위 차이는 정상 알림 수로만 드러난다.",
              "- 사후 최적 F1은 평가 라벨로 문턱을 고른 낙관적 상한이다. v2의 α=1% F1과 거의 같아 정상 자료만으로 정한 문턱이 거의 최적이다.",
              "- 가이드북 행의 정상 알림은 정상 창 중 경보 창 수다(기록구간이 아님).", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- 실행
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compute(out):
    started = time.monotonic()
    normal, abnormal, report = D.load()
    seg_all = D.segments(normal)
    ctxs = {sid: Context(sid, normal, abnormal, seg_all) for sid in D.SPLITS}
    checks = {}
    committed = pd.read_csv(GUARD / "outputs" / "metrics.csv")
    for sid, C in ctxs.items():
        for alpha in ALPHAS:
            for model, scores in (("guard_v2", {k: C.parts[k]["comp"]["score"] for k in ("cal", "test", "abn")}),
                                  ("baseline_v1", {k: C.v1_score(k) for k in ("cal", "test", "abn")})):
                r, _ = C.evaluate(scores, alpha)
                c = committed[committed.split.eq(sid) & committed.model.eq(model) & np.isclose(committed.alpha, alpha)].iloc[0]
                checks[f"{sid}_{model}_{alpha}_matches_metrics_csv"] = bool(
                    (r["tp"], r["fp"], r["fn"], r["normal_alerted"], r["abnormal_detected"])
                    == (c.tp, c.fp, c.fn, c.normal_notified_segments, c.abnormal_notified_segments))
    print(f"[{time.monotonic() - started:6.1f}s] 문맥·주 수치 대조", flush=True)
    alternatives, ch = same_feature_alternatives(ctxs)
    checks.update(ch)
    rules = combination_rules(ctxs)
    mitigation = fp_mitigation(ctxs)
    injection, rule_transfer, ch = fp_mitigation_injection(ctxs, normal, seg_all)
    checks.update(ch)
    print(f"[{time.monotonic() - started:6.1f}s] M3·O3·E7", flush=True)
    universe, stats_, sig, _ = candidate_universe(normal, abnormal, seg_all)
    nested, nested_meta = nested_selection(stats_, sig)
    paired, paired_summary, ch = paired_records(ctxs)
    checks.update(ch)
    ledger = search_ledger()
    evidence = selection_evidence(ledger, universe, nested, nested_meta, paired_summary, sig)
    checks["universe_matches_committed"] = f"{int(universe.matches_committed.fillna(False).sum())}/{int(universe.matches_committed.notna().sum())}"
    checks["universe_all_match"] = bool(universe.matches_committed.notna().all() and universe.matches_committed.fillna(False).all())
    checks["nested_all_v2"] = bool(nested.chosen_is_v2.all())
    checks["ledger_total_now"] = int(ledger.rules.sum())
    checks["ledger_supervised_models_at_dcd300a"] = ledger_at("dcd300a", "analysis/press_supervised/grouped_records.csv")
    print(f"[{time.monotonic() - started:6.1f}s] M4", flush=True)
    sup_rows, ch = supervised_rows(normal, abnormal)
    checks.update({f"supervised_{k}_matches_committed": v for k, v in ch.items()})
    unified = unified_comparison(ctxs, alternatives, rules, sup_rows)
    print(f"[{time.monotonic() - started:6.1f}s] M5", flush=True)
    tables = {"same_feature_alternatives.csv": alternatives, "combination_rules.csv": rules, "fp_mitigation_v2.csv": mitigation,
              "fp_mitigation_injection_v2.csv": injection, "rule_transfer_injection_v2.csv": rule_transfer,
              "search_ledger.csv": ledger, "candidate_universe.csv": universe, "nested_selection.csv": nested,
              "paired_records.csv": paired, "selection_evidence.csv": evidence, "unified_comparison.csv": unified}
    out.mkdir(parents=True, exist_ok=True)
    for name, t in tables.items():
        t.to_csv(out / name, index=False)
    (out / "unified_comparison.md").write_text(unified_markdown(unified), encoding="utf-8")
    deps = {p: sha(YEJUN / p) for p in ("press_guard/model.py", "press_guard/artifacts/guard_A.json", "press_guard/artifacts/guard_B.json",
                                        "press_guard/outputs/metrics.csv", "press_guard/outputs/records_first_alarm_v2.csv",
                                        "press_guard/outputs/ablation_v2.csv", "press_guard/outputs/rolling.csv",
                                        "press_submission/outputs/model_comparison_all.csv", "press_submission/outputs/sensitivity.csv",
                                        "press_submission/outputs/ablation.csv", "press_submission/outputs/persistence.csv",
                                        "press_submission/outputs/load_normalization.csv", "press_submission/outputs/lstm_guidebook_reproduction.json",
                                        "analysis/press_improvement/candidate_metrics.csv", "analysis/press_improvement/run_experiment.py",
                                        "analysis/press_advance/metrics.csv", "analysis/press_advance/run_experiment.py",
                                        "analysis/press_early/metrics.csv", "analysis/press_early/run_experiment.py",
                                        "analysis/press_supervised/run.py", "analysis/press_supervised/grouped_records.csv",
                                        "analysis/press_supplement/common.py", "press_guard/recalibrate.py", "press_guard/monitor.py")}
    manifest = dict(purpose="평가관 02 M3·M4·M5, 평가관 05 O3, 평가관 03 E7 사후 민감도·선정 근거. 주 모델·문턱·분할 불변",
                    input_sha256={k: v["sha256"] for k, v in report["files"].items()}, code_sha256={"run.py": sha(Path(__file__))},
                    dependencies_sha256=deps, precommit_git_verified=verify_precommit(), checks=checks,
                    random=dict(bootstrap_seed=SEED, bootstrap_reps=BOOT, isolation_forest_random_state=0, supervised="press_supervised MODELS(random_state=0)"),
                    nested_selection=dict(v1_limit=nested_meta["v1_limit"], eligible=nested_meta["eligible"], aliases=nested_meta["aliases"]),
                    outputs={n: sha(out / n) for n in OUTPUTS}, environment=D.environment(), elapsed_s=round(time.monotonic() - started, 1))
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="임시 폴더에 다시 계산해 이 폴더 산출물과 해시 대조")
    args = ap.parse_args()
    if args.check:
        tmp = Path(tempfile.mkdtemp(prefix="press_selection_check_"))
        try:
            manifest = compute(tmp)
            bad = [n for n in OUTPUTS if not (HERE / n).is_file() or sha(HERE / n) != manifest["outputs"][n]]
            failed = [k for k, v in manifest["checks"].items() if v is False]
            print("대조:", "일치" if not bad else f"불일치 {bad}", "/ 내부 점검:", "통과" if not failed else f"실패 {failed}")
            sys.exit(1 if bad or failed else 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    manifest = compute(HERE)
    D.dump_json(manifest, HERE / "manifest.json")
    failed = [k for k, v in manifest["checks"].items() if v is False]
    print("내부 점검:", "통과" if not failed else f"실패 {failed}", "·", manifest["elapsed_s"], "s")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
