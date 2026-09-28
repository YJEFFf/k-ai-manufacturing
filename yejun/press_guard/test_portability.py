"""이식성 정적 검사(루브릭 사이클2 평가관 06 R1): 한국어 Windows(CP949 기본 인코딩)·resource 모듈이 없는 환경에서 멈추지 않는다.

- 텍스트 입출력(read_text·write_text·open)은 모두 encoding을 지정한다.
- Unix 전용 resource 모듈은 runtime.py에서만 조건부로 쓴다.
- CP949 콘솔에서 한글·기호를 출력해도 멈추지 않는다(runtime.setup).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANALYSIS = HERE.parent / "analysis"
V1 = HERE.parent / "press_submission"
# vendor/는 준용 원본의 해시 고정 사본(press/data.py VENDOR_SHA256)이라 고치지 않는다. 그 명령행 main은 우리 경로에서 실행되지 않는다.
PACKAGES = [HERE, HERE / "tools"] + [ANALYSIS / p for p in ("press_supplement", "press_evidence", "press_supervised", "press_advance", "press_selection")] \
    + [V1, V1 / "press", V1 / "tests", V1 / "tools"]


def python_files():
    files = [p for d in PACKAGES if d.exists() for p in sorted(d.glob("*.py"))]
    return files + ([ANALYSIS / "package_contract.py"] if (ANALYSIS / "package_contract.py").exists() else [])


def calls(src, pattern):
    """정규식에 맞는 호출의 괄호 안 전체를 돌려준다(따옴표·중첩 괄호 고려)."""
    for m in re.finditer(pattern, src):
        k, depth, q = m.end(), 1, None
        while depth and k < len(src):
            c = src[k]
            if q:
                if c == "\\":
                    k += 1
                elif c == q:
                    q = None
            elif c in "\"'":
                q = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            k += 1
        yield src[m.start():k]


def test_text_io_declares_encoding():
    bad = []
    for f in python_files():
        src = f.read_text(encoding="utf-8")
        for call in calls(src, r"\.(read_text|write_text)\("):
            if "encoding=" not in call:
                bad.append(f"{f.name}: {call[:60]}")
        for call in calls(src, r"subprocess\.run\("):
            if "text=True" in call and "encoding=" not in call and "git" not in call:
                bad.append(f"{f.name}: {call[:60]}")
        for call in calls(src, r"(?<![\w.])open\("):
            binary = re.search(r"""["'][rwax+]*b[rwax+]*["']""", call)
            if not binary and "encoding=" not in call:
                bad.append(f"{f.name}: {call[:60]}")
    assert not bad, bad


def test_resource_module_only_in_runtime():
    bad = [f.name for f in python_files() if f.name != "runtime.py" and re.search(r"^\s*import resource|^\s*from resource", f.read_text(encoding="utf-8"), re.M)]
    assert not bad, bad


def test_cp949_console_does_not_crash():
    code = "import runtime; runtime.setup(); print('한글 경보 · 2단계 ≥ σ → ✓ 확률 55.0%')"
    env = {**os.environ, "PYTHONIOENCODING": "cp949", "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONUTF8", None)
    proc = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=env, capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    assert "한글 경보".encode("cp949") in proc.stdout



def test_python_version_gate(monkeypatch):
    import runtime
    import pytest
    for bad in ((3, 10, 12, "final", 0), (3, 13, 0, "final", 0)):
        monkeypatch.setattr(sys, "version_info", bad)
        with pytest.raises(SystemExit, match="3.11~3.12"):
            runtime.check_python()
    monkeypatch.setattr(sys, "version_info", (3, 12, 8, "final", 0))
    runtime.check_python()


def test_install_data_from_organizer_zip(tmp_path):
    """주최 측 ZIP(data/*.csv 구조)을 그대로 받아 표준 위치에 둔다. 해시가 다르면 멈춘다(평가관 06 R11)."""
    import pytest
    import runtime
    from model import D
    zips = sorted((HERE.parents[1] / "데이터셋" / "프레스_유압펌프_예지보전").glob("Dataset_*.zip"))
    if not zips:
        pytest.skip("주최 측 ZIP이 이 기기에 없다")
    placed = runtime.install_data(zips[0], tmp_path, D.FILES, D.EXPECTED_SHA256, D.DATA_SUBDIR)
    assert set(placed) == {"normal", "abnormal"}
    n, a, report = D.load(tmp_path)
    assert len(n) == 20000 and len(a) == 600 and all(f["sha256_ok"] for f in report["files"].values())
    with pytest.raises(SystemExit, match="SHA-256"):
        runtime.install_data(zips[0], tmp_path, D.FILES, {k: "0" * 64 for k in D.FILES}, D.DATA_SUBDIR)
