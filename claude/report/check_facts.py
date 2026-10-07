"""보고서 원고의 숫자가 모두 근거표(facts.csv)나 허용 목록에 있는지 확인한다.

입력: 원고 md(기본 final_v5.md), 같은 폴더의 facts.csv(facts_build.py가 만든다)
출력: 근거 없는 숫자를 줄 번호와 함께 출력, 마지막 줄에 "근거 없는 숫자: N개". 0개면 종료 코드 0
실행: python report/check_facts.py [원고.md]
허용 목록: 장·절 번호, 배점, 날짜·시각, α, 설계 상수(규칙 값·분할 경계·주입 강도·seed), 모델·규칙 이름의 숫자
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
# 문자열로 읽어야 "0.40" 같은 표시형이 0.4로 바뀌지 않는다
SHOWN = set(pd.read_csv(HERE / "facts.csv", encoding="utf-8-sig", usecols=["shown"], dtype=str)["shown"])

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
    "01", "02", "03", "04", "05", "06", "07", "08", "09",
    # 데이터 출처 표기 날짜(KAMP 양식)
    "2022.12",
}
# 이름·번호 속 숫자(v2, R1, 제2장, 그림 3, 2.4절, ISO 10816 등)는 대조 전에 지운다
NAME_PATTERN = re.compile(r"(?:v|R|FM|D|V|H|P|AR\(|k|B3k|lag-|C[12]d|O)\d+|\d+_[a-z]+\.py|제\d장|〔\d+점〕|그림 \d+|\d+행 창|[A-Z]\d"
                          r"|\[\d+\]|ISO \d+(?:-\d+)?(?::\d+)?|ISA-\d+\.\d+|VG \d+|\d\.\d절|\d\.\d·\d\.\d절")
REF_LINE = re.compile(r"^\s*\* \[\d+\]")   # 참고문헌 줄(서지 숫자)은 대조하지 않는다
NUM = re.compile(r"(?<![\w.])[-−+]?\d[\d,]*(?:\.\d+)?(?:e-\d+)?")


def main(path):
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        head, body = text[3:].split("---", 1)
        text = "\n" * (head.count("\n") + 1) + body   # 머리말 제외(줄 번호 유지)
    # 근거표 값은 부호를 뗀 형태와 천 단위 쉼표를 뗀 형태도 인정한다
    ok = SHOWN | {s.lstrip("+-−") for s in SHOWN} | {s.replace(",", "") for s in SHOWN} | WHITELIST
    bad = []
    for no, line in enumerate(text.splitlines(), 1):
        if REF_LINE.match(line):
            continue
        for m in NUM.finditer(NAME_PATTERN.sub(" ", line)):
            tok = m.group().replace("−", "-").lstrip("+")
            # 천 단위 쉼표가 든 정수(20,600)는 쉼표를 떼고 대조한다. 소수점이 있으면 그대로 둔다
            tok_n = tok.lstrip("-").replace(",", "") if "," in tok and "." not in tok else tok.lstrip("-")
            if tok_n not in ok and tok not in ok:
                bad.append((no, m.group(), line.strip()[:110]))
    for no, tok, line in bad:
        print(f"{no:4d}  {tok:>10}  | {line}")
    print(f"근거 없는 숫자: {len(bad)}개")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else HERE / "final_v5.md"))
