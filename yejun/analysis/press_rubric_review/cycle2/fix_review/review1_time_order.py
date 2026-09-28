"""검토 1: 수집 시각 순서(TimeOrder)·일괄/스트림 동일성·인과성 반례 시험.

사본에서만 실행한다(저장소에서 실행하지 않는다):
    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_time_order.py
사본의 yejun 폴더에는 press_guard/, press_submission/(원본 CSV 포함)이 있어야 한다.
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))

import numpy as np
import pandas as pd

from model import (D, TimeOrder, timestamp_order, layout, load_bundle, StreamDetector, cases, incidents,
                   time_order_events, timing_warning)

T0 = pd.Timestamp("2022-07-14 00:00:00")
normal, abnormal, _ = D.load()
MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
split = D.split_normal(normal, D.segments(normal), "B")
TEST = D.inputs_only(split["test"]).reset_index(drop=True)
REC = layout(TEST)[1]
CLEAN = TEST[REC == 0].reset_index(drop=True)          # 경보 없는 정상 기록(50행)
FALSE_ALARM = TEST[REC == 3].reset_index(drop=True)    # B 오경보 기록


def fmt(t):
    return "" if t is None else pd.Timestamp(t).strftime("%Y-%m-%d %H:%M:%S.%f")


def frame_with_times(times, source=None):
    """times(Timestamp 또는 None) 목록에 센서 값을 붙인다. source 행을 순환해 쓴다."""
    src = (source if source is not None else pd.concat([CLEAN] * 20, ignore_index=True)).reset_index(drop=True)
    out = src.iloc[np.arange(len(times)) % len(src)].copy().reset_index(drop=True)
    out[D.TIME] = [fmt(t) if t is not None else "" for t in times]
    return out


def held_of(times):
    ts = pd.to_datetime(pd.Series([fmt(t) if t is not None else "" for t in times]), format="mixed", utc=True, errors="coerce")
    return timestamp_order(ts)[0]


def stream(frame, chunks):
    det = StreamDetector(MODEL)
    parts, i = [], 0
    for c in chunks:
        if i >= len(frame):
            break
        parts.append(det.push(frame.iloc[i:i + c]))
        i += c
    while i < len(frame):
        parts.append(det.push(frame.iloc[i:i + 1])); i += 1
    return pd.concat(parts, ignore_index=True)


def same(a, b):
    try:
        pd.testing.assert_frame_equal(a, b, rtol=1e-11, atol=1e-11)
        return True, ""
    except AssertionError as exc:
        return False, str(exc).splitlines()[0][:160]


def check_stream_and_causality(frame, pred, rng, stops=None):
    res = {}
    for name, chunks in (("1", [1] * len(frame)), ("7", [7] * len(frame)), ("128", [128] * len(frame)),
                         ("random", list(rng.integers(1, 13, size=len(frame))))):
        ok, why = same(stream(frame, chunks), pred)
        res[f"stream_{name}"] = ok if ok else f"DIFF {why}"
    stops = stops if stops is not None else range(1, len(frame) + 1)
    bad = []
    for s in stops:
        ok, _ = same(MODEL.predict(frame.iloc[:s]), pred.iloc[:s])
        if not ok:
            bad.append(s)
    res["causal_prefix_fail"] = bad[:5]
    return res


def report(title, times, source=None, rng=None, stops=None, expect_held=None):
    frame = frame_with_times(times, source)
    pred = MODEL.predict(frame)
    held = np.flatnonzero(pred.status.eq("bad_time_order")).tolist()
    print(f"\n### {title}")
    print("  rows", len(frame), "| bad_time_order rows:", held, "| expected by stated intent:", expect_held)
    print("  status:", "".join({"ok": ".", "bad_time_order": "H", "bad_timestamp": "T", "bad_value": "V"}[s] for s in pred.status))
    print("  record_id:", pred.record_id.tolist()[:40], "..." if len(pred) > 40 else "")
    print("  time_order_events(held, resumed):", time_order_events(pred), "| warning:", timing_warning(pred)[:140])
    if rng is not None:
        print("  stream/causality:", check_stream_and_causality(frame, pred, rng, stops))
    return frame, pred


def main():
    rng = np.random.default_rng(20260929)
    k = lambda i: T0 + pd.Timedelta(seconds=0.1 * i)
    H = pd.Timedelta(hours=1)

    report("S1 첫 행 미래 튐(+1h)", [T0 + H] + [k(i) for i in range(12)], rng=rng, expect_held="명세상 튄 행만 건너뜀; 테스트 문서는 첫 행이면 2행 보류")
    report("S2 중간 한 행 미래 튐(+1h)", [k(i) for i in range(5)] + [T0 + H] + [k(i) for i in range(5, 15)], rng=rng, expect_held=[])
    report("S3 두 행 연속 미래 튐", [k(i) for i in range(5)] + [T0 + H, T0 + H + pd.Timedelta(seconds=.1)] + [k(i) for i in range(5, 15)], rng=rng,
           expect_held="명세 문구상 '한 행' 규칙 밖 → 이른 행 보류 후 3행째 새 기준(보류 2행)")
    report("S4 과거로 한 행 튐(-1h)", [k(i) for i in range(5)] + [T0 - H] + [k(i) for i in range(5, 15)], rng=rng, expect_held=[5])
    report("S5 시계 영구 후퇴(-1h)", [k(i) for i in range(10)] + [T0 - H + pd.Timedelta(seconds=.1 * j) for j in range(10)], rng=rng, expect_held=[10, 11])
    report("S6 시각 결측·센서 오류 섞임", [k(0), k(1), None, k(3), k(4), T0 - H, None, T0 - H + pd.Timedelta(seconds=.2), T0 - H + pd.Timedelta(seconds=.3),
                                      T0 - H + pd.Timedelta(seconds=.4), k(5), k(6)], rng=rng, expect_held="(결측 행은 상태 불변)")
    irregular = np.cumsum([0, .13, .07, .15, .05, .14, .06, .13])
    report("S7 불규칙 간격의 과거 시각", [k(i) for i in range(10)] + [T0 - H + pd.Timedelta(seconds=float(s)) for s in irregular] + [k(i) for i in range(10, 14)],
           rng=rng, expect_held=list(range(10, 18)))
    report("S8 동률 시각", [k(0), k(1), k(2), k(2), k(3), k(3), k(3), k(4)], rng=rng, expect_held=[])

    # S9 순서가 뒤집힌 한 기록(가장 늦은 행부터 도착): 명세 "기준보다 이른 행은 판정 보류"면 첫 행 뒤 9행이 보류돼야 한다.
    rev = [k(i) for i in range(5)] + [k(i) for i in range(14, 4, -1)] + [k(i) for i in range(15, 20)]
    report("S9 한 기록이 역순으로 도착(14→5)", rev, rng=rng, expect_held=list(range(6, 15)))
    # S10 미래 튐 뒤 감소하는 시각들
    dec = [k(i) for i in range(5)] + [T0 + H, T0 + pd.Timedelta(minutes=30), T0 + pd.Timedelta(minutes=20), T0 + pd.Timedelta(minutes=10)] + [k(i) for i in range(5, 10)]
    report("S10 미래 튐 뒤 감소 시각 3행(+30m,+20m,+10m)", dec, rng=rng, expect_held="적어도 +20m·+10m(기준 +30m보다 이름) 보류")
    # S11 이웃 두 행 맞바뀜
    report("S11 이웃 행 맞바뀜(t3,t2)", [k(0), k(1), k(3), k(2), k(4), k(5)], rng=rng, expect_held="명세 해석: t3를 튄 행으로 보면 보류 없음")

    # 순수 TimeOrder 무작위 대조: 인과성(prefix) 확인
    viol = 0
    for trial in range(300):
        n = int(rng.integers(5, 40))
        base = np.cumsum(rng.choice([.1, .1, .1, .1, .1, -3600, 3600, .0, .13, -.1], size=n))
        times = [T0 + pd.Timedelta(seconds=float(s)) if rng.random() > .08 else None for s in base]
        full = held_of(times)
        for s in range(1, n + 1):
            if not np.array_equal(held_of(times[:s]), full[:s]):
                viol += 1
                break
    print("\n### TimeOrder prefix causality violations in 300 random sequences:", viol)


if __name__ == "__main__":
    main()
