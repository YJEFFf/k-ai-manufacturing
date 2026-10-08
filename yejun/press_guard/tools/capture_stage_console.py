"""두 단계 경보 콘솔 화면 캡처: stage_console.py를 임시 포트로 띄우고 헤드리스 Chrome으로 찍는다(기존 capture_console.py와 같은 방식).

    PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/tools/capture_stage_console.py [--chrome <Chrome>] [--data-root <원본 CSV 폴더>] [--artifacts <모델 폴더>]

- 원본: --data-root가 없으면 press_submission/data, 그다음 저장소의 데이터셋/ 아래에서 해시가 맞는 CSV를 찾는다.
- 모델: --artifacts가 없고 press_guard/artifacts에 저장 모델이 없으면 동결 사본(outputs/expected/guard_*.json·probability_*.json)을
  임시 폴더에 복사해 쓴다. 동결 사본으로도 제출 예측 파일의 1·2단계 열이 시험 행마다 같다(analysis/press_stage_replay_2026-10-08/README.md).
- 산출물(outputs/console/): console_workspace_stage.png(분할 B, α 1%: 이상 사건의 2단계·R1 이어받음), console_workspace_stage_r2.png
  (정상 기록의 1단계 주의와 R2 보류), console_workspace_stage_r1_alpha5.png(비교 α 5% 정상: R1 이어받음·해제),
  console_evidence_stage.png(정상 운전 경보량·되풀이 기준·재생 대조), capture_stage.json(그림·코드 해시, Chrome 판, 선택한 사건).
  그림은 글꼴·브라우저 판에 따라 달라져 동결 대상이 아니다. 기존 capture_console.py의 그림·capture.json은 건드리지 않는다.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parents[1]
OUT = HERE / "outputs" / "console"
sys.path.insert(0, str(HERE / "tools"))
from capture_console import find_chrome, free_port, sha  # noqa: E402

NORMAL_SHA = "f2d61cb3b3108f49a3305d2966b3a31f26942ac8af8ffc9eb531b432b945b0a7"
ABNORMAL_RECORD_SHOWN = 11      # 보고서 그림 13(a)와 같은 이상 기록 11


def data_root(explicit):
    if explicit:
        return Path(explicit)
    for root in (REPO / "yejun" / "press_submission", REPO / "데이터셋"):
        for p in root.rglob("press_data_normal.csv") if root.is_dir() else []:
            if hashlib.sha256(p.read_bytes()).hexdigest() == NORMAL_SHA:
                return root
    raise SystemExit("대회 원본 CSV를 찾지 못했다. --data-root로 지정하라")


def artifacts_dir(explicit, tmp):
    if explicit:
        return Path(explicit), "지정 폴더"
    if (HERE / "artifacts" / "guard_A.json").is_file():
        return HERE / "artifacts", "press_guard/artifacts"
    for name in ("guard_A.json", "guard_B.json", "probability_A.json", "probability_B.json"):
        shutil.copy2(HERE / "outputs" / "expected" / name, Path(tmp) / name)
    return Path(tmp), "outputs/expected 동결 사본"


def post(base, body):
    req = urllib.request.Request(base + "/api/analyze", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


def shoot(chrome, base, path, size, target):
    if target.exists():
        target.unlink()
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                                 f"--window-size={size[0]},{size[1]}", "--virtual-time-budget=30000", f"--screenshot={target}", base + path],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        last, stable, deadline = -1, 0, time.monotonic() + 240
        while time.monotonic() < deadline and proc.poll() is None:
            now = target.stat().st_size if target.exists() else -1
            stable = stable + 1 if now == last and now > 0 else 0
            last = now
            if stable >= 4:
                break
            time.sleep(.5)
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    if not target.exists():
        raise SystemExit(f"{target.name}: 캡처 실패")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chrome")
    ap.add_argument("--data-root")
    ap.add_argument("--artifacts")
    args = ap.parse_args()
    chrome = find_chrome(args.chrome)
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        arts, arts_note = artifacts_dir(args.artifacts, tmp)
        port = free_port()
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "PYTHONUTF8": "1"}
        server = subprocess.Popen([sys.executable, str(HERE / "stage_console.py"), "--port", str(port), "--data-root", str(data_root(args.data_root)),
                                   "--artifacts", str(arts)], cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(240):
                try:
                    urllib.request.urlopen(base + "/api/overview", timeout=10).read()
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise SystemExit("콘솔 서버가 뜨지 않았다")
            # 서버 캐시를 데우고 찍을 사건을 라벨 없이 정한다(화면에 보이는 값과 같은 API 결과)
            mixed = post(base, {"split": "B", "alpha": 0.01, "dataset": "mixed"})
            l2 = min((c for c in mixed["incidents"] if c["level"] == 2), key=lambda c: c["priority_rank"])
            cases = sorted((c for c in mixed["cases"] if c["incident_id"] == l2["incident_id"]), key=lambda c: c["first_row"])
            first_rec = min(c["record_id"] for c in cases)
            k_abn = next(i for i, c in enumerate(cases, 1) if c["record_id"] == first_rec + ABNORMAL_RECORD_SHOWN)
            r2 = min((c for c in mixed["incidents"] if c["level"] == 1 and c["r2_hold_rows"] > 0), key=lambda c: c["first_row"])
            a5 = post(base, {"split": "B", "alpha": 0.05, "dataset": "normal"})
            # R1 해제가 있는 사건 가운데 2단계(점검 요청)를 먼저: 보고서 3.2절의 '기록 446 경보가 447 앞 7행으로 번짐'과 같은 경우
            r1 = min((c for c in a5["incidents"] if c["release_rows"] > 0), key=lambda c: (-c["level"], c["first_row"]))
            r1_cases = sorted((c for c in a5["cases"] if c["incident_id"] == r1["incident_id"]), key=lambda c: c["first_row"])
            k_rel = next(i for i, c in enumerate(r1_cases, 1) if c["release_row"] is not None)
            shots = (("console_workspace_stage.png", f"/?split=B&alpha=0.01&incident={l2['incident_id']}&case={k_abn}", (1600, 1560)),
                     ("console_workspace_stage_r2.png", f"/?split=B&alpha=0.01&incident={r2['incident_id']}", (1600, 1560)),
                     ("console_workspace_stage_r1_alpha5.png", f"/?split=B&alpha=0.05&dataset=normal&incident={r1['incident_id']}&case={k_rel}", (1600, 1560)),
                     ("console_evidence_stage.png", "/?split=B&alpha=0.01&tab=evidence", (1600, 2300)))
            for name, path, size in shots:
                shoot(chrome, base, path, size, OUT / name)
                print(f"{name}: {(OUT / name).stat().st_size:,} bytes", flush=True)
            version = subprocess.run([chrome, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
            selected = dict(level2_incident=dict(incident_id=l2["incident_id"], case=k_abn, record_id=cases[k_abn - 1]["record_id"],
                                                 abnormal_record=ABNORMAL_RECORD_SHOWN),
                            r2_incident=dict(incident_id=r2["incident_id"], records=r2["records"], r2_hold_rows=r2["r2_hold_rows"]),
                            r1_release_alpha5=dict(incident_id=r1["incident_id"], case=k_rel, records=r1["records"]))
            record = dict(chrome=version, models=arts_note, selected=selected,
                          shots={n: dict(url=p, size=list(s), sha256=sha(OUT / n)) for n, p, s in shots},
                          web_code_sha256={f: sha(HERE / "web" / f) for f in ("stage.html", "stage.js", "stage.css", "style.css")},
                          code_sha256={f: sha(HERE / f) for f in ("stage_console.py", "stages.py", "serve.py", "model.py")},
                          stats_B_mixed=mixed["stats"], level_counts_B_mixed=mixed["level_counts"],
                          note="그림은 글꼴·브라우저 판에 따라 달라져 동결 대상이 아니다. 기존 v2 콘솔 그림은 capture.json에 있다")
            (OUT / "capture_stage.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            server.terminate()
            server.wait(timeout=30)


if __name__ == "__main__":
    main()
