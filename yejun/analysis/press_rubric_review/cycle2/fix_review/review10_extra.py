"""검토 10 보조: 같은 시각 중복 행이 '유효 행 8행' 정상 복귀 근거를 부풀리는가.
[이상 11 →1.5초→ 정상 q0 m행 →1.5초→ 이상 12]에서 m = 5~7(원자료는 8행 미만이라 한 사건 (1,1,1))의 정상 행 일부를 같은 시각으로 한 번 더 보낸다.
6차 규칙에서 중복 행은 같은 단위로 이어지고 IncidentTracker는 그 행도 유효 행으로 센다. 판마다 같은 입력.

    REVIEW_ENV=<사본 yejun> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review10_extra.py
"""
import review9_lib as L

M = L.M
ver = ("a489001" if hasattr(M.CollectionUnits(), "extra") else "other") if hasattr(M, "CollectionUnits") else "c7d8bba"
print(f"# 판 {ver} · 사본 {L.ENV}")
mdl = L.model()
(r11, r12, r13), (q0, q1), mag = L.parts()
for m in (5, 6, 7, 8):
    f, st = L.chain([r11, q0.iloc[:m], r12], gap=1.5)
    row = [f"정상 {m}행 원자료 {L.summ(mdl.predict(f))}"]
    for k in (1, 2, 3):
        g = f
        for i in range(k):                       # 정상 기록의 앞 k행을 각각 한 번 더(같은 시각)
            g = L.dup(g, st[1] + 2 * i)
        row.append(f"중복 {k}행 {L.summ(mdl.predict(g))}")
    print(" · ".join(row), flush=True)
