"""기기 간 수치 동등성 판정(표준 라이브러리·numpy만 쓴다. 다른 패키지의 검증 도구가 경로로 불러 쓴다).

같은 기기에서는 SHA-256이 같아야 한다. 다른 기기(CPU·수학 라이브러리)에서 다시 학습한 모델 파일은 부동소수 끝자리가 달라
SHA-256이 달라진다(리눅스 x86-64 실측: 원소별 최대 절대 차이 5e-11). 이때 동결 사본(outputs/expected/의 같은 이름 파일)과
모든 수치 원소를 |차이| ≤ 1e-10 + 1e-8·|값|으로, 문자·논리 값은 정확히 비교한다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FROZEN_DIR = HERE / "outputs" / "expected"
RTOL, ATOL = 1e-8, 1e-10


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _flatten(obj, prefix=""):
    out = {}
    if isinstance(obj, dict):
        for k in sorted(obj):
            out.update(_flatten(obj[k], f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list) and obj and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in obj):
        out[prefix] = np.asarray(obj, float)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[prefix] = np.asarray([obj], float)
    elif isinstance(obj, (str, bool)) or obj is None or (isinstance(obj, list) and not obj):
        out[prefix] = obj
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    return out


def _state(path):
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    return state.get("state", state)


def compare_states(now: dict, frozen: dict) -> tuple[bool, str]:
    a, b = _flatten(now), _flatten(frozen)
    if set(a) != set(b):
        return False, f"필드 구성이 다름: {sorted(set(a) ^ set(b))[:5]}"
    for key in sorted(b):
        x, y = a[key], b[key]
        if isinstance(y, np.ndarray) or isinstance(x, np.ndarray):
            if not (isinstance(x, np.ndarray) and isinstance(y, np.ndarray)) or x.shape != y.shape:
                return False, f"{key} 모양이 다름"
            if any(not np.array_equal(f(x), f(y)) for f in (np.isnan, np.isposinf, np.isneginf)):
                return False, f"{key} 비유한 값 위치가 다름"
            ok = np.isfinite(y)
            d = np.abs(x[ok] - y[ok])
            bound = ATOL + RTOL * np.abs(y[ok])
            if len(d) and (d > bound).any():
                i = int(np.argmax(d - bound))
                return False, f"{key} 원소 차이 {d[i]:.3g} > 허용 {bound[i]:.3g}"
        elif x != y:
            return False, f"{key} 값이 다름"
    return True, "SHA-256은 다르지만 모든 원소가 동결 모델과 같음(|차이| ≤ 1e-10 + 1e-8·|값|: 기기 간 부동소수 차이)"


def artifact_equivalent(path, frozen_dir=FROZEN_DIR) -> tuple[bool, str]:
    """path의 모델 파일이 동결 사본(frozen_dir/같은 이름)과 같은가. 사본이 없으면 판정하지 않고 False."""
    path = Path(path)
    frozen = Path(frozen_dir) / path.name
    if not frozen.is_file():
        return False, f"동결 모델 사본 없음: {frozen}"
    if _sha(path) == _sha(frozen):
        return True, "SHA-256 같음"
    return compare_states(_state(path), _state(frozen))


def frozen_sha(name, frozen_dir=FROZEN_DIR):
    """동결 사본의 SHA-256(없으면 None)."""
    frozen = Path(frozen_dir) / name
    return _sha(frozen) if frozen.is_file() else None
