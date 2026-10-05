"""사인 창 길이 w를 정상 데이터만으로 고르는 규칙 (이상 데이터 미사용).

규칙: 정상 학습 구간 전류의 1−R² 상위 1% 문턱을 넘는 백색잡음 창이 99% 이상인 가장 작은 w.
    즉 "정상 파형과 무작위 잡음을 1% 오경보 수준에서 99% 이상 가를 수 있는 가장 짧은 창".
    창이 짧으면 사인+상수+주파수 탐색(사실상 파라미터 4개)이 잡음까지 맞춰 판별력을 잃는다(w=5: 잡음 R² 중앙 0.91).
보조 근거(휴리스틱): 정상 학습 전류의 앨리어싱 주파수 추정치와 그 반주기(관측 수)를 함께 기록한다.

2026-09-24 이전 규칙(정상 알림 비율 최소)은 점수 포화 결함 때문에 폐기했다 (프레스_실행계획 참고).
"""
import numpy as np
import pandas as pd

from scores import FREQS, _hats, sine_misfit, sine_score

CANDIDATES = tuple(range(4, 17))
Q_NORMAL = 0.99
TARGET_REJECT = 0.99
N_NOISE = 10000
SEED = 0


def alias_frequency(train, groups, min_len=20):
    """정상 학습 구간(길이 >= min_len)마다 전체 구간 사인 피팅 주파수의 중앙값."""
    x = train["AI2_Current"].to_numpy(float)
    freqs = []
    for g in np.unique(groups):
        seg = x[groups == g]
        if len(seg) < min_len:
            continue
        t = np.arange(len(seg)) * 0.1
        best = (np.inf, 0.0)
        for f in FREQS:
            A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones(len(seg))])
            c, *_ = np.linalg.lstsq(A, seg, rcond=None)
            sse = ((seg - A @ c) ** 2).sum()
            if sse < best[0]:
                best = (sse, f)
        freqs.append(best[1])
    return float(np.median(freqs)), len(freqs)


def select_w(train, blocks, candidates=CANDIDATES):
    groups = blocks(train)
    rng = np.random.default_rng(SEED)
    rows = []
    for w in candidates:
        s = sine_score(train, groups, w)
        thr = float(np.nanquantile(s, Q_NORMAL))
        noise = sine_misfit(rng.normal(size=(N_NOISE, w)))
        rows.append(dict(w=w, normal_misfit_q99=thr, noise_misfit_median=float(np.median(noise)),
                         noise_reject_rate=float((noise > thr).mean())))
    table = pd.DataFrame(rows)
    ok = table[table.noise_reject_rate >= TARGET_REJECT]
    w_rule = int(ok.w.min()) if len(ok) else int(table.loc[table.noise_reject_rate.idxmax(), "w"])
    f_alias, n_seg = alias_frequency(train, groups)
    info = dict(w_rule=w_rule, alias_freq_hz=f_alias, alias_segments=n_seg,
                half_period_obs=10 / (2 * f_alias) if f_alias > 0 else float("nan"))
    table["selected"] = table.w == w_rule
    return w_rule, table, info
