"""Build a standalone submission from the original ZIP and locked study sources.

No original submission, report, raw dataset or locked experiment is modified.
The three nonselectable comparators are omitted from distribution. Every retained
calculation is checked for syntax-tree equivalence before a new distribution
reference lock is made; actual selection and evaluation must run again.
"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "yejun/analysis/press_frontier_improvement_2026-10-08"
STUDY_REL = Path("yejun/analysis/press_improvement")
NAME = "북적북적_code_통합본"
OWN_LOCKED = ("PROTOCOL.md", "frontier_model.py", "scenarios.py", "run_experiment.py",
              "vibration_branch.py")
SHARED_LOCKED = ["yejun/press_guard/model.py"] + [f"yejun/press_submission/press/{name}"
                    for name in ("data.py", "scores.py", "calibrate.py", "validation.py")]
# Files the official pipeline imports at run time; packaging must never change them.
OFFICIAL_RUNTIME = ("yejun/press_guard/model.py", "yejun/press_guard/runtime.py")
IMPROVEMENT_AUDIT_TABLES = ("strong_baselines", "normal_sensitivity")
# Added studies that read the official pipeline outputs (filled when each study is frozen).
# Each entry: source folder, destination folder, files to ship, reference tables (relative to
# source outputs), the run_all step (arguments with {ROOT}/{DATA}/{STUDY} placeholders).
SENSITIVITY_ENV = {"PRESS_OFFICIAL_COPY": "{ROOT}", "PRESS_SENS_WORK": "{ROOT}/logs/sensitivity_work",
                   "PRESS_SENS_REFERENCE_TVT": "{ROOT}/code/press/tvt", "PRESS_SENS_CLEAN_ORIGINAL": "{ROOT}"}
STAGE_ENV = {"PRESS_STAGE_TVT": "{ROOT}/code/press/tvt",
             "PRESS_STAGE_DOMAIN_STATES": "{ROOT}/code/press/domain/outputs/06_operating_regime_records.csv"}
ADDED_STUDIES: list[dict] = [
    dict(name="official_sensitivity",
         source=ROOT / "yejun/analysis/press_official_sensitivity_2026-10-08",
         dest="yejun/analysis/press_official_sensitivity",
         files=("README.md", "PROTOCOL.md", "protocol.json", "protocol_lock.json", "sens_common.py",
                "run_grid.py", "run_swap.py", "run_e3.py", "make_summary.py"),
         # v2-family tables only; the swap tables also hold guidebook-LSTM rows that vary slightly by machine.
         reference_tables=("grid_metrics.csv", "grid_distribution.csv", "grid_main_effects.csv", "grid_oat.csv",
                           "grid_alpha01_wide.csv", "grid_alpha03_wide.csv", "grid_alpha05_wide.csv",
                           "grid_reference_v2.csv", "r2_ref_grid.csv", "e3_grid_per_window.csv",
                           "e3_grid_pooled.csv", "e3_r2_ref.csv"),
         steps=[dict(name=f"official_sensitivity_{part}", env=SENSITIVITY_ENV,
                     args=[f"{{ROOT}}/yejun/analysis/press_official_sensitivity/{script}"])
                for part, script in (("grid", "run_grid.py"), ("swap", "run_swap.py"),
                                     ("e3", "run_e3.py"), ("summary", "make_summary.py"))]),
    dict(name="stage_replay",
         source=ROOT / "yejun/analysis/press_stage_replay_2026-10-08",
         dest="yejun/analysis/press_stage_replay",
         files=("README.md", "common.py", "replay.py", "alarm_volume.py"),
         reference_tables=("replay_counts.csv", "alarm_events.csv", "alarm_volume_sets.csv",
                           "alarm_volume_states.csv", "repeat_criterion.csv"),
         steps=[dict(name="stage_replay", env=STAGE_ENV,
                     args=["{ROOT}/yejun/analysis/press_stage_replay/replay.py", "--data", "{DATA}",
                           "--official-cache", "{ROOT}/code/press/tvt/cache"]),
                dict(name="stage_alarm_volume", env=STAGE_ENV,
                     args=["{ROOT}/yejun/analysis/press_stage_replay/alarm_volume.py", "--data", "{DATA}"])]),
]
# Console/streaming files added to yejun/press_guard (never model.py/runtime.py).
PRESS_GUARD_UPDATES: tuple[str, ...] = ("stages.py", "stage_console.py", "tools/capture_stage_console.py", "README.md",
                                        "web/index.html", "web/app.js", "web/style.css",
                                        "web/stage.html", "web/stage.js", "web/stage.css")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path, normalize=False):
    data = Path(path).read_bytes()
    return digest(data.replace(b"\r\n", b"\n") if normalize else data)


def canonical_hash(obj):
    return digest(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path):
    return Path(path).read_text(encoding="utf-8")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def neutral_names(text):
    return text.replace("competitor_reference", "reference_methods").replace("CompetitorReference", "MethodReference")


class NormalizeAST(ast.NodeTransformer):
    """Canonicalize approved packaging names; leave every calculation intact."""
    def visit_Module(self, node):
        node = self.generic_visit(node)
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body.pop(0)
        node.body = [item for item in node.body if not (
            isinstance(item, ast.Assign) and any(isinstance(target, ast.Name) and target.id in ("SOURCE_COMMIT", "SOURCE_URL") for target in item.targets))]
        return node

    def visit_Name(self, node):
        node.id = neutral_names(node.id)
        return node

    def visit_ClassDef(self, node):
        node.name = neutral_names(node.name)
        return self.generic_visit(node)

    def visit_ImportFrom(self, node):
        node.module = neutral_names(node.module or "")
        for alias in node.names:
            alias.name = neutral_names(alias.name)
        return self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            node.value = neutral_names(node.value)
        return node


def calculation_ast(source):
    return ast.dump(NormalizeAST().visit(ast.parse(source)), include_attributes=False)


def portable_reference(text):
    parsed = ast.parse(text)
    end = parsed.body[0].end_lineno
    remainder = "\n".join(text.splitlines()[end:]) + "\n"
    lines = [line for line in remainder.splitlines() if not line.startswith(("SOURCE_COMMIT =", "SOURCE_URL ="))]
    header = '''"""Causal PCA-MSPC and shrinkage Mahalanobis reference statistics.

PCA scores combine scaled Hotelling T-squared and squared prediction error.
Ledoit-Wolf covariance: O. Ledoit and M. Wolf, Journal of Multivariate Analysis
88(2), 365-411 (2004), doi:10.1016/S0047-259X(03)00096-4.
The min statistic is jointly recalibrated; it is not an AND of independently
calibrated alarms. All preprocessing and record-level budgets are shared.
"""
'''
    return neutral_names(header + "\n".join(lines) + "\n")


def portable_protocol(text):
    lines = text.splitlines()
    lines[0] = "# 정상 전용 선택과 기록 단위 융합 실험 — 고정 프로토콜"
    for index, line in enumerate(lines):
        if "경쟁팀 일반 알고리즘" in line:
            lines[index] = "- 단독 8개와 결합 48개, 모두 56개를 고정한다. 별도 보정 OR 4개는 선택 대상이 아니다."
        elif "기존 보고서를 먼저 검수한 결과" in line:
            lines[index] = "선정 로그와 잠금 해시를 outputs/에 남긴 뒤 최종 평가한다. 이 배포본은 선택 대상이 아니었던 비교기 3개를 제외하고, 남은 56개 후보의 계산은 유지한다. 정상 전용 선택부터 다시 실행한다. 역사적 선택 시각과 배포 생성 시각은 구분해 기록하며, 원래 잠금 SHA-256은 package_manifest.json에 연결한다."
    return "\n".join(lines) + "\n"


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError(f"Expected exactly one packaging edit: {before[:80]!r}")
    return text.replace(before, after, 1)


def strip_reference_frontier(text):
    edits = [
        ('from competitor_reference import CompetitorReference\n', ''),
        ('    candidates += [dict(name=x, kind="reference", components=[x], weight=1.0,\n'
         '                        complexity=3, selectable=False)\n'
         '                   for x in ("REF_PCA", "REF_VIB", "REF_AND")]\n', ''),
        ('    assert len(candidates) == 59', '    assert len(candidates) == 56'),
        ('        self.reference_ = CompetitorReference().fit(records)\n', ''),
        ('        ref = self.reference_.score_parts(records)\n'
         '        out.update({"REF_PCA": ref["stage1"], "REF_VIB": ref["stage2"], "REF_AND": ref["and"]})\n', ''),
    ]
    for before, after in edits:
        text = replace_once(text, before, after)
    return text


def strip_reference_run(text):
    for before, after in (
        ('"vibration_branch.py", "competitor_reference.py"', '"vibration_branch.py"'),
        ('baseline_scope="59 protocol candidates', 'baseline_scope="56 protocol candidates'),
        ('candidates=59, separately_calibrated_or_comparators=4', 'candidates=56, separately_calibrated_or_comparators=4'),
    ):
        text = replace_once(text, before, after)
    return text


class RetainedCalculationAST(ast.NodeTransformer):
    """Project out only the three nonselectable branches and count metadata."""
    def visit_ImportFrom(self, node):
        return None if node.module == "competitor_reference" else node

    def visit_AugAssign(self, node):
        if isinstance(node.target, ast.Name) and node.target.id == "candidates":
            names = [item.value for item in ast.walk(node.value) if isinstance(item, ast.Constant) and isinstance(item.value, str) and item.value.startswith("REF_")]
            if set(names) == {"REF_PCA", "REF_VIB", "REF_AND"}:
                return None
        return self.generic_visit(node)

    def visit_Assign(self, node):
        target = node.targets[0]
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self" and target.attr == "reference_":
            return None
        if isinstance(target, ast.Name) and target.id == "ref" and isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == "self.reference_.score_parts":
            return None
        return self.generic_visit(node)

    def visit_Expr(self, node):
        call = node.value
        if isinstance(call, ast.Call) and ast.unparse(call.func) == "out.update" and len(call.args) == 1 and isinstance(call.args[0], ast.Dict):
            if {key.value for key in call.args[0].keys if isinstance(key, ast.Constant)} == {"REF_PCA", "REF_VIB", "REF_AND"}:
                return None
        return self.generic_visit(node)

    def visit_Assert(self, node):
        if ast.unparse(node.test) == "len(candidates) == 59":
            node.test.comparators[0].value = 56
        return self.generic_visit(node)

    def visit_Tuple(self, node):
        node.elts = [item for item in node.elts if not (isinstance(item, ast.Constant) and item.value == "competitor_reference.py")]
        return self.generic_visit(node)

    def visit_keyword(self, node):
        if node.arg == "candidates" and isinstance(node.value, ast.Constant) and node.value.value == 59:
            node.value.value = 56
        if node.arg == "baseline_scope" and isinstance(node.value, ast.Constant):
            node.value.value = node.value.value.replace("59 protocol candidates", "56 protocol candidates")
        return self.generic_visit(node)


def retained_calculation_ast(text):
    return ast.dump(RetainedCalculationAST().visit(ast.parse(text)), include_attributes=False)


def strip_anonymous_metadata(text):
    nodes = [node for node in ast.walk(ast.parse(text)) if isinstance(node, ast.keyword) and node.arg == "competitor"]
    assert len(nodes) == 1, "Expected one historical anonymous metadata keyword"
    node = nodes[0]
    expected = ast.parse('dict(repo="공개된 지도학습 분석(이름 생략)", f1=0.944)', mode="eval").body
    assert ast.dump(node.value) == ast.dump(expected), "Unexpected content in removable metadata"
    lines = text.splitlines(keepends=True)
    assert node.lineno == node.end_lineno
    del lines[node.lineno - 1]
    after = "".join(lines)
    class RemoveMetadata(ast.NodeTransformer):
        def visit_Call(self, call):
            call.keywords = [keyword for keyword in call.keywords if keyword.arg != "competitor"]
            return self.generic_visit(call)
    expected_ast = RemoveMetadata().visit(ast.parse(text))
    assert ast.dump(expected_ast, include_attributes=False) == ast.dump(ast.parse(after), include_attributes=False)
    return after


def strip_reference_tests(text):
    text = text.replace("test_declared_grid_has_48_fusions_and_11_references", "test_declared_grid_has_48_fusions_and_8_singles")
    text = text.replace('== 59', '== 56')
    text = text.replace('"VR1", "VR3", "VD1", "VD3",\n            "REF_PCA", "REF_VIB", "REF_AND"', '"VR1", "VR3", "VD1", "VD3"')
    text = text.replace('assert all(not s["selectable"] for s in grid if s["kind"] == "reference")', 'assert all(s["selectable"] for s in grid)')
    text = text.replace('"VD1": 2, "VD3": 4,\n              "REF_PCA": 9, "REF_VIB": 9, "REF_AND": 9', '"VD1": 2, "VD3": 4')
    text = text.replace('["V2", "CD+VD3@1", "REF_AND"]', '["V2", "CD+VD3@1"]')
    text = text.replace('fresh.guard_, fresh.vibration_, fresh.reference_,', 'fresh.guard_, fresh.vibration_,')
    assert "REF_" not in text and "reference_" not in text
    return text


def copy_filtered_table(source, destination):
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = [name for name in reader.fieldnames if not name.startswith("REF_")]
        rows = [row for row in reader if not row.get("model", "").startswith("REF_")]
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def source_lock(root):
    paths = [STUDY_REL / name for name in OWN_LOCKED] + [Path(p) for p in SHARED_LOCKED]
    return {p.as_posix(): file_hash(root / p, True) for p in paths}


def verify_historical_lock():
    payload = json.loads(read(SOURCE / "outputs/selection_lock.json"))
    expected = payload.pop("lock_sha256")
    assert canonical_hash(payload) == expected, "Historical lock payload changed"
    assert payload["normal_only_selection"] and not payload["abnormal_file_read"]
    for field, filename in (("config_sha256", "config.json"), ("selection_sha256", "selection.json"),
                            ("development_candidates_sha256", "development_candidates.csv")):
        assert file_hash(SOURCE / "outputs" / filename) == payload[field], filename
    for relative, expected_hash in payload["source_sha256_lf"].items():
        assert file_hash(ROOT / relative, True) == expected_hash, relative
    payload["lock_sha256"] = expected
    return payload


def extract_original(archive, target):
    copied = {}
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            if info.is_dir():
                continue
            relative = Path(*Path(info.filename).parts[1:])
            if relative.name in {"HISTORY.md", "AGENTS.md", "CLAUDE.md"}:
                continue  # Internal coordination notes are not execution inputs.
            if relative.parts[0] == "predictions":
                relative = Path("reference_results/official_predictions") / Path(*relative.parts[1:])
            if relative.suffix in (".pkl", ".pt", ".pth") or "cache" in relative.parts:
                raise ValueError(f"Precomputed fitted state is not allowed: {info.filename}")
            destination = (target / relative).resolve()
            if not destination.is_relative_to(target.resolve()):
                raise ValueError(f"Unsafe archive member: {info.filename}")
            data = handle.read(info)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            copied[relative.as_posix()] = digest(data)
    return copied


def build(target, include_extra_audits=True, attach_verification=None, packaging_utc=None):
    historical = verify_historical_lock()
    verification_basis = None
    if attach_verification is not None:
        # Clean-run records of an earlier build whose computational files are identical (checked by
        # verify_attached_build.py after packaging); they describe that run, not new computation.
        record = json.loads(read(Path(attach_verification) / "clean_full_run.json"))
        verification_basis = dict(run_archive_sha256=record["archive_sha256"], files=[],
                                  note="Run records of the archive above; this archive adds only these record files")
        for path in sorted(Path(attach_verification).glob("*.json")):
            destination = target / "verification" / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            verification_basis["files"].append(destination.relative_to(target).as_posix())
    packaging_created_utc = packaging_utc or datetime.now(timezone.utc).isoformat()
    original_zip = ROOT / "claude/submission/북적북적_code.zip"
    originals = extract_original(original_zip, target)
    # Keep the original runner and expected result contracts in this same layout.
    (target / "run_all.py").rename(target / "run_official.py")
    (target / "README.md").rename(target / "README_original.md")
    (target / "environment.yml").rename(target / "environment_original.yml")
    metadata_path = target / "code/press/domain/05_supervised_confound.py"
    metadata_original_hash = file_hash(metadata_path, True)
    write(metadata_path, strip_anonymous_metadata(read(metadata_path)))
    for path in (HERE / "templates").iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)
    study = target / STUDY_REL
    study.mkdir(parents=True, exist_ok=True)
    transformations = [dict(file=metadata_path.relative_to(target).as_posix(),
        source_sha256_lf=metadata_original_hash,
        distribution_sha256_lf=file_hash(metadata_path, True),
        change="One unused anonymous output metadata keyword removed; all remaining AST identical")]
    for filename in ("frontier_model.py", "scenarios.py", "run_experiment.py", "vibration_branch.py"):
        before = read(SOURCE / filename)
        after = strip_reference_frontier(before) if filename == "frontier_model.py" else (
            strip_reference_run(before) if filename == "run_experiment.py" else before)
        assert retained_calculation_ast(before) == retained_calculation_ast(after), f"Retained numerical source changed: {filename}"
        destination = study / filename
        write(destination, after)
        transformations.append(dict(file=destination.relative_to(target).as_posix(),
                                    source_sha256_lf=file_hash(SOURCE / filename, True),
                                    distribution_sha256_lf=file_hash(destination, True),
                                    retained_calculation_ast_equivalent=True))
    write(study / "PROTOCOL.md", portable_protocol(read(SOURCE / "PROTOCOL.md")))
    # Existing ZIP must contain precisely the locked shared numerical modules.
    for relative in SHARED_LOCKED:
        assert file_hash(target / relative, True) == file_hash(ROOT / relative, True), relative
    for filename in ("test_calibration_contract.py", "test_frontier_contracts.py", "test_scenario_contracts.py",
                     "test_selection_lock.py", "test_vibration_branch.py", "test_holdout_contracts.py"):
        before = read(SOURCE / "tests" / filename)
        after = strip_reference_tests(before) if filename == "test_frontier_contracts.py" else before
        write(study / "tests" / filename, after)
    for filename in ("verify_results.py", "verify_replay.py", "validate_holdout.py"):
        before = read(SOURCE / filename)
        after = before
        if filename == "verify_results.py":
            after = after.replace("from build_hwpx_copy import verify_protected_sources", "import sys\nsys.path.insert(0, str(Path(__file__).resolve().parents[3]))\nfrom package_integrity import verify_package")
            after = after.replace("protected_sources=verify_protected_sources()", "package_integrity=verify_package()")
            old_functions = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(before).body if isinstance(node, ast.FunctionDef)}
            new_functions = {node.name: ast.dump(node, include_attributes=False) for node in ast.parse(after).body if isinstance(node, ast.FunctionDef)}
            assert all(old_functions[name] == new_functions[name] for name in ("close", "verify_actual", "verify_injection"))
        write(study / filename, after)
    extra_tables = []
    if include_extra_audits:
        for filename in ("audit_strong_baselines.py", "audit_normal_sensitivity.py", "verify_normal_sensitivity.py"):
            shutil.copy2(SOURCE / filename, study / filename)
        for filename in ("test_strong_baselines.py", "test_normal_sensitivity.py"):
            shutil.copy2(SOURCE / "tests" / filename, study / "tests" / filename)
        for subdir in IMPROVEMENT_AUDIT_TABLES:
            for path in sorted((SOURCE / "outputs" / subdir).glob("*.csv")):
                destination = target / "reference_results/extra_audits/improvement" / subdir / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                extra_tables.append(dict(group="improvement", reference=destination.relative_to(target).as_posix(),
                                         generated=(STUDY_REL / "outputs" / subdir / path.name).as_posix()))
    official_audits = []
    for added in ADDED_STUDIES:
        destination = target / added["dest"]
        for relative in added["files"]:
            (destination / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(added["source"]) / relative, destination / relative)
        for relative in added["reference_tables"]:
            reference = target / "reference_results/extra_audits/official" / added["name"] / Path(relative).name
            reference.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(added["source"]) / "outputs" / relative, reference)
            extra_tables.append(dict(group="official", reference=reference.relative_to(target).as_posix(),
                                     generated=(Path(added["dest"]) / "outputs" / relative).as_posix()))
        for spec in added["steps"]:
            official_audits.append(dict(name=spec["name"], args=spec["args"], env=spec.get("env", {})))
    console_updates = []
    for relative in PRESS_GUARD_UPDATES:
        source_path, destination = ROOT / "yejun/press_guard" / relative, target / "yejun/press_guard" / relative
        previous = file_hash(destination, True) if destination.is_file() else None
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        console_updates.append(dict(file=f"yejun/press_guard/{relative}", previous_sha256_lf=previous,
                                    distribution_sha256_lf=file_hash(destination, True),
                                    change="Two-stage console/streaming code; not imported by the official pipeline"))
    for relative in OFFICIAL_RUNTIME:
        assert relative not in {item["file"] for item in console_updates}, relative
        assert file_hash(target / relative) == originals[relative], f"Official runtime changed: {relative}"
    reference = target / "reference_results/improvement"
    reference.mkdir(parents=True, exist_ok=True)
    for path in (SOURCE / "outputs").iterdir():
        if path.suffix == ".csv" and path.name not in ("A_abnormal_records.csv", "B_abnormal_records.csv"):
            copy_filtered_table(path, reference / path.name)
    config = json.loads(read(SOURCE / "outputs/config.json"))
    config["candidates"] = [spec for spec in config["candidates"] if spec["kind"] != "reference"]
    config["baseline_scope"] = config["baseline_scope"].replace("59 protocol candidates", "56 protocol candidates")
    assert len(config["candidates"]) == 56 and all(spec["selectable"] for spec in config["candidates"])
    write_json(reference / "config.json", config)
    selection = json.loads(read(SOURCE / "outputs/selection.json"))
    assert selection["candidates"] == 59
    selection["candidates"] = 56
    write_json(reference / "selection.json", selection)
    packaged_lock = dict(historical)
    packaged_lock.pop("lock_sha256")
    packaged_lock["created_utc"] = packaging_created_utc
    packaged_lock["original_selection_created_utc"] = historical["created_utc"]
    packaged_lock["source_sha256_lf"] = source_lock(target)
    for field, filename in (("config_sha256", "config.json"), ("selection_sha256", "selection.json"),
                            ("development_candidates_sha256", "development_candidates.csv")):
        packaged_lock[field] = file_hash(reference / filename)
    packaged_lock["packaging"] = dict(original_selection_lock_sha256=historical["lock_sha256"],
        packaging_created_utc=packaging_created_utc,
        status="Historical reference projected to 56 retained candidates; this is not a fresh execution lock",
        purpose="Three nonselectable comparators removed; all retained calculations and selection rule unchanged",
        retained_calculation_ast_equivalent=True)
    packaged_lock["lock_sha256"] = canonical_hash(packaged_lock)
    write_json(reference / "selection_lock.json", packaged_lock)
    # The run starts from raw inputs and recreates outputs; reference artifacts
    # are never used as computed results, and historical timestamps stay separate.
    unchanged = sum(file_hash(target / name) == old for name, old in originals.items()
                    if (target / name).is_file() and name not in ("run_all.py", "README.md", "requirements.txt", "environment.yml"))
    manifest = dict(schema=2, created_utc=packaging_created_utc,
        original_submission_sha256=file_hash(original_zip),
        original_submission_unchanged_files=unchanged,
        original_selection_lock_sha256=historical["lock_sha256"],
        original_selection_created_utc=historical["created_utc"],
        packaged_selection_lock_sha256=packaged_lock["lock_sha256"],
        selected=historical["selected"], calculation_ast_equivalent=True,
        calculation_equivalence_scope="All retained 56 candidates and four OR comparisons; three nonselectable comparators omitted",
        reference_derivation="Historical tables filtered by model identity only; numeric cells for retained models unchanged. Candidate count updated from 59 to 56. A fresh all-phase execution is required to claim reproduction.",
        packaging_status="Sources assembled; clean reproduction is recorded separately and not implied by this manifest",
        optional_audits_included=include_extra_audits,
        transformations=transformations,
        improvement_reference_csv_files=sorted(path.name for path in reference.glob("*.csv")),
        lock_scope="Historical lock retained by hash; distribution lock uses actual packaged source hashes. A fresh run generates its own normal-only selection lock.",
        extra_reference_tables=extra_tables,
        official_audits=official_audits,
        console_updates=console_updates,
        verification_basis=verification_basis,
        immutable_files_sha256={})
    for path in sorted(target.rglob("*")):
        if path.is_file():
            relative = path.relative_to(target).as_posix()
            # Runtime emits generated outputs to these locations. The immutable
            # reference_tables directory and all sources/data remain checked.
            manifest["immutable_files_sha256"][relative] = file_hash(path)
    write_json(target / "package_manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / f"{NAME}.zip")
    parser.add_argument("--include-extra-audits", action="store_true", help="Accepted for compatibility; added audits are included by default")
    parser.add_argument("--no-extra-audits", action="store_true", help="Build without the added audits")
    parser.add_argument("--attach-verification", type=Path, help="Folder with clean-run JSON records of an earlier identical build")
    parser.add_argument("--packaging-utc", help="Reuse the packaging timestamp of the executed build so its files stay byte-identical")
    args = parser.parse_args()
    args.include_extra_audits = not args.no_extra_audits
    output = args.output.resolve()
    if not output.is_relative_to(HERE) or output.suffix != ".zip":
        raise ValueError("Output ZIP must stay inside this integration workspace")
    build_root = HERE / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    target = Path(tempfile.mkdtemp(prefix="package_", dir=build_root)) / NAME
    target.mkdir()
    manifest = build(target, include_extra_audits=args.include_extra_audits,
                     attach_verification=args.attach_verification, packaging_utc=args.packaging_utc)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                handle.write(path, (Path(NAME) / path.relative_to(target)).as_posix())
    result = dict(zip=str(output), package=str(target), zip_sha256=file_hash(output),
                  zip_bytes=output.stat().st_size,
                  immutable_files=len(manifest["immutable_files_sha256"]),
                  original_selection_lock_sha256=manifest["original_selection_lock_sha256"],
                  packaged_selection_lock_sha256=manifest["packaged_selection_lock_sha256"],
                  calculation_ast_equivalent=True)
    result["optional_audits_included"] = args.include_extra_audits
    write_json(HERE / "build_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
