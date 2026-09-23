"""Inspect already CRC-verified archive hashes without re-reading cloud files."""
from pathlib import Path
from collections import Counter, defaultdict
import json
from sklearn.model_selection import train_test_split

root=Path(__file__).resolve().parent
inventory=json.loads((root/'archive_checks.json').read_text())
record=next(x for x in inventory if '761196' in x['path'])
assert record['status']=='zip_crc_all_pass'
members=[m for m in record['members'] if m['name'].endswith('.wav')]
groups=defaultdict(list)
for m in members:
    assert m['crc_checked'] and m['bytes_read']==m['bytes']
    groups[m['sha256']].append(m['name'])
labels=[int('FAN_sound_error/' in m['name']) for m in members]
train,test=train_test_split(list(range(len(members))),test_size=.2,random_state=42,stratify=labels)
train_hashes={members[i]['sha256'] for i in train}
result={
    'source_archive':record['path'],
    'file_counts':dict(Counter('error' if y else 'normal' for y in labels)),
    'unique_byte_hashes':len(groups),
    'normal_unique_byte_hashes':len({m['sha256'] for m,y in zip(members,labels) if not y}),
    'error_unique_byte_hashes':len({m['sha256'] for m,y in zip(members,labels) if y}),
    'duplicate_hash_groups':{h:names for h,names in groups.items() if len(names)>1},
    'illustrative_random_80_20_split':{
        'random_state':42,'stratified':True,
        'train_files':len(train),'test_files':len(test),
        'test_files_whose_exact_bytes_are_also_in_train':sum(members[i]['sha256'] in train_hashes for i in test),
        'test_normal_files':sum(not labels[i] for i in test),
        'test_error_files':sum(labels[i] for i in test),
        'note':'This is a leakage check, not a measured predictive score.'
    }
}
(root/'maintenance_audio_hash_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='duplicate_hash_groups'},ensure_ascii=False,indent=2))
