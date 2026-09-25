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
    content=json.loads(path.read_text()); content["state"]["ar2"][0]+=1
    path.write_text(json.dumps(content))
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
