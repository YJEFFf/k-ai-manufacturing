"""검토 3: 수정 커밋(110afa2) press_guard/verify.py의 행 단위 예측 비교(SHA가 다를 때의 경로)에 변조를 넣는다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_verify_tamper.py
사본의 outputs/test_predictions_A.csv와 커밋된 outputs/expected/predictions_digest.json을 쓴다. 변조 파일은 임시 폴더에만 쓴다.
T1~T13은 검토 1(review1_verify_tamper.py)과 같은 변조다. T14~T22는 새 규칙(float32 행별 상대 1e-6, ECDF 구간 1e-3,
열 요약 상대 1e-6·ECDF 열 1e-4)의 경계를 본다.
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


def judge(frame, name=NAME):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "outputs"; exp = out / "expected"; exp.mkdir(parents=True)
        shutil.copy2(OUT / "expected" / verify.DIGEST, exp / verify.DIGEST)
        for n in PREDICTIONS:
            if n != name:
                shutil.copy2(OUT / n, out / n)
        frame.to_csv(out / name, index=False)
        r = {x["file"]: x for x in verify.compare_predictions(out, exp)}[name]
        return r["ok"], r.get("reason", "")


def main():
    base = pd.read_csv(OUT / NAME)
    ok, why = judge(base)
    print(f"대조(변조 없음, 다시 쓴 같은 값): {'통과' if ok else '실패'} {why}")
    cases = []
    # ---- 검토 1과 같은 변조 ----
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
    cases.append((f"T5 점수가 {d[j]:.1e} 다른 두 행 맞바꿈(값 {s[a]:.3f})", t))
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
    # ---- 새 규칙의 경계 ----
    t = base.copy(); m = t.score <= 1.35; t.loc[m, "score"] += 0.0009
    cases.append((f"T14 ECDF 구간 점수({int(m.sum())}행)만 +0.0009", t))
    t = base.copy(); g = t.g_waveform.to_numpy(); body = np.flatnonzero(np.isfinite(g) & (g <= 1.35) & (g > 0.01))
    sign = np.where(np.arange(len(body)) % 2 == 0, 1.0, -1.0); t.loc[body, "g_waveform"] = g[body] + 0.0009 * sign
    cases.append((f"T15 ECDF 구간 파형 점수 {len(body)}행 ±0.0009 교대(합 보존)", t))
    t = base.copy(); t["p_value"] = t.p_value * (1 + 5e-7)
    cases.append(("T16 p값 전 행 ×(1+5e-7)", t))
    t = base.copy(); t["anomaly_probability"] = t.anomaly_probability * (1 + 2e-6)
    cases.append(("T17 이상 확률 전 행 ×(1+2e-6)", t))
    t = base.copy(); i = int(np.flatnonzero(t.record_likelihood_ratio.eq(t.record_likelihood_ratio.max()))[0]); t.loc[i, "record_likelihood_ratio"] = 120.0
    cases.append(("T18 기록 우도비 한 행 121→120", t))
    t = base.copy(); i = int(np.flatnonzero(t.score > 1.35)[0]); t.loc[i, "score"] += 1e-5
    cases.append((f"T19 꼬리 구간 점수 한 행 +1e-5(값 {base.score[i]:.3f})", t))
    # 기기 간 순위 한 칸 뒤바뀜의 크기(ECDF 최소 부근 약 5e-5)를 열 최솟값 행에 넣는다: 행 허용(1e-3) 안이지만 요약의 최솟값은 상대 1e-4다
    for col in ("g_waveform", "score", "g_magnitude"):
        t = base.copy(); v = t[col].to_numpy(); i = int(np.nanargmin(v)); step = 5e-5
        t.loc[i, col] = v[i] + step
        cases.append((f"T20 {col} 열 최솟값 행({v[i]:.3g})에 +{step:g}(ECDF 순위 한 칸 크기)", t))
    t = base.copy(); v = t.g_waveform.to_numpy(); i = int(np.nanargmin(v)); t.loc[i, "g_waveform"] = v[i] - 5e-5
    cases.append((f"T21 g_waveform 열 최솟값 행에 −5e-5", t))
    t = base.copy(); t["alpha"] = 0.0100000099
    cases.append(("T22 alpha 열 0.01→0.0100000099", t))

    print(f"{'변조':70s} | 판정 | 사유")
    for title, frame in cases:
        ok, why = judge(frame)
        print(f"{title:70s} | {'통과' if ok else '실패'} | {why[:110]}")


if __name__ == "__main__":
    main()
