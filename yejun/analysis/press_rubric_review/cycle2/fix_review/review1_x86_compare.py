"""검토 1: x86-64 리눅스 컨테이너(pg-x86, numpy 1.26.4·pandas 2.3.3)에서 같은 사본으로 v1 2단계 + v2 train.py --rolling을 다시 돌린 결과를
macOS 동결값과 verify.py의 비교 함수로 대조한다.

    REVIEW_ENV=<mac 사본의 yejun> X86_ENV=<x86 사본의 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_x86_compare.py
"""
import os, sys, hashlib
from pathlib import Path
MAC = Path(os.environ["REVIEW_ENV"]); X86 = Path(os.environ["X86_ENV"])
sys.path.insert(0, str(MAC / "press_guard"))
import numpy as np, pandas as pd
import verify
from equivalence import artifact_equivalent, _flatten, _state
from contracts import PREDICTIONS, TRAIN_TABLES

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]
print("## 모델 파일(x86 재학습 vs mac 동결)")
for n in ("guard_A.json", "guard_B.json", "probability_A.json", "probability_B.json"):
    frozen_dir = MAC / "press_guard" / "outputs" / "expected"
    if not (frozen_dir / n).is_file():
        frozen_dir = MAC / "press_guard" / "artifacts"      # 스냅숏의 expected/에 확률 보정기 사본이 없어 mac 저장 모델로 대조
    ok, why = artifact_equivalent(X86 / "press_guard" / "artifacts" / n, frozen_dir)
    a, b = _flatten(_state(X86 / "press_guard" / "artifacts" / n)), _flatten(_state(frozen_dir / n))
    diffs = [float(np.nanmax(np.abs(a[k] - b[k]))) for k in b if isinstance(b[k], np.ndarray) and a[k].shape == b[k].shape and a[k].size]
    print(f"  {n}: sha x86 {sha(X86/'press_guard'/'artifacts'/n)} mac {sha(frozen_dir/n)} | 동등 {ok} | 원소 최대 절대 차이 {max(diffs):.3g} | {why[:60]}")
print("## 학습 결과 표(verify.compare_csv, 1e-9 + 1e-9·|값|)")
for n in TRAIN_TABLES:
    r = verify.compare_csv(X86 / "press_guard" / "outputs" / n, MAC / "press_guard" / "outputs" / "expected" / n)
    print(f"  {n}: {'통과' if r['ok'] else '실패'} {r.get('reason', '')} {('max|Δ|=%.3g' % r['max_abs_diff']) if 'max_abs_diff' in r else ''}")
print("## 행 단위 예측(verify.compare_predictions: SHA 다르면 정확 열 + 0.001 격자 ±1)")
for r in verify.compare_predictions(X86 / "press_guard" / "outputs", MAC / "press_guard" / "outputs" / "expected"):
    print(f"  {r['file']}: {'통과' if r['ok'] else '실패'} {r.get('reason', '')} {r.get('note', '')}")
print("## 행 단위 예측의 열별 최대 차이(x86 − mac 실행 파일)")
for n in PREDICTIONS:
    x, y = pd.read_csv(X86 / "press_guard" / "outputs" / n), pd.read_csv(MAC / "press_guard" / "outputs" / n)
    worst = []
    for c in x.columns:
        if pd.api.types.is_float_dtype(x[c]):
            d = np.abs(x[c].to_numpy(float) - y[c].to_numpy(float)); d = d[np.isfinite(d)]
            if len(d) and d.max() > 0:
                worst.append((c, float(d.max()), int((d > 1e-9).sum())))
        elif not x[c].astype(str).equals(y[c].astype(str)):
            worst.append((c, "문자/정수 다름", int((x[c].astype(str) != y[c].astype(str)).sum())))
    worst.sort(key=lambda w: -w[1] if isinstance(w[1], float) else -1e9)
    print(f"  {n}: sha 같음 {sha(X86/'press_guard'/'outputs'/n) == sha(MAC/'press_guard'/'outputs'/n)} | 상위 차이 {worst[:4]}")

print("## 분석 결과표 전체(verify.RESULTS: compare_csv, 순위 통계 열만 1e-3)와 analysis_summary.json")
import json
fails = []
for n in verify.RESULTS:
    p, q = X86 / "press_guard" / "outputs" / n, MAC / "press_guard" / "outputs" / "expected" / n
    if not p.is_file():
        fails.append((n, "x86 결과 없음")); continue
    r = verify.compare_csv(p, q)
    if not r["ok"]:
        fails.append((n, r["reason"]))
print(f"  결과표 {len(verify.RESULTS)}개 중 실패 {len(fails)}개")
for n, why in fails:
    print(f"   실패 {n}: {why}")
a = json.loads((X86 / "press_guard" / "outputs" / "analysis_summary.json").read_text()); b = json.loads((MAC / "press_guard" / "outputs" / "expected" / "analysis_summary.json").read_text())
for s in (a, b):
    s.pop("elapsed_s", None)
diff = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
print("  analysis_summary.json 같은가(verify와 같은 정확 비교, elapsed_s 제외):", not diff, "| 다른 키:", diff[:8])
