"""Read-only addendum for the external commit completed during this review."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pymupdf
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
ROOT = STUDY.parents[2]
sys.path.insert(0, str(STUDY))
from audit_hwpx_pdf import normalize
from build_hwpx_copy import SRC, parse

snapshot = json.loads((HERE / 'snapshot.json').read_text(encoding='utf-8'))
target = '7a7e7f307c9c03b7bc643b18a0e4370180f3b5be'
relative = SRC.relative_to(ROOT).as_posix()
committed = subprocess.check_output(['git', 'show', target + ':' + relative], cwd=ROOT)
closing = json.loads((HERE / 'completion_state.json').read_text(encoding='utf-8'))
assert hashlib.sha256(committed).hexdigest() == closing['current_report_and_zip_sha256'][relative]
before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in snapshot['files_sha256']}
cover, chapters = parse(committed.decode('utf-8-sig'))
paragraphs = [cover['project'], *cover['summary']]
paragraphs += [block[2] for _, blocks in chapters for block in blocks if block[0] == 'p']
temp = Path(snapshot['temporary_previews'])
saved_pdf = temp / 'baseline_7a7e7f3.pdf'
pdf_bytes = saved_pdf.read_bytes() if saved_pdf.exists() else SRC.with_suffix('.pdf').read_bytes()
assert hashlib.sha256(pdf_bytes).hexdigest() == closing['current_report_and_zip_sha256'][SRC.with_suffix('.pdf').relative_to(ROOT).as_posix()]
if not saved_pdf.exists():
    saved_pdf.write_bytes(pdf_bytes)
with pymupdf.open(stream=pdf_bytes, filetype='pdf') as doc:
    joined = normalize('\n'.join(page.get_text().replace('일반국민/대학(원)생 부문', '') for page in doc))
    misses = [p for p in paragraphs if normalize(p) not in joined]
    p31 = doc[30]
    drawing_bottom = max(d['rect'].y1 for d in p31.get_drawings())
    visual_pages = [1, 42, 62, 63, 65, 66]
    sheet = Image.new('RGB', (1190, 1263), '#bbbbbb')
    draw = ImageDraw.Draw(sheet)
    for index, number in enumerate(visual_pages):
        page = doc[number-1]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(.5, .5), alpha=False)
        thumb = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        x, y = (index % 3) * 397, (index // 3) * 632 + 22
        sheet.paste(thumb, (x, y))
        draw.text((x, y-20), str(number), fill='black')
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), alpha=False)
        pix.save(temp / f'after_7a7e7f3_page_{number:02}.png')
    sheet.save(temp / 'after_7a7e7f3_contact.png')
    page_count = len(doc)
    margin_mm = (p31.rect.height-drawing_bottom) / 72 * 25.4

after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in snapshot['files_sha256']}
result = dict(
    checked_utc=datetime.now(timezone.utc).isoformat(), original_commit=snapshot['commit'],
    externally_completed_commit=target, scope='Changed paragraphs and rendering delta only; original audit retained.',
    paragraphs_checked=len(paragraphs), paragraph_misses=misses,
    pages=page_count, page_31_table_bottom_margin_mm=margin_mm,
    finding_status={'R01': 'remains', 'R02': 'resolved_by_external_commit', 'R03': 'remains',
                    'R04': 'remains', 'R05': 'remains', 'S01': 'remains', 'S02': 'remains'},
    changed_paragraphs=[21, 458, 678, 679, 683, 684, 688, 704, 714, 715],
    manual_delta_assessment=[
        'CD is now described as replacing V2 with sine-waveform and current-difference prediction error; the incorrect only-window/weight claim is removed.',
        'The extra-audits flag, legacy environment file, replay coverage and original-versus-packaged protocol distinction are clearer.',
        'The run commands still invoke bare python after installing into .venv.',
        'Baseline-comparison wording, reference 30 placement, the page-31 table margin and submission placeholders remain.'
    ],
    committed_manuscript_sha256=hashlib.sha256(committed).hexdigest(),
    frozen_pdf_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
    later_uncommitted_changes_excluded=True, live_files_sha256=after,
    live_files_changed_during_check=before != after,
    reviewed_pages_contact=str(temp / 'after_7a7e7f3_contact.png'),
    no_report_code_zip_edits_by_this_review=True)
(HERE / 'concurrent_delta_review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(dict(target=target, pages=page_count, paragraph_misses=len(misses),
                      page31_margin_mm=margin_mm, contact=result['reviewed_pages_contact']), ensure_ascii=False))
