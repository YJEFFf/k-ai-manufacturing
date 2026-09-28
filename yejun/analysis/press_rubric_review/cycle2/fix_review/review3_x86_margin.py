"""검토 3: x86-64 컨테이너에서 다시 만든 press_guard 결과가 verify.py(110afa2)의 허용 한계에 얼마나 가까운가.

    REVIEW_ENV=<x86 사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_x86_margin.py
x86 사본의 outputs/(컨테이너가 다시 만든 결과)와 outputs/expected/(커밋된 macOS 동결값)를 읽기만 한다.
- 결과 CSV: 열마다 max(|Δ|/허용)  (허용 = COLUMN_TOLERANCE 또는 1e-9 + 1e-7·|동결|)
- 행 단위 예측: 열마다 행별 max(|Δ|/허용)(float32 동결 값 기준)과 열 요약 5개의 max(상대 차이/허용 상대)
- 모델 4개: equivalence 허용 대비 최대 비율
비율이 1을 넘으면 verify가 실패한다.
"""
import json
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd

import verify
import equivalence
from contracts import PREDICTIONS

OUT = ENV / "press_guard" / "outputs"
EXP = OUT / "expected"
ART = ENV / "press_guard" / "artifacts"


def csv_margin(name):
    x, y = pd.read_csv(OUT / name), pd.read_csv(EXP / name)
    worst = (0.0, "")
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]) and not pd.api.types.is_integer_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float)
            ok = np.isfinite(xv) & np.isfinite(yv)
            if not ok.any():
                continue
            bound = verify.COLUMN_TOLERANCE.get((name, c), verify.TOL) + verify.RTOL * np.abs(yv[ok])
            r = float((np.abs(xv[ok] - yv[ok]) / bound).max())
            old = float((np.abs(xv[ok] - yv[ok]) / (verify.COLUMN_TOLERANCE.get((name, c), verify.TOL) + 1e-9 * np.abs(yv[ok]))).max())
            if r > worst[0]:
                worst = (r, f"{c}(1e-9 상대 규칙이면 {old:.2f})")
    return worst


def main():
    print("## 결과 CSV: 허용 대비 최대 비율 상위")
    rows = sorted(((csv_margin(n), n) for n in verify.RESULTS if (OUT / n).is_file()), reverse=True)
    for (r, col), n in rows[:10]:
        print(f"  {n:40s} {r:.3g}  {col}")
    print("\n## 행 단위 예측: SHA 같음 여부와 열별 허용 대비 최대 비율")
    digest = json.loads((EXP / verify.DIGEST).read_text(encoding="utf-8"))
    overall_row, overall_sum = [], []
    for name in PREDICTIONS:
        e = digest[name]; now = verify.prediction_digest(OUT / name)
        same = now["sha256"] == e["sha256"]
        x = pd.read_csv(OUT / name)
        worst_row, worst_sum = (0.0, ""), (0.0, "")
        for c, text in e["row_values"].items():
            frozen, cur = verify._unpack(text), x[c].to_numpy(float)
            ok = np.isfinite(frozen) & np.isfinite(cur)
            if ok.any():
                r = float((np.abs(cur[ok] - frozen[ok]) / verify._row_bound(c, frozen[ok])).max())
                if r > worst_row[0]:
                    worst_row = (r, c)
            rtol = verify.ECDF_SUMMARY_RTOL if c in verify.ECDF_COLUMNS else verify.ROW_RTOL
            a, b = now["numeric_summary"][c], e["numeric_summary"][c]
            for k, (u, w) in enumerate(zip(a[1:], b[1:])):
                if u is None or w is None:
                    continue
                lim = verify.ROW_ATOL + rtol * max(abs(u), abs(w))
                r = abs(u - w) / lim
                if r > worst_sum[0]:
                    worst_sum = (r, f"{c}.{['합', '제곱합', '최솟값', '최댓값'][k]}")
        print(f"  {name:30s} SHA 같음 {same} | 정확 열 같음 {now['exact_sha256'] == e['exact_sha256']} | 행별 최대 {worst_row[0]:.3g} ({worst_row[1]}) "
              f"| 요약 최대 {worst_sum[0]:.3g} ({worst_sum[1]})")
        overall_row.append(worst_row[0]); overall_sum.append(worst_sum[0])
    print("\n## 모델 4개: equivalence 허용 대비 최대 비율")
    for name in ("guard_A.json", "guard_B.json", "probability_A.json", "probability_B.json"):
        a, b = equivalence._flatten(equivalence._state(ART / name)), equivalence._flatten(equivalence._state(EXP / name))
        worst = 0.0
        for k in b:
            if isinstance(b[k], np.ndarray):
                ok = np.isfinite(b[k])
                if ok.any():
                    worst = max(worst, float((np.abs(a[k][ok] - b[k][ok]) / (equivalence.ATOL + equivalence.RTOL * np.abs(b[k][ok]))).max()))
        print(f"  {name:20s} SHA 같음 {equivalence._sha(ART / name) == equivalence._sha(EXP / name)} | 최대 비율 {worst:.3g}")


if __name__ == "__main__":
    main()
