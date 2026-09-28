"""최종 사본의 evidence 표·그림을 시스템 임시 폴더에서 재생성·대조한다.

원본 작업트리는 읽기만 한다. 자기 검수 JSON·로그만 round4에 쓴다.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
YEJUN=HERE.parents[3]
EVID=YEJUN/'analysis/press_evidence'


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    start=time.monotonic()
    scratch=Path(tempfile.mkdtemp(prefix='judge01_r4_evidence_'))
    dest=scratch/'yejun'
    directories=['press_guard','press_submission','analysis/press_evidence','analysis/press_supplement','analysis/press_supervised']
    for rel in directories:
        shutil.copytree(YEJUN/rel,dest/rel,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','.DS_Store'))
    shutil.copy2(YEJUN/'analysis/package_contract.py',dest/'analysis/package_contract.py')
    contract=json.loads((EVID/'contract.json').read_text())
    files=contract['outputs']+list(contract['manifests'])
    original={rel:sha(EVID/rel) for rel in files}
    env=os.environ.copy(); env.update(OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',MPLBACKEND='Agg')
    steps=[]
    def run(name,args):
        began=time.monotonic()
        p=subprocess.run([sys.executable]+args,cwd=dest,env=env,text=True,capture_output=True)
        (scratch/(name+'.log')).write_text(p.stdout+p.stderr)
        steps.append(dict(name=name,exit_code=p.returncode,elapsed_s=time.monotonic()-began,log=str(scratch/(name+'.log'))))
        print(name,'exit',p.returncode,round(time.monotonic()-began,2),'seconds',flush=True)
        if p.returncode: print((p.stdout+p.stderr)[-6000:],flush=True)
        return p.returncode
    run('initial_contract',['analysis/package_contract.py','--package','analysis/press_evidence'])
    run('build_tables',['analysis/press_evidence/build_tables.py'])
    run('build_diagnostics',['analysis/press_evidence/build_diagnostics.py'])
    run('final_contract',['analysis/package_contract.py','--package','analysis/press_evidence'])
    run('targeted_tests',['-m','pytest','-q','-p','no:cacheprovider','analysis/press_evidence/test_contract.py','analysis/press_evidence/test_diagnostics.py'])
    identical=[]; changed=[]
    for rel in contract['outputs']:
        (identical if sha(dest/'analysis/press_evidence'/rel)==original[rel] else changed).append(rel)
    manifest_changes={}
    def flatten(obj,prefix=''):
        result={}
        for k,v in obj.items():
            if isinstance(v,dict): result.update(flatten(v,prefix+k+'.'))
            else: result[prefix+k]=v
        return result
    for rel in contract['manifests']:
        a=flatten(json.loads((EVID/rel).read_text())); b=flatten(json.loads((dest/'analysis/press_evidence'/rel).read_text()))
        manifest_changes[rel]=[k for k in sorted(set(a)|set(b)) if a.get(k)!=b.get(k)]
    source_mutated=[rel for rel,digest in original.items() if sha(EVID/rel)!=digest]
    result=dict(scratch=str(scratch),steps=steps,identical=identical,changed=changed,manifest_changed_keys=manifest_changes,
        source_changed_during_rerun=source_mutated,bytecode_directories=[str(p) for p in dest.rglob('__pycache__')],elapsed_s=time.monotonic()-start)
    (HERE/'judge01_rerun.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print('identical',len(identical),'changed',changed,'manifest changes',manifest_changes,'source changed',source_mutated,flush=True)
    raise SystemExit(bool(changed or source_mutated or any(x['exit_code'] for x in steps)))


if __name__=='__main__': main()
