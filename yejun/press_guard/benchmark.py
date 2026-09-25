"""v2 처리시간 벤치마크(outputs/benchmark.json). 분할 A 평가 스트림(정상 평가 + 이상, 4,690행)을 묶음 크기별로 순차 추론한다.

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/benchmark.py

CPU 한 스레드 기준의 참고치다. 실제 설비의 수집 주기(0.1초)와 비교하려고 호출당 지연 p50/p95/max를 함께 기록한다.
"""
from pathlib import Path
import argparse
import json
import platform
import time

import numpy as np
import pandas as pd

from model import GuardModel, StreamDetector, D, HERE


def run_case(model, frame, chunk, repeats):
    latencies, totals = [], []
    for _ in range(repeats):
        det = StreamDetector(model)
        t_all = time.perf_counter()
        for i in range(0, len(frame), chunk):
            t0 = time.perf_counter()
            det.push(frame.iloc[i:i + chunk])
            latencies.append((time.perf_counter() - t0) * 1000)
        totals.append(time.perf_counter() - t_all)
    lat = np.asarray(latencies)
    best = min(totals)
    return dict(label=("전체" if chunk >= len(frame) else f"{chunk}행"), chunk=int(min(chunk, len(frame))), rows=int(len(frame)), calls=int(len(lat) // repeats),
                repeats=repeats, seconds_best=round(best, 4), rows_per_second=round(len(frame) / best, 1),
                p50_ms=round(float(np.percentile(lat, 50)), 3), p95_ms=round(float(np.percentile(lat, 95)), 3), max_ms=round(float(lat.max()), 3))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifacts", type=Path, default=HERE / "artifacts")
    ap.add_argument("--out", type=Path, default=HERE / "outputs")
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    model = GuardModel.load(args.artifacts / "guard_A.json")
    normal, abnormal, _ = D.load()
    split = D.split_normal(normal, D.segments(normal), "A")
    frame = pd.concat([split["test"], abnormal], ignore_index=True)
    runs = [run_case(model, frame, chunk, args.repeats) for chunk in (1, 8, 128, len(frame))]
    t0 = time.perf_counter(); model.predict(frame); batch = time.perf_counter() - t0
    result = dict(version="press-guard-v2.0", split="A", rows=int(len(frame)), sampling_seconds=D.DT, runs=runs,
                  batch_predict_seconds=round(batch, 4), environment=dict(D.environment(), processor=platform.processor(), omp_num_threads=__import__("os").environ.get("OMP_NUM_THREADS")),
                  note="CPU 한 스레드 참고치. 1행 묶음의 호출당 지연이 수집 주기 0.1초보다 작아야 행 단위 실시간 처리가 가능하다.")
    D.dump_json(result, args.out / "benchmark.json")
    print(pd.DataFrame(runs).to_string(index=False))
    print(f"전체 일괄 predict {batch:.3f}초 → {args.out / 'benchmark.json'}")


if __name__ == "__main__":
    main()
