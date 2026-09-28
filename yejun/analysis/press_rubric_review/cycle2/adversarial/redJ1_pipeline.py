"""정상·이상 파일의 수집·가공 경로 차이 점검(전류 격자, 진동 격자, 시각 위상)."""
import numpy as np, pandas as pd
from pathlib import Path
RAW = Path("/Volumes/YJSSD/공모전/k-제조데이터/yejun/press_submission/data/3_소성가공_예지보전")
nor = pd.read_csv(RAW/"press_data_normal.csv"); ab = pd.read_csv(RAW/"outlier_data.csv")
g = 1.1920929
for name, df in (("normal", nor), ("abn", ab)):
    q = df.AI2_Current.to_numpy()/g
    frac = q-np.floor(q)
    h, _ = np.histogram(frac, bins=10, range=(0, 1))
    print(name, "frac hist of current/g:", h.tolist())
# does normal current sit on any finer grid? try g/k
q = nor.AI2_Current.to_numpy()
for k in (2, 3, 4, 5, 8, 10, 16, 20, 32, 50, 64, 100):
    r = np.abs(q/(g/k)-np.round(q/(g/k)))*(g/k)
    print("normal on grid g/%d (tol 2e-5):" % k, round(float((r < 2e-5).mean()), 4), end=" | ")
print()
# decimal precision of normal current is 5 decimals => resolution 1e-5; count unique values
print("unique current normal", nor.AI2_Current.nunique(), "of", len(nor), "| abn", ab.AI2_Current.nunique(), "of", len(ab))
print("unique AI0 normal", nor.AI0_Vibration.nunique(), "abn", ab.AI0_Vibration.nunique())
# vibration grid in abnormal? check common divisor
for c in ("AI0_Vibration", "AI1_Vibration"):
    v = np.sort(np.unique(ab[c].to_numpy())); d = np.diff(v); print(c, "abn min diff", d.min(), "median diff", np.median(d))
    v = np.sort(np.unique(nor[c].to_numpy())); d = np.diff(v); print(c, "normal min diff", d.min(), "median diff", np.median(d))
# timestamp millisecond phases
tn = pd.to_datetime(nor.TimeStamp); ta = pd.to_datetime(ab.TimeStamp)
print("normal ms phase uniq", (tn.dt.microsecond//1000 % 100).nunique(), "abn", (ta.dt.microsecond//1000 % 100).nunique())
# amplitude ranges
print(nor[["AI0_Vibration","AI1_Vibration","AI2_Current"]].describe().round(4).to_string())
print(ab[["AI0_Vibration","AI1_Vibration","AI2_Current"]].describe().round(4).to_string())
# lag-1 autocorr of current within file
def seg_ids(df):
    t = pd.to_datetime(df.TimeStamp); d = t.diff().dt.total_seconds(); n = (d.sub(.1).abs() > .02).fillna(False).to_numpy(); n[0] = False; return np.cumsum(n)
for name, df in (("normal", nor), ("abn", ab)):
    s = seg_ids(df); x = df.AI2_Current.to_numpy(); same = s[1:] == s[:-1]
    print(name, "current lag1 within seg", round(float(np.corrcoef(x[1:][same], x[:-1][same])[0, 1]), 4),
          "| 2nd diff RMS / SD", round(float(np.sqrt(np.mean((x[2:]-2*x[1:-1]+x[:-2])[(s[2:] == s[:-2])]**2))/x.std()), 4))
