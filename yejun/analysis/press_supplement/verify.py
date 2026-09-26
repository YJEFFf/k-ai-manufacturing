"""보완 실험 결과를 실행 기록(manifest)·동결 기대값과 대조한다 — 루브릭 검수 R9.

    python verify.py                   # 무결성(코드·원본·기준 모델·외부 표·산출물 해시) + 동결 기대값 비교
    python verify.py --freeze          # 무결성이 통과한 실행만 expected/로 동결
    python verify.py --rerun E2,E3     # 커밋된 코드·원본으로 임시 폴더에 다시 만들어 기대값과 비교(E1 약 20분, E2·E3 약 2~3분)

수치 열 허용오차 1e-9, 정수·문자 열은 정확 비교. 실행 메타데이터(run_id·시각·소요 시간·환경)는 비교하지 않는다.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

import contract
from contract import EXPERIMENTS, HERE, manifest_name

EXPECTED = HERE / "expected"
TOL = 1e-9


def compare_csv(a, b):
    x, y = pd.read_csv(a), pd.read_csv(b)
    if x.shape != y.shape or list(x.columns) != list(y.columns):
        return f"{Path(a).name}: 모양·열 불일치 {x.shape} vs {y.shape}"
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float)
            if any(not np.array_equal(f(xv), f(yv)) for f in (np.isnan, np.isposinf, np.isneginf)):
                return f"{Path(a).name}: {c} 결측·무한 위치 불일치"
            ok = np.isfinite(xv)
            d = np.abs(xv[ok] - yv[ok])
            if len(d) and d.max() > TOL:
                return f"{Path(a).name}: {c} 최대 차이 {d.max():.3g} > {TOL:g}"
        elif not x[c].astype(str).equals(y[c].astype(str)):
            return f"{Path(a).name}: 문자 열 {c} 불일치"
    return None


def compare_to_expected(out, experiments):
    bad = []
    for exp in experiments:
        try:
            exp_manifest = json.loads((EXPECTED / manifest_name(exp)).read_text())
        except (OSError, ValueError) as exc:
            bad.append(f"{exp}: 동결 기대값 없음({exc}). 무결성 통과 실행에서 --freeze로 먼저 동결한다")
            continue
        for name in EXPERIMENTS[exp]["outputs"]:
            q = EXPECTED / name
            if not q.is_file():
                bad.append(f"{exp}: 동결 기대값 파일 없음 — {name}")
                continue
            if exp_manifest.get("outputs", {}).get(name) != contract.D.sha256_file(q):
                bad.append(f"{exp}: 동결 기대값이 동결 당시 기록과 다름 — {name}")
            p = Path(out) / name
            reason = compare_csv(p, q) if p.is_file() else f"{name}: 결과 파일 없음"
            if reason:
                bad.append(f"{exp}: {reason}")
        try:
            if exp_manifest.get("config") != json.loads((Path(out) / manifest_name(exp)).read_text()).get("config"):
                bad.append(f"{exp}: 실행 설정이 동결 실행과 다름")
        except (OSError, ValueError):
            bad.append(f"{exp}: 실행 manifest 없음")
    return bad


def rerun(experiments):
    """커밋된 코드로 임시 폴더에 다시 만들고 기대값과 비교한다. 결과 폴더는 지운다."""
    bad = []
    env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="press_supplement_rerun_") as tmp:
        for exp in experiments:
            out = Path(tmp) / exp
            cmd = [sys.executable, str(HERE / EXPERIMENTS[exp]["script"]), "--out", str(out)]
            print(f"-- {exp} 재실행: {' '.join(cmd[1:])}", flush=True)
            done = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if done.returncode:
                bad.append(f"{exp}: 재실행 실패(종료 코드 {done.returncode}) {done.stderr[-400:]}")
                continue
            bad += contract.errors(exp, out)
            bad += compare_to_expected(out, [exp])
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--rerun", default="", help="다시 만들어 비교할 실험(예: E1,E2,E3)")
    ap.add_argument("--experiments", default="E1,E2,E3")
    args = ap.parse_args(argv)
    experiments = [e for e in args.experiments.split(",") if e]
    integrity = [msg for exp in experiments for msg in contract.errors(exp, args.out)]
    if args.freeze:
        if integrity:
            print("동결 거부:\n  " + "\n  ".join(integrity), file=sys.stderr)
            return 2
        staged = Path(tempfile.mkdtemp(prefix=".freeze-", dir=HERE)) / "expected"
        staged.mkdir()
        for exp in experiments:
            for name in EXPERIMENTS[exp]["outputs"] + (manifest_name(exp),):
                shutil.copy2(args.out / name, staged / name)
        if EXPECTED.exists():
            for exp in experiments:     # 동결하지 않은 실험의 기대값은 남긴다
                for name in EXPERIMENTS[exp]["outputs"] + (manifest_name(exp),):
                    (EXPECTED / name).unlink(missing_ok=True)
        EXPECTED.mkdir(exist_ok=True)
        for f in staged.iterdir():
            shutil.move(str(f), EXPECTED / f.name)
        shutil.rmtree(staged.parent)
        print(f"동결: {', '.join(experiments)} → {EXPECTED}")
        return 0
    bad = integrity + compare_to_expected(args.out, experiments)
    if args.rerun:
        bad += rerun([e for e in args.rerun.split(",") if e])
    for msg in bad:
        print("FAIL", msg)
    print(f"{'통과' if not bad else '실패'}: 무결성·기대값 비교 {', '.join(experiments)}" + (f" · 재실행 {args.rerun}" if args.rerun else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
