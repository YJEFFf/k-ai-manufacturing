"""1단계 정확성 검사: 해시·기록구간·분할·잘못된 행·전처리·산출물 계약."""
import numpy as np
import pandas as pd
import pytest

from press import data as D
from press.artifact import Artifact
from press.diagnosis import format_rules, rule_stats, sine_fit


@pytest.fixture(scope="module")
def frames():
    normal, abnormal, report = D.load(D.PACKAGE_DIR, verify=True)
    return normal, abnormal, report


def test_hashes_and_rows(frames):
    _, _, report = frames
    assert all(v["sha256_ok"] and v["rows_ok"] for v in report["files"].values())


def test_segments_match_vendor_and_counts(frames):
    normal, abnormal, _ = frames
    vendor = D.load_vendor()
    for df, key in ((normal, "normal"), (abnormal, "abnormal")):
        seg = D.segments(df, D.validate_rows(df))
        assert (seg == vendor.blocks(df)).all()
        assert len(np.unique(seg)) == D.EXPECTED_SEGMENTS[key]
        pos, length = D.segment_positions(seg)
        assert pos.min() == 0 and (pos < length).all() and int(length[pos == 0].sum()) == len(df)


def test_split_sizes(frames):
    normal, _, _ = frames
    seg = D.segments(normal)
    expect = {"A": ((11963, 360), (3947, 120), (4090, 120)), "B": ((10133, 300), (3770, 120), (6097, 180))}
    for sid, exp in expect.items():
        sp = D.split_normal(normal, seg, sid)
        got = tuple((len(sp[p]), sp["segments"][p]) for p in ("train", "cal", "test"))
        assert got == exp, (sid, got)


def test_bad_row_becomes_boundary(frames):
    normal, _, _ = frames
    df = normal.head(200).copy()
    seg0 = D.segments(df, D.validate_rows(df))
    # 한 구간의 가운데 행을 망가뜨린다: 타임스탬프 하나, 센서값 하나
    i = int(np.flatnonzero(seg0 == seg0[50])[3])
    df.loc[i, D.TIME] = "not a time"
    df.loc[i + 20, D.SENSORS[0]] = np.nan
    status = D.validate_rows(df)
    assert status[i] == "bad_timestamp" and status[i + 20] == "bad_value" and (status != "ok").sum() == 2
    seg1 = D.segments(df, status)
    assert len(df) == 200                       # 행은 삭제되지 않는다
    assert seg1[i] != seg1[i - 1] and seg1[i + 1] != seg1[i]   # 잘못된 행 앞뒤가 경계
    assert len(np.unique(seg1)) >= len(np.unique(seg0)) + 2


def test_quantize_removes_format_shortcut(frames):
    normal, abnormal, _ = frames
    raw = rule_stats(normal, abnormal).set_index("rule")
    assert raw.loc["current_on_grid", "separability"] > 0.9 and raw.loc["vib_finer_than_1e-6", "separability"] > 0.9
    qn, qa = D.quantize(normal, "matched"), D.quantize(abnormal, "matched")
    m = rule_stats(qn, qa).set_index("rule")
    assert m.loc["current_on_grid", "separability"] < 0.55 and m.loc["vib_finer_than_1e-6", "separability"] < 0.55
    assert D.quantize(normal, "raw").equals(normal)


def test_inputs_only_and_no_label(frames):
    normal, _, _ = frames
    x = D.inputs_only(normal)
    assert x.columns.tolist() == [D.TIME] + D.SENSORS


def test_sine_fit_recovers_clean_sine():
    t = np.arange(50) * D.DT
    x = 3 * np.sin(2 * np.pi * 0.6 * t + 0.4) + 1.0
    f, r2, fit = sine_fit(x)
    assert abs(f - 0.6) < 1e-9 and r2 > 0.999999
    assert np.isnan(sine_fit(np.ones(20))[1])   # SST=0 → NaN


def test_artifact_roundtrip(tmp_path):
    a = Artifact(model_id="m", split="A", preprocess="matched", w=8, input_sha256={"normal": "x"}, state={"u": 1.5})
    p = a.save(tmp_path / "a.json")
    b = Artifact.load(p)
    assert b.trained and b.state["u"] == 1.5 and b.protocol_version == D.PROTOCOL_VERSION
