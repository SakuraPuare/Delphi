"""文档文件切分：Markdown 按标题层级，纯文本按段落"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

from delphi.ingestion.chunker import fallback_chunk
from delphi.ingestion.models import Chunk, ChunkMetadata

if TYPE_CHECKING:
    from pathlib import Path

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)", re.MULTILINE)

MAX_SECTION_LINES = 50


def _split_by_headings(text: str, level: int) -> list[tuple[str, str]]:
    """Split text into (heading_title, body) pairs at the given heading level.

    Lines before the first heading of that level are grouped under title=""."""
    prefix = "#" * level
    pattern = re.compile(rf"^{prefix}\s+(.*)", re.MULTILINE)

    sections: list[tuple[str, str]] = []
    positions: list[tuple[int, str]] = []

    for m in pattern.finditer(text):
        # Only match exact level (not deeper headings)
        line_start = m.start()
        # Check that the heading is exactly `level` #'s by verifying no extra #
        full_match = m.group(0)
        if full_match.lstrip().startswith(prefix + "#"):
            continue
        positions.append((line_start, m.group(1).strip()))

    if not positions:
        return [("", text)]

    # Content before first heading
    if positions[0][0] > 0:
        preamble = text[: positions[0][0]].strip()
        if preamble:
            sections.append(("", preamble))

    for i, (pos, title) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        body = text[pos:end]
        sections.append((title, body))

    return sections


def chunk_markdown(text: str) -> list[Chunk]:
    """Split markdown by H2 (primary), H1 fallback, H3 sub-split, sliding window last resort."""
    if not text.strip():
        logger.debug("Markdown 内容为空，跳过分块")
        return []

    # Determine primary split level
    h2_sections = _split_by_headings(text, 2)
    if len(h2_sections) > 1 or (len(h2_sections) == 1 and h2_sections[0][0]):
        primary_level = 2
        sections = h2_sections
    else:
        h1_sections = _split_by_headings(text, 1)
        if len(h1_sections) > 1 or (len(h1_sections) == 1 and h1_sections[0][0]):
            primary_level = 1
            sections = h1_sections
        else:
            # No headings at all — fallback
            logger.debug("Markdown 无标题结构，回退到滑动窗口分块")
            return _to_chunks(fallback_chunk(text), "heading", "")

    logger.debug("Markdown 按 H{} 标题分块, 段落数={}", primary_level, len(sections))

    chunks: list[Chunk] = []
    for title, body in sections:
        lines = body.splitlines()
        if len(lines) > MAX_SECTION_LINES and primary_level == 2:
            # Sub-split by H3
            sub_sections = _split_by_headings(body, 3)
            for sub_title, sub_body in sub_sections:
                heading_path = " > ".join(filter(None, [title, sub_title]))
                sub_lines = sub_body.splitlines()
                if len(sub_lines) > MAX_SECTION_LINES:
                    for fc in fallback_chunk(sub_body):
                        fc.metadata.node_type = "heading"
                        chunks.append(fc)
                else:
                    chunks.append(_make_heading_chunk(sub_body, heading_path))
        elif len(lines) > MAX_SECTION_LINES:
            for fc in fallback_chunk(body):
                fc.metadata.node_type = "heading"
                chunks.append(fc)
        else:
            chunks.append(_make_heading_chunk(body, title))

    return chunks


def _make_heading_chunk(text: str, heading_path: str) -> Chunk:
    lines = text.splitlines()
    return Chunk(
        text=text,
        metadata=ChunkMetadata(
            start_line=1,
            end_line=len(lines),
            node_type="heading",
            language="markdown",
            file_path=heading_path,  # temporarily store heading path; overwritten by caller
        ),
    )


def _to_chunks(chunks: list[Chunk], node_type: str, heading_path: str) -> list[Chunk]:
    for c in chunks:
        c.metadata.node_type = node_type
    return chunks


def chunk_text(text: str) -> list[Chunk]:
    """Split plain text by double newlines (paragraphs), merging small ones."""
    if not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not paragraphs:
        return []

    logger.debug("纯文本按段落分块, 段落数={}", len(paragraphs))

    merged: list[str] = []
    current_lines: list[str] = []
    current_count = 0

    for para in paragraphs:
        para_lines = para.splitlines()
        if current_count + len(para_lines) > MAX_SECTION_LINES and current_lines:
            merged.append("\n\n".join(current_lines))
            current_lines = [para]
            current_count = len(para_lines)
        else:
            current_lines.append(para)
            current_count += len(para_lines)

    if current_lines:
        merged.append("\n\n".join(current_lines))

    chunks: list[Chunk] = []
    line_offset = 1
    for block in merged:
        block_lines = block.splitlines()
        chunks.append(
            Chunk(
                text=block,
                metadata=ChunkMetadata(
                    start_line=line_offset,
                    end_line=line_offset + len(block_lines) - 1,
                    node_type="paragraph",
                    language="text",
                ),
            )
        )
        line_offset += len(block_lines) + 1  # +1 for the blank line separator

    return chunks


def chunk_pdf(path: Path) -> list[Chunk]:
    """按页提取 PDF 文本，每页作为一个 chunk，过长的页再用段落切分。"""
    import fitz  # pymupdf

    logger.info("开始解析 PDF 文件, path={}", path)
    chunks: list[Chunk] = []
    doc = fitz.open(path)
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        if not text:
            continue
        lines = text.splitlines()
        if len(lines) > MAX_SECTION_LINES:
            # 过长的页按段落切分
            sub_chunks = chunk_text(text)
            for c in sub_chunks:
                c.metadata.language = "pdf"
                c.metadata.node_type = f"page_{page_num + 1}"
            chunks.extend(sub_chunks)
        else:
            chunks.append(
                Chunk(
                    text=text,
                    metadata=ChunkMetadata(
                        start_line=page_num + 1,  # 用 page number 作为 start_line
                        end_line=page_num + 1,
                        node_type=f"page_{page_num + 1}",
                        language="pdf",
                    ),
                )
            )
    doc.close()
    logger.info("PDF 解析完成, path={}, 页数={}, 块数={}", path, len(doc) if hasattr(doc, '__len__') else '?', len(chunks))
    return chunks


def chunk_html(text: str) -> list[Chunk]:
    """用 trafilatura 提取 HTML 正文，然后按段落切分。"""
    from trafilatura import extract

    body = extract(text, include_comments=False, include_tables=True, output_format="txt")
    if not body or not body.strip():
        logger.debug("HTML 正文提取为空，跳过分块")
        return []
    logger.debug("HTML 正文提取完成, 正文长度={}", len(body))
    chunks = chunk_text(body)
    for c in chunks:
        c.metadata.language = "html"
    return chunks


def chunk_doc_file(path: Path) -> list[Chunk]:
    """Detect file type and chunk accordingly. Fill in file-level metadata."""
    ext = path.suffix.lower()
    logger.debug("开始处理文档文件, path={}, ext={}", path, ext)

    # PDF 需要特殊处理（二进制文件）
    if ext == ".pdf":
        logger.debug("检测到 PDF 文件，使用 PDF 解析器, path={}", path)
        chunks = chunk_pdf(path)
        for c in chunks:
            c.metadata.file_path = str(path)
        return chunks

    content = path.read_text(errors="replace")

    if ext in (".md", ".mdx"):
        chunks = chunk_markdown(content)
        lang = "markdown"
    elif ext == ".txt":
        chunks = chunk_text(content)
        lang = "text"
    elif ext in (".html", ".htm"):
        chunks = chunk_html(content)
        lang = "html"
    else:
        chunks = fallback_chunk(content)
        lang = ext.lstrip(".")

    for c in chunks:
        c.metadata.file_path = str(path)
        if not c.metadata.language:
            c.metadata.language = lang

    logger.info("文档分块完成, path={}, 块数={}, 类型={}", path, len(chunks), lang)
    return chunks
