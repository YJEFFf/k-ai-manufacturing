"""적대적 검수자 D — 문서에서 수치가 든 문장을 기계적으로 뽑는다.

읽기 전용이다. 저장소의 생성 스크립트를 실행하지 않는다.
산출: redD_claims_raw.csv (문서·행·문장·수치 목록), redD_table_notes.csv (표의 설명 열), redD_extract_claims.log
실행: OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python redD_extract_claims.py
"""
from __future__ import annotations

import csv
import html
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]  # .../k-제조데이터
YEJUN = REPO / "yejun"
COMMIT = "cc1aac2"

DOCS = [
    "yejun/press_guard/README.md",
    "yejun/press_guard/OPERATIONS.md",
    "yejun/press_guard/web/index.html",
    "yejun/press_guard/web/app.js",
    "yejun/press_submission/README.md",
    "yejun/press_submission/outputs/diagnosis.md",
    "yejun/analysis/press_evidence/README.md",
    "yejun/analysis/press_selection/README.md",
    "yejun/analysis/press_supervised/README.md",
    "yejun/analysis/press_supplement/README.md",
    "yejun/analysis/press_advance/README.md",
]

# 표의 설명 열(문서로 본다)
NOTE_COLUMNS = {
    "note", "remark", "limitation", "reading", "source", "incident_note", "sbb_note",
    "statistical_scope", "comparison", "evidence", "definition", "proxy_definition",
    "ci_method", "quartile_ci_method", "interaction_comparison", "key_terms",
    "source_downtime", "source_detect_basis", "level2_basis", "decision", "alternatives",
    "interpretation", "team_rule", "hypothesis", "confirmed", "basis", "meaning", "caveat",
}

TABLE_DIRS = [
    "yejun/press_guard/outputs",
    "yejun/analysis/press_evidence",
    "yejun/analysis/press_selection",
    "yejun/analysis/press_supervised",
    "yejun/analysis/press_supplement",
    "yejun/analysis/press_advance",
    "yejun/press_submission/outputs",
]

NUM = re.compile(r"(?<![A-Za-z_#/\-])[-+−]?\d[\d,]*(?:\.\d+)?(?:e[-+]?\d+)?%?", re.IGNORECASE)


def git_show(path: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{COMMIT}:{path}"],
        capture_output=True, check=True,
    )
    return out.stdout.decode("utf-8")


def tracked(prefix: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "-c", "core.quotepath=off", "ls-tree", "-r", "--name-only", COMMIT, prefix],
        capture_output=True, check=True,
    )
    return [p for p in out.stdout.decode("utf-8").splitlines() if p]


def strip_html(text: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(text)


def split_sentences(line: str) -> list[str]:
    parts = re.split(r"(?<=[다요음임함됨])\.\s+|(?<=\))\.\s+|\s\|\s", line)
    return [p.strip() for p in parts if p and p.strip()]


def main() -> int:
    rows = []
    per_doc = {}
    for doc in DOCS:
        text = git_show(doc)
        worktree = (REPO / doc).read_text(encoding="utf-8")
        same = text == worktree
        n_lines = text.count("\n") + 1
        n_num_lines = 0
        n_claims = 0
        in_code = False
        for i, raw in enumerate(text.splitlines(), 1):
            line = raw
            if doc.endswith(".md"):
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code:
                    continue
            if doc.endswith(".html"):
                line = strip_html(line)
            if doc.endswith(".js"):
                # 한글이 든 문자열·주석만 화면 문구·설명으로 본다
                if not re.search(r"[가-힣]", line):
                    continue
                line = strip_html(line)
            if not NUM.search(line):
                continue
            n_num_lines += 1
            for sent in split_sentences(line):
                nums = [m.group(0) for m in NUM.finditer(sent)]
                if not nums:
                    continue
                n_claims += 1
                rows.append({
                    "doc": doc, "line": i, "n_numbers": len(nums),
                    "numbers": " ".join(nums), "sentence": sent[:1500],
                })
        per_doc[doc] = (n_lines, n_num_lines, n_claims, same)

    with (HERE / "redD_claims_raw.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["doc", "line", "n_numbers", "numbers", "sentence"])
        w.writeheader()
        w.writerows(rows)

    # 표의 설명 열
    note_rows = []
    table_count = {}
    for d in TABLE_DIRS:
        files = [p for p in tracked(d) if p.endswith(".csv") and "/expected/" not in p]
        if d.endswith("press_guard/outputs") or d.endswith("press_submission/outputs"):
            files = [p for p in files if p.count("/") == d.count("/") + 1]
        else:
            files = [p for p in files if p.count("/") == d.count("/") + 1]
        table_count[d] = len(files)
        for p in files:
            text = git_show(p)
            reader = csv.reader(text.splitlines())
            try:
                header = next(reader)
            except StopIteration:
                continue
            idx = [(k, h) for k, h in enumerate(header) if h.strip().lower() in NOTE_COLUMNS]
            if not idx:
                continue
            seen = set()
            for r_i, r in enumerate(reader, 2):  # 파일의 행 번호(머리글이 1행)
                for k, h in idx:
                    if k >= len(r):
                        continue
                    v = r[k].strip()
                    if not v or (p, h, v) in seen:
                        continue
                    seen.add((p, h, v))
                    note_rows.append({"file": p, "line": r_i, "column": h, "has_number": int(bool(NUM.search(v))), "text": v[:3000]})

    with (HERE / "redD_table_notes.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "line", "column", "has_number", "text"])
        w.writeheader()
        w.writerows(note_rows)

    log = []
    log.append(f"기준 커밋 {COMMIT}")
    log.append("문서별: 전체 행 / 수치가 든 행 / 수치 문장(칸) / 작업 사본이 커밋과 같은가")
    tot = [0, 0, 0]
    for doc, (a, b, c, same) in per_doc.items():
        log.append(f"  {doc}: {a} / {b} / {c} / {same}")
        tot[0] += a; tot[1] += b; tot[2] += c
    log.append(f"  합계: {tot[0]} / {tot[1]} / {tot[2]}")
    log.append(f"수치 토큰 합계: {sum(r['n_numbers'] for r in rows)}")
    log.append("표의 설명 열(중복 제거):")
    for d, n in table_count.items():
        k = sum(1 for r in note_rows if r["file"].startswith(d + "/"))
        kn = sum(1 for r in note_rows if r["file"].startswith(d + "/") and r["has_number"])
        log.append(f"  {d}: CSV {n}개, 설명 칸 {k}개(수치 포함 {kn}개)")
    (HERE / "redD_extract_claims.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
