"""현재 점검 콘솔 화면 캡처: serve.py를 임시 포트로 띄우고 헤드리스 Chrome으로 작업 화면·성능 검증 화면을 찍는다.

    PYTHONDONTWRITEBYTECODE=1 python yejun/press_guard/tools/capture_console.py [--chrome <Chrome 실행 파일>]

산출물: outputs/console/console_workspace_v2.png, console_evidence_v2.png, capture.json(그림·웹 코드 해시, Chrome 판).
그림은 글꼴·브라우저 판에 따라 달라지므로 verify 동결 대상이 아니다. 분석 수치는 CSV가 원본이다.
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
OUT = HERE / "outputs" / "console"
CHROME_CANDIDATES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium", "chromium-browser",
                     r"C:\Program Files\Google\Chrome\Application\chrome.exe")
SHOTS = (("console_workspace_v2.png", "/?split=B&alpha=0.01", (1600, 1500)),
         ("console_evidence_v2.png", "/?split=B&alpha=0.01&tab=evidence", (1600, 7400)))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def find_chrome(explicit):
    for c in ([explicit] if explicit else []) + list(CHROME_CANDIDATES):
        if c and (Path(c).is_file() or shutil.which(c)):
            return shutil.which(c) or c
    raise SystemExit("Chrome을 찾지 못했다. --chrome으로 실행 파일을 지정하라")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chrome")
    args = ap.parse_args()
    chrome = find_chrome(args.chrome)
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "PYTHONUTF8": "1"}
    server = subprocess.Popen([sys.executable, str(HERE / "serve.py"), "--port", str(port)], cwd=HERE, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/api/overview", timeout=5).read()
                break
            except OSError:
                time.sleep(.5)
        else:
            raise SystemExit("콘솔 서버가 뜨지 않았다")
        for name, path, (w, h) in SHOTS:
            target = OUT / name
            if target.exists():
                target.unlink()
            with tempfile.TemporaryDirectory() as profile:
                # macOS의 헤드리스 Chrome은 캡처 뒤 끝나지 않을 때가 있어, 파일 크기가 멈추면 종료한다.
                proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                                         f"--window-size={w},{h}", "--virtual-time-budget=30000", f"--screenshot={target}", base + path],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                last, stable, deadline = -1, 0, time.monotonic() + 240
                while time.monotonic() < deadline and proc.poll() is None:
                    size = target.stat().st_size if target.exists() else -1
                    stable = stable + 1 if size == last and size > 0 else 0
                    last = size
                    if stable >= 4:
                        break
                    time.sleep(.5)
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                if not target.exists():
                    raise SystemExit(f"{name}: 캡처 실패")
            print(f"{name}: {target.stat().st_size:,} bytes", flush=True)
        version = subprocess.run([chrome, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
        record = dict(chrome=version, shots={n: dict(url=p, size=list(s), sha256=sha(OUT / n)) for n, p, s in SHOTS},
                      web_code_sha256={f: sha(HERE / "web" / f) for f in ("index.html", "app.js", "style.css")},
                      serve_sha256=sha(HERE / "serve.py"), model_sha256=sha(HERE / "model.py"),
                      note="그림은 글꼴·브라우저 판에 따라 달라져 verify 동결 대상이 아니다")
        (OUT / "capture.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        server.terminate()
        server.wait(timeout=30)


if __name__ == "__main__":
    main()
