"""평가관 06 사이클2 3회차 Q7 — 실행 기록(manifest 등)과 제출 목록 사본의 절대 경로 점검.

    python judge06_Q7_abs_paths.py <이름> <루트> [<루트> ...]

각 루트(yejun/의 부모) 아래 yejun/의 텍스트 파일(.json .csv .md .py .txt .yml .sh .html .js .cjs .css)에서
개발 기기·임시 폴더 절대 경로(/Volumes/, /Users/, /opt/anaconda3, /private/tmp, /private/var, /tmp/, C:\\, 평가관 임시 폴더 이름)를 찾는다.
실행 기록(파일 이름에 manifest가 들어가거나 analysis_summary·numbers·checks·audit·lock·reproduce_summary)과 그 밖을 나눠 센다.
결과: 이 폴더의 judge06_Q7_abs_paths_<이름>.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PAT = re.compile(r"(/Volumes/|/Users/|/opt/anaconda3|/private/tmp|/private/var|(?<![\w.])/tmp/|[A-Z]:\\\\|judge06r3)")
TEXT = (".json", ".csv", ".md", ".py", ".txt", ".yml", ".sh", ".html", ".js", ".cjs", ".css")
RECORD = re.compile(r"(manifest|analysis_summary|numbers|checks|audit|lock|reproduce_summary)[^/]*\.json$")
SKIP = re.compile(r"(reproduce_logs/|__pycache__|\.pytest_cache|press_rubric_review/)")


def scan(root: Path):
    hits = []
    for p in sorted((root / "yejun").rglob("*")):
        rel = p.relative_to(root).as_posix()
        if not p.is_file() or not rel.endswith(TEXT) or SKIP.search(rel):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        found = sorted(set(m.group(1) for m in PAT.finditer(text)))
        if found:
            kinds = {}
            for m in PAT.finditer(text):
                kinds[m.group(1)] = kinds.get(m.group(1), 0) + 1
            first = next(PAT.finditer(text))
            ctx = text[max(0, first.start() - 60): first.end() + 80].replace("\n", " ")
            hits.append(dict(file=rel, record=bool(RECORD.search(rel)), patterns=kinds, context=ctx))
    return hits


def main():
    name, roots = sys.argv[1], [Path(r) for r in sys.argv[2:]]
    out = {}
    for r in roots:
        hits = scan(r)
        out[str(r)] = hits
        rec = [h for h in hits if h["record"]]
        print(f"{r}: 절대 경로가 든 파일 {len(hits)}개(실행 기록 {len(rec)}개)")
        for h in hits:
            print(f"  {'[기록]' if h['record'] else '      '} {h['file']} {h['patterns']} … {h['context'][:150]}")
    (HERE / f"judge06_Q7_abs_paths_{name}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
