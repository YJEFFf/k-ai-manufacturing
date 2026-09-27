"""최종 패키지(프레스 ③) 파일 목록 계산 — 목록·SHA-256·블라인드 검사만 한다. ZIP은 만들지 않는다.

    python yejun/press_guard/tools/package_manifest.py [--out 목록.csv]

- 넣는 것: 최종 모델 코드(press_guard), 선행 v1 코드(press_submission), 후보 비교(press_advance, train.py가 대조), 의존성 파일,
  학습용 원본 CSV 2개, 저장 모델·확률 보정기, 테스트 예측 파일(분할별 1개), 동결 기대값, README·운영 절차서.
  보조 분석 패키지(진단·보완 실험·지도학습 비교·선정 근거)는 group=supporting으로 따로 표시한다.
- 빼는 것: 검수·작업 기록(analysis/press_rubric_review 등), 캐시, 행 단위 중간 예측(predictions_*), 로그.
- 블라인드 검사: 넣을 문서·코드에 절대 경로(/Users/, /opt/anaconda3, C:\\)가 없는지, 필요한 파일이 모두 있는지 본다.
- 대회 제출 ZIP 조립은 예준의 지시 전까지 보류한다(yejun/AGENTS.md). 이 도구는 목록만 계산한다.
"""
from pathlib import Path
import argparse
import hashlib
import re
import sys

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
YEJUN = HERE.parent
GROUPS = [
    ("final_model", "press_guard", ["*.py", "web/*", "tools/*.py", "tools/*.sh", "requirements*.txt", "environment.yml", "README.md", "OPERATIONS.md", ".gitignore"]),
    ("final_model", "press_guard/artifacts", ["guard_*.json", "probability_*.json"]),
    ("test_predictions", "press_guard/outputs", ["test_predictions_*.csv"]),
    ("final_outputs", "press_guard/outputs", ["*.csv", "*.json", "*.md", "*.png", "expected/*"]),
    ("baseline_v1", "press_submission", ["*.py", "press/*.py", "vendor/*.py", "requirements.txt", "README.md", "PROVENANCE.md", "tests/*.py", "tools/*"]),
    ("baseline_v1", "press_submission/outputs", ["expected/*"]),
    ("training_data", "press_submission/data/3_소성가공_예지보전", ["*.csv"]),
    ("candidates", "analysis/press_advance", ["*", "expected/*"]),
    ("supporting", "analysis/press_evidence", ["*.py", "*.csv", "*.json", "README.md", "figures/*", "expected/*"]),
    ("supporting", "analysis/press_supplement", ["*.py", "*.csv", "*.json", "*.png", "README.md", "expected/*"]),
    ("supporting", "analysis/press_supervised", ["*.py", "*.csv", "*.json", "README.md", "expected/*"]),
    ("supporting", "analysis/press_selection", ["*.py", "*.csv", "*.json", "*.md", "expected/*"]),
    ("supporting", "analysis", ["package_contract.py"]),
]
EXCLUDE = re.compile(r"(__pycache__|\.pytest_cache|reproduce_logs|reproduce_summary\.json|/predictions_|\.DS_Store|lstm_cache|demo)")
REQUIRED = ["press_guard/reproduce.py", "press_guard/requirements.txt", "press_guard/environment.yml", "press_guard/README.md",
            "press_guard/artifacts/guard_A.json", "press_guard/artifacts/guard_B.json", "press_guard/outputs/test_predictions_A.csv",
            "press_guard/outputs/test_predictions_B.csv", "press_submission/run_all.py", "press_submission/data/3_소성가공_예지보전/press_data_normal.csv",
            "press_submission/data/3_소성가공_예지보전/outlier_data.csv"]
ABSOLUTE = re.compile(r"(/Users/|/opt/anaconda3|/Volumes/|[A-Z]:\\\\)")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    rows, seen = [], set()
    for group, folder, patterns in GROUPS:
        base = YEJUN / folder
        for pat in patterns:
            for p in sorted(base.glob(pat)):
                rel = p.relative_to(YEJUN).as_posix()
                if not p.is_file() or rel in seen or EXCLUDE.search(rel):
                    continue
                seen.add(rel)
                rows.append(dict(group=group, path=rel, bytes=p.stat().st_size, sha256=sha(p)))
    return pd.DataFrame(rows)


def blind_checks(table):
    problems = [f"필수 파일 없음: {r}" for r in REQUIRED if r not in set(table.path)]
    for rel in table.path:
        if rel.endswith((".py", ".md", ".sh", ".txt", ".yml", ".html", ".js")) and rel != "press_guard/tools/package_manifest.py":
            text = (YEJUN / rel).read_text(encoding="utf-8", errors="replace")
            hits = sorted(set(ABSOLUTE.findall(text)))
            if hits:
                problems.append(f"절대 경로 {hits}: {rel}")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, help="목록 CSV")
    ap.add_argument("--zip", action="store_true", help="보류: ZIP 생성은 예준의 지시 전까지 하지 않는다")
    args = ap.parse_args()
    if args.zip:
        print("ZIP 조립은 보류 중이다(yejun/AGENTS.md: 최종 제출물 조립은 예준의 명시적 지시 뒤에). 목록만 계산한다.", file=sys.stderr)
        return 2
    table = collect()
    if args.out:
        table.to_csv(args.out, index=False)
    by_group = table.groupby("group").agg(files=("path", "size"), megabytes=("bytes", lambda b: round(b.sum() / 2 ** 20, 2)))
    print(by_group.to_string())
    print(f"합계 {len(table)}개 · {table.bytes.sum() / 2 ** 20:.1f} MB")
    problems = blind_checks(table)
    for p in problems:
        print("검사 실패:", p)
    print("블라인드 검사 통과" if not problems else f"블라인드 검사 {len(problems)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
