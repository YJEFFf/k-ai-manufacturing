"""수집 시각 순서(튄 한 행 건너뛰기·짧은 보류 뒤 새 기준)와 수집 오류 행의 사건 처리. 원본 동률시각과 동결 모델 지표를 보존한다."""
import hashlib

import numpy as np
import pandas as pd
import pytest

import simulate
from model import D, HERE, IncidentTracker, incident_columns, StreamDetector, cases, incidents, layout, load_bundle, time_order_events, timing_warning


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
    """역순으로 들어온 기록은 조용히 1행 기록으로 쪼개지지 않고 보류·경고된다(코드 검토 R1-03: 미래 튐 예외를 연달아 쓰던 문제).
    역순 기록의 첫 행(가장 늦은 시각)만 받아들이고 나머지는 모두 보류한다. 둘째 행은 튀기 전 기준의 다음 표본이 아니므로
    튐 예외가 아니다(검토 3 R3-03)."""
    model, false_alarm, clean, _, _ = inputs
    forward = at(clean, "2022-07-14 00:00:00")
    backward = at(clean, "2022-07-14 00:00:10")[::-1].reset_index(drop=True)      # 시각이 거꾸로 가는 50행
    frame = pd.concat([forward, backward], ignore_index=True)
    pred = model.predict(frame)
    tail = pred.iloc[len(forward):]
    assert tail.time_order_event.tolist()[:2] == [0, 1] and tail.status.iloc[1:].eq("bad_time_order").all()
    assert f"역순 수집 시각 {len(backward) - 1}행" in timing_warning(pred)
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


def stamp(frame, times):
    out = D.inputs_only(frame).copy().reset_index(drop=True)
    out[D.TIME] = [pd.Timestamp(t).strftime("%Y-%m-%d %H:%M:%S.%f") if t is not None else "" for t in times]
    return out


def magnitude_rows(model, abnormal, k):
    """1행 기록(크기 성분만)으로도 경보가 나는 이상 행 k개."""
    base = pd.Timestamp("2022-07-17 10:00:00")
    probe = model.predict(stamp(abnormal, [base + pd.Timedelta(seconds=10 * i) for i in range(len(abnormal))]))
    return D.inputs_only(abnormal).iloc[np.flatnonzero(probe.alarm.eq(1).to_numpy())[:k]].reset_index(drop=True)


def per_incident(pred):
    return pred[pred.incident_id.gt(0)].groupby("incident_id")[["incident_notification", "incident_escalation"]].sum()


@pytest.mark.parametrize("offsets", [(0, .2, .1, .3), (0, 5, .1, .2), (0, .25, .2, .3)], ids=["swap", "jump5s", "late150ms"])
def test_undo_does_not_repeat_escalation(inputs, offsets):
    """진행 중 사건 안에서 두 행이 맞바뀌거나 한 행이 튀거나 늦게 찍혀도 사건마다 시작·격상 알림은 한 번이다(검토 3 R3-01)."""
    model, _, clean, _, abnormal = inputs
    mag = magnitude_rows(model, abnormal, 4)
    start = pd.Timestamp("2022-07-14 00:00:07")
    frame = pd.concat([at(clean, "2022-07-14"), stamp(mag, [start + pd.Timedelta(seconds=o) for o in offsets])], ignore_index=True)
    pred = model.predict(frame)
    counts = per_incident(pred)
    assert len(counts) == 1 and counts.incident_notification.tolist() == [1] and counts.incident_escalation.tolist() == [1]
    assert incidents(cases(pred), pred).escalation_row.tolist() == pred.row_id[pred.incident_escalation.eq(1)].tolist()
    for chunk in (1, 7, 128):
        assert_stream_matches(model, frame, pred, chunk)
    log = simulate.run(frame, model, chunk=1)
    alerts = log[log.kind.isin(["사건 시작", "격상"])]                               # 보류 행의 '수집 오류' 알림은 따로 센다
    assert alerts.groupby("incident_id").kind.apply(list).tolist() == [["사건 시작", "격상"]]


@pytest.mark.parametrize("extra", ["nat", "held"])
def test_invalid_row_between_spike_and_timeline_still_undoes(inputs, extra):
    """튄 행과 원래 시간축 사이에 시각 결측·보류 행이 끼어도 진행 중인 사건이 쪼개지지 않는다(검토 3 R3-02)."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    base = model.predict(abnormal)
    src = int(base.index[base.alarm.eq(1) & base.reason.str.contains("magnitude")][0])
    glitch = abnormal.iloc[[src]].copy()
    glitch[D.TIME] = (pd.to_datetime(glitch[D.TIME]) + pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    between = abnormal.iloc[[300]].copy()
    between[D.TIME] = "" if extra == "nat" else (pd.to_datetime(between[D.TIME]) - pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    control = model.predict(pd.concat([abnormal.iloc[:300], glitch, abnormal.iloc[300:]], ignore_index=True))
    frame = pd.concat([abnormal.iloc[:300], glitch, between, abnormal.iloc[300:]], ignore_index=True)
    pred = model.predict(frame)
    assert pred.time_order_event.iloc[302] == 2 and pred.status.iloc[301] != "ok"
    assert pred.incident_id.iloc[299] == pred.incident_id.iloc[302:][pred.alarm.iloc[302:].eq(1)].iloc[0]
    assert (pred.incident_notification.sum(), pred.incident_escalation.sum()) == (control.incident_notification.sum(), control.incident_escalation.sum()) == (2, 1)
    for chunk in (7, 128):
        assert_stream_matches(model, frame, pred, chunk)


@pytest.mark.parametrize("late", [6.0, 4.9], ids=["past_row_in_gap", "resent_last_row"])
def test_past_row_after_record_start_is_held(inputs, late):
    """기록 첫 행 바로 뒤에 기록 사이 공백 안의 과거 행(또는 앞 기록 마지막 행의 재전송)이 와도 첫 행을 튄 행으로 보지 않는다.
    과거 행만 보류하고 이상 한 번은 사건 1개·시작 알림 1건이다(검토 3 R3-03)."""
    model, _, clean, _, abnormal = inputs
    mag = magnitude_rows(model, abnormal, 6)
    t0, start = pd.Timestamp("2022-07-14"), pd.Timestamp("2022-07-14 00:00:07")
    frame = pd.concat([at(clean, t0), stamp(mag.iloc[:1], [start]), stamp(clean.iloc[[10]], [t0 + pd.Timedelta(seconds=late)]),
                       stamp(mag.iloc[1:], [start + pd.Timedelta(seconds=.1 * i) for i in range(1, len(mag))])], ignore_index=True)
    pred = model.predict(frame)
    row = len(clean) + 1
    assert pred.status.iloc[row] == "bad_time_order" and pred.time_order_event.tolist().count(2) == 0
    assert pred.incident_notification.sum() == 1 and pred.incident_id.max() == 1
    for chunk in (1, 7, 128):
        assert_stream_matches(model, frame, pred, chunk)


@pytest.mark.parametrize("where", ["after", "before"])
def test_spike_row_is_not_a_quality_window_bound(inputs, where):
    """경보 없는 +1시간 튄 행이 경보 기록 바로 앞·뒤(기록 경계)에 와도 품질 의심 시간창이 열리지 않는다(검토 3 R3-06).
    튄 행 바로 뒤가 새 기록이면 그 기록의 앞 2행을 보류한 뒤 새 기준을 잡고, 새 시간축이 튀기 전 기준보다 뒤라 튄 행으로 확인한다
    (ORDER_SPIKE_REANCHOR). 창의 경계는 튐이 없을 때와 같거나(앞), 보류 2행만큼 늦다(뒤)."""
    model, false_alarm, clean, _, _ = inputs
    t0 = pd.Timestamp("2022-07-14")
    before, alarmed, after = at(clean, t0), at(false_alarm, t0 + pd.Timedelta(seconds=6)), at(clean, t0 + pd.Timedelta(seconds=13))
    spike = stamp(clean.iloc[[5]], [t0 + pd.Timedelta(hours=1)])
    plain = cases(model.predict(pd.concat([before, alarmed, after], ignore_index=True)))
    parts = [before, alarmed, spike, after] if where == "after" else [before, spike, alarmed, after]
    frame = pd.concat(parts, ignore_index=True)
    pred = model.predict(frame)
    assert pred.time_order_event.tolist().count(4) == 1 and pred.status.eq("bad_time_order").sum() == 2
    got = cases(pred)
    assert got.suspect_open.tolist() == plain.suspect_open.tolist() == [0]
    assert got.suspect_from.tolist() == plain.suspect_from.tolist()
    late = (pd.Timestamp(got.suspect_to.iloc[0]) - pd.Timestamp(plain.suspect_to.iloc[0])).total_seconds()
    assert late == (.2 if where == "after" else 0)
    for chunk in (7, 128):
        assert_stream_matches(model, frame, pred, chunk)


@pytest.mark.parametrize("seconds", [.5, 5, 30, 3600])
@pytest.mark.parametrize("mode", ["replace", "insert"])
def test_single_sample_timestamp_error_keeps_timeline(inputs, seconds, mode):
    """기록 안의 한 표본 시각이 앞으로 틀리면(표본을 대신하거나 끼어듦) 보류 없이 원래 시간축으로 잇고 이상 한 번은 사건 하나다
    (검토 5 R5-01: '다음 표본'만 인정하던 규칙은 표본을 대신한 튐에서 2행을 보류하고 사건을 나눴다)."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    frame = D.inputs_only(abnormal).reset_index(drop=True)
    t = pd.to_datetime(frame[D.TIME])
    i = 305                                               # 기록 11(280~329) 안
    wrong = (t[i] + pd.Timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S.%f")
    if mode == "replace":
        frame.loc[i, D.TIME] = wrong
    else:
        extra = frame.iloc[[i]].copy(); extra[D.TIME] = wrong
        frame = pd.concat([frame.iloc[:i + 1], extra, frame.iloc[i + 1:]], ignore_index=True)
    pred = model.predict(frame)
    assert pred.status.eq("bad_time_order").sum() == 0 and pred.time_order_event.tolist().count(2) == 1
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (1, 1, 1)
    assert_stream_matches(model, frame, pred, 7)


def test_record_end_spike_does_not_split_incident(inputs):
    """기록 끝 표본의 시각이 튀면 다음 기록의 앞 2행을 보류하고, 새 기준을 잡을 때 튄 행을 확인해 사건 효과를 되돌린다."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    frame = D.inputs_only(abnormal).reset_index(drop=True)
    t = pd.to_datetime(frame[D.TIME])
    frame.loc[329, D.TIME] = (t[329] + pd.Timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S.%f")   # 기록 11의 마지막 행
    pred = model.predict(frame)
    assert pred.status.eq("bad_time_order").sum() == 2 and pred.time_order_event.tolist().count(4) == 1
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (1, 1, 1)
    for chunk in (1, 7):
        assert_stream_matches(model, frame, pred, chunk)


@pytest.mark.parametrize("pause", [61, 600])
def test_stale_row_after_long_pause_is_held(inputs, pause):
    """60초 넘는 수집 중단 뒤 새 기록이 시작된 다음 공백 안의 과거 행이 와도 그 행만 보류한다(검토 5: R3-03이 긴 중단 뒤에 남았다)."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    frame = D.inputs_only(abnormal).reset_index(drop=True)
    t = pd.to_datetime(frame[D.TIME])
    moved = t + pd.to_timedelta(np.where(np.arange(len(frame)) >= 330, pause, 0.0), unit="s")
    frame[D.TIME] = moved.dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    stale = frame.iloc[[330]].copy(); stale[D.TIME] = (t[329] + pd.Timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S.%f")   # 공백 안 10초 지점
    base = model.predict(frame)
    pred = model.predict(pd.concat([frame.iloc[:331], stale, frame.iloc[331:]], ignore_index=True))
    assert pred.status.iloc[331] == "bad_time_order" and pred.status.eq("bad_time_order").sum() == 1
    assert not pred.time_order_event.isin([2, 4]).any()
    assert (pred.incident_notification.sum(), pred.incident_escalation.sum()) == (base.incident_notification.sum(), base.incident_escalation.sum())


def test_sine_projections_are_computed_once(monkeypatch):
    """사인 투영(주파수 1,001개 pinv)은 창 길이마다 한 번만 계산한다(검토 3 R3-04: setdefault가 매번 다시 계산하던 문제)."""
    import model as M
    calls = []
    monkeypatch.setattr(M, "_HATS", {})
    original = M.stable_hats
    monkeypatch.setattr(M, "stable_hats", lambda win: calls.append(win) or original(win))
    x, seg = np.cos(np.arange(40) * .377), np.zeros(40, int)
    first = M.sine_score(x, seg, 8)
    for _ in range(3):
        np.testing.assert_array_equal(M.sine_score(x, seg, 8), first)
    M.sine_score(x, seg, 6)
    assert calls == [8, 6]


def test_random_time_faults_keep_one_start_and_escalation_per_incident(inputs):
    """무작위 시각 오류(맞바뀜·작은 앞 튐·1시간 튐·1시간 뒤로·시각 결측)에도 사건마다 시작·격상 알림은 한 번 이하다.
    80회 가운데 앞 4회는 스트림(청크 7·128)과 일괄 결과도 대조한다. 110afa2 규칙은 이 80회 중 2회에서 격상이 중복됐다(검토 3 R3-01)."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    rng = np.random.default_rng(20260929)
    base = D.inputs_only(abnormal).reset_index(drop=True)
    times = pd.to_datetime(base[D.TIME])
    for trial in range(80):
        t = times.copy()
        for _ in range(6):
            i = int(rng.integers(1, len(base) - 2))
            kind = rng.choice(["swap", "jump", "spike", "back", "swap"])
            if kind == "swap":
                t.iloc[[i, i + 1]] = t.iloc[[i + 1, i]].to_numpy()
            elif kind == "jump":
                t.iloc[i] += pd.Timedelta(seconds=float(rng.choice([.2, .3, 2, 5, 30])))
            elif kind == "spike":
                t.iloc[i] += pd.Timedelta(hours=1)
            else:
                t.iloc[i] -= pd.Timedelta(hours=1)
        stamps = t.dt.strftime("%Y-%m-%d %H:%M:%S.%f").tolist()
        for i in rng.choice(len(base), 3, replace=False):
            if rng.random() < .5:
                stamps[i] = ""
        frame = base.copy()
        frame[D.TIME] = stamps
        pred = model.predict(frame)
        counts = per_incident(pred)
        assert (counts <= 1).all().all(), (trial, counts[(counts > 1).any(axis=1)])
        if trial < 4:
            assert_stream_matches(model, frame, pred, 128 if trial % 2 else 7)


def test_random_single_timestamp_spikes_do_not_split_the_episode(inputs):
    """한 표본의 시각만 앞으로 틀리는 오류(0.3초~1시간, 표본 대체·끼어듦, 기록 안·끝)를 무작위로 넣어도 이상 한 번의 경보 행은
    모두 한 사건에 남는다(튄 행 자체의 경보만 예외). 검토 5 R5-01: 3c6fbf3 규칙은 80곳 중 24~28곳에서 사건을 나눴다."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, _, abnormal = inputs
    rng = np.random.default_rng(20260930)
    base = D.inputs_only(abnormal).reset_index(drop=True)
    times = pd.to_datetime(base[D.TIME])
    for trial in range(40):
        stamps = times.dt.strftime("%Y-%m-%d %H:%M:%S.%f").tolist()
        rows, spikes = list(range(len(base))), set()
        for pos in sorted(rng.choice(np.arange(60, 580, 60), 3, replace=False) + rng.integers(0, 50, 3)):
            wrong = (times[pos] + pd.Timedelta(seconds=float(rng.choice([.3, 2, 5, 30, 3600])))).strftime("%Y-%m-%d %H:%M:%S.%f")
            if rng.random() < .5:
                stamps[pos] = wrong
                spikes.add(pos)
            else:
                rows.append(pos); stamps.append(wrong); spikes.add(len(stamps) - 1)
        order = sorted(range(len(rows)), key=lambda k: (rows[k], k >= len(base)))      # 끼어든 행은 원래 행 바로 뒤
        frame = base.iloc[[rows[k] for k in order]].reset_index(drop=True)
        frame[D.TIME] = [stamps[k] for k in order]
        is_spike = np.isin(order, list(spikes))
        pred = model.predict(frame)
        alarms = pred[pred.alarm.eq(1).to_numpy() & ~is_spike]
        assert alarms.incident_id.nunique() == 1, (trial, alarms.incident_id.value_counts().to_dict())
        assert (per_incident(pred) <= 1).all().all(), trial
        if trial < 2:
            assert_stream_matches(model, frame, pred, 7)


def _chain(parts, start, gap=3.0):
    """부분마다 0.1초 간격, 부분 사이 gap초 공백의 시각을 붙인다."""
    frames, times, t = [], [], pd.Timestamp(start)
    for part in parts:
        n = len(part)
        times += list(t + pd.to_timedelta(np.arange(n) * .1, unit="s"))
        t = times[-1] + pd.Timedelta(seconds=gap)
        frames.append(D.inputs_only(part))
    frame = pd.concat(frames, ignore_index=True)
    frame[D.TIME] = pd.Series(times).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    return frame


def _fault(frame, row, kind):
    f = frame.copy()
    t = pd.to_datetime(f[D.TIME])
    if kind == "nat":
        f.loc[row, D.TIME] = ""
    elif kind == "sensor":
        f.loc[row, D.SENSORS[0]] = np.nan
    else:
        f.loc[row, D.TIME] = (t[row] + pd.Timedelta(seconds=kind)).strftime("%Y-%m-%d %H:%M:%S.%f")
    return f


@pytest.fixture(scope="module")
def weak_parts(inputs):
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    _, _, _, normal, abnormal = inputs
    seg = D.segments(abnormal)
    test = D.inputs_only(D.split_normal(normal, D.segments(normal), "B")["test"]).reset_index(drop=True)
    pred = model.predict(test)
    rec = pred.record_id.to_numpy()
    quiet = [r for r in np.unique(rec) if pred.alarm[rec == r].sum() == 0 and (rec == r).sum() >= 30]
    return model, [abnormal[seg == k].reset_index(drop=True) for k in (11, 12, 13)], [test[rec == q].reset_index(drop=True) for q in quiet[:2]]


@pytest.mark.xfail(strict=True, reason="알려진 한계(검토 7 R7-01): 사건 단위가 건 대기열과 같은 (기록구간, 50행 블록)이라 오류 한 행이 기록을 자르면 사건이 나뉘거나 합쳐진다. 기록과 따로 정한 4~6차 규칙은 회귀(검토 8~10) 때문에 되돌렸다")
@pytest.mark.parametrize("kind", ["nat", "sensor", .03, 5])
def test_error_row_inside_record_does_not_split_incident(weak_parts, kind):
    """경보 없는 앞 조각(10행) 뒤에 이상이 이어지는 기록에서, 첫 이상 행의 오류 한 행(시각·센서 결측, 30 ms 흔들림, +5초 튐)이
    기록을 잘라도 사건은 하나다(검토 7 R7-01: 잘린 무경보 조각이 사건을 닫아 사건 둘·알림 넷이 됐다)."""
    model, (r11, r12, r13), (quiet, _) = weak_parts
    middle = pd.concat([D.inputs_only(quiet.iloc[:10]), D.inputs_only(r12)], ignore_index=True)
    frame = _chain([r11, middle, r13], "2022-07-21")
    base = model.predict(frame)
    assert (base.incident_id.max(), base.incident_notification.sum(), base.incident_escalation.sum()) == (1, 1, 1)
    pred = model.predict(_fault(frame, len(r11) + 10, kind))
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (1, 1, 1)
    assert_stream_matches(model, _fault(frame, len(r11) + 10, kind), pred, 7)


@pytest.mark.xfail(strict=True, reason="알려진 한계(검토 7 R7-01): 사건 단위가 건 대기열과 같은 (기록구간, 50행 블록)이라 오류 한 행이 기록을 자르면 사건이 나뉘거나 합쳐진다. 기록과 따로 정한 4~6차 규칙은 회귀(검토 8~10) 때문에 되돌렸다")
@pytest.mark.parametrize("kind", ["nat", "sensor", .03, 5])
def test_error_row_inside_short_normal_record_keeps_second_alert(weak_parts, kind):
    """두 이상 사이 정상 기록(14행) 가운데의 오류 한 행이 기록을 8행 미만 조각 둘로 잘라도 정상 복귀(유효 8행 이상)로 보고
    둘째 이상에 시작·격상 알림을 낸다(검토 7 R7-01: 두 이상이 한 사건으로 합쳐져 둘째 알림이 없었다)."""
    model, (r11, r12, _), (_, quiet) = weak_parts
    frame = _chain([r11, quiet.iloc[:14], r12], "2022-07-22")
    base = model.predict(frame)
    assert (base.incident_id.max(), base.incident_notification.sum(), base.incident_escalation.sum()) == (2, 2, 2)
    pred = model.predict(_fault(frame, len(r11) + 7, kind))
    second = pred.iloc[len(r11) + 14:]
    assert pred.incident_id.max() == 2 and (second.incident_notification.sum(), second.incident_escalation.sum()) == (1, 1)
    assert_stream_matches(model, _fault(frame, len(r11) + 7, kind), pred, 7)


@pytest.mark.parametrize("late", [2.55, 2.7, 2.95])
def test_late_stamped_record_end_does_not_merge_incidents(weak_parts, late):
    """이상 기록 끝 행이 늦게 찍혀 다음 정상 기록 앞 0.05~0.45초에 붙어도 두 이상은 따로 사건이다(간격이 도착한 행 수로 설명되지 않아
    그 행은 따로 단위). 사건 단위를 수집 공백 0.5초로만 나눈 4차 초안에서는 그 행의 경보가 정상 기록 전체를 경보 단위로 만들어 두 이상이 합쳐졌다."""
    model, (r11, r12, _), (_, quiet) = weak_parts
    frame = _chain([r11, quiet.iloc[:14], r12], "2022-07-22")
    f = _fault(frame, len(r11) - 1, late)
    pred = model.predict(f)
    assert pred.alarm.iloc[len(r11) - 1] == 1
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (2, 2, 2)
    for chunk in (1, 7):
        assert_stream_matches(model, f, pred, chunk)


@pytest.mark.parametrize("early", [2.55, 2.7, 2.95])
def test_early_stamped_record_start_does_not_merge_incidents(inputs, weak_parts, early):
    """이상 기록 첫 행(1행으로도 경보가 나는 행)이 이르게 찍혀 앞 정상 기록 끝 0.05~0.45초 뒤에 붙어도 두 이상은 따로 사건이고 둘째 이상에
    시작·격상 알림이 한 번씩 나간다(붙은 행은 따로 단위라 정상 기록이 정상 복귀 근거로 남는다)."""
    model, (r11, r12, _), (_, quiet) = weak_parts
    _, _, _, _, abnormal = inputs
    second = pd.concat([D.inputs_only(magnitude_rows(model, abnormal, 1)), D.inputs_only(r12)], ignore_index=True)
    frame = _chain([r11, quiet.iloc[:14], second], "2022-07-22")
    first = len(r11) + 14
    f = _fault(frame, first, -early)
    pred = model.predict(f)
    assert pred.alarm.iloc[first] == 1
    tail = pred.iloc[first:]
    assert pred.incident_id.max() == 2 and (tail.incident_notification.sum(), tail.incident_escalation.sum()) == (1, 1)
    for chunk in (1, 7):
        assert_stream_matches(model, f, pred, chunk)


@pytest.mark.parametrize("rows", [2, 3])
def test_displaced_row_group_does_not_merge_incidents(weak_parts, rows):
    """이상 기록 끝 2·3행이 같은 크기로 늦게 찍혀 다음 정상 기록 앞 0.3초에 붙어도 두 이상은 따로 사건이다(검토 8 R8-01: 붙은 묶음끼리는
    정상 간격이라 4차 수정본의 한 행 규칙이 풀려 합쳐졌다)."""
    model, (r11, r12, _), (_, quiet) = weak_parts
    frame = _chain([r11, quiet.iloc[:14], r12], "2022-07-22")
    t = pd.to_datetime(frame[D.TIME])
    f = frame.copy()
    for row in range(len(r11) - rows, len(r11)):
        f.loc[row, D.TIME] = (t[row] + pd.Timedelta(seconds=2.7)).strftime("%Y-%m-%d %H:%M:%S.%f")
    pred = model.predict(f)
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (2, 2, 2)
    assert_stream_matches(model, f, pred, 7)


@pytest.mark.parametrize("gap", [.3, .45, .5])
def test_short_gaps_between_records_still_close_incidents(weak_parts, gap):
    """기록 사이 공백이 0.5초 이하인 연속 운전에서도 30행 정상 기록이 두 이상 사이의 정상 복귀 근거가 된다(검토 8 R8-02: 공백 0.5초 이하를
    한 흐름·5초 블록으로 묶은 4차 수정본은 이상 셋을 한 사건으로 합쳤다. c7d8bba는 사건 셋)."""
    model, (r11, r12, r13), (quiet, _) = weak_parts
    frame = _chain([r11, quiet.iloc[:30], r12, quiet.iloc[:30], r13], "2022-07-23", gap=gap)
    pred = model.predict(frame)
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (3, 3, 3)
    assert_stream_matches(model, frame, pred, 7)




@pytest.mark.parametrize("fill", ["blank", "resend"])
def test_rows_inside_gap_do_not_bridge_records(weak_parts, fill):
    """기록 사이 공백(1.5초)에 시각이 빈 행 15개나 앞 기록의 지난 행 15개가 역순으로(계속 보류) 끼어도 두 이상은 따로 사건이다(검토 9 R9-01: 도착한 행 수를
    j의 상한으로만 쓴 5차 판은 공백을 이어 붙여 둘째 이상의 알림을 없앴다)."""
    model, (r11, r12, _), (quiet, _) = weak_parts
    frame = _chain([r11, quiet.iloc[:30], r12], "2022-07-24", gap=1.5)
    cut = len(r11) + 30
    extra = D.inputs_only(quiet.iloc[:15]).copy()
    extra[D.TIME] = "" if fill == "blank" else frame[D.TIME].iloc[cut - 16:cut - 1].to_numpy()[::-1]   # 마지막 행보다 이르고 역순이라 계속 보류된다
    f = pd.concat([frame.iloc[:cut], extra, frame.iloc[cut:]], ignore_index=True)
    assert (model.predict(frame).incident_id.max()) == 2
    pred = model.predict(f)
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (2, 2, 2)
    assert_stream_matches(model, f, pred, 7)


@pytest.mark.xfail(strict=True, reason="알려진 한계(검토 7 R7-01): 사건 단위가 건 대기열과 같은 (기록구간, 50행 블록)이라 같은 시각 중복 한 행(검토 9 R9-03)도 기록을 자르면 사건이 나뉘거나 합쳐진다. 기록과 따로 정한 4~6차 규칙은 회귀(검토 8~10) 때문에 되돌렸다")
def test_duplicate_row_before_onset_does_not_split_incident(weak_parts):
    """이상 시작 바로 앞 정상 행이 같은 시각으로 한 번 더 와도 사건은 하나다(검토 9 R9-03: 간격 0에서 단위가 나뉘어 앞 정상 조각이 사건을 닫았다)."""
    model, (r11, r12, r13), (quiet, _) = weak_parts
    middle = pd.concat([D.inputs_only(quiet.iloc[:10]), D.inputs_only(r12)], ignore_index=True)
    frame = _chain([r11, middle, r13], "2022-07-21")
    at = len(r11) + 9
    f = pd.concat([frame.iloc[:at + 1], frame.iloc[[at]], frame.iloc[at + 1:]], ignore_index=True)
    pred = model.predict(f)
    assert (pred.incident_id.max(), pred.incident_notification.sum(), pred.incident_escalation.sum()) == (1, 1, 1)
    assert_stream_matches(model, f, pred, 7)


def test_incident_queue_matches_row_alerts_in_long_continuous_record(inputs):
    """50행보다 긴 연속 기록에서 시각 결측 한 행이 기록을 나눠도 사건 대기열(incidents(cases))이 행별 사건·알림 열과 맞는다(검토 10 R10-03:
    사건 단위를 기록과 따로 정한 6차 판은 건과 사건의 경계가 어긋나 시작 알림이 나간 사건이 대기열에 없거나 단계가 달랐다). 경보 행은 정해 준다."""
    model, _, _, normal, _ = inputs
    test = D.inputs_only(D.split_normal(normal, D.segments(normal), "B")["test"]).reset_index(drop=True)
    seg = D.segments(test)
    frame = test.iloc[np.flatnonzero((seg >= 20) & (seg < 50))].reset_index(drop=True)
    frame[D.TIME] = (pd.Timestamp("2022-07-25 08:00:00") + pd.to_timedelta(np.arange(len(frame)) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
    rng = np.random.default_rng(2026)
    for d in (6, 16, 24, 40):
        f = frame.copy()
        f.loc[d, D.TIME] = ""
        base = model.predict(f)
        for _ in range(8):
            rows = rng.choice(400, size=int(rng.integers(2, 7)), replace=False)
            p = base.copy()
            a = np.zeros(len(p), bool); a[rows] = True
            a &= p.status.eq("ok").to_numpy()
            p["alarm"] = a.astype(int)
            p["reason"] = np.where(a, "magnitude", np.where(p.status.eq("ok"), "", "invalid_input"))
            times = pd.to_datetime(p.timestamp, format="mixed", utc=True, errors="coerce")
            inc = incident_columns(p.record_id.to_numpy(), p.alert_unit.to_numpy(), a, p.reason.to_numpy(), times,
                                   p.status.eq("ok").to_numpy(), p.time_order_event.to_numpy())
            p["incident_id"], p["incident_notification"], p["incident_escalation"], p["incident_update"] = inc.T
            queue = incidents(cases(p), p)
            assert set(p.incident_id[a].astype(int)) == set(queue.incident_id.astype(int))
            escalated = set(p.incident_id[p.incident_escalation.eq(1)].astype(int))
            assert all((r.level == 2) == (int(r.incident_id) in escalated) for r in queue.itertuples())

