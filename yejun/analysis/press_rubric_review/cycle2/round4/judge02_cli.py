"""평가관02 R3-M2: 실제 정상 재보정 → 두 prior CLI·모의운용·감시 확인.

judge02_verify.py가 만든 시스템 임시 사본만 실행한다. 원본 데이터는 읽기 전용이고
이 파일 옆 judge02_cli.json·호출 측 judge02_cli.log 외의 결과는 모두 임시 폴더에 둔다.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
evidence = json.loads((HERE / "judge02_checks.json").read_text())
TMP = Path(evidence["provenance"]["code_extracted_to"])
Y = TMP / "yejun"
G = Y / "press_guard"
DATA = Y / "press_submission/data/3_소성가공_예지보전"
DEST = TMP / "cli_review"
DEST.mkdir(exist_ok=True)
PY = "/opt/anaconda3/bin/python"
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
result = {"temporary_snapshot": str(TMP), "commands": []}
started = time.monotonic()


def command(args):
    r = subprocess.run([PY, *map(str, args)], cwd=Y, env=ENV, capture_output=True, text=True)
    entry = {"argv": list(map(str, args)), "code": r.returncode, "stdout": r.stdout, "stderr": r.stderr}
    result["commands"].append(entry)
    print("COMMAND", args[0], "exit", r.returncode, flush=True)
    print(r.stdout.strip(), flush=True)
    print(r.stderr.strip(), flush=True)
    assert r.returncode == 0
    return entry


site = DEST / "site.json"
command([G / "recalibrate.py", "--normal", DATA / "press_data_normal.csv", "--out", site])
tables = []
for prior in (.001, .01):
    out = DEST / f"abnormal_prior{prior}.csv"
    r = command([G / "predict.py", "--model", site, "--input", DATA / "outlier_data.csv", "--out", out, "--prior", prior])
    assert r["stderr"].count("라벨 확률 보정기가 없어") == 1
    assert "쓰이지 않습니다" in r["stderr"]
    tables.append(pd.read_csv(out))
cols = ["likelihood_ratio", "anomaly_probability", "record_likelihood_ratio", "record_probability"]
result["recalibrated_prediction"] = {
    "rows": [len(t) for t in tables],
    "alarms": [int(t.alarm.sum()) for t in tables],
    "missing": [{c: int(t[c].isna().sum()) for c in cols} for t in tables],
    "two_priors_have_same_alarm": bool(tables[0].alarm.equals(tables[1].alarm)),
}
assert all(t[cols].isna().all().all() for t in tables)
assert tables[0].alarm.equals(tables[1].alarm) and tables[0].alarm.sum() == 556

# 모의운용과 감시도 보정기 없는 실제 site 모델에 같은 안내를 한다.
for args in ([G / "simulate.py", "--model", site, "--csv", DATA / "outlier_data.csv", "--chunk", "128"],
             [G / "monitor.py", "--model", site, "--csv", DATA / "outlier_data.csv", "--reference", DATA / "press_data_normal.csv", "--out", DEST / "windows.csv"]):
    r = command(args)
    assert r["stderr"].count("라벨 확률 보정기가 없어") == 1

sys.path.insert(0, str(G))
from model import D, load_bundle
from probability import ProbabilityCalibrator

_, abnormal, _ = D.load()
bundle = load_bundle(TMP / "artifacts_refit/guard_B.json")
a, b = (bundle.predict(abnormal, prior=p) for p in (.001, .01))
result["with_calibrator_prior_change"] = {
    "same_alarm": bool(a.alarm.equals(b.alarm)),
    "same_score": bool(np.array_equal(a.score, b.score)),
    "same_likelihood_ratio": bool(np.array_equal(a.likelihood_ratio, b.likelihood_ratio)),
    "probability_increases": bool((a.anomaly_probability <= b.anomaly_probability).all()),
}
assert all(result["with_calibrator_prior_change"].values())

# 결함 발견 당시의 합성 함수 반례다. 대회·현장 관측값으로 해석하지 않는다.
c = ProbabilityCalibrator.fit([0, 1, 2, 3], [2, 3, 4], calibration_units=120)
q = np.array([1.0, 1.1, 1.5, 2.0])
result["synthetic_floor_counterexample_before_fix"] = {
    "normal_fit_scores": [0, 1, 2, 3], "abnormal_fit_scores": [2, 3, 4], "query": q.tolist(),
    "lr": c.likelihood_ratio(q).tolist(), "probability": c.probability(q).tolist(),
    "nondecreasing": bool((np.diff(c.likelihood_ratio(q)) >= 0).all()),
}
result["nominal_lr_counterexample"] = {
    "scope": "수학적 가정 반례; 관측 또는 현장 추정 아님",
    "tpr_assumed": .955, "nominal_far": 1 / 121, "smaller_far_allowed_by_upper_bound": 1 / 242,
    "nominal_lr": .955 * 121, "smaller_far_lr": .955 * 242,
    "primary_reference": "https://arxiv.org/pdf/2107.07511",
}
result["elapsed_s"] = time.monotonic() - started
(HERE / "judge02_cli.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({k: v for k, v in result.items() if k != "commands"}, ensure_ascii=False, indent=2))
