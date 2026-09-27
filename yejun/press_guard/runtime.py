"""실행 환경 공통 처리: 스레드 수, 한글 표준출력, 파이썬 판 확인, 입력 자료 배치(주최 측 ZIP·폴더), 실행 환경 기록.

- 스레드: BLAS·OpenMP 스레드를 1개로 고정한다(PRESS_THREADS로 바꿀 수 있다). 결과는 스레드 수와 무관하게 같았지만
  (루브릭 검수 R24·평가관 06), 여러 작업이 동시에 돌 때 과다 구독으로 4~5배 느려진다.
- 표준출력: 한국어 Windows(CP949) 콘솔에서 쓸 수 없는 기호는 바꿔 써서 멈추지 않게 한다. 파일 입출력은 모두 UTF-8이다.
- 파이썬: 3.10~3.12에서 실행·검증했다. 3.13 이상은 고정한 numpy 1.26.4 휠이 없어 설치되지 않는다.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import zipfile
from pathlib import Path

SUPPORTED = ((3, 10), (3, 12))
_LIMITS = None


def setup(threads=None):
    """CLI 시작 때 한 번 부른다."""
    global _LIMITS
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    n = int(threads or os.environ.get("PRESS_THREADS", "1"))
    try:
        from threadpoolctl import threadpool_limits
        _LIMITS = threadpool_limits(n)
    except ImportError:          # threadpoolctl은 scikit-learn 의존성이라 보통 있다
        _LIMITS = None
    return n


def check_python():
    v = sys.version_info[:2]
    if not SUPPORTED[0] <= v <= SUPPORTED[1]:
        raise SystemExit(f"파이썬 {platform.python_version()}: 이 패키지는 3.10~3.12에서 실행·검증했다(권장 3.12, environment.yml). "
                         "3.13 이상은 고정한 numpy 1.26.4 설치 파일이 없다.")


def peak_rss_mb():
    """최대 메모리(MB). Windows처럼 resource 모듈이 없으면 None."""
    try:
        import resource
    except ImportError:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(usage / (1024 ** 2 if sys.platform == "darwin" else 1024), 1)   # macOS는 바이트, Linux는 KB


def environment(base):
    """manifest용 실행 환경: v1 공통 항목 + 실제 BLAS·OpenMP 라이브러리와 스레드 수(threadpoolctl)."""
    env = dict(base)
    try:
        from threadpoolctl import threadpool_info
        env["blas"] = [dict(api=i.get("internal_api"), version=i.get("version"), threads=i.get("num_threads"), user_api=i.get("user_api"))
                       for i in threadpool_info()]
    except ImportError:
        env["blas"] = None
    env["press_threads"] = os.environ.get("PRESS_THREADS", "1")
    return env


def korean_fonts():
    """그림용 한글 글꼴 목록: 이 기기에 있는 것만(macOS·Windows·Linux 이름) + DejaVu Sans."""
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    wanted = ("Apple SD Gothic Neo", "AppleGothic", "Malgun Gothic", "NanumGothic", "Nanum Gothic", "Noto Sans CJK KR", "Noto Sans KR")
    return [f for f in wanted if f in have] + ["DejaVu Sans"]


def install_data(source, root, files, expected_sha256, subdir):
    """주최 측 ZIP(data/*.csv) 또는 두 CSV가 든 폴더에서 원본을 찾아 root/subdir에 둔다. SHA-256이 다르면 멈춘다."""
    import hashlib
    source, target = Path(source), Path(root) / subdir
    target.mkdir(parents=True, exist_ok=True)
    placed = {}
    for key, name in files.items():
        dest = target / name
        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as z:
                members = [m for m in z.namelist() if Path(m).name == name]
                if len(members) != 1:
                    raise SystemExit(f"{source}: {name}을 하나만 찾아야 한다(찾은 수 {len(members)})")
                data = z.read(members[0])
        elif source.is_dir():
            hits = sorted(p for p in source.rglob(name) if p.is_file())
            if not hits:
                raise SystemExit(f"{source}: {name} 없음")
            data = hits[0].read_bytes()
        else:
            raise SystemExit(f"{source}: ZIP 파일이나 폴더가 아니다")
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256[key]:
            raise SystemExit(f"{name}: SHA-256 {digest}가 대회 원본 {expected_sha256[key]}와 다르다")
        if not dest.exists() or hashlib.sha256(dest.read_bytes()).hexdigest() != digest:
            dest.write_bytes(data)
        placed[key] = str(dest)
    return placed


def copy_tree(src, dst, ignore=()):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*ignore), dirs_exist_ok=True)
