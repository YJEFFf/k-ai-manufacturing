"""한 명령 재현: 입력 확인 → v1 선행 → v2 학습·분석·실행 검증·동결값 비교 → 분석 패키지 재생성·검증 → 요약.

    python yejun/press_guard/reproduce.py                 # 기본(빠른 경로): torch 없이 최종 모델 전체 + 진단 패키지 재생성, 나머지 분석 패키지는 동결값 비교
    python yejun/press_guard/reproduce.py --full          # 전체: v1 1~5단계(LSTM, torch 필요)·후보 비교·지도학습 기준선·선정 근거·보완 실험 E1~E3 재실행까지.
                                                          #   LSTM 캐시가 있으면 약 25분, 새 사본(LSTM 처음부터 학습)은 약 63분
    python yejun/press_guard/reproduce.py --data "Dataset_소성가공 예지보전 AI 데이터셋.zip"   # 주최 측 ZIP(또는 두 CSV가 든 폴더)을 먼저 배치
    python yejun/press_guard/reproduce.py --tests         # 끝에 pytest·웹 회귀 시험까지

- 모든 단계는 같은 파이썬으로 하위 프로세스에서 돈다(스레드 1개, 바이트코드 파일 없음). 실패하면 그 단계 로그 끝을 보이고 멈춘다
  (--keep-going이면 계속). 단계별 결과·시간은 press_guard/outputs/reproduce_summary.json에 남는다(동결 대상 아님).
- 동결(--freeze)은 하지 않는다. 결과를 커밋된 기대값과 비교만 한다.
- 입력: 대회 원본 CSV 2개(press_submission/data/3_소성가공_예지보전/). SHA-256이 대회 원본과 다르면 멈춘다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parent
sys.path.insert(0, str(HERE))
import runtime  # noqa: E402


def steps(full, tests):
    py = sys.executable
    v1 = YEJUN / "press_submission"
    contract = YEJUN / "analysis" / "package_contract.py"
    s = []
    s.append(("v1 선행(주 모델·기준모델·행별 예측)", [py, str(v1 / "run_all.py")] + ([] if full else ["--steps", "2"]), v1))
    s.append(("v1 동결값 비교", [py, str(v1 / "verify.py"), "--out", "outputs"] + ([] if full else ["--steps", "2"]), v1))
    if full:
        s.append(("후보 비교(press_advance)", [py, str(YEJUN / "analysis" / "press_advance" / "run_experiment.py")], YEJUN))
    s += [("v2 학습·시간순 5회", [py, str(HERE / "train.py"), "--rolling"], HERE),
          ("v2 분석", [py, str(HERE / "analyze.py")], HERE),
          ("v2 실행 검증(audit)", [py, str(HERE / "audit.py")], HERE),
          ("v2 동결값 비교", [py, str(HERE / "verify.py")], HERE)]
    if full:
        # 지도학습 기준선(HGB)과 그것을 다시 돌리는 선정 근거 표는 결정 트리의 부동소수 분기 때문에 기기마다 TP가 ±1~3 달라진다
        # (리눅스 x86-64 실측). 빠른 경로는 커밋된 결과의 무결성·동결값만 확인하고, 전체 모드에서 다시 만든다(보완 실험 E1~E3와 같은 방식).
        # press_evidence가 지도학습 결과를 인용하므로 먼저 만든다.
        s += [("지도학습 기준선(press_supervised)", [py, str(YEJUN / "analysis" / "press_supervised" / "run.py")], YEJUN),
              ("모델 선정 근거(press_selection)", [py, str(YEJUN / "analysis" / "press_selection" / "run.py")], YEJUN)]
    ev = YEJUN / "analysis" / "press_evidence"
    s += [("진단 표(press_evidence)", [py, str(ev / "build_tables.py")], YEJUN),
          ("진단 보강 표·그림", [py, str(ev / "build_diagnostics.py")], YEJUN)]
    if contract.exists():
        for pkg in ("press_evidence", "press_supervised", "press_advance", "press_selection"):
            if (YEJUN / "analysis" / pkg / "contract.json").exists():
                s.append((f"{pkg} 동결값 비교", [py, str(contract), "--package", str(YEJUN / "analysis" / pkg)], YEJUN))
    sup = YEJUN / "analysis" / "press_supplement" / "verify.py"
    s.append(("보완 실험 E1~E3 " + ("재실행·비교" if full else "동결값 비교"), [py, str(sup)] + (["--rerun", "E1,E2,E3"] if full else []), YEJUN))
    if tests:
        s += [("시험: v2", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(HERE)], HERE),
              ("시험: v1", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(v1 / "tests")], v1),
              ] + [(f"시험: {p.parent.name}", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(p)], YEJUN)   # 같은 파일 이름이라 패키지마다 따로
                   for p in sorted((YEJUN / "analysis").glob("press_*/test_*.py"))]
        if shutil.which("node"):
            s.append(("시험: 웹 콘솔", ["node", str(HERE / "test_web.cjs")], HERE))
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="v1 LSTM 비교(torch)·후보 비교·E1~E3 재실행까지")
    ap.add_argument("--data", type=Path, help="주최 측 데이터 ZIP 또는 두 CSV가 든 폴더")
    ap.add_argument("--tests", action="store_true", help="끝에 시험까지 실행")
    ap.add_argument("--keep-going", action="store_true", help="실패해도 다음 단계를 계속한다")
    args = ap.parse_args(argv)
    runtime.check_python()
    runtime.setup()
    from model import D   # 파이썬 판 확인 뒤에 무거운 모듈을 부른다
    if args.data:
        placed = runtime.install_data(args.data, D.PACKAGE_DIR, D.FILES, D.EXPECTED_SHA256, D.DATA_SUBDIR)
        print(f"입력 배치: {placed}", flush=True)
    try:
        D.load()
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"입력 자료 오류: {exc}\n주최 측 ZIP을 --data로 주거나 README의 데이터 배치 절차를 따른다.")
    if args.full:
        try:
            import torch  # noqa: F401
        except ImportError:
            raise SystemExit("--full은 v1 LSTM 비교를 다시 만들어 torch가 필요하다(pip install -r yejun/press_guard/requirements-lstm.txt). 빠른 경로는 torch 없이 돈다.")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "1"),
           "PRESS_THREADS": os.environ.get("PRESS_THREADS", "1"), "PYTHONIOENCODING": "utf-8"}   # 단계 로그를 UTF-8로 받는다(CP949 콘솔)
    log_dir = HERE / "outputs" / "reproduce_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    results, start = [], time.monotonic()
    plan = steps(args.full, args.tests)
    for k, (name, cmd, cwd) in enumerate(plan, 1):
        t = time.monotonic()
        print(f"[{k}/{len(plan)}] {name} …", flush=True)
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log = log_dir / f"{k:02d}.log"
        log.write_text(f"$ {' '.join(cmd)}\n\n{proc.stdout}\n{proc.stderr}", encoding="utf-8")
        last = [line for line in (proc.stdout + proc.stderr).strip().splitlines() if line.strip()][-1:] or [""]
        results.append(dict(step=name, command=cmd, returncode=proc.returncode, seconds=round(time.monotonic() - t, 1), last_line=last[0][:200], log=str(log.relative_to(YEJUN))))
        print(f"      {'통과' if proc.returncode == 0 else '실패'} · {results[-1]['seconds']}초 · {last[0][:120]}", flush=True)
        if proc.returncode != 0:
            print("\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:]), file=sys.stderr)
            if not args.keep_going:
                break
    failed = [r for r in results if r["returncode"] != 0]
    summary = dict(mode="full" if args.full else "quick", python=sys.version.split()[0], total_seconds=round(time.monotonic() - start, 1),
                   passed=len(results) - len(failed), failed=len(failed), planned=len(plan), steps=results)
    (HERE / "outputs" / "reproduce_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{summary['passed']}/{len(plan)} 단계 통과 · {summary['total_seconds']}초 · 요약 press_guard/outputs/reproduce_summary.json")
    return 1 if failed or len(results) < len(plan) else 0


if __name__ == "__main__":
    raise SystemExit(main())
