"""검토 3: 수정 커밋(110afa2)의 무작위 시각 오류 입력에서 일괄 predict와 StreamDetector가 같은가, 앞부분 예측이 뒤 자료에 따라
바뀌지 않는가(인과성), 그리고 사건마다 시작·격상 알림이 한 번씩인가(사건 불변식).

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_fuzz_stream.py [시행 수]
검토 1의 무작위 입력(review1_fuzz_stream.py)에 작은 앞 튐(0.3·2·5·30초)·이웃 행 맞바뀜·튄 행 뒤 오류 행을 더하고, 경보가 잦은 이상 자료를 더 많이 쓴다.
"""
import os
import sys
from collections import Counter
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, load_bundle, StreamDetector, ORDER_SPIKE_SKIPPED

MODEL = load_bundle(ENV / "press_guard" / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
POOL = pd.concat([D.inputs_only(abnormal), D.inputs_only(normal).iloc[9000:9300]], ignore_index=True)
T0 = pd.Timestamp("2022-07-14 00:00:00")


def random_frame(rng):
    n = int(rng.integers(20, 70))
    start = int(rng.integers(0, len(POOL) - n))
    f = POOL.iloc[start:start + n].copy().reset_index(drop=True)
    t, times, kinds = 0.0, [], []
    i = 0
    while len(times) < n:
        r = rng.random()
        if r < .05:                                   # 한 행만 앞으로 튐(크기 무작위), 시간축은 그대로
            times.append(t + float(rng.choice([.3, 2.0, 5.0, 30.0, 3600.0]))); kinds.append("spike")
            if rng.random() < .3 and len(times) < n:  # 튄 행 바로 뒤에 시각 결측 한 행
                times.append(None); kinds.append("nat_after_spike")
            continue
        if r < .08 and len(times) + 1 < n:            # 이웃 두 행 맞바뀜
            times += [t + .2, t + .1]; kinds += ["swap", "swap"]; t += .2; continue
        if r < .10:   step = -3600.0
        elif r < .12: step = 0.0
        elif r < .14: step = -0.1
        elif r < .17: step = .1 + rng.choice([-.05, .05])
        elif r < .20: step = float(rng.choice([1.5, 4.0, 16.0]))     # 기록 사이 공백
        else:         step = .1 + rng.normal(0, .004)
        t += step; times.append(t); kinds.append("normal")
    times = times[:n]
    f[D.TIME] = [(T0 + pd.Timedelta(seconds=s)).strftime("%Y-%m-%d %H:%M:%S.%f") if (s is not None and rng.random() > .04) else "" for s in times]
    bad = rng.random(n) < .03
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
    rng = np.random.default_rng(20260929)
    stream_fail, causal_fail, dup = [], [], Counter()
    skipped_total, trials_with_dup, examples = 0, 0, []
    for trial in range(trials):
        f = random_frame(rng)
        pred = MODEL.predict(f)
        skipped_total += int((pred.time_order_event == ORDER_SPIKE_SKIPPED).sum())
        g = pred[pred.incident_id.gt(0)].groupby("incident_id")
        n_dup = int((g.incident_notification.sum() > 1).sum()); e_dup = int((g.incident_escalation.sum() > 1).sum())
        dup["사건 시작 두 번 이상"] += n_dup; dup["격상 두 번 이상"] += e_dup
        if n_dup or e_dup:
            trials_with_dup += 1
            if len(examples) < 5:
                examples.append((trial, n_dup, e_dup))
        for chunks in ([1], [2], [3], [5], [7], [8], [128], list(rng.integers(1, 12, size=40))):
            if not equal(stream(f, chunks), pred):
                stream_fail.append((trial, chunks[:3]))
                break
        if trial % 5 == 0:
            for s in range(1, len(f) + 1):
                if not equal(MODEL.predict(f.iloc[:s]), pred.iloc[:s]):
                    causal_fail.append((trial, s)); break
    print(f"시행 {trials}회, 튐 건너뜀(ORDER_SPIKE_SKIPPED) 행 합 {skipped_total}")
    print("일괄≠스트림:", stream_fail[:10], "건수", len(stream_fail))
    print("인과성 위반(앞부분 예측이 바뀜):", causal_fail[:10], "건수", len(causal_fail), f"(시행 {len(range(0, trials, 5))}개에서 모든 prefix)")
    print("사건 불변식 위반(사건 수):", dict(dup), f"| 위반이 있는 시행 {trials_with_dup}/{trials} | 예(시행, 시작 중복 사건, 격상 중복 사건): {examples}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
