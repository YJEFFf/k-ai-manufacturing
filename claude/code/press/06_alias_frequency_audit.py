"""10 Hz로 찍힌 전류의 겉보기(앨리어싱) 주파수를 구간별 사인 적합으로 확인한다(보고서 1.4·1.5절 전류 파형, 6장 실행 순서).

구간(0.15초 넘는 공백에서 끊음, 길이 >= MIN_LEN)마다 a·sin(2πft)+b·cos(2πft)+c 를 f ∈ [0, 5] Hz 격자에서 적합해 f·진폭·R²를 구한다.
정상에서 f가 안정되고 R²가 높으면 겉보기 주파수는 전원 주파수와 표본 간격이 만든 값이다. 이상에서 R²만 낮으면 깨진 것은 주파수가 아니라 파형이다.
입력: data/3_소성가공_예지보전/ 두 CSV(원본). 출력: outputs/alias/segment_sine_fit.csv, early_sine_r2.csv
실행: python code/press/06_alias_frequency_audit.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "3_소성가공_예지보전"
OUT = HERE / "outputs" / "alias"
MIN_LEN = 10
FREQS = np.arange(0.0, 5.0001, 0.005)  # 0~5 Hz(나이퀴스트), 0.005 Hz 간격
DT = 0.1


def segments(df):
    """0.15초 넘는 공백에서 끊은 구간 번호(1부터)."""
    t = pd.to_datetime(df.TimeStamp)
    return (t.diff().dt.total_seconds().fillna(9) > 0.15).cumsum().to_numpy()


def fit_sine(x):
    """주파수 격자를 훑어 잔차제곱합이 가장 작은 사인을 고른다. 반환 (f, 진폭, R²)."""
    t = np.arange(len(x)) * DT
    sst = ((x - x.mean()) ** 2).sum()
    best = (np.inf, 0.0, 0.0)
    for f in FREQS:
        A = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones_like(t)])
        coef, *_ = np.linalg.lstsq(A, x, rcond=None)
        sse = ((x - A @ coef) ** 2).sum()
        if sse < best[0]:
            best = (sse, f, np.hypot(coef[0], coef[1]))
    sse, f, amp = best
    return f, amp, 1 - sse / sst if sst > 0 else np.nan


def table(df, label):
    """구간별 적합 결과 표(MIN_LEN 미만 구간은 뺀다)."""
    seg = segments(df)
    rows = []
    for s in np.unique(seg):
        g = df[seg == s]
        if len(g) < MIN_LEN:
            continue
        f, amp, r2 = fit_sine(g.AI2_Current.to_numpy())
        rows.append(dict(set=label, seg=int(s), len=len(g), f_alias=f, amp=amp, r2=r2,
                         vib0_std=g.AI0_Vibration.std(), vib1_std=g.AI1_Vibration.std()))
    return pd.DataFrame(rows)


def main():
    """구간 적합표를 저장하고, 정상 앞 80%로 정한 문턱을 정상 뒤 20%와 이상에 적용해 본다."""
    OUT.mkdir(parents=True, exist_ok=True)
    normal = pd.read_csv(DATA / "press_data_normal.csv")
    abn = pd.read_csv(DATA / "outlier_data.csv")
    tn, ta = table(normal, "normal"), table(abn, "abnormal")
    tab = pd.concat([tn, ta], ignore_index=True)
    tab.to_csv(OUT / "segment_sine_fit.csv", index=False)

    print("== 구간 사인 피팅 요약 (길이 >= %d)" % MIN_LEN)
    print(tab.groupby("set")[["len", "f_alias", "amp", "r2"]].describe(percentiles=[.05, .5, .95]).T.round(3).to_string())

    # 짧은 구간은 R²가 쉽게 높거나 낮다. 길이 30 이상만 따로 본다
    long_ = tab[tab.len >= 30]
    print("\n== 길이 >= 30 구간만")
    print(long_.groupby("set")[["f_alias", "r2"]].describe(percentiles=[.05, .5, .95]).T.round(3).to_string())

    # 정상 시간 추이 (드리프트)
    tn["block"] = pd.qcut(tn.seg, 5, labels=False)
    print("\n== 정상 f_alias 시간 추이 (5등분)")
    print(tn.groupby("block")[["f_alias", "r2", "amp"]].median().round(3).to_string())

    print("\n== 이상 구간별")
    print(ta[["seg", "len", "f_alias", "amp", "r2", "vib0_std", "vib1_std"]].round(3).to_string(index=False))

    # 문턱은 정상 앞 80% 구간에서만 정한다(f는 0.5%/99.5%, R²는 1% 분위). 정상 뒤 20%와 이상은 평가에만 쓴다
    cut = int(len(tn) * 0.8)
    cal, test_n = tn.iloc[:cut], tn.iloc[cut:]
    lo_f, hi_f = cal.f_alias.quantile([0.005, 0.995])
    lo_r2 = cal.r2.quantile(0.01)
    rule = lambda d: (d.f_alias < lo_f) | (d.f_alias > hi_f) | (d.r2 < lo_r2)
    print("\n== 규칙: f 밖 [%.3f, %.3f] 또는 R² < %.3f (정상 앞 80%%로 보정)" % (lo_f, hi_f, lo_r2))
    print("정상 뒤 20%% 알림 %d/%d, 이상 탐지 %d/%d" % (rule(test_n).sum(), len(test_n), rule(ta).sum(), len(ta)))
    print("  f만: 이상 %d/%d, R²만: 이상 %d/%d" % (((ta.f_alias < lo_f) | (ta.f_alias > hi_f)).sum(), len(ta),
                                            (ta.r2 < lo_r2).sum(), len(ta)))


def early_check(ks=(4, 5, 6, 8, 10, 20)):
    """구간 첫 k개 관측만으로 사인 R²를 판정할 때 얼마나 일찍 잡히는지 본다.

    정상 구간을 예준 기본 분할 경계(360/480)로 나눠 문턱 = 정상 보정 구간(360~479) R²의 1% 분위, 평가 = 정상 480~ 과 이상 전체.
    """
    normal = pd.read_csv(DATA / "press_data_normal.csv")
    abn = pd.read_csv(DATA / "outlier_data.csv")
    sn, sa = segments(normal), segments(abn)
    sn = sn - sn.min()  # 정상 구간 번호를 0부터 세어 예준 기록 번호와 맞춘다
    cur_n, cur_a = normal.AI2_Current.to_numpy(), abn.AI2_Current.to_numpy()

    def r2s(x, seg, ids, k):
        """구간마다 첫 k개 관측의 R². k개가 안 되는 구간은 NaN."""
        v = []
        for s in ids:
            xs = x[seg == s]
            v.append(fit_sine(xs[:k])[2] if len(xs) >= k else np.nan)
        return np.array(v)

    out = []
    for k in ks:
        cal = r2s(cur_n, sn, range(360, 480), k)
        tst = r2s(cur_n, sn, range(480, 600), k)
        ab = r2s(cur_a, sa, np.unique(sa), k)
        thr = np.nanquantile(cal, 0.01)
        out.append(dict(k=k, sec=k * DT, thr=round(thr, 4),
                        normal_alarm=f"{int(np.nansum(tst < thr))}/{int(np.sum(~np.isnan(tst)))}",
                        abn_detect=f"{int(np.nansum(ab < thr))}/{int(np.sum(~np.isnan(ab)))}",
                        abn_too_short=int(np.isnan(ab).sum())))
    res = pd.DataFrame(out)
    res.to_csv(OUT / "early_sine_r2.csv", index=False)
    print("\n== 첫 k관측 사인 R² 조기판정 (문턱=정상 보정 구간 1%)")
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
    early_check()
