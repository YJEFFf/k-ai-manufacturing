"""검토 7 공용 도구. REVIEW_ENV=<사본의 yejun 폴더>의 press_guard를 불러온다(저장소는 읽지도 실행하지도 않는다)."""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ENV = Path(os.environ["REVIEW_ENV"]).resolve()
sys.path.insert(0, str(ENV / "press_guard"))
os.chdir(ENV / "press_guard")

import model as M  # noqa: E402
from model import D, HERE, StreamDetector, cases, incidents, load_bundle  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S.%f"
_CACHE = {}


def data():
    if "data" not in _CACHE:
        normal, abnormal, _ = D.load()
        _CACHE["data"] = normal, abnormal
    return _CACHE["data"]


def model(split="B"):
    key = ("model", split)
    if key not in _CACHE:
        _CACHE[key] = load_bundle(HERE / "artifacts" / f"guard_{split}.json")
    return _CACHE[key]


def base_abnormal():
    """대회 이상 파일 600행(21기록). 시각은 원래 값."""
    _, abnormal = data()
    frame = D.inputs_only(abnormal).reset_index(drop=True)
    return frame, pd.to_datetime(frame[D.TIME])


def normal_test(split="B"):
    normal, _ = data()
    sp = D.split_normal(normal, D.segments(normal), split)
    return D.inputs_only(sp["test"]).reset_index(drop=True)


def with_times(frame, times):
    out = D.inputs_only(frame).copy().reset_index(drop=True)
    out[D.TIME] = [pd.Timestamp(t).strftime(FMT) if t is not None and not pd.isna(t) else "" for t in times]
    return out


def build(frame, true_times, faults):
    """도착 순서의 입력을 만든다. faults는 (종류, 행, 값) 목록이다. 돌려주는 값: (입력, 오류 행 표시, 원래 행 번호).
    종류: replace(행 시각 += 값초), insert(행 사본을 시각 += 값초로 그 행 바로 앞에 끼움), insert_after(바로 뒤에 끼움),
    nat(시각 결측), nan(센서 결측), dup(같은 행을 바로 뒤에 한 번 더), move(행을 값칸 뒤로 늦게 도착)."""
    rows = list(range(len(frame)))
    times = [pd.Timestamp(t) for t in true_times]
    err = [False] * len(frame)
    nan_rows = set()
    items = [dict(src=i, t=times[i], err=False, nan=False) for i in rows]
    # 시계 재설정(step)은 원래 행 번호 row부터 끝까지 시각을 value초 옮긴다. 다른 오류보다 먼저 적용한다.
    for kind, row, value in faults:
        if kind == "step":
            for it in items:
                if it["src"] >= row and it["t"] is not None:
                    it["t"] = it["t"] + pd.Timedelta(seconds=value)
    # 원래 행 번호로 찾아 적용한다(삽입해도 번호가 밀리지 않게)
    for kind, row, value in faults:
        if kind == "step":
            continue
        idx = next(k for k, it in enumerate(items) if it["src"] == row and not it.get("extra"))
        if kind == "replace":
            items[idx]["t"] = items[idx]["t"] + pd.Timedelta(seconds=value)
            items[idx]["err"] = True
        elif kind in ("insert", "insert_after"):
            extra = dict(items[idx]); extra["t"] = items[idx]["t"] + pd.Timedelta(seconds=value); extra["err"] = True; extra["extra"] = True
            items.insert(idx if kind == "insert" else idx + 1, extra)
        elif kind == "nat":
            items[idx]["t"] = None
            items[idx]["err"] = True
        elif kind == "nan":
            items[idx]["nan"] = True
        elif kind == "dup":
            extra = dict(items[idx]); extra["err"] = True; extra["extra"] = True
            items.insert(idx + 1, extra)
        elif kind == "rexmit":          # row까지의 value행을 row 바로 뒤에 같은 시각으로 다시 보냄
            block = [dict(it) for it in items[max(0, idx - int(value) + 1):idx + 1]]
            for b in block:
                b["err"] = True; b["extra"] = True
            items[idx + 1:idx + 1] = block
        elif kind in ("tail", "backlog"):  # row 바로 뒤에, row 앞 행 시각 + (0.1·j 또는 1.0 + 0.1·j)초의 과거 행 value개
            prev_t = items[idx - 1]["t"] if idx > 0 and items[idx - 1]["t"] is not None else items[idx]["t"] - pd.Timedelta(seconds=5)
            off = 0.0 if kind == "tail" else 1.0
            block = []
            for j in range(1, int(value) + 1):
                b = dict(items[idx - 1] if idx > 0 else items[idx])       # 센서 값은 앞 기록 끝 행의 사본(과거 자료)
                b["t"] = prev_t + pd.Timedelta(seconds=off + 0.1 * j); b["err"] = True; b["extra"] = True; b["nan"] = False
                block.append(b)
            items[idx + 1:idx + 1] = block
        elif kind == "move":
            it = items.pop(idx); it["err"] = True
            items.insert(min(idx + int(value), len(items)), it)
        else:
            raise ValueError(kind)
    src = np.array([it["src"] for it in items])
    out = D.inputs_only(frame).iloc[src].copy().reset_index(drop=True)
    out[D.TIME] = [it["t"].strftime(FMT) if it["t"] is not None else "" for it in items]
    for k, it in enumerate(items):
        if it["nan"]:
            out.loc[k, D.SENSORS[0]] = np.nan
    return out, np.array([it["err"] for it in items]), src


def summarize(pred, err=None, base_pred=None):
    """행 단위 예측 요약. err는 오류(튄·끼운) 행 표시: 그 행 자체의 경보·알림은 본체에서 뺀다."""
    err = np.zeros(len(pred), bool) if err is None else np.asarray(err, bool)
    ev = pred.time_order_event.to_numpy()
    alarm = pred.alarm.eq(1).to_numpy()
    body = alarm & ~err
    inc = pred.incident_id.to_numpy()
    out = dict(rows=len(pred), held=int((pred.status == "bad_time_order").sum()),
               c2=int((ev == 2).sum()), c3=int((ev == 3).sum()), c4=int((ev == 4).sum()),
               alarms=int(alarm.sum()), body_alarms=int(body.sum()),
               incidents=int(len(set(inc[inc > 0]))), body_incidents=int(len(set(inc[body]))),
               starts=int(pred.incident_notification.sum()), escalations=int(pred.incident_escalation.sum()),
               body_starts=int(pred.incident_notification.to_numpy()[~err].sum()),
               body_escalations=int(pred.incident_escalation.to_numpy()[~err].sum()))
    per = pred[pred.incident_id.gt(0)].groupby("incident_id")[["incident_notification", "incident_escalation"]].sum()
    out["dup_alerts"] = int((per > 1).any(axis=1).sum()) if len(per) else 0
    return out


def stream_predict(mdl, frame, chunks):
    """chunks: 정수(고정 크기) 또는 크기 목록."""
    det = StreamDetector(mdl)
    parts, i = [], 0
    sizes = chunks if isinstance(chunks, (list, tuple, np.ndarray)) else None
    k = 0
    while i < len(frame):
        n = int(sizes[k % len(sizes)]) if sizes is not None else int(chunks)
        parts.append(det.push(frame.iloc[i:i + n]))
        i += n; k += 1
    return pd.concat(parts, ignore_index=True)


def same(a, b):
    try:
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), rtol=1e-11, atol=1e-11)
        return True
    except AssertionError:
        return False


def quality(pred):
    """사건 대기열의 품질 시간창(사건별 suspect_from/to/open)."""
    q = cases(pred)
    if not len(q):
        return []
    inc = incidents(q, pred)
    return list(zip(inc.incident_id, inc.suspect_from, inc.suspect_to, inc.suspect_open))
