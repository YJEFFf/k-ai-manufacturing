"""J4 위원 현장 모의 결과 요약: 임시 폴더(j4_field)의 예측·알림·재보정 보고서를 읽어 j4_field_results.json으로 요약한다.
팀 코드를 import하지 않는다. 입력은 운영 명령(predict·simulate·monitor·recalibrate·serve)이 임시 폴더에 쓴 파일이다.
실행: python j4_field_summary.py <임시폴더/j4_field>
"""
import json
import sys
from pathlib import Path

import pandas as pd

F = Path(sys.argv[1])
lab = pd.read_csv(F / "shift_B_labels.csv").label.to_numpy()
res = {}


def summarize(name, labels=None):
    p = pd.read_csv(F / f"{name}.csv", low_memory=False)
    out = dict(rows=len(p), records=int(p.record_id.nunique()), status=p.status.value_counts().to_dict(),
               alarm_rows=int(p.alarm.sum()), incident_starts=int(p.incident_notification.sum()),
               incident_escalations=int(p.incident_escalation.sum()))
    if labels is not None and len(labels) == len(p):
        a = p.alarm.to_numpy()
        out.update(normal_alarm_rows=int(a[labels == 0].sum()), abnormal_alarm_rows=int(a[labels == 1].sum()))
    esc = p.loc[p.incident_escalation == 1, ["timestamp", "record_id", "position", "reason"]]
    out["escalations"] = esc.astype(str).to_dict(orient="records")
    return out


res["predict_shift_B_guard_B"] = summarize("pred_shift_B", lab)
res["predict_shift_B_site_model"] = summarize("pred_site", lab)
res["predict_messy_csv_guard_B"] = summarize("pred_messy")
res["predict_excel_no_ms_guard_B"] = summarize("pred_noms", lab)
for k in (105, 110, 120):
    res[f"predict_normal_current_x{k/100:.2f}_guard_B"] = summarize(f"pred_x{k}")
sim = pd.read_csv(F / "sim_alerts_B.csv")
res["simulate_shift_B"] = dict(events=sim.kind.value_counts().to_dict(), notify=int(sim.notify.sum()),
                               compute_ms_p95=round(float(sim.compute_ms.quantile(.95)), 1),
                               probability_shown_on_false_alarms=sorted(set(sim.loc[sim.record_id < 180, "anomaly_probability"].round(3))))
mon = pd.read_csv(F / "monitor_windows.csv")
res["monitor_shift_B"] = mon[[c for c in ("window", "units", "alerted_units", "limit95", "limit99", "current_ratio", "recommended_action")
                              if c in mon.columns]].astype(str).to_dict(orient="records")
rep = json.loads((F / "site_report.json").read_text(encoding="utf-8"))
res["recalibrate_site"] = dict(passed=rep.get("passed"), units=rep.get("units"),
                               checks=[dict(name=c["name"], value=c["value"], limit=c["limit"], ok=c["ok"], note=c.get("note", "")) for c in rep["checks"]],
                               budget={k: v for k, v in rep.get("budget", {}).items() if not isinstance(v, (list, dict))})
if (F / "analyze_mixed.json").exists():
    r = json.loads((F / "analyze_mixed.json").read_text(encoding="utf-8"))
    res["console_analyze_mixed_B"] = dict(stats=r["stats"], level_counts=r["level_counts"], threshold=r["threshold"],
                                          incidents=[(i.get("incident_id"), i.get("level"), i.get("reference_label")) for i in r["incidents"]])
(Path(__file__).with_name("j4_field_results.json")).write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=1, default=str)[:6000])
