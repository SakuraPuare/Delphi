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
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".java": "java",
}

# Node types to extract as top-level chunks
_CHUNK_NODE_TYPES: set[str] = {
    "function_definition",  # Python
    "class_definition",  # Python
    "function_declaration",  # JS/TS/Go/C/C++/Java
    "class_declaration",  # JS/TS/Java
    "method_definition",  # JS/TS
    "method_declaration",  # Java
    "arrow_function",  # JS/TS (top-level only)
    "impl_item",  # Rust
    "function_item",  # Rust
    "struct_item",  # Rust
}

_NAME_NODE_TYPES: set[str] = {
    "identifier",
    "name",
    "property_identifier",
    "type_identifier",
}

MAX_CHUNK_LINES = 100
FALLBACK_WINDOW = 50
FALLBACK_OVERLAP = 10


def detect_language(path: Path) -> str | None:
    return EXT_MAP.get(path.suffix.lower())


def parse_code(source: bytes, language: str) -> list[Chunk]:
    """Parse source code with Tree-sitter and extract function/class chunks."""
    lang = _LANGUAGES.get(language)
    if lang is None:
        return []

    parser = Parser(lang)
    tree = parser.parse(source)

    chunks: list[Chunk] = []
    _extract_nodes(tree.root_node, source, chunks)

    # If no meaningful nodes found, fall back to sliding window
    if not chunks:
        return fallback_chunk(source.decode(errors="replace"))

    return chunks


def _get_symbol_name(node: Node) -> str:
    """从 AST 节点提取符号名称。"""
    for child in node.children:
        if child.type in _NAME_NODE_TYPES:
            return child.text.decode(errors="replace") if child.text else ""
    return ""


def _get_parent_symbol(node: Node) -> str:
    """向上查找父级符号名称（如方法所属的类）。"""
    parent = node.parent
    while parent:
        if parent.type in _CHUNK_NODE_TYPES:
            return _get_symbol_name(parent)
        parent = parent.parent
    return ""


def _extract_nodes(node: Node, source: bytes, chunks: list[Chunk]) -> None:
    """Recursively extract chunk-worthy nodes."""
    if node.type in _CHUNK_NODE_TYPES:
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
            # Split oversized nodes with sliding window
            symbol = _get_symbol_name(node)
            parent = _get_parent_symbol(node)
            for sub in fallback_chunk(text, FALLBACK_WINDOW, FALLBACK_OVERLAP):
                sub.metadata.node_type = node.type
                sub.metadata.start_line += node.start_point.row
                sub.metadata.end_line += node.start_point.row
                sub.metadata.symbol_name = symbol
                sub.metadata.parent_symbol = parent
                chunks.append(sub)
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
        return []

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
    source = path.read_bytes()

    chunks = parse_code(source, language) if language else fallback_chunk(source.decode(errors="replace"))

    # Fill in file-level metadata
    for chunk in chunks:
        chunk.metadata.file_path = str(path)
        chunk.metadata.repo_url = repo_url
        if language:
            chunk.metadata.language = language

    return chunks
