"""J4 위원 현장 모의 자료 생성(임시 폴더에만 쓴다. 저장소에는 이 스크립트만 둔다).

- site_normal.csv: 정상 기록 0~479(새 현장 정상 수집이라고 가정, 재보정용)
- site_normal_x110.csv: 같은 자료의 전류 ×1.10(다른 날 부하 수준이 10% 높은 현장 가정)
- shift_B.csv: 정상 기록 420~599 뒤에 이상 600행을 30초 공백 뒤로 시각을 옮겨 붙인 '교대 중 고장 발생' 파일
- shift_messy.csv: shift_B.csv를 현장 CSV처럼 흐트림(열 순서 변경·불필요 열·'/' 날짜 형식·센서 빈칸 3개·중복 행 1개·시각 ±5 ms 흔들림)
- changes.csv: 운전 조건 변경 기록 1건(monitor --changes)
실행: python j4_field_data.py <원본 데이터 폴더> <출력 폴더>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
S = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
cols = ["TimeStamp"] + S
nrm = pd.read_csv(src / "press_data_normal.csv")
ab = pd.read_csv(src / "outlier_data.csv")
t = pd.to_datetime(nrm.TimeStamp)
seg = np.cumsum(np.r_[False, np.abs(np.diff(t.astype("int64").to_numpy()) - 100_000_000) > 1_000])
fmt = lambda s: s.dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]

site = nrm.loc[seg < 480, cols]
site.to_csv(out / "site_normal.csv", index=False)
x110 = site.copy(); x110[S[2]] = x110[S[2]] * 1.10
x110.to_csv(out / "site_normal_x110.csv", index=False)

shift_n = nrm.loc[seg >= 420, cols].copy()
ta = pd.to_datetime(ab.TimeStamp)
offset = (t[seg >= 420].iloc[-1] + pd.Timedelta(seconds=30)) - ta.iloc[0]
shift_a = ab[cols].copy()
shift_a["TimeStamp"] = fmt(ta + offset)
shift = pd.concat([shift_n, shift_a], ignore_index=True)
shift.to_csv(out / "shift_B.csv", index=False)
labels = np.r_[np.zeros(len(shift_n), int), np.ones(len(shift_a), int)]
pd.Series(labels, name="label").to_csv(out / "shift_B_labels.csv", index=False)

rng = np.random.default_rng(20260930)
messy = shift.copy()
tt = pd.to_datetime(messy.TimeStamp) + pd.to_timedelta(rng.uniform(-5, 5, len(messy)).round(3), unit="ms")
messy["TimeStamp"] = tt.dt.strftime("%Y/%m/%d %H:%M:%S.%f").str[:-3]
for i in rng.choice(len(messy), 3, replace=False):
    messy.loc[i, S[int(rng.integers(0, 3))]] = np.nan
dup = int(rng.integers(100, len(messy) - 100))
messy = pd.concat([messy.iloc[:dup + 1], messy.iloc[[dup]], messy.iloc[dup + 1:]], ignore_index=True)
messy.insert(0, "Equipment_state", 0)
messy = messy[["Equipment_state", "AI2_Current", "TimeStamp", "AI1_Vibration", "AI0_Vibration"]]
messy.to_csv(out / "shift_messy.csv", index=True)

pd.DataFrame(dict(time=[fmt(pd.Series([t[seg >= 420].iloc[0] + pd.Timedelta(minutes=10)])).iloc[0]], note=["금형 교체"])).to_csv(out / "changes.csv", index=False)
print({p.name: sum(1 for _ in open(p, encoding="utf-8")) - 1 for p in sorted(out.glob("*.csv"))})
