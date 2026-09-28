"""분석 패키지 공용 검증 계약 — 루브릭 사이클2 평가관 06 R8.

    python analysis/package_contract.py --package analysis/press_evidence            # 실행 기록 무결성 + 동결 기대값 비교
    python analysis/package_contract.py --package analysis/press_evidence --freeze   # 무결성이 통과한 실행만 expected/로 동결
    python analysis/package_contract.py --package analysis/press_evidence --rerun    # contract.json의 명령으로 제자리 재실행 후 비교
    python analysis/package_contract.py --package analysis/press_supervised --out <폴더>  # 다른 폴더에 다시 만든 결과를 비교

yejun/ 에서 실행한다(경로는 yejun 기준 또는 절대 경로). 종료 코드: 0 통과, 1 실패, 2 동결 거부·계약 오류.

패키지 폴더의 contract.json
- outputs: 결과 파일(패키지 기준 상대 경로). .csv는 수치 열 허용오차·문자 열 정확 비교, .json은 meta_keys를 뺀 정확 비교,
  그림(.png·.jpg)은 존재·크기만 본다(글꼴·렌더러에 따라 바이트가 달라진다). 그 밖의 텍스트는 정확 비교.
- manifests: {실행 기록 파일: {"groups": {해시 묶음 키: 경로 규칙}, "scalars": {키: 파일}, "nested": {키: 필드}}}
    경로 규칙 "outputs"  결과 파일(패키지 기준. 'yejun/analysis/<패키지>/' 접두는 떼어 낸다)
             "data"     대회 원본(normal·abnormal → press_submission/data/3_소성가공_예지보전/)
             "guard"    press_guard/artifacts/<이름>
             "auto"     패키지 → yejun → 저장소 루트 → yejun/analysis 순서로 처음 있는 파일
    scalars 값: yejun 기준 파일 경로 또는 "@v1_code"(press_submission 코드 묶음 해시 press.validation.code_sha256)
    nested: {"inputs.files": "sha256"}처럼 {이름: {필드: 해시}} 묶음(이름은 "data" 규칙으로 찾는다)
- local_outputs: Git에서 뺀 결과(행 단위 원표 등). 있으면 실행 기록 해시와 같아야 하고, 동결에는 사본 대신 해시·행 수·열만 남긴다.
  없으면(갓 받은 사본) 실패로 세지 않고 재실행으로 생긴다고 알린다.
- tolerance: 수치 열 허용오차(기본 1e-9). meta_keys: JSON 비교에서 뺄 실행 메타 키.
- run_options: 실행 기록 config 가운데 결과에 영향이 없는 키(비교하지 않고 따로 보인다).
- commands: 재실행 명령(yejun 기준, --rerun과 README용).

동결: expected/ 아래에 결과·실행 기록 사본(그림 제외)과 expected/lock.json(사본의 SHA-256, 그림 목록)을 둔다.
lock.json과 사본이 다르면(동결값 변조) 실패한다. 무결성은 "이 결과가 기록된 실행에서 나왔는가", 동결 비교는 "그 실행이 동결
실행과 같은 결과인가"를 본다. 다른 기기에서는 결과와 실행 기록을 함께 다시 만들면 무결성이 통과하고, 동결 비교는 허용오차로 본다.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

ANALYSIS = Path(__file__).resolve().parent
YEJUN = ANALYSIS.parent
REPO = YEJUN.parent
IMAGES = (".png", ".jpg", ".jpeg", ".svg")
DATA_FILES = {"normal": "press_data_normal.csv", "abnormal": "outlier_data.csv"}
DATA_DIR = YEJUN / "press_submission" / "data" / "3_소성가공_예지보전"
DEFAULT_META = ("elapsed_s", "environment", "created", "run_id")
SCENARIOS = ("output_changed", "output_missing", "code_changed", "manifest_missing", "expected_changed")


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_contract(pkg: Path) -> dict:
    c = json.loads((pkg / "contract.json").read_text(encoding="utf-8"))
    c.setdefault("tolerance", 1e-9)
    c.setdefault("meta_keys", list(DEFAULT_META))
    c.setdefault("run_options", [])
    c.setdefault("commands", [])
    c.setdefault("local_outputs", [])
    return c


def _v1_code_hash():
    sys.path.insert(0, str(YEJUN / "press_submission"))
    from press.validation import code_sha256
    return code_sha256()


def resolve(key: str, rule: str, pkg: Path, out: Path) -> Path | None:
    if rule == "outputs":
        prefix = f"yejun/analysis/{pkg.name}/"
        return out / (key[len(prefix):] if key.startswith(prefix) else key)
    if rule == "data":
        return DATA_DIR / DATA_FILES[key] if key in DATA_FILES else None
    if rule == "guard":
        return YEJUN / "press_guard" / "artifacts" / key
    for base in (pkg, YEJUN, REPO, ANALYSIS):
        p = base / key
        if p.is_file():
            return p
    return None


def _get(d: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def integrity(pkg: Path, out: Path | None = None, contract: dict | None = None) -> list[str]:
    """실행 기록(manifest)에 적힌 입력·코드·모델·인용·결과 해시가 현재 파일과 같은가."""
    out = Path(out or pkg)
    c = contract or load_contract(pkg)
    bad, recorded_outputs = [], set()
    for name, spec in c["manifests"].items():
        path = out / name
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            bad.append(f"{name}: 실행 기록 없음·손상({exc})")
            continue
        for group, rule in spec.get("groups", {}).items():
            recorded = m.get(group)
            if not isinstance(recorded, dict) or not recorded:
                bad.append(f"{name}: 해시 묶음 '{group}' 없음")
                continue
            for key, digest in recorded.items():
                p = resolve(key, rule, pkg, out)
                if rule == "outputs" and key in c["local_outputs"] and (p is None or not p.is_file()):
                    continue                  # Git 제외 결과는 없을 수 있다(재실행으로 생성)
                if p is None or not p.is_file():
                    bad.append(f"{name}: {group} 파일 없음 — {key}")
                elif sha256(p) != digest:
                    bad.append(f"{name}: {group} 변경(실행 기록과 다름) — {key}")
                if rule == "outputs" and p is not None:
                    recorded_outputs.add(p.resolve())
        for key, target in spec.get("scalars", {}).items():
            digest = m.get(key)
            now = _v1_code_hash() if target == "@v1_code" else (sha256(YEJUN / target) if (YEJUN / target).is_file() else None)
            if digest is None or now is None or digest != now:
                bad.append(f"{name}: {key} 변경(실행 기록과 다름) — {target}")
        for key, field in spec.get("nested", {}).items():
            group = _get(m, key)
            if not isinstance(group, dict):
                bad.append(f"{name}: 해시 묶음 '{key}' 없음")
                continue
            for k, v in group.items():
                p = resolve(k, "data", pkg, out)
                if p is None or not p.is_file() or sha256(p) != (v or {}).get(field):
                    bad.append(f"{name}: {key}.{k} 변경 또는 없음")
    for rel in c["outputs"]:
        p = out / rel
        if not p.is_file():
            bad.append(f"결과 없음 — {rel}")
        elif p.resolve() not in recorded_outputs:
            bad.append(f"실행 기록에 없는 결과 — {rel}")
    return bad


def compare_csv(a: Path, b: Path, tol: float) -> str | None:
    x, y = pd.read_csv(a), pd.read_csv(b)
    if x.shape != y.shape or list(x.columns) != list(y.columns):
        return f"{a.name}: 모양·열 불일치 {x.shape} vs {y.shape}"
    for col in x.columns:
        if pd.api.types.is_numeric_dtype(x[col]) and pd.api.types.is_numeric_dtype(y[col]):
            xv, yv = x[col].to_numpy(float), y[col].to_numpy(float)
            if any(not np.array_equal(f(xv), f(yv)) for f in (np.isnan, np.isposinf, np.isneginf)):
                return f"{a.name}: {col} 결측·무한 위치 불일치"
            ok = np.isfinite(xv)
            d = np.abs(xv[ok] - yv[ok])
            if len(d) and d.max() > tol:
                return f"{a.name}: {col} 최대 차이 {d.max():.3g} > {tol:g}"
        elif not x[col].astype(str).equals(y[col].astype(str)):
            return f"{a.name}: 문자 열 {col} 불일치"
    return None


def _strip(obj, keys):
    if isinstance(obj, dict):
        return {k: _strip(v, keys) for k, v in obj.items() if k not in keys}
    if isinstance(obj, list):
        return [_strip(v, keys) for v in obj]
    return obj


def compare_expected(pkg: Path, out: Path | None = None, expected: Path | None = None, contract: dict | None = None) -> tuple[list[str], list[str]]:
    """동결 기대값과 비교한다. (실패 목록, 참고 목록)을 돌려준다."""
    out = Path(out or pkg)
    exp = Path(expected or pkg / "expected")
    c = contract or load_contract(pkg)
    bad, notes = [], []
    try:
        lock = json.loads((exp / "lock.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"동결 기대값 없음({exc}). 무결성 통과 실행에서 --freeze로 먼저 동결한다"], notes
    for name, digest in lock.get("files", {}).items():
        q = exp / name
        if not q.is_file() or sha256(q) != digest:
            bad.append(f"동결 기대값이 동결 당시와 다름 — {name}")
    for rel, meta in lock.get("local", {}).items():
        p = out / rel
        if not p.is_file():
            notes.append(f"Git 제외 결과 없음 — {rel}(재실행으로 생긴다)")
            continue
        x = pd.read_csv(p)
        if len(x) != meta["rows"] or list(x.columns) != meta["columns"]:
            bad.append(f"{rel}: 행 수·열이 동결 실행과 다름 ({len(x)}행)")
    for rel in c["outputs"]:
        p, q = out / rel, exp / rel
        if rel.lower().endswith(IMAGES):
            if not p.is_file() or p.stat().st_size == 0:
                bad.append(f"그림 없음 — {rel}")
            continue
        if rel not in lock.get("files", {}):
            bad.append(f"동결 목록에 없는 결과 — {rel}")
            continue
        if not p.is_file():
            bad.append(f"결과 없음 — {rel}")
            continue
        if rel.endswith(".csv"):
            reason = compare_csv(p, q, float(c["tolerance"]))
        elif rel.endswith(".json"):
            same = _strip(json.loads(p.read_text(encoding="utf-8")), set(c["meta_keys"])) == _strip(json.loads(q.read_text(encoding="utf-8")), set(c["meta_keys"]))
            reason = None if same else f"{rel}: 내용 불일치"
        else:
            reason = None if p.read_bytes().replace(b"\r\n", b"\n") == q.read_bytes().replace(b"\r\n", b"\n") else f"{rel}: 내용 불일치"
        if reason:
            bad.append(reason)
    options = set(c["run_options"])
    for name in c["manifests"]:
        try:
            now = json.loads((out / name).read_text(encoding="utf-8"))
            then = json.loads((exp / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad.append(f"{name}: 실행 기록 또는 동결 사본 없음")
            continue
        for key in ("input_hashes", "protocol"):
            if key in then and now.get(key) != then.get(key):
                bad.append(f"{name}: {key}가 동결 실행과 다름")
        if isinstance(then.get("config"), dict) or isinstance(now.get("config"), dict):
            a, b = dict(now.get("config") or {}), dict(then.get("config") or {})
            for k in options:
                if a.get(k) != b.get(k):
                    notes.append(f"{name}: 실행 옵션 {k} = {a.get(k)} (동결 {b.get(k)}) — 결과에 영향 없는 옵션이라 비교하지 않음")
                a.pop(k, None); b.pop(k, None)
            if a != b:
                bad.append(f"{name}: 실행 설정(config)이 동결 실행과 다름")
    return bad, notes


def verify(pkg: Path, out: Path | None = None, expected: Path | None = None) -> list[str]:
    c = load_contract(pkg)
    return integrity(pkg, out, c) + compare_expected(pkg, out, expected, c)[0]


def freeze(pkg: Path, out: Path | None = None) -> list[str]:
    """무결성이 통과한 실행만 expected/로 동결한다. 실패 사유 목록을 돌려준다(비어 있으면 동결함)."""
    out = Path(out or pkg)
    c = load_contract(pkg)
    bad = integrity(pkg, out, c)
    if bad:
        return bad
    staged = Path(tempfile.mkdtemp(prefix=".freeze-", dir=pkg)) / "expected"
    staged.mkdir()
    files, images, local = {}, [], {}
    for rel in c["local_outputs"]:
        x = pd.read_csv(out / rel)
        local[rel] = dict(sha256=sha256(out / rel), rows=int(len(x)), columns=list(x.columns))
    for rel in list(c["outputs"]) + list(c["manifests"]):
        if rel.lower().endswith(IMAGES):
            images.append(rel)
            continue
        target = staged / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out / rel, target)
        files[rel] = sha256(target)
    (staged / "lock.json").write_text(json.dumps(dict(package=pkg.name, files=files, images=images, local=local,
                                                      note="동결 사본의 SHA-256. 그림은 존재·크기만, Git 제외 결과(local)는 행 수·열만 비교한다"),
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    final = pkg / "expected"
    if final.exists():
        shutil.rmtree(final)
    staged.rename(final)
    shutil.rmtree(staged.parent)
    return []


def rerun(pkg: Path) -> list[str]:
    """contract.json의 명령을 yejun/에서 차례로 실행한다(제자리 재실행, 결정적 코드라 결과 값이 같아야 한다)."""
    c = load_contract(pkg)
    env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")   # 자식 출력은 UTF-8로 받는다(CP949 콘솔)
    bad = []
    for cmd in c["commands"]:
        args = [sys.executable if a == "python" else a for a in cmd.split()]
        print(f"-- {cmd}", flush=True)
        done = subprocess.run(args, cwd=YEJUN, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if done.returncode:
            bad.append(f"재실행 실패(종료 코드 {done.returncode}): {cmd} {done.stderr[-400:]}")
            break
    return bad


def mutate_and_verify(pkg: Path, scenario: str, tmp: Path) -> list[str]:
    """변조 검출 시험: 결과·실행 기록·동결값의 임시 사본을 바꾼 뒤 verify 결과(실패 목록)를 돌려준다."""
    c = load_contract(pkg)
    out, exp = tmp / "out", tmp / "expected"
    for rel in list(c["outputs"]) + list(c["manifests"]):
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pkg / rel, out / rel)
    shutil.copytree(pkg / "expected", exp)
    csvs = [r for r in c["outputs"] if r.endswith(".csv")]
    first_manifest = next(iter(c["manifests"]))
    if scenario == "output_changed":
        f = out / csvs[0]
        x = pd.read_csv(f)
        col = next((k for k in x.columns if pd.api.types.is_numeric_dtype(x[k]) and np.isfinite(x[k].to_numpy(float)).any()), None)
        if col is None:
            x.iloc[0, 0] = f"{x.iloc[0, 0]}_변조"
        else:
            i = int(np.flatnonzero(np.isfinite(x[col].to_numpy(float)))[0])
            x.loc[i, col] = float(x.loc[i, col]) + 1.0
        x.to_csv(f, index=False)
    elif scenario == "output_missing":
        (out / csvs[-1]).unlink()
    elif scenario == "code_changed":
        spec = c["manifests"][first_manifest]
        m = json.loads((out / first_manifest).read_text(encoding="utf-8"))
        group = next((g for g, rule in spec.get("groups", {}).items() if rule != "outputs"), None)
        if group is not None:
            key = next(iter(m[group]))
            m[group][key] = "0" * 64                     # 실행 뒤 코드·입력이 바뀐 것과 같다
        else:
            key = next(iter(spec.get("scalars", {})))
            m[key] = "0" * 64
        (out / first_manifest).write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    elif scenario == "manifest_missing":
        (out / first_manifest).unlink()
    elif scenario == "expected_changed":
        q = exp / csvs[0]
        q.write_text(q.read_text(encoding="utf-8").replace(",", ";", 1), encoding="utf-8")
    else:
        raise ValueError(scenario)
    return verify(pkg, out, exp)


PREREQUISITES = [DATA_DIR / name for name in DATA_FILES.values()] + [YEJUN / "press_guard" / "artifacts" / f"guard_{s}.json" for s in "AB"]
FIRST_RUN_HINT = "먼저 python yejun/press_guard/reproduce.py 로 원본 배치(--data 주최 측 ZIP)와 학습을 한다"


def missing_prerequisites():
    """Git에서 뺀 선행 파일(대회 원본 CSV, 저장 모델)이 없으면 그 목록. 갓 받은 사본은 한 명령 재현을 먼저 돌려야 한다."""
    return [str(p.relative_to(YEJUN)) for p in PREREQUISITES if not p.is_file()]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):     # 한국어 Windows(CP949) 콘솔에서 못 쓰는 기호는 바꿔 쓴다
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--out", type=Path, help="비교할 결과 폴더(기본: 패키지 폴더)")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--rerun", action="store_true", help="contract.json의 명령으로 제자리 재실행한 뒤 비교")
    args = ap.parse_args(argv)
    pkg = args.package if args.package.is_absolute() else (Path.cwd() / args.package)
    pkg = pkg.resolve()
    if not (pkg / "contract.json").is_file():
        print(f"계약 파일 없음: {pkg / 'contract.json'}", file=sys.stderr)
        return 2
    lacking = missing_prerequisites()
    if lacking:
        print(f"선행 파일 없음({', '.join(lacking)}). {FIRST_RUN_HINT}", file=sys.stderr)
        return 2
    if args.freeze:
        bad = freeze(pkg, args.out)
        if bad:
            print("동결 거부:\n  " + "\n  ".join(bad), file=sys.stderr)
            return 2
        print(f"동결: {pkg.name} → {pkg / 'expected'}")
        return 0
    bad = rerun(pkg) if args.rerun else []
    c = load_contract(pkg)
    bad += integrity(pkg, args.out, c)
    cmp_bad, notes = compare_expected(pkg, args.out, None, c)
    bad += cmp_bad
    for msg in notes:
        print("참고", msg)
    for msg in bad:
        print("FAIL", msg)
    print(f"{'통과' if not bad else '실패'}: {pkg.name} 실행 기록 무결성·동결 기대값 비교(결과 {len(c['outputs'])}개)" + (" · 제자리 재실행" if args.rerun else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
