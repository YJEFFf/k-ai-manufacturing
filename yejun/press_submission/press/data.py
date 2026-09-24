"""데이터 로드·검증·기록구간·분할·전처리 — PLAN.md §3 고정 프로토콜의 구현.

- 입력: TimeStamp, AI0_Vibration, AI1_Vibration, AI2_Current. 라벨·파일명·행 번호는 모델 입력에서 제외한다.
- 기록구간: 원래 행 순서에서 abs(Δt−0.1)>1e-6 이면 새 구간(vendor `blocks`와 같은 규칙). 잘못된 행은 앞뒤로 경계가 된다.
- 정상 분할 A: 구간 0~359 학습 / 360~479 보정 / 480~599 평가. B: 0~299 / 300~419 / 420~599.
- 주 전처리 matched: 진동 1e-4, 전류 1.1920929 간격으로 round. 민감도 raw, coarse.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

PROTOCOL_VERSION = "v1"
PACKAGE_DIR = Path(__file__).resolve().parents[1]
DATA_SUBDIR = Path("data") / "3_소성가공_예지보전"
FILES = {"normal": "press_data_normal.csv", "abnormal": "outlier_data.csv"}
EXPECTED_SHA256 = {
    "normal": "f2d61cb3b3108f49a3305d2966b3a31f26942ac8af8ffc9eb531b432b945b0a7",
    "abnormal": "9fad8c238e63dba3257d8be32a32362548955c772171a95c0d2af61b0435ed2e",
}
EXPECTED_ROWS = {"normal": 20000, "abnormal": 600}
EXPECTED_SEGMENTS = {"normal": 600, "abnormal": 21}
SENSORS = ["AI0_Vibration", "AI1_Vibration", "AI2_Current"]
TIME = "TimeStamp"
LABEL = "Equipment_state"
DT = 0.1
GAP_TOL = 1e-6
# split_id -> (vendor 이름, 학습 구간 끝(미포함), 보정 구간 끝(미포함)); 평가 = 나머지
SPLITS = {"A": ("normal_60_20_20", 360, 480), "B": ("normal_50_20_30", 300, 420)}
QUANTIZATION = {
    "raw": None,
    "matched": {"vib": 1e-4, "cur": 1.1920929},
    "coarse": {"vib": 1e-3, "cur": 4 * 1.1920929},
}
VENDOR = PACKAGE_DIR / "vendor" / "press_policy_audit.py"
VENDOR_SHA256 = "4887e4c52bcb9022324225a113d1ca4e54b37a395a0707cd222a72683b4312a0"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def data_dir(root) -> Path:
    return Path(root) / DATA_SUBDIR


def load(root=PACKAGE_DIR, verify: bool = True):
    """원본 두 CSV를 읽는다. verify=True면 SHA-256·행 수가 기대값과 다를 때 실패한다.

    반환: (normal, abnormal, report). report에는 경로·해시·행 수·검증 결과가 들어간다.
    """
    d = data_dir(root)
    frames, report = {}, {"data_dir": str(d), "verified": verify, "files": {}}
    for key, name in FILES.items():
        p = d / name
        if not p.exists():
            raise FileNotFoundError(f"{p} 없음. README의 데이터 배치 절차를 따르거나 --root를 지정한다.")
        digest = sha256_file(p)
        df = pd.read_csv(p)
        info = {"path": str(p), "sha256": digest, "rows": int(len(df)),
                "sha256_expected": EXPECTED_SHA256[key], "sha256_ok": digest == EXPECTED_SHA256[key],
                "rows_expected": EXPECTED_ROWS[key], "rows_ok": len(df) == EXPECTED_ROWS[key]}
        report["files"][key] = info
        if verify and not (info["sha256_ok"] and info["rows_ok"]):
            raise ValueError(f"{name}: 해시 또는 행 수가 기대값과 다르다 {info}")
        frames[key] = df
    return frames["normal"], frames["abnormal"], report


def validate_rows(frame: pd.DataFrame) -> np.ndarray:
    """행 상태: ok / bad_timestamp / bad_value. 필수 열이 없으면 예외. 잘못된 행은 삭제하지 않고 표시만 한다."""
    missing = [c for c in [TIME] + SENSORS if c not in frame.columns]
    if missing:
        raise KeyError(f"필수 열 없음: {missing}")
    t = pd.to_datetime(frame[TIME], errors="coerce")
    values = frame[SENSORS].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    status = np.full(len(frame), "ok", dtype=object)
    status[~np.isfinite(values).all(1)] = "bad_value"
    status[t.isna().to_numpy()] = "bad_timestamp"
    return status


def segments(frame: pd.DataFrame, status: np.ndarray | None = None) -> np.ndarray:
    """기록구간 번호(0부터). vendor blocks와 같은 규칙에 잘못된 행 경계를 더한다."""
    gap = pd.to_datetime(frame[TIME], errors="coerce").diff().dt.total_seconds()
    new = gap.sub(DT).abs().gt(GAP_TOL).fillna(False).to_numpy(bool)
    if status is not None:
        bad = np.asarray(status) != "ok"
        new = new | bad
        new[1:] |= bad[:-1]
        new[0] = False
    return np.cumsum(new)


def segment_positions(seg: np.ndarray):
    """구간 내 위치(0부터)와 구간 길이."""
    s = pd.Series(seg)
    pos = s.groupby(seg).cumcount().to_numpy()
    length = s.groupby(seg).transform("size").to_numpy()
    return pos, length


def split_normal(normal: pd.DataFrame, seg: np.ndarray, split_id: str):
    """정상 데이터를 시간순 구간 번호로 학습/보정/평가로 나눈다."""
    name, train_end, cal_end = SPLITS[split_id]
    ids = np.unique(seg)
    assert ids[0] == 0 and ids[-1] == len(ids) - 1, "구간 번호가 0부터 연속이어야 한다"
    parts = {"train": seg < train_end, "cal": (seg >= train_end) & (seg < cal_end), "test": seg >= cal_end}
    out = {k: normal[m].reset_index(drop=True) for k, m in parts.items()}
    out["name"] = name
    out["segments"] = {k: int(len(np.unique(seg[m]))) for k, m in parts.items()}
    return out


def quantize(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    """전처리 변환. raw는 원값 그대로. matched/coarse는 두 클래스에 같은 간격으로 round."""
    spec = QUANTIZATION[name]
    out = frame.copy()
    if spec is None:
        return out
    for c in SENSORS[:2]:
        out[c] = np.round(out[c] / spec["vib"]) * spec["vib"]
    out[SENSORS[2]] = np.round(out[SENSORS[2]] / spec["cur"]) * spec["cur"]
    return out


def inputs_only(frame: pd.DataFrame) -> pd.DataFrame:
    """추론 입력: TimeStamp + 센서 3열. 라벨·인덱스·파일명은 버린다."""
    return frame[[TIME] + SENSORS].reset_index(drop=True)


def load_vendor():
    """예준 평가 헬퍼(blocks, rms5, cutoff_at_budget, segment_max, summarize_records)를 해시 확인 후 import."""
    digest = hashlib.sha256(VENDOR.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if digest != VENDOR_SHA256:
        raise RuntimeError(f"vendor 파일이 바뀜: {digest}")
    spec = importlib.util.spec_from_file_location("press_vendor", VENDOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.SPLITS == [tuple(SPLITS["A"]), tuple(SPLITS["B"])]
    assert mod.COLS == SENSORS
    return mod


def environment() -> dict:
    """manifest용 실행 환경."""
    import matplotlib
    import scipy
    import sklearn
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__,
            "scipy": scipy.__version__, "matplotlib": matplotlib.__version__,
            "blas": (np.__config__.get_info("blas_opt_info") or {}).get("libraries", None) if hasattr(np.__config__, "get_info") else None,
            "protocol_version": PROTOCOL_VERSION}


def to_jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


def dump_json(obj, path: Path):
    path.write_text(json.dumps(to_jsonable(obj), ensure_ascii=False, indent=2), encoding="utf-8")
