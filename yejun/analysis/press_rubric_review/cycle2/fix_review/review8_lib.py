"""검토 8 공용 도구. REVIEW_ENV=<사본의 yejun 폴더>의 press_guard를 불러온다(저장소의 코드는 실행하지 않는다).
8b65130·c7d8bba 사본 어느 쪽에서도 같은 입력을 만들 수 있게, 입력 구성은 모델 판과 무관한 규칙(대회 원본 CSV 행 + 고정 시각)만 쓴다."""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ENV = Path(os.environ["REVIEW_ENV"]).resolve()
sys.path.insert(0, str(ENV / "press_guard"))
os.chdir(ENV / "press_guard")

import model as M  # noqa: E402
from model import D, HERE, StreamDetector, load_bundle  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S.%f"
VERSION = "8b65130" if hasattr(M, "CollectionUnits") else "c7d8bba"
_C = {}


def model():
    if "m" not in _C:
        _C["m"] = load_bundle(HERE / "artifacts" / "guard_B.json")
    return _C["m"]


def parts():
    """(이상 기록 11·12·13, 경보 없는 정상 기록 2개(30행 이상), 1행으로도 경보가 나는 이상 행 4개). 선정은 selfcheck4_displaced·시험과 같다.
    선정에 쓰는 예측(원자료 예측)은 두 판에서 같다(검토 7 불변식 (e))."""
    if "p" not in _C:
        mdl = model()
        normal, abnormal, _ = D.load()
        seg = D.segments(abnormal)
        test = D.inputs_only(D.split_normal(normal, D.segments(normal), "B")["test"]).reset_index(drop=True)
        pred = mdl.predict(test)
        rec = pred.record_id.to_numpy()
        quiet = [r for r in np.unique(rec) if pred.alarm[rec == r].sum() == 0 and (rec == r).sum() >= 30]
        ab = D.inputs_only(abnormal).reset_index(drop=True)
        probe = ab.copy()
        probe[D.TIME] = [(pd.Timestamp("2022-07-17 10:00:00") + pd.Timedelta(seconds=10 * i)).strftime(FMT) for i in range(len(ab))]
        mag = ab.iloc[np.flatnonzero(mdl.predict(probe).alarm.eq(1).to_numpy())[:4]].reset_index(drop=True)
        recs = [D.inputs_only(abnormal[seg == k]).reset_index(drop=True) for k in (11, 12, 13)]
        _C["p"] = recs, [test[rec == q].reset_index(drop=True) for q in quiet[:2]], mag
    return _C["p"]


def chain(parts_, gap=3.0, start="2022-07-22"):
    """부분마다 0.1초 간격, 부분 사이 gap초(목록이면 부분마다) 공백. 돌려주는 값: (입력, 부분 시작 행 번호 목록)."""
    frames, times, starts, t = [], [], [], pd.Timestamp(start)
    gaps = gap if isinstance(gap, (list, tuple)) else [gap] * len(parts_)
    for k, part in enumerate(parts_):
        starts.append(len(times))
        times += list(t + pd.to_timedelta(np.arange(len(part)) * .1, unit="s"))
        t = times[-1] + pd.Timedelta(seconds=gaps[k])
        frames.append(D.inputs_only(part))
    f = pd.concat(frames, ignore_index=True)
    f[D.TIME] = pd.Series(times).dt.strftime(FMT)
    return f, starts


def shift(frame, row, seconds):
    f = frame.copy()
    t = pd.to_datetime(f[D.TIME])
    f.loc[row, D.TIME] = (t[row] + pd.Timedelta(seconds=seconds)).strftime(FMT)
    return f


def nat(frame, row):
    f = frame.copy(); f.loc[row, D.TIME] = ""; return f


def sensor_nan(frame, row):
    f = frame.copy(); f.loc[row, D.SENSORS[0]] = np.nan; return f


def drop(frame, row):
    return frame.drop(index=row).reset_index(drop=True)


def dup(frame, row):
    return pd.concat([frame.iloc[:row + 1], frame.iloc[row:row + 1], frame.iloc[row + 1:]], ignore_index=True)


def summ(p):
    """(사건 수, 시작 알림, 격상 알림)."""
    return (int(p.incident_id.max()), int(p.incident_notification.sum()), int(p.incident_escalation.sum()))


def start_rows(p):
    return [int(i) for i in np.flatnonzero(p.incident_notification.to_numpy() == 1)]


def stream(frame, chunk):
    det = StreamDetector(model())
    sizes = chunk if isinstance(chunk, (list, tuple)) else None
    out, i, k = [], 0, 0
    while i < len(frame):
        n = int(sizes[k % len(sizes)]) if sizes else int(chunk)
        out.append(det.push(frame.iloc[i:i + n])); i += n; k += 1
    return pd.concat(out, ignore_index=True)


def same(a, b):
    try:
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), rtol=1e-11, atol=1e-11)
        return True
    except AssertionError:
        return False


def dup_alerts(p):
    per = p[p.incident_id.gt(0)].groupby("incident_id")[["incident_notification", "incident_escalation"]].sum()
    return int((per > 1).any(axis=1).sum()) if len(per) else 0
