"""X-04 재검수: 동결 예측을 읽어 평가 비율을 명시한 손실을 계산한다.

제품 코드/동결 결과는 쓰지 않는다. 출력은 이 검수 폴더의 JSON/CSV뿐이다.
분류별 분포를 그대로 두고 비율만 바꾸는 계산은 label-shift 시나리오이며
새 현장 자료의 성능 추정/검증이 아니다. 신뢰구간이나 새 점수를 만들지 않는다.

실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
  yejun/analysis/press_rubric_review/cycle2/recheck_20260929/probability_review.py
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
GUARD = REPO / "yejun/press_guard"
sys.path[:0] = [str(GUARD), str(REPO / "yejun/press_submission")]


def posterior(lr, pi):
    return pi * lr / (1 - pi + pi * lr)


def two_level_lr(sid, frame):
    """경보 0/1을 두 개의 교차 적합 확률로 바꾸는 별도 기준선.

    정상 평가 라벨은 적합하지 않고 정상 보정 구간만 쓴다. 이상은 기록별
    leave-one-record-out이다. 각 확률의 0 방지를 위해 Jeffreys 반개 보정을 쓴다.
    이 기준선과 0/1 자체를 확률로 해석한 기준선을 분리한다.
    """
    from model import load_bundle

    normal_path = REPO / "yejun/press_submission/data/3_소성가공_예지보전/press_data_normal.csv"
    raw = pd.read_csv(normal_path)
    gap = pd.to_datetime(raw.TimeStamp).diff().dt.total_seconds()
    record = (gap.sub(.1).abs().gt(1e-6)).cumsum()
    lo, hi = {"A": (360, 480), "B": (300, 420)}[sid]
    calibration = raw.loc[record.ge(lo) & record.lt(hi)].reset_index(drop=True)
    model_path = GUARD / "artifacts" / f"guard_{sid}.json"
    model = load_bundle(model_path)
    calibration_alarm = model.predict(calibration).alarm.to_numpy(dtype=int)
    yn = frame.label.eq(0).to_numpy()
    ya = ~yn
    ar = frame.loc[ya, "record_id"].to_numpy(dtype=int)
    aa = frame.loc[ya, "alarm"].to_numpy(dtype=int)
    na = frame.loc[yn, "alarm"].to_numpy(dtype=int)
    abnormal_lr = np.empty(len(aa))
    normal_lrs = []
    p0 = np.array([(np.count_nonzero(calibration_alarm == k) + .5) /
                   (len(calibration_alarm) + 1) for k in (0, 1)])
    for held in np.unique(ar):
        train = aa[ar != held]
        p1 = np.array([(np.count_nonzero(train == k) + .5) / (len(train) + 1)
                       for k in (0, 1)])
        ratio = p1 / p0
        abnormal_lr[ar == held] = ratio[aa[ar == held]]
        normal_lrs.append(ratio[na])
    result = np.empty(len(frame))
    result[yn] = np.median(normal_lrs, axis=0)
    result[ya] = abnormal_lr
    return result, dict(model_sha256=sha(model_path), raw_normal_sha256=sha(normal_path),
                        calibration_rows=len(calibration), calibration_alarm_rows=int(calibration_alarm.sum()),
                        crossfit="leave_one_abnormal_record_out; normal heldout predictions use median LR",
                        smoothing="Jeffreys 0.5 in each of two outcomes")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def losses(y, q, evaluation_prior):
    """R_pi = (1-pi) mean(loss | normal) + pi mean(loss | abnormal)."""
    y = np.asarray(y, dtype=int)
    q = np.asarray(q, dtype=float)
    assert np.isfinite(q).all() and ((0 <= q) & (q <= 1)).all()
    n0, n1 = int((y == 0).sum()), int((y == 1).sum())
    w = np.where(y == 1, evaluation_prior / n1, (1 - evaluation_prior) / n0)
    assert np.isclose(w.sum(), 1.0)
    brier = np.square(q - y)
    safe = np.clip(q, 1e-9, 1 - 1e-9)
    logloss = -(y * np.log(safe) + (1 - y) * np.log1p(-safe))
    bins = np.minimum((q * 10).astype(int), 9)
    ece = 0.0
    for b in np.unique(bins):
        k = bins == b
        ece += abs(float(np.sum(w[k] * (q[k] - y[k]))))
    return dict(brier=float(w @ brier), log_loss=float(w @ logloss),
                ece10=float(ece), brier_normal=float(brier[y == 0].mean()),
                brier_abnormal=float(brier[y == 1].mean()))


def main():
    rows, details = [], {}
    for sid in ("A", "B"):
        path = GUARD / "outputs" / f"test_predictions_{sid}.csv"
        f = pd.read_csv(path)
        y = f.label.to_numpy(dtype=int)
        observed_prior = float(y.mean())
        p_deploy = f.anomaly_probability.to_numpy(dtype=float)
        p_file = f.anomaly_probability_file_prior.to_numpy(dtype=float)
        lr = f.likelihood_ratio.to_numpy(dtype=float)
        assert np.allclose(p_deploy, .01 * lr / (.99 + .01 * lr), atol=1e-14, rtol=0)
        assert np.allclose(p_file, observed_prior * lr / (1 - observed_prior + observed_prior * lr), atol=1e-14, rtol=0)
        methods = {
            "isotonic_prior_0.01": p_deploy,
            "isotonic_prior_file": p_file,
            "one_minus_p_not_probability": 1 - f.p_value.to_numpy(dtype=float),
            "hard_alarm_0_1_not_calibrated": f.alarm.to_numpy(dtype=float),
            "constant_0.01": np.full(len(y), .01),
            "constant_file_prior": np.full(len(y), observed_prior),
        }
        lr2, baseline_meta = two_level_lr(sid, f)
        for prior_label, pi in (("0.01", .01), ("file", observed_prior)):
            methods[f"two_level_crossfit_uncapped_prior_{prior_label}"] = posterior(lr2, pi)
            methods[f"two_level_crossfit_cap121_prior_{prior_label}"] = posterior(np.minimum(lr2, 121), pi)
        for target, pi in (("observed_file", observed_prior), ("prior_0.01_label_shift_scenario", .01)):
            for name, q in methods.items():
                result = losses(y, q, pi)
                if target == "observed_file":
                    # A pure identity check independently guards weight normalization.
                    assert abs(result["brier"] - float(np.mean((q - y) ** 2))) < 1e-14
                rows.append(dict(split=sid, evaluation_distribution=target,
                                 evaluation_prior=pi, prediction=name, **result))
        alarm = f.alarm.eq(1).to_numpy()
        details[sid] = dict(input=str(path.relative_to(REPO)), input_sha256=sha(path),
                            rows=len(f), normal_rows=int((y == 0).sum()), abnormal_rows=int((y == 1).sum()),
                            observed_file_prior=observed_prior, alarm_rows=int(alarm.sum()),
                            alarm_rows_at_0_55=int(np.isclose(p_deploy[alarm], .55, atol=1e-12, rtol=0).sum()),
                            distinct_lr=int(np.unique(np.round(lr, 9)).size),
                            constant_prior_identity=.01 * .99,
                            two_level_baseline=baseline_meta)
    out = dict(review_target="be0c8b224f1fe4732056ff7979b798abc9153567",
               product_commit="cc1aac2e24f4ed9f954b0f7b76db06021be02afd",
               executed_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
               environment=dict(python=platform.python_version(), platform=platform.platform(),
                                numpy=np.__version__, pandas=pd.__version__),
               formula="(1-pi_eval)*mean(loss|normal) + pi_eval*mean(loss|abnormal)",
               caveat="동일한 두 파일의 클래스 조건부 분포가 유지된다는 가정의 재가중 계산이다. 실제 현장 검증이 아니다. 0/1과 1-p는 확률 모형이 아니다.",
               inputs=details, results=rows)
    (HERE / "probability_review.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(HERE / "probability_review.csv", index=False)
    print(pd.DataFrame(rows)[["split", "evaluation_distribution", "prediction", "brier", "log_loss", "ece10"]].to_string(index=False))
    print(json.dumps(details, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
