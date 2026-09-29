"""검토 7: 전수 모의(review7_sweep.py) 결과를 두 판 사이에서 위치·오류별로 맞대어, c7d8bba가 3c6fbf3보다 나빠진 곳(보류·분할·추가 시작·경보 감소)을 센다.

    python review7_sweep_compare.py <c7d8bba csv> <3c6fbf3 csv>
"""
import sys
import pandas as pd

a, b = pd.read_csv(sys.argv[1]), pd.read_csv(sys.argv[2])
key = ["base", "pos", "kind", "value"]
m = a.merge(b, on=key, suffixes=("", "_old"))
print(f"대조 {len(m)}건 (c7d8bba {len(a)}, 3c6fbf3 {len(b)})")
for col in ("split", "held", "extra_starts", "body_extra_starts", "alarm_loss", "dup_alerts"):
    worse = m[m[col] > m[col + "_old"]]
    better = m[m[col] < m[col + "_old"]]
    print(f"{col:18s}: 나빠짐 {len(worse):5d}건 · 나아짐 {len(better):5d}건")
    if len(worse):
        g = worse.groupby(["kind", "value", "cls"]).size()
        print("    나빠진 곳:", g.to_dict())
for label, x in (("c7d8bba", a), ("3c6fbf3", b)):
    ab = x[x.base == "ab"]
    print(f"{label}: 이상 파일 전수 {len(ab)}건 · 사건 분할 {int(ab.split.sum())} · 본체 추가 시작 {int((ab.body_extra_starts > 0).sum())} · 중복 알림 {int(ab.dup_alerts.sum())} · "
          f"보류 생긴 곳 {int((ab.held > 0).sum())} · 보류 합 {int(ab.held.sum())} · 경보 감소 합 {int(ab.alarm_loss.sum())}")
    s = ab[ab.split > 0].groupby(["kind", "value"]).size()
    if len(s):
        print("    분할:", s.to_dict())
