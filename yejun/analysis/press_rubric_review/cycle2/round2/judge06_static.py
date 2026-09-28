"""평가관 06 사이클2 2회차 — 정적 이식성 점검(ast 기반). 저장소는 읽기만 하고 결과는 이 폴더의 judge06_static.json에 쓴다.

대상: 기준 커밋(git show)의 파이썬 파일 가운데 최종 패키지 목록(press_guard/tools/package_manifest.py GROUPS)에 드는 폴더 전체
      + 팀 정적 시험(test_portability.py)의 범위. 커밋본을 읽으므로 작업 트리 변경과 무관하다.
점검
 1) 인코딩 없는 텍스트 입출력: open()/io.open/codecs.open(바이너리 모드 제외), 모든 .open(), .read_text(), .write_text(),
    tempfile.NamedTemporaryFile/TemporaryFile/SpooledTemporaryFile(텍스트 모드), subprocess(text=True·universal_newlines=True)의 encoding 누락
 2) Unix 전용: import resource/fcntl/termios/pwd/grp/posix, os.fork/os.getuid/os.uname, signal.SIGALRM/SIGKILL
 3) 문서·코드의 절대 경로(/Users/, /opt/anaconda3, /Volumes/, /private/tmp, C:\\)와 POSIX 전용 환경변수 접두 문법
 4) 팀 test_portability.py가 보는 범위와 비교(무엇이 빠지는가)

    OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python judge06_static.py
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
COMMIT = "f5679ca"
UNIX_MODULES = {"resource", "fcntl", "termios", "pwd", "grp", "posix", "crypt", "tty", "pty"}
UNIX_ATTRS = {("os", "fork"), ("os", "getuid"), ("os", "uname"), ("os", "geteuid"), ("signal", "SIGALRM"), ("signal", "SIGKILL")}
PACKAGE_DIRS = ["yejun/press_guard/", "yejun/press_submission/", "yejun/analysis/press_advance/", "yejun/analysis/press_evidence/",
                "yejun/analysis/press_supplement/", "yejun/analysis/press_supervised/", "yejun/analysis/press_selection/",
                "yejun/analysis/package_contract.py"]
EXTRA_DIRS = ["yejun/analysis/press_external/", "yejun/analysis/press_early/", "yejun/analysis/press_dayshift/"]
TEAM_SCOPE = ["yejun/press_guard/", "yejun/press_guard/tools/", "yejun/analysis/press_supplement/", "yejun/analysis/press_evidence/",
              "yejun/analysis/press_supervised/", "yejun/analysis/press_advance/", "yejun/analysis/press_selection/"]
ABS = re.compile(r"(/Users/|/opt/anaconda3|/Volumes/|/private/tmp|[A-Z]:\\\\)")
POSIX_ENV = re.compile(r"^\s*(?:export\s+)?[A-Z_]+=\S+\s+(?:[A-Z_]+=\S+\s+)*(?:/opt/anaconda3/bin/)?python", re.M)


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True).stdout.decode("utf-8")


def files_at_commit() -> list[str]:
    return [f for f in git("ls-tree", "-r", "--name-only", COMMIT, "yejun/").splitlines()]


def team_scanned(rel: str) -> bool:
    """test_portability.python_files(): 각 폴더의 *.py(하위 폴더 제외) + analysis/package_contract.py."""
    if rel == "yejun/analysis/package_contract.py":
        return True
    parent = rel.rsplit("/", 1)[0] + "/"
    return rel.endswith(".py") and parent in TEAM_SCOPE


def kw(call: ast.Call, name: str):
    return next((k.value for k in call.keywords if k.arg == name), None)


def const(node):
    return node.value if isinstance(node, ast.Constant) else None


def mode_of(call: ast.Call, pos: int):
    m = kw(call, "mode")
    if m is None and len(call.args) > pos:
        m = call.args[pos]
    return const(m) if m is not None else "r"


def scan_python(rel: str, src: str) -> list[dict]:
    hits = []
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [dict(file=rel, line=exc.lineno, kind="syntax", text=str(exc))]
    lines = src.splitlines()

    def add(node, kind):
        hits.append(dict(file=rel, line=node.lineno, kind=kind, text=lines[node.lineno - 1].strip()[:140]))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            for n in names:
                if n in UNIX_MODULES:
                    guarded = any(isinstance(p, ast.Try) and node in ast.walk(p) for p in ast.walk(tree))
                    add(node, f"unix_module:{n}" + (":guarded" if guarded else ""))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and (node.value.id, node.attr) in UNIX_ATTRS:
            add(node, f"unix_attr:{node.value.id}.{node.attr}")
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
        has_enc = kw(node, "encoding") is not None
        if name == "open" and (isinstance(f, ast.Name) or owner in ("io", "codecs")):
            m = mode_of(node, 1)
            if m is None:
                add(node, "open:mode_unknown" if not has_enc else "ok")
            elif "b" not in m and not has_enc:
                add(node, "open:no_encoding")
        elif name == "open" and isinstance(f, ast.Attribute):          # Path.open / zipfile.open 등 메서드
            m = mode_of(node, 0)
            if owner in ("zipfile", "tarfile", "gzip", "bz2", "lzma", "webbrowser"):
                continue
            if isinstance(f.value, ast.Name) and f.value.id in ("z", "zf", "zip", "archive"):
                continue
            if (m is None or "b" not in m) and not has_enc:
                add(node, "method_open:no_encoding")
        elif name in ("read_text", "write_text") and not has_enc:
            add(node, f"{name}:no_encoding")
        elif name in ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"):
            m = mode_of(node, 0) if kw(node, "mode") is not None or node.args else "w+b"
            if m and "b" not in m and not has_enc:
                add(node, "tempfile_text:no_encoding")
        elif name in ("run", "check_output", "Popen", "call", "check_call") and owner == "subprocess":
            text = const(kw(node, "text")) or const(kw(node, "universal_newlines"))
            if text and not has_enc:
                add(node, "subprocess_text:no_encoding")
    return [h for h in hits if h["kind"] != "ok"]


def scan_docs(rel: str, text: str) -> list[dict]:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if ABS.search(line):
            out.append(dict(file=rel, line=i, kind="absolute_path", text=line.strip()[:160]))
        if POSIX_ENV.search(line):
            out.append(dict(file=rel, line=i, kind="posix_env_prefix", text=line.strip()[:160]))
    return out


def main():
    files = files_at_commit()
    in_pkg = lambda r: any(r.startswith(d) or r == d for d in PACKAGE_DIRS)
    in_extra = lambda r: any(r.startswith(d) for d in EXTRA_DIRS)
    py_hits, doc_hits, scanned = [], [], []
    for rel in files:
        if not (in_pkg(rel) or in_extra(rel)):
            continue
        if rel.endswith(".py"):
            src = git("show", f"{COMMIT}:{rel}")
            scanned.append(rel)
            for h in scan_python(rel, src):
                h["in_package_list"] = in_pkg(rel)
                h["team_static_test_scans"] = team_scanned(rel)
                py_hits.append(h)
        elif rel.endswith((".md", ".sh", ".txt", ".yml")) and in_pkg(rel) and "/expected/" not in rel:
            for h in scan_docs(rel, git("show", f"{COMMIT}:{rel}")):
                doc_hits.append(h)
    summary = {}
    for h in py_hits:
        key = ("패키지" if h["in_package_list"] else "패키지 밖") + "|" + ("팀 시험 범위" if h["team_static_test_scans"] else "팀 시험 밖") + "|" + h["kind"]
        summary[key] = summary.get(key, 0) + 1
    doc_summary = {}
    for h in doc_hits:
        doc_summary[f"{h['kind']}|{h['file']}"] = doc_summary.get(f"{h['kind']}|{h['file']}", 0) + 1
    result = dict(commit=git("rev-parse", COMMIT).strip(), python_files_scanned=len(scanned),
                  team_scope_files=sum(team_scanned(r) for r in scanned), python_summary=summary, python_hits=py_hits,
                  doc_summary=doc_summary, doc_hits=doc_hits)
    (HERE / "judge06_static.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"기준 {result['commit'][:7]} · 파이썬 {len(scanned)}개(팀 시험 범위 {result['team_scope_files']}개)")
    for k, v in sorted(summary.items()):
        print(f"  {v:3d}  {k}")
    for h in py_hits:
        print(f"    {h['file']}:{h['line']} [{h['kind']}] {h['text']}")
    print("문서:")
    for k, v in sorted(doc_summary.items()):
        print(f"  {v:3d}  {k}")


if __name__ == "__main__":
    main()
