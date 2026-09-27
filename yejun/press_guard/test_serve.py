"""serve.py의 API 계약 검사. 네트워크 없이 Console을 직접 호출하고, 실제 HTTP 경로는 임시 포트로 한 번 확인한다."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pandas as pd
import pytest

from model import D, HERE
from serve import Console, handler, score_threshold


@pytest.fixture(scope="module")
def console():
    return Console()


def test_threshold_matches_rank_rule(console):
    for split, model in console.models.items():
        pred = model.predict(console.abnormal, .05)
        for alpha in (.01, .03, .05):
            thr = score_threshold(model.cal, alpha)
            p = model.predict(console.abnormal, alpha)
            finite = np.isfinite(p.score.to_numpy())
            assert np.array_equal(p.alarm.to_numpy()[finite], (p.score.to_numpy()[finite] > thr).astype(int)), (split, alpha)
        assert score_threshold(model.cal, .001) == float("inf")
        assert len(pred) == 600


def test_analyze_contract_and_cache(console):
    result = console.analyze({"split": "A", "alpha": .01, "dataset": "mixed"})
    metrics = pd.read_csv(HERE / "outputs" / "metrics.csv")
    row = metrics[metrics.split.eq("A") & metrics.model.eq("guard_v2") & metrics.alpha.eq(.01)].iloc[0]
    assert result["stats"]["alarm_rows"] == row.tp + row.fp and result["stats"]["notifications"] == row.abnormal_notified_segments + row.normal_notified_segments
    assert len(result["cases"]) == result["stats"]["notifications"] and len(result["points"]) == result["stats"]["rows"]
    assert {"record_id", "first_row", "evidence", "action", "reference_label", "detection_delay_s"} <= set(result["cases"][0])
    assert {"AI2_Current", "g_dynamics", "g_waveform", "g_magnitude", "p_value", "alarm", "notification", "status"} <= set(result["points"][0])
    assert all(c["reference_label"] in (0, 1) for c in result["cases"])
    assert {"priority_rank", "magnitude_sensors", "alarm_share", "alert_units", "beyond_calibration_length"} <= set(result["cases"][0])
    assert sorted(c["priority_rank"] for c in result["cases"]) == list(range(1, len(result["cases"]) + 1))
    assert result["min_p_attainable"] == 1 / 121 and result["alert_unit_rows"] == 50
    # 2단계 경보·품질 시간창·이상 확률(평가관 04 U1·U2, 02 M1)
    assert {"level", "level_name", "escalation_row", "suspect_from", "suspect_to", "suspect_seconds", "suspect_open", "quality_action",
            "max_probability", "max_likelihood_ratio"} <= set(result["cases"][0])
    assert {"alert_level", "escalation", "likelihood_ratio", "anomaly_probability", "record_probability"} <= set(result["points"][0])
    assert result["prior"] == .01 and result["probability_available"] is True
    assert sum(result["level_counts"].values()) == len(result["cases"])
    assert all(c["level"] == 2 for c in result["cases"] if c["reference_label"] == 1)     # 이상 21구간은 모두 격상
    assert console.analyze({"split": "A", "alpha": .01, "dataset": "mixed"}) is result   # 캐시
    json.dumps(result, allow_nan=False)   # NaN 없이 직렬화 가능


def test_upload_equals_builtin(console):
    sp = D.split_normal(console.normal, D.segments(console.normal), "B")
    csv = pd.concat([sp["test"], console.abnormal], ignore_index=True).to_csv(index=False)
    up = console.analyze({"split": "B", "alpha": .03, "dataset": "upload", "csv": csv})
    built = console.analyze({"split": "B", "alpha": .03, "dataset": "mixed"})
    assert up["stats"]["alarm_rows"] == built["stats"]["alarm_rows"] and len(up["cases"]) == len(built["cases"])
    assert "reference_label" not in up["cases"][0] and up["threshold"] == built["threshold"]


def test_prior_changes_probability_not_alarms(console):
    """사전 비율은 확률만 바꾸고 경보·알림은 그대로다. 확률은 우도비에 단조다."""
    lo = console.analyze({"split": "B", "alpha": .01, "dataset": "abnormal", "prior": .001})
    hi = console.analyze({"split": "B", "alpha": .01, "dataset": "abnormal", "prior": .1})
    assert lo["stats"] == {**hi["stats"], "elapsed_s": lo["stats"]["elapsed_s"]}
    a = pd.DataFrame(lo["points"]); b = pd.DataFrame(hi["points"])
    assert (a.alarm == b.alarm).all() and np.allclose(a.likelihood_ratio, b.likelihood_ratio, equal_nan=True)
    ok = a.likelihood_ratio.notna()
    assert (b.anomaly_probability[ok] >= a.anomaly_probability[ok]).all()


@pytest.mark.parametrize("request_, message", [
    ({"split": "C"}, "분할/경보"), ({"alpha": .02}, "분할/경보"), ({"dataset": "other"}, "자료"), ({"prior": .5}, "사전 비율"),
    ({"dataset": "upload", "csv": "a,b\n1,2\n"}, "필수 열"), ({"dataset": "upload", "csv": "TimeStamp,AI0_Vibration,AI1_Vibration,AI2_Current\n"}, "행"),
])
def test_rejects_bad_requests(console, request_, message):
    with pytest.raises((ValueError, KeyError), match=message):
        console.analyze(request_)


def test_overview_lists_metrics_external_audit(console):
    o = console.overview()
    assert len(o["metrics"]) == 12 and len(o["external"]) == 18
    assert isinstance(o["audit"], dict) and isinstance(o["benchmark"], dict)
    assert isinstance(o["conditions"], list) and isinstance(o["robustness"], list)
    assert len(o["decision_table"]) == 6 and o["alert_unit_rows"] == 50
    assert all({"checklist", "failure_modes", "source"} <= set(r) for r in o["decision_table"])
    assert o["outcome_columns"] == ["confirmed_at", "owner", "outcome", "measure", "status"] and o["escalation_alarm_rows"] == 2
    for key in ("levels", "probability", "label_free", "quality_windows", "monitor_gain", "expected_effect"):
        assert isinstance(o[key], list) and len(o[key]) > 0, key
    if o["workload"]:
        assert len(o["workload"]) == 6 and {"nominal_alerts_per_8h_elapsed", "upper95_alerts_per_8h_elapsed"} <= set(o["workload"][0])
    if o["conditions"]:
        assert {"split_id", "model", "subset", "condition", "value", "rows", "error_rows"} <= set(o["conditions"][0])


def test_http_routes(console):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(console))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        for path, mime in (("/", "text/html"), ("/app.js", "text/javascript"), ("/style.css", "text/css"), ("/api/overview", "application/json")):
            with urllib.request.urlopen(base + path) as r:
                assert r.status == 200 and r.headers["Content-Type"].startswith(mime), path
        req = urllib.request.Request(base + "/api/analyze", data=json.dumps({"split": "B", "alpha": .05, "dataset": "abnormal"}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
        assert body["stats"]["rows"] == 600 and len(body["cases"]) == 21
        bad = urllib.request.Request(base + "/api/analyze", data=b"[1]", headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(bad)
        assert err.value.code == 400
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(base + "/missing")
        assert err.value.code == 404
    finally:
        server.shutdown(); server.server_close()
