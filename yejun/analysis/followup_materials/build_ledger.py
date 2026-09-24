"""Current guide coverage ledger from stat and materialized texts; no originals changed."""
from pathlib import Path
import json,re,unicodedata,datetime,zipfile
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
catalog=json.loads(Path('/tmp/kamp_free_catalog.json').read_text())['entries']
source=next(p for p in ROOT.iterdir() if unicodedata.normalize('NFC',p.name)=='데이터셋')
old=OUT.parent/'reselection/pdf_text';new=OUT/'pdf_text'
def norm(s):return re.sub(r'[\s_,.\-]+','',unicodedata.normalize('NFC',s)).lower()
def identify(name):
 m=re.match(r'^(\d{2})\.',name)
 if m:return int(m.group(1))
 n=norm(name.removeprefix('Guidebook_').removesuffix('.pdf').removesuffix('.txt'))
 cand=[e['seq'] for e in catalog if norm(e['title'])==n]
 return cand[0] if len(cand)==1 else None
source_files={identify(p.name):p for p in source.glob('*.pdf')}
prior={identify(p.name):p for p in old.glob('*.txt') if p.stat().st_size}
fresh={identify(p.name):p for p in new.glob('*.txt') if p.stat().st_size}
reviewed={2:[6,7,8,9,17,18,19],9:[9,10,29,30,33,35,36,42],11:[9,10,16,19,20,21,22,24,27,28,29],18:[10,11,12,13,32,37,38,39],43:[10,11,12,13,32,33,34,35,42,43,44],45:[10,11,23,24,31,32,41,42,43,49],48:[8,9,11,12,28,31,32,33,34,35,36,37,38,39,40,41],50:[9,10,14,28,29,30,33,34,35,36,37,38,39],51:[8,9,10,12,14,23,24,28,29,30,31,32,33,34,35,36,37,38,39],52:[9,10,30,32,34,35,36,38,39,41,42,44,47],59:[9,10,11,12,32,33,34,35,36,37,43]}
rows=[]
for e in catalog:
 ident=e['seq']
 if ident==5:continue # Earlier welding material, outside the 49 additional-guide inventory.
 p=source_files.get(ident);t=fresh.get(ident) or prior.get(ident)
 r={'id':ident,'title':e['title'],'source':str(p.relative_to(ROOT)) if p else None,'source_current_location_known':p is not None,'source_bytes':p.stat().st_size if p else None,'text_extracted':t is not None,'text':str(t.relative_to(ROOT)) if t else None,'prior_text_exists':ident in prior,'followup_text_exists':ident in fresh}
 if ident in reviewed:r.update(review_status='decisive_label_validation_sections_reviewed_in_followup',reviewed_pdf_pages=reviewed[ident])
 elif ident==4:r.update(review_status='completed_injection_raw_guide_mapping_and_forward_audit',followup_report='yejun/analysis/followup_materials/injection_recovered/injection_recovered_verdict.md')
 elif ident==27:r['review_status']='energy_agent_reported_guide_review_complete'
 elif t:r['review_status']='text_available_no_new_decisive_review_claim_by_this_agent'
 else:r['review_status']='body_unavailable_or_current_location_unknown'
 rows.append(r)
summary={'checked_at':datetime.datetime.now().isoformat(timespec='seconds'),'scope':'49 additional guides; earlier ID5 welding guide is outside this count','catalog_guides_in_scope':49,'actual_source_pdfs_currently_located':len(source_files),'unique_texts_extracted':sum(r['text_extracted'] for r in rows),'no_body_ids':[r['id'] for r in rows if not r['text_extracted']],'followup_decisive_review_ids':sorted(reviewed),'delegated_review_ids':[4,27],'important':'Text extraction is not a claim that every guide page and every image was read; page lists identify decisive audited evidence. Missing previous path is not proof of permanent absence.'}
(OUT/'guide_ledger.json').write_text(json.dumps({'summary':summary,'guides':rows},ensure_ascii=False,indent=2))
lines=['# 추가 가이드북 현재 확보·검토 상태', '',f"확인 시점: {summary['checked_at']}",'',f"기존 용접기 ID5를 제외한 추가자료 49종 중 **{summary['unique_texts_extracted']}종의 본문 텍스트를 확보**했다. 현재 원래 데이터셋 폴더에서 경로를 확인한 PDF는 {summary['actual_source_pdfs_currently_located']}개다. 본문 추출과 핵심내용 검토는 아래에서 분리했다.",'','| ID | 자료 | 본문 추출 | 이번 핵심 검토 |','|---|---|---|---|']
for r in rows:
 review='라벨·검증 근거 검토' if r['id'] in reviewed else '원본·가이드 대조 및 미래 날짜 검증 완료' if r['id']==4 else '에너지 담당 검토 완료 보고' if r['id']==27 else '이번 담당 재검토 미주장' if r['text_extracted'] else '본문 미확보'
 lines.append(f"| {r['id']} | {r['title']} | {'확보' if r['text_extracted'] else '현재 경로 미확인' if not r['source_current_location_known'] else '접근 대기'} | {review} |")
lines+=['','본문 미확보: **6 머신비전, 23 장비이상 조기탐지**는 마지막 10초 재시도에서도 cloud 읽기가 완료되지 않았다. **12 X-ray 가이드**는 과거 기록의 경로에서 현재 파일을 찾지 못했다. 다른 위치나 이전 사본의 존재까지 부정하는 뜻은 아니다. **37 열처리 공급망최적화는 마지막 재시도에서 복구 성공**하여 본문 확보 수에 포함했다.','', f"이번 담당이 핵심 근거를 직접 검토한 가이드의 PDF 페이지는 JSON에 기록했다. 본문 추출 {summary['unique_texts_extracted']}종을 전 페이지 정독으로 표현하면 안 된다. 기존 보고서 검토 여부는 이 표에서 새로 단정하지 않는다.",'', '원본 파일이나 기존 완료 보고서는 변경하지 않았다. 데이터 압축파일은 별도 원표 감사 결과와 함께 확인해야 하며, PDF 접근 성공은 원본 데이터 검증 성공을 뜻하지 않는다.']
(OUT/'guide_ledger.md').write_text('\n'.join(lines)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
