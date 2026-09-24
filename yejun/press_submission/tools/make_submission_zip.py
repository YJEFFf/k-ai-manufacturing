"""제출용 코드 ZIP 조립 — PLAN.md §7. 저장소 정책과 달리 ZIP에는 학습용 데이터·artifacts(LSTM 캐시)·행별 예측 파일을 포함한다.

    python tools/make_submission_zip.py --out ../submission_press.zip [--exclude-lstm-cache]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = ["press", "vendor", "tests", "tools", "outputs", "evidence", "artifacts", "data"]
EXCLUDE_FILES = {"evidence/요청사항_준용.md"}   # 팀 내부 요청 노트는 제출물이 아니다
INCLUDE_FILES = ["README.md", "PLAN.md", "PROVENANCE.md", "requirements.txt", "run_all.py", "predict.py", "verify.py"]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store"}
BLIND_PATTERNS = tuple(p for p in ("@gm" "ail", "@na" "ver", "/Us" "ers/", "heoy" "ejun", "YJE" "FFf"))   # 자기 파일 검출을 피하려고 분리해 적음


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=PKG.parent / "submission_press.zip")
    ap.add_argument("--exclude-lstm-cache", action="store_true")
    args = ap.parse_args(argv)
    files = []
    for d in INCLUDE_DIRS:
        p = PKG / d
        if not p.exists():
            continue
        for f in sorted(p.rglob("*")):
            if f.is_file() and not (EXCLUDE_PARTS & set(f.parts)) and str(f.relative_to(PKG)) not in EXCLUDE_FILES:
                if args.exclude_lstm_cache and "lstm_cache" in f.parts:
                    continue
                files.append(f)
    files += [PKG / f for f in INCLUDE_FILES if (PKG / f).exists()]
    blind_hits = []
    for f in files:
        if f.suffix in (".py", ".md", ".txt", ".json", ".csv") and f.stat().st_size < 5_000_000:
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for pat in BLIND_PATTERNS:
                if pat in txt:
                    blind_hits.append((str(f.relative_to(PKG)), pat))
    manifest = {"files": {}, "blind_check_hits": blind_hits}
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            rel = f.relative_to(PKG)
            z.write(f, f"press_submission/{rel}")
            manifest["files"][str(rel)] = hashlib.sha256(f.read_bytes()).hexdigest()
        z.writestr("press_submission/ZIP_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"{len(files)}개 파일 → {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")
    if blind_hits:
        print("블라인드 검사에 걸린 문자열(제출 전 제거):")
        for rel, pat in sorted(set(blind_hits)):
            print(f"  {rel}: {pat}")
    return 1 if blind_hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
