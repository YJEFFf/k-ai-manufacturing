"""본문(md 또는 hwpx에서 뽑은 텍스트)의 숫자를 facts.csv와 대조한다.

허용 목록: 장·절 번호, 배점, 날짜·시각, α, 설계 상수(규칙 값·분할 경계·주입 강도·seed), 모델·규칙 이름의 숫자.
사용: python check_facts.py draft_v1.md   → 근거 없는 숫자를 줄 번호와 함께 출력, 없으면 종료 코드 0
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
FACTS = pd.read_csv(HERE / "facts.csv", encoding="utf-8-sig")

# 설계 상수·표기용 숫자 (근거: 계획 v4·코드 상수·양식)
WHITELIST = {
    # 배점·장·절
    "15", "40", "10", "1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "3.2", "3.3", "3.4",
    "4.1", "4.2", "4.3", "4.4", "3.5", "3.6", "1.6", "1.7", "6",
    # 날짜·시각·기간
    "2022", "07", "12", "17", "00", "01", "10", "51", "53", "7", "2", "46", "3", "5", "77", "33",
    # 수집 구조·전처리 상수
    "0.1", "50", "1e-4", "1.1920929", "1.192", "60", "8", "0.5", "0.60", "6", "4",
    # 분할 경계
    "0", "359", "360", "479", "480", "599", "299", "300", "419", "420", "11", "21", "600",
    # α·판정 상수·주입 설계
    "1", "2", "3", "5", "0.01", "0.002", "90", "29", "47", "0.75", "0.25", "60.6", "81.4", "272.4", "20",
    # 모델·규칙·case 이름의 숫자(v1 v2 v3 R1 R2 FM1~6 D1~3 V0~5 AR(2) P2 k5 k10)
    "9", "100",
    # 실행 스크립트 번호
    "01", "02", "03", "04", "05", "06",
    # 데이터 출처 표기 날짜(KAMP 양식)
    "2022.12",
}
NAME_PATTERN = re.compile(r"(?:v|R|FM|D|V|H|P|AR\(|k|B3k|lag-|C[12]d|O)\d+|\d+_[a-z]+\.py|제\d장|〔\d+점〕|그림 \d+|\d+행 창|[A-Z]\d"
                          r"|\[\d+\]|ISO \d+(?:-\d+)?(?::\d+)?|ISA-\d+\.\d+|VG \d+|\d\.\d절|\d\.\d·\d\.\d절")
REF_LINE = re.compile(r"^\s*\* \[\d+\]")   # 참고문헌 줄(서지 숫자)은 대조하지 않는다
NUM = re.compile(r"(?<![\w.])[-−+]?\d[\d,]*(?:\.\d+)?(?:e-\d+)?")


def allowed_values():
    shown = set(FACTS["shown"].astype(str))
    extra = set()
    for s in shown:
        extra.add(s.lstrip("+-−"))
        extra.add(s.replace(",", ""))
    return shown | extra | WHITELIST


def main(path):
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        head, body = text[3:].split("---", 1)
        text = "\n" * (head.count("\n") + 1) + body   # 머리말 제외(줄 번호 유지)
    ok = allowed_values()
    bad = []
    for no, line in enumerate(text.splitlines(), 1):
        if REF_LINE.match(line):
            continue
        clean = NAME_PATTERN.sub(" ", line)
        for m in NUM.finditer(clean):
            tok = m.group().replace("−", "-").lstrip("+")
            tok_n = tok.lstrip("-").replace(",", "") if tok.count(",") and "." not in tok else tok.lstrip("-")
            if tok_n in ok or tok in ok:
                continue
            bad.append((no, m.group(), line.strip()[:110]))
    for no, tok, line in bad:
        print(f"{no:4d}  {tok:>10}  | {line}")
    print(f"근거 없는 숫자: {len(bad)}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else HERE / "draft_v1.md"))
