"""보완 실험(E1·E2·E3)의 실행 계약 — 루브릭 검수 R9·R24.

실험마다 manifest에 실제 의존 코드, 원본, 기준 모델, 외부 비교표, 필수 산출물의 해시와 실제 BLAS 구성을 남긴다.
verify.py가 현재 파일과 대조한다. 결과 파일은 manifest를 쓴 뒤 바뀌면 안 된다. 그림은 CSV에서 다시 그리는 파생물이라 계약 밖이다.
"""
from pathlib import Path
import json
import time
import uuid

from common import HERE, YEJUN, D, BASE, PROTOCOL, ARTIFACTS  # noqa: F401
from press.validation import code_sha256

PROTOCOL_ID = PROTOCOL["version"]
PG = YEJUN / "press_guard"
EXT = YEJUN / "analysis" / "press_external"
SHARED_CODE = {
    "analysis/press_supplement/common.py": HERE / "common.py",
    "analysis/press_supplement/contract.py": HERE / "contract.py",
    "analysis/press_supplement/protocol.json": HERE / "protocol.json",
    "press_guard/model.py": PG / "model.py",
    "press_guard/train.py": PG / "train.py",        # E1의 v1 기준선 산식(train.baseline)
}
EXPERIMENTS = {
    "E1": dict(script="fault_injection.py", outputs=("e1_summary.csv", "e1_detection_floor.csv", "e1_reference_segments.csv"),
               local_outputs=("predictions_e1_records.csv",), artifacts=("guard_A.json", "guard_B.json"), sources={}, extra_inputs={}),
    "E2": dict(script="uci_v2.py", outputs=("e2_uci_metrics.csv", "e2_uci_strata.csv", "e2_uci_component_diagnostic_posthoc.csv", "e2_uci_comparison.csv"),
               local_outputs=(), artifacts=("guard_A.json", "guard_B.json"),   # 대회 자료 재현 점검이 동결 모델과 대조한다
               sources={"analysis/press_external/metrics.csv": EXT / "metrics.csv", "analysis/press_external/partitions.csv": EXT / "partitions.csv",
                        "press_guard/outputs/metrics.csv": PG / "outputs" / "metrics.csv"},
               extra_inputs={"uci_hydraulic_zip": EXT / "data" / "hydraulic.zip"}),
    "E3": dict(script="recalibration.py", outputs=("e3_curve.csv", "e3_stability.csv", "e3_domain_shift.csv"),
               local_outputs=(), artifacts=("guard_A.json",), sources={}, extra_inputs={}),
}


def manifest_name(exp):
    return f"{exp.lower()}_manifest.json"


def environment():
    env = D.environment()
    env["data_protocol_version"] = env.pop("protocol_version")     # 공용 v1 자료 처리 버전
    env["experiment_protocol"] = PROTOCOL_ID                        # 보완 실험 프로토콜(protocol.json)
    try:
        from threadpoolctl import threadpool_info
        env["blas_runtime"] = [{k: i.get(k) for k in ("user_api", "internal_api", "version", "num_threads")} for i in threadpool_info()]
    except ImportError:
        env["blas_runtime"] = None
    return env


def code_hashes(exp):
    code = {name: D.sha256_file(path) for name, path in SHARED_CODE.items()}
    script = EXPERIMENTS[exp]["script"]
    code[f"analysis/press_supplement/{script}"] = D.sha256_file(HERE / script)
    code["press_submission/press/* (code_sha256)"] = code_sha256()
    return code


def input_hashes(exp):
    hashes = {k: D.sha256_file(D.data_dir(BASE) / name) for k, name in D.FILES.items()}
    hashes.update({k: D.sha256_file(p) for k, p in EXPERIMENTS[exp]["extra_inputs"].items()})
    return hashes


def current(exp):
    spec = EXPERIMENTS[exp]
    return dict(code=code_hashes(exp), inputs=input_hashes(exp),
                artifacts={a: D.sha256_file(ARTIFACTS / a) for a in spec["artifacts"]},
                sources={k: D.sha256_file(p) for k, p in spec["sources"].items()})


def write_manifest(exp, out, start, config, **extra):
    spec = EXPERIMENTS[exp]
    out = Path(out)
    missing = [o for o in spec["outputs"] if not (out / o).is_file()]
    if missing:
        raise FileNotFoundError(f"{exp} 필수 산출물 없음: {missing}")
    manifest = dict(experiment=exp, protocol=PROTOCOL_ID, run_id=uuid.uuid4().hex, created=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    config=config, **current(exp),
                    outputs={o: D.sha256_file(out / o) for o in spec["outputs"]},
                    local_outputs={o: D.sha256_file(out / o) for o in spec["local_outputs"] if (out / o).is_file()},
                    environment=environment(), elapsed_s=round(time.monotonic() - start, 1), **extra)
    D.dump_json(manifest, out / manifest_name(exp))
    return manifest


def errors(exp, out, manifest=None):
    """manifest와 현재 코드·원본·모델·외부 표·산출물의 불일치 목록. 비어 있으면 통과."""
    out = Path(out)
    try:
        m = manifest if manifest is not None else json.loads((out / manifest_name(exp)).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{exp}: manifest 오류 {exc}"]
    bad = []
    if m.get("experiment") != exp or m.get("protocol") != PROTOCOL_ID:
        bad.append(f"{exp}: 실험·프로토콜 식별자 불일치")
    now = current(exp)
    for group, label in (("code", "코드"), ("inputs", "원본"), ("artifacts", "기준 모델"), ("sources", "외부 비교표")):
        recorded = m.get(group) or {}
        for name, digest in now[group].items():
            if recorded.get(name) != digest:
                bad.append(f"{exp}: {label} 변경 또는 기록 없음 — {name}")
    spec = EXPERIMENTS[exp]
    recorded = m.get("outputs") or {}
    for name in spec["outputs"]:
        path = out / name
        if not path.is_file():
            bad.append(f"{exp}: 산출물 없음 — {name}")
        elif recorded.get(name) != D.sha256_file(path):
            bad.append(f"{exp}: 산출물이 실행 기록과 다름 — {name}")
    for name, digest in (m.get("local_outputs") or {}).items():   # Git 제외 원표: 있으면 같아야 한다
        path = out / name
        if path.is_file() and D.sha256_file(path) != digest:
            bad.append(f"{exp}: 로컬 원표가 실행 기록과 다름 — {name}")
    return bad
