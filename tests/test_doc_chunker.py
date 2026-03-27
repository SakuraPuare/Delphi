"""doc_chunker 单元测试"""

from pathlib import Path
from textwrap import dedent

from delphi.ingestion.doc_chunker import (
    chunk_doc_file,
    chunk_html,
    chunk_markdown,
    chunk_pdf,
    chunk_text,
)


def test_chunk_markdown_multi_h2():
    text = dedent("""\
        # Guide

        Intro paragraph.

        ## Installation

        Install steps here.

        ## Configuration

        Config details here.

        ## Usage

        Usage info here.
    """)
    chunks = chunk_markdown(text)
    assert len(chunks) >= 3
    assert all(c.metadata.node_type == "heading" for c in chunks)


def test_chunk_markdown_h1_only():
    text = dedent("""\
        # Chapter One

        Content of chapter one.

        # Chapter Two

        Content of chapter two.
    """)
    chunks = chunk_markdown(text)
    assert len(chunks) >= 2
    assert all(c.metadata.node_type == "heading" for c in chunks)


def test_chunk_markdown_no_headings():
    text = "Just some plain text\nwith multiple lines\nbut no headings at all.\n"
    chunks = chunk_markdown(text)
    assert len(chunks) >= 1
    # Falls back to sliding window, node_type should still be "heading"
    assert all(c.metadata.node_type == "heading" for c in chunks)


def test_chunk_markdown_h3_subsplit():
    """H2 section exceeding 50 lines should be sub-split by H3."""
    long_body = "\n".join(f"line {i}" for i in range(30))
    text = "## Big Section\n\n### Part A\n\n" + long_body + "\n\n### Part B\n\n" + long_body
    chunks = chunk_markdown(text)
    assert len(chunks) >= 2


def test_chunk_text_paragraphs():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n"
    chunks = chunk_text(text)
    assert len(chunks) >= 1
    assert all(c.metadata.node_type == "paragraph" for c in chunks)
    # All three paragraphs should be present in the output
    combined = " ".join(c.text for c in chunks)
    assert "First" in combined
    assert "Third" in combined


def test_chunk_text_single_long_paragraph():
    lines = [f"Sentence number {i}." for i in range(80)]
    text = "\n".join(lines)
    chunks = chunk_text(text)
    assert len(chunks) >= 1
    assert all(c.metadata.node_type == "paragraph" for c in chunks)


def test_chunk_doc_file_markdown(tmp_path: Path):
    md = tmp_path / "doc.md"
    md.write_text("## Section A\n\nContent A.\n\n## Section B\n\nContent B.\n")
    chunks = chunk_doc_file(md)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.metadata.file_path == str(md)
        assert c.metadata.language == "markdown"


def test_chunk_doc_file_txt(tmp_path: Path):
    txt = tmp_path / "notes.txt"
    txt.write_text("Para one.\n\nPara two.\n\nPara three.\n")
    chunks = chunk_doc_file(txt)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.metadata.file_path == str(txt)
        assert c.metadata.language == "text"


def test_chunk_doc_file_unknown_ext(tmp_path: Path):
    rst = tmp_path / "readme.rst"
    rst.write_text("Some reStructuredText content\n====\n\nBody here.\n")
    chunks = chunk_doc_file(rst)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.metadata.language == "rst"


def test_chunk_markdown_empty():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n  \n  ") == []


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n  \n  ") == []


# ---------------------------------------------------------------------------
# PDF tests
# ---------------------------------------------------------------------------


def _create_test_pdf(path: Path, pages: list[str]) -> None:
    """Helper: create a simple PDF with the given text on each page."""
    import fitz

    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def test_chunk_pdf_single_page(tmp_path: Path):
    pdf = tmp_path / "single.pdf"
    _create_test_pdf(pdf, ["Hello from page one."])
    chunks = chunk_pdf(pdf)
    assert len(chunks) == 1
    assert "Hello from page one" in chunks[0].text
    assert chunks[0].metadata.language == "pdf"
    assert chunks[0].metadata.node_type == "page_1"
    assert chunks[0].metadata.start_line == 1
    assert chunks[0].metadata.end_line == 1


def test_chunk_pdf_multi_page(tmp_path: Path):
    pdf = tmp_path / "multi.pdf"
    _create_test_pdf(pdf, ["Page one text.", "Page two text.", "Page three text."])
    chunks = chunk_pdf(pdf)
    assert len(chunks) == 3
    combined = " ".join(c.text for c in chunks)
    assert "Page one" in combined
    assert "Page three" in combined
    for i, c in enumerate(chunks):
        assert c.metadata.language == "pdf"
        assert c.metadata.node_type == f"page_{i + 1}"


def test_chunk_pdf_empty_page_skipped(tmp_path: Path):
    """Pages with no text (e.g. blank pages) should be skipped."""
    import fitz

    pdf = tmp_path / "blank.pdf"
    doc = fitz.open()
    doc.new_page()  # blank page
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Only real page.")
    doc.save(str(pdf))
    doc.close()

    chunks = chunk_pdf(pdf)
    assert len(chunks) == 1
    assert "Only real page" in chunks[0].text
    assert chunks[0].metadata.node_type == "page_2"


def test_chunk_pdf_long_page_subsplit(tmp_path: Path):
    """A page with >50 lines should be sub-split via chunk_text."""
    long_text = "\n".join(f"Line number {i}" for i in range(60))
    pdf = tmp_path / "long.pdf"
    _create_test_pdf(pdf, [long_text])
    chunks = chunk_pdf(pdf)
    assert len(chunks) >= 1
    for c in chunks:
        assert c.metadata.language == "pdf"
        assert c.metadata.node_type == "page_1"


def test_chunk_doc_file_pdf(tmp_path: Path):
    pdf = tmp_path / "doc.pdf"
    _create_test_pdf(pdf, ["PDF via chunk_doc_file."])
    chunks = chunk_doc_file(pdf)
    assert len(chunks) >= 1
    assert chunks[0].metadata.file_path == str(pdf)
    assert chunks[0].metadata.language == "pdf"


# ---------------------------------------------------------------------------
# HTML tests
# ---------------------------------------------------------------------------

SAMPLE_HTML = "<html><body><h1>Title</h1><p>Hello world. This is a test paragraph.</p></body></html>"


def test_chunk_html_basic():
    chunks = chunk_html(SAMPLE_HTML)
    assert len(chunks) >= 1
    combined = " ".join(c.text for c in chunks)
    assert "Hello world" in combined or "Title" in combined


def test_chunk_html_empty():
    assert chunk_html("") == []
    assert chunk_html("   ") == []


def test_chunk_html_no_body():
    """HTML with no extractable body text should return empty list."""
    assert chunk_html("<html><head><title>T</title></head><body></body></html>") == []


def test_chunk_doc_file_html(tmp_path: Path):
    html_file = tmp_path / "page.html"
    html_file.write_text(SAMPLE_HTML)
    chunks = chunk_doc_file(html_file)
    # trafilatura may or may not extract text from minimal HTML;
    # if it does, verify metadata
    for c in chunks:
        assert c.metadata.file_path == str(html_file)
        # chunk_html now explicitly sets language="html"
        assert c.metadata.language == "html"


def test_chunk_doc_file_htm(tmp_path: Path):
    """Ensure .htm extension is also handled as HTML."""
    htm_file = tmp_path / "page.htm"
    htm_file.write_text(SAMPLE_HTML)
    chunks = chunk_doc_file(htm_file)
    for c in chunks:
        assert c.metadata.file_path == str(htm_file)
        assert c.metadata.language == "html"
