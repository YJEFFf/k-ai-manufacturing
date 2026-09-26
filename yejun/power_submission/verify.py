"""동결 기대값(expected/)과 현재 outputs/를 비교한다. 수치 파일(CSV/JSON)은 허용오차 안에서 같아야 한다.

사용:
    python verify.py                  # 비교(+ 산출물이 마지막 전체 실행에서 만들어졌는지 알림)
    python verify.py --require-fresh  # 비교 + 모든 비교 파일이 마지막 전체 실행 중에 쓰였어야 통과
    python verify.py --freeze         # 현재 outputs/를 expected/로 동결(의도한 변경 후에만)

추가로 시험 예측 파일(Git 제외)의 SHA-256과 그림 목록을 확인한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
EXP = ROOT / "expected"
# 실행 환경·시간, 입력 경로 표기(원본 동일성은 SHA-256으로 확인)는 비교하지 않는다
SKIP_JSON_KEYS = {"timings_s", "total_s", "versions", "platform", "source"}
RTOL = 1e-6
ATOL = 1e-6


def files(base: Path) -> list[Path]:
    return sorted(p.relative_to(base) for p in base.rglob("*")
                  if p.is_file() and p.suffix in (".csv", ".json") and "predictions" not in p.name
                  and p.name != "run_manifest.json")


def cmp_json(a, b, path="") -> list[str]:
    errs = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k in SKIP_JSON_KEYS:
                continue
            if k not in a or k not in b:
                errs.append(f"{path}/{k}: 키 불일치")
            else:
                errs += cmp_json(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            errs.append(f"{path}: 길이 {len(a)} != {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                errs += cmp_json(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        if not math.isclose(a, b, rel_tol=RTOL, abs_tol=ATOL):
            errs.append(f"{path}: {a} != {b}")
    elif a != b:
        errs.append(f"{path}: {a!r} != {b!r}")
    return errs


def cmp_csv(pa: Path, pb: Path) -> list[str]:
    a, b = pd.read_csv(pa), pd.read_csv(pb)
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return [f"{pa.name}: 형태 {a.shape}/{list(a.columns)[:5]} != {b.shape}/{list(b.columns)[:5]}"]
    errs = []
    for c in a.columns:
        x, y = a[c], b[c]
        if pd.api.types.is_bool_dtype(x) or pd.api.types.is_bool_dtype(y):
            bad = ~((x == y) | (x.isna() & y.isna()))
        elif pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            xf, yf = x.astype(float), y.astype(float)
            bad = ~(((xf - yf).abs() <= ATOL + RTOL * yf.abs()) | (xf.isna() & yf.isna()))
        else:
            bad = x.astype(object).where(x.notna(), "<NA>").astype(str) != y.astype(object).where(y.notna(), "<NA>").astype(str)
        if bad.any():
            i = bad.idxmax()
            errs.append(f"{pa.name}:{c} {int(bad.sum())}행 차이(예: {x[i]!r} != {y[i]!r})")
    return errs


def external_missing() -> bool:
    """외부 KAMP ZIP이 없어 external 단계가 항목을 건너뛴 실행인가(그 경우 external/*는 비교하지 않는다)."""
    p = OUT / "external" / "external_summary.json"
    if not p.exists():
        return True
    j = json.loads(p.read_text(encoding="utf-8"))
    return any(isinstance(v, dict) and "skipped" in v for v in j.values())


PRED = Path("test") / "predictions_test.csv"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def freshness(rels: list[Path]) -> tuple[bool, str]:
    """비교 대상이 마지막 전체 실행(run_manifest.json의 last_full_run) 시작~끝 사이에 쓰였는가.

    깨끗한 클론처럼 실행하지 않은 산출물은 파일 시각이 실행 기록보다 늦어 '신선하지 않음'이 된다."""
    mp = OUT / "run_manifest.json"
    if not mp.exists():
        return False, "run_manifest.json 없음 — run_all.py를 먼저 실행한다"
    m = json.loads(mp.read_text(encoding="utf-8"))
    full = m.get("last_full_run")
    if not full:
        return False, "전체 실행 기록 없음 — run_all.py(모든 단계)를 실행한다(일부 단계만 실행하면 신선도 확인은 실패한다)"
    pk = m.get("packaged_epoch")
    if pk is not None and (full.get("started_epoch") or 0) <= pk:
        return False, "제출 묶음을 만든 뒤의 전체 실행 기록이 없다 — 받은 사본에서 run_all.py를 실행한다"
    cs = full.get("code_sha256")
    if cs is not None:
        import run_all
        if run_all.code_sha256() != cs:
            return False, "마지막 전체 실행 뒤 코드가 바뀌었다 — run_all.py를 다시 실행한다"
    a = full.get("started_epoch")
    b = full.get("finished_epoch")
    if a is None or b is None:  # 이전 형식: 사람이 읽는 시각과 총 시간으로 계산
        b = time.mktime(time.strptime(full["finished_at"], "%Y-%m-%dT%H:%M:%S")) + 1
        a = b - float(full.get("total_s", 0)) - 2
    stale = [str(r) for r in rels if not (a - 1 <= (OUT / r).stat().st_mtime <= b + 1)]
    if stale:
        return False, f"마지막 전체 실행({full.get('finished_at')}) 밖에서 쓰인 파일 {len(stale)}개(예: {stale[:3]})"
    return True, f"모든 비교 파일이 마지막 전체 실행({full.get('started_at', '')}~{full.get('finished_at')}) 중에 쓰였다"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--require-fresh", action="store_true", help="비교 파일이 마지막 전체 실행에서 만들어지지 않았으면 실패")
    ap.add_argument("--skip-external", action="store_true", help="외부 KAMP 자료 산출물(external/*)을 비교하지 않는다")
    args = ap.parse_args(argv)
    if args.freeze:
        if EXP.exists():
            shutil.rmtree(EXP)
        for rel in files(OUT):
            (EXP / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT / rel, EXP / rel)
        if (OUT / PRED).exists():
            (EXP / "predictions_test.sha256").write_text(sha256(OUT / PRED) + "\n", encoding="utf-8")
        figs = sorted(p.name for p in (OUT / "figures").glob("*.png"))
        (EXP / "figures.txt").write_text("\n".join(figs) + "\n", encoding="utf-8")
        print(f"동결: {len(files(EXP))}개 파일 + 시험 예측 SHA-256 + 그림 {len(figs)}개 목록")
        return 0
    exp, cur = set(files(EXP)), set(files(OUT))
    skip_ext = args.skip_external or external_missing()
    if skip_ext:
        exp = {p for p in exp if p.parts[0] != "external"}
        cur = {p for p in cur if p.parts[0] != "external"}
        SKIP_JSON_KEYS.add("external")
        print("외부 KAMP 자료 산출물(external/*, key_numbers.external)은 비교하지 않는다(입력 ZIP 없음 또는 --skip-external)")
    errs = [f"누락: {p}" for p in sorted(exp - cur)] + [f"추가(기대값 없음): {p}" for p in sorted(cur - exp)]
    ok = 0
    for rel in sorted(exp & cur):
        e = (cmp_json(json.loads((OUT / rel).read_text(encoding="utf-8")), json.loads((EXP / rel).read_text(encoding="utf-8")), str(rel))
             if rel.suffix == ".json" else cmp_csv(OUT / rel, EXP / rel))
        if e:
            errs += e
        else:
            ok += 1
    print(f"일치 {ok}/{len(exp)}")
    # 시험 예측 파일(Git 제외, run_all로 생성)과 그림 목록
    shp = EXP / "predictions_test.sha256"
    if shp.exists():
        if (OUT / PRED).exists():
            same = sha256(OUT / PRED) == shp.read_text(encoding="utf-8").strip()
            print(f"시험 예측 파일 SHA-256 {'일치' if same else '불일치'}")
            if not same:
                errs.append("predictions_test.csv SHA-256 불일치")
        else:
            print("시험 예측 파일 없음(Git 제외) — run_all.py(peak 단계)로 만든 뒤 다시 확인한다")
    fl = EXP / "figures.txt"
    if fl.exists():
        miss = [n for n in fl.read_text(encoding="utf-8").split() if not (OUT / "figures" / n).exists()]
        print(f"그림 {'모두 있음' if not miss else f'{len(miss)}개 없음: {miss[:3]}'}")
        if miss:
            errs.append(f"그림 누락 {len(miss)}개")
    fresh, msg = freshness(sorted(exp & cur))
    print(("신선도 확인: " if fresh else "신선도 경고: ") + msg)
    if args.require_fresh and not fresh:
        errs.append("산출물이 마지막 전체 실행에서 만들어지지 않았다")
    for e in errs[:50]:
        print(" -", e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
