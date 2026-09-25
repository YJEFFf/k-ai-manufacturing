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
    assert console.analyze({"split": "A", "alpha": .01, "dataset": "mixed"}) is result   # 캐시
    json.dumps(result, allow_nan=False)   # NaN 없이 직렬화 가능


def test_upload_equals_builtin(console):
    sp = D.split_normal(console.normal, D.segments(console.normal), "B")
    csv = pd.concat([sp["test"], console.abnormal], ignore_index=True).to_csv(index=False)
    up = console.analyze({"split": "B", "alpha": .03, "dataset": "upload", "csv": csv})
    built = console.analyze({"split": "B", "alpha": .03, "dataset": "mixed"})
    assert up["stats"]["alarm_rows"] == built["stats"]["alarm_rows"] and len(up["cases"]) == len(built["cases"])
    assert "reference_label" not in up["cases"][0] and up["threshold"] == built["threshold"]


@pytest.mark.parametrize("request_, message", [
    ({"split": "C"}, "분할/경보"), ({"alpha": .02}, "분할/경보"), ({"dataset": "other"}, "자료"),
    ({"dataset": "upload", "csv": "a,b\n1,2\n"}, "필수 열"), ({"dataset": "upload", "csv": "TimeStamp,AI0_Vibration,AI1_Vibration,AI2_Current\n"}, "행"),
])
def test_rejects_bad_requests(console, request_, message):
    with pytest.raises((ValueError, KeyError), match=message):
        console.analyze(request_)


def test_overview_lists_metrics_external_audit(console):
    o = console.overview()
    assert len(o["metrics"]) == 12 and len(o["external"]) == 18
    assert isinstance(o["audit"], dict) and isinstance(o["benchmark"], dict)


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
