"""doc_chunker 单元测试"""

from pathlib import Path
from textwrap import dedent

from delphi.ingestion.doc_chunker import chunk_doc_file, chunk_markdown, chunk_text


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
