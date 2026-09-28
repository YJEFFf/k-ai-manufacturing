"""redC: 두 커밋(6c61a88 → cc1aac2)의 CSV를 표마다 분류한다. git show/ls-tree만 쓴다(읽기 전용).

분류: 값 동일 / 새 파일 / 삭제 / 행·열 추가(옛 값 보존) / 기존 값 변경.
- 옛 열이 모두 남아 있고, 옛 행(옛 열로 본 값)이 새 표에 모두 있으면 '행·열 추가'.
- 아니면 '기존 값 변경'이며 바뀐 열과 예를 적는다. 수치 열은 1e-9 안이면 같다고 본다.

    python redC_csv_compare.py
"""
import io
import json
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[5]
OLD, NEW = "6c61a88", "cc1aac2"
ROOTS = ["yejun/press_guard/outputs", "yejun/analysis/press_evidence", "yejun/analysis/press_supervised", "yejun/analysis/press_selection",
         "yejun/analysis/press_supplement", "yejun/analysis/press_advance", "yejun/analysis/press_early", "yejun/analysis/press_dayshift",
         "yejun/analysis/press_external", "yejun/analysis/press_improvement", "yejun/press_submission"]


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), "-c", "core.quotepath=false", *args], capture_output=True, check=True).stdout


def tree(commit):
    out = {}
    for line in git("ls-tree", "-r", commit, "--", *ROOTS).decode("utf-8").splitlines():
        meta, path = line.split("\t", 1)
        if path.endswith(".csv"):
            out[path] = meta.split()[2]
    return out


def load(commit, path):
    return pd.read_csv(io.BytesIO(git("show", f"{commit}:{path}")), dtype=str, keep_default_na=False)


def same_cell(a, b):
    if a == b:
        return True
    try:
        x, y = float(a), float(b)
    except ValueError:
        return False
    if np.isnan(x) and np.isnan(y):
        return True
    return bool(abs(x - y) <= 1e-9)


def norm(v):
    try:
        x = float(v)
    except ValueError:
        return v
    if np.isnan(x):
        return "nan"
    return repr(round(x, 9))


def classify(path):
    o, n = load(OLD, path), load(NEW, path)
    info = dict(rows_old=len(o), rows_new=len(n), cols_old=len(o.columns), cols_new=len(n.columns),
                columns_added=[c for c in n.columns if c not in o.columns], columns_removed=[c for c in o.columns if c not in n.columns])
    common = [c for c in o.columns if c in n.columns]
    if info["columns_removed"]:
        info["class"] = "기존 값 변경(열 삭제)"
    ok, nk = [tuple(norm(v) for v in r) for r in o[common].itertuples(index=False)], [tuple(norm(v) for v in r) for r in n[common].itertuples(index=False)]
    missing = Counter(ok) - Counter(nk)
    if not missing and not info["columns_removed"]:
        info["class"] = "행·열 추가(옛 값 보존)" if (info["columns_added"] or len(n) != len(o)) else "값 동일(서식만 다름)"
        return info
    info.setdefault("class", "기존 값 변경")
    info["old_rows_not_found"] = int(sum(missing.values()))
    if len(o) == len(n):
        changed = {}
        for c in common:
            idx = [i for i, (a, b) in enumerate(zip(o[c], n[c])) if not same_cell(a, b)]
            if idx:
                changed[c] = dict(cells=len(idx), examples=[dict(row=i, old=o[c].iloc[i][:160], new=n[c].iloc[i][:160]) for i in idx[:3]])
        info["changed_columns_same_position"] = changed
    return info


old, new = tree(OLD), tree(NEW)
report = {}
for path in sorted(set(old) | set(new)):
    if path not in old:
        report[path] = {"class": "새 파일"}
    elif path not in new:
        report[path] = {"class": "삭제"}
    elif old[path] == new[path]:
        report[path] = {"class": "값 동일"}
    else:
        report[path] = classify(path)
Path(__file__).with_name("redC_csv_compare.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
count = Counter(v["class"] for v in report.values())
print(dict(count), "합계", len(report))
for path, v in report.items():
    if v["class"] != "값 동일":
        print(v["class"], "|", path, "|", {k: x for k, x in v.items() if k not in ("class", "changed_columns_same_position")})
        for c, d in v.get("changed_columns_same_position", {}).items():
            print("      ", c, d["cells"], "칸", d["examples"][:2])
