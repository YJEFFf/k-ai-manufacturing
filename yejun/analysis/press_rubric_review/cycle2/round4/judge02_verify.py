"""평가관 02 사이클2 4회차 직접 검증.
3회차 독립 계산식을 재사용하되 현재 작업트리를 시스템 임시 사본에 복사한다.
원본/정상 분할/모델은 수정하지 않는다. 이 스크립트와 judge02_checks.json·judge02_run.log만 round4에 쓴다.
K1 주 지표·저장모델, K2 독립 등방회귀·교차확률, K3 현재 팀특징 부스팅21겹,
K4 주입전이 60행, K5 Markdown, K6 같은 특징 대안, K7 중첩선택, K8 통합표.
이전 회차의 별도 특징 실험은 이번 회차에 반복하지 않는다. 점수 확정 전 최종 산출물과 별도로 대조한다.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from scipy.stats import binom  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
COMMIT = "HEAD"
PREV_COMMIT = "061fac8"
DATA_DIR = REPO / "yejun" / "press_submission" / "data" / "3_소성가공_예지보전"
ROUND2 = json.loads((HERE.parent / "round2" / "judge02_checks.json").read_text(encoding="utf-8"))
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
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return None if not math.isfinite(v) else v
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_show_csv(commit, path):
    return pd.read_csv(io.StringIO(subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=REPO, text=True)))


# ---------------------------------------------------------------- 0. 현재 코드/필요 산출물 임시 사본
HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
BASE_COMMIT = HEAD
TMP = Path(tempfile.mkdtemp(prefix="judge02_c2r4_verify_"))
Y = TMP / "yejun"
paths = subprocess.check_output(["git", "ls-files", "-z", "--", "yejun/press_guard", "yejun/press_submission", "yejun/analysis"], cwd=REPO).decode().split("\0")
paths += [str(p.relative_to(REPO)) for p in (REPO / "yejun/press_guard/artifacts").glob("*.json")]
paths += [str(p.relative_to(REPO)) for p in (REPO / "yejun/press_guard/outputs").glob("test_predictions_*.csv")]
source_hashes = {}
for rel in paths:
    if not rel or rel.startswith("yejun/analysis/press_rubric_review/") or "/data/" in rel:
        continue
    source = REPO / rel
    if not source.is_file():
        continue
    dest = TMP / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    source_hashes[rel] = sha(dest)
(Y / "press_submission/data").mkdir(exist_ok=True)
(Y / "press_submission/data/3_소성가공_예지보전").symlink_to(DATA_DIR, target_is_directory=True)
RESULT["provenance"] = dict(head_at_start=HEAD, base_commit=BASE_COMMIT, code_extracted_to=str(TMP), data_dir=str(DATA_DIR),
                            source_sha256=source_hashes, note="작업트리 현재 사본으로 계산. 기존 커밋 점수를 그대로 신뢰하지 않고 원본에서 독립 재계산.")
log("HEAD", HEAD[:7], "현재 코드 사본 →", TMP)

sys.path.insert(0, str(Y / "press_guard"))
import model as M  # noqa: E402
from model import GuardModel, D, ALPHAS, layout, alert_units  # noqa: E402
import train as T  # noqa: E402
import probability as PR  # noqa: E402
import recalibrate as R  # noqa: E402
from press.calibrate import conformal_p, segment_max  # noqa: E402

from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score  # noqa: E402
from sklearn.neighbors import NearestNeighbors  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

normal, abnormal, report = D.load()
HASHES = {k: v["sha256"] for k, v in report["files"].items()}
RESULT["provenance"]["input_sha256"] = HASHES
RESULT["provenance"]["input_sha256_ok"] = all(v["sha256_ok"] and v["rows_ok"] for v in report["files"].values())
SEG_N = D.segments(normal)
SEG_A = D.segments(abnormal)
N_ABN = int(len(np.unique(SEG_A)))
# 새 기록 경계(0.1초 ± 20 ms, model.layout)가 v1 경계(D.segments)와 대회 자료에서 같은가
RESULT["provenance"]["layout_equals_v1_segments"] = dict(
    normal=bool(np.array_equal(layout(D.quantize(D.inputs_only(normal), "matched"))[1], SEG_N)),
    abnormal=bool(np.array_equal(layout(D.quantize(D.inputs_only(abnormal), "matched"))[1], SEG_A)))
log("원본 확인", RESULT["provenance"]["input_sha256_ok"], "정상 구간", len(np.unique(SEG_N)), "이상 구간", N_ABN,
    "새 기록 경계 = v1 경계", RESULT["provenance"]["layout_equals_v1_segments"])


def per_record(alarm, seg):
    s = pd.DataFrame(dict(r=seg, a=np.asarray(alarm, bool)))
    g = s.groupby("r").a
    return (g.size() - g.sum()).to_numpy(int), g.any().to_numpy(bool)


def alarm_from(cal_scores, units_cal, x_scores, alpha=.01):
    p = conformal_p(segment_max(cal_scores, units_cal), x_scores)
    return np.nan_to_num(p, nan=1.0) <= alpha


# ================================================================ K1. 주 수치·경보 불변
log("K1 주 수치 재계산")
committed_metrics = pd.read_csv(Y / "press_guard/outputs/metrics.csv")
manifest = json.loads((Y / "press_guard/outputs/manifest.json").read_text(encoding="utf-8"))
r2_rows = {(sid, r["alpha"]): r for sid, v in ROUND2["K1_headline_and_alarm_invariance"].items() for r in v["rows"]}
MODELS, SPLIT, PRED = {}, {}, {}
k1 = {}
art_dir = TMP / "artifacts_refit"
art_dir.mkdir()
for sid in D.SPLITS:
    split = D.split_normal(normal, SEG_N, sid)
    m = GuardModel.fit(split["train"], split["cal"], split=sid, input_hashes=HASHES)
    m.save(art_dir / f"guard_{sid}.json")
    MODELS[sid], SPLIT[sid] = m, split
    rows = []
    for alpha in ALPHAS:
        pn, pa = m.predict(split["test"], alpha), m.predict(abnormal, alpha)
        tp, fp = int(pa.alarm.sum()), int(pn.alarm.sum())
        fn = len(pa) - tp
        r = dict(alpha=alpha, tp=tp, fp=fp, fn=fn, f1=f1(tp, fp, fn),
                 normal_notified=int(pn.groupby("record_id").alarm.max().sum()), abnormal_detected=int(pa.groupby("record_id").alarm.max().sum()))
        c = committed_metrics[committed_metrics.split.eq(sid) & committed_metrics.model.eq("guard_v2") & np.isclose(committed_metrics.alpha, alpha)].iloc[0]
        r["equals_committed_metrics"] = bool((tp, fp, fn, r["normal_notified"], r["abnormal_detected"]) ==
                                             (c.tp, c.fp, c.fn, c.normal_notified_segments, c.abnormal_notified_segments) and abs(r["f1"] - c.f1) < 1e-12)
        o = r2_rows[(sid, alpha)]
        r["equals_round2_values"] = bool((tp, fp, fn, r["normal_notified"], r["abnormal_detected"]) ==
                                         (o["tp"], o["fp"], o["fn"], o["normal_notified"], o["abnormal_detected"]) and abs(r["f1"] - o["f1"]) < 1e-12)
        rows.append(r)
        if alpha == .01:
            PRED[sid] = dict(pn=pn, pa=pa)
    refit_sha = sha(art_dir / f"guard_{sid}.json")
    saved_sha = sha(Y / f"press_guard/artifacts/guard_{sid}.json")
    k1[sid] = dict(rows=rows, refit_artifact_sha256=refit_sha, manifest_artifact_sha256=manifest["artifacts"][f"guard_{sid}.json"],
                   refit_equals_manifest=refit_sha == manifest["artifacts"][f"guard_{sid}.json"],
                   current_saved_artifact_sha256=saved_sha, refit_equals_current_artifact=refit_sha == saved_sha)
    log(sid, [(r["alpha"], r["tp"], r["fp"], r["fn"], round(r["f1"], 6), r["equals_committed_metrics"], r["equals_round2_values"]) for r in rows],
        "저장 모델 해시 일치", k1[sid]["refit_equals_manifest"])
RESULT["K1_headline_and_alarm_invariance"] = k1


# ================================================================ K2. 이상 확률 층(R2-M2·R2-M3)
log("K2 이상 확률 층")


def iso_lr_factory(s0, s1, cap):
    """독립 구현: 정상(0)·이상(1) 점수에 등방 회귀 → 우도비 = 적합 오즈 / 적합 자료 이상 비율 오즈, 상한 cap, P̂=0은 최소 유한 우도비."""
    s0 = np.asarray(s0, float); s1 = np.asarray(s1, float)
    s0, s1 = s0[np.isfinite(s0)], s1[np.isfinite(s1)]
    x = np.r_[s0, s1]; y = np.r_[np.zeros(len(s0)), np.ones(len(s1))]
    iso = IsotonicRegression(y_min=0, y_max=1, increasing=True, out_of_bounds="clip").fit(x, y)
    odds_fit = y.mean() / (1 - y.mean())
    lv = np.unique(iso.predict(np.unique(x)))
    inner = lv[(lv > 0) & (lv < 1)]
    floor = min(float((inner / (1 - inner) / odds_fit).min()) if len(inner) else 1.0, cap)

    def lr(s):
        s = np.asarray(s, float)
        out = np.full(s.shape, np.nan)
        ok = np.isfinite(s)
        p = iso.predict(s[ok])
        pc = np.clip(p, 1e-9, 1 - 1e-9)
        out[ok] = np.where(p <= 0, floor, np.minimum(pc / (1 - pc) / odds_fit, cap))
        return out
    lr.iso, lr.odds_fit, lr.n0, lr.n1 = iso, odds_fit, len(s0), len(s1)
    return lr


def post(lr, pi):
    lr = np.asarray(lr, float)
    return pi * lr / (pi * lr + 1 - pi)


def ece10(y, p):
    e, edges = 0.0, np.linspace(0, 1, 11)
    for lo, hi in zip(edges[:-1], edges[1:]):
        k = (p >= lo) & ((p < hi) | (hi == 1))
        if k.any():
            e += k.mean() * abs(p[k].mean() - y[k].mean())
    return float(e)


def scores_metrics(y, q):
    q = np.clip(np.nan_to_num(q, nan=y.mean()), 1e-9, 1 - 1e-9)
    return dict(brier=float(brier_score_loss(y, q)), log_loss=float(log_loss(y, q)), ece=ece10(y, q),
                auroc=float(roc_auc_score(y, q)), ap=float(average_precision_score(y, q)))


prob_eval = pd.read_csv(Y / "press_guard/outputs/probability_eval_v2.csv")
prob_conv = pd.read_csv(Y / "press_guard/outputs/probability_conversion_v2.csv")
label_free = pd.read_csv(Y / "press_guard/outputs/label_free_alert_probability_v2.csv")
digest = json.loads((Y / "press_guard/outputs/expected/predictions_digest.json").read_text(encoding="utf-8"))
pred_out = TMP / "pred_out"
pred_out.mkdir()
k2 = {}
for sid in D.SPLITS:
    m, split = MODELS[sid], SPLIT[sid]
    cap = float(len(m.cal) + 1)
    deploy, oof_team = T.fit_probability(m, split["cal"], abnormal, sid, HASHES)
    deploy.save(art_dir / f"probability_{sid}.json")
    s_cal = m.predict(split["cal"]).score.to_numpy()
    pt, pa = m.predict(split["test"]), m.predict(abnormal)
    s_t, s_a = pt.score.to_numpy(), pa.score.to_numpy()
    rec_t, rec_a = pt.record_id.to_numpy(), pa.record_id.to_numpy()
    # (a) 배포 보정기 = 독립 구현, (b) 기록 1개 빼기 교차 적합 = 팀 oof
    my_deploy = iso_lr_factory(s_cal, s_a, cap)
    grid = np.linspace(np.nanmin(np.r_[s_cal, s_a, s_t]) - 1, np.nanmax(np.r_[s_cal, s_a, s_t]) + 5, 4001)
    deploy_equal = bool(np.allclose(my_deploy(grid), deploy.likelihood_ratio(grid), rtol=1e-10, atol=1e-12))
    my_oof = np.full(len(s_a), np.nan)
    ln_folds = []
    for r in np.unique(rec_a):
        keep = rec_a != r
        f_ = iso_lr_factory(s_cal, s_a[keep], cap)
        my_oof[~keep] = f_(s_a[~keep])
        ln_folds.append(f_(s_t))
    oof_equal = bool(np.allclose(my_oof, oof_team, rtol=1e-10, atol=1e-12))
    y = np.r_[np.zeros(len(s_t)), np.ones(len(s_a))]
    pi_rows = len(s_a) / len(y)
    fold21 = scores_metrics(y, post(np.r_[np.median(ln_folds, axis=0), my_oof], pi_rows))
    ce = prob_eval[prob_eval.split.eq(sid) & prob_eval.cv.eq("21fold") & prob_eval.unit.eq("rows")].set_index("method")
    fold21_vs_committed = {k: dict(mine=fold21[k], committed=float(ce.loc["calibrated_isotonic", k]), abs_diff=abs(fold21[k] - float(ce.loc["calibrated_isotonic", k])))
                           for k in ("brier", "log_loss", "ece", "auroc", "ap")}
    # (c) 예측 파일: 팀 train.evaluate_pair로 임시 폴더에 생성 → 새 열(file_prior·anomaly_probability_file_prior)과 README 수치
    m_prob = GuardModel(m.state).attach_probability(PR.ProbabilityCalibrator.load(art_dir / f"probability_{sid}.json"))
    T.evaluate_pair(m_prob, split["cal"], split["test"], abnormal, sid, pred_out, oof_lr=oof_team)
    fpath = pred_out / f"test_predictions_{sid}.csv"
    tpf = pd.read_csv(fpath)
    lab = tpf.label.to_numpy(float)
    tp_, fp_, fn_ = int(((tpf.alarm == 1) & (tpf.label == 1)).sum()), int(((tpf.alarm == 1) & (tpf.label == 0)).sum()), int(((tpf.alarm == 0) & (tpf.label == 1)).sum())
    ab, no = tpf[tpf.label.eq(1)], tpf[tpf.label.eq(0)]
    file_prev = float(lab.mean())
    new_cols_present = all(c in tpf.columns for c in ("file_prior", "anomaly_probability_file_prior"))
    pi1 = scores_metrics(lab, tpf.anomaly_probability.to_numpy())
    fprior_col = scores_metrics(lab, tpf.anomaly_probability_file_prior.to_numpy()) if new_cols_present else None
    fprior_mine = scores_metrics(lab, post(tpf.likelihood_ratio.to_numpy(), file_prev))
    alarm_rows = tpf[tpf.alarm.eq(1)]
    fa = tpf[(tpf.alarm == 1) & (tpf.label == 0)]
    ent = digest.get(f"test_predictions_{sid}.csv") or {}
    file_checks = dict(
        rows=len(tpf), f1=f1(tp_, fp_, fn_), tp_fp_fn=[tp_, fp_, fn_], new_columns_present=new_cols_present,
        file_prior_values=sorted(tpf.file_prior.unique().tolist()) if new_cols_present else None, file_prevalence=file_prev,
        file_prior_column_equals_posterior=(bool(np.allclose(tpf.anomaly_probability_file_prior, post(tpf.likelihood_ratio, file_prev), rtol=1e-12, atol=0))
                                            if new_cols_present else None),
        abnormal_lr_equals_my_oof=bool(np.allclose(ab.likelihood_ratio.to_numpy(), my_oof, rtol=1e-10)),
        normal_lr_equals_my_deploy=bool(np.allclose(no.likelihood_ratio.to_numpy(), my_deploy(no.score.to_numpy()), rtol=1e-10)),
        prob_equals_posterior_pi1=bool(np.allclose(tpf.anomaly_probability, post(tpf.likelihood_ratio, .01), rtol=1e-12)),
        record_prob_equals_posterior_pi1=bool(np.allclose(tpf.record_probability, post(tpf.record_likelihood_ratio, .01), rtol=1e-12)),
        sources=tpf.groupby("subset").probability_source.unique().apply(list).to_dict(),
        metrics_pi1=pi1, metrics_file_prior_column=fprior_col, metrics_file_prior_mine=fprior_mine,
        abnormal_rows_lr_at_cap=int(np.isclose(ab.likelihood_ratio.to_numpy(), cap).sum()),
        abnormal_prob_pi1_max=float(ab.anomaly_probability.max()),
        alarm_rows=len(alarm_rows), alarm_rows_lr_at_cap=int(np.isclose(alarm_rows.likelihood_ratio.to_numpy(), cap).sum()),
        false_alarm_rows=len(fa), false_alarm_lr=fa.likelihood_ratio.tolist(), false_alarm_prob_pi1=fa.anomaly_probability.tolist(),
        min_lr_alarm_rows=float(alarm_rows.likelihood_ratio.min()) if len(alarm_rows) else None,
        min_p_pi1_alarm_rows=float(alarm_rows.anomaly_probability.min()) if len(alarm_rows) else None,
        alarm_rows_lr_below_1=int((alarm_rows.likelihood_ratio < 1).sum()),
        my_file_sha256=sha(fpath), digest_sha256=ent.get("sha256"), sha_equals_digest=ent.get("sha256") == sha(fpath))
    # (d) 문턱 점수의 등방 계단(R2-M3)과 커밋 표 대조
    thr = float(np.max(m.cal))
    iso = my_deploy.iso
    x_all = np.r_[s_cal[np.isfinite(s_cal)], s_a[np.isfinite(s_a)]]
    lab_fit = np.r_[np.zeros(int(np.isfinite(s_cal).sum())), np.ones(int(np.isfinite(s_a).sum()))]
    pred_all = iso.predict(x_all)
    v_thr = float(iso.predict([thr])[0])
    blk = np.isclose(pred_all, v_thr, rtol=0, atol=1e-12)
    right_x = x_all[x_all > thr + 1e-12]
    nxt = float(right_x.min()) if len(right_x) else None
    step = dict(p_hat=v_thr, pi_fit=float(lab_fit.mean()), lr=float(v_thr / (1 - v_thr) / my_deploy.odds_fit) if 0 < v_thr < 1 else None,
                left=float(x_all[blk].min()), right_edge=float(x_all[blk].max()), next_score=nxt,
                p_hat_next=float(iso.predict([nxt])[0]) if nxt is not None else None,
                normal_cal_rows=int((blk & (lab_fit == 0)).sum()), abnormal_rows=int((blk & (lab_fit == 1)).sum()),
                lr_at_threshold_team=float(deploy.likelihood_ratio([thr + 1e-9])[0]), p_pi1_at_threshold=float(post(deploy.likelihood_ratio([thr + 1e-9])[0], .01)),
                lr_at_threshold_block=float(v_thr / (1 - v_thr) / my_deploy.odds_fit) if 0 < v_thr < 1 else None)
    cc = prob_conv[prob_conv.split.eq(sid) & np.isclose(prob_conv.prior, .01)].iloc[0]
    conv_cmp = dict(iso_step_left=(float(cc.iso_step_left), step["left"]), iso_step_right=(float(cc.iso_step_right), step["next_score"]),
                    step_normal_cal_rows=(int(cc.step_normal_cal_rows), step["normal_cal_rows"]), step_abnormal_rows=(int(cc.step_abnormal_rows), step["abnormal_rows"]),
                    step_p_hat=(float(cc.step_p_hat), step["p_hat"]), alarm_rows=(int(cc.alarm_rows), file_checks["alarm_rows"]),
                    alarm_rows_min_lr=(float(cc.alarm_rows_min_lr), file_checks["min_lr_alarm_rows"]),
                    alarm_rows_lr_below_1=(int(cc.alarm_rows_lr_below_1), file_checks["alarm_rows_lr_below_1"]),
                    false_alarm_rows=(int(cc.false_alarm_rows), file_checks["false_alarm_rows"]),
                    p_at_threshold=(float(cc.p_at_threshold), step["p_pi1_at_threshold"]))
    conv_ok = all((abs(a - b) < 1e-9 if isinstance(a, float) else a == b) for a, b in conv_cmp.values() if b is not None)
    k2[sid] = dict(deploy_equals_independent=deploy_equal, loo_equals_team_oof=oof_equal, pi_rows=pi_rows, cap=cap,
                   probability_refit_sha256=sha(art_dir / f"probability_{sid}.json"),
                   probability_saved_sha256=sha(Y / f"press_guard/artifacts/probability_{sid}.json"),
                   probability_artifact_equal=sha(art_dir / f"probability_{sid}.json") == sha(Y / f"press_guard/artifacts/probability_{sid}.json"),
                   fold21_vs_committed=fold21_vs_committed, prediction_file=file_checks, threshold_step=step, conversion_table_vs_mine=conv_cmp,
                   conversion_table_matches=conv_ok)
    log(sid, "배포=독립", deploy_equal, "LOO=독립", oof_equal, "21겹 Brier/ECE", round(fold21["brier"], 5), round(fold21["ece"], 5),
        "커밋 차 최대", max(v["abs_diff"] for v in fold21_vs_committed.values()))
    log(sid, "파일", {k: v for k, v in file_checks.items() if not k.startswith("metrics")})
    log(sid, "파일 채점 π=1%", {k: round(v, 5) for k, v in pi1.items()}, "파일 비율 열", {k: round(v, 5) for k, v in (fprior_col or {}).items()})
    log(sid, "문턱 계단", step, "변환표 일치", conv_ok)

# 라벨 없는 환산(README:111-116)
lf = label_free[label_free.split.eq("A") & np.isclose(label_free.alpha, .01)]
lf_nom = lf[lf.far_basis.eq("nominal") & lf.tpr_basis.eq("E1 cur_noise 0.1")].set_index("prior").p_anomaly_given_alert
lf_cal = lf[lf.far_basis.eq("calibrated95") & lf.tpr_basis.eq("E1 cur_noise 0.1")].set_index("prior").p_anomaly_given_alert
tpr = float(lf[lf.tpr_basis.eq("E1 cur_noise 0.1")].tpr.iloc[0])
far_nom = 1 / 121


def pa_given_alert(pi, tpr_, far):
    return pi * tpr_ / (pi * tpr_ + (1 - pi) * far)


sbb = 1 / PR.sellke_bayes_factor(1 / 121)
RESULT["K2_probability_layer"] = dict(
    per_split=k2,
    label_free=dict(tpr=tpr, nominal_pi0_1=float(lf_nom.loc[.001]), nominal_pi1=float(lf_nom.loc[.01]),
                    mine_nominal_pi0_1=pa_given_alert(.001, tpr, far_nom), mine_nominal_pi1=pa_given_alert(.01, tpr, far_nom),
                    calibrated95_pi0_1=float(lf_cal.loc[.001]), calibrated95_pi1=float(lf_cal.loc[.01]),
                    note_column_unit=sorted(label_free.note.unique().tolist())[:1]),
    sbb_lr=sbb, sbb_p_pi1=float(post(sbb, .01)))
log("라벨 없는 환산", RESULT["K2_probability_layer"]["label_free"], "SBB", round(sbb, 3), round(float(post(sbb, .01)), 4))

# π 단위 표기(R2-M2 ③): README 열 설명·콘솔 선택지·라벨 없는 환산 표
readme_guard = (Y / "press_guard/README.md").read_text(encoding="utf-8").splitlines()
index_html = (Y / "press_guard/web/index.html").read_text(encoding="utf-8")
RESULT["K2_prior_unit_text"] = dict(
    readme_lines=[f"{i + 1}: {l.strip()[:220]}" for i, l in enumerate(readme_guard) if ("π" in l and ("단위" in l or "비율" in l))][:8],
    console_prior_option=re.findall(r'<select id="prior">.*?</select>', index_html)[:1],
    label_free_note=sorted(label_free.note.unique().tolist()))
log("π 단위 표기", json.dumps(RESULT["K2_prior_unit_text"], ensure_ascii=False)[:900])


# ================================================================ K3. 지도학습 설명(R2-M4)
log("K3 지도학습 기준선")
sup = load_module("j02_sup", Y / "analysis/press_supervised/run.py")
gr = pd.read_csv(Y / "analysis/press_supervised/grouped_records.csv")
readme_sup = (Y / "analysis/press_supervised/README.md").read_text(encoding="utf-8")
g21 = gr[gr.cv.eq("21fold") & gr.threshold.eq("conformal")]
v2f1 = {sid: [r for r in k1[sid]["rows"] if r["alpha"] == .01][0]["f1"] for sid in D.SPLITS}
diffs = {}
for r in g21[g21.features.eq("window_plus_v2")].itertuples():
    diffs[f"{r.split}:{r.model}"] = dict(f1=float(r.f1), minus_v2=float(r.f1) - v2f1[r.split], detected=int(r.abnormal_detected_segments), normal_alerted=int(r.normal_alerted_segments))
unweighted = [v["minus_v2"] for k, v in diffs.items() if not k.endswith("_balanced")]
allw = [v["minus_v2"] for v in diffs.values()]


def judge_features(frame, m):
    """1회차 평가관 특징(round1·round2 judge02_verify.py와 같은 식)."""
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
    return df.to_numpy(float)


def judge_clf(kind, balanced):
    cw = "balanced" if balanced else None
    if kind == "logistic":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=1.0, class_weight=cw, max_iter=5000))
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=.1, class_weight=cw, random_state=0)


def loso(make, Xn, Xc, Xt, Xa, seg_cal, seg_test):
    fn, per_fold = 0, []
    for j in range(N_ABN):
        keep = SEG_A != j
        clf = make().fit(np.r_[Xn, Xa[keep]], np.r_[np.zeros(len(Xn)), np.ones(int(keep.sum()))])
        thr = float(pd.Series(clf.predict_proba(Xc)[:, 1]).groupby(seg_cal).max().max())
        pj = clf.predict_proba(Xa[~keep])[:, 1]
        miss = int((pj <= thr).sum())
        fn += miss
        per_fold.append(dict(record=j, rows=int((~keep).sum()), threshold=thr, fn=miss))
    clf = make().fit(np.r_[Xn, Xa], np.r_[np.zeros(len(Xn)), np.ones(len(Xa))])
    thr = float(pd.Series(clf.predict_proba(Xc)[:, 1]).groupby(seg_cal).max().max())
    al = clf.predict_proba(Xt)[:, 1] > thr
    fp = int(al.sum())
    return dict(fn=fn, fp=fp, f1=f1(600 - fn, fp, fn), normal_alerted=int(pd.Series(al).groupby(seg_test).any().sum()),
                detected=int(sum(1 for r in per_fold if r["fn"] < r["rows"])), per_fold=per_fold)


k3 = dict(window_plus_v2_minus_v2=diffs, unweighted_range=[min(unweighted), max(unweighted)], all_range=[min(allw), max(allw)], per_split={})
for sid in D.SPLITS:
    m, split = MODELS[sid], SPLIT[sid]
    seg_cal, seg_test = D.segments(split["cal"]), D.segments(split["test"])
    Fn, Fc, Ft, Fa = (sup.features(f, "window_plus_v2", m).to_numpy(float) for f in (split["train"], split["cal"], split["test"], abnormal))
    t0 = time.monotonic()
    team = loso(sup.MODELS["hgb"], Fn, Fc, Ft, Fa, seg_cal, seg_test)
    th = [r["threshold"] for r in team["per_fold"]]
    committed = g21[g21.split.eq(sid) & g21.features.eq("window_plus_v2") & g21.model.eq("hgb")].iloc[0]
    rec2 = team["per_fold"][2]
    out = dict(team_hgb_fn=team["fn"], committed_fn=int(committed.fn), detected=team["detected"], threshold_min=min(th), threshold_max=max(th),
               record2=dict(threshold=rec2["threshold"], fn=rec2["fn"], rows=rec2["rows"]), fn_by_fold=[r["fn"] for r in team["per_fold"]])
    log(sid, "팀 특징 부스팅 21겹 미탐", team["fn"], "커밋", int(committed.fn), "문턱", (round(min(th), 3), round(max(th), 3)), "기록 2", rec2,
        f"{time.monotonic() - t0:.0f}s")
    out["round1_features_rerun"] = False  # 과거 특징 비교는 3회차 기록을 참고하며 이번 회차에 반복하지 않는다.
    k3["per_split"][sid] = out
k3["readme_mentions"] = {s: (s in readme_sup) for s in ("0.248~0.997", "0.990", "47행", "0.830", "18/21", "−0.132", "0.9601·0.9574", "0.9709·0.9673", "−0.047~+0.011")}
RESULT["K3_supervised"] = k3
log("K3 범위", k3["unweighted_range"], k3["all_range"], k3["readme_mentions"])


# ================================================================ 성분 문맥(K4·K6·K7 공용)
def my_fusions(g):
    """독립 구현: g=−log10 p. Fisher: −2Σln p ~ χ²(2k), Stouffer: Σ Φ⁻¹(1−p)/√k, 합·평균. k = 유한 성분 수."""
    fin = np.isfinite(g)
    k = fin.sum(1)
    gz = np.where(fin, g, 0.0)
    total = gz.sum(1)
    with np.errstate(all="ignore"):
        fisher = -np.log10(stats.chi2.sf(2 * np.log(10) * total, 2 * np.maximum(k, 1)))
        fisher_log = -stats.chi2.logsf(2 * np.log(10) * total, 2 * np.maximum(k, 1)) / np.log(10)
        z = np.where(fin, stats.norm.isf(np.clip(10.0 ** (-np.where(fin, g, 0.0)), 1e-300, 1)), 0.0)
        stouffer = z.sum(1) / np.sqrt(np.maximum(k, 1))
    none = k == 0
    fisher = np.where(np.isfinite(fisher), fisher, fisher_log)
    return {"fisher": np.where(none, np.nan, fisher), "stouffer": np.where(none, np.nan, stouffer),
            "sum": np.where(none, np.nan, total), "mean": np.where(none, np.nan, total / np.maximum(k, 1))}


CTX = {}
for sid in D.SPLITS:
    m, split = MODELS[sid], SPLIT[sid]
    P = {}
    for key, frame in (("train", split["train"]), ("cal", split["cal"]), ("test", split["test"]), ("abn", abnormal)):
        q = D.quantize(D.inputs_only(frame), "matched")
        seg = layout(q)[1]
        pos = D.segment_positions(seg)[0]
        comp = m.components(q, seg)
        P[key] = dict(q=q, seg=seg, pos=pos, units=alert_units(seg, pos), comp=comp,
                      g=np.column_stack([comp["g_magnitude"], comp["g_waveform"], comp["g_dynamics"]]))
    assert np.array_equal(segment_max(P["cal"]["comp"]["score"], P["cal"]["units"]), m.cal)
    CTX[sid] = P


# ================================================================ K4. 같은 특징 대안의 주입 전이표(R2-M1) 독립 재계산
log("K4 같은 특징 대안의 주입 전이표(rule_transfer_injection_v2.csv)")
selm = load_module("j02_sel", Y / "analysis/press_selection/run.py")
rt_c = pd.read_csv(Y / "analysis/press_selection/rule_transfer_injection_v2.csv")
fpinj_c = pd.read_csv(Y / "analysis/press_selection/fp_mitigation_injection_v2.csv")
r2_k5 = {(sid, r["family"], r["level"]): r for sid, rows in ROUND2["K5_rule_transfer_injection"]["results"].items() for r in rows}
RULES = ("v2_fmax", "fisher", "stouffer", "sum", "5nn")
k4 = dict(rows=[], mismatches=[], max_abs_diff=0.0)
for sid in D.SPLITS:
    m, split, P = MODELS[sid], SPLIT[sid], CTX[sid]
    test = split["test"]
    units, in_unit, size = R.unit_layout(test)
    eligible = size >= R.MIN_UNIT_ROWS
    window = (in_unit >= R.T0) & (in_unit < R.T0 + R.WINDOW)
    nn5 = NearestNeighbors(n_neighbors=5).fit(np.nan_to_num(P["train"]["g"], nan=0.0))

    def rule_scores(comp):
        g = np.column_stack([comp["g_magnitude"], comp["g_waveform"], comp["g_dynamics"]])
        fu = my_fusions(g)
        return {"v2_fmax": comp["score"], "fisher": fu["fisher"], "stouffer": fu["stouffer"], "sum": fu["sum"],
                "5nn": nn5.kneighbors(np.nan_to_num(g, nan=0.0))[0].mean(1)}
    cals = {k: segment_max(v, P["cal"]["units"]) for k, v in rule_scores(P["cal"]["comp"]).items()}
    assert np.array_equal(cals["v2_fmax"], m.cal)
    for family, level in selm.INJ_FAMILIES:
        reps = selm.INJ_REPS if family in ("cur_noise", "vib_noise", "vib_shock") else 1
        hits = {(k, a): [] for k in RULES for a in ALPHAS}
        for rep in range(reps):
            rng = np.random.default_rng(rep)
            if family == "none":
                X = D.inputs_only(test)
            elif family == "vib_shock":
                X = selm.vib_shock(test, m, level, eligible & (in_unit == R.T0), rng)
            else:
                X = R.inject(test, m, family, level, eligible & (in_unit >= R.T0), rng)
            q = D.quantize(D.inputs_only(X), "matched")
            seg = layout(q)[1]
            sc = rule_scores(m.components(q, seg))
            for k_, s_ in sc.items():
                p_ = np.nan_to_num(conformal_p(cals[k_], s_), nan=1.0)
                for a in ALPHAS:
                    hit = (p_ <= a) & window & eligible
                    hits[(k_, a)].append(pd.Series(hit[eligible]).groupby(units[eligible]).any().to_numpy())
        for a in ALPHAS:
            row = dict(split=sid, alpha=a, family=family, level=level, reps=reps, units=int(pd.Series(units[eligible]).nunique()))
            for k_ in RULES:
                row[k_] = float(np.concatenate(hits[(k_, a)]).mean())
            c = rt_c[rt_c.split_id.eq(sid) & np.isclose(rt_c.alpha, a) & rt_c.family.eq(family) & np.isclose(rt_c.level, level)]
            if len(c) != 1:
                k4["mismatches"].append(("missing_row", sid, a, family, level))
            else:
                for k_ in RULES:
                    d_ = abs(row[k_] - float(c.iloc[0][f"{k_}_detect_2s"]))
                    k4["max_abs_diff"] = max(k4["max_abs_diff"], d_)
                    if d_ > 1e-12:
                        k4["mismatches"].append((sid, a, family, level, k_, row[k_], float(c.iloc[0][f"{k_}_detect_2s"])))
                row["committed_units"] = int(c.iloc[0].units)
            fp_c = fpinj_c[fpinj_c.split_id.eq(sid) & np.isclose(fpinj_c.alpha, a) & fpinj_c.family.eq(family) & np.isclose(fpinj_c.level, level)]
            row["equals_fp_mitigation_v2_col"] = bool(len(fp_c) == 1 and abs(float(fp_c.v2_detect_2s.iloc[0]) - row["v2_fmax"]) < 1e-12)
            if a == .01:
                o = r2_k5.get((sid, family, level))
                row["equals_round2_K5"] = bool(o is not None and all(abs(o[k_] - row[k_]) < 1e-12 for k_ in RULES))
            k4["rows"].append(row)
        log(sid, family, level, {k_: round(k4["rows"][-3][k_], 3) for k_ in RULES}, "(α1%)")
df4 = pd.DataFrame(k4["rows"])


def claim(expr, desc):
    return dict(desc=desc, holds=bool(expr))


a1 = df4[np.isclose(df4.alpha, .01)]
fams = a1[~a1.family.eq("none")]
A_, B_ = fams[fams.split.eq("A")], fams[fams.split.eq("B")]
k4["readme_claims_alpha1"] = [
    claim(((A_.fisher >= A_.v2_fmax) & (A_["sum"] >= A_.v2_fmax) & (A_["5nn"] >= A_.v2_fmax)).all(),
          "README:71 A에서는 Fisher·합·5NN이 모든 주입 족에서 fmax와 같거나 높다"),
    claim(set(B_[(B_.v2_fmax > B_.fisher) & (B_.v2_fmax > B_["sum"]) & (B_.v2_fmax > B_["5nn"])].apply(lambda r: f"{r.family}:{r.level}", axis=1)) == {"vib_shock:4.0"},
          "README:72 B에서 fmax가 세 대안 모두보다 앞서는 곳은 단발 충격 4σ뿐"),
    claim(((B_.family.eq("vib_noise") & np.isclose(B_.level, 2.0)) & (B_.v2_fmax > B_.fisher) & (B_.v2_fmax > B_["sum"])).any(),
          "README:72 B 진동 잡음 2σ에서 fmax가 Fisher·합보다 높다"),
    claim((B_[~(B_.family.eq("vib_shock") & np.isclose(B_.level, 4.0))]["5nn"] >= B_[~(B_.family.eq("vib_shock") & np.isclose(B_.level, 4.0))].v2_fmax).all(),
          "README:72 B 나머지 족은 5NN이 fmax와 같거나 높다"),
    claim((fams.stouffer <= fams.v2_fmax).all(), "README:73 Stouffer는 두 분할 모든 족에서 fmax 이하"),
    claim(set(B_[B_.fisher < B_.v2_fmax].apply(lambda r: f"{r.family}:{r.level}", axis=1)) == {"vib_noise:2.0", "vib_shock:4.0", "cur_noise:0.1", "vib_shock:6.0"},
          "combination_rules.csv Fisher remark: B에서 Fisher가 fmax보다 낮은 족은 진동 잡음 2σ·전류 잡음 0.1σ·단발 충격 4σ·6σ"),
]
k4["B_fisher_below_fmax_families"] = B_[B_.fisher < B_.v2_fmax][["family", "level", "v2_fmax", "fisher"]].to_dict("records")
for a in (.03, .05):
    aa = df4[np.isclose(df4.alpha, a) & ~df4.family.eq("none")]
    A2 = aa[aa.split.eq("A")]
    k4[f"A_alternatives_ge_fmax_alpha{int(a * 100)}"] = bool(((A2.fisher >= A2.v2_fmax) & (A2["sum"] >= A2.v2_fmax) & (A2["5nn"] >= A2.v2_fmax)).all())
    k4[f"A_rows_alt_below_fmax_alpha{int(a * 100)}"] = A2[(A2.fisher < A2.v2_fmax) | (A2["sum"] < A2.v2_fmax) | (A2["5nn"] < A2.v2_fmax)][
        ["family", "level", "v2_fmax", "fisher", "sum", "5nn"]].to_dict("records")
RESULT["K4_rule_transfer_injection"] = k4
log("K4 불일치", len(k4["mismatches"]), "최대 차", k4["max_abs_diff"], "README 주장", [(c["desc"][:40], c["holds"]) for c in k4["readme_claims_alpha1"]])
log("K4 B Fisher < fmax", k4["B_fisher_below_fmax_families"])


# ================================================================ K5. 비교표 입력 조건 열(R2-M5)
log("K5 비교표 입력 조건")
mc = pd.read_csv(Y / "press_guard/outputs/model_comparison_v2.csv")
md = (Y / "press_guard/outputs/model_comparison_v2.md").read_text(encoding="utf-8").splitlines()
table = [l for l in md if l.startswith("|")]
header_cells = len(re.split(r"(?<!\\)\|", table[0].strip().strip("|")))
row_cells = [(len(re.split(r"(?<!\\)\|", l.strip().strip("|"))), l[:70]) for l in table[2:]]
bad_rows = [(n, s) for n, s in row_cells if n != header_cells]
k5 = dict(csv_has_column="input_features" in mc.columns, empty_values=int(mc.input_features.fillna("").eq("").sum()),
          models=sorted(mc.model.unique().tolist()), mapping=mc.groupby("model").input_features.first().to_dict(),
          md_header_cells=header_cells, md_rows=len(row_cells), md_rows_with_wrong_cell_count=len(bad_rows), md_bad_row_examples=bad_rows[:4],
          md_final_model_row=[l for l in table if "**early6_ar2**" in l][:1])
RESULT["K5_model_comparison_input_column"] = k5
log("K5", {k: v for k, v in k5.items() if k not in ("mapping",)})


# ================================================================ K6. 같은 특징 대안·결합 규칙 독립 재계산(회귀: 모델 코드 변경 뒤에도 같은가)
log("K6 같은 특징 대안·결합 규칙")
ear = load_module("j02_ear", Y / "analysis/press_early/run_experiment.py")
alts_c = pd.read_csv(Y / "analysis/press_selection/same_feature_alternatives.csv")
rules_c = pd.read_csv(Y / "analysis/press_selection/combination_rules.csv")
k6 = {}
for sid in D.SPLITS:
    m, split, P = MODELS[sid], SPLIT[sid], CTX[sid]
    mats = {k: np.nan_to_num(P[k]["g"], nan=0.0) for k in P}
    nn5 = NearestNeighbors(n_neighbors=5).fit(mats["train"])
    iso_f = IsolationForest(random_state=0).fit(mats["train"])
    cands = {"v2": {k: P[k]["comp"]["score"] for k in ("cal", "test", "abn")},
             "5NN(v2 성분)": {k: nn5.kneighbors(mats[k])[0].mean(1) for k in ("cal", "test", "abn")},
             "IF(v2 성분)": {k: -iso_f.score_samples(mats[k]) for k in ("cal", "test", "abn")}}
    fus = {k: my_fusions(P[k]["g"]) for k in ("cal", "test", "abn")}
    for name in ("fisher", "stouffer", "sum", "mean"):
        cands[name] = {k: fus[k][name] for k in fus}
    tr = D.quantize(split["train"], "matched")
    seg_tr = D.segments(tr)
    for order in (1, 3, 4):
        lin = ear.Linear(tr, seg_tr, order)
        cands[f"early+AR({order})"] = {k: np.fmax(np.fmax(P[k]["comp"]["g_magnitude"], P[k]["comp"]["g_waveform"]),
                                                  lin.tail(lin.residual(D.quantize(D.inputs_only({"cal": split["cal"], "test": split["test"], "abn": abnormal}[k]), "matched"),
                                                                        P[k]["seg"]))) for k in ("cal", "test", "abn")}
    rows = []
    for alpha in ALPHAS:
        v2_thr_p = {k: np.nan_to_num(conformal_p(m.cal, P[k]["comp"]["score"]), nan=1.0) <= alpha for k in ("test", "abn")}
        for name, s in cands.items():
            at = alarm_from(s["cal"], P["cal"]["units"], s["test"], alpha)
            aa = alarm_from(s["cal"], P["cal"]["units"], s["abn"], alpha)
            fnr, det = per_record(aa, P["abn"]["seg"])
            tp, fp = int(aa.sum()), int(at.sum())
            rows.append(dict(alpha=alpha, candidate=name, tp=tp, fp=fp, fn=len(aa) - tp, f1=f1(tp, fp, len(aa) - tp),
                             normal_alerted=int(pd.Series(at).groupby(P["test"]["seg"]).any().sum()), detected=int(det.sum()),
                             no_evidence_abn=int((aa & ~v2_thr_p["abn"]).sum()), no_evidence_normal=int((at & ~v2_thr_p["test"]).sum())))
    df = pd.DataFrame(rows)
    name_map_alt = {"v2": "v2 (fmax, AR(2))", "5NN(v2 성분)": "5NN(v2 성분)", "IF(v2 성분)": "IF(v2 성분)", "sum": "합(v2 성분)",
                    "early+AR(1)": "early+AR(1)", "early+AR(3)": "early+AR(3)", "early+AR(4)": "early+AR(4)"}
    mism = []
    for r in df.itertuples():
        if r.candidate in name_map_alt:
            c = alts_c[alts_c.split_id.eq(sid) & np.isclose(alts_c.alpha, r.alpha) & alts_c.candidate.eq(name_map_alt[r.candidate])]
            ok = len(c) == 1 and (c.iloc[0].tp, c.iloc[0].fp, c.iloc[0].fn, c.iloc[0].normal_alerted, c.iloc[0].abnormal_detected) == (r.tp, r.fp, r.fn, r.normal_alerted, r.detected)
            if not ok:
                mism.append(("alt", r.alpha, r.candidate))
            if r.candidate in ("5NN(v2 성분)", "IF(v2 성분)", "sum", "v2") and not (len(c) == 1 and c.iloc[0].no_evidence_alarms_abnormal == r.no_evidence_abn):
                mism.append(("alt_no_evidence", r.alpha, r.candidate))
        if r.candidate in ("fisher", "stouffer", "sum", "mean"):
            c = rules_c[rules_c.split_id.eq(sid) & np.isclose(rules_c.alpha, r.alpha) & rules_c.rule.eq(r.candidate)]
            ok = len(c) == 1 and (c.iloc[0].tp, c.iloc[0].fp, c.iloc[0].fn, c.iloc[0].normal_alerted, c.iloc[0].no_evidence_alarms_abnormal,
                                  c.iloc[0].no_evidence_alarms_normal) == (r.tp, r.fp, r.fn, r.normal_alerted, r.no_evidence_abn, r.no_evidence_normal)
            if not ok:
                mism.append(("rule", r.alpha, r.candidate))
    k6[sid] = dict(rows=df.to_dict("records"), mismatches_vs_committed=mism)
    log(sid, "불일치", mism)
    log(sid, df[df.alpha.eq(.01)][["candidate", "tp", "fp", "fn", "normal_alerted", "detected", "no_evidence_abn", "no_evidence_normal"]].to_string(index=False))
# 커밋 사이 수치 열 불변(remark만 바뀌었는가)
num_unchanged = {}
for path, key in (("yejun/analysis/press_selection/same_feature_alternatives.csv", "candidate"), ("yejun/analysis/press_selection/combination_rules.csv", "rule")):
    old, new = git_show_csv(PREV_COMMIT, path), pd.read_csv(TMP / path)
    cols = [c for c in old.columns if c in new.columns and pd.api.types.is_numeric_dtype(old[c])]
    same_shape = old.shape[0] == new.shape[0]
    num_unchanged[path] = dict(numeric_cols=len(cols), rows_old=len(old), rows_new=len(new),
                               numeric_equal=bool(same_shape and np.allclose(old[cols].to_numpy(float), new[cols].to_numpy(float), equal_nan=True, rtol=0, atol=1e-12)),
                               changed_text_cols=[c for c in old.columns if c in new.columns and not pd.api.types.is_numeric_dtype(old[c]) and not old[c].equals(new[c])])
k6["numeric_unchanged_since_round3"] = num_unchanged
RESULT["K6_same_feature_and_rules"] = k6
log("K6 수치 열 불변", num_unchanged)


# ================================================================ K7. 선정 근거(회귀): 후보 재계산·중첩 선택·짝 비교
log("K7 선정 근거")
from press.scores import Scorer  # noqa: E402
adv = load_module("j02_adv", Y / "analysis/press_advance/run_experiment.py")
imp = load_module("j02_imp", Y / "analysis/press_improvement/run_experiment.py")
vendor = D.load_vendor()
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
STATS = {}
for sid in D.SPLITS:
    segs = SEGS[sid]
    for name, s in UNIVERSE[sid].items():
        an = alarm_from(s["cal"], segs["cal"], s["test"])
        aa = alarm_from(s["cal"], segs["cal"], s["abn"])
        fnr, det = per_record(aa, segs["abn"])
        STATS[(sid, name)] = dict(normal_alarm=int(pd.Series(an).groupby(segs["test"]).any().sum()), fp=int(an.sum()),
                                  fn_by_rec=fnr, det_by_rec=det, alarm_abn=aa, alarm_test=an)
names = sorted({n for (_, n) in STATS})
sig = {}
for n in names:
    key = np.r_[STATS[("A", n)]["alarm_abn"], STATS[("A", n)]["alarm_test"], STATS[("B", n)]["alarm_abn"], STATS[("B", n)]["alarm_test"]].astype(int).tobytes()
    sig.setdefault(key, []).append(n)
unique = [v[0] for v in sig.values()]
aliases = {v[0]: v[1:] for v in sig.values() if len(v) > 1}
base_rep = next(u for u in unique if u == "advance:baseline_w8" or "advance:baseline_w8" in aliases.get(u, []))
nA, nB = STATS[("A", base_rep)]["normal_alarm"], STATS[("B", base_rep)]["normal_alarm"]
eligible_normal = [u for u in unique if STATS[("A", u)]["normal_alarm"] <= nA and STATS[("B", u)]["normal_alarm"] <= nB]
chosen, held_fn = [], {"A": 0, "B": 0}
for j in range(N_ABN):
    keep = np.arange(N_ABN) != j
    best = None
    for u in eligible_normal:
        if not all(STATS[(s, u)]["det_by_rec"][keep].all() for s in "AB"):
            continue
        key = (sum(int(STATS[(s, u)]["fn_by_rec"][keep].sum()) for s in "AB"), STATS[("A", u)]["normal_alarm"] + STATS[("B", u)]["normal_alarm"], u)
        best = key if best is None or key < best else best
    chosen.append(best[2])
    for s in "AB":
        held_fn[s] += int(STATS[(s, best[2])]["fn_by_rec"][j])
v2_rep = next(u for u in unique if u == "advance:early6_ar2" or "advance:early6_ar2" in aliases.get(u, []))
paired = {}
rng = np.random.default_rng(20260927)
for sid in D.SPLITS:
    m = MODELS[sid]
    pn, pa = PRED[sid]["pn"], PRED[sid]["pa"]
    split = SPLIT[sid]
    ref_v1 = segment_max(T.baseline(m, split["cal"]), D.segments(split["cal"]))
    a1_ = np.nan_to_num(conformal_p(ref_v1, T.baseline(m, abnormal)), nan=1.0) <= .01
    n1_ = np.nan_to_num(conformal_p(ref_v1, T.baseline(m, split["test"])), nan=1.0) <= .01
    fn2, _ = per_record(pa.alarm.to_numpy(bool), pa.record_id.to_numpy())
    fn1, _ = per_record(a1_, SEG_A)
    better, worse = int((fn2 < fn1).sum()), int((fn2 > fn1).sum())
    sign_p = float(binom.sf(better - 1, better + worse, .5))
    rows_per = pa.groupby("record_id").size().to_numpy()
    fp2, fp1 = int(pn.alarm.sum()), int(n1_.sum())
    bd = []
    for _ in range(10000):
        idx = rng.integers(0, len(fn1), len(fn1))
        nr = rows_per[idx].sum()
        b1, b2 = fn1[idx].sum(), fn2[idx].sum()
        bd.append(f1(nr - b2, fp2, b2) - f1(nr - b1, fp1, b1))
    paired[sid] = dict(better=better, equal=int((fn2 == fn1).sum()), worse=worse, sign_p=sign_p,
                       delta_f1=f1(600 - fn2.sum(), fp2, fn2.sum()) - f1(600 - fn1.sum(), fp1, fn1.sum()),
                       delta_f1_ci=[float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))], fn_v1=int(fn1.sum()), fn_v2=int(fn2.sum()))
sel_ev = pd.read_csv(Y / "analysis/press_selection/selection_evidence.csv")
RESULT["K7_selection_evidence"] = dict(candidates=len(names), unique_patterns=len(unique), eligible_patterns=len(eligible_normal),
                                       v2_pattern=v2_rep, nested=dict(chosen_counts=pd.Series(chosen).value_counts().to_dict(), held_fn=held_fn),
                                       paired=paired, selection_evidence_rows=len(sel_ev))
log("후보", len(names), "패턴", len(unique), "정상 조건 통과", len(eligible_normal), "중첩", pd.Series(chosen).value_counts().to_dict(), held_fn)
log("짝 비교", paired)


# ================================================================ K8. 통합 비교표 무임계 지표(회귀)
log("K8 통합 비교표")
uni = pd.read_csv(Y / "analysis/press_selection/unified_comparison.csv")
k8 = {}
for sid in D.SPLITS:
    m, split = MODELS[sid], SPLIT[sid]
    pn, pa = PRED[sid]["pn"], PRED[sid]["pa"]
    y = np.r_[np.zeros(len(pn)), np.ones(len(pa))]
    s2 = np.r_[pn.score.to_numpy(), pa.score.to_numpy()]
    s1 = np.r_[T.baseline(m, split["test"]), T.baseline(m, abnormal)]
    lo = np.nanmin(np.r_[s1, s2]) - 1
    s1f, s2f = np.where(np.isfinite(s1), s1, lo), np.where(np.isfinite(s2), s2, lo)

    def oracle(yv, s):
        o = np.argsort(-s, kind="mergesort")
        ys, ss = yv[o], s[o]
        tp, fp = np.cumsum(ys), np.cumsum(1 - ys)
        last = np.r_[ss[1:] != ss[:-1], True]
        tp, fp = tp[last], fp[last]
        return float((2 * tp / (2 * tp + fp + (ys.sum() - tp))).max())
    mine = dict(v2_auroc=roc_auc_score(y, s2f), v2_ap=average_precision_score(y, s2f), v1_auroc=roc_auc_score(y, s1f), v1_ap=average_precision_score(y, s1f),
                v2_oracle=oracle(y, s2f), v1_oracle=oracle(y, s1f))
    u = uni[uni.split_id.eq(sid)]
    v2row = u[u.model.str.contains("v2 최종")].iloc[0]
    v1row = u[u.model.str.contains("v1 기준선")].iloc[0]
    committed = dict(v2_auroc=float(v2row.row_auroc), v2_ap=float(v2row.row_ap), v1_auroc=float(v1row.row_auroc), v1_ap=float(v1row.row_ap),
                     v2_oracle=float(v2row.oracle_f1_rows), v1_oracle=float(v1row.oracle_f1_rows))
    k8[sid] = dict(mine=mine, committed=committed, max_abs_diff=max(abs(mine[k] - committed[k]) for k in mine))
    log(sid, {k: round(v, 4) for k, v in mine.items()}, "커밋 차 최대", k8[sid]["max_abs_diff"])
RESULT["K8_unified_table"] = k8

RESULT["elapsed_s"] = time.monotonic() - T0
OUT_JSON.write_text(json.dumps(jsonable(RESULT), ensure_ascii=False, indent=1), encoding="utf-8")
log("완료 →", OUT_JSON.name)
