"""review4: 마크다운 표의 칸 수 점검(이스케이프되지 않은 | 검출). GFM 규칙: 표 안에서는 인라인 코드 안의 |도 칸 구분자다."""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = sys.argv[2:] or [str(p.relative_to(root)) for p in root.rglob("*.md")]


def cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return re.split(r"(?<!\\)\|", s)


bad = 0
for rel in files:
    p = root / rel
    lines = p.read_text(encoding="utf-8").splitlines()
    i = 0
    in_code = False
    while i < len(lines):
        if lines[i].lstrip().startswith("```"):
            in_code = not in_code
        if (not in_code and i + 1 < len(lines) and lines[i].lstrip().startswith("|")
                and re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", lines[i + 1])):
            ncol = len(cells(lines[i]))
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                k = len(cells(lines[j]))
                if k != ncol:
                    bad += 1
                    print(f"{rel}:{j + 1}: 칸 {k} (머리 {ncol}) :: {lines[j][:160]}")
                j += 1
            i = j
            continue
        i += 1
print("불일치 행", bad)
