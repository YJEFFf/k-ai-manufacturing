"""검토 1: x86-64 재실행 분석 결과표의 verify 허용 한계 대비 여유(|차이|/한계)를 표마다 적는다.

    REVIEW_ENV=<mac 사본의 yejun> X86_ENV=<x86 사본의 yejun> PYTHONDONTWRITEBYTECODE=1 python review1_x86_margin.py
"""
import os, sys
from pathlib import Path
MAC = Path(os.environ["REVIEW_ENV"]); X86 = Path(os.environ["X86_ENV"])
sys.path.insert(0, str(MAC / "press_guard"))
import numpy as np, pandas as pd
import verify
rows = []
for n in verify.RESULTS:
    x, y = pd.read_csv(X86 / "press_guard" / "outputs" / n), pd.read_csv(MAC / "press_guard" / "outputs" / "expected" / n)
    for c in x.columns:
        if pd.api.types.is_float_dtype(x[c]) and pd.api.types.is_float_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float); ok = np.isfinite(xv) & np.isfinite(yv)
            d = np.abs(xv[ok] - yv[ok]); bound = verify.COLUMN_TOLERANCE.get((n, c), verify.TOL) + verify.RTOL * np.abs(yv[ok])
            if len(d) and d.max() > 0:
                i = int(np.argmax(d / bound))
                rows.append((n, c, float(d[i]), float(bound[i]), float(d[i] / bound[i]), float(yv[ok][i]), float(xv[ok][i])))
t = pd.DataFrame(rows, columns=["file", "column", "abs_diff", "bound", "ratio", "mac", "x86"]).sort_values("ratio", ascending=False)
pd.set_option("display.width", 250)
print(t.head(12).to_string(index=False))
print("한계를 넘는 열:", int((t.ratio > 1).sum()), "| 한계의 10% 넘는 열:", int((t.ratio > .1).sum()))
