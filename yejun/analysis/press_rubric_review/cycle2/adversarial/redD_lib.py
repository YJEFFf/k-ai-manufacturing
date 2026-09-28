"""적대적 검수자 D 공용 도구. 읽기 전용이다(저장소 파일을 쓰지 않는다)."""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
YEJUN = REPO / "yejun"
GUARD = YEJUN / "press_guard"
OUT = GUARD / "outputs"
EV = YEJUN / "analysis" / "press_evidence"
SEL = YEJUN / "analysis" / "press_selection"
SUP = YEJUN / "analysis" / "press_supervised"
SPL = YEJUN / "analysis" / "press_supplement"
ADV = YEJUN / "analysis" / "press_advance"
V1 = YEJUN / "press_submission"

_cache: dict = {}


def T(path) -> pd.DataFrame:
    path = Path(path)
    if path not in _cache:
        _cache[path] = pd.read_csv(path)
    return _cache[path]


def one(df: pd.DataFrame, **cond):
    m = pd.Series(True, index=df.index)
    for k, v in cond.items():
        if isinstance(v, float):
            m &= (df[k] - v).abs() < 1e-9
        else:
            m &= df[k] == v
    sub = df[m]
    if len(sub) != 1:
        raise ValueError(f"행 {len(sub)}개: {cond}")
    return sub.iloc[0]


def decimals(text: str) -> int:
    t = text.replace(",", "").replace("%", "").replace("−", "-").strip()
    m = re.match(r"^[-+]?\d+(?:\.(\d+))?$", t)
    if not m:
        return 0
    return len(m.group(1) or "")


class Checks:
    def __init__(self):
        self.rows = []

    def num(self, cid, doc, line, claim, claimed: str, actual, source, note="", tol=None, truncate_ok=False):
        """claimed는 문서에 적힌 그대로의 문자열. actual은 같은 단위의 값."""
        c = claimed.replace(",", "").replace("%", "").replace("−", "-").replace("+", "").strip()
        status, diff = "확인 불가", ""
        try:
            cv = float(c)
            av = float(actual)
            if "e" in c.lower():
                t = abs(cv) * 0.06 if tol is None else tol
            else:
                t = 0.5 * 10 ** (-decimals(c)) * 1.000001 if tol is None else tol
            diff = av - cv
            if math.isnan(av):
                status = "확인 불가"
            elif abs(diff) <= t:
                status = "일치"
            elif truncate_ok and abs(diff) <= 2 * t:
                status = "일치(버림)"
            else:
                status = "어긋남"
        except (TypeError, ValueError):
            status = "일치" if str(actual) == claimed else "어긋남"
        self.rows.append(dict(id=cid, doc=doc, line=line, claim=claim, claimed=claimed,
                              actual=(f"{actual:.6g}" if isinstance(actual, float) else str(actual)),
                              diff=(f"{diff:.3g}" if diff != "" else ""), status=status, source=source, note=note))
        return status

    def text(self, cid, doc, line, claim, ok: bool, actual, source, note=""):
        self.rows.append(dict(id=cid, doc=doc, line=line, claim=claim, claimed="", actual=str(actual), diff="",
                              status="일치" if ok else "어긋남", source=source, note=note))

    def save(self, name):
        fields = ["id", "doc", "line", "claim", "claimed", "actual", "diff", "status", "source", "note"]
        with (HERE / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(self.rows)

    def summary(self):
        s = pd.Series([r["status"] for r in self.rows]).value_counts().to_dict()
        return s
