"""Read-only report inspection; write evidence here and render previews in TEMP."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pymupdf as fitz
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
ROOT = STUDY.parents[2]
sys.path.insert(0, str(STUDY))
from audit_hwpx_pdf import audit, normalize
from build_hwpx_copy import SRC, parse


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    assert not (HERE / 'snapshot.json').exists(), 'Preserve the existing review snapshot.'
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert head.startswith('b26115a'), 'This review targets the last completed b26115a report.'
    files = [SRC, SRC.with_suffix('.hwpx'), SRC.with_suffix('.pdf')]
    package = ROOT / 'yejun/submission/press_integrated_2026-10-08'
    archive = Path(json.loads((package / 'build_result.json').read_text(encoding='utf-8'))['zip'])
    files.append(archive)
    before = {path.relative_to(ROOT).as_posix(): digest(path) for path in files}
    temp = Path(tempfile.mkdtemp(prefix='press_report_audit_b26115a_'))
    save('snapshot.json', dict(commit=head, started_utc=datetime.now(timezone.utc).isoformat(),
                              files_sha256=before, temporary_previews=str(temp),
                              scope='Review only. No manuscript, native report, experiment or package changes.'))
    layout = audit(SRC, SRC.with_suffix('.hwpx'))
    save('layout_check.json', layout)
    cover, chapters = parse(SRC.read_text(encoding='utf-8-sig'))
    paragraphs = [cover['project'], *cover['summary']]
    paragraphs += [block[2] for _, blocks in chapters for block in blocks if block[0] == 'p']
    pages = []
    with fitz.open(SRC.with_suffix('.pdf')) as doc:
        thumbnails = []
        for i, page in enumerate(doc):
            text = page.get_text()
            (temp / f'page_{i+1:02}.txt').write_text(text, encoding='utf-8')
            blocks = [block for block in page.get_text('dict')['blocks'] if block['type'] == 0]
            spans = [span for block in blocks for line in block.get('lines', []) for span in line['spans'] if span['text'].strip()]
            images = page.get_image_info()
            pages.append(dict(page=i+1, characters=len(text), images=len(images),
                              fonts=sorted({(span['font'], round(span['size'], 2)) for span in spans}),
                              content_top=min((span['bbox'][1] for span in spans), default=None),
                              content_bottom=max((span['bbox'][3] for span in spans), default=None),
                              image_boxes=[image['bbox'] for image in images]))
            pix = page.get_pixmap(matrix=fitz.Matrix(0.45, 0.45), alpha=False)
            thumb = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            thumbnails.append(thumb)
        all_text = '\n'.join(page.get_text().replace('일반국민/대학(원)생 부문', '') for page in doc)
        joined = normalize(all_text)
        misses = [{'paragraph': p} for p in paragraphs if normalize(p) not in joined]
        (temp / 'all_pages.txt').write_text(all_text, encoding='utf-8')
        for first in range(0, len(thumbnails), 12):
            group = thumbnails[first:first+12]
            cell_w, cell_h = max(im.width for im in group)+16, max(im.height for im in group)+32
            sheet = Image.new('RGB', (4*cell_w, 3*cell_h), '#b8b8b8')
            draw = ImageDraw.Draw(sheet)
            for local, thumb in enumerate(group):
                x, y = (local%4)*cell_w+8, (local//4)*cell_h+24
                sheet.paste(thumb, (x,y))
                draw.text((x,y-19), str(first+local+1), fill='black')
            sheet.save(temp / f'contact_{first+1:02}_{min(first+12,len(doc)):02}.png')
        save('pdf_content_check.json', dict(pages=pages, paragraphs_checked=len(paragraphs),
                                           exact_normalized_paragraph_misses=misses,
                                           note='Misses may be page-boundary/header artifacts; inspect before claiming omissions.'))
    assert before == {path.relative_to(ROOT).as_posix(): digest(path) for path in files}
    print(json.dumps(dict(pages=len(pages), paragraphs_checked=len(paragraphs),
                          paragraph_misses=len(misses), temporary_previews=str(temp),
                          report_and_zip_unchanged=True), ensure_ascii=False))


if __name__ == '__main__':
    main()
