"""현장 활용 독립 검수. 제품 소스·산출물을 쓰지 않고 검수 JSON만 만든다."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request

ROOT = Path(__file__).resolve().parents[4]
GUARD = ROOT / "press_guard"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(GUARD))
import numpy as np
import pandas as pd
from scipy.stats import beta
from model import D, GuardModel, StreamDetector, cases, incidents, layout, load_bundle, PRIORITY_KEY
from monitor import (Reference, monitor_windows, exclude_unconfirmed_windows,
                     ACTION_OBSERVE, ACTION_RECALIBRATE, ACTION_INSPECT_SHIFT, ACTION_INSPECT)
from recalibrate import inject, unit_layout
import simulate

START = time.perf_counter()
RESULT = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": {}}
PATHS = ["model.py", "monitor.py", "recalibrate.py", "serve.py", "simulate.py", "train.py", "insights.py",
         "OPERATIONS.md", "README.md", "web/app.js", "web/index.html", "artifacts/guard_A.json", "artifacts/guard_B.json",
         "artifacts/probability_A.json", "artifacts/probability_B.json", "outputs/cases_A.csv", "outputs/cases_B.csv",
         "outputs/incidents_A.csv", "outputs/incidents_B.csv", "outputs/incident_summary_v2.csv", "outputs/alert_levels_v2.csv",
         "outputs/expected_effect_v2.csv", "outputs/monitor_gain_v2.csv", "outputs/queue_injection_ranks_v2.csv",
         "outputs/quality_windows_v2.csv", "outputs/decision_table_v2.csv", "outputs/metrics.csv", "outputs/rolling.csv"]

def hashes():
    return {p: hashlib.sha256((GUARD / p).read_bytes()).hexdigest() for p in PATHS}

def jsonable(obj):
    obj = D.to_jsonable(obj)
    if isinstance(obj, dict): return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list): return [jsonable(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj): return None
    return obj

def save():
    (HERE / "judge04_r4_check.json").write_text(json.dumps(jsonable(RESULT), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

def check(name, fn):
    start = time.perf_counter()
    try:
        out = fn()
        RESULT["checks"][name] = {"ok": True, "seconds": round(time.perf_counter() - start, 3), "result": out}
        print(f"PASS {name}: {time.perf_counter() - start:.2f}s", flush=True)
    except Exception:
        RESULT["checks"][name] = {"ok": False, "seconds": round(time.perf_counter() - start, 3), "error": traceback.format_exc()}
        print(f"FAIL {name}\n{traceback.format_exc()}", flush=True)
    save()

RESULT["head_start"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
RESULT["hashes_start"] = hashes()
NORMAL, ABNORMAL, DATA_REPORT = D.load()
RESULT["original_data"] = DATA_REPORT
SEG = D.segments(NORMAL)
MODELS = {s: load_bundle(GUARD / "artifacts" / f"guard_{s}.json") for s in ("A", "B")}
SPLITS = {s: D.split_normal(NORMAL, SEG, s) for s in MODELS}
B = D.inputs_only(SPLITS["B"]["test"]).reset_index(drop=True)
BP = MODELS["B"].predict(B)
BSEG = layout(B)[1]
REF = Reference.from_frame(pd.concat([SPLITS["B"]["train"], SPLITS["B"]["cal"]], ignore_index=True))

def pair_frame():
    parts, start = [], pd.Timestamp("2022-07-12T00:00:00")
    for record in (0, 3, 41, 0):
        part = B[BSEG == record].copy().reset_index(drop=True)
        part[D.TIME] = (start + pd.to_timedelta(np.arange(len(part)) / 10, unit="s")).astype(str)
        start += pd.Timedelta(seconds=(len(part) - 1) / 10 + 2)
        parts.append(part)
    return pd.concat(parts, ignore_index=True)

PAIR = pair_frame()

def state_and_pair():
    queue = cases(BP)
    assert queue.record_id.tolist() == [3, 41, 150]
    assert queue.operating_state.tolist() == ["load"] * 3
    counts = {"load": [0, 0], "low": [0, 0], "short": [0, 0]}
    for record in np.unique(BSEG):
        values = B.loc[BSEG == record, D.SENSORS[2]].to_numpy(float)
        rms = np.std(values)
        state = "short" if len(values) < 17 else "load" if rms >= 91.9 else "low"
        observed = BP[BP.record_id.eq(record)]
        assert observed.operating_state.iloc[-1] == state
        assert np.isclose(observed.record_current_rms.iloc[-1], rms, atol=1e-10)
        counts[state][0] += int(observed.alarm.max())
        counts[state][1] += 1
    assert counts == {"load": [3, 51], "low": [0, 94], "short": [0, 35]}
    pred = MODELS["B"].predict(PAIR)
    cq, iq = cases(pred), incidents(cases(pred), pred)
    assert cq.alarm_rows.tolist() == [1, 1]
    assert pred.incident_notification.sum() == pred.incident_escalation.sum() == 1
    row = int(pred.loc[pred.incident_escalation.eq(1), "row_id"].iloc[0])
    assert len(iq) == 1 and iq.level.iloc[0] == 2 and iq.escalation_row.iloc[0] == row
    assert incidents(cq).escalation_row.iloc[0] == row
    stream_results = {}
    for chunk in (1, 7, 128):
        stream = StreamDetector(MODELS["B"])
        actual = pd.concat([stream.push(PAIR.iloc[i:i + chunk]) for i in range(0, len(PAIR), chunk)], ignore_index=True)
        pd.testing.assert_frame_equal(actual, pred, rtol=1e-10, atol=1e-10)
        stream_results[str(chunk)] = "all columns identical within 1e-10"
    log = simulate.run(PAIR, MODELS["B"], chunk=7)
    assert log[log.notify.eq(1)].kind.tolist() == ["사건 시작", "격상"]
    assert int(log[log.kind.eq("격상")].row_id.iloc[0]) == row
    return {"B_state_counts_alarm_total": counts, "B_cases": queue[["record_id", "operating_state", "first_alarm_operating_state", "record_current_rms"]].to_dict("records"),
            "pair_rows": len(PAIR), "pair_cases": cq[["record_id", "alarm_rows", "level"]].to_dict("records"),
            "pair_incident": iq.to_dict("records"), "pair_notification_rows": log[["row_id", "kind", "level", "notify"]].to_dict("records"), "stream": stream_results}

def stored_incidents():
    rows = []
    for split, model in MODELS.items():
        for alpha in (.01, .03, .05):
            for subset, frame in (("normal_test", SPLITS[split]["test"]), ("abnormal", ABNORMAL)):
                p = model.predict(frame, alpha)
                # 독립 사건 정의: 시간순 알림 단위에서 바로 앞 단위도 경보이고 공백 <=60초인 경우 이어짐.
                blocks = p.groupby(["record_id", "alert_unit"], sort=False)
                previous, previous_end, count, inc, start_rows, escalate_rows = False, None, 0, 0, [], []
                for _, g in blocks:
                    t = pd.to_datetime(g.timestamp, format="mixed", utc=True)
                    alarms = g[g.alarm.eq(1)]
                    if len(alarms):
                        if not (previous and (t.iloc[0] - previous_end).total_seconds() <= 60):
                            inc += 1; count = 0
                            start_rows.append(int(alarms.row_id.iloc[0]))
                        for r in alarms.itertuples():
                            count += 1
                            if count == 2: escalate_rows.append(int(r.row_id))
                    previous, previous_end = bool(len(alarms)), t.iloc[-1]
                assert start_rows == p.loc[p.incident_notification.eq(1), "row_id"].astype(int).tolist()
                assert escalate_rows == p.loc[p.incident_escalation.eq(1), "row_id"].astype(int).tolist()
                iq = incidents(cases(p), p)
                if subset == "abnormal":
                    assert len(iq) == 1 and iq.level.iloc[0] == 2 and len(start_rows) + len(escalate_rows) == 2
                rows.append(dict(split=split, alpha=alpha, subset=subset, incidents=len(start_rows), escalations=len(escalate_rows)))
        mixed = pd.concat([SPLITS[split]["test"], ABNORMAL], ignore_index=True)
        p = model.predict(mixed)
        expected = incidents(cases(p), p)
        saved = pd.read_csv(GUARD / "outputs" / f"incidents_{split}.csv")
        for col in ("first_row", "cases", "level", "escalation_row", "operating_state", "alarm_rows", "quality_action"):
            pd.testing.assert_series_equal(expected[col].reset_index(drop=True), saved[col], check_names=False, check_dtype=False)
        ab = saved[saved.source.eq("abnormal")]
        assert ab.escalation_row.notna().all()
    return rows

def monitor_actions():
    details = []
    saved = pd.read_csv(GUARD / "outputs/monitor_gain_v2.csv")
    for gain in (1.0, 1.3, 1.5):
        f = B.copy(); f[D.SENSORS[2]] *= gain
        p = MODELS["B"].predict(f)
        w = monitor_windows(p, f, .01, len(MODELS["B"].cal), REF)
        changed = monitor_windows(p, f, .01, len(MODELS["B"].cal), REF, operating_changes=w.start.tolist())
        want = {1.0: ACTION_OBSERVE, 1.3: ACTION_INSPECT, 1.5: ACTION_INSPECT_SHIFT}[gain]
        assert w.recommended_action.iloc[0] == want
        if gain != 1: assert changed.recommended_action.iloc[0] == ACTION_RECALIBRATE
        item = saved[saved.split.eq("B") & saved.alpha.eq(.01) & saved.gain.eq(gain)].iloc[0]
        stringify = lambda x: " / ".join(f"{r.window}:{r.recommended_action}" for r in x.itertuples())
        assert item.recommended_actions_no_change == stringify(w)
        assert item.recommended_actions_with_change == stringify(changed)
        assert item.incident_notifications == w.incident_notifications.sum()
        details.append({"gain": gain, "windows": w.to_dict("records"), "changed": changed.recommended_action.tolist()})
    f = inject(B, MODELS["B"], "vib_noise", 1.0, BSEG >= 120, np.random.default_rng(0))
    w = monitor_windows(MODELS["B"].predict(f), f, .01, 120, REF)
    assert w.recommended_action.tolist() == [ACTION_OBSERVE, ACTION_OBSERVE, ACTION_INSPECT]
    pa = MODELS["B"].predict(ABNORMAL)
    wa = monitor_windows(pa, ABNORMAL, .01, 120, REF, window_units=5)
    assert wa.level1_notifications.sum() == wa.level2_escalations.sum() == 1
    assert wa.incident_notifications.sum() == 2
    return {"gain_scenarios": details, "last_window_vibration": w.to_dict("records"), "abnormal_across_five_windows": wa.to_dict("records")}

def exclusion():
    rows = []
    t = pd.to_datetime(B[D.TIME], format="mixed", utc=True)
    end = B[BSEG < 60][D.TIME].iloc[-1]
    want_drop = int((BSEG < 60).sum())
    for action in (ACTION_INSPECT, ACTION_INSPECT_SHIFT, ACTION_RECALIBRATE, ACTION_OBSERVE):
        for outcome in (None, "", "보류", "이상 확인", "정상 확인"):
            w = pd.DataFrame([dict(start=B[D.TIME].iloc[0], end=end, recommended_action=action)])
            if outcome is not None: w["outcome"] = outcome
            kept, report = exclude_unconfirmed_windows(B, w)
            expected = want_drop if action.startswith("설비 점검 요청") and outcome != "정상 확인" else 0
            assert report["rows_removed"] == expected and len(kept) == len(B) - expected
            rows.append(dict(action=action, outcome=outcome, **report))
    return rows

def expected_effect_raw():
    details = []
    for end in (180, 240, 420):
        tr = NORMAL[SEG < end]; cal = NORMAL[(SEG >= end) & (SEG < end + 120)]
        test = NORMAL[(SEG >= end + 120) & (SEG < end + 180)]
        fitted = GuardModel.fit(tr, cal, split=f"judge04_to_{end}")
        p = fitted.predict(test, .05)
        counts = p.groupby("record_id").alarm.sum()
        detail = dict(window=f"{end + 120}~{end + 179}", counts={str(int(i + end + 120)): int(v) for i, v in counts[counts > 0].items()},
                      level1=int((counts > 0).sum()), level2=int((counts >= 2).sum()))
        details.append(detail)
    assert [d["level1"] for d in details] == [5, 2, 2]
    assert [d["level2"] for d in details] == [1, 0, 0]
    t = pd.to_datetime(B[D.TIME], format="mixed")
    nominal = 1 / 121 * 180 / ((t.max() - t.min()).total_seconds() / 3600) * 8
    table = pd.read_csv(GUARD / "outputs/expected_effect_v2.csv")
    point = table[table.alert_scenario.eq("비중첩 폴드 추정(주추정)")]
    upper = table[table.alert_scenario.eq("비중첩 폴드 추정 95% 상한")]
    assert point.post_hoc.all() and point.evaluation_overlaps_rule_selection.eq(False).all()
    assert np.allclose(point.level2_per_8h, nominal / 7)
    assert np.allclose(upper.level2_per_8h, nominal * beta.ppf(.95, 2, 6))
    for alpha, numerator, denominator in ((.03, 2, 5), (.05, 3, 7)):
        p = MODELS["B"].predict(B, alpha)
        counts = p.groupby("record_id").alarm.sum()
        assert int((counts > 0).sum()) == denominator and int((counts >= 2).sum()) == numerator
        pick = table[table.alert_scenario.eq(f"민감도(동결 B α{int(alpha*100)}%)")]
        assert np.allclose(pick.level2_per_8h, nominal * numerator / denominator)
    # 제품 함수와 독립적으로 모든 가정별 점검시간/손익분기 산식 재계산.
    level1 = np.where(table.policy.eq("전건 확인"), table.level1_per_8h * table.assume_minutes_level1, 0)
    hours = (level1 + table.level2_per_8h.fillna(0) * table.assume_minutes_level2) / 60
    np.testing.assert_allclose(hours, table.inspection_hours_per_shift)
    year = hours * table.assume_shifts_per_day * table.assume_days_per_year
    avoided = table.assume_failures_per_year * table.source_detect_probability * table.assume_avoided_fraction * table.source_downtime_days * table.assume_shifts_per_day * 8
    np.testing.assert_allclose(year / avoided, table.breakeven_loss_ratio)
    return {"raw_refit_folds": details, "nominal_per_8h": nominal, "primary_per_8h": nominal / 7,
            "primary_upper95": nominal * beta.ppf(.95, 2, 6), "effect_rows_recalculated": len(table),
            "middle_primary": point[point.case.eq("중간")].to_dict("records")}

def queue_rankings_raw():
    saved = pd.read_csv(GUARD / "outputs/queue_injection_ranks_v2.csv")
    saved = saved[saved.key.eq(PRIORITY_KEY)].reset_index(drop=True)
    results = []
    for row in saved.itertuples():
        model = MODELS[row.split]
        raw = D.inputs_only(SPLITS[row.split]["test"])
        units, pos, size = unit_layout(raw)
        mask = (size >= 30) & (pos >= 10)
        pn = model.predict(raw, row.alpha)
        f = inject(raw, model, row.family, row.level_value, mask, np.random.default_rng(0))
        pi = model.predict(f, row.alpha)
        normal = incidents(cases(pn), pn)
        injected = incidents(cases(pi), pi)
        selected = set(pi.loc[mask, "record_id"].astype(int))
        if len(injected):
            injected = injected[injected.records.map(lambda value: bool(set(map(int, str(value).split("+"))) & selected))]
        joined = pd.concat([normal.assign(kind="normal"), injected.assign(kind="injected")], ignore_index=True)
        # 독립 정렬: 단계, 근거 개수, 경보 행 비율, 최대 점수 내림차순; 동점은 입력 시간순.
        ordered = joined.sort_values(["level", "evidence_count", "alarm_share", "peak_score"], ascending=False, kind="stable")
        kinds = ordered.kind.tolist()
        below = sum(k == "injected" for k in kinds[kinds.index("normal") + 1:]) if "normal" in kinds else 0
        assert len(normal) == row.false_alarm_incidents and len(injected) == row.injected_incidents
        assert below == row.injected_incidents_below_best_false_alarm
        results.append(dict(split=row.split, alpha=row.alpha, family=row.family, level=row.level_value, below=below))
    residual = [x for x in results if x["below"]]
    assert len(residual) == 2 and sum(x["below"] for x in residual) == 2
    return {"conditions_recomputed": len(results), "residual": residual}

def command_checks():
    result = {}
    with tempfile.TemporaryDirectory(prefix="judge04_r4_") as tmp:
        tmp = Path(tmp)
        cli_env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
        normal_path = tmp / "normal.csv"; D.inputs_only(NORMAL).to_csv(normal_path, index=False)
        bf = tmp / "B.csv"; B.to_csv(bf, index=False)
        mon = subprocess.run([sys.executable, str(GUARD / "monitor.py"), "--csv", str(bf), "--split", "B", "--out", str(tmp / "windows.csv")],
                             env=cli_env, capture_output=True, text=True, timeout=120)
        assert mon.returncode == 0, mon.stderr
        table = pd.read_csv(tmp / "windows.csv")
        assert table.alerted_units.tolist() == [2, 0, 1]
        result["monitor"] = dict(returncode=mon.returncode, stdout=mon.stdout, stderr=mon.stderr)
        pending = pd.DataFrame([dict(start=NORMAL[D.TIME].iloc[0], end=NORMAL.loc[SEG < 60, D.TIME].iloc[-1], recommended_action=ACTION_INSPECT_SHIFT)])
        for outcome in ("", "정상 확인"):
            win = pending.assign(outcome=outcome); wp = tmp / "input_windows.csv"; win.to_csv(wp, index=False)
            suffix = "pending" if not outcome else "confirmed"
            report = tmp / f"{suffix}_report.json"
            completed = subprocess.run([sys.executable, str(GUARD / "recalibrate.py"), "--normal", str(normal_path), "--windows", str(wp),
                                        "--out", str(tmp / f"{suffix}.json"), "--report", str(report)], env=cli_env, capture_output=True, text=True, timeout=120)
            assert completed.returncode in (0, 1), completed.stderr
            content = json.loads(report.read_text())
            expected = int((SEG < 60).sum()) if not outcome else 0
            assert content["excluded_by_windows"]["rows_removed"] == expected
            assert content["units"]["total"] == (540 if not outcome else 600)
            result[suffix] = {"returncode": completed.returncode, "excluded": content["excluded_by_windows"], "units": content["units"],
                              "passed": content["passed"], "model_saved": content["model_saved"], "stdout": completed.stdout, "stderr": completed.stderr}
    node = subprocess.run(["node", str(GUARD / "test_web.cjs")], capture_output=True, text=True, timeout=120)
    assert node.returncode == 0, node.stderr
    result["node_web"] = dict(returncode=node.returncode, stdout=node.stdout, stderr=node.stderr)
    return result

def actual_http_api():
    from http.server import ThreadingHTTPServer
    import serve
    console = serve.Console()
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.handler(console))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as response:
            assert response.status == 200
            return json.loads(response.read())
    try:
        overview = request("/api/overview")
        assert overview["audit"].get("all_ok") is True, "최종 코드와 동결 산출물의 audit 연결이 완결되어야 한다"
        gain = [r for r in overview["monitor_gain"] if r["split"] == "B" and r["gain"] == 1.3][0]
        assert "0:" + ACTION_INSPECT in gain["recommended_actions_no_change"]
        pair = request("/api/analyze", dict(split="B", alpha=.01, prior=.01, dataset="upload", csv=PAIR.to_csv(index=False)))
        assert pair["level_counts"] == {"주의": 0, "점검 요청": 1}
        assert pair["stats"]["incident_notifications"] == 2
        assert pair["incidents"][0]["level"] == 2 and "전수 확인" in pair["incidents"][0]["quality_action"]
        normal = request("/api/analyze", dict(split="B", alpha=.01, prior=.01, dataset="normal"))
        assert all(c["operating_state"] == "load" for c in normal["cases"])
        abnormal = request("/api/analyze", dict(split="B", alpha=.01, prior=.01, dataset="abnormal"))
        assert abnormal["stats"]["incident_notifications"] == 2
        assert abnormal["stats"]["case_notifications"] == 21
        assert all(np.isclose(i["max_probability"], .55) for i in abnormal["incidents"])
        (HERE / "judge04_api_pair.json").write_text(json.dumps({k: v for k, v in pair.items() if k != "points"}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"port": port, "pair": {k: pair[k] for k in ("stats", "level_counts", "incidents")},
                "normal_stats": normal["stats"], "abnormal_stats": abnormal["stats"], "overview_audit_at_request": overview["audit"],
                "api_monitor_matches_csv": True, "server_shutdown": True}
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        assert not thread.is_alive()

for name, fn in (("R3_04_raw_state_and_R3_02_pair", state_and_pair),
                 ("R3_02_stored_incidents_independent", stored_incidents),
                 ("R3_01_actions_R3_05_incident_monitor", monitor_actions),
                 ("R3_01_20_exclusion_combinations", exclusion),
                 ("R3_03_raw_fold_and_effect_math", expected_effect_raw),
                 ("R3_05_incident_queue_30_conditions", queue_rankings_raw),
                 ("direct_CLI_and_web_regression", command_checks),
                 ("actual_HTTP_API", actual_http_api)):
    check(name, fn)

RESULT["head_end"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
RESULT["hashes_end"] = hashes()
RESULT["hashes_changed_during_review"] = [p for p in PATHS if RESULT["hashes_start"][p] != RESULT["hashes_end"][p]]
RESULT["total_seconds"] = round(time.perf_counter() - START, 3)
RESULT["all_ok"] = all(c["ok"] for c in RESULT["checks"].values()) and not RESULT["hashes_changed_during_review"]
save()
print(f"DONE all_ok={RESULT['all_ok']} seconds={RESULT['total_seconds']}", flush=True)
raise SystemExit(0 if RESULT["all_ok"] else 1)
