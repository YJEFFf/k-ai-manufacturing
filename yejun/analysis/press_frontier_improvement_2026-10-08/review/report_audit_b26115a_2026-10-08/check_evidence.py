"""Compare the frozen report to saved results without running or editing models."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import zipfile

import pymupdf

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
ROOT = STUDY.parents[2]
OUT = STUDY / 'outputs'
SNAPSHOT = json.loads((HERE / 'snapshot.json').read_text(encoding='utf-8'))
REPORT = ROOT / next(p for p in SNAPSHOT['files_sha256'] if p.endswith('.md'))
ARCHIVE = ROOT / next(p for p in SNAPSHOT['files_sha256'] if p.endswith('.zip'))
REPORT_REL = REPORT.relative_to(ROOT).as_posix()
BASELINE_MD = subprocess.check_output(['git', 'show', SNAPSHOT['commit'] + ':' + REPORT_REL], cwd=ROOT)
assert hashlib.sha256(BASELINE_MD).hexdigest() == SNAPSHOT['files_sha256'][REPORT_REL]
LINES = BASELINE_MD.decode('utf-8-sig').splitlines()
CHECKS = []
SOURCES = {}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(path):
    SOURCES[path.relative_to(ROOT).as_posix()] = digest(path)
    return path.read_text(encoding='utf-8-sig')


def rows(relative):
    return list(csv.DictReader(io.StringIO(source(OUT / relative))))


def select(table, **criteria):
    matches = [r for r in table if all(r[k] == str(v) for k, v in criteria.items())]
    assert len(matches) == 1, (criteria, len(matches))
    return matches[0]


def bit(value):
    assert value in ('0', '1', 'True', 'False'), value
    return value in ('1', 'True')


def cell(line, column):
    # Numbered table column after the label; all selected labels lack escaped pipes.
    return LINES[line - 1].split('|')[column + 1].strip()


def check(line, column, values, decimals=0, scale=1):
    printed = re.findall(r'[-+]?\d+(?:\.\d+)?', cell(line, column))
    unrounded = [float(v) * scale for v in values]
    calculated = [format(v, f'.{decimals}f') for v in unrounded]
    within_display_precision = len(printed) == len(unrounded) and all(
        abs(float(p) - v) <= 0.5 * 10 ** -decimals + 1e-10 for p, v in zip(printed, unrounded))
    CHECKS.append(dict(line=line, column=column, reported=printed,
                       calculated=calculated, unrounded=unrounded,
                       exact_formatted_match=printed == calculated,
                       within_display_precision=within_display_precision))


def main():
    before = {name: digest(ROOT / name) for name in SNAPSHOT['files_sha256']}
    assert digest(ARCHIVE) == SNAPSHOT['files_sha256'][ARCHIVE.relative_to(ROOT).as_posix()]

    actual = rows('actual_metrics.csv')
    for line, model in [(404, 'V2'), (405, 'V2+VD3@1'), (406, 'VD3'), (407, 'OR_V2_VD3')]:
        ab = [select(actual, split=s, alpha='0.01', model=model, abnormal_subset='all21') for s in 'AB']
        for column, key, precision in [(1, 'row_f1', 3), (2, 'normal_fp_records', 0),
                                       (3, 'detected_records', 0), (4, 'fn', 0)]:
            check(line, column, [r[key] for r in ab], precision)

    injection = {s: rows(f'{s}_injection.csv') for s in 'AB'}
    families = ['current_distortion', 'vibration_noise', 'vibration_impulse', 'vibration_amplification']
    for line, family, strength in [(416, families[0], .5), (417, families[0], 1),
                                   (418, families[1], .5), (419, families[1], 1),
                                   (420, families[2], 2), (421, families[2], 4),
                                   (422, families[3], .5), (423, families[3], 1)]:
        for column, model in [(1, 'V2'), (2, 'V2+VD3@1')]:
            values = [statistics.mean(float(r['detection_rate']) for r in injection[s]
                                      if r['model'] == model and r['family'] == family
                                      and float(r['strength']) == strength and float(r['alpha']) == .01)
                      for s in 'AB']
            check(line, column, values, 1, 100)

    stress = {s: rows(f'{s}_stress.csv') for s in 'AB'}
    frequency = {s: rows(f'normal_sensitivity/{s}_frequency.csv') for s in 'AB'}
    for line, kind in [(433, 'offset'), (434, 'gain'), (435, 'load'),
                       (436, 'quantization'), (437, 'jitter'), (438, 'frequency')]:
        for column, model in [(1, 'V2'), (2, 'V2+VD3@1')]:
            values = []
            for split in 'AB':
                table = frequency[split] if kind == 'frequency' else stress[split]
                selected = [r for r in table if r['model'] == model and float(r['alpha']) == .01
                            and (kind == 'frequency' or r['kind'] == kind)]
                values.append(max(float(r['normal_record_fpr']) for r in selected))
            check(line, column, values, 1, 100)

    strong = rows('strong_baselines/actual_metrics.csv')
    family_summary = rows('strong_baselines/injection_family_summary.csv')
    for line, model in [(447, 'V2'), (448, 'V2+VD3@1'),
                         (449, '5NN_feature_matched'), (450, 'RidgeForecast_3channel')]:
        ab = [select(strong, split=s, alpha='0.01', model=model, abnormal_subset='all21') for s in 'AB']
        check(line, 1, [r['row_f1'] for r in ab], 3)
        check(line, 2, [r['normal_fp_records'] for r in ab])
        for column, family in enumerate(families, 3):
            check(line, column, [select(family_summary, phase=s, model=model, family=family)['detection_rate']
                                 for s in 'AB'], 1, 100)

    control_contrasts = [r for r in family_summary if r['model'] == '5NN_feature_matched'
                        and r['family'] in ['vibration_noise', 'vibration_impulse'] and r['phase'] in 'AB']
    bootstrap = [r for r in rows('strong_baselines/paired_block_bootstrap.csv') if float(r['alpha']) == .01]
    stability = json.loads(source(OUT / 'normal_sensitivity/summary.json'))['leave_one_family_out_choices']
    calibration = [r for r in rows('normal_sensitivity/derived_calibration_deltas.csv')
                   if r['split'] == 'B' and r['evaluation_family'] == 'intermittent_zeroing'
                   and r['contaminated_records'] in ('0', '1', '5')]

    official = []
    with zipfile.ZipFile(ARCHIVE) as archive:
        def read_zip(suffix):
            matches = [name for name in archive.namelist() if name.endswith('/' + suffix)
                       and name.count('/') == suffix.count('/') + 1]
            assert len(matches) == 1, (suffix, matches)
            return archive.read(matches[0]).decode('utf-8-sig')
        config = json.loads(read_zip('reference_results/improvement/config.json'))
        for split in 'AB':
            table = list(csv.DictReader(io.StringIO(read_zip(
                f'reference_results/official_predictions/test_predictions_{split}.csv'))))
            for column, target in [('locked_v2_R1_realtime', '1.000' if split == 'A' else '0.995'),
                                    ('final_v2_R1_R2_realtime', '1.000'),
                                    ('v2_realtime', '0.965' if split == 'A' else '0.970')]:
                tp = sum(bit(r['label']) and bit(r[column]) for r in table)
                fp = sum(not bit(r['label']) and bit(r[column]) for r in table)
                fn = sum(bit(r['label']) and not bit(r[column]) for r in table)
                f1 = 2 * tp / (2 * tp + fp + fn)
                official.append(dict(report_line=682, split=split, prediction=column, tp=tp, fp=fp, fn=fn,
                                     f1=f1, report_rounded=target, passed=f'{f1:.3f}' == target))
        runner_uses_current_interpreter = 'subprocess.run([sys.executable,' in read_zip('run_all.py')

    layout = {}
    baseline_pdf = Path(SNAPSHOT['temporary_previews']) / 'baseline.pdf'
    if not baseline_pdf.exists():
        baseline_pdf = REPORT.with_suffix('.pdf')
    assert digest(baseline_pdf) == SNAPSHOT['files_sha256'][REPORT.with_suffix('.pdf').relative_to(ROOT).as_posix()]
    with pymupdf.open(baseline_pdf) as pdf:
        page = pdf[30]
        text_bottom = max(span['bbox'][3] for b in page.get_text('dict')['blocks'] if b['type'] == 0
                          for line in b['lines'] for span in line['spans'] if span['text'].strip())
        drawing_bottom = max(d['rect'].y1 for d in page.get_drawings())
        layout = dict(page=31, page_height_pt=page.rect.height,
                      text_bottom_pt=text_bottom, text_margin_mm=(page.rect.height-text_bottom)/72*25.4,
                      drawing_bottom_pt=drawing_bottom,
                      drawing_margin_mm=(page.rect.height-drawing_bottom)/72*25.4)

    probe = ('import sys,json,importlib.util; '
             'print(json.dumps(dict(executable=sys.executable,prefix=sys.prefix,'
             'base_prefix=sys.base_prefix,numpy_found=importlib.util.find_spec("numpy") is not None)))')
    probes = []
    for executable in ['python', sys.executable]:
        completed = subprocess.run([executable, '-c', probe], capture_output=True, text=True)
        probes.append(dict(command=executable, returncode=completed.returncode,
                           stdout=completed.stdout.strip(), stderr=completed.stderr.strip()))

    clean = json.loads(source(ROOT / 'yejun/submission/press_integrated_2026-10-08/verification/clean_run.json'))
    clean_link = dict(archive_hash_matches=clean['final_archive_sha256'] == digest(ARCHIVE),
                     previous_status=clean['status'], previous_official_checks=clean['official_expected_checks'],
                     previous_contract_checks=clean['improvement_tests_passed'],
                     fresh_full_model_runs_this_review=False)
    unchanged = {name: digest(ROOT / name) == expected for name, expected in before.items()}
    result = dict(table_cell_pairs_checked=len(CHECKS), table_numbers_checked=sum(len(c['reported']) for c in CHECKS),
                  table_checks=CHECKS, official_prediction_recalculations=official,
                  selected_candidate_count=sum(c['selectable'] for c in config['candidates']),
                  five_nn_control_contrasts=control_contrasts, bootstrap_source_rows=bootstrap,
                  leave_one_family_out=stability, calibration_contamination_source_rows=calibration,
                  page_31_margin=layout,
                  interpreter_probes=probes, packaged_runner_uses_sys_executable=runner_uses_current_interpreter,
                  previous_clean_execution_evidence=clean_link, source_sha256=SOURCES,
                  protected_files_unchanged_during_this_check=unchanged,
                  live_files_match_review_start={name: digest(ROOT / name) == expected
                                                 for name, expected in SNAPSHOT['files_sha256'].items()},
                  reviewed_commit=SNAPSHOT['commit'], report_modified_by_review=False,
                  scope='Saved-result cross-check and harmless interpreter probes only; no training or report edits.')
    failures = [c for c in CHECKS if not c['within_display_precision']]
    boundaries = [c for c in CHECKS if c['within_display_precision'] and not c['exact_formatted_match']]
    result['rounding_boundary_notes'] = boundaries
    result['numbers_outside_display_precision'] = failures
    # A half-step rounding difference (8.75 -> 8.7 / 8.8) is retained, not silently discarded.
    (HERE / 'evidence_check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(table_cell_pairs=len(CHECKS), table_numbers=result['table_numbers_checked'],
                          failures=failures, rounding_boundary_notes=boundaries,
                          official=official, margin=layout, interpreters=probes,
                          unchanged=all(unchanged.values())), ensure_ascii=False))
    assert not failures and all(r['passed'] for r in official) and all(unchanged.values())


if __name__ == '__main__':
    main()
