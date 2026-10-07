"""Check a Hancom-rendered report against its Markdown and record layout evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

import pymupdf as fitz

from build_hwpx_copy import SRC, REPO, parse, verify_protected_sources


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).replace("\u00ad", "")


def audit(source: Path, hwpx: Path) -> dict:
    source_text = source.read_text(encoding="utf-8-sig")
    cover, chapters = parse(source_text)
    expected = [("project", cover["project"])]
    expected.extend(("summary", s) for s in cover["summary"])
    for heading, blocks in chapters:
        expected.append(("chapter", heading))
        for block in blocks:
            if block[0] == "p":
                expected.append(("paragraph", block[2]))
            elif block[0] == "table":
                expected.extend(("table_cell", c) for row in block[1] for c in row if c)
            elif block[0] == "fig":
                expected.append(("caption", f"[그림 {block[1]}] {block[2]}"))
    with zipfile.ZipFile(hwpx) as z:
        package_xml = "\n".join(z.read(n).decode("utf-8") for n in z.namelist()
                                if n.endswith((".xml", ".hpf")))
        preview_bytes = [z.read(n) for n in z.namelist() if n.endswith(".txt")]
        preview_text = "\n".join(data.decode("utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff")
                                             else "utf-8-sig") for data in preview_bytes)
        sections = [ET.fromstring(z.read(n)) for n in z.namelist()
                    if re.fullmatch(r"Contents/section\d+\.xml", n)]
        xml_text = normalize("".join(e.text or "" for root in sections for e in root.iter()
                                     if e.tag.rsplit("}", 1)[-1] == "t"))
        picture_controls = sum(e.tag.rsplit("}", 1)[-1] == "pic" for root in sections for e in root.iter())
    missing_xml = [{"kind": kind, "text": text} for kind, text in expected if normalize(text) not in xml_text]
    pdf = hwpx.with_suffix(".pdf")
    with fitz.open(pdf) as doc:
        pdf_metadata = json.dumps(doc.metadata, ensure_ascii=False)
        page_texts = [page.get_text() for page in doc]
        joined = normalize("".join(text.replace("일반국민/대학(원)생 부문", "") for text in page_texts))
        missing_pdf_short = [{"kind": kind, "text": text} for kind, text in expected
                             if kind in {"chapter", "caption", "table_cell"} and normalize(text) not in joined]
        bounds = []
        for page in doc:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        rect = fitz.Rect(span["bbox"])
                        if span["text"].strip() and (rect.x0 < -1 or rect.x1 > page.rect.width + 1
                                                   or rect.y0 < -1 or rect.y1 > page.rect.height + 1):
                            bounds.append({"page": page.number + 1, "text": span["text"], "bbox": list(rect)})
        chapter_pages = {heading: [i + 1 for i, text in enumerate(page_texts)
                                  if normalize(heading) in normalize(text)] for heading, _ in chapters}
        required_form_text = ["2026년 10월 8일", "팀장 : 허예준", "팀원 : 장준용", "경진대회 만족도 조사 완료"]
        missing_form_text = [text for text in required_form_text if normalize(text) not in joined]
        result = {"pages": len(doc), "chapter_pages": chapter_pages,
                  "pdf_image_instances": sum(len(page.get_images()) for page in doc),
                  "replacement_characters": "".join(page_texts).count("\ufffd"),
                  "out_of_page_text": bounds, "missing_pdf_short_blocks": missing_pdf_short,
                  "missing_required_form_text": missing_form_text}
    forbidden = ("경쟁", "chlanstjr0301", "workspace---claude", "518f9ada91fa8adb",
                 "공개 코드를 복사", "github.com/chlanstjr")
    content_check = {}
    for label, value in (("markdown", normalize(source_text)), ("hwpx", xml_text), ("pdf", joined)):
        found = [token for token in forbidden if normalize(token).casefold() in value.casefold()]
        content_check[label] = {"unexpected_provenance_markers": found,
                                "method_reference_29_present": "10.1016/S0047-259X(03)00096-4" in value}
    metadata_markers = {label: [token for token in forbidden
                               if normalize(token).casefold() in normalize(value).casefold()]
                        for label, value in (("hwpx_xml", package_xml), ("hwpx_preview_text", preview_text),
                                             ("pdf_metadata", pdf_metadata))}
    return {"source": source.relative_to(REPO).as_posix(), "hwpx": hwpx.relative_to(REPO).as_posix(),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "hwpx_sha256": hashlib.sha256(hwpx.read_bytes()).hexdigest(),
            "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "expected_text_blocks": len(expected), "missing_hwpx_blocks": missing_xml,
            "hwpx_picture_controls": picture_controls, "pdf": result,
            "content_check": content_check,
            "metadata_content_check": metadata_markers,
            "protected_sources": verify_protected_sources()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SRC)
    parser.add_argument("--hwpx", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.source.resolve(), args.hwpx.resolve())
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = args.output.resolve()
        if not target.is_relative_to((REPO / "yejun").resolve()) or "원본보관" in target.parts:
            raise ValueError("Audit output must be under yejun/ and outside 원본보관")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(serialized, encoding="utf-8")
    print(serialized)
    if (result["missing_hwpx_blocks"] or result["pdf"]["out_of_page_text"]
            or result["pdf"]["missing_pdf_short_blocks"] or result["pdf"]["missing_required_form_text"]
            or any(item["unexpected_provenance_markers"] or not item["method_reference_29_present"]
                   for item in result["content_check"].values())
            or any(result["metadata_content_check"].values())):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
