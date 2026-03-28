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


# ---------------------------------------------------------------------------
# Coverage gap tests
# ---------------------------------------------------------------------------


def test_chunk_markdown_h2_oversized_subsplit_h3():
    """H2 oversized section with successful sub-split at H3 level (lines 86-97).

    When primary split is H2 and a section exceeds MAX_SECTION_LINES,
    it sub-splits at H3. Verify heading_path format and line offsets.
    """
    # Small H2 section first, then an oversized H2 section with H3 sub-headings
    lines = ["## Intro", "", "Short intro.", ""]
    lines.append("## Big Section")
    lines.append("")
    lines.append("### Part A")
    lines.append("")
    for i in range(30):
        lines.append(f"Part A line {i}.")
    lines.append("")
    lines.append("### Part B")
    lines.append("")
    for i in range(30):
        lines.append(f"Part B line {i}.")
    text = "\n".join(lines)

    chunks = chunk_markdown(text)

    # Should have at least 3 chunks: Intro, Part A, Part B
    assert len(chunks) >= 3

    # Find chunks from the sub-split — they should have heading_path format
    symbol_names = [c.metadata.symbol_name for c in chunks]
    assert any("Big Section > Part A" in (s or "") for s in symbol_names), (
        f"Expected 'Big Section > Part A' in symbol_names, got {symbol_names}"
    )
    assert any("Big Section > Part B" in (s or "") for s in symbol_names), (
        f"Expected 'Big Section > Part B' in symbol_names, got {symbol_names}"
    )

    # Line offsets should not all be 1
    offsets = [c.metadata.start_line for c in chunks]
    assert len(set(offsets)) > 1, f"All offsets are the same: {offsets}"


def test_chunk_markdown_h1_oversized_no_subsplit():
    """H1 oversized section with no H2 sub-headings — falls back to sliding window (lines 100-106)."""
    lines = ["# Tiny Chapter", "", "Just a line.", ""]
    lines.append("# Huge Chapter")
    lines.append("")
    for i in range(60):
        lines.append(f"Content line {i} of the huge chapter.")
    text = "\n".join(lines)

    chunks = chunk_markdown(text)

    # The huge chapter should be split via fallback_chunk (sliding window)
    huge_chunks = [c for c in chunks if c.metadata.symbol_name == "Huge Chapter"]
    assert len(huge_chunks) >= 1, "Expected at least one chunk for 'Huge Chapter'"

    # Verify offsets are adjusted (not all 1)
    offsets = [c.metadata.start_line for c in huge_chunks]
    # The huge chapter starts after the tiny chapter, so offset should be > 1
    assert any(o > 1 for o in offsets), f"Expected offset > 1 for huge chapter, got {offsets}"


def test_chunk_markdown_heading_path_in_symbol_name(tmp_path: Path):
    """After chunk_doc_file, heading path should be preserved in symbol_name."""
    md = tmp_path / "doc.md"
    md.write_text("## Alpha\n\nAlpha content.\n\n## Beta\n\nBeta content.\n")
    chunks = chunk_doc_file(md)

    assert len(chunks) >= 2
    symbol_names = [c.metadata.symbol_name for c in chunks]
    assert "Alpha" in symbol_names
    assert "Beta" in symbol_names
    # file_path should be the actual file, not the heading path
    for c in chunks:
        assert c.metadata.file_path == str(md)


def test_chunk_markdown_line_offsets_correct():
    """Each chunk's start_line should correspond to its actual position in the text."""
    text = dedent("""\
        ## First

        First body.

        ## Second

        Second body.

        ## Third

        Third body.
    """)
    chunks = chunk_markdown(text)
    assert len(chunks) == 3

    # "## First" is at line 1, "## Second" at line 5, "## Third" at line 9
    # (counting from 1, blank lines included)
    assert chunks[0].metadata.start_line == 1
    assert chunks[1].metadata.start_line > chunks[0].metadata.start_line
    assert chunks[2].metadata.start_line > chunks[1].metadata.start_line

    # Verify ordering is strictly increasing
    for i in range(len(chunks) - 1):
        assert chunks[i].metadata.start_line < chunks[i + 1].metadata.start_line


def test_split_by_headings_skips_deeper_levels():
    """Splitting at level 2 should NOT split on ### H3 headings (line 32)."""
    from delphi.ingestion.doc_chunker import _split_by_headings

    text = dedent("""\
        ## Section One

        Some content.

        ### Subsection 1a

        More content under subsection.

        ## Section Two

        Content of section two.
    """)
    sections = _split_by_headings(text, 2)

    # Should only have 2 sections (split at ##), not 3
    titled = [(t, body) for t, body, _ in sections if t]
    assert len(titled) == 2, f"Expected 2 titled sections, got {len(titled)}: {[t for t, _ in titled]}"
    assert titled[0][0] == "Section One"
    assert titled[1][0] == "Section Two"

    # The ### Subsection should be inside Section One's body
    assert "### Subsection 1a" in titled[0][1]
    assert "More content under subsection" in titled[0][1]


def test_chunk_text_paragraph_merging():
    """Multiple small paragraphs should be merged until MAX_SECTION_LINES is hit (line 136, 146-149)."""
    # Create many small paragraphs that individually are tiny but together exceed 50 lines
    paragraphs = []
    for i in range(60):
        paragraphs.append(f"Paragraph {i} with a single line.")
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text)

    # Should produce more than 1 chunk since 60 single-line paragraphs > MAX_SECTION_LINES
    assert len(chunks) >= 2, f"Expected >=2 chunks from 60 paragraphs, got {len(chunks)}"
    assert all(c.metadata.node_type == "paragraph" for c in chunks)

    # All paragraphs should be present across chunks
    combined = " ".join(c.text for c in chunks)
    assert "Paragraph 0" in combined
    assert "Paragraph 59" in combined


def test_chunk_text_final_flush():
    """The final batch of current_lines should be flushed (lines 154-155)."""
    # 3 paragraphs, all well under 50 lines — they should all end up in one chunk
    text = "Alpha paragraph.\n\nBeta paragraph.\n\nGamma paragraph."
    chunks = chunk_text(text)

    assert len(chunks) == 1
    assert "Alpha" in chunks[0].text
    assert "Gamma" in chunks[0].text


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------

from delphi.ingestion.doc_chunker import _split_by_headings


def test_chunk_markdown_h1_oversized_subsplit_h2():
    """H2 oversized section sub-split at H3, where a sub-section is ALSO oversized (lines 91-97).

    When primary split is H2 and a section exceeds MAX_SECTION_LINES, it sub-splits
    at H3. If a resulting H3 sub-section is still >50 lines, it falls back to
    fallback_chunk for that sub-section (lines 92-97).
    """
    # One H3 sub-section with >50 lines triggers the fallback_chunk path inside sub-split
    h3a_body = "\n".join(f"H3A line {i}." for i in range(55))
    h3b_body = "\n".join(f"H3B line {i}." for i in range(10))
    text = (
        "## Small Section\n\n"
        "Short content.\n\n"
        "## Big Section\n\n"
        "### Part Alpha\n\n"
        f"{h3a_body}\n\n"
        "### Part Beta\n\n"
        f"{h3b_body}\n"
    )

    chunks = chunk_markdown(text)

    # Part Alpha is >50 lines so it goes through fallback_chunk (lines 92-97)
    # Part Beta is small so it uses _make_heading_chunk (line 99)
    symbol_names = [c.metadata.symbol_name for c in chunks]
    assert any("Big Section > Part Alpha" in (s or "") for s in symbol_names), (
        f"Expected 'Big Section > Part Alpha' in symbol_names, got {symbol_names}"
    )
    assert any("Big Section > Part Beta" in (s or "") for s in symbol_names), (
        f"Expected 'Big Section > Part Beta' in symbol_names, got {symbol_names}"
    )

    # Line offsets should not all be 1
    offsets = [c.metadata.start_line for c in chunks]
    assert len(set(offsets)) > 1, f"Expected varied start_line offsets, got {offsets}"


def test_chunk_markdown_h1_oversized_no_subsplit():
    """H1 oversized section with no H2 sub-headings falls back to sliding window (lines 101-106)."""
    # Build a single H1 section that is >50 lines with no H2 headings inside
    long_body = "\n".join(f"Content line {i} of the chapter." for i in range(60))
    text = (
        "# Huge Chapter\n\n"
        f"{long_body}\n\n"
        "# Tiny Chapter\n\n"
        "Short content.\n"
    )

    chunks = chunk_markdown(text)

    # The oversized section should fall back to sliding window
    huge_chunks = [c for c in chunks if c.metadata.symbol_name == "Huge Chapter"]
    assert len(huge_chunks) >= 1, "Expected at least one chunk for 'Huge Chapter'"

    # symbol_name should contain the H1 title
    for c in huge_chunks:
        assert c.metadata.symbol_name == "Huge Chapter"

    # start_line / end_line should have correct offsets (not all 1)
    if len(huge_chunks) > 1:
        starts = [c.metadata.start_line for c in huge_chunks]
        assert len(set(starts)) > 1, f"Expected varied start_lines for fallback chunks, got {starts}"


def test_chunk_markdown_heading_path_in_symbol_name():
    """After chunk_doc_file, heading path is preserved in symbol_name (not overwritten by file_path)."""
    tmp = Path("/tmp/test_heading_path.md")
    h2a_body = "\n".join(f"Line {i}." for i in range(30))
    h2b_body = "\n".join(f"Line {i}." for i in range(30))
    content = (
        "# Title\n\n"
        "## Section A\n\n"
        f"{h2a_body}\n\n"
        "## Section B\n\n"
        f"{h2b_body}\n"
    )
    tmp.write_text(content)
    try:
        chunks = chunk_doc_file(tmp)
        # file_path should be set to the file path
        assert all(c.metadata.file_path == str(tmp) for c in chunks)
        # symbol_name should still contain heading info, not be overwritten
        symbol_names = [c.metadata.symbol_name for c in chunks if c.metadata.symbol_name]
        assert len(symbol_names) >= 1, "Expected at least one chunk with a symbol_name heading path"
        assert any("Section" in s for s in symbol_names), (
            f"Expected heading path in symbol_name, got {symbol_names}"
        )
    finally:
        tmp.unlink(missing_ok=True)


def test_chunk_markdown_line_offsets_correct():
    """Each chunk's start_line corresponds to the actual line position in the original text."""
    text = dedent("""\
        ## First Section

        Content of first section.

        ## Second Section

        Content of second section.

        ## Third Section

        Content of third section.
    """)
    chunks = chunk_markdown(text)
    assert len(chunks) >= 3

    lines = text.splitlines()
    for c in chunks:
        if c.metadata.symbol_name:
            # The start_line should point to a line that contains the heading
            # (1-indexed, so subtract 1 for list access)
            idx = c.metadata.start_line - 1
            assert 0 <= idx < len(lines), (
                f"start_line {c.metadata.start_line} out of range for {len(lines)} lines"
            )
            # The line at start_line should contain the heading marker
            assert lines[idx].startswith("#"), (
                f"Expected heading at line {c.metadata.start_line}, got: {lines[idx]!r}"
            )


def test_split_by_headings_skips_deeper_levels():
    """Splitting at level 2 should NOT treat ### H3 headings as split points (line 32)."""
    text = dedent("""\
        ## Section One

        Some content here.

        ### Subsection 1a

        More content under subsection.

        ## Section Two

        Final content.
    """)
    sections = _split_by_headings(text, 2)

    # Only H2 headings should produce splits
    titled = [(t, body) for t, body, _ in sections if t]
    assert len(titled) == 2, f"Expected 2 titled sections, got {len(titled)}: {[t for t, _ in titled]}"
    assert titled[0][0] == "Section One"
    assert titled[1][0] == "Section Two"

    # The ### Subsection should be inside Section One's body, not a separate section
    assert "### Subsection 1a" in titled[0][1]
    assert "More content under subsection" in titled[0][1]


def test_chunk_text_paragraph_merging_edge_case():
    """Paragraph merging: when adding a paragraph would exceed MAX_SECTION_LINES,
    the current batch is flushed first (line 136, 146-149)."""
    # Create paragraphs where each is 10 lines, so after 5 paragraphs (50 lines)
    # the next one triggers a flush
    paragraphs = []
    for i in range(8):
        para = "\n".join(f"Para {i} line {j}." for j in range(10))
        paragraphs.append(para)
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text)

    # 80 total lines across 8 paragraphs should produce at least 2 chunks
    assert len(chunks) >= 2, f"Expected >=2 chunks, got {len(chunks)}"
    assert all(c.metadata.node_type == "paragraph" for c in chunks)

    # Verify all content is present
    combined = " ".join(c.text for c in chunks)
    assert "Para 0 line 0" in combined
    assert "Para 7 line 9" in combined

    # Verify start_line offsets increase across chunks
    starts = [c.metadata.start_line for c in chunks]
    assert starts == sorted(starts), f"start_lines should be monotonically increasing: {starts}"
    assert starts[0] == 1
    assert starts[-1] > 1
