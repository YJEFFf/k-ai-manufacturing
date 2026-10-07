"""Run an extracted submission in a fresh environment with workspace reads denied."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--python', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--section', choices=('all', 'official', 'improvement'), default='all')
    parser.add_argument('--extra-audits-only', action='store_true')
    parser.add_argument('--reuse-result', type=Path)
    parser.add_argument('--source-bridge', type=Path)
    args = parser.parse_args()
    if args.extra_audits_only != bool(args.reuse_result and args.source_bridge):
        parser.error('Extra audits require both a completed reproduction and a source-equivalence bridge.')
    if args.extra_audits_only and args.section != 'improvement':
        parser.error('Extra audits are an improvement-section operation.')
    archive = args.archive.resolve(strict=True)
    interpreter = args.python.resolve(strict=True)
    workspace = Path(__file__).resolve().parents[3]
    work = args.work_dir.resolve()
    if work.exists():
        raise SystemExit('Verification work directory must be new; existing files are preserved.')
    if work == workspace or workspace in work.parents:
        raise SystemExit('Extracted verification must run outside the original workspace.')
    work.mkdir(parents=True)
    unpacked = work / 'unpacked'
    unpacked.mkdir()
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            name = PurePosixPath(member.filename.replace('\\', '/'))
            if name.is_absolute() or '..' in name.parts or ':' in member.filename:
                raise ValueError(f'Unsafe ZIP member: {member.filename}')
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Symbolic links are not accepted in a submission archive.')
            target = (unpacked / str(name)).resolve()
            if unpacked not in target.parents and target != unpacked:
                raise ValueError('ZIP member escapes the extraction directory.')
        handle.extractall(unpacked)
    candidates = sorted(unpacked.rglob('run_all.py'), key=lambda p: len(p.parts))
    if not candidates or (len(candidates) > 1 and len(candidates[0].parts) == len(candidates[1].parts)):
        raise ValueError('Expected one top-level run_all.py entry point.')
    entry = candidates[0]
    reuse = None
    if args.extra_audits_only:
        previous = json.loads(args.reuse_result.read_text(encoding='utf-8-sig'))
        bridge = json.loads(args.source_bridge.read_text(encoding='utf-8-sig'))
        assert previous['status'] == 'passed' and previous['returncode'] == 0
        assert previous['section'] == 'improvement' and not previous['completion_errors']
        assert bridge['status'] == 'passed_source_equivalence'
        assert bridge['source_archive_sha256'] == previous['archive_sha256']
        assert bridge['final_archive_sha256'] == hashlib.sha256(archive.read_bytes()).hexdigest()
        assert Path(previous['extracted_root']).resolve() == Path(bridge['initial_extracted_root']).resolve()
        source = Path(previous['extracted_root']) / 'yejun/analysis/press_improvement/outputs'
        destination = entry.parent / 'yejun/analysis/press_improvement/outputs'
        if destination.exists() and any(destination.iterdir()):
            raise ValueError('Final archive must not contain precomputed study outputs.')
        hashes = {}
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                raise ValueError('Reused outputs must not contain symbolic links.')
            if path.is_file():
                relative = path.relative_to(source)
                if relative.parts[0] in ('strong_baselines', 'normal_sensitivity'):
                    continue
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
                hashes[relative.as_posix()] = digest
        assert hashes
        assert bridge['csv_comparison']['all_passed']
        for item in bridge['csv_comparison']['checks']:
            assert item['numeric_equal']
            assert hashes[item['file']] == item['candidate_runtime_output_sha256']
        reuse = dict(source_archive_sha256=previous['archive_sha256'],
                     source_extracted_root=previous['extracted_root'],
                     source_bridge_sha256=hashlib.sha256(args.source_bridge.read_bytes()).hexdigest(),
                     copied_output_files_sha256=hashes,
                     scope='Reuse only outputs from the completed core reproduction after source/data/reference equivalence. All extra audit outputs are generated anew.')
    guard = work / 'workspace_guard'
    guard.mkdir()
    guard_source = '''import os, sys
from pathlib import Path
_blocked = Path(%r).resolve()
def _audit(event, args):
    if event not in ('open', 'os.listdir', 'os.scandir', 'os.chdir') or not args:
        return
    value = args[0]
    if value is None or isinstance(value, int):
        return
    try:
        path = Path(os.fsdecode(value)).resolve()
    except (TypeError, ValueError, OSError):
        return
    if path == _blocked or _blocked in path.parents:
        raise PermissionError('Clean-package verification blocked original workspace access: ' + str(path))
sys.addaudithook(_audit)
''' % str(workspace)
    (guard / 'sitecustomize.py').write_text(guard_source, encoding='utf-8')
    env = dict(os.environ)
    env.pop('PRESS_REPO', None)
    env.update(PYTHONPATH=str(guard), PYTHONNOUSERSITE='1', PYTHONUTF8='1',
               PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    info_code = 'import json,sys; print(json.dumps(dict(version=sys.version, executable=sys.executable, prefix=sys.prefix, base_prefix=sys.base_prefix)))'
    info = json.loads(subprocess.check_output([str(interpreter), '-c', info_code], env=env, cwd=work, text=True, encoding='utf-8'))
    if info['prefix'] == info['base_prefix']:
        raise ValueError('Verification requires a virtual environment.')
    probe_code = '''from pathlib import Path
try:
    Path(%r).read_bytes()
except PermissionError as error:
    assert 'blocked original workspace access' in str(error)
    print('workspace read denied')
else:
    raise SystemExit('Workspace access guard did not block the probe')
''' % str(workspace / 'yejun/AGENTS.md')
    probe = subprocess.run([str(interpreter), '-c', probe_code], env=env, cwd=work, capture_output=True, text=True, encoding='utf-8')
    if probe.returncode or probe.stdout.strip() != 'workspace read denied':
        raise RuntimeError('Audit-hook probe failed: ' + probe.stdout + probe.stderr)
    child_code = 'import subprocess,sys; subprocess.run([sys.executable, "-c", %r], check=True)' % probe_code
    child_probe = subprocess.run([str(interpreter), '-c', child_code], env=env, cwd=work, capture_output=True, text=True, encoding='utf-8')
    if child_probe.returncode or child_probe.stdout.strip() != 'workspace read denied':
        raise RuntimeError('Child-process audit-hook probe failed: ' + child_probe.stdout + child_probe.stderr)
    pip_check = subprocess.run([str(interpreter), '-m', 'pip', 'check'], env=env, cwd=work, capture_output=True, text=True, encoding='utf-8')
    freeze = subprocess.check_output([str(interpreter), '-m', 'pip', 'freeze'], env=env, cwd=work, text=True, encoding='utf-8')
    if pip_check.returncode:
        raise RuntimeError(pip_check.stdout + pip_check.stderr)
    result = dict(archive_name=archive.name,
                  archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                  interpreter=info, installed_packages=freeze.splitlines(),
                  pip_check=pip_check.stdout.strip(),
                  extracted_root=str(entry.parent),
                  python_workspace_access_guard_tested=True,
                  workspace_guard_probe=probe.stdout.strip(),
                  child_process_guard_probe=child_probe.stdout.strip(),
                  isolation_scope='Fresh venv, archive extracted outside source workspace, user site disabled, Python file-access audit guard inherited by child processes. Not an OS sandbox for native libraries or non-Python processes.',
                  section=args.section,
                  command=[str(interpreter), str(entry), '--section', args.section],
                  status='running')
    if args.extra_audits_only:
        result['command'].append('--extra-audits-only')
        result['reused_core_evidence'] = reuse
        result['extra_audits_only'] = True
    target = args.result.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    def save():
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    save()
    log = work / 'full_run.log'
    started = time.monotonic()
    with log.open('w', encoding='utf-8') as stream:
        run = subprocess.run(result['command'], cwd=entry.parent, env=env, stdout=stream, stderr=subprocess.STDOUT)
    result.update(returncode=run.returncode, seconds=round(time.monotonic()-started, 2),
                  status='passed' if run.returncode == 0 else 'failed', run_log=str(log))
    summary_files = sorted(entry.parent.rglob('*summary.json'))
    result['run_summaries'] = {}
    for path in summary_files:
        if 'logs' in path.parts or path.name == 'integration_summary.json':
            try:
                result['run_summaries'][path.relative_to(entry.parent).as_posix()] = json.loads(path.read_text(encoding='utf-8-sig'))
            except (ValueError, UnicodeError):
                pass
    completion_errors = []
    if run.returncode == 0:
        integrated = result['run_summaries'].get('logs/integrated_run_summary.json', {})
        if not integrated.get('passed') or integrated.get('section') != args.section or integrated.get('quick') is not False or integrated.get('verify_only') is not False:
            completion_errors.append('Integrated full-run completion flags are missing or invalid.')
        required = set()
        if args.section in ('all', 'official'):
            required.add('official')
        if args.extra_audits_only:
            required.update(('reference', 'strong_baselines', 'normal_sensitivity', 'normal_aggregation', 'tests'))
            if not integrated.get('extra_audits_only'):
                completion_errors.append('Extra-only execution was not declared.')
        elif args.section in ('all', 'improvement'):
            required.update(('improvement', 'metrics', 'replay', 'reference', 'independent', 'freeze', 'tests'))
        steps = integrated.get('steps', [])
        if not required.issubset({item.get('name') for item in steps}) or any(item.get('returncode') != 0 for item in steps):
            completion_errors.append('Required integration steps did not all complete successfully.')
        if args.section in ('all', 'official'):
            official = result['run_summaries'].get('logs/run_summary.json', {})
            expected = json.loads((entry.parent / 'expected_results.json').read_text(encoding='utf-8'))['checks']
            checks = official.get('checks', [])
            if official.get('mode') != 'full' or len(official.get('steps', [])) != 26 or any(item.get('returncode') != 0 for item in official.get('steps', [])):
                completion_errors.append('The complete original 26-step pipeline was not verified.')
            if not expected or len(checks) != len(expected) or not all(item.get('ok') for item in checks):
                completion_errors.append('Original expected-result checks were incomplete or unsuccessful.')
    result['completion_errors'] = completion_errors
    if completion_errors:
        result.update(status='failed', returncode=2)
    save()
    print(json.dumps(dict(status=result['status'], seconds=result['seconds'], result=str(target), log=str(log)), ensure_ascii=False))
    raise SystemExit(result['returncode'])


if __name__ == '__main__':
    main()
