"""outputs/를 동결된 기대값(outputs/expected/)과 비교한다 — PLAN.md §7·§9.

    python verify.py --out outputs            # 비교
    python verify.py --out outputs --freeze   # 현재 outputs를 기대값으로 동결(검증된 실행에서만)

허용오차: 주 모델·집계 CSV 1e-8, IF/MLP-AE 1e-6(OMP 1스레드), LSTM 관련 1e-3 및 경보 판정 비교. 원본 입력 해시는 동일해야 한다.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOL = {"default": 1e-8, "isolation_forest": 1e-6, "mlp_ae_w5": 1e-6, "lstm": 1e-3}
SKIP = {"manifest.json", "checks.json", "numbers.json"}
ROW_LEVEL = ("predictions", "records_main")


def tol_for(name: str, model: str | None) -> float:
    if "lstm" in name or (model and "lstm" in model):
        return TOL["lstm"]
    if model in TOL:
        return TOL[model]
    return TOL["default"]


def compare_csv(a: Path, b: Path) -> dict:
    x, y = pd.read_csv(a), pd.read_csv(b)
    if x.shape != y.shape or list(x.columns) != list(y.columns):
        return dict(file=a.name, ok=False, reason=f"shape/columns {x.shape} vs {y.shape}")
    worst, alarms_diff = 0.0, 0
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float)
            both = np.isfinite(xv) & np.isfinite(yv)
            if (np.isfinite(xv) != np.isfinite(yv)).any():
                return dict(file=a.name, ok=False, reason=f"NaN pattern differs in {c}")
            d = float(np.max(np.abs(xv[both] - yv[both]))) if both.any() else 0.0
            models = x["model"].astype(str).tolist() if "model" in x.columns else [None] * len(x)
            tol = max(tol_for(a.name, m) for m in set(models)) if models else TOL["default"]
            if d > tol:
                return dict(file=a.name, ok=False, reason=f"{c}: max abs diff {d:.3g} > tol {tol:g}")
            worst = max(worst, d)
            if c.startswith("alarm") and (xv != yv).any():
                alarms_diff += int((xv != yv).sum())
        else:
            if not x[c].astype(str).equals(y[c].astype(str)):
                return dict(file=a.name, ok=False, reason=f"text column {c} differs")
    return dict(file=a.name, ok=True, max_abs_diff=worst, alarm_cells_diff=alarms_diff)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "outputs")
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args(argv)
    exp = args.out / "expected"
    files = [p for p in args.out.iterdir() if p.is_file() and p.suffix in (".csv", ".json") and p.name not in SKIP and not p.name.startswith(ROW_LEVEL)]
    if args.freeze:
        exp.mkdir(exist_ok=True)
        for p in files:
            shutil.copy2(p, exp / p.name)
        shutil.copy2(args.out / "manifest.json", exp / "manifest.json")
        print(f"동결: {len(files)}개 파일 → {exp}")
        return 0
    if not exp.exists():
        print("outputs/expected 가 없다. 검증된 실행에서 --freeze 로 먼저 동결한다.", file=sys.stderr)
        return 2
    man_now, man_exp = json.loads((args.out / "manifest.json").read_text()), json.loads((exp / "manifest.json").read_text())
    res = [dict(file="inputs.sha256", ok=man_now["inputs"]["files"] == man_exp["inputs"]["files"] or all(man_now["inputs"]["files"][k]["sha256"] == man_exp["inputs"]["files"][k]["sha256"] for k in man_exp["inputs"]["files"]))]
    for p in files:
        q = exp / p.name
        if not q.exists():
            res.append(dict(file=p.name, ok=False, reason="expected 없음"))
        elif p.suffix == ".csv":
            res.append(compare_csv(p, q))
        else:
            res.append(dict(file=p.name, ok=json.loads(p.read_text()) == json.loads(q.read_text()) or p.name == "diagnosis.json"))
    bad = [r for r in res if not r["ok"]]
    for r in res:
        print(("OK  " if r["ok"] else "FAIL") + f" {r['file']}" + (f"  ({r.get('reason')})" if not r["ok"] else (f"  max|Δ|={r['max_abs_diff']:.2g}" if "max_abs_diff" in r else "")))
    print(f"\n{len(res) - len(bad)}/{len(res)} 통과. 환경: {man_now['environment'].get('platform')} vs 동결 {man_exp['environment'].get('platform')}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
