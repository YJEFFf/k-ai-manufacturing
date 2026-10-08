"""stages.py(두 단계 경보 스트림) 시험: 공식 규칙과의 일치, 미래 행 불변, 기록 경계 초기화, 묶음 크기 불변, 제출 예측 파일 재현.

원본 CSV가 press_submission/data/3_소성가공_예지보전/(또는 PRESS_DATA_ROOT, 저장소의 데이터셋/ 아래)에 있어야 데이터 시험이 돈다.
준용 tvt(lib.py·제출 예측 파일)가 저장소에 없으면 그 대조 시험은 건너뛴다(읽기 전용으로 import만 한다).
"""
import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import stages
from model import D, HERE

TVT = HERE.parents[1] / "claude" / "code" / "press" / "tvt"


def _find_data():
    roots = [D.data_dir(D.PACKAGE_DIR), Path(os.environ["PRESS_DATA_ROOT"]) if os.environ.get("PRESS_DATA_ROOT") else None,
             HERE.parents[1] / "데이터셋"]
    found = {}
    for key, name in D.FILES.items():
        for root in filter(None, roots):
            hits = [p for p in sorted(Path(root).rglob(name)) if p.is_file()] if Path(root).is_dir() else []
            good = [p for p in hits if hashlib.sha256(p.read_bytes()).hexdigest() == D.EXPECTED_SHA256[key]]
            if good:
                found[key] = good[0]
                break
    return found if len(found) == 2 else None


DATA = _find_data()
needs_data = pytest.mark.skipif(DATA is None, reason="대회 원본 CSV 없음")


def _lib():
    if not (TVT / "lib.py").is_file():
        pytest.skip("준용 tvt/lib.py 없음")
    sys.dont_write_bytecode = True
    if str(TVT) not in sys.path:
        sys.path.append(str(TVT))
    import lib
    return lib


@pytest.fixture(scope="module")
def data():
    return pd.read_csv(DATA["normal"]), pd.read_csv(DATA["abnormal"])


@pytest.fixture(scope="module")
def small_state(data):
    """빠른 시험용: 정상 기록 0~119 학습, 120~239 보정(공식 분할과 다르다). α 1%는 보정 99기록 이상에서만 경보가 가능하다."""
    normal, _ = data
    seg = D.segments(normal)
    return stages.StageState.fit(normal[seg < 120].reset_index(drop=True), normal[(seg >= 120) & (seg < 240)].reset_index(drop=True),
                                 split="test_small")


@pytest.fixture(scope="module")
def flow(data):
    """정상 기록 400~439 다음 이상 21기록(이상은 R1 이어받기·R2 보류·관측 부족 행을 모두 만든다)."""
    normal, abnormal = data
    seg = D.segments(normal)
    return pd.concat([normal[(seg >= 400) & (seg < 440)], abnormal], ignore_index=True)[[D.TIME] + D.SENSORS]


def test_constants_and_r2_match_official_lib():
    lib = _lib()
    assert (stages.GAP_S, stages.CONFIRM_ROWS, stages.R2_Q, stages.R2_MIN_LEN, stages.F0) == \
           (lib.GAP_S, lib.CONFIRM_ROWS, lib.R2_Q, lib.R2_MIN_LEN, lib.F0)
    rng = np.random.default_rng(0)
    x = 200 * np.sin(2 * np.pi * stages.F0 * np.arange(300)) + rng.normal(0, 20, 300)
    rec = np.repeat(np.arange(10), 30)
    assert np.array_equal(stages.prefix_r2(x, rec), lib.prefix_r2(x, rec), equal_nan=True)


def test_rule_layer_matches_stream_rules():
    """R1 상태 기계가 lib.stream_rules(latch=True)와 무작위 입력 2,000개에서 행마다 같다(이어받기·해제·60초·확인 2행)."""
    lib = _lib()
    rng = np.random.default_rng(1)
    for _ in range(2000):
        n_rec = int(rng.integers(1, 8))
        lengths = rng.integers(1, 12, n_rec)
        records = np.repeat(np.arange(n_rec), lengths)
        gaps = rng.choice([1.5, 30.0, 59.9, 60.0, 60.1, 300.0], n_rec)
        t, times = 0.0, []
        for k, length in enumerate(lengths):
            t += gaps[k] if k else 0.0
            times += [t + 0.1 * j for j in range(length)]
            t = times[-1]
        ts = (np.array(times) * 1e9).astype("int64").astype("datetime64[ns]")
        own = rng.random(len(records)) < rng.choice([0.05, 0.3, 0.7])
        wave_ok = rng.random(len(records)) < rng.choice([0.1, 0.5, 0.9])
        ref, unreleased = lib.stream_rules(ts, records, own, wave_ok, True)
        got, inherited, released = stages.r1_rows(ts, records, own, wave_ok)
        assert np.array_equal(got, ref)
        assert np.array_equal(got, own | inherited) and not (inherited & released).any()
        for r in np.unique(records):   # 기록 끝까지 안 풀린 이어받기 = lib의 unreleased
            idx = np.flatnonzero(records == r)
            started = inherited[idx[0]] or released[idx[0]]
            assert unreleased[r] == bool(started and not released[idx].any()), r


@needs_data
def test_quantize_matches_official(data):
    normal, abnormal = data
    for frame in (normal, abnormal):
        x = frame[D.SENSORS].to_numpy(float)
        assert np.array_equal(stages._quantize(x), D.quantize(D.inputs_only(frame), "matched")[D.SENSORS].to_numpy(float))


@needs_data
def test_chunk_invariance(small_state, flow):
    """한 행씩(push_row), 한 번에, 무작위 묶음(1~97행)으로 넣어도 모든 열이 같다. 한 행 길과 묶음 길의 v2 성분 계산이 서로 대조된다."""
    once = stages.replay(small_state, flow)
    by_row = stages.rows_by_row(small_state, flow)
    assert by_row.equals(once)
    rng = np.random.default_rng(2)
    for _ in range(3):
        assert stages.replay(small_state, flow, chunk=rng.integers(1, 98, len(flow))).equals(once)
    assert stages.replay(small_state, flow, chunk=1).equals(once)
    assert set(once.columns) == set(stages.COLUMNS)


@needs_data
def test_future_rows_do_not_change_past(small_state, flow):
    """앞 k행의 결과는 뒤에 무엇이 오든 같다: 잘라 흘린 결과, 뒤를 다른 값으로 바꾼 결과가 앞 k행에서 같다."""
    full = stages.replay(small_state, flow)
    rng = np.random.default_rng(3)
    for k in sorted(rng.integers(1, len(flow), 6)):
        head = stages.replay(small_state, flow.iloc[:k])
        assert head.equals(full.iloc[:k])
        changed = flow.copy()
        changed.loc[k:, D.SENSORS] = changed.loc[k:, D.SENSORS].to_numpy()[::-1] * 3.0
        assert stages.replay(small_state, changed).iloc[:k].equals(full.iloc[:k])


@needs_data
def test_record_boundary_resets_windows_and_r1(data, small_state):
    """기록 경계(0.1초 ± 20 ms 밖)에서 위치·파형·AR 창·prefix R²가 새로 시작하고, R1은 직전 기록이 확인된 이상이고 60초 안일 때만 잇는다."""
    normal, abnormal = data
    seg_n, seg_a = D.segments(normal), D.segments(abnormal)
    nxt = normal[seg_n == 500].reset_index(drop=True)                 # 50행 정상 기록
    t0 = pd.to_datetime(nxt[D.TIME].iloc[0])

    def before(rec, gap_s):
        """rec 기록을 nxt 시작 gap_s초 앞에서 끝나게 옮긴다."""
        r = rec.reset_index(drop=True).copy()
        t = pd.to_datetime(r[D.TIME])
        r[D.TIME] = (t - t.iloc[-1] + t0 - pd.Timedelta(seconds=gap_s)).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str.slice(0, 23)
        return r

    quiet = before(normal[seg_n == 499], 5.0)
    fault = before(abnormal[seg_a == 1], 5.0)                      # 이상 기록 1(50행)
    far = before(abnormal[seg_a == 1], 61.0)
    near = before(abnormal[seg_a == 1], 0.13)                      # 0.13초: 기록 경계
    outs = {k: stages.replay(small_state, pd.concat([f, nxt], ignore_index=True)).iloc[-len(nxt):].reset_index(drop=True)
            for k, f in dict(quiet=quiet, fault=fault, far=far, near=near).items()}
    alone = stages.replay(small_state, nxt)
    cols = ["position", "score", "p_value", "g_magnitude", "g_waveform", "g_dynamics", "prefix_r2", "v2_alarm", "own1", "own2", "r2_hold"]
    for k, o in outs.items():
        assert o[cols].equals(alone[cols]), k                       # 직전 기록 내용과 무관
        assert (o.record == o.record.iloc[0]).all() and o.position.iloc[0] == 0
    fault_flags = stages.replay(small_state, fault)
    assert fault_flags.own1.sum() >= stages.CONFIRM_ROWS               # 직전 기록이 확인된 이상
    f = outs["fault"]
    rel = np.flatnonzero(f.released1.to_numpy())
    assert len(rel) == 1 and rel[0] >= stages.R2_MIN_LEN - 1           # 8행째 이후 전류 파형 정상에서 해제
    assert f.inherited1.iloc[:rel[0]].all() and not f.inherited1.iloc[rel[0]:].any() and f.stage1.iloc[:rel[0]].all()
    assert not f.insufficient.iloc[rel[0]] and f.insufficient.iloc[:stages.R2_MIN_LEN - 1].all()
    assert not outs["quiet"].inherited1.any() and not outs["far"].inherited1.any()   # 확인된 이상이 아니거나 60초 넘음
    assert outs["near"].inherited1.iloc[0]                                          # 0.13초 간격도 새 기록이고 이어받는다
    joined = stages.replay(small_state, pd.concat([before(normal[seg_n == 499], -0.0), nxt], ignore_index=True))
    assert joined.record.nunique() == 2                                             # 같은 시각 중복은 경계(간격 0)


@needs_data
def test_invalid_rows_break_records(small_state, flow):
    bad = flow.copy()
    bad.loc[30, D.SENSORS[2]] = np.nan
    out = stages.replay(small_state, bad)
    ref = stages.replay(small_state, flow)
    assert out.status[30] == "bad_value" and out.position[30] == 0 and out.position[31] == 0
    assert not out.v2_alarm[30] and out.insufficient[30]
    assert out.record[30] != out.record[29] and out.record[31] != out.record[30]
    assert out.iloc[:30].equals(ref.iloc[:30])


@needs_data
def test_stage2_is_inside_stage1(small_state, flow):
    out = stages.replay(small_state, flow)
    assert not (out.stage2 & ~out.stage1).any()
    assert (out.r2_hold <= (out.v2_alarm & out.wave_ok & (out.evidence == "magnitude"))).all()
    assert (out.level == np.where(out.stage2, 2, np.where(out.stage1, 1, 0))).all()
    assert out.event1_start.sum() >= out.event2_start.sum() >= 1


@needs_data
@pytest.mark.parametrize("sid", ["A", "B"])
def test_reproduces_submission_prediction_files(data, sid):
    """제출 예측 파일의 1단계(locked_v2_R1_realtime)·2단계(final_v2_R1_R2_realtime)·v2 열을 시험 행마다 그대로 낸다.
    흐름은 공식과 같다: 정상은 검증 정상 → 시험 정상 한 흐름, 이상은 21기록 전체(앞 10기록 = 검증)."""
    path = TVT / "outputs" / f"test_predictions_{sid}.csv"
    if not path.is_file():
        pytest.skip("제출 예측 파일 없음")
    normal, abnormal = data
    pred = pd.read_csv(path)
    sp = D.split_normal(normal, D.segments(normal), sid)
    state = stages.StageState.fit(sp["train"], sp["cal"], split=sid)
    flows = {"normal": (pd.concat([sp["cal"], sp["test"]], ignore_index=True), len(sp["cal"])),
             "abnormal": (abnormal, int((D.segments(abnormal) < 10).sum()))}
    for subset, (frame, n_valid) in flows.items():
        out = stages.replay(state, frame).iloc[n_valid:].reset_index(drop=True)
        p = pred[pred.subset.eq(subset)].reset_index(drop=True)
        assert len(out) == len(p) and (out.timestamp.str.slice(0, 23) == p.ts.str.slice(0, 23)).all()
        for mine, theirs in (("stage1", "locked_v2_R1_realtime"), ("stage2", "final_v2_R1_R2_realtime"), ("v2_alarm", "v2_realtime")):
            assert np.array_equal(out[mine].to_numpy(bool), p[theirs].astype(str).eq("True").to_numpy()), (sid, subset, mine)
