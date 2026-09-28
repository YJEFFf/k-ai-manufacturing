"""평가관 04 cycle2 round2: 수집 시각의 작은 흔들림(지터)이 현장 적용에 주는 영향.

대회 자료는 기록 안 시각 간격이 정확히 0.1초다. 기록 경계는 |Δt − 0.1| > GAP_TOL(1e-6초)로 정한다(model.layout, press.data).
PC·PLC 수집에서 흔한 ±1~2 ms 흔들림을 시각에만 넣고(센서 값은 그대로) 기록 수·미탐 행·정상 알림·경고 여부를 본다.
실행(yejun/에서): OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python analysis/press_rubric_review/cycle2/round2/judge04_jitter.py
쓰는 파일: 이 폴더의 judge04_jitter.json. 저장 모델은 로컬 artifact(원본 재학습본과 해시 동일).
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
sys.path.insert(0, str(YEJUN / "press_guard"))
from model import D, HERE as GUARD, load_bundle, cases  # noqa: E402

model = load_bundle(GUARD / "artifacts" / "guard_B.json")
normal, abnormal, _ = D.load()
test = D.split_normal(normal, D.segments(normal), "B")["test"]


def jitter(frame, ms, seed):
    t = pd.to_datetime(frame[D.TIME])
    g = frame.copy()
    if ms:
        t = t + pd.to_timedelta(np.random.default_rng(seed).integers(-ms, ms + 1, len(t)), unit="ms")
    g[D.TIME] = t.dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


out = {}
# 원본 시각 간격: 기록 안 간격이 정확히 0.1초인지(흔들림이 있는지)
for name, f in (("normal", normal), ("abnormal", abnormal)):
    d = pd.to_datetime(f[D.TIME]).diff().dt.total_seconds().dropna()
    dev = (d - D.DT).abs()
    out[f"raw_spacing_{name}"] = dict(intervals=int(len(d)), exact_0_1s=int((dev <= 1e-6).sum()),
                                     near_0_1s_not_exact=int(((dev > 1e-6) & (dev <= .05)).sum()), gaps_over_50ms=int((dev > .05).sum()))
for ms in (0, 1, 2):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pn = model.predict(D.inputs_only(jitter(test, ms, 0)), .01)
        pa = model.predict(D.inputs_only(jitter(abnormal, ms, 1)), .01)
    out[f"jitter_pm{ms}ms"] = dict(normal_records=int(pn.record_id.nunique()), abnormal_records=int(pa.record_id.nunique()),
                                   abnormal_rows_scored_with_dynamics=int(pa.g_dynamics.notna().sum()),
                                   abnormal_rows_scored_with_waveform=int(pa.g_waveform.notna().sum()),
                                   abnormal_fn_rows=int((pa.alarm == 0).sum()), abnormal_rows=len(pa),
                                   normal_alarm_rows=int(pn.alarm.sum()), normal_cases=int(len(cases(pn))) if pn.alarm.any() else 0,
                                   status_not_ok=int((pn.status != "ok").sum() + (pa.status != "ok").sum()),
                                   warnings=[str(x.message)[:120] for x in w])
# OPERATIONS 1단계(재보정·수락 검사)를 ±1 ms 흔들림이 있는 정상 0~479구간으로 실행(임시 폴더)
import os, subprocess, tempfile  # noqa: E402
tmp = Path(tempfile.mkdtemp(prefix="judge04_c2r2_jitter_"))
seg_all = D.segments(normal)
site = jitter(D.inputs_only(normal[seg_all < 480]), 1, 2)
site.to_csv(tmp / "normal_jitter.csv", index=False)
env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
r = subprocess.run([sys.executable, str(GUARD / "recalibrate.py"), "--normal", str(tmp / "normal_jitter.csv"), "--out", str(tmp / "site.json")],
                   cwd=YEJUN, env=env, capture_output=True, text=True)
rep = json.loads((tmp / "site_report.json").read_text(encoding="utf-8")) if (tmp / "site_report.json").exists() else {}
out["recalibrate_jitter_pm1ms"] = dict(returncode=r.returncode, stdout=r.stdout.strip()[-700:], stderr=r.stderr.strip()[-300:],
                                       units=rep.get("units"), passed=rep.get("passed"), saved=rep.get("model_saved"), tmp=str(tmp))
(HERE / "judge04_jitter.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1))
