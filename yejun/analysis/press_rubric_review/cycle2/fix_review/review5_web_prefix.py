"""검토 5: 콘솔 모의 화면(app.js viewNow)의 튄 행 제외 규칙이 파이썬 cases()와 같은가. 시각 오류가 여러 종류 섞인 입력의
관측 접두부마다 Python(Console.analyze)과 app.js 집계를 대조한다(저장소 test_web_prefix.cjs를 사본에서 그대로 쓴다).

    REVIEW_ENV=<사본의 yejun 폴더> OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 python review5_web_prefix.py
입력: 정상 기록 → 경보 기록 → (경보 없는 +1시간 끼운 튐) → 정상 기록 → (시각 결측 뒤 +5초 끼운 튐, 센서 결측 튐) →
이상 50행 가운데 표본 자리를 차지한 +5초 튐 → 120초 중단 뒤 새 기록 첫 행 다음 공백 안의 과거 행 → 정상 기록.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV = Path(os.environ["REVIEW_ENV"])
sys.path.insert(0, str(ENV / "press_guard"))
import numpy as np
import pandas as pd
from model import D, HERE, layout
from serve import Console

console = Console()
normal = D.inputs_only(D.split_normal(console.normal, D.segments(console.normal), "B")["test"])
segment = layout(normal)[1]
rec = {r: normal.loc[segment == r].reset_index(drop=True) for r in (0, 3, 41)}
abn = D.inputs_only(console.abnormal).reset_index(drop=True)


def at(frame, start):
    out = frame.copy().reset_index(drop=True)
    out[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(out)) * .1, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f")
    return out


t = pd.Timestamp("2022-07-12 00:00:00")
rows = []
a = at(rec[0], t); rows.append(a); t += pd.Timedelta(seconds=len(a) * .1 + 2)
b = at(rec[3], t); rows.append(b)
spike1 = at(rec[41].iloc[[5]], pd.Timestamp(b[D.TIME].iloc[-1]) + pd.Timedelta(hours=1)); rows.append(spike1)       # 경보 없는 +1시간 튐(다음은 새 기록 → 1시간 튐이라 예외)
t += pd.Timedelta(seconds=len(b) * .1 + 2)
c = at(rec[41], t); rows.append(c)
last_c = pd.Timestamp(c[D.TIME].iloc[-1])
nat = c.iloc[[1]].copy(); nat[D.TIME] = ""
spike2 = at(rec[0].iloc[[7]], last_c + pd.Timedelta(seconds=5)); rows += [spike2, nat]                               # +5초 튐 뒤 시각 결측 한 행
t = last_c + pd.Timedelta(seconds=.1)
d = at(abn.iloc[100:150], t)
dt = pd.to_datetime(d[D.TIME]); dt.iloc[20] += pd.Timedelta(seconds=5); d[D.TIME] = dt.dt.strftime("%Y-%m-%d %H:%M:%S.%f")   # 표본 자리를 차지한 +5초 튐
rows.append(d)
end_d = pd.Timestamp(d[D.TIME].iloc[-1])
e = at(abn.iloc[400:430], end_d + pd.Timedelta(seconds=120))
past = at(rec[0].iloc[[3]], end_d + pd.Timedelta(seconds=30))
rows += [e.iloc[:1], past, e.iloc[1:]]
f = at(rec[0], pd.Timestamp(e[D.TIME].iloc[-1]) + pd.Timedelta(seconds=3)); rows.append(f)
frame = pd.concat(rows, ignore_index=True)
bad = frame.index[len(a) + len(b)]                     # 첫 튄 행의 센서 하나를 결측으로 바꾼 변형도 따로 본다


def analyze(data):
    return console.analyze(dict(split="B", alpha=.01, prior=.01, dataset="upload", csv=data.to_csv(index=False)))


def compare(frame, label):
    full = analyze(frame)
    ev = [p["time_order_event"] for p in full["points"]]
    cut = set(range(0, len(frame), 7)) | {len(frame) - 1}
    for i, v in enumerate(ev):
        if v:
            cut.update((i - 2, i - 1, i, i + 1, i + 2))
    for cs in full["cases"]:
        cut.update((cs["first_row"] - 1, cs["first_row"], cs["row_to"], cs["row_to"] + 1))
    cut = sorted(x for x in cut if 0 <= x < len(frame))
    prefixes = []
    for cursor in cut:
        r = analyze(frame.iloc[:cursor + 1])
        prefixes.append(dict(cursor=cursor, cases=r["cases"], incidents=r["incidents"], alarm_rows=r["stats"]["alarm_rows"]))
    res = subprocess.run([shutil.which("node"), str(HERE / "test_web_prefix.cjs")], input=json.dumps(dict(full=full, prefixes=prefixes)),
                         text=True, encoding="utf-8", capture_output=True)
    print(f"{label}: 행 {len(frame)}, 시각 순서 부호 {pd.Series(ev).value_counts().to_dict()}, 건 {len(full['cases'])}, 사건 {len(full['incidents'])}, "
          f"접두부 {len(prefixes)}곳 → node 종료 {res.returncode}: {(res.stdout + res.stderr).strip()[:300]}")
    for cs in full["cases"]:
        print(f"    건 {cs['case_uid']}: 사건 {cs['incident_id']} · 경보 {cs['alarm_rows']} · 창 {cs['suspect_from'][11:23] or '열림'} ~ {cs['suspect_to'][11:23] or '열림'}")


compare(frame, "혼합 시각 오류")
variant = frame.copy(); variant.loc[bad, D.SENSORS[1]] = np.nan
compare(variant, "첫 튄 행이 센서 결측(bad_value)")
