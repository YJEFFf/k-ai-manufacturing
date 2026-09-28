#!/usr/bin/env python
"""review2 — A 문턱·A 평가 구간 문단 대조(팀 모듈 import 없음).

입력: review2_threshold_model.py가 만든 기록별 최대 점수 CSV, 저장 모델 JSON의 calibration 배열(자료로만 읽음),
      v2 행 단위 예측(test_predictions_A/B.csv), review2_verify.py가 만든 기록별 신호 요약 CSV.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ap = argparse.ArgumentParser()
ap.add_argument("--root", required=True, help="스냅숏 또는 저장소 루트(예측 CSV)")
ap.add_argument("--models", required=True, help="guard_A.json·guard_B.json 이 있는 폴더(사본)")
ap.add_argument("--work", required=True, help="review2 산출 CSV 폴더")
args = ap.parse_args()
R, M, W = Path(args.root), Path(args.models), Path(args.work)

cal = {s: np.asarray(json.loads((M / f"guard_{s}.json").read_text(encoding="utf-8"))["state"]["calibration"], float) for s in "AB"}
calrec = {s: pd.read_csv(W / f"review2_cal_record_max_{s}.csv", index_col=0).record_max for s in "AB"}
for s in "AB":
    assert np.allclose(np.sort(cal[s]), np.sort(calrec[s].to_numpy()), rtol=0, atol=1e-12)


def test_record_max(s):
    df = pd.read_csv(R / f"yejun/press_guard/outputs/test_predictions_{s}.csv")
    off = 480 if s == "A" else 420
    n = df[df.subset == "normal_test"]
    rm = n.groupby("record_id").agg(smax=("score", "max"), alarm=("alarm", "max"))
    rm.index = rm.index + off
    return rm


TA, TB = test_record_max("A"), test_record_max("B")
print("=" * 90)
print("1. A 보정 구간(360~479) 기록별 최대 점수 상위와 B 평가 오경보 기록")
top = calrec["A"].sort_values(ascending=False)
print("   상위 6:", "; ".join(f"{int(k)}={v:.6f}" for k, v in top.head(6).items()))
b_alarm = sorted(TB.index[TB.alarm == 1].tolist())
print(f"   B 평가(420~599) α 1% 오경보 기록: {b_alarm}")
print(f"   A 보정 상위 2 기록 {top.index[:2].tolist()} ⊂ B 오경보: {set(top.index[:2]) <= set(b_alarm)}")
dfb = pd.read_csv(R / "yejun/press_guard/outputs/test_predictions_B.csv")
dfb = dfb[dfb.subset == "normal_test"]
for alpha in (0.03, 0.05):
    recs = sorted((dfb.loc[dfb.p_value <= alpha + 1e-12, "record_id"] + 420).unique().tolist())
    inter = [r for r in top.index[:6] if r in recs]
    print(f"   B α {alpha:.0%} 오경보 기록 {recs}; A 보정 상위 6 가운데 포함 {inter}")
print(f"   B 모델 α 1% 문턱(B 보정 최대) {cal['B'].max():.6f}; B 오경보 기록의 B 점수 "
      + ", ".join(f"{r}={TB.loc[r, 'smax']:.3f}" for r in b_alarm))

print("\n2. α 1% 문턱이 어느 값으로 정해지는가(n=120: p=(1+k)/121 ≤ 0.01 ⇔ k=0 ⇔ s > 보정 최대)")
for k in range(0, 4):
    print(f"   k={k}: p={(1+k)/121:.4f} → α 1% 경보 {'예' if (1+k)/121 <= 0.01 else '아니오'}")
thr_full = cal["A"].max()
cf = {}
for drop in [[], [461], [423], [461, 423]]:
    keep = calrec["A"].drop(index=drop)
    thr = keep.max()
    n = len(keep)
    # 같은 규칙: p=(1+#{cal≥s})/(n+1) ≤ 0.01
    kk = n - np.searchsorted(np.sort(keep.to_numpy()), TA.smax.to_numpy(), side="left")
    alarms = int((((kk + 1) / (n + 1)) <= 0.01).sum())
    recs = TA.index[((kk + 1) / (n + 1)) <= 0.01].tolist()
    cf[str(drop)] = (thr, alarms, recs)
    print(f"   보정에서 {drop or '제외 없음'} 제외: 문턱 {thr:.6f}, A 평가 정상 알림 {alarms}/120 {recs}")
print(f"   A 평가 정상 기록 최대 점수 상위 3: " + "; ".join(f"{int(k)}={v:.4f}" for k, v in TA.smax.sort_values(ascending=False).head(3).items()))

print("\n3. A 평가 구간 점수가 보정 중앙값을 넘는 구간 수·Mann–Whitney")
med = np.median(cal["A"])
above = int((TA.smax > med).sum())
print(f"   A 보정 중앙값 {med:.6f}; A 평가 120기록 중 초과 {above}/120 (교환가능 기대 약 60)")
for alt in ["two-sided", "less"]:
    for method in ["asymptotic", "exact"]:
        try:
            r = stats.mannwhitneyu(TA.smax.to_numpy(), cal["A"], alternative=alt, method=method)
            print(f"   Mann–Whitney 평가 vs 보정 alternative={alt:<9} method={method:<10} U={r.statistic:.1f} p={r.pvalue:.3e}")
        except Exception as e:  # exact는 동점이 있으면 실패할 수 있다
            print(f"   Mann–Whitney {alt} {method}: 실패 {e}")
bn = stats.binomtest(above, 120, 0.5)
print(f"   (참고) 이항 검정 {above}/120 vs 0.5: p={bn.pvalue:.3e}")
# 초과 수를 다른 보정 분위와 비교(B)
medB = np.median(cal["B"])
print(f"   (참고) B: B 보정 중앙값 {medB:.6f}, B 평가 180기록 중 초과 {int((TB.smax > medB).sum())}/180")

print("\n4. 상태별 분모(원 전류 기록 평균 제거 RMS, ddof=0; 17행 미만 short, ≥91.9 load) — 인접 문단 대조")
per = pd.read_csv(W / "review2_record_signal_summary.csv", index_col=0)
for name, (r0, r1) in {"A 평가": (480, 600), "B 평가": (420, 600), "A 보정": (360, 480), "B 보정": (300, 420)}.items():
    p = per.loc[r0:r1 - 1]
    ge = p[p.n >= 17]
    print(f"   {name} {r0}~{r1-1}: 기록 {len(p)}, 17행 이상 {len(ge)}, 부하 {int(ge.load.sum())}, 저수준 {int(ge.low.sum())} "
          f"({ge.low.mean()*100:.1f}%), short {int((p.n < 17).sum())}")
b_load = [r for r in b_alarm if bool(per.loc[r, "load"])]
print(f"   B α 1% 오경보 기록의 상태: " + ", ".join(f"{r}={'load' if per.loc[r,'load'] else ('low' if per.loc[r,'low'] else 'short')}" for r in b_alarm))
