"""검토 7: review7_counter.py 결과 요약(오류 종류·크기별 사건 분할·알림 추가·보류)."""
import sys
import pandas as pd

d = pd.read_csv(sys.argv[1], dtype={"value": str})
names = dict(step="시계 뒤로 재설정(그 행부터 끝까지)", rexmit="앞 n행 묶음 재전송(그 행 뒤)", multi="n행 연속 튐(같은 크기)",
             late1="정상 마지막 행이 이상 첫 행 뒤에 도착", late2rev="정상 마지막 두 행이 이상 첫 행 뒤에 역순 도착",
             onset_spike="이상 첫 행 +Δ 튐", onset_step="이상 첫 행 뒤 시계 뒤로 재설정", onset_backlog="이상 첫 행 뒤 밀린 자료 10행(공백 안 +1초부터)",
             onset_tail="이상 첫 행 뒤 늦은 꼬리 n행(앞 기록 끝 +0.1초부터)")
for (k, v), g in d.groupby(["kind", "value"], sort=False):
    n = len(g)
    print(f"{names[k]:34s} {v:>14s}: {n:4d}곳 · 사건 분할 {int(g.split.sum()):4d}({g.split.mean():.0%}) · 시작 추가 {int((g.extra_starts > 0).sum()):4d} · "
          f"격상 추가 {int((g.extra_esc > 0).sum()):4d} · 보류 중앙 {g.held.median():g}·최대 {g.held.max()} · 부호3 {int((g.c3 > 0).sum())} · 부호4 {int((g.c4 > 0).sum())} · 부호2 {int((g.c2 > 0).sum())}")
