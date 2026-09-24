import pymupdf
import pytest

from finrag.ingestion.chunker import chunk_document
from finrag.ingestion.parser import export_markdown, parse_pdf
from finrag.models import Block, Document


def test_native_table_numbers_and_pages(pdf):
    doc = parse_pdf(pdf, "demo.pdf")
    assert doc.pages == 2
    tables = [b for b in doc.blocks if b.kind == "table"]
    assert len(tables) == 1
    assert tables[0].page == 1
    assert "12,400" in tables[0].content and "10,800" in tables[0].content
    assert "Net income" in tables[0].content
    assert any("2,450" in b.content and b.page == 2 for b in doc.blocks)
    markdown = export_markdown(doc)
    assert "## PDF page 2" in markdown
    assert "Financial performance" in markdown
    assert not doc.warnings


def test_optional_layout_parser_keeps_table_units_and_years(pdf):
    pytest.importorskip("pymupdf4llm")
    doc = parse_pdf(pdf, "demo.pdf", backend="layout")
    table = next(block for block in doc.blocks if block.kind == "table")
    assert table.page == 1
    assert table.content.startswith("Figures in IDR billion")
    assert "|Revenue|12,400|10,800|" in table.content
    assert "|Net income|1,800|1,300|" in table.content


def test_chunker_keeps_tables_intact_and_never_crosses_pages(pdf):
    doc = parse_pdf(pdf, "demo.pdf")
    chunks = chunk_document(doc, max_words=40, overlap=5)
    table = next(b for b in doc.blocks if b.kind == "table")
    assert any(c.content == table.content and c.page == table.page for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)
    assert [c.id for c in chunks] == [c.id for c in chunk_document(doc, 40, 5)]
    assert not any("2,450" in c.content and c.page == 1 for c in chunks)


def test_long_paragraph_preserves_all_words_and_overlap():
    text = " ".join(f"word{i}" for i in range(101))
    doc = Document(
        id="a", filename="a.pdf", pages=1, parser="test", blocks=[Block(page=1, content=text)]
    )
    chunks = chunk_document(doc, 40, 5)
    assert len(chunks) == 3
    assert chunks[0].content.split()[-5:] == chunks[1].content.split()[:5]
    assert set(text.split()) == set(" ".join(c.content for c in chunks).split())
    with pytest.raises(ValueError):
        chunk_document(doc, 40, 40)


def test_invalid_empty_and_encrypted_pdf(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_text("not a pdf")
    with pytest.raises(ValueError, match="readable PDF"):
        parse_pdf(path, "bad.pdf")
    pdf = pymupdf.open()
    pdf.new_page()
    pdf.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="secret", user_pw="secret")
    pdf.close()
    with pytest.raises(ValueError, match="unencrypted"):
        parse_pdf(path, "bad.pdf")


def test_page_limit(pdf):
    with pytest.raises(ValueError, match="between 1 and 1"):
        parse_pdf(pdf, "demo.pdf", max_pages=1)


def test_ocr_failure_is_visible(tmp_path, monkeypatch):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Native text stays available when image OCR fails.")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False)
    pix.clear_with(255)
    page.insert_image(pymupdf.Rect(72, 100, 122, 150), pixmap=pix)
    path = tmp_path / "mixed.pdf"
    doc.save(path)
    doc.close()

    def fail(*args, **kwargs):
        raise RuntimeError("no OCR")

    monkeypatch.setattr(pymupdf.Page, "get_textpage_ocr", fail)
    parsed = parse_pdf(path, "mixed.pdf")
    assert any("OCR unavailable" in w for w in parsed.warnings)
    assert any("Native text" in b.content for b in parsed.blocks)
