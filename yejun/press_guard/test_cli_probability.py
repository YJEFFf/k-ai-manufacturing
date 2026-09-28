"""라벨 보정기 없는 모델의 CLI 출력: 결측 확률을 숨기지 않고 경보는 그대로 제공한다."""
import pandas as pd
import pytest

import monitor
import predict
import simulate
from model import D, GuardModel, HERE


@pytest.fixture(scope="module")
def uncalibrated_input(tmp_path_factory):
    dest = tmp_path_factory.mktemp("without_probability")
    model = dest / "site.json"
    GuardModel.load(HERE / "artifacts" / "guard_B.json").save(model)
    _, abnormal, _ = D.load()
    csv = dest / "input.csv"
    D.inputs_only(abnormal.iloc[:100]).to_csv(csv, index=False)
    return model, csv


def test_predict_explains_empty_probability_and_unused_prior(uncalibrated_input, tmp_path, capsys):
    model, csv = uncalibrated_input
    outputs = []
    for prior in (.001, .01):
        path = tmp_path / f"pred_{prior}.csv"
        assert predict.main(["--model", str(model), "--input", str(csv), "--out", str(path), "--prior", str(prior)]) == 0
        message = capsys.readouterr().err
        assert message.count("라벨 확률 보정기가 없어") == 1 and "쓰이지 않습니다" in message
        outputs.append(pd.read_csv(path))
    cols = ["likelihood_ratio", "anomaly_probability", "record_likelihood_ratio", "record_probability"]
    assert all(p[cols].isna().all().all() for p in outputs)
    assert outputs[0].alarm.equals(outputs[1].alarm) and outputs[0].alarm.sum() > 0


@pytest.mark.parametrize("command", ["simulate", "monitor"])
def test_simulate_and_monitor_explain_missing_calibrator(command, uncalibrated_input, capsys):
    model, csv = uncalibrated_input
    args = ["--model", str(model), "--csv", str(csv)]
    if command == "simulate":
        code = simulate.main(args + ["--chunk", "64"])
    else:
        code = monitor.main(args + ["--reference", str(csv)])
    assert code == 0
    message = capsys.readouterr().err
    assert message.count("라벨 확률 보정기가 없어") == 1 and "쓰이지 않습니다" in message
