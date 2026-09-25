"""Claude 9ecbdcb의 네 가지 수정에 대한 실제 파일·클론 경로 검사.

파괴적 검사는 임시 클론에서만 수행한다. 원래 패키지·산출물·기대값은 읽기만 한다.
requirements.txt 환경에서:
  python recheck_claude_2.py --package ../../press_submission --out codex_recheck_2_results.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(root):
    return {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    pkg = args.package.resolve()
    repo = pkg.parents[1]
    env = dict(os.environ, OMP_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1",
               PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    before = {name: snapshot(pkg / name) for name in ("outputs", "artifacts")}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    findings = {}

    def add(name, passed, **facts):
        findings[name] = dict(passed=bool(passed), **facts)
        print(name + ": " + json.dumps(findings[name], ensure_ascii=False), flush=True)

    with tempfile.TemporaryDirectory(prefix="claude-recheck-2-") as scratch:
        tmp = Path(scratch)
        clone = tmp / "source"
        subprocess.run(["git", "clone", "-q", str(repo), str(clone)], check=True, env=env)
        cpkg = clone / "yejun" / "press_submission"
        out = cpkg / "outputs"
        expected = snapshot(out / "expected")

        def verify(*extra):
            r = subprocess.run([sys.executable, "verify.py", "--out", "outputs", *extra],
                               cwd=cpkg, env=env, text=True, capture_output=True)
            lines = r.stdout.strip().splitlines()
            return dict(exit_code=r.returncode, summary=lines[-1] if lines else r.stderr.strip(),
                        failures=[x for x in lines if x.startswith("FAIL")], stderr=r.stderr.strip())

        fresh = verify()
        add("fresh_clone_instructions", fresh["exit_code"] == 1 and "run_all.py를 먼저 실행" in fresh["stderr"], **fresh)
        for name in ("outputs", "artifacts", "data"):
            shutil.copytree(pkg / name, cpkg / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        baseline = verify()
        add("real_outputs_baseline", baseline["exit_code"] == 0, **baseline)

        # manifest를 고치는 대리 검사가 아니라 실제 실행 코드 파일을 바꾼다.
        for name in ("press/scores.py", "predict.py", "vendor/press_policy_audit.py"):
            p = cpkg / name
            original = p.read_bytes()
            p.write_bytes(original + b"\n# isolated review change\n")
            check, freeze = verify(), verify("--freeze")
            p.write_bytes(original)
            preserved = snapshot(out / "expected") == expected
            add("code_change:" + name,
                check["exit_code"] == 1 and freeze["exit_code"] == 2 and preserved
                and any("code.matches_manifest" in x for x in check["failures"]),
                verification=check, freeze_exit=freeze["exit_code"], expected_preserved=preserved)

        for name in ("main_A.json", "main_B.json"):
            p = cpkg / "artifacts" / name
            original = p.read_bytes()
            for how in ("tamper", "delete"):
                if how == "tamper":
                    state = json.loads(original)
                    state["state"]["scaler_mean"][0] += 1
                    p.write_text(json.dumps(state))
                else:
                    p.unlink()
                check, freeze = verify(), verify("--freeze")
                p.write_bytes(original)
                preserved = snapshot(out / "expected") == expected
                add("artifact_" + how + ":" + name,
                    check["exit_code"] == 1 and freeze["exit_code"] == 2 and preserved
                    and any("artifacts/" + name in x for x in check["failures"]),
                    verification=check, freeze_exit=freeze["exit_code"], expected_preserved=preserved)

        custom = cpkg / "custom_artifacts"
        (cpkg / "artifacts").rename(custom)
        relocated = verify("--artifacts", str(custom))
        default_missing = verify()
        custom.rename(cpkg / "artifacts")
        add("explicit_artifact_directory", relocated["exit_code"] == 0 and default_missing["exit_code"] == 1,
            explicit=relocated, without_override=default_missing)

        # 작업 트리의 기대값을 망가뜨려도 내부 클론은 커밋된 기대값만 사용해야 한다.
        target = out / "expected" / "model_comparison.csv"
        target.write_text("invalid uncommitted expectation\n")
        r = subprocess.run(["bash", "tools/clean_repro.sh"], cwd=cpkg,
                           env=dict(env, TMPDIR=str(tmp)), text=True, capture_output=True)
        locations = [line.removeprefix("임시 폴더: ").removesuffix(" (검사 후 삭제 가능)")
                     for line in r.stdout.splitlines() if line.startswith("임시 폴더: ")]
        inner_expected = (Path(locations[0]) / "clone/yejun/press_submission/outputs/expected"
                          if len(locations) == 1 else None)
        actual = snapshot(inner_expected) if inner_expected is not None and inner_expected.is_dir() else {}
        different = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
        same = not different
        add("clean_repro_uses_committed_expected", r.returncode == 0 and same,
            exit_code=r.returncode, expected_matches_commit=same, different_expected_files=different,
            summary=[line for line in r.stdout.splitlines() if "통과 (" in line], stderr=r.stderr.strip())

    unchanged = all(snapshot(pkg / name) == hashes for name, hashes in before.items())
    add("source_outputs_and_artifacts_unchanged", unchanged)
    result = dict(reviewed_commit=commit, reviewed_package=str(pkg), python=sys.version,
                  findings=findings, passed=all(row["passed"] for row in findings.values()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
