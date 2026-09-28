"""redC: 짧은 확인 모음. 임시 사본의 verify 모듈만 부른다(저장소 작업 사본은 읽기만).

    python redC_quick_checks.py <임시 사본>/yejun
(a) 부하 기록 3/51의 독립 이항 p와 공유 보정 BetaBinomial p 재계산
(b) 실수 열의 값 두 개를 행끼리 바꾸면 verify 허용오차 경로를 통과하는가
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "press_guard"))
import verify  # noqa: E402

out = dict(binom_p=float(stats.binom.sf(2, 51, 1 / 62)), betabinom_p=float(stats.betabinom.sf(2, 51, 1, 61)))
tmp = Path(__file__).with_name("redC_swap_tmp"); (tmp / "expected").mkdir(parents=True, exist_ok=True)
real = pd.read_csv(root / "press_guard" / "outputs" / "test_predictions_B.csv")
real.to_csv(tmp / "pred.csv", index=False)
(tmp / "expected" / verify.DIGEST).write_text(json.dumps({"pred.csv": verify.prediction_digest(tmp / "pred.csv")}), encoding="utf-8")
verify.PREDICTIONS = ("pred.csv",)
res = {}
fa = real.index[(real.label == 0) & (real.alarm == 1)][0]           # 정상 오경보 행 하나
quiet = real.index[(real.label == 1) & (real.alarm == 0)][0]        # 이상 미탐 행 하나
for cols in (["score", "p_value", "anomaly_score", "likelihood_ratio", "anomaly_probability"], ["anomaly_probability"], ["record_current_rms"]):
    x = real.copy()
    for c in cols:
        x.loc[[fa, quiet], c] = x.loc[[quiet, fa], c].to_numpy()
    x.to_csv(tmp / "pred.csv", index=False)
    r = verify.compare_predictions(tmp, tmp / "expected")[0]
    res["+".join(cols)] = dict(ok=r["ok"], note=r.get("note", ""), swapped_rows=[int(fa), int(quiet)])
out["swap_between_false_alarm_and_missed_row"] = res
for p in tmp.rglob("*"):
    if p.is_file():
        p.unlink()
(tmp / "expected").rmdir(); tmp.rmdir()
Path(__file__).with_name("redC_quick_checks.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
