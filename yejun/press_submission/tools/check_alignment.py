"""보고서·슬라이드·README 텍스트에 numbers.json의 헤드라인 수치가 그대로 들어 있는지 검사한다 — PLAN.md §7.

    python tools/check_alignment.py --numbers outputs/numbers.json --text 보고서.txt 발표.txt

hwpx/pptx는 먼저 텍스트로 추출한다(예: `unzip -p x.hwpx Contents/section0.xml | sed 's/<[^>]*>/ /g'`).
수치는 값·단위·분모가 함께 맞아야 하므로 '21/21' 같은 표기와 소수 3~4자리 표기를 모두 찾는다.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def variants(v, item):
    out = set()
    if isinstance(v, bool):
        return out
    if isinstance(v, int):
        out.add(f"{v:,}"); out.add(str(v))
        if "denominator" in item:
            out.add(f"{v}/{item['denominator']}")
    elif isinstance(v, float):
        for d in (2, 3, 4):
            out.add(f"{v:.{d}f}")
        if 0 <= v <= 1:
            out.add(f"{v*100:.1f}%"); out.add(f"{v*100:.2f}%")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--numbers", type=Path, required=True)
    ap.add_argument("--text", type=Path, nargs="+", required=True)
    args = ap.parse_args(argv)
    nums = json.loads(args.numbers.read_text(encoding="utf-8"))
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in args.text)
    text = re.sub(r"\s+", " ", text)
    missing, found = [], []
    for k, item in nums["items"].items():
        vs = variants(item["value"], item)
        hit = next((s for s in vs if s in text), None)
        (found if hit else missing).append((k, item["value"], hit))
    for k, v, h in found:
        print(f"FOUND   {k} = {v}  ({h})")
    for k, v, h in missing:
        print(f"MISSING {k} = {v}")
    print(f"\n{len(found)}/{len(found) + len(missing)} 수치 확인. run_id {nums.get('run_id')}. 값이 있어도 모델·분할·기준·분모가 맞는지는 사람이 확인한다.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
