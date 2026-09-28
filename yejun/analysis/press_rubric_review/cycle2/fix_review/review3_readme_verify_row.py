"""검토 3: 수정 커밋 README의 verify 설명이 코드(verify.py)와 맞는가, 그리고 GFM 표로 렌더링하면 칸이 온전한가.

    REVIEW_ENV=<사본의 yejun 폴더> python review3_readme_verify_row.py
markdown-it-py(GFM 표 규칙: 칸 안의 이스케이프 안 된 |는 칸 구분자)로 README '검증' 표를 렌더링해 verify 행의 둘째 칸을 뽑는다.
"""
import os, re, sys
from pathlib import Path
from markdown_it import MarkdownIt

ENV = Path(os.environ["REVIEW_ENV"])
readme = (ENV / "press_guard" / "README.md").read_text(encoding="utf-8")
sys.path.insert(0, str(ENV / "press_guard"))
src = (ENV / "press_guard" / "verify.py").read_text(encoding="utf-8")

print("## 코드(verify.py)의 허용오차 상수")
for name in ("TOL", "RTOL", "ROW_RTOL, ROW_ATOL", "ECDF_G_MAX, ECDF_ROW_ATOL, ECDF_SUMMARY_RTOL"):
    m = re.search(rf"^{re.escape(name)} = (.+)$", src, re.M)
    print(f"  {name} = {m.group(1).split('#')[0].strip() if m else '(없음)'}")
m = re.search(r'def prediction_digest.*?\n    """(.+?)"""', src, re.S)
print("  prediction_digest 설명:", m.group(1).strip() if m else "")

print("\n## README에서 verify 규칙을 적은 줄")
for i, line in enumerate(readme.splitlines(), 1):
    if "0.001 격자" in line or "1e-9·|값|" in line:
        print(f"  {i}: {line[:170]}")

print("\n## GFM 렌더링: '검증' 표의 verify 행")
md = MarkdownIt("commonmark").enable("table")
section = readme.split("## 검증", 1)[1].split("\n## ", 1)[0]
tokens = md.parse(section)
rows, cur, cell = [], None, None
for t in tokens:
    if t.type == "tr_open": cur = []
    elif t.type in ("td_open", "th_open"): cell = ""
    elif t.type == "inline" and cell is not None: cell += t.content
    elif t.type in ("td_close", "th_close"): cur.append(cell); cell = None
    elif t.type == "tr_close": rows.append(cur)
for r in rows:
    if "verify.py" in r[0]:
        print("  칸 수:", len(r))
        print("  첫 칸:", r[0])
        print("  둘째 칸(렌더링된 내용 전체):", repr(r[1]))
src_row = [l for l in section.splitlines() if "verify.py" in l][0]
print("  원문 행의 이스케이프 안 된 '|' 수(행 끝 포함):", len(re.findall(r"(?<!\\)\|", src_row)))
