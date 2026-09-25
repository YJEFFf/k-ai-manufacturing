"""동결 기대값(expected/)과 현재 outputs/를 비교한다. 수치 파일(CSV/JSON)은 허용오차 안에서 같아야 한다.

사용:
    python verify.py            # 비교
    python verify.py --freeze   # 현재 outputs/를 expected/로 동결(의도한 변경 후에만)
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
EXP = ROOT / "expected"
# 실행 환경·시간, 입력 경로 표기(원본 동일성은 SHA-256으로 확인)는 비교하지 않는다
SKIP_JSON_KEYS = {"timings_s", "total_s", "versions", "platform", "source"}
RTOL = 1e-6
ATOL = 1e-6


def files(base: Path) -> list[Path]:
    return sorted(p.relative_to(base) for p in base.rglob("*")
                  if p.is_file() and p.suffix in (".csv", ".json") and "predictions" not in p.name
                  and p.name != "run_manifest.json")


def cmp_json(a, b, path="") -> list[str]:
    errs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k in SKIP_JSON_KEYS:
                continue
            if k not in a or k not in b:
                errs.append(f"{path}/{k}: 키 불일치")
            else:
                errs += cmp_json(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            errs.append(f"{path}: 길이 {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                errs += cmp_json(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if not math.isclose(a, b, rel_tol=RTOL, abs_tol=ATOL):
            errs.append(f"{path}: {a} != {b}")
    elif a != b:
        errs.append(f"{path}: {a!r} != {b!r}")
    return errs


def cmp_csv(pa: Path, pb: Path) -> list[str]:
    a, b = pd.read_csv(pa), pd.read_csv(pb)
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return [f"{pa.name}: 형태 {a.shape}/{list(a.columns)[:5]} != {b.shape}/{list(b.columns)[:5]}"]
    errs = []
    for c in a.columns:
        x, y = a[c], b[c]
        if pd.api.types.is_bool_dtype(x) or pd.api.types.is_bool_dtype(y):
            bad = ~((x == y) | (x.isna() & y.isna()))
        elif pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            xf, yf = x.astype(float), y.astype(float)
            bad = ~(((xf - yf).abs() <= ATOL + RTOL * yf.abs()) | (xf.isna() & yf.isna()))
        else:
            bad = x.astype(object).where(x.notna(), "<NA>").astype(str) != y.astype(object).where(y.notna(), "<NA>").astype(str)
        if bad.any():
            i = bad.idxmax()
            errs.append(f"{pa.name}:{c} {int(bad.sum())}행 차이(예: {x[i]!r} != {y[i]!r})")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args(argv)
    if args.freeze:
        if EXP.exists():
            shutil.rmtree(EXP)
        for rel in files(OUT):
            (EXP / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT / rel, EXP / rel)
        print(f"동결: {len(files(EXP))}개 파일")
        return 0
    exp, cur = set(files(EXP)), set(files(OUT))
    errs = [f"누락: {p}" for p in sorted(exp - cur)] + [f"추가(기대값 없음): {p}" for p in sorted(cur - exp)]
    ok = 0
    for rel in sorted(exp & cur):
        e = (cmp_json(json.loads((OUT / rel).read_text()), json.loads((EXP / rel).read_text()), str(rel))
             if rel.suffix == ".json" else cmp_csv(OUT / rel, EXP / rel))
        if e:
            errs += e
        else:
            ok += 1
    print(f"일치 {ok}/{len(exp)}")
    for e in errs[:50]:
        print(" -", e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
