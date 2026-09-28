"""평가관 06 사이클2 3회차 Q6 — 변조 검출·허용오차·실행 옵션 시험(팀 시험과 다른 변조를 직접 만든다).

한 명령 재현을 마친 사본(기본 Q2 클론)을 임시 폴더에 복사해 그 안에서만 바꾸고, 시나리오마다 원래 파일로 되돌린다.
저장소에는 이 폴더의 judge06_Q6_tamper.json·.log만 쓴다.

 V  press_guard/verify.py(CLI, 같은 기기 경로: 실행 기록 해시)와 compare_predictions(다른 기기 경로: 동결 요약만)의 검출 단위.
    3회차 추가: 사건 알림 열(incident_*)·문자 열(magnitude_sensor·timestamp·probability_source)·근거·단계 열 변경
 C  analysis/package_contract.py --package <4개 패키지>(결과·실행 기록·코드·동결값·그림·허용오차·의존 파일·제자리 재실행)
 S  analysis/press_supplement/verify.py(결과·동결값·실행 옵션 cache_used·cache_version, 시험 UCI ZIP 유무)
 A  analyze.source_hashes()의 v1 비교표 허용오차(1e-6 통과·1e-2 실패)

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python judge06_Q6_tamper.py [원천 루트]
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
BASE = Path(os.environ.get("J06_BASE", "/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/judge06r3"))
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "Q2_venv" / "clone"
WORK = BASE / "Q6_tamper" / "work"
Y = WORK / "yejun"
PY = os.environ.get("PY", "/opt/anaconda3/bin/python")
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
UCI = REPO / "yejun/analysis/press_external/data/hydraulic.zip"
RESULTS: list[dict] = []
LOG = HERE / "judge06_Q6_tamper.log"


def log(msg):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(args, cwd=Y, timeout=1800):
    t = time.monotonic()
    p = subprocess.run([PY if a == "python" else a for a in args], cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    lines = [l for l in (p.stdout + p.stderr).strip().splitlines() if l.strip()]
    return p.returncode, lines, round(time.monotonic() - t, 1)


class Backup:
    """시나리오 동안 바꿀 파일을 보관했다가 되돌린다(없던 파일은 지운다)."""
    def __init__(self, *paths):
        self.paths = [Path(p) for p in paths]
    def __enter__(self):
        self.saved = {p: (p.read_bytes() if p.is_file() else None) for p in self.paths}
        return self
    def __exit__(self, *exc):
        for p, data in self.saved.items():
            if data is None:
                p.unlink(missing_ok=True)
            else:
                p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)


def record(group, sid, what, expect, rc, lines, secs, extra=None):
    ok_expect = (rc == 0) if expect == "pass" else (rc != 0)
    tail = " | ".join(l[:160] for l in lines[-3:])
    RESULTS.append(dict(group=group, id=sid, scenario=what, expect=expect, rc=rc, as_expected=ok_expect, seconds=secs, tail=tail, **(extra or {})))
    log(f"[{group}] {sid} {'기대대로' if ok_expect else '기대와 다름'} (기대 {expect}, rc={rc}, {secs}s) {what}\n      {tail}")


def edit_csv_cell(path: Path, delta: float, row=None, prefer=None):
    x = pd.read_csv(path)
    cols = [c for c in x.columns if pd.api.types.is_float_dtype(x[c]) and np.isfinite(x[c].to_numpy(float)).any()]
    col = prefer if prefer in cols else (cols[len(cols) // 2] if cols else None)
    if col is None:
        raise ValueError(f"{path.name}: 실수 열 없음")
    finite = np.flatnonzero(np.isfinite(x[col].to_numpy(float)))
    i = int(finite[len(finite) // 2]) if row is None else row
    old = float(x.loc[i, col])
    x.loc[i, col] = old + delta
    x.to_csv(path, index=False)
    return col, i, old


def forge_manifest_hash(manifest: Path, rel: str, new_digest: str):
    m = json.loads(manifest.read_text(encoding="utf-8"))
    hit = False
    g = m.get("outputs") or {}
    for k in list(g):
        if k == rel or k.endswith("/" + rel):
            g[k] = new_digest; hit = True
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return hit


# ---------------------------------------------------------------- V: press_guard verify
PROBE = r"""
import sys, json, shutil, tempfile
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "press_guard"); import verify
OUT = Path("press_guard/outputs"); res = {}
def probe(name, fn, target="test_predictions_A.csv"):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); (t / "expected").mkdir()
        shutil.copy2(OUT / "expected" / verify.DIGEST, t / "expected" / verify.DIGEST)
        for n in verify.PREDICTIONS: shutil.copy2(OUT / n, t / n)
        x = pd.read_csv(t / target); desc = fn(x); x.to_csv(t / target, index=False)
        r = {q["file"]: q for q in verify.compare_predictions(t, t / "expected")}[target]
        res[name] = dict(detected=not r["ok"], note=r.get("note", ""), change=desc)
quiet = lambda x: x.index[(x.alarm == 0) & x.score.notna()]
alarm = lambda x: x.index[x.alarm == 1]
def swap_score(x):
    i, j = quiet(x)[10], quiet(x)[200]; x.loc[[i, j], "score"] = x.loc[[j, i], "score"].to_numpy(); return f"rows {i},{j}"
def p_small(x): i = quiet(x)[10]; x.loc[i, "p_value"] += 1e-4; return f"row {i}"
def p_mid(x): i = quiet(x)[10]; x.loc[i, "p_value"] += 1e-2; return f"row {i}"
def score_small(x): i = quiet(x)[10]; x.loc[i, "score"] += 1e-4; return f"row {i}"
def lr(x): i = quiet(x)[10]; x.loc[i, "likelihood_ratio"] *= 1.001; return f"row {i}"
def alarm_flip(x): i = quiet(x)[100]; x.loc[i, "alarm"] = 1; return f"row {i}"
def reason_edit(x): i = alarm(x)[5]; x.loc[i, "reason"] = str(x.loc[i, "reason"]) + "+waveform"; return f"row {i}"
def level_edit(x): i = alarm(x)[5]; x.loc[i, "alert_level"] = 2 if x.loc[i, "alert_level"] != 2 else 1; return f"row {i}"
def inc_swap(x):
    on = x.index[x.incident_notification == 1]; off = x.index[(x.incident_notification == 0) & (x.alarm == 1)]
    i, j = on[0], off[0]; x.loc[[i, j], "incident_notification"] = x.loc[[j, i], "incident_notification"].to_numpy(); return f"notification moved {i}->{j}"
def inc_esc_swap(x):
    on = x.index[x.incident_escalation == 1]; off = x.index[(x.incident_escalation == 0) & (x.alarm == 1)]
    i, j = on[0], off[-1]; x.loc[[i, j], "incident_escalation"] = x.loc[[j, i], "incident_escalation"].to_numpy(); return f"escalation moved {i}->{j}"
def inc_id_swap(x):
    ids = x.incident_id.dropna().unique()
    if len(ids) < 2:
        a = x.index[x.incident_id.notna()]; i = a[0]; j = x.index[x.incident_id.isna()][0]
        x.loc[[i, j], "incident_id"] = x.loc[[j, i], "incident_id"].to_numpy(); return f"id moved {i}->{j}"
    i = x.index[x.incident_id == ids[0]][0]; j = x.index[x.incident_id == ids[1]][0]
    x.loc[[i, j], "incident_id"] = x.loc[[j, i], "incident_id"].to_numpy(); return f"ids swapped {i},{j}"
def sensor_edit(x):
    i = x.index[x.magnitude_sensor.notna()][3]; v = x.loc[i, "magnitude_sensor"]
    x.loc[i, "magnitude_sensor"] = "AI1_Vibration" if v != "AI1_Vibration" else "AI0_Vibration"; return f"row {i}: {v}"
def ts_edit(x): i = quiet(x)[10]; x.loc[i, "timestamp"] = "2099-01-01 00:00:00.000"; return f"row {i}"
def src_edit(x): i = alarm(x)[0]; x.loc[i, "probability_source"] = "forged"; return f"row {i}"
def rows_swapped(x):
    i, j = quiet(x)[10], quiet(x)[11]; x.loc[[i, j]] = x.loc[[j, i]].to_numpy(); return f"rows {i},{j}"
for n, f in [("점수 두 행 맞바꿈", swap_score), ("p값 한 행 +1e-4", p_small), ("p값 한 행 +1e-2", p_mid), ("점수 한 행 +1e-4", score_small),
             ("우도비 한 행 ×1.001", lr), ("인접 두 행 전체 맞바꿈", rows_swapped), ("경보 한 행 0→1", alarm_flip),
             ("근거(reason) 한 행 변경", reason_edit), ("단계(alert_level) 한 행 변경", level_edit),
             ("사건 1단계 알림 행 이동(incident_notification)", inc_swap), ("사건 2단계 알림 행 이동(incident_escalation)", inc_esc_swap),
             ("사건 번호 두 행 맞바꿈(incident_id)", inc_id_swap), ("크기 최대 센서 한 행 변경(magnitude_sensor)", sensor_edit),
             ("시각 한 행 변경(timestamp)", ts_edit), ("확률 출처 한 행 변경(probability_source)", src_edit)]:
    try:
        probe(n, f)
    except Exception as e:
        res[n] = dict(error=f"{type(e).__name__}: {e}")
print(json.dumps(res, ensure_ascii=False))
"""


def v_tests():
    pg = Y / "press_guard"; out = pg / "outputs"
    rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V0", "변조 없음", "pass", rc, lines, s)
    tp = out / "test_predictions_A.csv"
    with Backup(tp):
        x = pd.read_csv(tp); i = int(x.index[(x.label == 0) & (x.alarm == 0)][100]); x.loc[i, "alarm"] = 1; x.to_csv(tp, index=False)
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V1", f"test_predictions_A 정상 행 {i} 경보 0→1", "fail", rc, lines, s)
    with Backup(tp):
        x = pd.read_csv(tp); on = x.index[x.incident_notification == 1]; off = x.index[(x.incident_notification == 0) & (x.alarm == 1)]
        i, j = int(on[0]), int(off[0]); x.loc[[i, j], "incident_notification"] = x.loc[[j, i], "incident_notification"].to_numpy(); x.to_csv(tp, index=False)
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V1b", f"test_predictions_A 사건 1단계 알림을 행 {i}→{j}로 옮김(같은 기기 경로)", "fail", rc, lines, s)
    with Backup(out / "test_predictions_B.csv"):
        (out / "test_predictions_B.csv").unlink()
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V2", "test_predictions_B 삭제", "fail", rc, lines, s)
    f = out / "incidents_B.csv"
    with Backup(f):
        col, i, old = edit_csv_cell(f, 1e-6)
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V3", f"incidents_B.csv {col}[{i}] +1e-6", "fail", rc, lines, s)
    f = out / "expected" / "fp_intensity_v2.csv"
    with Backup(f):
        col, i, old = edit_csv_cell(f, 1e-3)
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V4", f"동결값 expected/fp_intensity_v2.csv {col}[{i}] +1e-3", "fail", rc, lines, s)
    f = pg / "model.py"
    with Backup(f):
        f.write_text(f.read_text(encoding="utf-8") + "\n# 평가관 변조\n", encoding="utf-8")
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V5", "model.py 끝에 주석 한 줄", "fail", rc, lines, s)
    f = pg / "artifacts" / "guard_A.json"
    with Backup(f):
        m = json.loads(f.read_text(encoding="utf-8")); m["state"]["ar2"][0] += 1e-12; f.write_text(json.dumps(m), encoding="utf-8")
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V6", "저장 모델 guard_A.json AR(2) 계수 +1e-12", "fail", rc, lines, s)
    f = out / "expected" / "predictions_digest.json"
    with Backup(f):
        d = json.loads(f.read_text(encoding="utf-8")); d["test_predictions_A.csv"]["alarm_rows"] += 1; f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V6b", "동결 요약 predictions_digest.json의 alarm_rows +1(SHA-256은 그대로)", "fail", rc, lines, s)
    rc, lines, s = run(["python", "-c", PROBE])
    try:
        probes = json.loads(lines[-1])
    except (ValueError, IndexError):
        probes = {"error": lines[-5:]}
    RESULTS.append(dict(group="V", id="V7", scenario="compare_predictions 검출 단위(동결 요약만 대조 = 다른 기기 경로, 실행 기록 해시 경로 제외)", probes=probes))
    log(f"[V] V7 compare_predictions 검출 단위(detected=True면 잡음):")
    for k, v in probes.items():
        log(f"      {k}: {v}")


# ---------------------------------------------------------------- C: package_contract
MAIN_SCRIPT = {"press_evidence": "build_tables.py", "press_supervised": "run.py", "press_advance": "run_experiment.py", "press_selection": "run.py"}


def c_tests():
    for pkg in ("press_evidence", "press_supervised", "press_advance", "press_selection"):
        d = Y / "analysis" / pkg
        c = json.loads((d / "contract.json").read_text(encoding="utf-8"))
        csvs = [r for r in c["outputs"] if r.endswith(".csv")]
        target = csvs[len(csvs) // 2]
        man = d / next(iter(c["manifests"]))
        for mname in c["manifests"]:
            if target in json.dumps(json.loads((d / mname).read_text(encoding="utf-8")).get("outputs", {})):
                man = d / mname
        cmd = ["python", "analysis/package_contract.py", "--package", f"analysis/{pkg}"]
        rc, lines, s = run(cmd); record("C", f"{pkg}:C0", "변조 없음", "pass", rc, lines, s)
        with Backup(d / target):
            col, i, old = edit_csv_cell(d / target, 1e-6)
            rc, lines, s = run(cmd); record("C", f"{pkg}:C1", f"{target} {col}[{i}] +1e-6(실행 기록 그대로)", "fail", rc, lines, s)
        with Backup(d / target, man):
            col, i, old = edit_csv_cell(d / target, 1e-6)
            hit = forge_manifest_hash(man, target, sha(d / target))
            rc, lines, s = run(cmd); record("C", f"{pkg}:C2", f"{target} +1e-6 + 실행 기록 해시 위조(기록 {hit})", "fail", rc, lines, s)
        with Backup(d / target, man):
            col, i, old = edit_csv_cell(d / target, 1e-12)
            hit = forge_manifest_hash(man, target, sha(d / target))
            rc, lines, s = run(cmd); record("C", f"{pkg}:C3", f"{target} +1e-12 + 실행 기록 해시 위조(허용오차 1e-9 안, 설계상 통과)", "pass", rc, lines, s)
        last = csvs[-1]
        with Backup(d / last):
            (d / last).unlink()
            rc, lines, s = run(cmd); record("C", f"{pkg}:C4", f"{last} 삭제", "fail", rc, lines, s)
        script = d / MAIN_SCRIPT[pkg]
        with Backup(script):
            script.write_text(script.read_text(encoding="utf-8") + "\n# 평가관 변조\n", encoding="utf-8")
            rc, lines, s = run(cmd); record("C", f"{pkg}:C5", f"{MAIN_SCRIPT[pkg]} 끝에 주석 한 줄", "fail", rc, lines, s)
        exp = d / "expected" / target
        with Backup(exp):
            col, i, old = edit_csv_cell(exp, 1e-3)
            rc, lines, s = run(cmd); record("C", f"{pkg}:C6", f"동결값 expected/{target} +1e-3", "fail", rc, lines, s)
        mm = json.loads(man.read_text(encoding="utf-8"))
        dep_groups = [g for g, rule in c["manifests"][man.name].get("groups", {}).items() if rule == "auto"]
        dep = None
        for g in dep_groups:
            for k in (mm.get(g) or {}):
                for b in (d, Y, WORK, Y / "analysis"):
                    if (b / k).is_file() and (b / k).suffix in (".csv", ".py") and not k.endswith(MAIN_SCRIPT[pkg]):
                        dep = b / k; break
                if dep: break
            if dep: break
        if dep:
            with Backup(dep):
                dep.write_bytes(dep.read_bytes() + b"\n")
                rc, lines, s = run(cmd); record("C", f"{pkg}:C7", f"의존 파일 {dep.relative_to(WORK)} 끝에 빈 줄", "fail", rc, lines, s)
    d = Y / "analysis" / "press_evidence"
    figs = sorted((d / "figures").glob("*.png"))
    fig, other = figs[0], figs[1]
    man = d / "diagnostics_manifest.json"
    rel = fig.relative_to(d).as_posix()
    if rel not in json.dumps(json.loads(man.read_text(encoding="utf-8")).get("outputs", {})):
        man = d / "manifest.json"
    with Backup(fig, man):
        shutil.copy2(other, fig)
        hit = forge_manifest_hash(man, rel, sha(fig))
        rc, lines, s = run(["python", "analysis/package_contract.py", "--package", "analysis/press_evidence"])
        record("C", "press_evidence:C8", f"그림 {fig.name}을 {other.name}로 바꾸고 실행 기록 해시 위조(기록 {hit}; 설계상 그림 내용은 비교하지 않음)", "pass", rc, lines, s)
    with Backup(fig):
        fig.unlink()
        rc, lines, s = run(["python", "analysis/package_contract.py", "--package", "analysis/press_evidence"])
        record("C", "press_evidence:C9", f"그림 {fig.name} 삭제", "fail", rc, lines, s)
    snap = WORK.parent / "evidence_snapshot"
    if snap.exists(): shutil.rmtree(snap)
    shutil.copytree(d, snap)
    rc, lines, s = run(["python", "analysis/package_contract.py", "--package", "analysis/press_evidence", "--rerun"], timeout=2400)
    record("C", "press_evidence:C10", "--rerun(build_tables·build_diagnostics 제자리 재실행 후 비교)", "pass", rc, lines, s)
    shutil.rmtree(d); shutil.copytree(snap, d)


# ---------------------------------------------------------------- S: supplement verify
def s_tests():
    sup = Y / "analysis" / "press_supplement"
    ext = Y / "analysis" / "press_external" / "data"
    had_zip = (ext / "hydraulic.zip").is_file()
    rc, lines, s = run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "analysis/press_supplement/test_contract.py"])
    record("S", "S0a", f"보완 계약 시험(UCI ZIP {'있음' if had_zip else '없음'})", "pass", rc, lines, s)
    if not had_zip:
        ext.mkdir(parents=True, exist_ok=True); shutil.copy2(UCI, ext / "hydraulic.zip")
    rc, lines, s = run(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "analysis/press_supplement/test_contract.py"])
    record("S", "S0b", "보완 계약 시험(UCI ZIP 넣음)", "pass", rc, lines, s)
    cmd = ["python", "analysis/press_supplement/verify.py"]
    rc, lines, s = run(cmd + ["--strict"]); record("S", "S1", "변조 없음(E1·E2·E3, ZIP 있음, --strict)", "pass", rc, lines, s)
    f = sup / "e1_summary.csv"
    with Backup(f):
        col, i, old = edit_csv_cell(f, 1e-6)
        rc, lines, s = run(cmd); record("S", "S2", f"e1_summary.csv {col}[{i}] +1e-6", "fail", rc, lines, s)
    f = sup / "expected" / "e3_curve.csv"
    with Backup(f):
        col, i, old = edit_csv_cell(f, 1e-3)
        rc, lines, s = run(cmd); record("S", "S3", f"동결값 expected/e3_curve.csv {col}[{i}] +1e-3", "fail", rc, lines, s)
    f = sup / "e2_manifest.json"
    with Backup(f):
        m = json.loads(f.read_text(encoding="utf-8")); m["config"]["cache_used"] = not m["config"]["cache_used"]; f.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        rc, lines, s = run(cmd); record("S", "S4", "e2_manifest config.cache_used 반전(결과 무관 옵션)", "pass", rc, lines, s)
    with Backup(f):
        m = json.loads(f.read_text(encoding="utf-8")); m["config"]["cache_version"] = "uci10hz-v2"; f.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        rc, lines, s = run(cmd); record("S", "S5", "e2_manifest config.cache_version 변경", "fail", rc, lines, s)
    g = Y / "press_guard" / "artifacts" / "guard_B.json"
    with Backup(g):
        mm = json.loads(g.read_text(encoding="utf-8")); mm["state"]["ar2"][0] += 1e-12; g.write_text(json.dumps(mm), encoding="utf-8")
        rc, lines, s = run(cmd); record("S", "S6", "보완 실험이 쓰는 저장 모델 guard_B.json AR(2) 계수 +1e-12", "fail", rc, lines, s)


# ---------------------------------------------------------------- A: analyze v1 비교표 허용오차(R9)
def a_tests():
    table = Y / "press_submission" / "outputs" / "model_comparison_all.csv"
    code = r"""
import sys; sys.path.insert(0, "press_guard")
import analyze
try:
    analyze.source_hashes(); print("RESULT pass")
except ValueError as e:
    print("RESULT fail", str(e)[:400])
"""
    def probe(sid, what, expect):
        rc, lines, s = run(["python", "-c", code])
        verdict = next((l for l in lines if l.startswith("RESULT")), "RESULT ?")
        record("A", sid, what, expect, 0 if verdict.startswith("RESULT pass") else 1, [verdict], s)
    probe("A0", "변조 없음", "pass")
    x = pd.read_csv(table)
    lstm = x.index[x.model.astype(str).str.contains("lstm", case=False)]
    fcol = next(c for c in x.columns if c.startswith("f1"))
    for sid, delta, expect in (("A1", 1e-6, "pass"), ("A2", 1e-2, "fail")):
        with Backup(table):
            y = pd.read_csv(table); y.loc[lstm[0], fcol] = y.loc[lstm[0], fcol] + delta; y.to_csv(table, index=False)
            probe(sid, f"v1 비교표 LSTM 행({x.loc[lstm[0], 'model']}) {fcol} +{delta:g}", expect)


def main():
    LOG.write_text("", encoding="utf-8")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.parent.mkdir(parents=True, exist_ok=True)
    t = time.monotonic()
    shutil.copytree(SRC / "yejun", Y, ignore=shutil.ignore_patterns(".git"))
    log(f"Q6 시작 {time.strftime('%F %T')} 원천 {SRC} → 작업 사본 {WORK} (복사 {time.monotonic() - t:.1f}s)")
    for fn in (v_tests, c_tests, s_tests, a_tests):
        try:
            fn()
        except Exception as exc:
            log(f"!! {fn.__name__} 중단: {type(exc).__name__}: {exc}")
            RESULTS.append(dict(group=fn.__name__, id="ERROR", scenario=str(exc)))
    bad = [r for r in RESULTS if r.get("as_expected") is False]
    (HERE / "judge06_Q6_tamper.json").write_text(json.dumps(dict(source=str(SRC), results=RESULTS, unexpected=len(bad)), ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Q6 끝 {time.strftime('%F %T')} · 시나리오 {sum('as_expected' in r for r in RESULTS)}개 중 기대와 다름 {len(bad)}개 · {time.monotonic() - t:.0f}s")


if __name__ == "__main__":
    main()
