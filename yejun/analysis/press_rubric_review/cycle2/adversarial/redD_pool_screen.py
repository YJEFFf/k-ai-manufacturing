"""적대적 검수자 D — 문서 수치 토큰을 커밋된 표·JSON 값 풀과 기계적으로 대조한다(1차 선별).

- 읽기 전용. 기준 커밋의 파일을 git show로 읽는다.
- 풀: 대상 패키지와 의존 패키지의 CSV 숫자 칸, JSON 숫자 잎.
- 토큰: 소수·백분율·지수·천 단위 쉼표 수, 분수 a/b(같은 표 행에 a와 b가 함께 있는지).
- 작은 정수(유효숫자 2자리 이하)는 우연히 맞기 쉬워 '정보 없음'으로 분류한다.
- 풀에서 찾지 못한 토큰은 어긋남이 아니라 '수동 확인 대상'이다(유도값·가이드북 값·개수 등).
산출: redD_pool_screen.csv, redD_pool_unmatched.csv, redD_pool_screen.log
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
COMMIT = "cc1aac2"

DOCS = [
    "yejun/press_guard/README.md",
    "yejun/press_guard/OPERATIONS.md",
    "yejun/press_guard/web/index.html",
    "yejun/press_submission/README.md",
    "yejun/press_submission/outputs/diagnosis.md",
    "yejun/analysis/press_evidence/README.md",
    "yejun/analysis/press_selection/README.md",
    "yejun/analysis/press_supervised/README.md",
    "yejun/analysis/press_supplement/README.md",
    "yejun/analysis/press_advance/README.md",
]

POOL_DIRS = [
    "yejun/press_guard/outputs",
    "yejun/press_guard/artifacts",
    "yejun/press_submission/outputs",
    "yejun/analysis/press_evidence",
    "yejun/analysis/press_selection",
    "yejun/analysis/press_supervised",
    "yejun/analysis/press_supplement",
    "yejun/analysis/press_advance",
    "yejun/analysis/press_dayshift",
    "yejun/analysis/press_early",
    "yejun/analysis/press_external",
    "yejun/analysis/press_improvement",
]


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), "-c", "core.quotepath=off", *args], capture_output=True, check=True).stdout


def tracked(prefix: str) -> list[str]:
    return [p for p in git("ls-tree", "-r", "--name-only", COMMIT, prefix).decode("utf-8").splitlines() if p]


def show(path: str) -> str:
    return git("show", f"{COMMIT}:{path}").decode("utf-8")


def to_float(s: str):
    s = s.strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


class Pool:
    def __init__(self):
        self.values = []        # (value, file, line, column)
        self.rows = []          # (file, line, frozenset(int values))
        self.by_round = defaultdict(list)

    def add(self, v, f, line, col):
        self.values.append((v, f, line, col))

    def finish(self):
        import bisect  # noqa: F401
        self.values.sort(key=lambda t: t[0])
        self.keys = [t[0] for t in self.values]

    def near(self, lo, hi, limit=3):
        import bisect
        i = bisect.bisect_left(self.keys, lo)
        out = []
        while i < len(self.keys) and self.keys[i] <= hi:
            out.append(self.values[i])
            if len(out) >= limit:
                break
            i += 1
        return out


def walk_json(obj, path, f, pool: Pool):
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk_json(v, f"{path}.{k}" if path else str(k), f, pool)
    elif isinstance(obj, list):
        if len(obj) > 400:
            return
        for i, v in enumerate(obj):
            walk_json(v, f"{path}[{i}]", f, pool)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, (int, float)):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return
        pool.add(float(obj), f, 0, path)


def build_pool() -> Pool:
    pool = Pool()
    n_csv = n_json = 0
    for d in POOL_DIRS:
        for p in tracked(d):
            if "/expected/" in p or "/console/" in p:
                continue
            base = p.rsplit("/", 1)[-1]
            if base.startswith("predictions") or base.startswith("test_predictions"):
                continue
            if p.endswith(".csv"):
                text = show(p)
                if len(text) > 6_000_000:
                    continue
                n_csv += 1
                reader = csv.reader(io.StringIO(text))
                try:
                    header = next(reader)
                except StopIteration:
                    continue
                pool.add(float(sum(1 for _ in csv.reader(io.StringIO(text))) - 1), p, 0, "<행 수>")
                for li, row in enumerate(reader, 2):
                    ints = set()
                    for ci, cell in enumerate(row):
                        v = to_float(cell)
                        if v is None:
                            continue
                        col = header[ci] if ci < len(header) else str(ci)
                        pool.add(v, p, li, col)
                        if abs(v - round(v)) < 1e-9 and abs(v) < 1e7:
                            ints.add(int(round(v)))
                    if ints:
                        pool.rows.append((p, li, frozenset(ints)))
            elif p.endswith(".json"):
                try:
                    obj = json.loads(show(p))
                except Exception:
                    continue
                n_json += 1
                walk_json(obj, "", p, pool)
    pool.finish()
    pool.n_csv, pool.n_json = n_csv, n_json
    return pool


CLEAN = [
    (re.compile(r"```.*?```", re.S), " "),
    (re.compile(r"\]\([^)]*\)"), "] "),                     # 링크 주소
    (re.compile(r"`[^`]*`"), " "),                           # 코드 표기
    (re.compile(r"<[^>]+>"), " "),                           # HTML 태그
    (re.compile(r"\b20\d\d-\d\d-\d\d\b"), " "),              # 날짜
    (re.compile(r"\b\d\d-\d\d\([월화수목금토일]\)"), " "),
    (re.compile(r"\b\d{1,2}:\d\d(?::\d\d(?:\.\d+)?)?\b"), " "),  # 시각
    (re.compile(r"\b[0-9a-f]{7,40}\b"), " "),                # 커밋 해시
]

FRACTION = re.compile(r"(?<![\w.,/])(\d[\d,]*)\s?/\s?(\d[\d,]*)(?![\w/]|\.\d)")
NUMBER = re.compile(r"(?<![\w.,/])([-+−]?\d[\d,]*(?:\.\d+)?(?:e[-+−]?\d+)?)(%p|%)?(?![\w/]|\.\d)", re.IGNORECASE)


def classify(tok: str):
    t = tok.replace(",", "").replace("−", "-")
    try:
        v = float(t)
    except ValueError:
        return None
    mant = t.lower().split("e")[0].lstrip("+-")
    dec = len(mant.split(".")[1]) if "." in mant else 0
    digits = mant.replace(".", "").lstrip("0")
    sig = len(digits) if digits else 1
    return v, dec, sig, ("e" in t.lower())


def match_number(pool: Pool, tok: str, pct: bool):
    c = classify(tok)
    if c is None:
        return None, []
    v, dec, sig, sci = c
    cands = []
    targets = [v]
    if pct:
        targets.append(v / 100.0)
    else:
        targets.append(v / 100.0)      # 본문이 %를 생략하고 쓴 비율
        targets.append(v * 100.0)
    for k, t in enumerate(targets):
        if sci:
            tol = abs(t) * 0.06
        else:
            d = dec + (2 if (k == 1) else 0) - (2 if (k == 2) else 0)
            tol = 0.5 * 10 ** (-d) * 1.0000001
        hit = pool.near(t - tol, t + tol)
        # 절댓값(부호를 글로 적은 경우)
        if not hit and t > 0:
            hit = pool.near(-t - tol, -t + tol)
        if hit:
            cands = hit
            break
    return (v, dec, sig, sci), cands


def main() -> int:
    pool = build_pool()
    out_rows = []
    summary = {}
    for doc in DOCS:
        text = show(doc)
        n_tok = n_info = n_hit = n_info_hit = n_frac = n_frac_hit = 0
        in_code = False
        for li, raw in enumerate(text.splitlines(), 1):
            line = raw
            if doc.endswith(".md") and line.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            for rx, rep in CLEAN:
                line = rx.sub(rep, line)
            used = []
            for m in FRACTION.finditer(line):
                a = int(m.group(1).replace(",", "")); b = int(m.group(2).replace(",", ""))
                used.append(m.span())
                if b == 0 or a > b * 50:
                    continue
                n_frac += 1
                hits = [(f, l) for f, l, s in pool.rows if a in s and b in s][:3]
                ok = bool(hits)
                n_frac_hit += ok
                out_rows.append(dict(doc=doc, line=li, token=f"{a}/{b}", kind="fraction", informative=1,
                                     matched=int(ok), sources="; ".join(f"{f}:{l}" for f, l in hits),
                                     context=raw.strip()[:240]))
            for m in NUMBER.finditer(line):
                if any(s <= m.start() < e for s, e in used):
                    continue
                tok, pct = m.group(1), bool(m.group(2))
                info, cands = match_number(pool, tok, pct)
                if info is None:
                    continue
                v, dec, sig, sci = info
                informative = int(sig >= 3 or dec >= 2 or sci)
                n_tok += 1
                n_info += informative
                ok = bool(cands)
                n_hit += ok
                n_info_hit += (ok and informative)
                out_rows.append(dict(doc=doc, line=li, token=tok + (m.group(2) or ""), kind="number", informative=informative,
                                     matched=int(ok), sources="; ".join(f"{f}:{l}:{c}={val:.6g}" for val, f, l, c in cands[:2]),
                                     context=raw.strip()[:240]))
        summary[doc] = (n_tok, n_info, n_info_hit, n_frac, n_frac_hit)

    fields = ["doc", "line", "token", "kind", "informative", "matched", "sources", "context"]
    with (HERE / "redD_pool_screen.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(out_rows)
    un = [r for r in out_rows if r["informative"] and not r["matched"]]
    with (HERE / "redD_pool_unmatched.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(un)

    log = [f"기준 커밋 {COMMIT}", f"풀: CSV {pool.n_csv}개, JSON {pool.n_json}개, 숫자 값 {len(pool.values):,}개, 정수 행 {len(pool.rows):,}개",
           "문서: 수 토큰 / 정보 있는 토큰 / 그중 풀 일치 / 분수 / 분수 일치(같은 표 행)"]
    tot = [0] * 5
    for doc, s in summary.items():
        log.append(f"  {doc}: {s[0]} / {s[1]} / {s[2]} / {s[3]} / {s[4]}")
        tot = [a + b for a, b in zip(tot, s)]
    log.append(f"  합계: {tot[0]} / {tot[1]} / {tot[2]} / {tot[3]} / {tot[4]}")
    log.append(f"수동 확인 대상(정보 있는 토큰·분수 중 풀에 없음): {len(un)}개 → redD_pool_unmatched.csv")
    (HERE / "redD_pool_screen.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
