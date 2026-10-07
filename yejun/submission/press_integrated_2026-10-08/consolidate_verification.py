"""Join completed executions and explicitly scoped source bridges for the final ZIP."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / 'verification'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    official = read(EVIDENCE / 'official_clean_run.json')
    improvement = read(EVIDENCE / 'improvement_clean_run.json')
    extra = read(EVIDENCE / 'extra_audits_clean_run.json')
    bridge = read(EVIDENCE / 'official_source_equivalence.json')
    improvement_bridge = read(EVIDENCE / 'improvement_source_equivalence.json')
    build = read(HERE / 'build_result.json')
    archive = Path(build['zip'])
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert all(run['status'] == 'passed' and run['returncode'] == 0 and not run['completion_errors']
               for run in (official, improvement, extra))
    assert official['section'] == 'official' and improvement['section'] == 'improvement'
    assert bridge['status'] == 'passed_source_equivalence'
    assert bridge['source_archive_sha256'] == official['archive_sha256']
    assert improvement_bridge['status'] == 'passed_source_equivalence'
    assert improvement_bridge['source_archive_sha256'] == improvement['archive_sha256']
    assert bridge['final_archive_sha256'] == improvement_bridge['final_archive_sha256'] == extra['archive_sha256'] == build['zip_sha256'] == archive_hash
    assert bridge['all_initial_immutable_files_still_match_initial_manifest']
    assert bridge['all_final_immutable_files_match_final_manifest']
    assert bridge['official_dispatch']['official_if_branch_ast_identical']
    assert all(bridge['official_dispatch']['helper_ast_identical'].values())
    assert official['installed_packages'] == improvement['installed_packages'] == extra['installed_packages']
    assert extra['extra_audits_only'] is True
    assert extra['reused_core_evidence']['source_archive_sha256'] == improvement['archive_sha256']
    assert extra['reused_core_evidence']['source_bridge_sha256'] == hashlib.sha256((EVIDENCE / 'improvement_source_equivalence.json').read_bytes()).hexdigest()
    assert Path(improvement['extracted_root']).resolve() == Path(improvement_bridge['initial_extracted_root']).resolve()
    assert improvement_bridge['csv_comparison']['all_passed']
    for item in improvement_bridge['csv_comparison']['checks']:
        assert item['numeric_equal']
        assert extra['reused_core_evidence']['copied_output_files_sha256'][item['file']] == item['candidate_runtime_output_sha256']
    for run in (official, improvement, extra):
        assert run['python_workspace_access_guard_tested']
        assert run['workspace_guard_probe'] == run['child_process_guard_probe'] == 'workspace read denied'
        summary = run['run_summaries']['logs/integrated_run_summary.json']
        assert summary['passed'] and not summary['quick'] and not summary['verify_only']
        assert all(step['returncode'] == 0 for step in summary['steps'])
    improvement_steps = improvement['run_summaries']['logs/integrated_run_summary.json']['steps']
    assert [step['name'] for step in improvement_steps] == ['improvement', 'metrics', 'replay', 'reference', 'independent', 'freeze', 'tests']
    extra_steps = extra['run_summaries']['logs/integrated_run_summary.json']['steps']
    assert [step['name'] for step in extra_steps] == ['reference', 'strong_baselines', 'normal_sensitivity', 'normal_aggregation', 'tests']
    original_summary = official['run_summaries']['logs/run_summary.json']
    assert len(original_summary['steps']) == 26 and all(row['ok'] for row in original_summary['checks'])
    original_root = Path(official['extracted_root'])
    final_root = Path(extra['extracted_root'])
    study_outputs = final_root / 'yejun/analysis/press_improvement/outputs'
    metadata = read(original_root / 'code/press/tvt/outputs/tvt_scores_meta.json')
    assert all(metadata[split]['lstm']['cached'] is False for split in ('A', 'B'))
    reference = read(study_outputs / 'reference_comparison.json')
    arithmetic = read(study_outputs / 'independent_implementation_verification.json')
    frozen = read(study_outputs / 'frozen_holdout/manifest.json')
    strong = read(study_outputs / 'strong_baselines/summary.json')
    normal = read(study_outputs / 'normal_sensitivity/summary.json')
    aggregation = read(study_outputs / 'normal_sensitivity/aggregation_verification.json')
    assert strong['passed'] and normal['passed'] and aggregation['passed']
    assert strong['model_selection_unchanged'] == normal['selected_model_unchanged'] == reference['selected']
    assert normal['abnormal_file_read'] is False and normal['independent_failure_validation'] is False
    assert all(row['aggregation_exact'] for row in aggregation['record_aggregation_checks'])
    assert reference['passed'] and reference['csv_checks'] and all(item['passed'] for item in reference['csv_checks'])
    assert arithmetic['passed']
    assert all(all(value == 0 for value in split['changed_alarms_by_alpha'].values()) for split in arithmetic['splits'])
    assert all(all(item['alarms_equal'].values()) for item in frozen['retrospective_export_equivalence'])
    test_log = (final_root / 'logs/integrated_tests.log').read_text(encoding='utf-8')
    matches = re.findall(r'(\d+) passed', test_log)
    assert matches and int(matches[-1]) == 108
    assert not re.search(r'\d+ (?:failed|skipped|xfailed|xpassed|error)', test_log)
    for name in ('verification.json', 'replay_verification.json', 'reference_comparison.json', 'independent_implementation_verification.json'):
        shutil.copyfile(study_outputs / name, EVIDENCE / ('packaged_' + name))
    shutil.copyfile(study_outputs / 'frozen_holdout/manifest.json', EVIDENCE / 'packaged_frozen_holdout_manifest.json')
    for subdir, filename in (('strong_baselines', 'summary.json'), ('normal_sensitivity', 'summary.json'), ('normal_sensitivity', 'aggregation_verification.json')):
        shutil.copyfile(study_outputs / subdir / filename, EVIDENCE / ('packaged_' + subdir + '_' + filename))
    result = dict(status='passed', passed=True, final_archive_name=archive.name,
                  final_archive_sha256=archive_hash, final_archive_bytes=archive.stat().st_size,
                  execution_strategy='Official 26 steps and retained-candidate improvement 7 steps ran in separate fresh extractions using one newly installed virtual environment. Explicit source/data/dispatch bridges link both to the final ZIP; the official module has one removed unused metadata keyword, verified by AST comparison. Final ZIP extra audits ran in a third fresh extraction, reusing only hash-verified core outputs and generating all added audit outputs anew. No single sequential --section all run is claimed.',
                  official_steps=26, official_expected_checks=len(original_summary['checks']),
                  official_all_checks_passed=True, original_lstm_retrained_without_cache=True,
                  improvement_steps=7, final_extra_steps=len(extra_steps), improvement_tests_passed=108,
                  improvement_reference_csv_files=len(reference['csv_checks']),
                  implementation_audit_rows=sum(item['audited_score_rows'] for item in arithmetic['splits']),
                  implementation_max_score_difference=max(item['maximum_absolute_score_difference'] for item in arithmetic['splits']),
                  implementation_alarm_mismatches=0,
                  frozen_equivalence_rows=sum(item['rows'] for item in frozen['retrospective_export_equivalence']),
                  frozen_alarms_identical=True,
                  python=official['interpreter']['version'],
                  official_seconds=official['seconds'], improvement_seconds=improvement['seconds'], extra_audits_seconds=extra['seconds'],
                  strong_baseline_metric_rows=strong['actual_metric_rows'],
                  strong_baseline_injection_rows=strong['injection_condition_model_rows'],
                  normal_sensitivity_record_rows=sum(item['record_scenario_rows'] for item in aggregation['record_aggregation_checks']),
                  extra_audits_reference_comparison=read(EVIDENCE / 'extra_audits_reference_comparison.json'),
                  selected=reference['selected'],
                  independent_failure_validation_completed=False, additional_independent_data_available=False,
                  limitation='All numerical performance checks use previously observed data; A/B overlap and 21 abnormal records are one known event.',
                  evidence=['official_clean_run.json', 'improvement_clean_run.json', 'extra_audits_clean_run.json',
                            'official_source_equivalence.json', 'improvement_source_equivalence.json',
                            'extra_audits_reference_comparison.json'])
    assert result['extra_audits_reference_comparison']['passed']
    assert result['extra_audits_reference_comparison']['final_archive_sha256'] == archive_hash
    assert read(EVIDENCE / 'preserved_sources_and_reports.json')['passed']
    result['report_updated'] = False
    (EVIDENCE / 'clean_run.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
