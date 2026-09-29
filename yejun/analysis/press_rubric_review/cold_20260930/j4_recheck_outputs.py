"""J4 위원 독립 점검 3: git 없는 임시 사본에서 한 명령 재현을 돌린 뒤, 그 결과 파일만으로 주 지표를 다시 센다.

팀 코드를 import하지 않는다.
- test_predictions_{A,B}.csv: label·alarm으로 F1, 정상 경보 기록 수, 이상 탐지 기록 수, 첫 경보 최대 지연, 사건 알림 수
- 임시 사본 outputs/*.csv와 저장소 커밋 outputs/*.csv의 SHA-256 비교(재현이 커밋 결과를 바이트 단위로 다시 만드는가)
실행: python j4_recheck_outputs.py <임시사본/yejun> <저장소/yejun>
결과: j4_recheck_outputs.json
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

tmp, repo = Path(sys.argv[1]), Path(sys.argv[2])
res = {}
for split in ("A", "B"):
    p = pd.read_csv(tmp / "press_guard" / "outputs" / f"test_predictions_{split}.csv", low_memory=False)
    lab, al = p.label.astype(int).to_numpy(), p.alarm.astype(int).to_numpy()
    tp, fp, fn = int(((lab == 1) & (al == 1)).sum()), int(((lab == 0) & (al == 1)).sum()), int(((lab == 1) & (al == 0)).sum())
    nrm, ab = p[p.label == 0], p[p.label == 1]
    first = ab[ab.alarm == 1].groupby("record_id").position.min()
    res[split] = dict(rows=len(p), tp=tp, fp=fp, fn=fn, f1=round(2 * tp / (2 * tp + fp + fn), 6),
                      normal_records_alerted=f"{int(nrm.groupby('record_id').alarm.max().sum())}/{nrm.record_id.nunique()}",
                      abnormal_records_detected=f"{len(first)}/{ab.record_id.nunique()}",
                      first_alarm_delay_max_s=round(float(first.max()) * 0.1, 1),
                      first_alarm_delay_median_s=round(float(first.median()) * 0.1, 2),
                      normal_incident_starts=int(nrm.incident_notification.sum()), normal_incident_escalations=int(nrm.incident_escalation.sum()),
                      abnormal_incident_starts=int(ab.incident_notification.sum()), abnormal_incident_escalations=int(ab.incident_escalation.sum()),
                      abnormal_row_alarms=int(ab.alarm.sum()),
                      prob_cap_rows_abnormal=int((ab.anomaly_probability.round(4) == round(float(ab.anomaly_probability.max()), 4)).sum()),
                      normal_alarm_prob_max=float(nrm.loc[nrm.alarm == 1, "anomaly_probability"].max()) if (nrm.alarm == 1).any() else None,
                      columns=len(p.columns))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


same, diff, missing = [], [], []
for f in sorted((repo / "press_guard" / "outputs").glob("*.csv")):
    if f.name.startswith(("predictions", "test_predictions")):
        continue   # Git 제외 파일
    t = tmp / "press_guard" / "outputs" / f.name
    if not t.exists():
        missing.append(f.name)
    elif sha(t) == sha(f):
        same.append(f.name)
    else:
        diff.append(f.name)
res["outputs_csv_vs_commit"] = dict(same=len(same), differ=diff, missing=missing)
ev_same, ev_diff = [], []
for f in sorted((repo / "analysis" / "press_evidence").glob("*.csv")):
    t = tmp / "analysis" / "press_evidence" / f.name
    (ev_same if t.exists() and sha(t) == sha(f) else ev_diff).append(f.name)
res["press_evidence_csv_vs_commit"] = dict(same=len(ev_same), differ=ev_diff)
summ = json.loads((tmp / "press_guard" / "outputs" / "reproduce_summary.json").read_text(encoding="utf-8"))
res["reproduce_summary"] = dict(mode=summ["mode"], python=summ["python"], total_seconds=summ["total_seconds"], passed=summ["passed"],
                                failed=summ["failed"], planned=summ["planned"],
                                steps=[(s["step"], s["returncode"], s["seconds"]) for s in summ["steps"]])
Path(__file__).with_name("j4_recheck_outputs.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1))
