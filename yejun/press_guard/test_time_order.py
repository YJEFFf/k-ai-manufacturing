"""수집 시각 순서(튄 한 행 건너뛰기·짧은 보류 뒤 새 기준)와 수집 오류 행의 사건 처리. 원본 동률시각과 동결 모델 지표를 보존한다."""
import hashlib

import numpy as np
import pandas as pd
import pytest

import simulate
from model import D, HERE, IncidentTracker, StreamDetector, cases, incidents, layout, load_bundle, time_order_events, timing_warning


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
def test_backdated_records_are_held_briefly_then_analyzed_separately(inputs, chunk):
    """7/14→7/13→7/12의 FP 기록. 기준보다 이른 기록은 앞 2행만 보류하고, 정상 간격으로 3행 이어지면 새 기준으로 판정한다.
    날짜가 거꾸로 간 기록은 서로 다른 사건이고 격상하지 않는다(적대적 검수 X-06: 한 번의 역행이 뒤 자료 전체를 막지 않게 한다)."""
    model, false_alarm, _, _, _ = inputs
    frame = pd.concat([at(false_alarm, day) for day in ("2022-07-14", "2022-07-13", "2022-07-12")], ignore_index=True)
    pred = model.predict(frame)
    held = np.flatnonzero(pred.status.eq("bad_time_order"))
    assert held.tolist() == [50, 51, 100, 101]
    assert pred.status.drop(index=held).eq("ok").all()
    assert pred.score.iloc[held].isna().all() and pred.alarm.iloc[held].sum() == 0
    assert pred.action.iloc[held].eq("수집 상태 확인").all()
    assert pred.position.iloc[52] == 0 and pred.position.iloc[102] == 0
    assert np.flatnonzero(pred.alarm.eq(1)).tolist() == [41, 91, 141]      # 같은 원자료 행이 각 기록에서 경보한다
    assert pred.incident_id.max() == 3 and pred.incident_notification.sum() == 3 and pred.incident_escalation.sum() == 0
    assert incidents(cases(pred), pred).level.tolist() == [1, 1, 1]
    assert time_order_events(pred) == (4, 2, 0)
    assert "역순 수집 시각 4행" in timing_warning(pred) and "2곳" in timing_warning(pred)
    log = simulate.run(frame, model, chunk=chunk)
    assert log[log.notify.eq(1)].kind.tolist() == ["사건 시작", "수집 오류", "사건 시작", "수집 오류", "사건 시작"]
    assert_stream_matches(model, frame, pred, chunk)


@pytest.mark.parametrize("chunk", [1, 7, 128])
def test_reanchor_is_causal_and_chunk_invariant(inputs, chunk):
    """70행 역행 기록 뒤 원래 날짜로 돌아와도 판정은 이어진다. 앞부분 예측은 뒤 자료에 따라 바뀌지 않는다(인과)."""
    model, false_alarm, _, _, _ = inputs
    older = pd.concat([false_alarm, false_alarm.iloc[:20]], ignore_index=True)
    frame = pd.concat([at(false_alarm, "2022-07-14"), at(older, "2022-07-13"),
                       at(false_alarm, "2022-07-14 00:00:06.9")], ignore_index=True)
    pred = model.predict(frame)
    assert np.flatnonzero(pred.status.eq("bad_time_order")).tolist() == [50, 51]
    assert pred.status.iloc[120:].eq("ok").all() and pred.position.iloc[52] == 0 and pred.position.iloc[120] == 0
    assert pred.g_dynamics.iloc[120:122].isna().all() and pred.record_current_rms.iloc[120] == 0
    assert pred.incident_escalation.sum() == 0 and pred.incident_notification.sum() == pred.incident_id.max() == 3
    assert_stream_matches(model, frame, pred, chunk)
    for stop in (1, 49, 50, 51, 52, 57, 119, 120, 121, 141):
        pd.testing.assert_frame_equal(model.predict(frame.iloc[:stop]), pred.iloc[:stop], rtol=1e-11, atol=1e-11)


@pytest.mark.parametrize("where", [0, 100, 350])
def test_single_future_timestamp_does_not_blind_detection(inputs, where):
    """미래 시각(+1시간) 한 행이 이상 자료 앞·중간에 끼어도 21기록을 모두 탐지한다(적대적 검수 X-06: 이전 규칙은 0/21).
    앞선 시간축이 있으면 튄 행만 건너뛴다(보류 0행). 자료의 첫 행이면 이을 시간축이 없어 2행을 보류한다."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    glitch = abnormal.iloc[[where]].copy()
    glitch[D.TIME] = (pd.to_datetime(glitch[D.TIME]) + pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    frame = pd.concat([abnormal.iloc[:where], glitch, abnormal.iloc[where:]], ignore_index=True)
    pred = model.predict(frame)
    body = pred.drop(index=where)
    assert body.status.eq("bad_time_order").sum() == (2 if where == 0 else 0)
    source = np.r_[np.arange(where), np.arange(where, len(abnormal))]
    detected = body.groupby(D.segments(abnormal)[source]).alarm.max()
    assert detected.sum() == 21
    for chunk in (1, 7, 128):
        assert_stream_matches(model, frame, pred, chunk)


def test_clock_set_back_permanently_reanchors(inputs):
    """시계가 1시간 뒤로 재설정되면 2행만 보류하고 새 기준으로 판정을 이어 간다. 경고가 남는다."""
    model, false_alarm, clean, _, _ = inputs
    frame = pd.concat([at(clean, "2022-07-14 01:00:00"), at(false_alarm, "2022-07-14 00:00:00")], ignore_index=True)
    pred = model.predict(frame)
    assert np.flatnonzero(pred.status.eq("bad_time_order")).tolist() == [len(clean), len(clean) + 1]
    assert pred.status.iloc[len(clean) + 2:].eq("ok").all() and pred.alarm.iloc[len(clean):].sum() == 1
    assert "새 기준으로 받아들인 곳 1곳" in timing_warning(pred)


@pytest.mark.parametrize("missing", [5, 22, 60])
def test_missing_rows_do_not_split_incident(inputs, missing):
    """시각 결측 행은 사건을 닫거나 나누지 않는다. 이상 한 번은 사건 1개·알림 2건이다(적대적 검수 C-02: 이전 규칙은 22행 결측에 사건 21개)."""
    _, _, _, _, abnormal = inputs
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    frame = abnormal.copy()
    rows = np.random.default_rng(missing).choice(len(frame), missing, replace=False)
    frame.loc[frame.index[rows], D.TIME] = ""
    pred = model.predict(frame)
    assert pred.status.eq("bad_timestamp").sum() == missing
    assert pred.incident_id.max() == 1 and pred.incident_notification.sum() == 1 and pred.incident_escalation.sum() == 1
    for chunk in (1, 7, 128):
        assert_stream_matches(model, frame, pred, chunk)


def test_two_single_row_alarms_across_invalid_row_escalate(inputs):
    """경보 1행 건 둘 사이에 수집 오류 한 행이 끼어도 같은 사건으로 격상한다."""
    model, false_alarm, _, _, _ = inputs
    first, second = at(false_alarm, "2022-07-14"), at(false_alarm, "2022-07-14 00:00:05.1")
    bad = second.iloc[:1].copy(); bad[D.SENSORS[0]] = np.nan; bad[D.TIME] = "2022-07-14 00:00:05.0"
    frame = pd.concat([first, bad, second], ignore_index=True)
    pred = model.predict(frame)
    assert pred.status.iloc[50] == "bad_value" and pred.alarm.sum() == 2
    assert pred.incident_id.max() == 1 and pred.incident_escalation.sum() == 1
    assert incidents(cases(pred), pred).level.tolist() == [2]


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
    """동결 모델 사본의 SHA-256을 고정하고, 현재 저장 모델이 그 사본과 같은지 본다. 같은 기기면 SHA-256이 같고,
    다른 기기에서 다시 학습했으면 모든 원소가 수치로 같아야 한다(equivalence.py, 리눅스 x86-64 실측 최대 5e-11)."""
    from equivalence import artifact_equivalent
    assert hashlib.sha256((HERE / "outputs" / "expected" / name).read_bytes()).hexdigest() == digest
    ok, why = artifact_equivalent(HERE / "artifacts" / name)
    assert ok, why


def test_reversed_record_is_held_with_warning(inputs):
    """역순으로 들어온 기록은 조용히 1행 기록으로 쪼개지지 않고 보류·경고된다(코드 검토 R1-03: 미래 튐 예외를 연달아 쓰던 문제)."""
    model, false_alarm, clean, _, _ = inputs
    forward = at(clean, "2022-07-14 00:00:00")
    backward = at(clean, "2022-07-14 00:00:10")[::-1].reset_index(drop=True)      # 시각이 거꾸로 가는 50행
    frame = pd.concat([forward, backward], ignore_index=True)
    pred = model.predict(frame)
    tail = pred.iloc[len(forward):]
    assert tail.time_order_event.tolist()[:2] == [0, 2] and tail.status.iloc[2:].eq("bad_time_order").all()
    assert f"역순 수집 시각 {len(backward) - 2}행" in timing_warning(pred)
    for chunk in (1, 7, 128):
        assert_stream_matches(model, frame, pred, chunk)


def test_short_fragments_do_not_bridge_long_gaps(inputs):
    """8행 미만 무경보 조각이 20분 이어져도 그 뒤의 새 이상은 새 사건·새 알림이다(코드 검토 R1-02: 조각이 공백 기준을 옮겨 알림 0건이던 문제)."""
    model, _, clean, _, abnormal = inputs
    first = abnormal[D.segments(abnormal) < 3].reset_index(drop=True)
    last = pd.to_datetime(first[D.TIME].iloc[-1])
    pieces = []
    for k in range(120):                                  # 7행 조각 120개, 조각 사이 10초: 약 20분
        piece = clean.iloc[:7].copy()
        start = last + pd.Timedelta(seconds=10 * (k + 1))
        piece[D.TIME] = (start + pd.to_timedelta(np.arange(7) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
        pieces.append(piece)
    second = abnormal[D.segments(abnormal) < 3].reset_index(drop=True).copy()
    start = last + pd.Timedelta(seconds=10 * 122)
    second[D.TIME] = (start + pd.to_timedelta(np.arange(len(second)) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
    frame = pd.concat([D.inputs_only(first)] + [D.inputs_only(x) for x in pieces] + [D.inputs_only(second)], ignore_index=True)
    pred = model.predict(frame)
    assert pred.iloc[len(first):len(frame) - len(second)].alarm.sum() == 0
    assert pred.incident_id.max() == 2 and pred.incident_notification.sum() == 2 and pred.incident_escalation.sum() == 2
    for chunk in (7, 128):
        assert_stream_matches(model, frame, pred, chunk)


def test_alarmed_spike_row_does_not_split_incident(inputs):
    """경보가 나는 미래 튐 한 행이 진행 중인 이상 사건을 둘로 쪼개지 않는다(코드 검토 R1-04). 튄 행 자체의 판정은 되돌리지 않는다."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    base = model.predict(abnormal)
    spike_src = int(base.index[base.alarm.eq(1) & base.reason.str.contains("magnitude")][0])
    glitch = abnormal.iloc[[spike_src]].copy()
    glitch[D.TIME] = (pd.to_datetime(glitch[D.TIME]) + pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    where = 300
    frame = pd.concat([abnormal.iloc[:where], glitch, abnormal.iloc[where:]], ignore_index=True)
    pred = model.predict(frame)
    assert pred.alarm.iloc[where] == 1 and pred.time_order_event.iloc[where + 1] == 2
    assert pred.incident_id.iloc[where - 1] == pred.incident_id.iloc[where + 1:][pred.alarm.iloc[where + 1:].eq(1)].iloc[0]
    assert pred.incident_escalation.sum() == 1
    for chunk in (1, 7, 128):
        assert_stream_matches(model, frame, pred, chunk)
