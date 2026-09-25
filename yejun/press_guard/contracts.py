"""v2의 필수 코드·단계·산출물 계약. 선택적으로 기록된 항목만 확인하지 않는다."""
import hashlib
import json
from pathlib import Path
from model import D, HERE, GuardModel, VERSION

CODE_FILES = ("model.py", "train.py", "predict.py", "analyze.py", "audit.py", "verify.py", "contracts.py",
              "serve.py", "benchmark.py", "tools/clean_repro.sh", "web/app.js", "web/index.html", "web/style.css")
TRAIN_TABLES = ("metrics.csv", "rolling.csv", "cases_A.csv", "cases_B.csv")
PREDICTIONS = tuple(f"predictions_{kind}_{sid}.csv" for kind in ("normal", "abnormal") for sid in ("A", "B"))
ANALYSIS_TABLES = ("model_comparison_v2.csv", "robustness_v2.csv", "error_conditions_v2.csv",
                   "records_first_alarm_v2.csv", "uncertainty_v2.csv", "workload_v2.csv")
ANALYSIS_FILES = ANALYSIS_TABLES + ("analysis_summary.json", "model_comparison_v2.md", "fig_recall_by_position_v2.png",
                                    "fig_first_alarm_v2.png", "fig_missed_example_v2.png")
ARTIFACTS = ("guard_A.json", "guard_B.json")
SOURCES = ("press_submission/outputs/manifest.json", "press_submission/outputs/expected/manifest.json",
           "press_submission/outputs/model_comparison_all.csv", "press_submission/outputs/predictions_A.csv",
           "press_submission/outputs/predictions_B.csv", "analysis/press_advance/manifest.json",
           "analysis/press_advance/metrics.csv", "analysis/press_advance/run_experiment.py")
AUDIT_NAMES = ("실행 코드·선행 산출물이 manifest와 같음", "저장 모델이 manifest와 같음", "v1 의존 코드가 학습 당시와 같음",
               "입력 자료 해시가 학습 당시와 같음") + tuple(
    f"{sid} {name}" for sid in ("A", "B") for name in ("입력 묶음 1·7·128행과 전체 추론 동일", "독립 집계가 metrics.csv와 같음",
        "p값이 보정 순위 규칙과 같음", "이상 구간마다 알림 한 번", "날짜 이동·라벨 변경에 불변"))


def read_json(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict): raise ValueError(f"{path}: JSON 객체가 아님")
    return value


def check_files(root, recorded, required):
    bad=[]
    recorded=recorded if isinstance(recorded,dict) else {}
    for name in required:
        p=Path(root)/name
        if not p.is_file(): bad.append(f"{name}: 없음")
        elif name not in recorded: bad.append(f"{name}: 실행 해시 없음")
        elif D.sha256_file(p)!=recorded[name]: bad.append(f"{name}: 실행 후 변경")
    return bad


def training_fingerprint(manifest):
    parts={k:manifest.get(k) for k in ("version","input_hashes","code_hashes","artifacts","outputs","config")}
    return hashlib.sha256(json.dumps(parts,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def run_fingerprint(manifest):
    parts=dict(training=training_fingerprint(manifest),analysis=manifest.get("analysis"))
    return hashlib.sha256(json.dumps(parts,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def training_errors(manifest, out, artifacts, code_root=HERE):
    bad=[]
    if manifest.get("version")!=VERSION: bad.append("manifest version 불일치")
    if manifest.get("input_hashes")!=D.EXPECTED_SHA256: bad.append("고정 입력 자료 해시 불일치")
    if manifest.get("config",{}).get("rolling") is not True: bad.append("rolling 평가 미실행")
    bad+=check_files(code_root,manifest.get("code_hashes"),CODE_FILES)
    bad+=check_files(out,manifest.get("outputs"),TRAIN_TABLES+PREDICTIONS)
    bad+=check_files(artifacts,manifest.get("artifacts"),ARTIFACTS)
    for name in ARTIFACTS:
        try:
            model=GuardModel.load(Path(artifacts)/name)
            if model.state.get("input_hashes")!=manifest.get("input_hashes"): bad.append(f"{name}: 입력 해시 불일치")
            if model.state.get("split")!=name.removeprefix("guard_").removesuffix(".json"): bad.append(f"{name}: 분할 불일치")
        except (OSError,ValueError,KeyError,TypeError) as exc: bad.append(f"{name}: {exc}")
    return bad


def analysis_errors(manifest, out, source_root=HERE.parent):
    analysis=manifest.get("analysis",{})
    bad=check_files(out,analysis.get("outputs"),ANALYSIS_FILES)
    if analysis.get("training_fingerprint")!=training_fingerprint(manifest): bad.append("analysis: 다른 학습 실행의 결과")
    bad+=check_files(source_root,analysis.get("sources"),SOURCES)
    return bad


def audit_errors(audit,manifest):
    bad=[]
    checks=audit.get("checks",[])
    checks=checks if isinstance(checks,list) else []
    names=[c.get("name") for c in checks if isinstance(c,dict)]
    if len(names)!=len(AUDIT_NAMES) or set(names)!=set(AUDIT_NAMES): bad.append("audit: 필수 검사 누락·중복")
    if len(checks)!=len(names) or any(c.get("ok") is not True for c in checks if isinstance(c,dict)): bad.append("audit: 개별 검사 실패")
    if audit.get("all_ok") is not True: bad.append("audit: all_ok가 아님")
    if audit.get("run_fingerprint")!=run_fingerprint(manifest): bad.append("audit: 다른 코드·모델·산출물의 실행")
    if audit.get("version")!=manifest.get("version"): bad.append("audit: version 불일치")
    return bad


def execution_errors(manifest,out,artifacts,require_audit=True):
    bad=training_errors(manifest,out,artifacts)+analysis_errors(manifest,out)
    if require_audit:
        bad+=check_files(out,{"audit.json":manifest.get("audit_sha256")},("audit.json",))
        try: bad+=audit_errors(read_json(Path(out)/"audit.json"),manifest)
        except (OSError,ValueError,TypeError) as exc: bad.append(f"audit.json: {exc}")
    return bad
