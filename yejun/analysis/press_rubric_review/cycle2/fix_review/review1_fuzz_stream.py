"""검토 1: 무작위 시각 오류(미래·과거 튐, 시계 후퇴, 중복, 결측, 센서 오류, 흔들림)에서 일괄 predict와 StreamDetector가 같은가,
그리고 앞부분 예측이 뒤 자료에 따라 바뀌지 않는가(인과성).

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review1_fuzz_stream.py [시행 수]
"""
import os
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, layout, load_bundle, StreamDetector

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
POOL = pd.concat([D.inputs_only(abnormal).iloc[:300], D.inputs_only(normal).iloc[9000:9300]], ignore_index=True)
T0 = pd.Timestamp("2022-07-14 00:00:00")


def random_frame(rng):
    n = int(rng.integers(20, 70))
    start = int(rng.integers(0, len(POOL) - n))
    f = POOL.iloc[start:start + n].copy().reset_index(drop=True)
    t, times = 0.0, []
    for i in range(n):
        r = rng.random()
        if r < .04:   step = 3600.0            # 미래로 튐(뒤 행이 이어받음)
        elif r < .07: step = -3600.0           # 과거로
        elif r < .09: step = 0.0               # 동률
        elif r < .12: step = -0.1              # 역순
        elif r < .15: step = .1 + rng.choice([-.05, .05])   # 허용 밖 흔들림
        else:         step = .1 + rng.normal(0, .004)
        if r < .04 and rng.random() < .7:
            times.append(t + 3600.0)            # 한 행만 미래로 튀고 시간축은 그대로
            continue
        t += step
        times.append(t)
    f[D.TIME] = [(T0 + pd.Timedelta(seconds=s)).strftime("%Y-%m-%d %H:%M:%S.%f") if rng.random() > .05 else "" for s in times]
    bad = rng.random(n) < .04
    f.loc[bad, D.SENSORS[0]] = np.nan
    return f


def stream(frame, chunks):
    det = StreamDetector(MODEL)
    parts, i, k = [], 0, 0
    while i < len(frame):
        c = int(chunks[k % len(chunks)]); k += 1
        parts.append(det.push(frame.iloc[i:i + c])); i += c
    return pd.concat(parts, ignore_index=True)


def equal(a, b):
    try:
        pd.testing.assert_frame_equal(a, b, rtol=1e-11, atol=1e-11)
        return True
    except AssertionError:
        return False


def main(trials):
    rng = np.random.default_rng(7)
    stream_fail, causal_fail, held_total, spikes = [], [], 0, 0
    for trial in range(trials):
        f = random_frame(rng)
        pred = MODEL.predict(f)
        held_total += int(pred.status.eq("bad_time_order").sum())
        for chunks in ([1], [2], [3], [5], [7], [8], [128], list(rng.integers(1, 12, size=40))):
            if not equal(stream(f, chunks), pred):
                stream_fail.append((trial, chunks[:3]))
                break
        if trial % 4 == 0:
            for s in range(1, len(f) + 1):
                if not equal(MODEL.predict(f.iloc[:s]), pred.iloc[:s]):
                    causal_fail.append((trial, s)); break
    print(f"시행 {trials}회, 판정 보류 행 합 {held_total}")
    print("일괄≠스트림:", stream_fail[:10], "건수", len(stream_fail))
    print("인과성 위반(앞부분 예측이 바뀜):", causal_fail[:10], "건수", len(causal_fail))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 120)
