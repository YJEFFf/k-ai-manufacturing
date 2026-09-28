"""simulate.py 계약: 한 행씩 흘려 넣은 모의 운용의 알림 행·단계가 일괄 분석과 같다(평가관 04 U7)."""
import numpy as np
import pandas as pd
import pytest

import simulate
from model import D, HERE, load_bundle


@pytest.fixture(scope="module")
def stream_frame():
    normal, abnormal, _ = D.load()
    seg = D.segments(normal)
    a_seg = D.segments(abnormal)
    # B 오경보 구간 423이 든 정상 기록 몇 개 + 이상 기록 앞 5구간(경보·격상)
    part = pd.concat([normal[(seg >= 421) & (seg <= 424)], abnormal[a_seg < 5]], ignore_index=True)
    return D.inputs_only(part)


def test_stream_alerts_equal_batch(stream_frame):
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    log = simulate.run(stream_frame, model, .01, chunk=1)
    batch = model.predict(stream_frame, .01)
    assert log[log.kind.eq("사건 시작")].row_id.tolist() == batch.index[batch.incident_notification.eq(1)].tolist()
    assert log[log.kind.eq("격상")].row_id.tolist() == batch.index[batch.incident_escalation.eq(1)].tolist()
    assert log[log.kind.eq("근거 추가")].row_id.tolist() == batch.index[batch.incident_update.eq(1)].tolist()
    assert (log[log.kind.eq("격상")].level == 2).all() and (log[log.kind.eq("사건 시작")].level == 1).all()
    assert log[log.kind.eq("근거 추가")].notify.eq(0).all()


def test_abnormal_minutes_are_one_incident():
    """평가관 04 R2-03: 대회 이상 21기록(2.76분)은 사건 1개, 알림 2건(사건 시작·격상)이다. 구간 단위 알림은 그대로 21건이다."""
    _, abnormal, _ = D.load()
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    log = simulate.run(D.inputs_only(abnormal), model, .01, chunk=64)
    assert log[log.notify.eq(1)].kind.tolist() == ["사건 시작", "격상"] and log.incident_id.nunique() == 1
    assert model.predict(abnormal, .01).notification.sum() == 21


def test_false_alarm_then_anomaly_escalates(stream_frame):
    """평가관 04 S2: 경보 1행짜리 건 바로 뒤 같은 기록에서 이상이 이어지면 새 첫 알림은 없어도 2단계 격상 알림이 나온다."""
    normal, abnormal, _ = D.load()
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    seg = D.segments(normal)
    fa = D.inputs_only(normal[seg == 423])                      # B α=1% 오경보 구간(경보 1행)
    batch_fa = model.predict(fa, .01)
    assert batch_fa.alarm.sum() == 1
    tail = D.inputs_only(abnormal[D.segments(abnormal) == 11]).copy()
    last = pd.to_datetime(fa[D.TIME].iloc[-1])
    tail[D.TIME] = [(last + pd.Timedelta(seconds=D.DT * (k + 1))).strftime("%Y-%m-%d %H:%M:%S.%f") for k in range(len(tail))]
    joined = pd.concat([fa, tail], ignore_index=True)          # 끊김 없이 이어 붙인 한 기록구간
    log = simulate.run(joined, model, .01, chunk=7)
    p = model.predict(joined, .01)
    assert p.record_id.nunique() == 1
    assert log.kind.tolist().count("격상") == 1 and log[log.kind.eq("격상")].row_id.iloc[0] >= len(fa) - 1
    assert log.kind.tolist().count("사건 시작") == 1                      # 오경보 1행과 이어진 이상은 같은 사건
    assert (p.alert_level.iloc[len(fa):] == 2).any()


def test_speed_waits_for_the_clock(stream_frame):
    """speed>0이면 수집 속도에 맞춰 기다린다(가짜 시계로 확인)."""
    model = load_bundle(HERE / "artifacts" / "guard_B.json")
    now = [0.0]
    waits = []
    simulate.run(stream_frame.iloc[:40], model, .01, chunk=10, speed=2.0, clock=lambda: now[0],
                 sleep=lambda s: (waits.append(s), now.__setitem__(0, now[0] + s)))
    assert len(waits) == 4 and np.allclose(np.cumsum(waits), [0.5, 1.0, 1.5, 2.0])
