"""stage_console.py(두 단계 경보 콘솔) 시험: API 계약, 제출 예측 파일과의 행 일치, 기존 v2 결과 불변, HTTP 경로, 기존 콘솔 파일의 코드 해시 유지.

원본 CSV(press_submission/data, PRESS_DATA_ROOT, 저장소의 데이터셋/ 중 하나)가 있어야 데이터 시험이 돈다. 모델은 press_guard/artifacts에
없으면 동결 사본(outputs/expected)을 임시 폴더에 복사해 쓴다. 제출 예측 파일(준용 tvt)이 없으면 그 대조만 건너뛴다.
"""
import hashlib
import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import serve
import stage_console as SC
from model import D, HERE

TVT = HERE.parents[1] / "claude" / "code" / "press" / "tvt"


def _data_root():
    roots = [D.data_dir(D.PACKAGE_DIR), Path(os.environ["PRESS_DATA_ROOT"]) if os.environ.get("PRESS_DATA_ROOT") else None,
             HERE.parents[1] / "데이터셋"]
    for root in filter(None, roots):
        if not Path(root).is_dir():
            continue
        hits = [p for p in Path(root).rglob("press_data_normal.csv")
                if hashlib.sha256(p.read_bytes()).hexdigest() == D.EXPECTED_SHA256["normal"]]
        if hits and any(Path(root).rglob("outlier_data.csv")):
            return Path(root)
    return None


ROOT = _data_root()


@pytest.fixture(scope="module")
def console(tmp_path_factory):
    if ROOT is None:
        pytest.skip("대회 원본 CSV 없음")
    arts = HERE / "artifacts"
    if not (arts / "guard_A.json").is_file():
        arts = tmp_path_factory.mktemp("artifacts")
        for name in ("guard_A.json", "guard_B.json", "probability_A.json", "probability_B.json"):
            shutil.copy2(HERE / "outputs" / "expected" / name, arts / name)
    return SC.StageConsole(data_root=ROOT, artifacts=arts)


def test_existing_console_files_keep_manifest_hashes():
    """기존 콘솔·모델 파일은 고치지 않는다: v2 실행 기록(outputs/manifest.json)의 코드 해시와 같아야 한다."""
    manifest = json.loads((HERE / "outputs" / "manifest.json").read_text(encoding="utf-8"))
    for name in ("serve.py", "web/index.html", "web/app.js", "web/style.css", "model.py", "runtime.py"):
        assert D.sha256_file(HERE / name) == manifest["code_hashes"][name], name


def test_mixed_b_contract_and_submission_rows(console):
    r = console.analyze({"split": "B", "alpha": .01, "dataset": "mixed"})
    json.dumps(r, allow_nan=False)
    s = r["stats"]
    assert s["v2_mismatch_rows"] == 0                                  # 기존 콘솔(StreamDetector)과 v2 경보가 행마다 같다
    assert r["level_counts"] == {"점검 요청": 1, "주의": 3}
    assert r["stage"]["official_alpha"] == .01 and r["stage"]["event_gap_s"] == 60.0
    inc = pd.DataFrame(r["incidents"])
    l2 = inc[inc.level.eq(2)].iloc[0]
    assert l2.reference_label == 1 and l2.cases == 21 and l2.priority_rank == 1 and l2.escalation_row == l2.first_row
    assert l2.r1_rows > 500 and l2.release_rows == 0                   # 이상 21기록은 R1이 끝까지 이어진다
    l1 = inc[inc.level.eq(1)]
    assert (l1.reference_label == 0).all() and (l1.r2_hold_rows >= 1).all() and (l1.stage2_rows == 0).all()
    assert set(l1.evidence) == {"magnitude"}                            # 정상 1단계 3건은 크기 단독 경보를 R2가 보류한 것
    cases = pd.DataFrame(r["cases"])
    assert set(cases.incident_id) == set(inc.incident_id) and cases.case_uid.is_unique
    pts = pd.DataFrame(r["points"])
    assert {"stage1", "stage2", "inherited1", "released1", "r2_hold", "insufficient", "prefix_r2", "stage_evidence", "incident_id",
            "stage_level", "anomaly_probability", "operating_state"} <= set(pts.columns)
    assert not ((pts.stage2 == 1) & (pts.stage1 == 0)).any()
    assert pts.incident_notification.sum() == len(inc) and pts.incident_escalation.sum() == 1
    path = TVT / "outputs" / "test_predictions_B.csv"
    if not path.is_file():
        pytest.skip("제출 예측 파일 없음")
    pred = pd.read_csv(path)
    n = int(pred.subset.eq("normal").sum())
    abn = pts.iloc[n:]
    rows = {"normal": pts.iloc[:n], "abnormal": abn[(abn.stage_record - abn.stage_record.min()) >= 10]}
    for subset, got in rows.items():
        p = pred[pred.subset.eq(subset)]
        assert len(got) == len(p)
        for mine, theirs in (("stage1", "locked_v2_R1_realtime"), ("stage2", "final_v2_R1_R2_realtime")):
            assert np.array_equal(got[mine].to_numpy() == 1, p[theirs].astype(str).eq("True").to_numpy()), (subset, mine)


def test_base_result_is_not_mutated(console):
    """두 단계 결과를 만들어도 기존 v2 분석 결과(캐시)는 바뀌지 않는다."""
    console.analyze({"split": "B", "alpha": .01, "dataset": "mixed"})
    base = serve.Console.analyze(console, {"split": "B", "alpha": .01, "dataset": "mixed"})
    assert "stage" not in base and "stage1" not in base["points"][0]
    assert base["stats"]["alarm_rows"] == sum(p["alarm"] for p in base["points"])


def test_alpha5_shows_r1_inheritance_and_release(console):
    """비교 α 5%의 B 정상: R1 이어받음·해제가 보이고, 이어받은 경보만으로 켜진 행(R1만)이 있는 2단계 사건이 있다."""
    r = console.analyze({"split": "B", "alpha": .05, "dataset": "normal"})
    inc = pd.DataFrame(r["incidents"])
    assert (inc.release_rows > 0).any() and r["stats"]["r1_release_rows"] > 0
    assert ((inc.level == 2) & (inc.r1_only_rows > 0)).any()
    cases = pd.DataFrame(r["cases"])
    rel = cases[cases.release_row.notna()]
    assert (rel.release_position >= 7).all()                            # 해제는 8행째(파형 판단 가능)부터


def test_upload_matches_builtin(console):
    sp = D.split_normal(console.normal, D.segments(console.normal), "A")
    csv = pd.concat([sp["test"], console.abnormal], ignore_index=True).to_csv(index=False)
    up = console.analyze({"split": "A", "alpha": .01, "dataset": "upload", "csv": csv})
    built = console.analyze({"split": "A", "alpha": .01, "dataset": "mixed"})
    for key in ("stage1_rows", "stage2_rows", "r1_rows", "r2_hold_rows", "stage1_events", "level2_incidents"):
        assert up["stats"][key] == built["stats"][key], key
    assert up["incidents"][0]["reference_label"] is None


def test_http_routes(console):
    server = ThreadingHTTPServer(("127.0.0.1", 0), SC.handler(console))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/", timeout=30).read().decode("utf-8")
        assert "/stage.js" in page and "/stage.css" in page and "두 단계" in page
        for path in ("/stage.js", "/stage.css", "/style.css"):
            assert urllib.request.urlopen(base + path, timeout=30).status == 200
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/app.js", timeout=30)          # 기존 화면 파일은 이 서버가 내지 않는다
        overview = json.loads(urllib.request.urlopen(base + "/api/overview", timeout=120).read())
        assert "stage" in overview and overview["stage"]["official_alpha"] == .01
        req = urllib.request.Request(base + "/api/analyze", data=json.dumps({"split": "B", "alpha": .01, "dataset": "abnormal"}).encode(),
                                     headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=300).read())
        assert res["level_counts"]["점검 요청"] == 1 and res["stats"]["rows"] == 600
    finally:
        server.shutdown()
        server.server_close()
