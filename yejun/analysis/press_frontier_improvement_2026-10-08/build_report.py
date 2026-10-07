#!/usr/bin/env python3
"""Render the separate Korean report Markdown as standalone HTML and A4 PDF.

Requires markdown, beautifulsoup4, PyMuPDF and an installed Chromium browser.
Does not modify the source Markdown, original report, or archive directory.
Example: /opt/anaconda3/bin/python yejun/analysis/press_frontier_improvement_2026-10-08/build_report.py
The PDF is a readable review layout, not the contest's HWPX template.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import html
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

import fitz
import markdown
from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DEFAULT_SOURCE = REPO / "yejun/결과보고서_북적북적_경쟁모델융합_개선안_2026-10-08/결과보고서_북적북적_개선본.md"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def original_figure_mapping() -> dict[int, str]:
    """Read the existing FIGS literal without importing/running the HWPX builder."""
    tree = ast.parse((REPO / "claude/report/build_hwpx.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FIGS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("Original FIGS mapping was not found")


def chrome_path(argument: str | None) -> str:
    candidates = [argument, os.environ.get("REPORT_CHROME"),
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                  "/Applications/Chromium.app/Contents/MacOS/Chromium",
                  os.path.join(os.environ.get("PROGRAMFILES", ""), "Google/Chrome/Application/chrome.exe"),
                  os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google/Chrome/Application/chrome.exe"),
                  shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("No Chromium browser found; pass --chrome or use --html-only")


def prepare_body(source: Path) -> tuple[str, dict]:
    text = source.read_text(encoding="utf-8-sig")
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    # A few HWP-style standalone indented bullet notes are not fenced code.
    text = re.sub(r"(?m)^ {4,}([*-] )", r"  \1", text)
    mapping = original_figure_mapping()
    figures = []

    def figure(match: re.Match) -> str:
        number, caption = int(match.group(1)), match.group(2)
        if number not in mapping:
            raise ValueError(f"Figure {number} has no FIGS mapping; use a Markdown image for new figures")
        path = source.parent / "figures" / mapping[number]
        if not path.is_file():
            raise FileNotFoundError(path)
        figures.append({"number": number, "file": str(path.relative_to(source.parent)), "sha256": sha256(path)})
        return (f'\n<figure id="figure-{number}"><img src="{data_uri(path)}" '
                f'alt="그림 {number}: {html.escape(caption, quote=True)}">'
                f'<figcaption>그림 {number}. {html.escape(caption)}</figcaption></figure>\n')

    text = re.sub(r"(?m)^\[그림 (\d+): (.*)\]\s*$", figure, text)
    rendered = markdown.markdown(text, extensions=["extra", "sane_lists", "nl2br"], tab_length=2)
    soup = BeautifulSoup(rendered, "html.parser")
    headings = []
    for index, heading in enumerate(soup.find_all(["h1", "h2", "h3"]), start=1):
        heading["id"] = f"section-{index}"
        label = heading.get_text(" ", strip=True)
        if heading.name == "h1" and re.search(r"제\d+장", label):
            heading["class"] = ["chapter"]
            headings.append({"id": heading["id"], "label": label})
        elif heading.name == "h1" and label == "표지":
            heading["class"] = ["cover-heading"]
    tables = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        ncols = max((len(row.find_all(["td", "th"], recursive=False)) for row in rows), default=0)
        if not ncols:
            continue
        table["class"] = ["report-table", f"cols-{ncols}"]
        weights = []
        for col in range(ncols):
            lengths = [len(cells[col].get_text(" ", strip=True)) for row in rows
                       if len(cells := row.find_all(["td", "th"], recursive=False)) > col]
            head = lengths[0] if lengths else 1
            body_mean = sum(lengths[1:]) / max(1, len(lengths) - 1)
            weights.append(math.sqrt(max(6, head, body_mean)))
        # Keep every column usable, while giving explanatory prose more space.
        total = sum(weights)
        widths = [0.45 / ncols + 0.55 * weight / total for weight in weights]
        colgroup = soup.new_tag("colgroup")
        for width in widths:
            col = soup.new_tag("col")
            col["style"] = f"width:{width * 100:.4f}%"
            colgroup.append(col)
        table.insert(0, colgroup)
        tables.append({"columns": ncols, "rows": len(rows)})
    # Embed any new Markdown images, so the HTML can be moved independently.
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith("data:"):
            continue
        if re.match(r"^[a-z]+://", src):
            raise ValueError(f"Remote images are not allowed in the standalone report: {src}")
        path = (source.parent / src).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        img["src"] = data_uri(path)
        figures.append({"number": None, "file": str(path), "sha256": sha256(path)})
    return str(soup), {"chapters": headings, "tables": tables, "figures": figures}


def build_html(source: Path) -> tuple[str, dict]:
    body, metadata = prepare_body(source)
    fonts = source.parent / "assets"
    regular, bold = fonts / "Pretendard-Regular.otf", fonts / "Pretendard-Bold.otf"
    title = source.stem.replace("_", " ")
    font_css = "\n".join(
        f'@font-face{{font-family:ReportKR;src:url("{data_uri(path)}") format("opentype");font-weight:{weight};font-style:normal;font-display:block;}}'
        for path, weight in ((regular, 400), (bold, 700)) if path.is_file())
    navigation = "".join(f'<a href="#{h["id"]}">{html.escape(h["label"])}</a>' for h in metadata["chapters"])
    css = """
    :root{color-scheme:light;--ink:#172637;--muted:#516478;--line:#c4cfd9;--accent:#205274;}
    *{box-sizing:border-box}html{font-family:ReportKR,"Malgun Gothic","Apple SD Gothic Neo","Noto Sans CJK KR",sans-serif;color:var(--ink);background:#edf1f5;}
    body{max-width:210mm;margin:24px auto;padding:17mm 15mm;background:white;font-size:10.8pt;line-height:1.64;}
    .edition{font-size:9pt;color:var(--muted);border-bottom:2px solid var(--accent);padding:0 0 4mm;margin-bottom:6mm;}
    .document-title{font-size:18pt;line-height:1.45;margin:0 0 5mm;font-weight:700;}
    nav{margin:8mm 0;padding:5mm;background:#f1f5f8;}nav a{display:block;font-size:10pt;margin:1.5mm 0;}
    h1{font-size:17pt;line-height:1.45;margin:12mm 0 6mm;color:#173d58;}
    h2{font-size:12.5pt;line-height:1.5;margin:7mm 0 3mm;}h3{font-size:11.5pt;margin:5mm 0 2.5mm;}
    h1,h2,h3{break-after:avoid-page;page-break-after:avoid;}
    .cover-heading{font-size:12pt;color:var(--muted);margin:0 0 3mm;}
    p{margin:2mm 0 3mm;orphans:3;widows:3;}ul,ol{padding-left:5mm;margin:2mm 0 4mm;}
    li{padding-left:0.5mm;margin-bottom:2.1mm;orphans:3;widows:3;}li>p{margin:1mm 0;}
    a{color:#164e77;text-decoration:none;overflow-wrap:anywhere;}
    code{font-family:ReportKR,sans-serif;font-size:.91em;background:#f0f3f5;padding:0 .15em;overflow-wrap:anywhere;}
    pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:3mm;background:#f2f5f7;font-size:9pt;line-height:1.45;}
    pre code{padding:0;background:none;}strong{font-weight:700;}
    blockquote{margin:4mm 0;border-left:3px solid #6d8da8;padding:1mm 4mm;color:#374e61;background:#f5f8fa;}
    table{border-collapse:collapse;width:100%;table-layout:fixed;margin:4mm 0 5mm;font-size:8.6pt;line-height:1.42;}
    thead{display:table-header-group;}tfoot{display:table-footer-group;}
    th,td{border:0.55pt solid var(--line);padding:1.7mm 1.55mm;vertical-align:top;word-break:normal;overflow-wrap:anywhere;}
    th{background:#eaf0f5;font-weight:700;text-align:left!important;}td{text-align:left!important;}
    tr{break-inside:avoid-page;page-break-inside:avoid;}
    .cols-7,.cols-8,.cols-9{font-size:7.9pt;line-height:1.4;}
    .cols-7 th,.cols-7 td,.cols-8 th,.cols-8 td,.cols-9 th,.cols-9 td{padding:1.4mm 1.1mm;}
    figure{margin:5mm 0 6mm;break-inside:avoid-page;page-break-inside:avoid;}
    img{display:block;max-width:100%;height:auto;margin:0 auto;}
    figure img{width:100%;max-height:165mm;object-fit:contain;}
    figcaption{margin-top:2mm;font-size:9pt;line-height:1.5;color:#40576b;text-align:left;}
    hr{border:0;border-top:1px solid var(--line);margin:7mm 0;}
    @page{size:A4;margin:16mm 14mm 18mm;
      @bottom-left{content:"북적북적 · 결과보고서 개선본";font-family:ReportKR,sans-serif;font-size:8pt;color:#647588;}
      @bottom-right{content:counter(page) " / " counter(pages);font-family:ReportKR,sans-serif;font-size:8pt;color:#647588;}}
    @media print{html,body{background:white;}body{max-width:none;margin:0;padding:0;font-size:10.8pt;}
      nav{display:none;}.chapter{break-before:page;page-break-before:always;}a{color:inherit;}table{margin-top:3mm;}}
    @media(max-width:720px){body{padding:6vw;margin:0;font-size:11pt;}table{font-size:8pt;}h1{font-size:16pt;}}
    """
    document = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="generator" content="Local report renderer; Chromium PDF">
<style>{font_css}\n{css}</style></head><body>
<div class="edition">검토용 복사본 · 2026-10-08 · 원본 보고서와 별도 보관</div>
<div class="document-title">{html.escape(title)}</div>
<nav aria-label="목차">{navigation}</nav><main>{body}</main>
</body></html>"""
    metadata["fonts"] = [{"file": p.name, "sha256": sha256(p)} for p in (regular, bold) if p.is_file()]
    return document, metadata


def inspect_pdf(pdf: Path, metadata: dict, previews: Path) -> dict:
    doc = fitz.open(pdf)
    texts = [page.get_text() for page in doc]
    alltext = re.sub(r"\s+", "", "\n".join(texts))
    chapter_pages = {}
    for heading in metadata["chapters"]:
        match = re.search(r"제\d+장", heading["label"])
        if match:
            needle = match.group()
            pages = [i + 1 for i, t in enumerate(texts) if needle in re.sub(r"\s+", "", t)]
            if not pages:
                raise AssertionError(f"Missing chapter in PDF: {heading['label']}")
            chapter_pages[needle] = pages[0]
    missing_captions = [f["number"] for f in metadata["figures"]
                        if f["number"] is not None and f"그림{f['number']}." not in alltext]
    if missing_captions:
        raise AssertionError(f"Figure captions missing from PDF: {missing_captions}")
    out_of_page = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    rect = fitz.Rect(span["bbox"])
                    if span["text"].strip() and (rect.x0 < -1 or rect.x1 > page.rect.width + 1 or rect.y0 < -1 or rect.y1 > page.rect.height + 1):
                        out_of_page.append({"page": page.number + 1, "text": span["text"][:80], "bbox": list(rect)})
    if out_of_page:
        raise AssertionError(f"Text outside page bounds: {out_of_page[:5]}")
    previews.mkdir(parents=True, exist_ok=True)
    # The first page, each chapter beginning, and selected dense / figure pages.
    selected = {0, len(doc) - 1} | {p - 1 for p in chapter_pages.values()}
    for needle in ("진동 단독 주입 탐지율", "그림 8.", "그림 12.", "고장 모드"):
        found = next((i for i, t in enumerate(texts) if needle.replace(" ", "") in re.sub(r"\s+", "", t)), None)
        if found is not None:
            selected.add(found)
    for pageno in sorted(selected):
        doc[pageno].get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False).save(previews / f"page_{pageno + 1:03d}.png")
    # Contact sheet is a viewing aid; no alteration of report figures occurs.
    from PIL import Image, ImageDraw
    thumbs = []
    for pageno in sorted(selected):
        im = Image.open(previews / f"page_{pageno + 1:03d}.png").convert("RGB")
        im.thumbnail((300, 430))
        cell = Image.new("RGB", (320, 466), "#e7ecf1")
        cell.paste(im, ((320 - im.width) // 2, 24))
        ImageDraw.Draw(cell).text((12, 6), f"Page {pageno + 1}", fill="#152535")
        thumbs.append(cell)
    cols = 3
    sheet = Image.new("RGB", (cols * 320, math.ceil(len(thumbs) / cols) * 466), "white")
    for i, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((i % cols) * 320, (i // cols) * 466))
    sheet.save(previews / "contact_sheet.png")
    return {"pages": len(doc), "chapter_pages": chapter_pages,
            "captions_verified": len([f for f in metadata["figures"] if f["number"] is not None]),
            "page_image_instances": sum(len(page.get_images()) for page in doc),
            "out_of_page_text_spans": len(out_of_page),
            "replacement_characters": alltext.count("\ufffd"),
            "preview_pages": [p + 1 for p in sorted(selected)], "extracted_text_characters": len(alltext)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--chrome")
    parser.add_argument("--html-only", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    output = (args.output_dir or source.parent).resolve()
    allowed_root = (REPO / "yejun").resolve()
    if not output.is_relative_to(allowed_root) or "원본보관" in output.parts:
        raise ValueError("Output must be under yejun/ and outside 원본보관")
    output.mkdir(parents=True, exist_ok=True)
    before = sha256(source)
    document, metadata = build_html(source)
    html_path = output / f"{source.stem}.html"
    pdf_path = output / f"{source.stem}.pdf"
    html_path.write_text(document, encoding="utf-8")
    metadata.update(source=str(source.relative_to(REPO)), source_sha256=before,
                    created_utc=datetime.now(timezone.utc).isoformat(), html_file=html_path.name,
                    html_sha256=sha256(html_path), layout="A4 review copy; not original HWPX form")
    if not args.html_only:
        browser = chrome_path(args.chrome)
        with tempfile.TemporaryDirectory(prefix="press-report-chrome-") as profile:
            command = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                       "--disable-extensions", "--disable-background-networking", "--no-pdf-header-footer",
                       "--allow-file-access-from-files", "--run-all-compositor-stages-before-draw",
                       "--virtual-time-budget=4000", f"--user-data-dir={profile}",
                       f"--print-to-pdf={pdf_path}", html_path.as_uri()]
            process = subprocess.run(command, capture_output=True, text=True, timeout=180)
            if process.returncode or not pdf_path.is_file():
                raise RuntimeError(f"Chrome PDF render failed ({process.returncode}): {process.stderr[-4000:]}")
        metadata["pdf_file"] = pdf_path.name
        metadata["pdf_sha256"] = sha256(pdf_path)
        metadata["pdf_audit"] = inspect_pdf(pdf_path, metadata, output / "render_preview")
        metadata["browser"] = subprocess.check_output([browser, "--version"], text=True).strip()
    if sha256(source) != before:
        raise RuntimeError("Source changed during rendering; rebuild from the final Markdown")
    (output / "render_manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"html": str(html_path), "pdf": str(pdf_path) if not args.html_only else None,
                      "audit": metadata.get("pdf_audit"), "source_sha256": before}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
