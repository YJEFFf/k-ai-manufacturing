"""재현용 제출 ZIP 구성: 코드·테스트·기대값·산출물(시험 예측 파일 포함)·원본 CSV와 파일별 SHA-256 목록.

사용:
    python make_submission.py                         # ../power_submission_package.zip
    python make_submission.py --out 경로.zip --with-external "/경로/데이터셋"   # 외부 KAMP ZIP 3개도 data/external/에

ZIP을 풀고 `python run_all.py`(원본은 data/에, 외부 ZIP을 넣었다면 data/external/에서 자동으로 찾음)
→ `python -m pytest -q tests` → `python verify.py --require-fresh`(풀기만 하고 실행하지 않은 사본은 실패).
내부 검수 기록(reviews/)은 기본으로 빼며 `--include-reviews`로 넣는다.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INCLUDE = ["run_all.py", "verify.py", "make_submission.py", "requirements.txt", "environment.yml", "README.md", "PLAN.md",
           "powerguard", "tests", "expected", "outputs", "data/okm_augumented_2021.csv"]
EXTERNAL = ["Dataset_표면처리 자원최적화 AI 데이터셋.zip", "Dataset_소성가공 자원최적화 AI 데이터셋.zip",
            "Dataset_생산계획 최적화 AI 데이터셋.zip"]
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "artifacts"}


def iter_files():
    for item in INCLUDE:
        p = ROOT / item
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not (set(f.relative_to(ROOT).parts) & SKIP_PARTS) and f.suffix != ".pyc":
                    yield f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "power_submission_package.zip"))
    ap.add_argument("--with-external", default=None, help="외부 KAMP ZIP이 있는 폴더(#41·#46·#30을 data/external/에 넣는다)")
    ap.add_argument("--include-reviews", action="store_true", help="내부 검수 기록(reviews/)도 넣는다(기본: 뺀다)")
    args = ap.parse_args(argv)
    if args.include_reviews:
        INCLUDE.append("reviews")
    missing = [m for m in ("data/okm_augumented_2021.csv", "outputs/test/predictions_test.csv") if not (ROOT / m).exists()]
    if missing:
        print(f"필수 파일 없음: {missing} — run_all.py를 먼저 실행한다(원본은 --data로 한 번 주면 data/에 저장된다)")
        return 1
    lines = []
    out = Path(args.out)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        import json
        import time
        for f in iter_files():
            arc = Path("power_submission") / f.relative_to(ROOT)
            if f.name == "run_manifest.json":
                # 받은 사본이 실행 없이 신선도 확인을 통과하지 않도록: 전체 실행 기록을 빼고 묶은 시각을 남긴다
                m = json.loads(f.read_text(encoding="utf-8"))
                m["packaged_from_full_run"] = m.pop("last_full_run", None)
                m["packaged_epoch"] = time.time()
                data = (json.dumps(m, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
                z.writestr(arc.as_posix(), data)
                lines.append(f"{hashlib.sha256(data).hexdigest()}  {arc.as_posix()}")
                continue
            z.write(f, arc.as_posix())
            lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {arc.as_posix()}")
        if args.with_external:
            for name in EXTERNAL:
                f = Path(args.with_external) / name
                if f.exists():
                    arc = Path("power_submission") / "data" / "external" / name
                    z.write(f, arc.as_posix())
                    lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {arc.as_posix()}")
                else:
                    print(f"외부 ZIP 없음(건너뜀): {f}")
        z.writestr("power_submission/SHA256SUMS.txt", "\n".join(lines) + "\n")
    print(f"만듦: {out} ({len(lines)}개 파일)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
