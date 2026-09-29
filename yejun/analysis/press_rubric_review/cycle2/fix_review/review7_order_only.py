"""검토 7 (f): 보류 행 수가 설명(기록 안 0행, 기록 끝 튐 2행)과 맞는가. 모델 없이 사본의 TimeOrder만 돌린다.
대회 정상 파일 20,000행(600기록, 3행 미만 기록 17개)의 모든 기록 끝 행·기록 첫 행과 기록 안 무작위 2,000행에 한 행 튐(대체)을 넣고,
튄 행 뒤 보류 행 수와 확인 부호(2·4)를 센다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_order_only.py
"""
from collections import Counter

from review7_lib import *  # noqa: F401,F403

normal, _ = data()
T = list(pd.to_datetime(normal[D.TIME], format="mixed", utc=True))
seg = D.segments(normal)
n = len(T)
first = np.flatnonzero(np.r_[True, seg[1:] != seg[:-1]])
last = np.r_[first[1:] - 1, n - 1]
lens = np.diff(np.r_[first, n])
rng = np.random.default_rng(3)
interior = rng.choice(np.setdiff1d(np.arange(1, n - 1), np.r_[first, last]), 2000, replace=False)
WIN = 400


def run(i, delta, mode):
    """i행 근처만 새 상태로 돌린다(앞 3행으로 기준을 잡음). 반환: (튄 행 뒤 보류 행 수, 확인 부호, 확인까지 행 수)."""
    lo = max(0, i - 3)
    seq = T[lo:i + WIN]
    j = i - lo
    if mode == "replace":
        seq = seq[:j] + [seq[j] + pd.Timedelta(seconds=delta)] + seq[j + 1:]
        after = j + 1
    else:
        seq = seq[:j + 1] + [seq[j] + pd.Timedelta(seconds=delta)] + seq[j + 1:]
        after = j + 2
    order = M.TimeOrder()
    codes = [order.step(t) for t in seq]
    tail = codes[after:]
    held = 0; confirm = None
    for k, c in enumerate(tail):
        if c == M.ORDER_HELD:
            held += 1
        elif c in (M.ORDER_SPIKE_SKIPPED, getattr(M, "ORDER_SPIKE_REANCHOR", 4), M.ORDER_REANCHOR):   # 옛 판에는 부호 4가 없다
            confirm = (c, k); break
        elif c == M.ORDER_OK and held and not any(x == M.ORDER_HELD for x in tail[k + 1:k + 4]):
            confirm = ("pass", k); break
        elif c == M.ORDER_OK and not held:
            confirm = ("none", k); break
    return held, confirm


print(f"# 판: {ENV.parent.name} · 정상 파일 {n}행 {len(first)}기록 · 3행 미만 기록 {int((lens < 3).sum())}개 · 기록 안 표본 {len(interior)}곳")
for label, positions, mode in (("기록 안(대체)", interior, "replace"), ("기록 안(끼어듦)", interior, "insert"),
                               ("기록 끝 행(대체)", last[:-1], "replace"), ("기록 끝 뒤(끼어듦)", last[:-1], "insert"),
                               ("기록 첫 행(대체)", first[1:], "replace")):
    for delta in (0.13, 0.25, 0.5, 2, 5, 16.7, 30, 60.1, 600, 3600):
        held = Counter(); conf = Counter(); worst = (0, None)
        for i in positions:
            h, c = run(int(i), delta, mode)
            held[h] += 1
            conf[c[0] if c else "끝까지"] += 1
            if h > worst[0]:
                worst = (h, int(i))
        dist = ", ".join(f"{k}행 {v}" for k, v in sorted(held.items()))
        cf = ", ".join(f"{({2: '부호2', 3: '부호3', 4: '부호4'}).get(k, k)} {v}" for k, v in conf.most_common())
        print(f"{label:12s} +{delta:<6g}: 보류 분포 [{dist}] · 결말 [{cf}] · 최대 보류 {worst[0]}행(행 {worst[1]})")
