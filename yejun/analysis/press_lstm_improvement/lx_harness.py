"""LSTM 오토인코더 보완 실험의 공통 모듈: 준용 tvt 평가 틀을 그대로 불러 쓰는 부분.

준용의 claude/code/press/tvt(분할, 형식 누수 제거, conformal 보정, 실시간 행 채점, R1)를 import만 한다.
claude/에는 아무것도 쓰지 않는다(yejun/AGENTS.md).
- 바이트코드 생성을 끈다(sys.dont_write_bytecode, 실행할 때 PYTHONDONTWRITEBYTECODE=1도 붙인다).
- 01_scores.build_split이 쓰는 LSTM 캐시 경로(모듈 전역 CACHE)를 이 폴더의 cache/tvt로 돌린다.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TVT = REPO / "claude/code/press/tvt"
DOMAIN_OUT = REPO / "claude/code/press/domain/outputs"
CACHE = HERE / "cache"
OUT = HERE / "outputs"
SPLITS = ("A", "B")
ALPHAS = (0.01, 0.03, 0.05)
PRIMARY_ALPHA = 0.01
TIE = 0.002                      # 준용 02_select_on_valid와 같은 동률 폭
FRAMES = ("valid_normal", "test_normal", "abnormal")   # 01_scores 행 표의 행 순서

_T: dict = {}
_M: dict = {}


def tvt():
    """준용 tvt 모듈(lib, evalcore, 01_scores)을 불러온다. 01_scores의 캐시는 이 폴더로 돌린다."""
    if not _T:
        if str(TVT) not in sys.path:
            sys.path.insert(0, str(TVT))
        import evalcore  # noqa: F401
        import lib
        spec = importlib.util.spec_from_file_location("tvt_s01", TVT / "01_scores.py")
        s01 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s01)
        s01.CACHE = CACHE / "tvt"
        _T.update(lib=lib, evalcore=sys.modules["evalcore"], s01=s01)
    return _T["lib"], _T["evalcore"], _T["s01"]


def setup() -> dict:
    """예준 모듈 묶음(M)과 원자료. 데이터는 yejun/press_submission/data(해시 검증)에서 읽는다."""
    if not _M:
        lib, _, _ = tvt()
        M = lib.setup(REPO)
        normal, abnormal, report = M["D"].load(REPO / "yejun/press_submission")
        M.update(repo=REPO, normal=normal, abnormal=abnormal, load_report=report)
        _M.update(M)
    return _M


def split_inputs(sid: str) -> dict:
    """01_scores.build_split과 같은 전처리로 LSTM 학습·채점 입력을 만든다.

    반환: train=(q, seg), frames={valid_normal|test_normal|abnormal: (q, seg)}, mean·scale(v2 표준화, 예준 LSTM 공통 프로토콜과 같음).
    """
    M = setup()
    _, _, s01 = tvt()
    D, guard = M["D"], M["guard"]
    sp = D.split_normal(M["normal"], D.segments(M["normal"]), sid)
    q_tr, seg_tr, _ = s01.frame_rows(M, sp["train"], "train", "normal")
    q_vn, seg_vn, _ = s01.frame_rows(M, sp["cal"], "valid", "normal")
    q_tn, seg_tn, _ = s01.frame_rows(M, sp["test"], "test", "normal")
    q_ab, seg_ab, _ = s01.frame_rows(M, M["abnormal"], "abn", "abnormal")
    model = guard.GuardModel.fit(sp["train"], sp["cal"], split=sid)
    return dict(train=(q_tr, seg_tr),
                frames={"valid_normal": (q_vn, seg_vn), "test_normal": (q_tn, seg_tn), "abnormal": (q_ab, seg_ab)},
                mean=np.asarray(model.mean, float), scale=np.asarray(model.scale, float), raw=sp)


def base_table(sid: str, rebuild: bool = False):
    """01_scores.build_split의 행 표(v2·v1·베이스라인·lstm20·v3)와 메타. 이 폴더 cache/에 저장해 다시 쓴다."""
    p, pm = CACHE / f"base_{sid}.pkl", CACHE / f"base_{sid}_meta.json"
    if p.exists() and pm.exists() and not rebuild:
        return pd.read_pickle(p), json.loads(pm.read_text(encoding="utf-8"))
    M = setup()
    _, _, s01 = tvt()
    table, meta = s01.build_split(M, M["normal"], M["abnormal"], sid)
    CACHE.mkdir(parents=True, exist_ok=True)
    table.to_pickle(p)
    pm.write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return table, json.loads(pm.read_text(encoding="utf-8"))


def calibrated_columns(name: str, scores: dict, seg_vn: np.ndarray, n_rows: int) -> dict:
    """프레임별 행 점수를 01_scores.calibrate와 같은 방식(검증 정상 기록별 최대 점수 conformal, 검증 정상 행 LOO)으로 p값으로 바꾼다."""
    M = setup()
    _, _, s01 = tvt()
    _, full, loo = s01.calibrate(M, scores["valid_normal"], seg_vn, scores)
    n_vn = len(scores["valid_normal"])
    return {f"{name}|score": np.concatenate([scores[k] for k in FRAMES]),
            f"{name}|p_full": np.concatenate([full[k] for k in FRAMES]),
            f"{name}|p_loo": np.concatenate([loo, np.full(n_rows - n_vn, np.nan)])}


def cand(name: str, h1: bool = False):
    """evalcore 후보 튜플: (이름, 기반 점수 열, R1, R2, 기록 단위 전용, 복잡도). LSTM에는 R2(성분 기반)를 얹지 않는다."""
    return (name + ("+H1" if h1 else ""), name, h1, False, False, 1 + int(h1))


def evaluate(table: pd.DataFrame, name: str, h1: bool, alpha: float, regime: str, r2_ref: float) -> dict:
    """준용 evalcore.evaluate 그대로. regime = 'valid'(LOO) 또는 'test'(valid → test 흐름, test 행만 채점)."""
    _, ev, _ = tvt()
    return ev.evaluate(table, cand(name, h1), alpha, regime, r2_ref)


def predict_rows(table: pd.DataFrame, name: str, h1: bool, alpha: float, regime: str, r2_ref: float) -> pd.DataFrame:
    _, ev, _ = tvt()
    return ev.predict_rows(table, cand(name, h1), alpha, regime, r2_ref)


def sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
