"""검토 1: 권고 확인용 — x86-64 재실행 예측의 열 요약(합·제곱합) 상대 차이가 얼마인가(요약 비교를 열별 상대 1e-6로 되살려도 통과하는가).

    REVIEW_ENV=<mac 사본의 yejun> X86_ENV=<x86 사본의 yejun> PYTHONDONTWRITEBYTECODE=1 python review1_x86_summary_margin.py
"""
import os, sys
from pathlib import Path
MAC = Path(os.environ["REVIEW_ENV"]); X86 = Path(os.environ["X86_ENV"])
sys.path.insert(0, str(MAC / "press_guard"))
import numpy as np
import verify
from contracts import PREDICTIONS
worst = []
exp = verify.read_json(MAC / "press_guard" / "outputs" / "expected" / verify.DIGEST)
for n in PREDICTIONS:
    now = verify.prediction_digest(X86 / "press_guard" / "outputs" / n)
    for c, (cnt, s, ss, mn, mx) in exp[n]["numeric_summary"].items():
        a = now["numeric_summary"][c]
        rel = max(abs(a[1] - s) / max(abs(s), 1e-300), abs(a[2] - ss) / max(abs(ss), 1e-300))
        worst.append((rel, n, c))
worst.sort(reverse=True)
for rel, n, c in worst[:6]:
    print(f"{n:28s} {c:28s} 합·제곱합 최대 상대 차이 {rel:.3g}")
print("상대 1e-6 넘는 열:", sum(r > 1e-6 for r, _, _ in worst), "/", len(worst))
