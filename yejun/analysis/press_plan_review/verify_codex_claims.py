"""Codex 적대적 검토(README.md)의 사실 주장을 원본 zip에서 직접 재계산한다.
실행: 저장소 루트에서  PYTHONDONTWRITEBYTECODE=1 python3 yejun/analysis/press_plan_review/verify_codex_claims.py
입력: 데이터셋/프레스_유압펌프_예지보전/Dataset_소성가공 예지보전 AI 데이터셋.zip (Git 제외). 출력은 화면에만 낸다."""
import zipfile, io, numpy as np, pandas as pd
Z = "데이터셋/프레스_유압펌프_예지보전/Dataset_소성가공 예지보전 AI 데이터셋.zip"
zf = zipfile.ZipFile(Z)
def load(name):
    df = pd.read_csv(io.BytesIO(zf.read(name)))
    df["t"] = pd.to_datetime(df["TimeStamp"])
    return df
N = load("data/press_data_normal.csv"); A = load("data/outlier_data.csv")

print("== R3: Δt (seconds) ==")
for lab, df in [("normal", N), ("abnormal", A)]:
    dt = df["t"].diff().dt.total_seconds().values[1:]
    small = dt[dt <= 0.15]
    print(f"{lab}: n_gaps={len(dt)}, dt==0.1 (±1e-6): {(np.abs(dt-0.1)<1e-6).sum()}, dt==0: {(dt==0).sum()}, other<=0.15: {((small!=0)&(np.abs(small-0.1)>=1e-6)).sum()}")
    print(f"   SD(all <=0.15 incl zeros)={small.std():.9f}  SD(positive only)={small[small>0].std():.2e}  max|dt-0.1| among positive small={np.abs(small[small>0]-0.1).max():.2e}")
    ms = df["t"].dt.microsecond.values // 1000
    print(f"   distinct ms fractional offsets mod 100: {sorted(set((ms % 100).tolist()))[:10]} (count {len(set((ms%100).tolist()))})")

def segments(df):
    dt = df["t"].diff().dt.total_seconds()
    return (dt.sub(0.1).abs().gt(1e-6).fillna(False)).cumsum().values
N["seg"] = segments(N); A["seg"] = segments(A)
print("\n== segments ==", N["seg"].nunique(), A["seg"].nunique())

print("\n== R6: LSTM trailing-20 windows inside abnormal segments ==")
L = A.groupby("seg").size().values
short = sorted(L[L < 20].tolist())
print("abnormal seg lengths:", sorted(L.tolist()))
print("segments <20:", len(short), short)
print("scorable rows (sum max(0,len-19)):", int(np.maximum(0, L-19).sum()), " scorable segments:", int((L>=20).sum()))
sr = int(np.maximum(0, L-19).sum()); print(f"F1 upper bound (unscored=miss, no FP): {2*sr/(600+sr):.5f}")
for w in (5, 8, 10):
    print(f"  w={w}: scorable rows {int(np.maximum(0, L-(w-1)).sum())}, scorable segs {int((L>=w).sum())}, F1 ub {2*np.maximum(0,L-(w-1)).sum()/(600+np.maximum(0,L-(w-1)).sum()):.4f}")

print("\n== R3: current means ==")
print(f"file means AI2: normal {N.AI2_Current.mean():.6f}, abnormal {A.AI2_Current.mean():.6f}")
sm = N.groupby("seg").AI2_Current.mean(); print(f"normal segment means range: {sm.min():.2f} .. {sm.max():.2f}; abnormal seg means range: {A.groupby('seg').AI2_Current.mean().min():.2f} .. {A.groupby('seg').AI2_Current.mean().max():.2f}")
print(f"normal AI2 std {N.AI2_Current.std():.2f}, abnormal {A.AI2_Current.std():.2f}")

print("\n== current grid: spacing and dimensionless tolerance explicitly reported ==")
# 05 uses spacing 1.1920929 and residual tolerance 1e-3. A tighter
# tolerance is a separate sensitivity check, not the same shortcut rule.
for definition, g in [("legacy_05", 1.1920929), ("binary_spacing_hypothesis", 1e7 * 2.0**-23)]:
    for lab, df in [("normal", N), ("abnormal", A)]:
        q = df.AI2_Current.values / g
        residual = np.abs(q - np.round(q))
        for tolerance in (1e-3, 1e-6):
            print(f"{definition}, {lab}: grid={g:.12g}, tolerance={tolerance:g}, "
                  f"on-grid fraction={(residual < tolerance).mean():.4f}")
print("vibration decimals (max digits after point, all rows) normal/abnormal:",
      max(len(s.split('.')[1]) if '.' in s else 0 for s in pd.read_csv(io.BytesIO(zf.read('data/press_data_normal.csv')), dtype=str).AI0_Vibration),
      max(len(s.split('.')[1]) if '.' in s else 0 for s in pd.read_csv(io.BytesIO(zf.read('data/outlier_data.csv')), dtype=str).AI0_Vibration))

print("\n== R1: half period ==")
f, dt = 0.6, 0.1
print(f"half period {0.5/f:.4f}s; w=8 span (w-1)dt={7*dt:.1f}s, duration w*dt={0.8:.1f}s; w needed by span: {int(np.ceil((0.5/f)/dt))+1}, by duration: {int(np.ceil((0.5/f)/dt))}")

print("\n== R7: mean-removed RMS phase sensitivity (unit sine 0.6Hz, dt=0.1) ==")
for w in (3, 8, 17):
    vals = []
    for ph in np.linspace(0, 2*np.pi, 360, endpoint=False):
        x = np.sin(2*np.pi*f*np.arange(w)*dt + ph); x = x - x.mean(); vals.append(np.sqrt((x**2).mean()))
    print(f"  w={w}: min {min(vals):.5f} max {max(vals):.5f} ratio {max(vals)/min(vals):.2f}")

print("\n== R2/R5 ==")
print(f"P(true FA rate of max-threshold > 1%) iid: 0.99^120 = {0.99**120:.6f}")
print(f"one-sided 95% upper bound on FA rate given 0/120: {1-0.05**(1/120):.6f}")
print(f"cutoff exceedance prob (1 allowed of 120): 2/121 = {2/121:.5f}; conformal alpha_eff at 1/3/5%: {[ (int(np.floor(a*121))) /121 for a in (0.01,0.03,0.05)]}")
