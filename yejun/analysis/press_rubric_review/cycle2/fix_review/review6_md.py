"""검토 6 문서 형식 검사: 대상 문서의 마크다운 표 칸 수(이스케이프 안 된 | 포함)와 상대 링크 대상 존재를 확인한다.

    python review6_md.py <사본>/yejun
GFM 규칙: 표 칸은 이스케이프(\\|)되지 않은 |로 나뉜다(코드 스팬 안이어도 같다). 머리 행의 칸 수와 다른 행을 적는다.
링크: [글](경로) 가운데 http·#·mailto가 아닌 것을 문서 위치 기준으로 풀어 파일·폴더 존재를 본다(#앵커는 떼고 본다).
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
DOCS = ["press_guard/README.md", "press_guard/OPERATIONS.md", "analysis/press_evidence/README.md",
        "analysis/press_selection/README.md", "analysis/press_rubric_review/cycle2/README.md",
        "analysis/press_selection/unified_comparison.md", "press_guard/outputs/model_comparison_v2.md", "press_guard/HISTORY.md"]
SPLIT = re.compile(r"(?<!\\)\|")
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)|!\[([^\]]*)\]\(([^)\s]+)\)")

bad_tables, bad_links, n_tables, n_links = [], [], 0, 0
for rel in DOCS:
    p = ROOT / rel
    lines = p.read_text(encoding="utf-8").splitlines()
    in_code = False
    header = None
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        s = line.strip()
        if s.startswith("|"):
            cells = len(SPLIT.split(s)) - 2
            if header is None:
                header = (i, cells); n_tables += 1
            elif cells != header[1]:
                bad_tables.append(f"{rel}:{i} 칸 {cells} (머리 {header[0]}행 {header[1]})")
        else:
            header = None
        for m in LINK.finditer(line):
            target = m.group(2) or m.group(4)
            if target.startswith(("http", "#", "mailto:")):
                continue
            n_links += 1
            path = target.split("#")[0]
            if not (p.parent / path).exists():
                bad_links.append(f"{rel}:{i} → {target}")
print(f"표 {n_tables}개 검사, 칸 수가 다른 행 {len(bad_tables)}개")
print("\n".join(bad_tables))
print(f"상대 링크 {n_links}개 검사, 대상 없음 {len(bad_links)}개")
print("\n".join(bad_links))
