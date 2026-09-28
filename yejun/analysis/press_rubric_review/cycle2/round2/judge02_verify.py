"""평가관 02 (cycle2/round2) 직접 검증 — 공식 항목 2. AI 예측모델 개발(40점). 기준 커밋 e9ed90f.

- 기준 커밋의 코드를 `git archive`로 시스템 임시 폴더에 풀어 그 코드로만 계산한다(작업 트리 코드 미사용).
- 원본: 데이터셋/프레스_유압펌프_예지보전/data/3_소성가공_예지보전/ (D.load가 SHA-256·행 수 확인).
- 쓰기: 이 파일 옆 judge02_checks.json 하나. 실행 기록은 호출 측에서 judge02_run.log로 받는다.
- 1회차(cycle2/round1/judge_02_model.md) M1~M5 완료 기준을 재계산으로 확인한다(K1~K7).
- K3b(지도학습 차이 원인)·K5(결합 규칙 대안의 주입 전이)는 평가관 계산이다. 팀 결과가 아니며 모델 재선택 근거로 쓰지 않는다.

실행(저장소 루트):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
    yejun/analysis/press_rubric_review/cycle2/round2/judge02_verify.py 2>&1 | tee yejun/analysis/press_rubric_review/cycle2/round2/judge02_run.log
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
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
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from scipy.stats import binom  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
COMMIT = os.environ.get("JUDGE_COMMIT", "e9ed90f")
DATA_DIR = REPO / "데이터셋" / "프레스_유압펌프_예지보전" / "data" / "3_소성가공_예지보전"
ROUND1 = json.loads((HERE.parent / "round1" / "judge02_checks.json").read_text(encoding="utf-8"))
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


# ---------------------------------------------------------------- 0. 기준 커밋 코드 추출
HEAD = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
BASE_COMMIT = subprocess.check_output(["git", "rev-parse", COMMIT], cwd=REPO, text=True).strip()
TMP = Path(tempfile.mkdtemp(prefix="judge02_c2r2_verify_"))
tar = subprocess.check_output(["git", "archive", "--format=tar", BASE_COMMIT, "yejun/press_guard", "yejun/press_submission", "yejun/analysis"], cwd=REPO)
tarfile.open(fileobj=io.BytesIO(tar)).extractall(TMP)
Y = TMP / "yejun"
(Y / "press_submission/data").mkdir(exist_ok=True)
(Y / "press_submission/data/3_소성가공_예지보전").symlink_to(DATA_DIR, target_is_directory=True)
RESULT["provenance"] = dict(head_at_start=HEAD, base_commit=BASE_COMMIT, head_equals_base=HEAD == BASE_COMMIT, code_extracted_to=str(TMP),
                            data_dir=str(DATA_DIR), note="기준 커밋 코드만 사용. 작업 트리 저장 모델은 해시 대조에만 읽었다.")
log("HEAD", HEAD[:7], "기준", BASE_COMMIT[:7], "→", TMP)

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
log("원본 확인", RESULT["provenance"]["input_sha256_ok"], "정상 구간", len(np.unique(SEG_N)), "이상 구간", N_ABN)


def per_record(alarm, seg):
    s = pd.DataFrame(dict(r=seg, a=np.asarray(alarm, bool)))
    g = s.groupby("r").a
    return (g.size() - g.sum()).to_numpy(int), g.any().to_numpy(bool)


def alarm_from(cal_scores, units_cal, x_scores, alpha=.01):
    p = conformal_p(segment_max(cal_scores, units_cal), x_scores)
    return np.nan_to_num(p, nan=1.0) <= alpha


# ================================================================ K1. 주 수치·경보 불변(M1 완료 기준 "경보·F1·정상 알림 불변")
log("K1 주 수치 재계산")
committed_metrics = pd.read_csv(Y / "press_guard/outputs/metrics.csv")
manifest = json.loads((Y / "press_guard/outputs/manifest.json").read_text(encoding="utf-8"))
r1_rows = {(sid, r["model"], r["alpha"]): r for sid, v in ROUND1["C1_headline_recomputed"].items() for r in v["rows"]}
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
        o = r1_rows[(sid, "guard_v2", alpha)]
        r["equals_round1_values"] = bool((tp, fp, fn, r["normal_notified"], r["abnormal_detected"]) ==
                                         (o["tp"], o["fp"], o["fn"], o["normal_notified"], o["abnormal_detected"]) and abs(r["f1"] - o["f1"]) < 1e-12)
        rows.append(r)
        if alpha == .01:
            PRED[sid] = dict(pn=pn, pa=pa)
    refit_sha = sha(art_dir / f"guard_{sid}.json")
    k1[sid] = dict(rows=rows, refit_artifact_sha256=refit_sha, manifest_artifact_sha256=manifest["artifacts"][f"guard_{sid}.json"],
                   refit_equals_manifest=refit_sha == manifest["artifacts"][f"guard_{sid}.json"])
    log(sid, [(r["alpha"], r["tp"], r["fp"], r["fn"], round(r["f1"], 6), r["equals_committed_metrics"], r["equals_round1_values"]) for r in rows],
        "저장 모델 해시 일치", k1[sid]["refit_equals_manifest"])
RESULT["K1_headline_and_alarm_invariance"] = k1


# ================================================================ K2. 이상 확률 층(M1)
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


def platt_lr_factory(s0, s1):
    x = np.r_[s0, s1]; y = np.r_[np.zeros(len(s0)), np.ones(len(s1))]
    ok = np.isfinite(x)
    m_ = LogisticRegression(C=1e6, max_iter=5000).fit(x[ok, None], y[ok])
    odds_fit = y[ok].mean() / (1 - y[ok].mean())

    def lr(s):
        q = np.clip(m_.predict_proba(np.nan_to_num(np.asarray(s, float))[:, None])[:, 1], 1e-12, 1 - 1e-12)
        return q / (1 - q) / odds_fit
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
prob_rel = pd.read_csv(Y / "press_guard/outputs/probability_reliability_v2.csv")
prob_conv = pd.read_csv(Y / "press_guard/outputs/probability_conversion_v2.csv")
wt_prob = {sid: json.loads((REPO / "yejun/press_guard/artifacts" / f"probability_{sid}.json").read_text(encoding="utf-8"))
           for sid in D.SPLITS if (REPO / "yejun/press_guard/artifacts" / f"probability_{sid}.json").exists()}
pred_out = TMP / "pred_out"
pred_out.mkdir()
k2 = {}
DEPLOY = {}
for sid in D.SPLITS:
    m, split = MODELS[sid], SPLIT[sid]
    cap = float(len(m.cal) + 1)
    deploy, oof_team = T.fit_probability(m, split["cal"], abnormal, sid, HASHES)
    deploy.save(art_dir / f"probability_{sid}.json")
    DEPLOY[sid] = deploy
    s_cal = m.predict(split["cal"]).score.to_numpy()
    pt, pa = m.predict(split["test"]), m.predict(abnormal)
    s_t, s_a = pt.score.to_numpy(), pa.score.to_numpy()
    rec_t, rec_a = pt.record_id.to_numpy(), pa.record_id.to_numpy()
    # (a) 배포 보정기: 독립 구현과 팀 구현 비교, 적합 자료 구성(정상 평가 행 미사용)
    my_deploy = iso_lr_factory(s_cal, s_a, cap)
    grid = np.linspace(np.nanmin(np.r_[s_cal, s_a, s_t]) - 1, np.nanmax(np.r_[s_cal, s_a, s_t]) + 5, 4001)
    deploy_equal = bool(np.allclose(my_deploy(grid), deploy.likelihood_ratio(grid), rtol=1e-10, atol=1e-12))
    st = deploy.state
    fit_rows_ok = bool(st["n_normal"] == int(np.isfinite(s_cal).sum()) and st["n_abnormal"] == int(np.isfinite(s_a).sum()))
    # (b) 기록 1개 빼기 교차 적합: 독립 구현 = 팀 oof
    my_oof = np.full(len(s_a), np.nan)
    ln_folds = []
    platt_a = np.full(len(s_a), np.nan); platt_n = []
    uncapped_a = np.full(len(s_a), np.nan); uncapped_n = []
    for r in np.unique(rec_a):
        keep = rec_a != r
        f_ = iso_lr_factory(s_cal, s_a[keep], cap)
        my_oof[~keep] = f_(s_a[~keep])
        ln_folds.append(f_(s_t))
        fu = iso_lr_factory(s_cal, s_a[keep], np.inf)
        uncapped_a[~keep] = fu(s_a[~keep]); uncapped_n.append(fu(s_t))
        fp_ = platt_lr_factory(s_cal, s_a[keep])
        platt_a[~keep] = fp_(s_a[~keep]); platt_n.append(fp_(s_t))
    oof_equal = bool(np.allclose(my_oof, oof_team, rtol=1e-10, atol=1e-12))
    y = np.r_[np.zeros(len(s_t)), np.ones(len(s_a))]
    pi_rows = len(s_a) / len(y)
    ln_med = np.median(ln_folds, axis=0)
    metr = {"calibrated_isotonic(21겹·정상 평가=겹 중앙)": scores_metrics(y, post(np.r_[ln_med, my_oof], pi_rows)),
            "calibrated_isotonic(예측 CSV 방식·정상 평가=배포 보정기)": scores_metrics(y, post(np.r_[deploy.likelihood_ratio(s_t), my_oof], pi_rows)),
            "isotonic_uncapped": scores_metrics(y, post(np.r_[np.median(uncapped_n, axis=0), uncapped_a], pi_rows)),
            "platt_logistic": scores_metrics(y, post(np.r_[np.median(platt_n, axis=0), platt_a], pi_rows)),
            "naive_1_minus_p": scores_metrics(y, 1 - np.r_[pt.p_value.to_numpy(), pa.p_value.to_numpy()]),
            "prevalence_only_brier": pi_rows * (1 - pi_rows)}
    ce = prob_eval[prob_eval.split.eq(sid) & prob_eval.cv.eq("21fold") & prob_eval.unit.eq("rows")].set_index("method")
    committed_cmp = {}
    for mine, theirs in (("calibrated_isotonic(21겹·정상 평가=겹 중앙)", "calibrated_isotonic"), ("isotonic_uncapped", "isotonic_uncapped"),
                         ("platt_logistic", "platt_logistic"), ("naive_1_minus_p", "naive_1_minus_p")):
        committed_cmp[theirs] = {k: dict(mine=metr[mine][k], committed=float(ce.loc[theirs, k]), abs_diff=abs(metr[mine][k] - float(ce.loc[theirs, k])))
                                 for k in ("brier", "log_loss", "ece", "auroc", "ap")}
    # 기록구간 단위(기록 최대 우도비, 기록 이상 비율)
    rl = np.r_[pd.Series(ln_med).groupby(rec_t).max().to_numpy(), pd.Series(my_oof).groupby(rec_a).max().to_numpy()]
    n_rt, n_ra = len(np.unique(rec_t)), len(np.unique(rec_a))
    yr = np.r_[np.zeros(n_rt), np.ones(n_ra)]
    pi_rec = n_ra / (n_ra + n_rt)
    rec_m = scores_metrics(yr, post(rl, pi_rec))
    cr = prob_eval[prob_eval.split.eq(sid) & prob_eval.cv.eq("21fold") & prob_eval.unit.eq("records") & prob_eval.method.eq("calibrated_isotonic")].iloc[0]
    # (c) 문턱 점수의 우도비와 그 등방 블록 구성
    thr = float(np.max(m.cal))
    lr_thr = float(deploy.likelihood_ratio([thr + 1e-9])[0])
    iso = my_deploy.iso
    x_all = np.r_[s_cal[np.isfinite(s_cal)], s_a[np.isfinite(s_a)]]
    lab = np.r_[np.zeros(int(np.isfinite(s_cal).sum())), np.ones(int(np.isfinite(s_a).sum()))]
    v_thr = float(iso.predict([thr + 1e-9])[0])
    Xth, Yth = iso.X_thresholds_, iso.y_thresholds_
    i_th = int(np.searchsorted(Xth, thr + 1e-9, side="right") - 1)
    pred_all = iso.predict(x_all)

    def blk_info(yv):
        b = np.isclose(pred_all, yv, rtol=0, atol=1e-12)
        return dict(fitted_p=float(yv), lr=(float(yv / (1 - yv) / my_deploy.odds_fit) if 0 < yv < 1 else None),
                    score_range=([float(x_all[b].min()), float(x_all[b].max())] if b.any() else None),
                    normal_cal_rows=int((b & (lab == 0)).sum()), abnormal_rows=int((b & (lab == 1)).sum()))
    near = np.abs(x_all - thr) <= .25
    block = dict(fitted_p_at_threshold=v_thr, pi_fit=float(lab.mean()),
                 between_thresholds=[float(Xth[i_th]), float(Xth[min(i_th + 1, len(Xth) - 1)])],
                 left_block=blk_info(Yth[i_th]), right_block=blk_info(Yth[min(i_th + 1, len(Yth) - 1)]),
                 rows_within_0_25_of_threshold=dict(normal_cal=int((near & (lab == 0)).sum()), abnormal=int((near & (lab == 1)).sum())),
                 normal_cal_rows_above_threshold_minus_0_5=int(((x_all >= thr - .5) & (lab == 0)).sum()))
    cc = prob_conv[prob_conv.split.eq(sid) & np.isclose(prob_conv.prior, .01)].iloc[0]
    # 경보 행 중 우도비 < 1(π와 상관없이 확률 < 사전 비율)인 행 수: 정상 평가(배포 보정기), 이상(교차 적합)
    al_t = pt.p_value.to_numpy() <= .01
    al_a = pa.p_value.to_numpy() <= .01
    lr_t_dep = deploy.likelihood_ratio(s_t)
    below = dict(normal_alarm_rows=int(al_t.sum()), normal_alarm_rows_lr_lt_1=int((al_t & (lr_t_dep < 1)).sum()),
                 abnormal_alarm_rows=int(al_a.sum()), abnormal_alarm_rows_lr_lt_1=int((al_a & (my_oof < 1)).sum()),
                 abnormal_alarm_rows_lr_lt_1_deploy=int((al_a & (deploy.likelihood_ratio(s_a) < 1)).sum()))
    lr_alarm = np.r_[lr_t_dep[al_t], my_oof[al_a]]
    below.update(min_lr_alarm_rows=float(lr_alarm.min()), min_p_pi1_alarm_rows=float(post(lr_alarm.min(), .01)),
                 alarm_rows_lr_below_10=int((lr_alarm < 10).sum()), alarm_rows_total=int(len(lr_alarm)),
                 normal_alarm_rows_lr=[float(x) for x in lr_t_dep[al_t]])
    # (d) 예측 CSV: 팀 train.evaluate_pair로 임시 폴더에 생성 → 열·F1·확률 출처·경보 불변
    m_prob = GuardModel(m.state).attach_probability(PR.ProbabilityCalibrator.load(art_dir / f"probability_{sid}.json"))
    T.evaluate_pair(m_prob, split["cal"], split["test"], abnormal, sid, pred_out, oof_lr=oof_team)
    tpf = pd.read_csv(pred_out / f"test_predictions_{sid}.csv")
    tp_, fp_, fn_ = int(((tpf.alarm == 1) & (tpf.label == 1)).sum()), int(((tpf.alarm == 1) & (tpf.label == 0)).sum()), int(((tpf.alarm == 0) & (tpf.label == 1)).sum())
    ab, no = tpf[tpf.label.eq(1)], tpf[tpf.label.eq(0)]
    no_prob = GuardModel(m.state)
    alarm_same = bool(np.array_equal(no_prob.predict(abnormal, .01).alarm.to_numpy(), ab.alarm.to_numpy())
                      and np.array_equal(no_prob.predict(split["test"], .01).alarm.to_numpy(), no.alarm.to_numpy()))
    file_checks = dict(columns=[c for c in tpf.columns if "prob" in c or "likelihood" in c], rows=len(tpf), f1=f1(tp_, fp_, fn_),
                       abnormal_lr_equals_my_oof=bool(np.allclose(ab.likelihood_ratio.to_numpy(), my_oof, rtol=1e-10)),
                       normal_lr_equals_my_deploy=bool(np.allclose(no.likelihood_ratio.to_numpy(), my_deploy(no.score.to_numpy()), rtol=1e-10)),
                       prob_equals_posterior_pi1=bool(np.allclose(tpf.anomaly_probability, post(tpf.likelihood_ratio, .01), rtol=1e-12)),
                       prior_values=sorted(tpf.probability_prior.unique().tolist()),
                       sources=tpf.groupby("subset").probability_source.unique().apply(list).to_dict(),
                       alarm_equals_without_probability=alarm_same,
                       # 파일의 확률 열(π=1%)을 그대로 대회 라벨에 채점하면: 사전 비율이 대회 비율과 달라 보정이 어긋난다(설계상)
                       file_prob_pi1_metrics=scores_metrics(tpf.label.to_numpy(float), tpf.anomaly_probability.to_numpy()),
                       file_prob_converted_to_file_prevalence=scores_metrics(tpf.label.to_numpy(float), post(tpf.likelihood_ratio.to_numpy(), tpf.label.mean())),
                       my_file_sha256=sha(pred_out / f"test_predictions_{sid}.csv"),
                       abnormal_prob_pi1_max=float(ab.anomaly_probability.max()), abnormal_prob_pi1_median=float(ab.anomaly_probability.median()),
                       abnormal_rows_lr_at_cap=int(np.isclose(ab.likelihood_ratio.to_numpy(), cap).sum()),
                       normal_rows_prob_pi1_max=float(no.anomaly_probability.max()))
    # (e) 단조성·사전 비율 변환·상한
    s_grid = np.linspace(-2, 40, 400)
    lrg = deploy.likelihood_ratio(s_grid)
    mono = dict(lr_nondecreasing=bool(np.all(np.diff(lrg) >= -1e-12)), lr_max=float(lrg.max()), lr_min=float(lrg.min()), cap=cap,
                prob_increasing_in_prior=bool(np.all(deploy.probability(s_grid, .1) >= deploy.probability(s_grid, .001))),
                posterior_odds_identity=bool(np.allclose(post(lrg, .01) / (1 - post(lrg, .01)), lrg * .01 / .99)))
    wt = wt_prob.get(sid)
    k2[sid] = dict(
        deploy_equals_independent=deploy_equal, fit_rows_are_calibration_plus_abnormal=fit_rows_ok,
        deploy_state=dict(n_normal=st["n_normal"], n_abnormal=st["n_abnormal"], pi_fit=st["pi_fit"], lr_cap=st["lr_cap"], lr_floor=st["lr_floor"]),
        deploy_sha256_refit=sha(art_dir / f"probability_{sid}.json"), deploy_sha256_manifest=manifest["artifacts"][f"probability_{sid}.json"],
        deploy_thresholds_equal_working_tree=(None if wt is None else bool(wt["state"]["thresholds_x"] == st["thresholds_x"] and wt["state"]["thresholds_y"] == st["thresholds_y"])),
        loo_equals_team_oof=oof_equal, pi_rows=pi_rows, metrics_rows=metr, committed_vs_mine=committed_cmp,
        records=dict(mine=rec_m, committed=dict(brier=float(cr.brier), ece=float(cr.ece), log_loss=float(cr.log_loss)), pi_rec=pi_rec),
        threshold=dict(score=thr, lr=lr_thr, committed_lr=float(cc.lr_at_threshold), p_pi1=float(post(lr_thr, .01)), committed_p_pi1=float(cc.p_at_threshold),
                       isotonic_block_at_threshold=block),
        alarm_rows_with_lr_below_1=below, prediction_file=file_checks, monotone_prior=mono)
    log(sid, "배포=독립", deploy_equal, "LOO=독립", oof_equal, "Brier(21겹)", round(metr["calibrated_isotonic(21겹·정상 평가=겹 중앙)"]["brier"], 5),
        "ECE", round(metr["calibrated_isotonic(21겹·정상 평가=겹 중앙)"]["ece"], 5), "문턱 LR", round(lr_thr, 3), "블록", block, "LR<1 경보행", below)
    log(sid, "예측 파일", {k: v for k, v in file_checks.items() if k not in ("file_prob_pi1_metrics", "file_prob_converted_to_file_prevalence")})
    log(sid, "파일 확률(π=1%) 채점", {k: round(v, 4) for k, v in file_checks["file_prob_pi1_metrics"].items()},
        "대회 비율 환산", {k: round(v, 4) for k, v in file_checks["file_prob_converted_to_file_prevalence"].items()})
# 라벨 없는 환산(최소 베이즈 인수, 알림 우도비 상한)
sbb = 1 / PR.sellke_bayes_factor(1 / 121)
RESULT["K2_probability_layer"] = dict(per_split=k2, sbb_lr_bound=sbb, sbb_p_pi1=float(post(sbb, .01)), alert_lr_cap=121.0, alert_p_pi1=float(post(121, .01)),
                                      model_py_doc_line4=(Y / "press_guard/model.py").read_text(encoding="utf-8").splitlines()[3])


# ================================================================ K3. 지도학습 기준선(M2): 팀 표 대조 + 1회차 값과의 차이 원인
log("K3 지도학습 기준선")
sup = load_module("j02_sup", Y / "analysis/press_supervised/run.py")
gr = pd.read_csv(Y / "analysis/press_supervised/grouped_records.csv")
inj = pd.read_csv(Y / "analysis/press_supervised/injection.csv")
readme_sup = (Y / "analysis/press_supervised/README.md").read_text(encoding="utf-8")


def judge_features(frame, m):
    """1회차 평가관 특징(round1 judge02_verify.py features와 같은 식)."""
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
    """이상 기록 1개 빼기 21겹, 문턱 = 정상 보정 기록구간 최대 확률(p > 문턱이면 경보). 정상 평가는 이상 전체로 학습한 모델."""
    fn, per_fold = 0, []
    for j in range(N_ABN):
        keep = SEG_A != j
        clf = make().fit(np.r_[Xn, Xa[keep]], np.r_[np.zeros(len(Xn)), np.ones(int(keep.sum()))])
        thr = float(pd.Series(clf.predict_proba(Xc)[:, 1]).groupby(seg_cal).max().max())
        pj = clf.predict_proba(Xa[~keep])[:, 1]
        miss = int((pj <= thr).sum())
        fn += miss
        per_fold.append(dict(record=j, rows=int((~keep).sum()), threshold=thr, fn=miss, held_p_median=float(np.median(pj))))
    clf = make().fit(np.r_[Xn, Xa], np.r_[np.zeros(len(Xn)), np.ones(len(Xa))])
    thr = float(pd.Series(clf.predict_proba(Xc)[:, 1]).groupby(seg_cal).max().max())
    al = clf.predict_proba(Xt)[:, 1] > thr
    fp = int(al.sum())
    return dict(fn=fn, fp=fp, f1=f1(600 - fn, fp, fn), normal_alerted=int(pd.Series(al).groupby(seg_test).any().sum()),
                detected=int(sum(1 for r in per_fold if r["fn"] < r["rows"])), per_fold=per_fold)


k3 = dict(committed_21fold_conformal={}, diagnosis={})
for sid in D.SPLITS:
    m, split = MODELS[sid], SPLIT[sid]
    seg_cal, seg_test = D.segments(split["cal"]), D.segments(split["test"])
    g = gr[gr.split.eq(sid) & gr.cv.eq("21fold") & gr.threshold.eq("conformal")]
    k3["committed_21fold_conformal"][sid] = g[["features", "model", "fn", "fp", "f1", "normal_alerted_segments", "abnormal_detected_segments"]].to_dict("records")
    diag = {}
    # 팀 특징(창+v2 성분) 부스팅: 겹별 문턱
    Fn, Fc, Ft, Fa = (sup.features(f, "window_plus_v2", m).to_numpy(float) for f in (split["train"], split["cal"], split["test"], abnormal))
    t0 = time.monotonic()
    team_hgb = loso(sup.MODELS["hgb"], Fn, Fc, Ft, Fa, seg_cal, seg_test)
    team_hgb3 = []
    for hold in sup.FOLDS["3fold"]:
        keep = ~np.isin(SEG_A, hold)
        clf = sup.MODELS["hgb"]().fit(np.r_[Fn, Fa[keep]], np.r_[np.zeros(len(Fn)), np.ones(int(keep.sum()))])
        thr = float(pd.Series(clf.predict_proba(Fc)[:, 1]).groupby(seg_cal).max().max())
        team_hgb3.append(dict(hold=hold.tolist(), threshold=thr, fn=int((clf.predict_proba(Fa[~keep])[:, 1] <= thr).sum())))
    committed_team = g[g.features.eq("window_plus_v2") & g.model.eq("hgb")].iloc[0]
    diag["team_window_plus_v2_hgb"] = dict(fn=team_hgb["fn"], committed_fn=int(committed_team.fn), f1=team_hgb["f1"], detected=team_hgb["detected"],
                                           thresholds=[r["threshold"] for r in team_hgb["per_fold"]], fn_by_fold=[r["fn"] for r in team_hgb["per_fold"]],
                                           rows_by_fold=[r["rows"] for r in team_hgb["per_fold"]], three_fold=team_hgb3)
    log(sid, "팀 특징 부스팅 21겹", team_hgb["fn"], "커밋", int(committed_team.fn), "문턱 범위",
        (round(min(diag["team_window_plus_v2_hgb"]["thresholds"]), 6), round(max(diag["team_window_plus_v2_hgb"]["thresholds"]), 6)),
        "겹별 미탐", diag["team_window_plus_v2_hgb"]["fn_by_fold"], f"{time.monotonic() - t0:.0f}s")
    # 1회차 평가관 특징: 가중·비가중 × 로지스틱·부스팅(1회차 값 재현과 가중치 효과 분리)
    Jn, Jc, Jt, Ja = (judge_features(f, m) for f in (split["train"], split["cal"], split["test"], abnormal))
    for kind in ("logistic", "hgb"):
        for bal in (True, False):
            r = loso(lambda: judge_clf(kind, bal), Jn, Jc, Jt, Ja, seg_cal, seg_test)
            key = f"judge_features:{kind}:{'balanced' if bal else 'unweighted'}"
            diag[key] = dict(fn=r["fn"], fp=r["fp"], f1=r["f1"], normal_alerted=r["normal_alerted"], detected=r["detected"],
                             threshold_min=min(x["threshold"] for x in r["per_fold"]), threshold_max=max(x["threshold"] for x in r["per_fold"]),
                             fn_by_fold=[x["fn"] for x in r["per_fold"]])
            log(sid, key, (r["fn"], r["fp"], round(r["f1"], 4), r["normal_alerted"], r["detected"]))
    k3["diagnosis"][sid] = diag
k3["round1_judge_values"] = {sid: {k: ROUND1["C8_supervised_baseline_check"]["results"][sid][f"signal_matched:{k}"]["f1_conformal"] for k in ("logistic", "hgb")} for sid in D.SPLITS}
k3["readme_mentions_difference_reason"] = dict(
    mentions_round1_values=any(s in readme_sup for s in ("0.960", "0.957", "0.971·", "0.967")),
    mentions_threshold_instability=any(s in readme_sup for s in ("불안정", "포화", "saturat")))
inj_conf = inj[inj.threshold.eq("conformal")]
k3["injection_vib2_4"] = inj_conf[inj_conf.family.eq("vib_noise") & inj_conf.level.isin([2.0, 4.0])][["split", "features", "model", "level", "detect_rate_2s", "v2_detect_rate_2s"]].to_dict("records")
RESULT["K3_supervised"] = k3


# ================================================================ K4. 같은 특징 대안·결합 규칙(M3·O3) 독립 재계산
log("K4 같은 특징 대안·결합 규칙")
ear = load_module("j02_ear", Y / "analysis/press_early/run_experiment.py")
alts_c = pd.read_csv(Y / "analysis/press_selection/same_feature_alternatives.csv")
rules_c = pd.read_csv(Y / "analysis/press_selection/combination_rules.csv")


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
k4 = {}
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
        v2_thr_p = {k: np.nan_to_num(conformal_p(m.cal, P[k]["comp"]["score"]), nan=1.0) <= alpha for k in ("test", "abn")}   # 어떤 성분이 단독으로 v2 문턱을 넘는가
        for name, s in cands.items():
            at = alarm_from(s["cal"], P["cal"]["units"], s["test"], alpha)
            aa = alarm_from(s["cal"], P["cal"]["units"], s["abn"], alpha)
            fnr, det = per_record(aa, P["abn"]["seg"])
            tp, fp = int(aa.sum()), int(at.sum())
            rows.append(dict(alpha=alpha, candidate=name, tp=tp, fp=fp, fn=len(aa) - tp, f1=f1(tp, fp, len(aa) - tp),
                             normal_alerted=int(pd.Series(at).groupby(P["test"]["seg"]).any().sum()), detected=int(det.sum()),
                             no_evidence_abn=int((aa & ~v2_thr_p["abn"]).sum()), no_evidence_normal=int((at & ~v2_thr_p["test"]).sum())))
    df = pd.DataFrame(rows)
    # 커밋 표와 대조
    name_map_alt = {"v2": "v2 (fmax, AR(2))", "5NN(v2 성분)": "5NN(v2 성분)", "IF(v2 성분)": "IF(v2 성분)", "sum": "합(v2 성분)",
                    "early+AR(1)": "early+AR(1)", "early+AR(3)": "early+AR(3)", "early+AR(4)": "early+AR(4)"}
    mism = []
    for r in df.itertuples():
        if r.candidate in name_map_alt:
            c = alts_c[alts_c.split_id.eq(sid) & np.isclose(alts_c.alpha, r.alpha) & alts_c.candidate.eq(name_map_alt[r.candidate])]
            ok = len(c) == 1 and (c.iloc[0].tp, c.iloc[0].fp, c.iloc[0].fn, c.iloc[0].normal_alerted, c.iloc[0].abnormal_detected) == (r.tp, r.fp, r.fn, r.normal_alerted, r.detected)
            ok_ne = len(c) == 1 and r.candidate in ("5NN(v2 성분)", "IF(v2 성분)", "sum", "v2") and (c.iloc[0].no_evidence_alarms_abnormal == r.no_evidence_abn)
            if not ok:
                mism.append(("alt", r.alpha, r.candidate))
            if r.candidate in ("5NN(v2 성분)", "IF(v2 성분)", "sum", "v2") and not ok_ne:
                mism.append(("alt_no_evidence", r.alpha, r.candidate))
        if r.candidate in ("fisher", "stouffer", "sum", "mean"):
            c = rules_c[rules_c.split_id.eq(sid) & np.isclose(rules_c.alpha, r.alpha) & rules_c.rule.eq(r.candidate)]
            ok = len(c) == 1 and (c.iloc[0].tp, c.iloc[0].fp, c.iloc[0].fn, c.iloc[0].normal_alerted, c.iloc[0].no_evidence_alarms_abnormal,
                                  c.iloc[0].no_evidence_alarms_normal) == (r.tp, r.fp, r.fn, r.normal_alerted, r.no_evidence_abn, r.no_evidence_normal)
            if not ok:
                mism.append(("rule", r.alpha, r.candidate))
    k4[sid] = dict(rows=df.to_dict("records"), mismatches_vs_committed=mism)
    log(sid, "불일치", mism)
    log(sid, df[df.alpha.eq(.01)][["candidate", "tp", "fp", "fn", "normal_alerted", "detected", "no_evidence_abn"]].to_string(index=False))
RESULT["K4_same_feature_and_rules"] = k4


# ================================================================ K5. 결합 규칙 대안의 주입 전이(평가관 계산, 채택 근거 아님)
log("K5 결합 규칙 대안의 주입 전이")
selm = load_module("j02_sel", Y / "analysis/press_selection/run.py")
fpinj_c = pd.read_csv(Y / "analysis/press_selection/fp_mitigation_injection_v2.csv")
k5 = {}
for sid in D.SPLITS:
    m, split, P = MODELS[sid], SPLIT[sid], CTX[sid]
    test = split["test"]
    units, in_unit, size = R.unit_layout(test)
    eligible = size >= R.MIN_UNIT_ROWS
    window = (in_unit >= R.T0) & (in_unit < R.T0 + R.WINDOW)
    mats_tr = np.nan_to_num(P["train"]["g"], nan=0.0)
    nn5 = NearestNeighbors(n_neighbors=5).fit(mats_tr)

    def rule_scores(comp):
        g = np.column_stack([comp["g_magnitude"], comp["g_waveform"], comp["g_dynamics"]])
        fu = my_fusions(g)
        return {"v2_fmax": comp["score"], "fisher": fu["fisher"], "stouffer": fu["stouffer"], "sum": fu["sum"],
                "5nn": nn5.kneighbors(np.nan_to_num(g, nan=0.0))[0].mean(1)}
    cal_scores = rule_scores(P["cal"]["comp"])
    cals = {k: segment_max(v, P["cal"]["units"]) for k, v in cal_scores.items()}
    assert np.array_equal(cals["v2_fmax"], m.cal)
    out = []
    for family, level in selm.INJ_FAMILIES:
        reps = selm.INJ_REPS if family in ("cur_noise", "vib_noise", "vib_shock") else 1
        hits = {k: [] for k in cals}
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
                alarm = np.nan_to_num(conformal_p(cals[k_], s_), nan=1.0) <= .01
                hit = alarm & window & eligible
                hits[k_].append(pd.Series(hit[eligible]).groupby(units[eligible]).any().to_numpy())
        row = dict(family=family, level=level, reps=reps, units=int(pd.Series(units[eligible]).nunique()))
        for k_ in cals:
            row[k_] = float(np.concatenate(hits[k_]).mean())
        c = fpinj_c[fpinj_c.split_id.eq(sid) & np.isclose(fpinj_c.alpha, .01) & fpinj_c.family.eq(family) & np.isclose(fpinj_c.level, level)]
        row["committed_v2"] = float(c.v2_detect_2s.iloc[0]) if len(c) else None
        out.append(row)
        log(sid, family, level, {k: round(v, 3) for k, v in row.items() if isinstance(v, float)})
    k5[sid] = out
RESULT["K5_rule_transfer_injection"] = dict(results=k5, note="α=1%, 주입은 press_guard/recalibrate.inject·press_selection.vib_shock(팀 코드)와 같은 방식·난수. "
                                                       "대안은 각자 정상 보정 최대로 재보정. 평가관 계산이며 채택 근거가 아니다.")


# ================================================================ K6. 선정 근거(M4): 후보 재계산·중첩 선택·짝 비교·장부·사전 커밋
log("K6 선정 근거")
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
v2_rep = next(u for u in unique if u == "advance:early6_ar2" or "advance:early6_ar2" in aliases.get(u, []))
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
nested_c = pd.read_csv(Y / "analysis/press_selection/nested_selection.csv")
cand_c = pd.read_csv(Y / "analysis/press_selection/candidate_universe.csv")
paired = {}
rng = np.random.default_rng(20260927)
for sid in D.SPLITS:
    m = MODELS[sid]
    pn, pa = PRED[sid]["pn"], PRED[sid]["pa"]
    split = SPLIT[sid]
    ref_v1 = segment_max(T.baseline(m, split["cal"]), D.segments(split["cal"]))
    a1 = np.nan_to_num(conformal_p(ref_v1, T.baseline(m, abnormal)), nan=1.0) <= .01
    n1 = np.nan_to_num(conformal_p(ref_v1, T.baseline(m, split["test"])), nan=1.0) <= .01
    fn2, _ = per_record(pa.alarm.to_numpy(bool), pa.record_id.to_numpy())
    fn1, _ = per_record(a1, SEG_A)
    better, worse = int((fn2 < fn1).sum()), int((fn2 > fn1).sum())
    sign_p = float(binom.sf(better - 1, better + worse, .5))
    rows_per = pa.groupby("record_id").size().to_numpy()
    fp2, fp1 = int(pn.alarm.sum()), int(n1.sum())
    bd = []
    for _ in range(10000):
        idx = rng.integers(0, len(fn1), len(fn1))
        nr = rows_per[idx].sum()
        b1, b2 = fn1[idx].sum(), fn2[idx].sum()
        bd.append(f1(nr - b2, fp2, b2) - f1(nr - b1, fp1, b1))
    paired[sid] = dict(better=better, equal=int((fn2 == fn1).sum()), worse=worse, sign_p=sign_p,
                       delta_f1=f1(600 - fn2.sum(), fp2, fn2.sum()) - f1(600 - fn1.sum(), fp1, fn1.sum()),
                       delta_f1_ci=[float(np.percentile(bd, 2.5)), float(np.percentile(bd, 97.5))], fn_v1=int(fn1.sum()), fn_v2=int(fn2.sum()))
ledger = pd.read_csv(Y / "analysis/press_selection/search_ledger.csv")
ledger_recount = {}
for r in ledger.itertuples():
    p = Y.parent / r.source
    if p.suffix == ".csv":
        t = pd.read_csv(p)
        col = "ablation" if r.source.endswith("press_submission/outputs/ablation.csv") else "model"
        ledger_recount[r.stage] = dict(committed=int(r.rules), recount=int(t[col].nunique()), names_equal=sorted(t[col].unique().tolist()) == sorted(r.names.split()))
    else:
        ledger_recount[r.stage] = dict(committed=int(r.rules), recount=1, names_equal=True)
git_first = {}
for p in ["yejun/analysis/press_advance/protocol.json", "yejun/analysis/press_advance/metrics.csv", "yejun/analysis/press_improvement/config.json",
          "yejun/analysis/press_improvement/candidate_metrics.csv", "yejun/analysis/press_early/protocol.json", "yejun/analysis/press_early/metrics.csv",
          "yejun/analysis/press_supplement/protocol.json", "yejun/analysis/press_supplement/e1_summary.csv", "yejun/press_submission/PLAN.md",
          "yejun/press_submission/outputs/sensitivity.csv"]:
    git_first[p] = subprocess.check_output(["git", "log", "--diff-filter=A", "--format=%h %ad", "--date=iso", BASE_COMMIT, "--", p], cwd=REPO, text=True).strip().splitlines()[-1:]
RESULT["K6_selection_evidence"] = dict(
    candidates=len(names), unique_patterns=len(unique), eligible_patterns=len(eligible_normal),
    nested=dict(chosen_counts=pd.Series(chosen).value_counts().to_dict(), held_fn=held_fn,
                committed_all_v2=bool(nested_c.chosen_is_v2.all()), committed_held_fn=dict(A=int(nested_c.held_out_fn_A.sum()), B=int(nested_c.held_out_fn_B.sum()))),
    candidate_table_matches=dict(committed_rows=len(cand_c), committed_match_flag=(cand_c["matches_committed"].value_counts().to_dict() if "matches_committed" in cand_c else None)),
    paired=paired, ledger_total_committed=int(ledger.rules.sum()), ledger_recount=ledger_recount, git_first_add=git_first)
log("후보", len(names), "패턴", len(unique), "정상 조건 통과", len(eligible_normal), "중첩", pd.Series(chosen).value_counts().to_dict(), held_fn)
log("짝 비교", paired)
log("장부 합", int(ledger.rules.sum()), {k: (v["committed"], v["recount"], v["names_equal"]) for k, v in ledger_recount.items()})


# ================================================================ K7. 통합 비교표(M5) 무임계 지표 대조
log("K7 통합 비교표")
uni = pd.read_csv(Y / "analysis/press_selection/unified_comparison.csv")
k7 = {}
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
    cols = [c for c in u.columns]
    v2row = u[u.model.str.contains("v2 최종")].iloc[0]
    v1row = u[u.model.str.contains("v1 기준선")].iloc[0]
    k7[sid] = dict(mine=mine, columns=cols,
                   committed=dict(v2_auroc=float(v2row.row_auroc), v2_ap=float(v2row.row_ap), v1_auroc=float(v1row.row_auroc), v1_ap=float(v1row.row_ap),
                                  v2_oracle=float(v2row.oracle_f1_rows), v1_oracle=float(v1row.oracle_f1_rows), v2_record_f1=float(v2row.record_f1),
                                  v1_record_f1=float(v1row.record_f1)),
                   round1_c6=ROUND1["C6_threshold_free"][sid])
    log(sid, {k: round(v, 4) for k, v in mine.items()}, "커밋", {k: round(v, 4) for k, v in k7[sid]["committed"].items()})
RESULT["K7_unified_table"] = k7

RESULT["elapsed_s"] = time.monotonic() - T0
OUT_JSON.write_text(json.dumps(jsonable(RESULT), ensure_ascii=False, indent=1), encoding="utf-8")
log("완료 →", OUT_JSON.name)
