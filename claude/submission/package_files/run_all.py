"""명령 하나로 전처리 → 학습 → 추론 → 결과 생성 → 보고서 수치 대조까지 실행한다.

    python run_all.py           # 전체: 데이터 진단, 모델(train/valid/test), test 예측 파일, 검증 실험, 사후 분석, 결과 대조
    python run_all.py --quick   # 핵심만: 데이터 진단, 모델, test 예측 파일, 2.4·2.7·4.3절 사후 계산, 결과 대조

- 모든 단계는 이 폴더(압축을 푼 위치)를 기준으로 상대 경로만 쓴다. 인터넷 연결이 필요 없다
- 단계마다 로그를 logs/<단계>.log 에 남기고, 끝나면 logs/run_summary.json 에 단계별 시간과 대조 결과를 쓴다
- 마지막에 expected_results.json(보고서 작성 때의 결과)과 비교해 일치 여부를 표로 보여 준다
- test 예측 파일(제출물): predictions/test_predictions_A.csv, predictions/test_predictions_B.csv
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from functools import reduce
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "3_소성가공_예지보전"
# v2 모듈(press_submission)은 자기 폴더 아래 이 위치에서 원본을 읽는다
TEAM_DATA = ROOT / "yejun" / "press_submission" / "data" / "3_소성가공_예지보전"
LOGS = ROOT / "logs"
PRED = ROOT / "predictions"
CSV_SHA256 = {   # 주최 측 원본(KAMP 소성가공 예지보전 AI 데이터셋)
    "press_data_normal.csv": "f2d61cb3b3108f49a3305d2966b3a31f26942ac8af8ffc9eb531b432b945b0a7",
    "outlier_data.csv": "9fad8c238e63dba3257d8be32a32362548955c772171a95c0d2af61b0435ed2e",
}

# (단계 이름, 실행 파일, 인자, --quick에도 포함, 설명). "--repo ."는 이 폴더를 팀 레포 루트로 쓰라는 뜻이다
STEPS = [
    ("1_진단_기록특징", "code/press/cases/01_case_features.py", [], True, "기록 단위 특징, 형식 누수 확인"),
    ("1_진단_보조수치", "code/press/cases/03_facts_extra.py", [], True, "측정 비율·기록 구조·형식 누수 보조 수치"),
    ("1_진단_겉보기주파수", "code/press/06_alias_frequency_audit.py", [], True, "전류 사인 적합 겉보기 주파수"),
    ("2_모델_학습과점수", "code/press/tvt/01_scores.py", ["--repo", "."], True, "정상 학습 자료로 모든 후보 학습, valid 보정"),
    ("2_모델_valid선택", "code/press/tvt/02_select_on_valid.py", [], True, "valid 채점, 모델 선택, 선택 결과 해시 잠금"),
    ("2_모델_test채점", "code/press/tvt/03_score_test.py", ["--repo", "."], True, "잠금 확인 후 test 채점"),
    ("2_모델_test예측파일", "code/press/tvt/05_test_predictions.py", [], True, "test 행 단위 예측 파일, 첫 경보 지연"),
    ("2_모델_이상확률", "code/press/tvt/08_probability.py", ["--repo", "."], True, "v2 점수를 이상 확률로(valid로만 보정, 경보·선택과 무관), 예측 파일에 열 추가"),
    ("3_검증_실험", "code/press/tvt/04_validation.py", ["--repo", "."], False, "인공 고장 주입·분할 변경·수집 조건 흔들림 검증(보고서 2.6절)"),
    ("4_사후_신호물리", "code/press/domain/01_signal_physics.py", [], False, "표본 간격·진동 스펙트럼·부하 관계(사후)"),
    ("4_사후_사건추세", "code/press/domain/02_event_trend.py", [], False, "이상 사건 안 추세(사후)"),
    ("4_사후_PCA관리도", "code/press/domain/03_mspc.py", [], False, "PCA 관리도 비교(사후)"),
    ("4_사후_순차검출", "code/press/domain/04_sequential_uncertainty.py", [], False, "CUSUM·EWMA·불확실성·경보 지표(사후)"),
    ("4_사후_지도학습대조", "code/press/domain/05_supervised_confound.py", [], False, "지도학습 대조와 세션 교락 시험(사후)"),
    ("4_사후_운전상태", "code/press/domain/06_operating_regime.py", [], False, "운전 상태별 오경보(사후)"),
    ("4_사후_이상양상", "code/press/domain/07_anomaly_patterns.py", [], False, "이상 기록 양상별 먼저 볼 곳(사후)"),
    ("4_사후_기록수F1", "code/press/tvt/06_record_count.py", [], True, "기록 하나를 1개로 센 F1(사후, 선택에 쓰지 않음)"),
    ("4_사후_R1기준선", "code/press/tvt/07_r1_on_baselines.py", [], True, "R1을 기준선에도 붙인 비교, 창 때문에 점수 없는 행(사후, 선택에 쓰지 않음)"),
    ("4_사후_성분절제", "code/press/tvt/09_component_ablation.py", ["--repo", "."], False, "v2 성분 조합별 인공 주입 탐지율(사후, 선택에 쓰지 않음)"),
    ("4_사후_문턱무관비교", "code/press/tvt/10_threshold_free.py", [], True, "R1 없는 행 AUROC·PR-AUC와 기록 단위 부트스트랩 구간(사후, 선택에 쓰지 않음)"),
    ("4_사후_보조수치", "code/press/tvt/11_posthoc_numbers.py", ["--repo", "."], True, "max|z|+R1+R2, 이상 확률 AUROC·ECE, 수집 공백(사후, 선택에 쓰지 않음)"),
    ("4_사후_합성열화", "code/press/tvt/12_ramp_warning.py", ["--repo", "."], True, "합성 열화(2·5·10분)에서 첫 경보 선행 시간(사후, 선택에 쓰지 않음)"),
    ("4_사후_R2표본밖", "code/press/tvt/13_r2_oos_alpha.py", ["--repo", "."], False, "R2 준-표본 밖 확인, α 명목 대 실측, 블록 부트스트랩(사후, 선택에 쓰지 않음)"),
    ("4_사후_베이스라인주입", "code/press/tvt/14_baseline_injection_ridge.py", ["--repo", "."], False, "베이스라인 인공 주입 탐지율, Ridge 예측 오차 베이스라인(사후, 선택에 쓰지 않음)"),
    ("4_사후_특징맞춤", "code/press/tvt/15_record_auroc_featbase.py", ["--repo", "."], False, "기록 단위 AUROC, v2 특징을 넣은 5NN·IsolationForest(사후, 선택에 쓰지 않음)"),
    ("4_사후_흔들림병행", "code/press/tvt/16_jitter_ridge_combo.py", ["--repo", "."], False, "표본 시각 흔들림 반증, v2+R1과 Ridge 병행(사후, 선택에 쓰지 않음)"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_lf(path: Path) -> str:
    """줄바꿈을 LF로 맞춘 뒤의 해시. 예측 CSV는 OS마다 줄바꿈(Windows CRLF, macOS·Linux LF)이 달라 내용이 같아도 바이트가 다르다."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def check_environment():
    """파이썬 판과 패키지 판을 requirements.txt와 비교한다. 없는 패키지만 멈추고 판 차이는 알리기만 한다."""
    print(f"파이썬 {platform.python_version()} ({sys.executable})")
    if sys.version_info[:2] != (3, 13):
        print("  주의: 결과는 파이썬 3.13에서 만들었다. 다른 판에서는 일부 값이 조금 다를 수 있다")
    want = {}
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name, sep, ver = line.split("#")[0].partition("==")
        if sep:
            want[name.strip()] = ver.strip()
    missing, differ = [], []
    for name, ver in want.items():
        try:
            have = version(name)
        except PackageNotFoundError:
            missing.append(name)
            continue
        if have.split("+")[0] != ver:      # torch의 "+cpu" 같은 빌드 꼬리표는 무시
            differ.append(f"{name} {have}(권장 {ver})")
    if missing:
        raise SystemExit("설치되지 않은 패키지: " + ", ".join(missing) + "\n먼저 실행: pip install -r requirements.txt")
    print("  주의: 권장 판과 다른 패키지 → " + "; ".join(differ) if differ else "  패키지 판: requirements.txt와 같음")


def place_data():
    """원본 CSV 해시를 확인하고 v2 모듈이 읽는 위치에 복사한다."""
    TEAM_DATA.mkdir(parents=True, exist_ok=True)
    for name, digest in CSV_SHA256.items():
        src = DATA / name
        if not src.exists():
            raise SystemExit(f"원본 데이터가 없다: {src}")
        if sha256(src) != digest:
            raise SystemExit(f"원본 데이터 해시가 다르다(파일이 바뀌었음): {src}")
        dst = TEAM_DATA / name
        if not dst.exists() or sha256(dst) != digest:
            shutil.copy2(src, dst)
    print("원본 데이터 2개 해시 확인, 배치 완료")


def run_step(name, script, args):
    """단계 하나를 별도 프로세스로 돌리고 (종료 코드, 걸린 초)를 돌려준다. 출력은 logs/<단계>.log 로."""
    LOGS.mkdir(exist_ok=True)
    # UTF-8 강제: 한국어 윈도우 기본 인코딩(CP949)에서 한글 출력·파일 읽기가 깨지지 않게. PRESS_REPO: v1·v2·v3 모듈 위치
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PRESS_REPO=str(ROOT), MPLBACKEND="Agg")
    t0 = time.time()
    with open(LOGS / f"{name}.log", "w", encoding="utf-8") as log:
        proc = subprocess.run([sys.executable, script, *args], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    return proc.returncode, time.time() - t0


def compare(quick):
    """expected_results.json의 항목마다 실행 결과를 읽어 기대값과 비교한다(sha256은 일치, 숫자는 허용 오차 안)."""
    exp = json.loads((ROOT / "expected_results.json").read_text(encoding="utf-8"))
    rows = []
    for item in exp["checks"]:
        if quick and not item.get("quick", False):
            continue
        f = ROOT / item["file"]
        try:
            if item["kind"] == "sha256":
                got = sha256_lf(f)
                ok, shown = got == item["value"], got[:12]
            else:
                if item["kind"] == "json":
                    got = float(reduce(lambda o, k: o[k], item["path"], json.loads(f.read_text(encoding="utf-8"))))
                else:   # csv: where 조건에 맞는 첫 행의 열 값
                    with open(f, encoding="utf-8-sig") as fh:
                        rec = [r for r in csv.DictReader(fh) if all(str(r[k]) == str(v) for k, v in item["where"].items())]
                    got = float(rec[0][item["column"]])
                ok, shown = abs(got - item["value"]) <= item.get("tol", 1e-9), f"{got:.6g}"
        except Exception as e:      # 파일이 없거나 형식이 다르면 실패로 센다
            ok, shown = False, f"오류: {e}"
        rows.append(dict(name=item["name"], ok=ok, got=shown, expected=item["value"] if item["kind"] != "sha256" else str(item["value"])[:12],
                         report=item.get("report", "")))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="핵심 단계만(진단·모델·test 예측·2.4·2.7·4.3절 사후 계산·대조)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:      # 표준출력이 파일 객체로 바뀐 환경(일부 IDE)
        pass
    start = time.time()
    check_environment()
    place_data()
    steps = [s for s in STEPS if s[3] or not a.quick]
    summary = dict(mode="quick" if a.quick else "full", python=platform.python_version(), steps=[])

    def save_summary():
        (LOGS / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for i, (name, script, args, _, desc) in enumerate(steps, 1):
        print(f"[{i}/{len(steps)}] {name}: {desc} ... ", end="", flush=True)
        code, sec = run_step(name, script, args)
        print(f"{'완료' if code == 0 else '실패'} ({sec:.0f}초)")
        summary["steps"].append(dict(name=name, script=script, returncode=code, seconds=round(sec, 1)))
        if code != 0:       # 뒤 단계는 앞 단계 산출물을 읽으므로 바로 멈춘다
            print(f"  → 로그 확인: logs/{name}.log")
            save_summary()
            raise SystemExit(1)
    PRED.mkdir(exist_ok=True)
    for s in ("A", "B"):
        shutil.copy2(ROOT / f"code/press/tvt/outputs/test_predictions_{s}.csv", PRED / f"test_predictions_{s}.csv")
    rows = compare(a.quick)
    summary["checks"] = rows
    summary["total_seconds"] = round(time.time() - start, 1)
    save_summary()
    print("\n결과 대조 (expected_results.json = 보고서 작성 때의 결과)")
    for r in rows:
        print(f"  {'일치' if r['ok'] else '불일치'} | {r['name']}: {r['got']} (기대 {r['expected']}) {r['report']}")
    n_ok = sum(r["ok"] for r in rows)
    print(f"\n대조 {n_ok}/{len(rows)} 일치, 전체 {summary['total_seconds'] / 60:.1f}분. 예측 파일: predictions/test_predictions_A.csv, _B.csv")
    raise SystemExit(0 if n_ok == len(rows) else 2)


if __name__ == "__main__":
    main()
