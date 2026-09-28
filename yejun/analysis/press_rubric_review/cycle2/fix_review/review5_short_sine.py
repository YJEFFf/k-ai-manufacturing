"""검토 5: build_tables.py OFFSET_MIN_LEN 주석(순수 0.6 Hz 사인은 10행이면 |평균| > SD가 될 수 있고 11행 이상이면 없다,
0.22 Hz 사인은 17행에서 57%)과 README R4 해석 조건을 위상 2만 개로 확인한다(SD는 ddof=1, 표본 간격 0.1초).

    python review5_short_sine.py
"""
import numpy as np

ph = np.linspace(0, 2 * np.pi, 20000, endpoint=False)
for n in (9, 10, 11, 12, 17, 25, 50):
    t = np.arange(n) * .1
    out = []
    for f in (0.6, 0.22):
        x = np.sin(2 * np.pi * f * t[None, :] + ph[:, None])
        out.append(np.mean(np.abs(x.mean(1)) > x.std(1, ddof=1)))
    print(f"{n:>3}행: 0.6 Hz {out[0]:.1%} · 0.22 Hz {out[1]:.1%}")
