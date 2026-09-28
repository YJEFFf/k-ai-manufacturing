"""3단계 검사: 절제 정의·조건 구간·라벨 우회 함수."""
import numpy as np
import pandas as pd

from press import data as D
from press.analysis import _len_bin, _quartile_bin, segment_features
from press.robustness import label_bypass
from press.scores import MainModel, Scorer
from press.calibrate import segment_max, thresholds_for


def test_bins():
    assert [_len_bin(n) for n in (1, 4, 5, 9, 10, 29, 30, 50)] == ["≤4", "≤4", "5–9", "5–9", "10–29", "10–29", "≥30", "≥30"]
    q = np.array([1.0, 2.0, 3.0])
    assert [_quartile_bin(x, q) for x in (0.5, 1.5, 2.5, 3.5, np.nan)] == ["Q1(<q25)", "Q2", "Q3", "Q4(≥q75)", "NA"]


def test_segment_features_amp_reliability():
    t = np.arange(40) * D.DT
    df = pd.DataFrame({D.TIME: pd.date_range("2022-07-12", periods=40, freq="100ms").strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3],
                       D.SENSORS[0]: np.random.default_rng(0).standard_normal(40) * 0.05,
                       D.SENSORS[1]: np.random.default_rng(1).standard_normal(40) * 0.05,
                       D.SENSORS[2]: 100 * np.sin(2 * np.pi * 0.6 * t)})
    seg = np.r_[np.zeros(30, int), np.ones(10, int)]
    f = segment_features(df, seg)
    assert list(f.length) == [30, 10] and list(f.amp_reliable) == [True, False]
    assert abs(f.amp_proxy.iloc[0] - 100) < 5 and f.r2_segment.iloc[0] > 0.99


def test_label_bypass_passes_on_fitted_model():
    normal, abnormal, _ = D.load(D.PACKAGE_DIR, verify=True)
    seg_n = D.segments(normal)
    sp = D.split_normal(normal, seg_n, "A")
    vendor = D.load_vendor()
    train, cal = D.quantize(sp["train"], "matched"), D.quantize(sp["cal"], "matched")
    scorer = Scorer(train, D.segments(train), vendor, wins=(8,), baselines=False)
    st = scorer.main_state(8)
    cal_seg = segment_max(scorer.score(cal, D.segments(cal))[0]["combined_w8"], D.segments(cal))
    st["calibration"] = {"unit": "recording_segments", "segment_max": cal_seg, "n": len(cal_seg), "thresholds": thresholds_for(cal_seg, "recording_segments")}
    st["preprocess_spec"] = D.QUANTIZATION["matched"]
    stream = pd.concat([D.inputs_only(D.quantize(sp["test"], "matched")), D.inputs_only(D.quantize(abnormal, "matched"))], ignore_index=True)
    lb = label_bypass(st, stream, "test")
    # 라벨·날짜·미래 행이 점수를 바꾸지 않는다. 미래 행을 덧붙이면 배열 길이가 달라 기기에 따라 부동소수 잡음(x86-64 실측 2.8e-14)이 생긴다.
    assert lb.passed.all() and (lb[lb.expect_equal].max_abs_score_diff <= 1e-12).all()
