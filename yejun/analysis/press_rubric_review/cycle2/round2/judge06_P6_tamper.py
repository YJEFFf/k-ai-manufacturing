"""평가관 06 사이클2 2회차 P6 — 변조 검출·허용오차·실행 옵션 시험(팀 시험과 다른 변조를 직접 만든다).

한 명령 재현을 마친 사본(기본 P2 클론)을 임시 폴더에 복사해 그 안에서만 바꾸고, 시나리오마다 원래 파일로 되돌린다.
저장소에는 이 폴더의 judge06_P6_tamper.json·.log만 쓴다.

 V  press_guard/verify.py(CLI)와 compare_predictions(행 단위 요약의 검출 단위)
 C  analysis/package_contract.py --package <4개 패키지>(결과·실행 기록·코드·동결값·그림·허용오차·제자리 재실행)
 S  analysis/press_supplement/verify.py(결과·동결값·실행 옵션 cache_used·cache_version, E2 --no-cache 실제 실행, 시험 11+개)
 A  analyze.source_hashes()의 v1 비교표 허용오차(R9: 1e-6 통과·1e-2 실패)와 오류 메시지의 해결 명령이 실제로 푸는가

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python judge06_P6_tamper.py [원천 루트]
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
BASE = Path(os.environ.get("J06_BASE", "/private/tmp/claude-501/-Volumes-YJSSD-----k------/69347b62-83f2-47fa-8d8d-9aa723b0597a/scratchpad/judge06r2"))
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "P2_venv" / "clone"
WORK = BASE / "P6_tamper" / "work"
Y = WORK / "yejun"
PY = os.environ.get("PY", "/opt/anaconda3/bin/python")
ENV = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
UCI = REPO / "yejun/analysis/press_external/data/hydraulic.zip"
RESULTS: list[dict] = []
LOG = HERE / "judge06_P6_tamper.log"


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
    """수치 열 한 칸에 delta를 더한다(가운데 행). 바꾼 (열, 행, 원값)을 돌려준다."""
    x = pd.read_csv(path)
    cols = [c for c in x.columns if pd.api.types.is_float_dtype(x[c]) and np.isfinite(x[c].to_numpy(float)).any()]
    if prefer and prefer in cols:
        col = prefer
    else:
        col = cols[len(cols) // 2] if cols else None
    if col is None:
        raise ValueError(f"{path.name}: 실수 열 없음")
    finite = np.flatnonzero(np.isfinite(x[col].to_numpy(float)))
    i = int(finite[len(finite) // 2]) if row is None else row
    old = float(x.loc[i, col])
    x.loc[i, col] = old + delta
    x.to_csv(path, index=False, float_format=None)
    return col, i, old


def forge_manifest_hash(manifest: Path, rel: str, new_digest: str):
    """실행 기록의 결과 해시를 바뀐 파일에 맞춘다(결과와 실행 기록을 함께 위조한 경우)."""
    m = json.loads(manifest.read_text(encoding="utf-8"))
    hit = False
    for group in ("outputs",):
        g = m.get(group) or {}
        for k in list(g):
            if k == rel or k.endswith("/" + rel):
                g[k] = new_digest; hit = True
    manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return hit


# ---------------------------------------------------------------- V: press_guard verify
def v_tests():
    pg = Y / "press_guard"; out = pg / "outputs"
    rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V0", "변조 없음", "pass", rc, lines, s)
    tp = out / "test_predictions_A.csv"
    with Backup(tp):
        x = pd.read_csv(tp); i = int(x.index[(x.label == 0) & (x.alarm == 0)][100]); x.loc[i, "alarm"] = 1; x.to_csv(tp, index=False)
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V1", f"test_predictions_A 정상 행 {i} 경보 0→1", "fail", rc, lines, s)
    with Backup(out / "test_predictions_B.csv"):
        (out / "test_predictions_B.csv").unlink()
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V2", "test_predictions_B 삭제", "fail", rc, lines, s)
    f = out / "workload_v2.csv"
    with Backup(f):
        col, i, old = edit_csv_cell(f, 1e-6)
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V3", f"workload_v2.csv {col}[{i}] +1e-6", "fail", rc, lines, s)
    f = out / "expected" / "metrics.csv"
    with Backup(f):
        col, i, old = edit_csv_cell(f, 1e-3)
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V4", f"동결값 expected/metrics.csv {col}[{i}] +1e-3", "fail", rc, lines, s)
    f = pg / "model.py"
    with Backup(f):
        f.write_text(f.read_text(encoding="utf-8") + "\n# 평가관 변조\n", encoding="utf-8")
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V5", "model.py 끝에 주석 한 줄", "fail", rc, lines, s)
    f = pg / "artifacts" / "guard_A.json"
    with Backup(f):
        m = json.loads(f.read_text(encoding="utf-8")); m["state"]["ar2"][0] += 1e-12; f.write_text(json.dumps(m), encoding="utf-8")
        rc, lines, s = run(["python", "press_guard/verify.py"]); record("V", "V6", "저장 모델 guard_A.json AR(2) 계수 +1e-12", "fail", rc, lines, s)
    # 행 단위 예측 요약(compare_predictions)의 검출 단위: 실행 기록 해시와 무관하게 동결 요약만 대조하는 경로(다른 기기용 허용오차 경로)
    code = r"""
import sys, json, shutil, tempfile
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "press_guard"); import verify
OUT = Path("press_guard/outputs"); res = {}
def probe(name, fn):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t); (t / "expected").mkdir()
        shutil.copy2(OUT / "expected" / verify.DIGEST, t / "expected" / verify.DIGEST)
        for n in verify.PREDICTIONS: shutil.copy2(OUT / n, t / n)
        x = pd.read_csv(t / "test_predictions_A.csv"); fn(x); x.to_csv(t / "test_predictions_A.csv", index=False)
        r = {q["file"]: q for q in verify.compare_predictions(t, t / "expected")}["test_predictions_A.csv"]
        res[name] = dict(ok=r["ok"], note=r.get("note", ""))
quiet = lambda x: x.index[(x.alarm == 0) & x.score.notna()]
def swap(x):
    i, j = quiet(x)[10], quiet(x)[200]; x.loc[[i, j], "score"] = x.loc[[j, i], "score"].to_numpy()
def p_small(x): x.loc[quiet(x)[10], "p_value"] += 1e-4
def p_mid(x): x.loc[quiet(x)[10], "p_value"] += 1e-2
def score_small(x): x.loc[quiet(x)[10], "score"] += 1e-4
def score_mid(x): x.loc[quiet(x)[10], "score"] += 1e-2
def lr(x): x.loc[quiet(x)[10], "likelihood_ratio"] *= 1.001
def rows_swapped(x):
    i, j = quiet(x)[10], quiet(x)[11]; x.loc[[i, j]] = x.loc[[j, i]].to_numpy()
for n, f in [("점수 두 행 맞바꿈", swap), ("p값 한 행 +1e-4", p_small), ("p값 한 행 +1e-2", p_mid), ("점수 한 행 +1e-4", score_small),
             ("점수 한 행 +1e-2", score_mid), ("우도비 한 행 ×1.001", lr), ("인접 두 행 전체 맞바꿈", rows_swapped)]:
    probe(n, f)
print(json.dumps(res, ensure_ascii=False))
"""
    rc, lines, s = run(["python", "-c", code])
    try:
        probes = json.loads(lines[-1])
    except (ValueError, IndexError):
        probes = {"error": lines[-5:]}
    RESULTS.append(dict(group="V", id="V7", scenario="compare_predictions 검출 단위(동결 요약만 대조, 실행 기록 해시 경로 제외)", probes=probes))
    log(f"[V] V7 compare_predictions 검출 단위: {json.dumps(probes, ensure_ascii=False)}")


# ---------------------------------------------------------------- C: package_contract
MAIN_SCRIPT = {"press_evidence": "build_tables.py", "press_supervised": "run.py", "press_advance": "run_experiment.py", "press_selection": "run.py"}


def c_tests():
    for pkg in ("press_evidence", "press_supervised", "press_advance", "press_selection"):
        d = Y / "analysis" / pkg
        c = json.loads((d / "contract.json").read_text(encoding="utf-8"))
        csvs = [r for r in c["outputs"] if r.endswith(".csv")]
        target = csvs[len(csvs) // 2]
        man = d / next(iter(c["manifests"]))
        # 어느 실행 기록이 target을 담는지 찾는다
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
        # 의존 파일(다른 패키지 결과) 변경: 실행 기록의 auto 묶음 첫 항목
        mm = json.loads(man.read_text(encoding="utf-8"))
        dep_groups = [g for g, rule in c["manifests"][man.name].get("groups", {}).items() if rule == "auto"]
        dep = None
        for g in dep_groups:
            for k in (mm.get(g) or {}):
                for b in (d, Y, WORK, Y / "analysis"):
                    if (b / k).is_file() and (b / k).suffix in (".csv", ".py") and k not in (MAIN_SCRIPT[pkg],) and not k.endswith(MAIN_SCRIPT[pkg]):
                        dep = b / k; break
                if dep: break
            if dep: break
        if dep:
            with Backup(dep):
                dep.write_bytes(dep.read_bytes() + b"\n")
                rc, lines, s = run(cmd); record("C", f"{pkg}:C7", f"의존 파일 {dep.relative_to(Y)} 끝에 빈 줄", "fail", rc, lines, s)
    # 그림: 다른 PNG로 바꾸고 실행 기록 해시를 맞추면(설계상 그림은 존재·크기만 비교) 통과하는가
    d = Y / "analysis" / "press_evidence"
    fig = d / "figures" / "fig_d2a_timeline.png"; man = d / "diagnostics_manifest.json"
    with Backup(fig, man):
        shutil.copy2(d / "figures" / "fig_d2b_blocks.png", fig)
        hit = forge_manifest_hash(man, "figures/fig_d2a_timeline.png", sha(fig))
        rc, lines, s = run(["python", "analysis/package_contract.py", "--package", "analysis/press_evidence"])
        record("C", "press_evidence:C8", f"그림 d2a를 d2b로 바꾸고 실행 기록 해시 위조(기록 {hit}; 설계상 그림 내용은 비교하지 않음)", "pass", rc, lines, s)
    with Backup(fig):
        fig.unlink()
        rc, lines, s = run(["python", "analysis/package_contract.py", "--package", "analysis/press_evidence"])
        record("C", "press_evidence:C9", "그림 d2a 삭제", "fail", rc, lines, s)
    # 제자리 재실행(--rerun): 계약의 명령으로 다시 만들고 비교
    snap = WORK.parent / "evidence_snapshot"
    if snap.exists(): shutil.rmtree(snap)
    shutil.copytree(d, snap)
    rc, lines, s = run(["python", "analysis/package_contract.py", "--package", "analysis/press_evidence", "--rerun"], timeout=1800)
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
    rc, lines, s = run(cmd); record("S", "S1", "변조 없음(E1·E2·E3, ZIP 있음)", "pass", rc, lines, s)
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
    # 실제 E2 --no-cache 실행(임시 폴더에 결과) → 그 폴더를 E2만 비교
    tmp = WORK.parent / "e2_nocache"
    if tmp.exists(): shutil.rmtree(tmp)
    rc, lines, s = run(["python", "analysis/press_supplement/uci_v2.py", "--no-cache", "--out", str(tmp)], timeout=3600)
    record("S", "S6a", "E2 uci_v2.py --no-cache 실행", "pass", rc, lines, s)
    rc, lines, s = run(["python", "analysis/press_supplement/verify.py", "--out", str(tmp), "--experiments", "E2"])
    same = {n: sha(tmp / n) == sha(sup / "expected" / n) for n in ("e2_uci_metrics.csv", "e2_uci_strata.csv", "e2_uci_component_diagnostic_posthoc.csv", "e2_uci_comparison.csv") if (tmp / n).is_file()}
    record("S", "S6b", "E2 --no-cache 결과를 verify(E2)", "pass", rc, lines, s, dict(bytes_equal_to_expected=same))


# ---------------------------------------------------------------- A: analyze v1 비교표 허용오차(R9)
def a_tests():
    v1out = Y / "press_submission" / "outputs"
    table = v1out / "model_comparison_all.csv"
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
        return verdict
    probe("A0", "변조 없음", "pass")
    x = pd.read_csv(table)
    lstm = x.index[x.model.astype(str).str.contains("lstm", case=False)]
    fcol = next(c for c in x.columns if c.startswith("f1"))
    for sid, delta, expect in (("A1", 1e-6, "pass"), ("A2", 1e-2, "fail")):
        with Backup(table):
            y = pd.read_csv(table); y.loc[lstm[0], fcol] = y.loc[lstm[0], fcol] + delta; y.to_csv(table, index=False)
            probe(sid, f"v1 비교표 LSTM 행({x.loc[lstm[0], 'model']}) {fcol} +{delta:g}", expect)
    # 오류 메시지가 권하는 명령(run_all.py --steps 2 --no-baselines)을 그대로 따르면 풀리는가
    snap = WORK.parent / "v1out_snapshot"; v1art = Y / "press_submission" / "artifacts"; snap_art = WORK.parent / "v1art_snapshot"
    for a, b in ((v1out, snap), (v1art, snap_art)):
        if b.exists(): shutil.rmtree(b)
        if a.exists(): shutil.copytree(a, b)
    try:
        (v1out / "predictions_A.csv").unlink()
        verdict = probe("A3", "v1 행별 예측 삭제(선행 단계 누락 상황)", "fail")
        RESULTS[-1]["message_has_fix_command"] = "run_all.py" in verdict and "reproduce.py" in verdict
        rc, lines, s = run(["python", "press_submission/run_all.py", "--steps", "2", "--no-baselines"], timeout=1800)
        record("A", "A4a", "오류 메시지의 해결 명령 실행: python press_submission/run_all.py --steps 2 --no-baselines(yejun/에서)", "pass", rc, lines, s)
        probe("A4b", "해결 명령 뒤 analyze 원본 검사", "pass")
        rc, lines, s = run(["python", "press_submission/run_all.py", "--steps", "2"], timeout=1800)
        record("A", "A5a", "대신 reproduce.py가 쓰는 명령: run_all.py --steps 2", "pass", rc, lines, s)
        probe("A5b", "그 뒤 analyze 원본 검사", "pass")
    finally:
        shutil.rmtree(v1out); shutil.copytree(snap, v1out)
        if snap_art.exists():
            shutil.rmtree(v1art, ignore_errors=True); shutil.copytree(snap_art, v1art)


def main():
    LOG.write_text("", encoding="utf-8")
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.parent.mkdir(parents=True, exist_ok=True)
    t = time.monotonic()
    shutil.copytree(SRC / "yejun", Y, ignore=shutil.ignore_patterns(".git"))
    log(f"P6 시작 {time.strftime('%F %T')} 원천 {SRC} → 작업 사본 {WORK} (복사 {time.monotonic() - t:.1f}s)")
    for fn in (v_tests, c_tests, s_tests, a_tests):
        try:
            fn()
        except Exception as exc:   # 한 묶음이 깨져도 나머지는 돈다
            log(f"!! {fn.__name__} 중단: {type(exc).__name__}: {exc}")
            RESULTS.append(dict(group=fn.__name__, id="ERROR", scenario=str(exc)))
    bad = [r for r in RESULTS if r.get("as_expected") is False]
    (HERE / "judge06_P6_tamper.json").write_text(json.dumps(dict(source=str(SRC), results=RESULTS, unexpected=len(bad)), ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"P6 끝 {time.strftime('%F %T')} · 시나리오 {sum('as_expected' in r for r in RESULTS)}개 중 기대와 다름 {len(bad)}개 · {time.monotonic() - t:.0f}s")


if __name__ == "__main__":
    main()
