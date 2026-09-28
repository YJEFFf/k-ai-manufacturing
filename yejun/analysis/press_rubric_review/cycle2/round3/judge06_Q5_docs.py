"""평가관 06 사이클2 3회차 Q5d — 제출 목록(package_manifest.py 출력 CSV)에 든 문서의 죽은 링크·내부 표기·절대 경로 점검(R2-08).

    python judge06_Q5_docs.py <목록 CSV> <목록 사본 루트(yejun/의 부모)>

- 링크: 목록에 든 .md의 [글](대상) 가운데 http·mailto·#만 있는 것을 뺀 상대 링크를 문서 위치 기준으로 풀어,
        목록에 그 파일이 있는지(폴더면 목록에 그 아래 파일이 있는지) 본다. 실행하면 생기는 Git 제외 파일(행 단위 예측 등)은 따로 센다.
- 내부 표기: 평가관·사이클·round·R2- 같은 검수 표기
- 결과: 이 폴더의 judge06_Q5_docs.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath

import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
LINK = re.compile(r"(?<!\!)\[([^\]]*)\]\(([^)\s]+)\)")
IMG = re.compile(r"\!\[([^\]]*)\]\(([^)\s]+)\)")
INTERNAL = re.compile(r"(평가관|사이클\s?2|cycle2|round[123]|루브릭 검수|press_rubric_review|R2-\d)")
REGEN = re.compile(r"(press_guard/outputs/(test_)?predictions_|press_guard/artifacts/|press_submission/outputs/(predictions_|records_)|reproduce_summary|reproduce_logs)")


def norm(p: str) -> str:
    parts = []
    for s in PurePosixPath(p).parts:
        if s == "..":
            if parts:
                parts.pop()
        elif s != ".":
            parts.append(s)
    return "/".join(parts)


def main():
    lst, root = Path(sys.argv[1]), Path(sys.argv[2])
    listed = set(pd.read_csv(lst).path)
    dirs = {str(PurePosixPath(p).parent) for p in listed}
    alldirs = set()
    for d in dirs:
        parts = d.split("/")
        for k in range(1, len(parts) + 1):
            alldirs.add("/".join(parts[:k]))
    dead, regen, internal, checked = [], [], [], 0
    for rel in sorted(p for p in listed if p.endswith(".md")):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        base = str(PurePosixPath(rel).parent)
        for i, line in enumerate(text.splitlines(), 1):
            for m in list(LINK.finditer(line)) + list(IMG.finditer(line)):
                target = m.group(2)
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path = target.split("#")[0]
                if not path:
                    continue
                checked += 1
                t = norm(f"{base}/{path}")
                if t in listed or t.rstrip("/") in alldirs:
                    continue
                item = dict(file=rel, line=i, target=target, resolved=t)
                (regen if REGEN.search(t) else dead).append(item)
            if INTERNAL.search(line):
                internal.append(dict(file=rel, line=i, text=line.strip()[:180]))
    res = dict(list=str(lst), listed_files=len(listed), md_files=sum(p.endswith(".md") for p in listed), links_checked=checked,
               dead_links=dead, links_to_regenerated_files=regen, internal_markers=internal)
    (HERE / "judge06_Q5_docs.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"목록 {len(listed)}개 · 문서 {res['md_files']}개 · 상대 링크 {checked}개 · 죽은 링크 {len(dead)}개 · 실행 시 생기는 파일로 가는 링크 {len(regen)}개 · 내부 표기 {len(internal)}행")
    for d in dead:
        print(f"  죽은 링크 {d['file']}:{d['line']} → {d['target']} ({d['resolved']})")
    for d in regen:
        print(f"  실행 뒤 생기는 파일 {d['file']}:{d['line']} → {d['target']}")
    for d in internal:
        print(f"  내부 표기 {d['file']}:{d['line']} {d['text'][:120]}")


if __name__ == "__main__":
    main()
