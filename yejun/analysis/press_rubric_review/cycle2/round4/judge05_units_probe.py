"""사건 격상 수정 뒤 2단계 주추정의 건/사건 단위 일치 여부를 원본 재적합으로 확인."""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]
sys.path.insert(0, str(Y / "press_guard"))
from model import D, GuardModel, load_bundle

start = time.monotonic()
normal, _ = D.load()[:2]
seg = D.segments(normal)
levels = pd.read_csv(Y / "press_guard/outputs/alert_levels_v2.csv")
rows = []
for end in (180, 240):
    train, cal, test = (normal[seg < end], normal[(seg >= end) & (seg < end + 120)], normal[(seg >= end + 120) & (seg < end + 180)])
    model = GuardModel.fit(train, cal)
    p = model.predict(test, .05)
    window = f"{end + 120}~{end + 179}"
    ref = levels[levels.normal_window.eq(window) & levels.alpha.eq(.05)].set_index("level")
    case1 = int(p.groupby("record_id").alarm.max().sum())
    case2 = int(p.groupby("record_id").escalation.max().sum())
    incident1, incident2 = int(p.incident_notification.sum()), int(p.incident_escalation.sum())
    assert case1 == ref.loc[1, "normal_alerted_segments"] and case2 == ref.loc[2, "normal_alerted_segments"]
    assert case1 == incident1 and case2 == incident2
    rows.append(dict(window=window, alpha=.05, alerted_records=case1, case_escalations=case2,
                     incident_starts=incident1, incident_escalations=incident2))

mb = load_bundle(Y / "press_guard/artifacts/guard_B.json")
test = D.split_normal(normal, seg, "B")["test"]
p = mb.predict(test, .01)
max_difference = 0.0
for record, group in p.groupby("record_id"):
    original = test.iloc[group.index][D.SENSORS[2]].to_numpy(float)
    expected = np.array([np.std(original[:i + 1]) for i in range(len(original))])
    max_difference = max(max_difference, float(np.max(np.abs(group.record_current_rms.to_numpy() - expected))))
assert max_difference < 1e-9
out = dict(two_nonoverlap_folds=rows, current_rms_causal_max_error=max_difference, normal_rows=len(test),
           elapsed_seconds=time.monotonic() - start, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           note="현재 주추정 120기록에서는 건·사건 2단계 건수가 같다. 다른 연속 입력에서도 같다는 보장은 아니다.")
(HERE / "judge05_units_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
