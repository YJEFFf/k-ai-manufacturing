"""평가관 06(코드·재현성) 2주기 1회차 — 실행 결과 대조와 정적 점검.

Phase A~E 스크립트(judge06_phase*.sh)가 시스템 임시 폴더에 만든 클론·산출물을 읽어 다음을 확인한다. 저장소에는 이 폴더의 judge06_results.json만 쓴다.
1) 새로 학습한 저장 모델·테스트 예측 파일(행 단위)의 SHA-256이 커밋된 동결 manifest와 같은가(비트 단위 재현)
2) 추론 전용 CLI(predict.py) 결과가 학습 실행의 예측과 같은가
3) 원본부터 다시 만든 후보 비교(press_advance)·진단 보강 표(press_evidence)·v1 비교표·지도학습 기준선(press_supervised)이 커밋본과 같은가
4) 제출 ZIP 조립기(press_submission/tools/make_submission_zip.py)가 무엇을 담는가(ZIP은 만들지 않고 목록만 계산)
5) 인코딩 미지정 텍스트 입출력·Unix 전용 모듈·절대 경로 등 정적 이식성 점검
6) Phase 로그의 단계별 종료 코드·시간

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python judge06_check.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
BASE = Path(os.environ.get("J06_BASE", "/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/judge06"))   # judge06_lib.sh와 같은 임시 폴더
CLONES = {"B_readme": BASE / "B_readme/clone", "C_full_raw": BASE / "C_full_raw/clone", "D_venv312": BASE / "D_venv/clone",
          "E_no_omp": BASE / "E_portability/clone_nomp"}
PRED = [f"predictions_{k}_{s}.csv" for k in ("normal", "abnormal") for s in ("A", "B")]


def sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def clone_commit() -> str:
    """클론이 가리키는 커밋(작업 중 저장소 HEAD가 움직여도 실행 기준과 같은 커밋으로 비교한다)."""
    for root in (CLONES["C_full_raw"], CLONES["B_readme"]):
        if (root / ".git").exists():
            return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


COMMIT = None


def git_show(rel: str) -> bytes:
    global COMMIT
    COMMIT = COMMIT or clone_commit()
    return subprocess.run(["git", "-C", str(REPO), "show", f"{COMMIT}:{rel}"], capture_output=True, check=True).stdout


def compare_csv(a: Path, b: Path, tol=1e-9) -> dict:
    if not a.is_file() or not b.is_file():
        return dict(ok=False, reason=f"파일 없음: {a if not a.is_file() else b}")
    if a.read_bytes() == b.read_bytes():
        return dict(ok=True, bytes_equal=True, max_abs_diff=0.0)
    x, y = pd.read_csv(a), pd.read_csv(b)
    if x.shape != y.shape or list(x.columns) != list(y.columns):
        return dict(ok=False, bytes_equal=False, reason=f"모양·열 불일치 {x.shape} vs {y.shape}")
    worst, where = 0.0, None
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            xv, yv = x[c].to_numpy(float), y[c].to_numpy(float)
            if not np.array_equal(np.isnan(xv), np.isnan(yv)):
                return dict(ok=False, bytes_equal=False, reason=f"{c} 결측 위치 불일치")
            m = ~np.isnan(xv)
            d = float(np.max(np.abs(xv[m] - yv[m]))) if m.any() else 0.0
            if d > worst:
                worst, where = d, c
        elif not x[c].astype(str).equals(y[c].astype(str)):
            return dict(ok=False, bytes_equal=False, reason=f"문자 열 {c} 불일치")
    return dict(ok=worst <= tol, bytes_equal=False, max_abs_diff=worst, worst_column=where)


def clone_hashes(expected: dict) -> dict:
    out = {}
    for name, root in CLONES.items():
        pg = root / "yejun/press_guard"
        if not (pg / "outputs/manifest.json").is_file():
            out[name] = "실행 없음"
            continue
        arts = {a: sha(pg / "artifacts" / a) == expected["artifacts"][a] for a in expected["artifacts"]}
        preds = {p: sha(pg / "outputs" / p) == expected["outputs"][p] for p in PRED}
        rows = {p: int(sum(1 for _ in open(pg / "outputs" / p, encoding="utf-8")) - 1) for p in PRED if (pg / "outputs" / p).is_file()}
        out[name] = dict(artifacts_bit_identical=arts, test_predictions_bit_identical=preds, prediction_rows=rows)
    return out


def predict_cli_check() -> dict:
    res = {}
    for name, cli in (("B_readme", BASE / "B_readme/press_predictions.csv"), ("C_full_raw", BASE / "C_full_raw/predict_cli_A_abnormal.csv")):
        train_pred = CLONES[name] / "yejun/press_guard/outputs/predictions_abnormal_A.csv"
        if not cli.is_file() or not train_pred.is_file():
            res[name] = "파일 없음"
            continue
        a, b = pd.read_csv(cli), pd.read_csv(train_pred)
        common = [c for c in b.columns if c in a.columns]
        diff = {}
        for c in common:
            if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c]):
                av, bv = a[c].to_numpy(float), b[c].to_numpy(float)
                same_nan = np.array_equal(np.isnan(av), np.isnan(bv))
                d = float(np.nanmax(np.abs(av - bv))) if np.isfinite(av).any() else 0.0
                if not same_nan or d > 0:
                    diff[c] = d if same_nan else "결측 위치 다름"
            elif not a[c].astype(str).equals(b[c].astype(str)):
                diff[c] = "문자 다름"
        res[name] = dict(rows=(len(a), len(b)), common_columns=len(common), only_in_cli=[c for c in a.columns if c not in b.columns],
                         only_in_train=[c for c in b.columns if c not in a.columns], differing_columns=diff)
    return res


def regenerated_tables() -> dict:
    res = {}
    C = CLONES["C_full_raw"] / "yejun"
    committed = BASE / "C_full_raw/committed"
    for rel in ("metrics.csv", "primary.csv"):
        res[f"press_advance/{rel}"] = compare_csv(C / "analysis/press_advance" / rel, committed / "press_advance" / rel)
    ev = sorted(p.name for p in (committed / "press_evidence").glob("*.csv"))
    res["press_evidence"] = {n: compare_csv(C / "analysis/press_evidence" / n, committed / "press_evidence" / n) for n in ev}
    v1 = ("model_comparison_all.csv", "model_comparison_lstm.csv", "model_comparison.csv", "operating_points.csv", "sensitivity.csv")
    res["press_submission_outputs(LSTM 처음부터)"] = {n: compare_csv(C / "press_submission/outputs" / n, committed / "press_submission_outputs" / n) for n in v1}
    sup = BASE / "E_portability/supervised_out"
    res["press_supervised"] = {}
    for n in ("random_rows.csv", "grouped_records.csv", "injection.csv"):
        tmp = BASE / f"committed_supervised_{n}"
        tmp.write_bytes(git_show(f"yejun/analysis/press_supervised/{n}"))
        res["press_supervised"][n] = compare_csv(sup / n, tmp)
    return res


def zip_builder_contents() -> dict:
    root = CLONES["C_full_raw"] / "yejun/press_submission"
    spec = importlib.util.spec_from_file_location("judge06_mkzip", root / "tools/make_submission_zip.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # 상수 정의만 실행(main은 호출하지 않음 → ZIP을 만들지 않는다)
    files = []
    for d in mod.INCLUDE_DIRS:
        p = mod.PKG / d
        if p.exists():
            files += [f for f in sorted(p.rglob("*")) if f.is_file() and not (mod.EXCLUDE_PARTS & set(f.parts))]
    files += [mod.PKG / f for f in mod.INCLUDE_FILES if (mod.PKG / f).exists()]
    rel = [str(f.relative_to(mod.PKG)) for f in files]
    return dict(package_root=str(mod.PKG.relative_to(CLONES["C_full_raw"])), include_dirs=mod.INCLUDE_DIRS, n_files=len(rel),
                total_mb=round(sum(f.stat().st_size for f in files) / 1e6, 2),
                includes_press_guard=any("press_guard" in r for r in rel),
                includes_v2_predictions=any(re.search(r"predictions_(normal|abnormal)_[AB]\.csv", r) for r in rel),
                includes_v1_predictions=[r for r in rel if re.search(r"outputs/predictions_[AB]\.csv", r)],
                includes_analysis_packages=any(r.startswith("analysis") for r in rel))


TEXT_IO = re.compile(r"\.read_text\(\s*\)|\.write_text\((?![^\n]*encoding)[^\n]*\)|(?<![\w.])open\((?![^\n]*(encoding|\"rb\"|'rb'|\"wb\"|'wb'|\"r\+b\"))[^\n]*\)")


def static_portability() -> dict:
    git_show("yejun/README.md")
    files = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", COMMIT, "--", "yejun/press_guard", "yejun/press_submission", "yejun/analysis/press_supplement",
                            "yejun/analysis/press_evidence", "yejun/analysis/press_advance", "yejun/analysis/press_supervised"],
                           capture_output=True, text=True, check=True).stdout.split()
    hits, unix_only, abs_paths = {}, [], {}
    for rel in files:
        if not rel.endswith((".py", ".md", ".sh")):
            continue
        text = git_show(rel).decode("utf-8")
        if rel.endswith(".py"):
            n = sum(1 for line in text.splitlines() if TEXT_IO.search(line) and "urlopen" not in line)
            if n:
                hits[rel] = n
            for i, line in enumerate(text.splitlines(), 1):
                if re.search(r"^\s*import resource\b|resource\.getrusage", line):
                    unix_only.append(f"{rel}:{i}: {line.strip()}")
        k = len(re.findall(r"/opt/anaconda3/bin/python", text))
        if k:
            abs_paths[rel] = k
    runtime = {k: v for k, v in hits.items() if "/test_" not in k and "/tests/" not in k}
    json_nonascii = {}
    for rel in ("yejun/press_submission/outputs/manifest.json", "yejun/press_submission/outputs/expected/manifest.json",
                "yejun/analysis/press_advance/manifest.json", "yejun/analysis/press_supplement/protocol.json",
                "yejun/analysis/press_supervised/protocol.json", "yejun/press_guard/outputs/audit.json",
                "yejun/press_guard/outputs/analysis_summary.json"):
        b = git_show(rel)
        try:
            b.decode("cp949"); cp = "cp949로 읽힘"
        except UnicodeDecodeError as e:
            cp = f"cp949 해독 실패(바이트 {e.start})"
        json_nonascii[rel] = cp
    return dict(encoding_less_text_io_runtime=runtime, encoding_less_text_io_tests={k: v for k, v in hits.items() if k not in runtime},
                unix_only_modules=unix_only, hardcoded_interpreter_path=abs_paths, json_read_without_encoding_cp949=json_nonascii)


def readme_checks() -> dict:
    g = git_show("yejun/press_guard/README.md").decode("utf-8")
    top = git_show("yejun/README.md").decode("utf-8")
    return dict(press_guard_readme_mentions_v1_prerequisite=("run_all" in g), press_guard_readme_mentions_requirements=("requirements" in g),
                press_guard_readme_mentions_test_prediction_file=bool(re.search(r"테스트\s*(데이터)?\s*예측|제출용 예측", g)),
                press_advance_has_readme=bool(subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", COMMIT, "yejun/analysis/press_advance/README.md"], capture_output=True, text=True).stdout.strip()),
                top_readme_has_single_entry=bool(re.search(r"run_all|make\b|한 번에|한 명령", top)),
                press_guard_has_requirements=bool(subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", COMMIT, "yejun/press_guard/requirements.txt", "yejun/press_guard/environment.yml"], capture_output=True, text=True).stdout.strip()),
                press_submission_has_environment_yml=bool(subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", COMMIT, "yejun/press_submission/environment.yml"], capture_output=True, text=True).stdout.strip()))


def normalize_cp949_log(log: Path) -> int:
    """Phase E 로그에는 CP949 모의 실행의 표준출력이 CP949 바이트로 들어 있다. 읽을 수 있게 그 줄만 CP949로 풀어 UTF-8로 다시 쓴다."""
    if not log.is_file():
        return 0
    lines, fixed = [], 0
    for raw in log.read_bytes().split(b"\n"):
        try:
            lines.append(raw.decode("utf-8"))
        except UnicodeDecodeError:
            lines.append("[cp949 출력] " + raw.decode("cp949", errors="replace")); fixed += 1
    if fixed:
        log.write_text("\n".join(lines), encoding="utf-8")
    return fixed


def phase_steps() -> dict:
    res = {}
    for log in sorted(HERE.glob("judge06_phase*.log")):
        res[log.stem] = [dict(zip(("step", "rc", "wall", "maxrss_mb"), re.match(r"STEP (\S+) rc=(\d+) wall=(\d+)s maxrss_mb=(\S+)", line).groups()))
                         for line in log.read_text(encoding="utf-8", errors="replace").splitlines() if line.startswith("STEP ")]
    return res


def main():
    normalize_cp949_log(HERE / "judge06_phaseE_portability.log")
    expected = json.loads(git_show("yejun/press_guard/outputs/expected/manifest.json"))
    result = dict(clone_commit=COMMIT, repo_head_now=subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                  bit_identity_vs_frozen_manifest=clone_hashes(expected), predict_cli_vs_train=predict_cli_check(),
                  regenerated_vs_committed=regenerated_tables(), zip_builder=zip_builder_contents(),
                  static_portability=static_portability(), readme=readme_checks(), phases=phase_steps())
    (HERE / "judge06_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
