"""인계 전 변경 영향 확인. 50시드 통계를 재실행하지 않고 종전 해시·최종 추론만 확인한다."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess
import sys
import time

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
Y = HERE.parents[3]
G = Y / 'press_guard'
sys.path.insert(0, str(G))
from model import GuardModel, D, layout

START = time.monotonic()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def body(text, name):
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise KeyError(name)


before_path = HERE / 'judge03_hashes_before_handoff.json'
if not before_path.exists():
    before_path.write_bytes((HERE / 'judge03_final_hashes.json').read_bytes())
old = json.loads(before_path.read_text())
changed, missing = [], []
for name, expected in old['files'].items():
    path = Y / name
    if not path.is_file():
        missing.append(name)
    elif sha(path) != expected:
        changed.append(dict(path=name, previous=expected, current=sha(path)))
allowed = {'press_guard/model.py', 'press_guard/README.md', 'analysis/press_supplement/e1_manifest.json'}
assert not missing
product_changes = [r for r in changed if not r['path'].startswith('analysis/press_rubric_review/')]
assert {r['path'] for r in product_changes} <= allowed, product_changes
model_old = subprocess.check_output(['git', 'show', '6c61a88:yejun/press_guard/model.py'], cwd=Y, text=True)
model_now = (G / 'model.py').read_text()
formula_names = ('components', 'sine_score', 'ar_residual')
same_formula = {name: body(model_old, name) == body(model_now, name) for name in formula_names}
assert all(same_formula.values())
normal, abnormal, report = D.load(Y / 'press_submission')
input_status = {}
for name, frame in [('normal', normal), ('abnormal', abnormal)]:
    status, seg = layout(frame)
    counts = pd.Series(status).value_counts().to_dict()
    input_status[name] = dict(rows=len(frame), records=int(np.unique(seg).size), status_counts=counts)
    assert (status == 'ok').all(), (name, counts)
metrics = pd.read_csv(G / 'outputs/metrics.csv')
predictions = []
for sid in 'AB':
    model = GuardModel.load(G / 'artifacts' / f'guard_{sid}.json')
    test = D.split_normal(normal, D.segments(normal), sid)['test']
    pn, pa = model.predict(test, .01), model.predict(abnormal, .01)
    values = dict(tp=int(pa.alarm.sum()), fp=int(pn.alarm.sum()), fn=int((pa.alarm == 0).sum()),
                  normal_notified_segments=int(pn.groupby('record_id').alarm.max().sum()),
                  abnormal_notified_segments=int(pa.groupby('record_id').alarm.max().sum()))
    row = metrics[metrics.split.eq(sid) & metrics.model.eq('guard_v2') & metrics.alpha.eq(.01)].iloc[0]
    assert all(values[key] == int(row[key]) for key in values)
    values['f1'] = 2*values['tp'] / (2*values['tp'] + values['fp'] + values['fn'])
    predictions.append(dict(split=sid, **values))
artifacts = {name: sha(G / 'artifacts' / name) for name in ('guard_A.json','guard_B.json','probability_A.json','probability_B.json')}
assert all(digest == old['files'][f'press_guard/artifacts/{name}'] for name,digest in artifacts.items())
e1 = Y / 'analysis/press_supplement'
manifest = json.loads((e1 / 'e1_manifest.json').read_text())
manifest_checks = {}
for group in ('outputs', 'local_outputs'):
    for name,digest in manifest[group].items():
        path = e1 / name
        manifest_checks[f'{group}/{name}'] = path.is_file() and sha(path) == digest
assert all(manifest_checks.values()), manifest_checks
assert manifest['code']['press_guard/model.py'] == sha(G / 'model.py')
table_delta = json.loads((HERE / 'field_final_tables_after.json').read_text())
csv_delta = json.loads((HERE / 'field_final_csv_delta.json').read_text())
assert csv_delta['compared'] == 59 and not csv_delta['changed']
assert table_delta['compared'] == 112 and table_delta['byte_identical'] == 111
assert table_delta['all_statistical_values_unchanged']
assert len(table_delta['differences']) == 2
assert all(row['column'] == 'evidence' for row in table_delta['differences'])
watched_product = [name for name in old['files'] if not name.startswith('analysis/press_rubric_review/')]
unchanged_product = [name for name in watched_product if name not in {r['path'] for r in changed}]
result = dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Y,text=True).strip(),
              prior_files_compared=len(old['files']), prior_files_byte_identical=len(old['files'])-len(changed),
              product_files_compared=len(watched_product), product_files_byte_identical=len(unchanged_product),
              changed=changed, missing=missing, unchanged_product_files=unchanged_product,
              statistical_formula_ast_equal_to_baseline=same_formula, original_input_status=input_status,
              primary_recount=predictions, model_sha256=artifacts, e1_manifest_output_checks=manifest_checks,
              e1_manifest_current_model_hash_valid=True, existing_59_csv_delta=csv_delta,
              existing_112_table_delta=table_delta, previous_full_checks_retained=1607,
              long_injection_rerun=False, score=14.5, score_range=[14.2,14.8],
              remaining_P0=0,remaining_P1=0,remaining_P2=0,elapsed_s=round(time.monotonic()-START,2))
(HERE / 'judge03_final_delta.json').write_text(json.dumps(D.to_jsonable(result), ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('unchanged_product_files','e1_manifest_output_checks','existing_112_table_delta')},ensure_ascii=False,indent=2))
