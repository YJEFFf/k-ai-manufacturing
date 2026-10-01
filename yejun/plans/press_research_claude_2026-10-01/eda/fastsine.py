"""버스트 단위 사인+오프셋 최소제곱 적합(벡터화). t 인자는 호환용이며 0.1초 등간격을 가정한다."""
import numpy as np
FREQS = np.arange(0.02, 5.0005, 0.002)
_cache = {}
def _proj(n):
    if n not in _cache:
        t = np.arange(n) * 0.1
        W = 2 * np.pi * FREQS[:, None] * t[None, :]
        M = np.stack([np.sin(W), np.cos(W), np.ones_like(W)], axis=2)      # F,n,3
        pinv = np.linalg.pinv(M)                                             # F,3,n
        _cache[n] = (M, pinv)
    return _cache[n]
def sinefit(t, x):
    n = len(x); M, pinv = _proj(n)
    coef = pinv @ x                                                          # F,3
    fit = np.einsum('fnk,fk->fn', M, coef)
    sse = ((x[None, :] - fit) ** 2).sum(1)
    j = int(np.argmin(sse)); c = coef[j]
    sst = np.sum((x - x.mean()) ** 2) + 1e-12
    return dict(f=float(FREQS[j]), amp=float(np.hypot(c[0], c[1])), off=float(c[2]),
                r2=float(1 - sse[j] / sst), rres=float(np.sqrt(sse[j] / n)))
