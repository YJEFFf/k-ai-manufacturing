"""redC: 두 커밋(6c61a88 → cc1aac2)의 predictions_digest.json 대조. git show만 쓴다(읽기 전용).

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python redC_digest_compare.py
"""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
OLD, NEW = "6c61a88", "cc1aac2"
PATH = "yejun/press_guard/outputs/expected/predictions_digest.json"


def show(commit, path):
    return subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"], capture_output=True, check=True).stdout.decode("utf-8")


old, new = json.loads(show(OLD, PATH)), json.loads(show(NEW, PATH))
report = {}
for name in sorted(set(old) | set(new)):
    o, n = old.get(name), new.get(name)
    if o is None or n is None:
        report[name] = dict(status="한쪽에만 있음", old=o is not None, new=n is not None)
        continue
    entry = dict(rows_old=o["rows"], rows_new=n["rows"], alarm_rows_old=o.get("alarm_rows"), alarm_rows_new=n.get("alarm_rows"),
                 file_sha_same=o["sha256"] == n["sha256"], exact_sha_same=o["exact_sha256"] == n["exact_sha256"],
                 columns_added=[c for c in n["columns"] if c not in o["columns"]],
                 columns_removed=[c for c in o["columns"] if c not in n["columns"]],
                 exact_columns_old=o.get("exact_columns"), exact_columns_new=n.get("exact_columns"))
    cols = {}
    for c in sorted(set(o["numeric_summary"]) | set(n["numeric_summary"])):
        a, b = o["numeric_summary"].get(c), n["numeric_summary"].get(c)
        if a is None or b is None:
            cols[c] = dict(status="요약 열 이동(실수↔정확 비교)" , old=a, new=b)
        elif a == b:
            cols[c] = dict(status="동일")
        else:
            cols[c] = dict(status="값 변경", old=a, new=b)
    entry["numeric"] = cols
    report[name] = entry

out = Path(__file__).with_name("redC_digest_compare.json")
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
for name, e in report.items():
    print("==", name, {k: v for k, v in e.items() if k not in ("numeric", "exact_columns_old", "exact_columns_new")})
    for c, v in e.get("numeric", {}).items():
        if v["status"] != "동일":
            print("   ", c, v)
    print("    동일 실수 열:", [c for c, v in e.get("numeric", {}).items() if v["status"] == "동일"])
