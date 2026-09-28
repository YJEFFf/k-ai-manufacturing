"""검토 1: press_guard/verify.py 행 단위 예측 비교의 'SHA-256이 다를 때' 경로에 변조를 넣어 본다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_verify_tamper.py
사본의 outputs/test_predictions_A.csv와 outputs/expected/predictions_digest.json을 쓴다. 변조 파일은 임시 폴더에만 쓴다.
각 변조에 대해 새 규칙(행별 0.001 격자 ±1칸) 판정과, 같은 요약에 이미 들어 있는 이전 규칙(열 요약 상대 1e-7)의 판정을 함께 적는다.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))

import numpy as np
import pandas as pd

import verify
from contracts import PREDICTIONS

OUT = ENV / "press_guard" / "outputs"
NAME = "test_predictions_A.csv"


def judge(frame):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "outputs"; exp = out / "expected"; exp.mkdir(parents=True)
        shutil.copy2(OUT / "expected" / verify.DIGEST, exp / verify.DIGEST)
        for n in PREDICTIONS:
            if n != NAME:
                shutil.copy2(OUT / n, out / n)
        frame.to_csv(out / NAME, index=False)
        r = {x["file"]: x for x in verify.compare_predictions(out, exp)}[NAME]
        now = verify.prediction_digest(out / NAME)
        e = verify.read_json(exp / verify.DIGEST)[NAME]
        old_ok = (now["columns"] == e["columns"] and now["rows"] == e["rows"] and now["exact_sha256"] == e["exact_sha256"]
                  and now["nonfinite_sha256"] == e["nonfinite_sha256"]
                  and all(verify._close(now["numeric_summary"][c], e["numeric_summary"][c]) for c in e["numeric_summary"]))
        return r["ok"], r.get("reason", ""), old_ok


def main():
    base = pd.read_csv(OUT / NAME)
    ok, why, old = judge(base)
    print(f"대조(변조 없음, 같은 바이트): 새 규칙 {'통과' if ok else '실패'}")
    cases = []

    t = base.copy(); i = int(np.flatnonzero(t.alarm.eq(0))[10]); t.loc[i, "alarm"] = 1
    cases.append(("T1 경보 한 행 0→1", t))
    t = base.copy(); t.loc[5, "score"] += 0.01
    cases.append(("T2 점수 한 행 +0.01", t))
    t = base.copy(); t.loc[5, "score"] += 0.0014
    cases.append(("T3 점수 한 행 +0.0014", t))
    t = base.copy(); t["score"] = t.score + 0.0009
    cases.append(("T4 점수 모든 행 +0.0009(체계적 이동)", t))
    t = base.copy(); s = t.score.to_numpy(); order = np.argsort(s); d = np.diff(s[order]); j = int(np.flatnonzero((d > 5e-4) & (d < 9e-4))[0])
    a, b = int(order[j]), int(order[j + 1]); t.loc[[a, b], "score"] = t.loc[[b, a], "score"].to_numpy()
    cases.append((f"T5 점수가 {d[j]:.1e} 다른 두 행 맞바꿈", t))
    t = base.copy(); m = t.anomaly_probability < 5e-4
    t.loc[m, "anomaly_probability"] *= 3; mr = t.record_probability < 5e-4; t.loc[mr, "record_probability"] *= 3
    cases.append((f"T6 이상 확률 <0.05%인 {int(m.sum())}/{len(t)}행을 3배(기록 확률 {int(mr.sum())}행도)", t))
    t = base.copy(); m = t.anomaly_probability < 1.4e-3; t.loc[m, "anomaly_probability"] = 0.0
    cases.append((f"T7 이상 확률 <0.14%인 {int(m.sum())}행을 0으로", t))
    t = base.copy(); t["probability_prior"] = 0.011
    cases.append(("T8 사전 비율 열 0.01→0.011(10%)", t))
    t = base.copy(); m = t.likelihood_ratio < 0.05; t.loc[m, "likelihood_ratio"] *= 1.02
    cases.append((f"T9 우도비 <0.05인 {int(m.sum())}행 ×1.02", t))
    t = base.copy(); m = t.anomaly_probability_file_prior < 0.007; t.loc[m, "anomaly_probability_file_prior"] *= 1.1
    cases.append((f"T10 파일 비율 확률 <0.7%인 {int(m.sum())}행 ×1.1", t))
    t = base.copy(); g = t.g_waveform.to_numpy(); fin = np.flatnonzero(np.isfinite(g)); a, b = int(fin[0]), int(fin[np.argmax(np.abs(g[fin] - g[fin[0]]))])
    t.loc[[a, b], "g_waveform"] = t.loc[[b, a], "g_waveform"].to_numpy()
    cases.append(("T11 파형 성분 두 행 맞바꿈(값 차이 큼)", t))
    t = base.copy(); i = int(np.flatnonzero(t.alarm.eq(1))[0]); before = t.loc[i, "reason"]
    t.loc[i, "reason"] = "dynamics" if before != "dynamics" else "magnitude"
    cases.append((f"T12 근거 문자열 한 행 변경({before}→{t.loc[i, 'reason']})", t))
    t = base.copy(); i = int(np.flatnonzero(t.incident_id.gt(0))[0]); t.loc[i, "incident_id"] += 1
    cases.append(("T13 사건 번호 한 행 +1", t))

    print(f"{'변조':60s} | 새 규칙 | 이전 규칙(요약 상대 1e-7) | 새 규칙 사유")
    for title, frame in cases:
        ok, why, old = judge(frame)
        print(f"{title:60s} | {'통과' if ok else '실패':4s} | {'통과' if old else '실패':4s} | {why[:80]}")


if __name__ == "__main__":
    main()
