"""검토 5: 3c6fbf3의 무작위 시각 오류 입력에서 일괄 predict와 StreamDetector가 같은가(청크 1·2·3·5·7·8·128·무작위),
앞부분 예측이 뒤 자료에 따라 바뀌지 않는가(인과성), 사건마다 시작·격상 알림이 한 번 이하인가(사건 불변식).

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_fuzz_stream.py [시행 수]
검토 3의 무작위 입력(review3_fuzz_stream.py)에 이번 규칙의 경계를 더했다: 표본 자리를 차지한 튐(행 시각만 +Δ), 60초 넘는 수집 중단,
중단 뒤 공백 안의 과거 행, 튄 행의 재전송(동률), 60초 경계(59.9·60.0·60.1초) 튐.
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
    n = int(rng.integers(20, 90))
    start = int(rng.integers(0, len(POOL) - n))
    f = POOL.iloc[start:start + n].copy().reset_index(drop=True)
    t, times = 0.0, []
    while len(times) < n:
        r = rng.random()
        if r < .04:                                   # 끼운 튐: 한 행만 앞으로, 시간축은 그대로
            times.append(t + float(rng.choice([.3, 2.0, 5.0, 30.0, 59.9, 60.0, 60.1, 3600.0])))
            if rng.random() < .25 and len(times) < n:
                times.append(times[-1])               # 튄 행 재전송(동률)
            elif rng.random() < .3 and len(times) < n:
                times.append(None)                    # 튄 행 뒤 시각 결측
            continue
        if r < .08:                                   # 표본 자리를 차지한 튐: 이 표본의 시각만 +Δ
            t += .1
            times.append(t + float(rng.choice([.3, 1.0, 5.0, 30.0, 59.9, 60.1, 3600.0])))
            continue
        if r < .10 and len(times) + 1 < n:            # 이웃 두 행 맞바뀜
            times += [t + .2, t + .1]; t += .2; continue
        if r < .12 and len(times) + 1 < n:            # 60초 넘는 수집 중단 뒤 새 기록 첫 행 다음에 공백 안의 과거 행
            gap = float(rng.choice([30.0, 61.0, 120.0, 600.0]))
            times += [t + gap, t + float(rng.uniform(.3, min(gap, 60.0)))]; t += gap; continue
        if r < .13:   step = -3600.0
        elif r < .15: step = 0.0
        elif r < .16: step = -0.1
        elif r < .19: step = .1 + rng.choice([-.05, .05])
        elif r < .23: step = float(rng.choice([1.5, 4.0, 16.0, 61.0, 300.0]))   # 기록 사이 공백(60초 넘는 중단 포함)
        else:         step = .1 + rng.normal(0, .004)
        t += step; times.append(t)
    times = times[:n]
    f[D.TIME] = [(T0 + pd.Timedelta(seconds=s)).strftime("%Y-%m-%d %H:%M:%S.%f") if (s is not None and rng.random() > .03) else "" for s in times]
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
    rng = np.random.default_rng(20260930)
    stream_fail, causal_fail, dup, errors = [], [], Counter(), []
    skipped_total, trials_with_dup, examples = 0, 0, []
    for trial in range(trials):
        f = random_frame(rng)
        try:
            pred = MODEL.predict(f)
        except Exception as exc:                      # _prune 등으로 사건 상태가 사라지면 KeyError
            errors.append((trial, repr(exc))); continue
        skipped_total += int((pred.time_order_event == ORDER_SPIKE_SKIPPED).sum())
        g = pred[pred.incident_id.gt(0)].groupby("incident_id")
        n_dup = int((g.incident_notification.sum() > 1).sum()); e_dup = int((g.incident_escalation.sum() > 1).sum())
        no_start = int((g.incident_notification.sum() == 0).sum())
        dup["사건 시작 두 번 이상"] += n_dup; dup["격상 두 번 이상"] += e_dup; dup["시작 알림 없는 사건"] += no_start
        if n_dup or e_dup or no_start:
            trials_with_dup += 1
            if len(examples) < 5:
                examples.append((trial, n_dup, e_dup, no_start))
        for chunks in ([1], [2], [3], [5], [7], [8], [128], list(rng.integers(1, 12, size=40))):
            if not equal(stream(f, chunks), pred):
                stream_fail.append((trial, chunks[:3]))
                break
        if trial % 5 == 0:
            for s in range(1, len(f) + 1):
                if not equal(MODEL.predict(f.iloc[:s]), pred.iloc[:s]):
                    causal_fail.append((trial, s)); break
    print(f"시행 {trials}회, 튐 건너뜀(ORDER_SPIKE_SKIPPED) 행 합 {skipped_total}, 예외 {len(errors)} {errors[:3]}")
    print("일괄≠스트림:", stream_fail[:10], "건수", len(stream_fail))
    print("인과성 위반(앞부분 예측이 바뀜):", causal_fail[:10], "건수", len(causal_fail), f"(시행 {len(range(0, trials, 5))}개에서 모든 prefix)")
    print("사건 불변식 위반(사건 수):", dict(dup), f"| 위반이 있는 시행 {trials_with_dup}/{trials} | 예(시행, 시작 중복, 격상 중복, 시작 없음): {examples}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 150)
