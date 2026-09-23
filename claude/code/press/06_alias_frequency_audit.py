"""③ 프레스: 10Hz로 찍힌 전류의 앨리어싱 주파수 검증.

구간(0.1초 초과 공백에서 끊음, 길이 >= MIN_LEN)마다 단일 사인파 a*sin(2πft)+b*cos(2πft)+c 를
f ∈ [0, 5]Hz 격자에서 최소제곱 피팅해 주파수 f, 진폭, 설명력 R² 를 구한다.
- 정상에서 f가 안정적이고 R²가 높으면: 앨리어싱 주파수는 전원/모터 주파수와 샘플링 간격이 만든 결정적 값
- 이상에서 R²가 낮으면: '주파수가 바뀐 것'이 아니라 '사인파 모양이 깨진 것'
정상 구간 f, R² 기준으로 이상 구간을 판정했을 때 몇 구간이 잡히는지도 센다 (문턱은 정상 보정 구간에서만).
실행: python code/press/06_alias_frequency_audit.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data" / "3_소성가공_예지보전"
OUT = HERE / "outputs" / "alias"
MIN_LEN = 10
FREQS = np.arange(0.0, 5.0001, 0.005)
DT = 0.1


def segments(df):
    t = pd.to_datetime(df.TimeStamp)
    return (t.diff().dt.total_seconds().fillna(9) > 0.15).cumsum().to_numpy()


def fit_sine(x):
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
    OUT.mkdir(parents=True, exist_ok=True)
    normal = pd.read_csv(DATA / "press_data_normal.csv")
    abn = pd.read_csv(DATA / "outlier_data.csv")
    tn, ta = table(normal, "normal"), table(abn, "abnormal")
    tab = pd.concat([tn, ta], ignore_index=True)
    tab.to_csv(OUT / "segment_sine_fit.csv", index=False)

    print("== 구간 사인 피팅 요약 (길이 >= %d)" % MIN_LEN)
    print(tab.groupby("set")[["len", "f_alias", "amp", "r2"]].describe(percentiles=[.05, .5, .95]).T.round(3).to_string())

    # 길이 영향 통제: 정상에서 같은 길이 분포로 비교 (길이 30 이상만)
    long_ = tab[tab.len >= 30]
    print("\n== 길이 >= 30 구간만")
    print(long_.groupby("set")[["f_alias", "r2"]].describe(percentiles=[.05, .5, .95]).T.round(3).to_string())

    # 정상 시간 추이 (드리프트)
    tn["block"] = pd.qcut(tn.seg, 5, labels=False)
    print("\n== 정상 f_alias 시간 추이 (5등분)")
    print(tn.groupby("block")[["f_alias", "r2", "amp"]].median().round(3).to_string())

    # 이상 구간 목록
    print("\n== 이상 구간별")
    print(ta[["seg", "len", "f_alias", "amp", "r2", "vib0_std", "vib1_std"]].round(3).to_string(index=False))

    # 정상 앞 80% 구간으로 문턱을 정하고(1%/99% 분위) 정상 뒤 20%와 이상에 적용
    cut = int(len(tn) * 0.8)
    cal, test_n = tn.iloc[:cut], tn.iloc[cut:]
    lo_f, hi_f = cal.f_alias.quantile([0.005, 0.995])
    lo_r2 = cal.r2.quantile(0.01)
    rule = lambda d: (d.f_alias < lo_f) | (d.f_alias > hi_f) | (d.r2 < lo_r2)
    print("\n== 규칙: f 밖 [%.3f, %.3f] 또는 R² < %.3f (정상 앞 80%%로 보정)" % (lo_f, hi_f, lo_r2))
    print("정상 뒤 20%% 알림 %d/%d, 이상 탐지 %d/%d" % (rule(test_n).sum(), len(test_n), rule(ta).sum(), len(ta)))
    print("  f만: 이상 %d/%d, R²만: 이상 %d/%d" % (((ta.f_alias < lo_f) | (ta.f_alias > hi_f)).sum(), len(ta),
                                            (ta.r2 < lo_r2).sum(), len(ta)))


if __name__ == "__main__":
    main()


def early_check(ks=(4, 5, 6, 8, 10, 20)):
    """구간 첫 k개 관측만으로 사인 피팅 R²를 판정할 때의 조기탐지 가능성.
    정상 기록구간을 시간순 60/20/20(예준 기본분할과 같은 경계: 360/480)으로 나누고,
    문턱 = 정상 보정 구간(360~479) R²의 1% 분위. 평가 = 정상 480~ 과 이상 전체."""
    normal = pd.read_csv(DATA / "press_data_normal.csv")
    abn = pd.read_csv(DATA / "outlier_data.csv")
    sn, sa = segments(normal), segments(abn)
    sn = sn - sn.min()
    out = []
    for k in ks:
        def r2s(df, seg, ids):
            v = []
            for s in ids:
                x = df.AI2_Current.to_numpy()[seg == s]
                v.append(fit_sine(x[:k])[2] if len(x) >= k else np.nan)
            return np.array(v)
        cal = r2s(normal, sn, range(360, 480))
        tst = r2s(normal, sn, range(480, 600))
        ab = r2s(abn, sa, np.unique(sa))
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
    early_check()
