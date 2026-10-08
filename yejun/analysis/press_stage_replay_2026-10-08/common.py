"""press_stage_replay 공통: 경로, 원본 자료(해시 확인), 공식 산출물(준용 tvt, 읽기 전용), 포아송 구간, 60초 사건 묶음.

준용 claude/ 코드는 import만 한다. __pycache__가 생기지 않게 sys.dont_write_bytecode를 먼저 켠다(PYTHONDONTWRITEBYTECODE=1과 같음).
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
GUARD = REPO / "yejun" / "press_guard"
# 저장소에서는 claude/ 공식 산출물을 읽는다. 제출 ZIP에서는 run_all.py가 같은 실행에서 만든 code/press 산출물을 넘긴다.
TVT = Path(os.environ.get("PRESS_STAGE_TVT", str(REPO / "claude" / "code" / "press" / "tvt")))
DOMAIN_STATES = Path(os.environ.get("PRESS_STAGE_DOMAIN_STATES",
                                    str(REPO / "claude" / "code" / "press" / "domain" / "outputs" / "06_operating_regime_records.csv")))
DATA_DEFAULT = REPO / "데이터셋"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)   # 제출 ZIP을 새로 풀면 outputs/가 없다
if str(GUARD) not in sys.path:
    sys.path.insert(0, str(GUARD))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import chi2  # noqa: E402

import runtime  # noqa: E402
from model import D  # noqa: E402

SPLITS = ("A", "B")
ABN_VALID_RECORDS = 10           # 이상 앞 10기록 = 검증(lib.ABN_VALID_RECORDS)
E3_ENDS = (180, 240, 300, 360, 420)   # 04 v3_splits·13 folds의 시간순 5창: 학습 < end, 보정 end~end+119, 평가 end+120~end+179
STATE_LABELS = {"quiet": "정숙 구간(연속 저부하)", "busy_low": "변동·저부하", "busy_mid": "변동·중부하",
                "busy_high": "변동·고부하", "busy_short": "변동·짧은 기록(8행 미만)"}
SHIFT_HOURS = 8.0
BENCHMARK_PER_HOUR = 6.0         # ISA-18.2 운전원당 시간당 약 6건 이하 "very likely acceptable"(exida 백서 Table 1, 보고서 참고문헌 [5])


def setup():
    """한 스레드 고정(runtime.setup)과 한글 표준출력."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    return runtime.setup(1)


def load_data(root: Path | None = None, keys=("normal", "abnormal")):
    """원본 CSV를 root 아래에서 찾아 SHA-256을 확인하고 읽는다. 반환: keys 순서의 프레임(기본 (normal, abnormal)).
    keys=("normal",)이면 이상 파일은 열지도 않는다(정상 전용 분석)."""
    root = Path(root or DATA_DEFAULT)
    frames = {}
    for key in keys:
        name = D.FILES[key]
        hits = sorted(p for p in root.rglob(name) if p.is_file())
        good = [p for p in hits if hashlib.sha256(p.read_bytes()).hexdigest() == D.EXPECTED_SHA256[key]]
        if not good:
            raise SystemExit(f"{root}: SHA-256이 대회 원본과 같은 {name}이 없다(--data로 원본 폴더를 지정)")
        frames[key] = pd.read_csv(good[0])
    return tuple(frames[k] for k in keys)


def tvt_modules():
    """준용 tvt의 lib·evalcore(읽기 전용 import). 공식 규칙의 기준 계산에만 쓴다."""
    if str(TVT) not in sys.path:
        sys.path.append(str(TVT))
    import evalcore
    import lib
    return lib, evalcore


def official_predictions(sid: str) -> pd.DataFrame:
    return pd.read_csv(TVT / "outputs" / f"test_predictions_{sid}.csv")


def official_meta() -> dict:
    return json.loads((TVT / "outputs" / "tvt_scores_meta.json").read_text(encoding="utf-8"))


def as_bool(series) -> np.ndarray:
    """예측 파일의 True/False·1/0 열을 bool로."""
    s = pd.Series(series)
    if s.dtype == bool:
        return s.to_numpy()
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0"]).to_numpy()


def poisson_ci(k: int, exposure_h: float, conf: float = 0.95):
    """포아송 사건률(시간당)의 정확(Garwood) 양측 구간."""
    a = 1 - conf
    lo = 0.0 if k == 0 else chi2.ppf(a / 2, 2 * k) / 2
    hi = chi2.ppf(1 - a / 2, 2 * k + 2) / 2
    return lo / exposure_h, hi / exposure_h


def poisson_upper(k: int, exposure_h: float, conf: float = 0.95):
    """단측 상한(보고서 2.5절 경보 운영 지표와 같은 계산: 0건이면 −ln(0.05) = 2.996)."""
    return chi2.ppf(conf, 2 * k + 2) / 2 / exposure_h


def event_ids(ts_ns: np.ndarray, alarm: np.ndarray, gap_s: float = 60.0) -> np.ndarray:
    """60초 묶음 사건 번호(1부터, 경보 없는 행 0). 직전 경보 행과 gap_s를 넘게 떨어진 경보 행이 새 사건을 연다(stages._Events와 같은 규칙)."""
    alarm = np.asarray(alarm, bool)
    out = np.zeros(len(alarm), int)
    idx = np.flatnonzero(alarm)
    if not len(idx):
        return out
    t = np.asarray(ts_ns, "int64")[idx]
    start = np.r_[True, np.diff(t) / 1e9 > gap_s]
    out[idx] = np.cumsum(start)
    return out


def cpu_name() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except (ImportError, OSError):
        return platform.processor() or platform.machine()


def environment() -> dict:
    import scipy
    return dict(python=platform.python_version(), platform=platform.platform(), cpu=cpu_name(), logical_cpus=os.cpu_count(),
                numpy=np.__version__, pandas=pd.__version__, scipy=scipy.__version__, threads=os.environ.get("PRESS_THREADS", "1"))


def jsonable(obj):
    """D.to_jsonable + NaN·±inf → None."""
    obj = D.to_jsonable(obj)
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jsonable(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(obj), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
