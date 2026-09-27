"""평가관 04(현장 활용방안) cycle2 round1 검증. 저장소 코드·산출물은 읽기만 한다.

실행(yejun/ 에서):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      analysis/press_rubric_review/cycle2/round1/judge04_field_check.py | tee analysis/press_rubric_review/cycle2/round1/judge04_field_check.log
쓰는 파일: 이 폴더의 judge04_field_check.json 하나. 재학습·재보정·예측 산출물은 시스템 임시 폴더에만 쓴다.
웹 API는 127.0.0.1 임시 포트(0번 → OS 배정)에 띄우고 끝나면 종료한다.

[사후] 표시가 붙은 항목은 이상 라벨을 본 뒤의 관찰이다. 성능 근거가 아니라 수정 항목의 실현 가능성 확인용이다.
[가정] 표시가 붙은 항목은 현장 자료가 없어 평가관이 둔 가정값이다.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
REPO = YEJUN.parent
GUARD = YEJUN / "press_guard"
SUPP = YEJUN / "analysis" / "press_supplement"
sys.path.insert(0, str(GUARD))
sys.path.insert(0, str(SUPP))
from model import GuardModel, StreamDetector, cases, action_for, D, DECISION_TABLE, ACTIONS, ALERT_UNIT_ROWS  # noqa: E402
from common import inject, split_rows, standard_noise  # noqa: E402

OUT = HERE / "judge04_field_check.json"
TMP = Path(tempfile.mkdtemp(prefix="judge04_c2r1_"))
res: dict = dict(tmp_dir=str(TMP))
T_START = time.time()


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def log(msg):
    print(f"[{time.time() - T_START:6.1f}s] {msg}", flush=True)


# ---------------------------------------------------------------- 0. 출처
res["provenance"] = dict(head=git("rev-parse", "HEAD"), status_before=git("status", "--porcelain", "--", "yejun"),
                         python=sys.version.split()[0], omp=os.environ.get("OMP_NUM_THREADS"))
log(f"HEAD {res['provenance']['head']}")

# ---------------------------------------------------------------- 1. 원본에서 재학습(임시 폴더) → 저장 모델·집계와 대조
env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
t0 = time.time()
run = subprocess.run([sys.executable, str(GUARD / "train.py"), "--out", str(TMP / "out"), "--artifacts", str(TMP / "art")],
                     cwd=YEJUN, env=env, capture_output=True, text=True)
manifest = json.loads((GUARD / "outputs" / "manifest.json").read_text())
retrain = dict(returncode=run.returncode, seconds=round(time.time() - t0, 1), stderr_tail=run.stderr[-500:])
for s in ("A", "B"):
    new = sha(TMP / "art" / f"guard_{s}.json")
    local = GUARD / "artifacts" / f"guard_{s}.json"
    retrain[f"guard_{s}"] = dict(retrained_eq_manifest=new == manifest["artifacts"][f"guard_{s}.json"],
                                 retrained_eq_local=local.exists() and new == sha(local))
m_new = pd.read_csv(TMP / "out" / "metrics.csv")
m_old = pd.read_csv(GUARD / "outputs" / "metrics.csv")
try:
    pd.testing.assert_frame_equal(m_new, m_old, check_exact=False, rtol=1e-12, atol=1e-12)
    retrain["metrics_equal_committed"] = True
except AssertionError as e:
    retrain["metrics_equal_committed"] = str(e)[:300]
for s in ("A", "B"):
    try:
        pd.testing.assert_frame_equal(pd.read_csv(TMP / "out" / f"cases_{s}.csv"), pd.read_csv(GUARD / "outputs" / f"cases_{s}.csv"),
                                      check_exact=False, rtol=1e-12, atol=1e-12)
        retrain[f"cases_{s}_equal_committed"] = True
    except AssertionError as e:
        retrain[f"cases_{s}_equal_committed"] = str(e)[:300]
res["retrain_from_raw"] = retrain
log(f"재학습 {retrain}")

models = {s: GuardModel.load(TMP / "art" / f"guard_{s}.json") for s in ("A", "B")}
normal, abnormal, _ = D.load()
test = {s: normal.iloc[split_rows(normal, s)["test"]].reset_index(drop=True) for s in ("A", "B")}

# ---------------------------------------------------------------- 2. 업무량 재계산 + [가정] 점검 시간 부담 + α 설계표
work = pd.read_csv(GUARD / "outputs" / "workload_v2.csv")
wl, burden, plan = [], [], []
for s, m in models.items():
    f = test[s]
    t = pd.to_datetime(f[D.TIME])
    elapsed_h = (t.max() - t.min()).total_seconds() / 3600
    n_units = int(D.segments(f).max() + 1)
    uph = n_units / elapsed_h
    for a in (.01, .03, .05):
        pred = m.predict(D.inputs_only(f), a)
        k = int(pred.notification.sum())
        grid = math.floor(a * (len(m.cal) + 1) + 1e-9) / (len(m.cal) + 1)
        up = float(stats.beta.ppf(.95, k + 1, n_units - k))
        w = work[(work.split_id == s) & (work.model == "guard_v2") & np.isclose(work.alpha, a)].iloc[0]
        row = dict(split=s, alpha=a, units=n_units, first_alerts=k, units_per_elapsed_h=uph,
                   nominal_8h=grid * uph * 8, observed_8h=k / elapsed_h * 8, upper95_8h=up * uph * 8)
        row["match_csv"] = bool(k == w.first_alert_segments and np.isclose(uph, w.units_per_elapsed_hour)
                                and np.isclose(row["nominal_8h"], w.nominal_alerts_per_8h_elapsed)
                                and np.isclose(row["observed_8h"], w.observed_alerts_per_8h_elapsed)
                                and np.isclose(row["upper95_8h"], w.upper95_alerts_per_8h_elapsed))
        wl.append(row)
        for minutes in (5, 10, 15):   # [가정] 알림 1건 현장 확인 시간
            burden.append(dict(split=s, alpha=a, minutes_per_check=minutes,
                               nominal_hours_per_8h=row["nominal_8h"] * minutes / 60,
                               observed_hours_per_8h=row["observed_8h"] * minutes / 60,
                               upper95_hours_per_8h=row["upper95_8h"] * minutes / 60))
    rows_per_unit = len(f) / n_units
    for target in (1, 3, 5, 10, 30):   # 교대 8시간당 목표 오경보(명목) → 필요한 α와 보정 단위
        a_t = target / (uph * 8)
        n_cal = math.ceil(1 / a_t - 1e-9) - 1
        plan.append(dict(split=s, target_alerts_per_8h=target, alpha=a_t, min_cal_units=n_cal,
                         cal_elapsed_hours=n_cal / uph, cal_sensor_minutes=n_cal * rows_per_unit * D.DT / 60))
res["workload"] = wl
res["assumed_check_burden"] = burden
res["alpha_planning"] = plan
log("업무량 " + ", ".join(f"{r['split']} α{r['alpha']}: 관측 {r['observed_8h']:.1f}/명목 {r['nominal_8h']:.1f}/상한 {r['upper95_8h']:.1f} 일치 {r['match_csv']}" for r in wl))

# ---------------------------------------------------------------- 3. 판단표·조치 규칙 정합
dt_csv = pd.read_csv(GUARD / "outputs" / "decision_table_v2.csv")
produced = {action_for(v, c, sh) for v in (False, True) for c in (False, True) for sh in (False, True)}
res["decision_table"] = dict(rows=len(dt_csv), csv_equals_model=dt_csv.to_dict("records") == list(DECISION_TABLE),
                             actions_produced=sorted(produced), all_produced_in_table=produced <= set(dt_csv.action),
                             table_actions_not_produced=sorted(set(dt_csv.action) - produced - {ACTIONS["invalid"]}),
                             check_targets=dt_csv.check_target.tolist())

# ---------------------------------------------------------------- 4. 혼합 대기열 우선순위 [사후] + 커밋된 cases CSV의 순위 성격
def key_sort(q):
    return q.assign(n=q.evidence.str.count(r"\+") + 1).sort_values(["n", "alarm_share", "peak_score"], ascending=False, kind="stable")


queue = {}
for s, m in models.items():
    mixed = pd.concat([test[s], abnormal], ignore_index=True)
    for a in (.01, .03, .05):
        pred = m.predict(D.inputs_only(mixed), a)
        pred["label"] = mixed[D.LABEL].astype(int).to_numpy()
        q = cases(pred)
        q["label"] = q.record_id.map(pred.groupby("record_id").label.first())
        fa = q[q.label == 0]
        queue[f"{s}_a{int(a * 100)}"] = dict(cases=len(q), notifications=int(pred.notification.sum()), false_alarm_cases=len(fa),
                                            false_alarm_ranks=sorted(fa.priority_rank.tolist()),
                                            false_alarm_alarm_rows=fa.alarm_rows.tolist(), false_alarm_evidence=fa.evidence.tolist(),
                                            abnormal_min_alarm_rows=int(q[q.label == 1].alarm_rows.min()),
                                            abnormal_min_share=round(float(q[q.label == 1].alarm_share.min()), 3),
                                            distinct_min_p=sorted({round(v, 6) for v in q.min_p}))
res["mixed_queue_posthoc"] = queue
cb = pd.read_csv(GUARD / "outputs" / "cases_B.csv")
res["committed_cases_B_rank"] = dict(sources=cb.source.value_counts().to_dict(),
                                     duplicated_ranks=int(cb.priority_rank.duplicated().sum()),
                                     normal_ranks_in_file=cb[cb.source == "normal"].priority_rank.tolist(),
                                     ranked_within_source=True if cb.groupby("source").priority_rank.apply(lambda r: sorted(r) == list(range(1, len(r) + 1))).all() else False)
log(f"혼합 대기열 오경보 순위 {[(k, v['false_alarm_ranks']) for k, v in queue.items()]}")

# ---------------------------------------------------------------- 5. 우선순위 키의 라벨 없는 점검: 주입 건 vs 정상 오경보
# 주입 건과 정상 오경보 건을 같은 정렬 키로 한 줄에 세운다(키는 건별 값이라 서로 다른 실행의 건을 합쳐 정렬할 수 있다).
FAMILIES = (("cur_noise", .1), ("cur_noise", .2), ("cur_offset", .4), ("vib_noise", 2.0), ("vib_noise", 4.0))
prio = []
for s, m in models.items():
    rows = split_rows(normal, s)["test"]
    f = D.inputs_only(test[s])
    seg = D.segments(f)
    pos, length = D.segment_positions(seg)
    eligible = np.unique(seg[length >= 30])
    mask = np.isin(seg, eligible) & (pos >= 10)
    z = standard_noise(len(normal), 0)
    for a in (.01, .03, .05):
        base = cases(m.predict(f, a))
        fa = base.assign(kind="false_alarm") if len(base) else pd.DataFrame()
        for fam, lv in FAMILIES:
            fi = inject(f, rows, m, fam, lv, mask, np.ones(len(f)), z)
            qi = cases(m.predict(fi, a))
            qi = qi[qi.record_id.isin(eligible) & (qi.first_alarm_position >= 10)].assign(kind="injected")
            pool = key_sort(pd.concat([qi, fa], ignore_index=True)).reset_index(drop=True)
            pool["rank"] = np.arange(1, len(pool) + 1)
            inj_r, fa_r = pool[pool.kind == "injected"]["rank"], pool[pool.kind == "false_alarm"]["rank"]
            prio.append(dict(split=s, alpha=a, family=fam, level=lv, eligible=len(eligible), injected_cases=len(qi),
                             false_alarms=len(fa_r), false_alarm_ranks=fa_r.tolist(),
                             injected_below_best_false_alarm=int((inj_r > fa_r.min()).sum()) if len(fa_r) else 0,
                             injected_below_all_false_alarms=int((inj_r > fa_r.max()).sum()) if len(fa_r) else 0,
                             injected_single_evidence_share=round(float((qi.evidence.str.count(r"\+") == 0).mean()), 3) if len(qi) else None,
                             injected_share_median=round(float(qi.alarm_share.median()), 3) if len(qi) else None,
                             injected_share_p10=round(float(qi.alarm_share.quantile(.1)), 3) if len(qi) else None,
                             false_alarm_share_max=round(float(fa.alarm_share.max()), 3) if len(fa) else None,
                             injected_actions=qi.action.value_counts().to_dict()))
res["priority_vs_injection"] = prio
log("주입 대 오경보 순위: " + "; ".join(f"{p['split']} α{p['alpha']} {p['family']}{p['level']} 주입{p['injected_cases']}/{p['eligible']} 오경보{p['false_alarms']} 아래{p['injected_below_best_false_alarm']}"
                                    for p in prio if p["false_alarms"]))

# ---------------------------------------------------------------- 6. 2단계 경보 실현 가능성 [사후]: 인접 단위 지속·단위 안 경보 행 수
tier = {}
for s, m in models.items():
    for a in (.01, .03, .05):
        pn = m.predict(D.inputs_only(test[s]), a)
        per = pn.groupby("record_id").alarm.max().to_numpy().astype(bool)
        rows_alarm = pn.groupby("record_id").alarm.sum().to_numpy()
        k, n = int(per.sum()), len(per)
        pairs = int((per[1:] & per[:-1]).sum())
        pa = m.predict(D.inputs_only(abnormal), a)
        ts = pd.to_datetime(abnormal[D.TIME]).reset_index(drop=True)
        rec_alarm = pa.groupby("record_id").alarm.max().to_numpy().astype(bool)
        first_alarm_t = {r: ts[g.index[g.alarm.eq(1)][0]] for r, g in pa.groupby("record_id") if g.alarm.eq(1).any()}
        start = ts.iloc[0]
        tier2 = next((r for r in range(1, len(rec_alarm)) if rec_alarm[r] and rec_alarm[r - 1]), None)
        # 단위 안 2번째 경보 행 시각
        second = {r: ts[g.index[g.alarm.eq(1)][1]] for r, g in pa.groupby("record_id") if g.alarm.sum() >= 2}
        first_rec2 = min(second) if second else None
        tier[f"{s}_a{int(a * 100)}"] = dict(
            normal_units=n, normal_alerted_units=k, normal_adjacent_alerted_pairs=pairs,
            independence_expected_pairs=round((n - 1) * (k / n) ** 2, 4),
            nominal_pair_rate_per_8h_indep=round((math.floor(a * (len(m.cal) + 1) + 1e-9) / (len(m.cal) + 1)) ** 2
                                                 * next(r["units_per_elapsed_h"] for r in wl if r["split"] == s) * 8, 3),
            normal_units_with_2plus_alarm_rows=int((rows_alarm >= 2).sum()),
            abnormal_tier1_delay_s=round((first_alarm_t[0] - start).total_seconds(), 3) if 0 in first_alarm_t else None,
            abnormal_tier2_adjacent_record=tier2,
            abnormal_tier2_adjacent_delay_s=round((first_alarm_t[tier2] - start).total_seconds(), 3) if tier2 is not None else None,
            abnormal_tier2_2rows_record=first_rec2,
            abnormal_tier2_2rows_delay_s=round((second[first_rec2] - start).total_seconds(), 3) if first_rec2 is not None else None,
            abnormal_records_with_2plus_rows=int(sum(1 for r, g in pa.groupby("record_id") if g.alarm.sum() >= 2)))
res["tiering_posthoc"] = tier
log(f"2단계 [사후] {tier}")

# ---------------------------------------------------------------- 7. 연속 입력(R7) — 정상 B 평가 + 이상을 0.1초 간격으로 이어 붙임
def restamp(frame, start="2026-09-27 08:00:00"):
    g = D.inputs_only(frame).copy()
    g[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(g)) * D.DT, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


cont = restamp(pd.concat([test["B"], abnormal], ignore_index=True))
n_norm = len(test["B"])
sd = StreamDetector(models["B"], .01)
pc = pd.concat([sd.push(cont.iloc[i:i + 128]) for i in range(0, len(cont), 128)], ignore_index=True)
pb = models["B"].predict(cont, .01)
qc = cases(pc)
ab_cases = qc[qc.first_row >= n_norm]
first_ab_note = pc.index[(pc.notification == 1) & (pc.index >= n_norm)]
res["continuous_stream_B"] = dict(rows=len(cont), normal_rows=n_norm, records=int(pc.record_id.nunique()),
                                  alert_units=int(pc.groupby(["record_id", "alert_unit"]).ngroups),
                                  notifications_total=int(pc.notification.sum()),
                                  notifications_normal_part=int(pc.notification.iloc[:n_norm].sum()),
                                  notifications_abnormal_part=int(pc.notification.iloc[n_norm:].sum()),
                                  first_abnormal_notification_after_onset_rows=int(first_ab_note[0] - n_norm) if len(first_ab_note) else None,
                                  stream_eq_batch_notifications=bool((pc.notification.to_numpy() == pb.notification.to_numpy()).all()),
                                  cases_total=len(qc), cases_starting_in_abnormal=len(ab_cases),
                                  abnormal_case=ab_cases.iloc[0][["first_row", "alarm_rows", "observed_rows", "alert_units", "evidence", "action", "beyond_calibration_length"]].to_dict() if len(ab_cases) else None,
                                  normal_part_alarm_rows=int(pc.alarm.iloc[:n_norm].sum()))
log(f"연속 입력 {res['continuous_stream_B']}")

# ---------------------------------------------------------------- 8. 품질검사 시간창 실현 가능성: 경보 전후 정상 판정 기록 사이의 시각 창
def suspect_windows(frame, pred):
    ts = pd.to_datetime(frame[D.TIME]).reset_index(drop=True)
    rec = pred.record_id.to_numpy()
    g = pd.DataFrame(dict(rec=rec, t=ts, a=pred.alarm.to_numpy()))
    per = g.groupby("rec").agg(start=("t", "min"), end=("t", "max"), alarm=("a", "max")).reset_index()
    out, i = [], 0
    while i < len(per):
        if not per.alarm[i]:
            i += 1; continue
        j = i
        while j + 1 < len(per) and per.alarm[j + 1]:
            j += 1
        lo = per.end[i - 1] if i > 0 else None
        hi = per.start[j + 1] if j + 1 < len(per) else None
        out.append(dict(first_rec=int(per.rec[i]), records=j - i + 1, open_start=lo is None, open_end=hi is None,
                        alarmed_span_s=(per.end[j] - per.start[i]).total_seconds(),
                        window_s=None if lo is None or hi is None else (hi - lo).total_seconds()))
        i = j + 1
    return out


qw = {}
for s, m in models.items():
    fn = D.inputs_only(test[s]); fa = D.inputs_only(abnormal)
    wn = suspect_windows(fn, m.predict(fn, .01))
    wa = suspect_windows(fa, m.predict(fa, .01))
    qw[s] = dict(normal_false_alarm_windows=wn, abnormal_episodes=wa)
res["quality_window_feasibility"] = qw
spm = (20, 40, 60)   # [가정] 분당 행정 수
fw = [w["window_s"] for w in qw["B"]["normal_false_alarm_windows"] if w["window_s"] is not None]
res["quality_window_parts_assumed_spm"] = {str(x): [round(v / 60 * x, 1) for v in fw] for x in spm}
log(f"품질 창 B 오경보 {fw}, 이상 {qw['B']['abnormal_episodes']}")

# ---------------------------------------------------------------- 9. 재보정 절차 실행(임시 폴더)
import recalibrate  # noqa: E402

seg_all = D.segments(normal)
csv = TMP / "recal_normal_0_479.csv"
D.inputs_only(normal[seg_all < 480]).to_csv(csv, index=False)
rc_ok = recalibrate.main(["--normal", str(csv), "--out", str(TMP / "site.json")])
rep = json.loads((TMP / "site_report.json").read_text())
rc_short = recalibrate.main(["--normal", str(csv), "--out", str(TMP / "site_short.json"), "--cal-units", "50"])
res["recalibrate"] = dict(exit_ok=rc_ok, passed=rep["passed"], units=rep["units"],
                          usage_minutes={k: dict(sensor=round(v["sensor_minutes"], 1), elapsed=round(v["elapsed_minutes"], 1)) for k, v in rep["usage"].items()},
                          checks=[dict(name=c["name"], value=c["value"], limit=c.get("limit"), ok=c["ok"]) for c in rep["checks"]],
                          exit_cal50=rc_short, cal50_model_written=(TMP / "site_short.json").exists())
log(f"재보정 {res['recalibrate']}")

# ---------------------------------------------------------------- 10. 1행 순차 지연(참고)
sd1 = StreamDetector(models["A"], .01)
fa1 = D.inputs_only(test["A"]).iloc[:300]
lat = []
for i in range(len(fa1)):
    t1 = time.perf_counter(); sd1.push(fa1.iloc[i:i + 1]); lat.append((time.perf_counter() - t1) * 1000)
bench = json.loads((GUARD / "outputs" / "benchmark.json").read_text())
res["latency_1row_ms"] = dict(rows=len(lat), p50=round(float(np.percentile(lat, 50)), 2), p95=round(float(np.percentile(lat, 95)), 2),
                              max=round(float(np.max(lat)), 2),
                              committed_benchmark_1row=[dict(p50=r["p50_ms"], p95=r["p95_ms"], max=r["max_ms"]) for r in bench["runs"] if r["chunk"] == 1])

# ---------------------------------------------------------------- 11. 웹 API(임시 포트)
sys.argv = ["serve.py"]
import serve  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

console = serve.Console()
console.models = models   # 원본에서 재학습한 모델로 교체(로컬 artifact와 해시 동일 여부는 1번에 기록)
server = ThreadingHTTPServer(("127.0.0.1", 0), serve.handler(console))
port = server.server_address[1]
th = threading.Thread(target=server.serve_forever, daemon=True)
th.start()


def call(path, body=None, raw=False):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    return data.decode() if raw else json.loads(data)


web = dict(port=port)
try:
    html = call("/", raw=True)
    web["html_has_per_unit_alpha"] = "(구간당)" in html
    web["html_has_priority_sort"] = "우선순위순" in html
    m30 = re.search(r"교대 8시간에 약 ([0-9~]+)건", html)
    web["html_shift_claim"] = m30.group(1) if m30 else None
    web["html_mentions_quality_inspection"] = "품질" in html
    ov = call("/api/overview")
    w_csv = work[work.model.eq("guard_v2")].reset_index(drop=True)
    w_api = pd.DataFrame(ov["workload"])
    web["overview"] = dict(audit_all_ok=ov["audit"].get("all_ok"), audit_checks=len(ov["audit"].get("checks", [])),
                           decision_table_eq_csv=ov["decision_table"] == dt_csv.to_dict("records"),
                           workload_rows=len(w_api), workload_eq_csv=bool(np.allclose(w_api.upper95_alerts_per_8h_elapsed, w_csv.upper95_alerts_per_8h_elapsed)),
                           alert_unit_rows=ov["alert_unit_rows"])
    for s in ("A", "B"):
        for a in (.01, .05):
            r = call("/api/analyze", dict(split=s, alpha=a, dataset="mixed"))
            cs = pd.DataFrame(r["cases"])
            web[f"mixed_{s}_a{int(a * 100)}"] = dict(cases=len(cs), notifications=r["stats"]["notifications"],
                                                     false_alarm_ranks=sorted(cs[cs.reference_label == 0].priority_rank.tolist()),
                                                     distinct_min_p=sorted({round(v, 6) for v in cs.min_p}),
                                                     threshold=round(r["threshold"], 4), min_p_attainable=round(r["min_p_attainable"], 6),
                                                     case_fields=sorted(cs.columns))
    up = call("/api/analyze", dict(split="B", alpha=.01, dataset="upload", csv=cont.to_csv(index=False)))
    cu = pd.DataFrame(up["cases"])
    web["upload_continuous_B"] = dict(rows=up["stats"]["rows"], segments=up["stats"]["segments"], cases=len(cu),
                                      notifications=up["stats"]["notifications"],
                                      cases_first_row_ge_normal=int((cu.first_row >= n_norm).sum()) if len(cu) else 0)
    one = pd.DataFrame({D.TIME: ["2026-09-27 12:00:00.000"], "AI0_Vibration": [models["A"].mean[0]], "AI1_Vibration": [models["A"].mean[1]],
                        "AI2_Current": [models["A"].mean[2] + 30 * models["A"].scale[2]]})
    u1 = call("/api/analyze", dict(split="A", alpha=.01, dataset="upload", csv=one.to_csv(index=False)))
    web["upload_one_row_current_spike"] = [dict(evidence=c["evidence"], action=c["action"], magnitude_sensors=c["magnitude_sensors"]) for c in u1["cases"]]
finally:
    server.shutdown(); server.server_close(); th.join(timeout=5)
web["server_stopped"] = not th.is_alive()
res["web_api"] = web
log(f"웹 {web}")

# ---------------------------------------------------------------- 12. 현장 활용 제안 요소의 존재 여부(문서·화면·코드 전수 검색)
files = [GUARD / "README.md", GUARD / "web" / "index.html", GUARD / "web" / "app.js", GUARD / "model.py", GUARD / "analyze.py",
         GUARD / "recalibrate.py", SUPP / "README.md", YEJUN / "analysis" / "press_evidence" / "README.md",
         YEJUN / "analysis" / "press_dayshift" / "README.md", YEJUN / "press_submission" / "outputs" / "field_decision_table.md"]
text = {str(p.relative_to(YEJUN)): p.read_text() for p in files}
KEYS = dict(cost=r"비용|절감|기대효과|손실", sop=r"운영 절차|절차서|흐름도|SOP|대응 시간|담당", quality_rule=r"품질검사|검사 대상|전수|샘플링|로트",
            tier=r"주의|경고 단계|단계 경보|격상|에스컬레이션", feedback=r"피드백|점검 결과|조치 결과|확인 결과",
            drift=r"드리프트|재보정 주기|재보정 트리거|교대별 감시|알림률 감시", integration=r"MES|PLC|SCADA|CMMS|엣지|경광등|문자 알림",
            guidebook_pain=r"2~3일|기어 마모|출력 유압")
res["proposal_elements"] = {k: {f: len(re.findall(pat, t)) for f, t in text.items() if re.findall(pat, t)} for k, pat in KEYS.items()}
log(f"제안 요소 검색 {res['proposal_elements']}")

# ---------------------------------------------------------------- 13. README 수치 대조
readme = (GUARD / "README.md").read_text()
b1 = next(r for r in wl if r["split"] == "B" and r["alpha"] == .01)
res["readme_claims"] = dict(
    b_a1_observed_60=bool(re.search(r"약 60건\(3/180\)", readme)) and round(b1["observed_8h"]) == 60,
    b_a1_upper_152=bool(re.search(r"약 152건", readme)) and round(b1["upper95_8h"]) == 152,
    rank_22_24_claim=bool(re.search(r"22~24위", readme)), rank_22_24_actual=queue["B_a1"]["false_alarm_ranks"],
    recal_claim_2_of_60=bool(re.search(r"알림 2/60\(한도 2\)", readme)),
    recal_actual=[(c["name"], c["value"], c.get("limit")) for c in res["recalibrate"]["checks"]][:1])

# ---------------------------------------------------------------- 14. 종료: 저장소 변경 없음 확인
after = git("status", "--porcelain", "--", "yejun")
res["provenance"]["status_after"] = after
res["provenance"]["changes_outside_cycle2"] = [l for l in after.splitlines() if "analysis/press_rubric_review/cycle2/" not in l]
res["provenance"]["pycache_created"] = [str(p) for p in YEJUN.rglob("__pycache__") if p.stat().st_mtime > T_START]
res["elapsed_s"] = round(time.time() - T_START, 1)
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
log(f"완료 → {OUT} (임시 폴더 {TMP})")
