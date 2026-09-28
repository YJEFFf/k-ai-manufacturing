"""redC: 새 코드(cc1aac2)로 만든 행 단위 예측 파일에 옛(6c61a88) 요약 규칙을 적용해 옛 동결 요약과 대조한다.

옛 exact_sha256 = 옛 정확 비교 13열의 행별 해시다. 같으면 경보·알림·단계·근거·조치가 행 단위로 같다.

    python redC_old_digest_on_new_predictions.py <새 예측 파일이 있는 outputs 폴더>
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[5]
OLD = "6c61a88"
OLD_EXACT = ("subset", "label", "row_id", "record_id", "position", "status", "alarm", "notification", "alert_level", "escalation", "reason", "action", "alert_unit")


def show(commit, path):
    return subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"], capture_output=True, check=True).stdout.decode("utf-8")


def old_digest(path, old_columns):
    x = pd.read_csv(path)
    added = [c for c in x.columns if c not in old_columns]
    x = x[[c for c in x.columns if c in old_columns]]
    exact = [c for c in OLD_EXACT if c in x.columns]
    numeric = [c for c in x.columns if c not in exact and pd.api.types.is_numeric_dtype(x[c])]
    summary = {}
    for c in numeric:
        v = x[c].to_numpy(float); f = np.isfinite(v)
        summary[c] = [int(f.sum()), float(v[f].sum()), float((v[f] ** 2).sum()), float(v[f].min()) if f.any() else None, float(v[f].max()) if f.any() else None]
    return dict(rows=int(len(x)), columns=list(x.columns), added=added,
                exact_sha256=hashlib.sha256(x[exact].astype(str).to_csv(index=False).encode()).hexdigest(), numeric_summary=summary)


def close(a, b):
    if a[0] != b[0]:
        return False
    return all((u is None and w is None) or (u is not None and w is not None and np.isclose(u, w, rtol=1e-12, atol=0)) for u, w in zip(a[1:], b[1:]))


out = Path(sys.argv[1])
expected = json.loads(show(OLD, "yejun/press_guard/outputs/expected/predictions_digest.json"))
report = {}
for name, e in expected.items():
    now = old_digest(out / name, e["columns"])
    diffs = {c: dict(old=e["numeric_summary"][c], new=now["numeric_summary"].get(c)) for c in e["numeric_summary"]
             if c not in now["numeric_summary"] or not close(now["numeric_summary"][c], e["numeric_summary"][c])}
    exactly = {c: now["numeric_summary"][c] == e["numeric_summary"][c] for c in e["numeric_summary"] if c in now["numeric_summary"]}
    report[name] = dict(rows_same=now["rows"] == e["rows"], old_columns_same_order=now["columns"] == e["columns"], added_columns=now["added"],
                        old_exact_sha256_same=now["exact_sha256"] == e["exact_sha256"], numeric_columns=len(e["numeric_summary"]),
                        numeric_bitwise_same=int(sum(exactly.values())), numeric_outside_rtol_1e12=diffs)
    print(name, json.dumps({k: v for k, v in report[name].items()}, ensure_ascii=False))
Path(__file__).with_name("redC_old_digest_on_new_predictions.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
