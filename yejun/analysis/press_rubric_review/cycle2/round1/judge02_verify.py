"""평가관 02 (cycle2/round1) 직접 검증 — 공식 항목 2. AI 예측모델 개발(40점).

- 커밋 HEAD의 코드를 `git archive`로 시스템 임시 폴더에 풀어 그 코드로만 계산한다(작업 트리의 미커밋 파일 배제).
- 원본: 데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전/ (D.load가 SHA-256·행 수 확인).
- 쓰기: 이 파일 옆 judge02_checks.json 하나. 실행 기록은 호출 측에서 judge02_run.log로 받는다.
- 이 검사는 평가 기록용이다. 여기서 계산한 확률·지도학습·민감도 수치는 팀 결과가 아니며 모델 재선택 근거로 쓰지 않는다.

실행(저장소 루트):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
    yejun/analysis/press_rubric_review/cycle2/round1/judge02_verify.py 2>&1 | tee yejun/analysis/press_rubric_review/cycle2/round1/judge02_run.log
"""
from __future__ import annotations

import io
import importlib.util
import json
import math
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
import pandas as pd
from scipy.stats import binom, mannwhitneyu

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
YEJUN_WT = REPO / "yejun"
DATA_ROOT = REPO / "데이터셋" / "프레스_유압펌프_예지보전"
OUT_JSON = HERE / "judge02_checks.json"
T0 = time.monotonic()
RESULT: dict = {}


def log(*a):
    print(f"[{time.monotonic() - T0:7.1f}s]", *a, flush=True)


def f1(tp, fp, fn):
    d = 2 * tp + fp + fn
    return 2 * tp / d if d else 0.0


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if not math.isfinite(v) else v
    if isinstance(o, float):
        return None if not math.isfinite(o) else o
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


# ---------------------------------------------------------------- 0. 커밋 코드 추출
HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
PATHS = ["yejun/press_guard", "yejun/press_submission", "yejun/analysis/press_advance", "yejun/analysis/press_improvement",
         "yejun/analysis/press_early", "yejun/analysis/press_supplement", "yejun/analysis/press_evidence",
         "yejun/analysis/press_supervised"]
TMP = Path(tempfile.mkdtemp(prefix="judge02_c2r1_"))
tarfile.open(fileobj=io.BytesIO(subprocess.check_output(["git", "archive", "--format=tar", HEAD, *PATHS], cwd=REPO))).extractall(TMP)
Y = TMP / "yejun"
porcelain = subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).splitlines()
RESULT["provenance"] = dict(head=HEAD, code_extracted_to=str(TMP), data_root=str(DATA_ROOT),
                            working_tree_uncommitted=porcelain,
                            note="미커밋 작업 트리 파일은 채점·계산에서 제외했다(커밋 코드만 사용).")
log("HEAD", HEAD, "→", TMP)

sys.path.insert(0, str(Y / "press_guard"))
import model as M  # noqa: E402  (press_submission 경로를 sys.path에 넣는다)
from model import GuardModel, D, ALPHAS  # noqa: E402
import train as T  # noqa: E402
from press.calibrate import conformal_p, segment_max  # noqa: E402
from press.scores import Scorer  # noqa: E402

from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402
from sklearn.neighbors import NearestNeighbors  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


normal, abnormal, report = D.load(DATA_ROOT)
RESULT["provenance"]["input_sha256"] = {k: v["sha256"] for k, v in report["files"].items()}
RESULT["provenance"]["input_sha256_ok"] = all(v["sha256_ok"] and v["rows_ok"] for v in report["files"].values())
SEG_N = D.segments(normal)
SEG_A = D.segments(abnormal)
N_ABN = int(len(np.unique(SEG_A)))
vendor = D.load_vendor()
log("원본 확인", RESULT["provenance"]["input_sha256_ok"], "정상 구간", len(np.unique(SEG_N)), "이상 구간", N_ABN)


def alarm_from(cal_scores, seg_cal, x_scores, alpha=.01):
    p = conformal_p(segment_max(cal_scores, seg_cal), x_scores)
    return np.nan_to_num(p, nan=1.0) <= alpha, p


def per_record(alarm, seg):
    s = pd.DataFrame(dict(r=seg, a=np.asarray(alarm, bool)))
    g = s.groupby("r").a
    return (g.size() - g.sum()).to_numpy(int), g.any().to_numpy(bool)   # FN 행, 탐지 여부


# ---------------------------------------------------------------- 1. 주 수치 재계산(원본에서 재적합)
log("C1 주 수치 재계산")
committed = pd.read_csv(Y / "press_guard/outputs/metrics.csv")
MODELS, SPLIT, PRED = {}, {}, {}
c1 = {}
for sid in D.SPLITS:
    split = D.split_normal(normal, SEG_N, sid)
    m = GuardModel.fit(split["train"], split["cal"], split=sid)
    MODELS[sid], SPLIT[sid] = m, split
    art = YEJUN_WT / "press_guard/artifacts" / f"guard_{sid}.json"
    art_diff = None
    if art.exists():
        a = GuardModel.load(art)
        art_diff = {k: float(np.max(np.abs(np.asarray(getattr(m, k), float) - np.asarray(getattr(a, k), float))))
                    for k in ("mean", "scale", "coef", "cal")}
    seg_cal, seg_test = D.segments(split["cal"]), D.segments(split["test"])
    ref_v1 = segment_max(T.baseline(m, split["cal"]), seg_cal)
    rows = []
    for alpha in ALPHAS:
        pn, pa = m.predict(split["test"], alpha), m.predict(abnormal, alpha)
        tp, fp = int(pa.alarm.sum()), int(pn.alarm.sum())
        fn = len(pa) - tp
        v2 = dict(model="guard_v2", alpha=alpha, tp=tp, fp=fp, fn=fn, f1=f1(tp, fp, fn),
                  normal_notified=int(pn.groupby("record_id").alarm.max().sum()),
                  abnormal_detected=int(pa.groupby("record_id").alarm.max().sum()))
        sn, sa = T.baseline(m, split["test"]), T.baseline(m, abnormal)
        an = np.nan_to_num(conformal_p(ref_v1, sn), nan=1.0) <= alpha
        aa = np.nan_to_num(conformal_p(ref_v1, sa), nan=1.0) <= alpha
        tp1, fp1 = int(aa.sum()), int(an.sum())
        v1 = dict(model="baseline_v1", alpha=alpha, tp=tp1, fp=fp1, fn=len(aa) - tp1, f1=f1(tp1, fp1, len(aa) - tp1),
                  normal_notified=int(pd.Series(an).groupby(seg_test).any().sum()),
                  abnormal_detected=int(pd.Series(aa).groupby(SEG_A).any().sum()))
        for r in (v2, v1):
            c = committed[committed.split.eq(sid) & committed.model.eq(r["model"]) & np.isclose(committed.alpha, alpha)].iloc[0]
            r["matches_committed"] = bool((r["tp"], r["fp"], r["fn"], r["normal_notified"], r["abnormal_detected"]) ==
                                          (c.tp, c.fp, c.fn, c.normal_notified_segments, c.abnormal_notified_segments)
                                          and abs(r["f1"] - c.f1) < 1e-12)
        rows += [v2, v1]
        if alpha == .01:
            PRED[sid] = dict(v2_normal=pn, v2_abn=pa, v1_normal_score=sn, v1_abn_score=sa, v1_normal_alarm=an,
                             v1_abn_alarm=aa, seg_test=seg_test, ref_v1=ref_v1)
    c1[sid] = dict(rows=rows, artifact_max_abs_diff=art_diff)
    log(sid, [(r["model"], r["alpha"], r["tp"], r["fp"], r["fn"], round(r["f1"], 6), r["matches_committed"]) for r in rows if r["alpha"] == .01])
RESULT["C1_headline_recomputed"] = c1

# ---------------------------------------------------------------- 2. 비교표 무결성
log("C2 비교표 무결성")
cmp_ = pd.read_csv(Y / "press_guard/outputs/model_comparison_v2.csv")
sel = cmp_[cmp_.criterion.eq("conformal") & np.isclose(cmp_.alpha, .01) & cmp_.calibration_unit.eq("recording_segments")]
v1all = pd.read_csv(Y / "press_submission/outputs/model_comparison_all.csv")
v1all = v1all[v1all.criterion.eq("conformal") & np.isclose(v1all.alpha, .01) & v1all.calibration_unit.eq("recording_segments")]
adv_m = pd.read_csv(Y / "analysis/press_advance/metrics.csv")
adv_m = adv_m[adv_m.criterion.eq("conformal") & np.isclose(adv_m.alpha, .01) & adv_m.input_variant.eq("matched")]
keys = ["tp", "fp", "fn", "normal_notified_segments", "abnormal_notified_segments", "f1_all_rows"]
c2 = {"models_per_split": sel.groupby("split_id").model.nunique().to_dict(), "rows": [], "source_mismatch": []}
for r in sel.itertuples():
    ok_f1 = abs(f1(r.tp, r.fp, r.fn) - r.f1_all_rows) < 1e-12
    src = v1all if r.source == "v1_package" else adv_m
    s = src[src.split.eq(r.split) & src.model.eq(r.model)]
    same = len(s) == 1 and all(np.isclose(getattr(r, k), s.iloc[0][k]) for k in keys)
    if not same:
        c2["source_mismatch"].append((r.split_id, r.model))
    c2["rows"].append(dict(split=r.split_id, model=r.model, source=r.source, tp=r.tp, fp=r.fp, fn=r.fn,
                           normal_alarm=r.normal_notified_segments, abn_detected=r.abnormal_notified_segments,
                           f1=r.f1_all_rows, ap_scored=r.ap_scored_rows, coverage=r.abnormal_row_coverage,
                           f1_formula_ok=ok_f1, equals_source_table=same))
c2["threshold_free_columns"] = [c for c in cmp_.columns if c.startswith(("ap_", "auroc", "auc", "brier", "log_loss"))]
c2["label_trained_models_in_table"] = sorted(set(sel.model) & {"logistic", "random_forest", "xgboost", "lightgbm", "hgb", "svm_supervised"})
c2["guidebook_lstm_in_main_table"] = bool(sel.model.str.contains("guidebook").any())
gb = json.loads((Y / "press_submission/outputs/lstm_guidebook_reproduction.json").read_text())
c2["guidebook_reproduction"] = dict(f1=gb["f1"], guide_reported_f1=gb["guide_reported"]["f1"], tp=gb["tp"], fp=gb["fp"], fn=gb["fn"],
                                    tn=gb["tn"], note=gb["notes"])
RESULT["C2_comparison_table"] = c2
log("모델 수", c2["models_per_split"], "원표 불일치", c2["source_mismatch"], "무임계 열", c2["threshold_free_columns"])

# ---------------------------------------------------------------- 3. v1 대 v2 짝 비교(기록구간 단위)
log("C3 짝 비교")
rec_committed = pd.read_csv(Y / "press_guard/outputs/records_first_alarm_v2.csv")
rng = np.random.default_rng(20260927)
c3 = {}
for sid in D.SPLITS:
    P = PRED[sid]
    pa = P["v2_abn"]
    fn2, det2 = per_record(pa.alarm.to_numpy(bool), pa.record_id.to_numpy())
    fn1, det1 = per_record(P["v1_abn_alarm"], SEG_A)
    rc = rec_committed[rec_committed.split_id.eq(sid)].sort_values("record_id")
    better, worse = int((fn2 < fn1).sum()), int((fn2 > fn1).sum())
    sign_p = float(binom.sf(better - 1, better + worse, .5)) if better + worse else 1.0
    rows_per = pa.groupby("record_id").size().to_numpy()
    fp2, fp1 = int(P["v2_normal"].alarm.sum()), int(P["v1_normal_alarm"].sum())
    boots_dfn, boots_df1 = [], []
    for _ in range(10000):
        idx = rng.integers(0, len(fn1), len(fn1))
        n_rows = rows_per[idx].sum()
        a1, a2 = fn1[idx].sum(), fn2[idx].sum()
        boots_dfn.append(a1 - a2)
        boots_df1.append(f1(n_rows - a2, fp2, a2) - f1(n_rows - a1, fp1, a1))
    nn2 = P["v2_normal"].groupby("record_id").alarm.max().to_numpy(bool)
    nn1 = pd.Series(P["v1_normal_alarm"]).groupby(P["seg_test"]).any().to_numpy(bool)
    c3[sid] = dict(fn_v1=int(fn1.sum()), fn_v2=int(fn2.sum()), segments_v2_better=better, segments_equal=int((fn2 == fn1).sum()),
                   segments_v2_worse=worse, sign_test_one_sided_p=sign_p,
                   delta_fn_boot95=[float(np.percentile(boots_dfn, 2.5)), float(np.percentile(boots_dfn, 97.5))],
                   delta_f1_observed=f1(600 - fn2.sum(), fp2, fn2.sum()) - f1(600 - fn1.sum(), fp1, fn1.sum()),
                   delta_f1_boot95=[float(np.percentile(boots_df1, 2.5)), float(np.percentile(boots_df1, 97.5))],
                   normal_alarm_segments_v1_only=int((nn1 & ~nn2).sum()), normal_alarm_segments_v2_only=int((nn2 & ~nn1).sum()),
                   normal_alarm_segments_both=int((nn1 & nn2).sum()),
                   matches_committed_records=bool(np.array_equal(rc.v1_fn_rows.to_numpy(), fn1) and np.array_equal(rc.v2_fn_rows.to_numpy(), fn2)))
    log(sid, c3[sid])
RESULT["C3_paired_v1_v2"] = c3

# ---------------------------------------------------------------- 4. 선택 인지(중첩) 평가: 팀이 같은 이상 21구간에서 본 후보 전체
log("C4 후보 전체 재계산·중첩 선택")
adv = load_module("j02_adv", Y / "analysis/press_advance/run_experiment.py")
imp = load_module("j02_imp", Y / "analysis/press_improvement/run_experiment.py")
ear = load_module("j02_ear", Y / "analysis/press_early/run_experiment.py")
WINS = (5, 6, 8, 10, 12, 15, 20)
UNIVERSE, SEGS = {}, {}
for sid in D.SPLITS:
    split = SPLIT[sid]
    tr = D.quantize(split["train"], "matched")
    seg_tr = D.segments(tr)
    frames = dict(cal=D.quantize(split["cal"], "matched"), test=D.quantize(split["test"], "matched"), abn=D.quantize(abnormal, "matched"))
    segs = {k: D.segments(f) for k, f in frames.items()}
    SEGS[sid] = segs
    u = {}
    sc = Scorer(tr, seg_tr, vendor, wins=WINS, baselines=True)
    per = {k: sc.score(frames[k], segs[k])[0] for k in frames}
    for name in per["cal"]:
        u[f"v1pkg:{name}"] = {k: per[k][name] for k in frames}
    cs = imp.CandidateScorer(tr, seg_tr, vendor)
    per = {k: cs.score(frames[k], segs[k]) for k in frames}
    for name in per["cal"]:
        u[f"improve:{name}"] = {k: per[k][name] for k in frames}
    base = Scorer(tr, seg_tr, vendor, wins=(6, 8), baselines=False)
    dyn = adv.Dynamics(tr, seg_tr)
    per = {k: adv.scores(base, dyn, frames[k], segs[k]) for k in frames}
    for name in per["cal"]:
        u[f"advance:{name}"] = {k: per[k][name] for k in frames}
    ar2, ar1, joint = ear.Linear(tr, seg_tr, 2), ear.Linear(tr, seg_tr, 1), ear.Joint(base.scaler, tr)
    per = {k: ear.scores(base, ar2, joint, ar1, frames[k], segs[k]) for k in frames}
    for name in per["cal"]:
        u[f"early:{name}"] = {k: per[k][name] for k in frames}
    UNIVERSE[sid] = u
    log(sid, "후보 점수", len(u))

STATS = {}
for sid in D.SPLITS:
    segs = SEGS[sid]
    for name, s in UNIVERSE[sid].items():
        an, _ = alarm_from(s["cal"], segs["cal"], s["test"])
        aa, _ = alarm_from(s["cal"], segs["cal"], s["abn"])
        fnr, det = per_record(aa, segs["abn"])
        STATS[(sid, name)] = dict(normal_alarm=int(pd.Series(an).groupby(segs["test"]).any().sum()), fp=int(an.sum()),
                                  fn_by_rec=fnr, det_by_rec=det, alarm_abn=aa, alarm_test=an)

# 커밋된 후보 표와 대조
ref_tables = {
    "v1pkg": pd.concat([v1all.assign(k=v1all.model),
                        (lambda s: s[s.criterion.eq("conformal") & np.isclose(s.alpha, .01) & s.preprocess.eq("matched")].assign(k=lambda d: d.model))(
                            pd.read_csv(Y / "press_submission/outputs/sensitivity.csv"))]),
    "improve": (lambda s: s[s.criterion.eq("conformal") & np.isclose(s.alpha, .01) & s.eval_preprocess.eq("matched")].assign(k=lambda d: d.model))(
        pd.read_csv(Y / "analysis/press_improvement/candidate_metrics.csv")),
    "advance": adv_m.assign(k=adv_m.model),
    "early": (lambda s: s[s.criterion.eq("conformal") & np.isclose(s.alpha, .01) & s.input_variant.eq("matched")].assign(k=lambda d: d.model))(
        pd.read_csv(Y / "analysis/press_early/metrics.csv")),
}
split_name = {sid: D.SPLITS[sid][0] for sid in D.SPLITS}
recon = []
for (sid, name), st in STATS.items():
    fam, model_name = name.split(":", 1)
    t = ref_tables[fam]
    t = t[t.split.eq(split_name[sid]) & t.k.eq(model_name)]
    if not len(t):
        recon.append(dict(split=sid, candidate=name, committed=None))
        continue
    c = t.iloc[0]
    fn = int(st["fn_by_rec"].sum())
    recon.append(dict(split=sid, candidate=name, committed=True,
                      match=bool(fn == c.fn and st["normal_alarm"] == c.normal_notified_segments and st["fp"] == c.fp),
                      fn=fn, committed_fn=int(c.fn), normal_alarm=st["normal_alarm"], committed_normal_alarm=int(c.normal_notified_segments)))
recon_df = pd.DataFrame(recon)
matched_names = set(recon_df[recon_df.committed.eq(True) & recon_df["match"].eq(True)].candidate)
mismatch = recon_df[recon_df.committed.eq(True) & ~recon_df["match"].fillna(False).astype(bool)]
log("후보 재계산 대조: 일치", len(recon_df[recon_df["match"].eq(True)]), "불일치", len(mismatch), "표 없음", int(recon_df.committed.isna().sum()))

# 동일 경보 벡터 후보는 하나로 합친다
names = sorted({n for (_, n) in STATS})
sig = {}
for n in names:
    key = tuple(np.r_[STATS[("A", n)]["alarm_abn"], STATS[("A", n)]["alarm_test"], STATS[("B", n)]["alarm_abn"], STATS[("B", n)]["alarm_test"]].astype(int).tobytes() for _ in [0])
    sig.setdefault(key, []).append(n)
unique = [v[0] for v in sig.values()]
aliases = {v[0]: v[1:] for v in sig.values() if len(v) > 1}
BASE_NAME = "advance:baseline_w8"
V2_NAME = "advance:early6_ar2"
base_rep = next(u for u in unique if u == BASE_NAME or BASE_NAME in aliases.get(u, []))
v2_rep = next(u for u in unique if u == V2_NAME or V2_NAME in aliases.get(u, []))
nA, nB = STATS[("A", base_rep)]["normal_alarm"], STATS[("B", base_rep)]["normal_alarm"]
eligible_normal = [u for u in unique if STATS[("A", u)]["normal_alarm"] <= nA and STATS[("B", u)]["normal_alarm"] <= nB]
chosen, held_fn = [], {"A": 0, "B": 0}
for j in range(N_ABN):
    keep = np.arange(N_ABN) != j
    best = None
    for u in eligible_normal:
        if not all(STATS[(s, u)]["det_by_rec"][keep].all() for s in "AB"):
            continue
        key = (sum(int(STATS[(s, u)]["fn_by_rec"][keep].sum()) for s in "AB"),
               STATS[("A", u)]["normal_alarm"] + STATS[("B", u)]["normal_alarm"], u)
        best = key if best is None or key < best else best
    chosen.append(best[2])
    for s in "AB":
        held_fn[s] += int(STATS[(s, best[2])]["fn_by_rec"][j])
apparent = {s: int(STATS[(s, v2_rep)]["fn_by_rec"].sum()) for s in "AB"}
ranking = sorted(((sum(int(STATS[(s, u)]["fn_by_rec"].sum()) for s in "AB"), u,
                   STATS[("A", u)]["normal_alarm"], STATS[("B", u)]["normal_alarm"],
                   int(STATS[("A", u)]["det_by_rec"].sum()), int(STATS[("B", u)]["det_by_rec"].sum())) for u in unique))
RESULT["C4_selection_aware"] = dict(
    candidates_scored=len(names), unique_alarm_patterns=len(unique), aliases=aliases,
    recomputed_vs_committed=dict(matched=int(recon_df["match"].eq(True).sum()), mismatched=mismatch.to_dict("records"),
                                 no_committed_row=recon_df[recon_df.committed.isna()].candidate.tolist()),
    rule="α=1%·matched·conformal. 두 분할 모두 정상 알림 ≤ v1(baseline_w8) 그리고 학습 이상 20구간 모두 탐지 → 두 분할 FN 합 최소(동률: 정상 알림 합, 이름)",
    eligible_by_normal_rule=eligible_normal, v1_normal_alarm=dict(A=nA, B=nB),
    nested_loso_fn=held_fn, apparent_v2_fn=apparent, chosen_counts=pd.Series(chosen).value_counts().to_dict(),
    ranking_total_fn=[dict(total_fn=r[0], candidate=r[1], normal_A=r[2], normal_B=r[3], detA=r[4], detB=r[5]) for r in ranking[:12]])
log("중첩 FN", held_fn, "외견 FN", apparent, "선택", pd.Series(chosen).value_counts().to_dict())

# ---------------------------------------------------------------- 5. 탐색 규모(같은 이상 21구간에서 본 점수 규칙 수)
def uniq(path, col="model", filt=None):
    t = pd.read_csv(path)
    if filt is not None:
        t = filt(t)
    return sorted(t[col].unique().tolist())


ledger = dict(
    v1_comparison=uniq(Y / "press_submission/outputs/model_comparison_all.csv"),
    v1_sensitivity=uniq(Y / "press_submission/outputs/sensitivity.csv"),
    v1_ablation=uniq(Y / "press_submission/outputs/ablation.csv", "ablation"),
    v1_persistence=uniq(Y / "press_submission/outputs/persistence.csv"),
    v1_load_normalization=uniq(Y / "press_submission/outputs/load_normalization.csv"),
    improvement=uniq(Y / "analysis/press_improvement/candidate_metrics.csv"),
    advance=uniq(Y / "analysis/press_advance/metrics.csv"),
    early=uniq(Y / "analysis/press_early/metrics.csv"),
    v2_ablation=uniq(Y / "press_guard/outputs/ablation_v2.csv"),
    supervised_baseline=uniq(Y / "analysis/press_supervised/grouped_records.csv"),
    guidebook_lstm=["guidebook_lstm_ae"])
flat = set()
for k, v in ledger.items():
    flat |= {f"{k}:{x}" for x in v}
RESULT["C5_search_ledger"] = dict(by_stage=ledger, stage_model_entries=len(flat),
                                  note="단계별 이름 기준 개수(중복 규칙 포함). 모두 같은 이상 21구간에서 평가됐다.")
git_dates = {}
for p in ["yejun/analysis/press_advance/protocol.json", "yejun/analysis/press_advance/metrics.csv",
          "yejun/analysis/press_improvement/config.json", "yejun/analysis/press_improvement/candidate_metrics.csv",
          "yejun/analysis/press_early/protocol.json", "yejun/analysis/press_early/metrics.csv",
          "yejun/analysis/press_supplement/protocol.json", "yejun/analysis/press_supplement/e1_summary.csv"]:
    git_dates[p] = subprocess.check_output(["git", "log", "--diff-filter=A", "--format=%h %ad", "--date=iso", "--", p], cwd=REPO, text=True).strip()
RESULT["C5_search_ledger"]["first_commit_of_protocol_vs_result"] = git_dates
log("탐색 규모", len(flat))

# ---------------------------------------------------------------- 6. 무임계 지표(행·기록구간)
log("C6 무임계 지표")
c6 = {}
for sid in D.SPLITS:
    P = PRED[sid]
    y = np.r_[np.zeros(len(P["v2_normal"])), np.ones(len(P["v2_abn"]))]
    s2 = np.r_[P["v2_normal"].score.to_numpy(), P["v2_abn"].score.to_numpy()]
    s1 = np.r_[P["v1_normal_score"], P["v1_abn_score"]]
    lo = np.nanmin(np.r_[s1, s2]) - 1
    s1f, s2f = np.where(np.isfinite(s1), s1, lo), np.where(np.isfinite(s2), s2, lo)
    rec = np.r_[P["seg_test"], SEG_A + 10_000]
    seg_df = pd.DataFrame(dict(r=rec, y=y, s1=s1f, s2=s2f)).groupby("r").agg(y=("y", "max"), s1=("s1", "max"), s2=("s2", "max"))
    best_v2 = 0.0
    for t in np.unique(s2f):
        al = s2f >= t
        best_v2 = max(best_v2, f1(int((al & (y == 1)).sum()), int((al & (y == 0)).sum()), int((~al & (y == 1)).sum())))
    c6[sid] = dict(v2_oracle_threshold_f1=best_v2, row_auroc_v2=roc_auc_score(y, s2f), row_auroc_v1=roc_auc_score(y, s1f),
                   row_ap_v2=average_precision_score(y, s2f), row_ap_v1=average_precision_score(y, s1f),
                   record_auroc_v2=roc_auc_score(seg_df.y, seg_df.s2), record_auroc_v1=roc_auc_score(seg_df.y, seg_df.s1),
                   v2_all_rows_scored=bool(np.isfinite(s2).all()), v1_unscored_rows=int((~np.isfinite(s1)).sum()))
    log(sid, {k: (round(v, 6) if isinstance(v, float) else v) for k, v in c6[sid].items()})
RESULT["C6_threshold_free"] = c6

# ---------------------------------------------------------------- 7. '이상 확률' 구현 가능성 점검(평가관 계산, 팀 결과 아님)
log("C7 확률 출력 가능성")


def fold_ids(rec_normal, rec_abn, k):
    """이상 기록구간 하나씩 + 정상 평가 기록구간을 시간순 k덩어리로 나눈 묶음 교차검증 폴드."""
    un = np.unique(rec_normal)
    blocks = np.array_split(un, k)
    fn_ = np.empty(len(rec_normal), int)
    for i, b in enumerate(blocks):
        fn_[np.isin(rec_normal, b)] = i
    ua = np.unique(rec_abn)
    fa = np.searchsorted(ua, rec_abn)
    return np.r_[fn_, fa]


def ece(y, p, bins=10):
    e, edges = 0.0, np.linspace(0, 1, bins + 1)
    for lo_, hi in zip(edges[:-1], edges[1:]):
        m_ = (p >= lo_) & (p < hi) if hi < 1 else (p >= lo_) & (p <= hi)
        if m_.any():
            e += m_.mean() * abs(y[m_].mean() - p[m_].mean())
    return e


def prior_shift(p, pi_data, pi_site):
    p = min(max(p, 1e-9), 1 - 1e-9)
    lr = (p / (1 - p)) / (pi_data / (1 - pi_data))
    o = lr * pi_site / (1 - pi_site)
    return o / (1 + o)


c7 = {}
for sid in D.SPLITS:
    P = PRED[sid]
    rn, ra = P["v2_normal"].record_id.to_numpy(), P["v2_abn"].record_id.to_numpy()
    y = np.r_[np.zeros(len(rn)), np.ones(len(ra))]
    s = np.r_[P["v2_normal"].score.to_numpy(), P["v2_abn"].score.to_numpy()]
    folds = fold_ids(rn, ra, N_ABN)
    oof = {"platt": np.zeros(len(y)), "isotonic": np.zeros(len(y))}
    for f in range(N_ABN):
        te, trn = folds == f, folds != f
        te_ = te & ((np.arange(len(y)) < len(rn)) | True)
        lr_ = LogisticRegression(C=1e3, max_iter=5000).fit(s[trn, None], y[trn])
        oof["platt"][te] = lr_.predict_proba(s[te, None])[:, 1]
        iso = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(s[trn], y[trn])
        oof["isotonic"][te] = iso.predict(s[te])
    pi = y.mean()
    out = dict(prevalence_rows=pi, brier_prevalence_only=pi * (1 - pi))
    for k, p_ in oof.items():
        pc = np.clip(p_, 1e-6, 1 - 1e-6)
        out[k] = dict(brier=brier_score_loss(y, pc), log_loss=log_loss(y, pc), ece10=ece(y, pc), auroc=roc_auc_score(y, pc),
                      mean_p_normal=float(pc[y == 0].mean()), mean_p_abnormal=float(pc[y == 1].mean()),
                      share_abnormal_rows_p_ge_0_5=float((pc[y == 1] >= .5).mean()), share_normal_rows_p_ge_0_5=float((pc[y == 0] >= .5).mean()))
    # 기록구간(최대 점수) 단위
    rec = np.r_[rn, ra + 10_000]
    g = pd.DataFrame(dict(r=rec, y=y, s=s, f=folds)).groupby("r").agg(y=("y", "max"), s=("s", "max"), f=("f", "first"))
    p_rec = np.zeros(len(g))
    for f in range(N_ABN):
        te, trn = (g.f == f).to_numpy(), (g.f != f).to_numpy()
        p_rec[te] = LogisticRegression(C=1e3, max_iter=5000).fit(g.s.to_numpy()[trn, None], g.y.to_numpy()[trn]).predict_proba(g.s.to_numpy()[te, None])[:, 1]
    pr = np.clip(p_rec, 1e-6, 1 - 1e-6)
    out["record_platt"] = dict(n_records=len(g), prevalence=float(g.y.mean()), brier=brier_score_loss(g.y, pr), log_loss=log_loss(g.y, pr),
                               brier_prevalence_only=float(g.y.mean() * (1 - g.y.mean())))
    # 문턱 근처 점수에서의 확률과 현장 사전확률 이동(전체 적합 Platt)
    full = LogisticRegression(C=1e3, max_iter=5000).fit(s[:, None], y)
    thr = float(np.sort(MODELS[sid].cal)[::-1][0])
    at = {"threshold(보정 최대)": thr, "abnormal_median": float(np.median(s[y == 1])), "normal_q99": float(np.quantile(s[y == 0], .99))}
    out["shift_table"] = {name: {f"pi_site={ps}": prior_shift(float(full.predict_proba([[v]])[0, 1]), pi, ps) for ps in (1e-3, 1e-2, .034, .1)}
                          | {"p_data": float(full.predict_proba([[v]])[0, 1]), "score": v} for name, v in at.items()}
    c7[sid] = out
    log(sid, "platt", {k: round(v, 5) for k, v in out["platt"].items()}, "isotonic brier", round(out["isotonic"]["brier"], 5))
# 라벨 없이 p값만으로 가능한 상한(Sellke–Bayarri–Berger 최소 베이즈 인수)
sbb = {}
for pv in (1 / 121, 3 / 121, 6 / 121):
    bmin = -math.e * pv * math.log(pv)
    sbb[f"p={pv:.5f}"] = {f"pi={pi_}": 1 / (1 + (1 - pi_) / pi_ * bmin) for pi_ in (1e-3, 1e-2, .034, .1, .5)} | {"min_bayes_factor_H0": bmin}
c7["label_free_upper_bound_SBB"] = sbb
RESULT["C7_probability_feasibility"] = c7

# ---------------------------------------------------------------- 8. 라벨 지도학습 기준선 점검(평가관 계산, 팀 결과 아님)
log("C8 지도학습 기준선 점검")


def features(frame, m):
    x = D.quantize(D.inputs_only(frame), "matched")
    seg = D.segments(x)
    v = x[D.SENSORS].to_numpy(float)
    z = (v - m.mean) / m.scale
    df = pd.DataFrame(z, columns=["z0", "z1", "z2"])
    df["absmax"] = np.abs(z).max(1)
    for k in range(3):
        s_ = pd.Series(z[:, k])
        df[f"std8_{k}"] = s_.groupby(seg).transform(lambda q: q.rolling(8, min_periods=2).std()).to_numpy()
        df[f"mean8_{k}"] = s_.groupby(seg).transform(lambda q: q.rolling(8, min_periods=1).mean()).to_numpy()
    df["sine6"] = M.sine_score(v[:, 2], seg, 6)
    df["sine8"] = M.sine_score(v[:, 2], seg, 8)
    df["ar2"] = M.ar_residual(x, seg, m.coef) / m.scale[2]
    for k in (0, 1):
        prev = pd.Series(z[:, k]).groupby(seg).shift(1).to_numpy()
        df[f"lag1prod_{k}"] = z[:, k] * prev
    df["dcur"] = np.abs(pd.Series(z[:, 2]).groupby(seg).diff().to_numpy())
    return df.to_numpy(float), seg


def format_features(which):
    path = D.data_dir(DATA_ROOT) / D.FILES[which]
    raw = pd.read_csv(path, dtype=str)
    dec = lambda s: s.str.split(".").str[1].str.len().fillna(0).astype(float)  # noqa: E731
    cur = raw[D.SENSORS[2]].astype(float)
    q = cur / 1.1920929
    return np.column_stack([dec(raw[D.SENSORS[0]]), dec(raw[D.SENSORS[1]]), np.abs(q - np.round(q))])


def make_clf(kind):
    if kind == "logistic":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced", max_iter=5000))
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=.1, class_weight="balanced", random_state=0)


c8 = {}
FEAT = {}
for sid in D.SPLITS:
    m = MODELS[sid]
    Xn, segn = features(normal, m)
    Xa, sega = features(abnormal, m)
    FEAT[sid] = (Xn, Xa)
    _, tr_end, cal_end = D.SPLITS[sid]
    itr, ical, ite = SEG_N < tr_end, (SEG_N >= tr_end) & (SEG_N < cal_end), SEG_N >= cal_end
    res = {}
    for feat_name, (Fn, Fa) in {"signal_matched": (Xn, Xa), "format_only": (format_features("normal"), format_features("abnormal"))}.items():
        for kind in ("logistic", "hgb"):
            if feat_name == "format_only" and kind == "logistic":
                continue
            fn_conf, fn_half, normal_alarm_conf, normal_alarm_half = 0, 0, [], []
            for j in range(N_ABN):
                ka = sega != j
                X = np.r_[Fn[itr], Fa[ka]]
                yv = np.r_[np.zeros(itr.sum()), np.ones(ka.sum())]
                clf = make_clf(kind).fit(X, yv)
                p_cal = clf.predict_proba(Fn[ical])[:, 1]
                p_te = clf.predict_proba(Fn[ite])[:, 1]
                p_j = clf.predict_proba(Fa[~ka])[:, 1]
                ref = segment_max(p_cal, SEG_N[ical])
                al_j = np.nan_to_num(conformal_p(ref, p_j), nan=1) <= .01
                al_te = np.nan_to_num(conformal_p(ref, p_te), nan=1) <= .01
                fn_conf += int((~al_j).sum())
                fn_half += int((p_j < .5).sum())
                normal_alarm_conf.append(int(pd.Series(al_te).groupby(SEG_N[ite]).any().sum()))
                normal_alarm_half.append(int(pd.Series(p_te >= .5).groupby(SEG_N[ite]).any().sum()))
            # 전체 행 F1: 정상 평가 알림은 폴드 중앙값 모델의 행 수로 근사하지 않고, 이상 21구간 모두로 학습한 모델로 계산
            clf = make_clf(kind).fit(np.r_[Fn[itr], Fa], np.r_[np.zeros(itr.sum()), np.ones(len(Fa))])
            p_cal, p_te = clf.predict_proba(Fn[ical])[:, 1], clf.predict_proba(Fn[ite])[:, 1]
            ref = segment_max(p_cal, SEG_N[ical])
            al_te = np.nan_to_num(conformal_p(ref, p_te), nan=1) <= .01
            fp_conf, fp_half = int(al_te.sum()), int((p_te >= .5).sum())
            res[f"{feat_name}:{kind}"] = dict(
                loso_fn_conformal=fn_conf, loso_fn_half=fn_half,
                f1_conformal=f1(600 - fn_conf, fp_conf, fn_conf), f1_half=f1(600 - fn_half, fp_half, fn_half),
                normal_alarm_conformal_all21=int(pd.Series(al_te).groupby(SEG_N[ite]).any().sum()),
                normal_alarm_half_all21=int(pd.Series(p_te >= .5).groupby(SEG_N[ite]).any().sum()),
                normal_alarm_conformal_fold_range=[min(normal_alarm_conf), max(normal_alarm_conf)],
                fp_rows_conformal=fp_conf, fp_rows_half=fp_half)
            if feat_name == "signal_matched":
                FEAT[(sid, kind)] = (clf, ref)
            log(sid, feat_name, kind, res[f"{feat_name}:{kind}"])
    # 무작위 행 분할(흔한 실수): 기록구간을 무시한 5겹 층화
    Xall = np.r_[Xn, Xa]
    yall = np.r_[np.zeros(len(Xn)), np.ones(len(Xa))]
    pred = np.zeros(len(yall))
    for trn, te in StratifiedKFold(5, shuffle=True, random_state=0).split(Xall, yall):
        pred[te] = make_clf("hgb").fit(Xall[trn], yall[trn]).predict_proba(Xall[te])[:, 1]
    tp_, fp_, fn_ = int(((pred >= .5) & (yall == 1)).sum()), int(((pred >= .5) & (yall == 0)).sum()), int(((pred < .5) & (yall == 1)).sum())
    res["random_row_5fold_hgb"] = dict(tp=tp_, fp=fp_, fn=fn_, f1=f1(tp_, fp_, fn_))
    c8[sid] = res
    log(sid, "random rows", res["random_row_5fold_hgb"])

# E1과 같은 방식의 주입(같은 날 정상 평가 기록, t0=10, 계단형)에 대한 전이
sup = load_module("j02_common", Y / "analysis/press_supplement/common.py")
committed_e1 = pd.read_csv(Y / "analysis/press_supplement/e1_summary.csv")
CONDS = [("none", 0.0), ("cur_noise", 0.1), ("cur_noise", 0.2), ("cur_noise", 0.4), ("cur_offset", 0.4), ("cur_offset", 0.8),
         ("vib_noise", 2.0), ("vib_noise", 4.0), ("cur_gain", 1.5), ("cur_gain", 0.5)]
zs = [sup.standard_noise(len(normal), rep) for rep in range(5)]
e1 = {}
for sid in D.SPLITS:
    m = MODELS[sid]
    rows_ = sup.split_rows(normal, sid)
    test = D.inputs_only(normal.iloc[rows_["test"]])
    seg = D.segments(test)
    pos, length = D.segment_positions(seg)
    eligible = np.unique(seg[length >= 30])
    mask = np.isin(seg, eligible) & (pos >= 10)
    ramp = np.ones(len(pos))
    out = []
    for fam, lv in CONDS:
        reps = range(5) if fam in ("vib_noise", "cur_noise") else range(1)
        rates = {"guard_v2": [], "sup_logistic": [], "sup_hgb": []}
        for rep in reps:
            frame = sup.inject(test, rows_["test"], m, fam, lv, mask, ramp, zs[rep])
            p2 = m.predict(frame, .01).p_value.to_numpy()
            rates["guard_v2"].append(sup.record_detection(p2, seg, pos, eligible, 10, .01))
            Xf, _ = features(frame, m)
            for kind in ("logistic", "hgb"):
                clf, ref = FEAT[(sid, kind)]
                pc = conformal_p(ref, clf.predict_proba(Xf)[:, 1])
                rates[f"sup_{kind}"].append(sup.record_detection(pc, seg, pos, eligible, 10, .01))
        row = dict(family=fam, level=lv, records=int(len(eligible)))
        for k, v in rates.items():
            d = pd.concat(v)
            row[f"{k}_detect_2s"] = float(d.detected_2s.mean())
            row[f"{k}_pre_alarm_records_rep0"] = int(v[0].pre_alarm.sum())
        ce = committed_e1[committed_e1.split.eq(sid) & committed_e1.family.eq(fam) & np.isclose(committed_e1.level, lv) &
                          committed_e1["shape"].eq("step") & committed_e1.t0.eq(10) & committed_e1.model.eq("guard_v2") &
                          np.isclose(committed_e1.alpha, .01)]
        row["guard_v2_committed_detect_2s"] = float(ce.detect_rate_2s.iloc[0]) if len(ce) else None
        out.append(row)
        log(sid, fam, lv, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items() if "detect" in k})
    e1[sid] = out
RESULT["C8_supervised_baseline_check"] = dict(results=c8, e1_transfer=e1, notes=[
    "평가관 계산. 특징은 v2와 같은 인과 창 특징(표준화 값·8행 이동 표준편차/평균·사인 1−R²·AR(2) 잔차·lag-1 곱·전류 차분), matched 양자화.",
    "LOSO: 이상 기록구간 하나를 빼고 정상 학습+나머지 20구간으로 학습, 문턱은 v2와 같은 정상 보정 구간 최대 점수 conformal α=1%(또는 0.5).",
    "format_only: 원문 소수 자릿수·전류 격자 잔차 3개만 쓴 분류기(지름길 시연).",
    "e1_transfer: 이상 21구간 전부로 학습한 분류기를 E1과 같은 주입 자료에 적용(주입 전 행 경보 포함)."])

# ---------------------------------------------------------------- 9. 선택 설계의 이웃 민감도(평가관 계산, 재선택 근거 아님)
log("C9 이웃 설계 민감도")
c9 = {}
for sid in D.SPLITS:
    split = SPLIT[sid]
    tr = D.quantize(split["train"], "matched")
    seg_tr = D.segments(tr)
    segs = SEGS[sid]
    frames = dict(cal=D.quantize(split["cal"], "matched"), test=D.quantize(split["test"], "matched"), abn=D.quantize(abnormal, "matched"))
    base = Scorer(tr, seg_tr, vendor, wins=(6, 8), baselines=False)
    cand = {}
    comps = {}
    for k in frames:
        comp, _ = base.components(frames[k], segs[k])
        pos, _ = D.segment_positions(segs[k])
        comps[k] = (comp["g_maxz3"], np.where(pos < 7, comp["g_sine_6"], comp["g_sine_8"]))
    for order in (1, 2, 3, 4):
        lin = ear.Linear(tr, seg_tr, order)
        cand[f"early+AR({order})"] = {k: np.fmax(np.fmax(*comps[k]), lin.tail(lin.residual(frames[k], segs[k]))) for k in frames}
    lin2 = ear.Linear(tr, seg_tr, 2)
    gdyn = {k: lin2.tail(lin2.residual(frames[k], segs[k])) for k in frames}
    mats = {k: np.nan_to_num(np.column_stack([comps[k][0], comps[k][1], gdyn[k]]), nan=0.0) for k in frames}
    cand["sum_of_components"] = {k: mats[k].sum(1) for k in frames}
    trm = {}
    comp_tr, _ = base.components(tr, seg_tr)
    pos_tr, _ = D.segment_positions(seg_tr)
    trm = np.nan_to_num(np.column_stack([comp_tr["g_maxz3"], np.where(pos_tr < 7, comp_tr["g_sine_6"], comp_tr["g_sine_8"]),
                                         lin2.tail(lin2.residual(tr, seg_tr))]), nan=0.0)
    iso = IsolationForest(random_state=0).fit(trm)
    cand["isolation_forest_on_v2_components"] = {k: -iso.score_samples(mats[k]) for k in frames}
    nn5 = NearestNeighbors(n_neighbors=5).fit(trm)
    cand["5nn_on_v2_components"] = {k: nn5.kneighbors(mats[k])[0].mean(1) for k in frames}
    rows = []
    for name, s in cand.items():
        an, _ = alarm_from(s["cal"], segs["cal"], s["test"])
        aa, _ = alarm_from(s["cal"], segs["cal"], s["abn"])
        fnr, det = per_record(aa, segs["abn"])
        tp_, fp_ = int(aa.sum()), int(an.sum())
        rows.append(dict(candidate=name, normal_alarm=int(pd.Series(an).groupby(segs["test"]).any().sum()), fp=fp_,
                         fn=int(fnr.sum()), detected=int(det.sum()), f1=f1(tp_, fp_, len(aa) - tp_)))
    c9[sid] = rows
    log(sid, [(r["candidate"], r["normal_alarm"], r["fn"], r["detected"], round(r["f1"], 4)) for r in rows])
RESULT["C9_neighbour_sensitivity"] = c9

# ---------------------------------------------------------------- 11. 팀의 press_supervised(커밋) 재실행 대조
log("C11 팀 지도학습 기준선 재실행")
import shutil  # noqa: E402

(Y / "press_submission/data").mkdir(exist_ok=True)
link = Y / "press_submission/data/3_소성가공_예지보전"
if not link.exists():
    link.symlink_to(D.data_dir(DATA_ROOT), target_is_directory=True)
(Y / "press_guard/artifacts").mkdir(exist_ok=True)
art_hash = {}
for sid in D.SPLITS:
    src = YEJUN_WT / "press_guard/artifacts" / f"guard_{sid}.json"
    if src.exists():
        shutil.copy2(src, Y / "press_guard/artifacts" / src.name)
        art_hash[sid] = D.sha256_file(src)
out_sup = TMP / "out_supervised"
env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
t_sup = time.monotonic()
proc = subprocess.run([sys.executable, str(Y / "analysis/press_supervised/run.py"), "--out", str(out_sup)], env=env, capture_output=True, text=True)
c11 = dict(returncode=proc.returncode, elapsed_s=time.monotonic() - t_sup, artifact_sha256=art_hash,
           manifest_dependency_guard_A=json.loads((Y / "analysis/press_supervised/manifest.json").read_text())["dependencies"]["press_guard/artifacts/guard_A.json"],
           tables={})
if proc.returncode == 0:
    for name in ("random_rows.csv", "grouped_records.csv", "injection.csv"):
        a_, b_ = pd.read_csv(Y / "analysis/press_supervised" / name), pd.read_csv(out_sup / name)
        try:
            pd.testing.assert_frame_equal(a_, b_, check_exact=False, rtol=0, atol=1e-12)
            c11["tables"][name] = "equal"
        except AssertionError as e:  # noqa: PERF203
            c11["tables"][name] = f"differs: {str(e)[:300]}"
    inj = pd.read_csv(Y / "analysis/press_supervised/injection.csv")
    c11["injection_pre_alarm_records_logistic_none"] = int(inj[inj.family.eq("none") & inj.model.eq("logistic")].pre_alarm_records.iloc[0])
    c11["injection_pre_alarm_records_logistic_all_conditions"] = sorted(inj[inj.model.eq("logistic")].pre_alarm_records.unique().tolist())
else:
    c11["stderr_tail"] = proc.stderr[-2000:]
RESULT["C11_team_supervised_rerun"] = c11
log("팀 지도학습 재실행", {k: v for k, v in c11.items() if k != "stderr_tail"})

# ---------------------------------------------------------------- 10. 문서 주장 대조
readme = (Y / "press_guard/README.md").read_text()
RESULT["C10_claims"] = dict(
    fn_reduction_A=(99 - 44) / 99, fn_reduction_B=(86 - 31) / 86,
    readme_mentions_55_6=("55.6%" in readme), readme_mentions_64_0=("64.0%" in readme),
    model_py_says_no_probability=("고장 확률은 추정하지 않는다" in (Y / "press_guard/model.py").read_text()),
    selection_state=json.loads(json.dumps(MODELS["A"].state["selection"])),
    prediction_columns=list(PRED["A"]["v2_abn"].columns))
RESULT["elapsed_s"] = time.monotonic() - T0
OUT_JSON.write_text(json.dumps(jsonable(RESULT), ensure_ascii=False, indent=1))
log("완료 →", OUT_JSON.name)
