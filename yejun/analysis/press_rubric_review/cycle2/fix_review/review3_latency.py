"""검토 3: 수정 커밋(110afa2)의 사인 투영 캐시(_HATS.setdefault(win, stable_hats(win)))가 실제로 캐시되는가, 1행 스트림 지연.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review3_latency.py [행 수]
dict.setdefault는 기본값 인수를 매번 계산하므로 stable_hats(win)(주파수 1,001개 pinv)가 sine_score 호출마다 다시 돈다.
benchmark.py와 같은 입력(분할 A 평가 스트림)의 앞 N행을 1행씩 push해 호출당 지연을 잰 뒤, stable_hats에 lru_cache를 씌워 다시 잰다.
두 경우의 예측이 같은지도 본다.
"""
import os, sys, time
from functools import lru_cache
from pathlib import Path
ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np, pandas as pd
import model as M
from model import D, GuardModel, StreamDetector

n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
model = GuardModel.load(ENV / "press_guard" / "artifacts" / "guard_A.json")
normal, abnormal, _ = D.load()
split = D.split_normal(normal, D.segments(normal), "A")
frame = pd.concat([split["test"], abnormal], ignore_index=True).iloc[:n]


def measure():
    det = StreamDetector(model); lat, parts = [], []
    for i in range(len(frame)):
        t0 = time.perf_counter(); parts.append(det.push(frame.iloc[i:i + 1])); lat.append((time.perf_counter() - t0) * 1000)
    t0 = time.perf_counter(); model.predict(frame); batch = time.perf_counter() - t0
    lat = np.asarray(lat[8:])      # 처음 몇 호출(임포트·워밍업) 제외
    return pd.concat(parts, ignore_index=True), np.percentile(lat, 50), np.percentile(lat, 95), batch


t0 = time.perf_counter(); M.stable_hats(8); print(f"stable_hats(8) 한 번: {(time.perf_counter() - t0) * 1000:.1f} ms (주파수 {len(M.FREQS)}개)")
a, p50a, p95a, ba = measure()
print(f"현재 코드: 1행 push 호출당 p50 {p50a:.1f} ms · p95 {p95a:.1f} ms | {n}행 일괄 predict {ba:.3f}초")
M.stable_hats = lru_cache(maxsize=None)(M.stable_hats)
b, p50b, p95b, bb = measure()
print(f"stable_hats에 lru_cache: 1행 push 호출당 p50 {p50b:.1f} ms · p95 {p95b:.1f} ms | {n}행 일괄 predict {bb:.3f}초")
pd.testing.assert_frame_equal(a, b, rtol=0, atol=0)
print("두 경우 스트림 예측이 비트 단위로 같다")
