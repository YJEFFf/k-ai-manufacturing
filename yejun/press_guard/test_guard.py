"""실제 CSV·저장 모델로 입력 경계/순차 추론/알림 계약 검증."""
import json
import numpy as np
import pandas as pd
import pytest
from model import GuardModel, StreamDetector, cases, D, HERE


@pytest.fixture(scope="module")
def data():
    return D.load()[:2]


@pytest.fixture(scope="module")
def model(data):
    n,_=data
    sp=D.split_normal(n,D.segments(n),"A")
    return GuardModel.fit(sp["train"],sp["cal"],split="A")


@pytest.mark.parametrize("chunks",[(1,),(2,7,3,1,19),(128,),(1000,)])
def test_stream_boundaries(model,data,chunks):
    n,a=data
    frame=pd.concat([n.iloc[:49],a.iloc[:97]],ignore_index=True)
    frame.loc[14,D.SENSORS[0]]=np.nan
    frame.loc[18,D.TIME]="bad"
    frame.loc[30,D.TIME]=frame.loc[29,D.TIME]
    frame.loc[40,D.TIME]=frame.loc[38,D.TIME]
    frame.loc[43,D.TIME]=pd.Timestamp(frame.loc[43,D.TIME]).isoformat()+"+00:00"
    expected=model.predict(frame)
    stream=StreamDetector(model)
    rows=[]; i=0; c=0
    while i<len(frame):
        size=chunks[c%len(chunks)]
        rows.append(stream.push(frame.iloc[i:i+size])); i+=size; c+=1
        assert len(stream.tail)<=7
    pd.testing.assert_frame_equal(pd.concat(rows,ignore_index=True),expected,rtol=1e-11,atol=1e-11)


def test_label_and_clock_bypass(model,data):
    _,a=data
    expected=model.predict(a)
    modified=D.inputs_only(a)
    modified[D.TIME]=(pd.to_datetime(modified[D.TIME])+pd.Timedelta(days=517)).astype(str)
    modified["Equipment_state"]=np.arange(len(a))%2
    modified["file_name"]="normal.csv"
    actual=model.predict(modified)
    pd.testing.assert_frame_equal(actual.drop(columns="timestamp"),expected.drop(columns="timestamp"))


def test_future_invariance(model,data):
    _,a=data
    full=model.predict(a)
    for end in (1,2,6,7,8,11,31,101):
        pd.testing.assert_frame_equal(model.predict(a.iloc[:end]),full.iloc[:end])


def test_invalid_reset_and_no_false_normal(model,data):
    n,_=data
    f=D.inputs_only(n.iloc[:20]).copy()
    f.loc[8,D.SENSORS[1]]=float("inf")
    pred=model.predict(f)
    assert pred.loc[8,"status"]=="bad_value"
    assert np.isnan(pred.loc[8,"score"]) and pred.loc[8,"alarm"]==0
    assert pred.loc[8,"action"]=="수집 상태 확인"
    assert pred.loc[9,"position"]==0 and np.isnan(pred.loc[9,"g_dynamics"])
    assert np.isnan(pred.loc[10,"g_dynamics"])


def test_one_notification_per_record(model,data):
    _,a=data
    pred=model.predict(a)
    assert len(cases(pred))==21
    assert pred.notification.sum()==21
    assert pred.groupby("record_id").notification.max().eq(1).all()
    assert pred.alarm.sum()==556


def test_artifact_roundtrip_and_tamper(model,data,tmp_path):
    path=tmp_path/"guard.json"
    model.save(path)
    pd.testing.assert_frame_equal(model.predict(data[1]),GuardModel.load(path).predict(data[1]))
    content=json.loads(path.read_text(encoding="utf-8")); content["state"]["ar2"][0]+=1
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError,match="해시"): GuardModel.load(path)


def test_empty_and_bad_contract(model,data):
    empty=D.inputs_only(data[0]).iloc[:0]
    assert model.predict(empty).empty
    assert StreamDetector(model).push(empty).empty
    with pytest.raises(KeyError): model.predict(pd.DataFrame({"time":[0]}))
    with pytest.raises(ValueError): model.predict(data[1],alpha=.02)


@pytest.mark.parametrize("alpha",[.01,.03,.05])
def test_rank_rule_independent(model,data,alpha):
    pred=model.predict(data[1],alpha)
    direct=np.asarray([(1+sum(model.cal>=s))/(len(model.cal)+1) for s in pred.score])
    np.testing.assert_array_equal(pred.p_value.to_numpy(),direct)
    np.testing.assert_array_equal(pred.alarm.to_numpy(),(direct<=alpha).astype(int))


def _continuous(frame, start="2022-07-12 02:00:00"):
    """끊김 없는 0.1초 간격으로 다시 찍은 입력(연속 수집 모의)."""
    f = D.inputs_only(frame).copy()
    f[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(f)) * 100, unit="ms")).astype(str)
    return f


def test_action_follows_magnitude_sensor(model, data):
    """크기 성분이 전류에서 나왔으면 진동 점검을 권하지 않는다(루브릭 검수 R6)."""
    n, _ = data
    base = D.inputs_only(n.iloc[:1]).copy()
    cur, vib = base.copy(), base.copy()
    cur[D.SENSORS[2]] = model.mean[2] + 30 * model.scale[2]
    vib[D.SENSORS[0]] = model.mean[0] + 30 * model.scale[0]
    pc, pv = model.predict(cur), model.predict(vib)
    assert pc.loc[0, "reason"] == "magnitude" and pc.loc[0, "magnitude_sensor"] == D.SENSORS[2]
    assert pc.loc[0, "action"] == "전류 크기·부하·계측 확인" and cases(pc).action.iloc[0] == "전류 크기·부하·계측 확인"
    assert pv.loc[0, "action"] == "진동·부하 확인" and cases(pv).magnitude_sensors.iloc[0] == D.SENSORS[0]


def _synthetic_normal(model, rows, seed=0):
    """끊김 없는 정상 모의 신호: 0.6 Hz 사인 전류 + 작은 잡음, 정상 척도의 절반인 진동 잡음. 실제 기록을 이어 붙이면 경계마다 위상이 끊겨 인공 경보가 생긴다."""
    rng = np.random.default_rng(seed)
    t = np.arange(rows) * D.DT
    return pd.DataFrame({D.TIME: "", D.SENSORS[0]: model.mean[0] + .5 * model.scale[0] * rng.standard_normal(rows),
                         D.SENSORS[1]: model.mean[1] + .5 * model.scale[1] * rng.standard_normal(rows),
                         D.SENSORS[2]: model.mean[2] + np.sqrt(2) * model.scale[2] * np.sin(2 * np.pi * .6 * t) + 2 * rng.standard_normal(rows)})


def test_continuous_stream_rearms_and_merges(model, data):
    """연속 입력은 50행 블록으로 알린다. 앞쪽 알림 뒤의 이상도 새 알림을 받고, 이어지는 이상 블록은 한 건으로 묶인다(R7)."""
    _, a = data
    normal_part = _synthetic_normal(model, 1500)
    normal_part.loc[39, D.SENSORS[0]] = model.mean[0] + 30 * model.scale[0]     # 앞쪽 오경보 하나
    frame = _continuous(pd.concat([normal_part, D.inputs_only(a)], ignore_index=True))
    pred = model.predict(frame)
    assert pred.record_id.nunique() == 1 and pred.beyond_calibration_length.sum() == len(frame) - 50
    assert pred.notification.iloc[:50].sum() == 1 and pred.alarm.iloc[50:1500].sum() == 0   # 전제: 스파이크 뒤 정상 부분은 조용하다
    later = pred.iloc[1500:]
    assert later.notification.sum() >= 1                      # 이상 부분이 앞 알림에 묻히지 않는다(이전 규칙이면 0)
    blocks = later.groupby("alert_unit").alarm.max()
    assert later.notification.sum() < blocks.sum()            # 경보가 이어진 블록은 새로 알리지 않는다
    queue = cases(pred)
    assert len(queue) == pred.notification.sum() and queue.beyond_calibration_length.iloc[-1] == 1
    for chunks in ((1,), (7, 50, 3), (128,)):
        stream = StreamDetector(model); parts = []; i = 0; c = 0
        while i < len(frame):
            size = chunks[c % len(chunks)]; parts.append(stream.push(frame.iloc[i:i + size])); i += size; c += 1
        pd.testing.assert_frame_equal(pd.concat(parts, ignore_index=True), pred, rtol=1e-11, atol=1e-11)


def test_calibration_unit_is_alert_unit(data):
    """보정도 알림과 같은 단위(기록구간 안 50행 블록)로 한다. 대회 자료는 기록구간과 같다."""
    n, _ = data
    sp = D.split_normal(n, D.segments(n), "A")
    cal = _continuous(sp["cal"].iloc[:1000])
    m = GuardModel.fit(sp["train"], cal, split="A")
    assert len(m.cal) == 20
    same = GuardModel.fit(sp["train"], sp["cal"], split="A")
    assert len(same.cal) == 120



@pytest.mark.parametrize("jitter_ms", [1, 2])
def test_timestamp_jitter_keeps_records(data, jitter_ms):
    """평가관 04 2회차 R2-05: 수집 시각이 ±1·2 ms 흔들려도 기록 경계(0.1초 ± 20 ms)와 미탐이 흔들림 없는 결과와 같다."""
    from model import load_bundle, timing_warning
    _, a = data
    m = load_bundle(HERE / "artifacts" / "guard_B.json")
    j = a.copy()
    t = pd.to_datetime(j.TimeStamp)
    j["TimeStamp"] = (t + pd.to_timedelta(np.random.default_rng(0).uniform(-jitter_ms, jitter_ms, len(t)) / 1000, unit="s")).astype(str)
    p0, pj = m.predict(a, .01), m.predict(j, .01)
    assert pj.record_id.nunique() == p0.record_id.nunique() == 21
    assert (pj.alarm == 0).sum() == (p0.alarm == 0).sum() == 31
    assert timing_warning(pj) == ""


def test_short_records_raise_timing_warning(data):
    """간격이 크게 흔들려 기록이 쪼개지면(평균 5행 미만) 수집 시각 간격 경고를 낸다."""
    from model import load_bundle, timing_warning
    _, a = data
    m = load_bundle(HERE / "artifacts" / "guard_B.json")
    j = a.copy()
    t = pd.to_datetime(j.TimeStamp)
    j["TimeStamp"] = (t + pd.to_timedelta(np.random.default_rng(1).uniform(-.05, .05, len(t)), unit="s")).astype(str)
    assert "수집 시각 간격" in timing_warning(m.predict(j, .01))
