"""역순 수집시각의 인과적 판정보류·회복·사건 분리. 원본 동률시각과 동결 모델 지표를 보존한다."""
import hashlib

import numpy as np
import pandas as pd
import pytest

import simulate
from model import D, HERE, IncidentTracker, StreamDetector, cases, incidents, layout, load_bundle, timing_warning


@pytest.fixture(scope="module")
def inputs():
    normal, abnormal, _ = D.load()
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    split = D.split_normal(normal, D.segments(normal), "B")
    frame = D.inputs_only(split["test"]).reset_index(drop=True)
    record = layout(frame)[1]
    return model, frame[record == 3].reset_index(drop=True), frame[record == 0].reset_index(drop=True), normal, abnormal


def at(frame, start):
    out = frame.copy().reset_index(drop=True)
    out[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(out)) * .1, unit="s")).astype(str)
    return out


def assert_stream_matches(model, frame, expected, chunk):
    detector = StreamDetector(model)
    parts = []
    for i in range(0, len(frame), chunk):
        parts.append(detector.push(frame.iloc[i:i + chunk]))
        assert len(detector.tail) <= 7
    actual = pd.concat(parts, ignore_index=True)
    pd.testing.assert_frame_equal(actual, expected, rtol=1e-11, atol=1e-11)


@pytest.mark.parametrize("chunk", [1, 7, 128])
def test_backdated_records_do_not_merge_or_escalate(inputs, chunk):
    """평가관 반례: 7/14→7/13→7/12의 FP 기록. 과거 100행은 오류로 보류하고 첫 사건을 격상하지 않는다."""
    model, false_alarm, _, _, _ = inputs
    frame = pd.concat([at(false_alarm, day) for day in ("2022-07-14", "2022-07-13", "2022-07-12")], ignore_index=True)
    pred = model.predict(frame)
    assert pred.status.iloc[:50].eq("ok").all()
    assert pred.status.iloc[50:].eq("bad_time_order").all()
    assert pred.score.iloc[50:].isna().all() and pred.alarm.iloc[50:].sum() == 0
    assert pred.action.iloc[50:].eq("수집 상태 확인").all()
    assert pred.incident_notification.sum() == 1 and pred.incident_escalation.sum() == 0
    queue = cases(pred)
    assert queue.level.tolist() == [1] and queue.suspect_to.tolist() == [""]
    assert incidents(queue, pred).level.tolist() == [1]
    assert "역순 수집 시각 100행" in timing_warning(pred)
    log = simulate.run(frame, model, chunk=chunk)
    assert log[log.notify.eq(1)].kind.tolist() == ["사건 시작", "수집 오류"]
    assert_stream_matches(model, frame, pred, chunk)


@pytest.mark.parametrize("chunk", [1, 7, 128])
def test_recovery_after_long_reversal_starts_new_record_and_incident(inputs, chunk):
    """tail 7행보다 긴 역행 뒤 기준 시각을 넘으면 새 기록·새 사건에서 다시 판정한다."""
    model, false_alarm, _, _, _ = inputs
    older = pd.concat([false_alarm, false_alarm.iloc[:20]], ignore_index=True)
    frame = pd.concat([at(false_alarm, "2022-07-14"), at(older, "2022-07-13"),
                       at(false_alarm, "2022-07-14 00:00:06.9")], ignore_index=True)
    pred = model.predict(frame)
    assert pred.status.eq("bad_time_order").sum() == 70
    assert pred.status.iloc[120:].eq("ok").all() and pred.position.iloc[120] == 0
    assert pred.g_dynamics.iloc[120:122].isna().all() and pred.record_current_rms.iloc[120] == 0
    assert pred.incident_notification.sum() == 2 and pred.incident_escalation.sum() == 0
    assert incidents(cases(pred), pred).level.tolist() == [1, 1]
    events = simulate.run(frame, model, chunk=chunk)
    assert events[events.notify.eq(1)].kind.tolist() == ["사건 시작", "수집 오류", "사건 시작"]
    assert_stream_matches(model, frame, pred, chunk)
    for stop in (1, 49, 50, 51, 57, 119, 120, 121, 141):
        pd.testing.assert_frame_equal(model.predict(frame.iloc[:stop]), pred.iloc[:stop], rtol=1e-11, atol=1e-11)


def test_nan_timestamp_does_not_erase_order_or_change_equal_time_policy(inputs):
    model, false_alarm, _, _, _ = inputs
    frame = at(false_alarm.iloc[:6], "2022-07-14")
    frame[D.TIME] = ["2022-07-14 00:00:01", "bad", "2022-07-13", "2022-07-14 00:00:01",
                     "2022-07-14 00:00:01", "2022-07-14 00:00:01.1"]
    pred = model.predict(frame)
    assert pred.status.tolist() == ["ok", "bad_timestamp", "bad_time_order", "ok", "ok", "ok"]
    assert pred.position.tolist() == [0, 0, 0, 0, 0, 1]
    for chunk in (1, 7, 128):
        assert_stream_matches(model, frame, pred, chunk)


@pytest.mark.parametrize("gap, merged", [(-1, False), (0, True), (60, True), (60.1, False)])
def test_incident_gap_requires_nonnegative_elapsed_time(gap, merged):
    tracker = IncidentTracker()
    start = pd.Timestamp("2022-07-14", tz="UTC")
    assert tracker.update(0, 0, True, "magnitude", start)[:3] == (1, 1, 0)
    result = tracker.update(1, 0, True, "magnitude", start + pd.Timedelta(seconds=gap))
    assert result[:3] == ((1, 0, 1) if merged else (2, 1, 0))


def test_reverse_quality_bounds_are_open_even_for_precomputed_predictions(inputs):
    """예전 예측 파일처럼 status가 ok여도 역순 시간창을 닫거나 음수 소요시간으로 내보내지 않는다."""
    model, false_alarm, clean, _, _ = inputs
    parts = [at(clean, "2022-07-14"), at(false_alarm, "2022-07-14 00:00:10"), at(clean, "2022-07-14 00:00:20")]
    pred = model.predict(pd.concat(parts, ignore_index=True))
    assert len(cases(pred)) == 1
    for record, date in enumerate(("2022-07-14", "2022-07-13", "2022-07-12")):
        mask = pred.record_id.eq(record)
        pred.loc[mask, "timestamp"] = (pd.Timestamp(date) + pd.to_timedelta(np.arange(mask.sum()) * .1, unit="s")).astype(str)
    case = cases(pred).iloc[0]
    assert case.suspect_from == case.suspect_to == "" and case.suspect_open == 1
    assert pd.isna(case.suspect_seconds)


def test_original_duplicate_timestamp_and_main_metrics_are_preserved(inputs):
    _, _, _, normal, abnormal = inputs
    status, records = layout(normal)
    assert (status == "ok").all() and len(np.unique(records)) == 600
    np.testing.assert_array_equal(records, D.segments(normal))
    original_time = pd.to_datetime(normal[D.TIME], format="mixed", utc=True)
    assert original_time.diff().dt.total_seconds().eq(0).sum() == 1
    for split, fn, fp, expected_f1, normal_units in (("A", 44, 0, .961938, 120), ("B", 31, 3, .970990, 180)):
        model = load_bundle(HERE / "artifacts" / f"guard_{split}.json")
        sp = D.split_normal(normal, D.segments(normal), split)
        pn, pa = model.predict(sp["test"]), model.predict(abnormal)
        assert pn.status.eq("ok").all() and pa.status.eq("ok").all()
        assert pn.alarm.sum() == fp and pa.alarm.eq(0).sum() == fn
        assert pn.record_id.nunique() == normal_units and pn.notification.sum() == fp
        assert pa.notification.sum() == 21 and pa.record_id.nunique() == 21
        tp = int(pa.alarm.sum())
        assert round(2 * tp / (2 * tp + fp + fn), 6) == expected_f1


@pytest.mark.parametrize("name,digest", [
    ("guard_A.json", "c938707f1dd16e7c239b8053e7f032d8fac828d6c753de2b898ba9130a594f10"),
    ("guard_B.json", "b64ac3b30bc697034104287964f3154e88c8a50749ccdec04f6d4f8744fd6969"),
    ("probability_A.json", "1a8100e78046393d9292fc7c305b5ec57b46c4e2c73b03abeb596052a8705f8a"),
    ("probability_B.json", "7fde4cd1bdfa74e78e2d3f07c5dbd9c27619e19b2e94ceb8fab786c27abcaae8"),
])
def test_frozen_artifacts_are_unchanged(name, digest):
    assert hashlib.sha256((HERE / "artifacts" / name).read_bytes()).hexdigest() == digest
