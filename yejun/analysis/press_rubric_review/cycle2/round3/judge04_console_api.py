"""평가관 04 cycle2 round3: 콘솔(serve.py)을 127.0.0.1 임시 포트에 띄워 API를 직접 호출하고 반드시 종료한다. 읽기 전용.

실행(yejun/에서):
  OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python \
      analysis/press_rubric_review/cycle2/round3/judge04_console_api.py 2>&1 | tee analysis/press_rubric_review/cycle2/round3/judge04_console_api.log
쓰는 파일: 이 폴더의 judge04_console_api.json. 업로드용 CSV는 시스템 임시 폴더에 만든다.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEJUN = HERE.parents[3]
GUARD = YEJUN / "press_guard"
sys.path.insert(0, str(GUARD))
from model import D, load_bundle  # noqa: E402

T0 = time.time()
TMP = Path(tempfile.mkdtemp(prefix="judge04_c2r3_api_"))
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
res: dict = dict(tmp_dir=str(TMP))


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return dict(http_error=e.code, body=e.read().decode()[:300])


# ---------- 업로드 자료 준비(원본에서)
normal, abnormal, _ = D.load()
seg = D.segments(normal)
testB = D.split_normal(normal, seg, "B")["test"].reset_index(drop=True)


def restamp(frame, start="2026-09-27 08:00:00"):
    g = D.inputs_only(frame).reset_index(drop=True)
    g[D.TIME] = (pd.Timestamp(start) + pd.to_timedelta(np.arange(len(g)) * D.DT, unit="s")).strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


def jitter(frame, ms, seed=0):
    g = D.inputs_only(frame).reset_index(drop=True)
    t = pd.to_datetime(g[D.TIME], format="mixed")
    g[D.TIME] = (t + pd.to_timedelta(np.random.default_rng(seed).uniform(-ms, ms, len(t)) / 1000, unit="s")).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    return g


def shift_to(frame, start):
    g = D.inputs_only(frame).reset_index(drop=True)
    t = pd.to_datetime(g[D.TIME], format="mixed")
    g[D.TIME] = (t - t.iloc[0] + pd.Timestamp(start)).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:-3]
    return g


mB = load_bundle(GUARD / "artifacts" / "guard_B.json")
pB = mB.predict(testB, .01)
rel = pB.record_id.to_numpy()
fa = pB[pB.alarm.eq(1)].groupby("record_id").alarm.sum()
clean = [r for r, g in pB.groupby("record_id") if len(g) == 50 and g.alarm.sum() == 0][:2]
parts, tcur = [], pd.Timestamp("2026-09-27 09:00:00")
for r in (clean[0], int(fa.index[0]), int(fa.index[1]), clean[1]):
    f = shift_to(testB[rel == r], tcur); parts.append(f); tcur = pd.to_datetime(f[D.TIME]).iloc[-1] + pd.Timedelta(seconds=2)
uploads = {
    "continuous_B_plus_abnormal": restamp(pd.concat([testB, abnormal], ignore_index=True)),
    "two_single_row_fa_2s_apart": pd.concat(parts, ignore_index=True),
    "abnormal_jitter_50ms": jitter(abnormal, 50),
    "mixed_B_jitter_2ms": jitter(pd.concat([testB, abnormal], ignore_index=True), 2),
    "mixed_B_no_jitter": D.inputs_only(pd.concat([testB, abnormal], ignore_index=True)),
}

# ---------- 서버
port = free_port()
proc = subprocess.Popen([sys.executable, str(GUARD / "serve.py"), "--port", str(port)], cwd=YEJUN, env=ENV,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
base = f"http://127.0.0.1:{port}"
try:
    for _ in range(240):
        try:
            get(base + "/"); break
        except OSError:
            time.sleep(.5)
    res["port"] = port
    index = get(base + "/").decode()
    appjs = get(base + "/app.js")
    res["static"] = dict(index_has_incident_queue="점검 대기열(사건)" in index, app_js_sha_eq_file=hashlib.sha256(appjs).hexdigest() == hashlib.sha256((GUARD / "web" / "app.js").read_bytes()).hexdigest())
    ov = json.loads(get(base + "/api/overview"))
    ee = pd.DataFrame(ov["expected_effect"])
    mid = ee[ee.case.eq("중간")]
    hl = mid[mid.alert_scenario.str.startswith("비사후") & mid.policy.eq("2단계만 출동")]
    res["overview"] = dict(audit_all_ok=ov["audit"].get("all_ok"), expected_effect_rows=len(ee),
                           shown_mid_rows=mid[["alert_scenario", "policy", "post_hoc", "level2_per_8h", "inspection_hours_per_shift", "breakeven_loss_ratio"]].to_dict("records"),
                           highlighted=hl[["alert_scenario", "level2_per_8h", "inspection_hours_per_shift", "breakeven_loss_ratio"]].to_dict("records"),
                           posthoc_flag_json_type=type(mid.post_hoc.iloc[0]).__name__,
                           monitor_gain_columns=sorted(ov["monitor_gain"][0].keys()) if ov["monitor_gain"] else [],
                           levels_rows=len(ov["levels"]), decision_table_rows=len(ov["decision_table"]))
    print("overview:", json.dumps(res["overview"], ensure_ascii=False)[:900], flush=True)

    def summarize(r):
        if "http_error" in r:
            return r
        inc, cs = pd.DataFrame(r.get("incidents", [])), pd.DataFrame(r.get("cases", []))
        out = dict(level_counts=r["level_counts"], incidents=len(inc), cases=len(cs), warnings=r.get("warnings"), lr_cap=r.get("lr_cap"),
                   segments=r["stats"]["segments"], alarm_rows=r["stats"]["alarm_rows"] if "alarm_rows" in r["stats"] else None)
        if len(cs):
            out.update(case_uid_unique=bool(cs.case_uid.is_unique), distinct_record_ids=int(cs.record_id.nunique()))
        if len(inc):
            capped = inc.max_likelihood_ratio >= (r["lr_cap"] or np.inf) - 1e-6
            out.update(incident_levels=inc.level.tolist(), incident_cases=inc.cases.tolist(), escalation_rows=inc.escalation_row.tolist(),
                       max_probability=sorted(set(inc.max_probability.round(4))), capped_share=float(capped.mean()),
                       quality_actions=sorted(set(inc.quality_action)))
        return out

    calls = {}
    for split in ("A", "B"):
        calls[f"mixed_{split}_a1_pi1"] = summarize(post(base + "/api/analyze", dict(split=split, alpha=.01, prior=.01, dataset="mixed")))
    calls["mixed_B_a1_pi0.1"] = summarize(post(base + "/api/analyze", dict(split="B", alpha=.01, prior=.001, dataset="mixed")))
    calls["mixed_B_a5_pi1"] = summarize(post(base + "/api/analyze", dict(split="B", alpha=.05, prior=.01, dataset="mixed")))
    for name, frame in uploads.items():
        csv = frame.to_csv(index=False)
        (TMP / f"{name}.csv").write_text(csv, encoding="utf-8")
        calls[f"upload_{name}"] = summarize(post(base + "/api/analyze", dict(split="B", alpha=.01, prior=.01, dataset="upload", csv=csv)))
    res["analyze"] = calls
    for k, v in calls.items():
        print(k, json.dumps(v, ensure_ascii=False)[:600], flush=True)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait()
    s = socket.socket()
    closed = s.connect_ex(("127.0.0.1", port)) != 0
    s.close()
    res["server_stopped"] = dict(returncode=proc.returncode, port_closed=closed)
    print("server stopped:", res["server_stopped"], flush=True)
res["elapsed_s"] = round(time.time() - T0, 1)
(HERE / "judge04_console_api.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                               encoding="utf-8")
print("elapsed", res["elapsed_s"])
