"""5단계 검사: 지속성 정책 점수, 진폭 정규화 특징."""
import numpy as np

from press.field import _amp, persistence_score, trailing_feature


def test_persistence_score_semantics():
    seg = np.r_[np.zeros(6, int), np.ones(4, int)]
    s = np.array([1.0, 5.0, np.nan, 2.0, 9.0, 3.0, 7.0, 1.0, 8.0, 2.0])
    p11 = persistence_score(s, seg, 1, 1)
    assert np.allclose(p11, s, equal_nan=True)
    p23 = persistence_score(s, seg, 2, 3)          # 최근 3개 유효값 중 2번째 큰 값
    assert np.isnan(p23[0]) and np.isnan(p23[1]) and np.isnan(p23[2])
    assert np.isnan(p23[3]) and np.isnan(p23[4]) and p23[5] == 3.0   # 결측(NaN)에서 창 초기화 → 2행 미판정, (2,9,3)→3 (검수 R3)
    assert np.isnan(p23[6]) and np.isnan(p23[7]) and p23[8] == 7.0  # 새 구간은 다시 채움: (7,1,8)→7
    p33 = persistence_score(s, seg, 3, 3)
    assert p33[5] == 2.0 and p33[8] == 1.0


def test_trailing_amp_on_sine():
    t = np.arange(40) * 0.1
    x = 100 * np.sin(2 * np.pi * 0.6 * t)
    a = trailing_feature(x, np.zeros(40, int), 17, _amp)
    assert np.isnan(a[:16]).all() and np.isfinite(a[16:]).all()
    assert abs(a[16:].mean() - 100) < 5
