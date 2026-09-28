"""평가관 06 사이클2 3회차 — 실행 결과 대조. Q1~Q10이 시스템 임시 폴더에 만든 사본을 읽는다. 저장소에는 judge06_results.json만 쓴다.

1) 한 명령 재현 요약(reproduce_summary.json): 단계별 종료 코드·시간
2) 비트 단위 재현: 저장 모델·확률 보정기·행 단위 예측 6개 파일의 SHA-256 대 커밋된 동결 기록(manifest.json·predictions_digest.json)
3) 결과 표: press_guard/outputs의 CSV·MD, 분석 패키지 결과, v1 결과를 커밋본(git show 061fac8)과 바이트·허용오차 비교
4) 파일만으로 F1 재계산(test_predictions의 label·alarm)과 이상 600행이 두 파일에 같은지
5) manifest의 실행 환경 기록(BLAS 이름·판·스레드 수, R11)

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python judge06_check.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
COMMIT = "061fac8"
BASE = Path(os.environ.get("J06_BASE", "/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/judge06r3"))
RUNS = {"Q1_git없는사본_conda_CSV만": BASE / "Q1_archive/copy", "Q2_새클론_lock_nodeps_tests": BASE / "Q2_venv/clone",
        "Q3_새클론_CP949_resource차단_tests": BASE / "Q3_cp949/clone", "Q5b_목록사본_copy_test": BASE / "Q5_package/copytest",
        "Q5c_목록사본_README_tests": BASE / "Q5_package/pkg", "Q8_새클론_full": BASE / "Q8_full/clone",
        "Q9_git없는사본_py3.11_lock_tests": BASE / "Q9_pyver/copy", "Q10_autocrlf클론": BASE / "Q10_crlf/clone"}
PRED = ["test_predictions_A.csv", "test_predictions_B.csv"] + [f"predictions_{k}_{s}.csv" for k in ("normal", "abnormal") for s in "AB"]


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def show(rel: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{COMMIT}:{rel}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def ls(rel_dir: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-tree", "--name-only", f"{COMMIT}:{rel_dir}"], capture_output=True, text=True, encoding="utf-8")
    return out.stdout.split()


def cmp_bytes_or_tol(now: Path, ref: bytes, tol=1e-9) -> dict:
    if not now.is_file():
        return dict(ok=False, reason="없음")
    b = now.read_bytes()
    if b == ref:
        return dict(ok=True, bytes_equal=True)
    if now.suffix != ".csv":
        return dict(ok=False, bytes_equal=False, reason="바이트 다름")
    x, y = pd.read_csv(now), pd.read_csv(io.BytesIO(ref))
    if x.shape != y.shape or list(x.columns) != list(y.columns):
        return dict(ok=False, bytes_equal=False, reason=f"모양 {x.shape} vs {y.shape}")
    worst = 0.0
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            a, b2 = x[c].to_numpy(float), y[c].to_numpy(float)
            if not np.array_equal(np.isnan(a), np.isnan(b2)):
                return dict(ok=False, bytes_equal=False, reason=f"{c} 결측 위치")
            m = ~np.isnan(a)
            worst = max(worst, float(np.max(np.abs(a[m] - b2[m]))) if m.any() else 0.0)
        elif not x[c].astype(str).equals(y[c].astype(str)):
            return dict(ok=False, bytes_equal=False, reason=f"문자 열 {c}")
    return dict(ok=worst <= tol, bytes_equal=False, max_abs_diff=worst)


def f1_from_file(p: Path):
    x = pd.read_csv(p)
    tp = int(((x.label == 1) & (x.alarm == 1)).sum()); fp = int(((x.label == 0) & (x.alarm == 1)).sum()); fn = int(((x.label == 1) & (x.alarm == 0)).sum())
    return dict(rows=len(x), normal_rows=int((x.label == 0).sum()), abnormal_rows=int((x.label == 1).sum()), tp=tp, fp=fp, fn=fn, f1=round(2 * tp / (2 * tp + fp + fn), 6))


def main():
    digest = json.loads(show("yejun/press_guard/outputs/expected/predictions_digest.json"))
    man = json.loads(show("yejun/press_guard/outputs/manifest.json"))
    committed_outputs = [n for n in ls("yejun/press_guard/outputs/") if n.endswith((".csv", ".md"))]
    packages = {"press_evidence": [n for n in ls("yejun/analysis/press_evidence/") if n.endswith(".csv")],
                "press_supervised": ["random_rows.csv", "grouped_records.csv", "injection.csv"],
                "press_selection": [n for n in ls("yejun/analysis/press_selection/") if n.endswith((".csv", ".md")) and n != "README.md"],
                "press_advance": ["metrics.csv", "primary.csv"],
                "press_supplement": [n for n in ls("yejun/analysis/press_supplement/") if n.startswith("e") and n.endswith(".csv")]}
    v1_tables = [n for n in ls("yejun/press_submission/outputs/") if n.endswith(".csv")]
    result = dict(commit=COMMIT, runs={})
    for name, root in RUNS.items():
        y = root / "yejun"
        r = dict(root=str(root), exists=y.is_dir())
        if not y.is_dir():
            result["runs"][name] = r; continue
        s = y / "press_guard/outputs/reproduce_summary.json"
        if s.is_file():
            sm = json.loads(s.read_text(encoding="utf-8"))
            r["reproduce"] = dict(mode=sm["mode"], python=sm["python"], passed=sm["passed"], planned=sm["planned"], failed=sm["failed"], total_seconds=sm["total_seconds"],
                                  steps=[(st["step"], st["returncode"], st["seconds"], st["last_line"][:90]) for st in sm["steps"]])
        art = {n: sha(y / "press_guard/artifacts" / n) == man["artifacts"].get(n) for n in man.get("artifacts", {})}
        r["artifacts_equal_committed_manifest"] = art
        r["predictions_equal_committed_digest"] = {n: sha(y / "press_guard/outputs" / n) == digest[n]["sha256"] for n in PRED}
        tp = {s_: f1_from_file(y / f"press_guard/outputs/test_predictions_{s_}.csv") for s_ in "AB" if (y / f"press_guard/outputs/test_predictions_{s_}.csv").is_file()}
        r["test_predictions_f1_from_file"] = tp
        if len(tp) == 2:
            a = pd.read_csv(y / "press_guard/outputs/test_predictions_A.csv"); b = pd.read_csv(y / "press_guard/outputs/test_predictions_B.csv")
            ca = a[a.label == 1].drop(columns=["model_id", "likelihood_ratio", "anomaly_probability", "record_likelihood_ratio", "record_probability", "score", "p_value", "g_magnitude", "g_waveform", "g_dynamics"], errors="ignore").reset_index(drop=True)
            cb = b[b.label == 1].drop(columns=["model_id", "likelihood_ratio", "anomaly_probability", "record_likelihood_ratio", "record_probability", "score", "p_value", "g_magnitude", "g_waveform", "g_dynamics"], errors="ignore").reset_index(drop=True)
            r["abnormal_rows_same_ids_both_files"] = bool(ca[["row_id", "record_id", "position", "timestamp"]].equals(cb[["row_id", "record_id", "position", "timestamp"]]))
        tables = {n: cmp_bytes_or_tol(y / "press_guard/outputs" / n, show(f"yejun/press_guard/outputs/{n}")) for n in committed_outputs}
        r["press_guard_tables"] = dict(total=len(tables), bytes_equal=sum(v.get("bytes_equal", False) for v in tables.values()),
                                       within_tol=sum(v["ok"] for v in tables.values()), differ={k: v for k, v in tables.items() if not v.get("bytes_equal")})
        pk = {}
        for pkg, names in packages.items():
            res = {n: cmp_bytes_or_tol(y / "analysis" / pkg / n, show(f"yejun/analysis/{pkg}/{n}")) for n in names}
            pk[pkg] = dict(total=len(res), bytes_equal=sum(v.get("bytes_equal", False) for v in res.values()), within_tol=sum(v["ok"] for v in res.values()),
                           differ={k: v for k, v in res.items() if not v.get("bytes_equal")})
        r["analysis_packages"] = pk
        v1 = {n: cmp_bytes_or_tol(y / "press_submission/outputs" / n, show(f"yejun/press_submission/outputs/{n}"), tol=1e-3) for n in v1_tables}
        present = {k: v for k, v in v1.items() if v.get("reason") != "없음"}
        r["v1_tables"] = dict(committed=len(v1), present=len(present), bytes_equal=sum(v.get("bytes_equal", False) for v in present.values()),
                              within_1e3=sum(v["ok"] for v in present.values()), differ={k: v for k, v in present.items() if not v.get("bytes_equal")})
        mf = y / "press_guard/outputs/manifest.json"
        if mf.is_file():
            env = json.loads(mf.read_text(encoding="utf-8")).get("environment", {})
            r["manifest_environment"] = dict(python=env.get("python"), blas=env.get("blas"), press_threads=env.get("press_threads"), platform=env.get("platform"))
        result["runs"][name] = r
    out = HERE / "judge06_results.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for name, r in result["runs"].items():
        print(f"== {name}: {'없음' if not r['exists'] else ''}")
        if not r["exists"]:
            continue
        if "reproduce" in r:
            rp = r["reproduce"]; print(f"   재현 {rp['mode']} py{rp['python']} {rp['passed']}/{rp['planned']} 통과 · {rp['total_seconds']}초")
        print(f"   저장 모델·보정기 동결 해시 일치: {r['artifacts_equal_committed_manifest']}")
        print(f"   행 단위 예측 동결 해시 일치: {r['predictions_equal_committed_digest']}")
        print(f"   파일만으로 F1: {r['test_predictions_f1_from_file']}; 이상 행 식별 같음: {r.get('abnormal_rows_same_ids_both_files')}")
        t = r["press_guard_tables"]; print(f"   press_guard 결과 {t['total']}개: 바이트 같음 {t['bytes_equal']}, 허용오차 안 {t['within_tol']}; 다름 {list(t['differ'])[:6]}")
        for pkg, v in r["analysis_packages"].items():
            print(f"   {pkg}: {v['bytes_equal']}/{v['total']} 바이트 같음, 허용오차 안 {v['within_tol']}; 다름 {list(v['differ'])[:5]}")
        v = r["v1_tables"]; print(f"   v1 결과 {v['present']}/{v['committed']}개 생성: 바이트 같음 {v['bytes_equal']}, 1e-3 안 {v['within_1e3']}; 다름 {list(v['differ'])[:5]}")
        if "manifest_environment" in r:
            print(f"   manifest 환경: {json.dumps(r['manifest_environment'], ensure_ascii=False)[:300]}")


if __name__ == "__main__":
    main()
