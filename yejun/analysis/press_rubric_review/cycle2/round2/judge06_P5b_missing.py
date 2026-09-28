"""평가관 06 사이클2 2회차 P5b — 패키지 목록(package_manifest.py)에서 빠진 파일 찾기.

커밋된 실행 기록(manifest)들이 "이 결과를 만들 때 읽었다"고 적은 파일을 모아, P5가 계산한 패키지 목록(package_list.csv)에 없는 것을 찾는다.
실행하면 다시 생기는 Git 제외 파일(저장 모델·행별 예측)은 빼고, 커밋된 파일인데 목록에 없는 것만 남긴다.
P5 복사본의 단계 로그에 찍힌 FileNotFoundError 경로도 함께 적는다. 결과: judge06_P5b_missing.json

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python judge06_P5b_missing.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
COMMIT = "f5679ca"
BASE = Path(os.environ.get("J06_BASE", "/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/judge06r2"))
LIST = BASE / "P5_package" / "package_list.csv"
LOGS = BASE / "P5_package" / "pkg" / "press_guard" / "outputs" / "reproduce_logs"
REGEN = re.compile(r"(press_guard/artifacts/|press_guard/outputs/(test_)?predictions_|press_submission/outputs/predictions_|press_submission/artifacts/|segment_metrics\.csv$)")


def show_json(rel):
    r = subprocess.run(["git", "-C", str(REPO), "show", f"{COMMIT}:yejun/{rel}"], capture_output=True)
    return json.loads(r.stdout) if r.returncode == 0 else {}


def tracked():
    out = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", COMMIT, "yejun/"], capture_output=True, text=True, encoding="utf-8").stdout
    return {p[len("yejun/"):] for p in out.split()}


def norm(key: str, pkg: str | None) -> list[str]:
    """실행 기록의 키를 yejun 기준 경로 후보로 바꾼다(package_contract.resolve의 auto 규칙과 같은 순서)."""
    k = key.replace("\\", "/")
    if k.startswith("yejun/"):
        return [k[len("yejun/"):]]
    cands = []
    if pkg:
        cands.append(f"analysis/{pkg}/{k}")
    cands += [k, f"analysis/{k}"]
    return cands


def main():
    listed = set(pd.read_csv(LIST).path)
    git_files = tracked()
    deps: dict[str, set[str]] = {}

    def add(src, key, pkg=None):
        for c in norm(key, pkg):
            if c in git_files or REGEN.search(c):
                deps.setdefault(c, set()).add(src)
                return

    m = show_json("press_guard/outputs/manifest.json")
    for k in (m.get("analysis", {}).get("sources") or {}):
        add("press_guard manifest.analysis.sources", k)
    for k in (show_json("press_guard/outputs/analysis_summary.json").get("external_inputs") or {}):
        add("press_guard analysis_summary.external_inputs", k)
    for name, groups in (("press_evidence/manifest.json", ("code_sha256", "sources")),
                         ("press_evidence/diagnostics_manifest.json", ("code_sha256", "sources", "cited")),
                         ("press_selection/manifest.json", ("code_sha256", "dependencies_sha256")),
                         ("press_supervised/manifest.json", ("code_sha256", "dependencies"))):
        mm = show_json(f"analysis/{name}")
        pkg = name.split("/")[0]
        for g in groups:
            for k in (mm.get(g) or {}):
                add(f"{name}:{g}", k, pkg)
    for e in ("e1", "e2", "e3"):
        mm = show_json(f"analysis/press_supplement/{e}_manifest.json")
        for g in ("code", "sources"):
            for k in (mm.get(g) or {}):
                add(f"press_supplement/{e}_manifest.json:{g}", k.split(" (")[0], None)
    missing = {p: sorted(s) for p, s in sorted(deps.items()) if p not in listed and not REGEN.search(p)}
    regex_excluded = [p for p in git_files if "/predictions_" in p and p.startswith("press_guard/outputs/expected/")]
    not_found = sorted({m.group(1).replace(str(BASE), "<J06>") for f in sorted(LOGS.glob("*.log"))
                        for m in re.finditer(r"No such file or directory: '([^']+)'", f.read_text(encoding="utf-8", errors="replace"))})
    integrity = sorted({line.strip()[:200] for f in sorted(LOGS.glob("*.log")) for line in f.read_text(encoding="utf-8", errors="replace").splitlines()
                        if "파일 없음" in line or "없음 —" in line or ": 없음" in line})
    result = dict(commit=COMMIT, listed_files=len(listed), recorded_dependencies=len(deps), missing_committed_dependencies=missing,
                  excluded_by_regex_in_expected=regex_excluded, step_log_file_not_found=not_found, step_log_missing_lines=integrity[:40])
    (HERE / "judge06_P5b_missing.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"목록 {len(listed)}개 · 실행 기록이 적은 의존 파일 {len(deps)}개 · 커밋돼 있는데 목록에 없는 의존 파일 {len(missing)}개")
    for p, s in missing.items():
        print(f"  - {p}  ← {', '.join(s)[:150]}")
    print(f"EXCLUDE 정규식(/predictions_)에 걸려 빠진 동결값: {regex_excluded}")
    print("P5 복사본 단계 로그의 FileNotFoundError:", not_found)


if __name__ == "__main__":
    main()
