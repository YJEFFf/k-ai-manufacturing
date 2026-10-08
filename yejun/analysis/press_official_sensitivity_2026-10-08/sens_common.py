"""공식 코드 사본(claude/code/press/tvt와 같은 계산)을 불러 상수 민감도를 계산하는 공통 함수.

- 공식 코드는 임시 폴더의 사본에서만 import한다(PRESS_OFFICIAL_COPY). claude/ 와 원래 clean-run 폴더는 읽기만 한다.
- 상수 바꾸기: lib.GAP_S·CONFIRM_ROWS·R2_MIN_LEN은 lib 모듈 전역값을 바꾼다(stream_rules·prefix_r2가 호출 때 전역을 읽는다).
  R2_Q는 r2_ref(학습 정상 prefix R²의 분위)를 다시 계산해 평가 함수 인자로 넘긴다(evalcore는 r2_ref를 인자로만 받는다).
  R2_MIN_LEN은 행 표의 prefix_r2 열을 저장된 current로 다시 계산해 바꾼다.
- 07.test_only의 α는 07 모듈 전역 PRIMARY_ALPHA를 바꿔 넘긴다.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import itertools
import json
import os
import platform
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

sys.dont_write_bytecode = True   # 사본 안에 __pycache__를 만들지 않는다

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)   # 제출 ZIP을 새로 풀면 outputs/가 없다
REPO = HERE.parents[2]                                   # 저장소 루트(k-제조데이터)
# 저장소에서는 claude/ 공식 산출물과 대조한다. 제출 ZIP에서는 run_all.py가 같은 실행에서 만든 공식 산출물을 넘긴다.
CLAUDE_TVT = Path(os.environ.get("PRESS_SENS_REFERENCE_TVT", str(REPO / "claude" / "code" / "press" / "tvt")))  # 읽기 전용 대조용
WORK = Path(os.environ.get("PRESS_SENS_WORK", r"C:\Users\junyj\AppData\Local\Temp\press_official_sensitivity_work"))
COPY = Path(os.environ.get("PRESS_OFFICIAL_COPY", str(WORK / "북적북적_code_통합본")))
CLEAN_ORIGINAL = Path(os.environ.get("PRESS_SENS_CLEAN_ORIGINAL",
                                     r"C:\Users\junyj\AppData\Local\Temp\k-manufacturing-official-clean-20261008\unpacked\북적북적_code_통합본"))
TVT = COPY / "code" / "press" / "tvt"

if not (TVT / "lib.py").exists():
    raise SystemExit(f"공식 코드 사본이 없다: {TVT}")
sys.path.insert(0, str(TVT))
import lib       # noqa: E402  공식 lib.py (사본)
import evalcore  # noqa: E402  공식 evalcore.py (사본)

PROTOCOL = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
GRID = PROTOCOL["grid"]
KEYS = ("GAP_S", "CONFIRM_ROWS", "R2_Q", "R2_MIN_LEN")
OFFICIAL = dict(GAP_S=60.0, CONFIRM_ROWS=2, R2_Q=0.005, R2_MIN_LEN=8)
ALPHAS = tuple(PROTOCOL["alphas"])
PRIMARY_ALPHA = PROTOCOL["primary_alpha"]
SPLITS = tuple(lib.SPLITS)
VARIANTS = {"stage1": "v2+H1", "stage2": "v2+H1+H2"}   # 1단계 주의 = v2+R1, 2단계 점검 요청 = v2+R1+R2
REFERENCE = "v2"

# 공식 lib 상수가 이 감사의 '공식값'과 같은지 먼저 확인한다
assert (lib.GAP_S, lib.CONFIRM_ROWS, lib.R2_Q, lib.R2_MIN_LEN) == (OFFICIAL["GAP_S"], OFFICIAL["CONFIRM_ROWS"], OFFICIAL["R2_Q"], OFFICIAL["R2_MIN_LEN"])
assert lib.PRIMARY_ALPHA == PRIMARY_ALPHA and tuple(lib.ALPHAS) == ALPHAS


def load_module(name: str, file: str):
    """숫자로 시작하는 공식 스크립트를 모듈로 불러온다(13_r2_oos_alpha.py의 _load와 같은 방식). main()은 실행하지 않는다."""
    spec = importlib.util.spec_from_file_location(name, TVT / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def grid_points():
    """완전 요인 81점. 순서: GAP_S → CONFIRM_ROWS → R2_Q → R2_MIN_LEN."""
    for g, c, q, m in itertools.product(GRID["GAP_S"], GRID["CONFIRM_ROWS"], GRID["R2_Q"], GRID["R2_MIN_LEN"]):
        yield dict(GAP_S=float(g), CONFIRM_ROWS=int(c), R2_Q=float(q), R2_MIN_LEN=int(m))


def is_official(p: dict) -> bool:
    return all(p[k] == OFFICIAL[k] for k in KEYS)


@contextlib.contextmanager
def lib_constants(gap=None, confirm=None, min_len=None):
    """lib 모듈 전역 상수를 잠시 바꾸고 끝나면 공식값으로 되돌린다."""
    old = (lib.GAP_S, lib.CONFIRM_ROWS, lib.R2_MIN_LEN)
    try:
        if gap is not None:
            lib.GAP_S = float(gap)
        if confirm is not None:
            lib.CONFIRM_ROWS = int(confirm)
        if min_len is not None:
            lib.R2_MIN_LEN = int(min_len)
        yield
    finally:
        lib.GAP_S, lib.CONFIRM_ROWS, lib.R2_MIN_LEN = old


@contextlib.contextmanager
def alpha_07(mod07, alpha):
    """07.test_only는 모듈 전역 PRIMARY_ALPHA를 쓴다. 잠시 α로 바꾼다."""
    old = mod07.PRIMARY_ALPHA
    try:
        mod07.PRIMARY_ALPHA = alpha
        yield
    finally:
        mod07.PRIMARY_ALPHA = old


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    return sha256_bytes(Path(p).read_bytes())


def sha256_lf(p: Path) -> str:
    """줄바꿈을 LF로 맞춘 해시(저장소 작업 트리는 CRLF, 사본은 LF)."""
    return sha256_bytes(Path(p).read_bytes().replace(b"\r\n", b"\n"))


def load_tables() -> dict:
    return {s: pd.read_pickle(TVT / "cache" / f"rows_{s}.pkl") for s in SPLITS}


def load_meta() -> dict:
    return json.loads((TVT / "outputs" / "tvt_scores_meta.json").read_text(encoding="utf-8"))


def candidates_by_name(meta) -> dict:
    """공식 후보 목록(evalcore.candidates, 복잡도 = 01_scores COMPLEXITY)."""
    return {c[0]: c for c in evalcore.candidates(meta["A"]["complexity"])}


def setup_official():
    """lib.setup(사본 루트): 예준 v1·v2·v3 모듈 경로를 넣고 모듈 묶음을 돌려준다(모델 학습 없음)."""
    return lib.setup(COPY)


def train_currents(M) -> dict:
    """분할별 정상 학습 구간의 (matched 양자화 전류, 기록 번호). 01_scores.build_split과 같은 함수로 읽는다."""
    S01 = load_module("tvt_s01_sens", "01_scores.py")
    D = M["D"]
    normal, _, _ = D.load(COPY / "yejun" / "press_submission")
    seg_all = D.segments(normal)
    out = {}
    for sid in SPLITS:
        sp = D.split_normal(normal, seg_all, sid)
        q_tr, seg_tr, _ = S01.frame_rows(M, sp["train"], "train", "normal")
        out[sid] = (q_tr[D.SENSORS[2]].to_numpy(float), seg_tr)
    return out


def prefix_r2_with(min_len: int, current: np.ndarray, rec: np.ndarray) -> np.ndarray:
    """공식 lib.prefix_r2를 R2_MIN_LEN만 바꿔 부른다."""
    with lib_constants(min_len=min_len):
        return lib.prefix_r2(current, rec)


def table_prefix(table: pd.DataFrame, min_len: int) -> np.ndarray:
    """행 표의 저장된 current와 기록 이름(rec)으로 prefix_r2 열을 다시 계산한다. 기록마다 행 순서는 원래 프레임과 같다."""
    return prefix_r2_with(min_len, table["current"].to_numpy(float), table["rec"].to_numpy())


def r2_refs(train_pr2: dict) -> dict:
    """(R2_Q, R2_MIN_LEN) → r2_ref. 01_scores와 같은 식 float(np.nanquantile(학습 prefix R², R2_Q))."""
    return {(float(q), int(m)): float(np.nanquantile(train_pr2[int(m)], float(q))) for q in GRID["R2_Q"] for m in GRID["R2_MIN_LEN"]}


def fp_records(pred: pd.DataFrame) -> dict:
    """test 정상 기록 중 실시간 경보가 1행 이상인 기록 수, test 이상 기록 중 탐지 기록 수."""
    rt = pred["alarm_realtime"].astype(bool)
    per = rt.groupby([pred["subset"], pred["rec"]]).max()
    return dict(test_fp_records=int(per.loc["normal"].sum()), test_normal_records=int(len(per.loc["normal"])),
                test_abn_records_detected=int(per.loc["abnormal"].sum()), test_abn_records=int(len(per.loc["abnormal"])))


def evaluate_point(table, cand, alpha, r2ref, mod07) -> dict:
    """한 격자점·α·변형의 지표. 모두 공식 함수(evaluate, predict_rows, 07.test_only)로 계산한다."""
    te = evalcore.evaluate(table, cand, alpha, "test", r2ref)
    va = evalcore.evaluate(table, cand, alpha, "valid", r2ref)
    pred = evalcore.predict_rows(table, cand, alpha, "test", r2ref)
    rec = fp_records(pred)
    # predict_rows와 evaluate는 같은 _streams 계산이다. 행 FP가 같은지 확인
    y = pred["label"].to_numpy() == 1
    a = pred["alarm_realtime"].to_numpy().astype(bool)
    assert int((a & ~y).sum()) == te["realtime"]["fp"] and int((~a & y).sum()) == te["realtime"]["fn"]
    with alpha_07(mod07, alpha):
        to = mod07.test_only(table, cand[1], cand[2], cand[3], r2ref)
    # 07.test_only의 정상 흐름은 evaluate test와 같다(α 패치가 보이는지 확인)
    assert to["fp"] == te["realtime"]["fp"], "test_only 정상 오경보 행이 evaluate와 다름(α 패치 확인)"
    return dict(test_tp=te["realtime"]["tp"], test_fp_rows=te["realtime"]["fp"], test_fn_rows=te["realtime"]["fn"],
                test_f1=te["realtime"]["f1"], test_record_f1=te["record"]["f1"],
                test_record_tp=te["record"]["tp"], test_record_fp=te["record"]["fp"], test_record_fn=te["record"]["fn"],
                **rec,
                valid_tp=va["realtime"]["tp"], valid_fp_rows=va["realtime"]["fp"], valid_fn_rows=va["realtime"]["fn"], valid_f1=va["realtime"]["f1"],
                valid_record_tp=va["record"]["tp"], valid_record_fp=va["record"]["fp"], valid_record_fn=va["record"]["fn"],
                valid_record_f1=va["record"]["f1"],
                test_only_f1=to["f1"], test_only_fn_rows=to["fn"], test_only_tp=to["tp"])


def patch_visibility_checks(tables, meta, cands, mod07, extra_modules=()) -> dict:
    """상수 패치가 실제 계산에 보이는지: 함수 객체·전역 확인 + 행동 확인."""
    res = {}
    res["evalcore.stream_rules is lib.stream_rules"] = evalcore.stream_rules is lib.stream_rules
    res["evalcore.record_flags is lib.record_flags"] = evalcore.record_flags is lib.record_flags
    res["07.stream_rules is lib.stream_rules"] = mod07.stream_rules is lib.stream_rules
    for name, mod in extra_modules:
        res[f"{name}.stream_rules is lib.stream_rules"] = mod.stream_rules is lib.stream_rules
        if hasattr(mod, "prefix_r2"):
            res[f"{name}.prefix_r2 is lib.prefix_r2"] = mod.prefix_r2 is lib.prefix_r2
    res["lib.stream_rules globals are lib module"] = lib.stream_rules.__globals__ is vars(lib)
    res["lib.prefix_r2 globals are lib module"] = lib.prefix_r2.__globals__ is vars(lib)
    # evalcore가 상수를 값으로 복사해 두지 않았는지(이름이 evalcore 네임스페이스에 없어야 한다)
    res["evalcore has no copied constants"] = not any(hasattr(evalcore, k) for k in ("GAP_S", "CONFIRM_ROWS", "R2_Q", "R2_MIN_LEN"))
    res["07 has no copied rule constants"] = not any(hasattr(mod07, k) for k in ("GAP_S", "CONFIRM_ROWS", "R2_MIN_LEN"))
    # 행동 확인: R1을 사실상 끄면(GAP_S=-1 또는 CONFIRM_ROWS=10^9) 1단계가 v2와 같아야 한다
    for s, t in tables.items():
        r2 = meta[s]["r2_ref"]
        v2 = evalcore.evaluate(t, cands["v2"], PRIMARY_ALPHA, "test", r2)["realtime"]
        on = evalcore.evaluate(t, cands["v2+H1"], PRIMARY_ALPHA, "test", r2)["realtime"]
        with lib_constants(gap=-1.0):
            off_gap = evalcore.evaluate(t, cands["v2+H1"], PRIMARY_ALPHA, "test", r2)["realtime"]
            off_gap07 = mod07.test_only(t, "v2", True, False, r2)
        with lib_constants(confirm=10 ** 9):
            off_conf = evalcore.evaluate(t, cands["v2+H1"], PRIMARY_ALPHA, "test", r2)["realtime"]
        res[f"{s}: GAP_S=-1 -> stage1 == v2"] = off_gap == v2 and on != v2
        res[f"{s}: GAP_S=-1 -> 07.test_only == v2"] = (off_gap07["tp"], off_gap07["fp"], off_gap07["fn"]) == (v2["tp"], v2["fp"], v2["fn"])
        res[f"{s}: CONFIRM_ROWS=1e9 -> stage1 == v2"] = off_conf == v2
        # R2_MIN_LEN = m: 길이 m 이상인 기록은 앞 m-1행만 NaN
        for m in GRID["R2_MIN_LEN"]:
            pr = table_prefix(t, m)
            ok = True
            for r, idx in pd.Series(np.arange(len(t))).groupby(t["rec"].to_numpy()):
                idx = idx.to_numpy()
                nan = np.isnan(pr[idx])
                k = min(m - 1, len(idx))
                ok &= bool(nan[:k].all()) and (len(idx) < m or not nan[k:].any())
            res[f"{s}: R2_MIN_LEN={m} -> first m-1 rows NaN only"] = bool(ok)
    # 끝난 뒤 공식값으로 돌아왔는지
    res["constants restored"] = (lib.GAP_S, lib.CONFIRM_ROWS, lib.R2_MIN_LEN, mod07.PRIMARY_ALPHA) == (
        OFFICIAL["GAP_S"], OFFICIAL["CONFIRM_ROWS"], OFFICIAL["R2_MIN_LEN"], PRIMARY_ALPHA)
    return res


def official_reproduction(tables, meta, cands, mod07, csv_dirs: dict) -> dict:
    """공식 상수에서 v2·v2+H1·v2+H1+H2의 test/valid 결과가 공식 출력과 같은지(정수 일치, F1 1e-12)."""
    res = {"checked": 0, "mismatches": []}
    for label, d in csv_dirs.items():
        test = pd.read_csv(d / "tvt_test.csv")
        valid = pd.read_csv(d / "tvt_valid.csv")
        for s, t in tables.items():
            r2 = meta[s]["r2_ref"]
            for name in ("v2", "v2+H1", "v2+H1+H2"):
                for a in ALPHAS:
                    for regime, ref in (("test", test), ("valid", valid)):
                        got = evalcore.evaluate(t, cands[name], a, regime, r2)
                        for mode, m in got.items():
                            row = ref[(ref.split == s) & (ref.model == name) & (ref["mode"] == mode) & np.isclose(ref.alpha, a)]
                            assert len(row) == 1
                            row = row.iloc[0]
                            res["checked"] += 1
                            if not (int(row.tp) == m["tp"] and int(row.fp) == m["fp"] and int(row.fn) == m["fn"]
                                    and abs(float(row.f1) - m["f1"]) <= 1e-12):
                                res["mismatches"].append(dict(source=label, split=s, model=name, alpha=a, regime=regime, mode=mode,
                                                              official=dict(tp=int(row.tp), fp=int(row.fp), fn=int(row.fn), f1=float(row.f1)), got=m))
        # 이상 흐름을 test부터 따로(07): α 1%
        r1b = pd.read_csv(d / "tvt_r1_baselines.csv")
        for s, t in tables.items():
            for name, (h1, h2) in (("v2+H1", (True, False)), ("v2+H1+H2", (True, True)), ("v2", (False, False))):
                to = mod07.test_only(t, "v2", h1, h2, meta[s]["r2_ref"])
                ref = r1b[(r1b.split == s) & (r1b.model == name)].iloc[0]
                res["checked"] += 1
                if abs(float(ref.test_only_f1) - to["f1"]) > 1e-12:
                    res["mismatches"].append(dict(source=label, split=s, model=name, check="test_only_f1", official=float(ref.test_only_f1), got=to["f1"]))
    res["ok"] = not res["mismatches"]
    return res


def prefix_and_ref_checks(tables, meta, train_pr2_8: dict) -> dict:
    """R2_MIN_LEN 8로 다시 계산한 prefix_r2가 캐시 열과 같고, (0.005, 8) r2_ref가 메타와 같은지."""
    res = {}
    for s, t in tables.items():
        pr = table_prefix(t, 8)
        cached = t["prefix_r2"].to_numpy(float)
        res[f"{s}: prefix_r2(8) == cached (bitwise, NaN positions)"] = bool(np.array_equal(pr, cached, equal_nan=True))
        ref = float(np.nanquantile(train_pr2_8[s], 0.005))
        res[f"{s}: r2_ref(0.005, 8) == meta"] = ref == meta[s]["r2_ref"]
        res[f"{s}: r2_ref recomputed"] = ref
    return res


def cache_hash_check() -> dict:
    sel = json.loads((TVT / "outputs" / "tvt_selection.json").read_text(encoding="utf-8"))
    out = {}
    for s in SPLITS:
        h = sha256_file(TVT / "cache" / f"rows_{s}.pkl")
        out[s] = dict(sha256=h, selection_inputs_sha256=sel["inputs"]["rows_sha256"][s], ok=h == sel["inputs"]["rows_sha256"][s])
    return out


SOURCE_FILES = {
    "tvt": ["lib.py", "evalcore.py", "01_scores.py", "02_select_on_valid.py", "04_validation.py", "07_r1_on_baselines.py",
            "10_threshold_free.py", "13_r2_oos_alpha.py"],
    "yejun": ["yejun/press_guard/model.py", "yejun/press_guard/runtime.py", "yejun/press_submission/press/data.py",
              "yejun/press_submission/press/calibrate.py", "yejun/press_submission/press/scores.py",
              "yejun/press_submission/press/lstm_ae.py", "yejun/analysis/press_master_validation_2026-10-03/core.py"],
}


def environment_record() -> dict:
    """실행 환경 판, 공식 소스 해시(사본 원문·LF 맞춤·claude/ 판 대조), 점수 캐시 해시."""
    pk = {}
    for name in ("numpy", "pandas", "scipy", "scikit-learn", "statsmodels", "torch", "threadpoolctl"):
        try:
            pk[name] = version(name)
        except PackageNotFoundError:
            pk[name] = None
    src = {}
    for f in SOURCE_FILES["tvt"]:
        p, c = TVT / f, CLAUDE_TVT / f
        src[f"code/press/tvt/{f}"] = dict(sha256=sha256_file(p), sha256_lf=sha256_lf(p),
                                         claude_repo_sha256_lf=sha256_lf(c) if c.exists() else None,
                                         same_as_claude_repo_lf=(sha256_lf(c) == sha256_lf(p)) if c.exists() else None,
                                         clean_run_original_sha256=sha256_file(CLEAN_ORIGINAL / "code/press/tvt" / f) if (CLEAN_ORIGINAL / "code/press/tvt" / f).exists() else None)
    for f in SOURCE_FILES["yejun"]:
        p, r = COPY / f, REPO / f
        src[f] = dict(sha256=sha256_file(p), sha256_lf=sha256_lf(p),
                      repo_yejun_sha256_lf=sha256_lf(r) if r.exists() else None,
                      same_as_repo_lf=(sha256_lf(r) == sha256_lf(p)) if r.exists() else None)
    return dict(python=platform.python_version(), executable=sys.executable, platform=platform.platform(), packages=pk,
                env=dict(PYTHONDONTWRITEBYTECODE=os.environ.get("PYTHONDONTWRITEBYTECODE"), PYTHONUTF8=os.environ.get("PYTHONUTF8")),
                official_copy=str(COPY), clean_run_original=str(CLEAN_ORIGINAL), sources=src, score_cache=cache_hash_check(),
                official_outputs={f: dict(copy_sha256=sha256_file(TVT / "outputs" / f),
                                          claude_repo_sha256=sha256_file(CLAUDE_TVT / "outputs" / f) if (CLAUDE_TVT / "outputs" / f).exists() else None)
                                  for f in ("tvt_test.csv", "tvt_valid.csv", "tvt_r1_baselines.csv", "tvt_scores_meta.json",
                                            "tvt_selection.json", "r2_oos_alpha.json")})


def dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=_jsonable) + "\n", encoding="utf-8")


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)
