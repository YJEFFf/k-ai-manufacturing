"""최종 패키지(프레스 ③) 파일 목록 계산 — 목록·SHA-256·블라인드 검사, 그리고 목록만 복사한 사본에서 한 명령 재현 시험. ZIP은 만들지 않는다.

    python yejun/press_guard/tools/package_manifest.py [--out 목록.csv]           # 목록·검사
    python yejun/press_guard/tools/package_manifest.py --copy-test <빈 폴더>        # 목록만 복사한 사본에서 reproduce.py 실행

- 목록의 경로는 저장소 루트 기준(yejun/...)이다. 묶음 최상위에 yejun/을 두면 README 명령(python yejun/press_guard/reproduce.py)이
  그대로 실행된다.
- 넣는 것: 최종 모델 코드(press_guard), 선행 v1 패키지(press_submission, 커밋된 결과·동결값 포함), 후보 비교(press_advance),
  실행 기록이 인용하는 의존 파일(press_dayshift·press_improvement·press_early·press_external 일부), 분석 패키지, 의존성 파일,
  학습용 원본 CSV 2개, 저장 모델·확률 보정기, 테스트 예측 파일(분할별 1개), README·운영 절차서.
- 빼는 것: 검수·작업 기록(analysis/press_rubric_review, press_guard/HISTORY.md, 각 폴더의 작업 README가 아닌 기록), 캐시,
  다시 만들어지는 행 단위 중간 예측(press_guard/outputs/predictions_*, press_submission/outputs/predictions_*·records_*), 로그.
- 블라인드 검사: 필수 파일, 실행 기록(manifest의 sources·cited·dependencies·external_inputs 등)이 가리키는 파일의 존재,
  넣을 문서·코드·실행 기록 JSON의 절대 경로(/Users/, /Volumes/, /opt/anaconda3, C:\\)를 본다.
- 대회 제출 ZIP 조립은 예준의 지시 전까지 보류한다(yejun/AGENTS.md). 이 도구는 목록과 복사 시험까지만 한다.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
YEJUN = HERE.parent
REPO = YEJUN.parent
# (묶음, 폴더(yejun 기준), 넣을 파일 패턴). 패턴은 git이 추적하는 파일에 적용하고, git이 없으면 폴더를 훑는다.
GROUPS = [
    ("final_model", "press_guard", ["*"]),
    ("baseline_v1", "press_submission", ["*"]),
    ("candidates", "analysis/press_advance", ["*"]),
    ("supporting", "analysis/press_evidence", ["*"]),
    ("supporting", "analysis/press_supplement", ["*"]),
    ("supporting", "analysis/press_supervised", ["*"]),
    ("supporting", "analysis/press_selection", ["*"]),
    ("supporting", "analysis", ["package_contract.py"]),
    ("dependency", "analysis/press_dayshift", ["v2_current_scale.csv"]),
    ("dependency", "analysis/press_improvement", ["candidate_metrics.csv", "run_experiment.py", "config.json"]),
    ("dependency", "analysis/press_early", ["metrics.csv", "primary.csv", "run_experiment.py", "protocol.json"]),
    ("dependency", "analysis/press_external", ["acquire.py", "acquisition.json", "metrics.csv", "partitions.csv"]),
]
# Git에서 뺀 파일 가운데 묶음에 넣을 것(실행하면 다시 생기지만, 테스트 예측과 저장 모델은 제출물이다)
GENERATED = [
    ("training_data", "press_submission/data/3_소성가공_예지보전/press_data_normal.csv"),
    ("training_data", "press_submission/data/3_소성가공_예지보전/outlier_data.csv"),
    ("final_model", "press_guard/artifacts/guard_A.json"), ("final_model", "press_guard/artifacts/guard_B.json"),
    ("final_model", "press_guard/artifacts/probability_A.json"), ("final_model", "press_guard/artifacts/probability_B.json"),
    ("test_predictions", "press_guard/outputs/test_predictions_A.csv"), ("test_predictions", "press_guard/outputs/test_predictions_B.csv"),
]
EXCLUDE = re.compile(r"(__pycache__|\.pytest_cache|\.DS_Store|reproduce_logs|reproduce_summary\.json|lstm_cache"
                     r"|^press_guard/HISTORY\.md$|^press_guard/outputs/predictions_|^press_submission/outputs/(predictions_|records_)"
                     r"|^press_guard/outputs/demo|^press_submission/PLAN\.md$)")
REQUIRED = ["press_guard/reproduce.py", "press_guard/requirements.txt", "press_guard/environment.yml", "press_guard/README.md",
            "press_guard/OPERATIONS.md", "press_guard/outputs/expected/predictions_digest.json", "press_submission/run_all.py",
            "press_submission/outputs/expected/manifest.json", "press_submission/outputs/model_comparison_all.csv"] + [p for _, p in GENERATED]
ABSOLUTE = re.compile(r"(/Users/|/Volumes/|/opt/anaconda3|[A-Z]:\\\\)")
TEXT = (".py", ".md", ".sh", ".txt", ".yml", ".html", ".js", ".json", ".cjs", ".css")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked(folder):
    try:
        # 추적 파일 + 아직 커밋하지 않았지만 무시 규칙에 걸리지 않는 새 파일
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", f"yejun/{folder}"],
                             capture_output=True, check=True).stdout
        return [Path(p).relative_to("yejun").as_posix() for p in out.decode("utf-8").split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        return [p.relative_to(YEJUN).as_posix() for p in (YEJUN / folder).rglob("*") if p.is_file()]


def collect():
    rows, seen = [], set()
    for group, folder, patterns in GROUPS:
        files = tracked(folder)
        for rel in sorted(files):
            name = rel[len(folder) + 1:] if folder != "analysis" else rel[len("analysis/"):]
            if "*" not in patterns and name not in patterns:
                continue
            if rel in seen or EXCLUDE.search(rel) or not (YEJUN / rel).is_file():
                continue
            seen.add(rel)
            rows.append(dict(group=group, path=f"yejun/{rel}", bytes=(YEJUN / rel).stat().st_size, sha256=sha(YEJUN / rel)))
    for group, rel in GENERATED:
        if rel not in seen and (YEJUN / rel).is_file():
            seen.add(rel)
            rows.append(dict(group=group, path=f"yejun/{rel}", bytes=(YEJUN / rel).stat().st_size, sha256=sha(YEJUN / rel)))
    return pd.DataFrame(rows)


def cited_paths():
    """실행 기록이 가리키는 파일(yejun 기준): v2 SOURCES와 분석 요약의 외부 입력, 분석 패키지 manifest의 의존·인용 묶음."""
    sys.path.insert(0, str(HERE))
    from contracts import SOURCES
    paths = set(SOURCES)
    summary = json.loads((HERE / "outputs" / "analysis_summary.json").read_text(encoding="utf-8"))
    paths |= set(summary.get("external_inputs", {}))
    for m in list((YEJUN / "analysis").glob("press_*/manifest.json")) + list((YEJUN / "analysis").glob("press_*/*_manifest.json")):
        pkg = m.parent.name
        if pkg not in ("press_advance", "press_evidence", "press_supplement", "press_supervised", "press_selection"):
            continue
        data = json.loads(m.read_text(encoding="utf-8"))
        for key in ("dependencies", "dependencies_sha256", "cited", "sources", "code_sha256", "code"):
            group = data.get(key)
            if isinstance(group, dict):
                for k in group:
                    k = str(k).removeprefix("yejun/")
                    if "/" in k and not k.startswith(("press_submission/press/*", "http")) and "(" not in k:
                        paths.add(k if (YEJUN / k).exists() or k.startswith(("press_", "analysis/")) else f"analysis/{pkg}/{k}")
    return sorted(p for p in paths if not p.endswith("/"))


def blind_checks(table):
    listed = {p.removeprefix("yejun/") for p in table.path}
    problems = [f"필수 파일 없음: {r}" for r in REQUIRED if r not in listed]
    # 실행하면 다시 생기는 행 단위 파일(EXCLUDE)은 목록에 없어도 된다
    problems += [f"실행 기록이 가리키는 파일이 목록에 없음: {c}" for c in cited_paths()
                 if c not in listed and (YEJUN / c).is_file() and not EXCLUDE.search(c)]
    for rel in table.path:
        if rel.endswith(TEXT) and rel != "yejun/press_guard/tools/package_manifest.py":
            text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            hits = sorted(set(ABSOLUTE.findall(text)))
            if hits:
                problems.append(f"절대 경로 {hits}: {rel}")
    problems += document_link_checks(table)
    return problems


def document_link_checks(table):
    """포함 문서의 상대 링크가 목록 안의 파일/폴더를 가리키는지 검사한다. 외부 URL·문서 내 앵커는 제외한다."""
    included = {(REPO / rel).resolve() for rel in table.path}
    problems = []
    for rel in table.path:
        path = REPO / rel
        if path.suffix.lower() != ".md":
            continue
        content = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        links = re.findall(r"!?\[[^\]]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", content)
        links += re.findall(r"^\s*\[[^\]]+\]:\s*(<[^>]+>|\S+)", content, flags=re.M)
        for raw in links:
            target = raw.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            if resolved not in included and not (resolved.is_dir() and any(resolved in p.parents for p in included)):
                problems.append(f"문서 상대 링크가 목록에 없음: {rel} → {target}")
    return problems


def copy_test(table, dest):
    """목록의 파일만 dest에 복사하고 그 사본에서 한 명령 재현을 실행한다(원본 CSV는 목록에 들어 있다)."""
    dest = Path(dest).resolve()
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest}가 비어 있지 않다")
    for rel in table.path:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO / rel, target)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, str(dest / "yejun/press_guard/reproduce.py")], cwd=dest, env=env)
    return proc.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, help="목록 CSV")
    ap.add_argument("--copy-test", type=Path, help="빈 폴더: 목록만 복사해 reproduce.py를 돌린다")
    ap.add_argument("--zip", action="store_true", help="보류: ZIP 생성은 예준의 지시 전까지 하지 않는다")
    args = ap.parse_args()
    if args.zip:
        print("ZIP 조립은 보류 중이다(yejun/AGENTS.md: 최종 제출물 조립은 예준의 명시적 지시 뒤에). 목록만 계산한다.", file=sys.stderr)
        return 2
    table = collect()
    if args.out:
        table.to_csv(args.out, index=False)
    by_group = table.groupby("group").agg(files=("path", "size"), megabytes=("bytes", lambda b: round(b.sum() / 2 ** 20, 2)))
    print(by_group.to_string())
    print(f"합계 {len(table)}개 · {table.bytes.sum() / 2 ** 20:.1f} MB")
    problems = blind_checks(table)
    for p in problems:
        print("검사 실패:", p)
    print("블라인드 검사 통과" if not problems else f"블라인드 검사 {len(problems)}건")
    if args.copy_test and not problems:
        rc = copy_test(table, args.copy_test)
        print(f"목록 사본의 한 명령 재현: 종료 코드 {rc}")
        return rc
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
