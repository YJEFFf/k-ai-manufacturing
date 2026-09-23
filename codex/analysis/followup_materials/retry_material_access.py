"""Bounded read-only material retry; user files are never modified.

Each copy runs in its own process with a 10-second deadline. Subsequent PDF
reads operate only on a non-iCloud /tmp copy. Large archive retries are skipped
if the cache budget would be exceeded. No report-template access.
"""
from pathlib import Path
import json,subprocess,unicodedata,datetime,shutil

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
ANALYSIS=OUT.parent
CACHE=Path('/tmp/kamp-followup-cache');CACHE.mkdir(exist_ok=True)
textdir=OUT/'pdf_text';textdir.mkdir(exist_ok=True)
mapping=json.loads((ANALYSIS/'reselection/download_source_mapping.json').read_text())
pdfs=json.loads((ANALYSIS/'reselection/pdf_available_inventory.json').read_text())
archive_checks=json.loads((ANALYSIS/'reselection/archive_checks.json').read_text())
read_pdfs={unicodedata.normalize('NFC',r['source']) for r in pdfs}
good_archives={unicodedata.normalize('NFC',r['path']) for r in archive_checks if r.get('status')=='zip_crc_all_pass'}
priority=[4,48,27,51,52,50,2,18,9,11,23,43,45]
def seq(rec):
    ids=rec.get('seq_candidates',[])
    return int(ids[0]) if ids else None
def order(rec):
    sid=seq(rec)
    return (priority.index(sid) if sid in priority else 999,rec['path'])
records=[];used=sum(p.stat().st_size for p in CACHE.glob('*') if p.is_file())
for m in sorted(mapping,key=order):
    p=ROOT/m['path'];ext=p.suffix.lower();norm=unicodedata.normalize('NFC',m['path'])
    if ext not in ['.pdf','.zip']:continue
    if '양식' in p.name:continue
    prior=(norm in read_pdfs) if ext=='.pdf' else (norm in good_archives)
    if prior and seq(m) not in [4,48,27,50,51,52]:continue
    try:st=p.stat()
    except FileNotFoundError:
        r={'source':m['path'],'id':seq(m),'suffix':ext,'status':'not_at_previous_path','checked_at':datetime.datetime.now().isoformat(timespec='seconds')}
        records.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
        (OUT/'material_access_retry.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
        continue
    r={'source':m['path'],'id':seq(m),'suffix':ext,'bytes':st.st_size,'dataless_before':bool(st.st_flags&0x40000000),'previous_content_checked':prior,'checked_at':datetime.datetime.now().isoformat(timespec='seconds')}
    records.append(r)
    target=CACHE/p.name;partial=target.with_name(target.name+'.part')
    if st.st_size==0:
        r['status']='zero_bytes';print(json.dumps(r,ensure_ascii=False),flush=True)
    elif target.exists() and target.stat().st_size==st.st_size:
        r['status']='cached';r['cache']=str(target)
    elif used+st.st_size>650_000_000 or shutil.disk_usage(CACHE).free-st.st_size<1_500_000_000:
        r['status']='deferred_cache_budget';print(json.dumps(r,ensure_ascii=False),flush=True)
    else:
        try:
            proc=subprocess.run(['/bin/cp',str(p),str(partial)],capture_output=True,timeout=10)
            if proc.returncode:raise RuntimeError(proc.stderr.decode(errors='replace')[:300])
            partial.rename(target);used+=st.st_size;r['status']='copied';r['cache']=str(target)
        except subprocess.TimeoutExpired:
            r['status']='copy_timeout_10s'
        except Exception as e:r['status']='copy_error';r['error']=str(e)
        if partial.exists():partial.unlink()
        print(json.dumps(r,ensure_ascii=False),flush=True)
    if 'cache' in r and ext=='.pdf':
        txt=textdir/(p.stem+'.txt')
        try:
            proc=subprocess.run(['pdftotext','-layout',str(target),str(txt)],capture_output=True,timeout=10)
            if proc.returncode:raise RuntimeError(proc.stderr.decode(errors='replace')[:200])
            text=txt.read_text();r['pdf_text']=str(txt.relative_to(ROOT));r['pages']=len(text.split('\f'))-1;r['chars']=len(text)
        except Exception as e:r['pdf_text_error']=str(e)
    (OUT/'material_access_retry.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print('DONE',len(records),flush=True)
