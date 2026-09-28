"""평가관 02 (cycle2/round3) — R2-M5 산출물 표(model_comparison_v2.md)를 GFM 표 규칙으로 렌더링해 칸 밀림을 확인한다.

- 기준 커밋 061fac8의 파일을 git show로 읽는다(작업 트리 미사용). 쓰기: 이 파일 옆 judge02_md_table.log(호출 측 tee).
- markdown-it-py의 GFM 표 규칙: 칸 안의 '|'는 '\\|'로 이스케이프해야 한다. 이스케이프하지 않은 'max|z|'는 칸 경계가 되고,
  머리글보다 많은 칸은 버려진다. 그래서 그 행의 값이 오른쪽 열로 밀린다.
실행(저장소 루트): OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
  yejun/analysis/press_rubric_review/cycle2/round3/judge02_md_table.py 2>&1 | tee yejun/analysis/press_rubric_review/cycle2/round3/judge02_md_table.log
"""
import re
import subprocess
from pathlib import Path

from markdown_it import MarkdownIt

REPO = Path(__file__).resolve().parents[5]
COMMIT = "061fac8"
PATH = "yejun/press_guard/outputs/model_comparison_v2.md"
text = subprocess.check_output(["git", "show", f"{COMMIT}:{PATH}"], cwd=REPO, text=True)
html = MarkdownIt("commonmark").enable("table").render(text)
header = re.findall(r"<th[^>]*>(.*?)</th>", html.split("</thead>")[0])
rows = [re.findall(r"<td[^>]*>(.*?)</td>", r) for r in html.split("<tbody>")[1].split("</tr>") if "<td" in r]
print(f"{COMMIT}:{PATH}")
print("머리글", len(header), "칸:", header)
src_rows = [l for l in text.splitlines() if l.startswith("| A |") or l.startswith("| B |")]
shifted = 0
for src, cells in zip(src_rows, rows):
    unescaped = len(re.findall(r"(?<!\\)\|", src)) - 1   # 칸 경계 수 = 칸 수
    if unescaped != len(header):
        shifted += 1
        show = dict(zip(header, cells))
        print(f"밀린 행: 원문 칸 {unescaped} → 렌더 {len(cells)}칸 | 모델={show.get('모델')!r} 입력 조건={show.get('입력 조건')!r} "
              f"출처={show.get('출처')!r} 미탐 행={show.get('미탐 행')!r} F1(전체 행)={show.get('F1(전체 행)')!r}")
print(f"렌더 행 {len(rows)}개 중 칸이 밀린 행 {shifted}개")
# 대조: README는 같은 표현을 'max\|z\|'로 이스케이프한다
readme = subprocess.check_output(["git", "show", f"{COMMIT}:yejun/press_guard/README.md"], cwd=REPO, text=True)
print("README의 이스케이프 표기 'max\\|z\\|' 사용:", "max\\|z\\|" in readme)
