"""代码关系提取：基于 Tree-sitter AST 分析函数调用和模块依赖"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

from loguru import logger
from tree_sitter import Parser

from delphi.ingestion.chunker import _LANGUAGES, EXT_MAP

if TYPE_CHECKING:
    from pathlib import Path

    from tree_sitter import Node

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Symbol:
    """代码符号"""

    name: str
    qualified_name: str  # file_path::class_name::method_name
    kind: str  # "function" | "class" | "method" | "module"
    file_path: str
    start_line: int
    end_line: int
    language: str


@dataclass
class Relation:
    """符号间关系"""

    source: str  # qualified_name
    target: str  # qualified_name or unresolved name
    kind: str  # "calls" | "imports" | "inherits" | "contains"


@dataclass
class CodeGraph:
    """代码关系图"""

    symbols: dict[str, Symbol] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)

    def add_symbol(self, symbol: Symbol) -> None:
        self.symbols[symbol.qualified_name] = symbol

    def add_relation(self, relation: Relation) -> None:
        self.relations.append(relation)

    def get_callers(self, name: str) -> list[Relation]:
        """获取调用了指定符号的所有关系"""
        return [r for r in self.relations if r.target == name and r.kind == "calls"]

    def get_callees(self, name: str) -> list[Relation]:
        """获取指定符号调用的所有关系"""
        return [r for r in self.relations if r.source == name and r.kind == "calls"]

    def get_dependencies(self, file_path: str) -> list[Relation]:
        """获取文件的 import 依赖"""
        return [r for r in self.relations if r.source.startswith(file_path) and r.kind == "imports"]

    def to_dict(self) -> dict:
        """序列化为 JSON 兼容的字典"""
        return {
            "symbols": {k: asdict(v) for k, v in self.symbols.items()},
            "relations": [asdict(r) for r in self.relations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> CodeGraph:
        """从字典反序列化"""
        graph = cls()
        for _qn, sd in data.get("symbols", {}).items():
            graph.add_symbol(Symbol(**sd))
        for rd in data.get("relations", []):
            graph.add_relation(Relation(**rd))
        return graph

    def merge(self, other: CodeGraph) -> None:
        """合并另一个图谱到当前图谱"""
        for sym in other.symbols.values():
            self.add_symbol(sym)
        self.relations.extend(other.relations)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _node_text(node: Node) -> str:
    return node.text.decode(errors="replace") if node.text else ""


def _find_children_by_type(node: Node, type_name: str) -> list[Node]:
    return [c for c in node.children if c.type == type_name]


def _find_name(node: Node) -> str:
    """提取节点的名称标识符"""
    for child in node.children:
        if child.type in ("identifier", "name", "property_identifier", "type_identifier"):
            return _node_text(child)
    return ""


def _collect_calls(node: Node, calls: list[str]) -> None:
    """递归收集函数体内的所有 call_expression"""
    if node.type in ("call", "call_expression"):
        func_node = node.child_by_field_name("function")
        if func_node is None and node.children:
            func_node = node.children[0]
        if func_node is not None:
            calls.append(_node_text(func_node))
    for child in node.children:
        _collect_calls(child, calls)


def _qualified(file_path: str, *parts: str) -> str:
    """构建 qualified_name: file_path::class::method"""
    segments = [file_path] + [p for p in parts if p]
    return "::".join(segments)


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------


def _extract_python(root: Node, file_path: str, graph: CodeGraph) -> None:
    """提取 Python 文件中的符号和关系"""
    for child in root.children:
        # imports
        if child.type == "import_statement" or child.type == "import_from_statement":
            graph.add_relation(
                Relation(
                    source=file_path,
                    target=_node_text(child).strip(),
                    kind="imports",
                )
            )
        # top-level functions
        elif child.type == "function_definition":
            _extract_python_function(child, file_path, "", graph)
        # classes
        elif child.type == "class_definition":
            _extract_python_class(child, file_path, graph)


def _extract_python_function(
    node: Node,
    file_path: str,
    parent: str,
    graph: CodeGraph,
) -> None:
    name = _find_name(node)
    qn = _qualified(file_path, parent, name) if parent else _qualified(file_path, name)
    graph.add_symbol(
        Symbol(
            name=name,
            qualified_name=qn,
            kind="method" if parent else "function",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            language="python",
        )
    )
    if parent:
        graph.add_relation(
            Relation(
                source=_qualified(file_path, parent),
                target=qn,
                kind="contains",
            )
        )
    # calls inside body
    body = node.child_by_field_name("body")
    if body:
        calls: list[str] = []
        _collect_calls(body, calls)
        for c in calls:
            graph.add_relation(Relation(source=qn, target=c, kind="calls"))


def _extract_python_class(node: Node, file_path: str, graph: CodeGraph) -> None:
    name = _find_name(node)
    qn = _qualified(file_path, name)
    graph.add_symbol(
        Symbol(
            name=name,
            qualified_name=qn,
            kind="class",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            language="python",
        )
    )
    # inheritance
    for child in node.children:
        if child.type == "argument_list":
            for arg in child.children:
                if arg.type == "identifier":
                    graph.add_relation(Relation(source=qn, target=_node_text(arg), kind="inherits"))
    # methods
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "function_definition":
                _extract_python_function(child, file_path, name, graph)


# ---------------------------------------------------------------------------
# JS / TS extractor
# ---------------------------------------------------------------------------

_JS_FUNC_TYPES = {"function_declaration", "method_definition", "arrow_function"}


def _extract_js(root: Node, file_path: str, lang: str, graph: CodeGraph) -> None:
    """提取 JS/TS 文件中的符号和关系"""
    for child in root.children:
        if child.type == "import_statement":
            graph.add_relation(
                Relation(
                    source=file_path,
                    target=_node_text(child).strip(),
                    kind="imports",
                )
            )
        elif child.type == "export_statement":
            # export may wrap a function/class declaration
            for sub in child.children:
                _extract_js_node(sub, file_path, "", lang, graph)
        else:
            _extract_js_node(child, file_path, "", lang, graph)


def _extract_js_node(
    node: Node,
    file_path: str,
    parent: str,
    lang: str,
    graph: CodeGraph,
) -> None:
    if node.type in _JS_FUNC_TYPES:
        name = _find_name(node)
        if not name and node.type == "arrow_function" and node.parent and node.parent.type == "variable_declarator":
            name = _find_name(node.parent)
        qn = _qualified(file_path, parent, name) if parent else _qualified(file_path, name)
        kind = "method" if parent else "function"
        graph.add_symbol(
            Symbol(
                name=name,
                qualified_name=qn,
                kind=kind,
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                language=lang,
            )
        )
        if parent:
            graph.add_relation(
                Relation(
                    source=_qualified(file_path, parent),
                    target=qn,
                    kind="contains",
                )
            )
        body = node.child_by_field_name("body")
        if body:
            calls: list[str] = []
            _collect_calls(body, calls)
            for c in calls:
                graph.add_relation(Relation(source=qn, target=c, kind="calls"))

    elif node.type == "class_declaration":
        name = _find_name(node)
        qn = _qualified(file_path, name)
        graph.add_symbol(
            Symbol(
                name=name,
                qualified_name=qn,
                kind="class",
                file_path=file_path,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                language=lang,
            )
        )
        # heritage / extends
        for child in node.children:
            if child.type == "class_heritage":
                for sub in child.children:
                    if sub.type == "identifier":
                        graph.add_relation(Relation(source=qn, target=_node_text(sub), kind="inherits"))
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                _extract_js_node(child, file_path, name, lang, graph)


# ---------------------------------------------------------------------------
# C / C++ extractor
# ---------------------------------------------------------------------------


def _extract_c(root: Node, file_path: str, lang: str, graph: CodeGraph) -> None:
    """提取 C/C++ 文件中的符号和关系"""
    for child in root.children:
        if child.type == "preproc_include":
            graph.add_relation(
                Relation(
                    source=file_path,
                    target=_node_text(child).strip(),
                    kind="imports",
                )
            )
        elif child.type == "function_definition":
            name = ""
            declarator = child.child_by_field_name("declarator")
            if declarator:
                name = _find_name(declarator)
                if not name:
                    name = _find_name(child)
            qn = _qualified(file_path, name)
            graph.add_symbol(
                Symbol(
                    name=name,
                    qualified_name=qn,
                    kind="function",
                    file_path=file_path,
                    start_line=child.start_point.row + 1,
                    end_line=child.end_point.row + 1,
                    language=lang,
                )
            )
            body = child.child_by_field_name("body")
            if body:
                calls: list[str] = []
                _collect_calls(body, calls)
                for c in calls:
                    graph.add_relation(Relation(source=qn, target=c, kind="calls"))


# ---------------------------------------------------------------------------
# Go extractor
# ---------------------------------------------------------------------------


def _extract_go(root: Node, file_path: str, graph: CodeGraph) -> None:
    """提取 Go 文件中的符号和关系"""
    for child in root.children:
        if child.type == "import_declaration":
            graph.add_relation(
                Relation(
                    source=file_path,
                    target=_node_text(child).strip(),
                    kind="imports",
                )
            )
        elif child.type == "function_declaration":
            name = _find_name(child)
            qn = _qualified(file_path, name)
            graph.add_symbol(
                Symbol(
                    name=name,
                    qualified_name=qn,
                    kind="function",
                    file_path=file_path,
                    start_line=child.start_point.row + 1,
                    end_line=child.end_point.row + 1,
                    language="go",
                )
            )
            body = child.child_by_field_name("body")
            if body:
                calls: list[str] = []
                _collect_calls(body, calls)
                for c in calls:
                    graph.add_relation(Relation(source=qn, target=c, kind="calls"))
        elif child.type == "method_declaration":
            name = _find_name(child)
            qn = _qualified(file_path, name)
            graph.add_symbol(
                Symbol(
                    name=name,
                    qualified_name=qn,
                    kind="method",
                    file_path=file_path,
                    start_line=child.start_point.row + 1,
                    end_line=child.end_point.row + 1,
                    language="go",
                )
            )
            body = child.child_by_field_name("body")
            if body:
                calls: list[str] = []
                _collect_calls(body, calls)
                for c in calls:
                    graph.add_relation(Relation(source=qn, target=c, kind="calls"))


# ---------------------------------------------------------------------------
# Rust extractor
# ---------------------------------------------------------------------------


def _extract_rust(root: Node, file_path: str, graph: CodeGraph) -> None:
    """提取 Rust 文件中的符号和关系"""
    for child in root.children:
        if child.type == "use_declaration":
            graph.add_relation(
                Relation(
                    source=file_path,
                    target=_node_text(child).strip(),
                    kind="imports",
                )
            )
        elif child.type == "function_item":
            name = _find_name(child)
            qn = _qualified(file_path, name)
            graph.add_symbol(
                Symbol(
                    name=name,
                    qualified_name=qn,
                    kind="function",
                    file_path=file_path,
                    start_line=child.start_point.row + 1,
                    end_line=child.end_point.row + 1,
                    language="rust",
                )
            )
            body = child.child_by_field_name("body")
            if body:
                calls: list[str] = []
                _collect_calls(body, calls)
                for c in calls:
                    graph.add_relation(Relation(source=qn, target=c, kind="calls"))
        elif child.type == "impl_item":
            impl_name = _find_name(child)
            qn_impl = _qualified(file_path, impl_name)
            graph.add_symbol(
                Symbol(
                    name=impl_name,
                    qualified_name=qn_impl,
                    kind="class",
                    file_path=file_path,
                    start_line=child.start_point.row + 1,
                    end_line=child.end_point.row + 1,
                    language="rust",
                )
            )
            body = child.child_by_field_name("body")
            if body:
                for sub in body.children:
                    if sub.type == "function_item":
                        fn_name = _find_name(sub)
                        fn_qn = _qualified(file_path, impl_name, fn_name)
                        graph.add_symbol(
                            Symbol(
                                name=fn_name,
                                qualified_name=fn_qn,
                                kind="method",
                                file_path=file_path,
                                start_line=sub.start_point.row + 1,
                                end_line=sub.end_point.row + 1,
                                language="rust",
                            )
                        )
                        graph.add_relation(
                            Relation(
                                source=qn_impl,
                                target=fn_qn,
                                kind="contains",
                            )
                        )
                        fn_body = sub.child_by_field_name("body")
                        if fn_body:
                            fn_calls: list[str] = []
                            _collect_calls(fn_body, fn_calls)
                            for c in fn_calls:
                                graph.add_relation(Relation(source=fn_qn, target=c, kind="calls"))
        elif child.type == "struct_item":
            name = _find_name(child)
            qn = _qualified(file_path, name)
            graph.add_symbol(
                Symbol(
                    name=name,
                    qualified_name=qn,
                    kind="class",
                    file_path=file_path,
                    start_line=child.start_point.row + 1,
                    end_line=child.end_point.row + 1,
                    language="rust",
                )
            )


# ---------------------------------------------------------------------------
# Java extractor
# ---------------------------------------------------------------------------


def _extract_java(root: Node, file_path: str, graph: CodeGraph) -> None:
    """提取 Java 文件中的符号和关系"""
    for child in root.children:
        if child.type == "import_declaration":
            graph.add_relation(
                Relation(
                    source=file_path,
                    target=_node_text(child).strip(),
                    kind="imports",
                )
            )
        elif child.type == "class_declaration":
            _extract_java_class(child, file_path, "", graph)


def _extract_java_class(
    node: Node,
    file_path: str,
    parent: str,
    graph: CodeGraph,
) -> None:
    name = _find_name(node)
    qn = _qualified(file_path, parent, name) if parent else _qualified(file_path, name)
    graph.add_symbol(
        Symbol(
            name=name,
            qualified_name=qn,
            kind="class",
            file_path=file_path,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            language="java",
        )
    )
    # superclass
    sc = node.child_by_field_name("superclass")
    if sc:
        graph.add_relation(Relation(source=qn, target=_node_text(sc), kind="inherits"))
    # interfaces
    ifaces = node.child_by_field_name("interfaces")
    if ifaces:
        for sub in ifaces.children:
            if sub.type == "type_identifier":
                graph.add_relation(Relation(source=qn, target=_node_text(sub), kind="inherits"))
    # body
    body = node.child_by_field_name("body")
    if body:
        for child in body.children:
            if child.type == "method_declaration":
                m_name = _find_name(child)
                m_qn = _qualified(file_path, name, m_name)
                graph.add_symbol(
                    Symbol(
                        name=m_name,
                        qualified_name=m_qn,
                        kind="method",
                        file_path=file_path,
                        start_line=child.start_point.row + 1,
                        end_line=child.end_point.row + 1,
                        language="java",
                    )
                )
                graph.add_relation(Relation(source=qn, target=m_qn, kind="contains"))
                m_body = child.child_by_field_name("body")
                if m_body:
                    calls: list[str] = []
                    _collect_calls(m_body, calls)
                    for c in calls:
                        graph.add_relation(Relation(source=m_qn, target=c, kind="calls"))
            elif child.type == "class_declaration":
                _extract_java_class(child, file_path, name, graph)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_LANG_EXTRACTORS = {
    "python": lambda root, fp, graph: _extract_python(root, fp, graph),
    "javascript": lambda root, fp, graph: _extract_js(root, fp, "javascript", graph),
    "typescript": lambda root, fp, graph: _extract_js(root, fp, "typescript", graph),
    "tsx": lambda root, fp, graph: _extract_js(root, fp, "tsx", graph),
    "c": lambda root, fp, graph: _extract_c(root, fp, "c", graph),
    "cpp": lambda root, fp, graph: _extract_c(root, fp, "cpp", graph),
    "go": lambda root, fp, graph: _extract_go(root, fp, graph),
    "rust": lambda root, fp, graph: _extract_rust(root, fp, graph),
    "java": lambda root, fp, graph: _extract_java(root, fp, graph),
}


def extract_graph(source: bytes, file_path: str, language: str) -> CodeGraph:
    """从单个文件提取代码关系图"""
    graph = CodeGraph()
    lang_obj = _LANGUAGES.get(language)
    if lang_obj is None:
        logger.debug("不支持的语言, 跳过提取: file={}, language={}", file_path, language)
        return graph

    parser = Parser(lang_obj)
    tree = parser.parse(source)

    extractor = _LANG_EXTRACTORS.get(language)
    if extractor:
        extractor(tree.root_node, file_path, graph)

    logger.debug(
        "单文件图谱提取完成: file={}, language={}, 符号数={}, 关系数={}",
        file_path, language, len(graph.symbols), len(graph.relations),
    )
    return graph


def extract_from_directory(
    root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> CodeGraph:
    """从目录中所有代码文件提取关系图"""
    from pathlib import Path as _Path

    merged = CodeGraph()
    root = _Path(root)
    logger.info("开始目录级图谱提取: root={}, include={}, exclude={}", root, include, exclude)

    file_count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        lang = EXT_MAP.get(path.suffix.lower())
        if lang is None:
            continue

        rel = str(path.relative_to(root))

        # include / exclude filtering
        if include and not any(_glob_match(rel, pat) for pat in include):
            continue
        if exclude and any(_glob_match(rel, pat) for pat in exclude):
            continue

        try:
            source = path.read_bytes()
            file_graph = extract_graph(source, rel, lang)
            merged.merge(file_graph)
            file_count += 1
        except Exception:
            logger.warning("文件图谱提取失败: {}", path, exc_info=True)

    logger.info(
        "目录级图谱提取完成: root={}, 处理文件数={}, 总符号数={}, 总关系数={}",
        root, file_count, len(merged.symbols), len(merged.relations),
    )
    return merged


def _glob_match(path: str, pattern: str) -> bool:
    """简单 glob 匹配"""
    from fnmatch import fnmatch

    return fnmatch(path, pattern)
