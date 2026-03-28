"""Tree-sitter 代码切分 + 滑动窗口回退"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_javascript as tsjs
import tree_sitter_python as tspy
import tree_sitter_rust as tsrust
import tree_sitter_typescript as tsts
from loguru import logger
from tree_sitter import Language, Node, Parser

from delphi.ingestion.models import Chunk, ChunkMetadata

if TYPE_CHECKING:
    from pathlib import Path

# --- Language registry ---

_LANGUAGES: dict[str, Language] = {
    "python": Language(tspy.language()),
    "javascript": Language(tsjs.language()),
    "typescript": Language(tsts.language_typescript()),
    "tsx": Language(tsts.language_tsx()),
    "go": Language(tsgo.language()),
    "rust": Language(tsrust.language()),
    "c": Language(tsc.language()),
    "cpp": Language(tscpp.language()),
    "java": Language(tsjava.language()),
}

# Extension → language key
EXT_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".java": "java",
}

# Node types to extract as top-level chunks
_CHUNK_NODE_TYPES: set[str] = {
    "function_definition",  # Python / C / C++
    "class_definition",  # Python
    "function_declaration",  # JS/TS/Go/C/C++/Java
    "class_declaration",  # JS/TS/Java
    "method_definition",  # JS/TS
    "method_declaration",  # Java
    "arrow_function",  # JS/TS (top-level only)
    "impl_item",  # Rust
    "function_item",  # Rust
    "struct_item",  # Rust
    # C/C++ specific
    "class_specifier",  # C++ class
    "struct_specifier",  # C/C++ struct
    "enum_specifier",  # C/C++ enum
    "namespace_definition",  # C++ namespace
    # Go specific
    "type_declaration",  # Go type/struct
}

# 容器节点：包含子方法/函数的类/结构体等，需要递归提取子节点
_CONTAINER_NODE_TYPES: set[str] = {
    "class_definition",  # Python
    "class_declaration",  # JS/TS/Java
    "class_specifier",  # C++ class
    "struct_specifier",  # C/C++ struct
    "impl_item",  # Rust
    "namespace_definition",  # C++ namespace
}

_NAME_NODE_TYPES: set[str] = {
    "identifier",
    "name",
    "property_identifier",
    "type_identifier",
}

MAX_CHUNK_LINES = 100
FALLBACK_WINDOW = 50
FALLBACK_OVERLAP = 5


def detect_language(path: Path) -> str | None:
    return EXT_MAP.get(path.suffix.lower())


def parse_code(source: bytes, language: str) -> list[Chunk]:
    """Parse source code with Tree-sitter and extract function/class chunks."""
    lang = _LANGUAGES.get(language)
    if lang is None:
        logger.debug("不支持的语言，跳过 Tree-sitter 解析: language={}", language)
        return []

    parser = Parser(lang)
    tree = parser.parse(source)

    chunks: list[Chunk] = []
    _extract_nodes(tree.root_node, source, chunks)

    # If no meaningful nodes found, fall back to sliding window
    if not chunks:
        logger.debug("未提取到有效 AST 节点，回退到滑动窗口分块, language={}", language)
        return fallback_chunk(source.decode(errors="replace"))

    # Filter out trivially small chunks (empty or single-char)
    chunks = [c for c in chunks if len(c.text.strip()) > 1]

    # 过滤空行级 chunk；单行函数/方法仍保留（依赖上方 strip 长度过滤去掉纯标点）
    MIN_CHUNK_LINES = 1
    chunks = [
        c
        for c in chunks
        if c.metadata.node_type == "fallback" or (c.metadata.end_line - c.metadata.start_line + 1) >= MIN_CHUNK_LINES
    ]

    logger.debug("Tree-sitter 解析完成, language={}, 块数={}", language, len(chunks))
    return chunks


def _get_symbol_name(node: Node) -> str:
    """从 AST 节点提取符号名称。"""
    # Direct name child (Python, JS, Java, Go, Rust)
    for child in node.children:
        if child.type in _NAME_NODE_TYPES:
            return child.text.decode(errors="replace") if child.text else ""

    # C/C++: name is nested in declarator chain
    # e.g. function_definition -> function_declarator -> qualified_identifier
    for child in node.children:
        if child.type in ("function_declarator", "init_declarator", "declarator"):
            # Look for the name inside the declarator
            for sub in child.children:
                if sub.type in _NAME_NODE_TYPES:
                    return sub.text.decode(errors="replace") if sub.text else ""
                if sub.type in ("qualified_identifier", "scoped_identifier", "template_function"):
                    # Return the full qualified name like "Class::Method"
                    return sub.text.decode(errors="replace") if sub.text else ""
                if sub.type == "field_identifier":
                    return sub.text.decode(errors="replace") if sub.text else ""
            # Recurse one more level for deeply nested declarators
            for sub in child.children:
                if sub.type in ("function_declarator", "pointer_declarator", "reference_declarator"):
                    for subsub in sub.children:
                        if subsub.type in _NAME_NODE_TYPES:
                            return subsub.text.decode(errors="replace") if subsub.text else ""
                        if subsub.type in ("qualified_identifier", "scoped_identifier"):
                            return subsub.text.decode(errors="replace") if subsub.text else ""

    return ""


def _get_parent_symbol(node: Node) -> str:
    """向上查找父级符号名称（如方法所属的类）。"""
    parent = node.parent
    while parent:
        if parent.type in _CHUNK_NODE_TYPES:
            return _get_symbol_name(parent)
        parent = parent.parent
    return ""


def _split_large_node(node: Node, source: bytes) -> list[Chunk]:
    """尝试按语义边界切分过大的 AST 节点。

    先尝试按函数体内的顶层语句分组，失败则回退到滑动窗口。
    """
    symbol = _get_symbol_name(node)
    parent = _get_parent_symbol(node)

    # Find the compound_statement (function body) child
    body_node = None
    for child in node.children:
        if child.type in ("compound_statement", "block", "statement_block"):
            body_node = child
            break

    if body_node is None or len(body_node.children) < 3:
        # No body found or too few children, use sliding window
        return _fallback_split(node, source, symbol, parent)

    # Group consecutive statements into chunks that fit within MAX_CHUNK_LINES
    chunks: list[Chunk] = []
    group_children: list[Node] = []
    group_lines = 0

    for child in body_node.children:
        # Skip punctuation tokens like { and }
        if child.type in ("{", "}", "comment"):
            continue
        child_lines = child.end_point.row - child.start_point.row + 1

        if group_lines + child_lines > MAX_CHUNK_LINES and group_children:
            # Flush current group
            start_byte = group_children[0].start_byte
            end_byte = group_children[-1].end_byte
            text = source[start_byte:end_byte].decode(errors="replace")
            chunks.append(
                Chunk(
                    text=text,
                    metadata=ChunkMetadata(
                        start_line=group_children[0].start_point.row + 1,
                        end_line=group_children[-1].end_point.row + 1,
                        node_type=node.type,
                        symbol_name=symbol,
                        parent_symbol=parent,
                    ),
                )
            )
            group_children = [child]
            group_lines = child_lines
        else:
            group_children.append(child)
            group_lines += child_lines

    # Flush remaining
    if group_children:
        start_byte = group_children[0].start_byte
        end_byte = group_children[-1].end_byte
        text = source[start_byte:end_byte].decode(errors="replace")
        chunks.append(
            Chunk(
                text=text,
                metadata=ChunkMetadata(
                    start_line=group_children[0].start_point.row + 1,
                    end_line=group_children[-1].end_point.row + 1,
                    node_type=node.type,
                    symbol_name=symbol,
                    parent_symbol=parent,
                ),
            )
        )

    # If semantic splitting produced reasonable results, use them
    if len(chunks) > 1:
        return chunks

    # Otherwise fall back to sliding window
    return _fallback_split(node, source, symbol, parent)


def _fallback_split(node: Node, source: bytes, symbol: str, parent: str) -> list[Chunk]:
    """滑动窗口回退切分。"""
    text = source[node.start_byte : node.end_byte].decode(errors="replace")
    chunks = []
    for sub in fallback_chunk(text, FALLBACK_WINDOW, FALLBACK_OVERLAP):
        sub.metadata.node_type = node.type
        sub.metadata.start_line += node.start_point.row
        sub.metadata.end_line += node.start_point.row
        sub.metadata.symbol_name = symbol
        sub.metadata.parent_symbol = parent
        chunks.append(sub)
    return chunks


def _extract_nodes(node: Node, source: bytes, chunks: list[Chunk]) -> None:
    """Recursively extract chunk-worthy nodes."""
    if node.type in _CHUNK_NODE_TYPES:
        # 容器节点（类/结构体等）：递归提取子方法，使 parent_symbol 正确设置
        if node.type in _CONTAINER_NODE_TYPES:
            child_chunks: list[Chunk] = []
            for child in node.children:
                _extract_nodes(child, source, child_chunks)
            if child_chunks:
                # 子节点已提取，直接使用（parent_symbol 由 _get_parent_symbol 自动解析）
                chunks.extend(child_chunks)
                return

        # 非容器节点或容器内无可提取子节点：作为整体 chunk
        text = source[node.start_byte : node.end_byte].decode(errors="replace")
        lines = text.count("\n") + 1

        if lines <= MAX_CHUNK_LINES:
            chunks.append(
                Chunk(
                    text=text,
                    metadata=ChunkMetadata(
                        start_line=node.start_point.row + 1,
                        end_line=node.end_point.row + 1,
                        node_type=node.type,
                        symbol_name=_get_symbol_name(node),
                        parent_symbol=_get_parent_symbol(node),
                    ),
                )
            )
        else:
            logger.debug("AST 节点过大，尝试语义切分, node_type={}, 行数={}", node.type, lines)
            chunks.extend(_split_large_node(node, source))
        return  # Don't recurse into children of extracted nodes

    for child in node.children:
        _extract_nodes(child, source, chunks)


def fallback_chunk(
    text: str,
    window: int = FALLBACK_WINDOW,
    overlap: int = FALLBACK_OVERLAP,
) -> list[Chunk]:
    """Sliding window chunking for files that can't be parsed with Tree-sitter."""
    lines = text.splitlines(keepends=True)
    if not lines:
        logger.debug("文本为空，跳过滑动窗口分块")
        return []

    logger.debug("使用滑动窗口分块, 总行数={}, window={}, overlap={}", len(lines), window, overlap)

    chunks: list[Chunk] = []
    step = max(window - overlap, 1)

    for start in range(0, len(lines), step):
        end = min(start + window, len(lines))
        chunk_text = "".join(lines[start:end])
        if chunk_text.strip():
            chunks.append(
                Chunk(
                    text=chunk_text,
                    metadata=ChunkMetadata(
                        start_line=start + 1,
                        end_line=end,
                        node_type="fallback",
                    ),
                )
            )
        if end >= len(lines):
            break

    return chunks


def chunk_file(path: Path, repo_url: str = "") -> list[Chunk]:
    """Read a file and return chunks with metadata populated."""
    language = detect_language(path)
    logger.debug("开始处理文件, path={}, language={}", path, language or "unknown")
    source = path.read_bytes()

    chunks = parse_code(source, language) if language else fallback_chunk(source.decode(errors="replace"))

    # Fill in file-level metadata
    for chunk in chunks:
        chunk.metadata.file_path = str(path)
        chunk.metadata.repo_url = repo_url
        if language:
            chunk.metadata.language = language

    logger.info("文件分块完成, path={}, 块数={}, language={}", path, len(chunks), language or "fallback")
    return chunks
