"""검토 7: 확인되지 않은 작은 시각 오류가 품질 의심 시간창(suspect_from/to)을 좁히는 크기. 맥락 자료(정상 6기록 → 3초 → 이상 파일 → 3초 → 정상 6기록)의
이상 마지막 행·이상 직전 정상 마지막 행에 +δ초를 넣는다. 원자료 창은 10:51:04.943 ~ 10:53:56.540이다.

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review7_window.py
"""
from review7_scenarios_ctx import *  # noqa: F401,F403

base = quality(MDL.predict(CF))[0]
print(f"# 판: {ENV.parent.name} · 원자료 창 {base[1][11:23]} ~ {base[2][11:23]}")
for label, row in (("이상 마지막 행", N1 - 1), ("이상 직전 정상 마지막 행", N0 - 1)):
    for d in (0.021, 0.03, 0.13, 0.5, 1, 2, 2.9, 3.1, 5):
        f, err, _ = build(CF, TC, [("replace", row, d)])
        p = MDL.predict(f)
        q = quality(p)
        s = summarize(p, err)
        a, b = pd.Timestamp(q[0][1]) if q[0][1] else None, pd.Timestamp(q[0][2]) if q[0][2] else None
        lost = ((pd.Timestamp(base[2]) - b).total_seconds() if b is not None and row == N1 - 1 else
                (a - pd.Timestamp(base[1])).total_seconds() if a is not None else float("nan"))
        print(f"{label} +{d:<5g}: 보류 {s['held']} 부호4 {s['c4']} · 창 {q[0][1][11:23] or '열림'} ~ {q[0][2][11:23] or '열림'} · 좁아진 폭 {lost:+.3f}초")
