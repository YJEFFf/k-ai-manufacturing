"""행 순서 교환·문자열 변조·기대 요약 변조가 허용오차 경로를 우회하지 못한다."""
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from model import D, HERE
import verify


@pytest.mark.parametrize("column", ["incident_id", "incident_notification", "incident_escalation", "magnitude_sensor", "timestamp", "operating_state"])
def test_exact_columns_detect_order_changes(tmp_path, monkeypatch, column):
    original = pd.DataFrame(dict(alarm=[1, 1], incident_id=[1, 2], incident_notification=[1, 0],
                                 incident_escalation=[0, 1], magnitude_sensor=["AI0", "AI1"],
                                 timestamp=["2022-01-01", "2022-01-02"], operating_state=["load", "low"], score=[1.1, 2.2]))
    filename = "pred.csv"
    original.to_csv(tmp_path / filename, index=False)
    exp = tmp_path / "expected"; exp.mkdir()
    (exp / verify.DIGEST).write_text(json.dumps({filename: verify.prediction_digest(tmp_path / filename)}), encoding="utf-8")
    monkeypatch.setattr(verify, "PREDICTIONS", (filename,))
    assert verify.compare_predictions(tmp_path, exp)[0]["ok"]
    original[column] = original[column].iloc[::-1].to_numpy()  # 수치 열도 합·제곱합 등은 그대로다
    original.to_csv(tmp_path / filename, index=False)
    assert not verify.compare_predictions(tmp_path, exp)[0]["ok"]


def test_expected_digest_hash_is_checked(tmp_path):
    exp = tmp_path / "expected"
    shutil.copytree(HERE / "outputs" / "expected", exp)
    manifest = json.loads((exp / "manifest.json").read_text(encoding="utf-8"))
    manifest["prediction_digest_sha256"] = D.sha256_file(exp / verify.DIGEST)
    (exp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert verify.expected_integrity(exp) == []
    data = json.loads((exp / verify.DIGEST).read_text(encoding="utf-8"))
    data[next(iter(data))]["rows"] += 1
    (exp / verify.DIGEST).write_text(json.dumps(data), encoding="utf-8")
    assert any(verify.DIGEST in err for err in verify.expected_integrity(exp))


@pytest.mark.parametrize("mutation", ["positive_inf", "negative_inf", "move_nan"])
def test_nonfinite_kind_and_position_cannot_use_float_tolerance(tmp_path, monkeypatch, mutation):
    original = pd.DataFrame(dict(alarm=[0, 0, 1], score=[np.nan, 1.2, 3.4]))
    filename = "pred.csv"
    original.to_csv(tmp_path / filename, index=False)
    exp = tmp_path / "expected"; exp.mkdir()
    (exp / verify.DIGEST).write_text(json.dumps({filename: verify.prediction_digest(tmp_path / filename)}), encoding="utf-8")
    monkeypatch.setattr(verify, "PREDICTIONS", (filename,))
    changed = original.copy()
    if mutation == "move_nan":
        changed["score"] = [1.2, np.nan, 3.4]
    else:
        changed.loc[0, "score"] = np.inf if mutation == "positive_inf" else -np.inf
    changed.to_csv(tmp_path / filename, index=False)
    assert not verify.compare_predictions(tmp_path, exp)[0]["ok"]
    original.loc[1, "score"] += 1e-11  # 정상적인 기기 간 반올림 차이는 여전히 허용한다.
    original.to_csv(tmp_path / filename, index=False)
    assert verify.compare_predictions(tmp_path, exp)[0]["ok"]
