"""⑤ 전력 패키지 전체 실행: 원본 → 진단 → 워크포워드 비교·선택 → 시험 → 피크 → 분석 → 현장 시뮬레이션 → 그림.

사용:
    python run_all.py                       # data/ 의 CSV 또는 저장소 데이터셋 ZIP 자동 탐색
    python run_all.py --data /경로/Dataset_자원\\ 최적화\\ AI\\ 데이터셋.zip
    python run_all.py --stages diagnostics,models   # 일부 단계만
    python run_all.py --stages predict              # 추론만: 저장된 모델로 시험 예측 재생성(학습 없음, 수 초)
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import warnings
from importlib import metadata

# 예상된 경고만 숨긴다(그림 한글 글꼴 누락 같은 경고는 보이게 둔다)
for _msg in ("Mean of empty slice", "invalid value encountered", "divide by zero encountered", "All-NaN slice encountered",
             "X does not have valid feature names", "Degrees of freedom <= 0"):
    warnings.filterwarnings("ignore", message=f".*{_msg}.*")

from powerguard import config as C  # noqa: E402
from powerguard import data as D  # noqa: E402
from powerguard import io  # noqa: E402

STAGES = ["diagnostics", "models", "predict", "peak", "analysis", "ablation", "field", "external", "figures", "digest"]


def versions() -> dict:
    out = {"python": platform.python_version(), "platform": platform.platform()}
    for pkg in ("numpy", "pandas", "scikit-learn", "lightgbm", "shap", "scipy", "matplotlib"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = None
    return out


def code_sha256() -> str:
    """powerguard/*.py와 run_all.py의 지문(실행 중 코드가 바뀌면 산출물 출처가 섞이므로 확인한다)."""
    import hashlib
    h = hashlib.sha256()
    for p in sorted(list((C.PKG_ROOT / "powerguard").glob("*.py")) + [C.PKG_ROOT / "run_all.py"]):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _git_commit() -> str | None:
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=C.PKG_ROOT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="원본 CSV 또는 KAMP ZIP 경로")
    ap.add_argument("--stages", default=",".join(STAGES))
    ap.add_argument("--kamp-dir", default=None, help="외부 KAMP 자료 ZIP 폴더(기본: 저장소 데이터셋/)")
    args = ap.parse_args(argv)
    C.DATA_PATH = args.data
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    if args.kamp_dir:
        from pathlib import Path
        C.KAMP_DIR = Path(args.kamp_dir)
    bad = [s for s in stages if s not in STAGES]
    if bad:
        print(f"알 수 없는 단계: {bad}", file=sys.stderr)
        return 2
    t_all = time.time()
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    code_start = code_sha256()
    timings, stage_times = {}, {}
    df, meta = D.load_raw(args.data)
    diag = D.diagnose(df)
    iv = D.build_intervals(df, diag)
    ctx = {"df": df, "meta": meta, "diag": diag, "iv": iv}

    def stage(name, fn):
        if name not in stages:
            return
        t0 = time.time()
        print(f"[{name}] 시작", flush=True)
        fn()
        timings[name] = round(time.time() - t0, 1)
        stage_times[name] = (t0, time.time())
        print(f"[{name}] 완료 {timings[name]}s", flush=True)

    def s_diag():
        from powerguard import stage_diagnostics
        stage_diagnostics.run(df, meta, diag, iv)

    def s_models():
        from powerguard import stage_models
        ctx["models"] = stage_models.run(iv, log=lambda m: print(m, flush=True))

    def _selection():
        return json.loads((C.OUTPUT_DIR / "cv" / "selection.json").read_text(encoding="utf-8"))

    def _frames():
        if "models" in ctx:
            return ctx["models"]["frames"]
        from powerguard import cv as CV
        return CV.build_frames(iv)

    def s_predict():
        from powerguard import stage_predict
        stage_predict.run(iv, _frames(), _selection())

    def s_peak():
        from powerguard import stage_peak
        stage_peak.run(iv, _frames(), _selection())

    def s_analysis():
        from powerguard import stage_analysis
        stage_analysis.run(iv, _frames(), _selection(), df=df, diag=diag, log=lambda m: print(m, flush=True))

    def s_ablation():
        from powerguard import stage_analysis
        stage_analysis.run_heavy(iv, df, diag, _selection(), log=lambda m: print(m, flush=True))

    def s_field():
        from powerguard import stage_field
        stage_field.run(iv, _frames(), _selection())

    def s_external():
        from powerguard import stage_external
        stage_external.run()

    def s_figures():
        from powerguard import stage_figures
        stage_figures.run(iv)

    stage("diagnostics", s_diag)
    stage("models", s_models)
    stage("predict", s_predict)
    stage("peak", s_peak)
    stage("analysis", s_analysis)
    stage("ablation", s_ablation)
    stage("field", s_field)
    stage("external", s_external)
    stage("figures", s_figures)

    def s_digest():
        from powerguard import stage_digest
        stage_digest.run()

    stage("digest", s_digest)
    if code_sha256() != code_start:
        print("오류: 실행 도중 코드(powerguard/*.py, run_all.py)가 바뀌었다. 산출물 출처가 섞였으니 다시 실행한다.", file=sys.stderr)
        return 3
    # 실행 기록: 일부 단계만 실행해도 이전 단계 기록을 지우지 않고 단계별로 갱신한다
    mpath = C.OUTPUT_DIR / "run_manifest.json"
    prev = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    per_stage = prev.get("stages_last_run", {}) if isinstance(prev.get("stages_last_run"), dict) else {}
    for s in stages:
        a, b = stage_times.get(s, (None, None))
        per_stage[s] = {"started_epoch": a, "finished_epoch": b, "finished_at": now, "seconds": timings.get(s)}
    inv = {"stages": stages, "argv": list(argv) if argv is not None else sys.argv[1:], "timings_s": timings,
           "total_s": round(time.time() - t_all, 1), "started_at": started_at, "finished_at": now,
           "started_epoch": t_all, "finished_epoch": time.time(), "full_run": stages == STAGES, "code_sha256": code_start}
    manifest = {"data": meta, "seed": C.SEED, "stages_last_run": per_stage, "last_invocation": inv,
                "last_full_run": inv if stages == STAGES else prev.get("last_full_run"),
                "environment": {"cpu_count": os.cpu_count(), "git_commit": _git_commit()}, "versions": versions()}
    io.write_json(manifest, mpath)
    print(f"전체 완료 {manifest['last_invocation']['total_s']}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
