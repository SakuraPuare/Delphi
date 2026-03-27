"""Graph RAG：利用代码符号关系图谱扩展检索结果

在向量检索返回 chunks 后，通过图谱查找每个 chunk 中符号的关联符号
（调用者、被调用者、继承关系等），将关联代码片段也加入上下文。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from delphi.graph.store import GraphStore
from delphi.retrieval.rag import ScoredChunk

if TYPE_CHECKING:
    from delphi.graph.extractor import CodeGraph, Symbol

logger = logging.getLogger(__name__)

# 关联符号的默认得分衰减系数：graph 扩展的 chunk 得分 = 原始 chunk 得分 * DECAY
_SCORE_DECAY = 0.6

# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _find_symbols_in_chunk(graph: CodeGraph, chunk: ScoredChunk) -> list[Symbol]:
    """在图谱中查找与 chunk 文件路径和行范围重叠的符号。"""
    matched: list[Symbol] = []
    for sym in graph.symbols.values():
        if sym.file_path != chunk.file_path:
            continue
        # 如果 chunk 没有行号信息，按文件路径匹配所有符号
        if chunk.start_line is None or chunk.end_line is None:
            matched.append(sym)
            continue
        # 行范围有交集即视为匹配
        if sym.start_line <= chunk.end_line and sym.end_line >= chunk.start_line:
            matched.append(sym)
    return matched


def _collect_related_qnames(graph: CodeGraph, symbol: Symbol) -> set[str]:
    """收集与给定符号直接关联的所有 qualified_name（调用者、被调用者、继承、包含）。"""
    qn = symbol.qualified_name
    related: set[str] = set()
    for rel in graph.relations:
        if rel.source == qn:
            related.add(rel.target)
        elif rel.target == qn:
            related.add(rel.source)
    return related


def _symbol_to_chunk(symbol: Symbol, score: float) -> ScoredChunk:
    """将图谱符号转换为 ScoredChunk（content 为符号的位置描述）。"""
    content = (
        f"// [graph-expanded] {symbol.kind} {symbol.qualified_name}\n"
        f"// {symbol.file_path}:{symbol.start_line}-{symbol.end_line}"
    )
    return ScoredChunk(
        content=content,
        file_path=symbol.file_path,
        start_line=symbol.start_line,
        end_line=symbol.end_line,
        score=score,
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def expand_with_graph(
    chunks: list[ScoredChunk],
    project_id: str,
    top_k: int = 5,
    *,
    graph_store: GraphStore | None = None,
) -> list[ScoredChunk]:
    """通过代码图谱扩展向量检索结果。

    流程：
    1. 从 GraphStore 加载项目图谱
    2. 对每个 chunk，查找其中包含的符号
    3. 通过图谱关系找到关联符号（调用者、被调用者、继承等）
    4. 将关联符号转为 ScoredChunk 并合并到结果中
    5. 去重、按 score 降序排列，返回扩展后的列表

    Args:
        chunks: 向量检索返回的原始 chunks
        project_id: 项目标识
        top_k: 最多扩展的关联 chunk 数量
        graph_store: 图谱存储实例，为 None 时自动创建

    Returns:
        扩展后的 chunk 列表（原始 + 关联），已去重并按 score 降序排列
    """
    if not chunks:
        return chunks

    store = graph_store or GraphStore()
    graph = store.get(project_id)
    if graph is None:
        logger.debug("No graph found for project '%s', skipping graph expansion", project_id)
        return chunks

    # 收集所有关联符号的 qualified_name -> 最佳来源 score
    related_qnames: dict[str, float] = {}
    # 已有 chunk 覆盖的 (file_path, start_line, end_line) 用于去重
    existing_ranges: set[tuple[str, int | None, int | None]] = {(c.file_path, c.start_line, c.end_line) for c in chunks}

    for chunk in chunks:
        symbols = _find_symbols_in_chunk(graph, chunk)
        for sym in symbols:
            for qn in _collect_related_qnames(graph, sym):
                # 保留最高的衰减 score
                decayed = chunk.score * _SCORE_DECAY
                if qn not in related_qnames or decayed > related_qnames[qn]:
                    related_qnames[qn] = decayed

    # 将关联符号转为 chunk，跳过已存在的范围
    expanded: list[ScoredChunk] = []
    for qn, score in related_qnames.items():
        sym = graph.symbols.get(qn)
        if sym is None:
            continue
        key = (sym.file_path, sym.start_line, sym.end_line)
        if key in existing_ranges:
            continue
        existing_ranges.add(key)
        expanded.append(_symbol_to_chunk(sym, score))

    # 按 score 降序取 top_k
    expanded.sort(key=lambda c: c.score, reverse=True)
    expanded = expanded[:top_k]

    if expanded:
        logger.info(
            "Graph expansion added %d chunks for project '%s'",
            len(expanded),
            project_id,
        )

    # 合并：原始 chunks 在前，扩展 chunks 在后
    return chunks + expanded
