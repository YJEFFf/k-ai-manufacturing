"""A1-2b 채널별 ADC 격자 탐색(원형 집중도). 값 v를 간격 s로 나눈 소수부의 위상 집중도 R(0~1)이 1에 가까우면 v = a + k·s 격자 위에 있다.
redA1_02b_adc_grid.log는 이 코드와 같은 내용을 인라인으로 실행한 출력이다(약 3~4분). 팀 모듈 import 없음."""
import numpy as np
import redA1_common as C

normal, abnormal = C.load_raw()


def fit_grid(v, s_lo, s_hi, n=20001):
    best = None
    for s in np.linspace(s_lo, s_hi, n):
        ph = 2 * np.pi * (v / s % 1.0)
        R = np.abs(np.exp(1j * ph).mean())
        if best is None or R > best[0]:
            best = (R, s, np.angle(np.exp(1j * ph).mean()) / (2 * np.pi))
    return best


for c, lo, hi in ((C.SENS[0], 1.09e-5, 1.12e-5), (C.SENS[1], 1.14e-5, 1.17e-5)):
    va = abnormal[c].to_numpy(float)
    R, s, a = fit_grid(va, lo, hi)
    print(c, "abnormal: 격자 간격", s, "집중도 R", R, "위상(격자 단위)", a)
    R, s, a = fit_grid(va, s * (1 - 2e-4), s * (1 + 2e-4), 4001)
    off = ((va / s - a + 0.5) % 1.0) - 0.5
    print("   정제 간격", s, "R", R, "격자 이탈 |off| 중앙", np.median(np.abs(off)), "최대", np.abs(off).max())
    vn = normal[c].to_numpy(float)
    Rn, sn, an = fit_grid(vn, lo, hi, 2001)
    print("   normal: 같은 범위 최고 집중도 R", Rn, "at", sn, "(무작위 20000점의 기대 R ~", 1 / np.sqrt(len(vn)) * 0.89, ")")
    for rng_ in ((1e-6 * 2, 1e-5), (1e-5, 5e-5), (5e-5, 4e-4)):
        Rn, sn, an = fit_grid(vn, rng_[0], rng_[1], 20001)
        print("   normal 격자 탐색", rng_, "최고 R", round(Rn, 4), "간격", sn)
xa, xn = abnormal[C.SENS[2]].to_numpy(float), normal[C.SENS[2]].to_numpy(float)
for name, x in (("abnormal", xa), ("normal", xn)):
    for rng_ in ((0.05, 0.5), (0.5, 3.0)):
        R, s, a = fit_grid(x, rng_[0], rng_[1], 20001)
        print("current", name, rng_, "최고 R", round(R, 4), "간격", s, "위상", a)
