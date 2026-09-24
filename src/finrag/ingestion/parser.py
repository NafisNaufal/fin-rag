"""Native text first, OCR on image pages, with physical (1-based) PDF page numbers."""

import hashlib
import json
from pathlib import Path

import pymupdf

from finrag.models import Block, Document


def validate_pdf(path: Path, max_pages: int) -> int:
    try:
        with pymupdf.open(path) as pdf:
            if not pdf.is_pdf or pdf.needs_pass:
                raise ValueError("Use an unencrypted PDF file.")
            if not 1 <= len(pdf) <= max_pages:
                raise ValueError(f"PDF must contain between 1 and {max_pages} pages.")
            return len(pdf)
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ValueError("This file is not a readable PDF.") from exc


def parse_pdf(
    path: Path,
    filename: str,
    *,
    company="",
    year=None,
    backend="pymupdf",
    ocr_language="eng",
    max_pages=500,
) -> Document:
    pages = validate_pdf(path, max_pages)
    # Identity includes parser configuration and user metadata: separate variants cannot overwrite
    # each other's indexed payload. Filenames are display labels, never filesystem paths.
    identity = path.read_bytes() + f"{backend}|{ocr_language}|{company}|{year}|{filename}".encode()
    doc = Document(
        id=hashlib.sha256(identity).hexdigest()[:24],
        filename=filename,
        company=company,
        year=year,
        pages=pages,
        parser=backend,
        blocks=[],
    )
    if backend == "layout":
        return _layout(path, doc)
    if backend == "docling":
        return _docling(path, doc)
    section = ""
    with pymupdf.open(path) as pdf:
        for page in pdf:
            number = page.number + 1
            text = page.get_text().strip()
            textpage = None
            # Mixed pages retain native text and OCR raster regions. Vector-only scans with very
            # little text use full-page OCR. Blank pages are recorded as warnings below.
            needs_ocr = bool(page.get_images()) or (len(text) < 30 and bool(page.get_drawings()))
            if needs_ocr:
                try:
                    textpage = page.get_textpage_ocr(
                        language=ocr_language, dpi=200, full=len(text) < 30
                    )
                except Exception as exc:
                    doc.warnings.append(
                        f"Page {number}: OCR unavailable ({type(exc).__name__}). "
                        "Install Tesseract and the requested language data."
                    )
            tables = []
            try:
                tables = list(page.find_tables().tables)
            except Exception as exc:
                doc.warnings.append(
                    f"Page {number}: table detection failed ({type(exc).__name__})."
                )
            ordered = []
            for table in tables:
                ordered.append((table.bbox[1], table.bbox[0], "table", table.to_markdown()))
            layout = page.get_text("dict", textpage=textpage, sort=True)
            for block in layout["blocks"]:
                if block["type"] != 0:
                    continue
                # Filter individual lines: a text block can span both a table and its caption.
                for line in block["lines"]:
                    rect = pymupdf.Rect(line["bbox"])
                    center = (rect.tl + rect.br) / 2
                    if any(center in pymupdf.Rect(t.bbox) for t in tables):
                        continue
                    content = "".join(s["text"] for s in line["spans"]).strip()
                    if not content:
                        continue
                    heading = max(s["size"] for s in line["spans"]) >= 15 and len(content) < 150
                    ordered.append((rect.y0, rect.x0, "heading" if heading else "text", content))
            for _, _, kind, content in sorted(ordered):
                if kind == "heading":
                    section = content
                doc.blocks.append(
                    Block(
                        page=number,
                        section=section,
                        kind="table" if kind == "table" else "text",
                        content=content,
                    )
                )
            if not ordered:
                doc.warnings.append(f"Page {number}: no extractable text found.")
    if not doc.blocks:
        raise ValueError(
            "No text could be extracted. Install OCR support or try the Docling parser."
        )
    return doc


def _layout(path: Path, doc: Document) -> Document:
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise ValueError(
            "Layout parsing is optional. Install it with: uv sync --extra layout"
        ) from exc

    pages = json.loads(pymupdf4llm.to_json(str(path))).get("pages", [])
    if len(pages) != doc.pages:
        raise ValueError("Layout parser did not process every PDF page.")
    section = ""
    for page in pages:
        number = page["page_number"]
        preceding_text = None
        for box in page.get("boxes", []):
            label = box.get("boxclass")
            if label in {"page-header", "page-footer", "picture"}:
                continue
            if label == "table":
                content = (box.get("table") or {}).get("markdown", "").strip()
                if preceding_text:
                    bottom, caption = preceding_text
                    if 0 <= box["y0"] - bottom <= 40 and len(caption) <= 300:
                        content = caption + "\n\n" + content
                preceding_text = None
            else:
                lines = [
                    "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                    for line in box.get("textlines") or []
                ]
                content = " ".join(line for line in lines if line)
            if not content:
                continue
            if label in {"section-header", "title"}:
                section = content
                preceding_text = None
            elif label != "table":
                preceding_text = (box["y1"], content)
            doc.blocks.append(
                Block(
                    page=number,
                    section=section,
                    kind="table" if label == "table" else "text",
                    content=content,
                )
            )
    if not doc.blocks:
        raise ValueError("Layout parser did not extract any text.")
    return doc


def _docling(path: Path, doc: Document) -> Document:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise ValueError("Docling is optional. Install it with: uv sync --extra docling") from exc
    result = DocumentConverter().convert(path)
    if str(result.status.value) != "success":
        raise ValueError(f"Docling conversion incomplete: {result.status.value}")
    section = ""
    for item, _level in result.document.iterate_items():
        label = str(item.label.value)
        if label in {"section_header", "title"}:
            section = item.text
        if not item.prov:
            continue
        if label == "table":
            content = item.export_to_markdown(doc=result.document)
        else:
            content = getattr(item, "text", "")
        if content.strip():
            doc.blocks.append(
                Block(
                    page=item.prov[0].page_no,
                    section=section,
                    kind="table" if label == "table" else "text",
                    content=content,
                )
            )
    if not doc.blocks:
        raise ValueError("Docling did not extract any text.")
    return doc


def export_markdown(doc: Document) -> str:
    parts = [
        f"# {doc.filename}",
        f"Company: {doc.company or 'Not specified'} | Year: {doc.year or '-'}",
    ]
    page, section = None, None
    for block in doc.blocks:
        if block.page != page:
            parts.append(f"\n## PDF page {block.page}")
            page = block.page
        if block.section and block.section != section:
            parts.append(f"\n### {block.section}")
            section = block.section
        parts.append(block.content)
    return "\n\n".join(parts) + "\n"
