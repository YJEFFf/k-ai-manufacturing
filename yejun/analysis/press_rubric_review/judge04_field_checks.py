"""평가관 04(현장 활용) 검수용 점검. 기존 코드·모델·산출물을 수정하지 않고 읽기만 한다.

실행(yejun/ 에서):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python analysis/press_rubric_review/judge04_field_checks.py
결과: analysis/press_rubric_review/judge04_field_checks.json (이 파일만 쓴다)
웹 API 점검은 127.0.0.1 임시 포트에 서버를 띄우고 끝나면 바로 종료한다.
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[1]
GUARD = YEJUN / "press_guard"
SUPP = YEJUN / "analysis" / "press_supplement"
sys.path.insert(0, str(GUARD))
sys.path.insert(0, str(SUPP))
from model import GuardModel, StreamDetector, cases, D  # noqa: E402
from common import inject, split_rows, standard_noise  # noqa: E402

OUT = HERE / "judge04_field_checks.json"
res: dict = {}
normal, abnormal, _ = D.load()
models = {s: GuardModel.load(GUARD / "artifacts" / f"guard_{s}.json") for s in D.SPLITS}


def mag_sources(pred):
    """경보 행 중 크기 성분이 발화한 행의 최대 |z| 센서."""
    a = pred[(pred.alarm == 1) & pred.reason.astype(str).str.contains("magnitude")]
    return a.magnitude_sensor.value_counts().to_dict()


def case_consistency(pred):
    """구간(case)별: 조치 문구에 '진동'이 있는데 크기 성분 발화 행의 센서가 모두 전류인 경우를 센다."""
    q = cases(pred)
    rows = []
    for c in q.itertuples():
        g = pred[(pred.record_id == c.record_id) & (pred.alarm == 1)]
        m = g[g.reason.astype(str).str.contains("magnitude")]
        sens = sorted(set(m.magnitude_sensor))
        rows.append(dict(record_id=c.record_id, evidence=c.evidence, action=c.action, magnitude_sensors="+".join(sens),
                         vib_word_but_current_only=bool("진동" in c.action and sens == ["AI2_Current"])))
    return pd.DataFrame(rows)


# ---------- 1. 조치 문구 정합성 ----------
one = pd.DataFrame({D.TIME: ["2026-09-26 12:00:00.000"], "AI0_Vibration": [models["A"].mean[0]],
                    "AI1_Vibration": [models["A"].mean[1]], "AI2_Current": [models["A"].mean[2] + 30 * models["A"].scale[2]]})
p1 = models["A"].predict(one, .01)
res["one_row_current_only"] = p1[["reason", "action", "magnitude_sensor", "alarm"]].to_dict("records")

observed = {}
for sid, m in models.items():
    rows = split_rows(normal, sid)
    for name, frame in (("normal_test", normal.iloc[rows["test"]]), ("abnormal", abnormal)):
        pred = m.predict(D.inputs_only(frame).reset_index(drop=True), .01)
        cc = case_consistency(pred)
        observed[f"{sid}_{name}"] = dict(magnitude_alarm_rows_by_sensor=mag_sources(pred), cases=len(cc),
                                         action_counts=cc.action.value_counts().to_dict() if len(cc) else {},
                                         vib_word_but_current_only=int(cc.vib_word_but_current_only.sum()) if len(cc) else 0)
res["observed_alpha01"] = observed

scen = [("cur_offset", .4, 10), ("cur_offset", .8, 10), ("cur_offset", .8, 0), ("cur_gain", 1.3, 10), ("cur_gain", 1.5, 10),
        ("cur_gain", 1.5, 0), ("cur_noise", .2, 10), ("vib_noise", 4, 10)]
inj = []
for sid, m in models.items():
    rows = split_rows(normal, sid)
    test = D.inputs_only(normal.iloc[rows["test"]]).reset_index(drop=True)
    seg = D.segments(test)
    pos, length = D.segment_positions(seg)
    z = standard_noise(len(normal), 0)
    for fam, lv, t0 in scen:
        eligible = np.unique(seg[length >= (30 if t0 == 10 else 20)])
        mask = np.isin(seg, eligible) & (pos >= t0)
        frame = inject(test, rows["test"], m, fam, lv, mask, np.ones(len(pos)), z)
        pred = m.predict(frame, .01)
        pred_e = pred[np.isin(pred.record_id, eligible)]
        cc = case_consistency(pred_e)
        inj.append(dict(split=sid, family=fam, level=lv, t0=t0, eligible_records=int(len(eligible)), cases=int(len(cc)),
                        magnitude_alarm_rows_by_sensor=mag_sources(pred_e),
                        action_counts=cc.action.value_counts().to_dict() if len(cc) else {},
                        vib_word_but_current_only_cases=int(cc.vib_word_but_current_only.sum()) if len(cc) else 0,
                        magnitude_only_evidence_cases=int((cc.evidence == "magnitude").sum()) if len(cc) else 0))
res["injection_alpha01_rep0"] = inj

# ---------- 2. 대기열 순서·우선순위 정보 ----------
queue = {}
for sid, m in models.items():
    rows = split_rows(normal, sid)
    mixed = pd.concat([normal.iloc[rows["test"]], abnormal], ignore_index=True)
    for alpha in (.01, .03, .05):
        pred = m.predict(D.inputs_only(mixed), alpha)
        truth = mixed[D.LABEL].astype(int).to_numpy()
        pred["label"] = truth
        q = cases(pred)
        q["label"] = q.record_id.map(pred.groupby("record_id").label.first())
        q["n_evidence"] = q.evidence.str.count(r"\+") + 1
        q["alarm_frac"] = q.alarm_rows / q.observed_rows
        by_peak = q.sort_values("peak_score", ascending=False).reset_index(drop=True)
        queue[f"{sid}_a{int(alpha*100)}"] = dict(
            n_cal=int(len(m.cal)), p_floor=1 / (len(m.cal) + 1), cases=int(len(q)), normal_cases=int((q.label == 0).sum()),
            queue_in_record_order=bool(q.record_id.is_monotonic_increasing),
            distinct_min_p=sorted(set(np.round(q.min_p, 6))), min_p_at_floor_share=float(np.isclose(q.min_p, 1 / (len(m.cal) + 1)).mean()),
            normal_case_peak_scores=[round(v, 3) for v in q[q.label == 0].peak_score],
            abnormal_case_peak_min=round(float(q[q.label == 1].peak_score.min()), 3),
            normal_case_ranks_by_peak_posthoc=[int(i) + 1 for i in by_peak.index[by_peak.label == 0]],
            normal_case_evidence=q[q.label == 0].evidence.tolist(),
            normal_case_alarm_frac=[round(v, 3) for v in q[q.label == 0].alarm_frac])
res["queue_priority"] = queue

# ---------- 3. 업무량 재계산 ----------
work = pd.read_csv(GUARD / "outputs" / "workload_v2.csv")
wl = []
for sid, m in models.items():
    rows = split_rows(normal, sid)
    test = normal.iloc[rows["test"]]
    t = pd.to_datetime(test[D.TIME])
    seg = D.segments(test)
    n_seg = int(len(np.unique(seg)))
    rec_h, el_h = len(test) * D.DT / 3600, (t.max() - t.min()).total_seconds() / 3600
    lengths = pd.Series(seg).value_counts()
    for alpha in (.01, .03, .05):
        pred = m.predict(D.inputs_only(test).reset_index(drop=True), alpha)
        k = int(pred.notification.sum())
        up = float(beta.ppf(.95, k + 1, n_seg - k))  # 단측 95% 상한(독립 가정 참고치)
        w = work[(work.split_id == sid) & (work.model == "guard_v2") & np.isclose(work.alpha, alpha)].iloc[0]
        wl.append(dict(split=sid, alpha=alpha, normal_segments=n_seg, first_alerts=k, stored_first_alerts=int(w.first_alert_segments),
                       recorded_h=rec_h, elapsed_h=el_h, segments_per_elapsed_h=n_seg / el_h,
                       seg_len_median_rows=float(lengths.median()), seg_len_max_rows=int(lengths.max()),
                       alerts_per_8h_elapsed=k / el_h * 8, alerts_per_8h_recorded_stored=float(w.scenario_alerts_per_day_8h_recorded_rate),
                       recomputed_match=bool(np.isclose(k / rec_h * 8, w.scenario_alerts_per_day_8h_recorded_rate)),
                       upper95_per_segment=up, upper95_alerts_per_8h_elapsed=up * n_seg / el_h * 8,
                       nominal_alpha_alerts_per_8h_elapsed=alpha * n_seg / el_h * 8))
res["workload"] = wl

# ---------- 4. 첫 경보 지연 대조 ----------
first = pd.read_csv(GUARD / "outputs" / "records_first_alarm_v2.csv")
delay = {}
for sid, m in models.items():
    q = cases(m.predict(D.inputs_only(abnormal), .01))
    f = first[first.split_id == sid].set_index("record_id")
    delay[sid] = dict(match=bool((q.set_index("record_id").first_alarm_position == f.v2_first_alarm_position).all()),
                      median_s=float(q.detection_delay_s.median()), max_s=float(q.detection_delay_s.max()))
res["delay_vs_records_first_alarm"] = delay

# ---------- 5. 끊김 없는 연속 스트림에서의 대기열 단위 ----------
def restamp(frame, start="2026-09-26 08:00:00"):
    f = D.inputs_only(frame).reset_index(drop=True).copy()
    f[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(f)) * D.DT, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return f


m = models["B"]
rows = split_rows(normal, "B")
normal_b = normal.iloc[rows["test"]]
cont = restamp(pd.concat([normal_b, abnormal], ignore_index=True))
stream = StreamDetector(m, .01)
pc = pd.concat([stream.push(cont.iloc[i:i + 128]) for i in range(0, len(cont), 128)], ignore_index=True)
n_norm = len(normal_b)
qc = cases(pc)
seg_pred = m.predict(D.inputs_only(pd.concat([normal_b, abnormal], ignore_index=True)), .01)
res["continuous_stream_B"] = dict(
    rows=len(cont), normal_rows=n_norm, records=int(pc.record_id.nunique()), notifications=int(pc.notification.sum()),
    first_notification_row=int(pc.index[pc.notification == 1][0]) if pc.notification.any() else None,
    first_notification_in_normal_part=bool(pc.notification.any() and pc.index[pc.notification == 1][0] < n_norm),
    alarm_rows_normal_part=int(pc.alarm.iloc[:n_norm].sum()), alarm_rows_abnormal_part=int(pc.alarm.iloc[n_norm:].sum()),
    cases=int(len(qc)), case_first_alarm_position=int(qc.first_alarm_position.iloc[0]) if len(qc) else None,
    case_evidence=qc.evidence.iloc[0] if len(qc) else None, case_action=qc.action.iloc[0] if len(qc) else None,
    segmented_same_rows_cases=int(len(cases(seg_pred))), segmented_notifications=int(seg_pred.notification.sum()))

# ---------- 6. 1행 순차 처리 속도(소규모) ----------
test_a = D.inputs_only(normal.iloc[split_rows(normal, "A")["test"]]).reset_index(drop=True).iloc[:400]
sd = StreamDetector(models["A"], .01)
lat = []
for i in range(len(test_a)):
    t0 = time.perf_counter(); sd.push(test_a.iloc[i:i + 1]); lat.append((time.perf_counter() - t0) * 1000)
res["latency_1row_ms"] = dict(rows=len(lat), p50=float(np.percentile(lat, 50)), p95=float(np.percentile(lat, 95)), max=float(np.max(lat)))

# ---------- 7. 웹 API(임시 포트, 종료 확인) ----------
sys.argv = ["serve.py"]
import serve  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

console = serve.Console()
server = ThreadingHTTPServer(("127.0.0.1", 0), serve.handler(console))
port = server.server_address[1]
th = threading.Thread(target=server.serve_forever, daemon=True); th.start()


def call(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


web = {}
try:
    ov = call("/api/overview")
    web["overview"] = dict(audit_all_ok=ov["audit"].get("all_ok"), audit_checks=len(ov["audit"].get("checks", [])),
                           benchmark_runs=len(ov["benchmark"].get("runs", [])), metrics_rows=len(ov["metrics"]))
    for sid in ("A", "B"):
        r = call("/api/analyze", dict(split=sid, alpha=.01, dataset="mixed"))
        cs = pd.DataFrame(r["cases"])
        web[f"mixed_{sid}_a1"] = dict(cases=len(cs), notifications=r["stats"]["notifications"], threshold=r["threshold"],
                                      normal_cases=int((cs.reference_label == 0).sum()), case_keys=sorted(cs.columns),
                                      has_magnitude_sensor_in_case=("magnitude_sensor" in cs.columns),
                                      actions=cs.action.value_counts().to_dict())
    up = call("/api/analyze", dict(split="A", alpha=.01, dataset="upload", csv=one.to_csv(index=False)))
    web["upload_one_row_current"] = dict(cases=up["cases"], point_magnitude_sensor=up["points"][0].get("magnitude_sensor"))
    small = cont.iloc[:600]
    upc = call("/api/analyze", dict(split="B", alpha=.01, dataset="upload", csv=small.to_csv(index=False)))
    web["upload_continuous_600"] = dict(segments=upc["stats"]["segments"], cases=len(upc["cases"]), alarm_rows=upc["stats"]["alarm_rows"])
finally:
    server.shutdown(); server.server_close(); th.join(timeout=5)
web["server_stopped"] = not th.is_alive()
res["web_api"] = web

OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
